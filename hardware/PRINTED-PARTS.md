# Printed parts: the full list for the final stack

This is every 3D-printed part in the weather station except the TX base itself (enclosure 4 plus its two fixes, which
is settled). It covers the TX's loose printed parts, the test prints, the three pod boxes and their lids, the shield
remix, and every place one part attaches to another or to the pole.

Where the numbers come from:
- Every dimension here comes from the code: `hardware/tx-stack-r1/cage/cage.py`, `hardware/tx-stack-r1/sources.py`,
  `hardware/pods-r1/box/podbox.py`, `hardware/pods-r1/sources.py` and `hardware/pods-r1/shield/remix.py`.
- The STL numbers (envelope, volume, triangle count) were measured off the committed files with numpy-stl in
  `.venv-cad` on 2026-11-24. Every committed STL is closed: no open edges.
- The check numbers come from running the checks that day (see [Checks run](#checks-run-2026-11-24)).
- Where a doc disagrees with the code, the code wins. The disagreements are listed at the end.

Mass is the solid volume times 1.27 g/cm³ (PETG). That's an upper bound, because the slicer's infill makes most parts
lighter. Print times are rough, from the 3.6 min/cm³ that `cage.py` keeps as `RING_PRINT` (Clint's coupon r1 on the H2D:
5.6 cm³ in about 20 minutes). The printer is the Bambu H2D (`cage.H2D_BED`, 325 x 320 bed), and every part fits it.

## Summary

| Part | Status | STL | Material | Envelope (mm, as the STL lies) | Qty |
|---|---|---|---|---|---|
| Rim test ring | TEST-ONLY | `tx-stack-r1/cage/stl/rim-ring.stl` | not stated (PETG, the base's material) | 175.50 x 129.50 x 8.00 | 1 |
| Base test coupon | TEST-ONLY | `tx-stack-r1/cage/stl/coupon.stl` | not stated (PETG, the base's material) | 29.00 x 42.50 x 74.50 | 1 |
| EVM front clips (left + right, one file) | FINAL | `tx-stack-r1/cage/stl/evm-clips.stl` | PETG (`cage.py` header) | 27.50 x 9.90 x 4.00 | 1 file (2 clips) |
| Lid shade | FINAL (the first print is its fit test) | `tx-stack-r1/cage/stl/lid-shade.stl` | white PETG | 140.30 x 186.30 x 29.40 | 1 |
| Retention bar | GATED: no STL | none | PETG (`cage.py` header) | 10.75 x 2.50 x 77.88 (box frame) | 1 |
| TH pod body | FINAL | `pods-r1/box/stl/pod-th-body.stl` | PETG, light colour | 63.18 x 107.22 x 27.64 | 1 |
| TH pod lid | FINAL | `pods-r1/box/stl/pod-th-lid.stl` | PETG, light colour | 63.18 x 107.22 x 3.00 | 1 |
| BARO pod body | FINAL | `pods-r1/box/stl/pod-baro-body.stl` | PETG, light colour | 68.26 x 111.03 x 27.64 | 1 |
| BARO pod lid | FINAL | `pods-r1/box/stl/pod-baro-lid.stl` | PETG, light colour | 68.26 x 111.03 x 3.00 | 1 |
| UV crown body | FINAL | `pods-r1/box/stl/pod-uv-body.stl` | PETG, light colour | 117.53 x 117.60 x 40.33 | 1 |
| UV crown lid (dome) | GATED: `uv_window` | `pods-r1/box/stl/pod-uv-lid.stl` | PETG, light colour | 117.53 x 117.56 x 37.40 | 1 |
| Remixed shield top cap | LOCAL-ONLY | none in git (`shield_out`) | not stated | not given (mesh-derived) | 1 |
| Remixed shield L-arm | LOCAL-ONLY | none in git (`shield_out`) | not stated | not given (mesh-derived) | 1 |
| Rim corner coupon r8, edge strips | TEST-ONLY, retired | `tx-stack-r1/cage/stl/rim-coupon.stl`, `rim-edge-long.stl`, `rim-edge-short.stl` | - | 47 x 45 x 8, 25 x 175 x 8, 130 x 25 x 8 | don't print |
| Pod boxes v1 | retired | `pods-r1/box/v1/*.stl` | - | - | don't print |

Not in this document:
- The TX base (enclosure 4 + fixes 1 and 2): settled. Its moulded features get one short section below,
  [Interfaces on the base](#interfaces-on-the-base).
- Clint's printed lid bolts (`lid_bolt` in `tx-stack-r1/sources.py`): his own STL (`lid_bolt.stl`, 2026-11-17), not
  in the repo. Their numbers are in the attachment list.
- The rest of the radiation shield (cup, stand, six louver plates): Clint's 3MF as he got it, unchanged.

## Features of the base, not separate prints

These are moulded into the base. They are not separate prints, and the base's checks cover them:
- the pack tray, its 45° front-lip ramp, its two strap slots and the support block under its left end (`tray_solid`)
- the card slots in the left wall and the right corner post, and the backplane groove, slot and support pads
- the EVM supports: the left ledge, the left keeper, the right fin and the right lid-end block, with the two clip
  insert bores (`charger_solid`)
- the gland and vent holes in the bottom wall, over 1 mm pockets in its inside face. There are no gland bosses:
  `cage.py` says "No outside bosses and no drip edge".

The retention bar is the one exception. It is a **separate print** (`parts()` notes it as "separate: two M3 screws").
Its solid comes from `bar_solid`, but nothing writes an STL of it yet (see [Retention bar](#retention-bar-gated)).

## Frames

- **TX box frame (Xb, Yb, Zb).** Seen from the open lid: Xb runs right from the lid frame's left edge, and the inside
  left wall is at Xb 1.25. Yb runs from the inside floor (the back as hung) toward the lid. Zb runs up from the lid
  frame's bottom edge, and the inside bottom wall is at Zb 1.0. This frame is **left-handed**, so a part's solid in
  it is a mirror image. Every TX print file goes through `cage.true_frame()` ((Xb, Yb, Zb) → (Xb, Zb, Yb)) or is built
  in the real hand. The lid's top face is at Yb 142 and the base-lid seam is at Yb 117.
- **Lid-rim frame** (`cage/lid-rim-spec.md`, the ring): origin at the lid's centre, X along the long side, Y along the
  short side, Z up from the bed.
- **Pod board frame** (`podbox.py`, `CAD-BRIEF.md`): origin at the Perma-Proto Quarter's lower-left corner, on its
  component face. x runs to the right along the board, and y runs up along it (the jack's mouth faces −y). z points
  out of the component face toward the lid. The mount face is z −9.5. The pod STLs keep x and y from this frame and only shift z.
- **Shield frame** (`shield/assemble.py`): Z up, the louver-plate axis on the Z axis, Z = 0 on the arm's pocket floor.

---

## TX parts

### Rim test ring (TEST-ONLY)

| | |
|---|---|
| STL | `hardware/tx-stack-r1/cage/stl/rim-ring.stl` |
| Generator | `cage.py: ring_solid()` (written by `write_ring()`), from the segment table in `cage/lid-rim-spec.md` via `lid_rim_spec.py` |
| Regenerate | `cd hardware/tx-stack-r1/cage && ../../../.venv-cad/bin/python cage.py --ring` (not gated) |
| Purpose | Checks the base's sealing lip, all four S-curves and the four bolt holes on the real #905 lid before the full base prints. It settles `ring_fit`. |
| Material | Not stated in code. It's a fit test of the base's rim, so print it in the base's PETG. |
| Orientation | Flat on its land (ASSEMBLY.md 2.1). The STL is in that pose. No supports needed (land + a vertical lip). |
| Print notes | Not specified. `cage.py` estimates about 58 min. |
| Envelope | 175.50 x 129.50 x 8.00, 16.23 cm³, 5728 triangles, about 20.6 g |
| Frame | Lid-rim frame: origin at the lid centre (the STL runs X −87.75..87.75, Y −64.75..64.75, Z 0..8) |

| Feature | Value | Source |
|---|---|---|
| Outline | 175.5 x 129.5, corner R4 (`corner_r_out`, not measured from the scan) | `lid-rim-spec.md`, `l5_lid_out` |
| Land | Z 0 to 3.5, from the outline in to the lip's inner face, open in the middle | `ring_solid` |
| Lip | 2 wide x 4.5 tall on the land (Z 3.5 to 8), centred on the lid channel's centre line | `rim_tongue` |
| Lip path | 28 segments, 12 arcs, straights 169.5 x 123.0 apart centre to centre. Each S is 15.4 deep, with outer bends R3.5 and a middle bend R7.15 | `seal_s`, `seal_curve_r` |
| Holes | 4 x Ø7 at the lid's bolt positions, 156 x 109 apart | `lid-rim-spec.md`, `l2_screw_pos` |
| Hole to lip | 3.90 (spec asks at least 2.2); hole to the outline 6.25 | `ring_checks` |

Mates with: the #905 clear lid (its O-ring channel and corner bosses). No fasteners.

Checks: `ring_checks()` (only with `--ring`). Results: tangency 0.0° at every joint, spans 169.5 x 123, valid solid, fits the bed.
It also prints `SPEC INCONSISTENT: the short-side straight lip is 3 in from the outline, the spec's check says 3.25`.
That's the spec's own stated check against its segment table, not a ring fault.

Open items: `ring_fit` (the whole point of the print). The lip height (L6) isn't settled either: the ring has 4.5 and
enclosure 4 has 2.5 (`enc_lip`), and Clint's report on the ring decides it.

### Base test coupon (TEST-ONLY)

| | |
|---|---|
| STL | `hardware/tx-stack-r1/cage/stl/coupon.stl` |
| Generator | `cage.py: coupon_solid()` (the base's `shell_solid()` plus the left wall, cut to `COUPON`) |
| Regenerate | `cd hardware/tx-stack-r1/cage && ../../../.venv-cad/bin/python cage.py --coupon` (not gated) |
| Purpose | The base's top-left corner, used to tune the card slot fit, try a printed lid bolt in its bore, check the land and lip round one corner, and leak-test a wall patch. |
| Material | Not stated. Same PETG as the base, since it stands in for it. |
| Orientation | Real hand, Yb up, the cut face at Yb 45 on the bed (`cage.py --coupon`, ASSEMBLY.md 2.2). Same pose as the base, so the 45° roofs print unsupported. |
| Print notes | Not specified. About 126 min (`COUPON_CM3` 35.1 x 3.6). |
| Envelope | 29.00 x 42.50 x 74.50, 35.10 cm³, 2434 triangles, about 44.6 g |
| Frame | Box frame region Xb −4..26, Yb 45..120.5, Zb 130..173.5, turned through `true_frame` and set on the origin |

| Feature | Value |
|---|---|
| Card slot | B3's slot in the left wall, 2 mm deep, 1.6 + `slot_clear` 0.3 wide |
| Lid-bolt bore | the top-left one at (Xb 7.25, Zb 162.75): Ø10 from Yb 80.75, 45° chamfer to Ø14.6 at the wall top |
| Rim | wall top (seam) at Yb 117, the 2 x 2.5 sealing lip round the corner block |
| Leak patch | left wall 72 x 42 (`coupon_checks`); ASSEMBLY.md says the top wall is over 30 x 30 too |

Mates with: a SolderFul card (slot), one of Clint's printed lid bolts, the #905 lid's corner.

Checks: `coupon_checks()` runs on every `cage.py` run. With `--coupon` it also checks the solid is valid and its volume is
`COUPON_CM3` ± 0.5. Last run: B3 slot, bore at (7.25, 162.75), lip round the corner, 72 x 42 patch, 35.1 cm³.

Open items: `slot_clear` 0.3 (TBD, tune here), and the lip squeeze (follows L6).

### EVM front clips (FINAL)

| | |
|---|---|
| STL | `hardware/tx-stack-r1/cage/stl/evm-clips.stl` (both clips side by side) |
| Generator | `cage.py: clip_solid(k)` for k = 0 (left), 1 (right); `clip_print()` lays them out |
| Regenerate | `cd hardware/tx-stack-r1/cage && ../../../.venv-cad/bin/python cage.py --clip` (not gated) |
| Purpose | Two L-clips that hold the BQ25798EVM's front edge down and stop it sliding toward the lid. The board has no mounting holes. Two clips instead of one bar, because J8 sits on the front edge between them. |
| Material | PETG (the `cage.py` header: "PETG on the Bambu H2D"). Nothing clip-specific. |
| Orientation | On their top faces, the lip flush with the plate's top, so both sit on the bed (`clip_print`). No supports. |
| Print notes | Not specified. |
| Envelope | 27.50 x 9.90 x 4.00, 0.70 cm³ for the pair, 1056 triangles, about 0.9 g |
| Frame | Built in the box frame, turned through `true_frame`, then onto the top face; left clip at X 0, right clip from X 16 |

| Feature | Left clip | Right clip |
|---|---|---|
| Plate (box frame) | Xb 1.75–12.0, Yb 101.9–109.5, Zb 48.41–52.41 (4.0 tall, `CLIP_T`) | Xb 94.5–106.0, same Yb and Zb |
| Lip over the board | Yb 99.6–101.9, Zb 50.21–52.41: reaches 2.0 over the board's front edge (`CLIP_LIP`), 0.2 above its top face (`CLIP_ABOVE`), covers 3.75 along the edge | same |
| Plate back face to the board's front edge | 0.3 (`CLIP_GAP`) | 0.3 |
| Screw hole | Ø3.4 through, at (4.5, 106) | Ø3.4 through, at (100.25, 106) |
| Screw | M3 x 8 socket cap (head Ø5.5 x 3.0, `CLIP_SCREW`). 4.0 of thread in the insert | same |
| Insert (in the base) | M3 heat-set, `insert_m3` 5.7 long x 4.6 knurl, in a Ø4.0 x 6.5 bore (`bar_bore`) down from the keeper's top | same, in the lid-end block |

Mates with: the base's left keeper / right fin and lid-end block (seat at Zb 48.41, the EVM board's underside level),
and the EVM's front edge (board Xb 8.25–98.25, front edge Yb 101.6, top face Zb 50.01).

Checks: `clip_checks()` on every `cage.py` run: insert on its seat, the head inside the plate, clear of the board, the lip
at least 2.0 over the edge, thread 3.0 to (bore − 0.5), every clip box and screw head at least 1 mm from every EVM part and the
base's keepouts. Last run: lip 3.75 over the board and 0.2 above it, 4 of thread. The nearest EVM part is J8, 11.2 mm
from the left clip, and JP9, 13.4 mm from the right. `solar_checks()` also keeps the solar pair 1 mm clear of the clips
(nearest anything is the pack tray, 1.3). `coax_corner_check()` includes the right clip.

Open items: `insert_m3` (5.7 x 4.6, TBD: calipers). The EVM's heights (`evm` 15 above, `evm_under` 4 below, TBD) and
`evm_edge_tails` (TBD) set the ledges the clips sit beside.

### Lid shade (FINAL; its first print is the fit test)

| | |
|---|---|
| STL | `hardware/tx-stack-r1/cage/stl/lid-shade.stl` |
| Generator | `cage.py: shade_solid()`, laid down by `shade_print()` |
| Regenerate | `cd hardware/tx-stack-r1/cage && ../../../.venv-cad/bin/python cage.py --shade` (not gated) |
| Purpose | A white cap over the #905's clear lid that keeps sun off the cards, EVM and pack. Without it `shade_estimate()` gives 17–26 K over the air on a clear day, which is past the charger's 41.8 °C WARM stop. With it, 0.7–1.0 K. |
| Material | **White PETG**, so the plate reflects most of the sun (it absorbs about 25 %, `shade_estimate`). |
| Orientation | Plate down on the bed, skirt and feet up (`shade_print`, README BOM "Print plate down"). The vent windows are 20 mm bridges in vertical walls. No supports. |
| Print notes | Plate and skirt 2.4 thick: "2.4 is six 0.42 mm perimeters" (`shade` row; see the disagreements). `shade_checks` fails it under 1.6 ("under four perimeters"). Layer height and infill not specified. About 6 h at 3.6 min/cm³. |
| Envelope | 140.30 x 186.30 x 29.40, 101.47 cm³, 3508 triangles, about 128.9 g |
| Frame | Built in the real hand (X = Xb, Y = Zb, Z = Yb), turned 180° about X and set on the origin, so STL Z = 156.4 − Yb |

| Feature | Value | Source |
|---|---|---|
| Skirt inside | 135.5 x 181.5, corner R7 (the lid's R4 + 3): 3.0 off the lid's sides | `shade` gap 3.0, `corner_r_out` |
| Skirt outside | 140.3 x 186.3, R9.4 | `shade` t 2.4 |
| Plate | 2.4 thick, underside 12 over the lid's top face (Yb 154–156.4) | `shade` air 12 |
| Skirt reach | 15 down the lid's sides, to Yb 127: 10 above the seam | `shade` skirt 15 |
| Vent windows | 14 of them, 20 wide x 8 tall (Yb 144–152), 12 min between them. 4 per long side, 3 per short side. 2240 mm² out against 1902 mm² in at the skirt gap | `SHADE_WIN`, `shade_windows()` |
| Crush ribs | 10 (3 per long side, 2 per short), 3 wide, Yb 129–140, each reaching 0.3 past the gap into the lid's side | `SHADE_RIBS`, `shade_rib_fit` |
| Feet | 4 x Ø8 at (Xb 26.75 / 96.75, Zb 34.75 / 134.75), standing 12 on the lid's top face | `shade` foot 8, `SHADE_FEET` |
| Plate to bolt heads | 5 (bolt heads assumed 7 proud) | `lid_head_proud` |

Mates with: the #905 lid's polycarbonate sides (the ribs) and its top face (the feet). It clears Clint's printed bolt
heads (head Ø11) and the SMA bulkhead. It's a push fit with no fasteners, and it pulls off by hand before the lid bolts come out.

Checks: `shade_checks()` on every `cage.py` run checks:
- the plate is at least 2 over the bolt heads, and each foot is at least 2 from a bolt head and on the lid's flat top
- the skirt ends at least 5 over the lip and clears the SMA bulkhead
- the rib fit is 0–0.6, the wall is at least 1.6, and the windows' area is at least the skirt gap's

`--shade` also checks the solid is valid. Last run: 5 over the heads, skirt 10 above the seam, 10 ribs, 14 windows,
2240 / 1902 mm².

Open items:
- `lid_head_proud` 7 (TBD): measure the printed bolts with the lid on.
- `shade_rib_fit` 0.3 (TBD): tune on the first print until it pushes on by hand and doesn't lift in a gust.
- `corner_r_out` R4 (TBD, not from the scan): it sets the skirt's inside corner.

### Retention bar (GATED)

| | |
|---|---|
| STL | none |
| Generator | `cage.py: parts()` ("retention bar" box) + `bar_solid()` (its two holes). No print pose and no exporter |
| Regenerate | nothing writes it. `cage.py --solid` builds it and reports it valid at 2.0 cm³. `cage.py --stl` is refused until `l2_screw_pos` and `ring_fit` are sourced, and even past that gate `main()` only builds solids. It writes no STL. |
| Purpose | A flat strip across the four cards' front-left corners that stops a card backing out of its socket. It comes off before any card does. |
| Material | PETG (the `cage.py` header). |
| Orientation | Not specified. It's a flat 2.5 mm strip, so flat on its broad face is the obvious pose. |
| Envelope | Box frame Xb 1.25–12.0, Yb 63.37–65.87, Zb 72.73–150.61: 10.75 x 2.50 x 77.88, 2.0 cm³ (`--solid`), about 2.5 g |

| Feature | Value | Source |
|---|---|---|
| Thickness in front of the cards | 2.5 | `bar` |
| Holes | 2 x Ø3.4 through (along Yb) at Xb 5, Zb 76.5 and 146.5 | `bar_inserts` |
| Back face | Yb 63.37, 1.0 in front of the cards' front edge (`CARD_FRONT` 62.37) | `parts()` |

Mates with: the left wall's front face (Yb 63.37), with two M3 heat-set inserts (`insert_m3`) in Ø4.0 x 6.5 bores at
Xb 5, Zb 76.5 and 146.5. The screw is M3. Its length isn't given anywhere in the code.

Checks: the `cage.py` box checks (inside the box, off the base's keepouts) and the `--solid` validity check. The
backplane checks leave it out on purpose (it goes on after the cards).

What it's waiting for: an export path (a print pose and a `write_stl` call), and the M3 screw length. Behind those sit
`insert_m3` (TBD) and the base's own gate (`l2_screw_pos`, `ring_fit`).

### Interfaces on the base

These belong to the settled base. They're listed so the loose parts above have something to mate with. All values are from
`cage.py` (box frame).

| Feature | Where and how big | What mates |
|---|---|---|
| Lid-bolt bores | 4 x Ø10 in the corner blocks (15.4 square) from Yb 80.75, chamfered 45° to Ø14.6 at the wall top; at Xb 7.25 / 116.25, Zb 6.75 / 162.75 (109 x 156 apart) | Clint's printed lid bolts |
| Wall top and lip | seam at Yb 117; sealing lip 2 x 2.5 on the inside edge, on the lid channel's centre line (3.0 / 3.25 in from the lid's short / long edges) | #905 lid and its O-ring |
| Card slots | one per card, 2 mm deep in the left wall (`cage_wall` 8.5) and the right corner post, 1.6 + 0.3 wide; B4 Zb 80.73, B2 95.97, B1 116.29, B3 136.61 (card top faces) | SolderFul cards |
| Backplane | 3 plain Ø6 pads, tops at Yb 8; left-wall groove Xb 6–8.5, Yb 8–10.1 (45° roof) down a rail to Zb 67.01; right-post slot 6.5 deep (to Xb 92.30), 2.1 high | PAD3U backplane, no screws |
| Retention bar inserts | Ø4.0 x 6.5 bores at Xb 5, Zb 76.5 / 146.5 in the left wall's front face (Yb 63.37) | retention bar |
| EVM supports | left ledge (Xb 1.25–10.25, 2 under the board's edge, Yb 10.1–103, chamfered under), left keeper (to Xb 9.25, Yb 95.13–109), right fin (Xb 96.25–100.25, floor to the board), right lid-end block (Xb 100.25–122.25, Yb 92–109); board seat Zb 48.41; notched under the edge tails | BQ25798EVM |
| Clip inserts | Ø4.0 x 6.5 bores down from Zb 48.41 at (4.5, 106) and (100.25, 106) | EVM front clips |
| Pack tray | 3 thick at Zb 21.41–24.41, Xb 1.25–96.25, Yb 0–62; 45° lip ramp Xb 16.5–89.5 from Yb 56 up 6 to Yb 62; strap slots 3 x 20 at Xb 15 and 91 from Yb 19; support block to Xb 12, Yb 58, 5 tall | pack #353 (69 x 54 x 18) and a hook-and-loop strap |
| Glands | bottom wall: 5 x Ø13.0 (PG-7 #762) and 2 x Ø15.5 (PG-9 #761, each with a 24 mm clearance cut up to Zb 8), at Xb 26 / 50 / 74 / 98, Yb 25 / 60 (no gland at (74, 60)) | glands, port cables, solar lead |
| Vent | Ø12.5 at (Xb 50, Yb 85) in the bottom wall | Amphenol LTW VENT-PS1YBK-N8002 (M12 x 1.5) |
| SMA bulkhead | Ø6.44 in the right wall at Yb 94.14, Zb 60.38, Ø14.2 x 1 nut seat inside | SMA bulkhead jack, bonding lug |
| Mounting flanges | both short ends in the floor plane, Xb 31.75–91.75, reach 28, 6 thick, R8 corners, a 7 mm 45° gusset; two 3.5 x 14 slots each at Xb 48 and 75.5, Zb −18 / 187.5 | hose clamps to the pole |

---

## Pod boxes

All six come from `hardware/pods-r1/box/podbox.py`. Regenerate them all with

```
cd hardware/pods-r1 && ../../.venv-cad/bin/python box/podbox.py
```

That writes `box/stl/pod-{th,baro,uv}-{body,lid}.stl`. `run.sh` runs it too. A run on 2026-11-24 rewrote all six
byte for byte (no git change).

The common print rules come from the `podbox.py` docstring and `CAD-BRIEF.md`:
- Material: PETG in a light colour.
- Body: printed back face (the mount face) down. Lid: printed inner face down, with the O-ring groove on the bed. The
  STLs are saved in those poses.
- No supports. Every hole whose axis lies flat in print (the TH and BARO bottom-wall glands and the vent) is a
  teardrop pointing +z, capped at 1.1 r.
- Layer height, perimeters and infill: not specified.

The shared numbers:

| Feature | Value | Source |
|---|---|---|
| Walls, back included | 3.0 | `WALL` |
| Inside corner radius | 2.0 (outside 5.0) | `R_IN` |
| Clearance, every part / plug and bend / board copper side to the walls and lid | at least 2.0 | `CLEAR` |
| Gland nut to the nearest wall or the lid | at least 1.0 (this sets the TH and BARO depth) | `NUT_GAP` |
| Gland hole | Ø13.0 (PG-7 #762, nut 16.6 across corners) | `gland` |
| M3 heat-set insert bore | Ø4.0 x 6.7 (knurl − 0.6, length + 1.0, from `insert_m3` 5.7 x 4.6) | `pod_insert_bore` |
| Board standoffs | 2 x Ø5.5 (`mount_keep` 2.75 radius) at (3.81, 25.4) and (39.37, 25.4), from the back wall's inner face (z −6.5) to z −1.6; Ø2.5 pilot, blind, stopping 1.0 short of the outside back face | `mount_keep`, `pod_pilot_m3` |
| Board screws | 2 x M3 x 8 pan head A2 (ISO 7045), thread-forming into the pilots | `pod_screw` |
| O-ring | Ø1.5 cord, NBR 70 (EPDM 70 the alternative), cut and butt-joined. Not 1.78 / AS568 | `pod_oring` |

### TH pod body and lid (FINAL)

| | Body | Lid |
|---|---|---|
| STL | `hardware/pods-r1/box/stl/pod-th-body.stl` | `hardware/pods-r1/box/stl/pod-th-lid.stl` |
| Generator | `podbox.py: body("TH")` → `_build` | `podbox.py: lid("TH")` |
| Envelope | 63.18 x 107.22 x 27.64 | 63.18 x 107.22 x 3.00 |
| Volume, mass | 41.40 cm³, about 52.6 g | 15.28 cm³, about 19.4 g |
| Triangles | 4268 | 2524 |
| Rough time | about 2.5 h | about 55 min |
| STL frame | board frame, shifted so the back face (z −9.5) is Z 0 | board frame, shifted so the rim (z 18.14) is Z 0 |

Purpose: holds the TH pod board (Perma-Proto Quarter with the ID EEPROM and the RJ11 jack). The SHT45 itself sits
outside on the shield stand, on a 4-core lead. The box is completely sealed: no window and no vent.

| Feature | Value |
|---|---|
| Inside | 47.18 x 91.22 x 24.64 (x −2.00..45.18, y −38.42..52.80, z −6.50..18.14) |
| Outside, with the lid | 63.18 x 107.22 x 30.64, lugs included |
| Corner lugs | 4 x Ø8.0, full height, joined to the walls by flat webs, centres (−6.00, −42.42), (−6.00, 56.80), (49.18, −42.42), (49.18, 56.80) |
| Lid insert bores | Ø4.0 x 6.7 down from the rim in each lug |
| Mount insert bores | Ø4.0 x 6.7 up from the back face in each lug, blind (z −9.5 to −2.8) |
| Port gland | Ø13.0 teardrop through the bottom wall at x 10.16, z 8.84, axis −y, coaxial with the jack |
| Lead gland | Ø13.0 teardrop through the bottom wall at x 31.82, z 5.82, axis −y (SHT45 lead, OD 3.0–4.3) |
| Lid | 3.0 plate, the body's outline with the lugs, 0.8 chamfer round its top outer edge, 4 x Ø3.4 screw holes |
| Lid groove | 2.03 wide x 1.12 deep (1.35 d x 0.75 d), centreline over the rim's centreline (282.8 long), 25.3 % squeeze. The lid lands flat on the 3.0 rim as a hard stop, so the groove sets the squeeze, not the screw torque |

### BARO pod body and lid (FINAL)

| | Body | Lid |
|---|---|---|
| STL | `hardware/pods-r1/box/stl/pod-baro-body.stl` | `hardware/pods-r1/box/stl/pod-baro-lid.stl` |
| Generator | `podbox.py: body("BARO")` | `podbox.py: lid("BARO")` |
| Envelope | 68.26 x 111.03 x 27.64 | 68.26 x 111.03 x 3.00 |
| Volume, mass | 45.58 cm³, about 57.9 g | 17.38 cm³, about 22.1 g |
| Triangles | 4488 | 2524 |
| Rough time | about 2.7 h | about 1 h |
| STL frame | as TH | as TH |

Purpose: holds the BARO pod board with the BMP581. It's sealed against water but has to breathe, because a sealed box
drifts about 3.5 hPa per °C. That's why it has the vent, the ePTFE membrane and the baffle.

| Feature | Value |
|---|---|
| Inside | 52.26 x 95.03 x 24.64 (x −2.00..50.26, y −38.42..56.61, z −6.50..18.14) |
| Outside, with the lid | 68.26 x 111.03 x 30.64 |
| Corner lugs | 4 x Ø8.0 at (−6.00, −42.42), (−6.00, 60.61), (54.26, −42.42), (54.26, 60.61); lid and mount insert bores as TH |
| Port gland | as TH: Ø13.0 at x 10.16, z 8.84, axis −y |
| Vent | Ø4.0 teardrop through the bottom wall at x 34.36, z 0.70, axis −y |
| ePTFE seat | Ø12.4 x 0.4 in the bottom wall's inner face, concentric with the vent, teardrop-topped like the holes (v1) |
| ePTFE vent | Gore VE70510, adhesive, Ø10.2 x 0.34, 5.5 effective (`baro_eptfe`) |
| Baffle | fin 1.6 thick at x 26.36..42.36, y −35.92..−34.32 (2.5 above the bottom wall's inner face), from the back wall z −6.5 up to z 8.7; overhangs the vent hole by 6.0 on its three open sides |
| Lid groove | 2.03 x 1.12, centreline 300.6, 25.3 % squeeze |

### UV crown body (FINAL)

| | |
|---|---|
| STL | `hardware/pods-r1/box/stl/pod-uv-body.stl` |
| Generator | `podbox.py: body("UV")` → `_crown_body()` |
| Envelope | 117.53 x 117.60 x 40.33, 87.46 cm³, 6202 triangles, about 111.1 g, about 5.3 h |
| STL frame | board frame, shifted so the floor (z −9.5) is Z 0. The crown's axis is at (10.16, 13.375) |
| Orientation | floor down (mount face on the bed). The gland hole is a teardrop. The O-ring groove and bayonet channels are shallow roofs (0.93 and 1.3 deep). |

Purpose: the drum of the UV pod. It holds the UV pod board and stands on the remixed shield cap.

| Feature | Value |
|---|---|
| Drum | outside Ø117.6 (r 58.8) from the floor (z −9.5) to the ledge (z 20.84); bore r 54.0 from z −6.5 (3.0 floor) |
| Spigot | r 56.4 outside, r 53.6 inside (2.8 wall; it steps 0.4 in from the bore on a 45° chamfer), z 20.84 to the joint at z 30.84 |
| O-ring groove | radial, round the spigot, centre z 23.84: 2.03 wide x 0.93 deep, centreline 351.4. 24.7 % squeeze with the skirt's 0.2 clearance. Cord Ø1.5, or a stock 110 x 1.5 NBR 70 O-ring |
| Bayonet channels | 3 entry slots down from the spigot's top at 90°, 210°, 330° (box frame, from +x), each with a channel running 25° clockwise (seen from above), 1.3 deep. The channel's end is the stop. No slot over the gland (270°) |
| Detents | one Ø1.4 post per channel floor, just behind the locked lug, 0.2 interference with the lug's inner face |
| Port gland | Ø13.0 teardrop, level through the drum wall at x 10.16, z 8.84, axis −y. Flat land inside at y −38.42 (the nut's seat), Ø22 spot face outside |
| Breather | Ø2.0, level through the drum wall at 90° (opposite the gland), z 7.17. A flat Ø12.4 seat is cut into the bore with its floor at r 54.4, for a Gore VE70510. 4.4 of drum wall behind it |
| Floor bosses | 4 x Ø8.0 on r 31 about the axis, at (−6.27, 39.66), (−20.05, 20.35), (−16.13, −3.05), (26.59, −12.91), 7.7 tall from the mount face (`mount_boss_depth`: bore + 1.0), each with a blind Ø4.0 x 6.7 insert bore from below (1.0 cap) |
| Board standoffs | as TH/BARO |
| No corner lugs, no lid screws | |

### UV crown lid (GATED: `uv_window`)

| | |
|---|---|
| STL | `hardware/pods-r1/box/stl/pod-uv-lid.stl` |
| Generator | `podbox.py: lid("UV")` → `_crown_lid()` |
| Envelope | 117.53 x 117.56 x 37.40, 47.75 cm³, 6138 triangles, about 60.6 g, about 2.9 h |
| STL frame | board frame, shifted so the skirt's bottom (z 20.84, the ledge) is Z 0. Dome up |
| Orientation | The STL is saved skirt down, dome up. The code doesn't give a pose or support plan for the crown lid: the "no supports" note in the docstring was written for the flat lids. In this pose the two LTR390 bosses and the aperture tube hang from the dome's underside (their bottoms at about Z 29.5 and 33 above the bed), and the inner apex is a near-flat ceiling. So expect supports inside the dome, or choose a pose in the slicer. |
| Gate | `uv_window` (TBD). `sources.py`: "measure the one you get (diameter and thickness, calipers) and set this row before the lid prints: the recess follows it." |

Purpose: the UV pod's dome. It carries the window over the LTR390 and the LTR390 itself, and it twists onto the drum.

| Feature | Value |
|---|---|
| Skirt | bore r 56.6 (0.2 radial clearance on the spigot), outside r 58.8 (flush with the drum), 2.2 wall, z 20.84 to 30.84 |
| Bayonet lugs | 3 inside the skirt, each 8.0 arc x 2.4 tall x 1.0 deep, centred 3.5 below the joint (z 27.34), at 90°/210°/330° turned −25°. Lock: 25° clockwise seen from above, like a jar lid |
| Dome | quarter ellipse, 28 rise from the joint, 3.0 shell, apex z 58.84, cut flat at z 58.24 |
| Window recess | Ø20.3 x 1.0 deep in the flat, on the axis: the disc sits flush |
| Aperture | Ø17.0 (a 1.5 ledge all round), at the top of a tube (OD 21.0) from z 53.79 up to the dome |
| Window | JGS1 fused quartz disc, uncoated, Ø20 x 1 (generic; Edmund #22-694 the fallback), bedded in DOWSIL 3145 RTV (neutral cure) |
| LTR390 bosses | 2 x Ø5.0 at (0.00, 7.03) and (20.32, 19.73), faces at z 50.39 (board top z 50.34 + 0.05 copper); Ø2.1 pilots to z 55.24 (0.5 past the M2.5 x 6 screw's tip) |
| LTR390 screws | 2 x M2.5 x 6 pan head A2, thread-forming (`ltr_screw`, `pod_pilot_m25`) |

### Pod checks and their last numbers

Run: `.venv-cad/bin/python -m unittest tests.test_pods_box tests.test_pods_v1` (17 tests, OK). `run.sh` runs the same
step. The tests assert thresholds without printing numbers, so the numbers below were measured on the same solids with
the tests' own helpers (`tests/test_pods_box.py`), 2026-11-24.

| Check (test) | Threshold | TH | BARO | UV |
|---|---|---|---|---|
| Parts, plug and bend to the body (`test_board_fits`) | ≥ 2.0 | 3.03 | 2.00 | 3.03 |
| Parts to the lid | ≥ 2.0 | 2.54 | 2.54 | 11.21 |
| Board copper side to the walls | ≥ 2.0 | 2.00 | 2.00 | 2.00 |
| Lid over the tallest part | ≥ 2.0 | 2.54 | 2.53 | 5.24 |
| Port gland nut to the lid | > 0.2 (brief: 1.0) | 1.00 | 1.00 | 6.06 |
| Port gland nut to the plug body | > 0.5 | 11.66 | 11.66 | 11.66 |
| Lead gland nut to the lid / plug | > 0.2 / > 0.5 | 4.02 / 14.45 | - | - |
| Lid and body overlap closed (`test_lid_not_glued`) | none | 0 mm³ | 0 mm³ | 0 mm³ |
| Insert bores break into the cavity (`test_insert_bores_blind`, and the longer-insert mutation test) | none | none | none | none |
| O-ring squeeze (`test_uv_crown_seal_and_bayonet`) | > 20 % | 25.3 % | 25.3 % | 24.7 % |
| BARO baffle free gap (`test_baro_vent_baffled`) | ≥ 2.0 (brief: 2.5) | - | 7.90 | - |
| BARO line of sight vent → BMP581 | blocked | - | blocked | - |
| ePTFE seats flat across ≥ Ø11.7 and ≥ 0.34 deep (`test_eptfe_seats`) | | - | yes | yes |
| Breather: drum wall behind its seat (`test_uv_breather`) | ≥ 3.0 | - | - | 4.40 |
| Spigot wall behind the bayonet slots and channels (`test_uv_crown_walls`) | ≥ 1.2 | - | - | 1.52 |
| Plastic round and over the M2.5 pilots | ≥ 1.2 | - | - | passes |
| LTR390 parts clear of the lid, screws only in their pilots (`test_uv_ltr390_clears_lid`) | | - | - | passes |
| Floor bosses on r 31, no keep-outs on the mount face (`test_uv_crown_mount`, `test_mount_face`) | | passes | passes | passes |
| Openings face down / out (`test_openings_face_down`), STLs written (`test_stls_written`) | | passes | passes | passes |
| Model matches Clint's printed v1 TH/BARO; v1 files closed (`test_pods_v1`) | | passes | passes | - |

### Pod open items (all TBD in `pods-r1/sources.py`; each regenerates the boxes)

- `insert_m3` 5.7 x 4.6 (in the TX `sources.py`), so `pod_insert_bore` Ø4.0 x 6.7: calipers on the inserts on hand.
- `pod_oring` Ø1.5: measure the cord.
- `pod_pilot_m3` Ø2.5 and `pod_pilot_m25` Ø2.1: not tried in a test print.
- `uv_window` Ø20 x 1.0: measure the disc as bought, before the UV lid prints (the gate).
- `baro_eptfe` Ø10.2 x 0.34: the vent as bought.
- `gland` nut 16.6 across corners (TX `sources.py`, derived by scaling): the glands on hand.
- `pod_screw` M3 x 8, `pod_mount_screw` M3 x 10, `ltr_screw` M2.5 x 6: not bought.
- `permaproto_q_t` 1.6, `mount_keep` 2.75: measure.

---

## Shield remix (LOCAL-ONLY)

`hardware/pods-r1/shield/remix.py` remixes two parts of Clint's radiation-shield 3MF: the top cap (object_70) and the
L-arm (object_72). The 3MF's licence isn't known, so the remixed STLs go only to `shield_out` (outside git). This section gives
no mesh-derived numbers, renders or files: only our own design intent, our parameters and the interfaces.

Regenerate (local only, needs the 3MF at `sources.shield_3mf`, hash checked):
`cd hardware/pods-r1 && ../../.venv-cad/bin/python shield/remix.py`. It writes `cap_remixed.stl` and
`arm_remixed.stl` to `shield_out`.

Checks: `tests.test_pods_shield` and `tests.test_pods_remix` (15 tests, OK on 2026-11-24), and `remix_checks()` in
`remix.py`. Their numbers come off the shield's meshes, so they're not repeated here.

### Remixed top cap

- Purpose: carries the UV crown on the shield's axis, with the crown's port gland pointing +x (away from the pole).
- Added to the cap:
  - one boss column per mount screw, Ø10 (`BOSS_D`), from the roof down to a screw seat 5.0 (`GRIP`) below the flat top
  - a Ø6.5 counterbore (`CBORE_D`, head + 1) running from each seat straight down and out of the cap's open bottom
  - a skirt under the crown: a 2.4 shell (`SKIRT_T`) that starts 0.6 outside and 0.6 above the top louver plate
    (`SKIRT_FOOT`) and flares out in one S-curve to the crown's drum (r 58.8), with a top ring reaching in to r 36
    (`SKIRT_RING_IN`) that fuses to the roof. Nothing hangs in front of the louvers.
- Interface: 4 x M3 x 10 pan head A2 (`pod_mount_screw`) go up from inside the cap, with the cap off the stack, through
  the counterbores and 5.0 of plastic into the crown's floor-boss inserts (r 31). That leaves 5.0 of thread in the insert.
- Print: on its flat top, as the original (`CAP_PRINT_UP`). The ring is on the bed and the skirt leans in from there.
- Material: not stated in the code.

### Remixed L-arm

- Purpose: carries the TH and BARO boxes beside the cup, below the louver plates. TH goes on the −x face (the side of the
  cup's lead hole) and BARO on the +x face.
- Added to the arm:
  - one vertical face per box, 5.0 thick (`FACE_T`, the base plate's own thickness, checked), 2.0 outside the cup's
    largest radius (`FACE_GAP`), with 6.0 of face past every hole centre (`FACE_MARGIN`)
  - a tab of the same thickness joining each face to the base plate, reaching in to |x| 15 (`TAB_IN`)
  - Ø3.4 holes at the boxes' lug centres
  - a Ø6 lead hole in the TH tab (`LEAD_HOLE_D`) for the SHT45 lead
- Placement: each box's top sits 6 below the lowest louver plate (`BOX_BELOW_PLATES`), its back on the face, lid
  outward, glands down.
- Interface: 4 x M3 x 10 pan head A2 per box, from the face's inner (cup) side through the 5.0 face into the box's back-face lug
  inserts. Fit the boxes before the cup goes on the arm.
- Pole saddle (Clint, 2026-11-24: strapped to the pole like everything else, no screws): a block on the upright's
  back, as wide (`SADDLE_HALF_W` 19.5 each side) and as tall as the upright, with a vertical V groove in its back:
  80° included (`SADDLE_HALF_ANGLE` 40), 28 wide at the back (`SADDLE_LIP` 14), 16.7 deep. A pole from Ø22 to Ø34
  (`POLE_RANGE`) sits on the V's two flanks along two vertical lines, so the arm can't rock or spin once it's strapped.
  `pole_axis(d)` gives where a pole of diameter d sits: the 1 in pole's axis is 19.8 behind the V's apex
  (`POLE_D` 25.4).
- Strap tunnels: two, straight across the saddle along X, 14.5 x 3.8 clear (`STRAP_SLOT`: strap width x thickness),
  between the upright's back face and a 2.0 wall in front of the V's apex (`STRAP_WALL`). Their centres are at Z 5 and
  Z 51 in the shield frame (`STRAP_SLOT_Z`, 46 apart: `STRAP_SLOT_PITCH`), as far apart as the upright allows, with
  at least 1.2 of wall all round (checked). Each tunnel's rear edge is rounded R2 at both exits (`STRAP_EXIT_R`), and
  the saddle's back corners are notched R3 over each tunnel's height (`SADDLE_CORNER_R`), so the strap never bends
  over a sharp edge. A strap goes through a tunnel, out both sides, round the saddle's back corners and round the
  pole: pole and bracket in one loop, about 130 mm on the 1 in pole. The wire straps on the pole go at the same two
  heights, so they bind the arm too.
- The upright's original small slots are filled. Nothing goes through the upright now.
- Print: on its back (`ARM_PRINT_UP`), now the saddle's back face, because the new faces hang below the base plate.
  The faces run back to the saddle's back plane, so they still stand on the bed with the saddle's two flats. The V's
  flanks are 50° from straight down, and the tunnels' roofs (14.5 across) and the tabs' undersides beside the
  saddle are short bridges.
- Pole: two straps per arm (`pole_strap_tie`: Panduit PLT4H-C0, 7.6 x 1.9, 368 long, black weather-resistant nylon
  66; or `pole_strap_band`: a stainless SAE 20 hose clamp, 1/2 in band, an SAE 24 on a pole near 34 mm), through the
  tunnels and round the pole, heads or worm housings turned to the pole's back. `strap_envelope()` is the pole, the
  straps and their heads, and the TH and BARO boxes keep 5 mm from it.
- Material: not stated in the code.

---

## Mounting on the pole

The station isn't mounted anywhere yet, and Clint left the layout to me (2026-11-24), so this is my call. It's drawn
and checked on the restricted full-assembly page (`hardware/printed-parts-pages/build.py`, the layout constants and
`layout_checks()`), which has the exact heights. Directions assume the northern hemisphere, so the sun side is south.

- **The pole:** 1 in (25.4), vertical, its top about 2.0 m above the ground.
- **Top: the SparkFun SEN-15901 weather meter.** Its two-tube mast stands beside the pole's top end on the north
  side, overlapping it by 160 mm, held by both of the kit's gear clamps (20 and 140 mm below the pole's top). The
  cross arm sits on the mast's top, about 2.5 m up, and runs east-west: cups on the east end, vane on the west.
  Wind goes at the top for clean air, and an east-west arm never shades the UV crown (south) or covers the rain
  gauge (north).
- **The radiation shield and the pod bracket, south side.** The bracket's V saddle sits on the pole and the arm
  reaches south, so the UV crown has an open sky toward the sun. The bracket's two zip ties go through its tunnels
  and round the pole and whatever RJ11 cables pass there, never the mast: the bracket's upright tops out at least
  20 mm under the mast's foot. I wanted the crown's top 400 mm under the cross arm. The mast is two tubes long and
  has to start above the bracket, so the crown ends up a little lower than that.
- **The rain gauge, north side.** On its arm, level, 250 mm under the UV crown's top, with nothing above its funnel.
  Its clamp goes round the pole, not the mast. The kit's armature is made for its own tube, so check it closes on
  the 1 in pole; if it doesn't, a hose clamp through it does the job.
- **The TX box, lowest, north side.** In the pole's shade, so the pack stays cool. It hangs by its back, lid facing
  north (out from the pole), lid shade on, top flange 300 mm under the rain gauge's foot, on its two flanges with
  SAE 20 hose clamps (row 10).
- **Cables.** The wind cable comes from the vane end of the cross arm and down the mast; the rain cable from the
  gauge along its arm; the three pod cables from the shield group. All five run down the pole, each on its own
  line round it, held by the bracket's zip ties where they pass it, by plain wire ties no more than about 250 mm
  apart elsewhere, and by the TX base's hose clamps. Each leaves the pole under the box and ends with a drip loop at
  least 70 mm below its gland before it goes up into it.

`layout_checks()` fails the page build if any part runs into another (bar the designed contacts: the saddle on the
pole, the ties through the tunnels, the clamps on the pole and the mast) or if anything is over the rain gauge's
funnel or the UV crown's window.

## Attachment points

| # | Joint | Fastener / method | Side A feature | Side B feature | Source |
|---|---|---|---|---|---|
| 1 | #905 lid → TX base | 4 x Clint's printed lid bolts: head Ø11 x 11, shank Ø6.5 x 23, thread 10 major / 7 minor, 1.5 pitch RH, 11 long, 45 overall | lid's Ø8 holes | Ø10 bores (shallow printed thread) in the corner blocks, 109 x 156 apart | `lid_bolt`, `enc_lid_bores` |
| 2 | Lid seal | the #905's own O-ring, squeezed by the bolts | lid's O-ring channel | base's 2 x 2.5 lip on the channel centre line | `enc_lip`, `rim_tongue` |
| 3 | Lid shade → lid | push fit: 10 crush ribs, 0.3 interference; 4 feet rest on the lid top | skirt ribs, Ø8 feet | lid's polycarbonate sides and top face | `shade`, `shade_rib_fit` |
| 4 | EVM clip (x2) → base | 1 x M3 x 8 socket cap each, into an M3 heat-set insert (5.7 x 4.6) | clip's Ø3.4 hole | Ø4.0 x 6.5 bore at (4.5, 106) / (100.25, 106) | `CLIP_SCREW`, `CLIP_INS`, `bar_bore` |
| 5 | EVM → base | slides back on the ledges; held down and forward by the clips' lips | board edges, front edge | left ledge, right fin top (Zb 48.41) | `charger_solid` |
| 6 | Retention bar → base | 2 x M3 (length not set) into M3 heat-set inserts | bar's Ø3.4 holes | Ø4.0 x 6.5 bores at Xb 5, Zb 76.5 / 146.5 | `bar_inserts` |
| 7 | Cards → base | slide in the slots; the retention bar stops them backing out | card edges | left-wall slots, right-post slots | `parts()` |
| 8 | Backplane → base | none: the plugged cards hold it | board edges | pads, groove, post slot | `backplane_checks` |
| 9 | Pack → tray | hook-and-loop strap | pack #353 | two 3 x 20 strap slots, 45° lip | `STRAP` |
| 10 | TX base → pole | 2 stainless hose clamps (or straps), SAE size 20 (19-44 mm), band 12.7 or narrower: each closes to about 34 mm round the 1 in pole and the flange | mounting flanges, two 3.5 x 14 slots each | pole (about 1 in, 25.4) | `mount_flange` |
| 11 | Glands → base / pods | PG-7 #762 (Ø13.0) and PG-9 #761 (Ø15.5), locknut inside | gland thread | wall hole | `GLANDS`, `gland` |
| 12 | Vent → base | M12 x 1.5 screw-in ePTFE vent, Amphenol LTW VENT-PS1YBK-N8002 | vent thread | Ø12.5 hole at (50, 85) | `enc_glands`, `vent` |
| 13 | SMA bulkhead → base | bulkhead nut, plus the bonding lug (Panduit PV14-14R-L) on the outside thread | jack | Ø6.44 hole, Ø14.2 nut seat | `sma_bulkhead` |
| 14 | TH / BARO lid → body | 4 x M3 x 8 pan head A2 into M3 heat-set inserts | lid's Ø3.4 holes | lug bores Ø4.0 x 6.7 | `pod_screw`, `pod_insert_bore` |
| 15 | TH / BARO seal | Ø1.5 O-ring cord, 25.3 % squeeze, the lid lands on the rim | lid groove 2.03 x 1.12 | 3.0 rim | `pod_oring`, `groove()` |
| 16 | Pod board → body (all three) | 2 x M3 x 8 pan head, thread-forming | Perma-Proto's Ø3.2 holes | Ø5.5 standoffs, Ø2.5 pilots | `pod_screw`, `pod_pilot_m3` |
| 17 | TH / BARO box → remixed arm | 4 x M3 x 10 pan head A2 per box, from the cup side, 5.0 grip, 5.0 in the insert | arm face's Ø3.4 holes (5.0 face) | back-face lug inserts, Ø4.0 x 6.7 blind | `pod_mount_screw`, `remix.arm_mount` |
| 18 | UV crown lid → body | 3-lug bayonet, 25° clockwise, detent 0.2 | lugs in the skirt | spigot slots, channels, detent posts | `CROWN_*` |
| 19 | UV crown seal | Ø1.5 cord or a 110 x 1.5 O-ring, radial, 24.7 % squeeze | skirt bore r 56.6 | spigot groove 2.03 x 0.93 | `groove("UV")` |
| 20 | LTR390 → crown lid | 2 x M2.5 x 6 pan head A2, thread-forming | breakout's corner holes | Ø5.0 bosses, Ø2.1 pilots | `ltr_screw`, `pod_pilot_m25` |
| 21 | UV window → crown lid | DOWSIL 3145 RTV bed, 24 h cure | Ø20 x 1 JGS1 disc | Ø20.3 x 1.0 recess, 1.5 ledge | `uv_window`, `uv_window_seal` |
| 22 | ePTFE vents → BARO / crown | adhesive (Gore VE70510), on a clean flat seat | vent | Ø12.4 x 0.4 seats | `baro_eptfe`, `eptfe_seat` |
| 23 | UV crown → remixed cap | 4 x M3 x 10 pan head A2 up from inside the cap, through the counterbores, 5.0 grip | cap's boss seats | floor-boss inserts on r 31 | `pod_mount_screw`, `remix.uv_mount` |
| 24 | Remixed arm → pole | 2 straps, each through a strap tunnel and round the pole: a Panduit PLT4H-C0 heavy zip tie (7.6 x 1.9, 368 long, UV-black nylon 66) or a 1/2 in stainless SAE 20 hose clamp; about 130 mm of loop on the 1 in pole; the wire straps at the same heights | saddle's 80° V; two 14.5 x 3.8 tunnels at Z 5 and 51 (`STRAP_SLOT_Z`) | pole (about 1 in, 25.4; the V takes 22-34) | `pole_strap_tie`, `pole_strap_band`, `remix.STRAP_SLOT_Z` |
| 25 | Base bond → pole | 14 AWG green from the SMA bulkhead's lug to a SatelliteSale SS-GSG9-1 strap | bonding lug | pole | README, ASSEMBLY.md |

---

## Print queue

Print the tests first, because two of them settle numbers the finals depend on.

1. **Rim test ring** (`rim-ring.stl`, about 1 h). Press the real lid on it and set `ring_fit`. This is the base's gate,
   not any loose part's, but it's the cheapest print that tells you the most.
2. **Base test coupon** (`coupon.stl`, about 2 h). Tune `slot_clear` with a card, try one printed lid bolt, check the
   lip on the corner, leak-test the patch. Set the M3 inserts you'll use everywhere and measure them (`insert_m3`).
   Every insert bore in this document follows that one number.
3. **EVM front clips** (`evm-clips.stl`, minutes). These only need the inserts in the base's keeper and lid-end block.
4. **TH and BARO bodies and lids** (`pod-th-*`, `pod-baro-*`, about 7 h in all). The model matches Clint's printed v1,
   so these are the safest pod prints. Try the Ø2.5 pilot and the Ø1.5 cord on the TH box first.
5. **UV crown body** (`pod-uv-body.stl`, about 5 h).
6. **Lid shade** (`lid-shade.stl`, about 6 h, white PETG). Print it once the lid is on with its printed bolts, so the
   first print checks the head clearance and the rib grip together.
7. **UV crown lid** (`pod-uv-lid.stl`, about 3 h) after the JGS1 disc arrives and `uv_window` is set from it.
8. **Retention bar**, once it has an export (see its section).
9. The remixed cap and arm, locally, after the pod boxes, since the boxes go on the arm before the cup does.

Don't print `rim-coupon.stl`, `rim-edge-long.stl`, `rim-edge-short.stl` or anything in `pods-r1/box/v1/`. They're kept as history.

---

## Checks run (2026-11-24)

| Command | Result |
|---|---|
| `python3 hardware/tx-stack-r1/sources.py --check` | README dimension table in step |
| `python3 hardware/tx-stack-r1/cage/cage.py` | cage PASS, STL gate closed on `l2_screw_pos`, `ring_fit` |
| `.venv-cad/bin/python cage.py --solid` | every solid valid: shell 457.1 cm³, left wall 34.7, right corner post 12.0, pads 0.9, retention bar 2.0, charger ledges 19.2, pack tray 21.7 |
| `.venv-cad/bin/python cage.py --ring --clip --shade --coupon` | all four STLs rewritten byte for byte (no git change), ring and coupon checks pass |
| `python3 hardware/pods-r1/sources.py --check` | README dimension table in step |
| `.venv-cad/bin/python hardware/pods-r1/box/podbox.py` | six STLs rewritten byte for byte (no git change) |
| `.venv-cad/bin/python -m unittest tests.test_pods_box tests.test_pods_v1` | 17 tests OK |
| `.venv-cad/bin/python -m unittest tests.test_pods_shield tests.test_pods_remix` | 15 tests OK |

The full `run.sh` scripts also rebuild the schematic, drawings and sheets. Those don't touch the printed parts, so
they weren't run for this document.

---

## Where the docs and the code disagree (the code wins)

1. **The retention bar has no STL path.** `cage.py`'s docstring ("`--stl` export STL: refused until the lid gate is
   sourced") and the TX README suggest `--stl` writes the base. `main()` only checks the gate and builds solids. No call
   writes the base or the bar, even when the gate opens.
2. **One EVM clip or two.** TX README, Mechanical connections, Charger row: "a clip at the front on two M3 screws".
   The code has two separate clips (`clip_boxes(0)`, `clip_boxes(1)`), one M3 x 8 each. ASSEMBLY.md has it right.
3. **Clip corners.** `clip_solid()`'s docstring says "its corners rounded off in plan". The code only unions two boxes
   and cuts the hole, so the corners are square.
4. **Gland "bosses".** ASSEMBLY.md 2.4: "Fit the glands in the bottom wall's bosses". The base has holes over 1 mm
   pockets in the inside face and, per `cage.py`, "No outside bosses".
5. **Mounting-flange slots.** TX README, Base to the pole: "two 3.45 x 13.95 slots (Xb 47.95 and 75.45)". `mount_flange`
   builds 3.5 x 14 slots at Xb 48 and 75.5.
6. **Vent hole.** The `enc_glands` row builds the vent hole at 12.5, while its own note says the enclosure 4 print measured
   12.46, and the README BOM says "Check its panel hole against 12.46 mm". The model and the print differ by 0.04, and
   the vent's real panel hole (`vent`, TBD) isn't known yet.
7. **Shade wall perimeters.** The `shade` row says "2.4 is six 0.42 mm perimeters". Six at 0.42 is 2.52, so 2.4 is
   nearer five and a bit (or six at 0.40).
8. **`podbox.py` docstring, UV.** It still describes the pre-crown UV box: the port gland "goes through that floor",
   two corner lugs at the gland's end keep their lid inserts, two floor bosses. The code has a round crown, the gland
   level through the drum wall, no lugs and four floor bosses on r 31. `CAD-BRIEF.md` matches the code.
9. **BARO baffle gap.** `CAD-BRIEF.md` asks for at least 2.5 of free gap round the baffle. `test_baro_vent_baffled`
   asserts at least 2.0. The model has 7.90, so both pass.
10. **Insert bore depth.** The same M3 insert (`insert_m3` 5.7 long) gets a 6.5 deep bore in the TX base (`bar_bore`,
    length + 0.8) and 6.7 in the pods (`pod_insert_bore`, length + 1.0). Not wrong, but they don't share a rule.
11. **cage.py's run list.** The docstring's Run section and the README's `cage.py` row list `--ring`, `--solid`, `--stl`
    and `--shade` (the README row only `--solid`, `--stl`, `--ring`). Neither lists `--clip` or `--coupon`, which
    ASSEMBLY.md uses.
12. **Ring spec.** `cage.py --ring` prints `SPEC INCONSISTENT: the short-side straight lip is 3 in from the outline,
    the spec's check says 3.25` (inside `lid-rim-spec.md`, its segment table against its stated check).
