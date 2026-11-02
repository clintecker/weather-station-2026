/* The bench telemetry packet (README.md): one every 5 s from the TX, plain LoRa, test only. Pure C, so
 * the host tests (tests/test_benchlink.py) check the layout against the logger's decoder.
 * Little endian, 78 bytes (version 4; version 2 was bytes 0..61 and its CRC at 62). Version 4 is version 3's
 * layout with change A's meaning: byte 20 on, the PB1 node behind the ISET network, not the ISET pin; and
 * the shunt in the official orientation, so the logger turns its sign into battery_ma. The logger keeps
 * version 3 and older with their own meaning (the ISET pin, no gain; no battery_ma):
 *    0  'W' 'B'  magic
 *    2  u8   version (BL_VERSION)
 *    3  u8   flags (BL_F_*; bits 6 and 7, the clip flags, need no layout change)
 *    4  u32  seq: packets sent since boot
 *    8  u32  uptime, s since power-on: the RTC tick count (1/1024 s, HAL_GetTick() on this board), which
 *            keeps counting through a reset and restarts only when the board loses power; wraps at 48.5 days
 *   12  i32  INA228 VBUS, uV: the charger's OUT (VBUS on its own sense lead to the OUT joint)
 *   16  i32  INA228 shunt current, uA, mean of the interval: raw, the part's own sign: + = into VIN+, out
 *            through VIN-. With the official orientation (CELL+ on VIN+, the charger's BATT socket on VIN-;
 *            docs/superpowers/specs/2026-10-29-power-telemetry-design.md section 3.1) + is OUT OF the cell.
 *            The TX sends it unturned; the logger turns it once, for version 4 only (tools/benchlink_log.py
 *            battery_ma(): battery_ma = -ishunt_ma, + into the cell).
 *   20  i32  ISET mean, uV: the PB1 node voltage, behind 10 kOhm series with 100 nF and 1 MOhm to ground,
 *            not the charger's ISET pin: V_ISET = iset_uv x 1.01 MOhm / 1 MOhm. tools/benchlink_log.py applies
 *            that gain (version 4 only) and R_ISET (1 kOhm): I = 400 * V_ISET / R_ISET (TI SLUS810 eq. 3).
 *   24  i32  ISET minimum, uV (the PB1 node, as above)
 *   28  i32  ISET maximum, uV (the PB1 node, as above)
 *   32  i32  INA228 die temperature, m degC
 *   36  i32  MAX17048 VCELL, uV
 *   40  i32  MAX17048 SOC, milli-percent
 *   44  i32  MAX17048 CRATE, milli-percent an hour
 *   48  i32  SHT45 temperature, m degC
 *   52  i32  SHT45 relative humidity, milli-percent
 *   56  i32  the charger's input (VBUS), uV: A2 (PA10) through the 20k/10k divider, times VIN_DIVIDER_PPM / 1e6
 *   60  u8   good INA228 samples in the interval (the ADC's count is not sent)
 *   61  u8   failed INA228 samples in the interval
 *   62  u8   reset cause of this boot (BL_RESET_*, App/bl_guard.h)
 *   63  u8   crashes recorded since the TX last lost power (saturates at 255)
 *   64  u16  boots since the TX last lost power
 *   66  u16  radio transmissions that timed out, since boot
 *   68  u16  I2C bus restarts, since boot
 *   70  u16  of those, restarts that found SDA held low and clocked it free
 *   72  u32  program counter of the last recorded crash, 0 for none
 *   76  u16  CRC-16/CCITT-FALSE of bytes 0..75 */
#ifndef BL_PKT_H
#define BL_PKT_H

#include <stdint.h>

#define BL_PKT_LEN 78U
#define BL_VERSION 4U   /* change A (the ISET network, the shunt's orientation): same layout as 3 */

#define BL_F_INA    0x01U   /* the INA228 answered with its ids */
#define BL_F_GAUGE  0x02U   /* the MAX17048 answered with its version */
#define BL_F_SHT    0x04U   /* the SHT45 measured with good CRCs */
#define BL_F_PGOOD  0x08U   /* the bq24074 PGOOD pin is low (asserted) */
#define BL_F_CHG    0x10U   /* the bq24074 CHG pin is low (asserted) */
#define BL_F_ADC    0x20U   /* the ISET and input readings are valid */
/* A reading of the interval clipped: its 16-conversion mean was at or above POWER_ADC_CLIP_RAW (4080, 99.6 %
   of full scale; firmware/common/power_regs.h adc_clipped, the node's rule, spec section 9.5). The node then
   sends charger_input_mv INVALID and no ISET current; the logger leaves vin_v, or the charge_* columns, empty
   so the acceptance drill compares like with like. The value is still sent (older loggers ignore the bit). */
#define BL_F_VIN_CLIP  0x40U   /* the charger input (PA10) clipped: above about 3 x VDDA */
#define BL_F_ISET_CLIP 0x80U   /* ISET (PB1) clipped */

typedef struct {
  uint8_t flags;
  uint32_t seq, uptime_s;
  int32_t vout_uv, ishunt_ua, iset_uv, iset_min_uv, iset_max_uv, ina_die_mc;
  int32_t vcell_uv, soc_mpct, crate_mpct_h, sht_t_mc, sht_rh_mpct, vin_uv;
  uint8_t samples, misses;
  uint8_t reset_cause, faults;
  uint16_t boots, tx_timeouts, i2c_restarts, i2c_unsticks;
  uint32_t fault_pc;
} bl_reading;

uint16_t bl_crc16(const uint8_t *p, unsigned n);
void bl_pack(const bl_reading *r, uint8_t out[BL_PKT_LEN]);
/* 0 and *r filled when the magic, version and CRC are right; -1 otherwise. */
int bl_unpack(const uint8_t *in, unsigned n, bl_reading *r);

/* SHT45 (Sensirion datasheet 4.4/4.6): CRC-8 polynomial 0x31, init 0xFF over each 2-byte word; and the
   conversions to m degC and milli-percent RH (RH clamped to 0..100 %). */
uint8_t sht45_crc8(const uint8_t *p, unsigned n);
int32_t sht45_t_mc(uint16_t raw);
int32_t sht45_rh_mpct(uint16_t raw);

#endif
