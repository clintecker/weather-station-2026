/* GENERATED from node_store.lit.md by tools/tangle.py: do not edit. Edit the document, then run
 * tools/tangle.py firmware/stage0-node/App/node_store.lit.md (tests/test_tangle.py checks this file). */
/* Power-fail-safe node state in internal flash.
 *
 * Each record ends with one commit double-word, which the writer programs after the data.
 * An interrupted write therefore leaves nothing, an uncommitted slot, or a double-word with an
 * uncorrectable error-correcting code (ECC) fault. NMI_Handler reports that fault through
 * ws_flash_ecc_fault. Boot reads all three as "not present".
 * Monotonic values only increase: recovery takes the maximum of all readable records.
 * This file does not call the hardware abstraction layer (HAL). Flash goes through the
 * ws_flash_* primitives (flash_layout.h): App/flash_stm32wl.c on the board,
 * firmware/sim_flash.c in tests/test_store_powercut.py.
 * node_store.lit.md holds the design, the layouts and the power-cut argument. This file is
 * generated from it. */
#define WS_CHECK_FILE 5
#include "node_store.h"
#include <limits.h>
#include <string.h>
#include "ws_be.h"
#include "ws_check.h"
#include "ws_frame.h"

#define ERASED 0xFFFFFFFFFFFFFFFFULL
/* Header, station, check-value and commit double-words: a 32-bit tag in the high half, a 32-bit
   value in the low half. */
static uint64_t dw_make(uint32_t hi, uint32_t lo) { return (uint64_t)hi << 32 | lo; }
static uint32_t dw_hi(uint64_t w) { return (uint32_t)(w >> 32); }
static uint32_t dw_lo(uint64_t w) { return (uint32_t)w; }
/* The address of double-word pos of a record or page that starts at base. */
static uint32_t dw_addr(uint32_t base, uint32_t pos) { return base + pos * WS_DW_BYTES; }
#define CFG_MAGIC  0x57534331UL /* "WSC1" */
#define CFG_MAGIC2 0x4B435631UL /* "KCV1" */
#define CFG_KEY_DWORDS (WS_KEY_LEN / WS_DW_BYTES)
enum { CFG_ID_POS, CFG_KEY_POS, CFG_KCV_POS = CFG_KEY_POS + CFG_KEY_DWORDS, CFG_DWORDS };
_Static_assert(WS_KEY_LEN % WS_DW_BYTES == 0, "the key fills whole double-words");
/* The 3-byte key check value as the low bits of a 32-bit number, big-endian like its hex form. */
static uint32_t kcv_value(const uint8_t kcv[WS_KCV_LEN]) { return (uint32_t)ws_get_be64(kcv, WS_KCV_LEN); }
#define META_MAGIC 0x57534D31UL /* "WSM1" */
#define META_EPOCH 0xE1U
#define META_CTR   0xC2U
#define META_LOST  0xD1U /* cumulative journal overflow losses */
#define META_ABAND 0xD2U /* cumulative abandoned records (NACK / strike limit) */
#define META_RAIN  0xA1U /* the rain module setting: bit 0 on, latest wins through a rising value */
#define META_TYPE_SHIFT 56U                                  /* type: bits 63-56, value: bits 55-0 */
#define META_VALUE_MAX ((1ULL << META_TYPE_SHIFT) - 1U)
#define META_DWORDS (WS_PAGE_SIZE / WS_DW_BYTES)
#define META_FIRST_POS 1U   /* position 0 is the page header */
#define META_FIRST_GEN 1U
#define CTR_BLOCK 256U
static uint64_t meta_word(uint32_t type, uint64_t value) { return (uint64_t)type << META_TYPE_SHIFT | value; }
#define JPG_MAGIC  (0x57534A00UL | JOURNAL_SLOT_BYTES) /* "WSJ" + slot size: another layout is ignored */
#define SLOT_MAGIC 0x4A53U
#define JOURNAL_FIRST_SEQ 1U   /* page sequence 0 marks "not a journal page" */

