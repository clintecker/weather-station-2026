# Firmware event model (stage0-node, both roles)

Decision 2026-10-15 (Clint): the firmware is interrupt and event driven throughout. Nothing waits
for time or polls a peripheral at run time, and we can show how everything operates at all times.
This page is the reference; the code points here.

## How the firmware runs

There is no RTOS. Three kinds of code run:

| Kind | Examples | Runs until |
|---|---|---|
| Interrupt handler | radio (`SUBGHZ_Radio`), RTC alarm (all `UTIL_TIMER` callbacks), I2C2, USART2, DMA | it returns; it only copies data and posts an event or sets a task |
| Sequencer task (main loop) | `process` (radio events), `sample`, `sensor_task`, `console_task`, `check` (watchdog) | it returns; one task at a time, never re-entered |
| Idle | `UTIL_SEQ_Idle` → low-power mode | the next interrupt |

A task never waits for time. When something must happen later, the task starts a timer and returns;
the timer's interrupt posts the next task.

## TX: the minute's exchange (`App/app_tx.c`)

Sampling: the 15-s periodic timer posts `sample`, which starts an SHT45 measurement and returns.
The measurement is a chain of interrupts (`App/sensor.c`): command write (I2C interrupt mode) →
10 ms timer → reply read → `sensor_task`, which hands the result to `sampled()`. A guard timer
(20 ms) ends any transfer that never completes (`rc=-6`); after any failure the stuck-bus recovery
runs one pin step per 1 ms timer tick (`ws_i2c_recover_step`, same waveform as before). Every 4th
sample journals the minute's report and starts the exchange.

The exchange is one explicit state machine. Every state is left by an event that is certain to come:

| State | Left by | Next |
|---|---|---|
| `idle` | the 4th sample's report | `sending` (first frame, no gap) |
| `gap` | gap timer (50 ms) | `sending` (next frame) or `diag-sending` (health report), or `idle` if nothing could be sent |
| `sending` | radio TxDone | `ack-wait` (receive window opens, 2 s) |
|  | radio TxTimeout (3 s, the radio's own timer) | `gap` or `idle` (drain stops) |
| `ack-wait` | RxDone, the authentic reply to this frame | `gap` (next frame) or end of exchange |
|  | RxDone, anything else (foreign, forged, another frame's ACK) | `ack-wait` for the rest of the window, or no reply if < 50 ms is left |
|  | RxTimeout (window over) / RxError | no reply: drain stops, end of exchange |
| `diag-sending` | TxDone or TxTimeout | `idle` (radio sleeps) |

End of exchange: link state updated, then `gap` → health report if one is due, else `idle`.
Any (state, event) pair not in this table is counted (`unexpected=` on `#timing`), printed as
`#error unexpected event=… state=…`, and otherwise ignored. Events are bits, so two arriving before
`process` runs are both handled. The watchdog check also requires that a busy exchange ends
within 30 s.

Other timers: a commanded reboot (WIPE, PROVISION) stops sampling and resets from a 200 ms timer, so
the console can send the reply first; a boot storage failure retries by a reset after 10 minutes.

## RX (`App/app_rx.c`)

Always in continuous receive. Radio interrupts post bits (`EV_RX`, `EV_RX_CRC`, `EV_RX_HDR`,
`EV_TX_DONE`, `EV_TX_TIMEOUT`); `process` forwards frames, logs failed receptions with every byte the
radio kept (`#rx crc … data=`, `#rx hdr rssi=`), and returns to listening. A host ACK line goes on air
from the console task; its TxDone/TxTimeout returns the radio to listening.

## What still stalls the CPU (hardware, not our choice)

| Stall | Bound | When it happens |
|---|---|---|
| Flash page erase | ~22 ms typical (STM32WL55 datasheet, t_ERASE); the CPU cannot fetch from flash meanwhile | starting a journal page (~every 28 readings), meta-page compaction, WIPE. Always with the radio idle: before an exchange, or between frames (checked by the host harness) |
| Flash double-word program | ~82 µs (datasheet t_PROG) | journal append, ACK mark, counter reservation; radio idle |
| Radio SPI / BUSY handshakes in ST's driver | microseconds, loop-counter bounded | every radio command |
| RTC sub-second read loop, UART start-up flags | a few cycles; boot only for the UART | timer reads |

These are measured on the board, not assumed: `#timing` reports `erase_peak_us`, `prog_peak_us`, the
longest task and the longest interrupt handler (DWT cycle counter, `App/busymon.h`).

## How we know

| Check | What it proves | Where |
|---|---|---|
| Host state-machine harness | The real `app_tx.c` runs over a simulated clock, timers, sequencer, radio and flash: gaps are timers, every state ends, a 3 h randomized link (lost ACKs, NACKs, junk frames, radio timeouts, send failures) produces no unexpected event, keeps the watchdog check healthy, and never writes flash while the radio transmits or receives | `firmware/host/tx_harness.c`, `tests/test_tx_machine.py` |
| Build-time wait check | No blocking call (`HAL_Delay`, blocking HAL I2C/UART/SPI, …) is reachable from any interrupt handler or task in the linked image; every timeout-loop user is classified | `tools/blocking_report.py`, `make ROLE=… waits`, CI |
| Run-time timing | Peaks of every task, handler and flash stall since boot, on the console and RX `#alive` (stored by the gateway) | `App/busymon.c`, `#timing`, `#alive` |
| Console never blocks | A line that does not fit the 2 KB output queue is dropped and counted (`trace_drops`) | `sys_app.h` `APP_PRINTF` |

The only deliberate endless loops are the bench commands `TEST-HANG` (proves the watchdog) and
`TEST-FAULT` (proves crash recording).
