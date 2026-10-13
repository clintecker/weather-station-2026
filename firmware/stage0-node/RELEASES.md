# Stage-0 firmware releases

Each release is built from a clean commit (no `-dirty`), built twice from scratch with identical
hashes, flashed to both boards, and recorded here. H01 evidence must name a release from this file.

## How to cut a release

1. Commit everything. `git status --short` must print nothing, or the build is labeled `-dirty`.
2. Run `tools/fetch-vendor.sh`. It verifies every pinned vendor commit. Use xPack arm-none-eabi-gcc 15.2.1-1.1 (the Makefile `TOOLCHAIN` default).
3. In `firmware/stage0-node`, run `make clean && make ROLE=rx && make ROLE=tx`. Note the two `.bin` SHA-256 values printed at the end of each build. Each build also prints `flash budget: N of 65536 B` and fails above 90 % (`docs/firmware-budget.md`).
4. Run `make clean && make ROLE=rx && make ROLE=tx` again. Both `.bin` hashes must be identical to step 3.
5. Flash RX, then TX: `make ROLE=rx flash SERIAL=<RX serial>`, then the same with `ROLE=tx`. Check that both `#boot` lines show `fw=<12-character commit>`.
6. Add a section below with the commit, date, hashes, inputs, flash record and radio settings, and commit it.

**Which hashes are reproducible:** the `.bin` hashes are the release identity. They match any clean build of the same commit with the same inputs; a rebuild of a07f498 in another checkout matched (see `docs/hardware/nucleo-wl55jc-bringup.md`, Office session). The `.elf` hashes are informational only. The Makefile compiles with `-g3`, so the ELF debug info embeds absolute source and toolchain paths, and the ELF hash changes with the checkout location. Every build also embeds the commit (`-DWS_FW_VERSION` from `git describe`), so a later commit never reproduces an earlier release.

## 0f456040fe54 — 2026-10-13 (bench, sensor not yet wired)

| Artifact | SHA-256 |
|---|---|
| `build/rx/stage0-rx.bin` (30,360 B) | `5dd14d59c3c053d94146808422c8d82b865ae34ff52a9a16780def7d7e65629a` |
| `build/rx/stage0-rx.elf` (path-dependent) | `39244ffa8354c93d75ed7cb437d834aff39802bacb5c32fc25eb6d200fcb13b2` |
| `build/tx/stage0-tx.bin` (53,176 B) | `0bd4e94575634bf792993d73c5fafff67f1bc20624445de98625da67c0057f60` |
| `build/tx/stage0-tx.elf` (path-dependent) | `8a920d899646d27da38d7af8ba6e7524dd57a2e1f144a49b8e05f4502855b38e` |

- Source: commit `0f456040fe54`. Changes since a07f498: sensor `rc=` on `#sample` and `#sensor` boot check; internal I2C pull-ups; I2C bus-recovery STOP fix (`ws_i2c_recover`); WIPE keeps counter and epoch (gap G17); strict PROVISION parser with key cleared from console buffers; while probing, SURPLUS/NORMAL send the live reading every minute (only CONSERVE backs off); health reports also while probing. Protocol and flash layout unchanged (draft 4).
- Inputs: as a07f498 (`tools/fetch-vendor.sh`, xPack arm-none-eabi-gcc 15.2.1-1.1, OpenOCD 0.12.0).
- Reproducibility: two clean builds (`make clean`, then both roles) gave identical `.bin` hashes.
- Flashed 2026-10-13: RX → board B `0016001E4142500E20353451`, TX → board A `003B00194142500E20353451`. TX `STATUS`: `fw=0f456040fe54`, `provisioned=1`, `kcv=b7142e` (office key kept across the flash), `kat=pass`. First minute: `#sample … valid=0 rc=-2` (no sensor wired: address NACK, as intended), both pending readings ACKed, gateway accepted 2, rejected 0.
- Radio (bench): 915.0 MHz, LoRa 500 kHz, SF7, CR 4/5, 0 dBm.
- Not an H01 release: the SHT45 is not connected yet, and the radio settings are bench values.

## a07f498273f7 — 2026-10-13 (bench, sensor not yet wired)

| Artifact | SHA-256 |
|---|---|
| `build/rx/stage0-rx.bin` | `ed2f0d3516a59e960a39d2e2a1ec93736790d14f41e2810a413565e77f8262c1` |
| `build/rx/stage0-rx.elf` | `78a199714633e44da8d36a84a21158b77ba14ef6494497b00946364143308b7e` |
| `build/tx/stage0-tx.bin` | `3d4ad22f0842219bf947a6ce0d9eb9d50adc0c8240ced6c90072e23fbaac4e79` |
| `build/tx/stage0-tx.elf` | `4425d77b8454aaa6c41f6d9408a3846404165caddc9550ddd76615dce37a6155` |

- Source: commit `a07f498273f7` (protocol draft 4 + NACK + health report). Build: `make ROLE=rx`, `make ROLE=tx` in `firmware/stage0-node`.
- Inputs: `tools/fetch-vendor.sh` (STM32CubeWL v1.6.0 `f934cd2` + pinned submodules, Mbed TLS 3.6.6), xPack arm-none-eabi-gcc 15.2.1-1.1, OpenOCD 0.12.0.
- Reproducibility: two clean builds gave identical `.bin` hashes.
- Flashed 2026-10-13: RX → board B `0016001E4142500E20353451`, TX → board A `003B00194142500E20353451`. Both boot lines report `fw=a07f498273f7`.
- Radio (bench): 915.0 MHz, LoRa 500 kHz, SF7, CR 4/5, 0 dBm.
- Not an H01 release: the SHT45 is not connected, and the radio settings are bench values.
