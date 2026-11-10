# TX card cage r3: Wio-E5 mini TX on four SolderFul cards and a backplane

> **Status (2026-11-10):** this r3 is laid out in the stock #905 (TIBOX) base, with the charger EVM at the old 80 x 80
> estimate. Clint measured it at 90 x 90 (96 across J8), which does not fit with 2 mm margins here; a printed,
> deeper base that mates with the #905 lid is being studied. The cards, backplane, routing and mechanical table
> carry over to it.

The transmitter is four SolderFul SOLDERBREAD#02 cards, each with its two back rails snapped off (81.3 x 41.91 mm
`[TBD-MEASURE]`), standing as horizontal shelves in a printed card cage in the Adafruit #905 box (TIBOX 125 x 175
x 75: a 50 mm body and a 25 mm clear lid tray; inside 121 x 169, 48 deep in the body, about 72 closed). The box
hangs on its pole by its floor (the back wall), long side vertical; the cage base sits on the box's eight floor posts
and screws to six of them; the cable glands are in the right wall below the jacks and the SMA bulkhead is in the
right wall near the top. Each card
carries a right-angle 18-pin header on its back edge, its mating pins out past the snapped edge, that plugs into a
socket on a PAD3U padboard backplane, so any card slides out toward the lid on its own. Battery current never
passes through the backplane, a strip, a header or a socket.

| Card (bottom to top) | Role | What it carries |
|---|---|---|
| B4 | POWER | The battery monitor INA228 (0x40), the fuel gauge MAX17048 (0x36), the S7V8F3 3.3 V regulator and the battery + lug (Keystone 7328). |
| B2 | PORTS B + METERS | Sensor port 4 and the wind and rain jacks, with the meter pull-ups, filters, clamps and 1 k series resistors. |
| B1 | PORTS A | Sensor ports 1-3: each a jack breakout, an MF-R010 fuse, 100 ohm series resistors and BAT85S / 1N5232B clamps. |
| B3 | CORE | The Wio-E5 mini on its header, the enclosure air sensor SHTC3 (0x70) and a right-angle SWD header at the front edge. |
| backplane | bus | BusBoard PAD3U padboard (a pad per hole, no strips) cut to 21 x 39 holes; a tinned bus wire on the copper side carries each of the 18 lines; four Sullins sockets, the PCA9548 mux (0x71) behind it on foam, the four QT leads to the ports and the charger I2C pins. |
| power zone | below the cards | The BQ25798EVM standing parallel to the floor in a printed edge cradle in front of the backplane, the battery pack standing on a printed tray in front of it; on leads to B4. |

The bus header is Sullins PRPC040SBAN-M71RC (right angle, 1x40, cut to 1x18; the 1x18 PRPC018SBAN-M71RC is no
longer sold at DigiKey, same drawing) into Sullins PPPC181LFBN-RC (1x18 female) on the backplane. The card ends at
the snap line (card Y 41.91 `[TBD-MEASURE]`); the header insulator ends at 43.43, its mating pins at 49.27 (7.36
past the edge); the socket mouth is at 44.27, 2.36 mm clear of the card and 0.84 mm clear of the insulator (the
depth stop); 5.00 mm of the 5.84 mm mating pin goes in, and the card's edge sits 10.86 mm from the backplane. All
checked in L5.

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
| `layout/route.py` | Routes every wire, jumper and lead on its card: flat, on a 1.27 mm grid, right-angle runs, every part footprint an obstacle; the cut lengths come from the routes. |
| `layout/layout_checks.py` | Layout checks L1-L9 (below); `--write` rewrites the mechanical table in this README. |
| `cage/cage.py` | The printed cage: base plate (120 x 157) on the box's eight floor posts, screwed to A1, A2 and B1-B4, left wall with card slots, right corner post, backplane posts, retention bar, charger standoffs, pack tray; the box's own keep-outs (corner screw posts, floor posts, D tabs, ribs); the glands and their pitch check. `--solid` builds the solids in CadQuery and checks they are valid. No STL yet. |
| `layout/drawings.py` | Writes `drawings/B1..B4-top.svg`, `drawings/backplane.svg`, `drawings/cage-side.svg`, and the build sheets `build/B1..B4.md`, `build/BACKPLANE.md`, `build/ASSEMBLY.md`. `--png` also writes PNG copies into `renders/`. |
| `build/ASSEMBLY.md` | The charger jumper steps before any power, the cage, the card order and the leads off the cards. |
| `build/B1..B4.md`, `build/BACKPLANE.md` | Build sheets: the snap-off first, underside wires with routed lengths, top jumpers, parts lowest first with orientation, leads, strip map, checks before power; the backplane's cut, bus wires and hole-by-hole table. |
| `render/fetch_models.py` | Fetches the makers' STEP files and two Eagle board files into `render/models/` (not committed), checks each SHA-256, and builds the two boards into STEP with KiCad. |
| `render/MODELS.md` | Every part in the renders: its model source, real / imported / stand-in, and why; the login-only models and where to put them. |
| `render/kicad_render.py` | Writes the KiCad boards `render/kicad/tx-stack-B1..B4.kicad_pcb` and `tx-stack-cage.kicad_pcb` and renders them with `kicad-cli pcb render`, each PNG with a legend naming its stand-ins. |
| `renders/*.png` | Every render and a PNG copy of every drawing. |

### Renders and their stand-ins

- Drawings: `block-diagram`, `B1..B4-top` (with the routed wires), `backplane`, `cage-side`.
- KiCad per card: `B1..B4-render-top`, `B1..B4-render-bottom` (the underside wires; labels read from below),
  `B1..B4-render-iso`.
