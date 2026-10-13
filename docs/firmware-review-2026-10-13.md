# Stage 0 firmware roadmap: synthesis of the architecture, robustness, sensor and protocol/test reviews

Scope: `firmware/stage0-node`, `firmware/common`, `firmware/stage0.c`, the `ws0/` gateway contract and the tests. Four specialist reviews (38 findings) went through skeptic verification. Only claims that survived are kept, and the key ones were re-read in the code for this synthesis.

---

> **Status, 2026-10-13 evening (release `0f456040fe54`):** implemented: P1 (WIPE keeps counters and
> epoch, gap G17), P2 (strict `PROVISION` parser, key cleared from console buffers), the §2.2 sensor
> items (`rc=` on `#sample`, internal I2C pull-ups, `#sensor` boot check), the I2C bus-recovery STOP
> fix (`ws_i2c_recover()`, host-tested), health reports while probing, and Clint's probing decision
> (live reading every minute while probing in SURPLUS/NORMAL; back-off only in CONSERVE), plus the
> simulator's 5-per-minute drain. The rest of this review is unchanged and still open.

> **Status update (later 2026-10-13):** also done: P4 (gateway counter high-water mark in
> `gateway-nonces.sqlite3`, raised durably before each commit; `provision-node` refuses a board at or
> below it; `tests/test_counter_regression.py`), P5/P6/P7 (UART error re-arm, RX relisten after 5 silent
> minutes, TX consecutive-failure watchdog and boot retry), P3 (`node_store.c` over a `ws_flash` ops
> struct, host flash simulator with a power cut at every operation, `tests/test_store_powercut.py`),
> and CI (`.github/workflows/ci.yml`). The power-cut sweep found and pinned four store bugs, all fixed:
> an ACKed record could return after a cut during a journal wrap; an interrupted WIPE could leave
> records on an unprovisioned board; the abandoned total could drop after a failed write; lost records
> could go uncounted after a failed write.

## 1. Executive summary

- **The firmware is in good shape for an MVP.** The hard parts are done carefully:
  - Durable counter reservation before sealing (`app_tx.c:181-182`).
  - Commit-last flash records, with a header-last meta compaction.
  - Crypto that is host-tested and checked again by a boot KAT using the same Python vectors.
  - A watchdog that checks real progress, not just a spinning loop.
  - An SHT45 driver that is pure C and host-tested.
  
  Nothing here needs a rewrite.
- **Top risk (critical): nonce reuse after WIPE.** `store_wipe()` (`node_store.c:300-303`) erases both meta pages, so the AES-CCM counter restarts at 1 (`node_store.c:126-134`). The gateway has no per-node counter high-water mark (`ws0/service.py:61-91`), so reusing a key after a wipe would go **undetected**.
  - `docs/CONTEXT-PACK.md:45` has already been corrected.
  - `docs/hardware/nucleo-wl55jc-bringup.md:295` still says the board will be "re-provisioned with the `run-hw` key and the next epoch floor". Fix that line today. Fix the firmware in the next release.
- **The second risk is test coverage, not code quality.** The two modules that decide security and H01 have no host tests:
  - `node_store.c` (nonce counter, journal, power-fail recovery).
  - The policy inside `app_tx.c` (backlog, link probing, strikes, airtime). The bench already saw a 121.6 s backfill against the 120 s limit (`bringup.md:299`).
  
  The best-value investment is a flash-port seam plus a power-cut simulator, then a pure `tx_policy` extraction.
- **Some failures are silent on the H01 path** (each is a few lines to fix):
  - A UART overrun stops the RX console, which carries the ACK downlink, and it is never re-armed.
  - The RX "really listening" check reads the driver's cached state, not the radio chip.
  - A TX that keeps failing to send is still reported as healthy.
