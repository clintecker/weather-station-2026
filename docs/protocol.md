# Stage-0 wire protocol, draft 5

This is the normative specification of the protocol on `master`, released to both boards as
`bc5e6ede429c` on 2026-10-14 (`firmware/stage0-node/RELEASES.md`). It is **not yet a frozen H01
contract**: when H01 passes, the PRD freezes the identity, time and quality contract. The design
reasoning is in [`protocol-draft5-design.md`](protocol-draft5-design.md). How
each layer works end to end (sensor → journal → crypto → LoRa → USB → SQLite → time) is in
[`protocol-stack.md`](protocol-stack.md).

Direct LoRa carries one frame per packet: an observation (OBS), a health report (DIAG), an ACK or a
NACK. There is no mesh and no module discovery. Every integer on the wire is **big-endian**.

Where the code and this text disagree, the code wins. The code is:

| Part | C (node, RX bridge) | Python (gateway) |
|---|---|---|
| Envelope, ACK/NACK | `firmware/common/ws_frame.{c,h}` | `ws0/protocol.py` |
| Observation and field catalog | `firmware/common/ws_obs.{c,h}` | `ws0/fields.py` |
| RX filters, console line parsing | `firmware/common/ws_console.{c,h}` | `ws0/link.py`, `ws0/__main__.py` |
| Node application | `firmware/stage0-node/App/app_tx.c`, `app_rx.c`, `node_store.c`, `node_fields.h` | — |
| Validation, storage | — | `gateway.py`, `ws0/service.py` |

## Changes from draft 4

| | Draft 4 | Draft 5 |
|---|---|---|
| Header | 16 bytes: `WS`, version, kind, station u32, counter u64 | **8 bytes**: version << 4 \| kind, station **u16**, counter **u40** |
| CCM tag | 16 bytes | **8 bytes** |
| Frame sizes | every kind 56 B | OBS 39–94 B (**42 B** for the T/RH build, **51 B** with the 15-s summary), ACK/NACK **33 B**, DIAG **48 B** |
| ACK/NACK plaintext | 24 B (UTC u64 or reason + reserved, echo u64) | **17 B** (UTC or reason u32, echo u40) |
| DIAG plaintext | 24 B | **32 B**: adds firmware build ID, ACK RSSI/SNR, crash count, energy state |
| Observation | fixed 24 B: T, RH, one validity byte, fillers `0x8000`/`0xFFFF` | 22-byte head + **field bitmap** + catalog fields; each field has its own **INVALID** code |
| Gateway record | `version: 4`, record-level validity | `version: 5`, per-field `null`, quality `valid`/`partial`/`sensor_fault` |
| Station ID | 1 to 2^32 − 1 | **1 to 65,535** |
| Counter | 64-bit | **1 to 2^40 − 1**, refused beyond |
| Replay | any frame at or below the counter mark raised the key-reuse alarm | a byte-identical copy is a **replay** (counted, no alarm); only different bytes raise the alarm |
| Journal page magic | `WSJ1` | `WSJ` + slot size (`WSJ0` for 48-byte slots) |

Draft-4 frames are rejected: their first byte `0x57` reads as version 5, kind 7, which is not a
kind. The nonce construction did not change, but the draft-5 release still uses a **new key** (see
"Counters and limits"). Earlier drafts: draft 4 (2026-10-12) added the uptime field; draft 3 the
impossible fillers; draft 2 the authenticated time in the ACK. Recorded `simulation-results/` and
evidence logs before 2026-10-14 are in older drafts.

## 1. Envelope

| Offset | Bytes | Field | Protection |
|---:|---:|---|---|
| 0 | 1 | High nibble: version **5**. Low nibble: kind (1 OBS, 2 ACK, 3 NACK, 4 DIAG) | Clear, authenticated |
| 1 | 2 | Station ID, u16, 1–65,535 | Clear, authenticated |
| 3 | 5 | Transmission counter, u40, 1 to 2^40 − 1 | Clear, authenticated |
| 8 | *n* | AES-128-CCM ciphertext of the kind's plaintext | Encrypted, authenticated |
| 8 + *n* | 8 | CCM tag, M = 8 (a constant; never inferred from the length) | — |

