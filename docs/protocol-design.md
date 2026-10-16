# Protocol draft 5: design

**Status:** design, revision 2 (2026-10-14). **Implemented on `master`** in commits `6f52a51`
(catalog), `0d5ebc2` (envelope), `5dbe2d9` (gateway decoding), `51ae971` (node encoder and
journal), `a4f1d08` (32-byte DIAG), `dd49609` (replay vs key reuse) and `bc5e6ed` (per-field Home
Assistant discovery). Released as `bc5e6ede429c` and flashed to both boards on 2026-10-14 with a
new key (`firmware/stage0-node/RELEASES.md`). The normative specification is
[`protocol.md`](protocol.md); this file keeps the design rationale. Where the implementation differs
from the text below, the code and `protocol.md` win. Known differences:
- the journal page magic is `"WSJ"` + the slot size in its low byte (`WSJ0` for 48-byte slots), not
  a fixed `WSJ2` (§7), so a field-set change that changes the slot size also retires old pages;
- the RX filter is fuzzed through the existing `console` target, not a new `fuzz_air`; the new
  target is `obs` (the encoder) (§6);
- the pre-decryption length check for an observation (gateway and RX filter) allows any catalog
  length, 39–85 bytes (plaintext 23–69: at least one 1-byte field, at most every field), not the
  build's `WS_OBS_PLAIN_MAX` (§3.4); the exact length is checked after decryption as designed;
- the C/Python catalog cross-checks live in `tests/test_obs.py`, not `tests/test_frame.py` (§6);
- the gateway accepts any calibration revision 0–255; it does not yet check it against a configured
  maximum (§5.6);
- the TX `STATUS` line still prints `ctr` as a 32-bit value (§7).

Revision 2 folds in four parallel reviews (security, encoding, implementation fit, requirements and
simplicity) and Clint's decisions:
- introduce draft 5 **before H01**;
- **8-byte** CCM tag;
- **compact 8-byte header**;
- **byte-aligned** fields: bit-packing saved no airtime, because LoRa sends whole symbol blocks;
- battery and solar telemetry go **inside the observation**, not in a separate frame kind;
- greenfield: **no backward compatibility**.

H01 runs on this draft. When H01 passes, the PRD freezes the identity, time and quality contract
(PRD §12, H01).

## 1. Goals

1. One frame per minute carries everything the proof-of-concept station measures now and the PRD's
   Core set later (R01), with room to spare.
2. Little fixed overhead. Draft 4 spent 32 of its 56 bytes on the header and tag, on every frame,
   ACKs included.
3. Each value has time, unit and validity (R10). One dead sensor never hides the others.
4. Get the identity, time and quality contract right now, because H01 freezes it.
5. Keep the security properties of draft 4. The one deliberate weakening is the forgery bound of the
   shorter tag (§3.3).

## 2. Sizes and airtime

LoRa at 500 kHz, CR 4/5, 8-symbol preamble, explicit header, CRC on (`protocol-stack.md` §8.2).
Airtime moves in steps: about every 3–4 bytes at SF7 and every 6 bytes at SF12.

| Frame | Draft 4 | Draft 5 | SF7 | SF12 |
|---|---:|---:|---:|---:|
| Observation, T/RH with the minute summary (the Stage-0 build) | — | **51 B** | 25.7 ms | 534.5 ms |
| Observation, T/RH only (the first draft-5 build) | 56 B | 42 B | 21.8 ms | 452.6 ms |
| Observation, PRD Core weather set | — | 56 B | 26.9 ms | 575.5 ms |
| Observation, full PoC build (weather + battery + enclosure, §5.5) | — | 78 B | 34.6 ms | 698.4 ms |
| ACK / NACK | 56 B | **33 B** | 18.0 ms | 411.6 ms |
| DIAG | 56 B | 48 B | 24.4 ms | 493.6 ms |

