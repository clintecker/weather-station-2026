/* GENERATED from wsmp_host.lit.md by tools/tangle.py: do not edit. Edit the document, then run
 * tools/tangle.py firmware/stage0-node/App/wsmp_host.lit.md (tests/test_tangle.py checks this file). */
#include "wsmp_host.h"
#include <string.h>
#include "port_id.h"

#ifndef WSMP_HOST_BUDGET
#define WSMP_HOST_BUDGET WSMP_RADIO_BUDGET   /* a test build can make it smaller */
#endif
#define GOOD_PROBES 2U
#define MISSED_LATCHES 3U
#define FLAP_CHANGES 5U                    /* the fifth join or leave within the hour quarantines */
#define FLAP_WINDOW_MS 3600000UL
#define QUARANTINE_MS 3600000UL
#define PROBE_ABSENT 0
#define PROBE_PRESENT 1
#define REMOVAL_PROBES 2U                  /* a refused or quarantined module: missed probes in a row */
#define HOLD_ROUNDS 2U                     /* the boot hold: probes of every port module */
#define HOLD_MAX_MS (3UL * WSMP_SAMPLE_MS) /* and at most this long, so a silent driver cannot hold it */
#define BOOT_SHIFT 8U                      /* the boot ID: epoch << 8 | admission count (section 6.7) */
#define COUNT_MASK 0xFFU
#define CAP_RECORD 1U                      /* identity capabilities bit 0: a valid record */
#define COUNT_MAX 255U                     /* the incomplete counter saturates */
#define DECIMAL 10U

typedef struct {
  uint8_t state, good, missed, timed;          /* timed: a flap quarantine that ends by itself */
  uint8_t values, channels, report_class;      /* the admitted module's share of the radio budget */
  int probe;
  uint16_t probe_seq;
  uint32_t quarantine_until, changes;
  uint32_t change_at[FLAP_CHANGES];            /* the times of the last joins and leaves */
  wsmp_snapshot snap;
  int have_snap;
  /* An I2C port module's identity (section 6.7): */
  uint8_t reason;                              /* the verdict behind Quarantined or Refused (WSMP_V_*) */
  uint8_t holder, checking;                    /* a duplicate's holder port, and its check running */
  uint8_t admissions, missed_probes, rounds;   /* rounds: probes since boot, for the boot hold */
  uint8_t with_record, has_sensor_serial;
  uint8_t id_wait, incomplete;                 /* an incomplete identification waits for the next probe; how many */
  uint64_t serial, rec_serial;
  uint32_t sensor_serial;
} port_t;

static port_t ports[P_COUNT];
static uint16_t token;
static uint8_t hold_over, hold_started;
static uint32_t hold_from;

void wsmp_host_init(void)
{
  memset(ports, 0, sizeof ports);
  token = 0;
  hold_over = hold_started = 0;
}

static int in_layout(const port_t *s)
{
  return s->state == WH_ADMITTED || s->state == WH_ACTIVE || s->state == WH_SUSPECT;
}

static int fits(enum wsmp_port p, unsigned values, unsigned channels)
{
  for (unsigned q = P_AIR_TH; q < P_COUNT; q++)
  {
    const port_t *s = &ports[q];
    if (q == (unsigned)p || !in_layout(s) || s->report_class != WSMP_RC_MINUTE) continue;
    values += s->values;
    channels += s->channels;
  }
  return values + wsmp_quality_bytes(channels) <= WSMP_HOST_BUDGET;
}

typedef struct { uint8_t values, channels, report_class; } share_t;   /* a module's part of the budget */

