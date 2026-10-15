#ifndef TX_EXCHANGE_H
#define TX_EXCHANGE_H
#include <stdint.h>
#include "node_store.h"
#include "stage0.h"
#include "ws_frame.h"
#include "ws_obs.h"
/* The minute's radio exchange (docs/firmware-event-model.md): the live observation, then older
 * pending ones as the policy allows, each with a fresh durably reserved counter and one ACK
 * window; then the health report if one is due. One explicit state machine, driven by radio and
 * timer events (App/events.h). Every state is left by an event that is certain to come. */
#define MAX_QUEUE     21U   /* live + up to 20 backlog (SURPLUS at SF7); RAM 84 B */
#define OBS_FRAME_MAX (WS_OBS_PLAIN_MAX + WS_FRAME_OVERHEAD)

void exchange_init(void);   /* radio, timers and the process task; the radio sleeps */
/* Start the minute's exchange: live (NULL if its journal append failed) first, then up to
   backlog of the oldest pending records. Nothing to send: stays idle. */
void exchange_start(const jref_t *live, unsigned backlog);
int exchange_busy(void);
int exchange_overdue(uint32_t now_s);   /* busy for longer than this exchange's worst case (watchdog) */
const char *exchange_state_name(void);

typedef struct {
  uint32_t sent, acked, no_ack, ack_rejects;
  uint32_t unexpected;   /* events in a state that does not expect them */
  ws_failrun air;        /* transmissions that failed in a row (review P7) */
} tx_counts_t;
extern tx_counts_t tx_counts;
#endif
