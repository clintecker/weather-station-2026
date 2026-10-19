# Firmware event model (both board roles)

This page describes how the firmware in `firmware/stage0-node` runs on both boards. The
transmitter (TX) is the station node with the sensor. The receiver (RX) is the bridge on the
gateway's USB cable. The code comments point to this page.

On 2026-10-15 Clint decided that the firmware is interrupt and event driven throughout. At run
time, no code waits for time or polls a peripheral. Five independent reviewers checked this page
the same day. Their findings are included below.

## How the firmware runs

The firmware has no real-time operating system (RTOS). Three kinds of code run:

| Kind | Examples | Runs until |
|---|---|---|
| Interrupt handler | radio (`SUBGHZ_Radio`, priority 0), RTC alarm (all `UTIL_TIMER` callbacks, priority 0, run with interrupts masked), I2C2, USART2, direct memory access (DMA) (priority 2) | it returns. A handler copies data, starts the next hardware step or timer, and posts an event or a task. A handler never formats console lines. The main loop prints the RX `#alive` report |
| Sequencer task (main loop) | `process` (radio events), `sample`, `module_tick`, `bus_task` (I2C), `console_task`, `check` (watchdog) | it returns. One task runs at a time. A task is never re-entered |
| Idle | `UTIL_SEQ_Idle` → low-power mode | the next interrupt |

A task never waits for time. When something must happen later, the task starts a timer and
returns. The timer's interrupt then posts the next task.

```mermaid
flowchart LR
  HW["Hardware event: radio, RTC alarm, I2C, UART"] --> ISR["Interrupt handler"]
  ISR -->|"sets an event bit (events_post)"| BITS["Pending event bits"]
  ISR -->|"posts the task (UTIL_SEQ_SetTask)"| SEQ["Sequencer, main loop"]
  BITS --> SEQ
  SEQ -->|"runs one task"| TASK["Task: process, sample, module_tick, bus_task, console_task, check"]
  TASK -->|"takes and clears the bits (events_take)"| BITS
  TASK -->|"starts a timer, then returns"| TIMER["UTIL_TIMER on the RTC alarm"]
  TIMER -->|"alarm interrupt"| ISR
  SEQ -->|"no task pending"| IDLE["UTIL_SEQ_Idle, low-power mode"]
  IDLE -->|"next interrupt"| ISR
```

Events are bits (`App/events.h`). Two events that arrive before `process` runs are both handled.

ST's timer server counts real-time clock (RTC) ticks of 1/1024 s. It rounds a period down to whole
ticks and makes it at least 3 ticks (`timer_if.c`). A timer can also start up to one tick late.
The periods on this page are the values that the code requests. `HAL_GetTick()` also counts these
ticks, not milliseconds. The firmware therefore measures time with `SysTimeGetMcuTime()`.

## TX: sampling (`App/app_tx.c`, `App/wsmp_host.c`, `App/i2c_bus.c`)

Two periodic timers drive the sampling. Neither task waits for a measurement:

- A 250 ms module timer posts the `module_tick` task (`CFG_SEQ_Task_Sensor`). This task calls
  `wsmp_host_tick()`. The station host gives each local module one tick and then reads its probe
  result.
- A 15-second sample timer posts the `sample` task. `sample` counts the ticks. The 4th tick latches
  every module and makes the minute's report.

The `sample` task also runs once at boot. The first report therefore comes at 45,000 ms. The report
uses the snapshots that the latch froze. It does not wait for an I2C transfer.

Each module does at most one bus step per tick. The temperature and humidity modules
(`App/mod_th.c`) start a sample every 15 s. The SHT45 module writes the measure command on one tick.
It reads the reply on a later tick, at least 250 ms after the command. The SHT45 needs at most
8.3 ms.

The modules share one I2C bus (`App/i2c_bus.c`). A module submits a transfer. The bus queues the
transfers and runs one at a time, in submission order:

```mermaid
stateDiagram-v2
  [*] --> S_IDLE
  S_IDLE --> S_XFER : a transfer is queued, it starts in I2C interrupt mode, guard timer starts
  S_IDLE --> S_RECOVER : a recovery-only request is queued
  S_XFER --> S_DONE : transfer complete, guard stops
  S_XFER --> S_DONE : I2C error, HAL refusal or 30 ms guard timeout
  S_DONE --> S_IDLE : bus_task, success or a failure with SDA high, i2c_bus_done with the code
  S_DONE --> S_RECOVER : bus_task, timeout, HAL refusal or SDA low
  S_RECOVER --> S_RECOVER : one pin step per timer tick
  S_RECOVER --> S_RECOVERED : recovery finished
  S_RECOVERED --> S_IDLE : bus_task, I2C re-initialised, i2c_bus_done with the code
```

