# Next stages: parts and plan

Written 2026-10-14, while the first-revision (R0) test PCBs and printed fixtures are in transit.
**Nothing has been ordered or quoted.** The authority is the v0.2 product and technical
requirements (PRD/TRD, `weather-station-v0.2-prd-trd.html`): §3 gives the stage order, §7 the
component families. This document picks exact parts within those families.

**Price key:**
- **live** = read on the maker's or store's own page on 2026-10-14.
- **snapshot** = a search-engine copy of a distributor page.
- **not verified** = no price found (DigiKey, Mouser and TI blocked automated checks).

Check again every price that is not live before you order.

## 1. Where we are

The PRD orders the work in four stages. Each stage ends with acceptance tests (gates). The next
stage starts only after those tests pass.

```mermaid
flowchart LR
  S0["Stage 0: data path on the bench"] -- "H01 passes" --> S1["Stage 1: main power and pack state"]
  S1 -- "H02 and H03 pass" --> S2["Stage 2: one wired module"]
  S2 -- "H04 passes" --> S3["Stage 3: complete unheated sensing"]
  S3 -- "H05, H06, H07 and H11 pass" --> F["Stage 3 complete"]
```

| Stage | What it builds | Gate (PRD acceptance tests) | State |
|---|---|---|---|
| 0 | The data path: sensor node → LoRa → receiver → gateway → database, on the bench with USB power | H01, the 24-hour delivery test: ≥ 1,426 of 1,440 readings within 120 s, plus a restart and outage matrix | SHT45 reading on the bench (2026-10-14). Next: protocol version 5 (`protocol-design.md`), then H01 on that release |
| 1 | Main power and pack state: battery pack, charger, solar, pack monitoring | H02, pack energy accounting: pack Ah/Wh within 5 %. H03, cold and solar endurance: 168 h at −35 °C, cold-charge inhibit, dawn recovery, a 7-day deficit recovered in ≤ 3 solar days | Parts planned below. Building waits for H01 |
| 2 | One wired sensor module on a sealed RJ45 port | H04, the port test: power, faults, 10 m cable, 10⁶ transactions | Long-lead parts identified. Every module follows WSMP ([`module-protocol.md`](module-protocol.md)), which replaces the PRD §11 register map |
| 3 | The complete unheated sensor set | H05 (defined in PRD §12). H06, the rain acceptance test. H07, UV index sensor qualification. H11, 30-day on-device storage | Instruments identified |

