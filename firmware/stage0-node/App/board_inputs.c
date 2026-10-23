/* The bench station's board inputs for the WSMP local modules (docs/hardware/bench-station-wiring.md):
 *   PC0  LPTIM1 IN1 (AF1): the anemometer reed switch, counted by hardware (board_pulse_count);
 *   PB2  ADC IN4: the wind vane divider, one conversion at a time by interrupt (board_vane_mv);
 *   PB5  EXTI5, falling edge: the rain gauge reed switch (mod_rain_tip);
 *   PB8, PB10  inputs with pull-up: the bq24074 PGOOD and CHG pins, active low (board_charger_pins).
 * The configurations follow ST's NUCLEO-WL55JC examples (LPTIM_PulseCounter, ADC_SingleConversion).
 * The pin map must be checked against UM2592 before the protoboard (the wiring guide's checklist). */
#include "board_inputs.h"
#include "clock.h"
#include "i2c_bus.h"
#include "mod_power.h"
#include "mod_rain.h"
#include "mod_wind.h"
#include "stm32wlxx_hal.h"

#define CUPS_PIN GPIO_PIN_0       /* PC0 */
#define VANE_PIN GPIO_PIN_2       /* PB2 */
#define RAIN_PIN GPIO_PIN_5       /* PB5 */
#define PGOOD_PIN GPIO_PIN_8      /* PB8 */
#define CHG_PIN GPIO_PIN_10       /* PB10 */
#define INPUT_IRQ_PRIORITY 2U     /* as the I2C and the console: below the radio and the RTC */
#define COUNTER_PERIOD 0xFFFFU    /* LPTIM1 counts freely over 16 bits */
#define ADC_FULL_SCALE 4095U
#define VDDA_MV 3300U             /* the vane's pull-up uses the same supply: the reading is a ratio */
#define VANE_RESTART_CALLS 3U     /* calls without a result (1 s apart) before the conversion starts again */

static LPTIM_HandleTypeDef hlptim1;
static ADC_HandleTypeDef hadc;
static volatile uint16_t vane_raw;
static volatile int vane_ready;
static unsigned vane_waits;   /* calls since the last result */

/* cppcheck-suppress constParameterPointer ; ST's HAL callback signature */
void HAL_LPTIM_MspInit(LPTIM_HandleTypeDef *h)
{
  if (h->Instance != LPTIM1) return;
  RCC_PeriphCLKInitTypeDef clk = { .PeriphClockSelection = RCC_PERIPHCLK_LPTIM1, .Lptim1ClockSelection = RCC_LPTIM1CLKSOURCE_LSE };
  (void)HAL_RCCEx_PeriphCLKConfig(&clk);
  __HAL_RCC_LPTIM1_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();
  GPIO_InitTypeDef gpio = { .Pin = CUPS_PIN, .Mode = GPIO_MODE_AF_PP, .Pull = GPIO_PULLUP, .Speed = GPIO_SPEED_FREQ_LOW,
                            .Alternate = GPIO_AF1_LPTIM1 };
  HAL_GPIO_Init(GPIOC, &gpio);
}

