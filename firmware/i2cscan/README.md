# I2C bench tool

This is a first check of the I2C2 bus on the NUCLEO-WL55JC1, for board B of the bench breadboard
(`hardware/bench-breadboard-r0`, and the r1 bench). It answers these questions:

- Are the bus lines pulled up?
- Which parts answer?
- Do the INA228 and the MAX17048 read what the meter reads?
- Do the weather sensors and the weather meter (cups, vane, rain) read at all?

It isn't the weather-station firmware, and its output isn't H01 evidence.

On the **power parts** the tool only reads. It writes no INA228 or MAX17048 register, so the node
firmware finds them as it left them. The **weather sensors** get only what a reading needs. These are
the node's own values (`stage0-node/App/mod_th.c`, `mod_reg.c`):

- the SHT45 measure command 0xFD
- the SHTC3 wake 0x3517 and measure 0x7866
- the BMP581 OSR_CONFIG 0x36 = 0x40 and forced mode ODR_CONFIG 0x37 = 0x82
- the LTR390 MAIN_CTRL 0x00 = 0x0A (UVS mode)

The node sets them again when it starts. The tool also writes to the OLED, on its own SPI bus. It
doesn't use the radio.

## What it prints

At start the tool prints a `#power PA9 (D9) high` line and a `#oled` line with the display's SPI
clock. PA9 is the sensor power enable, and it isn't wired on the bench (see "The OLED" below). Then
it prints this line. It prints it again whenever a scan finds nothing:

```
#lines SDA=high SCL=high: pull-ups present
```

Then a scan, repeated every 10 s, one line for each address that answers:

```
#scan 0x36 MAX17048 gauge
#scan 0x40 INA228 battery monitor
#scan 2 found
```

Then once a second (the INA228 line averages four samples):

```
#ina228 vbus=3.8459 V shunt=+0.564 mV i=+37.60 mA (battery discharging) die=24.1 C
#gauge vcell=3.8460 V soc=78.4 % rate=-0.62 %/h
```

| Field | Meaning |
|---|---|
| `vbus` | the voltage at the INA228's VBUS input, which the official wiring runs on its own sense lead (L_VBUS, from screw terminal X1.2) to the **OUT** lever connector (WAGO_SYS_OUT, the load rail; build-progression record P5), **not the cell**. The back solder jumper from VBUS to VIN+ (SJ1) is open. During a charge OUT sits above the cell (4.3-4.5 V while the cell is below 4.1 V); on battery alone it sits a little below it. Near 0 V means nothing feeds VBUS (the sense lead is out); the current is still right |
| `shunt`, `i` | the voltage across the 0.015 ohm shunt, and the current from it, in the part's own sign. **Positive: out of the battery. Negative: into it (charging).** The shunt is in the pack's + lead: VIN+ to the CELL+ lever connector (lead L_CELL_INA), VIN- to the BATT lever connector (lead L_INA_BATT) and on to the charger's BATT socket. The node and the benchlink logger turn the sign so that + is into the cell (spec section 3.1) |
| `die` | the INA228's own temperature |
| `vcell` | the voltage of the **CELL+ node** (upstream of the shunt) as the gauge measures it on its own lead (L_GAUGE_POS, the red lead of a cut #1131 in its CELL+ position; its minus lead is unconnected and its ground comes over STEMMA QT; record P4, M4). At rest it is the battery voltage; under current it includes the pack-lead drop, I x R_pack |
| `soc` | the gauge's state-of-charge estimate. Right after the gauge powers up it is a first guess; it settles over the first hours |
| `rate` | the gauge's charge or discharge rate in % an hour |

In its hibernate mode the gauge measures every 45 s, so `vcell` can stay the same for a while.

**Phase B rail monitors.** After each scan (every 10 s, and once at start) the tool reads each phase B
INA228 that answers. It uses the node's addresses (`stage0-node/App/power_config.h` `POWER_ADDR_*`,
[`power-metering.md`](../../docs/hardware/power-metering.md) section 7). You get one line for each
monitor, from a single sample (not averaged). Phase A has none of them, so it prints nothing:

```
#scan 0x41 INA228 load monitor (phase B)
#rail load 0x41 vbus=4.4012 V shunt=+1.020 mV i=+68.00 mA die=25.3 C
#rail solar 0x45 vbus=6.1020 V shunt=+6.000 mV i=+400.00 mA die=26.0 C
```

| Rail | Address, strap | `i` positive | `vbus` |
|---|---|---|---|
| `load` | 0x41: A0 to VS | from OUT to the load | the LOAD joint (the load side of the shunt, on its own lead), not OUT |
| `solar` | 0x45: A0 and A1 to VS | from the panel into the station | the panel's lead, before D4 |
| `usb-c` | 0x48: A1 to **SDA** (a rework) | from the USB-C source into the station | the USB-C VBUS, before D2 |

`#rail ... is not an INA228` means another part answers at that address. If a rail INA228 is
missing from the scan but a `?` shows at another address, its strap is wrong. For example,
0x48 seen as 0x40 or 0x44 means the A1-to-SDA wire is open or on the wrong pad. The node uses the
same sign for each rail as printed here (power spec section 3.1). It turns only the battery rail.

**Weather sensors and meter.** Once a second, after the power lines, you get these two lines. The tool
triggers each sensor once at start and then the second before each line. So the first line after a
start already shows readings. A `-` marks a sensor that didn't answer or failed its CRC.

```
#meters cups=72 hz=2 wind=1.33 m/s (3 s) vane=1486 mV NE rain=2 tips 0.56 mm
#air sht45 23.10 C 50.80 % | shtc3 22.92 C 52.15 % | bmp581 983.0 hPa | ltr390 uv=0 counts
```

| Field | Meaning |
|---|---|
| `cups`, `hz` | cup pulses since start (LPTIM1 on PB5, 16 bits, wraps) and in the last second: one a turn |
| `wind` | the pulses of the last 3 s × 0.66698 m/s per Hz (the node's factor) ÷ 3 |
| `vane` | PB2 in ratio mV and its compass point from the node's table (`mod_wind.c`); `OPEN` above 3200 mV (no vane, cable or jack open), `?` between points |
| `rain` | tips since start (EXTI4 on PB4, 100 ms lockout as `mod_rain.c`) × 0.2794 mm |
| `sht45`, `shtc3` | temperature and humidity, both CRCs checked; `-` if no answer or a CRC failed |
| `bmp581` | station pressure in hPa (not reduced to sea level) |
| `ltr390` | raw UVS counts (18 bits, 100 ms, gain 3); 0 indoors is normal |

## Build and flash

```sh
cd firmware/i2cscan
make flash SERIAL=003B00194142500E20353451
```

The flash writes only the application region. The node's key and journal (pages 95 to 127) survive.
To go back to the node firmware afterwards, flash it as in
[`../stage0-node/README.md`](../stage0-node/README.md), "Build and flash".

## Watch the console

```sh
ls /dev/cu.usbmodem*                                     # the NUCLEO's ST-LINK serial port
.venv/bin/python -m serial.tools.miniterm /dev/cu.usbmodemXXXX 115200
```

Press the black RESET button (B4) to see the start lines again. Ctrl-] quits miniterm.

## Before connecting

- Mode A: the NUCLEO on USB, the BATTERY POWER link on board B **open**. Never use the NUCLEO's USB
  and the battery supply together.
- The STEMMA QT hub takes the **unswitched 3.3 V** from CN6.4 and GND from CN6.6, never the
  5 V pin.
- The power monitors take the same 3V3 on their own cable (QTM, bench-bb-r0.3, change C).
- The bench has no sensor load switch. Change C's PA9 switch isn't part of the breadboard build
  (build-progression record 4.6 dated note, 2026-11-02), so nothing connects to PA9.
- SDA goes to PA11 (D14, CN5.9) and SCL to PA12 (D15, CN5.10)
  ([`docs/hardware/bench-station-wiring.md`](../../docs/hardware/bench-station-wiring.md)).

## Checks against the meter