So byte 0 is `0x51` (OBS), `0x52` (ACK), `0x53` (NACK) or `0x54` (DIAG).

- **AAD:** the 8 header bytes. Changing the version, kind, station or counter breaks the tag.
- **Nonce (13 bytes):** kind (1 byte) + station as a big-endian **u32** + counter as a big-endian
  **u64**. It is built from the integers, never copied from the header bytes (`header()` in
  `ws_frame.c`, `_header_and_nonce()` in `protocol.py`). Same construction as draft 4.
- **Key:** 128 bits per station, shared by the node and the gateway. Key check value (KCV) = first
  3 bytes of AES-128(key, 16 zero bytes); safe to display.
- **Libraries:** Mbed TLS 3.6.6 CCM on the node; `cryptography` AESCCM (OpenSSL) on the gateway. The
  project has no AES code of its own.
- **Overhead:** 16 bytes per frame (8 header + 8 tag).

Example, the boot self-test vector (`KAT_OBS` in `App/app_tx.c`, key `000102…0f`): header
`51 0001 0100000002` = OBS, station 1, counter 0x100000002; nonce
`01 00000001 0000000100000002`.

### Frame lengths

| Kind | Plaintext | Frame | Checked |
|---|---:|---:|---|
| OBS | 23–78 B (22 + 1 to 56 field bytes) | 39–94 B | Range before decrypting; exact length from the field bitmap after |
| ACK, NACK | 17 B | 33 B | Exact, before decrypting |
| DIAG | 32 B | 48 B | Exact, before decrypting |

The gateway checks the length, version, kind and station **before** decrypting
(`plain_lengths()`, `unseal()`). A frame that fails any check, or the tag, is dropped silently. It
is never answered, so an outsider cannot make the gateway send a NACK. The Stage-0 build always
sends 42-byte observations.

## 2. Counters and limits

There are two counter spaces under one key. The kind byte in the nonce keeps every (kind, counter)
pair distinct, so no two frames share a nonce.

| Counter space | Used by | Kept in |
|---|---|---|
| Node | OBS and DIAG | TX flash monotonic log, reserved in blocks of 256 before use (`store_next_counter`, `App/node_store.c`) |
| Gateway | ACK and NACK | `gateway-nonces.sqlite3`, one `BEGIN IMMEDIATE` transaction per counter (`Nonces.next`) |

A 5-byte header field would truncate a larger counter silently, and a truncated counter repeats a
nonce. So the limits are enforced at every place that issues or seals a counter:

| Limit | Node (C) | Gateway (Python) |
|---|---|---|
| Counter 1 to 2^40 − 1 | `store_next_counter` refuses past `WS_COUNTER_MAX`; `ws_seal_kind` refuses 0 and > `WS_COUNTER_MAX`, wipes its output buffer and returns < 0; the boot self-test checks that 2^40 is refused | `Nonces.next` raises "Nonce space exhausted; rotate key"; `_header_and_nonce` raises; `to_bytes(5)` would also raise |
| Station 1 to 65,535 | `ws_parse_provision` (`firmware/stage0.c`), `store_config_write`, `store_config_load`, `ws_seal_kind`, `ws_open_reply` | `_header_and_nonce`; `station_id` in `gateway.json` (`ws0/service.py`, `STATION_MAX`) |
| Kind 1 to 4 | `ws_seal_kind` | `_header_and_nonce` |

2^40 frames last more than 100,000 years at 20 frames a minute.

Rules that keep nonces unique:
- The node reserves a counter block in flash **before** it uses a counter from it. A reset skips the
  rest of the block (for example counter 8 → 257).
- `WIPE ERASE-ALL-NODE-STATE` erases the key and the journal and **keeps** the counter and epoch
  (since release `0f456040fe54`, gap G17). The `PROVISION` epoch floor raises only the epoch.
