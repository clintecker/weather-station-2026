#ifndef WSMP_IDENT_H
#define WSMP_IDENT_H
/* The identity and admission verdict of a module found on an I2C port
 * (docs/superpowers/specs/2026-10-21-sensor-module-ports-design.md section 6.7, "Verdicts, in this
 * order"; firmware/common/wsmp_ident.lit.md). Pure: the bus reads, the holder check and the state
 * machine around it are the station's. Portable C: no HAL, no heap, no state. */
#include <stdint.h>
#include "wsmp.h"

/* The verdict. The two duplicates are not yet a refusal: the station checks the holder on
   holder_port (section 6.7, "Checking the holder"), then admits the newcomer if the holder is gone
   and refuses it (DUP_SERIAL or DUP_TYPE on the console) if the holder is present. */
enum { WSMP_V_ADMIT, WSMP_V_TYPE_CONFLICT, WSMP_V_DUP_SERIAL, WSMP_V_DUP_TYPE };

/* A module on another port: holding is 1 while it is Admitted, Active or Suspect (WSMP section 7). */
typedef struct { uint8_t port, holding; uint16_t type; uint64_t serial; } wsmp_port_held;

/* What the identification of one port saw: the probed part's type (a probe-table address answered
   with its ID check), the record read (read_ok 0 after 3 failed tries: no ACK at 0x50 or a transfer
   error), and the sensor's own serial if the part has one (the SHT4x, command 0x89). */
typedef struct {
  uint8_t port, read_ok, has_sensor_serial;
  uint16_t probed_type;
  const uint8_t *record;   /* WSMP_RECORD_LEN bytes when read_ok */
  uint32_t sensor_serial;
} wsmp_observed;

typedef struct {
  uint8_t verdict, holder_port;   /* holder_port: for the duplicates */
  uint8_t status, source, id_flags;   /* the record status and serial source (WSMP_REC_*, WSMP_SRC_*) */
  uint64_t serial;
  uint32_t record_crc;   /* the applied record's CRC-32C; 0 whenever no record is applied */
  wsmp_record record;    /* the parsed record; its calibration applies only with status WSMP_REC_APPLIED */
} wsmp_verdict;

/* Namespace 0x00: the station-bound fallback, WSMP_LOCAL_SERIAL(port, type) of wsmp_local.h. */
uint64_t wsmp_port_serial(uint8_t port, uint16_t type);
/* Namespace 0x02: the module type in bits 55-40, bits 39-32 zero, the sensor's serial in 31-0. */
uint64_t wsmp_sensor_serial(uint16_t type, uint32_t sensor_serial);
/* Steps 1-6 of the verdict order: the first that applies decides. held lists the modules of the other
   ports (an entry for o->port itself is ignored), n of them. */
void wsmp_identify(const wsmp_observed *o, const wsmp_port_held *held, unsigned n, wsmp_verdict *v);
#endif
