# ws0: the gateway package

This is the gateway for the bench prototype. One process reads the USB serial lines from the RX board. It opens and checks each frame, commits it to SQLite, and sends the ACK or NACK back. The same process serves the HTTP API, the dashboard and optional MQTT. Run it as `python -m ws0 {init,demo,serve,provision-node}` from the repository root ([`README.md`](../README.md)). It needs only `requirements.txt`.

| Module | What |
|---|---|
| `__main__.py` | The command line: `init` (new run directory, key, token, nonce state), `demo` (simulated node), `serve` (the RX board), `provision-node` (key to the TX board over USB) |
| `service.py` | The gateway: frame handling, the commit-then-ACK rule, the read-only HTTP API and MQTT with Home Assistant discovery |
| `protocol.py` | The radio protocol, version 6, gateway side (health report: `pack_diag`, `unpack_diag`, `diag_problems`). Generated from [`protocol.lit.md`](protocol.lit.md) by `tools/tangle.py`, so edit that document, not this file |
| `fields.py` | The observation field catalog (version 2: 33 fields, with the extension bitmap for fields 32-33): encoder and decoder, units, labels and the station/power fields (`DIAGNOSTIC_FIELDS`). The C twin is `firmware/common/ws_obs.c` |
| `wsmp_set.py` | The WSMP descriptor set (module-protocol section 11.1, with each module's serial, identity flags and record CRC): decode, encode and the registry check. The C twin is `firmware/common/wsmp.c` |
| `descsets.py` | The descriptor sets the gateway holds by station key (WSMP-E5 to E7, with the registry version), the current set (the generation of the newest frame by its counter), the module identities it publishes to Home Assistant, and the two-station serial alarm (for a multi-station gateway, not wired yet). It keeps its own `descriptor-sets.sqlite3` in the run directory |
| `wsmp_registry.py` | WSMP registry codes. Generated from `firmware/common/wsmp_registry.toml` by `tools/wsmp_registry.py`, so don't edit it |
| `link.py` | The USB serial link to the RX board, found by ST-LINK serial number, with reconnect. If an open port delivers nothing for 90 s, the gateway reopens it in place. That's not a back-off and not a failure. The wait doubles to 400 s and resets on any line (decision record H8(f)). Each reopen logs a `serial-reopen` warn event (`#gateway serial-reopen path=... silent_s=... next_s=...`). The 180 s `receiver-silent` alarm stays the outer one |
| `clock.py` | Host clock check by SNTP at start and every hour. The ACK carries host time. If the check measures the host clock as wrong (off by more than 1 s), the gateway doesn't pass it on. The ACK then carries UTC 0 and the node keeps its own clock |
| `logfile.py` | Size-rotated logs (`--log-file`) |
| `web.py`, `static/` | The dashboard: back end (telemetry tables, event stream, history) and the page ([`docs/web-dashboard.md`](../docs/web-dashboard.md)) |
| `simulator.py` | The simulated node of `demo` and the harness: journal before send, delete only after a valid ACK |
| `harness.py` | The deterministic simulation campaigns: `python -m ws0.harness` ([`docs/simulation-harness.md`](../docs/simulation-harness.md)) |

The SQLite store itself is [`gateway.py`](../gateway.py) at the repository root, generated from [`gateway.lit.md`](../gateway.lit.md). The HTTP interface is [`docs/openapi.json`](../docs/openapi.json). The wire format is [`docs/protocol.md`](../docs/protocol.md).

## What the gateway stores

| Data | From | Stored as | Exposed |
|---|---|---|---|
| Observation (every minute) | kind 1 frame, `fields.decode` | one record: the base keys plus the catalog fields the build sends. INVALID is `null`, and a field the build has no source for is absent | `/v1/observations`, `/v1/observations/latest`, `/v1/history`, CSV, MQTT `…/weather`, HA entities `<station>_<field>` |
| Health report (every 15 minutes) | kind 4 frame, 64 bytes, `health_report` in `service.py` | one row of the keys below, with each "none" code as `null`. A non-canonical report is kept with a warning. When its charger stage is 7 (reserved), the five charger status keys (`charger_input_power_ok`, `charger_charging`, `charger_fault`, `charger_stage`, `charger_active_input`) are `null`. A set fitted bit 7 only gives the warning | `/v1/diagnostics`, `/v1/status` `node_diagnostics`, `/v1/history` `diagnostics`, SSE `diagnostic`, MQTT `…/diagnostics`, HA entities `<station>_diag_<key>` for the keys this build measures: the power keys plus `mcu_supply_mv` (a fitted key that faults still gets one). They go unavailable once the newest report is older than `health_max_age` (`…/diagnostics/availability`): 1,900 s, or 3,720 s when the report says CRITICAL, where reports come with the hourly beacon |

The health-report keys are `HEALTH_KEYS` in `service.py`. Units and `null` rules are in the `HealthReport` schema
in [`docs/openapi.json`](../docs/openapi.json). The design is in [`docs/superpowers/specs/2026-10-29-power-telemetry-design.md`](../docs/superpowers/specs/2026-10-29-power-telemetry-design.md) section 6.

| Group | Keys |
|---|---|
| Station (version 5) | `epoch`, `uptime_s`, `journal_pending`, `journal_lost_total`, `journal_torn_slots`, `abandoned_total`, `missed_acks_since_boot`, `rejected_replies_since_boot`, `reset_cause`, `link`, `firmware_build`, `ack_rssi_dbm`, `ack_snr_db`, `crashes_since_power_up`, `energy_state` |
| Station (version 6) | `last_crash_pc` (8 hex digits, `null` = no crash since power-up, `ffffffff` = a crash whose stacked frame was not trusted, so no PC. The dashboard says "crash, frame not trusted (no PC)"), `boots_since_power_up`, `tx_timeouts_since_boot`, `i2c_recoveries_since_boot`, `mcu_supply_mv` |
| Power (version 6) | `power_monitor_temp_c`, `battery_soc_pct`, `battery_soc_rate_pct_h`, `charger_input_power_ok`, `charger_charging`, `charger_fault`, `charger_stage`, `charger_active_input`, `charger_reported_input_mv`, `charger_reported_input_ma`, `charger_reported_battery_mv`, `charger_reported_battery_ma`, `charger_temp_c`, `pack_temp_c`, `charger_cold_hold` (true while the charger holds a cold pack: power good, no fault, `not_charging`, pack under 6.3 °C; null without a pack temperature) |
| Why a power key is `null` (version 6, from the fitted byte) | `power_not_measured` (this build has no source), `power_sensor_faults` (the fitted source failed): sorted lists of power keys |

The health keys never share a name with an observation field. `charger_input_mv` (observation,
the PA10 divider) and `charger_reported_input_mv` (health report, the charger's own ADC) are two
different measurements. To see which phase fills which rail and key, read [`docs/web-dashboard.md`](../docs/web-dashboard.md)
"Power view" and [`docs/runbook-home-assistant.md`](../docs/runbook-home-assistant.md) "Power entities".
`tests/test_openapi.py` keeps the API schemas equal to `fields.MEASURED` and these keys.
