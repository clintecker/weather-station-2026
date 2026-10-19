/* The battery and charger module (mod_power.h).
 *   INA228 at 0x40 (datasheet section 7.6): MANUFACTURER_ID 0x3E = 0x5449, DEVICE_ID 0x3F >> 4 =
 *   0x228. SHUNT_CAL 0x02 = 13107.2e6 x CURRENT_LSB x R_shunt with CURRENT_LSB = 10 uA. VBUS 0x05 and
 *   CURRENT 0x07 are 24-bit registers whose top 20 bits hold the value: VBUS 195.3125 uV a count,
 *   CURRENT signed, CURRENT_LSB a count.
 *   MAX17048 at 0x36: VERSION 0x08 & 0xFFF0 = 0x0010, SOC 0x04 high byte in whole %.
 * Charge and energy integrate in 64-bit uA ms and uW ms, so the counters (whole mAh and mWh) lose
 * nothing to rounding. A sample's current counts over the time since the previous good sample; the
 * first sample after a failure counts over no time. */
#define WS_CHECK_FILE 16
#include "mod_power.h"
#include <string.h>
#include "i2c_bus.h"
#include "mod_mean.h"
#include "ws_check.h"
#include "wsmp_local.h"

#define INA228_ADDR 0x40U
#define MAX17048_ADDR 0x36U
#define INA228_MANUFACTURER 0x5449U
#define INA228_DEVICE 0x228U
#define INA228_SHUNT_MOHM 15U          /* Adafruit 5832; measure the shunt on the bench */
#define INA228_CURRENT_LSB_UA 10
/* 13107.2e6 x 10e-6 A x 0.015 ohm = 1966.08 */
#define INA228_SHUNT_CAL ((uint16_t)(131072ULL * INA228_CURRENT_LSB_UA * INA228_SHUNT_MOHM / 10000ULL))
#define REG_MANUFACTURER 0x3EU
#define REG_DEVICE 0x3FU
#define REG_SHUNT_CAL 0x02U
#define REG_VBUS 0x05U
#define REG_CURRENT 0x07U
#define REG_VERSION 0x08U
#define REG_SOC 0x04U
#define MAX17048_VERSION_MASK 0xFFF0U
#define MAX17048_VERSION 0x0010U
#define POWER_PERIOD_MS 1000U
#define GAUGE_EVERY 15U                /* the gauge is read once in this many samples */
#define VBUS_UV_NUM 3125               /* 195.3125 uV = 3125 / 16 uV */
#define VBUS_UV_DEN 16
#define VALUE_SHIFT 4U                 /* the 20-bit value sits in bits 23-4 */
#define UA_MS_PER_MAH 3600000000LL     /* 1 mA for 1 h */
#define UW_MS_PER_MWH 3600000000LL
#define UV_UA_PER_UW 1000000LL
#define CHANNELS 7U
#define SOC_MAX_PCT 100U              /* the registry range of the state of charge */

typedef enum { ST_IDLE, ST_MANUFACTURER, ST_DEVICE, ST_CAL, ST_VBUS, ST_CURRENT, ST_VERSION, ST_SOC } power_step;
typedef struct {
  power_step step;
  uint32_t next_ms, sample_ms, last_ms;
  int have_last, cal_needed, gauge_ok, probe;
  unsigned samples_since_gauge;
  uint16_t probe_seq;
  uint8_t buf[3], cal[3];
  int64_t uv, charge_in, charge_out, energy_in, energy_out;   /* uV, then uA ms and uW ms */
  uint8_t soc;
  mean_win win;   /* the voltage mean, in mV */
} power_t;

static power_t pw;
static uint32_t boot;
static const uint8_t reg_manufacturer = REG_MANUFACTURER, reg_device = REG_DEVICE, reg_vbus = REG_VBUS,
                     reg_current = REG_CURRENT, reg_version = REG_VERSION, reg_soc = REG_SOC;

static void submit(enum i2c_client c, const uint8_t *tx, uint8_t txlen, uint8_t *rx, uint8_t rxlen)
{
  /* The bus refuses only a busy client or a bad form; one step at a time makes neither. */
  (void)WS_CHECK(i2c_bus_submit(c, c == I2C_C_INA228 ? INA228_ADDR : MAX17048_ADDR, tx, txlen, rx, rxlen) == 0);
}

static void step(power_step next, enum i2c_client c, const uint8_t *reg, uint8_t len)
{
  pw.step = next;
  submit(c, reg, 1, pw.buf, len);
}

