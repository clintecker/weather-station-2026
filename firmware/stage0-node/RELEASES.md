# Stage-0 firmware releases

Each release is built from a clean commit (no `-dirty`), built twice from scratch with identical
hashes, flashed to both boards, and recorded here. H01 evidence must name a release from this file.

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