- Never restore old node flash or an old gateway nonce database while keeping the key. If counter
  state is lost, use a new key ([`runbook-moving-boards.md`](runbook-moving-boards.md)).
- **A frame-format change needs a new key and fresh state:** WIPE the TX, `init` a new run
  directory, `provision-node`. The draft-5 release did this (run directory `run-d5`, KCV
  `5618eb`). CCM's keystream blocks encode only the nonce length, not the tag length, so a draft-4
  key could repeat keystream across versions.

## 3. ACK and NACK (kinds 2 and 3, gateway → node)

Both have the same 17-byte plaintext. They use the gateway's counter space.

| Offset | Bytes | ACK | NACK |
|---:|---:|---|---|
| 0 | 4 | Epoch of the observation | Epoch of the rejected observation |
| 4 | 4 | Sequence of the observation | Sequence of the rejected observation |
| 8 | 4 | Host UTC at commit, Unix seconds; **0** when the gateway measured its own clock as wrong (`ws0/clock.py`) | Reason: **1** identity collision, **2** invalid record |
| 12 | 5 | **Echo:** the counter of the observation frame being answered | Echo, as for the ACK |

C API: `ws_open_reply(key, station, frame, len, &kind, &counter, &epoch, &seq, &word, &echo)`, where
`word` is the UTC or the reason.

**Gateway.** It seals an ACK only **after** the SQLite commit, and also for an identity it already
holds (a retry after a lost ACK). It seals a NACK only for an **authentic** observation that it must
reject permanently, after it stores the raw frame in its `rejections` table.

**Node.**
- Any authentic ACK clears its own journal record (found by epoch and sequence).
- It sets its clock only from an ACK whose echo, epoch and sequence match the frame it just sent,
  in that frame's receive window, and only if the UTC is at or after 2026-01-01 (this also ignores
  the 0 above). A recorded ACK replayed later cannot match, so it cannot move the clock.
- It accepts a NACK only for the frame it just sent. It then marks the record done and adds 1 to
  the persisted `abandoned` total.
- After an authentic reply it latches the reply's RSSI and SNR for the DIAG report. A forged reply
  cannot set them.

## 4. Health report (DIAG, kind 4, node → gateway)

Fire-and-forget: no journal entry, no receive window, no reply. It uses the node's counter space.
The node sends one every 15 minutes and after each link-state change, after that minute's exchange,
also while probing. The gateway stores it in its `diagnostics` table, ordered by (epoch, uptime), not
by arrival.

| Offset | Bytes | Field | Gateway JSON name |
|---:|---:|---|---|
| 0 | 4 | Epoch | `epoch` |
| 4 | 4 | Uptime, seconds | `uptime_s` |
| 8 | 2 | Journal records pending | `journal_pending` |
| 10 | 4 | Journal records lost to overflow (cumulative, persisted) | `journal_lost_total` |
| 14 | 2 | Torn (burned) slots found at boot | `journal_torn_slots` |
| 16 | 2 | Abandoned records (cumulative, persisted) | `abandoned_total` |
| 18 | 2 | Missed ACKs since boot | `missed_acks_since_boot` |
| 20 | 2 | Rejected replies since boot | `rejected_replies_since_boot` |
| 22 | 1 | Reset cause: 0 unknown, 1 power, 2 pin, 3 brownout, 4 software, 5 watchdog, 6 lowpower, 7 option-bytes | `reset_cause` |
| 23 | 1 | Link state: 0 linked, 1 probing | `link` |
| 24 | 4 | Firmware build ID: the first 8 hex digits of `WS_FW_VERSION` (the release commit); 0 if not hex | `firmware_build` (8 hex digits) |
| 28 | 1 | RSSI of the last authentic ACK/NACK as the node heard it, signed dBm, clamped to −127…127; **−128 = none yet** | `ack_rssi_dbm` (`null` for −128) |
| 29 | 1 | SNR of that reply, signed dB; −128 = none yet | `ack_snr_db` (`null` for −128) |
| 30 | 1 | Crashes since power-up (`fault_count()`, RTC backup register DR11), saturating at 255 | `crashes_since_power_up` |
| 31 | 1 | Energy state (section 5.2) | `energy_state` |

