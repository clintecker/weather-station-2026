# Proof-of-concept shopping list

Off-the-shelf parts for building the critical modules now (2026-10-14). Prices and stock were read
on each store's own product page that day. **Nothing has been ordered.** The long-term PRD design
(4S pack, RS-485 modules, qualified instruments) is in [`next-stages-plan.md`](next-stages-plan.md).

Everything wires to the TX NUCLEO-WL55JC1: I2C2 through a STEMMA QT hub, plus a few GPIO and ADC pins.

## Power (one Li-ion cell, solar charged)

| Part | Product | Price | Stock | Notes |
|---|---|---:|---|---|
| Solar charger | Adafruit bq24074 #4755 | $14.95 | In stock | 5–10 V input (28 V protected), 1 A charge (0.5 or 1.5 A by jumper), power path |
| Charger thermistor | Adafruit 10K NTC #372 | $4.00 | In stock | **Needed:** none of the packs has one. Tape it to the pack for cold-charge inhibit |
| Solar panel | Voltaic P110 10 W 6 V (Voltaic direct, or Adafruit #5369) | $65.00 / $64.95 | In stock | Voc 6.94 V, about 8.7 V when cold, under the charger's 10 V limit. Adafruit's own 6 V panels are discontinued |
| Battery | Adafruit 3.7 V 6600 mAh #353 | $24.50 | In stock | About 24 Wh (normal shipping), protected, 69 × 54 × 18 mm |
| 3.3 V regulator | Pololu S7V8F3 #2122 | $9.95 | Active (backorders allowed) | Buck-boost, 2.7–11.8 V in, < 0.1 mA quiescent. Feeds the Nucleo's 3V3 pin (CN7.16) |
| Fuel gauge | Adafruit MAX17048 #5580 | $5.95 | In stock | I2C 0x36, about 3–23 µA |
| Power monitor | Adafruit INA228 #5832 | $14.95 | In stock | I2C 0x40, 15 mΩ shunt |

## Sensors

| Part | Product | Price | Stock | Notes |
|---|---|---:|---|---|
| Wind + rain | SparkFun Weather Meter Kit SEN-15901 | $79.95 | In stock | Cups (reed, 1.492 mph per Hz), vane (resistor network, 8 directions reliably), rain 0.2794 mm per tip |
| RJ11 breakouts | SparkFun BOB-14021 + 2× RJ11 jack PRT-00132 | $2.75 + 2 × $1.75 | In stock | One per meter cable |
| Pressure | Adafruit BMP581 #6407 | $9.95 | In stock | ±0.3 hPa absolute. Substitute for the out-of-stock BMP390 |
| UV | Adafruit LTR390 #4831 | $4.95 | In stock | **UVA only, not a UV index.** A stand-in until a real UV-index part is chosen (DFRobot SEN0636 claims a UV index; its stock isn't shown) |
| Enclosure T/RH | Adafruit SHTC3 #4636 | $6.95 | In stock | I2C 0x70. **Not the SHT40:** it shares address 0x44 with the outdoor SHT45 |
| Outdoor T/RH | Adafruit 6174 SHT45 (PTFE) | — | **Have** | Sensirion SHT45-AD1F |

## Storage and wiring

| Part | Product | Price | Stock |
|---|---|---:|---|
| 16 MB SPI flash | Adafruit W25Q128 #5643 | $4.95 | In stock |
| I2C hub | Adafruit 5-port STEMMA QT hub #5625 | $2.50 | In stock |
| STEMMA QT cables | Adafruit #4210 (100 mm), #4401 (200 mm) | $0.95, $1.25 | In stock |

## Housing

| Part | Product | Price | Stock |
|---|---|---:|---|
| Electronics box | Adafruit IP66 enclosure #905 (175 × 125 × 75 mm) | $19.95 | 35 in stock |
| Cable glands | Adafruit PG-7 #762, PG-9 #761 | $1.95 each | In stock |
| Radiation shield | **Printed:** `hardware/poc-enclosure-r1/` (or buy an Ambient Weather SRS100LX, $54.99) | — | — |
| Printed-part hardware | Rods, nuts, inserts, hose clamps, SMA bulkhead pigtail: see `hardware/poc-enclosure-r1/README.md` | — | — |

**Total for the electronics and sensors above:** about $305, before shipping, the printed parts and
their hardware.

## I2C addresses on I2C2

| Address | Device |
|---|---|
| 0x36 | MAX17048 |
| 0x40 | INA228 |
| 0x44 | SHT45 (outdoor) |
| 0x46 or 0x47 | BMP581 (check the jumper) |
| 0x53 | LTR390 |
| 0x70 | SHTC3 (enclosure) |

## Caveats

- **Cable glands:** the meter cables end in RJ11 plugs, which won't pass a PG-7 or PG-9 gland. Either
  cut and re-terminate them inside the box, or use a larger gland.
- **Battery cut-off:** the pack cuts off at about 3.0 V. The S7V8F3 runs down to 2.7 V, so the
  regulator isn't the limit.
- **Console on battery:** with the Nucleo powered through its 3V3 pin, the ST-LINK (USB console and
  programmer) is off. **Never connect USB and the 3.3 V supply at the same time.**
