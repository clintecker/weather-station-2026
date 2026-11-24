# Assembly: charger set-up, the printed base, shelves, cards, cables

`layout/drawings.py` writes this sheet. Read it with `drawings/cage-side.svg`, `build/B1..B4.md` and `build/BACKPLANE.md`.

## 1. Charger (BQ25798EVM) before any power: jumper changes (TI SLUUCB5; issue #34)

The EVM ships set for two cells. Do these in order, with nothing connected:

1. **JP24 off, JP22 on** (PROG: one cell, 1.5 MHz). JP22 is the only PROG jumper fitted.
2. **Battery sense wire first, then JP9 off.** Screw the charger battery sense lead into J5 SNS_BATP, J5's middle position (J5 is an ED120/3DS screw block: PGND, BATP, BATTERY from the back edge, SLUUCB5E Figure 4-1). It comes from R7 on the backplane (its free leg at line 24, hole 7). Only then remove JP9, so BATP never floats.
3. **JP18 off, thermistor on J7.** Fit the Adafruit #372 10 kohm NTC (B 3950) to J7 and tape it to the pack. The EVM's TS divider is set for a 103AT (B 3435), so with this NTC the chip's fixed cold stop sits at about 4 C and its fixed hot stop at about 55 C. The firmware moves the warm point to about 42 C and stops charging there (`App/power_config.h`). Read the TS percentage over I2C at room temperature. Check that it sits in the normal band before you charge.
4. **JP12, JP17 and JP30 stay in.** JP30 powers the EVM's 3.3 V PULLUP rail. That rail holds the I2C pull-ups R39 (SCL) and R40 (SDA), 10 kohm each. R41 and R42 on the same rail pull up /INT and /CE. Only the SCL/SDA pair counts toward the bus total (1.40 kohm, schematic check 3).
5. There's one status LED, D13 (the STAT LED). It sits on JP32, which is fitted as shipped, and draws about 0.6-0.7 mA when lit. Leave it, or pull JP32 to remove it.
6. USB in is J6, micro-B (JP7 on VIN1). Use a USB-C to micro-B cable from the 2 A adapter (PS1). PS1 is for the bench only: set-up, first power and charger checks with the lid off. It has no gland, and the station runs on the solar panel once the lid is on.
7. **First power without the pack and with JP17 out** (charge disabled). The firmware does the I2C part (`firmware/stage0-node/App/charger.c`, built with `WS_POWER_PROFILE=3 WS_I2C_MUX=1`). At every start it writes the charge voltage (4.2 V, REG0x01-0x02) and the charge current (ICHG about 0.9 A; spec charger set-up, electrical C1/M1/M2, and issue #34), reads both back and checks that REG0x0A says one cell. It writes them again after any chip reset, because ICHG goes back to its 1 A default on a power cycle or a chip watchdog timeout. It also sets the input over-voltage limit to 12 V (the chip powers up at 7 V, which the P110 can pass on a cold morning), the panel's MPPT at 0.81 of its open-circuit voltage, and the warm stop above. It keeps charge off until a fresh TS reading is neither cold, warm nor hot. The JP22 note says 2 A, and the datasheet default is 1 A. The firmware runs on the cards, so do this check once they're in (Session 8): USB in J6, no pack, JP17 out, then type `CHARGER` on the TX console. Look for `cells=1`, `vreg_mv=4200`, `ichg_ma=900`, `vac_ovp=2`, `voc_pct=4`, `ts=NORMAL` and `hold=none`, and write down `ts_pct` and `pack_dc` (the pack temperature in 0.1 C). Then refit JP17 and connect the pack, last.

## 2. Print the base (`cage/cage.py`)

1. Print the rim test ring first (`cage.py --ring`, `cage/stl/rim-ring.stl`). It's the whole rim, 175.5 x 129.5 x 8, about an hour to print, flat on its land. Press the real lid onto it. The lip must drop into the O-ring channel all the way round and through all four S-curves. All four holes must sit under the lid's at once, and the outer edge must be flush on all four sides. Correct `cage/lid-rim-spec.md` until it does, then set `ring_fit` True.

   `cage.py --stl` refuses the full base until `ring_fit` and L2 (`l2_screw_pos`, the lid bolt positions) are sourced. L1 left that gate when Clint's printed bolts (option c) were chosen. Also settle the EVM's part heights and J6 under it (`evm`, `evm_under`).
2. Then print the test coupon (`cage.py --coupon`, `cage/stl/coupon.stl`, not gated). It's the base's top-left corner cut out of the model: Xb -4 to 26, Zb 130 up, Yb 45 to the lip, about 126 minutes, printed Yb up with the cut face on the bed. It holds B3's slot in the left wall (tune `slot_clear` until a card slides in with light friction), the top-left lid bolt bore (try one of the printed bolts in it) and the land and sealing lip round that corner. Fit the lid on that corner and check that the sealing lip presses the O-ring with the lid's walls down on the land. The squeeze isn't settled: it follows from whichever lip height is right (README). Its left and top walls are more than 30 mm square, so leak-test them too.
3. Print the base in a light-coloured PETG (README, PETG in sun), with the floor on the bed (Yb up), not rim down. The 45-degree roofs over the groove and the backplane slot are drawn for that orientation. The floor is 3 mm, the long walls 4.25 mm and the short walls 4.0 mm, printed solid (roughly 9-10 perimeters at a 0.42 mm line width). Don't put inserts in the four corner posts: the lid goes on with Clint's 3D-printed bolts in their bores. With the iron, set the retention bar's two M3 heat-set inserts in the left wall's front face. Set the EVM clips' two down into the left keeper and the right lid-end block, at Xb 4.5 and 100.25, Yb 106. Print the two clips (`cage.py --clip`, `cage/stl/evm-clips.stl`, not gated) flat on their top faces.

   Leak-test the bare base: water in the base, or soapy water with the lid on and a little pressure through the vent hole. Coat the inside only if it leaks. Paint or clear-coat the outside against UV.
4. Fit the glands in the bottom wall's bosses. Five 13 mm holes take PG-7s #762, for the four sensor-port cables S1-S4 and the solar lead. Two 15.5 mm holes take PG-9s #761, for the flat wind and rain cables (right column). There's no spare. Which gland takes which cable (`cage.GLAND_USE`, Xb, Yb): S4 SPARE (26, 25), S3 BARO (50, 25), S2 UV (74, 25), WIND (98, 25), SOLAR (26, 60), S1 TH (50, 60), RAIN (98, 60). The port cables in use get the shortest runs from the right column's foot (back and left under the tray), the spare S4 the longest, and the solar lead the left front one, nearest J2. S4 has no pod yet, and an empty PG-7 doesn't seal, so fit its gland with a 4 x 20 mm stainless dowel pin (ISO 8734, A1) in its seal, cap tightened (`cage.GLAND_BLANK`). Take the pin out when a pod goes on S4. Fit the M12 vent, and the SMA bulkhead low in the right wall (enclosure 4: Yb 94.14, Zb 60.38). On the bulkhead's outside thread, out from the wall: the sealing washer, the bonding lug (Panduit PV14-14R-L, 16-14 AWG, 1/4 in stud), the lock washer, the nut.

   Then fit the backplane (its build sheet, section 6). Tilt its factory right edge into the right corner post's slot, lower it and slide it left into the left wall's groove. There are no screws, because the cards hold it, so fit them straight after. It comes off again only after every card is out.
5. Shelves, bottom to top: the pack on its tray (strap) first. Next the EVM, with its Bumpon feet peeled off, slid back on its ledges to the stop. Then the two front clips, one each side of J8: each clip's lip over the board's front edge, an M3 x 8 socket cap through it into its insert. Leads with service loops. Then the cards.
6. Cables. A 6P plug (9.65 x 6.6 mm, 11.7 across its corners, 12.2 with the latch) passes no gland. The PG-7 bore is 7.9 and the PG-9's 10.5, even with the seal out. So every cable goes through its gland with no plug on its inside end. You crimp that plug afterwards, inside the box, with Clint's 6P crimp plugs and a 6P (RJ11/RJ12) crimp tool.

   Round port cables: from outside, slide the cap, the seal and the body's bore over the bare end. Pull the length through, crimp the plug and tighten the cap. Use the same pin order as the module end: 2 3.3 V, 3 data, 4 ground, 5 clock.

   The weather meters' flat cables come with their plugs fitted. Note which colour sits at which plug position (wind 2-5, rain 3-4). Cut the plug off outside the box and pass the cable in through the PG-9 with its seal out. Crimp a new plug in the same order. Once the cable's position is final, seal the gap with silicone or a split grommet. After that the cable comes out only if you cut the seal (and the plug).

   Check that the crimp plugs hold the meters' narrower flat cable with each conductor on its position. If they don't, use 6P4C plugs.

   Inside, leave a service loop in the space in front of the cards. Outside, leave a drip loop below each gland before you tie the cable to the pole. Each cable runs from its plug to the right column, down it, and left under the pack tray to its gland (cage/shelves-spec.md).
7. The coax: fit AD1 on the Wio-E5 mini's SMA, its arm toward the lid, and the 135110 plug on AD1. Bend the cable right in front of the cards and run it down the right column to the bulkhead low in the right wall. Clip it to the right corner post. The 6 in cable reaches. Clint checked it on 2026-11-17: it fits the low bulkhead with no tight bend. The straight plug on the bulkhead's inner end passes about 6.4 mm over the EVM's lid-right corner, where SLUUCB5E Figure 4-1 has only silk (JP9, the nearest part, is about 4 mm off; `cage.py` checks it).
8. Mount the box with hose clamps or straps through the two slots in each mounting flange (the short ends, in the floor plane). The pole is about 1 in (25.4 mm): use stainless worm-drive clamps, SAE size 20 (about 19-44 mm), band 12.7 mm wide or less. Each one closes to about 34 mm round the pole and the flange. Put the lid on with its four printed bolts.

   The antenna, AE1: Taoglas TI.96.A113 (915 MHz dipole, IP67, hinged SMA(M), screwed straight onto the bulkhead outside, folded to point up). Screw it onto the bulkhead jack finger-tight plus a quarter turn, fold it at its hinge so it stands vertical, tip up, then wrap the coupling nut, the hinge and the thread in 3M Scotch 23 self-amalgamating tape, with 3M Scotch Super 33+ over it (the datasheet gives no UV rating).

   The bond to the pole (required: the pole is metal and earthed). 14 AWG stranded copper, green THWN-2, from the lug on the bulkhead to a SatelliteSale SS-GSG9-1 grounding strap on the pole (1/2-2 in pipe, so it fits the 1 in pole; the SS-GSG12-1 for a pole over 2 in), on bare metal with Ideal Noalox under it. Short and straight, no coil. Check it at 1 ohm or less from the bulkhead's body to the pole.

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
| PG1 lead + | F5 lead from PG1 | PG1's red lead cut to 30 mm, then F5's own holder lead | PG1's red lead spliced to the pack fuse F5's holder lead, within 30 mm of PG1's socket |
| F5 lead + | backplane line 21 hole 6 | 100 mm, trim to fit | pack + (after the fuse F5) to the junction, 24 AWG stranded, red with a black band |
| U1 battery + (J5 BATTERY) | backplane line 19 hole 6 | 100 mm, trim to fit | charger battery + (J5 BATTERY) to lines 19-20, 24 AWG stranded, red with a black band |
| U1 system out (J3 SYS) | backplane line 26 hole 6 | 100 mm, trim to fit | charger system output (J3 SYS) to line 26 (B4 pin 26, the regulator in), 24 AWG stranded, red with a black band |
| U1 system ground (J3 GND) | backplane line 12 hole 11 | 100 mm, trim to fit | charger system ground (J3 GND) to line 12 (the bus ground, SYS's return), 24 AWG stranded, black |
| R7 2 | U1 battery sense (J5 SNS_BATP) | 100 mm, trim to fit | charger battery sense (J5 SNS_BATP) from R7's free leg, 24 AWG stranded, white with a red band |
| EVM J8 (KK 4-pin housing, pins 1-3) | XJ1 on the backplane (three 1-way 0.1 in housings, flagged GND, SCL, SDA) | 150 mm | charger I2C: ground, clock, data |
| solar panel cable (Voltaic P110), cut at its gland (26, 60) | EVM J2 VIN2 (red), J2 GND (black) | 260 mm | 22 AWG stranded red/black pair, twisted, soldered and heat-shrunk to the panel cable's cores just above the gland nut; into J2 in twin ferrules with D6's leads (below). Route: forward under the EVM, up in front of the left keeper between its clip and J8, back over the clip along the left wall to J2 |

**The solar TVS D6** sits in J2 itself: Littelfuse P4KE15A, 15 V 400 W unidirectional TVS, DO-41 (solar input clamp, across EVM J2: cathode to VIN2, anode to GND, each lead in a twin ferrule with the solar lead's core). Crimp each solar core together with one D6 lead in a Phoenix Contact AI-TWIN 2 x 0.75-8 GY twin ferrule (3200807): the red core with the banded (cathode) lead, the black core with the other. The body lies along J2's wire side. VIN2 is J2's back position, GND its lid-side one. Its 12.8 V stand-off is above the panel's cold 8.7 V and the charger's 12 V input cut-off, so it never conducts in normal use; it clamps a surge on the panel lead to about 21 V, under the BQ25798's 30 V limit (README, Lightning and surge).

Battery leads are 24 AWG stranded (red +, black -), about 8.4 mV drop per 0.1 m at 1 A (84.2 mohm/m). J5 BATTERY to line 19 is soldered at the backplane and screwed at J5. The pack + lead is soldered at line 21. The pack - lead runs straight from the pack to J5 GND (screwed) and doesn't touch the backplane. The charger sense lead from R7 is 24 AWG stranded too.

**The pack fuse F5** sits in the pack + lead, as close to the pack as the leads allow: Littelfuse 021701.6HXP (5 x 20 mm, 1.6 A fast-acting, glass) in a Schurter 8601.2000 in-line holder (wire leads), spliced into PG1's red lead next to the pack. Cut PG1's red lead 30 mm from its socket, splice and heat-shrink it to one of the holder's leads, and splice the holder's other lead to the backplane's pack + lead (line 21, hole 6). The holder lies on the pack tray beside the pack, under the strap. A short anywhere past it (the lead, the junction on the backplane, B4, the EVM's battery path) now opens the fuse instead of leaning on the pack's own protection board alone. The path carries at most the 0.9 A charge, so the 1.6 A fuse runs at 56 % of its rating. A blown fuse looks like a missing pack: the station keeps running only while USB or the panel feeds SYS. The README's parts list has two spare fuses.

SYS (J3 SYS to line 26) and its return (J3 GND to line 12, black) are a same-length pair of 24 AWG stranded leads, run side by side. The 3.3 V regulator's load and the radio's transmit peaks return mainly on that ground lead. So they don't depend on the I2C lead's J8 pin 1. J8 pin 1 is tied to the same ground on the EVM and still carries a small parallel share. The battery current reaches B4 only on doubled header pins (19-20, 21-22, layout check L4). No lead goes to a card (L10).

The solar pair is 22 AWG: the panel gives 1.67 A at its maximum power point and about 1.9 A into a short (solar_p110), and the pair's two legs drop about 45 mV at 1.67 A. Its length is `cage.solar_route()` (183 mm, checked clear of the cards, the pack, the EVM and the clips) plus a 70 mm service loop.

Inside the box, leave 60-80 mm service loops on the jack cables and the solar lead (no spec sets that length yet). Outside, leave a drip loop below each gland.

## 5. Before the first power

- Charger jumpers as in section 1, the pack disconnected, JP17 out.
- Each card's own 'Before power' list, and the backplane's.
- 3.3 V supply to ground on the backplane: open (more than 1 kohm).
