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
#define COUNT_MAX 255U                     /* the incomplete and unverified counters saturate */
#define DECIMAL 10U
#ifndef WSMP_HOST_SLOT_MS
#define WSMP_HOST_SLOT_MS 3000U            /* the pre-latch slot (section 6.7); a test build can make it 0 */
#endif
#define LATCH_MS 60000UL                   /* the latch period: wsmp_host_latch sets the next one this far on */
#define TIMEOUT_LATCHES 60U                /* flagged and unverified in a row: the port is ended */
#define UNVERIFIED_SHOWN 3U                /* the console shows the unverified run from this many latches */

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
  /* What admission saw, for the identity check before each latch (section 5.1): */
  uint8_t status;                              /* the record status (WSMP_REC_*) */
  uint32_t rec_crc, img_crc;                   /* the record's stored CRC; the CRC-32C of the image read */
  uint8_t replug;                              /* the sticky possibly-replugged flag */
  uint8_t check_on;                            /* this latch's identity check was asked for */
  uint8_t unverified, timeout_run;             /* unverified latches in a row; of them, with the flag set */
} port_t;

static port_t ports[P_COUNT];
static uint16_t token;
static uint8_t hold_over, hold_started;
static uint32_t hold_from;
static uint32_t next_latch;
static uint8_t latch_known, slot_on;

void wsmp_host_init(void)
{
  memset(ports, 0, sizeof ports);
  token = 0;
  hold_over = hold_started = 0;
  latch_known = slot_on = 0;
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
  s->status = v->status;
  s->rec_crc = v->record.crc;
  s->img_crc = o->read_ok ? wsmp_crc32c(o->record, WSMP_RECORD_LEN) : 0U;
  s->replug = s->check_on = s->unverified = s->timeout_run = 0;
  local_bind(p, v->status == WSMP_REC_APPLIED ? &v->record : NULL, boot_id, now_ms);
}

/* The identity a port module was admitted with, for its holder check and its identity check. */
static port_id_expect expect_of(const port_t *h)
{
  return (port_id_expect){ .serial = h->rec_serial, .id_serial = h->serial, .sensor_serial = h->sensor_serial,
                           .rec_crc = h->rec_crc, .img_crc = h->img_crc, .with_record = h->with_record,
                           .has_sensor_serial = h->has_sensor_serial, .status = h->status };
}

/* A duplicate: the holder check on the holder's port, once its engine is free (else the next tick). In
   the pre-latch slot the check waits in the engine until the latch (section 5.1). */
static void duplicate(port_t *s, const wsmp_verdict *v)
{
  s->reason = v->verdict;
  s->holder = v->holder_port;
  if (!port_id_is_port((enum wsmp_port)v->holder_port)) { s->state = WH_REFUSED; return; }   /* on-board: present */
  if (port_id_state((enum wsmp_port)v->holder_port) != PORT_ID_DONE) return;
  const port_id_expect e = expect_of(&ports[v->holder_port]);
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

static void end_port(port_t *h, uint32_t now_ms);

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
  end_port(&ports[s->holder], now_ms);
  decide(p, s, 0, now_ms);
}

static int in_slot(uint32_t now_ms)
{
#if WSMP_HOST_SLOT_MS > 0
  return latch_known && (int32_t)(now_ms - (next_latch - WSMP_HOST_SLOT_MS)) >= 0;
#else
  (void)now_ms;
  return 0;
#endif
}

/* Every module tick, before the drivers': the slot's start holds every port-module driver, and each
   module in the layout gets its identity check once a latch. */