At SF12 a full PoC exchange costs 2 × 698 + 300 ms = 1.7 s. That fits under even the 2 s CONSERVE
airtime cap (`radio-energy-policy.md`).

## 3. Envelope

### 3.1 Layout

| Offset | Bytes | Field | Protection |
|---:|---:|---|---|
| 0 | 1 | High nibble: version = **5**. Low nibble: kind (1 OBS, 2 ACK, 3 NACK, 4 DIAG) | Authenticated, clear |
| 1 | 2 | Station ID, u16, 1–65535 | Authenticated, clear |
| 3 | 5 | Transmission counter, u40 | Authenticated, clear |
| 8 | *n* | AES-128-CCM ciphertext of the kind's plaintext | Encrypted and authenticated |
| 8 + *n* | 8 | CCM tag, **M = 8, a fixed constant**. It is never inferred from the frame length | — |

- **AAD:** the 8 header bytes. Every integer is big-endian.
- **Version:** any version other than 5, and any unassigned kind (0, 5–15), is dropped silently. A
  draft-4 frame starts with `0x57` ('W'), so it reads as version 5, kind 7, and is dropped.

### 3.2 Nonce and counter

- **Nonce (13 bytes):** the kind as an integer (1 byte) + the station ID as a big-endian u32 + the
  counter as a big-endian u64. It is built **from the integers**, never copied from the header bytes.
  This is the same construction as draft 4.
- **Two counter spaces:**
  - the node's flash counter, used by OBS and DIAG;
  - the gateway's nonce database, used by ACK and NACK.

  The kind byte keeps the two spaces apart.
- **Counter range: 1 to 2^40 − 1, enforced in three places on each side:**
  1. the node's allocator `store_next_counter` and the gateway's `Nonces.next` both refuse to issue
     a counter at or past 2^40;
  2. the seal routine (`ws_seal_kind` in C, `seal()` in Python) rejects an out-of-range counter
     itself;
  3. Python writes the counter with `to_bytes(5, 'big')`, which raises on overflow, and never masks.

  **Why all three:** a 5-byte header field truncates silently. Without these checks, a counter at or
  past 2^40 would go on air as a small counter, which is nonce reuse and a total loss of security.
- **Lifetime:** 2^40 frames is more than 100,000 years at 20 frames per minute. Even a reboot loop
  once a second, skipping a 256-counter block each time, lasts about 136 years.
- **New key at release:** the draft-5 release uses a **new key and fresh state**: a new run
  directory, a new gateway nonce database, and a WIPE plus PROVISION on the node. It never keeps
  the draft-4 key. CCM's keystream blocks encode only L, not M, so any cross-version counter overlap
  would reuse keystream. A fresh key rules that out at no cost.

### 3.3 Tag length

M = 8 gives a forgery probability of 2^-64 per attempt. RFC 3610 allows M from 4 to 16. NIST SP
800-38C allows 64-bit tags and, in Appendix B, ties the tag length to the number of forgery
attempts an attacker gets.

Attempts here are online and limited by airtime. Continuous jamming at SF7 allows about 50 attempts
per second, and 2^64 attempts would take about 10^10 years. The node also listens only in short ACK
windows. Truncated CBC-MAC has no GCM-style attack on short tags.

### 3.4 Length checks

| Check | Before decrypting (silent drop) | After decrypting (NACK reason 2 for OBS) |
|---|---|---|
| OBS | 8 + 22 + 0 … 8 + `WS_OBS_PLAIN_MAX` + 8 | The exact length the field bitmap gives (§5.4) |
| DIAG | 48 | — |
| ACK / NACK | 33 | — |

A frame that fails before authentication is never answered, as in draft 4.

### 3.5 RX bridge

The bridge holds no key. It forwards upstream:
- frames whose first byte is `0x51` (OBS) with an OBS-range length;
- frames whose first byte is `0x54` (DIAG) with length 48.

