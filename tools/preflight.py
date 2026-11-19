#!/usr/bin/env python3
"""Check a run's preflight block (decision record D6, M5, P8, section 4.3) against the breadboard
model and the pass limits.

    .venv/bin/python tools/preflight.py NOTES.md [--model .../wiring.toml] [--sheet .../build-sheet.md]

Without --model and --sheet, the block's `revision` picks them: a frozen earlier revision (record 6.1,
hardware/bench-breadboard-r0/source/revisions/<revision>.toml) is checked against its own model and its
sheet (revisions/<revision>/build-sheet.md); any other revision against the current wiring.toml and
build-sheet.md.

The block is the first fenced block in NOTES.md whose info string is `toml preflight`:

    ```toml preflight
    model_hash = "<git blob sha1 of wiring.toml>"   # git hash-object, or checklist.blob_sha1
    sheet_hash = "<git blob sha1 of build-sheet.md>"
    revision = "bench-bb-r0.1"        # wiring.toml's `revision` when the readings were taken
    power_mode = "A"                  # "A" (the station on USB) or "B" (on the regulator)
    meter = "Fluke 87V, 600 mV DC range, high-resolution mode (0.01 mV)"   # checklist.METER
    date = 2026-10-30
    photo = "preflight-2026-10-30.jpg"
    wiggle = "pass"                   # C11/C18/C23 wiggle result: "pass" or "fail"
    rewire = false                    # true after a rewire: the 1 A rows C12-C14, C16-C18 are required
    step_exit = false                 # true at a step exit: the same
    deviations = []                   # free text, one string per deviation from the build sheet
    dv0_mv = 4.2                      # gauge VCELL - INA VBUS at zero current, for power_mode
                                      # (or a table: dv0_mv = { A = 4.2, B = 3.9 })
    r_pack_mohm = 41.0                # C14: PATH_PACK_POS + PATH_PACK_NEG (needed when both are read)

    [[reading]]
    check = "C12"                     # the section 4.3 row
    span = "PATH_POS"                 # a path segment (checklist.PATH_IDS), and/or
    # joint = "WAGO_CELL_POS"         # a model [[joint]] id, or lead = "L_PACK_POS", or link = "LK_..."
    mv = 52.0                         # the DMM reading (a step for C11/C18/C23: max - min)
    ma = 900.0                        # the INA228 current; the 1 A rows need 800-1000 mA
    # value = "open"                  # text or number where the row reads one (C1-C5, C16, C19, C23)
    # lever = "open"                  # C2 only: the lever-open half (value in ohm, at least 100)
    # unit = "mOhm"                   # optional; when given it must be the row's unit
    # contact = "ph"                  # C14 only: "ph", "clamp" or "screw" (a joint reads as a clamp,
                                      # a pack-side span as the 28 mOhm span)
    # signal = "VBUS"                 # C17 only: "VBUS", "CHG" or "PGOOD"
    ```

How a reading meets its row (checklist.CHECKS, `op`): mOhm = mv / (ma / 1000); mV rows read `mv`;
mA rows read `ma` (C5 and C16 compare `ma` with the reference current in `value`); C2 reads `value`
in ohm: under 0.5 with the TIE closed, and, with `lever = "open"`, at least checklist.C2_OPEN_MIN_OHM
(100 ohm; the honest reading is kOhm to about 1 MOhm: R_ISER, R_IPD and diode paths, record 4.3);
an OL reading (`value = "open"` with `unit = "open"`) fails that half, as record 4.3 never reads OL;
text rows read `value`.

Status (exit code), one line per problem first; the tool never blocks a run:
  valid (0)    every check passes.
  failing (1)  an unknown id (when the ids are checked), a reading outside its limit, a 1 A reading
               outside 800-1000 mA, R_pack not the sum of the two pack-side spans, wiggle not "pass",
               a bad or missing top key, or a required row missing: mode A needs C1-C11 and C19,
               mode B needs C15 and C20-C23, and rewire or step_exit adds C12-C14 and C16-C18 (C15
               is numbered in that range but is a mode-B row).
  missing (2)  no block, or it does not parse.
  stale (3)    a hash differs from the current model or sheet: the model changed since the run. Not
               failing: the readings are still held to their limits, and the ids are checked only
               when the block's revision equals the model's; otherwise each is reported "unchecked
               (revision differs)".
A failing block outranks a stale one. Missing and failing runs are logged as "wiring unverified".
"""
import argparse
import importlib.util
import math
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HW = ROOT/'hardware'/'bench-breadboard-r0'
MODEL = HW/'source'/'wiring.toml'
SHEET = HW/'build-sheet.md'
FROZEN = re.compile(r'bench-bb-r\d+\.\d+')   # the name of a frozen revision's model file, and nothing else


