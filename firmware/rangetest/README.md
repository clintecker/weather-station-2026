# Range test (bench tool)

Measures the LoRa link in **both directions about once a second** while you walk. Built from ST's
SubGHz_Phy PingPong (STM32CubeWL v1.6.0, see `readme.txt`); `firmware/pingpong` stays as the recorded
smoke test. Not the weather-station protocol and not H01 evidence.

Both boards run the same image. They bounce a 16-byte packet back and forth. Each packet carries what
the sender measured of the other board's previous packet, so one console logs both directions.

## Buttons (either board; both boards switch together)

| Button | Action |
|---|---|
| B1 | Mark a spot: `#rt mark n` on that board's console, one green blink |
| B2 | TX power one step down: +22 → +14 → +10 → 0 dBm, then back to +22 |
| B3 | Spreading factor one step down: SF12 → SF10 → SF9 → SF7, then back to SF12 |
| RESET (black) | Restart that board |

Green blinks after B2/B3 show the requested position on the ladder (1 blink = top).
Presses before the next exchange stack into one change.

**Boot and fallback are SF12 / +22 dBm**, the longest reach. A restarted board adopts the settings of
the first packet it hears. About 30 s without contact returns both boards to SF12 / +22, so they meet
again anywhere the strongest setting reaches. Step down from there to find the cheapest setting that
still works. At close range on a desk, +22 dBm overloads the receiver: readings are meaningless there.

How a change is agreed: the proposal travels in a packet sent with the current settings; the peer acks
and switches once the ack is sent; the proposer switches on hearing the ack. The first packet heard with
the new settings commits them. If nothing is heard for 5 receive windows after a switch, both roll back.
Logic and tests: `App/rt_proto.c`, `tests/test_rangetest.py`.

Fixed: 915.0 MHz, 500 kHz bandwidth (FCC §15.247(a)(2) decision, 2026-10-12), CR 4/5.

## Build, flash, log

```sh
cd firmware/rangetest && make
make flash SERIAL=003B00194142500E20353451     # then the other board
# log one board by its ST-LINK serial (port names change with the USB socket):
.venv/bin/python tools/rangetest_log.py 0016001E4142500E20353451 evidence/<run>/rangetest.csv
```

The image is about 36 KB and stays below the weather-station node state at `0x08010000` (page 32),
so the provisioned key and journal survive. Put the weather-station release back afterwards (see
`firmware/stage0-node/RELEASES.md`) and confirm `STATUS` shows the expected `kcv`.

Console lines (115200 8N1): `#rt rx ping|pong seq= rssi= snr= peer_rssi= peer_snr= sf= pwr= peer_sf=
peer_pwr=`, `#rt miss`, `#rt cfg … switched|commit|rollback|adopted|fallback`, `#rt propose`, `#rt mark`.
ST's own `OnRxTimeout` / `OnRxError` lines tell a silent window from a corrupted packet.
