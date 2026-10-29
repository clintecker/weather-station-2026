/* Bench telemetry link (README.md): ROLE=tx reads the bench's power and air parts and sends one packet
 * every 5 s; ROLE=rx prints every packet it hears. Plain LoRa, test only: not the station protocol.
 *   TX, every 250 ms: the INA228 shunt and VBUS, and the ADC on the bq24074 ISET pin (PB1 = A0) and on the
 *   charger's input through its divider (PA10 = A2).
 *   TX, every 5 s: the INA228 die temperature, the MAX17048, the SHT45, the PGOOD/CHG pins, then the
 *   packet (bl_pkt.h). Blocking HAL transfers with short timeouts from one sequencer task, as in
 *   firmware/i2cscan: a bench tool, not the node.
 *   RX: continuous reception; each packet is printed as "#bl rssi=.. snr=.. len=.. hex=..", and every
 *   10 s a heartbeat "#bl hb ..." with the counts and the seconds since the last packet.
 * Both roles run under the supervised watchdog (App/bl_guard.h): the TX must get a packet out at least
 * every 20 s, the RX must handle each heard packet within 5 s (a silent receiver is re-armed, not reset).
 * Every boot prints "#bl boot ...".
 * Times: HAL_GetTick() on this board counts 1/1024 s RTC ticks, not milliseconds (board timer_if.c; the
 * node's App/clock.h). The tick counter keeps running through a reset and restarts at power-on; it wraps
 * after 48.5 days. TICKS() converts.
 * Drills (README.md): hold a NUCLEO button for about 2 s (two 1 s checks in a row). The red LED lights
 * while the hold is seen; red and green together mean the drill fired: let go. A button held through a boot is ignored until it is
 * released, so a drill cannot repeat itself. B1: hang the main loop (expect a watchdog reset).
 * B2: crash (expect a software reset and a "#fault" record). B3, TX only: lose the next "transmission
 * done" (expect "#bl radio stuck" and a watchdog reset). */
#include <string.h>
#include "bench_regs.h"
#include "bl_guard.h"
#include "bl_pkt.h"
#include "fault.h"
#include "main.h"   /* the LED and button pins, RTC_N_PREDIV_S */
#include "radio.h"
#include "stm32_seq.h"
#include "stm32_timer.h"
#include "stm32wlxx_hal.h"
#include "subghz_phy_app.h"
#include "sys_app.h"
#include "utilities_def.h"

/* The project's bench radio settings (stage0-node/App/radio_cfg.h): 915 MHz, 500 kHz (FCC 15.247
   digital modulation), SF7, CR 4/5. 10 dBm: margin across the room for a day's run. */
#define RF_FREQUENCY_HZ 915000000U
#define LORA_BW 2U
#define LORA_SF 7U
#define LORA_CR 1U
#define LORA_PREAMBLE 8U

#define FLASH_MS 80U                /* LED flash: green (LD2) a good packet, red (LD3) a bad one or an error */
#define DRILL_HOLD_CHECKS 2U        /* 1 s checks in a row with the button down */
#define TICKS_PER_S (1U << RTC_N_PREDIV_S)   /* HAL_GetTick() units */

static RadioEvents_t events;
static uint8_t buf[BL_PKT_LEN];
#define DRILL_FIRED_MS 300U        /* both LEDs on before a drill that resets at once */
static UTIL_TIMER_Object_t flash_timer;
static unsigned held[3];
static int armed[3];   /* seen released since boot */
static volatile int drill_leds;   /* a drill owns the LEDs: the packet flash leaves them alone */

