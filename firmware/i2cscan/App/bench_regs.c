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
