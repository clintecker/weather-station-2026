# Chicago electronics bench — equipment list

Selected for the finished Stage-0 prototypes and the later low-power weather station. Reuse any equivalent equipment you already have. Prices below are planning allowances in USD, not live carts, stock guarantees or quotes; exclude tax and shipping. Manufacturer capabilities checked 8 October 2026.

## Core bench

| Qty | Item / my pick | Why it belongs here | Planning allowance |
|---:|---|---|---:|
| 1 | **Fluke 87V multimeter** | Continuity, rail voltage, current, resistor checks; durable general-purpose meter | $500–650 |
| 1 | **Siglent SPD3303X-E programmable supply** | Current-limited first power, two adjustable 0–32 V / 0–3.2 A channels for later supply experiments | $350–500 |
| 1 | **Hakko FX-888DX soldering station, US 120 V** | Header soldering, wire repairs and prototype rework | $125–180 |
| 1 | **Weller Zero Smog Shield Pro** | Local fume capture while soldering; replace filters on schedule | $250–450 |
| 1 set | Grounded ESD mat, common-point ground and resistor-equipped wrist strap | Static-controlled assembly area | $60–120 |
| 1 | LED magnifying lamp or 5–10x inspection loupe | Spot bridges, cracked joints and connector orientation | $50–150 |
| 1 | Small PCB vise / board holder | Secure board while soldering and probing | $40–80 |
| 1 set | Flush cutters, 20–30 AWG wire stripper, fine tweezers, small pliers, precision drivers | Wiring and mechanical assembly | $80–150 |
| 1 set | Insulated mini-grabber leads, silicone banana leads, needle probes and spare meter fuses | Make stable measurements without slipping across adjacent pins | $50–100 |
| 1 set | Electronics solder, compatible flux pen, solder wick, tip cleaner, IPA and lint-free swabs | Ten header joints plus rework/cleanup | $50–100 |
| 1 set | Micro-B USB data cables, short jumper leads, 22–26 AWG wire, heat-shrink and labels | Programming, sensor hookup and identifiable harnesses | $30–60 |
| 1 | Digital caliper, 150 mm | Check printed fit, holes, PCB dimensions and screw lengths | $30–80 |
| 1 kit | M2/M3 screws, nuts, nylon spacers/washers, rubber feet and small parts organizer | Mount prototypes and keep hardware identifiable | $20–40 |

Core allowance: **$1,735–2,760**, before scope/logic analyzer, tax and shipping. This is a comfortable durable bench, not the minimum possible spend. The Fluke can be replaced by an existing reputable fused DMM with DC voltage/current, continuity and resistance; you do not need a new meter solely for this project. USB power is enough for the first Nucleo run, so the supply can wait if you want to spread purchases out.

The Hakko US page displayed $121.47 at review; confirm the actual bundle/handpiece in the cart. Select a roughly 1.6–2.4 mm chisel tip compatible with the shipped handpiece. The standard FX-8801 uses T18 tips; the optional FX-8806 uses a different tip family. Do not buy a tip assortment solely on the station name.

If the boards arrive fully assembled, the meter, inspection light, leads and computer are the immediate requirements. The soldering setup is for fixes and future boards, not a prerequisite to opening the package.

## Debugging additions I would choose

| Priority | Item | Use and limits | Budget |
|---|---|---|---:|
| First upgrade | **Rigol DHO804 oscilloscope** | Four analog channels, 70 MHz, 12-bit acquisition; see 3.3 V dips, I2C edges, reset timing and switching noise. Supplied probes are listed by Rigol. It does not measure the 915 MHz radio carrier. | Manufacturer page lists **$459**; verify cart |
| Optional convenience | **Saleae Logic 8** | Long I2C/SPI/UART captures with decoded transactions. Logic 2 offers an Apple Silicon build for your Mac. Buy if you want the smoother protocol-debugging workflow; unnecessary to duplicate a working analyzer. | Obtain current quote; reserve roughly $500–1,000 |
| Before low-power tuning | **Nordic Power Profiler Kit II (nRF-PPK2)** | Measure 3.3 V MCU/sensor sleep current and radio bursts. Only for a correctly isolated low-voltage rail. | Allow $100–160; confirm distributor price |

Scope + supply + multimeter answer different questions: the supply limits delivered power, the meter measures steady values, and the scope reveals short disturbances. The logic analyzer turns wire transitions into protocol transactions. A supply's front-panel current reading is not a sleep-current profiler.

