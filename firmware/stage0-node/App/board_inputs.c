/* The station's board inputs for the WSMP local modules and the power telemetry
 * (docs/hardware/bench-station-wiring.md; power telemetry design, section 9.5). The same MCU pins in the
 * bench and in the field. NUCLEO positions from UM2592 table 17 (ARDUINO) and table 18 (ST morpho):
 *   PB5  CN9.5 D4 (CN10.29)  LPTIM1_IN1 (AF1, DS13293 alternate function table): the anemometer reed
 *                   switch (cups), counted by hardware (board_pulse_count);
 *   PB2  CN8.2 A1   ADC1_IN4: the wind vane divider (board_vane_mv);
 *   PB1  CN8.1 A0   ADC1_IN5: the ISET node (10 kOhm series from the charger, 100 nF and 1 MOhm to
 *                   ground), analog, no pull (board_power_adc);
 *   PA10 CN8.3 A2   ADC1_IN6: the charger input (VBUS) through 20k (two 10k in series) over 10k, analog,
 *                   no pull: VIN = pin x POWER_VIN_DIVIDER_PPM / 1e6 (nominal 3, measured per record 4.4
 *                   step 12), full scale 3 x VDDA (9.9 V at 3.3 V) (board_power_adc);
 *   PB4  CN8.4 A3 (CN7.34)  EXTI4, falling edge: the rain gauge reed switch (mod_rain_tip); its reset
 *                   function NJTRST is released by this configuration (debug is SWD only);
 *   PB8  CN9.6 D5 (CN10.27)  input with pull-up: the bq24074 PGOOD pin, active low (board_charger_pins);
 *   PB10 CN9.7 D6 (CN10.25)  input with pull-up and EXTI10 on both edges: the bq24074 CHG pin, active
 *                   low (board_charger_pins), its edges counted for the 2 Hz fault flash (board_charger_edges);
 *   PA11 CN5.9 D14, PA12 CN5.10 D15: I2C2 SDA and SCL (App/i2c_bus.lit.md);
 *   PB14 CN8.5 A4 (CN7.36)  push-pull output, active low: the mux RESET when WS_I2C_MUX=1
 *                   (i2c_bus_mux_reset_line; build-progression record N5); untouched otherwise;
 *   PB12 CN9.3 D2, PB13 CN8.6 A5: driven as push-pull probe outputs by DBG_Init (sys_debug.c), always:
 *                   probe outputs, never free pins.
 * The ADC runs one interrupt-driven regular sequence: IN4 (vane), IN5 (ISET), IN6 (charger input),
 * VREFINT; 160.5 cycles each (VREFINT needs at least 4 us, DS13293 tS_vrefint; the divider's 6.67 kOhm
 * source needs at least 19.5 cycles, DS13293 table 82), hardware oversampling x16, shift 4. A sequence
 * takes about 0.9 ms at 12 MHz. The vane stays ratiometric (its pull-up shares VDDA: mod_wind.c keeps
 * the fixed 3300 "ratio mV"); VREFINT gives VDDA for the absolute inputs (board_power_adc).
 * The pull-up rule: PB8 and PB10 (FT_f) keep their internal pull-ups, so each must stay below
 * min(VDD, VDDA) + 0.3 V (DS13293 table 26 note 3; table 76 note 7): the bq24074 pins are open drain,
 * and the breakout's status LEDs must not pull them higher. The bench measured at most 2.9 V on USB;
 * the net the LED anodes go to is recorded in hardware/bench-breadboard-r0/source/wiring.toml.
 * PA10 (FT_fa) without a pull allows at most min(VDD, VDDA) + 3.6 V and 5.5 V (DS13293 table 26).
 * The configurations follow ST's NUCLEO-WL55JC examples (LPTIM_PulseCounter, ADC_SingleConversion).
 * Remapped at step 1 change B, approved by Clint 2026-10-30 (docs/superpowers/specs/
 * 2026-10-29-build-progression-decisions.md, record 7.1 N2; section 4.5): cups from PC0 (morpho only,
 * CN10.14) to PB5, rain from PB5 to PB4, so every station pin is on the Arduino headers. This file,
 * wiring.toml and tests/test_board_inputs.py move together. The power pins (PB1, PA10, PB8, PB10) do
 * not move.
 * The counter link probe (build-progression record M7 and its dated notes of 2026-10-30; board_inputs.h):
 * once at boot and every 15 minutes, in two phases on UTIL timers, so nothing waits at run time.
 * Phase 1: read the LPTIM1 count (c0); PB5 keeps its AF mode and only its PUPDR field turns to
 * pull-down; EXTI line 4 is masked and PB4 gets its pull-down; a one-shot of LINK_SETTLE_MS is armed.
 * Phase 2 (its expiry): read both pins, restore both pull-ups, clear the EXTI4 pending bit (an open
 * rain link fell while masked) and only then unmask, and read the count again (c1). LPTIM1's filter
 * (8 LSE samples, 244 us, cups_init) passes the 1 ms falling edge of an open cups link, so the
 * c1 - c0 pulses of the window are taken out of the count (cups_offset) and are no edge for the
 * probe; the count holds still through the window. A real cup pulse inside the window is lost with
 * them: at 75 m/s (112 Hz) that is at most one pulse per probe, under one at any realistic speed.
 * A rain tip inside the window is lost too (the line is masked); no probe ever makes one. */