static int admission(enum wsmp_port p, const uint8_t id[WSMP_IDENTITY_LEN], const uint8_t desc[WSMP_DESC_BLOCK_LEN],
                     share_t *share)
{
  wsmp_identity ident;
  wsmp_desc d[WSMP_MAX_CHANNELS];
  if (wsmp_unpack_identity(id, &ident) != WSMP_OK || ident.desc_digest != wsmp_crc32c(desc, WSMP_DESC_BLOCK_LEN) ||
      wsmp_unpack_desc(desc, ident.channels, d) != WSMP_OK ||
      wsmp_desc_check(d, ident.channels, ident.type, ident.schema) != WSMP_OK)
    return WH_QUARANTINED;
  const wsmp_type_entry *type = wsmp_type(ident.type);
  if (!type) return WH_QUARANTINED;   /* wsmp_desc_check already found it; this keeps the pointer checked */
  *share = (share_t){ .values = (uint8_t)wsmp_values_bytes(d, ident.channels), .channels = ident.channels,
                      .report_class = type->report_class };
  if (share->report_class == WSMP_RC_MINUTE && !fits(p, share->values, share->channels)) return WH_REFUSED;
  return WH_ADMITTED;
}

int wsmp_host_admit(enum wsmp_port p, const uint8_t id[WSMP_IDENTITY_LEN], const uint8_t desc[WSMP_DESC_BLOCK_LEN])
{
  share_t share;
  return admission(p, id, desc, &share);
}

static int valid_record(uint8_t status)
{
  return status == WSMP_REC_APPLIED || status == WSMP_REC_CAL_REJECTED || status == WSMP_REC_SENSOR_CHANGED;
}

/* The modules in the layout, each with its serial and type, for wsmp_identify. */
static unsigned holders(wsmp_port_held held[P_COUNT])
{
  unsigned n = 0;
  for (unsigned q = P_AIR_TH; q < P_COUNT; q++)
  {
    const port_t *s = &ports[q];
    if (!in_layout(s)) continue;
    uint16_t type = local_type((enum wsmp_port)q);
    held[n++] = (wsmp_port_held){ .port = (uint8_t)q, .holding = 1, .type = type,
                                  .serial = port_id_is_port((enum wsmp_port)q) ? s->serial : WSMP_LOCAL_SERIAL(q, type) };
  }
  return n;
}

static void admit_verdict(enum wsmp_port p, port_t *s, const wsmp_observed *o, const wsmp_verdict *v, uint32_t now_ms)
{
  uint8_t id[WSMP_IDENTITY_LEN], desc[WSMP_DESC_BLOCK_LEN];
  share_t share;
  uint32_t boot_id = local_boot_epoch() << BOOT_SHIFT | ((s->admissions + 1U) & COUNT_MASK);
  local_set_identity(p, v->serial, v->id_flags, valid_record(v->status) ? (uint16_t)CAP_RECORD : 0U);
  local_identity(p, id, desc);
  s->state = (uint8_t)admission(p, id, desc, &share);
  s->reason = WSMP_V_ADMIT;
  s->timed = 0;
  if (s->state != WH_ADMITTED) return;
  s->values = share.values; s->channels = share.channels; s->report_class = share.report_class;
  s->admissions++;
  s->serial = v->serial;
  s->with_record = (uint8_t)valid_record(v->status);
  s->rec_serial = v->record.serial;
  s->has_sensor_serial = o->has_sensor_serial;
  s->sensor_serial = o->sensor_serial;
  local_bind(p, v->status == WSMP_REC_APPLIED ? &v->record : NULL, boot_id, now_ms);
}

/* A duplicate: the holder check on the holder's port, once its engine is free (else the next tick). */
static void duplicate(port_t *s, const wsmp_verdict *v)
{
  const port_t *h = &ports[v->holder_port];
  s->reason = v->verdict;
  s->holder = v->holder_port;
  if (!port_id_is_port((enum wsmp_port)v->holder_port)) { s->state = WH_REFUSED; return; }   /* on-board: present */
  if (port_id_state((enum wsmp_port)v->holder_port) != PORT_ID_DONE) return;
  const port_id_expect e = { .serial = h->rec_serial, .sensor_serial = h->sensor_serial, .with_record = h->with_record,
                             .has_sensor_serial = h->has_sensor_serial };
  port_id_holder((enum wsmp_port)v->holder_port, &e);
  s->checking = 1;
}

