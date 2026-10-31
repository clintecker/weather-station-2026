/* The interim map (wsmp_catalog_map.h). Each module's fields enter the bitmap only while the module
 * is in the layout. A missing channel gives the field's INVALID code (the catalog cannot carry the
 * WSMP qualities "partial" and "suspect"; MODULES and the health report show them). Left out: the
 * minute extremes (fields 21-24): the gateway derives extremes from the means (WSMP rule 6).
 * The wind speed is the pulse increment since the previous reading of the same module boot times
 * the registry factor; the first reading after a (re)start has no speed and no direction.
 *
 * Power (docs/superpowers/specs/2026-10-29-power-telemetry-design.md sections 3.2, 5.2, 5.3 and 9.7).
 * The battery module (type 8) fills fields 11-16, the rails module (type 9) fields 26-30, 32 and 33.
 * Both are base-board modules, always in the layout (App/mod_power.h), so a dead part gives INVALID
 * fields, never absent ones. Presence per slot:
 *   - "not fitted" (WSMP_QUAL_NOT_FITTED: the build, WS_POWER_PROFILE, has no source): the field is
 *     left out of the bitmap. Absence is a property of the build, never of a part's state;
 *   - missing or fault (and unknown codes): INVALID;
 *   - a long window (WSMP-T3): INVALID for the means; the counters (13-16) keep their value;
 *   - an energy slot marked missing (a step without a fresh cell voltage): INVALID for 13 and 14 only.
 * The fill per phase (spec section 3.2):
 *   phase A  11-16 (gauge, battery INA228), 26 (the battery INA228's VBUS on OUT), 28 (the PA10 divider);
 *            27, 29, 30, 32 and 33 are not fitted, so absent;
 *   phase B  every power field: one INA228 per rail (load, solar, USB-C) besides the battery's.
 * Field 28 (charger input voltage) is measured after the sources join, so in phase A the source is
 * unknown: the map never infers solar or USB-C from it (no heuristic; solar and USB-C are never
 * connected together, and only phase B's upstream monitors tell them apart).
 * Currents are mean mA as two's complement in the slot; the catalog code is I + 32768, and put()'s
 * range check (ws_obs_code_ok) alone decides INVALID: -32768 to +32766 mA encode, anything else is
 * INVALID (no separate clamp). Fields 17 and 18 (retired) are no longer mapped: the health report
 * carries SOC and the charger status. */
#include "wsmp_catalog_map.h"
#include <math.h>
#include "wsmp_host.h"

#define PRESSURE_OFFSET_DECI_HPA 3000U   /* field 2: 0.1 hPa, offset 300.0 hPa */
#define WIND_TOP_DECI 750U               /* 75.0 m/s */
#define CALM_DECI 5U                     /* below 0.5 m/s */
#define DEG_FULL 360
#define UMS_PER_DECI_MS 100000ULL        /* um/s in 0.1 m/s */
#define MS_PER_S 1000ULL
#define RAD_TO_DEG 57.29577951f
#define CURRENT_OFFSET 32768U           /* fields 12, 27, 30, 33: offset binary, code = mA + 32768 */
#define RAIL_FIELDS 7U                   /* the rails module's channels (registry type 9) */

/* A counter without a usable value: its quality is "missing" on the radio (WSMP section 9: missing,
   fault, or a code this station does not know). A mean, gust or rate is also unusable over a window
   longer than a minute (WSMP-T3, for example the first window after a quarantine). Counters stay
   usable there: they do not depend on the window. */
static int counter_missing(const wsmp_snapshot *s, unsigned i) { return wsmp_quality_air(s->slot[i].quality) == WSMP_QUAL_MISSING; }
static int long_window(const wsmp_snapshot *s) { return (s->flags & WSMP_FLAG_LONG_WINDOW) != 0; }
static int missing(const wsmp_snapshot *s, unsigned i) { return counter_missing(s, i) || long_window(s); }
/* The build has no source for the slot (WSMP 1.1, quality 6): its field stays out of the bitmap. Checked
   before counter_missing(), which sees quality 6 as "missing" (its radio code). */
static int not_fitted(const wsmp_snapshot *s, unsigned i) { return s->slot[i].quality == WSMP_QUAL_NOT_FITTED; }
/* Every code goes in only if its field can hold it; anything else is INVALID, so a reading always
   encodes (an out-of-range code would fail the minute, and ten such minutes trip the watchdog). */
