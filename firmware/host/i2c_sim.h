#ifndef HOST_I2C_SIM_H
#define HOST_I2C_SIM_H
/* A host model of the I2C2 bus with many devices (firmware/host/i2c_sim.c), for App/i2c_bus.c and
 * the local WSMP modules. It stands in for ST's HAL I2C, GPIO and NVIC calls. A device answers at its
 * 7-bit address; its model (firmware/host/i2c_models.c, a switch on the kind) gives the bytes. Faults:
 * an address NACK, a NACK after the address, a transfer that never completes, a latency, and SDA held
 * low until a number of SCL rising edges during the recovery. A device may be on the PA9 switched
 * sensor branch (i2c_sim_switched): it is off the bus while PA9 is low. The model follows the firmware's bus
 * profile, WS_I2C_MUX (App/i2c_bus.h, default 0):
 *   1, the mux: DEVK_MUX at 0x71, added with the peripheral's first start, joins a channel's devices
 *     to the bus while its bit is set; a device on no channel is upstream and always on the bus. Its
 *     RESET line (i2c_bus_mux_reset_line) clears the mask and lets a held SDA go.
 *   0, the STEMMA QT hub: no mux device, and i2c_sim_add puts every device upstream. */
#include <stdint.h>
#include "sim_core.h"

enum i2c_sim_kind { DEVK_TEST = 1, DEVK_SHT45, DEVK_SHTC3, DEVK_BMP581, DEVK_LTR390, DEVK_INA228, DEVK_MAX17048,
                    DEVK_MUX, DEVK_EEPROM, DEVK_BQ25798 };
enum i2c_sim_mode { DM_OK, DM_NACK_ADDR, DM_NACK_DATA, DM_HANG, DM_BUSY, DM_HANG_READ,
                    DM_BUS_ERROR };   /* a bus error (HAL_I2C_ERROR_BERR), as noise or a misplaced START gives */
#define I2C_SIM_DEVICES 16
#define I2C_SIM_BUF 132                     /* a whole module record and its address */
#define I2C_SIM_UPSTREAM (-1)

/* returns the device index, or -1. With the mux, a part of the probe table goes on its channel of the
   static map (0x44 channel 0, 0x53 channel 1, 0x46 and 0x47 channel 2), except the upstream kinds
   (DEVK_SHTC3, DEVK_INA228, DEVK_MAX17048, DEVK_BQ25798), which are upstream at any address, as is every other
   address. On the hub every device is upstream. */
int i2c_sim_add(int kind, uint8_t addr7);
int i2c_sim_add_on(int kind, uint8_t addr7, int channel);   /* channel 0-7, or I2C_SIM_UPSTREAM */
/* On the PA9 switched branch (per-port power, change C; not built on the breadboard since 2026-11-02,
   build-progression record 4.6 dated note): a switched device NACKs its
   address while the recorded PA9 state (i2c_sim_power) is low. A device is unswitched when added, as
   the power monitors are (the INA228s and the MAX17048, PORT-9): they answer whatever PA9 does. */
void i2c_sim_switched(int dev, int switched);
void i2c_sim_remove(int dev);               /* unplugged: no answer at its address */
void i2c_sim_restore(int dev);              /* plugged in again */
void i2c_sim_mode(int dev, int mode, int sda_hold_edges, uint32_t latency_ms);
/* One failed transfer: the n-th transfer to dev from now (1: the next) ends as mode (DM_NACK_ADDR or
   DM_BUS_ERROR) once; the ones before and after it as the device's own mode. */
void i2c_sim_fail_nth(int dev, uint32_t n, int mode);
extern const sim_source i2c_sim_source;

