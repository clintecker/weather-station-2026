# Firmware event model (stage0-node, both roles)

Decision 2026-10-15 (Clint): the firmware is interrupt and event driven throughout. Nothing waits
for time or polls a peripheral at run time, and we can show how everything operates at all times.
This page is the reference; the code points here. Reviewed the same day by five independent
reviewers; their findings are folded in below.

## How the firmware runs

There is no RTOS. Three kinds of code run:

| Kind | Examples | Runs until |
|---|---|---|
| Interrupt handler | radio (`SUBGHZ_Radio`, priority 0), RTC alarm (all `UTIL_TIMER` callbacks, priority 0, run with interrupts masked), I2C2, USART2, DMA (priority 2) | it returns. It copies data, starts the next hardware step or timer (the sensor chain), and posts an event or task. It never formats console lines (the RX `#alive` report is printed from the main loop) |
| Sequencer task (main loop) | `process` (radio events), `sample`, `sensor_task`, `console_task`, `check` (watchdog) | it returns; one task at a time, never re-entered |
| Idle | `UTIL_SEQ_Idle` → low-power mode | the next interrupt |

A task never waits for time. When something must happen later, the task starts a timer and returns;
the timer's interrupt posts the next task.

ST's timer server counts 1/1024 s RTC ticks, rounds a period down to whole ticks and makes it at
least 3 ticks (`timer_if.c`); a timer can also start up to a tick late. Periods below are what the
code asks for. `HAL_GetTick()` also counts those ticks, not milliseconds, so the firmware measures
time from `SysTimeGetMcuTime()` instead.

## TX: the minute's exchange (`App/app_tx.c`)

Sampling: the 15-s periodic timer posts `sample`, which starts an SHT45 measurement and returns.
The measurement is a chain of interrupts (`App/sensor.c`): command write (I2C interrupt mode) →
11 ms timer (≥ 9.8 ms after rounding; the SHT45 needs at most 8.3 ms) → reply read → `sensor_task`,
which hands the result to `sampled()`. A 30 ms guard timer ends any transfer that never completes
(`rc=-6`); it is longer than a flash page erase, which delays the I2C interrupt. After any failure
the stuck-bus recovery runs one pin step per timer tick (~2-3 ms; `ws_i2c_recover_step`, same
waveform as before), ~15-70 ms in all. Every 4th sample journals the minute's report and starts the
exchange.

The exchange is one explicit state machine. Every state is left by an event that is certain to come:

| State | Left by | Next |
|---|---|---|
| `idle` | the 4th sample's report | `sending` (first frame, no gap) |
| `gap` | gap timer (50 ms) | `sending` (next frame) or `diag-sending` (health report). A local send failure (journal read, seal, radio busy) moves to the next item after another gap; a refused counter reservation ends the exchange (`idle`) |
| `sending` | radio TxDone | `ack-wait`: the firmware's 2 s `ack_timer` starts, the radio listens with no driver timeout (`Radio.Rx(0)`) |
|  | TxTimeout (3 s, a software timer in ST's radio driver) | radio put in standby (the driver leaves it transmitting); drain stops: `gap` if a health report is due, else `idle` |
| `ack-wait` | RxDone, the authentic reply to this frame | `ack_timer` stopped; `gap` (next frame) or end of exchange |
|  | RxDone, anything else (foreign, forged, another frame's ACK), RxError (payload CRC failed), RxTimeout (ST's radio.c reports a header error so) | listen again (`Radio.Rx(0)`), same window |
|  | `ack_timer` (the window is over) | radio put in standby; no reply: drain stops, end of exchange |
| `diag-sending` | TxDone, or TxTimeout (radio put in standby) | `idle` (radio sleeps) |

Why the window is the firmware's own timer: ST's driver window (`RxTimeoutTimer`) is not stopped by
a CRC error and its timeout leaves the radio receiving, which produced stray timeouts in later
states and let the next flash write overlap a listening radio (reviews, 2026-10-15). With
`Radio.Rx(0)` no driver timer is armed; the chip's own single-reception timeout is ~65 s.

ST's HAL raises RxDone for a packet whose payload CRC failed and then RxError, in the same interrupt.
The RxDone callback recognises it (`ws_radio_take_crc_error`, the HAL's CRC flag) and leaves it to
RxError, in both roles.

End of exchange: link state updated, then `gap` → health report if one is due, else `idle`.
Any (state, event) pair not in this table is counted (`unexpected=` on `#timing`), printed as
`#error unexpected event=… state=…`, and otherwise ignored. Events are bits, so two arriving before
`process` runs are both handled. The watchdog check also requires a busy exchange to end within its
worst case: (frames + 1) × (3 s transmit timeout + 2 s window + 50 ms gap) + 5 s.

Console commands that write flash (WIPE, PROVISION, TEST-FLASH-STORM) are refused with
`#error busy …; retry` during an exchange or a pending reboot. A commanded reboot (WIPE, PROVISION)
stops sampling and resets from a 200 ms timer (created once at boot), so the console can send the
reply first; a second one meanwhile is refused. TEST-FLASH-STORM stops sampling, so no exchange
starts. A storage-init or epoch-reservation failure at boot (self-test passed) retries by a reset
after 10 minutes.

## RX (`App/app_rx.c`)

Always in continuous receive. Radio interrupts post bits (`EV_RX`, `EV_RX_CRC`, `EV_RX_HDR`,
`EV_TX_DONE`, `EV_TX_TIMEOUT`); `process` forwards frames and logs failed receptions with every byte
the radio kept (`#rx crc … data=`, `#rx hdr rssi=`). The radio stays in continuous receive through
both failures (ST's radio.c), so nothing re-arms it. One capture waits for `process` at a time;
failures meanwhile are counted (`fault_overruns` on `#alive`), as is a forwarded frame replaced
before it was printed. A host ACK line goes on air from the console task; its TxDone/TxTimeout
returns the radio to listening. The 60 s `#alive` timer only asks for the report; `process` prints it.

## What still stalls the CPU (hardware, not our choice)

| Stall | Bound | When it happens |
|---|---|---|
| Flash page erase | STM32WL55 datasheet (DS13293) t_ERASE: ~22 ms typical, ~24.5 ms max (from the datasheet as recalled in review; to be checked against the PDF and measured). The CPU cannot fetch from flash meanwhile, so interrupts start late by up to that much | starting a journal page (every 36 readings), meta-page compaction, WIPE, PROVISION, TEST-FLASH-STORM. Always with the radio idle: journal and counter writes happen before an exchange or between frames, and the flash-writing commands are refused during one (checked by the host harness) |
| Flash double-word program | DS13293 t_PROG: ~82 µs typical, ~91 µs max (same caveat) | journal append, ACK mark, counter reservation; radio idle |
| Radio SPI / BUSY handshakes in ST's driver | bounded by ST's loop counters (`stm32wlxx_hal_subghz.c`); microseconds per command, ~3.5 ms on wake with calibration (`tools/blocking_report.py` table) | every radio command; inside `task_peak_us` / `isr_peak_us` |
| RTC sub-second double read, UART start-up flags | `timer_if.c` reads the sub-second register until two reads agree (it changes every 30.5 µs); UART TEACK/REACK at start | timer reads; console start |

These can be measured on the board: `#timing` reports `erase_peak_us`, `prog_peak_us`, the longest
task and the longest interrupt handler (DWT cycle counter, `App/busymon.h`). An interrupt's late start
during an erase is not in `isr_peak_us` (that times how long a handler runs). No measured values are
recorded yet; they come with the reflash.

## How we know

| Check | What it proves | Where |
|---|---|---|
| Host state-machine harness | The real `app_tx.c` over a simulated clock, timers, sequencer, flash and a radio that follows ST's driver (CRC failure = RxDone + RxError; driver timeouts leave the radio transmitting or receiving; a simulated SHT45). Gaps are timers; every state ends; damaged packets do not end the window early; flash commands wait for the exchange; a 3 h randomized link (lost ACKs, NACKs, junk, CRC and header failures, transmit timeouts, send failures) gives no unexpected event, keeps the watchdog check healthy, and never writes flash while the radio transmits or receives | `firmware/host/tx_harness.c`, `tests/test_tx_machine.py` |
| Host sensor-driver harness | The real `sensor.c` over ST-rounded timers and a simulated I2C bus and SHT45: one done() per measurement with the documented code for success, NACKs, bad CRC, hangs and a busy bus; recovery clocks a held SDA free or reports it stuck; a completion at the guard's instant cannot overwrite the timeout; the read never comes before 9 ms | `firmware/host/sensor_harness.c`, `tests/test_sensor_machine.py` |
| Build-time wait check | No blocking call (`HAL_Delay`, blocking HAL I2C/UART/SPI, …) is reachable from any interrupt handler or task in the linked image; every timeout-loop user is classified | `tools/blocking_report.py`, `make ROLE=… waits`, CI |
| Run-time timing | TX `#timing`: peaks of tasks, handlers and flash stalls since boot. RX `#alive`: tasks and handlers (stored by the gateway). SysTick, NMI and HardFault are not timed | `App/busymon.c` |
| Console never blocks | A line that does not fit the 2 KB output queue is dropped and counted (`trace_drops`). Lines are kept under the 640-byte line buffer, which would cut a longer one uncounted | `sys_app.h` `APP_PRINTF` |

The only deliberate hangs are bench commands: TEST-HANG (an endless loop; proves the watchdog) and
TEST-FAULT (waits 50 ms for the console, then faults; the fault handler resets). `Error_Handler`
(an init failure) also loops forever, with interrupts off; the watchdog ends it only if it was
already started.
