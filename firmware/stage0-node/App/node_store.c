/* Power-fail-safe node state in internal flash.
 *
 * Every record is committed by programming one final double-word after its data, so an
 * interrupted write leaves either nothing, an uncommitted slot, or a double-ECC error that
 * NMI_Handler reports through ws_flash_ecc_fault. All three read back as "not present".
 * Monotonic values only ever increase: recovery takes the maximum of everything readable.
 * No HAL here: flash goes through ws_flash_internal (App/flash_stm32wl.c on the board,
 * firmware/sim_flash.c in tests/test_store_powercut.py). */
#include "node_store.h"
#include <string.h>
#include "ws_be.h"
#include "ws_frame.h"

#define ERASED 0xFFFFFFFFFFFFFFFFULL
#define CFG_MAGIC  0x57534331UL /* "WSC1" */
#define CFG_MAGIC2 0x4B435631UL /* "KCV1" */
#define META_MAGIC 0x57534D31UL /* "WSM1" */
#define JPG_MAGIC  (0x57534A00UL | JOURNAL_SLOT_BYTES) /* "WSJ" + slot size: another layout is ignored */
#define SLOT_MAGIC 0x4A53U
#define META_EPOCH 0xE1U
#define META_CTR   0xC2U
#define META_LOST  0xD1U /* cumulative journal overflow losses (gap G8) */
#define META_ABAND 0xD2U /* cumulative abandoned records (NACK / strike limit) */
#define META_DWORDS (WS_PAGE_SIZE / 8U)
#define CTR_BLOCK 256U

/* Geometry the on-flash format depends on (node_store.h). */
#define SLOT_BYTES JOURNAL_SLOT_BYTES
#define COMMIT_OFF (JOURNAL_PLAIN_DW * 8U)
#define ACK_OFF (COMMIT_OFF + 8U)
_Static_assert(SLOT_BYTES == JOURNAL_PLAIN_DW * 8U + 16U && SLOT_BYTES >= WS_OBS_PLAIN_MAX + 16U,
               "slot = plaintext rounded to double-words + commit + ack double-words");
_Static_assert(SLOT_BYTES < 256U, "the slot size fits in the page magic's low byte");
_Static_assert(JOURNAL_SLOTS_PER_PAGE >= 1U && 8U + JOURNAL_SLOTS_PER_PAGE * SLOT_BYTES <= WS_PAGE_SIZE, "journal slots fit in one page");
_Static_assert((uint64_t)WS_CONFIG_PAGE * WS_PAGE_SIZE >= 0x10000U, "node state sits above the 64 KB firmware region (STM32WL55JCIX_FLASH.ld)");
_Static_assert(WS_CONFIG_PAGE < WS_META_PAGE_A && WS_META_PAGE_A < WS_META_PAGE_B && WS_META_PAGE_B < WS_JOURNAL_FIRST,
               "config, meta and journal pages are distinct and in order");
_Static_assert(WS_JOURNAL_PAGES >= 2U && WS_JOURNAL_FIRST + WS_JOURNAL_PAGES <= 128U, "journal fits in the 128 flash pages");
_Static_assert(WS_JOURNAL_PAGES <= 0xFFFFU && JOURNAL_SLOTS_PER_PAGE <= 0xFFFFU, "jref_t page and slot are 16-bit");

/* ---- flash primitives (ws_flash ops, flash_layout.h) ---- */
static uint32_t n_ecc;
static uint64_t rd64(uint32_t addr, int *bad) {
 uint64_t v;
 if (ws_flash_internal.read64(ws_flash_internal.ctx, addr, &v)) { n_ecc++; if (bad) *bad = 1; return 0; }
 return v;
}
static int prog64(uint32_t addr, uint64_t v) {
 return ws_flash_internal.prog64(ws_flash_internal.ctx, addr, v) ? -1 : 0;
}
static int erase_page(uint32_t page) {
 return ws_flash_internal.erase(ws_flash_internal.ctx, page) ? -1 : 0;
}

