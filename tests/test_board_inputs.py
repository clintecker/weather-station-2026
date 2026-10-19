"""The bench station's board inputs (firmware/stage0-node/App/board_inputs.c) on the host.

board_inputs.c is compiled unchanged against a small stand-in for ST's HAL (written below), which
models the EXTI pending flags, the GPIO input levels and the ADC result. The shared EXTI9_5 vector
serves the rain gauge on line 5, and the board also unmasks line 6 (button B3, PC6): the handler must
clear every line it owns, or one press re-enters the interrupt forever."""
import ctypes
import unittest

try:
    from toolchain import ROOT, host_library, needs_cc          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import ROOT, host_library, needs_cc    # python -m unittest tests.<module>

HAL_STUB = r'''
#ifndef STUB_HAL_H
#define STUB_HAL_H
#include <stdint.h>
typedef enum { HAL_OK, HAL_ERROR, HAL_BUSY } HAL_StatusTypeDef;
typedef enum { GPIO_PIN_RESET, GPIO_PIN_SET } GPIO_PinState;
typedef struct { uint32_t idr; } GPIO_TypeDef;
extern GPIO_TypeDef stub_gpiob, stub_gpioc;
#define GPIOB (&stub_gpiob)
#define GPIOC (&stub_gpioc)
#define GPIO_PIN_0 (1U << 0)
#define GPIO_PIN_2 (1U << 2)
#define GPIO_PIN_5 (1U << 5)
#define GPIO_PIN_6 (1U << 6)
#define GPIO_PIN_7 (1U << 7)
#define GPIO_PIN_8 (1U << 8)
#define GPIO_PIN_9 (1U << 9)
#define GPIO_PIN_10 (1U << 10)
enum { GPIO_MODE_INPUT, GPIO_MODE_ANALOG, GPIO_MODE_AF_PP, GPIO_MODE_IT_FALLING };
enum { GPIO_NOPULL, GPIO_PULLUP };
enum { GPIO_SPEED_FREQ_LOW };
enum { GPIO_AF1_LPTIM1 = 1 };
typedef struct { uint32_t Pin, Mode, Pull, Speed, Alternate; } GPIO_InitTypeDef;
void HAL_GPIO_Init(GPIO_TypeDef *port, GPIO_InitTypeDef *init);
GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef *port, uint16_t pin);
void HAL_GPIO_EXTI_IRQHandler(uint16_t pin);
void HAL_GPIO_EXTI_Callback(uint16_t pin);
typedef enum { ADC_IRQn = 18, EXTI9_5_IRQn = 22 } IRQn_Type;
void HAL_NVIC_SetPriority(IRQn_Type irq, uint32_t pre, uint32_t sub);
void HAL_NVIC_EnableIRQ(IRQn_Type irq);
enum { RCC_PERIPHCLK_LPTIM1 = 1, RCC_LPTIM1CLKSOURCE_LSE = 2 };
typedef struct { uint32_t PeriphClockSelection, Lptim1ClockSelection; } RCC_PeriphCLKInitTypeDef;
HAL_StatusTypeDef HAL_RCCEx_PeriphCLKConfig(RCC_PeriphCLKInitTypeDef *clk);
#define __HAL_RCC_LPTIM1_CLK_ENABLE() ((void)0)
#define __HAL_RCC_GPIOB_CLK_ENABLE() ((void)0)
#define __HAL_RCC_GPIOC_CLK_ENABLE() ((void)0)
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
enum { ADC_CLOCK_SYNC_PCLK_DIV4, ADC_RESOLUTION_12B, ADC_DATAALIGN_RIGHT, ADC_SCAN_DISABLE, ADC_EOC_SINGLE_CONV, ADC_SOFTWARE_START,
       ADC_OVR_DATA_OVERWRITTEN, ADC_SAMPLETIME_160CYCLES_5, ADC_TRIGGER_FREQ_LOW, ADC_CHANNEL_4, ADC_REGULAR_RANK_1,
       ADC_SAMPLINGTIME_COMMON_1 };
typedef struct { uint32_t ClockPrescaler, Resolution, DataAlign, ScanConvMode, EOCSelection, LowPowerAutoWait, LowPowerAutoPowerOff,
                 ContinuousConvMode, NbrOfConversion, DiscontinuousConvMode, ExternalTrigConv, DMAContinuousRequests, Overrun,
                 SamplingTimeCommon1, OversamplingMode, TriggerFrequencyMode; } ADC_InitTypeDef;
typedef struct { ADC_TypeDef *Instance; ADC_InitTypeDef Init; } ADC_HandleTypeDef;
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

SHIM = r'''
#include <stdint.h>
#include "stm32wlxx_hal.h"
#include "board_inputs.h"
#include "mod_power.h"
#include "mod_wind.h"
GPIO_TypeDef stub_gpiob, stub_gpioc;
LPTIM_TypeDef stub_lptim1;
ADC_TypeDef stub_adc;
static uint32_t exti_pending;
static int tips, adc_starts, adc_fail_next, adc_calibrated_first = -1;
static uint32_t lptim_sample_time;
static uint32_t adc_value;
static ADC_HandleTypeDef *adc;
void HAL_GPIO_Init(GPIO_TypeDef *port, GPIO_InitTypeDef *init) { (void)port; (void)init; }
GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef *port, uint16_t pin) { return (port->idr & pin) ? GPIO_PIN_SET : GPIO_PIN_RESET; }
/* As ST's: serves one line if it is pending: clear its flag, then the callback. */
void HAL_GPIO_EXTI_IRQHandler(uint16_t pin)
{
  if (exti_pending & pin) { exti_pending &= ~(uint32_t)pin; HAL_GPIO_EXTI_Callback(pin); }
}
void HAL_NVIC_SetPriority(IRQn_Type irq, uint32_t pre, uint32_t sub) { (void)irq; (void)pre; (void)sub; }
void HAL_NVIC_EnableIRQ(IRQn_Type irq) { (void)irq; }
HAL_StatusTypeDef HAL_RCCEx_PeriphCLKConfig(RCC_PeriphCLKInitTypeDef *clk) { (void)clk; return HAL_OK; }
HAL_StatusTypeDef HAL_LPTIM_Init(LPTIM_HandleTypeDef *h) { lptim_sample_time = h->Init.UltraLowPowerClock.SampleTime; HAL_LPTIM_MspInit(h); return HAL_OK; }
HAL_StatusTypeDef HAL_LPTIM_Counter_Start(LPTIM_HandleTypeDef *h, uint32_t period) { (void)h; (void)period; return HAL_OK; }
uint32_t HAL_LPTIM_ReadCounter(const LPTIM_HandleTypeDef *h) { (void)h; return 1234; }
HAL_StatusTypeDef HAL_ADC_Init(ADC_HandleTypeDef *h) { adc = h; HAL_ADC_MspInit(h); return HAL_OK; }
HAL_StatusTypeDef HAL_ADC_ConfigChannel(ADC_HandleTypeDef *h, ADC_ChannelConfTypeDef *c) { (void)h; (void)c; return HAL_OK; }
HAL_StatusTypeDef HAL_ADC_Start_IT(ADC_HandleTypeDef *h)
{
  (void)h; if (adc_calibrated_first < 0) adc_calibrated_first = 0;
  adc_starts++;
  if (adc_fail_next) { adc_fail_next = 0; return HAL_ERROR; }
  return HAL_OK;
}
HAL_StatusTypeDef HAL_ADCEx_Calibration_Start(ADC_HandleTypeDef *h) { (void)h; if (adc_calibrated_first < 0) adc_calibrated_first = 1; return HAL_OK; }
uint32_t HAL_ADC_GetValue(const ADC_HandleTypeDef *h) { (void)h; return adc_value; }
void HAL_ADC_IRQHandler(ADC_HandleTypeDef *h) { HAL_ADC_ConvCpltCallback(h); }
uint32_t clock_ms(void) { return 0; }
void mod_rain_tip(uint32_t now_ms) { (void)now_ms; tips++; }
void ADC_IRQHandler(void);
void EXTI9_5_IRQHandler(void);
void t_init(void) { board_inputs_init(); }
void t_exti_raise(uint32_t lines) { exti_pending |= lines; }
uint32_t t_exti_pending(void) { return exti_pending; }
void t_exti_irq(void) { EXTI9_5_IRQHandler(); }
int t_tips(void) { return tips; }
void t_pins(uint32_t idr) { stub_gpiob.idr = idr; }
void t_adc_done(uint32_t value) { adc_value = value; ADC_IRQHandler(); }
int t_adc_starts(void) { return adc_starts; }
void t_adc_fail_next(void) { adc_fail_next = 1; }
int t_adc_calibrated_first(void) { return adc_calibrated_first; }
uint32_t t_lptim_sample_time(void) { return lptim_sample_time; }
int t_vane(uint16_t *mv) { return board_vane_mv(mv); }
'''

PIN = {n: 1 << n for n in range(11)}


@needs_cc
class BoardInputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = ROOT/'firmware/stage0-node/App'
        import tempfile
        from pathlib import Path
        cls.stub = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.stub.cleanup)
        (Path(cls.stub.name)/'stm32wlxx_hal.h').write_text(HAL_STUB)
        cls.lib = host_library(cls, 'boardinputs', '-I', cls.stub.name, '-I', app, '-I', ROOT/'firmware/common',
                               '-I', ROOT/'firmware', app/'board_inputs.c', files={'shim.c': SHIM})
        cls.lib.t_init()

    def test_every_line_of_the_shared_vector_is_cleared(self):
        # Button B3 (PC6) is configured with a falling-edge interrupt by the board's own GPIO setup.
        # Its line shares EXTI9_5 with the rain gauge: one press must not leave it pending.
        self.lib.t_exti_raise(PIN[6] | PIN[7] | PIN[8] | PIN[9])
        self.lib.t_exti_irq()
        self.assertEqual(self.lib.t_exti_pending(), 0)

    def test_a_rain_tip_reaches_the_rain_module_and_only_it(self):
        before = self.lib.t_tips()
        self.lib.t_exti_raise(PIN[5])
        self.lib.t_exti_irq()
        self.lib.t_exti_raise(PIN[6])
        self.lib.t_exti_irq()
        self.assertEqual(self.lib.t_tips(), before + 1)

    def test_charger_pins_are_active_low(self):
        for idr, pins in ((PIN[8] | PIN[10], 0), (PIN[10], 1), (PIN[8], 2), (0, 3)):
            with self.subTest(idr=idr):
                self.lib.t_pins(idr)
                self.assertEqual(self.lib.board_charger_pins(), pins)

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
        mv = ctypes.c_uint16()
        starts = self.lib.t_adc_starts()
        self.lib.t_adc_done(2048)
        self.assertEqual(self.lib.t_vane(ctypes.byref(mv)), 1)
        self.assertEqual(mv.value, 2048 * 3300 // 4095)
        self.assertEqual(self.lib.t_adc_starts(), starts + 1)          # the next conversion starts
        self.assertEqual(self.lib.t_vane(ctypes.byref(mv)), 0)          # nothing new yet


if __name__ == '__main__':
    unittest.main()
