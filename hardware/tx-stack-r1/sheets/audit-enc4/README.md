# Enclosure 4 audit (2026-11-17)

This audit checks Clint's `~/Downloads/enclosure 4.stl` against enclosure 3 and against the model. The STL is an Open
CASCADE export with 106,190 triangles, and it isn't committed. The box frame is the one in `cage/cage.py`. It maps from
the STL's lid-centre frame like this: Xb = 61.75 − Y, Yb = Z − 3, Zb = X + 84.75 (the same map as `../audit-enc3/sl.py`).

## Scripts

Run them with `python3 -I` (numpy, scipy) or the CAD venv (`sec.py` needs matplotlib). Pass the STL path as the
argument where a script asks for it. I ran them from a scratch folder, so the paths inside them are that run's paths.

- `load.py`: reads a binary or ASCII STL.
- `vox_diff.py STL OUT.npz DIR`: voxelises a print at 0.5 mm in the box frame.
- `diff.py`: lists the added and removed regions from enclosure 3 to enclosure 4.
- `sec.py`: draws the section images `sec1.png` to `sec3.png`. Grey is in both, blue is enclosure 4 only, red is
  enclosure 3 only.
- `pl.py`: cuts exact plane sections of the mesh (0.05 mm) and finds holes.
- `m1.py`: measures the bottom-wall and right-wall holes.
- `m2.py`: measures the tray, fin, ledges, flanges and slots along lines.
- `lip.py`: gives the profile of the tray lip.
- `pg9.py`: checks the room for the PG-9 locknuts.
- `pen.py`: gives the true overlap volume of items that touch.
- `fit/`: this is `../audit-enc3`'s fit check (`fit.py`, `sl.py`, `vox.py`) pointed at enclosure 4. I added the EVM,
  the pack, the gland locknuts and the SMA bulkhead. `fit_results.txt` is its output. It ran against the model as it
  was before this audit's changes. That's why it still names `m3_button` and the screw posts, and sets them aside.

## Findings

Changed from enclosure 3:

- Backplane screw posts: removed (both, with their inserts). Clint says the cards that plug into the backplane hold it.
  The groove rail now starts at Zb 67.0. The corner post's slot runs from Zb 72.75 to 150.6. The three support pads
  stay.
- Bottom wall: there are five PG-7 holes (G1-G3, G5 and G6) at **Ø13.0**. They were 12.0 before, which was undersize.
  **G7 and both PG-9 holes are gone.** The vent is Ø12.46 at (50, 85), the same as before. A 1 mm land (Zb 0 to 1)
  covers the inside from about Xb 80 to the right wall. For Zb 0 to 8, the right corner block's left face is now at
  Xb 106.85 (it was about 110).
- SMA bulkhead: moved to the right wall at Yb 94.14, Zb 60.38, Ø6.44, with an inner nut seat of Ø14.2. It was at
  Yb 86.14, Zb 144.6.
- Mounting flanges: these are new, and they replace the pole lugs. They sit on the short ends in the floor plane,
  Yb −3 to 3 and Xb 31.75 to 91.75. They reach Zb −31 and 200.5. Each flange has two 3.45 × 13.95 slots at Xb 47.95 and 75.45
  (centres Zb −18 and 187.5).
