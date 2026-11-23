#ifndef POD_WRITE_H
#define POD_WRITE_H
/* PODWRITE: write a port module's ID record (firmware-current-design.md section 6.9) into its 24LC32 at
 * 0x50 on the port's mux channel, then read it back and check it (App/pod_write.c). It's how a pod built
 * from hardware/pods-r1 gets its identity; tools/podwrite.py draws the serial and keeps the ledger.
 *
 * The job runs on the port's record client in steps (bus completions and module ticks); nothing waits.
 * It locks the port's identity reads (port_id_lock) and holds the driver, then: reads the EEPROM and
 * refuses one that already holds a valid record; for a type with a sensor serial (the SHT45) reads it
 * for the sensor bind; packs the record and checks it parses as the station would; writes it in four
 * 32-byte pages, each followed by acknowledge polling for the write cycle; reads all 128 bytes back
 * and compares them. The EEPROM's WP must be open (the pod's JP1 shunt off), or the verify fails. */
#include <stdint.h>
#include "wsmp.h"
#include "wsmp_local.h"

#define POD_WRITE_CONFIRM "WRITE-POD-RECORD"   /* the token the console line must end with */
#define POD_WRITE_HW_REV 1U                    /* hardware/pods-r1 */

/* What a finished job reports (pod_write_report). */
enum pod_write_outcome { PW_OK, PW_HAS_RECORD, PW_NO_EEPROM, PW_NO_SERIAL, PW_WRITE, PW_TIMEOUT, PW_VERIFY,
                         PW_OUTCOME_COUNT };
/* Why pod_write_start refused: 0 started, else one of these. */
enum { PW_START_OK, PW_START_BUSY, PW_START_PORT, PW_START_TYPE, PW_START_SERIAL };

typedef struct {
  uint8_t port, outcome;
  uint16_t type;
  uint64_t serial;
  uint32_t bind_value, crc;
  uint8_t image[WSMP_RECORD_LEN];   /* the record as written (valid when outcome is PW_OK or PW_VERIFY) */
} pod_write_result;

/* "<port> <type> <serial: 16 hex> WRITE-POD-RECORD", the arguments after "PODWRITE ": 0 and the three
   values, or -1 for anything else (a missing or different token, extra text, a field out of range). */
int pod_write_parse(const char *args, unsigned *port, unsigned *type, uint64_t *serial);
/* Starts the job: the port must be an I2C port module (port_id_is_port) whose type is type, and the
   serial a record serial (top byte 0x01, its low 56 bits neither 0 nor all ones). utc is the
   programming time written in the record (0 while the time is unknown). */
int pod_write_start(enum wsmp_port p, uint16_t type, uint64_t serial, uint32_t utc);
int pod_write_busy(void);                        /* 1 while a job runs, on any port */
int pod_write_owns(enum wsmp_port p);            /* 1 while the port's record client is the job's */
void pod_write_tick(enum wsmp_port p);           /* every module tick (from port_id_tick) */
void pod_write_i2c_done(enum wsmp_port p, int rc);
/* The finished job, from the main loop (a link-time seam): App/tx_console.c prints it. */
void pod_write_report(const pod_write_result *r);
#endif
