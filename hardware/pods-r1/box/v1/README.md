# Pod boxes v1 (the printed ones)

These six STLs are the v1 pod boxes: the files Clint prints. His CAD agent made them on 2026-11-18 from
[`../CAD-BRIEF.md`](../CAD-BRIEF.md).

| File | Part |
|---|---|
| `pod-th-body.stl`, `pod-th-lid.stl` | TH box: sealed, two PG-7 glands |
| `pod-baro-body.stl`, `pod-baro-lid.stl` | BARO box: one PG-7, the 4 mm vent with its ePTFE seat and baffle |
| `pod-uv-body.stl`, `pod-uv-lid.stl` | UV box: floor gland, window recess in the lid |

They're in print orientation, in the same frame as `../stl/` (the model's own export): body back face on the bed,
lid groove face on the bed.

## What v1 changed from the brief's reference model

We diffed each part against the reference (boolean subtraction both ways, 2026-11-18). Everything else is the same
to 0.01 mm.

- Every corner lug has two flat webs that join it to the walls. Each web is parallel to the corner's diagonal and
  tangent to the lug, so the notch between the lug and the rounded corner is filled. About 117 mm3 per lug on a body.
- Every lid has a 0.8 mm chamfer round its top outer edge (the face away from the O-ring groove).
- The BARO vent hole and its ePTFE seat are teardrops pointing up in print, like the gland holes.

`../podbox.py` now builds the same three features, so the sheets draw v1. `tests/test_pods_v1.py` checks that the
model and these files differ by less than 20 mm3 per part in each direction (7.7 mm3 at most on import, all of it
tessellation).

Still assumed in v1: the heat-set insert (5.7 long x 4.6 knurl, so bores 4.0 x 6.7) and the O-ring cord (1.5).
Measure both before a big print run; if either changes, the bores or the groove change and v1 needs a new revision.