static void on_flash_end(void *ctx)
{
  (void)ctx;
  if (drill_leds) return;
  HAL_GPIO_WritePin(LED2_GPIO_Port, LED2_Pin, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(LED3_GPIO_Port, LED3_Pin, GPIO_PIN_RESET);
}

static void flash(int good)
{
  if (drill_leds) return;
  if (good) HAL_GPIO_WritePin(LED2_GPIO_Port, LED2_Pin, GPIO_PIN_SET);
  else HAL_GPIO_WritePin(LED3_GPIO_Port, LED3_Pin, GPIO_PIN_SET);
  (void)UTIL_TIMER_Start(&flash_timer);
}

static void leds_buttons_init(void)
{
  (void)UTIL_TIMER_Create(&flash_timer, FLASH_MS, UTIL_TIMER_ONESHOT, on_flash_end, NULL);
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();
  GPIO_InitTypeDef b = { .Pin = BUT1_Pin | BUT2_Pin, .Mode = GPIO_MODE_INPUT, .Pull = GPIO_PULLUP,
                         .Speed = GPIO_SPEED_FREQ_LOW };
  HAL_GPIO_Init(GPIOA, &b);
  b.Pin = BUT3_Pin;
  HAL_GPIO_Init(GPIOC, &b);
}

static void leds(GPIO_PinState green, GPIO_PinState red)
{
  HAL_GPIO_WritePin(LED2_GPIO_Port, LED2_Pin, green);
  HAL_GPIO_WritePin(LED3_GPIO_Port, LED3_Pin, red);
}

/* 1 once button k (0..2) has been held down for DRILL_HOLD_CHECKS checks in a row (the buttons pull low),
   counting only after it was seen released since boot. Red while a hold is seen, red and green when it
   fires. */
static int drill(unsigned k)
{
  static GPIO_TypeDef *const port[] = { BUT1_GPIO_Port, BUT2_GPIO_Port, BUT3_GPIO_Port };
  static const uint16_t pin[] = { BUT1_Pin, BUT2_Pin, BUT3_Pin };
  int down = HAL_GPIO_ReadPin(port[k], pin[k]) == GPIO_PIN_RESET;
  if (!down)
  {
    if (held[k]) { leds(GPIO_PIN_RESET, GPIO_PIN_RESET); drill_leds = 0; }
    armed[k] = 1;
    held[k] = 0;
    return 0;
  }
  if (!armed[k]) return 0;
  held[k]++;
  drill_leds = 1;
  if (held[k] < DRILL_HOLD_CHECKS) { leds(GPIO_PIN_RESET, GPIO_PIN_SET); return 0; }
  if (held[k] > DRILL_HOLD_CHECKS) return 0;   /* fired already: wait for the release */
  leds(GPIO_PIN_SET, GPIO_PIN_SET);
  return 1;
}

/* The drills both roles share; called from the 1 s check. */
static void common_drills(void)
{
  if (drill(0))
  {
    APP_PRINTF("#bl drill hang: the main loop stops; expect reset=watchdog\n");
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wanalyzer-infinite-loop"
    for (;;) { }   /* bound: none on purpose: the drill */
#pragma GCC diagnostic pop
  }
  if (drill(1))
  {
    HAL_Delay(DRILL_FIRED_MS);   /* let the LEDs show before the reset */
    fault_test();
  }
}

#ifdef BL_ROLE_tx
#define TX_POWER_DBM 10
#define TX_TIMEOUT_MS 3000U

#define SDA_PIN GPIO_PIN_11
#define SCL_PIN GPIO_PIN_12
#define I2C_TIMING 0x20303E5DU
#define XFER_TIMEOUT_MS 10U
#define INA228_ADDR 0x40U
#define MAX17048_ADDR 0x36U
#define SHT45_ADDR 0x44U
#define SHT45_MEASURE 0xFDU         /* high repeatability, no heater */
#define SHT45_WAIT_MS 10U           /* 8.3 ms maximum (datasheet table 4) */
#define SHT45_LEN 6U
#define PGOOD_PIN GPIO_PIN_8        /* PB8, CN10.27: low = valid input */
#define CHG_PIN GPIO_PIN_10         /* PB10, CN10.25: low = charging */
#define ISET_PIN GPIO_PIN_1         /* PB1 = A0, CN8.1: ADC1_IN5 */
#define VIN_PIN GPIO_PIN_10         /* PA10 = A2, CN8.3: ADC1_IN6, VBUS through 20k/10k */
#define VIN_DIVIDER 3
#define ADC_AVG 16U                 /* conversions averaged per ADC reading (ISET, the input, VREFINT) */
#define ADC_POLL_MS 2U
#define TICK_MS 250U
#define TICKS_PER_PACKET 20U        /* 5 s */
#define UV_PER_MV 1000
#define TICKS(ms) ((uint32_t)(((uint64_t)(ms) * TICKS_PER_S) / MS_PER_S))
#define TX_STUCK_MS 5000U           /* a send with neither done nor timeout after this: the radio is stuck */
#define TX_HEALTH_MS 20000U         /* no packet out for this long: stop feeding the watchdog */
#define MS_PER_S 1000U
#define UNSTICK_CLOCKS 9U           /* I2C bus clear (UM10204 3.1.16): up to nine SCL pulses, then a STOP */

enum { INA_VSHUNT = 0x04, INA_VBUS = 0x05, INA_DIETEMP = 0x06, INA_MANUFACTURER = 0x3E, INA_DEVICE = 0x3F };
enum { GAUGE_VCELL = 0x02, GAUGE_SOC = 0x04, GAUGE_VERSION = 0x08, GAUGE_CRATE = 0x16 };

static I2C_HandleTypeDef hi2c2;
static ADC_HandleTypeDef hadc;
static UTIL_TIMER_Object_t tick_timer;
static unsigned ticks;
static int64_t shunt_sum, vbus_sum, iset_sum, vin_sum;
static int32_t iset_min, iset_max;
static unsigned samples, misses, adc_samples;
static uint32_t seq;
static int adc_ok;
static volatile int tx_busy, drop_done;
static volatile uint32_t tx_started_ms, last_done_ms;
static uint16_t tx_timeouts, i2c_restarts, i2c_unsticks;
static int stuck_reported, unhealthy_reported;

/* cppcheck-suppress constParameterPointer ; ST's HAL callback signature */
void HAL_I2C_MspInit(I2C_HandleTypeDef *h)
{
  if (h->Instance != I2C2) return;
  RCC_PeriphCLKInitTypeDef clk = { .PeriphClockSelection = RCC_PERIPHCLK_I2C2,
                                   .I2c2ClockSelection = RCC_I2C2CLKSOURCE_PCLK1 };
  (void)HAL_RCCEx_PeriphCLKConfig(&clk);
  __HAL_RCC_GPIOA_CLK_ENABLE();
  GPIO_InitTypeDef gpio = { .Pin = SDA_PIN | SCL_PIN, .Mode = GPIO_MODE_AF_OD, .Pull = GPIO_NOPULL,
                            .Speed = GPIO_SPEED_FREQ_LOW, .Alternate = GPIO_AF4_I2C2 };
  HAL_GPIO_Init(GPIOA, &gpio);
  __HAL_RCC_I2C2_CLK_ENABLE();
}

/* cppcheck-suppress constParameterPointer ; ST's HAL callback signature */
void HAL_I2C_MspDeInit(I2C_HandleTypeDef *h)
{
  if (h->Instance != I2C2) return;
  __HAL_RCC_I2C2_CLK_DISABLE();
  HAL_GPIO_DeInit(GPIOA, SDA_PIN | SCL_PIN);
}

/* cppcheck-suppress constParameterPointer ; ST's HAL callback signature */
void HAL_ADC_MspInit(ADC_HandleTypeDef *h)
{
  if (h->Instance != ADC) return;
  __HAL_RCC_ADC_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  GPIO_InitTypeDef gpio = { .Pin = ISET_PIN, .Mode = GPIO_MODE_ANALOG, .Pull = GPIO_NOPULL };
  HAL_GPIO_Init(GPIOB, &gpio);
  __HAL_RCC_GPIOA_CLK_ENABLE();
  gpio.Pin = VIN_PIN;
  HAL_GPIO_Init(GPIOA, &gpio);
}

static void bus_start(void)
{
  hi2c2.Instance = I2C2;
  hi2c2.Init.Timing = I2C_TIMING;
  hi2c2.Init.OwnAddress1 = 0;
  hi2c2.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
  hi2c2.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
  hi2c2.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
  hi2c2.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;
  if (HAL_I2C_Init(&hi2c2) != HAL_OK || HAL_I2CEx_ConfigAnalogFilter(&hi2c2, I2C_ANALOGFILTER_ENABLE) != HAL_OK)
    APP_PRINTF("#error i2c init\n");
}

static void line(uint16_t pin, GPIO_PinState level)
{
  HAL_GPIO_WritePin(GPIOA, pin, level);
  HAL_Delay(1);
}

/* With the peripheral released: if a target holds SDA low (it lost a clock mid-byte), clock SCL until
   it lets go, then send a STOP. 1 when SDA was held. Both pins open drain; the modules pull them up. */
static int bus_unstick(void)
{
  GPIO_InitTypeDef gpio = { .Pin = SDA_PIN | SCL_PIN, .Mode = GPIO_MODE_OUTPUT_OD, .Pull = GPIO_NOPULL,
                            .Speed = GPIO_SPEED_FREQ_LOW };
  HAL_GPIO_WritePin(GPIOA, SDA_PIN | SCL_PIN, GPIO_PIN_SET);
  HAL_GPIO_Init(GPIOA, &gpio);
  HAL_Delay(1);
  if (HAL_GPIO_ReadPin(GPIOA, SDA_PIN) == GPIO_PIN_SET) return 0;
  for (unsigned i = 0; i < UNSTICK_CLOCKS && HAL_GPIO_ReadPin(GPIOA, SDA_PIN) == GPIO_PIN_RESET; i++)
  {
    line(SCL_PIN, GPIO_PIN_RESET);
    line(SCL_PIN, GPIO_PIN_SET);
  }
  line(SCL_PIN, GPIO_PIN_RESET);   /* STOP: SDA rises while SCL is high */
  line(SDA_PIN, GPIO_PIN_RESET);
  line(SCL_PIN, GPIO_PIN_SET);
  line(SDA_PIN, GPIO_PIN_SET);
  int freed = HAL_GPIO_ReadPin(GPIOA, SDA_PIN) == GPIO_PIN_SET;
  APP_PRINTF("#bl i2c sda held low: %s\n", freed ? "freed" : "still low");
  return 1;
}

static void bus_restart(void)
{
  (void)HAL_I2C_DeInit(&hi2c2);   /* returns the pins to analog (HAL_I2C_MspDeInit) */
  if (i2c_restarts < UINT16_MAX) i2c_restarts++;
  if (bus_unstick() && i2c_unsticks < UINT16_MAX) i2c_unsticks++;
  bus_start();
}

static void adc_start(void)
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
  hadc.Init.SamplingTimeCommon1 = ADC_SAMPLETIME_160CYCLES_5;   /* also long enough for VREFINT */
  hadc.Init.OversamplingMode = DISABLE;
  hadc.Init.TriggerFrequencyMode = ADC_TRIGGER_FREQ_LOW;
  adc_ok = HAL_ADC_Init(&hadc) == HAL_OK && HAL_ADCEx_Calibration_Start(&hadc) == HAL_OK;
  if (!adc_ok) APP_PRINTF("#error adc init\n");
}

