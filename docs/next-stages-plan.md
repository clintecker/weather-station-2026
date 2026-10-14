# Next stages: parts and plan

Written 2026-10-14, while the R0 PCBs and printed fixtures are in transit. **Nothing has been
ordered or quoted.** The authority is the v0.2 PRD/TRD (`weather-station-v0.2-prd-trd.html`,
§3 stage order, §7 component families). This document picks exact parts within those families.

**Price key:**
- **live** = read on the maker's or store's own page on 2026-10-14;
- **snapshot** = a search-engine copy of a distributor page;
- **not verified** = no price found (DigiKey, Mouser and TI blocked automated checks).

Re-check everything that isn't live before ordering.

## 1. Where we are

| Stage | Gate | State |
|---|---|---|
| 0 Data path | H01 (24 h, ≥ 1,426 of 1,440 within 120 s, restart/outage matrix) | SHT45 reading on the bench (2026-10-14). Next: protocol draft 5 (`protocol-draft5-design.md`), then H01 on that release |
| 1 Main power and pack state | H02 (pack Ah/Wh within 5 %), H03 (168 h at −35 °C, cold-charge inhibit, dawn recovery, 7-day deficit back in ≤ 3 solar days) | Parts planned below. Building waits for H01 |
| 2 One wired module | H04 (RJ45 port: power, faults, 10 m, 10⁶ transactions) | Long-lead parts identified |
| 3 Complete unheated sensing | H05, H06, H07, H11 | Instruments identified |