/* store_ready guard (review P3): mutators refuse to run on RAM state that no successful init
   produced, instead of appending at a stale position. */
static uint8_t meta_ready, journal_ready;

/* ---- provisioning ---- */
int store_config_load(uint32_t *station, uint8_t key[16], uint8_t kcv_out[3]) {
 uint32_t a = WS_PAGE_ADDR(WS_CONFIG_PAGE); int bad = 0; uint8_t kcv[3];
 uint64_t d0 = rd64(a, &bad), k0 = rd64(a + 8, &bad), k1 = rd64(a + 16, &bad), d3 = rd64(a + 24, &bad);
 if (bad || (d0 >> 32) != CFG_MAGIC || (d3 >> 32) != CFG_MAGIC2) return -1;
 memcpy(key, &k0, 8); memcpy(key + 8, &k1, 8); ws_wipe(&k0, 8); ws_wipe(&k1, 8);
 if (ws_key_check(key, kcv) || (uint32_t)(d3 & 0xFFFFFFU) != ((uint32_t)kcv[0] << 16 | kcv[1] << 8 | kcv[2])) {
  ws_wipe(key, 16); return -2;
 }
 *station = (uint32_t)d0;
 if (*station == 0 || *station > WS_STATION_MAX) { ws_wipe(key, 16); return -3; }
 memcpy(kcv_out, kcv, 3);
 return 0;
}
int store_config_write(uint32_t station, const uint8_t key[16], uint8_t kcv[3]) {
 uint32_t a = WS_PAGE_ADDR(WS_CONFIG_PAGE); uint64_t k0, k1;
 for (uint32_t i = 0; i < 4; i++) if (rd64(a + 8 * i, 0) != ERASED) return -1; /* refuse overwrite */
 if (station == 0 || station > WS_STATION_MAX || ws_key_check(key, kcv)) return -2;
 memcpy(&k0, key, 8); memcpy(&k1, key + 8, 8);
 /* Magic double-word last: a torn write is never mistaken for a valid config. */
 if (prog64(a + 8, k0) || prog64(a + 16, k1) ||
     prog64(a + 24, (uint64_t)CFG_MAGIC2 << 32 | (uint32_t)kcv[0] << 16 | kcv[1] << 8 | kcv[2]) ||
     prog64(a, (uint64_t)CFG_MAGIC << 32 | station)) { ws_wipe(&k0, 8); ws_wipe(&k1, 8); return -3; }
 ws_wipe(&k0, 8); ws_wipe(&k1, 8);
 return 0;
}

/* ---- monotonic meta log ---- */
static uint32_t meta_active, meta_pos, meta_gen;
static uint32_t max_epoch;
static uint64_t ctr_reserved, ctr_next;
static uint32_t lost_total, abandoned_total;

