#ifndef TX_TIME_H
#define TX_TIME_H
#include <stdint.h>
/* TX time trust. Time comes only from an authentic ACK that echoes the counter of the frame just
 * sent (replayed ACKs cannot move the clock; App/tx_exchange.c checks that) and is trusted for 6 h
 * (LSE drift; see the gateway's DRIFT_PPM). Option D: the trust survives a system reset (NRST,
 * software, watchdog) through two RTC backup registers; a power loss clears the backup domain, so
 * trust is lost, as it must be. */
void time_restore(void);       /* at boot: keep the trust if the RTC kept counting and the sync is recent */
int time_valid(void);
uint32_t time_utc(void);       /* UTC seconds, or 0 while the time is unknown */
int time_sync(uint32_t utc);   /* set the clock from an ACK's time; 0 (nothing set) if it is implausible */
#endif
