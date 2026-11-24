# TX stack r3: Wio-E5 mini TX on four SolderFul cards and a backplane, in a printed base

The transmitter is four SolderFul SOLDERBREAD#02 cards, the BQ25798EVM and the battery pack. Each card has its two
back rails snapped off (81.3 x 41.91 mm `[TBD-MEASURE]`). They're all horizontal shelves in one stack. The stack sits
in a printed PETG base (enclosure 4) under the original Adafruit #905 clear lid and its O-ring. The base hangs on its
pole by its back, long side vertical. Every shelf slides in toward the back.

Once it's on the pole, [`MAINTENANCE.md`](MAINTENANCE.md) has what to check, how often, and what each alert means.

Every printed part other than the base (the EVM clips, the lid shade, the retention bar, the test ring and coupon, the pod
boxes and the shield remix) is defined in [`../PRINTED-PARTS.md`](../PRINTED-PARTS.md), with its status, STL, print
pose, dimensions, fasteners and checks.

The base is 120 mm deep outside. It has a 3 mm floor, long walls 4.25 mm thick and short walls 4.0 mm thick. Inside,
it's 121 x 167.5, and 140 deep from the floor to the closed lid. (The drawings use 123.5 x 169.5, which is the lid
frame. The 120 is the base's outside depth.)

The lid interface comes from Clint's photos and lid scans. The lid has a 9 mm rim: a 3 mm wall, a 3 mm O-ring channel
and another 3 mm wall. The channel curves in round 22 x 21 mm corner bosses. The O-ring sits 2 mm down in its channel.
The lid screws are 9.75 mm in from the short sides and 10.25 from the long sides (holes 156 x 109 apart, each +-1,
`[TBD-MEASURE]`).

The base meets the lid on its wall top. That's 4.25 wide on the long walls and 4.0 on the short walls, plus the
15.4 mm corner blocks. There's no 9 mm land.

A sealing lip, 2 mm wide and 2.5 mm tall, stands on the wall top's inside
edge. Its centre is on the channel's centre line (3 / 3.25 mm in from the lid's edge), as printed in enclosure 4. The
corner blocks carry 10 mm printed-thread bores for Clint's 3D-printed lid bolts. There are no heat-set inserts.

The rim follows `cage/lid-rim-spec.md`, measured off Clint's 300 dpi lid scans (2026-11-11). A whole-rim test ring
(`cage/stl/rim-ring.stl`, `cage.py --ring`, not gated) checks the lip, all four S-curves and the four holes on the
real lid first. `cage/cage.py --stl` refuses the full base until the ring fits (`ring_fit`) and the lid-screw positions
(L2, `l2_screw_pos`) are sourced. The corner coupons r1-r8 and the two edge strips are history. Only the last corner
coupon (`cage/stl/rim-coupon.stl`, `renders/rim-coupon-iso.png` and `-top.png`) and the two edge strips
(`rim-edge-long.stl`, `rim-edge-short.stl` and their top renders) stay, because r1-r8 each overwrote the same file. The
code that made them is in git up to c5e3281.

Each card carries a right-angle 1x30 header on its back edge, with its mating pins out past the snapped edge. The
header plugs into a socket on a PAD3U padboard backplane, so you can slide any card out toward the lid on its own.
Each card has one spare pin pulled (B1 27, B2 28, B3 29, B4 30), and its own socket has a key plug in that contact. So
a card seats only in its own slot. A colour dot on each card and slot matches them up: B1 blue, B2 green, B3 yellow,
B4 red.

The battery current crosses a header and its socket only on B4's doubled pins (19-20 and 21-22). That's about 0.5 A a
contact at 1 A (layout check L4 and schematic check 5). Everywhere else it runs in soldered leads, and it touches no
card strip except those pins' own.

| Card (bottom to top) | Role | What it carries |
|---|---|---|
| B4 | POWER | The battery monitor INA228 (0x40), the fuel gauge MAX17048 (0x36), the S7V8F3 3.3 V regulator B4's power pins: pins 19-23 and 26 power, 24-25 its 3.3 V and ground (isolated pads on the backplane); no lead leaves it. |
| B2 | PORTS B + METERS | Sensor port 4 and the wind and rain jacks, with the meter pull-ups, filters, clamps and 1 k series resistors. |
| B1 | PORTS A | Sensor ports 1-3: each a jack breakout, an MF-R010 fuse, 100 ohm series resistors, BAT85S clamps on data and clock and a P4KE6.8A TVS on its 3.3 V. |
| B3 | CORE | The Wio-E5 mini on its header, the enclosure air sensor SHTC3 (0x70) and a right-angle SWD header at the front edge. |
| backplane | bus | BusBoard PAD3U padboard (a pad per hole, no strips) its plated end, 31 rows (lines 0-30) x 38 holes, factory edges right, top and bottom; a bare bus wire on the copper side carries each of the 18 lines and B4's six power lines; the battery + junction (lines 21-22) with R7 and R8, short leads to the EVM and the pack, and the charger's own ground lead (J3 GND to line 12); four generic female sockets, every one 1x30 with a key plug in its card's pulled position (on lines 19-30 only B4's power contacts meet a bus wire; the rest, the key plugs' contacts included, sit on isolated pads), the PCA9548 mux (0x71) behind it on foam, wired by five header leads and four QT cables (#4209, pin ends cut off) whose SDA and SCL wires carry sensor ports 1-4, and the charger I2C pins. |
| shelves below the cards | power | The battery pack (lowest, the heaviest part) on a moulded tray, then the BQ25798EVM (90 x 90, J8 toward the lid) on two moulded ledges; on short leads to the backplane's lower end, never to a card. |

The bus header on every card is a generic 2.54 mm right-angle male header cut to 1x30. It uses rows 1-30 of column j,
pin n goes to backplane line n, and the card's key pin is pulled. It's drawn as the Sullins PRPC drawing, with its
mating pin 5.8 nominal `[TBD-MEASURE]`. It plugs into a generic female strip on the backplane, cut to the same length
(you lose one position at each cut).

The card ends at the snap line (card Y 41.91 `[TBD-MEASURE]`). The header insulator ends at 43.43, and its mating pins
at 49.23 (7.32 past the edge). The socket mouth is at 44.27. That's 2.36 mm clear of the card and 0.84 mm clear of
the insulator, which is the depth stop.

4.96 mm of the 5.8 mm mating pin goes in (at least 4.16 with the card 0.8 mm
short). The card's edge sits 10.86 mm from the backplane. L5 checks all of this, and L13 checks the keys.

Everything here is generated from four sources:

- `schematic/model.py`: the circuit, with plain names for every net, and the r1 → r2 changes with their reasons
- `layout/stack.py`: where every part, pin, jumper and wire goes, on the cards and the backplane
- `cage/cage.py`: the printed cage, parametric. The inputs Clint must measure are named at its top.
- `sources.py`: every dimension, with its source or `[TBD-MEASURE]`

`./run.sh` rebuilds everything and runs every check. It exits non-zero if any step or check fails.

## Files

| Path | What it is |
|---|---|
| `run.sh` | Rebuilds and checks the schematic, the dimension table, the layout, the cage (checks only), the drawings, the build sheets and the renders. It doesn't run `cage.py --solid` / `--ring` or `cage/ring_views.py`. |
| `sources.py` | Every dimension: value, source, status (sourced / derived / TBD). Writes the table at the end of this README. `--check` fails if it's out of step. |
| `schematic/model.py` | The logical schematic: 86 parts and 53 nets, each net with its plain name. Each pin records how it's contacted. Also the RJ11 pin maps, the Wio-E5 functions, the outdoor-line protection, the ERC waivers and the r1 → r2 lists. |
| `schematic/kicad_gen.py` | model.py → `tx-stack-r1.kicad_sch`: parts grouped by function (power, battery and charging, radio and MCU, weather meters, sensor ports, bus, outdoor ends) in framed groups, with drawn wires inside a group and plain-name labels only between groups. |
| `schematic/checks.py` | Schematic checks 1-10 (below), against KiCad's netlist and ERC. |
| `schematic/r1-connections.json` | r1's connections, frozen, for check 10. |
| `schematic/tx-stack-r1.pdf` | The schematic, one sheet. |
| `schematic/blockdiag.py` → `drawings/block-diagram.svg` | One-page block diagram with real part numbers. |
| `layout/stack.py` | Card geometry (hole grid, strips, rails), footprints from each maker's board file, the placements, every conductor, the backplane and the joint card → socket. |
| `layout/route.py` | Routes every wire, jumper and lead on its card: flat, on a 1.27 mm grid, right-angle runs, every part footprint an obstacle. The cut lengths come from the routes. |
| `layout/layout_checks.py` | Layout checks L1-L13 (below). L12 is the handedness: the box frame is left-handed, Xb runs left to right seen from the lid, and lid-centre Y = 61.75 - Xb, so each card goes in as a real card. `--write` rewrites the mechanical table in this README. |
| `cage/cage.py` | The printed base as enclosure 4 (with its two fixes) and its moulded cage. It has the lid interface as named inputs, the lip following the O-ring channel, and four corner blocks with lid-bolt bores for Clint's printed bolts (no heat-set inserts). It also has the card slots, the right corner post, the backplane support pads (no screw posts), the EVM ledge, keeper and fin, the pack tray, the gland and vent holes over pockets in the bottom wall, the SMA bulkhead hole and the mounting flanges. There are no outside bosses and no drip edge. It runs the fit checks with 2 mm margins and the gland pitch. `--solid` builds the solids in CadQuery. `--stl` refuses until the lid-screw positions (`l2_screw_pos`) and the ring fit are sourced. `--ring` writes `cage/stl/rim-ring.stl` (the whole rim from `lid-rim-spec.md`, not gated) and checks it against the spec (mirrors, spans, tangency, hole-to-lip clearance). |
| `cage/shelves-spec.md` | CAD-bot spec for the pack tray and the charger ledges below the cards. Enclosure 3 had none. Enclosure 4 (the v3 print) has them, with fix 1 (tray to Yb 62, ramp from Yb 56). |
| `cage/lid-rim-spec.md`, `cage/lid_rim_spec.py` | The lid rim measured off Clint's 300 dpi scans: outline, the lip's centre line as a segment table, the lip section, the holes. `lid_rim_spec.py` reads it. `sources.py` takes the rim keys from it, and `cage.py --ring` builds the ring straight from the table. |
| `cage/ring_views.py` | The ring's dimensioned top view (spans, one corner's segment points and radii, the hole spacing) and iso view, `renders/rim-ring-top.png` and `rim-ring-iso.png` (needs the CadQuery venv). The full base's solid (`shell_solid`) is now enclosure 4 with its rounded corners and fillets. The box version (`shell`) is used only for the drawings and renders. The lip's S path with the spec's arcs is in the ring only. |
| `layout/drawings.py` | Writes `drawings/B1..B4-top.svg`, `drawings/backplane.svg`, `drawings/cage-side.svg`, and the build sheets `build/B1..B4.md`, `build/BACKPLANE.md`, `build/ASSEMBLY.md`. `--png` also writes PNG copies into `renders/`. |
| `build/ASSEMBLY.md` | The charger jumper steps before any power, the cage, the card order and the leads off the cards. |
| `build/B1..B4.md`, `build/BACKPLANE.md` | Build sheets: the snap-off first, underside wires with routed lengths, top jumpers, parts lowest first with orientation, leads, strip map, checks before power. For the backplane: its cut, bus wires and hole-by-hole table. |
| `render/fetch_models.py` | Fetches the makers' STEP files and two Eagle board files into `render/models/` (not committed), checks each SHA-256, and builds the two boards into STEP with KiCad. |
| `render/MODELS.md` | Every part in the renders: its model source, real / imported / stand-in, and why. Also the login-only models and where to put them. |
| `render/kicad_render.py` | Writes the KiCad boards `render/kicad/tx-stack-B1..B4.kicad_pcb` and `tx-stack-cage.kicad_pcb` and renders them with `kicad-cli pcb render`, each PNG with a legend naming its stand-ins. |
| `renders/*.png` | Every render and a PNG copy of every drawing. |

