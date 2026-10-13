# Weather Station — Stage 0 software checkpoint

Authority: **Weather Station v0.2 PRD/TRD, 8 October 2026**, sections 3, 9, 11 and H01.
Status: Python gateway (`ws0`) plus Stage-0 firmware for two NUCLEO-WL55JC1 boards, built, flashed and bench-tested (`firmware/stage0-node/`). **Stage 0 is not complete; H01 NOT RUN.**

Resuming the bench work? Start with `docs/CONTEXT-PACK.md`. Firmware: `firmware/stage0-node/README.md`, releases: `firmware/stage0-node/RELEASES.md`. Moving boards between gateways: `docs/runbook-moving-boards.md`. Tools: `tools/README.md`.

## Run the simulated demo on your Mac

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

Times in records are Unix seconds UTC. `from` is inclusive and `to` exclusive. A sample with an unknown clock gets a reconstructed UTC time, with an uncertainty, once a synchronized sample from the same boot epoch exists. Until then its effective time is null: it is kept in SQLite but never returned by `/v1/observations`. Pagination is bounded to 1,000 rows. Read `docs/openapi.json` for the interface.

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

## Run with the boards

Both boards run the Stage-0 firmware (`firmware/stage0-node/README.md`). Find each board's port and ST-LINK serial with `.venv/bin/python -m serial.tools.list_ports -v`. TX must be unprovisioned (`WIPE ERASE-ALL-NODE-STATE` on its console erases it). Never re-provision a wiped TX with a key it has used before (`docs/runbook-moving-boards.md`).

```sh
python -m ws0 init --hardware --station station-01 --station-id 1 --directory run-office
python -m ws0 provision-node --directory run-office --serial /dev/cu.usbmodem<TX>
python -m ws0 serve --directory run-office --serial-number <RX ST-LINK serial>
python tools/status.py --directory run-office
```

`serve` writes receiver diagnostics to `run-office/receiver.log`. For unattended runs, use the launchd agent (`tools/deploy/macos/install.sh`) or the systemd unit (`tools/deploy/linux/ws0-gateway.service`). See `tools/README.md`. Home Assistant: `docs/runbook-home-assistant.md`. The gateway is meant to run on macOS, Linux or Windows.

## Run the simulation harness

```sh
# 13 deterministic scenarios, 24 virtual hours each; no hardware or broker required.
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
is an older campaign: 12 scenarios, recorded at commit 8aca123 (protocol draft 1, before
`reboot-during-outage` was added). In that campaign all 17,280 observations were recovered,
with zero duplicate rows and zero detected nonce reuse. One noisy-link seed delivered 98.82% on time, below the 99%
target. Scenario PASS means its declared recovery/integrity contract passed; it is not
an H01 pass. See `docs/simulation-harness.md` for the exact model and limitations.

## Home Assistant / MQTT

The service includes MQTT publishing and HA discovery for temperature and humidity. MQTT is disabled by default so the demo runs without an existing broker. To enable it, stop the service and edit `run-demo/gateway.json`: set `mqtt.enabled` to true, set the broker hostname/port, add `mqtt.username` if required, and enable `mqtt.tls` for a TLS broker. Supply the password in environment variable `WS_MQTT_PASSWORD`; it is not stored in source code. Restart to apply configuration. Live reload is not implemented in this checkpoint.

The broker must already be configured in Home Assistant. No HA instance or broker has been changed for you. The simulated device appears under **simulation-01**. Both gateway health and measurement freshness must be online for its sensors to be available. Gateway disconnection uses MQTT last-will; stale measurements go offline at 180 seconds. Discovery is republished when the broker reconnects. The two measurement sensors fulfill the Stage-0 weather-data integration; this does not manufacture an unsupported forecast/composite weather entity.

MQTT was verified against a local Mosquitto broker (`evidence/mqtt-local-broker-2026-10-13/`): discovery, last will and reconnect. A real Home Assistant instance, TLS and broker authentication remain untested. Use a separate future station ID and key for hardware. Never reuse the demo state as production provisioning.

## What is implemented

- AES-128-CCM authenticated observation and ACK frames; 16-byte authentication tags.
- Durable host nonce allocation, endpoint/key binding, separate observation identity.
- SQLite storage, immutable deduplication and collision rejection.
- Persistent simulated transmitter queue, restart handling and bounded backfill.
- Authenticated loopback HTTP status/history and CSV export.
- Optional MQTT snapshots, availability and Home Assistant discovery.
- USB serial ingestion from the RX board (`ws0 serve`), with ACK/NACK return.
- Portable C SHT45 acquisition/CRC/conversion and 24-byte observation serializer.
- Stage-0 TX/RX firmware (`firmware/stage0-node/`): flash journal of about 3.3 days, durable counters and epochs, watchdog, wired provisioning.
- Failure-oriented Python/C tests and recorded validation output.

## Current state and open work

Release `0f456040fe54` is built, recorded in `firmware/stage0-node/RELEASES.md` and flashed (2026-10-13). On the previous release, `a07f498273f7`, a 9 h bench soak delivered 549 of 549 minutes on time (`evidence/soak-a07f498-2026-10-13/`). RF settings are bench values (`firmware/stage0-node/App/radio_cfg.h`: 915.0 MHz, 500 kHz, SF7, CR 4/5, 0 dBm).

Still open before H01:
- SHT45 readings on hardware.
- Home Assistant against the real broker.
- Placement link budget, antennas and current measurements.
- The 24-hour run with its restart/outage matrix.

Simulation does not pass H01. The 30-day on-device storage requirement belongs to the later H11 qualification. Ordered next steps: `docs/CONTEXT-PACK.md` §6.

## Tests

```sh
sh tools/fetch-vendor.sh   # pinned STM32CubeWL + Mbed TLS; without it 7 C-vs-Python crypto tests skip
WS0_UNSAFE_FAST_FSYNC=1 python -m unittest discover -s tests -v
```

Expect 83 tests. One SNTP test needs network and skips without it. The C tests require `cc` (Apple Command Line Tools on macOS). The 1,440-record test uses accelerated virtual timestamps, not 24 hours of elapsed time. `evidence/validation.txt` is historical: 28 tests at commit 8aca123.

`WS0_UNSAFE_FAST_FSYNC=1` is **test-only**: it turns off SQLite `fullfsync`, so commits are not power-loss durable. Never set it for a gateway that ACKs real data.

## State and key handling

Keep the entire run directory private. Never copy it to two concurrently running hosts; never restore an older nonce state while retaining its key. If nonce state is lost or rolled back, retire that key and provision a new configuration for both ends. Host counters persist in SQLite; on the TX board, counters and boot epochs persist in flash (`firmware/stage0-node/App/node_store.c`). WIPE resets the node counter, so a wiped node needs a new key. A known key must not be used with a reset counter. Do not commit keys, tokens or run databases. The downloadable archive includes no working secrets.

## Ordered next steps

See `docs/CONTEXT-PACK.md` §6. Stage 1 (power and pack state) starts only after H01 passes.

Existing PCB/print orders are prototype aids. Their arrival is not a prerequisite for the first USB-powered development-board data path. No solar, pack control, RJ45/Modbus abstraction, heater or shared-charging implementation is added here.
