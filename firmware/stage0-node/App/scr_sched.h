/* Which bench screen to show, and which of its frames, step by step (docs/superpowers/specs/
 * 2026-11-04-node-oled-and-e2e-design.md, "The screens" and "The buttons"). Pure C, no HAL:
 * tests/test_scr_sched.py drives it on the host. App/oled_app.c steps it every 125 ms (8 steps a second)
 * and draws what it says.
 *   boot     BOOT, then HACK, then HOME.
 *   base     HOME for 15 s, then the next detail screen (AIR, PRESSURE, POWER, RADIO, SCOPE, VANE, RAIN,
 *            SYSTEM in turn) for 15 s, then HOME again, and so on. A base screen's frame counts its steps
 *            from 0; it is drawn at every step of its animation (sched_anim), then every sched_every steps
 *            (HOME and SCOPE 2: 4 a second; the rest 8: once a second), and at the next step after an ACK,
 *            a NO ACK or B3 on.
 *   interlude one of FORTUNE, SCOPE, FROG, VANE, MATRIX, RAIN, PINBALL, SYSTEM, HACK in turn, every 120 s at
 *            a fixed phase (the first 120 s after sched_init), for scr_frames(id) frames, then HOME. One
 *            falls due only while HOME is up: due during a detail screen or a packet it waits for HOME,
 *            and the next is still due on the phase.
 *   packet   EV_SENT_LIVE plays BURST, then BANNER (HOME with the banner), then HOME. It preempts whatever
 *            is on (at its next step). EV_SENT_EXTRA only counts a frame for the banner.
 * Times are ms of one clock (clock_ms); differences wrap safely. Only in WS_BENCH_OLED=1 builds. */
#ifndef SCR_SCHED_H
#define SCR_SCHED_H
#include <stdint.h>
#include "scr_screens.h"

/* EV_B1..EV_B3 are the buttons. B1: the next of every screen, in the order HOME, the detail screens, then
   FORTUNE, FROG, MATRIX, PINBALL, HACK, then HOME again (its own list: the interludes' order is apart). A
   base screen picked stays its 15 s, an interlude plays its frames, then the base cycle goes on. B2: pause
   or resume. Paused, the screen stays where B1 put it (design, "The buttons"): the one up at the press
   (HOME if a packet or boot screen was up, after it ends) is held, plays again from frame 0 each time it
   ends (a base screen after its 15 s), and comes back after a packet's burst and banner; B1 moves the held
   screen to the next one; no base cycle, no interludes. On resume the held screen plays to its end, the
   cycle goes on from it, and the next interlude is a full period away. B3: the display off (sched_step
   reports display_on 0, the screens go on in step) or on. While the display is off, B1 and B2 do nothing:
   no change the user cannot see. */
enum sched_ev { EV_SENT_LIVE, EV_SENT_EXTRA, EV_ACK, EV_NO_ACK, EV_B1, EV_B2, EV_B3 };

#define SCHED_DWELL_STEPS 120U   /* a base screen's 15 s */

void sched_init(uint32_t now_ms);
void sched_event(enum sched_ev e, uint32_t now_ms);
/* One step: the screen and frame to show now, and whether the display is on. Returns 1 if that frame
   is to be drawn and sent, 0 if the screen stays as it is (a base screen between its redraws). A step that
   could not send its frame must not be taken: the caller waits for the next tick instead. */
int sched_step(uint32_t now_ms, enum scr_id *id, unsigned *frame, int *display_on);
unsigned sched_extras(void);   /* frames sent after the live one, since the last EV_SENT_LIVE */
int sched_display_on(void);    /* what B3 says, before the step: the caller powers the panel first */
/* A base screen's animation (steps drawn one by one from frame 0) and the steps between its later redraws: its
   scr_defs anim and every. */
unsigned sched_anim(enum scr_id id);
unsigned sched_every(enum scr_id id);
#endif
