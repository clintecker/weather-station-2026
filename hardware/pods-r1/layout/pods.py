"""The three pod boards (TH, BARO, UV) laid out on the Adafruit Perma-Proto Quarter #1608, as data.

Board frame: permaproto.py's. Millimetres, x to the right, y up, origin at the board's lower-left corner with the silk
readable (columns 1-15 left to right, rows A-J bottom to top, rails bot+ bot- below row A and top+ top- above row J).
Z up from the Perma-Proto's top face. Every pin, lead and wire end sits in a named hole ("A1", "H10", "top-5").

The gland edge is the board's BOTTOM edge (y = 0, the bot+ rail side): J1's jack mouth faces it (-y), so the box's
PG-7 gland (Task 6) sits below that edge and the cable plugs straight up into the jack. The jack board overhangs that
edge as on the TX cards (the BOB-14021 reaches y -7.62, the jack's mouth y -10.42); the breakout on row J overhangs
the top edge and the right edge (see the report). All three pods share one footprint:

  J1   BOB-14021 + 87180-066LF on a 1x6 male header, pins 1-6 in A1-A6, turned 180 (mouth to the bottom edge)
  U1   Adafruit 24LC32 #5146, turned 180, header in row F: VIN F10 ... WP F5 (its board hangs down over rows B-E)
  U2   the sensor, upright, header in row J: VIN J10, then 3Vo J11, GND J12, SCL J13 ... (BARO and UV only)
  JP1  Sullins PRPC002SAAN-RC + SPC02SYAN shunt in H4 (pin 1, 3V3) and H5 (pin 2, WP): shunt on = WP at 3.3 V
  R1   10 k Yageo MFR-25FBF52-10K lying along column 5 from J5 (WP) to top-5: shunt off = WP pulled to GND = writable
  top- rail = GND (R1's ground, tapped from U1's GND strip by J8 to top-8); top+, bot+ and bot- are unused

U1 and U2 share only strip F-J10, where both put VIN (3V3). TH has no U2: its lead lands on J10, J12, J13 and J14,
the holes UV's LTR390 uses for VIN, GND, SCL and SDA, so TH and UV are wired identically. BARO differs from UV only
in its two SDA wires (they end on strip F-J15 instead of F-J14), because the BMP581's SDI is its sixth pad.
All nine wires run on the copper side along routes stored with them (Wire.path); none needs a top jumper.

Rulings applied (task 3 brief): the port's 3.3 V feeds every breakout's VIN (their header-side pull-ups go to VIN);
3Vo is left unconnected; every fitted 10 k pull-up stays (Task 4 does the budget); WP floats on the 24LC32 board, so
R1 pulls it down and JP1 lifts it.
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.dont_write_bytecode = True
_HERE = Path(__file__).resolve().parent
for _p in (_HERE, _HERE.parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import sources as S            # noqa: E402  hardware/pods-r1/sources.py
import permaproto as PP        # noqa: E402

P = 2.54                                         # hole pitch (permaproto_q_cols)
HDR = S.val("hdr_plastic")                       # male header plastic, board to breakout (TX row)
PCB = S.val("breakout_t")                        # breakout PCB thickness (TX row, TBD 1.6)
POD_NAMES = ("TH", "BARO", "UV")
COLOURS = {"3V3": "red", "GND": "black", "SCL": "yellow", "SDA": "blue"}     # TX convention; anything else green
GLAND_EDGE = "bottom"                            # the board edge J1's mouth faces


@dataclass
class Box:
    """An axis-aligned 3D box in the board frame (mm). keepout: space that must stay clear but holds no part
    (the plug in the jack, the shunt's finger room)."""
    x0: float
    y0: float
    x1: float
    y1: float
    z0: float
    z1: float
    what: str
    keepout: bool = False

    def __post_init__(self):
        self.x0, self.x1 = sorted((self.x0, self.x1))
        self.y0, self.y1 = sorted((self.y0, self.y1))
        self.z0, self.z1 = sorted((self.z0, self.z1))


@dataclass
class Placed:
    """A part on the board. pins: {pin name: hole}; nets: {pin name: net or None (left unconnected)}.
    part: the exact maker names and numbers. For a breakout: source (its sources.py row), rot (0 or 180, never
    mirrored), origin (its maker frame's (0, 0) in the board frame), unfitted (header pads left without a pin)."""
    ref: str
    kind: str
    part: str
    pins: dict
    nets: dict
    boxes: list
    note: str = ""
    source: str = ""
    rot: int = 0
    origin: tuple = (0.0, 0.0)
    unfitted: tuple = ()


@dataclass
class Wire:
    """24 AWG solid hook-up wire between two holes; side "bottom" runs on the copper side (its ends may sit in holes a
    breakout covers from above), "top" lies on the component side. path: the route as laid, (x, y) from hole_a through
    each right-angle bend to hole_b, on the 1.27 grid (the hole lines and the lines midway between them), keeping
    OD/2 + fillet_clear from every used hole but its own ends (Clint's rule on the TX cards)."""
    net: str
    hole_a: str
    hole_b: str
    side: str
    colour: str
    note: str = ""
    path: tuple = ()


@dataclass
class Conductor:
    colour: str
    net: str
    pad: str          # the SHT45 header pad it is soldered to (sensor end)
    hole: str         # the pod-board hole it is soldered into (pod end)


@dataclass
class Lead:
    """The TH pod's stranded 4-wire lead from the SHT45 (in the shield) to the pod board."""
    ref: str
    part: str
    source: str
    conductors: list
    length_m: float
    note: str = ""


@dataclass
class Pod:
    name: str
    sensor: str                      # the sources.py row of the pod's sensor breakout
    parts: list
    wires: list
    lead: Lead = None
    joints: set = field(default_factory=set)      # holes deliberately shared by two parts (none on these boards)

    def part(self, ref):
        return next(p for p in self.parts if p.ref == ref)

    def nets(self):
        """Intended nets: {net: {"ref.pin", ...}} from each part's pin nets and, for TH, the lead's sensor pads
        ("U2.VIN" etc. on the SHT45 at the lead's far end). Unconnected pins are left out (see unconnected())."""
        out = {}
        for p in self.parts:
            for pin, net in p.nets.items():
                if net:
                    out.setdefault(net, set()).add(f"{p.ref}.{pin}")
        if self.lead:
            for c in self.lead.conductors:
                out.setdefault(c.net, set()).add(f"{self.lead.ref}.{c.pad}")
        return out

    def unconnected(self):
        return {f"{p.ref}.{pin}" for p in self.parts for pin, net in p.nets.items() if not net}

    def holes_used(self):
        """{hole: [what uses it]}: part pins, wire ends and lead ends."""
        used = {}
        for p in self.parts:
            for pin, h in p.pins.items():
                used.setdefault(h, []).append(f"{p.ref}.{pin}")
        for w in self.wires:
            for h in (w.hole_a, w.hole_b):
                used.setdefault(h, []).append(f"wire {w.net} {w.hole_a}-{w.hole_b}")
        if self.lead:
            for c in self.lead.conductors:
                used.setdefault(c.hole, []).append(f"lead {c.colour} {c.net}")
        return used


def xy(hole):
    return PP.HOLES[hole]


def tf(rot, x0, y0, x, y):
    """Maker frame -> board frame: a turn about z by rot (0 or 180), never a mirror."""
    return {0: (x0 + x, y0 + y), 180: (x0 - x, y0 - y)}[rot]


def tbox(rot, x0, y0, b, ref):
    (xa, ya), (xb, yb) = tf(rot, x0, y0, b.x0, b.y0), tf(rot, x0, y0, b.x1, b.y1)
    return Box(xa, ya, xb, yb, b.z0, b.z1, f"{ref} {b.what}", b.keepout)


def hole_at(x, y):
    for name, (hx, hy) in PP.HOLES.items():
        if abs(hx - x) < 1e-3 and abs(hy - y) < 1e-3:
            return name
    raise ValueError(f"no hole at ({x:.3f}, {y:.3f})")


# ------------------------------------------------------------------ footprints
# BOB-14021 + 87180-066LF: the TX cards' bob() geometry (hardware/tx-stack-r1/layout/stack.py, read only), by value.
BOB_PIN1_X = 13.97          # maker x of header pin 1 (pins run to 1.27 at pin 6); TX stack.py bob()
BOB_JACK_X = 7.62           # maker x of the jack's centre line; TX stack.py bob()
BOB_PEG_TO_MOUTH = 7.88     # jack pegs to mouth (KiCad fab: pegs 8.89, mouth 16.77 from the pin-1 row); TX stack.py bob()


def bob(ref, first_hole, nets, note=""):
    """J1: BOB-14021 standing on its soldered 1x6 male header, tab snapped off, jack pins cut flush, turned 180 so the
    mouth faces the board's bottom edge: pin i in the hole (i - 1) columns right of first_hole."""
    hx, hy = xy(first_hole)
    by = S.val("bob_hdr_y")
    mouth = S.val("bob_peg_y") + BOB_PEG_TO_MOUTH
    x0, y0 = hx + BOB_PIN1_X, hy + by
    jw, jd, jh = S.val("jack_w"), S.val("jack_d"), S.val("jack_h")
    pw, _ph, pl, _len = S.val("plug_6p")
    t = HDR + PCB
    mk = [Box(0, by - 1.27, S.val("bob_w"), by + 1.27, 0, HDR, "1x6 male header plastic"),
          Box(0, 0, S.val("bob_w"), S.val("bob_d"), HDR, t, "SparkFun BOB-14021 PCB"),
          Box(BOB_JACK_X - jw / 2, mouth - jd, BOB_JACK_X + jw / 2, mouth, t, t + jh, "Amphenol 87180-066LF jack"),
          Box(BOB_JACK_X - pw / 2, mouth, BOB_JACK_X + pw / 2, mouth + S.val("plug_len"), t + 1, t + 1 + pl,
              "RJ11 plug and its cable bend", keepout=True)]
    pins = {str(i): hole_at(*tf(180, x0, y0, BOB_PIN1_X - (i - 1) * P, by)) for i in range(1, 7)}
    return Placed(ref, "BOB", "SparkFun BOB-14021 + Amphenol 87180-066LF on a 1x6 male header", pins, nets,
                  [tbox(180, x0, y0, b, ref) for b in mk], note, rot=180, origin=(x0, y0))


BREAKOUT_PART = {
    "eeprom_24lc32": "Adafruit 24LC32 I2C EEPROM STEMMA QT breakout #5146",
    "ltr390": "Adafruit LTR390 UV light sensor breakout #4831",
    "bmp581": "Adafruit BMP581 pressure and temperature breakout #6407",
    "sht45": "Adafruit SHT45 temperature and humidity breakout with PTFE cap #6174",
}


def breakout(ref, key, rot, pin1_hole, nets, fitted=None, note=""):
    """An Adafruit breakout standing on its own header, drawn from its sources.py row: outline key, pad names
    key_pins (left to right in the maker frame), header row key_hdr (x of pad 1, y, pitch). fitted: how many pads,
    from pad 1, get a header pin (the rest stay empty); default all. Pad 1 goes in pin1_hole."""
    w, d = S.val(key)
    names = S.val(key + "_pins")
    hx1, hy, pitch = S.val(key + "_hdr")
    n = len(names) if fitted is None else fitted
    mx = {nm: (hx1 + i * pitch, hy) for i, nm in enumerate(names[:n])}
    px, py = xy(pin1_hole)
    x0, y0 = (px - hx1, py - hy) if rot == 0 else (px + hx1, py + hy)
    mk = [Box(hx1 - 1.27, hy - 1.27, hx1 + (n - 1) * pitch + 1.27, hy + 1.27, 0, HDR, f"1x{n} male header plastic"),
          Box(0, 0, w, d, HDR, HDR + PCB, f"{BREAKOUT_PART[key].split(' #')[0]} PCB")]
    pins = {nm: hole_at(*tf(rot, x0, y0, *p)) for nm, p in mx.items()}
    return Placed(ref, "BREAKOUT", BREAKOUT_PART[key], pins, {nm: nets.get(nm) for nm in pins},
                  [tbox(rot, x0, y0, b, ref) for b in mk], note, source=key, rot=rot, origin=(x0, y0),
                  unfitted=tuple(names[n:]))


def jp1(ref, h1, h2, note=""):
    """2-pin vertical male header (pin 1 in h1, pin 2 in h2, along a row) with its shunt fitted."""
    (xa, ya), (xb, yb) = xy(h1), xy(h2)
    assert ya == yb and abs(xb - xa - P) < 1e-3, "JP1 lies along a row, pin 2 to the right of pin 1"
    plastic, post, sq = S.val("jp1_hdr")
    sl, sw, sh = S.val("shunt_spc02")
    xm, ym = (xa + xb) / 2, ya
    boxes = [Box(xa - 1.27, ya - 1.27, xb + 1.27, ya + 1.27, 0, plastic, f"{ref} Sullins PRPC002SAAN-RC plastic"),
             Box(xa - sq / 2, ya - sq / 2, xb + sq / 2, ya + sq / 2, plastic, plastic + post, f"{ref} posts"),
             Box(xm - sl / 2, ym - sw / 2, xm + sl / 2, ym + sw / 2, plastic, plastic + sh,
                 f"{ref} Sullins SPC02SYAN shunt")]
    return Placed(ref, "HDR2", "Sullins PRPC002SAAN-RC 2-pin header + Sullins SPC02SYAN shunt",
                  {"1": h1, "2": h2}, {"1": "3V3", "2": "WP"}, boxes, note)


def r_lying(ref, h1, h2, nets, note=""):
    """Axial resistor lying flat on the top face along a row or a column, leads in h1 and h2 (7.62 or more apart)."""
    (xa, ya), (xb, yb) = xy(h1), xy(h2)
    along_x = abs(ya - yb) < 1e-3
    assert along_x or abs(xa - xb) < 1e-3, "R1 lies along a row or a column"
    assert abs(xb - xa) + abs(yb - ya) >= 3 * P - 1e-3, "R1 needs 7.62 or more between its holes"
    bl, bd = S.val("r1_body")
    xm, ym = (xa + xb) / 2, (ya + yb) / 2
    hl, hw = (bl / 2, bd / 2) if along_x else (bd / 2, bl / 2)
    boxes = [Box(xm - hl, ym - hw, xm + hl, ym + hw, 0.1, 0.1 + bd, f"{ref} resistor body"),
             Box(min(xa, xb) - 0.3, min(ya, yb) - 0.3, max(xa, xb) + 0.3, max(ya, yb) + 0.3, 0, 1.0,
                 f"{ref} resistor leads")]
    return Placed(ref, "RLY", "Yageo MFR-25FBF52-10K, 10 k 1 % 1/4 W metal film", {"1": h1, "2": h2}, nets, boxes, note)


# ------------------------------------------------------------------ the shared footprint
JACK_NETS = {"1": None, "2": "3V3", "3": "SDA", "4": "GND", "5": "SCL", "6": None}     # the sensor-port pin map
BREAKOUT_NETS = {"VIN": "3V3", "GND": "GND", "SCL": "SCL", "SDA": "SDA", "SCK": "SCL", "SDI": "SDA", "WP": "WP"}
# not connected on purpose: 3Vo (regulator output; the port's 3.3 V goes in at VIN), INT, and on the BMP581 SDO
# (pulled to 3.3 V on the board, address 0x47); CS and INT of the BMP581 get no header pin (fitted=6).


def w(net, a, b, side="bottom", note="", path=()):
    pts = tuple((round(i * G, 4), round(j * G, 4)) for i, j in path)
    return Wire(net, a, b, side, COLOURS.get(net, "green"), note, pts)


G = P / 2          # the routing grid: hole lines and the lines midway between them

# Routes (grid units of 1.27 mm from the board's lower-left corner, ends included), found with a small A* router run
# once during design under the TX rules: right-angle runs, few bends, OD/2 + fillet_clear from every used hole but
# the wire's own ends, no two runs side by side 1.27 apart, insulated wires crossing only at right angles, clear of
# the mounting holes' mount_keep. The checks in tests/test_pods_layout.py re-verify them from the holes.
_COMMON_WIRES = [
    ("3V3", "E2", "F4", "jack 3.3 V strip to JP1's 3.3 V strip (F4 under U1: from the copper side)",
     [(5, 17), (9, 17), (9, 23)]),
    ("3V3", "G4", "G10", "JP1's 3.3 V strip to the VIN strip U1 and U2 share", [(9, 25), (21, 25)]),
    ("GND", "D4", "F12", "jack ground strip (under U1) to the sensor's GND strip", [(9, 15), (25, 15), (25, 23)]),
    ("SCL", "E5", "G13", "jack clock strip (under U1) to the sensor's SCL strip",
     [(11, 17), (23, 17), (23, 25), (27, 25)]),
    ("SCL", "H13", "H7", "the sensor's SCL strip to U1 SCL", [(27, 27), (15, 27)]),
    ("GND", "I12", "I8", "the sensor's GND strip to U1 GND", [(25, 29), (17, 29)]),
    ("GND", "J8", "top-8", "U1 GND to the top- rail (R1's ground)", [(17, 31), (17, 37)]),
]
_SDA_WIRES = {     # the sensor's SDA strip: F-J14 (LTR390 SDA, and the TH lead's blue) or F-J15 (BMP581 SDI)
    14: [("SDA", "C3", "F14", "jack data strip (under U1) to the sensor's SDA strip",
          [(7, 13), (27, 13), (27, 23), (29, 23)]),
         ("SDA", "I14", "J6", "the sensor's SDA strip to U1 SDA, round the right edge and under the sensor's overhang",
          [(29, 29), (33, 29), (33, 39), (13, 39), (13, 31)])],
    15: [("SDA", "C3", "F15", "jack data strip (under U1) to the sensor's SDI strip",
          [(7, 13), (27, 13), (27, 23), (31, 23)]),
         ("SDA", "I15", "J6", "the sensor's SDI strip to U1 SDA, round the right edge and under the sensor's overhang",
          [(31, 29), (33, 29), (33, 39), (13, 39), (13, 31)])],
}


def _common(sda_col):
    parts = [
        bob("J1", "A1", JACK_NETS, "the sensor port; mouth to the bottom (gland) edge, overhanging it as on the TX cards"),
        breakout("U1", "eeprom_24lc32", 180, "F10", BREAKOUT_NETS,
                 note="ID EEPROM at 0x50; turned 180 so VIN shares strip F-J10 with U2's VIN; its board hangs down "
                      "over rows B-E, clear of both mounting holes"),
        jp1("JP1", "H4", "H5", "write protect: shunt on = WP at 3.3 V = protected; shunt off = R1 holds WP low = writable"),
        r_lying("R1", "J5", "top-5", {"1": "WP", "2": "GND"},
                "WP pull-down (the 24LC32 board leaves WP floating), lying along column 5 over the unused top+5 hole"),
    ]
    wires = [w(n, a, b, "bottom", note, path) for n, a, b, note, path in _COMMON_WIRES + _SDA_WIRES[sda_col]]
    return parts, wires


def _th():
    parts, wires = _common(14)
    lead = Lead("U2", BREAKOUT_PART["sht45"], "sht45",
                [Conductor("red", "3V3", "VIN", "J10"), Conductor("black", "GND", "GND", "J12"),
                 Conductor("yellow", "SCL", "SCL", "J13"), Conductor("blue", "SDA", "SDA", "J14")],
                S.val("th_lead_m"),
                "stranded 4-wire lead soldered to the SHT45's own header pads (no header on the SHT45); the pod end "
                "lands where the UV pod's LTR390 has VIN, GND, SCL and SDA, so the board is wired as the UV pod's. "
                "SHT45 3Vo is left unconnected.")
    return Pod("TH", "sht45", parts, wires, lead)


def _uv():
    parts, wires = _common(14)
    parts.append(breakout("U2", "ltr390", 0, "J10", BREAKOUT_NETS,
                          note="sensor face up for the lid window; overhangs the top edge 3.81 and the right edge 2.54"))
    return Pod("UV", "ltr390", parts, wires)


def _baro():
    parts, wires = _common(15)
    parts.append(breakout("U2", "bmp581", 0, "J10", BREAKOUT_NETS, fitted=6,
                          note="header cut to 6 pins (VIN..SDI); CS (pulled up on the board: I2C mode) and INT pads "
                               "left empty: CS would land between column 15 and the board edge, INT beyond the edge; "
                               "overhangs the top edge 3.81 and the right edge 5.08"))
    return Pod("BARO", "bmp581", parts, wires)


_BUILD = {"TH": _th, "BARO": _baro, "UV": _uv}


def pod(name):
    return _BUILD[name]()


def hole_map(p):
    """ASCII hole map of one pod (rows top to bottom as seen from the component side)."""
    used = p.holes_used()
    tag = {}
    for part in p.parts:
        for pin, h in part.pins.items():
            tag[h] = f"{part.ref}.{pin}"[:6]
    for wi, wr in enumerate(p.wires, 1):
        for h in (wr.hole_a, wr.hole_b):
            tag[h] = f"w{wi}:{wr.net}"
    if p.lead:
        for c in p.lead.conductors:
            tag[c.hole] = f"L.{c.colour[:3]}"
    rows = ["top-", "top+"] + list("JIHGF") + ["--"] + list("EDCBA") + ["bot-", "bot+"]
    out = ["      " + "".join(f"{c:<8}" for c in range(1, 16))]
    for r in rows:
        if r == "--":
            out.append("      " + "(mounting holes at the left and right ends of this gap)")
            continue
        out.append(f"{r:<6}" + "".join(f"{tag.get(f'{r}{c}', '.'):<8}" for c in range(1, 16)))
    assert all(h in PP.HOLES for h in used)
    return "\n".join(out)


if __name__ == "__main__":
    for n in POD_NAMES:
        p = pod(n)
        print(f"== {n}")
        print(hole_map(p))
        for i, wr in enumerate(p.wires, 1):
            print(f"  w{i} {wr.net:<4} {wr.hole_a:>4} -> {wr.hole_b:<4} {wr.side} {wr.colour}  {wr.note}")
