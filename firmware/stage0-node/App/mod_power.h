#ifndef MOD_POWER_H
#define MOD_POWER_H
/* The battery and charger module (WSMP module type 5, health class): the INA228 monitor in the cell's
 * positive lead, the MAX17048 fuel gauge and the bq24074 status pins. Once a second it reads the
 * voltage and current and integrates charge and energy; every 15 s it reads the gauge. */
#include <stdint.h>
#include "wsmp.h"

#define POWER_PGOOD 0x01U   /* board_charger_pins(): PGOOD asserted (input power good) */
#define POWER_CHG   0x02U   /* board_charger_pins(): CHG asserted (charging) */
/* The bq24074 status pins, both open drain and active low, as asserted bits (a link-time seam: the
   board, App/board_inputs.c, or a host harness defines it). */
int board_charger_pins(void);

void mod_power_init(uint32_t boot_id, uint32_t now_ms);
void mod_power_tick(uint32_t now_ms);
int mod_power_probe(uint16_t *seq);
void mod_power_identity(uint8_t id[WSMP_IDENTITY_LEN], uint8_t desc[WSMP_DESC_BLOCK_LEN]);
void mod_power_latch(uint16_t token, uint32_t now_ms);
void mod_power_snapshot(uint8_t snap[WSMP_SNAPSHOT_LEN]);
void mod_power_i2c_done(int rc);   /* both of its clients: I2C_C_INA228 and I2C_C_MAX17048 */
#endif
