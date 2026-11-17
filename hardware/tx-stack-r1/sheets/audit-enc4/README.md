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

- The coax (Amphenol 135110-01-06.00, about 110 between its plugs) from AD1 on B3 (Zb about 140) down the right column
  to the bulkhead at Zb 60: the route is about 120-130. Probably too short.
- A straight plug on the bulkhead's inner end reaches about Xb 93, about 6-10 above the EVM's lid-right corner (board
  to Xb 98.25, Yb 101.6). Check it clears, or use a right-angle plug.

Re-audit the next STL with the same scripts.
