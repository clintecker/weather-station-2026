"""One-page block diagram of the TX stack (power tree, I2C tree with the mux, meter lines, radio path).
Labels come from model.py, so part numbers, addresses and MCU pins stay in step with the schematic; the
drawing asserts every net it names exists in the model. python3 blockdiag.py -> ../drawings/block-diagram.svg
"""
import html
from pathlib import Path

import model

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "drawings" / "block-diagram.svg"
P = {p["ref"]: p for p in model.PARTS}
F = model.MCU_FUNCTION
items = []


def esc(s):
    return html.escape(str(s), quote=True)


def need(*nets):
    for n in nets:
        assert n in model.NETS, f"block diagram names net {n} that model.py lacks"


def box(x, y, w, h, title, lines=(), fill="#eef3fa", stroke="#2b4a77", board=None):
    items.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
    items.append(f'<text x="{x + 8}" y="{y + 18}" font-size="13" font-weight="bold">{esc(title)}</text>')
    if board:
        items.append(f'<text x="{x + w - 6}" y="{y + 18}" font-size="11" text-anchor="end" fill="#8a1c24" '
                     f'font-weight="bold">{esc(board)}</text>')
    for i, s in enumerate(lines):
        items.append(f'<text x="{x + 8}" y="{y + 35 + i * 14}" font-size="11" fill="#333">{esc(s)}</text>')
    return (x, y, w, h)


