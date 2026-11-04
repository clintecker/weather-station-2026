"""Step 3 layout options: simple top-view sketches, to scale (mm), plate front edge at the bottom.

Outlines from the makers' board files and pages (see ../.pcba-workflow/circuit-review.md evidence);
the #368/#369 and the OLED header position are estimates until measured. Writes option-{a,b,c}.png.
Run: uv run --with matplotlib python sketch_options.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mp  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
SIZE = {  # w x h in mm, as seen from above
    "BB830": (165.1, 54.6), "NUCLEO": (70.0, 64.5), "CHG": (38.1, 33.0), "INA": (25.4, 20.3),
    "WAGO3": (17.0, 20.5), "WAGO5": (26.6, 20.5), "PACK": (69.0, 54.0), "USBF": (20.3, 14.0),
    "USBM": (14.0, 12.7), "BARREL": (30.0, 15.0), "QT": (25.4, 17.8), "OLED": (85.0, 58.0),
    "BOB": (21.6, 20.6), "LOAD": (16.0, 6.0),
}
COLOUR = {"power": "#f4b183", "bb": "#d9d9d9", "sensor": "#a9d18e", "mcu": "#9dc3e6", "oled": "#c5a5e0",
          "meter": "#ffe699"}


def box(ax, kind, x, y, label, group, rot=False):
    w, h = SIZE[kind]
    if rot:
        w, h = h, w
    ax.add_patch(mp.Rectangle((x, y), w, h, fc=COLOUR[group], ec="black", lw=0.8))
    ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=6.5, wrap=True)
    return x, y, w, h


def arrow(ax, x, y, dx, dy, label):
    ax.annotate(label, xy=(x, y), xytext=(x + dx, y + dy), fontsize=6.5, ha="center",
                arrowprops=dict(arrowstyle="->", lw=0.8))


def plate(title, w, h, parts, notes, out):
    fig, ax = plt.subplots(figsize=(11, 11 * h / w + 1.2))
    ax.add_patch(mp.Rectangle((0, 0), w, h, fc="#fbfbf7", ec="black", lw=1.5))
    for p in parts:
        p(ax)
    ax.text(w / 2, -8, "FRONT EDGE (you sit here)", ha="center", fontsize=8)
    ax.text(w / 2, h + 4, "BACK EDGE: all USB cables and the solar lead leave here", ha="center", fontsize=8)
    ax.set_xlim(-10, w + 10)
    ax.set_ylim(-26, h + 14)
    ax.set_aspect("equal")
    ax.set_title(f"{title}    plate {w:.0f} x {h:.0f} mm", fontsize=11, loc="left")
    ax.axis("off")
    handles = [mp.Patch(fc=c, ec="black", label=k) for k, c in (
        ("power island (screw/WAGO/JST only)", COLOUR["power"]), ("breadboard", COLOUR["bb"]),
        ("weather meter jacks", COLOUR["meter"]), ("QT sensors", COLOUR["sensor"]), ("NUCLEO", COLOUR["mcu"]),
        ("OLED", COLOUR["oled"]))]
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, -0.13), ncol=6, fontsize=6.5, frameon=False)
    fig.text(0.01, 0.005, notes, fontsize=7, va="bottom")
    fig.savefig(HERE / out, dpi=130, bbox_inches="tight")
    plt.close(fig)


def power_island(ax, x0, y0):
    """Pack, charger, four INA228, gauge, three WAGOs, the source breakouts: about 190 x 95 mm."""
    box(ax, "PACK", x0, y0, "Pack 6600 mAh\n(+ NTC taped on)", "power")
    box(ax, "WAGO3", x0 + 74, y0 + 34, "WAGO\nCELL+", "power")
    box(ax, "WAGO5", x0 + 74, y0 + 4, "WAGO\nSTAR", "power")
    box(ax, "INA", x0 + 96, y0 + 34, "INA228\n0x40 batt", "power")
    box(ax, "INA", x0 + 74, y0 + 58, "MAX17048\ngauge", "power")
    box(ax, "CHG", x0 + 126, y0 + 22, "bq24074\n#4755", "power")
    box(ax, "INA", x0 + 126, y0 - 2, "INA228\n0x41 load", "power")
    box(ax, "WAGO5", x0 + 156, y0 - 2, "WAGO\nLOAD", "power")
    box(ax, "LOAD", x0 + 156, y0 + 21, "100R", "power")
    box(ax, "INA", x0 + 104, y0 + 64, "INA228\n0x48 USB", "power")
    box(ax, "INA", x0 + 134, y0 + 64, "INA228\n0x45 solar", "power")
    box(ax, "USBF", x0 + 104, y0 + 88, "#4090", "power")
    box(ax, "USBM", x0 + 104 + 22, y0 + 88, "#5978", "power")
    box(ax, "BARREL", x0 + 142, y0 + 88, "#368/#369", "power")


def option_a():
    W, H = 380, 270

    def parts(ax):
        power_island(ax, 8, 158)
        box(ax, "BB830", 8, 30, "BB830 #1: all signal circuits\n(divider, ISET, S7V8F3, links, meter pull-ups,\nI2C junction rows, 3V3/GND rails)", "bb")
        box(ax, "BOB", 18, 9.5, "RJ11\nwind", "meter")
        box(ax, "BOB", 44, 9.5, "RJ11\nrain", "meter")
        box(ax, "NUCLEO", 112, 88, "TX NUCLEO\n(USB to back)", "mcu")
        box(ax, "OLED", 185, 12, "OLED 2.7in", "oled")
        for i, (nm, dx, dy) in enumerate((("hub", 0, 0), ("SHT45", 0, 22), ("SHTC3", 30, 22), ("BMP581", 30, 0),
                                          ("LTR390", 0, 44))):
            box(ax, "QT", 290 + dx, 14 + dy, nm, "sensor")
        box(ax, "NUCLEO", 290, 190, "RX NUCLEO\n(USB to back)", "mcu")
        arrow(ax, 29, 6, 0, -14, "meter cables")
        arrow(ax, 125, 255, 0, 14, "USB-C adapter, solar")
    plate("Option A: one breadboard, everything else on standoffs", W, H, [parts],
          "One BB830 along the front carries every signal circuit; the RJ11 breakouts overhang the front edge. Power island behind it, "
          "TX NUCLEO between them, sensors and RX NUCLEO on the right.\n"
          "+ smallest (380 x 270), fewest boards, all breadboard work in one place.  - long leads from the breadboard to the charger "
          "and the regulator chain crosses the middle; OLED leads cross the board.", "option-a.png")


def option_b():
    W, H = 400, 290

    def parts(ax):
        power_island(ax, 8, 170)
        box(ax, "BB830", 210, 205, "BB830 #1 POWER signals:\nVBUS divider, ISET network,\nS7V8F3, BATTERY link, tie row", "bb")
        box(ax, "BB830", 8, 30, "BB830 #2 SENSOR signals:\nmeter pull-ups + filters, I2C junction rows,\nOLED link + 220 uF, 3V3/GND rails", "bb")
        box(ax, "BOB", 18, 9.5, "RJ11\nwind", "meter")
        box(ax, "BOB", 44, 9.5, "RJ11\nrain", "meter")
        box(ax, "NUCLEO", 200, 100, "TX NUCLEO\n(USB to back)", "mcu")
        box(ax, "OLED", 290, 25, "OLED 2.7in", "oled")
        for nm, dx, dy in (("hub", 0, 0), ("SHT45", 30, 0), ("SHTC3", 60, 0), ("BMP581", 90, 0), ("LTR390", 120, 0)):
            box(ax, "QT", 20 + dx, 100 + dy, nm, "sensor")
        box(ax, "NUCLEO", 300, 100, "RX NUCLEO\n(USB to back)", "mcu")
        arrow(ax, 29, 6, 0, -14, "meter cables")
        arrow(ax, 125, 275, 0, 14, "USB-C adapter, solar")
    plate("Option B: two breadboards by function (power signals / sensor signals)", W, H, [parts],
          "BB #1 sits against the power island and holds only charger and regulator signals; BB #2 along the front holds the meter, "
          "I2C and OLED supply. TX NUCLEO in the middle reaches both with short jumpers.\n"
          "+ grouped exactly by function, short leads, the power side can be debugged without touching sensors.  "
          "- one more board, 400 x 290 (inside the 300 x 400 target).", "option-b.png")


def option_c():
    W, H = 400, 260

    def parts(ax):
        power_island(ax, 8, 158)
        box(ax, "BB830", 8, 20, "BB830 #1 POWER signals", "bb")
        box(ax, "NUCLEO", 8, 84, "RX NUCLEO", "mcu")
        box(ax, "BB830", 226, 195, "BB830 #2 SENSOR signals", "bb")
        box(ax, "BOB", 391, 198, "RJ11\nwind", "meter", rot=True)
        box(ax, "BOB", 391, 224, "RJ11\nrain", "meter", rot=True)
        for nm, dx in (("hub", 0), ("SHT45", 30), ("SHTC3", 60), ("BMP581", 90), ("LTR390", 120)):
            box(ax, "QT", 226 + dx, 160 + 0 * dx, nm, "sensor")
        box(ax, "NUCLEO", 205, 15, "TX NUCLEO", "mcu")
        box(ax, "OLED", 295, 15, "OLED 2.7in", "oled")
        arrow(ax, 420, 236, 0, 16, "meter cables")
    plate("Option C: left-to-right signal flow (power -> MCU -> sensors)", W, H, [parts],
          "Left half power (island behind, power breadboard in front), right half sensors (sensor breadboard behind with the RJ11 "
          "jacks out the right side), TX NUCLEO and OLED front-centre and front-right.\n"
          "+ the plate reads like the block diagram, TX NUCLEO and OLED right in front of you.  - meter jacks on the side, "
          "not the front; the two breadboards are far apart (the TX NUCLEO bridges them with longer leads).", "option-c.png")


if __name__ == "__main__":
    option_a()
    option_b()
    option_c()
    print("wrote option-a.png, option-b.png, option-c.png")
