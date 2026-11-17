"""Every dimension and electrical fact the three sensor pods' drawings use, with its source.

status: "sourced"  read from a maker's CAD file, a datasheet or this repo
        "derived"  computed from sourced numbers, or read from a maker's file with a stated gap (the note says which)
        "TBD"      [TBD-MEASURE]: not found in any source; nothing may use it as a real number until measured
The README's dimension table is generated from this file (python3 sources.py --check keeps it in step).
Values shared with the TX stack (bob_w, jack_w, ...) are read from hardware/tx-stack-r1/sources.py, never copied:
val(), tbd() and label() fall through to it.

Board coordinates below are millimetres, x to the right, y up, origin at the lower-left corner of the outline for the
breakouts (the origin of Adafruit's Eagle file for the Perma-Proto, which is the board centre).
"""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_TX_PATH = HERE.parent / "tx-stack-r1" / "sources.py"


def _load_tx():
    """The TX stack's sources.py, read-only, under its own module name (both files are called sources.py)."""
    spec = importlib.util.spec_from_file_location("tx_stack_sources", _TX_PATH)
    mod = importlib.util.module_from_spec(spec)
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True     # never leave a __pycache__ in the TX folder
    path = list(sys.path)
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = keep
        sys.path[:] = path
    return mod


TX = _load_tx()

GH = "https://github.com/adafruit/"
SHT = (GH + "Adafruit-SHT40-PCB/blob/44a53d7af8/Adafruit%20SHT45.brd (last change to the file 2023-01-13; repo HEAD 40fe2b3aca; "
       "the .sch in the same commit)")
BMP = (GH + "Adafruit-BMP5xx-Temperature-and-Pressure-Sensor-PCB/blob/6ce79de433/"
       "Adafruit%20BMP581%20Temperature%20and%20Pressure%20Sensor%20rev%20B.brd (last change to the file 2025-09-02; repo HEAD 0d42329e09; "
       "the .sch in the same commit)")
LTR = GH + "Adafruit-LTR390-PCB/blob/0f4656c2b2/Adafruit_LTR390.brd (commit 0f4656c2b2, 2020-12-29, also repo HEAD; the .sch in the same commit)"
EEP = (GH + "Adafruit-24LC32-PCB/blob/e92cf5549d/Adafruit%2024LC32%20I2C%20EEPROM.brd (commit e92cf5549d, 2021-08-11, also repo HEAD; "
       "the .sch in the same commit)")
PERMA = (GH + "Adafruit-Perma-Proto-PCB/blob/6a11bc3bbf/adafruit%20permaproto%20quarterbreadboard.brd (last change to the file "
         "2026-06-03; repo HEAD 2c7f1ba879; Adafruit 1/4-size Perma-Proto, product 1608 in the repo README)")
TI = "TI SLVA689 'I2C Bus Pullup Resistor Calculation', https://www.ti.com/lit/an/slva689/slva689.pdf, Table 1 (standard mode column)"
SHIELD = "~/Downloads/Stevenson_screen_NFS.3mf"     # kept unexpanded in the table; shield_path() expands it where used