/* The mean of ADC_AVG conversions of one channel, raw counts; -1 on a failure. */
static int32_t adc_read(uint32_t channel)
{
  ADC_ChannelConfTypeDef ch = { .Channel = channel, .Rank = ADC_REGULAR_RANK_1,
                                .SamplingTime = ADC_SAMPLINGTIME_COMMON_1 };
  if (HAL_ADC_ConfigChannel(&hadc, &ch) != HAL_OK) return -1;
  uint32_t sum = 0;
  for (unsigned i = 0; i < ADC_AVG; i++)
  {
    if (HAL_ADC_Start(&hadc) != HAL_OK || HAL_ADC_PollForConversion(&hadc, ADC_POLL_MS) != HAL_OK) return -1;
    sum += HAL_ADC_GetValue(&hadc);
  }
  return (int32_t)(sum / ADC_AVG);
}

/* A channel in uV at the pin, scaled by VDDA from the factory VREFINT calibration; -1 on a failure. */
static int32_t pin_uv(uint32_t channel)
{
  int32_t vref = adc_read(ADC_CHANNEL_VREFINT);
  int32_t raw = adc_read(channel);
  if (vref <= 0 || raw < 0) return -1;
  uint32_t vdda_mv = __HAL_ADC_CALC_VREFANALOG_VOLTAGE((uint32_t)vref, ADC_RESOLUTION_12B);
  return (int32_t)(__HAL_ADC_CALC_DATA_TO_VOLTAGE(vdda_mv, (uint32_t)raw, ADC_RESOLUTION_12B)) * UV_PER_MV;
}

