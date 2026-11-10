# TX card cage r2: Wio-E5 mini TX on four SolderFul cards and a backplane

The transmitter is four SolderFul SOLDERBREAD#02 cards (81.3 x 50.8 mm) standing as horizontal shelves in a printed
card cage in the back of the Adafruit #905 box. The box hangs on its pole by the back wall, long side vertical; the
cable glands are in the bottom wall and the SMA bulkhead is in a side wall near the top. Each card carries a
right-angle 18-pin header on its back edge that plugs into a socket on a stripboard backplane against the back wall,
so any card slides out toward the lid on its own. Battery current never passes through the backplane, a strip, a
header or a socket.

| Card (bottom to top) | Role | What it carries |
|---|---|---|
| B4 | POWER | The battery monitor INA228 (0x40), the fuel gauge MAX17048 (0x36), the S7V8F3 3.3 V regulator and the battery + lug (Keystone 7328). |
| B2 | PORTS B + METERS | Sensor port 4 and the wind and rain jacks, with the meter pull-ups, filters, clamps and 1 k series resistors. |
| B1 | PORTS A | Sensor ports 1-3: each a jack breakout, an MF-R010 fuse, 100 ohm series resistors and BAT85S / 1N5232B clamps. |
| B3 | CORE | The Wio-E5 mini on its header, the enclosure air sensor SHTC3 (0x70) and a right-angle SWD header at the front edge. |
| backplane | bus | BusBoard ST2 cut to 21 strips x 39 holes: four Sullins sockets, the PCA9548 mux (0x71) behind it on foam, the four QT leads to the ports and the charger I2C pins. |
| power zone | below the cards | The battery pack on a printed shelf and the BQ25798EVM on two printed rails, on leads to B4. |

The bus header is Sullins PRPC018SBAN-M71RC (right angle, 1x18) into Sullins PPPC181LFBN-RC (1x18 female) on the
backplane: 5.0 mm of the 5.84 mm mating pin goes in, checked in L5. The SolderFul's own strips are too short for an
18-line bus, so the backplane is stripboard.

Everything here is generated from four sources:

- `schematic/model.py`: the circuit, with plain names for every net, and the r1 → r2 changes with their reasons
- `layout/stack.py`: where every part, pin, jumper and wire goes, on the cards and the backplane
- `cage/cage.py`: the printed cage, parametric; the inputs Clint must measure are named at its top
- `sources.py`: every dimension, with its source or `[TBD-MEASURE]`

`./run.sh` rebuilds everything and runs every check. It exits non-zero if any step or check fails.

## Files

| Path | What it is |
|---|---|
| `run.sh` | Rebuilds and checks everything below, in order. |
| `sources.py` | Every dimension: value, source, status (sourced / derived / TBD). Writes the table at the end of this README; `--check` fails if it is out of step. |
| `schematic/model.py` | The logical schematic: 90 parts and 53 nets, each net with its plain name. Each pin records how it is contacted. Also the RJ11 pin maps, the Wio-E5 functions, the outdoor-line protection, the ERC waivers and the r1 → r2 lists. |
| `schematic/kicad_gen.py` | model.py → `tx-stack-r1.kicad_sch`: parts grouped by function (power, battery and charging, radio and MCU, weather meters, sensor ports, bus) in framed groups, with drawn wires inside a group and plain-name labels only between groups. |
| `schematic/checks.py` | Schematic checks 1-10 (below), against KiCad's netlist and ERC. |
| `schematic/r1-connections.json` | r1's connections, frozen, for check 10. |
| `schematic/tx-stack-r1.pdf` | The schematic, one sheet. |
| `schematic/blockdiag.py` → `drawings/block-diagram.svg` | One-page block diagram with real part numbers. |
| `layout/stack.py` | Card geometry (hole grid, strips, rails), footprints from each maker's board file, the placements, every conductor, the backplane and the joint card → socket. |
| `layout/layout_checks.py` | Layout checks L1-L7 (below). |
| `cage/cage.py` | The printed cage: back plate on the corner bosses, left wall with card slots, right corner post, backplane posts, retention bar, pack shelf, charger rails. `--solid` builds the solids in CadQuery and checks they are valid. No STL yet. |
| `layout/drawings.py` | Writes `drawings/B1..B4-top.svg`, `drawings/backplane.svg`, `drawings/cage-side.svg`, and the build sheets `build/B1..B4.md`, `build/BACKPLANE.md`, `build/ASSEMBLY.md`. `--png` also writes PNG copies into `renders/`. |
| `build/ASSEMBLY.md` | The charger jumper steps before any power, the cage, the card order and the leads off the cards. |
| `build/B1..B4.md`, `build/BACKPLANE.md` | Build sheets: underside wires with lengths, top jumpers, parts lowest first with orientation, leads, strip map, checks before power. |
| `render/fetch_models.py` | Fetches the makers' STEP files into `render/models/` (not committed) and checks each SHA-256. |
| `render/kicad_render.py` | Writes the KiCad boards `render/kicad/tx-stack-B1..B4.kicad_pcb` and `tx-stack-cage.kicad_pcb` and renders them with `kicad-cli pcb render`, each PNG with a legend naming its stand-ins. |
| `renders/*.png` | Every render and a PNG copy of every drawing. |

