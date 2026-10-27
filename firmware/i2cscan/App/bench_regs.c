/* Register decoding for the I2C bench tool: see bench_regs.h for the registers and their units. */
#include "bench_regs.h"

#define INA228_MANUFACTURER 0x5449U   /* "TI" */
#define INA228_DEVICE 0x228U
#define MAX17048_VERSION 0x0010U
#define MAX17048_VERSION_MASK 0xFFF0U

/* The INA228's 20-bit two's-complement count from the top 20 of 24 bits (the low 4 are reserved). */
int32_t ina228_count(uint32_t raw24)
{
  int32_t count = (int32_t)((raw24 >> 4) & 0xFFFFFU);
  return count >= 0x80000 ? count - 0x100000 : count;
}

uint32_t ina228_raw24(int32_t count) { return ((uint32_t)count & 0xFFFFFU) << 4; }

int32_t ina228_vshunt_nv(uint32_t raw24) { return (int32_t)((int64_t)ina228_count(raw24) * 3125 / 10); }

int32_t ina228_vbus_uv(uint32_t raw24) { return (int32_t)((int64_t)ina228_count(raw24) * 3125 / 16); }

/* nV / mOhm = uA. From the count, so the nV rounding does not add to the current's. */
int32_t ina228_current_ua(uint32_t vshunt_raw24, int32_t shunt_mohm)
{
  return (int32_t)((int64_t)ina228_count(vshunt_raw24) * 3125 / (10 * (int64_t)shunt_mohm));
}

int32_t ina228_dietemp_mc(uint16_t raw16) { return (int32_t)(int16_t)raw16 * 125 / 16; }

int ina228_ids_match(uint16_t manufacturer, uint16_t device)
{
  return manufacturer == INA228_MANUFACTURER && (device >> 4) == INA228_DEVICE;
}

int32_t max17048_vcell_uv(uint16_t raw16) { return (int32_t)raw16 * 625 / 8; }

int32_t max17048_soc_mpct(uint16_t raw16) { return (int32_t)raw16 * 1000 / 256; }

int32_t max17048_crate_mpct_h(uint16_t raw16) { return (int32_t)(int16_t)raw16 * 208; }

int max17048_version_match(uint16_t version) { return (version & MAX17048_VERSION_MASK) == MAX17048_VERSION; }

const char *bench_part_name(uint8_t addr7)
{
  switch (addr7)
  {
    case 0x36: return "MAX17048 gauge";
    case 0x3C: case 0x3D: return "SSD1305 OLED";
    case 0x40: return "INA228 battery monitor";
    case 0x44: return "SHT45 air";
    case 0x47: return "BMP581 pressure";
    case 0x53: return "LTR390 UV";
    case 0x70: return "SHTC3 enclosure";
    default: return "?";
  }
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