static int read_reg(uint8_t addr7, uint8_t reg, uint8_t *b, uint16_t len)
{
  return HAL_I2C_Mem_Read(&hi2c2, (uint16_t)(addr7 << 1), reg, I2C_MEMADD_SIZE_8BIT, b, len, XFER_TIMEOUT_MS) == HAL_OK ? 0 : -1;
}

static int read16(uint8_t addr7, uint8_t reg, uint16_t *v)
{
  uint8_t b[2];
  if (read_reg(addr7, reg, b, sizeof b)) return -1;
  *v = (uint16_t)((b[0] << 8) | b[1]);
  return 0;
}

static int read24(uint8_t addr7, uint8_t reg, uint32_t *v)
{
  uint8_t b[3];
  if (read_reg(addr7, reg, b, sizeof b)) return -1;
  *v = ((uint32_t)b[0] << 16) | ((uint32_t)b[1] << 8) | b[2];
  return 0;
}

static void sample(void)
{
  uint32_t shunt, vbus;
  if (read24(INA228_ADDR, INA_VSHUNT, &shunt) || read24(INA228_ADDR, INA_VBUS, &vbus)) { misses++; bus_restart(); }
  else { shunt_sum += ina228_count(shunt); vbus_sum += ina228_count(vbus); samples++; }
  if (!adc_ok) return;
  int32_t uv = pin_uv(ADC_CHANNEL_5);
  int32_t vin = pin_uv(ADC_CHANNEL_6);
  if (uv < 0 || vin < 0) return;
  vin_sum += vin;
  if (!adc_samples || uv < iset_min) iset_min = uv;
  if (!adc_samples || uv > iset_max) iset_max = uv;
  iset_sum += uv;
  adc_samples++;
}

