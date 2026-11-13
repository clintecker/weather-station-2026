# Render models

Every part in the renders, where its model comes from, and why. `render/fetch_models.py` fetches and checks
(SHA-256) every file marked real or imported into `render/models/` (not committed); a missing or changed file
falls back to the checked boxes, and the render's legend says so.

Status: **real** = the maker's or KiCad's 3D model; **imported** = the bare board built from the maker's Eagle
board file with KiCad (`kicad-cli pcb import --format eagle`, then `pcb export step --board-only`: board, pads,
tracks and silkscreen, no part models); **drawn** = generated from the maker's drawing in `kicad_render.py`;
**stand-in** = the envelope boxes the layout checks use.

| Part | Model source | Status | Why |
|---|---|---|---|
| SolderFul SOLDERBREAD#02 cards | `kicad_render.py`: outline, holes, strips from the datasheet (`sources.py`), back rails snapped off | drawn | no maker model |
| Lying resistors, standing DO-35 (BAT85S) and DO-41 (1N4733A) diodes, 100 nF discs | KiCad 10 library (`Resistor_THT`, `Diode_THT`, `Capacitor_THT`) | real | |
| Breakout headers (0.1 in, vertical) | KiCad 10 library (`Connector_PinHeader_2.54mm`) | real | |
| Bus header and SWD header (Clint's generic 2.54 mm right-angle male, cut to 18) | `kicad_render.py` from the Sullins PRPC drawing as a stand-in for the generic part: tails, 90 degree bends, insulator, 5.8 mm mating pins [TBD-MEASURE] | drawn | the generic header has no drawing; KiCad's generic header has the wrong mating length |
| Backplane socket (generic 2.54 mm female strip, cut to 1x18) | boxes (drawn open in the section), sized from the Sullins PPPC drawing [TBD-MEASURE] | stand-in | as above |
| Adafruit SHTC3 #4636 | https://raw.githubusercontent.com/adafruit/Adafruit_CAD_Parts/main/4636%20SHTC3/4636%20SHTC3.step | real | |
| Adafruit MAX17048 #5580 | https://raw.githubusercontent.com/adafruit/Adafruit_CAD_Parts/main/5580%20MAX17048/5580%20MAX17048.step | real | |
| Adafruit INA228 #5832 | https://raw.githubusercontent.com/adafruit/Adafruit_CAD_Parts/main/5832%20INA228%20STEMMA%20QT/5832%20INA228%20STEMMA%20QT.step | real | shows its terminal block, which is not fitted |
| Adafruit PCA9548 #5626 (mux) | https://raw.githubusercontent.com/adafruit/Adafruit_CAD_Parts/main/5626%20PCA9548%20Stemma/5626%20PCA9548%20Stemma.step | real | in the cage renders |
| Pololu S7V8F3 | https://www.pololu.com/file/0J1374/pololu-step-up-step-down-voltage-regulator-s7v8fx.step | real | |
| SparkFun BOB-14021 board | https://raw.githubusercontent.com/sparkfun/RJ11_Breakout/master/hardware/RJ11-Breakout.brd (one board kept from the panel of two) | imported | SparkFun publishes no 3D model |
| Amphenol 87180-066LF RJ11 jack (the new BOBs) | boxes, 13.2 x 18 x 11.5 (RS 771-0215 listing) | stand-in | amphenol-cs.com refuses scripts (403); no Amphenol drawing in hand |
| 4UCON 14869 jack (SparkFun PRT-00132, on Clint's two existing BOBs) | https://cdn.sparkfun.com/assets/8/6/5/f/1/RJ11-Datasheet.pdf: 13.34 x 20.57 x 15.70 | checked only (L9 flag: too tall for the card pitch) | SparkFun's own STEP is an outdated version (community.sparkfun.com/t/44748) |
| RJ11 / RJ12 6P plug and the flat cable leaving its rear | box: standard 6P body after Cinch 32-5996UL (https://static.chipdip.ru/lib/750/DOC011750893.pdf: 9.65 x 6.60, 7.47 with the latch, 13.34 long) and `plug_len`, `plug_bend` [TBD-MEASURE] | stand-in | Clint's plugs are generic unbranded 6P6C crimp plugs; SparkFun sells none |
| Seeed Wio-E5 mini board | https://files.seeedstudio.com/products/113990939/LoRa-E5%20mini%20v1.0.brd | imported | Seeed publishes no 3D model |
| LoRa-E5 module, SMA-K, USB-C, buttons on the mini | boxes from the brd's footprints | stand-in | the import carries no part models |
| Bourns MF-R010 fuses | boxes | stand-in | Bourns models only through SnapEDA / Octopart (login) |
| WAGO 222-415 lever connector (E1) | box, 26.6 x 20.5 x 14.5 (WAGO data sheet, https://www.wago.com/222-415) | stand-in | the WAGO STEP sits behind the product page's download form |
| Amphenol RF 132172 SMA adapter (AD1) | boxes | stand-in | amphenolrf.com refuses scripts (403) |
| Amphenol RF 135110-01-06.00 cable and bulkhead | tubes and cylinders | stand-in | amphenolrf.com refuses scripts (403) |
| TE / Linx ANT-916-CW-HWR-SMA antenna | cylinders, length `ant_len` [TBD-MEASURE] | stand-in | te.com refuses scripts (403) |
| Adafruit #761 PG-9 and #762 PG-7 glands | thread, locknut, flange, body and dome from https://cdn-shop.adafruit.com/product-files/761/761diagram.jpg (PG-7 scaled by 11.5 / 15.2, https://www.adafruit.com/product/762) | drawn | |
| TI BQ25798EVM | box, outline `evm` [TBD-MEASURE] | stand-in | the EVM design files are not a direct download (TI product folder, login for some) |
| Printed cage, pack, box walls | boxes from `cage/cage.py` | stand-in | the cage is parametric boxes until it is printed |

## Models only behind a login

Download each into its own folder under `render/models/` (not committed), then tell the next pass its name so
`fetch_models.py` can check its SHA-256 and the renders can use it:

| Part | Where | Put it in |
|---|---|---|
| Amphenol 87180-066LF | https://www.amphenol-cs.com/product/87180066lf.html (3D model link), or https://www.snapeda.com/search/?q=87180-066LF | `render/models/JACK/` |
| Bourns MF-R010 | https://www.bourns.com/products/circuit-protection/resettable-fuses-pptc/product/MF-R (CAD models via SnapEDA) | `render/models/PTC/` |
| Amphenol RF 132172 and 135110-01-06.00 | https://www.amphenolrf.com/132172.html, https://www.amphenolrf.com/135110-01-06-00.html | `render/models/SMA/` |
| TE / Linx ANT-916-CW-HWR-SMA | https://www.te.com/en/product-ANT-916-CW-HWR-SMA.html | `render/models/ANT/` |
| TI BQ25798EVM design files | https://www.ti.com/tool/BQ25798EVM (design files) | `render/models/EVM/` |
