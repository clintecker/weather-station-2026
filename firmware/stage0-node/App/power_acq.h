#ifndef POWER_ACQ_H
#define POWER_ACQ_H
/* Power acquisition (App/power_acq.c; docs/superpowers/specs/2026-10-29-power-telemetry-design.md
 * sections 3, 6.3, 9.4 and 9.5): the parts of the profile's rail table (App/power_config.h), the
 * MAX17048 gauge, the board ADC (ISET, charger input, VREFINT) and the bq24074 CHG and PGOOD pins, read
 * on non-blocking step machines over the shared I2C bus (one transfer at a time for each client). It
 * turns them into a minute window of source-agnostic slots (enum power_slot) and the slow values of the
 * health report. App/mod_power.c is its WSMP face.
 *
 * Schedule (every interval counted from clock_ms(), never HAL_GetTick, which counts 1/1024 s here):
 *   each INA228 rail   1 s   SHUNT_CAL check (a mismatch: the part was reset, so identify it, calibrate
 *                            it and take a new base), VBUS if the rail's VBUS is read, CHARGE.
 *                            ENERGY is not read (battery energy is dQ x the cell voltage).
 *                     60 s   DIETEMP
 *   MAX17048          15 s   VERSION, VCELL, SOC, CRATE
 *   board ADC          1 s   the latest sequence (board_power_adc)
 *   CHG and PGOOD    250 ms  the pins and the CHG edge count (board_charger_edges)
 *
 * Values:
 *   - Rail current (mA) = sign x sum of the window's CHARGE deltas (CURRENT_LSB x 1 s a count) over the
 *     sum of their elapsed milliseconds; the step after a reset or a calibration is only a new base.
 *   - Battery voltage = the gauge's VCELL in every profile; no INA228 VBUS fallback (the official wiring
 *     puts the battery INA228's VBUS on OUT, which is the load voltage in phase A; in profile B it is not
 *     read, wherever its lead sits. The build-progression record's M4, the INA228 VBUS at CELL+ as the
 *     cell voltage of record, is rejected for the wire format: spec section 17).
 *   - Battery energy: each step adds dQ x the latest VCELL (at most 20 s old) to energy in or out by the
 *     sign of dQ. A step with charge and no fresh VCELL adds its charge but no energy and marks the
 *     window: both energy slots are missing for it (fields 13 and 14 INVALID that minute).
 *   - Charger input (mV) = the PA10 pin x POWER_VIN_DIVIDER_PPM / 1e6, VDDA-scaled; a clipped sample
 *     (>= 4080) makes the minute's slot missing. ISET (mA) = 400 x V_ISET / R_ISET, V_ISET = the PB1 pin
 *     x 1e6 / POWER_ISET_GAIN_PPM (the 10k/1M network), while PGOOD is asserted; 0 while it is not, none
 *     when the ADC failed or ISET clipped. Each ADC sequence is sampled once (its seq):
 *     with no new sequence in the minute (a stalled ADC) the charger input is missing and VDDA and ISET
 *     are none, not the last values again.
 *
 * Qualities (WSMP codes, firmware/common/wsmp.h): GOOD; PARTIAL in the first window, after a gap (a
 * failed step, a reset) or with too few samples; MISSING with no sample (a part absent, a wrong chip
 * ID, a clipped ADC, energy without a fresh VCELL); FAULT with no sample after a bus fault; NOT_FITTED
 * for a slot the profile has no source for. A slot that is not fitted never becomes anything else. */
#include <stdint.h>
#include "i2c_bus.h"
#include "power_config.h"

/* The health report's none codes (spec section 6.1). */
#define POWER_NONE_U16 0xFFFFU
#define POWER_NONE_I16 INT16_MIN
#define POWER_NONE_U8  0xFFU

/* Charger status byte (spec section 6.3): bit 0 input power good, bit 1 charging (CHG steady), bit 2
   fault (CHG flashing: 3 or more edges within 2 s, cleared after 4 s without one), bits 3-5 stage (0 not
   reported in phase A), bits 6-7 active input (0 not reported in phase A). */
