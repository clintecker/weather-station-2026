#ifndef CHARGER_H
#define CHARGER_H
/* The BQ25798 charger (phase C, WS_POWER_PROFILE 3; App/power_config.h): its set-up, its charge gate
 * and its readings, on one step machine that App/power_acq.c drives. Registers: TI SLUSDV2C (rev. June
 * 2026) section 7.5.1; conversions firmware/common/power_regs.h.
 *
 * Every CHARGER_PERIOD_MS the machine:
 *   1. identifies the part (REG48 PN = 3) until it has, and after any NACK;
 *   2. reads REG01-REG18. The set-up is VREG, ICHG and ITERM (POWER_CHG_VREG_MV, POWER_CHG_ICHG_MA and
 *      POWER_CHG_ITERM_MA's nearest code) with STOP_WD_CHG (REG09 bit 5: a watchdog expiry turns charge
 *      off), VAC_OVP (REG10), VOC_PCT (REG15) and the JEITA and TS settings (REG17, REG18). Any of them other than set rewrites all of them, then reads them back.
 *      At the first poll that is the boot write; after a set-up that held, it is a chip reset (the I2C
 *      watchdog expired or the chip lost power: ICHG resets to 1 A on either, SLUSDV2C table 7-16),
 *      counted in resets. EN_MPPT is not part of it: the chip clears it whenever VBUS goes;
 *   3. reads the status registers REG1B-REG21 and, once a one-shot conversion is done, the ADC
 *      (REG2E-REG42);
 *   4. writes REG0F with EN_CHG set only when nothing holds charge off (enum charger_hold), and REG10
 *      with WD_RST, which keeps the chip in host mode (its 40 s watchdog, table 7-26; past it, the chip
 *      resets EN_CHG and the set-up, and STOP_WD_CHG makes that charge off);
 *   5. writes REG15 with EN_MPPT when VBUS is present, VSYS_STAT is clear and EN_MPPT reads 0 (section
 *      7.3.6.3), counted in mppt_sets, not in resets;
 *   6. starts the next one-shot ADC conversion (REG2E = ADC_EN | ADC_RATE, 15-bit).
 * A failed transfer ends the poll; the next one starts again from the top. */
#include <stdint.h>
#include "i2c_bus.h"

#define CHARGER_PERIOD_MS 5000U
#define CHARGER_TS_FRESH_MS 12000U   /* the oldest TS reading the gate trusts: two polls and a margin */

/* Why charge is held off (EN_CHG written 0), the first that applies; CH_NONE: EN_CHG written 1. */
enum charger_hold { CH_NONE, CH_ABSENT, CH_PART, CH_CELLS, CH_READBACK, CH_TS_STALE, CH_TS_COLD, CH_TS_HOT,
                    CH_TS_WARM, CH_COUNT };

/* The latest readings, each as the chip gave it (raw register images), for the gate, the status byte and
   the console. */
typedef struct {
  uint8_t present;      /* REG48 matched at the last identify, and no NACK since */
  uint8_t ok;           /* the last poll ran to its end */
  uint8_t fault;        /* the last failure was a bus fault, not an absent part */
  uint8_t configured;   /* the set-up (step 2) read back as set */
  uint8_t adc_ok;       /* an ADC read since boot */
  uint8_t hold;         /* enum charger_hold of the last REG0F write (CH_ABSENT before any) */
  uint8_t reg48, reg05, reg09, reg0a, reg0f, reg10, reg15, reg17, reg18, reg2e;
  uint16_t vreg_raw, ichg_raw;    /* REG01-02, REG03-04 */
  uint8_t st[7];                  /* REG1B to REG21 */
  uint16_t ibus, ibat, vbus, vbat, vsys, ts, tdie;   /* REG31 to REG41, raw */
  uint32_t ts_ms;                 /* when ts was converted (the poll that read it) */
  uint32_t poll_ms;               /* when the last poll ended */
  uint16_t applies;               /* set-up writes since boot, the boot write included */
  uint16_t resets;                /* chip resets seen: a set-up that held, then read back as another */
  uint16_t failures;              /* failed transfers since boot */
  uint16_t mppt_sets;             /* EN_MPPT writes since boot (each time VBUS came back, or after a reset) */
} charger_t;

/* What a power window takes from the charger: the ADC reads since the last close (sums and their count)
   and the latest values, each none-free only when n > 0; fault: a bus fault since the last close. */
typedef struct {
  int64_t ibat_ma, vbus_mv, vsys_mv;
  uint16_t n;
  uint16_t vbus_last_mv, vbat_last_mv;
  int16_t ibus_last_ma, tdie_last_dc;
  int16_t pack_last_dc;   /* the pack NTC from TS (charger_pack_temp_dc), POWER_NONE_I16 out of its range */
  uint8_t fault;
} charger_win_t;

void charger_init(uint32_t now_ms);
void charger_tick(uint32_t now_ms);   /* starts a poll when one is due and none runs; never waits */
void charger_i2c_done(int rc);        /* I2C_C_CHARGER's completion */
const charger_t *charger_state(void);
/* The health report's charger status byte (power telemetry spec section 6.3): 0xFF without a complete
   poll, else power good (PG_STAT), charging (CHG_STAT 1-4 or 6), fault (a REG20/REG21 fault or a hold
   for the cell count or the read-back), the stage and the active input. Another part at the charger's
   address (CH_PART) never completes a poll, and reads as the fault bit alone (0x04): stage and input not
   reported. A TS hold (cold, warm,
   hot) is no fault: the health report's pack temperature carries it, and a stale TS reading leaves that
   slot none under its fitted bit, which the gateway reports as a sensor fault. */
uint8_t charger_status_byte(void);
/* The pack temperature in 0.1 degC from a TS ADC result (REG3F): the Adafruit #372 NTC (B 3950) across the
   EVM's TS divider (App/power_config.h), by table, -30 to +80 degC; POWER_NONE_I16 outside it (an open or
   shorted thermistor). */
int16_t charger_pack_temp_dc(uint16_t ts_raw16);
void charger_close(charger_win_t *w);   /* the window's ADC values; starts the next window */
/* "#charger ..." (no newline) into buf, truncated to len - 1 characters; returns its length. */
#define CHARGER_LINE_MAX 512U   /* the longest line is about 495 characters (every field at its widest) */
unsigned charger_line(char *buf, unsigned len, uint32_t now_ms);
#endif
