/* The bench telemetry packet (README.md): one every 5 s from the TX, plain LoRa, test only. Pure C, so
 * the host tests (tests/test_benchlink.py) check the layout against the logger's decoder.
 * Little endian, 78 bytes (version 3; version 2 was bytes 0..61 and its CRC at 62):
 *    0  'W' 'B'  magic
 *    2  u8   version (BL_VERSION)
 *    3  u8   flags (BL_F_*)
 *    4  u32  seq: packets sent since boot
 *    8  u32  uptime, s since power-on: the RTC tick count (1/1024 s, HAL_GetTick() on this board), which
 *            keeps counting through a reset and restarts only when the board loses power; wraps at 48.5 days
 *   12  i32  INA228 VBUS, uV: the charger's OUT (VBUS jumpered to the OUT column)
 *   16  i32  INA228 shunt current, uA, mean of the interval: + = into VIN+, out through VIN-
 *   20  i32  ISET mean, uV: the bq24074's charge current, I = 400 * V_ISET / R_ISET (TI SLUS810 eq. 3)
 *   24  i32  ISET minimum, uV
 *   28  i32  ISET maximum, uV
 *   32  i32  INA228 die temperature, m degC
 *   36  i32  MAX17048 VCELL, uV
 *   40  i32  MAX17048 SOC, milli-percent
 *   44  i32  MAX17048 CRATE, milli-percent an hour
 *   48  i32  SHT45 temperature, m degC
 *   52  i32  SHT45 relative humidity, milli-percent
 *   56  i32  the charger's input (VBUS), uV: A2 (PA10) through a 20k/10k divider, times 3
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
#define BL_VERSION 3U

#define BL_F_INA    0x01U   /* the INA228 answered with its ids */
#define BL_F_GAUGE  0x02U   /* the MAX17048 answered with its version */
#define BL_F_SHT    0x04U   /* the SHT45 measured with good CRCs */
#define BL_F_PGOOD  0x08U   /* the bq24074 PGOOD pin is low (asserted) */
#define BL_F_CHG    0x10U   /* the bq24074 CHG pin is low (asserted) */
#define BL_F_ADC    0x20U   /* the ISET and input readings are valid */

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
