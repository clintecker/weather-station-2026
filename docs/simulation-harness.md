# Stage-0 simulation harness

Run `python -m ws0.harness --output my-results` from the project root. It uses the
installed Stage-0 dependencies and a virtual clock. No device, RF transmission,
network listener, MQTT broker or cloud service is involved.

## Model boundary

The production-path Python components execute normally: observation encode/decode,
AES-CCM authentication, durable nonce allocation, node journal, SQLite storage,
commit-before-ACK, backfill, identity deduplication and freshness. The simulator
replaces the physical sensor, clock, packet delivery and selected failure sources.
On a simulated reboot, actual node/gateway objects and database connections close
and reopen. In-flight packets remain in the delivery queue.

This is a discrete-event model, not an STM32 instruction emulator or RF simulator.
Independent Bernoulli loss is a test stimulus, not an estimated real-world channel.
Host SQLite persistence does not establish MCU flash power-loss safety. The harness
sets `WS0_UNSAFE_FAST_FSYNC=1` by default, skipping the slow drive-cache flush,
because it models restarts, not power loss. Radio
receive windows, airtime, duty cycle, interference, RSSI/SNR, firmware concurrency,
power/current, buffer overflow and enclosure/environmental effects are not modeled.
The serial framing adapter, MQTT broker and Home Assistant are outside this campaign;
the broader unit suite has separate HTTP, C core and mocked MQTT tests.

## Built-in scenarios

| Scenario | Injection | Required result |
|---|---|---|
| baseline | None | Complete exact storage; at least 99% within 120s |
| noisy-link (3 seeds) | 10% uplink/ACK loss; 1% corruption; 15% duplicates; 0–20s delay | Exact eventual recovery; measure latency without assuming success. Since 2026-10-13 the gateway does not answer a duplicated or reordered copy (counter at or below its high-water mark, P4); the harness counts these as expected `counter_regressions`. A real LoRa link cannot reorder frames, so this lowers simulated timeliness only (about 1–2 points vs `simulation-results/`) |
| radio-outage | Link unavailable during minutes 20–40 | Unavailable state, complete recovery; full latency denominator retained; the 99% target is expected to fail (runs of 1 day or less) |
| host-outage | Host unavailable minutes 20–30, restart at 30 | Recovery from node journal |
| reboots | Node, gateway and simultaneous restarts with delayed packets | Exact recovery, nonce continuity, at least 99% within 120s |
| sensor-fault | Null/fault samples minutes 20–25 | Faults never presented as current valid measurements; recovery; at least 99% within 120s |
| clock-errors | Unknown clock minutes 20–25; +3600s minutes 30–35 | Unavailable during bad-clock samples; corrected clock recovers |
| reboot-during-outage | Link unavailable minutes 20–80; node reboot at minute 50 (no clock until the link returns) | Every unsynchronized sample ends with a reconstructed or synchronized time; complete recovery; the 99% target is expected to fail (runs of 1 day or less) |
| storage-failure | Database commit raises minutes 20–25 | No ACK on failed commit; journal retained and later recovered |
| ack-loss | 50% ACK loss; 15% duplicates | Idempotent storage and eventual journal drainage; at least 99% within 120s |
| identity-collision | Authenticated changed payload with an existing identity | Reject collision (answered with an authenticated NACK), preserve original observation; at least 99% within 120s |

Each default scenario schedules 1,440 one-minute samples. Samples are always counted
in the denominator. An observation is timely only if it has a synchronized or
gateway-reconstructed time within five seconds of the harness's acquisition clock,
and its first commit occurs within 120 seconds of acquisition. Like the firmware, the
simulated node has no trusted clock after a boot until its first authentic ACK, so
those samples rely on gateway reconstruction (reported as `reconstructed_time_samples`
and `unresolved_time_samples`). Sensor faults are counted separately; transport timeliness
alone is not evidence that the sensor functioned correctly.

The live sample is attempted before up to two older samples each minute. After the
sampling window, the harness allows at most `minutes + 120` additional drain minutes,
at two queued records/minute. Drain time is reported separately. Complete eventual
recovery does not erase late delivery or pass a failed latency threshold.

This drain model is simpler than the firmware. The simulated node sends the live
sample plus up to 2 backlog records every minute, even while the link is down. The
board firmware drains up to 5 backlog records per minute in the normal energy state,
capped by airtime (`backlog_limit`, `firmware/common/ws_policy.c`). After 3
silent minutes it enters PROBING: live-only probes with a 2, 4, 8, then 15-minute
back-off, and journal-only minutes in between (failure-modes.md G13). The harness
does not model PROBING, so its outage latencies and drain times are not
firmware-accurate.

## Custom scenarios

Copy `examples/scenarios/custom-outage.json` and edit it. All interval endpoints use
minute indices `[start, end)`; clock-step intervals add a third element, the offset
in seconds. Rates are probabilities in [0,1]. `seed` determines packet fault choices.
`node_reboots` and `gateway_reboots` list minute indices. JSON is strictly mapped to
the Scenario fields; misspelled options fail instead of being ignored.

The harness records:

- Every sampled expected identity and its true virtual acquisition time.
- Raw encrypted frame sends, losses, arrivals, rejected packets and ACK events.
- Freshness/availability at the end of every sampling minute.
- Exact stored payload comparisons against scheduled observations.
- New-encryption nonce reuse (wire duplication of identical ciphertext is allowed).
- Pending journal records, late/missing records, duplicate rows and recovery time.

`result.json` and the command exit code represent the declared scenario contract.
Exit 0 means all requested scenario contracts passed. Exit 1 means a contract failed.
Input/configuration errors also exit nonzero. `physical_H01` always remains `NOT RUN`.

## Reproducibility and evidence

Each scenario gets an isolated temporary state directory, with a deterministic public
fixture key derived from `SHA256("PUBLIC-TEST-KEY/" + scenario_name)[:16]`. This is for
repeatable test bytes only. Never use these keys or cloned simulation nonce state for
a device deployment. Real provisioning remains `python -m ws0 init`, which generates
random local keys. No deployment secrets are included in campaign evidence.

The output contains `scenario.json`, `result.json`, `trace.jsonl`, `availability.json`
and an SQLite backup per scenario, plus `summary.json` and a readable `report.html`.
Identical scenario inputs and source versions reproduce event traces and results;
SQLite file bytes and wall-clock test timings need not be identical. See the archive's
source commit and SHA256 manifest for the code/evidence checkpoint.

Tests verify repeatability, outage denominator preservation, commit-failure recovery,
corrupt/missing-data detection and a total-loss case that terminates with failure.
`--negative-control` intentionally removes a row from the oracle input to prove a
missing-data failure is surfaced. It does not modify stored evidence or the gateway
implementation; its report explicitly identifies the negative control.

## Next hardware gate

Use this harness to regress protocol and gateway changes. The boards are running, and
bench and office RF measurements now exist (see `evidence/README.md`). Use measured
RF loss and latency traces to inform additional scenarios. H01 still requires the real 24-hour placement run,
restarts, stale behavior and outage recovery described in `H01-checklist.md`.