D = {
    # ---------------------------------------------------------------- Adafruit Perma-Proto Quarter #1608
    "permaproto_q": ((43.18, 50.8), "Perma-Proto Quarter #1608 outline, width x height (x 43.18 across the 15 columns, y 50.8 along them); corner radius permaproto_q_corner_r; thickness not in the file", PERMA + ": Dimension layer 20, x -21.59..21.59, y -25.4..25.4", "sourced"),
    "permaproto_q_corner_r": (2.54, "Perma-Proto Quarter outline corner radius", PERMA + ": four 90 degree arcs on layer 20", "sourced"),
    "permaproto_q_cols": ((15, 2.54, -17.78), "Perma-Proto Quarter columns: count, pitch, x of the first column (file coordinates, origin at the board centre; columns 1..15 left to right as silkscreened); the outline's left edge is at x -21.59", PERMA + ": the 210 plated holes' x values", "sourced"),
    "permaproto_q_rows": ((-13.97, -11.43, -8.89, -6.35, -3.81, 3.81, 6.35, 8.89, 11.43, 13.97), "Perma-Proto Quarter terminal-strip rows, y of each (file coordinates; silk letters A to E at the five lower, F to J at the five upper): a 7.62 gap between E and F carries the mounting holes", PERMA + ": the 150 terminal-strip holes' y values", "sourced"),
    "permaproto_q_strips": ((5, 30), "Perma-Proto Quarter copper (bottom layer): holes per strip, strip count; each column is two separate 5-hole strips, one over rows A-E and one over rows F-J (30 strips, the two halves not joined), each running along y; nothing joins neighbouring columns", PERMA + ": 30 signals of five holes on one x each, bottom-layer wires between neighbours", "sourced"),
    "permaproto_q_rails": ((-21.59, -19.05, 19.05, 21.59), "Perma-Proto Quarter power rails: y of the four rails, each one continuous 15-hole strip along x (every column's hole in that row joined; no break in the middle); the outer pair beside each edge", PERMA + ": signals N$31, N$32, N$63, N$64, 14 contiguous bottom-layer segments each over the 15 holes", "sourced"),
    "permaproto_q_silk": (("A", "B", "C", "D", "E", "F", "G", "H", "I", "J"), "Perma-Proto Quarter printed row letters, in the order of permaproto_q_rows (A lowest y, J highest; printed beside both long edges, rotated 90 degrees) and column numbers 1 to 15 left to right (printed above and below the grid, upright). The four rails carry no letters: the rails at y -21.59 and 19.05 are the + rails (red silk line and a '+' beside each), the ones at y -19.05 and 21.59 the - rails (blue silk line, no text); this repo names them bot+, bot-, top+, top-", PERMA + ": tPlace text A-J at x -19.304 and 20.574, 1-15 at y 15.24 and -16.256; layer 112 (red) wires y -23.368 and 17.272, layer 113 (blue) wires y -17.272 and 23.368, '+' text on layer 112 at (-20.828, -24.638), (19.05, -24.638), (19.05, 16.002), (-20.828, 16.002)", "derived"),
    "permaproto_q_hole": ((1.2, 1.9304), "Perma-Proto Quarter plated hole drill and pad (annular) diameter, all 210 holes", PERMA + ": every via drill 1.2, diameter 1.9304, extent 1-16", "sourced"),
    "permaproto_q_mount": ((3.2, 17.78, 0.0), "Perma-Proto Quarter mounting holes: drill, x of the pair (at +-x), y (file coordinates; unplated)", PERMA + ": two <hole> entries drill 3.2 at (-17.78, 0) and (17.78, 0)", "sourced"),
    # ---------------------------------------------------------------- Adafruit SHT45 #6174 (TH pod)
    "sht45": ((25.4, 17.78), "SHT45 #6174 breakout outline, width x height (the PTFE-capped #6174 uses the SHT45 board; Adafruit's product page gives 25.5 x 17.7 x 4.8 overall); two 2.5 mm plated mounting holes at (2.54, 2.54), (22.86, 2.54), (2.54, 15.24), (22.86, 15.24)", SHT + ": Dimension layer 20, 0..25.4 x 0..17.78", "sourced"),
    "sht45_pins": (("VIN", "3Vo", "GND", "SCL", "SDA"), "SHT45 header pads, left to right as laid out (board net names VCC, 3.3V, GND, SCL, SDA)", SHT + ": element JP2 (1X05, pads 1-5)", "sourced"),
    "sht45_hdr": ((7.62, 2.54, 2.54), "SHT45 header: x of pad 1, y of the row, pitch (from the board's lower-left corner)", SHT + ": JP2 at (12.7, 2.54), pads at -5.08..+5.08", "sourced"),
    "sht45_pullup_k": (10.0, "SHT45 pull-ups, kohm: SDA and SCL on the header side each 10k to VIN (pad 1); the sensor side has its own 10k to 3.3 V behind a BSS138 level shifter; no jumper to cut them (the shifter's header side is what the pod sees)", SHT + " and its .sch: R3 RESPACK_4X0603 10K, pins 1-8 VCC-SCL, 3-6 VCC-SDA, 2-7 and 4-5 3.3V to the sensor-side lines", "sourced"),
    "sht45_addr": ("0x44", "SHT45 I2C address (fixed, cannot be changed)", "https://learn.adafruit.com/adafruit-sht40-temperature-humidity-sensor/pinouts: 'The I2C address is 0x44 and cannot be changed'; https://www.adafruit.com/product/6174", "sourced"),
    # ---------------------------------------------------------------- Adafruit BMP581 #6407 (baro pod)
    "bmp581": ((25.4, 17.78), "BMP581 #6407 breakout outline, width x height; 2.5 mm plated mounting holes at the four corners, as the SHT45; the repo README lists BMP580 #6413, not 6407: the .brd name says BMP581 and the layout is the same family", BMP + ": Dimension layer 20, 0..25.4 x 0..17.78", "sourced"),
    "bmp581_pins": (("VIN", "3Vo", "GND", "SCK", "SDO", "SDI", "CS", "INT"), "BMP581 header pads, left to right (board net names VCC, 3.3V, GND, SCK/SCL, SDO/ADR, SDI/SDA, CS, INT)", BMP + ": element JP1 (1X08, pads 1-8)", "sourced"),
    "bmp581_hdr": ((3.81, 2.54, 2.54), "BMP581 header: x of pad 1, y of the row, pitch (from the board's lower-left corner)", BMP + ": JP1 at (12.7, 2.54), pads at -8.89..+8.89", "sourced"),
    "bmp581_pullup_k": (10.0, "BMP581 pull-ups, kohm: SDA and SCL on the header side each 10k to VIN, sensor side 10k to 3.3 V behind a BSS138 shifter; CS has 10k to 3.3 V (I2C mode); no jumper to cut the I2C pull-ups", BMP + " and its .sch: R2 RESPACK_4X0603 10K (as the SHT45), R1 10K CS_3V to 3.3V", "sourced"),
    "bmp581_addr": ("0x47", "BMP581 default I2C address: SDO/ADR is pulled to 3.3 V by R4 (10k) and solder jumper SJ1 (SDO to GND) is open as shipped, so SDO high; closing SJ1 gives 0x46. The address for SDO high is the BMP5 datasheet's, not read from the Adafruit files", BMP + ": R4 10K SDO/ADR to 3.3V, SJ1 SOLDERJUMPER_ARROW_NOPASTE SDO/ADR-GND; SDO high = 0x47 per Bosch BMP581 datasheet (not downloaded)", "derived"),
    # ---------------------------------------------------------------- Adafruit LTR390 #4831 (UV pod)
    "ltr390": ((25.4, 17.78), "LTR390 #4831 breakout outline, width x height; 2.5 mm plated mounting holes at the four corners", LTR + ": Dimension layer 20, 0..25.4 x 0..17.78", "sourced"),
    "ltr390_pins": (("VIN", "3Vo", "GND", "SCL", "SDA", "INT"), "LTR390 header pads, left to right (board net names VCC, 3.3V, GND, SCL, SDA, INT)", LTR + ": element JP1 (1X06, pads 1-6)", "sourced"),
    "ltr390_hdr": ((6.35, 2.54, 2.54), "LTR390 header: x of pad 1, y of the row, pitch (from the board's lower-left corner)", LTR + ": JP1 at (12.7, 2.54), pads at -6.35..+6.35", "sourced"),
    "ltr390_pullup_k": (10.0, "LTR390 pull-ups, kohm: SDA and SCL on the header side each 10k to VIN, sensor side 10k to 3.3 V behind a BSS138 shifter; INT has 10k to 3.3 V; no jumper to cut the I2C pull-ups", LTR + " and its .sch: R3 RESPACK_4X0603 10K (as the SHT45), R2 10K INT to 3.3V", "sourced"),
    "ltr390_addr": ("0x53", "LTR390 I2C address (the chip has one fixed 7-bit address; the board has no address jumper). Not read from a downloaded Adafruit page: their learn pages did not render", "the pod spec (docs/superpowers/specs/2026-11-17-sensor-pods-design.md) and the LTR-390UV-01 datasheet (not downloaded); no address pad or jumper in " + LTR, "derived"),
    # ---------------------------------------------------------------- Adafruit 24LC32 STEMMA QT #5146 (ID EEPROM, one per pod)
    "eeprom_24lc32": ((25.4, 17.78), "24LC32 STEMMA QT #5146 breakout outline, width x height (the .brd outline sits at x -4.953..20.447, y -4.5085..13.2715; the same size as the other breakouts); 2.5 mm mounting holes at the four corners", EEP + ": Dimension layer 20; adafruit.com/product/5146 says 25.4 x 17.7 x 4.5", "sourced"),
    "eeprom_24lc32_pins": (("VIN", "3Vo", "GND", "SCL", "SDA", "WP"), "24LC32 header pads, left to right (board net names VCC, 3.3V, GND, SCL, SDA, WP)", EEP + ": element JP1 (1X06, pads 1-6)", "sourced"),
    "eeprom_24lc32_hdr": ((6.35, 2.54, 2.54), "24LC32 header: x of pad 1, y of the row, pitch (from the board's lower-left corner; the file has JP1 at (7.747, -1.9685), pads at -6.35..+6.35, on the outline's origin -4.953, -4.5085)", EEP + ": JP1 and the Dimension layer", "sourced"),
    "eeprom_24lc32_pullup_k": (10.0, "24LC32 board pull-ups, kohm: SDA and SCL on the header side each 10k to VIN, and the chip side 10k to 3.3 V behind a BSS138 shifter; no jumper to cut them", EEP + " and its .sch: R3 RESPACK_4X0603 10K (as the SHT45)", "sourced"),
    "eeprom_24lc32_addr": ("0x50", "24LC32 default I2C address: A0, A1, A2 each pulled to GND by 10k (R1 pack); solder jumpers SJ1-SJ3 (open as shipped) tie A2, A1, A0 to 3.3 V", EEP + ": R1 RESPACK_4X0603 10K, SJ1-SJ3 SOLDERJUMPER_ARROW_NOPASTE; the repo README: 'The default I2C address is 0x50'", "sourced"),
    "eeprom_24lc32_wp": ("floating", "24LC32 WP default on the board: the WP net runs only from header pad 6 (JP1) to the chip's pin 7; no pull-up, no pull-down, no resistor and no solder jumper on it, so it floats unless the header pad is wired. The pod must strap it (pod design: 2-pin header with a shunt, shunt on = protected, WP to 3.3 V). The CAT24C32's internal pull-down on WP is the chip's datasheet, not read", EEP + ": signal WP = JP1 pad 6, U1 pin 7, U3 pin 7 only (brd and sch); the 4th element of the R1 pack (N$1) only feeds the LED", "sourced"),
    # ---------------------------------------------------------------- the pod board's small parts (layout/pods.py)
    "jp1_hdr": ((2.54, 6.0, 0.64), "JP1 write-protect header, Sullins PRPC002SAAN-RC 2-pin vertical male header (inventory, DigiKey order 2026-11-09): plastic height, post above the plastic, post square. The plastic height is the TX hdr_plastic class of part; the post length and square are the common 0.1 in header's nominal, not read from Sullins' drawing", "INVENTORY.md (Sullins PRPC002SAAN-RC, 100 on order); not from a Sullins drawing: measure one", "TBD"),
    "shunt_spc02": ((5.08, 2.54, 6.0), "Sullins SPC02SYAN shunt (jumper cap) on JP1: length along the two posts, width, height above the header plastic. Nominal 0.1 in shunt size, not read from Sullins' drawing", "INVENTORY.md (Sullins SPC02SYAN, 100 on order); not from a Sullins drawing: measure one", "TBD"),
    "r1_body": ((6.3, 2.5), "R1 10 k WP pull-down, Yageo MFR-25FBF52-10K lying flat: body length x diameter (the DIN0207 class the TX's r_lying_h uses)", "INVENTORY.md (Yageo MFR-25FBF52-10K); KiCad R_Axial_DIN0207_L6.3mm_D2.5mm model, as the TX r_lying_h row; not from Yageo's drawing", "derived"),
    "mount_keep": (2.75, "radius around each Perma-Proto mounting hole kept free of parts: an M3 pan-head screw's head (ISO 7045 dk 5.5) so the screw can be driven after the parts are soldered", "ISO 7045 M3 head diameter 5.5, from the standard's table as remembered; the pod box (Task 6) picks the real screw", "TBD"),
    "th_lead_m": (0.5, "TH lead length, SHT45 header pads to the TH pod board (stranded 4-wire); the spec's estimate is 0.3 to 0.5 m, this row holds the upper end until the assembled shield and arm set it", "docs/superpowers/specs/2026-11-17-sensor-pods-design.md item 8 ('about 0.3-0.5 m')", "TBD"),
    # ---------------------------------------------------------------- the pods' gland, cable and I2C limits
    "pg7_seal": ((TX.val("gland_pg7")[4], TX.val("gland_pg7")[5]), "PG-7 #762 sealing range, cable OD min x max (a cable outside it gets a PG-9 at that end)", "tx-stack-r1/sources.py gland_pg7 (cable 0.118-0.169 in), " + TX.D["gland_pg7"][2], "derived"),
    "cable_max_m": (2.0, "longest cable run from pod to TX port", "Clint, 2026-11-17: docs/superpowers/specs/2026-11-17-sensor-pods-design.md (cable runs are under 2 m)", "sourced"),
    "cable_pf_per_m": (None, "capacitance per metre of the bought 6-conductor round cable (conductor to conductor, the SDA/SCL pair)", "[TBD-MEASURE]: the cable is not bought; take its datasheet figure or measure it with an LCR meter", "TBD"),
    "i2c_sink_ma": (3.0, "standard- and fast-mode I2C low-level output sink current the bus pull-ups must stay under (at VOL 0.4 V)", TI + ": 'Low-level output voltage (at 3 mA current sink)'", "sourced"),
    "rise_ns_max": (1000, "standard-mode I2C maximum SDA/SCL rise time (30 to 70 percent), ns", TI + ": tr 1000 ns standard mode (300 fast, 120 fast-plus)", "sourced"),
    # ---------------------------------------------------------------- the radiation shield (never committed)
    "shield_3mf": ((SHIELD, "c8a6f1bc66e94d516a0e3b6fd50ad338343281649da1c4f9df0fd2809695a768"), "Clint's Stevenson-screen radiation shield model: local path (outside git), sha256. Only the top cap (object_70) and the L-arm (object_72) are remixed. The file and everything derived from its meshes stay out of git", "~/Downloads/Stevenson_screen_NFS.3mf (Clint, 2026-11-17; sha256 taken from the file on 2026-11-17)", "sourced"),
}