static void read_ina(bl_reading *r)
{
  uint16_t mfr, dev, die;
  if (read16(INA228_ADDR, INA_MANUFACTURER, &mfr) || read16(INA228_ADDR, INA_DEVICE, &dev)
      || read16(INA228_ADDR, INA_DIETEMP, &die)) { bus_restart(); return; }
  if (!ina228_ids_match(mfr, dev) || !samples) return;
  r->flags |= BL_F_INA;
  r->vout_uv = ina228_vbus_uv(ina228_raw24(bench_mean(vbus_sum, samples)));
  r->ishunt_ua = ina228_current_ua(ina228_raw24(bench_mean(shunt_sum, samples)), BENCH_SHUNT_MOHM);
  r->ina_die_mc = ina228_dietemp_mc(die);
}

static void read_gauge(bl_reading *r)
{
  uint16_t version, vcell, soc, crate;
  if (read16(MAX17048_ADDR, GAUGE_VERSION, &version) || read16(MAX17048_ADDR, GAUGE_VCELL, &vcell)
      || read16(MAX17048_ADDR, GAUGE_SOC, &soc) || read16(MAX17048_ADDR, GAUGE_CRATE, &crate)) { bus_restart(); return; }
  if (!max17048_version_match(version)) return;
  r->flags |= BL_F_GAUGE;
  r->vcell_uv = max17048_vcell_uv(vcell);
  r->soc_mpct = max17048_soc_mpct(soc);
  r->crate_mpct_h = max17048_crate_mpct_h(crate);
}

