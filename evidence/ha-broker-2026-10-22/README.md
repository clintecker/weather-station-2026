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
| Login as `weatherstation` with the run directory's password | `Success`, both by the broker's LAN address and by its Tailscale name |
| Wrong password (after the HA password was changed, before the file was updated) | `Not authorized`: the broker enforces the HA account |
| HA discovery | 11 retained `homeassistant/sensor/station-01_*/config` topics |
| Retained state | `…/weather` holds the last reading of run-d7 (23.0 °C, 34.42 %); `…/gateway_availability` is `offline` (the clean stop) |
| HA device | `station-01` ("Stage 0 hardware", Weather Station Project) under MQTT with 10 sensors and 1 diagnostic entity, all Unavailable while the gateway is stopped (`ha-device-station-01.png`) |

Not tested: TLS (the broker has none), entities updating live in HA (needs the gateway running:
the next hardware session), and the outage matrix (H01).

The password was rotated on 2026-10-22: a generated value, written to `run-d7/mqtt-password`
with mode 0600 and set on the HA user.
