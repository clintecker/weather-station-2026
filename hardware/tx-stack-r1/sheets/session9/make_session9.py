"""Session 9: commission. Same flat-pack style and pipeline as Sessions 2-8.

Starting point: Session 8 is done. The box is loaded, the lid is off, the pack is unplugged from PG1 and JP17 is
out. This session unlocks and flashes the Wio-E5 mini over J3 (SWD), provisions it over its own USB-C, checks it
on USB power with no pack, puts the pack on, and checks the first frames on air. It ends with the box ready for
its lid and the mount (Session 8 page 14).

Source of truth, read below and asserted so the sheet breaks when they drift:
  firmware/board/wio-e5/README.md (SWD wiring, unlock, console), firmware/stage0-node/Makefile and
  firmware/board/stm32wl/rules.mk (build, flash, SHA-256), firmware/board/wio-e5/gen/board.mk (unlock),
  firmware/stage0-node/App/tx_console.c, app_tx.c, charger.c (what the console prints),
  firmware/stage0-node/README.md "Provision and run (host)", docs/runbook-moving-boards.md (the key rule),
  ws0/__main__.py (init, provision-node), docs/openapi.json (the API), docs/runbook-home-assistant.md,
  tools/e2e_check.py, hardware/tx-stack-r1/build/B3.md (J3), build/ASSEMBLY.md section 1 (JP17, J6).
Pictures: scenes9.py.

Usage: .venv-pdf/bin/python make_session9.py [OUT_DIR]     (default: ../out; writes session9-all.pdf)
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sheetlib import *          # noqa: F401,F403,E402
import sheetlib as SL           # noqa: E402

SL.LEADER_INK = True
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "out"
REPO = Path("/Users/clint/code/electronics/weather-station-2026")
FW = REPO / "firmware"


def rd(p):
    return (REPO / p).read_text()


# ------------------------------------------------------------------ facts the pages print, checked against the sources
MAKEFILE = rd("firmware/stage0-node/Makefile")
RULES = rd("firmware/board/stm32wl/rules.mk")
BOARDMK = rd("firmware/board/wio-e5/gen/board.mk")
WIO = rd("firmware/board/wio-e5/README.md")
NODE = rd("firmware/stage0-node/README.md")
CONSOLE = rd("firmware/stage0-node/App/tx_console.c")
APP = rd("firmware/stage0-node/App/app_tx.c")
CHARGER = rd("firmware/stage0-node/App/charger.c")
RADIO = rd("firmware/stage0-node/App/radio_cfg.h")
WSMP = rd("firmware/stage0-node/App/wsmp_host.c")
I2CH = rd("firmware/stage0-node/App/i2c_bus.h")
MAIN = rd("ws0/__main__.py")
MOVING = rd("docs/runbook-moving-boards.md")
HA = rd("docs/runbook-home-assistant.md")
E2E = rd("tools/e2e_check.py")
B3 = rd("hardware/tx-stack-r1/build/B3.md")
ASM = rd("hardware/tx-stack-r1/build/ASSEMBLY.md")
API = json.loads(rd("docs/openapi.json"))

BUILD = "make ROLE=tx BOARD=wio-e5 WS_POWER_PROFILE=3 WS_I2C_MUX=1"
assert BUILD in MAKEFILE and BUILD in WIO
assert "WS_BENCH_OLED, WS_POWER_PROFILE and WS_I2C_MUX are not remembered" in MAKEFILE
assert "BUILD      = build/$(ROLE)$(OLED_SUFFIX)$(BOARD_SUFFIX)" in MAKEFILE      # the flags are not in the path
assert "#define WS_I2C_MUX 0" in I2CH and "I2C_MUX_ADDR 0x71U" in I2CH           # no flag: the hub profile, no mux
assert "shasum -a 256 $@" in RULES and "connect_assert_srst" in RULES and "program $(TARGET).elf verify reset exit" in RULES
assert "interface/stlink.cfg" in RULES and "target/stm32wlx.cfg" in RULES
assert '"stm32l4x unlock 0" -c "stm32l4x option_load 0"' in BOARDMK
assert "make BOARD=wio-e5 unlock SERIAL=<serial>" in WIO and "RDP = AA" in WIO
assert "To be confirmed on the first board" in WIO and "To be confirmed on the hardware" in WIO
assert "USART1 on PB6 (TX) and PB7 (RX)" in WIO and "115200 8N1" in WIO
assert "The bus 3.3 V back-feeds the mini's AP2112" in rd("hardware/tx-stack-r1/README.md")
# no option-byte (brown-out) target yet: when one lands, page 04 must change
for mk in (MAKEFILE, RULES, BOARDMK):
    assert not re.search(r"^(bor|brownout|option)\w*\s*:", mk, re.M | re.I), "a BOR target landed: update page 04"
assert "Set the brown-out reset (BOR) level in the option bytes" in rd("docs/failure-modes.md")
# J3 (B3.md): column a, rows 12-16
J3 = [("1", "a12", "3.3 V", "VDD / VREF (TARGET SENSE)"), ("2", "a13", "SWDIO", "SWDIO"),
      ("3", "a14", "SWCLK", "SWCLK"), ("4", "a15", "NRST", "NRST (RESET)"), ("5", "a16", "GND", "GND")]
for pin, h, what, _ in J3:
    assert f"| {h} |" in B3, h
assert "soldered in column a rows 12-16" in B3
# the console lines
assert "#boot role=tx fw=%s reset=%s kat=%s freq=%u bw=%u sf=%u power=%d" in APP
assert "#unprovisioned: send PROVISION <station_id> <key>" in APP
assert "#status role=tx fw=%s reset=%s provisioned=%d station=%u kcv=%s kat=%s" in CONSOLE
assert "link=%s silent=%u energy=%s time=%s utc=%u uptime=%u meter_link=%s" in CONSOLE
assert "i2c_recoveries=%u i2c_stuck=%u mux_resets=%u" in CONSOLE and "#kat %s" in CONSOLE
assert '"ok", "cups-suspect", "vane-out-of-table", "cups-open", "rain-open"' in CONSOLE
assert '#sensor rain=%s' in CONSOLE
for k in (" present=", " ok=", " cells=", " vreg_mv=", " ichg_ma=", " iterm_ma=", " ts_pct=", " ts=", " stage=",
          " en_chg=", " hold=", " vbat_mv=", " ibat_ma=", " vbus_mv="):
    assert f'"{k}"' in CHARGER, k
assert '" air_th=", " pressure=", " uva=", " encl_th=", " battery=",' in WSMP
assert "#define WS_RF_FREQUENCY_HZ   915000000UL" in RADIO and "#define WS_TX_POWER_DBM      0" in RADIO
# provisioning, the key rule, the gateway
assert "python -m ws0 init --hardware --station station-01 --station-id 1 --directory" in NODE
assert "provision-node --directory run-hw --serial /dev/cu.usbmodem<TX port>" in NODE
assert "**After a WIPE, `init` a new run directory (a new key).**" in NODE
assert "Prefer a new key. A new key is never wrong." in MOVING
assert "Provisioned station" in MAIN and "refusing to overwrite" in MAIN and "'http_port':8088" in MAIN
assert "/v1/status" in API["paths"] and "/v1/observations/latest" in API["paths"]
assert "wind_dir_deg" in API["components"]["schemas"]["Observation"]["properties"]
assert "rain_tips" in API["components"]["schemas"]["Observation"]["properties"]
assert "--power-pending" in E2E and "e2e: all fields ok" in NODE
assert "Settings → Devices & services → MQTT" in HA and "mqtt-password" in HA
assert "**First power without the pack and with JP17 out** (charge disabled)" in ASM
assert "USB in is J6, micro-B" in ASM and "Then refit JP17 and connect the pack, last." in ASM

RX_SERIAL = "0016001E4142500E20353451"     # the RX NUCLEO's ST-LINK (install.sh default, stage0-node README)
OLD_TX = "003B00194142500E20353451"        # the NUCLEO that was the TX (runbook-moving-boards.md)
assert RX_SERIAL in NODE and OLD_TX in MOVING
RUN = "run-stack1"                         # any NEW directory name; run*/ stays out of git

SLOGANS9 = [
    "THE PACK GOES ON LAST.",
    "WS_I2C_MUX=1. EVERY TIME.",
    "A NEW KEY IS NEVER WRONG.",
    "READ THE LINE. WRITE THE NUMBER.",
]


# ------------------------------------------------------------------ helpers (Session 8's, plus code blocks)
def para(c, x, y, w, s_, size=9.3, lead=12.4, font="ALT", color=INK):
    """Wrap s_ to width w; returns the y under it."""
    out = []
    for block in s_.split("\n"):
        line = ""
        for wd in block.split():
            t = (line + " " + wd).strip()
            if SL.pdfmetrics.stringWidth(t, font, size) > w and line:
                out.append(line)
                line = wd
            else:
                line = t
        out.append(line)
    for i, ln in enumerate(out):
        text(c, x, y - i * lead, ln, size, font, color)
    LAB.block(x - 2, y - lead * len(out) + size * 0.3, x + w, y + size, "text")
    return y - lead * len(out)


def steps_list(c, x, y, w, items, size=9.3, lead=12.4, gap=4, start=1):
    """Numbered steps; wider than 400 pt, they go in two columns."""
    if w > 400 and len(items) > 2:
        k = (len(items) + 1) // 2
        cw = (w - 16) / 2
        y1 = steps_list(c, x, y, cw, items[:k], size, lead, gap, start)
        y2 = steps_list(c, x + cw + 16, y, cw, items[k:], size, lead, gap, start + k)
        return min(y1, y2)
    for i, s_ in enumerate(items):
        text(c, x, y, f"{i + start}.", size, "HEAD", INK)
        y = para(c, x + 14, y, w - 14, s_, size, lead) - gap
    return y


def check_item(c, x, y, s_, size=9.4, w=None):
    """A magenta 'CHECK' tag: a guess or an open doc fact, to confirm at the bench."""
    r = chip(c, x, y, "CHECK", 7.5, "HEAD", WHITE, "l", fill=NEON)
    if w:
        return para(c, r[2] + 6, y, w - (r[2] + 6 - x), s_, size, size * 1.3, "ALT", NEON)
    text(c, r[2] + 6, y, s_, size, "ALT", NEON)
    return y - 14


def in_model(c, x, y, s_, size=9.4, w=None):
    """A grey 'FROM THE CODE' tag: a fact the firmware or the docs settle, no bench check needed."""
    r = chip(c, x, y, "FROM THE CODE", 7.5, "HEAD", WHITE, "l", fill=GREY)
    if w:
        return para(c, r[2] + 6, y, w - (r[2] + 6 - x), s_, size, size * 1.3, "ALT", GREY)
    text(c, r[2] + 6, y, s_, size, "ALT", GREY)
    return y - 14


def wrap(s_, w, font, size):
    out, line = [], ""
    for wd in s_.split():
        t = (line + " " + wd).strip()
        if SL.pdfmetrics.stringWidth(t, font, size) > w and line:
            out.append(line)
            line = wd
        else:
            line = t
    return out + [line]


def note_box(c, x, y, w, title, lines, colour=NEON, fill="#FFE6F1", tsize=10.5, size=8.8):
    """A coloured box: a title, then each line wrapped to the box."""
    lead = size * 1.32
    rows = [r for s_ in lines for r in wrap(s_, w - 20, "ALT", size)]
    h = 16 + tsize + lead * len(rows)
    c.setStrokeColor(colour)
    c.setFillColor(HexColor(fill))
    lw(c, 2)
    c.rect(x, y - h, w, h, stroke=1, fill=1)
    text(c, x + 10, y - 4 - tsize, title, tsize, "HEAD", colour)
    for i, s_ in enumerate(rows):
        text(c, x + 10, y - 10 - tsize - size - lead * i, s_, size, "ALT", INK)
    LAB.block(x, y - h, x + w, y, "note box")
    return y - h


CODE_BG = HexColor("#1C1C1C")


def code(c, x, y, w, lines, size=9.4, note=None):
    """Lines to type (or to expect) on a dark strip, MONO, shrunk to fit w. Returns the y under it."""
    s = size
    while max(SL.pdfmetrics.stringWidth(l, "MONO", s) for l in lines) > w - 14 and s > 6.4:
        s -= 0.1
    lead = s * 1.38
    h = 8 + lead * len(lines)
    c.setFillColor(CODE_BG)
    c.rect(x, y - h, w, h, stroke=0, fill=1)
    for i, l in enumerate(lines):
        col = HexColor("#8A8A8A") if l.startswith("#  ") else (HAZ if l.startswith("$ ") else WHITE)
        text(c, x + 7, y - 4 - s * 0.9 - lead * i, l, s, "MONO", col)
    LAB.block(x, y - h, x + w, y, "code")
    return y - h


def expect(c, x, y, w, rows, size=9.6, kw=150):
    """Expected fields: (field, what it should say)."""
    for i, (k, v) in enumerate(rows):
        text(c, x, y - i * size * 1.5, k, size, "MONO", NEON)
        text(c, x + kw, y - i * size * 1.5, v, size, "ALT", INK)
    LAB.block(x, y - size * 1.5 * len(rows) + 6, x + w, y + 9, "expect")
    return y - size * 1.5 * len(rows)


def col_labels(c, a, items, x, side="l", size=8.6, gap=15, lo=None):
    """Chips in one column at x, each at its anchor's height, pushed apart in anchor order."""
    pts = []
    for it in items:
        px, py = a.A(it[0])
        pts.append([py - 3, px, py, it[1]])
    pts.sort(key=lambda p: -p[2])
    for i in range(1, len(pts)):
        pts[i][0] = min(pts[i][0], pts[i - 1][0] - gap)
    if lo is not None and pts and pts[-1][0] < lo:
        d = lo - pts[-1][0]
        for p_ in pts:
            p_[0] += d
    for yy, px, py, t in pts:
        r = chip(c, x, yy, t, size, "ALT", INK, side)
        leader(c, r, px, py)


