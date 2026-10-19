/* The SHT45 and SHTC3 modules (mod_th.h). One step a tick:
 *   SHT45: command 0xFD, then on a later tick read 6 bytes.
 *   SHTC3: wake 0x3517, then measure 0x7866, then read 6 bytes, then sleep 0xB098.
 * The sensors keep their result until it is read, so a read one tick (250 ms) later is valid. A
 * result goes into the window that is open when it arrives, so a sample that straddles a latch counts
 * once, in the new window. The probe result is the outcome of the last sample: an address NACK means
 * absent, any other failure is a bus fault (WSMP-P1, WSMP-P3). */
#define WS_CHECK_FILE 13
#include "mod_th.h"
#include <string.h>
#include "i2c_bus.h"
#include "mod_mean.h"
#include "stage0.h"
#include "ws_check.h"
#include "ws_obs.h"   /* WS_TEMP_MIN_CENTI, WS_TEMP_MAX_CENTI, WS_RH_MAX_CENTI */
#include "wsmp_local.h"

#define SHTC3_ADDR 0x70U
#define TH_REPLY_LEN 6U
#define TH_CMD_LEN 2U
#define TH_WORD_LEN 2U
#define SHTC3_T_SPAN_CENTI 17500
#define SHTC3_T_OFFSET_CENTI (-4500)
#define SHTC3_RH_SPAN_CENTI 10000
#define SHTC3_ROUND (1UL << 15)
#define SHTC3_SHIFT 16U

typedef enum { ST_IDLE, ST_WAKE, ST_AWAKE, ST_MEASURE, ST_READY, ST_READ, ST_SLEEP } th_step;
typedef struct {
  th_step step;
  uint32_t next_sample_ms;
  mean_win win;
  int probe;
  uint16_t probe_seq;
  uint8_t reply[TH_REPLY_LEN];
} th_t;

static th_t th[TH_COUNT];
static uint32_t boot;
static const uint8_t sht45_measure[1] = { WS_SHT45_MEASURE };
static const uint8_t shtc3_wake[TH_CMD_LEN] = { 0x35, 0x17 };
static const uint8_t shtc3_measure[TH_CMD_LEN] = { 0x78, 0x66 };
static const uint8_t shtc3_sleep[TH_CMD_LEN] = { 0xB0, 0x98 };

static enum i2c_client client(enum th_unit u) { return u == TH_AIR ? I2C_C_SHT45 : I2C_C_SHTC3; }
static uint8_t addr(enum th_unit u) { return u == TH_AIR ? WS_SHT45_ADDR : SHTC3_ADDR; }
static uint16_t type(enum th_unit u) { return u == TH_AIR ? WSMP_T_AIR_TH : WSMP_T_ENCL_TH; }
static enum wsmp_port port(enum th_unit u) { return u == TH_AIR ? P_AIR_TH : P_ENCL_TH; }

static void submit(enum th_unit u, const uint8_t *tx, uint8_t txlen, uint8_t *rx, uint8_t rxlen)
{
  /* The bus refuses only a busy client or a bad form; one step at a time makes neither. */
  (void)WS_CHECK(i2c_bus_submit(client(u), addr(u), tx, txlen, rx, rxlen) == 0);
}

void mod_th_init(uint32_t boot_id)
{
  boot = boot_id;
  memset(th, 0, sizeof th);
}

/* The next step of the sample in progress, or the start of the next sample when it is due. */
void mod_th_tick(enum th_unit u, uint32_t now_ms)
{
  th_t *s = &th[u];
  if (s->step == ST_AWAKE) { s->step = ST_MEASURE; submit(u, shtc3_measure, TH_CMD_LEN, NULL, 0); return; }
  if (s->step == ST_READY) { s->step = ST_READ; submit(u, NULL, 0, s->reply, TH_REPLY_LEN); return; }
  if (s->step != ST_IDLE || (int32_t)(now_ms - s->next_sample_ms) < 0) return;
  s->next_sample_ms += WSMP_SAMPLE_MS;
  if ((int32_t)(now_ms - s->next_sample_ms) >= 0) s->next_sample_ms = now_ms + WSMP_SAMPLE_MS;   /* fell behind: resync */
  if (u == TH_AIR) { s->step = ST_MEASURE; submit(u, sht45_measure, sizeof sht45_measure, NULL, 0); }
  else { s->step = ST_WAKE; submit(u, shtc3_wake, TH_CMD_LEN, NULL, 0); }
}

