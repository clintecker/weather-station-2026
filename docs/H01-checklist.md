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

## 24-hour placement test

Use one-minute observations, USB/bench power and the actual intended placements.
Schedule 1,440 intervals. At least **1,426** must arrive within 120 seconds of acquisition
(ceil(0.99 × 1440)). Count unique intervals, not packets or retransmissions. Unknown
acquisition time cannot prove latency. Publish missing, late, invalid-clock and
sensor-fault records as separate counts; do not silently exclude them.

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
