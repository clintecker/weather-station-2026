# Firmware budget: flash, RAM, CPU and radio

The summary's flash and RAM figures were measured 2026-10-16 on master (`f26bc3b`, after release
`809230951ae1`); the stack table and the radio section on release `bc5e6ede429c` (2026-10-14, protocol draft 5). Older rows say which release they were measured on
(`firmware/stage0-node/RELEASES.md`). Measured numbers come from the build (`arm-none-eabi-size`, the linker map) or from the firmware's own
airtime formula. Rows marked **estimate** are planning figures for future features, not
measurements.

## Summary

| Resource | Available | Used now | Status |
|---|---|---|---|
| Flash, application region | 64 KB (pages 0–31, enforced by the linker script) | TX 58,240 B (88.9 %), RX 34,840 B (53.2 %) | **TX is the constraint**: 7,296 B left, 742 B below the 90 % guard |
| Flash, node state | 192 KB (pages 32–127) | key 1 page, meta log 2 pages, journal 93 pages (3,348 slots of 56 B for the T/RH build with the minute summary, about 2.3 days) | Pages fixed by `App/flash_layout.h`; slot size follows `App/node_fields.h` |
| RAM | 64 KB (RAM1 32 KB + RAM2 32 KB) | TX: about 6.0 KB static data + 8 KB reserved stack + 0.5 KB heap, all in RAM1; worst-case stack estimate 5,784 B of 8,192 B (71 %) | Ample; RAM2 unused |
| CPU | Cortex-M4 at 48 MHz (Cortex-M0+ core unused) | One sample and a few frames per minute | No constraint |
| Radio payload | 35-byte observation plaintext in a 51-byte frame (T/RH with the minute summary); the draft-5 catalog allows up to 78 B in a 94-byte frame | Temperature and humidity only | No longer the limit: every catalog field fits in one frame (section below) |

Sources: `firmware/board/nucleo-wl55jc/STM32WL55JCIX_FLASH.ld` (shared by every NUCLEO project; FLASH 64K, RAM1/RAM2 32K each, heap 0x200, stack 0x2000 since the stack work below; 0x800 before),
`App/flash_layout.h`, `firmware/common/ws_frame.h` (`WS_HEADER_LEN 8`, `WS_TAG_LEN 8`), `firmware/common/ws_obs.h` and
`App/node_fields.h` (`WS_OBS_PLAIN_MAX` = 35 for T/RH with the minute summary).

The build enforces a budget: `make` prints `flash budget: N of 65536 B` and fails above
`FLASH_BUDGET_PCT` (default 90 %) of the application region (`firmware/stage0-node/Makefile`).

The 15-s T/RH sampling with a minute summary (catalog fields 21–25, `ws_th_*` in `firmware/stage0.c`)
is in the build: a 35 B plaintext, 51 B on air (25.7 ms at SF7, 534.5 ms at SF12), 56-byte journal
slots.

**Efficiency review, unreleased (2026-10-14), TX 54,832 → 51,080 B (−3,752 B):** AES without the
decrypt direction (`MBEDTLS_BLOCK_CIPHER_NO_DECRYPT`, −2,208 B; CCM and the key check value only
encrypt), 128-bit keys only (−272 B, AES context 272 → 176 B on the stack), bitwise CRCs instead of
GCC 15's lookup tables (`-fno-optimize-crc` on `node_store.o` and `stage0.o`, −752 B), a 32-bit
minute mean (−208 B), boot self-test vectors as byte arrays (−184 B), the field catalog as one
X-macro (−88 B), the build ID computed at build time (−56 B) and smaller items. The TX reply
buffer is 33 B instead of 255 B (RAM −224 B). Stack bound: TX 6,056 B (74 %), RX 2,276 B (28 %).

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

Draft 5 (release `bc5e6ede429c`): the observation encoder and catalog table,
`firmware/common/ws_obs.c`, link 676 B into the TX image (508 B code + 168 B table; from the linker
map). Against the previous release `45f43e78fe91` the TX image grew by 856 B (52,896 → 53,752 B) and
the RX image by 112 B (31,584 → 31,696 B). The encoder is most of the TX growth; the rest is the
larger health report and the new self-test, less the removed draft-4 packer (not broken down).

## Stack

Measured 2026-10-14 on release `bc5e6ede429c` (draft 5).

| | TX | RX |
|---|---:|---:|
| Worst-case estimate (`make stack`, `tools/stack_report.py`) | 6,528 B (80 % of 8,192 B) | 2,212 B (27 %) |
| Deepest direct chain from `main` | 1,280 B (boot self-test through Mbed TLS CCM) | 276 B (`fault_report` through the trace printf) |
| Deepest callback chain | 1,256 B (`on_line`, console commands) | 428 B (`process`) |
| RAM the stack can actually grow into before it meets static data | 28,136 B | 29,568 B |

