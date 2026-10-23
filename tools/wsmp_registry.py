#!/usr/bin/env python3
"""Generate the WSMP registry (docs/module-protocol.md section 4) for C and Python.

    tools/wsmp_registry.py           write firmware/common/wsmp_registry.h and ws0/wsmp_registry.py,
                                     and add new codes to tools/wsmp_registry.lock
    tools/wsmp_registry.py --check   exit 1 if a generated file is stale or a locked code changed

The source is firmware/common/wsmp_registry.toml. Codes are append-only (WSMP-G1): the lock file
names every code once given, and pins its meaning: each quantity's unit, and each module type's
channels for each schema. A code that disappears, changes its name or unit, or changes the channels
of a schema it already has stops the build. A new schema may bring new channels.
"""
import argparse
import pprint
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'firmware' / 'common' / 'wsmp_registry.toml'
HEADER = ROOT / 'firmware' / 'common' / 'wsmp_registry.h'
PYTHON = ROOT / 'ws0' / 'wsmp_registry.py'
LOCK = ROOT / 'tools' / 'wsmp_registry.lock'
TABLES = ('quantity', 'unit', 'kind', 'module_type')
MEANING = ('quantity_unit', 'type_schema')   # lock-only tables: what a code means, beside its name
UNIT_CODE_MAX = 255                          # wsmp_unit_of and the descriptor's unit are one byte
PREFIX = {'quantity': 'Q', 'unit': 'U', 'kind': 'K', 'module_type': 'T'}
REPORT_CLASSES = ('minute', 'health')
BANNER = 'GENERATED from firmware/common/wsmp_registry.toml by tools/wsmp_registry.py. Do not edit.'
MAX_CHANNELS = 8
INT32 = (-2**31, 2**31 - 1)                   # wsmp_cal_limits holds the calibration bounds as int32


def load():
    reg = tomllib.loads(SOURCE.read_text())
    for table in TABLES:
        codes = [row['code'] for row in reg[table]]
        if len(set(codes)) != len(codes) or 0 in codes:
            sys.exit(f'wsmp_registry: {table} codes must be unique and non-zero')
    return reg


def lock_entries():
    entries = {}
    if LOCK.exists():
        for line in LOCK.read_text().splitlines():
            if line.strip() and not line.startswith('#'):
                table, code, name = line.split(None, 2)
                entries[(table, code if table == 'type_schema' else int(code))] = name
    return entries


def channels_text(row):
    return ' '.join(f'{q}/{k}' for q, k in row['channels'])


def current(reg):
    """Every lock entry the registry gives now: the names, then the meanings."""
    now = {(table, row['code']): row['name'] for table in TABLES for row in reg[table]}
    now.update({('quantity_unit', row['code']): str(row['unit']) for row in reg['quantity']})
    now.update({('type_schema', f'{row["code"]}.{row["schema"]}'): channels_text(row) for row in reg['module_type']})
    return now


def lock_order(entry):
    (table, code), _ = entry
    return ((TABLES + MEANING).index(table), tuple(map(int, str(code).split('.'))))


def lock_text(reg, old):
    entries = dict(old)
    for key, value in current(reg).items():
        entries.setdefault(key, value)
    lines = ['# WSMP codes once given (WSMP-G1, append-only), with their meaning: quantity_unit <quantity> <unit>',
             '# and type_schema <type>.<schema> <quantity>/<kind> per channel. tools/wsmp_registry.py adds new ones.']
    lines += [f'{t} {c} {n}' for (t, c), n in sorted(entries.items(), key=lock_order)]
    return '\n'.join(lines) + '\n'


def lock_violations(reg, old):
    """Locked entries the registry broke. A type's old schema may be gone: a new one replaced it."""
    now = current(reg)
    return [f'{t} {c} "{n}" was removed or changed (codes are append-only, WSMP-G1)'
            for (t, c), n in old.items() if now.get((t, c), None if t != 'type_schema' else n) != n]


def calibration(reg):
    """The calibration table (record major 1) with each quantity's physical range at the row's scale."""
    ranges = {row['code']: row['range'] for row in reg['quantity']}
    out = {}
    for row in reg.get('calibration', []):
        factor = 10 ** -row['scale']
        lo, hi = (v * factor for v in ranges[row['quantity']])
        out[row['quantity']] = {'scale': row['scale'], 'offset_bound': row['offset_bound'], 'gain_min': row['gain'][0],
                                'gain_max': row['gain'][1], 'range_min': lo, 'range_max': hi,
                                'margin_below': row['margin'][0], 'margin_above': row['margin'][1]}
    return out