### Renders and their stand-ins

- Drawings: `block-diagram`, `B1..B4-top`, `backplane`, `cage-side`.
- KiCad per card: `B1..B4-render-top`, `B1..B4-render-iso`. Real models: KiCad's library for the lying
  resistors, the standing DO-35 diodes, the 100 nF discs and the 0.1 in headers; the makers' STEP files for the
  SHTC3, MAX17048 and INA228 (Adafruit_CAD_Parts) and the S7V8F3 (Pololu). The INA228 model shows its terminal block,
  which is not fitted here.
- Stand-ins (boxes from the same list the checks use): the Wio-E5 mini (Seeed publishes no 3D model), its SMA
  right-angle adapter, the jack breakouts (BOB-14021 + Amphenol 87180, modelled from their drawings), the MF-R010
  fuses, the battery lug. The bus and SWD headers are KiCad's generic right-angle headers, same pitch and pin line as
  the Sullins part.
- KiCad assembly: `cage-render-iso`, `cage-render-front`. Every part is an envelope box: the cage, the backplane and
  its sockets, the mux, the cards and their parts, the pack and the BQ25798EVM (its outline is a placeholder).

## Regenerating

```sh
./run.sh                               # everything, with all checks
sh schematic/run.sh                    # schematic + checks 1-10 only
python3 layout/layout_checks.py        # layout checks L1-L7 only
python3 cage/cage.py [--solid]         # the cage against the box inside
python3 layout/drawings.py --png       # drawings + build sheets (+ PNGs)
python3 render/fetch_models.py         # makers' STEP files (once; the renders fall back to boxes offline)
python3 render/kicad_render.py [--no-render]
python3 sources.py                     # after changing a dimension: rewrite the table below
```

You need python3 3.11+ with Pillow, KiCad 10 (`kicad-cli` with its 3D library), and Google Chrome or Chromium.
`--solid` needs CadQuery (`.venv-cad`).

## What the checks verify

**Schematic (`schematic/checks.py`):**

1. KiCad's netlist round-trips to model.py, net for net and pin for pin; every net that crosses groups carries its plain name.
2. Every connected pin is in exactly one net, every unused pin in none; every net has at least two members.
3. The I2C address map (no upstream clash, every 0x50 behind a mux channel, addresses match the firmware) and the upstream pull-up total (1.40 kohm, at or above 0.97 kohm).
4. Each sensor port's 3.3 V comes only through its own MF-R010 from the 3.3 V supply.
5. No battery current passes a header, socket or strip; the series chain, the lug and the sense resistors are present.
6. The RJ11 pin maps (sensor ports 2 3.3 V, 3 data, 4 ground, 5 clock; wind 2/3 ground, 4 cups, 5 vane; rain 3 ground, 4 rain).
7. The Wio-E5 pins match the firmware's board file.
8. KiCad ERC reports nothing beyond the written waivers.
9. Every outdoor line has its series resistor and clamps; the port pull-up (about 5 kohm) allows 236 pF, about 2-3 m of cable at an assumed 50 pF/m `[TBD-MEASURE]`.
10. r2's connections differ from r1's only by the listed changes below.

