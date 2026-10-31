#include "selftest.h"
#include <string.h>
#include "ws_frame.h"
#include "ws_obs.h"

/* Known-answer test (KAT) vectors of protocol version 6 (byte 0 = 0x61-0x63), shared with
 * tests/test_frame.py. They were made directly with the cryptography library's AESCCM from the
 * designed header and nonce, not by ws0/protocol.py. The version byte is authenticated (it is in the
 * AAD), so a version change changes every tag: regenerate the three arrays with
 * `.venv/bin/python -m tests.test_frame --kat` (selftest_frames, the one source) and paste them here. */
static const uint8_t KAT_KEY[WS_KEY_LEN] = { 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15 };
/* Observation: the encoder's own known answer (the KAT record of tests/test_obs.py: T -12.34 C,
 * RH 45.67 %, epoch 1, seq 2, UTC 1791991189, uptime 300 s, NORMAL), sealed with counter 0x100000002. Raw bytes, not hex
 * text (no decoder needed); tests/test_frame.py reads these three arrays back from this file. */
static const uint8_t KAT_OBS[] = {
  0x61, 0x00, 0x01, 0x01, 0x00, 0x00, 0x00, 0x02, 0xbd, 0x50, 0xc6, 0xbe, 0x34, 0x00, 0xa7, 0x50, 0xd4, 0x0c, 0xca, 0x5a, 0xad,
  0xad, 0x57, 0xb7, 0x16, 0xf1, 0x66, 0x58, 0xa0, 0x9d, 0x96, 0x8a, 0xcf, 0x9a, 0x57, 0xff, 0x27, 0xdb, 0x21, 0x80, 0x53, 0x90 };
static const uint8_t KAT_ACK[] = {
  0x62, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x05, 0x0e, 0x1e, 0xb4, 0x54, 0x47, 0x66, 0xf4, 0xe6, 0xe0,
  0xff, 0xdb, 0xb3, 0xf6, 0xd1, 0x41, 0x3d, 0x06, 0x74, 0x08, 0x2e, 0x29, 0xb9, 0x21, 0xfd, 0xdd };
static const uint8_t KAT_NACK[] = {
  0x63, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x06, 0x84, 0x9a, 0xdd, 0xbf, 0x88, 0xd9, 0xaa, 0xdd, 0x88,
  0x4a, 0xa3, 0xbb, 0x89, 0x13, 0x65, 0x75, 0x37, 0x88, 0xe8, 0xb4, 0xe4, 0xaa, 0x83, 0xce, 0xfb };
#define KAT_OBS_PLAIN_LEN WS_OBS_PLAIN_LEN(WS_F_TEMPERATURE_C | WS_F_HUMIDITY_PCT)
#define KAT_OBS_FRAME_LEN (KAT_OBS_PLAIN_LEN + WS_FRAME_OVERHEAD)
_Static_assert(sizeof KAT_OBS == KAT_OBS_FRAME_LEN && sizeof KAT_ACK == WS_ACK_FRAME_LEN && sizeof KAT_NACK == WS_ACK_FRAME_LEN,
               "known-answer vectors have their frame lengths");
#define KAT_COUNTER 0x100000002ULL

/* The observation: encoded and sealed it must be KAT_OBS byte for byte. The counter limit is part
   of the self-test too: 2^40 must be refused, never truncated. */
static int obs_ok(void)
{
  uint8_t plain[KAT_OBS_PLAIN_LEN], frame[KAT_OBS_FRAME_LEN];
  ws_obs_t o = { .epoch = 1, .seq = 2, .utc = 1791991189UL, .uptime = 300, .energy = WS_ENERGY_NORMAL,
                 .bitmap = WS_F_TEMPERATURE_C | WS_F_HUMIDITY_PCT };
  o.code[WS_FI_TEMPERATURE_C] = ws_code_temp_centi(-1234);
  o.code[WS_FI_HUMIDITY_PCT] = ws_code_rh_centi(4567);
  if (ws_obs_encode(&o, plain, sizeof plain) != (int)sizeof plain) return 0;
  if (ws_seal_kind(KAT_KEY, 1, WS_KIND_OBS, KAT_COUNTER, plain, sizeof plain, frame, sizeof frame) != KAT_OBS_FRAME_LEN ||
      memcmp(frame, KAT_OBS, sizeof frame)) return 0;
  return ws_seal_kind(KAT_KEY, 1, WS_KIND_OBS, WS_COUNTER_MAX + 1ULL, plain, sizeof plain, frame, sizeof frame) < 0;
}

/* A reply vector, optionally with its tag changed, and what opening it must give. */
typedef struct {
  const uint8_t *frame;
  uint8_t tamper;       /* XORed into the last tag byte */
  uint8_t opens;        /* 0: ws_open_reply must refuse it */
  uint8_t kind;
  uint64_t counter, echo;
  uint32_t epoch, seq, word;
} kat_reply;
static const kat_reply replies[] = {
  { KAT_ACK, 0, 1, WS_KIND_ACK, 5, KAT_COUNTER, 17, 42, 1760000000UL },
  { KAT_ACK, 1, 0, 0, 0, 0, 0, 0, 0 },                                     /* a tampered tag must fail */
  { KAT_NACK, 0, 1, WS_KIND_NACK, 6, KAT_COUNTER, 17, 42, WS_NACK_COLLISION },
};

static int reply_ok(const kat_reply *v)
{
  uint8_t frame[WS_ACK_FRAME_LEN], kind; uint64_t ctr, echo; uint32_t ep, sq, word;
  memcpy(frame, v->frame, sizeof frame);
  frame[sizeof frame - 1] ^= v->tamper;
  int opened = ws_open_reply(KAT_KEY, 1, frame, sizeof frame, &kind, &ctr, &ep, &sq, &word, &echo) == 0;
  if (!opened || !v->opens) return opened == v->opens;
  return kind == v->kind && ctr == v->counter && ep == v->epoch && sq == v->seq && word == v->word && echo == v->echo;
}

int selftest_kat(void)
{
  if (!obs_ok()) return 0;
  for (unsigned i = 0; i < sizeof replies / sizeof replies[0]; i++)
    if (!reply_ok(&replies[i])) return 0;
  return 1;
}
