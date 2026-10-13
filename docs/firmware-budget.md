# Firmware budget: flash, RAM, CPU and radio

Measured 2026-10-13 on release `0f456040fe54` (`firmware/stage0-node/RELEASES.md`). Measured
numbers come from the build (`arm-none-eabi-size`, the linker map) or from the firmware's own
airtime formula. Rows marked **estimate** are planning figures for future features, not
measurements.

## Summary

| Resource | Available | Used now | Status |
|---|---|---|---|
| Flash, application region | 64 KB (pages 0–31, enforced by the linker script) | TX 53,176 B (81 %), RX 30,360 B (46 %) | **TX is the constraint**: about 12 KB left |
| Flash, node state | 192 KB (pages 32–127) | key 1 page, meta log 2 pages, journal 93 pages (4,743 slots, about 3.3 days) | Fixed by `App/flash_layout.h` |
| RAM | 64 KB (RAM1 32 KB + RAM2 32 KB) | TX: 6,944 B bss + 112 B data + 2.5 KB heap/stack, all in RAM1 | Ample; RAM2 unused |
| CPU | Cortex-M4 at 48 MHz (Cortex-M0+ core unused) | One sample and a few frames per minute | No constraint |
| Radio payload | 24-byte observation plaintext in a 56-byte frame | Temperature and humidity only | **The constraint for more sensors** |

Sources: `STM32WL55JCIX_FLASH.ld` (FLASH 64K, RAM1/RAM2 32K each, heap 0x200, stack 0x800),
`App/flash_layout.h`, `firmware/common/ws_frame.h` (`WS_OBS_PLAIN_LEN 24`, header 16, tag 16).

The build enforces a budget: `make` prints `flash budget: N of 65536 B` and fails above
`FLASH_BUDGET_PCT` (default 90 %) of the application region (`firmware/stage0-node/Makefile`).

## Where the TX flash goes

Linked sections from `build/tx/stage0-tx.map` (`.text`, `.rodata`, `.data`):

| Component | Bytes | Share |
|---|---:|---:|
| ST HAL drivers | 14,328 | 27 % |
| SubGHz_Phy radio driver | 8,470 | 16 % |
| Mbed TLS (AES-128-CCM only) | 7,482 | 14 % |
| Board glue (`Core/`: clocks, UART, RTC, IRQs, startup) | 5,159 | 10 % |
| ST utilities (sequencer, timer, trace, printf) | 2,988 | 6 % |
| libc + libgcc | 1,748 | 3 % |
| **Our code** (`app_tx`, `node_store`, `stage0`, `ws_frame`, `sensor`, console, LEDs, watchdog) | about 12,500 | about 24 % |

Measured on the `a07f498` sources; release 0f456040fe54 is the same size within 8 bytes (53,184 → 53,176 B). About 41 KB is platform
cost that does not grow with features; new features add mostly our own code and a few more HAL
modules.

## Measured savings available

| Option | TX | RX | Cost |
|---|---:|---:|---|
| Link-time optimisation (`-flto`), measured in a scratch build | 53,176 → 46,584 B (**−6.6 KB, −12 %**) | 30,360 → 25,488 B (−16 %) | Changes inlining and code order; needs a full bench check before any release uses it |
| Low-layer (LL) drivers instead of HAL for GPIO/I2C/UART | not measured | — | **estimate**: a large part of the 14 KB HAL share; a rewrite of board glue |
| Field build without the debug console text | not measured | — | **estimate**: 1–3 KB; loses bench diagnostics |

## Future features (estimates)

| Feature (stage) | Flash estimate | Notes |
|---|---|---|
| Power telemetry: INA228, BQ25798, NTCs (Stage 1) | 4–7 KB | Two I2C drivers plus the ADC HAL module |
| SPI NOR journal for the 30-day buffer, H11 (Stage 1) | 6–10 KB | SPI HAL plus a journal backend |
| RS-485 / Modbus sensor modules (Stage 2) | 4–8 KB, plus a few KB per sensor type | UART HAL is already linked |
| Low-power sleep, heater control, energy state machine | 4–8 KB | Mostly our code |
| Multi-sensor payload (protocol draft 5) | 1–3 KB | Encoder and decoder |
| **Total** | **about 20–40 KB** | **Does not fit in the 12 KB left** |

## The plan that makes it fit

1. **Flash layout v2 with H11.** The 30-day buffer moves to SPI NOR, which frees most of the 186 KB
   internal journal. The application region can then grow to 128 KB or more. **Constraint:** the
   key and the transmission counter live in the node-state pages. A layout change must carry the
   counter and epoch across (or the board gets a new key); otherwise it repeats AES-CCM nonces
   (gap G17, `docs/runbook-moving-boards.md`).
2. **LTO as a measured reserve** (−6.6 KB on TX) if a feature must land before layout v2.
3. **Budget check** in every build (above), and a size line in every `RELEASES.md` entry.
4. **Module split after H01** (`docs/firmware-review-2026-10-13.md` §4–5): sensors become
   drivers behind one interface instead of edits to `app_tx.c`.

## Radio payload: the limit for more sensors

Every frame carries a fixed 32 bytes (16-byte authenticated header, 16-byte tag) around the
plaintext. Air time per frame from the firmware's formula (`airtime_ms()` in `App/app_tx.c`:
500 kHz, CR 4/5, 8-symbol preamble, explicit header, CRC on):

| Plaintext | Frame | SF7 | SF9 | SF10 | SF12 |
|---:|---:|---:|---:|---:|---:|
| 24 B (today) | 56 B | 26.9 ms | 87.3 ms | 164.4 ms | 575.5 ms |
| 40 B | 72 B | 33.3 ms | 107.8 ms | 195.1 ms | 657.4 ms |
| 56 B | 88 B | 38.5 ms | 123.1 ms | 225.8 ms | 780.3 ms |
| 72 B | 104 B | 44.9 ms | 143.6 ms | 256.5 ms | 903.2 ms |
| 104 B | 136 B | 56.4 ms | 179.5 ms | 328.2 ms | 1,108.0 ms |

- **One bigger frame beats several frames.** Going from 24 to 56 bytes of plaintext adds 36 % air
  time at SF12 (575.5 → 780.3 ms); a second 56-byte frame adds 100 %, plus another ACK window.
- **The airtime cap shrinks the backlog drain.** At SF12 the NORMAL cap of 5 s per minute allows
  about 3 exchanges with today's frame (5000 / (2 × 575.5 + 300)) and 2 with an 88-byte frame
  (5000 / (2 × 780.3 + 300)). The ACK is also a 56-byte frame (`WS_ACK_FRAME_LEN`); this estimate
  assumes it keeps that size.
- **Energy follows air time.** Per-frame energy figures and SF choices: `docs/radio-energy-policy.md` §3.

**Recommendation:** design the draft-5 observation format (for example, a sensor bitmap plus
fixed-width fields, or a compact type-length-value list) **before** the second sensor type,
sized for the full sensor set in one frame.
