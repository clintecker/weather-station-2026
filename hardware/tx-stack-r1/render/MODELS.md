# Render models

This page lists every part in the renders, where its model comes from, and why. `render/fetch_models.py` fetches
every file marked real or imported into `render/models/` (not committed) and checks its SHA-256. If a file is
missing or changed, the render draws the checked boxes instead and says so in its legend.

What the Status column means:

- **real**: the maker's or KiCad's 3D model.
- **imported**: the bare board, built with KiCad from the maker's Eagle board file. The steps are
  `kicad-cli pcb import --format eagle`, then
  `pcb export step --board-only --include-pads --include-tracks --include-silkscreen`. You get the board, pads,
  tracks and silkscreen, but no part models. (`--board-only` on its own gives you only the bare board.)
- **drawn**: generated in `kicad_render.py` from the maker's drawing.
- **stand-in**: the envelope boxes the layout checks use.

| Part | Model source | Status | Why |
|---|---|---|---|
| SolderFul SOLDERBREAD#02 cards | `kicad_render.py`: outline, holes, strips from the datasheet (`sources.py`), back rails snapped off | drawn | we found no maker model (a web search turned up none, and solderful.com didn't load) |
| Lying resistors, standing DO-35 diodes, 100 nF discs | KiCad 10 library (`Resistor_THT`, `Diode_THT`, `Capacitor_THT`) | real | |
| Breakout headers (0.1 in, vertical) | KiCad 10 library (`Connector_PinHeader_2.54mm`) | real | |
| Bus header and SWD header (Clint's generic 2.54 mm right-angle male, the bus header cut to 1x30, the SWD header to 1x5) | `kicad_render.py` from the Sullins PRPC drawing as a stand-in for the generic part: tails, 90 degree bends, insulator, 5.8 mm mating pins [TBD-MEASURE] | drawn | the generic header has no drawing; KiCad's generic header has the wrong mating length |
| Backplane socket (generic 2.54 mm female strip, cut to 1x30) | boxes (drawn open in the section), sized from the Sullins PPPC drawing [TBD-MEASURE] | stand-in | as above |
| Adafruit SHTC3 #4636 | https://raw.githubusercontent.com/adafruit/Adafruit_CAD_Parts/main/4636%20SHTC3/4636%20SHTC3.step | real | |
| Adafruit MAX17048 #5580 | https://raw.githubusercontent.com/adafruit/Adafruit_CAD_Parts/main/5580%20MAX17048/5580%20MAX17048.step | real | |
| Adafruit INA228 #5832 | https://raw.githubusercontent.com/adafruit/Adafruit_CAD_Parts/main/5832%20INA228%20STEMMA%20QT/5832%20INA228%20STEMMA%20QT.step | real | shows its terminal block, which is not fitted |
| Adafruit PCA9548 #5626 (mux) | https://raw.githubusercontent.com/adafruit/Adafruit_CAD_Parts/main/5626%20PCA9548%20Stemma/5626%20PCA9548%20Stemma.step | real | in the cage renders |
| Pololu S7V8F3 | https://www.pololu.com/file/0J1374/pololu-step-up-step-down-voltage-regulator-s7v8fx.step | real | |
| SparkFun BOB-14021 board | https://raw.githubusercontent.com/sparkfun/RJ11_Breakout/master/hardware/RJ11-Breakout.brd (one board kept from the panel of two) | imported | SparkFun publishes no 3D model |
| Amphenol 87180-066LF RJ11 jack (the new BOBs) | boxes, 13.2 x 18 x 11.5. The 13.2 x 18 footprint matches the F.Fab outline of KiCad 10's `RJ12_Amphenol_54601-x06_Horizontal`. The 11.5 height comes only from the RS 771-0215 listing, which we couldn't check (RS returns 403) | stand-in | amphenol-cs.com refuses scripts (403); no Amphenol drawing in hand |
| 4UCON 14869 jack (SparkFun PRT-00132, on Clint's two existing BOBs) | https://cdn.sparkfun.com/assets/8/6/5/f/1/RJ11-Datasheet.pdf: 13.34 x 20.57 x 15.70 | checked only (L9 flag: too tall for the card pitch) | SparkFun's own STEP is an outdated version (community.sparkfun.com/t/44748) |
| RJ11 / RJ12 6P plug and the flat cable leaving its rear | box: standard 6P body after Cinch 32-5996UL (https://static.chipdip.ru/lib/750/DOC011750893.pdf: 9.65 x 6.60, 7.47 with the latch, 13.34 long) and `plug_len` [TBD-MEASURE]. Only `plug_len` sizes the box. `plug_bend` is listed in `sources.py` and only goes into the estimate for `plug_len`. No geometry reads it | stand-in | Clint's plugs are generic unbranded 6P6C crimp plugs; SparkFun sells none |
| Seeed Wio-E5 mini board | https://files.seeedstudio.com/products/113990939/LoRa-E5%20mini%20v1.0.brd | imported | Seeed publishes no 3D model |
| LoRa-E5 module, SMA-K, USB-C, buttons on the mini | boxes from the brd's footprints | stand-in | the import carries no part models |
| Bourns MF-R010 fuses | boxes | stand-in | Octopart lists 3D models for MF-R010 through partners such as SnapEDA. We couldn't load bourns.com (403), so we don't know if Bourns hosts its own |
| Amphenol RF 132172 SMA adapter (AD1) | boxes | stand-in | amphenolrf.com refuses scripts (403) |
| Amphenol RF 135110-01-06.00 cable and bulkhead | tubes and cylinders | stand-in | amphenolrf.com refuses scripts (403) |
| Taoglas TI.96.A113 antenna (AE1) | cylinders: coupling nut, hinge, the whip folded up, `ant_len` (203 x 12.7, from the datasheet) | stand-in | no STEP looked for |
| Adafruit #761 PG-9 and #762 PG-7 glands | thread, locknut, flange, body and dome from https://cdn-shop.adafruit.com/product-files/761/761diagram.jpg (PG-7 scaled by 11.5 / 15.2, https://www.adafruit.com/product/762) | drawn | |
| TI BQ25798EVM | box, outline `evm` [TBD-MEASURE] | stand-in | we found no published EVM design files. ti.com/tool/BQ25798EVM has only the user's guide SLUUCB5 and an EU DoC |
| Printed cage, pack, box walls | boxes from `cage/cage.py` | stand-in | the cage is parametric boxes until it is printed |

## Models only behind a login

You can download each of these by hand into its own folder under `render/models/` (not committed). A file name
alone isn't enough for the next pass. Nothing reads these folders yet.

Before a render can use a downloaded model, a later pass has to change the code:

- Add a `SOURCES` entry in `fetch_models.py` with the file name and SHA-256. `fetch()` expects a URL, so it
  also needs to handle a file that has none.
- Add a `step` entry on the part's placement in `layout/stack.py`, or on the cage extras in `kicad_render.py`.

The folder names below follow the `render/models/<kind>/` layout that `fetch_models.py` uses. No code defines
these kinds yet. `PTC` is already a footprint kind in `layout/stack.py`, but it has no model entry.

| Part | Where | Put it in |
|---|---|---|
| Amphenol 87180-066LF | https://www.amphenol-cs.com/product/87180066lf.html (not checked: 403), or DigiKey's listing https://www.digikey.com/en/products/detail/amphenol-cs-fci/87180-066LF/1001371 (EDA/CAD Models section). SnapEDA has no 3D model for this part. | `render/models/JACK/` |
| Bourns MF-R010 | https://www.bourns.com/products/circuit-protection/resettable-fuses-pptc/product/MF-R (not checked: 403). Octopart's MF-R010 page lists 3D models through SnapEDA and other partners. | `render/models/PTC/` |
| Amphenol RF 132172 and 135110-01-06.00 | https://www.amphenolrf.com/132172.html, https://www.amphenolrf.com/135110-01-06-00.html | `render/models/SMA/` |
| Taoglas TI.96.A113 | https://www.taoglas.com/datasheets/TI.96.A113.pdf (datasheet; no model downloaded) | `render/models/ANT/` |
| TI BQ25798EVM design files | None that we found. https://www.ti.com/tool/BQ25798EVM has no design-file download. The schematic, layout images and BOM are in the user's guide SLUUCB5 (https://ti.com/lit/pdf/SLUUCB5). People ask TI for the CAD files on E2E. | `render/models/EVM/` |