static int meta_scan(uint32_t page, uint32_t *gen, uint32_t *last) {
 uint32_t a = WS_PAGE_ADDR(page); int bad = 0;
 uint64_t h = rd64(a, &bad);
 if (bad || (h >> 32) != META_MAGIC) return -1;
 *gen = (uint32_t)h; *last = 0;
 for (uint32_t i = 1; i < META_DWORDS; i++) {
  int b = 0; uint64_t v = rd64(a + 8 * i, &b);
  if (!b && v == ERASED) continue;
  *last = i;
  if (b) continue;
  uint64_t val = v & 0x00FFFFFFFFFFFFFFULL;
  if ((v >> 56) == META_EPOCH && val > max_epoch && val <= 0xFFFFFFFFULL) max_epoch = (uint32_t)val;
  if ((v >> 56) == META_CTR && val > ctr_reserved) ctr_reserved = val;
  if ((v >> 56) == META_LOST && val > lost_total && val <= 0xFFFFFFFFULL) lost_total = (uint32_t)val;
  if ((v >> 56) == META_ABAND && val > abandoned_total && val <= 0xFFFFFFFFULL) abandoned_total = (uint32_t)val;
 }
 return 0;
}
static int meta_append(uint32_t type, uint64_t value) {
 if (value >> 56) return -1;
 if (meta_pos >= META_DWORDS) {
  /* Compact into the other page; its header is written last so a torn compaction
     leaves the current page authoritative. The other page still carries an older valid header:
     zero it first (programming all-zeros over data is allowed), so an erase cut part way can
     never leave half-erased values under a header boot would trust (firmware review finding 4:
     junk could raise the counter past 2^40 and disable the node for good). */
  uint32_t other = meta_active == WS_META_PAGE_A ? WS_META_PAGE_B : WS_META_PAGE_A;
  uint32_t a = WS_PAGE_ADDR(other);
  int bad = 0;
  if (rd64(a, &bad) != ERASED && prog64(a, 0)) return -2;
  if (erase_page(other) ||
      prog64(a + 8, (uint64_t)META_EPOCH << 56 | max_epoch) ||
      prog64(a + 16, (uint64_t)META_CTR << 56 | ctr_reserved) ||
      prog64(a + 24, (uint64_t)META_LOST << 56 | lost_total) ||
      prog64(a + 32, (uint64_t)META_ABAND << 56 | abandoned_total) ||
      prog64(a, (uint64_t)META_MAGIC << 32 | (meta_gen + 1))) return -2;
  meta_active = other; meta_gen++; meta_pos = 5;
 }
 if (prog64(WS_PAGE_ADDR(meta_active) + 8 * meta_pos, (uint64_t)type << 56 | value)) { meta_pos++; return -3; }
 meta_pos++;
 return 0;
}
int store_meta_init(void) {
 uint32_t ga = 0, gb = 0, la = 0, lb = 0;
 int va, vb;
 meta_ready = 0;
 max_epoch = 0; ctr_reserved = 0; lost_total = 0; abandoned_total = 0;
 va = meta_scan(WS_META_PAGE_A, &ga, &la) == 0;
 vb = meta_scan(WS_META_PAGE_B, &gb, &lb) == 0;
 if (!va && !vb) {
  if (erase_page(WS_META_PAGE_A) || prog64(WS_PAGE_ADDR(WS_META_PAGE_A), (uint64_t)META_MAGIC << 32 | 1)) return -1;
  meta_active = WS_META_PAGE_A; meta_gen = 1; meta_pos = 1;
 } else if (va && (!vb || ga > gb)) {
  meta_active = WS_META_PAGE_A; meta_gen = ga; meta_pos = la + 1;
 } else {
  meta_active = WS_META_PAGE_B; meta_gen = gb; meta_pos = lb + 1;
 }
 ctr_next = ctr_reserved + 1; /* skip anything that may have been used before reset */
 meta_ready = 1;
 return 0;
}
int store_next_epoch(uint32_t *epoch) {
 if (!meta_ready) return STORE_ENOTREADY;
 /* 0xFFFFFFFF is the bench storm test's epoch (app_tx.c STORM_EPOCH), whose records the boot
    scrub acknowledges: a real boot must never get it. */
 if (max_epoch >= 0xFFFFFFFEUL) return -1;
 if (meta_append(META_EPOCH, (uint64_t)max_epoch + 1)) return -2;
 *epoch = ++max_epoch;
 return 0;
}
/* Gap G5: after a WIPE, the gateway supplies a floor above every epoch it has stored, so new
   observation identities can never collide with history. Values only move up. */
int store_epoch_floor(uint32_t floor) {
 if (!meta_ready) return STORE_ENOTREADY;
 if (floor <= max_epoch) return 0;
 if (meta_append(META_EPOCH, floor)) return -1;
 max_epoch = floor;
 return 0;
}
int store_note_abandoned(void) {
 if (!meta_ready) return STORE_ENOTREADY;
 if (meta_append(META_ABAND, (uint64_t)abandoned_total + 1)) return -1;
 abandoned_total++;
 return 0;
}
uint32_t store_abandoned_total(void) { return abandoned_total; }