static void put(ws_obs_t *o, unsigned field, uint32_t code)
{
  o->bitmap |= WS_F(field);
  o->code[field] = ws_obs_code_ok(field, code) ? code : ws_obs_invalid(field);
}
static void invalid(ws_obs_t *o, unsigned field) { put(o, field, ws_obs_invalid(field)); }

/* A mean of temperature (slot 0) and humidity (slot 1) into two catalog fields. Each channel has its
   own sample count (a suspect sample leaves only its own channel), so each slot is checked alone. */
static void th(ws_obs_t *o, const wsmp_snapshot *s, unsigned ft, unsigned fh)
{
  if (missing(s, 0)) invalid(o, ft);
  else put(o, ft, ws_code_temp_centi((int32_t)s->slot[0].value));
  if (missing(s, 1)) invalid(o, fh);
  else put(o, fh, ws_code_rh_centi((int32_t)s->slot[1].value));
}

static void air(ws_obs_t *o, wsmp_map_summary *sum)
{
  const wsmp_snapshot *s = wsmp_host_snapshot(P_AIR_TH);
  if (!s) return;
  th(o, s, WS_FI_TEMPERATURE_C, WS_FI_HUMIDITY_PCT);
  unsigned n = missing(s, 0) ? 0U : s->slot[0].count;
  put(o, WS_FI_TH_SAMPLES, n > WS_TH_SAMPLES_MAX ? WS_TH_SAMPLES_MAX : n);
  sum->th_valid = !missing(s, 0);
  sum->t = sum->th_valid ? (int16_t)(int32_t)s->slot[0].value : 0;
  sum->h_valid = sum->th_valid && !missing(s, 1);   /* RH can be missing with a valid temperature */
  sum->h = sum->h_valid ? (uint16_t)s->slot[1].value : 0U;
  sum->th_samples = n;
}

static void pressure_uva_enclosure(ws_obs_t *o)
{
  const wsmp_snapshot *p = wsmp_host_snapshot(P_PRESSURE), *u = wsmp_host_snapshot(P_UVA), *e = wsmp_host_snapshot(P_ENCL_TH);
  if (p)
  {
    uint32_t v = p->slot[0].value;
    if (missing(p, 0) || v < PRESSURE_OFFSET_DECI_HPA) invalid(o, WS_FI_PRESSURE_HPA);   /* put() refuses above the top */
    else put(o, WS_FI_PRESSURE_HPA, v - PRESSURE_OFFSET_DECI_HPA);
  }
  if (u)
  {
    if (missing(u, 0)) invalid(o, WS_FI_UVA_RAW);
    else put(o, WS_FI_UVA_RAW, u->slot[0].value);
  }
  if (e) th(o, e, WS_FI_ENCLOSURE_TEMP_C, WS_FI_ENCLOSURE_RH_PCT);
}

/* The previous pulse counter of the same module boot, for the speed. */
static uint32_t prev_pulses;
static uint16_t prev_boot;
static int have_prev;

static uint32_t speed_deci(const wsmp_snapshot *s, int *known)
{
  uint32_t inc = s->slot[0].value - prev_pulses;
  *known = have_prev && prev_boot == s->boot16 && !missing(s, 0) && s->window_ms > 0;
  have_prev = !counter_missing(s, 0);   /* a long window's counter is still a base for the next */
  prev_pulses = s->slot[0].value;
  prev_boot = s->boot16;
  if (!*known) return 0;
  uint64_t num = (uint64_t)inc * WSMP_WIND_UMS_PER_HZ * MS_PER_S * 2U, den = (uint64_t)s->window_ms * UMS_PER_DECI_MS * 2U;
  return (uint32_t)((num + den / 2U) / den);
}

static uint32_t direction(const wsmp_snapshot *s)
{
  float d = atan2f((float)(int32_t)s->slot[2].value, (float)(int32_t)s->slot[3].value) * RAD_TO_DEG;
  int deg = (int)lroundf(d);
  if (deg < 0) deg += DEG_FULL;
  return (uint32_t)(deg % DEG_FULL);
}