static void read_sht(bl_reading *r)
{
  uint8_t cmd = SHT45_MEASURE, b[SHT45_LEN];
  if (HAL_I2C_Master_Transmit(&hi2c2, (uint16_t)(SHT45_ADDR << 1), &cmd, 1, XFER_TIMEOUT_MS) != HAL_OK) { bus_restart(); return; }
  HAL_Delay(SHT45_WAIT_MS);
  if (HAL_I2C_Master_Receive(&hi2c2, (uint16_t)(SHT45_ADDR << 1), b, SHT45_LEN, XFER_TIMEOUT_MS) != HAL_OK) { bus_restart(); return; }
  if (sht45_crc8(b, 2) != b[2] || sht45_crc8(b + 3, 2) != b[5]) return;
  r->flags |= BL_F_SHT;
  r->sht_t_mc = sht45_t_mc((uint16_t)((b[0] << 8) | b[1]));
  r->sht_rh_mpct = sht45_rh_mpct((uint16_t)((b[3] << 8) | b[4]));
}

static void send_packet(void)
{
  bl_reading r;
  memset(&r, 0, sizeof r);
  r.seq = seq++;
  r.uptime_s = HAL_GetTick() / TICKS_PER_S;
  read_ina(&r);
  read_gauge(&r);
  read_sht(&r);
  if (HAL_GPIO_ReadPin(GPIOB, PGOOD_PIN) == GPIO_PIN_RESET) r.flags |= BL_F_PGOOD;
  if (HAL_GPIO_ReadPin(GPIOB, CHG_PIN) == GPIO_PIN_RESET) r.flags |= BL_F_CHG;
  if (adc_samples)
  {
    r.flags |= BL_F_ADC;
    r.iset_uv = bench_mean(iset_sum, adc_samples);
    r.iset_min_uv = iset_min;
    r.iset_max_uv = iset_max;
    r.vin_uv = bench_mean(vin_sum, adc_samples) * VIN_DIVIDER;
  }
  r.samples = (uint8_t)samples;
  r.misses = (uint8_t)misses;
  r.reset_cause = bl_guard_reset_code();
  r.faults = bl_guard_faults();
  r.boots = bl_guard_boots();
  r.fault_pc = bl_guard_fault_pc();
  r.tx_timeouts = tx_timeouts;
  r.i2c_restarts = i2c_restarts;
  r.i2c_unsticks = i2c_unsticks;
  shunt_sum = vbus_sum = iset_sum = vin_sum = 0;
  samples = misses = adc_samples = 0;
  bl_pack(&r, buf);
  APP_PRINTF("#bl seq=%u flags=%02X vin_uv=%d vout_uv=%d ishunt_ua=%d iset_uv=%d vcell_uv=%d soc_mpct=%d t_mc=%d rh_mpct=%d\n",
             (unsigned)r.seq, r.flags, (int)r.vin_uv, (int)r.vout_uv, (int)r.ishunt_ua, (int)r.iset_uv, (int)r.vcell_uv,
             (int)r.soc_mpct, (int)r.sht_t_mc, (int)r.sht_rh_mpct);
  if (tx_busy) return;   /* the previous send never finished: the check sees it and stops the watchdog */
  tx_started_ms = HAL_GetTick();
  tx_busy = 1;
  Radio.Send(buf, BL_PKT_LEN);
}