int store_next_counter(uint64_t *counter) {
 if (!meta_ready) return STORE_ENOTREADY;
 /* The header carries 40 bits: past that a counter would be truncated and repeat a nonce. */
 if (ctr_next > WS_COUNTER_MAX) return -2;
 if (ctr_next > ctr_reserved) {
  uint64_t upto = ctr_reserved + CTR_BLOCK;
  if (meta_append(META_CTR, upto)) return -1; /* no durable reservation, no counter */
  ctr_reserved = upto;
 }
 *counter = ctr_next++;
 return 0;
}

/* ---- journal ---- */
static uint32_t page_seq[WS_JOURNAL_PAGES];
static uint8_t pending[(JOURNAL_CAPACITY + 7) / 8];
static uint32_t head, head_slot, n_pending, n_lost, n_burned;

#define BIT(r) ((uint32_t)(r).page * JOURNAL_SLOTS_PER_PAGE + (r).slot)
static int is_pending(uint32_t i) { return pending[i >> 3] >> (i & 7) & 1; }
static void set_pending(uint32_t i, int on) {
 if (on) pending[i >> 3] |= (uint8_t)(1U << (i & 7)); else pending[i >> 3] &= (uint8_t)~(1U << (i & 7));
}
static uint32_t slot_addr(uint32_t page, uint32_t slot) {
 return WS_PAGE_ADDR(WS_JOURNAL_FIRST + page) + 8 + slot * SLOT_BYTES;
}
static uint16_t crc16(const uint8_t *d, unsigned n) {
 uint16_t c = 0xFFFF;
 while (n--) { c ^= (uint16_t)(*d++ << 8); for (int b = 0; b < 8; b++) c = (c & 0x8000) ? (uint16_t)(c << 1 ^ 0x1021) : (uint16_t)(c << 1); }
 return c;
}
static int journal_new_page(uint32_t page, uint32_t seq) {
 uint32_t dropped = 0;
 for (uint32_t s = 0; s < JOURNAL_SLOTS_PER_PAGE; s++) dropped += (uint32_t)is_pending(page * JOURNAL_SLOTS_PER_PAGE + s);
 /* persist before the page is reused; if that fails, keep the page and its records */
 if (dropped && meta_append(META_LOST, (uint64_t)lost_total + dropped)) return -1;
 for (uint32_t s = 0; s < JOURNAL_SLOTS_PER_PAGE; s++) set_pending(page * JOURNAL_SLOTS_PER_PAGE + s, 0);
 n_pending -= dropped; n_lost += dropped; lost_total += dropped;
 page_seq[page] = 0;
 if (erase_page(WS_JOURNAL_FIRST + page) || prog64(WS_PAGE_ADDR(WS_JOURNAL_FIRST + page), (uint64_t)JPG_MAGIC << 32 | seq)) return -1;
 page_seq[page] = seq;
 return 0;
}
int store_journal_init(void) {
 uint32_t best = 0; int found = 0;
 journal_ready = 0;
 memset(pending, 0, sizeof pending); n_pending = n_lost = n_burned = 0;
 for (uint32_t p = 0; p < WS_JOURNAL_PAGES; p++) {
  int bad = 0; uint64_t h = rd64(WS_PAGE_ADDR(WS_JOURNAL_FIRST + p), &bad);
  page_seq[p] = (!bad && (h >> 32) == JPG_MAGIC && (uint32_t)h) ? (uint32_t)h : 0;
  if (page_seq[p] && page_seq[p] >= best) { best = page_seq[p]; head = p; found = 1; }
 }
 if (!found) {
  head = 0; head_slot = 0;
  if (journal_new_page(0, 1)) return -1;
  journal_ready = 1;
  return 0;
 }
 for (uint32_t p = 0; p < WS_JOURNAL_PAGES; p++) {
  if (!page_seq[p]) continue;
  uint32_t last_used = 0;
  for (uint32_t s = 0; s < JOURNAL_SLOTS_PER_PAGE; s++) {
   uint32_t a = slot_addr(p, s); int bad_data = 0, bad_ack = 0, erased = 1; uint64_t d[JOURNAL_PLAIN_DW + 1], ack;
   for (uint32_t k = 0; k <= JOURNAL_PLAIN_DW; k++) { d[k] = rd64(a + 8 * k, &bad_data); erased &= d[k] == ERASED; }
   ack = rd64(a + ACK_OFF, &bad_ack);
   if (!bad_data && !bad_ack && erased && ack == ERASED) continue;
   last_used = s + 1;
   uint64_t commit = d[JOURNAL_PLAIN_DW];
   uint8_t plain[WS_OBS_PLAIN_MAX]; memcpy(plain, d, sizeof plain);
   if (bad_data || (commit >> 48) != SLOT_MAGIC || (uint16_t)(commit >> 32) != crc16(plain, sizeof plain)) { n_burned++; continue; }
   /* An ECC fault confined to the ACK word means the ACK program was interrupted; the
      host had already committed (it ACKed), so treating it as acknowledged loses nothing. */
   if (!bad_ack && ack == ERASED) { set_pending(p * JOURNAL_SLOTS_PER_PAGE + s, 1); n_pending++; }
  }
  if (p == head) head_slot = last_used;
 }
 if (head_slot >= JOURNAL_SLOTS_PER_PAGE) {
  /* The head is full, so the next page's recycle may have been cut mid-erase, which can wipe
     an ACK word but leave its record: finish the recycle before trusting that page. */
  uint32_t next = (head + 1) % WS_JOURNAL_PAGES;
  if (journal_new_page(next, page_seq[head] + 1)) return -1;
  head = next; head_slot = 0;
 }
 journal_ready = 1;
 return 0;
}
int store_journal_append(const uint8_t plain[WS_OBS_PLAIN_MAX], jref_t *ref) {
 uint64_t d[JOURNAL_PLAIN_DW] = { 0 };
 if (!meta_ready || !journal_ready) return STORE_ENOTREADY; /* a wrap persists the lost total */
 if (head_slot >= JOURNAL_SLOTS_PER_PAGE) {
  uint32_t next = (head + 1) % WS_JOURNAL_PAGES;
  if (journal_new_page(next, page_seq[head] + 1)) return -1;
  head = next; head_slot = 0;
 }
 uint32_t a = slot_addr(head, head_slot);
 ref->page = (uint16_t)head; ref->slot = (uint16_t)head_slot;
 head_slot++; /* consumed even if programming fails: never reuse a possibly torn slot */
 memcpy(d, plain, WS_OBS_PLAIN_MAX);
 for (uint32_t k = 0; k < JOURNAL_PLAIN_DW; k++)
  if (prog64(a + 8 * k, d[k])) { n_burned++; return -2; }
 if (prog64(a + COMMIT_OFF, (uint64_t)SLOT_MAGIC << 48 | (uint64_t)crc16(plain, WS_OBS_PLAIN_MAX) << 32)) { n_burned++; return -2; }
 set_pending(BIT(*ref), 1); n_pending++;
 return 0;
}
int store_journal_read(jref_t ref, uint8_t plain[WS_OBS_PLAIN_MAX]) {
 uint32_t a = slot_addr(ref.page, ref.slot); int bad = 0; uint64_t d[JOURNAL_PLAIN_DW];
 for (uint32_t k = 0; k < JOURNAL_PLAIN_DW; k++) d[k] = rd64(a + 8 * k, &bad);
 if (bad) return -1;
 memcpy(plain, d, WS_OBS_PLAIN_MAX);
 return 0;
}
int store_journal_ack(jref_t ref) {
 uint32_t i = BIT(ref);
 if (!journal_ready) return STORE_ENOTREADY;
 if (!is_pending(i)) return 0;
 if (prog64(slot_addr(ref.page, ref.slot) + ACK_OFF, 0)) return -1;
 set_pending(i, 0); n_pending--;
 return 0;
}
unsigned store_journal_oldest(jref_t *out, unsigned max, const jref_t *except) {
 unsigned n = 0;
 if (!journal_ready) return 0;
 for (uint32_t k = 1; k <= WS_JOURNAL_PAGES && n < max; k++) {
  uint32_t p = (head + k) % WS_JOURNAL_PAGES; /* oldest page first, head page last */
  if (!page_seq[p]) continue;
  for (uint32_t s = 0; s < JOURNAL_SLOTS_PER_PAGE && n < max; s++) {
   jref_t r = { (uint16_t)p, (uint16_t)s };
   if (!is_pending(BIT(r))) continue;
   if (except && except->page == r.page && except->slot == r.slot) continue;
   out[n++] = r;
  }
 }
 return n;
}
/* Shared by find and scrub: the next pending slot, from index *i on, whose identity (epoch and,
   unless any_seq, sequence: the plaintext's first 8 bytes) matches and reads back without an ECC
   fault. Returns 1 with its ref and *i just past it; 0 when no such slot is left. */
