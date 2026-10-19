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

int model_write(int kind, int dev, const uint8_t *data, uint16_t n)
{
  switch (kind)
  {
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
    default: return -1;
  }
}

int model_mem_read(int kind, int dev, uint8_t reg, uint8_t *data, uint16_t n)
{
  switch (kind)
  {
    case DEVK_BMP581: case DEVK_LTR390: return reg_read(kind, dev, reg, data, n);
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
}
