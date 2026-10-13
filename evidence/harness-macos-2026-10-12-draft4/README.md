# Harness run: protocol draft 4 (macOS, 2026-10-12)

`python -m ws0.harness` output that was committed with `a196203` (draft 4: gateway-reconstructed time from uptime,
and time trust across resets). It has 13 scenarios plus `summary.json` and `report.html`.

What changed compared with draft 3:
- **New scenario `reboot-during-outage`:** link down for minutes 20–80, node reboot at minute 50.
  32 samples had no clock; all 32 got a reconstructed time (`unresolved_time_samples` 0).
  Timely 95.83 % (1380/1440), maximum latency 3600 s. The latency miss is expected (`expect_latency_failure`).
  PASS.
- **New metrics:** `reconstructed_time_samples` and `unresolved_time_samples`. A reconstructed time within 5 s
  now counts as timely.
- **clock-errors:** 99.31 % → 99.65 % (1430 → 1435 timely; 6 samples reconstructed).
- Every scenario now has at least 1 unknown-clock sample, because samples taken after a
  node boot and before its first ACK have no clock (simulator.py:26-28). Examples: reboots 4, ack-loss 2. Every one of them is reconstructed.
- All 13 scenarios pass. 0 missing. noisy-link-73 (98.82 %), radio-outage (98.61 %) and reboot-during-outage
  stay below 99 %. `physical_H01` is `NOT RUN`.