/* Geometry the on-flash format depends on (node_store.h). Positions are double-words in a slot. */
#define SLOT_BYTES JOURNAL_SLOT_BYTES
#define COMMIT_POS JOURNAL_PLAIN_DW
#define ACK_POS (COMMIT_POS + 1U)
_Static_assert(SLOT_BYTES == (ACK_POS + 1U) * WS_DW_BYTES && COMMIT_POS * WS_DW_BYTES >= WS_OBS_PLAIN_MAX,
               "slot = plaintext rounded to double-words + commit + ack double-words");
_Static_assert(SLOT_BYTES <= UINT8_MAX, "the slot size fits in the page magic's low byte");
_Static_assert(JOURNAL_SLOTS_PER_PAGE >= 1U && JOURNAL_HDR_BYTES + JOURNAL_SLOTS_PER_PAGE * SLOT_BYTES <= WS_PAGE_SIZE,
               "journal slots fit in one page");
_Static_assert(WS_OBS_ID_LEN <= WS_DW_BYTES, "a record's identity is in its first double-word");
_Static_assert((uint64_t)WS_STATE_FIRST * WS_PAGE_SIZE >= WS_FIRMWARE_BYTES, "node state sits above the firmware region");
_Static_assert(WS_JOURNAL_FIRST + WS_JOURNAL_PAGES == WS_META_PAGE_A && WS_META_PAGE_A < WS_META_PAGE_B &&
               WS_META_PAGE_B < WS_CONFIG_PAGE && WS_CONFIG_PAGE == WS_FLASH_PAGES - 1U,
               "journal, meta and config pages are distinct, in order, and end at the last page");
_Static_assert(WS_JOURNAL_PAGES >= 2U, "the journal ring has at least two pages");
#ifdef WS_JOURNAL_DEFAULT
/* The board's ring keeps 24 h of this build's widest record (WS_OBS_PLAIN_MAX, from WS_NODE_FIELDS).
   One page is always being recycled, so it does not count. This is the per-build ceiling: a field
   set above 80 B of plaintext (a 96 B frame) does not compile. */
_Static_assert((WS_JOURNAL_PAGES - 1U) * JOURNAL_SLOTS_PER_PAGE >= 24U * 60U,
               "the journal keeps 24 hours of the build's widest record");
#endif
_Static_assert(WS_JOURNAL_PAGES <= UINT16_MAX && JOURNAL_SLOTS_PER_PAGE <= UINT16_MAX, "jref_t page and slot are 16-bit");

/* ---- flash primitives (flash_layout.h) ---- */
static uint32_t n_ecc;
static uint64_t rd64(uint32_t addr, int *bad) {
 uint64_t v;
 if (ws_flash_read64(addr, &v)) { n_ecc++; if (bad) *bad = 1; return 0; }
 return v;
}
/* Every write stays inside the node-state pages (journal, meta and config, flash_layout.h).
   No write reaches the firmware below them. A bad address or page fails like a flash error. */
#define STORE_PAGE_FIRST WS_STATE_FIRST
#define STORE_PAGE_END WS_FLASH_PAGES
static int prog64(uint32_t addr, uint64_t v) {
 if (!WS_CHECK(addr >= WS_PAGE_ADDR(STORE_PAGE_FIRST) && addr < WS_PAGE_ADDR(STORE_PAGE_END) && addr % WS_DW_BYTES == 0))
  return STORE_EFLASH;
 return ws_flash_prog64(addr, v) ? STORE_EFLASH : STORE_OK;
}
static int erase_page(uint32_t page) {
 if (!WS_CHECK(page >= STORE_PAGE_FIRST && page < STORE_PAGE_END)) return STORE_EFLASH;
 return ws_flash_erase(page) ? STORE_EFLASH : STORE_OK;
}

/* The mutators refuse to run on RAM state that no successful init built. Otherwise they
   could append at a stale position. */
