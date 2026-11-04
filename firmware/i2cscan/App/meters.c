/* The weather meter inputs (meters.h), the node's configuration (stage0-node/App/board_inputs.c) cut down
 * for the bench tool:
 *   PB5  CN9.5 D4   LPTIM1_IN1 (AF1), pull-up: the anemometer reed, counted by hardware, 8-sample LSE filter;
 *   PB2  CN8.2 A1   ADC1_IN4: the vane divider, 160.5 cycles, oversampling x16, polled (a bench tool);
 *   PB4  CN8.4 A3   EXTI4 falling, pull-up: the rain reed, a 100 ms lockout from the last edge (mod_rain.c).
 * The 10 kOhm pull-ups and the 100 nF filters are on the breadboard at the jacks. No link probe: an open
 * link shows here as a count that never moves and, for the vane, "OPEN". */
#include "meters.h"
#include "stm32wlxx_hal.h"

#define CUPS_PIN GPIO_PIN_5
#define VANE_PIN GPIO_PIN_2
#define RAIN_PIN GPIO_PIN_4
#define COUNTER_PERIOD 0xFFFFU
#define ADC_FULL_SCALE 4095U
#define RATIO_MV 3300U
#define ADC_TIMEOUT_MS 5U
#define RAIN_LOCKOUT_MS 100U
#define RAIN_IRQ_PRIORITY 2U

static LPTIM_HandleTypeDef hlptim1;
static ADC_HandleTypeDef hadc;
static int adc_ok;
static volatile uint32_t tips, last_edge_ms;
static volatile int had_edge;

/* cppcheck-suppress constParameterPointer ; ST's HAL callback signature */
void HAL_LPTIM_MspInit(LPTIM_HandleTypeDef *h)
{
  if (h->Instance != LPTIM1) return;
  RCC_PeriphCLKInitTypeDef clk = { .PeriphClockSelection = RCC_PERIPHCLK_LPTIM1, .Lptim1ClockSelection = RCC_LPTIM1CLKSOURCE_LSE };
  (void)HAL_RCCEx_PeriphCLKConfig(&clk);
  __HAL_RCC_LPTIM1_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  GPIO_InitTypeDef gpio = { .Pin = CUPS_PIN, .Mode = GPIO_MODE_AF_PP, .Pull = GPIO_PULLUP, .Speed = GPIO_SPEED_FREQ_LOW,
                            .Alternate = GPIO_AF1_LPTIM1 };
  HAL_GPIO_Init(GPIOB, &gpio);
}

/* cppcheck-suppress constParameterPointer ; ST's HAL callback signature */
void HAL_ADC_MspInit(ADC_HandleTypeDef *h)
{
  if (h->Instance != ADC) return;
  __HAL_RCC_ADC_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  GPIO_InitTypeDef gpio = { .Pin = VANE_PIN, .Mode = GPIO_MODE_ANALOG, .Pull = GPIO_NOPULL };
  HAL_GPIO_Init(GPIOB, &gpio);
}

static void cups_init(void)
{
  hlptim1.Instance = LPTIM1;
  hlptim1.Init.Clock.Source = LPTIM_CLOCKSOURCE_APBCLOCK_LPOSC;
  hlptim1.Init.Clock.Prescaler = LPTIM_PRESCALER_DIV1;
  hlptim1.Init.UltraLowPowerClock.Polarity = LPTIM_CLOCKPOLARITY_FALLING;
  hlptim1.Init.UltraLowPowerClock.SampleTime = LPTIM_CLOCKSAMPLETIME_8TRANSITIONS;
  hlptim1.Init.Trigger.Source = LPTIM_TRIGSOURCE_SOFTWARE;
  hlptim1.Init.OutputPolarity = LPTIM_OUTPUTPOLARITY_HIGH;
  hlptim1.Init.UpdateMode = LPTIM_UPDATE_IMMEDIATE;
  hlptim1.Init.CounterSource = LPTIM_COUNTERSOURCE_EXTERNAL;
  hlptim1.Init.Input1Source = LPTIM_INPUT1SOURCE_GPIO;
  hlptim1.Init.Input2Source = LPTIM_INPUT2SOURCE_GPIO;
  if (HAL_LPTIM_Init(&hlptim1) == HAL_OK) (void)HAL_LPTIM_Counter_Start(&hlptim1, COUNTER_PERIOD);
}

