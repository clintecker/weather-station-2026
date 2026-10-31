/* Device models for the host I2C bus (i2c_sim.h): what each part answers. One switch on the kind,
 * so the harness needs no function pointers. Tasks 4-6 of the WSMP bench station plan add the parts. */
#include <string.h>
#include "i2c_sim.h"
#include "stage0.h"   /* ws_crc8, WS_SHT45_* */

/* DEVK_TEST: a plain device. A read gives the bytes 0xA0 + i; a register read gives reg + i; a write
   is accepted and kept. */
static uint8_t test_written[I2C_SIM_DEVICES][I2C_SIM_BUF];

/* DEVK_SHT45 (datasheet section 4): command 0xFD starts a measurement of up to 8.3 ms; a read then
   gives the T word, its CRC, the RH word, its CRC. Command 0x89 makes the next read give the serial,
   high word first, in the same form. A read sooner than 9 ms after a measure command is flagged (the
   driver must wait), and so is a 0x89 between a measure command and its read. An unknown command is
   a NACK. */
typedef struct { uint16_t t_raw, rh_raw; int bad_crc, serial_bad, serial_fails, measuring, serial_next; uint32_t serial; uint64_t measured_at; } sht45_t;
static sht45_t sht45[I2C_SIM_DEVICES];
static int sht45_too_early, sht45_commands, sht45_interleaved, sht45_serial_commands;
#define SHT45_READY_MS 9U
void model_sht45_set(int dev, uint16_t t_raw, uint16_t rh_raw, int bad_crc)
{
  sht45[dev].t_raw = t_raw; sht45[dev].rh_raw = rh_raw; sht45[dev].bad_crc = bad_crc;
}
void model_sht45_set_serial(int dev, uint32_t serial, int bad) { sht45[dev].serial = serial; sht45[dev].serial_bad = bad; }
void model_sht45_serial_fail_next(int dev, int n) { sht45[dev].serial_fails = n; }
int model_sht45_read_too_early(void) { return sht45_too_early; }
int model_sht45_commands(void) { return sht45_commands; }
int model_sht45_interleaved(void) { return sht45_interleaved; }
int model_sht45_serial_commands(void) { return sht45_serial_commands; }

static int sht45_write(int dev, const uint8_t *data, uint16_t n)
{
  sht45_t *s = &sht45[dev];
  if (n == 1 && data[0] == WS_SHT4X_SERIAL)
  {
    if (s->serial_bad == 2) return -1;
    sht45_serial_commands++;
    if (s->measuring) sht45_interleaved = 1;
    s->serial_next = 1;
    return 0;
  }
  if (n != 1 || data[0] != WS_SHT45_MEASURE) return -1;
  sht45_commands++;
  s->measured_at = sim_now();
  s->measuring = 1;
  s->serial_next = 0;
  return 0;
}

static void words(uint8_t *data, uint16_t a, uint16_t b, int bad)
{
  data[0] = (uint8_t)(a >> 8); data[1] = (uint8_t)a; data[2] = ws_crc8(data, 2);
  data[3] = (uint8_t)(b >> 8); data[4] = (uint8_t)b; data[5] = (uint8_t)(ws_crc8(data + 3, 2) ^ (bad ? 1U : 0U));
}

static int sht45_read(int dev, uint8_t *data, uint16_t n)
{
  sht45_t *s = &sht45[dev];
  if (n != WS_SHT45_REPLY_LEN) return -1;
  if (s->serial_next)
  {
    s->serial_next = 0;
    words(data, (uint16_t)(s->serial >> 16), (uint16_t)s->serial, s->serial_bad == 1 || s->serial_fails > 0);
    if (s->serial_fails > 0) s->serial_fails--;
    return 0;
  }
  if (sim_now() - s->measured_at < (uint64_t)SHT45_READY_MS * SIM_UNITS_PER_MS) sht45_too_early = 1;
  s->measuring = 0;
  words(data, s->t_raw, s->rh_raw, s->bad_crc);
  return 0;
}