/* Counters and state for the tests. */
uint32_t i2c_sim_transfers(void);           /* to the parts: the mux's are not counted */
uint32_t i2c_sim_addr_transfers(int addr7);
uint32_t i2c_sim_writes(int dev);          /* write attempts addressed to one device */
uint32_t i2c_sim_deinits(void);
int i2c_sim_scl_edges(void);
int i2c_sim_ready(void);
int i2c_sim_pin_errors(void);
int i2c_sim_power(void);                    /* the PA9 sensor supply: 1 on */
int i2c_sim_complete_at_guard(int error);   /* the transfer in flight ends when its 30 ms guard expires */
int i2c_sim_addr_log(int i);                /* the address of the i-th transfer (the first 64), or -1 */
int i2c_sim_mux_device(void);               /* the mux's device index, or -1 on the hub */
uint8_t i2c_sim_mux_mask(void);
void i2c_sim_mux_set_mask(uint8_t mask);    /* the mux model's register */
uint32_t i2c_sim_mux_resets(void);          /* RESET pulses */
uint32_t i2c_sim_upstream_with_channel(void);   /* upstream parts addressed with a channel selected */

/* The device models (firmware/host/i2c_models.c). Each returns 0, or -1 for a NACK of the data. */
int model_write(int kind, int dev, const uint8_t *data, uint16_t n);
int model_read(int kind, int dev, uint8_t *data, uint16_t n);
int model_mem_read(int kind, int dev, uint16_t reg, uint8_t *data, uint16_t n);
void model_reset(int kind, int dev);
/* The SHT45 model: the raw words it answers, a bad RH checksum, and whether a read came too early. */
void model_sht45_set(int dev, uint16_t t_raw, uint16_t rh_raw, int bad_crc);
int model_sht45_read_too_early(void);
int model_sht45_commands(void);   /* measure commands that reached an SHT45 */
/* The serial its 0x89 read gives: bad 1 a bad CRC, bad 2 a NACK of the command. */
void model_sht45_set_serial(int dev, uint32_t serial, int bad);
void model_sht45_serial_fail_next(int dev, int n);   /* the next n serial replies have a bad CRC */
int model_sht45_interleaved(void);   /* a 0x89 came between a measure command and its read */
int model_sht45_serial_commands(void);   /* 0x89 commands that reached an SHT45 */
void model_shtc3_set(int dev, uint16_t t_raw, uint16_t rh_raw);
int model_shtc3_asleep(int dev);
void model_reg_set_id(int dev, uint8_t id);
void model_reg_power_cycle(int dev);
void model_reg_set_data(int dev, uint32_t data);
/* The INA228 model (i2c_models.c): each index is one part with its own shunt. uv is the bus
   voltage at VBUS, ua the true current through the shunt (+ from VIN+ to VIN-). The registers follow
   from them: VSHUNT = ua x shunt, CURRENT from VSHUNT and the SHUNT_CAL actually written (0 while it
   is 0; 1966 with the default 15 mOhm shunt gives 10 uA counts), CHARGE and ENERGY integrate CURRENT
   while the part converts. A power cycle restores the register reset values (SHUNT_CAL 0x1000). */
void model_ina228_set(int dev, int32_t uv, int32_t ua);
void model_ina228_shunt(int dev, int32_t uohm);      /* the physical shunt, micro-ohm (default 15000) */
void model_ina228_die(int dev, int32_t milli_c);     /* DIETEMP, m degC (default 25000) */
void model_ina228_power_cycle(int dev);
/* The MAX17048 model: SOC in whole % (dev), or 1/256 %; the cell voltage (uV, default 4.000 V) and
   the charge rate (m%/h, signed). The part has one address (0x36): the dev-less setters act on every
   MAX17048. */
void model_max17048_set(int dev, uint8_t soc);
void model_max17048_soc_256(uint16_t soc_256);
void model_max17048_cell(int32_t uv);
void model_max17048_rate(int32_t mpct_h);
/* DEVK_MUX: the control register is written and read back as one byte; xor spoils the read-back. */
void model_mux_readback_xor(uint8_t xor_mask);
void model_mux_readback_xor_idle(uint8_t xor_mask);   /* the read-back of mask 0 only */
int model_mux_write_count(void);
int model_mux_writes(int i);                /* the i-th value written (the first 64), or -1 */
int model_mux_reads(void);
/* DEVK_EEPROM (24LC32A, 4 KiB): a word-address read gives the image from that address; a fresh image
   is i & 0xFF at address i. */