- The 30 ms guard timer ends a transfer that never completes (`rc=-6`). The guard is longer than a
  flash page erase, because an erase delays the I2C interrupt.
- The stuck-bus recovery runs only when the bus can be stuck. These are a timeout, a HAL refusal,
  or SDA low after a failure. An address NACK from an absent sensor costs no recovery.
- A module can also ask for the recovery alone. The temperature and humidity modules do this after
  a bad CRC.
- The recovery (`ws_i2c_recover_step`) runs one pin step per timer tick. One tick is about 2–3 ms.
  The whole recovery takes about 15–70 ms.
- `bus_task` (`CFG_SEQ_Task_I2c`) gives the code to `i2c_bus_done()`. `App/wsmp_local.c` passes it
  to the module that owns the transfer. The bus then starts the next queued transfer.
- A module turns a failed sample into its probe result. An address NACK means absent. Any other
  failure is a bus fault.

`minute_report()` in `App/app_tx.c` journals the report in flash. If the transmit policy allows a
send this minute, it then starts the exchange.

## TX: flash is written only with the radio idle

The firmware writes flash only while the radio is idle, without exception (2026-10-15). The
previous minute's exchange can still run when a report is ready. The firmware then keeps the
encoded reading in RAM and does not journal it:

```mermaid
flowchart TD
  R["Minute report ready"] --> B{"Exchange still running?"}
  B -->|"no"| J["Journal the reading, then start the exchange if the policy allows"]
  B -->|"yes"| H{"Two readings already held?"}
  H -->|"no"| K["Hold the reading in RAM. Print #busy and journal=held on #sample"]
  H -->|"yes"| D["Drop the oldest held reading, count held_lost, print #error held-lost, hold the newest"]
  K --> W["Exchange ends: radio_idle calls held_flush"]
  D --> W
  W --> F["Journal every held reading first. Print #held journaled seq= rc= pending="]
  F --> N["The next minute sends them as backlog"]
```

A normal exchange ends well within its minute. Only a hung radio holds a reading. The exchange
then outlasts its bound (at most 116 s). The independent watchdog (IWDG) resets the board about
8 s later. At most two readings can be waiting, and the firmware holds
two.

A watchdog reset for a stuck exchange loses no held reading. The watchdog check first stops the
radio and journals the held readings (see the exchange bound below). Other resets (power loss, a
fault) lose the held readings. Those sequence numbers then never arrive, and the gateway sees the
gap.

## TX: the minute's exchange (`App/tx_exchange.c`)

The exchange is one explicit state machine. An event that is certain to come ends every state.
The events are the radio's TxDone and TxTimeout, the gap timer and the acknowledgement (ACK)
window timer.

```mermaid
stateDiagram-v2
  [*] --> idle
  idle --> gap : minute report starts the exchange
  gap --> sending : gap timer, next frame sent
  gap --> gap : gap timer, local send failure, next item after another gap
  gap --> idle : gap timer, counter reservation refused
  gap --> idle : gap timer, last item failed locally, no report due
  gap --> diag_sending : gap timer, health report sent
  gap --> idle : gap timer, health report not sent
  sending --> ack_wait : TxDone, ack_timer starts, Radio.Rx(0)
  sending --> gap : TxTimeout, standby, drain stops, health report due
  sending --> idle : TxTimeout, standby, drain stops, no report due
  ack_wait --> ack_wait : other packet, RxError or RxTimeout, listen again
  ack_wait --> gap : authentic reply to this frame, next frame or health report
  ack_wait --> idle : authentic reply, last frame, no report due
  ack_wait --> gap : ack_timer ends the window, standby, next frame or health report
  ack_wait --> idle : ack_timer ends the window, last frame, no report due
  diag_sending --> idle : TxDone or TxTimeout, radio sleeps
```

The code names the states `idle`, `gap`, `sending`, `ack-wait` and `diag-sending`. The diagram
writes `diag_sending` and `ack_wait` because Mermaid state names cannot contain a hyphen. The table
gives the detail of each transition:

