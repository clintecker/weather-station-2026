"""Session 9 (commission) illustrations, same pipeline as Sessions 2-8 (r3d: hidden lines + flat colour).

One new picture (access: the loaded box from Session 8, lid off, with J3 and the Wio-E5 mini's USB-C marked, both at
B3's front edge, from stack.PLACE["B3"] through stack.card_to_box), and the pictures this session shares with
Sessions 5, 7 and 8, rendered again into this folder (never into theirs): B3's top face with J3 and A1 (scenes5), the
EVM with its jumpers and the pack at PG1 (scenes7), the EVM on its ledges (scenes8).

Run ONE scene per process: .venv-cad/bin/python -B scenes9.py NAME   (list: scenes9.py list)
"""
import importlib
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SHEETS = HERE.parent
for p in (SHEETS / "session5", SHEETS / "session7", SHEETS / "session8"):
    sys.path.append(str(p))

OUT = HERE / "svg"
OUT.mkdir(exist_ok=True)
SCENES = {}


def scene(fn):
    SCENES[fn.__name__] = fn
    return fn


@scene
def access():
    """The loaded box (scenes8.built), plus J3's mating pins and the mini's USB-C receptacle on B3 (the top card)."""
    import scenes8 as B
    import stack as st
    B.OUT = OUT
    s = B.new()
    B.base(s)
    B.A.backplane(s)
    B.pack(s, rt1=False)
    B.evm(s, silk=False)
    B.A.cards(s)
    B.glands(s, inside=True, stub=12.0)
    pl = {p["ref"]: p for p in st.PLACE["B3"]}
    pins = next(b for b in pl["J3"]["boxes"] if b.what == "J3 mating pins")
    usb = next(b for b in pl["A1"]["boxes"] if b.what == "A1 USB-C receptacle")
    s.anchor("j3", B.P(*st.card_to_box("B3", (pins.x0 + pins.x1) / 2, pins.y0 + 1.0, pins.z1)))
    s.anchor("usbc", B.P(*st.card_to_box("B3", usb.x0 + 0.5, (usb.y0 + usb.y1) / 2, usb.z1)))
    B.R("access", s, (0.5, 0.45, 1.0), fit=(330, 330), keep=["B3_front", "B4_front", "j3", "usbc", "bar"])


def _shared(mod, fn):
    def f():
        m = importlib.import_module(mod)
        m.OUT = OUT                     # write here, never into that session's svg/
        m.SCENES[fn]()
    f.__name__ = fn
    scene(f)


for _n in ("t_mini", "t_swd_iso"):
    _shared("scenes5", _n)
for _n in ("evm_done", "jp_fit", "pack_pg1"):
    _shared("scenes7", _n)
for _n in ("evm_in",):
    _shared("scenes8", _n)


if __name__ == "__main__":
    names = sys.argv[1:]
    if names == ["list"]:
        print(" ".join(SCENES))
        sys.exit()
    for n in names:
        SCENES[n]()
