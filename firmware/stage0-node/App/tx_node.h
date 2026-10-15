#ifndef TX_NODE_H
#define TX_NODE_H
#include <stdint.h>
#include "stage0.h"
/* The TX role, in modules (firmware/stage0-node/README.md, "Source files"):
 *   app_tx.c       boot, sampling, the minute's report (journaled, or held during an exchange),
 *                  watchdog health
 *   tx_exchange.c  the minute's radio exchange, one state machine (docs/firmware-event-model.md)
 *   tx_policy.c    energy and link state, what a minute may send, strikes, health-report schedule
 *   tx_time.c      time trust (sync from an ACK, kept across a warm reset)
 *   tx_console.c   console commands, STATUS, the TEST-FLASH-STORM bench load
 *   selftest.c     the boot known-answer test
 * This header holds what they share: the node's identity and run state, owned by app_tx.c. */
typedef struct {
  uint32_t station;
  uint8_t key[16], kcv[3];
  int provisioned, kat_ok;
  int running;                  /* sampling by design: the watchdog expects progress */
  int rebooting;                /* a commanded reboot is pending: a late reading is dropped */
  int storming;                 /* TEST-FLASH-STORM: sampling stopped */
  uint32_t boot_epoch, next_seq;
  uint32_t boot_s;              /* clock_s() at boot: the uptime origin */
  uint32_t sensor_faults;       /* minutes with no valid sample */
  uint32_t held_lost;           /* held readings dropped for a newer one (see held_flush) */
  ws_failrun journal_fails;     /* the minute's journal appends that failed in a row (review P7) */
} tx_node_t;
extern tx_node_t tx_node;

/* app_tx.c */
void sampling_stop(void);   /* no more samples (commanded reboot, TEST-FLASH-STORM); the watchdog stops expecting them */
/* Journal the readings held while an exchange was running. tx_exchange.c calls it the moment the
   radio goes idle, before anything else runs: flash is only written with the radio idle. */
void held_flush(void);
#endif
