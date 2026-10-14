/* Bench range test: 16-byte packet and the two-board settings handshake.
 *
 * Pure C with no HAL dependency, so tests/test_rangetest.py runs it on the host.
 *
 * A board proposes new settings (SF or TX power) inside its next packet, still sent with the
 * current settings. The peer answers with an ack, also with the current settings, and switches
 * once that ack has left its antenna. The proposer switches when it hears the ack. Both are then
 * "tentative": the first packet heard with the new settings commits them. If a board hears
 * nothing for RT_ROLLBACK_MISSES receive windows while tentative, it returns to the previous
 * settings, where the other board still is (lost ack) or will also return (lost link).
 *
 * Restarts: a board boots at the defaults and adopts the settings of the first packet it hears,
 * so restarting one board does not leave the two at different power. If a board hears nothing
 * for RT_LOST_MISSES receive windows (about 30 s), it returns to the defaults; the other board
 * does the same, so the two always find each other again at the most robust setting,
 * SF12 / +22 dBm, which is also the boot setting.
 *
 * Packet: 'R' 'T' version type cfg prop_gen prop_cfg ack_gen seq[2] peer_rssi[2] peer_snr pad[3]
 * cfg bytes are (sf_index << 4) | power_index. Generation 0 means "none". Little-endian.
 */
#ifndef RT_PROTO_H
#define RT_PROTO_H

#include <stddef.h>
#include <stdint.h>

#define RT_PKT_LEN          16
#define RT_VERSION          1
#define RT_ROLLBACK_MISSES  5
#define RT_LOST_MISSES      10
#define RT_NO_RSSI          (-32768)

enum { RT_PING = 0, RT_PONG = 1 };
enum { RT_EV_SWITCHED = 1, RT_EV_COMMIT = 2, RT_EV_ROLLBACK = 4, RT_EV_ADOPTED = 8, RT_EV_FALLBACK = 16 };

typedef struct { uint8_t sf, pwr; } rt_cfg_t;   /* indexes into the ladders below */

typedef struct {
  rt_cfg_t cur, prev;
  uint8_t  tentative, misses;
  uint8_t  fresh;               /* booted (or fell back) and not yet heard the peer */
  uint8_t  lost;                /* consecutive misses while not tentative */
  uint8_t  gen, has_prop;       /* my proposal */
  rt_cfg_t prop;
  uint8_t  ack_gen;             /* peer proposal I owe an ack for (0 = none) */
  rt_cfg_t staged;
  uint8_t  ack_in_flight;       /* last packet built carried that ack */
} rt_state_t;

typedef struct {
  uint8_t  type;
  rt_cfg_t cfg;                 /* sender's settings when it sent */
  uint16_t seq;
  int16_t  peer_rssi;           /* what the sender measured on my last packet */
  int8_t   peer_snr;
} rt_rx_t;

size_t rt_state_size(void);
void   rt_init(rt_state_t *st);
void   rt_press_sf(rt_state_t *st);
void   rt_press_pwr(rt_state_t *st);
size_t rt_build(rt_state_t *st, uint8_t type, uint16_t seq, int16_t peer_rssi, int8_t peer_snr,
                uint8_t *out);
int    rt_on_rx(rt_state_t *st, const uint8_t *buf, size_t len, rt_rx_t *info);  /* -1: not ours */
int    rt_on_tx_done(rt_state_t *st);
int    rt_on_miss(rt_state_t *st);

int    rt_sf_of(rt_cfg_t c);    /* spreading factor, e.g. 7 */
int    rt_pwr_of(rt_cfg_t c);   /* dBm */
/* Settings one event in a returned event set refers to. rt_on_rx can report COMMIT (or ADOPTED)
   and SWITCHED together: the commit was of the settings in force before the switch. */
rt_cfg_t rt_event_cfg(const rt_state_t *st, int events, int event);
int    rt_cur_sf(const rt_state_t *st);
int    rt_cur_pwr(const rt_state_t *st);
int    rt_is_tentative(const rt_state_t *st);
int    rt_info_sf(const rt_rx_t *info);    /* sender's settings */
int    rt_info_pwr(const rt_rx_t *info);

#endif /* RT_PROTO_H */