#include "board_inputs.h"
#include "clock.h"
#include "i2c_bus.h"
#include "mod_power.h"
#include "mod_rain.h"
#include "mod_wind.h"
#include "oled_hooks.h"   /* WS_BENCH_OLED, 0 by default */
#if WS_BENCH_OLED
#include "oled_app.h"
#endif
#include "stm32_timer.h"
#include "stm32wlxx_hal.h"
#include "sys_conf.h"

/* The ST debug outputs that would drive the power and bus pins (sys_conf.h, sys_debug.c DBG_Init). */
_Static_assert(DEBUG_RF_HSE32RDY_ENABLED == 0, "DEBUG_RF_HSE32RDY drives PA10, the charger input divider");
_Static_assert(DEBUG_RF_NRESET_ENABLED == 0, "DEBUG_RF_NRESET drives PA11, I2C2 SDA");
_Static_assert(DEBUG_RF_BUSY_ENABLED == 0, "DEBUG_RF_BUSY drives PA12, I2C2 SCL");
_Static_assert(DEBUG_RF_SMPSRDY_ENABLED == 0, "DEBUG_RF_SMPSRDY drives PB2, the wind vane");
_Static_assert(DEBUG_RF_LDORDY_ENABLED == 0, "DEBUG_RF_LDORDY drives PB4, the rain gauge");

#define CUPS_PIN GPIO_PIN_5       /* PB5 = D4, CN9.5: LPTIM1_IN1 AF1 */
#define VANE_PIN GPIO_PIN_2       /* PB2 */
#define ISET_PIN GPIO_PIN_1 /* PB1 */
#define VIN_PIN GPIO_PIN_10 /* PA10 */
#define RAIN_PIN GPIO_PIN_4       /* PB4 = A3, CN8.4: EXTI4 */
#define PGOOD_PIN GPIO_PIN_8      /* PB8 */
#define CHG_PIN GPIO_PIN_10       /* PB10 */
#define MUX_RESET_PIN GPIO_PIN_14 /* PB14 = A4, CN8.5: the mux RESET, active low (N5) */
#define INPUT_IRQ_PRIORITY 2U     /* as the I2C and the console: below the radio and the RTC */
#define COUNTER_PERIOD 0xFFFFU    /* LPTIM1 counts freely over 16 bits */
#define ADC_FULL_SCALE 4095U
#define RATIO_MV 3300U            /* the vane's pull-up uses VDDA too: its reading is a ratio */
#define ADC_RESTART_CALLS 3U      /* calls without a new sequence before a start is tried again */
#define CUPS_BIT 5U               /* CUPS_PIN's position: its two PUPDR bits */
#define RAIN_BIT 4U               /* RAIN_PIN's position */
#define PUPD_MASK 3U              /* RM0453 GPIOx_PUPDR: two bits a pin, 01 pull-up, 10 pull-down */
#define PUPD_UP 1U
#define PUPD_DOWN 2U
#define LINK_SETTLE_MS 1U         /* the probe window: an open link falls in microseconds */
#define LINK_LOWS_MAX 0xFFFFU
_Static_assert((1U << CUPS_BIT) == CUPS_PIN && (1U << RAIN_BIT) == RAIN_PIN, "the PUPDR positions follow the pins");