/* DEVK_SHTC3 (datasheet sections 5.4-5.9): wake 0x3517, measure 0x7866 (normal mode, T first, no clock
   stretching), sleep 0xB098. A command other than wake while asleep is a NACK; a read before a
   measurement is a NACK. */
typedef struct { uint16_t t_raw, rh_raw; int asleep, measured; } shtc3_t;
static shtc3_t shtc3[I2C_SIM_DEVICES];
void model_shtc3_set(int dev, uint16_t t_raw, uint16_t rh_raw) { shtc3[dev].t_raw = t_raw; shtc3[dev].rh_raw = rh_raw; }
int model_shtc3_asleep(int dev) { return shtc3[dev].asleep; }

static int shtc3_write(int dev, const uint8_t *data, uint16_t n)
{
  uint16_t cmd = n == 2 ? (uint16_t)(data[0] << 8 | data[1]) : 0;
  shtc3_t *s = &shtc3[dev];
  if (cmd == 0x3517) { s->asleep = 0; return 0; }
  if (s->asleep) return -1;
  if (cmd == 0x7866) { s->measured = 1; return 0; }
  if (cmd == 0xB098) { s->asleep = 1; s->measured = 0; return 0; }
  return -1;
}

static int shtc3_read(int dev, uint8_t *data, uint16_t n)
{
  shtc3_t *s = &shtc3[dev];
  if (n != 6 || s->asleep || !s->measured) return -1;
  data[0] = (uint8_t)(s->t_raw >> 8); data[1] = (uint8_t)s->t_raw; data[2] = ws_crc8(data, 2);
  data[3] = (uint8_t)(s->rh_raw >> 8); data[4] = (uint8_t)s->rh_raw; data[5] = ws_crc8(data + 3, 2);
  s->measured = 0;
  return 0;
}

/* DEVK_BMP581 and DEVK_LTR390: register parts. A register write is [register, value]. The data
   registers answer the set value (little-endian) only while the part is configured as the module
   needs; otherwise they read 0. A power cycle clears the configuration. */
typedef struct { uint8_t id, osr, odr, main_ctrl; uint32_t data; } regdev_t;
static regdev_t regdev[I2C_SIM_DEVICES];
void model_reg_set_id(int dev, uint8_t id) { regdev[dev].id = id; }
void model_reg_power_cycle(int dev) { regdev[dev].osr = regdev[dev].odr = regdev[dev].main_ctrl = 0; }
void model_reg_set_data(int dev, uint32_t data) { regdev[dev].data = data; }

static int reg_write(int kind, int dev, const uint8_t *data, uint16_t n)
{
  regdev_t *r = &regdev[dev];
  if (n != 2) return -1;
  if (kind == DEVK_BMP581 && data[0] == 0x36) r->osr = data[1];
  else if (kind == DEVK_BMP581 && data[0] == 0x37) r->odr = data[1];
  else if (kind == DEVK_LTR390 && data[0] == 0x00) r->main_ctrl = data[1];
  return 0;
}

static int reg_read(int kind, int dev, uint8_t reg, uint8_t *data, uint16_t n)
{
  const regdev_t *r = &regdev[dev];
  int id_reg = kind == DEVK_BMP581 ? 0x01 : 0x06, data_reg = kind == DEVK_BMP581 ? 0x20 : 0x10;
  int ready = kind == DEVK_BMP581 ? (r->osr == 0x40 && r->odr == 0x82) : r->main_ctrl == 0x0A;
  uint32_t v = ready ? r->data : 0U;
  if (reg == id_reg && n == 1) { data[0] = r->id; return 0; }
  if (reg != data_reg || n != 3) return -1;
  data[0] = (uint8_t)v; data[1] = (uint8_t)(v >> 8); data[2] = (uint8_t)(v >> 16);
  return 0;
}

