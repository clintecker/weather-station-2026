"""The step 1 pre-run checklist and the battery-path budgets: one copy, shared by the build sheet
(make.py) and the preflight tool (tools/preflight.py).

Authority: docs/superpowers/specs/2026-10-29-build-progression-decisions.md, section 4.3 (rows
C1-C23, the pass limits), P8 (the 1 A path limits), M5 (when each row runs), M6 (the path segment
ids and the 20 mV drop flag), D6 (the preflight block) and 7.1 Q2 (the meter).

Each CHECKS row has these keys:

  id           'C1' .. 'C23'
  mode         'A' (the station on USB, the 38 mA screen and the 1 A rows) or 'B' (the station on
               the regulator: C15, C20-C23)
  when         WHEN_PRE_A, WHEN_1A or WHEN_PRE_B: before every mode-A run; after every rewire and
               at every step exit (charging at 0.8-1.0 A); before every mode-B run
  condition    the record's Condition cell
  measure      the record's Measure cell
  limit_value  the pass limit, in `unit`: a number, a dict of numbers (C14 by contact, C17 by
               signal), a (percent, mA) pair (C5, C16), or the text a by-eye or open row must read
  unit         'mOhm' (mV / the INA228 current in A), 'mV', 'mA', 'ohm', 'open', 'by eye' or
               'recorded'
  op           how a reading meets limit_value: 'le' (<=), 'lt' (<), 'ge' (>=), 'abs_le'
               (|x| <=), 'step' (a min/max step below the limit), 'pct_mA' (|INA - reference| <=
               percent of the reference + mA), 'text' (the reading's value equals the limit text),
               'record' (any number), 'by_signal' (C17: VBUS >= its floor, CHG/PGOOD <= the ceiling)
  expect       extra text the reading's value must equal, or None (C23: 'no reset')
  note         the rest of the record's Pass cell

Standard library only; no KiCad."""
import hashlib
from pathlib import Path

METER = 'Fluke 87V, 600 mV DC range, high-resolution mode (0.01 mV)'

WHEN_PRE_A = 'before every mode-A run'
WHEN_1A = 'after every rewire and at every step exit (1 A charge)'
WHEN_PRE_B = 'before every mode-B run'

ONE_A_MIN_MA = 800.0     # P8: the 1 A rows are read with the INA228 current between 0.8 and 1.0 A
ONE_A_MAX_MA = 1000.0
SCREEN_MA = 38.0         # the 100 ohm load at about 3.8 V (C5)

# C2's lever-open half (record 4.3): a floor, not "open". With the TIE's lever open, every other path
# from STAR to logic ground still holds a resistor of 100 ohm or more (the load; R_ISER, R6, R_IPD) or a
# junction, so a reading under this is a second conductor.
C2_OPEN_MIN_OHM = 100.0

UNITS = ('mOhm', 'mV', 'mA', 'ohm', 'open', 'by eye', 'recorded')


def _row(cid, mode, when, condition, measure, limit_value, unit, op, note, expect=None):
    assert unit in UNITS, unit
    return dict(id=cid, mode=mode, when=when, condition=condition, measure=measure,
                limit_value=limit_value, unit=unit, op=op, expect=expect, note=note)


_C5 = 'pack plugged, input off, load on, 1 min settled (about 38 mA)'
_C12 = 'charging, first 10 min of CC, I = 0.8-1.0 A, V_ISET about 2.0-2.4 V'
_C15 = 'mode B, TX bursts (NUCLEO USB unplugged, SHUNT fitted, 100 ohm load out, OLED VCC lead ' \
       'unplugged, DMM min/max across at least 5 radio TX bursts)'
_C1 = 'pack unplugged, nothing powered'

