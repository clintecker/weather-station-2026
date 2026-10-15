/* Host test driver for stage0-node/App/node_store.c over the sim_flash model (review P3).
 *
 *   test_store functional [wrap]  store_ready guards + one scripted workload, no faults
 *   test_store sweep [wrap]       the workload once per flash op index, power cut at that op,
 *                                 every cut outcome (sim_flash.h); reboot and check invariants
 *   test_store errsweep [wrap]    the workload once per flash op index, that op fails like a
 *                                 HAL error (flash unchanged, or left torn / partially erased)
 *                                 and the workload carries on
 * wrap=1 (default) runs the journal past its capacity. Output: "VIOLATION ..." lines (first few
 * per category), then "COUNT <category> <n>" for every category seen and one "SUMMARY" line.
 * The process exits 0 unless the driver itself breaks (exit 2: unknown mode, or a driver limit
 * such as MAXREC); the caller judges the categories.
 *
 * Model: the driver keeps what the application has been told (every counter and epoch
 * returned, every record appended / acked / abandoned, the lost and abandoned totals it read)
 * plus the one store call in flight when power was cut. After each reboot it checks:
 *   counter_repeat      a counter at or below one already returned
 *   epoch_repeat        an epoch at or below one already returned (or a floor already set)
 *   acked_returned      a record whose ACK returned 0 is pending again
 *   pending_uncounted   pending records missing after reboot exceed the rise in the lost total
 *   lost_decreased, abandoned_decreased
 *   config_wrong        config loads with a station/key that was never written
 *   config_lost         a completed provisioning no longer loads (no WIPE in flight)
 *   wipe_journal_survives  an interrupted WIPE left the board unprovisioned but with pending
 *                       journal records (they would go out under the next identity)
 *   sim_violation       a program over a non-erased double-word, a bad address
 * and, in fault-free runs, exact bookkeeping (lost_mismatch, abandoned_mismatch, ...). */
#include <setjmp.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "node_store.h"
#include "sim_flash.h"
#include "ws_frame.h"
#define WS_CHECK_FILE 0   /* reads the count; has no checks of its own */
#include "ws_check.h"

static sim_flash S;
int ws_flash_read64(uint32_t addr, uint64_t *out) { return sim_flash_read64(&S, addr, out); }
int ws_flash_prog64(uint32_t addr, uint64_t value) { return sim_flash_prog64(&S, addr, value); }
int ws_flash_erase(uint32_t page) { return sim_flash_erase(&S, page); }

/* node_store only needs a deterministic 3-byte check value; AES is tested in test_frame.py. */
int ws_key_check(const uint8_t key[16], uint8_t out[3]) {
 uint32_t h = 2166136261U;
 for (int i = 0; i < 16; i++) h = (h ^ key[i]) * 16777619U;
 out[0] = (uint8_t)(h >> 16); out[1] = (uint8_t)(h >> 8); out[2] = (uint8_t)h;
 return 0;
}

/* ---- violation bookkeeping ---- */
#define MAXCAT 40
static const char *cat_name[MAXCAT];
static unsigned long cat_count[MAXCAT];
static int ncat;
static const char *mode = "functional";
static uint64_t cur_op = SIM_NEVER; static int cur_variant;
static const char *where = "";

static void viol(const char *cat, const char *fmt, ...) {
 int c = 0;
 while (c < ncat && strcmp(cat_name[c], cat)) c++;
 if (c == ncat) { if (ncat == MAXCAT) abort(); cat_name[ncat++] = cat; }
 if (cat_count[c]++ < 4) {
  va_list ap; va_start(ap, fmt);
  char target[24] = "-";  /* what the cut op was writing: an address (program) or a page (erase) */
  if (S.cut_kind == SIM_OP_PROG) snprintf(target, sizeof target, "0x%08lx", (unsigned long)S.cut_addr);
  else if (S.cut_kind == SIM_OP_ERASE) snprintf(target, sizeof target, "page%lu", (unsigned long)S.cut_addr);
  printf("VIOLATION %s mode=%s op=%lld kind=%s target=%s variant=%d at=%s: ", cat, mode,
         cur_op == SIM_NEVER ? -1LL : (long long)cur_op,
         S.cut_kind == SIM_OP_PROG ? "prog" : S.cut_kind == SIM_OP_ERASE ? "erase" : "-",
         target, cur_variant, where);
  vprintf(fmt, ap); printf("\n"); va_end(ap);
 }
}
#define CHECK(cat, cond, ...) do { if (!(cond)) viol(cat, __VA_ARGS__); } while (0)

