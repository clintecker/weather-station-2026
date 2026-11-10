#!/bin/sh
# Rebuild and check everything in hardware/tx-stack-r1. Exits non-zero on the first failed step or check.
# Needs python3 (with Pillow), KiCad 10 (kicad-cli) and Google Chrome or Chromium (SVG -> PNG).
set -e
cd "$(dirname "$0")"
echo "== schematic: model.py -> KiCad -> ERC + netlist -> checks 1-10 -> PDF"
sh schematic/run.sh
echo "== dimension table in README.md"
python3 sources.py --check
echo "== layout checks L1-L7"
python3 layout/layout_checks.py
echo "== printed cage: parts inside the box"
python3 cage/cage.py
echo "== block diagram, card top views, backplane, cage side view, build sheets"
python3 schematic/blockdiag.py
python3 layout/drawings.py --png
echo "== KiCad 3D renders (maker models from render/fetch_models.py; boxes if offline)"
python3 render/fetch_models.py
python3 render/kicad_render.py
for f in block-diagram B1-top B2-top B3-top B4-top backplane cage-side \
         B1-render-top B1-render-iso B2-render-top B2-render-iso B3-render-top B3-render-iso \
         B4-render-top B4-render-iso cage-render-iso cage-render-front; do
    [ -s "renders/$f.png" ] || { echo "missing renders/$f.png"; exit 1; }
done
echo "== tx-stack-r1 (r2 cage): every check passes"
