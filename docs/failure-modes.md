# Stage-0 communication: failure modes, recovery, and loss budget

> **Document type:** Failure modes and effects analysis (FMEA) and recovery runbook.
> **Applies to:** Stage 0 data path: TX board → LoRa → RX board → USB → gateway (`ws0`) → SQLite. Protocol draft 4 and later.
> **Status:** Most behaviors exist in code. Column **Verified** tells you what has evidence. Section 10 lists the open issues. **H01 is NOT RUN.**
> **Related:** [`protocol-stack.md`](protocol-stack.md) (how each layer operates) · [`protocol.md`](protocol.md) (byte formats) · [`H01-checklist.md`](H01-checklist.md).

---

## 1. Purpose and scope

This document defines the behavior of the Stage-0 communication system when a part of it does not operate correctly. For each failure, it gives:

- how the system detects the failure,
- what the system does immediately,
- how the system recovers (automatically, by an operator, or not at all),
- what data the failure can delay or lose,
- the effect on the H01 acceptance test,
- the evidence that the behavior is correct.

**In scope:** the TX board, the RX board, the radio link, the USB link, the gateway process, its SQLite files, and the host computer.
**Out of scope:** Stage 1 and later items (battery, solar, RS-485 modules, heaters), and MQTT/Home Assistant availability. These components are downstream of storage, so their failures cannot cause data loss.

### 1.1 Operating context: the bench is not the use case

The protocol exists for one job: **an unattended station sends periodic sensor readings over a long radio path, from battery and solar power, to an indoor receiver.** Stage 0 runs on a desk with USB power. Many failures that cost nothing on the bench cost energy, airtime, or data in the field. This document classifies each failure for the **deployment**, and it gives the bench evidence where it exists.

| Property | Stage-0 bench (now) | Deployment (design target) |
|---|---|---|
| TX power | USB, unlimited | Protected 4S battery pack + 20–40 W solar. **Average budget ≤ 0.25 W for the complete station** (spec §4) |
| TX attendance | On the desk | Outdoors, unattended; a site visit is expensive |
| Distance | ~30 cm | Roof/yard to indoor receiver through walls; to be measured (H01). No range claim. |
| Radio settings | SF7, 0 dBm, RSSI ≈ −23 dBm | SF and power from the measured link budget: SF9–SF12, up to +22 dBm (§15.247 allows +30 dBm) |
| Airtime, 42-byte observation frame (draft 5) | 21.8 ms | 72 ms (SF9) to 453 ms (SF12) |
| Packet loss | Rare | **Routine.** Weather, snow on the antenna, interference, temperature |
| Gateway host | Mac, can sleep | Always-on Linux computer or SBC on mains (spec §1). It must not sleep. |
| Typical outage | Developer stops the gateway | **House power outage or storm.** The station keeps measuring on solar; the gateway is down. This is exactly what store-and-forward is for. |

**Design principle.** The node is the energy-limited and unattended side. The gateway is mains-powered and attended. Therefore:

1. The node must **fail cheaply.** A failure must not make it spend much more energy than normal operation.
2. Put decisions and extra work on the **gateway side** where possible (for example: NACKs, time checks, monitoring).
3. Never trade data safety for energy, and never trade energy for convenience.

### 1.2 Energy cost of a failed exchange

Each frame costs transmit energy plus the energy of the ACK receive window. The window is short when the ACK arrives. It stays open for the full **2,000 ms** when no ACK arrives.

| SF (500 kHz) | Airtime, 42-byte observation | TX charge at ~100 mA (+20 dBm class) | RX charge, full 2 s window at ~5 mA |
|---|---:|---:|---:|
| SF7 | 22 ms | 2.2 mC | 10 mC |
| SF10 | 134 ms | 13 mC | 10 mC |
| SF12 | 453 ms | 45 mC | 10 mC |

Draft 4 frames were 56 bytes (27 / 164 / 576 ms, 2.7 / 16 / 58 mC); the outage arithmetic below uses those.

*The current values are datasheet-class assumptions for the STM32WL. Stage 1 must measure them (spec H02).*

- In a **normal minute**, the node sends 1 frame and the ACK closes the window early.
- In a **failed minute**, the firmware sends **1 frame** and waits the **full 2 s**: the drain stops at the first missed ACK (with backlog pending: one more frame first, which a strike needs; see `protocol-stack.md` 9.5).
- After *K* = 3 silent minutes the node enters PROBING and sends only one live probe per back-off interval (2, 4, 8, then 15 min). The minutes between probes have no radio activity (`radio-energy-policy.md` §6).

Why PROBING exists: a rule that sends 3 frames per failed minute (live + 2 backlog), each with the full 2 s window, costs at SF12 and +20 dBm about 3 × (58 + 10) ≈ 200 mC per minute, against about 60 mC in a normal minute. Over a one-day gateway outage, that is about 290 C ≈ 80 mAh, or roughly **0.27 Wh/day** at 3.3 V: about **4–5 % of the 6 Wh/day core budget**, spent on a link that is known to be down. PROBING reduces this to about 100 probes, about 0.007 Wh/day. A timed ACK window would shorten each failed window further (§10, *Blind 2 s ACK window*).

---

## 2. Definitions

### 2.1 Recovery classes

| Class | Meaning |
|---|---|
| **AUTO** | The system recovers with no human action. No data is lost. Data can be late. |
| **AUTO-BOUNDED** | The system recovers with no human action. It can lose a defined, counted, small quantity of data. |
| **OPERATOR** | A person must do a procedure from section 9. Data is safe if the person acts before a stated deadline. |
| **UNRECOVERABLE** | Some data is lost permanently, or it was never acquired. The system must make the loss visible. |