/* DEVK_INA228 (TI SBOS904 / SLYS021A sections 7.6 and 8.1). Each device has its own physical shunt
   (micro-ohm, default 15000), a true current through it (uA, + from VIN+ to VIN-), a bus voltage and
   a die temperature, all set by the test; the registers follow from them as on the part:
     VSHUNT 0x04  ua x shunt in 312.5 nV counts (78.125 nV with CONFIG.ADCRANGE), rounded, 20-bit
                  signed: 37,604 uA through 15,000 uOhm is 564.06 uV, 1805 counts.
     CURRENT 0x07 VSHUNT x 4096 / SHUNT_CAL, the SHUNT_CAL actually written: with
                  CURRENT_LSB = SHUNT_CAL / (13107.2e6 x R) a count is VSHUNT / (R x CURRENT_LSB)
                  (the x4 of ADCRANGE = 1 cancels the finer VSHUNT step). 0 while SHUNT_CAL is 0;
                  clipped to the 20-bit signed range. 1805 counts with SHUNT_CAL 1966 is 3761 (37.6 mA).
     VBUS 0x05    195.3125 uV counts, rounded: 3,845,898 uV is 19691.
     DIETEMP 0x06 7.8125 m degC counts, 16-bit signed: 24,101 m degC is 3085, -1000 is 0xFF80.
     POWER 0x08   VBUS x |CURRENT| / 16384 (3.2 x CURRENT_LSB W a count), 24-bit unsigned.
     ENERGY 0x09  40-bit unsigned, 16 x 3.2 x CURRENT_LSB J a count: the integral of VBUS x |CURRENT|
                  / 262144 counts a second (4.000 V at 500 mA, SHUNT_CAL 1966: 3906 a second).
     CHARGE 0x0A  40-bit signed, CURRENT_LSB x 1 s a count: the integral of CURRENT.
     ids          MANUFACTURER_ID 0x3E = 0x5449, DEVICE_ID 0x3F = 0x2281.
   The accumulators integrate the CURRENT register value, not the true current, while ADC_CONFIG.MODE
   converts the shunt continuously (0xA, 0xB, 0xE, 0xF; reset 0xF): the sum over the part's conversions
   is that integral (the 3 ms conversion grain is not modelled). Their remainders are kept, so a read
   gives the floor of the integral. CONFIG 0x00 and ADC_CONFIG 0x01 accept writes: CONFIG.RST (bit 15)
   is a power-on reset, CONFIG.RSTACC (bit 14) clears the accumulators, both self-clearing; ADCRANGE
   (bit 4) selects the shunt range. SHUNT_CAL 0x02 keeps its 15-bit field. The other writable
   registers (0x03, 0x0B-0x11) accept and ignore a write; anything else is a NACK. A power cycle
   (power-on reset) restores the reset values: CONFIG 0, ADC_CONFIG 0xFB68, SHUNT_CAL 0x1000,
   accumulators 0. Every INA228 index is independent, so several parts at distinct addresses work. */
#define SIM_UNITS_PER_S ((int64_t)1000 * SIM_UNITS_PER_MS)
#define INA_CONFIG_RST 0x8000U
#define INA_CONFIG_RSTACC 0x4000U
#define INA_CONFIG_KEPT 0x3FF0U             /* CONVDLY, TEMPCOMP, ADCRANGE; bits 3-0 read 0 */
#define INA_ADCRANGE 0x0010U
#define INA_ADC_CONFIG_RESET 0xFB68U
#define INA_SHUNT_CAL_RESET 0x1000U
#define INA_SHUNT_CAL_FIELD 0x7FFFU
#define INA_DEFAULT_SHUNT_UOHM 15000
#define INA_DEFAULT_DIE_MC 25000
#define INA_COUNT20_MAX 0x7FFFF
#define INA_COUNT20_MIN (-0x80000)
#define INA_ENERGY_DIV 262144               /* VBUS counts x CURRENT counts x 1 s per ENERGY count */
#define INA_POWER_DIV 16384                 /* VBUS counts x CURRENT counts per POWER count */
#define REG40_MASK 0xFFFFFFFFFFULL
typedef struct { int32_t uv, ua, shunt_uohm, die_mc; uint16_t cal, config, adc_config;
                 int64_t charge, charge_frac, energy, energy_frac; uint64_t at; } ina228_t;
