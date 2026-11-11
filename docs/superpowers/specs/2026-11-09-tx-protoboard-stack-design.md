# TX protoboard card cage (r3): design

Status: r3, 2026-11-10 (r2 after the electrical and mechanical reviews of r1, 2026-11-09; r3 snaps the cards'
back rails off, moves the backplane to a PAD3U padboard, routes every wire, and takes the box from the maker's
catalogue). The generated design, its checks,
build sheets and renders are in `hardware/tx-stack-r1/` (revised in place; git history keeps r1). Its README
lists what changed from r1 and why, what is still a stand-in, and what Clint must measure.

## Intent

The breadboard bench (`hardware/bench-breadboard-r1/`) proved the TX design, except for one thing: the
bq24074 could not charge with the battery INA228 in the loop. Breadboard, Dupont and WAGO resistance
ended charging early (record F1, and again on 2026-11-09). The next step makes the TX a **compact,
soldered unit** that goes into the IP66 box, and replaces as much of the power measurement as it can with
the **BQ25798** (issue #34).

Success is: the TX, its power system and every sensor port fit in a printed base under the #905 lid; the battery charges to
full with current measured in the loop; every outdoor sensor plugs in through a gland to an internal RJ11
jack and is found at boot; **any card comes out on its own without desoldering**.

## Goals

- Four DigiKey SolderFul BreadBoards (SOLDERBREAD#02: 81.3 x 50.8 mm, 1.6 mm, 0.1 in pitch, 30 rows, a-e and
  f-j joined per row, two rails per long edge) as cards in a printed cage.
- The MCU and radio are a **Seeed Wio-E5 mini** (STM32WLE5JC, issue #35) on its own header on the CORE card;
  the NUCLEO is the bench programmer only (SWD).
- **Five outdoor cables** (TH, baro, UV, wind, rain) each pass a gland and plug into an **internal RJ11
  jack**. Each I2C module is found at boot by its ID EEPROM (`docs/firmware-current-design.md` §4.1).
- **BQ25798EVM** replaces the bq24074 and the solar, USB-C and load INA228s. **One INA228 (0x40,
  battery) and the MAX17048 stay** (Clint, 2026-11-09).
- The battery loop is soldered or screwed end to end: no breadboard, Dupont, WAGO, header, socket or strip.
- No OLED.

## Non-goals

- RJ11 ports on the outside of the box, a custom PCB, a bare BQ25798 board, the 16 MiB SPI flash (#33).
- Print files (STL) for the cage: not until the box inside is measured.
- The outdoor module ends beyond the pin map below.

## Anti-goals

- Any connector or breadboard contact in the battery current path (the F1 failure), **except the pack's own
  JST PH mating pair** (keep the pack unmodified and swappable).
- A port pin map under which plugging a meter cable into an I2C jack, or the reverse, shorts 3.3 V to ground.

## Mechanical: the card cage

The enclosure is a **printed PETG base** (Clint, 2026-11-10) under the original Adafruit #905 clear lid and its
O-ring: 175 x 130 outside (TIBOX 175 long; the width and corner radius are L5 `[TBD-MEASURE]`), 100 mm deep outside,
3 mm walls; inside 124 x 169, 120 deep with the lid closed (the seam at 97). It hangs on its pole by its back (two
moulded lugs and hose clamps), long side vertical, a drip edge over the top seam. The stock body was dropped because
the BQ25798EVM measured 90 x 90 (96 across J8) and did not fit it with 2 mm margins.

The lid interface is from Clint's photos: a 9 mm rim (3 mm wall, a 3 mm channel holding the white O-ring about 2 mm
down, 3 mm wall), the channel curving in an S round each 22 x 21 mm corner boss, the screws 10 mm in from both
outside edges. The base copies it: a 9 mm land, a 2 x 3 mm sealing lip on the channel's centre line and its
S-curves, like the original base's (about 1 mm squeeze on an assumed round 3 mm cord), a solid 3 mm corner land
under each boss, and a corner post with an M4 heat-set insert (3 mm of PETG round it) under each screw. The
original base takes about 8 mm plastic screws in moulded threads; the base uses M4 stainless screws on 12 mm washers
through the lid's 8 mm holes instead (a printed copy of the thread is the other, parametric option). The lip's
height is the original base's 3 mm (Clint); its offset follows the lid's channel. The rim (outline,
lip path, holes) is measured off 300 dpi scans of the lid (`hardware/tx-stack-r1/cage/lid-rim-spec.md`). A whole-rim
test ring, not gated, is printed first and the real lid pressed onto it; `cage/cage.py --stl` refuses the full base
until the ring fits and the screws and the lid's corner pocket (L1) are settled.
PETG's heat deflection (about 70 C, to be checked on the spool's datasheet) against more than 45 C inside in sun: a
light colour and a UV paint or clear coat; ASA is a later-revision option.

Everything is one vertical stack of horizontal shelves, each sliding toward the back, bottom to top: the pack (lies
flat on a tray 2 mm over the gland nuts), the BQ25798EVM (on two moulded ledges, Bumpons off, 2 mm in front of the
backplane's lower end, J8 toward the lid), then the cards B4, B2, B1, B3 (the SHTC3 on the top card, about 84 mm
above the charger). Moulded in the base: a left wall with one slot per card; a right corner post that takes each
card's back-right corner; four posts that hold the **backplane** (BusBoard PAD3U padboard, a pad per hole, cut to
21 x 39 holes; a tinned bus wire on the copper side per bus line; copper side back) 8 mm off the floor over the mux;
a retention bar screwed across the front-left of the stack after the cards are in. The lid's corner lands set the
card heights: a card's parts cannot pass a top corner as it slides out, so the stack sits 3 mm under them.

