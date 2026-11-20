/* The battery and rails modules and the health accessor (mod_power.h): the WSMP face of
 * App/power_acq.c, which owns every part, bus transfer and conversion. This file only turns a closed
 * power_acq window into the two modules' snapshots and caches the slow values (spec section 9.6).
 *   Slot values: means in mV and mA (scale -3 of V and A), counters in mWh and mAh; a signed value is
 *   stored as its two's complement in the 32-bit slot, as every WSMP slot is.
 *   Qualities come from power_acq unchanged (good, partial, missing, fault, not fitted), except that a
 *   module's own first window is never better than partial. */
#define WS_CHECK_FILE 16
#include "mod_power.h"
#include <string.h>
#include "mod_mean.h"
#include "power_acq.h"
#include "ws_check.h"
#include "wsmp_local.h"
#include "ws_frame.h"

#define PROBE_PERIOD_MS 1000U   /* the probe sequence moves once a second */
#define MODULES 2U

typedef struct {
  mean_win win;   /* the header, the retry rule and the frozen snapshot; no mean channels */
} module_t;

typedef struct {
  module_t mod[MODULES];
  power_window_t acq;      /* the last closed power_acq window */
  uint16_t acq_token;      /* the latch token that closed it */
  uint8_t acq_closed;      /* 1 once a window was closed */
  uint16_t probe_seq;
  uint32_t probe_next_ms;
  uint32_t boot;
  power_health_t health;
} power_t;

static power_t pw;

/* The slots of each module, in channel order (registry types 8 and 9). */
static const uint8_t battery_slots[POWER_BATTERY_CHANNELS] = { PS_BATT_MV, PS_BATT_MA, PS_ENERGY_IN, PS_ENERGY_OUT,
                                                                PS_CHARGE_IN, PS_CHARGE_OUT };
static const uint8_t rails_slots[POWER_RAILS_CHANNELS] = { PS_LOAD_MV, PS_LOAD_MA, PS_CHARGER_IN_MV, PS_SOLAR_MV,
                                                            PS_SOLAR_MA, PS_USB_MV, PS_USB_MA };

/* The health slots profiles A and B have a source for (spec sections 3.3 and 6.1): VREFINT, the
   INA228 die, the gauge, the CHG and PGOOD pins and ISET (phase C: the BQ25798's status and IBAT). */
#define HEALTH_FITTED_AB (WS_FIT_MCU_SUPPLY | WS_FIT_MONITOR_TEMP | WS_FIT_GAUGE | WS_FIT_CHARGER_STATUS | WS_FIT_CHARGE_CURRENT)
/* Phase C adds the BQ25798's registers (stage, active input, VBUS, IBUS, VBAT, die). The pack temperature
   stays unfitted: TS is a % of REGN, and the B 3950 NTC on the EVM's 103AT divider has no fitted curve. */
#define HEALTH_FITTED (HEALTH_FITTED_AB | (POWER_HAS_BQ25798 ? WS_FIT_CHARGER_REGS : 0U))

static void health_none(power_health_t *h)
{
  *h = (power_health_t){ .vdda_mv = POWER_NONE_U16, .soc = POWER_NONE_U16, .chg_input_mv = POWER_NONE_U16,
                         .chg_batt_mv = POWER_NONE_U16, .monitor_temp = POWER_NONE_I16, .soc_rate = POWER_NONE_I16,
                         .chg_input_ma = POWER_NONE_I16, .chg_batt_ma = POWER_NONE_I16, .chg_temp = POWER_NONE_I16,
                         .pack_temp = POWER_NONE_I16, .charger_status = POWER_NONE_U8, .fitted = HEALTH_FITTED };
}

void mod_power_init(uint32_t boot_id, uint32_t now_ms)
{
  memset(&pw, 0, sizeof pw);
  pw.boot = boot_id;
  pw.probe_next_ms = now_ms;
  for (unsigned m = 0; m < MODULES; m++) mean_reset(&pw.mod[m].win, now_ms);
  health_none(&pw.health);
  power_acq_init(now_ms);
}

void mod_power_tick(uint32_t now_ms)
{
  power_acq_tick(now_ms);
  if (mean_due(&pw.probe_next_ms, now_ms, PROBE_PERIOD_MS)) pw.probe_seq++;
}

/* Base-board modules: present whatever their parts answer (spec section 8.5). */
int mod_power_probe(uint16_t *seq)
{
  *seq = pw.probe_seq;
  return 1;
}

static void battery_descriptors(wsmp_desc d[POWER_BATTERY_CHANNELS])
{
  static const uint16_t counter_q[4] = { WSMP_Q_ENERGY_IN, WSMP_Q_ENERGY_OUT, WSMP_Q_CHARGE_IN, WSMP_Q_CHARGE_OUT };
  d[0] = (wsmp_desc){ .quantity = WSMP_Q_BATTERY_VOLTAGE, .unit = WSMP_U_VOLT, .scale = -3, .width = 2, .kind = WSMP_K_MEAN };
  d[1] = (wsmp_desc){ .quantity = WSMP_Q_BATTERY_CURRENT, .unit = WSMP_U_AMPERE, .scale = -3, .width = 2, .is_signed = 1,
                      .kind = WSMP_K_MEAN };
  for (unsigned i = 0; i < 4U; i++)
    d[2U + i] = (wsmp_desc){ .quantity = counter_q[i], .unit = i < 2U ? WSMP_U_WATT_HOUR : WSMP_U_AMPERE_HOUR, .scale = -3,
                             .width = 3, .kind = WSMP_K_COUNTER };
}

