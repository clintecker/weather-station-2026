# The node store: state that survives a power cut at any instant

This document is the source of `node_store.c`. The C file is generated from the code chunks below
by `tools/tangle.py` and committed, so the build, the analysers and the power-cut tests read
ordinary C; `tests/test_tangle.py` fails if the two ever differ. Edit this file, then:

```sh
tools/tangle.py firmware/stage0-node/App/node_store.lit.md          # node_store.c
tools/tangle.py --weave out.html firmware/stage0-node/App/node_store.lit.md  # this page
```

Code chunks are named (⟨journal-append⟩ ≡ ...) and refer to each other by name; each one says
where it is used. The chunks appear in the order that makes the argument, not in file order; the last
section assembles the file.

## 1. What has to survive

The TX node keeps three kinds of state in its own internal flash, and each has a different
promise to keep when the power goes at an arbitrary moment (a flat battery, a brown-out, someone
pulling the USB cable in the middle of a page erase):

| State | What it is | The promise after any power cut |
|---|---|---|
| Provisioning | station id and the 16-byte AES key, with a key check value | it is the one that was written, or there is none; never a mix |
| Monotonic values | boot epoch, transmission counter (the AES-CCM nonce), the lost and abandoned totals | never lower than any value already handed out or reported; a counter or epoch is never handed out twice |
| Journal | the observation plaintexts not yet acknowledged by the gateway | an ACKed record never comes back; a pending record never disappears without being counted as lost |

The counter promise is the one with teeth. The counter is the nonce of AES-CCM under a key that
outlives this firmware: handing out the same counter twice under one key breaks the encryption
and the authentication of both frames. Everything else is about data quality (a record sent twice
is deduplicated by the gateway; a record lost is at least counted), but a repeated nonce is a
security failure. So the store's rule for monotonic values is blunt: *reserve on flash first, use
second*, and on boot take the maximum of everything readable.

These are the invariants `firmware/test_store.c` checks after every simulated reboot, with a cut
at every single flash operation of a scripted workload and every way that cut can land
(`tests/test_store_powercut.py`: about 33,000 simulated reboots across the sweeps):

- `counter_repeat`, `epoch_repeat`: no counter or epoch at or below one already returned;
- `acked_returned`: no record whose ACK returned 0 is pending again;
- `pending_uncounted`: pending records that vanished are covered by the rise in the lost total;
- `lost_decreased`, `abandoned_decreased`: the totals never fall;
- `config_wrong`, `config_lost`: the config is the one written or none, and a completed
  provisioning still loads;
- `wipe_journal_survives`: an interrupted WIPE never leaves an unprovisioned board with records
  that would go out under the next identity;
- `sim_violation`: nothing programs a double-word that is not erased.

## 2. The flash we are writing to

The STM32WL55JC has 256 KB of single-bank flash in 128 pages of 2 KB. The rules that matter
(RM0453 section 3.3), as `firmware/sim_flash.c` models them:

| Operation | Normal effect | If the power is cut during it |
|---|---|---|
| erase one page (~22 ms) | every double-word of the page reads all ones | the page is partially erased: some double-words erased, some still old, some unreadable |
| program one double-word (~82 µs) | 8 bytes, once per erase, 8-byte aligned | the double-word holds the old (erased) value, the new value, or a torn value |
| program zeros over written data | allowed (RM0453 PROGERR: "except if the data to write is all zeros") | as above |
| read one double-word | the value | (no cut effect) a torn double-word fails its ECC: a double error raises the NMI |

Each double-word carries its own ECC. A torn program leaves bits that do not match it; the read
raises a double-ECC NMI, `NMI_Handler` sets `ws_flash_ecc_fault`, and the board's
`ws_flash_read64` (`App/flash_stm32wl.c`) returns nonzero. So a read has three outcomes, not two:
erased, a value, or *unreadable*. Every decision below has to say what it does with the third.

The node state lives above the firmware, in fixed pages (`flash_layout.h`):

| Pages | Use |
|---|---|
| 0–31 (64 KB) | firmware (the linker script enforces the limit) |
| 32 | provisioning: station id, key, key check value |
| 33, 34 | meta log A and B: the monotonic values, append-only, compacted from one into the other |
| 35–127 | journal: a ring of 93 pages of observation slots |

No HAL here: flash goes through three link-time functions, `ws_flash_read64`, `ws_flash_prog64`
and `ws_flash_erase` (`flash_layout.h`). On the board they are `App/flash_stm32wl.c`; on the host
they are `firmware/sim_flash.c`, which is how the power-cut tests run this exact file (review item
P3: a link-time seam, not a table of function pointers, Power of Ten rule 9).

### The one idea: commit last

Every record in this file is written the same way: the data first, then *one final double-word*
that says "this record is complete". A cut can then leave only three things, and all three read
back as *not present*:

1. nothing: the cut came before the first program;
2. data without its commit double-word: the commit is erased, so the record is ignored;
3. a torn double-word somewhere: its read fails ECC, and an unreadable commit is not a commit.

Monotonic values add a second idea: they *only ever increase*, so recovery never has to decide
which of two copies is the right one. It takes the maximum of everything readable, and losing a
record to a cut can only make the next boot reserve a little higher than strictly necessary.

The whole file is an application of those two ideas to three layouts. Here is the prologue the
generated file starts with, which says the same in six lines:

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

### Reading, writing and erasing