/* cppcheck-suppress constParameterPointer ; ST's HAL callback signature */
void HAL_ADC_MspInit(ADC_HandleTypeDef *h)
{
  if (h->Instance != ADC) return;
  __HAL_RCC_ADC_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  GPIO_InitTypeDef gpio = { .Pin = VANE_PIN, .Mode = GPIO_MODE_ANALOG, .Pull = GPIO_NOPULL };
  HAL_GPIO_Init(GPIOB, &gpio);
  HAL_NVIC_SetPriority(ADC_IRQn, INPUT_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(ADC_IRQn);
}

static void cups_init(void)
{
  hlptim1.Instance = LPTIM1;
  hlptim1.Init.Clock.Source = LPTIM_CLOCKSOURCE_APBCLOCK_LPOSC;
  hlptim1.Init.Clock.Prescaler = LPTIM_PRESCALER_DIV1;
  hlptim1.Init.UltraLowPowerClock.Polarity = LPTIM_CLOCKPOLARITY_FALLING;   /* a closing reed pulls PC0 low */
  /* An edge counts after 8 equal samples of the LSE kernel clock (244 us): reed bounce does not count,
     and 112 Hz (75 m/s, a 9 ms period) passes with a wide margin. */
  hlptim1.Init.UltraLowPowerClock.SampleTime = LPTIM_CLOCKSAMPLETIME_8TRANSITIONS;
  hlptim1.Init.Trigger.Source = LPTIM_TRIGSOURCE_SOFTWARE;
  hlptim1.Init.OutputPolarity = LPTIM_OUTPUTPOLARITY_HIGH;
  hlptim1.Init.UpdateMode = LPTIM_UPDATE_IMMEDIATE;
  hlptim1.Init.CounterSource = LPTIM_COUNTERSOURCE_EXTERNAL;
  hlptim1.Init.Input1Source = LPTIM_INPUT1SOURCE_GPIO;
  hlptim1.Init.Input2Source = LPTIM_INPUT2SOURCE_GPIO;
  if (HAL_LPTIM_Init(&hlptim1) == HAL_OK) (void)HAL_LPTIM_Counter_Start(&hlptim1, COUNTER_PERIOD);
}

static void vane_init(void)
{
  hadc.Instance = ADC;
  hadc.Init.ClockPrescaler = ADC_CLOCK_SYNC_PCLK_DIV4;
  hadc.Init.Resolution = ADC_RESOLUTION_12B;
  hadc.Init.DataAlign = ADC_DATAALIGN_RIGHT;
  hadc.Init.ScanConvMode = ADC_SCAN_DISABLE;
  hadc.Init.EOCSelection = ADC_EOC_SINGLE_CONV;
  hadc.Init.LowPowerAutoWait = DISABLE;
  hadc.Init.LowPowerAutoPowerOff = DISABLE;
  hadc.Init.ContinuousConvMode = DISABLE;
  hadc.Init.NbrOfConversion = 1;
  hadc.Init.DiscontinuousConvMode = DISABLE;
  hadc.Init.ExternalTrigConv = ADC_SOFTWARE_START;
  hadc.Init.DMAContinuousRequests = DISABLE;
  hadc.Init.Overrun = ADC_OVR_DATA_OVERWRITTEN;
  hadc.Init.SamplingTimeCommon1 = ADC_SAMPLETIME_160CYCLES_5;   /* the divider's source impedance is up to 10 kOhm */
  hadc.Init.OversamplingMode = DISABLE;
  hadc.Init.TriggerFrequencyMode = ADC_TRIGGER_FREQ_LOW;
  ADC_ChannelConfTypeDef ch = { .Channel = ADC_CHANNEL_4, .Rank = ADC_REGULAR_RANK_1, .SamplingTime = ADC_SAMPLINGTIME_COMMON_1 };
  if (HAL_ADC_Init(&hadc) != HAL_OK || HAL_ADC_ConfigChannel(&hadc, &ch) != HAL_OK) return;
  /* The offset calibration, once, before the first conversion: the closest vane positions are 30 mV
     apart (891 and 1000 ohm), a margin of 15 mV. Its wait is bounded (tools/blocking_report.py). If it
     fails, the vane still reads, with the factory offset. */
  (void)HAL_ADCEx_Calibration_Start(&hadc);
  (void)HAL_ADC_Start_IT(&hadc);
}

static void pins_init(void)
{
  __HAL_RCC_GPIOB_CLK_ENABLE();
  GPIO_InitTypeDef in = { .Pin = PGOOD_PIN | CHG_PIN, .Mode = GPIO_MODE_INPUT, .Pull = GPIO_PULLUP, .Speed = GPIO_SPEED_FREQ_LOW };
  HAL_GPIO_Init(GPIOB, &in);
  GPIO_InitTypeDef rain = { .Pin = RAIN_PIN, .Mode = GPIO_MODE_IT_FALLING, .Pull = GPIO_PULLUP, .Speed = GPIO_SPEED_FREQ_LOW };
  HAL_GPIO_Init(GPIOB, &rain);
  HAL_NVIC_SetPriority(EXTI9_5_IRQn, INPUT_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(EXTI9_5_IRQn);
}

void board_inputs_init(void)
{
  pins_init();
  cups_init();
  vane_init();
}

uint16_t board_pulse_count(void) { return (uint16_t)HAL_LPTIM_ReadCounter(&hlptim1); }

int board_vane_mv(uint16_t *mv)
{
  if (!vane_ready)
  {
    /* A conversion takes about 20 us. No result for three calls means its start was refused: start
       it again. A start while one runs is refused harmlessly (HAL_BUSY). */
    if (++vane_waits >= VANE_RESTART_CALLS) { vane_waits = 0; (void)HAL_ADC_Start_IT(&hadc); }
    return 0;
  }
  vane_waits = 0;
  vane_ready = 0;
  *mv = (uint16_t)((uint32_t)vane_raw * VDDA_MV / ADC_FULL_SCALE);
  (void)HAL_ADC_Start_IT(&hadc);   /* the next conversion; its interrupt sets vane_ready */
  return 1;
}

int board_charger_pins(void)
{
  int pins = 0;
  if (HAL_GPIO_ReadPin(GPIOB, PGOOD_PIN) == GPIO_PIN_RESET) pins |= (int)POWER_PGOOD;
  if (HAL_GPIO_ReadPin(GPIOB, CHG_PIN) == GPIO_PIN_RESET) pins |= (int)POWER_CHG;
  return pins;
}

/* The mux RESET line (i2c_bus.h). Its NUCLEO pin is TBD: it must pass the UM2592 checklist of the
   wiring guide first (sensor module ports design, section 4.1). Until it is wired the pulse does
   nothing, and a channel whose device holds SDA stays stuck until it is unplugged (section 4.3). */
void i2c_bus_mux_reset_line(int asserted) { (void)asserted; }

/* cppcheck-suppress constParameterPointer ; ST's HAL callback signature */
void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *h)
{
  if (h != &hadc) return;
  vane_raw = (uint16_t)HAL_ADC_GetValue(h);
  vane_ready = 1;
}

void HAL_GPIO_EXTI_Callback(uint16_t pin)
{
  if (pin == RAIN_PIN) mod_rain_tip(clock_ms());
}

void ADC_IRQHandler(void);        /* vector table names (startup_stm32wl55jcix.s) */
void EXTI9_5_IRQHandler(void);
void ADC_IRQHandler(void) { HAL_ADC_IRQHandler(&hadc); }
/* EXTI9_5 serves lines 5 to 9. The board's own GPIO setup also arms line 6 (button B3, PC6), so the
   handler serves every line: a pending line it skipped would re-enter this interrupt forever. Only
   the rain gauge's line reaches a module (HAL_GPIO_EXTI_Callback). */
void EXTI9_5_IRQHandler(void)
{
  static const uint16_t lines[] = { GPIO_PIN_5, GPIO_PIN_6, GPIO_PIN_7, GPIO_PIN_8, GPIO_PIN_9 };
  for (unsigned i = 0; i < sizeof lines / sizeof lines[0]; i++) HAL_GPIO_EXTI_IRQHandler(lines[i]);
}
