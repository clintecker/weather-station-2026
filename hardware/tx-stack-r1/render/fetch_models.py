"""Fetch the makers' STEP models the renders use into render/models/ (not committed: see render/.gitignore).

Each file is checked against the SHA-256 it had when the layout was drawn, so a changed upstream model is
noticed, not silently rendered. A model that cannot be fetched is left out and the render draws that part's
checked boxes instead, and says so in its legend. Two boards have no published 3D model but do publish their
Eagle board files; those are fetched (checked the same way) and built into a STEP of the bare board with KiCad:
  kicad-cli pcb import --format eagle; Eagle's unmapped layers onto Cmts.User; (BOB) keep one board of the
  panel of two; kicad-cli pcb export step --board-only (pads, tracks and silkscreen; no part models).
The jack on the BOB and the module, SMA and USB-C on the mini stay the checked boxes (see MODELS.md).
Run: python3 -I fetch_models.py  (-I: it reads downloaded files)
"""
import hashlib
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODELS = HERE / "models"
ADA = "https://raw.githubusercontent.com/adafruit/Adafruit_CAD_Parts/main/"
# kind -> (url, local name, sha256, origin note)
SOURCES = {
    "INA": (ADA + urllib.parse.quote("5832 INA228 STEMMA QT/5832 INA228 STEMMA QT.step"), "5832_INA228.step",
            "701a1218ebb487fcea3885c3fbee4d62b44c5e3f696c0d88083ee149094fb82b",
            "Adafruit_CAD_Parts 5832; shows the terminal block, which is not fitted here"),
    "MAX": (ADA + urllib.parse.quote("5580 MAX17048/5580 MAX17048.step"), "5580_MAX17048.step",
            "acc003d40a01eeeb7e5f63c9f6da4e4e87a5113dcc4a02990f2f26b7df2e7971", "Adafruit_CAD_Parts 5580"),
    "SHTC3": (ADA + urllib.parse.quote("4636 SHTC3/4636 SHTC3.step"), "4636_SHTC3.step",
              "8db7931b70e13c49441b1210dd43ab487653ebeca56fa6fc78ef7b40055487e1", "Adafruit_CAD_Parts 4636"),
    "REG": ("https://www.pololu.com/file/0J1374/pololu-step-up-step-down-voltage-regulator-s7v8fx.step",
            "pololu_s7v8fx.step", "1bdaa13a7e0b634f9f4bb45f22c088f3b8e8441d8b0866a5b7e670253c667e4e",
            "Pololu S7V8Fx (file 0J1374)"),
    "MUX": (ADA + urllib.parse.quote("5626 PCA9548 Stemma/5626 PCA9548 Stemma.step"), "5626_PCA9548_Stemma.step",
            "779515a72bc38dec6b447a22e6d0c9fac81e6742112680273c4ebd894c0db6e2", "Adafruit_CAD_Parts 5626"),
}
# kind -> (Eagle .brd url, local name, sha256, crop box (x0, y0, x1, y1) in KiCad coordinates or None, built STEP)
BUILT = {
    "BOB": ("https://raw.githubusercontent.com/sparkfun/RJ11_Breakout/master/hardware/RJ11-Breakout.brd",
            "RJ11-Breakout.brd", "9ebffbcad9b55241fa45ab11c6ae7e05caeed996e5e09114794b8e1e149d0c63",
            (0.0, -20.32, 15.24, 0.0), "bob14021_board.step"),
    "MINI": ("https://files.seeedstudio.com/products/113990939/" + urllib.parse.quote("LoRa-E5 mini v1.0.brd"),
             "LoRa-E5_mini_v1.0.brd", "7ea2457d73b3f7a3acdfc23fdf1edf9ed1c607c1acfdd0610586985f7a3a22d5",
             None, "wio_e5_mini_board.step"),
}


def path_of(kind):
    """Local path of a verified model (or of a STEP built from a verified board file), or None."""
    if kind in BUILT:
        _u, _n, sha, _c, step = BUILT[kind]
        p, stamp = MODELS / kind / step, MODELS / kind / (step + ".from")
        return p if p.exists() and stamp.exists() and stamp.read_text().strip() == sha else None
    if kind not in SOURCES:
        return None
    p = MODELS / kind / SOURCES[kind][1]
    if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == SOURCES[kind][2]:
        return p
    return None


