# Harness run: protocol draft 3 (macOS, 2026-10-12)

`python -m ws0.harness` output that was committed with `e3da38b` (draft 3: impossible fillers for invalid sensor readings).
It has 12 scenarios plus `summary.json` and `report.html`.

The results match `../harness-macos-2026-10-12-draft2/`: the same timely %, rejection counts and pass verdicts.
The traces differ from the first macOS run (`../harness-macos-2026-10-12/`) because the wire encoding changed.
All 12 scenarios pass. 0 missing. `physical_H01` is `NOT RUN`.
