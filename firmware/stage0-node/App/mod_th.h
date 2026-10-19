#ifndef MOD_TH_H
#define MOD_TH_H
/* The two temperature and humidity modules (WSMP module types 1 and 4): the SHT45 for the outside
 * air and the SHTC3 in the enclosure. Each samples every 15 s on the module tick, in steps that never
 * wait, and keeps the means of its window (App/wsmp_local.h has the operations). */
#include <stdint.h>
#include "wsmp.h"

enum th_unit { TH_AIR, TH_ENCL, TH_COUNT };

void mod_th_init(uint32_t boot_id, uint32_t now_ms);
void mod_th_tick(enum th_unit u, uint32_t now_ms);
int mod_th_probe(enum th_unit u, uint16_t *seq);
void mod_th_identity(enum th_unit u, uint8_t id[WSMP_IDENTITY_LEN], uint8_t desc[WSMP_DESC_BLOCK_LEN]);
void mod_th_latch(enum th_unit u, uint16_t token, uint32_t now_ms);
void mod_th_snapshot(enum th_unit u, uint8_t snap[WSMP_SNAPSHOT_LEN]);
void mod_th_i2c_done(enum th_unit u, int rc);
/* SHTC3 datasheet section 5.11, in 0.01 units rounded half up: 0, or I2C_ECRC on a CRC mismatch. */
int mod_shtc3_parse(const uint8_t reply[6], int16_t *centi_c, uint16_t *centi_rh);
#endif
