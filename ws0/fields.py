"""Observation plaintext: field catalog v2, encoder and decoder.

docs/protocol-design.md section 5 and docs/superpowers/specs/2026-10-29-power-telemetry-design.md
section 5. The C twin is firmware/common/ws_obs.{c,h}; tests/test_obs.py checks that both produce
and accept the same bytes. Bitmap bit 31 (EXT) is not a field: it announces a u16 extension bitmap
after the header whose bit j is field 32 + j.
"""
import math
import struct
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal

HEAD = struct.Struct('>IIIIBBI')       # epoch, sequence, UTC, uptime, flags, calibration, bitmap
HEAD_LEN = HEAD.size                   # 22
EXT_WORD = struct.Struct('>H')         # extension bitmap, present only when bit 31 (EXT) is set
EXT, EXT_SHIFT, INDEX_LIMIT = 31, 32, 48   # EXT bit; extension bit j = field 32 + j; fields 0-47
BASE_FIELDS = (1 << EXT) - 1           # fields 0-30: the wire bitmap's own bits
CURRENT_OFFSET = 32768                 # currents: 1 mA, offset binary, -32768..+32766 mA
ENERGY = ('surplus', 'normal', 'conserve', 'critical')   # the firmware's energy_t numbering
WIND_DIR_CALM = 0xFFFE
FLAG_UTC, ENERGY_SHIFT, ENERGY_MASK, FLAGS_RESERVED = 0x01, 1, 0x03, 0xF8   # flags: bit 0 UTC known, bits 1-2 energy
TEMP_MIN_CENTI, TEMP_MAX_CENTI, RH_MAX_CENTI = -4000, 12500, 10000         # SHT45: -40.00..125.00 C, 0..100.00 %
TEMP_CODE_TOP = TEMP_MAX_CENTI - TEMP_MIN_CENTI                             # code = centi C + 40.00 C
TH_SAMPLES_MAX = 60                                                          # 15-s samples in a minute's window
QUALIFIER_BITS, QUALIFIABLE_COUNT = 2, 16                                   # qualifiers: 2 bits for each of fields 0-15
DEGREES = 360


def code_top(width):
    """The highest in-range code of a field whose all-ones value is INVALID."""
    return 2**(8 * width) - 2
QUALIFIER = (None, 'suspected_icing', 'delayed_melt', 'outside_envelope')


@dataclass(frozen=True)
class Field:
    index: int
    name: str
    width: int          # bytes
    max: int            # highest in-range code
    scale: int = 1      # code units per unit
    offset: int = 0     # code of value 0, in code units (value = (code - offset) / scale)
    unit: str = ''
    ha_class: str = ''  # Home Assistant device_class
    counter: bool = False  # since-boot counter: non-decreasing in sequence order within an epoch
    meta: bool = False     # describes the other values (sample count); not counted in quality
    clamp: bool = False    # relative humidity: readings just outside 0..100 are clamped, not INVALID

    @property
    def invalid(self):
        return None if self.name == 'qualifiers' else 2**(8 * self.width) - 1

    def code_ok(self, code):
        if 0 <= code <= self.max:
            return True
        return code in (self.invalid, WIND_DIR_CALM if self.name == 'wind_dir_deg' else None)

    def value(self, code):
        """Exact decode: no float noise (code - offset is an integer before the one division)."""
        n = code - self.offset
        return n if self.scale == 1 else n / self.scale

    def code(self, value):
        """Physical value -> code: round half up; out of range -> INVALID (RH fields clamp)."""
        if value is None:
            return self.invalid
        if self.clamp:
            value = min(max(value, 0), RH_MAX_CENTI / self.scale)
        # Round half up = floor(x + 0.5), exact on the value as written (Decimal(str(x))): in binary
        # floating point -40.005 * 100 is -4000.5000000001 and would round the wrong way. (Decimal's
        # ROUND_HALF_UP rounds halves away from zero, which is not what section 5.3 means.)
        x = Decimal(str(value)) * self.scale + Decimal('0.5')
        n = int(x.to_integral_value(ROUND_FLOOR)) + self.offset
        if self.name == 'wind_dir_deg':
            n %= DEGREES
        return n if 0 <= n <= self.max else self.invalid