static uint8_t meta_ready, journal_ready;

/* ---- provisioning ---- */
int store_config_load(uint32_t *station, uint8_t key[WS_KEY_LEN], uint8_t kcv_out[WS_KCV_LEN]) {
 uint32_t a = WS_PAGE_ADDR(WS_CONFIG_PAGE); int bad = 0; uint8_t kcv[WS_KCV_LEN]; uint64_t k[CFG_KEY_DWORDS];
 uint64_t id = rd64(dw_addr(a, CFG_ID_POS), &bad), check = rd64(dw_addr(a, CFG_KCV_POS), &bad);
 for (uint32_t i = 0; i < CFG_KEY_DWORDS; i++) k[i] = rd64(dw_addr(a, CFG_KEY_POS + i), &bad);
 memcpy(key, k, WS_KEY_LEN); ws_wipe(k, sizeof k);
 int rc = bad || dw_hi(id) != CFG_MAGIC || dw_hi(check) != CFG_MAGIC2 ? STORE_ENODATA
        : ws_key_check(key, kcv) || dw_lo(check) != kcv_value(kcv) ? STORE_EKEY
        : dw_lo(id) == 0 || dw_lo(id) > WS_STATION_MAX ? STORE_ERANGE : STORE_OK;
 if (rc) { ws_wipe(key, WS_KEY_LEN); return rc; }
 *station = dw_lo(id);
 memcpy(kcv_out, kcv, WS_KCV_LEN);
 return STORE_OK;
}
/* 1 if every double-word of the record is erased (a programmed one cannot be programmed again). */
static int cfg_erased(uint32_t a) {
 for (uint32_t i = 0; i < CFG_DWORDS; i++) if (rd64(dw_addr(a, i), 0) != ERASED) return 0;
 return 1;
}
int store_config_write(uint32_t station, const uint8_t key[WS_KEY_LEN], uint8_t kcv[WS_KCV_LEN]) {
 uint32_t a = WS_PAGE_ADDR(WS_CONFIG_PAGE); uint64_t k[CFG_KEY_DWORDS]; int rc = STORE_OK;
 if (!cfg_erased(a)) return STORE_EEXISTS; /* WIPE must erase the page first */
 if (station == 0 || station > WS_STATION_MAX) return STORE_ERANGE;
 if (ws_key_check(key, kcv)) return STORE_EKEY;
 memcpy(k, key, sizeof k);
 for (uint32_t i = 0; i < CFG_KEY_DWORDS && !rc; i++) rc = prog64(dw_addr(a, CFG_KEY_POS + i), k[i]);
 ws_wipe(k, sizeof k);
 /* The station double-word goes last because it commits the record. */
 if (rc || prog64(dw_addr(a, CFG_KCV_POS), dw_make(CFG_MAGIC2, kcv_value(kcv))) ||
     prog64(dw_addr(a, CFG_ID_POS), dw_make(CFG_MAGIC, station))) return STORE_EFLASH;
 return STORE_OK;
}

/* ---- monotonic meta log ---- */
static uint32_t meta_active, meta_pos, meta_gen;
static uint32_t max_epoch;
static uint64_t ctr_reserved, ctr_next;
static uint32_t lost_total, abandoned_total;
static uint32_t rain_setting;