enum { RANK_VANE, RANK_ISET, RANK_VIN, RANK_VREF, SEQ_LEN };

static LPTIM_HandleTypeDef hlptim1;
static ADC_HandleTypeDef hadc;
static int adc_ok;                          /* initialised and every channel configured */
static uint16_t conv[SEQ_LEN];              /* the running sequence (interrupt only) */
static unsigned rank;                       /* its next rank (interrupt only) */
static volatile uint16_t done[SEQ_LEN];     /* the latest complete sequence */
static volatile uint32_t done_seq;          /* complete sequences since boot */
static volatile uint32_t chg_edges;
struct adc_reader { uint32_t seen; unsigned waits; };
static struct adc_reader vane_reader, power_reader;
/* The link probe: written by its timer interrupts (and EXTI4 for rain_edge), read by the main loop. */
static UTIL_TIMER_Object_t link_period_timer, link_settle_timer;
static volatile uint16_t link_lows[BOARD_LINK_COUNT];
static volatile uint8_t probing;          /* a probe window is open */
static volatile uint8_t rain_edge;        /* a rain tip since the last probe */
static volatile uint16_t cups_offset;     /* the probes' own pulses, out of the count */
static volatile uint16_t cups_hold;       /* the count through a probe window */
static volatile uint16_t cups_at_probe;   /* the count at the last probe */
static uint16_t probe_c0;                 /* LPTIM1 at the window's start */

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
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  GPIO_InitTypeDef gpio = { .Pin = VANE_PIN | ISET_PIN, .Mode = GPIO_MODE_ANALOG, .Pull = GPIO_NOPULL };
  HAL_GPIO_Init(GPIOB, &gpio);
  gpio.Pin = VIN_PIN;
  HAL_GPIO_Init(GPIOA, &gpio);
  HAL_NVIC_SetPriority(ADC_IRQn, INPUT_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(ADC_IRQn);
}