static void probe(th_t *s, int result)
{
  s->probe = result;
  s->probe_seq++;
}

static void sample_failed(th_t *s, int rc)
{
  probe(s, rc == I2C_ENACK_ADDR ? 0 : -1);
  s->step = ST_IDLE;
}

static void read_done(enum th_unit u, th_t *s)
{
  int16_t t = 0; uint16_t h = 0;
  int rc = u == TH_AIR ? ws_sht45_parse(s->reply, &t, &h) : mod_shtc3_parse(s->reply, &t, &h);
  if (rc) { sample_failed(s, rc); return; }
  if (h > WS_RH_MAX_CENTI) h = WS_RH_MAX_CENTI;
  if (t >= WS_TEMP_MIN_CENTI && t <= WS_TEMP_MAX_CENTI) mean_add(&s->win, (const int32_t[MEAN_CHANNELS]){ t, h });
  probe(s, 1);
  if (u == TH_AIR) { s->step = ST_IDLE; return; }
  s->step = ST_SLEEP;
  submit(u, shtc3_sleep, TH_CMD_LEN, NULL, 0);
}

void mod_th_i2c_done(enum th_unit u, int rc)
{
  th_t *s = &th[u];
  if (s->step == ST_SLEEP) { s->step = ST_IDLE; return; }   /* a failed sleep command costs only power */
  if (rc) { sample_failed(s, rc); return; }
  if (s->step == ST_WAKE) s->step = ST_AWAKE;
  else if (s->step == ST_MEASURE) s->step = ST_READY;
  else if (WS_CHECK(s->step == ST_READ)) read_done(u, s);
}

int mod_th_probe(enum th_unit u, uint16_t *seq)
{
  *seq = th[u].probe_seq;
  return th[u].probe;
}

int mod_shtc3_parse(const uint8_t reply[6], int16_t *centi_c, uint16_t *centi_rh)
{
  if (ws_crc8(reply, TH_WORD_LEN) != reply[2] || ws_crc8(reply + 3, TH_WORD_LEN) != reply[5]) return I2C_ECRC;
  uint32_t t_raw = (uint32_t)reply[0] << 8 | reply[1], h_raw = (uint32_t)reply[3] << 8 | reply[4];
  *centi_c = (int16_t)((int32_t)((SHTC3_T_SPAN_CENTI * t_raw + SHTC3_ROUND) >> SHTC3_SHIFT) + SHTC3_T_OFFSET_CENTI);
  *centi_rh = (uint16_t)((SHTC3_RH_SPAN_CENTI * h_raw + SHTC3_ROUND) >> SHTC3_SHIFT);
  return 0;
}

static void descriptors(wsmp_desc d[2])
{
  d[0] = (wsmp_desc){ .quantity = WSMP_Q_AIR_TEMPERATURE, .unit = WSMP_U_CEL, .scale = -2, .width = 2, .is_signed = 1, .kind = WSMP_K_MEAN };
  d[1] = (wsmp_desc){ .quantity = WSMP_Q_RELATIVE_HUMIDITY, .unit = WSMP_U_PERCENT, .scale = -2, .width = 2, .is_signed = 0, .kind = WSMP_K_MEAN };
}

void mod_th_identity(enum th_unit u, uint8_t id[WSMP_IDENTITY_LEN], uint8_t desc[WSMP_DESC_BLOCK_LEN])
{
  wsmp_desc d[2];
  descriptors(d);
  wsmp_pack_desc(d, 2, desc);
  wsmp_identity ident = { .type = type(u), .schema = 1, .channels = 2, .fw_major = 1, .fw_minor = 0,
                          .serial = WSMP_LOCAL_SERIAL(port(u), type(u)), .boot_id = boot,
                          .desc_digest = wsmp_crc32c(desc, WSMP_DESC_BLOCK_LEN) };
  wsmp_pack_identity(&ident, id);
}

void mod_th_latch(enum th_unit u, uint16_t token, uint32_t now_ms)
{
  uint8_t id[WSMP_IDENTITY_LEN], desc[WSMP_DESC_BLOCK_LEN];
  mod_th_identity(u, id, desc);
  mean_latch(&th[u].win, token, now_ms, boot, desc, 2);
}

void mod_th_snapshot(enum th_unit u, uint8_t snap[WSMP_SNAPSHOT_LEN]) { memcpy(snap, th[u].win.frozen, WSMP_SNAPSHOT_LEN); }