static ina228_t ina[I2C_SIM_DEVICES];

/* a / b rounded half away from zero, for b > 0 */
static int64_t div_round(int64_t a, int64_t b)
{
  return a >= 0 ? (a + b / 2) / b : -((b / 2 - a) / b);
}

static int64_t clamp64(int64_t v, int64_t lo, int64_t hi) { return v < lo ? lo : v > hi ? hi : v; }
static int32_t count20(int64_t v) { return (int32_t)clamp64(v, INA_COUNT20_MIN, INA_COUNT20_MAX); }
static uint32_t raw24(int32_t count) { return ((uint32_t)count & 0xFFFFFU) << 4; }
static int64_t abs64(int64_t v) { return v < 0 ? -v : v; }

static int32_t ina228_vshunt(const ina228_t *p)
{
  int64_t pv = (int64_t)p->ua * p->shunt_uohm;                     /* uA x uOhm = pV */
  return count20(div_round(pv, (p->config & INA_ADCRANGE) ? 78125 : 312500));
}

static int32_t ina228_current(const ina228_t *p)
{
  if (p->cal == 0U) return 0;
  return count20(div_round((int64_t)ina228_vshunt(p) * 4096, p->cal));
}

static int32_t ina228_vbus(const ina228_t *p) { return count20(div_round((int64_t)p->uv * 16, 3125)); }
static uint16_t ina228_die(const ina228_t *p) { return (uint16_t)clamp64(div_round((int64_t)p->die_mc * 128, 1000), INT16_MIN, INT16_MAX); }

static int ina228_shunt_continuous(const ina228_t *p)
{
  unsigned mode = p->adc_config >> 12;
  return mode == 0xAU || mode == 0xBU || mode == 0xEU || mode == 0xFU;
}

/* Adds rate x dt / div to a register (count) and its remainder (count x sim units), floor-normalised.
   rate <= 2^38 and dt split into whole seconds and the rest keep every product inside int64 for
   gaps of up to 2^25 s between reads. */
static void accumulate(int64_t *reg, int64_t *frac, int64_t rate, int64_t dt, int64_t div)
{
  int64_t whole = rate * (dt / SIM_UNITS_PER_S), unit = div * SIM_UNITS_PER_S;
  *reg += whole / div;
  *frac += (whole % div) * SIM_UNITS_PER_S + rate * (dt % SIM_UNITS_PER_S);
  *reg += *frac / unit;
  *frac %= unit;
  if (*frac < 0) { *frac += unit; (*reg)--; }
}

static void ina228_advance(ina228_t *p)
{
  uint64_t now = sim_now();
  int64_t dt = (int64_t)(now - p->at);
  p->at = now;
  if (!ina228_shunt_continuous(p)) return;
  int32_t cur = ina228_current(p);
  accumulate(&p->charge, &p->charge_frac, cur, dt, 1);
  accumulate(&p->energy, &p->energy_frac, abs64(ina228_vbus(p)) * abs64(cur), dt, INA_ENERGY_DIV);
}

/* Power-on reset: the registers return to their reset values; the physics (bus, current, shunt,
   die) stays. */
static void ina228_por(ina228_t *p)
{
  *p = (ina228_t){ .uv = p->uv, .ua = p->ua, .shunt_uohm = p->shunt_uohm, .die_mc = p->die_mc,
                   .cal = INA_SHUNT_CAL_RESET, .adc_config = INA_ADC_CONFIG_RESET, .at = sim_now() };
}

void model_ina228_set(int dev, int32_t uv, int32_t ua) { ina228_advance(&ina[dev]); ina[dev].uv = uv; ina[dev].ua = ua; }
void model_ina228_shunt(int dev, int32_t uohm) { ina228_advance(&ina[dev]); ina[dev].shunt_uohm = uohm < 0 ? 0 : uohm; }
void model_ina228_die(int dev, int32_t milli_c) { ina[dev].die_mc = milli_c; }
/* A brown-out or a quick re-plug: the registers return to their reset values, with no bus error. */
void model_ina228_power_cycle(int dev) { ina228_advance(&ina[dev]); ina228_por(&ina[dev]); }

