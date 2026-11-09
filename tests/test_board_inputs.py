"""The bench station's board inputs (firmware/stage0-node/App/board_inputs.c) on the host.

board_inputs.c is compiled unchanged against a small stand-in for ST's HAL (written below), which
models the EXTI pending flags, the GPIO input levels, output levels and pin set-up, the clocks
enabled for LPTIM1, and the ADC: its channel sequence, one conversion-complete interrupt per rank with
EOS on the last, and VREFINT_CAL. Since step 1 change B (build-progression record N2, approved
2026-10-30 in 7.1) the cups count on PB5 (LPTIM1_IN1, AF1) and the rain gauge is on PB4, served by
EXTI4 alone. The shared EXTI9_5 vector now serves only button B3 (PC6, line 6, unmasked by the board):
the handler must still clear every line it owns, or one press re-enters the interrupt forever.
EXTI15_10 serves CHG (PB10) on line 10, both edges (power telemetry design, section 9.5). A second
build with WS_I2C_MUX=1 drives the mux RESET on PB14 (record N5).

The counter link probe (record M7, its dated notes of 2026-10-30): the stand-in also models GPIOB's
MODER and PUPDR registers, the EXTI line 4 mask and pending bit, ST's UTIL timers (fired by the test)
and an open link on PB5 or PB4, whose level then follows its internal pull; LPTIM1 counts each falling
edge of PB5, as its filter passes the probe's 1 ms edge. The real App/mod_wind.c is linked too (its
window code stubbed), for the cups link verdict over the real probe."""
import ctypes
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from toolchain import CC_STRICT, ROOT, fresh_copy, host_library, needs_cc          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import CC_STRICT, ROOT, fresh_copy, host_library, needs_cc    # python -m unittest tests.<module>

HAL_STUB = r'''
#ifndef STUB_HAL_H
#define STUB_HAL_H
#include <stdint.h>
typedef enum { HAL_OK, HAL_ERROR, HAL_BUSY } HAL_StatusTypeDef;
typedef enum { GPIO_PIN_RESET, GPIO_PIN_SET } GPIO_PinState;
typedef struct { uint32_t MODER, PUPDR, idr, odr; } GPIO_TypeDef;
extern GPIO_TypeDef stub_gpioa, stub_gpiob, stub_gpioc;
#define GPIOA (&stub_gpioa)
#define GPIOB (&stub_gpiob)
#define GPIOC (&stub_gpioc)
#define GPIO_PIN_0 (1U << 0)
#define GPIO_PIN_1 (1U << 1)
#define GPIO_PIN_2 (1U << 2)
#define GPIO_PIN_3 (1U << 3)
#define GPIO_PIN_4 (1U << 4)
#define GPIO_PIN_5 (1U << 5)
#define GPIO_PIN_6 (1U << 6)
#define GPIO_PIN_7 (1U << 7)
#define GPIO_PIN_8 (1U << 8)
#define GPIO_PIN_9 (1U << 9)
#define GPIO_PIN_10 (1U << 10)
#define GPIO_PIN_11 (1U << 11)
#define GPIO_PIN_12 (1U << 12)
#define GPIO_PIN_13 (1U << 13)
#define GPIO_PIN_14 (1U << 14)
#define GPIO_PIN_15 (1U << 15)
enum { GPIO_MODE_INPUT, GPIO_MODE_ANALOG, GPIO_MODE_AF_PP, GPIO_MODE_IT_FALLING, GPIO_MODE_IT_RISING_FALLING, GPIO_MODE_OUTPUT_PP };
enum { GPIO_NOPULL, GPIO_PULLUP, GPIO_PULLDOWN };   /* as the PUPDR codes */
enum { GPIO_SPEED_FREQ_LOW };
enum { GPIO_AF1_LPTIM1 = 1 };
typedef struct { uint32_t Pin, Mode, Pull, Speed, Alternate; } GPIO_InitTypeDef;
void HAL_GPIO_Init(GPIO_TypeDef *port, GPIO_InitTypeDef *init);
GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef *port, uint16_t pin);
void HAL_GPIO_WritePin(GPIO_TypeDef *port, uint16_t pin, GPIO_PinState state);
void HAL_GPIO_EXTI_IRQHandler(uint16_t pin);
void HAL_GPIO_EXTI_Callback(uint16_t pin);
/* The EXTI line 4 mask and pending bit (stm32wlxx_ll_exti.h, stm32wlxx_hal_gpio.h). */
#define LL_EXTI_LINE_4 (1U << 4)
void LL_EXTI_DisableIT_0_31(uint32_t lines);
void LL_EXTI_EnableIT_0_31(uint32_t lines);
void stub_exti_clear(uint32_t lines);
#define __HAL_GPIO_EXTI_CLEAR_IT(lines) stub_exti_clear(lines)
typedef enum { EXTI0_IRQn = 6, EXTI1_IRQn = 7, EXTI4_IRQn = 10, ADC_IRQn = 18, EXTI9_5_IRQn = 22, EXTI15_10_IRQn = 39 } IRQn_Type;
void HAL_NVIC_SetPriority(IRQn_Type irq, uint32_t pre, uint32_t sub);
void HAL_NVIC_EnableIRQ(IRQn_Type irq);
void HAL_NVIC_DisableIRQ(IRQn_Type irq);
enum { RCC_PERIPHCLK_LPTIM1 = 1, RCC_LPTIM1CLKSOURCE_LSE = 2 };
typedef struct { uint32_t PeriphClockSelection, Lptim1ClockSelection; } RCC_PeriphCLKInitTypeDef;
HAL_StatusTypeDef HAL_RCCEx_PeriphCLKConfig(RCC_PeriphCLKInitTypeDef *clk);
#define __HAL_RCC_LPTIM1_CLK_ENABLE() ((void)0)
extern uint32_t stub_gpio_clk;   /* a bit for each port clock enabled: A 1, B 2, C 4 */
#define __HAL_RCC_GPIOA_CLK_ENABLE() (stub_gpio_clk |= 1U)
#define __HAL_RCC_GPIOB_CLK_ENABLE() (stub_gpio_clk |= 2U)
#define __HAL_RCC_GPIOC_CLK_ENABLE() (stub_gpio_clk |= 4U)
#define __HAL_RCC_ADC_CLK_ENABLE() ((void)0)
typedef struct { int unused; } LPTIM_TypeDef;
extern LPTIM_TypeDef stub_lptim1;
#define LPTIM1 (&stub_lptim1)
enum { LPTIM_CLOCKSOURCE_APBCLOCK_LPOSC, LPTIM_PRESCALER_DIV1, LPTIM_CLOCKPOLARITY_FALLING, LPTIM_CLOCKSAMPLETIME_DIRECTTRANSITION,
       LPTIM_CLOCKSAMPLETIME_8TRANSITIONS,
       LPTIM_TRIGSOURCE_SOFTWARE, LPTIM_OUTPUTPOLARITY_HIGH, LPTIM_UPDATE_IMMEDIATE, LPTIM_COUNTERSOURCE_EXTERNAL,
       LPTIM_INPUT1SOURCE_GPIO, LPTIM_INPUT2SOURCE_GPIO };
typedef struct { uint32_t Source, Prescaler; } LPTIM_ClockConfigTypeDef;
typedef struct { uint32_t Polarity, SampleTime; } LPTIM_ULPClockConfigTypeDef;
typedef struct { uint32_t Source; } LPTIM_TriggerConfigTypeDef;
typedef struct { LPTIM_ClockConfigTypeDef Clock; LPTIM_ULPClockConfigTypeDef UltraLowPowerClock; LPTIM_TriggerConfigTypeDef Trigger;
                 uint32_t OutputPolarity, UpdateMode, CounterSource, Input1Source, Input2Source; } LPTIM_InitTypeDef;
typedef struct { LPTIM_TypeDef *Instance; LPTIM_InitTypeDef Init; } LPTIM_HandleTypeDef;
HAL_StatusTypeDef HAL_LPTIM_Init(LPTIM_HandleTypeDef *h);
HAL_StatusTypeDef HAL_LPTIM_Counter_Start(LPTIM_HandleTypeDef *h, uint32_t period);
uint32_t HAL_LPTIM_ReadCounter(const LPTIM_HandleTypeDef *h);
void HAL_LPTIM_MspInit(LPTIM_HandleTypeDef *h);
typedef struct { int unused; } ADC_TypeDef;
extern ADC_TypeDef stub_adc;
#define ADC (&stub_adc)
#define ENABLE 1
#define DISABLE 0
enum { ADC_CLOCK_SYNC_PCLK_DIV4, ADC_RESOLUTION_12B, ADC_DATAALIGN_RIGHT, ADC_SCAN_ENABLE, ADC_EOC_SINGLE_CONV, ADC_SOFTWARE_START,
       ADC_OVR_DATA_OVERWRITTEN, ADC_SAMPLETIME_160CYCLES_5, ADC_TRIGGER_FREQ_LOW,
       ADC_REGULAR_RANK_1, ADC_REGULAR_RANK_2, ADC_REGULAR_RANK_3, ADC_REGULAR_RANK_4, ADC_SAMPLINGTIME_COMMON_1,
       ADC_OVERSAMPLING_RATIO_16, ADC_RIGHTBITSHIFT_4, ADC_TRIGGEREDMODE_SINGLE_TRIGGER };
/* The channel numbers as the sequence reports them (ADC_CHANNEL_VREFINT is IN13 on this part). */
#define ADC_CHANNEL_2 2U
#define ADC_CHANNEL_4 4U
#define ADC_CHANNEL_5 5U
#define ADC_CHANNEL_6 6U
#define ADC_CHANNEL_VREFINT 13U
typedef struct { uint32_t Ratio, RightBitShift, TriggeredMode; } ADC_OversamplingTypeDef;
typedef struct { uint32_t ClockPrescaler, Resolution, DataAlign, ScanConvMode, EOCSelection, LowPowerAutoWait, LowPowerAutoPowerOff,
                 ContinuousConvMode, NbrOfConversion, DiscontinuousConvMode, ExternalTrigConv, DMAContinuousRequests, Overrun,
                 SamplingTimeCommon1, SamplingTimeCommon2, OversamplingMode; ADC_OversamplingTypeDef Oversampling;
                 uint32_t TriggerFrequencyMode; } ADC_InitTypeDef;
typedef struct { ADC_TypeDef *Instance; ADC_InitTypeDef Init; } ADC_HandleTypeDef;
#define ADC_FLAG_EOS (1U << 3)
extern uint32_t stub_adc_isr;
#define __HAL_ADC_GET_FLAG(h, flag) ((void)(h), (stub_adc_isr & (flag)) == (flag))
/* As ST's (stm32wlxx_ll_adc.h): VREFINT_CAL is taken at VDDA = 3.3 V on this part. */
extern uint16_t stub_vrefint_cal;
#define VREFINT_CAL_ADDR ((const uint16_t *)&stub_vrefint_cal)
#define VREFINT_CAL_VREF 3300UL
#define __HAL_ADC_CALC_VREFANALOG_VOLTAGE(data, res) ((void)(res), ((uint32_t)(*VREFINT_CAL_ADDR) * VREFINT_CAL_VREF) / (data))
typedef struct { uint32_t Channel, Rank, SamplingTime; } ADC_ChannelConfTypeDef;
HAL_StatusTypeDef HAL_ADC_Init(ADC_HandleTypeDef *h);
HAL_StatusTypeDef HAL_ADC_ConfigChannel(ADC_HandleTypeDef *h, ADC_ChannelConfTypeDef *c);
HAL_StatusTypeDef HAL_ADC_Start_IT(ADC_HandleTypeDef *h);
HAL_StatusTypeDef HAL_ADCEx_Calibration_Start(ADC_HandleTypeDef *h);
uint32_t HAL_ADC_GetValue(const ADC_HandleTypeDef *h);
void HAL_ADC_IRQHandler(ADC_HandleTypeDef *h);
void HAL_ADC_MspInit(ADC_HandleTypeDef *h);
void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *h);
#endif
'''

