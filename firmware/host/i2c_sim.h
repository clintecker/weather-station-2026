#ifndef HOST_I2C_SIM_H
#define HOST_I2C_SIM_H
/* A host model of the I2C2 bus with many devices (firmware/host/i2c_sim.c), for App/i2c_bus.c and
 * the local WSMP modules. It stands in for ST's HAL I2C, GPIO and NVIC calls. A device answers at its
 * 7-bit address; its model (firmware/host/i2c_models.c, a switch on the kind) gives the bytes. Faults:
 * an address NACK, a NACK after the address, a transfer that never completes, a latency, and SDA held
 * low until a number of SCL rising edges during the recovery. */
#include <stdint.h>
#include "sim_core.h"

enum i2c_sim_kind { DEVK_TEST = 1, DEVK_SHT45, DEVK_SHTC3, DEVK_BMP581, DEVK_LTR390, DEVK_INA228, DEVK_MAX17048 };
enum i2c_sim_mode { DM_OK, DM_NACK_ADDR, DM_NACK_DATA, DM_HANG, DM_BUSY, DM_HANG_READ,
                    DM_BUS_ERROR };   /* a bus error (HAL_I2C_ERROR_BERR), as noise or a misplaced START gives */
#define I2C_SIM_DEVICES 8
#define I2C_SIM_BUF 16

int i2c_sim_add(int kind, uint8_t addr7);   /* returns the device index, or -1 */
void i2c_sim_remove(int dev);               /* unplugged: no answer at its address */
void i2c_sim_restore(int dev);              /* plugged in again */
void i2c_sim_mode(int dev, int mode, int sda_hold_edges, uint32_t latency_ms);
extern const sim_source i2c_sim_source;

/* Counters and state for the tests. */
uint32_t i2c_sim_transfers(void);
uint32_t i2c_sim_addr_transfers(int addr7);
uint32_t i2c_sim_writes(int dev);          /* write attempts addressed to one device */
uint32_t i2c_sim_deinits(void);
int i2c_sim_scl_edges(void);
int i2c_sim_ready(void);
int i2c_sim_pin_errors(void);
int i2c_sim_power(void);                    /* the PA9 sensor supply: 1 on */
int i2c_sim_complete_at_guard(int error);   /* the transfer in flight ends when its 30 ms guard expires */

/* The device models (firmware/host/i2c_models.c). Each returns 0, or -1 for a NACK of the data. */
int model_write(int kind, int dev, const uint8_t *data, uint16_t n);
int model_read(int kind, int dev, uint8_t *data, uint16_t n);
int model_mem_read(int kind, int dev, uint8_t reg, uint8_t *data, uint16_t n);
void model_reset(int kind, int dev);
/* The SHT45 model: the raw words it answers, a bad RH checksum, and whether a read came too early. */
void model_sht45_set(int dev, uint16_t t_raw, uint16_t rh_raw, int bad_crc);
int model_sht45_read_too_early(void);
int model_sht45_commands(void);   /* measure commands that reached an SHT45 */
void model_shtc3_set(int dev, uint16_t t_raw, uint16_t rh_raw);
int model_shtc3_asleep(int dev);
void model_reg_set_id(int dev, uint8_t id);
void model_reg_power_cycle(int dev);
void model_reg_set_data(int dev, uint32_t data);
void model_ina228_set(int dev, int32_t uv, int32_t ua);
void model_ina228_power_cycle(int dev);
void model_max17048_set(int dev, uint8_t soc);
#endif
