"""The WSMP descriptor set, gateway side (docs/module-protocol.md section 11.1).

A station describes its modules in one descriptor set: an 8-byte header (generation, module count,
a reserved byte, the CRC-32C digest of everything after the header), then one 18-byte entry for
each module in increasing port order (port, module type, schema, channel count, serial,
``id_flags``, ``record_crc``), each followed by its 6-byte descriptors. The identity fields are the
sensor module ports design's (docs/firmware-current-design.md,
section 6.7, "The serial reaches the gateway"). The C twin is ``firmware/common/wsmp.c``
(``wsmp_pack_set``, ``wsmp_unpack_set``, ``wsmp_set_check``); ``tests/test_wsmp_set.py`` checks the
two against each other byte for byte.
"""
import struct
from dataclasses import dataclass

from . import wsmp_registry as reg

HEAD = struct.Struct('>HBBI')        # generation, module count, reserved, digest
ENTRY = struct.Struct('>BHBBQBI')    # port, type, schema, channels, serial, id_flags, record_crc
DESC = struct.Struct('>HBbBB')       # quantity, unit, scale, form (width - 1, signed, reserved), kind
MODULES_MAX = 8                       # WSMP-P8
CHANNELS_MAX = 24                     # WSMP-P8
MAX_LEN = HEAD.size + MODULES_MAX * ENTRY.size + CHANNELS_MAX * DESC.size   # 296, WSMP-E4
SCALE_MAX = 6
WIDTH_MAX = 4

# id_flags: the serial source in bits 0-1, the record status in bits 4-7 (bits 2-3 reserved).
SOURCES = ('port', 'record', 'sensor', 'adapter')
STATUSES = ('applied', 'READ', 'BLANK', 'NO_MAGIC', 'VERSION', 'MALFORMED', 'CRC', 'CAL_REJECTED',
            'SENSOR_CHANGED')
NO_RECORD = frozenset(STATUSES[1:7])   # the NO_RECORD reasons (section 6.9)


class SetError(ValueError):
    """A descriptor set that WSMP section 11.1 refuses. ``code`` is the C twin's WSMP_E* name."""

    def __init__(self, code, why):
        super().__init__(f'{code}: {why}')
        self.code = code


def crc32c(data):
    """CRC-32C (Castagnoli, reflected 0x82F63B78), as WSMP uses it."""
    crc = 0xFFFFFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = crc >> 1 ^ (0x82F63B78 if crc & 1 else 0)
    return crc ^ 0xFFFFFFFF


@dataclass(frozen=True)
class Descriptor:
    quantity: int
    unit: int
    scale: int
    width: int
    signed: bool
    kind: int


@dataclass(frozen=True)
class Module:
    port: int
    type: int
    schema: int
    serial: int
    id_flags: int
    record_crc: int
    descriptors: tuple

    @property
    def source(self):
        return SOURCES[self.id_flags & 0x03]

    @property
    def status(self):
        return STATUSES[self.id_flags >> 4]

    @property
    def no_record(self):
        return self.status in NO_RECORD

    @property
    def namespace(self):
        return self.serial >> 56


@dataclass(frozen=True)
class DescriptorSet:
    generation: int
    digest: int
    modules: tuple


def _desc(b):
    quantity, unit, scale, form, kind = DESC.unpack(b)
    if form & 0x0F:
        raise SetError('WSMP_ERESERVED', 'a reserved descriptor bit is set')
    return Descriptor(quantity, unit, scale, (form >> 5) + 1, bool(form & 0x10), kind)