def ring(c, x, y, r=4.2, w=1.6):
    """Hole marker that reads on the red card: hazard yellow on a black outline."""
    SL.HC.mark(x, y, "ring")
    c.setStrokeColor(INK)
    lw(c, w + 1.6)
    c.circle(x, y, r, stroke=1, fill=0)
    c.setStrokeColor(HAZ)
    lw(c, w)
    c.circle(x, y, r, stroke=1, fill=0)


def stand(c, g, rules):
    x, y, w, h = panel(c, g, None, "STANDING ORDERS.", warn=True)
    for i, s in enumerate(rules):
        yy = y + h - 12 - i * (h - 8) / len(rules)
        verdict(c, x + 20, yy, True, 9)
        text(c, x + 36, yy - 4, s, 8.6, "ALT", INK)


# ------------------------------------------------------------------ 00 cover: what you need
def cover(c, pg):
    page(c, "00", "SESSION 9: COMMISSION",
         "FLASH, PROVISION AND CHECK THE TX. LID OFF. THE PACK GOES ON NEAR THE END, NOT BEFORE.", pg, SLOGANS9[0])
    g = Grid(2, 3, heights=[1.5, 1.0, 0.55])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["Where you start: Session 8's box, lid off,",
                                            "the pack apart from PG1, JP17 out."])
    a = Art(c, "access", x + 40, y + 6, w - 128, h - 12, align="l")
    col_labels(c, a, [("usbc", "MINI USB-C\n(CONSOLE)"), ("j3", "J3 (SWD)"), ("B3_front", "B3 CORE"),
                      ("B4_front", "B4 POWER")], a.x + a.w + 6, lo=y + 14, gap=26)
    x, y, w, h = panel(c, g.cell(1, 0), None, "WHAT YOU NEED.")
    parts = [("AN ST-LINK", "the spare NUCLEO-WL55JC1's (the old TX,", f"serial {OLD_TX[:8]}...) or a standalone ST-LINK"),
             ("5 DUPONT LEADS", "female ends onto J3's pins", ""),
             ("USB-C CABLE", "the Mac to the Wio-E5 mini (console)", ""),
             ("2 A USB ADAPTER", "USB-C to micro-B cable into EVM J6", "(ASSEMBLY.md 1.6)"),
             ("THE GATEWAY MAC", "the repo, .venv, OpenOCD, the RX NUCLEO", f"(ST-LINK {RX_SERIAL[:8]}...)"),
             ("THE WEATHER METERS", "on their cables, plus a fan or a hand", "to spin the cups")]
    yy = y + h - 18
    for t, l1, l2 in parts:
        text(c, x + 14, yy, t, 11, "HEAD", INK)
        text(c, x + 14, yy - 11, l1, 8.4, "ALT", GREY)
        if l2:
            text(c, x + 14, yy - 21, l2, 8.4, "ALT", GREY)
        yy -= 36 if l2 else 26
    x, y, w, h = panel(c, g.cell(0, 1, 2), None, "THE STEPS. IN THIS ORDER.")
    steps = ["01  SWD: J3 TO THE PROBE", "02  ONE-TIME UNLOCK (RDP 1 TO 0)", "03  BUILD AND FLASH (RX, THEN TX)",
             "04  BROWN-OUT LEVEL (WAITS ON FIRMWARE)", "05  THE CONSOLE ON USB-C", "06  PROVISION: A NEW KEY",
             "07  SELF-TEST ON USB, NO PACK", "08  PACK ON: JP17, THEN PG1", "09  FIRST FRAMES ON AIR",
             "10  REPORT"]
    half = (len(steps) + 1) // 2
    for i, s in enumerate(steps):
        col, row = divmod(i, half)
        text(c, x + 14 + col * w / 2, y + h - 18 - row * (h - 14) / half, s, 12, "HEAD", INK)
    stand(c, g.cell(0, 2, 2), [
        "THE PACK STAYS OFF PG1 AND JP17 STAYS OUT UNTIL PAGE 08. CHARGER MUST SHOW VREG 4200, ICHG 900 FIRST.",
        "POWER THE STACK FROM EVM J6 FIRST, THEN THE MINI'S USB-C. NEVER THE MINI'S USB-C ALONE.",
        "EVERY BUILD AND FLASH LINE CARRIES WS_POWER_PROFILE=3 WS_I2C_MUX=1. NO EXCEPTIONS."])


