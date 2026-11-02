# WSMP bench station: design

Status: design, approved section by section on 2026-10-18. Not implemented. This is sub-project 6
of [`2026-10-16-sixteen-stations-design.md`](2026-10-16-sixteen-stations-design.md). It implements
the station side of WSMP ([`docs/module-protocol.md`](../../module-protocol.md)) with local modules.

**Amended 2026-10-29** by the power telemetry design
([`2026-10-29-power-telemetry-design.md`](2026-10-29-power-telemetry-design.md), "PT" below). The
approved body stands except where a dated note says otherwise:

| Item | Change (2026-10-29) | Where |
|---|---|---|
| Battery | a 1S3P Li-ion pack: three 2,200 mAh cells in parallel, 6,600 mAh, 3.0-4.2 V (3.7 V nominal) | sections 1 and 3 |
| Pins | the bench wiring of 2026-10-28/29 is the official design: ISET on PB1, the charger input divider on PA10, CHG on PB10 and PGOOD on PB8 with the pull-up limit; the node and the bench tool use the same pins | section 2 |
| Mode A | the bench lessons: a short, low-resistance battery loop; the INA228 VBUS jumper on OUT with the back jumper cut; the gauge on the cell; the charger's safety timer | section 3 |
| Firmware | `mod_power.c` builds two modules, battery (type 8) and power rails (type 9), and the health accessor `mod_power_health()`; the board ADC reads ISET, the divider and VREFINT | section 4 |
| Radio and map | protocol version 6, catalog version 2: the battery fields' meanings are corrected, fields 17 and 18 are retired, fields 26-30, 32 and 33 are new; the slow battery items go in the health report | sections 1 and 5 |

**Amended 2026-10-30** by the build-progression decision record
([`2026-10-29-build-progression-decisions.md`](2026-10-29-build-progression-decisions.md), "BP"
below) and Clint's answers of 2026-10-30 (BP section 7.1). The body and the 2026-10-29 notes stand
except where a 2026-10-30 note says otherwise:

| Item | Change (2026-10-30) | Where | BP |
|---|---|---|---|
| Sensor ports | the v1 sensor ports are RJ11 (sensor-module-ports spec); there is no RJ45 in v1 | section 1 | H6 |
| Meter pins | cups on PB5 (LPTIM1_IN1, AF1; Arduino D4, CN9.5), rain on PB4 (EXTI4; Arduino A3, CN8.4); approved 2026-10-30 | section 2 | N2, 7.1 N2 |
| R_ISET | R9 = 1 kΩ (record 1.4); adopted with change A, read by this workflow from 7.1 P3 "change A as written"; R_ISET confirmed by build-sheet check 2; Clint to confirm (design D4/D5); ICHG = 890 A·Ω ÷ 1 kΩ = 0.89 A typ | section 2 | 1.4 |
| PA9 switch | ~~proved on the breadboard first (step 1 change C, exit 9); soldered at step 2 only if proven~~ *Superseded 2026-11-02:* change C is deferred to the carrier; steps 1 and 2 have no sensor power switch | section 2 | S2 |
| Battery chain | no current through a breadboard contact; the gauge on the CELL+ node by its own lead, its minus unconnected, ground over STEMMA QT | section 3 | P1, P3–P5, M4 |
| Mode B | the regulator feeds CN6.4 at steps 1 and 2 (the same 3V3 net as CN7.16) | section 3 | N3 |
| Check 5 | mode B for one hour is also step 1 exit 10, on the breadboard | section 6 | S2 |

## 1. Goal

Connect every "Plan B" part ([`docs/poc-shopping-list.md`](../../poc-shopping-list.md)) to one TX
board at the same time, as WSMP local modules. Every sensor reaches the gateway and Home Assistant
from the first day. A sensor can be plugged in or removed while the station runs.

