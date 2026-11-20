/* The BQ25798 charger (charger.h): set-up, charge gate, readings. Register facts from TI SLUSDV2C (rev.
 * June 2026), section 7.5.1, cited by table beside each; the I2C rules from section 7.3.14 (address 0x6B;
 * multi-byte reads and writes cross register boundaries, high byte of a 16-bit register first).
 *
 * The charge gate (EN_CHG, REG0F bit 5, table 7-25). Charge stays off until the part is a BQ25798, CELL
 * says one cell, VREG and ICHG read back as set, and a TS reading no older than CHARGER_TS_FRESH_MS
 * exists with the TS comparators not COLD or HOT (REG1F, table 7-40). COLD and HOT also catch an open or
 * shorted thermistor (TS near 100 % or 0 % of REGN). COOL and WARM still charge: the chip's own JEITA
 * profile lowers the current or the voltage there (REG16-REG18). The chip enforces its TS limits on
 * its own too; the gate adds the firmware's view and the report. */
#define WS_CHECK_FILE 19
#include "charger.h"
#include <string.h>
#include "power_config.h"
#include "power_regs.h"
#include "ws_check.h"
#include "ws_frame.h"

/* Registers (SLUSDV2C table 7-13, the register map) and the bursts the poll reads. */
#define REG_VREG 0x01U          /* REG01-02 VREG; the burst runs to REG10 */
#define CONFIG_LEN 16U          /* REG01 to REG10 */
#define OFF_VREG 0U
#define OFF_ICHG 2U             /* REG03-04 */
#define OFF_0A 9U               /* REG0A */
#define OFF_0F 14U              /* REG0F */
#define OFF_10 15U              /* REG10 */
#define LIMITS_LEN 4U           /* VREG and ICHG, written as one burst from REG01 */
#define REG_CTRL0 0x0FU         /* REG0F, then REG10 */
#define REG_STATUS 0x1BU        /* REG1B to REG21 */
#define STATUS_LEN 7U
#define REG_ADC_CTRL 0x2EU      /* REG2E, then REG2F-30 and the results REG31 to REG42 */
#define ADC_LEN 21U
#define OFF_IBUS 3U             /* REG31 */
#define OFF_IBAT 5U             /* REG33 */
#define OFF_VBUS 7U             /* REG35 */
#define OFF_VBAT 13U            /* REG3B */
#define OFF_VSYS 15U            /* REG3D */
#define OFF_TS 17U              /* REG3F */
#define OFF_TDIE 19U            /* REG41 */
#define REG_PART 0x48U

#define EN_CHG 0x20U            /* REG0F bit 5 (table 7-25) */
#define WD_RST 0x08U            /* REG10 bit 3 (table 7-26) */
#define ADC_EN 0x80U            /* REG2E bit 7 (table 7-55) */
#define ADC_START 0xC0U         /* ADC_EN | ADC_RATE (one-shot), ADC_SAMPLE 0 (15-bit, 24 ms a channel) */
/* Status bits, by their offset in st[] (REG1B = 0). */
#define S_1B 0U
#define S_1C 1U
#define S_1E 3U
#define S_1F 4U
#define S_20 5U
#define S_21 6U
#define VBUS_PRESENT 0x01U      /* REG1B bit 0 (table 7-36) */
#define AC1_PRESENT 0x02U       /* REG1B bit 1 */
#define AC2_PRESENT 0x04U       /* REG1B bit 2 */
#define PG_STAT 0x08U           /* REG1B bit 3 */
#define WD_STAT 0x20U           /* REG1B bit 5 */
#define CHG_STAT_SHIFT 5U       /* REG1C bits 7:5 (table 7-37) */
#define ADC_DONE 0x20U          /* REG1E bit 5 (table 7-39) */
#define TS_HOT 0x01U            /* REG1F bits 0-3 (table 7-40) */
#define TS_WARM 0x02U
#define TS_COOL 0x04U
#define TS_COLD 0x08U
#define FAULT0_MASK 0x7FU       /* REG20 bits 6:0, the OVP and OCP faults; bit 7 is IBAT regulation (table 7-41) */
#define FAULT1_MASK 0xF4U       /* REG21 bits 7:4 VSYS short/OVP, OTG OVP/UVP, bit 2 TSHUT (table 7-42) */