/* Voltages unsigned, currents signed (spec section 8.1). */
static void rails_descriptors(wsmp_desc d[POWER_RAILS_CHANNELS])
{
  static const uint16_t q[POWER_RAILS_CHANNELS] = { WSMP_Q_LOAD_VOLTAGE, WSMP_Q_LOAD_CURRENT, WSMP_Q_CHARGER_INPUT_VOLTAGE,
                                                    WSMP_Q_SOLAR_VOLTAGE, WSMP_Q_SOLAR_CURRENT, WSMP_Q_USB_VOLTAGE,
                                                    WSMP_Q_USB_CURRENT };
  static const uint8_t is_current[POWER_RAILS_CHANNELS] = { 0, 1, 0, 0, 1, 0, 1 };
  for (unsigned i = 0; i < POWER_RAILS_CHANNELS; i++)
    d[i] = (wsmp_desc){ .quantity = q[i], .unit = is_current[i] ? WSMP_U_AMPERE : WSMP_U_VOLT, .scale = -3, .width = 2,
                        .is_signed = is_current[i], .kind = WSMP_K_MEAN };
}

static unsigned channels_of(enum power_module m) { return m == PM_BATTERY ? POWER_BATTERY_CHANNELS : POWER_RAILS_CHANNELS; }

static void desc_block(enum power_module m, uint8_t desc[WSMP_DESC_BLOCK_LEN])
{
  wsmp_desc d[WSMP_MAX_CHANNELS];
  if (m == PM_BATTERY) battery_descriptors(d);
  else rails_descriptors(d);
  wsmp_pack_desc(d, channels_of(m), desc);
}

/* Every caller passes a PM_* constant; a bad value is a bug, and each caller recovers on the spot. */
static int known(enum power_module m) { return WS_CHECK(m == PM_BATTERY || m == PM_RAILS); }

void mod_power_identity(enum power_module m, uint8_t id[WSMP_IDENTITY_LEN], uint8_t desc[WSMP_DESC_BLOCK_LEN])
{
  if (!known(m))   /* recovery: an all-zero identity and block, which name no module type */
  {
    memset(id, 0, WSMP_IDENTITY_LEN);
    memset(desc, 0, WSMP_DESC_BLOCK_LEN);
    return;
  }
  desc_block(m, desc);
  if (m == PM_BATTERY) local_pack_identity(P_BATTERY, WSMP_T_BATTERY, POWER_BATTERY_CHANNELS, pw.boot, desc, id);
  else local_pack_identity(P_RAILS, WSMP_T_POWER_RAILS, POWER_RAILS_CHANNELS, pw.boot, desc, id);
}

/* The slow values of a closed window, with their none codes; the charger-reported input, battery
   voltage and die temperature have a source in phase C only, the pack temperature in none. */
static void health_cache(const power_slow_t *s)
{
  health_none(&pw.health);
  pw.health.vdda_mv = s->vdda_mv;
  pw.health.soc = s->soc_256;
  pw.health.soc_rate = s->soc_rate;
  pw.health.monitor_temp = s->monitor_temp;
  pw.health.chg_batt_ma = s->chg_batt_ma;
  pw.health.charger_status = s->charger_status;
  pw.health.chg_input_mv = s->chg_input_mv;
  pw.health.chg_input_ma = s->chg_input_ma;
  pw.health.chg_batt_mv = s->chg_batt_mv;
  pw.health.chg_temp = s->chg_temp;
}

/* power_acq's window for this token: closed by the first module to latch with it, then shared. */
static const power_window_t *window_for(uint16_t token, uint32_t now_ms)
{
  if (!pw.acq_closed || token != pw.acq_token)
  {
    power_acq_latch(now_ms, &pw.acq);
    pw.acq_token = token;
    pw.acq_closed = 1;
    health_cache(&pw.acq.slow);
  }
  return &pw.acq;
}

void mod_power_latch(enum power_module m, uint16_t token, uint32_t now_ms)
{
  uint8_t desc[WSMP_DESC_BLOCK_LEN];
  wsmp_snapshot snap;
  if (!known(m)) return;   /* recovery: no window is latched */
  mean_win *w = &pw.mod[m == PM_BATTERY ? 0 : 1].win;
  const uint8_t *slots = m == PM_BATTERY ? battery_slots : rails_slots;
  desc_block(m, desc);
  if (!mean_close(w, token, now_ms, pw.boot, desc, 0, &snap)) return;   /* WSMP-L3: a retry */
  const power_window_t *acq = window_for(token, now_ms);
  int first = (snap.flags & WSMP_FLAG_FIRST_WINDOW) != 0;
  for (unsigned i = 0; i < channels_of(m); i++)
  {
    const power_slot_t *s = &acq->slot[slots[i]];
    uint8_t q = first && s->quality == WSMP_QUAL_GOOD ? (uint8_t)WSMP_QUAL_PARTIAL : s->quality;
    snap.slot[i] = (wsmp_slot){ .value = (uint32_t)s->value, .count = s->count, .quality = q };
  }
  mean_store(w, &snap);
}

void mod_power_snapshot(enum power_module m, uint8_t snap[WSMP_SNAPSHOT_LEN])
{
  if (!known(m)) { memset(snap, 0, WSMP_SNAPSHOT_LEN); return; }   /* recovery: the before-any-window state */
  memcpy(snap, pw.mod[m == PM_BATTERY ? 0 : 1].win.frozen, WSMP_SNAPSHOT_LEN);
}

void mod_power_health(power_health_t *out) { *out = pw.health; }