TIMER_STUB = r'''
#ifndef STUB_TIMER_H
#define STUB_TIMER_H
/* ST's UTIL timer server (stm32_timer.h), as far as board_inputs.c uses it: the test fires them. */
#include <stdint.h>
typedef enum { UTIL_TIMER_ONESHOT, UTIL_TIMER_PERIODIC } UTIL_TIMER_Mode_t;
typedef enum { UTIL_TIMER_OK, UTIL_TIMER_INVALID_PARAM, UTIL_TIMER_HW_ERROR, UTIL_TIMER_UNKNOWN_ERROR } UTIL_TIMER_Status_t;
typedef struct { uint32_t period; UTIL_TIMER_Mode_t mode; void (*callback)(void *); void *argument; int running; } UTIL_TIMER_Object_t;
UTIL_TIMER_Status_t UTIL_TIMER_Create(UTIL_TIMER_Object_t *t, uint32_t period, UTIL_TIMER_Mode_t mode, void (*callback)(void *),
                                      void *argument);
UTIL_TIMER_Status_t UTIL_TIMER_Start(UTIL_TIMER_Object_t *t);
#endif
'''

SHIM = r'''
#include <stdint.h>
#include "stm32wlxx_hal.h"
#include "board_inputs.h"
#include "i2c_bus.h"
#include "mod_power.h"
#include "mod_wind.h"
#include "mod_mean.h"
#include "stm32_timer.h"
#include "wsmp_local.h"
GPIO_TypeDef stub_gpioa, stub_gpiob, stub_gpioc;
LPTIM_TypeDef stub_lptim1;
ADC_TypeDef stub_adc;
uint32_t stub_adc_isr;
uint32_t stub_gpio_clk;
uint16_t stub_vrefint_cal = 1504;
static int tips, adc_starts, adc_fail_next, adc_calibrated_first = -1, adc_irq_disabled;
static uint32_t lptim_sample_time, lptim_clk;
static uint64_t irq_enabled;
static uint32_t irq_priority[64];
static uint32_t adc_value;
static ADC_HandleTypeDef *adc;
static uint32_t seq_channel[8], seq_rank[8], seq_n, config_after_start;
/* [port A, B, C][pin]: the last HAL_GPIO_Init, the number of them, and the output level it found. */
static struct { uint32_t mode, pull, alt, inits, odr_at_init; } pin_mode[3][16];
static int port_index(const GPIO_TypeDef *port) { return port == GPIOA ? 0 : port == GPIOB ? 1 : 2; }
static uint32_t exti_imr;   /* the EXTI interrupt mask: a bit for each unmasked line */
/* MODER codes (RM0453: 00 input, 01 output, 10 alternate, 11 analog) of the stand-in's modes. */
static const uint32_t moder_of[] = { 0U, 3U, 2U, 0U, 0U, 1U };
static void registers(GPIO_TypeDef *port, unsigned n, const GPIO_InitTypeDef *init)
{
  port->MODER = (port->MODER & ~(3U << (2U * n))) | (moder_of[init->Mode] << (2U * n));
  port->PUPDR = (port->PUPDR & ~(3U << (2U * n))) | (init->Pull << (2U * n));
  if (init->Mode == GPIO_MODE_IT_FALLING || init->Mode == GPIO_MODE_IT_RISING_FALLING) exti_imr |= 1U << n;
}
void HAL_GPIO_Init(GPIO_TypeDef *port, GPIO_InitTypeDef *init)
{
  for (unsigned n = 0; n < 16; n++)
  {
    if (!(init->Pin & (1U << n))) continue;
    registers(port, n, init);
    pin_mode[port_index(port)][n].mode = init->Mode;
    pin_mode[port_index(port)][n].pull = init->Pull;
    pin_mode[port_index(port)][n].alt = init->Alternate;
    pin_mode[port_index(port)][n].inits++;
    pin_mode[port_index(port)][n].odr_at_init = (port->odr >> n) & 1U;
  }
}
/* An open link (a bit for each of PB4, PB5): the pin follows its own pull, pulled up or down. */
static uint32_t link_open, link_level = (1U << 4) | (1U << 5);
static uint32_t lptim_count = 1234;
static uint32_t level_b(unsigned n)
{
  if (!(link_open & (1U << n))) return (stub_gpiob.idr >> n) & 1U;
  return ((stub_gpiob.PUPDR >> (2U * n)) & 3U) == GPIO_PULLUP;
}
/* The levels of the open links now: a falling PB5 is a pulse for LPTIM1, a falling PB4 sets its EXTI
   pending bit, masked or not. (The other tests raise their own lines: an intact link has no edges.) */
static uint32_t exti_pending;
static void link_sync(void)
{
  for (unsigned n = 4; n <= 5; n++)
  {
    uint32_t level = level_b(n);
    int falls = ((link_level >> n) & 1U) && !level && (link_open & (1U << n));
    if (falls && n == 5) lptim_count++;
    if (falls && n == 4) exti_pending |= 1U << n;
    link_level = (link_level & ~(1U << n)) | (level << n);
  }
}
GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef *port, uint16_t pin)
{
  if (port == GPIOB) link_sync();
  if (port == GPIOB && (pin & ((1U << 4) | (1U << 5)))) return level_b(pin == (1U << 4) ? 4U : 5U) ? GPIO_PIN_SET : GPIO_PIN_RESET;
  return (port->idr & pin) ? GPIO_PIN_SET : GPIO_PIN_RESET;
}
static uint32_t gpio_writes[3];
void HAL_GPIO_WritePin(GPIO_TypeDef *port, uint16_t pin, GPIO_PinState state)
{
  gpio_writes[port_index(port)]++;
  if (state == GPIO_PIN_SET) port->odr |= pin; else port->odr &= ~(uint32_t)pin;
}
/* As ST's: serves one line if it is pending: clear its flag, then the callback. */
void HAL_GPIO_EXTI_IRQHandler(uint16_t pin)
{
  if (exti_pending & pin) { exti_pending &= ~(uint32_t)pin; HAL_GPIO_EXTI_Callback(pin); }
}
/* The order of the probe's EXTI steps: each records when it came (one count for all). */
static uint32_t exti_steps, cleared_at, unmasked_at;
void LL_EXTI_DisableIT_0_31(uint32_t lines) { exti_imr &= ~lines; }
void LL_EXTI_EnableIT_0_31(uint32_t lines) { exti_imr |= lines; unmasked_at = ++exti_steps; }
void stub_exti_clear(uint32_t lines) { exti_pending &= ~lines; cleared_at = ++exti_steps; }
/* The UTIL timers board_inputs.c creates, and the test's firing of them. */
static UTIL_TIMER_Object_t *timers[4];
static unsigned n_timers;
static int refuse_starts;
UTIL_TIMER_Status_t UTIL_TIMER_Create(UTIL_TIMER_Object_t *t, uint32_t period, UTIL_TIMER_Mode_t mode, void (*callback)(void *),
                                      void *argument)
{
  *t = (UTIL_TIMER_Object_t){ .period = period, .mode = mode, .callback = callback, .argument = argument };
  if (n_timers < 4) timers[n_timers++] = t;
  return UTIL_TIMER_OK;
}
UTIL_TIMER_Status_t UTIL_TIMER_Start(UTIL_TIMER_Object_t *t)
{
  if (refuse_starts > 0) { refuse_starts--; return UTIL_TIMER_HW_ERROR; }
  t->running = 1;
  return UTIL_TIMER_OK;
}
static UTIL_TIMER_Object_t *timer_of(uint32_t period)
{
  for (unsigned i = 0; i < n_timers; i++) if (timers[i]->period == period) return timers[i];
  return 0;
}
/* 1 if a running timer of this period expired (a one-shot stops first, as ST's does). */
int t_fire(uint32_t period)
{
  UTIL_TIMER_Object_t *t = timer_of(period);
  if (!t || !t->running) return 0;
  link_sync();
  if (t->mode == UTIL_TIMER_ONESHOT) t->running = 0;
  t->callback(t->argument);
  return 1;
}
int t_timer_running(uint32_t period) { const UTIL_TIMER_Object_t *t = timer_of(period); return t && t->running; }
int t_timer_mode(uint32_t period) { const UTIL_TIMER_Object_t *t = timer_of(period); return t ? (int)t->mode : -1; }
void t_refuse_starts(int n) { refuse_starts = n; }
void t_link_open(uint32_t pins) { link_open = pins; link_sync(); }
void t_cup_pulses(uint32_t n) { lptim_count += n; }
uint32_t t_moder(int pin) { return (stub_gpiob.MODER >> (2U * (unsigned)pin)) & 3U; }
uint32_t t_pupdr(int pin) { return (stub_gpiob.PUPDR >> (2U * (unsigned)pin)) & 3U; }
uint32_t t_pupdr_c(int pin) { return (stub_gpioc.PUPDR >> (2U * (unsigned)pin)) & 3U; }
uint32_t t_exti_masked(int line) { return !((exti_imr >> line) & 1U); }
uint32_t t_cleared_at(void) { return cleared_at; }
uint32_t t_unmasked_at(void) { return unmasked_at; }
/* mod_wind.c's window and identity code is not under test here: stand-ins. */
void mean_reset(mean_win *w, uint32_t now_ms) { (void)w; (void)now_ms; }
int mean_close(mean_win *w, uint16_t token, uint32_t now_ms, uint32_t boot_id, const uint8_t desc[WSMP_DESC_BLOCK_LEN],
               unsigned channels, wsmp_snapshot *snap)
{ (void)w; (void)token; (void)now_ms; (void)boot_id; (void)desc; (void)channels; (void)snap; return 0; }
void mean_store(mean_win *w, const wsmp_snapshot *snap) { (void)w; (void)snap; }
uint8_t mean_quality(const wsmp_snapshot *snap, unsigned samples) { (void)snap; (void)samples; return 0; }
void wsmp_pack_desc(const wsmp_desc *d, unsigned n, uint8_t out[WSMP_DESC_BLOCK_LEN]) { (void)d; (void)n; (void)out; }
void local_pack_identity(enum wsmp_port p, uint16_t type, uint8_t channels, uint32_t boot_id,
                         const uint8_t desc[WSMP_DESC_BLOCK_LEN], uint8_t id[WSMP_IDENTITY_LEN])
{ (void)p; (void)type; (void)channels; (void)boot_id; (void)desc; (void)id; }
void HAL_NVIC_SetPriority(IRQn_Type irq, uint32_t pre, uint32_t sub) { (void)sub; irq_priority[irq] = pre; }
void HAL_NVIC_EnableIRQ(IRQn_Type irq) { irq_enabled |= 1ULL << irq; if (irq == ADC_IRQn) adc_irq_disabled = 0; }
void HAL_NVIC_DisableIRQ(IRQn_Type irq) { if (irq == ADC_IRQn) adc_irq_disabled = 1; }
HAL_StatusTypeDef HAL_RCCEx_PeriphCLKConfig(RCC_PeriphCLKInitTypeDef *clk) { (void)clk; return HAL_OK; }
/* Records the port clocks the LPTIM1 set-up enables itself (HAL_LPTIM_MspInit). */
HAL_StatusTypeDef HAL_LPTIM_Init(LPTIM_HandleTypeDef *h)
{
  lptim_sample_time = h->Init.UltraLowPowerClock.SampleTime;
  stub_gpio_clk = 0; HAL_LPTIM_MspInit(h); lptim_clk = stub_gpio_clk;
  return HAL_OK;
}
HAL_StatusTypeDef HAL_LPTIM_Counter_Start(LPTIM_HandleTypeDef *h, uint32_t period) { (void)h; (void)period; return HAL_OK; }
uint32_t HAL_LPTIM_ReadCounter(const LPTIM_HandleTypeDef *h) { (void)h; link_sync(); return lptim_count & 0xFFFFU; }
HAL_StatusTypeDef HAL_ADC_Init(ADC_HandleTypeDef *h) { adc = h; HAL_ADC_MspInit(h); return HAL_OK; }
/* Records the sequence: rank r (ADC_REGULAR_RANK_1 + r) converts channel c. */
HAL_StatusTypeDef HAL_ADC_ConfigChannel(ADC_HandleTypeDef *h, ADC_ChannelConfTypeDef *c)
{
  (void)h;
  if (adc_starts) config_after_start++;   /* a configuration after the first start */
  if (seq_n < 8) { seq_channel[seq_n] = c->Channel; seq_rank[seq_n] = c->Rank; seq_n++; }
  return HAL_OK;
}
HAL_StatusTypeDef HAL_ADC_Start_IT(ADC_HandleTypeDef *h)
{
  (void)h; if (adc_calibrated_first < 0) adc_calibrated_first = 0;
  adc_starts++;
  if (adc_fail_next) { adc_fail_next = 0; return HAL_ERROR; }
  return HAL_OK;
}
HAL_StatusTypeDef HAL_ADCEx_Calibration_Start(ADC_HandleTypeDef *h) { (void)h; if (adc_calibrated_first < 0) adc_calibrated_first = 1; return HAL_OK; }
uint32_t HAL_ADC_GetValue(const ADC_HandleTypeDef *h) { (void)h; return adc_value; }
/* As ST's for a software-started sequence: one callback per EOC, EOS set with the last one. */
void HAL_ADC_IRQHandler(ADC_HandleTypeDef *h) { HAL_ADC_ConvCpltCallback(h); stub_adc_isr = 0; }
uint32_t clock_ms(void) { return 0; }
void mod_rain_tip(uint32_t now_ms) { (void)now_ms; tips++; }
void ADC_IRQHandler(void);
void EXTI4_IRQHandler(void);
void EXTI9_5_IRQHandler(void);
void EXTI15_10_IRQHandler(void);
void t_init(void) { board_inputs_init(); }
void t_exti_raise(uint32_t lines) { exti_pending |= lines; }
uint32_t t_exti_pending(void) { return exti_pending; }
void t_exti_irq(void) { EXTI9_5_IRQHandler(); }
void t_exti4_irq(void) { EXTI4_IRQHandler(); }
void t_exti15_10_irq(void) { EXTI15_10_IRQHandler(); }
int t_tips(void) { return tips; }
void t_pins(uint32_t idr) { stub_gpiob.idr = idr; }
void t_idr(int port, uint32_t idr) { (port == 0 ? &stub_gpioa : port == 1 ? &stub_gpiob : &stub_gpioc)->idr = idr; }
/* One conversion's interrupt; last = it ends the sequence (EOS). */
void t_adc_conv(uint32_t value, int last) { adc_value = value; stub_adc_isr = last ? ADC_FLAG_EOS : 0U; ADC_IRQHandler(); }
/* A whole sequence, in rank order: vane, ISET, charger input, VREFINT. */
void t_adc_seq(uint32_t vane, uint32_t iset, uint32_t vin, uint32_t vref)
{
  t_adc_conv(vane, 0); t_adc_conv(iset, 0); t_adc_conv(vin, 0); t_adc_conv(vref, 1);
}
void t_adc_done(uint32_t vane) { t_adc_seq(vane, 100, 200, 1504); }
int t_adc_starts(void) { return adc_starts; }
void t_adc_fail_next(void) { adc_fail_next = 1; }
int t_adc_calibrated_first(void) { return adc_calibrated_first; }
int t_adc_irq_disabled(void) { return adc_irq_disabled; }
uint32_t t_seq_n(void) { return seq_n; }
uint32_t t_seq_channel(uint32_t i) { return seq_channel[i]; }
uint32_t t_seq_rank(uint32_t i) { return seq_rank[i]; }
uint32_t t_config_after_start(void) { return config_after_start; }
uint32_t t_adc_init(uint32_t field)
{
  const ADC_InitTypeDef *i = &adc->Init;
  const uint32_t v[] = { i->ScanConvMode, i->NbrOfConversion, i->EOCSelection, i->SamplingTimeCommon1, i->OversamplingMode,
                         i->Oversampling.Ratio, i->Oversampling.RightBitShift, i->ContinuousConvMode };
  return v[field];
}
void t_vrefint_cal(uint16_t cal) { stub_vrefint_cal = cal; }
uint32_t t_pin_mode(int port, int pin) { return pin_mode[port][pin].mode; }
uint32_t t_pin_pull(int port, int pin) { return pin_mode[port][pin].pull; }
uint32_t t_pin_alt(int port, int pin) { return pin_mode[port][pin].alt; }
uint32_t t_pin_inits(int port, int pin) { return pin_mode[port][pin].inits; }
uint32_t t_pin_odr_at_init(int port, int pin) { return pin_mode[port][pin].odr_at_init; }
uint32_t t_pin_level(int port, int pin) { return ((port == 0 ? stub_gpioa : port == 1 ? stub_gpiob : stub_gpioc).odr >> pin) & 1U; }
uint32_t t_gpio_writes(int port) { return gpio_writes[port]; }
uint32_t t_lptim_clk(void) { return lptim_clk; }
uint32_t t_irq_enabled(int irq) { return (uint32_t)(irq_enabled >> irq) & 1U; }
uint32_t t_irq_priority(int irq) { return irq_priority[irq]; }
void t_mux_reset(int asserted) { i2c_bus_mux_reset_line(asserted); }
uint32_t t_lptim_sample_time(void) { return lptim_sample_time; }
/* The HAL names the tests compare against. */
const uint32_t k_scan_enable = ADC_SCAN_ENABLE, k_eoc_single = ADC_EOC_SINGLE_CONV, k_160_5 = ADC_SAMPLETIME_160CYCLES_5,
               k_ovs_16 = ADC_OVERSAMPLING_RATIO_16, k_shift_4 = ADC_RIGHTBITSHIFT_4, k_rank_1 = ADC_REGULAR_RANK_1,
               k_analog = GPIO_MODE_ANALOG, k_input = GPIO_MODE_INPUT, k_it_both = GPIO_MODE_IT_RISING_FALLING,
               k_it_falling = GPIO_MODE_IT_FALLING, k_nopull = GPIO_NOPULL, k_pullup = GPIO_PULLUP,
               k_af_pp = GPIO_MODE_AF_PP, k_af1_lptim1 = GPIO_AF1_LPTIM1, k_output_pp = GPIO_MODE_OUTPUT_PP,
               k_exti4 = EXTI4_IRQn, k_exti9_5 = EXTI9_5_IRQn, k_pulldown = GPIO_PULLDOWN;
int t_vane(uint16_t *mv) { return board_vane_mv(mv); }
int t_power(board_power_adc_t *out) { return board_power_adc(out); }
'''