T, RH = dict(scale=100, offset=-TEMP_MIN_CENTI, unit='°C', ha_class='temperature'), dict(scale=100, unit='%', ha_class='humidity', clamp=True)
MV, MA = dict(unit='mV', ha_class='voltage'), dict(offset=CURRENT_OFFSET, unit='mA', ha_class='current')
FIELDS = (
    Field(0, 'temperature_c', 2, TEMP_CODE_TOP, **T),
    Field(1, 'humidity_pct', 2, RH_MAX_CENTI, **RH),
    Field(2, 'pressure_hpa', 2, 8000, scale=10, offset=-3000, unit='hPa', ha_class='atmospheric_pressure'),
    Field(3, 'wind_speed_ms', 2, 750, scale=10, unit='m/s', ha_class='wind_speed'),
    Field(4, 'wind_gust_ms', 2, 750, scale=10, unit='m/s', ha_class='wind_speed'),
    Field(5, 'wind_dir_deg', 2, 359, unit='°'),
    Field(6, 'rain_tips', 3, code_top(3), counter=True),
    Field(7, 'uv_index', 1, 250, scale=10),
    Field(8, 'irradiance_wm2', 2, 2000, unit='W/m²', ha_class='irradiance'),
    Field(9, 'uva_raw', 3, 2**20 - 1),   # LTR390 counts (20 bit)
    Field(10, 'qualifiers', 4, 2**32 - 1),   # no INVALID
    # Battery: 11 is the cell terminal voltage; 12 the battery current, + into the cell (1 mA, offset
    # binary); 13-16 battery-terminal energy and charge since boot, split by that sign (13 and 14 are
    # INVALID in a minute where a step had no fresh battery voltage).
    Field(11, 'batt_mv', 2, code_top(2), **MV),
    Field(12, 'batt_current_ma', 2, code_top(2), **MA),
    Field(13, 'energy_in_mwh', 3, code_top(3), unit='mWh', ha_class='energy', counter=True),
    Field(14, 'energy_out_mwh', 3, code_top(3), unit='mWh', ha_class='energy', counter=True),
    Field(15, 'charge_in_mah', 3, code_top(3), unit='mAh', counter=True),
    Field(16, 'charge_out_mah', 3, code_top(3), unit='mAh', counter=True),
    # Retired (version 6 builds do not send them; still decodable, never reused): the health report
    # carries SOC and the charger status.
    Field(17, 'soc_gauge_pct', 1, 100, unit='%', ha_class='battery'),
    Field(18, 'charger_pins', 1, 3),
    Field(19, 'enclosure_temp_c', 2, TEMP_CODE_TOP, **T),
    Field(20, 'enclosure_rh_pct', 2, RH_MAX_CENTI, **RH),
    # 15-s sampling summary of the minute: coverage and extrema (product spec, sampling section).
    # temperature_c and humidity_pct are then the mean of th_samples valid samples. All five are
    # INVALID together.
    Field(21, 'temperature_min_c', 2, TEMP_CODE_TOP, **T),
    Field(22, 'temperature_max_c', 2, TEMP_CODE_TOP, **T),
    Field(23, 'humidity_min_pct', 2, RH_MAX_CENTI, **RH),
    Field(24, 'humidity_max_pct', 2, RH_MAX_CENTI, **RH),
    Field(25, 'th_samples', 1, TH_SAMPLES_MAX, meta=True),
    # Power rails (catalog v2). Voltages 1 mV; currents 1 mA offset binary, + into the load or station.
    Field(26, 'load_mv', 2, code_top(2), **MV),
    Field(27, 'load_current_ma', 2, code_top(2), **MA),
    Field(28, 'charger_input_mv', 2, code_top(2), **MV),   # after the sources join: source not identified
    Field(29, 'solar_mv', 2, code_top(2), **MV),
    Field(30, 'solar_current_ma', 2, code_top(2), **MA),
    # 31 is EXT, not a field. 32-47 travel in the extension bitmap; 34-47 are reserved.
    Field(32, 'usb_mv', 2, code_top(2), **MV),
    Field(33, 'usb_current_ma', 2, code_top(2), **MA),
)
DEFINED = sum(1 << f.index for f in FIELDS)
BY_NAME = {f.name: f for f in FIELDS}
BY_INDEX = {f.index: f for f in FIELDS}
_indexes = [f.index for f in FIELDS]
if (_indexes != sorted(set(_indexes)) or EXT in BY_INDEX           # checks that survive python -O
        or not all(0 <= i < INDEX_LIMIT for i in _indexes)):
    raise ImportError('field catalog indexes must increase strictly, skip 31 (EXT) and stay below 48')


def fields_len(mask):
    """Bytes after the 22-byte header for logical field mask: the extension word when any field
    32-47 is present, then the fields."""
    return (EXT_WORD.size if mask >> EXT_SHIFT else 0) + sum(f.width for f in FIELDS if mask >> f.index & 1)