/* A 32-bit total only moves up, and only to a value that fits. */
static void raise32(uint32_t *total, uint64_t val) {
 if (val > *total && val <= UINT32_MAX) *total = (uint32_t)val;
}
/* Folds one readable meta record into the RAM maxima. It ignores unknown types. */
static void meta_absorb(uint64_t v) {
 uint64_t val = v & META_VALUE_MAX;
 switch (v >> META_TYPE_SHIFT) {
 case META_EPOCH: raise32(&max_epoch, val); break;
 case META_CTR: if (val > ctr_reserved) ctr_reserved = val; break;
 case META_LOST: raise32(&lost_total, val); break;
 case META_ABAND: raise32(&abandoned_total, val); break;
 case META_RAIN: raise32(&rain_setting, val); break;
 default: break;
 }
}
static int meta_scan(uint32_t page, uint32_t *gen, uint32_t *last) {
 uint32_t a = WS_PAGE_ADDR(page); int bad = 0;
 uint64_t h = rd64(a, &bad);
 if (bad || dw_hi(h) != META_MAGIC) return STORE_ENODATA;
 *gen = dw_lo(h); *last = 0;
 for (uint32_t i = META_FIRST_POS; i < META_DWORDS; i++) {
  int b = 0; uint64_t v = rd64(dw_addr(a, i), &b);
  if (!b && v == ERASED) continue;
  *last = i; /* an unreadable double-word still occupies its position */
  if (!b) meta_absorb(v);
 }
 return STORE_OK;
}
/* Compacts into the other page. It writes that page's header last, so a cut compaction
   leaves the current page authoritative. The other page still carries an older valid header.
   The code zeroes that header first, which the flash allows over written data. A cut during
   the erase then cannot leave half-erased values under a header that boot trusts. */
static int meta_compact(void) {
 uint32_t other = meta_active == WS_META_PAGE_A ? WS_META_PAGE_B : WS_META_PAGE_A;
 uint32_t a = WS_PAGE_ADDR(other);
 const uint64_t rec[] = { meta_word(META_EPOCH, max_epoch), meta_word(META_CTR, ctr_reserved),
                          meta_word(META_LOST, lost_total), meta_word(META_ABAND, abandoned_total),
                          meta_word(META_RAIN, rain_setting) };
 int bad = 0;
 if (rd64(a, &bad) != ERASED && prog64(a, 0)) return STORE_EFLASH;
 if (erase_page(other)) return STORE_EFLASH;
 for (uint32_t k = 0; k < sizeof rec / sizeof rec[0]; k++) if (prog64(dw_addr(a, META_FIRST_POS + k), rec[k])) return STORE_EFLASH;
 if (prog64(a, dw_make(META_MAGIC, meta_gen + 1))) return STORE_EFLASH;
 meta_active = other; meta_gen++; meta_pos = META_FIRST_POS + sizeof rec / sizeof rec[0];
 return STORE_OK;
}
static int meta_append(uint32_t type, uint64_t value) {
 if (value > META_VALUE_MAX) return STORE_ERANGE;
 if (meta_pos >= META_DWORDS && meta_compact()) return STORE_EFLASH;
 int rc = prog64(dw_addr(WS_PAGE_ADDR(meta_active), meta_pos), meta_word(type, value));
 meta_pos++; /* a failed program may have torn the double-word: never reuse it */
 return rc ? STORE_EFLASH : STORE_OK;
}
int store_meta_init(void) {
 uint32_t ga = 0, gb = 0, la = 0, lb = 0;
 int va, vb;
 meta_ready = 0;
 max_epoch = 0; ctr_reserved = 0; lost_total = 0; abandoned_total = 0; rain_setting = 0;
 va = meta_scan(WS_META_PAGE_A, &ga, &la) == STORE_OK;
 vb = meta_scan(WS_META_PAGE_B, &gb, &lb) == STORE_OK;
 if (!va && !vb) {
  if (erase_page(WS_META_PAGE_A) || prog64(WS_PAGE_ADDR(WS_META_PAGE_A), dw_make(META_MAGIC, META_FIRST_GEN))) return STORE_EFLASH;
  meta_active = WS_META_PAGE_A; meta_gen = META_FIRST_GEN; meta_pos = META_FIRST_POS;
 } else if (va && (!vb || ga > gb)) {
  meta_active = WS_META_PAGE_A; meta_gen = ga; meta_pos = la + 1;
 } else {
  meta_active = WS_META_PAGE_B; meta_gen = gb; meta_pos = lb + 1;
 }
 ctr_next = ctr_reserved + 1; /* skips any counter that the node may have used before the reset */
 meta_ready = 1;
 return STORE_OK;
}
int store_next_epoch(uint32_t *epoch) {
 if (!meta_ready) return STORE_ENOTREADY;
 /* A real boot never gets STORE_EPOCH_RESERVED. The bench storm test uses that epoch, and the
    boot scrub acknowledges its records. */
 if (max_epoch >= STORE_EPOCH_RESERVED - 1U) return STORE_EEXHAUSTED;
 int rc = meta_append(META_EPOCH, (uint64_t)max_epoch + 1);
 if (rc) return rc;
 *epoch = ++max_epoch;
 return STORE_OK;
}
/* After a WIPE, the gateway supplies a floor above every epoch it has stored. New observation
   identities then cannot collide with stored ones. The epoch only moves up. */
