# Pitfalls

Each item happened in the worked example (weather-station-2026). The commit or file is in brackets.

## Rendering

- A process that renders many scenes can segfault partway and still exit 0. Render one scene per process. Then check that each expected SVG exists and is not empty. [every `render_all.sh`]
- OpenCascade hidden-line removal crashes on a triangle mesh made into faces. For a mesh (an STL or 3MF from a printing site), use a depth-buffer renderer with the same SVG and JSON output. [`hardware/pods-r1/sheets/mrender.py`]
- Hidden-line output leaves small gaps where a silhouette meets an edge. Without a snap step, a region never closes and gets no fill. [`r3d.py`, `snap`]
- A large face can take the colour of a small part whose outline did not close, because one sample point landed on the part. Vote over several points in each large region. [`01e507a`]
- A map from a left-handed frame mirrors the picture without any error. Declare every frame map and refuse a negative determinant. [`handed.py`, layout check L12]
- A leader anchor can sit behind another part, so the leader points at the wrong thing. Check that each anchor is visible on the part that it names. [`Scene.anchor(on=...)`]
- Decal text on a cropped render can run past the crop. Clip the picture to its box. [`session4/sheetlib.py`]
- A scene module that routes every wire on import is slow. Session 3's `list` took about 3.5 minutes. Cache the routing result, keyed by a hash of every source file it reads. [`scenes4.py`, `_routes()`]

## Geometry and parts

- A maker STEP can leave out a factory-fitted part, or you can drop it to tidy the picture. The INA228 breakout's green X1 terminal block was missing, and that hid a real clash with the next card's header tails. Draw every board as supplied. Add a removal step. Run the clash check with the part fitted. [`304e308`]
- A lead soldered to a breakout pad looked "jammed into a port". Draw a pad lead as a solder joint, and route it round the breakout's own sockets. [`c4f9a70`]
- The first padboard model drew every other row of pads square. Photos of the real board showed square pads on every fifth line and row. Check each board model against a photo. If the copper pattern is not symmetric, name the face by its printed legend. [`10d391b`]
- A breadboard-style card was drawn with loose pads. Draw the strips joined as on the real card, so the reader sees which holes connect. [`01e507a`]

## Text and data

- A page script that types hole names or lengths drifts from the build list. Parse the build list and cross-check it against the layout model when the scene module loads. [`b2md.py`, `b3md.py`]
- A vague noun stops the builder. "Under the card" with four same-looking cards on the bench caused a question. Name the board, the face, the hole and the wire every time.
- An untraced number looks as sure as a measured one. Keep every value in the facts table with a status, and print `[TBD-MEASURE]` on any label that shows a TBD value.

## Builds and environments

- Two sessions printed label issues but failed only on hole issues. Make every check fail the build. [`session1/v2/make_session1_v2.py`, `session2/make_session2.py`]
- Shared pictures copied by hand into each session folder went stale, and nothing rendered them again. Render shared scenes into each session's own folder from one function. [`scenes5.py`, `_shared`]
- Scripts that hold absolute paths, and a default venv inside a temporary scratch folder, break on the next machine or session. Use repo-relative paths, repo-local venvs, an `env.sh` that prints a loud WARNING, and a setup script. [`3b6cebd`, `hardware/pods-r1/sheets/env.sh`]
- Fonts from one operating system's font folder tie the layout step to that system. Name the font files in one place and fail early with a clear message when one is missing.
- A test that counts pages in a manifest can pass when the PDF is short. Count the page objects in the PDF itself too. [`tests/test_pods_sheets.py`, `pdf_page_count`]
- A model or mesh with an unknown licence must not reach git. Keep its renders and PDF in gitignored folders, and say so in the README. [pods-r1 Session Q]

## Review

- The checks find overlaps and offsets. They do not find a wrong part, a confusing caption or a leader on the wrong but visible part. Render every page to PNG and examine each one before you hand the sheet over.
- The person at the bench is the last check. Ask for photos and measurements, apply the corrections, and rebuild.
