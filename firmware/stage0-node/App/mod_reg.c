/* The BMP581 and LTR390 modules (mod_reg.h).
 *   BMP581 (datasheet sections 4.3 and 5): CHIP_ID 0x01 = 0x50. OSR_CONFIG 0x36 = 0x40 (pressure on,
 *   oversampling 1x), then ODR_CONFIG 0x37 = 0x82 (deep standby off, forced mode: one measurement).
 *   PRESS_DATA 0x20-0x22, little-endian, Pa x 64. The value is 0.1 hPa: raw / 640, rounded half up.
 *   LTR390 (datasheet section 7): PART_ID 0x06, high nibble 0xB (the part number; the low nibble is
 *   the revision, not compared). MAIN_CTRL 0x00 = 0x0A (UVS mode, enabled),
 *   18-bit, 100 ms by default. UVS_DATA 0x10-0x12, little-endian, 20 bits of counts.
 * A read one tick (250 ms) after the configuration is past both parts' measurement time. Both are port
 * modules: each sample is calibrated, then cropped and range-checked (sensor module ports design,
 * section 6.9). */
#define WS_CHECK_FILE 15
#include "mod_reg.h"
#include <string.h>
#include "i2c_bus.h"
#include "mod_mean.h"
#include "ws_check.h"
#include "wsmp_cal.h"
#include "wsmp_local.h"

#define REG_WRITE_LEN 2U
#define DATA_LEN 3U
#define MAX_WRITES 2U
#define BYTE_BITS 8U
#define BMP581_PA64_PER_DECI_HPA 640U   /* 64 counts a Pa, 10 Pa a 0.1 hPa */
#define LTR390_COUNT_MASK 0xFFFFFUL     /* 20 bits */

typedef struct {
  enum i2c_client client; uint8_t addr, id_reg, id, id_mask, data_reg, writes;
  uint8_t write[MAX_WRITES][REG_WRITE_LEN];
  uint16_t type; enum wsmp_port port; wsmp_desc desc;
} reg_part;

static const reg_part parts[REG_COUNT] = {
  { I2C_C_BMP581, 0x47, 0x01, 0x50, 0xFF, 0x20, 2, { { 0x36, 0x40 }, { 0x37, 0x82 } }, WSMP_T_PRESSURE, P_PRESSURE,
    { .quantity = WSMP_Q_STATION_PRESSURE, .unit = WSMP_U_HPA, .scale = -1, .width = 2, .is_signed = 0, .kind = WSMP_K_MEAN } },
  { I2C_C_LTR390, 0x53, 0x06, 0xB0, 0xF0, 0x10, 1, { { 0x00, 0x0A } }, WSMP_T_UVA, P_UVA,
    { .quantity = WSMP_Q_UVA_COUNTS, .unit = WSMP_U_COUNT, .scale = 0, .width = 3, .is_signed = 0, .kind = WSMP_K_MEAN } },
};

typedef enum { ST_IDLE, ST_ID, ST_CONFIG, ST_READY, ST_DATA } reg_step;
typedef struct {
  reg_step step;
  uint8_t next_write, id, data[DATA_LEN];
  uint32_t next_sample_ms;
  int probe;
  uint16_t probe_seq;
  mean_win win;
  uint8_t calibrated;   /* cal applies to the channel */
  wsmp_cal_entry cal;
} reg_t;

static reg_t reg[REG_COUNT];
static uint32_t boot;

static void submit(enum reg_unit u, const uint8_t *tx, uint8_t txlen, uint8_t *rx, uint8_t rxlen)
{
  /* The bus refuses only a busy client or a bad form; one step at a time makes neither. */
  (void)WS_CHECK(i2c_bus_submit(parts[u].client, parts[u].addr, tx, txlen, rx, rxlen) == 0);
}

void mod_reg_init(uint32_t boot_id, uint32_t now_ms)
{
  boot = boot_id;
  memset(reg, 0, sizeof reg);
  for (unsigned u = 0; u < REG_COUNT; u++) { mean_reset(&reg[u].win, now_ms); reg[u].next_sample_ms = now_ms; }
}

