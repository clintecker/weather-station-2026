# Range test (bench tool)

This tool measures the LoRa link in **both directions about once a second** while you walk. It's built from ST's
SubGHz_Phy PingPong (STM32CubeWL v1.6.0).
The node and this tool share the board code, linker script and build rules in `firmware/board/nucleo-wl55jc`.
This directory holds only the application (`SubGHz_Phy/App/`, `App/rt_proto.*`) and its sequencer
task list (`Core/Inc/utilities_def.h`). It doesn't use the weather-station protocol, and its results aren't H01 evidence.

Both boards run the same image. They bounce a 16-byte packet back and forth. Each packet carries what
the sender measured of the other board's previous packet, so one console logs both directions.

## Buttons (either board; both boards switch together)

| Button | Action |
|---|---|
| B1 | Mark a spot: `#rt mark n` on that board's console, one green blink |
| B2 | TX power one step down: +22 → +14 → +10 → 0 dBm, then back to +22 |
| B3 | Spreading factor one step down: SF12 → SF10 → SF9 → SF7, then back to SF12 |
| B4 (RESET, black) | Restart that board |

After B2 or B3, the green blinks show the requested position on the ladder (1 blink = top).
If you press more than once before the next exchange, the presses add up to one change.

**Boot and fallback are SF12 / +22 dBm**, the longest reach. A restarted board adopts the settings of
the first packet it hears. After about 30 s without contact, both boards go back to SF12 / +22. That way they find each other
again anywhere the strongest setting reaches. Step down from there to find the cheapest setting that
still works. At close range on a desk, +22 dBm overloads the receiver, so you can't trust the readings there.

Here's how the two boards agree on a change:
1. The proposer sends the proposal in a packet on the current settings.
2. The peer sends an ack and then switches.
3. The proposer switches when it hears the ack.
4. The first packet either board hears on the new settings commits them.
5. If nothing comes in for 5 receive windows after a switch, both roll back.

The logic is in `App/rt_proto.c` and the tests are in `tests/test_rangetest.py`.

Fixed: 915.0 MHz, 500 kHz bandwidth (FCC §15.247(a)(2) decision, 2026-10-12), CR 4/5.

## Build, flash, log

```sh
cd firmware/rangetest && make
make flash SERIAL=003B00194142500E20353451     # then the other board
cd ../..                                       # the logger runs from the repo root
# log one board by its ST-LINK serial (port names change with the USB socket):
mkdir -p evidence/<run>
.venv/bin/python tools/rangetest_log.py 0016001E4142500E20353451 evidence/<run>/rangetest.csv
```

Flash both boards with the same build. The packet version byte (`RT_VERSION` in `App/rt_proto.h`) is still 1
across tool versions v1–v3. So boards running different builds talk to each other and you get no warning.
Status as of 2026-10-13 (about 17:00Z): we built v3 (SF12 / +22 dBm boot and fallback) and tested it on the host, but it's **not yet flashed**.

The image is about 36 KB. It links with the board's shared linker script, which stops at the end of the 190 KB
application region (pages 0–94). So a range-test build can't reach the weather-station node state
at `0x0802F800` (page 95), and the provisioned key and journal survive. Afterwards, put the weather-station release
back (see `firmware/stage0-node/RELEASES.md`). Then check that `STATUS` shows the expected `kcv`.

Logger (`tools/rangetest_log.py <board> <csv>`):
- `<board>` is an ST-LINK serial number (preferred) or a `/dev/...` port path. The logger reopens the port after a USB dropout and records a `usb` row.
- The logger appends to the CSV and writes the header only once. The CSV's directory must already exist.
- Columns: `utc` (time of day, `HH:MM:SS.mmm`, no date), `event`, `sf`, `pwr_dbm`, `up_rssi`, `up_snr`, `down_rssi`, `down_snr`, `peer_sf`, `peer_pwr_dbm`, `detail`.
- `event` is one of `rx`, `miss`, `rx_timeout`, `rx_error`, `cfg`, `propose`, `mark` or `usb`.
- "up" is what this board heard. "down" is what the other board reported hearing of this board's previous packet.
- The logger prints a summary line every 10 s when something changed, or every 2 minutes as a heartbeat.
- It warns `SETTINGS MISMATCH` after 3 packets in a row from a peer on different settings.

The console runs at 115200 8N1. It prints these lines:
- `#rt rx ping|pong seq= rssi= snr= peer_rssi= peer_snr= sf= pwr= peer_sf= peer_pwr=`
- `#rt miss sf= pwr=`
- `#rt cfg sf= pwr= boot|switched|commit|rollback|adopted|fallback` (the board prints `boot` once at start-up)
- `#rt propose sf= pwr=`
- `#rt mark n`

ST's own `OnRxTimeout` / `OnRxError` lines show you if the receive window was silent or if a corrupted packet came in.
