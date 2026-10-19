#!/usr/bin/env python3
"""Generate the WSMP registry (docs/module-protocol.md section 4) for C and Python.

    tools/wsmp_registry.py           write firmware/common/wsmp_registry.h and ws0/wsmp_registry.py,
                                     and add new codes to tools/wsmp_registry.lock
    tools/wsmp_registry.py --check   exit 1 if a generated file is stale or a locked code changed

The source is firmware/common/wsmp_registry.toml. Codes are append-only (WSMP-G1): the lock file
names every code once given, and a code that disappears or changes its name stops the build.
"""
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
PREFIX = {'quantity': 'Q', 'unit': 'U', 'kind': 'K', 'module_type': 'T'}
REPORT_CLASSES = ('minute', 'health')
BANNER = 'GENERATED from firmware/common/wsmp_registry.toml by tools/wsmp_registry.py. Do not edit.'
MAX_CHANNELS = 8


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
                entries[(table, int(code))] = name
    return entries


def lock_text(reg, old):
    entries = dict(old)
    for table in TABLES:
        for row in reg[table]:
            entries.setdefault((table, row['code']), row['name'])
    lines = ['# WSMP codes once given (WSMP-G1, append-only). tools/wsmp_registry.py adds new ones.']
    lines += [f'{t} {c} {n}' for (t, c), n in sorted(entries.items(), key=lambda e: (TABLES.index(e[0][0]), e[0][1]))]
    return '\n'.join(lines) + '\n'


def lock_violations(reg, old):
    now = {(table, row['code']): row['name'] for table in TABLES for row in reg[table]}
    return [f'{t} {c} "{n}" was removed or renamed (codes are append-only, WSMP-G1)'
            for (t, c), n in old.items() if now.get((t, c)) != n]


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
    out += ['}', '',
            'uint8_t wsmp_canonical_unit(uint16_t quantity);       /* 0 for an unknown quantity */',
            'const wsmp_type_entry *wsmp_type(uint16_t type);      /* NULL for an unknown type */', '', '#endif', '']
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
            f'KINDS = {fmt(k)}\n\nMODULE_TYPES = {fmt(t)}\n')


def check_channels(reg):
    quantities = {row['code'] for row in reg['quantity']}
    kinds = {row['code'] for row in reg['kind']}
    for row in reg['module_type']:
        if not 1 <= len(row['channels']) <= MAX_CHANNELS or row['report_class'] not in REPORT_CLASSES:
            sys.exit(f'wsmp_registry: module type {row["code"]}: 1-{MAX_CHANNELS} channels and a known report class')
        for quantity, kind in row['channels']:
            if quantity not in quantities or kind not in kinds:
                sys.exit(f'wsmp_registry: module type {row["code"]} names an unknown quantity or kind')


def main(argv):
    check = argv[1:] == ['--check']
    reg = load()
    check_channels(reg)
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
