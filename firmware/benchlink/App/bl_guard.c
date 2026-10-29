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

/* RTC backup registers (TAMP->BKPxR), kept while the board has power. DR0-DR2 belong to SysTime
   (Core/Src/timer_if.c) and DR5-DR11 to the crash record (stage0-node/App/fault.c; DR6 the PC). DR12 holds this boot count. */
#define BKP(n) ((&TAMP->BKP0R)[n])
enum { BKP_FAULT_PC = 6, BKP_BOOTS = 12 };
#define U8_MAX 255U
#define U16_MAX 65535U

static IWDG_HandleTypeDef hiwdg;
static UTIL_TIMER_Object_t check_timer;
static uint8_t cause = BL_RESET_UNKNOWN;
static uint16_t boots;
static uint32_t fault_pc;
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
  /* The backup domain is cleared at power-on, so the count restarts with the power. */
  if (cause == BL_RESET_POWER) BKP(BKP_BOOTS) = 0;
  if (BKP(BKP_BOOTS) < U16_MAX) BKP(BKP_BOOTS) = BKP(BKP_BOOTS) + 1U;
  boots = (uint16_t)BKP(BKP_BOOTS);
  /* fault_report() clears only the magic, so DR6 keeps the PC of the latest crash. */
  if (fault_count()) fault_pc = BKP(BKP_FAULT_PC);
  APP_PRINTF("#bl boot role=%s reset=%s boots=%u faults=%u\n", role, cause_name[cause], (unsigned)boots,
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
uint16_t bl_guard_boots(void) { return boots; }
uint8_t bl_guard_faults(void) { uint32_t n = fault_count(); return (uint8_t)(n > U8_MAX ? U8_MAX : n); }
uint32_t bl_guard_fault_pc(void) { return fault_pc; }
