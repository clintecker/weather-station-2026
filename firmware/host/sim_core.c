/* The simulated board every host harness shares (include/sim_core.h). Sources of the semantics:
 *  - clock: board timer_if.c. HAL_GetTick() counts 1/1024 s RTC ticks, not milliseconds
 *    (docs/firmware-event-model.md); SysTimeGetMcuTime() is TIMER_IF_GetTime (seconds = ticks >> 10,
 *    milliseconds = sub-ticks * 1000 >> 10); SysTimeGet() adds the offset SysTimeSet() stored.
 *  - timer server: vendor/STM32CubeWL/Utilities/timer/stm32_timer.c over timer_if.c. A period is
 *    TIMER_IF_Convert_ms2Tick (ms * 1024 / 1000, rounded down), at least MIN_ALARM_DELAY = 3 ticks,
 *    counted from the current tick. UTIL_TIMER_Start on a timer that is already running is refused
 *    (UTIL_TIMER_INVALID_PARAM) and changes nothing; refusals are counted. The running timers form
 *    ST's sorted list, with ST's insertion order for equal expiries (TimerInsertNewHeadTimer /
 *    TimerInsertTimer). The alarm interrupt runs every expired timer, in list order; a periodic
 *    timer is started again after its callback unless the callback stopped it (IsReloadStopped).
 *    UTIL_TIMER_SetPeriod restarts a running timer.
 *  - sequencer: vendor/STM32CubeWL/Utilities/sequencer/stm32_seq.c UTIL_SEQ_Run: the highest
 *    priority with a pending task, round robin within it (the round_robin mask and the starving
 *    list), highest task bit first (SEQ_BitPosition = 31 - clz). Events, pause and nesting are not
 *    modelled (the firmware uses none). A task that keeps re-posting itself never settles: after
 *    1000 tasks in one pass the pass ends (counted, or fatal: sim_config) so time can move on.
 *  - the event loop: interrupts run in time order (NVIC order when due together); every interrupt
 *    due at the same instant runs before the main loop does, as on the chip; then the main loop runs
 *    every posted task to completion. The clock moves only between tasks: a task that waited for
 *    time would hang here, and there is no HAL_Delay at all.
 *  - watchdog (board watchdog.c): a 1 s check timer posts the check task, which calls the health
 *    test and refreshes the IWDG; 8 s without a refresh is a reset (4000 / 500 Hz), counted.
 * Checked after every task: interrupts are not left masked. */
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fault.h"
#include "leds.h"
#include "rtc.h"
#include "sim_core.h"
#include "stackmon.h"
#include "stm32_seq.h"
#include "stm32_systime.h"
#include "stm32wlxx_hal.h"
#include "sys_app.h"
#include "utilities_def.h"
#include "watchdog.h"

static void fatal(const char *what)
{
  fprintf(stderr, "%s: %s\n", sim_cfg.name, what);
  abort();
}

/* ---- clock, CMSIS, RTC ---- */
static uint64_t now;          /* units */
static uint32_t utc_offset;   /* SysTimeGet = MCU seconds + offset */
DWT_Type host_dwt;
CoreDebug_Type host_coredebug;
uint32_t SystemCoreClock = 48000000U;
uint32_t host_primask;
RTC_HandleTypeDef hrtc;
static uint32_t bkp[RTC_BKP_COUNT];
uint64_t sim_now(void) { return now; }
uint64_t sim_ticks(void) { return now / SIM_UNITS_PER_TICK; }
uint64_t sim_ms(void) { return now / SIM_UNITS_PER_MS; }
void sim_set_ms(uint64_t ms) { now = ms * SIM_UNITS_PER_MS; }
uint32_t sim_ms_to_ticks(uint32_t ms) { return (uint32_t)(((uint64_t)ms << 10) / 1000U); }
uint32_t HAL_GetTick(void) { return (uint32_t)sim_ticks(); }
SysTime_t SysTimeGetMcuTime(void)
{
  uint64_t t = sim_ticks();
  return (SysTime_t){ .Seconds = (uint32_t)(t >> 10), .SubSeconds = (int16_t)(((t & 1023U) * 1000U) >> 10) };
}
SysTime_t SysTimeGet(void)
{
  SysTime_t t = SysTimeGetMcuTime();
  t.Seconds += utc_offset;
  return t;
}
void SysTimeSet(SysTime_t t) { utc_offset = t.Seconds - SysTimeGetMcuTime().Seconds; }
uint32_t HAL_RTCEx_BKUPRead(RTC_HandleTypeDef *h, uint32_t reg) { (void)h; return bkp[reg]; }
void HAL_RTCEx_BKUPWrite(RTC_HandleTypeDef *h, uint32_t reg, uint32_t value) { (void)h; bkp[reg] = value; }