def plain_len(mask):
    return HEAD_LEN + fields_len(mask)


def encode(epoch, seq, utc, uptime, energy, cal_rev, codes):
    """codes: {field index: code}. Raises ValueError for anything the decoder would reject."""
    mask = sum(1 << i for i in codes)
    if not codes or any(i < 0 for i in codes) or mask & ~DEFINED or not 0 <= energy < len(ENERGY):
        raise ValueError('Invalid field set or energy state')
    body = b''
    for f in FIELDS:
        if f.index in codes:
            if not f.code_ok(codes[f.index]):
                raise ValueError(f'{f.name}: code {codes[f.index]} out of range')
            body += codes[f.index].to_bytes(f.width, 'big')
    _check_wind(codes)
    ext = mask >> EXT_SHIFT
    head = HEAD.pack(epoch, seq, utc, uptime, (FLAG_UTC if utc else 0) | energy << ENERGY_SHIFT, cal_rev,
                     mask & BASE_FIELDS | (1 << EXT if ext else 0))
    return head + (EXT_WORD.pack(ext) if ext else b'') + body


def _check_wind(codes):
    s, d = BY_NAME['wind_speed_ms'], BY_NAME['wind_dir_deg']
    speed, direction = codes.get(s.index), codes.get(d.index)
    if speed == s.invalid and direction is not None and direction != d.invalid:
        raise ValueError('Wind direction without a valid speed')


def decode(plain):
    """Canonical decode (section 5.4, the rules that need only this record). Returns
    (header dict, {field index: code}); raises ValueError for a non-canonical plaintext."""
    if len(plain) < HEAD_LEN:
        raise ValueError('Observation too short')
    epoch, seq, utc, uptime, flags, cal_rev, bitmap = HEAD.unpack_from(plain)
    mask = _mask(plain, bitmap)
    if flags & FLAGS_RESERVED or mask & ~DEFINED or not mask:
        raise ValueError('Reserved flag or bitmap bits, or no fields')
    if bool(flags & FLAG_UTC) != (utc != 0):
        raise ValueError('Time-known flag does not match UTC')
    if len(plain) != plain_len(mask):
        raise ValueError('Observation length does not match its field bitmap')
    codes, at = {}, HEAD_LEN + (EXT_WORD.size if mask >> EXT_SHIFT else 0)
    for f in FIELDS:
        if mask >> f.index & 1:
            code = int.from_bytes(plain[at:at + f.width], 'big')
            if not f.code_ok(code):
                raise ValueError(f'{f.name}: code {code} out of range')
            codes[f.index] = code
            at += f.width
    _check_wind(codes)
    head = dict(epoch=epoch, sequence=seq, utc=utc, uptime=uptime, energy_state=ENERGY[flags >> ENERGY_SHIFT & ENERGY_MASK],
                calibration_revision=cal_rev, time_known=bool(flags & FLAG_UTC))
    return head, codes


def _mask(plain, bitmap):
    """The logical field mask of a header: bits 0-30, plus the extension bitmap when EXT is set (an
    empty extension bitmap is not canonical)."""
    if not bitmap >> EXT & 1:
        return bitmap
    if len(plain) < HEAD_LEN + EXT_WORD.size:
        raise ValueError('Observation too short for its extension bitmap')
    ext = EXT_WORD.unpack_from(plain, HEAD_LEN)[0]
    if not ext:
        raise ValueError('Extension bitmap announced but empty')
    return bitmap & BASE_FIELDS | ext << EXT_SHIFT


# The qualifiers field holds QUALIFIER_BITS for each of the first QUALIFIABLE_COUNT catalog fields (design 5.3).
QUALIFIABLE = {BY_INDEX[i].name: i for i in range(QUALIFIABLE_COUNT)}
QUALIFIER_MASK = 2**QUALIFIER_BITS - 1


def values(codes):
    """{field index: code} -> JSON-ready {name: value}. INVALID -> None; CALM -> None plus wind_calm."""
    out = {}
    for i, code in codes.items():
        f = BY_INDEX[i]
        if f.name == 'qualifiers':
            out['qualifiers'] = {BY_INDEX[k].name: QUALIFIER[code >> QUALIFIER_BITS * k & QUALIFIER_MASK]
                                 for k in QUALIFIABLE.values() if code >> QUALIFIER_BITS * k & QUALIFIER_MASK}
        elif f.name == 'wind_dir_deg':
            out['wind_calm'] = code == WIND_DIR_CALM
            out[f.name] = None if code in (WIND_DIR_CALM, f.invalid) else code
        else:
            out[f.name] = None if code == f.invalid else f.value(code)
    return out


