#ifndef PORT_ID_H
#define PORT_ID_H
/* The identity reads of an I2C port module (firmware-current-design.md, section 6.7): the module
 * record at 0x50 on the port's mux channel, the sensor's own serial, and the holder check. Each runs
 * across steps, never waits, and holds the port's driver in its idle state while it runs, so an
 * identity read is never between a measure command and its read (the SHT45's 0x89 is the driver's
 * own step). A sample that falls due meanwhile waits and keeps its phase. */
#include <stdint.h>
#include "wsmp_ident.h"
#include "wsmp_local.h"
#include "i2c_bus.h"

/* What a holder check and an identity check compare: the identity seen at the module's admission.
   serial is the record's serial (with_record), id_serial the verdict's (any source), status the record
   status, rec_crc the record's stored CRC (0x7C) and img_crc the CRC-32C of the 128 bytes read. */
typedef struct {
  uint64_t serial, id_serial;
  uint32_t sensor_serial, rec_crc, img_crc;
  uint8_t with_record, has_sensor_serial, status;
} port_id_expect;

enum { PORT_ID_BUSY, PORT_ID_DONE };
enum { PORT_ID_PRESENT, PORT_ID_GONE };
/* The outcome of an identity check (section 6.7, "Outcome of a check"). */
enum { PORT_ID_CHECKING, PORT_ID_MATCHED, PORT_ID_CHANGED, PORT_ID_UNVERIFIED };

int port_id_is_port(enum wsmp_port p);   /* 1 for an I2C port module (ports 1-8 of the design) */
void port_id_init(void);
/* The identification of a newly probed module: the record (3 tries back to back, a CRC failure read
   once more), then the sensor serial if the part has one (3 tries back to back). */
void port_id_identify(enum wsmp_port p);
/* The holder check of the module admitted on p with the identity e (section 6.7, "Checking the
   holder"): gone only on two address NACKs back to back, a different part, or a confirmed different
   identity; present otherwise (a failed read is not absence). */
void port_id_holder(enum wsmp_port p, const port_id_expect *e);
void port_id_tick(enum wsmp_port p);     /* every module tick, after the driver's */
int port_id_state(enum wsmp_port p);
/* After an identification: 1 if it is incomplete (the sensor serial failed 3 tries back to back), so
   no verdict may be decided from it (a read error is not a verdict); identify again later. */
int port_id_incomplete(enum wsmp_port p);
/* After an identification: what it saw, for wsmp_identify. o->record points into the port's buffer,
   valid until the port's next identity read. */
void port_id_observed(enum wsmp_port p, wsmp_observed *o);
int port_id_holder_result(enum wsmp_port p);
/* The pre-latch slot of the port (section 6.7): on, the driver starts no new sample (a sample due
   waits, its phase kept) and no identification or holder check begins; one asked for waits until the
   slot ends. */
void port_id_slot(enum wsmp_port p, int on);
/* The identity check of the module admitted on p with the identity e: from the driver's idle state,
   before any identification or holder check that has not begun. The parts: the sensor serial (a
   different one read twice), then the record as admission saw it (applied or SENSOR_CHANGED: the
   serial at 0x0C and the CRC at 0x7C, a difference confirmed by a full read that is a valid record,
   or by two full reads that agree with each other on an invalid image or a NACK; READ: a NACK at 0x50
   agrees, a valid record is a change; a content NO_RECORD or CAL_REJECTED: the CRC-32C of the whole
   image, a different one read twice and parsed as at admission). */
void port_id_check(enum wsmp_port p, const port_id_expect *e);
/* The check's outcome: PORT_ID_CHECKING until it is done. port_id_check_end forgets it (the latch). */
int port_id_check_result(enum wsmp_port p);
void port_id_check_end(enum wsmp_port p);
void port_id_i2c_done(enum wsmp_port p, int rc);
/* The port's record client (0x50 on its channel). */
enum i2c_client port_id_client(enum wsmp_port p);
/* PODWRITE (App/pod_write.c) has the port: on, no identification, holder check or identity check
   begins, and the driver is held; one already past its start runs on. */
void port_id_lock(enum wsmp_port p, int on);
/* 1 when no identity read of the port is past its start: the record client and the driver are free. */
int port_id_quiet(enum wsmp_port p);
#endif