/* ---- model ---- */
#define MAXREC 16384
#define STORM 0xFFFFFFFFUL
enum { ST_NONE, ST_PENDING, ST_ACKED, ST_ABANDONED, ST_LOST, ST_WIPED, ST_FAILED };
typedef struct { uint32_t epoch; uint8_t st, ack_failed; jref_t ref; } rec_t;
/* ack_failed: an ACK returned an error; a torn ACK word counts as acknowledged at the next boot. */
static rec_t R[MAXREC];
static uint32_t nrec;
static uint32_t cyc[MAXREC], ncyc;
static uint8_t present[MAXREC];

enum { OP_NONE, OP_INIT, OP_PROVISION, OP_EPOCH, OP_FLOOR, OP_COUNTER, OP_APPEND, OP_ACK,
       OP_ABANDON_ACK, OP_NOTE, OP_SCRUB, OP_WIPE };
static struct { int op; uint32_t rec; } infl;
static int cut_happened;   /* the next power_cycle follows a power cut */
static int fault_op = OP_NONE; /* store call in flight when the injected cut or failure hit */
static void note_fault(void) { fault_op = infl.op; }
static int err_mode;       /* errsweep: one op fails, flash unchanged */

static struct {
 uint64_t max_counter;
 uint32_t max_epoch, boot_epoch;
 uint32_t lost_seen, lost_base, aband_seen;
 int cfg; uint32_t station; uint8_t key[16];
 uint32_t try_station; uint8_t try_key[16];
 int wipe_uncertain;      /* a WIPE returned an error: some pages may be erased */
 uint32_t wipes, boots;
} M;

static void model_reset(void) {
 memset(R, 0, sizeof R); nrec = 0; ncyc = 0; memset(&M, 0, sizeof M); infl.op = OP_NONE;
 cut_happened = 0; fault_op = OP_NONE;
}

static void be32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v; }
static uint32_t rd_be32(const uint8_t *p) { return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3]; }
/* Record i carries (epoch, seq = i) like an observation, plus a pattern derived from both. */
/* The journal stores WS_OBS_PLAIN_MAX bytes (node_fields.h) without parsing them. */
#define PLAIN WS_OBS_PLAIN_MAX
static void plain_for(uint32_t i, uint8_t p[PLAIN]) {
 be32(p, R[i].epoch); be32(p + 4, i);
 for (uint32_t k = 8; k < PLAIN; k++) p[k] = (uint8_t)(i * 31U + k * 7U + R[i].epoch);
}

static void observe(void) {
 uint32_t lost = store_journal_lost(), ab = store_abandoned_total();
 CHECK("lost_decreased", lost >= M.lost_seen, "lost %u after %u", (unsigned)lost, (unsigned)M.lost_seen);
 CHECK("abandoned_decreased", ab >= M.aband_seen, "abandoned %u after %u", (unsigned)ab, (unsigned)M.aband_seen);
 M.lost_seen = lost; M.aband_seen = ab;
}

