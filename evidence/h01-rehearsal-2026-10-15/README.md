# H01 lab rehearsal, 2026-10-15 (interrupt-driven firmware)

**Not an H01 result.** A 24-hour run on the bench (the gateway Mac's desk, not the intended
placement), scored with the H01 rules as a rehearsal of release `7eb79f64f2bd`: the interrupt-driven,
refactored, reviewed firmware (docs/firmware-event-model.md, docs/power-of-ten.md). Placement for
this run was left to the bench (Clint, 2026-10-15: "it doesn't truly matter where the TX is").

| Item | Value |
|---|---|
| Start | 2026-10-15T22:37:00Z (24 h window ends 2026-10-16T22:37:00Z) |
| Firmware | release `7eb79f64f2bd` on both boards (firmware/stage0-node/RELEASES.md), protocol draft 5 |
| Gateway | `ws0 serve` at commit `7eb79f64f2bd`, run directory `run-d6` (key `kcv=e03059`), MQTT to Home Assistant on, dashboard on |
| TX | board A `003B00194142500E20353451`, USB to the gateway Mac, on the desk; SHT45 in room air (~23 C, ~55 %RH at start) |
| RX | board B `0016001E4142500E20353451`, USB to the gateway Mac |
| Link at start | -29 dBm, SNR 13-14 (gateway side) |
| Radio | 915.0 MHz, 500 kHz, SF7, CR 4/5, 0 dBm (bench values) |
| Host | Desktop Mac that never sleeps |

Before the start (not part of the window): both boards flashed 22:33Z, gateway restarted 22:34:30Z;
epoch 42 seq 0 and 1 stored and acknowledged 22:35-22:36Z.

New in this firmware and worth reading at the end: TX `#timing` and `#counts` (task/interrupt
peaks, `check_fails`, `held_lost`, `unexpected`), RX `#alive` (`crc_errors`, `hdr_errors`,
`frames_lost`, `relistens`, task/interrupt peaks), and the gateway's `rx_faults` table
(`tools/rx_faults.py`).

Score at the end with:

```sh
.venv/bin/python tools/h01_report.py --db run-d6/observations.sqlite3 --station station-01 \
  --start 2026-10-15T22:37:00Z --hours 24 --output evidence/h01-rehearsal-2026-10-15/report
```