static void tick_task(void)
{
  sample();
  if (++ticks < TICKS_PER_PACKET) return;
  ticks = 0;
  send_packet();
}

static void on_tick(void *ctx)
{
  (void)ctx;
  UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Scan, CFG_SEQ_Prio_0);
}

static void on_tx_done(void)
{
  if (drop_done) { drop_done = 0; return; }   /* drill B3: as if the radio never said done */
  Radio.Sleep();
  last_done_ms = HAL_GetTick();
  tx_busy = 0;
  flash(1);
}

static void on_tx_timeout(void)
{
  APP_PRINTF("#bl tx timeout\n");
  Radio.Sleep();
  if (tx_timeouts < UINT16_MAX) tx_timeouts++;
  tx_busy = 0;
  flash(0);
}

int bl_role_check(void)
{
  common_drills();
  if (drill(2)) { APP_PRINTF("#bl drill radio: the next done is lost; expect reset=watchdog\n"); drop_done = 1; }
  uint32_t started = tx_started_ms, done = last_done_ms;   /* read before now: an ISR may move them */
  uint32_t now = HAL_GetTick();
  if (tx_busy && now - started > TICKS(TX_STUCK_MS))
  {
    if (!stuck_reported) APP_PRINTF("#bl radio stuck: no done or timeout after %u ms; watchdog reset next\n",
                                    (unsigned)((uint64_t)(now - started) * MS_PER_S / TICKS_PER_S));
    stuck_reported = 1;
    return 0;
  }
  if (now - done > TICKS(TX_HEALTH_MS))
  {
    if (!unhealthy_reported) APP_PRINTF("#bl no packet out for %u s; watchdog reset next\n",
                                        (unsigned)((now - done) / TICKS_PER_S));
    unhealthy_reported = 1;
    return 0;
  }
  stuck_reported = unhealthy_reported = 0;
  return 1;
}

static void role_init(void)
{
  APP_PRINTF("\nBENCHLINK TX (weather-station-2026 bench test, plain LoRa): one %u-byte packet every %u ms\n",
             BL_PKT_LEN, TICK_MS * TICKS_PER_PACKET);
  __HAL_RCC_GPIOB_CLK_ENABLE();
  GPIO_InitTypeDef pins = { .Pin = PGOOD_PIN | CHG_PIN, .Mode = GPIO_MODE_INPUT, .Pull = GPIO_PULLUP,
                            .Speed = GPIO_SPEED_FREQ_LOW };
  HAL_GPIO_Init(GPIOB, &pins);
  bus_start();
  adc_start();
  events.TxDone = on_tx_done;
  events.TxTimeout = on_tx_timeout;
  Radio.Init(&events);
  Radio.SetChannel(RF_FREQUENCY_HZ);
  Radio.SetTxConfig(MODEM_LORA, TX_POWER_DBM, 0, LORA_BW, LORA_SF, LORA_CR, LORA_PREAMBLE, false, true, 0, 0,
                    false, TX_TIMEOUT_MS);
  Radio.SetMaxPayloadLength(MODEM_LORA, BL_PKT_LEN);
  Radio.Sleep();
  last_done_ms = HAL_GetTick();
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Scan, UTIL_SEQ_RFU, tick_task);
  (void)UTIL_TIMER_Create(&tick_timer, TICK_MS, UTIL_TIMER_PERIODIC, on_tick, NULL);
  (void)UTIL_TIMER_Start(&tick_timer);
}

#else   /* BL_ROLE_rx */

