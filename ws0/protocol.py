# GENERATED from protocol.lit.md by tools/tangle.py: do not edit. Edit the document, then run
# tools/tangle.py ws0/protocol.lit.md (tests/test_tangle.py checks this file).
"""Binary radio protocol, version 5, gateway side. All integers are big-endian (network byte order).

AES-CCM comes from cryptography (OpenSSL). This module does not implement it.
The firmware reserves each counter durably before use (firmware/stage0-node/App/node_store.c).
The firmware never resets the counter, not even on WIPE. A flash-layout change does reset it,
and always comes with a new key (docs/runbook-moving-boards.md). So one key never sees a
repeated nonce on one board.
"""
import hashlib
import sqlite3
import struct
from pathlib import Path
from gateway import full_flush, validate
from cryptography.hazmat.primitives.ciphers.aead import AESCCM

from . import fields

# Envelope (docs/protocol-design.md section 3): byte 0 = version << 4 | kind, then station u16
# and counter u40. The ciphertext and an 8-byte CCM tag follow. firmware/common/ws_frame.c builds
# the same bytes. tests/test_frame.py compares them byte for byte.
VERSION = 5
KEY_LEN, KCV_LEN = 16, 3                   # AES-128 key. Key check value = AES-ECB(key, 0)[:3]
SIGNAL_NONE = -128                         # health report RSSI and SNR: no authentic ACK heard yet
EPOCH_RESERVED = 2**32 - 1                 # the bench storm test's epoch. A real boot never gets it
VERSION_SHIFT, KIND_MASK = 4, 0x0F          # byte 0: version in the high nibble, kind in the low
STATION_AT, STATION_BYTES = 1, 2
COUNTER_AT, COUNTER_BYTES = STATION_AT + STATION_BYTES, 5
HEADER_LEN = COUNTER_AT + COUNTER_BYTES
TAG_LEN = 8
STATION_MAX = 2**(8 * STATION_BYTES) - 1
COUNTER_MAX = 2**(8 * COUNTER_BYTES) - 1   # a larger counter would truncate and repeat a nonce
NONCE = struct.Struct('>BIQ')               # kind, station u32, counter u64: 13 bytes
# ACK and NACK plaintexts (17 bytes): epoch u32, sequence u32, word u32, then the u40 counter of
# the observation frame answered. The word of an ACK is the host UTC at commit, or 0 if the
# gateway measured its clock as wrong. The word of a NACK is the reason. The node accepts the
# time only from the reply to the frame that it just sent, so a replayed ACK cannot set its
# clock. NACKs share the gateway's ACK counter space. The kind byte keeps the nonces distinct.
REPLY_HEAD = struct.Struct('>III')
REPLY_LEN = REPLY_HEAD.size + COUNTER_BYTES


def pack_reply(epoch, sequence, word, echo):
    return REPLY_HEAD.pack(epoch, sequence, word) + echo.to_bytes(COUNTER_BYTES, 'big')


def unpack_reply(plain):
    """(epoch, sequence, word, echo)"""
    if len(plain) != REPLY_LEN:
        raise ValueError('Wrong reply length')
    return (*REPLY_HEAD.unpack(plain[:REPLY_HEAD.size]), int.from_bytes(plain[REPLY_HEAD.size:], 'big'))


KIND_OBS, KIND_ACK, KIND_NACK, KIND_DIAG = 1, 2, 3, 4
# Health report (kind 4, docs/protocol-design.md section 4). The node sends it once: no journal,
# no ACK. Fields: epoch, uptime s, journal pending, lost (cumulative, persisted), torn slots
# present, abandoned (cumulative, persisted), missed ACKs and rejected replies since boot, reset
# cause, link state, firmware build ID (first 4 bytes of the release commit), the signal of the
# last authentic ACK as the node heard it (RSSI dBm, SNR dB, -128 = none yet), crashes since
# power-up, energy state.
DIAG = struct.Struct('>IIHIHHHHBBIbbBB')
RESET_CAUSES = ('unknown','power','pin','brownout','software','watchdog','lowpower','option-bytes')
LINK_STATES = ('linked','probing')
NACK_COLLISION, NACK_INVALID = 1, 2


