# Harness run: protocol draft 2 (macOS, 2026-10-12)

`python -m ws0.harness` output that was committed with `d825c17` (Stage-0 board firmware, protocol draft 2).
It has 12 scenarios in the same layout as `../harness-macos-2026-10-12/`, plus `summary.json` and `report.html`.

Compared with `../harness-macos-2026-10-12/`:
- Every `trace.jsonl` differs, because the frame format changed. `result.json` is identical for 9 scenarios.
- Only the three noisy-link scenarios changed, and only their `rejected` counts: noisy-link-7 39 → 40,
  noisy-link-2026 32 → 31. Timely % is unchanged (noisy-link-73 is still 98.82 %, below 99 %).
- All 12 scenarios pass. 0 missing everywhere. `physical_H01` is `NOT RUN`.
