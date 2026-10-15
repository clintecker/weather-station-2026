# Web dashboard

The gateway serves a live dashboard for the TX node, the RX receiver and the sensor data from the
same process and port as the API. It needs no internet connection, no account and no build step:
plain HTML, CSS and JavaScript in `ws0/static/`, with its own SVG charts (no libraries, nothing
from a CDN). Server side: `ws0/web.py`, standard library only.

## Open it

1. Start the gateway as usual (`ws0 serve …`, or `ws0 demo` for a simulated node).
2. Open `http://127.0.0.1:<http_port>/` on the gateway machine (default port 8088).
3. Paste the API token: `api_token` in `<run dir>/gateway.json`. The page keeps it in this tab's
   `sessionStorage` only; closing the tab forgets it. **Sign out** clears it at once.

From another machine (a phone, a laptop), prefer an SSH tunnel to the gateway:
`ssh -L 8088:127.0.0.1:8088 <gateway host>`, then open `http://127.0.0.1:8088/` locally.

## What it shows

**Live** (updates within about a second of each event; ages count up locally):

| Part | Content |
|---|---|
| Status chips | Key-reuse alarm, reading fresh/stale (180 s, as the API), sensor quality, receiver alive/silent (180 s), host clock state (`ok` / `unverified` / `bad`; "not checked" in demo), node link and energy state, overdue node health report |
| Readings | Latest value of every catalog field the node sends, with unit and age. A null field shows "sensor fault"; wind calm shows "calm"; qualifiers (icing …) are shown |
| Node (TX) health | Latest 15-minute health report: firmware build, epoch, uptime, reset cause, link and energy state, journal pending/lost/torn, abandoned, missed ACKs, rejected replies, crashes, ACK RSSI/SNR as the node heard the gateway |
| Receiver (RX) | Latest `#alive` report: forwarded, dropped, ACKs, re-listens, UART errors, stack peak, CRC/header errors since boot, longest task and interrupt (µs, with the name of the one that set the peak), trace drops, uptime. Plus **bad receptions in the last hour** (CRC vs header), from the gateway's `rx_faults` table: a few an hour from other 915 MHz devices and noise is normal and shown plainly; above 30 in the trailing hour, or any dropped by the rate limit, it is marked as a warning |
| Gateway | Accepted/rejected/NACKed this run, node-counter mark and regressions, host clock, stream state |
| Recent frames | Last 40 frames: time, kind, counter, outcome (ACK, duplicate, NACK, diag, rejected, commit failed, dropped by RX, reply not delivered), RSSI and SNR as the RX heard them |
| Events | Last 60 gateway and receiver events: gateway start/stop, serial open/lost, receiver silent, host clock, rejected frames, RX boots, re-listens. Bad receptions are not listed one by one: one info event per clock hour that had any ("bad receptions <hour> + 1 h: n CRC, m header"), and one warning (`rx-fault-rate`) when more than 30 fall in the trailing hour; the next such warning only after the rate has dropped to 15 or fewer |

**History** (last hour, day, week, or a custom range; relative ranges keep following live):

- **Sensors:** one chart per catalog field present. Solid line = synchronized time, dashed =
  time reconstructed from the node's uptime; a break = no reading; a shaded band = sensor fault.
  Missing values are never drawn as zeros. Readings that have no time yet are counted, not plotted.
- **Link quality:** uplink RSSI and SNR per frame (RX side) next to downlink ACK RSSI/SNR (node
  side, from its health reports), and problem frames (NACK, rejected, dropped).
- **Node health:** energy and link state bands, journal pending, journal lost, missed ACKs,
  crashes, boot epoch, abandoned records. Markers: node boots (epoch changes, with reset cause),
  firmware changes, gateway starts.
