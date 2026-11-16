# Enclosure 2: shelves build spec (pack tray and charger ledges)

Enclosure 2 has no bottom shelves yet. This spec adds the two that `cage/cage.py` models below the cards: the
**pack tray** (the battery lies on it) and the **charger ledges** (the BQ25798EVM slides in on them). Every
dimension is in mm. The numbers come from `cage/cage.py` (`parts()` and `contents()`), 2026-11-13; the pack and
tray moved 12.5 right on 2026-11-16 to clear enclosure 3's bottom-left corner block (Xb 0–16.5, Zb 0–16.4). Apply this
**after** the mirror in `backplane-mount-spec.md` (step 0): every position here describes the mirrored box.

## Coordinate frame

The same as `backplane-mount-spec.md`. Look into the open base from the lid side, glands at the bottom:

- **Xb** runs from the inside face of the **left** wall (the card block and the retention bar) to the right (the
  corner post, the SMA wall), left to right as you look in. Inside width 123.5.
- **Zb** runs up from the inside face of the **bottom** wall (the glands). Inside length 169.5.
- **Yb** runs from the inside face of the **floor** (the back, on the pole) toward the lid. The seam is at Yb 97.0.
- **Lid-centre frame** (the CAD bot's): **X = Zb − 84.75, Y = 61.75 − Xb, Z = Yb + 3.0**. +Y is the left wall.

Each shelf is a flat plate across Xb and Yb, so "height" below means Zb (up the box as it hangs).

## What to add to enclosure 2

1. **Add the pack tray:** a plate **Xb 16.5 to 89.5, Yb 0 to 58.0, Zb 9.9 to 11.9** (2.0 thick). It is moulded to the
   floor along its back edge (Yb 0) and to the bottom-left corner block's right face (Xb 16.5).
   - Lid frame: Y +45.25 to −27.75, Z 3.0 to 61.0, X −74.85 to −72.85.
2. **Add the pack tray's front lip:** **Xb 16.5 to 89.5, Yb 56.0 to 58.0, Zb 11.9 to 17.9** (6 high). It stops the
   pack sliding toward the lid.
   - Lid frame: Z 59.0 to 61.0, X −72.85 to −66.85.
3. **Add two strap slots** through the tray for a hook-and-loop strap over the pack: 20 × 3, at Xb 22.5 and 83.5 (just
   outside the pack's ends), centred at Yb 29. *These slots are my call; the model doesn't draw them.*
4. **Add the left charger ledge:** **Xb 0 to 8.75, Yb 0 to 94.0, Zb 33.9 to 35.9**, moulded to the left wall and to the
   floor.
   - Lid frame: Y +61.75 to +53.0, Z 3.0 to 97.0, X −50.85 to −48.85.
5. **Add the right charger ledge:** **Xb 94.75 to 98.75, Yb 0 to 94.0, Zb 33.9 to 35.9**, on a rib (step 6). It does
   not reach the right wall.
   - Lid frame: Y −33.0 to −37.0, Z 3.0 to 97.0, X −50.85 to −48.85.
6. **Add the right ledge's rib:** **Xb 94.75 to 98.75, Yb 0 to 2.0, Zb 11.9 to 33.9**, standing on the floor under the
   ledge's back end.
   - Lid frame: Y −33.0 to −37.0, Z 3.0 to 5.0, X −72.85 to −50.85.
   - The model has only this 2-deep rib. If the ledge sags when printed, add a 45° gusset under it, but stay out of
     the keep-outs below.
7. **Add a back stop for the charger** on each ledge: a block 2.0 long (Yb 9.6 to 11.6), the ledge's width, 3.0 tall
   above the ledge top (Zb 35.9 to 38.9). The board's back edge stops at Yb 11.6, 2.0 in front of the backplane's
   component face (Yb 9.6). *The model gives that position, not the block; the block is my call.*
8. **Retention at the front:** the model notes "a snap clip at the front" but does not draw it. The board reaches Yb
   101.6, past the ledges' ends (Yb 94.0) and past the seam. The simplest design that fits is a printed latch tab on
   each ledge's front end, pressing down on the board's top face. *Design it to suit; it must stay below Yb 94.0 and
   out of the rim keep-outs.*

## What sits on them

| Item | Box frame (Xb, Yb, Zb) | Lid frame (Y, Z, X) | Source |
|---|---|---|---|
| Battery pack #353, lying flat | 18.5–87.5, 2.0–56.0, 11.9–29.9 | +43.25 to −25.75, 5.0–59.0, −72.85 to −54.85 | pack 69 × 54 × 18, sourced |
| BQ25798EVM board and parts above | 6.75–96.75, 11.6–101.6, 35.9–52.5 | +55.0 to −35.0, 14.6–104.6, −48.85 to −32.25 | evm 90 × 90 × 15 `[TBD-MEASURE]` |
| EVM underside (J6 micro-B, tails) | 6.75–96.75, 11.6–101.6, 31.9–35.9 | as above, X −52.85 to −48.85 | evm_under 4.0 `[TBD-MEASURE]` |
| EVM J8 (I2C lead, toward the lid) | 36.75–51.75, 101.6–107.6, 35.9–45.9 | +25.0 to +10.0, 104.6–110.6, −48.85 to −38.85 | evm_j8 6.0, sourced |

- The EVM rests 2.0 onto each ledge (its edges at Xb 6.75 and 96.75). Its Bumpon feet come off. It has no mounting
  holes.
- **Measure the EVM** (`[TBD-MEASURE]`): its outline, the tallest part above the board, and how far J6 and the solder
  tails reach below it. The underside parts must clear both ledges. If J6 sits over a ledge, notch that ledge.

## Keep-outs (nothing of these shelves goes here)

- **Gland locknuts** (`external-openings-spec.md`): a cylinder above each gland's inside seat, up to **Zb 8.0**: Ø19
  for the PG-7s at Xb 26, 50 and 74, Ø24 for the PG-9s at Xb 98, in the rows at Yb 25 and 60. The tray's underside
  (Zb 9.9) is 1.9 above them. The right rib (Yb 0 to 2) and the ledges (from Zb 11.9) are clear of all of them.
- **The vent** at (Xb 50, Yb 85): its inside nut cylinder must be clear too. The tray ends at Yb 58.
- **Backplane screw posts:** bottom right Ø7 at **(Xb 86.63, Zb 54.06)**, bottom left Ø8 at (7.78, 54.06), both Yb 0 to
  8.0. Both are above the ledges (top Zb 35.9). Their M3 heads reach Yb 11.25, **0.35** from the EVM's envelope at
  Zb 50.56 to 52.5 (the right one) `[TBD-MEASURE: the EVM's height]`.
- **The backplane** itself: its bottom edge is at Zb 48.71, Yb 8.0 to 9.6. The EVM is 2.0 in front of it (Yb 11.6).
- **B4**, the lowest card: its underside and solder tails start at Zb 77.6. The EVM's top (Zb 52.5) is well below.
- **Corner insert posts** (lid screws): Xb 0 to 13.05 and 110.45 to 123.5, Zb 0 to 13.05, Yb 77 to 94. The tray ends at
  Yb 58, so it clears them.
- **The rim lip and the corner lands:** Yb 94.0 to 97.0 all round. The ledges stop at Yb 94.0.

## Checks (`cage/cage.py` main)

- Each content (the pack, the EVM, J6 and the tails, J8) keeps 2.0 from every wall, keep-out, cage part and the
  other.
- The EVM is 2.0 in front of the backplane's lower end, and 2.0 below B4's underside.
- No two gland nuts are closer than their radii plus 1.0.
