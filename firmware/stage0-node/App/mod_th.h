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
/* Binds the unit to a newly admitted module (sensor module ports design, section 6.7): a fresh window,
   the module's boot ID, and the calibration of applied, the module's record if its status is applied, else NULL. The
   enclosure sensor is on the base, not a port module: it takes no calibration. */
void mod_th_bind(enum th_unit u, const wsmp_record *applied, uint32_t boot_id, uint32_t now_ms);
/* While held the unit starts no new sample (a sample due waits, its phase kept); a step in progress
   finishes. Idle: no step in progress. An identity read holds the unit and waits for idle. */
void mod_th_hold(enum th_unit u, int on);
void mod_th_set_boot(enum th_unit u, uint32_t boot_id);   /* a new boot ID, the window kept */
int mod_th_idle(enum th_unit u);
/* The SHT45's own serial (command 0x89), read as a step of the driver's step machine, started only
   from its idle state, so never between a measure command and its read (section 6.7). A sample that
   falls due meanwhile waits for it and keeps its phase. */
void mod_th_serial_request(enum th_unit u);
/* 1 with *serial once the read is done, 0 while it waits or runs, or the failure (I2C_E*). A failed
   read is not a probe: it changes no presence. */
int mod_th_serial_result(enum th_unit u, uint32_t *serial);
/* SHTC3 datasheet section 5.11, in 0.01 units rounded half up: 0, or I2C_ECRC on a CRC mismatch. */
int mod_shtc3_parse(const uint8_t reply[6], int16_t *centi_c, uint16_t *centi_rh);
#endif
