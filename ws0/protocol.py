"""Draft Stage-0 binary protocol; all integers are network byte order.

AES-CCM is provided by cryptography/OpenSSL, never implemented here.
The firmware reserves counters durably before use (firmware/stage0-node/App/node_store.c) and
never resets them, not even on WIPE (gap G17), so a key never sees a repeated nonce on a board.
"""
import hashlib
import sqlite3
import struct
from pathlib import Path
from gateway import full_flush
from cryptography.hazmat.primitives.ciphers.aead import AESCCM

from . import fields

# Draft-5 envelope (docs/protocol-draft5-design.md section 3): byte 0 = version << 4 | kind,
# station u16, counter u40; then ciphertext and an 8-byte CCM tag. The C twin is
# firmware/common/ws_frame.c, checked byte for byte by tests/test_frame.py.
VERSION = 5
HEADER_LEN, TAG_LEN = 8, 8
STATION_MAX = 65535
COUNTER_MAX = 2**40 - 1   # the header holds 5 bytes; a larger counter would truncate and repeat a nonce
# ACK and NACK plaintexts (17 bytes): epoch u32, sequence u32, word u32 (host UTC at commit for an
# ACK, 0 if the gateway measured its clock wrong; the reason for a NACK), and the u40 counter of
# the observation frame being answered. The echo lets the node accept the time only from the
# reply to the frame it just sent, so a replayed ACK cannot set its clock. NACKs (gap G2) share
# the gateway's ACK counter space; the kind byte keeps the nonces distinct.
REPLY_LEN = 17


def pack_reply(epoch, sequence, word, echo):
    return struct.pack('>III', epoch, sequence, word) + echo.to_bytes(5, 'big')


def unpack_reply(plain):
    """(epoch, sequence, word, echo)"""
    if len(plain) != REPLY_LEN:
        raise ValueError('Wrong reply length')
    return (*struct.unpack('>III', plain[:12]), int.from_bytes(plain[12:], 'big'))


KIND_OBS, KIND_ACK, KIND_NACK, KIND_DIAG = 1, 2, 3, 4
# DIAG (kind 4, gap G8; draft-5 design section 4): node health, fire-and-forget (no journal, no
# ACK). Epoch, uptime s, journal pending, lost (cumulative, persisted), torn slots present, abandoned
# (cumulative, persisted), missed ACKs and rejected replies since boot, reset cause, link state;
# firmware build ID (first 4 bytes of the release commit), signal of the last authentic ACK as the
# node heard it (RSSI dBm, SNR dB; -128 = none yet), crashes since power-up, energy state.
DIAG = struct.Struct('>IIHIHHHHBBIbbBB')
RESET_CAUSES = ('unknown','power','pin','brownout','software','watchdog','lowpower','option-bytes')
LINK_STATES = ('linked','probing')
NACK_COLLISION, NACK_INVALID = 1, 2


class Nonces:
    """Reserve counters durably before encryption; never silently recreate state."""
    def __init__(self, path, key, station, kind, create=False):
        path = Path(path)
        if not create and not path.exists():
            raise ValueError('Missing nonce state: provision a NEW key, never reset counters')
        if create and path.exists():
            raise ValueError('Refusing to overwrite nonce state')
        self.db = sqlite3.connect(path)
        full_flush(self.db)  # WAL, synchronous=FULL, and on macOS flush the drive cache too (gap G4)
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
            # Review item P4: the gateway's high-water mark of the node's counter space (OBS and
            # DIAG share it). It lives here, in the state that is never restored from a backup
            # (runbook R7), so restoring observations can never lower it.
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

    def node_counter(self):
        """The stored node-counter high-water mark and regression record (gateway only)."""
        mark, count, last, at, replays = self.db.execute(
            'SELECT max_counter,regressions,last_regression,last_regression_at,replays FROM node_counter '
            'WHERE binding=?', (self.node_binding,)).fetchone()
        return {'max_node_counter': mark, 'counter_regression': count,
                'last_regression_counter': last, 'last_regression_at': at, 'replays': replays}

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