**Layout (`layout/layout_checks.py`):**

- **L1:** every pin on a hole, every conductor end a real hole or pad, no hole doubled, nothing under a spacer, the back rails bare under the socket.
- **L2/L3:** the copper equals the schematic; no strip carries two nets (checked without part-internal ties).
- **L4:** no battery net touches a strip.
- **L5:** the bus is on rows 1-18 of column j on every card and strips 1-18 of the backplane; insertion 5.00 mm of 5.84 (at least 4.20 with the card 0.8 mm short).
- **L6:** no two part bodies collide on a card.
- **L7:** each card pitch clears the tallest part below, its tails and 0.5 mm; nothing collides with the cage, the backplane or another card; each card slides out alone; everything fits the box inside; the power zone stays under B4; the mux stays clear of the socket tails.

## What changed from r1, and why

r1 stacked the boards on standoffs with soldered bus wires between them; the reviews found it could not be taken
apart (mechanical C1), did not fit the floor (C2) and had 0.5 mm to the lid (C3). r2 replaces the stack with the card
cage. The connection changes (check 10):

- **Removed:** the B3-B4 socket XS1 and the B4 bus pins XP1 (the cards now plug into the backplane); the QT leads on B1 (W11-W14) move to the backplane as W1-W4, beside the mux.
- **Added:** a right-angle bus header per card (XH1-XH4) and a backplane socket per card (XB1-XB4); the charger I2C pins XJ1 on the backplane; the battery + lug E1 (mechanical M8); 100 ohm resistors R7 and R8 at the tap end of the charger battery sense (BATP) and the fuel gauge cell sense leads (electrical m11); the pack thermistor RT1 on EVM J7 with JP18 removed (M2); the right-angle SMA adapter AD1; on every outdoor line a series resistor and clamps (M5): 100 ohm and BAT85S Schottky clamps (to the port 3.3 V and from ground) on each sensor port's data and clock, a 1N5232B zener on each port's 3.3 V, and on cups, vane and rain a 1N5232B zener and a 1 k series resistor to the MCU, with a new 100 nF filter on the vane (C3).
- **Moved:** the charger and gauge sense now leave the lug through R7 and R8; EVM J8 pin 1 is the I2C lead's ground; each port's data and clock pass their series resistors between jack and mux; each meter line passes its 1 k between the jack side and the MCU pin; AD1 sits between the radio and the coax.
- **Renamed:** EVM pins are named by terminal (J3 SYS, J8.2 clock, J8.3 data).

Clamps on the sensor-port data and clock are BAT85S (at most 10 pF at 1 V, Vishay doc 88146), not zeners: a DO-35
zener adds 100 pF or more, which would eat the 236 pF budget.

## Deferred, with reasons

- **Sensor-power switch on PA9 (electrical M3).** No orderable through-hole current-limited switch was found; the
  pin is marked "not wired" in the model. A short on one port still browns out the 3.3 V supply until its MF-R010
  trips.
- **Firmware README profile and pin notes (m10).** Outside this directory; left for a firmware change.

## Open questions

- **The cage is drawn on assumed box dimensions.** Every cage position moves with `box_in` and `boss`.
- **Thermistor bias.** The #372 NTC is B 3950; the EVM's TS divider assumes a 103AT (B 3435). Read TS at room temperature before the first charge (build/ASSEMBLY.md).
- **Mini back-feed.** The mini's AP2112 is back-fed from the bus 3.3 V; with USB-C in for the console two regulators run in parallel (accepted, electrical m3).
- **B4 tether.** B4 carries the battery and SYS leads to the EVM; it slides out with them attached, so leave them a service loop.

## Measurements for Clint

All `[TBD-MEASURE]`; each is a named input in `sources.py` (and `cage/cage.py` for the first four):

