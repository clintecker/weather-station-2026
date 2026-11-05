/* Power acquisition (power_acq.h): the rail table's INA228s, the MAX17048, the board ADC and the
 * bq24074 pins, each on its own step machine. Register maps and conversions are firmware/common/
 * power_regs.h (TI SBOS904, Analog Devices MAX17048, ST DS13293, TI SLUS810), the constants
 * App/power_config.h, the design docs/superpowers/specs/2026-10-29-power-telemetry-design.md
 * sections 3.1, 3.2, 6.3, 9.4 and 9.5. */
#define WS_CHECK_FILE 18
#include "power_acq.h"
#include <string.h>
#include "board_inputs.h"
#include "mod_power.h"
#include "power_regs.h"
#include "ws_check.h"
#include "ws_round.h"
#include "wsmp.h"

#define RAIL_PERIOD_MS 1000U
#define TEMP_EVERY 60U                 /* rail steps between DIETEMP reads: 60 s */
#define GAUGE_PERIOD_MS 15000U
#define ADC_PERIOD_MS 1000U
#define PIN_PERIOD_MS 250U
#define VCELL_FRESH_MS 20000U          /* the oldest VCELL a step's energy may use */
#define EDGE_POLLS 8U                  /* pin polls in 2 s */
#define FAULT_EDGES 3U                 /* CHG edges within 2 s that make a fault (2 Hz flashing) */
#define FAULT_CLEAR_MS 4000U           /* without an edge for this long, the fault clears */
#define ACC_MASK 0xFFFFFFFFFFULL       /* CHARGE is a 40-bit two's-complement register */
#define ACC_SIGN 0x8000000000ULL
#define UAS_PER_MAH 3600000LL
#define NWS_PER_MWH 3600000000LL       /* nW s: uA s x uV / 1000 */
#define UV_PER_MV 1000
#define UA_PER_MA 1000
#define MC_PER_DECI_C 100
#define CENTI_RATE 100                 /* m%/h to 0.1 %/h */

typedef enum { RS_IDLE, RS_CAL_CHECK, RS_MANUFACTURER, RS_DEVICE, RS_CAL, RS_VBUS, RS_CHARGE, RS_TEMP } rail_step;
typedef enum { GS_IDLE, GS_VERSION, GS_VCELL, GS_SOC, GS_CRATE } gauge_step;

typedef struct {
  int64_t dq_uas;        /* sum of the window's charge deltas, sign applied */
  int64_t vbus_mv;       /* sum of the window's VBUS reads */
  uint32_t covered_ms;   /* sum of the valid steps' elapsed time */
  uint16_t steps, vbus_n;
  uint8_t gap;           /* a step was lost: a failure or a reset of the part */
} rail_win;

typedef struct {
  rail_step step;
  uint8_t cal_needed, have_base, fault, temp_ok, since_temp;
  uint16_t manufacturer;
  uint32_t next_ms, base_ms;
  uint64_t base_charge;
  int32_t die_mc;
  uint8_t buf[5], cal[3];
  rail_win win;
  int32_t live_ma_x100, live_vbus_mv;   /* the latest step's mean current (0.01 mA) and VBUS, for the screen */
  uint8_t live_step, live_vbus;         /* a step / a VBUS read since the part was last lost */
} rail_t;

typedef struct {
  gauge_step step;
  uint8_t ok, fault, vcell_ok;
  uint32_t next_ms, vcell_ms;
  int32_t vcell_uv;
  uint16_t soc_256;
  int16_t rate;
  uint8_t buf[2];
  int64_t sum_mv;
  uint16_t n;
} gauge_t;

typedef struct {
  uint32_t next_ms, seq;                        /* seq: the last ADC sequence sampled, kept across windows */
  int64_t vin_mv, iset_ma, vdda_mv;
  uint16_t vin_n, iset_n, vdda_n;
  uint8_t vin_clipped, iset_bad;
} adc_win;

