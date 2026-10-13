# Stage-0 transport draft 4

This is a tested host protocol and portable C payload draft, **not a frozen H01 contract**.
For how each layer works end to end (sensor bus → journal → crypto → LoRa → USB → SQLite → time sync),
with diagrams and sources, read [`protocol-stack.md`](protocol-stack.md).
Direct LoRa carries one observation or one acknowledgment. No mesh or module discovery.
Every integer is big-endian. Observation frame: 56 bytes. ACK frame: 56 bytes.

Draft 4 (2026-10-12) changes from draft 3: version byte 4; the 8-byte UTC field becomes a
4-byte UTC field (u32 seconds, valid to 2106) plus a 4-byte **uptime** (seconds since the
node booted, always present). The gateway reconstructs the UTC time of an unsynchronized
sample from the nearest synchronized sample of the same epoch (see protocol-stack.md 11.3).

Draft 3 (2026-10-12) changes from draft 2: version byte 3; an invalid reading carries the
impossible fillers temperature `0x8000` (-327.68 °C) and humidity `0xFFFF` (655.35 %), not 0.
A reader that ignores the validity flag can therefore never see a plausible value such as
0.00 °C. The validity flag stays authoritative.

Draft 2 (2026-10-12) changes from draft 1: version byte 2; the ACK carries host UTC and
echoes the acknowledged frame's transmission counter (authenticated time sync). Draft-1
frames are rejected. Recorded `simulation-results/` predate this change.

## Authenticated envelope

| Offset | Bytes | Field |
|---|---:|---|
| 0 | 2 | ASCII `WS` |
| 2 | 1 | Version, 4 |
| 3 | 1 | Kind: 1 observation, 2 gateway ACK |
| 4 | 4 | Numeric station ID |
| 8 | 4 | Transmission counter high word |
| 12 | 4 | Transmission counter low word |
| 16 | 24 | AES-128-CCM ciphertext (observation or ACK) |
| end | 16 | Authentication tag |

AES-CCM nonce = kind (1 byte) + station ID (4) + high counter (4) + low counter (4).
The full 16-byte header is authenticated additional data. A per-station 128-bit key
is shared by the node and gateway; kinds separate the two nonce domains.

Python uses `cryptography` 50.0.1 / OpenSSL AESCCM. A durable SQLite transaction
reserves every counter **before** encryption. Failure stops sending. The allocator
binds its database to key fingerprint, station and direction. Retries allocate fresh
counters; observation identity is independent and unchanged. Cloning/rolling back
state with the same key is prohibited. Firmware must implement a power-fail-safe
reserved epoch/counter allocation scheme before using this key structure.

## Observation plaintext (24 bytes)

| Offset | Bytes | Field |
|---|---:|---|
| 0 | 4 | Durable sample/boot epoch |
| 4 | 4 | Sample sequence within epoch |
| 8 | 4 | Sample UTC Unix seconds (u32), 0 if time unknown |
| 12 | 4 | Uptime: seconds since node boot (u32), always present; monotonic, unaffected by time sync |
| 16 | 2 | Signed temperature in 0.01°C; `0x8000` (-32768) if sensor invalid |
| 18 | 2 | Unsigned RH in 0.01%; `0xFFFF` if sensor invalid |
| 20 | 1 | Validity: 1 both measurements valid, 0 sensor fault |
| 21 | 1 | Time quality: 1 synchronized, 0 unknown |
| 22 | 2 | Calibration revision; currently 0 only |

SHT45 failure invalidates the complete paired reading. JSON represents invalid
measurements as null and preserves separate time quality. Later individual sensor
fields need their own validity, not expansion in Stage 0.

Observation identity = configured station name + sample epoch + sample sequence.
Epoch must increase durably across node restarts. Sample identity, not wall-clock
sorting, determines newest data; a corrected clock can therefore recover availability.
A sample more than five seconds ahead of its receipt time is quarantined. This
threshold is a conservative draft clock-tolerance setting, not an H01 waiver.

NACK (kind 3, 24-byte plaintext) = sample epoch (4) + sequence (4) + reason (4: 1 identity
collision, 2 invalid record) + reserved 0 (4) + echoed observation counter (8). The gateway sends a
NACK only for an **authenticated** frame that it must reject permanently, after it stores the raw
frame in its `rejections` table. It shares the gateway's ACK counter space; the kind byte keeps the
nonces distinct. The node accepts a NACK only for the frame it just sent, then stops retrying that
record. An unauthenticated or wrong-version frame never gets a NACK.

DIAG (kind 4, 24-byte plaintext, node → gateway, fire-and-forget) = epoch (4) + uptime s (4) +
journal pending (2) + journal lost total (4) + torn slots (2) + abandoned total (2) + missed ACKs
since boot (2) + rejected replies since boot (2) + reset cause (1) + link state (1). It uses the
node's observation counter space. The gateway stores it and never answers it.

ACK plaintext (24 bytes) = acknowledged sample epoch (4) + sample sequence (4) + host UTC
Unix seconds at commit (8) + the 64-bit transmission counter of the observation frame being
answered (8). The node sets its clock only from an ACK whose echoed counter equals the
frame it just sent, in that frame's receive window; a recorded ACK replayed later cannot
match and cannot move the clock. Any authentic ACK still clears its own journal entry.
ACK is only
created after SQLite commit; the node verifies it before removing the journal entry.
Exact duplicate observations are acknowledged again. Conflicting payloads under the
same observation identity are rejected and never acknowledged. Replayed valid data
cannot alter stored time or freshness. Replayed ACKs affect only their exact identity.

Receiver/host USB contract: one ASCII hexadecimal frame per newline, 115200 baud,
8N1. Receiver forwards opaque RF frames upstream and host ACK frames downstream;
it must never acknowledge independently. Maximum input line is 256 bytes. Lines
starting with `#` are receiver diagnostics (RSSI/SNR, drops); the host logs them to
`receiver.log` and never parses them as frames.

## Radio exchange (firmware/stage0-node)

RF: 915.0 MHz LoRa, 500 kHz bandwidth, SF7, CR 4/5, 8-symbol preamble, explicit header,
CRC on, 0 dBm (bench). See docs/hardware/nucleo-wl55jc-bringup.md for the regulatory basis.
Each minute the node journals one observation, then sends it, then at most two older
pending ones. After each frame it listens up to 2000 ms for the ACK (no LoRa symbol
timeout), then waits 50 ms before the next frame. A missing ACK leaves the record
journaled; each retry gets a fresh counter. The node trusts its clock for 6 hours after
the last time sync, then marks samples time-unknown until the next ACK.

References:
- https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESCCM
- https://sensirion.com/resource/datasheet/sht4x
