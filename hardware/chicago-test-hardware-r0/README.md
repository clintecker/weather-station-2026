# Chicago weather-station test hardware R0

Open **index.html** for the illustrated build/order guide and bench equipment list.

## Send to manufacturers

- PCB fabrication: `manufacturing/sensor-interface-gerbers.zip` — five 50 x 35 mm, two-layer, 1.6 mm FR-4 boards.
- Through-hole assembly: also send `manufacturing/BOM.csv`, `manufacturing/placement.csv`, `manufacturing/assembly-top.svg` and `docs/build-and-order.md`.
- 3D printer: `mechanical/nucleo-fit-coupon.stl` first. After fit confirmation, two `nucleo-open-cradle.stl`, one `sensor-interface-base.stl` and one `sensor-ventilated-tray.stl`.
- All fixture STEP files are editable solid geometry. `sensor-interface-bare-pcb.step` is a dimensional reference only, not a printable functional PCB.

## Editable sources

Open `pcb/sensor-interface.kicad_pro` in KiCad 7 or later; schematic, PCB and local symbol/footprint libraries are included. The passive board has no firmware. Scripted regeneration used KiCad 7.0.11 and CadQuery 2.7.0; use `source/build_schematic.py`, `source/build_pcb.py`, `source/build_mechanical.py`, then `source/export_fabrication.sh`. Run the pcbnew scripts with the Python environment supplied by your KiCad installation. The CAD generator is fully editable parametric Python; STEP also opens in FreeCAD/Fusion/other CAD tools.

Verification scripts: `source/verify_electrical.py` and `source/check_meshes.py`. Validation outputs are included. Physical fit and electrical bench qualification remain untested. No manufacturer order has been placed.

The bundle is an engineering prototype: a passive sensor connection/current-test board plus open bench fixtures around purchased Nucleo and SHT45 modules. It does not contain the later battery/solar/controller PCB or a weatherproof enclosure. The Stage-0 software starter remains a separate package.