CHECKS = (
    _row('C1', 'A', WHEN_PRE_A, _C1,
         'continuity INA228 X1.2 (VBUS) to X1.3 (VIN+) on every INA228', 'open', 'open', 'text',
         'SJ1 open'),
    _row('C2', 'A', WHEN_PRE_A, 'as C1',
         "open the TIE's lever at STAR: STAR to CN6.6", 0.5, 'ohm', 'lt',
         f'with the TIE closed, under 0.5 ohm; with the lever open, at least {C2_OPEN_MIN_OHM:g} ohm on the '
         'ohms range (a reading with lever = "open"; the value recorded): never 0, since a second '
         'conductor reads like the TIE, and not OL either, since the TIE is not the only path: R9, R_ISER and '
         'R_IPD give about 1.01 MOhm, about 11 kOhm plus a diode by meter polarity (PB1\'s ESD diode), and '
         'the 100 ohm load, OUT and the regulator\'s switches give another diode path'),
    _row('C3', 'A', WHEN_PRE_A, 'as C1',
         'each breakout test-point strip (charger a50-a53, a59; INA228 VIN+, VIN-, VBUS) holds only '
         'its header pin', 'pass', 'by eye', 'text', 'by eye against the build sheet'),
    _row('C4', 'A', WHEN_PRE_A, 'as C1',
         "pack-mating pigtail and board pigtails: red is + by meter against the board's silkscreen; "
         'unused black leads insulated', 'pass', 'by eye', 'text', 'by eye and meter'),
    _row('C5', 'A', WHEN_PRE_A, _C5, 'INA228 current against OUT / 100 ohm', (2.0, 2.0), 'mA',
         'pct_mA', 'within 2 % + 2 mA (reading: ma = INA228, value = OUT / 100 ohm in mA)'),
    _row('C6', 'A', WHEN_PRE_A, 'as C5', 'pack plug + (back-probed) to charger header OUT', 10.0,
         'mV', 'le', ''),
    _row('C7', 'A', WHEN_PRE_A, 'as C5', 'STAR to charger header GND', 1.0, 'mV', 'le',
         'the load does not return through the charger'),
    _row('C8', 'A', WHEN_PRE_A, 'as C5', 'STAR to CN6.6', 1.0, 'mV', 'le', ''),
    _row('C9', 'A', WHEN_PRE_A, 'as C5, then the load lever opened',
         'INA228 current at zero load; record dV0 = gauge VCELL - INA VBUS', 1.0, 'mA', 'abs_le',
         'dV0 recorded (the block\'s dv0_mv)'),
    _row('C10', 'A', WHEN_PRE_A, 'as C5', 'DMM at the pack plug against gauge VCELL', 10.0, 'mV',
         'abs_le', 'within 10 mV (reading: mv = DMM - gauge)'),
    _row('C11', 'A', WHEN_PRE_A, "as C5, DMM min/max on C6's span",
         'wiggle each lever, pigtail, PH plug, the TIE, the regulator leads and both USB cables for '
         '30 s; watch vout and vcell in the logger and the A0 (ISET) and A2 (VIN) readings; under the '
         'node firmware only (benchlink has no counter), spin the cups through the wiggle: the next '
         'observation\'s wind speed is not zero and STATUS still shows meter_link=ok', 1.0, 'mV', 'step',
         'no step >= 1 mV on the DMM (about 26 mOhm); no visible step in the logger'),
    _row('C12', 'A', WHEN_1A, _C12, '+ span: pack plug + to header LIPO', 75.0, 'mOhm', 'le',
         'PATH_POS, including the 15 mOhm shunt'),
    _row('C13', 'A', WHEN_1A, 'as C12', '- span: header GND to pack plug -', 40.0, 'mOhm', 'le',
         'PATH_NEG'),
    _row('C14', 'A', WHEN_1A, 'as C12',
         'each JST PH mating; each lever clamp to clamp; each screw (VIN+ link, VIN- link); the two '
         'pack-side spans: pack plug + (back-probed) to the CELL+ clamp, and the STAR clamp to pack '
         'plug - (back-probed)', {'ph': 20.0, 'clamp': 5.0, 'screw': 5.0, 'pack_span': 28.0},
         'mOhm', 'le', 'their sum recorded as R_pack'),
    _row('C15', 'B', WHEN_PRE_B, _C15, 'TIE: STAR to the regulator GND strip', 1.0, 'mV', 'lt', ''),
    _row('C16', 'A', WHEN_1A, 'as C12',
         'ISET-derived current (R_ISET 1000 ohm) against INA228 battery current', (10.0, 20.0), 'mA',
         'pct_mA', 'a shunt bypass reads near 0 (reading: ma = INA228, value = ISET-derived mA)'),
    _row('C17', 'A', WHEN_1A, 'as C12, then the input removed for a moment',
         'charger header VBUS while charging; CHG and PGOOD high levels with the input removed '
         '(both off)', {'VBUS': 4600.0, 'CHG': 3600.0, 'PGOOD': 3600.0}, 'mV', 'by_signal',
         'VBUS >= 4.6 V; CHG/PGOOD highs <= 3.6 V (VDD + 0.3 V)'),
    _row('C18', 'A', WHEN_1A, 'as C12, DMM min/max on the + span', 'wiggle as C11', 2.0, 'mV',
         'step', 'no step >= 2 mV'),
    _row('C19', 'A', WHEN_PRE_A, 'NUCLEO', 'tug each Arduino-header jumper; tape in place; jumpers tied',
         'pass', 'by eye', 'text', 'none moves; tape present'),
    _row('C20', 'B', WHEN_PRE_B, 'as C15', 'STAR to CN6.6', 3.0, 'mV', 'le', ''),
    _row('C21', 'B', WHEN_PRE_B, 'as C15',
         "the regulator's VOUT pin to CN6.4 (the whole P1 output chain: LK_REG_SHUNT, SHUNT, "
         'L_REG_3V3, the board-A 3V3 strip where LK_3V3_CN6_4 starts (QT.V+; change C, which moved it to the load '
         'switch, is deferred to the carrier), LK_3V3_CN6_4)', 10.0, 'mV', 'le', ''),
    _row('C22', 'B', WHEN_PRE_B, 'as C15, between TX bursts',
         'mode-B dV0: gauge VCELL - INA VBUS with the station idle', None, 'recorded', 'record',
         'recorded (the block\'s dv0_mv)'),
    _row('C23', 'B', WHEN_PRE_B, "as C15, DMM min/max on C21's span",
         'wiggle L_REG_VIN, LK_REG_SHUNT, the SHUNT, L_REG_3V3, LK_3V3_CN6_4, L_NUC_RET (the CN6.7 '
         'lead) and L_TIE, for 30 s each', 2.0, 'mV', 'step', 'no reset; no step >= 2 mV',
         expect='no reset'),
)