The 2-byte counts saturate at `0xFFFF`. Python layout: `DIAG = struct.Struct('>IIHIHHHHBBIbbBB')`.

## 5. Observation (kind 1, node → gateway)

### 5.1 Layout

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 4 | Epoch: boot epoch, durable, increases at each TX boot |
| 4 | 4 | Sequence within the epoch, from 0 |
| 8 | 4 | Sample UTC, Unix seconds (u32, valid to 2106); **0** if the time is unknown |
| 12 | 4 | Uptime: seconds since the node booted; always present; time sync never changes it |
| 16 | 1 | Flags: bit 0 time known (must equal UTC ≠ 0); bits 1–2 energy state; bits 3–7 zero |
| 17 | 1 | Calibration revision, u8; 0 in Stage 0 |
| 18 | 4 | Field bitmap, u32: field *i* is present when `(bitmap >> i) & 1`. T/RH = `0x00000003` |
| 22 | *k* | The present fields in increasing *i*, each a big-endian unsigned integer of its catalog width |

The plaintext length is 22 + the widths of the present fields (`WS_OBS_PLAIN_LEN(bitmap)`,
`ws_obs_plain_len()`). The Stage-0 plaintext is 22 + 2 + 2 = **26 bytes**; the frame is 42 bytes.

**Presence rule.** Which fields are present depends only on the build (`WS_NODE_FIELDS` in
`App/node_fields.h`), never on a reading. A faulted field is sent with its INVALID code, never left
out, so the frame length does not reveal a sensor fault. A bitmap of 0 is rejected.

Example, the encoder's known answer (`tests/test_obs.py`, `run_kat` in `App/app_tx.c`): epoch 1,
sequence 2, UTC 1791991189, uptime 300 s, NORMAL, T −12.34 °C, RH 45.67 %:

```text
00000001 00000002 6acf9d95 0000012c 03    00  00000003 0ace  11d7
epoch=1  seq=2    utc      uptime   flags cal bitmap   T     RH
```

Flags `0x03` = time known + energy 1 (NORMAL). T code `0x0ace` = 2766 = −12.34 °C + 40.00 °C in
0.01 °C. RH code `0x11d7` = 4567.

### 5.2 Energy state (flag bits 1–2)

| Code | State | Gateway string |
|---:|---|---|
| 0 | SURPLUS | `surplus` |
| 1 | NORMAL | `normal` |
| 2 | CONSERVE | `conserve` |
| 3 | CRITICAL | `critical` |

This is the firmware's `energy_t` numbering. The Stage-0 build always sends 1 (NORMAL, USB power).

### 5.3 Field catalog v1

Value = (code − offset) / scale. INVALID is the field's all-ones code (`0xFF`, `0xFFFF` or
`0xFFFFFF`), except `qualifiers`, which has none.