### Renders and their stand-ins

- Drawings: `block-diagram`, `B1..B4-top` (with the routed wires), `backplane`, `cage-side`.
- KiCad per card: `B1..B4-render-top`, `B1..B4-render-bottom` (the underside wires, with labels that read from
  below), `B1..B4-render-iso`.
- KiCad assembly: `cage-render-iso`, `cage-render-front`, `cage-render-exploded` (the cards pulled 45 mm toward the
  lid), `cage-render-section` (B1, its header and socket, cut at bus line 9, seen from the right).
- Every model, its source and why it is or isn't real: `render/MODELS.md`. Each PNG's legend names its stand-ins.

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

1. KiCad's netlist round-trips to model.py, net for net and pin for pin. Every net that crosses groups carries its plain name.
2. Every connected pin is in exactly one net, and every unused pin in none. Every net has at least two members.
3. The I2C address map (no upstream clash, every 0x50 behind a mux channel, addresses match the firmware) and the upstream pull-up total (1.40 kohm, at or above 0.97 kohm).
4. Each sensor port's 3.3 V comes only through its own MF-R010 from the 3.3 V supply.
5. The battery current crosses a header and its socket only on two pins or more (B4 pins 19-20 and 21-22). The series chain, the junction and the sense resistors are present.
6. The RJ11 pin maps. Sensor ports: 2 3.3 V, 3 data, 4 ground, 5 clock. Wind: 2/3 ground, 4 cups, 5 vane. Rain: 3 ground, 4 rain.
7. The Wio-E5 pins match the firmware's board file.
8. KiCad ERC reports nothing beyond the written waivers.
9. Every outdoor line has its series resistor and clamps. The port pull-up (5 kohm on S1-S3, which carry a module) allows 236 pF. Less a 60 pF allowance for the clamps and boards, that's about 3.5 m of cable at an assumed 50 pF/m `[TBD-MEASURE]`. S4, with no module, has 10 kohm: 118 pF, about 1.2 m.
10. r2's connections differ from r1's only by the listed changes below.

**Layout (`layout/layout_checks.py`):**

- L1: every pin is on a hole, and every conductor end is a real hole or pad. No hole is used twice. Each backplane bus wire is soldered only at real holes of its own line.
- L2/L3: the copper equals the schematic. No strip (card) and no wire-joined pad group (backplane) carries two nets. The PAD3U has no strips, so nothing connects unless a wire does. The check runs without part-internal ties.
- L4: the battery current touches only B4's doubled power-pin strips and their backplane lines, and each crossing is on two pins. The charger's SYS (J3 SYS to line 26) and its return (J3 GND to line 12) each have their own lead to their bus wire.
- L5: the bus is on rows 1-18 of column j on every card and bus wires 1-18 of the backplane. Every header is the 1x30 less exactly its key pin (B1 27, B2 28, B3 29, B4 30), a spare pin with no net. Insertion is 4.96 mm of 5.8 (at least 4.16 with the card 0.8 mm short). The socket body never overlaps the snapped card (2.36 mm clear).
- L6: no two part bodies collide on a card.
- L7: each card pitch clears the tallest part below, its tails and 0.5 mm. Nothing collides with the cage, the backplane, another card, the base's corner blocks (lid-screw bores), or the gland nuts and their cable rise. With the lid on, nothing hits the lid's inner channel wall or corner bosses.
  - Each card slides out alone, and everything fits the box inside. The EVM stays 2 mm in front of the backplane and the charger 0.5 mm under B4. The mux stays clear of the socket tails. L7 lists what sits past the base-lid seam.
  - `cage/cage.py` separately checks that the pack and EVM keep 2 mm from the walls, the lid's inner wall and bosses, the glands and the cage parts.
- L8: every routed wire, jumper and lead (67 of 67) runs on its side of the card in right-angle runs. It crosses no part footprint (a pad lead crosses only its own breakout) and passes over no used hole but its own ends. It shares no grid run with another conductor, except in an insulated lead bundle (at most 4). A bare jumper meets nothing.
- L10: each card comes out alone (Clint's rule, below). No soldered or clamped lead leaves a card. Everything else off a card is its header or a hand plug. The charger and the pack meet only the backplane, and nothing runs card to card except through the backplane.
- L13: the slot keys. Each socket's key plug sits in its card's pulled position, on an isolated pad (no bus wire, no lead). For every card and socket, the card's pins miss the plug only in its own socket, so any other card stubs on it.
- L9: every mating and fixing in the table below. It computes the slot play against the socket lead-in, the room over each plug's latch, the SMA/coax path and the gland bores for the flat cables. It flags anything held by solder or adhesive alone, or reachable only after something else comes out.

## What changed from r1, and why

r1 stacked the boards on standoffs with soldered bus wires between them. The reviews found you couldn't take it
apart (mechanical C1). It also didn't fit the floor (C2), and it had 0.5 mm to the lid (C3). r2 replaces the stack with the
card cage. These are the connection changes (check 10):

- Removed: the B3-B4 socket XS1 and the B4 bus pins XP1, since the cards now plug into the backplane. The QT leads on B1 (W11-W14) are gone: the mux on the backplane takes the sensor ports on cut QT cables in its channels 0-3.
- Added:
  - a right-angle bus header per card (XH1-XH4) and a backplane socket per card (XB1-XB4)
  - the charger I2C pins XJ1 on the backplane
  - the battery + junction (backplane lines 21-22, mechanical M8)
  - 100 ohm resistors R7 and R8 at the tap end of the charger battery sense (BATP) and the fuel gauge cell sense leads (electrical m11)
  - the pack thermistor RT1 on EVM J7, with JP18 removed (M2)
  - the right-angle SMA adapter AD1
  - on every outdoor line, a series resistor and clamps (M5): 100 ohm and BAT85S Schottky clamps (to the port 3.3 V and from ground) on each sensor port's data and clock, and a TVS on each port's 3.3 V (a 1N5232B zener until r3; now a P4KE6.8A, see below)
  - on cups, vane and rain, a clamp (now a P4KE6.8A TVS) and a 1 k series resistor to the MCU, with a new 100 nF filter on the vane (C3)
- Moved: the charger and gauge sense now leave the battery + junction through R7 and R8 on the backplane. EVM J8 pin 1 is the I2C lead's ground. Each port's data and clock pass their series resistors between jack and mux. Each meter line passes its 1 k between the jack side and the MCU pin. AD1 sits between the radio and the coax.
- Renamed: EVM pins are named by terminal (J3 GND as SYSN, J8.2 clock, J8.3 data).

The clamps on the sensor-port data and clock are BAT85S (at most 10 pF at 1 V, 1 MHz, Vishay doc 85513), not zeners.
A DO-35 zener adds 100 pF or more, which would eat the 236 pF budget. Schematic check 9 now adds up the clamp
capacitance on each I2C line and fails over 20 pF (two BAT85S).

## What changed in r3, and why

- Back rails snapped off each card (`sb_snap_y`, card Y 41.91 `[TBD-MEASURE]`) before any soldering, and the edge
  filed flat. The header's mating pins now stand 7.32 mm past the edge into the socket. The card edge is 10.86 mm
  from the backplane.
- RJ11 jacks face the lid (2026-11-16). On B1 and B2, every BOB-14021 stands on a soldered 1x6 male header in row a
  (pin n in its own column and strip). It overhangs the front edge with its mouth toward the lid. The plugs and their
  cable bends sit in front of the cards. The printed spacers, the back jack's tongue, the right post's cut and the
  flying leads are gone. Each port's clamps stand in its jack's strips, with its fuse and supply TVS in a block beside it.
- Backplane on a BusBoard PAD3U padboard (a pad per hole). It's the PAD3U's plated end, 31 lines (0-30) x 38 holes, a
  rectangle with only its left edge cut. It carries 18 bare bus wires, each soldered at every pin of its line, plus
  B4's power lines. The cut step and the hole-by-hole table are in `build/BACKPLANE.md`.

  Since enclosure 4 there are
  no screws and nothing drilled. The board lies on three support pads, and the cards plugged into its sockets hold
  it. The left edge goes in the left wall's groove. The factory right edge goes in a 6.5 mm deep slot in the right
  corner post (Xb 85.8-92.3, `cage/backplane-mount-spec.md`). You tilt it into the slot, then slide it left into the
  groove.
- Slot keys (Clint, 2026-11-16). The four sockets are identical, so any card fitted any slot, and B3 in B4's slot
  would have put the battery on the Wio-E5. Each card pulls one spare pin (B1 27, B2 28, B3 29, B4 30). Its own socket
  takes a key plug there: a cut-off male pin, flush with the mouth, soldered to nothing. A colour dot goes on each
  card and slot (B1 blue, B2 green, B3 yellow, B4 red). L5 and L13 check them.
- Charger ground lead: J3 GND to backplane line 12 (24 AWG stranded, black, beside the SYS lead). Now SYS's return
  doesn't run only through the I2C lead's J8 pin 1 and its KK crimp. L4 checks it.
- Wires routed (`layout/route.py`) instead of drawn straight. The lengths, drawings and renders follow the routes.
- A printed base instead of the #905 body (Clint, 2026-11-10). The EVM measured 90 x 90 (96 across J8) and didn't
  fit the stock body with 2 mm margins. The base is PETG (enclosure 4): 120 deep outside (walls to Yb 117), a 3 mm
  floor, 4.25 mm long walls and 4.0 mm short walls. It mates with the #905's own lid and O-ring.

  Everything is one
  vertical stack of shelves (pack, EVM, B4, B2, B1, B3). The SHTC3 on the top card is about 72 mm above the charger's
  tallest part (layout check L7 note).
- Glands go through the bottom wall over 1 mm pockets (enclosure 4 has no bosses): PG-7 #762 and PG-9 #761, from
  Adafruit's drawings, with a pitch check. Each cable rises out of its gland, turns right under the pack tray and runs
  up the right column past the pack and the EVM (`cage/shelves-spec.md`).
- The lid's corners set the card heights. The lid's corner bosses (22 x 21) and the O-ring's S-curve round them sit
  over solid corner blocks in the base. Each block is 15.4 mm square from the inside faces, floor to wall top, with
  the lid-bolt bores (enclosure 4). So a card's parts can't pass a top corner as it slides out. The card stack is
  10 mm lower (`power_zone` 82). B3's top is about 9 mm under the upper corner blocks (Zb 143.9 vs 153.1, about 7 mm
  counting plug keep-outs).
