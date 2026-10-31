#ifndef TX_POLICY_H
#define TX_POLICY_H
#include <stdint.h>
#include "node_store.h"
/* The node's transmission policy state (docs/radio-energy-policy.md); the decisions themselves
 * are pure functions in firmware/common/ws_policy.c. */

/* Energy state (WS_ENERGY_*): fixed at NORMAL. The node measures its battery and charger (power
   telemetry design), but the thresholds are deferred to the energy-policy work (design 9.9, open
   decision D1: measured loads and the pack reserve); that work feeds the pack, charger and solar
   telemetry in here. Unknown energy must map to CONSERVE (fail closed). */
int energy_state(void);
void policy_init(void);   /* at boot: the airtime of one answered exchange and of a health report */
/* What this minute may send: -1 nothing (the reading stays journaled), else how many backlog
   frames may follow the live reading. A minute whose health report follows the exchange reserves
   its airtime first (design 6.4). A minute that may send counts as the last send. */
int policy_minute_backlog(void);
/* End of a minute's exchange: strikes for the unanswered records (only if the gateway answered
   something, replied[i] for queue[i]) and the link state. */
void policy_exchange_end(const jref_t *queue, const uint8_t *replied, unsigned n);
void policy_strike_forget(uint32_t epoch, uint32_t seq);   /* an authentic ACK for this record */
/* Health report (kind 4): every 15 min and at each link-state change. */
int policy_diag_due(void);
void policy_diag_sent(uint32_t now_s);
int policy_probing(void);
uint32_t policy_silent_minutes(void);
#endif
