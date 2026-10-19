#ifndef I2C_BUS_H
#define I2C_BUS_H
/* The shared I2C2 bus of the station's local WSMP modules (App/i2c_bus.lit.md): PA11 SDA, PA12 SCL,
 * 100 kHz. One transfer is on the bus at a time, in submission order, each with a 30 ms guard. After
 * a transfer that may leave the bus stuck (a timeout, a bus error, a HAL refusal, or SDA still low) the bus runs
 * the stuck-bus recovery before the next transfer. A clean NACK costs none. Nothing waits. */
#include <stdint.h>

/* One client for each I2C module. A client has at most one transfer queued or running. */
enum i2c_client { I2C_C_SHT45, I2C_C_BMP581, I2C_C_LTR390, I2C_C_SHTC3, I2C_C_INA228, I2C_C_MAX17048, I2C_C_COUNT };

/* Completion codes. A module adds its own I2C_ECRC after a bad checksum. */
#define I2C_OK          0
#define I2C_ENACK_ADDR (-2)   /* no acknowledge of the address or the command: absent, or not ready */
#define I2C_ENACK_DATA (-3)   /* the read failed after the address */
#define I2C_ECRC       (-4)
#define I2C_ESTUCK     (-5)   /* SDA still low after the recovery */
#define I2C_ETIMEOUT   (-6)   /* the transfer did not finish within its guard */
#define I2C_EBUS       (-7)   /* a bus error, lost arbitration, or a HAL refusal: a bus fault, not an absence */

void i2c_bus_init(void);
/* Queues one transfer of client c to the 7-bit address addr7:
 *   txlen > 0, rxlen == 0: write tx (a command or a register write);
 *   txlen == 0, rxlen > 0: read rxlen bytes;
 *   txlen == 1, rxlen > 0: write the register address tx[0], then read rxlen bytes (repeated start);
 *   txlen == 0, rxlen == 0: no transfer, only the stuck-bus recovery (rc 0 or I2C_ESTUCK).
 * Both buffers must stay valid until the completion. Returns 0 (queued), or -1 if c already has a
 * transfer or the form is not one of the four. */
int i2c_bus_submit(enum i2c_client c, uint8_t addr7, const uint8_t *tx, uint8_t txlen, uint8_t *rx, uint8_t rxlen);
/* The completion of client c's transfer, from the main loop (a link-time seam, Power of Ten rule 9):
   the module layer defines it (App/wsmp_local.c). It may submit the next transfer. */
void i2c_bus_done(enum i2c_client c, int rc);
/* The sensor 3.3 V switch on PA9 (only on the protoboard, a no-op on the breadboard). */
void i2c_bus_power(int on);
#endif
