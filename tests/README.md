# Tests

Python `unittest` tests for the gateway, the tools and the firmware. The firmware tests compile the real C sources (`firmware/`) for the host with `cc` and drive them through `ctypes` or small C drivers (`firmware/test_*.c`, `firmware/host/`). Each test file's docstring says what it covers.

Run from the repository root:

```sh
sh tools/fetch-vendor.sh                                                   # once: pinned Mbed TLS for the crypto tests
WS0_UNSAFE_FAST_FSYNC=1 .venv/bin/python -m unittest discover -s tests     # 595 tests on 2026-10-19 (commit 09e6cea)
.venv/bin/python -m unittest tests.test_h01_report                         # one module
```

## What each group covers

| Files | Covers |
|---|---|
| `test_gateway.py`, `test_counter_regression.py`, `test_clock.py`, `test_link.py`, `test_logfile.py`, `test_mqtt_config.py`, `test_web.py`, `test_dashboard_js.py` | The gateway (`ws0/`, `gateway.py`): storage, deduplication, freshness, nonce-reuse detection, host clock check, serial link, logs, MQTT settings, dashboard back end and page script |
| `test_harness.py` | The simulation harness (`ws0/harness.py`), with its intentional-failure controls |
| `test_frame.py`, `test_obs.py` | C against Python: the same frames and observation bytes on both sides |
| `test_stage0.py`, `test_store_powercut.py`, `test_flash_layout.py` | Portable sensor code, the flash store under simulated power cuts, the flash layout against the linker script |
| `test_tx_machine.py`, `test_rx_machine.py`, `test_i2c_bus.py`, `test_board_inputs.py`, `test_busymon.py`, `test_check.py` | The TX and RX firmware as built, over a simulated board and I2C bus |
| `test_wsmp_core.py`, `test_wsmp_host.py`, `test_wsmp_map.py`, `test_wsmp_registry.py`, `test_modules.py` | The module protocol WSMP and the seven bench station modules |
| `test_wsmp_record.py`, `test_wsmp_cal.py` | Module identity on the sensor ports (spec 2026-10-21 sections 6.7, 6.9): the module record v1.0, its calibration and the rounding helper, and the admission verdict |
| `test_fuzz.py` | Short fuzz runs of the input parsers under AddressSanitizer and UBSan (`firmware/fuzz/`) |
| `test_rangetest.py` | The range-test firmware's packet format and settings handshake |
| `test_h01_report.py`, `test_rx_faults_tool.py`, `test_power_cut_tool.py`, `test_stack_report.py`, `test_blocking_report.py`, `test_loop_bounds.py`, `test_tangle.py` | The tools in `tools/` |
| `test_breadboard.py` | The breadboard map `hardware/bench-breadboard-r0/` against the wiring guide and the firmware pins |

Helpers, not tests: `toolchain.py` (skip rules, host C builds, a provisioned test station) `wsmp_wind_ref.py` (wind reference values written from the datasheet, independent of `mod_wind.c`) and `wsmp_record_ref.py` (the module record, CRC-32C, calibration and rounding written from the spec, independent of the C; integer arithmetic only). Data: `ws_div_round_vectors.csv`, the rounding golden vectors that the C helper and the Python reference must both give.

## What a test needs, and when it skips

| Needs | Tests | Without it |
|---|---|---|
| `cc` | every test that builds firmware C | skips; fails if `WS_REQUIRE_CC=1` |
| `vendor/` (`tools/fetch-vendor.sh`) | the Mbed TLS tests in `test_frame.py`, `test_fuzz.py`, `test_tx_machine.py` | skips; fails if `WS_REQUIRE_VENDOR=1` |
| `node` | `test_dashboard_js.py` | skips |
| KiCad 10 and `tools/fetch-router.sh` | the model tests in `test_breadboard.py` | skips and names what is missing |
| network | one SNTP test in `test_clock.py` | skips |
| POSIX | the permission-bit test in `test_mqtt_config.py`, the `flock` test in `test_link.py` | skips on Windows |

## Environment variables

| Variable | Effect |
|---|---|
| `WS0_UNSAFE_FAST_FSYNC=1` | SQLite `synchronous=OFF` and no `fullfsync`: a commit does not survive a power loss. `toolchain.py` sets it for every test module. Never set it for a gateway that acknowledges real data |
| `WS_REQUIRE_CC=1`, `WS_REQUIRE_VENDOR=1` | Turn the `cc` and `vendor/` skips into failures. CI sets both on Linux and macOS |
| `WS_FUZZ_RUNS` | Mutated inputs per fuzz target in `test_fuzz.py` (default 20000) |
| `WS_RX_APP` | Build a modified copy of `app_rx.c` in `test_rx_machine.py` (mutation testing) |

The 1,440-record test in `test_stage0.py` uses accelerated virtual timestamps. No test here is evidence for the 24-hour delivery test (H01).