/* ---- store calls, each recording what the application learns ---- */
static int do_counter(void) {
 uint64_t c; int rc;
 infl.op = OP_COUNTER; rc = store_next_counter(&c); infl.op = OP_NONE;
 if (!rc) {
  CHECK("counter_repeat", c > M.max_counter, "counter %llu after %llu", (unsigned long long)c, (unsigned long long)M.max_counter);
  if (c > M.max_counter) M.max_counter = c;
 }
 return rc;
}
static void do_counters(int n) { for (int i = 0; i < n; i++) do_counter(); }
static int do_epoch(void) {
 uint32_t e; int rc;
 infl.op = OP_EPOCH; rc = store_next_epoch(&e); infl.op = OP_NONE;
 if (!rc) {
  CHECK("epoch_repeat", e > M.max_epoch, "epoch %u after %u", (unsigned)e, (unsigned)M.max_epoch);
  if (e > M.max_epoch) M.max_epoch = e;
  M.boot_epoch = e;
 }
 return rc;
}
static void do_floor(uint32_t f) {
 infl.op = OP_FLOOR; int rc = store_epoch_floor(f); infl.op = OP_NONE;
 if (!rc && f > M.max_epoch) M.max_epoch = f;
}
static void do_note(void) {
 infl.op = OP_NOTE; store_note_abandoned(); infl.op = OP_NONE;
 observe();
}
static uint32_t do_append(uint32_t epoch) {
 uint8_t p[PLAIN]; uint32_t i = nrec++; int rc;
 if (nrec >= MAXREC) { fprintf(stderr, "MAXREC\n"); exit(2); }
 R[i].epoch = epoch; R[i].st = ST_NONE; plain_for(i, p);
 infl.op = OP_APPEND; infl.rec = i; rc = store_journal_append(p, &R[i].ref); infl.op = OP_NONE;
 R[i].st = rc ? ST_FAILED : ST_PENDING;
 observe();
 return i;
}
/* ACK as the application does: find by (epoch, seq), then ack that slot. */
static int do_ack(uint32_t i, int op) {
 jref_t r; int rc;
 if (R[i].st != ST_PENDING) return -1;
 if (store_journal_find(R[i].epoch, i, &r)) return -1; /* dropped by a wrap: sync() counts it */
 CHECK("find_wrong", r.page == R[i].ref.page && r.slot == R[i].ref.slot, "rec %u", (unsigned)i);
 infl.op = op; infl.rec = i; rc = store_journal_ack(r); infl.op = OP_NONE;
 if (!rc) R[i].st = op == OP_ABANDON_ACK ? ST_ABANDONED : ST_ACKED;
 else R[i].ack_failed = 1;
 return rc;
}
static void do_abandon(uint32_t i) { if (do_ack(i, OP_ABANDON_ACK) == 0) do_note(); }
static void do_provision(uint32_t station, uint8_t seed) {
 uint8_t key[16];
 for (int k = 0; k < 16; k++) key[k] = (uint8_t)(seed * 17 + k * 29 + 1);
 M.try_station = station; memcpy(M.try_key, key, 16);
 infl.op = OP_PROVISION; uint8_t kcv[3]; int rc = store_config_write(station, key, kcv); infl.op = OP_NONE;
 if (!rc) {
  uint8_t want[3]; ws_key_check(key, want);
  CHECK("config_kcv", !memcmp(kcv, want, 3), "provision returned a wrong key check value");
  M.cfg = 1; M.station = station; memcpy(M.key, key, 16);
 }
}
static void do_wipe(void) {
 infl.op = OP_WIPE; int rc = store_wipe(); infl.op = OP_NONE;
 if (rc) { M.wipe_uncertain = 1; return; }
 for (uint32_t i = 0; i < nrec; i++) if (R[i].st == ST_PENDING) R[i].st = ST_WIPED;
 M.cfg = 0; M.wipes++;
}

/* Compares the store's pending set with the model. After a cut, the call in flight may or may
   not have taken effect; otherwise the bookkeeping must match exactly. */