#define HEX_LEN (2U * BL_PKT_LEN + 1U)
#define HEARTBEAT_S 10U
#define REARM_S 60U                 /* this long with nothing heard: restart reception */
#define PENDING_S 5U                /* a heard packet not handled within this: the main loop is stuck */
static uint16_t rx_len;
static int16_t rx_rssi;
static int8_t rx_snr;
static volatile int rx_state;   /* 1: packet, 2: error */
static unsigned checks, quiet_s, pending_s;
static uint32_t good, bad, errors, rearms;

static void listen(void) { Radio.Rx(0); }

static void rx_task(void)
{
  static const char digits[] = "0123456789abcdef";
  char hex[HEX_LEN];
  int state = rx_state;   /* taken once: a callback during the print must not be wiped below */
  rx_state = 0;
  if (!state) return;
  if (state == 1)
  {
    unsigned n = rx_len > BL_PKT_LEN ? BL_PKT_LEN : rx_len;
    for (unsigned i = 0; i < n; i++) { hex[2U * i] = digits[buf[i] >> 4]; hex[2U * i + 1U] = digits[buf[i] & 0xFU]; }
    hex[2U * n] = '\0';
    APP_PRINTF("#bl rssi=%d snr=%d len=%u hex=%s\n", (int)rx_rssi, (int)rx_snr, (unsigned)rx_len, hex);
    bl_reading r;
    int ok = bl_unpack(buf, rx_len, &r) == 0;
    if (ok) good++;
    else bad++;
    flash(ok);
  }
  else { APP_PRINTF("#bl rx error\n"); errors++; flash(0); }
  quiet_s = 0;
  listen();
}

int bl_role_check(void)
{
  common_drills();
  checks++;
  if (++quiet_s % REARM_S == 0 && !rx_state)
  {
    APP_PRINTF("#bl rx rearm: nothing heard for %u s\n", quiet_s);
    rearms++;
    Radio.Sleep();
    listen();
  }
  if (checks % HEARTBEAT_S == 0)
    APP_PRINTF("#bl hb up=%u good=%u bad=%u err=%u quiet_s=%u rearm=%u boots=%u reset=%s faults=%u\n",
               (unsigned)(HAL_GetTick() / TICKS_PER_S), (unsigned)good, (unsigned)bad, (unsigned)errors, quiet_s,
               (unsigned)rearms, (unsigned)bl_guard_boots(), bl_guard_reset_name(), (unsigned)bl_guard_faults());
  pending_s = rx_state ? pending_s + 1U : 0U;
  return pending_s < PENDING_S;
}

static void on_rx_done(uint8_t *payload, uint16_t size, int16_t rssi, int8_t snr)
{
  rx_len = size;
  memcpy(buf, payload, size > BL_PKT_LEN ? BL_PKT_LEN : size);
  rx_rssi = rssi;
  rx_snr = snr;
  rx_state = 1;
  UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Scan, CFG_SEQ_Prio_0);
}

static void on_rx_error(void)
{
  rx_state = 2;
  UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Scan, CFG_SEQ_Prio_0);
}

static void on_rx_timeout(void) { listen(); }

static void role_init(void)
{
  APP_PRINTF("\nBENCHLINK RX (weather-station-2026 bench test, plain LoRa): prints every packet\n");
  events.RxDone = on_rx_done;
  events.RxError = on_rx_error;
  events.RxTimeout = on_rx_timeout;
  Radio.Init(&events);
  Radio.SetChannel(RF_FREQUENCY_HZ);
  Radio.SetRxConfig(MODEM_LORA, LORA_BW, LORA_SF, LORA_CR, 0, LORA_PREAMBLE, 0, false, 0, true, 0, 0, false, true);
  Radio.SetMaxPayloadLength(MODEM_LORA, BL_PKT_LEN);
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Scan, UTIL_SEQ_RFU, rx_task);
  listen();
}
#endif

void SubghzApp_Init(void)
{
#ifdef BL_ROLE_tx
  bl_guard_start("tx");
#else
  bl_guard_start("rx");
#endif
  leds_buttons_init();
  role_init();
}