# ------------------------------------------------------------------ 01 SWD wiring
def swd(c, pg):
    page(c, "01", "SWD: J3 TO THE PROBE", "B3.md: J3 IN COLUMN A, ROWS 12-16. PINS FLAT TOWARD THE FRONT EDGE. LID OFF.",
         pg, SLOGANS9[3])
    g = Grid(2, 2, heights=[1.15, 1.0])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, [
        "B3 CORE, TOP FACE (Session 5's drawing). J3's five pins in A12-A16, at the front edge. The Dupont housings push",
        "on past the edge with the lid off. The mini's USB-C is at its left end: that's the console (page 05)."])
    a = Art(c, "t_mini", x + 40, y + 6, w - 200, h - 12, align="l")
    for _, h_, _, _ in J3:
        ring(c, *a.A(h_.upper()))
    col_labels(c, a, [(h_.upper(), f"{h_.upper()}  J3.{p}  {what}") for p, h_, what, _ in J3],
               a.x + a.w + 14, gap=16, lo=y + 14)
    ux, uy = a.A("A1:usb")
    label(c, x + 14, uy + 26, "USB-C\n(CONSOLE)", ux, uy, 9)

    x, y, w, h = panel(c, g.cell(0, 1, 2), 2, [
        "Five leads, one per signal, matched by the names printed on the probe. The target is powered from the stack",
        "(EVM J6), so the probe's 3.3 V lead only senses it. connect_assert_srst in the flash rule needs the NRST lead."])
    # the wiring drawing: probe on the left, J3 on the right
    px0, py0 = x + 30, y + h - 26
    bw, bh, rowh = 150, 22, 24
    text(c, px0, py0 + 4, "THE PROBE (ST-LINK)", 11, "HEAD", INK)
    jx = x + w - 30 - bw
    text(c, jx, py0 + 4, "J3 ON B3", 11, "HEAD", INK)
    LAB.block(px0, py0, x + w - 30, py0 + 16, "heads")
    colours = [HexColor("#D7262E"), HexColor("#2E9E4F"), HexColor("#F2C318"), HexColor("#7A4FD0"), INK]
    for i, (pin, h_, what, probe) in enumerate(J3):
        yy = py0 - 14 - i * rowh
        c.setStrokeColor(INK)
        c.setFillColor(WHITE)
        lw(c, 1.2)
        c.rect(px0, yy - 7, bw, bh - 4, stroke=1, fill=1)
        text(c, px0 + 8, yy, probe, 9, "ALT", INK)
        c.setFillColor(WHITE)
        c.rect(jx, yy - 7, bw, bh - 4, stroke=1, fill=1)
        text(c, jx + 8, yy, f"PIN {pin}  {h_.upper()}  {what}", 9, "ALT", INK)
        c.setStrokeColor(colours[i])
        lw(c, 2.4)
        c.line(px0 + bw, yy + 2, jx, yy + 2)
        c.setFillColor(colours[i])
        c.circle(px0 + bw, yy + 2, 2.4, stroke=0, fill=1)
        c.circle(jx, yy + 2, 2.4, stroke=0, fill=1)
    yb = py0 - 14 - 5 * rowh
    LAB.block(px0, yb, x + w - 30, py0, "wiring")
    yb = check_item(c, x + 14, yb - 8, "The NUCLEO-WL55JC1 (MB1389, STLINK-V3E) as an external probe: nobody has found "
                    "the setting that cuts its own STM32WL off the SWD lines, or the connector that brings them out "
                    "(wio-e5 README). Find both on the board and in the MB1389 schematic before you wire, or use a "
                    "standalone ST-LINK. The Makefile uses OpenOCD's interface/stlink.cfg, so it must be an ST-LINK.",
                    w=w - 28)
    in_model(c, x + 14, yb - 6, "Lead colours are whatever you have: the drawing's colours are only to tell them apart.",
             w=w - 28)