def c_cal_entry(quantity, c):
    return (f'  {{ {quantity}, {c["scale"]}, {c["offset_bound"]}, {c["gain_min"]}UL, {c["gain_max"]}UL, '
            f'{c["range_min"]}, {c["range_max"]}, {c["margin_below"]}, {c["margin_above"]} }},')


def c_type_entry(row):
    chans = ', '.join(f'{{ {q}, {k} }}' for q, k in row['channels'])
    rc = f'WSMP_RC_{row["report_class"].upper()}'
    return f'  {{ {row["code"]}, {row["schema"]}, {len(row["channels"])}, {rc}, {{ {chans} }} }},'


def header_text(reg):
    out = [f'/* {BANNER} */', '#ifndef WSMP_REGISTRY_H', '#define WSMP_REGISTRY_H', '#include <stddef.h>',
           '#include <stdint.h>', '', f'#define WSMP_REGISTRY_VERSION {reg["version"]}', '']
    for table in TABLES:
        out += [f'#define WSMP_{PREFIX[table]}_{row["id"]} {row["code"]}' for row in reg[table]]
        out.append('')
    out += ['#define WSMP_RC_MINUTE 0', '#define WSMP_RC_HEALTH 1',
            f'#define WSMP_KIND_MAX {max(row["code"] for row in reg["kind"])}U', '']
    for row in reg['module_type']:
        for key, value in row.get('factors', {}).items():
            out.append(f'#define WSMP_{row["id"]}_{key.upper()} {value}UL')
        for i, state in enumerate(row.get('states', [])):
            out.append(f'#define WSMP_{row["id"]}_STATE_{state.upper()} {i}')
    top = max(row['code'] for row in reg['quantity'])
    units = [0] * (top + 1)
    for row in reg['quantity']:
        units[row['code']] = row['unit']
    out += ['', 'typedef struct { uint16_t quantity; uint8_t kind; } wsmp_type_ch;',
            'typedef struct { uint16_t type; uint8_t schema, channels, report_class; '
            f'wsmp_type_ch ch[{MAX_CHANNELS}]; }} wsmp_type_entry;', '',
            '/* The tables are initializers only: firmware/common/wsmp.c holds the one copy of each. */',
            '/* The canonical unit of each quantity (WSMP-G3), indexed by the quantity code. */',
            f'#define WSMP_UNIT_OF_COUNT {top + 1}U',
            f'#define WSMP_UNIT_OF_INIT {{ {", ".join(map(str, units))} }}',
            f'#define WSMP_TYPE_COUNT {len(reg["module_type"])}U',
            '#define WSMP_TYPES_INIT { \\']
    out += [c_type_entry(row) + ' \\' for row in reg['module_type']]
    cal = calibration(reg)
    out += ['}', '',
            '/* The calibration table of module record major 1 (frozen; a later minor may only widen a bound):',
            '   integers at the channel scale, gains in ppm, the physical range and its crop margins. */',
            'typedef struct {',
            '  uint16_t quantity; int8_t scale; int32_t offset_bound; uint32_t gain_min, gain_max;',
            '  int32_t range_min, range_max, margin_below, margin_above;',
            '} wsmp_cal_limits;',
            f'#define WSMP_CAL_COUNT {len(cal)}U',
            '#define WSMP_CAL_INIT { \\']
    out += [c_cal_entry(q, c) + ' \\' for q, c in cal.items()]
    out += ['}', '',
            'uint8_t wsmp_canonical_unit(uint16_t quantity);       /* 0 for an unknown quantity */',
            'const wsmp_type_entry *wsmp_type(uint16_t type);      /* NULL for an unknown type */',
            'const wsmp_cal_limits *wsmp_cal_limits_of(uint16_t quantity);   /* NULL: no record calibration */',
            '', '#endif', '']
    return '\n'.join(out)