PIN = {n: 1 << n for n in range(16)}
PORT = {'A': 0, 'B': 1, 'C': 2}
APP = ROOT/'firmware/stage0-node/App'
BOARD_INC = ROOT/'firmware/board/nucleo-wl55jc/Core/Inc'
SOURCE = APP/'board_inputs.c'
WIND = APP/'mod_wind.c'
PROBE_MS, SETTLE_MS = 900_000, 1        # every 15 minutes; the window, about 1 ms (record M7)
CUPS, RAIN = 0, 1                       # enum board_link
METER_OK, CUPS_SUSPECT, VANE_OUT, CUPS_OPEN, RAIN_OPEN = range(5)   # enum meter_link
MODER_AF, PUPD_UP, PUPD_DOWN = 2, 1, 2  # RM0453 GPIOx_MODER and GPIOx_PUPDR codes


def include_flags(stub_dir, *first):
    """The include path of a board_inputs.c build: the HAL stand-in, then any directory in first (one
    that overrides a board header), then the station's own."""
    return ['-I', stub_dir, *(x for d in first for x in ('-I', d)), '-I', APP, '-I', ROOT/'firmware/common',
            '-I', ROOT/'firmware', '-I', BOARD_INC]


# The bench build's button forward (App/oled_app.c is not linked here): the presses it was given.
BENCH_SHIM = r'''
#include "oled_app.h"
unsigned t_presses[4];
void oled_app_button(unsigned b) { if (b < 4U) t_presses[b]++; }
'''