- **Tonight's SHT45 test:** nothing blocks it. One small change is strongly advised first: print the `sensor_read()` return code in `#sample`, and turn on the I2C pull-ups. Without it, every fault shows only as `valid=0`.
- **Do not refactor `app_tx.c` into five modules before H01.** Extract only the pure arithmetic, with no change in behaviour. Leave the module split for Stage 1 preparation, between H01 and Stage 1.
- **Freeze rule:**
  - Every step below is its own entry in `RELEASES.md`.
  - Do no code changes while an H01 run is in progress.
  - No test criterion is loosened anywhere in this plan.

---

## 2. Before tonight's SHT45 test

### 2.1 Must-do (docs only, no firmware)

1. **Fix `docs/hardware/nucleo-wl55jc-bringup.md:295`.** Replace "until it is re-provisioned with the `run-hw` key and the next epoch floor" with a pointer to `docs/runbook-moving-boards.md` options A, B or C: move the gateway with its key, copy `run-office` privately, or use a new key. CONTEXT-PACK and the runbook already say "never reuse". The bring-up log is the last place that contradicts them.

### 2.2 Strongly recommended build (about 10 lines; record it in RELEASES.md if any evidence will name it)

| Change | Where | Why |
|---|---|---|
| Keep the return code: `int rc = sensor_read(&t,&h); int valid = rc == 0;` and add `rc=%d` to `#sample` | `app_tx.c:395`, `:401` | Tells the faults apart: -2 = address NACK (wiring or pull-ups), -3 = read NACK (timing), -4 = CRC (noise or cable). Today all three print as `valid=0`. |
| Turn on the internal pull-ups: `.Pull = GPIO_PULLUP` | `sensor.c:20` and the recovery GPIO in `sensor.c:51` | With the STEMMA cable unplugged, the breakout's pull-ups go with it and both lines float, so the fault code becomes random. With the about 40 kΩ internal pull-ups, an absent sensor always reads as a clean -2. The breakout's 10 kΩ stay the real pull-ups. |
| Optional: probe at boot by sending soft reset `0x94` and one read, then print `#sensor ok` or `#sensor absent rc=N` | `sensor.c` `sensor_init` | Confirms the sensor answers before the first minute. |

Embedded note: I2C lines are "open-drain". Devices can only pull a line low. A resistor (the pull-up) brings it back high. If nothing pulls the line up, it floats and reads at random.

### 2.3 Hardware test plan for tonight (steps 0-6; steps 7-10 wait for the pre-H01 release candidate)

| Step | Action | Pass | Fail |
|---|---|---|---|
| 0 | Power off. Wire SCL to CN10.3 (PA12), SDA to CN10.5 (PA11), GND to CN10.9, 3V3 to **CN7.16**. Meter-check that red is not on CN7.18 (5 V) and that 3V3 and GND are not shorted. | Wiring matches `docs/protocol-stack.md:104-107` | Anything on CN7.18 |
| 1 | Power on and watch the TX console | `#boot … kat=pass`; with the probe, `#sensor ok` | No boot line, KAT fail |
| 2 | First reading | `#sample … valid=1 t=NNNN rh=NNNN`, in 0.01 units. t within ±1.5 °C and rh within ±8 %RH of a room reference. The gateway row is `quality=valid` with `temperature_c == t/100` exactly. | `valid=0`, or the values are implausible |
| 3 | 15-minute soak | Every sample `valid=1`, `sensor_faults=0` (the `#counts` line of `STATUS`), no `#nack`, and the change at rest is under 0.3 °C per minute | Any fault, or any `#nack` on a valid reading |
| 4 | Breathe on the sensor | RH rises by more than 10 %RH, T rises, and both return to baseline within minutes | No response |
| 5 | Unplug the STEMMA cable between samples and leave it out for at least 3 minutes | Each sample is `valid=0` (`rc=-2` with pull-ups), `sensor_faults` goes up by 1 per minute, the gateway stores `sensor_fault` with null T and RH, the exchange is still ACKed, and there is **no new `#boot`** | A reboot, a hang, or a fault that reaches the gateway as a number |
| 6 | Replug | The first or second sample after replug is `valid=1` | `valid=0` for more than 2 samples, or `#boot … reset=power` on replug (inrush on 3V3: note it for G14 and keep hot-plug out of the field procedure) |

