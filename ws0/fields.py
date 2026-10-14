"""Draft-5 observation plaintext: field catalog v1, encoder and decoder.

docs/protocol-draft5-design.md section 5. The C twin is firmware/common/ws_obs.{c,h};
tests/test_obs.py checks that both produce and accept the same bytes.
"""
import struct
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal

HEAD = struct.Struct('>IIIIBBI')       # epoch, sequence, UTC, uptime, flags, calibration, bitmap
HEAD_LEN = HEAD.size                   # 22
ENERGY = ('surplus', 'normal', 'conserve', 'critical')   # the firmware's energy_t numbering
WIND_DIR_CALM = 0xFFFE
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

    @property
    def invalid(self):
        return None if self.name == 'qualifiers' else (1 << (8 * self.width)) - 1

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
        if self.name in ('humidity_pct', 'enclosure_rh_pct', 'humidity_min_pct', 'humidity_max_pct'):
            value = min(max(value, 0), 100)
        # Round half up = floor(x + 0.5), exact on the value as written (Decimal(str(x))): in binary
        # floating point -40.005 * 100 is -4000.5000000001 and would round the wrong way. (Decimal's
        # ROUND_HALF_UP rounds halves away from zero, which is not what section 5.3 means.)
        x = Decimal(str(value)) * self.scale + Decimal('0.5')
        n = int(x.to_integral_value(ROUND_FLOOR)) + self.offset
        if self.name == 'wind_dir_deg':
            n %= 360
        return n if 0 <= n <= self.max else self.invalid


T, RH = dict(scale=100, offset=4000, unit='°C', ha_class='temperature'), dict(scale=100, unit='%', ha_class='humidity')
FIELDS = (
    Field(0, 'temperature_c', 2, 16500, **T),
    Field(1, 'humidity_pct', 2, 10000, **RH),
    Field(2, 'pressure_hpa', 2, 8000, scale=10, offset=-3000, unit='hPa', ha_class='atmospheric_pressure'),
    Field(3, 'wind_speed_ms', 2, 750, scale=10, unit='m/s', ha_class='wind_speed'),
    Field(4, 'wind_gust_ms', 2, 750, scale=10, unit='m/s', ha_class='wind_speed'),
    Field(5, 'wind_dir_deg', 2, 359, unit='°'),
    Field(6, 'rain_tips', 3, 16777214, counter=True),
    Field(7, 'uv_index', 1, 250, scale=10),
    Field(8, 'irradiance_wm2', 2, 2000, unit='W/m²', ha_class='irradiance'),
    Field(9, 'uva_raw', 3, 1048575),
    Field(10, 'qualifiers', 4, 0xFFFFFFFF),
    Field(11, 'batt_mv', 2, 65534, unit='mV', ha_class='voltage'),
    Field(12, 'batt_current_ma', 2, 65534, scale=10, offset=32768, unit='mA', ha_class='current'),
    Field(13, 'energy_in_mwh', 3, 16777214, unit='mWh', ha_class='energy', counter=True),
    Field(14, 'energy_out_mwh', 3, 16777214, unit='mWh', ha_class='energy', counter=True),
    Field(15, 'charge_in_mah', 3, 16777214, unit='mAh', counter=True),
    Field(16, 'charge_out_mah', 3, 16777214, unit='mAh', counter=True),
    Field(17, 'soc_gauge_pct', 1, 100, unit='%', ha_class='battery'),
    Field(18, 'charger_pins', 1, 3),
    Field(19, 'enclosure_temp_c', 2, 16500, **T),
    Field(20, 'enclosure_rh_pct', 2, 10000, **RH),
    # 15-s sampling summary of the minute (PRD section 9: coverage and extrema). temperature_c and
    # humidity_pct are then the mean of th_samples valid samples; all five are INVALID together.
    Field(21, 'temperature_min_c', 2, 16500, **T),
    Field(22, 'temperature_max_c', 2, 16500, **T),
    Field(23, 'humidity_min_pct', 2, 10000, **RH),
    Field(24, 'humidity_max_pct', 2, 10000, **RH),
    Field(25, 'th_samples', 1, 60, meta=True),
)
DEFINED = (1 << len(FIELDS)) - 1
BY_NAME = {f.name: f for f in FIELDS}
assert all(f.index == i for i, f in enumerate(FIELDS))