| State | Left by | Next |
|---|---|---|
| `idle` | the 4th sample's report | `gap`. The first frame also waits 50 ms. The radio can have gone to sleep moments earlier and needs time to enter sleep before the firmware wakes it. ST's `RadioSleep` waited 2 ms instead |
| `gap` | gap timer (50 ms) | `sending` (next frame) or `diag-sending` (health report). A local send failure (journal read, seal, radio busy) moves to the next item after another gap. A refused counter reservation ends the exchange (`idle`) |
| `sending` | radio TxDone | `ack-wait`. The firmware's 2 s `ack_timer` starts. The radio listens with no driver timeout (`Radio.Rx(0)`) |
|  | TxTimeout (3 s, a software timer in ST's radio driver) | The firmware puts the radio in standby, because the driver leaves it transmitting. The drain stops: `gap` if a health report is due, else `idle` |
| `ack-wait` | RxDone with the authentic reply to this frame | `ack_timer` stops. Then `gap` (next frame) or end of exchange |
|  | RxDone with any other packet (foreign, forged, another frame's ACK), RxError (payload CRC failed), RxTimeout (ST's `radio.c` reports a header error this way) | The radio listens again (`Radio.Rx(0)`) in the same window |
|  | `ack_timer` (the window is over) | The firmware puts the radio in standby. No reply: the drain ends after one more frame, or at once after a second miss in a row. Then `gap` or end of exchange |
| `diag-sending` | TxDone, or TxTimeout (the firmware puts the radio in standby) | `idle` (radio sleeps) |

The firmware uses its own timer for the ACK window for two reasons. A cyclic redundancy check (CRC)
error does not stop ST's driver window (`RxTimeoutTimer`). The driver's timeout also leaves the
radio receiving. These faults caused stray timeouts in later states. They also let the next flash
write overlap a listening radio (reviews, 2026-10-15). With `Radio.Rx(0)` the driver arms no timer.
The chip's own single-reception timeout is about 65 s.

ST's HAL raises RxDone for a packet whose payload CRC failed. It then raises RxError in the same
interrupt. In both roles, the RxDone callback recognises such a packet with
`ws_radio_take_crc_error` (the HAL's CRC flag). The callback leaves the packet to RxError.

End of exchange: the firmware updates the link state. It then goes to `gap` and the health report
if one is due, else to `idle`.

The firmware drops two races without counting them:

- a TxTimeout that fires in the same pass as its TxDone. The frame left.
- an ack-end that the timer posted while the firmware handled the reply that closed the window.

The firmware counts every other (state, event) pair that the table does not list (`unexpected=` on
`#timing`). It prints `#error unexpected event=… state=…` and otherwise ignores the event.

### Exchange bound

The watchdog check requires a busy exchange to end within its worst case:

(frames + 1) × (3 s transmit timeout + 2 s window + 50 ms gap) + 5 s

When the exchange passes this bound, the check does these steps:

1. It stops sampling.
2. It stops the gap and ACK timers, puts the radio in standby and ends the exchange.
3. It journals any held reading, because the radio is now idle.
4. It keeps failing, so the watchdog resets the board (`#watchdog radio exchange stuck; …`).

### Console commands during an exchange

The console refuses the commands that write flash (WIPE, PROVISION, TEST-FLASH-STORM) during an
exchange or a pending reboot. The reply is `#error busy …; retry`.

A commanded reboot (WIPE, PROVISION) stops sampling and resets from a 200 ms timer. The firmware
creates this timer once at boot. The delay lets the console send the reply first. The console
refuses a second reboot command while one is pending.

TEST-FLASH-STORM is a bench command. A field build does not include it. It writes at most 24 000
journal slots per boot, in about 30 s. This is far from wearing out the journal. It stops sampling,
so no exchange starts.

A storage-init or epoch-reservation failure at boot (with the self-test passed) causes a retry.
The firmware resets the board after 10 minutes.

## RX (`App/app_rx.c`)

The RX is always in continuous receive. Radio interrupts post event bits (`EV_RX`, `EV_RX_CRC`,
`EV_RX_HDR`, `EV_TX_DONE`, `EV_TX_TIMEOUT`). The `process` task forwards frames to the gateway. It
also logs failed receptions with every byte that the radio kept (`#rx crc … data=`,
`#rx hdr rssi=`).

```mermaid
sequenceDiagram
  participant Node as TX node
  participant Radio as RX radio
  participant ISR as RX radio interrupt
  participant Proc as RX process task
  participant Con as RX console task
  participant GW as Gateway on USB
  Node->>Radio: frame
  Radio->>ISR: RxDone
  ISR->>Proc: EV_RX bit
  Proc->>GW: frame as a hex line
  GW->>Con: host ACK line
  Con->>Radio: send the ACK (ws_radio_send)
  Radio->>Node: ACK
  Radio->>ISR: TxDone or TxTimeout
  ISR->>Proc: EV_TX_DONE or EV_TX_TIMEOUT bit
  Proc->>Radio: listen again in continuous receive
```

- The radio stays in continuous receive through both kinds of failed reception (ST's `radio.c`).
  Nothing re-arms it.
- One capture waits for `process` at a time. The firmware counts failures that arrive meanwhile
  (`fault_overruns` on `#alive`). It also counts a forwarded frame that a newer frame replaced
  before `process` printed it.
- The console task puts a host ACK line on air. Its TxDone or TxTimeout returns the radio to
  listening. After a TxTimeout the firmware first puts the radio in standby, because the chip can
  still be transmitting.
- Only one ACK is on air at a time. The console refuses a second line meanwhile (`#tx busy`).
- The 60 s `#alive` timer only requests the report. `process` prints it.

The watchdog runs the RX health test every second. The test fails when one of these checks fails:

- The console receive is armed. The test re-arms it once before it fails.
- Console output is moving. A trace DMA transfer that does not finish for 3 s fails the test.
- An ACK is not on air for longer than the 3 s transmit timeout plus 2 s.
- The radio is heard from. After 16 minutes with no radio event, the firmware puts the radio in
  standby and listens again. 16 minutes is longer than the node's longest silence. Two such
  relistens in a row with no radio event fail the check, and the watchdog resets the board.

The firmware prints at most 20 failure lines a minute and counts the rest.

## Radio commands and the radio interrupt

ST's HAL lets one radio (SUBGHZ) command hold the driver at a time. A radio interrupt can arrive
while a main-loop command holds the driver. The HAL then refuses the interrupt's own commands
(HAL_BUSY). The interrupt cannot clear the radio's interrupt flag and re-enters at once. This
starves the main loop.

Every radio command from the main loop therefore runs with the radio interrupt masked in the
nested vectored interrupt controller (NVIC). These commands are `ws_radio_send`, `ws_radio_rx`,
`ws_radio_standby`, `ws_radio_sleep` and `ws_radio_rx_full_length` in `App/radio_cfg.*`. The
interrupt waits and runs immediately after. The host harnesses count every radio command made with
the interrupt unmasked. Every test requires a count of zero.

## What still stalls the CPU

These stalls come from the hardware. The firmware cannot avoid them.

| Stall | Bound | When it happens |
|---|---|---|
| Flash page erase | STM32WL55 datasheet (DS13293) t_ERASE: about 22 ms typical, about 24.5 ms maximum (the datasheet values as recalled in review). Measured on the board: 22,057 µs (`erase_peak_us`, release 586001994b09). The CPU cannot fetch from flash during an erase, so interrupts start late by up to that time | Start of a journal page (every 36 readings), meta-page compaction, WIPE, PROVISION, TEST-FLASH-STORM. Always with the radio idle (see below) |
| Flash double-word program | DS13293 t_PROG: about 82 µs typical, about 91 µs maximum (same caveat) | Journal append, ACK mark, counter reservation. Always with the radio idle |
| Radio SPI and BUSY handshakes in ST's driver | ST's loop counters bound them (`stm32wlxx_hal_subghz.c`). Microseconds per command, about 3.5 ms on wake with calibration (`tools/blocking_report.py` table) | Every radio command. Included in `task_peak_us` and `isr_peak_us` |
| RTC sub-second double read, UART start-up flags | `timer_if.c` reads the sub-second register until two reads agree. The register changes every 30.5 µs. The UART waits for TEACK and REACK at start | Timer reads, console start |

Flash writes always happen with the radio idle. Journal and counter writes happen before an
exchange or between frames. A reading made during an exchange waits in RAM until the exchange
ends. The console refuses the flash-writing commands during an exchange. The host harness checks
this in every test, a hung radio included.

The board measures these stalls. `#timing` reports `erase_peak_us`, `prog_peak_us`, the longest
task and the longest interrupt handler. The data watch and trace unit (DWT) cycle counter provides
the times (`App/busymon.h`). `isr_peak_us` times how long a handler runs. It does not include an
interrupt's late start during an erase. No measured values are recorded yet. They come with the
reflash.

## How we know

| Check | What it proves | Where |
|---|---|---|
| Host state-machine harness | Runs the real `app_tx.c` and its modules (`tx_exchange.c`, `tx_policy.c`, `tx_time.c`, `tx_console.c`, `selftest.c`) over a simulated clock, timers, sequencer, flash and radio. The real WSMP modules run on the I2C bus model with one simulated SHT45. The simulated radio follows ST's driver: a CRC failure is RxDone + RxError, and driver timeouts leave the radio transmitting or receiving. The tests prove these points: gaps are timers. Every state ends. Damaged packets do not end the window early. Flash commands wait for the exchange. Every (state, event) pair outside the table is only counted. Two events pending together are handled in bit order. Only the ACK for the frame just sent ends a window or sets the clock. A counter reservation swept across a whole exchange never meets a busy radio. The drain, link, health-report, strike and watchdog policies (transmit-failure run, exchange bound) behave as documented. A reading made while an exchange hangs is held in RAM, journaled when the radio goes idle and sent as backlog. A third held reading replaces the oldest and is counted. 3-hour randomised links with 5 fixed seeds include lost ACKs whose windows run out, NACKs, junk, CRC and header failures, another frame's ACK, transmit timeouts and send failures. These runs give no unexpected event. The radio state matches the exchange state, the watchdog check stays healthy, and no flash write happens while the radio transmits or receives. Timers and sequencer have ST's semantics. The suite builds with UBSan and reruns under ASan where the runtime can be preloaded | `firmware/host/tx_harness.c` over `firmware/host/sim_core.c`, `tests/test_tx_machine.py` |
| Host RX bridge harness | Runs the real `app_rx.c` and `console.c` over 1/1024 s ticks with ST's timer server, the sequencer, a continuous-receive radio that follows ST's driver, the console UART interrupt, the trace FIFO and the watchdog's health check. The tests prove these points: every valid frame is forwarded once as hex. CRC-failed packets are never forwarded and are logged whole. Header failures are logged. Nothing re-arms the radio after a failure. Only a valid host ACK or NACK is transmitted, and the radio listens again after it. The main loop prints `#alive`. Relisten and watchdog recovery behave as documented. A reference model checks a 6-hour randomised run line by line. A mutation pass plants 47 bugs and the tests catch all but one equivalent mutant. Review findings not yet fixed are `expectedFailure` tests | `firmware/host/rx_harness.c` over `firmware/host/sim_core.c`, `tests/test_rx_machine.py` |
| Host I2C bus harness | Runs the real `i2c_bus.c` over ST-rounded timers and a host model of ST's HAL I2C with many devices. Each transfer gives one `i2c_bus_done()` with the documented code for success, NACKs, hangs and a held SDA line. The recovery clocks a held SDA line free or reports it stuck. An absent device costs no recovery. A completion at the guard's instant counts once. Clients are served in order, one at a time, and a busy client's second submit is refused | `firmware/host/wsmp_harness.c` and `firmware/host/i2c_sim.c` over `firmware/host/sim_core.c`, `tests/test_i2c_bus.py` |
| Host WSMP module and station-host harness | Runs the real local modules (`wsmp_local.c`, `mod_*.c`), the station host (`wsmp_host.c`) and the catalog map (`wsmp_catalog_map.c`) on the same bus model. The tests check the module conformance cases, the mean windows and the latch. They also check presence, admission, the flap limit and the map round trip through the gateway's decoder | `firmware/host/wsmp_harness.c`, `firmware/host/i2c_models.c`, `tests/test_modules.py`, `tests/test_wsmp_host.py`, `tests/test_wsmp_map.py` |
| Build-time wait check | No interrupt handler or task in the linked image can reach a blocking call (`HAL_Delay`, blocking HAL I2C/UART/SPI, …). Every user of a timeout loop is classified | `tools/blocking_report.py`, `make ROLE=… waits`, CI |
| Run-time timing | TX `#timing` reports the peaks of tasks, handlers and flash stalls since boot. RX `#alive` reports tasks and handlers, and the gateway stores them. A task's peak is its own time, with the time of interrupts that ran meanwhile taken out. Interrupt time is summed once per outermost handler. The peak is named after the task's slowest timed step. `task_wall_us` gives the wall time with interrupts included (TX `#timing`, RX STATUS). SysTick, NMI and HardFault are not timed. `firmware/test_busymon.c` tests this on the host | `App/busymon.c` |
| Run-time checks | The board checks invariants of our own code: state-machine preconditions, indexes before buffers, flash writes inside the node-state pages, and timer starts that must not be refused. Each site has a recovery. The firmware counts failures and records the first site (TX `#counts`, RX `STATUS`). Every host harness test requires zero failures | `WS_CHECK`, `firmware/common/ws_check.h`, [`docs/power-of-ten.md`](power-of-ten.md) rule 5 |
| Console never blocks | The firmware drops and counts a line that does not fit the 2 KB output queue (`trace_drops`). Lines stay under the 640-byte line buffer, which would cut a longer line without a count | `sys_app.h` `APP_PRINTF` |

## Deliberate hangs

Only bench commands hang on purpose:

- TEST-HANG runs an endless loop. It proves that the watchdog resets the board.
- TEST-FAULT waits 50 ms for the console, then faults. The fault handler resets the board.

`Error_Handler` (an init failure) also loops forever, with interrupts off. The watchdog ends it only
if the watchdog has already started.
