#ifndef I2C_BUS_H
#define I2C_BUS_H
/* The shared I2C2 bus of the station's local WSMP modules (App/i2c_bus.lit.md): PA11 SDA, PA12 SCL,
 * 100 kHz. One transfer is on the bus at a time, in submission order, each with a guard of 30 ms
 * plus 90 us a byte. After a transfer that may leave the bus stuck (a timeout, a bus error, a HAL
 * refusal, or SDA still low) the bus runs the stuck-bus recovery before the next transfer. A clean
 * NACK costs none. Nothing waits.
 * The bus profile (WS_I2C_MUX, i2c_bus.lit.md section 11; power telemetry spec section 9.1):
 *   0 (the firmware default, the official phase A wiring): a passive STEMMA QT hub, no mux. Every
 *     client is upstream; there is no mux boot job, no deselect and no phantom check, and the record
 *     clients (0x50) complete with I2C_ENACK_ADDR without bus traffic (no record EEPROMs on the hub).
 *   1: phase 1 of the sensor module ports (docs/firmware-current-design.md
 *     sections 4.3, 6.5, 6.6): a mux at I2C_MUX_ADDR and a static channel map. A port client's
 *     transfer is preceded by its channel's select and read-back and followed by the deselect (0x00)
 *     and its read-back; upstream clients are served only with no channel selected. At boot, before
 *     any client: a mux RESET pulse, the deselect and its read-back, then the phantom check. */
#include <stdint.h>

#ifndef WS_I2C_MUX
#define WS_I2C_MUX 0   /* the STEMMA QT hub; host builds that test the mux pass -DWS_I2C_MUX=1 */
#endif

/* One client for each I2C part, and one for each port module's record EEPROM (0x50 on the port's
   channel). A client has at most one transfer queued or running. The four INA228 rail monitors
   (power telemetry spec section 9.2) are upstream in both profiles: I2C_C_INA228 the battery (0x40),
   then the load (0x41), solar (0x45) and USB-C (0x48) rails. I2C_C_INA228 to I2C_C_MAX17048 stay one
   run: the power module's clients (wsmp_local.c routes the run). I2C_C_CHARGER, the BQ25798 (0x6B,
   upstream, phase C only), is the power module's too; it comes last so the run and the record
   clients keep their numbers (the #test lines' ack and fail bits). */
enum i2c_client { I2C_C_SHT45, I2C_C_BMP581, I2C_C_LTR390, I2C_C_SHTC3, I2C_C_INA228, I2C_C_INA_LOAD,
                  I2C_C_INA_SOLAR, I2C_C_INA_USB, I2C_C_MAX17048, I2C_C_REC_AIR, I2C_C_REC_PRESSURE,
                  I2C_C_REC_UVA, I2C_C_CHARGER, I2C_C_COUNT };
#define I2C_EID        (-8)   /* a module's own code: a part answered with another chip ID */

#define I2C_MUX_ADDR 0x71U   /* not the default 0x70: the SHTC3 is there (firmware-current-design.md, section 4.1) */
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
/* The sensor 3.3 V switch on PA9 (D9, CN5.2; morpho CN10.19), 1 on. Not wired: since 2026-11-02
   change C's switch is not part of the breadboard build (build-progression record section 4.6 dated
   note), so on the breadboard PA9 is unconnected and driving it does nothing. With per-port power
   it enables the ports' current-limited switches (PORT-5); the power monitors (INA228s, MAX17048) and
   the SHTC3 are unswitched (PORT-9), so a PA9 cycle never drops them. */
void i2c_bus_power(int on);
/* The mux RESET line, active low on the TCA9548A (a link-time seam): asserted 1, released 0. The
   board defines it (App/board_inputs.c): PB14 (A4, CN8.5 / morpho CN7.36; build-progression record
   N5), wired when WS_I2C_MUX=1, once A4 is checked not to be tied to SDA; a no-op in the
   hub profile. */
void i2c_bus_mux_reset_line(int asserted);
int i2c_bus_ready(void);           /* 1 once the boot job is done (at once in the hub profile) */
/* 0 until a deselect reads back 0x00, and after one that failed with its RESET retry. Always 1 in the
   hub profile: there is no channel to leave selected. */
int i2c_bus_mux_ok(void);
uint8_t i2c_bus_phantoms(void);    /* the phantom check's result, a bit for each I2C_PH_* address (0 on the hub) */
/* Counters since boot, each saturating at 0xFFFF, read from the main loop (the health report, the
   #status line). They never touch the bus. */
uint16_t i2c_bus_recoveries(void);   /* stuck-bus recoveries started, recover-only requests included */
uint16_t i2c_bus_stuck(void);        /* recoveries that ended with SDA still low (I2C_ESTUCK) */
uint16_t i2c_bus_mux_resets(void);   /* mux RESET pulses, the boot job's included; 0 in the hub profile */
/* The clients that answered and failed since the previous call, bit c for client c (enum i2c_client),
   from the main loop; the call clears both masks and never touches the bus. *acked: the client's own
   transfer completed with I2C_OK (a mux operation or a recovery never counts). *failed: its job ended
   with any other code. A client may be in both. TEST-SENSOR-POWER reads it at each PA9 edge (the
   port power-cycle test; step 1's exit 9 until 2026-11-02, build-progression record 4.6 dated note). */
void i2c_bus_outcomes(uint16_t *acked, uint16_t *failed);
#endif
