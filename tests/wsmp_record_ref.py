"""Reference computations for the module record v1.0, its calibration and the rounding helper, written
from docs/superpowers/specs/2026-10-21-sensor-module-ports-design.md sections 6.7 and 6.9, independent
of firmware/common/wsmp.c, wsmp_cal.c and ws_round.h.

Integer arithmetic only: Python's // is floor division, so div_round is the spec's formula as written.
Python's round() (half to even) is never used here."""
import csv
from pathlib import Path

RECORD_LEN = 128
MAGIC = b'WSMR'
CRC_AT = 0x7C

# Record status codes, identity-flag bits 4-7 (section 6.9, Checks).
APPLIED, READ, BLANK, NO_MAGIC, VERSION, MALFORMED, CRC, CAL_REJECTED, SENSOR_CHANGED = range(9)
# Serial sources, identity-flag bits 0-1 (section 6.7).
SRC_PORT, SRC_RECORD, SRC_SENSOR = 0, 1, 2

# The calibration table frozen for record major 1 (section 6.9), at each quantity's channel scale:
# quantity: (offset bound, gain min, gain max, physical min, physical max, margin below, margin above).
CAL = {
    1: (200, 980_000, 1_020_000, -8_000, 6_000, 0, 0),             # air temperature, 0.01 degC
    2: (1_000, 900_000, 1_100_000, 0, 10_000, 300, 300),           # relative humidity, 0.01 %
    3: (50, 990_000, 1_010_000, 3_000, 11_000, 0, 0),              # station pressure, 0.1 hPa
    8: (16, 100_000, 10_000_000, 0, 1_048_576, 16, 0),             # UVA counts
}

# WSMP section 4.4: each module type's channels as (quantity, kind). Types 8 (battery) and 9 (power rails)
# are copied from the power-telemetry design (docs/superpowers/specs/2026-10-29-power-telemetry-design.md
# section 8.1), not from the generated registry.
CHANNELS = {
    1: ((1, 2), (2, 2)), 2: ((3, 2),), 3: ((8, 2),), 4: ((1, 2), (2, 2)),
    5: ((9, 2), (11, 6), (12, 6), (13, 6), (14, 6), (15, 1), (16, 10)),
    6: ((17, 6), (5, 7), (6, 8), (6, 9)), 7: ((7, 6),),
    8: ((9, 2), (10, 2), (11, 6), (12, 6), (13, 6), (14, 6)),
    9: ((18, 2), (19, 2), (20, 2), (21, 2), (22, 2), (23, 2), (24, 2)),
}
# Sensor-bind kind 1 (the SHT4x serial, command 0x89) is required exactly for the module types whose part
# has a readable sensor serial: type 1 in v1 (section 6.9, check 6). On any other type it is MALFORMED.
SENSOR_SERIAL_TYPES = frozenset({1})

VECTORS = Path(__file__).resolve().parent/'ws_div_round_vectors.csv'


def crc32c(data):
    """CRC-32C (Castagnoli): reflected polynomial 0x82F63B78, init and final XOR 0xFFFFFFFF."""
    crc = 0xFFFF_FFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F6_3B78 if crc & 1 else 0)
    return crc ^ 0xFFFF_FFFF


def seal(record):
    """The record with its CRC-32C over bytes 0x00-0x7B written big-endian at 0x7C."""
    b = bytearray(record)
    b[CRC_AT:] = crc32c(b[:CRC_AT]).to_bytes(4, 'big')
    return bytes(b)


def entry(quantity, kind, revision, offset, gain):
    """One 16-byte calibration entry."""
    return (quantity.to_bytes(2, 'big') + bytes([kind, 0]) + revision.to_bytes(2, 'big') + bytes(2)
            + offset.to_bytes(4, 'big', signed=True) + gain.to_bytes(4, 'big'))


def record(module_type=1, serial=0x01_A1B2C3D4E5F607, bind_kind=1, bind_value=0x1234_5678, part=b'ADA-SHT45-M1',
           cal=(), minor=0, flags=0, hw=2, programmed=1_792_000_000, length=RECORD_LEN, major=1):
    """A sealed record. The defaults are a valid type-1 (SHT45) record with no calibration."""
    b = bytearray(RECORD_LEN)
    b[0:4] = MAGIC
    b[4], b[5] = major, minor
    b[6:8] = length.to_bytes(2, 'big')
    b[8:10] = module_type.to_bytes(2, 'big')
    b[10], b[11] = hw, flags
    b[12:20] = serial.to_bytes(8, 'big')
    b[20] = bind_kind
    b[24:28] = bind_value.to_bytes(4, 'big')
    b[28:32] = programmed.to_bytes(4, 'big')
    b[32:48] = part.ljust(16, b'\0')
    for i, e in enumerate(cal):
        b[0x40 + 16 * i:0x50 + 16 * i] = entry(*e)
    return seal(b)


def div_round(num, den):
    """ws_div_round: floor((2 num + den) / (2 den)) for den > 0, round half up."""
    assert den > 0
    return (2 * num + den) // (2 * den)


def vectors():
    """The golden (num, den, expected) rows that the C helper and this reference both must give."""
    with VECTORS.open(newline='') as f:
        return [(int(r['num']), int(r['den']), int(r['expected'])) for r in csv.DictReader(f)]


def apply(raw, offset, gain):
    """v' = ws_div_round(v x gain, 10^6) + offset."""
    return div_round(raw * gain, 1_000_000) + offset


def crop(quantity, value):
    """(value, good): always clamped to the physical range (wsmp_cal_crop); good within the margin,
    suspect beyond it."""
    _, _, _, lo, hi, below, above = CAL[quantity]
    return min(max(value, lo), hi), lo - below <= value <= hi + above


def sensor_serial(module_type, serial32):
    """Namespace 0x02: bits 55-40 the module type, bits 39-32 zero, bits 31-0 the sensor's serial."""
    return 0x02 << 56 | module_type << 40 | serial32


def port_serial(port, module_type):
    """Namespace 0x00, WSMP_LOCAL_SERIAL(port, type) of wsmp_local.h."""
    return 0x5753_0000_0000 | port << 8 | module_type


def bind_ok(module_type, kind, value):
    """Check 6's sensor-bind rules: a known kind, no value without a kind, kind 1 iff the type's part has a serial."""
    if kind not in (0, 1) or (kind == 0 and value != 0):
        return False
    return (kind == 1) == (module_type in SENSOR_SERIAL_TYPES)


def entry_ok(module_type, quantity, kind, revision, offset, gain):
    """Check 7 for one used entry, at any minor: a quantity in the table, a (quantity, kind) that matches a
    channel of the type (kind 0 matches every channel of the quantity), revision not 0 (it means
    uncorrected), the offset and gain within the table's bounds."""
    if quantity not in CAL or revision == 0:
        return False
    if not any(q == quantity and (kind == 0 or k == kind) for q, k in CHANNELS.get(module_type, ())):
        return False
    off, gmin, gmax = CAL[quantity][:3]
    return -off <= offset <= off and gmin <= gain <= gmax


def check7(module_type, entries):
    """APPLIED or CAL_REJECTED for the (quantity, kind, revision, offset, gain) entries; all-zero ones skipped."""
    used = [e for e in entries if any(e)]
    keys = [(q, k) for q, k, *_ in used]
    if len(set(keys)) != len(keys) or not all(entry_ok(module_type, *e) for e in used):
        return CAL_REJECTED
    return APPLIED