def _row(key):
    return D[key] if key in D else TX.D[key]


def val(key):
    return _row(key)[0]


def tbd(key):
    return _row(key)[3] == "TBD"


def _fmt(v):
    if v is None:
        return "?"
    if isinstance(v, tuple):
        return " x ".join(_fmt(x) for x in v)
    return v if isinstance(v, str) else f"{v:g}"


def shield_path():
    """The shield 3MF's real local path (the table keeps the unexpanded ~/Downloads form)."""
    return Path(val("shield_3mf")[0]).expanduser()


def _is_length(v):
    vs = v if isinstance(v, tuple) else (v,)
    return all(x is None or (isinstance(x, (int, float)) and not isinstance(x, bool)) for x in vs)


def label(key):
    """Text for a drawing label: the value (with mm when it is a number), and the TBD flag when it is a placeholder."""
    v = val(key)
    s = "x".join(_fmt(x) for x in v) if isinstance(v, tuple) else _fmt(v)
    return s + (" mm" if _is_length(v) else "") + (" [TBD-MEASURE]" if tbd(key) else "")


def permaproto_q_holes():
    """All 210 plated holes of the Perma-Proto Quarter as (x, y, strip), file coordinates (origin at the board centre).
    strip is "A-E<col>" or "F-J<col>" (columns 1-15) for a 5-hole strip, "rail<y>" for a 15-hole rail."""
    n, pitch, x0 = val("permaproto_q_cols")
    rows = val("permaproto_q_rows")
    out = []
    for c in range(int(n)):
        x = round(x0 + c * pitch, 4)
        for i, y in enumerate(rows):
            out.append((x, y, f"{'A-E' if i < 5 else 'F-J'}{c + 1}"))
        for y in val("permaproto_q_rails"):
            out.append((x, y, f"rail{y:g}"))
    return out


def table():
    rows = ["| Key | Value | What | Source | Status |", "|---|---|---|---|---|"]
    for k, (v, what, src, st) in D.items():
        rows.append(f"| `{k}` | {_fmt(v)} | {what} | {src} | {'[TBD-MEASURE]' if st == 'TBD' else st} |")
    return "\n".join(rows)


BEGIN, END = "<!-- dimensions:begin (generated by sources.py) -->", "<!-- dimensions:end -->"


def sync_readme(check=False):
    p = HERE / "README.md"
    text = p.read_text()
    a, b = text.index(BEGIN) + len(BEGIN), text.index(END)
    new = text[:a] + "\n" + table() + "\n" + text[b:]
    if check:
        return new == text
    p.write_text(new)
    return True


if __name__ == "__main__":
    if "--check" in sys.argv:
        ok = sync_readme(check=True)
        print("README dimension table", "in step" if ok else "OUT OF STEP: run python3 sources.py")
        sys.exit(0 if ok else 1)
    sync_readme()
    print("README dimension table written")
