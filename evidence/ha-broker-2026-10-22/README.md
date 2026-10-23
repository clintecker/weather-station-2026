# Gateway against Clint's Home Assistant broker (2026-10-22)

Broker: the Mosquitto add-on on Clint's Home Assistant OS VM, port 1883, no TLS (8883 has no
certificate configured). The add-on's own login list is empty, so it authenticates against Home
Assistant user accounts. The gateway uses a dedicated, non-administrator HA user `weatherstation`.
The broker host and the password live only in the run directory (`run-d7/`, git-ignored).

The gateway first published to this broker during the `run-d7` session (ended 2026-10-19 21:58 UTC).
This record was made with the hardware off: a read-only MQTT client (its own client ID, so it did
not displace the gateway) subscribed to the retained topics.

| Check | Result |
|---|---|
| Wrong password (step 2 below) | `Not authorized`: the broker enforces the HA account |
| Login as `weatherstation` with the run directory's password (step 3) | `Success`, both by the broker's LAN address and by its Tailscale name |
| HA discovery | 11 retained `homeassistant/sensor/station-01_*/config` topics (`retained-topics.txt`) |
| Retained state | `…/weather` holds the last reading of run-d7 (23.0 °C, 34.42 %); `…/gateway_availability` is `offline` (the clean stop) |
| HA device | `station-01` ("Stage 0 hardware", Weather Station Project) under MQTT with 10 sensors and 1 diagnostic entity, all Unavailable while the gateway is stopped (`ha-device-station-01.png`) |

Not tested: TLS (the broker has none), entities updating live in HA (needs the gateway running:
the next hardware session), and the outage matrix (H01).

Order of events on 2026-10-22:

1. A generated password was written to `run-d7/mqtt-password` (mode 0600) and set on the HA user,
   replacing the one run-d7 used.
2. Before the HA user matched the file, a login with the file's password got `Not authorized`.
3. Once both matched, the login got `Success`. The topic list (`retained-topics.txt`) was taken
   after that.

The gateway itself has not yet logged in with the new password; that is the next hardware
session. The screenshot is cropped below the device name; the model string "Stage 0 hardware"
and the entity count identify it as `station-01`.