static void put(uint8_t *data, uint16_t n, uint32_t v)
{
  for (uint16_t i = 0; i < n; i++) data[i] = (uint8_t)(v >> (8U * (n - 1U - i)));
}

static void put40(uint8_t *data, uint64_t v)
{
  for (unsigned i = 0; i < 5U; i++) data[i] = (uint8_t)(v >> (8U * (4U - i)));
}

/* The 40-bit accumulators: 1 if reg is one of them (and fills data). */
static int ina228_accumulator(const ina228_t *p, uint8_t reg, uint8_t *data)
{
  if (reg == 0x09) put40(data, (uint64_t)p->energy & REG40_MASK);
  else if (reg == 0x0A) put40(data, (uint64_t)p->charge & REG40_MASK);
  else return 0;
  return 1;
}

static int ina228_read(int dev, uint8_t reg, uint8_t *data, uint16_t n)
{
  ina228_t *p = &ina[dev];
  ina228_advance(p);
  if (n == 5) return ina228_accumulator(p, reg, data) ? 0 : -1;
  int32_t cur = ina228_current(p), vbus = ina228_vbus(p);
  uint32_t power = (uint32_t)clamp64(abs64(vbus) * abs64(cur) / INA_POWER_DIV, 0, 0xFFFFFF);
  const struct { uint8_t reg; uint16_t n; uint32_t v; } regs[] = {
    { 0x00, 2, p->config }, { 0x01, 2, p->adc_config }, { 0x02, 2, p->cal },
    { 0x04, 3, raw24(ina228_vshunt(p)) }, { 0x05, 3, raw24(vbus) }, { 0x06, 2, ina228_die(p) },
    { 0x07, 3, raw24(cur) }, { 0x08, 3, power }, { 0x3E, 2, 0x5449 }, { 0x3F, 2, 0x2281 } };
  for (unsigned i = 0; i < sizeof regs / sizeof regs[0]; i++)
    if (regs[i].reg == reg && regs[i].n == n) { put(data, n, regs[i].v); return 0; }
  return -1;
}

static void ina228_write_config(ina228_t *p, uint16_t v)
{
  if (v & INA_CONFIG_RST) { ina228_por(p); return; }
  if (v & INA_CONFIG_RSTACC) p->charge = p->charge_frac = p->energy = p->energy_frac = 0;
  p->config = (uint16_t)(v & INA_CONFIG_KEPT);
}

static int ina228_write(int dev, const uint8_t *data, uint16_t n)
{
  ina228_t *p = &ina[dev];
  uint8_t reg = data[0];
  if (n != 3 || (reg > 0x03 && (reg < 0x0B || reg > 0x11))) return -1;
  ina228_advance(p);
  uint16_t v = (uint16_t)(data[1] << 8 | data[2]);
  if (reg == 0x00) ina228_write_config(p, v);
  else if (reg == 0x01) p->adc_config = v;
  else if (reg == 0x02) p->cal = (uint16_t)(v & INA_SHUNT_CAL_FIELD);
  return 0;
}

/* DEVK_MAX17048 (Analog Devices MAX17048/9): VERSION 0x08 = 0x0012; VCELL 0x02 in 78.125 uV counts
   (3,846,015 uV is 49229); SOC 0x04 in 1/256 % (0x4E66 is 78.398 %); CRATE 0x16 two's complement,
   0.208 %/h a count (-624 m%/h is 0xFFFD). The gauge senses the cell, not the charger output, so its
   VCELL is set apart from any INA228's VBUS; a reset gauge reads 4.000 V, 0 %, 0 %/h. The part has
   one fixed address (0x36), so the cell, rate and fine SOC setters act on every MAX17048 index. */
