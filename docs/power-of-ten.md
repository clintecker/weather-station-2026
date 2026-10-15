# Power of Ten: our firmware against NASA/JPL's ten rules

Requested 2026-10-15 (Clint): apply Holzmann's "The Power of Ten: Rules for Developing
Safety-Critical Code" (IEEE Computer, June 2006) to our firmware C "where it makes sense". This page
is the status per rule: what complies, the deviations we keep and why, and what CI enforces so it
stays that way. It describes the tree as of the commit that last changed this page.

**Scope.** Our C in both roles: `firmware/stage0-node/App/*`, `firmware/common/*`, `firmware/stage0.c`
and `.h`, and our edits in the ST-generated board files (`Core/Src/stm32wlxx_it.c`, `sys_app.h`). Not
`vendor/` (ST's HAL, SubGHz_Phy, utilities; Mbed TLS), not the rest of the ST-generated board code
(`firmware/board/nucleo-wl55jc`), not the host harnesses and test programs (`firmware/host`,
`firmware/test_*.c`, `firmware/fuzz`), which run on the PC and may allocate, recurse or `longjmp`.
Size of the scope: 26 C files, 275 functions (lizard), about 2,600 lines of code.

## Summary

| # | Rule (short) | Status | Enforced by |
|---|---|---|---|
| 1 | Simple control flow: no `goto`, `setjmp`/`longjmp`, recursion | **Complies** (two bounded vendor cycles, outside our code) | `tools/stack_report.py` fails on recursion (`make stack`, CI); no `goto`/`setjmp` in scope (grep, below) |
| 2 | A fixed upper bound on every loop | **Complies with documented deviations** (2 deliberate hangs) | `tools/loop_bounds.py` (in `tools/code_shape.sh`, CI host job) |
| 3 | No dynamic allocation after initialisation | **Complies** (none at all) | The link fails if an allocator is linked (`NO_HEAP=1`, CI firmware job); `-Wvla -Walloca` |
| 4 | No function longer than 60 lines | **Complies** (also CCN ≤ 10) | `tools/code_shape.sh` (lizard), CI host job |
| 5 | Assertions: at least two per function, with an explicit recovery | **Partial**: a check facility with a defined recovery, 35 sites (0.13 per function, below the target; argued below) | Every host harness test requires zero failed checks; tests make checks fail on purpose |
| 6 | Data at the smallest possible scope | **Complies** (one shared variable left, set by an interrupt) | Review; `-Wmissing-declarations`, `-Wredundant-decls`, cppcheck `variableScope` |
| 7 | Check every non-void result; check parameters | **Complies with documented deviations** (`memcpy`/`memset`, `APP_PRINTF`, ST's void radio API) | `(void)` casts with reasons; `WS_CHECK` at module boundaries; review |
| 8 | Preprocessor: includes and simple macros only | **Complies with documented deviations** (an X-macro catalog, one token-pasting wrapper, `__LINE__` in `WS_CHECK`, 6 conditional-compilation switches) | Review; `-Wundef`, `-Wunused-macros` |
| 9 | One level of dereference; no function pointers | **Complies with documented deviations** (ST's callback APIs; `ws_i2c_pins`, the pin interface the stuck-bus recovery drives on the board and in its host test) | Review; `tools/stack_report.py` accounts for every pointer call |
| 10 | All warnings on, zero warnings, static analysis every day | **Complies** (every push, not daily) | `-Werror` strict set, GCC `-fanalyzer`, Cppcheck, all in CI |

## Rule 1: simple control flow

**Complies.** No `goto`, `setjmp` or `longjmp` in scope (`grep -n "goto\|setjmp\|longjmp"` over the
scope finds none; the host power-cut driver `firmware/test_store.c` uses `setjmp` to model a power cut
and is out of scope). No recursion: `tools/stack_report.py` (`make ROLE=tx|rx stack`, CI) builds the
call graph from GCC's `-fcallgraph-info=su` and fails on any cycle except the listed bounded ones,
both in vendor code (`BOUNDED_RECURSION`): ST's `RadioSetPublicNetwork` ⇄ `RadioSetModem` (runs at
most once) and Mbed TLS's CCM ⇄ cipher-layer cycles, which cannot run because our configuration has
no cipher layer (`MBEDTLS_CIPHER_C` off, `common/ws_mbedtls_config.h`).

The `for (;;)` loops in `App/bench.c` (TEST-HANG) and `App/fault.c` (after the faulting read) and ST's
`while (1)` in the fault handlers are deliberate ends of execution, not control flow: see rule 2.

## Rule 2: every loop has a fixed upper bound

**Complies with documented deviations.** 49 loops in scope. 38 are counting loops whose header states
the bound (`for (i = 0; i < n; i++)` with a constant or a parameter whose maximum the caller fixes);
the other 11 carry a `bound:` comment saying what bounds them, for example the journal scrub
(`App/node_store.c`, `store_journal_scrub`: at most `JOURNAL_CAPACITY` passes, each match moves the
index past its slot) or `ws_hex_decode` (`common/ws_console.c`: at most `max + 1` passes).
`tools/loop_bounds.py` checks this syntactically: a counting loop's step must move toward its bound,
its body must not assign the loop variable, and a literal bound must fit a declared 8- or 16-bit
counter; any other loop needs a `bound:` comment. What a symbolic bound (a parameter, a constant) is
worth, and whether a `bound:` comment is true, is reviewed, not proven. A loop that fails the check
fails `tools/code_shape.sh` and so CI (`tests/test_loop_bounds.py` tests the checker, including the
review's counterexamples). In scope: `App/`, `firmware/common`, `firmware/stage0.c` and the node's
`Core/Src/stm32wlxx_it.c` (its fault-handler loops are the documented deliberate hangs).

Changed for this rule (commit "every loop has a stated upper bound"):
- `App/tx_exchange.c` `process()`: the event loop now counts at most `EV_COUNT` bits; before, it
  shifted until the batch was empty, and a stray bit would have been handled with an event name past
  the end of `ev_name` (and is now also a `WS_CHECK`, rule 5).
- `firmware/stage0.c` `ws_i2c_recover` (host tests): at most `WS_I2C_RECOVER_STEPS` (23) steps; on
  the board the same sequence is one step per timer tick (`App/sensor.c` `on_step`), bounded the same.

String loops (`parse_u32` in `stage0.c`, `strlen`/`strncmp` in `ws_cmd_find`) are bounded by the
console line, which `ws_line_feed` always NUL-terminates within `WS_LINE_MAX` (256) characters.

Deviations, deliberate unbounded loops:
- `App/bench.c` `test_hang`: TEST-HANG stops the main loop so the watchdog must reset the board (its
  purpose); left out of a field build (`-DWS_FIELD_BUILD`).
- `App/fault.c` `fault_test`: never reached, the read before it faults (TEST-FAULT, bench only).
- ST's `while (1)` after `fault_record` (which never returns) in `Core/Src/stm32wlxx_it.c`, the stock
  MemManage/BusFault/UsageFault handlers (those faults are not enabled; they escalate to HardFault)
  and `Error_Handler` (an init failure; `docs/firmware-event-model.md` lists it).

## Rule 3: no dynamic memory allocation after initialisation

**Complies: there is no dynamic allocation at all**, not even at start-up. Every buffer is static or
on the stack with a size fixed at compile time. Mbed TLS is configured without the generic cipher
layer, which `calloc`'d a context for every seal and open (`common/ws_mbedtls_config.h`: no
`MBEDTLS_CIPHER_C`, so CCM keeps its AES context inline), and without `MBEDTLS_PLATFORM_C`.
- Enforced at link time: `NO_HEAP=1` (`firmware/stage0-node/Makefile`; the rule is in
  `firmware/board/nucleo-wl55jc/board.mk`) fails the link if `malloc`, `calloc`, `realloc`, `free`,
  their `_r` forms or `_sbrk` are linked in. Both images pass ("no heap: no allocator linked").
- `-Wvla` and `-Walloca` (strict set) forbid stack allocation of run-time size.
- The stack is bounded statically (`tools/stack_report.py`: TX 5,744 B, RX 2,588 B of the 8,192 B the
  linker reserves) and measured at run time (`stack_peak` on `#counts` / `#alive`).
- Note: the shared linker script still reserves 512 B of heap (`_Min_Heap_Size`) that nothing uses.
  It is board code shared with `firmware/rangetest`; left as is.

## Rule 4: no function longer than 60 lines

**Complies.** `tools/code_shape.sh` runs lizard with `-L 60` (lines per function) and `-C 10`
(cyclomatic complexity, stricter than the rule asks) over the scope and the host harnesses, and
jscpd (no copied code). CI host job. The 275 functions average 6.9 lines and CCN 3.2.

## Rule 5: assertions with an explicit recovery

**Partial: the facility, its reporting and its tests comply; the density (0.13 per function) is far
below Holzmann's 2 per function, deliberately.**

**The facility** (`firmware/common/ws_check.h`, `ws_check.c`): `WS_CHECK(cond)` is an expression, 1
if `cond` holds, else 0 after counting the failure. It never halts or resets: the caller recovers on
the spot, written next to the check (return an error, skip the step, end the exchange, clamp an index,
fall back to a cautious value). Unlike `assert()` it is never compiled out, so a condition may be the
call whose result it checks (rule 7). Cost: no strings; a failure records the count since boot and the
first site, a 16-bit `(file number << 10) | line` (the file numbers are listed in `ws_check.h`;
`tests/test_check.py` keeps them unique and every user under 1024 lines). Reporting: TX `#counts`
`check_fails=N check_first=F:L`; RX on its `STATUS` reply (not `#alive`: the gateway stores those
fields). Any nonzero count is a firmware bug to report.

**What a check is, and is not.** A check states an invariant of our own code: a failure is a bug.
Input that can legitimately be bad (a received frame, a console line, flash read back after a power
cut) is not checked with `WS_CHECK`: it is validated, and its failures are normal events with their
own counters (`ack_rejects`, `#rx drop`, `#host reject`, `burned`, `#error journal-read`). That code is
plentiful and already "an assertion with a recovery" in Holzmann's sense, but it is not counted here.

**The 35 sites** (34 in TX, 6 in RX; some files are in both), by kind:

| Kind | Sites (file, function) | Recovery |
|---|---|---|
| State-machine preconditions | `tx_exchange.c`: `exchange_start` (no exchange running), `handle` (an unknown state is idle), `process` (only `EV_*` bits); `sensor.c` `sensor_task` (posted only in `S_DONE`/`S_RECOVERED`) | refuse the start / back to idle / drop the stray bits / nothing to do |
| Index and length bounds before a buffer is used | `tx_exchange.c` `send_current` (`qi < qn`), `mark_replied` (`qi`), `exchange_start` (backlog fits the queue); `tx_policy.c` `policy_exchange_end` (`n` fits `struck[]`); `app_tx.c` `held_count`; `node_store.c` `store_journal_read`/`_ack` (the ref is a journal slot, before it indexes the pending bitmap); `busymon.c` `busymon_end` (`kind`); `console.c` `hex_print` (frame length); `ws_policy.c` `ws_strike_note` (table size), `ws_link_probe_interval` (`probe_step`) | end the exchange / skip the write / clamp / refuse (-1) |
| Flash writes stay in the node-state pages | `node_store.c` `prog64`, `erase_page`: every program and erase lies inside pages 32–127 (never the firmware) and is double-word aligned | refused like a failed flash operation, which every caller already handles |
| Our own data must encode or seal | `app_tx.c` `minute_report` (`ws_obs_encode`); `tx_exchange.c` `send_obs`, `send_diag` (`ws_seal_kind` with a provisioned station and a reserved counter) | `journal=ERROR` / the item is skipped, as for a local send failure |
| ST timer starts that must not be refused | `tx_exchange.c` gap and ACK-window timers; `sensor.c` guard, measurement and step timers; `tx_console.c` reboot timer; `app_rx.c` `#alive` timer; `watchdog.c` check timer. ST refuses a start only for a running timer | its event still comes from the running timer; the reboot timer resets at once instead |
| HAL results that should not fail for our arguments | `sensor.c` `i2c_start` (`HAL_I2C_Init`, analog filter); `watchdog.c` `HAL_IWDG_Init` (it can return `HAL_TIMEOUT` if the LSI never settles); `console.c` `console_init` (`vcom_ReceiveInit`) | the next transfer fails and the bus recovery re-initialises / the IWDG takes the values when its update completes / re-arm the receive once (RX's health check re-arms too) |
| Policy inputs | `ws_policy.c` `ws_lora_airtime_ms` (SF, bandwidth, coding rate) | a whole minute: the live reading only, no division by zero |

**Tests.** Every test of the TX, RX and sensor harnesses and every power-cut sweep now also requires
zero failed checks, so the invariants are checked on every simulated step (the 3 h randomised TX links
and the 6 h RX run included). Tests make a check fail on purpose and see it counted, reported with its
site and recovered from: TX (`test_a_failed_check_is_counted_reported_and_recovered`: the gap timer is
already running when the exchange starts it; the exchange goes on and `#counts` shows `check_fails=1`
and the site), RX (the console receive does not start at boot; one re-arm, the downlink works,
`STATUS` shows the site), the store (`firmware/test_store.c` `checks()`: refs outside the journal are
refused, counted, the pending set untouched) and the facility itself (`tests/test_check.py`).

**Why the density is lower than 2 per function, and should be:**
- Cost. A check costs 12–20 B of flash. TX is at 88.1 % of its 64 KB region against a hard 90 % limit
  (1,238 B left). The 35 sites cost 664 B with the facility and its reporting; Holzmann's density over TX's 255
  functions would be about 500 checks, roughly 8 KB, which does not fit.
- Most of the 275 functions are too small to have an invariant worth a run-time check: one-line
  accessors, timer and radio callbacks that post an event bit, the timed task wrappers. 161 functions
  are non-trivial (CCN ≥ 3 or ≥ 8 lines); 26 of them hold a check, and they are the ones that index
  arrays, write flash or move a state machine.
- The portable pure code (`ws_frame.c`, `ws_obs.c`, `ws_console.c`, `stage0.c`) validates every input
  and returns an error: that is its recovery, it is fuzzed (`firmware/fuzz`, libFuzzer in CI) and unit
  tested, and a `WS_CHECK` there would count legitimate bad input as bugs.
- Many invariants are checked where checking costs no flash: 20 `_Static_assert`s (layouts, table
  sizes, the journal geometry), and the host harnesses' per-step invariants (no flash write while the
  radio is busy, no radio command with its interrupt unmasked, no refused timer start, no task that
  never settles, no interrupt mask left set), which run the real firmware C on every test.

## Rule 6: data at the smallest possible scope

**Complies.** Each module keeps its state `static`: every file-scope variable in scope is private to
its file but one (below). Changed for this rule (commit "narrow the shared node state"):
- `tx_node` was one writable global that every TX module could read and change, the AES key
  included. Now `app_tx.c` owns this boot's identity and run state and the others get a `const` view
  (`node_state()`, `App/tx_node.h`); the key and station live in `tx_exchange.c`, the only module that
  seals and opens frames (`exchange_load_identity`), and the console sees the station and key check
  value only (`exchange_identity()`, read-only). `rebooting` and `storming` became `tx_console.c`
  statics. Behaviour unchanged.
- `tx_counts` is static in `tx_exchange.c`, read through `exchange_counts()`.
- Cppcheck's `variableScope` findings (two variables, `ws_line_feed`, `ws_key_check`) were narrowed.

Kept (documented): the one variable shared across files is `ws_flash_ecc_fault`
(`Core/Src/stm32wlxx_it.c`), which the NMI handler sets and the flash read checks: an interrupt can
only report through shared state. The board's `ws_trace_drops` (console drops) is the same kind.

## Rule 7: check every result and every parameter

**Complies with documented deviations.** Every non-void call in scope either has its result used or
is cast to `(void)`, with the reason next to it or here:
- ST's `UTIL_TIMER_Create`/`Stop`/`SetPeriod` fail only for a NULL object or callback
  (`stm32_timer.c`), and `Start` also for a running timer. Ours are static objects with named
  callbacks: those calls are `(void)`; the starts a state machine relies on are `WS_CHECK`ed (rule 5).
- `HAL_FLASH_Unlock`/`Lock` (`App/flash_stm32wl.c`): a flash that did not unlock refuses the program or
  erase that follows, whose status is returned. `HAL_RCCEx_PeriphCLKConfig` for I2C2 only selects a
  clock. `HAL_IWDG_Refresh` always returns `HAL_OK`. `HAL_I2C_DeInit` fails only for a NULL handle.
- `store_note_abandoned` (twice): a total that failed to persist is only a count; the record is
  acknowledged either way. The bench storm load ignores its writes' results on purpose.
- Every flash, journal and counter call in the exchange is checked (no reservation, no transmission).

Deviations:
- `memcpy`, `memset`, `memmove` return their destination argument; their results are not used and not
  cast (the common reading of the rule; casting them adds nothing).
- `APP_PRINTF` (`sys_app.h`) checks its own result: a line the console queue cannot take is dropped and
  counted (`trace_drops` on `#timing` / `#alive`), never waited for. That is the deliberate design of a
  console that never blocks (`docs/firmware-event-model.md`).
- ST's radio API returns nothing for `Init`, `Rx`, `Standby`, `Sleep` and the configuration calls
  (`radio.h`); only `Send` reports (and is checked). A command that silently fails shows up as a
  missing event: the TX exchange's ACK-window and transmit timeouts and its watchdog bound, and the RX
  health check (no radio event for 16 minutes, a transmission longer than 5 s) recover from it.

Parameters at module boundaries: the store refuses a journal ref outside the journal and every flash
address outside the node-state pages; `exchange_start` clamps the backlog to the queue;
`policy_exchange_end` its count; the pure functions validate their inputs (`ws_seal_kind`,
`ws_open_reply`, `ws_obs_encode`, `ws_parse_provision`, `ws_hex_decode`). Pointers that our own code
passes (addresses of static or stack objects) are not NULL-checked.

## Rule 8: limited use of the preprocessor

**Complies with documented deviations.** Our macros are constants and short expression macros; no
macro defines a type, hides control flow, or spans more than a statement. Changed for this rule:
`node_store.c`'s `BIT()` and `ws_check.h`'s site accessors became static functions.
Deviations kept, with the reason:
- `WS_OBS_CATALOG` (`common/ws_obs.h`), an X-macro: the field catalog's widths and maxima exist once,
  and `ws_obs.c`'s tables and the constant-expression record lengths (`WS_OBS_PLAIN_LEN`, used to size
  buffers and the journal slot) are generated from it, so they cannot drift apart. A
  `_Static_assert` checks one entry per field; `tests/test_obs.py` checks it against the gateway's
  `ws0/fields.py`.
- `BUSYMON_TASK(fn)` (`App/busymon.h`) uses token pasting and stringising to generate each task's
  one-line timed wrapper (`fn_timed`), so every task is measured the same way and carries its name.
  `BUSYMON_ISR(name, body)` wraps a handler body in the same timing as one statement. The generated
  functions are ordinary C that GCC, lizard and the stack and blocking reports see.
- `WS_CHECK` must be a macro: it records its caller's `__LINE__`.
- `APP_PRINTF` (board `sys_app.h`) is variadic (it was ST's).
- Conditional compilation, six switches, each a build variant or a guard: `WS_FIELD_BUILD` (bench
  commands left out: `bench.c`, `tx_console.c`), `WS_NODE_FIELDS` (the build's field set,
  `node_fields.h`), `WS_JOURNAL_PAGES` (host tests shrink the journal, `flash_layout.h`),
  `WS_FW_BUILD_ID` and `WS_CHECK_FILE` (`#error` if the build or the file did not define them), and
  `DEBUGGER_ENABLED` (`watchdog.c`, ST's switch). `-Wundef` and `-Wunused-macros` are on.

## Rule 9: restricted pointers, no function pointers

**Complies with documented deviations.**

Changed for this rule (commits "link-time seams instead of our own function pointers" and "one level
of indirection in the PROVISION parser"): our own function pointers with one implementation per build
became named functions resolved at link time: the flash primitives (`ws_flash_read64`/`prog64`/
`erase`, `App/flash_layout.h`: was a table of three pointers), the console line handler
(`console_line`), the sensor's result (`sensor_done`) and the watchdog health test
(`watchdog_healthy`). The PROVISION parser no longer advances a cursor through a `const char **`.

Deviations kept:
- **ST's callback APIs**, which we cannot avoid: `UTIL_TIMER` callbacks, `UTIL_SEQ` tasks (registered
  as their `BUSYMON_TASK` wrappers), SubGHz_Phy's `RadioEvents_t` and its `Radio` function table, the
  board's `vcom_ReceiveInit` character callback. (ST's HAL weak callbacks, such as
  `HAL_I2C_MasterTxCpltCallback`, are link-time overrides, not pointers.)
- **`ws_i2c_pins`** (`stage0.h`): a `const` table of pin functions behind the I2C stuck-bus recovery
  waveform, so the same `ws_i2c_recover_step` is host-tested with simulated pins
  (`firmware/test_policy.c`) and drives the real pins in `sensor.c`. A link-time seam would force
  every build that links `stage0.c` (the fuzzers, the host tests) to define pin stubs.

How the stack bound treats indirect calls: `tools/stack_report.py` follows direct calls exactly; a
call through a pointer may reach any function whose address is taken (from the object files'
relocations) and that is linked, with at most two pointer hops on one stack (main loop → task →
driver callback) and two nested interrupts. The changes above removed four of our own targets from
that conservative set, so those paths are now computed exactly.

Pointer dereference: one level wherever we can choose. Struct members are reached through one pointer
(`p->x`); `held[i][k]` is a two-dimensional array, not a pointer to pointers. One deliberate
exception: `ws_cmd_find(const char *const names[])` takes the command-name table, an array of string
pointers.

## Rule 10: all warnings, zero warnings, static analysis

**Complies.** What CI runs on every push and pull request (`.github/workflows/ci.yml`):
- **Compiler**, our C only (`STRICT` in `firmware/board/nucleo-wl55jc/board.mk`; ST's code builds with
  `-Wall`): `-Wall -Wextra -Wshadow -Wconversion -Wsign-conversion -Wcast-qual -Wstrict-prototypes
  -Wmissing-prototypes -Wundef -Wdouble-promotion -Wformat=2 -Wnull-dereference` and, added for this
  rule, `-Wpedantic -Wformat-signedness -Wformat-overflow=2 -Wformat-truncation=2 -Wvla -Walloca
  -Wcast-align -Wpointer-arith -Wredundant-decls -Wold-style-definition -Wmissing-declarations
  -Wwrite-strings -Wjump-misses-init -Wlogical-op -Wduplicated-cond -Wduplicated-branches
  -Wswitch-default -Wfloat-equal -Wunused-macros -Wstack-usage=512`, all with `-Werror`. Both roles
  build with zero warnings, and so does `firmware/rangetest`'s strict file.
- **Console formats are now checked.** ST's `UTIL_ADV_TRACE_COND_FSend` has no `format` attribute, so
  GCC never compared `APP_PRINTF`'s formats with their arguments on the target. `sys_app.h` now passes
  the same arguments to a never-called `printf`-attributed function as well (no code). It found three
  `int` constants printed with `%u` (harmless; now unsigned).
- **GCC's static analyser** (`-fanalyzer`) on our C for both roles: zero findings.
- **Cppcheck 2.22.0** (`tools/cppcheck.sh`; the pinned `cppcheck==1.5.3` wheel in
  `requirements-dev.txt`), warning, style, performance and portability checks, exhaustive: zero
  findings. It runs without the HAL and ST utility include paths (`--suppress=missingInclude`), so it
  analyses our code without ST's types and does not cover the board files: a lighter check than the
  compiler's own, which sees everything. Its first run found 14: two variables whose scope could shrink, a pointer that could be
  const, a static assert it misread (now `!= 0`), and ST callback signatures that we cannot make
  const, suppressed inline with the reason (`/* cppcheck-suppress … ; ST's … signature */`).
- **Our own analyses**: worst-case stack (`make stack`), no blocking call reachable at run time
  (`make waits`, `tools/blocking_report.py`), function size and duplication, loop bounds, no heap,
  the flash budget, reproducible builds, libFuzzer on the four input parsers, and the host harnesses
  under UBSan (and ASan where it can be preloaded).

Deviation: "daily" becomes "every push". With every tool pinned, a run on unchanged code repeats the
last result, so a schedule would add nothing; any change is analysed before it is merged.

## What this cost

Measured from clean trees (same version-string length) before (`1947b40`) and after this work:

| | Before | After | Change |
|---|---|---|---|
| TX flash (code + data) | 57,136 B (87.2 %) | 57,744 B (88.1 %) | +608 B: the checks and their reporting +664, the narrower node state +80, the loop and macro changes +16, the link-time seams −120, the parser −32 |
| RX flash | 34,072 B (52.0 %) | 34,152 B (52.1 %) | +80 B: the checks and their reporting +128, the link-time seams −48 |
| TX worst-case stack (`make stack`) | 5,648 B | 5,744 B | +96 B (of 8,192 B) |
| RX worst-case stack | 2,588 B | 2,588 B | 0 |

TX keeps 1,238 B below the 90 % guard.
