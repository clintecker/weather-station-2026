# Enclosure 4 audit (2026-11-17)

Clint's `~/Downloads/enclosure 4.stl` (Open CASCADE export, 106,190 triangles), checked against enclosure 3 and against
the model. The STL is not committed. Box frame as in `cage/cage.py`, from the STL's lid-centre frame:
Xb = 61.75 − Y, Yb = Z − 3, Zb = X + 84.75 (the same map as `../audit-enc3/sl.py`).

## Scripts

Run with `python3 -I` (numpy, scipy) or the CAD venv (matplotlib for `sec.py`), the STL path as the argument where
asked. They were run from a scratch folder; paths inside are that run's.

- `load.py`: reads a binary or ASCII STL.
- `vox_diff.py STL OUT.npz DIR`: voxelises a print at 0.5 mm in the box frame. `diff.py`: added and removed regions,
  enclosure 3 to 4. `sec.py`: the section images `sec1.png` to `sec3.png` (grey both, blue enclosure 4 only, red
  enclosure 3 only).
- `pl.py`: exact plane sections of the mesh (0.05 mm) and hole finding. `m1.py`: the bottom-wall and right-wall holes.
  `m2.py`: the tray, fin, ledges, flanges and slots along lines. `lip.py`: the tray lip's profile. `pg9.py`: room for
  the PG-9 locknuts. `pen.py`: the true overlap volume of items that touch.
- `fit/`: `../audit-enc3`'s fit check (`fit.py`, `sl.py`, `vox.py`) pointed at enclosure 4, with the EVM, the pack, the
  gland locknuts and the SMA bulkhead added; `fit_results.txt` is its output. It ran against the model as it stood
  before this audit's changes (it still names `m3_button` and the screw posts, and sets them aside).

## Findings

Changed from enclosure 3:

- **Backplane screw posts: removed** (both, with their inserts). Clint: the cards plugged into the backplane hold it.
  The groove rail now starts at Zb 67.0; the corner post's slot runs Zb 72.75 to 150.6; the three support pads stay.
- **Bottom wall:** five PG-7 holes, **Ø13.0** (were 12.0 undersize): G1-G3 and G5, G6. **G7 and both PG-9 holes are
  gone.** Vent Ø12.46 at (50, 85), unchanged. A 1 mm land (Zb 0 to 1) covers the inside from about Xb 80 to the right
  wall, and the right corner block's left face is at Xb 106.85 for Zb 0 to 8 (about 110 before).
- **SMA bulkhead moved:** right wall, Yb 94.14, Zb 60.38, Ø6.44, inner nut seat Ø14.2 (was Yb 86.14, Zb 144.6).
- **Mounting flanges** (new, replace the pole lugs): short ends, floor plane Yb −3 to 3, Xb 31.75 to 91.75, to Zb −31
  and 200.5, two 3.45 × 13.95 slots each at Xb 47.95 and 75.45 (centres Zb −18 and 187.5).
- **Shelves (new, as `cage/shelves-spec.md` v3):** tray Zb 21.4-24.4, Yb 0-58, Xb to 100.25, strap slots Xb 13.5-16.5
  and 89.5-92.5; left block under it; fin Xb 96.25-100.25, Zb 21.4-48.4, Yb 0-109; left ledge Xb 0-9.85, top Zb 48.4,
  Yb 13.85-109; right lid-end block Xb 102-121, Yb 101.75-109, Zb 38.4-48.4; M3 keeper bores Ø4 at (4.5, 106) and
  (100.25, 106), Zb 40-48.4.

Fit (`fit/fit_results.txt`, `pen.py`):