How the estimate works: GCC writes each function's frame size and its direct calls
(`-fcallgraph-info=su`, `.ci` files beside the objects). The script adds the deepest chain from
`main`, two levels of pointer calls (sequencer task, then driver callback), and two nested
interrupts, each with one pointer call, plus 32 B per exception frame. Any function whose address
is taken counts as a possible pointer target. Prebuilt newlib/libgcc functions (`memcpy`,
`memset`, the 64-bit divides) have no call-graph data and count 0 B; they are leaf functions
with small frames. Unbounded recursion or a variable-size frame fails the check. CI runs it on
both roles.

Changes made for it:

- The linker's reserved stack (`_Min_Stack_Size`) went from 2 KB to 8 KB. The old 2 KB was below
  the TX estimate. Nothing checks the real stack against this reservation at run time, but the
  linker now refuses to link if static data plus 8 KB no longer fits.
- Our recursion `send_current` ↔ `next_item` (now `App/tx_exchange.c`) became a loop.
- Mbed TLS's generic cipher layer is gone (`MBEDTLS_CIPHER_C` off): CCM now calls AES through the
  smaller block-cipher layer. That removed a recursion cycle in the call graph, all `malloc`/`free`
  from the TX image, and 1.7 KB of flash.
- `sample()` keeps its 104-byte observation record (`ws_obs_t`) in static memory, not on the stack.
  It is part of the deepest callback chain, which the estimate counts four times (about 416 B).
  With the record on the stack the TX estimate was 83 %.
- Run-time check: the stack is filled with a pattern at start-up (`App/stackmon.c`), and
  `stack_peak` (TX `#counts`, RX `#alive`) reports the deepest byte ever overwritten. A field
  value near the 8 KB reservation would mean the estimate is wrong.

## Blocking waits

Rule: the firmware is interrupt/event driven. After boot nothing may busy-wait or block for
milliseconds; only short hardware handshakes with a stated bound are allowed. `make waits`
(`tools/blocking_report.py`, CI on both roles) checks this from the same GCC call graphs as the
stack bound.

- **Run-time roots**: every interrupt handler (`*_IRQHandler`, `*_Handler`, not `Reset_Handler`),
  every linked address-taken function (sequencer tasks, timer and radio callbacks, driver tables,
  the console line handler: a pointer call can reach any of them), and `MX_SubGHz_Phy_Process`, the
  body of `main`'s forever loop. Exception: a function whose address is taken *only* in the
  SubGHz_Phy `Radio` table is followed as a direct call from each function that calls
  `Radio.Slot(...)` in the compiled sources; any other use of the slot or of `Radio` keeps it a root.
- **Boot code**: what `main` reaches by direct calls and no root reaches. Waits there are allowed
  and listed (clock set-up, LSE start-up, IWDG init, radio reset).
- **Tables in the tool**, each entry with its reason and source reference:
  - `BANNED`: `HAL_Delay`, `TIMER_IF_DelayMs`, blocking HAL I2C/UART/SPI/DMA/ADC transfers and
    polls, `vcom_Trace`, `UTIL_SEQ_WaitEvt`, `RadioIsChannelFree`, `RFW_PollRxBytes`. Reachable at
    run time: **fail**.
  - `ALLOWED`: flash program/erase (CPU stalls on the single bank anyway; page erase 24.5 ms max),
    SUBGHZ BUSY-line and SPI byte handshakes (counter-bounded, ~100 ms cap, µs in practice), RTC
    sub-second double read and init/sync flags (≤ 2 RTCCLK), UART TEACK/REACK after enable, the
    boot RCC/IWDG waits. Each states its bound.
  - `CLOCKS` (`HAL_GetTick`, `UTIL_TIMER_GetCurrentTime`, `UTIL_TIMER_GetElapsedTime`): every
    run-time function that calls one must be in a table (`TIMESTAMP` if it only reads the time).
    An unclassified caller **fails**: this is how a new HAL timeout loop or hand-written delay is
    caught.
  - `TEST_ONLY` (`fault_test`, `test_hang`): deliberate hang/crash bench commands; waits reachable
    only through them are listed, not failures.
- **Limits**: only calls are visible. An inline register poll (`while (!(REG & FLAG));`) or a
  counter loop GCC inlined from a static function is not seen, so `ALLOWED` names the public
  functions holding such loops (e.g. `vcom_ReceiveInit`, whose BUSY/REACK loops have no counter),
  and new inline polls must be caught in review. Prebuilt newlib/libgcc is assumed not to wait.