/* The EVM's inputs (tx-stack design, Power): VIN1 is the USB micro-B J6 (JP7), VIN2 the solar lead (J2). */
#define VAC1_INPUT WS_CHG_INPUT_USB_C
#define VAC2_INPUT WS_CHG_INPUT_SOLAR

typedef enum { CS_IDLE, CS_ID, CS_CONFIG, CS_LIMITS, CS_VERIFY, CS_STATUS, CS_ADC, CS_CONTROL, CS_ADC_START } chg_step;

typedef struct {
  charger_t s;
  charger_win_t win;
  chg_step step;
  uint8_t held;          /* the set-up read back as set at least once since boot */
  uint8_t adc_started;   /* a one-shot conversion was started since the last reset seen */
  uint32_t now, next_ms;
  uint8_t buf[ADC_LEN], tx[LIMITS_LEN + 1U];
} chg_t;

static chg_t cg;

static uint16_t be16(const uint8_t *p) { return (uint16_t)(p[0] << 8 | p[1]); }

static void submit(chg_step s, uint8_t txlen, uint8_t rxlen)
{
  cg.step = s;
  /* The bus refuses only a busy client or a bad form; one step at a time makes neither. */
  if (!WS_CHECK(i2c_bus_submit(I2C_C_CHARGER, POWER_ADDR_CHARGER, cg.tx, txlen, rxlen ? cg.buf : NULL, rxlen) == 0))
    charger_i2c_done(I2C_EBUS);
}

static void read_regs(chg_step s, uint8_t reg, uint8_t len) { cg.tx[0] = reg; submit(s, 1, len); }

static uint16_t vreg_want(void) { return bq25798_vreg_raw(POWER_CHG_VREG_MV); }
static uint16_t ichg_want(void) { return bq25798_ichg_raw(POWER_CHG_ICHG_MA); }

static uint16_t count_up(uint16_t n) { return n == UINT16_MAX ? n : (uint16_t)(n + 1U); }

/* A NACK or another part is an absent charger (identified again at the next poll); anything else a bus
   fault. The poll ends here; charge stays as the chip has it (its watchdog takes over if we stay away). */
static void failed(int rc)
{
  charger_t *s = &cg.s;
  s->fault = rc != I2C_ENACK_ADDR && rc != I2C_ENACK_DATA && rc != I2C_EID;
  if (s->fault) cg.win.fault = 1;
  else { s->present = 0; s->hold = (uint8_t)(rc == I2C_EID ? CH_PART : CH_ABSENT); }
  s->ok = 0;
  s->failures = count_up(s->failures);
  cg.step = CS_IDLE;
}

static void config_read(void)
{
  charger_t *s = &cg.s;
  s->vreg_raw = be16(cg.buf + OFF_VREG);
  s->ichg_raw = be16(cg.buf + OFF_ICHG);
  s->reg0a = cg.buf[OFF_0A];
  s->reg0f = cg.buf[OFF_0F];
  s->reg10 = cg.buf[OFF_10];
}

static int config_matches(void) { return cg.s.vreg_raw == vreg_want() && cg.s.ichg_raw == ichg_want(); }

/* VREG and ICHG as one 4-byte write from REG01 (high bytes first; the reserved top bits written 0). */
static void write_limits(void)
{
  uint16_t v = vreg_want(), i = ichg_want();
  if (cg.held) cg.s.resets = count_up(cg.s.resets);
  cg.held = 0;
  cg.adc_started = 0;   /* a reset chip's ADC registers are from before it */
  cg.s.applies = count_up(cg.s.applies);
  cg.tx[0] = REG_VREG;
  cg.tx[1] = (uint8_t)(v >> 8); cg.tx[2] = (uint8_t)v;
  cg.tx[3] = (uint8_t)(i >> 8); cg.tx[4] = (uint8_t)i;
  submit(CS_LIMITS, LIMITS_LEN + 1U, 0);
}