static void adc_init(void)
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
  hadc.Init.SamplingTimeCommon1 = ADC_SAMPLETIME_160CYCLES_5;
  hadc.Init.SamplingTimeCommon2 = ADC_SAMPLETIME_160CYCLES_5;
  hadc.Init.OversamplingMode = ENABLE;
  hadc.Init.Oversampling.Ratio = ADC_OVERSAMPLING_RATIO_16;
  hadc.Init.Oversampling.RightBitShift = ADC_RIGHTBITSHIFT_4;
  hadc.Init.Oversampling.TriggeredMode = ADC_TRIGGEREDMODE_SINGLE_TRIGGER;
  hadc.Init.TriggerFrequencyMode = ADC_TRIGGER_FREQ_LOW;
  if (HAL_ADC_Init(&hadc) != HAL_OK) return;
  ADC_ChannelConfTypeDef ch = { .Channel = ADC_CHANNEL_4, .Rank = ADC_REGULAR_RANK_1, .SamplingTime = ADC_SAMPLINGTIME_COMMON_1 };
  if (HAL_ADC_ConfigChannel(&hadc, &ch) != HAL_OK) return;
  (void)HAL_ADCEx_Calibration_Start(&hadc);
  adc_ok = 1;
}

static void rain_init(void)
{
  __HAL_RCC_GPIOB_CLK_ENABLE();
  GPIO_InitTypeDef rain = { .Pin = RAIN_PIN, .Mode = GPIO_MODE_IT_FALLING, .Pull = GPIO_PULLUP, .Speed = GPIO_SPEED_FREQ_LOW };
  HAL_GPIO_Init(GPIOB, &rain);
  HAL_NVIC_SetPriority(EXTI4_IRQn, RAIN_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(EXTI4_IRQn);
}

void meters_init(void)
{
  cups_init();
  adc_init();
  rain_init();
}

/* The counter's clock is the pulses, so a read can tear: read until two agree (at most three reads). */
uint16_t meters_cups(void)
{
  uint16_t a = (uint16_t)HAL_LPTIM_ReadCounter(&hlptim1), b = (uint16_t)HAL_LPTIM_ReadCounter(&hlptim1);
  return a == b ? a : (uint16_t)HAL_LPTIM_ReadCounter(&hlptim1);
}

uint32_t meters_tips(void) { return tips; }

int meters_vane_mv(uint16_t *mv)
{
  if (!adc_ok || HAL_ADC_Start(&hadc) != HAL_OK) return 0;
  int ok = HAL_ADC_PollForConversion(&hadc, ADC_TIMEOUT_MS) == HAL_OK;
  uint32_t raw = ok ? HAL_ADC_GetValue(&hadc) : 0U;
  (void)HAL_ADC_Stop(&hadc);
  if (!ok) return 0;
  *mv = (uint16_t)(raw * RATIO_MV / ADC_FULL_SCALE);
  return 1;
}

/* The lockout runs from the last edge, counted or not, so a chattering contact counts once (mod_rain.c). */
void HAL_GPIO_EXTI_Callback(uint16_t pin)
{
  if (pin != RAIN_PIN) return;
  uint32_t now = HAL_GetTick();
  if (!had_edge || now - last_edge_ms >= RAIN_LOCKOUT_MS) tips++;
  had_edge = 1;
  last_edge_ms = now;
}

void EXTI4_IRQHandler(void);   /* vector table name (startup_stm32wl55jcix.s, weak there) */
void EXTI4_IRQHandler(void) { HAL_GPIO_EXTI_IRQHandler(RAIN_PIN); }