def python_text(reg):
    units = {row['code']: row for row in reg['unit']}
    q = {row['code']: {**{k: v for k, v in row.items() if k != 'code'}, 'ucum': units[row['unit']]['ucum']}
         for row in reg['quantity']}
    u = {row['code']: {k: v for k, v in row.items() if k != 'code'} for row in reg['unit']}
    k = {row['code']: {kk: v for kk, v in row.items() if kk != 'code'} for row in reg['kind']}
    t = {row['code']: {**{kk: v for kk, v in row.items() if kk not in ('code', 'channels')},
                       'channels': [tuple(c) for c in row['channels']], 'factors': row.get('factors', {})}
         for row in reg['module_type']}
    fmt = lambda v: pprint.pformat(v, width=110, sort_dicts=False)  # noqa: E731
    return (f'# {BANNER}\n"""The WSMP registry codes (docs/module-protocol.md section 4)."""\n\n'
            f'REGISTRY_VERSION = {reg["version"]}\n\nQUANTITIES = {fmt(q)}\n\nUNITS = {fmt(u)}\n\n'
            f'KINDS = {fmt(k)}\n\nMODULE_TYPES = {fmt(t)}\n\n'
            f'# Module record major 1 calibration (frozen): bounds and ranges at the channel scale.\n'
            f'CALIBRATION = {fmt(calibration(reg))}\n')


def check_codes(reg):
    """The ranges the generated C relies on: kinds 1..WSMP_KIND_MAX with no gap, one-byte units, and
    a known unit for each quantity."""
    kinds = {row['code'] for row in reg['kind']}
    if kinds != set(range(1, max(kinds) + 1)):
        sys.exit('wsmp_registry: kind codes must run from 1 with no gap (wsmp.c checks 1..WSMP_KIND_MAX)')
    units = {row['code'] for row in reg['unit']}
    if max(units) > UNIT_CODE_MAX:
        sys.exit(f'wsmp_registry: unit codes must be {UNIT_CODE_MAX} or less (one byte)')
    for row in reg['quantity']:
        if row['unit'] not in units:
            sys.exit(f'wsmp_registry: quantity {row["code"]} names an unknown unit {row["unit"]}')


def check_channels(reg):
    quantities = {row['code'] for row in reg['quantity']}
    kinds = {row['code'] for row in reg['kind']}
    for row in reg['module_type']:
        if not 1 <= len(row['channels']) <= MAX_CHANNELS or row['report_class'] not in REPORT_CLASSES:
            sys.exit(f'wsmp_registry: module type {row["code"]}: 1-{MAX_CHANNELS} channels and a known report class')
        for quantity, kind in row['channels']:
            if quantity not in quantities or kind not in kinds:
                sys.exit(f'wsmp_registry: module type {row["code"]} names an unknown quantity or kind')


def check_calibration(reg):
    """Each calibration row: a known quantity once, a scale of -6 to 0 (the range converts exactly),
    non-negative bounds and margins, 0 < gain min <= gain max, and every value fits int32."""
    quantities = {row['code'] for row in reg['quantity']}
    seen = set()
    for row in reg.get('calibration', []):
        q = row['quantity']
        if q not in quantities or q in seen or not -6 <= row['scale'] <= 0:
            sys.exit(f'wsmp_registry: calibration of quantity {q}: a known quantity, once, with a scale of -6 to 0')
        seen.add(q)
        c = calibration(reg)[q]
        if not (0 < c['gain_min'] <= c['gain_max'] < 2**32 and c['offset_bound'] >= 0 and min(row['margin']) >= 0):
            sys.exit(f'wsmp_registry: calibration of quantity {q}: bounds out of order or negative')
        if not all(INT32[0] <= c[k] <= INT32[1] for k in ('offset_bound', 'range_min', 'range_max', 'margin_below', 'margin_above')):
            sys.exit(f'wsmp_registry: calibration of quantity {q}: a value does not fit int32')


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--check', action='store_true', help='exit 1 if a generated file is stale or a locked code changed')
    check = ap.parse_args(argv[1:]).check
    reg = load()
    check_codes(reg)
    check_channels(reg)
    check_calibration(reg)
    old = lock_entries()
    bad = lock_violations(reg, old)
    if bad:
        print('\n'.join(bad), file=sys.stderr)
        return 1
    wanted = {HEADER: header_text(reg), PYTHON: python_text(reg), LOCK: lock_text(reg, old)}
    stale = [p for p, text in wanted.items() if not p.exists() or p.read_text() != text]
    if check:
        for p in stale:
            print(f'wsmp_registry: {p.relative_to(ROOT)} is stale: run tools/wsmp_registry.py', file=sys.stderr)
        if not stale:
            print('wsmp_registry: OK')
        return 1 if stale else 0
    for p in stale:
        p.write_text(wanted[p])
        print(f'wsmp_registry: wrote {p.relative_to(ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