static void reconcile(void) {
 static jref_t refs[JOURNAL_CAPACITY + 1];
 int cut = cut_happened;
 int maybe_wipe = (cut && infl.op == OP_WIPE) || M.wipe_uncertain;
 int inflight_ack = cut && (infl.op == OP_ACK || infl.op == OP_ABANDON_ACK);
 unsigned n = store_journal_oldest(refs, JOURNAL_CAPACITY + 1, NULL), missing = 0;
 uint32_t last_missing = 0;
 CHECK("pending_count", n == store_journal_pending(), "oldest %u pending %u", n, (unsigned)store_journal_pending());
 memset(present, 0, nrec);
 for (unsigned k = 0; k < n; k++) {
  uint8_t p[PLAIN], want[PLAIN]; uint32_t i;
  if (store_journal_read(refs[k], p)) { viol("unreadable_pending", "page %u slot %u", refs[k].page, refs[k].slot); continue; }
  i = rd_be32(p + 4);
  if (i >= nrec) { viol("foreign_record", "seq %u", (unsigned)i); continue; }
  plain_for(i, want);
  if (memcmp(p, want, PLAIN)) { viol("foreign_record", "rec %u content differs", (unsigned)i); continue; }
  if (present[i]) { viol("duplicate_pending", "rec %u", (unsigned)i); continue; }
  present[i] = 1;
  switch (R[i].st) {
  case ST_PENDING: break;
  case ST_ACKED: case ST_ABANDONED:
   if (inflight_ack && infl.rec == i) break;
   if (cut && infl.op == OP_SCRUB && R[i].epoch == STORM) break;
   if (maybe_wipe) { viol("note_acked_back_after_interrupted_wipe", "rec %u", (unsigned)i); break; }
   /* Fixed 2026-10-13 (store_journal_init finishes an interrupted recycle): an interrupted erase
      while a journal append recycled the oldest page (journal_new_page) could erase an ACK word
      but not its record, which then read back as pending. Kept as its own category so a
      regression is recognisable; any other path is acked_returned. Both fail the sweeps. */
   viol(fault_op == OP_APPEND && S.cut_kind == SIM_OP_ERASE ? "acked_returned_recycle_erase" : "acked_returned",
        "rec %u (state %d) pending again at page %u slot %u", (unsigned)i, R[i].st, refs[k].page, refs[k].slot);
   break;
  case ST_NONE: case ST_FAILED:
   if (cut && infl.op == OP_APPEND && infl.rec == i) break;
   viol("unexpected_record", "rec %u whose append failed is pending", (unsigned)i);
   break;
  case ST_LOST: viol("note_lost_back", "rec %u counted lost is pending again", (unsigned)i); break;
  case ST_WIPED:
   if (!maybe_wipe) viol("wiped_returned", "rec %u", (unsigned)i);
   break;
  }
  R[i].st = ST_PENDING; R[i].ref = refs[k];
 }
 for (uint32_t i = 0; i < nrec; i++) {
  if (R[i].st != ST_PENDING || present[i]) continue;
  if ((inflight_ack && infl.rec == i) || R[i].ack_failed) { R[i].st = ST_ACKED; continue; }
  if (cut && infl.op == OP_SCRUB && R[i].epoch == STORM) { R[i].st = ST_ACKED; continue; }
  if (maybe_wipe) { R[i].st = ST_WIPED; continue; }
  R[i].st = ST_LOST; missing++; last_missing = i;
 }
 uint32_t lost = store_journal_lost();
 uint32_t delta = lost > M.lost_base ? lost - M.lost_base : 0;
 /* Fixed 2026-10-13: journal_new_page used to erase the page even when persisting the lost
    total failed. Kept as its own category so a regression is recognisable; it fails the sweeps. */
 CHECK(err_mode && fault_op == OP_APPEND ? "lost_decreased_wrap_persist_failed" : "lost_decreased",
       lost >= M.lost_seen, "lost %u after %u", (unsigned)lost, (unsigned)M.lost_seen);
 if (!cut && !err_mode)
  CHECK("lost_mismatch", missing == delta, "%u records gone, lost rose by %u", missing, (unsigned)delta);
 else
  CHECK("pending_uncounted", missing <= delta, "%u records gone (last rec %u), lost rose by %u", missing, (unsigned)last_missing, (unsigned)delta);
 M.lost_seen = M.lost_base = lost;
}

static void check_config(unsigned npending) {
 uint32_t st = 0; uint8_t key[16], kcv[3] = { 0xA5, 0xA5, 0xA5 }, want[3]; int cut = cut_happened;
 int rc = store_config_load(&st, key, kcv);
 /* The returned key check value is the loaded key's; a failed load leaves it untouched. */
 if (rc == 0) { ws_key_check(key, want); if (memcmp(kcv, want, 3)) viol("config_kcv", "wrong key check value"); }
 else if (kcv[0] != 0xA5 || kcv[1] != 0xA5 || kcv[2] != 0xA5) viol("config_kcv", "kcv written on a failed load (rc %d)", rc);
 int match = rc == 0 && M.cfg && st == M.station && !memcmp(key, M.key, 16);
 int match_try = rc == 0 && cut && infl.op == OP_PROVISION && st == M.try_station && !memcmp(key, M.try_key, 16);
 int wiping = (cut && infl.op == OP_WIPE) || M.wipe_uncertain;
 int was_cfg = M.cfg;
 /* An interrupted WIPE may leave the old config readable; no other config may appear. */
 if (rc == 0 && !match && !match_try) viol("config_wrong", "station %u loaded", (unsigned)st);
 if (rc != 0 && M.cfg && !wiping) viol("config_lost", "rc %d", rc);
 if (rc != 0 && was_cfg && wiping && npending)
  viol("wipe_journal_survives", "unprovisioned after an interrupted WIPE with %u pending records", npending);
 if (match_try) { M.station = st; memcpy(M.key, key, 16); }
 M.cfg = rc == 0;
}

