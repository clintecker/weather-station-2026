# macOS validation of the Stage-0 checkpoint — 2026-10-12

First execution of checkpoint `8aca12393142d8d85232bf7c0ae62dc19dbc783f` outside the original Linux host. **This is host software and simulation only. H01 remains NOT RUN.**

## Inputs

| Artifact | SHA-256 | Check |
|---|---|---|
| `weather-station-stage0.zip` | `b415259ddefb31b94e4362aa8ae049cdbb51fba2ecb9be95ca8072f814381903` | 90/90 files match its `SHA256SUMS.txt`. Contents identical to git `8aca123` apart from the two manifest files. |
| `weather-station-stage0-history.bundle` | `c061feaef8e88d1cd3971cb4ccc4d24b98b20f494a6ef419bea342bff244c09b` | HEAD `8aca123`, 2 commits. This repo was initialised from it. |
| `chicago-test-hardware-r0.zip` | `e273d1fb645ea7edcc3f427f460f53321ca00ce64928584399a5fff8fff493e4` | 66/66 files match its `SHA256SUMS.txt`. Imported to `hardware/chicago-test-hardware-r0/`. |

## Host

MacBookPro18,4 (Apple M1 Max), macOS 26.7.1 (25G313), Python 3.12.7 (mise), Apple clang 17.0.0. Virtualenv `.venv` contains exactly the `requirements.txt` pins: cryptography 50.0.1, paho-mqtt 2.1.0, pyserial 3.5, cffi 2.1.1, pycparser 3.11.

## Unit tests

`python -m unittest discover -s tests -v` → **28/28 OK** in 5.3 s. This includes the C tests (`test_c_python_wire`, `test_sensirion_crc`, `test_bus_failures_crc_and_conversion`) built with Apple clang.

## Simulation harness

`python -m ws0.harness --output evidence/harness-macos-2026-10-12` → exit 0, 38 s wall time.

| Scenario | Timely | Missing | Trace vs recorded `simulation-results/` |
|---|---:|---:|---|
| baseline | 100.00% | 0 | identical |
| noisy-link-7 | 99.24% | 0 | identical |
| noisy-link-73 | **98.82%** | 0 | identical |
| noisy-link-2026 | 99.03% | 0 | identical |
| radio-outage | 98.61% | 0 | identical |
| host-outage | 99.31% | 0 | **recorded trace truncated** (see below) |
| reboots | 100.00% | 0 | identical |
| sensor-fault | 100.00% | 0 | identical |
| clock-errors | 99.31% | 0 | identical |
| storage-failure | 99.65% | 0 | identical |
| ack-loss | 100.00% | 0 | identical |
| identity-collision | 100.00% | 0 | identical |

These reproduce the recorded campaign. The known weakness is unchanged: **noisy-link-73 misses the 99%-within-120 s target (98.82%)**. Scenario PASS means each scenario's integrity/recovery contract held; it is not an H01 pass.

### Finding: recorded `host-outage/trace.jsonl` is incomplete
- Recorded: 2,962 events, ending at virtual time 1800034860 on an `uplink send`. macOS run: 7,255 events.
- The first 2,962 lines are byte-identical, and `result.json` is identical. Only the recorded trace stops early.
- The recorded file still matches the archive's `SHA256SUMS.txt`, so it was already short when the manifest was generated, not damaged in transfer.
- Likely cause: the trace was copied or captured before the run finished writing it. The original evidence is left unchanged. Use `evidence/harness-macos-2026-10-12/host-outage/trace.jsonl` as the complete trace for this scenario.