| | Decision (Clint, 2026-10-18) |
|---|---|
| Parts | Plan B: SHT45, BMP581, LTR390, SHTC3, INA228, MAX17048, bq24074 with one Li-ion cell, SparkFun SEN-15901. *Amended 2026-10-29: the cell is a 1S3P pack (3 × 2,200 mAh in parallel, 6,600 mAh, 3.0-4.2 V); the bq24074 is the Adafruit #4755 with its 1.0 A ISET jumper (PT section 1)* |
| First goal | the bench. Outdoor cabling and RJ45 modules come later. *Amended 2026-10-30 (BP H6): the v1 sensor ports are RJ11 ([`2026-10-21-sensor-module-ports-design.md`](2026-10-21-sensor-module-ports-design.md)); there is no RJ45 in v1. Outdoor cabling still comes later* |
| Power | two modes: board on USB with the battery chain beside it, and board on the battery |
| Wiring | breadboard, then a soldered protoboard, then a custom PCB |
| Module contract | WSMP 1.0, local binding (WSMP section 10) |
| Radio | today's protocol (version 5). The station maps WSMP channels onto today's catalog fields until sub-project 7. *Amended 2026-10-29: protocol version 6, catalog version 2 (PT sections 4 and 5); the map stays interim* |
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
| Anemometer reed switch | PC0 (LPTIM1 IN1, morpho CN10.14). *Superseded pin, 2026-10-30 (BP N2): PB5 (LPTIM1_IN1, AF1; Arduino D4, CN9.5; morpho CN10.29)* | switch to ground, 10 kΩ pull-up, RC filter of 1 ms |
| Rain gauge reed switch | PB5 (EXTI5). *Superseded pin, 2026-10-30 (BP N2): PB4 (EXTI4; Arduino A3, CN8.4; morpho CN7.34)* | as the anemometer, plus a 100 ms lockout in the firmware |
| Wind vane | PB2 (ADC IN4) | 10 kΩ pull-up to 3.3 V, the divider of the SparkFun datasheet |
| bq24074 PGOOD and CHG | PB8, PB10 | open drain, internal pull-ups |
| bq24074 ISET (added 2026-10-29) | PB1 (ADC1_IN5, Arduino A0, CN8.1) | straight to ISET, analog, no pull. Charge current I = 400 × V_ISET ÷ R_ISET (SLUS810 section 9.3.5.1; R_ISET about 890 Ω, measured). *Amended 2026-10-30: R_ISET is R9 = 1 kΩ (record 1.4); adopted with change A, read by this workflow from 7.1 P3 "change A as written"; R_ISET confirmed by build-sheet check 2; Clint to confirm (design D4/D5). ICHG = 0.89 A typ; currents logged with 890 Ω read 12 % high.* *Amended 2026-10-30 (BP M2, adopted with change A, read by this workflow from 7.1 P3): no longer a straight wire. ISET → 10 kΩ 1 % at the charger end → the PB1 node, with 100 nF and 1 MΩ to logic ground. The pin reads V_ISET × 1 MΩ ÷ 1.01 MΩ (gain 990099 ppm, `POWER_ISET_GAIN_PPM`) until the per-board fit replaces it. The fit is stored in `wiring.toml` first, as the charger's `iset_gain_ppm`.* |
| Charger input voltage (added 2026-10-29) | PA10 (ADC1_IN6, Arduino A2, CN8.3) | charger VBUS through 20 kΩ (two 10 kΩ 1 % in series) over 10 kΩ to GND; VIN = 3 × the pin. Analog, no pull. *Amended 2026-10-30 (BP M2): VIN = the pin × the stored ratio, (R4 + R5 + R6) ÷ R6 from the three resistors as measured (`POWER_VIN_DIVIDER_PPM`; 3 nominal), not an integer 3; checked in circuit within 1 %; the bottom resistor to logic ground* |
| Sensor 3.3 V switch | PA9 | a load switch on the protoboard. Not on the breadboard. *Amended 2026-10-30 (BP S2; step 1 change C, BP 4.6): proved on the breadboard first, from a pre-assembled load-switch breakout (EN from CN5.2, D9), with the STEMMA QT bus split into an unswitched branch (power monitors) and a switched branch (sensor hub); step 1 exit 9. Soldered at step 2 only if exit 9 passed; otherwise port power waits for the mux (PORT-5)*. *Amended 2026-11-02 (BP 4.6 dated note): change C is deferred to the carrier board; neither the breadboard nor the protoboard carries a sensor switch, PA9 is unconnected on them, and the carrier switches each port from PA9 (CN10.19)* |
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
- *Amended 2026-10-29 (PT sections 1, 9.5 and 11.1):* the ISET and divider rows above, with CHG and
  PGOOD, are the bench wiring proven on 2026-10-28/29
  ([`firmware/benchlink/README.md`](../../../firmware/benchlink/README.md) "Wiring") and the official
  phase A design: the node firmware (`firmware/stage0-node`) reads them on the same pins as the bench
  tool. **Pull-up limit:** PB8 and PB10 are FT_f pins, but with the internal pull-ups on a pin must
  stay below min(VDD, VDDA) + 0.3 V (DS13293 Rev 5 table 26 note 3); the bench measured at most
  2.9 V on USB. **PA10 limit:** FT_fa, at most min(VDD, VDDA) + 3.6 V and 5.5 V (DS13293 table 26),
  a charger input of 16.5 V through the 3:1 divider with the MCU powered, about 10.8 V without; the
  panel's cold Voc stays at or below about 10.2 V (the bq24074's OVP). The debug outputs on PA10
  (`DEBUG_RF_HSE32RDY_ENABLED`), PA11, PA12 and PB2 stay off; PB12 and PB13 are probe outputs, never
  free pins.