- Cards, backplane, plugs, socket tails, mux: clear, at least 1.85 (B3's SHTC3 to the left wall), as in enclosure 3.
- EVM: rests on its ledges (its underside box overlaps only the ledge strips under its edges, by design); its parts
  above the board, J8 and the SMA bulkhead's inside: clear.
- PG-7 locknuts: seated on the wall, clear.
- **Pack: not clear.** The lip is a 45° ramp from Yb 50 (Zb 24.4) to Yb 56 (Zb 30.4), flat to 58, as the shelves spec
  then asked. The pack (54 deep, Yb 2 to 56) overlaps it by 1197 mm³: its front edge rides 4 up the ramp, its top then
  into the EVM's underside zone.

## Fixes asked of Clint ("enclosure 4 + fixes", modelled in the repo)

1. **Tray lip:** extend the tray to Yb 62 and start the 45° ramp at Yb 56, rising to Zb 30.4 at Yb 62.
2. **PG-9 holes back:** Ø15.5 at (Xb 98, Yb 25) and (98, 60); the right corner block back to Xb ≥ 110 for Zb 0 to 8, and
   the 1 mm land cut away inside each Ø24 locknut keep-out (Zb 0 to 8).

## Session 6 checks [TBD-MEASURE]

- ~~The coax too short~~: resolved, Clint 2026-11-17: the 6 inch cable fits the low bulkhead (it was worse at the old
  high one, bending the cable to fit).
- A straight plug on the bulkhead's inner end reaches about Xb 93, about 6-10 above the EVM's lid-right corner (board
  to Xb 98.25, Yb 101.6). Check it clears, or use a right-angle plug.

Re-audit the next STL with the same scripts.

## The model against enclosure 4 (2026-11-17)

`cage/cage.py` now builds the base as enclosure 4 + the two fixes (`shell_solid()`, the parts' `solid` callables).
`python cage.py --audit-stl OUT.stl` (CAD venv) writes the shell and every moulded part (not the retention bar, a
separate print) as one STL in the box frame. `vox_model.py OUT.stl model.npz DIR` voxelises it on the same 0.5 mm grid
as `vox_diff.py`; `model_diff.py v4.npz model.npz` lists the regions in one and not the other (opened by one voxel to
drop face skins) over 20 mm³; `classify.py` sorts them. Result (`model_diff.txt`): 544,094 mm³ printed, 546,289
modelled; 67 regions over 20 mm³, every one explained:

| Group | Regions | mm³ | Why |
|---|---|---|---|
| fix 1, enclosure 4 only | 1 | 1953 | the old lip ramp from Yb 50 (Xb 16.5-89.5, Zb 24.4-30.4) |
| fix 1, model only | 1 | 2217 | the tray to Yb 62 and the ramp from Yb 56 |
| fix 2, enclosure 4 only | 2 | 2531 | the PG-9 holes and their Ø24 cuts to Zb 8 at (98, 25) and (98, 60) |
| outside faces, enclosure 4 only (model solid) | 64 | 2823 | debossed lettering and marks 1 mm deep: left wall (13 identical 32 × 5 recesses every 12 mm at Yb 7-39, lettering at Yb 61-89), right wall (Yb 65-85), top wall (Yb 25-92), bottom wall (Yb 98-110). Not modelled |

What the model now carries, from the STL (`sources.py`: enc_inside, enc_outer_r, enc_blocks, enc_lid_bores, enc_lip,
enc_pockets, enc_glands, enc_sma_seat, mount_flange; the shelf and post numbers in `cage.py`):

- Outside Xb −3..126.5, Zb −3..172.5, R9 corners; floor Yb −3..0; walls to Yb 117; long walls 4.25 (inside faces Xb
  1.25 / 122.25), short walls 4.0 (Zb 1 / 168.5). The frame (W × H 123.5 × 169.5, the lid outline less 3) is kept.
- Four corner blocks 15.4 square from the inside faces, floor to wall top, R8 inner corner, R2.5 fillets to the walls
  (none at the bottom-left block's foot along P1); Ø10 bores from Yb 80.75, 45° chamfer to Ø14.6 at the top, at the
  lid's screw positions. **Ø10 is not the Ø5.6 an M4 heat-set insert wants** (`cage.py` prints a FLAG).
- The 2 × 2.5 lip on the inside edge (walls and block faces).
- Bottom wall: 1 mm pockets P1-P3 with 45° roofs (P2 narrows at 45° from Yb 64.5 to the vent's 8 mm land), PG-7 Ø13 ×
  5, vent Ø12.5, fix 2 PG-9 Ø15.5 × 2 with Ø24 cuts to Zb 8. Teardrop tops on the holes are not modelled (they lift the
  centroids 0.2; centres stay 25 / 60 / 85).
- SMA Ø6.44 at Yb 94.14, Zb 60.38, Ø14.2 seat 1.0 into the right wall. Flanges as `mount_flange`, R8 corners, slots,
  a 7 mm 45° gusset each.
- EVM ledge chamfered under, back end 45° in plan, tail notches with 45° front ends; left keeper (45° roof) and right
  lid-end block (V back edge) to Yb 109 with Ø4 × 6.5 clip insert bores; fin Yb 0-109; tray with two 3 × 20 strap
  slots and a support block Xb 1.25-12, Zb 16.4-21.4.
- The right corner post's front cut back over B2 and B1 (Yb 15.15 to its front, from the lower card's top face to 2
  below the next slot, stepped to Xb 89.6 down to the slot roof).
- The retention bar now starts at the real left wall, Xb 1.25-12 (it was 0-12 in the lid frame).

