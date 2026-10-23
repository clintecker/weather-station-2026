#ifndef PORT_ID_H
#define PORT_ID_H
/* The identity reads of an I2C port module (sensor module ports design, section 6.7): the module
 * record at 0x50 on the port's mux channel, the sensor's own serial, and the holder check. Each runs
 * across steps, never waits, and holds the port's driver in its idle state while it runs, so an
 * identity read is never between a measure command and its read (the SHT45's 0x89 is the driver's
 * own step). A sample that falls due meanwhile waits and keeps its phase. */
#include <stdint.h>
#include "wsmp_ident.h"
#include "wsmp_local.h"

/* What a holder check compares: the identity seen at the holder's admission. */
typedef struct { uint64_t serial; uint32_t sensor_serial; uint8_t with_record, has_sensor_serial; } port_id_expect;

enum { PORT_ID_BUSY, PORT_ID_DONE };
enum { PORT_ID_PRESENT, PORT_ID_GONE };

int port_id_is_port(enum wsmp_port p);   /* 1 for an I2C port module (ports 1-8 of the design) */
void port_id_init(void);
/* The identification of a newly probed module: the record (3 tries back to back, a CRC failure read
   once more), then the sensor serial if the part has one. */
void port_id_identify(enum wsmp_port p);
/* The holder check of the module admitted on p with the identity e (section 6.7, "Checking the
   holder"): gone only on two address NACKs back to back, a different part, or a confirmed different
   identity; present otherwise (a failed read is not absence). */
void port_id_holder(enum wsmp_port p, const port_id_expect *e);
void port_id_tick(enum wsmp_port p);     /* every module tick, after the driver's */
int port_id_state(enum wsmp_port p);
/* After an identification: what it saw, for wsmp_identify. o->record points into the port's buffer,
   valid until the port's next identity read. */
void port_id_observed(enum wsmp_port p, wsmp_observed *o);
int port_id_holder_result(enum wsmp_port p);
void port_id_i2c_done(enum wsmp_port p, int rc);
#endif