- *Amended 2026-10-30 (BP N2 and N3; N2 approved by Clint on 2026-10-30, BP 7.1; change B, BP 4.5):*
  the meter inputs move before any solder. Cups PC0 → **PB5** (LPTIM1_IN1 on AF1, the same AF as
  PC0; Arduino D4, CN9.5). Rain PB5 → **PB4** (EXTI4; Arduino A3, CN8.4). PC0 is morpho-only, so the
  step 2 shield cannot reach it. PB4's reset function NJTRST is released when the firmware configures
  the pin (debug is SWD only); `DEBUG_RF_LDORDY_ENABLED` (would drive PB4) and
  `DEBUG_RF_SMPSRDY_ENABLED` (would drive PB2) stay 0 by compile-time assert. Every station signal
  lands on an Arduino female header: vane CN8.2 (A1), PGOOD CN9.6 (D5), CHG CN9.7 (D6), ISET CN8.1,
  the divider CN8.3, PA9 CN5.2 (D9). The firmware (`firmware/stage0-node/App/board_inputs.c`) and the
  breadboard model use these pins.
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

*Amended 2026-10-30 (BP section 3, S1, S2, 7.1 Q8):* the build order is step 1 (breadboard v2, no
solder, no current through a breadboard contact), step 2 (the soldered #196 shield and Perma-Proto
module board; H01), 1b, 2c, 3 (the carrier PCB under the NUCLEO), 4 and 5. Every circuit soldered at
step 2 was first proved on the breadboard at step 1.

## 3. Power modes

**Mode A, daily: the board on USB, the battery chain beside it.**
- The board runs from the ST-LINK USB as today. The console and flashing work.
- The I2C sensors run from the board's 3.3 V.
- A separate USB charger feeds the bq24074. The 6,600 mAh cell is on its battery terminal. Its
  output drives a fixed test load of 100 Ω, ½ W (about 40 mA).
- The INA228 shunt is in the cell's positive lead. The MAX17048 reads the cell.
- *Amended 2026-10-29 (PT sections 1, 2, 11.1 and 11.2; the bench lessons of 2026-10-28/29):*
  - the "cell" is the 1S3P pack (6,600 mAh, 3.0-4.2 V). The charger's input is one source on its
    own cable, the solar panel on the DC jack or a USB-C supply, never both at once;
  - **keep the battery loop short and low resistance:** the pack, the INA228 VIN+, the shunt, VIN−
    and the charger's LIPO terminal, and the − leg to the charger's GND, on short heavy leads off the
    breadboard, within the span limits of PT section 11.2 (+ span at most 75 mΩ, − span at most
    40 mΩ, each pack-side span at most 28 mΩ; this line said "at most 50 mV at 1 A for both legs",
    superseded later the same day by record P8). A 0.2 Ω breadboard path ended 1 A charges early;
  - **the INA228's VBUS jumper goes to OUT** (the load rail, `load_mv`), and the breakout's back
    solder jumper from VBUS to VIN+ is cut. A closed back jumper ties the pack to OUT;
  - **the MAX17048 senses the cell, not OUT:** its own Kelvin leads to the pack's + and −, before the
    shunt, never through a load-carrying ground jumper;
  - **the charger's safety timer:** the #4755 schematic shows TMR tied to GND (timers disabled;
    confirm on the board in hand). If TMR floats, the default 4-6 h timer is shorter than a 1 A charge
    of 6.6 Ah from empty (6-7 h): fit RTMR = 72 kΩ, or start the test charge at 3.85 V or more.
  The bench breadboard build sheet carries these as its power checks
  ([`hardware/bench-breadboard-r0/build-sheet.md`](../../../hardware/bench-breadboard-r0/build-sheet.md)).
