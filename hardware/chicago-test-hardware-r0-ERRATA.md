# Errata: chicago-test-hardware-r0

`hardware/chicago-test-hardware-r0/SHA256SUMS.txt` locks the package `hardware/chicago-test-hardware-r0/` (66 of 66 files verified on 2026-10-13). The package is not edited, with one exception: commit a6d7a9e (2026-10-14) changed `source/render_prototype.py` so that it runs from this repository. `shasum -a 256 -c SHA256SUMS.txt` therefore reports that one file as FAILED and the other 65 as OK. These corrections apply on top of the package.

| Where in the package | Says | Correct | Evidence |
|---|---|---|---|
| `docs/build-and-order.md`:8 and :100 (also `index.html` and `technical-guide.html`) | Adafruit SHT45 breakout, product **5665** | The part of record is Adafruit **6174**. It is the same SHT45 breakout with a PTFE membrane. It is electrically interchangeable, and it is the part that arrived on 2026-10-13 | `firmware/README.md` (Hardware target), `docs/protocol-stack.md` §3.1, `.pcba-workflow/circuit-review.md` finding F1 |
| `docs/bench-equipment.md`:23 (also `technical-guide.html`) | Core allowance **$1,735–2,760** | **$1,635–2,660**: the sum of the 13 core-bench rows in the same table and in `docs/bench-equipment.csv` | Low: 500+350+125+250+60+50+40+80+50+50+30+30+20 = 1,635. High: 650+500+180+450+120+150+80+150+100+100+60+80+40 = 2,660 |
| `docs/bench-equipment.md`:39 and :46, `docs/bench-equipment.csv`:22 (also `technical-guide.html`) | The planned pack is **4S** and "can reach 16.8 V"; "do not use PPK2 on 4S" | The pack is **1S3P Li-ion**: three 2,200 mAh cells in parallel, 6,600 mAh, 3.0-4.2 V (3.7 V nominal), at most **4.2 V**. That is inside the PPK2's 0.8-5.0 V DUT range, but the PPK2's 1 A limit is below the 1 A charge plus the load, and a PPK2 in series would add resistance to the battery path (its + span at most 75 mΩ, build-sheet power check 7); so measure the downstream 3.3 V rail with it, as the row says, and the pack with the calibrated reference of the next row. Every other 4S assumption (pack voltage, the 16.8 V figure) is replaced by the 1S3P values | Clint's decision of 2026-10-29: `docs/superpowers/specs/2026-10-29-power-telemetry-design.md` section 1; build sheet `hardware/bench-breadboard-r0/build-sheet.md` (CELL row, power check 7) |
| `docs/bench-equipment.md`:46, `docs/bench-equipment.csv`:22 (row "1 — pack/solar") | A calibrated reference to validate **INA228 accounting** (one monitor, the pack) | The reference now validates **four INA228 rails**: battery (signed, + into the cell), solar input, USB-C input and load, one INA228 each at distinct addresses (0x40, 0x45, 0x48, 0x41), plus the bq24074 ISET and charger-input readings in phase A. Its range: 0-4.2 V on the battery, up to the panel's cold Voc (at most about 10.2 V) on solar, 5 V on USB-C; currents to about 1.5 A. A calibrated shunt or a DC clamp meter; a DMM in series only in a short steady window | spec sections 3, 9.2 and 12.2; `firmware/benchlink/README.md` "Acceptance drill" |

These items were checked and are correct (no erratum):

- the pin map against UM2592 Rev 4 Table 17 (CN6.4 3V3, CN6.6 GND, CN5.9 PA11 I2C2_SDA, CN5.10 PA12 I2C2_SCL)
- the 70.0 mm board width (UM2592 Figure 7)
- the netlist (5 nets)
- the drills (10 × 1.02 mm plated holes, 4 × 3.2 mm non-plated holes)
- the 42 × 27 mm mount pattern
- the design rule check: 0 violations, 0 unconnected pads, 0 footprint errors
- the fixture sizes against `validation/mechanical.json`
- the B&K 8500B rating of 150 V / 30 A / 300 W (manufacturer page, checked 2026-10-13).
