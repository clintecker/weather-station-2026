# Weather station 2026: current-system specification (breadboard development system)

This was first read from `weather-station-2026` at `origin/master`, commit `e44977f` (2026-11-02), plus
the parts inventory `/Users/clint/code/electronics/INVENTORY.md`. We then updated it up to commit
`26da337` (2026-11-09). Some line citations still point at the `e44977f` text. This page covers **what
the parts are and how they work together electrically, in firmware and on the wire**. It has **no
physical breadboard layout** on purpose (no holes, rows, columns, board letters, jumper numbers or lead
IDs). You design the physical layout.

## 0. How to read the citations

Every fact has a source. It's either `path:line` (paths are relative to the repository root) or a
datasheet or maker reference. "Inferred" marks a conclusion we drew here that no source states.

| Short name | Path |
|---|---|
| INV | `/Users/clint/code/electronics/INVENTORY.md` (outside the repo) |
| BSW | `docs/hardware/bench-station-wiring.md` |
| PM | `docs/hardware/power-metering.md` |
| PTD | `docs/superpowers/specs/2026-10-29-power-telemetry-design.md` |
| WT | `hardware/bench-breadboard-r0/source/wiring.toml` (used only for functional facts: nets, values, part pinouts) |
| NR | `firmware/stage0-node/README.md` |
| REL | `firmware/stage0-node/RELEASES.md` |
| BI / BIH | `firmware/stage0-node/App/board_inputs.c` / `.h` |
| PC | `firmware/stage0-node/App/power_config.h` |
| IBH / IBC | `firmware/stage0-node/App/i2c_bus.h` / `i2c_bus.c` |
| PROTO | `docs/protocol.md` |
| PS | `docs/protocol-stack.md` |
| EVM | `docs/firmware-event-model.md` |
| FM | `docs/failure-modes.md` |
| WSMP | `docs/module-protocol.md` |
| BL / BLP | `firmware/benchlink/README.md` / `firmware/benchlink/App/bl_pkt.h` |
| I2CS | `firmware/i2cscan/README.md` |
| RT | `firmware/rangetest/README.md` |
| TR | `tools/README.md` |
| HA | `docs/runbook-home-assistant.md` |
| WEB | `docs/web-dashboard.md` |
| GW | `gateway.lit.md` |
| SHOP | `docs/poc-shopping-list.md` |
| BRU | `docs/hardware/nucleo-wl55jc-bringup.md` |

The repository cites these datasheets (PTD:28-29, PM:15-20, PS:595-627):

- ST UM2592 Rev 4 (NUCLEO-WL55JC user manual, Tables 9, 11-19)
- ST DS13293 Rev 5 (STM32WL55)
- ST RM0453 (STM32WL reference manual)
- TI SLUS810N (bq2407x)
- TI SBOS904 / SLYS021A (INA228)
- Analog Devices MAX17048
- Sensirion SHT4x and SHTC3
- Bosch BMP581
- Lite-On LTR390
- SparkFun SEN-15901 datasheet
- Semtech SX126x / AN1200.13

---

## 1. Purpose and scope

**Purpose.** A fresh session will redesign the breadboard development build from scratch. To do that,
it needs the complete functional picture:

- every part
- every electrical connection, by function and net
- every component value
- every MCU pin
- the firmware behaviour that depends on the wiring
- the protocols
- the open questions that the physical build must answer

**In scope** (the breadboarded development system):

| Element | What it is |
|---|---|
| TX node | NUCLEO-WL55JC1 running `firmware/stage0-node` with `ROLE=tx`: reads sensors, weather meter and power telemetry, journals one record a minute, sends it over LoRa (NR:3-6) |
| RX bridge | a second NUCLEO-WL55JC1 running the same tree with `ROLE=rx`: keyless radio-to-USB bridge (NR:6, NR:116) |
| Mac gateway and tools | `python -m ws0` (gateway, SQLite store, HTTP API and dashboard, MQTT / Home Assistant) and `tools/` (NR:133-136, TR:5-33) |
| Bench firmware | `firmware/benchlink` (plain-LoRa power telemetry link), `firmware/i2cscan` (I2C/power check with the bench OLED), `firmware/rangetest` (link walk test) (NR:8) |
| Power, phases A and B | phase A: bq24074 charger, one battery INA228 (0x40), MAX17048 (0x36); phase B: plus load (0x41), solar (0x45) and USB-C (0x48) INA228s (PM:24-27) |

**Out of scope** except where firmware has a dormant path: enclosure, carrier PCB, BQ25798 charger
(phase C), the sixteen-station network, field mounting, the RJ11 sensor-port design. Dormant paths:

| Dormant path | One line |
|---|---|
| Power profile C | `WS_POWER_PROFILE 3` stops the build with `#error` (BQ25798 driver is a later phase) (PC:35-36) |
| I2C mux variant | `WS_I2C_MUX=1` builds a TCA9548A (0x71) port bus with RESET on PB14; default 0 is the passive hub (IBH:8-21, BI:221-229) |
| Wio-E5 mini TX board | `make ROLE=tx BOARD=wio-e5` builds the TX for a Seeed Wio-E5 mini (STM32WLE5JC) from `firmware/board/wio-e5`: I2C2 on PA15/PB15, cups PC0, vane PB3, console USART1 on its USB-C, no charger pins; compiled, not yet run on hardware (issue #35; `firmware/board/wio-e5/README.md`) |
| Sensor-port power switch | PA9 is driven high as "sensor power enable" but is unconnected on the bench; no sensor power switch is part of the breadboard build (IBH:65-70, IBC:417-420, BSW:90) |
| Field build | `-DWS_FIELD_BUILD` drops `TEST-HANG`/`TEST-FAULT` (NR:119) |

**Status today.** Master builds **protocol version 6** (power telemetry). Nobody **cut that release
yet**: RELEASES.md lists it as "Next release (not cut yet)" (REL:31). The last recorded node releases
are TX `04fcc656938d` and RX `cc2766a38c61`, on protocol 5 (NR:28, REL:81, REL:137). The 24-hour H01
delivery test is still to do (NR:33).

Benchlink proved the phase A power chain on 2026-10-28/29, **except
the shunt in the battery path** (PTD:58, BRU:498-507).

---

## 2. System overview

### 2.1 What flows where

- Sensors and power monitors -> TX node over **I2C2** (PA11 SDA, PA12 SCL, 100 kHz) through a passive
  STEMMA QT hub (IBH:3-11, BSW:81).
- Weather meter (cups, vane, rain) -> TX node GPIO/timer/ADC: cups on PB5 (LPTIM1), vane on PB2 (ADC),
  rain on PB4 (EXTI4) (BI:4-13).
- bq24074 charger status/analog -> TX node: ISET on PB1, input divider on PA10, PGOOD on PB8, CHG on
  PB10 (BI:7-16).
- TX -> RX: **LoRa 915.0 MHz, 500 kHz, SF7, CR 4/5**, AES-128-CCM frames: one observation a minute
  (plus backlog), a health report every 15 min (radio_cfg.h:11-18, NR:312-314).
- RX -> TX: ACK/NACK frame per observation, sealed by the gateway (PROTO:170-187).
- RX <-> Mac: USB CDC through the on-board ST-LINK V3E, 115200 8N1. Frames go up as lowercase hex lines,
  and ACK/NACK hex lines come down (PS:801-831).
- Mac gateway -> SQLite (`observations`, `rejections`, `diagnostics`, plus `rx_alive`, `rx_faults`,
  `gateway_events`, `radio_events`), HTTP API + dashboard on 127.0.0.1:8088, MQTT to Home Assistant
  (gateway.py:168-188, ws0/web.py:61-76, ws0/__main__.py:39, HA:96-107).

### 2.2 Block diagram (indented list)

- **Power sources** (only one connected at a time: PM:40-41)
  - Solar panel (Voltaic P110, 6 V nominal) -> charger DC jack -> Schottky D4 -> charger VBUS/IN
  - USB-C floating wall adapter (5 V, >= 2 A) -> charger USB-C -> Schottky D2 -> charger VBUS/IN
  - (phase B: a solar INA228 and a USB-C INA228 in each source lead, before the diodes)
- **bq24074 charger breakout** (Adafruit #4755)
  - BAT <-> **battery INA228 shunt** <-> CELL+ node <-> 1S3P Li-ion pack (6600 mAh)
    - MAX17048 gauge senses CELL+ (cell side of the shunt)
    - NTC on THERM, taped to the pack
  - OUT (system rail, "SYSOUT") -> load node
    - battery INA228 VBUS sense (phase A load voltage)
    - (phase B: load INA228 in series here)
    - 100 ohm test load (bench mode A only)
    - Pololu S7V8F3 3.3 V buck-boost -> NUCLEO 3V3 (bench mode B only)
  - ISET -> 10 kohm -> ISET node (100 nF, 1 Mohm to GND) -> PB1
  - VBUS -> 20 kohm / 10 kohm divider -> PA10
  - CHG -> PB10, PGOOD -> PB8 (open drain, MCU pull-ups)
- **TX NUCLEO-WL55JC1** (STM32WL55JC, SX126x-class radio on die)
  - I2C2 -> STEMMA QT hub -> SHT45 0x44, BMP581 0x47, LTR390 0x53, SHTC3 0x70
  - I2C2 -> second QT branch (always powered) -> INA228 0x40 -> MAX17048 0x36 (phase B: + 0x41, 0x45, 0x48)
  - PB5 / PB2 <- RJ11 breakout <- SEN-15901 wind cable (cups, vane)
  - PB4 <- RJ11 breakout <- SEN-15901 rain cable
  - SPI1 -> bench OLED. Two builds drive it: `i2cscan`, and the TX node's bench build
    (`make ROLE=tx WS_BENCH_OLED=1` in `firmware/stage0-node`, Makefile:8, Makefile:54-65). The default
    field build (`WS_BENCH_OLED=0`) and the RX leave it out.
  - ST-LINK USB -> Mac (console and flash, plus the 3V3 supply in bench mode A)
  - SubGHz radio -> antenna -> LoRa
- **RX NUCLEO-WL55JC1** (no external wiring)
  - LoRa <-> radio, and USB (ST-LINK VCP) <-> Mac
- **Mac**
  - `ws0 serve` (finds RX by ST-LINK serial) -> SQLite store -> HTTP :8088 dashboard/API, MQTT -> Home Assistant
  - `tools/` (console, status, h01_report, rx_faults, benchlink_log/dash, rangetest_log, preflight)

---

## 3. Hardware inventory

Quantities come from INV, counted 2026-10-20/21. Rows marked "received 2026-11-05" are from the DigiKey
order of 2026-11-02. Those parts are at home and nobody counted them yet (INV:66-81, INV:417-419).
"Interface" and "Address/pins" give the functional connection, not a layout.

### 3.1 MCU and radio

| Part | Maker # | Qty | Role | Interface | Address / pins | Supply | Notes |
|---|---|---|---|---|---|---|---|
| ST NUCLEO-WL55JC1 | NUCLEO-WL55JC1 | 2 (INV:15) | TX node and RX bridge | ST-LINK V3E USB (SWD, VCP 115200 8N1), Arduino + morpho headers | TX ST-LINK serial `003B00194142500E20353451`, RX `0016001E4142500E20353451` (NR:5-6, BRU:19-27) | USB 5 V via ST-LINK, or external 3.0-3.6 V on 3V3 (CN6.4 = CN7.16), max 1.3 A, ST-LINK then unpowered (UM2592 sec. 6.4, Table 9; BSW:375-380) | STM32WL55JC, 256 KB flash (128 x 2 KB), RDP level 0 (BRU:27-35). High-band board 865-928 MHz (PS:597). Jumpers at factory default (BRU:164-172). Measured target 3.276-3.290 V on USB (BRU:31) |

On-board resources that the firmware uses or reserves (UM2592 Table 19, through BSW:117-154):

- buttons B1 PA0, B2 PA1, B3 PC6
- LEDs LED1 blue PB15, LED2 green PB9, LED3 red PB11 (board main.h:63-78)
- TCXO supply PB0
- RF switch PC3/PC4/PC5
- LSE crystal PC14/PC15
- SWD PA13/PA14
- BOOT0 PH3
- VCP PA2/PA3

### 3.2 Power

| Part | Maker # | Qty | Role | Interface | Address / pins | Supply | Notes |
|---|---|---|---|---|---|---|---|
| Adafruit bq24074 USB/DC/solar Li-ion charger | Adafruit #4755 | 1 (INV:17) | charger with power path | USB-C and DC jack inputs, BATT and SYSOUT JST PH sockets, 11-pin header GND, LIPO, GND, OUT, CHG, PGOOD, CE, ISET, THERM, GND, VBUS (WT:172-176) | MCU: ISET->PB1, VBUS->PA10, CHG->PB10, PGOOD->PB8 | input 5-10 V, absolute 28 V, charges only below OVP 10.2-10.8 V (SLUS810; PM:277-278) | R_ISET = R9 1 kohm behind the closed "1A" jumper: I_CHG = 890 / R_ISET = 0.89 A typ (0.80-0.98 A) (BSW:270, WT:184-190). TMR tied to GND per schematic: all safety timers disabled (confirm) (BSW:272). ITERM 0.30 A typ (0.225-0.375) (WT:190). CE has R8 10 kohm to GND (charging enabled) (WT:190). CHG/PGOOD LED anodes on OUT via 10 kohm (WT:190). THERM solder jumper ties fixed R10 10 kohm to TS: cut it for the NTC (BSW:273). Inputs reach VBUS through SK34A Schottky D2 (USB-C) and D4 (DC jack) (PM:157-159). EN1/EN2 set by solder jumpers SJ2/SJ1, state on the board in hand not recorded (PM:206-208) |
| Li-ion polymer pack 3.7 V 6600 mAh | Adafruit #353 | 1 (INV:18) | battery | JST PH 2-pin plug | — | 3.0-4.2 V, 3.7 V nominal, about 24.4 Wh | 1S3P: three 2200 mAh cells in parallel, protected, 69 x 54 x 18 mm (SHOP:49). JST PH colours vary: check polarity with a meter (WT:323). The pack's own lead is never cut (BSW:221) |
| 10 k precision epoxy NTC, B = 3950 | Adafruit #372 | 1 (INV:19) | charger temperature cut-off | 2 leads to THERM and logic GND | — | — | taped to the pack; with B3950 charging stops below about +3.5 °C and above about +47 °C (BSW:273). Not read by the MCU in phases A/B (PM:151) |
| Voltaic P110 solar panel, 10 W, "5 V" (Voltaic: 6 V) | Adafruit #5369 | 1 (INV:20) | solar source | barrel plug (re-terminated by Clint to fit the charger's DC jack) | — | Voc 6.94 V, about 8.7 V cold | jack is 5.5 x 2.1 mm by inference from Adafruit's page, not measured (PM:179-182) |
| USB-C wall adapter, floating | — (not inventoried) | not listed | bench charger input / backup | USB-C into the charger's own USB-C | — | 5 V >= 2 A | never the Mac or a hub that shares the NUCLEO ground (BSW:243-245, WT:342-347). Inferred: must be a separate, isolated supply |
| Pololu S7V8F3 3.3 V step-up/step-down | Pololu #2122 | 5 (INV:16) | 3.3 V for the NUCLEO in battery mode | pins SHDN, VIN, GND, VOUT (WT:231) | VIN from charger OUT; VOUT to NUCLEO 3V3 | 2.7-11.8 V in, < 0.1 mA quiescent (SHOP:50; Pololu #2122 page) | pin order is "bench check" (no maker page shows it) (WT:232-233) |
| 100 ohm 1/2 W resistor | Yageo MFR50SFTE52-100R | 30 received 2026-11-05 (INV:418) | fixed test load on OUT, bench mode A | 2 leads | OUT to power ground | — | about 38-40 mA (BSW:301-302); 1/4 W would run at 0.18 W (INV:418) |
| 1 ohm 2 W resistor | Vishay CPF21R0000FKE36 | 10 received 2026-11-05 (INV:417) | fault-injection test of the pack-lead step flag | — | — | — | (SHOP:82) |

### 3.3 Power measurement

| Part | Maker # | Qty | Role | Interface | Address / pins | Supply | Notes |
|---|---|---|---|---|---|---|---|
| Adafruit INA228 85 V 20-bit power monitor | Adafruit #5832 | 1 on hand (INV:22) + 5 received 2026-11-05 (INV:74) | battery rail (phase A); load, solar, USB-C rails (phase B) | I2C over STEMMA QT; X1 screw terminal VIN+ (X1.3), VBUS (X1.2), VIN- (X1.1) in parallel with header VIN+/VBUS/VIN- (WT:201-206) | battery 0x40 (A1 GND, A0 GND, as shipped); load 0x41 (A0 jumper to VS); solar 0x45 (both to VS); USB-C 0x48 (A1 wired to SDA: rework) (PM:297-302) | 3.3 V from QT; 640 µA typ, 1.1 mA max continuous (PM:334) | shunt R1 15 mohm 1 % 2 W 2512 (PM:51-52). SJ1 back jumper VBUS->VIN+ must be **open** on every board (PM:79-82). Header VCC/GND not used: power and ground come over QT (WT:208). I2C pull-ups 10 kohm in a resistor pack shared with the ADDR pull-downs, **no cut jumper** (PM:324-326). Green power LED about 0.13 mA (PM:335-336) |
| Adafruit MAX17048 Li-ion fuel gauge | Adafruit #5580 | 1 (INV:21) | cell voltage, SOC, SOC rate | I2C over STEMMA QT; two JST PH BAT sockets; 6-pin header VIN, GND, SCL, SDA, INT, QSTART (WT:219-220) | 0x36 fixed | about 3-23 µA (SHOP:51) | senses CELL+ by the red lead of a JST PH pigtail in one BAT socket; black lead insulated; ground over QT (PM:63) |
| Adafruit INA228 (phase B rails) | #5832 | see above | phase B | — | 0x41, 0x45, 0x48 | — | in scope for the breadboard build (step 1b): the three extra rails are not wired in the current breadboard model yet |
| USB-C female breakout (5.1 kohm CC) | Adafruit #4090 | 5 received 2026-11-05 (INV:77) | phase B USB-C metering, source side | screw/solder | — | — | sink-configured: 5.1 kohm Rd CC1 and CC2 to GND, 5 V only, no PD; data pins unconnected (PM:240-244). Needs soldering (INV:77) |
| USB-C male plug breakout | Adafruit #5978 | 5 received 2026-11-05 (INV:78) | phase B USB-C metering, charger side | — | — | — | needs soldering (INV:78) |
| Female 2.1 mm DC jack to screw terminal | Adafruit #368 | 5 received 2026-11-05 (INV:75) | phase B: panel plug into the solar meter | — | — | — | (PM:174) |
| Male 2.1 mm barrel plug to screw terminal | Adafruit #369 | 4 received 2026-11-05 (INV:76) | phase B: solar meter into the charger DC jack | — | — | — | (PM:175) |
| ADC divider and ISET network parts | see 4.5 | — | charger input and charge current sense | — | PA10, PB1 | — | 1 Mohm received 2026-11-05 (INV:438); 100 nF X7R radial (KEMET C320C104K5R5TA) received 2026-11-05 (INV:84); 10 kohm 1 % from the Yageo RS4X kit (INV:100-102) |

### 3.4 Sensors

| Part | Maker # | Qty | Role | Interface | Address / pins | Supply | Notes |
|---|---|---|---|---|---|---|---|
| Adafruit SHT45 with PTFE cap | Adafruit #6174 | 2 (INV:23) | outside air T/RH (module type 1) | I2C STEMMA QT | 0x44 (stage0.h:16) | 3.3 V | Sensirion SHT45-AD1F (SHOP:63); one spare |
| Adafruit SHTC3 | Adafruit #4636 | 1 (INV:24) | enclosure T/RH (type 4) | I2C STEMMA QT | 0x70 (mod_th.c:22) | 3.3 V | chosen over SHT40 to avoid 0x44 (SHOP:62) |
| Adafruit BMP581 | Adafruit #6407 | 1 (INV:25) | pressure (type 2) | I2C STEMMA QT (SPI possible) | firmware uses 0x47 (mod_reg.c:34); SHOP lists "0x46 or 0x47" | 3.3 V | CHIP_ID 0x50 (mod_reg.c:2) |
| Adafruit LTR390 | Adafruit #4831 | 1 (INV:26) | UVA counts (type 3) | I2C STEMMA QT | 0x53 (mod_reg.c:36) | 3.3 V | **UVA only, not a UV index** (INV:26) |
| Adafruit STEMMA QT 5-port hub | Adafruit #5625 | 1 (INV:28) | passive I2C fan-out | JST SH 4-pin | — | — | passive; inferred: adds no pull-ups |
| Adafruit W25Q128 SPI flash 16 MB | Adafruit #5643 | 1 (INV:27) | future 30-day storage | SPI | **not connected; no document says how** (INV:27, SHOP:40) | — | firmware does not use it (NR:399) |

### 3.5 Weather meters

| Part | Maker # | Qty | Role | Interface | Address / pins | Supply | Notes |
|---|---|---|---|---|---|---|---|
| SparkFun Weather Meter Kit | SEN-15901 | 1 (INV:35) | wind speed (cups), direction (vane), rain gauge | two RJ11 cables: wind (vane, cups plug into vane) and rain | cups PB5, vane PB2, rain PB4 | passive reeds and resistor network | anemometer counted 2026-10-21 (INV:493). Cups 1.492 mph per Hz = 0.66698 m/s per Hz; rain 0.2794 mm per tip (SHOP:58, WSMP:228-229) |
| SparkFun RJ11 breakout | BOB-14021 (+ PRT-00132 jacks) | 1 panel of two boards, 2 jacks (INV:36) | one breakout per meter cable | 6-pin header, labels 1 "-", 2 B, 3 R, 4 G, 5 Y, 6 "-" (WT:61-62) | see 4.4 | — | panel must be separated and jacks/headers soldered; whether done is unrecorded (INV:36, INV:494). Meter cables are never cut (BSW:168-169) |
| RJ12 6P6C crimp plugs | — | 100, at home (INV:37) | future cables | — | — | — | needs a 6P crimper (none yet) (INV:37) |
| RJ11 cables, straight-through | — | 2+: reported received 2026-11-09, not counted, location not recorded (INV:40) | — | — | — | — | still need the 6-conductor check and a meter check that they're straight-through (INV:40) |

### 3.6 Display (bench only)

| Part | Maker # | Qty | Role | Interface | Address / pins | Supply | Notes |
|---|---|---|---|---|---|---|---|
| Adafruit 2.7" 128 x 64 monochrome OLED | Adafruit #2674 (SSD1325) | **not in INV** (only its capacitor is: INV:72) | bench readout for `i2cscan` and the TX bench build (`WS_BENCH_OLED=1`) | SPI1, write only; 20-pin header (WT:393-394) | see 4.3 | 3.3 V, 50-150 mA (I2CS, "The OLED") | must be in SPI mode: R19 and R21 fitted, R18 and R20 empty (WT:396). 220 µF across its 3.3 V and GND (WT:400-407) |
| 220 µF 16 V radial electrolytic | Rubycon 16YXJ220MT16.3X11 (and Panasonic EEU-FC1C221) | 20 + 10 received 2026-11-05 (INV:72-73) | OLED bulk capacitor | — | — | — | polarised (WT:407) |

### 3.7 Interconnect and build materials

| Part | Maker # | Qty | Role | Notes |
|---|---|---|---|---|
| Breadboards | unrecorded size | 3 (INV:34) | build | size not recorded at the count (INV:34, INV:540) |
| BusBoard BB830 830-point | BB830 | 5 received 2026-11-05 (INV:80) | build | some 830-point boards split each rail at the centre (WT:33) |
| STEMMA QT cables 100 mm / 200 mm | Adafruit #4210 / #4401 | 1 + 1 (INV:29-30) | I2C | only two on hand for about seven QT boards (INV:29) |
| STEMMA QT to male header cable | Adafruit #4209 | 5 received 2026-11-05 (INV:71) | I2C into the MCU headers | |
| JST PH 2-pin cable, female | Adafruit #1131 | 5 received 2026-11-05 (INV:67) | cut into pack-mating and board-mating pigtail halves for the battery path and gauge sense | |
| WAGO 222-413 (3-way) / 222-415 (5-way) lever connectors | 222-413 / 222-415 | 20 + 20 received 2026-11-05 (INV:68-69) | splices for all battery/charge/load current | accept 22 AWG solid; stranded twisted (WT:617) |
| 22 AWG solid hook-up wire, 6 colours | Adafruit #1311 | 1 pack received 2026-11-05 (INV:70) | force leads and signal jumpers | |
| 24 AWG copper hook-up wire, 7 colours | — | 7 rolls, home (INV:448) | jumpers | solid or stranded unrecorded |
| Male-to-female jumpers | — | 120 (INV:85) | OLED, debug | |
| 2.54 mm header kit | — | 1 kit (INV:65) | | |
| Yageo MFR-25 1 % 1/4 W kits RS2X, RS3X, RS4X | RS2X/RS3X/RS4X | 5 of each E96 value, 100 ohm-97.6 kohm (INV:82-84, INV:90-103) | pull-ups, divider, ISET series | no 1 ohm or 1 Mohm in the kits (INV:84) |
| Instruments | Fluke 87V, Rigol DS1054Z, Saleae Logic 8, Siglent SPD3303X-E | 1 each (INV:57-60) | measurement | power-path drops are read on the 87V 600 mV range (BSW:396-402) |

---

## 4. How it works together, electrically

### 4.1 Power path

**Topology (phase A).** Sources -> charger IN/VBUS -> charger power path -> OUT (system rail) and BAT
(cell). The battery INA228 shunt sits **in the pack's positive lead**. It's between the CELL+ node (pack
side) and the charger's BAT pin (PM:62, BSW:221). Functional nets (WT:510-577):

| Net | Members (functional) | Source |
|---|---|---|
| CELL_POS ("CELL+") | pack +, INA228 VIN+, gauge BAT+ (sense) | WT:514-516 |
| BATT | INA228 VIN-, charger BATT socket + (= header LIPO) | WT:519-521 |
| SYS_OUT ("OUT") | charger SYSOUT socket + (= header OUT), 100 ohm load, INA228 VBUS sense, regulator VIN | WT:525-528 |
| CHGR_IN | adapter + into charger USB-C (before D2) | WT:532-534 |
| CHGR_VBUS | charger VBUS header pin, top of the input divider | WT:537-539 |
| THERM | charger THERM, NTC | WT:570-572 |
| REG_OUT | regulator VOUT, then the battery-power link to 3V3 | WT:575-577 |
| 3V3 | NUCLEO 3V3 (CN6.4 = CN7.16), both QT branches' V+, the three meter pull-ups, the battery-power link, OLED VCC and its capacitor | WT:442-446 |
| GND | one net in two domains, see below | WT:452-459 |

**Per source.**

| Source | Path | Notes / source |
|---|---|---|
| Solar | panel -> charger DC jack -> D4 (SK34A) -> IN | phase A has no monitor upstream of the join; "the source is not identified" (PM:157-159). Cold Voc must stay <= about 10.2 V (OVP) (PM:284-285) |
| USB-C | floating 5 V >= 2 A adapter -> charger USB-C -> D2 (SK34A) -> IN | VBUS reads source minus the Schottky drop (BSW:291-296) |
| NUCLEO USB | Mac -> ST-LINK USB -> on-board regulation -> NUCLEO 3V3 | powers MCU, radio, all I2C parts and OLED in bench mode A (BSW:300-303). Inferred: on-board 3V3 regulator per UM2592 |
| Rule | **USB-C is never connected at the same time as solar**, in any phase | PM:40-41, PTD:43 |

**Where each meter measures (phase A).**

| Quantity | Sensor | Sense point | Firmware sign / field | Source |
|---|---|---|---|---|
| Battery current, charge/energy counters | battery INA228 0x40, shunt between CELL+ (VIN+) and BATT (VIN-) | pack + lead | part counts VIN+->VIN- (out of cell) positive; firmware sign -1, so + = into the cell; fields 12-16 | PM:108-113, PC:111-120 |
| Load voltage | battery INA228 VBUS on its own sense lead to OUT | OUT | field 26 `load_mv` | PM:62, PM:130 |
| Cell voltage, SOC, SOC rate | MAX17048 0x36, red lead at CELL+ | CELL+ node, includes the pack-lead drop I x R_pack | field 11 `batt_mv`; SOC and rate in the health report | PTD:127-137, PM:63 |
| Charger input voltage | PA10 via divider | charger VBUS header (after D2/D4) | field 28 `charger_input_mv` | PM:64 |
| Charge current (charger's view) | PB1 via ISET network | charger ISET pin | health `charger_reported_battery_ma` (cross-check only) | PM:65, BSW:271 |
| INA228 die temperature | battery INA228 | — | health `power_monitor_temp_c` | PM:145 |
| MCU supply | VREFINT | VDDA | health `mcu_supply_mv` | PM:146 |

**Phase B additions** (PM:69-77). These are in scope for the breadboard build but aren't in the
breadboard model yet. Phase B adds three INA228s:

- load INA228 0x41, in series from OUT to a LOAD node that feeds the test load and the regulator (VBUS at LOAD)
- solar INA228 0x45, in the panel lead before D4 (VBUS at the panel side, SOLAR_IN)
- USB-C INA228 0x48, between a sink-configured USB-C receptacle and the charger's USB-C, before D2 (VBUS at USB_IN)

The battery INA228's VBUS moves to CELL+ as a host-side cross-check. The node doesn't read it
(PC:12-17). Phase B needs EN2 high and EN1 low on the #4755 (input limit by R_ILIM, no VIN-DPM). EN1 =
EN2 = high is standby (PM:194-209). Input-margin check: with USB-C only at full charge, charger VBUS
must be >= 4.6 V (PM:211-215). The back-feed check uses 10 kohm on the idle input (PM:190-192).

With EN2 high and a weak source, PGOOD/CHG may cycle at low sun. That's analysed, not measured
(PM:246-271).

**Ground.** One GND net in two domains joined by **exactly one conductor** (WT:448-459, BSW:223):

| Domain | Members | Source |
|---|---|---|
| Power ground | pack -, charger BATT and SYSOUT socket minus, charger header GNDs (zero-current test points), test-load return, a star point at pack negative | WT:448-456, BSW:223 |
| Logic ground | NUCLEO GND, both QT branches, meter returns and filter caps, divider and ISET returns, regulator GND, OLED GND, NTC return | WT:448-458 |
| The tie | one conductor from the pack-negative star point to the regulator GND / logic ground, in both modes | BSW:223, BSW:318-319 |

Rules that follow (FM:300-310):

- Don't wire the gauge's or the INA228's minus/GND header pins. Their ground comes over QT.
- Insulate the black lead of the SYSOUT pigtail and the black lead of the gauge pigtail.
- The charger input must be a floating adapter.

A second tie makes battery return current flow in the QT cables (FM:310). The NTC returns to logic
ground, not the star. That costs up to 40 mV of TS offset during a 1 A charge, and we accept it (+0.4 °C
shift on the cold trip, +3.8 °C on the hot trip) (BSW:238-241).

**Force-current rule.** Battery, charge, input and load current must **never pass through a breadboard
strip, header pin or Dupont contact**. Use lever connectors, the INA228 screw terminal and the JST PH
sockets for splices (BSW:215-217). That's because the bq24074 BAT pin is both the output and the
voltage sense. About 0.2 ohm of contacts at 1 A ended charges early. A 3-4 ohm intermittent contact made OUT
wander 120-150 mV (BSW:261-263, FM:308).

The one exception we tolerate is the regulator chain in mode B
(BSW:310-312).

The charger header's LIPO, OUT and GND pins carry no current. They're only test points. The rest of the
header carries CHG, PGOOD, ISET, THERM and VBUS (BSW:233-236).

**Battery-path resistance budget at 1 A** (FM:291, BL:72):

- \+ span (pack plug + to LIPO, with the 15 mohm shunt): <= 75 mohm
- \- span (charger GND to pack -): <= 40 mohm
- each pack-side span: <= 28 mohm (R_pack is the sum of them)
- each JST PH mating: <= 20 mohm
- each lever clamp or screw: <= 5 mohm

Lead lengths: pigtail halves <= 60 mm, solid force links <= 50 mm, regulator supply and tie <= 100 mm.
26 AWG is about 13 mohm per 100 mm. These come from build-progression record H7
(`docs/superpowers/specs/2026-10-29-build-progression-decisions.md:153`).

**Bench power modes.**

| Mode | NUCLEO supply | Charger chain | OLED | Rule | Source |
|---|---|---|---|---|---|
| A (daily) | ST-LINK USB | drives only the 100 ohm test load on OUT (about 40 mA); battery-power link open, so the regulator feed is dead | powered | remove/connect the charger input to see discharge/charge | BSW:300-303 |
| B (power tests) | pack -> charger -> OUT -> S7V8F3 -> battery-power link (a 2-pin header with a removable shunt, "BATTERY POWER: USB UNPLUGGED") -> NUCLEO 3V3 (CN6.4); return from CN6.7 to regulator GND | test load removed | VCC lead unplugged (its 50-150 mA would ride the regulator chain and the INA228 reading) | console optional via a 3.3 V USB-serial on PA2/PA3, data and ground only | BSW:305-315, BSW:328-330 |
| Interlock | **never connect the NUCLEO USB and the battery supply at the same time**; A->B: unplug USB, remove load, unplug OLED VCC, fit shunt; B->A: remove shunt first, then OLED, load, USB. Mode changes never move the ground tie or the CN6.7 return | | | | BSW:316-326 |

**The NTC and the charger.** Cut the THERM solder jumper first. If you don't, the fixed 10 kohm R10 sits
in parallel and keeps TS <= 10 kohm. Then the cold trip never fires, and the hot trip moves to about
35 °C (BSW:273, FM:293). TS reads about 0.75 V at 25 °C. If it reads 0.375 V, the jumper is still closed
(BSW:475).

### 4.2 I2C buses

One bus: **I2C2, PA11 SDA (AF4), PA12 SCL (AF4), open-drain, internal pull-ups also enabled, 100 kHz,
TIMINGR `0x20323E5D` at PCLK1 48 MHz** (IBC:14-15, IBC:26, IBC:42-43, IBH:3-4). SDADEL = 2 gives 146 ns
of data hold. The INA228 needs that when you strap its A1 to SDA (0x48) (PM:312-318).

| Branch | Power | Devices (address) | Source |
|---|---|---|---|
| Sensor hub (one QT cable to the 5-port hub) | unswitched NUCLEO 3V3 | SHT45 0x44, BMP581 0x47, LTR390 0x53, SHTC3 0x70 | BSW:50-54, WT:79-87 |
| Power-monitor branch (second QT cable, daisy chain) | unswitched NUCLEO 3V3, always powered | battery INA228 0x40 -> MAX17048 0x36; phase B adds 0x41, 0x45, 0x48 | BSW:55-56, WT:89-100 |
| Shared | GND, SDA, SCL common to both branches; hub ground straight from a NUCLEO GND pin | | WT:87, WT:415-416 |

Notes:
- 3V3 only, never the 5 V pin. CN6.5 sits next to CN6.4 (BSW:82, BSW:107-108).
- Pull-ups are on the breakouts only. With about nine STEMMA boards (phase B), the parallel pull-up is
  about 1.11 kohm. It sinks 2.6 mA at 0.4 V, which is inside 3 mA. It passes if you measure >= 0.97 kohm
  with the bus idle and powered off (PM:324-330). Inferred for phase A (six breakouts with 10 kohm each):
  about 1.7 kohm.
- The 0x48 strap adds the INA228's 10 kohm ADDR1 pull-down to SDA. Idle SDA sits at about 3.0 V, and we accept that (PM:319-322).
- Reserved addresses (never an INA228): 0x36, 0x44, 0x46, 0x47, 0x50, 0x53, 0x70, 0x71 (build-time
  asserts, PC:53-66).
- Bus behaviour: one transfer at a time, with a guard of 30 ms + 90 µs/byte. Stuck-bus recovery (up to
  9 SCL clocks, then STOP) runs only after a timeout, a bus error, a HAL refusal or SDA low. An address
  NACK means "absent" and costs no recovery (IBH:3-7, WSMP:648-652, EVM:80-93).
- In the hub build, record clients at 0x50 complete as NACK without bus traffic (no ID EEPROMs) (IBH:9-11).

### 4.3 SPI OLED (bench only, driven by `firmware/i2cscan` and the TX bench build)

| OLED pin | Signal | MCU pin | NUCLEO morpho (Arduino alias) | Source |
|---|---|---|---|---|
| 1 | GND | GND | CN10.20 | WT:396, WT:820-828 |
| 2 | 3.3 V in | 3V3 | CN7.16 | WT:810-818 |
| 4 | DC (low command, high data) | PC2 | CN10.21 (D8, CN5.1) | i2cscan/App/oled.h:8 |
| 7 | SCLK | PA5 SPI1_SCK | CN10.11 (D13, CN5.6) | oled.h:5 |
| 8 | DIN | PA7 SPI1_MOSI | CN10.15 (D11, CN5.4) | oled.h:6 |
| 15 | CS (low while sending, GPIO) | PA4 | CN10.17 (D10, CN5.3) | oled.h:7 |
| 16 | RST (low = reset) | PC1 | CN10.23 (D7, CN9.8) | oled.h:9 |
| 20 | frame ground | GND or open | — | WT:396 |
| 3, 5, 6, 9-14, 17-19 | unused | — | — | WT:393-396 |

SPI clock: the fastest step <= 1 MHz (SSD1325 limit). One frame is 4096 bytes, about 45 ms (oled.h:19-20,
I2CS "The OLED"). Run the supply pair straight to NUCLEO pins, never through a shared ground rail.
Otherwise its return current offsets the ground-referenced readings (ISET, VIN_SENSE, vane) (FM:307).

The node TX firmware drives the OLED when you build it with `make ROLE=tx WS_BENCH_OLED=1`
(`App/oled_app.c`, `App/oled_dma.c`, SPI1 DMA). The default field build (`WS_BENCH_OLED=0`) and the RX
leave it out (`firmware/stage0-node/Makefile`:8, :54-65). It uses the same pins as the table above (`App/oled_dma.h`:6).

### 4.4 Weather meter inputs

**RJ11 pinout on the BOB-14021** (labels 1 "-", 2 B, 3 R, 4 G, 5 Y, 6 "-", WT:61-62, SEN-15901
datasheet through BSW:175-177):

| Cable | Pin | Function | Net | Source |
|---|---|---|---|---|
| Wind | 2 | vane return | GND | WT:457 (BOBW.2 in GND) |
| Wind | 3 | cups return | GND | WT:457 (BOBW.3) |
| Wind | 4 | cups reed (inner pair 3/4) | CUPS -> PB5 | WT:481-484 |
| Wind | 5 | vane network (outer pair 2/5) | VANE -> PB2 | WT:487-490 |
| Rain | 3 | bucket reed return | GND | WT:457 (BOBR.3) |
| Rain | 4 | bucket reed | RAIN -> PB4 | WT:493-496 |
| Both | 1, 6 | unused | — | WT:62 |

Confirm each conductor by continuity with the meter cable plugged in (BSW:175-177).

**Input conditioning.** It sits at the jack end, beside each breakout. That way the link probe sees every
wire between the pull-up and the MCU (BSW:179-183, WT:102-106):

| Input | MCU | Pull-up | Filter | Firmware | Source |
|---|---|---|---|---|---|
| Cups | PB5 = LPTIM1_IN1 (AF1), counts falling edges | 10 kohm to 3.3 V | 100 nF to GND (about 1 ms) | LPTIM1 on LSE, digital filter 8 samples (244 µs); 16-bit free-running count; 75 m/s = about 112 Hz | BSW:187, BI:138-154 |
| Rain | PB4 = EXTI4, falling edge | 10 kohm to 3.3 V | 100 nF to GND | 100 ms lockout from the last edge (chatter counts once) | BSW:188, mod_rain.c:13, mod_rain.c:34-42 |
| Vane | PB2 = ADC1_IN4 | 10 kohm to 3.3 V | none | ratiometric (pull-up and ADC share VDDA); > 3.2 V = open vane (absent); 16 positions, nearest of the SparkFun table, band ±5 % R then ±10 mV | BSW:189-193, mod_wind.c:24-47 |

Vane resistances clockwise from north in 22.5° steps (ohm): 33000, 6570, 8200, 891, 1000, 688, 2200, 1410,
3900, 3140, 16000, 14120, 120000, 42120, 64900, 21880 (mod_wind.c:39-41). Closest pair 891/1000 ohm is
30 mV apart (BI:195-197). Nobody measured the real voltages on the bench yet. They go into `vane_mv`
once measured (BSW:421-428). An unconnected PB2 floats and can look like a valid position, so you
need the pull-up (BSW:453-456).

The internal pull-ups on PB5/PB4 stay on. The **counter link probe** runs at boot and every 15 min. It
swaps them for pull-downs for about 1 ms. An intact link (external 10 kohm at the jack end) reads high,
and an open one reads low.

After three low reads with no edge, rain goes "rain-open" (fault). Cups go
"cups-suspect", and then "cups-open" if the vane moves or after 24 h (BIH:38-58, BI:38-48,
mod_wind.c:13-17). The probe can't see an open beyond the pull-up, in the cable or jack (mod_rain.c:3-6).

### 4.5 Charger signals to the MCU

| Signal | Circuit and values | MCU pin and mode | Conversion | Source |
|---|---|---|---|---|
| ISET (charge current monitor) | charger ISET -> 10 kohm 1 % series (at the charger end) -> ISET node -> PB1; node has 100 nF and 1 Mohm to logic ground | PB1 = ADC1_IN5, analog, no pull | V_ISET = V_PB1 x 1e6 / 990099 (1 Mohm / 1.01 Mohm, nominal until per-board fit); I = 400 x V_ISET / R_ISET (1000 ohm) (SLUS810 eq. 3), ±10 % + R_ISET tolerance; about 2.2 V at full fast charge | BSW:271, WT:281-312, PC:82-93 |
| Charger input (VBUS) | VBUS -> 10 kohm + 10 kohm (1 %) -> PA10 -> 10 kohm -> logic ground | PA10 = ADC1_IN6, analog, no pull | VIN = pin x 3 (POWER_VIN_DIVIDER_PPM 3000000, nominal until the three resistors are measured); full scale 3 x VDDA = 9.9 V; source 6.67 kohm needs >= 19.5 ADC cycles (firmware uses 160.5); draws VBUS / 30 kohm | BSW:279-280, PC:94-99, WT:245-279 |
| CHG | open drain, active low; breakout LED (10 kohm to OUT) | PB10, input, internal pull-up, EXTI10 both edges (edge count for 2 Hz fault detection) | bit 1 "charging"; 3+ edges in 2 s = fault, clears after 4 s | BI:15-16, BI:207-208, power_acq.c:22-24 |
| PGOOD | open drain, active low; breakout LED (10 kohm to OUT) | PB8, input, internal pull-up | bit 0 "input power good" | BI:14, BI:205-206 |

**Limits** (DS13293 through BSW:284-285). PB8 and PB10 are FT_f. But **with the internal pull-up on,
the pin must stay below min(VDD, VDDA) + 0.3 V**. The LEDs on OUT pull a released pin to at most 2.9 V,
measured on USB. Nobody measured the worst case on the panel yet (FM:295).

PA10 (FT_fa, no pull) allows
min(VDD,VDDA) + 3.6 V and <= 5.5 V. That means VBUS <= 16.5 V powered, and about 10.8 V unpowered
(PM:279-280). ADC clipping: an oversampled result >= 4080 is out of range, and the field is INVALID
(BSW:281).

**What the ISET network parts do** (PTD:718-723):

- The 100 nF is the source that the ADC samples.
- The 1 Mohm pulls an open wire to 0 V, so the CHG cross-check flags it.
- If a firmware fault drives PB1 low, ISET sees 909 ohm. That gives +10 % charge current, not a short.

**ADC set-up** for the vane, ISET, VIN and VREFINT (BI:22-26, BI:170-200, BIH:13-23):

- one interrupt-driven regular sequence: IN4, IN5, IN6, VREFINT
- 12-bit, 160.5 cycles each, hardware oversampling x16, shift 4
- about 0.9 ms a sequence at 12 MHz
- one offset calibration at boot
- VDDA = 3300 x VREFINT_CAL / VREFINT_raw (this part takes VREFINT_CAL at 3.3 V)

### 4.6 Complete MCU pin map (TX node)

Arduino positions from UM2592 Rev 4 Table 17, morpho aliases Table 18 (BSW:117-154, WT:35-50). A morpho
alias is the same MCU pin.

| Pin | NUCLEO header (Arduino; morpho alias) | Function | Dir | Net | Source |
|---|---|---|---|---|---|
| PA11 | D14, CN5.9; CN10.5 | I2C2 SDA (AF4, OD) | I/O | I2C_SDA | BSW:81, IBC:42-43 |
| PA12 | D15, CN5.10; CN10.3 | I2C2 SCL (AF4, OD) | I/O | I2C_SCL | BSW:81 |
| PB5 | D4, CN9.5; CN10.29 | anemometer cups, LPTIM1_IN1 (AF1) | in | CUPS | BSW:85, BI:4-5 |
| PB2 | A1, CN8.2; CN7.30 | wind vane, ADC1_IN4 | analog in | VANE | BSW:86, BI:6 |
| PB4 | A3, CN8.4; CN7.34 | rain gauge, EXTI4 falling (NJTRST released; SWD only) | in | RAIN | BSW:87, BI:12-13 |
| PB1 | A0, CN8.1; CN7.28 | bq24074 ISET node, ADC1_IN5 | analog in | ISET | BSW:97, BI:7-8 |
| PA10 | A2, CN8.3; CN7.32 | charger VBUS divider, ADC1_IN6 | analog in | VIN_SENSE | BSW:98, BI:9-11 |
| PB8 | D5, CN9.6; CN10.27 | bq24074 PGOOD, pull-up | in | PGOOD | BSW:88, BI:14 |
| PB10 | D6, CN9.7; CN10.25 | bq24074 CHG, pull-up, EXTI10 both edges | in | CHG | BSW:89, BI:15-16 |
| PA9 | D9, CN5.2; CN10.19 | sensor port power enable: **unconnected on the bench**; firmware drives it high | out | — | BSW:90, IBC:417-420 |
| PB14 | A4, CN8.5; CN7.36 | mux RESET, only in the `WS_I2C_MUX=1` variant; untouched otherwise | out | — | BSW:145, BI:221-229 |
| PA5 | morpho CN10.11 (D13, CN5.6) | OLED SCLK, SPI1_SCK (i2cscan and the TX bench build) | out | OLED_SCLK | BSW:91 |
| PA7 | CN10.15 (D11, CN5.4) | OLED DIN, SPI1_MOSI | out | OLED_DIN | BSW:92 |
| PA4 | CN10.17 (D10, CN5.3) | OLED CS | out | OLED_CS | BSW:93 |
| PC2 | CN10.21 (D8, CN5.1) | OLED DC | out | OLED_DC | BSW:94 |
| PC1 | CN10.23 (D7, CN9.8) | OLED RST | out | OLED_RST | BSW:95 |
| 3V3 | CN6.4 (= CN7.16) | hub and power-monitor supply; mode-B 3.3 V entry at CN6.4; OLED VCC at CN7.16 | pwr | 3V3 | BSW:82-83, BSW:96 |
| GND | CN6.6, CN6.7, CN10.20 | hub ground (CN6.6); mode-B return (CN6.7); OLED ground (CN10.20) | pwr | GND | BSW:82-84, BSW:96 |
| PA2, PA3 | VCP (to ST-LINK) | console UART, 115200 8N1 (firmware USART2; BSW calls it LPUART1, UM2592 Table 12) | I/O | — | usart.c:42-43, BSW:121 |
| PB12, PB13 | D2 CN9.3; A5 CN8.6 | ST debug probe outputs, always driven push-pull by DBG_Init: **not free** | out | — | BSW:143-144, BI:20-21 |
| PB15, PB9, PB11 | CN10.28, CN10.26, CN10.30 | LED1 blue, LED2 green, LED3 red | out | — | BSW:140-146, main.h:63-78 |
| PA0, PA1, PC6 | CN10.1, CN10.36, CN10.12 | buttons B1, B2, B3 | in | — | BSW:119-120, BSW:151 |
| PA13, PA14 | CN7.13, CN7.15 | SWD | — | — | BSW:130 |
| PB0; PC3-PC5; PC14-15; PH3 | — | TCXO supply; RF switch; LSE; BOOT0 | — | — | BSW:132, BSW:150, BSW:153-154 |
| PB6, PB7 | D1, D0 | USART1, **reserved, never a station signal** | — | — | BSW:109-110, BSW:138 |
| PB3 | D3, CN9.4 | T_SWO (via SB8): last-resort only | — | — | BSW:135 |
| PA15 | CN7.17 | T_JTDI: last-resort only | — | — | BSW:131 |
| Free | PA6 (D12), PA8 (CN10.16), PC0 (CN10.14), PC13 (CN7.23, slow signals only) | — | — | — | BSW:124, BSW:126, BSW:147, BSW:152 |

Header hazards: tape the 5 V pins "NO 5V". They're CN6.5 and CN6.8 (Arduino), and CN7.18, CN7.24, CN7.6
and CN10.8 (morpho). CN6.2 (IOREF) and CN5.8 (AVDD) stay empty (BSW:107-108, BSW:370-372). Build-time
asserts keep ST's RF debug outputs off PA10, PA11, PA12, PB2 and PB4 (BI:60-64). Station signals land on
the Arduino headers. Only the OLED uses morpho pins (BSW:100-105).

---

## 5. Firmware (TX node)

### 5.1 Architecture

Base: ST STM32CubeWL v1.6.0 SubGHz_Phy PingPong board support in `firmware/board/nucleo-wl55jc`. All the
bench firmware shares it. Mbed TLS 3.6.6 does the CCM (NR:8, PROTO:103-104). One source tree builds two
roles, picked by `ROLE=tx|rx` (Makefile:3-4).

**Event model.** There's no RTOS (EVM:13-36, NR:462). Interrupts copy data, start the next hardware step
or timer, and post event bits or sequencer tasks. The tasks (`process`, `sample`, `module_tick`,
`bus_task`, `console_task`, `check`) run one at a time and never wait. Idle enters low-power, but only
sleep (`LOW_POWER_DISABLE=1`). Interrupt priorities: radio and RTC alarm at 0, and ADC, EXTI, I2C and
console at 2 (EVM:17, BI:74).

Time comes from the RTC through `clock_ms()`. `HAL_GetTick` counts 1/1024 s, and nothing uses it
(EVM:40-43, NR:118). The firmware writes flash only while the radio is idle. If a minute report arrives
during an exchange, the firmware holds it in RAM, at most two of them (EVM:100-125).

**Main loop and ticks.**

| Timer | Period | Does | Source |
|---|---|---|---|
| module tick | 250 ms | `wsmp_host_tick`: one step of each local module, then reads its probe | EVM:49-51, wsmp_local.h:12 |
| sample tick | 15 s | counts ticks; the **4th latches every module and makes the minute report**; first report at 45 s | app_tx.c:43, EVM:52-56 |
| exchange | per minute | gap 50 ms, send, 2 s ACK window, next frame; TX timeout 3 s | tx_exchange.c:30-32, radio_cfg.h:18 |
| health report | 900 s and on link change | 64-byte kind 4 | tx_policy.c:19, PROTO:210-214 |
| watchdog check | 1 s | refresh IWDG (about 8 s: LSI/64, reload 4000) only if healthy | watchdog.c:12-15 |
| link probe | boot + 15 min | cups/rain link test (4.4) | BIH:48 |

**Module system (WSMP local modules).** Each sensor is a local WSMP module on a numbered port. A
`switch` per operation (probe, identify, latch, snapshot) drives it. The station host handles presence,
admission against the registry and radio budget, the minute latch and flap limits (NR:106-109,
wsmp_local.h:3-13).

| Port | Module type | Part(s) | Channels | Source |
|---|---|---|---|---|
| 1 `air_th` | 1 | SHT45 0x44 | T, RH (means) | wsmp_local.h:11, mod_th.c |
| 2 `pressure` | 2 | BMP581 0x47 | pressure | mod_reg.c:34 |
| 3 `uva` | 3 | LTR390 0x53 | UVA counts | mod_reg.c:36 |
| 4 `encl_th` | 4 | SHTC3 0x70 | T, RH | mod_th.c:22 |
| 5 `battery` | 8 | MAX17048, battery INA228 | V, I, energy in/out, charge in/out | mod_power.h:7-13 |
| 6 `wind` | 6 | SEN-15901 cups + vane | pulse counter, 3 s gust, east/north vector sums | mod_wind.h:3-5 |
| 7 `rain` | 7 | SEN-15901 bucket | tip counter | mod_rain.h:3-6 |
| 8 `rails` | 9 | INA228s, PA10 divider | load V/I, charger input V, solar V/I, USB-C V/I | mod_power.h:14-21 |

The battery and rails modules are base-board modules. They're present in every profile, whatever the
parts answer. A dead part gives INVALID fields, never absent ones (mod_power.h:23-27). The rain gauge is
a bare switch, so its presence is a stored setting (`SENSOR rain on/off`) (mod_rain.h:5-6). Module
states: absent, probing, identifying, admitted, active, suspect, quarantined, refused (wsmp_host.h:10,
the state diagram in `docs/module-protocol.md`, NR:249, WSMP:491-506).

**Drivers.**

| Driver | Behaviour | Source |
|---|---|---|
| `i2c_bus.c` | queued non-blocking I2C2, guard timer, stuck-bus recovery, counters | IBH:3-7 |
| `mod_th.c` | SHT45: cmd 0xFD, read 6 B a tick later; serial 0x89. SHTC3: wake 0x3517, measure 0x7866, read 6 B, sleep 0xB098; CRC-8 checked | mod_th.c:1-10, 53-55 |
| `mod_reg.c` | BMP581: CHIP_ID 0x01 = 0x50; OSR 0x36 = 0x40, ODR 0x37 = 0x82 (forced); PRESS 0x20-22 Pa x 64. LTR390: PART_ID 0x06 high nibble 0xB; MAIN_CTRL 0x00 = 0x0A (UVS); UVS_DATA 0x10-12, 20 bits. Configuration rewritten every sample | mod_reg.c:2-7, mod_reg.h:4-9 |
| `mod_wind.c` | cups bins every 250 ms; gust = max 12-bin (3 s) sum x 0.66698 m/s/Hz / 3 s; vane every 1 s | mod_wind.c:1-12, 24-37 |
| `power_acq.c` | INA228 per rail every 1 s (SHUNT_CAL check, VBUS 0x05, CHARGE 0x0A), DIETEMP every 60 s; MAX17048 every 15 s (VERSION, VCELL 78.125 µV/LSB, SOC 1/256 %, CRATE 0.208 %/h); board ADC every 1 s; CHG/PGOOD every 250 ms | power_acq.c:16-24, PTD:681-688 |
| `power_regs.c` (common) | INA228/MAX17048/ISET/divider/VREFINT conversions shared with i2cscan and benchlink | NR:112 |
| `board_inputs.c` | LPTIM1, ADC sequence, EXTI4/EXTI10, link probe | BI:1-48 |

**INA228 configuration** (PTD:689-703, PC:75-80):

- ADCRANGE 0 (±163.84 mV), CURRENT_LSB 10 µA, range ±5.24 A
- SHUNT_CAL = 131072 x lsb_µA x R_µΩ / 10^7 = 1966 for 15 mohm
- the firmware doesn't read the ENERGY register
- rail current = sign x ΣΔCHARGE / Σelapsed
- battery energy = ΣΔQ x latest VCELL. The VCELL must be <= 20 s old. If it isn't, that minute's energy fields are INVALID.

### 5.2 What it samples and how often

| Quantity | Sampling | Minute value | Source |
|---|---|---|---|
| Air T/RH (SHT45), enclosure T/RH (SHTC3), pressure, UVA | every 15 s | mean of the window (4 samples) | wsmp_local.h:13, mod_mean.h:3-7 |
| Cup pulses | counted continuously; read every 250 ms | counter since boot; 3 s gust max | mod_wind.h:3-5 |
| Vane | every 1 s | east/north unit-vector sums | mod_wind.c:28 |
| Rain | interrupt per tip | tips since boot | mod_rain.c:1-2 |
| INA228 rails | every 1 s | mean current, VBUS mean | power_acq.c:16 |
| MAX17048 | every 15 s | mean VCELL (4 reads) | PTD:112 |
| ISET, VIN, VDDA | every 1 s | means | power_acq.c:19 |
| CHG/PGOOD | every 250 ms | health report byte | power_acq.c:20 |

### 5.3 Fault handling, watchdog, storage, console, power profiles

**Watchdog.** The IWDG is about 8 s. Only the main loop refreshes it, and only when the TX is healthy.
Healthy means a sample in the last 150 s and no exchange past its bound ((frames + 1) x (3 s + 2 s +
50 ms) + 5 s).

On a stuck exchange, the firmware first stops sampling, stops the radio and journals the
held readings. Then it lets the reset happen. More than 10 journal or transmit failures in a row also
reset it (NR:347-351, EVM:198-208, app_tx.c:84, NR:252).

**Crash records.** A HardFault or a non-ECC NMI saves the registers to RTC backup DR5-DR11 and resets.
The next boot prints `#fault kind= pc= lr= cfsr= hfsr= bfar= count=`. DR6 keeps the last crash PC. DR12
counts boots since power-up, and power-on zeroes it. There's no backup battery, so a power loss clears
them.

A brown-out reads as "power" (NR:272-287). The run-time checks `WS_CHECK` count failures and
record the first site (NR:228).

**Boot self-test (KAT)** (NR:354-360). At boot the firmware:

- encodes and seals a known observation
- opens a known ACK/NACK
- checks that a tampered ACK fails
- checks that it refuses counter 2^40

If any of these fail, the board refuses to transmit.

**Flash map and journal** (256 KB, 128 x 2 KB pages) (flash_layout.h:4-8, NR:373-401):

| Pages | Use |
|---|---|
| 0-94 (190 KB) | firmware (linker-enforced); a flash rewrites only these |
| 95-124 | journal ring, 30 pages x 21 slots of 96 B (v6 field set) |
| 125-126 | monotonic log A/B: boot epoch, counter reservations (blocks of 256), lost/abandoned totals |
| 127 | config: station ID, key, KCV |

Slot = plaintext rounded to 8 B + commit double-word (magic + CRC-16) + ACK double-word. Page magic =
"WSJ" + slot size (0x57534A60). The journal holds >= 609 records, about 10.15 h without an ACK. On
overflow, the firmware erases the oldest page and counts it as `lost` (NR:389-401).

Torn writes read back
as burned. A torn ACK word counts as acknowledged (NR:450-453). 70 reset-during-write cycles passed, but
**nobody tested a true power removal yet** (NR:448, FM:266).

**Console** (ST-LINK VCP, 115200 8N1) (NR:172-175, tx_console.c:266):

| TX command | Does |
|---|---|
| `STATUS` | prints `#status`, `#counts`, `#timing` |
| `KAT` | reruns the self-test |
| `MODULES` | `#modules ...` and `#ident ...` per module |
| `SENSOR rain on` / `off` | stores whether the rain gauge is fitted |
| `PROVISION <id> <32 hex key> [epoch_floor]` | only when unprovisioned; use `ws0 provision-node`, never type a key |
| `WIPE ERASE-ALL-NODE-STATE` | erases key and journal, keeps counter/epoch/totals; reboots with solid red LED3 |
| `TEST-HANG`, `TEST-FAULT` | prove watchdog and crash records (bench) |
| `TEST-SENSOR-POWER` | PA9 power-cycle test; meaningless on the bench (PA9 unconnected) |
| `TEST-FLASH-STORM` | continuous flash writes for power-cut tests |

Key `#status` fields: `fw`, `reset`, `provisioned`, `station`, `kcv`, `kat`, `epoch`, `next_seq`, `ctr`,
`link`, `energy`, `time`, `meter_link` (NR:197-210). `#counts`: `pending`, `lost`, `burned`, `abandoned`,
`sent`, `acked`, `no_ack`, `tx_timeouts`, `i2c_recoveries`, `i2c_stuck`, `check_fails` (NR:214-228).
`#sample` comes once a minute (NR:247). The TX refuses commands that write flash during an exchange
(EVM:212-213).

**LEDs** (NR:364-369):

- LED1 blue: 400 ms = sending, a 40 ms blip every 2 s = alive
- LED2 green: ACK received
- LED3 red: 400 ms = no ACK, rejected ACK or TX timeout. 1 s = NACK or abandon. Solid = not running.

**Power profiles** (PC:7-39, NR:80-84):

| `WS_POWER_PROFILE` | Build | Rails |
|---|---|---|
| **1, phase A (default; the bench build)** | bq24074 + battery INA228 0x40 (VBUS on OUT fills `load_mv`) + MAX17048 0x36 | load current, solar, USB-C "not fitted" |
| 2, phase B | adds load 0x41, solar 0x45, USB-C 0x48 INA228s; battery VBUS not read | all |
| 3, phase C (the TX stack) | BQ25798 0x6B (`App/charger.c`) + battery INA228 0x40 (VBUS not read) + MAX17048 0x36; the charger's ADC fills the load voltage and the charger input. The energy state is live | load current, solar, USB-C "not fitted" |

Other build constants: `WS_I2C_MUX` is 0 (hub, default) or 1 (mux variant). `WS_NODE_FIELDS` defaults to
`WS_F_WSMP_BENCH` (77 B) (NR:83-84). The energy state is live only in profile 3 (the TX stack): CONSERVE 30 / 35 % SOC and
3.60 / 3.70 V, CRITICAL 8 / 13 % and 3.45 / 3.55 V (decision D1, settled 2026-11-22 with a 25 mW planning load,
`docs/radio-energy-policy.md` section 3, `firmware/common/ws_policy.c`). Profiles 1 and 2 stay NORMAL. Time: the TX sets its clock only from the ACK of the frame it just sent (UTC >=
2026-01-01). It trusts that time for 6 h and keeps it across a warm reset in RTC DR3/DR4 (tx_time.c:8-13,
PROTO:199-202, NR:460-461).

**Calibration constants still nominal** (PC:67-99):

- shunt 15,000 µΩ. You check this value against a series meter, and change it only if it fails.
- `POWER_R_ISET_OHM` 1000
- `POWER_ISET_GAIN_PPM` 990099
- `POWER_VIN_DIVIDER_PPM` 3000000

A dirty-tree build reports firmware build ID 0. So commit a measured constant before you flash
(PC:20-25, Makefile:25).

### 5.4 Build, release and gates

| Item | Fact | Source |
|---|---|---|
| Toolchain | xPack arm-none-eabi-gcc 15.2.1-1.1; `tools/fetch-vendor.sh` pins STM32CubeWL v1.6.0 and Mbed TLS 3.6.6 | NR:37-42, NR:67 |
| Outputs | `build/<role>/stage0-<role>.{elf,bin,map}`; prints size, flash budget and `.bin` SHA-256 | NR:64, NR:72 |
| Targets | `all`, `flash` (OpenOCD, connect under reset, verify), `stack` (worst-case vs 8 KB reservation), `waits` (no reachable busy-wait), `clean` | NR:72-76 |
| Budget | link fails above 90 % of 194,560 B; v6 build (default profile, 2026-11-04) TX 90,264 B (46.4 %), RX 34,904 B (17.9 %); field build `make ROLE=tx BOARD=wio-e5 WS_POWER_PROFILE=3 WS_I2C_MUX=1` TX 94,808 B (48.7 %) at `ee8e008` | NR:69, NR:384 |
| Release | clean tree, fetch-vendor, two clean builds with identical `.bin` hashes, flash RX then TX, check `fw=` on both `#boot`, record in RELEASES.md | REL:6-14 |
| Format change | drain journal (`pending=0`), WIPE, flash both from the same release, `init` a new run directory, provision with a new key, start a matching gateway, record | REL:16-27 |

`tools/gates.sh` (local copy of CI, exit 0 only if all pass) (gates.sh:18-53, TR:20):

| Gate | Checks |
|---|---|
| ruff | Python lint |
| code shape | `code_shape.sh`: lizard (CCN <= 10, <= 60 lines a function), jscpd (no copies), `loop_bounds.py`, `tangle.py --check` (literate sources match), `wsmp_registry.py --check` (TR:12) |
| cppcheck | any finding fails |
| two clean builds | RX and TX built twice, identical `.bin` hashes, flash budget line, no heap |
| bench firmware | rangetest, i2cscan, benchlink (tx and rx) build |
| gcc -fanalyzer | both roles with `ANALYZE=1` |
| stack bound | `make stack` both roles |
| no blocking waits | `make waits` both roles |
| TX profile variants | phase B (`-DWS_POWER_PROFILE=2`) and mux (`-DWS_I2C_MUX=1`): analyzer, stack, waits |
| unit tests | `python -m unittest discover -s tests` (with firmware C on the host) |
| fuzz | standalone, 1M runs a target |
| Power of Ten rule 1 | no `goto`, `setjmp`, `longjmp` in scope |

CI (`.github/workflows/ci.yml`) adds libFuzzer 60 s a target and compares bins with RELEASES.md
(non-gating) (TR:52-54).

---

## 6. Firmware (RX bridge) and the other bench firmware

### 6.1 RX bridge (`stage0-node`, `ROLE=rx`)

| Aspect | Behaviour | Source |
|---|---|---|
| Role | keyless: never decrypts; forwards any canonical v6 observation (39-110 B) or health report (80 B) as one lowercase hex line, then `#rx obs rssi= snr=` | NR:175, NR:293-294 |
| Radio | continuous receive, same settings as TX | EVM:228, radio_cfg.h:19 |
| Downlink | takes one 66-hex-digit ACK/NACK line from the host and transmits it once; one in flight; TX timeout 3 s | NR:175, NR:299 |
| Diagnostics | `#rx drop`, `#rx crc len= ... data=<hex>` (bytes kept by the radio), `#rx hdr rssi=`, `#host reject`, `#tx timeout/busy`, `#alive` every 60 s | NR:295-300 |
| Self-heal | relisten after 16 min without radio events; two in a row fail health -> watchdog reset; console output stopped 3 s fails health | NR:300-302 |
| Commands | `STATUS`, `TEST-HANG`, `TEST-FAULT`, or an ACK/NACK hex line; lines starting `#` ignored; non-ASCII, > 256 chars or damaged lines discarded | NR:175 |
| LEDs | blue = forwarded, green = ACK handed to radio, red = error | NR:366-368 |
| USB rule | RX alone on a direct Mac port, never replugged during a run; TX on another port; label cables by ST-LINK serial | BSW:492-497 |

### 6.2 Other bench firmware

| Firmware | Purpose | How used | Source |
|---|---|---|---|
| `firmware/benchlink` | plain (unencrypted) LoRa power-telemetry link for the charger/battery bench; TX samples every 250 ms, sends a 78 B packet every 5 s at **10 dBm**, 915 MHz/500 kHz/SF7/CR4/5; RX prints each packet; a Mac logger writes CSV and a dashboard charts it. Same MCU pins as the node. Not H01 evidence | `make ROLE=tx flash SERIAL=<TX>`, `make ROLE=rx flash SERIAL=<RX>`; then `tools/benchlink_log.py`, `tools/benchlink_dash.py` | BL:3-22, BL:58-64, benchlink.c:133 |
| `firmware/i2cscan` | I2C2 bench check. It only reads the power parts (INA228, MAX17048) and sends the weather sensors (SHT45, SHTC3, BMP581, LTR390) only the commands a reading needs. It checks pull-ups, scans every 10 s, reads INA228/MAX17048, the air sensors and the weather meter (cups, vane, rain) once a second, and the phase B rails if present. It draws on the bench OLED, drives PA9 high and has no radio | `make flash SERIAL=<TX>`; miniterm at 115200 | I2CS:3-9, I2CS:13-67, I2CS:72-84 |
| `firmware/rangetest` | bidirectional link test about once a second with a 16 B ping-pong; buttons step TX power (+22/+14/+10/0 dBm) and SF (12/10/9/7); boot and fallback SF12/+22 dBm; 915 MHz/500 kHz/CR4/5 fixed; both boards same image | `make flash` both; `tools/rangetest_log.py <serial> <csv>` | RT:3-34, RT:38-45 |

All three link inside the 190 KB firmware region, so the node's key and journal (pages 95-127) survive.
Reflash the node release afterwards (BL:24-26, I2CS:76-78, RT:51-54).

---

## 7. Protocols

### 7.1 LoRa radio settings and link behaviour

| Parameter | Value | Source |
|---|---|---|
| Frequency | 915.0 MHz, single channel | radio_cfg.h:11 |
| Bandwidth | 500 kHz (FCC 15.247(a)(2) digital-modulation class; never below 500 kHz) | radio_cfg.h:6-13, PS:629-637 |
| SF / CR / preamble | SF7, 4/5, 8 symbols | radio_cfg.h:14-16 |
| Header / CRC / IQ / sync | explicit, 16-bit CRC on, normal IQ, private sync word 0x1424 | PS:603-607 |
| TX power | 0 dBm (bench value; benchlink 10 dBm) | radio_cfg.h:12 |
| Symbol timeout | 0 (off): 5 symbols at SF7/500 kHz = 1.3 ms closed the ACK window early; firmware's 2 s timer bounds RX | radio_cfg.h:17, PS:641-645 |
| TX timeout | 3 s | radio_cfg.h:18 |
| Airtime at SF7 | 93 B obs 41.0 ms, 81 B 35.9 ms, ACK 18.0 ms, health 35.9 ms; SF12 821.2 / 739.3 / 411.6 / 739.3 ms | PS:614-627 |
| Measured | 30 cm, 0 dBm: RSSI -23/-24 dBm, SNR 12-13 dB (bench, not range) | PS:647-658 |

**Link behaviour** (NR:312-315, EVM:129-194). Each minute the live reading goes first. Up to 5 pending
readings follow, capped at about 5 s of estimated airtime. In a health minute, the TX reserves the
health report's airtime first.

Each frame gets one 2 s ACK window. After a miss, the TX sends one more frame.
A second miss or a TX failure ends the drain. After 3 silent minutes, the state goes to `probing` (live
reading only).

The TX abandons a record on a NACK, or after 10 strikes (tx_policy.c:17, tx_policy.c:75-81). A strike is
a try that went unanswered while the gateway answered a later frame in the same exchange. Misses on a
dead link don't count. Health reports have no journal and no ACK.

### 7.2 Over-the-air frame (protocol version 6)

**Envelope** (big-endian everywhere) (PROTO:54-60, PROTO:64-69):

| Offset | Bytes | Field |
|---|---|---|
| 0 | 1 | high nibble version 6, low nibble kind: 0x61 observation, 0x62 ACK, 0x63 NACK, 0x64 health report |
| 1 | 2 | station ID, 1-65535 |
| 3 | 5 | transmission counter, 1 to 2^40-1 |
| 8 | n | AES-128-CCM ciphertext |
| 8+n | 8 | CCM tag (M = 8) |

Crypto details (PROTO:86-105, PROTO:140-168):

- AAD = the 8 header bytes.
- Nonce (13 B) = kind (u8) + station (u32) + counter (u64), built from integers.
- The key is 128-bit, one per station. KCV = the first 3 bytes of AES(key, 0^16).
- The node counter space covers the observation and the health report. The node reserves it in flash, in blocks of 256.
- The gateway counter space covers ACK/NACK (`gateway-nonces.sqlite3`).
- A frame-format change needs a new key.

**Frame lengths** (PROTO:113-131), plaintext/frame:

- observation: 23-94 B / 39-110 B. The node build ceiling is 80/96 B, and the current node field set is 77/93 B.
- ACK/NACK: 17/33 B
- health report: 64/80 B

The gateway checks length, version, kind and station before it decrypts. It sends nothing for a failed
frame.

**ACK/NACK plaintext, 17 B** (PROTO:182-187):

- epoch (u32)
- sequence (u32)
- u32: in an ACK, the host UTC at commit (0 if the gateway's clock is wrong). In a NACK, the reason (1 identity collision, 2 invalid record).
- echo of the answered frame's counter (u40)

The gateway sends the ACK only after the SQLite commit.

**Observation plaintext** (PROTO:449-459):

| Offset | Bytes | Field |
|---|---|---|
| 0 | 4 | epoch (boot epoch, durable, +1 per boot) |
| 4 | 4 | sequence within the epoch, from 0 |
| 8 | 4 | sample UTC, Unix s (0 = unknown) |
| 12 | 4 | uptime, s |
| 16 | 1 | flags: bit 0 UTC known; bits 1-2 energy state (0 surplus, 1 normal, 2 conserve, 3 critical); bits 3-7 zero |
| 17 | 1 | calibration revision (0) |
| 18 | 4 | field bitmap: bit i = field i for 0-30; bit 31 = EXT |
| 22 | 2 | extension bitmap (only if EXT): bit j = field 32+j |
| 22/24 | k | present fields in increasing index, each big-endian unsigned of its width |

Value = (code - offset) / scale. INVALID is the all-ones code, and it means a fitted source failed or
was out of range. Absent (not in the bitmap) means this build has no source for it (PROTO:483-503,
PROTO:540).

**Field catalog v2** (PROTO:545-581):

| i | Field | B | Unit / step | Offset | Range | Built from |
|---:|---|---:|---|---:|---|---|
| 0 | `temperature_c` | 2 | 0.01 °C | 4000 | -40.00..125.00 | SHT45 |
| 1 | `humidity_pct` | 2 | 0.01 % | 0 | 0..100.00 | SHT45 |
| 2 | `pressure_hpa` | 2 | 0.1 hPa | -3000 | 300.0..1100.0 | BMP581 |
| 3 | `wind_speed_ms` | 2 | 0.1 m/s, minute mean | 0 | 0..75.0 | cups |
| 4 | `wind_gust_ms` | 2 | 0.1 m/s, max 3 s mean | 0 | 0..75.0 | cups |
| 5 | `wind_dir_deg` | 2 | 1° | 0 | 0..359; 0xFFFE CALM | vane |
| 6 | `rain_tips` | 3 | tips since boot | 0 | counter | rain |
| 7 | `uv_index` | 1 | 0.1 UVI | 0 | 0..25.0 | defined, not built |
| 8 | `irradiance_wm2` | 2 | 1 W/m² | 0 | 0..2000 | defined |
| 9 | `uva_raw` | 3 | counts | 0 | 0..2^20-1 | LTR390 |
| 10 | `qualifiers` | 4 | 2 bits per field 0-15 | — | no INVALID | defined |
| 11 | `batt_mv` | 2 | 1 mV, cell (gauge VCELL) mean | 0 | 0..65534 | battery module |
| 12 | `batt_current_ma` | 2 | 1 mA offset binary, + into cell | 32768 | -32768..+32766 | battery INA228 |
| 13 | `energy_in_mwh` | 3 | mWh since boot, ΣΔQ x VCELL (charging) | 0 | counter | battery |
| 14 | `energy_out_mwh` | 3 | mWh since boot (discharging) | 0 | counter | battery |
| 15 | `charge_in_mah` | 3 | mAh since boot into cell | 0 | counter | battery |
| 16 | `charge_out_mah` | 3 | mAh since boot out of cell | 0 | counter | battery |
| 17 | `soc_gauge_pct` | 1 | % | 0 | retired in v6 | — |
| 18 | `charger_pins` | 1 | bits | 0 | retired in v6 | — |
| 19 | `enclosure_temp_c` | 2 | as 0 | 4000 | | SHTC3 |
| 20 | `enclosure_rh_pct` | 2 | as 1 | 0 | | SHTC3 |
| 21-24 | T/RH min/max | 2 each | as 0/1 | | defined, not sent | — |
| 25 | `th_samples` | 1 | count of valid T/RH samples | 0 | 0..60 | SHT45 module |
| 26 | `load_mv` | 2 | 1 mV, OUT mean | 0 | | battery INA228 VBUS (A) |
| 27 | `load_current_ma` | 2 | 1 mA offset binary, + into load | 32768 | | load INA228 (B) |
| 28 | `charger_input_mv` | 2 | 1 mV, after the join, under load; source not identified | 0 | | PA10 divider |
| 29 | `solar_mv` | 2 | 1 mV, upstream of join | 0 | | solar INA228 (B) |
| 30 | `solar_current_ma` | 2 | 1 mA offset binary, + into station | 32768 | | solar INA228 (B) |
| 31 | — | — | EXT bit | | | |
| 32 | `usb_mv` | 2 | 1 mV, upstream of join (ext bit 0) | 0 | | USB-C INA228 (B) |
| 33 | `usb_current_ma` | 2 | 1 mA offset binary (ext bit 1) | 32768 | | USB-C INA228 (B) |
| 34-47 | reserved | | must be zero | | | |

Records by phase (PROTO:472-476):

- phase A: fields 0-6, 9, 11-16, 19, 20, 25, 26, 28, bitmap `0x1619FA7F`, 65 B (81 B frame)
- phase B adds 27, 29, 30, 32, 33: bitmap `0xFE19FA7F` + ext `0x0003`, 77 B (93 B)

Example known answer: epoch 1, seq 2, T -12.34 °C -> code 0x0ACE, RH 45.67 % -> 0x11D7
(PROTO:505-524).

**Health report plaintext, 64 B** (PROTO:256-288):

| Off | B | Field | None code |
|---:|---:|---|---|
| 0 | 4 | epoch | — |
| 4 | 4 | uptime s | — |
| 8 | 2 | journal pending | — |
| 10 | 4 | journal lost total | — |
| 14 | 2 | torn slots | — |
| 16 | 2 | abandoned total | — |
| 18 | 2 | missed ACKs since boot | — |
| 20 | 2 | rejected replies since boot | — |
| 22 | 1 | reset cause: 0 unknown, 1 power, 2 pin, 3 brownout, 4 software, 5 watchdog, 6 lowpower, 7 option-bytes | — |
| 23 | 1 | link: 0 linked, 1 probing | — |
| 24 | 4 | firmware build ID (first 8 hex of commit; 0 if dirty) | — |
| 28 | 1 | ACK RSSI dBm (i8) | -128 |
| 29 | 1 | ACK SNR dB (i8) | -128 |
| 30 | 1 | crashes since power-up | — |
| 31 | 1 | energy state | — |
| 32 | 4 | last crash PC | 0 none, 0xFFFFFFFF untrusted |
| 36 | 2 | boots since power-up | — |
| 38 | 2 | TX timeouts since boot | — |
| 40 | 2 | I2C recoveries since boot | — |
| 42 | 2 | VDDA mV | 0xFFFF |
| 44 | 2 | hottest INA228 die, 0.1 °C (i16) | -32768 |
| 46 | 2 | gauge SOC, 1/256 % | 0xFFFF |
| 48 | 2 | SOC rate, 0.1 %/h (i16) | -32768 |
| 50 | 1 | charger status | 0xFF |
| 51 | 1 | fitted byte (bit 7 = 0) | — |
| 52 | 2 | charger-reported input mV | 0xFFFF |
| 54 | 2 | charger-reported input mA (i16) | -32768 |
| 56 | 2 | charger-reported battery mV | 0xFFFF |
| 58 | 2 | charger-reported charge mA (i16); phase A = ISET current while PGOOD, 0 without | -32768 |
| 60 | 2 | charger die temp 0.1 °C | -32768 |
| 62 | 2 | pack temp 0.1 °C | -32768 |

Charger status byte (PROTO:367-375):

- bit 0: input power good (PGOOD)
- bit 1: charging (CHG steady)
- bit 2: fault (CHG 3+ edges in 2 s, clears after 4 s)
- bits 3-5: stage (0 in phase A, 7 non-canonical)
- bits 6-7: active input (0 = not reported in phases A/B)

Fitted byte (PROTO:305-316): bit 0 VDDA, 1 monitor temp, 2 gauge, 3 charger status bits 0-2, 4 charger
registers, 5 charge current, 6 pack temp. Phases A and B send 0x2F. A none code under a set bit means a
sensor fault. Under a clear bit it means not measured. SOC over-reads during a charge (PROTO:347-350).

### 7.3 WSMP (DATAVANE5K module protocol)

Version 1.1 draft. The station side works for local modules. The radio part, remote modules and the UTC
latch aren't implemented (WSMP:3-7). WSMP is the contract between the station and its modules. Local
drivers present the same blocks that a remote Modbus module would (WSMP:10-13, WSMP:629-646).

| Element | Definition | Source |
|---|---|---|
| Registry | versioned codes for quantities, units, kinds, module types (types 1-9 above; type 5 frozen, replaced by 8 and 9); generated from `firmware/common/wsmp_registry.toml` | WSMP:121, WSMP:216-238, TR:25 |
| Descriptor (6 B) | quantity (u16), unit, scale (power of ten, -6..+6), air width-1, signed, kind; value = integer x 10^scale | WSMP:315-350 |
| Identity block (32 B) | magic 0x5753, WSMP version, module type, schema + channel count, serial (u64), firmware version/build, boot ID (local modules use the station boot epoch), capabilities, descriptor digest (CRC-32C) | WSMP:380-399 |
| Snapshot (72 B) | header: latch token, boot ID low 16, window ms, flags (first window, long window, sensor fault), descriptor tag; 8 slots of value (u32), sample count (u16), quality (u8) | WSMP:418-458 |
| Quality codes | 0 good, 1 partial, 2 suspect, 3 missing, 4 warming up, 5 sensor fault, 6 not fitted | WSMP:597-606 |
| Presence/admission | absent -> probing -> 2 good probes -> identifying -> admitted/quarantined/refused; active <-> suspect; 3 latches without a good read -> absent. A local I2C module is present after a successful sample; address NACK = absent; other failures = bus fault; BMP581/LTR390/INA228 also check chip ID | WSMP:491-520 |
| Identity verdict and records | per-port module records in an ID EEPROM (0x50) with namespaced serials (0x00 port, 0x01 record, 0x02 sensor) and statuses (applied, NO_RECORD, CAL_REJECTED, SENSOR_CHANGED); in the hub build no EEPROM exists, so port modules are admitted as NO_RECORD | firmware/common/wsmp_ident.lit.md:1-30, IBH:9-11, NR:250 |
| To the gateway | today the interim map `wsmp_catalog_map.c` turns snapshots into catalog fields; descriptor sets on the radio come later | NR:113, WSMP:656-700 |

### 7.4 USB/serial framing to the Mac

| Direction | Line | Source |
|---|---|---|
| Physical | MCU UART PA2/PA3 -> ST-LINK V3E -> USB CDC `/dev/cu.usbmodem*`, 115200 8N1; identify boards by ST-LINK serial, not port name | PS:801-810, ws0/link.py:18 |
| RX -> host | frame as lowercase hex + `\n` (up to 186 chars for 93 B; 160 for a health report) | PS:816 |
| RX -> host | `#...` diagnostics, logged to `receiver.log`, never decoded as frames; `#alive` every 60 s; receiver silent after 180 s | PS:817-820, ws0/__main__.py:25 |
| host -> RX | 66 hex digits + `\n` (33 B ACK or NACK), or `STATUS` | PS:820-821 |
| Limits | RX accepts host lines <= 256 B (`WS_LINE_MAX`); gateway accepts <= 1024 chars; longer dropped whole | PS:825, ws_console.h:6, ws0/link.py:25 |
| Robustness | exclusive open (flock); reconnect back-off 1, 2, 4, 8, 15 s; reopen an open-but-silent port after 90 s, doubling to 400 s | PS:810, ws0/link.py:1-26 |

### 7.5 Gateway ingest, storage and outputs

| Stage | Behaviour | Source |
|---|---|---|
| Accept | check length, version (6), kind, station; decrypt; decode; validate against a closed schema | PROTO:119-122, GW:32-40 |
| Store | `ingest` returns only after a WAL commit with `synchronous=FULL` and `F_FULLFSYNC` (about 5.3 ms median); identity (station, session=epoch, sequence) immutable; exact repeat = no-op, different payload = collision (NACK 1) | GW:32-36, GW:90-135 |
| Reply | ACK sealed only after commit; NACK only for an authentic, permanently invalid record, stored in `rejections` first | PROTO:192-195 |
| Health reports | stored in `diagnostics`, ordered by (epoch, uptime); none codes -> null; derived lists `power_not_measured`, `power_sensor_faults` | PROTO:212-214, PROTO:316-320 |
| Time | samples without UTC get reconstructed time from the nearest synchronized sample of the same boot epoch. Error bound: 2 s of quantisation (1 s on each of the two whole-second fields, the sample uptime and the reference) plus 150 ppm of the time span to the reference | gateway.py:16-22, GW:598-648 |
| Freshness | latest reading current only if known, bounded, not future and younger than the live interval + 120 s for the energy state it carries (180 s SURPLUS/NORMAL, 420 s CONSERVE, 3,720 s CRITICAL); a health report fresh for max(1,900 s, that) | `gateway.py` `current_max_age`, `ws0/service.py` `health_max_age` |
| Files (run directory, git-ignored) | `gateway.json` (config incl. radio key and API token: secrets), `observations.sqlite3`, `gateway-nonces.sqlite3`, `receiver.log`, optional `mqtt-password` | NR:168, PROTO:143, HA:25-28 |
| HTTP | 127.0.0.1:8088 by default; dashboard at `/`, API `/v1/status`, `/v1/history`, `/v1/events` (SSE), `/v1/radio`, `/v1/diagnostics`, `/v1/receiver/alive`, `/v1/gateway/events`; bearer token required | ws0/__main__.py:39, WEB:22-27, WEB:221-223, WEB:242-258 |
| Dashboard | readings, power view (absent = "not measured in this build", null = "sensor fault"), node health, RX `#alive`, bad receptions, recent frames | WEB:29-40, WEB:71-92 |
| MQTT | root `weatherstation/v1/<station>`, retained, QoS 1: `.../weather` (on change and every 300 s), `.../availability`, `.../gateway_availability` (last will), `.../diagnostics`, `.../modules`; HA discovery `homeassistant/sensor/<station>_<field>/config` and health keys under `<station>_diag_<key>`; counters `total_increasing`; power/enclosure fields are diagnostic entities | HA:96-119 |
| MQTT config | `gateway.json` `mqtt`: enabled, host, port (1883), tls, username; password only in `<run>/mqtt-password` (mode 600) or `WS_MQTT_PASSWORD`, never in git or chat | HA:20-25 |

### 7.6 Benchlink packet (version 4) and CSV

**Packet**: 78 B, little-endian, CRC-16/CCITT-FALSE over bytes 0-75, one every 5 s (BLP:1-40):

| Off | Type | Field |
|---:|---|---|
| 0 | 'W' 'B' | magic |
| 2 | u8 | version (4) |
| 3 | u8 | flags: 0x01 INA ok, 0x02 gauge ok, 0x04 SHT ok, 0x08 PGOOD low, 0x10 CHG low, 0x20 ADC valid, 0x40 VIN clipped, 0x80 ISET clipped |
| 4 | u32 | seq since boot |
| 8 | u32 | uptime s since power-on |
| 12 | i32 | INA228 VBUS µV (OUT) |
| 16 | i32 | INA228 shunt current µA, raw sign (+ = out of the cell) |
| 20/24/28 | i32 | ISET node mean/min/max µV (PB1, behind the ISET network) |
| 32 | i32 | INA228 die m°C |
| 36 | i32 | MAX17048 VCELL µV |
| 40 | i32 | SOC milli-% |
| 44 | i32 | CRATE milli-%/h |
| 48 | i32 | SHT45 temperature m°C |
| 52 | i32 | SHT45 RH milli-% |
| 56 | i32 | charger input µV (PA10 x divider) |
| 60/61 | u8 | good/failed INA228 samples |
| 62 | u8 | reset cause |
| 63 | u8 | crashes since power loss |
| 64 | u16 | boots since power loss |
| 66 | u16 | TX timeouts |
| 68/70 | u16 | I2C restarts / of those, SDA unsticks |
| 72 | u32 | last crash PC |
| 76 | u16 | CRC |

RX console line: `#bl rssi= snr= len= hex=` per packet, and `#bl hb ...` every 10 s (benchlink.c:9-13).

**CSV** (`tools/benchlink_log.py`, one row per packet). Columns: `utc, local, rssi, snr, seq, gap,
uptime_s, ina, gauge, sht, pgood, chg, adc, charge_ma, charge_min_ma, charge_max_ma, load_ma, vout_v,
vcell_v, soc_pct, rate_pct_h, temp_c, rh_pct, ina_die_c, ishunt_ma, battery_ma, samples, misses, vin_v,
reset, boots, faults, fault_pc, tx_timeouts, i2c_restarts, i2c_unsticks, version` (benchlink_log.py:99-117).
Derived columns (BL:110-119):

- `charge_ma` = 400 x (V_PB1 / 0.990099) / 1000 ohm
- `battery_ma` = -`ishunt_ma` (+ into cell, v4 only)
- `load_ma` = OUT / 100 ohm (an estimate)
- the logger writes clipped readings as empty

A side file
`<name>-events.csv` records boots, silences, alerts and the `logger_start` constants (TR:15).

---

## 8. How to run it

Run these from the repository root, with the project virtualenv (README.md:40-44, NR:37-42, TR:3). Keep
secrets off command lines. `console.py` refuses `PROVISION` (TR:19).

```sh
# one-time setup
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt   # requirements-dev.txt for gates
sh tools/fetch-vendor.sh                     # pinned STM32CubeWL v1.6.0 + Mbed TLS 3.6.6

# find boards (ST-LINK serials: TX 003B00194142500E20353451, RX 0016001E4142500E20353451)
.venv/bin/python -m serial.tools.list_ports -v

# build and flash the node firmware (both boards, same build)
cd firmware/stage0-node
make ROLE=rx flash SERIAL=0016001E4142500E20353451
make ROLE=tx flash SERIAL=003B00194142500E20353451
# phase B or mux variants: make ROLE=tx OPT='-Os -DWS_POWER_PROFILE=2'
cd ../..

# provision and serve (a new run directory per key; run*/ is git-ignored and holds secrets)
.venv/bin/python -m ws0 init --hardware --station station-01 --station-id 1 --directory run-<name>
.venv/bin/python -m ws0 provision-node --directory run-<name> --serial /dev/cu.usbmodem<TX>
.venv/bin/python -m ws0 serve --directory run-<name> --serial-number 0016001E4142500E20353451
.venv/bin/python tools/status.py --directory run-<name>
# dashboard: http://127.0.0.1:8088/ (paste the api_token from the run's gateway.json in the browser)

# long runs: launchd agent that restarts the gateway
tools/deploy/macos/install.sh install run-<name> 0016001E4142500E20353451
tools/deploy/macos/install.sh status

# console and checks
.venv/bin/python tools/console.py 003B00194142500E20353451 STATUS
.venv/bin/python tools/console.py 003B00194142500E20353451 MODULES
.venv/bin/python tools/console.py 003B00194142500E20353451 "SENSOR rain on"
.venv/bin/python tools/rx_faults.py --db run-<name>/observations.sqlite3
.venv/bin/python tools/h01_report.py --db run-<name>/observations.sqlite3 --station station-01 \
    --start <ISO UTC> --hours 24 --output evidence/<run>

# bench power link (benchlink) and its logger/dashboard
make -C firmware/benchlink ROLE=tx flash SERIAL=003B00194142500E20353451
make -C firmware/benchlink ROLE=rx flash SERIAL=0016001E4142500E20353451
.venv/bin/python tools/benchlink_log.py --serial-number 0016001E4142500E20353451 \
    --out evidence/<run>/benchlink.csv [--preflight evidence/<run>/notes.md]
.venv/bin/python tools/benchlink_dash.py --csv evidence/<run>/benchlink.csv   # http://127.0.0.1:8099/

# I2C and power check with the OLED
make -C firmware/i2cscan flash SERIAL=003B00194142500E20353451
.venv/bin/python -m serial.tools.miniterm /dev/cu.usbmodemXXXX 115200

# range test (both boards), then log one
make -C firmware/rangetest flash SERIAL=<each board>
.venv/bin/python tools/rangetest_log.py 0016001E4142500E20353451 evidence/<run>/rangetest.csv

# simulation and gates
python -m ws0 demo
python -m ws0.harness --output my-simulation-results
tools/gates.sh
```

To re-key, send `WIPE ERASE-ALL-NODE-STATE` to the TX. Then make a **new** run directory and run
`provision-node` (NR:155-157). Drain the journal (`pending=0`) before any format or field-set change
(NR:444).

Bench acceptance checks to repeat on the new build (BSW:439-451):

1. After a minute, `MODULES` shows every module `active`. Rain stays `absent` until `SENSOR rain on`.
2. Hot-plug a sensor. It goes suspect -> absent -> active, with no reset.
3. 100 counted cup pulses read within ±1.
4. All 20 bucket tips show up in the count.
5. `meter_link=ok`.
6. Mode A sign check: battery current is negative with no input and positive during a charge.
7. One hour in mode B with no reset.

---

## 9. Known limits and open hardware questions for the breadboard build

### 9.1 To confirm on the part in hand

| # | Question | Why it matters | Source |
|---|---|---|---|
| 1 | bq24074 TMR tied to GND? (ohms TMR-GND, charger unpowered) | if floating, a 4-6 h safety timer ends long 1 A charges with CHG flashing | BSW:272, BSW:480 |
| 2 | R_ISET really 1 kohm (ISET-GND, unpowered, pack out) | sets I_CHG and the ISET conversion | BSW:472 |
| 3 | THERM solder jumper cut (TS about 0.75 V at 25 °C, not 0.375 V) | otherwise no cold cut-off | BSW:475, FM:293 |
| 4 | INA228 SJ1 open on every board (VBUS to VIN+ open) | closed SJ1 ties the cell to OUT and bypasses 4.2 V regulation: a safety hazard | BSW:471, FM:290 |
| 5 | #4755 EN1/EN2 jumper states (SJ2/SJ1) | phase B needs EN2 high, EN1 low; VIN-DPM behaviour depends on it | PM:206-208, PM:353 |
| 6 | Divider resistors R4-R6 measured (ratio stored) | VIN accuracy within 1 % | BSW:279, PC:94-99 |
| 7 | ISET gain fit (CC charge > 200 mA vs INA228) | ISET conversion nominal until then | PC:88-93 |
| 8 | Shunt verified: INA228 current vs a series meter within 2 % + 2 mA | nominal 15 mohm otherwise | BSW:473 |
| 9 | Released CHG/PGOOD voltage on the panel at its highest Voc (with pull-ups) | must stay < min(VDD,VDDA) + 0.3 V; 2.9 V measured only on USB | BSW:476, FM:295 |
| 10 | Real vane voltages for all 16 positions | firmware uses computed values | BSW:421-428 |
| 11 | RJ11 conductor mapping by continuity; are the BOB-14021 jacks soldered and the panel separated | pinout is from the meter datasheet, not measured here | BSW:175-177, INV:36 |
| 12 | Pololu S7V8F3 pin order | "bench check": no maker page shows it | WT:232-233 |
| 13 | Pack JST PH polarity | colours vary | WT:323 |
| 14 | Charger DC jack size (5.5 x 2.1 mm by inference) | panel plug fit | PM:181-182 |
| 15 | OLED in SPI mode (R19/R21 fitted, R18/R20 empty); OLED not listed in the inventory | display stays dark otherwise | WT:396, INV (absent) |
| 16 | NUCLEO solder bridges on the station pins (visual) | open item of the UM2592 checklist | BSW:381-383 |
| 17 | NUCLEO 3V3 measured in modes A and B | not measured yet; allowed 3.0-3.6 V | BRU:504 |
| 18 | Breadboard size of the three boards on hand (830-point?) and split rails | unrecorded | INV:34, INV:540, WT:33 |
| 19 | BMP581 address (0x47 in firmware; SHOP says 0x46 or 0x47) | ID fails if strapped to 0x46 | mod_reg.c:34, SHOP:33 |
| 20 | Bus pull-up measured >= 0.97 kohm, idle SDA high | many breakouts in parallel | PM:326-330 |

### 9.2 Measured vs nominal and untested

| Item | Status | Source |
|---|---|---|
| Shunt in the battery path at 1 A, normal termination (CHG release at 0.20-0.40 A, cell >= 4.12 V) | not yet proven (phase A exit criteria 3 and 4) | PTD:66-85, BRU:500 |
| Node firmware reading the power chain | not yet run on hardware (benchlink did) | BRU:506 |
| Cup bounce filter and vane calibration | still need bench checks | NR:464 |
| Gauge VCELL vs meter (within 10 mV at rest; at 1 A at its own sense points) | open | BSW:478 |
| True power removal during flash writes | never tested (only resets) | NR:448, FM:266 |
| Brown-out vs power-on | indistinguishable; no low-voltage inhibit | FM:298, FM:504 |
| Backup domain across a real power loss | open question | NR:461 |
| Weak-source (low-sun) PGOOD/CHG cycling with EN2 high | analysed only | PM:246-271 |
| 6 dB bandwidth and antenna gain | not measured; Part 15 reading is not a certificate | PS:635 |
| Two NUCLEOs on one hub stalled the RX serial port once | rule: RX alone on a direct Mac port | BSW:489-497 |
| Phase B wiring | the three extra INA228 rails (load, solar, USB-C) are documented in PM but not yet in the breadboard model: the new layout must add them | PM |

### 9.3 Electrical rules the new layout must keep (restated from the sources)

1. No battery, charge, input or load current goes through any breadboard strip, header pin or Dupont
   contact. The only exception is the regulator chain in battery mode (BSW:215-217, BSW:310-312).
2. Exactly one conductor joins power ground (pack-negative star) and logic ground. Module grounds come
   over their QT cables. Insulate the unused pigtail minus leads (FM:310, BSW:223).
3. The gauge red lead goes on the cell side of the shunt (CELL+). The INA228 VBUS gets its own sense lead
   to OUT. Sense leads never share a clamp with a force lead or run bundled along one (BSW:225-231,
   WT:732).
4. Put the meter pull-ups and filters at the jack end, so the link probe sees every wire to the MCU
   (BSW:179-183).
5. Run the OLED supply and return straight to NUCLEO pins, not a shared ground rail. Unplug its VCC in
   battery mode (FM:307, BSW:96).
6. Never connect NUCLEO USB and the battery supply together. Never connect USB-C and solar together. Feed
   the charger input from a floating adapter (BSW:316, PM:40-41, BSW:243-245).
7. Only 3.3 V goes to the QT parts. Tape the 5 V header pins (BSW:82, BSW:107-108).
8. Keep the battery-path span limits at 1 A from 4.1. Keep force leads short (pigtails <= 60 mm, solid
   links <= 50 mm, regulator supply and tie <= 100 mm).
9. PA10 input: the source's cold Voc must be <= about 10.2 V with the 3:1 divider. A higher source needs
   a new ratio (PM:284-293).