The PPK2 accepts a DUT rail of 0.8–5.0 V and up to 1 A within its specifications. **Do not connect it directly to the planned 4S battery pack, which can reach 16.8 V.** Measure a downstream 3.3 V rail and account for USB/debugger bypass paths. These measurements are useful but do not by themselves establish energy drawn from the pack.

## Add at the relevant later stage

| Stage | Equipment | Decision |
|---|---|---|
| 1 — pack/solar | Programmable DC electronic load, e.g. **B&K Precision 8500B** | 150 V / 30 A / 300 W model listed by manufacturer; $1,405 on its page at review. Rent/borrow if only a few tests. Verify accuracy at our very low core current; a high full-scale rating does not guarantee low-current accuracy. |
| 1 — pack/solar | Calibrated reference meter/current shunt or suitable power analyzer | Needed to validate INA228 accounting against an independent reference. Select voltage/current range and calibration based on actual pack/load; do not use PPK2 on 4S. |
| 1 — cold testing | Environmental-chamber access to −35°C, logged pack temperatures and controlled load | Outsource or rent access. A household freezer does not establish the specified −35°C operating point or thermal uniformity. |
| 1/5 — temperature logging | Multichannel thermocouple/RTD logger and appropriate attached probes | Select after pack/thermal fixture layout. At least two pack regions plus ambient; additional channels for collector and drain later. |
| 2 — module bus | Isolated USB–RS-485 adapter, 10 m selected cable, current-limited fault fixture | Needed when the RJ45/Modbus port exists, not for current I2C bench board. |
| 3 — sensing | Traceable T/RH reference, rain-test scale/flow rig, appropriate wind/UV references | These verify measurement quality. A second cheap sensor is a comparison, not traceable calibration. |
| 5 — heating | Higher-power load/supply if required by measured heater demand; thermal camera optional | Choose after thermal-coupon power is known. Do not buy a heater-sized supply now. |

No separate SWD debugger is required for the Nucleo boards: ST-LINK is built in. Add a standalone ST-LINK and keyed SWD cable when the custom controller needs one. No hot-air station, reflow oven, RF spectrum analyzer, 3D printer or custom crimp tool is required for this first batch. Have the manufacturer assemble fine-pitch parts in later designs.

## Small details that matter

- Keep a clean sensor area away from solder flux and solvent fumes; do not wash or contaminate the SHT45 sensing aperture.
- Current measurements go in series. Return the lead to the voltage jack after measuring current.
- Ordinary scope ground clips share instrument ground. Connect them to circuit ground only, not to battery positive or a switching node; use a suitable differential probe for high-side measurements later. Never remove protective earth to float a scope.
- First sensor-only bench power is 3.3 V with a 20 mA limit and the Nucleo disconnected. Nucleo normal operation uses USB; do not add another supply to its 3.3 V rail at the same time.
- Label units TX-01 and RX-01, and record firmware revision, board revision, wiring and measurement setup with every test.

## Buying sources

Use manufacturers' US stores or their listed authorized distributors. DigiKey and Mouser are good starting points for parts and instruments; compare instrument bundles and calibration options with the manufacturer's dealer list. For small hardware, buy locally or from an industrial supplier. Avoid spending on an industrial electrical-service bundle when a standalone meter and miniature electronics probes meet the task.

- Fluke 87V: https://www.fluke.com/en-us/product/electrical-testing/digital-multimeters/fluke-87v
- Siglent supply: https://siglentna.com/product/spd3303x-e/
- Hakko US station: https://hakkousa.com/diy-hobbyiest/sub-hobbyiest/hobbyist/fx-888dx.html
- Weller extractor: https://www.weller-tools.com/us/en/filtration/products/solder-fumes/zero-smog-shield-pro
- Rigol scope: https://www.rigolna.com/products/rigol-digital-oscilloscopes/dho800/
- Saleae analyzer: https://www.saleae.com/products/logic-8
- Saleae Apple Silicon software: https://www.saleae.com/downloads
- Nordic PPK2 limits: https://docs.nordicsemi.com/r/bundle/ug_ppk2/page/ug/ppk/ppk_power_supply_specs.html
- Nordic PPK2 guide: https://docs.nordicsemi.com/r/bundle/ug_ppk2/page/ug/ppk/ppk_user_guide_intro.html
- B&K load: https://www.bkprecision.com/products/electronic-loads/8500B
