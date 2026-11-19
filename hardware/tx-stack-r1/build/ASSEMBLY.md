# Assembly: charger set-up, the printed base, shelves, cards, cables

`layout/drawings.py` writes this sheet. Read it with `drawings/cage-side.svg`, `build/B1..B4.md` and `build/BACKPLANE.md`.

## 1. Charger (BQ25798EVM) before any power: jumper changes (TI SLUUCB5; issue #34)

The EVM ships set for two cells. Do these in order, with nothing connected:

1. **JP24 off, JP22 on** (PROG: one cell, 1.5 MHz). JP22 is the only PROG jumper fitted.
2. **Battery sense wire first, then JP9 off.** Solder the charger battery sense lead to J5 SNS_BATP. It comes from R7 on the backplane (its free leg at line 24, hole 7). Only then remove JP9, so BATP never floats.
3. **JP18 off, thermistor on J7.** Fit the Adafruit #372 10 kohm NTC (B 3950) to J7 and tape it to the pack. The EVM's TS divider is set for a 103AT (B 3435), so the cold and hot thresholds move by a few degrees. Read the TS percentage over I2C at room temperature. Check that it sits in the normal band before you charge.
4. **JP12, JP17 and JP30 stay in.** JP30 powers the EVM's 3.3 V PULLUP rail. That rail holds the I2C pull-ups R39 (SCL) and R40 (SDA), 10 kohm each. R41 and R42 on the same rail pull up /INT and /CE. Only the SCL/SDA pair counts toward the bus total (1.40 kohm, schematic check 3).
5. There's one status LED, D13 (the STAT LED). It sits on JP32, which is fitted as shipped, and draws about 0.6-0.7 mA when lit. Leave it, or pull JP32 to remove it.
6. USB in is J6, micro-B (JP7 on VIN1). Use a USB-C to micro-B cable from the 2 A adapter.
7. **First power without the pack and with JP17 out** (charge disabled). Over I2C, read REG0x0A (cell count) and REG0x01-0x02 (charge voltage 4.2 V). Set the charge current (ICHG) to about 0.9 A (spec charger set-up, electrical C1/M1/M2, and issue #34). The JP22 note says 2 A, and the datasheet default is 1 A. Then refit JP17 and connect the pack.

## 2. Print the base (`cage/cage.py`)

1. Print the rim test ring first (`cage.py --ring`, `cage/stl/rim-ring.stl`). It's the whole rim, 175.5 x 129.5 x 8, about an hour to print, flat on its land. Press the real lid onto it. The lip must drop into the O-ring channel all the way round and through all four S-curves. All four holes must sit under the lid's at once, and the outer edge must be flush on all four sides. Correct `cage/lid-rim-spec.md` until it does, then set `ring_fit` True.

   `cage.py --stl` refuses the full base until `ring_fit` and L2 (`l2_screw_pos`, the lid bolt positions) are sourced. L1 left that gate when Clint's printed bolts (option c) were chosen. Also settle the EVM's part heights and J6 under it (`evm`, `evm_under`).
2. Then print a second test coupon. `cage.py` has no coupon mode, so nothing in the repo defines its shape yet. It should hold one card slot (tune `slot_clear` until a card slides with light friction), one lid bolt post (try one of the printed bolts in it) and one lid corner of the land and tongue. Fit the lid on that corner and check that the sealing lip presses the O-ring with the lid's walls down on the land. The squeeze isn't settled: it follows from whichever lip height is right (README). Add a 30 mm square of the base wall to leak-test.
3. Print the base in a light-coloured PETG (README, PETG in sun), with the floor on the bed (Yb up), not rim down. The 45-degree roofs over the groove and the backplane slot are drawn for that orientation. The floor is 3 mm, the long walls 4.25 mm and the short walls 4.0 mm, printed solid (roughly 9-10 perimeters at a 0.42 mm line width). Don't put inserts in the four corner posts: the lid goes on with Clint's 3D-printed bolts in their bores. With the iron, set the retention bar's two M3 heat-set inserts in the left wall's front face. Set the EVM clip's two down into the left keeper and the right lid-end block, at Xb 4.5 and 100.25, Yb 106.

   Leak-test the bare base: water in the base, or soapy water with the lid on and a little pressure through the vent hole. Coat the inside only if it leaks. Paint or clear-coat the outside against UV.
4. Fit the glands in the bottom wall's bosses. Five 13 mm holes take PG-7s #762, for the four sensor-port cables S1-S4 and the solar lead. Two 15.5 mm holes take PG-9s #761, for the flat wind and rain cables (right column). There's no spare. Fit the M12 vent, and the SMA bulkhead low in the right wall (enclosure 4: Yb 94.14, Zb 60.38).

   Then fit the backplane (its build sheet, section 6). Tilt its factory right edge into the right corner post's slot, lower it and slide it left into the left wall's groove. There are no screws, because the cards hold it, so fit them straight after. It comes off again only after every card is out.
5. Shelves, bottom to top: the pack on its tray (strap) first. Next the EVM, with its Bumpon feet peeled off, slid back on its ledges to the stop, clip at the front, leads with service loops. Then the cards.
6. Cables. A 6P plug (9.65 x 6.6 mm, 11.7 across its corners, 12.2 with the latch) passes no gland. The PG-7 bore is 7.9 and the PG-9's 10.5, even with the seal out. So every cable goes through its gland with no plug on its inside end. You crimp that plug afterwards, inside the box, with Clint's 6P crimp plugs and a 6P (RJ11/RJ12) crimp tool.

   Round port cables: from outside, slide the cap, the seal and the body's bore over the bare end. Pull the length through, crimp the plug and tighten the cap. Use the same pin order as the module end: 2 3.3 V, 3 data, 4 ground, 5 clock.

   The weather meters' flat cables come with their plugs fitted. Note which colour sits at which plug position (wind 2-5, rain 3-4). Cut the plug off outside the box and pass the cable in through the PG-9 with its seal out. Crimp a new plug in the same order. Once the cable's position is final, seal the gap with silicone or a split grommet. After that the cable comes out only if you cut the seal (and the plug).

   Check that the crimp plugs hold the meters' narrower flat cable with each conductor on its position. If they don't, use 6P4C plugs.

   Inside, leave a service loop in the space in front of the cards. Outside, leave a drip loop below each gland before you tie the cable to the pole. Each cable runs from its plug to the right column, down it, and left under the pack tray to its gland (cage/shelves-spec.md).
7. The coax: fit AD1 on the Wio-E5 mini's SMA, its arm toward the lid, and the 135110 plug on AD1. Bend the cable right in front of the cards and run it down the right column to the bulkhead low in the right wall. Clip it to the right corner post. The 6 in cable reaches. Clint checked it on 2026-11-17: it fits the low bulkhead with no tight bend. [TBD-MEASURE] Check that the straight plug on the bulkhead's inner end clears the EVM's lid-right corner (or use a right-angle plug).
8. Mount the box with hose clamps or straps through the two slots in each mounting flange (the short ends, in the floor plane). Put the lid on with its four printed bolts.

## 3. Cards, bottom to top: B4 POWER, B2 PORTS B + METERS, B1 PORTS A, B3 CORE (top)

**Labels (the slot key's colour code).** Each card gets a dot on its front edge. The same colour goes beside its slot on the base and beside its socket on the backplane: B1 blue, B2 green, B3 yellow, B4 red, so match the dots. The key plugs (BACKPLANE.md section 2) stop a wrong card at the socket mouth. If a card won't go the last few millimetres, it's in the wrong slot, so never force it.

Every card has its back rails snapped off and the edge filed flat first (step 1 of its build sheet). Each card slides in from the lid side along its left-wall slot and right-post slot. It goes in until its header pins enter the socket (4.96 mm), and the header insulator meets the socket 0.84 mm further in. On B1 and B2 the RJ11 jacks overhang the front edge, mouths toward the lid. Fit the retention bar (front left, two M3 screws) last.

To take a card out, take the bar off. Unplug that card's own plugs: the RJ11 cables on B1 and B2, the coax at AD1 on B3, and the SWD and USB-C leads if fitted. Then slide it out. No card needs another card out first. Nothing is soldered between a card and anything else (layout check L10).

## 4. Leads off the cards

| From | To | Length | What |
|---|---|---|---|
| PG1 lead - | U1 battery - (J5 GND) | 150 mm, trim to fit | pack - to charger battery - (J5 GND), 24 AWG stranded, black |
| RT1 1 | U1 thermistor (J7) | 150 mm, trim to fit | thermistor to EVM J7 |
| RT1 2 | U1 thermistor ground (J7 GND) | 150 mm, trim to fit | thermistor return to EVM J7 |
| PG1 lead + | backplane line 21 hole 6 | 100 mm, trim to fit | pack + (pigtail) to the junction, 24 AWG stranded, red with a black band |
| U1 battery + (J5 BATTERY) | backplane line 19 hole 6 | 100 mm, trim to fit | charger battery + (J5 BATTERY) to lines 19-20, 24 AWG stranded, red with a black band |
| U1 system out (J3 SYS) | backplane line 26 hole 6 | 100 mm, trim to fit | charger system output (J3 SYS) to line 26 (B4 pin 26, the regulator in), 24 AWG stranded, red with a black band |
| U1 system ground (J3 GND) | backplane line 12 hole 11 | 100 mm, trim to fit | charger system ground (J3 GND) to line 12 (the bus ground, SYS's return), 24 AWG stranded, black |
| R7 2 | U1 battery sense (J5 SNS_BATP) | 100 mm, trim to fit | charger battery sense (J5 SNS_BATP) from R7's free leg, 24 AWG stranded, white with a red band |
| EVM J8 (KK 4-pin housing, pins 1-3) | backplane charger pins | 150 mm | charger I2C: ground, clock, data |
| mux channel 0-3 (QT) | backplane QT lead pins | 150 mm (Adafruit #4209) | sensor ports S1-S4 |

Battery leads are 24 AWG stranded (red +, black -), about 8.4 mV drop per 0.1 m at 1 A (84.2 mohm/m). J5 BATTERY to line 19 is soldered at the backplane and screwed at J5. The pack + pigtail is soldered at line 21. The pack - lead runs straight from the pack to J5 GND (screwed) and doesn't touch the backplane. The charger sense lead from R7 is 24 AWG stranded too.

SYS (J3 SYS to line 26) and its return (J3 GND to line 12, black) are a same-length pair of 24 AWG stranded leads, run side by side. The 3.3 V regulator's load and the radio's transmit peaks return mainly on that ground lead. So they don't depend on the I2C lead's J8 pin 1. J8 pin 1 is tied to the same ground on the EVM and still carries a small parallel share. The battery current reaches B4 only on doubled header pins (19-20, 21-22, layout check L4). No lead goes to a card (L10).

Inside the box, leave 60-80 mm service loops on the jack cables and the solar lead (no spec sets that length yet). Outside, leave a drip loop below each gland.

## 5. Before the first power

- Charger jumpers as in section 1, the pack disconnected, JP17 out.
- Each card's own 'Before power' list, and the backplane's.
- 3.3 V supply to ground on the backplane: open (more than 1 kohm).
