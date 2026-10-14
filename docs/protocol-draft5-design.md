# Protocol draft 5: design

**Status:** design for review (2026-10-14). Not implemented. Clint approved the direction on
2026-10-14: introduce draft 5 **before H01**, shorten the authentication tag to **8 bytes**, and
use a **compact 8-byte header**. When this design is approved, it replaces draft 4
(`protocol.md`) and H01 runs on it. The PRD freezes the payload identity, time and quality
contract when H01 passes (PRD §12, H01 "On pass").

## 1. Goals

1. **Room for the full station.** The PRD's Core sensor set (R01: temperature, RH, station pressure,
   liquid precipitation, wind speed and direction, UV index; optional solar irradiance) must fit in
   one frame per minute, with room left over.
2. **No wasted bits.** Each measurement takes only the bits its range and resolution need.
3. **Less fixed overhead.** Today 32 of the 56 bytes are header and tag. Every frame, ACKs
   included, pays them.
4. **Keep what H01 will freeze:** observation identity (station, epoch, sequence), time (UTC or
   unknown, plus uptime) and quality. Keep every security property of draft 4.
5. **Only build what the active stage needs** (PRD §1 scope rule). Draft 5 implements temperature
   and RH only. The other fields are specified here and implemented in the stage that adds each
   sensor.

## 2. Size and airtime

LoRa at 500 kHz, CR 4/5, 8-symbol preamble, explicit header, CRC on (`protocol-stack.md` §8.2).

| Frame | Draft 4 | Draft 5 | Airtime SF7 | Airtime SF12 |
|---|---:|---:|---|---|
| Observation, T/RH (Stage 0) | 56 B | **40 B** | 26.9 → 20.5 ms | 575.5 → 452.6 ms |
| Observation, full Core set | (draft 4 cannot carry it) | **51 B** | 25.7 ms | 534.5 ms |
| ACK / NACK | 56 B | **33 B** | 26.9 → 18.0 ms | 575.5 → 411.6 ms |
| DIAG | 56 B | **40 B** | 26.9 → 20.5 ms | 575.5 → 452.6 ms |

Where the savings come from: the header goes from 16 to 8 bytes and the tag from 16 to 8 bytes,
saving 16 bytes per frame. Bit-packing the full Core field set takes 15 bytes instead of 18
byte-aligned (§5.2). The fixed overhead was the larger cost.

## 3. Frame envelope

| Offset | Bytes | Field | Protection |
|---:|---:|---|---|
| 0 | 1 | High 4 bits: version = **5**. Low 4 bits: kind (1 OBS, 2 ACK, 3 NACK, 4 DIAG; 5 PACK reserved for Stage 1) | Authenticated, clear |
| 1 | 2 | Station ID, u16, 1–65535 | Authenticated, clear |
| 3 | 5 | Transmission counter, u40 | Authenticated, clear |
| 8 | *n* | AES-128-CCM ciphertext of the kind's plaintext | Encrypted and authenticated |
| 8+*n* | 8 | CCM authentication tag (M = 8) | — |