def build(owner, name, *defines, bench=False, board_inc=()):
    """board_inputs.c and the shim as a host library, with the HAL stand-in (owner is the TestCase class);
    bench: WS_BENCH_OLED=1, with a stand-in for the display's button forward; board_inc: another board's
    Core/Inc ahead of the NUCLEO's (its board_pins.h)."""
    owner.stub = tempfile.TemporaryDirectory()
    owner.addClassCleanup(owner.stub.cleanup)
    (Path(owner.stub.name)/'stm32wlxx_hal.h').write_text(HAL_STUB)
    (Path(owner.stub.name)/'stm32_timer.h').write_text(TIMER_STUB)
    # sys_conf.h is the board's own: board_inputs.c asserts its RF debug outputs are off.
    files = {'shim.c': SHIM, **({'bench.c': BENCH_SHIM} if bench else {})}
    return host_library(owner, name, *defines, *(('-DWS_BENCH_OLED=1',) if bench else ()), *include_flags(owner.stub.name, *board_inc),
                        SOURCE, WIND, files=files)


class PowerAdc(ctypes.Structure):
    """board_power_adc_t (App/board_inputs.h)."""
    _fields_ = [('iset_raw', ctypes.c_uint16), ('vin_raw', ctypes.c_uint16), ('vref_raw', ctypes.c_uint16),
                ('vdda_mv', ctypes.c_uint16), ('seq', ctypes.c_uint32)]


