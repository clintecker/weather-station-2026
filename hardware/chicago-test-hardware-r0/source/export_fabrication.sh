#!/usr/bin/env bash
# Run from anywhere after installing KiCad 7+; CAD source lives beside this script.
set -euo pipefail
package_root="$(cd "$(dirname "$0")/.." && pwd)"
kicad_command="${KICAD_CLI:-kicad-cli}"
board_path="$package_root/pcb/sensor-interface.kicad_pcb"
mkdir -p "$package_root/manufacturing/gerbers"
"$kicad_command" pcb export gerbers --no-x2 --subtract-soldermask --layers F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts --output "$package_root/manufacturing/gerbers/" "$board_path"
"$kicad_command" pcb export drill --excellon-separate-th --generate-map --map-format svg --output "$package_root/manufacturing/gerbers/" "$board_path"
"$kicad_command" pcb export svg --layers F.Cu,F.Silkscreen,Edge.Cuts --page-size-mode 2 --exclude-drawing-sheet --output "$package_root/docs/pcb-top.svg" "$board_path"
"$kicad_command" sch export svg --output "$package_root/docs/schematic/" "$package_root/pcb/sensor-interface.kicad_sch"
"$kicad_command" sch export netlist --format kicadxml --output "$package_root/validation/schematic-netlist.xml" "$package_root/pcb/sensor-interface.kicad_sch"

"$kicad_command" pcb export pos --format csv --units mm --side front --output "$package_root/manufacturing/placement.csv" "$board_path"