int store_epoch_floor(uint32_t floor) {
 if (!meta_ready) return STORE_ENOTREADY;
 if (floor <= max_epoch) return STORE_OK;
 int rc = meta_append(META_EPOCH, floor);
 if (rc) return rc;
 max_epoch = floor;
 return STORE_OK;
}
int store_note_abandoned(void) {
 if (!meta_ready) return STORE_ENOTREADY;
 int rc = meta_append(META_ABAND, (uint64_t)abandoned_total + 1);
 if (rc) return rc;
 abandoned_total++;
 return STORE_OK;
}
uint32_t store_abandoned_total(void) { return abandoned_total; }

int store_rain_set(int on) {
 if (!meta_ready) return STORE_ENOTREADY;
 if ((rain_setting & 1U) == (on ? 1U : 0U)) return STORE_OK;
 if (rain_setting == UINT32_MAX) return STORE_EEXHAUSTED;
 int rc = meta_append(META_RAIN, (uint64_t)rain_setting + 1);
 if (rc) return rc;
 rain_setting++;
 return STORE_OK;
}
int store_rain_enabled(void) { return (int)(rain_setting & 1U); }

int store_next_counter(uint64_t *counter) {
 if (!meta_ready) return STORE_ENOTREADY;
 /* The header carries 40 bits. It would truncate a larger counter and repeat a nonce. */
 if (ctr_next > WS_COUNTER_MAX) return STORE_EEXHAUSTED;
 if (ctr_next > ctr_reserved) {
  uint64_t upto = ctr_reserved + CTR_BLOCK;
  int rc = meta_append(META_CTR, upto);
  if (rc) return rc; /* no durable reservation, no counter */
  ctr_reserved = upto;
 }
 *counter = ctr_next++;
 return STORE_OK;
}

/* ---- journal ---- */
static uint32_t page_seq[WS_JOURNAL_PAGES];
static uint8_t pending[(JOURNAL_CAPACITY + CHAR_BIT - 1) / CHAR_BIT];   /* one bit per slot */
static uint32_t head, head_slot, n_pending, n_lost, n_burned;

static uint32_t slot_index(jref_t r) { return (uint32_t)r.page * JOURNAL_SLOTS_PER_PAGE + r.slot; }
static int is_pending(uint32_t i) { return pending[i / CHAR_BIT] >> (i % CHAR_BIT) & 1U; }
static void set_pending(uint32_t i, int on) {
 uint8_t bit = (uint8_t)(1U << (i % CHAR_BIT));
 if (on) pending[i / CHAR_BIT] |= bit; else pending[i / CHAR_BIT] &= (uint8_t)~bit;
}
static uint32_t slot_addr(uint32_t page, uint32_t slot) {
 return WS_PAGE_ADDR(WS_JOURNAL_FIRST + page) + JOURNAL_HDR_BYTES + slot * SLOT_BYTES;
}
#define CRC16_INIT 0xFFFFU   /* CRC-16/CCITT-FALSE */
#define CRC16_POLY 0x1021U
#define CRC16_TOP  0x8000U
static uint16_t crc16(const uint8_t *d, unsigned n) {
 uint16_t c = CRC16_INIT;
 /* bound: n bytes (WS_OBS_PLAIN_MAX from the only caller), CHAR_BIT bits each */
 while (n--) {
  c ^= (uint16_t)(*d++ << CHAR_BIT);
  for (int b = 0; b < CHAR_BIT; b++) c = (c & CRC16_TOP) ? (uint16_t)(c << 1 ^ CRC16_POLY) : (uint16_t)(c << 1);
 }
 return c;
}
/* The commit double-word: the high half is the slot magic (bits 31-16) and the plaintext's CRC
   (bits 15-0). The low half is zero. */
