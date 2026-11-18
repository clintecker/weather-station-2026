# Pod boxes: CAD brief (TH, BARO, UV)

This brief is for a CAD agent that will model and print the three sensor pod boxes. Every number here comes
from `box/podbox.py` and `sources.py` as of 2026-11-18. The reference STLs are `box/stl/pod-{th,baro,uv}-{body,lid}.stl`;
they are saved in print orientation, not in the frame below. Units are millimetres.

## What these boxes are

Each box holds one soldered Adafruit Perma-Proto Quarter board (43.18 × 50.8 × 1.6) carrying:
- the sensor breakout,
- an ID EEPROM,
- a 6P RJ11 jack (SparkFun BOB-14021 with an 87180 jack), whose mouth faces down.

A cable comes in through a PG-7 cable gland and is crimped onto a plug inside, after it has passed the gland.

| Box | Holds | Mounted | Openings |
|---|---|---|---|
| TH | the SHT45 board's port end; the SHT45 itself sits outside on the shield stand, on a 4-core lead | upright on the −x face of the remixed shield arm | 2 × PG-7 in the bottom wall (port cable and SHT45 lead) |
| BARO | BMP581 | upright on the +x face of the remixed shield arm | 1 × PG-7 and a Ø4 vent with a baffle, both in the bottom wall |
| UV | LTR390 | lying flat, window up, on the remixed shield cap | 1 × PG-7 through the floor; a window in the lid |

## Sealing (Clint, 2026-11-18)

- **TH: completely sealed.** It needs an opaque lid, no window and no vent. The only openings are the two glands; the O-ring lid seals the rest.
- **BARO: sealed against water, but it must keep its vent.** A box sealed airtight stops tracking outside pressure. Trapped air changes pressure with temperature, about 3.5 hPa per °C, which is far more than the BMP581's ±0.5 hPa. Keep the Ø4 vent, put the adhesive ePTFE membrane on its inside seat (it passes air and blocks water), and keep the baffle. The lid is opaque.
- **UV: the only box with a window.** The window is a 20 × 1.5 PTFE diffuser disc (UV-grade acrylic or quartz is the alternative), set flush in the lid. The rest of the lid is opaque.
- **Desiccant:** none is required. A small pocket for a 1 g silica pack is welcome in TH and UV if it fits outside the cavity minimums below.

## Frame

All coordinates use the **pod board frame**:
- **Origin:** the Perma-Proto's lower-left corner, on its component face. The board occupies x 0..43.18, y 0..50.8, z −1.6..0. z = 0 is the component face; the copper side faces −z.
- **x:** to the right along the board.
- **y:** up along the board. The jack's mouth faces −y.
- **z:** out of the component face, toward the lid.
- **Back face:** the box's back (z = −9.5) is the **mount face**. The lid sits at the top (+z).
- **Orientation as mounted:**
  - TH and BARO: world up = +y, so the glands point at the ground and the lid faces outward.
  - UV: world up = +z, so the lid and window face the sky.

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
| Gland holes | Ø13.0 (PG-7, 11.5 thread). The gland nut is 16.6 across its corners, sits inside, and must keep 1.0 clear of every wall and of the lid; that rule sets the box depth |
| Clearance | at least 2.0 from every part, cable plug and bend, the board and its copper side, to every wall and the lid |
| Material and print | PETG, light colour. Body prints back face down, lid prints groove face down. No supports: holes whose axis lies flat in print (the TH/BARO bottom-wall glands and the vent) are teardrops pointing +z, capped at 1.1 × r |

## Per box (board frame)

### TH (sealed)
- **Inside cavity** (minimum, do not shrink): x −2.00..45.18, y −38.42..52.80, z −6.50..18.14 (47.18 × 91.22 × 24.64).
- **Outside:** walls x −5.00..48.18, y −41.42..55.80, z −9.50..18.14. The lid adds z 18.14..21.14. With the lugs the box is 63.18 × 107.22 × 30.64.
- **Lugs** (centres): (−6.00, −42.42), (−6.00, 56.80), (49.18, −42.42), (49.18, 56.80).
- **Port gland:** Ø13.0 through the bottom wall (y −41.42..−38.42) at x 10.16, z 8.84, axis −y. It is coaxial with the RJ11 jack and plug: **fixed**.
- **Lead gland:** Ø13.0 through the bottom wall at x 31.82, z 5.82, axis −y. It carries the SHT45's round 4-core lead (OD 3.0–4.3).
- **Mount face:** z −9.50. M3 heat-set inserts in all four lugs from the back, blind: bore Ø4.0 × 6.7 deep, z −9.5 to −2.8.