typedef struct {
  uint32_t next_ms, last_edges, last_edge_ms, ring[EDGE_POLLS];
  unsigned at;
  int pins;
  uint8_t fault;
} pins_t;

typedef struct {
  uint32_t now, start_ms;
  uint8_t latched, energy_missing;
  uint16_t cal[POWER_RAIL_COUNT];
  int64_t charge_in, charge_out, energy_in, energy_out;   /* since init: uA s and nW s */
  rail_t rail[POWER_RAIL_COUNT];
  gauge_t gauge;
  adc_win adc;
  pins_t pin;
} acq_t;

static acq_t pa;
static const uint8_t reg_shunt_cal = 0x02U, reg_vbus = 0x05U, reg_dietemp = 0x06U, reg_charge = 0x0AU,
                     reg_manufacturer = 0x3EU, reg_device = 0x3FU;
static const uint8_t reg_vcell = 0x02U, reg_soc = 0x04U, reg_version = 0x08U, reg_crate = 0x16U;

static uint16_t be16(const uint8_t *p) { return (uint16_t)(p[0] << 8 | p[1]); }
static uint32_t be24(const uint8_t *p) { return (uint32_t)p[0] << 16 | (uint32_t)p[1] << 8 | p[2]; }
static uint64_t be40(const uint8_t *p) { return (uint64_t)p[0] << 32 | (uint64_t)be24(p + 1) << 8 | p[4]; }
static int16_t sat16(int64_t v) { return (int16_t)(v > INT16_MAX ? INT16_MAX : v < -INT16_MAX ? -INT16_MAX : v); }

/* 1 when a periodic step is due, and its next time; the signed comparison survives the clock's wrap. */
static int due(uint32_t *next_ms, uint32_t period_ms)
{
  if ((int32_t)(pa.now - *next_ms) < 0) return 0;
  *next_ms += period_ms;
  if ((int32_t)(pa.now - *next_ms) >= 0) *next_ms = pa.now + period_ms;   /* fell behind: resync */
  return 1;
}

/* ---- the INA228 rails ---- */

/* A NACK or another chip is an absent part (its slots missing); anything else is a bus fault. The
   part's base is lost, so the window has a gap, and it is identified and calibrated again. */
static void rail_failed(rail_t *r, int rc)
{
  r->fault = rc != I2C_ENACK_ADDR && rc != I2C_ENACK_DATA && rc != I2C_EID;
  if (r->have_base) r->win.gap = 1;
  r->have_base = 0;
  r->cal_needed = 1;
  r->temp_ok = 0;
  r->live_step = r->live_vbus = 0;
  r->step = RS_IDLE;
}

static void rail_submit(unsigned i, rail_step s, const uint8_t *tx, uint8_t txlen, uint8_t rxlen)
{
  rail_t *r = &pa.rail[i];
  r->step = s;
  /* The bus refuses only a busy client or a bad form; one step at a time makes neither. */
  if (!WS_CHECK(i2c_bus_submit(POWER_RAILS[i].client, POWER_RAILS[i].addr, tx, txlen, rxlen ? r->buf : NULL, rxlen) == 0))
    rail_failed(r, I2C_EBUS);
}

static void rail_read(unsigned i, rail_step s, const uint8_t *reg, uint8_t len) { rail_submit(i, s, reg, 1, len); }

static void rail_measure(unsigned i)
{
  if (POWER_RAILS[i].vbus_slot != PS_NONE) rail_read(i, RS_VBUS, &reg_vbus, 3);
  else rail_read(i, RS_CHARGE, &reg_charge, 5);
}

static void rail_identified(unsigned i)
{
  rail_t *r = &pa.rail[i];
  if (r->step == RS_MANUFACTURER) { r->manufacturer = be16(r->buf); rail_read(i, RS_DEVICE, &reg_device, 2); return; }
  if (!ina228_ids_match(r->manufacturer, be16(r->buf))) { rail_failed(r, I2C_EID); return; }
  r->cal[0] = reg_shunt_cal; r->cal[1] = (uint8_t)(pa.cal[i] >> 8); r->cal[2] = (uint8_t)pa.cal[i];
  rail_submit(i, RS_CAL, r->cal, sizeof r->cal, 0);
}

