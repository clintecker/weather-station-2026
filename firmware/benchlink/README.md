# Bench telemetry link

A bench test of the power breadboard (board B of `hardware/bench-breadboard-r0`): the bq24074 charger,
the cell, the 100 ohm test load, the INA228 and MAX17048 on the I2C hub, and an SHT45. The TX NUCLEO reads
them and sends one packet every 5 s over plain LoRa. The RX NUCLEO prints every packet. A logger on the
Mac writes them to a CSV, and a local dashboard charts them. It was built to watch a cell charge from the
panel in the day and discharge at night, and to keep doing so unattended.

**Not the weather-station firmware, not its protocol, and not H01 evidence.** Packets are not encrypted
or authenticated. The node firmware is [`../stage0-node/`](../stage0-node/README.md).

Radio: 915 MHz, 500 kHz bandwidth, SF7, CR 4/5, the project's bench settings
(`../stage0-node/App/radio_cfg.h`; 500 kHz is FCC 15.247 digital modulation). The power, 10 dBm, is this
tool's own: margin across a room for a day's run.

## Build and flash

```sh
cd firmware/benchlink
make ROLE=tx flash SERIAL=003B00194142500E20353451   # the TX board
make ROLE=rx flash SERIAL=0016001E4142500E20353451   # the RX board
```

`make ROLE=tx` alone builds `build/tx/benchlink-tx.elf` and `.bin` (the same for `rx`). Flashing writes
only the application region: the node's key and journal (pages 55 to 127) survive. To go back to the
node firmware, flash it as in [`../stage0-node/README.md`](../stage0-node/README.md), "Build and flash".

The build shares the board code with the node ([`../board/nucleo-wl55jc/`](../board/nucleo-wl55jc/)),
the register decoding with the I2C tool (`../i2cscan/App/bench_regs.c`) and the crash record with the
node (`../stage0-node/App/fault.c`). It keeps its own:

| File | What |
|---|---|
| `Core/Src/stm32wlxx_it.c` | the board's, with the HardFault and NMI handlers recording the crash and resetting (as the node's) instead of spinning; without the node's flash error-correction hook |
| `Core/Inc/utilities_def.h` | the sequencer tasks: `CFG_SEQ_Task_Scan` (the TX's 250 ms tick, the RX's received packet) and `CFG_SEQ_Task_Guard` (the 1 s watchdog check) |
| `App/subghz_phy_app.h` | `SubghzApp_Init`, where the board code hands over to `App/benchlink.c` |

Tests: `tests/test_benchlink.py` (the packet and SHT45 code compiled for the host against the logger's
decoder, and the three tools below). The drills below exercise the boards.

## Wiring

On top of the I2C hub wiring of [`docs/hardware/bench-station-wiring.md`](../../docs/hardware/bench-station-wiring.md)
section 2 (SDA CN5.9, SCL CN5.10, 3V3 CN6.4, GND CN6.6), on the TX NUCLEO:

| Signal | TX pin | Header | From |
|---|---|---|---|
| bq24074 CHG | PB10 | CN10.25 | the charger's CHG pin, direct (internal pull-up) |
| bq24074 PGOOD | PB8 | CN10.27 | the charger's PGOOD pin, direct (internal pull-up) |
| Charge current | PB1, ADC1_IN5 | CN8.1 (A0) | the charger's ISET pin, direct |
| Charger input | PA10, ADC1_IN6 | CN8.3 (A2) | the charger's VBUS through a divider: 20 kohm (two 10 kohm in series) from VBUS to the pin, 10 kohm from the pin to GND. The pin sees VBUS / 3 (2.1 V at the panel's 6.3 V; up to 9.9 V keeps the pin under 3.3 V) |

