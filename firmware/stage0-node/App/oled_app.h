/* The bench OLED's application (WS_BENCH_OLED=1 only; docs/superpowers/specs/
 * 2026-11-04-node-oled-and-e2e-design.md): a 125 ms UTIL timer posts a main-loop task, which steps the
 * screen scheduler (App/scr_sched.h), fills the view (App/oled_view.h) and the exchange's notes
 * (App/oled_hooks.h), draws the screen into the 1 KB frame buffer, expands it into the driver's send
 * buffer and sends it (App/oled_dma.h). Nothing is drawn in an interrupt, and nothing waits: a step that
 * finds the driver busy (a frame still going out, or the panel's start-up) does nothing, and the
 * scheduler's next frame goes at the next tick. The frame buffer and the view are in RAM2. */
#ifndef OLED_APP_H
#define OLED_APP_H

/* The driver (oled_dma_init), the scheduler (BOOT, then HACK), the task and the timer. Once, at boot. */
void oled_app_start(void);
/* A button went down: b is 1 (B1, PA0: next screen), 2 (B2, PA1: pause or resume the rotation) or 3 (B3,
   PC6: display on or off). From the EXTI interrupt (App/board_inputs.c): it only sets a flag; the 125 ms
   step debounces (50 ms) and passes the press to the scheduler. */
void oled_app_button(unsigned b);
#endif
