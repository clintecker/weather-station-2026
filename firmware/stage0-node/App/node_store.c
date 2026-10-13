/* Power-fail-safe node state in internal flash.
 *
 * Every record is committed by programming one final double-word after its data, so an
 * interrupted write leaves either nothing, an uncommitted slot, or a double-ECC error that
 * NMI_Handler reports through ws_flash_ecc_fault. All three read back as "not present".
 * Monotonic values only ever increase: recovery takes the maximum of everything readable. */
#include "node_store.h"
#include <string.h>
#include "stm32wlxx_hal.h"
#include "ws_frame.h"

#define ERASED 0xFFFFFFFFFFFFFFFFULL
#define CFG_MAGIC  0x57534331UL /* "WSC1" */
#define CFG_MAGIC2 0x4B435631UL /* "KCV1" */
#define META_MAGIC 0x57534D31UL /* "WSM1" */
#define JPG_MAGIC  0x57534A31UL /* "WSJ1" */
#define SLOT_MAGIC 0x4A53U
#define META_EPOCH 0xE1U
#define META_CTR   0xC2U
#define META_DWORDS (WS_PAGE_SIZE / 8U)
#define CTR_BLOCK 256U
#define SLOT_BYTES 40U

/* ---- flash primitives ---- */
static uint32_t n_ecc;
static uint64_t rd64(uint32_t addr, int *bad) {
 ws_flash_ecc_fault = 0;
 uint64_t v = *(volatile const uint64_t *)addr;
 __DSB();
 if (ws_flash_ecc_fault) { n_ecc++; if (bad) *bad = 1; return 0; }
 return v;
}
static int prog64(uint32_t addr, uint64_t v) {
 HAL_StatusTypeDef st;
 HAL_FLASH_Unlock();
 __HAL_FLASH_CLEAR_FLAG(FLASH_FLAG_ALL_ERRORS);
 st = HAL_FLASH_Program(FLASH_TYPEPROGRAM_DOUBLEWORD, addr, v);
 HAL_FLASH_Lock();
 return st == HAL_OK ? 0 : -1;
}
static int erase_page(uint32_t page) {
 FLASH_EraseInitTypeDef e = { .TypeErase = FLASH_TYPEERASE_PAGES, .Page = page, .NbPages = 1 };
 uint32_t err = 0; HAL_StatusTypeDef st;
 HAL_FLASH_Unlock();
 __HAL_FLASH_CLEAR_FLAG(FLASH_FLAG_ALL_ERRORS);
 st = HAL_FLASHEx_Erase(&e, &err);
 HAL_FLASH_Lock();
 return st == HAL_OK ? 0 : -1;
}

/* ---- provisioning ---- */
int store_config_load(uint32_t *station, uint8_t key[16]) {
 uint32_t a = WS_PAGE_ADDR(WS_CONFIG_PAGE); int bad = 0; uint8_t kcv[3];
 uint64_t d0 = rd64(a, &bad), k0 = rd64(a + 8, &bad), k1 = rd64(a + 16, &bad), d3 = rd64(a + 24, &bad);
 if (bad || (d0 >> 32) != CFG_MAGIC || (d3 >> 32) != CFG_MAGIC2) return -1;
 memcpy(key, &k0, 8); memcpy(key + 8, &k1, 8);
 if (ws_key_check(key, kcv) || (uint32_t)(d3 & 0xFFFFFFU) != ((uint32_t)kcv[0] << 16 | kcv[1] << 8 | kcv[2])) {
  memset(key, 0, 16); return -2;
 }
 *station = (uint32_t)d0;
 return 0;
}
int store_config_write(uint32_t station, const uint8_t key[16]) {
 uint32_t a = WS_PAGE_ADDR(WS_CONFIG_PAGE); uint64_t k0, k1; uint8_t kcv[3];
 for (uint32_t i = 0; i < 4; i++) if (rd64(a + 8 * i, 0) != ERASED) return -1; /* refuse overwrite */
 if (station == 0 || ws_key_check(key, kcv)) return -2;
 memcpy(&k0, key, 8); memcpy(&k1, key + 8, 8);
 /* Magic double-word last: a torn write is never mistaken for a valid config. */
 if (prog64(a + 8, k0) || prog64(a + 16, k1) ||
     prog64(a + 24, (uint64_t)CFG_MAGIC2 << 32 | (uint32_t)kcv[0] << 16 | kcv[1] << 8 | kcv[2]) ||
     prog64(a, (uint64_t)CFG_MAGIC << 32 | station)) return -3;
 return 0;
}

