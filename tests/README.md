# Tests

These are the Python `unittest` tests for the gateway, the tools and the firmware. The firmware tests compile the real C sources (`firmware/`) for the host with `cc`. Then they drive them through `ctypes` or small C drivers (`firmware/test_*.c`, `firmware/host/`). Each test file's docstring says what it covers.

Run these from the repository root:

```sh
sh tools/fetch-vendor.sh                                                   # once: pinned Mbed TLS for the crypto tests
WS0_UNSAFE_FAST_FSYNC=1 .venv/bin/python -m unittest discover -s tests     # 1,681 tests collected on 2026-11-19 (master 5e4bd84)
.venv/bin/python -m unittest tests.test_h01_report                         # one module
```

You can get the count without running the tests: `.venv/bin/python -c "import unittest; print(unittest.defaultTestLoader.discover('tests').countTestCases())"`. New tests raise the count, so rerun the command rather than trust the number above.

## What each group covers

| Files | Covers |
|---|---|
| `test_gateway.py`, `test_counter_regression.py`, `test_clock.py`, `test_link.py`, `test_logfile.py`, `test_mqtt_config.py`, `test_web.py`, `test_dashboard_js.py` | The gateway (`ws0/`, `gateway.py`): storage, deduplication, freshness, nonce-reuse detection, host clock check, serial link, logs, MQTT settings and Home Assistant discovery (health entities only for measured keys, unavailable once the newest health report is older than 1,900 s, and the fitted byte's "not measured" and "sensor fault" lists), dashboard back end and page script. `test_link.py` covers the open-but-silent reopen of `ws0/link.py` (decision record H8(f)). The link reopens in place after 90 s with no byte. The wait doubles up to 400 s and resets on any line. There's no reopen at the RX's 60 s `#alive` cadence. Each reopen is a `serial-reopen` event, not a failure, and `receiver-silent` still comes at 180 s. `test_dashboard_js.py` checks that a `serial-reopen` gateway event draws a marker |
| `test_harness.py` | The simulation harness (`ws0/harness.py`), with its intentional-failure controls |
| `test_frame.py`, `test_obs.py` | C against Python: the same frames and observation bytes on both sides |
| `test_stage0.py`, `test_store_powercut.py`, `test_flash_layout.py` | `test_stage0.py` covers the simulated station-to-gateway pipeline and its failure cases: replay, tamper, clock quarantine, ACK tamper, NACKs, time reconstruction, diagnostics and the epoch floor, HTTP/CSV, MQTT discovery, and CLI and service smoke tests. It also covers the portable sensor core `firmware/stage0.c` (SHT45 CRC and conversion, bus recovery) and the TX transmission policy `firmware/common/ws_policy.c`. `test_store_powercut.py` runs the flash store under simulated power cuts, and `test_flash_layout.py` checks the flash layout against the linker script |
| `test_tx_machine.py`, `test_rx_machine.py`, `test_i2c_bus.py`, `test_board_inputs.py`, `test_busymon.py`, `test_check.py` | `test_tx_machine.py`, `test_rx_machine.py`, `test_i2c_bus.py` and `test_board_inputs.py` test the TX and RX firmware as built, over a simulated board and I2C bus. `test_busymon.py` checks `App/busymon.c`'s task-time accounting on the host. `test_check.py` checks the run-time check facility (`firmware/common/ws_check.h`) and its per-file site numbering. `test_tx_machine.py` decodes the health report (kind 4, version 6) with the gateway's own `unpack_diag`. `test_i2c_bus.py` runs both bus profiles (mux and hub) and the recovery counter. It checks the I2C timing register's data hold for the INA228 SDA strap (`BusTiming`). It also checks the switched and unswitched devices: PA9 cycled 10 times drops only the sensors on the switched branch, while the INA228 and the MAX17048 on the unswitched branch never NACK (record step 1 exit 9). `i2c_bus_outcomes` names the clients that answered and failed (exit 9's per-half evidence), and the four INA228 rail monitors read side by side upstream. `test_board_inputs.py` runs the board ADC sequence (vane, ISET, charger input, VREFINT), VDDA from VREFINT, the pin modes and the CHG edges. It checks change B's pins (record N2): cups on PB5 with LPTIM1_IN1 (AF1), rain on PB4 with EXTI4. It checks the `DEBUG_RF_LDORDY_ENABLED` assert (a build with it on doesn't compile), and mux RESET on PB14, untouched without the mux. It also runs the counter link probe (record M7): two phases on a timer, the pull-up restored, and no self-count (the probe's own pulses on an open cups link add no count). `test_tx_machine.py` also runs TEST-SENSOR-POWER (PA9 low for `WSMP_SAMPLE_MS` + 1 s from a timer, ending high. Each half's `ack=`/`fail=` masks show the switched SHT45 gone and back and the INA228 and MAX17048 answering throughout) and the `#status` field `meter_link=` beside the radio `link` |
| `test_power_acq.py` | The power acquisition `firmware/stage0-node/App/power_acq.c` through `firmware/host/power_harness.c`, hub profile, one build per power profile (1 phase A, 2 phase B): battery current sign, means and energy, OUT kept apart from the cell, CHG flashing as a fault, ISET without PGOOD, four rails with one absent, and known answers shared with `power_regs.c` and `tools/benchlink_log.py` (spec 2026-10-29 sections 3, 6.3, 9.3 to 9.5) |
| `test_fault.py` | The crash record and the boot counter `firmware/stage0-node/App/fault.c` against a stand-in for the TAMP backup registers: last crash PC 0 with no crash, one boot a `fault_boot_note()`, saturation at 0xFFFF, a power-on restarts the count, DR12 written only there (spec 2026-10-29 sections 6.2, 9.8) |
| `test_wsmp_core.py`, `test_wsmp_host.py`, `test_wsmp_map.py`, `test_wsmp_registry.py`, `test_modules.py` | These test the module protocol WSMP and the eight bench station modules (ports 1 to 8: air T/RH, pressure, UVA, enclosure T/RH, battery, wind, rain, rails). They also test the battery (type 8) and rails (type 9) modules, the catalog map in power profiles 1 and 2, and the registry's quantities 18 to 24. `test_modules.py` also holds the meter link rules (record M7). Rain with three lows and no tip goes to fault, and a tip clears it. Cups with three lows go to suspect, not fault, then to fault when the vane moves or after 24 h. A vane reading outside the direction table gets flagged |
| `test_wsmp_set.py`, `test_descsets.py` | The descriptor set: the C codec (`firmware/common/wsmp.c`) and its Python twin (`ws0/wsmp_set.py`) against bytes from the specification. It also covers the gateway's descriptor sets (`ws0/descsets.py`), the current set, the serial alarm and the module identities it publishes |
| `test_wsmp_record.py`, `test_wsmp_cal.py` | Module identity on the sensor ports (spec 2026-10-21 sections 6.7, 6.9): the module record v1.0, its calibration and the rounding helper, and the admission verdict |
| `test_fuzz.py` | Short fuzz runs of the input parsers under AddressSanitizer and UBSan (`firmware/fuzz/`) |
| `test_rangetest.py` | The range-test firmware's packet format and settings handshake |
| `test_i2cscan.py` | The power conversions and the bench helpers against the datasheet scale factors, and the I2C tool's OLED text. `firmware/common/power_regs.c` holds the INA228, MAX17048, ADC/VREFINT and bq24074 ISET conversions, one copy linked by the node, `firmware/i2cscan` and `firmware/benchlink`. `firmware/i2cscan/App/bench_regs.c` holds the bench-only helpers, built on `power_regs.c` |
| `test_benchlink.py` | The bench telemetry link: its packet and SHT45 code against the logger's decoder. It checks the logger's rows (`battery_ma`, the shunt current turned once, + into the cell, and an older CSV backfilled), its R_ISET default of 1000 Ω (record 1.4, adopted with change A, read by this workflow from 7.1 P3, Clint to confirm) and `--iset-gain` default (0.990099, nominal) in `charge_ma`, its `--r-iset`, `--k-iset` and `--r-load` options. It checks the model hash, the build-sheet hash and the preflight status in the `logger_start` event detail, with the CSV header unchanged. It also covers events and main loop (a scripted port and a fake clock), the console logger, and the dashboard's charge count, `--shunt-from`, gaps, CSV reading and HTTP handler |
| `test_benchlink_dash.py` | The dashboard's step 1 flags (`tools/benchlink_dash.py`, record M4, M6, M7, P8, P9): the drop form and its gates (PGOOD, 30 mA, dV0; 20 mV and the 10 mV step), the VCELL step flag, the SOC-suspect window, injection case A raising only the drop flag and case B only the step flag, the M7 cross-checks, the CELL+ label with the VCELL − I × R_pack estimate, and P9's termination check. It checks `--rewrite-iset` rescaling only the rows after a `logger_start` with `r_iset=` the old value, `--preflight` with a stale block, and a structural check that the page draws every flag |
| `test_preflight.py` | `tools/preflight.py` and `source/checklist.py` (record D6). A good block is valid. It's stale when a hash differs from the current `wiring.toml` blob or `build-sheet.md`. It fails for an unknown id, a limit breach or a missing row, and it's missing with no block. C12 to C14 and C16 to C18 (the 1 A rows) are required when `rewire` or `step_exit` is true and not otherwise. C15 is a mode-B row. It also checks the exit codes 0 to 3 |
| `test_h01_report.py`, `test_rx_faults_tool.py`, `test_power_cut_tool.py`, `test_stack_report.py`, `test_blocking_report.py`, `test_loop_bounds.py`, `test_tangle.py` | These test the tools in `tools/`. `test_rx_faults_tool.py` classifies captures of protocol versions 6 (ours) and 5 (ours, previous version). `test_h01_report.py` also lists the serial gaps beside the score (record H8): `serial-lost` to `serial-open`, `serial-reopen`, `receiver-silent`, each missed `#alive` minute, clipped to the window, an open gap marked open |
| `test_openapi.py` | `docs/openapi.json` against the gateway: the Observation schema has exactly the catalog fields (`ws0/fields.py` `MEASURED`), the base keys, `wind_calm` and `qualifiers`, and each catalog field has its unit and decoded range. The HealthReport schema has exactly the keys the gateway stores. Served records, reports, history and status match their schemas (spec 2026-10-29 sections 5, 6.1, 10.2) |
| `test_breadboard.py` | The breadboard map `hardware/bench-breadboard-r0/` against the wiring guide and the firmware pins. It checks the off-board joints and leads (parsed, listed once in the sheet, drawn end to end, force leads wider than sense leads). In the sheet tier, `make.py sheet` runs without KiCad, its output equals the committed sheet, and the sheet carries the revision and both hashes (the `wiring.toml` blob and the renders' `layout.json` `model_hash`). It also checks the "Changes from the previous revision" section against the 2026-10-29 baseline |
| `test_breadboard_checks.py` | `source/checks.py` (record D3 checks 1 to 6 and 9, and check 8's ISET constants, `check_iset`: step 1 exit 7): each check on a change-A-shaped fixture model, once as built (passes) and once broken in one place (only that check fails). It also checks the H7 lead lengths (L_REG_3V3 and L_NUC_RET bounded by C20/C21, not 100 mm), the lead geometry and the M6 path segments |

A few files here are helpers, not tests:

- `toolchain.py`: skip rules, host C builds, a provisioned test station, and the `WS_I2C_MUX` choice of `wsmp_sources()`.
- `wsmp_wind_ref.py`: wind reference values written from the datasheet, independent of `mod_wind.c`.
- `wsmp_record_ref.py`: the module record, CRC-32C, calibration and rounding written from the spec, independent of the C. It uses integer arithmetic only.

`ws_div_round_vectors.csv` is data. It holds the rounding golden vectors, and the C helper and the Python reference must both give them.

## What a test needs, and when it skips

| Needs | Tests | Without it |
|---|---|---|
| `cc` | every test that builds firmware C | skips, or fails if `WS_REQUIRE_CC=1` |
| `vendor/` (`tools/fetch-vendor.sh`) | the Mbed TLS tests in `test_frame.py`, `test_fuzz.py`, `test_tx_machine.py` | skips, or fails if `WS_REQUIRE_VENDOR=1` |
| `node` | `test_dashboard_js.py` | skips |
| KiCad 10 and `tools/fetch-router.sh` | the KiCad tests in `test_breadboard.py` (its model and sheet tests need neither) | skips and names what is missing |
| nothing | `test_preflight.py`, `test_breadboard_checks.py`, `test_benchlink_dash.py`: no KiCad, no serial port and no git history (CI's checkout is shallow). They write their fixtures to a temporary directory. `test_breadboard_checks.py` also reads the committed model | no skip for a missing tool. `test_breadboard_checks.py` holds the committed model to every check only once it carries the change-A joints, and says so when it skips |
| network | one SNTP test in `test_clock.py` | skips |
| POSIX | the permission-bit test in `test_mqtt_config.py`, the `flock` test in `test_link.py` | skips on Windows |

### Host build variants

Two compile-time switches pick the board a host build models. Each test passes its value with `-D`. Neither one is an environment variable.

| Switch | Values | Which tests | Rule |
|---|---|---|---|
| `WS_I2C_MUX` (`firmware/stage0-node/App/i2c_bus.h:19`) | `0` is the STEMMA QT hub, no mux (the firmware default, the official phase A wiring). `1` is the ports board's TCA9548A mux at 0x71 with record EEPROMs | `1`: every build through `toolchain.wsmp_sources()` (`tests/toolchain.py:78`), the default for `test_modules.py`, `test_wsmp_map.py`, `test_wsmp_host.py` and `test_i2c_bus.py`'s `I2cBus`. `0`: `test_power_acq.py`, `test_tx_machine.py`, `test_i2c_bus.py`'s `I2cBusHub` | Existing tests keep `WS_I2C_MUX=1` (spec 2026-10-29 section 14, Bus). A new test of the field wiring uses the hub variant, `wsmp_sources(..., mux=0)` or `-DWS_I2C_MUX=0` |
| `WS_POWER_PROFILE` (`firmware/stage0-node/App/power_config.h:32-33`) | `1` is phase A, the default (bq24074, battery INA228 0x40, MAX17048 0x36). `2` is phase B (plus load 0x41, solar 0x45, USB-C 0x48 INA228s). `3` is phase C, and it stops the build (`#error`) | `test_power_acq.py` (`PhaseA`, `PhaseB`), `test_wsmp_map.py` (`PROFILE = 1`, `PhaseB`). Every other build takes the default | A slot a profile cannot fill is not fitted (absent), never INVALID. A test asserts which by the profile, not by a part's state |

## Environment variables

| Variable | Effect |
|---|---|
| `WS0_UNSAFE_FAST_FSYNC=1` | SQLite `synchronous=OFF` and no `fullfsync`, so a commit doesn't survive a power loss. Importing `tests/toolchain.py` sets `WS0_UNSAFE_FAST_FSYNC=1` (unless it's already set), so a module that imports it gets fast SQLite when you run it alone. `test_gateway.py`, `test_link.py`, `test_harness.py` and `test_counter_regression.py` set it themselves. Never set it for a gateway that acknowledges real data |
| `WS_REQUIRE_CC=1`, `WS_REQUIRE_VENDOR=1` | Turn the `cc` and `vendor/` skips into failures. CI sets both on Linux and macOS |
| `WS_FUZZ_RUNS` | Mutated inputs per fuzz target in `test_fuzz.py` (default 20000) |
| `WS_RX_APP` | Build a modified copy of `app_rx.c` in `test_rx_machine.py` (mutation testing) |

The 1,440-record test in `test_stage0.py` uses accelerated virtual timestamps. None of the tests here count as evidence for the 24-hour delivery test (H01).

## The wave gate (power telemetry work)

The power telemetry work (`docs/superpowers/plans/2026-10-29-power-telemetry.md`, spec `docs/superpowers/specs/2026-10-29-power-telemetry-design.md` section 14) changes many files in waves of parallel batches. The full suite is the gate between waves:

| Step | What happens |
|---|---|
| After each wave | The orchestrator runs the whole suite once, as above (`WS0_UNSAFE_FAST_FSYNC=1 .venv/bin/python -m unittest discover -s tests`), never `tools/gates.sh` |
| Expected-red set | It records every red test with the batch that owns its fix. A test is expected red only if a later batch owns its fix. A red test owned by the finished wave or an earlier one goes back to its owner |
| Must-pass list | Each batch must pass the tests it owns and every test green at the previous gate. An expected-red test it does not own is not its failure |
| Last wave | The expected-red set is empty. The Gates stage then runs `tools/gates.sh` once |

A worker runs only its own modules (`.venv/bin/python -m unittest tests.test_x`), not the whole suite.