| Tool line | Meter |
|---|---|
| `#ina228 ... i=` | the Fluke 87V in series in the pack + lead at CELL+ position 1 (record M1; its mA input for the 38 mA load). Expect about OUT / 100 ohm with the 100 ohm load and no source (roughly 37-42 mA over a 3.7-4.2 V cell), positive (out of the battery). It should agree within 2 % + 2 mA of the meter (build-sheet power check 3: the shunt is verified, not measured). Its current shunt adds about 1.8 ohm on the mA input (1.8 mV/mA, about 68 mV at 38 mA) and about 30 mOhm on the A input, so put it in series only for a short steady reading (the span limits, build-sheet power check 7: the + span at most 75 mOhm) |
| `#rail <rail> ... i=` | the 87V the same way, in series in that rail's + lead, at a steady current: within 2 % + 2 mA (build-sheet power check B3) |
| `#gauge vcell=` | at rest or at the 38 mA load, the meter at the pack plug (back-probed): within 10 mV. At a 1 A charge, the meter across the gauge's own sense points (the CELL+ clamp to the STAR clamp): within 10 mV, the pack-plug difference recorded (build-sheet power check 8) |
| `#ina228 vbus=` | OUT, on the OUT lever connector (or the charger's OUT header pin, a zero-current test point). With a source charging the cell (below 4.1 V): 4.3-4.5 V and at least 100 mV above `vcell` (build-sheet power check 9). With no source: a little below `vcell` (the charger's battery FET) |

These readings catch the following wiring faults:

| Reading | Wiring fault |
|---|---|
| `vbus` equals `vcell` within a few mV **while charging** | the INA228's back VBUS-to-VIN+ jumper is closed (VBUS on the cell, and OUT tied to the cell, which bypasses the charger's 4.2 V regulation): cut it (build-sheet power check 1) |
| `vbus` near 3.3 V, near 0 V, or near the charger's input | the VBUS sense lead (L_VBUS) is on the wrong net (the 3.3 V rail, GND, or VBUS of the charger) or out: it goes to the OUT lever connector |
| `vcell` reads like `vbus` (4.3-4.5 V while charging) | the gauge senses OUT, not CELL+: its red lead (L_GAUGE_POS) goes in its own CELL+ position, upstream of the shunt |
| `vcell` differs from the meter across the CELL+ and STAR clamps by more than 10 mV at 1 A | the gauge's lead is not on CELL+, or its ground is not the one the record allows (ground over STEMMA QT only; record P4). A difference against the pack plug of up to I x R_pack + 10 mV is the pack-lead drop, not a fault (record M4) |

## When it goes wrong

| Line | Likely cause |
|---|---|
| `#lines SDA=LOW SCL=LOW: no pull-ups` | the hub has no 3.3 V or GND, or the cable to the NUCLEO is out |
| `#lines ... one line low` | SDA and SCL swapped or one open, or a part holding SDA low (unplug parts one at a time) |
| `#scan` shows 0x40 but not 0x36 | the gauge's STEMMA QT cable, or its CELL+ lead (L_GAUGE_POS): the gauge runs from the cell, not from the hub |
| `#ina228 0x40 is not an INA228` | another part at 0x40, or the INA228's address jumpers changed |
| `i=` the wrong sign | VIN+ and VIN- swapped at the INA228 screw terminal: L_CELL_INA (from the CELL+ connector) goes to VIN+ (X1.3), L_INA_BATT (to the BATT connector) to VIN- (X1.1) |
| `i=` near zero with a load fitted | the pack is not in the shunt's path: it is plugged straight into the charger's own BATT socket, which bypasses the shunt (the 2026-10-28/29 fault). The pack connects only through the shunt (build-progression record P3): pack plug, the pack-mating half of a cut #1131 (L_PACK_POS) to the CELL+ lever connector, L_CELL_INA to the INA228 shunt, L_INA_BATT to the BATT lever connector, and the board-mating half of the same #1131 (L_BATT_POS) into the charger's BATT socket; no breadboard contact in the path. The [build sheet](../../hardware/bench-breadboard-r0/build-sheet.md) has the leads (section 3), the joints (section 4) and the span limits (section 5, power check 7) |

