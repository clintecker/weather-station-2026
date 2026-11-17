# TX stack r3: Wio-E5 mini TX on four SolderFul cards and a backplane, in a printed base

The transmitter is four SolderFul SOLDERBREAD#02 cards, each with its two back rails snapped off (81.3 x 41.91 mm
`[TBD-MEASURE]`), the BQ25798EVM and the battery pack, all horizontal shelves in one stack inside a printed PETG
base (100 mm deep, 3 mm walls) under the original Adafruit #905 clear lid and its O-ring. The base hangs on its pole
by its back, long side vertical; inside 123.5 x 169.5, 120 deep with the lid closed. Every shelf slides toward the back.
The lid interface is from Clint's photos: a 9 mm rim (3 mm wall, 3 mm O-ring channel, 3 mm wall), the channel
curving in round 22 x 21 mm corner bosses, the screws 10 mm in from the outside edges, the O-ring 2 mm down in its
channel. The base copies it with a 9 mm land, a 2 mm wide sealing lip on the channel's centre line (its height is
not settled: see Open questions, L6), and corner posts with M4 heat-set inserts for
M4 stainless screws on 12 mm washers through the lid's 8 mm holes. The rim follows `cage/lid-rim-spec.md`,
measured off Clint's 300 dpi lid scans (2026-11-11). A whole-rim test ring (`cage/stl/rim-ring.stl`, `cage.py
--ring`, not gated) checks the lip, all four S-curves and the four holes on the real lid first; `cage/cage.py --stl`
refuses the full base until the ring fits and the screws (L1) are settled. The corner coupons r1-r8 and the two edge
strips are history (their STLs and renders stay in `cage/stl/` and `renders/`; the code that made them is in git up to
c5e3281). Each card carries a right-angle 1x30 header
on its back edge, its mating pins out past the snapped edge, that plugs into a socket on a PAD3U padboard
backplane, so any card slides out toward the lid on its own. Each card has one spare pin pulled (B1 27, B2 28, B3 29,
B4 30) and its own socket a key plug in that contact, so a card seats only in its own slot (a colour dot on each card
and slot: B1 blue, B2 green, B3 yellow, B4 red). The battery current crosses a header and its socket only on B4's
doubled pins (19-20 and 21-22, about 0.5 A a contact at 1 A, layout check L4 and schematic check 5); everywhere else
it runs in soldered leads, and it touches no card strip but those pins' own.

| Card (bottom to top) | Role | What it carries |
|---|---|---|
| B4 | POWER | The battery monitor INA228 (0x40), the fuel gauge MAX17048 (0x36), the S7V8F3 3.3 V regulator B4's power pins: pins 19-23 and 26 power, 24-25 its 3.3 V and ground (isolated pads on the backplane); no lead leaves it. |
| B2 | PORTS B + METERS | Sensor port 4 and the wind and rain jacks, with the meter pull-ups, filters, clamps and 1 k series resistors. |
| B1 | PORTS A | Sensor ports 1-3: each a jack breakout, an MF-R010 fuse, 100 ohm series resistors and BAT85S / 1N5232B clamps. |
| B3 | CORE | The Wio-E5 mini on its header, the enclosure air sensor SHTC3 (0x70) and a right-angle SWD header at the front edge. |
| backplane | bus | BusBoard PAD3U padboard (a pad per hole, no strips) its plated end, 31 rows (lines 0-30) x 38 holes, factory edges right, top and bottom; a bare bus wire on the copper side carries each of the 18 lines and B4's six power lines; the battery + junction (lines 21-22) with R7 and R8, short leads to the EVM and the pack, and the charger's own ground lead (J3 GND to line 12); four generic female sockets, every one 1x30 with a key plug in its card's pulled position (on lines 19-30 only B4's power contacts meet a bus wire; the rest, the key plugs' contacts included, sit on isolated pads), the PCA9548 mux (0x71) behind it on foam, the four QT leads to the ports and the charger I2C pins. |
| shelves below the cards | power | The battery pack (lowest, the heaviest part) on a moulded tray, then the BQ25798EVM (90 x 90, J8 toward the lid) on two moulded ledges; on short leads to the backplane's lower end, never to a card. |

The bus header is a generic 2.54 mm right-angle male header cut to 1x30 on every card (rows 1-30 of column j; pin n on backplane line n; the card's key pin pulled) (drawn as the Sullins PRPC drawing; its
mating pin 5.8 nominal, `[TBD-MEASURE]`) into a generic female strip cut to the same length (one position lost at each cut) on the backplane. The card ends at
the snap line (card Y 41.91 `[TBD-MEASURE]`); the header insulator ends at 43.43, its mating pins at 49.23 (7.32
past the edge); the socket mouth is at 44.27, 2.36 mm clear of the card and 0.84 mm clear of the insulator (the
depth stop); 4.96 mm of the 5.8 mm mating pin goes in (at least 4.16 with the card 0.8 mm short), and the card's
edge sits 10.86 mm from the backplane. All checked in L5; the keys in L13.

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
| `layout/layout_checks.py` | Layout checks L1-L13 (below; L12 the handedness: the box frame is left-handed, Xb left to right seen from the lid, lid-centre Y = 61.75 - Xb, so each card goes in as a real card); `--write` rewrites the mechanical table in this README. |
| `cage/cage.py` | The printed base and its moulded cage: the lid interface as named inputs (rim, bosses, L1-L6), a 9 mm land and a tongue that follows the lid's O-ring channel round the corner bosses, corner lands and posts with M4 heat-set inserts for the lid screws, card slots, right corner post, backplane posts, EVM ledges, pack tray, gland bosses, vent, SMA boss, pole lugs, drip edge; the shelf fit checks with 2 mm margins and the gland pitch. `--solid` builds the solids in CadQuery; `--stl` refuses until L1 and the ring fit are sourced; `--ring` writes `cage/stl/rim-ring.stl` (the whole rim from `lid-rim-spec.md`, not gated) and checks it against the spec (mirrors, spans, tangency, hole-to-lip clearance). |
| `cage/shelves-spec.md` | CAD-bot spec for the pack tray and the charger ledges below the cards (enclosure 3, as printed, has none; the next print, v3, adds them). |
| `cage/lid-rim-spec.md`, `cage/lid_rim_spec.py` | The lid rim measured off Clint's 300 dpi scans: outline, the lip's centre line as a segment table, the lip section, the holes. `lid_rim_spec.py` reads it; `sources.py` takes the rim keys from it and `cage.py --ring` builds the ring straight from the table. |
| `cage/ring_views.py` | The ring's dimensioned top view (spans, one corner's segment points and radii, the hole spacing) and iso view, `renders/rim-ring-top.png` and `rim-ring-iso.png` (needs the CadQuery venv). The full base's solids are still boxes: its S has square corners; the ring has the spec's arcs. |
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
python3 layout/layout_checks.py        # layout checks L1-L13 only (--write: the mechanical table)
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
5. The battery current crosses a header and its socket only on two pins or more (B4 pins 19-20 and 21-22); the series chain, the junction and the sense resistors are present.
6. The RJ11 pin maps (sensor ports 2 3.3 V, 3 data, 4 ground, 5 clock; wind 2/3 ground, 4 cups, 5 vane; rain 3 ground, 4 rain).
7. The Wio-E5 pins match the firmware's board file.
8. KiCad ERC reports nothing beyond the written waivers.
9. Every outdoor line has its series resistor and clamps; the port pull-up (about 5 kohm) allows 236 pF, about 2-3 m of cable at an assumed 50 pF/m `[TBD-MEASURE]`.
10. r2's connections differ from r1's only by the listed changes below.

**Layout (`layout/layout_checks.py`):**

- **L1:** every pin on a hole, every conductor end a real hole or pad, no hole doubled, every backplane bus wire soldered only at real holes of its own line.
- **L2/L3:** the copper equals the schematic; no strip (card) and no wire-joined pad group (backplane: the PAD3U has no strips, nothing connects unless a wire does) carries two nets (checked without part-internal ties).
- **L4:** the battery current touches only B4's doubled power-pin strips and their backplane lines; each crossing is on two pins; the charger's SYS (J3 SYS to line 26) and its return (J3 GND to line 12) each have their own lead to their bus wire.
- **L5:** the bus is on rows 1-18 of column j on every card and bus wires 1-18 of the backplane; every header is the 1x30 less exactly its key pin (B1 27, B2 28, B3 29, B4 30), a spare pin with no net; insertion 4.96 mm of 5.8 (at least 4.16 with the card 0.8 mm short); the socket body never overlaps the snapped card (2.36 mm clear).
- **L6:** no two part bodies collide on a card.
- **L7:** each card pitch clears the tallest part below, its tails and 0.5 mm; nothing collides with the cage, the backplane, another card, the base's corner lands and insert posts, its rim lip, or the gland nuts; each card slides out alone; everything fits the box inside; the EVM and pack shelves stay 2 mm clear of each other, the backplane, B4, the lid's inner wall and bosses; the mux stays clear of the socket tails; what sits past the base-lid seam (in the lid tray) is listed.
- **L8:** every routed wire, jumper and lead (81 of 81) runs on its side of the card in right-angle runs, crosses no part footprint (a pad lead only its own breakout), passes over no used hole but its own ends, and shares no grid run with another conductor except an insulated lead bundle (at most 3); a bare jumper meets nothing.
- **L10:** each card comes out alone (Clint's rule, below): no soldered or clamped lead leaves a card; everything else off a card is its header or a hand plug; the charger and the pack meet only the backplane; nothing runs card to card except through the backplane.
- **L13:** the slot keys: each socket's key plug sits in its card's pulled position, on an isolated pad (no bus wire, no lead); for every card and socket the card's pins miss the plug only in its own socket, so any other card stubs on it.
- **L9:** every mating and fixing in the table below; the slot play against the socket lead-in, the room over each plug's latch, the SMA path and the cage screws' access are computed, and anything held by solder or adhesive alone or reachable only after something else comes out is flagged.

## What changed from r1, and why

r1 stacked the boards on standoffs with soldered bus wires between them; the reviews found it could not be taken
apart (mechanical C1), did not fit the floor (C2) and had 0.5 mm to the lid (C3). r2 replaces the stack with the card
cage. The connection changes (check 10):

- **Removed:** the B3-B4 socket XS1 and the B4 bus pins XP1 (the cards now plug into the backplane); the QT leads on B1 (W11-W14) move to the backplane as W1-W4, beside the mux.
- **Added:** a right-angle bus header per card (XH1-XH4) and a backplane socket per card (XB1-XB4); the charger I2C pins XJ1 on the backplane; the battery + junction (backplane lines 21-22; mechanical M8); 100 ohm resistors R7 and R8 at the tap end of the charger battery sense (BATP) and the fuel gauge cell sense leads (electrical m11); the pack thermistor RT1 on EVM J7 with JP18 removed (M2); the right-angle SMA adapter AD1; on every outdoor line a series resistor and clamps (M5): 100 ohm and BAT85S Schottky clamps (to the port 3.3 V and from ground) on each sensor port's data and clock, a 1N5232B zener on each port's 3.3 V, and on cups, vane and rain a 1N5232B zener and a 1 k series resistor to the MCU, with a new 100 nF filter on the vane (C3).
- **Moved:** the charger and gauge sense now leave the battery + junction through R7 and R8 on the backplane; EVM J8 pin 1 is the I2C lead's ground; each port's data and clock pass their series resistors between jack and mux; each meter line passes its 1 k between the jack side and the MCU pin; AD1 sits between the radio and the coax.
- **Renamed:** EVM pins are named by terminal (J3 SYS, J8.2 clock, J8.3 data).

Clamps on the sensor-port data and clock are BAT85S (at most 10 pF at 1 V, Vishay doc 88146), not zeners: a DO-35
zener adds 100 pF or more, which would eat the 236 pF budget.

## What changed in r3, and why

- **Back rails snapped off** each card (`sb_snap_y`, card Y 41.91 `[TBD-MEASURE]`) before any soldering, the edge
  filed flat. The header's mating pins now stand 7.32 mm past the edge into the socket; the card edge is 10.86 mm
  from the backplane.
- **RJ11 jacks face the lid** (2026-11-16): on B1 and B2 every BOB-14021 stands on a soldered 1x6 male header in
  row a (pin n in its own column and strip), overhanging the front edge, mouth toward the lid; the plugs and their
  cable bends sit in front of the cards. The printed spacers, the back jack's tongue, the right post's cut and the
  flying leads are gone; each port's clamps stand in its jack's strips, its fuse and zener in a block beside it.
- **Backplane on a BusBoard PAD3U padboard** (pad per hole): the PAD3U's plated end, 31 lines (0-30) x 38 holes, a
  rectangle with only its left edge cut: 18 bare bus wires, each soldered at every pin of its line, and B4's power lines; cut step and hole-by-hole table in `build/BACKPLANE.md`; two M3 screws, through the one drilled hole (s0.2) and the
  lower factory mounting hole (drilled out to 3.2), into two floor posts; the left edge in the left wall's groove, the factory right edge in a 4.0 slot in the right corner post (`cage/backplane-mount-spec.md`): tilted into the slot, slid left into the groove.
- **Slot keys** (Clint, 2026-11-16): the four sockets are identical, so any card fitted any slot, and B3 in B4's
  would have put the battery on the Wio-E5. Each card pulls one spare pin (B1 27, B2 28, B3 29, B4 30) and its own
  socket takes a key plug there (a cut-off male pin, flush with the mouth, soldered to nothing); a colour dot on
  each card and slot (B1 blue, B2 green, B3 yellow, B4 red). Checked in L5 and L13.
- **Charger ground lead:** J3 GND to backplane line 12 (24 AWG stranded, black, beside the SYS lead), so SYS's
  return no longer runs only through the I2C lead's J8 pin 1 and its KK crimp. Checked in L4.
- **Wires routed** (`layout/route.py`) instead of drawn straight: lengths, drawings and renders follow the routes.
- **A printed base instead of the #905 body** (Clint, 2026-11-10): the EVM measured 90 x 90 (96 across J8) and
  did not fit the stock body with 2 mm margins. The base is PETG, 100 deep outside, 3 mm walls, and mates with the
  #905's own lid and O-ring; everything is one vertical stack of shelves (pack, EVM, B4, B2, B1, B3), the SHTC3 on
  the top card about 84 mm above the charger. Glands in the bottom wall's bosses (PG-7 #762 and PG-9 #761, from
  Adafruit's drawing), with a pitch check; each cable rises out of its gland, turns right under the pack tray and
  runs up the right column past the pack and the EVM (`cage/shelves-spec.md`).
- **The lid's corners set the card heights.** The lid's corner bosses (22 x 21) and the O-ring's curve round them
  need a solid 3 mm land in each corner of the base at the seam, so a card's parts can't pass a top corner as it
  slides out. The card stack is 10 mm lower (`power_zone` 82): B3's top is 3 mm under the upper corner lands. The
  EVM moved forward, 2 mm in front of the backplane's lower end (it now reaches 10.6 mm into the lid), and 4 mm
  right, clear of the lid's inner channel wall. The base's land is the lid's full 9 mm rim (6 mm inside the wall),
  and the cage's left wall is 8.5 mm, so the cards' left edges clear it as they slide out.
- **The spare depth in front of the cards** (Yb 66 to 120) takes the RJ11 cables' service loops, the EVM's lead
  loops, and the coax: AD1's arm now points toward the lid, the plug and the RG-316 bend fit in front of the cards,
  and the cable reaches the SMA bulkhead boss in the right wall. The coax path is resolved.
- **Renders:** imported BOB-14021 and Wio-E5 mini boards, the Adafruit PCA9548 STEP, the header drawn with its
  pins bent, routed wire tubes, bottom views, an exploded cage and a section; `render/MODELS.md`.

## Not yet ordered

Everything the build needs that is in neither the DigiKey cart (2026-11-09) nor `INVENTORY.md`. Stock and price
from digikey.ca on 2026-11-10; quantities include spares. On hand per `INVENTORY.md`, so not listed: the M4 heat-set
inserts (100) for the lid screws and the M3 heat-set inserts (200) for the backplane posts, the generic 2.54 mm right-angle male headers and female strips (every one cut to 1x30), 
24 AWG solid and stranded hook-up wire, the Adafruit 1311 22 AWG solid (stripped for the bus), the M3 screws for the backplane and the bar, the RJ12 6P6C crimp plugs (100, generic; modelled as
the standard 6P body after Cinch 32-5996UL), and the PETG (Clint).

| Part | Maker part | DigiKey | Need | Buy | Stock | Price (CAD, 1 off) | Note |
|---|---|---|---|---|---|---|---|
| Signal clamp diode | Vishay BAT85S-TR | BAT85SCT-ND | 16 | 20 | 44,459 | 0.74 | |
| Zener clamp 5.6 V | onsemi 1N5232BTR | 1N5232BFSCT-ND | 7 | 10 | 86,084 | 0.25 | |
| Series and sense resistor 100 ohm | Stackpole CF14JT100R | CF14JT100RCT-ND | 10 | 15 | 308,663 | 0.16 | the Yageo kit has 5; the cart's CF14JT1M00 (1 Mohm, 50) matches no part here: check that line |
| SMA right-angle adapter (AD1) | Amphenol RF 132172 | ACX1249-ND | 1 | 1 | 10,603 | 20.40 | pending Clint's measurement of the 135110 plug length; its arm toward the lid |
| Cable glands PG-7 (round port cables) and PG-9 (flat weather-meter cables, seal out, packed) | Adafruit #762 and #761 (Clint has one of each), or LAPP 53111000 (M12) for the PG-7s | 2181-53111000-ND | 6 PG-7 + 2 PG-9 | 5 PG-7 + 1 PG-9 | LAPP not stocked (2 weeks) | bulk only | plus silicone or split grommets for the two flat cables |
| Hose clamps for the pole lugs | stainless, to suit the pole | - | 2 | 2 | - | - | the two on hand are for the shield arm |
| Pressure-equalising vent | M12 x 1.5 vent plug | - | 1 | 1 | not checked | - | DigiKey number not found in this pass |
| JST PH 2-pin socket with leads (pack pigtail) | any | - | 1 | 2 | not checked | - | DigiKey number not found in this pass |
| USB-C to micro-B cable (EVM J6) | any | - | 1 | 1 | not checked | - | |
| Hook-and-loop strap (pack), foam tape (mux) | any | - | 1 each | 1 each | not checked | - | |

## Mechanical connections

**Rule (Clint, 2026-11-13): each card (B1-B4) can be pulled out independently of every other card, and inspected.**
No card has a soldered or clamped wire leaving it. Everything that leaves a card goes through its backplane header,
or is an ordinary plug on that card that comes out by hand (an RJ11 port cable, the SMA coax, the SWD or USB-C
lead). The charger and the pack connect only to the backplane; nothing runs from one card to another except through
the backplane. Taking a card out needs only the retention bar off, its own plugs out, then a straight pull; never
another card first (layout check L10, with L7's slide-out and plug-clearance checks).

Every mating and fixing: how it is held, what takes the force, how it comes apart. Flagged: anything held by
solder or adhesive alone, or that cannot be reached or removed without taking something else apart first.

<!-- mechanical:begin (generated by layout/layout_checks.py --write) -->
| Mating or fixing | Held by | Force path | Taken apart | Flag |
|---|---|---|---|---|
| Card in its slot | left wall slot (2 mm deep) and the right corner post slot; the retention bar across the front left | the slots take the card's weight and any knock across it; the bar stops it backing out | two M3 screws: bar off, card slides out toward the lid |  |
| Bus header into the backplane socket | 29 contacts' friction on every card (the 1x30 less its key pin: B1 27, B2 28, B3 29, B4 30; its own socket's key plug sits there and blocks every other card); axis Yb (in the card plane, toward the back wall); insertion 4.96 mm of 5.8; the insulator meets the socket 0.84 mm further in (the depth stop) | the socket; side play is the slot's 0.3 mm, inside the socket lead-in (0.5 mm [TBD-MEASURE]) | pull the card straight out toward the lid (bar off first) |  |
| B3 U5 breakout (enclosure air sensor, top card, away from the charger) | its own header, soldered in the breakout and in the card (one row) | the header pins; a QT plug's push goes through the breakout into the header | desolder the header row (or cut the pins and fit a new header) | held by solder alone on one header row |
| B4 U2 breakout (battery monitor) | its own header, soldered in the breakout and in the card (one row) | the header pins; a QT plug's push goes through the breakout into the header | desolder the header row (or cut the pins and fit a new header) | held by solder alone on one header row |
| B4 U6 breakout (fuel gauge) | its own header, soldered in the breakout and in the card (one row) | the header pins; a QT plug's push goes through the breakout into the header | desolder the header row (or cut the pins and fit a new header) | held by solder alone on one header row |
| B4 U7 breakout (3.3 V regulator) | its own header, soldered in the breakout and in the card (one row) | the header pins | desolder the header row (or cut the pins and fit a new header) | held by solder alone on one header row |
| B1 J12 RJ11 breakout | its own 1x6 male header, soldered in the breakout and in row a of the card, one pin in each of columns 5-10 (six strips); the breakout overhangs the card's front edge, the jack's mouth toward the lid | the plug's push and pull run along the jack axis (Yb) through the jack and the breakout into the six header pins, in bending (the breakout overhangs the front edge); the latch takes the pull | desolder the six header pins (or cut them and fit a new header) | held by solder alone on one header row; the plug's push and pull load the six pins |
| B1 J13 RJ11 breakout | its own 1x6 male header, soldered in the breakout and in row a of the card, one pin in each of columns 11-16 (six strips); the breakout overhangs the card's front edge, the jack's mouth toward the lid | the plug's push and pull run along the jack axis (Yb) through the jack and the breakout into the six header pins, in bending (the breakout overhangs the front edge); the latch takes the pull | desolder the six header pins (or cut them and fit a new header) | held by solder alone on one header row; the plug's push and pull load the six pins |
| B1 J11 RJ11 breakout | its own 1x6 male header, soldered in the breakout and in row a of the card, one pin in each of columns 24-29 (six strips); the breakout overhangs the card's front edge, the jack's mouth toward the lid | the plug's push and pull run along the jack axis (Yb) through the jack and the breakout into the six header pins, in bending (the breakout overhangs the front edge); the latch takes the pull | desolder the six header pins (or cut them and fit a new header) | held by solder alone on one header row; the plug's push and pull load the six pins |
| B2 J14 RJ11 breakout | its own 1x6 male header, soldered in the breakout and in row a of the card, one pin in each of columns 15-20 (six strips); the breakout overhangs the card's front edge, the jack's mouth toward the lid | the plug's push and pull run along the jack axis (Yb) through the jack and the breakout into the six header pins, in bending (the breakout overhangs the front edge); the latch takes the pull | desolder the six header pins (or cut them and fit a new header) | held by solder alone on one header row; the plug's push and pull load the six pins |
| B2 J22 RJ11 breakout | its own 1x6 male header, soldered in the breakout and in row a of the card, one pin in each of columns 8-13 (six strips); the breakout overhangs the card's front edge, the jack's mouth toward the lid | the plug's push and pull run along the jack axis (Yb) through the jack and the breakout into the six header pins, in bending (the breakout overhangs the front edge); the latch takes the pull | desolder the six header pins (or cut them and fit a new header) | held by solder alone on one header row; the plug's push and pull load the six pins |
| B2 J21 RJ11 breakout | its own 1x6 male header, soldered in the breakout and in row a of the card, one pin in each of columns 24-29 (six strips); the breakout overhangs the card's front edge, the jack's mouth toward the lid | the plug's push and pull run along the jack axis (Yb) through the jack and the breakout into the six header pins, in bending (the breakout overhangs the front edge); the latch takes the pull | desolder the six header pins (or cut them and fit a new header) | held by solder alone on one header row; the plug's push and pull load the six pins |
| RJ11 plug latch and cable | the jack latch; the latch is on the plug, 12.9 mm free over the tightest plug (B2 J21 RJ11 plug (standard 6P body after Cinch 32-5996UL)); the plugs go in from the lid side (mouths at Yb 72.8); each flat cable leaves its plug toward the lid, bends down in front of the cards (the plug and the bend reach Yb 97.8, 22.2 mm short of the lid), crosses right to the right column (cage/shelves-spec.md: Xb 100-122, beside the EVM and the pack) and down it to the cable space under the pack tray, then along the floor to its gland in the bottom wall | the latch, then the gland's seal (strain relief) | press the latch (lid open, from the front), pull; loosen the gland nut to pull the cable through |  |
| Wio-E5 mini on B3 | soldered on its own 2 x 12 header (not in sockets) | the header pins | desolder 24 pins | held by solder alone; cannot come off without desoldering 24 pins |
| Wio-E5 mini USB-C console | the receptacle's friction; cable plugged from the left with the lid open | the mini's receptacle and its header | pull the plug |  |
| SMA, adapter and coax to the bulkhead | AD1 screwed on the mini's SMA-K, its arm toward the lid; the 135110 plug screwed on AD1; the cable bends right in front of the cards to the bulkhead jack in the right wall's boss | the coax is clipped to the cage at its bend so a pull on it reaches the bulkhead, not the mini's SMA | unscrew the plug at AD1 (8 mm spanner), then lift B3 out |  |
| B4's power pins (the battery path) | header pins 19-20 (charger battery +, after the shunt) and 21-22 (the battery + junction) doubled, 23 gauge sense, 26 SYS (24-25 its 3.3 V and ground, on isolated pads), in the B4 socket on lines 19-26; the junction, R7 and R8 and the leads to the EVM and the pack are on the backplane | the socket contacts (about 0.5 A each on the doubled pins at 1 A) | pull B4 out: the battery path opens at its header, nothing to unscrew |  |
| Battery pack | lies flat on the pack tray, the lowest shelf (the heaviest part low); a hook-and-loop strap through the tray | the tray's front lip and the strap | open the strap, unplug the JST PH, slide it out |  |
| Charger (BQ25798EVM) | a shelf: its side edges on two moulded ledges, a stop at the back, a snap clip at the front (the board has no mounting holes); the Bumpon feet (H1-H4, 3M SJ-5303) peeled off first | the ledges; the terminal screws are tightened from above, in the room under B4 | unscrew its leads at its terminals (they run to the backplane, not to a card), flex the clip, slide it toward the lid on its service loops | its underside parts (J6, tails: 4 mm [TBD-MEASURE]) must clear the 2 mm ledges at the edges |
| Backplane on its posts | two M3 screws (the drilled s0.2, and the PAD3U's lower factory hole drilled out to 3.2) into heat-set inserts in two round floor posts; the left edge in the left wall's groove and its rail, the factory right edge in a 4.0 slot in the right corner post (tilted into the slot, slid left into the groove) | the posts, three plain pads and the groove and slot floors take the card insertion push | undo the two screws, slide it right to the slot's end, lift the left side, out, after every card is out | removable only after all four cards are out |
| Lid to the printed base | four M4 stainless screws on 12 mm washers through the lid's 8 mm holes into M4 heat-set inserts (5.6 mm holes, 3 mm of wall round each) in the base's corner posts, 156 x 109 apart (9.75 / 10.25 in from the lid's edges, cage/lid-rim-spec.md; option b, recommended over a printed copy of the original 8 mm plastic thread); the base's 9 mm land under the lid's rim, its 2 x 4.5 sealing lip in the lid's O-ring channel | the screws squeeze the O-ring; the lid's rim takes a knock | undo the four lid screws | not settled: the screw and the lid's corner pocket (L1), and the rim test ring's fit on the real lid: no full STL until they are |
| Base to the pole | two moulded lugs on the back, a hose clamp or U-bolt through each; no screw through the back into the box | the lugs' roots in the 3 mm floor | open the clamps |  |
| Cables through the glands | five round cables (the four sensor-port cables S1-S4 and the solar lead) in PG-7s (#762, seal 3.0-4.3 mm; 6 PG-7s, 1 spare, blanked) in the bottom wall's bosses, each passed through its gland before its inside plug is crimped (a 6P plug, about 12 mm across its corners, passes no gland bore); the flat wind and rain cables in PG-9s (#761) with the seal out and the gap packed with silicone or a split grommet, their factory plugs cut off and new 6P plugs crimped inside | the gland's seal (round) or the sealant (flat); a drip loop below each gland outside, so water runs off the loop and not along the cable into the gland | loosen the cap (round); cut the sealant (flat) | a flat cable is sealed once its position is final and then comes out only by cutting the seal |
<!-- mechanical:end -->

## Deferred, with reasons

- **Sensor-power switch on PA9 (electrical M3).** No orderable through-hole current-limited switch was found; the
  pin is marked "not wired" in the model. A short on one port still browns out the 3.3 V supply until its MF-R010
  trips.
- **Firmware README profile and pin notes (m10).** Outside this directory; left for a firmware change.

## Open questions

- **The lid interface is not settled.** The rim, the corner bosses, the screw positions (L2) and the O-ring's
  inset (L4) are from Clint; the channel depth does not matter (Clint). Open:
  - L1, the screws. The original base has large moulded threads, about 8 mm, for plastic screws. Two options are
    parametric (`lid_screw_opt`): (a) a printed thread copying the original (needs its pitch and length); (b) M4
    stainless pan heads on 12 mm washers (ISO 7093, `[TBD-MEASURE]`) through the lid's 8 mm holes into M4 heat-set
    inserts. **(b) is recommended:** brass inserts survive the lid coming off many times, a coarse PETG thread
    wears. The washer must seat in the lid's square corner pocket (`lid_pocket`, 14 placeholder). The holes are
    outside the O-ring, so they need no seal.
  - L5 and the rim come from `cage/lid-rim-spec.md` (300 dpi scans, 2026-11-11): the lid 175.5 x 129.5, the
    straight lips 169.5 x 123.0 apart centre to centre (3.0 in from the short edges, 3.25 from the long), each S
    15.4 deep with R3.5 outer and R7.15 middle bends. The holes are 156 x 109 apart (9.75 from the short edges,
    10.25 from the long), each about +-1 `[TBD-MEASURE]`: 156 is between Clint's tape (155) and the maker's 157.
    For the full base this changed: the outline from 175 x 130 (inside now 123.5 x 169.5), the lip insets from
    4.0 / 3.5, the S from 13.5 / 14.0, the radii from 3 / 5.5, the screws from 155 x 109. The spec's own check
    says the straight lip is 3.25 in from the outline; its segment table puts the short sides' at 3.0.
  - L6, the lip height: **not settled.** `cage/lid-rim-spec.md`, `sources.rim_tongue` and `cage.py` build the
    lip 2 wide x 4.5 tall (the test ring too); Clint's earlier note on the original base (`l6_body_rib`) says 3 tall.
    Which one the printed base and the test ring actually carry is not known here: it waits on Clint's report of
    the printed base and the test ring on the real lid. Nothing is changed until then. The lip sits on the lid
    channel's centre line (that is what must seal); offset and width are named inputs (`rim_tongue`). Clint's
    eyeball of the original lip, 1-2 mm in from the base's edge, disagrees with that line: the original base is
    about 1.25 mm wider a side than the lid, so that would put it under the lid's outer wall. The squeeze on the
    O-ring (assumed a round 3 mm solid cord, 2 mm down) follows from whichever height is right.
- **PETG in sun.** Its heat-deflection temperature is about 70 C (0.45 MPa; check the spool's datasheet:
  Bambu's pages refuse scripts) against an inside above 45 C in sun (mechanical review): a light colour and a UV
  paint or clear coat outside.
- **The EVM's heights** (15 mm tallest part above, 4 mm J6 and tails below) are not measured; it sits 2 mm in front
  of the backplane's lower end, 25 mm under B4, and must clear the 2 mm ledges at its edges. Its front 4.6 mm and J8
  reach past the seam into the lid (to Yb 107.6 of 120): J8's plug has 12 mm.
- **Glands and cables.** The weather-meter cables are flat (about 2.3 x 6.6, derived from TE 5-555042-3's cable
  entry): each goes through a PG-9 (bore 10.5 with the seal out; 7.0 across the cable plus 0.5 mm of sealant a side
  fits) packed with silicone or a split grommet, sealed only once the cable's position is final. The round
  cables (sensor ports S1-S4 and the solar lead; the sixth PG-7 is a blanked spare) take PG-7s (3.0-4.3 mm):
  measure them. A 6P plug is about 11.7 mm across its corners (12.2 with the latch), more than either gland's bore
  (PG-7 7.9, PG-9 10.5 with the seal out), so every cable goes through its gland with no plug on its inside end and
  that plug is crimped after (Clint has 6P crimp plugs; a 6P crimp tool is needed, not yet listed). The weather
  meters' factory plugs are cut off outside and re-crimped inside, same order (`build/ASSEMBLY.md` step 2.6); open:
  whether Clint's 6P6C plugs hold the meters' narrower flat cable on the right positions, or 6P4C plugs are needed.
  A drip loop below every gland.
- **RJ11 jack:** the BOB-14021s take the Amphenol 87180-066LF (11.5 mm, RS listing). The 4UCON 14869 (SparkFun
  PRT-00132, 15.70 mm high) would be too tall under the next card (21.8 mm needed on the header, 18.72 there).
  Clint has bare BOB-14021 boards and loose jacks (2026-11-16), nothing assembled: check the loose jacks are the
  87180-066LF before soldering.
- **Thermistor bias.** The #372 NTC is B 3950; the EVM's TS divider assumes a 103AT (B 3435). Read TS at room temperature before the first charge (build/ASSEMBLY.md).
- **Mini back-feed.** The mini's AP2112 is back-fed from the bus 3.3 V; with USB-C in for the console two regulators run in parallel (accepted, electrical m3).
- **B4 power through the backplane** (resolved 2026-11-13): the battery path, its senses and SYS reach B4 on header pins 19-23 and 26; B4 slides out with nothing to undo. Pulling B4 opens the battery path (the shunt is on B4): the EVM then sees no battery, which is the intended way to power down. The doubled socket contacts' resistance is not measured `[TBD-MEASURE]`: a few milliohm per pair is a few mV at 1 A, seen only by the INA228's bus-voltage reading; the charger (BATP) and the gauge sense the junction itself on the backplane.

## Measurements for Clint

The floor sheet M1-M13 is no longer needed (the stock body is replaced). Still `[TBD-MEASURE]`, each a named input
in `sources.py`:

1. The #905 lid, copied by the printed base. In from Clint (2026-11-10): the rim 3 + 3 channel + 3 = 9 mm
   (`lid_rim`), the corner bosses 22 x 21 with 3 mm outside the hole (`lid_boss`), L2 the screws 10 mm from both
   outside edges (`l2_screw_pos`), L4 the O-ring 2 mm below the channel walls (`l4_oring_proud`). Still needed:
   - L1 the original screw: thread diameter, pitch, length (`l1_lid_screw`, for option a); the lid's corner
     pocket width and the boss height under the screw head (`lid_pocket`, for option b); the M4 screws and washers
     as bought (`m4_screw`, `m4_washer`);
   - the rim test ring on the real lid (`ring_fit`): the lip in the channel all round and through the four S-curves,
     all four holes at once (156 x 109, each +-1: `l2_screw_pos`), the outer edge flush on all four sides;
   - the lid's corner radius (`l5_lid_out`) and the O-ring's cross-section (round 3 mm assumed).
2. The BQ25798EVM's tallest part (`evm`) and what hangs below it (J6, tails: `evm_under`); the M4 heat-set inserts'
   hole and length (`insert_m4`).
3. The snap line: card Y of the cut between column j and the inner back rail (`sb_snap_y`).
4. The card slot fit on a printed test slot (`slot_clear`); the socket's lead-in (`align_tol`).
5. Solder tails and underside wires below a card, after the first card (`tails`).
6. The generic header and socket (`ra_*`, `socket_*`); a standing DO-35 diode's height (`diode_stand_h`); the 24 AWG insulation OD (`wire24`).
7. The PG-9 locknut across corners (`gland_pg9_nut`); the PG-7's lengths are scaled from the PG-9 (`gland_pg7`).
8. Each round port cable's outer diameter (PG-7: 3.0-4.3 mm) and the flat meter cable's size (`flat_cable`,
   `sealant`).
9. An RJ11 plug, its boot and cable bend (`plug_len`, `plug_bend`), and the room a finger needs over its latch
   (`finger`).
10. The USB-C console plug overmould (`usbc_plug`) and the mini's USB-C height (`mini_usbc_h`).
11. The Amphenol 132172 adapter's arms (`sma_ra`), the mini's SMA overhang (`mini_sma_out`), the 135110 cable's
    straight plug (`sma_plug_len`), the RG-316 bend radius (`rg316_bend`) and the antenna's length (`ant_len`).
12. The QT lead housing height (`qt_lead_h`) and the QT socket height (`qt_h`).
13. The foam pad under the mux (`foam`), the breakout PCB thickness (`breakout_t`) and the S7V8F3's inductor
    (`s7v8f3_h`).
14. The jack height in a test fit (`jack_h`), and each port cable's capacitance (for the 236 pF limit).

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
| `jack_4ucon` | 13.34 x 20.57 x 15.7 | 4UCON 14869 jack (SparkFun PRT-00132; not used, too tall under the next card: L9): width x length x height (15.00 to the shoulder); pins 1.27 stagger, 6.35 outer, rows 2.54 apart, 8.89 from the pegs; pegs 3.20 at 10.16; tails 4.30 | 4UCON drawing 14869 (SparkFun PRT-00132 jack), cdn.sparkfun.com/assets/8/6/5/f/1/RJ11-Datasheet.pdf (SparkFun's STEP is an outdated version: community.sparkfun.com/t/44748) | sourced |
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
| `ina228_sj1` | open | INA228 #5832 VBUS jumper SJ1 (VBUS to VIN+) as shipped; closed for high-side measurement | learn.adafruit.com/adafruit-ina228-i2c-power-monitor/pinouts (VBUS Jumper); Adafruit-INA228-PCB .sch: SJ1 pins VIN+ / VBUS, SOLDERJUMPER_ARROW_NOPASTE (open) | sourced |
| `max17048` | 25.4 x 20.32 | MAX17048 #5580 outline | Adafruit Eagle board, github.com/adafruit/Adafruit-MAX17048-PCB | sourced |
| `qt_lead_h` | 14 | QT lead male-pin housing height (#4209) | premium jumper housing; measure | [TBD-MEASURE] |
| `qt_h` | 2.9 | STEMMA QT (JST SH) socket height | bench r1 kicad_layout.py qt_socket | [TBD-MEASURE] |
| `jstph_h` | 6 | JST PH 2-pin socket height (MAX17048) | KiCad JST_PH_B2B-PH-K model; bench r1 model_gauge | sourced |
| `s7v8f3` | 11.43 x 16.51 | Pololu S7V8F3 outline | bench r1 build.py SIZE['REG'] (0.45 x 0.65 in); pin order from the board in hand | sourced |
| `s7v8f3_h` | 3 | S7V8F3 tallest part (inductor) | bench r1 kicad_layout.py model_reg | [TBD-MEASURE] |
| `ptc` | 7.4 x 3.1 x 12.7 | MF-R010 Style 1 (round dipped disc on two kinked leads): A width x E thickness x B top-to-kinks (max); leads C 5.1 +/- 0.7 apart, 0.51 dia, D >= 7.6 below the kinks | Bourns MF-R datasheet dimension table + Style 1 drawing (Clint, 2026-11-16) | sourced |
| `res_v_h` | 9 | 10 kohm standing (P5.08 vertical) height | KiCad R_Axial_DIN0207 vertical model, L 6.3 + lead | derived |
| `cap_h` | 6 | 100 nF disc height | KiCad C_Disc_D3.8mm model, D 3.8 + lead | derived |
| `pack` | 69 x 54 x 18 | battery pack #353 | INVENTORY.md / docs/current-system.md (SHOP:49) | sourced |
| `ra_offset` | 1.52 | right-angle header: hole centre to the insulator's back face | Clint's generic 2.54 mm right-angle male header (cut to 18), 2026-11-13; drawn as the Sullins PRPC drawing (Sullins right-angle male header drawing, mfgdatasheets.nlight.net (PRPC018SBAN-M71RC, -M71 single narrow)) (.060): check on the part | [TBD-MEASURE] |
| `ra_insulator` | 2.54 | right-angle header insulator, along the mating pins | Clint's generic 2.54 mm right-angle male header (cut to 18), 2026-11-13; drawn as the Sullins PRPC drawing (Sullins right-angle male header drawing, mfgdatasheets.nlight.net (PRPC018SBAN-M71RC, -M71 single narrow)) (.100): check on the part | [TBD-MEASURE] |
| `ra_mate` | 5.8 | right-angle header mating (long) leg beyond the insulator | Clint's generic 2.54 mm right-angle male header (cut to 18), 2026-11-13; drawn as the Sullins PRPC drawing (Sullins right-angle male header drawing, mfgdatasheets.nlight.net (PRPC018SBAN-M71RC, -M71 single narrow)): 5.8 nominal; measure Clint's | [TBD-MEASURE] |
| `ra_tail` | 3.05 | right-angle header solder tail below the insulator | Clint's generic 2.54 mm right-angle male header (cut to 18), 2026-11-13; drawn as the Sullins PRPC drawing (Sullins right-angle male header drawing, mfgdatasheets.nlight.net (PRPC018SBAN-M71RC, -M71 single narrow)) (.120): check on the part | [TBD-MEASURE] |
| `ra_pin_z` | 1.27 | right-angle header pin centre above the card | the 2.54 square insulator on the board | derived |
| `socket_h` | 8.5 | backplane socket body, backplane face to mouth (1x30 cut from a longer female strip, one position lost at each cut) | Clint's generic 2.54 mm female header strip (cut to 18), 2026-11-13; drawn as the Sullins PPPC drawing (Sullins PPPC female header drawing (PPPC181LFBN-RC), sullinscorp.com): check on the part | [TBD-MEASURE] |
| `socket_w` | 2.54 | backplane socket body width (single row) | Clint's generic 2.54 mm female header strip (cut to 18), 2026-11-13; drawn as the Sullins PPPC drawing (Sullins PPPC female header drawing (PPPC181LFBN-RC), sullinscorp.com) | [TBD-MEASURE] |
| `socket_tail` | 3 | socket solder tail beyond the backplane copper | Clint's generic 2.54 mm female header strip (cut to 18), 2026-11-13; drawn as the Sullins PPPC drawing (Sullins PPPC female header drawing (PPPC181LFBN-RC), sullinscorp.com): .118 tail; check on the part | [TBD-MEASURE] |
| `insertion` | 4.96 | chosen pin insertion into the socket (5.8 nominal available; 0.84 left for print tolerance) | layout rule | derived |
| `card_bp_gap` | 10.86 | snapped card back edge to backplane face | 39.37 (column j) + 1.52 + 2.54 + 5.8 - 4.96 + 8.5 - 41.91 (sb_snap_y) | derived |
| `fillet_clear` | 0.6 | solder fillet radius kept clear round a used hole: an underside wire's insulation stays this far from the hole centre | coordinator rule (Clint): OD/2 + 0.6 from any hole a pin or another wire end uses | derived |
| `pad_pitch` | 2.54 | PAD3U hole pitch (a separate pad per hole, no strips) | BusBoard PAD3U Padboard, busboardcom.busboard.us/PAD3U (38 x 62 holes, 0.037 in holes on 0.1 in, 160.02 x 100.08 x 1.6 mm; DigiKey 4526-PAD3U-ND) | sourced |
| `strip_size` | 160.02 x 100.08 x 1.6 | BusBoard PAD3U padboard, 62 holes along 160 mm x 38 along 100 mm; the backplane is the plated end's 31 rows (lines 0-30) by the full 38 holes, lines across the 160 mm side | BusBoard PAD3U Padboard, busboardcom.busboard.us/PAD3U (38 x 62 holes, 0.037 in holes on 0.1 in, 160.02 x 100.08 x 1.6 mm; DigiKey 4526-PAD3U-ND) | sourced |
| `pad3u_mount` | 2.8 x 3.75 x 2.65 x 88.9 | PAD3U factory mounting holes at one 100 mm end: drill diameter, copper ring diameter, centre beyond the end row's hole centres, centre to centre; on the 2nd and 37th of the 38 holes, the pads beside them left off | Clint's 300 dpi PAD3U scan with a steel ruler, 2026-11-13 (scan_20261113142805.pdf p.1-2): scaled by the ruler, 11.958 px/mm along the 100 mm side, 11.919 along the 160 (the hole pitch then reads 2.542 both ways): drill 33.5 px, ring 45 px, 31.5 px past row 1, 1063 px apart; +-0.1 | sourced |
| `pad3u_far_holes` | 1.5 x 1.27 | PAD3U unplated holes at the other 100 mm end: diameter, centre before the end row (midway between the last two rows), on the 2nd and 37th holes | Clint's 300 dpi PAD3U scan with a steel ruler, 2026-11-13 (scan_20261113142805.pdf p.1-2): scaled by the ruler, 11.958 px/mm along the 100 mm side, 11.919 along the 160 (the hole pitch then reads 2.542 both ways): 17.5-18.5 px; +-0.1 | sourced |
| `pad3u_edges` | 2.81 x 2.23 x 99.68 | PAD3U factory edges measured: long side to the outer holes' centres (2.84 and 2.78), the far (unplated) end to its last row, the width | Clint's 300 dpi PAD3U scan with a steel ruler, 2026-11-13 (scan_20261113142805.pdf p.1-2): scaled by the ruler, 11.958 px/mm along the 100 mm side, 11.919 along the 160 (the hole pitch then reads 2.542 both ways); BusBoard's 100.08 / 38 rows would give 3.05 | sourced |
| `pad3u_plated_edge` | 2.83 | PAD3U mounting holes' centre to the factory edge at that end | derived: BusBoard's 160.02 less 60 pitches (61 rows in the scan), the far margin 2.23 and the holes' 2.65; the scan cuts that end off, so measure it with calipers | [TBD-MEASURE] |
| `bp_slot` | 6.5 x 2.1 | the right corner post's backplane slot: depth into its -Xb face (Xb 85.8), height (Yb 8.0 to 10.1, as the left groove) | the fit: the board tilts its factory right edge (Xb 89.46, beyond line 30) in to the slot's end, so its left edge clears the left wall's face (8.5) as it comes down, then slides left into the left groove; the 31-line board (1x30 sockets) needs the end at Xb 91.65 or more, so 6.5 (end 92.30) keeps 0.65 for a factory edge further out than BusBoard's numbers give; deeper than Clint's 1-2 mm past the card slots because line 30 is needed | derived |
| `pad3u_factory_margin` | 3.05 x 2.54 | PAD3U factory edge to the nearest hole centre: across the lines (100.08 side), along them (160.02 side) | derived from strip_size: (100.08 - 37 x 2.54) / 2 and (160.02 - 61 x 2.54) / 2; more than the 1.27 of a cut edge, so the backplane keeps no factory edge | derived |
| `pad_margin` | 1.27 | backplane cut edge to the nearest hole centre (cut midway between two hole lines) | half the 2.54 pitch | derived |
| `bus_wire` | 0.64 | bare bus wire for the 18 backplane lines: 22 AWG solid, stripped (Adafruit 1311 hook-up wire, on hand) | AWG 22 = 0.644 mm | sourced |
| `align_tol` | 0.5 | header pin to socket misalignment the socket's lead-in takes | typical 0.1 in female header lead-in; check one card in the cage | [TBD-MEASURE] |
| `finger` | 8 | vertical room needed over a plug to press its latch | a fingertip or a small screwdriver | [TBD-MEASURE] |
| `rg316_bend` | 12.7 | RG-316 minimum static bend radius (the 135110-01 cable) | typical 5 x 2.5 mm OD; not in the Amphenol listing | [TBD-MEASURE] |
| `ant_len` | 100 | ANT-916-CW-HWR length, hinge to tip (render only) | not looked up: TE page refuses scripts; measure | [TBD-MEASURE] |
| `sma_plug_len` | 20 | straight SMA plug and its crimp ferrule on the 135110 cable | typical; measure the cable | [TBD-MEASURE] |
| `bp_post` | 7 x 8 x 3.5 x 4 x 6.5 x 1 | backplane floor posts: the right two's diameter, the bottom-left's diameter and its flat from its centre (+Xb side, toward the mux), insert bore diameter x depth from the top, fillet at the foot | cage/backplane-mount-spec.md (as Clint printed them): 7 clears line 18's pads by 0.7; the bottom left 8 for more plastic round the insert's knurl, its flat 3.5 leaving 0.31 to the mux; the board's tab (line -1, holes 1-3) gives s0.2 about 2.2 of FR4; the bore for an M3 x 5.7 insert about 4.6 across the knurl (knurl - 0.6, length + 0.8) | derived |
| `m3_button` | 5.7 x 1.65 | M3 button-head screw (backplane): head diameter, head height | ISO 7380-1, M3: dk max 5.7, k max 1.65 | sourced |
| `bar_inserts` | 5 x 76.5 x 146.5 x 3.4 | the retention bar's two M3 heat-set inserts in the left wall's front face: Xb, the two Zb, and the bar's clearance holes (the bores as bp_post's, for insert_m3) | enclosure 3 STL (as printed, audited 2026-11-16, sheets/audit-enc3): bores at Xb 5.00, Zb 76.50 and 146.50; the lower bore leaves 0.48 of plastic to the B4 slot's floor | sourced |
| `bp_groove` | 2.5 x 0.5 x 2.5 | the left wall's backplane groove: depth into the wall's slot-side face, height over the board's component face, the board's sideways fit travel (lowered this far to the right, then slid left into the groove) | cage/backplane-mount-spec.md: 0.5 clear past the board's edge; floor level with the post tops, a 45 degree roof | derived |
| `insert_m3` | 5.7 x 4.6 | M3 heat-set insert for the backplane posts: length, knurl diameter | cage/backplane-mount-spec.md: assumed; measure with calipers before printing | [TBD-MEASURE] |
| `bp_posts` | 8 | backplane copper face off the base's floor (the mux on its foam and the socket tails behind it, 2 mm clear) | mux 4.8 + foam 1 + 2 = 7.8 | derived |
| `cage_plate` | 0 | cage base plate: none (the printed base's floor carries the cage) | layout choice | derived |
| `cage_wall` | 8.5 | cage left wall thickness; card slots 2 mm deep | layout choice: the cards' left edge clears the base's 6 mm rim lip (the full 9 mm land less the 3 mm wall) by 0.5 mm as they slide out | derived |
| `slot_clear` | 0.3 | card slot width over the 1.6 mm card (print tuning) | Bambu H2D first-print allowance (the base is PETG); tune on a test slot | [TBD-MEASURE] |
| `bar` | 2.5 | retention bar thickness in front of the card front edges | layout choice | derived |
| `tails` | 1.5 | solder tails and bottom-side wires below a card | typical; measure after the first card | [TBD-MEASURE] |
| `clear` | 0.5 | minimum clearance kept between parts | layout rule | derived |
| `do35` | 4.56 x 2 | DO-35 body length x diameter (1N5232B, BAT85S) | onsemi 1N5221B series and Vishay BAT85 (doc 88146) outline DO-35/DO-204AH | sourced |
| `diode_stand_h` | 7 | standing DO-35 height (body on one lead, the other looped over) | 4.56 body + 1 lead + loop; check on the part | [TBD-MEASURE] |
| `wire24` | 0.511 x 1.45 x 84.2 | 24 AWG insulated hook-up wire (card wires solid, flying leads stranded): conductor diameter, insulation OD, resistance mohm/m | AWG 24 = 0.511 mm, 84.2 mohm/m at 20 C (0.205 mm2 copper); OD about 1.3-1.6 for PVC hook-up wire: measure Clint's | [TBD-MEASURE] |
| `r_lying_h` | 2.5 | lying DIN0207 resistor height (body diameter) | KiCad R_Axial_DIN0207_L6.3mm_D2.5mm model | derived |
| `evm` | 90 x 90 x 15 | BQ25798EVM (BMS034) board outline x tallest part above it; no mounting holes; feet H1-H4 3M Bumpon SJ-5303 (11.2 x 5.1) peeled off for the rails | outline: Clint, by hand, 2026-11-10: 90 x 90; parts (SLUUCB5E BOM): J1-J4 On-Shore ED120/2DS, J5 ED120/3DS (5.08 mm terminal blocks), J7 Molex 0393570002, J9 3M N2510-6002-RB, J8 Molex 0022053041, J6 Molex 47346-0001, about 33 jumpers with shunts; 15 covers a 5.08 mm rising-clamp block (about 10-12, makers' drawings not reached) | [TBD-MEASURE] |
| `evm_j8` | 12 | EVM J8 (right-angle 4-pin KK, the EV2300/2400 I2C port our lead uses) reach past the board's lid edge | Clint, 2026-11-16 (photo IMG_8591 + message): 90 x 90, J8 sticks out about 12 | sourced |
| `evm_j8_x` | 15 x 27 | EVM J8 across the lid edge, from the board's left (J6) edge: from, to | Clint's sketch 2026-11-16: 15 from the left, 66 to the right (15 + 66 + housing does not close on 90); the photo scales the housing to about 12, so the envelope is 15 to 27 | derived |
| `evm_j8_lead` | 15 | the I2C lead's KK plug on J8 and the lead's first bend, past J8's end | KK 2.54 plug housing about 10 deep plus a bend; not measured | [TBD-MEASURE] |
| `evm_overhang` | 1.5 x 6 | EVM parts past the board edge, above the board: left (J6 micro-USB), right (J3 and J5 terminal blocks, the BAT jumper) | Clint's photo IMG_8591 2026-11-16, scaled on the 90 mm board (about 7.2 px/mm) | [TBD-MEASURE] |
| `evm_edge_tails` | 28 x 41 x 55 x 68 x 34 x 48 x 51 x 69 | EVM through-hole tails near the edges, from the board's back edge toward the lid: left edge (J1, J2 and J6) from-to, from-to; right edge (J3, J5) from-to, from-to; the ledges are notched there | Clint's photo IMG_8591 2026-11-16, scaled; widened 1 each side | [TBD-MEASURE] |
| `box_out` | 125 x 175 x 75 | #905 (TIBOX) outside, for reference: width x length x depth (the printed base replaces its 50 mm body) | TIBOX enclosure catalogue, cdn-shop.adafruit.com/datasheets/TIBOX.pdf p.5; adafruit.com/product/905 | sourced |
| `lid_depth` | 25 | #905 clear lid tray depth, outside (kept: the printed base mates with it) | TIBOX enclosure catalogue, cdn-shop.adafruit.com/datasheets/TIBOX.pdf p.5 D2; Clint, by hand, 2026-11-10: lid about 25 deep, no lip | sourced |
| `base_out_depth` | 100 | printed base depth, outside, rim to back | Clint, 2026-11-10: 100 mm | sourced |
| `base_wall` | 3 | printed base walls and floor (PETG, about 7 perimeters on a 0.4 nozzle, solid) | layout choice for a watertight FDM wall | derived |
| `gasket` | 1 | allowance off the closed depth for the lid's O-ring and fit | assumed until M17 | [TBD-MEASURE] |
| `lid_rim` | 3 x 3 x 3 | #905 lid rim, outside to inside: plastic wall, O-ring channel (white O-ring in it), plastic wall: a 9 mm land; the O-ring path curves in round the four corner bosses | Clint's photo and sketch of the lid, 2026-11-10 (photo-8525 lid-up.jpg) | sourced |
| `lid_boss` | 22 x 21 x 3 | #905 lid corner screw boss: along the long side x along the short side (from the outside edges), wall outside the screw hole | Clint's photo and sketch of the lid, 2026-11-10 (photo-8525 lid-up.jpg) | sourced |
| `rim_tongue` | 2 x 4.5 x 3 x 3.25 | the base's sealing lip: width, height above the land, centre-line offset from the lid's outside edge on the short sides, and on the long sides; it follows the lid channel's S-curve round each corner boss; the land ends at its inner face | cage/lid-rim-spec.md: Clint's 300 dpi lid scans with a steel ruler, 2026-11-11 (11.953 px/mm; the lip path +-0.3, the spans +-0.4): lip 2 x 4.5 on the land; the straights 169.5 x 123.0 apart centre to centre in the 175.5 x 129.5 outline (was 4.0 / 3.5 from the coupon fits r1-r8) | sourced |
| `l1_lid_screw` | 8 x 0 x 0 | L1: the original lid screw: thread diameter, pitch, length (option a, a printed thread to match) | Clint, 2026-11-10 (photo-8528 rim.jpg and notes, via the coordinator): the original base's corner holes are large moulded threads, about 8 mm (coarse plastic thread in the photo); pitch and length not measured | [TBD-MEASURE] |
| `lid_screw_opt` | b | lid screws: (a) a printed thread matching the original screw; (b) M4 stainless screws with washers through the lid's 8 mm holes into M4 heat-set inserts | layout choice (recommended b: brass inserts survive the lid coming off many times, a printed PETG thread wears; the original screw is not needed) | derived |
| `seal_curve_r` | 3.5 x 7.15 | radii of the S-curve's bends round each corner boss, on the lip's centre line: the two outer bends (where it leaves the straight legs), the middle bend (round the boss's inner corner); tangent, axis-aligned exits | cage/lid-rim-spec.md: Clint's 300 dpi lid scans with a steel ruler, 2026-11-11 (11.953 px/mm; the lip path +-0.3, the spans +-0.4): middle R7.15 (7.14-7.16 at all four corners), outer R3.5 (3.0-4.0) (was 3 / 5.5 from the coupon fits) | sourced |
| `seal_s` | 15.4 x 15.4 | the S-curve round each corner boss, lip centre line to lip centre line: the middle run parallel to the short side sits this far in from the short-side lip line, the run parallel to the long side this far in from the long-side lip line | cage/lid-rim-spec.md: Clint's 300 dpi lid scans with a steel ruler, 2026-11-11 (11.953 px/mm; the lip path +-0.3, the spans +-0.4): 15.4 (15.1-15.6 at all four corners) (was 13.5 / 14.0 from the coupon fits) | sourced |
| `corner_r_out` | 4 | the lid's (and the base's) outside corner radius, in plan | cage/lid-rim-spec.md: Clint's 300 dpi lid scans with a steel ruler, 2026-11-11 (11.953 px/mm; the lip path +-0.3, the spans +-0.4): R4 not measured from the scan; coupons r1-r8 used R4 without complaint | [TBD-MEASURE] |
| `ring_fit` | 0 | the rim test ring (cage.py --ring, cage/stl/rim-ring.stl) on the real lid: the lip in the O-ring channel all the way round and through all four S-curves, all four holes under the lid's at once, the outer edge flush on all four sides | pending: Clint prints it and fits the lid; set True and sourced when it fits (the corner coupons r1-r8 and the edge strips are history) | [TBD-MEASURE] |
| `ring` | 3.5 x 8 x 7 | the rim test ring (cage.py --ring): land top, lip top (the ring's height), screw hole diameter | cage/lid-rim-spec.md: Clint's 300 dpi lid scans with a steel ruler, 2026-11-11 (11.953 px/mm; the lip path +-0.3, the spans +-0.4): land Z 0-3.5, lip Z 3.5-8.0, holes 7.0 (an M4 passes at +-1 of spacing) | sourced |
| `m4_washer` | 12 x 1 | M4 large (fender) washer, stainless: OD x thickness, for option b, over the lid's 8 mm hole | ISO 7093-1 size 4 (d2 12, h 1), from the standard's table as remembered: check the ones bought | [TBD-MEASURE] |
| `m4_screw` | 8 x 3.1 x 20 | M4 stainless pan-head screw: head diameter, head height, length (option b) | ISO 7045 M4 head (dk 8, k 3.1), from the standard's table as remembered; length a layout choice: through the lid boss (L1 pending) into the 8 mm insert | [TBD-MEASURE] |
| `lid_pocket` | 14 | the lid's square corner pocket, inside width (the washer must seat in it); the hole 8 mm through its floor | pending: Clint's photo-8526 shows a square pocket with a round counterbored hole; width placeholder | [TBD-MEASURE] |
| `l2_screw_pos` | 9.75 x 10.25 | L2: lid screw centre from the outside edges: from the short side, from the long side | cage/lid-rim-spec.md: Clint's 300 dpi lid scans with a steel ruler, 2026-11-11 (11.953 px/mm; the lip path +-0.3, the spans +-0.4): holes at (+-78.0, +-54.5), 156 x 109 apart: 156 the midpoint of Clint's tape (155) and the maker's DS-AT-1217 H3 157, 109 the maker's W3 and Clint's 108-110; each +-1, not readable from the scan (was 155 x 109) | [TBD-MEASURE] |
| `l4_oring_proud` | -2 | L4: how far the O-ring sits above (+) or below (-) the channel walls | Clint, 2026-11-10 (lid-measure sheet, via the coordinator): inset about 2 mm below the walls | sourced |
| `l5_lid_out` | 175.5 x 129.5 x 4 | L5: lid outside length x width, corner radius (the base matches it; the radius in use is corner_r_out) | cage/lid-rim-spec.md: Clint's 300 dpi lid scans with a steel ruler, 2026-11-11 (11.953 px/mm; the lip path +-0.3, the spans +-0.4) (was 175 x 130 by tape and Adafruit) | sourced |
| `base_905` | 175 x 131 | the original #905 base's outside length x width (wider than the lid) | Adafruit #905 drawing, via the coordinator: base 131 wide against the lid's 128.5 | sourced |
| `l6_body_rib` | 3 x 1.5 | L6: the original base's sealing lip: height, and its offset in from the base's outer edge (rough) | Clint, 2026-11-10 (via the coordinator): 3 mm tall; 1-2 mm in from the base's outer edge, an eyeball estimate (a rough check that disagrees with the channel line) | sourced |
| `box_in` | 123.5 x 169.5 x 120 | printed base inside: width x length (up the pole) x depth floor to closed lid (base 97 inside + lid 24 less the gasket allowance) | from l5_lid_out less 2 x base_wall, base_out_depth, base_wall, lid_depth (its top about 1 mm) and gasket | derived |
| `insert_m4` | 5.6 x 8 | M4 heat-set insert: hole x length | typical M4 heat-set insert for plastics; check the ones bought | [TBD-MEASURE] |
| `corner_keepout` | 20 | the insert post's depth below the seam (the corner land's reach comes from seal_s and rim_tongue) | an M4 heat-set insert (8) with 3 mm of PETG under it, and the screw (L1) | derived |
| `evm_under` | 4 | BQ25798EVM underside: J6 micro-USB (bottom-mounted) and solder tails below the board | J6 Molex 47346-0001 (SLUUCB5E BOM), right-angle bottom mount; height not reached | [TBD-MEASURE] |
| `vent` | 12.5 | M12 pressure-equalising vent: panel hole | typical M12 x 1.5 vent plug; not chosen yet | [TBD-MEASURE] |
| `power_zone` | 82 | box bottom to the lowest card's socket row (the EVM shelf in front of the backplane's lower end) | layout choice: low enough that B3's top clears the lid's upper corner lands by 2 mm | derived |
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