- **Receiver health:** forwarded, dropped, re-listens, UART errors, stack peak, uptime, CRC and
  header errors, longest task and interrupt (counters and peaks since the RX board's last boot);
  RX boot, serial-lost and receiver-silent markers.

Long ranges are reduced on the server (`max_points`, about 1.5 points per screen pixel): mean per
time bucket, last value for counters; a bucket whose readings are all faults stays a gap.
Hovering (or touching) a chart shows the values at that time.

## How live updates work

The page opens one `GET /v1/events` stream (Server-Sent Events) with `fetch()`, because
`EventSource` cannot send the `Authorization` header. The gateway pushes an event when it stores an
observation or a health report, handles a radio frame, gets an RX `#alive` report or bad
reception (`rx_fault`, carrying the trailing-hour count), or logs a gateway event. An idle stream gets a heartbeat comment every 15 s; if the page hears nothing for 45 s it
reconnects (back-off 1 s doubling to 15 s).

Every event has an id `<gateway run>-<n>`. On reconnect the page sends the last id it handled as
`Last-Event-ID`; the gateway replays everything after it from a buffer of the last 5,000 events.
If that is impossible (the gateway restarted, or the page was away too long) the gateway sends
`resync` and the page reloads its snapshot from the history endpoints, so nothing is missed either
way. At most 8 streams are open at once (each holds one server thread); a ninth gets HTTP 503.

## Where the data comes from

The serve loop writes, next to the observations in `<run dir>/observations.sqlite3`:

| Table | One row per | Source |
|---|---|---|
| `radio_events` | frame line from the RX board | frame + the RX's following `#rx obs rssi= snr=` line, or `#rx drop`; outcome from the gateway; the frame's bytes (`frame_hex`, for `tools/rx_faults.py`) |
| `rx_alive` | RX `#alive` report (60 s) | RX console; `task_peak`/`isr_peak` are names (text), the rest numbers; unknown fields are ignored |
| `rx_faults` | bad reception: `#rx crc` (with every received byte) or `#rx hdr` | RX console: `received_at` (gateway UTC), `kind` `crc`/`hdr`, `length`, `rssi_dbm`, `snr_db`, `data` (lowercase hex). Rate-limited with other radio noise (GW6: burst 200, then one per 10 s); the number dropped since the gateway started is in the API's `summary.throttled`, and each suppressed run is a `suppressed` event |
| `gateway_events` | gateway or receiver event | `#gateway …` notes, RX boot/re-listen lines, hourly bad-reception counts, rejected frames |

`diagnostics` (node health reports) already existed. `receiver.log` is unchanged and stays the raw
evidence. Volume is about 1,500 frames (with their bytes) and 1,440 RX reports a day (tens of MB a
year), so there is no retention yet. Endpoints: `docs/openapi.json` (`/v1/events`, `/v1/history`,
`/v1/radio`, `/v1/radio/faults`, `/v1/receiver/alive`, `/v1/diagnostics`, `/v1/gateway/events`).
`tools/rx_faults.py` lists the stored bad receptions and says whether each CRC capture looks like
one of our frames (and how many bits differ from the closest accepted frame) or foreign/noise.

`ws0 demo` invents RSSI/SNR, RX reports and a node health report every 15 minutes so every panel
has something to show. Demo values are not evidence.

## Security

- The server listens on **127.0.0.1 only** by default. `http_bind` in `gateway.json` (an IP
  address, for example `"0.0.0.0"` or a LAN address) is the only way to listen elsewhere; the
  gateway then prints a warning at every start. The API is plain HTTP, so the token would cross the
  network in clear text: prefer the SSH tunnel above.
- The page itself (`/`, `/dashboard`, `/static/…`) is served without authentication and contains no
  data. It is a fixed list of files; no request path reaches the file system. Every `/v1/`
  endpoint, the event stream included, needs `Authorization: Bearer <api_token>`.
- The token is entered once per tab, kept in `sessionStorage`, sent only in the header, never in
  a URL, never logged (the server keeps no access log).
- Text from the device, the logs and the API is inserted with `textContent` only, never as HTML.
  The page sends a strict Content-Security-Policy (no inline script, `connect-src 'self'`), no
  framing, `nosniff` and `no-referrer`. No CORS headers are sent, so other sites cannot call the API
  from a browser.
