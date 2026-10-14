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

## bc5e6ede429c — 2026-10-14 (bench, protocol draft 5, SHT45 wired)

| Artifact | SHA-256 |
|---|---|
| `build/rx/stage0-rx.bin` (31,696 B) | `27d6a013b442fffcf8d5d2e8c7aa9a1d2b8e55db49d33cab6119ca44650ffa6c` |
| `build/rx/stage0-rx.elf` (path-dependent) | `77ed90ab4f7a9c73de17bcb1954cbd07c3ffc5e7916eab078c99dfba8b9127ff` |
| `build/tx/stage0-tx.bin` (53,752 B) | `89726d99a486e6c31600ac643e4bf108911d57e753d1f4f025118f83aac0c03b` |
| `build/tx/stage0-tx.elf` (path-dependent) | `66bb1327d3a617d697d1050ba6bf6692894d818e714e5e26ae077cda6bb3ae4a` |

- Source: commit `bc5e6ede429c`. **Protocol draft 5** (`docs/protocol-draft5-design.md`, commits 6f52a51..bc5e6ed): 8-byte header and CCM tag, u40 counter (refused past 2^40-1 in the allocator and the sealer), u16 station, 33-byte ACK/NACK, byte-aligned observation with a field bitmap (T/RH build: 26-byte plaintext, 42-byte frame), 32-byte health report (build ID, ACK RSSI/SNR, crash count, energy state). Journal slots sized by the build's fields (48 B, 3,906 records); page magic "WSJ" + slot size. RX forwards frames up to the largest catalog frame (`hex_print` truncated above 64 B before).
- Built from a clean `git worktree` of the commit (the main checkout had uncommitted docs). Inputs: as a07f498. Flash budget: TX 82.0 %, RX 48.4 %. Stack bound: TX 80 %, RX 27 %.
- Reproducibility: two clean builds gave identical `.bin` hashes.
- Release procedure for the format change: TX `WIPE ERASE-ALL-NODE-STATE` (run by Clint; `pending=0` checked first, counter kept: 8622 before, 8705 after), flash, new run directory `run-d5`, `provision-node` with a **new key**.
- Flashed 2026-10-14 17:58Z: RX → board B `0016001E4142500E20353451`, TX → board A `003B00194142500E20353451`. TX after provisioning: `fw=bc5e6ede429c`, `kcv=5618eb`, `kat=pass` (draft-5 encoder vector, sealed frame, 2^40 refusal), `epoch=35`, `ctr=8705`, `#sensor ok t=2607 rh=4059`.
- Bench check 17:59Z: on air a 42 B observation and a 33 B ACK; the live reading and the one taken before the gateway started both stored (version 5, T/RH valid, availability per field); 2 accepted / 0 rejected, `alarm` null, counter mark 8708, `replays=0`; RX `uart_errors=0`.
- Not yet an H01 release: radio settings are bench values; the sensor-unplug check and the first health report on this release are still to be seen.

## 45f43e78fe91 — 2026-10-13 (bench, sensor not yet wired)

| Artifact | SHA-256 |
|---|---|
| `build/rx/stage0-rx.bin` (31,584 B) | `d81863d8641c939271b611bec9cd67003534bb5afd85e652820219f1afbd6956` |
| `build/rx/stage0-rx.elf` (path-dependent) | `520b795909c553b2a3c8a2fb325e7bc25e7194eb1ca03e53424b3d5aacc7a113` |
| `build/tx/stage0-tx.bin` (52,896 B) | `b254929cd3f507fec5ba43d7bc2fd3476941b48d4ac21836b4e9ee18ba08bd68` |
| `build/tx/stage0-tx.elf` (path-dependent) | `f074ba8e02397bc54be4f5ec0433267c9d93d3db609435198dc42a40c1665913` |

- Source: commit `45f43e78fe91`. Changes since 9e3d38f08e8b: strict warnings with `-Werror` for our C; stack reservation 2 → 8 KB after a worst-case bound (`make stack`: TX 6,408 B, RX 2,020 B); Mbed TLS cipher layer removed (no heap use, −1.7 KB); `stack_peak` reported; TX `STATUS` split into `#status` + `#counts` (the single line was truncated); HardFault/NMI crash records (`#fault`, `TEST-FAULT`); `_Static_assert`s on frame and flash geometry; console parsing moved to `firmware/common/ws_console.c` (fuzzed). Protocol and flash layout unchanged (draft 4).
- Inputs: as a07f498. Flash budget: TX 80.7 %, RX 48.2 %.
- Reproducibility: two clean builds gave identical `.bin` hashes.
- Flashed 2026-10-13 21:31Z: RX → board B `0016001E4142500E20353451`, TX → board A `003B00194142500E20353451`. TX `STATUS`: `fw=45f43e78fe91`, `kcv=b7142e`, `kat=pass`, `epoch=32`, `ctr=7939`, `stack_peak=1240`.
- Crash test: `TEST-FAULT` on TX gave `#fault kind=hard pc=0800109a lr=080008a7 cfsr=00008200 hfsr=40000000 bfar=20040000 count=1`, with `reset=software` at once; `pc` is the faulting load in `fault_test` (`fault.c:48`). It also gave `epoch=33` and `ctr=8193` (both moved forward). On RX: the same record, with `pc=080010fa` (its `fault_test` load).
- Gateway after the restart: 6 accepted / 0 rejected, `alarm` null, counter high-water mark 8200, `counter_regression=0`, RX `relistens=0 uart_errors=0 stack_peak=392`.
- Not an H01 release: the SHT45 is not connected yet, and the radio settings are bench values.

## 9e3d38f08e8b — 2026-10-13 (bench, sensor not yet wired)

| Artifact | SHA-256 |
|---|---|
| `build/rx/stage0-rx.bin` (30,912 B) | `c7239804707461eceee901fea1252c9cbc3e4fdba0324162acd9fed8e14bfa5c` |
| `build/rx/stage0-rx.elf` (path-dependent) | `511fed32ff6dd5c4bc6b5ace7e5024a906a7c8c98c31a9f5b4497c4514549cc3` |
| `build/tx/stage0-tx.bin` (53,880 B) | `91d8e5479fb44295e08006e0e1243fcb38f510d6cdf6a15afc9cb6a7193f4135` |
| `build/tx/stage0-tx.elf` (path-dependent) | `63535ce267939f3c9b615e7189a4c34c866461a94d5604643086ddc63487564f` |

- Source: commit `9e3d38f08e8b`. Changes since 0f456040fe54: flash store over a `ws_flash` ops struct with host power-cut tests (P3) and four store fixes they found; UART receive errors re-armed and counted (P5); RX relisten after 5 silent minutes (P6); TX consecutive-failure watchdog and boot retry (P7). Protocol and flash layout unchanged.
- Inputs: as a07f498. Flash budget: TX 82.2 %, RX 47.2 %.
- Reproducibility: two clean builds gave identical `.bin` hashes.
- Flashed 2026-10-13: RX → board B `0016001E4142500E20353451`, TX → board A `003B00194142500E20353451`. TX `STATUS`: `fw=9e3d38f08e8b`, `kcv=b7142e`, `kat=pass`, `epoch=31`, `ctr=7683`. Gateway: 2 accepted / 0 rejected, `alarm` null, counter high-water mark 7684, RX `relistens=0 uart_errors=0`.
- Not an H01 release: the SHT45 is not connected yet, and the radio settings are bench values.

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