/* ---- timer server ---- */
#define TIMER_INVALID_PARAM 1
#define MIN_ALARM_DELAY 3U
static UTIL_TIMER_Object_t *timers, *list_head;
static uint32_t timer_start_refused;
UTIL_TIMER_Object_t *sim_timers(void) { return timers; }
uint64_t sim_timer_due(uint64_t start, uint32_t period_ms)
{
  if (sim_cfg.timer_exact_ms) return start + (uint64_t)period_ms * SIM_UNITS_PER_MS;
  uint32_t ticks = sim_ms_to_ticks(period_ms);
  if (ticks < MIN_ALARM_DELAY) ticks = MIN_ALARM_DELAY;
  return (start / SIM_UNITS_PER_TICK + ticks) * SIM_UNITS_PER_TICK;
}
static int in_list(const UTIL_TIMER_Object_t *t)
{
  for (const UTIL_TIMER_Object_t *p = list_head; p; p = p->list_next)
    if (p == t) return 1;
  return 0;
}
static void unlink_timer(UTIL_TIMER_Object_t *t)
{
  for (UTIL_TIMER_Object_t **p = &list_head; *p; p = &(*p)->list_next)
    if (*p == t) { *p = t->list_next; return; }
}
/* ST's TimerInsertTimer: after the head, and before the first timer that expires at the same time
   or later. */
static void insert_timer(UTIL_TIMER_Object_t *t)
{
  UTIL_TIMER_Object_t *cur = list_head;
  while (cur->list_next && t->due > cur->list_next->due) cur = cur->list_next;
  t->list_next = cur->list_next;
  cur->list_next = t;
}
int UTIL_TIMER_Create(UTIL_TIMER_Object_t *t, uint32_t period, UTIL_TIMER_Mode_t mode, void (*cb)(void *), void *arg)
{
  int known = 0;
  for (UTIL_TIMER_Object_t *p = timers; p; p = p->next) known |= p == t;
  unlink_timer(t);   /* ST would corrupt its list here; the firmware never re-creates a running timer */
  t->period = period; t->mode = mode; t->cb = cb; t->arg = arg; t->running = 0; t->reload_stopped = 0;
  t->list_next = NULL;
  if (!known) { t->next = timers; timers = t; }
  return 0;
}
int UTIL_TIMER_Start(UTIL_TIMER_Object_t *t)
{
  if (t->running || in_list(t)) { timer_start_refused++; return TIMER_INVALID_PARAM; }
  t->running = 1; t->reload_stopped = 0; t->due = sim_timer_due(now, t->period);
  if (!list_head || t->due < list_head->due) { t->list_next = list_head; list_head = t; }
  else insert_timer(t);
  return 0;
}
int UTIL_TIMER_Stop(UTIL_TIMER_Object_t *t)
{
  t->reload_stopped = 1;
  if (list_head) { t->running = 0; unlink_timer(t); }
  return 0;
}
int UTIL_TIMER_SetPeriod(UTIL_TIMER_Object_t *t, uint32_t period)
{
  t->period = period;
  if (!in_list(t)) return 0;
  UTIL_TIMER_Stop(t);
  return UTIL_TIMER_Start(t);
}
static int timer_pending(uint64_t *at)
{
  if (!list_head) return 0;
  *at = list_head->due;
  return 1;
}
static void timer_fire(void)   /* UTIL_TIMER_IRQ_Handler, one expired timer at a time */
{
  UTIL_TIMER_Object_t *t = list_head;
  list_head = t->list_next;
  t->running = 0;
  t->cb(t->arg);
  if (t->mode == UTIL_TIMER_PERIODIC && !t->reload_stopped) UTIL_TIMER_Start(t);
}
static const sim_source timer_source = { timer_pending, timer_fire, SIM_IRQ_RTC_ALARM };
uint32_t h_timer_start_refused(void) { return timer_start_refused; }