| *i* | Field | Bytes | Unit, step | Offset (codes) | In-range codes | Value range | Special codes | Status |
|---:|---|---:|---|---:|---|---|---|---|
| 0 | `temperature_c` | 2 | 0.01 °C | 4000 | 0–16500 | −40.00 to 125.00 | `0xFFFF` INVALID | **Stage 0** (SHT45) |
| 1 | `humidity_pct` | 2 | 0.01 % | 0 | 0–10000 | 0 to 100.00 | `0xFFFF` INVALID | **Stage 0** (SHT45) |
| 2 | `pressure_hpa` | 2 | 0.1 hPa | −3000 | 0–8000 | 300.0 to 1100.0 | `0xFFFF` INVALID | defined, not built |
| 3 | `wind_speed_ms` | 2 | 0.1 m/s | 0 | 0–750 | 0 to 75.0, mean over the minute | `0xFFFF` INVALID | defined |
| 4 | `wind_gust_ms` | 2 | 0.1 m/s | 0 | 0–750 | 0 to 75.0, highest 3-s mean | `0xFFFF` INVALID | defined |
| 5 | `wind_dir_deg` | 2 | 1° | 0 | 0–359 | 0 to 359, wraps mod 360 | `0xFFFE` CALM; `0xFFFF` INVALID | defined |
| 6 | `rain_tips` | 3 | tips since boot | 0 | 0–16,777,214 | counter | `0xFFFFFF` INVALID | defined |
| 7 | `uv_index` | 1 | 0.1 UVI | 0 | 0–250 | 0 to 25.0 | `0xFF` INVALID | defined |
| 8 | `irradiance_wm2` | 2 | 1 W/m² | 0 | 0–2000 | 0 to 2000 | `0xFFFF` INVALID | defined |
| 9 | `uva_raw` | 3 | sensor counts | 0 | 0–1,048,575 (2^20 − 1) | raw; never reported as UV index | `0xFFFFFF` INVALID | defined |
| 10 | `qualifiers` | 4 | 2 bits per field 0–15: 0 ok, 1 suspected icing, 2 delayed melt, 3 outside the qualified envelope | — | any u32 | — | none (never INVALID) | defined |
| 11 | `batt_mv` | 2 | 1 mV | 0 | 0–65,534 | 0 to 65,534 | `0xFFFF` INVALID | defined |
| 12 | `batt_current_ma` | 2 | 0.1 mA, positive = into the cells | 32768 | 0–65,534 | −3276.8 to +3276.6 | `0xFFFF` INVALID | defined |
| 13 | `energy_in_mwh` | 3 | mWh since boot | 0 | 0–16,777,214 | counter | `0xFFFFFF` INVALID | defined |
| 14 | `energy_out_mwh` | 3 | mWh since boot | 0 | 0–16,777,214 | counter | `0xFFFFFF` INVALID | defined |
| 15 | `charge_in_mah` | 3 | mAh since boot | 0 | 0–16,777,214 | counter | `0xFFFFFF` INVALID | defined |
| 16 | `charge_out_mah` | 3 | mAh since boot | 0 | 0–16,777,214 | counter | `0xFFFFFF` INVALID | defined |
| 17 | `soc_gauge_pct` | 1 | 1 %, fuel-gauge estimate | 0 | 0–100 | 0 to 100 | `0xFF` INVALID | defined |
| 18 | `charger_pins` | 1 | bit 0 PGOOD, bit 1 CHG | 0 | 0–3 | raw pins | `0xFF` INVALID | defined |
| 19 | `enclosure_temp_c` | 2 | as field 0 | 4000 | 0–16500 | −40.00 to 125.00 | `0xFFFF` INVALID | defined |
| 20 | `enclosure_rh_pct` | 2 | as field 1 | 0 | 0–10000 | 0 to 100.00 | `0xFFFF` INVALID | defined |
| 21 | `temperature_min_c` | 2 | as field 0: lowest valid 15-s sample of the minute | 4000 | 0–16500 | −40.00 to 125.00 | `0xFFFF` INVALID | next release |
| 22 | `temperature_max_c` | 2 | as field 0: highest | 4000 | 0–16500 | −40.00 to 125.00 | `0xFFFF` INVALID | next release |
| 23 | `humidity_min_pct` | 2 | as field 1: lowest | 0 | 0–10000 | 0 to 100.00 | `0xFFFF` INVALID | next release |
| 24 | `humidity_max_pct` | 2 | as field 1: highest | 0 | 0–10000 | 0 to 100.00 | `0xFFFF` INVALID | next release |
| 25 | `th_samples` | 1 | valid T/RH samples behind fields 0, 1, 21–24 (metadata) | 0 | 0–60 | count | `0xFF` INVALID | next release |
| 26–31 | reserved | — | — | — | must be zero | — | — | — |

All 26 fields together are 56 bytes, so the largest plaintext is 78 bytes and the largest frame 94.
Fields 0 and 1 have a driver in release bc5e6ede429c; 21–25 are built and come with the next
release; the others are fixed in the catalog so that later builds need no wire change. Counter
fields (6, 13–16) start at 0 when their epoch starts.

