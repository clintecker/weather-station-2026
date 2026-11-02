#ifndef POWER_CONFIG_H
#define POWER_CONFIG_H
/* The station's power build: its profile, its rail table and its power constants
 * (docs/superpowers/specs/2026-10-29-power-telemetry-design.md sections 2, 3, 8.6, 9.2 and 9.3).
 * Fixed at build time, no dynamic allocation (docs/power-of-ten.md rule 3). App/power_acq.c reads it.
 *
 * WS_POWER_PROFILE (spec section 2):
 *   1  phase A (the default): the bq24074 charger, the battery INA228 at 0x40 (shunt in the battery path,
 *      VBUS by its own sense lead to the OUT connector (P5), so its VBUS is the load voltage) and the
 *      MAX17048 gauge at 0x36 on the CELL+ node (M4). Load current and the solar and USB-C rails are not
 *      fitted.
 *   2  phase B: phase A plus a load INA228 (0x41, on OUT), a solar INA228 (0x45) and a USB-C INA228
 *      (0x48), each upstream of the point where the sources join (the #4755's own D2/D4 OR pair, with
 *      EN2 high and EN1 low; spec section 11.3). The battery INA228's VBUS is not read: the load INA228 owns the
 *      load voltage, and the battery voltage stays the gauge's VCELL. Its sense lead moves from OUT to the
 *      CELL+ node (position 4) at step 1b, a host-side cross-check (spec section 17, build-progression
 *      record step 1b, P5 and M4).
 *   3  phase C (BQ25798): a later phase; the build stops.
 *
 * Calibration (spec section 8.6). Every constant is nominal until the build sheet's check measures or
 * verifies it (hardware/bench-breadboard-r0/build-sheet.md); a measured value replaces it here, with the
 * check cited beside it. A nonzero firmware build ID in the health report names the commit, so these
 * constants; a dirty tree sends build ID 0 (Makefile FW_BUILD_ID), so commit a measured value before
 * flashing it. The profile shows in the observation: only profile 2 sends the load, solar and USB-C
 * fields (spec sections 5.3 and 8.6). */
#include <stdint.h>
#include "i2c_bus.h"

#define WS_POWER_PROFILE_A 1
#define WS_POWER_PROFILE_B 2
#define WS_POWER_PROFILE_C 3
#ifndef WS_POWER_PROFILE
#define WS_POWER_PROFILE WS_POWER_PROFILE_A
#endif
#if WS_POWER_PROFILE == WS_POWER_PROFILE_C
#error "WS_POWER_PROFILE 3 (phase C, BQ25798): BQ25798 driver: a later phase"
#elif WS_POWER_PROFILE != WS_POWER_PROFILE_A && WS_POWER_PROFILE != WS_POWER_PROFILE_B
#error "WS_POWER_PROFILE must be 1 (phase A) or 2 (phase B)"
#endif

/* The power slots, source-agnostic: what is measured, never which part measures it (spec section 3.2).
   The battery module (WSMP type 8) is PS_BATT_MV to PS_CHARGE_OUT, the rails module (type 9) the rest. */
enum power_slot { PS_BATT_MV, PS_BATT_MA, PS_ENERGY_IN, PS_ENERGY_OUT, PS_CHARGE_IN, PS_CHARGE_OUT,
                  PS_LOAD_MV, PS_LOAD_MA, PS_CHARGER_IN_MV, PS_SOLAR_MV, PS_SOLAR_MA, PS_USB_MV, PS_USB_MA,
                  PS_COUNT };
#define PS_NONE 0xFFU   /* a rail whose VBUS is not read */

/* INA228 addresses (spec section 9.2; straps A1, A0 from TI SBOS904, verify before strapping). */
#define POWER_ADDR_BATTERY 0x40U   /* GND, GND (the Adafruit #5832 default) */
#define POWER_ADDR_LOAD    0x41U   /* GND, VS */
#define POWER_ADDR_SOLAR   0x45U   /* VS, VS */
#define POWER_ADDR_USB     0x48U   /* SDA, GND (a rework: the #5832 jumpers reach VS only) */
/* Never an INA228 address: the gauge (0x36), the SHT45 and its phantom (0x44), the BMP581 (0x46, 0x47),
   the record EEPROM (0x50), the LTR390 (0x53), the SHTC3 (0x70) and the mux (0x71). */
#define POWER_ADDR_RESERVED(a) ((a) == 0x36U || (a) == 0x44U || (a) == 0x46U || (a) == 0x47U || (a) == 0x50U || \
                                (a) == 0x53U || (a) == 0x70U || (a) == 0x71U)
_Static_assert(!POWER_ADDR_RESERVED(POWER_ADDR_BATTERY), "battery INA228 on a reserved address");
_Static_assert(!POWER_ADDR_RESERVED(POWER_ADDR_LOAD), "load INA228 on a reserved address");
_Static_assert(!POWER_ADDR_RESERVED(POWER_ADDR_SOLAR), "solar INA228 on a reserved address");
_Static_assert(!POWER_ADDR_RESERVED(POWER_ADDR_USB), "USB-C INA228 on a reserved address");
_Static_assert(POWER_ADDR_BATTERY != POWER_ADDR_LOAD && POWER_ADDR_BATTERY != POWER_ADDR_SOLAR &&
               POWER_ADDR_BATTERY != POWER_ADDR_USB && POWER_ADDR_LOAD != POWER_ADDR_SOLAR &&
               POWER_ADDR_LOAD != POWER_ADDR_USB && POWER_ADDR_SOLAR != POWER_ADDR_USB,
               "two INA228 rails share an address");
