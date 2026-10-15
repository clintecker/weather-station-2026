/* The simulated board every host harness shares (firmware/host/sim_core.c): the clock, ST's timer
 * server and sequencer, the CMSIS stand-ins, the RTC, the watchdog, the board stubs, the console
 * capture and the event loop. A harness (tx_harness.c, rx_harness.c, sensor_harness.c) adds only its
 * role's devices: it defines `sim_cfg`, and each device that raises interrupts on its own is a
 * sim_source the event loop serves in time order. */
#ifndef HOST_SIM_CORE_H
#define HOST_SIM_CORE_H
#include <stddef.h>
#include <stdint.h>
#include "stm32_timer.h"

/* Time is counted in units of 1/1 024 000 s, so that both a whole millisecond (the tests' clock) and
   a whole 1/1024 s RTC tick (the board's clock) are whole numbers of units. */
#define SIM_UNITS_PER_MS   1024U
#define SIM_UNITS_PER_TICK 1000U

/* An interrupt source. Due together, interrupts are served in NVIC order: preemption priority, then
   IRQ number (CM4 vector numbers, stm32wl55xx.h; priorities from the board's MSP init code). */
#define SIM_IRQ(prio, num) ((uint32_t)(prio) << 8 | (uint32_t)(num))
#define SIM_IRQ_RTC_ALARM SIM_IRQ(0, 42)   /* rtc.c: priority 0; the timer server's alarm */
#define SIM_IRQ_SUBGHZ    SIM_IRQ(0, 50)   /* subghz.c: priority 0 */
#define SIM_IRQ_I2C2_EV   SIM_IRQ(2, 32)   /* sensor.c: priority 2 */
typedef struct {
  int (*pending)(uint64_t *at);   /* 1 if an interrupt is coming, and when (units) */
  void (*fire)(void);             /* raise it (interrupt context) */
  uint32_t irq;                   /* SIM_IRQ(...) */
} sim_source;

typedef struct {
  const char *name;                       /* for fatal messages */
  const sim_source *const *sources;       /* NULL-terminated; the timer server is always there */
  void (*on_time)(uint64_t from, uint64_t to);   /* the clock moved (units); may be NULL */
  /* 1: a timer period is exact milliseconds, not ST's whole ticks (tests/test_tx_machine.py states
     its expectations, 50 ms gaps and so on, in whole ms from the specification; ST would make a
     50 ms gap 51 ticks = 49.8 ms). Everything else (ordering, refusals, reloads) stays ST's. */
  int timer_exact_ms;
  int watchdog_periodic;   /* 1: watchdog_start runs the 1 s check timer and the 8 s IWDG */
  int reset_fatal;         /* 1: NVIC_SystemReset aborts the test; 0: it is counted */
  int saturation_fatal;    /* 1: tasks that never settle abort the test; 0: counted, time moves on */
  int primask_leak_fatal;  /* 1: a task leaving interrupts masked aborts the test; 0: counted */
} sim_config;
extern const sim_config sim_cfg;   /* defined by the harness */

/* ---- clock ---- */
uint64_t sim_now(void);                 /* units */
uint64_t sim_ticks(void);               /* RTC ticks */
uint64_t sim_ms(void);                  /* whole ms, rounded down */
void sim_set_ms(uint64_t ms);           /* before boot: the clock starts here */
uint32_t sim_ms_to_ticks(uint32_t ms);  /* timer_if.c TIMER_IF_Convert_ms2Tick */
uint64_t sim_timer_due(uint64_t start, uint32_t period_ms);   /* when a timer started at `start` expires */

/* ---- timer server ---- */
UTIL_TIMER_Object_t *sim_timers(void);  /* every timer created, running or not (->next) */

/* ---- sequencer and event loop ---- */
void sim_run_tasks(void);               /* the main loop: every posted task, unless held */
void sim_set_hold(int on);              /* hold the main loop off; interrupts still post */
void sim_advance(uint32_t ms);          /* move the test clock, serving every interrupt due */

/* ---- radio commands: call at the start of every harness radio command (counts unmasked ones) ---- */
void sim_radio_command(void);
void ws_radio_irq_hold(void);
void ws_radio_irq_release(void);

/* ---- console capture (h_output returns it) ---- */
int sim_capture(const char *text, size_t n);   /* 0 if it did not fit (nothing is kept) */
#endif