MEASURED = tuple(f.name for f in FIELDS if f.name != 'qualifiers')


def quality(record):
    """valid: every present measurement valid (CALM counts); partial: some INVALID; sensor_fault: all."""
    present = [record[name] is not None or (name == 'wind_dir_deg' and record.get('wind_calm'))
               for name in MEASURED if name in record and not BY_NAME[name].meta]
    if not present:
        raise ValueError('No measurements')
    return 'valid' if all(present) else 'sensor_fault' if not any(present) else 'partial'


def codes_from_record(record):
    """Inverse of values(): {field index: code} for the catalog fields present in a record."""
    codes = {}
    for f in FIELDS:
        if f.name not in record:
            continue
        v = record[f.name]
        if f.name == 'qualifiers':
            codes[f.index] = sum(QUALIFIER.index(q) << QUALIFIER_BITS * QUALIFIABLE[n] for n, q in v.items())
        elif f.name == 'wind_dir_deg' and record.get('wind_calm'):
            codes[f.index] = WIND_DIR_CALM
        else:
            codes[f.index] = f.code(v)
    return codes


def dew_point(temperature_c, humidity_pct):
    """Derived dew point in °C (Magnus formula, Sonntag 1990 constants over water: within about
    ±0.35 °C from −45 to +60 °C), rounded to 0.01. None when either input is missing or RH is 0
    (the logarithm is undefined; the air has no measurable water). Derived values are computed at
    publication and never stored in the immutable observation payload."""
    if temperature_c is None or humidity_pct is None or humidity_pct <= 0:
        return None
    a, b = 17.62, 243.12
    gamma = math.log(humidity_pct / 100) + a * temperature_c / (b + temperature_c)
    return round(b * gamma / (a - gamma), 2)


# Power and enclosure fields describe the station, not the weather: HA diagnostic entities.
DIAGNOSTIC_FIELDS = frozenset({'batt_mv','batt_current_ma','energy_in_mwh','energy_out_mwh','charge_in_mah',
                               'charge_out_mah','soc_gauge_pct','charger_pins','enclosure_temp_c',
                               'enclosure_rh_pct','uva_raw','th_samples','load_mv','load_current_ma',
                               'charger_input_mv','solar_mv','solar_current_ma','usb_mv','usb_current_ma'})


# Display names: Home Assistant entities and dashboard charts (the HA unique_id stays the field name,
# so renaming here is safe).
LABELS = {'temperature_c':'Temperature','humidity_pct':'Humidity','pressure_hpa':'Pressure',
          'wind_speed_ms':'Wind speed','wind_gust_ms':'Wind gust','wind_dir_deg':'Wind direction',
          'rain_tips':'Rain tips','uv_index':'UV index','irradiance_wm2':'Solar irradiance',
          'uva_raw':'UVA raw (not UV index)','batt_mv':'Battery voltage','batt_current_ma':'Battery current (+ charging)',
          'energy_in_mwh':'Energy in','energy_out_mwh':'Energy out','charge_in_mah':'Charge in',
          'charge_out_mah':'Charge out','soc_gauge_pct':'Battery (fuel gauge estimate)',
          'charger_pins':'Charger status pins','enclosure_temp_c':'Enclosure temperature',
          'enclosure_rh_pct':'Enclosure humidity','temperature_min_c':'Temperature minimum (minute)',
          'temperature_max_c':'Temperature maximum (minute)','humidity_min_pct':'Humidity minimum (minute)',
          'humidity_max_pct':'Humidity maximum (minute)','th_samples':'T/RH samples per minute',
          'load_mv':'Load voltage','load_current_ma':'Load current',
          'charger_input_mv':'Charger input voltage (source not identified)','solar_mv':'Solar input voltage',
          'solar_current_ma':'Solar input current','usb_mv':'USB-C input voltage','usb_current_ma':'USB-C input current',
          'dew_point_c':'Dew point (derived)'}
# Published with the weather but computed by the gateway, never sent by the node (fields.derived).
DERIVED = {'dew_point_c': dict(unit='°C', ha_class='temperature', needs=('temperature_c','humidity_pct'),
                              compute=dew_point)}


def derived(record):
    """Values computed from a record's measurements, labelled as derived. The product spec requires
    a unit and validity for every value, and derived values must be marked as such."""
    return {name: spec['compute'](*(record[n] for n in spec['needs']))
            for name, spec in DERIVED.items() if all(n in record for n in spec['needs'])}
