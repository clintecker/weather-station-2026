/* I2C bench tool (README.md): checks the bus lines, lists every address that answers on I2C2, then
 * prints the INA228 and MAX17048 readings once a second and lists the bus again every 10 s, with one
 * reading of each phase B rail INA228 (load, solar, USB-C) that answers. The same
 * readings go to the bench OLED on SPI1 (oled.h), redrawn once a second.
 * It only reads: no register of any part is written, so the node firmware later finds every part as
 * it left it. Blocking HAL transfers with a short timeout, from one sequencer task: a bench tool, not
 * the node (stage0-node/App/i2c_bus.c is the interrupt-driven bus). PA9 is driven high at start and stays
 * high: the sensor power enable, carrier only (build-progression record 4.6 dated note, 2026-11-02: change
 * C's load switch is deferred to the carrier). On the bench PA9 is unconnected, so this is harmless. */
#include <string.h>
#include "bench_regs.h"
#include "bench_screen.h"
#include "oled.h"
#include "stm32_seq.h"
#include "stm32_timer.h"
#include "stm32wlxx_hal.h"
#include "subghz_phy_app.h"
#include "sys_app.h"
#include "utilities_def.h"

#define SDA_PIN GPIO_PIN_11       /* PA11 = D14, CN5.9 */
#define SCL_PIN GPIO_PIN_12       /* PA12 = D15, CN5.10 */
#define POWER_PIN GPIO_PIN_9      /* PA9 = D9, CN5.2 (CN10.19): sensor power enable (carrier only), high = on */
#define POWER_UP_MS 2U            /* a switch's turn-on (carrier) and the SHT45's 1 ms power-up (its datasheet tPU) */
#define I2C_TIMING 0x20323E5DU    /* 100 kHz at PCLK1 = 48 MHz, SDADEL 2: the node's value (stage0-node/App/i2c_bus.c) */
#define XFER_TIMEOUT_MS 10U       /* the longest transfer here, 3 bytes, takes ~0.4 ms at 100 kHz */
#define PROBE_TRIES 1U
#define TICK_MS 250U
#define TICKS_PER_LINE 4U         /* each line averages 4 INA228 samples: one line a second */
#define LINES_PER_SCAN 10U
#define INA228_ADDR 0x40U
#define MAX17048_ADDR 0x36U
/* The phase B rail monitors (stage0-node/App/power_config.h POWER_ADDR_LOAD, _SOLAR, _USB; power-metering.md
   section 7): read once a scan, so their address straps (0x48 is an A1-to-SDA rework) and their shunts can be
   checked before the node runs profile B. tests/test_i2cscan.py checks the addresses against power_config.h. */
static const struct { uint8_t addr; const char *rail; } RAILS[] = {
  { 0x41U, "load" }, { 0x45U, "solar" }, { 0x48U, "usb-c" },
};
#define FIRST_ADDR 0x08U          /* 0x00-0x07 and 0x78-0x7F are reserved (UM10204 table 4) */
#define LAST_ADDR 0x77U
#define NUM_MAX 16U

enum { INA_VSHUNT = 0x04, INA_VBUS = 0x05, INA_DIETEMP = 0x06, INA_MANUFACTURER = 0x3E, INA_DEVICE = 0x3F };
enum { GAUGE_VCELL = 0x02, GAUGE_SOC = 0x04, GAUGE_VERSION = 0x08, GAUGE_CRATE = 0x16 };

static I2C_HandleTypeDef hi2c2;
static UTIL_TIMER_Object_t tick_timer;
static unsigned ticks, lines;
static int64_t shunt_sum, vbus_sum;   /* the INA228 counts of this line's samples (ina228_count) */
static unsigned samples, misses;
static bench_view view;   /* the latest readings, for the OLED */
static oled_fb screen;
static int oled_failed;   /* the last frame timed out: said once, until a frame goes through again */

