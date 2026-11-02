#include "bl_guard.h"
#include "fault.h"
#include "stm32_seq.h"
#include "stm32_timer.h"
#include "stm32wlxx_hal.h"
#include "sys_app.h"
#include "sys_conf.h"
#include "utilities_def.h"

#define CHECK_PERIOD_MS 1000U
/* LSI 32 kHz / 64 = 500 Hz; 4000 counts = 8 s. The longest blocking step is one tick's I2C and ADC
   work, a few tens of ms. */
#define IWDG_PRESCALER IWDG_PRESCALER_64
#define IWDG_RELOAD 4000U

/* The crash record (DR5-DR11) and the boot counter (DR12) in the RTC backup registers belong to
   stage0-node/App/fault.c, linked here (Makefile): fault_boot_note() is the boot counter's only writer,
   so benchlink and the node count boots the same way and never twice. */
#define U8_MAX 255U

static IWDG_HandleTypeDef hiwdg;
static UTIL_TIMER_Object_t check_timer;
static uint8_t cause = BL_RESET_UNKNOWN;
static const char *const cause_name[] = {
  [BL_RESET_UNKNOWN] = "unknown", [BL_RESET_POWER] = "power", [BL_RESET_PIN] = "pin",
  [BL_RESET_BROWNOUT] = "brownout", [BL_RESET_SOFTWARE] = "software", [BL_RESET_WATCHDOG] = "watchdog",
  [BL_RESET_LOWPOWER] = "lowpower", [BL_RESET_OPTION_BYTES] = "option-bytes" };
_Static_assert(sizeof cause_name / sizeof cause_name[0] == BL_RESET_COUNT, "one name per reset code");

static void request_check(void *ctx)
{
  (void)ctx;
  UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Guard, CFG_SEQ_Prio_0);
}

static void check(void)
{
  if (bl_role_check()) (void)HAL_IWDG_Refresh(&hiwdg);
}

/* As stage0-node: the brownout (BOR) flag is also set at power-on, so both read as power; a crash
   resets through NVIC_SystemReset and reads as software, with the crash record beside it. */
static void read_reset_cause(void)
{
  if (__HAL_RCC_GET_FLAG(RCC_FLAG_IWDGRST)) cause = BL_RESET_WATCHDOG;
  else if (__HAL_RCC_GET_FLAG(RCC_FLAG_BORRST)) cause = BL_RESET_POWER;
  else if (__HAL_RCC_GET_FLAG(RCC_FLAG_SFTRST)) cause = BL_RESET_SOFTWARE;
  else if (__HAL_RCC_GET_FLAG(RCC_FLAG_LPWRRST)) cause = BL_RESET_LOWPOWER;
  else if (__HAL_RCC_GET_FLAG(RCC_FLAG_OBLRST)) cause = BL_RESET_OPTION_BYTES;
  else if (__HAL_RCC_GET_FLAG(RCC_FLAG_PINRST)) cause = BL_RESET_PIN;
  __HAL_RCC_CLEAR_RESET_FLAGS();
}

void bl_guard_start(const char *role)
{
  read_reset_cause();
  /* Once a boot, before fault_report(): the count restarts with the power (a brown-out reads as
     power too, stage0-node/App/watchdog.h). */
  fault_boot_note(cause == BL_RESET_POWER);
  APP_PRINTF("#bl boot role=%s reset=%s boots=%u faults=%u\n", role, cause_name[cause], (unsigned)bl_guard_boots(),
             (unsigned)fault_count());
  fault_report();   /* prints "#fault ..." and clears the record */
#if defined(DEBUGGER_ENABLED) && (DEBUGGER_ENABLED == 1)
  __HAL_DBGMCU_FREEZE_IWDG();   /* a halted debug session must not reset the board */
#endif
  hiwdg.Instance = IWDG;
  hiwdg.Init.Prescaler = IWDG_PRESCALER;
  hiwdg.Init.Window = IWDG_WINDOW_DISABLE;
  hiwdg.Init.Reload = IWDG_RELOAD;
  if (HAL_IWDG_Init(&hiwdg) != HAL_OK) APP_PRINTF("#error iwdg init\n");   /* started either way */
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Guard, UTIL_SEQ_RFU, check);
  (void)UTIL_TIMER_Create(&check_timer, CHECK_PERIOD_MS, UTIL_TIMER_PERIODIC, request_check, NULL);
  (void)UTIL_TIMER_Start(&check_timer);
}

uint8_t bl_guard_reset_code(void) { return cause; }
const char *bl_guard_reset_name(void) { return cause_name[cause]; }
uint16_t bl_guard_boots(void) { return (uint16_t)fault_boots(); }   /* saturates at 0xFFFF (fault.c) */
uint8_t bl_guard_faults(void) { uint32_t n = fault_count(); return (uint8_t)(n > U8_MAX ? U8_MAX : n); }
uint32_t bl_guard_fault_pc(void) { return fault_last_pc(); }   /* fault_report() keeps the PC */