class Nonces:
    """Reserve each counter durably before encryption. Never recreate state silently."""
    def __init__(self, path, key, station, kind, create=False):
        path = Path(path)
        if not create and not path.exists():
            raise ValueError('Missing nonce state: provision a NEW key, never reset counters')
        if create and path.exists():
            raise ValueError('Refusing to overwrite nonce state')
        self.db = sqlite3.connect(path)
        full_flush(self.db)  # WAL and synchronous=FULL. On macOS, also flush the drive cache
        self.db.execute('CREATE TABLE IF NOT EXISTS nonce (binding TEXT, counter INTEGER)')
        binding = hashlib.sha256(key + struct.pack('>IB', station, kind)).hexdigest()
        row = self.db.execute('SELECT binding FROM nonce').fetchone()
        if create:
            with self.db:
                self.db.execute('INSERT INTO nonce VALUES (?,0)', (binding,))
        elif not row or row[0] != binding:
            raise ValueError('Nonce state/key/endpoint mismatch')
        self.station, self.kind = station, kind
        if kind == KIND_ACK:
            # The gateway's high-water mark of the node's counter space. Observations and health
            # reports share that space. The mark lives here, in state that is never restored from a
            # backup, so a restore of the observations can never lower it.
            self.node_binding = hashlib.sha256(key + struct.pack('>IB', station, KIND_OBS)).hexdigest()
            self.db.execute('CREATE TABLE IF NOT EXISTS node_counter (binding TEXT PRIMARY KEY, '
                            'max_counter INTEGER NOT NULL, regressions INTEGER NOT NULL, '
                            'last_regression INTEGER, last_regression_at REAL, replays INTEGER NOT NULL DEFAULT 0)')
            # SHA-256 of every authentic node frame accepted as fresh, by counter. A later frame with the
            # same counter and the same bytes is a replay (harmless). Different bytes under one counter
            # are a repeated nonce (docs/protocol-design.md section 6).
            self.db.execute('CREATE TABLE IF NOT EXISTS node_frames (binding TEXT, counter INTEGER, digest TEXT, '
                            'PRIMARY KEY(binding, counter))')
            with self.db:
                self.db.execute('INSERT OR IGNORE INTO node_counter (binding,max_counter,regressions) VALUES (?,0,0)',
                                (self.node_binding,))

    def node_counter(self):
        """Return the stored node-counter high-water mark and regression record (gateway only)."""
        mark, count, last, at, replays = self.db.execute(
            'SELECT max_counter,regressions,last_regression,last_regression_at,replays FROM node_counter '
            'WHERE binding=?', (self.node_binding,)).fetchone()
        return {'max_node_counter': mark, 'counter_regression': count,
                'last_regression_counter': last, 'last_regression_at': at, 'replays': replays}

    def advance_node_counter(self, counter, now, digest):
        """Call only for an authenticated node frame, with the SHA-256 hex digest of its bytes.
        Return one of three verdicts:
        'fresh': the counter is above the mark. The mark is raised and the digest kept.
        'replay': an exact copy of a frame already accepted. Counted, no alarm.
        'regression': at or below the mark with different or unknown bytes. This is a repeated
        nonce or key reuse, counted for the alarm.
        The commit comes before the gateway acts on the frame. So after a crash the mark is never
        lower than a counter that the gateway stored or answered."""
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

    def next(self):
        """Reserve and commit the next counter. The immediate transaction also stops two allocators
        on one file from reading the same counter."""
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


