"""Fetch the makers' STEP models the renders use into render/models/ (not committed: see render/.gitignore).

Each file is checked against the SHA-256 it had when the layout was drawn, so a changed upstream model is
noticed, not silently rendered. A model that cannot be fetched is left out and the render draws that part's
checked boxes instead, and says so in its legend. Run: python3 fetch_models.py
"""
import hashlib
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
}


def path_of(kind):
    """Local path of a verified model, or None."""
    if kind not in SOURCES:
        return None
    p = MODELS / kind / SOURCES[kind][1]
    if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == SOURCES[kind][2]:
        return p
    return None


def fetch():
    ok = True
    for kind, (url, name, sha, _note) in SOURCES.items():
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
    return ok


if __name__ == "__main__":
    fetch()
    sys.exit(0)
