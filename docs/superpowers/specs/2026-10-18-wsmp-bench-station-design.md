# WSMP bench station: design

Status: design, approved section by section on 2026-10-18. Not implemented. This is sub-project 6
of [`2026-10-16-sixteen-stations-design.md`](2026-10-16-sixteen-stations-design.md). It implements
the station side of WSMP ([`docs/module-protocol.md`](../../module-protocol.md)) with local modules.

## 1. Goal

Connect every "Plan B" part ([`docs/poc-shopping-list.md`](../../poc-shopping-list.md)) to one TX
board at the same time, as WSMP local modules. Every sensor reaches the gateway and Home Assistant
from the first day. A sensor can be plugged in or removed while the station runs.

| | Decision (Clint, 2026-10-18) |
|---|---|
| Parts | Plan B: SHT45, BMP581, LTR390, SHTC3, INA228, MAX17048, bq24074 with one Li-ion cell, SparkFun SEN-15901 |
| First goal | the bench. Outdoor cabling and RJ45 modules come later |
| Power | two modes: board on USB with the battery chain beside it, and board on the battery |
| Wiring | breadboard, then a soldered protoboard, then a custom PCB |
| Module contract | WSMP 1.0, local binding (WSMP section 10) |
| Radio | today's protocol (version 5). The station maps WSMP channels onto today's catalog fields until sub-project 7 |
| Remote modules | RS-485 and Modbus per WSMP section 13, later |

Out of scope:
- WSMP on the radio (sub-project 7);
- the remote module adapter and the RS-485 port hardware;
- deep sleep (Stop 2);
- counting rain tips across a power loss (PRD test H06);
- the siting and calibration archive;
- the custom PCB.

## 2. Hardware and pins

| Function | Pin | Wiring |
|---|---|---|
| I2C bus: SHT45 0x44, BMP581 0x46 or 0x47, LTR390 0x53, SHTC3 0x70, INA228 0x40, MAX17048 0x36 | PA11 SDA, PA12 SCL (I2C2, D14 and D15) | one STEMMA QT hub at 100 kHz. The breakouts give the pull-ups (six 10 kΩ in parallel, about 1.7 kΩ). The microcontroller's internal pull-ups are off |
| Anemometer reed switch | PC0 (LPTIM1 IN1, morpho CN10.14) | switch to ground, 10 kΩ pull-up, RC filter of 1 ms |
| Rain gauge reed switch | PB5 (EXTI5) | as the anemometer, plus a 100 ms lockout in the firmware |
| Wind vane | PB2 (ADC IN4) | 10 kΩ pull-up to 3.3 V, the divider of the SparkFun datasheet |
| bq24074 PGOOD and CHG | PB8, PB10 | open drain, internal pull-ups |
| Sensor 3.3 V switch | PA9 | a load switch on the protoboard. Not on the breadboard |
| Reserved | USART1 on PB6 and PB7 (one RS-485 port), SPI1 on PA5, PA6 and PA7 (NOR flash) | not wired now |

These pins are in use, and this design must not take them:

| Pins | Use |
|---|---|
| PB15, PB9, PB11 | LEDs |
| PA0, PA1, PC6 | buttons |
| PB12, PB13 | radio debug outputs |
| PA2, PA3 | console (USART2) |
| PC3, PC4, PC5 | RF switch |
| PB0 | TCXO supply |
| PA13, PA14 | SWD |
| PC14, PC15 | LSE crystal |

- The pin map comes from ST's NUCLEO-WL55JC example projects. ST's board manual (UM2592) must
  confirm every pin, header position and solder bridge before the protoboard is soldered. The
  examples disagree about some header positions.
- The anemometer pulses go to the hardware counter, so no pulse is lost while the processor is busy.
  A 75 m/s wind gives about 112 pulses a second, well inside the 1 ms filter.
- The vane decodes 16 positions by voltage window. A reading at the supply rail means "no vane",
  which is how the wind module shows presence (WSMP-P1).
- A second RS-485 port has no free UART while the console uses USART2. The station has one remote
  port until a UART multiplexer exists. This corrects the PRD's four ports and WSMP section 13.

Build steps:
1. **Breadboard and jumper wires.** Proves the pin map and the drivers.
2. **Soldered protoboard** (for example an Adafruit Perma-Proto). Holds the STEMMA QT hub, the
   SparkFun RJ11 breakout, the pull-ups, filters and divider, the sensor power switch and the power
   shunt header. It must be ready before the 24-hour acceptance run.
3. **Custom PCB.** A later revision of the sensor-interface board. A separate project.

## 3. Power modes

