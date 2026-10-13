"""Draft Stage-0 binary protocol; all integers are network byte order.

AES-CCM is provided by cryptography/OpenSSL, never implemented here.
Firmware must implement the same durable nonce contract before RF use.
"""
import hashlib
import sqlite3
import struct
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESCCM

HEADER = struct.Struct('>2sBBIII')  # magic, version, kind, station, tx epoch, counter
# Draft 4: sample epoch/seq, UTC seconds (u32, 0 if unknown), seconds since boot (u32, always),
# T/RH, validity/time, calibration. Uptime lets the gateway reconstruct unknown times later.
OBS = struct.Struct('>IIIIhHBBH')
# Acknowledged sample epoch/seq, host UTC at commit, and the 64-bit transmission counter
# of the observation frame being answered. The echo lets the node accept the time only
# from the reply to the frame it just sent, so a replayed ACK cannot set its clock.
ACK = struct.Struct('>IIQQ')
# NACK (kind 3, gap G2): the gateway authenticated the frame but must reject it permanently
# (identity collision or invalid record). Epoch/seq, reason, reserved 0, echoed frame counter.
# It is sealed from the gateway's ACK counter space; the kind byte keeps the nonces distinct.
NACK = struct.Struct('>IIIIQ')
KIND_OBS, KIND_ACK, KIND_NACK, KIND_DIAG = 1, 2, 3, 4
# DIAG (kind 4, gap G8): node health, fire-and-forget (no journal, no ACK). Epoch, uptime s,
# journal pending, lost (cumulative, persisted), torn slots present, abandoned (cumulative,
# persisted), missed ACKs and rejected replies since boot, reset cause, link state.
DIAG = struct.Struct('>IIHIHHHHBB')
RESET_CAUSES = ('unknown','power','pin','brownout','software','watchdog','lowpower','option-bytes')
LINK_STATES = ('linked','probing')
NACK_COLLISION, NACK_INVALID = 1, 2
VERSION = 4
# Draft 3: invalid readings carry impossible fillers so a flag-blind reader never sees a
# plausible value (0.00 degC is a real Chicago temperature).
TEMP_INVALID = -32768  # 0x8000 = -327.68 degC
RH_INVALID = 0xFFFF    # 655.35 %RH


class Nonces:
    """Reserve counters durably before encryption; never silently recreate state."""
    def __init__(self, path, key, station, kind, create=False):
        path = Path(path)
        if not create and not path.exists():
            raise ValueError('Missing nonce state: provision a NEW key, never reset counters')
        if create and path.exists():
            raise ValueError('Refusing to overwrite nonce state')
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA synchronous=FULL')
        from gateway import full_flush
        full_flush(self.db)  # macOS: flush the drive cache too (gap G4)
        self.db.execute('CREATE TABLE IF NOT EXISTS nonce (binding TEXT, counter INTEGER)')
        binding = hashlib.sha256(key + struct.pack('>IB', station, kind)).hexdigest()
        row = self.db.execute('SELECT binding FROM nonce').fetchone()
        if create:
            with self.db:
                self.db.execute('INSERT INTO nonce VALUES (?,0)', (binding,))
        elif not row or row[0] != binding:
            raise ValueError('Nonce state/key/endpoint mismatch')
        self.station, self.kind = station, kind

    def next(self):
        """An immediate transaction also prevents concurrent allocator collisions."""
        self.db.execute('BEGIN IMMEDIATE')
        try:
            counter = self.db.execute('SELECT counter FROM nonce').fetchone()[0] + 1
            if counter >= 2**63:
                raise ValueError('Nonce space exhausted; rotate key')
            self.db.execute('UPDATE nonce SET counter=?', (counter,))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return counter >> 32, counter & 0xffffffff


def seal(key, station, kind, allocator, payload):
    """Authenticate the clear header and encrypt payload with a 128-bit tag."""
    # NACKs share the gateway's ACK counter space; health reports share the node's observation
    # counter space. The kind byte in the nonce keeps every (kind, counter) pair distinct.
    shared = (kind == KIND_NACK and allocator.kind == KIND_ACK) or (kind == KIND_DIAG and allocator.kind == KIND_OBS)
    if allocator.station != station or (allocator.kind != kind and not shared):
        raise ValueError('Wrong nonce allocator')
    epoch, counter = allocator.next()
    header = HEADER.pack(b'WS', VERSION, kind, station, epoch, counter)
    nonce = struct.pack('>BIII', kind, station, epoch, counter)
    return header + AESCCM(key, tag_length=16).encrypt(nonce, payload, header)


def frame_counter(packet):
    """64-bit transmission counter from an (authenticated) frame header."""
    _magic, _version, _kind, _station, high, low = HEADER.unpack(packet[:HEADER.size])
    return high << 32 | low


def unseal(key, station, kind, packet):
    """Reject unknown versions, directions, endpoints and invalid tags."""
    size = OBS.size if kind == 1 else ACK.size
    if len(packet) != HEADER.size + size + 16:
        raise ValueError('Wrong frame length')
    magic, version, direction, device, epoch, counter = HEADER.unpack(packet[:HEADER.size])
    if (magic, version, direction, device) != (b'WS', VERSION, kind, station):
        raise ValueError('Unexpected frame header')
    return AESCCM(key, tag_length=16).decrypt(
        struct.pack('>BIII', kind, station, epoch, counter),
        packet[HEADER.size:], packet[:HEADER.size])


def encode_observation(record):
    """Scale measurements; invalid values use explicit flags and zero wire slots."""
    from gateway import validate
    validate(record)
    valid = record['quality'] == 'valid'
    return OBS.pack(int(record['session']), record['sequence'], record['sampled_at'] or 0, record['uptime_s'],
                    round(record['temperature_c'] * 100) if valid else TEMP_INVALID,
                    round(record['humidity_pct'] * 100) if valid else RH_INVALID,
                    int(valid), int(record['time_quality'] == 'synchronized'), 0)


def decode_observation(payload, station):
    """Unknown time and sensor faults stay null rather than plausible measurements."""
    epoch, sequence, utc, uptime, temp, rh, valid, timed, calibration = OBS.unpack(payload)
    if valid not in (0, 1) or timed not in (0, 1) or calibration != 0:
        raise ValueError('Unsupported observation flags/calibration')
    if (not timed and utc != 0) or (not valid and (temp, rh) != (TEMP_INVALID, RH_INVALID)):
        raise ValueError('Noncanonical invalid values')
    if valid and (temp == TEMP_INVALID or rh == RH_INVALID):
        raise ValueError('Invalid-reading filler in a valid observation')
    record = dict(version=2, station=station, session=str(epoch), sequence=sequence,
                  sampled_at=utc if timed else None, uptime_s=uptime,
                  time_quality='synchronized' if timed else 'unknown',
                  temperature_c=temp / 100 if valid else None,
                  humidity_pct=rh / 100 if valid else None,
                  quality='valid' if valid else 'sensor_fault')
    from gateway import validate
    validate(record)
    return record
