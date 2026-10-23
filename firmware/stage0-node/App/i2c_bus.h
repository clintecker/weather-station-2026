#ifndef I2C_BUS_H
#define I2C_BUS_H
/* The shared I2C2 bus of the station's local WSMP modules (App/i2c_bus.lit.md): PA11 SDA, PA12 SCL,
 * 100 kHz. One transfer is on the bus at a time, in submission order, each with a guard of 30 ms
 * plus 90 us a byte. After a transfer that may leave the bus stuck (a timeout, a bus error, a HAL
 * refusal, or SDA still low) the bus runs the stuck-bus recovery before the next transfer. A clean
 * NACK costs none. Nothing waits.
 * Phase 1 of the sensor module ports (docs/superpowers/specs/2026-10-21-sensor-module-ports-design.md
 * sections 4.3, 6.5, 6.6): a mux at I2C_MUX_ADDR and a static channel map. A port client's transfer
 * is preceded by its channel's select and read-back and followed by the deselect (0x00) and its
 * read-back; upstream clients are served only with no channel selected. At boot, before any client:
 * a mux RESET pulse, the deselect and its read-back, then the phantom check. */
#include <stdint.h>

/* One client for each I2C module. A client has at most one transfer queued or running. */
enum i2c_client { I2C_C_SHT45, I2C_C_BMP581, I2C_C_LTR390, I2C_C_SHTC3, I2C_C_INA228, I2C_C_MAX17048, I2C_C_COUNT };

#define I2C_MUX_ADDR 0x71U   /* not the default 0x70: the SHTC3 is there (ports design, section 3) */
#define I2C_RX_MAX 128U      /* the longest read: a whole module record (section 6.9) */

/* Completion codes. A module adds its own I2C_ECRC after a bad checksum. */
#define I2C_OK          0
#define I2C_ENACK_ADDR (-2)   /* no acknowledge of the address or the command: absent, or not ready */
#define I2C_ENACK_DATA (-3)   /* the read failed after the address */
#define I2C_ECRC       (-4)
#define I2C_ESTUCK     (-5)   /* SDA still low after the recovery */
#define I2C_ETIMEOUT   (-6)   /* the transfer did not finish within its guard */
#define I2C_EBUS       (-7)   /* a bus error, lost arbitration, a HAL refusal, or a mux that did not take
                                 the channel: a bus fault, not an absence */

/* The phantom table: the port probe table and the record EEPROM (section 6.7), probed at boot with
   every channel deselected. Bit i of i2c_bus_phantoms is address i: it answered upstream (PORT-15),
   so the port client at it is refused for the boot (I2C_ENACK_ADDR, no bus traffic). */
enum { I2C_PH_SHT45, I2C_PH_BMP581, I2C_PH_LTR390, I2C_PH_EEPROM, I2C_PHANTOM_COUNT };

void i2c_bus_init(void);   /* also starts the boot job */
/* Queues one transfer of client c to the 7-bit address addr7:
 *   txlen > 0, rxlen == 0: write tx (a command or a register write);
 *   txlen == 0, 0 < rxlen <= I2C_RX_MAX: read rxlen bytes;
 *   txlen == 1, 0 < rxlen <= I2C_RX_MAX: write the register address tx[0], then read (repeated start);
 *   txlen == 2, 0 < rxlen <= I2C_RX_MAX: write the word address tx[0] tx[1] (high byte first), then
 *     read (repeated start): the 24LC32A;
 *   txlen == 0, rxlen == 0: no transfer, only the stuck-bus recovery (rc 0 or I2C_ESTUCK).
 * Both buffers must stay valid until the completion. Returns 0 (queued), or -1 if c already has a
 * transfer or the form is not one of the five. */
int i2c_bus_submit(enum i2c_client c, uint8_t addr7, const uint8_t *tx, uint8_t txlen, uint8_t *rx, uint16_t rxlen);
/* The completion of client c's transfer, from the main loop (a link-time seam, Power of Ten rule 9):
   the module layer defines it (App/wsmp_local.c). It may submit the next transfer. */
void i2c_bus_done(enum i2c_client c, int rc);
/* The sensor 3.3 V switch on PA9 (only on the protoboard, a no-op on the breadboard). */
void i2c_bus_power(int on);
/* The mux RESET line, active low on the TCA9548A (a link-time seam): asserted 1, released 0. The
   board defines it; its pin is TBD (ports design, section 4.1). */
void i2c_bus_mux_reset_line(int asserted);
int i2c_bus_ready(void);           /* 1 once the boot job is done */
int i2c_bus_mux_ok(void);          /* 0 after a mux write that did not read back, until one does */
uint8_t i2c_bus_phantoms(void);    /* the phantom check's result, a bit for each I2C_PH_* address */
#endif