The cards are horizontal shelves, each with its two back rails snapped off along the line past column j (card
depth 41.91 mm `[TBD-MEASURE]`) and the edge filed flat before any soldering. Each has a **Sullins
PRPC040SBAN-M71RC** right-angle header cut to 1x18 (the 1x18 PRPC018SBAN-M71RC is no longer sold) on its back
edge (column j, rows 1-18), its mating pins 7.36 mm past the snapped edge, which plugs 5.0 mm into a **Sullins PPPC181LFBN-RC** 1x18 socket on the
backplane (5.84 mm of mating pin; at least 4.2 mm if a card sits 0.8 mm short; the socket 2.36 mm clear of the
card, the card edge 10.86 mm from the backplane). The back RJ11 breakout on B1 and B2 overhangs the snapped edge;
its printed spacer's tongue is gripped by the right corner post. Every wire, jumper and lead is routed flat on a
1.27 mm grid around the parts (`layout/route.py`). Card order bottom to top:
B4 POWER, B2 PORTS B + METERS, B1 PORTS A, B3 CORE, at pitches of 15.24, 20.32 and 20.32 mm, each clearing the
tallest part below plus its tails and 0.5 mm. The jacks face the right wall; the cable glands are in the bottom wall's
bosses (six PG-7 #762 for the round port cables, two PG-9 #761 for the flat wind and rain cables, sealed once the
cable is final), with a pitch check; a vent in the bottom wall. The SMA bulkhead is in the right wall below the
upper corner land: the mini's SMA through a right-angle adapter (Amphenol RF 132172) with its arm toward the lid, the
135110 plug on it, the RG-316 bending right in front of the cards (the base's spare depth). The base is parametric
(`cage/cage.py`): the lid interface, the shelves, the EVM outline and the slot allowance are named inputs, and every
shelf is checked with 2 mm margins.

Why a cage and not the r1 standoff stack: r1's soldered bus wires meant it could not come apart (mechanical
C1), the box floor did not hold the stack, pack and charger (C2), and the lid margin was 0.5 mm on a floor
spacer that did not exist (C3). The SolderFul's own strips are too short to carry an 18-line bus, hence the
padboard backplane with its bus wires.

