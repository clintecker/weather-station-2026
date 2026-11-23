# Pod boxes: CAD brief (TH, BARO, UV)

This brief is for a CAD agent that will model and print the three sensor pod boxes. Units are millimetres.

Here's where the numbers come from:
- Every box dimension comes from `box/podbox.py` and `sources.py` as of 2026-11-18 (the UV crown: 2026-11-19; the window, the vents and the UV breather: 2026-11-23).
- The cap and arm mount details come from `shield/remix.py`.
- The pressure figures and the 1 g silica pack size don't come from those files. The 3.5 hPa/°C is plain gas-law physics. The BMP581's ±0.5 hPa is Bosch's figure.

The reference STLs are `box/stl/pod-{th,baro,uv}-{body,lid}.stl`. They're saved in print orientation, not in the frame below.

## What these boxes are

Each box holds one soldered Adafruit Perma-Proto Quarter board (43.18 × 50.8 × 1.6) that carries:
- the sensor breakout, on BARO only (BMP581). The TH and UV boards carry no sensor. The SHT45 sits outside on the shield stand, and the LTR390 sits in the UV crown's lid. Each one's 4-core lead lands on its board at J10, J12, J13 and J14.
- an ID EEPROM.
- a 6P RJ11 jack (SparkFun BOB-14021 with an 87180 jack). The jack's mouth faces down.

A cable comes in through a PG-7 cable gland. You crimp the plug onto it inside the box, after the cable goes through the gland.

| Box | Holds | Mounted | Openings |
|---|---|---|---|
| TH | the SHT45 board's port end; the SHT45 itself sits outside on the shield stand, on a 4-core lead | upright on the −x face of the remixed shield arm | 2 × PG-7 in the bottom wall (port cable and SHT45 lead) |
| BARO | BMP581 | upright on the +x face of the remixed shield arm | 1 × PG-7 and a Ø4 vent with a baffle, both in the bottom wall |
| UV | LTR390 (in the lid, on a 0.30 m lead) | a round crown, window up, on the remixed shield cap | 1 × PG-7, level, through the drum wall; a Ø2 breather across from it; a window at the top of the dome |

## Sealing (Clint, 2026-11-18)