1. The #905 box inside: width, height, depth from the back wall to the closed lid (`box_in`).
2. The four corner bosses: centre from the side walls, and diameter (`boss`).
3. The BQ25798EVM outline and its tallest part (`evm`).
4. The card slot fit: print a test slot (`slot_clear`).
5. Solder tails and underside wires below a card, after the first card (`tails`).
6. The Sullins socket's solder tail (`socket_tail`).
7. A standing DO-35 diode's height (`diode_stand_h`).
8. The Keystone 7328 lug (`lug`).
9. The PG-7 glands bought: panel hole and nut (`gland`).
10. An RJ11 plug and its cable bend past the jack (`plug_len`).
11. The USB-C console plug overmould (`usbc_plug`) and the mini's USB-C height (`mini_usbc_h`).
12. The Amphenol 132172 adapter's arms (`sma_ra`) and the mini's SMA overhang (`mini_sma_out`).
13. The QT lead housing height (`qt_lead_h`) and the QT socket height (`qt_h`).
14. The foam pad under the mux (`foam`), the breakout PCB thickness (`breakout_t`) and the S7V8F3's inductor (`s7v8f3_h`).
15. The jack height in a test fit, and each port cable's capacitance (for the 236 pF limit).

## Dimension sources

Status `[TBD-MEASURE]` means no source was found. The drawings use the value as a labelled placeholder until it is measured.

