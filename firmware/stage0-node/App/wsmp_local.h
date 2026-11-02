#ifndef WSMP_LOCAL_H
#define WSMP_LOCAL_H
/* The station's local WSMP modules (docs/module-protocol.md section 10): one port for each module
 * type of the bench station. Each operation is a switch on the port (no function pointers, Power of
 * Ten rule 9). Every operation runs in the main loop.
 * P_BATTERY (5, type 8) and P_RAILS (8, type 9) are the base-board power modules (App/mod_power.h),
 * present in every power profile (docs/superpowers/specs/2026-10-29-power-telemetry-design.md
 * section 8.4). Port 5 was P_POWER (type 5, battery and charger) up to protocol version 5. */
#include <stdint.h>
#include "wsmp.h"

enum wsmp_port { P_AIR_TH = 1, P_PRESSURE, P_UVA, P_ENCL_TH, P_BATTERY, P_WIND, P_RAIN, P_RAILS, P_COUNT };
#define WSMP_TICK_MS 250U        /* the station calls local_tick for every port this often */
#define WSMP_SAMPLE_MS 15000U    /* the temperature, humidity, pressure and UVA modules sample this often */

/* Starts every local module. boot_id is the station's boot epoch (WSMP-I2). */
void local_init(uint32_t boot_id, uint32_t now_ms);
/* One step of the module's own schedule: sampling and the probe that goes with it. */
void local_tick(enum wsmp_port p, uint32_t now_ms);
/* The latest probe: 1 present, 0 absent, -1 bus fault. seq changes with every probe. */
int local_probe_result(enum wsmp_port p, uint16_t *seq);
/* The identity and descriptor blocks, byte for byte as WSMP section 6 defines them. */
void local_identity(enum wsmp_port p, uint8_t id[WSMP_IDENTITY_LEN], uint8_t desc[WSMP_DESC_BLOCK_LEN]);
/* WSMP-L1 to L3: freeze the snapshot, start the next window. A repeated token is a retry. */
void local_latch(enum wsmp_port p, uint16_t token, uint32_t utc, uint32_t now_ms);
/* Binds a port module's driver to a newly admitted module (sensor module ports design, section 6.7):
   its window starts afresh, boot_id is its boot ID, and applied (the module's record when its status
   is applied, else NULL) gives its calibration. A port without a port-module driver ignores it. */
void local_bind(enum wsmp_port p, const wsmp_record *applied, uint32_t boot_id, uint32_t now_ms);
uint32_t local_boot_epoch(void);   /* the station's boot epoch of local_init */
/* A port module's new boot ID without a new window: a matched identity check cleared its possibly-
   replugged flag (section 6.7). */
void local_set_boot(enum wsmp_port p, uint32_t boot_id);
/* The identity an I2C port module was admitted with (section 6.7): its serial, the identity flags
   (wsmp_id_flags) and the capabilities (bit 0: a valid record). The identity block carries them. */
void local_set_identity(enum wsmp_port p, uint64_t serial, uint16_t id_flags, uint16_t caps);
/* The driver of a port module while an identity read runs (App/port_id.c): held, it starts no new
   sample; idle, it has no step in progress. The ID check is a step of the driver from idle: the
   SHT45's serial read (0x89), or the chip ID register of the BMP581 and LTR390. Its result: 0 while
   it runs, 1 the part (with *serial for a part that has one), I2C_EID another chip, or the bus code. */
void local_hold(enum wsmp_port p, int on);
int local_idle(enum wsmp_port p);
void local_id_check(enum wsmp_port p);
int local_id_result(enum wsmp_port p, uint32_t *serial);
int local_has_sensor_serial(enum wsmp_port p);
uint16_t local_type(enum wsmp_port p);   /* the module type the port's probe finds */
/* The frozen snapshot of the last latch. */
void local_snapshot(enum wsmp_port p, uint8_t snap[WSMP_SNAPSHOT_LEN]);

/* The serial number of a local module: never 0, unique for each port and type of one station. A port
   whose module type changes starts a new serial, so a new counter series (WSMP-C3): port 5 went from
   type 5 to type 8 (0x575300000505 to 0x575300000508) with protocol version 6, and port 8 is new
   (0x575300000809). */
#define WSMP_LOCAL_SERIAL(port, type) (0x575300000000ULL | (uint64_t)(port) << 8 | (uint64_t)(type))
/* The identity block of a local module (schema 1, firmware 1.0) whose packed descriptor block is desc. */
void local_pack_identity(enum wsmp_port p, uint16_t type, uint8_t channels, uint32_t boot_id,
                         const uint8_t desc[WSMP_DESC_BLOCK_LEN], uint8_t id[WSMP_IDENTITY_LEN]);
#endif