def arrow(pts, label="", colour="#444", width=2, dash=False, lx=None, ly=None, anchor="middle"):
    d = "M" + " L".join(f"{x},{y}" for x, y in pts)
    da = ' stroke-dasharray="6 3"' if dash else ""
    items.append(f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="{width}"{da} marker-end="url(#a)"/>')
    if label:
        if lx is None:
            (x0, y0), (x1, y1) = pts[-2], pts[-1]
            lx, ly = (x0 + x1) / 2, (y0 + y1) / 2 - 5
        items.append(f'<text x="{lx}" y="{ly}" font-size="11" text-anchor="{anchor}" fill="{colour}">{esc(label)}</text>')


def line(pts, colour, width=2, dash=False):
    d = "M" + " L".join(f"{x},{y}" for x, y in pts)
    da = ' stroke-dasharray="6 3"' if dash else ""
    items.append(f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="{width}"{da}/>')


def text(x, y, s, size=11, colour="#333", anchor="start", weight="normal"):
    items.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{colour}" text-anchor="{anchor}" '
                 f'font-weight="{weight}">{esc(s)}</text>')


def addr(ref):
    return " ".join(f"0x{a:02X}" for a in P[ref].get("i2c") or [])


def main():
    need("SOLAR_P", "VUSB", "PACK_P", "CELL_P", "BAT_P", "SYS", "+3V3", "I2C_SDA", "I2C_SCL", "MUX_RST",
         "CUPS", "VANE", "RAIN", "RF_MINI", "RF_WALL", "VCCIO", *[f"P{k}_SDA" for k in range(1, 5)])
    W, H = 1500, 960
    PW, I2, MT, RF = "#C0392B", "#1F5FBF", "#2CA02C", "#8E44AD"
    text(W / 2, 30, "TX stack r1: block diagram (Wio-E5 mini TX on four SolderFul boards)", 18, anchor="middle", weight="bold")
    text(W / 2, 50, "Generated from schematic/model.py. Red: power. Blue: I2C. Green: meter lines. Purple: RF. "
         "Dashed: battery current (soldered leads only, never a strip).", 12, anchor="middle")
    # ---------------- power tree (left)
    box(30, 80, 230, 62, P["PV1"]["value"], [P["PV1"]["part"][:36], "gland, off the stack"], "#fdf2e9", PW)
    box(30, 160, 230, 50, P["PS1"]["value"], [P["PS1"]["part"]], "#fdf2e9", PW)
    box(30, 250, 230, 62, P["BT1"]["value"] + " pack", [P["BT1"]["part"], "69 x 54 x 18 mm, beside the stack"], "#fdf2e9", PW)
    box(300, 90, 230, 110, "BQ25798EVM (U1) charger", ["TI SLUUCB5; MPPT from solar", "I2C " + addr("U1") + ", INT not wired",
        "outline [TBD-MEASURE]", "rides on B4 (mount TBD)"], "#fdf2e9", PW, "B4")
    box(300, 240, 230, 92, "INA228 (U2) shunt " + addr("U2"), [P["U2"]["part"] + ", 15 mohm shunt",
        "battery leads on the X1 pads", "header pins 5-7 pulled"], "#fdf2e9", PW, "B4")
    box(300, 352, 230, 62, "MAX17048 (U6) gauge " + addr("U6"), [P["U6"]["part"], "VBAT on the JP2 pad (CELL_P)"],
        "#fdf2e9", PW, "B4")
    box(570, 90, 200, 62, "S7V8F3 (U7) 3.3 V", [P["U7"]["part"] + " buck-boost", "SYS in, +3V3 out"], "#fdf2e9", PW, "B4")
    arrow([(260, 110), (300, 120)], "SOLAR", PW)
    arrow([(260, 185), (280, 185), (280, 170), (300, 170)], "VUSB", PW, lx=282, ly=200, anchor="start")
    arrow([(145, 312), (145, 380), (300, 380)], "", PW, dash=True)
    text(150, 344, "PACK+ via JST PH pigtail (PG1)", 11, PW)
    text(150, 358, "CELL_P to U6 VBAT", 11, PW)
    arrow([(260, 285), (300, 285)], "", PW, dash=True)
    text(262, 272, "CELL_P", 10, PW)
    arrow([(415, 240), (415, 200)], "BAT_P (VIN-)", PW, dash=True, lx=420, ly=225, anchor="start")
    arrow([(530, 120), (570, 120)], "SYS", PW)
    text(150, 432, "Battery current runs only in", 11, PW, weight="bold")
    text(150, 446, "soldered leads: checks 6 (schematic) and L4 (layout)", 11, PW)
    # 3V3 rail
    line([(770, 120), (820, 120), (820, 470)], PW, 3)
    text(826, 330, "+3V3 bus", 12, PW, weight="bold")
    text(826, 344, "(bus column)", 11, PW)
    # ---------------- MCU
    a = P["A1"]
    box(860, 90, 300, 140, "Wio-E5 mini (A1)", [a["part"], "soldered low on B3 (not socketed)",
        f"I2C2 SDA {F['I2C_SDA']}, SCL {F['I2C_SCL']} (4.7k on board)", f"MUX_RST {F['MUX_RST']}",
        f"CUPS {F['CUPS']}, VANE {F['VANE']} (ADC), RAIN {F['RAIN']}", "SWD 1x5 right angle (J3)"], "#eef3fa", "#2b4a77", "B3")
    arrow([(820, 160), (860, 160)], "3V3", PW)
    # radio path
    box(1220, 90, 250, 50, "SMA on the mini", ["RF_MINI, edge-mount SMA-K"], "#f5eef8", RF, "B3")
    box(1220, 160, 250, 50, "CX1 " + P["CX1"]["value"], ["Amphenol 135110-01-06.00, RG-316"], "#f5eef8", RF)
    box(1220, 230, 250, 50, "AE1 " + P["AE1"]["value"], [P["AE1"]["part"]], "#f5eef8", RF)
    arrow([(1160, 115), (1220, 115)], "LoRa", RF)
    arrow([(1345, 140), (1345, 160)], "", RF)
    arrow([(1345, 210), (1345, 230)], "", RF)
    text(1350, 296, "bulkhead in the box wall", 11, RF)
    # ---------------- I2C tree
    line([(1010, 230), (1010, 470), (300, 470)], I2, 3)
    text(1016, 260, "I2C_SDA / I2C_SCL bus column", 12, I2, weight="bold")
    arrow([(415, 470), (415, 414)], "", I2)
    arrow([(560, 470), (560, 332), (530, 332)], "", I2)
    arrow([(545, 470), (545, 160), (530, 160)], "", I2)
    box(860, 500, 280, 62, "SHTC3 (U5) " + addr("U5"), [P["U5"]["part"] + ", board climate", "on B3 rows 23-27"],
        "#eef3fa", I2, "B3")
    arrow([(1010, 470), (1010, 500)], "", I2)
    box(300, 500, 400, 92, "PCA9548 (U4) mux " + addr("U4"), [P["U4"]["part"] + ", on a foam pad, wired by its pads",
        f"RESET from {F['MUX_RST']}; ch0-3 on the QT sockets", "QT V+ is VCCIO (not 3V3): folded back on the leads"],
        "#eef3fa", I2, "B2")
    arrow([(650, 470), (650, 500)], "", I2)
    text(656, 490, "upstream", 11, I2)
    # ports
    for k in range(1, 5):
        jref, mod, ch = model.PORTS[k]
        x = 30 + (k - 1) * 290
        box(x, 640, 260, 76, f"Port S{k}: {jref} RJ11 + F{k} MF-R010",
            [f"QT lead W1{k} from mux ch{ch}", f"P{k}_3V3 through the PTC (check 5)", "BOB-14021 + 87180-066LF"],
            "#eef3fa", I2, "B1")
        arrow([(380 + (k - 1) * 70, 592), (380 + (k - 1) * 70, 615), (x + 130, 615), (x + 130, 640)], "", I2)
        if mod:
            m = P[mod]
            box(x, 760, 260, 50, f"{mod} {m['value']} " + addr(mod), [m["part"][:40]], "#f4f6f8", "#555")
        else:
            box(x, 760, 260, 50, "spare port", ["no module yet"], "#f4f6f8", "#999")
        arrow([(x + 130, 716), (x + 130, 760)], "6P cable", "#555", lx=x + 136, ly=742, anchor="start")
    line([(820, 470), (820, 628), (30, 628)], PW, 1.5, True)
    text(30, 624, "+3V3 to each PTC (B1 back + rail, one wire from B2)", 11, PW)
    # meters
    box(1200, 500, 270, 92, "Meters (B2): J21 wind, J22 rain", ["BOB-14021 + 87180-066LF, 10k pull-ups R1-R3",
        "100 nF C1 (cups), C2 (rain)", f"CUPS {F['CUPS']}, VANE {F['VANE']}, RAIN {F['RAIN']}"], "#eefaf0", MT, "B2")
    box(1200, 640, 270, 50, "SEN-15901 (M1, M2)", ["wind vane + cups, rain gauge, 6P cables"], "#f4f6f8", "#555")
    arrow([(1335, 640), (1335, 592)], "", MT)
    arrow([(1200, 545), (1180, 545), (1180, 200), (1160, 200)], "CUPS / VANE / RAIN", MT, lx=1186, ly=380, anchor="start")
    # boards key
    y = 850
    text(30, y, "Boards (bottom to top): B1 PORTS, 20 mm, B2 METERS, 20 mm, B3 CORE, 10 mm (Sullins socket + header), "
         "B4 POWER. Bus column f-j rows 23-30: 3V3, GND, SCL, SDA, MUX_RST, CUPS, VANE, RAIN.", 12, weight="bold")
    text(30, y + 20, "Addresses (check 2): upstream " + ", ".join(
        f"{r} {addr(r)}" for r in ("U6", "U2", "U1", "U5", "U4")) + "; behind the mux, each port: 24LC32 0x50 + its sensor.", 12)
    text(30, y + 40, "GND is common everywhere and is not drawn. Pin maps: schematic/model.py PIN_MAPS, checked against "
         "firmware/host/include/board_pins.h (check 7).", 12)
    head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
            f'font-family="Helvetica, Arial, sans-serif"><title>TX stack r1 block diagram</title>'
            f'<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="context-stroke"/></marker></defs>'
            f'<rect width="100%" height="100%" fill="#ffffff"/>')
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(head + "\n".join(items) + "</svg>\n")
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