typedef struct { uint16_t soc_256; int32_t cell_uv, rate_mpct_h; } gauge_t;
static gauge_t gauge[I2C_SIM_DEVICES];
#define GAUGE_DEFAULT_CELL_UV 4000000
void model_max17048_set(int dev, uint8_t soc) { gauge[dev].soc_256 = (uint16_t)(soc << 8); }
void model_max17048_soc_256(uint16_t soc_256)
{
  for (int i = 0; i < I2C_SIM_DEVICES; i++) gauge[i].soc_256 = soc_256;
}
void model_max17048_cell(int32_t uv)
{
  for (int i = 0; i < I2C_SIM_DEVICES; i++) gauge[i].cell_uv = uv;
}
void model_max17048_rate(int32_t mpct_h)
{
  for (int i = 0; i < I2C_SIM_DEVICES; i++) gauge[i].rate_mpct_h = mpct_h;
}

static int max17048_read(int dev, uint8_t reg, uint8_t *data, uint16_t n)
{
  const gauge_t *g = &gauge[dev];
  if (n != 2) return -1;
  if (reg == 0x08) put(data, n, 0x0012);
  else if (reg == 0x02) put(data, n, (uint32_t)clamp64(div_round((int64_t)g->cell_uv * 128, 10000), 0, 0xFFFF));
  else if (reg == 0x04) put(data, n, g->soc_256);
  else if (reg == 0x16) put(data, n, (uint16_t)clamp64(div_round(g->rate_mpct_h, 208), INT16_MIN, INT16_MAX));
  else return -1;
  return 0;
}

/* DEVK_MUX (TCA9548A, datasheet section 8.6.1): one control register, a bit for each channel. */
#define MUX_LOG 64
static uint8_t mux_xor, mux_xor_idle;
static int mux_log[MUX_LOG], nmux_log, nmux_reads;
void model_mux_readback_xor(uint8_t xor_mask) { mux_xor = xor_mask; }
void model_mux_readback_xor_idle(uint8_t xor_mask) { mux_xor_idle = xor_mask; }   /* only with no channel selected */
int model_mux_write_count(void) { return nmux_log; }
int model_mux_writes(int i) { return i >= 0 && i < nmux_log && i < MUX_LOG ? mux_log[i] : -1; }
int model_mux_reads(void) { return nmux_reads; }

static int mux_write(const uint8_t *data, uint16_t n)
{
  if (n != 1) return -1;
  if (nmux_log < MUX_LOG) mux_log[nmux_log] = data[0];
  nmux_log++;
  i2c_sim_mux_set_mask(data[0]);
  return 0;
}

static int mux_read(uint8_t *data, uint16_t n)
{
  if (n != 1) return -1;
  nmux_reads++;
  data[0] = (uint8_t)(i2c_sim_mux_mask() ^ mux_xor ^ (i2c_sim_mux_mask() == 0U ? mux_xor_idle : 0U));
  return 0;
}

/* DEVK_EEPROM (24LC32A): 4 KiB; a read past the end wraps to 0, as the part's address counter does. */
#define EEPROM_LEN 4096U
static uint8_t eeprom[I2C_SIM_DEVICES][EEPROM_LEN];
static int eeprom_fails[I2C_SIM_DEVICES], eeprom_corrupts[I2C_SIM_DEVICES], eeprom_skips[I2C_SIM_DEVICES];
static uint16_t eeprom_corrupt_at[I2C_SIM_DEVICES];   /* the byte the next corrupted reads flip */
void model_eeprom_write(int dev, uint16_t at, const uint8_t *data, uint16_t n)
{
  for (uint16_t i = 0; i < n; i++) eeprom[dev][(at + i) % EEPROM_LEN] = data[i];
}
void model_eeprom_fail_next(int dev, int n) { eeprom_fails[dev] = n; eeprom_skips[dev] = 0; }
void model_eeprom_fail_after(int dev, int skip, int n) { eeprom_fails[dev] = n; eeprom_skips[dev] = skip; }
void model_eeprom_corrupt_next(int dev, int n) { model_eeprom_corrupt_at(dev, 0x20U, n); }
void model_eeprom_corrupt_at(int dev, uint16_t at, int n) { eeprom_corrupt_at[dev] = at; eeprom_corrupts[dev] = n; }