/* ---- sequencer ---- */
static void (*task_cb[32])(void);
static uint32_t task_set, clear_list;
static struct { uint32_t priority, round_robin; } task_prio[CFG_SEQ_Prio_NBR];
static uint32_t task_saturations, task_runs, primask_leaks;
static int hold, fault_tests, in_tasks;
static jmp_buf fault_jump;
void UTIL_SEQ_RegTask(uint32_t mask, uint32_t flags, void (*task)(void)) { (void)flags; task_cb[31 - __builtin_clz(mask)] = task; }
void UTIL_SEQ_SetTask(uint32_t mask, uint32_t prio)
{
  if (prio >= CFG_SEQ_Prio_NBR) fatal("UTIL_SEQ_SetTask: no such priority");
  task_set |= mask;
  task_prio[prio].priority |= mask;
}
static int seq_pick(void)   /* UTIL_SEQ_Run's choice of the next task */
{
  uint32_t c = 0;
  while (task_prio[c].priority == 0) c++;
  uint32_t current = task_prio[c].priority;
  if ((task_prio[c].round_robin & current) == 0) task_prio[c].round_robin = ~0U;
  clear_list |= ~task_prio[c].round_robin;
  uint32_t starving = task_set & ~clear_list;
  if (starving & current) current &= starving;
  if (starving == 0) clear_list = 0;
  return 31 - __builtin_clz(current & task_prio[c].round_robin);
}
static void seq_run_one(void)
{
  int id = seq_pick();
  uint32_t bit = 1U << id;
  task_set &= ~bit;
  for (int p = 0; p < CFG_SEQ_Prio_NBR; p++) task_prio[p].priority &= ~bit;
  if (!task_cb[id]) return;   /* ST: UTIL_SEQ_CatchWarning */
  for (int p = 0; p < CFG_SEQ_Prio_NBR; p++) task_prio[p].round_robin &= ~bit;
  task_cb[id]();
  task_runs++;
  clear_list |= bit;
}
static void check_primask(void)
{
  if (!host_primask) return;
  primask_leaks++; host_primask = 0;
  if (sim_cfg.primask_leak_fatal) fatal("a task left interrupts masked");
}
static void saturated(void)
{
  task_saturations++;
  if (sim_cfg.saturation_fatal) fatal("tasks never settle");
}
void sim_run_tasks(void)
{
  if (hold || fault_tests) return;   /* held off, or the board is resetting after a fault */
  if (setjmp(fault_jump)) { in_tasks = 0; return; }
  in_tasks = 1;
  for (int guard = 0; task_set; guard++)
  {
    if (guard > 1000) { saturated(); break; }
    seq_run_one();
    check_primask();
  }
  in_tasks = 0;
}
void sim_set_hold(int on) { hold = on; }
uint32_t h_task_saturations(void) { return task_saturations; }
uint32_t h_task_pending(void) { return task_set; }
uint32_t h_task_runs(void) { return task_runs; }
uint32_t h_primask_leaks(void) { return primask_leaks; }
int h_fault_tests(void) { return fault_tests; }
/* TEST-FAULT: the board records a HardFault and resets; here the main loop stops for good. */
void fault_test(void)
{
  fault_tests++;
  if (!in_tasks) fatal("fault_test outside a task");
  longjmp(fault_jump, 1);
}

