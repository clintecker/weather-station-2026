# ws0: the gateway package

The gateway for the bench prototype. One process reads the RX board's USB serial lines, opens and checks each frame, commits it to SQLite, sends the ACK or NACK back, and serves the HTTP API, the dashboard and optional MQTT. Run it as `python -m ws0 {init,demo,serve,provision-node}` from the repository root ([`README.md`](../README.md)). It needs only `requirements.txt`.

| Module | What |
|---|---|
| `__main__.py` | The command line: `init` (new run directory, key, token, nonce state), `demo` (simulated node), `serve` (the RX board), `provision-node` (key to the TX board over USB) |
| `service.py` | The gateway: frame handling, the commit-then-ACK rule, the read-only HTTP API and MQTT with Home Assistant discovery |
| `protocol.py` | The radio protocol, version 5, gateway side. Generated from [`protocol.lit.md`](protocol.lit.md) by `tools/tangle.py`: edit the document |
| `fields.py` | The observation field catalog: encoder and decoder. The C twin is `firmware/common/ws_obs.c` |
| `wsmp_registry.py` | WSMP registry codes. Generated from `firmware/common/wsmp_registry.toml` by `tools/wsmp_registry.py`: do not edit |
| `link.py` | The USB serial link to the RX board, found by ST-LINK serial number, with reconnect |
| `clock.py` | Host clock check by SNTP at start and every hour. The ACK carries host time, so a wrong host clock is refused |
| `logfile.py` | Size-rotated logs (`--log-file`) |
| `web.py`, `static/` | The dashboard: back end (telemetry tables, event stream, history) and the page ([`docs/web-dashboard.md`](../docs/web-dashboard.md)) |
| `simulator.py` | The simulated node of `demo` and the harness: journal before send, delete only after a valid ACK |
| `harness.py` | The deterministic simulation campaigns: `python -m ws0.harness` ([`docs/simulation-harness.md`](../docs/simulation-harness.md)) |

The SQLite store itself is [`gateway.py`](../gateway.py) at the repository root, generated from [`gateway.lit.md`](../gateway.lit.md). The HTTP interface is [`docs/openapi.json`](../docs/openapi.json). The wire format is [`docs/protocol.md`](../docs/protocol.md).