/* SHUNT_CAL as written, or the part was reset since (with its accumulators): identify it again. */
static void rail_cal_checked(unsigned i)
{
  rail_t *r = &pa.rail[i];
  if (be16(r->buf) == pa.cal[i]) { rail_measure(i); return; }
  if (r->have_base) r->win.gap = 1;
  r->have_base = 0;
  r->cal_needed = 1;
  r->live_step = r->live_vbus = 0;   /* the screen's values are from before the reset */
  rail_read(i, RS_MANUFACTURER, &reg_manufacturer, 2);
}

/* One battery step: the counters by sign, and the energy at the cell voltage when it is fresh. */
static void battery_step(int64_t uas)
{
  if (uas >= 0) pa.charge_in += uas;
  else pa.charge_out -= uas;
  if (uas == 0) return;
  const gauge_t *g = &pa.gauge;
  if (!g->vcell_ok || pa.now - g->vcell_ms > VCELL_FRESH_MS) { pa.energy_missing = 1; return; }
  int64_t nws = uas * g->vcell_uv / UV_PER_MV;   /* |uas| < 2^41, vcell < 2^23 */
  if (nws >= 0) pa.energy_in += nws;
  else pa.energy_out -= nws;
}

/* The CHARGE read: the delta since the base (wrapped to 40 bits) is a step, then the new base. The
   first read after a calibration or a failure is only the base. */
static void rail_charge(unsigned i)
{
  rail_t *r = &pa.rail[i];
  uint64_t raw = be40(r->buf), d = (raw - r->base_charge) & ACC_MASK;
  if (r->have_base)
  {
    int64_t counts = (d & ACC_SIGN) ? (int64_t)d - (int64_t)(ACC_MASK + 1U) : (int64_t)d;
    int64_t uas = POWER_RAILS[i].sign * ina228_charge_uas(counts, POWER_RAILS[i].current_lsb_ua);
    r->win.dq_uas += uas;
    r->win.covered_ms += pa.now - r->base_ms;
    r->win.steps++;
    if (pa.now != r->base_ms)
    {
      r->live_ma_x100 = (int32_t)ws_div_round(uas * 100, (int64_t)(pa.now - r->base_ms));   /* uA s / ms = mA */
      r->live_step = 1;
    }
    if (i == POWER_RAIL_BATTERY) battery_step(uas);
  }
  r->base_charge = raw;
  r->base_ms = pa.now;
  r->have_base = 1;
  r->fault = 0;
  if (r->since_temp < TEMP_EVERY) r->since_temp++;
  if (!r->temp_ok || r->since_temp >= TEMP_EVERY) rail_read(i, RS_TEMP, &reg_dietemp, 2);
  else r->step = RS_IDLE;
}

static void rail_done(unsigned i, int rc)
{
  rail_t *r = &pa.rail[i];
  if (rc) { rail_failed(r, rc); return; }
  switch (r->step)
  {
    case RS_CAL_CHECK: rail_cal_checked(i); break;
    case RS_MANUFACTURER: case RS_DEVICE: rail_identified(i); break;
    case RS_CAL: r->cal_needed = 0; r->have_base = 0; rail_measure(i); break;
    case RS_VBUS:
      r->win.vbus_mv += ws_div_round(ina228_vbus_uv(be24(r->buf)), UV_PER_MV);
      r->win.vbus_n++;
      r->live_vbus_mv = (int32_t)ws_div_round(ina228_vbus_uv(be24(r->buf)), UV_PER_MV); r->live_vbus = 1;
      rail_read(i, RS_CHARGE, &reg_charge, 5);
      break;
    case RS_CHARGE: rail_charge(i); break;
    case RS_TEMP: r->die_mc = ina228_dietemp_mc(be16(r->buf)); r->temp_ok = 1; r->since_temp = 0; r->step = RS_IDLE; break;
    default: (void)WS_CHECK(0); r->step = RS_IDLE; break;   /* no transfer was out: a bug */
  }
}

