#ifndef TX_NODE_H
#define TX_NODE_H
#include <stdint.h>
#include "stage0.h"
/* The TX role, in modules (firmware/stage0-node/README.md, "Source files"):
 *   app_tx.c       boot, sampling, the minute's report (journaled, or held during an exchange),
 *                  watchdog health
 *   tx_exchange.c  the minute's radio exchange, one state machine (docs/firmware-event-model.md);
 *                  the node's key and station (the only module that seals and opens frames)
 *   tx_policy.c    energy and link state, what a minute may send, strikes, health-report schedule
 *   tx_time.c      time trust (sync from an ACK, kept across a warm reset)
 *   tx_console.c   console commands, STATUS, the TEST-FLASH-STORM bench load
 *   selftest.c     the boot known-answer test
 * Each module keeps its own state static (docs/power-of-ten.md, rule 6). This header is app_tx.c's
 * part: this boot's identity and run state, read-only to the others. */
typedef struct {
  uint32_t boot_s;                /* clock_s() at boot: the uptime origin */
  uint32_t boot_epoch, next_seq;  /* this boot's durable epoch (0 until reserved); the next sequence */
  int kat_ok;                     /* the last known-answer self-test passed */
  int running;                    /* sampling by design: the watchdog expects progress */
  uint32_t sensor_faults;         /* minutes with no valid sample */
  uint32_t held_lost;             /* held readings dropped for a newer one (see held_flush) */
  ws_failrun journal_fails;       /* the minute's journal appends that failed in a row (review P7) */
} tx_node_t;
const tx_node_t *node_state(void);   /* read-only view; only app_tx.c writes it */
uint32_t node_uptime_s(void);        /* RTC seconds since boot */
int node_selftest(void);             /* run the self-test again (KAT command); its result */

void sampling_stop(void);   /* no more samples (commanded reboot, TEST-FLASH-STORM); the watchdog stops expecting them */
/* Journal the readings held while an exchange was running. tx_exchange.c calls it the moment the
   radio goes idle, before anything else runs: flash is only written with the radio idle. */
void held_flush(void);
#endif