/* One power-on: the application's boot sequence (app_tx.c SubghzApp_Init) plus the checks. */
static void power_cycle(void) {
 uint64_t ops0 = S.ops; int rc;
 where = "boot";
 infl.op = cut_happened ? infl.op : OP_NONE;
 int saved_op = infl.op; uint32_t saved_rec = infl.rec;
 rc = store_meta_init(); if (!rc) rc = store_journal_init();
 if (rc) {
  if (err_mode && S.fail_at >= ops0 && S.fail_at < S.ops) { rc = store_meta_init(); if (!rc) rc = store_journal_init(); }
  if (rc) { viol("init_failed", "rc %d", rc); return; }
 }
 M.boots++;
 infl.op = saved_op; infl.rec = saved_rec;
 reconcile();
 uint32_t ab = store_abandoned_total();
 /* Fixed 2026-10-13: store_note_abandoned used to raise the RAM total before (and even if not)
    persisting. Kept as its own category so a regression is recognisable; it fails the sweeps. */
 CHECK(err_mode && fault_op == OP_NOTE ? "abandoned_decreased_note_failed" : "abandoned_decreased",
       ab >= M.aband_seen, "abandoned %u after %u", (unsigned)ab, (unsigned)M.aband_seen);
 if (!(cut_happened && infl.op == OP_NOTE) && !err_mode)
  CHECK("abandoned_mismatch", ab == M.aband_seen, "abandoned %u, application saw %u", (unsigned)ab, (unsigned)M.aband_seen);
 CHECK("abandoned_jump", ab <= M.aband_seen + 1, "abandoned %u after %u", (unsigned)ab, (unsigned)M.aband_seen);
 M.aband_seen = ab;
 CHECK("counter_repeat", store_counter_next() > M.max_counter, "next %llu after %llu",
       (unsigned long long)store_counter_next(), (unsigned long long)M.max_counter);
 check_config(store_journal_pending());
 /* the boot scrub of storm records */
 uint32_t want = 0;
 for (uint32_t i = 0; i < nrec; i++) if (R[i].st == ST_PENDING && R[i].epoch == STORM) want++;
 cut_happened = 0; M.wipe_uncertain = 0; infl.op = OP_SCRUB;
 uint32_t got = store_journal_scrub(STORM);
 infl.op = OP_NONE;
 for (uint32_t i = 0; i < nrec; i++) {
  jref_t r;
  if (R[i].st == ST_PENDING && R[i].epoch == STORM && store_journal_find(STORM, i, &r)) R[i].st = ST_ACKED;
 }
 if (!err_mode) CHECK("scrub_count", got == want, "scrubbed %u of %u", (unsigned)got, (unsigned)want);
 do_epoch();
 CHECK("sim_violation", S.violations == 0, "%s", S.last_violation);
 where = "run";
}

/* ---- the scripted workload ---- */
static void sync_now(void) { reconcile(); }

/* One sampling minute: a transmission counter, a journal append, ACKs for older records,
   sometimes an abandon. About a quarter of the records stay pending so the wrap loses some. */
static void obs_cycle(void) {
 uint32_t c = ncyc, r;
 do_counter();
 r = do_append(M.boot_epoch);
 cyc[ncyc++] = r;
 if (c >= 3 && c % 3 != 2) do_ack(cyc[c - 3], OP_ACK);
 if (c % 4 == 0) do_ack(r, OP_ACK);
 if (c >= 6 && c % 11 == 5) do_abandon(cyc[c - 6]);
 if (c % 25 == 24) sync_now();
}