static void rail_tick(unsigned i)
{
  rail_t *r = &pa.rail[i];
  if (r->step != RS_IDLE || !due(&r->next_ms, RAIL_PERIOD_MS)) return;
  if (r->cal_needed) rail_read(i, RS_MANUFACTURER, &reg_manufacturer, 2);
  else rail_read(i, RS_CAL_CHECK, &reg_shunt_cal, 2);
}

/* ---- the gauge ---- */

static void gauge_read(gauge_step s, const uint8_t *reg)
{
  gauge_t *g = &pa.gauge;
  g->step = s;
  if (!WS_CHECK(i2c_bus_submit(I2C_C_MAX17048, POWER_ADDR_GAUGE, reg, 1, g->buf, 2) == 0)) g->step = GS_IDLE;
}

/* A NACK or another chip is an absent gauge; anything else a bus fault. Its values go with it. */
static void gauge_failed(int rc)
{
  gauge_t *g = &pa.gauge;
  g->fault = rc != I2C_ENACK_ADDR && rc != I2C_ENACK_DATA && rc != I2C_EID;
  g->ok = g->vcell_ok = 0;
  g->step = GS_IDLE;
}

static void gauge_done(int rc)
{
  gauge_t *g = &pa.gauge;
  uint16_t v = be16(g->buf);
  if (rc) { gauge_failed(rc); return; }
  switch (g->step)
  {
    case GS_VERSION:
      if (max17048_version_match(v)) gauge_read(GS_VCELL, &reg_vcell);
      else gauge_failed(I2C_EID);
      break;
    case GS_VCELL:
      g->vcell_uv = max17048_vcell_uv(v); g->vcell_ms = pa.now; g->vcell_ok = 1;
      g->sum_mv += ws_div_round(g->vcell_uv, UV_PER_MV); g->n++;
      gauge_read(GS_SOC, &reg_soc);
      break;
    case GS_SOC: g->soc_256 = max17048_soc_256(v); gauge_read(GS_CRATE, &reg_crate); break;
    case GS_CRATE:
      g->rate = sat16(ws_div_round(max17048_crate_mpct_h(v), CENTI_RATE));
      g->ok = 1; g->fault = 0; g->step = GS_IDLE;
      break;
    default: (void)WS_CHECK(0); g->step = GS_IDLE; break;   /* no transfer was out: a bug */
  }
}

/* ---- the board ADC and the pins ---- */

/* One sample of the latest sequence, VDDA-scaled. A clipped result (>= 4080) is out of range: the
   minute's charger input is missing, and ISET (while PGOOD is asserted) gives no current. A sequence
   already sampled is no sample (spec section 9.6): a stalled ADC leaves the window empty, so the charger
   input is missing and VDDA and the charger's battery current are none, not the last values again. */
static void adc_sample(void)
{
  board_power_adc_t s;
  adc_win *a = &pa.adc;
  if (board_power_adc(&s) != 0) return;   /* no sequence, or the ADC failed: no sample */
  if (s.seq == a->seq) return;            /* no new sequence since the last sample */
  a->seq = s.seq;
  a->vdda_mv += s.vdda_mv; a->vdda_n++;
  if (adc_clipped(s.vin_raw)) a->vin_clipped = 1;
  else { a->vin_mv += divider_mv_ppm(adc_pin_uv(s.vin_raw, s.vdda_mv), POWER_VIN_DIVIDER_PPM); a->vin_n++; }
  if (!((unsigned)pa.pin.pins & POWER_PGOOD)) { a->iset_n++; return; }   /* no input, no charge: 0 mA */
  if (adc_clipped(s.iset_raw)) { a->iset_bad = 1; return; }
  int32_t v_iset_uv = unscale_ppm(adc_pin_uv(s.iset_raw, s.vdda_mv), POWER_ISET_GAIN_PPM);   /* the 10k/1M network */
  a->iset_ma += ws_div_round(iset_charge_ua(v_iset_uv, POWER_R_ISET_OHM), UA_PER_MA);
  a->iset_n++;
}

