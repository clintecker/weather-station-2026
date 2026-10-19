# Power of Ten: our firmware against NASA/JPL's ten rules

On 2026-10-15 Clint asked us to apply Holzmann's "The Power of Ten: Rules for Developing
Safety-Critical Code" (IEEE Computer, June 2006) to our firmware C "where it makes sense". This page
gives the status of each rule. It lists what complies, the deviations we keep and why, and what CI
enforces. It describes the tree as of the commit that last changed this page.

"TX" is the transmitter, the station node with the sensor. "RX" is the receiver, the bridge on the
gateway's USB cable. Both roles build from `firmware/stage0-node`.

**Scope.** The rules apply to our C in both roles:

- `firmware/stage0-node/App/*`, `firmware/common/*`, `firmware/stage0.c` and `.h`.
- Our edits in the ST-generated board files (`Core/Src/stm32wlxx_it.c`, `sys_app.h`).

The rules do not apply to:

- `vendor/` (ST's HAL, SubGHz_Phy and utilities, and Mbed TLS).
- The rest of the ST-generated board code (`firmware/board/nucleo-wl55jc`).
- The host harnesses and test programs (`firmware/host`, `firmware/test_*.c`, `firmware/fuzz`).
  These run on the PC and may allocate, recurse or use `longjmp`.

Size of the scope: 26 C files, 320 functions (counted by lizard, headers included), 2,146
non-comment lines of code (lizard NLOC).

## Summary

| # | Rule (short) | Status | Enforced by |
|---|---|---|---|
| 1 | Simple control flow: no `goto`, `setjmp`/`longjmp`, recursion | **Complies** (two bounded vendor cycles, outside our code) | `tools/stack_report.py` fails on recursion (`make stack`, CI). No `goto` or `setjmp` in scope (grep, below) |
| 2 | A fixed upper bound on every loop | **Complies with documented deviations** (2 deliberate hangs) | `tools/loop_bounds.py` (in `tools/code_shape.sh`, CI host job) |
| 3 | No dynamic allocation after initialisation | **Complies** (none at all) | The link fails if an allocator is linked (`NO_HEAP=1`, CI firmware job). `-Wvla -Walloca` |
| 4 | No function longer than 60 lines | **Complies** (also cyclomatic complexity ≤ 10) | `tools/code_shape.sh` (lizard), CI host job |
| 5 | Assertions: at least two per function, with an explicit recovery | **Partial**: a check facility with a defined recovery at 41 sites (about 0.1 per function, below the target, argued below) | Every host harness test requires zero failed checks. Tests make checks fail on purpose |
| 6 | Data at the smallest possible scope | **Complies** (one shared variable left, set by an interrupt) | Review. `-Wmissing-declarations`, `-Wredundant-decls`, Cppcheck `variableScope` |
| 7 | Check every non-void result and check parameters | **Complies with documented deviations** (`memcpy`/`memset`, `APP_PRINTF`, ST's void radio API) | `(void)` casts with reasons, `WS_CHECK` at module boundaries, review |
| 8 | Preprocessor: includes and simple macros only | **Complies with documented deviations** (an X-macro catalog, one token-pasting wrapper, `__LINE__` in `WS_CHECK`, 6 conditional-compilation switches) | Review. `-Wundef`, `-Wunused-macros` |
| 9 | One level of dereference and no function pointers | **Complies with documented deviations** (ST's callback APIs, and `ws_i2c_pins`, the pin interface that the stuck-bus recovery drives on the board and in its host test) | Review. `tools/stack_report.py` accounts for every pointer call |
| 10 | All warnings on, zero warnings, static analysis every day | **Complies** (every push, not daily) | `-Werror` strict set, GCC `-fanalyzer`, Cppcheck, all in CI |

## Rule 1: simple control flow

**Complies.**

- No `goto`, `setjmp` or `longjmp` is in scope. `grep -n "goto\|setjmp\|longjmp"` over the scope
  finds none. The host power-cut driver `firmware/test_store.c` uses `setjmp` to model a power cut.
  It is out of scope.
- No recursion. `tools/stack_report.py` (`make ROLE=tx|rx stack`, CI) builds the call graph from
  GCC's `-fcallgraph-info=su`. It fails on any cycle except the listed bounded ones
  (`BOUNDED_RECURSION`). Both listed cycles are in vendor code:
  - ST's `RadioSetPublicNetwork` ⇄ `RadioSetModem`. It runs at most once.
  - Mbed TLS's CCM ⇄ cipher-layer cycles. They cannot run, because our configuration has no cipher
    layer (`MBEDTLS_CIPHER_C` off, `common/ws_mbedtls_config.h`).

The `for (;;)` loops in `App/bench.c` (TEST-HANG) and `App/fault.c` (after the faulting read) are
deliberate ends of execution, not control flow. ST's `while (1)` in the fault handlers is the same.
See rule 2.

## Rule 2: every loop has a fixed upper bound

**Complies with documented deviations.** The scope has 49 loops:

- 38 are counting loops whose header states the bound (`for (i = 0; i < n; i++)`). The bound is a
  constant or a parameter whose maximum the caller fixes.
- The other 11 carry a `bound:` comment that says what bounds them. Two examples:
  - the journal scrub (`App/node_store.c`, `store_journal_scrub`). It makes at most
    `JOURNAL_CAPACITY` passes, and each match moves the index past its slot.
  - `ws_hex_decode` (`common/ws_console.c`). It makes at most `max + 1` passes.

`tools/loop_bounds.py` checks the loops syntactically:

- A counting loop's step must move toward its bound.
- Its body must not assign the loop variable.
- A literal bound must fit a declared 8-bit or 16-bit counter.
- Any other loop needs a `bound:` comment.

Review, not proof, decides what a symbolic bound (a parameter, a constant) is worth. Review also
decides whether a `bound:` comment is true. A loop that fails the check fails `tools/code_shape.sh`,
so it fails CI. `tests/test_loop_bounds.py` tests the checker, including the review's
counterexamples. The check covers `App/`, `firmware/common`, `firmware/stage0.c` and the node's
`Core/Src/stm32wlxx_it.c`. The fault-handler loops in that file are the documented deliberate
hangs.

Changes for this rule (commit "every loop has a stated upper bound"):

- `App/tx_exchange.c` `process()`: the event loop now counts at most `EV_COUNT` bits. Before, it
  shifted until the batch was empty. A stray bit would then have been handled with an event name
  past the end of `ev_name`. A stray bit is now also a `WS_CHECK` failure (rule 5).
- `firmware/stage0.c` `ws_i2c_recover` (host tests): at most `WS_I2C_RECOVER_STEPS` (23) steps. On
  the board, the same sequence runs one step per timer tick (`App/i2c_bus.c` `on_step`), with the
  same bound.

The console line bounds the string loops (`parse_u32` in `stage0.c`, `strlen` and `strncmp` in
`ws_cmd_find`). `ws_line_feed` always ends the line with a NUL within `WS_LINE_MAX` (256)
characters.

Deviations, which are deliberate unbounded loops:

- `App/bench.c` `test_hang`: TEST-HANG stops the main loop, so the watchdog must reset the board.
  That is its purpose. A field build leaves it out (`-DWS_FIELD_BUILD`).
- `App/fault.c` `fault_test`: the code never reaches this loop, because the read before it faults
  (TEST-FAULT, bench only).
- ST's `while (1)` loops in `Core/Src/stm32wlxx_it.c`:
  - after `fault_record`, which never returns.
  - in the stock MemManage, BusFault and UsageFault handlers. Those faults are not enabled, so they
    escalate to HardFault.
  - in `Error_Handler` (an init failure). [`docs/firmware-event-model.md`](firmware-event-model.md)
    lists it.

## Rule 3: no dynamic memory allocation after initialisation

**Complies: the firmware has no dynamic allocation at all**, not even at start-up. Every buffer is
static or on the stack, with a size fixed at compile time.

- Mbed TLS is configured without the generic cipher layer. That layer allocated a context with
  `calloc` for every seal and open. With no `MBEDTLS_CIPHER_C`, CCM keeps its AES context inline
  (`common/ws_mbedtls_config.h`). Mbed TLS is also configured without `MBEDTLS_PLATFORM_C`.
- The link enforces the rule. With `NO_HEAP=1` (`firmware/stage0-node/Makefile`, rule in
  `firmware/board/nucleo-wl55jc/board.mk`) the link fails if `malloc`, `calloc`, `realloc`, `free`,
  their `_r` forms or `_sbrk` are linked in. Both images pass ("no heap: no allocator linked").
- `-Wvla` and `-Walloca` (strict set) forbid stack allocation of run-time size.
- `tools/stack_report.py` bounds the stack statically: TX 5,744 B, RX 2,588 B of the 8,192 B that
  the linker reserves. The firmware also measures it at run time (`stack_peak` on `#counts` and
  `#alive`).
- Note: the shared linker script still reserves 512 B of heap (`_Min_Heap_Size`) that nothing
  uses. It is board code shared with `firmware/rangetest`, so we leave it as it is.

## Rule 4: no function longer than 60 lines

**Complies.** `tools/code_shape.sh` runs lizard with `-L 60` (lines per function) and `-C 10`
(cyclomatic complexity, stricter than the rule asks). It runs over the scope and the host
harnesses. It also runs jscpd, which finds copied code. The check runs in the CI host job. The 320
functions average 6.7 lines and a cyclomatic complexity of 3.0.

## Rule 5: assertions with an explicit recovery

**Partial.** The facility, its reporting and its tests comply. The density (0.11 per function) is
far below Holzmann's 2 per function. This is deliberate.

### The facility

`firmware/common/ws_check.h` and `ws_check.c` provide `WS_CHECK(cond)`:

```mermaid
flowchart LR
  C["WS_CHECK(cond)"] --> Q{"cond holds?"}
  Q -->|"yes"| ONE["Value 1, caller goes on"]
  Q -->|"no"| CNT["ws_check_fail: count since boot, record the first site"]
  CNT --> ZERO["Value 0"]
  ZERO --> REC["Caller recovers on the spot: return an error, skip the step, end the exchange, clamp an index or fall back to a cautious value"]
```

- `WS_CHECK` is an expression. It never halts or resets the board.
- The recovery is written next to the check.
- Unlike `assert()`, `WS_CHECK` is never compiled out. A condition can therefore be the call whose
  result it checks (rule 7).
- Cost: no strings. A failure records the count since boot and the first site. The site is a
  16-bit value, `(file number << 10) | line`:

```mermaid
packet-beta
  0-5: "file number, 1-63"
  6-15: "line, 1-1023"
```

`ws_check.h` lists the file numbers. `tests/test_check.py` keeps them unique and keeps every user
file under 1024 lines.

Reporting:

- TX prints `check_fails=N check_first=F:L` on `#counts`.
- RX prints the same fields on its `STATUS` reply, not on `#alive`, because the gateway stores the
  `#alive` fields.

Any nonzero count is a firmware bug to report.

### What a check is and is not

A check states an invariant of our own code. A failure is a bug.

`WS_CHECK` does not check input that can legitimately be bad: a received frame, a console line, or
flash read back after a power cut. Our code validates such input. Its failures are normal events
with their own counters (`ack_rejects`, `#rx drop`, `#host reject`, `burned`,
`#error journal-read`). This code is plentiful and is already "an assertion with a recovery" in
Holzmann's sense. This page does not count it.

### The 41 sites

TX has 40 sites and RX has 7. Some files are in both roles.

| Kind | Sites (file, function) | Recovery |
|---|---|---|
| State-machine preconditions | `tx_exchange.c`: `exchange_start` (no exchange running), `handle` (an unknown state is idle), `process` (only `EV_*` bits). `i2c_bus.c` `bus_task` (posted only in `S_DONE` or `S_RECOVERED`) | refuse the start, back to idle, drop the stray bits, or do nothing |
| Index and length bounds before a buffer is used | `tx_exchange.c` `send_current` (`qi < qn`), `mark_replied` (`qi`), `exchange_start` (backlog fits the queue). `tx_policy.c` `policy_exchange_end` (`n` fits `struck[]`). `app_tx.c` `held_count`. `node_store.c` `store_journal_read` and `_ack` (the ref is a journal slot, checked before it indexes the pending bitmap). `busymon.c` `busymon_end` (`kind`), `busymon_isr_exit` (an exit has its enter). `console.c` `hex_print` (frame length). `ws_policy.c` `ws_strike_note` (table size), `ws_link_probe_interval` (`probe_step`) | end the exchange, skip the write, clamp, or refuse (-1) |
| Flash writes stay in the node-state pages | `node_store.c` `prog64`, `erase_page`: every program and erase lies inside pages 55–127 (never the firmware) and is double-word aligned | refused like a failed flash operation, which every caller already handles |
| Our own data must encode or seal | `app_tx.c` `minute_report` (`ws_obs_encode`). `tx_exchange.c` `send_obs`, `send_diag` (`ws_seal_kind` with a provisioned station and a reserved counter) | `journal=ERROR`, or the item is skipped as for a local send failure |
| ST timer starts that must not be refused | `tx_exchange.c` gap and ACK-window timers. `i2c_bus.c` guard and step timers. `tx_console.c` reboot timer. `app_rx.c` `#alive` timer. `watchdog.c` check timer. ST refuses a start only for a running timer | the running timer still delivers its event. The reboot timer resets at once instead |
| HAL results that should not fail for our arguments | `i2c_bus.c` `i2c_start` (`HAL_I2C_Init`, analog filter). `watchdog.c` `HAL_IWDG_Init`, which can return `HAL_TIMEOUT` if the internal low-speed oscillator (LSI) never settles. `console.c` `console_init` (`vcom_ReceiveInit`) | the next transfer fails and the bus recovery re-initialises. The independent watchdog (IWDG) takes the values when its update completes. The console re-arms the receive once, and the RX health check also re-arms it |
| Local module steps | `mod_th.c`, `mod_reg.c`, `mod_power.c`: the bus takes each submitted transfer (`i2c_bus_submit` returns 0: one step at a time), and a completion arrives in a step that expects one. `wsmp_local.c` `i2c_bus_done`: the completion belongs to a known client | the sample counts as failed and the module waits for its next sample |
| Policy inputs | `ws_policy.c` `ws_lora_airtime_ms` (spreading factor, bandwidth, coding rate) | a whole minute: the live reading only, no division by zero |

### Tests

Every test of the TX, RX and sensor harnesses and every power-cut sweep requires zero failed checks.
The invariants are therefore checked on every simulated step. This includes the 3-hour randomised
TX links and the 6-hour RX run.

Some tests make a check fail on purpose. They confirm that the firmware counts it, reports its site
and recovers:

- TX (`test_a_failed_check_is_counted_reported_and_recovered`): the gap timer is already running
  when the exchange starts it. The exchange goes on, and `#counts` shows `check_fails=1` and the
  site.
- RX: the console receive does not start at boot. The firmware re-arms it once, the downlink works,
  and `STATUS` shows the site.
- The store (`firmware/test_store.c` `checks()`): the store refuses and counts refs outside the
  journal. The pending set does not change.
- The facility itself (`tests/test_check.py`).

### Why the density is lower than 2 per function

- **Cost.** A check costs 12–20 B of flash. TX uses 51.7 % of its 110 KB region. The final
  station's features need an estimated 18–33 KB of the 26 KB below the 75 % headroom target. The
  sites cost about 660 B with the facility and its reporting (measured at 35 sites). Holzmann's
  density over TX's 287 functions would be about 570 checks, roughly 9 KB. That is too large a
  share of the headroom.
- **Small functions.** Most of the 320 functions are too small to have an invariant worth a
  run-time check. Examples are one-line accessors, timer and radio callbacks that post an event
  bit, and the timed task wrappers. 170 functions are non-trivial (cyclomatic complexity ≥ 3 or
  ≥ 8 lines). 29 of them hold a check. These 29 are the functions that index arrays, write flash or
  move a state machine.
- **Pure code validates its input.** The portable pure code (`ws_frame.c`, `ws_obs.c`,
  `ws_console.c`, `stage0.c`) validates every input and returns an error. That is its recovery.
  This code is fuzzed (`firmware/fuzz`, libFuzzer in CI) and unit tested. A `WS_CHECK` there would
  count legitimate bad input as bugs.
- **Free checks.** Many invariants are checked where a check costs no flash:
  - 25 `_Static_assert`s (layouts, table sizes, the journal geometry).
  - The host harnesses' per-step invariants: no flash write while the radio is busy, no radio
    command with its interrupt unmasked, no refused timer start, no task that never settles, no
    interrupt mask left set. These run the real firmware C on every test.

## Rule 6: data at the smallest possible scope

**Complies.** Each module keeps its state `static`. Every file-scope variable in scope is private
to its file, except one (below).

Changes for this rule (commit "narrow the shared node state"):

- `tx_node` was one writable global that every TX module could read and change, including the AES
  key. Now `app_tx.c` owns this boot's identity and run state. The other modules get a `const` view
  (`node_state()`, `App/tx_node.h`).
- The key and station live in `tx_exchange.c`, the only module that seals and opens frames
  (`exchange_load_identity`). The console sees only the station and the key check value
  (`exchange_identity()`, read-only).
- `rebooting` and `storming` became `tx_console.c` statics. Behaviour is unchanged.
- `tx_counts` is static in `tx_exchange.c`. Other modules read it through `exchange_counts()`.
- Cppcheck's `variableScope` findings (two variables, in `ws_line_feed` and `ws_key_check`) were
  narrowed.

Kept and documented: `ws_flash_ecc_fault` (`Core/Src/stm32wlxx_it.c`) is the one variable shared
across files. The NMI handler sets it and the flash read checks it. An interrupt can only report
through shared state. The board's `ws_trace_drops` (console drops) is the same kind.

## Rule 7: check every result and every parameter

**Complies with documented deviations.** Every non-void call in scope either uses its result or
casts it to `(void)`. The reason is next to the cast or listed here:

- ST's `UTIL_TIMER_Create`, `Stop` and `SetPeriod` fail only for a NULL object or callback
  (`stm32_timer.c`). `Start` also fails for a running timer. Our timers are static objects with
  named callbacks, so those calls are `(void)`. The starts that a state machine relies on are
  checked with `WS_CHECK` (rule 5).
- `HAL_FLASH_Unlock` and `Lock` (`App/flash_stm32wl.c`): if the flash did not unlock, it refuses
  the next program or erase, and that call returns the status.
- `HAL_RCCEx_PeriphCLKConfig` for I2C2 only selects a clock.
- `HAL_IWDG_Refresh` always returns `HAL_OK`.
- `HAL_I2C_DeInit` fails only for a NULL handle.
- `store_note_abandoned` (twice): a total that failed to persist is only a count. The record is
  acknowledged either way.
- The bench storm load ignores the results of its writes on purpose.
- Every flash, journal and counter call in the exchange is checked. With no counter reservation,
  the node does not transmit.

Deviations:

- `memcpy`, `memset` and `memmove` return their destination argument. Our code does not use or cast
  their results. This is the common reading of the rule, and a cast adds nothing.
- `APP_PRINTF` (`sys_app.h`) checks its own result. The console drops and counts a line that its
  queue cannot take (`trace_drops` on `#timing` and `#alive`). It never waits. This is the
  deliberate design of a console that never blocks ([`docs/firmware-event-model.md`](firmware-event-model.md)).
- ST's radio API returns nothing for `Init`, `Rx`, `Standby`, `Sleep` and the configuration calls
  (`radio.h`). Only `Send` reports a result, and our code checks it. A command that fails silently
  shows up as a missing event. These mechanisms recover from it:
  - the TX exchange's ACK-window and transmit timeouts and its watchdog bound.
  - the RX health check (no radio event for 16 minutes, or a transmission longer than 5 s).

Parameters at module boundaries:

- The store refuses a journal ref outside the journal and every flash address outside the
  node-state pages.
- `exchange_start` clamps the backlog to the queue. `policy_exchange_end` clamps its count.
- The pure functions validate their inputs (`ws_seal_kind`, `ws_open_reply`, `ws_obs_encode`,
  `ws_parse_provision`, `ws_hex_decode`).
- Our code does not NULL-check pointers that it passes itself (addresses of static or stack
  objects).

## Rule 8: limited use of the preprocessor

**Complies with documented deviations.** Our macros are constants and short expression macros. No
macro defines a type, hides control flow or spans more than a statement.

Changes for this rule: `node_store.c`'s `BIT()` and `ws_check.h`'s site accessors became static
functions.

Deviations kept, with the reason:

- `WS_OBS_CATALOG` (`common/ws_obs.h`) is an X-macro. The field catalog's widths and maxima exist
  once. `ws_obs.c`'s tables and the constant-expression record lengths are generated from it, so
  they cannot drift apart. `WS_OBS_PLAIN_LEN` sizes buffers and the journal slot. A
  `_Static_assert` checks one entry per field. `tests/test_obs.py` checks the catalog against the
  gateway's `ws0/fields.py`.
- `BUSYMON_TASK(fn)` (`App/busymon.h`) uses token pasting and stringising. It generates each task's
  one-line timed wrapper (`fn_timed`), so every task is measured the same way and carries its name.
  `BUSYMON_ISR(name, body)` wraps a handler body in the same timing as one statement. The generated
  functions are ordinary C that GCC, lizard and the stack and blocking reports see.
- `WS_CHECK` must be a macro, because it records its caller's `__LINE__`.
- `APP_PRINTF` (board `sys_app.h`) is variadic. It came from ST.
- Conditional compilation uses six switches. Each is a build variant or a guard:
  - `WS_FIELD_BUILD` leaves out the bench commands (`bench.c`, `tx_console.c`).
  - `WS_NODE_FIELDS` selects the build's field set (`node_fields.h`).
  - `WS_JOURNAL_PAGES` lets host tests shrink the journal (`flash_layout.h`).
  - `WS_FW_BUILD_ID` and `WS_CHECK_FILE` cause `#error` if the build or the file did not define
    them.
  - `DEBUGGER_ENABLED` (`watchdog.c`) is ST's switch.

`-Wundef` and `-Wunused-macros` are on.

## Rule 9: restricted pointers and no function pointers

**Complies with documented deviations.**

Changes for this rule (commits "link-time seams instead of our own function pointers" and "one level
of indirection in the PROVISION parser"):

- Our own function pointers had one implementation per build. They became named functions that the
  linker resolves:
  - the flash primitives (`ws_flash_read64`, `prog64`, `erase` in `App/flash_layout.h`). These were
    a table of three pointers.
  - the console line handler (`console_line`).
  - the completion of an I2C transfer (`i2c_bus_done`, defined in `App/wsmp_local.c`).
  - the watchdog health test (`watchdog_healthy`).
- The PROVISION parser no longer advances a cursor through a `const char **`.

Deviations kept:

- **ST's callback APIs**, which we cannot avoid: `UTIL_TIMER` callbacks, `UTIL_SEQ` tasks
  (registered as their `BUSYMON_TASK` wrappers), SubGHz_Phy's `RadioEvents_t` and its `Radio`
  function table, and the board's `vcom_ReceiveInit` character callback. ST's HAL weak callbacks,
  such as `HAL_I2C_MasterTxCpltCallback`, are link-time overrides, not pointers.
- **`ws_i2c_pins`** (`stage0.h`) is a `const` table of pin functions behind the I2C stuck-bus
  recovery waveform. With this table, the same `ws_i2c_recover_step` is host-tested with simulated
  pins (`firmware/test_policy.c`) and drives the real pins in `i2c_bus.c`. A link-time seam would
  force every build that links `stage0.c` (the fuzzers, the host tests) to define pin stubs.

How the stack bound treats indirect calls: `tools/stack_report.py` follows direct calls exactly. A
call through a pointer may reach any linked function whose address is taken (from the object
files' relocations). The bound allows at most two pointer hops on one stack and two nested
interrupts:

```mermaid
flowchart LR
  M["Main loop"] -->|"pointer hop 1"| T["Sequencer task"]
  T -->|"pointer hop 2"| CB["Driver callback"]
  CB -.->|"interrupt on top of this stack"| I1["Interrupt 1, one pointer call"]
  I1 -.->|"nested interrupt"| I2["Interrupt 2, one pointer call"]
```

The changes above removed four of our own targets from that conservative set. The tool now computes
those paths exactly.

Pointer dereference: our code uses one level wherever we can choose. Struct members are reached
through one pointer (`p->x`). `held[i][k]` is a two-dimensional array, not a pointer to pointers.
One deliberate exception: `ws_cmd_find(const char *const names[])` takes the command-name table, an
array of string pointers.

## Rule 10: all warnings, zero warnings, static analysis

**Complies.** CI runs these checks on every push and pull request (`.github/workflows/ci.yml`):

- **Compiler**, our C only (`STRICT` in `firmware/board/nucleo-wl55jc/board.mk`). ST's code builds
  with `-Wall` only. Our flags: `-Wall -Wextra -Wshadow -Wconversion -Wsign-conversion -Wcast-qual
  -Wstrict-prototypes -Wmissing-prototypes -Wundef -Wdouble-promotion -Wformat=2
  -Wnull-dereference`. This rule added `-Wpedantic -Wformat-signedness -Wformat-overflow=2
  -Wformat-truncation=2 -Wvla -Walloca -Wcast-align -Wpointer-arith -Wredundant-decls
  -Wold-style-definition -Wmissing-declarations -Wwrite-strings -Wjump-misses-init -Wlogical-op
  -Wduplicated-cond -Wduplicated-branches -Wswitch-default -Wfloat-equal -Wunused-macros
  -Wstack-usage=512`. All flags run with `-Werror`. Both roles build with zero warnings, and so
  does `firmware/rangetest`'s strict file.
- **Console formats.** ST's `UTIL_ADV_TRACE_COND_FSend` has no `format` attribute. GCC therefore
  never compared `APP_PRINTF`'s formats with their arguments on the target. `sys_app.h` now also
  passes the same arguments to a never-called function with the `printf` attribute. This adds no
  code. It found three `int` constants printed with `%u`. They were harmless and are now unsigned.
- **GCC's static analyser** (`-fanalyzer`) on our C for both roles: zero findings.
- **Cppcheck 2.22.0** (`tools/cppcheck.sh`, from the pinned `cppcheck==1.5.3` wheel in
  `requirements-dev.txt`): warning, style, performance and portability checks, exhaustive, with
  zero findings.
  - It runs without the HAL and ST utility include paths (`--suppress=missingInclude`). It
    therefore analyses our code without ST's types and does not cover the board files. It is a
    lighter check than the compiler's, which sees everything.
  - Its first run found 14 issues: two variables whose scope could shrink, a pointer that could be
    const, a static assert that it misread (now `!= 0`), and ST callback signatures that we cannot
    make const. Those signatures are suppressed inline with the reason
    (`/* cppcheck-suppress … ; ST's … signature */`).
- **Our own analyses**:
  - worst-case stack (`make stack`).
  - no blocking call reachable at run time (`make waits`, `tools/blocking_report.py`).
  - function size and duplication, loop bounds, no heap, and the flash budget.
  - reproducible builds.
  - libFuzzer on the four input parsers.
  - the host harnesses under UBSan, and under ASan where it can be preloaded.

Deviation: "daily" becomes "every push". Every tool is pinned, so a run on unchanged code repeats
the last result. A schedule would add nothing. CI analyses every change before it is merged.

## What this cost

Measured from clean trees (same version-string length) before (`1947b40`) and after this work:

| | Before | After | Change |
|---|---|---|---|
| TX flash (code + data) | 57,136 B (87.2 %) | 57,744 B (88.1 %) | +608 B: the checks and their reporting +664, the narrower node state +80, the loop and macro changes +16, the link-time seams −120, the parser −32 |
| RX flash | 34,072 B (52.0 %) | 34,152 B (52.1 %) | +80 B: the checks and their reporting +128, the link-time seams −48 |
| TX worst-case stack (`make stack`) | 5,648 B | 5,744 B | +96 B (of 8,192 B) |
| RX worst-case stack | 2,588 B | 2,588 B | 0 |

After this work, TX stayed 1,238 B below the 90 % guard.