Global fail conditions:
- Any sensor fault reaches the gateway as a number.
- Any reboot is caused by the sensor path.

Bench caveat: a USB dropout makes the ST-LINK reset the MCU. Identify those resets by the reset cause and the ST-LINK behaviour, and do not count them against the sensor path.

---

## 3. Before H01: prioritized list

Effort: S = under half a day, M = 1-3 days. Releases are listed in the order of section 5.

| # | Severity | Effort | Files | Concrete change |
|---|---|---|---|---|
| P1 | **critical** | S | `node_store.c:300-303`, `app_tx.c:484-500` | `store_wipe` keeps `WS_META_PAGE_A/B` and erases only config and journal, so the counter and epoch rise for the life of the board. **Ship it in the same release as P2.** Once meta survives a WIPE, a saturated epoch floor can only be cleared with a debugger. Bench check: `STATUS ctr` after WIPE+PROVISION is greater than before. |
| P2 | medium (paired with P1) | S | `app_tx.c:488-499` | Make the PROVISION parser strict:<br>• digits only, with an overflow check (`id > 0xFFFFFFFFUL` is dead code on a 32-bit `unsigned long`);<br>• `strtoul` must not see a leading `-`;<br>• exact field count, with no trailing garbage after the floor;<br>• `floor < 0xFFFF0000`;<br>• zeroize the `line` and `isr_buf` buffers after PROVISION. |
| P3 | high | M | `node_store.c:27-51` → new `flash_port.h` + `flash_stm32wl.c`; new host `sim_flash.c` + test | Put the three primitives (`read64`, `prog64`, `erase`) behind an ops struct, the same pattern as `ws_i2c`. The host RAM model follows the STM32WL rules: erased = all ones, each double-word programmed once, a cut during a program leaves either a partial value or an ECC fault, and a cut during an erase leaves partially erased content. The base address maps to `0x0800xxxx`.<br>Run a scripted workload (reserve, append, ack, compaction, wrap) and cut power at every operation. Assert: counters never repeat or go backwards; epochs strictly increase; no ACKed record comes back; no pending record disappears without being counted; lost and abandoned never decrease.<br>Add a `store_ready` guard to the mutators. This complements the physical G7 storm and does not replace it. |
| P4 | medium | S | `ws0/service.py`, `ws0/protocol.py` (`Nonces` DB), tests | The gateway stores `max_node_counter` per key binding, covering OBS and DIAG together. It updates only after authentication. On a counter at or below the max: no reply, nothing stored, increment `counter_regression`, raise a loud `/v1/status` alarm ("possible key reuse: re-key"), and keep the raw frame. Retries always use fresh counters (`store_next_counter`), so this check has no false positives. C7/C8 change from "not detected" to "detected on the first frame". `provision-node` shows the high-water mark. No wire change. |
| P5 | medium | S | `Core/Src/usart_if.c` (USER CODE), `app_rx.c:57-65` | Add `HAL_UART_ErrorCallback`: clear ORE/FE/NE/PE, call `HAL_UART_Receive_IT(&huart2,&charRx,1)` again, and count `uart_errors` in `#alive` and STATUS. `rx_healthy` also requires `huart2.RxState == HAL_UART_STATE_BUSY_RX`, with one re-arm attempt before a watchdog reset. Today no error callback exists anywhere in `App/` or `Core/`. |
| P6 | medium | S | `app_rx.c:36-64`, `docs/failure-modes.md:253` | `Radio.GetStatus()` returns a cached software mode (`vendor/…/radio.c:737-744`). Timestamp the last RxDone or RxError. If none arrives within N minutes (N above a few TX intervals), run `Radio.Standby(); Radio.Rx(0)` and count it as `relistens=` in `#alive`. The gateway alarms when `listening=1` but no frames arrive for K intervals. Correct the M2 wording. |
| P7 | medium | S | `app_tx.c:430-437`, `:182`, `:188`, `:533-542` | Count **consecutive failed attempts** only: journal append rc≠0, `store_next_counter` failure, or `Radio.Send` ≠ OK. Reset on any success. Above about 10, `tx_healthy` returns 0. Minutes where the policy suppressed sending must not count (PROBING between probes, CONSERVE, CRITICAL). A transient store-init or epoch-reserve failure at boot schedules one `NVIC_SystemReset` after about 10 minutes. Never do this when unprovisioned or when the KAT fails. |
| P8 | medium | M | `app_tx.c:198-270`, `:331`, `:408-422` → new HAL-free `tx_policy.c/.h` | Extract with **no behaviour change**: `lora_airtime_ms`, the queue plan (backlog, airtime cap, probing), link-state transitions, strike settlement, the reply-classification predicate, and `energy_state()` behind a header. ctypes tests cover:<br>• airtime against Semtech calculator values;<br>• the probing back-off 120/240/480/900 s;<br>• strikes only when some reply arrived;<br>• a scripted outage→recovery case asserting the first backlog item commits within 120 s under the H01 radio settings, to reproduce and pin the 121.6 s observation. |
| P9 | medium | S | `app_tx.c:446-460`, `:467-476` | TEST-FLASH-STORM stops itself after a fixed budget (about 30 s) and prints `#storm stopped`. Today it can wear the journal flash to its rated limit in about 13 h. Wrap `TEST-HANG` and `TEST-FLASH-STORM` in `#if WS_BENCH_COMMANDS`, and record the flag per release. |
| P10 | medium | S | `Makefile:19,75,105-109`, `tools/h01_report.py`, new `tools/release.sh` | Make releases harder to get wrong:<br>• Add `-ffile-prefix-map` (the ELF embeds `/Users/clint/...` from `-g3`), or declare the `.bin` the only canonical artifact.<br>• `make release` refuses a `-dirty` or `unknown` tree, builds twice, compares, and prints the RELEASES.md block.<br>• `h01_report.py --release <hash>` is required and must exist in RELEASES.md; record `STATUS fw=` at the start and end of the run. |
| P11 | medium | S | `.github/workflows/ci.yml`, `tests/test_frame.py:37` | Add CI. See section 6. |
| P12 | medium | S | `main.c` USER CODE before `SystemClock_Config`, `watchdog.c`, `main.c:170-173` | Arm the IWDG (and read the reset cause) before the LSE and RTC start-up. Their timeouts never expire because `HAL_GetTick()` returns 0 until the timer server starts (`sys_app.c:223-234`, which carries ST's own warning). `watchdog_start` then only registers the supervised check. `Error_Handler` calls `NVIC_SystemReset()`. |
| P13 | medium | S | `stage0.c`, `app_tx.c:395-401`, `sensor.c`, `test_sensor.c` | Make the sensor ready for H01:<br>• Name the sensor return codes in an enum in `stage0.h`.<br>• Add a range code for t < -4000 or t > 12500, so the minute goes out as `valid=0` instead of being NACKed and abandoned (`gateway.py:62` uses -40..125). Cite the limits in `protocol.md`.<br>• Change the measurement delay to 12 ms (`stage0.c:16`; real wait today is 8.8-9.8 ms against an 8.3 ms maximum).<br>• In recovery, write PA11/PA12 ODR high **before** `HAL_GPIO_Init` (`sensor.c:51-55`), return whether SDA is still low, and send a soft reset `0x94` after recovery.<br>• Make the test bus table-driven: raw 0x0000 and 0xFFFF, about -20 °C, RH clamps at both ends, a corrupted T-CRC with a good RH word.<br>• `i2c_start` returns its HAL status, printed at boot. |
| P14 | low | S | `app_rx.c:67-105` | At the top of `process()`, snapshot `event`, `rx_len` and a copy of `rx_frame` with interrupts briefly off, then clear `event`, as TX already does (`app_tx.c:365-366`). Delete the trailing `event = EV_NONE`. Add a dropped-event counter to `#alive`. |
| P15 | low | S | `app_tx.c:272-298`, `stage0.c`, `watchdog.c`, `tests/test_frame.py` | Move packing into `ws_pack_diag(out, const ws_diag_t*)` in `stage0.c`, plus a ctypes test that unpacks through `ws0.protocol.DIAG` and checks the `RESET_CAUSES`/`LINK_STATES` indices. Watchdog returns an enum alongside the string. Leave "brownout" as reserved; BORRST semantics stay unchanged until G14. |
| P16 | low | S | `flash_layout.h`, `node_store.c`, `app_tx.c` | Add `_Static_assert`s (none exist today):<br>• `JOURNAL_FIRST + PAGES == 128`;<br>• `SLOT_BYTES*51 + 8 <= WS_PAGE_SIZE`;<br>• `MAX_QUEUE-1 >= max(backlog_limit)`;<br>• config page above the linker image.<br>The gateway compares the radio fingerprints in the TX and RX `#boot` lines. |
| P17 | medium | S | `node_store.c:126-128`, `app_tx.c:533-536` | Fail closed when counter state is lost. `store_meta_init` returns a distinct "created fresh" code. If the node is provisioned and meta was created fresh: print `#error counter-state-lost: re-key required`, show solid red, do not transmit, and keep feeding the watchdog. |

---

## 4. Target architecture, Stage 0 → Stage 1

### 4.1 Module map

```
firmware/
  common/                      HAL-free, host-compiled, shared by roles + tests
    ws_frame.{c,h}             seal/open (Mbed TLS CCM); Stage 1: length-param seal + ws_reply struct
    stage0.{c,h}               obs/diag packing, SHT4x driver over ws_i2c, sensor status enum
    tx_policy.{c,h}     [P8]   airtime, queue plan, link FSM, strikes, reply classify, energy_t
    node_store.{c,h}           meta log (epoch/counter/totals), config, journal  — over ws_flash ops [P3]
    (Stage 1 split) nv_config / nv_mono / journal over ws_nvm backend
  port/   (thin HAL shims, on target only)
    flash_stm32wl.c     [P3]   ws_flash ops: HAL_FLASH_*, ECC NMI flag
    sensor.c                   ws_i2c ops on I2C2 + bus recovery (exists)
    watchdog.c                 IWDG arm + supervised check (exists; P12 splits arm/supervise)
    energy_usb.c        [P8]   energy_state() -> EN_NORMAL (fail-closed rule lives in tx_policy)
  App/
    app_tx.c                   orchestration only: sequencer tasks, radio callbacks, exchange, console
    app_rx.c                   keyless bridge
  tests/ + host sim
    sim_flash.c         [P3]   NOR-semantics RAM flash with power-cut injection
```

### 4.2 What stays tied to the HAL and what is host-testable

- **Host-testable (pure C, no HAL includes):**
  - Framing and crypto, observation and DIAG packing, the SHT4x protocol and CRC.
  - Policy (backlog, link, strikes, airtime).
  - The node_store logic, over a flash ops struct.
  - Console argument parsing (Stage 1 move into a `console_parse.c`).
- **HAL-bound, kept small:**
  - The flash, I2C and UART shims.
  - IWDG, RTC backup registers and time.
  - Radio callbacks, sequencer wiring, `main.c` and the CubeMX `Core/`.

A useful rule: if a function takes only integers and buffers and returns a decision, it belongs in `common/`, where it gets host tests.

### 4.3 Seams for Stage 1 (prepare the seam, do not build the feature)

| Seam | Stage 0 shape | Stage 1 plugs in |
|---|---|---|
| **Energy state** | `energy_t energy_state(void)` behind a header (P8). The USB build returns NORMAL. Host tests inject every state, including "unknown → CONSERVE". | A battery/solar monitor implementation. `LOW_POWER_DISABLE=1` stays through H01. |
| **Sensors** | `ws_i2c` ops + `ws_sht45_read` + a named status enum (P13). The journal slot and the plaintext length come from **one** constant. `protocol.md` notes that bytes 22-23 are reserved for a future versioned or multi-channel plaintext. | A sensor table `{name, init, read(ctx, ws_meas_t*)}`, a sampler, per-channel validity in a new frame version, and a two-phase SHT4x read (start, then fetch 10 ms later) so the MCU can sleep between them. |
| **Storage backend** | The `ws_flash` ops struct (P3) and the simulator. | Split into `nv_config` (internal flash), `nv_mono` (internal flash) and `journal` over a `ws_nvm` backend (SPI NOR, 4 KB sectors). Make `jref_t` an opaque index. Track pending records with head/tail or per-sector counts, not a 43k-bit bitmap (about 5.4 KB of RAM). Find records from (epoch, seq). Add a per-record CRC on meta and journal headers, plus a layout-version field. |
| **Transport** | `ws_seal_kind`/`ws_open_reply` with fixed sizes. The RX filters on exact length and version. | A length-parameterized seal with a per-kind length table, a `ws_reply` struct, and an RX that forwards any `'WS'` frame within the length bounds (the gateway decides policy). Later, a shared radio-event ring if a third role or low-power mode needs it. Timer-driven exchange steps replace `HAL_Delay(INTER_FRAME_MS)`. |
| **Board** | Three Core/ copies (pingpong, rangetest, stage0-node). | `firmware/board/<board>/` selected by `BOARD=`. rangetest builds from the shared `radio_cfg`. |

---

## 5. Incremental refactor sequence

Each step is small, has its own verification, and keeps the firmware releasable. "Release" means a new `RELEASES.md` entry with two-build hashes. Never change firmware during an H01 run.

| # | Step | Verification | New release? |
|---|---|---|---|
| 0 | Fix the `bringup.md:295` doc line (2.1) | Review | No (docs) |
| 1 | Sensor diagnostics for tonight: `rc=` + pull-ups (+ optional boot probe) | Tonight's plan, steps 0-6 | Yes, if any evidence names it |
| 2 | CI skeleton: host tests with `WS_REQUIRE_VENDOR=1`, both roles built twice with hashes compared (P11) | Green CI; delete vendor/ and confirm the job fails instead of skipping | No (tooling) |
| 3 | P1 + P2 (+ P17): WIPE keeps meta, strict PROVISION, fail-closed on lost counter state | Bench: ctr after WIPE+PROVISION is above the value before; a malformed floor is rejected; a forced meta loss gives `#error counter-state-lost` | **Yes** |
| 4 | P4 gateway counter high-water mark | Python tests: replay gets no ACK, a replayed DIAG is not stored, a simulated wipe raises the alarm | No (gateway), but note it in the H01 runbook |
| 5 | P3 flash port, with the binary unchanged where possible + `sim_flash` power-cut test + `store_ready` | Host cut-at-every-op test passes; G7 part A storm re-run on the bench | **Yes** (note whether the `.bin` changed) |
| 6 | P5 + P6 + P14: UART re-arm, real RX liveness, RX event snapshot | Bench: inject an overrun (paste a burst) and the console recovers with a `uart_errors` count; `relistens=` appears after a forced silence | **Yes** |
| 7 | P7 + P12 + P9: TX failure counter, early IWDG, bounded storm / bench flag | Bench: a forced Radio.Send failure leads to a watchdog reset with `reset=watchdog`; the storm stops itself; boot time stays well under 8 s | **Yes** |
| 8 | P13 + P15 + P16: sensor hardening, `ws_pack_diag`, static asserts | Expanded `test_sensor.c` + DIAG ctypes test; tonight's plan steps 7-10 (single-wire faults, stuck SDA, plug cycling, overnight soak) on this RC | **Yes** |
| 9 | P8 `tx_policy` extraction with no behaviour change | Host policy tests incl. outage→recovery ≤120 s; bench outage replay matches pre-refactor logs | **Yes** |
| 10 | P10 release tooling; tag this release as the **H01 candidate** and freeze | `make release` reproduces; `h01_report --release` validates it | Release = the H01 candidate |
| — | **H01 run** (no firmware changes during the run) | H01 criteria unchanged | — |
| 11+ (after H01) | Stage 1 preparation: console table + `console_parse.c`, `node_time`, explicit exchange FSM, store split + `ws_nvm` + opaque `jref_t`, meta/journal CRC + layout version, frame API generalization, board/ dir, MSB-LSB-MSB RTC read + preserving MSBticks | Host tests for each; each is its own release | Yes, each |

Steps 3-9 can be merged into fewer releases if bench time is short. Keep step 3 first, and keep step 5 separate from step 9 so a regression points to one change.

---

## 6. Testing and tooling plan

**Host tests:**
- Add one host-build helper (a make target or a shared pytest fixture) when the first new C module lands. It compiles `common/*.c` + `sim_flash.c` with `-Wall -Wextra -Werror -fsanitize=address,undefined` into one `.so`. All ctypes tests load that one artifact, replacing the ad-hoc `cc` calls in `test_frame.py:46`.
- New suites:
  - `test_store_powercut` (P3)
  - `test_tx_policy` (P8)
  - a table-driven `test_sensor` (P13)
  - `test_diag_pack` (P15)
  - `test_provision_parse` (P2; a fuzz-style table)
  - gateway `test_counter_regression` (P4)
  - Later: RTC wrap arithmetic (stage1+)
- Keep the existing KAT vectors as fixed regression tests through every refactor.

**CI (GitHub Actions; no `.github/` exists today):**
- Host job: Python 3.12, cached `tools/fetch-vendor.sh`, then `WS_REQUIRE_VENDOR=1 WS0_UNSAFE_FAST_FSYNC=1 python -m unittest discover -s tests`. The `skipUnless` at `test_frame.py:37` must fail when the env var is set.
- Firmware job: xPack 15.2.1-1.1 with its SHA-256 verified. Build `ROLE=tx` and `ROLE=rx` twice and compare the `.bin` hashes. Print `size`, which guards the 64 KB link region (TX is at about 53 KB). Upload the bins and maps.
- Optional: `-Wextra -Werror` for `App/` and `common/` only. They are reported as already warning-clean. Never apply it to Cube sources.
- For commits named in RELEASES.md, compare against the recorded `.bin` hash. A match from a Linux runner is a useful extra check, and a mismatch is something to investigate, not a gate.

**Release automation (P10):**
- `make release` refuses `-dirty` or `unknown`, builds both roles twice from a clean worktree, and prints the RELEASES.md block.
- `make flash` prints the sha256 and says whether it is recorded. With `H01=1` it refuses an unrecorded build.
- Record `WS_BENCH_COMMANDS` per release.
- `h01_report.py` requires `--release`, and the evidence folder holds the `STATUS fw=` lines from the start and end of the run.

---

## 7. Appendix: refuted and downgraded findings (one line each)

No finding was fully refuted. These were downgraded or corrected:

- **architecture-1** (god module, high → medium): the evidence is right, but a full 5-module split before H01 adds risk. Only the pure policy arithmetic gets extracted now (P8). The `:182` exit path skipping strike settlement only happens when the store is already broken.
- **architecture-3 / robustness-9** (RX mailbox, merged, → low): the race is real, but a second radio event needs tens of ms of preamble and retries cover any loss. Two-line snapshot fix (P14); the ring buffer is deferred.
- **architecture-4** (DIAG packing, medium → low): today's ordering matches Python. This is a drift risk, not a current bug.
- **architecture-5** (storage geometry, → low, no change before H01): the Stage 1 design note is kept; making `jref_t` opaque now would touch the critical module for no gain.
- **architecture-6** (SHT45-shaped API, → low, Stage 1): a `ws_meas_t` wrapper now adds API with no wire benefit. Only the single-constant slot size is kept.
- **architecture-7** (blocking delays, → low): partly wrong. HAL_Delay is RTC-based, not SysTick-based (`sys_app.c:200-254`), and Stage 0 sends at most 6 frames per minute, not 21.
- **architecture-9** (warnings / host build, → low): warning flags do not change the generated code, but `-g3` records the switches, so the ELF hash changes.
- **robustness-1 / protocol-tests-1** (merged, critical, kept): one correction. The gateway does *not* reject replayed counters, so reuse would go undetected (hence P4). CONTEXT-PACK has since been fixed; bringup.md:295 has not.
- **robustness-2** (fail-open meta, high → medium): losing both headers at once while config survives is unlikely. The realistic trigger is a layout change, which release discipline already gates. The layout-version field is deferred to the first layout change.
- **robustness-3** (early watchdog, high → medium): a slow LSE only delays boot. Only a dead crystal hangs it.
- **robustness-4** (UART overrun, high → medium): RX does no flash erases, and a bench USB dropout resets the MCU anyway. The likelihood is low, but the fix is cheap.
- **robustness-6** (silent TX stall, kept medium): corrected to count failed attempts only. Counting minutes without a send would trip falsely during PROBING, CONSERVE or CRITICAL.
- **robustness-7** (flash storm, medium/now → low/before-H01): only reachable through a bench command.
- **robustness-8, -11** (meta CRC, RTC wrap): confirmed but stage1+, because H01's 24 h run and the deferred G7 part B do not exercise them.
- **sensor-2** (range mismatch, medium → low): the rejected frame is kept in the reject log, H01 counts both outcomes as invalid, and Chicago never reaches -40 °C.
- **sensor-3** (bus recovery, medium → low): in the real stuck-SDA case the loop does produce a STOP. In the SDA-high case the stray pulse is harmless. The 1 ms half-periods are legal, so the fix is two lines, with no GPIO abstraction.
- **sensor-6** (test vectors, medium → low): no current signed-promotion bug exists; this is hygiene.
- **sensor-7** (HAL init return codes, → low): HAL_I2C_Init practically cannot fail here. Folded into the boot log line only.
- **sensor-8** (sensor seams): trimmed to an enum plus a protocol.md note; the module split is deferred.
- **sensor-9** (test plan): trimmed to steps 0-6 tonight. Caveat: with internal pull-ups on, a 3V3-only lift can back-power the sensor.
- **protocol-tests-2** (counter high-water mark, high → medium): the DoS argument is weak. Its value is detection.
- **protocol-tests-3** (store tests, high, kept): the claimed "page-0 firmware overwrite" hazard is refuted, because STM32WL refuses to program a double-word that is not erased (PROGERR). `store_ready` stays as hygiene only.
- **protocol-tests-4**: the line citation was corrected to `bringup.md:299`. Having the Python harness drive the C policy is deferred.
- **protocol-tests-5** (PROVISION parser, kept medium): only because P1 makes a saturated floor survive a WIPE. On its own it would be low.
- **protocol-tests-6** (CI, now → before-H01): not needed for tonight's sensor test.
- **protocol-tests-8** (console attack surface): H01 builds do not need TEST-FLASH-STORM unless G7 evidence is gathered with that release. Pick one flag setting per release and record it.

Key files: `/Users/clint/code/weather-station-2026/weather-station-2026/firmware/stage0-node/App/node_store.c`, `/Users/clint/code/weather-station-2026/weather-station-2026/firmware/stage0-node/App/app_tx.c`, `/Users/clint/code/weather-station-2026/weather-station-2026/firmware/stage0-node/App/app_rx.c`, `/Users/clint/code/weather-station-2026/weather-station-2026/firmware/stage0-node/App/sensor.c`, `/Users/clint/code/weather-station-2026/weather-station-2026/firmware/stage0.c`, `/Users/clint/code/weather-station-2026/weather-station-2026/ws0/service.py`, `/Users/clint/code/weather-station-2026/weather-station-2026/docs/hardware/nucleo-wl55jc-bringup.md`