static void wind(ws_obs_t *o)
{
  const wsmp_snapshot *s = wsmp_host_snapshot(P_WIND);
  if (!s) { have_prev = 0; return; }
  int known;
  uint32_t speed = speed_deci(s, &known);
  if (!known || speed > WIND_TOP_DECI) { invalid(o, WS_FI_WIND_SPEED_MS); invalid(o, WS_FI_WIND_DIR_DEG); }
  else
  {
    put(o, WS_FI_WIND_SPEED_MS, speed);
    if (speed < CALM_DECI) put(o, WS_FI_WIND_DIR_DEG, WS_WIND_DIR_CALM);
    else if (missing(s, 2)) invalid(o, WS_FI_WIND_DIR_DEG);
    else put(o, WS_FI_WIND_DIR_DEG, direction(s));
  }
  uint32_t gust = (s->slot[1].value + 5U) / 10U;   /* 0.01 m/s to 0.1 m/s, half up */
  if (missing(s, 1) || gust > WIND_TOP_DECI) invalid(o, WS_FI_WIND_GUST_MS);
  else put(o, WS_FI_WIND_GUST_MS, gust);
}

static void rain(ws_obs_t *o)
{
  const wsmp_snapshot *s = wsmp_host_snapshot(P_RAIN);
  if (!s) return;
  if (counter_missing(s, 0)) invalid(o, WS_FI_RAIN_TIPS);
  else put(o, WS_FI_RAIN_TIPS, s->slot[0].value % ws_obs_invalid(WS_FI_RAIN_TIPS));   /* wraps below INVALID */
}

/* One power mean: a voltage (mV, unsigned) or a current (mA, two's complement). A current's code wraps
   in 32 bits, so exactly -32768..+32766 mA land on codes 0..65534 and put() turns the rest INVALID. */
static void power_mean(ws_obs_t *o, const wsmp_snapshot *s, unsigned slot, unsigned field, int current)
{
  if (not_fitted(s, slot)) return;
  if (missing(s, slot)) { invalid(o, field); return; }
  put(o, field, current ? s->slot[slot].value + CURRENT_OFFSET : s->slot[slot].value);
}

/* The battery module (type 8): slot 0 the cell voltage (field 11), slot 1 the battery current, + into
   the cell (field 12), slots 2-5 the counters (fields 13-16), which wrap like their 3-byte fields. */
static void battery(ws_obs_t *o)
{
  static const unsigned counter_field[4] = { WS_FI_ENERGY_IN_MWH, WS_FI_ENERGY_OUT_MWH, WS_FI_CHARGE_IN_MAH, WS_FI_CHARGE_OUT_MAH };
  const wsmp_snapshot *s = wsmp_host_snapshot(P_BATTERY);
  if (!s) return;
  power_mean(o, s, 0, WS_FI_BATT_MV, 0);
  power_mean(o, s, 1, WS_FI_BATT_CURRENT_MA, 1);
  for (unsigned i = 0; i < 4; i++)
  {
    if (not_fitted(s, 2 + i)) continue;
    if (counter_missing(s, 2 + i)) invalid(o, counter_field[i]);
    else put(o, counter_field[i], s->slot[2 + i].value % ws_obs_invalid(counter_field[i]));
  }
}

/* The rails module (type 9), slots in registry order: load voltage and current, charger input voltage,
   solar voltage and current, USB-C voltage and current. */
static void rails(ws_obs_t *o)
{
  static const struct { uint8_t field, current; } rail[RAIL_FIELDS] = {
    { WS_FI_LOAD_MV, 0 }, { WS_FI_LOAD_CURRENT_MA, 1 }, { WS_FI_CHARGER_INPUT_MV, 0 }, { WS_FI_SOLAR_MV, 0 },
    { WS_FI_SOLAR_CURRENT_MA, 1 }, { WS_FI_USB_MV, 0 }, { WS_FI_USB_CURRENT_MA, 1 } };
  const wsmp_snapshot *s = wsmp_host_snapshot(P_RAILS);
  if (!s) return;
  for (unsigned i = 0; i < RAIL_FIELDS; i++) power_mean(o, s, i, rail[i].field, rail[i].current);
}

void wsmp_map_obs(ws_obs_t *o, wsmp_map_summary *sum)
{
  *sum = (wsmp_map_summary){ 0 };
  o->bitmap = 0;
  air(o, sum);
  pressure_uva_enclosure(o);
  wind(o);
  rain(o);
  battery(o);
  rails(o);
  if (o->bitmap) return;
  /* No module in the layout: the air fields go INVALID, as before WSMP, so the reading still encodes
     (the catalog refuses an empty bitmap) and the gateway sees the minute. */
  invalid(o, WS_FI_TEMPERATURE_C);
  invalid(o, WS_FI_HUMIDITY_PCT);
  put(o, WS_FI_TH_SAMPLES, 0);
}