**Mode A, daily: the board on USB, the battery chain beside it.**
- The board runs from the ST-LINK USB as today. The console and flashing work.
- The I2C sensors run from the board's 3.3 V.
- A separate USB charger feeds the bq24074. The 6,600 mAh cell is on its battery terminal. Its
  output drives a fixed test load of 100 Ω, ½ W (about 40 mA).
- The INA228 shunt is in the cell's positive lead. The MAX17048 reads the cell.
- The battery chain ground connects to the board ground.
- Removing the charger starts a discharge test. Connecting it starts a charge test.

**Mode B, power tests: the battery powers the station.**
- Cell, bq24074, Pololu S7V8F3 3.3 V regulator, then the board's 3V3 pin (CN7.16) and the sensors.
- The ST-LINK USB is unplugged, so the ST-LINK is off. The operator watches through the radio and
  the gateway.
- An optional 3.3 V USB-serial adapter on PA2 and PA3 gives the console. Connect only its ground and
  data lines, never its power pin.

**Switching. Never connect the USB and the battery supply at the same time.**

| From A to B | From B to A |
|---|---|
| 1. Unplug the board's USB cable. | 1. Remove the power shunt. |
| 2. Remove the 100 Ω test load. | 2. Fit the 100 Ω test load. |
| 3. Fit the power shunt (regulator output to the 3V3 pin). | 3. Connect the board's USB cable. |

- The protoboard has a two-pin header with one shunt, labelled "BATTERY POWER: USB UNPLUGGED". On
  the breadboard it is one labelled jumper wire.
- Before the first mode-B run, UM2592 must confirm the jumper settings for powering the board on
  CN7.16.

## 4. Firmware

| Part | File | Does |
|---|---|---|
| WSMP core | `firmware/common/wsmp.{c,h}`, generated `wsmp_registry.h` | block layouts, big-endian packing, descriptor checks against the registry, CRC-32C, quality mapping. Portable C without HAL calls, so the remote module adapter can use it later |
| Registry | one registry file and a generator for the C header and the Python module. The generated files are committed | the codes of WSMP section 4 |
| Station host | `App/wsmp_host.c` | port table and presence state machine (WSMP section 7), debounce, admission against the radio budget, latch at :50, read deadline, flap limit |
| Interim map | `App/wsmp_catalog_map.c` | snapshots to today's catalog fields (section 5). Removed in sub-project 7 |
| Local modules | `App/mod_sht45.c`, `mod_bmp581.c`, `mod_ltr390.c`, `mod_shtc3.c`, `mod_power.c`, `mod_wind.c`, `mod_rain.c` | one driver for each module type, with `probe`, `identify`, `latch` and `read_snapshot`. The SHT45 code moves out of `sensor.c` |
| I2C bus | `App/i2c_bus.c` | the shared bus with timeouts, one probe slot for each module, recovery (nine clocks and a stop), and the sensor power switch |

Timing:
- Temperature, humidity, pressure and UVA: each module samples every 15 s on its own timer, in two
  steps (start, then fetch). No code waits for a sensor.
- Wind: the station reads the pulse counter every 250 ms. The gust is the largest 3-s mean of 12
  quarter-second bins. The vane is read every second.
