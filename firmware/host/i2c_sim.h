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
enum i2c_sim_mode { DM_OK, DM_NACK_ADDR, DM_NACK_DATA, DM_HANG, DM_BUSY, DM_HANG_READ };
#define I2C_SIM_DEVICES 8
#define I2C_SIM_BUF 16

int i2c_sim_add(int kind, uint8_t addr7);   /* returns the device index, or -1 */
void i2c_sim_remove(int dev);               /* unplugged: no answer at its address */
void i2c_sim_mode(int dev, int mode, int sda_hold_edges, uint32_t latency_ms);
extern const sim_source i2c_sim_source;

/* Counters and state for the tests. */
uint32_t i2c_sim_transfers(void);
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
#endif