## The cards

| Card | Role | Contents |
|---|---|---|
| B4 | POWER | INA228 0x40 (header pins 5-7 pulled; battery leads on its X1 pads), MAX17048 (cell sense on JP2 VBAT), S7V8F3 3.3 V regulator, battery + lug (Keystone 7328 on an M3 nylon screw) |
| B2 | PORTS B + METERS | Sensor port 4; wind and rain jacks with the 10 k pull-ups, 100 nF filters (now also on the vane), 1N5232B clamps and 1 k series resistors to the MCU |
| B1 | PORTS A | Sensor ports 1-3 |
| B3 | CORE | Wio-E5 mini, SHTC3 enclosure sensor (upstream of the mux), right-angle SWD header at the front edge |
| backplane | bus | Four sockets; the PCA9548 #5626 (A0 bridged, 0x71) on foam behind it, wired by its pads; four QT leads from the bus strips to the ports' mux channels; the charger I2C pins |

Each sensor port is a SparkFun BOB-14021 + Amphenol 87180-066LF jack (on a printed spacer, mouth flush with
the card's right edge, wired to the card by flying leads), an MF-R010 fuse in its 3.3 V, 100 ohm in series on
data and clock, BAT85S Schottky clamps from data and clock to the port 3.3 V and from ground, and a 1N5232B
zener on the port 3.3 V.

**Bus (18 lines, backplane strips 1-18):** 3.3 V supply, ground, sensor port 1 data and clock, cups, vane,
I2C clock, sensor port 2 data and clock, I2C data, rain, ground, sensor port 3 data and clock, mux reset,
spare, sensor port 4 data and clock. On the Wio-E5 mini: I2C data PA15, clock PB15, cups PC0 (LPTIM1_IN1),
vane PB3 (ADC_IN2), rain PB4, mux reset PB14; the console is the mini's own USB-C (USART1 PB6/PB7).

## RJ11 pin maps (middle four positions only, so any 4- or 6-conductor straight-through cable works)

| Jack | Pin 2 | Pin 3 | Pin 4 | Pin 5 |
|---|---|---|---|---|
| Sensor ports 1-4 | 3.3 V | data (SDA) | ground | clock (SCL) |
| Wind (`current-system.md` §4.4) | ground (vane return) | ground (cups return) | cups (wind speed) pulse | vane (wind direction) |
| Rain | — | ground | rain pulse | — |

Why this order: ground sits between data and clock in untwisted flat cable, and a mis-plug cannot short the
supply. A wind or rain cable in a sensor port puts a reed switch across data and ground and the vane network
(at least about 680 ohm) across 3.3 V and clock. An I2C module in a meter jack gets its 3.3 V pin grounded and
its ground on a 10 k pull-up: it stays unpowered. Each outdoor I2C module carries its sensor breakout and a
24LC32-class ID EEPROM at 0x50 on the same four lines.

**Cable limit:** each port's lines are pulled up by about 5 kohm (the module's and the mux's 10 k), which at
100 kHz allows about 236 pF: roughly 2-3 m of flat phone cable at an assumed 50 pF/m `[TBD-MEASURE]`. Longer
runs need 2.2-3.3 k pull-ups at the jack; scope each port with its real cable.

## Power

```
solar (P110) --> EVM VIN2 --+
USB (micro-B J6) -> EVM VIN1 --+ BQ25798 -- SYS (J3) --> S7V8F3 --> 3.3 V supply (bus)
                               +- battery + (J5) <-- INA228 shunt (B4) <-- lug E1 <-- pack + (JST PH)
                                  charger battery sense (BATP, J5 SNS_BATP) <-- 100 ohm R7 <-- lug E1
fuel gauge cell sense (MAX17048 JP2 VBAT) <-- 100 ohm R8 <-- lug E1
```

- **Battery + junction:** the pack pigtail, the shunt input and both sense leads meet on the lug E1, not in a
  free-air splice (mechanical M8). The sense resistors sit at the lug end so a chafed sense wire cannot short
  the pack (electrical m11).
- **Charger set-up before any power** (electrical C1, M1, M2; issue #34), in `build/ASSEMBLY.md`: JP24 off and
  JP22 on (one cell); the sense wire soldered, then JP9 off; JP18 off and a 10 k NTC (Adafruit #372) on J7,
  taped to the pack; JP12, JP17 and JP30 stay. First power without the pack and with JP17 out; read REG0x0A
  (cell count) and REG0x01-02 (charge voltage 4.2 V) and set ICHG to about 0.9 A before connecting the pack.
  The #372 is B 3950 against the EVM's 103AT-sized divider: read TS at room temperature and confirm it is in
  the normal band.
- **Pull-ups:** the EVM's 10 k I2C pull-ups (on its own 3.3 V rail, JP30) cannot be switched off; with the
  breakouts' the upstream total is 1.40 kohm, still above the 0.97 kohm floor.
- **Pack:** Adafruit #353, Li-ion 1S3P 6600 mAh with its own protection board. Charge current near 0.9 A;
  termination about 10 % of ICHG. Battery-loop budget stays F1's (+ side 75 mohm or less, − side 40 mohm or
  less), measured once built.
- **Sensor-power switch on PA9: deferred** (electrical M3). No orderable through-hole current-limited switch
  was found; a shorted port browns out the 3.3 V supply until its MF-R010 trips.

## Firmware

- The Wio-E5 board build (`firmware/board/wio-e5/`, its README states the power profile) runs on this unit;
  missing parts read INVALID and do not stop the station. Build with the mux enabled and without the bench
  OLED.
- The BQ25798 driver (profile 3, now `#error`) is a separate plan (issue #34). The EVM's I2C is wired to the
  bus now (0x6B clashes with nothing).
- The mux part is a PCA9548 (#5626), pin- and register-compatible with the TCA9548A the firmware names.

## Measurements still needed `[TBD-MEASURE]`

The full list, with the key each feeds, is in `hardware/tx-stack-r1/README.md`. The ones that move the cage:
the lid screws and the lid's corner pocket (L1), the rim test ring's fit on the real lid, the snap line, the BQ25798EVM's part heights, and the card slot fit on a printed test slot. Also the cable outer diameters for the PG-7 glands (3-6.5 mm, round cable seals; flat
does not), and each port cable's capacitance.

## Parts

- Ports: SparkFun BOB-14021 and Amphenol **87180-066LF** 6P6C jacks (test-fit one jack before soldering);
  Bourns MF-R010; Vishay BAT85S; onsemi 1N5232B; 100 ohm and 1 k 1/4 W resistors.
- Bus: Sullins PRPC040SBAN-M71RC (right angle, cut to 1x18) per card; Sullins PPPC181LFBN-RC (1x18 female) per
  card on a BusBoard PAD3U padboard with 22 AWG tinned bus wires.
- Battery: Keystone 7328 lug on an M3 nylon screw; Adafruit #372 10 k NTC.
- Radio (#35): Wio-E5 mini, Amphenol RF 132172 right-angle SMA adapter, Amphenol 135110-01-06.00 (SMA
  bulkhead to plug, RG-316, 6 in), Linx ANT-916-CW-HWR-SMA outside, vertical.
- Module ends: Adafruit Perma-Proto quarter (1608).
- On hand: one PG-7 gland, premade RJ11 cables, EEPROMs, the PCA9548 mux. Not yet ordered: the README's list.

## Next revision (not now)

A **Molex 0432236113** ganged 1x6 6P6C jack (70.7 x 22.6 x 12.8 mm, 11.38 mm port pitch, staggered contacts)
puts all six ports on one edge. Its staggered pins do not fit 0.1 in boards, so it waits for the first custom
PCB, together with the ports exposed under the box.