def fields_len(bitmap):
    return sum(f.width for f in FIELDS if bitmap >> f.index & 1)


def encode(epoch, seq, utc, uptime, energy, cal_rev, codes):
    """codes: {field index: code}. Raises ValueError for anything the decoder would reject."""
    bitmap = sum(1 << i for i in codes)
    if not codes or bitmap & ~DEFINED or not 0 <= energy <= 3:
        raise ValueError('Invalid field set or energy state')
    body = b''
    for f in FIELDS:
        if f.index in codes:
            if not f.code_ok(codes[f.index]):
                raise ValueError(f'{f.name}: code {codes[f.index]} out of range')
            body += codes[f.index].to_bytes(f.width, 'big')
    _check_wind(codes)
    return HEAD.pack(epoch, seq, utc, uptime, int(utc != 0) | energy << 1, cal_rev, bitmap) + body


def _check_wind(codes):
    speed, direction = codes.get(3), codes.get(5)
    if speed == FIELDS[3].invalid and direction is not None and direction != FIELDS[5].invalid:
        raise ValueError('Wind direction without a valid speed')


def decode(plain):
    """Canonical decode (section 5.4, the rules that need only this record). Returns
    (header dict, {field index: code}); raises ValueError for a non-canonical plaintext."""
    if len(plain) < HEAD_LEN:
        raise ValueError('Observation too short')
    epoch, seq, utc, uptime, flags, cal_rev, bitmap = HEAD.unpack_from(plain)
    if flags & 0xF8 or bitmap & ~DEFINED or not bitmap:
        raise ValueError('Reserved flag or bitmap bits, or no fields')
    if (flags & 1) != (utc != 0):
        raise ValueError('Time-known flag does not match UTC')
    if len(plain) != HEAD_LEN + fields_len(bitmap):
        raise ValueError('Observation length does not match its field bitmap')
    codes, at = {}, HEAD_LEN
    for f in FIELDS:
        if bitmap >> f.index & 1:
            code = int.from_bytes(plain[at:at + f.width], 'big')
            if not f.code_ok(code):
                raise ValueError(f'{f.name}: code {code} out of range')
            codes[f.index] = code
            at += f.width
    _check_wind(codes)
    head = dict(epoch=epoch, sequence=seq, utc=utc, uptime=uptime, energy_state=ENERGY[flags >> 1 & 3],
                calibration_revision=cal_rev, time_known=bool(flags & 1))
    return head, codes


def values(codes):
    """{field index: code} -> JSON-ready {name: value}. INVALID -> None; CALM -> None plus wind_calm."""
    out = {}
    for i, code in codes.items():
        f = FIELDS[i]
        if f.name == 'qualifiers':
            out['qualifiers'] = {FIELDS[k].name: QUALIFIER[code >> 2 * k & 3]
                                 for k in range(16) if code >> 2 * k & 3}
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
            names = {g.name: g.index for g in FIELDS[:16]}
            codes[f.index] = sum(QUALIFIER.index(q) << 2 * names[n] for n, q in v.items())
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
    import math
    if temperature_c is None or humidity_pct is None or humidity_pct <= 0:
        return None
    a, b = 17.62, 243.12
    gamma = math.log(humidity_pct / 100) + a * temperature_c / (b + temperature_c)
    return round(b * gamma / (a - gamma), 2)


def derived(record):
    """Values computed from a record's measurements, labelled as derived (PRD R10: every value has a
    unit and validity; derived values are marked as such)."""
    out = {}
    if 'temperature_c' in record and 'humidity_pct' in record:
        out['dew_point_c'] = dew_point(record['temperature_c'], record['humidity_pct'])
    return out