# ------------------------------------------------------------------ 02 unlock
def unlock(c, pg):
    page(c, "02", "ONE-TIME UNLOCK: RDP 1 TO 0", "SEEED SHIPS THE MODULE LOCKED (RDP LEVEL 1). ONCE PER NEW BOARD.",
         pg, SLOGANS9[3])
    g = Grid(1, 2, heights=[1.25, 0.75])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "From firmware/stage0-node on the gateway Mac. SERIAL is the probe's ST-LINK serial",
        "(.venv/bin/python -m serial.tools.list_ports -v lists it as SER=...)."])
    yy = note_box(c, x + 40, y + h - 10, w - 50, "NOT YET RUN ON A REAL BOARD", [
        "The wio-e5 README marks this 'to be confirmed on the first board'. It's written from the OpenOCD 0.12.0 manual.",
        "Write down exactly what OpenOCD prints, good or bad. It goes on the report (page 10)."])
    yy = steps_list(c, x + 44, yy - 16, w - 56, [
        "Power: the 2 A adapter into EVM J6. No pack, JP17 out. The mini's USB-C can stay out for now.",
        "Probe on J3 (page 01), probe's USB into the Mac."], 10.2, 13.4)
    yy = code(c, x + 44, yy - 4, w - 56, [
        "$ cd firmware/stage0-node",
        f"$ make BOARD=wio-e5 unlock SERIAL={OLD_TX}",
        "#  runs: init, reset halt, stm32l4x unlock 0, stm32l4x option_load 0, shutdown (gen/board.mk)"])
    yy = steps_list(c, x + 44, yy - 14, w - 56, [
        "The option load resets the chip. OpenOCD may then report a lost connection. That's expected.",
        "Taking RDP back to 0 mass-erases the flash. Seeed's AT firmware is gone after this, for good.",
        "Swap in the probe's own serial if you're not using the old TX NUCLEO."], 9.3, start=3)
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["If it fails: STM32CubeProgrammer does the same thing (wio-e5 README)."])
    sw = w * 0.56
    a = Art(c, "t_swd_iso", x + sw + 10, y + 6, w - sw - 16, h - 12)
    label(c, x + sw + 14, y + h - 14, "J3: THE PROBE LEADS STAY ON", *a.A("J3:tip"), 9)
    steps_list(c, x + 44, y + h - 18, sw - 50, [
        "STM32CubeProgrammer, connect over the same ST-LINK (mode: under reset, since NRST is wired).",
        "Option bytes, Read Out Protection: set RDP to AA, Apply. The chip mass-erases the same way.",
        "Write down which way worked. Then go on to page 03: the build and flash don't change."], 10.2, 13.4)