/* The CHG flash rule (spec section 6.3): 3 or more edges within 2 s is a fault, which clears after 4 s
   without an edge. ring holds the edge count of each of the last 8 polls (2 s). */
static void pins_poll(void)
{
  pins_t *p = &pa.pin;
  uint32_t edges = board_charger_edges();
  p->pins = board_charger_pins();
  if (edges != p->last_edges) { p->last_edges = edges; p->last_edge_ms = pa.now; }
  uint32_t recent = edges - p->ring[p->at];
  p->ring[p->at] = edges;
  p->at = (p->at + 1U) % EDGE_POLLS;
  if (recent >= FAULT_EDGES) p->fault = 1;
  else if (p->fault && pa.now - p->last_edge_ms >= FAULT_CLEAR_MS) p->fault = 0;
}

static uint8_t charger_status(void)
{
  unsigned pins = (unsigned)pa.pin.pins;
  uint8_t st = (pins & POWER_PGOOD) ? POWER_STATUS_POWER_GOOD : 0U;   /* CHG without PGOOD is kept */
  if (pa.pin.fault) st |= POWER_STATUS_FAULT;
  else if (pins & POWER_CHG) st |= POWER_STATUS_CHARGING;
  return st;   /* stage 0 and active input 0: the pins cannot tell (phase A and B) */
}

/* ---- the API ---- */

void power_acq_init(uint32_t now_ms)
{
  memset(&pa, 0, sizeof pa);
  pa.now = pa.start_ms = now_ms;
  for (unsigned i = 0; i < POWER_RAIL_COUNT; i++)
  {
    pa.cal[i] = ina228_shunt_cal(POWER_RAILS[i].shunt_uohm, POWER_RAILS[i].current_lsb_ua);
    (void)WS_CHECK(pa.cal[i] != 0U);   /* power_config.h: a shunt and step that fit SHUNT_CAL */
    pa.rail[i] = (rail_t){ .cal_needed = 1, .next_ms = now_ms };
  }
  pa.gauge.next_ms = pa.adc.next_ms = pa.pin.next_ms = now_ms;
  pa.pin.last_edges = board_charger_edges();
  pa.pin.last_edge_ms = now_ms;
  for (unsigned i = 0; i < EDGE_POLLS; i++) pa.pin.ring[i] = pa.pin.last_edges;
}

void power_acq_tick(uint32_t now_ms)
{
  pa.now = now_ms;
  if (due(&pa.pin.next_ms, PIN_PERIOD_MS)) pins_poll();
  if (due(&pa.adc.next_ms, ADC_PERIOD_MS)) adc_sample();
  for (unsigned i = 0; i < POWER_RAIL_COUNT; i++) rail_tick(i);
  if (pa.gauge.step == GS_IDLE && due(&pa.gauge.next_ms, GAUGE_PERIOD_MS)) gauge_read(GS_VERSION, &reg_version);
}

void power_acq_i2c_done(enum i2c_client c, int rc)
{
  if (c == I2C_C_MAX17048) { gauge_done(rc); return; }
  for (unsigned i = 0; i < POWER_RAIL_COUNT; i++)
    if (POWER_RAILS[i].client == c) { rail_done(i, rc); return; }
  (void)WS_CHECK(0);   /* a client this profile has no rail for never submits: ignore it */
}

