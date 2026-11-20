#ifndef CHARGER_H
#define CHARGER_H
/* The BQ25798 charger (phase C, WS_POWER_PROFILE 3; App/power_config.h): its set-up, its charge gate
 * and its readings, on one step machine that App/power_acq.c drives. Registers: TI SLUSDV2C (rev. June
 * 2026) section 7.5.1; conversions firmware/common/power_regs.h.
 *
 * Every CHARGER_PERIOD_MS the machine:
 *   1. identifies the part (REG48 PN = 3) until it has, and after any NACK;
 *   2. reads REG01-REG10 (VREG, ICHG, ITERM, CELL, REG0F, REG10). VREG, ICHG or ITERM other than
 *      POWER_CHG_VREG_MV, POWER_CHG_ICHG_MA and POWER_CHG_ITERM_MA's nearest code rewrites all three,
 *      then reads them back. At the first poll that is the boot write; after a
 *      set-up that held, it is a chip reset (the I2C watchdog expired or the chip lost power: ICHG resets
 *      to 1 A on either, SLUSDV2C table 7-16), counted in resets;
 *   3. reads the status registers REG1B-REG21 and, once a one-shot conversion is done, the ADC
 *      (REG2E-REG42);
 *   4. writes REG0F with EN_CHG set only when nothing holds charge off (enum charger_hold), and REG10
 *      with WD_RST, which keeps the chip in host mode (its 40 s watchdog, table 7-26);
 *   5. starts the next one-shot ADC conversion (REG2E = ADC_EN | ADC_RATE, 15-bit).
 * A failed transfer ends the poll; the next one starts again from the top. */
#include <stdint.h>
#include "i2c_bus.h"

#define CHARGER_PERIOD_MS 5000U
#define CHARGER_TS_FRESH_MS 12000U   /* the oldest TS reading the gate trusts: two polls and a margin */

/* Why charge is held off (EN_CHG written 0), the first that applies; CH_NONE: EN_CHG written 1. */
enum charger_hold { CH_NONE, CH_ABSENT, CH_PART, CH_CELLS, CH_READBACK, CH_TS_STALE, CH_TS_COLD, CH_TS_HOT,
                    CH_COUNT };

/* The latest readings, each as the chip gave it (raw register images), for the gate, the status byte and
   the console. */
typedef struct {
  uint8_t present;      /* REG48 matched at the last identify, and no NACK since */
  uint8_t ok;           /* the last poll ran to its end */
  uint8_t fault;        /* the last failure was a bus fault, not an absent part */
  uint8_t configured;   /* VREG, ICHG and ITERM read back as set */
  uint8_t adc_ok;       /* an ADC read since boot */
  uint8_t hold;         /* enum charger_hold of the last REG0F write (CH_ABSENT before any) */
  uint8_t reg48, reg09, reg0a, reg0f, reg10, reg2e;
  uint16_t vreg_raw, ichg_raw;    /* REG01-02, REG03-04 */
  uint8_t st[7];                  /* REG1B to REG21 */
  uint16_t ibus, ibat, vbus, vbat, vsys, ts, tdie;   /* REG31 to REG41, raw */
  uint32_t ts_ms;                 /* when ts was converted (the poll that read it) */
  uint32_t poll_ms;               /* when the last poll ended */
  uint16_t applies;               /* VREG/ICHG writes since boot, the boot write included */
  uint16_t resets;                /* chip resets seen: a set-up that held, then read back as another */
  uint16_t failures;              /* failed transfers since boot */
} charger_t;

/* What a power window takes from the charger: the ADC reads since the last close (sums and their count)
   and the latest values, each none-free only when n > 0; fault: a bus fault since the last close. */
typedef struct {
  int64_t ibat_ma, vbus_mv, vsys_mv;
  uint16_t n;
  uint16_t vbus_last_mv, vbat_last_mv;
  int16_t ibus_last_ma, tdie_last_dc;
  uint8_t fault;
} charger_win_t;

void charger_init(uint32_t now_ms);
void charger_tick(uint32_t now_ms);   /* starts a poll when one is due and none runs; never waits */
void charger_i2c_done(int rc);        /* I2C_C_CHARGER's completion */
const charger_t *charger_state(void);
/* The health report's charger status byte (power telemetry spec section 6.3): 0xFF without a complete
   poll, else power good (PG_STAT), charging (CHG_STAT 1-4 or 6), fault (a REG20/REG21 fault or a hold
   for the part, the cell count or the read-back), the stage and the active input. */
uint8_t charger_status_byte(void);
void charger_close(charger_win_t *w);   /* the window's ADC values; starts the next window */
/* "#charger ..." (no newline) into buf, truncated to len - 1 characters; returns its length. */
#define CHARGER_LINE_MAX 416U   /* the longest line is 400 characters (every field at its widest) */
unsigned charger_line(char *buf, unsigned len, uint32_t now_ms);
#endif
