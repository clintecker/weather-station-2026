#ifndef WSMP_HOST_H
#define WSMP_HOST_H
/* The station side of WSMP (docs/module-protocol.md section 7, App/wsmp_host.lit.md): one state for
 * each local port, the probes, admission against the registry and the radio budget, the minute latch
 * and the flap limit. Every function runs in the main loop. */
#include <stdint.h>
#include "wsmp.h"
#include "wsmp_local.h"

enum wsmp_host_state { WH_ABSENT, WH_PROBING, WH_IDENTIFYING, WH_ADMITTED, WH_ACTIVE, WH_SUSPECT, WH_QUARANTINED, WH_REFUSED };

void wsmp_host_init(void);                       /* after local_init: every port Absent */
void wsmp_host_tick(uint32_t now_ms);            /* every WSMP_TICK_MS: module ticks and probes */
void wsmp_host_latch(uint32_t utc, uint32_t now_ms);   /* the minute latch of every port in the layout */
/* When the next latch is due (the latch timer's): the pre-latch slot starts WSMP_HOST_SLOT_MS before it
   (sensor module ports design, section 6.7). wsmp_host_latch also sets it a minute on. */
void wsmp_host_next_latch(uint32_t at_ms);
/* The last snapshot of a port in the layout (Active or Suspect), or NULL. */
const wsmp_snapshot *wsmp_host_snapshot(enum wsmp_port p);
int wsmp_host_state(enum wsmp_port p);
/* Checks a module's blocks against the registry and the budget: WH_ADMITTED, WH_REFUSED (over the
   budget) or WH_QUARANTINED (bad identity or descriptors). wsmp_host_tick calls it after two probes. */
int wsmp_host_admit(enum wsmp_port p, const uint8_t id[WSMP_IDENTITY_LEN], const uint8_t desc[WSMP_DESC_BLOCK_LEN]);
uint32_t wsmp_host_changes(enum wsmp_port p);   /* how often the port joined or left the layout */
/* The MODULES console line, "#modules air_th=active ..."; returns its length (at most len - 1). */
#define WSMP_MODULES_LINE_MAX 256U   /* the longest line: every port with its longest state, the I2C ports with
                                       (incomplete=255)(unverified=255) */
unsigned wsmp_host_modules_line(char *buf, unsigned len);
/* The descriptor set of the layout (WSMP section 11.1, with the identity entry of the sensor module
   ports design, section 6.7): every Admitted, Active or Suspect port in increasing port order. The
   generation is left 0 for the caller (WSMP-E1), which builds the set after the minute's latch steps
   (wsmp_host_latch): an Admitted module joins the readings at that latch. Returns the module count;
   *dropped (if not NULL) counts layout modules whose blocks did not unpack (a bug), left out. */
unsigned wsmp_host_set(wsmp_set *set, unsigned *dropped);
/* Module i of a set as a console line, "#ident port=1 type=1 serial=<16 hex> source=record
   status=applied crc=<8 hex>"; returns its length (0 past the last module). */
#define WSMP_IDENT_LINE_MAX 112U
unsigned wsmp_host_ident_line(const wsmp_set *set, unsigned i, char *buf, unsigned len);
#endif