void model_eeprom_write(int dev, uint16_t at, const uint8_t *data, uint16_t n);
void model_eeprom_fail_next(int dev, int n);      /* the next n reads NACK their data */
void model_eeprom_fail_after(int dev, int skip, int n);   /* the next skip reads are served, then n NACK */
void model_eeprom_corrupt_next(int dev, int n);   /* the next n reads that cover byte 0x20 flip a bit of it */
void model_eeprom_corrupt_at(int dev, uint16_t at, int n);   /* the same for byte at */
/* DEVK_BQ25798 (TI SLUSDV2C): the register file REG00-REG48 at power-on reset (CELL from the PROG
   strap, model_bq25798_cells, default one cell: VREG 4.2 V; ICHG 1 A; REG0F 0xA2; REG10 0xB5 (VAC_OVP 7 V);
   REG15 0xAA; REG17 0x7A; REG18 0x54; REG48
   0x19). Multi-byte reads and writes cross registers; a read past REG48 gives 0xFF, one that starts
   past it NACKs. Any write enters host mode and starts the I2C watchdog (REG10 WATCHDOG, 40 s by
   default); WD_RST restarts it and reads back 0. Its expiry resets ICHG, EN_CHG (to 1), EN_TERM and
   ADC_EN, REG17 and REG18 and sets WD_STAT. Writing ADC_EN starts a conversion that ends 300 ms later (with VBUS or VBAT
   up): the ADC registers take the physics below, ADC_DONE_STAT sets and, in one-shot mode, ADC_EN
   clears. CHG_STAT is the set stage while EN_CHG is 1 and TS is neither COLD nor HOT (nor WARM with
   JEITA_ISETH 0), else 0. EN_MPPT (REG15 bit 0) is refused without VBUS, below VSYSMIN (VBAT under 3.5 V,
   VSYS_STAT) or with EN_ICO, and cleared when VBUS goes; while set, VINDPM is VOC_PCT x VBUS. Defaults:
   VBUS 5 V, VBAT 3.8 V, VSYS 3.6 V, TS 52.0 %, die 30 degC. */
void model_bq25798_power_cycle(int dev);
void model_bq25798_cells(int dev, unsigned cells);   /* the PROG strap, applied at the next power cycle */
/* The physics: VBUS, IBUS, VBAT, IBAT (+ charging), VSYS; TS in 0.1 % of REGN; the die in 0.1 degC. */
void model_bq25798_set(int dev, int32_t vbus_mv, int32_t ibus_ma, int32_t vbat_mv, int32_t ibat_ma, int32_t vsys_mv);
void model_bq25798_ts(int dev, unsigned permille, uint8_t ts_bits);   /* ts_bits: REG1F bits 3:0, COLD COOL WARM HOT */
void model_bq25798_die(int dev, int32_t deci_c);
/* REG1B's AC1/AC2 present bits (PG and VBUS present follow VBUS above 3.4 V), the stage CHG_STAT shows
   while charge is on, and the REG20 and REG21 fault bits. */
void model_bq25798_status(int dev, int ac1, int ac2, unsigned chg_stat, uint8_t fault0, uint8_t fault1);
void model_bq25798_watchdog_expire(int dev);   /* the watchdog runs out now */
void model_bq25798_ignore_limits(int dev, int ignore);   /* writes to REG01-REG04 are dropped */
void model_bq25798_adc_stall(int dev, int stall);       /* conversions never finish (as if postponed) */
uint8_t model_bq25798_reg(int dev, uint8_t reg);   /* the register file, with no side effect */
void model_bq25798_poke(int dev, uint8_t reg, uint8_t v);   /* set a register as if the chip had */
uint32_t model_bq25798_limit_writes(int dev);       /* writes that touched REG01-REG04 */
uint32_t model_bq25798_kicks(int dev);              /* WD_RST writes */
uint32_t model_bq25798_reg_resets(int dev);         /* writes with REG09 REG_RST set (each one a full reset) */
#endif