- **AAD** = the 8 header bytes.
- **Nonce** (13 bytes) = kind (1) + station ID zero-extended to 4 bytes + counter zero-extended to
  8 bytes. This is **byte-for-byte the draft-4 nonce construction**, so the draft-4 uniqueness
  argument still holds. Counters keep counting up across the upgrade (the node's flash counter
  and the gateway's nonce database are unchanged). So the existing key stays valid: no draft-5
  frame can reuse a nonce that a draft-4 frame already used.
- **Counter limit.** Each side refuses to seal when the counter would reach 2^40 (fail closed: no
  sending). 2^40 frames is more than 100,000 years at the 20-frames-per-minute SURPLUS maximum.
- **Frame length** = 16 + plaintext length. The LoRa explicit header carries it. Every kind has a
  fixed plaintext length, except OBS, whose length the field bitmap (§5) determines. A receiver
  rejects any other length before decrypting.
- **Dropped:** the `WS` magic (2 bytes). The private sync word and the PHY CRC already filter
  foreign packets, and the tag rejects anything else. A foreign frame costs one failed tag check.
- **Tag length.** The chance that a forged or altered frame passes is 2^-64 per attempt.
  LoRaWAN uses 4 bytes. One key never mixes tag lengths under the same nonce, because nonces
  never repeat (§3, nonce). Mbed TLS (`mbedtls_ccm_encrypt_and_tag`, `tag_len` 8) and
  `cryptography` (`AESCCM(key, tag_length=8)`) both support M = 8.

## 4. Fixed plaintexts

**ACK (kind 2), 17 bytes:** epoch u32 · sequence u32 · host UTC u32 (Unix seconds at commit;
**0** when the gateway measured its own clock as wrong) · echoed observation counter u40.
Draft 4 used a u64 UTC. A u32 is valid to 2106, the same as the observation's UTC field.

**NACK (kind 3), 17 bytes:** epoch u32 · sequence u32 · reason u32 · echoed counter u40. The
layout matches the ACK, so the node opens both with one code path, as in draft 4. Reasons:

| Reason | Meaning | Node action |
|---:|---|---|
| 1 | Identity collision | Stop retrying; count as `abandoned` (as draft 4) |
| 2 | Invalid record | Stop retrying; count as `abandoned` (as draft 4) |
| 3 | **Deferred**: authentic, but the gateway can't decode it yet (§5.3) | **Keep the record**, count no strike, and end this minute's drain. Draft 5 adds this reason |

**DIAG (kind 4), 24 bytes:** unchanged from draft 4 (`protocol.md`). Stage 1 extends the
health report or adds kind 5 (PACK) for the per-pack schema of PRD §5. That decision belongs to
Stage 1 (`radio-energy-policy.md` §7).

**PACK (kind 5):** reserved. Stage 1 defines it, using the field-table method of §5, for the PRD
§5 per-pack schema. It is sent every 5 minutes and on a state change. Nothing is implemented in
draft 5.

## 5. Observation plaintext (kind 1)

### 5.1 Layout

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 4 | Epoch u32 (boot epoch, durable) |
| 4 | 4 | Sequence u32 within the epoch |
| 8 | 4 | Sample UTC u32 Unix seconds; **0** if time unknown |
| 12 | 4 | Uptime u32, seconds since boot, always present |
| 16 | 1 | Flags: bit 0 time known · bits 1–2 energy state at sampling (0 NORMAL, 1 SURPLUS, 2 CONSERVE, 3 CRITICAL) · bits 3–7 zero |
| 17 | 1 | Calibration revision u8 (0 in Stage 0) |
| 18 | 2 | Field bitmap u16: bit *i* set = catalog field *i* is present. Bit 15 = another u16 bitmap follows (catalog fields 15–29); zero in draft 5 |
| 20 | *k* | Present fields, bit-packed in increasing field order, most significant bit first, zero-padded to a byte boundary |

Bytes 0–15 are the identity and time contract. They have the same meaning and width as in draft 4.
The 1-byte flags field replaces draft 4's two bytes for validity and time quality. Validity moves
into each field (§5.2).

The energy state tells the gateway the reporting interval the node was in when it sampled:
60 s, or 300 s in CONSERVE (PRD R02). The gateway therefore doesn't treat a CONSERVE gap as a
link failure. Stage 0 always sends NORMAL.

### 5.2 Field catalog v1

**Every field reserves its all-ones code as INVALID** (sensor fault, sample missing, or out of
range). This replaces draft 4's validity byte and filler values. Each field pays for it with
one code, never a bit. Field-specific special codes sit just below all-ones.

| Bit | Field | Encoding | Range | Bits | Special codes | Stage |
|---:|---|---|---|---:|---|---|
| 0 | `temperature_c` | (T + 40.00) × 100 | −40.00 to 125.00 °C (SHT45 range) | 15 | 32767 invalid | **0 (draft 5)** |
| 1 | `humidity_pct` | RH × 100 | 0.00 to 100.00 % | 14 | 16383 invalid | **0 (draft 5)** |
| 2 | `pressure_hpa` | (P − 300.0) × 10 | 300.0 to 1100.0 hPa, station pressure | 13 | 8191 invalid | 3 |
| 3 | `wind_speed_ms` | v × 10, scalar mean over the interval | 0.0 to 75.0 m/s | 10 | 1023 invalid | 3 |
| 4 | `wind_gust_ms` | v × 10, maximum rolling 3-s average in the interval | 0.0 to 75.0 m/s | 10 | 1023 invalid | 3 |
| 5 | `wind_dir_deg` | vector-mean direction, degrees | 0 to 359 | 9 | 510 calm (too little wind for a direction), 511 invalid | 3 |
| 6 | `rain_tips` | lifetime tip count | 0 to 16,777,214 | 24 | 16777215 invalid | 3 |
| 7 | `uv_index` | UVI × 10 | 0.0 to 25.0 | 8 | 255 invalid | 3 |
| 8 | `irradiance_wm2` | W/m² | 0 to 2000 | 11 | 2047 invalid | 3 (optional module) |
| 9–14 | reserved | — | — | — | must be zero | — |

**Sizes:** T/RH = 29 bits → 4 bytes, so the plaintext is 24 bytes and the frame 40 bytes. The full
catalog v1 is 114 bits → 15 bytes, so the plaintext is 35 bytes and the frame 51 bytes.

**Why the rain counter is 24 bits and never wraps:** a lifetime count lets the gateway compute
rain for any period, and a lost frame loses nothing (PRD §9: no duplicated or lost tips). With 24
bits and 0.2 mm tips, the counter wraps after 3,355 m of rain, which is never. So the gateway can
treat **any decrease as a counter reset** (for example after a flash wipe), flag it, and never
mistake a reset for a wrap. A 16-bit counter would force that ambiguous guess.

**Reserved bits 9–14** are for measurements whose meaning isn't tested yet: T/RH minimum, maximum
and sample coverage (PRD §9: 15-s sampling, "store coverage, mean and extrema"), suspected
icing, delayed melt, and outside-envelope flags (PRD R10). Each gets its encoding when its stage
tests it. Draft 5 leaves them unassigned rather than guessing.

### 5.3 One valid encoding per reading

The gateway rejects (with a NACK, reason 2) an authenticated observation that:

- has a length other than 20 + ⌈(sum of the present fields' bits) / 8⌉;
- has a non-zero padding bit, reserved flag bit, or reserved bitmap bit (9–15);
- has a code outside its field's range that is not one of that field's special codes;
- has time known ≠ (UTC ≠ 0);
- is otherwise not canonical as draft 4 defines it (identity, time quarantine).

**Unknown field bit (gateway older than the node).** A bit the gateway's catalog doesn't define
means the node runs a newer catalog. The gateway can't find the field lengths. It then stores
the raw frame in `rejections` with reason `unknown_field`, answers with **NACK reason 3
(deferred)**, and raises a status alarm: "update the gateway". The node keeps the record journaled
and retries later, so the data waits instead of being abandoned.

Silence would not be enough. While older records (without the new field) are still in the
backlog, the gateway would answer them and ignore the newer ones. The node's strike safety net
(abandon a record after 10 exchanges in which other frames were answered) would then drop the
newer records. The deferred reply tells the node to wait without counting a strike.
**Update the gateway before the node.**

### 5.4 Gateway record (JSON and storage)

The stored record keeps draft 4's keys (`version`, `station`, `session`, `sequence`,
`sampled_at`, `uptime_s`, `time_quality`, `temperature_c`, `humidity_pct`, `quality`) and adds
`energy_state`, `calibration_revision` and each catalog field that is present. An INVALID code
becomes `null`. `wind_dir_deg` CALM becomes `null` with `wind_calm: true`. `quality` is `valid`
when every present field is valid, otherwise `sensor_fault`. A T/RH-only station therefore
behaves exactly as today. Absent fields are omitted, not null, so "not installed" stays
distinct from "faulty".

**Identity collision compares measurements, not encodings.** Draft 4 compared the stored JSON
text, so the same reading re-sent as draft 5 (for example a record journaled before the upgrade)
would differ only in `version`, read as a collision, and be NACKed. Draft 5 compares the
identity, time and measurement fields and ignores `version`.

## 6. Code: one schema, generated twice

- The single source is `protocol/fields-v1.json`: index, name, unit, scale, offset, bits, and
  special codes.
- `tools/gen_fields.py` generates `firmware/common/ws_fields.h` (a C table) and
  `ws0/fields.py`. A test fails if the generated files don't match the committed ones.
- `firmware/common/ws_bits.{c,h}`: a pure MSB-first bit writer and reader, host-tested and
  fuzzed. The node only encodes; the C reader exists for the cross-check tests.
- Cross-check (`tests/test_frame.py`): the C encoder and the Python decoder must agree on random
  readings for every field, including INVALID and special codes and every bitmap subset. Python
  must reject every non-canonical mutation of §5.3.
- The firmware's boot known-answer test (`kat=pass`) gets a new draft-5 vector, tag length 8.
- The fuzz targets switch to the draft-5 envelope (`fuzz_reply` with ACK/NACK at 33 bytes), and a
  new `fuzz_obs` target fuzzes the Python decoder.

## 7. Node changes

- **Envelope:** `ws_frame.{c,h}` take a plaintext length and use tag length 8, the u40 counter
  and the u16 station ID. `ws_frame.h` static asserts are updated (ACK frame 33 B, OBS ≤ 56 B in
  Stage 0).
- **Journal:** the slot stays 40 bytes. A Stage-0 build's maximum OBS plaintext (T/RH) is 24
  bytes, the same as today, so the outage buffer stays 4,743 records (3.3 days). A build's
  configured field set fixes its maximum plaintext, and a static assert ties the slot size to it.
  The SPI-NOR journal of H11 brings bigger slots for the full sensor set.
- **Upgrade without losing data:** new journal pages get the magic `WSJ2`. Pending records on
  older `WSJ1` pages hold draft-4 plaintexts. The node converts each one to a draft-5 plaintext
  **when it reads it to send** (same epoch, sequence, time and T/RH; time-known from draft-4 time
  quality; invalid from draft-4 validity). It never rewrites them in flash. `WSJ1` pages are
  reused as `WSJ2` in the normal ring order once their records are done.
- **Station ID** must be 1–65535. `PROVISION` refuses anything larger.
- **The RX bridge** checks a frame's length (17 to 56 bytes in draft 5), version 5 and kind
  (1 or 4 upstream, 2 or 3 downstream). It still holds no key.

## 8. Gateway changes

- `ws0/protocol.py`: draft-5 envelope, ACK and NACK; the OBS decoder is driven by the generated
  catalog.
- `load_config`: station ID 1–65535.
- `/v1/status`: the `unknown_field` alarm. `openapi.json`: the new record keys.
- MQTT discovery publishes an entity only for fields the station has actually sent, so there are
  no phantom Home Assistant sensors.
- The simulator and harness switch to draft 5. Their recorded `simulation-results/` are already
  stale (draft 1) and stay labeled as such.

## 9. Release and upgrade order

1. Stop the gateway. The TX keeps journaling.
2. Flash RX, then TX (both draft 5). The TX converts its pending `WSJ1` records when it sends
   them.
3. Start the draft-5 gateway.

The draft-5 gateway does not accept draft-4 frames. Any frames the TX sent before the switch
stay journaled, because they got no ACK, and go out again as draft 5. Record the release in
`RELEASES.md`. The key and the counters carry over (§3). **No re-provisioning.**

## 10. Tests and gate

- Host: everything in §6, plus the existing suites switched to draft 5 (frame, gateway, harness,
  counter regression, power-cut store, fuzz).
- Bench, before H01:
  - flash with pending `WSJ1` records and check that they arrive converted, without collision;
  - check that the 40-byte observation and 33-byte ACK round trip;
  - check the sensor unplug test (`null` T/RH, `quality=sensor_fault`);
  - check a counter-limit guard test on the host.
- **H01 runs on the draft-5 release.** A draft-4 smoke test is not H01 evidence.

## 11. Not in draft 5 (deliberately)

- Pack telemetry (kind 5), DIAG extensions, the T/RH extrema and coverage fields, and the
  icing, melt and envelope flags. Each is specified in its own stage, as §4 and §5.2 describe.
- Delta encoding or compression across records. Records must stay independent, because any one
  frame can be lost or arrive out of order (backfill).
- A sub-byte header or a shorter identity block. Bytes 0–15 are the frozen contract. Saving one
  or two bytes there isn't worth the risk.