- *Amended 2026-10-30 (BP P1, P3–P5, M4; change A, BP 4.4; 7.1 P3 "change A as written"):* no
  battery, charge, input or load current runs through a breadboard contact. The force path is the
  pack → the cut #1131 pigtail → WAGO CELL+ → the INA228 terminal (VIN+, shunt, VIN−) → WAGO BATT →
  the charger's BATT socket; the charger's SYSOUT socket feeds WAGO OUT (the 100 Ω load, the INA228
  VBUS lead, the regulator). **The gauge** (MAX17048) sits on the CELL+ node by its own lead: the red
  lead of a cut #1131 half in its own CELL+ position, its minus (black) lead insulated and
  unconnected, its ground over STEMMA QT. It reads the CELL+ node, which differs from the pack
  terminal by I × R_pack while current flows (M4). This replaces "the MAX17048 reads the cell" and
  "its own Kelvin leads to the pack's + and −" above. The battery chain ground meets the board ground
  only through one TIE from the STAR at pack − (P4). At step 1 the charger input is the breakout's
  USB-C from a floating wall adapter.
- The battery chain ground connects to the board ground.
- Removing the charger starts a discharge test. Connecting it starts a charge test.

**Mode B, power tests: the battery powers the station.**
- Cell, bq24074, Pololu S7V8F3 3.3 V regulator, then the board's 3V3 pin (CN7.16) and the sensors.
  *Amended 2026-10-30 (BP N3, P1): at steps 1 and 2 the regulator feeds **CN6.4**, the Arduino 3V3
  pin the step 2 shield uses: regulator → the BATTERY POWER shunt → the unswitched board-A 3V3 node →
  CN6.4; the station return runs on its own lead from CN6.7. CN6.4 and CN7.16 are one 3V3 net
  (UM2592 Tables 17 and 18). On the bench CN7.16 feeds only the OLED, whose VCC lead is unplugged in
  mode B. The carrier (step 3) may use CN7.16.*
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
- *Amended 2026-10-30 (BP N3, 4.4):* at steps 1 and 2 the shunt is the BATTERY POWER shunt header on
  breadboard B, and the UM2592 check is for powering the board on CN6.4 (the same 3V3 net as CN7.16).
  Ground is untouched by a mode change: A to B also unplugs the OLED's VCC lead from CN7.16, and B to
  A takes the shunt out before the USB goes in.

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
  *Amended 2026-10-29 (PT sections 9.3-9.6):* `App/power_acq.c` reads the INA228 (CHARGE, VBUS on
  OUT, DIETEMP), the MAX17048 (VCELL, SOC, CRATE), the board ADC (ISET, the divider and VREFINT, one
  interrupt-driven sequence on the 250 ms vane tick) and CHG and PGOOD. `mod_power.c` turns them into
  two base modules that are present in every power profile: battery (type 8: cell voltage, battery
  current + into the cell, the energy and charge counters) and power rails (type 9: load, charger
  input, solar and USB-C voltages and currents). A slot the profile has no source for is "not
  fitted"; a dead part gives "missing". `mod_power_health()` returns the slow values (SOC and rate,
  charger status, die temperature, VDDA, the charger-reported charge current from ISET) for the
  health report. The shunt, R_ISET and the divider ratio are build constants in
  `App/power_config.h`, measured on the build sheet. *Amended 2026-10-30 (BP M1, M2, 1.4): the shunt
  is the nominal 15 mΩ, verified against a series meter, not measured; R_ISET is R9 = 1 kΩ (record 1.4); adopted with change A, read by this workflow from 7.1 P3 "change A as written"; R_ISET confirmed by build-sheet check 2; Clint to confirm (design D4/D5),
  with the ISET gain fit; the divider ratio is measured.*
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

*Amended 2026-10-29 (PT sections 5.2, 8.1 and 9.7): the version 6 map of the power rows.* The
battery module (type 8) maps to fields 11-16 and the power rails module (type 9) to fields 26-30, 32
and 33. A "not fitted" slot leaves its field out; a missing or faulted slot gives INVALID.