### 2.2 Data custody states

One observation goes through these states. At each state, **one** component is responsible for it.

```mermaid
stateDiagram-v2
  direction LR
  [*] --> Acquired: sensor read (or fault)
  Acquired --> Journaled: flash slot committed
  Journaled --> InFlight: sealed + transmitted
  InFlight --> Journaled: no ACK (retry later)
  InFlight --> Committed: gateway SQLite COMMIT
  Committed --> Acknowledged: TX opens authentic ACK
  Committed --> Committed: ACK lost → duplicate → ACK again
  Acknowledged --> [*]: TX slot cleared
  Journaled --> Lost: ring full, page erased (counted)
  Acquired --> Lost: journal write failed
  note right of Committed
    From here, the gateway
    is the custodian.
  end note
```

| State | Custodian | Durable? | What destroys it |
|---|---|---|---|
| Acquired | TX RAM | No | TX reset before the journal write (a window of a few milliseconds) |
| Journaled / InFlight | TX flash | Yes | Journal overflow (counted), TX flash failure, `WIPE` |
| Committed | Gateway SQLite **and** TX flash | Yes (two copies) | Nothing, until the ACK arrives |
| Acknowledged | Gateway SQLite only | Yes (full flush on; see §6, *Host power cut during a SQLite commit*) | Loss or corruption of the gateway database |

**Key property:** An observation always has at least one durable custodian between the journal write and the end of its life. The TX board deletes its copy only after it verifies an authentic ACK. The gateway makes that ACK only after its commit.

---

## 3. Guarantees and loss budget

### 3.1 Invariants (must hold in every failure)

| Invariant | Mechanism | Verified |
|---|---|---|
| The gateway never sends an ACK for an observation that it did not commit. | `Gateway.receive`: commit, then seal ACK | Simulation `storage-failure`; unit `test_commit_failure_no_ack` |
| The TX board never deletes an observation without an authentic ACK for that identity. | `ws_open_ack` + `store_journal_find` | Unit `test_ack_tamper_keeps_pending` (simulator); bench (firmware) |
| No (key, nonce) pair is used two times. | Durable counter blocks; kind byte splits directions | Bench: reboot skips the block (8 → 257); reset during flash writes: the counter never went back over 71 boots (`evidence/g7-reset-during-write-2026-10-13/`); true power removal not tested (§10, *Power-removal test not done*). Key reuse after a WIPE: see §8.2. |
| No two different observations have the same identity. | Durable epoch before the first sample | Bench: epochs 1 → 2 → 3 over reboots (`hardware/nucleo-wl55jc-bringup.md`, "Reboot behaviour"); epochs always increased over 71 boots of the reset test; after `WIPE` + `provision-node` the epoch floor keeps identities unique (§8.2, *WIPE then re-provision under the same station name*). |
| The database stores each identity once. A changed payload with an old identity is rejected. | Primary key + payload comparison | Simulation `identity-collision`, `ack-loss` |
| An invalid or stale reading is never shown as current. | Validity flag, impossible fillers (draft 3), 180 s freshness, 5 s future quarantine | Unit + simulation `sensor-fault`, `clock-errors` |
| A replayed ACK cannot change the TX clock. | Counter echo in the ACK | Design + unit vectors; no adversarial bench test |

### 3.2 Loss budget

This is the data loss that the design accepts. **Items marked ⚠ need Clint's approval. They define how H01 and H11 read a failure.**

| Category | Accepted loss | Rationale |
|---|---|---|
| **Never acceptable** | Loss of a committed observation; a duplicate row; nonce reuse; an invalid or stale value shown as current | Spec §9, §11, H01, H11 |
| TX power cut during a journal write | **≤ 1 observation per power cut** (the slot in progress) | Flash cannot commit atomically faster than a power loss |
| TX unpowered (battery depleted, brown-out), or TX sensor absent | **All intervals while the TX board is down.** These readings never exist, so they are not "lost". They show as a time gap between two epochs. | No energy, no measurement. In deployment, prevention is the job of the power system (spec R03: 168 h without solar). |
| RX, gateway, or link down | **0 lost** if the outage is ≤ **65 h** (journal capacity: 3,906 one-minute records, T/RH build; 79 h in draft 4). Data is late. | Store-and-forward. A multi-day winter storm outage at the house can exceed 65 h; the 30-day target is H11 (external flash). |
| Outage > 65 h | **Oldest pending observations, 42 at a time** (one flash page of 48-byte slots). Counted on the TX board as `lost`. | **Approved by Clint 2026-10-12:** drop oldest first (newest data is more valuable). |
| Time unknown after a TX boot | Warm reset: the board keeps time trust across the reset (backup registers). Power loss: the gateway reconstructs the time of every reading in the epoch from the uptime field after the first sync. Residual: an epoch that ends before its first sync stays `unknown`. | Approved by Clint 2026-10-12. Evidence: bench warm reset `#time restored`; cold start reconstructed ±2 s; simulation `reboot-during-outage` 32/32 reconstructed. |
| Backlog drain | Backlog clears at up to **5 observations per minute** (NORMAL; `backlog_limit` in `firmware/common/ws_policy.c`) in addition to live data, and stops at the first missed ACK. An outage of *D* minutes takes about *D*/5 minutes to clear. | Live data has priority. ⚠ H11 must accept or raise this rate. |

### 3.3 H01 budget

H01 needs **≥ 1,426 of 1,440** one-minute intervals committed within 120 s of acquisition. So the run can miss **at most 14 intervals in 24 h**.

