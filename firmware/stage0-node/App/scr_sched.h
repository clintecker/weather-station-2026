/* Which bench screen to show, and which of its frames, step by step (docs/superpowers/specs/
 * 2026-11-04-node-oled-and-e2e-design.md, "The interludes"). Pure C, no HAL: tests/test_scr_sched.py
 * drives it on the host. App/oled_app.c steps it every 125 ms (8 frames a second) and draws what it says.
 *   boot     BOOT, then HACK, then NORMAL.
 *   NORMAL   redrawn once a second (every 8th step), or at the next step after an ACK or a NO ACK.
 *   rotation one interlude of SCOPE, VANE, SYSTEM, HACK in turn, 120 s after the last one started
 *            (the first 120 s after sched_init), each for scr_frames(id) frames; one that falls due
 *            during a packet waits for NORMAL.
 *   packet   EV_SENT_LIVE plays BURST, then BANNER, then NORMAL. It preempts whatever is on (an
 *            interlude yields at its next frame). EV_SENT_EXTRA only counts a frame for the banner.
 * Times are ms of one clock (clock_ms); differences wrap safely. Only in WS_BENCH_OLED=1 builds. */
#ifndef SCR_SCHED_H
#define SCR_SCHED_H
#include <stdint.h>
#include "scr_view.h"

/* EV_B1..EV_B3 are the buttons. B1: the next of NORMAL, SCOPE, VANE, SYSTEM, HACK, then NORMAL again (the
   screen plays from its first frame, then falls back to NORMAL as any interlude). B2: pause or resume the
   rotation (no automatic interludes while paused; packets still show; on resume the next one is a full
   period away). B3: the display off (sched_step reports display_on 0, the screens go on in step) or on. */
enum sched_ev { EV_SENT_LIVE, EV_SENT_EXTRA, EV_ACK, EV_NO_ACK, EV_B1, EV_B2, EV_B3 };

void sched_init(uint32_t now_ms);
void sched_event(enum sched_ev e, uint32_t now_ms);
/* One step: the screen and frame to show now, and whether the display is on. Returns 1 if that frame
   is to be drawn and sent, 0 if the screen stays as it is (NORMAL between its redraws). A step that
   could not send its frame must not be taken: the caller waits for the next tick instead. */
int sched_step(uint32_t now_ms, enum scr_id *id, unsigned *frame, int *display_on);
unsigned sched_extras(void);   /* frames sent after the live one, since the last EV_SENT_LIVE */
#endif