/* The verdict order. recheck: a latch's re-evaluation of a refusal, which starts no holder check. */
static void decide(enum wsmp_port p, port_t *s, int recheck, uint32_t now_ms)
{
  wsmp_observed o;
  wsmp_port_held held[P_COUNT];
  wsmp_verdict v;
  unsigned n = holders(held);   /* fills held before the call reads it */
  port_id_observed(p, &o);
  wsmp_identify(&o, held, n, &v);
  if (v.verdict == WSMP_V_ADMIT) { admit_verdict(p, s, &o, &v, now_ms); return; }
  if (recheck) return;
  if (v.verdict != WSMP_V_TYPE_CONFLICT) { duplicate(s, &v); return; }
  s->state = WH_QUARANTINED;
  s->reason = v.verdict;
  s->timed = 0;
  s->missed_probes = 0;
}

static void end_holder(port_t *h, uint32_t now_ms);

/* 1 while a lower port is still identifying: verdicts are decided in port order. A port waiting for
   its next probe after an incomplete identification does not count. */
static int lower_identifying(enum wsmp_port p)
{
  for (unsigned q = P_AIR_TH; q < (unsigned)p; q++)
    if (ports[q].state == WH_IDENTIFYING && !ports[q].id_wait) return 1;
  return 0;
}

static void identifying(enum wsmp_port p, port_t *s, int held, uint32_t now_ms)
{
  if (!s->checking)
  {
    if (s->id_wait || port_id_state(p) != PORT_ID_DONE) return;
    if (port_id_incomplete(p))   /* no verdict: identified again at the next probe */
    {
      s->id_wait = 1;
      if (s->incomplete < COUNT_MAX) s->incomplete++;
      return;
    }
    if (!held && !lower_identifying(p)) decide(p, s, 0, now_ms);
    return;
  }
  if (port_id_state((enum wsmp_port)s->holder) != PORT_ID_DONE) return;
  s->checking = 0;
  if (port_id_holder_result((enum wsmp_port)s->holder) == PORT_ID_PRESENT) { s->state = WH_REFUSED; s->missed_probes = 0; return; }
  end_holder(&ports[s->holder], now_ms);
  decide(p, s, 0, now_ms);
}

static void identify(enum wsmp_port p, port_t *s)
{
  uint8_t id[WSMP_IDENTITY_LEN], desc[WSMP_DESC_BLOCK_LEN];
  share_t share;
  local_identity(p, id, desc);
  s->state = (uint8_t)admission(p, id, desc, &share);
  if (s->state == WH_ADMITTED) { s->values = share.values; s->channels = share.channels; s->report_class = share.report_class; }
  s->timed = 0;
}

/* Absent and Probing: presence builds up, two good probes in a row. A port module is then identified
   across steps (section 4.1); an on-board module at once. */
static void on_probe_presence(enum wsmp_port p, port_t *s)
{
  if (s->probe != PROBE_PRESENT) { s->good = 0; s->state = WH_ABSENT; return; }
  if (s->state == WH_ABSENT) { s->good = 1; s->state = WH_PROBING; return; }
  if (++s->good < GOOD_PROBES) return;
  if (!port_id_is_port(p)) { identify(p, s); return; }
  s->state = WH_IDENTIFYING;
  s->checking = 0;
  port_id_identify(p);
}

/* Admitted, Refused and Quarantined: wait for a removal (or the end of a flap quarantine). A refused
   or quarantined module keeps probing: two missed probes in a row remove it (section 6.7). */
static void on_probe_waiting(port_t *s, uint32_t now_ms)
{
  int ended;
  s->missed_probes = s->probe == PROBE_ABSENT ? (uint8_t)(s->missed_probes + 1U) : 0U;
  if (s->state == WH_ADMITTED) ended = s->probe == PROBE_ABSENT;
  else if (s->state == WH_QUARANTINED && s->timed) ended = (int32_t)(now_ms - s->quarantine_until) >= 0;
  else ended = s->missed_probes >= REMOVAL_PROBES;
  if (!ended) return;
  s->state = WH_ABSENT;
  s->reason = WSMP_V_ADMIT;
  s->missed_probes = 0;
}

