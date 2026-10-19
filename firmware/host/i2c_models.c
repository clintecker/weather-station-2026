/* Device models for the host I2C bus (i2c_sim.h): what each part answers. One switch on the kind,
 * so the harness needs no function pointers. Tasks 4-6 of the WSMP bench station plan add the parts. */
#include <string.h>
#include "i2c_sim.h"
#include "stage0.h"   /* ws_crc8, WS_SHT45_* */

/* DEVK_TEST: a plain device. A read gives the bytes 0xA0 + i; a register read gives reg + i; a write
   is accepted and kept. */
static uint8_t test_written[I2C_SIM_DEVICES][I2C_SIM_BUF];

/* DEVK_SHT45 (datasheet section 4): command 0xFD starts a measurement of up to 8.3 ms; a read then
   gives the T word, its CRC, the RH word, its CRC. A read sooner than 9 ms after the command is
   flagged (the driver must wait). An unknown command is a NACK. */
typedef struct { uint16_t t_raw, rh_raw; int bad_crc; uint64_t measured_at; } sht45_t;
static sht45_t sht45[I2C_SIM_DEVICES];
static int sht45_too_early;
#define SHT45_READY_MS 9U
void model_sht45_set(int dev, uint16_t t_raw, uint16_t rh_raw, int bad_crc)
{
  sht45[dev].t_raw = t_raw; sht45[dev].rh_raw = rh_raw; sht45[dev].bad_crc = bad_crc;
}
int model_sht45_read_too_early(void) { return sht45_too_early; }

static int sht45_write(int dev, const uint8_t *data, uint16_t n)
{
  if (n != 1 || data[0] != WS_SHT45_MEASURE) return -1;
  sht45[dev].measured_at = sim_now();
  return 0;
}

static int sht45_read(int dev, uint8_t *data, uint16_t n)
{
  if (n != WS_SHT45_REPLY_LEN) return -1;
  if (sim_now() - sht45[dev].measured_at < (uint64_t)SHT45_READY_MS * SIM_UNITS_PER_MS) sht45_too_early = 1;
  data[0] = (uint8_t)(sht45[dev].t_raw >> 8); data[1] = (uint8_t)sht45[dev].t_raw; data[2] = ws_crc8(data, 2);
  data[3] = (uint8_t)(sht45[dev].rh_raw >> 8); data[4] = (uint8_t)sht45[dev].rh_raw;
  data[5] = (uint8_t)(ws_crc8(data + 3, 2) ^ (sht45[dev].bad_crc ? 1U : 0U));
  return 0;
}

int model_write(int kind, int dev, const uint8_t *data, uint16_t n)
{
  switch (kind)
  {
    case DEVK_TEST: memcpy(test_written[dev], data, n < I2C_SIM_BUF ? n : I2C_SIM_BUF); return 0;
    case DEVK_SHT45: return sht45_write(dev, data, n);
    default: return -1;
  }
}

int model_read(int kind, int dev, uint8_t *data, uint16_t n)
{
  switch (kind)
  {
    case DEVK_TEST: for (uint16_t i = 0; i < n; i++) data[i] = (uint8_t)(0xA0U + i); return 0;
    case DEVK_SHT45: return sht45_read(dev, data, n);
    default: return -1;
  }
}

int model_mem_read(int kind, int dev, uint8_t reg, uint8_t *data, uint16_t n)
{
  (void)dev;
  switch (kind)
  {
    case DEVK_TEST: for (uint16_t i = 0; i < n; i++) data[i] = (uint8_t)(reg + i); return 0;
    default: return -1;
  }
}

void model_reset(int kind, int dev)
{
  if (kind == DEVK_TEST) memset(test_written[dev], 0, sizeof test_written[dev]);
  if (kind == DEVK_SHT45) sht45[dev] = (sht45_t){ .t_raw = 0x8000, .rh_raw = 0x8000 };
}