The PRD allows planning and sourcing Stage 1 now ("plan and source the stage-1 pack and chamber
access"). Building Stage 1 waits for H01.

## 2. Order early (long lead or scarce)

| Item | Why early | Stage |
|---|---|---|
| **Main pack quote** (custom 4S4P Molicel M35A, battery management system (BMS), thermistor (NTC) leads) | Custom build. It ships as Class 9 dangerous goods (about 200 Wh, over the 100 Wh limit), by ground only | 1 |
| **−35 °C chamber booking** (7+ days, energized lithium pack) | Few places accept it; booking lead time | 1 |
| **STM32C0116-DK** (development kit for the module adapter's microcontroller) | One distributor snapshot showed a 99-week lead. Buy whatever stock appears | 2 |
| **Sealed RJ45 pair** (Amphenol RJF544: receptacle RJF54421 + plug RJF5446) | 16-week lead (snapshot) | 2 |
| **sglux ERYCA UV photodiode quote** (Boston Electronics) | Quote only. It is the one true-UV-index chip for a home-built sensor head (H07) | 3 |
| BQ25798EVM, TPS62933EVM, TPS26624-25EVM | These TI evaluation modules (EVMs) showed 0 stock or 12-week leads in snapshots | 1, 2 |

## 3. Stage 1 bill of materials

| Item | Part | Price | Notes |
|---|---|---|---|
| Charger evaluation | **TI BQ25798EVM** | ~$149–179 (not verified) | 1–4S, charger input (VBUS) 3.6–24 V operating / 30 V absolute maximum, 5 A charge, maximum power point tracking (MPPT), 16-bit ADC. **It ships set for 2S. Move the jumper to 4S (JP28 or JP29) before you connect the pack.** Configure it over I2C from the Nucleo board (TI's BQ Studio is Windows-only) |
| Pack monitor | **SparkFun SEN-31438** INA228 Qwiic (or Adafruit 5832) | $14.95 live | The INA228's ENERGY register is unsigned, so net Wh must be integrated in firmware from signed current × voltage |
| Kelvin shunt | Vishay WSK2512R0100BEA (10 mΩ, 0.1 %, 4-terminal) | not verified | Full scale 4.1 A / 16.4 A. Offset error ≈ 0.1 mA, about 0.6 % at the ≈ 17 mA core load (0.25 W ÷ 14.4 V) |
| Main pack | Custom **4S4P Molicel INR18650-M35A**, ≈ 14.4 V, 14 Ah, ≈ 200 Wh, balancing BMS, fuse, XT60 lead | quote | Cells charge at 0–60 °C and discharge at −40–60 °C (reseller datasheet copies. Get the official revision from the vendor). US candidates: AA Portable Power (CA), Epec (MA), Voltaplex (SC), Inventus Power (Woodridge IL, minimum order quantity likely too high) |
| Pack temperature probes | 2× Semitec **103AT-11** (10 k, B3435) | ≈ $3 each (snapshot) | One goes to the BQ25798 temperature-sense (TS) pin for the hardware charge inhibit. One goes to an STM32 ADC for the firmware inhibit, a second opinion. Ask the pack vendor to fit both |
| Enclosure T/RH | **Adafruit 4885** SHT40 | $5.95 live | PRD's enclosure sensor |
| Pack → Nucleo supply | **TI TPS62933EVM** (5 V out) into the Nucleo's 5 V input | ≈ $59, out of stock (snapshot) | The Nucleo's own regulator, LEDs and ST-LINK spoil the idle-current figure. Stage-1 current numbers are for the development board, not the final node |
| Fuse | Littelfuse FHAC0001ZXJ inline ATO holder + 7.5 A ATO; ≈ 3 A fuse on the solar input | not verified | At the pack's positive terminal, before everything |
| Pack connector | XT60 pair (SparkFun PRT-10474) | $2.50 live | Keyed. Anderson Powerpole connectors can be assembled reversed |
| Solar (after the battery work passes) | **2× Voltaic P110** (10 W, 6 V) **in series** | $65 each, live | See §5: ordinary "12 V" panels are not compatible |
| Wiring | 16 AWG silicone, Qwiic cables, lugs | — | Kelvin sense leads separate from the current path |

**Must-have hardware ≈ $420–450**, plus the pack quote.

### Bench equipment for H02 and H03

| Item | Part | Price | Buy / rent |
|---|---|---|---|
| Reference for Ah/Wh accounting | Siglent SDM3065X 6½-digit multimeter with calibration certificate + calibrated Riedon RSN-5-100 shunt | $857 live + shunt (not verified) | Needed: H02 requires an independent calibrated reference. Do not use a PPK2 or Joulescope on a 16.8 V pack (their limit is 15 V) |
| Programmable load | Siglent SDL1020X-E ($574 live) or B&K 8500B ($1,405) | — | Borrow or rent if possible. Resistors that the Nucleo switches can serve as the ≈ 17 mA core load |
| −35 °C chamber | Rent an Espec SU-242 (Transcat) or TestEquity 107; or use a lab such as Gaynes Labs (Bridgeview IL) | quote | −35 °C is near the SU-242's −40 °C floor for a 168 h hold. Confirm that the lab accepts energized lithium packs |
| Temperature logger | Pico USB TC-08 + type-T probes | $479 (listing) | Should-have. It can wait |

## 4. Stages 2 and 3: chosen parts

| Function | Pick | Price | Meets PRD target? |
|---|---|---|---|
| Module adapter microcontroller development kit | STM32C0116-DK (fallback NUCLEO-C031C6) | ≈ $12–14 (snapshot) | — |
| RS-485 | TI RS485-HF-DPLX-EVM (supplied without a chip) + THVD2410DR | not verified / ≈ $3 | ±70 V bus fault, < 1 µA shutdown |
| Port eFuse | TPS26624-25EVM | ≈ €100 (snapshot) | Needs resistor changes for the 10–18 V window and the 100 mA limit. Each powered port draws 340 µA, which counts against the 0.25 W budget |
| Bench RS-485 adapter | Waveshare USB TO RS232/485 (B), SKU 26547 | $16.99 live | Isolated |
| Cable | Vertical Cable 069-559/CMX outdoor Cat6, solid copper, −40 °C | not verified | Use RJ45 plugs rated for solid wire |
| Rain | **Davis AeroCone 6466M** (0.2 mm per tip) | $160 live | Yes on paper (±3 % or ±1 tip). At 2 mm/h, test runs need ≥ 20 tips |
| Wind | **Davis 6410** | $240 live | **Speed: no, below about 10 m/s** (±1 m/s against the ±0.5 m/s target). Direction: yes (±3°). See the wind accuracy decision in §6 |
| UV index | **Davis 6490** as the commercial fallback; sglux ERYCA for a DIY head (H07) | $425 live / quote | The 6490 is borderline below about UV index 3. Check it against a reference. The LTR390 and GUVA-S12SD measure UVA only, **not** UV index |
| Pressure | Adafruit 4816 BMP390 | $10.95 (out of stock at Adafruit) | — |
| Ambient T/RH | SHT45-AD1F (PTFE membrane) | — | **Already have it**: Adafruit 6174 carries exactly this part |
| 30-day storage (H11) | Winbond W25Q128JVSIM (16 MB, −40 °C); Adafruit 5643 breakout for the bench | $4.95 live (breakout) | Prefer the "IM" suffix. The "IQ" part has quad mode permanently on, so it loses the hardware write-protect pin |
| Irradiance (optional) | Apogee SP-110-SS | $255 live | — |
| Precision reference (not a deliverable) | SparkFun SEN-15901 weather meter kit | $79.95 live | Cheap comparison only |

**Rough cost:** Stage 2 ≈ $250–650 (mostly connectors). Stage 3 core ≈ $850–1,000.

## 5. Findings that change designs

1. **Ordinary "12 V" solar panels are incompatible with the BQ25798 in a Chicago winter.**
   - A 36-cell panel's open-circuit voltage (Voc) of about 22 V rises to about 27 V at −35 °C.
   - That is above the charger's 24 V operating limit. The charger's over-voltage protection then
     blocks charging at the cold dawn that H03 tests.
   - The Victron 36-cell panel reaches about 30 V, the absolute maximum.
   - Rule: **Voc at standard test conditions (25 °C) ≤ about 18 V.** Two 6 V Voltaic panels in
     series give 13.9 V, rising to about 17.2 V when cold.
2. **The charger alone gives no cold-charge margin.** The BQ25798 stops charging at 0 °C and
   resumes at 3 °C, which is exactly the cell's limit.
   - Add a firmware inhibit at about +3–5 °C from the second probe.
   - Require a BMS hardware cold-charge cutoff.
   - An open or shorted probe must inhibit charging. The firmware never sets `TS_IGNORE`.
3. **After a crash or watchdog reset, the charger returns to its jumper defaults.** The 4S
   jumper must therefore be right in hardware: 16.8 V, 1 A.
4. **MPPT is off after power-on. The firmware cannot enable it below about 12 V on the pack.**
   Dawn recovery from a deeply discharged pack or a dead MCU therefore runs without MPPT. H03
   must test exactly that case.
5. **The INA228 energy register cannot tell charge from discharge.** The H02 accounting
   integrates signed power in firmware. It keeps the INA228's signed CHARGE register as a
   cross-check.
6. **Powered sensors cost standby current:** Hall or optical anemometers about 3 mA, the Davis
   6490 2.4 mA, each eFuse 0.34 mA. Power them only while sampling (PRD §6). Measure the warm-up
   time.

## 6. Decisions for Clint

| Decision | Options |
|---|---|
| Wind accuracy | Davis 6410 + own calibration against a reference. Or RM Young 05103 (meets the target, four-figure price not verified). Or revise the PRD target |
| Pack | Which vendor to approach, and the budget. The pack is the largest single item and needs Class 9 shipping |
| H02 reference | SDM3065X + calibrated shunt (≈ $1k), or Qoitech Otii Ace Pro, or borrow one |
| Load | Buy the Siglent ($574), or rent the B&K |
| Chamber | Rental (Transcat/TestEquity), or a local lab (Gaynes) |
| Connectors | RJF544 composite (≈ $55–75 per pair), or RJF TV metal (≈ $170–200 per pair) |
| Charge voltage | 16.8 V (full capacity), or about 16.4 V (longer cell life) |

## 7. Open checks before ordering

- The official Molicel M35A datasheet revision. The copies disagree on the maximum charge current
  (1.7 or 3.4 A per cell). The 5 A charger limit is fine either way.
- BQ25798 datasheet inconsistencies. RT2 is printed as both 30.31 and 31.31 kΩ. The input
  over-voltage protection (ACOVP) option table differs between two sections. Check both against
  the EVM schematic.
- The SparkFun INA228 onboard shunt is listed as both 10 and 15 mΩ. Measure it.
- The RJ45 plug's cable-diameter range against the 6.1 mm cable.
- Live price and stock for everything marked snapshot or not verified.