### BARO (water-sealed, vented)
- **Inside cavity** (minimum): x −2.00..50.26, y −38.42..56.61, z −6.50..18.14 (52.26 × 95.03 × 24.64).
- **Outside:** walls x −5.00..53.26, y −41.42..59.61, z −9.50..18.14, plus the lid. With the lugs the box is 68.26 × 111.03 × 30.64.
- **Lugs:** (−6.00, −42.42), (−6.00, 60.61), (54.26, −42.42), (54.26, 60.61).
- **Port gland:** as TH, at x 10.16, z 8.84, axis −y: **fixed**.
- **Vent:** Ø4.0 through the bottom wall at x 34.36, z 0.70, axis −y.
- **ePTFE seat:** a Ø12.4 × 0.4 recess in the bottom wall's inner face, concentric with the vent, for a Ø12 adhesive membrane.
- **Baffle:** a fin 1.6 thick at x 26.36..42.36, y −35.92..−34.32 (2.5 above the bottom wall's inner face), standing from the back wall z −6.5 up to z 8.7. It overhangs the vent hole by 6.0 on its three open sides, so there is no straight line from outside to the BMP581. Keep at least 2.5 of free gap round it so air moves.
- **Mount face:** as TH, inserts in all four lugs.

### UV (window)
- **Inside cavity** (minimum): x −2.00..47.72, y −43.06..56.87, z −6.50..17.60 (49.72 × 99.93 × 24.10).
- **Outside:** walls x −5.00..50.72, y −46.06..59.87, z −9.50..17.60. The lid adds z 17.60..20.60. With the lugs the box is 65.72 × 115.93 × 30.10.
- **Lugs:** (−6.00, −47.06), (−6.00, 60.87), (51.72, −47.06), (51.72, 60.87).
- **Floor gland:** Ø13.0 through the back/floor at (10.16, −33.76), axis −z. The cable rises through it, bends over (10 mm allowance) and runs level into the jack: **fixed**.
- **Window**, in the lid at (33.02, 45.72), centred over the LTR390's sensor chip (**fixed**):
  - a Ø20.3 × 1.5 deep recess in the lid's top face, so the disc sits flush and no water ponds on it;
  - a Ø17.0 aperture through the lid (a 1.5 ledge all round);
  - the disc is bedded in neutral-cure silicone.
- **Mount face:** z −9.50, the floor.
  - **Lug inserts:** only the two far-end lugs, (−6.00, 60.87) and (51.72, 60.87), take mount inserts. The gland-end lugs keep only their lid inserts.
  - **Floor bosses:** two blind bosses inside the box, Ø8.0 at (4.00, −20.46) and (41.72, −20.46), from the floor up to z −1.8. Each takes an M3 insert from outside: bore Ø4.0 × 6.7, leaving 1.0 of plastic over the bore.
  - **Keep-out:** a Ø18.0 circle round the floor gland at (10.16, −33.76) on the mount face. The cap must stay clear of it; the gland hangs past the cap's edge.

## Mounting interfaces (fixed: the remixed shield parts are drilled to match)

- **TH and BARO:**
  - The back face lies flat on a face of the remixed L-bracket arm: TH on the arm's −x face, BARO on its +x face, glands down.
  - 4 × M3 × 10 pan head go from the arm side through the arm face (5.0 plastic) into the four lug inserts.
  - The insert pattern is the four lug centres above.
- **UV:**
  - The floor sits on the remixed top cap. The cap's flat top is a disc of r 38.03; a fused saddle (x 25–75, y ±26, 5 thick, three ribs) carries the floor bosses.
  - 2 × M3 × 10 go down through the cap's counterbores into the far-end lug inserts.
  - 2 × M3 × 10 go up through the saddle into the floor-boss inserts.
  - The gland end overhangs the cap's edge; the cable runs down outside the louvers with a drip loop below the gland.
- **If you move a lug, a boss or a gland,** the remixed arm and cap (`shield/remix.py`) and the cable runs no longer match. Do not move them unless the remix is regenerated too.

## What you may change, and what you must not

- **Free:** outside cosmetics (chamfers, ribs, labels such as "TH", "BARO", "UV" embossed on the lid), lug fillets, and a desiccant pocket.
- **Free:** thicker walls outward only, as long as the mount faces and lug centres stay put.
- **Fixed:** the inside cavity (minimum), the standoff positions and heights, the gland positions and axes, the vent, ePTFE seat and baffle, the window position and recess, the mount face plane (z −9.5), the lug centres and floor-boss centres, and the seal groove geometry.

## Values still to measure (TBD; regenerate if they change)

| Value | Today | Measure |
|---|---|---|
| M3 heat-set insert | 5.7 long × 4.6 knurl, so bore Ø4.0 × 6.7 | calipers on the inserts on hand |
| O-ring cord | Ø1.5 | the cord on hand |
| Board screw pilot | Ø2.5 in PETG | a test print |
| Window disc | Ø20 × 1.5 PTFE | the disc as bought |
| ePTFE patch | Ø12 × 0.4 | the patch as bought |
| PG-7 nut | 16.6 across corners | the glands on hand |

## Checks before printing

1. The body and lid are each one closed solid.
2. The body and lid, closed, do not intersect.
3. The board (x 0..43.18, y 0..50.8, z −1.6..0) sits on the standoff tops, and every wall is at least 2.0 from it.
4. Every gland nut (16.6 across corners, behind its hole) is at least 1.0 clear of every wall and the lid.
5. BARO: no straight line from outside through the vent reaches the inside without hitting the baffle.
6. UV: nothing on the mount face (bosses, lugs) intrudes into the Ø18 keep-out.
7. Each insert bore stays blind: none pierces the sealed cavity.
