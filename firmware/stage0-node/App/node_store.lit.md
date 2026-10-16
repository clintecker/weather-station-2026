# node_store: durable node state

`node_store.c` keeps the TX node's durable state in the STM32WL55's internal flash: the
provisioning record (station id and AES key), the monotonic values (boot epoch, transmission
counter, lost and abandoned totals) and the journal of observations not yet acknowledged by the
gateway. Every function in it tolerates a power cut at any flash operation.

This document is the source. `tools/tangle.py` generates `node_store.c` from the code chunks
below. The generated file is committed, so the build, the static analysers and the host tests
read ordinary C. Edit this file, then regenerate and check:

```sh
python3 tools/tangle.py firmware/stage0-node/App/node_store.lit.md                     # write node_store.c
python3 tools/tangle.py --check                                                      # CI: committed .c == tangle
python3 tools/tangle.py --weave /tmp/node_store.html firmware/stage0-node/App/node_store.lit.md   # render
```

A chunk is a fenced ` ```c {#name} ` block. A line `<<name>>` inside a chunk includes chunk
`name`. Chunks appear in reading order. The root chunk (section 8) puts them in C order.

## 1. Guarantees

After a power cut at any flash operation, followed by a reboot:

| State | Guarantee | Checked by (`firmware/test_store.c`) |
|---|---|---|
| Provisioning | the record last written completely, or none | `config_wrong`, `config_lost` |
| Epoch, counter | never at or below a value already returned | `epoch_repeat`, `counter_repeat` |
| Lost, abandoned totals | never lower than a value already reported | `lost_decreased`, `abandoned_decreased` |
| Journal | an acknowledged record is not pending again. A pending record that disappears is counted in the lost total | `acked_returned`, `pending_uncounted` |
| WIPE | an interrupted WIPE never leaves an unprovisioned board holding pending records | `wipe_journal_survives` |
| Flash use | no program over a double-word that is not erased | `sim_violation` |

The counter is the AES-CCM nonce under a key that survives reflashing and WIPE (section 7). A
repeated counter under one key breaks confidentiality and authenticity of both frames, so the
counter guarantee has no exceptions. The others bound data loss.

## 2. Flash model

The STM32WL55JC has 128 pages of 2 KB, single bank (RM0453 section 3.3). `firmware/sim_flash.c`
models the operations this file uses:

| Operation | Effect | After a cut during it |
|---|---|---|
| Erase one page (~22 ms) | every double-word reads `0xFFFF FFFF FFFF FFFF` | some double-words erased, some old, some unreadable |
| Program one double-word (~82 µs) | 8 bytes, 8-byte aligned, once per erase | the old (erased) value, the new value, or a torn value |
| Program zeros over written data | allowed (RM0453, PROGERR exception) | as above |
| Read one double-word | the value | a torn double-word fails ECC: the NMI handler sets `ws_flash_ecc_fault`, the read returns nonzero |

A read therefore has three outcomes: erased, a value, or unreadable. Every decision below states
what it does with an unreadable double-word.

Page map (`flash_layout.h`):

| Pages | Contents |
|---|---|
| 0–31 | firmware (64 KB, the linker script enforces the limit) |
| 32 | provisioning record |
| 33, 34 | meta log A and B |
| 35–127 | journal, a ring of 93 pages |

## 3. Recovery rules

Two rules cover every record:

1. **Commit word last.** A record is complete when its commit double-word is programmed, and that
   double-word is programmed after all others. A cut leaves nothing, data without a commit, or a
   torn double-word. Boot treats all three as "record absent".
2. **Maximum of readable values.** A monotonic value is stored as records that only raise it. Boot
   takes the maximum over every readable record, so a lost record lowers nothing it has already
   returned. Every value is persisted before it is returned (section 5).

The generated file opens with the same summary:

```c {#abstract}
/* Power-fail-safe node state in internal flash.
 *
 * Every record is committed by programming one final double-word after its data, so an
 * interrupted write leaves either nothing, an uncommitted slot, or a double-ECC error that
 * NMI_Handler reports through ws_flash_ecc_fault. All three read back as "not present".
 * Monotonic values only ever increase: recovery takes the maximum of everything readable.
 * No HAL here: flash goes through the ws_flash_* primitives (flash_layout.h: App/flash_stm32wl.c on
 * the board, firmware/sim_flash.c in tests/test_store_powercut.py). The design, the layouts and
 * the power-cut argument are in node_store.lit.md, which this file is generated from. */
```

### Return codes

Every function returns `STORE_OK` (0) or a negative `STORE_E*` code from `node_store.h`.
Callers only test for nonzero. The value appears in `#error` lines.

| Code | Value | Meaning |
|---|---|---|
| `STORE_EFLASH` | -1 | a program or erase failed, or `prog64`/`erase_page` refused the address |
| `STORE_ENODATA` | -2 | no valid record: erased, unreadable or not committed; or not found |
| `STORE_EKEY` | -3 | the key check value cannot be computed, or does not match |
| `STORE_ERANGE` | -4 | station id or meta value out of range |
| `STORE_EEXISTS` | -5 | the provisioning page is not erased |
| `STORE_EEXHAUSTED` | -6 | no epoch or counter left |
| `STORE_EINVAL` | -7 | a `jref_t` this file did not issue (`WS_CHECK` records the site) |
| `STORE_ENOTREADY` | -16 | init has not succeeded |

### Flash access

`rd64` returns 0 and sets `*bad` on an ECC fault. `bad` stays set, so a caller can read several
double-words and test once. `n_ecc` counts faults since boot (`store_ecc_faults()`). A nonzero
count after boot means a cut tore a double-word.

```c {#erased}
#define ERASED 0xFFFFFFFFFFFFFFFFULL
/* Header, station, check-value and commit double-words: a 32-bit tag in the high half, a 32-bit
   value in the low half. */
static uint64_t dw_make(uint32_t hi, uint32_t lo) { return (uint64_t)hi << 32 | lo; }
static uint32_t dw_hi(uint64_t w) { return (uint32_t)(w >> 32); }
static uint32_t dw_lo(uint64_t w) { return (uint32_t)w; }
/* The address of double-word pos of a record or page that starts at base. */
static uint32_t dw_addr(uint32_t base, uint32_t pos) { return base + pos * WS_DW_BYTES; }
```

```c {#flash-primitives}
/* ---- flash primitives (flash_layout.h) ---- */
static uint32_t n_ecc;
static uint64_t rd64(uint32_t addr, int *bad) {
 uint64_t v;
 if (ws_flash_read64(addr, &v)) { n_ecc++; if (bad) *bad = 1; return 0; }
 return v;
}
<<write-guards>>
```

`prog64` and `erase_page` refuse any address outside pages 32–127, or a misaligned program, with
a `WS_CHECK` (`firmware/common/ws_check.h`). The refusal returns `STORE_EFLASH`, the same as a failed
flash operation, which every caller handles. A wrong address can only come from a bug in this file. The
check stops such a bug from erasing firmware pages.

```c {#write-guards}
/* Every write stays inside the node-state pages (config, meta, journal; flash_layout.h): never the
   firmware below them. A bad address or page is refused like a failed flash operation. */
#define STORE_PAGE_END (WS_JOURNAL_FIRST + WS_JOURNAL_PAGES)
static int prog64(uint32_t addr, uint64_t v) {
 if (!WS_CHECK(addr >= WS_PAGE_ADDR(WS_CONFIG_PAGE) && addr < WS_PAGE_ADDR(STORE_PAGE_END) && addr % WS_DW_BYTES == 0))
  return STORE_EFLASH;
 return ws_flash_prog64(addr, v) ? STORE_EFLASH : STORE_OK;
}
static int erase_page(uint32_t page) {
 if (!WS_CHECK(page >= WS_CONFIG_PAGE && page < STORE_PAGE_END)) return STORE_EFLASH;
 return ws_flash_erase(page) ? STORE_EFLASH : STORE_OK;
}
```

Mutators require the RAM state that a successful `store_meta_init` or `store_journal_init` built.
Without it they return `STORE_ENOTREADY` (`node_store.h`) and write nothing (review P3), so a failed
boot scan cannot lead to appends at a stale position.

```c {#ready-flags}
/* store_ready guard (review P3): mutators refuse to run on RAM state that no successful init
   produced, instead of appending at a stale position. */
static uint8_t meta_ready, journal_ready;
```

## 4. Provisioning record

Page 32 holds one record of four double-words:

| Position | Name | Contents |
|---|---|---|
| 0 | `CFG_ID_POS` | `CFG_MAGIC` "WSC1" (bits 63–32), station id (bits 31–0) |
| 1, 2 | `CFG_KEY_POS` | key bytes 0–7, 8–15 |
| 3 | `CFG_KCV_POS` | `CFG_MAGIC2` "KCV1" (bits 63–32), key check value (bits 23–0) |

A position is a double-word index: `dw_addr(page address, position)` gives its address, and
`dw_make`, `dw_hi` and `dw_lo` build and split the tag-and-value double-words.

```c {#config-constants}
#define CFG_MAGIC  0x57534331UL /* "WSC1" */
#define CFG_MAGIC2 0x4B435631UL /* "KCV1" */
#define CFG_KEY_DWORDS (WS_KEY_LEN / WS_DW_BYTES)
enum { CFG_ID_POS, CFG_KEY_POS, CFG_KCV_POS = CFG_KEY_POS + CFG_KEY_DWORDS, CFG_DWORDS };
_Static_assert(WS_KEY_LEN % WS_DW_BYTES == 0, "the key fills whole double-words");
/* The 3-byte key check value as the low bits of a 32-bit number, big-endian like its hex form. */
static uint32_t kcv_value(const uint8_t kcv[WS_KCV_LEN]) { return (uint32_t)ws_get_be64(kcv, WS_KCV_LEN); }
```

### Write

`store_config_write` programs the key, the check value, then the station double-word, which is
the commit word:

```text
cut before the station dw   station dw erased       load returns STORE_ENODATA (not provisioned)
cut during the station dw   station dw unreadable   load returns STORE_ENODATA
station dw programmed       complete                load returns the record
```

| Return | Cause |
|---|---|
| `STORE_EEXISTS` | a double-word of the record is not erased (it cannot be programmed again; WIPE erases the page) |
| `STORE_ERANGE` | station id outside 1..`WS_STATION_MAX` |
| `STORE_EKEY` | `ws_key_check` failed |
| `STORE_EFLASH` | a program failed |

The stack copy of the key is wiped on every path.

```c {#config-write}
/* 1 if every double-word of the record is erased (a programmed one cannot be programmed again). */
static int cfg_erased(uint32_t a) {
 for (uint32_t i = 0; i < CFG_DWORDS; i++) if (rd64(dw_addr(a, i), 0) != ERASED) return 0;
 return 1;
}
int store_config_write(uint32_t station, const uint8_t key[WS_KEY_LEN], uint8_t kcv[WS_KCV_LEN]) {
 uint32_t a = WS_PAGE_ADDR(WS_CONFIG_PAGE); uint64_t k[CFG_KEY_DWORDS]; int rc = STORE_OK;
 if (!cfg_erased(a)) return STORE_EEXISTS; /* WIPE first */
 if (station == 0 || station > WS_STATION_MAX) return STORE_ERANGE;
 if (ws_key_check(key, kcv)) return STORE_EKEY;
 memcpy(k, key, sizeof k);
 for (uint32_t i = 0; i < CFG_KEY_DWORDS && !rc; i++) rc = prog64(dw_addr(a, CFG_KEY_POS + i), k[i]);
 ws_wipe(k, sizeof k);
 /* The station double-word last: it commits the record. */
 if (rc || prog64(dw_addr(a, CFG_KCV_POS), dw_make(CFG_MAGIC2, kcv_value(kcv))) ||
     prog64(dw_addr(a, CFG_ID_POS), dw_make(CFG_MAGIC, station))) return STORE_EFLASH;
 return STORE_OK;
}
```

### Load

`store_config_load` returns 0 only when both magics match, every double-word is readable, the
recomputed key check value (`ws_key_check`) equals the stored one, and the station id is in range.
It returns `STORE_ENODATA` (missing or unreadable), `STORE_EKEY` (check value mismatch: the key
changed after it was written) or `STORE_ERANGE` (station out of range), and zeroes the key buffer
on every failure. On success it also fills `kcv_out` with the check value, which the console
prints for comparison with the gateway's.

```c {#config-load}
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
```

## 5. Meta log

### Format

Pages 33 and 34 hold an append-only log of 64-bit records:

```text
 63      56 55                                                  0
+----------+-----------------------------------------------------+
|   type   |                  value (56 bits)                    |
+----------+-----------------------------------------------------+
```

| Type | Name | Value |
|---|---|---|
| `0xE1` | `META_EPOCH` | highest boot epoch reserved, or the epoch floor |
| `0xC2` | `META_CTR` | highest counter reserved (inclusive) |
| `0xD1` | `META_LOST` | cumulative records overwritten while pending (gap G8) |
| `0xD2` | `META_ABAND` | cumulative records abandoned by NACK or strike limit |

A record is one double-word, so it is its own commit word. Double-word 0 of a page is the header:
`META_MAGIC` "WSM1" in bits 63–32 and a generation number in bits 31–0. Positions 1–255 hold
records.

```c {#meta-constants}
#define META_MAGIC 0x57534D31UL /* "WSM1" */
#define META_EPOCH 0xE1U
#define META_CTR   0xC2U
#define META_LOST  0xD1U /* cumulative journal overflow losses (gap G8) */
#define META_ABAND 0xD2U /* cumulative abandoned records (NACK / strike limit) */
#define META_TYPE_SHIFT 56U                                  /* type: bits 63-56, value: bits 55-0 */
#define META_VALUE_MAX ((1ULL << META_TYPE_SHIFT) - 1U)
#define META_DWORDS (WS_PAGE_SIZE / WS_DW_BYTES)
#define META_FIRST_POS 1U   /* position 0 is the page header */
#define META_FIRST_GEN 1U
#define CTR_BLOCK 256U
static uint64_t meta_word(uint32_t type, uint64_t value) { return (uint64_t)type << META_TYPE_SHIFT | value; }
```

RAM state: the active page, the next free position and its generation, and the four maxima.
`ctr_next` is the next counter to return. It stays at or below `ctr_reserved + 1` (counters are
reserved in blocks, below).

```c {#meta-state}
/* ---- monotonic meta log ---- */
static uint32_t meta_active, meta_pos, meta_gen;
static uint32_t max_epoch;
static uint64_t ctr_reserved, ctr_next;
static uint32_t lost_total, abandoned_total;
```

### Boot

`meta_absorb` raises a maximum from one record and ignores unknown types. The lost and abandoned
totals are 32-bit in RAM. `raise32` ignores a value above `0xFFFFFFFF` instead of truncating it.

```c {#meta-absorb}
/* A 32-bit total only moves up, and only to a value that fits. */
static void raise32(uint32_t *total, uint64_t val) {
 if (val > *total && val <= UINT32_MAX) *total = (uint32_t)val;
}
/* Folds one readable meta record into the RAM maxima; unknown types are ignored. */
static void meta_absorb(uint64_t v) {
 uint64_t val = v & META_VALUE_MAX;
 switch (v >> META_TYPE_SHIFT) {
 case META_EPOCH: raise32(&max_epoch, val); break;
 case META_CTR: if (val > ctr_reserved) ctr_reserved = val; break;
 case META_LOST: raise32(&lost_total, val); break;
 case META_ABAND: raise32(&abandoned_total, val); break;
 default: break;
 }
}
```

`meta_scan` reads a page header and every position. A page without a readable "WSM1" header is not
a meta page. An unreadable record adds no value but still counts as used: `*last` is the last
position that is not erased, and appends continue after it, because a torn double-word cannot be
programmed again.

```c {#meta-scan}
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
```

`store_meta_init` scans both pages into the same maxima. The active page is the valid page with the
higher generation (B on a tie). With no valid page it erases A and writes a generation-1 header.
Taking the maxima from both pages is correct during a compaction, when both can be valid.
`ctr_next` starts at `ctr_reserved + 1`, which skips any counters of the last block that were used
before the reset.

```c {#meta-init}
int store_meta_init(void) {
 uint32_t ga = 0, gb = 0, la = 0, lb = 0;
 int va, vb;
 meta_ready = 0;
 max_epoch = 0; ctr_reserved = 0; lost_total = 0; abandoned_total = 0;
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
 ctr_next = ctr_reserved + 1; /* skip anything that may have been used before reset */
 meta_ready = 1;
 return STORE_OK;
}
```

If both meta pages are unreadable while the provisioning record survives, the counter restarts at 1
under the existing key. Firmware review rated this robustness-2. It needs a layout change to cause,
and a layout-version field is deferred to the first layout change.

### Append

`meta_append` returns `STORE_ERANGE` for a value over `META_VALUE_MAX` (56 bits), compacts when
the active page is full, and returns `STORE_EFLASH` if the compaction or the program fails. Callers
pass its code through. A failed program still consumes its
position: the double-word may be torn.

```c {#meta-append}
static int meta_append(uint32_t type, uint64_t value) {
 if (value > META_VALUE_MAX) return STORE_ERANGE;
 if (meta_pos >= META_DWORDS && meta_compact()) return STORE_EFLASH;
 int rc = prog64(dw_addr(WS_PAGE_ADDR(meta_active), meta_pos), meta_word(type, value));
 meta_pos++; /* a failed program may have torn the double-word: never reuse it */
 return rc ? STORE_EFLASH : STORE_OK;
}
```

### Compaction

When the active page is full, `meta_compact` writes the four maxima as fresh records into the other
page and makes it active with the next generation:

```text
step                                    other page at boot          active page at boot
1. program 0 over its header            not a meta page             valid, all values
2. erase it                             not a meta page             valid, all values
3. program EPOCH, CTR, LOST, ABAND      not a meta page (no header) valid, all values
4. program header WSM1 | gen + 1        valid, higher generation    valid, older generation
   RAM: active = other page, pos = META_FIRST_POS + 4
```

A cut at steps 1–3 leaves the current page authoritative and the next append compacts again. After
step 4 the maxima over both pages are unchanged.

Step 1 fixes firmware review finding 4 (FW4, 2026-10-14). The other page holds the previous
generation with a valid header. Erasing it with the header in place allowed a cut to leave the
header readable over partially erased records. Boot would then take maxima from junk, and a counter
above 2^40 disables the node permanently (WIPE keeps the counter). Programming zeros over the
header first (allowed over written data) makes the page invalid before the erase starts. The test
model's partial erases leave whole double-words old, erased or unreadable, never altered values, so
the sweeps exercise the step order but cannot reproduce the original failure.

```c {#meta-compact}
/* Compact into the other page; its header is written last so a torn compaction
   leaves the current page authoritative. The other page still carries an older valid header:
   zero it first (programming all-zeros over data is allowed), so an erase cut part way can
   never leave half-erased values under a header boot would trust (firmware review finding 4). */
static int meta_compact(void) {
 uint32_t other = meta_active == WS_META_PAGE_A ? WS_META_PAGE_B : WS_META_PAGE_A;
 uint32_t a = WS_PAGE_ADDR(other);
 const uint64_t rec[] = { meta_word(META_EPOCH, max_epoch), meta_word(META_CTR, ctr_reserved),
                          meta_word(META_LOST, lost_total), meta_word(META_ABAND, abandoned_total) };
 int bad = 0;
 if (rd64(a, &bad) != ERASED && prog64(a, 0)) return STORE_EFLASH;
 if (erase_page(other)) return STORE_EFLASH;
 for (uint32_t k = 0; k < sizeof rec / sizeof rec[0]; k++) if (prog64(dw_addr(a, META_FIRST_POS + k), rec[k])) return STORE_EFLASH;
 if (prog64(a, dw_make(META_MAGIC, meta_gen + 1))) return STORE_EFLASH;
 meta_active = other; meta_gen++; meta_pos = META_FIRST_POS + sizeof rec / sizeof rec[0];
 return STORE_OK;
}
```

An unreadable header reads as 0 with `bad` set, which is not `ERASED`, so step 1 also zeroes it.

### Reserve before use

Every caller appends first and changes RAM only after the append succeeds, so RAM never holds a
value the next boot would not restore. The error sweep found one exception: `store_note_abandoned`
raised `abandoned_total` before appending, so a failed program made the reported total fall after
the next reboot (fixed 2026-10-13, `test_bug_failed_abandon_note_lowers_total_after_reboot`).

**Epoch.** `store_next_epoch` reserves one epoch per boot, before sampling. The observation
identity is (epoch, sequence). It returns `STORE_EEXHAUSTED` one below `STORE_EPOCH_RESERVED`
(`UINT32_MAX`, `node_store.h`). That epoch is `STORM_EPOCH`, the bench storm test's, whose records
the boot scrub acknowledges.

```c {#next-epoch}
int store_next_epoch(uint32_t *epoch) {
 if (!meta_ready) return STORE_ENOTREADY;
 /* A real boot never gets STORE_EPOCH_RESERVED, the bench storm test's epoch, whose records the
    boot scrub acknowledges. */
 if (max_epoch >= STORE_EPOCH_RESERVED - 1U) return STORE_EEXHAUSTED;
 int rc = meta_append(META_EPOCH, (uint64_t)max_epoch + 1);
 if (rc) return rc;
 *epoch = ++max_epoch;
 return STORE_OK;
}
```

**Epoch floor** (gap G5). After a WIPE the gateway supplies a floor above every epoch it has stored
for the station. A floor at or below the current epoch is accepted and changes nothing.

```c {#epoch-floor}
/* Gap G5: after a WIPE, the gateway supplies a floor above every epoch it has stored, so new
   observation identities can never collide with history. Values only move up. */
int store_epoch_floor(uint32_t floor) {
 if (!meta_ready) return STORE_ENOTREADY;
 if (floor <= max_epoch) return STORE_OK;
 int rc = meta_append(META_EPOCH, floor);
 if (rc) return rc;
 max_epoch = floor;
 return STORE_OK;
}
```

**Abandoned total** (gap G8): incremented for each record the gateway NACKed or the strike limit
dropped.

```c {#abandoned}
int store_note_abandoned(void) {
 if (!meta_ready) return STORE_ENOTREADY;
 int rc = meta_append(META_ABAND, (uint64_t)abandoned_total + 1);
 if (rc) return rc;
 abandoned_total++;
 return STORE_OK;
}
uint32_t store_abandoned_total(void) { return abandoned_total; }
```

**Counter.** One counter per transmission would fill a meta page every 255 frames, so the log
reserves blocks of `CTR_BLOCK` (256) and `store_next_counter` returns counters from RAM within the
block. A reset discards the rest of the block (init starts at `ctr_reserved + 1`): at most 255 of
2^40 counters. The frame header carries 40 bits (`WS_COUNTER_MAX`). Past it the function returns
`STORE_EEXHAUSTED` permanently instead of truncating. A failed reservation returns its error and
no counter.

```c {#next-counter}
int store_next_counter(uint64_t *counter) {
 if (!meta_ready) return STORE_ENOTREADY;
 /* The header carries 40 bits: past that a counter would be truncated and repeat a nonce. */
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
```

## 6. Journal

### Format

Pages 35–127 form a ring (`WS_JOURNAL_PAGES`, the host sweeps build it with 3 pages so they wrap).
Each page has an 8-byte header followed by fixed-size slots. Default build (35-byte plaintext):

```text
journal page, 2048 B: 56-byte slots, 36 per page, 24 B unused
+-----------------------+--------+--------+-----+---------+--------+
| WSJ+size | sequence   | slot 0 | slot 1 | ... | slot 35 | unused |
+-----------------------+--------+--------+-----+---------+--------+

slot, 56 B
+-------------------------------+---------------------------+------------------+
| plaintext, zero-padded:       | commit:                   | ACK:             |
| JOURNAL_PLAIN_DW double-words | 0x4A53 | CRC-16 | 0       | erased = pending |
|                               | (bits 63-48|47-32|31-0)   | 0 = acknowledged |
+-------------------------------+---------------------------+------------------+
 position 0                      COMMIT_POS                  ACK_POS
```

The slot size follows the build's field set (`node_fields.h`). The widest catalog gives 78-byte
plaintexts, 96-byte slots and 21 slots per page, and the host tests build that geometry too. The
header magic carries the slot size in its low byte, so a page written with another slot size reads
as "not a journal page". The header's low 32 bits are the page sequence, incremented for each page
opened. The head is the page with the highest sequence.

```c {#journal-constants}
#define JPG_MAGIC  (0x57534A00UL | JOURNAL_SLOT_BYTES) /* "WSJ" + slot size: another layout is ignored */
#define SLOT_MAGIC 0x4A53U
#define JOURNAL_FIRST_SEQ 1U   /* page sequence 0 marks "not a journal page" */
```

```c {#geometry}
/* Geometry the on-flash format depends on (node_store.h). Positions are double-words in a slot. */
#define SLOT_BYTES JOURNAL_SLOT_BYTES
#define COMMIT_POS JOURNAL_PLAIN_DW
#define ACK_POS (COMMIT_POS + 1U)
```

Compile-time checks tie the format to `node_fields.h` and `flash_layout.h` (review P16):

```c {#geometry-checks}
_Static_assert(SLOT_BYTES == (ACK_POS + 1U) * WS_DW_BYTES && COMMIT_POS * WS_DW_BYTES >= WS_OBS_PLAIN_MAX,
               "slot = plaintext rounded to double-words + commit + ack double-words");
_Static_assert(SLOT_BYTES <= UINT8_MAX, "the slot size fits in the page magic's low byte");
_Static_assert(JOURNAL_SLOTS_PER_PAGE >= 1U && JOURNAL_HDR_BYTES + JOURNAL_SLOTS_PER_PAGE * SLOT_BYTES <= WS_PAGE_SIZE,
               "journal slots fit in one page");
_Static_assert(WS_OBS_ID_LEN <= WS_DW_BYTES, "a record's identity is in its first double-word");
_Static_assert((uint64_t)WS_CONFIG_PAGE * WS_PAGE_SIZE >= WS_FIRMWARE_BYTES, "node state sits above the firmware region");
_Static_assert(WS_CONFIG_PAGE < WS_META_PAGE_A && WS_META_PAGE_A < WS_META_PAGE_B && WS_META_PAGE_B < WS_JOURNAL_FIRST,
               "config, meta and journal pages are distinct and in order");
_Static_assert(WS_JOURNAL_PAGES >= 2U && WS_JOURNAL_FIRST + WS_JOURNAL_PAGES <= WS_FLASH_PAGES, "journal fits in flash");
_Static_assert(WS_JOURNAL_PAGES <= UINT16_MAX && JOURNAL_SLOTS_PER_PAGE <= UINT16_MAX, "jref_t page and slot are 16-bit");
```

### Slot states

A slot is programmed at most twice after its page is erased: data and commit by the append, then
zero into the ACK double-word by the acknowledgement.

```text
erased --append--> pending --ack--> acknowledged
   |
   +-- cut or failed program during the append --> burned (never reused)
```

Boot classifies each slot from flash:

| Data and commit | ACK double-word | Boot state |
|---|---|---|
| all erased | erased | blank |
| readable, commit matches the plaintext | erased | pending |
| readable, commit matches the plaintext | not erased, or unreadable | acknowledged |
| any unreadable, or commit does not match | any | burned (counted by `store_journal_burned()`) |

The commit word holds the slot magic and a CRC-16 of the plaintext. Boot compares its upper 32
bits with `slot_commit_word(plain) >> 32`. The CRC catches a commit word that survived a partial
page erase over data that did not (or the reverse).

An unreadable ACK double-word counts as acknowledged: the ACK program starts only after the
gateway's authenticated ACK arrived, so the gateway already stored the record. Treating it as
pending would send it again.

```c {#crc}
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
   (bits 15-0); the low half is zero. */
static uint64_t slot_commit_word(const uint8_t plain[WS_OBS_PLAIN_MAX]) {
 return dw_make((uint32_t)SLOT_MAGIC << 16 | crc16(plain, WS_OBS_PLAIN_MAX), 0);
}
```

`node_store.c` is built with `-fno-optimize-crc` (Makefile): GCC 15 otherwise replaces this loop
and `ws_crc8` with 768 B of lookup tables, for code that runs a few times a minute.

### RAM state

Rebuilt from flash at every boot: `page_seq[p]` (0 = not a journal page), one pending bit per slot
of the ring, and the head position. `n_lost` and `n_burned` count since boot. The persisted lost
total is `lost_total` in the meta log. A slot is named by a `jref_t` (page, slot). Only this file
creates them, and the public functions that take one check its range.

```c {#journal-state}
/* ---- journal ---- */
static uint32_t page_seq[WS_JOURNAL_PAGES];
static uint8_t pending[(JOURNAL_CAPACITY + CHAR_BIT - 1) / CHAR_BIT];   /* one bit per slot */
static uint32_t head, head_slot, n_pending, n_lost, n_burned;
```

```c {#journal-helpers}
static uint32_t slot_index(jref_t r) { return (uint32_t)r.page * JOURNAL_SLOTS_PER_PAGE + r.slot; }
static int is_pending(uint32_t i) { return pending[i / CHAR_BIT] >> (i % CHAR_BIT) & 1U; }
static void set_pending(uint32_t i, int on) {
 uint8_t bit = (uint8_t)(1U << (i % CHAR_BIT));
 if (on) pending[i / CHAR_BIT] |= bit; else pending[i / CHAR_BIT] &= (uint8_t)~bit;
}
static uint32_t slot_addr(uint32_t page, uint32_t slot) {
 return WS_PAGE_ADDR(WS_JOURNAL_FIRST + page) + JOURNAL_HDR_BYTES + slot * SLOT_BYTES;
}
```

### Append

```text
1. head page full: open the next page (below)
2. take (head, head_slot); head_slot++
3. program plaintext double-words 0 .. JOURNAL_PLAIN_DW-1
4. program the commit word
5. RAM: set the pending bit
```

The slot is consumed at step 2, before any program, so a failed program leaves a burned slot that
is never reused. Append requires `meta_ready` because opening a page may persist the lost total.

```c {#journal-append}
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
```

### Opening a page

The page after the head is the oldest. When the ring is full it still holds pending records, which
opening it destroys. `journal_new_page` counts them before the erase:

```text
1. count pending slots on the page
2. if any: meta_append(LOST, lost_total + count)    fails: return its error, page untouched
3. RAM: clear their pending bits, add count to the totals, page_seq = 0
4. erase the page
5. program the header: WSJ | slot size, sequence = previous head's + 1
```

A cut between steps 2 and 4 over-counts: the records remain and the total already includes them
(the sweep records this as `note_lost_back`, over-counting is allowed). A cut during steps 4–5
leaves a page with its old header and some old slots, or no readable header. Boot repairs it
(next section). The step-2 failure path was missing until the error sweep found it: a failed
`meta_append(META_LOST)` was ignored and the page erased, losing records the total never counted
(fixed 2026-10-13, `test_bug_failed_lost_persist_still_erases_page`).

```c {#journal-new-page}
static int journal_new_page(uint32_t page, uint32_t seq) {
 uint32_t dropped = 0;
 for (uint32_t s = 0; s < JOURNAL_SLOTS_PER_PAGE; s++) dropped += (uint32_t)is_pending(page * JOURNAL_SLOTS_PER_PAGE + s);
 /* persist before the page is reused; if that fails, keep the page and its records */
 int rc = dropped ? meta_append(META_LOST, (uint64_t)lost_total + dropped) : STORE_OK;
 if (rc) return rc;
 for (uint32_t s = 0; s < JOURNAL_SLOTS_PER_PAGE; s++) set_pending(page * JOURNAL_SLOTS_PER_PAGE + s, 0);
 n_pending -= dropped; n_lost += dropped; lost_total += dropped;
 page_seq[page] = 0;
 if (erase_page(WS_JOURNAL_FIRST + page) || prog64(WS_PAGE_ADDR(WS_JOURNAL_FIRST + page), dw_make(JPG_MAGIC, seq))) return STORE_EFLASH;
 page_seq[page] = seq;
 return STORE_OK;
}
```

`journal_advance_if_full` opens the next page only when the head is full. Append and init both
call it.

```c {#journal-advance}
/* Opens a fresh page after the head once the head is full (append, and init after a cut). */
static int journal_advance_if_full(void) {
 if (head_slot < JOURNAL_SLOTS_PER_PAGE) return STORE_OK;
 uint32_t next = (head + 1) % WS_JOURNAL_PAGES;
 int rc = journal_new_page(next, page_seq[head] + 1);
 if (rc) return rc;
 head = next; head_slot = 0;
 return STORE_OK;
}
```

### Boot

`journal_find_head` reads every page header. The head is the page with the highest sequence (the
later page on a tie). A page with an unreadable or foreign header is not a journal page.

```c {#journal-find-head}
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
```

`journal_scan_slot` classifies one slot (table above). `journal_scan_page` returns one past the
last slot that is not blank. On the head page the next append goes there, after any burned slot.

```c {#journal-scan-slot}
/* Boot scan of one slot: 0 if blank, else 1 after counting it burned (torn or unreadable data)
   or, when committed and not acknowledged, pending. */
static int journal_scan_slot(uint32_t p, uint32_t s) {
 uint32_t a = slot_addr(p, s); int bad_data = 0, bad_ack = 0, erased = 1; uint64_t d[COMMIT_POS + 1], ack;
 for (uint32_t k = 0; k <= COMMIT_POS; k++) { d[k] = rd64(dw_addr(a, k), &bad_data); erased &= d[k] == ERASED; }
 ack = rd64(dw_addr(a, ACK_POS), &bad_ack);
 if (!bad_data && !bad_ack && erased && ack == ERASED) return 0;
 uint8_t plain[WS_OBS_PLAIN_MAX]; memcpy(plain, d, sizeof plain);
 /* A torn ACK word (ECC) means the ACK program was interrupted after the host committed: acked. */
 if (bad_data || dw_hi(d[COMMIT_POS]) != dw_hi(slot_commit_word(plain))) n_burned++;
 else if (!bad_ack && ack == ERASED) { set_pending(p * JOURNAL_SLOTS_PER_PAGE + s, 1); n_pending++; }
 return 1;
}
/* Scans a journal page's slots; returns one past the last used slot (0 if none). */
static uint32_t journal_scan_page(uint32_t p) {
 uint32_t last_used = 0;
 for (uint32_t s = 0; s < JOURNAL_SLOTS_PER_PAGE; s++) if (journal_scan_slot(p, s)) last_used = s + 1;
 return last_used;
}
```

The last step of `store_journal_init` fixes the first bug the power-cut sweep found (2026-10-13,
`test_bug_interrupted_recycle_resurrects_acked_record`). If the head page is full, the next page's
recycle may have been cut during its erase, which can erase an ACK double-word while the record's
data and commit survive. That slot then reads as pending and an acknowledged record is sent again.
Init therefore finishes the recycle (`journal_advance_if_full`) before it trusts that page. A page
after a head that is not full was never recycled, so its slots are as written.

```c {#journal-init}
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
 /* The head is full, so the next page's recycle may have been cut mid-erase, which can wipe
    an ACK word but leave its record: finish the recycle before trusting that page. */
 int rc = journal_advance_if_full();
 if (rc) return rc;
 journal_ready = 1;
 return STORE_OK;
}
```

### Read and acknowledge

`store_journal_read` returns `STORE_ENODATA` if any plaintext double-word is unreadable. The caller prints
`#error journal-read` and moves to the next record.

```c {#journal-read}
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
```

`store_journal_ack` programs zero into the ACK double-word, then clears the pending bit. If the
program fails the record stays pending and is sent again. The gateway deduplicates it. Clearing the
bit first would let RAM drop a record that flash still holds as pending, and the next boot would
send it anyway. Acknowledging a slot that is not pending returns 0 and writes nothing.

```c {#journal-ack}
int store_journal_ack(jref_t ref) {
 if (!journal_ready) return STORE_ENOTREADY;
 if (!WS_CHECK(ref_in_journal(ref))) return STORE_EINVAL;   /* before it indexes pending[] */
 uint32_t i = slot_index(ref);
 if (!is_pending(i)) return STORE_OK;
 if (prog64(dw_addr(slot_addr(ref.page, ref.slot), ACK_POS), 0)) return STORE_EFLASH;
 set_pending(i, 0); n_pending--;
 return STORE_OK;
}
```

### Pending records

`store_journal_oldest` returns pending records oldest first: pages from the one after the head to
the head, slots in order within a page. `except` excludes the record the exchange already holds.

```c {#journal-oldest}
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
```

A record's identity is (epoch, sequence), the plaintext's first 8 bytes, big-endian.
`next_pending_match` searches pending slots for an identity, comparing against flash. A slot whose
first double-word is unreadable never matches. `store_journal_find` matches epoch and sequence.
`store_journal_scrub` matches the epoch only.

```c {#journal-find}
/* Shared by find and scrub: the next pending slot, from index *i on, whose identity (epoch and,
   unless any_seq, sequence: the plaintext's first WS_OBS_ID_LEN bytes) matches and reads back
   without an ECC fault. Returns 1 with its ref and *i just past it; 0 when no such slot is left. */
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
```

`store_journal_scrub` acknowledges every pending record of one epoch. Boot calls it with
`STORM_EPOCH` to drop the bench storm test's records. Each match advances `i` past its slot and no
slot is found at or past `JOURNAL_CAPACITY`, so the loop runs at most `JOURNAL_CAPACITY` times
(Power of Ten rule 2, `tools/loop_bounds.py` reads the `bound:` comment).

```c {#journal-scrub}
uint32_t store_journal_scrub(uint32_t marker)
{
 uint32_t n = 0, i = 0; jref_t r;
 if (!journal_ready) return 0;
 /* Only bad == 0 slots match; the ack clears slot r's bit, which the scan has already passed.
    Each match moves i past its slot, and none is found at or past JOURNAL_CAPACITY, so: */
 /* bound: at most JOURNAL_CAPACITY passes */
 while (next_pending_match(marker, 1, 0, &i, &r))
  if (store_journal_ack(r) == 0) n++;
 return n;
}
```

Accessors for the console, `#sample` and the DIAG report. Only the lost total persists across
boots.

```c {#accessors}
uint32_t store_journal_pending(void) { return n_pending; }
uint32_t store_journal_lost(void) { return lost_total; } /* cumulative, persisted */
uint32_t store_journal_burned(void) { return n_burned; }
uint32_t store_ecc_faults(void) { return n_ecc; }
uint64_t store_counter_next(void) { return ctr_next; }
```

## 7. WIPE

`store_wipe` erases the journal and the provisioning record. It never erases the meta log (gap
G17, review P1): the counter, epoch and totals keep rising for the life of the board. The first
version erased both meta pages, which restarted the counter at 1. Re-provisioning the same key then
repeated nonces. A key first used under this firmware can follow the board across WIPEs. A key used
under older firmware, or on another board, cannot (`docs/runbook-moving-boards.md`).

Order:

```text
journal_ready = 0               RAM no longer describes flash
erase journal pages 35-127      any failure: return STORE_EFLASH, record kept
erase provisioning page 32      the board is unprovisioned from here
```

The provisioning page is erased last (2026-10-13,
`test_bug_interrupted_wipe_leaves_journal_on_unprovisioned_board`). The first version erased it
first. A cut after that left an unprovisioned board with pending records, which went out under the
next PROVISION's identity. With the record kept on a failed journal erase, the board stays
provisioned, the operator does not see `#wipe ok`, and runs WIPE again. An interrupted WIPE can
leave acknowledged records pending again (`note_acked_back_after_interrupted_wipe`). WIPE makes no
promise until it reports success.

```c {#wipe}
/* WIPE erases the key and the journal but never the meta log (gap G17): the counter (the AES-CCM
 * nonce), the boot epoch and the lost/abandoned totals keep rising for the life of the board. */
int store_wipe(void) {
 int rc = STORE_OK;
 journal_ready = 0; /* the RAM journal no longer describes flash: store_journal_init again */
 for (uint32_t p = 0; p < WS_JOURNAL_PAGES; p++) rc |= erase_page(WS_JOURNAL_FIRST + p);
 if (rc) return STORE_EFLASH; /* keep the key: an unprovisioned board must not carry old records */
 return erase_page(WS_CONFIG_PAGE);
}
```

## 8. The file

The generated file orders the chunks for C: constants and compile-time checks, flash access, then
provisioning, the meta log and the journal, each after the state it uses.

```c {#node_store.c}
<<abstract>>
#define WS_CHECK_FILE 5
#include "node_store.h"
#include <limits.h>
#include <string.h>
#include "ws_be.h"
#include "ws_check.h"
#include "ws_frame.h"

<<erased>>
<<config-constants>>
<<meta-constants>>
<<journal-constants>>

<<geometry>>
<<geometry-checks>>

<<flash-primitives>>

<<ready-flags>>

<<config-load>>
<<config-write>>

<<meta-state>>

<<meta-absorb>>
<<meta-scan>>
<<meta-compact>>
<<meta-append>>
<<meta-init>>
<<next-epoch>>
<<epoch-floor>>
<<abandoned>>

<<next-counter>>

<<journal-state>>

<<journal-helpers>>
<<crc>>
<<journal-new-page>>
<<journal-advance>>
<<journal-find-head>>
<<journal-scan-slot>>
<<journal-init>>
<<journal-append>>
<<journal-read>>
<<journal-ack>>
<<journal-oldest>>
<<journal-find>>
<<accessors>>

<<journal-scrub>>

<<wipe>>
```

## 9. Tests

`firmware/test_store.c` runs a scripted workload (provision, boot epochs, counter blocks, journal
appends and ACKs, abandons, two meta compactions, a journal wrap with losses, the storm scrub,
WIPE) over `firmware/sim_flash.c`, in three modes:

| Mode | What it does |
|---|---|
| functional | the workload once, checking results |
| sweep | for each flash operation index: cut power there once for each outcome the model has, reboot, check every guarantee in section 1. Program outcomes: old, new, torn. Erase outcomes: none, all, two random partial patterns, partial with unreadable double-words. |
| errsweep | for each flash operation index: fail that operation like a HAL error (flash unchanged, or left torn / partially erased), continue the workload, check |

and three geometries: `full` (the board's 93-page journal), `small` (a 3-page journal, so the sweeps
wrap) and `wide` (the widest field catalog, 3 pages). `tests/test_store_powercut.py` builds and
runs them under ASan and UBSan and fails on any violation it does not list as a note. It also runs
the four `test_bug_*` regressions named above.

```sh
.venv/bin/python -m unittest tests.test_store_powercut tests.test_tangle
```
