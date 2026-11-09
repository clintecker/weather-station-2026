# TX stack r1: Wio-E5 mini TX on four SolderFul boards

This is the transmitter built as a stack of four SolderFul SOLDERBREAD#02 boards (81.3 x 50.8 mm), from the
bottom up:

| Board | Role | What it carries |
|---|---|---|
| B1 | PORTS | Four sensor ports S1–S4 (BOB-14021 + 87180-066LF). Each has its own MF-R010 PTC and a QT lead from the mux. |
| B2 | METERS | The wind and rain jacks, the 10k pull-ups and 100 nF caps, and the PCA9548 mux (0x71) on a foam pad. |
| B3 | CORE | The Wio-E5 mini (soldered low), the SHTC3 (0x70), a right-angle SWD header and the Sullins bus socket. |
| B4 | POWER | The INA228 (0x40), the MAX17048 (0x36), the S7V8F3 and the bus pins. The BQ25798EVM and the pack sit beside the stack on leads. |

Everything here is generated, from three sources:

- `schematic/model.py`: the circuit
- `layout/stack.py`: where every part, pin, jumper and wire goes
- `sources.py`: every dimension, with its source

`./run.sh` rebuilds everything and runs every check. It exits non-zero if any step or check fails.

## Files

| Path | What it is |
|---|---|
| `run.sh` | Rebuilds and checks everything below, in order. |
| `sources.py` | Every dimension the drawings use: its value, source and status (sourced / derived / `[TBD-MEASURE]`). It writes the table at the end of this README. `--check` fails if the table is out of step. |
| `schematic/model.py` | The logical schematic: 40 parts and 36 nets. Each pin records how it is contacted (header, socket, solder, JST, ...). It also holds the RJ11 pin maps, the Wio-E5 functions and the ERC waivers, each with a reason. |
| `schematic/kicad_gen.py` | model.py → `tx-stack-r1.kicad_sch`, using the same method as `bench-breadboard-r1`. |
| `schematic/checks.py` | Schematic checks 1–8 (listed below), run against KiCad's netlist and ERC. |
| `schematic/run.sh` | Generates the schematic, runs ERC and the netlist export, exports `tx-stack-r1.pdf`, then runs checks.py. |
| `schematic/tx-stack-r1.pdf` | The schematic, one sheet. |
| `schematic/blockdiag.py` → `drawings/block-diagram.svg` | One-page block diagram: power tree, I2C tree with the mux, meter lines, and the radio and antenna path, all with real part numbers. Its labels come from model.py. |
| `layout/stack.py` | Board geometry (hole grid, strips, notches, mounting holes, standoffs, gaps) and footprints. Footprint coordinates come from each maker's board file (cited in `sources.py`). Also the placements and every conductor. |
| `layout/layout_checks.py` | Layout checks L1–L7 (listed below). |
| `layout/drawings.py` | Writes `drawings/B1..B4-top.svg` (top views, to scale on the hole grid), `drawings/stack-elevation.svg` (side elevation, to scale) and `build/B1..B4.md` (hole-by-hole build lists). With `--png`, it also writes PNG copies into `renders/` (headless Chrome). |
| `build/B1.md` … `build/B4.md` | Build lists to solder from: underside links first, then parts lowest first with pin → hole → net tables, then top jumpers, then leads to other boards, then the strip map. |
| `render/kicad_render.py` | Writes the KiCad 10 boards `render/kicad/tx-stack-B1..B4.kicad_pcb` and `tx-stack-all.kicad_pcb` (the four boards on standoffs at their gaps), then renders them with `kicad-cli pcb render`. |
| `render/kicad/3d/*.wrl` | Generated VRML: labelled boxes for parts with no KiCad model, plus wires, slabs and standoffs. |
| `renders/*.png` | Every render and a PNG copy of every drawing. |

### Renders

**Drawings (PNG copies):**

- `renders/block-diagram.png`
- `renders/stack-elevation.png`
- `renders/B1-top.png`
- `renders/B2-top.png`
- `renders/B3-top.png`
- `renders/B4-top.png`

**KiCad, per board:** `renders/B{1..4}-render-top.png` and `renders/B{1..4}-render-iso.png`.

**KiCad, the whole stack:** `renders/stack-render-iso.png` and `renders/stack-render-front.png`.

KiCad's own STEP models are used where its library has the part:

- the 1x8 socket (PinSocket_1x08)
- the 0.1 in headers under every breakout and the mini
- the right-angle 1x5 SWD header
- the vertical DIN0207 10k resistors
- the 3.8 mm 100 nF discs

The other parts are labelled boxes, generated from the same box list the layout checks use: the BOBs and jacks, the mux, the mini, the SHTC3, INA228, MAX17048, S7V8F3 and PTCs, and the QT leads. KiCad has an RJ12_Amphenol_54601 footprint but no 3D model for it.

## Regenerating

```sh
./run.sh                               # everything, with all checks
sh schematic/run.sh                    # schematic + checks 1-8 only
python3 layout/layout_checks.py        # layout checks L1-L7 only
python3 layout/drawings.py --png       # drawings + build lists (+ PNGs)
python3 render/kicad_render.py [--no-render]
python3 sources.py                     # after changing a dimension: rewrite the table below
```

You need:

- python3 3.11+ with Pillow
- KiCad 10 (`kicad-cli`, with its stock 3D library)
- Google Chrome or Chromium (for SVG → PNG)

A full run takes about a minute; the high-quality KiCad renders are most of it.

## What the checks verify

**Schematic (`schematic/checks.py`):**

1. KiCad's netlist round-trips to model.py, net for net and pin for pin.
2. Every connected pin is in exactly one net and every `nc` pin in none. Every net has at least 2 members.
3. The I2C address map:
   - Upstream of the mux there are no clashes and no 0x50: 0x36, 0x40, 0x6B, 0x70, 0x71.
   - Every 0x50 EEPROM sits behind a mux channel, and no selected channel clashes with the upstream bus.
   - The addresses match the firmware (`i2c_bus.h`, `power_config.h`).
   - The upstream pull-ups stay at 0.97 kΩ or above (1632 Ω).
4. Every port's 3V3 (jack pin 2) comes only through its own MF-R010 from +3V3.
5. No battery-current path runs through a header, socket or strip. Every battery-net member is a soldered lead, an EVM terminal or the pack's JST. The series chain and the sense taps are present.
6. The RJ11 pin maps match:
   - I2C ports: 2 3V3, 3 SDA, 4 GND, 5 SCL
   - wind: 2/3 GND, 4 CUPS, 5 VANE
   - rain: 3 GND, 4 RAIN
7. The Wio-E5 pins match the firmware's `firmware/board/wio-e5/board.toml` (or `board_pins.h`): SDA PA15, SCL PB15, CUPS PC0, VANE PB3, RAIN PB4, MUX_RST PB14.
8. KiCad ERC reports nothing beyond the 48 written waivers.

**Layout (`layout/layout_checks.py`):**

- **L1:** Every placed pin lands on a hole, every conductor end is a real hole or pad, and no hole takes two conductors.
- **L2/L3:** The copper equals the schematic. Each net is one connected piece of strips, pins and wires. No strip carries two nets; this is checked without the part-internal ties, so a tie cannot hide a short.
- **L4:** No battery net touches a strip.
- **L5:** The bus is on the same rows (f–j 23–30: 3V3, GND, SCL, SDA, MUX_RST, CUPS, VANE, RAIN) on B2, B3 and B4. The B3 socket and the B4 pins line up hole for hole.
- **L6:** No two part bodies collide in 3D, and no part sits on a standoff.
- **L7:** Each gap clears the tallest part below it, plus solder tails and 0.5 mm clearance. Pin insertion into the socket is checked. The stack total must fit inside the box (75 outside − 2 walls). The jacks must reach the front edge.

## Decisions that differ from the brief

1. **Gaps are 20 / 20 / 10 mm, not 20 / 10 / 10.** The B2 jacks stand 15.6 mm (header 2.5 + BOB 1.6 + jack 11.5), so a 10 mm B2–B3 gap is 7.6 mm short. The elevation drawing shows it.
2. **The Wio-E5 mini is soldered on its own header** (2.5 mm plastic between), not on sockets. A socketed mini (about 15.8 mm tall) would need a 20 mm B3–B4 gap, which makes the stack 79.5 mm against 75 mm outside. Soldered, B3–B4 keeps 10 mm with the Sullins socket and header (insertion 7.0 mm), and the stack is 69.5 mm.
3. **The PCA9548 is on the B2 front half, on a foam pad, wired by its pads.**
   - Its 5-pin header can't stand in one column without shorting a strip, and B1 has no room.
   - Ports reach it by four #4209 QT leads running down to B1.
   - B1 has no bus column: it takes 3V3 to its back + rail by one wire, and nothing else from the bus.
