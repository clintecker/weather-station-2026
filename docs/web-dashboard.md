# Web dashboard

The gateway serves a live dashboard for the transmitter node (TX), the receiver board (RX) and the
sensor data. It uses the same process and port as the API. It needs no internet connection, no
account and no build step. It is plain HTML, CSS and JavaScript in `ws0/static/`, with its own SVG
charts (no libraries, nothing from a CDN). The server side is `ws0/web.py`, standard library only.

```mermaid
flowchart LR
  RX["RX board (USB serial lines)"] --> SL["Gateway serve loop"]
  SL --> DB[("observations.sqlite3: observations, diagnostics, radio_events, rx_alive, rx_faults, gateway_events")]
  SL --> EV["Event buffer (last 5,000 events)"]
  DB --> API["/v1/ history endpoints"]
  EV --> SSE["/v1/events stream"]
  API --> PG["Dashboard page"]
  SSE --> PG
```

## Open it

1. Start the gateway as usual (`ws0 serve …`, or `ws0 demo` for a simulated node).
2. Open `http://127.0.0.1:<http_port>/` on the gateway machine (default port 8088).
3. Paste the API token: `api_token` in `<run dir>/gateway.json`. The page keeps the token in this
   tab's `sessionStorage` only. Closing the tab forgets it. **Sign out** clears it at once.

From another machine (a phone, a laptop), prefer an SSH tunnel to the gateway:
`ssh -L 8088:127.0.0.1:8088 <gateway host>`. Then open `http://127.0.0.1:8088/` locally.

## What it shows

**Live** (updates within about a second of each event. Ages count up locally):