Adding code: a new `HAL_GetTick` reader needs a `TIMESTAMP` entry (`'file.c:function'` for a static);
a new hardware wait needs an `ALLOWED` entry with its worst-case bound from the datasheet/RM.

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
| Multi-sensor payload (protocol draft 5) | **Done**: +856 B TX against release `45f43e78fe91` | `ws_obs.c` is 676 B; the decoder is on the gateway |
| **Total** | **about 18–33 KB** | **Does not fit in the 11.5 KB left** |

## Requirement (Clint, 2026-10-13)

The STM32WL55JC stays. The firmware must **fully support the final station** (all sensor types,
power modules, 30-day buffer, low power) **with room for expansion**. Working targets until the
final design is sized:

- **Headroom:** the final TX image uses at most **75 %** of its application region, leaving at least
  25 % for later sensors and fixes. Until flash layout v2, every build also stays under the 90 %
  guard in the Makefile.
- **Watch:** every `RELEASES.md` entry records the `.bin` sizes; review this file at each stage gate
  and whenever a release grows by more than 2 KB.
- **Layout v2 before the region is outgrown:** key and counter pages move to the top of flash so they
  never move again, the code/journal boundary becomes one shared constant, and a one-time migration
  carries the counter and epoch across (`docs/failure-modes.md`, §10 open issues: code space for the
  final station).

## The plan that makes it fit

1. **Flash layout v2 with H11.** The 30-day buffer moves to SPI NOR, which frees most of the 186 KB
   internal journal. The application region can then grow to 128 KB or more. **Constraint:** the
   key and the transmission counter live in the node-state pages. A layout change must carry the
   counter and epoch across (or the board gets a new key); otherwise it repeats AES-CCM nonces
   (`docs/runbook-moving-boards.md`).
2. **LTO as a measured reserve** (−6.6 KB on TX) if a feature must land before layout v2.
3. **Budget check** in every build (above), and a size line in every `RELEASES.md` entry.
4. **Module split after H01** (`docs/firmware-review-2026-10-13.md` §4–5): sensors become
   drivers behind one interface instead of edits to `app_tx.c`.

## Radio payload

Draft 5 carries a fixed 16 bytes per frame (8-byte authenticated header, 8-byte tag) around the
plaintext; draft 4 carried 32. Air time per frame from the firmware's formula (`ws_lora_airtime_ms()` in
`firmware/common/ws_policy.c`: 500 kHz, CR 4/5, 8-symbol preamble, explicit header, CRC on; the firmware rounds up
to whole milliseconds):

| Frame | Plaintext | Frame | SF7 | SF9 | SF10 | SF12 |
|---|---:|---:|---:|---:|---:|---:|
| ACK / NACK | 17 B | 33 B | 18.0 ms | 61.7 ms | 113.2 ms | 411.6 ms |
| Observation, T/RH with the minute summary (Stage 0, today) | 35 B | 51 B | 25.7 ms | 82.2 ms | 154.1 ms | 534.5 ms |
| Health report (DIAG) | 32 B | 48 B | 24.4 ms | 77.1 ms | 143.9 ms | 493.6 ms |
| Observation, Core weather set (design §2) | 40 B | 56 B | 26.9 ms | 87.3 ms | 164.4 ms | 575.5 ms |
| Observation, full proof-of-concept build | 62 B | 78 B | 34.6 ms | 112.9 ms | 205.3 ms | 698.4 ms |
| Observation, every catalog field | 78 B | 94 B | 41.0 ms | 133.4 ms | 236.0 ms | 821.2 ms |
| (Draft 4, every kind) | 24 B | 56 B | 26.9 ms | 87.3 ms | 164.4 ms | 575.5 ms |

- **One frame carries every field.** The largest possible observation (85 B) is still one frame,
  so more sensors never need a second frame or a second ACK window.
- **The airtime cap sets the backlog drain.** The firmware counts one exchange as observation +
  ACK air time + 300 ms (`exchange_ms`). For the T/RH build that is 22 + 18 + 300 = 340 ms at SF7
  (the 5 s NORMAL cap allows 14 exchanges, so the NORMAL limit of 5 binds) and 453 + 412 + 300 =
  1,165 ms at SF12 (4 exchanges). With the full PoC frame at SF12: 699 + 412 + 300 = 1,411 ms, so 3.
- **Energy follows air time.** Per-frame energy figures and SF choices:
  `docs/radio-energy-policy.md` §3.