static void slot_tick(uint32_t now_ms)
{
  uint8_t slot = (uint8_t)in_slot(now_ms);
  for (unsigned q = P_AIR_TH; q < P_COUNT; q++)
  {
    port_t *s = &ports[q];
    if (!port_id_is_port((enum wsmp_port)q)) continue;
    if (slot != slot_on) port_id_slot((enum wsmp_port)q, slot);
    if (!slot || !in_layout(s) || s->check_on) continue;
    const port_id_expect e = expect_of(s);
    port_id_check((enum wsmp_port)q, &e);
    s->check_on = 1;
  }
  slot_on = slot;
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
  slot_tick(now_ms);
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
    /* A missed probe or a failed sample read of a module in the layout: possibly replugged. */
    if (port_id_is_port((enum wsmp_port)q) && in_layout(s) && probe != PROBE_PRESENT) s->replug = 1;
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

/* A port ended before its three missed latches: a holder found gone, a confirmed change of identity or
   the timeout (section 6.7). It leaves the layout now; it is probed again as any new module. */
static void end_port(port_t *h, uint32_t now_ms)
{
  if (!in_layout(h)) return;
  int joined = h->state != WH_ADMITTED;
  h->state = WH_ABSENT;
  h->have_snap = 0;
  h->good = 0;
  h->missed = 0;
  h->unverified = 0;
  if (joined) layout_change(h, now_ms);
}

/* A good read (WSMP-P2) ends Suspect only with a matched check; good but unverified, the missed-latch
   count is neither raised nor reset. An on-board module has no check: its outcome is "matched".
   Returns 1 if the latch's read was good. */
static int latch_one(enum wsmp_port p, port_t *s, int outcome, uint32_t utc, uint32_t now_ms)
{
  uint8_t raw[WSMP_SNAPSHOT_LEN];
  local_latch(p, token, utc, now_ms);
  local_snapshot(p, raw);
  int read_ok = wsmp_unpack_snapshot(raw, &s->snap) == WSMP_OK && s->snap.token == token;
  s->have_snap = read_ok;
  int good = read_ok && s->probe != PROBE_ABSENT;
  if (good && s->state == WH_SUSPECT && outcome != PORT_ID_MATCHED) return 1;
  if (good) { s->state = WH_ACTIVE; s->missed = 0; return 1; }
  s->state = WH_SUSPECT;
  if (++s->missed < MISSED_LATCHES) return 0;
  s->state = WH_ABSENT;
  s->have_snap = 0;
  s->good = 0;
  s->unverified = 0;
  layout_change(s, now_ms);
  return 0;
}

/* The outcome of the port's identity check at this latch: unverified if it was not asked for or has not
   finished. An on-board module, or a port not in the layout, has none: "matched". */
static int outcome_of(enum wsmp_port p, const port_t *s)
{
  if (!port_id_is_port(p) || !in_layout(s)) return PORT_ID_MATCHED;
  int r = s->check_on ? port_id_check_result(p) : PORT_ID_UNVERIFIED;
  return r == PORT_ID_CHECKING ? PORT_ID_UNVERIFIED : r;
}

/* A matched check at a good latch clears the flag: the module may have been replugged, so it takes a
   new boot ID (the port's admission count goes up), the snapshot this latch froze included. */
static void new_boot(enum wsmp_port p, port_t *s)
{
  s->admissions++;
  uint32_t boot = local_boot_epoch() << BOOT_SHIFT | (s->admissions & COUNT_MASK);
  local_set_boot(p, boot);
  s->snap.boot16 = (uint16_t)boot;
}

/* Returns the outcome the identity result takes: a latch whose read failed (a missed probe or sample
   read) never matches, so an unplugged module whose check agrees (a READ module's NACK) keeps its flag. */
static int transition(enum wsmp_port p, port_t *s, int outcome, uint32_t utc, uint32_t now_ms)
{
  if (s->state == WH_ADMITTED && outcome != PORT_ID_CHANGED) { s->state = WH_ACTIVE; s->missed = 0; layout_change(s, now_ms); }
  if (s->state != WH_ACTIVE && s->state != WH_SUSPECT) return outcome;
  int good = latch_one(p, s, outcome, utc, now_ms);
  if (outcome == PORT_ID_MATCHED && !good) return PORT_ID_UNVERIFIED;
  if (s->replug && outcome == PORT_ID_MATCHED) new_boot(p, s);
  return outcome;
}

/* The window just frozen is published as missing: every slot. */
static void withhold(port_t *s)
{
  for (unsigned i = 0; i < WSMP_MAX_CHANNELS; i++) s->snap.slot[i] = (wsmp_slot){ .quality = WSMP_QUAL_MISSING };
}

/* The identity-check result of a port module still in the layout (section 5.1). */
static void identity_result(port_t *s, int outcome, uint32_t now_ms)
{
  if (!in_layout(s)) return;
  if (outcome == PORT_ID_CHANGED) { end_port(s, now_ms); return; }
  if (outcome == PORT_ID_MATCHED) { s->replug = 0; s->unverified = 0; s->timeout_run = 0; return; }
  if (s->unverified < COUNT_MAX) s->unverified++;
  if (!s->replug) return;   /* unverified without the flag: published as usual (PORT-17) */
  withhold(s);
  if (++s->timeout_run >= TIMEOUT_LATCHES) end_port(s, now_ms);
}

void wsmp_host_next_latch(uint32_t at_ms)
{
  next_latch = at_ms;
  latch_known = 1;
}

/* When this latch was due: the latch predicted, unless it comes early (before it: the schedule was not
   what was told) or a whole period late; then now. The next is due a period after it, so a sample task
   that runs late does not move the slot. */
static uint32_t due_at(uint32_t now_ms)
{
  uint32_t late = now_ms - next_latch;
  return latch_known && (int32_t)late >= 0 && late < LATCH_MS ? next_latch : now_ms;
}

void wsmp_host_latch(uint32_t utc, uint32_t now_ms)
{
  int outcome[P_COUNT];
  token++;
  for (unsigned q = P_AIR_TH; q < P_COUNT; q++)
  {
    outcome[q] = outcome_of((enum wsmp_port)q, &ports[q]);
    if (!port_id_is_port((enum wsmp_port)q)) continue;
    port_id_check_end((enum wsmp_port)q);   /* the slot ends with the latch */
    port_id_slot((enum wsmp_port)q, 0);
    ports[q].check_on = 0;
  }
  slot_on = 0;
  wsmp_host_next_latch(due_at(now_ms) + LATCH_MS);
  for (unsigned q = P_AIR_TH; q < P_COUNT; q++) outcome[q] = transition((enum wsmp_port)q, &ports[q], outcome[q], utc, now_ms);
  for (unsigned q = P_AIR_TH; q < P_COUNT; q++)
    if (port_id_is_port((enum wsmp_port)q)) identity_result(&ports[q], outcome[q], now_ms);
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

/* "(incomplete=N)" or "(unverified=N)" (head, 12 characters): a port's count, when it is shown. */
static unsigned append_count(char *buf, unsigned len, unsigned n, const char head[13], unsigned count)
{
  char text[13U + 4U];   /* the head, up to 3 digits and ')' */
  unsigned i = 12U;
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
    const port_t *s = &ports[q];
    n = append(buf, len, append(buf, len, n, name[q]), state_name(s));
    if (s->incomplete) n = append_count(buf, len, n, "(incomplete=", s->incomplete);
    if (s->unverified >= UNVERIFIED_SHOWN) n = append_count(buf, len, n, "(unverified=", s->unverified);
  }
  return n;
}