<!-- dimensions:begin (generated by sources.py) -->
| Key | Value (mm) | What | Source | Status |
|---|---|---|---|---|
| `sb_w` | 81.3 | SolderFul board length | https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/6170/DKS-SOLDERBREAD-02-ND.pdf p.2 | sourced |
| `sb_h` | 50.8 | SolderFul board width | https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/6170/DKS-SOLDERBREAD-02-ND.pdf p.2 | sourced |
| `sb_t` | 1.6 | SolderFul board thickness | https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/6170/DKS-SOLDERBREAD-02-ND.pdf p.1 | sourced |
| `pitch` | 2.54 | hole pitch | https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/6170/DKS-SOLDERBREAD-02-ND.pdf p.1 | sourced |
| `sb_hole` | 1 | solder hole diameter | https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/6170/DKS-SOLDERBREAD-02-ND.pdf p.1 | sourced |
| `sb_mhole` | 3 | mounting hole and edge-notch diameter | https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/6170/DKS-SOLDERBREAD-02-ND.pdf p.1-2 | sourced |
| `sb_mhole_span` | 71.1 | centre-line mounting holes, outer pair, centre to centre | https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/6170/DKS-SOLDERBREAD-02-ND.pdf p.2 | sourced |
| `sb_notch_side_y` | 8.9 | side notch centre from the long edge | https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/6170/DKS-SOLDERBREAD-02-ND.pdf p.2 (8.9 mm) | sourced |
| `sb_notch_side_span` | 33 | side notches, outer pair, centre to centre | https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/6170/DKS-SOLDERBREAD-02-ND.pdf p.2 | sourced |
| `sb_notch_end_span` | 68.6 | front and back edge notches, centre to centre (X 6.35 and 74.95) | https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/6170/DKS-SOLDERBREAD-02-ND.pdf p.2 | sourced |
| `sb_centre` | 25.4 | centre channel (middle notch, mounting holes) from the front edge | https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/6170/DKS-SOLDERBREAD-02-ND.pdf p.2 (25.4 mm) | sourced |
| `sb_x1` | 3.82 | row 1 hole centre from the left edge | (81.3 - 29 x 2.54) / 2, rows centred as drawn on p.2 | derived |
| `sb_ya` | 11.43 | column a from the front edge | 25.4 - 3.81 (half the 0.3 in channel, p.2) - 4 x 2.54 | derived |
| `sb_rails` | 3.81 | outer rail from the edge; inner rail 6.35 mm | drawing p.2 measured against the 2.54 grid | derived |
| `bob_w` | 15.24 | BOB-14021 width (along the header) | SparkFun RJ11-Breakout.brd (github.com/sparkfun/RJ11_Breakout, BOB-14021): outline 0..15.24 | sourced |
| `bob_d` | 20.32 | BOB-14021 depth (snap-off tab removed) | SparkFun RJ11-Breakout.brd (github.com/sparkfun/RJ11_Breakout, BOB-14021): outline 0..20.32 | sourced |
| `bob_hdr_y` | 1.27 | header row from the BOB back edge | SparkFun RJ11-Breakout.brd (github.com/sparkfun/RJ11_Breakout, BOB-14021): JP4 at y 1.27 | sourced |
| `bob_peg_y` | 15.24 | jack peg line from the BOB back edge | SparkFun RJ11-Breakout.brd (github.com/sparkfun/RJ11_Breakout, BOB-14021): JP3 at y 15.24 | sourced |
| `jack_w` | 13.2 | 87180 / 54601 jack body width | KiCad 10 footprint RJ12_Amphenol_54601-x06_Horizontal (fab layer); RS 771-0215 listing 13.2 | sourced |
| `jack_d` | 18 | jack body depth (peg line + 7.88 to the mouth) | KiCad 10 footprint RJ12_Amphenol_54601-x06_Horizontal (fab layer): fab -1.23..16.77; RS 18 mm | sourced |
| `jack_h` | 11.5 | jack body height above the BOB | RS Components 771-0215 (87180-066LF) listing, 11.5 x 13.2 x 18 mm; test-fit one jack (docs/superpowers/specs/2026-11-09-tx-protoboard-stack-design.md) | sourced |
| `hdr_plastic` | 2.5 | male header plastic (board to breakout) | standard 0.1 in header; bench r1 kicad_layout.py SEAT_Z | sourced |
| `breakout_t` | 1.6 | breakout PCB thickness (Adafruit, SparkFun, Seeed) | Eagle files: 1.6 mm default stack; not stated | [TBD-MEASURE] |
| `mux_w` | 40.64 | PCA9548 #5626 length | Adafruit Eagle board, github.com/adafruit/Adafruit-PCA9548-PCB; adafruit.com/product/5626: 40.6 x 20.2 x 4.8 mm | sourced |
| `mux_d` | 20.32 | PCA9548 #5626 width | Adafruit Eagle board, github.com/adafruit/Adafruit-PCA9548-PCB | sourced |
| `mux_h` | 4.8 | PCA9548 #5626 overall height | adafruit.com/product/5626 | sourced |
| `foam` | 1 | double-sided foam pad under the mux | not chosen yet | [TBD-MEASURE] |
| `mini_w` | 49.97 | Wio-E5 mini length | Seeed 'LoRa-E5 mini v1.0.brd' (files.seeedstudio.com/products/113990939/), linked from wiki.seeedstudio.com/LoRa_E5_mini: outline | sourced |
| `mini_d` | 22.99 | Wio-E5 mini width | Seeed 'LoRa-E5 mini v1.0.brd' (files.seeedstudio.com/products/113990939/), linked from wiki.seeedstudio.com/LoRa_E5_mini: outline; wiki 50 x 23 mm | sourced |
| `mini_rows` | 17.78 | Wio-E5 mini header rows, centre to centre (7 x 2.54) | Seeed 'LoRa-E5 mini v1.0.brd' (files.seeedstudio.com/products/113990939/), linked from wiki.seeedstudio.com/LoRa_E5_mini: J1 pads B and D | sourced |
| `mini_module_h` | 2.5 | LoRa-E5 module height | Seeed 'LoRa-E5 mini v1.0.brd' (files.seeedstudio.com/products/113990939/), linked from wiki.seeedstudio.com/LoRa_E5_mini: package MOUDLE28P-1.25-12X12X2.5MM | sourced |
| `mini_sma` | 6.5 | SMA-K body, square | Seeed 'LoRa-E5 mini v1.0.brd' (files.seeedstudio.com/products/113990939/), linked from wiki.seeedstudio.com/LoRa_E5_mini: package SMA5P-SMD-5.1-6.5X6.5X16.5MM | sourced |
| `mini_sma_out` | 12.3 | SMA beyond the mini's edge | 16.5 mm package length from the ANT pad's inner end at x 45.8 (Seeed 'LoRa-E5 mini v1.0.brd' (files.seeedstudio.com/products/113990939/), linked from wiki.seeedstudio.com/LoRa_E5_mini); the brd's doc layer disagrees: measure | [TBD-MEASURE] |
| `mini_usbc_h` | 3.2 | USB-C receptacle height above the mini | typical mid-mount Type-C; part not named in the brd | [TBD-MEASURE] |
| `usbc_plug` | 7 | USB-C plug overmould thickness (console cable) | typical cable; measure Clint's | [TBD-MEASURE] |
| `shtc3` | 25.4 x 17.78 | SHTC3 #4636 outline | Adafruit Eagle board, github.com/adafruit/Adafruit-SHTC3-PCB | sourced |
| `ina228` | 25.4 x 20.32 | INA228 #5832 outline | Adafruit Eagle board, github.com/adafruit/Adafruit-INA228-PCB | sourced |
| `max17048` | 25.4 x 20.32 | MAX17048 #5580 outline | Adafruit Eagle board, github.com/adafruit/Adafruit-MAX17048-PCB | sourced |
| `qt_lead_h` | 14 | QT lead male-pin housing height (#4209) | premium jumper housing; measure | [TBD-MEASURE] |
| `qt_h` | 2.9 | STEMMA QT (JST SH) socket height | bench r1 kicad_layout.py qt_socket | [TBD-MEASURE] |
| `jstph_h` | 6 | JST PH 2-pin socket height (MAX17048) | KiCad JST_PH_B2B-PH-K model; bench r1 model_gauge | sourced |
| `s7v8f3` | 11.43 x 16.51 | Pololu S7V8F3 outline | bench r1 build.py SIZE['REG'] (0.45 x 0.65 in); pin order from the board in hand | sourced |
| `s7v8f3_h` | 3 | S7V8F3 tallest part (inductor) | bench r1 kicad_layout.py model_reg | [TBD-MEASURE] |
| `ptc` | 7.4 x 3.1 x 12.7 | MF-R010 body W x T x H (max), leads 5.08 | Bourns MF-R datasheet table, via distributor listings | sourced |
| `res_v_h` | 9 | 10 kohm standing (P5.08 vertical) height | KiCad R_Axial_DIN0207 vertical model, L 6.3 + lead | derived |
| `cap_h` | 6 | 100 nF disc height | KiCad C_Disc_D3.8mm model, D 3.8 + lead | derived |
| `pack` | 69 x 54 x 18 | battery pack #353 | INVENTORY.md / docs/current-system.md (SHOP:49) | sourced |
| `evm` | 88.9 x 63.5 x 15 | BQ25798EVM outline and tallest part (placeholder until measured) | docs/superpowers/specs/2026-11-09-tx-protoboard-stack-design.md 'Measurements still needed' 2 | [TBD-MEASURE] |
| `ra_offset` | 1.52 | right-angle header: hole centre to the insulator's back face | Sullins right-angle male header drawing, mfgdatasheets.nlight.net (PRPC018SBAN-M71RC, -M71 single narrow) (.060) | sourced |
| `ra_insulator` | 2.54 | right-angle header insulator, along the mating pins | Sullins right-angle male header drawing, mfgdatasheets.nlight.net (PRPC018SBAN-M71RC, -M71 single narrow) (.100) | sourced |
| `ra_mate` | 5.84 | right-angle header mating pin length beyond the insulator | Sullins right-angle male header drawing, mfgdatasheets.nlight.net (PRPC018SBAN-M71RC, -M71 single narrow) code BA (.230) | sourced |
| `ra_tail` | 3.05 | right-angle header solder tail below the insulator | Sullins right-angle male header drawing, mfgdatasheets.nlight.net (PRPC018SBAN-M71RC, -M71 single narrow) code BA (.120) | sourced |
| `ra_pin_z` | 1.27 | right-angle header pin centre above the card | Sullins right-angle male header drawing, mfgdatasheets.nlight.net (PRPC018SBAN-M71RC, -M71 single narrow): insulator .100 square on the board | derived |
| `socket_h` | 8.5 | Sullins PPPC181LFBN-RC body, backplane face to mouth | Sullins PPPC female header drawing (PPPC181LFBN-RC), sullinscorp.com | sourced |
| `socket_w` | 2.54 | Sullins PPPC socket body width (single row) | Sullins PPPC female header drawing (PPPC181LFBN-RC), sullinscorp.com | sourced |
| `socket_tail` | 3 | socket solder tail beyond the backplane copper | Sullins PPPC female header drawing (PPPC181LFBN-RC), sullinscorp.com: .118 tail; check on the part | [TBD-MEASURE] |
| `insertion` | 5 | chosen pin insertion into the socket (5.84 available; 0.84 left for print tolerance) | layout rule | derived |
| `card_bp_gap` | 1.97 | card back edge to backplane face | 39.37 (column j) + 1.52 + 2.54 + 5.84 - 5.0 + 8.5 - 50.8 | derived |
| `strip_pitch` | 2.54 | BusBoard ST2 stripboard: hole pitch, strips run the length | BusBoard ST2 stripboard, busboardcom.busboard.us/ST2 (DigiKey 4526-ST2-ND) | sourced |
| `strip_size` | 100 x 80 x 1.6 | BusBoard ST2 stripboard, 31 strips x 39 holes (cut to 21 strips wide) | BusBoard ST2 stripboard, busboardcom.busboard.us/ST2 (DigiKey 4526-ST2-ND) | sourced |
| `bp_posts` | 7 | backplane copper face above the cage back plate (mux, foam and socket tails behind it) | layout choice | derived |
| `cage_plate` | 3 | cage back plate thickness (PLA) | layout choice | derived |
| `cage_wall` | 4 | cage left wall thickness; card slots 2 mm deep | layout choice | derived |
| `slot_clear` | 0.3 | card slot width over the 1.6 mm card (print tuning) | Bambu H2D PLA first-print allowance; tune on a test slot | [TBD-MEASURE] |
| `bar` | 3 | retention bar thickness in front of the card front edges | layout choice | derived |
| `tails` | 1.5 | solder tails and bottom-side wires below a card | typical; measure after the first card | [TBD-MEASURE] |
| `clear` | 0.5 | minimum clearance kept between parts | layout rule | derived |
| `bob_spacer` | 2 | printed spacer under each RJ11 breakout (bonded to the card) | layout choice | derived |
| `do35` | 4.56 x 2 | DO-35 body length x diameter (1N5232B, BAT85S) | onsemi 1N5221B series and Vishay BAT85 (doc 88146) outline DO-35/DO-204AH | sourced |
| `diode_stand_h` | 7 | standing DO-35 height (body on one lead, the other looped over) | 4.56 body + 1 lead + loop; check on the part | [TBD-MEASURE] |
| `r_lying_h` | 2.5 | lying DIN0207 resistor height (body diameter) | KiCad R_Axial_DIN0207_L6.3mm_D2.5mm model | derived |
| `lug` | 13.5 x 1.93 | Keystone 7328 ring solder lug length x thickness | DigiKey 36-7328-ND listing (verify on the part) | [TBD-MEASURE] |
| `box_out` | 125 x 175 x 75 | #905 box outside: width x height (hanging, long side up) x depth | docs/superpowers/specs/2026-11-09-tx-protoboard-stack-design.md; adafruit.com/product/905 | sourced |
| `box_in` | 119 x 169 x 69 | #905 box inside: width x height x depth back wall to closed lid | assumed 3 mm walls: measure | [TBD-MEASURE] |
| `boss` | 8 x 8 x 6 | #905 inside corner bosses: centre from the side walls (x, z) and diameter | not published: measure | [TBD-MEASURE] |
| `power_zone` | 92 | box bottom to the lowest card (pack cradle, charger slot, glands' cable bend) | layout choice | derived |
| `gland` | 12.5 x 19 | PG-7 cable gland: panel hole x nut across corners | typical PG-7 (12.5 mm hole); confirm with the glands bought | [TBD-MEASURE] |
| `plug_len` | 25 | RJ11 plug and cable bend beyond the jack mouth | mechanical review M6 (service loop); measure a plug | [TBD-MEASURE] |
| `sma_ra` | 10 x 15 | Amphenol RF 132172 right-angle adapter: arm lengths | amphenolrf.com/132172.html drawing; verify | [TBD-MEASURE] |
<!-- dimensions:end -->
