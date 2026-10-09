# Weather Station — Stage 0 software checkpoint

Authority: **Weather Station v0.2 PRD/TRD, 8 October 2026**, sections 3, 9, 11 and H01.
Status: executable host software and portable C groundwork. **Stage 0 is not complete; H01 NOT RUN.**

## Run on your Mac

Python 3.12 is the tested baseline. Open this folder in VS Code and run:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m ws0 init
python -m ws0 demo
```

`init` creates a private `run-demo` directory with a fresh radio key, API token and persistent nonce state. It refuses to overwrite an existing directory. `demo` emits one simulated sample immediately, then every 60 seconds. It exercises the encrypted frame → gateway → SQLite → encrypted ACK path. All station identifiers say `simulation-01`. Ctrl-C stops it; rerun `demo` to resume with a new observation epoch and the old queued history.

In a second terminal, from the same folder:

```sh
source .venv/bin/activate
python tools/status.py
```

This displays live status without printing your API token. The read-only API listens at `127.0.0.1:8088` and requires the bearer token from `run-demo/gateway.json` on every request. Routes:

- `GET /v1/status`
- `GET /v1/observations/latest`
- `GET /v1/observations?limit=100&offset=0`
- `GET /v1/observations?from=2026-10-09T00:00:00Z&to=2026-10-10T00:00:00Z&format=csv`

Times in records are Unix seconds UTC. `from` is inclusive and `to` exclusive. Unknown acquisition times remain null and are retained in SQLite but excluded from time-filtered history. Pagination is bounded to 1,000 rows. Read `docs/openapi.json` for the interface.

## Exercise failures while waiting

Run these in a second terminal. These commands act only on the simulator:

```sh
# Interrupt transport; leave demo running so it journals new observations.
touch run-demo/link-down
# After three missed reporting intervals, status becomes unavailable.
# Restore the path: live data is sent first, then at most two queued records/minute.
rm run-demo/link-down

# Make the next sensor samples explicitly invalid.
touch run-demo/sensor-fault
# Restore measurements.
rm run-demo/sensor-fault
```

The transmitter journal deletes a reading only after a valid authenticated ACK. The gateway produces that ACK only after database commit. Old backfill and exact duplicate packets never refresh a measurement's age. A newer sensor failure or unknown clock marks the measurement unavailable. Future-clock samples are quarantined at receipt; a subsequent correctly timed observation restores availability.

## Run the simulation harness

```sh
# 12 deterministic scenarios, 24 virtual hours each; no hardware or broker required.
python -m ws0.harness --output my-simulation-results

# Inspect the generated report on macOS.
open my-simulation-results/report.html

# Edit a scenario JSON to change loss, delay, outages, clock faults or reboots.
python -m ws0.harness --scenario examples/scenarios/custom-outage.json --output custom-results

# Intentional failure control: this should exit with status 1 and report a missing row.
python -m ws0.harness --scenario examples/scenarios/short-baseline.json --negative-control --output negative-results
```

Output directories must be new, so repeated runs cannot silently overwrite evidence.
Fixed scenario seeds reproduce raw frame/event traces. The included `simulation-results/report.html`
contains the recorded campaign: all 17,280 observations recovered, zero duplicate rows,
zero detected nonce reuse. One noisy-link seed delivered 98.82% on time, below the 99%
target. Scenario PASS means its declared recovery/integrity contract passed; it is not
an H01 pass. See `docs/simulation-harness.md` for the exact model and limitations.

## Home Assistant / MQTT

The service includes MQTT publishing and HA discovery for temperature and humidity. MQTT is disabled by default so the demo runs without an existing broker. To enable it, stop the service and edit `run-demo/gateway.json`: set `mqtt.enabled` to true, set the broker hostname/port, add `mqtt.username` if required, and enable `mqtt.tls` for a TLS broker. Supply the password in environment variable `WS_MQTT_PASSWORD`; it is not stored in source code. Restart to apply configuration. Live reload is not implemented in this checkpoint.

The broker must already be configured in Home Assistant. No HA instance or broker has been changed for you. The simulated device appears under **simulation-01**. Both gateway health and measurement freshness must be online for its sensors to be available. Gateway disconnection uses MQTT last-will; stale measurements go offline at 180 seconds. Discovery is republished when the broker reconnects. The two measurement sensors fulfill the Stage-0 weather-data integration; this does not manufacture an unsupported forecast/composite weather entity.

MQTT behavior has local mocked-publisher tests; live broker interoperability and actual HA entity behavior remain to verify. Use a separate future station ID and key for hardware. Never reuse the demo state as production provisioning.

## What is implemented

- AES-128-CCM authenticated observation and ACK frames; 16-byte authentication tags.
- Durable host nonce allocation, endpoint/key binding, separate observation identity.
- SQLite storage, immutable deduplication and collision rejection.
- Persistent simulated transmitter queue, restart handling and bounded backfill.
- Authenticated loopback HTTP status/history and CSV export.
- Optional MQTT snapshots, availability and Home Assistant discovery.
- Bounded USB serial hex-frame ingestion for the planned receiver contract.
- Portable C SHT45 acquisition/CRC/conversion and 24-byte observation serializer.
- Failure-oriented Python/C tests and recorded validation output.

## What still must be implemented or tested before H01

**There are no flashable Nucleo binaries in this checkpoint.** `firmware/stage0.c` is portable code tested on the host compiler, not an STM32Cube project. The remaining board work is explicit in `firmware/README.md`: pin the vendor/toolchain revisions, verify pin mapping, integrate radio/crypto and a power-fail-safe journal, implement wired provisioning and time synchronization, compile/link both targets, then flash and test them. The serial code has no physical receiver validation yet.

Actual RF settings, regulatory configuration, antennas, current measurements, intended-placement reliability and the 24-hour run remain untested. Simulation does not pass H01. The 30-day on-device storage requirement belongs to the later H11 qualification; select the Stage-0 storage needed for its declared outage before firmware release. No additional parts order is required to run this software.

## Tests

```sh
python -m unittest discover -s tests -v
```

The C tests require `cc` (Apple Command Line Tools on macOS). The recorded test host is Linux/Python 3.12; macOS execution has not been independently performed. The 1,440-record test uses accelerated virtual timestamps, not 24 hours of elapsed time. See `evidence/validation.txt`.

## State and key handling

Keep the entire run directory private. Never copy it to two concurrently running hosts; never restore an older nonce state while retaining its key. If nonce state is lost or rolled back, retire that key and provision a new configuration for both ends. SQLite host counter persistence is implemented; STM32 monotonic epoch persistence and flash wear management are not. A known key must not be used with a reset counter. Do not commit keys, tokens or run databases. The downloadable archive includes no working secrets.

## Ordered next steps

1. Complete and build the Stage-0 Nucleo transmitter/receiver integration against this draft protocol.
2. Bring up USB, sensor CRC readings and direct-radio transport using normal bench power.
3. Run and record `docs/H01-checklist.md`, including intended-placement, restart and outage tests.
4. Freeze the passing source/toolchain/BOM/configuration/evidence checkpoint.
5. Only then begin Stage 1 power and pack-state implementation.

Existing PCB/print orders are prototype aids. Their arrival is not a prerequisite for the first USB-powered development-board data path. No solar, pack control, RJ45/Modbus abstraction, heater or shared-charging implementation is added here.