/* ---- monotonic meta log ---- */
static uint32_t meta_active, meta_pos, meta_gen;
static uint32_t max_epoch;
static uint64_t ctr_reserved, ctr_next;

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
 }
 return 0;
}
static int meta_append(uint32_t type, uint64_t value) {
 if (value >> 56) return -1;
 if (meta_pos >= META_DWORDS) {
  /* Compact into the other page; its header is written last so a torn compaction
     leaves the current page authoritative. */
  uint32_t other = meta_active == WS_META_PAGE_A ? WS_META_PAGE_B : WS_META_PAGE_A;
  uint32_t a = WS_PAGE_ADDR(other);
  if (erase_page(other) ||
      prog64(a + 8, (uint64_t)META_EPOCH << 56 | max_epoch) ||
      prog64(a + 16, (uint64_t)META_CTR << 56 | ctr_reserved) ||
      prog64(a, (uint64_t)META_MAGIC << 32 | (meta_gen + 1))) return -2;
  meta_active = other; meta_gen++; meta_pos = 3;
 }
 if (prog64(WS_PAGE_ADDR(meta_active) + 8 * meta_pos, (uint64_t)type << 56 | value)) { meta_pos++; return -3; }
 meta_pos++;
 return 0;
}
int store_meta_init(void) {
 uint32_t ga = 0, gb = 0, la = 0, lb = 0;
 int va, vb;
 max_epoch = 0; ctr_reserved = 0;
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
 return 0;
}
int store_next_epoch(uint32_t *epoch) {
 if (max_epoch == 0xFFFFFFFFUL) return -1;
 if (meta_append(META_EPOCH, (uint64_t)max_epoch + 1)) return -2;
 *epoch = ++max_epoch;
 return 0;
}
int store_next_counter(uint64_t *counter) {
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
 for (uint32_t s = 0; s < JOURNAL_SLOTS_PER_PAGE; s++) {
  uint32_t i = page * JOURNAL_SLOTS_PER_PAGE + s;
  if (is_pending(i)) { set_pending(i, 0); n_pending--; n_lost++; }
 }
 page_seq[page] = 0;
 if (erase_page(WS_JOURNAL_FIRST + page) || prog64(WS_PAGE_ADDR(WS_JOURNAL_FIRST + page), (uint64_t)JPG_MAGIC << 32 | seq)) return -1;
 page_seq[page] = seq;
 return 0;
}
int store_journal_init(void) {
 uint32_t best = 0; int found = 0;
 memset(pending, 0, sizeof pending); n_pending = n_lost = n_burned = 0;
 for (uint32_t p = 0; p < WS_JOURNAL_PAGES; p++) {
  int bad = 0; uint64_t h = rd64(WS_PAGE_ADDR(WS_JOURNAL_FIRST + p), &bad);
  page_seq[p] = (!bad && (h >> 32) == JPG_MAGIC && (uint32_t)h) ? (uint32_t)h : 0;
  if (page_seq[p] && page_seq[p] >= best) { best = page_seq[p]; head = p; found = 1; }
 }
 if (!found) { head = 0; head_slot = 0; return journal_new_page(0, 1); }
 for (uint32_t p = 0; p < WS_JOURNAL_PAGES; p++) {
  if (!page_seq[p]) continue;
  uint32_t last_used = 0;
  for (uint32_t s = 0; s < JOURNAL_SLOTS_PER_PAGE; s++) {
   uint32_t a = slot_addr(p, s); int bad_data = 0, bad_ack = 0; uint64_t d[4], ack;
   for (int k = 0; k < 4; k++) d[k] = rd64(a + 8 * k, &bad_data);
   ack = rd64(a + 32, &bad_ack);
   if (!bad_data && !bad_ack && d[0] == ERASED && d[1] == ERASED && d[2] == ERASED && d[3] == ERASED && ack == ERASED) continue;
   last_used = s + 1;
   uint8_t plain[24]; memcpy(plain, d, 24);
   if (bad_data || (d[3] >> 48) != SLOT_MAGIC || (uint16_t)(d[3] >> 32) != crc16(plain, 24)) { n_burned++; continue; }
   /* An ECC fault confined to the ACK word means the ACK program was interrupted; the
      host had already committed (it ACKed), so treating it as acknowledged loses nothing. */
   if (!bad_ack && ack == ERASED) { set_pending(p * JOURNAL_SLOTS_PER_PAGE + s, 1); n_pending++; }
  }
  if (p == head) head_slot = last_used;
 }
 return 0;
}
int store_journal_append(const uint8_t plain[24], jref_t *ref) {
 uint64_t d[3];
 if (head_slot >= JOURNAL_SLOTS_PER_PAGE) {
  uint32_t next = (head + 1) % WS_JOURNAL_PAGES;
  if (journal_new_page(next, page_seq[head] + 1)) return -1;
  head = next; head_slot = 0;
 }
 uint32_t a = slot_addr(head, head_slot);
 ref->page = (uint16_t)head; ref->slot = (uint16_t)head_slot;
 head_slot++; /* consumed even if programming fails: never reuse a possibly torn slot */
 memcpy(d, plain, 24);
 if (prog64(a, d[0]) || prog64(a + 8, d[1]) || prog64(a + 16, d[2]) ||
     prog64(a + 24, (uint64_t)SLOT_MAGIC << 48 | (uint64_t)crc16(plain, 24) << 32)) { n_burned++; return -2; }
 set_pending(BIT(*ref), 1); n_pending++;
 return 0;
}
int store_journal_read(jref_t ref, uint8_t plain[24]) {
 uint32_t a = slot_addr(ref.page, ref.slot); int bad = 0; uint64_t d[3];
 for (int k = 0; k < 3; k++) d[k] = rd64(a + 8 * k, &bad);
 if (bad) return -1;
 memcpy(plain, d, 24);
 return 0;
}
int store_journal_ack(jref_t ref) {
 uint32_t i = BIT(ref);
 if (!is_pending(i)) return 0;
 if (prog64(slot_addr(ref.page, ref.slot) + 32, 0)) return -1;
 set_pending(i, 0); n_pending--;
 return 0;
}
unsigned store_journal_oldest(jref_t *out, unsigned max, const jref_t *except) {
 unsigned n = 0;
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
int store_journal_find(uint32_t epoch, uint32_t seq, jref_t *ref) {
 uint8_t want[8] = { (uint8_t)(epoch >> 24), (uint8_t)(epoch >> 16), (uint8_t)(epoch >> 8), (uint8_t)epoch,
                     (uint8_t)(seq >> 24), (uint8_t)(seq >> 16), (uint8_t)(seq >> 8), (uint8_t)seq };
 for (uint32_t i = 0; i < JOURNAL_CAPACITY; i++) {
  if (!is_pending(i)) continue;
  jref_t r = { (uint16_t)(i / JOURNAL_SLOTS_PER_PAGE), (uint16_t)(i % JOURNAL_SLOTS_PER_PAGE) };
  int bad = 0; uint64_t d0 = rd64(slot_addr(r.page, r.slot), &bad);
  if (!bad && !memcmp(&d0, want, 8)) { *ref = r; return 0; }
 }
 return -1;
}
uint32_t store_journal_pending(void) { return n_pending; }
uint32_t store_journal_lost(void) { return n_lost; }
uint32_t store_journal_burned(void) { return n_burned; }
uint32_t store_ecc_faults(void) { return n_ecc; }
uint64_t store_counter_next(void) { return ctr_next; }

uint32_t store_journal_scrub(uint32_t marker)
{
 uint32_t n = 0;
 for (uint32_t i = 0; i < JOURNAL_CAPACITY; i++) {
  if (!is_pending(i)) continue;
  jref_t r = { (uint16_t)(i / JOURNAL_SLOTS_PER_PAGE), (uint16_t)(i % JOURNAL_SLOTS_PER_PAGE) };
  int bad = 0; uint64_t d0 = rd64(slot_addr(r.page, r.slot), &bad);
  uint8_t b[4]; memcpy(b, &d0, 4);
  if (!bad && ((uint32_t)b[0] << 24 | (uint32_t)b[1] << 16 | (uint32_t)b[2] << 8 | b[3]) == marker
      && store_journal_ack(r) == 0) n++;
 }
 return n;
}

int store_wipe(void) {
 int rc = erase_page(WS_CONFIG_PAGE) | erase_page(WS_META_PAGE_A) | erase_page(WS_META_PAGE_B);
 for (uint32_t p = 0; p < WS_JOURNAL_PAGES; p++) rc |= erase_page(WS_JOURNAL_FIRST + p);
 return rc ? -1 : 0;
}