| Part | Content |
|---|---|
| Status chips | Key-reuse alarm, reading fresh/stale (180 s, as the API), sensor quality, receiver alive/silent (180 s), host clock state (`ok` / `unverified` / `bad`, "not checked" in demo), node link and energy state, overdue node health report |
| Readings | Latest value of every catalog field the node sends, with unit and age. A null field shows "sensor fault". Wind calm shows "calm". Qualifiers (icing …) are shown. The station and power fields (`DIAGNOSTIC_FIELDS` in `ws0/fields.py`: battery, load, charger input, solar, USB-C, enclosure) get their own "Station and power" tiles below the weather. A field the record does not carry has no tile (not measured in this build, see [Power view](#power-view)) |
| Node (TX) health | Latest 15-minute health report: firmware build, epoch, uptime, reset cause, link and energy state, journal pending/lost/torn, abandoned, missed ACKs, rejected replies, crashes, ACK signal strength and signal-to-noise ratio (RSSI/SNR) as the node heard the gateway. Protocol version 6 adds: last crash PC (`0x` + 8 hex digits, "none", or "crash, frame not trusted (no PC)" for `ffffffff`), boots since power-up, radio TX timeouts, I2C bus recoveries, MCU supply (VDDA), power-monitor die temperature, battery state of charge and its rate (fuel gauge), charger status (input power, charging, fault, stage), charger active input, charger-reported input and battery voltage and current, charger and pack temperature. A key the report sends as its none code shows "sensor fault" when the report lists it in `power_sensor_faults` (its source is fitted but failed: a dead fuel gauge, a failed ADC) and "not measured in this build" when it lists it in `power_not_measured` (the fitted byte, design section 6.1); without those lists, "not measured" ("none" for the crash PC). A report from older firmware without the key shows "—" (`healthRows` in `ws0/static/app.js`) |
| Receiver (RX) | Latest `#alive` report: forwarded, dropped, ACKs, re-listens, UART errors, stack peak, CRC/header errors since boot, bad receptions the RX could not capture (overrun: one arrived while the previous capture was still queued), longest task and interrupt (µs, with the name of the one that set the peak), trace drops, uptime. Also **bad receptions in the last hour** (CRC vs header), from the gateway's `rx_faults` table. A few an hour from other 915 MHz devices and noise is normal and shown plainly. The page marks a warning above 30 in the trailing hour, or when the rate limit dropped any in that hour ("n more dropped by the rate limit in the last hour"). The count stays current with no new bad reception: the gateway publishes it again (at most once a minute) when old ones leave the hour |
| Gateway | Accepted/rejected/NACKed this run, node-counter mark and regressions, host clock, stream state |
| Recent frames | Last 40 frames: time, kind, counter, outcome (ACK, duplicate, NACK, diag = health report, rejected, commit failed, dropped by RX, reply not delivered), RSSI and SNR as the RX heard them |
| Events | Last 60 gateway and receiver events: gateway start/stop, serial open/lost, receiver silent, host clock, rejected frames, RX boots, re-listens. The page does not list bad receptions one by one. It shows one info event per clock hour that had any ("bad receptions <hour> + 1 h: n CRC, m header"). It shows one warning (`rx-fault-rate`) when more than 30 fall in the trailing hour. The next such warning comes only after the rate has dropped to 15 or fewer |

**History** (last hour, day, week, or a custom range. Relative ranges keep following live):

- **Sensors:** one chart per catalog field present.
  - A solid line is synchronized time. A dashed line is time reconstructed from the node's uptime.
  - A break means no reading. A shaded band means a sensor fault.
  - The page never draws missing values as zeros. It counts readings that have no time yet, but does not plot them.
- **Power:** one block per rail, voltage and current paired, every minute from the observations;
  battery current signed around a zero line ("charging" above, "discharging" below); the battery
  energy and charge counters. Below them, from the 15-minute health reports: state of charge and
  its rate, the charger status, charge stage and active input as state bands, and the
  charger-reported values.
  See [Power view](#power-view).
- **Link quality:** uplink RSSI and SNR per frame (RX side) next to downlink ACK RSSI/SNR (node
  side, from its health reports), and problem frames (NACK, rejected, dropped).
- **Node health:** energy and link state bands, journal pending, journal lost, missed ACKs,
  crashes, boot epoch, abandoned records, boots since power-up, radio TX timeouts, I2C bus
  recoveries, MCU supply (VDDA), power-monitor die temperature. Markers: node boots (epoch changes, with reset cause),
  firmware changes, gateway starts.
- **Receiver health:** forwarded, dropped, re-listens, UART errors, stack peak, uptime, CRC and
  header errors, longest task and interrupt (counters and peaks since the RX board's last boot).
  Markers: RX boot, serial-lost, serial reopen and receiver-silent. A "serial reopen" marker is a
  `serial-reopen` event: the RX port stayed open but sent nothing for 90 s (doubling to 400 s), and
  the gateway reopened it in place (`ws0/link.py`; build-progression record H8).

The server reduces long ranges (`max_points`, about 1.5 points per screen pixel). It uses the mean
per time bucket, and the last value for counters. A bucket whose readings are all faults stays a
gap. Hovering over (or touching) a chart shows the values at that time.

## Power view

The power view shows what the node measures of its four rails: battery, load (system), solar
input and USB-C input, plus the charger input after the sources join. Design:
[`docs/superpowers/specs/2026-10-29-power-telemetry-design.md`](superpowers/specs/2026-10-29-power-telemetry-design.md)
sections 3 and 10. The page's rail table is `RAILS` in `ws0/static/app.js:36`.

**Not measured vs sensor fault.** These are two different things, and the page never shows either
as a number:

| The record | Means | The page shows |
|---|---|---|
| The field is absent (not in the record's bitmap) | This build has no source for it: a property of the hardware phase, never of a part's state | "not measured in this build": one line for a rail with no field in any record of the range, an empty slot for one missing field of a rail (`railCharts`, `ws0/static/app.js:1103`). The rail's names come from `observations.diagnostic` and `labels` of `/v1/history` (`observation_series`, `ws0/web.py:775`) |
| The field is present and `null` (INVALID) | The source is fitted but failed, or its reading was out of range | "sensor fault": a shaded band on the chart, a "sensor fault" tile. The record is `partial` |

The power fields of a version 6 build are always in the record when the build fits their source:
a dead INA228 or fuel gauge gives `null` ("sensor fault"), never absence. The health report has one
none code a slot, so its fitted byte (design section 6.1) gives the same split: the gateway lists a
`null` power key in `power_sensor_faults` when the build has its source and in `power_not_measured`
when it does not. A chart whose every report in the range is `null` says "Sensor fault (no value in
these health reports)" when a report lists the key as a fault and "Not measured in this build"
otherwise; a key no report carries is "Not in these health reports (older firmware)" (`diagEmpty`,
`ws0/static/app.js:1092`). A phase A station with a dead fuel gauge therefore shows a sensor
fault for SOC, never "not measured".

**Which source fills each rail, by phase** (design section 3.2). Phase A is the current bench and
field build (bq24074 charger, one INA228 in the battery path, MAX17048 gauge). Phase B adds one
INA228 per rail. Phase C replaces the charger with the BQ25798: "C+B" keeps phase B's INA228s,
"C alone" has only the BQ25798.

| Value (field) | Phase A | Phase B | Phase C+B | Phase C alone |
|---|---|---|---|---|
| Battery voltage (`batt_mv`) | MAX17048 VCELL at the CELL+ node (includes the pack-lead drop; record M4) | as A | as A | as A |
| Battery current (`batt_current_ma`) | battery INA228 | as A | as A | as A |
| Battery energy and charge (`energy_*_mwh`, `charge_*_mah`) | battery INA228 charge × VCELL | as A | as A | as A |
| Load voltage (`load_mv`) | battery INA228 VBUS, on its own sense lead to the OUT connector (record P5) | load INA228 | load INA228 | BQ25798 VSYS |
| Load current (`load_current_ma`) | not measured | load INA228 | load INA228 | not measured |
| Charger input voltage (`charger_input_mv`) | PA10 × the stored divider ratio (3 nominal); **source not identified** | as A | BQ25798 VBUS | BQ25798 VBUS |
| Solar voltage (`solar_mv`) | not measured | solar INA228 | solar INA228 | BQ25798 VAC1 |
| Solar current (`solar_current_ma`) | not measured | solar INA228 | solar INA228 | BQ25798 IBUS while solar is the active input, 0 while USB-C is or with no input |
| USB-C voltage (`usb_mv`) | not measured | USB-C INA228 | USB-C INA228 | BQ25798 VAC2 |
| USB-C current (`usb_current_ma`) | not measured | USB-C INA228 | USB-C INA228 | BQ25798 IBUS while USB-C is the active input, 0 while solar is or with no input |

- **Phase A cannot tell solar from USB-C.** The bq24074 has one input and no monitor sits upstream
  of where the sources join, so the page shows "Charger input (source not identified)" and the
  solar and USB-C rails say "not measured in this build". The node never guesses the source.
  USB-C is for bench work and occasional backup charging only, never connected together with solar.
- **Battery current sign:** + into the cell (charging), − out of the cell (discharging), in mA,
  −32,768 to +32,766. Load and source currents are + into the load or into the station. The SOC
  rate of the health report is + while charging too.
- **Field 11 (`batt_mv`) changed meaning in version 6.** It is now the cell voltage from the fuel
  gauge. Version 5 builds sent the INA228 VBUS of whatever net its jumper sensed (on the official
  wiring the charger OUT, which reads higher than the cell while charging). A run directory holds
  one version, so version 5 values stay in their own database; do not compare them with version 6
  values as the same quantity.
- **Retired:** `soc_gauge_pct` (17) and `charger_pins` (18) are not sent by version 6 builds. The
  health report carries the state of charge (`battery_soc_pct`) and the charger status. An older
  database still charts them.
- **Charger state bands** (`drawCharger`, `ws0/static/app.js:1140`): "Charger status" (power good,
  charging, fault, from the three booleans), "Charger stage" (pre-charge, constant current, constant
  voltage, top-off, terminated, not charging) and "Charger active input" (solar, USB-C, or "no input":
  the charger reports that neither input powers it, phase C at night). The gateway keeps every change
  of these keys when it thins a long range (`DIAGNOSTIC_STATE`, `ws0/web.py:832-833`), so each stage step
  stays on the band. A `null` stage or input follows the fitted byte like the charts: "not measured in
  this build" in phases A and B (the pins cannot tell them), "sensor fault" when a fitted charger read
  failed (`stateText`, `ws0/static/app.js:568`).
- The every-minute rails are redrawn with the sensor charts; the health-report values (one every
  15 minutes) with the node charts.

**Known limitation: freshness vs the CONSERVE interval** (design section 15, R9). The gateway calls
a reading current for 180 s (`CURRENT_MAX_AGE_S`, `gateway.py:27`; the page's `STALE_S`,
`ws0/static/app.js:24`). In the CONSERVE energy state the node sends at most every 5 minutes
(`firmware/common/ws_policy.h:31`). In CONSERVE the status chip, the tiles and the Home Assistant
availability would therefore flip to "stale" between sends although nothing is wrong. Deferred with
the energy state: `energy_state()` stays NORMAL in this phase (`firmware/stage0-node/App/tx_policy.c:28`),
so a NORMAL node sends every minute and the limit is not reached. When the energy thresholds are
set, the freshness limit must follow the interval of the reported energy state.

## How live updates work

The page opens one `GET /v1/events` stream (Server-Sent Events) with `fetch()`. It cannot use
`EventSource`, because `EventSource` cannot send the `Authorization` header.

The gateway pushes an event when it does one of these:

- stores an observation or a health report,
- handles a radio frame,
- gets an RX `#alive` report or a bad reception (`rx_fault`, with the trailing-hour count),
- logs a gateway event.

When that count changes only because time passed (or the rate limit dropped some), the gateway
sends `rx_fault_summary`, at most once a minute.

```mermaid
sequenceDiagram
  participant P as Dashboard page
  participant G as Gateway
  P->>G: GET /v1/events (Authorization header)
  G-->>P: event, id run-n
  G-->>P: heartbeat comment every 15 s when idle
  Note over P: Nothing heard for 45 s
  P->>G: Reconnect after back-off (1 s, doubling to 15 s), Last-Event-ID = last id
  alt Missed events still in the buffer
    G-->>P: Replay every event after that id
  else Gateway restarted, or the page was away too long
    G-->>P: resync
    P->>G: Reload the snapshot from the history endpoints
  end
```

Every event has an id `<gateway run>-<n>`. On reconnect, the page sends the last id it handled as
`Last-Event-ID`. The gateway then replays everything after that id from a buffer of the last 5,000
events. If replay is impossible (the gateway restarted, or the page was away too long), the
gateway sends `resync`. The page then reloads its snapshot from the history endpoints. Either way,
the page misses nothing.

- When a snapshot or history load fails, the page shows the failure and retries (back-off 2 s,
  doubling to 60 s).
- History requests time out after 30 s.
- Until a snapshot has loaded, a resumed stream reloads it too.
- At most 8 streams are open at once (each holds one server thread). A ninth gets HTTP 503.

## Where the data comes from

The serve loop writes these tables next to the observations in `<run dir>/observations.sqlite3`:

| Table | One row per | Source |
|---|---|---|
| `radio_events` | frame line from the RX board | The frame + the RX's following `#rx obs rssi= snr=` line, or `#rx drop`. The outcome comes from the gateway. The table keeps the frame's bytes (`frame_hex`, for `tools/rx_faults.py`) for authentic frames only (outcome ack, duplicate, diag, nack). It does not keep a rejected frame's bytes |
| `rx_alive` | RX `#alive` report (60 s) | RX console. `task_peak`/`isr_peak` are names (text), the rest are numbers. Unknown fields are ignored |
| `rx_faults` | bad reception: `#rx crc` (with every received byte) or `#rx hdr` | RX console: `received_at` (gateway UTC), `kind` `crc`/`hdr`, `length`, `rssi_dbm`, `snr_db`, `data` (lowercase hex). Rate-limited with other radio noise (burst 200, then one per 10 s). The API's `summary.throttled` gives the number dropped in the same trailing hour. Each suppressed run is a `suppressed` event. The gateway deletes rows older than 30 days (hourly, `RX_FAULT_RETENTION_S`). Out-of-range values (RSSI outside -200..20 dBm, SNR outside -64..64 dB, length over 255) make a line malformed: the gateway logs a `rx_fault_malformed` warning and stores no row |
| `gateway_events` | gateway or receiver event | `#gateway …` notes, RX boot/re-listen lines, hourly bad-reception counts, rejected frames. The serial-link kinds are `serial-lost`, `serial-open`, `serial-reopen` (level warn, with the port path and `silent_s`) and the receiver-silent note, stored as kind `receiver-silent:` (the note's second word, colon included: `ws0/web.py:534`) |

The `diagnostics` table (node health reports) already existed. `receiver.log` is unchanged and
stays the raw evidence. The volume is about 1,500 frames (with their bytes) and 1,440 RX reports a
day (tens of MB a year). Only `rx_faults` therefore has a retention limit (30 days).

The gateway creates missing tables but never migrates them (greenfield project).

- If a table in an existing database lacks a column this version writes, `ws0 serve` and
  `ws0 demo` refuse to start and name the table. Example: `rx_alive` from before `fault_overruns`.
- To fix it, stop the gateway, then rename or drop that table
  (`sqlite3 <run dir>/observations.sqlite3 "ALTER TABLE rx_alive RENAME TO rx_alive_old"`). Then
  start again.
- `tools/rx_faults.py` reports the same problem instead of a traceback.

The RX serial link accepts lines up to 1,024 characters (`ws0/link.py` `MAX_LINE`). The firmware's
longest line, a 255-byte `#rx crc` capture, is about 560 characters. The gateway drops a longer
line whole, through its newline.

Endpoints: `docs/openapi.json` (`/v1/events`, `/v1/history`, `/v1/radio`, `/v1/radio/faults`,
`/v1/receiver/alive`, `/v1/diagnostics`, `/v1/gateway/events`). Its `components.schemas` describe
the shapes: `Observation` (every catalog field, with unit, range and `null`), `HealthReport` (every
stored health key), `DiagnosticRow`, `History` and its series, `Status`. `tests/test_openapi.py`
checks them against `ws0/fields.py` and `ws0/service.py`.

`tools/rx_faults.py` lists the stored bad receptions. For each CRC capture it says which of three
cases applies:

- one of our frames (and how many bits differ from the closest accepted frame),
- one of ours with a damaged kind byte (under 10% of bits differ from an accepted frame within ±5 s),
- foreign traffic or noise.

`ws0 demo` invents RSSI/SNR, RX reports and a node health report every 15 minutes, so every panel
has something to show. Its node sends a phase A power set (battery voltage and signed current with
a day and night pattern, energy and charge counters, load and charger input voltage; solar, USB-C
and load current are "not measured in this build") and 64-byte health reports (`power_state` and
`Node.health` in `ws0/simulator.py`). Demo values are not evidence.

## Security

- By default the server listens on **127.0.0.1 only**.
  - `http_bind` in `gateway.json` (an IP address, for example `"0.0.0.0"` or a LAN address) is the
    only way to listen elsewhere. The gateway then prints a warning at every start.
  - An IPv6 address is also permitted (for example `"::1"`). A host name is refused.
  - The API is plain HTTP, so the token would cross the network in clear text. Prefer the SSH
    tunnel above.
- The server does not look up the host name at start (no reverse DNS). A slow DNS server thus
  cannot delay the gateway start.
- The server accepts at most 32 connections at a time (`HTTP_MAX_CONNECTIONS` in
  `ws0/service.py`). It closes a connection above this limit at once. A request must arrive within
  10 s (`HTTP_TIMEOUT_S`). Thus slow or half-open clients cannot use all threads and file
  descriptors.
- The server sends the page itself (`/`, `/dashboard`, `/static/…`) without authentication. The
  page contains no data. It is a fixed list of files, and no request path reaches the file
  system. Every `/v1/` endpoint, the event stream included, needs
  `Authorization: Bearer <api_token>`.
- The user enters the token once per tab. The page keeps it in `sessionStorage` and sends it only
  in the header, never in a URL. The server never logs it (it keeps no access log).
- The page inserts text from the device, the logs and the API with `textContent` only, never as
  HTML.
- The server sends the page with a strict Content-Security-Policy (no inline script, `connect-src 'self'`), no
  framing, `nosniff` and `no-referrer`. The server sends no CORS headers, so other sites cannot
  call the API from a browser.