static void cups_init(void)
{
  hlptim1.Instance = LPTIM1;
  hlptim1.Init.Clock.Source = LPTIM_CLOCKSOURCE_APBCLOCK_LPOSC;
  hlptim1.Init.Clock.Prescaler = LPTIM_PRESCALER_DIV1;
  hlptim1.Init.UltraLowPowerClock.Polarity = LPTIM_CLOCKPOLARITY_FALLING;   /* a closing reed pulls PB5 low */
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

/* The regular sequence, in rank order. All channels are configured here, once, before any start:
   never HAL_ADC_ConfigChannel while ADSTART is set. */
static int adc_channels(void)
{
  static const uint32_t channel[SEQ_LEN] = { ADC_CHANNEL_4, ADC_CHANNEL_5, ADC_CHANNEL_6, ADC_CHANNEL_VREFINT };
  static const uint32_t rank_of[SEQ_LEN] = { ADC_REGULAR_RANK_1, ADC_REGULAR_RANK_2, ADC_REGULAR_RANK_3, ADC_REGULAR_RANK_4 };
  for (unsigned i = 0; i < SEQ_LEN; i++)
  {
    ADC_ChannelConfTypeDef ch = { .Channel = channel[i], .Rank = rank_of[i], .SamplingTime = ADC_SAMPLINGTIME_COMMON_1 };
    if (HAL_ADC_ConfigChannel(&hadc, &ch) != HAL_OK) return 0;
  }
  return 1;
}

static void adc_init(void)
{
  hadc.Instance = ADC;
  hadc.Init.ClockPrescaler = ADC_CLOCK_SYNC_PCLK_DIV4;
  hadc.Init.Resolution = ADC_RESOLUTION_12B;
  hadc.Init.DataAlign = ADC_DATAALIGN_RIGHT;
  hadc.Init.ScanConvMode = ADC_SCAN_ENABLE;            /* fully configurable sequencer: ranks 1 to 4 */
  hadc.Init.EOCSelection = ADC_EOC_SINGLE_CONV;        /* one interrupt per channel: its result is read there */
  hadc.Init.LowPowerAutoWait = DISABLE;
  hadc.Init.LowPowerAutoPowerOff = DISABLE;
  hadc.Init.ContinuousConvMode = DISABLE;
  hadc.Init.NbrOfConversion = SEQ_LEN;
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
  if (HAL_ADC_Init(&hadc) != HAL_OK || !adc_channels()) return;
  adc_ok = 1;
  /* The offset calibration, once, before the first conversion: the closest vane positions are 30 mV
     apart (891 and 1000 ohm), a margin of 15 mV. Its wait is bounded (tools/blocking_report.py). If it
     fails, the inputs still read, with the factory offset. */
  (void)HAL_ADCEx_Calibration_Start(&hadc);
  (void)HAL_ADC_Start_IT(&hadc);
}

static void pins_init(void)
{
  __HAL_RCC_GPIOB_CLK_ENABLE();
  GPIO_InitTypeDef in = { .Pin = PGOOD_PIN, .Mode = GPIO_MODE_INPUT, .Pull = GPIO_PULLUP, .Speed = GPIO_SPEED_FREQ_LOW };
  HAL_GPIO_Init(GPIOB, &in);
  GPIO_InitTypeDef chg = { .Pin = CHG_PIN, .Mode = GPIO_MODE_IT_RISING_FALLING, .Pull = GPIO_PULLUP, .Speed = GPIO_SPEED_FREQ_LOW };
  HAL_GPIO_Init(GPIOB, &chg);
  GPIO_InitTypeDef rain = { .Pin = RAIN_PIN, .Mode = GPIO_MODE_IT_FALLING, .Pull = GPIO_PULLUP, .Speed = GPIO_SPEED_FREQ_LOW };
  HAL_GPIO_Init(GPIOB, &rain);
  HAL_NVIC_SetPriority(EXTI4_IRQn, INPUT_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(EXTI4_IRQn);
  /* For button B3 only (PC6, line 6): the board's GPIO setup (gpio.c, MX_GPIO_Init) arms its falling
     edge but enables no vector, so without this a press would leave line 6 pending for good. */
  HAL_NVIC_SetPriority(EXTI9_5_IRQn, INPUT_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(EXTI9_5_IRQn);
  HAL_NVIC_SetPriority(EXTI15_10_IRQn, INPUT_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(EXTI15_10_IRQn);
#if WS_BENCH_OLED
  /* The bench OLED's buttons B1 (PA0) and B2 (PA1): falling edge, internal pull-up (the NUCLEO's buttons
     pull the pin low). B3 is PC6 above. */
  __HAL_RCC_GPIOA_CLK_ENABLE();
  GPIO_InitTypeDef keys = { .Pin = GPIO_PIN_0 | GPIO_PIN_1, .Mode = GPIO_MODE_IT_FALLING, .Pull = GPIO_PULLUP,
                            .Speed = GPIO_SPEED_FREQ_LOW };
  HAL_GPIO_Init(GPIOA, &keys);
  HAL_NVIC_SetPriority(EXTI0_IRQn, INPUT_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(EXTI0_IRQn);
  HAL_NVIC_SetPriority(EXTI1_IRQn, INPUT_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(EXTI1_IRQn);
#endif
}

/* The mux RESET (PB14), only with the mux: released (high) before it becomes an output, so the mux
   sees no pulse at boot but the boot job's own (i2c_bus.lit.md). Without the mux PB14 stays as reset left it. */
static void mux_reset_init(void)
{
  if (WS_I2C_MUX != 1) return;   /* a value, not an #if: both profiles always compile (power-of-ten.md, rule 8) */
  HAL_GPIO_WritePin(GPIOB, MUX_RESET_PIN, GPIO_PIN_SET);
  GPIO_InitTypeDef out = { .Pin = MUX_RESET_PIN, .Mode = GPIO_MODE_OUTPUT_PP, .Pull = GPIO_NOPULL, .Speed = GPIO_SPEED_FREQ_LOW };
  HAL_GPIO_Init(GPIOB, &out);
}

/* The cup count: LPTIM1 less the probes' own pulses, held still through a probe window (one read,
   which may tear: mod_wind.c reads until two agree). */
uint16_t board_pulse_count(void)
{
  if (probing) return cups_hold;
  return (uint16_t)((uint16_t)HAL_LPTIM_ReadCounter(&hlptim1) - cups_offset);
}

/* LPTIM1 for the probe: its clock is the pulses, so a read can tear; after two reads that differ the
   counter has just moved, and pulses come at least 9 ms apart, so a third read stands. */
static uint16_t lptim_count(void)
{
  uint16_t a = (uint16_t)HAL_LPTIM_ReadCounter(&hlptim1), b = (uint16_t)HAL_LPTIM_ReadCounter(&hlptim1);
  return a == b ? a : (uint16_t)HAL_LPTIM_ReadCounter(&hlptim1);
}

/* The pull of one GPIOB pin and nothing else of it: PUPDR only, so the mode, the alternate function and
   the EXTI line stay as they are. A read-modify-write: at run time only the probe writes GPIOB's PUPDR. */
static void pull_set(unsigned bit, uint32_t pull)
{
  uint32_t shift = 2U * bit;
  GPIOB->PUPDR = (GPIOB->PUPDR & ~(PUPD_MASK << shift)) | (pull << shift);
}

static void link_note(enum board_link link, int low, int edge)
{
  uint16_t n = link_lows[link];
  if (!low) n = 0;
  else if (edge) n = 1;                       /* the link worked since the last probe: a new run */
  else if (n < LINK_LOWS_MAX) n++;
  link_lows[link] = n;
}

/* Phase 2, at the one-shot's expiry (read = 0 only when the one-shot was refused: restore, no verdict). */
static void link_probe_end(int read)
{
  int cups_low = HAL_GPIO_ReadPin(GPIOB, CUPS_PIN) == GPIO_PIN_RESET;
  int rain_low = HAL_GPIO_ReadPin(GPIOB, RAIN_PIN) == GPIO_PIN_RESET;
  pull_set(CUPS_BIT, PUPD_UP);
  pull_set(RAIN_BIT, PUPD_UP);
  __HAL_GPIO_EXTI_CLEAR_IT(RAIN_PIN);         /* an open link fell while masked: no tip */
  LL_EXTI_EnableIT_0_31(LL_EXTI_LINE_4);
  uint16_t c1 = lptim_count();
  cups_offset = (uint16_t)(cups_offset + (uint16_t)(c1 - probe_c0));
  probing = 0U;
  if (!read) return;
  link_note(BOARD_LINK_CUPS, cups_low, cups_hold != cups_at_probe);
  link_note(BOARD_LINK_RAIN, rain_low, rain_edge);
  cups_at_probe = cups_hold;
  rain_edge = 0U;
}

/* Phase 1: from boot (board_inputs_init) and the 15-minute timer. */
static void link_probe_start(void)
{
  if (probing) return;
  probe_c0 = lptim_count();
  cups_hold = (uint16_t)(probe_c0 - cups_offset);
  probing = 1U;
  LL_EXTI_DisableIT_0_31(LL_EXTI_LINE_4);
  pull_set(CUPS_BIT, PUPD_DOWN);
  pull_set(RAIN_BIT, PUPD_DOWN);
  if (UTIL_TIMER_Start(&link_settle_timer) != UTIL_TIMER_OK) link_probe_end(0);   /* never left pulled down */
}

static void on_link_period(void *ctx) { (void)ctx; link_probe_start(); }
static void on_link_settle(void *ctx) { (void)ctx; link_probe_end(1); }

static void link_probe_init(void)
{
  (void)UTIL_TIMER_Create(&link_settle_timer, LINK_SETTLE_MS, UTIL_TIMER_ONESHOT, on_link_settle, NULL);
  (void)UTIL_TIMER_Create(&link_period_timer, BOARD_LINK_PROBE_MS, UTIL_TIMER_PERIODIC, on_link_period, NULL);
  (void)UTIL_TIMER_Start(&link_period_timer);
  link_probe_start();
}

unsigned board_link_lows(enum board_link link) { return link < BOARD_LINK_COUNT ? link_lows[link] : 0U; }

int board_link_edge_seen(enum board_link link)
{
  if (link == BOARD_LINK_RAIN) return rain_edge != 0U;
  return board_pulse_count() != cups_at_probe;
}

void board_inputs_init(void)
{
  pins_init();
  mux_reset_init();
  cups_init();
  adc_init();
  link_probe_init();
}

/* 1 if a sequence completed since this reader's last one: the reader takes it, then starts the next
   (adc_next). A sequence takes about 0.9 ms; no new one for ADC_RESTART_CALLS calls means its start was
   refused or lost: start again. A start while one runs is refused harmlessly (HAL_BUSY), so the vane
   and the power readers can both start: whichever comes first. */
static int adc_fresh(struct adc_reader *r)
{
  uint32_t seq = done_seq;
  if (seq != r->seen) { r->seen = seq; r->waits = 0; return 1; }
  if (++r->waits >= ADC_RESTART_CALLS) { r->waits = 0; (void)HAL_ADC_Start_IT(&hadc); }
  return 0;
}

static void adc_next(void) { (void)HAL_ADC_Start_IT(&hadc); }   /* its last interrupt completes it */

int board_vane_mv(uint16_t *mv)
{
  if (!adc_ok || !adc_fresh(&vane_reader)) return 0;
  *mv = (uint16_t)((uint32_t)done[RANK_VANE] * RATIO_MV / ADC_FULL_SCALE);
  adc_next();
  return 1;
}

int board_power_adc(board_power_adc_t *out)
{
  if (!adc_ok) return -1;
  int fresh = adc_fresh(&power_reader);
  HAL_NVIC_DisableIRQ(ADC_IRQn);   /* one sequence: the interrupt does not update it half-way */
  uint32_t seq = done_seq;
  uint16_t iset = done[RANK_ISET], vin = done[RANK_VIN], vref = done[RANK_VREF];
  HAL_NVIC_EnableIRQ(ADC_IRQn);
  if (fresh) adc_next();
  if (seq == 0U || vref == 0U) return -1;
  uint32_t vdda = __HAL_ADC_CALC_VREFANALOG_VOLTAGE((uint32_t)vref, ADC_RESOLUTION_12B);
  if (vdda > UINT16_MAX) return -1;
  *out = (board_power_adc_t){ .iset_raw = iset, .vin_raw = vin, .vref_raw = vref, .vdda_mv = (uint16_t)vdda, .seq = seq };
  return 0;
}

uint32_t board_charger_edges(void) { return chg_edges; }

int board_charger_pins(void)
{
  int pins = 0;
  if (HAL_GPIO_ReadPin(GPIOB, PGOOD_PIN) == GPIO_PIN_RESET) pins |= (int)POWER_PGOOD;
  if (HAL_GPIO_ReadPin(GPIOB, CHG_PIN) == GPIO_PIN_RESET) pins |= (int)POWER_CHG;
  return pins;
}

/* The mux RESET line (i2c_bus.h): PB14 (A4, CN8.5 / morpho CN7.36; build-progression record N5),
   active low on the TCA9548A, wired with the mux (WS_I2C_MUX=1), once A4 is checked not to be
   tied to SDA. In the hub profile (WS_I2C_MUX=0) there is no mux: the call does nothing
   and PB14 is not driven. */
void i2c_bus_mux_reset_line(int asserted)
{
  if (WS_I2C_MUX == 1) HAL_GPIO_WritePin(GPIOB, MUX_RESET_PIN, asserted ? GPIO_PIN_RESET : GPIO_PIN_SET);
}

/* One call per conversion (EOC), in rank order; the last also has EOS. A sequence counts only when
   EOS comes after exactly SEQ_LEN results: a lost interrupt (an overrun) drops that sequence, and the
   next one starts at rank 1 again. */
/* cppcheck-suppress constParameterPointer ; ST's HAL callback signature */
void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *h)
{
  if (h != &hadc) return;
  uint16_t value = (uint16_t)HAL_ADC_GetValue(h);
  if (rank < SEQ_LEN) conv[rank] = value;
  if (rank <= SEQ_LEN) rank++;
  if (!__HAL_ADC_GET_FLAG(h, ADC_FLAG_EOS)) return;
  if (rank == SEQ_LEN)
  {
    for (unsigned i = 0; i < SEQ_LEN; i++) done[i] = conv[i];
    done_seq++;
  }
  rank = 0;
}

void HAL_GPIO_EXTI_Callback(uint16_t pin)
{
  if (pin == RAIN_PIN) { rain_edge = 1U; mod_rain_tip(clock_ms()); }
  if (pin == CHG_PIN) chg_edges++;
#if WS_BENCH_OLED
  if (pin == GPIO_PIN_0) oled_app_button(1U);   /* B1 */
  if (pin == GPIO_PIN_1) oled_app_button(2U);   /* B2 */
  if (pin == GPIO_PIN_6) oled_app_button(3U);   /* B3 */
#endif
}

void ADC_IRQHandler(void);        /* vector table names (startup_stm32wl55jcix.s, where EXTI4 is weak) */
void EXTI4_IRQHandler(void);
#if WS_BENCH_OLED
void EXTI0_IRQHandler(void);
void EXTI1_IRQHandler(void);
#endif
void EXTI9_5_IRQHandler(void);
void EXTI15_10_IRQHandler(void);
void ADC_IRQHandler(void) { HAL_ADC_IRQHandler(&hadc); }

/* Serves every line a vector owns: a pending line it skipped would re-enter that interrupt forever.
   HAL_GPIO_EXTI_IRQHandler clears a pending line, then calls HAL_GPIO_EXTI_Callback. */
static void exti_serve(const uint16_t *lines, unsigned n)
{
  for (unsigned i = 0; i < n; i++) HAL_GPIO_EXTI_IRQHandler(lines[i]);
}
#define EXTI_SERVE(lines) exti_serve((lines), (unsigned)(sizeof (lines) / sizeof (lines)[0]))

#if WS_BENCH_OLED
int board_button_up(unsigned b)
{
  if (b == 1U) return HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_0) == GPIO_PIN_SET;
  if (b == 2U) return HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_1) == GPIO_PIN_SET;
  if (b == 3U) return HAL_GPIO_ReadPin(GPIOC, GPIO_PIN_6) == GPIO_PIN_SET;
  return 0;
}

/* EXTI0 and EXTI1 own lines 0 and 1 alone: the bench buttons B1 (PA0) and B2 (PA1). */
void EXTI0_IRQHandler(void) { HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_0); }
void EXTI1_IRQHandler(void) { HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_1); }
#endif

/* EXTI4 owns line 4 alone: the rain gauge (PB4). */
void EXTI4_IRQHandler(void)
{
  static const uint16_t lines[] = { RAIN_PIN };
  EXTI_SERVE(lines);
}
/* EXTI9_5 serves lines 5 to 9 for button B3 only (PC6, line 6, armed by the board's GPIO setup). No
   station input is on these lines since change B (PB5 is the LPTIM1 input): none reaches a module. */
void EXTI9_5_IRQHandler(void)
{
  static const uint16_t lines[] = { GPIO_PIN_5, GPIO_PIN_6, GPIO_PIN_7, GPIO_PIN_8, GPIO_PIN_9 };
  EXTI_SERVE(lines);
}
/* EXTI15_10 serves lines 10 to 15: CHG (PB10) on line 10. */
void EXTI15_10_IRQHandler(void)
{
  static const uint16_t lines[] = { GPIO_PIN_10, GPIO_PIN_11, GPIO_PIN_12, GPIO_PIN_13, GPIO_PIN_14, GPIO_PIN_15 };
  EXTI_SERVE(lines);
}