/* Identifying, after an incomplete identification (section 4.1): the next probe identifies again,
   unless it failed. */
static void on_probe_retry(enum wsmp_port p, port_t *s)
{
  s->id_wait = 0;
  if (s->probe != PROBE_PRESENT) { s->good = 0; s->state = WH_ABSENT; return; }
  port_id_identify(p);
}

static void on_probe(enum wsmp_port p, port_t *s, uint32_t now_ms)
{
  if (s->state == WH_ABSENT || s->state == WH_PROBING) on_probe_presence(p, s);
  else if (s->state == WH_IDENTIFYING && s->id_wait) on_probe_retry(p, s);
  else if (s->state == WH_ADMITTED || s->state == WH_REFUSED || s->state == WH_QUARANTINED) on_probe_waiting(s, now_ms);
  /* Active and Suspect: the latch decides */
}

/* The boot hold (section 6.7): the port modules' verdicts wait until each has probed twice since
   boot, two station-wide probe rounds, then they are decided in port order. */
static int boot_held(uint32_t now_ms)
{
  if (hold_over) return 0;
  if (!hold_started) { hold_started = 1; hold_from = now_ms; }
  for (unsigned q = P_AIR_TH; q < P_COUNT; q++)
    if (port_id_is_port((enum wsmp_port)q) && ports[q].rounds < HOLD_ROUNDS && now_ms - hold_from < HOLD_MAX_MS) return 1;
  hold_over = 1;
  return 0;
}

void wsmp_host_tick(uint32_t now_ms)
{
  for (unsigned q = P_AIR_TH; q < P_COUNT; q++)
  {
    port_t *s = &ports[q];
    uint16_t seq;
    local_tick((enum wsmp_port)q, now_ms);
    if (port_id_is_port((enum wsmp_port)q)) port_id_tick((enum wsmp_port)q);
    int probe = local_probe_result((enum wsmp_port)q, &seq);
    if (seq == s->probe_seq) continue;
    s->probe_seq = seq;
    s->probe = probe;
    if (s->rounds < HOLD_ROUNDS) s->rounds++;
    on_probe((enum wsmp_port)q, s, now_ms);
  }
  int held = boot_held(now_ms);
  for (unsigned q = P_AIR_TH; q < P_COUNT; q++)   /* in port order: the lower port decides first */
    if (ports[q].state == WH_IDENTIFYING) identifying((enum wsmp_port)q, &ports[q], held, now_ms);
}

static void layout_change(port_t *s, uint32_t now_ms)
{
  memmove(s->change_at, s->change_at + 1, sizeof s->change_at - sizeof s->change_at[0]);
  s->change_at[FLAP_CHANGES - 1U] = now_ms;
  s->changes++;
  if (s->changes < FLAP_CHANGES || now_ms - s->change_at[0] >= FLAP_WINDOW_MS) return;
  s->state = WH_QUARANTINED;
  s->timed = 1;
  s->quarantine_until = now_ms + QUARANTINE_MS;
  s->have_snap = 0;
}

/* A holder found gone (section 6.7): it leaves the layout now, a removal sooner than three missed latches. */
static void end_holder(port_t *h, uint32_t now_ms)
{
  if (!in_layout(h)) return;
  int joined = h->state != WH_ADMITTED;
  h->state = WH_ABSENT;
  h->have_snap = 0;
  h->good = 0;
  h->missed = 0;
  if (joined) layout_change(h, now_ms);
}

