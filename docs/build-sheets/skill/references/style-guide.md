# Style guide

The look is "cyberpunk flat-pack": furniture instructions from a dystopia that cares a lot about your solder joints. The numbers below are the worked example's (`sheetlib.py` and `r3d.py` in weather-station-2026). Change the palette for a new project if you like, but keep the roles.

## Page

- US Letter, 612 x 792 pt, 30 pt margin.
- Paper background `#EEECE6`. Panels are white with a 1.4 pt ink border.
- Header: a black band 92 pt tall across the top. On the left, a hazard-yellow block with the step number in a 54 pt condensed bold face. Beside it, the title in white (34 pt, shrunk until it fits) and a subtitle in yellow mono (9 pt, shrunk to no less than 8 pt).
- Top right of the band: the protocol line (`PROTOCOL 02 // SESSION 2 // B4 POWER`) and the unit name, 8 pt grey mono.
- Under the band: an 8 pt hazard stripe, black diagonals on yellow, 16 pt period.
- Footer: a thin rule at 34 pt, the slogan at the left in 8 pt mono, the page number at the right.

## Colour roles

| Token | Hex | Role |
|---|---|---|
| PAPER | `#EEECE6` | page background |
| INK | `#121212` | lines, text, leaders |
| HAZ | `#FFD400` | hazard yellow: the thing you work on, step numbers |
| NEON | `#FF2E88` | magenta: measure, critical, warnings, hole names |
| WHITE | `#FFFFFF` | chips, panels, leader halos |
| GREY | `#7A7A7A` | page furniture |

Wire colours on the page match the real insulation: red `#D7262E`, black `#1C1C1C`, yellow `#E0B000`, blue `#2D6FD0`, green `#2E9A48`. Draw a board in its real colour. The SolderFul card is red `#C42A2E` with gold `#D9AE3F` pads. Adafruit breakouts are `#25283A`.

## Fonts

Three faces: a condensed bold for titles and step numbers, a rounded bold for chips, and a mono for captions, the subtitle and the footer. The worked example uses DIN Condensed Bold, DIN Alternate Bold and Andale Mono from the macOS system fonts. Minimum sizes: 9 pt for a label, 8 pt for fine print, 12 pt for a key value.

## Panels

- A page is a grid of panels (`Grid(cols, rows, heights=...)`).
- Each panel has a black numbered badge (13 pt radius) in its top-left corner. No text or art may enter the badge's corner.
- The caption sits at the bottom of the panel in 9 pt mono, under a light rule. Write it as instructions, with the board and the face first: "B4 POWER, UNDERSIDE (row J toward you). ..."
- A warning panel has a 2.2 pt magenta border and magenta caption text.
- A face tag ("TOP FACE", "UNDERSIDE") sits in yellow on black at the top left of a board picture.

## Pictures

- Orthographic projection only. No perspective.
- Hidden lines removed by OpenCascade. Line weights: 0.55 pt for edges, 0.45 times that for edges shorter than 7 pt, 1.3 times for silhouettes, and a 1.1 pt outline around each part's visible area.
- Three flat tones per colour (1.0, 0.86 and 0.72 of the base colour), picked by the face normal against a light from the upper left. No gradients, no shadows, no texture.
- Silkscreen and hole letters are decals on the board face. They are drawn only where that face is the visible one.
- A zoom is a circle-clipped close-up with a thin line back to a small circle on the overview (`zoom_link`, used in Session 1).

## Labels

- Every label is a white chip with 2.6 pt padding. Text inside is the label font, ink or magenta.
- A leader starts where the line from the chip centre to the target crosses the chip edge. It ends on a dot (1.6 pt, on a 2.6 pt white halo).
- Each leader is a 1.0 pt line on a 2.6 pt white halo. On a red or busy board, make every leader black.
- Dimensions are magenta lines with arrowheads and end ticks. The value sits on a chip that breaks the line.
- Put chips in lanes beside the picture, not on top of it, wherever the panel has room.

## Words

- Holes as printed: E10 means row E, column 10. Rails get a name and a column ("+ RAIL 22").
- Wires: number, from, to, cut length, bends, colour and role. "1 F1 TO + RAIL 1, 40 MM CUT, STRAIGHT, RED 3.3 V".
- Parts: reference, maker part number and what it does. "U2 INA228, Adafruit #5832".
- Standing orders on the cover: how the sheet names holes, which face is TOP, what not to power.
- Slogans: short, deadpan, slightly ominous, and true. "A WIRE UNDER A PART CANNOT BE FIXED LATER." "THE BAND IS THE CATHODE. THE CATHODE IS THE LAW."
- End every board with a "meter before power" page: a table of continuity checks, each with BEEP or NO BEEP, and a box to tick. Tell the reader to stop, photograph and report if one fails.