It accepts downstream exactly 33 bytes with a first byte of `0x52` or `0x53`. This filter moves into
`ws_console.c` (`ws_air_frame_ok`, `ws_host_reply_ok`), so it is host-tested and fuzzed.

### 3.6 What an eavesdropper sees

The kind, station ID, counter, frame length and timing. A field's presence never depends on a
reading (§5.1), so the length doesn't reveal sensor faults. Everyone can tell a NACK from an ACK by
its kind byte, as in draft 4.

## 4. Fixed plaintexts

**ACK (kind 2), 17 bytes:** epoch u32 · sequence u32 · host UTC u32 (0 when the gateway measured its
own clock as wrong) · echoed observation counter u40.

**NACK (kind 3), 17 bytes:** epoch u32 · sequence u32 · reason u32 (1 identity collision, 2 invalid
record) · echoed counter u40. The node stops retrying that record and counts it as `abandoned`.

The node's reply API becomes `ws_open_reply(…, uint32_t *epoch, uint32_t *seq, uint32_t *word,
uint64_t *echo)`, where `word` is the UTC or the reason.

**DIAG (kind 4), 32 bytes, every 15 min and on each link-state change:**

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 4 | Epoch |
| 4 | 4 | Uptime (s) |
| 8 | 2 | Journal pending |
| 10 | 4 | Journal lost total |
| 14 | 2 | Torn slots |
| 16 | 2 | Abandoned total |
| 18 | 2 | Missed ACKs since boot |
| 20 | 2 | Rejected replies since boot |
| 22 | 1 | Reset cause |
| 23 | 1 | Link state |
| 24 | 4 | **Firmware build ID:** the first 4 bytes of the release commit hash |
| 28 | 1 | **RSSI** of the last ACK, as heard by the node: signed dBm; −128 = none yet |
| 29 | 1 | **SNR** of the last ACK: signed dB; −128 = none yet |
| 30 | 1 | **Crash record count** (`fault.c`, TAMP DR11, saturating) |
| 31 | 1 | **Energy state** (§5.2) |

16-bit counters saturate at `0xFFFF`. Reset-cause and link-state codes are as in draft 4.

## 5. Observation (kind 1)

### 5.1 Layout

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 4 | Epoch u32 (boot epoch, durable) |
| 4 | 4 | Sequence u32 within the epoch |
| 8 | 4 | Sample UTC u32; **0** if time unknown |
| 12 | 4 | Uptime u32 (s since boot) |
| 16 | 1 | Flags: bit 0 time known (must equal UTC ≠ 0) · bits 1–2 energy state at sampling (§5.2) · bits 3–7 zero |
| 17 | 1 | Calibration revision u8 (§5.6) |
| 18 | 4 | Field bitmap u32: field *i* is present when `(bitmap >> i) & 1` (T/RH alone = `0x00000003`) |
| 22 | *k* | Present fields in increasing *i*, each a big-endian unsigned integer of its catalog width |

**Presence rule:**
- Which fields are present depends only on the build's configuration, plus at most a fixed
  schedule keyed on the sequence number. For example, the power fields can be sent every 5th
  sequence.
- Presence never depends on a reading. A faulted field is sent with its INVALID code, never left
  out. "Absent" means "not sent in this record by design".
- A bitmap of 0 is rejected.

**Every observation covers exactly one minute**, in every energy state:
- **NORMAL / SURPLUS:** the node transmits each minute's record and drains the backlog.
- **CONSERVE:** it journals every minute and transmits only the latest record every 300 s.
- **CRITICAL:** it journals and doesn't transmit.

The energy-state bits record the **reporting mode** (PRD R02). The gateway takes the current mode
from the newest record by identity order, not from backfilled ones.

### 5.2 Energy-state codes

These are the firmware's existing `energy_t` and `ws_link_may_send` numbering:

| Code | State |
|---:|---|
| 0 | SURPLUS |
| 1 | NORMAL |
| 2 | CONSERVE |
| 3 | CRITICAL |

The Stage-0 build always sends 1 (NORMAL).

### 5.3 Field catalog v1

**Encoding rules for every field:**
- The code is `round_half_up((x − min) / step)`. It is computed in integer arithmetic from the
  sensor's raw counts wherever possible, so C and Python can't disagree on half-way values.
- The **all-ones code is INVALID**: no sample, a sensor fault, or out of range.
- **Out-of-range readings become INVALID, never clamped.** The only exception is RH, which is
  clamped to 0–100 % (Sensirion practice, as the firmware already does).
- Codes above the field's maximum are rejected, except the field's listed special codes.
- **Decoding is exact:** `(code − offset_code) / scale`, with an integer offset in code units.
  Every code round-trips, so no floating-point noise reaches the stored JSON.
- **Counters** (`rain_tips` and the energy and charge counters) are **since-boot** counts: each
  starts at 0 when its epoch starts.
  - The gateway totals them across epochs: the sum of each epoch's last value.
  - Within one epoch they must not decrease **in sequence order**. The gateway compares each record
    with its stored neighbours by sequence, never by arrival order, so backfill is safe. A decrease
    is NACK reason 2.
  - Per-tip power-cut durability (H06) is a later firmware change. Until then, tips counted after
    the last journaled minute before a power cut can be lost (up to about 59 s of tips).

| *i* | Field | Bytes | Unit / step | Range (codes) | Special codes | First build |
|---:|---|---:|---|---|---|---|
| 0 | `temperature_c` | 2 | 0.01 °C, offset −40.00 | −40.00 to 125.00 (0–16500) | 0xFFFF INVALID | **Stage 0** |
| 1 | `humidity_pct` | 2 | 0.01 % | 0 to 100.00 (0–10000) | 0xFFFF INVALID | **Stage 0** |
| 2 | `pressure_hpa` | 2 | 0.1 hPa, offset 300.0 | 300.0 to 1100.0 (0–8000) | 0xFFFF INVALID | PoC (BMP581) |
| 3 | `wind_speed_ms` | 2 | 0.1 m/s | 0 to 75.0: scalar mean over the minute | 0xFFFF INVALID | PoC (SEN-15901) |
| 4 | `wind_gust_ms` | 2 | 0.1 m/s | 0 to 75.0: highest rolling 3-s mean in the minute | 0xFFFF INVALID | PoC |
| 5 | `wind_dir_deg` | 2 | 1° | 0 to 359: unit-vector mean, wraps mod 360 | 0xFFFE CALM (mean speed < 0.5 m/s); 0xFFFF INVALID (also required whenever the speed is INVALID) | PoC |
| 6 | `rain_tips` | 3 | tips since boot | 0 to 16,777,214 | 0xFFFFFF INVALID | PoC (0.2794 mm per tip, set in the gateway config) |
| 7 | `uv_index` | 1 | 0.1 UVI | 0 to 25.0 (0–250) | 0xFF INVALID | Only from a sensor qualified for UV index (H07) |
| 8 | `irradiance_wm2` | 2 | 1 W/m² | 0 to 2000 | 0xFFFF INVALID | Optional module |
| 9 | `uva_raw` | 3 | sensor counts (gain and integration time fixed per build, set in the gateway config) | 0 to 2^20 − 1 | 0xFFFFFF INVALID | PoC (LTR390). **Never reported as UV index** (PRD §9, H07) |
| 10 | `qualifiers` | 4 | 2 bits per field 0–15: 0 ok, 1 suspected icing, 2 delayed melt, 3 outside the qualified envelope | — | — (never INVALID) | Stage 3 (R10) |
| 11 | `batt_mv` | 2 | 1 mV | 0 to 65534 | 0xFFFF INVALID | PoC (INA228) |
| 12 | `batt_current_ma` | 2 | 0.1 mA, offset binary (`code = I + 32768`), **positive = into the cells**, mean over the minute | −3276.8 to +3276.6 mA | 0xFFFF INVALID | PoC (INA228) |
| 13 | `energy_in_mwh` | 3 | mWh since boot, integrated from **signed** V × I in firmware (the INA228 ENERGY register is unsigned) | 0 to 16,777,214 | 0xFFFFFF INVALID | PoC |
| 14 | `energy_out_mwh` | 3 | as above, discharge | as above | 0xFFFFFF INVALID | PoC |
| 15 | `charge_in_mah` | 3 | mAh since boot | as above | 0xFFFFFF INVALID | PoC |
| 16 | `charge_out_mah` | 3 | mAh since boot | as above | 0xFFFFFF INVALID | PoC |
| 17 | `soc_gauge_pct` | 1 | 1 %, **fuel-gauge estimate** (MAX17048 voltage model; not a calibrated SOC, PRD §5) | 0 to 100 | 0xFF INVALID | PoC |
| 18 | `charger_pins` | 1 | raw bq24074 pins: bit 0 PGOOD (input power good), bit 1 CHG (charging); bits 2–7 zero | 0 to 3 | 0xFF INVALID | PoC |
| 19 | `enclosure_temp_c` | 2 | as `temperature_c` | as field 0 | 0xFFFF INVALID | PoC (SHTC3) |
| 20 | `enclosure_rh_pct` | 2 | as `humidity_pct` | as field 1 | 0xFFFF INVALID | PoC (SHTC3) |
| 21–31 | reserved | — | — | must be zero | — | — |

T/RH use the 60-s mean of the minute's samples, or the single sample while the node samples once a
minute (Stage 0). Each record states which: the calibration revision maps to the sampling
description in the gateway config.

### 5.4 One valid encoding per reading

The gateway rejects (NACK reason 2) an authenticated observation that:
- has a length other than 22 + the sum of the present fields' widths;
- has a non-zero reserved flag bit or reserved bitmap bit (21–31), or a bitmap of 0;
- has a code above its field's maximum that is not one of that field's special codes;
- has a `wind_dir_deg` that isn't INVALID while `wind_speed_ms` is INVALID;
- has time known ≠ (UTC ≠ 0);
- has a counter that decreases in sequence order within its epoch (§5.3);
- fails the existing identity and time checks (collision; more than 5 s ahead of receipt is
  quarantined).

Gateway and node share one catalog and ship together, so an unknown bit is a bug, not a newer node.

### 5.5 Builds

The node's configuration header (`firmware/stage0-node/App/node_fields.h`) names the build's fields
with one constant:

```c
#define WS_NODE_FIELDS (WS_F_TEMPERATURE_C | WS_F_HUMIDITY_PCT)   /* Stage 0 */
```

`WS_OBS_PLAIN_MAX` = 22 + the sum of those fields' widths.

The journal stores `WS_OBS_PLAIN_MAX` bytes per slot, plus the commit word and the ACK word:
`SLOT_BYTES = roundup8(WS_OBS_PLAIN_MAX) + 16`. The record's actual length comes from its own
bitmap when it is read back.

| Build | Plaintext | Frame | Slot | Records (93 pages) | Outage buffer |
|---|---:|---:|---:|---:|---:|
| Stage 0 (T/RH with the minute summary) | 35 B | 51 B | 56 B | 3,348 | 2.3 days |
| Full PoC (fields 0–6, 9, 11–20) | 62 B | 78 B | 80 B | 2,325 | 1.6 days |

The smaller buffer is accepted for the proof of concept. The 30-day buffer comes with the SPI-NOR
journal (H11).

### 5.6 Calibration revision

One revision per station, starting at 0 and only increasing (never wrapping). It names a calibration
and sampling set kept in the gateway config. The node applies the calibration. The gateway accepts
any revision up to the highest one configured. Stage 0 = 0.

### 5.7 Gateway record

The stored JSON has `version: 5`, `station`, `session`, `sequence`, `sampled_at`, `uptime_s`,
`time_quality`, `energy_state` (string: `surplus`, `normal`, `conserve` or `critical`),
`calibration_revision`, `quality`, and each present field:
- an INVALID field is `null`;
- a CALM direction is `null`, with `wind_calm: true`. `wind_calm` is always present, true or false,
  whenever `wind_dir_deg` is;
- qualifiers become a `qualifiers` object holding only the non-ok fields.

**Quality is per field.** The record-level `quality` is only a convenience:
- `valid`: every present field is valid (CALM counts as valid);
- `partial`: some present fields are INVALID;
- `sensor_fault`: all present fields are INVALID.

Availability in `/v1/observations/latest` and MQTT is decided per field, so a dead UV sensor never
hides the temperature. **H01 scoring uses the validity of the T/RH fields.**

`gateway.validate` becomes catalog-driven and replaces the draft-4 closed schema. The version-1/2
branches and their table migrations are deleted (greenfield). Units and CSV columns come from the
catalog.

## 6. Code

- **One hand-written table per side,** cross-checked by tests instead of generated from a shared
  file:
  - C `firmware/common/ws_obs.{c,h}`: the catalog widths, maxima and INVALID codes, and the encoder;
  - Python `ws0/fields.py`: the same table plus unit and Home Assistant metadata, and the decoder.
- **Cross-check tests** (`tests/test_frame.py`):
  - the C encoder and the Python decoder agree on random readings for every field and every bitmap
    subset, including INVALID, CALM and the range edges;
  - every code decodes and re-encodes exactly;
  - every non-canonical mutation in §5.4 is rejected.
- **Known-answer vectors:** a non-crypto encoding vector shared by C and Python (T = −12.34 °C,
  RH = 45.67 %), plus a new crypto known-answer vector (M = 8) for the node's boot self-test.
- **Fuzzing:**
  - `fuzz_reply` gets 33-byte ACK and NACK vectors;
  - a new C target, `fuzz_air`, covers `ws_air_frame_ok` and the encoder's length rule;
  - Python decoding gets a seeded random-mutation test.
  - New targets are registered in `firmware/fuzz/Makefile`, `tests/test_fuzz.py` and the CI
    libFuzzer loop.
- **Flash:** the estimated net TX change is 0 to +0.5 KB, against 5.8 KB of headroom under the 90 %
  guard. Record the size in `firmware-budget.md`.

## 7. Node changes

- **Envelope** (`ws_frame.{c,h}`):
  - a length parameter, tag length 8, u16 station and u40 counter;
  - the nonce built from the integers;
  - the counter-range check (§3.2);
  - new constants and static asserts (header 8, tag 8, ACK 33, DIAG 48, OBS ≤ `WS_OBS_PLAIN_MAX` + 16);
  - `hex_print` asserted to fit the largest frame.
- **Encoder:** `ws_pack_observation` is replaced by the `ws_obs` encoder, which maps the energy state
  and applies the out-of-range rule. SHT45 temperature outside −40 to 125 °C becomes INVALID.
- **Store:**
  - the journal page magic changes to `WSJ2`. Draft-4 pages are already ignored at boot
    (`node_store.c:212`) and recycled through the normal erase-before-reuse, so there is no boot
    sweep;
  - slot size and CRC length come from §5.5;
  - `store_next_counter` refuses at 2^40.
- **PROVISION:** accepts station 1–65535 only (`stage0.c`, `fuzz_provision`, `load_config`).
  `store_config_load` rejects anything larger.
- **TX:**
  - KAT vectors, buffer sizes and `exchange_ms` (OBS maximum + ACK length);
  - DIAG gets its new fields: the ACK RSSI/SNR come from the radio's receive callback;
  - STATUS prints `ctr` as 64-bit.
- **RX:** the filter from §3.5.

## 8. Gateway changes

- **`ws0/protocol.py`:** the envelope, ACK, NACK, DIAG and the catalog-driven OBS decoder.
  `Nonces.next` refuses at 2^40.
- **`gateway.py`:** the catalog-driven `validate`, per-field availability in `latest()`, and the
  counter-monotonicity check (§5.3).
- **`ws0/service.py`:** station 1–65535; per-field Home Assistant discovery, from the newest record's
  keys and republished when the set grows; units and CSV.
- **Replay vs reuse:** keep a record of each node frame (counter → SHA-256 of the frame). A repeat
  with identical bytes is a replay: count it, no alarm. A repeat with different bytes is real nonce
  reuse: raise the key-reuse alarm. Draft 4 raised the alarm for a plain replay.
- **Simulator, harness, `__main__`, `openapi.json`** (add a record schema).
- **`tools/h01_report.py`:** score on T/RH field validity.

## 9. Release

1. WIPE the TX.
2. Flash RX and TX.
3. `init` a fresh run directory.
4. `provision-node` with the new key.
5. Start the gateway.

Record the release in `RELEASES.md` and the image size in `firmware-budget.md`. Replace
`protocol.md` with this draft. Update `protocol-stack.md` (frame layout, §13 tag size),
`firmware/stage0-node/README.md` and `firmware-budget.md`.

## 10. Tests

On the host, beyond the existing suites switched to draft 5:
- the encoding known-answer vector; range edges decoding to exact JSON values;
- counter limits: `store_next_counter` seeded near 2^40, the seal routine refusing 2^40, and
  `Nonces.next` refusing 2^40;
- draft-4 journal pages ignored and recycled; the power-cut sweep at the new slot size;
- energy-state mapping; SHT45 out of range → INVALID;
- PROVISION: 65535 accepted, 65536 rejected (C and Python);
- RX upstream and downstream filters (unit tests plus `fuzz_air`);
- the length checks before decryption (35 and `max + 1` dropped) vs after decryption (NACK);
- one NACK test per non-canonical rule in §5.4, including a counter decrease in sequence order and
  backfill out of arrival order *accepted*;
- per-field availability (a dead field doesn't hide the others);
- replay vs reuse classification;
- the harness nonce-uniqueness check on the new nonce layout;
- equal frame lengths for valid and faulted readings.

On the bench, before H01:
- a 51-byte observation and a 33-byte ACK round trip;
- the sensor-unplug test (`null` T/RH, `quality=sensor_fault`);
- DIAG fields: build ID and ACK RSSI/SNR.

**H01 runs on the draft-5 release.**

## 11. Implementation order

Each step is one commit with CI green. The C and Python sides of a wire change move together.

1. Catalog tables (C + Python) and the encoder/decoder with their cross-tests. No wire change yet.
2. Envelope in C and Python: length parameter, M = 8, u16/u40, counter range, reply API, KATs,
   `fuzz_reply`, console reply check.
3. Observation encode/decode, `gateway.validate`, `Store` (per-field quality, counter rule), NACK
   tests.
4. PROVISION 1–65535.
5. Store: `WSJ2`, slot sizes, counter limit, `test_store.c`.
6. TX/RX application: KAT, sizes, DIAG fields, RX filter in `ws_console`, `fuzz_air`.
7. Gateway service, MQTT discovery, simulator, harness, `h01_report`, openapi.
8. Build, flash-budget record, docs, release, bench checks, then H01.

## 12. Not in draft 5

- Implementing fields beyond T/RH. The catalog is fixed now, and each sensor's driver arrives with
  its hardware.
- Per-tip rain durability (H06), the qualifier logic (R10 detection), and calibration sets beyond
  revision 0.
- Delta or cross-record compression. Records must stand alone, because any one can be lost or
  arrive out of order.