- Rain: one interrupt for each tip, then the lockout.
- Battery: the INA228 integrates by itself. The module reads it at the latch.
- The latch is on the station's existing minute report (the fourth 15-s tick after boot) in this
  sub-project. The latch at second 50 of the UTC minute (WSMP-T1) arrives with sub-project 4, which
  moves the whole minute to UTC. (Ruling at the plan review, 2026-10-18: the current timing is what
  `tests/test_tx_machine.py` pins, and moving it is sub-project 4's change.)
- Flash writes still happen only while the radio is idle. There is still no blocking wait
  (`make waits`).

Console:
- `MODULES` lists each port, its state, its module type and the quality of each channel.
- `SENSOR rain on|off` enables the rain module. The node stores the setting as a latest-wins
  record in its meta log.

Rules:
- The WSMP core and the station host are literate sources (`*.lit.md`, `tools/tangle.py`).
- The Power of Ten rules and the existing gates apply. A function has a complexity of at most 10 and
  at most 60 lines. Loops are bounded and there is no heap. The stack bound, cppcheck and the
  analyzer run as today.
- Budget estimate: about 14 KB of flash (core and host 4 KB, seven drivers 9 KB, interim map
  0.5 KB). TX grows from 58 KB to about 72 KB, 65 % of 110 KB, under the 75 % target. About 1 KB
  of RAM.
- The station stays in sleep mode as today (`LOW_POWER_DISABLE`). The hardware counter also counts
  in sleep.

## 5. Interim map to today's catalog

Until sub-project 7, each reading uses the version 5 catalog ([`docs/protocol-design.md`](../../protocol-design.md),
fields 0 to 25). The bitmap of each reading shows the fields of the modules that are active. A
channel with quality "missing" gives the field's INVALID code.

| WSMP channel | Catalog field | Conversion on the station |
|---|---|---|
| air temperature mean | 0 `temperature_c` | to 0.01 °C, offset −40.00 |
| air humidity mean | 1 `humidity_pct` | to 0.01 % |
| sample count of the air module | 25 `th_samples` | as is |
| pressure mean | 2 `pressure_hpa` | to 0.1 hPa, offset 300.0 |
| anemometer pulses | 3 `wind_speed_ms` | pulse increment × 0.667 m/s per Hz ÷ window, to 0.1 m/s |
| gust | 4 `wind_gust_ms` | to 0.1 m/s |
| east and north sums | 5 `wind_dir_deg` | atan2 to whole degrees. CALM below 0.5 m/s |
| rain tips | 6 `rain_tips` | as is (3 bytes) |
| UVA counts | 9 `uva_raw` | as is |
| battery voltage | 11 `batt_mv` | to 1 mV |
| charge counters | 12 `batt_current_ma` | net charge increment ÷ window, to 0.1 mA |
| energy and charge counters | 13–16 | to mWh and mAh |
| state of charge | 17 `soc_gauge_pct` | to 1 % |
| charger state | 18 `charger_pins` | off: PGOOD 0. Charging: PGOOD 1, CHG 1. Done: PGOOD 1, CHG 0. Fault: INVALID |
| enclosure temperature and humidity | 19, 20 | as fields 0 and 1 |

- The station sets `WS_NODE_FIELDS` to all these fields, so the journal slot fits the widest
  reading. The widest reading is 63 bytes of plaintext. The journal still keeps 24 hours.
- Fields 21 to 24 (the minute extremes) are not sent. The gateway derives extremes from the minute
  means (WSMP rule 6).
- The catalog cannot carry the WSMP quality codes "partial" and "suspect". The station sends the
  value. The `MODULES` console command and the health report show the quality.
- The battery channels travel in the minute reading until sub-project 7 moves them into the health
  report.
- The gateway must have Home Assistant entities for every field in this table, under the WSMP
  entity rule (`<station>_<role>_<quantity>_<kind>`, WSMP-H1). Sub-project 2 owns that change.
  This sub-project checks that the gateway stores and shows every field.

## 6. Testing and acceptance

Host tests (CI, no hardware):
- The existing TX test harness gets a register-level model of each I2C part. It also gets models of
  the pulse counter, the analog input and the pin interrupt.
- WSMP conformance (section 14 of WSMP) for every local driver.
- Hot-plug cases:
  - modules come and go at random times;
  - SDA is held low;
  - an SHT45 does not acknowledge during a measurement;
  - a module flaps;
  - a module is over the budget.

  The tests check the debounce (WSMP-P2), the quality codes and the flap limit. They also check
  that a bus fault never changes the layout.
- Wind and rain against a Python reference: pulse trains and vane voltages give exactly the
  reference counts, gust and vector sums.
- The interim map: snapshot, catalog fields, the gateway's decoder, and back to the same values.
- Fuzzing of the WSMP block parser in the existing fuzz gate, one million cases.
- Every existing gate, including the flash budget and the stack bound.

Bench check on the breadboard:
1. Each sensor reads plausible values against a room thermometer and the local pressure report.
2. Unplug and plug in each STEMMA sensor while the station runs. It is admitted within two latches
   and removed after three. No reset.
3. Turning the cups gives a speed and a gust. All 16 vane positions decode.
4. Twenty tips by hand give exactly twenty tips.
5. Mode A shows charge and discharge. Mode B runs the station for one hour.

Acceptance on the protoboard: a 24-hour run with every sensor, measured at the gateway.
- At least 99 % of minutes committed within 120 s (the H01 measure for this build).
- Every channel has quality "good" in at least 99 % of minutes.
- No `WS_CHECK` failure and no unexpected reset.
- Only this real run counts. A simulation or a smoke test never counts as acceptance.

## 7. Risks and open items

| Item | What to do |
|---|---|
| Pin map not confirmed by UM2592 | Check every pin, header position, solder bridge and the CN7.16 power jumpers before the protoboard and before mode B |
| Plugging a STEMMA sensor into the live 3.3 V rail | The inrush can glitch the bus or reset the board. The firmware recovers. On the bench, plug gently. The protoboard's power switch allows a controlled power cycle |
| The LPTIM glitch filter with an external clock | Not confirmed. The RC filter is the primary debounce |
| Vane voltage windows | They depend on the pull-up value. Measure the 16 positions on the bench and put the windows in the wind module type entry |
| Flash budget | 72 KB is an estimate. The flash guard in every build and the size line of every release watch it |
| Rain tips lost at a power cut | Accepted on the bench. PRD test H06 needs persistent counting later |