| WSMP channel (quantity) | Catalog field (v2) | Conversion on the station |
|---|---|---|
| battery voltage (9): the cell, from the gauge | 11 `batt_mv` | mean over the minute, to 1 mV |
| battery current (10), + into the cell | 12 `batt_current_ma` | INA228 CHARGE delta × −1 ÷ window, to **1 mA**, offset 32,768; outside −32,768 to +32,766 mA INVALID. Sent from version 6 on |
| energy into and out of the battery (11, 12) | 13 `energy_in_mwh`, 14 `energy_out_mwh` | Σ ΔQ × cell voltage, split by sign, to mWh; INVALID in a minute where a step had no fresh cell voltage |
| charge into and out of the battery (13, 14) | 15 `charge_in_mah`, 16 `charge_out_mah` | to mAh, split by the sign of PT section 3.1 |
| load voltage (18): OUT | 26 `load_mv` | to 1 mV (phase A: the battery INA228's VBUS, on its own sense lead to OUT) |
| load current (19) | 27 `load_current_ma` | to 1 mA, offset 32,768 (phase A: not fitted, absent) |
| charger input voltage (20) | 28 `charger_input_mv` | PA10 × the stored divider ratio (3 nominal), to 1 mV; the source is not identified; a clipped ADC is INVALID |
| solar voltage and current (21, 22) | 29 `solar_mv`, 30 `solar_current_ma` | to 1 mV and 1 mA (phase A: absent) |
| USB-C voltage and current (23, 24) | 32 `usb_mv`, 33 `usb_current_ma` | to 1 mV and 1 mA, in the extension bitmap (phase A: absent) |
| state of charge, charger state | 17, 18 | **retired**: no longer mapped; the health report carries them (below) |

- The station sets `WS_NODE_FIELDS` to all these fields, so the journal slot fits the widest
  reading. The widest reading is 63 bytes of plaintext. The journal still keeps 24 hours.
  *Amended 2026-10-29: `WS_F_WSMP_BENCH` is the 77-byte version 6 set (a 93-byte frame, a 96-byte
  journal slot, 24.15 hours); the per-build ceiling is 80 bytes (PT sections 5.4 and 7).*
- Fields 21 to 24 (the minute extremes) are not sent. The gateway derives extremes from the minute
  means (WSMP rule 6).
- The catalog cannot carry the WSMP quality codes "partial" and "suspect". The station sends the
  value. The `MODULES` console command and the health report show the quality.
- The battery channels travel in the minute reading until sub-project 7 moves them into the health
  report. *Amended 2026-10-29 (PT sections 3.3, 6 and 8.2): the fast battery and rail values (the
  rows above) stay in the minute reading; the slow battery items go in the health report through
  `mod_power_health`: gauge SOC and its rate, the charger status from CHG and PGOOD, the
  power-monitor die temperature, VDDA from VREFINT and the ISET charge current, beside the station
  counters, every 15 minutes in the 64-byte version 6 report. They are not WSMP channels in this
  phase; sub-project 7 decides whether they become health-class channels.*
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
   *Amended 2026-10-30 (BP S2): the mode-B hour is also step 1 exit 10 (BP section 3), so mode B
   is proved on the breadboard before solder: the station runs from the regulator through the CN6.4
   entry, readings reach the gateway every minute, the mode-B checklist rows pass and no reset is
   logged.*

Acceptance on the protoboard: a 24-hour run with every sensor, measured at the gateway.
- At least 99 % of minutes committed within 120 s (the H01 measure for this build).
- Every channel has quality "good" in at least 99 % of minutes.
- No `WS_CHECK` failure and no unexpected reset.
- Only this real run counts. A simulation or a smoke test never counts as acceptance.

## 7. Risks and open items

| Item | What to do |
|---|---|
| Pin map not confirmed by UM2592 | Check every pin, header position, solder bridge and the CN7.16 power jumpers before the protoboard and before mode B. *Amended 2026-10-30 (BP N3): the mode-B entry at steps 1 and 2 is CN6.4, the same 3V3 net; the checklist also ticks PB4, PB5 and PB14* |
| Plugging a STEMMA sensor into the live 3.3 V rail | The inrush can glitch the bus or reset the board. The firmware recovers. On the bench, plug gently. The protoboard's power switch allows a controlled power cycle |
| The LPTIM glitch filter with an external clock | Not confirmed. The RC filter is the primary debounce |
| Vane voltage windows | They depend on the pull-up value. Measure the 16 positions on the bench and put the windows in the wind module type entry |
| Flash budget | 72 KB is an estimate. The flash guard in every build and the size line of every release watch it |
| Rain tips lost at a power cut | Accepted on the bench. PRD test H06 needs persistent counting later |