void mod_power_init(uint32_t boot_id, uint32_t now_ms)
{
  boot = boot_id;
  memset(&pw, 0, sizeof pw);
  mean_reset(&pw.win, now_ms);
  pw.cal_needed = 1;
  pw.win.period_ms = POWER_PERIOD_MS;
}

void mod_power_tick(uint32_t now_ms)
{
  if (pw.step != ST_IDLE || (int32_t)(now_ms - pw.next_ms) < 0) return;
  pw.next_ms += POWER_PERIOD_MS;
  if ((int32_t)(now_ms - pw.next_ms) >= 0) pw.next_ms = now_ms + POWER_PERIOD_MS;   /* fell behind: resync */
  pw.sample_ms = now_ms;
  step(ST_MANUFACTURER, I2C_C_INA228, &reg_manufacturer, 2);
}

static uint16_t be16(const uint8_t *p) { return (uint16_t)(p[0] << 8 | p[1]); }
static uint32_t be24(const uint8_t *p) { return (uint32_t)p[0] << 16 | (uint32_t)p[1] << 8 | p[2]; }

static void monitor_failed(int rc)
{
  pw.probe = rc == I2C_ENACK_ADDR ? 0 : -1;
  pw.probe_seq++;
  pw.cal_needed = 1;
  pw.have_last = 0;
  pw.step = ST_IDLE;
}

/* The INA228 is this module: anything else at its address is "absent". */
static void identified(void)
{
  if (pw.step == ST_MANUFACTURER)
  {
    if (be16(pw.buf) != INA228_MANUFACTURER) { monitor_failed(I2C_ENACK_ADDR); return; }
    step(ST_DEVICE, I2C_C_INA228, &reg_device, 2);
    return;
  }
  if ((be16(pw.buf) >> VALUE_SHIFT) != INA228_DEVICE) { monitor_failed(I2C_ENACK_ADDR); return; }
  if (!pw.cal_needed) { step(ST_VBUS, I2C_C_INA228, &reg_vbus, 3); return; }
  pw.cal[0] = REG_SHUNT_CAL; pw.cal[1] = (uint8_t)(INA228_SHUNT_CAL >> 8); pw.cal[2] = (uint8_t)INA228_SHUNT_CAL;
  pw.step = ST_CAL;
  submit(I2C_C_INA228, pw.cal, sizeof pw.cal, NULL, 0);
}

static void integrate(int64_t ua)
{
  int64_t dt = pw.have_last ? (int64_t)(pw.sample_ms - pw.last_ms) : 0;
  int64_t uw = pw.uv * ua / UV_UA_PER_UW;
  if (ua >= 0) { pw.charge_in += ua * dt; pw.energy_in += uw * dt; }
  else { pw.charge_out -= ua * dt; pw.energy_out -= uw * dt; }
  pw.last_ms = pw.sample_ms;
  pw.have_last = 1;
}

static void measured(void)
{
  if (pw.step == ST_VBUS)
  {
    pw.uv = (int64_t)(be24(pw.buf) >> VALUE_SHIFT) * VBUS_UV_NUM / VBUS_UV_DEN;
    step(ST_CURRENT, I2C_C_INA228, &reg_current, 3);
    return;
  }
  int32_t raw = (int32_t)(be24(pw.buf) << 8) >> (8 + VALUE_SHIFT);   /* sign-extend the 24-bit register */
  integrate((int64_t)raw * INA228_CURRENT_LSB_UA);
  mean_add(&pw.win, (const int32_t[MEAN_CHANNELS]){ (int32_t)(pw.uv / 1000), 0 });
  pw.probe = 1;
  pw.probe_seq++;
  if (++pw.samples_since_gauge < GAUGE_EVERY && pw.gauge_ok) { pw.step = ST_IDLE; return; }
  pw.samples_since_gauge = 0;
  step(ST_VERSION, I2C_C_MAX17048, &reg_version, 2);
}

static void gauge_done(int rc)
{
  if (rc) { pw.gauge_ok = 0; pw.step = ST_IDLE; return; }
  if (pw.step == ST_VERSION)
  {
    if ((be16(pw.buf) & MAX17048_VERSION_MASK) != MAX17048_VERSION) { pw.gauge_ok = 0; pw.step = ST_IDLE; return; }
    step(ST_SOC, I2C_C_MAX17048, &reg_soc, 2);
    return;
  }
  pw.soc = pw.buf[0] > SOC_MAX_PCT ? SOC_MAX_PCT : pw.buf[0];   /* ModelGauge reads 101 % and more near full */
  pw.gauge_ok = 1;
  pw.step = ST_IDLE;
}

