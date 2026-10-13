# Runbook: connect the gateway to Home Assistant (MQTT)

The gateway publishes to an MQTT broker; Home Assistant (HA) picks the station up through MQTT
discovery. Tested against a local Mosquitto broker (`evidence/mqtt-local-broker-2026-10-13/`); a real
HA instance, TLS and broker authentication are still to be verified (context pack §6.3).

## What is needed

| Item | Where it goes |
|---|---|
| Broker host name or IP, port (1883 plain, usually 8883 for TLS) | `gateway.json` → `mqtt.host`, `mqtt.port` |
| TLS on or off | `gateway.json` → `mqtt.tls` (`true` uses the system's trusted CA certificates: `paho` `tls_set()`) |
| MQTT user name | `gateway.json` → `mqtt.username` |
| MQTT password | **Not in `gateway.json` and never in chat or git.** A file `mqtt-password` in the run directory (first line), or the `WS_MQTT_PASSWORD` environment variable, which wins if set (`mqtt_password()` in `ws0/service.py`) |

The run directory (for example `run-office/`) already holds the radio key; it is git-ignored
(`run*/`). On macOS and Linux the gateway warns if `mqtt-password` is readable by other users. On
Windows, protect the run directory with folder permissions: the POSIX permission check does not
apply there.

## Set up the broker in Home Assistant OS (Clint's setup)

Source: the Mosquitto add-on documentation,
https://github.com/home-assistant/addons/blob/master/mosquitto/DOCS.md (checked 2026-10-13; recent
HA versions call add-ons "Apps", so menu names may differ on older versions).

1. **Install the broker:** Settings → Apps → Install app → **Mosquitto broker** → Install, then Start.
   Check its log after a couple of minutes.
2. **Create a user for the gateway:** Settings → People → Users → Add user (for example
   `weatherstation`). If the Users tab is missing, turn on Advanced Mode in your HA profile. The
   names `homeassistant` and `addons` are reserved. The broker accepts HA users; anonymous
   connections are refused.
3. **Enable the MQTT integration:** Settings → Devices & services. MQTT appears as a discovered
   integration; select it, keep discovery on, and submit.
4. **Gateway settings:** `host` = the HA machine's address (for example `homeassistant.local` or its
   IP), `port` 1883, `tls` false (TLS on 8883 needs the add-on's `certfile` and `keyfile`), `username`
   = the user from step 2. Then follow the steps below.

## Steps

1. Stop the gateway (Ctrl-C, or the service; see below).
2. Edit `<run dir>/gateway.json`:

   ```json
   "mqtt": {"enabled": true, "host": "<broker>", "port": 1883, "tls": false, "username": "<user>"}
   ```

3. Write the password file yourself (macOS / Linux):

   ```sh
   ( umask 077; printf '%s\n' '<password>' > run-office/mqtt-password )
   ```

   On Windows, create `run-office\mqtt-password` with the password on the first line.
4. Start the gateway. A refused login or TLS problem is logged as
   `#gateway mqtt connect refused: <reason>` (stderr; `serve.out` under launchd).
5. In HA: Settings → Devices & services → MQTT. A device named after the station
   (`station-01`) appears with two sensors, Temperature (°C) and Humidity (%).

## What the gateway publishes

Root topic `weatherstation/v1/<station>` (all retained, QoS 1; `ws0/service.py`, `MQTT`):

| Topic | Content |
|---|---|
| `homeassistant/sensor/<station>_temperature_c/config`, `…_humidity_pct/config` | HA discovery, republished on every broker connect |
| `…/weather` | Latest observation (JSON), on change and every 300 s |
| `…/availability` | `online` / `offline` from the reading's age |
| `…/gateway_availability` | `online`; `offline` as the last will, so HA marks the station unavailable if the gateway dies |
| `…/diagnostics` | Node health report and the key-reuse alarm, if any |

A sensor shows as available only when both availability topics are `online`.

## Run the gateway unattended

| OS | How |
|---|---|
| macOS | `tools/deploy/macos/install.sh install <run dir> <RX ST-LINK serial>` (LaunchAgent; restarts on exit) |
| Linux | `tools/deploy/linux/ws0-gateway.service` (systemd unit; see the comments in the file) |
| Windows | No wrapper is shipped yet. Run `python -m ws0 serve --directory <run dir> --serial-number <RX serial>` from Task Scheduler ("At log on", "Restart if the task fails"), or wrap it with a service manager such as NSSM. Not yet tested. |

All three read the password from the run directory, so no OS-specific secret store is involved.