# ------------------------------------------------------------------ 03 build and flash
def flash(c, pg):
    page(c, "03", "BUILD AND FLASH: RX, THEN TX", "ONE TREE, ONE RELEASE, BOTH BOARDS (RUNBOOK-MOVING-BOARDS.MD). THEN THE TX.",
         pg, SLOGANS9[1])
    g = Grid(1, 2, heights=[1.1, 0.9])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "Stop the gateway first: only one process can hold the RX port.", "Archive the old run directory: its key is retired."])
    yy = code(c, x + 10, y + h - 28, w - 20, [
        "$ tools/deploy/macos/install.sh uninstall        # stop the old gateway",
        "$ cd firmware/stage0-node",
        f"$ make ROLE=rx flash SERIAL={RX_SERIAL}",
        "#  the RX NUCLEO, through its own ST-LINK",
        f"$ {BUILD}",
        "#  look for: flash budget (tx, wio-e5, profile 3, mux 1): ...  and the SHA-256 line",
        "$ shasum -a 256 build/tx-wio-e5/stage0-tx.bin",
        f"$ {BUILD} flash SERIAL={OLD_TX}"])
    yy = steps_list(c, x + 44, yy - 16, w - 56, [
        "The budget line has to say 'profile 3, mux 1'. If it doesn't, stop: the flags didn't go in.",
        "Write down the SHA-256 the build printed (the first 8 characters do). The shasum line before the "
        "flash must print the same.",
        "OpenOCD programs the .elf, reads it back (verify) and resets the board. It must end without an error.",
        "Using another probe? Its serial goes after SERIAL= instead."], 10.2, 13.4)
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "The Makefile: 'WS_BENCH_OLED, WS_POWER_PROFILE and WS_I2C_MUX are not remembered'. The build",
        "directory is build/tx-wio-e5 whatever the flags, so a bare flash line rebuilds without them."])
    yy = note_box(c, x + 40, y + h - 6, w - 50, "WS_I2C_MUX=1 IS NOT REMEMBERED.", [
        "Type the full line every time: make ... WS_POWER_PROFILE=3 WS_I2C_MUX=1 flash SERIAL=...",
        "Leave WS_I2C_MUX=1 off and the firmware builds for the hub profile (WS_I2C_MUX 0, i2c_bus.h): no mux at 0x71,",
        "no channel select. The pods sit behind the mux, so MODULES shows EVERY POD ABSENT (air_th, pressure, uva).",
        "Leave WS_POWER_PROFILE=3 off and there's no charger code: CHARGER prints '#charger not-fitted'.",
        "Seen either? Nothing is broken. Flash again with the full line."], tsize=20, size=10)
    in_model(c, x + 14, yy - 16, "Each object keeps a .flags file and rebuilds when its flags change (rules.mk), so the "
             "full line always gives the right image; the short one always gives the wrong one.", w=w - 28)


# ------------------------------------------------------------------ 04 brown-out (BOR)
def bor(c, pg):
    page(c, "04", "BROWN-OUT LEVEL: WAITS ON FIRMWARE", "OPTION BYTES OVER J3. NO MAKE TARGET FOR IT YET (CHECKED 2026-11-22).",
         pg, SLOGANS9[3])
    g = Grid(1, 2, heights=[1.0, 1.0])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["docs/failure-modes.md, 'No low-voltage inhibit'."], warn=True)
    c.setFillColor(HexColor("#FFF6C8"))
    c.setStrokeColor(INK)
    lw(c, 2.4)
    bx_, by_, bw_, bh_ = x + 30, y + 24, w - 60, h - 40
    c.rect(bx_, by_, bw_, bh_, stroke=1, fill=1)
    text(c, bx_ + bw_ / 2, by_ + bh_ - 44, "WAITS ON FIRMWARE", 40, "HEAD", INK, "c")
    LAB.block(bx_, by_, bx_ + bw_, by_ + bh_, "waits box")
    lines = ["Nothing in stage0-node/Makefile, board/stm32wl/rules.mk or wio-e5/gen/board.mk sets the",
             "brown-out reset (BOR) level yet. failure-modes.md lists the fix: set the BOR level in the option",
             "bytes, and don't start a journal write or a transmission below a measured voltage.",
             "Skip this step today. When the target lands it's one make line with SERIAL=, over these same",
             "J3 leads, and this page gets that line."]
    for i, s_ in enumerate(lines):
        text(c, bx_ + 20, by_ + bh_ - 70 - i * 14, s_, 9.6, "ALT", INK)
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["What it's for, so you know what you're missing until then."])
    yy = steps_list(c, x + 44, y + h - 18, w - 56, [
        "At dawn, weak sun can start the board and a radio burst can drop it again: brown-out cycling "
        "(failure-modes.md section 6). Each boot takes a new epoch; nothing is lost, but it can repeat many times.",
        "A brown-out reads as reset=power today, not 'brownout' (App/watchdog.c). The boot count since power-up "
        "stays at 1. So a cycling board looks like a string of power-ons.",
        "Until the BOR target lands, the pack (1S3P, about 98 h at 0.25 W) is the margin. Keep it charged."], 10.2, 13.4)
    check_item(c, x + 14, yy - 10, "Which BOR level to set isn't decided anywhere in the repo yet. That's for the firmware "
               "change, not for the bench.", w=w - 28)