The three primitives get thin wrappers. `rd64` turns an ECC fault into a flag and a zero value,
and counts it (`store_ecc_faults()` reports the count: a non-zero count after boot means a cut
tore something). The `bad` flag is sticky: a caller can read several double-words and test once.

```c {#erased}
#define ERASED 0xFFFFFFFFFFFFFFFFULL
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

Writes are where a bug does damage: a wild address could erase the firmware under the running
program. So every program and erase checks that it lies inside the node-state pages (config,
meta, journal; never the firmware below them) and that a program is double-word aligned. This is
a `WS_CHECK` (`firmware/common/ws_check.h`, Power of Ten rule 5): a failure is a bug in this file,
counted with its site, and the recovery is to refuse the operation exactly like a failed flash
operation, which every caller already handles.

```c {#write-guards}
/* Every write stays inside the node-state pages (config, meta, journal; flash_layout.h): never the
   firmware below them. A bad address or page is refused like a failed flash operation. */
#define STORE_PAGE_END (WS_JOURNAL_FIRST + WS_JOURNAL_PAGES)
static int prog64(uint32_t addr, uint64_t v) {
 if (!WS_CHECK(addr >= WS_PAGE_ADDR(WS_CONFIG_PAGE) && addr < WS_PAGE_ADDR(STORE_PAGE_END) && !(addr & 7U))) return -1;
 return ws_flash_prog64(addr, v) ? -1 : 0;
}
static int erase_page(uint32_t page) {
 if (!WS_CHECK(page >= WS_CONFIG_PAGE && page < STORE_PAGE_END)) return -1;
 return ws_flash_erase(page) ? -1 : 0;
}
```

One more guard sits under everything that writes. The RAM state below (where the next meta
record goes, which journal slots are pending) is only meaningful after a successful boot scan.
The mutators refuse to run on RAM state that no successful init produced (review P3: the
`store_ready` guard), instead of appending at a stale position; they return `STORE_ENOTREADY`
(`node_store.h`) and touch nothing.

```c {#ready-flags}
/* store_ready guard (review P3): mutators refuse to run on RAM state that no successful init
   produced, instead of appending at a stale position. */
static uint8_t meta_ready, journal_ready;
```

## 3. Provisioning: four double-words, magic last

The config page holds one record of four double-words:

| Offset | Double-word | Contents |
|---|---|---|
| +0 | `d0` | `CFG_MAGIC` "WSC1" (high 32 bits) · station id (low 32) |
| +8 | `k0` | key bytes 0–7 |
| +16 | `k1` | key bytes 8–15 |
| +24 | `d3` | `CFG_MAGIC2` "KCV1" (high 32) · 0 · key check value (low 24 bits) |

```c {#config-constants}
#define CFG_MAGIC  0x57534331UL /* "WSC1" */
#define CFG_MAGIC2 0x4B435631UL /* "KCV1" */
```

The write order is the commit-last rule with the commit at offset 0: key halves, then the check
value, then the first double-word with its magic. A cut anywhere before that last program leaves
`d0` erased, and the page loads as *not provisioned*. The page is written once: a double-word that
is not erased cannot be programmed again, so `store_config_write` refuses rather than tear an
existing config (WIPE erases the page first).

```text
program order:  k0 (+8)  ->  k1 (+16)  ->  d3 (+24: KCV1 | kcv)  ->  d0 (+0: WSC1 | station)
cut before d0:  d0 erased             -> load returns -1 (not provisioned)
torn d0:        d0 unreadable (ECC)   -> load returns -1
d0 written:     all four complete     -> the one config that was written
```

The key copies on the stack are wiped on every path, including the failing ones (the security
audit of 2026-10-14 checked these are kept).

```c {#config-write}
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
```

Loading checks more than the magics. Both magics must be present and every double-word readable;
then the key check value (`ws_key_check`: a short, keyed fingerprint of the key) is recomputed
and must match the stored one, so a key that was damaged after it was written is refused rather
than used; and the station id must be in range. Any failure zeroes the key buffer, so a caller
cannot accidentally use half a key. The check value is handed back, so the console can show it
and an operator can compare it with the gateway's.

```c {#config-load}
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
```

## 4. The monotonic meta log

### Records that only go up

The four monotonic values share one append-only log. Each record is a single double-word, so
*a record is its own commit*: it is either fully programmed, still erased, or unreadable.

```text
 63      56 55                                                  0
+----------+-----------------------------------------------------+
|   type   |                  value (56 bits)                    |
+----------+-----------------------------------------------------+
```

| Type | Name | Value |
|---|---|---|
| `0xE1` | `META_EPOCH` | the highest boot epoch reserved (or floor set) |
| `0xC2` | `META_CTR` | the counter reserved *up to* (inclusive) |
| `0xD1` | `META_LOST` | cumulative journal records overwritten while pending (gap G8) |
| `0xD2` | `META_ABAND` | cumulative records abandoned (NACK or strike limit) |

A meta page is a header double-word, `META_MAGIC` "WSM1" in the high half and a *generation*
number in the low half, followed by 255 record positions:

```text
page 33 or 34 (2048 B = 256 double-words)
+--------------------+----------+----------+-----+----------+
| WSM1 | generation  | record 1 | record 2 | ... | record   |
|      (header)      |          |          |     |   255    |
+--------------------+----------+----------+-----+----------+
  dw 0                 dw 1       dw 2              dw 255
```

```c {#meta-constants}
#define META_MAGIC 0x57534D31UL /* "WSM1" */
#define META_EPOCH 0xE1U
#define META_CTR   0xC2U
#define META_LOST  0xD1U /* cumulative journal overflow losses (gap G8) */
#define META_ABAND 0xD2U /* cumulative abandoned records (NACK / strike limit) */
#define META_DWORDS (WS_PAGE_SIZE / 8U)
#define CTR_BLOCK 256U
```

The RAM side is the maxima themselves, plus where the log is: the active page, the next free
position in it, and its generation. `ctr_next` is the next counter to hand out, which may be
below `ctr_reserved` (that is the point of reserving in blocks, below).

```c {#meta-state}
/* ---- monotonic meta log ---- */
static uint32_t meta_active, meta_pos, meta_gen;
static uint32_t max_epoch;
static uint64_t ctr_reserved, ctr_next;
static uint32_t lost_total, abandoned_total;
```

### Boot: the maximum of everything readable

Recovery folds every readable record into the RAM maxima. There is no "latest record" to find
and no ordering to trust: a record can only raise a value. The totals are 32-bit in RAM while the
record holds 56 bits, so `raise32` refuses a value that would not fit rather than truncate it into
something smaller. Unknown types are ignored.

```c {#meta-absorb}
/* A 32-bit total only moves up, and only to a value that fits. */
static void raise32(uint32_t *total, uint64_t val) {
 if (val > *total && val <= 0xFFFFFFFFULL) *total = (uint32_t)val;
}
/* Folds one readable meta record into the RAM maxima; unknown types are ignored. */
static void meta_absorb(uint64_t v) {
 uint64_t val = v & 0x00FFFFFFFFFFFFFFULL;
 switch (v >> 56) {
 case META_EPOCH: raise32(&max_epoch, val); break;
 case META_CTR: if (val > ctr_reserved) ctr_reserved = val; break;
 case META_LOST: raise32(&lost_total, val); break;
 case META_ABAND: raise32(&abandoned_total, val); break;
 default: break;
 }
}
```

Scanning a page reads its header (a page without a readable `WSM1` header is not a meta page),
then every position. The one subtle line is what an *unreadable* record does: it contributes no
value, but it still occupies its position. The next append must go after it, because a torn
double-word can never be programmed again. So `last` is the last position that is not erased,
readable or not.

```c {#meta-scan}
static int meta_scan(uint32_t page, uint32_t *gen, uint32_t *last) {
 uint32_t a = WS_PAGE_ADDR(page); int bad = 0;
 uint64_t h = rd64(a, &bad);
 if (bad || (h >> 32) != META_MAGIC) return -1;
 *gen = (uint32_t)h; *last = 0;
 for (uint32_t i = 1; i < META_DWORDS; i++) {
  int b = 0; uint64_t v = rd64(a + 8 * i, &b);
  if (!b && v == ERASED) continue;
  *last = i; /* an unreadable double-word still occupies its position */
  if (!b) meta_absorb(v);
 }
 return 0;
}
```

Init scans both pages into the same maxima. Which page is *active* (where appends go) is the
valid page with the higher generation; with neither valid it starts a fresh log on page A at
generation 1. Note that the maxima come from *both* pages: during a compaction both can be valid,
and whichever records each holds, the maximum over both is still a correct lower bound.

The last line before `meta_ready` is the counter rule: `ctr_next` starts one past the highest
reservation, skipping whatever part of the last block may have been used before the reset.

```c {#meta-init}
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
```

(Both pages unreadable while the config survives would restart the counter at 1 under an old
key. The firmware review rated this robustness-2: unlikely without a layout change, which release
discipline gates; the layout-version field is deferred to the first layout change.)

### Appending

An append programs the next position. Two details carry the safety. First, a value with
anything in the type byte is refused: it would turn into a different record. Second, the
position is consumed *even when the program fails*: a failed program may have left a torn
double-word, which can never be written again, so the next append moves on.

```c {#meta-append}
static int meta_append(uint32_t type, uint64_t value) {
 if (value >> 56) return -1;
 if (meta_pos >= META_DWORDS && meta_compact()) return -2;
 if (prog64(WS_PAGE_ADDR(meta_active) + 8 * meta_pos, (uint64_t)type << 56 | value)) { meta_pos++; return -3; }
 meta_pos++;
 return 0;
}
```

### Compaction: header last, and never under an old header

When the active page is full, the current maxima are rewritten as four fresh records into the
other page, which then becomes active with the next generation. The header is written *last*: until
it is, the new page is not a valid meta page and the current page stays authoritative; once it
is, the new page has the higher generation and carries every maximum.

There was a hole in the first version of this (firmware review finding 4, fixed as FW4 on
2026-10-14). The other page is not blank: it is the *previous* generation, with a valid header and
old values. Compaction erased it while that header was still there. An erase cut part way leaves
a partially erased page, and if the header survived the cut while some records were half-erased,
boot would trust the page and take the maximum of junk. A junk counter above 2^40 disables the
node for good, because WIPE keeps the counter. The fix is one program before the erase: zero the
old header. Programming all-zeros over written data is the one overwrite this flash allows, and a
zero header is not `WSM1`, so from that instant the other page is invisible to boot no matter how
its erase ends.

```text
step                                   other page as boot sees it    active page
1. program 0 over its old header       invalid (header 0)            authoritative
2. erase it                            invalid (erased / partial)    authoritative
3. program EPOCH, CTR, LOST, ABAND     invalid (no header yet)       authoritative
4. program header WSM1 | gen+1         valid, higher generation      valid, older
   -> RAM: active = other, pos = 5     (boot takes the max of both pages either way)
```

A cut at any step leaves the current page valid with every value, so the next boot simply
compacts again. The flash model cannot produce half-erased *values* (its partial erases leave
whole double-words old, erased or unreadable), so FW4 is a guard by construction; the sweeps
still pass through every step.

```c {#meta-compact}
/* Compact into the other page; its header is written last so a torn compaction
   leaves the current page authoritative. The other page still carries an older valid header:
   zero it first (programming all-zeros over data is allowed), so an erase cut part way can
   never leave half-erased values under a header boot would trust (firmware review finding 4). */
static int meta_compact(void) {
 uint32_t other = meta_active == WS_META_PAGE_A ? WS_META_PAGE_B : WS_META_PAGE_A;
 uint32_t a = WS_PAGE_ADDR(other);
 int bad = 0;
 if (rd64(a, &bad) != ERASED && prog64(a, 0)) return -1;
 if (erase_page(other) ||
     prog64(a + 8, (uint64_t)META_EPOCH << 56 | max_epoch) ||
     prog64(a + 16, (uint64_t)META_CTR << 56 | ctr_reserved) ||
     prog64(a + 24, (uint64_t)META_LOST << 56 | lost_total) ||
     prog64(a + 32, (uint64_t)META_ABAND << 56 | abandoned_total) ||
     prog64(a, (uint64_t)META_MAGIC << 32 | (meta_gen + 1))) return -1;
 meta_active = other; meta_gen++; meta_pos = 5;
 return 0;
}
```

(The header test reads `!= ERASED`: an unreadable header reads as 0 with `bad` set, which is not
erased, so it is zeroed too; `firmware/sim_flash.c` lets zeros go over a torn double-word, as it
does over any written one.)

### Using the log: persist first, then raise

Every user of the log follows one order: append the new value, and only if that succeeded,
raise the RAM copy and hand the value out. If the append fails nothing changes, so RAM never
shows a value the next boot would not restore. This order was not always kept: the harness's
error sweep found that `store_note_abandoned` raised `abandoned_total` before `meta_append`, so a
failed program made STATUS show a total that went *down* after the next reboot (fixed
2026-10-13; `test_bug_failed_abandon_note_lowers_total_after_reboot`).

**Epochs.** One per boot, before sampling: the observation identity is (epoch, sequence), so a
new epoch makes every identity of this boot new. `0xFFFFFFFF` is reserved for the bench storm
test (`app_tx.c` `STORM_EPOCH`, FW7), whose records the boot scrub acknowledges: a real boot must
never be given it, so the epoch stops one short.

```c {#next-epoch}
int store_next_epoch(uint32_t *epoch) {
 if (!meta_ready) return STORE_ENOTREADY;
 /* 0xFFFFFFFF is the bench storm test's epoch (app_tx.c STORM_EPOCH), whose records the boot
    scrub acknowledges: a real boot must never get it. */
 if (max_epoch >= 0xFFFFFFFEUL) return -1;
 if (meta_append(META_EPOCH, (uint64_t)max_epoch + 1)) return -2;
 *epoch = ++max_epoch;
 return 0;
}
```

**Epoch floor** (gap G5). After a WIPE the gateway supplies a floor above every epoch it has
stored for this station, so new observation identities can never collide with history. Values
only move up: a floor at or below the current epoch is accepted and changes nothing.

```c {#epoch-floor}
/* Gap G5: after a WIPE, the gateway supplies a floor above every epoch it has stored, so new
   observation identities can never collide with history. Values only move up. */
int store_epoch_floor(uint32_t floor) {
 if (!meta_ready) return STORE_ENOTREADY;
 if (floor <= max_epoch) return 0;
 if (meta_append(META_EPOCH, floor)) return -1;
 max_epoch = floor;
 return 0;
}
```

**Abandoned records** (gap G8): a record the gateway NACKed, or that hit the strike limit, is
dropped and counted, cumulatively across boots.

```c {#abandoned}
int store_note_abandoned(void) {
 if (!meta_ready) return STORE_ENOTREADY;
 if (meta_append(META_ABAND, (uint64_t)abandoned_total + 1)) return -1;
 abandoned_total++;
 return 0;
}
uint32_t store_abandoned_total(void) { return abandoned_total; }
```

**Counters.** One per transmission, so a record per counter would fill a meta page in 255
frames. Instead the log reserves counters in blocks of `CTR_BLOCK` (256): the record says
"everything up to here may have been used", and counters inside the block are handed out from
RAM. A reset throws away the rest of the block (init starts at `ctr_reserved + 1`), which costs
at most 255 counters of a 2^40 space and never repeats one. The frame header carries the counter
in 40 bits (`WS_COUNTER_MAX`); past that it would be truncated and repeat a nonce, so the store
refuses instead, permanently. A failed reservation hands out nothing: no durable reservation, no
counter, no transmission.

```c {#next-counter}
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
```

## 5. The observation journal

### Layout: a ring of pages of slots

The journal keeps every observation plaintext until the gateway acknowledges it. It is a ring of
`WS_JOURNAL_PAGES` pages (93 on the board, 3 in the host sweeps so that they wrap). Each page is an
8-byte header and as many fixed-size slots as fit:

```text
journal page (2048 B; default build: 35-byte plaintext -> 56-byte slots, 36 per page, 24 B spare)
+----------------------+--------+--------+-----+---------+-------+
| WSJ | slot size | seq| slot 0 | slot 1 | ... | slot 35 | spare |
|  (header, 8 B)       |  56 B  |  56 B  |     |   56 B  |       |
+----------------------+--------+--------+-----+---------+-------+

one slot
+------+------+------+------+------+------------------------+------------------+
| dw 0 | dw 1 | dw 2 | dw 3 | dw 4 | commit                 | ACK              |
|  plaintext, zero-padded to      | 0x4A53 | CRC16 | 0     | erased: pending  |
|  JOURNAL_PLAIN_DW double-words  | (magic)|(plain)| (low) | 0: acknowledged  |
+------+------+------+------+------+------------------------+------------------+
  +0                                COMMIT_OFF               ACK_OFF
```

The geometry follows the build's field set (`node_fields.h`): the widest catalog has 78-byte
plaintexts, 96-byte slots and 21 slots a page, and the host tests sweep that build too (a
geometry-specific bookkeeping slip once hid behind the default field set, 2026-10-14).

The page header's magic carries the slot size in its low byte (`"WSJ"` + size), so a page written
under another layout is simply not a journal page. Its low 32 bits are the page's *sequence*,
which grows by one for each page opened: the ring's head is the page with the highest sequence.

```c {#journal-constants}
#define JPG_MAGIC  (0x57534A00UL | JOURNAL_SLOT_BYTES) /* "WSJ" + slot size: another layout is ignored */
#define SLOT_MAGIC 0x4A53U
```

```c {#geometry}
/* Geometry the on-flash format depends on (node_store.h). */
#define SLOT_BYTES JOURNAL_SLOT_BYTES
#define COMMIT_OFF (JOURNAL_PLAIN_DW * 8U)
#define ACK_OFF (COMMIT_OFF + 8U)
```

All of that is checked at compile time, together with the page map, so a field added to the
catalog or a page moved in `flash_layout.h` cannot silently break the format (review P16):

```c {#geometry-checks}
_Static_assert(SLOT_BYTES == JOURNAL_PLAIN_DW * 8U + 16U && SLOT_BYTES >= WS_OBS_PLAIN_MAX + 16U,
               "slot = plaintext rounded to double-words + commit + ack double-words");
_Static_assert(SLOT_BYTES < 256U, "the slot size fits in the page magic's low byte");
_Static_assert(JOURNAL_SLOTS_PER_PAGE >= 1U && 8U + JOURNAL_SLOTS_PER_PAGE * SLOT_BYTES <= WS_PAGE_SIZE, "journal slots fit in one page");
_Static_assert((uint64_t)WS_CONFIG_PAGE * WS_PAGE_SIZE >= 0x10000U, "node state sits above the 64 KB firmware region (STM32WL55JCIX_FLASH.ld)");
_Static_assert(WS_CONFIG_PAGE < WS_META_PAGE_A && WS_META_PAGE_A < WS_META_PAGE_B && WS_META_PAGE_B < WS_JOURNAL_FIRST,
               "config, meta and journal pages are distinct and in order");
_Static_assert(WS_JOURNAL_PAGES >= 2U && WS_JOURNAL_FIRST + WS_JOURNAL_PAGES <= 128U, "journal fits in the 128 flash pages");
_Static_assert(WS_JOURNAL_PAGES <= 0xFFFFU && JOURNAL_SLOTS_PER_PAGE <= 0xFFFFU, "jref_t page and slot are 16-bit");
```

### The life of a slot

A slot is written three times at most, each a program over erased double-words, and its state is
read entirely from flash:

```text
               append: plaintext dws, then commit          ack: program 0
  erased  ------------------------------------>  pending  ------------------>  acknowledged
  (blank)                                       (commit ok,                    (ACK = 0)
     |                                           ACK erased)
     |  cut / failed program part way
     +-----------------------------------------> burned (torn or uncommitted: never reused)
```

At boot each slot is classified by what can be read back:

| Data and commit | ACK double-word | Boot says | Why |
|---|---|---|---|
| all erased | erased | blank | never written; the head may append here |
| readable, commit magic and CRC match | erased | **pending** | a complete record the gateway has not ACKed |
| readable, commit matches | 0 | acknowledged | done |
| readable, commit matches | unreadable (ECC) | acknowledged | the ACK program was interrupted: see below |
| unreadable, or commit wrong or missing | anything | burned | a torn append; counted in `store_journal_burned()` |

The commit double-word is the slot magic and a CRC-16 of the plaintext in the upper half, zeros
below. Boot compares only the upper half. The CRC makes the commit specific to *this* plaintext,
which matters after a partial page erase: a commit double-word that survived while the data
under it was erased (or the reverse) does not match and the slot is burned instead of pending
with junk.

The ACK row with an ECC fault is a deliberate choice. A torn ACK means power went while the
ACK was being programmed, and that program only starts after the gateway's authenticated ACK
arrived: the host had already committed the record. Treating the slot as acknowledged loses
nothing; treating it as pending would send it again.

```c {#crc}
static uint16_t crc16(const uint8_t *d, unsigned n) {
 uint16_t c = 0xFFFF;
 /* bound: n bytes (WS_OBS_PLAIN_MAX from the only caller), 8 bits each */
 while (n--) { c ^= (uint16_t)(*d++ << 8); for (int b = 0; b < 8; b++) c = (c & 0x8000) ? (uint16_t)(c << 1 ^ 0x1021) : (uint16_t)(c << 1); }
 return c;
}
/* The commit double-word: magic and the plaintext CRC in the upper half, zeros below. */
static uint64_t slot_commit_word(const uint8_t plain[WS_OBS_PLAIN_MAX]) {
 return (uint64_t)SLOT_MAGIC << 48 | (uint64_t)crc16(plain, WS_OBS_PLAIN_MAX) << 32;
}
```

(GCC 15 turns bitwise CRC loops like this one into lookup tables, 768 B together with
`stage0.c`'s `ws_crc8`; they run a few times a minute, so the Makefile builds this file with
`-fno-optimize-crc` and keeps the loop.)

### RAM state

The journal's RAM state is rebuilt from flash at every boot and describes it exactly:
`page_seq[p]` is page p's sequence (0: not a journal page), `pending` is one bit per slot of the
whole ring, `head`/`head_slot` is where the next append goes. `n_lost` and `n_burned` are
since-boot counts; `lost_total` (in the meta log) is the persisted one.

A slot is named by a `jref_t`, its page and slot number. One comes only from this file (append,
oldest, find), so it is always a slot of the journal; the entry points that take one still check.

```c {#journal-state}
/* ---- journal ---- */
static uint32_t page_seq[WS_JOURNAL_PAGES];
static uint8_t pending[(JOURNAL_CAPACITY + 7) / 8];
static uint32_t head, head_slot, n_pending, n_lost, n_burned;
```

```c {#journal-helpers}
static uint32_t slot_index(jref_t r) { return (uint32_t)r.page * JOURNAL_SLOTS_PER_PAGE + r.slot; }
static int is_pending(uint32_t i) { return pending[i >> 3] >> (i & 7) & 1; }
static void set_pending(uint32_t i, int on) {
 if (on) pending[i >> 3] |= (uint8_t)(1U << (i & 7)); else pending[i >> 3] &= (uint8_t)~(1U << (i & 7));
}
static uint32_t slot_addr(uint32_t page, uint32_t slot) {
 return WS_PAGE_ADDR(WS_JOURNAL_FIRST + page) + 8 + slot * SLOT_BYTES;
}
```

### Appending a record

The append is the commit-last rule again, with the commit double-word after the plaintext:

```text
1. head full?  -> open the next page (recycle, below)
2. ref = (head, head_slot); head_slot++        <- the slot is consumed now
3. program plaintext dw 0 .. JOURNAL_PLAIN_DW-1
4. program the commit dw (magic | CRC16)        <- the record exists from here
5. RAM: mark pending
```

The slot is consumed before anything is programmed: if a program fails part way, the slot may
hold a torn double-word that can never be written again, so it is never reused and counts as
burned. It also needs `meta_ready`, because a wrap may have to persist the lost total.

```c {#journal-append}
int store_journal_append(const uint8_t plain[WS_OBS_PLAIN_MAX], jref_t *ref) {
 uint64_t d[JOURNAL_PLAIN_DW] = { 0 };
 if (!meta_ready || !journal_ready) return STORE_ENOTREADY; /* a wrap persists the lost total */
 if (journal_advance_if_full()) return -1;
 uint32_t a = slot_addr(head, head_slot);
 ref->page = (uint16_t)head; ref->slot = (uint16_t)head_slot;
 head_slot++; /* consumed even if programming fails: never reuse a possibly torn slot */
 memcpy(d, plain, WS_OBS_PLAIN_MAX);
 for (uint32_t k = 0; k < JOURNAL_PLAIN_DW; k++)
  if (prog64(a + 8 * k, d[k])) { n_burned++; return -2; }
 if (prog64(a + COMMIT_OFF, slot_commit_word(plain))) { n_burned++; return -2; }
 set_pending(slot_index(*ref), 1); n_pending++;
 return 0;
}
```

### Opening a page: count the losses before the erase

When the head page is full, the next page of the ring is opened. That page is the *oldest* one,
and it may still hold pending records: the ring is full and the oldest records are overwritten.
That is a loss, and it must be counted durably *before* the erase destroys the evidence. The
order:

```text
1. count the pending slots on the page (dropped)
2. if dropped: meta_append(LOST, lost_total + dropped)   -- fails -> return -1, nothing changed
3. RAM: clear their pending bits, add to the totals; page_seq = 0
4. erase the page
5. program its header: WSJ|size, seq = previous head's seq + 1
```

The second step's failure path is another bug the error sweep found (2026-10-13,
`test_bug_failed_lost_persist_still_erases_page`): the first version ignored a failed
`meta_append(META_LOST)` and erased the page anyway, so the records were gone while the persisted
total never counted them. Now a failed persist fails the append and keeps the page and its
records.

A cut between the persist and the erase over-counts (the records are still there, pending, and
the lost total already includes them): that direction is allowed, and the sweep notes it as
`note_lost_back`. A cut during the erase or the header program is the dangerous one: the page may
keep its old header and some old slots, or have no readable header at all. Either way the head is
still the full page before it, and that is what boot uses to repair it (next section).

```c {#journal-new-page}
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
```

The rule "open a page only when the head is full" lives in one place, used by the append and,
for a reason that comes next, by boot:

```c {#journal-advance}
/* Opens a fresh page after the head once the head is full (append, and init after a cut). */
static int journal_advance_if_full(void) {
 if (head_slot < JOURNAL_SLOTS_PER_PAGE) return 0;
 uint32_t next = (head + 1) % WS_JOURNAL_PAGES;
 if (journal_new_page(next, page_seq[head] + 1)) return -1;
 head = next; head_slot = 0;
 return 0;
}
```

### Boot: rebuilding the journal from flash

Boot reads every page header. The head is the page with the highest sequence (the later page on
a tie); an unreadable or foreign header makes a page not a journal page.

```c {#journal-find-head}
/* Reads every page header into page_seq (0: not a journal page) and points head at the
   highest sequence, the later page on a tie. Returns 0 when no page is a journal page. */
static int journal_find_head(void) {
 uint32_t best = 0; int found = 0;
 for (uint32_t p = 0; p < WS_JOURNAL_PAGES; p++) {
  int bad = 0; uint64_t h = rd64(WS_PAGE_ADDR(WS_JOURNAL_FIRST + p), &bad);
  page_seq[p] = (!bad && (h >> 32) == JPG_MAGIC && (uint32_t)h) ? (uint32_t)h : 0;
  if (page_seq[p] && page_seq[p] >= best) { best = page_seq[p]; head = p; found = 1; }
 }
 return found;
}
```

Then every slot of every journal page is classified by the table above. A slot that is not blank
is *used*, whatever its state: on the head page the next append goes after the last used slot,
never into a burned one.

```c {#journal-scan-slot}
/* Boot scan of one slot: 0 if blank, else 1 after counting it burned (torn or unreadable data)
   or, when committed and not acknowledged, pending. */
static int journal_scan_slot(uint32_t p, uint32_t s) {
 uint32_t a = slot_addr(p, s); int bad_data = 0, bad_ack = 0, erased = 1; uint64_t d[JOURNAL_PLAIN_DW + 1], ack;
 for (uint32_t k = 0; k <= JOURNAL_PLAIN_DW; k++) { d[k] = rd64(a + 8 * k, &bad_data); erased &= d[k] == ERASED; }
 ack = rd64(a + ACK_OFF, &bad_ack);
 if (!bad_data && !bad_ack && erased && ack == ERASED) return 0;
 uint8_t plain[WS_OBS_PLAIN_MAX]; memcpy(plain, d, sizeof plain);
 /* A torn ACK word (ECC) means the ACK program was interrupted after the host committed: acked. */
 if (bad_data || (d[JOURNAL_PLAIN_DW] >> 32) != (slot_commit_word(plain) >> 32)) n_burned++;
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

The last step of init closes the hole the power-cut sweep found first (2026-10-13,
`test_bug_interrupted_recycle_resurrects_acked_record`). Picture the ring when the head page has
just filled and an append is opening the next page: it erases the oldest page, which holds
acknowledged records. Cut that erase part way, and some slots can have their ACK double-word
erased while their data and commit survive. Boot reads such a slot as *pending*, and an
acknowledged record is sent again.

The fix: if the head page is full, the next page's recycle may have been cut, so boot *finishes
it* (with `journal_new_page`, counting its pending records as lost, which the next append would
have done anyway) before it trusts that page. A page after a non-full head was never touched by a
recycle, so its slots are as they were written.

```c {#journal-init}
int store_journal_init(void) {
 journal_ready = 0;
 memset(pending, 0, sizeof pending); n_pending = n_lost = n_burned = 0;
 if (!journal_find_head()) {
  head = 0; head_slot = 0;
  if (journal_new_page(0, 1)) return -1;
  journal_ready = 1;
  return 0;
 }
 for (uint32_t p = 0; p < WS_JOURNAL_PAGES; p++) {
  if (!page_seq[p]) continue;
  uint32_t last_used = journal_scan_page(p);
  if (p == head) head_slot = last_used;
 }
 /* The head is full, so the next page's recycle may have been cut mid-erase, which can wipe
    an ACK word but leave its record: finish the recycle before trusting that page. */
 if (journal_advance_if_full()) return -1;
 journal_ready = 1;
 return 0;
}
```

### Reading and acknowledging

A read returns the plaintext of a slot, or fails if any of it is unreadable (the caller
reports `#error journal-read` and moves on).

```c {#journal-read}
/* A jref_t comes only from this file (append, oldest, find): always a slot of the journal. */
static int ref_in_journal(jref_t r) { return r.page < WS_JOURNAL_PAGES && r.slot < JOURNAL_SLOTS_PER_PAGE; }
int store_journal_read(jref_t ref, uint8_t plain[WS_OBS_PLAIN_MAX]) {
 if (!WS_CHECK(ref_in_journal(ref))) return -1;
 uint32_t a = slot_addr(ref.page, ref.slot); int bad = 0; uint64_t d[JOURNAL_PLAIN_DW];
 for (uint32_t k = 0; k < JOURNAL_PLAIN_DW; k++) d[k] = rd64(a + 8 * k, &bad);
 if (bad) return -1;
 memcpy(plain, d, WS_OBS_PLAIN_MAX);
 return 0;
}
```

An ACK programs zero into the slot's ACK double-word, then clears the pending bit. Flash first:
if the program fails the record stays pending and will be sent again, which the gateway
deduplicates; the other order could forget a record that flash still says is pending, and the
next boot would send it anyway. Acknowledging a slot that is not pending is a no-op, so a
duplicate ACK is harmless.

```c {#journal-ack}
int store_journal_ack(jref_t ref) {
 if (!journal_ready) return STORE_ENOTREADY;
 if (!WS_CHECK(ref_in_journal(ref))) return -1;   /* before it indexes pending[] */
 uint32_t i = slot_index(ref);
 if (!is_pending(i)) return 0;
 if (prog64(slot_addr(ref.page, ref.slot) + ACK_OFF, 0)) return -1;
 set_pending(i, 0); n_pending--;
 return 0;
}
```

### Finding pending records

The exchange sends backlog oldest first. The oldest page is the one after the head, so the walk
starts at `head + 1` and ends with the head page itself; within a page, slot order is append
order. `except` skips the record the exchange is already sending.

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

An ACK names a record by its identity, (epoch, sequence), which are the plaintext's first 8 bytes
in big-endian order. `next_pending_match` is the one search, shared by find (epoch and sequence)
and scrub (epoch only). It compares against flash, not a RAM copy, and a slot whose first
double-word is unreadable never matches.

```c {#journal-find}
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
```

The scrub acknowledges every pending record of one epoch. Boot uses it for the bench storm
test's epoch (`STORM_EPOCH`): the storm fills the journal with records that must never be sent.
The loop's bound is the argument Power of Ten rule 2 asks for, and `tools/loop_bounds.py` wants
it written next to the loop: each match moves `i` past its slot, and no slot is found at or past
`JOURNAL_CAPACITY`, so there are at most that many passes.

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

The read-only accessors feed the console (`tx_console.c`), the `#sample` line and the DIAG health
report (`tx_exchange.c`). Only the lost total is persisted; burned and ECC faults count since
boot.

```c {#accessors}
uint32_t store_journal_pending(void) { return n_pending; }
uint32_t store_journal_lost(void) { return lost_total; } /* cumulative, persisted */
uint32_t store_journal_burned(void) { return n_burned; }
uint32_t store_ecc_faults(void) { return n_ecc; }
uint64_t store_counter_next(void) { return ctr_next; }
```

## 6. WIPE: the key and the journal go, the meta log stays

WIPE de-provisions the board: it erases the key and the journal. It never erases the meta log
(gap G17, review P1, rated critical). The first version erased both meta pages, so after a WIPE
the transmission counter restarted at 1; with the same key provisioned again, that is nonce
reuse, and the gateway had no per-node counter high-water mark to notice. Now the counter, the
boot epoch and the lost/abandoned totals keep rising for the life of the board. A key first used
under this firmware can therefore follow the board across WIPEs; a key used under older firmware
(which reset the counter) or on another board cannot (`docs/runbook-moving-boards.md`).

The order of the erases is the third fix the power-cut sweep produced (2026-10-13,
`test_bug_interrupted_wipe_leaves_journal_on_unprovisioned_board`). The first version erased the
config page first: a cut after the key was gone left an unprovisioned board whose journal still
held pending records, and after the next PROVISION they went out under the new station identity.
So the journal goes first and the key last, and if any journal erase failed the key is kept: a
board that still has its key is visibly not wiped, and the operator, who never saw `#wipe ok`,
runs WIPE again. (An interrupted WIPE may leave acknowledged records readable and pending again,
`note_acked_back_after_interrupted_wipe` in the sweep: the store does not promise anything about a
WIPE that did not finish.)

```text
journal_ready = 0           RAM no longer describes flash
erase journal pages 35..127 any failure -> return -1, key kept
erase config page 32        the board is unprovisioned only now
```

```c {#wipe}
/* WIPE erases the key and the journal but never the meta log (gap G17): the counter (the AES-CCM
 * nonce), the boot epoch and the lost/abandoned totals keep rising for the life of the board. */
int store_wipe(void) {
 int rc = 0;
 journal_ready = 0; /* the RAM journal no longer describes flash: store_journal_init again */
 for (uint32_t p = 0; p < WS_JOURNAL_PAGES; p++) rc |= erase_page(WS_JOURNAL_FIRST + p);
 if (rc) return -1; /* keep the key: an unprovisioned board must not carry old records */
 return erase_page(WS_CONFIG_PAGE) ? -1 : 0;
}
```

## 7. The file

The generated file puts the pieces in C's order: constants and compile-time checks, the flash
wrappers, then provisioning, the meta log and the journal, each below the state it uses.

```c {#node_store.c}
<<abstract>>
#define WS_CHECK_FILE 5
#include "node_store.h"
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

## 8. How this is tested

The proof that the argument above holds is the host power-cut harness, not the prose.
`firmware/test_store.c` runs a scripted workload over `firmware/sim_flash.c` (provision, boot
epochs, counter blocks, journal appends and ACKs, abandons, two meta compactions, a journal wrap
with losses, the storm scrub, WIPE), and then:

- **sweep**: once per flash operation index, cuts the power at that operation with every outcome
  the model has (program: old, new, torn; erase: none, all, two random partial patterns, partial
  with unreadable double-words), reboots and checks every invariant of section 1;
- **errsweep**: once per operation index, makes that operation fail like a HAL error (flash
  unchanged, or left torn / partially erased) and lets the workload carry on;
- three geometries: the board's 93-page journal, a 3-page journal so the sweeps wrap, and the
  widest slot the field catalog allows.

`tests/test_store_powercut.py` builds and runs all of them, with ASan and UBSan, and fails on any
violation category it does not list as a note. The three regression tests named above
(interrupted recycle, interrupted WIPE, failed persists) each keep the bug they found from
returning.