def _items(s):
    """(start, end) of every top-level item of a KiCad board file."""
    depth, start, out = 0, None, []
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
            if depth == 2:
                start = i
        elif ch == ")":
            if depth == 2:
                out.append((start, i + 1))
            depth -= 1
    return out


def _crop(s, box):
    """Keep the board outline, parts and copper inside box (one board of a panel)."""
    x0, y0, x1, y1 = box
    res, last = [], 0
    for a, b in _items(s):
        it = s[a:b]
        drop = False
        if it.startswith("(gr_") and "Edge.Cuts" in it:
            pts = [(float(x), float(y)) for x, y in re.findall(r"\((?:start|end) ([-\d.]+) ([-\d.]+)\)", it)]
            drop = not all(x0 <= x <= x1 and y0 <= y <= y1 for x, y in pts)
        elif it.startswith("(footprint"):
            m = re.search(r"\(at ([-\d.]+) ([-\d.]+)", it)
            drop = not (x0 <= float(m.group(1)) <= x1 and y0 <= float(m.group(2)) <= y1)
        elif it.startswith(("(gr_", "(segment", "(via", "(zone", "(arc")):
            pts = [(float(x), float(y)) for x, y in re.findall(r"\((?:start|end|at|xy|mid) ([-\d.]+) ([-\d.]+)", it)]
            drop = bool(pts) and not all(x0 - 0.5 <= x <= x1 + 0.5 and y0 - 0.6 <= y <= y1 + 0.5 for x, y in pts)
        res.append(s[last:a])
        if not drop:
            res.append(it)
        last = b
    res.append(s[last:])
    return "".join(res)


def build(kind, d, brd):
    """Eagle board file -> KiCad board -> STEP of the bare board, in d (the board file's own folder)."""
    _u, _n, sha, crop, step = BUILT[kind]
    pcb = d / "imported.kicad_pcb"
    r = subprocess.run(["kicad-cli", "pcb", "import", "--format", "eagle", "-o", str(pcb), str(brd)],
                       capture_output=True, text=True)
    if r.returncode or not pcb.exists():
        print(f"build {kind}: KiCad import failed: {r.stderr[-200:]}")
        return False
    s = pcb.read_text().replace('(layer "UNDEFINED")', '(layer "Cmts.User")')
    if crop:
        s = _crop(s, crop)
    pcb.write_text(s)
    r = subprocess.run(["kicad-cli", "pcb", "export", "step", "--board-only", "--include-pads", "--include-silkscreen",
                        "--include-tracks", "--user-origin", "0x0mm", "-f", "-o", str(d / step), str(pcb)],
                       capture_output=True, text=True)
    if r.returncode or not (d / step).exists():
        print(f"build {kind}: STEP export failed: {r.stderr[-200:]}")
        return False
    (d / (step + ".from")).write_text(sha + "\n")
    print(f"built {kind}: {step} from {_n}")
    return True


def fetch():
    ok = True
    todo = [(k, v[0], v[1], v[2]) for k, v in SOURCES.items()] + [(k, v[0], v[1], v[2]) for k, v in BUILT.items()]
    for kind, url, name, sha in todo:
        if path_of(kind):
            continue
        d = MODELS / kind                   # one folder per download
        d.mkdir(parents=True, exist_ok=True)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tx-stack-render"})
            data = urllib.request.urlopen(req, timeout=60).read()
        except Exception as e:  # noqa: BLE001 - offline is allowed: the render falls back to boxes
            print(f"fetch {kind}: {e}; the render will draw boxes")
            ok = False
            continue
        if hashlib.sha256(data).hexdigest() != sha:
            print(f"fetch {kind}: checksum differs from the one recorded; not used (boxes drawn)")
            ok = False
            continue
        (d / name).write_bytes(data)
        print(f"fetched {kind}: {name}")
        if kind in BUILT and not build(kind, d, d / name):
            ok = False
    return ok


if __name__ == "__main__":
    fetch()
    sys.exit(0)