/* cppcheck-suppress constParameterPointer ; ST's HAL callback signature */
void HAL_I2C_MspInit(I2C_HandleTypeDef *hi2c)
{
  if (hi2c->Instance != I2C2) return;
  RCC_PeriphCLKInitTypeDef clk = { .PeriphClockSelection = RCC_PERIPHCLK_I2C2,
                                   .I2c2ClockSelection = RCC_I2C2CLKSOURCE_PCLK1 };
  (void)HAL_RCCEx_PeriphCLKConfig(&clk);
  __HAL_RCC_GPIOA_CLK_ENABLE();
  /* No internal pull-ups: the breakouts carry the bus pull-ups, and a missing one should show. */
  GPIO_InitTypeDef gpio = { .Pin = SDA_PIN | SCL_PIN, .Mode = GPIO_MODE_AF_OD, .Pull = GPIO_NOPULL,
                            .Speed = GPIO_SPEED_FREQ_LOW, .Alternate = GPIO_AF4_I2C2 };
  HAL_GPIO_Init(GPIOA, &gpio);
  __HAL_RCC_I2C2_CLK_ENABLE();
}

/* cppcheck-suppress constParameterPointer ; ST's HAL callback signature */
void HAL_I2C_MspDeInit(I2C_HandleTypeDef *hi2c)
{
  if (hi2c->Instance != I2C2) return;
  __HAL_RCC_I2C2_CLK_DISABLE();
  HAL_GPIO_DeInit(GPIOA, SDA_PIN | SCL_PIN);
}