# ------------------------------------------------------------------ 05 console
def console(c, pg):
    page(c, "05", "THE CONSOLE ON THE MINI'S USB-C", "USART1 (PB6/PB7) TO THE MINI'S OWN USB-UART BRIDGE. 115200 8N1.",
         pg, SLOGANS9[3])
    g = Grid(1, 2, heights=[0.8, 1.2])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["J6 first (the stack's power), then the USB-C cable from the Mac into the mini."])
    yy = steps_list(c, x + 44, y + h - 18, w - 56, [
        "Plug the 2 A adapter into EVM J6 if it isn't already. Then the USB-C cable into the mini's USB-C "
        "(page 01 shows where).",
        "Find the port: run the list before and after you plug in. The new entry is the mini."], 10.2, 13.4)
    yy = code(c, x + 44, yy - 4, w - 56, [
        "$ .venv/bin/python -m serial.tools.list_ports -v",
        "$ .venv/bin/python -m serial.tools.miniterm /dev/cu.<the mini's port> 115200      # Ctrl-] quits"])
    check_item(c, x + 14, yy - 12, "The mini's USB-UART bridge chip isn't named in the repo, so the port's name "
               "(usbserial-..., wchusbserial-...) and whether it has a serial number (tools/console.py needs one) are "
               "for the bench. Write the name down.", w=w - 28)
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "Press RESET on the mini (or replug J6) to see the boot. A fresh board isn't provisioned yet, so it stops here:",
        "no modules, no radio. That's right. Page 06 provisions it."])
    yy = code(c, x + 10, y + h - 28, w - 20, [
        "#boot role=tx fw=<git describe> reset=pin kat=pass freq=915000000 bw=2 sf=7 power=0",
        "#status role=tx fw=... reset=pin provisioned=0 ... kat=pass epoch=... next_seq=...",
        "#counts pending=0 lost=0 ... i2c_recoveries=0 i2c_stuck=0 mux_resets=...",
        "#timing state=...",
        "#unprovisioned: send PROVISION <station_id> <key>"], size=8.6)
    yy = expect(c, x + 20, yy - 18, w - 40, [
        ("kat=pass", "the AES self-test passed. kat=FAIL: stop and send the line."),
        ("fw=", "the same git describe as the build (a -dirty suffix means uncommitted changes)"),
        ("freq=915000000", "915 MHz, bandwidth code 2 (500 kHz), SF7 (App/radio_cfg.h)"),
        ("power=0", "0 dBm: the bench setting in radio_cfg.h, fine across a room"),
        ("reset=", "pin after the RESET button, power after a replug")], kw=110)
    yy = check_item(c, x + 14, yy - 6, "The board sleeps between jobs and wakes on a start bit (EXTI 26). If a command "
                    "gets no reply, send it again (open hardware check 3 in the wio-e5 README).", w=w - 28)
    in_model(c, x + 14, yy - 10, "Mini back-feed: J6 powers the 3.3 V bus, and with USB-C in the mini's AP2112 runs in "
             "parallel. Accepted (README, electrical m3).", w=w - 28)


# ------------------------------------------------------------------ 06 provision
def provision(c, pg):
    page(c, "06", "PROVISION: A NEW RUN DIRECTORY, A NEW KEY", "STAGE0-NODE README 'PROVISION AND RUN'. RUNBOOK-MOVING-BOARDS.MD.",
         pg, SLOGANS9[2])
    g = Grid(1, 2, heights=[1.25, 0.75])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "Quit miniterm first: provision-node needs the port to itself. From the repo root on the gateway Mac."])
    yy = code(c, x + 10, y + h - 28, w - 20, [
        f"$ .venv/bin/python -m ws0 init --hardware --station station-01 --station-id 1 --directory {RUN}",
        f"#  Created {RUN}; secrets stay in gateway.json",
        f"$ .venv/bin/python -m ws0 provision-node --directory {RUN} --serial /dev/cu.<the mini's port>",
        "#  Gateway node-counter high-water mark: none (no gateway state yet)",
        "#  Provisioned station 1 (kcv <6 hex>); node says:  ...  then the board reboots, provisioned"])
    yy = expect(c, x + 20, yy - 18, w - 40, [
        ("station-01, ID 1", "the station Home Assistant already knows: same device, same entities"),
        ("epoch floor", f"provision-node works it out from {RUN}'s database: a new directory gives 0"),
        ("kcv", "write it on the report. STATUS on the TX shows the same kcv=... from now on"),
        (RUN, "any NEW name. Never an old run directory, never an evidence directory")], kw=118)
    yy = steps_list(c, x + 44, yy - 10, w - 56, [
        "Rain gauge: it can't be detected, so tell the board it's fitted. In miniterm type SENSOR rain on and "
        "look for '#sensor rain=on'. '#error busy ... retry' means a radio exchange was running: type it again.",
        f"{RUN}/ holds the key. Git ignores run*/. It moves only by a private route, never git, chat or email."], 10.2, 13.4)
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["The key rule (runbook-moving-boards.md): use a key only with a counter "
                                            "that only goes up."], warn=True)
    steps_list(c, x + 44, y + h - 18, w - 56, [
        "This board was mass-erased by the unlock, so it's unprovisioned: no WIPE needed today.",
        "Provisioning again later (a second try, a reflash)? On the TX console: WIPE ERASE-ALL-NODE-STATE. The board "
        "reboots. Then ws0 init a NEW directory and provision-node with that. Never re-use the old key.",
        "provision-node refuses a board that's already provisioned ('refusing to overwrite'). That's the cue to WIPE.",
        "PROVISION refused with '#error journal-not-empty (WIPE first)': WIPE, then provision again."], 10.2, 13.4)