void mod_reg_tick(enum reg_unit u, uint32_t now_ms)
{
  reg_t *s = &reg[u];
  if (s->step == ST_READY) { s->step = ST_DATA; submit(u, &parts[u].data_reg, 1, s->data, DATA_LEN); return; }
  if (s->step != ST_IDLE || !mean_due(&s->next_sample_ms, now_ms, WSMP_SAMPLE_MS)) return;
  s->step = ST_ID;
  submit(u, &parts[u].id_reg, 1, &s->id, 1);
}

static void probe(reg_t *s, int result)
{
  s->probe = result;
  s->probe_seq++;
  s->step = ST_IDLE;
}

/* The sample's value in the descriptor's units, from the little-endian data registers. */
static int32_t value(enum reg_unit u, const uint8_t d[DATA_LEN])
{
  uint32_t raw = (uint32_t)d[0] | (uint32_t)d[1] << BYTE_BITS | (uint32_t)d[2] << (2U * BYTE_BITS);
  if (u == REG_UVA) return (int32_t)(raw & LTR390_COUNT_MASK);
  return (int32_t)((raw + BMP581_PA64_PER_DECI_HPA / 2U) / BMP581_PA64_PER_DECI_HPA);
}

static void config_next(enum reg_unit u, reg_t *s)
{
  if (s->next_write == parts[u].writes) { s->step = ST_READY; return; }
  s->step = ST_CONFIG;
  submit(u, parts[u].write[s->next_write++], REG_WRITE_LEN, NULL, 0);
}

void mod_reg_i2c_done(enum reg_unit u, int rc)
{
  reg_t *s = &reg[u];
  if (rc) { probe(s, rc == I2C_ENACK_ADDR ? 0 : -1); return; }
  if (s->step == ST_ID)
  {
    if ((s->id & parts[u].id_mask) != parts[u].id) { probe(s, 0); return; }   /* another chip here: not this module */
    s->next_write = 0;
    config_next(u, s);
  }
  else if (s->step == ST_CONFIG) config_next(u, s);
  else if (WS_CHECK(s->step == ST_DATA))
  {
    int32_t v[MEAN_CHANNELS] = { 0, 0 };
    uint8_t q[MEAN_CHANNELS] = { WSMP_QUAL_GOOD, WSMP_QUAL_GOOD };
    q[0] = wsmp_cal_crop(parts[u].desc.quantity, wsmp_cal_apply(s->calibrated ? &s->cal : NULL, value(u, s->data)), &v[0]);
    mean_add_q(&s->win, v, q);
    probe(s, 1);
  }
}

void mod_reg_bind(enum reg_unit u, const wsmp_record *applied, uint32_t now_ms)
{
  reg_t *s = &reg[u];
  const wsmp_cal_entry *e = applied ? wsmp_cal_find(applied, parts[u].desc.quantity, parts[u].desc.kind) : NULL;
  mean_reset(&s->win, now_ms);
  s->calibrated = e != NULL;
  s->cal = e ? *e : (wsmp_cal_entry){ 0 };
}

int mod_reg_probe(enum reg_unit u, uint16_t *seq)
{
  *seq = reg[u].probe_seq;
  return reg[u].probe;
}

void mod_reg_identity(enum reg_unit u, uint8_t id[WSMP_IDENTITY_LEN], uint8_t desc[WSMP_DESC_BLOCK_LEN])
{
  wsmp_pack_desc(&parts[u].desc, 1, desc);
  local_pack_identity(parts[u].port, parts[u].type, 1, boot, desc, id);
}

void mod_reg_latch(enum reg_unit u, uint16_t token, uint32_t now_ms)
{
  uint8_t desc[WSMP_DESC_BLOCK_LEN];
  wsmp_pack_desc(&parts[u].desc, 1, desc);
  mean_latch(&reg[u].win, token, now_ms, boot, desc, 1);
}

void mod_reg_snapshot(enum reg_unit u, uint8_t snap[WSMP_SNAPSHOT_LEN]) { memcpy(snap, reg[u].win.frozen, WSMP_SNAPSHOT_LEN); }
