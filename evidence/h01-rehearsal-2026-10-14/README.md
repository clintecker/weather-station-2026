# H01 lab rehearsal, 2026-10-14

**Not an H01 result.** A 24-hour run in the office lab (not the intended placement), scored with the
H01 rules as a rehearsal. Placement is Clint's call; the PRD scores H01 "at intended placement".

| Item | Value |
|---|---|
| Start | 2026-10-14T18:54:00Z (24 h window ends 2026-10-15T18:54:00Z) |
| Firmware | release `bc5e6ede429c` on both boards (RELEASES.md), protocol draft 5 |
| Gateway | `ws0 serve` at commit `2e74bde39cc5`, run directory `run-d5` (key `kcv=5618eb`), MQTT to Home Assistant on, dashboard on |
| TX | board A `003B00194142500E20353451`, on a USB supply, taped to the lab AC unit; SHT45 in the AC's outlet air (about 6-7 C, 85-88 %RH at start) |
| RX | board B `0016001E4142500E20353451`, USB to the gateway Mac, across the room |
| Link at start | -52 dBm, SNR 12-13 (gateway side) |
| Radio | 915.0 MHz, 500 kHz, SF7, CR 4/5, 0 dBm (bench values) |
| Host | Desktop Mac that never sleeps (used 24/7) |

Before the start (not part of the window): TX moved 18:43-18:51Z (sessions 36, 37); the RX USB cable was
replugged twice (18:45:46Z, 18:50:23-18:51:24Z). The window starts after both.

Score at the end with:

```sh
.venv/bin/python tools/h01_report.py --db run-d5/observations.sqlite3 --station station-01 \
  --start 2026-10-14T18:54:00Z --hours 24 --output evidence/h01-rehearsal-2026-10-14/report
```

## Result (scored 2026-10-15T18:55Z)

The H01 scorer passes this window, but this is a **lab rehearsal, not H01**: office lab, not the
intended placement. The report's own "PASS" heading is the scorer's verdict on these rules only.
Full report: [`report/report.md`](report/report.md), [`report/report.json`](report/report.json).

| Measure | Value |
|---|---:|
| On-time valid readings | 1440 of 1440 intervals (1426 required) |
| Late / missing / sensor faults | 0 / 0 / 0 |
| Boot epochs (resets) | 1: no reset of the TX in 24 h |
| Gateway rejections | 0 |
| Latency, sample to gateway | median 1.5 s, max 2.0 s (sample time is whole seconds) |
| Frames received | 1440 observations acknowledged, 96 health reports |
| Link (gateway side) | -58 to -43 dBm, SNR 6 to 14 dB |
| Temperature / RH seen | 5.95 to 23.12 C, 48.4 to 94.4 %RH (AC outlet air, then the AC idle) |
| RX failed receptions (`#rx error`) | 46 in the window, none at the TX's transmit second; no RX drop, reboot, relisten or watchdog line. RX dropped 0 frames, so these were most likely all LoRa header failures (no payload): ambient 915 MHz noise or other devices. The new RX firmware logs each one (`#rx crc` with bytes, `#rx hdr`) |

Firmware during the run was `bc5e6ede429c`. The firmware that follows (interrupt-driven rework,
docs/firmware-event-model.md) was not part of this run and needs its own rehearsal.
