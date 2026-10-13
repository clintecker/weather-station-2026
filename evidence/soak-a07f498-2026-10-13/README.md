# Bench soak: release a07f498273f7, 2026-10-13 (9 h 9 min)

**Not an H01 run.** The SHT45 is not wired, so every reading is an honest `sensor_fault` and the scorer's verdict is FAIL by design: 0 on-time *valid* readings. This record covers transport, timing and node health only.

## Setup
- Firmware: release `a07f498273f7` on both boards (see `firmware/stage0-node/RELEASES.md`).
  - TX: board A `003B00194142500E20353451`
  - RX: board B `0016001E4142500E20353451`
- Boards about 30 cm apart, 0 dBm, LoRa 915.0 MHz, 500 kHz bandwidth, SF7.
- Gateway: launchd agent `com.clintecker.weatherstation.gateway` on the bench Mac, `run-hw/`.
- Boot epoch 99 for the whole window. It started at 04:17:13Z, after the last G7 reset-test cycle, so the reset cause shows `pin`.
- The window ended when the boards were unplugged to take them to the office. The gateway logged `serial-lost` at 13:28:07Z and `receiver-silent` at 13:30:11Z, which is the G12 alarm working as designed.

## Result
Scored with `tools/h01_report.py --start 2026-10-13T04:18:00Z --hours 9.15` (`report.md`, `report.json`):

| Measure | Value |
|---|---:|
| One-minute intervals | 549 |
| Transport on time (≤120 s) | **549** |
| Missing | 0 |
| Late | 0 |
| Unknown-time observations | 0 |
| Latency median / max | 1.5 s / 2.0 s |
| Gateway rejections (NACK) | 0 |

**Health reports (kind 4).** All 37 expected reports arrived, one every 15 min from uptime 1 s to 32,401 s. Every report shows:
- `journal_pending=0`, `journal_lost_total=0`, `abandoned_total=0`
- `missed_acks_since_boot=0`, `rejected_replies_since_boot=0`
- `link=linked`, `reset_cause=pin`
- `journal_torn_slots=1`: one slot burned by the earlier G7 reset-during-write test. This is expected and stays put until that journal page is recycled.

**RX liveness.** 550 RX `#alive` lines in the window, one per minute. No receiver-silent alarm until the unplug.

## What it shows
- With the link healthy, every reading committed within about 2 s and no ACK was lost in 9 hours.
- The one-per-minute schedule held with no drift into neighbouring intervals: each interval counted exactly once.
- This says nothing about range, real placement, sensor behaviour or power. Those are still H01 work.
