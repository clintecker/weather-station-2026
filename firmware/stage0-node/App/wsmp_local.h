#ifndef WSMP_LOCAL_H
#define WSMP_LOCAL_H
/* The station's local WSMP modules (docs/module-protocol.md section 10): one port for each module
 * type of the bench station. Each operation is a switch on the port (no function pointers, Power of
 * Ten rule 9). Every operation runs in the main loop. */
#include <stdint.h>
#include "wsmp.h"

enum wsmp_port { P_AIR_TH = 1, P_PRESSURE, P_UVA, P_ENCL_TH, P_POWER, P_WIND, P_RAIN, P_COUNT };
#define WSMP_TICK_MS 250U        /* the station calls local_tick for every port this often */
#define WSMP_SAMPLE_MS 15000U    /* the temperature, humidity, pressure and UVA modules sample this often */

/* Starts every local module. boot_id is the station's boot epoch (WSMP-I2). */
void local_init(uint32_t boot_id);
/* One step of the module's own schedule: sampling and the probe that goes with it. */
void local_tick(enum wsmp_port p, uint32_t now_ms);
/* The latest probe: 1 present, 0 absent, -1 bus fault. seq changes with every probe. */
int local_probe_result(enum wsmp_port p, uint16_t *seq);
/* The identity and descriptor blocks, byte for byte as WSMP section 6 defines them. */
void local_identity(enum wsmp_port p, uint8_t id[WSMP_IDENTITY_LEN], uint8_t desc[WSMP_DESC_BLOCK_LEN]);
/* WSMP-L1 to L3: freeze the snapshot, start the next window. A repeated token is a retry. */
void local_latch(enum wsmp_port p, uint16_t token, uint32_t utc, uint32_t now_ms);
/* The frozen snapshot of the last latch. */
void local_snapshot(enum wsmp_port p, uint8_t snap[WSMP_SNAPSHOT_LEN]);

/* The serial number of a local module: never 0, unique for each port and type of one station. */
#define WSMP_LOCAL_SERIAL(port, type) (0x575300000000ULL | (uint64_t)(port) << 8 | (uint64_t)(type))
#endif