static uint64_t slot_commit_word(const uint8_t plain[WS_OBS_PLAIN_MAX]) {
 return dw_make((uint32_t)SLOT_MAGIC << 16 | crc16(plain, WS_OBS_PLAIN_MAX), 0);
}
static int journal_new_page(uint32_t page, uint32_t seq) {
 uint32_t dropped = 0;
 for (uint32_t s = 0; s < JOURNAL_SLOTS_PER_PAGE; s++) dropped += (uint32_t)is_pending(page * JOURNAL_SLOTS_PER_PAGE + s);
 /* persist the loss before the page is reused. On failure keep the page and its records. */
 int rc = dropped ? meta_append(META_LOST, (uint64_t)lost_total + dropped) : STORE_OK;
 if (rc) return rc;
 for (uint32_t s = 0; s < JOURNAL_SLOTS_PER_PAGE; s++) set_pending(page * JOURNAL_SLOTS_PER_PAGE + s, 0);
 n_pending -= dropped; n_lost += dropped; lost_total += dropped;
 page_seq[page] = 0;
 if (erase_page(WS_JOURNAL_FIRST + page) || prog64(WS_PAGE_ADDR(WS_JOURNAL_FIRST + page), dw_make(JPG_MAGIC, seq))) return STORE_EFLASH;
 page_seq[page] = seq;
 return STORE_OK;
}
/* Opens a fresh page after the head once the head is full (append, and init after a cut). */
static int journal_advance_if_full(void) {
 if (head_slot < JOURNAL_SLOTS_PER_PAGE) return STORE_OK;
 uint32_t next = (head + 1) % WS_JOURNAL_PAGES;
 int rc = journal_new_page(next, page_seq[head] + 1);
 if (rc) return rc;
 head = next; head_slot = 0;
 return STORE_OK;
}
/* Reads every page header into page_seq (0: not a journal page) and points head at the
   highest sequence, the later page on a tie. Returns 0 when no page is a journal page. */
static int journal_find_head(void) {
 uint32_t best = 0; int found = 0;
 for (uint32_t p = 0; p < WS_JOURNAL_PAGES; p++) {
  int bad = 0; uint64_t h = rd64(WS_PAGE_ADDR(WS_JOURNAL_FIRST + p), &bad);
  page_seq[p] = !bad && dw_hi(h) == JPG_MAGIC ? dw_lo(h) : 0;
  if (page_seq[p] && page_seq[p] >= best) { best = page_seq[p]; head = p; found = 1; }
 }
 return found;
}
/* Boot scan of one slot. Returns 0 if the slot is blank, else 1. It counts a slot with torn or
   unreadable data as burned, and a committed slot without an ACK as pending. */