- Shelves: new, as in `cage/shelves-spec.md` v3.
  - Tray: Zb 21.4-24.4, Yb 0-58, Xb to 100.25. Strap slots at Xb 13.5-16.5 and 89.5-92.5. A left block sits under it.
  - Fin: Xb 96.25-100.25, Zb 21.4-48.4, Yb 0-109.
  - Left ledge: Xb 1.25-9.85 (from the left wall's inside face), top at Zb 48.4, Yb 13.85-109.
  - Right lid-end block: from Xb 102 to the right wall (inside face Xb 122.25), Yb 101.75-109 (at Xb 110, because the
    back edge is a V), Zb 38.4-48.4.
  - M3 keeper bores: Ø4 at (4.5, 106) and (100.25, 106), Zb 41.9-48.4 (6.5 deep).

Fit (`fit/fit_results.txt`, `pen.py`):

- Cards, backplane, plugs, socket tails, mux: clear, as in enclosure 3. The card and backplane slabs sit in their
  slots (0.01). The XH headers and the backplane socket bodies are 0.56 from the left wall. The socket tails behind the
  backplane are 1.35 from the wall, and B3's SHTC3 is 1.85. The plugs and the mux are over 2.
- EVM: it rests on its ledges. Its underside box overlaps only the ledge strips under its edges, and that's by design.
  Its parts above the board, J8 and the inside of the SMA bulkhead are clear.
- PG-7 locknuts: they sit on the wall and they're clear.
- **Pack: not clear.** The lip is a 45° ramp from Yb 50 (Zb 24.4) to Yb 56 (Zb 30.4), then flat to Yb 58. That's what
  the shelves spec asked for at the time. The pack (54 deep, Yb 2 to 56) overlaps the lip by 1197 mm³. Its front edge
  rides 4 up the ramp, and that pushes its top into the EVM's underside zone.

## Fixes asked of Clint ("enclosure 4 + fixes", modelled in the repo)

1. Tray lip: extend the tray to Yb 62. Start the 45° ramp at Yb 56 so that it rises to Zb 30.4 at Yb 62.
2. PG-9 holes back: put Ø15.5 holes at (Xb 98, Yb 25) and (98, 60). Move the right corner block back to Xb ≥ 110 for
   Zb 0 to 8. Cut the 1 mm land away inside each Ø24 locknut keep-out (Zb 0 to 8).

## Session 6 checks [TBD-MEASURE]

- ~~The coax too short~~: resolved. Clint confirmed on 2026-11-17 that the 6 inch cable fits the low bulkhead. It was
  worse at the old high bulkhead, where he had to bend the cable to make it fit.
- A straight plug on the bulkhead's inner end reaches about Xb 93. That's about 6-10 above the EVM's lid-right corner
  (the board runs to Xb 98.25, Yb 101.6). Check that it clears, or use a right-angle plug.

Re-audit the next STL with the same scripts.

## The model against enclosure 4 (2026-11-17)

`cage/cage.py` now builds the base as enclosure 4 plus the two fixes (`shell_solid()` and the parts' `solid`
callables). To compare the model with the print:

1. Run `python cage.py --audit-stl OUT.stl` in the CAD venv. It writes the shell and every moulded part as one STL in
   the box frame. It leaves out the retention bar, because that's a separate print.
2. Run `vox_model.py OUT.stl model.npz DIR`. It voxelises the STL on the same 0.5 mm grid as `vox_diff.py`.
3. Run `model_diff.py v4.npz model.npz`. It lists the regions over 20 mm³ that are in one and not the other. It opens
   them by one voxel first to drop face skins.
4. Run `classify.py` to sort the regions.

The result is in `model_diff.txt`: 544,094 mm³ printed and 546,289 mm³ modelled. There are 68 regions over 20 mm³
(3 in enclosure 4 only, 65 in the model only), and every one has a reason:

| Group | Regions | mm³ | Why |
|---|---|---|---|
| fix 1, solid in enclosure 4 only | 1 | 1953 | the old lip ramp from Yb 50 (Xb 16.5-89.5, Zb 24.4-30.4) |
| fix 1, solid in the model only | 1 | 2217 | the tray to Yb 62 and the ramp from Yb 56 |
| fix 2, solid in enclosure 4 only | 2 | 2531 | the PG-9 holes and their Ø24 cuts to Zb 8 at (98, 25) and (98, 60) |
| outside faces, solid in the model only (recessed in enclosure 4) | 64 | 2823 | debossed lettering and marks 1 mm deep: left wall (13 identical 32 × 5 recesses every 12 mm at Yb 7-39, lettering at Yb 61-89), right wall (Yb 65-85), top wall (Yb 25-92), bottom wall (Yb 98-110). Not modelled |

The model takes these numbers from the STL. They're in `sources.py` (enc_inside, enc_outer_r, enc_blocks,
enc_lid_bores, enc_lip, enc_pockets, enc_glands, enc_sma_seat, mount_flange), and the shelf and post numbers are in
`cage.py`.

- Shell: the outside is Xb −3..126.5, Zb −3..172.5, with R9 corners. The floor is Yb −3..0, and the walls go up to
  Yb 117. The long walls are 4.25 thick (inside faces Xb 1.25 / 122.25). The short walls are 4.0 (Zb 1 / 168.5). The
  model keeps the frame (W × H 123.5 × 169.5, which is the lid outline less 3).
- Corner blocks: there are four, each 15.4 square from the inside faces, from the floor to the wall top. Each has an
  R8 inner corner and R2.5 fillets to the walls. The bottom-left block has no fillet at its foot along P1.
- Lid bores: each corner block has a Ø10 bore at the lid's screw position. The bore starts at Yb 80.75 and has a 45°
  chamfer to Ø14.6 at the top. An M4 heat-set insert wants Ø5.6, not Ø10, but these bores don't take inserts. They
  take Clint's 3D-printed lid bolts (`cage.py:857`, `sources.py` lid_screw_opt c). `cage.py` doesn't print a FLAG
  about them.
- Lip: 2 × 2.5 on the inside edge (the walls and the block faces).
- Bottom wall: 1 mm pockets P1-P3 with 45° roofs. P2 narrows at 45° from Yb 64.5 to the vent's 8 mm land. It has the
  PG-7 holes (Ø13 × 5), the vent (Ø12.5) and the fix 2 PG-9 holes (Ø15.5 × 2, with Ø24 cuts to Zb 8). The model
  leaves out the teardrop tops on the holes. They lift the centroids by 0.2, and the centres stay at 25 / 60 / 85.
- SMA: Ø6.44 at Yb 94.14, Zb 60.38, with a Ø14.2 seat 1.0 into the right wall.
- Flanges: as `mount_flange`, with R8 corners, the slots and a 7 mm 45° gusset on each.
- Shelves: the EVM ledge has a chamfer underneath. Its back end is 45° in plan, and its tail notches have 45° front
  ends. The left keeper (45° roof) and the right lid-end block (V back edge) run to Yb 109, with Ø4 × 6.5 clip insert
  bores. The fin runs Yb 0-109. The tray has two 3 × 20 strap slots and a support block at Xb 1.25-12, Zb 16.4-21.4.
- Right corner post: its front is cut back over B2 and B1. The cut runs from Yb 15.15 to the post's front. It goes from
  the lower card's top face to 2 below the next slot, stepped to Xb 89.6 down to the slot roof.
- Retention bar: it now starts at the real left wall, Xb 1.25-12 (it was 0-12 in the lid frame).