/* The first hold that applies (the gate, charger.c head); CH_PART comes from the identify (failed). */
static enum charger_hold hold_now(void)
{
  const charger_t *s = &cg.s;
  if (!s->present) return CH_ABSENT;   /* present: REG48's PN matched (CS_ID) */
  if (bq25798_cells(s->reg0a) != POWER_CHG_CELLS) return CH_CELLS;
  if (!s->configured) return CH_READBACK;
  if (!s->adc_ok || cg.now - s->ts_ms > CHARGER_TS_FRESH_MS) return CH_TS_STALE;
  if (s->st[S_1F] & TS_COLD) return CH_TS_COLD;
  if (s->st[S_1F] & TS_HOT) return CH_TS_HOT;
  return CH_NONE;
}

/* REG0F with EN_CHG by the gate, REG10 with WD_RST; every other bit as read. */
static void write_control(void)
{
  charger_t *s = &cg.s;
  s->hold = (uint8_t)hold_now();
  cg.tx[0] = REG_CTRL0;
  cg.tx[1] = (uint8_t)(s->hold == CH_NONE ? (s->reg0f | EN_CHG) : (s->reg0f & (uint8_t)~EN_CHG));
  cg.tx[2] = (uint8_t)(s->reg10 | WD_RST);
  s->reg0f = cg.tx[1];
  submit(CS_CONTROL, 3, 0);
}

static void adc_read(void)
{
  charger_t *s = &cg.s;
  charger_win_t *w = &cg.win;
  const uint8_t *b = cg.buf;
  s->reg2e = b[0];
  s->ibus = be16(b + OFF_IBUS); s->ibat = be16(b + OFF_IBAT); s->vbus = be16(b + OFF_VBUS);
  s->vbat = be16(b + OFF_VBAT); s->vsys = be16(b + OFF_VSYS); s->ts = be16(b + OFF_TS); s->tdie = be16(b + OFF_TDIE);
  s->ts_ms = cg.now;
  s->adc_ok = 1;
  w->ibat_ma += (int16_t)s->ibat; w->vbus_mv += s->vbus; w->vsys_mv += s->vsys;
  w->n = count_up(w->n);
  w->vbus_last_mv = s->vbus; w->vbat_last_mv = s->vbat;
  w->ibus_last_ma = (int16_t)s->ibus; w->tdie_last_dc = bq25798_tdie_dc(s->tdie);
}

/* After the status burst: the ADC when the last one-shot conversion has finished (ADC_DONE set, so the
   values are this conversion's), else straight to the control write. */
static void status_read(void)
{
  memcpy(cg.s.st, cg.buf, STATUS_LEN);
  if (cg.adc_started && (cg.s.st[S_1E] & ADC_DONE)) read_regs(CS_ADC, REG_ADC_CTRL, ADC_LEN);
  else write_control();
}

void charger_i2c_done(int rc)
{
  charger_t *s = &cg.s;
  if (rc) { failed(rc); return; }
  switch (cg.step)
  {
    case CS_ID:
      s->reg48 = cg.buf[0];
      if (!bq25798_pn_match(s->reg48)) { failed(I2C_EID); break; }
      s->present = 1;
      read_regs(CS_CONFIG, REG_VREG, CONFIG_LEN);
      break;
    case CS_CONFIG:
      config_read();
      if (config_matches()) { s->configured = 1; cg.held = 1; read_regs(CS_STATUS, REG_STATUS, STATUS_LEN); }
      else { s->configured = 0; write_limits(); }
      break;
    case CS_LIMITS: read_regs(CS_VERIFY, REG_VREG, CONFIG_LEN); break;
    case CS_VERIFY:
      config_read();
      s->configured = (uint8_t)config_matches();
      cg.held = s->configured;
      read_regs(CS_STATUS, REG_STATUS, STATUS_LEN);
      break;
    case CS_STATUS: status_read(); break;
    case CS_ADC:
      /* ADC_EN still set: a conversion is running after all (a second host?): skip this one. */
      if (!(cg.buf[0] & ADC_EN)) adc_read();
      write_control();
      break;
    case CS_CONTROL:
      cg.tx[0] = REG_ADC_CTRL; cg.tx[1] = ADC_START;
      submit(CS_ADC_START, 2, 0);
      break;
    case CS_ADC_START:
      cg.adc_started = 1;
      s->ok = 1; s->fault = 0; s->poll_ms = cg.now;
      cg.step = CS_IDLE;
      break;
    default: (void)WS_CHECK(0); cg.step = CS_IDLE; break;   /* no transfer was out: a bug */
  }
}