static int journal_scan_slot(uint32_t p, uint32_t s) {
 uint32_t a = slot_addr(p, s); int bad_data = 0, bad_ack = 0, erased = 1; uint64_t d[COMMIT_POS + 1], ack;
 for (uint32_t k = 0; k <= COMMIT_POS; k++) { d[k] = rd64(dw_addr(a, k), &bad_data); erased &= d[k] == ERASED; }
 ack = rd64(dw_addr(a, ACK_POS), &bad_ack);
 if (!bad_data && !bad_ack && erased && ack == ERASED) return 0;
 uint8_t plain[WS_OBS_PLAIN_MAX]; memcpy(plain, d, sizeof plain);
 /* A torn ACK word (ECC fault) means a cut stopped the ACK program after the gateway stored
    the record. So the slot counts as acknowledged. */
 if (bad_data || dw_hi(d[COMMIT_POS]) != dw_hi(slot_commit_word(plain))) n_burned++;
 else if (!bad_ack && ack == ERASED) { set_pending(p * JOURNAL_SLOTS_PER_PAGE + s, 1); n_pending++; }
 return 1;
}
/* Scans the slots of a journal page. Returns one past the last used slot (0 if none). */
static uint32_t journal_scan_page(uint32_t p) {
 uint32_t last_used = 0;
 for (uint32_t s = 0; s < JOURNAL_SLOTS_PER_PAGE; s++) if (journal_scan_slot(p, s)) last_used = s + 1;
 return last_used;
}
int store_journal_init(void) {
 journal_ready = 0;
 memset(pending, 0, sizeof pending); n_pending = n_lost = n_burned = 0;
 if (!journal_find_head()) {
  head = 0; head_slot = 0;
  int rc = journal_new_page(0, JOURNAL_FIRST_SEQ);
  if (rc) return rc;
  journal_ready = 1;
  return STORE_OK;
 }
 for (uint32_t p = 0; p < WS_JOURNAL_PAGES; p++) {
  if (!page_seq[p]) continue;
  uint32_t last_used = journal_scan_page(p);
  if (p == head) head_slot = last_used;
 }
 /* A full head means that a cut may have stopped the next page's recycle during its erase.
    That erase can clear an ACK word and keep its record. Finish the recycle first. */
 int rc = journal_advance_if_full();
 if (rc) return rc;
 journal_ready = 1;
 return STORE_OK;
}
int store_journal_append(const uint8_t plain[WS_OBS_PLAIN_MAX], jref_t *ref) {
 uint64_t d[JOURNAL_PLAIN_DW] = { 0 };
 if (!meta_ready || !journal_ready) return STORE_ENOTREADY; /* a wrap persists the lost total */
 int rc = journal_advance_if_full();
 if (rc) return rc;
 uint32_t a = slot_addr(head, head_slot);
 ref->page = (uint16_t)head; ref->slot = (uint16_t)head_slot;
 head_slot++; /* consumed even if programming fails: never reuse a possibly torn slot */
 memcpy(d, plain, WS_OBS_PLAIN_MAX);
 for (uint32_t k = 0; k < JOURNAL_PLAIN_DW; k++)
  if (prog64(dw_addr(a, k), d[k])) { n_burned++; return STORE_EFLASH; }
 if (prog64(dw_addr(a, COMMIT_POS), slot_commit_word(plain))) { n_burned++; return STORE_EFLASH; }
 set_pending(slot_index(*ref), 1); n_pending++;
 return STORE_OK;
}
/* A jref_t comes only from this file (append, oldest, find): always a slot of the journal. */
static int ref_in_journal(jref_t r) { return r.page < WS_JOURNAL_PAGES && r.slot < JOURNAL_SLOTS_PER_PAGE; }
int store_journal_read(jref_t ref, uint8_t plain[WS_OBS_PLAIN_MAX]) {
 if (!WS_CHECK(ref_in_journal(ref))) return STORE_EINVAL;
 uint32_t a = slot_addr(ref.page, ref.slot); int bad = 0; uint64_t d[JOURNAL_PLAIN_DW];
 for (uint32_t k = 0; k < JOURNAL_PLAIN_DW; k++) d[k] = rd64(dw_addr(a, k), &bad);
 if (bad) return STORE_ENODATA;
 memcpy(plain, d, WS_OBS_PLAIN_MAX);
 return STORE_OK;
}
int store_journal_ack(jref_t ref) {
 if (!journal_ready) return STORE_ENOTREADY;
 if (!WS_CHECK(ref_in_journal(ref))) return STORE_EINVAL;   /* before it indexes pending[] */
 uint32_t i = slot_index(ref);
 if (!is_pending(i)) return STORE_OK;
 if (prog64(dw_addr(slot_addr(ref.page, ref.slot), ACK_POS), 0)) return STORE_EFLASH;
 set_pending(i, 0); n_pending--;
 return STORE_OK;
}
/* Appends page p's pending refs, in slot order and skipping 'except', to out[n..max). */
static unsigned page_pending(uint32_t p, jref_t *out, unsigned n, unsigned max, const jref_t *except) {
 for (uint32_t s = 0; s < JOURNAL_SLOTS_PER_PAGE && n < max; s++) {
  jref_t r = { (uint16_t)p, (uint16_t)s };
  if (!is_pending(slot_index(r))) continue;
  if (except && except->page == r.page && except->slot == r.slot) continue;
  out[n++] = r;
 }
 return n;
}
unsigned store_journal_oldest(jref_t *out, unsigned max, const jref_t *except) {
 unsigned n = 0;
 if (!journal_ready) return 0;
 for (uint32_t k = 1; k <= WS_JOURNAL_PAGES && n < max; k++) {
  uint32_t p = (head + k) % WS_JOURNAL_PAGES; /* oldest page first, head page last */
  if (page_seq[p]) n = page_pending(p, out, n, max, except);
 }
 return n;
}
/* Shared by find and scrub. Finds the next pending slot, from index *i on, that reads back
   without an ECC fault and whose identity matches. The identity is the plaintext's first
   WS_OBS_ID_LEN bytes: the epoch, then the sequence. With any_seq set, only the epoch counts.
   Returns 1 with the slot's ref and *i just past the slot. Returns 0 when no such slot is left. */
