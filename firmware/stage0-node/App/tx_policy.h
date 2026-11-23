#ifndef TX_POLICY_H
#define TX_POLICY_H
#include <stdint.h>
#include "node_store.h"
/* The node's transmission policy state (docs/radio-energy-policy.md); the decisions themselves
 * are pure functions in firmware/common/ws_policy.c. */

/* Energy state (WS_ENERGY_*, docs/radio-energy-policy.md section 3). The TX stack build (profile 3)
   decides it once a minute from the gauge (SOC, VCELL), the charger's VBAT when the gauge is gone, and
   the charger's evidence of a full pack; unknown is CONSERVE (fail closed). A change prints "#energy"
   and makes a health report due. The bench builds (profiles 1 and 2) stay at NORMAL. */
int energy_state(void);
void policy_energy_minute(void);   /* once a minute, before the reading is built */
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
