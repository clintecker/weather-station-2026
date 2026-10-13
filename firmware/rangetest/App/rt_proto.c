/* Bench range test protocol; see rt_proto.h. */
#include "rt_proto.h"

#include <string.h>

/* Ladders cycled by the buttons, most robust first. Index 0 is the boot and fallback setting, so
 * boards that lose each other meet again at the longest reach; the buttons step down toward
 * cheaper settings and wrap back to the top. +22 dBm is the board maximum; FCC 15.247(a)(2)
 * allows up to +30 dBm conducted at 500 kHz. */
static const uint8_t SF_LADDER[]  = { 12, 10, 9, 7 };
static const int8_t  PWR_LADDER[] = { 22, 14, 10, 0 };
#define LADDER_LEN 4

static uint8_t pack_cfg(rt_cfg_t c) { return (uint8_t)((c.sf << 4) | c.pwr); }

static int unpack_cfg(uint8_t b, rt_cfg_t *c)
{
  c->sf = b >> 4;
  c->pwr = b & 0x0F;
  return c->sf < LADDER_LEN && c->pwr < LADDER_LEN;
}

static int same(rt_cfg_t a, rt_cfg_t b) { return a.sf == b.sf && a.pwr == b.pwr; }

size_t rt_state_size(void) { return sizeof(rt_state_t); }

void rt_init(rt_state_t *st)
{
  memset(st, 0, sizeof *st);
  st->fresh = 1;
}

static void propose(rt_state_t *st, int sf_step, int pwr_step)
{
  rt_cfg_t base = st->has_prop ? st->prop : st->cur;
  base.sf = (uint8_t)((base.sf + sf_step) % LADDER_LEN);
  base.pwr = (uint8_t)((base.pwr + pwr_step) % LADDER_LEN);
  st->prop = base;
  st->has_prop = 1;
  st->gen = (uint8_t)(st->gen == 255 ? 1 : st->gen + 1);
}

void rt_press_sf(rt_state_t *st) { propose(st, 1, 0); }
void rt_press_pwr(rt_state_t *st) { propose(st, 0, 1); }

size_t rt_build(rt_state_t *st, uint8_t type, uint16_t seq, int16_t peer_rssi, int8_t peer_snr,
                uint8_t *out)
{
  memset(out, 0, RT_PKT_LEN);
  out[0] = 'R';
  out[1] = 'T';
  out[2] = RT_VERSION;
  out[3] = type;
  out[4] = pack_cfg(st->cur);
  if (st->has_prop)
  {
    out[5] = st->gen;
    out[6] = pack_cfg(st->prop);
  }
  out[7] = st->ack_gen;
  st->ack_in_flight = st->ack_gen != 0;
  out[8] = (uint8_t)seq;
  out[9] = (uint8_t)(seq >> 8);
  out[10] = (uint8_t)peer_rssi;
  out[11] = (uint8_t)((uint16_t)peer_rssi >> 8);
  out[12] = (uint8_t)peer_snr;
  return RT_PKT_LEN;
}

static void switch_to(rt_state_t *st, rt_cfg_t next)
{
  st->prev = st->cur;
  st->cur = next;
  st->tentative = 1;
  st->misses = 0;
}

int rt_on_rx(rt_state_t *st, const uint8_t *buf, size_t len, rt_rx_t *info)
{
  rt_cfg_t cfg, prop;
  int ev = 0;

  if (len < RT_PKT_LEN || buf[0] != 'R' || buf[1] != 'T' || buf[2] != RT_VERSION || buf[3] > RT_PONG
      || !unpack_cfg(buf[4], &cfg))
    return -1;

  st->lost = 0;

  /* First packet since boot or fallback: take the peer's settings, so a restart of one board
     never leaves the two at different power. (Same SF is implied: I heard it.) */
  if (st->fresh)
  {
    st->fresh = 0;
    if (!same(cfg, st->cur))
    {
      st->cur = st->prev = cfg;
      st->tentative = 0;
      ev |= RT_EV_ADOPTED;
    }
  }

  /* Hearing anything means the current settings work. */
  if (st->tentative)
  {
    st->tentative = 0;
    st->misses = 0;
    ev |= RT_EV_COMMIT;
  }

  /* Peer agreed to my proposal: switch now; my next packet goes out with the new settings. */
  if (st->has_prop && buf[7] == st->gen)
  {
    st->has_prop = 0;
    if (!same(st->prop, st->cur))
    {
      switch_to(st, st->prop);
      ev |= RT_EV_SWITCHED;
    }
  }

  /* Peer proposes: ack in my next packet, switch after it is sent. A peer proposal wins over
     my own unacknowledged one (both boards pressing at once is a bench mistake, not a mode). */
  if (buf[5] != 0 && unpack_cfg(buf[6], &prop))
  {
    st->ack_gen = buf[5];
    st->staged = prop;
    st->has_prop = 0;
  }
  else
  {
    st->ack_gen = 0;
  }

  if (info)
  {
    info->type = buf[3];
    info->cfg = cfg;
    info->seq = (uint16_t)(buf[8] | (buf[9] << 8));
    info->peer_rssi = (int16_t)(buf[10] | (buf[11] << 8));
    info->peer_snr = (int8_t)buf[12];
  }
  return ev;
}

int rt_on_tx_done(rt_state_t *st)
{
  if (!st->ack_in_flight)
    return 0;
  st->ack_in_flight = 0;
  st->ack_gen = 0;
  if (same(st->staged, st->cur))
    return 0;
  switch_to(st, st->staged);
  return RT_EV_SWITCHED;
}

int rt_on_miss(rt_state_t *st)
{
  static const rt_cfg_t defaults = { 0, 0 };

  if (!st->tentative)
  {
    if (++st->lost < RT_LOST_MISSES)
      return 0;
    st->lost = 0;
    st->has_prop = 0;
    st->ack_gen = 0;
    st->fresh = 1;
    if (same(st->cur, defaults))
      return 0;
    st->cur = st->prev = defaults;
    return RT_EV_FALLBACK;
  }
  if (++st->misses < RT_ROLLBACK_MISSES)
    return 0;
  st->cur = st->prev;
  st->tentative = 0;
  st->misses = 0;
  return RT_EV_ROLLBACK;
}

int rt_sf_of(rt_cfg_t c) { return SF_LADDER[c.sf]; }
int rt_pwr_of(rt_cfg_t c) { return PWR_LADDER[c.pwr]; }
int rt_cur_sf(const rt_state_t *st) { return rt_sf_of(st->cur); }
int rt_cur_pwr(const rt_state_t *st) { return rt_pwr_of(st->cur); }
int rt_is_tentative(const rt_state_t *st) { return st->tentative; }
int rt_info_sf(const rt_rx_t *info) { return rt_sf_of(info->cfg); }
int rt_info_pwr(const rt_rx_t *info) { return rt_pwr_of(info->cfg); }