def unpack(data):
    """The descriptor set in ``data``, or SetError with the first fault (the C twin's order)."""
    data = bytes(data)
    if not HEAD.size <= len(data) <= MAX_LEN:
        raise SetError('WSMP_ELEN', f'{len(data)} bytes')
    generation, count, reserved, digest = HEAD.unpack_from(data)
    if reserved:
        raise SetError('WSMP_ERESERVED', 'the header reserved byte is not 0')
    if count > MODULES_MAX:
        raise SetError('WSMP_ELEN', f'{count} modules')
    at, total, modules = HEAD.size, 0, []
    for _ in range(count):
        if len(data) - at < ENTRY.size:
            raise SetError('WSMP_ELEN', 'an entry runs past the end')
        port, mtype, schema, channels, serial, id_flags, record_crc = ENTRY.unpack_from(data, at)
        at += ENTRY.size
        if not 1 <= channels <= 8 or serial == 0:
            raise SetError('WSMP_ELEN', f'port {port}: {channels} channels, serial {serial:#x}')
        total += channels
        if total > CHANNELS_MAX:
            raise SetError('WSMP_ELEN', f'{total} channels')
        if id_flags & 0x0C or id_flags >> 4 >= len(STATUSES):
            raise SetError('WSMP_ERESERVED', f'port {port}: id_flags {id_flags:#04x}')
        if len(data) - at < channels * DESC.size:
            raise SetError('WSMP_ELEN', 'descriptors run past the end')
        descs = tuple(_desc(data[at + i * DESC.size:at + (i + 1) * DESC.size]) for i in range(channels))
        at += channels * DESC.size
        if modules and port <= modules[-1].port:
            raise SetError('WSMP_ETYPE', f'port {port} after port {modules[-1].port}')
        modules.append(Module(port, mtype, schema, serial, id_flags, record_crc, descs))
    if at != len(data):
        raise SetError('WSMP_ELEN', f'{len(data) - at} bytes after the last entry')
    if crc32c(data[HEAD.size:]) != digest:
        raise SetError('WSMP_EDIGEST', 'the digest does not match')
    return DescriptorSet(generation, digest, tuple(modules))


def pack(generation, modules):
    """The bytes of a set (the simulator's and the tests'); modules in increasing port order."""
    body = b''
    for m in modules:
        body += ENTRY.pack(m.port, m.type, m.schema, len(m.descriptors), m.serial, m.id_flags, m.record_crc)
        for d in m.descriptors:
            body += DESC.pack(d.quantity, d.unit, d.scale, (d.width - 1) << 5 | int(d.signed) << 4, d.kind)
    return HEAD.pack(generation, len(modules), 0, crc32c(body)) + body


def check(s):
    """WSMP-E7: every module against the registry (WSMP-D7); its serial's namespace is its source; no
    module type twice (v1). Returns None or the first fault as text (the C twin's order)."""
    for m in s.modules:
        for d in m.descriptors:
            q = reg.QUANTITIES.get(d.quantity)
            if q is None or not 1 <= d.kind <= max(reg.KINDS):
                return f'port {m.port}: unknown quantity {d.quantity} or kind {d.kind}'
            if d.unit != q['unit']:
                return f'port {m.port}: unit {d.unit} is not the unit of quantity {d.quantity}'
            if not -SCALE_MAX <= d.scale <= SCALE_MAX or not 1 <= d.width <= WIDTH_MAX:
                return f'port {m.port}: scale {d.scale} or width {d.width} out of range'
        t = reg.MODULE_TYPES.get(m.type)
        if t is None or t['schema'] != m.schema:
            return f'port {m.port}: unknown module type {m.type} schema {m.schema}'
        if [(d.quantity, d.kind) for d in m.descriptors] != list(t['channels']):
            return f'port {m.port}: channels differ from module type {m.type}'
        if m.namespace != m.id_flags & 0x03:          # the serial's top byte is its source (section 6.7)
            return f'port {m.port}: serial namespace {m.namespace:#04x} is not its source {m.source}'
    types = [m.type for m in s.modules]
    if len(types) != len(set(types)):                 # v1: one module per type (the design's proposed WSMP-P10)
        return f'module type twice in one set: {sorted(t for t in set(types) if types.count(t) > 1)}'
    return None
