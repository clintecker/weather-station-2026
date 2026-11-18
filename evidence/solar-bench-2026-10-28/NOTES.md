# Solar bench, 2026-10-28: notes on benchlink.csv

- Battery plugged straight into the bq24074's own "LiPo Batt" socket (not through the INA228 shunt):
  `ishunt_ma` carries no battery current. Battery current = `charge_ma` (ISET pin) while PGOOD; the load
  `load_ma` (OUT / 100 ohm) comes from the cell when PGOOD is off.
- INA228 VBUS jumpered to the charger's OUT column: `vout_v` is OUT, not the cell.
- **Before 14:50:08 local, the gauge's battery input was on OUT** (its jumper went to the INA228 VIN-
  column, which was tied to OUT): `vcell_v`, `soc_pct` and `rate_pct_h` before then describe OUT, not
  the cell. From 14:50:08 the gauge pigtail is jumpered to the charger's LIPO column (B:h31 -> B:d51);
  the gauge restarted then (SoC re-estimated at 17 %).
- 14:31:02 and 14:31:18: TX reboots (seq back to 0). ~14:32:2x: one packet lost while the RX was reflashed.
- From ~14:40 the sun moves off the panel (indoor window): the charge current falls with it.
- ~15:26 local: USB-C plugged into the charger (charging ~936 mA, constant current). The bench cannot tell
  USB-C from the solar panel: both feed the charger's one input. Rows from here are USB charging, not solar.
- 15:3x: CSV gained a `vin_v` column (packet version 2: the charger's VBUS through a 20k/10k divider on
  A2); earlier rows have it empty. Backup of the CSV before the change: benchlink.before-v2.csv.
- **No data 15:40:33 to 15:44:50**: the RX was unplugged while the TX was connected for flashing.
- From 15:44:50 `vin_v` is live: USB-C under ~990 mA reads ~4.57 V (the supply sags to the charger's
  VIN-DPM limit). The divider resistors add about +-3 %.

## 2026-10-29

- 17:24:20 (Oct 28) to 08:48:29: no packets for 15 h 24 min. The Mac stayed awake and the RX stayed on USB
  (no reconnects); the TX's next packet had seq 0 and uptime 5 s, so the TX was reset or re-powered at 08:48.
  Cause unknown: the bench firmware (v2) had no watchdog and its HardFault handler spins, so a hang or a
  lost supply both look like this. Fixed in v3 (watchdog, reset cause and crash record in every packet).
- About 13:05: the breadboard moved to the desk for the v3 flash and the drills. The USB-C charger stayed
  behind: no charger input from 13:07. The TX restarted at 13:07:15 (seq 0) on the Mac's USB.
- 13:07:36: the TX console is recorded to tx-console.log (tools/benchlink_console.py).
- The uptime field is HAL_GetTick() / 1000, and on this board HAL_GetTick() reads the RTC, which survives
  a reset and restarts only at power-on (no backup battery on the NUCLEO). Seen at 13:12: after the flash's
  pin reset the v3 TX's packet 4 still read 375 s. So the 08:48 packet's uptime of 5 s means the TX had
  lost power, not just been reset: most likely its outlet was switched off about 17:24 and on about 08:48.
- 13:11-13:12: RX and TX flashed with benchlink v3 (watchdog, reset cause and crash record, packet v3).
  The logger restarted at 13:12:16 (CSV migrated to 35 columns; backup benchlink.csv.before-35-columns;
  events now in benchlink-events.csv). The first v3 boot reads reset=power: v2 never cleared the reset
  flags, so they still held the 13:07 power-up.
- 13:38-14:07 drills on benchlink v3 (all passed; events in benchlink-events.csv): B1 hang -> watchdog reset
  in 7 s; B2 crash -> software reset with the crash PC (the first try crash-looped while B2 was held:
  fixed, buttons now arm only after a release and light red/green); B3 lost radio done -> "radio stuck",
  watchdog reset; pin reset (flash) on both boards; TX USB unplugged twice -> reset=power, uptime and
  crash record cleared, silence start/end logged; RX B1 hang -> RX watchdog reset in 7 s, one packet lost.
- Found by the unplug drill: unplugging the TX left the RX's serial port open on the Mac but delivering
  nothing while the RX kept printing. The loggers now reopen a port after 25 s without a line; the second
  unplug drill showed rx_port_reopen and the data resuming on its own.
- 14:17: the RX logger, the TX console logger and the dashboard now run as launchd agents
  (~/Library/LaunchAgents/local.benchlink.{logger,console,dash}.plist, KeepAlive, from bench-tools/ here),
  so they restart after a crash or a reboot. Remove after the run: launchctl bootout gui/501/local.benchlink.<name>
  and delete the plist. The logger raises a macOS notification after 2 min with no packet. The dashboard
  shades every gap over 30 s with how the TX came back, and shows a red banner when the data is over 30 s old.
- From 14:17 the TX stays on the Mac's USB, with no charger input (no panel, no USB-C): an overnight
  discharge of the cell into the 100 ohm load.
- 14:45: both boards re-flashed with the reviewed v3 (TX 5721888e..., RX 5d4be6a4...) and the three launchd
  jobs restarted on the reviewed tools. From here uptime_s is real seconds; before, it was RTC ticks / 1000
  (2.4 % high). The flash's pin reset shows as reset=pin, boots=2 on the TX.