static int eeprom_read(int dev, uint16_t at, uint8_t *data, uint16_t n)
{
  if (eeprom_skips[dev] > 0) eeprom_skips[dev]--;
  else if (eeprom_fails[dev] > 0) { eeprom_fails[dev]--; return -1; }
  for (uint16_t i = 0; i < n; i++) data[i] = eeprom[dev][(at + i) % EEPROM_LEN];
  uint16_t c = eeprom_corrupt_at[dev];
  if (eeprom_corrupts[dev] > 0 && at <= c && n > c - at) { eeprom_corrupts[dev]--; data[c - at] ^= 1U; }
  return 0;
}

int model_write(int kind, int dev, const uint8_t *data, uint16_t n)
{
  switch (kind)
  {
    case DEVK_MUX: return mux_write(data, n);
    case DEVK_INA228: return ina228_write(dev, data, n);
    case DEVK_TEST: memcpy(test_written[dev], data, n < I2C_SIM_BUF ? n : I2C_SIM_BUF); return 0;
    case DEVK_SHT45: return sht45_write(dev, data, n);
    case DEVK_SHTC3: return shtc3_write(dev, data, n);
    case DEVK_BMP581: case DEVK_LTR390: return reg_write(kind, dev, data, n);
    default: return -1;
  }
}

int model_read(int kind, int dev, uint8_t *data, uint16_t n)
{
  switch (kind)
  {
    case DEVK_TEST: for (uint16_t i = 0; i < n; i++) data[i] = (uint8_t)(0xA0U + i); return 0;
    case DEVK_SHT45: return sht45_read(dev, data, n);
    case DEVK_SHTC3: return shtc3_read(dev, data, n);
    case DEVK_MUX: return mux_read(data, n);
    default: return -1;
  }
}

int model_mem_read(int kind, int dev, uint16_t reg, uint8_t *data, uint16_t n)
{
  switch (kind)
  {
    case DEVK_BMP581: case DEVK_LTR390: return reg_read(kind, dev, (uint8_t)reg, data, n);
    case DEVK_INA228: return ina228_read(dev, (uint8_t)reg, data, n);
    case DEVK_MAX17048: return max17048_read(dev, (uint8_t)reg, data, n);
    case DEVK_EEPROM: return eeprom_read(dev, reg, data, n);
    case DEVK_TEST: for (uint16_t i = 0; i < n; i++) data[i] = (uint8_t)(reg + i); return 0;
    default: return -1;
  }
}

void model_reset(int kind, int dev)
{
  if (kind == DEVK_TEST) memset(test_written[dev], 0, sizeof test_written[dev]);
  if (kind == DEVK_SHT45) sht45[dev] = (sht45_t){ .t_raw = 0x8000, .rh_raw = 0x8000 };
  if (kind == DEVK_SHTC3) shtc3[dev] = (shtc3_t){ .t_raw = 0x8000, .rh_raw = 0x8000, .asleep = 1 };
  if (kind == DEVK_BMP581) regdev[dev] = (regdev_t){ .id = 0x50 };
  if (kind == DEVK_LTR390) regdev[dev] = (regdev_t){ .id = 0xB2 };
  if (kind == DEVK_INA228)
  {
    ina[dev] = (ina228_t){ .shunt_uohm = INA_DEFAULT_SHUNT_UOHM, .die_mc = INA_DEFAULT_DIE_MC };
    ina228_por(&ina[dev]);
  }
  if (kind == DEVK_MAX17048) gauge[dev] = (gauge_t){ .cell_uv = GAUGE_DEFAULT_CELL_UV };
  if (kind == DEVK_EEPROM)
  {
    for (unsigned i = 0; i < EEPROM_LEN; i++) eeprom[dev][i] = (uint8_t)i;
    eeprom_fails[dev] = eeprom_corrupts[dev] = 0;
  }
}