static void latch_one(enum wsmp_port p, port_t *s, uint32_t utc, uint32_t now_ms)
{
  uint8_t raw[WSMP_SNAPSHOT_LEN];
  local_latch(p, token, utc, now_ms);
  local_snapshot(p, raw);
  int read_ok = wsmp_unpack_snapshot(raw, &s->snap) == WSMP_OK && s->snap.token == token;
  s->have_snap = read_ok;
  if (read_ok && s->probe != PROBE_ABSENT) { s->state = WH_ACTIVE; s->missed = 0; return; }
  s->state = WH_SUSPECT;
  if (++s->missed < MISSED_LATCHES) return;
  s->state = WH_ABSENT;
  s->have_snap = 0;
  s->good = 0;
  layout_change(s, now_ms);
}

void wsmp_host_latch(uint32_t utc, uint32_t now_ms)
{
  token++;
  for (unsigned q = P_AIR_TH; q < P_COUNT; q++)
  {
    port_t *s = &ports[q];
    if (s->state == WH_ADMITTED) { s->state = WH_ACTIVE; s->missed = 0; layout_change(s, now_ms); }
    if (s->state == WH_ACTIVE || s->state == WH_SUSPECT) latch_one((enum wsmp_port)q, s, utc, now_ms);
  }
  for (unsigned q = P_AIR_TH; q < P_COUNT; q++)
  {
    port_t *s = &ports[q];
    if (s->state == WH_REFUSED && s->reason != WSMP_V_ADMIT) decide((enum wsmp_port)q, s, 1, now_ms);
  }
}

const wsmp_snapshot *wsmp_host_snapshot(enum wsmp_port p)
{
  const port_t *s = &ports[p];
  return (s->state == WH_ACTIVE || s->state == WH_SUSPECT) && s->have_snap ? &s->snap : NULL;
}

int wsmp_host_state(enum wsmp_port p) { return ports[p].state; }
uint32_t wsmp_host_changes(enum wsmp_port p) { return ports[p].changes; }

/* Appends text at buf + n, truncated to the buffer (len - 1 characters and the terminator); returns
   the new length. */
static unsigned append(char *buf, unsigned len, unsigned n, const char *text)
{
  for (const char *c = text; *c && n + 1U < len; c++) buf[n++] = *c;   /* bound: len - 1 characters */
  buf[n] = 0;
  return n;
}

/* A port's state, or the verdict behind a refusal or a quarantine (section 6.7: console only in v1). */
static const char *state_name(const port_t *s)
{
  static const char *const state[] = { "absent", "probing", "identifying", "admitted", "active", "suspect",
                                       "quarantined", "refused" };
  static const char *const verdict[] = { "", "type_conflict", "dup_serial", "dup_type" };
  int by_verdict = (s->state == WH_REFUSED || s->state == WH_QUARANTINED) && s->reason != WSMP_V_ADMIT;
  return by_verdict ? verdict[s->reason] : state[s->state];
}

/* "(incomplete=N)": the port's incomplete identifications (section 4.1), when there were any. */
static unsigned append_incomplete(char *buf, unsigned len, unsigned n, unsigned count)
{
  static const char head[] = "(incomplete=";
  char text[sizeof head + 4U];   /* up to 3 digits and ')' */
  unsigned i = sizeof head - 1U;
  if (count == 0) return n;
  memcpy(text, head, i);
  if (count >= DECIMAL * DECIMAL) text[i++] = (char)('0' + count / (DECIMAL * DECIMAL));
  if (count >= DECIMAL) text[i++] = (char)('0' + count / DECIMAL % DECIMAL);
  text[i++] = (char)('0' + count % DECIMAL);
  text[i++] = ')';
  text[i] = 0;
  return append(buf, len, n, text);
}

unsigned wsmp_host_modules_line(char *buf, unsigned len)
{
  static const char *const name[P_COUNT] = { "", " air_th=", " pressure=", " uva=", " encl_th=", " power=", " wind=", " rain=" };
  if (len == 0) return 0;
  unsigned n = append(buf, len, 0, "#modules");
  for (unsigned q = P_AIR_TH; q < P_COUNT; q++)
  {
    n = append(buf, len, append(buf, len, n, name[q]), state_name(&ports[q]));
    n = append_incomplete(buf, len, n, ports[q].incomplete);
  }
  return n;
}
