/* What the radio exchange (App/tx_exchange.c) tells the bench OLED: a minute's exchange starts, a frame
 * went on air, the gateway answered it, or no answer came. They run in the exchange's own main-loop task, so they only note
 * the event and copy the frame; App/oled_app.c draws later, from its own task.
 * In the field build (WS_BENCH_OLED=0, the default) they are empty inline functions: the exchange
 * compiles to the same code as without them, and links no oled_ symbol (tests/test_scr_sched.py). */
#ifndef OLED_HOOKS_H
#define OLED_HOOKS_H
#include <stdint.h>
#ifndef WS_BENCH_OLED
#define WS_BENCH_OLED 0   /* the field build: no display (Makefile) */
#endif

/* What a frame sent is. LIVE: the minute's live reading, the first frame of its exchange (it plays the
   packet burst); BACKLOG and REPORT (the health report) follow it, and the banner only counts them. */
enum oled_sent { OLED_SENT_BACKLOG, OLED_SENT_LIVE, OLED_SENT_REPORT };

#if WS_BENCH_OLED
/* The minute's exchange starts (exchange_start, with or without a live reading): the airtime of this
   minute starts again. */
void oled_note_exchange(void);
/* frame: the sealed bytes just sent (len of them). kind: enum oled_sent. seq: the observation's
   sequence (0 for a health report). */
void oled_note_sent(uint32_t seq, const uint8_t *frame, uint8_t len, int kind);
/* The authentic ACK to the frame just sent, and its signal. Every argument of a hook is a value the
   exchange already holds, so the field build's empty hooks leave no call behind. */
void oled_note_ack(uint32_t seq, int16_t rssi, int8_t snr);
void oled_note_no_ack(uint32_t seq);   /* the window ended without a reply */
#else
static inline void oled_note_exchange(void) {}
static inline void oled_note_sent(uint32_t seq, const uint8_t *frame, uint8_t len, int kind)
{ (void)seq; (void)frame; (void)len; (void)kind; }
static inline void oled_note_ack(uint32_t seq, int16_t rssi, int8_t snr) { (void)seq; (void)rssi; (void)snr; }
static inline void oled_note_no_ack(uint32_t seq) { (void)seq; }
#endif
#endif
