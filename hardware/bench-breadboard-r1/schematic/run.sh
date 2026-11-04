#!/bin/sh
# Regenerate the bench r1 schematic and check it: model.py -> KiCad file -> KiCad ERC and netlist ->
# rule checks -> PDF. Exit status 0 only if every check passes. Needs KiCad 10 (kicad-cli).
set -e
cd "$(dirname "$0")"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
python3 kicad_gen.py
kicad-cli sch erc --format json --severity-all -o "$T/erc.json" bench-r1.kicad_sch >/dev/null 2>&1 || true
kicad-cli sch export netlist --format kicadsexpr -o "$T/bench.net" bench-r1.kicad_sch >/dev/null 2>&1
kicad-cli sch export pdf -o bench-r1.pdf bench-r1.kicad_sch >/dev/null 2>&1
python3 checks.py "$T/bench.net" "$T/erc.json"