static void workload(int wrap) {
 power_cycle();                       /* first boot: creates the meta log and journal page 0 */
 do_provision(1001, 1); power_cycle(); /* PROVISION reboots */
 for (int i = 0; i < 40; i++) obs_cycle();
 power_cycle();
 /* Fill the meta log well past two compactions (A->B->A): epochs, abandoned notes, and
    counter bursts that cross reservation blocks. */
 for (int i = 0; i < 560; i++) {
  if (i % 3 == 0) do_epoch();
  else if (i % 3 == 1) { if (i % 30 == 1) do_note(); else do_epoch(); }
  else if (i % 15 == 2) do_counters(300);
  else do_epoch();
  if (i == 300) power_cycle();
 }
 do_floor(M.max_epoch + 1000);
 power_cycle();
 int n = wrap ? (int)(JOURNAL_CAPACITY + JOURNAL_CAPACITY / 2) : 60;
 for (int i = 0; i < n; i++) obs_cycle();
 sync_now();
 /* TEST-FLASH-STORM leftovers: some acked at once, the rest scrubbed at the next boot */
 for (int i = 0; i < 6; i++) { uint32_t r = do_append(STORM); if (i % 2) do_ack(r, OP_ACK); }
 power_cycle();
 for (int i = 0; i < 10; i++) obs_cycle();
 /* Account for any wrap losses before the WIPE: afterwards a missing record reads as wiped, so a
    loss left unchecked here would make the exact lost count disagree (seen with 56-byte slots). */
 sync_now();
 do_wipe(); power_cycle();             /* WIPE reboots; meta must survive it */
 do_provision(1002, 2); power_cycle();
 for (int i = 0; i < 20; i++) obs_cycle();
 power_cycle();
}

/* After a cut: reboot and check, run a little more, reboot and check again. */
static void recovery(void) {
 power_cycle();
 for (int i = 0; i < 6; i++) { obs_cycle(); do_counters(100); }
 power_cycle();
}

/* ---- store_ready guards ---- */
static int guards(void) {
 uint64_t c; uint32_t e; jref_t r; uint8_t p[PLAIN] = { 0 }; int bad = 0;
 if (store_next_counter(&c) != STORE_ENOTREADY) { printf("GUARD next_counter\n"); bad++; }
 if (store_next_epoch(&e) != STORE_ENOTREADY) { printf("GUARD next_epoch\n"); bad++; }
 if (store_epoch_floor(5) != STORE_ENOTREADY) { printf("GUARD epoch_floor\n"); bad++; }
 if (store_note_abandoned() != STORE_ENOTREADY || store_abandoned_total() != 0) { printf("GUARD note_abandoned\n"); bad++; }
 if (store_journal_append(p, &r) != STORE_ENOTREADY) { printf("GUARD append\n"); bad++; }
 r.page = 0; r.slot = 0;
 if (store_journal_ack(r) != STORE_ENOTREADY) { printf("GUARD ack\n"); bad++; }
 if (store_journal_scrub(STORM) != 0) { printf("GUARD scrub\n"); bad++; }
 if (S.ops) { printf("GUARD flash touched before init\n"); bad++; }
 if (store_meta_init()) { printf("GUARD meta_init\n"); bad++; }
 if (store_journal_append(p, &r) != STORE_ENOTREADY) { printf("GUARD append before journal_init\n"); bad++; }
 if (store_next_counter(&c) || c != 1) { printf("GUARD counter after meta_init\n"); bad++; }
 if (store_journal_init() || store_journal_append(p, &r)) { printf("GUARD append after init\n"); bad++; }
 if (store_wipe() || store_journal_append(p, &r) != STORE_ENOTREADY) { printf("GUARD append after wipe\n"); bad++; }
 if (store_next_counter(&c) || c != 2) { printf("GUARD counter after wipe\n"); bad++; }
 return bad;
}

/* ---- draft-5 limits ---- */
/* The transmission counter stops at 2^40 - 1 (the header holds 5 bytes): seed the meta log just
   below it, then the allocator must hand out exactly WS_COUNTER_MAX and refuse the next one. */