static int next_pending_match(uint32_t epoch, int any_seq, uint32_t seq, uint32_t *i, jref_t *ref) {
 uint8_t want[WS_OBS_ID_LEN];
 ws_put_be32(want, epoch); ws_put_be32(want + WS_OBS_EPOCH_LEN, seq);
 for (uint32_t k = *i; k < JOURNAL_CAPACITY; k++) {
  if (!is_pending(k)) continue;
  jref_t r = { (uint16_t)(k / JOURNAL_SLOTS_PER_PAGE), (uint16_t)(k % JOURNAL_SLOTS_PER_PAGE) };
  int bad = 0; uint64_t d0 = rd64(slot_addr(r.page, r.slot), &bad);
  if (!bad && !memcmp(&d0, want, any_seq ? WS_OBS_EPOCH_LEN : WS_OBS_ID_LEN)) { *ref = r; *i = k + 1; return 1; }
 }
 return 0;
}
int store_journal_find(uint32_t epoch, uint32_t seq, jref_t *ref) {
 uint32_t i = 0;
 if (!journal_ready) return STORE_ENOTREADY;
 return next_pending_match(epoch, 0, seq, &i, ref) ? STORE_OK : STORE_ENODATA;
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
 /* Only slots without an ECC fault match. The ack clears the bit of slot r, which the search
    has already passed. Each match moves i past its slot. No match exists at or past
    JOURNAL_CAPACITY. Therefore: */
 /* bound: at most JOURNAL_CAPACITY passes */
 while (next_pending_match(marker, 1, 0, &i, &r))
  if (store_journal_ack(r) == 0) n++;
 return n;
}

/* WIPE erases the key and the journal but never the meta log: the counter (the AES-CCM
 * nonce), the boot epoch and the lost/abandoned totals keep rising for the life of the board. */
int store_wipe(void) {
 int rc = STORE_OK;
 journal_ready = 0; /* RAM no longer describes flash: call store_journal_init again */
 for (uint32_t p = 0; p < WS_JOURNAL_PAGES; p++) rc |= erase_page(WS_JOURNAL_FIRST + p);
 if (rc) return STORE_EFLASH; /* keep the key: an unprovisioned board must not carry old records */
 return erase_page(WS_CONFIG_PAGE);
}
