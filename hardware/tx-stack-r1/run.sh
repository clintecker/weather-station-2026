#!/bin/sh
# Rebuild and check everything in hardware/tx-stack-r1. Exits non-zero on the first failed step or check.
# Needs python3 (with Pillow), KiCad 10 (kicad-cli) and Google Chrome or Chromium (SVG -> PNG).
set -e
cd "$(dirname "$0")"
echo "== schematic: model.py -> KiCad -> ERC + netlist -> checks 1-8 -> PDF"
sh schematic/run.sh
echo "== dimension table in README.md"
python3 sources.py --check
echo "== layout checks L1-L7"
python3 layout/layout_checks.py
echo "== block diagram, top views, build lists, side elevation"
python3 schematic/blockdiag.py
python3 layout/drawings.py --png
echo "== KiCad 3D renders"
python3 render/kicad_render.py
for f in block-diagram stack-elevation B1-top B2-top B3-top B4-top \
         B1-render-top B1-render-iso B2-render-top B2-render-iso B3-render-top B3-render-iso \
         B4-render-top B4-render-iso stack-render-iso stack-render-front; do
    [ -s "renders/$f.png" ] || { echo "missing renders/$f.png"; exit 1; }
done
echo "== tx-stack-r1: every check passes"
