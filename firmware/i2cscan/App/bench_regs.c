/* Bench-only helpers (bench_regs.h); the register conversions are in firmware/common/power_regs.c. */
#include "bench_regs.h"

/* The parts normally on this bench's bus. The phase B rail INA228s are at the node's addresses
   (stage0-node/App/power_config.h POWER_ADDR_*; tests/test_i2cscan.py checks them). */
static const struct { uint8_t addr; const char *name; } PARTS[] = {
  { 0x36U, "MAX17048 gauge" }, { 0x3CU, "SSD1305 OLED" }, { 0x3DU, "SSD1305 OLED" },
  { 0x40U, "INA228 battery monitor" }, { 0x41U, "INA228 load monitor (phase B)" },
  { 0x44U, "SHT45 air" }, { 0x45U, "INA228 solar monitor (phase B)" }, { 0x47U, "BMP581 pressure" },
  { 0x48U, "INA228 USB-C monitor (phase B)" }, { 0x53U, "LTR390 UV" }, { 0x70U, "SHTC3 enclosure" },
};

const char *bench_part_name(uint8_t addr7)
{
  for (size_t i = 0; i < sizeof PARTS / sizeof PARTS[0]; i++)
    if (PARTS[i].addr == addr7) return PARTS[i].name;
  return "?";
}

int32_t bench_mean(int64_t sum, unsigned n)
{
  if (n == 0) return 0;
  int64_t half = (int64_t)n / 2;
  return (int32_t)((sum < 0 ? sum - half : sum + half) / (int64_t)n);
}

char *bench_fixed(char *out, size_t n, int32_t value, unsigned drop, unsigned decimals, int sign)
{
  char digits[24];   /* |INT32_MIN| has 10 digits, plus a point, padding zeros and a sign */
  size_t len = 0, k = 0;
  int64_t v = value;
  uint64_t div = 1;
  if (drop > BENCH_FIXED_MAX_DIGITS || decimals > BENCH_FIXED_MAX_DIGITS)
  {
    if (n > 1) { out[0] = '?'; out[1] = '\0'; }
    else if (n == 1) out[0] = '\0';
    return out;
  }
  for (unsigned i = 0; i < drop; i++) div *= 10U;
  uint64_t mag = (uint64_t)(v < 0 ? -v : v);
  mag = (mag + div / 2) / div;   /* rounds half away from zero; div = 1 leaves it unchanged */
  for (unsigned i = 0; mag > 0 || i <= decimals; i++)
  {
    if (i == decimals && decimals > 0) digits[len++] = '.';
    digits[len++] = (char)('0' + mag % 10U);
    mag /= 10U;
  }
  int nonzero = 0;
  for (size_t i = 0; i < len; i++) nonzero |= digits[i] > '0';
  if (nonzero && v < 0) digits[len++] = '-';
  else if (nonzero && sign) digits[len++] = '+';
  if (n == 0) return out;
  while (len > 0 && k + 1 < n) out[k++] = digits[--len];
  out[k] = '\0';
  return out;
}

/* The node's vane table (stage0-node/App/mod_wind.c, which keeps it static): each position's resistance,
   clockwise from north, its nominal reading and its band (+-5 %, then +-10 mV). */
#define VANE_PULL_UP_OHM 10000UL
#define VANE_SUPPLY_MV 3300UL
#define VANE_OPEN_MV 3200U
#define VANE_TOL_PCT 5UL
#define VANE_ADC_MV 10U
#define VANE_MV(r) ((uint16_t)((VANE_SUPPLY_MV * (r) + ((r) + VANE_PULL_UP_OHM) / 2U) / ((r) + VANE_PULL_UP_OHM)))
#define VANE_OHMS(X) X(33000UL) X(6570UL) X(8200UL) X(891UL) X(1000UL) X(688UL) X(2200UL) X(1410UL) X(3900UL) \
                     X(3140UL) X(16000UL) X(14120UL) X(120000UL) X(42120UL) X(64900UL) X(21880UL)
#define VANE_NOMINAL(r) VANE_MV(r),
#define VANE_LOW(r) (uint16_t)(VANE_MV((r) * (100UL - VANE_TOL_PCT) / 100UL) - VANE_ADC_MV),
#define VANE_HIGH(r) (uint16_t)(VANE_MV((r) * (100UL + VANE_TOL_PCT) / 100UL) + VANE_ADC_MV),
#define VANE_POSITIONS 16U
static const uint16_t vane_mv[VANE_POSITIONS] = { VANE_OHMS(VANE_NOMINAL) };
static const uint16_t vane_low[VANE_POSITIONS] = { VANE_OHMS(VANE_LOW) };
static const uint16_t vane_high[VANE_POSITIONS] = { VANE_OHMS(VANE_HIGH) };
static const char *const vane_point[VANE_POSITIONS] = { "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                                                        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW" };

const char *bench_vane_point(uint16_t mv)
{
  if (mv > VANE_OPEN_MV) return "OPEN";
  unsigned best = VANE_POSITIONS;
  unsigned best_d = 0;
  for (unsigned i = 0; i < VANE_POSITIONS; i++)
  {
    if (mv < vane_low[i] || mv > vane_high[i]) continue;
    unsigned d = (unsigned)(mv > vane_mv[i] ? mv - vane_mv[i] : vane_mv[i] - mv);
    if (best == VANE_POSITIONS || d < best_d) { best = i; best_d = d; }
  }
  return best == VANE_POSITIONS ? "?" : vane_point[best];
}

static uint8_t sht_crc(const uint8_t *d)
{
  uint8_t crc = 0xFFU;
  for (unsigned i = 0; i < 2U; i++)
  {
    crc ^= d[i];
    for (unsigned bit = 0; bit < 8U; bit++) crc = (uint8_t)((crc & 0x80U) ? ((unsigned)crc << 1) ^ 0x31U : (unsigned)crc << 1);
  }
  return crc;
}

/* raw * span / div, rounded to nearest, plus offset (all in 0.01 units). */
static int32_t sht_scale(uint16_t raw, uint32_t span, uint32_t div, int32_t offset)
{
  return (int32_t)(((uint64_t)raw * span + div / 2U) / div) + offset;
}

int bench_sht_parse(const uint8_t b[6], int shtc3, int32_t *centi_c, int32_t *centi_rh)
{
  if (sht_crc(b) != b[2] || sht_crc(b + 3) != b[5]) return -1;
  uint16_t t = (uint16_t)((b[0] << 8) | b[1]), rh = (uint16_t)((b[3] << 8) | b[4]);
  uint32_t div = shtc3 ? 65536U : 65535U;
  *centi_c = sht_scale(t, 17500U, div, -4500);
  int32_t h = shtc3 ? sht_scale(rh, 10000U, div, 0) : sht_scale(rh, 12500U, div, -600);
  *centi_rh = h < 0 ? 0 : h > 10000 ? 10000 : h;
  return 0;
}

int32_t bench_bmp581_dhpa(const uint8_t b[3])
{
  uint32_t raw = (uint32_t)b[0] | ((uint32_t)b[1] << 8) | ((uint32_t)b[2] << 16);
  return (int32_t)((raw + 320U) / 640U);
}

uint32_t bench_ltr390_counts(const uint8_t b[3])
{
  return ((uint32_t)b[0] | ((uint32_t)b[1] << 8) | ((uint32_t)b[2] << 16)) & 0xFFFFFU;
}