def vdda_mv(vrefint_cal, vref_raw):
    """VDDA from a VREFINT pair (DS13293 table 14: VREFINT_CAL is taken at VDDA = 3.3 V; RM0461)."""
    return 3300 * vrefint_cal // vref_raw


@needs_cc
class BoardInputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = build(cls, 'boardinputs')      # the firmware default: WS_I2C_MUX 0, the STEMMA QT hub
        cls.lib.t_init()
        cls.lib.t_fire(SETTLE_MS)                # the boot probe's second phase: the pull-ups are back

    def k(self, name):
        return ctypes.c_uint32.in_dll(self.lib, f'k_{name}').value

    def power(self):
        out = PowerAdc()
        return self.lib.t_power(ctypes.byref(out)), out

    def test_every_line_of_the_shared_vector_is_cleared(self):
        # Button B3 (PC6) is configured with a falling-edge interrupt by the board's own GPIO setup,
        # which enables no vector: EXTI9_5 stays enabled for it alone, and one press must not leave
        # its line pending.
        self.assertEqual(self.lib.t_irq_enabled(self.k('exti9_5')), 1)
        self.lib.t_exti_raise(PIN[5] | PIN[6] | PIN[7] | PIN[8] | PIN[9])
        self.lib.t_exti_irq()
        self.assertEqual(self.lib.t_exti_pending(), 0)

    def test_a_rain_tip_reaches_the_rain_module_through_exti4(self):
        # Change B (record N2): the rain gauge is PB4, line 4, on its own vector EXTI4.
        self.assertEqual(self.lib.t_irq_enabled(self.k('exti4')), 1)
        self.assertEqual(self.lib.t_irq_priority(self.k('exti4')), 2)   # INPUT_IRQ_PRIORITY, as EXTI15_10
        before = self.lib.t_tips()
        self.lib.t_exti_raise(PIN[4])
        self.lib.t_exti4_irq()
        self.assertEqual(self.lib.t_exti_pending(), 0)
        self.assertEqual(self.lib.t_tips(), before + 1)

    def test_exti9_5_no_longer_reaches_the_rain_module(self):
        # Line 5 (PB5) is the cups' LPTIM1 input now, not an interrupt; line 6 is button B3.
        before = self.lib.t_tips()
        for lines in (PIN[5], PIN[6], PIN[5] | PIN[6]):
            self.lib.t_exti_raise(lines)
            self.lib.t_exti_irq()
        self.assertEqual(self.lib.t_exti_pending(), 0)
        self.assertEqual(self.lib.t_tips(), before)

    def test_the_cups_count_on_pb5_with_lptim1_in1(self):
        # PB5 = D4, CN9.5: LPTIM1_IN1 is AF1 (DS13293 alternate function table), the GPIOB clock in
        # the LPTIM1 set-up; PC0 (morpho only) is no longer touched.
        self.assertEqual(self.lib.t_pin_mode(PORT['B'], 5), self.k('af_pp'))
        self.assertEqual(self.lib.t_pin_alt(PORT['B'], 5), self.k('af1_lptim1'))
        self.assertEqual(self.lib.t_pin_pull(PORT['B'], 5), self.k('pullup'))
        self.assertEqual(self.lib.t_lptim_clk(), 2)                    # GPIOB only (A 1, B 2, C 4)
        self.assertEqual(self.lib.t_pin_inits(PORT['C'], 0), 0)

    def test_the_rf_debug_outputs_are_asserted_off(self):
        # sys_debug.c would drive PB4 (rain) with LDORDY and PB2 (vane) with SMPSRDY.
        text = SOURCE.read_text()
        for line in ('_Static_assert(DEBUG_RF_LDORDY_ENABLED == 0, "DEBUG_RF_LDORDY drives PB4, the rain gauge");',
                     '_Static_assert(DEBUG_RF_SMPSRDY_ENABLED == 0, "DEBUG_RF_SMPSRDY drives PB2, the wind vane");'):
            with self.subTest(line=line):
                self.assertIn(line, text)

    def test_ldordy_enabled_does_not_compile(self):
        # The board's sys_conf.h with one value changed, ahead of the real one on the include path:
        # 0 compiles (the control), 1 stops the build at the assert.
        real = (BOARD_INC/'sys_conf.h').read_text()
        line = '#define DEBUG_RF_LDORDY_ENABLED              0'
        self.assertEqual(real.count(line), 1)
        for value, ok in ((0, True), (1, False)):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as conf:
                (Path(conf)/'sys_conf.h').write_text(real.replace(line, line[:-1] + str(value)))
                r = subprocess.run([*CC_STRICT, '-fsyntax-only', *map(str, include_flags(self.stub.name, conf)), str(SOURCE)],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode == 0, ok, r.stderr[-800:])
                if not ok:
                    self.assertIn('DEBUG_RF_LDORDY drives PB4, the rain gauge', r.stderr)

    def test_pb14_is_untouched_without_the_mux(self):
        self.lib.t_mux_reset(1)
        self.lib.t_mux_reset(0)
        self.assertEqual((self.lib.t_pin_inits(PORT['B'], 14), self.lib.t_gpio_writes(PORT['B'])), (0, 0))

    def test_charger_pins_are_active_low(self):
        for idr, pins in ((PIN[8] | PIN[10], 0), (PIN[10], 1), (PIN[8], 2), (0, 3)):
            with self.subTest(idr=idr):
                self.lib.t_pins(idr)
                self.assertEqual(self.lib.board_charger_pins(), pins)

    def test_chg_edges_are_counted_on_exti10(self):
        # The 2 Hz fault flash (SLUS810 table 9-2) needs every edge, not one sample per latch: EXTI10
        # on both edges, served by EXTI15_10, which clears every line it owns.
        self.lib.board_charger_edges.restype = ctypes.c_uint32
        before, tips = self.lib.board_charger_edges(), self.lib.t_tips()
        for _ in range(5):
            self.lib.t_exti_raise(PIN[10])
            self.lib.t_exti15_10_irq()
        self.lib.t_exti_raise(PIN[11] | PIN[12] | PIN[13] | PIN[14] | PIN[15])
        self.lib.t_exti15_10_irq()
        self.assertEqual(self.lib.board_charger_edges(), before + 5)
        self.assertEqual(self.lib.t_exti_pending(), 0)
        self.assertEqual(self.lib.t_tips(), tips)                      # CHG never reaches the rain module

    def test_pin_modes(self):
        # PB1 and PA10 analog with no pull (a pull would bias the ISET node and the 6.67-kOhm
        # divider); PB8 and PB10 inputs with their pull-ups (the bq24074 pins are open drain); PB2 analog.
        cases = (('B', 1, 'analog', 'nopull'), ('A', 10, 'analog', 'nopull'), ('B', 2, 'analog', 'nopull'),
                 ('B', 8, 'input', 'pullup'), ('B', 10, 'it_both', 'pullup'), ('B', 4, 'it_falling', 'pullup'),
                 ('B', 5, 'af_pp', 'pullup'))
        for port, pin, mode, pull in cases:
            with self.subTest(pin=f'P{port}{pin}'):
                self.assertEqual(self.lib.t_pin_mode(PORT[port], pin), self.k(mode))
                self.assertEqual(self.lib.t_pin_pull(PORT[port], pin), self.k(pull))
        self.assertEqual(self.lib.t_pin_alt(PORT['B'], 5), self.k('af1_lptim1'))

    def test_the_sequence_has_four_channels(self):
        # IN4 (PB2 vane), IN5 (PB1 ISET), IN6 (PA10 divider), VREFINT (IN13), ranks 1 to 4, configured
        # once before the first start (never HAL_ADC_ConfigChannel while ADSTART is set).
        self.assertEqual(self.lib.t_seq_n(), 4)
        self.assertEqual([self.lib.t_seq_channel(i) for i in range(4)], [4, 5, 6, 13])
        self.assertEqual([self.lib.t_seq_rank(i) for i in range(4)], [self.k('rank_1') + i for i in range(4)])
        self.assertEqual(self.lib.t_config_after_start(), 0)
        init = [self.lib.t_adc_init(i) for i in range(8)]
        self.assertEqual(init, [self.k('scan_enable'), 4, self.k('eoc_single'), self.k('160_5'), 1,
                                self.k('ovs_16'), self.k('shift_4'), 0])

    def test_the_power_inputs_and_vdda(self):
        self.lib.t_vrefint_cal(1504)
        self.lib.t_adc_seq(2048, 812, 3001, 1712)                     # VDDA about 2.9 V
        rc, out = self.power()
        self.assertEqual(rc, 0)
        self.assertEqual((out.iset_raw, out.vin_raw, out.vref_raw), (812, 3001, 1712))   # unscaled counts
        self.assertEqual(out.vdda_mv, vdda_mv(1504, 1712))
        self.assertEqual(self.lib.t_adc_irq_disabled(), 0)             # the ADC interrupt is on again
        for cal, raw in ((1504, 1504), (1490, 1650), (1520, 1366), (1504, 1379)):   # 3.3, 2.98, 3.67, 3.6 V
            with self.subTest(cal=cal, raw=raw):
                self.lib.t_vrefint_cal(cal)
                self.lib.t_adc_seq(2048, 0, 0, raw)
                rc, out = self.power()
                self.assertEqual((rc, out.vdda_mv), (0, vdda_mv(cal, raw)))
        for raw in (0, 75):                                            # 0, or a VDDA beyond 16 bits: the ADC failed
            with self.subTest(raw=raw):
                self.lib.t_adc_seq(2048, 0, 0, raw)
                self.assertEqual(self.power()[0], -1)
        self.lib.t_vrefint_cal(1504)

    def test_no_sequence_yet(self):
        lib = fresh_copy(type(self), self.lib._name)
        lib.t_init()
        out = PowerAdc()
        self.assertEqual(lib.t_power(ctypes.byref(out)), -1)
        lib.t_adc_seq(2048, 100, 200, 1504)
        self.assertEqual(lib.t_power(ctypes.byref(out)), 0)
        self.assertEqual(out.seq, 1)

    def test_a_sequence_counts_only_when_whole(self):
        # A lost conversion interrupt (an overrun) drops that sequence; the next one is whole again.
        self.lib.t_adc_seq(2048, 100, 200, 1504)
        _, before = self.power()
        for v in (1, 2, 3):
            self.lib.t_adc_conv(v, v == 3)                            # three results, then EOS
        rc, out = self.power()
        self.assertEqual((rc, out.seq), (0, before.seq))
        self.lib.t_adc_seq(2048, 111, 222, 1504)
        rc, out = self.power()
        self.assertEqual((rc, out.seq, out.iset_raw, out.vin_raw), (0, before.seq + 1, 111, 222))

    def test_a_refused_start_does_not_stop_the_other_channels(self):
        self.lib.t_adc_seq(2048, 100, 200, 1504)
        self.lib.t_adc_fail_next()
        rc, first = self.power()                                       # takes the sequence; the next start is refused
        self.assertEqual(rc, 0)
        starts = self.lib.t_adc_starts()
        for _ in range(3):                                             # three 1-s samples with no new sequence
            rc, out = self.power()
            self.assertEqual((rc, out.seq), (0, first.seq))            # still the latest complete sequence
        self.assertEqual(self.lib.t_adc_starts(), starts + 1)          # then the sequence starts again
        self.lib.t_adc_seq(1000, 300, 400, 1504)
        rc, out = self.power()
        self.assertEqual((rc, out.seq, out.iset_raw, out.vin_raw, out.vref_raw), (0, first.seq + 1, 300, 400, 1504))
        mv = ctypes.c_uint16()
        self.assertEqual(self.lib.t_vane(ctypes.byref(mv)), 1)         # and the vane gets the same sequence
        self.assertEqual(mv.value, 1000 * 3300 // 4095)

    def test_the_adc_is_calibrated_before_its_first_conversion(self):
        # The closest vane positions are 30 mV apart (891 and 1000 ohm on a 10 kOhm pull-up): the
        # offset error of an uncalibrated ADC is too close to the 15 mV margin.
        self.assertEqual(self.lib.t_adc_calibrated_first(), 1)

    def test_the_cup_input_filters_contact_bounce(self):
        # 8 equal samples of the 32.768 kHz kernel clock (244 us) before an edge counts: far below the
        # 9 ms period of 112 Hz (75 m/s), far above reed bounce.
        LPTIM_CLOCKSAMPLETIME_8TRANSITIONS = 4                         # its value in HAL_STUB's enum
        self.assertEqual(self.lib.t_lptim_sample_time(), LPTIM_CLOCKSAMPLETIME_8TRANSITIONS)

    def test_a_refused_conversion_start_is_tried_again(self):
        # One refused HAL_ADC_Start_IT must not leave the vane without results until a reboot.
        mv = ctypes.c_uint16()
        self.lib.t_adc_done(1000)
        self.lib.t_adc_fail_next()
        self.assertEqual(self.lib.t_vane(ctypes.byref(mv)), 1)          # takes the result; the restart is refused
        starts = self.lib.t_adc_starts()
        for _ in range(3):                                              # three 1-s vane samples with no result
            self.assertEqual(self.lib.t_vane(ctypes.byref(mv)), 0)
        self.assertEqual(self.lib.t_adc_starts(), starts + 1)           # then the conversion starts again
        self.lib.t_adc_done(1000)
        self.assertEqual(self.lib.t_vane(ctypes.byref(mv)), 1)

    def test_vane_reading_and_restart(self):
        # The vane is ratiometric: the fixed 3300 "ratio mV", whatever VDDA is (mod_wind.c:21-30).
        mv = ctypes.c_uint16()
        self.lib.t_vrefint_cal(1504)
        self.lib.t_adc_seq(0, 0, 0, 1712)                             # a sequence the vane has not taken
        self.lib.t_vane(ctypes.byref(mv))
        starts = self.lib.t_adc_starts()
        self.lib.t_adc_seq(2048, 100, 200, 1712)                      # VDDA 2.9 V does not scale the vane
        self.assertEqual(self.lib.t_vane(ctypes.byref(mv)), 1)
        self.assertEqual(mv.value, 2048 * 3300 // 4095)
        self.assertEqual(self.lib.t_adc_starts(), starts + 1)          # the next sequence starts
        self.assertEqual(self.lib.t_vane(ctypes.byref(mv)), 0)          # nothing new yet


WIO_INC = ROOT/'firmware/board/wio-e5/Core/Inc'


@needs_cc
class WioE5Pins(unittest.TestCase):
    """The same board_inputs.c with the Wio-E5 mini's board layer (issue #35; its Core/Inc/board_pins.h
    ahead of the NUCLEO's): cups on PC0 (LPTIM1_IN1, AF1), the vane on PB3 (ADC1_IN2), no charger pins,
    and rain (PB4) and the mux RESET (PB14) as on the NUCLEO."""

    @classmethod
    def setUpClass(cls):
        cls.lib = build(cls, 'boardinputs_wio', board_inc=(WIO_INC,))
        cls.lib.t_init()                         # boot probe phase 1: the pull-downs are on

    def k(self, name):
        return ctypes.c_uint32.in_dll(self.lib, f'k_{name}').value

    def test_cups_on_pc0_with_lptim1_in1(self):
        self.assertEqual(self.lib.t_pin_mode(PORT['C'], 0), self.k('af_pp'))
        self.assertEqual(self.lib.t_pin_alt(PORT['C'], 0), self.k('af1_lptim1'))
        self.assertEqual(self.lib.t_lptim_clk(), 4)                    # GPIOC only (A 1, B 2, C 4)
        self.assertEqual(self.lib.t_pin_inits(PORT['B'], 5), 0)       # PB5 is the mini's LED

    def test_the_probe_pulls_pc0_and_pb4_and_restores_them(self):
        self.assertEqual((self.lib.t_pupdr_c(0), self.lib.t_pupdr(4)), (PUPD_DOWN, PUPD_DOWN))
        self.assertEqual(self.lib.t_fire(SETTLE_MS), 1)
        self.assertEqual((self.lib.t_pupdr_c(0), self.lib.t_pupdr(4)), (PUPD_UP, PUPD_UP))
        self.assertEqual(self.lib.t_pupdr(5), 0)                       # GPIOB pin 5 never touched

    def test_the_vane_is_pb3_adc1_in2_and_the_sequence_keeps_four_ranks(self):
        self.assertEqual(self.lib.t_pin_mode(PORT['B'], 3), self.k('analog'))
        self.assertEqual(self.lib.t_pin_pull(PORT['B'], 3), self.k('nopull'))
        self.assertEqual(self.lib.t_seq_n(), 4)
        self.assertEqual([self.lib.t_seq_channel(i) for i in range(4)], [2, 13, 6, 13])   # vane, (VREFINT), VIN, VREFINT
        self.assertEqual(self.lib.t_pin_mode(PORT['A'], 10), self.k('analog'))   # the charger input divider stays

    def test_no_charger_pins(self):
        for pin in (1, 2, 8, 10):                                      # ISET, the NUCLEO's vane, PGOOD, CHG
            with self.subTest(pin=f'PB{pin}'):
                self.assertEqual(self.lib.t_pin_inits(PORT['B'], pin), 0)
        for idr in (0, PIN[8] | PIN[10]):
            with self.subTest(idr=idr):
                self.lib.t_pins(idr)
                self.assertEqual(self.lib.board_charger_pins(), 0)

    def test_rain_stays_on_pb4_exti4(self):
        self.assertEqual(self.lib.t_pin_mode(PORT['B'], 4), self.k('it_falling'))
        self.assertEqual(self.lib.t_irq_enabled(self.k('exti4')), 1)


@needs_cc
class LinkProbe(unittest.TestCase):
    """The counter link probe (record M7): two phases on UTIL timers, the cups count kept clean of the
    probe's own edge, no rain tip from a probe, and the low runs behind the verdicts."""

    @classmethod
    def setUpClass(cls):
        cls.lib = build(cls, 'boardinputs_probe')

    def setUp(self):
        self.lib = fresh_copy(type(self), self.lib._name)
        self.lib.board_pulse_count.restype = ctypes.c_uint16
        self.lib.t_pins(PIN[4] | PIN[5] | PIN[8] | PIN[10])           # intact links read high; charger pins off
        self.lib.t_init()                                              # phase 1 of the boot probe

    def k(self, name):
        return ctypes.c_uint32.in_dll(self.lib, f'k_{name}').value

    def probe(self):
        """The rest of one probe: phase 2 now, then the next 15-minute phase 1 and its phase 2."""
        self.assertEqual(self.lib.t_fire(SETTLE_MS), 1)

    def next_probe(self):
        self.assertEqual(self.lib.t_fire(PROBE_MS), 1)
        self.probe()

    def test_phase_1_arms_a_timer_and_does_not_wait(self):
        # Boot ran phase 1 and returned with the pull-downs on: phase 2 waits for the one-shot.
        self.assertEqual((self.lib.t_timer_running(SETTLE_MS), self.lib.t_timer_mode(SETTLE_MS)), (1, 0))   # one-shot
        self.assertEqual((self.lib.t_timer_running(PROBE_MS), self.lib.t_timer_mode(PROBE_MS)), (1, 1))     # periodic
        self.assertEqual((self.lib.t_pupdr(5), self.lib.t_pupdr(4)), (PUPD_DOWN, PUPD_DOWN))
        self.probe()
        self.assertEqual((self.lib.t_pupdr(5), self.lib.t_pupdr(4)), (PUPD_UP, PUPD_UP))
        self.assertEqual(self.lib.t_timer_running(SETTLE_MS), 0)
        self.assertNotIn('HAL_Delay', SOURCE.read_text())

    def test_pb5_changes_only_its_pull_and_stays_in_af(self):
        inits = self.lib.t_pin_inits(PORT['B'], 5)
        for phase in (1, 2):
            with self.subTest(phase=phase):
                self.assertEqual(self.lib.t_moder(5), MODER_AF)          # still LPTIM1_IN1
                self.assertEqual(self.lib.t_pin_alt(PORT['B'], 5), self.k('af1_lptim1'))
                self.assertEqual(self.lib.t_pin_inits(PORT['B'], 5), inits)   # no HAL_GPIO_Init: PUPDR only
                self.assertEqual(self.lib.t_pupdr(5), PUPD_DOWN if phase == 1 else PUPD_UP)
                if phase == 1:
                    self.probe()

    def test_exti4_is_masked_through_the_probe_and_cleared_before_unmask(self):
        self.lib.t_link_open(PIN[4])                                   # an open rain link falls when pulled down
        self.assertEqual(self.lib.t_exti_masked(4), 1)
        tips = self.lib.t_tips()
        self.probe()
        self.assertEqual(self.lib.t_exti_masked(4), 0)
        self.assertLess(self.lib.t_cleared_at(), self.lib.t_unmasked_at())   # pending cleared, then unmasked
        self.assertEqual(self.lib.t_exti_pending() & PIN[4], 0)
        self.assertEqual(self.lib.t_pupdr(4), PUPD_UP)                 # the pull-up is back
        self.lib.t_exti4_irq()
        self.assertEqual(self.lib.t_tips(), tips)                      # a probe never makes a rain tip
        self.assertEqual(self.lib.board_link_lows(RAIN), 1)

    def test_an_open_cups_link_adds_no_count_and_is_suspect_after_three_probes(self):
        # LPTIM1's filter (244 us) passes the 1 ms pull-down edge of an open PB5: c1 - c0 comes out.
        self.lib.mod_wind_init(0, 0)
        self.lib.t_link_open(PIN[5])
        before = self.lib.board_pulse_count()
        self.probe()
        verdicts = [self.lib.mod_wind_link()]
        for _ in range(2):
            self.next_probe()
            verdicts.append(self.lib.mod_wind_link())
        self.assertEqual(self.lib.board_pulse_count(), before)        # three probe edges, no net count
        self.assertEqual(self.lib.board_link_lows(CUPS), 3)
        self.assertEqual(self.lib.board_link_edge_seen(CUPS), 0)      # the probe's edges are not edges
        self.assertEqual(verdicts, [METER_OK, METER_OK, CUPS_SUSPECT])

    def test_the_count_holds_through_the_window_and_real_pulses_go_on(self):
        self.lib.t_link_open(PIN[5])
        self.probe()
        start = self.lib.board_pulse_count()
        self.lib.t_cup_pulses(4)                                       # four real pulses
        self.assertEqual(self.lib.board_pulse_count(), (start + 4) & 0xFFFF)
        self.assertEqual(self.lib.board_link_edge_seen(CUPS), 1)
        self.assertEqual(self.lib.t_fire(PROBE_MS), 1)                 # phase 1: the open link falls now
        held = self.lib.board_pulse_count()
        self.lib.t_link_open(PIN[5])                                   # (the model counts the fall)
        self.assertEqual(self.lib.board_pulse_count(), held)          # held still through the window
        self.probe()
        self.assertEqual(self.lib.board_pulse_count(), held)
        self.assertEqual(self.lib.board_link_lows(CUPS), 1)            # low, but a real edge since: a new run

    def test_an_intact_link_reads_high(self):
        for _ in range(3):
            self.probe() if self.lib.t_timer_running(SETTLE_MS) else self.next_probe()
        self.assertEqual((self.lib.board_link_lows(CUPS), self.lib.board_link_lows(RAIN)), (0, 0))

    def test_a_rain_tip_resets_the_run(self):
        self.lib.t_link_open(PIN[4])
        self.probe()
        self.next_probe()
        self.assertEqual(self.lib.board_link_lows(RAIN), 2)
        self.lib.t_link_open(0)                                        # repaired: a real tip arrives
        self.lib.t_exti_raise(PIN[4])
        self.lib.t_exti4_irq()
        self.assertEqual(self.lib.board_link_edge_seen(RAIN), 1)
        self.lib.t_link_open(PIN[4])
        self.next_probe()
        self.assertEqual((self.lib.board_link_lows(RAIN), self.lib.board_link_edge_seen(RAIN)), (1, 0))

    def test_a_refused_one_shot_restores_the_pull_ups(self):
        self.probe()
        self.lib.t_refuse_starts(1)
        self.assertEqual(self.lib.t_fire(PROBE_MS), 1)
        self.assertEqual((self.lib.t_pupdr(5), self.lib.t_pupdr(4), self.lib.t_exti_masked(4)), (PUPD_UP, PUPD_UP, 0))


@needs_cc
class BenchButtons(unittest.TestCase):
    """WS_BENCH_OLED=1: the bench buttons B1 PA0, B2 PA1, B3 PC6, active low (App/oled_app.c reads them up)."""

    @classmethod
    def setUpClass(cls):
        cls.lib = build(cls, 'boardinputs_bench', bench=True)
        cls.lib.t_init()

    def test_board_button_up_reads_each_pin(self):
        self.lib.t_idr(PORT['A'], PIN[0] | PIN[1])
        self.lib.t_idr(PORT['C'], PIN[6])
        self.assertEqual([self.lib.board_button_up(b) for b in range(5)], [0, 1, 1, 1, 0])   # 0 and 4 are no button
        for b, (port, pin) in ((1, ('A', 0)), (2, ('A', 1)), (3, ('C', 6))):
            with self.subTest(b=b):
                self.lib.t_idr(PORT['A'], PIN[0] | PIN[1])
                self.lib.t_idr(PORT['C'], PIN[6])
                self.lib.t_idr(PORT[port], (PIN[0] | PIN[1] if port == 'A' else PIN[6]) & ~PIN[pin])
                self.assertEqual([self.lib.board_button_up(i) for i in (1, 2, 3)], [int(i != b) for i in (1, 2, 3)])

    def test_pa0_pa1_falling_edge_with_pull_ups(self):
        for pin in (0, 1):
            with self.subTest(pin=pin):
                self.assertEqual(self.lib.t_pin_mode(PORT['A'], pin), ctypes.c_uint32.in_dll(self.lib, 'k_it_falling').value)
                self.assertEqual(self.lib.t_pin_pull(PORT['A'], pin), ctypes.c_uint32.in_dll(self.lib, 'k_pullup').value)


@needs_cc
class MuxReset(unittest.TestCase):
    """WS_I2C_MUX=1: the mux RESET (i2c_bus_mux_reset_line) on PB14 = A4, CN8.5 (record N5), active low."""

    @classmethod
    def setUpClass(cls):
        cls.lib = build(cls, 'boardinputs_mux', '-DWS_I2C_MUX=1')
        cls.lib.t_init()

    def k(self, name):
        return ctypes.c_uint32.in_dll(self.lib, f'k_{name}').value

    def test_pb14_is_a_push_pull_output_released_at_init(self):
        self.assertEqual(self.lib.t_pin_inits(PORT['B'], 14), 1)
        self.assertEqual(self.lib.t_pin_mode(PORT['B'], 14), self.k('output_pp'))
        self.assertEqual(self.lib.t_pin_pull(PORT['B'], 14), self.k('nopull'))
        self.assertEqual(self.lib.t_pin_odr_at_init(PORT['B'], 14), 1)   # high before it drives: no boot pulse
        self.assertEqual(self.lib.t_pin_level(PORT['B'], 14), 1)

    def test_pb14_is_low_while_asserted(self):
        self.lib.t_mux_reset(1)
        self.assertEqual(self.lib.t_pin_level(PORT['B'], 14), 0)
        self.lib.t_mux_reset(0)
        self.assertEqual(self.lib.t_pin_level(PORT['B'], 14), 1)


if __name__ == '__main__':
    unittest.main()