def _header_and_nonce(kind, station, counter):
    """Return the header (also the AAD) and the 13-byte nonce. Both come from the integers: kind,
    station u32, counter u64. to_bytes raises on a value that its field cannot hold, so no value
    is truncated."""
    if not 1 <= station <= STATION_MAX or not 1 <= counter <= COUNTER_MAX or not KIND_OBS <= kind <= KIND_DIAG:
        raise ValueError('Station, counter or kind out of range')
    header = (bytes([VERSION << VERSION_SHIFT | kind]) + station.to_bytes(STATION_BYTES, 'big') +
              counter.to_bytes(COUNTER_BYTES, 'big'))
    return header, NONCE.pack(kind, station, counter)


def seal(key, station, kind, allocator, payload):
    """Authenticate the clear header and encrypt the payload with an 8-byte tag."""
    # NACKs share the gateway's ACK counter space. Health reports share the node's observation
    # counter space. The kind byte in the nonce keeps every (kind, counter) pair distinct.
    shared = (kind == KIND_NACK and allocator.kind == KIND_ACK) or (kind == KIND_DIAG and allocator.kind == KIND_OBS)
    if allocator.station != station or (allocator.kind != kind and not shared):
        raise ValueError('Wrong nonce allocator')
    header, nonce = _header_and_nonce(kind, station, allocator.next())
    return header + AESCCM(key, tag_length=TAG_LEN).encrypt(nonce, payload, header)


def frame_kind(packet):
    """Return the kind of a frame of this protocol version. Return None for an empty packet or
    another version."""
    return packet[0] & KIND_MASK if packet and packet[0] >> VERSION_SHIFT == VERSION else None


def frame_counter(packet):
    """Return the transmission counter from the header of an authenticated frame."""
    return int.from_bytes(packet[COUNTER_AT:HEADER_LEN], 'big')


# The plaintext lengths that a frame of each kind may have, checked before decryption
# (docs/protocol-design.md section 3.4). The exact length of an observation depends on its
# encrypted field bitmap. fields.decode checks it after decryption.
PLAIN_LENGTHS = {KIND_OBS: range(fields.HEAD_LEN + 1, fields.HEAD_LEN + fields.fields_len(fields.DEFINED) + 1),
                 KIND_ACK: (REPLY_LEN,), KIND_NACK: (REPLY_LEN,), KIND_DIAG: (DIAG.size,)}


def plain_lengths(kind):
    return PLAIN_LENGTHS.get(kind, ())


def unseal(key, station, kind, packet):
    """Reject the wrong length, version, kind or station before decryption. Then reject a bad tag."""
    if len(packet) - HEADER_LEN - TAG_LEN not in plain_lengths(kind):
        raise ValueError('Wrong frame length')
    if frame_kind(packet) != kind or int.from_bytes(packet[STATION_AT:COUNTER_AT], 'big') != station:
        raise ValueError('Unexpected frame header')
    header, nonce = _header_and_nonce(kind, station, frame_counter(packet))
    return AESCCM(key, tag_length=TAG_LEN).decrypt(nonce, packet[HEADER_LEN:], header)


def encode_observation(record):
    """Convert a gateway record to an observation plaintext (docs/protocol-design.md section 5).
    The simulator's node uses it."""
    validate(record)
    return fields.encode(int(record['session']), record['sequence'], record['sampled_at'] or 0, record['uptime_s'],
                         fields.ENERGY.index(record['energy_state']), record['calibration_revision'],
                         fields.codes_from_record(record))


def decode_observation(payload, station):
    """Convert an observation plaintext to a gateway record. INVALID fields are None, never numbers."""
    head, codes = fields.decode(payload)
    record = dict(version=VERSION, station=station, session=str(head['epoch']), sequence=head['sequence'],
                  sampled_at=head['utc'] if head['time_known'] else None, uptime_s=head['uptime'],
                  time_quality='synchronized' if head['time_known'] else 'unknown',
                  energy_state=head['energy_state'], calibration_revision=head['calibration_revision'],
                  **fields.values(codes))
    record['quality'] = fields.quality(record)
    validate(record)
    return record