- **TH: completely sealed.** It gets an opaque lid, with no window and no vent. The two glands are the only openings. The O-ring lid seals the rest.
- **BARO: sealed against water, but it must keep its vent.** An airtight box stops tracking outside pressure, because trapped air changes pressure with temperature. That's about 3.5 hPa per °C, far more than the BMP581's ±0.5 hPa. So keep the Ø4 vent and the baffle. A Gore VE70510 adhesive ePTFE vent (Ø10.2 × 0.34, 5.5 effective) goes on the vent's inside seat. It lets air through and keeps water out. It's required, not optional. The lid is opaque.
- **UV: the only box with a window.** The window is a Ø20 × 1 uncoated JGS1 fused quartz disc (a generic listing; Edmund Optics #22-694 is the fallback), set flush in the flat at the top of the dome and bedded in DOWSIL 3145 (neutral-cure silicone). It passes about 93 % of the LTR390's 280–430 nm band and doesn't age in sun. The rest of the lid is opaque. The lid seals on an O-ring round the body's spigot, not on a lid groove.
- **UV breathes (2026-11-23).** A Ø2 hole goes level through the drum wall, across from the gland, with the same Gore VE70510 vent stuck over it on a flat seat inside. The crown is the biggest box and has a dark dome over a window. Without a breather it pumps damp air in through the O-ring and the window bed as it heats and cools, and the window fogs from inside.
- **Desiccant:** you don't need any. A small pocket for a 1 g silica pack is welcome in TH and UV, if it fits outside the cavity minimums below.

## Frame

All coordinates use the **pod board frame**:
- **Origin:** the Perma-Proto's lower-left corner, on its component face. The board fills x 0..43.18, y 0..50.8, z −1.6..0. z = 0 is the component face, and the copper side faces −z.
- **x:** to the right along the board.
- **y:** up along the board. The jack's mouth faces −y.
- **z:** out of the component face, toward the lid.
- **Back face:** the box's back (z = −9.5) is the **mount face**. The lid sits at the top (+z).
- **Orientation as mounted:**
  - TH and BARO: world up = +y. The glands point at the ground and the lid faces outward.
  - UV: world up = +z. The lid and window face the sky.

## Common construction (all three)

| Feature | Value |
|---|---|
| Wall, all round, back included | 3.0 |
| Inside corner radius (edges along z) | 2.0 |
| Outside corner radius | 5.0 (2.0 + wall) |
| Lid plate | 3.0 thick, same outline as the body including the lugs; lands flat on the 3.0 rim (hard stop) |
| Corner lugs | 4 cylinders Ø8.0, full body height, centred 1.0 beyond each outer corner in x and in y (positions per box below) |
| Lid fixing | 4 × M3 × 8 pan head through Ø3.4 lid holes into M3 heat-set inserts in the lugs; bore Ø4.0 × 6.7 deep from the rim, outside the seal |
| Seal | Ø1.5 O-ring cord in a groove in the **lid's** underside: 2.03 wide × 1.12 deep (25 % squeeze), centreline over the rim's centreline (inside outline grown 1.5, corner radius 3.5) |
| Board standoffs | 2 posts Ø5.5 at (3.81, 25.4) and (39.37, 25.4), from the back wall's inner face (z −6.5) up to z −1.6, where the board's copper side rests; Ø2.5 pilot, blind (stops 1.0 short of the outside back face), for M3 × 8 thread-forming screws through the board's Ø3.2 holes |
| Gland holes | Ø13.0 (PG-7: the thread is 12.5 nominal per DIN 40430; Adafruit lists the #762's screw end as 11.5). The 13.0 hole clears either. The gland nut is 16.6 across its corners, sits inside, and must keep 1.0 clear of every wall and of the lid; that rule sets the box depth |
| Clearance | at least 2.0 from every part, cable plug and bend, the board and its copper side, to every wall and the lid |
| Material and print | PETG, light colour. Body prints back face down, lid prints groove face down. No supports: holes whose axis lies flat in print (the TH/BARO bottom-wall glands and the vent) are teardrops pointing +z, capped at 1.1 × r |

## Per box (board frame)

### TH (sealed)
- **Inside cavity** (minimum, don't shrink it): x −2.00..45.18, y −38.42..52.80, z −6.50..18.14 (47.18 × 91.22 × 24.64).
- **Outside:** walls x −5.00..48.18, y −41.42..55.80, z −9.50..18.14. The lid adds z 18.14..21.14. With the lugs the box is 63.18 × 107.22 × 30.64.
- **Lugs** (centres): (−6.00, −42.42), (−6.00, 56.80), (49.18, −42.42), (49.18, 56.80).
- **Port gland:** Ø13.0 through the bottom wall (y −41.42..−38.42) at x 10.16, z 8.84, axis −y. It's coaxial with the RJ11 jack and plug: **fixed**.
- **Lead gland:** Ø13.0 through the bottom wall at x 31.82, z 5.82, axis −y. It carries the SHT45's round 4-core lead (OD 3.0 to 4.3).
- **Mount face:** z −9.50. M3 heat-set inserts go in all four lugs from the back, blind: bore Ø4.0 × 6.7 deep, z −9.5 to −2.8.

### BARO (water-sealed, vented)
- **Inside cavity** (minimum): x −2.00..50.26, y −38.42..56.61, z −6.50..18.14 (52.26 × 95.03 × 24.64).
- **Outside:** walls x −5.00..53.26, y −41.42..59.61, z −9.50..18.14, plus the lid. With the lugs the box is 68.26 × 111.03 × 30.64.
- **Lugs:** (−6.00, −42.42), (−6.00, 60.61), (54.26, −42.42), (54.26, 60.61).
- **Port gland:** as TH, at x 10.16, z 8.84, axis −y: **fixed**.
- **Vent:** Ø4.0 through the bottom wall at x 34.36, z 0.70, axis −y.
- **ePTFE seat:** a Ø12.4 × 0.4 recess in the bottom wall's inner face, concentric with the vent, for the Gore VE70510 (Ø10.2 × 0.34). Gore wants the flat area at least the vent's diameter plus 1.5, so 11.7; 12.4 clears it.
- **Baffle:** a fin 1.6 thick at x 26.36..42.36, y −35.92..−34.32 (2.5 above the bottom wall's inner face). It stands from the back wall at z −6.5 up to z 8.7. It overhangs the vent hole by 6.0 on its three open sides, so there's no straight line from outside to the BMP581. Keep at least 2.5 of free gap round it so air can move.
- **Mount face:** as TH, inserts in all four lugs.

### UV (the crown)
The UV pod isn't a box: it's a round crown, a drum with a dome lid that twists on. Everything is about its axis at
(10.16, 13.375), which runs through the port plug's axis, so the gland points straight out of the drum.
- **Drum:** outside Ø117.6 (r 58.8) from the floor at z −9.50 up to the ledge at z 20.84. Inside bore r 54.0 from
  z −6.50 (a 3.0 floor).
- **Spigot:** r 56.4 outside, r 53.6 inside (2.8 wall: it steps 0.4 in from the drum's bore on a 45° chamfer),
  from the ledge up to the joint at z 30.84; 1.5 is left behind the bayonet's channels and slots. The lid's skirt slides over it
  with 0.2 clearance, flush with the drum outside.
- **O-ring:** a radial groove round the spigot at z 23.84, 0.93 deep × 2.03 wide, for the 1.5 cord (351 mm of it; or a stock metric 110 × 1.5 O-ring, NBR 70; not 1.78 / AS568, which squeezes 36 %).
  The lid's skirt squeezes it about 25 %. It sits below the bayonet, so no slot crosses it.
- **Bayonet:** 3 lugs inside the lid's skirt (8 wide, 2.4 tall, 1.0 deep, centred 3.5 below the joint). The
  spigot has an entry slot down from its top at 90°, 210° and 330° (box frame, from +x) and a channel round from
  each. The lid locks 25° clockwise seen from above; the channel's end is the stop. No slot is over the gland (270°).
  A detent in each channel (a Ø1.4 post on the channel floor, just behind the locked lug) catches the lug by 0.2, so
  the lid clicks into the locked end and stays there.
- **Dome lid:** a quarter-ellipse dome, 28 rise from the joint, 3.0 thick, apex z 58.84, cut flat at z 58.24 for
  the window. The overall crown is 67.7 tall from the floor.
- **Port gland:** Ø13.0, level, through the drum wall at (10.16, y, 8.84), axis −y. Inside: a flat land (the nut's
  seat) at y −38.42. Outside: a Ø22 flat spot face. Both **fixed**.
- **Breather:** Ø2.0, level, through the drum wall at 90° (axis +y, straight across from the gland), at z 7.17 (half
  way from the floor's inner face to the ledge). Inside, a flat seat Ø12.4 cut into the bore, its floor 0.4 beyond the
  bore's radius (r 54.4), for the Gore VE70510. 4.4 of drum wall stays behind it.
- **Window**, on the axis (**fixed**):
  - a Ø20.3 × 1.0 deep recess in the flat at the top of the dome. The disc sits flush, so no water ponds on it.
  - a Ø17.0 aperture (a 1.5 ledge all round) at the top of a short tube down toward the LTR390.
  - the disc sits in a bed of DOWSIL 3145 RTV, a neutral-cure silicone. Acetoxy (vinegar-smelling) silicone gives off acid while it cures, inside a closed crown with the LTR390 in it.
- **LTR390:** in the lid, chip up, its board's top at z 50.34, on two bosses under the dome at (0.00, 7.03) and
  (20.32, 19.73), two of its corner holes. 2 × M2.5 × 6 thread-forming into Ø2.1 pilots, which stop 0.5 past the screw's
  tip (at least 1.2 of plastic to the dome's outside and to the window recess). The aperture tube's bottom is 0.5
  above the tops of the breakout's two factory STEMMA QT sockets (they reach past the tube's outside radius). Its 0.30 m lead runs to the board below.
- **Board:** on the two standoffs from the floor under the Perma-Proto's mounting holes, (3.81, 25.4) and
  (39.37, 25.4), M3 × 8 thread-forming, as in TH and BARO.
- **Mount face:** z −9.50, the floor. Four blind floor bosses take M3 inserts from below: bore Ø4.0 × 6.7, at
  r 31 about the axis, at (−6.27, 39.66), (−20.05, 20.35), (−16.13, −3.05) and (26.59, −12.91), clear of the
  board. No corner lugs and no lid screws.

## Mounting interfaces (fixed: the remixed shield parts are drilled to match)

- **TH and BARO:**
  - The back face lies flat on a face of the remixed L-bracket arm: TH on the arm's −x face, BARO on its +x face, glands down.
  - 4 × M3 × 10 pan head go from the arm side through the arm face (5.0 plastic) into the four lug inserts.
  - The insert pattern is the four lug centres above.
- **UV:**
  - The floor sits on the remixed top cap, the crown's axis on the shield's axis, turned so the gland points +x.
    The cap's flat top is a disc of r 38.03; all four floor bosses (r 31) are on it.
  - The cap carries a skirt under the crown: a shell 2.4 thick that starts just outside and above the top louver
    plate and flares out in one S-curve to the crown's drum (r 58.8), with a ring at the flat top's level. Nothing of
    it hangs in front of the louvers.
  - 4 × M3 × 10 go up from inside the cap (with the cap off the stack), through its counterbores and the 5.0 of
    plastic under the flat top, into the floor-boss inserts.
  - The gland comes level out of the drum. The cable runs out to a drip loop, then down outside the louvers.
- **If you move a lug, a boss or a gland,** the cable runs won't match any more. Nor will the remixed arm and cap (`shield/remix.py`). Don't move them unless you regenerate the remix too.

## What you may change, and what you must not

- **Free:** outside cosmetics (chamfers, ribs, labels such as "TH", "BARO", "UV" embossed on the lid), lug fillets, and a desiccant pocket.
- **Free:** thicker walls outward only, as long as the mount faces and lug centres stay put.
- **Fixed:**
  - the inside cavity (minimum), the standoff positions and heights.
  - the gland positions and axes, the vent, ePTFE seat and baffle, the UV breather and its seat.
  - the window position and recess.
  - the mount face plane (z −9.5), the lug centres and floor-boss centres.
  - the seal groove geometry.

## Values still to measure (TBD; regenerate if they change)

| Value | Today | Measure |
|---|---|---|
| M3 heat-set insert | 5.7 long × 4.6 knurl, so bore Ø4.0 × 6.7 | calipers on the inserts on hand |
| O-ring cord | Ø1.5 | the cord on hand |
| Board screw pilot | Ø2.5 in PETG | a test print |
| Window disc | Ø20 × 1.0 JGS1 fused quartz (generic; Edmund #22-694 fallback). Generic discs vary more: the recess follows the measured disc | the disc as bought, calipers |
| ePTFE vent | Gore VE70510, Ø10.2 × 0.34 | the vent as bought |
| PG-7 nut | 16.6 across corners | the glands on hand |

## Checks before printing

1. The body and lid are each one closed solid.
2. The body and lid, closed, don't intersect.
3. The board (x 0..43.18, y 0..50.8, z −1.6..0) sits on the standoff tops, and every wall is at least 2.0 from it.
4. Every gland nut (16.6 across corners, behind its hole) is at least 1.0 clear of every wall and the lid.
5. BARO: no straight line from outside through the vent reaches the BMP581 board without hitting the baffle.
   Both ePTFE seats (BARO's vent, the UV breather) are flat across at least Ø11.7 and at least 0.34 deep.
6. UV: the floor is flat (nothing stands proud of it), and the lid twists on and off by hand with the cord in its groove.
7. Each insert bore stays blind: none of them breaks into the sealed cavity.