#define POWER_ADDR_GAUGE 0x36U     /* MAX17048, fixed */

/* Shunts, micro-ohm: the Adafruit #5832's 15 mOhm (1 %), nominal. Verified, not measured (spec section 8.6):
   build-sheet power check 3 (the battery rail) and phase B check B3 (load, solar, USB-C) compare each rail's
   current with a series reference, within 2 % + 2 mA; only a rail that fails gets its reference-derived value
   here, with the check cited. */
#define POWER_SHUNT_UOHM_BATTERY 15000U
#define POWER_SHUNT_UOHM_LOAD    15000U
#define POWER_SHUNT_UOHM_SOLAR   15000U
#define POWER_SHUNT_UOHM_USB     15000U
/* The current step (CURRENT_LSB), uA. CURRENT and so CHARGE are 20-bit signed: a rail measures
   +-2^19 x CURRENT_LSB, +-5.24 A at 10 uA (the shunt ADC itself would reach +-10.9 A at 15 mOhm). That
   is each rail's limit in phases A and B (the bq24074 charges at most 1.5 A); a rail that needs more
   raises its step (20 uA: +-10.5 A). SHUNT_CAL = 131072 x lsb x R / 10^7 (ina228_shunt_cal). */
#define POWER_LSB_UA 10U
#define POWER_RAIL_LIMIT_MA 5242   /* 2^19 x 10 uA */

/* bq24074 ISET (SLUS810 eq. 2 and 3). R_ISET: R9 = 1 kOhm behind the #4755's closed 1A jumper
   (build-progression record section 1.4), so ICHG = KISET / R_ISET = 890 / 1000 = 0.89 A typ; ISET
   currents read with the earlier 890 were 12 % high. Confirmed by build-sheet check 2 (ISET to GND,
   charger unpowered, cell disconnected). Adopted with change A, read by this workflow from record 7.1 P3
   'change A as written'; Clint to confirm (power-telemetry design D4/D5). */
#define POWER_R_ISET_OHM 1000U
/* The ISET gain, ppm: the PB1 node sits behind 10 kOhm in series from the charger's ISET, with 1 MOhm
   (and 100 nF) to ground (record M2), so the pin reads V_ISET x 1 MOhm / 1.01 MOhm = 0.990099 V_ISET.
   Nominal until the M2 per-board fit (a CC charge above 200 mA, load off, against the battery INA228).
   Adopted with change A, read by this workflow from record 7.1 P3 'change A as written'; Clint to
   confirm (power-telemetry design D4/D5). */
#define POWER_ISET_GAIN_PPM 990099U
/* The charger input divider, ppm: 20 kOhm (two 10 kOhm, R4 + R5) over 10 kOhm (R6),
   (R4 + R5 + R6) / R6 x 1e6, so VIN = pin x POWER_VIN_DIVIDER_PPM / 1e6. Nominal (3) until the three
   resistors are measured (record 4.4 step 12); checked in circuit against the model within 1 %.
   Adopted with change A, read by this workflow from record 7.1 P3 'change A as written'; Clint to
   confirm (power-telemetry design D4/D5). */
#define POWER_VIN_DIVIDER_PPM 3000000U

/* One INA228 rail (spec section 9.3). sign turns the part's VIN+ -> VIN- count into the rail's
   positive direction (section 3.1). vbus_slot is the slot its VBUS fills, or PS_NONE (not read). */
typedef struct {
  enum i2c_client client;
  uint8_t addr;
  uint32_t shunt_uohm, current_lsb_ua;
  int8_t sign;
  uint8_t current_slot, vbus_slot;
} power_rail_t;

/* The battery rail is row 0 in every profile: it also feeds the counters and the battery energy. Battery:
   CELL+ on VIN+, the charger's BATT socket (the BATT joint, record P3) on VIN-: out of the cell, sign -1.
   Load, solar, USB-C: VIN+ towards the source, sign +1. */
#define POWER_RAIL_BATTERY 0U
#if WS_POWER_PROFILE == WS_POWER_PROFILE_A
#define POWER_RAIL_COUNT 1U
static const power_rail_t POWER_RAILS[POWER_RAIL_COUNT] = {
  { I2C_C_INA228, POWER_ADDR_BATTERY, POWER_SHUNT_UOHM_BATTERY, POWER_LSB_UA, -1, PS_BATT_MA, PS_LOAD_MV },
};
#else
#define POWER_RAIL_COUNT 4U
static const power_rail_t POWER_RAILS[POWER_RAIL_COUNT] = {
  { I2C_C_INA228, POWER_ADDR_BATTERY, POWER_SHUNT_UOHM_BATTERY, POWER_LSB_UA, -1, PS_BATT_MA, PS_NONE },
  { I2C_C_INA_LOAD, POWER_ADDR_LOAD, POWER_SHUNT_UOHM_LOAD, POWER_LSB_UA, 1, PS_LOAD_MA, PS_LOAD_MV },
  { I2C_C_INA_SOLAR, POWER_ADDR_SOLAR, POWER_SHUNT_UOHM_SOLAR, POWER_LSB_UA, 1, PS_SOLAR_MA, PS_SOLAR_MV },
  { I2C_C_INA_USB, POWER_ADDR_USB, POWER_SHUNT_UOHM_USB, POWER_LSB_UA, 1, PS_USB_MA, PS_USB_MV },
};
#endif
#endif