static int counter_limit(void) {
 uint64_t c = 0; int bad = 0;
 sim_flash_reset(&S);
 if (store_meta_init()) { printf("LIMIT meta_init\n"); return 1; }
 sim_flash_prog64(&S, WS_PAGE_ADDR(WS_META_PAGE_A) + 8, (uint64_t)0xC2 << 56 | (WS_COUNTER_MAX - 1U));
 if (store_meta_init()) { printf("LIMIT meta_init seeded\n"); return 1; }
 if (store_next_counter(&c) || c != WS_COUNTER_MAX) { printf("LIMIT last counter %llu\n", (unsigned long long)c); bad++; }
 if (store_next_counter(&c) == 0) { printf("LIMIT counter past 2^40-1 issued: %llu\n", (unsigned long long)c); bad++; }
 return bad;
}

/* A journal page written with another slot layout (here the draft-4 "WSJ1" magic, 40-byte slots)
   is ignored at boot, never read as records of this layout. */
static int foreign_layout(void) {
 uint8_t p[PLAIN] = { 0 }; jref_t r; int bad = 0;
 sim_flash_reset(&S);
 uint32_t a = WS_PAGE_ADDR(WS_JOURNAL_FIRST);
 sim_flash_prog64(&S, a, (uint64_t)0x57534A31UL << 32 | 7U);                    /* "WSJ1", sequence 7 */
 for (uint32_t k = 1; k <= 4; k++) sim_flash_prog64(&S, a + 8 * k, 0x0102030405060708ULL * k);
 if (store_meta_init() || store_journal_init()) { printf("FOREIGN init\n"); return 1; }
 if (store_journal_pending() != 0 || store_journal_burned() != 0) {
  printf("FOREIGN pending=%u burned=%u\n", (unsigned)store_journal_pending(), (unsigned)store_journal_burned()); bad++;
 }
 if (store_journal_append(p, &r) || store_journal_pending() != 1) { printf("FOREIGN append\n"); bad++; }
 return bad;
}

/* ---- run-time checks (firmware/common/ws_check.h) ---- */
/* A jref_t outside the journal (none ever comes from the store) is refused by read and ack: each
   failed check is counted, the first one's site is node_store.c's, and the pending set is untouched. */
static int checks(void) {
 uint8_t p[PLAIN] = { 0 }; jref_t r, out = { (uint16_t)WS_JOURNAL_PAGES, 0 }; int bad = 0;
 sim_flash_reset(&S);
 if (store_meta_init() || store_journal_init() || store_journal_append(p, &r)) { printf("CHECK init\n"); return 1; }
 uint32_t before = ws_check_count(), pending = store_journal_pending();
 if (store_journal_ack(out) == 0 || store_journal_read(out, p) == 0) { printf("CHECK out-of-journal ref accepted\n"); bad++; }
 out.page = 0; out.slot = (uint16_t)JOURNAL_SLOTS_PER_PAGE;
 if (store_journal_ack(out) == 0) { printf("CHECK out-of-page slot accepted\n"); bad++; }
 if (ws_check_count() != before + 3 || store_journal_pending() != pending) {
  printf("CHECK count %u -> %u, pending %u -> %u\n", (unsigned)before, (unsigned)ws_check_count(), (unsigned)pending,
         (unsigned)store_journal_pending()); bad++;
 }
 if (!before && WS_CHECK_FILE_OF(ws_check_first()) != 5) { printf("CHECK first site %04x\n", ws_check_first()); bad++; }
 if (store_journal_ack(r) || store_journal_pending() != pending - 1) { printf("CHECK a real ack after\n"); bad++; }
 return bad;
}

static void summary(const char *extra) {
 for (int c = 0; c < ncat; c++) printf("COUNT %s %lu\n", cat_name[c], cat_count[c]);
 printf("SUMMARY mode=%s journal_pages=%u check_fails=%u %s\n", mode, (unsigned)WS_JOURNAL_PAGES, (unsigned)ws_check_count(), extra);
}

