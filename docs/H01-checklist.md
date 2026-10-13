# H01 — physical data-path gate

**Status: NOT RUN.** Simulated observations cannot satisfy this gate.
Source of acceptance criteria: v0.2 section 3 Stage 0 and section 12 H01.

## Capture before testing

- Source revision, vendor/toolchain versions, binary hashes and configuration without keys.
- Board/sensor/BOM revisions; exact wiring, supply and current-measurement boundaries.
- Receiver host, antennas and intended placement including obstructions.
- Declared synchronized acquisition-time source, clock accuracy and report period.
- Raw receiver frames/logs, SQLite database and transmitter journal counters.
- MQTT/HA discovery, measurement availability and local API checks.

## Setup before the run

- **SHT45 wired and verified first:** a CRC-checked valid reading on the TX console, plus the
  unplug test (`sensor_fault`, then recovery). Without a sensor every reading is a
  `sensor_fault` and the verdict is FAIL by design (see `evidence/soak-a07f498-2026-10-13/`).
- **Secure the USB cables and run no debugger sessions during the run.** A USB dropout of about
  1 s makes the ST-LINK reset its board (`reset=pin`); a debugger session can also reset TX
  (`docs/hardware/nucleo-wl55jc-bringup.md`, "Office session"; failure mode E12 in
  `failure-modes.md`).
- If TX was wiped, it must have been provisioned with a **new** key (`docs/runbook-moving-boards.md`;
  gap G17 in `failure-modes.md`): a WIPE restarts the nonce counter.
- Do not run bench fault-injection commands (`TEST-HANG`, `TEST-FLASH-STORM`) on the boards under
  test during the placement run.
- Know the outage risk from probe back-off (`failure-modes.md` §3.3): after any outage of 3
  minutes or more, up to 14 more intervals can be late. This is an open risk for Clint to
  decide; it does not change the pass criteria below.

## Link check before the run (gap G15)

At the intended placements, record RSSI and SNR in **both** directions for at least 30
exchanges: uplink from `receiver.log` (`#rx obs`), downlink from the TX console (`#ack … rssi`).
Both boards print `power=` at boot and must match. If the downlink margin is more than 3 dB
worse than the uplink, fix the receiver antenna position before starting the 24-hour run.

## 24-hour placement test

Use one-minute observations, USB/bench power and the actual intended placements.
Schedule 1,440 intervals. At least **1,426** must arrive within 120 seconds of acquisition
(ceil(0.99 × 1440)). Count unique intervals, not packets or retransmissions. Unknown
acquisition time cannot prove latency. A **gateway-reconstructed** time (protocol draft 4,
protocol-stack.md 11.3.2) is a known time when it meets the 5 s tolerance; count it, and
report reconstructed intervals separately (decision by Clint, 2026-10-12). Publish missing, late, invalid-clock and
sensor-fault records as separate counts; do not silently exclude them.

Score the run with:

```
.venv/bin/python tools/h01_report.py --db <run-dir>/observations.sqlite3 --station <station name> \
    --start <UTC, e.g. 2026-10-15T00:00:00Z> --hours 24 --output evidence/h01-<date>
```

Always give `--db` and `--station` explicitly: the defaults (`run-hw/observations.sqlite3`,
`station-01`) may not match the run, and a wrong station scores 0 intervals. `--output` must be a
new directory (the tool refuses an existing one). The exit code is 0 for PASS and 1 for FAIL. It
applies these rules to the gateway database and writes `report.json` and `report.md`. The verdict
needs on-time **valid** readings; transport-only success (sensor-fault readings delivered on time)
is reported beside it, never instead of it. `invalid_clock_observations` counts observations, not
intervals.

Record the exact test interval and denominator. Report all intervals if injecting
faults in the same run. A dedicated separate fault-test phase can characterize recovery,
but must not be silently subtracted from the placement run's denominator.

## Restart and outage matrix

- Reboot transmitter, receiver and gateway independently.
- Confirm sample identities never collide and transmission nonces never repeat.
- Drop link; confirm sampling/journaling continues.
- At 180 seconds without a fresh valid reading, HA and API show unavailable.
- Restore link; live observations take precedence over backfill.
- Recover every successfully journaled observation without duplicate database rows.
- Lose an ACK after commit; retry must produce a new ACK and only one stored record.
- Inject sensor failure and unknown clock; represent readings honestly.
- Correct a clock error; a newer valid observation restores availability.
- Confirm broker outage/reconnect does not stop SQLite ingestion; confirm HA last-will.

## Decision

Pass only when placement latency, identity, time, restarts, stale state and recovery
all meet the specification. Save the full evidence set and freeze a reproducible
checkpoint before Stage 1. On failure: fix antenna placement, link settings and
buffering; if necessary relocate the receiver or select a better qualified module.
Retest; do not introduce mesh or lower the pass threshold.
