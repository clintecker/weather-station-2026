#ifndef SENSOR_H
#define SENSOR_H
#include <stdint.h>
/* SHT45 on I2C2: SDA = PA11 (CN5.9 / morpho CN10.5), SCL = PA12 (CN5.10 / CN10.3), per UM2592
 * Rev 4 Tables 17-18. 100 kHz, open-drain. The Adafruit 6174 breakout carries the real 10 kOhm
 * pull-ups; the MCU's internal pull-ups are on only so an unplugged sensor reads as a NACK. */
void sensor_init(void);
/* Return codes, printed as rc= on #sample: 0 ok (CRC-checked), -2 address NACK (sensor absent
 * or wiring), -3 read NACK, -4 CRC mismatch (noise, cable), -5 bus still stuck after recovery.
 * On any fault the outputs are untouched. */
#define SENSOR_BUS_STUCK (-5)
int sensor_read(int16_t *centi_c, uint16_t *centi_rh);
#endif
