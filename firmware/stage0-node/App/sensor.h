#ifndef SENSOR_H
#define SENSOR_H
#include <stdint.h>
/* SHT45 on I2C2: SDA = PA11 (CN5.9, D14), SCL = PA12 (CN5.10, D15), per UM2592 Rev 4
 * Table 17. 100 kHz, open-drain, MCU pull-ups off (the Adafruit 6174 breakout has them). */
void sensor_init(void);
/* 0 and outputs set on a CRC-checked reading; nonzero (outputs untouched) on any fault. */
int sensor_read(int16_t *centi_c, uint16_t *centi_rh);
#endif