/* The level is set before the pin becomes an output, so it never pulses low. */
static void sensors_on(void)
{
  __HAL_RCC_GPIOA_CLK_ENABLE();
  HAL_GPIO_WritePin(GPIOA, POWER_PIN, GPIO_PIN_SET);
  GPIO_InitTypeDef en = { .Pin = POWER_PIN, .Mode = GPIO_MODE_OUTPUT_PP, .Pull = GPIO_NOPULL,
                          .Speed = GPIO_SPEED_FREQ_LOW };
  HAL_GPIO_Init(GPIOA, &en);
  HAL_Delay(POWER_UP_MS);
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

/* The idle levels of SDA and SCL as inputs with the weak internal pull-down (about 40 kOhm): a breakout's
   pull-up (10 kOhm or less) still reads high, and an unconnected line reads low instead of floating. High
   on both means a powered breakout holds the bus up; low means no pull-up (hub unpowered or cable out)
   or a part holding the line. */
static void lines_line(void)
{
  (void)HAL_I2C_DeInit(&hi2c2);
  __HAL_RCC_GPIOA_CLK_ENABLE();
  GPIO_InitTypeDef gpio = { .Pin = SDA_PIN | SCL_PIN, .Mode = GPIO_MODE_INPUT, .Pull = GPIO_PULLDOWN,
                            .Speed = GPIO_SPEED_FREQ_LOW };
  HAL_GPIO_Init(GPIOA, &gpio);
  HAL_Delay(2U);   /* lets the pins settle after the switch from the I2C peripheral */
  int sda = HAL_GPIO_ReadPin(GPIOA, SDA_PIN) == GPIO_PIN_SET;
  int scl = HAL_GPIO_ReadPin(GPIOA, SCL_PIN) == GPIO_PIN_SET;
  APP_PRINTF("#lines SDA=%s SCL=%s: %s\n", sda ? "high" : "LOW", scl ? "high" : "LOW",
             sda && scl ? "pull-ups present" :
             !sda && !scl ? "no pull-ups: is the hub on 3V3 (CN6.4) and GND, and the cable in?" :
             "one line low: a part holds it, or SDA/SCL are swapped or open");
  HAL_GPIO_DeInit(GPIOA, SDA_PIN | SCL_PIN);
  bus_start();
}

static void scan_line(void)
{
  unsigned found = 0;
  for (uint8_t a = FIRST_ADDR; a <= LAST_ADDR; a++)
  {
    if (HAL_I2C_IsDeviceReady(&hi2c2, (uint16_t)(a << 1), PROBE_TRIES, XFER_TIMEOUT_MS) != HAL_OK) continue;
    if (found < BENCH_SCREEN_MAX_FOUND) view.found[found] = a;
    found++;
    APP_PRINTF("#scan 0x%02X %s\n", a, bench_part_name(a));
  }
  APP_PRINTF("#scan %u found\n", found);
  view.nfound = found;
  if (!found) lines_line();
}

static int read_reg(uint8_t addr7, uint8_t reg, uint8_t *buf, uint16_t len)
{
  return HAL_I2C_Mem_Read(&hi2c2, (uint16_t)(addr7 << 1), reg, I2C_MEMADD_SIZE_8BIT, buf, len, XFER_TIMEOUT_MS) == HAL_OK ? 0 : -1;
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

/* A failed transfer can leave the HAL handle in an error state: start the peripheral again. */
static void bus_restart(void)
{
  (void)HAL_I2C_DeInit(&hi2c2);
  bus_start();
}

static void ina_sample(void)
{
  uint32_t shunt, vbus;
  if (read24(INA228_ADDR, INA_VSHUNT, &shunt) || read24(INA228_ADDR, INA_VBUS, &vbus)) { misses++; bus_restart(); return; }
  shunt_sum += ina228_count(shunt);
  vbus_sum += ina228_count(vbus);
  samples++;
}

static void ina_line(void)
{
  uint16_t mfr, dev, die;
  char v[NUM_MAX], mv[NUM_MAX], ma[NUM_MAX], c[NUM_MAX];
  view.ina_ok = 0;
  if (read16(INA228_ADDR, INA_MANUFACTURER, &mfr) || read16(INA228_ADDR, INA_DEVICE, &dev)
      || read16(INA228_ADDR, INA_DIETEMP, &die)) { APP_PRINTF("#ina228 no answer at 0x40\n"); bus_restart(); return; }
  if (!ina228_ids_match(mfr, dev)) { APP_PRINTF("#ina228 0x40 is not an INA228 (ids %04X %04X)\n", mfr, dev); return; }
  if (!samples) { APP_PRINTF("#ina228 no samples this second (%u failed)\n", misses); return; }
  uint32_t shunt = ina228_raw24(bench_mean(shunt_sum, samples));
  uint32_t vbus = ina228_raw24(bench_mean(vbus_sum, samples));
  int32_t ua = ina228_current_ua(shunt, BENCH_SHUNT_UOHM);
  view.ina_ok = 1;
  view.ua = ua;
  view.vbus_uv = ina228_vbus_uv(vbus);
  APP_PRINTF("#ina228 vbus=%s V shunt=%s mV i=%s mA (%s) die=%s C\n",
             bench_fixed(v, sizeof v, ina228_vbus_uv(vbus), 2, 4, 0),
             bench_fixed(mv, sizeof mv, ina228_vshunt_nv(shunt), 3, 3, 1),
             bench_fixed(ma, sizeof ma, ua, 1, 2, 1),
             ua > 0 ? "battery discharging" : ua < 0 ? "battery charging" : "no current",
             bench_fixed(c, sizeof c, ina228_dietemp_mc(die), 2, 1, 0));
}

/* One phase B rail INA228: a single VSHUNT and VBUS reading (not averaged) in the part's own sign, VIN+ to
   VIN- positive, which is the rail's + direction (into the station for solar and USB-C, to the load for
   load; power spec section 3.1). Silent when the address does not answer: phase A has none of them. */
static void rail_line(uint8_t addr7, const char *rail)
{
  uint16_t mfr, dev, die;
  uint32_t shunt, vbus;
  char v[NUM_MAX], mv[NUM_MAX], ma[NUM_MAX], c[NUM_MAX];
  if (HAL_I2C_IsDeviceReady(&hi2c2, (uint16_t)(addr7 << 1), PROBE_TRIES, XFER_TIMEOUT_MS) != HAL_OK) return;
  if (read16(addr7, INA_MANUFACTURER, &mfr) || read16(addr7, INA_DEVICE, &dev) || read16(addr7, INA_DIETEMP, &die)
      || read24(addr7, INA_VSHUNT, &shunt) || read24(addr7, INA_VBUS, &vbus))
  { APP_PRINTF("#rail %s 0x%02X read failed\n", rail, addr7); bus_restart(); return; }
  if (!ina228_ids_match(mfr, dev)) { APP_PRINTF("#rail %s 0x%02X is not an INA228 (ids %04X %04X)\n", rail, addr7, mfr, dev); return; }
  APP_PRINTF("#rail %s 0x%02X vbus=%s V shunt=%s mV i=%s mA die=%s C\n", rail, addr7,
             bench_fixed(v, sizeof v, ina228_vbus_uv(vbus), 2, 4, 0),
             bench_fixed(mv, sizeof mv, ina228_vshunt_nv(shunt), 3, 3, 1),
             bench_fixed(ma, sizeof ma, ina228_current_ua(shunt, BENCH_SHUNT_UOHM), 1, 2, 1),
             bench_fixed(c, sizeof c, ina228_dietemp_mc(die), 2, 1, 0));
}

static void rails_line(void)
{
  for (size_t i = 0; i < sizeof RAILS / sizeof RAILS[0]; i++) rail_line(RAILS[i].addr, RAILS[i].rail);
}

static void gauge_line(void)
{
  uint16_t version, vcell, soc, crate;
  char v[NUM_MAX], pct[NUM_MAX], rate[NUM_MAX];
  view.gauge_ok = 0;
  if (read16(MAX17048_ADDR, GAUGE_VERSION, &version) || read16(MAX17048_ADDR, GAUGE_VCELL, &vcell)
      || read16(MAX17048_ADDR, GAUGE_SOC, &soc) || read16(MAX17048_ADDR, GAUGE_CRATE, &crate))
  { APP_PRINTF("#gauge no answer at 0x36\n"); bus_restart(); return; }
  if (!max17048_version_match(version)) { APP_PRINTF("#gauge 0x36 is not a MAX17048 (version %04X)\n", version); return; }
  view.gauge_ok = 1;
  view.vcell_uv = max17048_vcell_uv(vcell);
  view.soc_mpct = max17048_soc_mpct(soc);
  view.crate_mpct_h = max17048_crate_mpct_h(crate);
  APP_PRINTF("#gauge vcell=%s V soc=%s %% rate=%s %%/h\n",
             bench_fixed(v, sizeof v, max17048_vcell_uv(vcell), 2, 4, 0),
             bench_fixed(pct, sizeof pct, max17048_soc_mpct(soc), 2, 1, 0),
             bench_fixed(rate, sizeof rate, max17048_crate_mpct_h(crate), 1, 2, 1));
}

static void screen_update(void)
{
  bench_screen(&screen, &view);
  int failed = oled_show(&screen) != 0;
  if (failed && !oled_failed) APP_PRINTF("#oled SPI timeout: the frame was not sent\n");
  oled_failed = failed;
}

static void tick_task(void)
{
  ina_sample();
  if (++ticks < TICKS_PER_LINE) return;
  ticks = 0;
  ina_line();
  gauge_line();
  screen_update();
  shunt_sum = vbus_sum = 0;
  samples = misses = 0;
  if (++lines >= LINES_PER_SCAN) { lines = 0; scan_line(); rails_line(); }
}

static void on_tick(void *ctx)
{
  (void)ctx;
  UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Scan, CFG_SEQ_Prio_0);
}

void SubghzApp_Init(void)
{
  APP_PRINTF("\nI2CSCAN (weather-station-2026 bench tool): I2C2 SDA=PA11 (D14) SCL=PA12 (D15), 100 kHz, read only\n");
  APP_PRINTF("#help i>0: current out of the battery; i<0: into it (shunt %d mOhm in the cell + lead)\n", BENCH_SHUNT_MOHM);
  APP_PRINTF("#power PA9 (D9) high: sensor power enable (carrier only; unconnected on the bench)\n");
  sensors_on();
  oled_init();
  APP_PRINTF("#oled SSD1325 on SPI1 at %u Hz: SCLK PA5 (D13), DIN PA7 (D11), CS PA4 (D10), DC PC2 (D8), RST PC1 (D7)."
             " Write only: check the screen\n", oled_spi_hz());
  bus_start();
  lines_line();
  scan_line();
  rails_line();
  screen_update();
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Scan, UTIL_SEQ_RFU, tick_task);
  (void)UTIL_TIMER_Create(&tick_timer, TICK_MS, UTIL_TIMER_PERIODIC, on_tick, NULL);
  (void)UTIL_TIMER_Start(&tick_timer);
}