int main(int argc, char **argv) {
 static jmp_buf jb;
 char buf[512];
 int wrap = argc > 2 ? atoi(argv[2]) : 1;
 if (argc < 2) { fprintf(stderr, "usage: %s functional|sweep|errsweep [wrap]\n", argv[0]); return 2; }
 mode = argv[1];
 if (strcmp(mode, "functional") && strcmp(mode, "sweep") && strcmp(mode, "errsweep")) {
  fprintf(stderr, "unknown mode '%s'; usage: %s functional|sweep|errsweep [wrap]\n", mode, argv[0]);
  return 2;
 }
 setvbuf(stdout, NULL, _IOLBF, 0);
 sim_flash_reset(&S);
 if (!strcmp(mode, "functional")) {
  int g = guards() + counter_limit() + foreign_layout() + checks();
  sim_flash_reset(&S); model_reset();
  workload(wrap);
  uint32_t ma = S.page_erases[WS_META_PAGE_A - SIM_FIRST_PAGE], mb = S.page_erases[WS_META_PAGE_B - SIM_FIRST_PAGE];
  uint32_t j0 = S.page_erases[WS_JOURNAL_FIRST - SIM_FIRST_PAGE];
  snprintf(buf, sizeof buf, "guard_failures=%d ops=%llu progs=%llu erases=%llu meta_erases=%u,%u journal0_erases=%u "
           "lost=%u abandoned=%u max_counter=%llu max_epoch=%u records=%u boots=%u wipes=%u zero_overwrites=%llu "
           "ecc_reads=%llu",
           g, (unsigned long long)S.ops, (unsigned long long)S.progs, (unsigned long long)S.erases,
           (unsigned)ma, (unsigned)mb, (unsigned)j0, (unsigned)M.lost_seen, (unsigned)M.aband_seen,
           (unsigned long long)M.max_counter, (unsigned)M.max_epoch, (unsigned)nrec, (unsigned)M.boots, (unsigned)M.wipes,
           (unsigned long long)S.zero_overwrites, (unsigned long long)S.ecc_reads);
  summary(buf);
  return 0;
 }
 /* Golden run: how many ops, and of which kind. */
 static uint8_t kinds[1 << 20];
 S.on_fault = note_fault;
 S.kinds = kinds; S.kinds_cap = sizeof kinds;
 sim_flash_reset(&S); model_reset();
 workload(wrap);
 uint64_t nops = S.ops, runs = 0, cuts_prog = 0, cuts_erase = 0, zero_ow = 0, ecc_reads = 0;
 if (nops > sizeof kinds) { fprintf(stderr, "too many ops\n"); return 2; }
 S.kinds = NULL; S.kinds_cap = 0;
 err_mode = !strcmp(mode, "errsweep");
 for (uint64_t k = 0; k < nops; k++) {
  int nv = err_mode ? SIM_FAIL_VARIANTS : sim_flash_variants(kinds[k]);
  for (int v = 0; v < nv; v++) {
   zero_ow += S.zero_overwrites; ecc_reads += S.ecc_reads;
   sim_flash_reset(&S); model_reset();
   cur_op = k; cur_variant = v; where = "run";
   runs++;
   if (err_mode) { S.fail_at = k; S.fail_variant = v; S.seed = (uint32_t)k; workload(wrap); continue; }
   S.cut_at = k; S.cut_variant = v; S.seed = (uint32_t)k; S.cut_jump = &jb;
   if (setjmp(jb) == 0) { workload(wrap); viol("cut_not_reached", "workload finished"); continue; }
   if (S.cut_kind != kinds[k]) viol("nondeterministic", "op kind differs from the golden run");
   S.cut_at = SIM_NEVER; S.cut_jump = NULL;
   cut_happened = 1; where = "after-cut";
   if (S.cut_kind == SIM_OP_PROG) cuts_prog++; else cuts_erase++;
   recovery();
  }
 }
 snprintf(buf, sizeof buf, "cut_points=%llu runs=%llu prog_cuts=%llu erase_cuts=%llu zero_overwrites=%llu ecc_reads=%llu",
          (unsigned long long)nops, (unsigned long long)runs, (unsigned long long)cuts_prog, (unsigned long long)cuts_erase,
          (unsigned long long)(zero_ow + S.zero_overwrites), (unsigned long long)(ecc_reads + S.ecc_reads));
 summary(buf);
 return 0;
}
