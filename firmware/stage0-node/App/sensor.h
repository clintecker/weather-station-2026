#ifndef SENSOR_H
#define SENSOR_H
#include <stdint.h>
/* SHT45 on I2C2: SDA = PA11 (CN5.9 / morpho CN10.5), SCL = PA12 (CN5.10 / CN10.3), per UM2592
 * Rev 4 Tables 17-18. 100 kHz, open-drain. The Adafruit 6174 breakout carries the real 10 kOhm
 * pull-ups; the MCU's internal pull-ups are on only so an unplugged sensor reads as a NACK. */
void sensor_init(void);
/* Starts one measurement and returns at once: 0, or -1 if one is still running. sensor_done() runs
 * later from the main loop (the sensor task): ~11 ms after the start, or ~15-100 ms after a
 * failure (a 30 ms guard timeout, then the bus recovery). Its rc, printed as rc= on #sample: 0 ok (CRC-checked), -1 the
 * previous measurement had not finished (app_tx.c),
 * -2 address NACK (sensor absent or wiring), -3 read NACK, -4 CRC mismatch (noise, cable),
 * -5 bus still stuck after recovery, -6 a transfer never completed. On a fault the values are 0. */
#define SENSOR_BUS_STUCK (-5)
#define SENSOR_TIMEOUT   (-6)
int sensor_start(void);
/* The measurement's result, defined by the user of the driver (App/app_tx.c; the host harnesses):
   a link-time call, not a registered function pointer (docs/power-of-ten.md rule 9). */
void sensor_done(int rc, int16_t centi_c, uint16_t centi_rh);
#endif