void charger_init(uint32_t now_ms)
{
  memset(&cg, 0, sizeof cg);
  cg.now = cg.next_ms = now_ms;
  cg.s.hold = CH_ABSENT;
}

void charger_tick(uint32_t now_ms)
{
  cg.now = now_ms;
  if (cg.step != CS_IDLE || (int32_t)(now_ms - cg.next_ms) < 0) return;
  cg.next_ms = now_ms + CHARGER_PERIOD_MS;
  if (!cg.s.present) read_regs(CS_ID, REG_PART, 1);
  else read_regs(CS_CONFIG, REG_VREG, CONFIG_LEN);
}

const charger_t *charger_state(void) { return &cg.s; }

static uint8_t stage_of(unsigned chg_stat)
{
  static const uint8_t stage[8] = { WS_CHG_STAGE_NOT_CHARGING, WS_CHG_STAGE_PRECHARGE, WS_CHG_STAGE_PRECHARGE,
                                    WS_CHG_STAGE_CC, WS_CHG_STAGE_CV, WS_CHG_STAGE_NONE /* 5: reserved */,
                                    WS_CHG_STAGE_TOPOFF, WS_CHG_STAGE_TERMINATED };
  return stage[chg_stat & 7U];
}

static uint8_t input_of(uint8_t st1b)
{
  unsigned ac = st1b & (AC1_PRESENT | AC2_PRESENT);
  if (!(st1b & VBUS_PRESENT) && !ac) return WS_CHG_INPUT_NO_INPUT;
  if (ac == AC1_PRESENT) return VAC1_INPUT;
  if (ac == AC2_PRESENT) return VAC2_INPUT;
  return WS_CHG_INPUT_NOT_REPORTED;   /* both present: the register map does not say which one powers it */
}

uint8_t charger_status_byte(void)
{
  const charger_t *s = &cg.s;
  if (!s->ok) return WS_CHARGER_NONE;
  unsigned chg = s->st[S_1C] >> CHG_STAT_SHIFT;
  uint8_t st = (s->st[S_1B] & PG_STAT) ? WS_CHG_POWER_GOOD : 0U;
  if ((chg >= 1U && chg <= 4U) || chg == 6U) st |= WS_CHG_CHARGING;
  if ((s->st[S_20] & FAULT0_MASK) || (s->st[S_21] & FAULT1_MASK) || s->hold == CH_PART || s->hold == CH_CELLS ||
      s->hold == CH_READBACK)
    st |= WS_CHG_FAULT;
  return (uint8_t)(st | WS_CHG_STAGE(stage_of(chg)) | WS_CHG_INPUT(input_of(s->st[S_1B])));
}

void charger_close(charger_win_t *w)
{
  *w = cg.win;
  cg.win = (charger_win_t){ 0 };
}

/* ---- the console line ---- */

static unsigned put(char *buf, unsigned len, unsigned n, const char *t)
{
  for (; *t && n + 1U < len; t++) buf[n++] = *t;   /* bound: len - 1 characters */
  buf[n] = 0;
  return n;
}

static unsigned put_dec(char *buf, unsigned len, unsigned n, int32_t v)
{
  char t[12];   /* "-2147483648" and the terminator */
  unsigned i = sizeof t - 1U;
  uint32_t u = v < 0 ? 0U - (uint32_t)v : (uint32_t)v;
  t[i] = 0;
  do { t[--i] = (char)('0' + u % 10U); u /= 10U; } while (u && i > 1U);   /* bound: 10 digits */
  if (v < 0) t[--i] = '-';
  return put(buf, len, n, t + i);
}

static unsigned put_hex(char *buf, unsigned len, unsigned n, uint32_t v, unsigned digits)
{
  char t[11] = "0x";
  for (unsigned i = 0; i < digits && i < 8U; i++) t[2U + i] = "0123456789abcdef"[(v >> (4U * (digits - 1U - i))) & 0x0FU];
  t[2U + (digits < 8U ? digits : 8U)] = 0;
  return put(buf, len, n, t);
}

