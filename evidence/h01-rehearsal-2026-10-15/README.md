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

## Result: ended early (Clint, 2026-10-16 15:05Z: "24 hours is arbitrary")

Scored over the first **16 hours** (22:37Z to 14:37Z; the scorer takes whole hours). **Lab rehearsal,
not H01**; the scorer's "PASS" heading is its verdict on these rules only. Report:
[`report/report.md`](report/report.md).

| Measure | Value |
|---|---:|
| On-time valid readings | 960 of 960 intervals (951 required) |
| Late / missing / sensor faults / gateway rejections | 0 / 0 / 0 / 0 |
| Resets | none (one boot epoch, TX uptime 59,494 s at 15:05Z) |
| Latency, sample to gateway | median 1.5 s, max 2.0 s |
| TX at 15:05Z | sent 991, acked 991, no_ack 0, abandoned 0, `check_fails=0`, `unexpected=0`, `held_lost=0` |
| TX `#timing` peaks | task 23,849 µs (`sensor_task`: the minute report's journal write includes a 22 ms page erase), interrupt 228 µs (radio), erase 22,042 µs, program 94 µs |
| RX `#alive` at 15:05Z | forwarded 1,058, dropped 3, `frames_lost=0`, `relistens=0`, `hdr_errors=81`, `crc_errors=0`, `trace_drops=0`; task peak **1,888 µs** (`process`), interrupt peak 216 µs (radio) |
| Bad receptions (gateway `rx_faults`, `tools/rx_faults.py`) | 80 header failures, 0 CRC failures. Spread over the minute (none at the TX's seconds :01-:03); RSSI mostly -93 to -95 dBm (noise floor), a few at -64 to -66 dBm (another transmitter nearby). The 3 RX drops were zero-length packets (`len=0`) |

The scorer warned that 587 readings lie within 2 s of an interval edge: the TX samples at second
:01-:02 of the minute and the window starts on :00. A scoring-alignment note, not a fault (no
interval held two readings).

Open: the RX `process` task's 1.9 ms peak (the longest thing either board does) is unexplained; the
next firmware times each step of it and separates interrupt time (2026-10-16).