void power_acq_live(power_live_t *p)
{
  const rail_t *b = &pa.rail[POWER_RAIL_BATTERY];
  const gauge_t *g = &pa.gauge;
  *p = (power_live_t){ 0 };
  p->batt_ok = b->live_step;
  p->batt_ma_x100 = b->live_step ? b->live_ma_x100 : 0;
  for (unsigned i = 0; i < POWER_RAIL_COUNT; i++)
    if (POWER_RAILS[i].vbus_slot == PS_LOAD_MV && pa.rail[i].live_vbus) p->out_mv = pa.rail[i].live_vbus_mv;
  p->gauge_ok = g->ok;
  if (g->vcell_ok) p->vcell_mv = (uint16_t)ws_div_round(g->vcell_uv, UV_PER_MV);
  if (g->ok) p->soc_pct_x10 = (uint16_t)ws_div_round((int64_t)g->soc_256 * 10, 256);
  p->charger = charger_status();
  p->charging = (p->charger & POWER_STATUS_CHARGING) != 0U;
  static const uint8_t current[PL_RAILS] = { PS_LOAD_MA, PS_SOLAR_MA, PS_USB_MA };
  for (unsigned k = 0; k < PL_RAILS; k++)   /* bound: the 3 rails beside the battery */
    for (unsigned i = 0; i < POWER_RAIL_COUNT; i++)   /* bound: the profile's rails */
    {
      if (POWER_RAILS[i].current_slot != current[k]) continue;
      const rail_t *r = &pa.rail[i];
      power_rail_live_t *l = &p->rail[k];
      l->fitted = 1;
      l->ok = r->live_step;
      l->ma_x100 = r->live_step ? r->live_ma_x100 : 0;
      l->mv = r->live_step && r->live_vbus ? r->live_vbus_mv : 0;
    }
}

int power_acq_fitted(enum power_slot s)
{
  if (s <= PS_CHARGE_OUT || s == PS_CHARGER_IN_MV) return 1;   /* the gauge, the battery rail, the ADC */
  for (unsigned i = 0; i < POWER_RAIL_COUNT; i++)
    if (POWER_RAILS[i].current_slot == s || POWER_RAILS[i].vbus_slot == s) return 1;
  return 0;
}

/* A slot's quality: missing (or fault, after a bus fault) without a sample, partial in the first
   window or when incomplete, else good. */
static uint8_t quality(unsigned n, int complete, int fault)
{
  if (n == 0U) return fault ? (uint8_t)WSMP_QUAL_FAULT : (uint8_t)WSMP_QUAL_MISSING;
  return (!pa.latched || !complete) ? (uint8_t)WSMP_QUAL_PARTIAL : (uint8_t)WSMP_QUAL_GOOD;
}

/* n samples a period apart fill the window, short of one at its edge. */
static int filled(unsigned n, uint32_t period_ms, uint32_t window_ms) { return (uint64_t)(n + 1U) * period_ms >= window_ms; }

static int32_t mean(int64_t sum, unsigned n) { return n ? (int32_t)ws_div_round(sum, (int64_t)n) : 0; }

static void rail_close(unsigned i, power_window_t *out)
{
  const rail_t *r = &pa.rail[i];
  const rail_win *w = &r->win;
  int whole = !w->gap && w->covered_ms + RAIL_PERIOD_MS >= out->window_ms;
  out->slot[POWER_RAILS[i].current_slot] = (power_slot_t){
    .value = w->covered_ms ? (int32_t)ws_div_round(w->dq_uas, (int64_t)w->covered_ms) : 0,   /* uA s / ms = mA */
    .count = w->steps, .quality = quality(w->steps, whole, r->fault) };
  if (POWER_RAILS[i].vbus_slot != PS_NONE)
    out->slot[POWER_RAILS[i].vbus_slot] = (power_slot_t){ .value = mean(w->vbus_mv, w->vbus_n), .count = w->vbus_n,
      .quality = quality(w->vbus_n, !w->gap && filled(w->vbus_n, RAIL_PERIOD_MS, out->window_ms), r->fault) };
}