- The EVM moved forward, 2 mm in front of the backplane's lower end. With the 120-deep base it stays inside the base.
  Its front edge is at Yb 101.6, J8 reaches about Yb 113.6, and the seam is at Yb 117. Its left edge at Xb 8.25 keeps
  J6 clear of the lid's inner channel wall (`cage.py` `EVM_X0`).
- The cage's left wall is 8.5 mm. It was sized against the lid's full 9 mm rim (6 mm inside the wall), so the cards'
  left edges clear it as they slide out.
- The spare depth in front of the cards (Yb 62.4 to the closed lid at 140, with the base's seam at 117) takes the
  RJ11 cables' service loops, the EVM's lead loops and the coax. AD1's arm now points toward the lid. The plug and the
  RG-316 bend fit in front of the cards, and the cable reaches the SMA bulkhead in the right wall. The coax path is
  resolved.
- Renders: imported BOB-14021 and Wio-E5 mini boards and the Adafruit PCA9548 STEP. The header is drawn with its pins
  bent. There are routed wire tubes, bottom views, an exploded cage and a section. See `render/MODELS.md`.

## Protection, sun and outdoor parts (2026-11-23)

Cards B1 and B2 aren't built yet, so these went straight into the design.

- **Supply and meter-line clamps: Littelfuse P4KE6.8A TVS** (D11, D21, D31, D41 on the port 3.3 V; D51, D52, D53 on
  cups, vane and rain), in place of the 1N5232B 5.6 V zener. The zener has a soft knee, leaks 5 uA at 3 V and has no
  surge rating. The P4KE6.8A is a 400 W TVS (10/1000 us) in DO-41: stand-off 5.8 V, breakdown 6.45-7.14 V, about
  10.5 V clamping at its rated pulse current. Nobody makes a through-hole TVS below about 6.8 V, and the SMD ones on
  breakouts (a USBLC6-2SC6 on a SOT-23 adapter, say) would need a DIP carrier across the card's centre channel,
  which bridges strips. Its datasheet only promises leakage at 5.8 V (1 mA max), so every one gets screened at 3.3 V
  before it goes in (Session 3 step 08: under 1 uA, which is under 8 mV of error at the vane's divider). The lowest
  one goes on the vane, D52. The I2C data and clock keep their BAT85S pairs: a TVS is hundreds of pF.
  - DO-41 is 2.7 mm across, so on B2 D51 and D52 stand on their ground-strip holes (d4, d7) with the banded lead
    looped over, the wind jack's cups and vane wires moved to c5 and c6, and D53 stands 5.5 mm up on its lead, over
    J22's header and C2 (layout check L6 caught all of these).
- **Pack fuse F5: Littelfuse 021701.6HXP** (5 x 20 mm glass, 1.6 A fast-acting, 35 A breaking at 250 V) in a
  **Schurter 8601.2000** in-line holder (wire leads, 6.3 A, DigiKey 486-3835-ND), spliced into PG1's red lead within
  30 mm of the socket. The #353 pack can give 3.3 A continuous and its leads and the JST PH are rated 2 A; nothing
  protected the pack + run to the junction. The most the path carries is the 0.9 A charge (56 % of 1.6 A), the
  system's own draw and radio bursts are far below that. A PTC was the other choice, but its 0.3 ohm or so would
  sit between the cell and the sense junction and skew the fuel gauge. A blown fuse looks like a missing pack on the
  console (`vbat_mv` from the EVM, no INA228 bus volts). Two spare fuses go in the box's bag.
- **Lid shade** (`cage.py --shade`, `cage/stl/lid-shade.stl`, white PETG). The #905 lid is clear polycarbonate. Sun
  on it puts something like 14 W into the dark boards inside. Spread over the box's 0.13 m2 of skin, that's 17-26 K
  over the outside air (`cage.shade_estimate()`: 800 W/m2, 85 % through the lid, 90 % absorbed, 4-6 W/m2K out; none
  of it measured). On a 25 C day that passes the charger's 41.8 C WARM stop. The shade is a cap over the lid: a plate
  12 mm above it on four feet, a skirt down the lid's sides with a 3 mm air gap, and 14 windows in the skirt above the
  lid's top so the air moves through. Crush ribs hold it on the lid's sides, and it pulls off by hand. A cap beats a
  shade on an arm because the lid faces away from the pole. Paint or foil on the lid was the third choice: it would
  stop you seeing in, and paint flakes. The plate's height over the bolt heads (`lid_head_proud`) and the rib grip
  (`shade_rib_fit`) are guesses until Clint measures the printed bolts and prints one.
- **Antenna AE1: Taoglas TI.96.A113**, screwed straight onto the SMA bulkhead jack in the box's right wall. There's
  no cable (Clint, 2026-11-23). The ANT-916-ID-2000-SMA from the previous change was wrong: it's a remote-mount
  antenna on a 2 m cable and a bracket. The TI.96.A113 is a 915 MHz half-wave dipole (900-940 MHz; the firmware runs
  915.0 MHz, `radio_cfg.h`). It's 203 mm long and 12.7 mm across, with an SMA(M) plug on a hinge, IP67, -40 to +85 C,
  PC+PBT inside a TPEE jacket. A dipole needs no ground plane, which suits a plastic box. The bulkhead end of CX1
  (Amphenol 135110-01-06.00, "SMA Straight Bulkhead Jack to SMA Straight Plug") is a standard SMA jack, not RP-SMA,
  so the SMA(M) plug mates with it. The inside pigtail is still CX1, from the bulkhead to AD1 on the mini's SMA-K.
  - **Weather.** Taoglas says IP67 and "outdoors or indoors", but its datasheet gives no UV rating. So once it's
    screwed on and folded, wrap the coupling nut, the hinge and the jack's thread in 3M Scotch 23 self-amalgamating
    tape, then cover that with 3M Scotch Super 33+ vinyl tape, which takes the sun. Scotch 23 on its own isn't
    UV-stable. Check the jacket for chalking or cracks once a year (`MAINTENANCE.md`).
  - **The fallback** is the Abracon AANE-WH-0039-1 (868/915 MHz whip, SMA(M), IP65, UV-resistant ABS, swivels
    straight, 45 or 90 degrees). It's the only one I found that states a UV rating, but I found no DigiKey or Mouser
    stock for it.
  - **Which way it points.** The box hangs long side vertical, and the bulkhead is in the right wall at Zb 60 (about a
    third of the way up from the bottom wall, not near the top), with its axis horizontal. Screw the antenna on
    straight, then fold it 90 degrees at the hinge so it stands vertical, tip up. Vertical is the right polarisation
    for the gateway's antenna. The whip runs up beside the right wall, about 22 mm out from it, and its tip ends about
    70 mm above the top wall. It's about 100 mm in front of the pole (the box hangs by its back and the bulkhead is at
    Yb 94). That's about a third of a wavelength, so a metal pole will push the pattern a little away from itself.
    That's fine for the PoC: watch the RSSI on the gateway.
- **Vent: Amphenol LTW VENT-PS1YBK-N8002**, an M12 x 1.5 screw-in ePTFE vent (DigiKey
  1754-VENT-PS1YBK-N8002-ND). It goes in the hole the bottom wall already has (Xb 50, Yb 85, `cage.VENT`), so the
  base doesn't change. I haven't opened its own drawing yet: check its panel hole and nut against the 12.46 mm hole
  before printing the base.
- **S4 blanking plug: a 4 x 20 mm ISO 8734 dowel pin, A1 stainless.** No maker sells a blanking plug for a PG-7's
  seal, and "any nylon rod" isn't a part. A ground dowel pin is round, smooth, 4 mm (inside the seal's 3.0-4.3 mm)
  and won't creep.

## Lightning and surge

What the box can take, and what it can't. It's a plastic box on a metal, earthed pole, bonded to it at the SMA
bulkhead. This is about induced surges and static, not about surviving a strike nearby.

- **The RJ11 ports.** Each line has a series resistor (100 ohm on I2C, 1 k on the meters) and clamps behind it: BAT85S
  pairs to the port's 3.3 V and ground on I2C, a P4KE6.8A on each port's 3.3 V and on cups, vane and rain. That
  handles ESD from a hand on a plug (IEC 61000-4-2 class) and the small transients a few metres of cable pick up from
  a nearby switching load or a strike a long way off. It won't save anything from a strike on the pole or the mast
  next to it. The PTC on each port's 3.3 V (MF-R010) limits what a shorted or wet cable can draw.