#define POWER_STATUS_POWER_GOOD 0x01U
#define POWER_STATUS_CHARGING   0x02U
#define POWER_STATUS_FAULT      0x04U

/* One slot of a closed window. value: a mean (mV, mA) or a counter since boot (mWh, mAh). */
typedef struct {
  int32_t value;
  uint16_t count;    /* samples (means) or valid steps (counters) in the window */
  uint8_t quality;   /* WSMP_QUAL_* */
} power_slot_t;

/* The slow values (health report, spec sections 3.3 and 6.1), each with its none code. */
typedef struct {
  uint16_t soc_256;        /* gauge SOC, 1/256 % as read (can pass 100 %) */
  int16_t soc_rate;        /* gauge SOC rate, 0.1 %/h, + while charging, saturating */
  uint8_t charger_status;  /* section 6.3 */
  int16_t monitor_temp;    /* the hottest fitted INA228's latest DIETEMP, 0.1 degC */
  uint16_t vdda_mv;        /* VDDA from VREFINT, mean of the window's samples */
  int16_t chg_batt_ma;     /* charger-reported charge current, mean of the window's samples */
  /* Phase C only (the BQ25798's ADC, the window's latest read), else none: */
  uint16_t chg_input_mv, chg_batt_mv;   /* VBUS, VBAT */
  int16_t chg_input_ma, chg_temp;       /* IBUS (+ into the charger), the die, 0.1 degC */
} power_slow_t;

typedef struct {
  power_slot_t slot[PS_COUNT];
  uint32_t window_ms;   /* the window's length */
  uint8_t first;        /* 1 for the first window since init */
  power_slow_t slow;
} power_window_t;

/* now_ms is clock_ms() (App/clock.h) in every call. */
void power_acq_init(uint32_t now_ms);
void power_acq_tick(uint32_t now_ms);   /* every WSMP_TICK_MS (250 ms); starts what is due, never waits */
/* The completion of a power client's transfer (i2c_bus_done routes I2C_C_INA228 to I2C_C_MAX17048 and
   I2C_C_CHARGER here). */
void power_acq_i2c_done(enum i2c_client c, int rc);
/* Closes the window at now_ms into *out and opens the next one. */
void power_acq_latch(uint32_t now_ms, power_window_t *out);
/* What the bench screen shows right now, each from the latest read (nothing is closed or reset).
   batt_ok: the battery INA228 has a current step; batt_ma_x100 is that step's mean current in 0.01 mA
   (+ into the cell), out_mv the load rail's latest VBUS (OUT), 0 where the profile reads none.
   gauge_ok: the MAX17048 answered its last read; vcell_mv and soc_pct_x10 (0.1 %) are its values.
   charging: the bq24074 CHG pin steady (not flashing), or the BQ25798's CHG_STAT (phase C); charger: the
   health report's charger status byte. Phase C: out_mv is the charger's VSYS.
   rail: the load, solar and USB-C INA228s (enum power_live_rail): fitted, the profile has the rail's
   current slot; ok, its part has a current step; ma_x100 and mv, as the battery's (mv 0 where its VBUS is
   not read). A value whose part is not ok reads 0. */
enum power_live_rail { PL_LOAD, PL_SOLAR, PL_USB, PL_RAILS };
typedef struct { int fitted, ok; int32_t ma_x100, mv; } power_rail_live_t;
typedef struct {
  int batt_ok;
  int32_t batt_ma_x100, out_mv;
  int gauge_ok;
  uint16_t vcell_mv, soc_pct_x10;
  int charging;
  uint8_t charger;
  power_rail_live_t rail[PL_RAILS];
} power_live_t;
void power_acq_live(power_live_t *p);
/* 1 if the profile has a source for the slot. */
int power_acq_fitted(enum power_slot s);
#endif