static int next_pending_match(uint32_t epoch, int any_seq, uint32_t seq, uint32_t *i, jref_t *ref) {
 uint8_t want[8];
 ws_put_be32(want, epoch); ws_put_be32(want + 4, seq);
 for (uint32_t k = *i; k < JOURNAL_CAPACITY; k++) {
  if (!is_pending(k)) continue;
  jref_t r = { (uint16_t)(k / JOURNAL_SLOTS_PER_PAGE), (uint16_t)(k % JOURNAL_SLOTS_PER_PAGE) };
  int bad = 0; uint64_t d0 = rd64(slot_addr(r.page, r.slot), &bad);
  if (!bad && !memcmp(&d0, want, any_seq ? 4U : 8U)) { *ref = r; *i = k + 1; return 1; }
 }
 return 0;
}
int store_journal_find(uint32_t epoch, uint32_t seq, jref_t *ref) {
 uint32_t i = 0;
 if (!journal_ready) return -1;
 return next_pending_match(epoch, 0, seq, &i, ref) ? 0 : -1;
}
uint32_t store_journal_pending(void) { return n_pending; }
uint32_t store_journal_lost(void) { return lost_total; } /* cumulative, persisted */
uint32_t store_journal_burned(void) { return n_burned; }
uint32_t store_ecc_faults(void) { return n_ecc; }
uint64_t store_counter_next(void) { return ctr_next; }

uint32_t store_journal_scrub(uint32_t marker)
{
 uint32_t n = 0, i = 0; jref_t r;
 if (!journal_ready) return 0;
 /* Only bad == 0 slots match; the ack clears slot r's bit, which the scan has already passed. */
 while (next_pending_match(marker, 1, 0, &i, &r))
  if (store_journal_ack(r) == 0) n++;
 return n;
}

/* WIPE erases the key and the journal but never the meta log: the transmission counter (the
 * AES-CCM nonce), the boot epoch and the lost/abandoned totals keep rising for the life of the
 * board (gap G17). A key first used under this firmware can therefore follow the board across
 * WIPEs; a key used under older firmware (which reset the counter) or on another board cannot
 * (docs/runbook-moving-boards.md). */
int store_wipe(void) {
 int rc = 0;
 journal_ready = 0; /* the RAM journal no longer describes flash: store_journal_init again */
 for (uint32_t p = 0; p < WS_JOURNAL_PAGES; p++) rc |= erase_page(WS_JOURNAL_FIRST + p);
 if (rc) return -1; /* keep the key: an unprovisioned board must not carry old records */
 return erase_page(WS_CONFIG_PAGE) ? -1 : 0;
}
