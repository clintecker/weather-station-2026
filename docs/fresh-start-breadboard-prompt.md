# Fresh start: lay out the breadboarded weather station

Paste everything below the line into a new Claude Code session, started in
`/Users/clint/code/electronics/weather-station-2026`.

---

I'm building a solar-powered LoRa weather station. Right now I want **one thing**: the whole system
built out on breadboards, efficiently and cleanly, as a development bench I can build, debug and carry
around in one piece. Design it from scratch. **Don't take anything for granted**, and ignore any earlier
layouts, revisions, plans, "changes", or build sheets in this repo unless I point you at them. We kept
dragging old decisions along, and I want a clean rethink.

## Read this first

`docs/current-system.md` is a factual specification of what exists today:
- every part, with its role, interface, I²C address and supply;
- how the parts connect electrically (the power path, the four metered rails, the I²C buses, the OLED, the weather meter inputs, the charger signals, a full MCU pin map);
- how the TX firmware, the RX bridge, the radio protocol, WSMP, the gateway and the bench tools work.

It contains no breadboard layout: that is your job. Treat it as facts to design around, check anything it marks as unverified against the parts in hand, and tell me where you'd change something.

## What the system has to do

- **TX node** (a NUCLEO-WL55JC1): reads every sensor and every power rail, shows status on an OLED, and
  sends readings over LoRa.
- **RX bridge** (a second NUCLEO-WL55JC1): receives over LoRa and passes the data to my Mac over USB.
- **Power:** a 1S Li-ion pack, charged from a solar panel or a USB-C wall adapter (never both at once),
  through a charger. The rest of the system runs from the pack through a 3.3 V regulator. On the bench
  the TX NUCLEO can also be powered over its own USB.
- **Power measurement:** voltage and current on four rails (battery, load, solar, USB-C), plus a fuel
  gauge on the cell, plus the charger's own status signals.
- **Weather inputs:** temperature and humidity (×2), pressure, UV light, and a wind/rain meter kit
  (wind speed, wind direction, rain).

## The parts I have (the source of truth is `../INVENTORY.md`, so check it)

- **Boards:** 2 × ST NUCLEO-WL55JC1.
- **Power:**
  - Adafruit #353 1S3P 6600 mAh pack (JST PH), with an Adafruit #372 10 kΩ NTC
  - Adafruit #4755 bq24074 charger (USB-C and DC jack inputs; BATT and SYSOUT JST PH sockets)
  - Pololu S7V8F3 3.3 V regulator
  - 4 or more Adafruit #5832 INA228 (I²C, STEMMA QT, with a screw terminal for the measured current)
  - Adafruit #5580 MAX17048 fuel gauge
  - Voltaic P110 solar panel (2.1 mm barrel plug)
  - Adafruit #368 and #369 barrel-jack-to-screw-terminal adapters
  - Adafruit #4090 and #5978 USB-C female and male breakouts
  - a USB-C wall adapter
- **Sensors:**
  - Adafruit #5625 STEMMA QT 5-port hub
  - SHT45 #6174
  - SHTC3 #4636
  - BMP581 #6407
  - LTR390 #4831
  - SparkFun SEN-15901 weather meter kit (two RJ11 cables)
  - 2 × SparkFun BOB-14021 RJ11 breakouts
- **Display:** Adafruit #2674 2.7" 128 × 64 OLED (SSD1325, SPI).
- **Build materials:**
  - breadboards: BusBoard BB830 × 5 and full-size Elegoo × 3
  - 3 packs of BOJACK pre-cut jumpers (14 lengths, 2–125 mm: spans of 1–10, 20, 30, 40 and 50 holes)
  - 22 AWG solid hook-up wire
  - Dupont jumpers
  - WAGO 222-413 and 222-415 lever connectors
  - Adafruit #1131 JST PH cables
  - Adafruit #4209 STEMMA QT-to-header cables
  - a few STEMMA QT cables
  - resistor kits and capacitors
- **Tools:** a Fluke 87V and a soldering station. Soldering header pins onto breakouts is fine.

## What I want

- **Everything lives on a breadboard, or in its own home** on a 3D-printed base plate. The plate comes
  later and is designed around your layout, so for now just say what needs a home off the breadboards.
- **Group by function:** all the QT sensor parts together; all the charger, regulator and power-metering
  parts together. A clean, efficient layout with short, tidy, mostly orthogonal wiring from the pre-cut
  kit.
- **Compact:** about 300 × 400 mm or less is the target, but working room beats cramming.
- **Safe and measurable:** you decide, and explain, how the charge and battery currents (up to about
  1 A) should be wired. Where does breadboard contact resistance matter, and where does it not?
- **Reuse the existing firmware's pin choices** where that's sensible, because the firmware already
  works. The pin map is in `docs/current-system.md`, and the source is in `firmware/stage0-node/App/`
  (`board_inputs.h`, `power_config.h`, `i2c_bus.h`). You may propose changes, with reasons.
- **Ignore the existing breadboard model's layout** (`hardware/bench-breadboard-r0`: its holes, jumpers
  and board assignments). Use it only if I ask you to compare.

## How to work with me

- Ask me questions before designing. Go one step at a time, and get my approval before moving on.
- Brief and direct. Explain any command before running it, especially deletes. Don't commit or push
  until I ask.
- No Mermaid diagrams in chat (I can't render them). Use tables, lists, or images you generate.
- Never read or print anything under `run*/` directories. Never print my email, address or passwords.
- No RJ45 anywhere.
- Before choosing positions, get the real outlines and pinouts from the makers' datasheets and drawings
  (ST UM2592 for the NUCLEO; Adafruit's and SparkFun's product pages and PCB files).

## What to deliver, in order

1. Your questions for me.
2. A short functional block list: what connects to what, and which signals and power rails go where.
3. Two or three layout options as simple top-view sketches (generated images), with trade-offs. I pick
   one.
4. For the chosen layout: a hole-by-hole wiring plan, a jumper cut list from the BOJACK kit, a parts
   placement list, and a clean top-view render. Then, separately, a render as it would physically sit
   (true outlines, both NUCLEOs, the pack, the cables).
5. A list of what needs a home off the breadboards, for the base plate later.