# ------------------------------------------------------------------ 07 self-test
def selftest(c, pg):
    page(c, "07", "SELF-TEST ON USB, NO PACK", "J6 AND THE MINI'S USB-C IN. NO PACK ON PG1. JP17 STILL OUT. CONSOLE OPEN.",
         pg, SLOGANS9[3])
    g = Grid(2, 2, heights=[1.12, 0.88])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, [
        "Give it two minutes after the reboot: the modules go probing, identifying, admitted, active. Then type each",
        "command and tick what it shows. The values are from the console code (tx_console.c, charger.c, wsmp_host.c)."])
    cw = (w - 64) / 2
    lx, rx = x + 44, x + 54 + cw
    text(c, lx, y + h - 16, "STATUS  (THREE LINES: #status, #counts, #timing)", 10, "HEAD", INK)
    yy = expect(c, lx, y + h - 32, cw, [
        ("provisioned=1", "station=1, kcv= your page 06 value"),
        ("kat=pass", "KAT on its own prints '#kat pass'"),
        ("meter_link=ok", "worst of wind and rain (below)"),
        ("i2c_recoveries=0", "in #counts: no stuck-bus recovery"),
        ("i2c_stuck=0", "no recovery that left SDA low"),
        ("mux_resets=1", "the boot pulse only; more = a fault"),
        ("check_fails=0", "no run-time check failed")], size=8.8, kw=104)
    text(c, rx, y + h - 16, "MODULES  (ONE #modules LINE, THEN #ident LINES)", 10, "HEAD", INK)
    yy2 = expect(c, rx, y + h - 32, cw, [
        ("air_th=active", "S1 (J11): the SHT45 pod, mux ch 0"),
        ("uva=active", "S2 (J12): the LTR390 pod, mux ch 1"),
        ("pressure=active", "S3 (J13): the BMP581 pod, mux ch 2"),
        ("encl_th=active", "the SHTC3 on B3 (0x70)"),
        ("wind=active", "the cups and vane, J21"),
        ("rain=active", "J22, after SENSOR rain on"),
        ("battery= rails=", "base-board modules: always present")], size=8.8, kw=104)
    yy = min(yy, yy2)
    check_item(c, x + 12, yy - 8, "mux_ok isn't printed anywhere on the console. Three pods active and mux_resets=1 "
               "is the mux check. The 'resets = 1 after boot' reading comes from i2c_bus.h's comment.", w=w - 24)
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["CHARGER (one #charger line). No pack yet."])
    yy = expect(c, x + 40, y + h - 16, w - 46, [
        ("present=1 ok=1", "it answers at 0x6B"),
        ("cells=1", "REG0x0A: one cell"),
        ("vreg_mv=4200", "charge voltage set"),
        ("ichg_ma=900", "charge current set"),
        ("iterm_ma=80", "termination, 40 mA steps"),
        ("ts=NORMAL", "thermistor band"),
        ("hold=none", "nothing holding charge off"),
        ("ts_pct=", "write it down (report)")], size=9.4, kw=100)
    x, y, w, h = panel(c, g.cell(1, 1), 3, ["A pod in the wrong port reads absent."])
    yy = steps_list(c, x + 44, y + h - 18, w - 56, [
        "J6 and USB-C out. Swap the S1 and S2 plugs at J11 and J12.",
        "Power back (J6, then USB-C). Two minutes, then MODULES: air_th=absent, uva=absent.",
        "Power off, plugs back, power on, MODULES: all active again."], 9.6, lead=12.6)
    check_item(c, x + 14, yy - 6, "If it reads refused or type_conflict instead of absent, write down the exact line.",
               w=w - 28)


# ------------------------------------------------------------------ 08 pack on
def pack_on(c, pg):
    page(c, "08", "PACK ON: JP17, THEN PG1, LAST", "ASSEMBLY.md 1.7. ONLY AFTER PAGE 07'S CHARGER LINE READ RIGHT.",
         pg, SLOGANS9[0])
    g = Grid(2, 2, heights=[1.05, 0.95])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["EVM top face (Session 7's drawing).", "JP17 goes back on."])
    a = Art(c, "evm_done", x + 6, y + 6, w - 96, h - 12, align="l")
    col_labels(c, a, [("JP17", "JP17: REFIT"), ("J6", "J6 (USB 5 V)"), ("J7", "J7 (RT1)")], a.x + a.w + 6, lo=y + 14)
    x, y, w, h = panel(c, g.cell(1, 0), 2, ["The pack's JST PH into PG1."])
    a = Art(c, "pack_pg1", x + 8, y + 40, w - 16, h - 52)
    label(c, x + 14, y + 22, "PG1: THE LAST PLUG IN", *a.A("pg1"), 9)
    x, y, w, h = panel(c, g.cell(0, 1, 2), 3, [
        "BQ25798 charges at up to 0.9 A from J6; 'stage' is REG1C's charge state by name (charger.c)."])
    yy = steps_list(c, x + 44, y + h - 18, w - 56, [
        "Everything off: the mini's USB-C out, then J6 out.",
        "Refit JP17 on the EVM.",
        "Plug the pack into PG1. It's the last connection in the box. The TX starts on the pack.",
        "J6 back in, then the mini's USB-C, then miniterm. Type CHARGER."], 10.2, 13.4)
    yy = expect(c, x + 58, yy - 8, w - 70, [
        ("en_chg=1 hold=none", "charge allowed: the pack's thermistor reads NORMAL (ts=NORMAL)"),
        ("stage=cc", "or precharge, cv, topoff or terminated: all fine, depends how full the pack is"),
        ("ibat_ma=", "above 0 while it charges (write it down); vbat_mv= the pack's voltage"),
        ("STATUS, MODULES", "same as page 07. battery= now reads real numbers")], size=8.6, kw=110)
    check_item(c, x + 14, yy - 8, "Optional, if there's sun: J6 out, panel uncovered. CHARGER vbus_mv should read the "
               "panel's voltage and ibat_ma above 0. Write both down.",
               w=w - 28)