**15-s sampling (PRD section 9), next release.** The node reads the SHT45 every 15 s
(`SAMPLE_PERIOD_MS`) and sends one observation per minute after the 4th sample. With fields 21–25
present, `temperature_c` and `humidity_pct` are the **mean** of the minute's valid samples (round
half up, in integers: `ws_th_mean_*`, `firmware/stage0.c`), 21–24 are their extrema and 25 is how
many samples were valid. A sample outside −40.00…125.00 °C is not counted; RH is clamped to
0–100 % before counting. With no valid sample, fields 0, 1 and 21–24 are INVALID and 25 is 0.
`th_samples` is metadata: it does not count towards the record's `quality`, so a dead sensor is
still `sensor_fault`.

### 5.4 Encoding rules

| Rule | Where |
|---|---|
| Code = round half up of (value × scale) + offset, that is `floor(x × scale + 0.5) + offset`, computed exactly (Python `Decimal`; C works from integer 0.01 units) | `Field.code()`; `ws_code_temp_centi`, `ws_code_rh_centi` |
| Out of range → **INVALID**, never clamped | `Field.code()`; `ws_code_temp_centi` (T outside −40.00…125.00 °C) |
| Exception: relative humidity (fields 1 and 20) is **clamped** to 0–100 % | `Field.code()`; `ws_code_rh_centi` |
| `wind_dir_deg` wraps modulo 360 before the range check | `Field.code()` |
| No sample or a sensor fault → INVALID. The Stage-0 node sends **both** T and RH INVALID after any SHT45 fault | `sample()` in `App/app_tx.c` |
| A wind direction needs a valid speed: if `wind_speed_ms` is INVALID, `wind_dir_deg` must be INVALID (CALM is not allowed either) | `ws_obs_encode`, `_check_wind` |
| Decoding is exact: (code − offset) is an integer before the single division, so no float noise reaches the stored JSON | `Field.value()` |

The C encoder `ws_obs_encode` refuses (returns −1) any record the decoder would reject. The C and
Python encoders produce identical bytes (`tests/test_obs.py`).

### 5.5 One valid encoding per reading (canonical rules)

The gateway accepts exactly one byte form for each reading. An **authentic** observation that
breaks a rule below is stored in `rejections` and answered with a **NACK**:

| Rule | NACK reason | Code |
|---|---:|---|
| Plaintext length ≠ 22 + the present fields' widths | 2 | `fields.decode` |
| A flag bit 3–7 set, a reserved bitmap bit (26–31) set, or a bitmap of 0 | 2 | `fields.decode` |
| Time-known flag ≠ (UTC ≠ 0) | 2 | `fields.decode` |
| A code above its field's maximum that is not that field's INVALID or CALM | 2 | `Field.code_ok` |
| `wind_dir_deg` not INVALID while `wind_speed_ms` is INVALID | 2 | `_check_wind` |
| A since-boot counter that decreases **in sequence order** within its epoch (section 6) | 2 | `Store.check_counters` |
| Anything else `gateway.validate` refuses (for example a value that is not an exact catalog value, or a quality that does not match the fields) | 2 | `gateway.validate` |
| Same identity (station, epoch, sequence) as a stored record, different content | **1** | `Store.ingest` |

A frame with a length outside 39–94 bytes, a wrong version, kind or station, or a bad tag never
reaches these checks: it is dropped with no reply (section 1). The gateway and node ship one
catalog together, so an unknown bit is a bug, not a newer node.

A sample time more than 5 s after its receipt time is **not** rejected: it is stored and
**quarantined** (`future_clock_at_receipt`); waiting does not make it valid.

## 6. Gateway record

`decode_observation()` turns a plaintext into this JSON record, and `gateway.validate()` checks it
(closed schema: no other keys).