4. **The standoffs are at the left side notch (0, 41.9), the right centre hole (76.2, 25.4) and the right side notch (81.3, 8.9).** The datasheet shows no corner holes: the board has three Ø3.0 centre-line holes and ten edge half-holes. The centre and left holes are under BOB1/BOB3 and the mini.
5. **INA228 header pins 5–7 (VBUS, VIN−, VIN+) are pulled.** The battery leads solder to the X1 terminal pads, so no battery current reaches a strip.
6. The SWD header is a right-angle 1x5 at a8–a12, pointing at the front.
7. The EVM's INT is not wired and its pull-ups are off. The USB-C console plug fits only with B4 lifted off (a service keep-out, not counted in the gap check).

## Open questions

- **Mounting holes.** The brief says corner holes; the SolderFul datasheet p.2 shows centre-line holes and edge notches. The front-left corner has no standoff, so it is unsupported. Is a fourth support needed, perhaps a nylon spacer on the left centre notch?
- **Soldered mini vs sockets.** Soldering costs the mini's reuse. A low-profile socket strip (about 3 mm) would also fit at 10 mm. Which does Clint want?
- **Box inside depth.** It is taken as 75 − 2 × 2.5 [TBD] = 70 mm, leaving 0.5 mm over the 69.5 mm stack; the floor height of 3 mm is also TBD. Measure the #905 box. If the margin is short, the first part to lose height is the MAX17048's unused JST PH socket (desolder it: −6 mm).
- **BQ25798EVM.** Its outline, its tallest part and its terminals (SLUUCB5) are not measured, so it is not drawn. Where does it mount? On the lid, beside the pack, or on B4's free back half?
- **LDO back-feed.** The mini's AP2112 LDO is back-fed from the bus 3V3. With USB-C plugged in for the console, there are two 3V3 sources. Confirm this is safe, or cut the mini's 3V3 link while on USB.
- **Hardware not yet measured:**
  - the hex size of the Hilitchi standoff kit (5.0 mm across flats assumed)
  - the SMA's protrusion past the mini's edge (12.3 mm assumed; the brd's doc layer disagrees)
  - the QT lead housing height (14 mm)
  - the USB-C plug overmould
- **Sullins sockets.** Only one 1x8 socket is used (B3–B4). The 1x12 sockets meant for the mini are now unneeded and were never ordered.

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
| `evm` | ? x ? x ? | BQ25798EVM outline and tallest part | docs/superpowers/specs/2026-11-09-tx-protoboard-stack-design.md 'Measurements still needed' 2 | [TBD-MEASURE] |
| `socket_h` | 8.5 | Sullins PPPC081LFBN-RC body height | the brief; Sullins PPPC series 8.5 mm | sourced |
| `pin_below` | 8.5 | male pin below the upper board, plastic slid off | the brief | sourced |
| `insertion` | 7 | pin insertion into the socket at a 10 mm gap | 8.5 - (10 - 8.5) | derived |
| `standoff_20` | 20 | M3 brass standoff, B1-B2 and B2-B3 | docs/superpowers/specs/2026-11-09-tx-protoboard-stack-design.md (20 mm spacers, built) + this layout | sourced |
| `standoff_10` | 10 | M3 brass standoff, B3-B4 | docs/superpowers/specs/2026-11-09-tx-protoboard-stack-design.md | sourced |
| `standoff_af` | 5 | standoff hex across flats (clearance uses the corners, 2.89 mm radius) | Hilitchi kit: not published | [TBD-MEASURE] |
| `tails` | 1.5 | solder tails and bottom-side wires below a board | typical; measure | [TBD-MEASURE] |
| `floor` | 3 | B1 above the box floor (standoffs or bosses) | box not measured | [TBD-MEASURE] |
| `box_depth_out` | 75 | #905 box outside depth | docs/superpowers/specs/2026-11-09-tx-protoboard-stack-design.md | sourced |
| `box_wall` | 2.5 | #905 box floor and lid thickness, each | box not measured | [TBD-MEASURE] |
| `clear` | 0.5 | minimum vertical clearance kept between parts | layout rule | derived |
<!-- dimensions:end -->