The PRD allows planning and sourcing Stage 1 now ("plan and source the stage-1 pack and chamber
access"). Building Stage 1 waits for H01.

## 2. Order early (long lead or scarce)

| Item | Why early | Stage |
|---|---|---|
| **Main pack quote** (custom 4S4P Molicel M35A, BMS, NTC leads) | Custom build, ships as Class 9 dangerous goods (about 200 Wh, over the 100 Wh limit), ground only | 1 |
| **−35 °C chamber booking** (7+ days, energized lithium pack) | Few places accept it; booking lead time | 1 |
| **STM32C0116-DK** (adapter MCU dev kit) | One distributor snapshot showed a 99-week lead; buy whatever stock appears | 2 |
| **Sealed RJ45 pair** (Amphenol RJF544: receptacle RJF54421 + plug RJF5446) | 16-week lead (snapshot) | 2 |
| **sglux ERYCA UV photodiode quote** (Boston Electronics) | Quote only; it's the one true-UV-index chip for a DIY head (H07) | 3 |
| BQ25798EVM, TPS62933EVM, TPS26624-25EVM | TI EVMs showed 0 stock / 12-week leads in snapshots | 1, 2 |

## 3. Stage 1 bill of materials

| Item | Part | Price | Notes |
|---|---|---|---|
| Charger evaluation | **TI BQ25798EVM** | ~$149–179 (not verified) | 1–4S, VBUS 3.6–24 V operating / 30 V absolute maximum, 5 A charge, MPPT, 16-bit ADC. **Ships set for 2S: move the jumper to 4S (JP28 or JP29) before connecting the pack.** Configure it over I2C from the Nucleo (TI's BQ Studio is Windows-only) |
| Pack monitor | **SparkFun SEN-31438** INA228 Qwiic (or Adafruit 5832) | $14.95 live | The INA228's ENERGY register is unsigned, so net Wh must be integrated in firmware from signed current × voltage |
| Kelvin shunt | Vishay WSK2512R0100BEA (10 mΩ, 0.1 %, 4-terminal) | not verified | Full scale 4.1 A / 16.4 A. Offset error ≈ 0.1 mA, about 0.6 % at the ≈ 17 mA core load (0.25 W ÷ 14.4 V) |
| Main pack | Custom **4S4P Molicel INR18650-M35A**, ≈ 14.4 V, 14 Ah, ≈ 200 Wh, balancing BMS, fuse, XT60 lead | quote | Cells charge 0–60 °C and discharge −40–60 °C (reseller datasheet copies; get the official revision from the vendor). US candidates: AA Portable Power (CA), Epec (MA), Voltaplex (SC), Inventus Power (Woodridge IL, MOQ likely too high) |
| Pack temperature probes | 2× Semitec **103AT-11** (10 k, B3435) | ≈ $3 each (snapshot) | One goes to the BQ25798 TS pin (hardware charge inhibit), one to an STM32 ADC (firmware inhibit, second opinion). Ask the pack vendor to fit both |
| Enclosure T/RH | **Adafruit 4885** SHT40 | $5.95 live | PRD's enclosure sensor |
| Pack → Nucleo supply | **TI TPS62933EVM** (5 V out) into the Nucleo's 5 V input | ≈ $59, out of stock (snapshot) | The Nucleo's own regulator, LEDs and ST-LINK spoil the idle-current figure. Stage-1 current numbers are for the dev board, not the final node |
| Fuse | Littelfuse FHAC0001ZXJ inline ATO holder + 7.5 A ATO; ≈ 3 A fuse on the solar input | not verified | At pack +, before everything |
| Pack connector | XT60 pair (SparkFun PRT-10474) | $2.50 live | Keyed; Anderson Powerpole can be assembled reversed |
| Solar (after the battery work passes) | **2× Voltaic P110** (10 W, 6 V) **in series** | $65 each, live | See §5: ordinary "12 V" panels are not compatible |
| Wiring | 16 AWG silicone, Qwiic cables, lugs | — | Kelvin sense leads separate from the current path |

**Must-have hardware ≈ $420–450**, plus the pack quote.

### Bench equipment for H02/H03

| Item | Part | Price | Buy / rent |
|---|---|---|---|
| Reference for Ah/Wh accounting | Siglent SDM3065X 6½-digit DMM with cal certificate + calibrated Riedon RSN-5-100 shunt | $857 live + shunt (not verified) | Needed: H02 requires an independent calibrated reference. Do not use a PPK2 or Joulescope on a 16.8 V pack (15 V limit) |
| Programmable load | Siglent SDL1020X-E ($574 live) or B&K 8500B ($1,405) | — | Borrow or rent if possible. The ≈ 17 mA core load can be resistors switched by the Nucleo |
| −35 °C chamber | Rent an Espec SU-242 (Transcat) or TestEquity 107; or use a lab such as Gaynes Labs (Bridgeview IL) | quote | −35 °C is near the SU-242's −40 °C floor for a 168 h hold. Confirm that energized lithium packs are allowed |
| Temperature logger | Pico USB TC-08 + type-T probes | $479 (listing) | Should-have; can wait |

## 4. Stages 2 and 3: chosen parts

| Function | Pick | Price | Meets PRD target? |
|---|---|---|---|
| Adapter MCU dev kit | STM32C0116-DK (fallback NUCLEO-C031C6) | ≈ $12–14 (snapshot) | — |
| RS-485 | TI RS485-HF-DPLX-EVM (supplied without a chip) + THVD2410DR | not verified / ≈ $3 | ±70 V bus fault, < 1 µA shutdown |
| Port eFuse | TPS26624-25EVM | ≈ €100 (snapshot) | Needs resistor changes for the 10–18 V window and 100 mA limit. 340 µA per powered port counts against the 0.25 W budget |
| Bench RS-485 adapter | Waveshare USB TO RS232/485 (B), SKU 26547 | $16.99 live | Isolated |
| Cable | Vertical Cable 069-559/CMX outdoor Cat6, solid copper, −40 °C | not verified | Use RJ45 plugs rated for solid wire |
| Rain | **Davis AeroCone 6466M** (0.2 mm per tip) | $160 live | Yes on paper (±3 % or ±1 tip). At 2 mm/h, test runs need ≥ 20 tips |
| Wind | **Davis 6410** | $240 live | **Speed: no below about 10 m/s** (±1 m/s vs ±0.5). Direction yes (±3°). See decision D1 |
| UV index | **Davis 6490** as the commercial fallback; sglux ERYCA for a DIY head (H07) | $425 live / quote | 6490 is borderline below about UVI 3; check it against a reference. LTR390 and GUVA-S12SD are UVA only, **not** UV index |
| Pressure | Adafruit 4816 BMP390 | $10.95 (out of stock at Adafruit) | — |
| Ambient T/RH | SHT45-AD1F (PTFE membrane) | — | **Already have it**: Adafruit 6174 carries exactly this part |
| 30-day storage (H11) | Winbond W25Q128JVSIM (16 MB, −40 °C); Adafruit 5643 breakout for the bench | $4.95 live (breakout) | Prefer the "IM" suffix: the "IQ" has quad mode permanently on and loses the hardware write-protect pin |
| Irradiance (optional) | Apogee SP-110-SS | $255 live | — |
| Precision reference (not a deliverable) | SparkFun SEN-15901 weather meter kit | $79.95 live | Cheap comparison only |

**Rough cost:** Stage 2 ≈ $250–650 (mostly connectors); Stage 3 core ≈ $850–1,000.

## 5. Findings that change designs

1. **Ordinary "12 V" solar panels are incompatible with the BQ25798 in a Chicago winter.** A
   36-cell panel's Voc of about 22 V rises to about 27 V at −35 °C. That is above the charger's
   24 V operating limit, and its over-voltage protection then blocks charging at exactly the cold
   dawn H03 tests. The Victron 36-cell panel reaches about 30 V, the absolute maximum. Rule:
   **Voc at standard test conditions (25 °C) ≤ about 18 V.** Two 6 V Voltaic panels in series
   give 13.9 V, rising to about 17.2 V when cold.
2. **No cold-charge margin from the charger alone.** The BQ25798 stops charging at 0 °C and
   resumes at 3 °C, which is exactly the cell's limit. Add a firmware inhibit at about +3–5 °C
   from the second probe, and require a BMS hardware cold-charge cutoff. An open or shorted
   probe must inhibit charging. Firmware never sets `TS_IGNORE`.
3. **After a crash or watchdog reset, the charger returns to its jumper defaults.** The 4S
   jumper must therefore be right in hardware: 16.8 V, 1 A.
4. **MPPT is off after power-on and can't be enabled below about 12 V on the pack.** Dawn
   recovery from a deeply discharged pack or a dead MCU therefore runs without MPPT, and H03
   must test exactly that.
5. **The INA228 energy register can't tell charge from discharge.** H02 accounting integrates
   signed power in firmware and keeps the INA228's signed CHARGE register as a cross-check.
6. **Powered sensors cost standby current:** Hall/optical anemometers about 3 mA, the Davis
   6490 2.4 mA, each eFuse 0.34 mA. Power them only while sampling (PRD §6), and measure the
   warm-up time.

## 6. Decisions for Clint

| # | Decision | Options |
|---|---|---|
| D1 | Wind accuracy | (a) Davis 6410 + own calibration against a reference; (b) RM Young 05103 (meets the target, four-figure price not verified); (c) revise the PRD target |
| D2 | Pack | Which vendor to approach, and the budget. The pack is the largest single item and needs Class 9 shipping |
| D3 | H02 reference | SDM3065X + calibrated shunt (≈ $1k) vs Qoitech Otii Ace Pro vs borrowing |
| D4 | Load | Buy the Siglent ($574) vs rent the B&K |
| D5 | Chamber | Rental (Transcat/TestEquity) vs a local lab (Gaynes) |
| D6 | Connectors | RJF544 composite (≈ $55–75 per pair) vs RJF TV metal (≈ $170–200 per pair) |
| D7 | Charge voltage | 16.8 V (full capacity) vs about 16.4 V (longer cell life) |

## 7. Open checks before ordering

- The official Molicel M35A datasheet revision. The copies disagree on maximum charge current
  (1.7 vs 3.4 A per cell); the 5 A charger limit is fine either way.
- BQ25798 datasheet inconsistencies: RT2 is printed as both 30.31 and 31.31 kΩ, and the ACOVP
  option table differs between two sections. Check them against the EVM schematic.
- The SparkFun INA228 onboard shunt is listed as both 10 and 15 mΩ. Measure it.
- The RJ45 plug's cable-diameter range against the 6.1 mm cable.
- Live price and stock for everything marked snapshot or not verified.