The INA228's VBUS jumper goes to the charger's OUT, so its bus voltage is OUT, the load's voltage. The
MAX17048 must sense the cell itself (its pigtail on the charger's LIPO terminal), not OUT. The breadboard
map (`hardware/bench-breadboard-r0/`) does not include the ISET wire or the divider.

PB8 and PB10 are 5 V tolerant (FT_f, STM32WL55 datasheet DS13293 Rev 5, Table 20), but only with the
internal pull-up off above VDD + 0.3 V (Table 26, note 3), and this firmware turns the pull-ups on. CHG and
PGOOD light their LEDs from OUT and measured at most 2.9 V on the bench, so they stay below that limit.

## What it measures

Every 250 ms the TX samples the INA228 (shunt and bus voltage) and the two ADC channels (16 conversions
each, scaled by VDDA from the factory VREFINT calibration). Every 5 s it adds the INA228 die temperature,
the MAX17048 (cell voltage, state of charge, rate), the SHT45 (temperature, humidity, CRC checked) and the
CHG and PGOOD pins, then sends one packet. The layout is in [`App/bl_pkt.h`](App/bl_pkt.h): 78 bytes,
version 3, CRC-16/CCITT-FALSE.

The CSV columns that are not plain readings:

| Column | From |
|---|---|
| `charge_ma`, `charge_min_ma`, `charge_max_ma` | the mean, minimum and maximum ISET voltage over the 5 s: I = 400 x V_ISET / R_ISET (TI SLUS810 eq. 3), R_ISET = 890 ohm for the board's 1.0 A jumper. About +-10 % |
| `load_ma` | OUT / 100 ohm (the bench load). The idle 3.3 V regulator's ~1 mA is left out |
| `vin_v` | the charger's input: the TX multiplies the A2 reading by 3 (the divider) before sending |
| `vout_v` | the INA228 bus voltage (OUT) |
| `vcell_v`, `soc_pct`, `rate_pct_h` | the MAX17048 as read. Its state of charge is a voltage model: it reads high while the cell charges |

Known limits:

- The charge current is the charger's own regulation signal. It reads the current into the cell, not what
  the input delivers.
- The INA228's shunt (`ishunt_ma`) carries no current while the cell sits in the charger's LIPO socket,
  as on the 2026-10-28 bench. On that bench a battery lead through the breadboard (about 0.2 ohm) made
  the charger end 1 A charges early, so the cell went into the socket directly.

## Supervision

Both roles run under the independent watchdog (IWDG, about 8 s; [`App/bl_guard.h`](App/bl_guard.h), after
the node's `watchdog.c`). A 1 s timer only *requests* a check. The check runs in the main loop and refreshes
the watchdog only when the role shows progress:

| Role | Healthy when | Otherwise |
|---|---|---|
| TX | a transmission finished ("TX done") within the last 20 s, and no transmission has been in flight for over 5 s | `#bl radio stuck ...` or `#bl no packet out ...`, then a watchdog reset |
| RX | every heard packet is handled within 5 s | a watchdog reset. A receiver that hears nothing for 60 s is restarted (`#bl rx rearm`, counted), not reset |

A hung main loop or a stopped timer resets the board as well. A HardFault or an unexpected NMI records the
program counter and fault registers in RTC backup registers DR5-DR11 (`../stage0-node/App/fault.c`) and
resets at once; the next boot prints them as `#fault ...`.

Every boot prints `#bl boot role=<tx|rx> reset=<cause> boots=<n> faults=<n>`. Every TX packet carries the
reset cause, `boots`, `faults` and `fault_pc`. The causes, and what they meant on the bench:

| `reset=` | Cause |
|---|---|
| `power` | power-on or brownout: the board lost power (the brownout flag is also set at power-on, so the two read the same) |
| `pin` | the NRST pin: the black reset button, or a flash |
| `watchdog` | the IWDG: the role stopped showing progress |
| `software` | a software reset: after a recorded crash (`faults` rises and `fault_pc` is set) |
| `lowpower`, `option-bytes`, `unknown` | not expected on this bench |

`boots` (backup register DR12) and `faults` count since the board last lost power: the NUCLEO has no
backup battery, so a power loss clears the backup domain. The first boot of this firmware after older
firmware can read `power` from flags the older firmware never cleared.

Times: on this board `HAL_GetTick()` counts 1/1024 s RTC ticks, not milliseconds (the board's
`Core/Src/timer_if.c`; the node's `App/clock.h`). The firmware converts, so `uptime_s` and the RX
heartbeat's `up=` are seconds. The tick count keeps running through a reset and restarts only when the
board loses power: **uptime is the time since power-on**, so a small uptime after a gap means the board
lost power, whatever the firmware version. It wraps after 48.5 days; the logger therefore takes a reboot
from the sequence number and the boot count, not from the uptime.

The TX also restarts the I2C bus after any failed transfer. Before re-initialising it, it checks SDA: if a
part holds SDA low (it lost a clock mid-byte), it clocks SCL up to nine times and sends a STOP (UM10204
3.1.16). The packet counts the restarts and the stuck-SDA recoveries.

## Console lines

| Board | Line | Meaning |
|---|---|---|
| TX | `#bl seq=<n> flags=<hex> vin_uv=... vout_uv=... ...` | one packet's readings, as sent |
| TX | `#bl tx timeout` | the radio reported a transmit timeout (counted in `tx_timeouts`) |
| TX | `#bl radio stuck: no done or timeout after <ms> ms; watchdog reset next` | a transmission never finished |
| TX | `#bl no packet out for <s> s; watchdog reset next` | no transmission finished for 20 s |
| TX | `#bl i2c sda held low: freed` (or `still low`) | the bus recovery ran |
| TX | `#error i2c init`, `#error adc init` | a peripheral did not start |
| RX | `#bl rssi=<dBm> snr=<dB> len=<n> hex=<packet>` | a received packet, raw |
| RX | `#bl hb up=<s> good=<n> bad=<n> err=<n> quiet_s=<s> rearm=<n> boots=<n> reset=<cause> faults=<n>` | heartbeat, every 10 s |
| RX | `#bl rx error` | a reception failed its CRC or header |
| RX | `#bl rx rearm: nothing heard for <s> s` | reception restarted after 60 s of silence |
| both | `#bl boot ...`, `#fault ...` | as above |
| both | `#bl drill ...`, `#test-fault: ...` | a drill (below) |
| both | `#error iwdg init` | the watchdog's settings did not take within ST's wait (it runs either way) |

## LEDs

| LED | TX | RX |
|---|---|---|
| green (LD2), 80 ms | a packet went out | a good packet came in |
| red (LD3), 80 ms | a transmit timeout | a bad packet or a reception error |
| red, steady | a drill button is held | the same |
| red and green, steady | the drill fired: let go | the same |

While a drill button is down the drill owns the LEDs: packet flashes are skipped.

## Drills

Each drill proves one recovery path. Hold the NUCLEO button (labelled B1, B2, B3 on the board) for about
2 s (the firmware looks once a second and wants two looks in a row): red lights once the hold is seen, red
and green together once the drill fires. A button held through a boot is ignored until it has been
released, so a drill cannot repeat itself.

| Drill | Board | Expected | 2026-10-29 |
|---|---|---|---|
| B1: hang the main loop | TX | `#bl drill hang ...`, then within about 8 s `reset=watchdog` | watchdog reset after 7 s; about 15 s of data lost |
| B2: crash (a read of an unmapped address) | TX | `#test-fault ...`, then `#fault kind=hard ... bfar=20040000` and `reset=software` | as expected (the first try, before the release rule, crashed again on every boot while B2 was held) |
| B3: lose the next "TX done" | TX | `#bl drill radio ...`, `#bl radio stuck ...` after 5 s, then `reset=watchdog` | as expected; about 25 s lost |
| black reset button, or a flash | both | `reset=pin`; uptime and the crash record kept | as expected |
| unplug USB for about 40 s | TX | `silence_start`, `silence_end`, then `reset=power` with uptime near 0 and the crash record cleared | as expected, twice |
| B1: hang the main loop | RX | `#bl drill hang ...`, then `reset=watchdog` | watchdog reset after 7 s; one packet lost |

The 2026-10-29 drills ran on the firmware before the review fixes (the times in ticks, the drill owning
the LEDs); the run's logs are kept outside the repository.

## Logging and the dashboard

Three tools in [`../../tools/`](../../tools/README.md), run from the repository root:

```sh
.venv/bin/python tools/benchlink_log.py --serial-number 0016001E4142500E20353451 --out evidence/<run>/benchlink.csv
.venv/bin/python tools/benchlink_console.py --serial-number 003B00194142500E20353451 --out evidence/<run>/tx-console.log
.venv/bin/python tools/benchlink_dash.py --csv evidence/<run>/benchlink.csv [--sources evidence/<run>/sources.csv] \
    [--anchor "YYYY-MM-DD HH:MM:SS"] [--gauge-valid-from "YYYY-MM-DD HH:MM:SS"]
```

### benchlink_log.py

It decodes every packet line from the RX (packet versions 1 to 3), checks the CRC and appends one CSV
row, synced to disk. It opens the port exclusively, so a second program cannot split the lines.

Beside the CSV (`<run>/benchlink.csv`), `<run>/benchlink-events.csv` records what explains a gap. The
events (`EVENTS` in the tool; the alert ones also raise a macOS notification, at most one per event name
every 5 min):

| Event | When |
|---|---|
| `logger_start`, `csv_prepared` | the logger started; what it did to the CSV first (below) |
| `rx_connected`, `rx_absent`, `rx_disconnected` | the RX port opened; the RX is not on USB (**alert**); the port failed |
| `rx_open_failed` | the port is there but will not open, for example another program holds it (**alert**; logged once, then a count every 5 min) |
| `rx_port_reopen` | no line at all for 25 s: the port is closed and opened again. Seen 2026-10-29: unplugging the other NUCLEO on the same USB hub left this port open but delivering nothing while the RX kept printing. A reopen that brings nothing back doubles the wait, up to 400 s |
| `rx_heartbeat_lost`, `rx_heartbeat_back` | no line from the RX for 30 s with its port open: the RX is hung (**alert**); and when lines come back |
| `rx_note` | an RX boot, crash, re-arm, drill, reception error or init error line |
| `tx_first_packet`, `tx_boot` | the first packet; a TX reboot (the sequence number went back or the boot count changed), with its reset cause |
| `packets_missed`, `tx_tx_timeouts`, `tx_i2c_restarts`, `tx_i2c_unsticks` | missing sequence numbers; a TX error counter rose |
| `bad_packet` | a packet line that fails its length, version or CRC check |
| `silence_start`, `silence_end`, `alert` | no packet for 30 s; the first packet after; no packet for 2 min, or none since the logger started (**alert**) |
| `csv_write_failed`, `csv_write_resumed` | a row could not be written (a full disk: **alert**; reading goes on and the next packet retries); writing works again |
| `host_sleep` | the Mac slept (the wall clock ran ahead of the monotonic clock) |
| `logger_error`, `logger_crash` | a line the logger could not handle (it goes on); the logger stopped on an exception (launchd restarts it). Both **alert** |

Before the first row, the logger prepares the CSV: an older header (its columns all known) is rewritten
to the current one, with a copy kept as `benchlink.csv.before-<n>-columns` (`<n>`, the new header's
column count); a file it cannot use (unknown columns) is moved to `benchlink.csv.set-aside-<time>` and a
new CSV starts; a last line cut off by an earlier failed write is ended, so the next row does not join
onto it.

### benchlink_console.py

It records a board's console to a text file, each line prefixed with the local time and its UTC offset.
Use it for the TX while the TX is on a Mac: if it stops, the last lines show where. It reopens a port that
stays silent for 25 s, and a failed write goes to stdout instead.

### benchlink_dash.py

It serves `http://127.0.0.1:8099/`: an animated energy-flow view, tiles and charts of the run (current,
battery current, state of charge, cell voltage, input source, temperature, humidity, RSSI with quality
bands). Every gap of over 30 s is shaded and lines break across it; a gap wide enough on screen is labelled
with its length, how the TX came back and the counted charge's estimate for it. A red banner shows when the
newest packet is over 30 s old, or when the page cannot load data (the page then says why and marks the
view stale). Unreadable CSV rows, such as a line the logger is still writing, are skipped and counted in
the status line.

The dashboard's state of charge is counted: the net battery current integrated from `--anchor`, a moment
when the cell had rested near 0 A, started from a typical Li-ion rest-voltage table (about +-10 %) and a
6600 mAh capacity. Without `--anchor` nothing is counted. A gap is bridged with the mean battery current at
its two ends, because the load runs whether or not the TX reports. `--sources` names known input windows
(`start,end,source` in local time) where the automatic USB-C or solar call is wrong; a line it cannot read
is reported in the status line. `--gauge-valid-from` hides the gauge's readings from before it sensed the
cell.

### Unattended

To keep the three running unattended on a Mac, make each a launchd agent with `KeepAlive` and
`RunAtLoad`, the repository as `WorkingDirectory`, and the virtualenv's Python with the tool's arguments
above, so they restart after a crash or a reboot. `tools/deploy/macos/install.sh` does the same for the
gateway and is a model. Run the tools from a copy that is not in a temporary directory: macOS clears
`/tmp` at boot.
