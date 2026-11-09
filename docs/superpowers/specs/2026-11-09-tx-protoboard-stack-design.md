# TX protoboard stack (r1): design

Status: draft for Clint's approval, 2026-11-09. Builder check done; its questions are answered in place.

**On hold (2026-11-09): the MCU.** The NUCLEO does not fit this stack: it is about 70 mm wide against 50.8 mm, has
no mounting holes, and its 2-row Morpho headers short on the breadboard strips. Clint chose to **spike
splitting the MCU and radio out** (a RAK3172 / STM32WLE5 module on a SolderFul layer, with the NUCLEO's
ST-LINK as the bench programmer), issue #35. The fallback is a carrier perfboard with isolated holes that the
NUCLEO plugs down into (CN7 pin 1 to CN10 pin 1 = 60.96 mm = 24 × 0.1", per KiCad's Nucleo-64 template,
still to be measured on the MB1389). The rest of this design stands either way; the sections naming
the NUCLEO jumper bundle and B3 change with the outcome.

## Intent

The breadboard bench (`hardware/bench-breadboard-r1/`) proved the TX design, except for one thing: the
bq24074 could not charge with the battery INA228 in the loop. Breadboard, Dupont and WAGO resistance
ended charging early (record F1, and again on 2026-11-09). The next step makes the TX a **compact,
soldered unit** that can go into the IP66 box, and replaces as much of the power measurement as it can
with the **BQ25798** (issue #34).

Success is: the TX, its power system and every sensor port fit in the #905 box; the battery charges to
full with current measured in the loop; every outdoor sensor plugs in through a gland to an internal RJ11
jack and is found at boot.

## Goals

- Four DigiKey SolderFul BreadBoards (SOLDERBREAD#02: 81.3 × 50.8 mm, 1.6 mm, 0.1" pitch, 30 rows,
  breadboard pattern: a–e and f–j joined per row, ± rails) stacked on **20 mm spacers** (already built).
- **Five outdoor cables** (TH, baro, UV, wind, rain) each pass a gland and plug into an **internal RJ11
  jack**. Each I2C module is found at boot by its ID EEPROM (`docs/firmware-current-design.md` §4.1).
- **BQ25798EVM** replaces the bq24074 and the solar, USB-C and load INA228s. **One INA228 (0x40,
  battery) and the MAX17048 stay** (Clint, 2026-11-09).
- The battery loop is soldered end to end: no breadboard, Dupont or WAGO in it.
- No OLED.

## Non-goals

- RJ11 ports exposed on the outside of the box (facing down under the unit). Clint: a later "final final"
  version, not now.
- A custom PCB, a bare BQ25798 board, or the 16 MiB SPI flash (#33).
- The outdoor module ends (sensor breakout + EEPROM + jack) beyond the pin map below; they get their own
  build sheet.

## Anti-goals

- Any connector or breadboard contact in the battery current path (the F1 failure), **except the pack's own JST PH mating pair** (Clint, 2026-11-09: keep the pack unmodified and swappable). BATP and the MAX17048 sense tap on B4 right at the JST socket, so that one contact pair is the only resistance between the cell and the charger's sense.
- A port pin map under which plugging a meter cable into an I2C jack, or the reverse, shorts 3.3 V to GND.

## Approaches considered

1. **Cable entry.** (a) **Thread the bare cable through a PG-7 gland, then crimp the plug inside**
   (chosen: 100 RJ12 plugs on hand; needs the Klein VDV226-011 crimper and 4 more PG-7 glands);
   (b) split cable-entry glands that clamp over a plugged cable; (c) waterproof bulkhead couplers.
   Hardwiring cables straight to the boards was not wanted: everything plugs in.
2. **Stack to NUCLEO.** (a) Morpho stacking headers straight onto the NUCLEO (Clint's preference) **does
   not work on this board**: a 2-row 0.1" header lands both rows in one a–e strip and shorts. (b)
   **Boards stack to each other on single-row headers down one column (each pin in its own row strip);
   the stack reaches the NUCLEO through one bundle of female-ended jumpers onto the Morpho pins** (chosen,
   my call after (a) failed). (c) Soldered wire bundles: rejected, hard to service.
3. **Jack split.** **Bottom board: 4 I2C jacks (mux ch0–3; ch3 is the spare the ports design already
   calls for). Board 2: wind and rain.** (Clint, 2026-11-09.) Alternatives were 3 I2C + wind on the
   bottom, or all 5 on one board.

## The stack (bottom to top)

| Board | Name | Contents |
|---|---|---|
| B1 | PORTS | 4 RJ11 jacks on the front edge, column E rows 1–6, 8–13, 15–20, 22–27 (each jack's 6 pins in 6 row strips). PCA9548 #5626, **A0 bridged → 0x71**; ch0–3 → S1–S4 |
| B2 | METERS | WIND and RAIN jacks (the BOB-14021 pair) on the front edge. Cups and rain 10 kΩ pull-ups + 100 nF to GND; vane 10 kΩ pull-up (values from `docs/current-system.md` §4.4, unchanged) |
| B3 | CORE BUS | The NUCLEO jumper bundle lands here. SHTC3 enclosure sensor wired direct, upstream of the mux. 3V3/GND distribution to the stack |
| B4 | POWER | INA228 0x40 in the battery loop, MAX17048 on the cell, S7V8F3 3.3 V regulator, battery JST pigtail soldered in. Leads out to the EVM's BAT and SYS |

Beside the stack on the box floor: the NUCLEO-WL55JC1, the BQ25798EVM and the battery pack.

**Inter-board bus** (single-row header down one column through all four boards): 3V3, GND, SDA, SCL,
MUX_RST (PB14), CUPS (PB5), VANE (PB2), RAIN (PB4). The builder picks the column; each pin sits in a
different row strip.

## RJ11 pin maps (middle four positions only, so any 4- or 6-conductor straight-through cable works)

| Jack | Pin 2 | Pin 3 | Pin 4 | Pin 5 |
|---|---|---|---|---|
| I2C S1–S4 (**my call**) | 3V3 | SDA | GND | SCL |
| WIND (existing, `current-system.md` §4.4) | GND (vane return) | GND (cups return) | CUPS → PB5 | VANE → PB2 |
| RAIN (existing) | — | GND | RAIN → PB4 | — |

Why this I2C order: GND sits between SDA and SCL in untwisted flat cable, and a mis-plug cannot short
the supply. A wind or rain cable in an I2C jack puts a reed switch across SDA–GND (3–4) and the vane
network (≥ about 680 Ω) across 3V3–SCL (2–5). An I2C module in a meter jack gets its 3V3 pin grounded
and its GND pin on a 10 kΩ pull-up: it stays unpowered. **The INVENTORY note that puts 3.3 V on pin 1 is
superseded** (4-conductor cable does not carry pin 1).

Each outdoor I2C module is wired to the same map: its sensor breakout and a 24LC32-class ID EEPROM at
0x50 share the 4 lines.

## Power

```
solar (P110) ─► EVM VAC/VBUS ─┐
USB-C ────────► EVM ──────────┤ BQ25798 ── SYS ─► S7V8F3 ─► 3V3 (NUCLEO CN6.4 + stack)
                              └ BAT ◄── soldered ── INA228 0x40 (B4) ── pack + (JST, soldered)
                                BATP sense ◄── own wire, to the pack + side of the INA shunt
MAX17048 CELL+ ◄── own sense wire at the pack terminal
```

- **BATP** (EVM J5 SNS_BATP, jumper JP9 per issue #34) senses the cell at the pack, not at the EVM, so
  the INA228 shunt and wiring sit outside the charger's voltage sense. This is the fix for F1.
- Battery-loop wire: the 22 AWG solid hook-up is the minimum; the loop budget stays F1's (+ side ≤
  75 mΩ, − side ≤ 40 mΩ), measured once built.
- The NUCLEO is powered at CN6.4 (3V3) with return at CN6.7, as bench mode B.
- **Pack:** Adafruit #353, Li-ion 1S3P 6600 mAh with its own protection board, JST PH lead. Charge current
  stays near the bench's 0.89 A (about 0.13 C); termination about 10% of ICHG.
- **Battery INA228:** Adafruit #5832 (one of the 5 at home). Its shunt sits in the + leg between the pack
  and the EVM's BAT; BATP taps on the pack side of it, so the charger regulates the cell, not the EVM
  terminal. The SYS load hangs off the EVM side, which is fine.
- **EVM before the driver exists (my call):** it charges on its own hardware defaults (cell count and
  limits from its on-board PROG/strap settings). The builder reads the EVM guide (SLUUCB5) for those
  defaults and for which of J5/JP9 is the BATP sense on this revision, and records them. The EVM's
  SDA, SCL, INT and GND are **wired to the stack bus now** (0x6B clashes with nothing), so profile 3 needs
  no rewiring. Its I2C pull-ups must not go to a rail above 3.3 V: disable them and use the 3.3 V
  pull-ups already on the bus.
- **Inputs (my call):** USB-C to the EVM's VIN1, solar to VIN2. The P110 (6.94 V open circuit, about
  8.7 V cold) is inside the BQ25798's input range. The solar cable comes through the sixth gland and lands
  on the EVM's input terminal; its barrel plug is cut or adapted at the box.
- **I2C pull-ups:** the NUCLEO has none on PA11/PA12. Each Adafruit breakout carries its own 10 kΩ, and the
  mux isolates the port channels. The builder checks the bus edges once with the scope; nothing is added
  unless they are slow.
- **Mux address:** the firmware already expects 0x71 (`docs/current-system.md` line 71).

## Firmware

- Today's TX build (`WS_POWER_PROFILE=2`) runs on this stack: missing INA228s and the bq24074 ADC pins
  read INVALID, they do not stop the station (`firmware-current-design.md`, ports 9 and 14). Build it with
  `WS_I2C_MUX=1` and without `WS_BENCH_OLED`.
- The BQ25798 driver (`WS_POWER_PROFILE=3`, now `#error`) is a **separate plan** (issue #34): I2C 0x6B,
  one-shot ADC, MPPT enable, ITERM about 10% of ICHG. This stack does not wait for it.
- The mux part is a PCA9548 (#5626), pin- and register-compatible with the TCA9548A the firmware names.

## Measurements still needed  `[TBD-MEASURE]`

1. #905 box inside floor and inside depth. The stack is about 66 mm plus parts above B4 and tails below
   B1; the box is 75 mm deep outside.
2. BQ25798EVM outline and tallest part.
3. NUCLEO-WL55JC1 outline including the SMA.
4. Battery pack (#353) size.
5. Outer diameter of each cable for the PG-7 glands (they grip about 3–6.5 mm), and whether the RJ11 cables are flat (a round gland does not seal flat cable well).

If the floor cannot hold the NUCLEO, EVM and pack beside the stack, the first fallback is to mount the
EVM on top of B4 on its own spacers.

## Parts (ordered 2026-11-09, DigiKey; rows in INVENTORY.md "On order")

- Ports: 10 × SparkFun BOB-14021 and 20 × Amphenol **87180-066LF** 6P6C jacks. The 87180 replaces the
  sold-out PRT-00132. The BOB's footprint (SparkFun Eagle: 1.27 mm stagger, rows 6.35 and 8.89 mm from the
  peg line, 3.25 mm pegs 10.16 mm apart) matches Amphenol's 54601-x06 exactly; the 87180 is Amphenol's
  listed replacement for it. **Test-fit one jack before soldering.** Base needs 6 BOBs (4 I2C, wind, rain;
  2 on hand), each outdoor I2C module 1 more.
- Module ends: 10 × Adafruit Perma-Proto quarter (1608).
- Per-port protection: 20 × Bourns MF-R010 (100 mA PTC) in each I2C port's 3V3.
- Stack bus: 12 × Sullins PPPC081LFBN-RC 1×8 sockets. Standoffs from the Hilitchi M2/M3 kit: B1→B2 20 mm
  (jack height), B2→B3 and B3→B4 10 mm with the male header's plastic slid off (or a 1 mm washer for 11 mm).
  Stack height about 46 mm.
- Radio (#35): 5 × Wio-E5 mini, 5 × Linx ANT-916-CW-HWR-SMA, 5 × Amphenol 135110-01-06.00 (SMA bulkhead
  jack to straight plug, RG-316, 6"): antenna outside, vertical, on the box top or upper wall.
- NUCLEO fallback: 5 × BusBoard PAD3U, 10 × Sullins PPPC192LFBN-RC (2×19).
- Passives: 0.1 µF X7R, 10 kΩ 1 %, 1 MΩ, shunts, 2-pin headers.
- **Not ordered, still needed:** female-to-female jumpers for SWD from the NUCLEO's ST-LINK to the
  Wio-E5 (Adafruit 266 or equivalent).
- On hand: glands, a modular crimper, premade RJ11 cables, EEPROMs, the PCA9548 mux.

## Next revision (not now)

A **Molex 0432236113** ganged 1×6 6P6C jack (70.7 × 22.6 × 12.8 mm, 11.38 mm port pitch, contacts staggered
1.27 mm in rows 2.54 mm apart, a board lock at each end; measured from Molex's STEP model) puts all six
ports on one edge. Its staggered pins don't fit 0.1" boards, so it waits for the first custom PCB,
together with the ports exposed under the box.

## Left to the builder

- The inter-board header column, header heights, and wire colours.
- Where the mux and the pull-ups sit on B1 and B2 (f–j halves are free beside each jack).
- Strain relief inside the box for each cable.
