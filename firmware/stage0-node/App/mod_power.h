#ifndef MOD_POWER_H
#define MOD_POWER_H
/* The WSMP face of the power acquisition (App/power_acq.c; docs/superpowers/specs/
 * 2026-10-29-power-telemetry-design.md sections 5.3, 8.1, 8.3-8.5 and 9.6): two base-board modules and
 * the slow values of the health report.
 *
 *   Battery module, port P_BATTERY (5), WSMP type 8, minute class, 6 channels in registry order:
 *     0 battery voltage, V -3 w2 unsigned, mean: the cell (MAX17048 VCELL at the CELL+ node, which
 *       includes the pack-lead drop while current flows, record M4; never the charger OUT)
 *     1 battery current, A -3 w2 signed, mean: + into the cell (charging); the battery INA228's CHARGE
 *       delta over the window's time, its shunt in the battery path between CELL+ and the charger's
 *       BATT socket (record P3)
 *     2-5 energy in, energy out (Wh -3 w3), charge in, charge out (Ah -3 w3): counters since boot
 *   Rails module, port P_RAILS (8), WSMP type 9, minute class, 7 channels, V -3 w2 unsigned and
 *   A -3 w2 signed, means:
 *     0 load voltage: the charger OUT (the system rail; phase A: the battery INA228's VBUS sense lead on OUT)
 *     1 load current, + into the load
 *     2 charger input voltage: the bq24074 IN after the sources join (PA10 x POWER_VIN_DIVIDER_PPM); the source is
 *       not identified
 *     3, 4 solar voltage and current, + into the station, upstream of the join
 *     5, 6 USB-C voltage and current, + into the station, upstream of the join
 *
 * Presence (WSMP-P1, spec section 8.5): both modules are fixed by WS_POWER_PROFILE and present in every
 * profile, always, whatever their parts answer. A missing part (NACK, wrong ID) makes only its own slots
 * missing, a bus fault makes them fault, and a slot the profile has no source for is "not fitted"
 * (WSMP_QUAL_NOT_FITTED, WSMP 1.1). So the catalog map turns a dead part into INVALID fields, never
 * absent ones.
 *
 * Each module's latch closes power_acq's window once for the latch token (the first of the two modules
 * to latch with a new token closes it; the other copies the same window), so both modules report the
 * same minute. */
#include <stdint.h>
#include "wsmp.h"

#define POWER_PGOOD 0x01U   /* board_charger_pins(): PGOOD asserted (input power good) */
#define POWER_CHG   0x02U   /* board_charger_pins(): CHG asserted (charging) */
/* The bq24074 status pins, both open drain and active low, as asserted bits (a link-time seam: the
   board, App/board_inputs.c, or a host harness defines it). */
int board_charger_pins(void);

#define POWER_BATTERY_CHANNELS 6U
#define POWER_RAILS_CHANNELS 7U

/* The health report's power values (spec sections 3.3 and 6.1), cached at the last latch. Every member
   has the name and the none code of its ws_diag_t member (firmware/common/ws_frame.h): unsigned all
   ones, signed the type's minimum, the charger status 0xFF. Phase A and B have no charger-reported
   input, battery voltage or temperatures (none); chg_batt_ma is the bq24074 ISET current while PGOOD is
   asserted, 0 mA while it is not, none when the ADC failed or ISET clipped. fitted is the profile's
   WS_FIT_* mask (ws_frame.h): a none code in a fitted slot is a fault, in any other "not measured". */
typedef struct {
  uint16_t vdda_mv;          /* MCU supply, VDDA via VREFINT, mean of the last window */
  uint16_t soc;              /* gauge SOC, 1/256 % as read */
  uint16_t chg_input_mv, chg_batt_mv;
  int16_t monitor_temp;      /* the hottest fitted INA228's die, 0.1 degC */
  int16_t soc_rate;          /* gauge SOC rate, 0.1 %/h, + while charging */
  int16_t chg_input_ma, chg_batt_ma;
  int16_t chg_temp, pack_temp;
  uint8_t charger_status;    /* spec section 6.3 */
  uint8_t fitted;            /* WS_FIT_* bits: the slots this profile has a source for (spec section 6.1) */
} power_health_t;

enum power_module { PM_BATTERY, PM_RAILS };

void mod_power_init(uint32_t boot_id, uint32_t now_ms);
void mod_power_tick(uint32_t now_ms);   /* once per station tick (the battery port's) */
/* Always 1 (present); seq moves once a second. */
int mod_power_probe(uint16_t *seq);
void mod_power_identity(enum power_module m, uint8_t id[WSMP_IDENTITY_LEN], uint8_t desc[WSMP_DESC_BLOCK_LEN]);
void mod_power_latch(enum power_module m, uint16_t token, uint32_t now_ms);
void mod_power_snapshot(enum power_module m, uint8_t snap[WSMP_SNAPSHOT_LEN]);
/* The cached slow values of the last latch; every member is its none code before the first one. Never
   touches the bus or the ADC. */
void mod_power_health(power_health_t *out);
#endif