- KiCad assembly: `cage-render-iso`, `cage-render-front`, `cage-render-exploded` (the cards pulled 45 mm toward the
  lid), `cage-render-section` (B1, its header and socket, cut at bus line 9, seen from the right).
- Every model, its source and why it is or is not real: `render/MODELS.md`. Each PNG's legend names its stand-ins.

## Regenerating

```sh
./run.sh                               # everything, with all checks
sh schematic/run.sh                    # schematic + checks 1-10 only
python3 layout/layout_checks.py        # layout checks L1-L9 only (--write: the mechanical table)
python3 cage/cage.py [--solid]         # the cage against the box inside
python3 layout/drawings.py --png       # drawings + build sheets (+ PNGs)
python3 -I render/fetch_models.py      # makers' models (once; the renders fall back to boxes offline)
python3 -I render/kicad_render.py [--no-render]
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

- **L1:** every pin on a hole, every conductor end a real hole or pad, no hole doubled, nothing under a spacer; every backplane bus wire soldered only at real holes of its own line.
- **L2/L3:** the copper equals the schematic; no strip (card) and no wire-joined pad group (backplane: the PAD3U has no strips, nothing connects unless a wire does) carries two nets (checked without part-internal ties).
- **L4:** no battery net touches a strip.
- **L5:** the bus is on rows 1-18 of column j on every card and bus wires 1-18 of the backplane; insertion 5.00 mm of 5.84 (at least 4.20 with the card 0.8 mm short); the socket body never overlaps the snapped card (2.36 mm clear).
- **L6:** no two part bodies collide on a card.
- **L7:** each card pitch clears the tallest part below, its tails and 0.5 mm; nothing collides with the cage, the backplane, another card or the box's corner screw posts, floor posts, D tabs and ribs; each card slides out alone; everything fits the box inside; the power zone stays under B4; the mux stays clear of the socket tails; what sits past the body-lid seam (in the lid tray) is listed.
- **L8:** every routed wire, jumper and lead (81 of 81) runs on its side of the card in right-angle runs, crosses no part footprint (a pad lead only its own breakout), passes over no used hole but its own ends, and shares no grid run with another conductor except an insulated lead bundle (at most 3); a bare jumper meets nothing.
- **L9:** every mating and fixing in the table below; the slot play against the socket lead-in, the room over each plug's latch, the SMA path and the cage screws' access are computed, and anything held by solder or adhesive alone or reachable only after something else comes out is flagged.

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

## What changed in r3, and why

- **Back rails snapped off** each card (`sb_snap_y`, card Y 41.91 `[TBD-MEASURE]`) before any soldering, the edge
  filed flat. The header's mating pins now stand 7.36 mm past the edge into the socket; the card edge is 10.86 mm
  from the backplane. The back RJ11 breakout on B1 and B2 overhangs the snapped edge by 4.8 mm: its printed spacer
  carries a tongue in the card plane that the right corner post grips; the post is cut away round that jack and
  plug.
- **Backplane on a BusBoard PAD3U padboard** (pad per hole): 18 tinned bus wires, each soldered at every pin of its
  line; cut step and hole-by-hole table in `build/BACKPLANE.md`; screw holes at lines 0 and 20, holes 2 and 36.
- **Wires routed** (`layout/route.py`) instead of drawn straight: lengths, drawings and renders follow the routes.
- **Box from the maker's catalogue and Clint's floor sheet (M1-M13):** TIBOX 125 x 175 x 75; inside 121 x 169
  (M1 + 2 x M5, M2 + 2 x M6), 48 deep in the body (M12), about 72 closed (48 + 25 less a 1 mm gasket allowance).
  The cage base (120 x 157, the maker's DS-1217P length) sits on the eight 7 mm floor posts over the 1 mm ribs,
  screws to A1 and A2 (M4 brass inserts, M4 x 10) and B1-B4 (blind, M3 self-tappers); notched for the D tabs, the
  corner screw posts (15 mm) and the gland nuts; a window behind the backplane lets the socket tails and the mux
  reach down into the 7 mm under it.
- **Power zone re-planned for the measured EVM (about 80 x 80, TI SLUUCB5 Fig. 4-1):** it stands parallel to the
  floor in a printed edge cradle in front of the backplane (it has no mounting holes; the Bumpon feet come off),
  the pack standing in front of it; the glands moved to the
  right wall (PG-7 #762 and PG-9 #761, from Adafruit's drawing), with a gland-to-gland pitch check.
- **Renders:** imported BOB-14021 and Wio-E5 mini boards, the Adafruit PCA9548 STEP, the header drawn with its
  pins bent, routed wire tubes, bottom views, an exploded cage and a section; `render/MODELS.md`.

## Not yet ordered

Everything the build needs that is in neither the DigiKey cart (2026-11-09) nor `INVENTORY.md`. Stock and price
from digikey.ca on 2026-11-10; quantities include spares. On hand per `INVENTORY.md`, so not listed: the two M4 x 10
socket-head screws and washers for A1, A2 (the 450-piece M4 kit), the M3 nylon screw and nut for the lug (the nylon
M2/M3/M4 kit), the M3 screws for the backplane and the bar, and the RJ12 6P6C crimp plugs (100, generic; modelled as the
standard 6P body after Cinch 32-5996UL).

| Part | Maker part | DigiKey | Need | Buy | Stock | Price (CAD, 1 off) | Note |
|---|---|---|---|---|---|---|---|
| Right-angle bus and SWD header, 1x40 | Sullins PRPC040SBAN-M71RC | S1111EC-40-ND | 77 pins (4 x 18 + 5) | 3 | 5,728 | 2.97 | cut to length; replaces PRPC018SBAN-M71RC (no longer sold) |
| Backplane socket, 1x18 female | Sullins PPPC181LFBN-RC | S7051-ND | 4 | 6 | 5,847 | 1.74 | |
| Signal clamp diode | Vishay BAT85S-TR | BAT85SCT-ND | 16 | 20 | 44,459 | 0.74 | |
| Zener clamp 5.6 V | onsemi 1N5232BTR | 1N5232BFSCT-ND | 7 | 10 | 86,084 | 0.25 | |
| Series and sense resistor 100 ohm | Stackpole CF14JT100R | CF14JT100RCT-ND | 10 | 15 | 308,663 | 0.16 | the Yageo kit has 5; the cart's CF14JT1M00 (1 Mohm, 50) matches no part here: check that line |
| Battery lug | Keystone 7328 | 36-7328-ND | 1 | 3 | 25,100 | 0.33 | |
| SMA right-angle adapter (AD1) | Amphenol RF 132172 | ACX1249-ND | 1 | 1 | 10,603 | 20.40 | needed (a straight plug does not fit, L9), but the coax path is unresolved: order after it is |
| Tinned bus wire, 22 AWG solid | Alpha Wire 298 SV005 | 298SV005-ND | about 1.6 m | 1 spool (30.5 m) | 309 | 147.28 | or strip the 22 AWG solid hookup wire on hand, if it is solid |
| Cable glands PG-7 (round port cables) and PG-9 (flat weather-meter cables, seal out, packed) | Adafruit #762 and #761 (Clint has one of each), or LAPP 53111000 (M12) for the PG-7s | 2181-53111000-ND | 6 PG-7 + 2 PG-9 | 5 PG-7 + 1 PG-9 | LAPP not stocked (2 weeks) | bulk only | plus silicone or split grommets for the two flat cables |
| Self-tapping screws into the B posts (blind) | M3 (or No. 4) for plastic, 10 mm | - | 4 | 6 | - | - | the bore is not measured |
| JST PH 2-pin socket with leads (pack pigtail) | any | - | 1 | 2 | not checked | - | DigiKey number not found in this pass |
| USB-C to micro-B cable (EVM J6) | any | - | 1 | 1 | not checked | - | |
| Hook-and-loop strap (pack), foam tape (mux) | any | - | 1 each | 1 each | not checked | - | |

## Mechanical connections

Every mating and fixing: how it is held, what takes the force, how it comes apart. Flagged: anything held by
solder or adhesive alone, or that cannot be reached or removed without taking something else apart first.

<!-- mechanical:begin (generated by layout/layout_checks.py --write) -->
| Mating or fixing | Held by | Force path | Taken apart | Flag |
|---|---|---|---|---|
| Card in its slot | left wall slot (2 mm deep) and the right corner post slot; the retention bar across the front left | the slots take the card's weight and any knock across it; the bar stops it backing out | two M3 screws: bar off, card slides out toward the lid |  |
| Bus header into the backplane socket | 18 contacts' friction; axis Yb (in the card plane, toward the back wall); insertion 5.00 mm of 5.84; the insulator meets the socket 0.84 mm further in (the depth stop) | the socket; side play is the slot's 0.3 mm, inside the socket lead-in (0.5 mm [TBD-MEASURE]) | pull the card straight out toward the lid (bar off first) |  |
| B3 U5 breakout (enclosure air sensor, top card, away from the charger) | its own header, soldered in the breakout and in the card (one row) | the header pins; a QT plug's push goes through the breakout into the header | desolder the header row (or cut the pins and fit a new header) | held by solder alone on one header row |
| B4 U2 breakout (battery monitor) | its own header, soldered in the breakout and in the card (one row) | the header pins; a QT plug's push goes through the breakout into the header | desolder the header row (or cut the pins and fit a new header) | held by solder alone on one header row |
| B4 U6 breakout (fuel gauge) | its own header, soldered in the breakout and in the card (one row) | the header pins; a QT plug's push goes through the breakout into the header | desolder the header row (or cut the pins and fit a new header) | held by solder alone on one header row |
| B4 U7 breakout (3.3 V regulator) | its own header, soldered in the breakout and in the card (one row) | the header pins | desolder the header row (or cut the pins and fit a new header) | held by solder alone on one header row |
| B1 J11 RJ11 breakout | bonded to its printed spacer, the spacer bonded to the card; its six pads take flying leads to the card (no pin goes into the card); the spacer's tongue sits in the right corner post slot | the plug's push and pull run along the jack axis (Xb) through the jack and the breakout into the two bonds and the post; the latch takes the pull | unsolder the six leads at the card; cut the spacer bond | held by adhesive alone (the post takes the push on this one) |
| B1 J12 RJ11 breakout | bonded to its printed spacer, the spacer bonded to the card; its six pads take flying leads to the card (no pin goes into the card) | the plug's push and pull run along the jack axis (Xb) through the jack and the breakout into the two bonds; the latch takes the pull | unsolder the six leads at the card; cut the spacer bond | held by adhesive alone: the plug's push and pull load the bond |
| B1 J13 RJ11 breakout | bonded to its printed spacer, the spacer bonded to the card; its six pads take flying leads to the card (no pin goes into the card) | the plug's push and pull run along the jack axis (Xb) through the jack and the breakout into the two bonds; the latch takes the pull | unsolder the six leads at the card; cut the spacer bond | held by adhesive alone: the plug's push and pull load the bond |
| B2 J14 RJ11 breakout | bonded to its printed spacer, the spacer bonded to the card; its six pads take flying leads to the card (no pin goes into the card); the spacer's tongue sits in the right corner post slot | the plug's push and pull run along the jack axis (Xb) through the jack and the breakout into the two bonds and the post; the latch takes the pull | unsolder the six leads at the card; cut the spacer bond | held by adhesive alone (the post takes the push on this one) |
| B2 J21 RJ11 breakout | bonded to its printed spacer, the spacer bonded to the card; its six pads take flying leads to the card (no pin goes into the card) | the plug's push and pull run along the jack axis (Xb) through the jack and the breakout into the two bonds; the latch takes the pull | unsolder the six leads at the card; cut the spacer bond | held by adhesive alone: the plug's push and pull load the bond |
| B2 J22 RJ11 breakout | bonded to its printed spacer, the spacer bonded to the card; its six pads take flying leads to the card (no pin goes into the card) | the plug's push and pull run along the jack axis (Xb) through the jack and the breakout into the two bonds; the latch takes the pull | unsolder the six leads at the card; cut the spacer bond | held by adhesive alone: the plug's push and pull load the bond |
| RJ11 plug latch and cable | the jack latch; the latch is on the plug, 4.5 mm free over the tightest plug (B1 J11 RJ11 plug (standard 6P body after Cinch 32-5996UL)); each cable turns down beyond the plug in the 12.7 mm column to the right wall and runs down past the charger to its PG-7 gland in the right wall, below the jacks | the latch, then the gland's seal (strain relief) | press the latch (lid open, from the front), pull; loosen the gland nut to pull the cable through | less than 8 mm [TBD-MEASURE] over the plug to press its latch from above: B1 J11 4.5, B2 J14 4.5 mm (a small screwdriver from the front instead) |
| Wio-E5 mini on B3 | soldered on its own 2 x 12 header (not in sockets) | the header pins | desolder 24 pins | held by solder alone; cannot come off without desoldering 24 pins |
| Wio-E5 mini USB-C console | the receptacle's friction; cable plugged from the left with the lid open | the mini's receptacle and its header | pull the plug |  |
| SMA, adapter and coax to the bulkhead | AD1 screwed on the mini's SMA-K, its arm up; the 135110 plug screwed on AD1; the bulkhead jack nut in the right wall near the top | the coax is clipped to the cage at its bend so a pull on it reaches the bulkhead, not the mini's SMA | unscrew the plug at AD1 (8 mm spanner), then lift B3 out | the coax does not fit: 4.1 mm over the adapter arm, the straight plug and the bend need 34.2 (all [TBD-MEASURE]); AD1's arm also meets the box's corner screw post; unresolved |
| Battery lug E1 on B4 | Keystone 7328 on an M3 nylon screw and nut through the right centre hole | the screw; the 22 AWG leads are soldered to the lug tail and sleeved | undo the nut |  |
| Battery pack | stands on its long edge on the pack tray in front of the charger; a hook-and-loop strap through the tray | the tray's front lip and the strap | open the strap, unplug the JST PH |  |
| Charger (BQ25798EVM) | an edge cradle (the board has no mounting holes): its bottom edge in a groove on the pack tray, its side edges in two channels, snap clips at the front; the Bumpon feet (H1-H4, 3M SJ-5303) peeled off first | the channels and the groove; the terminal screws are tightened from the lid side against the cradle | take the pack out, unscrew the leads at its terminals, flex the clips, lift it toward the lid | the left channel stops under the backplane: the upper left corner is held only by the board itself |
| B4 and the charger | B4's battery and sense leads are screwed into the EVM terminals | the terminal screws | unscrew the leads at the EVM before B4 slides out | B4 is tethered to the charger by its leads: unscrew them first |
| Backplane on its posts | four M3 screws through lines 0 and 20 into the printed posts | the posts take the card insertion push | undo the four screws, after every card is out | removable only after all four cards are out |
| Cage to the box | the base plate on the A, B and C posts (7 mm, over the 1 mm ribs); an M4 x 10 socket-head screw and washer into each A brass insert, an M3 self-tapper into each blind B post (size [TBD-MEASURE]); notched for the D tabs and the corner posts | six screws; the D tabs locate it; C1 and C2 bear only | undo the six screws after what covers them is out | the screws are behind BQ25798EVM (standing, outline TBD); battery pack #353 (standing); cage backplane posts; cage charger cradle; cage pack tray; cage retention bar; card B1; card B3: the cage comes out last |
| Cables through the glands | six round port cables in PG-7s (#762, seal 3.0-4.3 mm); the flat wind and rain cables in PG-9s (#761) with the seal out and the gap packed with silicone or a split grommet | the gland's seal (round) or the sealant (flat); a drip loop below each gland outside, so water runs off the loop and not along the cable into the gland | loosen the cap (round); cut the sealant (flat) | a flat cable is sealed once its position is final and then comes out only by cutting the seal |
<!-- mechanical:end -->

## Deferred, with reasons

- **Sensor-power switch on PA9 (electrical M3).** No orderable through-hole current-limited switch was found; the
  pin is marked "not wired" in the model. A short on one port still browns out the 3.3 V supply until its MF-R010
  trips.
- **Firmware README profile and pin notes (m10).** Outside this directory; left for a firmware change.

## Open questions

- **The coax does not fit (L9 flag).** A straight plug on the mini's SMA needs 32.7 mm to the right wall and has
  23.4, so AD1 is needed; but over AD1's up arm there are 4.1 mm where the plug and the RG-316 bend need 34.2, and
  the arm meets the upper right corner screw post (the bulkhead as drawn also sits in that post). Options: move the
  mini about 5 rows left on B3 (then a straight plug fits, no AD1; U5 moves), or a right-angle plug cable. Lowering
  the stack is no longer open: the standing EVM leaves 4.1 mm under B4.
- **RJ11 latches:** less than 8 mm `[TBD-MEASURE]` over two plugs (B1 J11, B2 J14: 4.5 mm): press
  them with a small screwdriver from the front, or test with a real plug.
- **The charger EVM fit.** Standing parallel to the floor, the EVM (about 80 x 80 +-5 `[TBD-MEASURE]`, scaled
  from TI SLUUCB5 Fig. 4-1) leaves 4.1 mm under B4; lying on the bottom wall it would need about 107 mm of the 72
  mm depth. Measure the board and its tallest part (J1-J5, J9) before printing the cradle.
- **The cage comes out last.** Its six screws are behind the charger, the pack, the backplane posts, B1 and B3.
- **The mux clears C1's top by 0.2 mm** in the window behind the backplane: check with the foam pad chosen.
- **Glands and cables.** The weather-meter cables are flat (about 2.3 x 6.6, derived from TE 5-555042-3's cable
  entry): each goes through a PG-9 (bore 10.5 with the seal out; 7.0 across the cable plus 0.5 mm of sealant a side
  fits) packed with silicone or a split grommet, sealed only once the cable's position is final. The round port
  cables take PG-7s (3.0-4.3 mm): measure them. A drip loop below every gland.
- **Clint's two existing BOB-14021s** carry the 4UCON 14869 jack, 15.70 mm high: too tall under the next card
  (21.3 mm needed, 18.72 there). The cards use new BOBs with the 87180-066LF (11.5 mm, RS listing).
- **Thermistor bias.** The #372 NTC is B 3950; the EVM's TS divider assumes a 103AT (B 3435). Read TS at room temperature before the first charge (build/ASSEMBLY.md).
- **Mini back-feed.** The mini's AP2112 is back-fed from the bus 3.3 V; with USB-C in for the console two regulators run in parallel (accepted, electrical m3).
- **B4 tether.** B4 carries the battery and SYS leads to the EVM; unscrew them at the EVM before B4 slides out.

## Measurements for Clint

The box is measured (Clint, by hand, 2026-11-10, his floor sheet M1-M13): M1 145, M2 92, M3 100, M4 92, M5 12,
M6 14-15, M7 ribs 1 mm high, M8 and M10 posts 7 mm, M9 M4 (confirmed), M11 B and C blind, M12 48; inside 121 x 169
derived. Still `[TBD-MEASURE]`, each a named input in `sources.py`:

1. The B post bore for the self-tappers (`b_screw`).
2. The rib width (`m7_rib`), the D tab positions (`d_tab`), the post diameter (`post_d`), and the closed depth's
   gasket allowance (`gasket`).
3. The BQ25798EVM outline and its tallest part (`evm`), and J8's reach past the edge (`evm_j8`).
4. The snap line: card Y of the cut between column j and the inner back rail (`sb_snap_y`).
5. The card slot fit on a printed test slot (`slot_clear`); the socket's lead-in (`align_tol`).
6. Solder tails and underside wires below a card, after the first card (`tails`).
7. The Sullins socket's solder tail (`socket_tail`); a standing DO-35 diode's height (`diode_stand_h`).
8. The PG-9 locknut across corners (`gland_pg9_nut`); the PG-7's lengths are scaled from the PG-9 (`gland_pg7`).
9. Each round port cable's outer diameter (PG-7: 3.0-4.3 mm) and the flat meter cable's size (`flat_cable`, `sealant`).
10. An RJ11 plug, its boot and cable bend (`plug_len`, `plug_bend`), and the room a finger needs over its latch
    (`finger`).
11. The USB-C console plug overmould (`usbc_plug`) and the mini's USB-C height (`mini_usbc_h`).
12. The Amphenol 132172 adapter's arms (`sma_ra`), the mini's SMA overhang (`mini_sma_out`), the 135110 cable's
    straight plug (`sma_plug_len`), the RG-316 bend radius (`rg316_bend`) and the antenna's length (`ant_len`).
13. The QT lead housing height (`qt_lead_h`) and the QT socket height (`qt_h`).
14. The foam pad under the mux (`foam`), the breakout PCB thickness (`breakout_t`) and the S7V8F3's inductor
    (`s7v8f3_h`).
15. The jack height in a test fit (`jack_h`), and each port cable's capacitance (for the 236 pF limit).

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
| `sb_snap_y` | 41.91 | card depth after the back rails are snapped off: the break line between column j (39.37) and the inner back rail (44.45), on the side notches' centre line (41.9) | midpoint of the two hole lines; SolderFul p.2 side notches at 50.8 - 8.9; where it actually breaks: measure | [TBD-MEASURE] |
| `sb_rails` | 3.81 | outer rail from the edge; inner rail 6.35 mm | drawing p.2 measured against the 2.54 grid | derived |
| `bob_w` | 15.24 | BOB-14021 width (along the header) | SparkFun RJ11-Breakout.brd (github.com/sparkfun/RJ11_Breakout, BOB-14021): outline 0..15.24 | sourced |
| `bob_d` | 20.32 | BOB-14021 depth (snap-off tab removed) | SparkFun RJ11-Breakout.brd (github.com/sparkfun/RJ11_Breakout, BOB-14021): outline 0..20.32 | sourced |
| `bob_hdr_y` | 1.27 | header row from the BOB back edge | SparkFun RJ11-Breakout.brd (github.com/sparkfun/RJ11_Breakout, BOB-14021): JP4 at y 1.27 | sourced |
| `bob_peg_y` | 15.24 | jack peg line from the BOB back edge | SparkFun RJ11-Breakout.brd (github.com/sparkfun/RJ11_Breakout, BOB-14021): JP3 at y 15.24 | sourced |
| `jack_w` | 13.2 | 87180 / 54601 jack body width | KiCad 10 footprint RJ12_Amphenol_54601-x06_Horizontal (fab layer); RS 771-0215 listing 13.2 | sourced |
| `jack_d` | 18 | jack body depth (peg line + 7.88 to the mouth) | KiCad 10 footprint RJ12_Amphenol_54601-x06_Horizontal (fab layer): fab -1.23..16.77; RS 18 mm | sourced |
| `jack_h` | 11.5 | jack body height above the BOB | RS Components 771-0215 (87180-066LF) listing, 11.5 x 13.2 x 18 mm; test-fit one jack (docs/superpowers/specs/2026-11-09-tx-protoboard-stack-design.md) | sourced |
| `jack_4ucon` | 13.34 x 20.57 x 15.7 | 4UCON 14869 jack (on Clint's two existing BOB-14021s): width x length x height (15.00 to the shoulder); pins 1.27 stagger, 6.35 outer, rows 2.54 apart, 8.89 from the pegs; pegs 3.20 at 10.16; tails 4.30 | 4UCON drawing 14869 (SparkFun PRT-00132 jack), cdn.sparkfun.com/assets/8/6/5/f/1/RJ11-Datasheet.pdf (SparkFun's STEP is an outdated version: community.sparkfun.com/t/44748) | sourced |
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
| `ra_offset` | 1.52 | right-angle header: hole centre to the insulator's back face | Sullins right-angle male header drawing, mfgdatasheets.nlight.net (PRPC018SBAN-M71RC, -M71 single narrow) (.060) | sourced |
| `ra_insulator` | 2.54 | right-angle header insulator, along the mating pins | Sullins right-angle male header drawing, mfgdatasheets.nlight.net (PRPC018SBAN-M71RC, -M71 single narrow) (.100) | sourced |
| `ra_mate` | 5.84 | right-angle header mating pin length beyond the insulator | Sullins right-angle male header drawing, mfgdatasheets.nlight.net (PRPC018SBAN-M71RC, -M71 single narrow) code BA (.230) | sourced |
| `ra_tail` | 3.05 | right-angle header solder tail below the insulator | Sullins right-angle male header drawing, mfgdatasheets.nlight.net (PRPC018SBAN-M71RC, -M71 single narrow) code BA (.120) | sourced |
| `ra_pin_z` | 1.27 | right-angle header pin centre above the card | Sullins right-angle male header drawing, mfgdatasheets.nlight.net (PRPC018SBAN-M71RC, -M71 single narrow): insulator .100 square on the board | derived |
| `socket_h` | 8.5 | Sullins PPPC181LFBN-RC body, backplane face to mouth | Sullins PPPC female header drawing (PPPC181LFBN-RC), sullinscorp.com | sourced |
| `socket_w` | 2.54 | Sullins PPPC socket body width (single row) | Sullins PPPC female header drawing (PPPC181LFBN-RC), sullinscorp.com | sourced |
| `socket_tail` | 3 | socket solder tail beyond the backplane copper | Sullins PPPC female header drawing (PPPC181LFBN-RC), sullinscorp.com: .118 tail; check on the part | [TBD-MEASURE] |
| `insertion` | 5 | chosen pin insertion into the socket (5.84 available; 0.84 left for print tolerance) | layout rule | derived |
| `card_bp_gap` | 10.86 | snapped card back edge to backplane face | 39.37 (column j) + 1.52 + 2.54 + 5.84 - 5.0 + 8.5 - 41.91 (sb_snap_y) | derived |
| `pad_pitch` | 2.54 | PAD3U hole pitch (a separate pad per hole, no strips) | BusBoard PAD3U Padboard, busboardcom.busboard.us/PAD3U (38 x 62 holes, 0.037 in holes on 0.1 in, 160.02 x 100.08 x 1.6 mm; DigiKey 4526-PAD3U-ND) | sourced |
| `strip_size` | 160.02 x 100.08 x 1.6 | BusBoard PAD3U padboard, 62 holes along 160 mm x 38 along 100 mm; the backplane is a piece 21 x 40 holes cut from it, lines along the 160 mm side | BusBoard PAD3U Padboard, busboardcom.busboard.us/PAD3U (38 x 62 holes, 0.037 in holes on 0.1 in, 160.02 x 100.08 x 1.6 mm; DigiKey 4526-PAD3U-ND) | sourced |
| `pad_margin` | 1.27 | backplane cut edge to the nearest hole centre (cut midway between two hole lines) | half the 2.54 pitch | derived |
| `bus_wire` | 0.64 | tinned copper bus wire for the 18 backplane lines, 22 AWG | AWG 22 = 0.644 mm | sourced |
| `align_tol` | 0.5 | header pin to socket misalignment the socket's lead-in takes | typical 0.1 in female header lead-in; check one card in the cage | [TBD-MEASURE] |
| `finger` | 8 | vertical room needed over a plug to press its latch | a fingertip or a small screwdriver | [TBD-MEASURE] |
| `rg316_bend` | 12.7 | RG-316 minimum static bend radius (the 135110-01 cable) | typical 5 x 2.5 mm OD; not in the Amphenol listing | [TBD-MEASURE] |
| `ant_len` | 100 | ANT-916-CW-HWR length, hinge to tip (render only) | not looked up: TE page refuses scripts; measure | [TBD-MEASURE] |
| `sma_plug_len` | 20 | straight SMA plug and its crimp ferrule on the 135110 cable | typical; measure the cable | [TBD-MEASURE] |
| `bp_posts` | 3 | backplane copper face above the cage base plate; the plate is cut away behind the backplane so the socket tails, bus wires and the mux on its foam reach down into the 7 mm under the plate | layout choice: mux bottom 0.2 over C1's top | derived |
| `cage_plate` | 3 | cage back plate thickness (PLA) | layout choice | derived |
| `cage_wall` | 4 | cage left wall thickness; card slots 2 mm deep | layout choice | derived |
| `slot_clear` | 0.3 | card slot width over the 1.6 mm card (print tuning) | Bambu H2D PLA first-print allowance; tune on a test slot | [TBD-MEASURE] |
| `bar` | 2.5 | retention bar thickness in front of the card front edges | layout choice | derived |
| `tails` | 1.5 | solder tails and bottom-side wires below a card | typical; measure after the first card | [TBD-MEASURE] |
| `clear` | 0.5 | minimum clearance kept between parts | layout rule | derived |
| `tongue` | 6 x 8.89 | printed tongue on the back jack's spacer: width x reach past the snapped edge (to the old 50.8 edge) | layout choice: the right corner post grips its last 1.5 mm | derived |
| `bob_spacer` | 2 | printed spacer under each RJ11 breakout (bonded to the card) | layout choice | derived |
| `do35` | 4.56 x 2 | DO-35 body length x diameter (1N5232B, BAT85S) | onsemi 1N5221B series and Vishay BAT85 (doc 88146) outline DO-35/DO-204AH | sourced |
| `diode_stand_h` | 7 | standing DO-35 height (body on one lead, the other looped over) | 4.56 body + 1 lead + loop; check on the part | [TBD-MEASURE] |
| `r_lying_h` | 2.5 | lying DIN0207 resistor height (body diameter) | KiCad R_Axial_DIN0207_L6.3mm_D2.5mm model | derived |
| `lug` | 13.5 x 0.38 | Keystone 7328 ring solder lug length x thickness (ring for #4 / M3, 3.1 mm hole) | Keystone solder lugs catalogue p.79, keyelco.com/userAssets/file/K75p79.pdf: 7328 .531 long, .015 brass, H .120 | sourced |
| `evm` | 80 x 80 x 15 | BQ25798EVM (BMS034) board outline x tallest part above it, +/-5 mm; no mounting holes; feet H1-H4 3M Bumpon SJ-5303 (11.2 x 5.1) under it, removed in the cradle | outline: TI SLUUCB5 Fig. 4-1 p.15, scaled by the 0.1 in pitch of J8 and J9; parts (SLUUCB5E BOM): J1-J4 On-Shore ED120/2DS, J5 ED120/3DS (5.08 mm terminal blocks), J7 Molex 0393570002, J9 3M N2510-6002-RB, J8 Molex 0022053041, J6 Molex 47346-0001, about 33 jumpers with shunts; 15 covers a 5.08 mm rising-clamp block (about 10-12, makers' drawings not reached) with its wire entry and screwdriver room | [TBD-MEASURE] |
| `evm_j8` | 9 | EVM J8 (right-angle 4-pin) reach past the board edge | TI SLUUCB5 Fig. 4-1 p.15, scaled | [TBD-MEASURE] |
| `box_out` | 125 x 175 x 75 | #905 box outside: width x length x depth (TIBOX 125 x 175 x 75, screw type, clear cover DS-AT-1217) | TIBOX enclosure catalogue, cdn-shop.adafruit.com/datasheets/TIBOX.pdf p.5 row 125x175x75 (+/-1 mm) | sourced |
| `box_split` | 50 x 25 | #905 body depth + clear lid tray depth (the lid is a 25 mm deep tray, same footprint, no lip into the base) | TIBOX enclosure catalogue, cdn-shop.adafruit.com/datasheets/TIBOX.pdf p.5 D1+D2 50+25; Clint, by hand, 2026-11-10: lid about 25 deep, no lip | sourced |
| `wall_t` | 4.5 | #905 wall thickness | Clint, by hand, 2026-11-10: 4-5 mm | sourced |
| `m1_a_span` | 145 | M1: A1 to A2 centre to centre (the brass-insert posts the cage base screws to) | Clint, by hand, 2026-11-10 (floor-measure.jpg): 145, on the long centre line | sourced |
| `m2_b_across` | 92 | M2: B1 to B2 centre to centre, across the box | Clint, by hand, 2026-11-10 (floor-measure.jpg): 92 (the B rectangle assumed centred on the box) | sourced |
| `m3_b_along` | 100 | M3: B1 to B3 centre to centre, along the box | Clint, by hand, 2026-11-10 (floor-measure.jpg): B1-B3 = B2-B4 = 100 | sourced |
| `m4_c_span` | 92 | M4: C1 to C2 centre to centre (figure-8 posts on the cross rib) | Clint, by hand, 2026-11-10 (floor-measure.jpg): 92, at mid-length, assumed in line with the B columns | sourced |
| `m5_a_wall` | 12 | M5: A1 centre to its end wall (inside face) | Clint, by hand, 2026-11-10 (floor-measure.jpg): 12 | sourced |
| `m6_b_wall` | 14.5 | M6: B1 centre to the long wall beside it (inside face) | Clint, by hand, approximate, 2026-11-10 (floor-measure.jpg): 14-15 | sourced |
| `m7_rib` | 1 x 18 | M7: the cross ribs (centre line and mid-length band): height above the flat floor x width; the cage base clears them (it sits on the posts) | Clint, by hand, 2026-11-10 (floor-measure.jpg): 1 mm high; width not given, 18 scaled from the photo | sourced |
| `m8_a_h` | 7 | M8: A post height, flat floor to the top | Clint, by hand, approximate, 2026-11-10 (floor-measure.jpg): about 7 | sourced |
| `m9_a_thread` | 4 | M9: A insert thread; the cage base holes are M4 clearance (4.5 mm); M4 x 10 socket-head screw (3 mm plate + 0.8 washer + about 6 engaged) | Clint, 2026-11-10: M4 confirmed | sourced |
| `m10_bc_h` | 7 x 7 | M10: B and C post heights, floor to top (the cage base sits on them and on A) | Clint, by hand, 2026-11-10 (floor-measure.jpg): 7, the same as A | sourced |
| `m11_bc_through` | 0 | M11: B and C holes right through the back (1 yes, 0 no) | Clint, by hand, 2026-11-10 (floor-measure.jpg): blind screw posts for mounting plates; the cage base screws to B1-B4 | sourced |
| `m12_base_depth` | 48 | M12: base inside depth, rim to the flat floor (the seam is here) | Clint, by hand, 2026-11-10 (floor-measure.jpg): 48 | sourced |
| `m13_inside` | 169 x 121 | M13: inside length x width at the middle (walls not tapered: the same at floor and rim) | length 145 + 2 x 12 = 169 (M1, M5); width 92 + 2 x 14.5 = 121 (M2, M6), Clint by hand 2026-11-10, agreeing with his about 170 x 120 | derived |
| `box_in` | 121 x 169 x 72 | #905 box inside: width x length (up the pole) x depth floor to closed lid (M12 48 + lid 25 less the gasket allowance) | width and length from M1, M2, M5, M6; depth 48 + 25 - 1 (Clint, by hand, 2026-11-10: about 73 closed) | derived |
| `gasket` | 1 | allowance off the closed depth for the lid's seal and fit | assumed; the TIBOX lid seats on a gasket | [TBD-MEASURE] |
| `b_screw` | 3 | screws into the B posts: M3 self-tapping for plastic (or No. 4), through 3.4 mm holes in the base | assumed; the blind post bore not measured | [TBD-MEASURE] |
| `corner_keepout` | 15 | corner screw posts: how far they stick out along each wall from the corner, full depth | Clint, 2026-11-10 (B17 = 15, along the long wall); the diagram's (120 - 90) / 2 = 15 along the short wall agrees | sourced |
| `post_d` | 9 | A, B and C post outside diameter; D tab size | Adafruit #905 diagram (not to scale), cdn-shop.adafruit.com/datasheets/175mmenclosurediagram.pdf p.1 (inside bottom 135.7 x 90 mm straight walls between the corner bosses): 8 mm posts; 9 allows for the photo | [TBD-MEASURE] |
| `d_tab` | 12 x 6 x -24 x -6 | D1, D2 locating tabs: offset (dXb, dZb) of D1 from A1 and of D2 from A2 | Clint's floor photo 2026-11-10 (photo-8524), scaled | [TBD-MEASURE] |
| `mount_plate` | 109 x 157 | maker's mounting plate DS-1217P (W3 x H3): the cage base plate is the same size | TIBOX enclosure catalogue, cdn-shop.adafruit.com/datasheets/TIBOX.pdf p.5 H3 x W3 157 x 109 | sourced |
| `power_zone` | 92 | box bottom to the lowest card (pack cradle, charger slot, glands' cable bend) | layout choice | derived |
| `gland` | 12 x 16.6 | PG-7 (#762) gland: panel hole x nut across corners | hole: the 11.5 mm screw end (Adafruit #762 PG-7 gland, adafruit.com/product/762) + 0.5; nut: the PG-9's 22 scaled by 11.5 / 15.2 | derived |
| `gland_pg7` | 11.5 x 6 x 16.6 x 11.4 x 3 x 4.3 | PG-7 (#762): thread, thread length inside (L1), body outside (L2), cap (L3), cable min, max | Adafruit #762 PG-7 gland, adafruit.com/product/762: 11.5 mm screw end, cable 0.118-0.169 in; L1, L2, L3 the PG-9's scaled by 11.5 / 15.2 | derived |
| `gland_pg9` | 15.2 x 7.9 x 22 x 15.1 x 4 x 6.4 | PG-9 (#761): thread D1, thread length inside L1, body outside L2, cap L3, cable min, max | Adafruit #761 PG-9 gland drawing, cdn-shop.adafruit.com/product-files/761/761diagram.jpg; cable 0.158-0.252 in from adafruit.com/product/761 | sourced |
| `gland_bore` | 7.9 x 10.5 | gland bore with the seal out: PG-7, PG-9 (D2) | Adafruit #761 PG-9 gland drawing, cdn-shop.adafruit.com/product-files/761/761diagram.jpg: D2 10.5; PG-7 scaled by 11.5 / 15.2 | derived |
| `flat_cable` | 2.3 x 6.6 | weather-meter flat cable, thickness x width (Clint: the meter cables are flat) | TE 5-555042-3 flat-cable plug's cable entry, commscope.com/globalassets/digizuite/67464-p360-5-555042-3-external.pdf (not downloaded) | derived |
| `sealant` | 0.5 | silicone or split grommet round a flat cable in an open gland bore, each side | assumed | [TBD-MEASURE] |
| `gland_pg9_nut` | 22 | PG-9 locknut and cap across corners | not on the drawing (not to scale); typical 19 mm across flats | [TBD-MEASURE] |
| `plug_6p` | 9.65 x 6.6 x 7.47 x 13.34 | 6P plug body: width, height, height with the latch, length (latch 5.95 long, 2.77 at its tip; contacts 1.02 pitch) | Cinch 32-5996UL (AIM-Cambridge) drawing, static.chipdip.ru/lib/750/DOC011750893.pdf (Mouser's copy): drawn for round cable; the standard 6P body for Clint's generic flat-cable 6P6C plugs | sourced |
| `plug_len` | 25 | RJ11 plug beyond the jack mouth, with the flat cable leaving its rear and bending | the 6P body (plug_6p, 13.34 long, partly inside the jack) and the flat cable's bend (plug_bend); measure one of Clint's plugs | [TBD-MEASURE] |
| `plug_bend` | 10 | modular cable minimum bend radius behind the plug | flat 4- or 6-wire modular cable, typical; measure the weather meter's cable | [TBD-MEASURE] |
| `sma_ra` | 10 x 15 | Amphenol RF 132172 right-angle adapter: arm lengths | amphenolrf.com/132172.html drawing; verify | [TBD-MEASURE] |
<!-- dimensions:end -->
