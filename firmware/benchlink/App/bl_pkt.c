#include "bl_pkt.h"

#define CRC16_INIT 0xFFFFU
#define CRC16_POLY 0x1021U
#define CRC8_INIT 0xFFU
#define CRC8_POLY 0x31U
#define BYTE_BITS 8U
#define TOP16 0x8000U
#define TOP8 0x80U
#define SHT_FULL 65535
#define SHT_T_SPAN_MC 175000
#define SHT_T_OFFSET_MC (-45000)
#define SHT_RH_SPAN_MPCT 125000
#define SHT_RH_OFFSET_MPCT (-6000)
#define RH_MAX_MPCT 100000
#define CRC_AT 76U
#define BODY_AT 4U

uint16_t bl_crc16(const uint8_t *p, unsigned n)
{
  uint16_t crc = CRC16_INIT;
  for (unsigned i = 0; i < n; i++)
  {
    crc = (uint16_t)(crc ^ (uint16_t)(p[i] << BYTE_BITS));
    for (unsigned b = 0; b < BYTE_BITS; b++)
      crc = (crc & TOP16) ? (uint16_t)((crc << 1) ^ CRC16_POLY) : (uint16_t)(crc << 1);
  }
  return crc;
}

uint8_t sht45_crc8(const uint8_t *p, unsigned n)
{
  uint8_t crc = CRC8_INIT;
  for (unsigned i = 0; i < n; i++)
  {
    crc ^= p[i];
    for (unsigned b = 0; b < BYTE_BITS; b++)
      crc = (crc & TOP8) ? (uint8_t)((crc << 1) ^ CRC8_POLY) : (uint8_t)(crc << 1);
  }
  return crc;
}

int32_t sht45_t_mc(uint16_t raw)
{
  return SHT_T_OFFSET_MC + (int32_t)(((int64_t)SHT_T_SPAN_MC * raw) / SHT_FULL);
}

int32_t sht45_rh_mpct(uint16_t raw)
{
  int32_t rh = SHT_RH_OFFSET_MPCT + (int32_t)(((int64_t)SHT_RH_SPAN_MPCT * raw) / SHT_FULL);
  return rh < 0 ? 0 : rh > RH_MAX_MPCT ? RH_MAX_MPCT : rh;
}

static void put16(uint8_t *o, uint16_t v)
{
  o[0] = (uint8_t)v;
  o[1] = (uint8_t)(v >> BYTE_BITS);
}

static uint16_t get16(const uint8_t *in) { return (uint16_t)(in[0] | (in[1] << BYTE_BITS)); }

static void put32(uint8_t *o, uint32_t v)
{
  for (unsigned i = 0; i < 4U; i++) o[i] = (uint8_t)(v >> (BYTE_BITS * i));
}

static uint32_t get32(const uint8_t *in)
{
  uint32_t v = 0;
  for (unsigned i = 0; i < 4U; i++) v |= (uint32_t)in[i] << (BYTE_BITS * i);
  return v;
}

/* The twelve i32 fields from offset 12, in packet order. */
static int32_t *field(bl_reading *r, unsigned k)
{
  int32_t *const f[] = { &r->vout_uv, &r->ishunt_ua, &r->iset_uv, &r->iset_min_uv, &r->iset_max_uv,
                         &r->ina_die_mc, &r->vcell_uv, &r->soc_mpct, &r->crate_mpct_h, &r->sht_t_mc,
                         &r->sht_rh_mpct, &r->vin_uv };
  return f[k];
}

#define NFIELDS 12U
#define FIELDS_AT 12U
#define SAMPLES_AT 60U
enum { RESET_AT = 62, FAULTS_AT, BOOTS_AT, TX_TIMEOUTS_AT = 66, I2C_RESTARTS_AT = 68, I2C_UNSTICKS_AT = 70,
       FAULT_PC_AT = 72 };

void bl_pack(const bl_reading *r, uint8_t out[BL_PKT_LEN])
{
  bl_reading c = *r;
  out[0] = 'W';
  out[1] = 'B';
  out[2] = (uint8_t)BL_VERSION;
  out[3] = c.flags;
  put32(out + BODY_AT, c.seq);
  put32(out + BODY_AT + 4U, c.uptime_s);
  for (unsigned k = 0; k < NFIELDS; k++) put32(out + FIELDS_AT + 4U * k, (uint32_t)*field(&c, k));
  out[SAMPLES_AT] = c.samples;
  out[SAMPLES_AT + 1U] = c.misses;
  out[RESET_AT] = c.reset_cause;
  out[FAULTS_AT] = c.faults;
  put16(out + BOOTS_AT, c.boots);
  put16(out + TX_TIMEOUTS_AT, c.tx_timeouts);
  put16(out + I2C_RESTARTS_AT, c.i2c_restarts);
  put16(out + I2C_UNSTICKS_AT, c.i2c_unsticks);
  put32(out + FAULT_PC_AT, c.fault_pc);
  put16(out + CRC_AT, bl_crc16(out, CRC_AT));
}

int bl_unpack(const uint8_t *in, unsigned n, bl_reading *r)
{
  if (n != BL_PKT_LEN || in[0] != 'W' || in[1] != 'B' || in[2] != BL_VERSION) return -1;
  if (get16(in + CRC_AT) != bl_crc16(in, CRC_AT)) return -1;
  r->flags = in[3];
  r->seq = get32(in + BODY_AT);
  r->uptime_s = get32(in + BODY_AT + 4U);
  for (unsigned k = 0; k < NFIELDS; k++) *field(r, k) = (int32_t)get32(in + FIELDS_AT + 4U * k);
  r->samples = in[SAMPLES_AT];
  r->misses = in[SAMPLES_AT + 1U];
  r->reset_cause = in[RESET_AT];
  r->faults = in[FAULTS_AT];
  r->boots = get16(in + BOOTS_AT);
  r->tx_timeouts = get16(in + TX_TIMEOUTS_AT);
  r->i2c_restarts = get16(in + I2C_RESTARTS_AT);
  r->i2c_unsticks = get16(in + I2C_UNSTICKS_AT);
  r->fault_pc = get32(in + FAULT_PC_AT);
  return 0;
}