void mod_power_i2c_done(int rc)
{
  if (pw.step == ST_VERSION || pw.step == ST_SOC) { gauge_done(rc); return; }
  if (rc) { monitor_failed(rc); return; }
  if (pw.step == ST_MANUFACTURER || pw.step == ST_DEVICE) identified();
  else if (pw.step == ST_CAL) { pw.cal_needed = 0; step(ST_VBUS, I2C_C_INA228, &reg_vbus, 3); }
  else if (WS_CHECK(pw.step == ST_VBUS || pw.step == ST_CURRENT)) measured();
}

int mod_power_probe(uint16_t *seq)
{
  *seq = pw.probe_seq;
  return pw.probe;
}

static void descriptors(wsmp_desc d[CHANNELS])
{
  static const uint16_t counter_q[4] = { WSMP_Q_ENERGY_IN, WSMP_Q_ENERGY_OUT, WSMP_Q_CHARGE_IN, WSMP_Q_CHARGE_OUT };
  d[0] = (wsmp_desc){ .quantity = WSMP_Q_BATTERY_VOLTAGE, .unit = WSMP_U_VOLT, .scale = -3, .width = 2, .kind = WSMP_K_MEAN };
  for (unsigned i = 0; i < 4; i++)
    d[1 + i] = (wsmp_desc){ .quantity = counter_q[i], .unit = i < 2 ? WSMP_U_WATT_HOUR : WSMP_U_AMPERE_HOUR, .scale = -3,
                            .width = 3, .kind = WSMP_K_COUNTER };
  d[5] = (wsmp_desc){ .quantity = WSMP_Q_STATE_OF_CHARGE, .unit = WSMP_U_PERCENT, .scale = 0, .width = 1, .kind = WSMP_K_POINT };
  d[6] = (wsmp_desc){ .quantity = WSMP_Q_CHARGER_STATE, .unit = WSMP_U_STATE, .scale = 0, .width = 1, .kind = WSMP_K_STATE };
}

void mod_power_identity(uint8_t id[WSMP_IDENTITY_LEN], uint8_t desc[WSMP_DESC_BLOCK_LEN])
{
  wsmp_desc d[CHANNELS];
  descriptors(d);
  wsmp_pack_desc(d, CHANNELS, desc);
  wsmp_identity ident = { .type = WSMP_T_POWER, .schema = 1, .channels = CHANNELS, .fw_major = 1, .fw_minor = 0,
                          .serial = WSMP_LOCAL_SERIAL(P_POWER, WSMP_T_POWER), .boot_id = boot,
                          .desc_digest = wsmp_crc32c(desc, WSMP_DESC_BLOCK_LEN) };
  wsmp_pack_identity(&ident, id);
}

/* The bq24074 state (registry, module type 5): off without input power, charging while CHG is
   asserted, done after it. A fault is not readable from the two pins. */
static uint32_t charger_state(void)
{
  unsigned pins = (unsigned)board_charger_pins();
  if (!(pins & POWER_PGOOD)) return WSMP_POWER_STATE_OFF;
  return (pins & POWER_CHG) ? WSMP_POWER_STATE_CHARGING : WSMP_POWER_STATE_DONE;
}

void mod_power_latch(uint16_t token, uint32_t now_ms)
{
  uint8_t id[WSMP_IDENTITY_LEN], desc[WSMP_DESC_BLOCK_LEN];
  wsmp_snapshot snap;
  unsigned samples = pw.win.n;
  mod_power_identity(id, desc);
  if (!mean_close(&pw.win, token, now_ms, boot, desc, 1, &snap)) return;
  const int64_t totals[4] = { pw.energy_in / UW_MS_PER_MWH, pw.energy_out / UW_MS_PER_MWH,
                              pw.charge_in / UA_MS_PER_MAH, pw.charge_out / UA_MS_PER_MAH };
  uint8_t q = mean_quality(&snap, samples);
  for (unsigned i = 0; i < 4; i++) snap.slot[1 + i] = (wsmp_slot){ .value = (uint32_t)totals[i], .count = (uint16_t)samples, .quality = q };
  snap.slot[5] = (wsmp_slot){ .value = pw.soc, .count = (uint16_t)pw.gauge_ok, .quality = mean_quality(&snap, (unsigned)pw.gauge_ok) };
  snap.slot[6] = (wsmp_slot){ .value = charger_state(), .count = 1, .quality = mean_quality(&snap, 1) };
  mean_store(&pw.win, &snap);
}

void mod_power_snapshot(uint8_t snap[WSMP_SNAPSHOT_LEN]) { memcpy(snap, pw.win.frozen, WSMP_SNAPSHOT_LEN); }
