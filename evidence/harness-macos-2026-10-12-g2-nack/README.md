# Harness run: G2 authenticated NACK (macOS, 2026-10-12)

`python -m ws0.harness` output that was committed with `19c4049` (G2: authenticated NACK for permanent rejections).
It has 13 scenarios plus `summary.json` and `report.html`.

What changed compared with `../harness-macos-2026-10-12-draft4/`:
- **New `nacks` counter.** In identity-collision, the altered frame is now answered with a NACK: `nacks` 1,
  `rejected` 1 → 0, `ack_sent` 1440 → 1441. Its trace has 7204 events, against 7202 before.
- Timely % and pass verdicts are unchanged in every scenario. `nacks` is 0 everywhere else.
- All 13 scenarios pass. 0 missing. `physical_H01` is `NOT RUN`.
