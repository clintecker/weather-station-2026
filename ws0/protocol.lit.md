# protocol: the draft-5 frame on the gateway side

`protocol.py` builds and opens the draft-5 radio frames. It builds the clear header, the AES-128-CCM
nonce and the ACK, NACK and DIAG plaintexts. It builds the observation plaintext through
`ws0/fields.py`. It also holds `Nonces`, the durable counter allocator that the gateway (and the
simulator's node) reserves every nonce from. For the gateway it keeps the high-water mark of the
node's counter, which detects replays and repeated nonces.

This document is the source. `tools/tangle.py` generates `protocol.py` from the code chunks below.
The repository also holds the generated file, so imports, ruff and the tests read ordinary Python.
Edit this file, then regenerate and check:

```sh
python3 tools/tangle.py ws0/protocol.lit.md                          # write protocol.py
python3 tools/tangle.py --check ws0/protocol.lit.md                  # committed .py == tangle
python3 tools/tangle.py --weave /tmp/protocol.html ws0/protocol.lit.md   # render
```

A chunk is a fenced ` ```python {#name} ` block. A line `<<name>>` inside a chunk includes chunk
`name` at that line's indentation. Chunks appear in reading order. The root chunk (section 9) puts
them in file order.

## 1. Guarantees

| Property | Guarantee | Checked by |
|---|---|---|
| Wire format | Python and `firmware/common/ws_frame.c` produce and accept the same bytes for every kind | `tests/test_frame.py`: `test_known_answer_vectors`, `test_random_agreement_both_directions`, `test_diagnostic_frame_agreement`, `test_diag_plaintext_matches_python` |
| Field limits | a station or counter that its header field cannot hold is refused, never truncated | `test_counter_and_station_limits` |
| Gateway counter | `Nonces.next` commits a counter before it returns it and refuses past `COUNTER_MAX` | `test_gateway_allocator_stops_at_the_limit` |
| Nonce state | a missing state file raises. It is never recreated | `tests/test_stage0.py`: `test_nonce_restart_and_missing_state` |
| Durability | the nonce database runs WAL, `synchronous=FULL` and `fullfsync` | `tests/test_gateway.py`: `test_full_flush_pragmas_are_on` |
| Node counter mark | committed before the frame is acted on, kept across restarts, never moved by an unauthenticated frame | `tests/test_counter_regression.py`: `test_mark_is_raised_before_commit`, `test_mark_survives_gateway_restart`, `test_unauthenticated_frame_never_moves_the_mark` |
| Replay | an exact copy of an accepted frame is counted, with no alarm | `test_replayed_obs_gets_no_reply_and_is_not_stored`, `test_exact_duplicate_of_latest_frame_is_not_answered` |
| Regression | any other authentic frame at or below the mark raises the key-reuse alarm | `test_same_counter_different_bytes_alarms`, `test_older_frame_never_seen_still_alarms`, `test_wipe_and_reuse_alarms_on_first_frame` |
| Unseal | the wrong length, version, kind or station is refused before decryption | `test_reply_rejections`, `test_diagnostic_frame_agreement` |

The counter is the AES-CCM nonce. One nonce under one key for two different plaintexts breaks the
confidentiality and authenticity of both frames. The allocator rules in section 5 and the mark in
section 6 exist for that reason.

## 2. Module header

The generated file opens with its docstring and imports. AES-CCM comes from `cryptography`
(OpenSSL). `gateway.py` supplies `full_flush` (the SQLite durability pragmas) and `validate` (the
gateway record schema).

```python {#module-docstring}
"""Draft Stage-0 binary protocol; all integers are network byte order.

AES-CCM is provided by cryptography/OpenSSL, never implemented here.
The firmware reserves counters durably before use (firmware/stage0-node/App/node_store.c) and
never resets them, not even on WIPE, so a key never sees a repeated nonce on a board.
"""
```

```python {#imports}
import hashlib
import sqlite3
import struct
from pathlib import Path
from gateway import full_flush, validate
from cryptography.hazmat.primitives.ciphers.aead import AESCCM

from . import fields
```

## 3. Envelope

### Header

The layout is draft-5 design section 3.1. `firmware/common/ws_frame.c` builds the same bytes.
`tests/test_frame.py` compiles that file with Mbed TLS and checks agreement byte for byte (section
10).

```text
offset  0        1        3            8                 8+n
       +--------+--------+------------+-----------------+--------+
       | ver|kd | station| counter    | ciphertext (n)  | tag    |
       | 1 B    | u16    | u40        |                 | 8 B    |
       +--------+--------+------------+-----------------+--------+
        clear and authenticated (AAD)   encrypted
```

| Offset | Bytes | Constant | Contents |
|---:|---:|---|---|
| 0 | 1 | `VERSION_SHIFT`, `KIND_MASK` | `VERSION` (5) in the high nibble, kind in the low nibble |
| 1 | 2 | `STATION_AT`, `STATION_BYTES` | station id, 1 to `STATION_MAX` (65535) |
| 3 | 5 | `COUNTER_AT`, `COUNTER_BYTES` | transmission counter, 1 to `COUNTER_MAX` (2^40 − 1) |
| 8 | n | `HEADER_LEN` | AES-128-CCM ciphertext of the kind's plaintext |
| 8 + n | 8 | `TAG_LEN` | CCM tag |

The 8 header bytes are the AAD. The tag length is a fixed constant. It is never inferred from the
frame length.

```python {#envelope}
# Draft-5 envelope (docs/protocol-draft5-design.md section 3): byte 0 = version << 4 | kind,
# station u16, counter u40; then ciphertext and an 8-byte CCM tag. The C twin is
# firmware/common/ws_frame.c, checked byte for byte by tests/test_frame.py.
VERSION = 5
```

The key, the key check value and two reserved values used by other modules:

| Constant | Value | Use |
|---|---|---|
| `KEY_LEN` | 16 | AES-128 key |
| `KCV_LEN` | 3 | key check value: the first 3 bytes of AES-ECB(key, 0) |
| `SIGNAL_NONE` | −128 | DIAG RSSI and SNR before the node heard an authentic ACK |
| `EPOCH_RESERVED` | 2^32 − 1 | the bench storm test's epoch. A real boot never gets it |

```python {#key-and-markers}
KEY_LEN, KCV_LEN = 16, 3                   # AES-128 key; key check value: AES-ECB(key, 0)[:3]
SIGNAL_NONE = -128                         # DIAG rssi/snr: no authentic ACK heard yet
EPOCH_RESERVED = 2**32 - 1                 # the bench storm test's epoch; a real boot never gets it
```

```python {#header-layout}
VERSION_SHIFT, KIND_MASK = 4, 0x0F          # byte 0: version in the high nibble, kind in the low
STATION_AT, STATION_BYTES = 1, 2
COUNTER_AT, COUNTER_BYTES = STATION_AT + STATION_BYTES, 5
HEADER_LEN = COUNTER_AT + COUNTER_BYTES
TAG_LEN = 8
STATION_MAX = 2**(8 * STATION_BYTES) - 1
COUNTER_MAX = 2**(8 * COUNTER_BYTES) - 1   # a larger counter would truncate and repeat a nonce
```

A counter above `COUNTER_MAX` cannot go in the 5-byte field. Truncating it would put a small
counter on air, which repeats a nonce. Every path refuses such a counter instead (sections 5 and 7).

### Nonce

The 13-byte nonce is the kind as u8, the station as u32 and the counter as u64, big-endian. The code
builds it from the integers and never copies it from the header bytes. `ws_frame.c` uses the same
construction (`NONCE_LEN` 13).

```text
offset  0      1                  5                                13
       +------+------------------+----------------------------------+
       | kind | station u32      | counter u64                      |
       +------+------------------+----------------------------------+
```

The kind byte keeps two counter spaces apart under one key. The node's flash counter seals OBS and
DIAG. The gateway's `Nonces` database seals ACK and NACK. The same counter value in both spaces
gives two different nonces.

```python {#nonce-layout}
NONCE = struct.Struct('>BIQ')               # kind, station u32, counter u64: 13 bytes
```

### Header and nonce from the integers

`_header_and_nonce` checks the ranges first. It raises `ValueError` for a station outside 1 to
`STATION_MAX`, a counter outside 1 to `COUNTER_MAX`, or a kind outside `KIND_OBS` to `KIND_DIAG`.
`to_bytes` raises on a value its field cannot hold, so the code never masks or truncates a value.

```python {#header-and-nonce}
def _header_and_nonce(kind, station, counter):
    """Header (also the AAD) and the 13-byte nonce, built from the integers: kind, station u32,
    counter u64. to_bytes raises on a value its field cannot hold, so nothing is truncated."""
    if not 1 <= station <= STATION_MAX or not 1 <= counter <= COUNTER_MAX or not KIND_OBS <= kind <= KIND_DIAG:
        raise ValueError('Station, counter or kind out of range')
    header = (bytes([VERSION << VERSION_SHIFT | kind]) + station.to_bytes(STATION_BYTES, 'big') +
              counter.to_bytes(COUNTER_BYTES, 'big'))
    return header, NONCE.pack(kind, station, counter)
```

### Reading the header

`frame_kind` returns the kind only when the high nibble is `VERSION`. An empty packet or another
version returns `None`. A draft-4 frame starts with `0x57`, which reads as version 5 kind 7, and no
caller accepts kind 7. `frame_counter` reads the counter field. It checks nothing, so callers use it
on a frame that `unseal` authenticated, or to rebuild the nonce inside `unseal`.

```python {#frame-kind}
def frame_kind(packet):
    """Kind of a frame of this protocol version, or None (empty or another version)."""
    return packet[0] & KIND_MASK if packet and packet[0] >> VERSION_SHIFT == VERSION else None
```

```python {#frame-counter}
def frame_counter(packet):
    """Transmission counter from an (authenticated) frame header."""
    return int.from_bytes(packet[COUNTER_AT:HEADER_LEN], 'big')
```

## 4. Kinds and fixed plaintexts

| Kind | Name | Sender | Counter space | Plaintext |
|---:|---|---|---|---|
| 1 | `KIND_OBS` | node | node | observation, 23 to 78 bytes (section 8) |
| 2 | `KIND_ACK` | gateway | gateway | reply, 17 bytes |
| 3 | `KIND_NACK` | gateway | gateway | reply, 17 bytes |
| 4 | `KIND_DIAG` | node | node | `DIAG`, 32 bytes |

```python {#kinds}
KIND_OBS, KIND_ACK, KIND_NACK, KIND_DIAG = 1, 2, 3, 4
```

### ACK and NACK

Both replies carry one 17-byte layout (draft-5 design section 4). `reply_unpack` in `ws_frame.c`
reads the same fields.

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 4 | epoch of the observation answered |
| 4 | 4 | sequence of the observation answered |
| 8 | 4 | word: ACK = host UTC at commit, or 0 when the gateway measured its own clock as wrong. NACK = reason |
| 12 | 5 | echo: the counter of the observation frame answered |

The echo ties the reply to one frame. The node accepts the time only from the reply to the frame
it just sent, so a replayed ACK cannot set its clock.

```python {#reply-layout}
# ACK and NACK plaintexts (17 bytes): epoch u32, sequence u32, word u32 (host UTC at commit for an
# ACK, 0 if the gateway measured its clock wrong; the reason for a NACK), and the u40 counter of
# the observation frame being answered. The echo lets the node accept the time only from the
# reply to the frame it just sent, so a replayed ACK cannot set its clock. NACKs share
# the gateway's ACK counter space; the kind byte keeps the nonces distinct.
REPLY_HEAD = struct.Struct('>III')
REPLY_LEN = REPLY_HEAD.size + COUNTER_BYTES
```

`pack_reply` writes the echo with `to_bytes(COUNTER_BYTES)`, which raises for a value over 40 bits.
`unpack_reply` raises `ValueError('Wrong reply length')` for any length but `REPLY_LEN` and returns
`(epoch, sequence, word, echo)`.

```python {#pack-reply}
def pack_reply(epoch, sequence, word, echo):
    return REPLY_HEAD.pack(epoch, sequence, word) + echo.to_bytes(COUNTER_BYTES, 'big')
```

```python {#unpack-reply}
def unpack_reply(plain):
    """(epoch, sequence, word, echo)"""
    if len(plain) != REPLY_LEN:
        raise ValueError('Wrong reply length')
    return (*REPLY_HEAD.unpack(plain[:REPLY_HEAD.size]), int.from_bytes(plain[REPLY_HEAD.size:], 'big'))
```

NACK reasons (`ws0/service.py` picks one when an authentic observation fails decoding or storing):

| Constant | Value | Cause in `service.py` |
|---|---|---|
| `NACK_COLLISION` | 1 | `ValueError('Identity collision')`: another record holds this (epoch, sequence) |
| `NACK_INVALID` | 2 | any other `ValueError` from `decode_observation` or the store |

```python {#nack-reasons}
NACK_COLLISION, NACK_INVALID = 1, 2
```

### DIAG

DIAG is the node's health report. It is fire-and-forget: the node does not journal it and the
gateway does not answer it. The struct is `>IIHIHHHHBBIbbBB`, 32 bytes:

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 4 | epoch |
| 4 | 4 | uptime (s) |
| 8 | 2 | journal pending |
| 10 | 4 | journal lost total (cumulative, persisted) |
| 14 | 2 | torn slots present |
| 16 | 2 | abandoned total (cumulative, persisted) |
| 18 | 2 | missed ACKs since boot |
| 20 | 2 | rejected replies since boot |
| 22 | 1 | reset cause, an index into `RESET_CAUSES` |
| 23 | 1 | link state, an index into `LINK_STATES` |
| 24 | 4 | firmware build id: the first 4 bytes of the release commit |
| 28 | 1 | RSSI of the last authentic ACK, signed dBm, `SIGNAL_NONE` = none yet |
| 29 | 1 | SNR of the last authentic ACK, signed dB, `SIGNAL_NONE` = none yet |
| 30 | 1 | crashes since power-up |
| 31 | 1 | energy state, an index into `fields.ENERGY` |

`ws_diag_pack` in the firmware writes the same bytes (`test_diag_plaintext_matches_python`). The
order of `RESET_CAUSES` follows `ws_reset_t` in `watchdog.h` (`test_reset_cause_numbering`).
`service.py` maps an index past the end of a table to `'unknown'`.

```python {#diag-layout}
# DIAG (kind 4; draft-5 design section 4): node health, fire-and-forget (no journal, no
# ACK). Epoch, uptime s, journal pending, lost (cumulative, persisted), torn slots present, abandoned
# (cumulative, persisted), missed ACKs and rejected replies since boot, reset cause, link state;
# firmware build ID (first 4 bytes of the release commit), signal of the last authentic ACK as the
# node heard it (RSSI dBm, SNR dB; -128 = none yet), crashes since power-up, energy state.
DIAG = struct.Struct('>IIHIHHHHBBIbbBB')
RESET_CAUSES = ('unknown','power','pin','brownout','software','watchdog','lowpower','option-bytes')
LINK_STATES = ('linked','probing')
```

## 5. Nonces: the durable counter allocator

`Nonces` owns one SQLite file per (key, station, kind). The gateway opens one for `KIND_ACK`. The
simulator's node opens one for `KIND_OBS`. A hardware node keeps its counter in flash
(`node_store.c`), so provisioning a hardware station creates only the gateway file.

```python {#nonces-class}
class Nonces:
    """Reserve counters durably before encryption; never silently recreate state."""
    <<nonces-init>>

    <<node-counter>>

    <<advance-node-counter>>

    <<next>>
```

### Opening

| Step | Check | On failure |
|---|---|---|
| 1 | `create=False` and the file is missing | `ValueError('Missing nonce state: provision a NEW key, never reset counters')` |
| 2 | `create=True` and the file exists | `ValueError('Refusing to overwrite nonce state')` |
| 3 | connect, then `full_flush`: WAL, `synchronous=FULL`, and `F_FULLFSYNC` on macOS | — |
| 4 | binding = SHA-256 hex of key ‖ station u32 ‖ kind u8 | — |
| 5 | `create=True`: insert (binding, 0) in one transaction | — |
| 6 | otherwise the stored binding must equal this one | `ValueError('Nonce state/key/endpoint mismatch')` |

**Why the state is never recreated.** A new file starts at counter 0, so its first counter would
be 1. The key already used counter 1 and every counter up to the lost value. Recreating the file
silently would repeat nonces under the same key. Only `provision` in `ws0/__main__.py` passes
`create=True`, and it generates a new key in the same step. The error text names that remedy.

**Why the binding.** The binding is a hash of the key, station and kind. Step 6 fails for a state
file copied to another station, used with another key, or opened for the wrong kind. So the file
never hands out counters for another nonce space. The file stores the hash, not the key.

`WS0_UNSAFE_FAST_FSYNC=1` turns the durability pragmas off for simulations and unit tests
(`gateway.full_flush`). Those runs claim no power-loss durability.

```python {#nonces-init}
def __init__(self, path, key, station, kind, create=False):
    path = Path(path)
    if not create and not path.exists():
        raise ValueError('Missing nonce state: provision a NEW key, never reset counters')
    if create and path.exists():
        raise ValueError('Refusing to overwrite nonce state')
    self.db = sqlite3.connect(path)
    full_flush(self.db)  # WAL, synchronous=FULL, and on macOS flush the drive cache too
    self.db.execute('CREATE TABLE IF NOT EXISTS nonce (binding TEXT, counter INTEGER)')
    binding = hashlib.sha256(key + struct.pack('>IB', station, kind)).hexdigest()
    row = self.db.execute('SELECT binding FROM nonce').fetchone()
    if create:
        with self.db:
            self.db.execute('INSERT INTO nonce VALUES (?,0)', (binding,))
    elif not row or row[0] != binding:
        raise ValueError('Nonce state/key/endpoint mismatch')
    self.station, self.kind = station, kind
    <<node-counter-tables>>
```

### Reserving a counter

`next` runs in a `BEGIN IMMEDIATE` transaction:

```text
1. BEGIN IMMEDIATE                 take the write lock before reading
2. counter = stored counter + 1
3. counter > COUNTER_MAX           raise 'Nonce space exhausted; rotate key', roll back
4. UPDATE, COMMIT                  durable (synchronous=FULL)
5. return counter                  only now does seal() encrypt with it
```

| Event | Result |
|---|---|
| Crash before the commit | the counter was not returned, so no frame used it. The next call returns it |
| Crash after the commit | the counter is stored as used. A frame may or may not have gone out. The next call returns the counter after it |
| Two processes on one file | `BEGIN IMMEDIATE` takes the write lock before the read, so they never read the same value |
| Any exception | rollback, then re-raise. The stored counter is unchanged |

A crash therefore skips a counter at most. It never repeats one.

```python {#next}
def next(self):
    """An immediate transaction also prevents concurrent allocator collisions."""
    self.db.execute('BEGIN IMMEDIATE')
    try:
        counter = self.db.execute('SELECT counter FROM nonce').fetchone()[0] + 1
        if counter > COUNTER_MAX:
            raise ValueError('Nonce space exhausted; rotate key')
        self.db.execute('UPDATE nonce SET counter=?', (counter,))
        self.db.commit()
    except Exception:
        self.db.rollback()
        raise
    return counter
```

## 6. The node counter high-water mark

The node seals OBS and DIAG from one strictly increasing counter. Every transmission, retries
included, takes a fresh one, and WIPE keeps it (`store_next_counter` in `node_store.c`). An
authentic node frame at or below the highest counter seen so far is therefore a copy or a repeated
nonce. The gateway keeps that mark in its `KIND_ACK` nonce file.

### Tables

Opening a `KIND_ACK` allocator adds two tables and seeds the mark at 0. Both are keyed by
`node_binding`, the binding of (key, station, `KIND_OBS`).

| Table | Columns | Contents |
|---|---|---|
| `node_counter` | `binding`, `max_counter`, `regressions`, `last_regression`, `last_regression_at`, `replays` | the mark, the regression count with the last one's counter and time, the replay count |
| `node_frames` | `binding`, `counter`, `digest` | SHA-256 of each frame accepted as fresh, by counter |

The mark lives in the nonce file, not the observation database. An operator can restore the
observation database from a backup. The nonce file is never restored, so a restore cannot lower the
mark.

```python {#node-counter-tables}
if kind == KIND_ACK:
    # The gateway's high-water mark of the node's counter space (OBS and
    # DIAG share it). It lives here, in the state that is never restored from a backup,
    # so restoring observations can never lower it.
    self.node_binding = hashlib.sha256(key + struct.pack('>IB', station, KIND_OBS)).hexdigest()
    self.db.execute('CREATE TABLE IF NOT EXISTS node_counter (binding TEXT PRIMARY KEY, '
                    'max_counter INTEGER NOT NULL, regressions INTEGER NOT NULL, '
                    'last_regression INTEGER, last_regression_at REAL, replays INTEGER NOT NULL DEFAULT 0)')
    # SHA-256 of every authentic node frame accepted as fresh, by counter: a later frame with
    # the same counter and the same bytes is a replay (harmless); different bytes under one
    # counter is a repeated nonce (draft-5 design section 8).
    self.db.execute('CREATE TABLE IF NOT EXISTS node_frames (binding TEXT, counter INTEGER, digest TEXT, '
                    'PRIMARY KEY(binding, counter))')
    with self.db:
        self.db.execute('INSERT OR IGNORE INTO node_counter (binding,max_counter,regressions) VALUES (?,0,0)',
                        (self.node_binding,))
```

### Verdicts

`service.py` calls `advance_node_counter(counter, now, digest)` only for a frame that `unseal`
authenticated. `digest` is the SHA-256 hex of the whole frame. It runs in one `BEGIN IMMEDIATE`
transaction:

| Condition | Verdict | Change | What `service.py` does |
|---|---|---|---|
| `counter > mark` | `fresh` | mark = counter, store (counter, digest) | goes on to decode and store the frame |
| `counter <= mark`, stored digest for this counter equals `digest` | `replay` | `replays + 1` | rejection row (once per frame), raises `Replay`. No reply, no alarm |
| `counter <= mark`, no stored digest or a different one | `regression` | `regressions + 1`, `last_regression` = counter, `last_regression_at` = now | rejection row, raises `CounterRegression`. No reply. Status shows `'possible key reuse: re-key the node'` |

**Why a replay is not an alarm.** An exact copy reuses no nonce. It is the same ciphertext under the
same nonce, so it reveals nothing new. The gateway still neither answers nor stores it.

**Why a regression is an alarm.** Different bytes under a counter already seen have one cause. The
node sealed a second plaintext with a nonce it already used. That breaks CCM for both frames. An
unknown frame below the mark counts too. Direct LoRa does not reorder frames, so the gateway treats
an older counter that never arrived as reuse (`test_older_frame_never_seen_still_alarms`). A node
that restarts its counter under the old key produces this verdict on its first frame
(`test_wipe_and_reuse_alarms_on_first_frame`). The remedy is a new key.

**Why before the frame is acted on.** `service.py` calls this before `decode_observation` and the
database commit. A crash or a failed commit after it leaves the mark at or above every counter the
gateway stored or answered. The node retries with a fresh counter, so the raised mark never rejects
a genuine retry (`test_mark_is_raised_before_commit`).

An exception rolls the transaction back and re-raises.

```python {#advance-node-counter}
def advance_node_counter(self, counter, now, digest):
    """Call only for an authenticated node frame, with the SHA-256 hex digest of its bytes.
    Returns 'fresh' (counter above the mark: the mark is raised and the digest kept), 'replay'
    (an exact copy of a frame already accepted: counted, no alarm) or 'regression' (at or below
    the mark with different or unknown bytes: a repeated nonce or key reuse, counted for the
    alarm). Committed before the frame is acted on, so a crash can never leave the mark lower
    than a counter the gateway stored or answered."""
    self.db.execute('BEGIN IMMEDIATE')
    try:
        mark = self.db.execute('SELECT max_counter FROM node_counter WHERE binding=?',
                               (self.node_binding,)).fetchone()[0]
        if counter > mark:
            verdict = 'fresh'
            self.db.execute('UPDATE node_counter SET max_counter=? WHERE binding=?', (counter, self.node_binding))
            self.db.execute('INSERT OR REPLACE INTO node_frames VALUES (?,?,?)', (self.node_binding, counter, digest))
        else:
            seen = self.db.execute('SELECT digest FROM node_frames WHERE binding=? AND counter=?',
                                   (self.node_binding, counter)).fetchone()
            if seen and seen[0] == digest:
                verdict = 'replay'
                self.db.execute('UPDATE node_counter SET replays=replays+1 WHERE binding=?', (self.node_binding,))
            else:
                verdict = 'regression'
                self.db.execute('UPDATE node_counter SET regressions=regressions+1, last_regression=?, '
                                'last_regression_at=? WHERE binding=?', (counter, now, self.node_binding))
        self.db.commit()
    except Exception:
        self.db.rollback()
        raise
    return verdict
```

`node_counter` returns the stored row as a dict for the status page, the HTTP API and MQTT. Only a
`KIND_ACK` allocator has `node_binding`, so these two methods are for the gateway only.

| Key | Column |
|---|---|
| `max_node_counter` | `max_counter` |
| `counter_regression` | `regressions` |
| `last_regression_counter` | `last_regression` |
| `last_regression_at` | `last_regression_at` |
| `replays` | `replays` |

```python {#node-counter}
def node_counter(self):
    """The stored node-counter high-water mark and regression record (gateway only)."""
    mark, count, last, at, replays = self.db.execute(
        'SELECT max_counter,regressions,last_regression,last_regression_at,replays FROM node_counter '
        'WHERE binding=?', (self.node_binding,)).fetchone()
    return {'max_node_counter': mark, 'counter_regression': count,
            'last_regression_counter': last, 'last_regression_at': at, 'replays': replays}
```

## 7. Seal and unseal

### seal

`seal(key, station, kind, allocator, payload)` returns header ‖ ciphertext ‖ tag. Checks in order:

| Step | Check | On failure |
|---|---|---|
| 1 | `allocator.station == station` | `ValueError('Wrong nonce allocator')` |
| 2 | `allocator.kind == kind`, or a shared space: NACK on an ACK allocator, DIAG on an OBS allocator | `ValueError('Wrong nonce allocator')` |
| 3 | `allocator.next()` reserves a counter durably | `ValueError('Nonce space exhausted; rotate key')` |
| 4 | `_header_and_nonce`: station, counter and kind ranges | `ValueError('Station, counter or kind out of range')` |
| 5 | AES-CCM encrypt, AAD = header, `TAG_LEN` 8 | — |

The shared spaces are safe because the kind byte is in the nonce. ACK 5 and NACK 5 use different
nonces. A failure at step 4 leaves the counter of step 3 consumed. A skipped counter is never reused.

```python {#seal}
def seal(key, station, kind, allocator, payload):
    """Authenticate the clear header and encrypt payload with an 8-byte tag."""
    # NACKs share the gateway's ACK counter space; health reports share the node's observation
    # counter space. The kind byte in the nonce keeps every (kind, counter) pair distinct.
    shared = (kind == KIND_NACK and allocator.kind == KIND_ACK) or (kind == KIND_DIAG and allocator.kind == KIND_OBS)
    if allocator.station != station or (allocator.kind != kind and not shared):
        raise ValueError('Wrong nonce allocator')
    header, nonce = _header_and_nonce(kind, station, allocator.next())
    return header + AESCCM(key, tag_length=TAG_LEN).encrypt(nonce, payload, header)
```

### Plaintext lengths

`unseal` checks the plaintext length before it decrypts (draft-5 design section 3.4). Plaintext
length = frame length − `HEADER_LEN` − `TAG_LEN`.

| Kind | Plaintext bytes | Frame bytes |
|---|---|---|
| OBS | `fields.HEAD_LEN + 1` (23) to `fields.HEAD_LEN + fields.fields_len(fields.DEFINED)` (78) | 39 to 94 |
| ACK | `REPLY_LEN` (17) | 33 |
| NACK | `REPLY_LEN` (17) | 33 |
| DIAG | `DIAG.size` (32) | 48 |
| other | none | every length is refused |

The OBS range covers every bitmap of the full catalog, not one build's. `unseal` refuses an OBS
plaintext with no field here, because the smallest field adds one byte. The exact OBS length depends
on the encrypted field bitmap, so `fields.decode` checks it after decryption.

```python {#plain-length-table}
# Plaintext lengths a frame of each kind may have before decrypting (design 3.4). An observation's
# exact length depends on its encrypted field bitmap and is checked after.
PLAIN_LENGTHS = {KIND_OBS: range(fields.HEAD_LEN + 1, fields.HEAD_LEN + fields.fields_len(fields.DEFINED) + 1),
                 KIND_ACK: (REPLY_LEN,), KIND_NACK: (REPLY_LEN,), KIND_DIAG: (DIAG.size,)}
```

```python {#plain-lengths}
def plain_lengths(kind):
    return PLAIN_LENGTHS.get(kind, ())
```

### unseal

`unseal(key, station, kind, packet)` returns the plaintext. Checks in order:

| Step | Check | On failure |
|---|---|---|
| 1 | plaintext length is in `plain_lengths(kind)` | `ValueError('Wrong frame length')` |
| 2 | `frame_kind(packet) == kind`: version 5 and this kind | `ValueError('Unexpected frame header')` |
| 3 | the station field equals `station` | `ValueError('Unexpected frame header')` |
| 4 | `_header_and_nonce` from (kind, station, header counter): the counter is 1 to `COUNTER_MAX` | `ValueError('Station, counter or kind out of range')` |
| 5 | AES-CCM decrypt with the rebuilt header as AAD | `cryptography.exceptions.InvalidTag` |

Steps 1 to 4 cost no cryptography. Step 5 fails for a wrong key, a changed byte anywhere, or a
changed kind (the kind is in the nonce and the AAD). `service.py` never answers a frame that fails
here. A NACK for an unauthenticated frame would let anyone make the node drop a record.

`ws_open_reply` in `ws_frame.c` applies the same checks to ACK and NACK on the node
(`test_reply_rejections`).

```python {#unseal}
def unseal(key, station, kind, packet):
    """Reject the wrong length, version, kind or station before decrypting, then a bad tag."""
    if len(packet) - HEADER_LEN - TAG_LEN not in plain_lengths(kind):
        raise ValueError('Wrong frame length')
    if frame_kind(packet) != kind or int.from_bytes(packet[STATION_AT:COUNTER_AT], 'big') != station:
        raise ValueError('Unexpected frame header')
    header, nonce = _header_and_nonce(kind, station, frame_counter(packet))
    return AESCCM(key, tag_length=TAG_LEN).decrypt(nonce, packet[HEADER_LEN:], header)
```

## 8. Observations

The observation plaintext layout is draft-5 design section 5, implemented in `ws0/fields.py`. These
two functions convert between it and the gateway record (design section 5.7).

`encode_observation` validates the record with `gateway.validate`, then calls `fields.encode`. The
simulator's node uses it. Gateway record to `fields.encode` arguments:

| Record key | Argument |
|---|---|
| `session` (string) | epoch, `int(...)` |
| `sequence` | sequence |
| `sampled_at`, `None` → 0 | UTC |
| `uptime_s` | uptime |
| `energy_state` | its index in `fields.ENERGY` |
| `calibration_revision` | calibration revision |
| present fields | codes, from `fields.codes_from_record` |

```python {#encode-observation}
def encode_observation(record):
    """Gateway record -> draft-5 observation plaintext (design 5); the simulator's node uses it."""
    validate(record)
    return fields.encode(int(record['session']), record['sequence'], record['sampled_at'] or 0, record['uptime_s'],
                         fields.ENERGY.index(record['energy_state']), record['calibration_revision'],
                         fields.codes_from_record(record))
```

`decode_observation` runs the canonical decode (`fields.decode`), which raises `ValueError` for a
non-canonical plaintext. It then builds the record:

| Record key | Source |
|---|---|
| `version` | `VERSION` |
| `station` | the station name passed in |
| `session` | `str(epoch)` |
| `sequence` | sequence |
| `sampled_at` | UTC when the time-known flag is set, else `None` |
| `uptime_s` | uptime |
| `time_quality` | `'synchronized'` when the time is known, else `'unknown'` |
| `energy_state`, `calibration_revision` | from the header |
| one key per present field | `fields.values`: an INVALID field is `None`, never a number |
| `quality` | `fields.quality(record)` |

`gateway.validate` checks the result. A `ValueError` from either step reaches `service.py`, which
answers the authentic frame with `NACK_INVALID` (`tests/test_stage0.py`:
`test_invalid_authentic_record_is_nacked`).

```python {#decode-observation}
def decode_observation(payload, station):
    """Draft-5 observation plaintext -> gateway record. INVALID fields are null, never numbers."""
    head, codes = fields.decode(payload)
    record = dict(version=VERSION, station=station, session=str(head['epoch']), sequence=head['sequence'],
                  sampled_at=head['utc'] if head['time_known'] else None, uptime_s=head['uptime'],
                  time_quality='synchronized' if head['time_known'] else 'unknown',
                  energy_state=head['energy_state'], calibration_revision=head['calibration_revision'],
                  **fields.values(codes))
    record['quality'] = fields.quality(record)
    validate(record)
    return record
```

## 9. The file

The root chunk puts the chunks in the order of the committed `protocol.py`.

```python {#protocol.py}
<<module-docstring>>
<<imports>>

<<envelope>>
<<key-and-markers>>
<<header-layout>>
<<nonce-layout>>
<<reply-layout>>


<<pack-reply>>


<<unpack-reply>>


<<kinds>>
<<diag-layout>>
<<nack-reasons>>


<<nonces-class>>


<<header-and-nonce>>


<<seal>>


<<frame-kind>>


<<frame-counter>>


<<plain-length-table>>


<<plain-lengths>>


<<unseal>>


<<encode-observation>>


<<decode-observation>>
```

## 10. Tests

| File | What it checks |
|---|---|
| `tests/test_frame.py`, `FrameAgreement` | builds `firmware/common/ws_frame.c` with Mbed TLS. Known-answer vectors made from the spec (`test_vectors_follow_the_spec`), Python and C on the same vectors (`test_known_answer_vectors`), 300 random keys, stations and counters in both directions (`test_random_agreement_both_directions`), field limits on both sides (`test_counter_and_station_limits`), `Nonces.next` at `COUNTER_MAX` (`test_gateway_allocator_stops_at_the_limit`), reply rejections (`test_reply_rejections`), DIAG frames and plaintext (`test_diagnostic_frame_agreement`, `test_diag_plaintext_matches_python`) |
| `tests/test_frame.py`, `FirmwareTables` | the TX self-test vectors in `App/selftest.c` (`test_selftest_vectors`) and the `RESET_CAUSES` order (`test_reset_cause_numbering`) |
| `tests/test_counter_regression.py` | every verdict of section 6 through `Gateway.receive`, the shared OBS and DIAG space (`test_obs_and_diag_share_one_counter_space`), restart and write-ahead behaviour, and harness runs that must never alarm |
| `tests/test_stage0.py` | `test_nonce_restart_and_missing_state`, `test_invalid_authentic_record_is_nacked` |
| `tests/test_gateway.py` | `test_full_flush_pragmas_are_on` |

`FrameAgreement` needs a C compiler and `vendor/`. CI sets `WS_REQUIRE_VENDOR=1`, so a missing
`vendor/` fails these tests instead of skipping them.

```sh
.venv/bin/python -m unittest tests.test_frame tests.test_counter_regression tests.test_stage0 tests.test_gateway
```