## The OLED

The same readings appear on the bench OLED, redrawn once a second. It's an Adafruit #2674, 2.7"
128 x 64, with an SSD1325 controller. It sits on **SPI1** (not I2C), so it isn't in the scan. The r1
bench mounts the panel upside down (BB3, DS1 at 180°). So the tool draws the frame turned
180° (`oled_surf_on(frame, 1)`) and sends it as drawn.

Each I2C part's row says `NO <part>` when it didn't answer (`NO INA228`, `NO MAX17048`, `NO SHT45`,
`NO SHTC3`, `NO BMP581`). The LTR390 shows `UV NO`. The WIND and RAIN rows stay blank until the meter
inputs are up.

```
I2C 44 47 53 70
BATT +37.60mA 3.846V     (INA228 0x40: current, OUT)
CELL 3.846V 78.4%        (MAX17048)
AIR 23.10C 50.80%        (SHT45)
BOX 22.92C 52.15%        (SHTC3, the enclosure)
P 983.0hPa UV 0          (BMP581; LTR390 counts)
WIND 1.33m/s NE
RAIN 2 TIPS 0.56mm
```

The tool configures the display once, at start. If the display gets its 3.3 V later (you fit the
OLED link's jumper cap with the board running), press RESET.

**Interface:** the module must be in SPI mode. On its back, **R19 and R21 fitted, R18 and R20 empty**
(Adafruit's guide). The module may ship in 8-bit mode with R18 and R20 fitted.

| OLED pin | Signal | NUCLEO | MCU pin |
|---|---|---|---|
| 1 | GND | CN10.20, its own lead (L_OLED_GND) | GND |
| 2 | 3.3 V in (100-150 mA) | CN7.16, its own lead (L_OLED_VCC); unplugged in mode B | 3V3 |
| 4 | DC | CN10.21 | PC2 (alias D8, CN5.1, stays empty) |
| 7 | SCLK | CN10.11 | PA5, SPI1_SCK (alias D13, CN5.6, stays empty) |
| 8 | DIN | CN10.15 | PA7, SPI1_MOSI (alias D11, CN5.4, stays empty) |
| 15 | CS | CN10.17 | PA4 (alias D10, CN5.3, stays empty) |
| 16 | RST | CN10.23 | PC1 (alias D7, CN9.8, stays empty) |
| 3, 5, 6, 9-14, 17-19 | not used | leave empty | |
| 20 | frame ground (the metal case) | GND, or leave open | |

The pins come from UM2592 Rev 4, Tables 17 and 18. The hardware build sheet
(`hardware/bench-breadboard-r0/build-sheet.md`) lands each signal on its morpho pin only. It puts the
supply pair straight on the NUCLEO, never on a breadboard rail (build-progression record N1, N3).

D9 (PA9) isn't used for reset. It's the sensor power enable. Change C's switch isn't part of the
breadboard build (build-progression record 4.6 dated note, 2026-11-02), so on the bench nothing
connects to PA9. This tool still drives PA9 high at start and keeps it high. A `#power` line says so.
That's harmless on the bench.

Put the kit's 220 uF capacitor across the OLED's 3.3 V and GND (+ to 3.3 V). The display draws
50-150 mA from the NUCLEO's 3V3.

The SPI clock is the fastest step at or below 1 MHz (Adafruit: the SSD1325 needs 1 MHz or less). The
start line prints it. The set-up commands are Adafruit's for this module (Adafruit_SSD1325_Library).

**Mode B (battery only):** the regulator makes 3.3 V from the cell, and the OLED's 50-150 mA comes
from that same 3.3 V. So in mode B the INA228's current includes the display. For mode B battery
readings, unplug the OLED's 3.3 V wire (the build sheet's bench checks name it). Mode A, the daily
setup with the NUCLEO on USB, isn't affected.

SPI is write only, so the tool can't tell if a display is there. If the screen stays dark, check the
3.3 V at pin 2, the five signal wires, and R19/R21. `#oled SPI timeout` means SPI1 itself stalled,
not the display.