BY_ID = {row['id']: row for row in CHECKS}

# Section 4.3's last paragraph: which rows each run needs. "C12-C18 after every rewire" means the
# 1 A rows; C15 is numbered inside that range but is a mode-B row (the TIE carries current only in
# mode B), so it is required with mode B, not with a rewire.
REQUIRED_MODE_A = tuple(r['id'] for r in CHECKS if r['when'] == WHEN_PRE_A)
REQUIRED_MODE_B = tuple(r['id'] for r in CHECKS if r['when'] == WHEN_PRE_B)
REQUIRED_1A = tuple(r['id'] for r in CHECKS if r['when'] == WHEN_1A)

# P8 and M6: the battery-path segments, their budgets in mOhm at the 1 A measurement.
BUDGETS = {
    'PATH_POS': 75.0,        # pack plug + to header LIPO, including the 15 mOhm shunt (C12)
    'PATH_NEG': 40.0,        # header GND to pack plug - (C13)
    'PATH_PACK_POS': 28.0,   # pack plug + to the CELL+ clamp: one PH mating at 20 + 60 mm lead at 8 (C14)
    'PATH_PACK_NEG': 28.0,   # the STAR clamp to pack plug - (C14)
}
PATH_CELL_OUT_FLAG_MV = 20.0   # M6 drop form: CELL+ to OUT, flagged when drop - dV0 > 20 mV
PATH_IDS = (*BUDGETS, 'PATH_CELL_OUT')
PACK_SPANS = ('PATH_PACK_POS', 'PATH_PACK_NEG')

COVERAGE_NOTE = ('PATH_CELL_OUT covers CELL+ to OUT only; the pack mating (PATH_PACK_POS, '
                 'PATH_PACK_NEG) is covered by C6/C11 at preflight, C12-C14 at 1 A and the VCELL '
                 'step flag live')


def implied_mv(budget_mohm, current_ma):
    """The drop a budget allows at a current: mOhm x A = mV (75 mOhm at 1000 mA is 75 mV)."""
    return budget_mohm * current_ma / 1000.0


def mohm(mv, ma):
    """A span's resistance from its drop and the INA228 current: mV / A = mOhm."""
    return mv / (ma / 1000.0)


def blob_sha1(path):
    """git's blob hash of a file (what `git hash-object` prints), computed without git."""
    data = Path(path).read_bytes()
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()