def _header_and_nonce(kind, station, counter):
    """Header (also the AAD) and the 13-byte nonce, built from the integers: kind, station u32,
    counter u64. to_bytes raises on a value its field cannot hold, so nothing is truncated."""
    if not 1 <= station <= STATION_MAX or not 1 <= counter <= COUNTER_MAX or not 1 <= kind <= 4:
        raise ValueError('Station, counter or kind out of range')
    header = bytes([VERSION << 4 | kind]) + station.to_bytes(2, 'big') + counter.to_bytes(5, 'big')
    return header, struct.pack('>BIQ', kind, station, counter)


def seal(key, station, kind, allocator, payload):
    """Authenticate the clear header and encrypt payload with an 8-byte tag."""
    # NACKs share the gateway's ACK counter space; health reports share the node's observation
    # counter space. The kind byte in the nonce keeps every (kind, counter) pair distinct.
    shared = (kind == KIND_NACK and allocator.kind == KIND_ACK) or (kind == KIND_DIAG and allocator.kind == KIND_OBS)
    if allocator.station != station or (allocator.kind != kind and not shared):
        raise ValueError('Wrong nonce allocator')
    header, nonce = _header_and_nonce(kind, station, allocator.next())
    return header + AESCCM(key, tag_length=TAG_LEN).encrypt(nonce, payload, header)


def frame_kind(packet):
    """Kind of a frame of this protocol version, or None (empty or another version)."""
    return packet[0] & 0x0F if packet and packet[0] >> 4 == VERSION else None


def frame_counter(packet):
    """Transmission counter from an (authenticated) frame header."""
    return int.from_bytes(packet[3:HEADER_LEN], 'big')


def plain_lengths(kind):
    """Plaintext lengths a frame of this kind may have before decrypting (design 3.4). An
    observation's exact length depends on its encrypted field bitmap and is checked after."""
    if kind == KIND_OBS:
        return range(fields.HEAD_LEN + 1, fields.HEAD_LEN + fields.fields_len(fields.DEFINED) + 1)
    return (REPLY_LEN,) if kind in (KIND_ACK, KIND_NACK) else (DIAG.size,)


def unseal(key, station, kind, packet):
    """Reject the wrong length, version, kind or station before decrypting, then a bad tag."""
    if len(packet) - HEADER_LEN - TAG_LEN not in plain_lengths(kind):
        raise ValueError('Wrong frame length')
    if frame_kind(packet) != kind or int.from_bytes(packet[1:3], 'big') != station:
        raise ValueError('Unexpected frame header')
    header, nonce = _header_and_nonce(kind, station, frame_counter(packet))
    return AESCCM(key, tag_length=TAG_LEN).decrypt(nonce, packet[HEADER_LEN:], header)


def encode_observation(record):
    """Gateway record -> draft-5 observation plaintext (design 5); the simulator's node uses it."""
    from gateway import validate
    validate(record)
    return fields.encode(int(record['session']), record['sequence'], record['sampled_at'] or 0, record['uptime_s'],
                         fields.ENERGY.index(record['energy_state']), record['calibration_revision'],
                         fields.codes_from_record(record))


def decode_observation(payload, station):
    """Draft-5 observation plaintext -> gateway record. INVALID fields are null, never numbers."""
    head, codes = fields.decode(payload)
    record = dict(version=5, station=station, session=str(head['epoch']), sequence=head['sequence'],
                  sampled_at=head['utc'] if head['time_known'] else None, uptime_s=head['uptime'],
                  time_quality='synchronized' if head['time_known'] else 'unknown',
                  energy_state=head['energy_state'], calibration_revision=head['calibration_revision'],
                  **fields.values(codes))
    record['quality'] = fields.quality(record)
    from gateway import validate
    validate(record)
    return record
