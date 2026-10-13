# MQTT against a live broker (2026-10-13)

Broker: Mosquitto 2.1.2 on 127.0.0.1:1883 (anonymous, local only). Gateway: live hardware
gateway (station-01) under launchd. Capture: `mosquitto_sub -v -t '#'` (`capture-connect-lwt.log`).

| Check | Result |
|---|---|
| HA discovery on connect | `homeassistant/sensor/station-01_{temperature_c,humidity_pct}/config`, retained |
| Measurement + availability | `weatherstation/v1/station-01/weather`; `availability offline` (correct: readings are `sensor_fault`, no sensor yet) |
| Last will on SIGKILL | broker published `gateway_availability offline` at the kill; launchd restart republished discovery and `online` within 1 s |
| Broker restart | gateway reconnected and republished discovery/state ~18 s after the broker came back |
| Found and fixed | gateway republished identical retained state every second (~172k messages/day); now publishes on change plus every 300 s |

Not tested: a real Home Assistant instance (needs Clint's broker/HA details), TLS, broker auth.
MQTT was disabled again on the live gateway after the test.
