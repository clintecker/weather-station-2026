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
the register and ADC conversions with the node and the I2C tool (`../common/power_regs.c`; the bench
helpers in `../i2cscan/App/bench_regs.c`) and the crash record and boot counter with the node
(`../stage0-node/App/fault.c`). It keeps its own:

| File | What |
|---|---|
| `Core/Src/stm32wlxx_it.c` | the board's, with the HardFault and NMI handlers recording the crash and resetting (as the node's) instead of spinning; without the node's flash error-correction hook |
| `Core/Inc/utilities_def.h` | the sequencer tasks: `CFG_SEQ_Task_Scan` (the TX's 250 ms tick, the RX's received packet) and `CFG_SEQ_Task_Guard` (the 1 s watchdog check) |
| `App/subghz_phy_app.h` | `SubghzApp_Init`, where the board code hands over to `App/benchlink.c` |

Tests: `tests/test_benchlink.py` (the packet and SHT45 code compiled for the host against the logger's
decoder, and the three tools below). The drills below exercise the boards.

## Wiring

This wiring is the **official phase A power design** (spec
[`2026-10-29-power-telemetry-design.md`](../../docs/superpowers/specs/2026-10-29-power-telemetry-design.md)
sections 1 and 2): the node firmware uses the same MCU pins on the bench and in the field
(`../stage0-node/App/board_inputs.c:3-21`, the pin list, and `:66-73`, the pin defines). The pins were
proven with this tool on 2026-10-28/29 **except the shunt in the battery path**: the cell then sat in the
charger's own BATT (LIPO) socket, so the INA228's shunt carried no current. Step 1 of the
[build-progression decision record](../../docs/superpowers/specs/2026-10-29-build-progression-decisions.md)
(breadboard v2, change A, section 4.4) puts the pack through the shunt (record P3); phase A exit criteria
3 and 4 (the acceptance drill below and a 1 A charge that terminates normally with the shunt in the path)
prove that part.

On top of the I2C hub wiring of [`docs/hardware/bench-station-wiring.md`](../../docs/hardware/bench-station-wiring.md)
section 2 (SDA CN5.9, SCL CN5.10, 3V3 CN6.4, GND CN6.6), on the TX NUCLEO:

| Signal | TX pin | Header | From |
|---|---|---|---|
| Sensor power enable | PA9 | D9, CN5.2 (morpho alias CN10.19) | carrier only: unconnected on the bench (change C's load switch is deferred to the carrier, record 4.6 dated note, 2026-11-02); the hub, the INA228 and the gauge are all on the unswitched 3V3. The TX drives it high at start and keeps it high (`sensors_on`), harmless here |
| bq24074 CHG | PB10 | D6, CN9.7 (morpho alias CN10.25) | the charger's CHG pin, direct (internal pull-up) |
| bq24074 PGOOD | PB8 | D5, CN9.6 (morpho alias CN10.27) | the charger's PGOOD pin, direct (internal pull-up) |
| Charge current | PB1, ADC1_IN5 | A0, CN8.1 (morpho alias CN7.28) | the charger's ISET pin through 10 kohm 1 % at the charger end (R_ISER) into the PB1 node, which has 100 nF (C_ISET) and 1 Mohm (R_IPD) to logic ground (record M2). The pin reads V_ISET x 1 Mohm / 1.01 Mohm; the firmware sends the pin voltage and the logger applies the gain (`--iset-gain`) |
| Charger input | PA10, ADC1_IN6 | A2, CN8.3 (morpho alias CN7.32) | the charger's VBUS through a divider: 20 kohm (R4 and R5, two 10 kohm in series) from VBUS to the pin, 10 kohm (R6) from the pin to logic ground. The pin sees about VBUS / 3 (2.1 V at the panel's 6.3 V). Full scale is VDDA at the pin, so the input reads up to about 3 x VDDA (9.9 V at 3.3 V). The ratio is `VIN_DIVIDER_PPM` (`App/benchlink.c:157`, nominal 3000000, used at `:413`), to be replaced by the ratio of the three measured resistors (record M2; it must equal the node's `POWER_VIN_DIVIDER_PPM`) |

The power parts:

| Part | Connection |
|---|---|
| INA228 (0x40) | the shunt in the pack's + lead (record P3): pack plug, the pack-mating half of a cut #1131 (L_PACK_POS) to the CELL+ lever connector, a 22 AWG solid link (L_CELL_INA) to the screw terminal VIN+, the 15 mohm shunt, VIN- by L_INA_BATT to the BATT lever connector, and the board-mating half of the same #1131 (L_BATT_POS) into the charger's BATT socket. No breadboard contact in the path (record P1). Its VBUS is its own 22 AWG sense lead (L_VBUS) to the OUT lever connector (record P5), so its bus voltage is OUT, the load's voltage, not the cell. The back solder jumper from VBUS to VIN+ (SJ1) is open, checked by continuity |
| MAX17048 (0x36) | on the CELL+ node, upstream of the shunt: the red lead of a second cut #1131 in one of its BAT sockets (L_GAUGE_POS) in its own CELL+ position; its black lead (L_GAUGE_NEG) is insulated and unconnected, and the gauge takes ground over STEMMA QT (record P4, M4). Under current it reads the CELL+ node, above or below the pack terminal by I x R_pack (record M4). Never on the charger's BATT terminal and never on OUT |
| Battery path | limited span by span (spec section 11.2, amended 2026-10-29; build-sheet power check 7), each a DMM mV drop over the INA228 current at 0.8-1.0 A: the + span (pack plug, its JST PH pair, the leads, VIN+, the 15 mohm shunt, VIN-, to the charger's LIPO) at most 75 mohm; the - span (the charger's GND to pack -) at most 40 mohm; each pack-side span at most 28 mohm; each JST PH mating at most 20 mohm; each clamp or screw at most 5 mohm. Never through breadboard strips: a 0.2 ohm breadboard path ended 1 A charges early on 2026-10-28 |
| Charger input | the source on its own cable into the breakout's DC jack or its USB-C, solar or USB-C, never both; never through breadboard strips. Step 1: a floating USB-C wall adapter into the breakout's USB-C (L_USB_IN) |
| Ground | one STAR lever connector at pack negative (record P4): the pack's black lead, the charger BATT pigtail's black lead, the load return and the TIE (L_TIE, the only conductor between STAR and logic ground) |

The breadboard model ([`hardware/bench-breadboard-r0/`](../../hardware/bench-breadboard-r0/README.md))
includes all of it, by stable ids: the ISET network (R_ISER, C_ISET, R_IPD and the jumper to CN8.1), the
divider (R4 and R5 in series from VBUS, R6 to logic ground, and the jumper to CN8.3), the lever connectors
(joints WAGO_CELL_POS, WAGO_BATT, WAGO_SYS_OUT, WAGO_STAR), the battery leads (L_PACK_POS, L_PACK_NEG,
L_CELL_INA, L_INA_BATT, L_BATT_POS, L_BATT_NEG), the OUT and load leads (L_SYSOUT_POS, L_RLOAD_A,
L_RLOAD_B), the sense leads (L_GAUGE_POS, L_VBUS) and the charger input (L_USB_IN). Its
[build sheet](../../hardware/bench-breadboard-r0/build-sheet.md) lists them in sections 2 to 5 (jumpers,
leads, joints, power path; the jumpers' W-numbers change on every regeneration, the ids do not), and its
section "Power checks" has the measurements that go with them (R_ISET, the shunt verified against a
series reference, the battery-path spans, the gauge, OUT against VCELL).

PB8 and PB10 are 5 V tolerant (FT_f, STM32WL55 datasheet DS13293 Rev 5, Table 20), but only with the
internal pull-up off above VDD + 0.3 V (Table 26, note 3), and this firmware (and the node's) turns the
pull-ups on. CHG and PGOOD light their LEDs from OUT and measured at most 2.9 V on the bench, so they stay
below that limit; build-sheet power check 6 measures the worst case on the panel. PA10 (FT_fa, no pull)
allows at most min(VDD, VDDA) + 3.6 V and 5.5 V (Table 26): with the 3:1 divider a VBUS up to 16.5 V with
the MCU powered and about 10.8 V unpowered. The bq24074 charges only below its OVP (10.2-10.8 V).

## What it measures

Every 250 ms the TX samples the INA228 (shunt and bus voltage) and the two ADC channels (16 conversions
each, scaled by VDDA from the factory VREFINT calibration). Every 5 s it adds the INA228 die temperature,
the MAX17048 (cell voltage, state of charge, rate), the SHT45 (temperature, humidity, CRC checked) and the
CHG and PGOOD pins, then sends one packet. The layout is in [`App/bl_pkt.h`](App/bl_pkt.h): 78 bytes,
version 4, CRC-16/CCITT-FALSE. Version 4 is version 3's layout with change A's meaning: the ISET words are
the PB1 node behind the 10 kohm and 1 Mohm network, and the shunt is in the official orientation. The
logger applies `--iset-gain` and turns the shunt's sign into `battery_ma` for version 4 only. A version 3
or older packet (an old capture replayed, or an old TX paired with a new RX) keeps its own meaning: its
ISET words are the charger's ISET pin (no gain) and its `battery_ma` stays empty (`ishunt_ma` is logged
raw, as before). `tx_first_packet` and `tx_boot` name the version, with "before change A" for an old one.
Flash the TX and RX together.

The CSV columns that are not plain readings:

| Column | From |
|---|---|
| `ishunt_ma` | the INA228 shunt current **as the part counts it: + = into VIN+, out through VIN-**. With the official orientation (CELL+ on VIN+, the charger's BATT socket on VIN-, through the BATT joint; spec section 3.1, record P3) + is out of the cell, a discharge. The TX sends it unturned (`App/bl_pkt.h`, offset 16) |
| `battery_ma` | the battery current, **+ into the cell** (charging): `battery_ma = -ishunt_ma`, turned once by the logger (`battery_ma()`, `tools/benchlink_log.py:149-154`; version 4 packets only), the only place the bench tools turn it. Rows of an older CSV get it from their `ishunt_ma` when the logger rewrites the header, but only rows whose `version` is 4 or later; rows with no `version` (logged before that column existed) stay empty. It is the measured current only from the moment the cell went through the shunt: the dashboard's `--shunt-from` |
| `version` | the packet's version (`BL_VERSION`, 1 to 4): which meaning the row's ISET and shunt columns have. Version 4 is change A's |
| `charge_ma`, `charge_min_ma`, `charge_max_ma` | the mean, minimum and maximum ISET voltage over the 5 s: I = `--k-iset` (400) x V_ISET / `--r-iset` (1000 ohm: R9 behind the board's closed 1A jumper, ICHG 0.89 A typ; TI SLUS810 eq. 3), with V_ISET = the PB1 pin voltage / `--iset-gain` (0.990099, the 10 kohm and 1 Mohm network, nominal until the per-board fit; record M2). About +-10 % plus R_ISET's own tolerance (build-sheet power check 2 measures R_ISET). Empty when an ISET reading of the 5 s clipped (flag `BL_F_ISET_CLIP`, the node's `adc_clipped` rule). R_ISET 1000 ohm and the gain were adopted with change A, read by this workflow from record 7.1 P3; Clint to confirm (design D4/D5). **Earlier runs read 12 % high:** they were logged with R_ISET 890 ohm (record section 1.4); see "charge_ma of earlier runs" below |
| `load_ma` | OUT / `--r-load` (100 ohm, the bench load). The idle 3.3 V regulator's ~1 mA is left out. **A bench-only estimate**: the field has no fixed load resistor; phase B measures the load with its own INA228 |
| `vin_v` | the charger's input: the TX multiplies the A2 reading by `VIN_DIVIDER_PPM` / 10^6 (the divider, nominal 3) before sending. Under load it sags (input sag, below). A pin reading at or near full scale (an oversampled 4080 or more) is logged empty, as the node sends it INVALID |
| `vout_v` | the INA228 bus voltage: OUT, not the cell. During a charge OUT sits above the cell (check below) |
| `vcell_v`, `soc_pct`, `rate_pct_h` | the MAX17048 as read. `vcell_v` is the **CELL+ node, which includes the pack-lead drop** (record M4): under current it differs from the pack terminal by I x R_pack (about 25-35 mV at a 0.9 A charge); the dashboard shows VCELL - I x R_pack beside it. Its state of charge over-reads while the cell charges (below) |

Known limits:

| Limit | What it means |
|---|---|
| ISET is the charger's own regulation signal | it reads the current the charger drives into the battery terminal, not what the input delivers and not the net cell current (OUT's load is fed alongside). +-10 % (SLUS810 section 9.3.5.1) |
| Shunt bypassed before step 1 | on 2026-10-28/29 the cell sat in the charger's BATT (LIPO) socket, so the shunt carried no current and `ishunt_ma` read about 0 while the cell charged and discharged. **The 2026-10-28/29 `ishunt_ma`, `battery_ma` and the charge counters are invalid** (record D1: the runs are kept as evidence, those columns marked invalid by time window, not repeated). Step 1 fixes the bypass: the pack connects only through the shunt (change A, record P3), and while the INA228 meters the battery the pack never plugs into the charger's BATT socket. For a CSV that spans the rewire, start the dashboard with `--shunt-from` at the moment the cell went through the shunt |
| `charge_ma` of earlier runs | rows logged with `--r-iset 890` read 12 % high (1000 / 890 = 1.12; record section 1.4). `benchlink_dash.py --rewrite-iset 890 --events <run>/benchlink-events.csv` rescales `charge_ma` by 890 / 1000 only on the rows logged under a `logger_start` event that names `r_iset=890`, up to the next `logger_start`; other rows and the CSV on disk are unchanged (`tools/benchlink_dash.py:296-309`). The logger before this change wrote only `pid=` in `logger_start`, so rows it logged carry no `r_iset` and are not rescaled: read them as 0.89 x `charge_ma` |
| Input sag | the charger input under load is not the source's open-circuit voltage: a weak panel, or a 5 V USB-C source behind its cable and the breakout's Schottky diode (D2 or D4, SK34A; build-sheet CHGR note). What holds it depends on the #4755's EN2 jumper (SLUS810 table 7-2 and section 9.3.4.1.1). **EN2 low** (USB100/USB500): VIN-DPM holds IN at 4.35-4.63 V by cutting the charge current; termination detection is disabled and the safety timer runs slower, so a `vin_v` near 4.4-4.6 V while charging means VIN-DPM, not a 4.5 V source. **EN2 high, EN1 low** (the R_ILIM mode, expected on the board and required for phase B): VIN-DPM does not act, so a source that cannot supply the current is pulled down, as far as a FET drop above the cell; at low sun the charger may drop input power and cycle PGOOD and CHG (`docs/hardware/power-metering.md` section 5.4). Record EN1 and EN2 (build-sheet check B1) |
| Gauge SOC over-read | the MAX17048's SOC (ModelGauge) is a model of the cell voltage. While the cell charges its terminal voltage sits above its rest voltage, so `soc_pct` reads high (it can show near 100 % well before the charge ends) and settles back after the charge. Read it at rest; the node sends it as `battery_soc_pct` with the same caveat |
| bq24074 safety timer | the #4755 ties TMR to GND (Adafruit schematic), which disables every safety timer, so the 2026-10-28 early end was the 0.2 ohm path, not a timer fault (spec R11, closed 2026-10-29). Confirm TMR on the board in hand (build-sheet power check 10). Only with TMR floating is the fast-charge timer 4-6 h (SLUS810 `tMAXCHG`), shorter than a 1 A charge of 6.6 Ah from empty (6-7 h): then a long charge ends with CHG flashing at about 2 Hz until the input or CE is toggled; fit RTMR = 72 kohm (7.2-12 h) or start a 1 A charge at 3.85 V or more |
| Bench-only estimates | `load_ma` (OUT / 100 ohm), `battery_ma` before `--shunt-from` (the dashboard's ISET - load fallback) and the dashboard's counted SOC (OCV-anchored) are estimates for this bench. None of them goes to the node, the protocol or the gateway |

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

`boots` and `faults` count since the board last lost power: the NUCLEO has no backup battery, so a power
loss clears the backup domain. They are the node's own counters, kept the same way, so the bench and the
node's health report (spec section 6.2) agree:

| Counter | Register | Owner |
|---|---|---|
| `faults` | DR11, the crash count of the crash record DR5-DR11 (DR6 the PC) | `fault_record()` in `../stage0-node/App/fault.c` (linked here), read by `fault_count()` |
| `fault_pc` | DR6, kept after `fault_report()` until the next crash or a power loss | `fault_last_pc()` (`fault.c:58`): 0 while the crash count is 0 |
| `boots` | DR12, zeroed at a power-on reset, then one added a boot, saturating at 0xFFFF | `fault_boot_note()` (`fault.c:60-64`), its only writer, called once a boot by `bl_guard.c:59` here and by the node's `app_tx.c` and `app_rx.c`; read by `fault_boots()` |

So flashing benchlink after the node (or back) neither loses nor double-counts a boot. A brown-out reads
as `power` too and restarts the count (`../stage0-node/App/watchdog.h`). The first boot of this firmware
after older firmware can read `power` from flags the older firmware never cleared.

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
.venv/bin/python tools/benchlink_log.py --serial-number 0016001E4142500E20353451 --out evidence/<run>/benchlink.csv \
    [--r-iset 1000] [--k-iset 400] [--iset-gain 0.990099] [--r-load 100] \
    [--model hardware/bench-breadboard-r0/source/wiring.toml] [--preflight evidence/<run>/notes.md]
.venv/bin/python tools/benchlink_console.py --serial-number 003B00194142500E20353451 --out evidence/<run>/tx-console.log
.venv/bin/python tools/benchlink_dash.py --csv evidence/<run>/benchlink.csv [--sources evidence/<run>/sources.csv] \
    [--anchor "YYYY-MM-DD HH:MM:SS"] [--gauge-valid-from "YYYY-MM-DD HH:MM:SS"] [--shunt-from "YYYY-MM-DD HH:MM:SS"] \
    [--dv0 mV] [--r-pack mOhm] [--power-mode A|B] [--preflight evidence/<run>/notes.md] \
    [--events evidence/<run>/benchlink-events.csv] [--rewrite-iset OLD] [--r-iset ohm]
```

The logger's `--r-iset` (ohm, default 1000), `--k-iset` (the ISET ratio, 400), `--iset-gain` (the PB1
node over V_ISET, 0.990099 nominal) and `--r-load` (ohm, 100) default to today's values
(`tools/benchlink_log.py:49-58`); give `--r-iset` the value build-sheet power check 2 measured and
`--iset-gain` the per-board fit (record M2). `--model` names the breadboard model whose hashes are logged
and `--preflight` the run's notes holding the preflight block (below, "Host checks").

### benchlink_log.py

It decodes every packet line from the RX (packet versions 1 to 4; 1 to 3 with their pre-change-A
meaning, above), checks the CRC and appends one CSV row, synced to disk. It opens the port exclusively, so a second program cannot split the lines.

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
the status line, and printed once to the dashboard's stderr (again only if the count grows). The same holds
for a `logger_start` row of `--events` it cannot read: counted in the status line and the flag note, and
printed once, because its rows would otherwise be rescaled (or not) under the wrong R_ISET without a word.

The dashboard's state of charge is counted: the net battery current integrated from `--anchor`, a moment
when the cell had rested near 0 A, started from a typical Li-ion rest-voltage table (about +-10 %) and a
6600 mAh capacity. Without `--anchor` nothing is counted. A gap is bridged with the mean battery current at
its two ends, because the load runs whether or not the TX reports. `--sources` names known input windows
(`start,end,source` in local time) where the automatic USB-C or solar call is wrong; a line it cannot read
is reported in the status line. `--gauge-valid-from` hides the gauge's readings from before it sensed the
cell. `--shunt-from` is the moment the cell went through the shunt: from it on the battery current is the
measured `battery_ma` (+ into the cell); rows before it, and CSVs without that column, use the ISET minus
load estimate, which the page marks as an estimate. Without `--shunt-from` every row is an estimate.

### Unattended

To keep the three running unattended on a Mac, make each a launchd agent with `KeepAlive` and
`RunAtLoad`, the repository as `WorkingDirectory`, and the virtualenv's Python with the tool's arguments
above, so they restart after a crash or a reboot. `tools/deploy/macos/install.sh` does the same for the
gateway and is a model. Run the tools from a copy that is not in a temporary directory: macOS clears
`/tmp` at boot.

## Host checks

The step 1 checks of the build-progression record run on the Mac, in `tools/benchlink_dash.py` (computed
there, `:218-240` and `:306-399`; drawn by the page), from the CSV's existing columns. No firmware field
carries them (record M6: firmware fields wait for a protocol revision). Every check that needs the
battery current takes the measured `battery_ma` (from `--shunt-from` on), never the ISET estimate:
without `--shunt-from` those checks stay off.

| Check | Rule | Source |
|---|---|---|
| Path metric, drop form (PATH_CELL_OUT) | valid only with PGOOD inactive and the battery discharging at 30 mA or more: drop = VCELL - VOUT - dV0, R_path = drop / I. Flagged above 20 mV (about 0.5 ohm at 38 mA), or on a step of more than 10 mV between consecutive valid samples at constant load (\|dI\| < 2 mA). dV0 (the same difference at zero current, per power mode) comes from `--dv0` or the preflight block for `--power-mode` | record M6; `drop_rows` (`:306`) |
| Coverage of the path metric | it covers CELL+ to OUT only. **The pack mating (PATH_PACK_POS, PATH_PACK_NEG) is not covered**: a fault there moves both ends together. That span is covered by checklist rows C6 and C11 at every preflight, by C12-C14 at 1 A, and live only by the VCELL step flag | record P5, M6; `DROP_COVERAGE` (`:233`) |
| VCELL step flag | valid in every state: with \|dI\| < 2 mA between consecutive samples, a gauge VCELL step of more than 8 mV is flagged (a 6.6 Ah cell cannot step that much in one sample at constant current, so it is a contact) | record M6; `step_rows` (`:326`) |
| SOC suspect | from a drop or VCELL step flag until 30 minutes pass with no further flag. SOC is marked suspect, never dropped | record M4, M6; `suspect_rows` (`:337`) |
| PGOOD against the divider (M7) | PGOOD asserted with the divider input below 4.0 V, or not asserted above 4.7 V | record M7; `m7_row` (`:346`) |
| CHG against ISET (M7) | CHG asserted with V_ISET under 0.02 V (an open ISET wire reads 0 V), or V_ISET above 0.2 V with CHG off | record M7; `m7_row` |
| ISET against the INA228 (M7) | while CHG is on above 200 mA, the ISET current against the INA228 battery current, outside 10 % + 20 mA. This also catches a bypassed shunt (the 2026-10-28/29 fault) | record M7; `m7_row` |
| CELL+ label (M4) | `vcell` is labelled "CELL+ node, includes the pack-lead drop", with VCELL - I x R_pack beside it (R_pack from `--r-pack` or the preflight block) | record M4; `corr_row` (`:356`) |
| Termination (P9) | at each CHG release with PGOOD on, the last sample before it has the INA228 current in 0.20-0.40 A and VCELL - I x R_pack at or above 4.12 V | record P9; `termination` (`:363`) |

**The preflight status.** Each run's notes begin with a fenced preflight block (record D6, M5), checked by
`tools/preflight.py`. The logger records, in the detail of its `logger_start` event, the git blob hashes
of the model (`--model`) and of the build sheet beside it, and the run's preflight status: **valid**,
**stale** (the model or the build sheet changed since the run: a hash differs from the current file),
**failing** (a missing id or a limit breach) or **missing** (no `--preflight`, or no block)
(`tools/benchlink_log.py:551-580`). They go in the event detail, not in the CSV header, because
`prepare_csv` (`benchlink_log.py:253`) sets aside a live CSV whose header it does not know. A missing or
failing block does not stop the log; it marks the run "wiring unverified" (record D6). The dashboard's
`--preflight` shows the same status and takes dV0 (for `--power-mode`) and R_pack from the block; a stale
block is shown as a warning and its values are still used; `--dv0` and `--r-pack` override it.

Not here: step 1b's current balance, the same-chip dV/dI and step 2c's power balance need the load,
solar and USB-C INA228s, which the one-INA228 benchlink packet does not carry (record M6, section 6.4).

## Bench to field

What this bench found, and where it goes (spec section 12.1). The node firmware reads phase A itself;
benchlink stays a bench tool.

| Bench knowledge | Goes to | Where |
|---|---|---|
| Sign convention: the cell on VIN+, so the part's VIN+ to VIN- is out of the cell; the battery rail's + is into the cell | node firmware (sign -1 on the battery rail), protocol, gateway | `../stage0-node/App/power_config.h:111-119` (rail table, phase A), `../stage0-node/App/power_acq.c:185` (sign applied to each CHARGE step) |
| VCELL (the gauge on the CELL+ node, which includes the pack-lead drop under current; record M4) is the battery voltage | node, field 11 `batt_mv` | `power_acq.c:257` (VCELL read), `power_acq.c:400` (the slot) |
| OUT (the INA228 VBUS, on its sense lead to the OUT connector) is the load rail, not the cell | node, field 26 `load_mv` | `power_config.h:118` (`PS_LOAD_MV` on the battery rail in phase A) |
| ISET charge current, I = 400 x V_ISET / R_ISET with V_ISET = the PB1 pin / the ISET gain; 0 mA without PGOOD | node, health `charger_reported_battery_ma` | `../stage0-node/App/board_inputs.c:68` (PB1), `power_config.h:87` (R_ISET, 1000), `:93` (the gain), `power_acq.c:287-291` (0 mA without PGOOD, the clip, the gain, the current), `:410` (the health value); `../common/power_regs.h:70`, `:83` (`unscale_ppm`) |
| Charger input, VIN = PA10 x `POWER_VIN_DIVIDER_PPM` / 10^6 (nominal 3); a clipped pin (an oversampled 4080 or more) is INVALID | node, field 28 `charger_input_mv` (with the input-sag note); benchlink applies the same clip (`adc_clipped`) and its own `VIN_DIVIDER_PPM` | `board_inputs.c:69` (PA10), `power_config.h:99`, `power_acq.c:285-286` (the clip, the ratio); `power_regs.h:78-79` |
| CHG and PGOOD, with CHG flashing as a fault | node, health charger status byte | `board_inputs.c:205-208` (pull-ups, EXTI10), `:217-218` and `:434` (the EXTI15_10 interrupt), `power_acq.c:23-24` (3 edges in 2 s, clear after 4 s), `power_acq.c:305` |
| Gauge SOC and rate | node, health `battery_soc_pct`, `battery_soc_rate_pct_h` | `power_acq.c:416-417` |
| INA228 die temperature | node, health `power_monitor_temp_c` | `power_acq.c:215`, `:424-426` (the hottest rail) |
| VDDA from VREFINT (replaces the fixed 3300 mV) | node, health `mcu_supply_mv`; scales ISET and VIN | `board_inputs.c:346-358` (`board_power_adc`), `power_regs.h:63-64` |
| Reset cause, boots, crashes, last crash PC | node, health report | `../stage0-node/App/fault.h:14-21`, `fault.c:58-66` (DR11, DR6, DR12) |
| TX timeouts, I2C recoveries | node, health report | `../stage0-node/App/tx_exchange.c:131`, `../stage0-node/App/i2c_bus.c:318` (counted in `recover_begin`), `:431` (`i2c_bus_recoveries`) |
| The shared conversions (INA228, MAX17048, ADC, ISET, divider) | one copy for the node, i2cscan and benchlink | `../common/power_regs.h:36-83` |
| Battery-path resistance (the span limits of build-sheet power check 7), gauge on CELL+, the VBUS sense lead on the OUT connector with SJ1 open, FT_f pull-up limit, input sag and the EN1/EN2 mode, the safety timer | wiring docs and build-sheet checks | [`build-sheet.md`](../../hardware/bench-breadboard-r0/build-sheet.md) "Power checks" 1-10, `wiring.toml` notes, this README "Wiring" and "Known limits" |
| Plain LoRa every 5 s, the CSV logger, the dashboard, `sources.csv`, the solar or USB-C call, the OCV-anchored counted SOC, `load_ma` = OUT / 100 ohm, ISET minimum and maximum, the drills | bench only | this directory and `tools/benchlink_*.py` |

The node never guesses the input source: phase A has one charger input and no monitor upstream of where
solar and USB-C join, so the dashboard's solar or USB-C call (and `--sources`) stays here.

## Acceptance drill (node against benchlink)

Phase A exit criterion 3 (spec section 12.2). On one breadboard and one pack, with the shunt in the
battery path (`--shunt-from` set to the moment it went in):

1. Flash benchlink (TX and RX). Log a known-state window of each: USB-C charging, solar charging, and
   discharging into the 100 ohm load (no source). Note each window's start and end.
2. Hold the reference on the battery current through each window (below).
3. Flash the node firmware ([`../stage0-node/README.md`](../stage0-node/README.md)) and repeat the same
   three windows. The node's values come from the gateway (ws0) for the observation fields and the health
   report.

| Check | Pass |
|---|---|
| Battery current, node and benchlink, against the reference | the same sign (+ into the cell) and within 2 % + 2 mA of the reference, in each window |
| ISET charge current | node and benchlink within 10 % of each other (the ISET monitor's own +-10 %) |
| Divider ratio | node `charger_input_mv` against a DMM on the charger's VBUS within 1 % |
| VCELL | node `batt_mv` and benchlink `vcell_v` against the meter at the pack plug within 10 mV, at rest or at the 38 mA load (build-sheet power check 8; under a 1 A charge the gauge reads CELL+, record M4) |
| CHG and PGOOD | equal on both firmwares in each window |
| Die temperature and VDDA | plausible: near the room temperature; VDDA near 3.3 V |
| OUT against VCELL | during a charge with the cell below 4.1 V, `load_mv` (OUT) reads 4.3-4.5 V and at least 100 mV above VCELL (build-sheet power check 9). Less means the INA228 VBUS sense lead is on the wrong net or SJ1, its back jumper, is closed |

**The current reference** is the Fluke 87V in series in the pack + lead at CELL+ position 1 (build-progression
record M1, dated note 2026-10-30: no calibrated shunt or clamp meter is bought; 7.1 Q2). On its 10 A range it
adds tens to hundreds of milliohms and would recreate the 0.2 ohm lesson, so it stays in series only for a
short steady window (a few seconds at a steady current), **never during a termination run** (exit criterion 4:
a 1 A charge that ends with CHG off and steady, not flashing) and never during the battery-path checks.

The results go in a new evidence run directory (never the live one) and the release's `RELEASES.md` entry.