- **Solar input: D6, a Littelfuse P4KE15A across EVM J2** (Clint, 2026-11-23: no longer optional). The Voltaic P110
  is a 6 V panel: about 7.2 V open circuit at 25 C and roughly 8.7 V at -30 C (`docs/failure-modes.md`). The
  firmware sets the BQ25798's VAC over-voltage cut-off to 12 V (`vac_ovp`; 11.6-12.4 V, TI datasheet 7.5), so a cold
  panel never trips it. The surge risk is the 2 m panel lead. The P4KE15A (400 W, DO-41, sources `solar_tvs`):
  - its stand-off is 12.8 V, above the panel's 8.7 V and above the cut-off's 12.4 V worst case, so it never
    conducts in normal use and the charger's own OVP acts first on a slow over-voltage;
  - it breaks down at 14.3-15.8 V and clamps at about 21.2 V at its rated pulse current (about 19 A), under the
    BQ25798's 30 V absolute maximum on VAC1, VAC2 and VBUS (datasheet 6.1). That leaves about 9 V of margin.
  - It mounts in J2 itself: cathode (the banded end) to VIN2, anode to GND. Each lead shares a Phoenix Contact
    AI-TWIN 2 x 0.75-8 GY twin ferrule (3200807) with the solar lead's core. The body lies along J2's wire side.
    Session 8 step 12 has the steps.
- **The antenna.** No gas-tube arrestor. The pole is earthed now, but the antenna screws straight onto the bulkhead,
  so an arrestor would mean an extra adapter sticking out of the wall, more loss and another connector to seal. The
  bond below does the main job. If the antenna ends up the highest point on the mast, revisit this.
- **Bonding to the pole (required: the pole is metal and earthed, Clint 2026-11-23).** The SMA bulkhead's body is
  the one place where outside metal meets circuit ground (through the coax shield). Bond it to the pole, so the
  antenna's shield, the circuit ground and the pole sit at the same potential when something nearby lifts the
  ground:
  - **Lug:** a Panduit PV14-14R-L ring terminal (16-14 AWG, 1/4 in stud) on the jack's 1/4-36 outside thread. The
    order out from the wall: the sealing washer, the lug, the lock washer, the nut. It has to be clamped metal to
    metal under the nut. Check that the antenna's coupling nut still gets 4 mm of thread past that stack. If it
    doesn't, leave the rubber washer out and seal the hole with a ring of silicone instead.
  - **Wire:** 14 AWG stranded copper, green THWN-2 (rated for sun), as short and straight as you can, with no sharp
    bends and no coil. Crimp the lug on, and heat-shrink the crimp.
  - **Pole clamp:** a SatelliteSale SS-GSG9-1 grounding strap (adjustable, for 1/2-2 in pipe, set-screw stud for
    10-14 AWG). It fits the station's pole, which is about 1 in. For a pole over 2 in, use its 12 in version, SS-GSG12-1. It's galvanised steel: I found no
    adjustable stainless earthing strap sold in hobby channels. Clean the pole to bare metal under it and smear the
    contact with an antioxidant paste (Ideal Noalox) before you tighten it.
  - Session 8 step 14 has the steps. `MAINTENANCE.md` has the yearly check.

## Not yet ordered

This is everything the build needs that's in neither the DigiKey cart (2026-11-09) nor `INVENTORY.md`. Quantities
include spares. The stock and price come from digikey.ca on 2026-11-10. That lookup is a snapshot, and the repo
doesn't keep it. Today's stock counts differ.

These are on hand, so they're not listed:

- per `INVENTORY.md`: the M3 heat-set inserts (200) for the retention bar and the EVM clip. The backplane has no
  screws since enclosure 4. The lid takes Clint's printed bolts, so the M4 inserts (100, also on hand) aren't needed.
- per `INVENTORY.md`: the Adafruit 1311 22 AWG solid (stripped for the bus), the M3 screws for the bar, and the RJ12
  6P6C crimp plugs (100, generic, modelled as the standard 6P body after Cinch 32-5996UL).
- per `INVENTORY.md`: 5 Adafruit #1131 JST PH 2-pin cables (received 2026-11-05), set aside for the pack and board
  pigtails.
- per Clint (2026-11-13): the generic 2.54 mm right-angle male headers and female strips (every one cut to 1x30), and
  24 AWG solid and stranded hook-up wire. `INVENTORY.md` records only a 2.54 mm male/female header kit and 7 rolls of
  24 AWG (solid or stranded not recorded).
- the PETG: Clint's own supply. It isn't in `INVENTORY.md`, which records only PLA.

| Part | Maker part | DigiKey | Need | Buy | Stock | Price (CAD, 1 off) | Note |
|---|---|---|---|---|---|---|---|
| Signal clamp diode | Vishay BAT85S-TR | BAT85SCT-ND | 16 | 20 | 44,459 | 0.74 | |
| TVS clamp 6.8 V 400 W (D11-D41, D51-D53) | Littelfuse P4KE6.8A | not looked up | 7 | 10 | not checked | - | Screen each at 3.3 V before fitting (Session 3 step 08): under 1 uA. Three spare for the screen. |
| Pack fuse (F5) | Littelfuse 021701.6HXP, 5 x 20 mm 1.6 A fast | not looked up | 1 | 3 | not checked | - | Two spares in the box's bag. |
| In-line fuse holder (F5) | Schurter 8601.2000 | 486-3835-ND | 1 | 1 | in stock | - | Wire leads, 6.3 A. Spliced into PG1's red lead next to the pack. |
| Solar input TVS (D6) | Littelfuse P4KE15A | not looked up | 1 | 2 | not checked | - | Across EVM J2, cathode to VIN2 (Lightning and surge). |
| Twin ferrules for D6 in J2 | Phoenix Contact AI-TWIN 2 x 0.75-8 GY (3200807) | not looked up | 2 | 5 | not checked | - | Each holds a D6 lead and a solar core. Crimp with the bootlace tool. |
| Antenna (AE1) | Taoglas TI.96.A113 | not looked up | 1 | 1 | not checked | - | 915 MHz dipole, IP67, hinged SMA(M), screws straight onto the bulkhead. Fallback: Abracon AANE-WH-0039-1. |
| Joint tapes for AE1 | 3M Scotch 23 (self-amalgamating) and 3M Scotch Super 33+ (vinyl, over it) | - | 1 roll each | 1 each | not checked | - | Over the coupling nut, the hinge and the thread. |
| Bonding lug | Panduit PV14-14R-L (16-14 AWG, 1/4 in stud) | not looked up | 1 | 2 | not checked | - | On the bulkhead's outside thread, under its nut. |
| Bonding wire | 14 AWG stranded copper, green THWN-2 | - | about 1 m | 1 m | - | - | Lug to the pole clamp. Cut to length. |
| Pole earthing clamp | SatelliteSale SS-GSG9-1 (1/2-2 in pipe), or SS-GSG12-1 for a bigger pole | - | 1 | 1 | not checked | - | Galvanised strap with a set-screw stud. Antioxidant paste (Ideal Noalox) under it. |
| Series and sense resistor 100 ohm | Stackpole CF14JT100R | CF14JT100RCT-ND | 10 | 15 | 308,663 | 0.16 | The Yageo kit has 5. `INVENTORY.md` also lists 30 Yageo MFR50SFTE52-100R (1/2 W): check whether they fit before you buy these. The cart's CF14JT1M00 (1 Mohm, 50) matches no part here, so check that line. |
| SMA right-angle adapter (AD1) | Amphenol RF 132172 | ACX1249-ND | 1 | 1 | 10,603 | 20.40 | Pending Clint's measurement of the 135110 plug length. Its arm points toward the lid. |
| Cable glands PG-7 (round port cables) and PG-9 (flat weather-meter cables, seal out, packed) | Adafruit #762 and #761 (Clint has one of each), or LAPP 53111000 (M12) for the PG-7s | 2181-53111000-ND | 5 PG-7 + 2 PG-9 | 5 PG-7 + 1 PG-9 | LAPP not stocked (2 weeks) | bulk only | Need is from `cage.py` `GLANDS` (enclosure 4). With one of each on hand, this buy leaves one spare PG-7 and no spare PG-9. Add silicone or split grommets for the two flat cables. |
| Blanking pin for the spare S4 PG-7 | dowel pin ISO 8734 4 x 20, A1 stainless | - | 1 | 1 | not checked | - | S4 has no pod yet, and an empty PG-7 doesn't seal. The pin sits in the gland's seal (3.0-4.3 mm) with the cap tightened until a pod is added (`cage.GLAND_BLANK`, sources `gland_blank`). |
| Hose clamps for the mounting flanges' slots | stainless worm-drive, SAE size 20 (about 3/4-1-3/4 in, 19-44 mm), band 12.7 mm wide or less | - | 2 | 2 | - | - | The pole is about 1 in (25.4 mm). Round it and the flange between one flange's two slots (27.5 mm apart, 3.5 x 14), each band closes to about 34 mm as a circle, mid-range for a size 20. The 14 mm slots take a band up to 12.7 mm. The two on hand were bought for the shield arm, but its slots are only about 4 mm tall (pods-r1 `pole_clamp_env`), so check which band fits where. |
| Pressure-equalising vent | Amphenol LTW VENT-PS1YBK-N8002 (M12 x 1.5, ePTFE) | 1754-VENT-PS1YBK-N8002-ND | 1 | 1 | 0 on the 2026-11-23 check (more were due 2026-11-20) | 7.31 | In the bottom wall's existing hole (`cage.VENT`). Check its panel hole against 12.46 mm. |
| Lid shade | printed, white PETG (`cage/stl/lid-shade.stl`) | - | 1 | - | - | - | Print plate down. Clint's own PETG. |
| USB-C to micro-B cable (EVM J6) | any | - | 1 | 1 | not checked | - | |
| Hook-and-loop strap (pack), foam tape (mux) | any | - | 1 each | 1 each | not checked | - | |

## Mechanical connections

**Rule (Clint, 2026-11-13): each card (B1-B4) can be pulled out independently of every other card, and inspected.**
No card has a soldered or clamped wire leaving it. Everything that leaves a card goes through its backplane header,
or it's an ordinary plug on that card that comes out by hand (an RJ11 port cable, the SMA coax, the SWD or USB-C
lead).