/* The counters since init (mWh, mAh); the energy slots are missing in a window where a step had no
   fresh cell voltage. */
static void battery_close(power_window_t *out)
{
  const rail_t *r = &pa.rail[POWER_RAIL_BATTERY];
  uint8_t q = quality(r->win.steps, !r->win.gap, r->fault);
  uint8_t qe = pa.energy_missing ? (uint8_t)WSMP_QUAL_MISSING : q;
  const int64_t totals[4] = { pa.energy_in / NWS_PER_MWH, pa.energy_out / NWS_PER_MWH,
                              pa.charge_in / UAS_PER_MAH, pa.charge_out / UAS_PER_MAH };
  for (unsigned k = 0; k < 4U; k++)
    out->slot[PS_ENERGY_IN + k] = (power_slot_t){ .value = (int32_t)totals[k], .count = r->win.steps,
                                                  .quality = k < 2U ? qe : q };
  const gauge_t *g = &pa.gauge;
  out->slot[PS_BATT_MV] = (power_slot_t){ .value = mean(g->sum_mv, g->n), .count = g->n,
                                          .quality = quality(g->n, filled(g->n, GAUGE_PERIOD_MS, out->window_ms), g->fault) };
}

static void adc_close(power_window_t *out)
{
  const adc_win *a = &pa.adc;
  uint8_t q = a->vin_clipped ? (uint8_t)WSMP_QUAL_MISSING : quality(a->vin_n, filled(a->vin_n, ADC_PERIOD_MS, out->window_ms), 0);
  out->slot[PS_CHARGER_IN_MV] = (power_slot_t){ .value = mean(a->vin_mv, a->vin_n), .count = a->vin_n, .quality = q };
  out->slow.vdda_mv = a->vdda_n ? (uint16_t)mean(a->vdda_mv, a->vdda_n) : (uint16_t)POWER_NONE_U16;
  out->slow.chg_batt_ma = (a->iset_bad || !a->iset_n) ? (int16_t)POWER_NONE_I16 : sat16(mean(a->iset_ma, a->iset_n));
}

static void slow_close(power_slow_t *s)
{
  const gauge_t *g = &pa.gauge;
  s->soc_256 = g->ok ? g->soc_256 : (uint16_t)POWER_NONE_U16;
  s->soc_rate = g->ok ? g->rate : (int16_t)POWER_NONE_I16;
  s->charger_status = charger_status();
  int have = 0;
  int32_t hottest = 0;
  for (unsigned i = 0; i < POWER_RAIL_COUNT; i++)
  {
    const rail_t *r = &pa.rail[i];
    if (r->temp_ok && (!have || r->die_mc > hottest)) { hottest = r->die_mc; have = 1; }
  }
  s->monitor_temp = have ? sat16(ws_div_round(hottest, MC_PER_DECI_C)) : (int16_t)POWER_NONE_I16;
}

void power_acq_latch(uint32_t now_ms, power_window_t *out)
{
  memset(out, 0, sizeof *out);
  pa.now = now_ms;
  out->window_ms = now_ms - pa.start_ms;
  out->first = !pa.latched;
  for (unsigned s = 0; s < PS_COUNT; s++) out->slot[s].quality = WSMP_QUAL_NOT_FITTED;
  for (unsigned i = 0; i < POWER_RAIL_COUNT; i++) rail_close(i, out);
  battery_close(out);
  adc_close(out);
  slow_close(&out->slow);
  for (unsigned i = 0; i < POWER_RAIL_COUNT; i++) memset(&pa.rail[i].win, 0, sizeof pa.rail[i].win);
  pa.gauge.sum_mv = 0;
  pa.gauge.n = 0;
  pa.adc = (adc_win){ .next_ms = pa.adc.next_ms, .seq = pa.adc.seq };
  pa.energy_missing = 0;
  pa.start_ms = now_ms;
  pa.latched = 1;
}