| Key | Value |
|---|---|
| `version` | `5` |
| `station` | Configured station name (string) |
| `session` | The epoch, as a decimal string |
| `sequence` | Sequence number |
| `sampled_at` | UTC seconds, or `null` when the time is unknown |
| `uptime_s` | Uptime |
| `time_quality` | `synchronized` or `unknown` |
| `energy_state` | `surplus`, `normal`, `conserve` or `critical` |
| `calibration_revision` | 0–255 |
| `quality` | `valid`, `partial` or `sensor_fault` (below) |
| *each present field* | Its value in catalog units, or **`null`** for INVALID |
| `wind_calm` | Present exactly when `wind_dir_deg` is: `true` for CALM (then `wind_dir_deg` is `null`), else `false` |
| `qualifiers` | Object with only the non-ok fields, for example `{"temperature_c": "suspected_icing"}` |

**Quality** is computed over the present measurement fields (all but `qualifiers`):
- `valid`: every present field has a value (CALM counts as a value);
- `partial`: some present fields are `null`;
- `sensor_fault`: every present field is `null`.

For the Stage-0 build, a sensor fault gives `temperature_c: null, humidity_pct: null,
quality: "sensor_fault"`.

**Per-field availability.** `/v1/observations/latest` reports `fields_available` per field and the
units per field; Home Assistant gets one entity per field, each unavailable when its own value is
`null`. A dead sensor never hides the others. **H01 scores the validity of the T/RH fields**
(`tools/h01_report.py`).

**Identity.** Observation identity = station + epoch + sequence. A record whose identity is already
stored with the same content is a duplicate: no new row, ACK again. Different content under the same
identity is a collision: NACK reason 1, never an ACK. Identity order (epoch, then sequence), not
wall-clock time, decides which record is newest.

**Since-boot counters** (`rain_tips`, `energy_*`, `charge_*`) must not decrease **in sequence
order** within one epoch. The gateway compares a new record with its stored neighbours by sequence
(the nearest lower and nearest higher sequence that has a value), never by arrival order, so an
older record that arrives late (backfill) is accepted. `null` values are skipped.

**Reconstructed time.** An unsynchronized record gets an effective time from the nearest
synchronized record of the same epoch: `ref_utc + (uptime − ref_uptime)`, uncertainty 2 s + 150 ppm
× |uptime − ref_uptime| (`Store.reconstruct`, `protocol-stack.md` §11.3.2).

## 7. Replay and key reuse

The gateway keeps a high-water mark of the node counter, plus the SHA-256 of every authentic node
frame it accepted as fresh, by counter (`node_counter` and `node_frames` tables in the nonce
database, `Nonces.advance_node_counter`). For every **authentic** OBS or DIAG frame:

| Case | Verdict | What the gateway does |
|---|---|---|
| Counter above the mark | fresh | Raises the mark, keeps the digest, then processes the frame |
| Counter at or below the mark, same bytes as the frame accepted under that counter | **replay** | No reply, nothing stored as data; raw frame kept in `rejections` with reason `replay`; `replays` counted; **no alarm** |
| Counter at or below the mark, different bytes, or a counter never accepted | **counter regression** | No reply, nothing stored as data; raw frame kept in `rejections` with reason `counter_regression`; `/v1/status` raises the persistent alarm "possible key reuse: re-key the node" |

The mark is committed before the frame is acted on. A direct LoRa link cannot reorder frames, so an
older, never-seen counter means a repeated nonce or a reused key, not a late frame. The alarm clears
only with a new key in a new state directory (runbook R5).

## 8. RX bridge and USB line contract

The RX board holds no key. It never acknowledges anything itself; the gateway is the only ACK
authority. Serial: 115200 baud, 8N1, one line per message, `\n`-terminated (`\r` ignored).

| Direction | Line | Rule |
|---|---|---|
| RX → host | Lowercase hex of one received frame | Only if `ws_air_frame_ok()`: version 5 and either kind 1 with length 39–94 B (78–188 hex digits) or kind 4 with length 48 B (96 digits). The Stage-0 observation is 84 digits. Anything else gives `#rx drop len= rssi= snr=` |
| RX → host | `#…` | Diagnostics (`#rx obs rssi= snr=` after each forwarded frame, `#rx crc len= rssi= snr= data=` and `#rx hdr rssi=` for bad receptions, `#alive` every 60 s, `#boot`, `#status`, `#watchdog …`, `#tx busy`, `#host reject len=`, …) |
| host → RX | 66 hex digits | One ACK or NACK, transmitted once with the uplink radio settings. Only if `ws_host_reply_ok()`: exactly 33 bytes, version 5, kind 2 or 3. Anything else gives `#host reject len=` |
| host → RX | `STATUS`, `TEST-HANG`, `TEST-FAULT` | Commands; lines that start with `#` are ignored |

