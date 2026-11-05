#ifndef MOD_REG_H
#define MOD_REG_H
/* The two register-based mean modules (WSMP module types 2 and 3): the BMP581 for the station
 * pressure and the LTR390 for UVA counts. Each sample, every 15 s, takes these steps on the module
 * tick, and none of them waits:
 *   1. read the chip ID register; a wrong ID means "absent";
 *   2. write the configuration (again every sample, so a part plugged in again is set up again);
 *   3. on a later tick, read the data registers.
 * The window and the snapshot are App/mod_mean.c's. */
#include <stdint.h>
#include "wsmp.h"

enum reg_unit { REG_PRESSURE, REG_UVA, REG_COUNT };

void mod_reg_init(uint32_t boot_id, uint32_t now_ms);
void mod_reg_tick(enum reg_unit u, uint32_t now_ms);
int mod_reg_probe(enum reg_unit u, uint16_t *seq);
void mod_reg_identity(enum reg_unit u, uint8_t id[WSMP_IDENTITY_LEN], uint8_t desc[WSMP_DESC_BLOCK_LEN]);
void mod_reg_latch(enum reg_unit u, uint16_t token, uint32_t now_ms);
void mod_reg_snapshot(enum reg_unit u, uint8_t snap[WSMP_SNAPSHOT_LEN]);
/* The latest valid sample as the window takes it (calibrated, cropped): pressure in 0.1 hPa, UVA in
   raw counts. 1 if there was one in the last 30 s of module ticks, else 0. Read-only. */
int mod_reg_live(enum reg_unit u, int32_t *value);
/* Binds the unit to a newly admitted module: a fresh window, its boot ID and the calibration of
   applied (NULL: none). */
void mod_reg_bind(enum reg_unit u, const wsmp_record *applied, uint32_t boot_id, uint32_t now_ms);
/* As mod_th's: no new sample while held; idle with no step in progress. */
void mod_reg_hold(enum reg_unit u, int on);
void mod_reg_set_boot(enum reg_unit u, uint32_t boot_id);   /* a new boot ID, the window kept */
int mod_reg_idle(enum reg_unit u);
/* The ID check of an identity read, a step from idle: the chip ID register read alone. Its result: 0
   while it waits or runs, 1 the part's ID, I2C_EID another chip, or the bus code. Never a probe. */
void mod_reg_id_check(enum reg_unit u);
int mod_reg_id_result(enum reg_unit u);
void mod_reg_i2c_done(enum reg_unit u, int rc);
#endif