/* " key=" then a decimal. */
static unsigned kv(char *buf, unsigned len, unsigned n, const char *key, int32_t v)
{
  return put_dec(buf, len, put(buf, len, n, key), v);
}

static const char *ts_band(uint8_t st1f)
{
  if (st1f & TS_COLD) return "COLD";
  if (st1f & TS_HOT) return "HOT";
  if (st1f & TS_COOL) return "COOL";
  if (st1f & TS_WARM) return "WARM";
  return "NORMAL";
}

unsigned charger_line(char *buf, unsigned len, uint32_t now_ms)
{
  static const char *const hold[CH_COUNT] = { "none", "absent", "not-bq25798", "cells", "readback", "ts-stale",
                                              "ts-cold", "ts-hot" };
  static const char *const stage[8] = { "none", "precharge", "cc", "cv", "topoff", "terminated", "not-charging", "?" };
  const charger_t *s = &cg.s;
  if (len == 0) return 0;
  unsigned n = put(buf, len, 0, "#charger");
  if (!POWER_HAS_BQ25798) return put(buf, len, n, " not-fitted (WS_POWER_PROFILE 3 only)");
  n = kv(buf, len, n, " present=", s->present);
  n = kv(buf, len, n, " ok=", s->ok);
  n = put_hex(buf, len, put(buf, len, n, " reg48="), s->reg48, 2);
  n = put_hex(buf, len, put(buf, len, n, " reg0a="), s->reg0a, 2);
  n = kv(buf, len, n, " cells=", (int32_t)bq25798_cells(s->reg0a));
  n = put_hex(buf, len, put(buf, len, n, " reg01_02="), s->vreg_raw, 4);
  n = kv(buf, len, n, " vreg_mv=", bq25798_vreg_mv(s->vreg_raw));
  n = put_hex(buf, len, put(buf, len, n, " reg03_04="), s->ichg_raw, 4);
  n = kv(buf, len, n, " ichg_ma=", bq25798_ichg_ma(s->ichg_raw));
  n = put(buf, len, n, " ts_pct=");
  if (s->adc_ok)
  {
    uint16_t pm = bq25798_ts_permille(s->ts);
    n = put_dec(buf, len, n, pm / 10U);
    n = put_dec(buf, len, put(buf, len, n, "."), pm % 10U);
  }
  else n = put(buf, len, n, "none");
  n = put(buf, len, put(buf, len, n, " ts="), ts_band(s->st[S_1F]));
  n = kv(buf, len, n, " ts_age_ms=", s->adc_ok ? (int32_t)(now_ms - s->ts_ms) : -1);
  unsigned chg = s->st[S_1C] >> CHG_STAT_SHIFT;
  n = kv(buf, len, n, " chg_stat=", (int32_t)chg);
  n = put(buf, len, put(buf, len, n, " stage="), stage[stage_of(chg) & 7U]);
  n = kv(buf, len, n, " en_chg=", (s->reg0f & EN_CHG) != 0U);
  n = put(buf, len, put(buf, len, n, " hold="), s->hold < CH_COUNT ? hold[s->hold] : "?");
  n = kv(buf, len, n, " pg=", (s->st[S_1B] & PG_STAT) != 0U);
  n = kv(buf, len, n, " wd=", (s->st[S_1B] & WD_STAT) != 0U);
  n = put_hex(buf, len, put(buf, len, n, " fault0="), s->st[S_20], 2);
  n = put_hex(buf, len, put(buf, len, n, " fault1="), s->st[S_21], 2);
  n = kv(buf, len, n, " vbus_mv=", s->vbus);
  n = kv(buf, len, n, " ibus_ma=", (int16_t)s->ibus);
  n = kv(buf, len, n, " vbat_mv=", s->vbat);
  n = kv(buf, len, n, " ibat_ma=", (int16_t)s->ibat);
  n = kv(buf, len, n, " vsys_mv=", s->vsys);
  n = kv(buf, len, n, " applies=", s->applies);
  n = kv(buf, len, n, " resets=", s->resets);
  n = kv(buf, len, n, " failures=", s->failures);
  return kv(buf, len, n, " poll_age_ms=", s->ok ? (int32_t)(now_ms - s->poll_ms) : -1);
}