- A line is at most 256 bytes on both sides (`WS_LINE_MAX`; `ws0/link.py`). A longer line is
  discarded whole.
- The bridge prints the largest catalog frame whole (85 bytes; `hex_print` in `App/console.c`, with a
  static assert against the 256-byte trace buffer) and reports anything longer as `#error`, never a
  truncated line.
- The gateway writes every `#` line to `receiver.log` and never decodes it as a frame. It reads
  `#alive` and `#boot role=rx` only for receiver liveness (silent after 180 s). It logs each frame and
  its reply (`frame <hex> -> ack <hex>`, `-> nack <hex>`, `diag <hex>`).
- While the RX console holds a complete line, it drops further input; the host sends one line per
  exchange.

## 9. Radio exchange (`firmware/stage0-node`)

Unchanged from draft 4 except the frame sizes.

RF: 915.0 MHz LoRa, 500 kHz bandwidth, SF7, CR 4/5, 8-symbol preamble, explicit header, CRC on,
0 dBm (bench), symbol timeout off (`App/radio_cfg.h`). See
[`hardware/nucleo-wl55jc-bringup.md`](hardware/nucleo-wl55jc-bringup.md) for the regulatory basis.
At SF7 a 42-byte observation takes 21.8 ms on air, a 33-byte ACK 18.0 ms and a 48-byte DIAG 24.4 ms
(`protocol-stack.md` §8.2).

- Each minute the node journals one observation. While the link is LINKED it sends it, then up to
  *N* older pending ones, oldest first. *N* comes from the transmission policy
  ([`radio-energy-policy.md`](radio-energy-policy.md)): 20/5/0/0 for SURPLUS/NORMAL/CONSERVE/CRITICAL
  (Stage 0 is fixed at NORMAL, so 5). It is further capped by a per-minute airtime budget
  (15/5/2/0 s), counting one exchange as observation airtime + ACK airtime + 300 ms, which is
  22 + 18 + 300 = **340 ms** at SF7 (`exchange_ms`, `airtime_ms()` in `App/app_tx.c`).
- CONSERVE sends only the live reading, at most every 300 s. CRITICAL journals and does not send.
- After each frame the node listens up to 2000 ms for the reply, then waits 50 ms before the next
  frame. The first missed reply ends that minute's drain.
- After 3 consecutive minutes with no answer the node goes PROBING: it sends only the live reading,
  with no backlog: every minute in SURPLUS and NORMAL (so always in Stage 0), and after 120, 240,
  480, then every 900 s in CONSERVE. Any answer returns it to LINKED.
- A missing ACK leaves the record journaled. Each retry has the same identity and a fresh counter.
- Strike limit: a record that stays unanswered in 10 exchanges in which the gateway answered other
  frames is abandoned and counted (`STRIKE_LIMIT` 10, 6 tracking slots). Exchanges with no answer at
  all never count, so an outage never abandons data.
- The node trusts its clock for 6 hours after the last time sync, then sends UTC 0 (time unknown)
  until the next accepted ACK.
- The Python simulator (`ws0/simulator.py`) drains 5 records per minute, like NORMAL.

References:
- RFC 3610, *Counter with CBC-MAC (CCM)*: <https://www.rfc-editor.org/rfc/rfc3610>
- NIST SP 800-38C: <https://csrc.nist.gov/pubs/sp/800/38/c/upd1/final>
- `cryptography` AESCCM: <https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESCCM>
- Sensirion SHT4x datasheet: <https://sensirion.com/resource/datasheet/sht4x>