| Event during H01 | Intervals it costs |
|---|---|
| One lost frame or one lost ACK | **0.** The next minute resends the reading as the oldest backlog item. It commits at about t + 61 s, so it is still within 120 s. |
| Two lost exchanges in a row for one reading | 1 (it commits at about t + 121 s or later) |
| Outage of *N* minutes (any cause) | About *N* − 1 (live reading every minute in NORMAL; in CONSERVE up to 14 more, see below) |
| TX reboot (any cause) | Outage time only. Warm reset: no time loss. Power loss: first reading reconstructed by the gateway. |
| RX reboot | 0 to 1 |
| Gateway restart (a few seconds) | 0 |

**Probe back-off and H01 (Clint's decision, 2026-10-13).** SURPLUS and NORMAL send the live reading every minute while probing (`ws_link_may_send()`, `firmware/stage0.c`). Only CONSERVE backs off (2, 4, 8, then 15 min); there, one outage of 3 minutes or more can make up to 14 more readings late: the whole H01 budget. Stage 0 and H01 run in NORMAL.

---

## 4. Component behavior models

### 4.1 TX board

```mermaid
stateDiagram-v2
  [*] --> SelfTest
  SelfTest --> HALTED: KAT fail / flash init fail / epoch reserve fail
  SelfTest --> UNPROVISIONED: no valid config
  SelfTest --> NORMAL: provisioned, epoch reserved
  UNPROVISIONED --> SelfTest: PROVISION (reboot)
  NORMAL --> PROBING: 3 consecutive minutes with no answer
  PROBING --> NORMAL: any authentic ACK or NACK (to a probe)
  NORMAL --> TIME_UNKNOWN: >6 h since last time sync
  TIME_UNKNOWN --> NORMAL: ACK with matching echo
  PROBING --> OVERFLOW: journal ring full
  OVERFLOW --> PROBING: still no ACK (oldest page erased again)
  OVERFLOW --> NORMAL: authentic ACK
  state HALTED {
    [*] --> red_solid
  }
```

| State | LED | Samples? | Transmits? | Exit |
|---|---|---|---|---|
| NORMAL | Blue blip every 2 s; blue then green each minute | Yes | Yes | — |
| NORMAL, minute with a missed ACK (silent minutes 1–2) | Blue then **red** | Yes, journaled | 1 frame; the drain stops at the first miss | Next authentic ACK |
| PROBING (`link=probing`) | Blue then **red** at each probe; **no radio flash** in the minutes between probes | Yes, journaled | Live-only probe at 2, 4, 8, then every 15 min (scheduled from the exchange start) | Any answered probe |
| TIME_UNKNOWN | as NORMAL or PROBING | Yes, UTC = 0 | Yes | Next ACK with matching echo |
| OVERFLOW (not a separate firmware state) | as PROBING | Yes; erases the oldest page and counts `lost` | Probes only | Link returns; backlog drains |
| UNPROVISIONED | **Red solid** | No | No | `ws0 provision-node` |
| HALTED | **Red solid** | No | No | Operator (section 9) |

### 4.2 RX board

The RX board has one operating state: **continuous receive**. It leaves this state only to send one ACK, then it returns. It has no key and no stored data, so a reset loses only a frame or ACK that is in progress.

### 4.3 Gateway

| State | Detection | Behavior |
|---|---|---|
| Serving | `serve.out` "Stage 0 hardware; API …" | Normal |
| Rejecting | `receiver.log`: `rejected …` | No ACK; TX journals and retries |
| **Exited** | Process gone; no new lines in `receiver.log` | No ACKs; TX journals. launchd (`KeepAlive`) or systemd restarts it. |

---

## 5. Failure catalogue — peer unavailable

| Scenario | Detection | Immediate behavior | Recovery | Data impact | H01 | Verified |
|---|---|---|---|---|---|---|
| **Gateway process stopped** (crash, Ctrl-C, update). launchd/systemd restarts it. | No `#ack` on TX; red LED each minute; API down | RX prints frames; nobody answers. TX journals. | AUTO after restart (§9.1). Backlog up to 5/min. | None if restarted within 65 h | *N* − 1 | **Bench, 2026-10-12:** gateway stopped during draft-3 switch; queued reading delivered next minute. launchd restart after SIGKILL: discovery and `online` republished within 1 s (`evidence/mqtt-local-broker-2026-10-13/`) |
| **Host asleep** (Mac lid closed, sleep) | As *gateway process stopped*; process suspended | As *gateway process stopped*. USB VCP data from RX is lost while the host sleeps. | AUTO on wake. | None if < 65 h | *N* − 1 | No. **Bench only.** The deployment host is always-on (spec §1). Disable sleep for H01. |
| **House power outage** (deployment) | Gateway, RX, and network down; station runs on solar | TX journals every minute and retries (energy cost, §1.2) | AUTO when power returns | None if < 65 h; oldest data lost beyond (§8.3, *TX journal full*) | *N* − 1 | No. This is the main store-and-forward case. |
| **RX USB disconnected** while the gateway runs | `receiver.log`: `#gateway serial-lost`, then `serial-open` | The gateway keeps serving its API. It looks for the RX board by **ST-LINK serial number** with back-off (1–15 s) and reopens it under any port name. | AUTO | None (TX journals) | *N* − 1 | Unit tests (`tests/test_link.py`: unplug, replug under a new name, missing board, write failure). **Physical replug: pending.** |
| **RX board down** (unpowered, hung, wrong firmware) | Red each minute on TX; no `#rx` lines; no RX blue heartbeat; `#gateway receiver-silent` in `receiver.log` after 180 s without an RX `#alive` report (`receiver` in `/v1/status`) | TX journals | AUTO if power returns; OPERATOR if hung (§9.2) | None if < 65 h | *N* − 1 | Bench: RX reflashes (seconds); `receiver-silent` logged after an unplug (`evidence/soak-a07f498-2026-10-13/`) |
| **TX board down** | No new frames; API `available=false` after 180 s | Nothing is acquired | AUTO on power return: new epoch, backlog first | **Readings during the outage are never acquired** | *N* | Bench: TX reboots, epochs 1→8; cold start reconstructed |
| **All down** (shared USB hub or building power) | Everything dark | Nothing acquired | AUTO on power return | As *TX board down* | As *TX board down* | No |

---

## 6. Failure catalogue — power events

"Reset test" below means `tools/power_cut_test.py --method reset`: 70 cycles, 71 boots, `evidence/g7-reset-during-write-2026-10-13/` (§10, *Power-removal test not done*). True power removal is not tested.

| Scenario | Immediate behavior | Recovery | Data impact | Verified |
|---|---|---|---|---|
| TX power cut **between** flash writes | RAM lost; journal intact | AUTO: new epoch, counters skip to the next block, backlog first | Reading in RAM not yet journaled: ≤ 1 | Bench: resets (not cuts) |
| TX power cut **during** a journal slot write | Slot torn | AUTO: scan counts the slot as `burned` | **≤ 1 observation** | Reset test: 21 boots found and handled torn double-words. True power cut not tested |
| TX power cut during an **ACK-word** write | ACK word torn | AUTO: ECC fault treated as acknowledged (the gateway committed it first) | None | Reset test. True power cut not tested |
| TX power cut during a **counter or epoch** reservation | Entry torn | AUTO: torn entry ignored; maximum of valid entries used. Can skip numbers; cannot repeat them. | None | Reset test: epochs always increased, counter never went back. True power cut not tested |
| TX power cut during **meta-page compaction** | New page has no header | AUTO: old page stays authoritative | None | Reset-test workload includes compactions; no record shows a reset landed inside one. True power cut not tested |
| TX power cut during a **flash page erase** (ring advance) | Page partly erased | AUTO: page has no valid header; its slots are not read. Its pending entries were already counted `lost`. | Already counted | Reset-test workload includes ring-advance erases; no record shows a reset landed inside one. True power cut not tested |
| RX power cut | Frame or ACK in progress lost | AUTO: TX retries next minute | None | Bench (reflash resets) |
| Host power cut **during** a SQLite commit | Transaction rolls back or completes | AUTO: if rolled back, no ACK was sent and TX retries. If completed, the ACK may be missing and TX resends a duplicate. | None (full flush on: `fullfsync` and `checkpoint_fullfsync` for the observation and nonce databases; 5.3 ms median / 16 ms max per commit, recorded in `gateway.py` lines 23–24; simulations opt out with `WS0_UNSAFE_FAST_FSYNC=1`) | Simulation; pragma unit test |
| Host power cut **after** commit, before ACK | Row committed; ACK not sent | AUTO: duplicate next minute, ACK again | None | Simulation `ack-loss` |
| USB brown-out / hub reset | Boards reset (as *TX power cut between flash writes* and *RX power cut*). USB device may get a **new port name.** | AUTO for boards and gateway: with `--serial-number` the gateway finds the RX board under its new name. OPERATOR only when the gateway runs with `--serial <path>` (§9.8) | As *TX power cut between flash writes* | Bench: board A dropped off USB once |
| **TX battery near empty: brown-out cycling** (deployment; for example at dawn, when weak solar starts the board and a radio burst stops it again) | Each boot reserves a new epoch and skips the rest of a 256-counter block; after a power loss the first readings have no time until a sync (reconstructed later by the gateway); a flash write can occur at marginal voltage | AUTO when energy recovers | Each cycle: ≤ 1 torn slot, ≥ 1 time-unknown reading. A fast cycle can repeat many times. | **Not tested.** Needs a low-voltage inhibit (§10, *No low-voltage inhibit*). |
| **USB dropout of about 1 s on a bench board** (cable moved or touched; also an OpenOCD/debugger session) | The ST-LINK pulses the MCU reset pin when it re-enumerates: the board restarts with `reset=pin` (not `power`). TX: new epoch, counter block skipped, time trust restored. The gateway sees `serial-lost` / `serial-open` for RX | AUTO | ≤ 1 reading in RAM; outage time counts against H01 | **Bench 2026-10-13:** TX 4 times, RX twice; `RCC_CSR` showed `PINRSTF` only; two TX resets from debugger sessions (`docs/hardware/nucleo-wl55jc-bringup.md`, "Office session"). Bench only (no ST-LINK on the field node). For H01: secure cables, no debugger sessions |

---

## 7. Failure catalogue — radio link

| Scenario | Detection | Behavior | Recovery | Data impact | H01 | Verified |
|---|---|---|---|---|---|---|
| **Observation frame lost** | TX `#ack none`, red | Slot stays pending | AUTO: resent next minute (new counter) | None | 0 (single loss) | Bench, before the symbol-timeout fix |
| **ACK lost** | As *frame lost*; gateway already has the row | Duplicate next minute; gateway ACKs again | AUTO | None | 0 | Simulation `ack-loss` |
| **ACK late** (after the 2 s window) | As *frame lost* | TX ignores it (radio off); duplicate later | AUTO | None | 0 | Design |
| **Asymmetric link: observations get through, ACKs never do** | First 3 minutes: gateway receives every minute, TX red every minute. Then, in CONSERVE, the gateway receives only probes (≤ 1 per 15 min). TX `link=probing` (console `STATUS`); TX `pending` grows. Health reports (sent every 15 min and at each link-state change, also while PROBING) arrive with link state `probing` | The node decides the link state from ACKs only, so it enters PROBING: live reading only, no backlog. With healthy energy (SURPLUS, NORMAL; always in Stage 0) the live reading still goes every minute; in CONSERVE only at 2, 4, 8, then 15 min. The backlog cannot drain without ACKs. | OPERATOR to repair the link (both roles use the same `radio_cfg.h` power, SF and BW; check placement and antenna) | NORMAL: the gateway gets every live reading on time; unacknowledged copies fill the journal and the oldest are overwritten after about 65 h (counted `lost`, though the gateway already holds them). CONSERVE: only probes arrive | NORMAL: **0** (live readings commit on arrival). CONSERVE: most intervals missed | No |
| **Interference or jamming** | Both directions fail | As *RX board down* (§5) | AUTO when it stops | None if < 65 h | *N* − 1 | No |
| **Out of range / bad placement** | Low RSSI, intermittent lost frames and ACKs | As *frame lost* / *ACK lost* | OPERATOR: placement, SF, power (spec H01 branch) | None if ≥ 1 success per 65 h | Likely fail | Bench (30 cm): −23 / −24 dBm only (`protocol-stack.md` §8.5) |
| **TX frame during the RX ACK transmission** | Frame lost | As *frame lost* | AUTO | None | 0 | **Fixed:** symbol-timeout bug (2026-10-12) |
| **Foreign LoRa traffic on 915 MHz** | RX `#rx drop`; `#rx crc`/`#rx hdr` (bad receptions, stored in `rx_faults`, `tools/rx_faults.py`) | RX discards (length, magic, version); the gateway counts bad receptions and warns above 30 an hour | AUTO | None | 0 | No |
| **Link margin changes** with weather, snow or ice on the antenna, wet foliage, and temperature (deployment) | RSSI/SNR trend in `receiver.log`; more lost frames and ACKs | Intermittent losses and duplicates; more TX energy per delivered reading | AUTO per exchange; OPERATOR if the trend continues (antenna, placement, SF) | None if ≥ 1 success per 65 h | Risk to the 14-interval budget | No. H01 must run at the real placement in real weather. |
| **Downlink weaker than uplink** (the ACK path) | Gateway receives frames; TX gets no ACKs (as *asymmetric link*) | As *asymmetric link* | OPERATOR: give the ACK the same link budget. Both roles configure the radio from the same `radio_cfg.h` constants (power, SF, BW); RX prints `power=` at boot. The H01 checklist requires a both-directions measurement at the real placement. | As *asymmetric link* | As *asymmetric link* | No |

---

## 8. Failure catalogue — misbehaving devices and configuration

### 8.1 Misbehaving devices

| Scenario | Detection | Behavior | Recovery | Data impact | Verified |
|---|---|---|---|---|---|
| **TX firmware hang** | `#boot … reset=watchdog` | Supervised IWDG resets the board in ≤ 8 s if the main loop stops, sampling stops for > 150 s, or an exchange is stuck for > 30 s. Time trust is restored. | AUTO | ≤ 1 interval per hang | **Bench 2026-10-12:** `TEST-HANG` → `reset=watchdog` after 7.9 s, time restored, next reading ACKed |
| **RX firmware hang** | `#boot … reset=watchdog` in `receiver.log` | IWDG resets the board in ≤ 8 s if the main loop stops or the radio stops listening (one re-arm attempt first). After 16 min with no radio event, RX re-arms receive (`#relisten`, counted as `relistens=` in `#alive`); after 2 relistens in a row with no radio event, the watchdog resets the board (`firmware/stage0-node/App/app_rx.c`) | AUTO | None (TX retries) | **Bench 2026-10-12:** `TEST-HANG` → `reset=watchdog` after 7 s |
| **TX sends corrupt frames** | Gateway `rejected InvalidTag` | No ACK; TX retries | AUTO if transient | None if transient | Unit tests |
| **TX clock ahead** of host | Gateway quarantines (`future_clock_at_receipt`) | Stored, not available | AUTO: next ACK corrects the clock | Readings not current until corrected | Simulation `clock-errors` |
| **TX clock behind** host | Readings look old; may be stale | Stored; availability by age | AUTO: next ACK | Readings not current until corrected | Simulation |
| **Host clock wrong** (no NTP) | `host_clock.state=bad` in `/v1/status`; `#gateway host-clock bad` in `receiver.log` | `ws0/clock.py` checks the host offset by SNTP at start and hourly. Off by more than 1 s (allowing for rtt/2) → `bad`: ACKs carry no time; the node keeps its own clock, then marks samples unknown after 6 h. Server unreachable or round trip too slow → `unverified`: time still issued, next check in 5 min | OPERATOR: fix host time sync | Timestamps stay correct while the node clock holds; no wrong host time reaches the data | Unit tests (6, including a real SNTP query) |
| **TX transmits continuously** ("babbling") | RX blue LED constant; `receiver.log` flood | Gateway deduplicates; airtime used | OPERATOR: reset/reflash TX | None | No (firmware cannot do this by design) |
| **RX drops, duplicates, or delays frames** | Gaps / duplicate log lines | Duplicates are idempotent; delays reduce timeliness | AUTO | None (late only) | Simulation |
| **RX alters a frame** | Tag fails | Rejected; retried | AUTO | None | Unit tests |
| **RX forges an ACK** | Impossible: the RX board has no key | — | — | None | Design |
| **A frame that the gateway always rejects** ("poison") | `receiver.log` `-> nack`; TX `#nack`; gateway `rejections` table | Authentic but unacceptable (identity collision, invalid record): the gateway stores the raw frame in `rejections` and sends an authenticated **NACK**; TX drops the record and counts `abandoned`. Safety net: 10 unanswered tries while the gateway answers other frames → `#abandon`. An unauthenticated frame gets no NACK. | AUTO | None: the frame is kept in `rejections` and can be recovered (§9.6) | **Bench 2026-10-12:** planted collision → `#nack reason=1`, `abandoned=1`; the reading was then recovered from `rejections`. Unit tests (5); harness `identity-collision` (1 NACK) |

### 8.2 Configuration and provisioning errors

**Key-reuse detection** (applies to the last three rows). The gateway keeps a counter high-water mark per key in `gateway-nonces.sqlite3`. On the first frame whose counter is at or below the mark: no reply, nothing stored, frame kept in `rejections` (reason `counter_regression`), and `/v1/status` `alarm` = "possible key reuse: re-key the node". The alarm persists; only re-keying into a new state directory clears it. `ws0 provision-node` refuses a board whose `ctr` is at or below the mark. Tests: `tests/test_counter_regression.py`.

| Scenario | Detection | Behavior | Recovery | Data impact | Verified |
|---|---|---|---|---|---|
| **Protocol version mismatch** (one board or gateway not updated) | `#rx drop` or `rejected Unexpected frame header` | All traffic stops; TX journals | OPERATOR: update all three (§9.4). **Check TX `pending=0` first.** | None if the old pending plaintexts stay canonical; else poison frames (§8.1) | Bench: draft-3 switch |
| **Wrong key on TX** | Every frame `rejected InvalidTag` | TX journals until full | OPERATOR: re-key (§9.5) | Journal content after a WIPE is lost | Prevented by KCV check at provisioning |
| **Wrong station ID** | `Unexpected frame header` | As *wrong key* | OPERATOR (§9.5) | As *wrong key* | Unit tests |
| **Both boards flashed with the same role** | No `#rx` lines / no TX samples | As *RX board down* or *TX board down* (§5) | OPERATOR: reflash (README) | As *RX board down* / *TX board down* | No |
| **`WIPE` then re-provision under the same station name** | — | `provision-node` sends an epoch floor = 1 + the highest epoch stored in **that state directory's** database (observations, rejections, health reports). The node raises its epoch base before its first sample, so new identities do not collide. The floor does **not** raise the nonce counter (see *WIPE, then PROVISION with a key TX has used before*). | Use a **new key** after every WIPE (§9.5). With a new state directory the floor is 0 and the history lives in the old directory | None for identity, if the same directory is used | Unit `test_epoch_floor_is_above_all_stored_epochs` |
| **Gateway nonce database lost** | Gateway refuses to start (`Missing nonce state`) | No ACKs | OPERATOR: re-key (§9.5). **First, drain TX if possible (impossible without the nonce DB).** | TX journal lost at WIPE | Unit `test_nonce_restart_and_missing_state` |
| **Old backup of nonce DB or TX flash restored with the same key** | TX flash restore: detected on the first frame (key-reuse detection above). A nonce-DB restore lowers the mark too, so it is not detected: never restore it (§9.7) | **Nonce reuse, a confidentiality and integrity break** | **UNRECOVERABLE for that key.** Re-key immediately. | Security, not data | Prohibited by procedure |
| **Two TX boards with the same key and station** | Identity collisions; nonce reuse. Detected on the first frame (key-reuse detection above) | Nonce reuse, a confidentiality and integrity break | UNRECOVERABLE for that key | Security, not data | Prohibited by procedure |
| **`WIPE`, then `PROVISION` with a key TX has used before** | Detected on the first frame (key-reuse detection above) | From release `0f456040fe54`, `store_wipe()` erases only the key page and the journal (`App/node_store.c`); the counter, epoch and lost/abandoned totals rise for the life of the board. Firmware before that release erased both meta pages, so the 64-bit counter restarted at 1. A key used on that older firmware, or on another board, can therefore still collide: every new frame repeats an AES-CCM nonce (kind + station + counter) already sent on air: **a confidentiality and integrity break** | **UNRECOVERABLE for that key.** Re-key | Security, not data | Firmware behavior from `0f456040fe54` plus procedure: `docs/runbook-moving-boards.md` (prefer a new key). Lost counter state is not yet fail-closed (§10) |

### 8.3 Storage

| Scenario | Behavior | Recovery | Data impact | Verified |
|---|---|---|---|---|
| **TX journal full** | Erase oldest page; count `lost` (cumulative, persisted in flash before the erase, reported in the kind-4 health report) | AUTO-BOUNDED | Oldest ≤ 51 per page | No |
| **TX journal write fails** | Sample identity used; slot counted `burned`; that reading is not sent | AUTO-BOUNDED | 1 per failure | No |
| **TX counter reservation fails** | That minute's exchange stops (no counter, no frame) | AUTO retry next minute; persistent failure = HALTED in effect | Journals until full | No |
| **TX flash wear-out** | Program/erase errors (journal write or counter reservation fails) | OPERATOR: replace board | — | Estimate: journal pages ≈ 1 erase / 2.7 days each; meta pages ≈ 1 compaction / 40 days. Far below 10,000 cycles. |
| **Host disk full** | Commit fails; no ACK | AUTO when space returns | None | Simulation `storage-failure` |
| **Gateway database corrupt or deleted** | Gateway errors / empty history | OPERATOR: restore `observations.sqlite3` from backup (§9.7) | **Rows committed after the backup and already ACKed are lost permanently** | No |

---

## 9. Recovery procedures (runbook)

### 9.1 Restart the gateway

Normally launchd (`tools/deploy/macos/install.sh status`) or systemd does this automatically.

1. Run `tools/deploy/macos/install.sh install`, or by hand `python -m ws0 serve --directory run-hw --serial-number 0016001E4142500E20353451`.
2. Make sure `serve.out` shows `Stage 0 hardware`.
3. Make sure a TX green flash occurs within 60 s.
4. The backlog drains at up to 5 per minute (NORMAL). If TX is in PROBING, the drain starts after its next answered probe (up to 15 min). Do not stop the gateway during the drain.

### 9.2 Reset the RX board

Push the black RESET button, or unplug and reconnect the USB cable. If the port name changes, do §9.8. RX holds no state.

### 9.3 Reset the TX board

Push RESET. The board reserves a new epoch and sends the backlog first. It restores its time trust (`#time restored`) if it synced in the last 6 hours.

### 9.4 Change the protocol version

1. On the TX console, send `STATUS`. Wait for `pending=0`. If the link is down, repair it first.
2. Flash the RX board.
3. Flash the TX board.
4. Restart the gateway with the matching code.
5. Make sure the next minute gives green on TX.

### 9.5 Re-key a station (destructive)

1. Drain the TX journal first (`pending=0`) with the **old** gateway, if it still operates.
2. Stop the gateway.
3. Make a new state directory with a **new key**: `python -m ws0 init --hardware --station <name> --station-id <id> --directory <new dir>`. `ws0 init` refuses an existing directory, so there is no in-place re-key. **Never re-provision a key TX has used before:** it can repeat nonces (§8.2; `docs/runbook-moving-boards.md`). The epoch floor protects observation identities only, and only against the history in the directory that `provision-node` reads (a new directory gives floor 0).
4. On the TX console, send `WIPE ERASE-ALL-NODE-STATE`.
5. Run `python -m ws0 provision-node --directory <dir> --serial <TX port>`.
6. Never use the old key again.

**Rejections with reason `counter_regression` are not readings to recover:** they mean a key was reused (§8.2, key-reuse detection). Re-key the node (§9.5); never re-ingest them.

### 9.6 Recover a NACKed reading

The gateway keeps every NACKed frame in `observations.sqlite3`, table `rejections` (`frame_hex`). After you correct the cause (for example, a wrong stored row), decode the frame with the station key and `Store.ingest` it. Example: the bench recovery in `docs/hardware/nucleo-wl55jc-bringup.md`.

### 9.7 Restore the gateway database

- You can restore `observations.sqlite3` from a backup. Both gateway databases use a write-ahead log:
  a database is the `.sqlite3` file **plus** its `-wal` and `-shm` files. Back up and restore all
  three together while the gateway is stopped (or use `sqlite3 <db> ".backup <file>"`), never the
  `.sqlite3` file alone: recent commits live in the `-wal` file.
- **Never restore `gateway-nonces.sqlite3`.** If it is lost, do §9.5. Deleting only its `-wal` file
  loses the latest counters, which is the same as restoring an old copy: never do it.
- Rows that the TX board deleted after the backup time are lost. Record the loss window.

### 9.8 Port name changed

No action is necessary with `--serial-number`; the gateway finds the board again. With `--serial <path>`, run `st-info --probe`, find the RX board (`0016001E4142500E20353451`), and restart with the new path.

### 9.9 Bench fault injection (never during an H01 placement run)

- **Watchdog:** send `TEST-HANG` on the TX or RX console. The main loop stops; expect `#boot … reset=watchdog` within about 8 s.
- **Flash writes under reset:** `TEST-FLASH-STORM` on the TX console pauses sampling and writes journal slots (acknowledged at once, epoch 4294967295, never transmitted) and counter reservations continuously until the next reboot. It uses up journal slots and counter blocks. The boot scrub drops any storm slot left pending.
- **Automated:** `tools/power_cut_test.py --method reset --serial-number <TX ST-LINK serial> --cycles <n> --gateway-db <dir>/observations.sqlite3 --output evidence/<new dir>` asserts NRST through the ST-LINK (needs `openocd`) at a random time (`--min-run`/`--max-run`, default 0.3–4 s) during the storm. It checks on every boot that the epoch strictly increases, the counter never goes back, the self-test passes, and the reset cause is `pin`; at the end it checks the gateway database for storm records. `--method power --hub <loc> --port <n>` removes VBUS with `uhubctl` (the power-removal test); run `--check` first, because the bench hubs do not really cut VBUS. `--output` must not exist; the exit code is 0 for pass, 1 for fail.

---

## 10. Open issues

Issues that are still open or partly open. "Needed by" gives the latest point at which the fix must exist.

| Issue | What is wrong | Effect | Proposed fix | Needed by |
|---|---|---|---|---|
| **Key in plain flash** | The key is in plain flash (RDP level 0). | Physical access to the board gives the key. | Set RDP level 1. Document the recovery (a mass erase loses the journal). | Before field use |
| **Power-removal test not done** | The reset test passed: 70 cycles, 2026-10-13 (`evidence/g7-reset-during-write-2026-10-13/`; stopped early by Clint). Epochs always increased, the counter never went back, the self-test passed on all 71 boots, 21 boots found and handled double-ECC (torn) double-words, up to 3 torn slots burned per boot, 0 storm records reached the gateway. A reset aborts a flash program/erase like a power cut does (RM0453), so the reset test covers torn slots, ECC recovery, and counter and epoch monotonicity. True power removal, including slow supply decay, is not tested. The bench VIA Labs hubs advertise per-port power switching but do not cut VBUS (board reset cause `pin`, not `power`). | The TX power-cut rows in §6 have reset evidence only. | Run `tools/power_cut_test.py --method power` (§9.9) with a hub that really switches VBUS, for example Yepkit YKUSH. | Deferred by Clint 2026-10-13; no date set |
| **Backlog drain rate** | Design: [`radio-energy-policy.md`](radio-energy-policy.md) §5–6. The drain sends up to 5 per minute in NORMAL and 20 in SURPLUS, airtime-capped, and stops at the first missed ACK. | A long outage takes about one fifth of its own length to clear. | Review the 5/min NORMAL rate in H11. | Decide in H11 |
| **No low-voltage inhibit** | Nothing stops a journal write or a transmission at a marginal supply voltage. | A flash write can tear, and a radio burst can cause a brown-out loop (§6, *TX battery near empty*). | Set the brown-out reset (BOR) level in the option bytes. Do not start a journal write or a transmission below a measured voltage threshold (pack voltage from Stage 1 telemetry; VDD/VREFINT now). | Before field use (Stage 1 interface) |
| **Blind 2 s ACK window** | The receiver stays open for the full 2 s when no ACK arrives. | Each failed exchange costs a full 2 s of receive current (§1.2). | Use a timed receive slot: the gateway's turnaround is predictable, so open the receiver at a fixed delay after TxDone and close it with a symbol timeout sized for the SF (LoRaWAN Class A uses the same idea: RX1 delay + preamble timeout) [[LoRaWAN]](https://resources.lora-alliance.org/technical-specifications). Measure the gateway turnaround first. **Recalculate the symbol timeout for each SF** (see the 1.3 ms bug in `protocol-stack.md` §8.4). | Before field use |
| **Lost counter state is not fail-closed** | WIPE keeps the counter from release `0f456040fe54` (§8.2). A key used on older firmware or on another board can still repeat nonces; the gateway detects it on the first such frame. If the node's counter state is lost, the node does not refuse to transmit. | Nonce reuse is detected after the fact, not prevented. | Fail closed when counter state is lost: `store_meta_init` reports "created fresh"; a provisioned node with fresh meta prints `#error counter-state-lost: re-key required`, shows solid red, does not transmit, and keeps feeding the watchdog (`docs/firmware-review-2026-10-13.md` §3). Procedure meanwhile: `docs/runbook-moving-boards.md` (prefer a new key). | Proposed, not scheduled |
| **Code space for the final station** | See `docs/firmware-budget.md`. TX uses 82.0 % of the 64 KB application region (release `bc5e6ede429c`); Stage 1+ features are estimated at 18–33 KB against about 11.5 KB left. The region is a layout choice (`App/flash_layout.h`, `firmware/board/nucleo-wl55jc/STM32WL55JCIX_FLASH.ld`), not a chip limit: the STM32WL55JC has 256 KB. The key and counter pages (32–34) sit right after the code, so growing the region means moving them. | Stage 1+ features do not fit the current region. | Watch: Makefile flash guard (fails above 90 %), sizes in every release. Fix (Stage 1, with H11): flash layout v2 with key/counter pages at the top of flash, one shared boundary constant, and a one-time migration that carries counter and epoch (never a counter reset: a reset repeats nonces). Target: final image ≤ 75 % of its region. | Before Stage 1 features |

---

## 11. Verification status

| Evidence | Covers |
|---|---|
| Unit tests (`tests/`, 82 test functions on 2026-10-13, including 21 for the range-test tool) | Frame agreement C ↔ Python, tamper/replay rejection, commit-failure no-ACK, nonce restart, canonical fillers, NACK, health reports, epoch floor, serial link, host clock, H01 scorer |
| Simulation harness (12 scenarios × 1,440 samples) | Outages, reboots, ACK loss, duplication, corruption, commit failure, clock faults, identity collision. **The node is the Python simulator, not the firmware.** The simulator drains 5 backlog records per minute but does not model PROBING or the drain stop at the first missed ACK (`ws0/simulator.py`), so its outage results do not cover the current firmware link behavior. |
| Bench (2026-10-12) | Gateway down → journal → delivery; TX reboots → new epoch and counter skip; version mismatch rejection; reflash keeps state; foreign LoRa frames dropped; symbol-timeout failure and fix |
| Bench (2026-10-13) | Watchdog on TX and RX (§8.1); NACK for poison frames (§8.1); reset during flash writes, 70 cycles (§6); link outage with PROBING (`evidence/g13-outage-2026-10-13/`: 1 frame per silent minute, PROBING after 3 silent minutes, journal-only minutes between probes, live-only probe, back-off doubled, relinked on the first answered probe, backlog drained 5 per minute oldest first, `lost=0`; the log ends mid-drain at `pending=5`, and it predates the probe-schedule fix, so it shows probes at +3 and +5 min instead of +2 and +4; no log of the current schedule yet); 9 h soak (`evidence/soak-a07f498-2026-10-13/`: first health report at uptime 1 s, 550 RX `#alive` lines) |
| **Not yet tested** | True power removal (§10), journal overflow (§8.3), physical USB replug under load (§5; unit-tested), long RX outage (§5), asymmetric link (§7), host sleep (§5) |

Before the 24-hour H01 run starts, close every issue in §10 marked "Before H01", or have Clint accept it explicitly. Do not run H01 and then remove failures from the denominator.

H01 runs on USB power (spec Stage 0), so it does not test the energy behavior (§1.2; §10 *No low-voltage inhibit* and *Blind 2 s ACK window*). Those behaviors are verified in Stage 1 with measured current (H02/H03). PROBING is implemented; its energy inputs come from Stage 1. Verify its energy effect with measured current (H02/H03) before the station runs from a battery for the first time.

---

## 12. Change control

When a change affects a behavior in this document:

1. Update the row in sections 5–8.
2. Update the **Verified** column only when there is evidence: a test, a log, or a measurement. Give its location.
3. If the change closes an open issue, delete it from section 10 and record the evidence in the affected row.
4. If the change can lose data in a new way, add a row to the loss budget (3.2) and get approval.