def _load_checklist():
    spec = importlib.util.spec_from_file_location('checklist', HW/'source'/'checklist.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checklist = _load_checklist()

INFO = 'toml preflight'
FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')
EXIT = {'valid': 0, 'failing': 1, 'missing': 2, 'stale': 3}
MESSAGE = {'valid': 'preflight: valid',
           'failing': 'preflight: failing; run marked wiring unverified',
           'missing': 'preflight: missing; run marked wiring unverified',
           'stale': 'preflight: stale; the model changed since the run'}
ID_KEYS = ('joint', 'lead', 'link')
R_PACK_TOLERANCE_MOHM = 0.1   # R_pack is written by hand from the two rounded spans
CONTACTS = ('ph', 'clamp', 'screw')
# Reading keys looked up by name: anything but a string is a failing line, never an exception.
TEXT_KEYS = ('check', 'span', *ID_KEYS, 'contact', 'signal', 'lever')


# ---- the block ----

def find_block(text):
    """The body of the first `toml preflight` fenced block, or None. Other fenced blocks are
    skipped whole, so a fence-like line inside them does not open one."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):                       # bound: i grows on every pass
        m = FENCE.match(lines[i])
        if not m or (m[1][0] == '`' and '`' in m[2]):
            i += 1
            continue
        end = _closing(lines, i + 1, m[1])
        if m[2].strip() == INFO:
            return None if end is None else '\n'.join(lines[i + 1:end])
        i = len(lines) if end is None else end + 1
    return None


def _closing(lines, start, opener):
    """The index of the line that closes a fence opened by `opener`, or None."""
    for j in range(start, len(lines)):
        m = FENCE.match(lines[j])
        if m and m[1][0] == opener[0] and len(m[1]) >= len(opener) and not m[2].strip():
            return j
    return None


def read_block(notes):
    """(the parsed block, None) or (None, why it is missing)."""
    try:
        body = find_block(Path(notes).read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError) as e:
        return None, f'notes: cannot read {notes}: {e}'
    if body is None:
        return None, f'notes: no closed ```{INFO} block'
    try:
        return tomllib.loads(body), None
    except tomllib.TOMLDecodeError as e:
        return None, f'block: does not parse: {e}'


# ---- the model ----

def model_ids(doc):
    """Every id a reading may name: [[joint]].id, [[lead]].id and [[link]].id."""
    return {item['id'] for kind in ID_KEYS for item in doc.get(kind, ()) if 'id' in item}


def _load_model(model):
    try:
        return tomllib.loads(Path(model).read_text(encoding='utf-8')), None
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        return None, f'model: cannot read {model}: {e}'


def _hash_lines(block, model, sheet):
    """The stale lines: each stated hash that differs from (or cannot be compared with) its file."""
    lines = []
    for key, path in (('model_hash', model), ('sheet_hash', sheet)):
        try:
            now = checklist.blob_sha1(path)
        except OSError as e:
            lines.append(f'{key}: cannot hash {path}: {e}')
            continue
        if block.get(key) != now:
            lines.append(f'{key}: {block.get(key)} differs from {Path(path).name} ({now}): '
                         'the model or sheet changed since the run')
    return lines


# ---- top keys ----

def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _dv0(block):
    """dv0_mv by power mode: a number is the block's own mode, a table gives modes by name."""
    raw = block.get('dv0_mv')
    if _num(raw):
        return {block.get('power_mode'): float(raw)}
    if isinstance(raw, dict) and raw and all(k in ('A', 'B') and _num(v) for k, v in raw.items()):
        return {k: float(v) for k, v in raw.items()}
    return None


TOP_TYPES = (('model_hash', str), ('sheet_hash', str), ('revision', str), ('meter', str),
             ('photo', str), ('rewire', bool), ('step_exit', bool), ('deviations', list))


def check_top(block):
    """The failing lines for the top keys."""
    bad = [f'block: {key} must be a {kind.__name__}' for key, kind in TOP_TYPES
           if not isinstance(block.get(key), kind)]
    if block.get('power_mode') not in ('A', 'B'):
        bad.append(f'block: power_mode {block.get("power_mode")!r} is not "A" or "B"')
    if 'date' not in block:
        bad.append('block: date missing')
    if block.get('wiggle') != 'pass':
        bad.append(f'block: wiggle is {block.get("wiggle")!r}, not "pass"')
    if not all(isinstance(d, str) for d in block.get('deviations') or ()):
        bad.append('block: deviations must be strings')
    dv0 = _dv0(block)
    if dv0 is None or block.get('power_mode') not in dv0:
        bad.append('block: dv0_mv missing for the power mode (C9 / C22)')
    if not isinstance(block.get('reading', []), list):
        bad.append('block: reading must be [[reading]] tables')
    return bad


# ---- one reading against its row ----

def _quantity(row, r):
    """The number a numeric row compares, or a failing line (str)."""
    unit = row['unit']
    if unit == 'mOhm':
        if not (_num(r.get('mv')) and _num(r.get('ma')) and r['ma'] > 0):
            return 'needs mv and a positive ma'
        return checklist.mohm(r['mv'], r['ma'])
    key = {'mV': 'mv', 'mA': 'ma', 'ohm': 'value'}[unit]
    return float(r[key]) if _num(r.get(key)) else f'needs a numeric {key}'


def _limit(row, r):
    """The numeric limit for this reading (C14 by contact or span), or a failing line (str)."""
    limit = row['limit_value']
    if not isinstance(limit, dict):
        return limit
    if r.get('span') in checklist.PACK_SPANS:
        return limit['pack_span']
    contact = r.get('contact', 'clamp' if 'joint' in r else None)
    return limit[contact] if contact in CONTACTS else 'needs contact = "ph", "clamp" or "screw"'


COMPARE = {'le': lambda x, lim: x <= lim, 'lt': lambda x, lim: x < lim, 'step': lambda x, lim: x < lim,
           'abs_le': lambda x, lim: abs(x) <= lim}


def _numeric(row, r):
    x, lim = _quantity(row, r), _limit(row, r)
    for why in (x, lim):
        if isinstance(why, str):
            return why
    if not COMPARE[row['op']](x, lim):
        return f'{x:.2f} {row["unit"]} outside the limit ({row["op"]} {lim:g})'
    return None


def _pct(row, r):
    pct, extra = row['limit_value']
    if not (_num(r.get('ma')) and _num(r.get('value'))):
        return 'needs ma (INA228) and value (the reference mA)'
    allowed = abs(r['value']) * pct / 100.0 + extra
    if abs(r['ma'] - r['value']) > allowed:
        return f'{r["ma"]:g} mA against {r["value"]:g} mA: more than {pct:g} % + {extra:g} mA apart'
    return None


def _by_signal(row, r):
    signal, mv = r.get('signal'), r.get('mv')
    if signal not in row['limit_value'] or not _num(mv):
        return 'needs signal = "VBUS", "CHG" or "PGOOD" and mv'
    lim = row['limit_value'][signal]
    ok = mv >= lim if signal == 'VBUS' else mv <= lim
    return None if ok else f'{signal} {mv:g} mV outside the limit ({"ge" if signal == "VBUS" else "le"} {lim:g})'


def _text(row, r):
    return None if r.get('value') == row['limit_value'] else f'value must be {row["limit_value"]!r}'


def _record(row, r):
    return None if _num(r.get('mv')) else 'needs mv'


OPS = {'le': _numeric, 'lt': _numeric, 'step': _numeric, 'abs_le': _numeric, 'pct_mA': _pct,
       'by_signal': _by_signal, 'text': _text, 'record': _record}


def _one_amp(row, r):
    """A 1 A row's INA228 current must be 0.8-1.0 A (P8); C17's CHG/PGOOD highs are read unpowered."""
    if row['when'] != checklist.WHEN_1A or (row['op'] == 'by_signal' and r.get('signal') != 'VBUS'):
        return None
    ma = r.get('ma')
    if _num(ma) and checklist.ONE_A_MIN_MA <= ma <= checklist.ONE_A_MAX_MA:
        return None
    return f'1 A row: ma {ma!r} outside {checklist.ONE_A_MIN_MA:g}-{checklist.ONE_A_MAX_MA:g} mA'


def _lever_open(r):
    """C2's lever-open half: an ohm reading at or above the floor, never OL (record 4.3)."""
    if r.get('unit') == 'open':
        return ['reads OL with the lever open: it is never OL (record 4.3), so give the ohm reading']
    if r.get('unit') not in (None, 'ohm'):
        return [f'unit {r.get("unit")!r} is not the row\'s \'ohm\'']
    value, floor = r.get('value'), checklist.C2_OPEN_MIN_OHM
    if not _num(value):
        return ['needs a numeric value (ohm) with lever = "open"']
    return [] if value >= floor else [f'{value:g} ohm with the lever open: under {floor:g} ohm, a second '
                                      'conductor from STAR to logic ground']


def check_reading(row, r):
    """The failing lines for one reading against its checklist row."""
    unit, lever = r.get('unit'), r.get('lever')
    if lever is not None and (row['id'] != 'C2' or lever not in ('open', 'closed')):
        return ['lever is "open" or "closed", on C2 only']
    if row['unit'] == 'ohm' and (lever == 'open' or (lever is None and unit == 'open')):   # C2's lever-open half
        return _lever_open(r)
    if unit is not None and unit != row['unit']:
        return [f'unit {unit!r} is not the row\'s {row["unit"]!r}']
    lines = [OPS[row['op']](row, r), _one_amp(row, r)]
    if row['expect'] is not None and r.get('value') != row['expect']:
        lines.append(f'value must be {row["expect"]!r}')
    return [line for line in lines if line]


def _id_lines(r, ids):
    """(failing, info) for the ids a reading names; ids is None when they are not checked."""
    bad, info = [], []
    span = r.get('span')
    if span is not None and span not in checklist.PATH_IDS:
        bad.append(f'span {span!r} is not a path segment ({", ".join(checklist.PATH_IDS)})')
    for key in ID_KEYS:
        name = r.get(key)
        if name is None:
            continue
        if ids is None:
            info.append(f'{key} {name!r}: unchecked (revision differs)')
        elif name not in ids:
            bad.append(f'{key} {name!r} is not in the model')
    return bad, info


def _text_key_lines(r):
    """The failing lines for name keys that are not strings (a hand-typed list or table)."""
    return [f'{key} must be a string, not {type(r[key]).__name__}'
            for key in TEXT_KEYS if key in r and not isinstance(r[key], str)]


def check_readings(readings, ids):
    """(failing, info) lines for every [[reading]]."""
    bad, info = [], []
    for n, r in enumerate(readings, 1):
        where = f'reading {n} ({r.get("check") if isinstance(r, dict) else type(r).__name__})'
        typed = _text_key_lines(r) if isinstance(r, dict) else []
        if typed:
            bad += [f'{where}: {line}' for line in typed]
            continue
        row = checklist.BY_ID.get(r.get('check')) if isinstance(r, dict) else None
        if row is None:
            bad.append(f'{where}: unknown check')
            continue
        b, i = _id_lines(r, ids)
        bad += [f'{where}: {line}' for line in b + check_reading(row, r)]
        info += [f'{where}: {line}' for line in i]
    return bad, info


# ---- the whole block ----

def required(block):
    """The rows this run must carry (section 4.3's last paragraph)."""
    need = checklist.REQUIRED_MODE_A if block.get('power_mode') == 'A' else checklist.REQUIRED_MODE_B
    if block.get('rewire') is True or block.get('step_exit') is True:
        need = need + checklist.REQUIRED_1A
    return need


def _pack_spans(readings):
    """The last C14 mOhm reading of each pack-side span: {span: mOhm}."""
    found = {}
    for r in readings:
        if isinstance(r, dict) and r.get('check') == 'C14' and r.get('span') in checklist.PACK_SPANS \
                and _num(r.get('mv')) and _num(r.get('ma')) and r['ma'] > 0:
            found[r['span']] = checklist.mohm(r['mv'], r['ma'])
    return found


def _r_pack_lines(block, readings):
    spans = _pack_spans(readings)
    if len(spans) < len(checklist.PACK_SPANS):
        return []
    total, stated = sum(spans.values()), block.get('r_pack_mohm')
    if not _num(stated):
        return [f'R_pack: r_pack_mohm not recorded (the pack-side spans sum to {total:.2f} mOhm)']
    if abs(stated - total) > R_PACK_TOLERANCE_MOHM:
        return [f'R_pack: r_pack_mohm {stated:g} is not the sum of the pack-side spans ({total:.2f} mOhm)']
    return []


def _readings(block):
    raw = block.get('reading', [])
    return raw if isinstance(raw, list) else []


def _checked_ids(block, model):
    """(the model ids, or None when the revisions differ or the model cannot be read; info lines)."""
    doc, why = _load_model(model)
    if doc is None:
        return None, [why]
    if block.get('revision') != doc.get('revision'):
        return None, [f'revision: block {block.get("revision")!r}, model {doc.get("revision")!r}: '
                      'ids unchecked (revision differs)']
    return model_ids(doc), []


def files_for(revision):
    """(model, sheet) for a block's revision: a frozen earlier revision's own model and sheet when
    source/revisions/ holds it (record 6.1), else the current wiring.toml and build-sheet.md."""
    if isinstance(revision, str) and FROZEN.fullmatch(revision):
        model = HW/'source'/'revisions'/f'{revision}.toml'
        if model.is_file():
            return model, HW/'revisions'/revision/'build-sheet.md'
    return MODEL, SHEET


def status(notes, model=None, sheet=None):
    """(status, problems): status is 'valid', 'failing', 'missing' or 'stale'; problems are the
    lines to print, failing ones first. A model or sheet left None comes from the block's revision
    (files_for)."""
    block, why = read_block(notes)
    if block is None:
        return 'missing', [why]
    by_revision = files_for(block.get('revision'))
    model, sheet = model or by_revision[0], sheet or by_revision[1]
    readings = _readings(block)
    ids, info = _checked_ids(block, model)
    bad, id_info = check_readings(readings, ids)
    present = {r.get('check') for r in readings if isinstance(r, dict) and isinstance(r.get('check'), str)}
    bad = check_top(block) + bad + _r_pack_lines(block, readings)
    bad += [f'{cid}: required for this run and missing' for cid in required(block) if cid not in present]
    stale = _hash_lines(block, model, sheet)
    state = 'failing' if bad else 'stale' if stale else 'valid'
    return state, bad + stale + info + id_info


def values(notes):
    """The numbers the logger and dashboard take from a block: {'dv0_mv': {mode: mV}, 'r_pack_mohm':
    mOhm or None}. r_pack_mohm is the stated value, else the sum of the two pack-side spans."""
    block, _ = read_block(notes)
    if block is None:
        return {'dv0_mv': {}, 'r_pack_mohm': None}
    spans = _pack_spans(_readings(block))
    r_pack = block.get('r_pack_mohm')
    if not _num(r_pack):
        r_pack = sum(spans.values()) if len(spans) == len(checklist.PACK_SPANS) else None
    return {'dv0_mv': _dv0(block) or {}, 'r_pack_mohm': None if r_pack is None else float(r_pack)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('notes', type=Path, help='the run notes (Markdown) holding the block')
    parser.add_argument('--model', type=Path, help=f'the model (default: by the block\'s revision, else {MODEL})')
    parser.add_argument('--sheet', type=Path, help=f'the build sheet (default: by the block\'s revision, else {SHEET})')
    args = parser.parse_args(argv)
    state, problems = status(args.notes, args.model, args.sheet)
    for line in problems:
        print(line)
    print(MESSAGE[state])
    return EXIT[state]


if __name__ == '__main__':
    sys.exit(main())
