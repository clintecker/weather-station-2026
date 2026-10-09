# Stage-0 transport draft 1

This is a tested host protocol and portable C payload draft, **not a frozen H01 contract**.
Direct LoRa carries one observation or one acknowledgment. No mesh or module discovery.
Every integer is big-endian. Observation frame: 56 bytes. ACK frame: 40 bytes.

## Authenticated envelope

| Offset | Bytes | Field |
|---|---:|---|
| 0 | 2 | ASCII `WS` |
| 2 | 1 | Version, 1 |
| 3 | 1 | Kind: 1 observation, 2 gateway ACK |
| 4 | 4 | Numeric station ID |
| 8 | 4 | Transmission counter high word |
| 12 | 4 | Transmission counter low word |
| 16 | 24 or 8 | AES-128-CCM ciphertext |
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
| 8 | 8 | Sample UTC Unix seconds, 0 if time unknown |
| 16 | 2 | Signed temperature in 0.01°C, 0 if sensor invalid |
| 18 | 2 | Unsigned RH in 0.01%, 0 if sensor invalid |
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

ACK plaintext = acknowledged sample epoch (4) + sample sequence (4). ACK is only
created after SQLite commit; the node verifies it before removing the journal entry.
Exact duplicate observations are acknowledged again. Conflicting payloads under the
same observation identity are rejected and never acknowledged. Replayed valid data
cannot alter stored time or freshness. Replayed ACKs affect only their exact identity.

Receiver/host USB contract: one ASCII hexadecimal frame per newline, 115200 baud,
8N1. Receiver forwards opaque RF frames upstream and host ACK frames downstream;
it must never acknowledge independently. Maximum input line is 256 bytes. Radio
scheduling, host-to-node authenticated time synchronization and receive-window timing
remain to implement with the target firmware. No RF configuration is implied here.

References:
- https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESCCM
- https://sensirion.com/resource/datasheet/sht4x