# ------------------------------------------------------------------ 09 on air
def on_air(c, pg):
    page(c, "09", "FIRST FRAMES ON AIR", "THE RX NUCLEO ON THE GATEWAY MAC, WS0 SERVE ON THE NEW DIRECTORY, HOME ASSISTANT.",
         pg, SLOGANS9[3])
    g = Grid(1, 2, heights=[1.05, 0.95])
    x, y, w, h = panel(c, g.cell(0, 0), 1, [
        "MQTT: runbook-home-assistant.md steps 2-3 for the new directory. The password goes in the file, never in chat."])
    yy = code(c, x + 10, y + h - 28, w - 20, [
        f"#  in {RUN}/gateway.json:",
        "#  \"mqtt\": {\"enabled\": true, \"host\": \"<broker>\", \"port\": 1883, \"tls\": false, \"username\": \"<user>\"}",
        f"$ ( umask 077; printf '%s\\n' '<password>' > {RUN}/mqtt-password )",
        f"$ tools/deploy/macos/install.sh install {RUN} {RX_SERIAL}",
        f"$ export WS0_API_TOKEN=<api_token from {RUN}/gateway.json>",
        "$ curl -s -H \"Authorization: Bearer $WS0_API_TOKEN\" http://127.0.0.1:8088/v1/status",
        "$ .venv/bin/python tools/e2e_check.py --power-pending"])
    yy = expect(c, x + 20, yy - 18, w - 40, [
        ("TX STATUS", "link=linked time=synchronized utc=<now>: the ACKs carry the time"),
        ("TX #counts", "sent= and acked= climb each minute, no_ack= stays near 0, pending=0"),
        ("/v1/status", "alarm: null; accepted_this_process climbs; latest has a reading"),
        ("e2e_check", "'e2e: all fields ok'. Rails this stack doesn't measure show pending: expected"),
        ("Home Assistant", "Settings > Devices & services > MQTT > station-01: entities update")], kw=104)
    x, y, w, h = panel(c, g.cell(0, 1), 2, [
        "The meters, read back through the gateway: /v1/observations/latest, a fresh reading each minute.",
        "Wind direction needs the cups turning: with the cups still it's calm and the direction is null."])
    yy = steps_list(c, x + 44, y + h - 18, w - 56, [
        "Rain: tip the bucket by hand 5 times. Next minute, rain_tips is 5 higher (it counts since boot).",
        "Cups: spin them, or a fan on them, for a whole minute. wind_speed_ms above 0, wind_gust_ms at or above it.",
        "Vane: fan on the cups, hold the vane still for a minute, read wind_dir_deg. Turn it a quarter turn, "
        "repeat, four times. Each reading moves about 90 degrees the same way round.",
        "STATUS meter_link=ok through all of it. cups-open, rain-open, cups-suspect or vane-out-of-table: "
        "check that meter's 6P plug (Session 8 page 11), then send the line."], 10.2, 13.4)
    check_item(c, x + 14, yy - 6, "Which vane position the firmware calls 0 degrees, against true north, is a mounting "
               "job, not today's. Today only the steps matter.", w=w - 28)


# ------------------------------------------------------------------ 10 report
REPORT_ROWS = [("PROBE USED, NUCLEO CONNECTOR", "WRITE", "page 01: what you plugged into, if the NUCLEO"),
               ("UNLOCK: MAKE OR CUBEPROGRAMMER", "WRITE", "page 02, and what OpenOCD printed"),
               ("TX IMAGE SHA-256 (FIRST 8)", "HEX", "page 03, and the budget line said profile 3, mux 1"),
               ("CONSOLE PORT NAME", "WRITE", "page 05: /dev/cu.<...>"),
               ("KCV", "HEX", "page 06, the same on STATUS"),
               ("MODULES ALL ACTIVE / WRONG PORT ABSENT", "Y / Y", "page 07"),
               ("CHARGER TS_PCT, NO PACK", "%", "page 07"),
               ("IBAT_MA ON THE PACK", "mA", "page 08 (and solar vbus_mv, if sun)"),
               ("TIME=SYNCHRONIZED, E2E ALL OK", "Y / N", "page 09"),
               ("RAIN 5 TIPS, VANE 4 STEPS", "Y / N", "page 09")]


def report(c, pg):
    page(c, "10", "REPORT THE COMMISSION.", "SEND THE NUMBERS. THEN THE LID GOES ON.", pg, SLOGANS9[3])
    g = Grid(1, 2, heights=[1.62, 0.38])
    x, y, w, h = panel(c, g.cell(0, 0), 1, ["Send these to Claude. They close the CHECK items on pages 01-09."])
    for i, (lab, unit, exp) in enumerate(REPORT_ROWS):
        yy = y + h - 22 - i * (h - 16) / len(REPORT_ROWS)
        text(c, x + 44, yy, lab, 12, "HEAD", INK)
        c.setStrokeColor(NEON)
        lw(c, 1.8)
        c.rect(x + 330, yy - 8, 110, 22, stroke=1, fill=0)
        text(c, x + 448, yy, unit, 11, "HEAD", INK)
        text(c, x + 44, yy - 11, exp, 8.3, "MONO", GREY)
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["Next: close the box (Session 8 page 14, the lid and the mount)."])
    for i, s_ in enumerate(["SWD leads off J3, USB-C off the mini, J6 out. The pack stays on PG1: the TX runs on it.",
                            "The lid on with its four printed bolts, then the mount, glands down.",
                            "Brown-out level (page 04): when the firmware lands, lid off, J3, one make line."]):
        text(c, x + 44, y + h - 22 - i * 15, "-  " + s_, 9.6, "ALT", INK)


PAGES = [cover, swd, unlock, flash, bor, console, provision, selftest, pack_on, on_air, report]
HOLE_ISSUES = []


def build(path, fns):
    cv = canvas.Canvas(str(path), pagesize=(W, H))
    cv.setTitle("Session 9: commission")
    cv.setAuthor("TX-STACK-R1")
    issues = 0
    for i, fn in enumerate(fns):
        fn(cv, i + 1)
        n = LAB.check()
        issues += len(n)
        hi = SL.HC.check(i + 1)
        for m in hi:
            print("  HOLE", m)
        HOLE_ISSUES.extend(hi)
        SL.HC.reset()
        cv.showPage()
    cv.save()
    return issues


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    bad = build(OUT / "session9-all.pdf", PAGES)
    print("ok", len(PAGES), "pages,", bad, "label issues,", len(HOLE_ISSUES), "hole-alignment issues", SL.HC.STATS)
    if bad or HOLE_ISSUES:
        sys.exit("BUILD FAILED: label issues or hole callouts off their holes")