/* ---- watchdog ---- */
static int (*healthy_fn)(void);
static UTIL_TIMER_Object_t wd_timer;
static uint64_t wd_refreshed;   /* ticks */
static uint32_t wd_resets, wd_unhealthy, wd_checks;
static void wd_check(void)
{
  wd_checks++;
  if (healthy_fn()) wd_refreshed = sim_ticks(); else wd_unhealthy++;
}
static void wd_request(void *arg) { (void)arg; UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Watchdog, CFG_SEQ_Prio_0); }
void watchdog_start(int (*healthy)(void))
{
  healthy_fn = healthy;
  if (!sim_cfg.watchdog_periodic) return;
  wd_refreshed = sim_ticks();
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Watchdog, UTIL_SEQ_RFU, wd_check);
  UTIL_TIMER_Create(&wd_timer, 1000, UTIL_TIMER_PERIODIC, wd_request, NULL);
  UTIL_TIMER_Start(&wd_timer);
}
static void wd_iwdg(void)
{
  if (!sim_cfg.watchdog_periodic || !healthy_fn) return;
  if (sim_ticks() - wd_refreshed > 8U * 1024U) { wd_resets++; wd_refreshed = sim_ticks(); }
}
ws_reset_t watchdog_reset_code(void) { return WS_RESET_POWER; }
const char *watchdog_reset_cause(void) { return "power"; }
int h_healthy(void) { return healthy_fn(); }
uint32_t h_wd_resets(void) { return wd_resets; }
uint32_t h_wd_unhealthy(void) { return wd_unhealthy; }
uint32_t h_wd_checks(void) { return wd_checks; }

/* ---- board stubs ---- */
static uint32_t led_flashes[3];
static int resets;
void leds_init(void) {}
void led_flash(led_t led, uint32_t ms) { (void)ms; led_flashes[led]++; }
void led_set(led_t led, int on) { (void)led; (void)on; }
void fault_report(void) {}
uint32_t fault_count(void) { return 0; }
void stackmon_paint(void) {}
uint32_t stackmon_peak(void) { return 0; }
void NVIC_SystemReset(void)
{
  resets++;
  if (sim_cfg.reset_fatal) fatal("NVIC_SystemReset");
}
uint32_t h_led_flashes(int led) { return led_flashes[led]; }
int h_resets(void) { return resets; }

/* ---- console capture ---- */
volatile uint32_t ws_trace_drops;
static char out[1 << 20];
static size_t out_len;
int sim_capture(const char *text, size_t n)
{
  if (out_len + n >= sizeof out) return 0;
  memcpy(out + out_len, text, n);
  out_len += n;
  return 1;
}
/* Console output since the last call (NUL-terminated, valid until the next call). */
const char *h_output(void)
{
  static char copy[sizeof out];
  memcpy(copy, out, out_len); copy[out_len] = 0; out_len = 0;
  return copy;
}
uint32_t h_trace_drops(void) { return ws_trace_drops; }

/* ---- the event loop ---- */
/* The next interrupt (the earliest; NVIC order when due together), not before now. */
static void consider(const sim_source *s, const sim_source **best, uint64_t *at)
{
  uint64_t t;
  if (!s->pending(&t)) return;
  if (t < now) t = now;
  if (!*best || t < *at || (t == *at && s->irq < (*best)->irq)) { *best = s; *at = t; }
}
static const sim_source *next_event(uint64_t *at)
{
  const sim_source *best = NULL;
  consider(&timer_source, &best, at);
  for (const sim_source *const *s = sim_cfg.sources; s && *s; s++) consider(*s, &best, at);
  return best;
}
static void move_to(uint64_t t)
{
  uint64_t from = now;
  now = t;
  if (sim_cfg.on_time) sim_cfg.on_time(from, t);
  wd_iwdg();
}
static int due_now(void)
{
  uint64_t at;
  return next_event(&at) && at == now;
}
void sim_advance(uint32_t ms)
{
  uint64_t until = now + (uint64_t)ms * SIM_UNITS_PER_MS, at;
  const sim_source *s;
  sim_run_tasks();
  while ((s = next_event(&at)) && at <= until)
  {
    move_to(at);
    s->fire();
    if (!due_now()) sim_run_tasks();
  }
  move_to(until);
  sim_run_tasks();
}

/* ---- radio interrupt masking (tx_harness.c, rx_harness.c) ----
   The firmware masks the radio interrupt around every main-loop radio command (radio_cfg.h,
   2026-10-15 review M1); a harness radio command made without it is counted (tests require none). */
static int radio_irq_held;
static uint32_t unmasked_radio_calls;
void ws_radio_irq_hold(void) { radio_irq_held++; }
void ws_radio_irq_release(void) { radio_irq_held--; }
void sim_radio_command(void) { if (radio_irq_held <= 0) unmasked_radio_calls++; }
uint32_t h_unmasked_radio_calls(void) { return unmasked_radio_calls; }
