# Evidence index

None of this is an H01 pass. H01 (the 24-hour placement run) has not been run.

| Path | What |
|---|---|
| `validation.txt` | Unit-test output (28 tests, OK) from the **original Linux checkpoint** run, before the repo came to macOS |
| `environment.json` | Host and status record from the same **original Linux checkpoint** (Python 3.12.14, Ubuntu cc). Its `"macos"` field predates the macOS validation below |
| `macos-validation-2026-10-12.md` | First macOS run of checkpoint `8aca123`: unit tests and harness compared with the recorded `simulation-results/` |
| `harness-macos-2026-10-12/` | Harness output for that macOS validation (12 scenarios) |
| `harness-macos-2026-10-12-draft2/` | Harness re-run at protocol draft 2 (`d825c17`) |
| `harness-macos-2026-10-12-draft3/` | Harness re-run at protocol draft 3 (`e3da38b`) |
| `harness-macos-2026-10-12-draft4/` | Harness re-run at protocol draft 4 (`a196203`); adds `reboot-during-outage` (13 scenarios) |
| `harness-macos-2026-10-12-g2-nack/` | Harness re-run with authenticated NACK (`19c4049`) |
| `g13-outage-2026-10-13/` | TX console during a bench link outage: PROBING back-off and backlog drain (G13) |
| `g7-reset-during-write-2026-10-13/` | 70 NRST resets during flash writes: G7 part A, PASS |
| `mqtt-local-broker-2026-10-13/` | Gateway against a local Mosquitto broker: discovery, last will, republish |
| `soak-a07f498-2026-10-13/` | 9 h bench soak of firmware a07f498 (transport only; sensor not wired) |
| `range-walk-office-2026-10-13/` | Office range walk with the weather-station firmware (SF7/0 dBm) |
| `rangetest-office-2026-10-13/` | Office range test with `firmware/rangetest`, both link directions, SF/power steps; `analyze.py` recomputes the numbers |