The charger and the pack connect only to the backplane. Nothing runs from one card to another except through
the backplane. To take a card out, you only take the retention bar off, unplug its own plugs, then pull it straight
out. You never need to take another card out first (layout check L10, with L7's slide-out and plug-clearance checks).

The table lists every mating and fixing: how it's held, what takes the force and how it comes apart. The Flag column
marks anything held by solder or adhesive alone, or that you can't reach or remove without taking something else
apart first.

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
| RJ11 plug latch and cable | the jack latch; the latch is on the plug, 12.9 mm free over the tightest plug (B2 J21 RJ11 plug (standard 6P body after Cinch 32-5996UL)); the plugs go in from the lid side (mouths at Yb 72.8); each flat cable leaves its plug toward the lid, bends down in front of the cards (the plug and the bend reach Yb 97.8, 42.2 mm short of the lid), crosses right to the right column (cage/shelves-spec.md: Xb 100-122, beside the EVM and the pack) and down it to the cable space under the pack tray, then along the floor to its gland in the bottom wall | the latch, then the gland's seal (strain relief) | press the latch (lid open, from the front), pull; loosen the gland nut to pull the cable through |  |
| Wio-E5 mini on B3 | soldered on its own 2 x 12 header (not in sockets) | the header pins | desolder 24 pins | held by solder alone; cannot come off without desoldering 24 pins |
| Wio-E5 mini USB-C console | the receptacle's friction; cable plugged from the left with the lid open | the mini's receptacle and its header | pull the plug |  |
| SMA, adapter and coax to the bulkhead | AD1 screwed on the mini's SMA-K, its arm toward the lid; the 135110 plug screwed on AD1; the cable bends right in front of the cards and runs down the right column to the bulkhead jack low in the right wall (enclosure 4: Yb 94.14, Zb 60.38) | the coax is clipped to the cage at its bend so a pull on it reaches the bulkhead, not the mini's SMA | unscrew the plug at AD1 (8 mm spanner), then lift B3 out |  |
| B4's power pins (the battery path) | header pins 19-20 (charger battery +, after the shunt) and 21-22 (the battery + junction) doubled, 23 gauge sense, 26 SYS (24-25 its 3.3 V and ground, on isolated pads), in the B4 socket on lines 19-26; the junction, R7 and R8 and the leads to the EVM and the pack are on the backplane | the socket contacts (about 0.5 A each on the doubled pins at 1 A) | pull B4 out: the battery path opens at its header, nothing to unscrew |  |
| Battery pack | lies flat on the pack tray, the lowest shelf (the heaviest part low); a hook-and-loop strap through the tray | the tray's front lip and the strap | open the strap, unplug the JST PH, slide it out |  |
| Charger (BQ25798EVM) | a shelf: its side edges on two moulded ledges, a stop at the back, a clip at the front on two M3 screws into heat-set inserts (Yb 106; the board has no mounting holes); the Bumpon feet (H1-H4, 3M SJ-5303) peeled off first | the ledges; the terminal screws are tightened from above, in the room under B4 | unscrew its leads at its terminals (they run to the backplane, not to a card), unscrew the front clip, slide it toward the lid on its service loops | its underside parts (J6, tails: 4 mm [TBD-MEASURE]) must clear the 2 mm ledges at the edges |
| Backplane on its pads | no screws (enclosure 4): three plain floor pads behind it; the left edge in the left wall's groove and its rail, the factory right edge in a 6.5 mm deep slot (Xb 85.8 to 92.3) in the right corner post (tilted into the slot, slid left into the groove); the four cards plugged into its sockets hold it in place | three plain pads and the groove and slot floors take the card insertion push; the groove and slot roofs and the plugged cards take the pull | after every card is out: slide it right to the slot's end, lift the left side, out | removable only after all four cards are out; loose until the cards are in |
| Lid to the printed base | four of Clint's 3D-printed bolts through the lid's 8 mm holes into the Ø10 bores in the base's corner posts (no heat-set inserts; Clint, 2026-11-17), 156 x 109 apart (9.75 / 10.25 in from the lid's edges, cage/lid-rim-spec.md); the base's wall top under the lid's rim, its 2 x 2.5 sealing lip in the lid's O-ring channel | the bolts squeeze the O-ring; the lid's rim takes a knock | undo the four printed lid bolts | fastening settled (Clint's printed bolts, no inserts); still open: the rim test ring's fit on the real lid |
| Base to the pole | two mounting flanges on the short ends, in the floor plane (enclosure 4), each with two 3.45 x 13.95 slots (Xb 47.95 and 75.45): hose clamps or straps through the slots; no screw through the back into the box | the flanges' roots on the end walls and the floor | open the clamps |  |
| Cables through the glands | five round cables (the four sensor-port cables S1-S4 and the solar lead) in PG-7s (#762, seal 3.0-4.3 mm; 5 PG-7s, 0 spare) through the bottom wall over 1 mm pockets (no bosses), each passed through its gland before its inside plug is crimped (a 6P plug, about 12 mm across its corners, passes no gland bore); the flat wind and rain cables in PG-9s (#761) with the seal out and the gap packed with silicone or a split grommet, their factory plugs cut off and new 6P plugs crimped inside | the gland's seal (round) or the sealant (flat); a drip loop below each gland outside, so water runs off the loop and not along the cable into the gland | loosen the cap (round); cut the sealant (flat) | a flat cable is sealed once its position is final and then comes out only by cutting the seal |
<!-- mechanical:end -->

## Deferred, with reasons

- Sensor-power switch on PA9 (electrical M3). We found no orderable through-hole current-limited switch, so the
  model marks the pin "not wired". A short on one port still browns out the 3.3 V supply until its MF-R010 trips.
- Firmware README profile and pin notes (m10). They're outside this directory, so they wait for a firmware change.

## Open questions

- **The bulkhead's outside thread length.** The sealing washer, the bonding lug, the lock washer and the nut all
  go on the jack's outside thread, and the antenna's coupling nut needs about 4 mm after them. Measure the real
  135110 jack before Session 8.
- **AE1's UV life.** The TI.96.A113's datasheet says IP67 but nothing about UV. The tape covers the joint, not the
  whip's jacket, so look at it every year.
- **The lid shade's two guesses:** how far the printed lid bolts' heads stand proud of the lid (`lid_head_proud`, 7
  assumed; the plate clears them by 5) and how hard the crush ribs grip (`shade_rib_fit`, 0.3). Print one and try it.

- **The lid interface isn't fully settled.** The rim, the corner bosses, the screw positions (L2) and the O-ring's
  inset (L4) are from Clint. The channel depth doesn't matter (Clint). Here's what's still open:
  - L1, the screws: settled. `lid_screw_opt` is (c), Clint's 3D-printed bolts in the corner posts' Ø10 bores, with
    no heat-set inserts (Clint, 2026-11-17). Option (a), a printed thread copying the original base's large moulded
    threads (about 8 mm), stays parametric and needs its pitch and length. Option (b), M4 screws into inserts, is
    superseded. The holes are outside the O-ring, so they need no seal.
  - L5 and the rim come from `cage/lid-rim-spec.md` (300 dpi scans, 2026-11-11). The lid is 175.5 x 129.5. The
    straight lips are 169.5 x 123.0 apart centre to centre (3.0 in from the short edges, 3.25 from the long). Each S
    is 15.4 deep with R3.5 outer and R7.15 middle bends. The holes are 156 x 109 apart (9.75 from the short edges,
    10.25 from the long), each about +-1 `[TBD-MEASURE]`. 156 is between Clint's tape (155) and the maker's 157. For
    the full base this changed the outline from 175 x 130 (the lid frame is now 123.5 x 169.5), the lip insets from
    4.0 / 3.5, the S from 13.5 / 14.0, the radii from 3 / 5.5 and the screws from 155 x 109.
  - L6, the lip height. Enclosure 4 as printed has a 2 x 2.5 lip (`enc_lip`). `cage/lid-rim-spec.md`,
    `sources.rim_tongue` and `cage.py --ring` build it 2 wide x 4.5 tall, so the test ring has 4.5. Clint's earlier
    note on the original base (`l6_body_rib`) says 3 tall. Which height seals best waits on Clint's report of the
    test ring on the real lid. Nothing changes until then.
  - The lip sits on the lid channel's centre line, because that's what must seal. Its offset and width are named
    inputs (`rim_tongue`). Clint's eyeball of the original lip, 1-2 mm in from the base's edge, disagrees with that
    line. The original base is about 1.25 mm wider a side than the lid, so that would put the lip under the lid's
    outer wall. The squeeze on the O-ring (assumed a round 3 mm solid cord, 2 mm down) follows from whichever height
    is right.
- PETG in sun. Its heat-deflection temperature is about 70 C at 0.45 MPa. Check the spool's datasheet, because
  Bambu's pages refuse scripts. The inside could go above 45 C in sun. That's an estimate: there's no measurement or
  review text for it in the repo. The plan is a light colour and a UV paint or clear coat outside.
- The EVM's heights (15 mm tallest part above, 4 mm J6 and tails below) aren't measured. The EVM sits 2 mm in front
  of the backplane's lower end, and its top is 12.6 mm under B4. It must clear the 2 mm ledges at its edges. With
  enclosure 4 the seam is at Yb 117, and nothing reaches the lid tray. The EVM's front edge is at Yb 101.6, and J8
  sticks out about 12 mm past it (`evm_j8`). The I2C lead's plug and first bend (`evm_j8_lead`, 15, TBD) come after
  that.
- Glands and cables. The weather-meter cables are flat, about 2.3 x 6.6 (derived from TE 5-555042-3's cable entry).
  Each goes through a PG-9 with the seal out (bore 10.5). 7.0 across the cable plus 0.5 mm of sealant a side fits.

  The gap is packed with silicone or a split grommet, sealed only once the cable's position is final. The round
  cables (S1-S4 and the solar lead) take five PG-7s (3.0-4.3 mm), with no spare: enclosure 4 dropped the sixth
  gland. Measure those cables.
- Plugs and glands. A 6P plug is about 11.7 mm across its corners (12.2 with the latch). That's more than either
  gland's bore (PG-7 7.9, PG-9 10.5 with the seal out). So every cable goes through its gland with no plug on its
  inside end, and you crimp that plug after. Clint has 6P crimp plugs, but a 6P crimp tool is needed and isn't listed
  yet.

  The weather meters' factory plugs get cut off outside and re-crimped inside, in the same order
  (`build/ASSEMBLY.md` step 2.6). Still open: do Clint's 6P6C plugs hold the meters' narrower flat cable on the right
  positions, or are 6P4C plugs needed? Put a drip loop below every gland.
- RJ11 jack. The BOB-14021s take the Amphenol 87180-066LF (11.5 mm, RS listing). The 4UCON 14869 (SparkFun
  PRT-00132, 15.70 mm high) would be too tall under the next card: it needs 21.8 mm on the header, and there are
  18.72. Clint has bare BOB-14021 boards and loose jacks (2026-11-16), nothing assembled. Check that the loose jacks
  are the 87180-066LF before you solder.
- Thermistor bias. The #372 NTC is B 3950, but the EVM's TS divider assumes a 103AT (B 3435). Read TS at room
  temperature before the first charge (`build/ASSEMBLY.md`).
- Mini back-feed. The bus 3.3 V back-feeds the mini's AP2112. With USB-C in for the console, two regulators run in
  parallel (accepted, electrical m3).
- B4 power through the backplane (resolved 2026-11-13). The battery path, its senses and SYS reach B4 on header pins
  19-23 and 26, so B4 slides out with nothing to undo. If you pull B4, the battery path opens, because the shunt is on B4.
  The EVM then sees no battery, and that's the intended way to power down.

  The doubled socket
  contacts' resistance isn't measured `[TBD-MEASURE]`. A few milliohm per pair is a few mV at 1 A. Only the INA228's bus-voltage
  reading sees it, because the charger (BATP) and the gauge sense the junction itself on the backplane.

## Measurements for Clint

The floor sheet M1-M13 isn't needed any more, because the printed base replaces the stock body. These are still
`[TBD-MEASURE]`. Most are TBD keys in `sources.py`. Where an item is sourced, derived or has no key, it says so.

1. The #905 lid, copied by the printed base. In from Clint (2026-11-10): the rim 3 + 3 channel + 3 = 9 mm
   (`lid_rim`) and the corner bosses 22 x 21 with 3 mm outside the hole (`lid_boss`). Also L4, the O-ring 2 mm below the
   channel walls (`l4_oring_proud`). L2, from the 2026-11-11 lid scans: the screws are 9.75 mm from the short edges
   and 10.25 from the long (156 x 109 apart, each +-1, `l2_screw_pos`, `[TBD-MEASURE]`). They're no longer 10 mm from
   both edges. Still needed:
   - the rim test ring on the real lid (`ring_fit`): the lip in the channel all round and through the four S-curves,
     all four holes at once (156 x 109, each +-1: `l2_screw_pos`), and the outer edge flush on all four sides
   - the lid's corner radius (`corner_r_out`: R4 assumed, not measured from the scan, though `l5_lid_out` itself is sourced)
     and the O-ring's cross-section (a round 3 mm cord assumed, no `sources.py` key)
   - L1, the original screw's diameter, pitch and length (`l1_lid_screw`): only if you go back to option (a). The
     lid takes Clint's printed bolts (option c), so the M4 screw, washer and pocket measurements aren't needed.
2. The BQ25798EVM's tallest part (`evm`) and what hangs below it (J6, tails: `evm_under`). The M3 heat-set inserts'
   length and knurl diameter (`insert_m3`, for the retention bar and the EVM clip). The lid takes printed bolts, so
   there are no M4 inserts.
3. The snap line: card Y of the cut between column j and the inner back rail (`sb_snap_y`).
4. The card slot fit on a printed test slot (`slot_clear`), and the socket's lead-in (`align_tol`).
5. Solder tails and underside wires below a card, after the first card (`tails`).
6. The generic header and socket (`ra_*`, `socket_*`), a standing DO-35 diode's height (`diode_stand_h`), and the 24 AWG insulation OD (`wire24`).
7. The PG-9 locknut across corners (`gland_pg9_nut`). The PG-7's lengths are scaled from the PG-9 (`gland_pg7`).
8. Each round port cable's outer diameter. It has no `sources.py` key, and the PG-7 takes 3.0-4.3 mm per
   `gland_pg7`. Also the sealant round a flat meter cable (`sealant`). The flat cable's 2.3 x 6.6 (`flat_cable`) is
   derived from the TE 5-555042-3 plug drawing.
9. An RJ11 plug, its boot and cable bend (`plug_len`, `plug_bend`), and the room a finger needs over its latch
   (`finger`).
10. The USB-C console plug overmould (`usbc_plug`) and the mini's USB-C height (`mini_usbc_h`).
11. The Amphenol 132172 adapter's arms (`sma_ra`), the mini's SMA overhang (`mini_sma_out`), the 135110 cable's
    straight plug (`sma_plug_len`), the RG-316 bend radius (`rg316_bend`) and the antenna's length (`ant_len`).
12. The QT socket height (`qt_h`).
13. The foam pad under the mux (`foam`), the breakout PCB thickness (`breakout_t`) and the S7V8F3's inductor
    (`s7v8f3_h`).
14. A test fit of one jack to confirm `jack_h` (sourced, 11.5 mm from the RS listing). Also each port cable's
    capacitance against the 236 pF limit (assumed 50 pF/m, not a `sources.py` input).

## Dimension sources

Status `[TBD-MEASURE]` means we found no source. The drawings use the value as a labelled placeholder until someone
measures it.

The `pad3u_*` rows come from Clint's PAD3U scan (`scan_20261113142805.pdf`). That scan isn't in the repo, so those
values rest on commit 82edf8a and `cage/backplane-mount-spec.md`. The pixel arithmetic in each row is consistent.

A few generated rows are known to be off. Their fixes belong in `sources.py`, so the table below still shows the old
text:

- `pad3u_plated_edge`: its stated derivation gives 2.74 (5.39 from line 30), not 2.83. It's `[TBD-MEASURE]` either
  way (calipers).
- `rg316_bend`: 5 x 2.5 mm OD is 12.5, not 12.7. 12.7 is 0.5 in, which some RG-316 makers list as the minimum static
  bend radius. Others give 15 mm.
- `coax_len`: 152.4 less two 20 mm plugs is 112.4, so 110 is a rounded-down allowance. Clint's fit (2026-11-17)
  stands.
- `do35`: the onsemi 1N5221B case 017AG (DO-204AH) gives a body 4.56 x 1.91 max. The 2 is an envelope rounded up from
  that. Vishay's BAT85S is doc 85513, not 88146.
- `power_zone`: 82 is a layout choice that drops the stack so B3's top sits under the upper corner blocks. That's
  about 7 mm clear in enclosure 4 (Zb 145.8 vs 153.1), not 2 mm.

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
| `ant_len` | 203 x 12.7 | AE1 antenna, Taoglas TI.96.A113: length (hinge included) x diameter. It screws straight onto the bulkhead jack outside and folds 90 degrees at its hinge to stand vertical, tip up | Taoglas TI.96.A113 datasheet rev B: 203 mm tall, 13 mm (12.7) across, SMA(M) on a hinge, IP67, 900-940 MHz, PC+PBT/TPEE, -40 to +85 C, no ground plane needed (a dipole) | sourced |
| `solar_tvs` | 12.8 x 14.3 x 15.8 x 21.2 | D6, Littelfuse P4KE15A across EVM J2: stand-off, breakdown min, breakdown max, clamping at its rated pulse current (V) | Littelfuse P4KE series (P4KE15A: VR 12.8 V, VBR 14.3-15.8 V at 1 mA, VC 21.2 V at about 19 A, 400 W 10/1000 us); against the P110's cold Voc (about 8.7 V), the BQ25798's VAC OVP at the 12 V setting (11.6-12.4 V, datasheet 7.5) and its 30 V absolute maximum on VAC1/VAC2/VBUS (6.1) | sourced |
| `bond_lug` | 6.6 x 14 | the bonding lug on the SMA bulkhead's outside thread: ring hole x wire (AWG). Panduit PV14-14R-L (16-14 AWG, 1/4 in stud) on the jack's 1/4-36 thread, 14 AWG stranded copper (green, THWN-2) to a pole clamp | Panduit PV14-14R ring terminal family (the -14R is the 1/4 in stud); the 1/4-36 SMA bulkhead thread (cage/external-openings-spec.md); the hole is the 1/4 in stud's nominal clearance: measure the lug | [TBD-MEASURE] |
| `sma_plug_len` | 20 | straight SMA plug and its crimp ferrule on the 135110 cable | typical; measure the cable | [TBD-MEASURE] |
| `sma_bulkhead` | 94.14 x 60.38 x 6.44 x 14.2 | SMA bulkhead in the right wall: Yb, Zb of its axis, the hole, the inner nut seat | enclosure 4 STL (as printed, audited 2026-11-17, sheets/audit-enc4); moved from Yb 86.14, Zb 144.6 in enclosure 3 | sourced |
| `coax_len` | 110 | 135110-01-06.00 coax: cable between the two plugs | the part number's 6.00 in (152.4) overall less two straight plugs (sma_plug_len); Clint, 2026-11-17: the 6 inch cable fits the bulkhead at Zb 60.38, better than the old high bulkhead (no tight bend to make) | sourced |
| `mount_flange` | 31.75 x 91.75 x 28 x 6 x 3.5 x 14 x 48 x 75.5 x 8 x 7 | mounting flanges on both short ends, in the floor plane: Xb from, to, reach past the end wall, thickness (Yb -3 to 3), slot width x length (round ends), the two slots' Xb, the far corners' radius, the 45 degree gusset's leg (along Yb from the flange's face and along Zb from the end wall) | enclosure 4 STL (as printed, audited 2026-11-17, sheets/audit-enc4): slot centres at Zb -18 and 187.5 | sourced |
| `enc_wall_top` | 117 | the printed base's wall top (the seam land), Yb | enclosure 3 and 4 STLs (as printed, audit-enc3, audit-enc4): walls to Yb 117 with a 2.0 lip | sourced |
| `enc_inside` | 1.25 x 122.25 x 1 x 168.5 | the printed base's inside faces: left and right walls (Xb), bottom and top walls (Zb); the long walls 4.25 thick, the short ones 4.0, outside faces Xb -3 / 126.5 and Zb -3 / 172.5 | enclosure 4 STL (as printed, audited 2026-11-17, sheets/audit-enc4) | sourced |
| `enc_outer_r` | 9 | the printed base's outside corner radius (its four edges along Yb, floor to wall top) | enclosure 4 STL (as printed, audited 2026-11-17, sheets/audit-enc4): fitted to the outline at Zb -2.9 to 4 | sourced |
| `enc_blocks` | 15.4 x 8 x 2.5 | the four corner blocks, floor to wall top: square from the inside faces, the radius of each block's inner corner, the fillet where a block meets a wall | enclosure 4 STL (as printed, audited 2026-11-17, sheets/audit-enc4): faces at Xb 16.65 / 106.85, Zb 16.4 / 153.1 | sourced |
| `enc_lid_bores` | 10 x 80.75 x 114.7 x 14.6 | the lid-screw bores in the corner blocks, at the lid's screw positions: diameter, from Yb, chamfer from Yb, chamfer diameter at the wall top (45 degrees) | enclosure 4 STL (as printed, audited 2026-11-17, sheets/audit-enc4): four bores at Xb 7.25 / 116.25, Zb 6.75 / 162.75 | sourced |
| `enc_lip` | 2 x 2.5 | the sealing lip on the wall top's inside edge, all round the walls and the corner blocks: width, height above the wall top | enclosure 4 STL (as printed, audited 2026-11-17, sheets/audit-enc4): Yb 117 to 119.5, its inner face flush with the walls' and blocks' inside faces | sourced |
| `enc_pockets` | ((16.5 x 35.5) x 73.63 x ?) x ((40.5 x 59.5) x 96.3 x (64.5 x 8)) x ((64.5 x 83.5) x 38.63 x ?) | gland pockets in the bottom wall's inside face (the wall 4.0, Zb -3 to 1; each pocket 1.0 deep, to Zb 0): Xb from-to, the Yb apex of its 45 degree roof (each runs from the floor, Yb 0), and where one narrows at 45 degrees to the vent's land (from Yb, to this half-width) | enclosure 4 STL (as printed, audited 2026-11-17, sheets/audit-enc4): lands of radius 9.5 round the glands at Yb 25 and 60, 8 round the vent | sourced |
| `enc_glands` | 13 x 12.5 x 15.5 | gland and vent holes through the bottom wall: PG-7, the M12 vent, PG-9 | enclosure 4 STL (as printed, audited 2026-11-17, sheets/audit-enc4) (PG-7 13.0, the vent 12.46; all teardrop-topped for printing); the PG-9s 15.5 (fix 2, not in enclosure 4) | sourced |
| `enc_sma_seat` | 1 | the SMA bulkhead's inner nut seat (sma_bulkhead's 14.2) depth into the right wall | enclosure 4 STL (as printed, audited 2026-11-17, sheets/audit-enc4): Xb 122.25 to about 123.25 | sourced |
| `bar_bore` | 4 x 6.5 | M3 heat-set insert bore for the retention bar's two inserts in the left wall's front face: diameter x depth | enclosure 3 and 4 STLs (as printed; the bore for an M3 x 5.7 insert about 4.6 across the knurl: knurl - 0.6, length + 0.8) | derived |
| `bar_inserts` | 5 x 76.5 x 146.5 x 3.4 | the retention bar's two M3 heat-set inserts in the left wall's front face: Xb, the two Zb, and the bar's clearance holes (the bores bar_bore, for insert_m3) | enclosure 3 STL (as printed, audited 2026-11-16, sheets/audit-enc3): bores at Xb 5.00, Zb 76.50 and 146.50; the lower bore leaves 0.48 of plastic to the B4 slot's floor | sourced |
| `bp_groove` | 2.5 x 0.5 x 2.5 | the left wall's backplane groove: depth into the wall's slot-side face, height over the board's component face, the board's sideways fit travel (lowered this far to the right, then slid left into the groove) | cage/backplane-mount-spec.md: 0.5 clear past the board's edge; floor level with the support pads' tops, a 45 degree roof | derived |
| `insert_m3` | 5.7 x 4.6 | M3 heat-set insert for the retention bar and the EVM clip (the only inserts: the backplane has no screws since enclosure 4, the lid takes printed bolts): length, knurl diameter | cage/backplane-mount-spec.md: assumed; measure with calipers before printing | [TBD-MEASURE] |
| `bp_posts` | 8 | backplane copper face off the base's floor (the mux on its foam and the socket tails behind it, 2 mm clear) | mux 4.8 + foam 1 + 2 = 7.8 | derived |
| `cage_plate` | 0 | cage base plate: none (the printed base's floor carries the cage) | layout choice | derived |
| `cage_wall` | 8.5 | cage left wall thickness; card slots 2 mm deep | layout choice: the cards' left edge clears the base's 6 mm rim lip (the full 9 mm land less the 3 mm wall) by 0.5 mm as they slide out | derived |
| `slot_clear` | 0.3 | card slot width over the 1.6 mm card (print tuning) | Bambu H2D first-print allowance (the base is PETG); tune on a test slot | [TBD-MEASURE] |
| `bar` | 2.5 | retention bar thickness in front of the card front edges | layout choice | derived |
| `tails` | 1.5 | solder tails and bottom-side wires below a card | typical; measure after the first card | [TBD-MEASURE] |
| `clear` | 0.5 | minimum clearance kept between parts | layout rule | derived |
| `do35` | 4.56 x 2 | DO-35 body length x diameter (BAT85S) | Vishay BAT85S (doc 85513) outline DO-35/DO-204AH | sourced |
| `diode_stand_h` | 7 | standing DO-35 height (body on one lead, the other looped over) | 4.56 body + 1 lead + loop; check on the part | [TBD-MEASURE] |
| `do41` | 5.2 x 2.7 x 0.86 | DO-41 body length x diameter x lead diameter, all max (the P4KE6.8A TVS clamps D11-D41, D51-D53) | Vishay P4KE6.8A thru P4KE540A datasheet (vishay.com/en/product/88365), DO-204AL (DO-41) outline: body 4.1-5.2 long, 2.0-2.7 across, leads 0.86 max (into the SolderFul's 1.0 holes) | sourced |
| `tvs_stand_h` | 8.6 | standing DO-41 height (body on one lead, the other looped over) | 5.2 body + 0.8 lead below it + a 2.6 loop over the top; check on the part | [TBD-MEASURE] |
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
| `base_out_depth` | 120 | printed base depth, outside, back to wall top (the lip stands 2.5 above it) | enclosure 4 STL (as printed, audited 2026-11-17, sheets/audit-enc4): floor Yb -3 to 0, walls to Yb 117 | sourced |
| `base_wall` | 3 | printed base floor (the lid frame's wall: the lid outline less this is the frame W x H); the walls are thicker (enc_inside) | enclosure 4 STL (as printed, audited 2026-11-17, sheets/audit-enc4): floor 3.0 (Yb -3 to 0) | sourced |
| `gasket` | 1 | allowance off the closed depth for the lid's O-ring and fit | assumed until M17 | [TBD-MEASURE] |
| `lid_rim` | 3 x 3 x 3 | #905 lid rim, outside to inside: plastic wall, O-ring channel (white O-ring in it), plastic wall: a 9 mm land; the O-ring path curves in round the four corner bosses | Clint's photo and sketch of the lid, 2026-11-10 (photo-8525 lid-up.jpg) | sourced |
| `lid_boss` | 22 x 21 x 3 | #905 lid corner screw boss: along the long side x along the short side (from the outside edges), wall outside the screw hole | Clint's photo and sketch of the lid, 2026-11-10 (photo-8525 lid-up.jpg) | sourced |
| `rim_tongue` | 2 x 4.5 x 3 x 3.25 | the base's sealing lip: width, height above the land, centre-line offset from the lid's outside edge on the short sides, and on the long sides; it follows the lid channel's S-curve round each corner boss; the land ends at its inner face | cage/lid-rim-spec.md: Clint's 300 dpi lid scans with a steel ruler, 2026-11-11 (11.953 px/mm; the lip path +-0.3, the spans +-0.4): lip 2 x 4.5 on the land; the straights 169.5 x 123.0 apart centre to centre in the 175.5 x 129.5 outline (was 4.0 / 3.5 from the coupon fits r1-r8) | sourced |
| `l1_lid_screw` | 8 x 0 x 0 | L1: the original lid screw: thread diameter, pitch, length (option a, a printed thread to match) | Clint, 2026-11-10 (photo-8528 rim.jpg and notes, via the coordinator): the original base's corner holes are large moulded threads, about 8 mm (coarse plastic thread in the photo); pitch and length not measured | [TBD-MEASURE] |
| `lid_head_proud` | 7 | Clint's printed lid bolt: its head's top above the lid's top face (the lid shade's plate clears it) | lid_bolt: the head is 11 tall on a seat no more than 20.7 above the wall top, and the lid is 25 deep (lid_depth), so up to 6.7 above the lid top; rounded up; measure with the lid on | [TBD-MEASURE] |
| `shade` | 3 x 2.4 x 12 x 15 x 8 | the lid shade (cage.py --shade): the skirt's gap to the lid's sides, plate and skirt thickness, the plate's underside above the lid's top face, how far the skirt reaches down the lid's sides, the feet's diameter | layout choice: a 12 mm air gap over the lid (the bolt heads plus 5), a 3 mm chimney gap round its sides; 2.4 is six 0.42 mm perimeters | derived |
| `shade_rib_fit` | 0.3 | the lid shade's crush ribs: how far each reaches past the skirt gap into the lid's side (what holds the shade on) | a first guess for PETG ribs on the #905 lid's polycarbonate sides; tune on the first print until it pushes on by hand and doesn't lift in a gust | [TBD-MEASURE] |
| `lid_screw_opt` | c | lid fastening: (a) a printed thread matching the original screw; (b) M4 stainless screws into M4 heat-set inserts (superseded); (c) Clint's 3D-printed bolts in the corner posts' lid bores (enc_lid_bores), no inserts | Clint, 2026-11-17: the four corner posts take his 3D-printed bolts; there are no heat-set inserts in them | sourced |
| `lid_bolt` | 11 x 11 x 6.5 x 23 x 10 x 7 x 1.5 x 11 x 45 | Clint's printed lid bolt (option c), from the head's top: head diameter x height (a 4-lobe drive recess 4 deep, r 1.27 to 3.13), plain shank diameter x length, then the thread: major, minor, pitch (right hand), length; overall length. Into enc_lid_bores' shallow printed thread (a 10.0 circle orbiting the axis 0.26 off-centre, 1.5 pitch, right hand): about 0.26 radial engagement. Full thread engagement needs the head's seat no more than 20.7 above the wall top (Yb 117); the tip reaches the bore's floor (Yb 80.75) only below the wall top | lid_bolt.stl from Clint, 2026-11-17 (sliced: scratchpad bolttools/prof.py, hand.py; the bore by bore2.py on enclosure 4) | sourced |
| `seal_curve_r` | 3.5 x 7.15 | radii of the S-curve's bends round each corner boss, on the lip's centre line: the two outer bends (where it leaves the straight legs), the middle bend (round the boss's inner corner); tangent, axis-aligned exits | cage/lid-rim-spec.md: Clint's 300 dpi lid scans with a steel ruler, 2026-11-11 (11.953 px/mm; the lip path +-0.3, the spans +-0.4): middle R7.15 (7.14-7.16 at all four corners), outer R3.5 (3.0-4.0) (was 3 / 5.5 from the coupon fits) | sourced |
| `seal_s` | 15.4 x 15.4 | the S-curve round each corner boss, lip centre line to lip centre line: the middle run parallel to the short side sits this far in from the short-side lip line, the run parallel to the long side this far in from the long-side lip line | cage/lid-rim-spec.md: Clint's 300 dpi lid scans with a steel ruler, 2026-11-11 (11.953 px/mm; the lip path +-0.3, the spans +-0.4): 15.4 (15.1-15.6 at all four corners) (was 13.5 / 14.0 from the coupon fits) | sourced |
| `corner_r_out` | 4 | the lid's (and the base's) outside corner radius, in plan | cage/lid-rim-spec.md: Clint's 300 dpi lid scans with a steel ruler, 2026-11-11 (11.953 px/mm; the lip path +-0.3, the spans +-0.4): R4 not measured from the scan; coupons r1-r8 used R4 without complaint | [TBD-MEASURE] |
| `ring_fit` | 0 | the rim test ring (cage.py --ring, cage/stl/rim-ring.stl) on the real lid: the lip in the O-ring channel all the way round and through all four S-curves, all four holes under the lid's at once, the outer edge flush on all four sides | pending: Clint prints it and fits the lid; set True and sourced when it fits (the corner coupons r1-r8 and the edge strips are history) | [TBD-MEASURE] |
| `ring` | 3.5 x 8 x 7 | the rim test ring (cage.py --ring): land top, lip top (the ring's height), screw hole diameter | cage/lid-rim-spec.md: Clint's 300 dpi lid scans with a steel ruler, 2026-11-11 (11.953 px/mm; the lip path +-0.3, the spans +-0.4): land Z 0-3.5, lip Z 3.5-8.0, holes 7.0 (an M4 passes at +-1 of spacing) | sourced |
| `l2_screw_pos` | 9.75 x 10.25 | L2: lid screw centre from the outside edges: from the short side, from the long side | cage/lid-rim-spec.md: Clint's 300 dpi lid scans with a steel ruler, 2026-11-11 (11.953 px/mm; the lip path +-0.3, the spans +-0.4): holes at (+-78.0, +-54.5), 156 x 109 apart: 156 the midpoint of Clint's tape (155) and the maker's DS-AT-1217 H3 157, 109 the maker's W3 and Clint's 108-110; each +-1, not readable from the scan (was 155 x 109) | [TBD-MEASURE] |
| `l4_oring_proud` | -2 | L4: how far the O-ring sits above (+) or below (-) the channel walls | Clint, 2026-11-10 (lid-measure sheet, via the coordinator): inset about 2 mm below the walls | sourced |
| `l5_lid_out` | 175.5 x 129.5 x 4 | L5: lid outside length x width, corner radius (the base matches it; the radius in use is corner_r_out) | cage/lid-rim-spec.md: Clint's 300 dpi lid scans with a steel ruler, 2026-11-11 (11.953 px/mm; the lip path +-0.3, the spans +-0.4) (was 175 x 130 by tape and Adafruit) | sourced |
| `base_905` | 175 x 131 | the original #905 base's outside length x width (wider than the lid) | Adafruit #905 drawing, via the coordinator: base 131 wide against the lid's 128.5 | sourced |
| `l6_body_rib` | 3 x 1.5 | L6: the original base's sealing lip: height, and its offset in from the base's outer edge (rough) | Clint, 2026-11-10 (via the coordinator): 3 mm tall; 1-2 mm in from the base's outer edge, an eyeball estimate (a rough check that disagrees with the channel line) | sourced |
| `box_in` | 121 x 167.5 x 140 | printed base inside: width x length (up the pole) x depth floor to closed lid (base 117 inside + lid 24 less the gasket allowance) | enc_inside, base_out_depth less the floor, lid_depth (its top about 1 mm) and gasket | derived |
| `evm_terms` | (J1 x GND x VIN1) x (J2 x VIN2 x GND) x (J3 x GND x SYS) x (J5 x GND x SNS_BATP x BATTERY) | EVM terminal blocks: each block's positions in order from the board's back edge (backplane side) toward the lid edge (J8) | TI SLUUCB5E Figure 4-1 silk (J2: VIN2 on the square pad, PGND; J5: PGND, BATP, BATTERY; J1, J3: PGND first) and Table 1-2 | sourced |
| `evm_term_y` | (J1 x 34.11 x 39.19) x (J2 x 58.81 x 63.89) x (J3 x 40.56 x 45.64) x (J5 x 55.25 x 60.33 x 65.41) | EVM terminal blocks: each position's screw centre, from the board's back edge, in evm_terms' order | TI SLUUCB5E (BQ25798EVM user's guide), Figure 4-1 top layer, scaled at 16.74 px/mm on the 90 x 90 outline (300 dpi render), one centre per block (J1 36.65, J2 61.35, J3 43.10, J5 60.33; +-1 mm); the positions step 5.08 mm from it (On-Shore ED120 pitch) | derived |
| `evm_j6_y` | 44.5 x 52.9 | EVM J6 (micro-B, bottom-mounted, left edge): from, to, from the board's back edge | TI SLUUCB5E (BQ25798EVM user's guide), Figure 4-1 top layer, scaled at 16.74 px/mm on the 90 x 90 outline (300 dpi render); +-1 mm | derived |
| `evm_j7` | 61.8 x 70.5 x 79.8 x 87.2 | EVM J7 (Molex 0393570002, 2-position 3.5 mm block, the external thermistor): x from-to from the left (J6) edge, y from-to from the back edge; EXT THERM on the left, AGND on the right | TI SLUUCB5E (BQ25798EVM user's guide), Figure 4-1 top layer, scaled at 16.74 px/mm on the 90 x 90 outline (300 dpi render); +-1 mm; Table 1-2 | derived |
| `evm_jp` | (JP9 x 83.2 x 73.3 x 3 x x) x (JP12 x 39.6 x 77.2 x 2 x y) x (JP17 x 55.1 x 64.1 x 2 x y) x (JP18 x 51.2 x 77.2 x 2 x y) x (JP22 x 47.1 x 6.4 x 2 x y) x (JP24 x 54.8 x 6.4 x 2 x y) x (JP30 x 3.8 x 73.8 x 2 x y) x (JP32 x 59.3 x 22 x 2 x y) | EVM jumpers this build touches: name, centre x from the left edge, y from the back edge, pins, the axis the pins run along (JP9 left to right: BAT, BATP, BATTERY) | TI SLUUCB5E (BQ25798EVM user's guide), Figure 4-1 top layer, scaled at 16.74 px/mm on the 90 x 90 outline (300 dpi render); +-1 mm; Table 1-3 | derived |
| `solar_p110` | 5.71 x 1.67 x 6.94 x 1.9 | Voltaic P110 10 W panel: Vmp, Imp (A), Voc, Isc (A, estimated) | voltaicsystems.com P110 page and Adafruit #5369: Vmp 5.71 V, Imp 1.67 A, Voc 6.94 V; Isc not published, taken as about 1.15 x Imp | derived |
| `wire22` | 0.644 x 1.6 x 53 | 22 AWG stranded hook-up wire (the solar lead): conductor diameter, insulation OD, resistance mohm/m | AWG 22 = 0.644 mm, 52.96 mohm/m at 20 C (0.326 mm2 copper); OD about 1.5-1.7 for PVC hook-up wire | derived |
| `evm_under` | 4 | BQ25798EVM underside: J6 micro-USB (bottom-mounted) and solder tails below the board | J6 Molex 47346-0001 (SLUUCB5E BOM), right-angle bottom mount; height not reached | [TBD-MEASURE] |
| `vent` | 12.5 | M12 pressure-equalising vent: panel hole | Amphenol LTW VENT-PS1YBK-N8002, M12 x 1.5 screw-in ePTFE vent (DigiKey 1754-VENT-PS1YBK-N8002-ND); hole from the M12 thread, the series datasheet not opened: check its panel hole and nut | [TBD-MEASURE] |
| `power_zone` | 82 | box bottom to the lowest card's socket row (the EVM shelf in front of the backplane's lower end) | layout choice: low enough that B3's top clears the lid's upper corner lands by 2 mm | derived |
| `gland` | 13 x 16.6 | PG-7 (#762) gland: panel hole x nut across corners | hole: enclosure 4 STL as printed (13.0, audited 2026-11-17, sheets/audit-enc4; the 11.5 mm screw end (Adafruit #762 PG-7 gland, adafruit.com/product/762) goes in without reaming); nut: the PG-9's 22 scaled by 11.5 / 15.2 | derived |
| `gland_pg7` | 11.5 x 6 x 16.6 x 11.4 x 3 x 4.3 | PG-7 (#762): thread, thread length inside (L1), body outside (L2), cap (L3), cable min, max | Adafruit #762 PG-7 gland, adafruit.com/product/762: 11.5 mm screw end, cable 0.118-0.169 in; L1, L2, L3 the PG-9's scaled by 11.5 / 15.2 | derived |
| `gland_blank` | 4 x 20 | blanking rod in the spare S4 PG-7 (no pod on S4 yet; an empty PG-7 doesn't seal): diameter, length | ISO 8734 dowel pin 4 x 20, A1 stainless (h6, ground smooth): a stock part, inside the PG-7 seal's 3.0-4.3 mm range (gland_pg7); 20 mm leaves a grip past the cap | derived |
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
