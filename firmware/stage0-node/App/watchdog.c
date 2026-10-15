#define WS_CHECK_FILE 9
#include "busymon.h"
#include "watchdog.h"
#include "stm32_seq.h"
#include "stm32_timer.h"
#include "stm32wlxx_hal.h"
#include "sys_conf.h"
#include "utilities_def.h"
#include "ws_check.h"

#define CHECK_PERIOD_MS 1000U
/* LSI 32 kHz / 64 = 500 Hz; 4000 counts = 8 s. Longest legitimate blocking operation is a
 * full WIPE (94 page erases: 93 journal + config, ~2.2 s), well inside this window. */
#define IWDG_PRESCALER  IWDG_PRESCALER_64
#define IWDG_RELOAD     4000U

static IWDG_HandleTypeDef hiwdg;
static UTIL_TIMER_Object_t check_timer;
static ws_reset_t cause = WS_RESET_UNKNOWN;
/* Indexed by code (designated initializers), so the name and the DIAG wire code cannot drift apart. */
static const char *const cause_name[] = {
  [WS_RESET_UNKNOWN] = "unknown", [WS_RESET_POWER] = "power", [WS_RESET_PIN] = "pin",
  [WS_RESET_BROWNOUT] = "brownout", [WS_RESET_SOFTWARE] = "software", [WS_RESET_WATCHDOG] = "watchdog",
  [WS_RESET_LOWPOWER] = "lowpower", [WS_RESET_OPTION_BYTES] = "option-bytes" };
_Static_assert(sizeof cause_name / sizeof cause_name[0] == WS_RESET_COUNT, "one name per reset code");

static void request_check(void *ctx)
{
  (void)ctx;
  UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Watchdog, CFG_SEQ_Prio_0);
}

static void check(void)
{
  if (watchdog_healthy()) (void)HAL_IWDG_Refresh(&hiwdg);   /* always HAL_OK (stm32wlxx_hal_iwdg.c) */
}
BUSYMON_TASK(check)

static void read_reset_cause(void)
{
  if (__HAL_RCC_GET_FLAG(RCC_FLAG_IWDGRST)) cause = WS_RESET_WATCHDOG;
  else if (__HAL_RCC_GET_FLAG(RCC_FLAG_BORRST)) cause = WS_RESET_POWER; /* BOR flag is also set at power-on */
  else if (__HAL_RCC_GET_FLAG(RCC_FLAG_SFTRST)) cause = WS_RESET_SOFTWARE;
  else if (__HAL_RCC_GET_FLAG(RCC_FLAG_LPWRRST)) cause = WS_RESET_LOWPOWER;
  else if (__HAL_RCC_GET_FLAG(RCC_FLAG_OBLRST)) cause = WS_RESET_OPTION_BYTES;
  else if (__HAL_RCC_GET_FLAG(RCC_FLAG_PINRST)) cause = WS_RESET_PIN;
  __HAL_RCC_CLEAR_RESET_FLAGS();
}

ws_reset_t watchdog_reset_code(void) { return cause; }
const char *watchdog_reset_cause(void) { return cause_name[cause]; }

void watchdog_start(void)
{
  read_reset_cause();
#if defined(DEBUGGER_ENABLED) && (DEBUGGER_ENABLED == 1)
  __HAL_DBGMCU_FREEZE_IWDG(); /* a halted debug session must not trigger resets */
#endif
  hiwdg.Instance = IWDG;
  hiwdg.Init.Prescaler = IWDG_PRESCALER;
  hiwdg.Init.Window = IWDG_WINDOW_DISABLE;
  hiwdg.Init.Reload = IWDG_RELOAD;
  /* Started either way (the HAL writes the start key first). A timeout means the new prescaler and
     reload had not taken effect within ST's wait; they still do once the update completes. Counted. */
  (void)WS_CHECK(HAL_IWDG_Init(&hiwdg) == HAL_OK);
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Watchdog, UTIL_SEQ_RFU, check_timed);
  (void)UTIL_TIMER_Create(&check_timer, CHECK_PERIOD_MS, UTIL_TIMER_PERIODIC, request_check, NULL);
  (void)WS_CHECK(UTIL_TIMER_Start(&check_timer) == UTIL_TIMER_OK);   /* created just above */
}
