# I2C bench tool

A first check of the I2C2 bus on the NUCLEO-WL55JC1, for board B of the bench breadboard
(`hardware/bench-breadboard-r0`). It answers: are the bus lines pulled up, which parts answer, and do
the INA228 and the MAX17048 read what the meter reads? Not the weather-station firmware and not H01
evidence.

On I2C the tool **only reads**: it writes no register of any I2C part, so the node firmware finds
every part as it left it. It writes only to the OLED, on its own SPI bus. It does not use the radio.

## What it prints

At start, after a `#oled` line with the display's SPI clock (see "The OLED" below), and again
whenever a scan finds nothing:

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
| `vbus` | the voltage at the INA228's VBUS input: the cell voltage when the VBUS jumper on the breakout's back joins it to VIN+ (check it; the build sheet's INA228 row). Near 0 V means the jumper is open and nothing feeds VBUS; the current is still right |
| `shunt`, `i` | the voltage across the 0.015 ohm shunt, and the current from it. **Positive: out of the battery. Negative: into it (charging).** The shunt is in the cell's + lead: VIN+ to the cell, VIN- to the charger's LIPO pin |
| `die` | the INA228's own temperature |
| `vcell` | the cell voltage as the gauge measures it on its pigtail (GBAT) |
| `soc` | the gauge's state-of-charge estimate. Right after the gauge powers up it is a first guess; it settles over the first hours |
| `rate` | the gauge's charge or discharge rate in % an hour |

In its hibernate mode the gauge measures every 45 s, so `vcell` can stay the same for a while.

## Build and flash

```sh
cd firmware/i2cscan
make flash SERIAL=003B00194142500E20353451
```

Flashing writes only the application region. The node's key and journal (pages 55 to 127) survive.
To go back to the node firmware afterwards, flash it as in
[`../stage0-node/README.md`](../stage0-node/README.md), "Build and flash".

## Watch the console

```sh
ls /dev/cu.usbmodem*                                     # the NUCLEO's ST-LINK serial port
.venv/bin/python -m serial.tools.miniterm /dev/cu.usbmodemXXXX 115200
```

Press the black RESET button (B4) to see the start lines again. Ctrl-] quits miniterm.

## Before connecting

- Mode A: the NUCLEO on USB, the BATTERY POWER link on board B **open**. Never the NUCLEO's USB and
  the battery supply together.
- The STEMMA QT hub takes **3.3 V from CN6.4** and GND from CN6.6, never the 5 V pin. SDA to PA11
  (D14, CN5.9), SCL to PA12 (D15, CN5.10) ([`docs/hardware/bench-station-wiring.md`](../../docs/hardware/bench-station-wiring.md)).

## Checks against the meter

| Tool line | Meter |
|---|---|
| `#ina228 ... i=` | the current in series where W26 was: about +37.6 mA with the 100 ohm load and no solar |
| `#ina228 vbus=` and `#gauge vcell=` | the cell voltage at B:f39 (+) to B:f40 (-); the three agree within a few mV |

## When it goes wrong

| Line | Likely cause |
|---|---|
| `#lines SDA=LOW SCL=LOW: no pull-ups` | the hub has no 3.3 V or GND, or the cable to the NUCLEO is out |
| `#lines ... one line low` | SDA and SCL swapped or one open, or a part holding SDA low (unplug parts one at a time) |
| `#scan` shows 0x40 but not 0x36 | the gauge's STEMMA QT cable, or its pigtail: the gauge runs from the cell, not from the hub |
| `#ina228 0x40 is not an INA228` | another part at 0x40, or the INA228's address jumpers changed |
| `i=` the wrong sign | VIN+ and VIN- swapped on the breadboard (W16, W18) |
| `i=` near zero with a load fitted | the cell is not in the shunt's path: is it on the pigtail at B:f39/f40 and not the charger's own JST socket? |

## The OLED

The same readings appear on the bench OLED, redrawn once a second: Adafruit #2674, 2.7" 128 x 64,
SSD1325 controller, on **SPI1** (not I2C, so it is not in the scan).

```
I2C 36 40
+37.60mA                (twice the size)
VBUS 3.8459V
CELL 3.8460V 78.4%
RATE -0.62%/h
```

**Interface:** the module must be in SPI mode: on its back, **R19 and R21 fitted, R18 and R20 empty**
(Adafruit's guide; the module may ship in 8-bit mode with R18 and R20 fitted).

| OLED pin | Signal | NUCLEO | Arduino name, MCU pin |
|---|---|---|---|
| 1 | GND | GND rail | |
| 2 | 3.3 V in (100-150 mA) | 3V3 rail (board A L+) | |
| 4 | DC | CN5.1 | D8, PC2 |
| 7 | SCLK | CN5.6 | D13, PA5 (SPI1_SCK) |
| 8 | DIN | CN5.4 | D11, PA7 (SPI1_MOSI) |
| 15 | CS | CN5.3 | D10, PA4 |
| 16 | RST | CN9.8 | D7, PC1 |
| 3, 5, 6, 9-14, 17-19 | not used | leave empty | |
| 20 | frame ground (the metal case) | GND, or leave open | |

The pins are from UM2592 Rev 4, Table 17. D9 (PA9) is not used for reset: the protoboard switches
the sensors' 3.3 V with it. Put the kit's 220 uF capacitor across the OLED's 3.3 V and GND (+ to
3.3 V). The display draws 50-150 mA from the NUCLEO's 3V3.

The SPI clock is the fastest step at or below 1 MHz (Adafruit: the SSD1325 needs 1 MHz or less); the
start line prints it. The set-up commands are Adafruit's for this module (Adafruit_SSD1325_Library).
SPI is write only, so the tool cannot tell whether a display is there: if the screen stays dark,
check the 3.3 V at pin 2, the five signal wires, and R19/R21. `#oled SPI timeout` means SPI1 itself
stalled, not the display.
