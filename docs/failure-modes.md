# Stage-0 communication: failure modes, recovery, and loss budget

> **Document type:** Failure modes and effects analysis (FMEA) and recovery runbook.
> **Applies to:** Stage 0 data path: TX board → LoRa → RX board → USB → gateway (`ws0`) → SQLite. Protocol draft 4 and later.
> **Status:** Most behaviors exist in code. Column **Verified** tells you what has evidence. Section 10 lists the known gaps. **H01 is NOT RUN.**
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
| Airtime, 56-byte frame | 26.9 ms | 87 ms (SF9) to 576 ms (SF12) |
| Packet loss | Rare | **Routine.** Weather, snow on the antenna, interference, temperature |
| Gateway host | Mac, can sleep | Always-on Linux computer or SBC on mains (spec §1). It must not sleep. |
| Typical outage | Developer stops the gateway | **House power outage or storm.** The station keeps measuring on solar; the gateway is down. This is exactly what store-and-forward is for. |

**Design principle.** The node is the energy-limited and unattended side. The gateway is mains-powered and attended. Therefore:

1. The node must **fail cheaply.** A failure must not make it spend much more energy than normal operation.
2. Put decisions and extra work on the **gateway side** where possible (for example: NACKs, time checks, monitoring).
3. Never trade data safety for energy, and never trade energy for convenience.

### 1.2 Energy cost of a failed exchange

Each frame costs transmit energy plus the energy of the ACK receive window. The window is short when the ACK arrives. It stays open for the full **2,000 ms** when no ACK arrives.

| SF (500 kHz) | Airtime, 56 B | TX charge at ~100 mA (+20 dBm class) | RX charge, full 2 s window at ~5 mA |
|---|---:|---:|---:|
| SF7 | 27 ms | 2.7 mC | 10 mC |
| SF10 | 164 ms | 16 mC | 10 mC |
| SF12 | 576 ms | 58 mC | 10 mC |

*The current values are datasheet-class assumptions for the STM32WL. Stage 1 must measure them (spec H02).*

- In a **normal minute**, the node sends 1 frame and the ACK closes the window early.
- In a **failed minute**, today's firmware sends **3 frames** (live + 2 backlog) and waits the **full 2 s** after each.

At SF12 and +20 dBm, one failed minute costs about 3 × (58 + 10) ≈ 200 mC, against about 60 mC in a normal minute. Over a one-day gateway outage, that is about 290 C ≈ 80 mAh, or roughly **0.27 Wh/day** at 3.3 V. That is about **4–5 % of the 6 Wh/day core budget**, spent on a link that is known to be down. Gaps G13 and G16 (section 10) address this.

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
| Acknowledged | Gateway SQLite only | Yes (see gap G4) | Loss or corruption of the gateway database |

**Key property:** An observation always has at least one durable custodian between the journal write and the end of its life. The TX board deletes its copy only after it verifies an authentic ACK. The gateway makes that ACK only after its commit.

---

## 3. Guarantees and loss budget

### 3.1 Invariants (must hold in every failure)

| # | Invariant | Mechanism | Verified |
|---|---|---|---|
| I1 | The gateway never sends an ACK for an observation that it did not commit. | `Gateway.receive`: commit, then seal ACK | Simulation `storage-failure`; unit `test_commit_failure_no_ack` |
| I2 | The TX board never deletes an observation without an authentic ACK for that identity. | `ws_open_ack` + `store_journal_find` | Unit `test_ack_tamper_keeps_pending` (simulator); bench (firmware) |
| I3 | No (key, nonce) pair is used two times. | Durable counter blocks; kind byte splits directions | Bench: reboot skips the block (8 → 257); not power-cut tested |
| I4 | No two different observations have the same identity. | Durable epoch before the first sample | Bench: epochs 1→5 over reboots; **broken by `WIPE`, see G5** |
| I5 | The database stores each identity once. A changed payload with an old identity is rejected. | Primary key + payload comparison | Simulation `identity-collision`, `ack-loss` |
| I6 | An invalid or stale reading is never shown as current. | Validity flag, impossible fillers (draft 3), 180 s freshness, 5 s future quarantine | Unit + simulation `sensor-fault`, `clock-errors` |
| I7 | A replayed ACK cannot change the TX clock. | Counter echo in the ACK | Design + unit vectors; no adversarial bench test |

### 3.2 Loss budget

This is the data loss that the design accepts. **Items marked ⚠ need Clint's approval. They define how H01 and H11 read a failure.**

| Category | Accepted loss | Rationale |
|---|---|---|
| **Never acceptable** | Loss of a committed observation; a duplicate row; nonce reuse; an invalid or stale value shown as current | Spec §9, §11, H01, H11 |
| TX power cut during a journal write | **≤ 1 observation per power cut** (the slot in progress) | Flash cannot commit atomically faster than a power loss |
| TX unpowered (battery depleted, brown-out), or TX sensor absent | **All intervals while the TX board is down.** These readings never exist, so they are not "lost". They show as a time gap between two epochs. | No energy, no measurement. In deployment, prevention is the job of the power system (spec R03: 168 h without solar). |
| RX, gateway, or link down | **0 lost** if the outage is ≤ **79 h** (journal capacity). Data is late. | Store-and-forward. A multi-day winter storm outage at the house can exceed 79 h; the 30-day target is H11 (external flash). |
| Outage > 79 h | **Oldest pending observations, 51 at a time** (one flash page). Counted on the TX board as `lost`. | **Approved by Clint 2026-10-12:** drop oldest first (newest data is more valuable). |
| Time unknown after a TX boot | **Closed (G6).** Warm reset: time trust restored (D). Power loss: the gateway reconstructs the time of every reading in the epoch after its first sync (C). Residual: an epoch that ends before its first sync stays `unknown`. | Approved by Clint 2026-10-12 (C + D) |
| Backlog drain | Backlog clears at **2 observations per minute** in addition to live data. An outage of *D* minutes takes *D*/2 minutes to clear. | Live data has priority. ⚠ H11 must accept or raise this rate. |

### 3.3 H01 budget

H01 needs **≥ 1,426 of 1,440** one-minute intervals committed within 120 s of acquisition. So the run can miss **at most 14 intervals in 24 h**.

| Event during H01 | Intervals it costs |
|---|---|
| One lost frame or one lost ACK | **0.** The next minute resends the reading as the oldest backlog item. It commits at about t + 61 s, so it is still within 120 s. |
| Two lost exchanges in a row for one reading | 1 (it commits at about t + 121 s or later) |
| Outage of *N* minutes (any cause) | About *N* − 1 |
| TX reboot (any cause) | Outage time only. Warm reset: no time loss (D). Power loss: first reading reconstructed (C). |
| RX reboot | 0 to 1 |
| Gateway restart (a few seconds) | 0 |

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
  NORMAL --> LINK_DEGRADED: no ACK in window
  LINK_DEGRADED --> NORMAL: authentic ACK
  NORMAL --> TIME_UNKNOWN: >6 h since last time sync
  TIME_UNKNOWN --> NORMAL: ACK with matching echo
  LINK_DEGRADED --> OVERFLOW: journal ring full
  OVERFLOW --> LINK_DEGRADED: ACKs drain backlog
  state HALTED {
    [*] --> red_solid
  }
```

| State | LED | Samples? | Transmits? | Exit |
|---|---|---|---|---|
| NORMAL | Blue blip every 2 s; blue then green each minute | Yes | Yes | — |
| LINK_DEGRADED | Blue then **red** each minute | Yes, journaled | Yes, retries | Next authentic ACK |
| TIME_UNKNOWN | as above | Yes, UTC = 0 | Yes | Next ACK with matching echo |
| OVERFLOW | as LINK_DEGRADED | Yes; erases the oldest page | Yes | Backlog drains |
| UNPROVISIONED | **Red solid** | No | No | `ws0 provision-node` |
| HALTED | **Red solid** | No | No | Operator (section 9) |

### 4.2 RX board

The RX board has one operating state: **continuous receive**. It leaves this state only to send one ACK, then it returns. It has no key and no stored data, so a reset loses only a frame or ACK that is in progress.

### 4.3 Gateway

| State | Detection | Behavior |
|---|---|---|
| Serving | `serve.out` "Stage 0 hardware; API …" | Normal |
| Rejecting | `receiver.log`: `rejected …` | No ACK; TX journals and retries |
| **Exited** | Process gone; no new lines in `receiver.log` | No ACKs; TX journals. **No automatic restart (gap G3).** |

---

## 5. Failure catalogue — peer unavailable

| ID | Scenario | Detection | Immediate behavior | Recovery | Data impact | H01 | Verified |
|---|---|---|---|---|---|---|---|
| P1 | **Gateway process stopped** (crash, Ctrl-C, update). Now restarted by launchd/systemd (G3). | No `#ack` on TX; red LED each minute; API down | RX prints frames; nobody answers. TX journals. | AUTO after restart (R1). Backlog 2/min. | None if restarted within 79 h | *N* − 1 | **Bench, 2026-10-12:** gateway stopped during draft-3 switch; queued reading delivered next minute |
| P2 | **Host asleep** (Mac lid closed, sleep) | As P1; process suspended | As P1. USB VCP data from RX is lost while the host sleeps. | AUTO on wake. | None if < 79 h | *N* − 1 | No. **Bench only.** The deployment host is always-on (spec §1). Disable sleep for H01. |
| P7 | **House power outage** (deployment) | Gateway, RX, and network down; station runs on solar | TX journals every minute and retries (energy cost, §1.2) | AUTO when power returns | None if < 79 h; oldest data lost beyond (S1) | *N* − 1 | No. This is the main store-and-forward case. |
| P3 | **RX USB disconnected** while the gateway runs | `receiver.log`: `#gateway serial-lost`, then `serial-open` | The gateway keeps serving its API. It looks for the RX board by **ST-LINK serial number** with back-off (1–15 s) and reopens it under any port name. | AUTO | None (TX journals) | *N* − 1 | Unit tests (`tests/test_link.py`: unplug, replug under a new name, missing board, write failure). **Physical replug: pending.** |
| P4 | **RX board down** (unpowered, hung, wrong firmware) | Red each minute on TX; no `#rx` lines; no RX blue heartbeat | TX journals | AUTO if power returns; OPERATOR if hung (R2) | None if < 79 h | *N* − 1 | Bench: RX reflashes (seconds) |
| P5 | **TX board down** | No new frames; API `available=false` after 180 s | Nothing is acquired | AUTO on power return: new epoch, backlog first | **Readings during the outage are never acquired** | *N* | Bench: TX reboots, epochs 1→8; cold start reconstructed |
| P6 | **All down** (shared USB hub or building power) | Everything dark | Nothing acquired | AUTO on power return | As P5 | As P5 | No |

---

## 6. Failure catalogue — power events

| ID | Scenario | Immediate behavior | Recovery | Data impact | Verified |
|---|---|---|---|---|---|
| E1 | TX power cut **between** flash writes | RAM lost; journal intact | AUTO: new epoch, counters skip to the next block, backlog first | Reading in RAM not yet journaled: ≤ 1 | Bench: resets (not cuts) |
| E2 | TX power cut **during** a journal slot write | Slot torn | AUTO: scan counts the slot as `burned` | **≤ 1 observation** | **Not tested (gap G7)** |
| E3 | TX power cut during an **ACK-word** write | ACK word torn | AUTO: ECC fault treated as acknowledged (the gateway committed it first) | None | **Not tested (G7)** |
| E4 | TX power cut during a **counter or epoch** reservation | Entry torn | AUTO: torn entry ignored; maximum of valid entries used. Can skip numbers; cannot repeat them. | None | **Not tested (G7)** |
| E5 | TX power cut during **meta-page compaction** | New page has no header | AUTO: old page stays authoritative | None | **Not tested (G7)** |
| E6 | TX power cut during a **flash page erase** (ring advance) | Page partly erased | AUTO: page has no valid header; its slots are not read. Its pending entries were already counted `lost`. | Already counted | **Not tested (G7)** |
| E7 | RX power cut | Frame or ACK in progress lost | AUTO: TX retries next minute | None | Bench (reflash resets) |
| E8 | Host power cut **during** a SQLite commit | Transaction rolls back or completes | AUTO: if rolled back, no ACK was sent and TX retries. If completed, the ACK may be missing and TX resends a duplicate. | None (full flush on, G4) | Simulation; pragma unit test |
| E9 | Host power cut **after** commit, before ACK | Row committed; ACK not sent | AUTO: duplicate next minute, ACK again | None | Simulation `ack-loss` |
| E10 | USB brown-out / hub reset | Board resets (as E1/E7). USB device may get a **new port name.** | AUTO for boards; OPERATOR for the gateway (G3, R8) | As E1 | Bench: board A dropped off USB once |
| E11 | **TX battery near empty: brown-out cycling** (deployment; for example at dawn, when weak solar starts the board and a radio burst stops it again) | Each boot reserves a new epoch and skips the rest of a 256-counter block; after a power loss the first readings have no time until a sync (reconstructed later, C); a flash write can occur at marginal voltage | AUTO when energy recovers | Each cycle: ≤ 1 torn slot, ≥ 1 time-unknown reading. A fast cycle can repeat many times. | **Not tested.** Needs low-voltage inhibit (G14). |

---

## 7. Failure catalogue — radio link

| ID | Scenario | Detection | Behavior | Recovery | Data impact | H01 | Verified |
|---|---|---|---|---|---|---|---|
| L1 | Observation frame lost | TX `#ack none`, red | Slot stays pending | AUTO: resent next minute (new counter) | None | 0 (single loss) | Bench, before the symbol-timeout fix |
| L2 | ACK lost | As L1; gateway already has the row | Duplicate next minute; gateway ACKs again | AUTO | None | 0 | Simulation `ack-loss`; bench (seq 1 resent before fix) |
| L3 | ACK late (after the 2 s window) | As L1 | TX ignores it (radio off); duplicate later | AUTO | None | 0 | Design |
| L4 | **Obs gets through, ACKs never do** (asymmetric link) | Gateway receives every minute; TX shows red every minute; TX `pending` grows | Gateway stores all data. TX resends 2 backlog/min forever at full energy cost (§1.2); journal overflows after 79 h. | AUTO for data; OPERATOR to repair the link | **None at the gateway.** TX `lost` counter grows (false losses). **Energy: about 3× the normal radio energy, without end.** | 0 (live data commits) | No |
| L5 | Interference or jamming | Both directions fail | As P4 | AUTO when it stops | None if < 79 h | *N* − 1 | No |
| L6 | Out of range / bad placement | Low RSSI, intermittent L1/L2 | As L1/L2 | OPERATOR: placement, SF, power (spec H01 branch) | None if ≥ 1 success per 79 h | Likely fail | Bench: −22 to −24 dBm only |
| L7 | TX frame during the RX ACK transmission | Frame lost | As L1 | AUTO | None | 0 | **Fixed:** symbol-timeout bug (2026-10-12) |
| L8 | Foreign LoRa traffic on 915 MHz | RX `#rx drop` | RX discards (length, magic, version) | AUTO | None | 0 | Bench: PingPong frames dropped |
| L9 | **Link margin changes** with weather, snow or ice on the antenna, wet foliage, and temperature (deployment) | RSSI/SNR trend in `receiver.log`; more L1/L2 events | Intermittent L1/L2 and duplicates; more TX energy per delivered reading | AUTO per exchange; OPERATOR if the trend continues (antenna, placement, SF) | None if ≥ 1 success per 79 h | Risk to the 14-interval budget | No. H01 must run at the real placement in real weather. |
| L10 | **Downlink weaker than uplink** (the ACK path) | Gateway receives frames; TX gets no ACKs (L4) | As L4 | OPERATOR: give the ACK the same link budget (G15) | As L4 | As L4 | No. Today the RX board sends ACKs at **0 dBm** from indoors. |

---

## 8. Failure catalogue — misbehaving devices and configuration

### 8.1 Misbehaving devices

| ID | Scenario | Detection | Behavior | Recovery | Data impact | Verified |
|---|---|---|---|---|---|---|
| M1 | **TX firmware hang** | `#boot … reset=watchdog` | Supervised IWDG resets the board in ≤ 8 s if the main loop stops, sampling stops for > 150 s, or an exchange is stuck for > 30 s. Time trust is restored (D). | AUTO | ≤ 1 interval per hang | **Bench 2026-10-12:** `TEST-HANG` → `reset=watchdog` after 7.9 s, time restored, next reading ACKed |
| M2 | **RX firmware hang** | `#boot … reset=watchdog` in `receiver.log` | IWDG resets the board in ≤ 8 s if the main loop stops or the radio stops listening (one re-arm attempt first) | AUTO | None (TX retries) | **Bench 2026-10-12:** `TEST-HANG` → `reset=watchdog` after 7 s |
| M3 | TX sends corrupt frames | Gateway `rejected InvalidTag` | No ACK; TX retries | AUTO if transient | None if transient | Unit tests |
| M4 | **TX clock ahead** of host | Gateway quarantines (`future_clock_at_receipt`) | Stored, not available | AUTO: next ACK corrects the clock | Readings not current until corrected | Simulation `clock-errors` |
| M5 | TX clock behind host | Readings look old; may be stale | Stored; availability by age | AUTO: next ACK | As M4 | Simulation |
| M6 | **Host clock wrong** (no NTP) | Not detected by the system | Gateway stamps wrong time; TX copies it | OPERATOR: fix host time | **All timestamps wrong but consistent. Unrecoverable for that period.** | No (gap G9) |
| M7 | TX transmits continuously ("babbling") | RX blue LED constant; `receiver.log` flood | Gateway deduplicates; airtime used | OPERATOR: reset/reflash TX | None | No (firmware cannot do this by design) |
| M8 | RX drops, duplicates, or delays frames | Gaps / duplicate log lines | Duplicates are idempotent; delays reduce timeliness | AUTO | None (late only) | Simulation |
| M9 | RX alters a frame | Tag fails | Rejected; retried | AUTO | None | Unit tests |
| M10 | RX forges an ACK | Impossible: the RX board has no key | — | — | None | Design |
| M11 | **A frame that the gateway always rejects** ("poison") | `receiver.log` `-> nack`; TX `#nack`; gateway `rejections` table | Authentic but unacceptable (identity collision, invalid record): the gateway stores the raw frame in `rejections` and sends an authenticated **NACK**; TX drops the record and counts `abandoned`. Safety net: 10 unanswered tries while the gateway answers other frames → `#abandon`. An unauthenticated frame gets no NACK. | AUTO | None: the frame is kept in `rejections` and can be recovered | **Bench 2026-10-12:** planted collision → `#nack reason=1`, `abandoned=1`; the reading was then recovered from `rejections`. Unit tests (5); harness `identity-collision` (1 NACK) |

### 8.2 Configuration and provisioning errors

| ID | Scenario | Detection | Behavior | Recovery | Data impact | Verified |
|---|---|---|---|---|---|---|
| C1 | **Protocol version mismatch** (one board or gateway not updated) | `#rx drop` or `rejected Unexpected frame header` | All traffic stops; TX journals | OPERATOR: update all three (R4). **Check TX `pending=0` first.** | None if the old pending plaintexts stay canonical; else poison (M11) | Bench: draft-3 switch |
| C2 | Wrong key on TX | Every frame `rejected InvalidTag` | TX journals until full | OPERATOR: re-key (R5) | Journal content after a WIPE is lost | Prevented by KCV check at provisioning |
| C3 | Wrong station ID | `Unexpected frame header` | As C2 | OPERATOR (R5) | As C2 | Unit tests |
| C4 | Both boards flashed with the same role | No `#rx` lines / no TX samples | As P4 or P5 | OPERATOR: reflash (README) | As P4/P5 | No |
| C5 | **`WIPE` then re-provision under the same station name** | Gateway: `Identity collision` for epoch 1, 2, … | **New readings collide with stored history** and become poison (M11). API "latest" also selects the old, higher epoch. | OPERATOR: **do not do this today.** Use a new station name and directory (R5). Fix: G5. | Severe until fixed | No |
| C6 | **Gateway nonce database lost** | Gateway refuses to start (`Missing nonce state`) | No ACKs | OPERATOR: re-key (R5). **First, drain TX if possible (impossible without the nonce DB).** | TX journal lost at WIPE | Unit `test_nonce_restart_and_missing_state` |
| C7 | Old backup of nonce DB or TX flash restored with the same key | **Not detected** | **Nonce reuse, a confidentiality and integrity break** | **UNRECOVERABLE for that key.** Re-key immediately. | Security, not data | Prohibited by procedure |
| C8 | Two TX boards with the same key and station | Identity collisions; nonce reuse | As C7 | UNRECOVERABLE for that key | As C7 | Prohibited by procedure |

### 8.3 Storage

| ID | Scenario | Behavior | Recovery | Data impact | Verified |
|---|---|---|---|---|---|
| S1 | TX journal full | Erase oldest page; count `lost` (RAM only, gap G8) | AUTO-BOUNDED | Oldest ≤ 51 per page | No |
| S2 | TX journal write fails | Sample identity used; slot counted `burned`; that reading is not sent | AUTO-BOUNDED | 1 per failure | No |
| S3 | TX counter reservation fails | That minute's exchange stops (no counter, no frame) | AUTO retry next minute; persistent failure = HALTED in effect | Journals until full | No |
| S4 | TX flash wear-out | Program/erase errors (S2/S3) | OPERATOR: replace board | — | Estimate: journal pages ≈ 1 erase / 3.3 days each; meta pages ≈ 1 compaction / 40 days. Far below 10,000 cycles. |
| S5 | Host disk full | Commit fails; no ACK | AUTO when space returns | None | Simulation `storage-failure` |
| S6 | Gateway database corrupt or deleted | Gateway errors / empty history | OPERATOR: restore `observations.sqlite3` from backup (R7) | **Rows committed after the backup and already ACKed are lost permanently** | No |

---

## 9. Recovery procedures (runbook)

**R1 — Restart the gateway.** Normally launchd (`tools/deploy/macos/install.sh status`) or systemd does this automatically.
1. Run `tools/deploy/macos/install.sh install`, or by hand `python -m ws0 serve --directory run-hw --serial-number 0016001E4142500E20353451`.
2. Make sure `serve.out` shows `Stage 0 hardware`.
3. Make sure a TX green flash occurs within 60 s.
4. The backlog drains at 2 per minute. Do not stop the gateway during the drain.

**R2 — Reset the RX board.** Push the black RESET button, or unplug and reconnect the USB cable. If the port name changes, do R8. RX holds no state.

**R3 — Reset the TX board.** Push RESET. The board reserves a new epoch and sends the backlog first. It restores its time trust (`#time restored`) if it synced in the last 6 hours.

**R4 — Change the protocol version.**
1. On the TX console, send `STATUS`. Wait for `pending=0`. If the link is down, repair it first.
2. Flash the RX board.
3. Flash the TX board.
4. Restart the gateway with the matching code.
5. Make sure the next minute gives green on TX.

**R5 — Re-key a station (destructive).**
1. Drain the TX journal first (`pending=0`) with the **old** gateway, if it still operates.
2. Stop the gateway.
3. Make a **new** state directory with a **new station name** (until G5 is fixed): `python -m ws0 init --hardware --station station-02 --station-id 2 --directory run-hw-2`.
4. On the TX console, send `WIPE ERASE-ALL-NODE-STATE`.
5. Run `python -m ws0 provision-node --directory run-hw-2 --serial <TX port>`.
6. Keep the old directory read-only for its history. Never use its key again.

**R6 — Recover a NACKed reading.** The gateway keeps every NACKed frame in `observations.sqlite3`, table `rejections` (`frame_hex`). After you correct the cause (for example, a wrong stored row), decode the frame with the station key and `Store.ingest` it. Example: the bench recovery in `docs/hardware/nucleo-wl55jc-bringup.md`.

**R7 — Restore the gateway database.**
- You can restore `observations.sqlite3` from a backup.
- **Never restore `gateway-nonces.sqlite3`.** If it is lost, do R5.
- Rows that the TX board deleted after the backup time are lost. Record the loss window.

**R8 — Port name changed.** No action is necessary with `--serial-number`; the gateway finds the board again. With `--serial <path>`, run `st-info --probe`, find the RX board (`0016001E4142500E20353451`), and restart with the new path.

---

## 10. Known gaps and remediation plan

Priority: **P1** = fix before H01; **P2** = fix before field use; **P3** = track.

| ID | Gap | Risk | Proposed fix | Priority |
|---|---|---|---|---|
| G1 | ~~No hardware watchdog~~ **Closed 2026-10-12** (evidence: M1, M2). Was: no hardware watchdog on TX or RX | A hang stops the system until a person resets it (M1, M2). **A field station is unattended: a hang can last until a site visit.** | Enable the IWDG (independent watchdog, LSI clock), ~8 s timeout. Refresh it from the main loop only when the radio state machine and the sample timer advance. | **P1** |
| G2 | ~~Poison records block the backlog~~ **Closed 2026-10-12** (evidence: M11). Was: poison records block the backlog | Two permanently rejected records stop all backlog drain (M11, C1, C5), and each retry costs node energy | (a) The gateway answers a permanent rejection with an authenticated NACK, so the node stops at once (the mains side decides; §1.1 principle). (b) As a safety net, the TX board marks an entry `abandoned` after *N* attempts (counted and reported). Implement both. | **P1** |
| G3 | ~~Gateway exits on a serial error; no supervisor; port names change~~ **Closed 2026-10-12** (evidence: P3; launchd restarted the gateway 2 s after SIGKILL and it handled the next frame 3 s later). Was: gateway exits on a serial error; no supervisor; port names change | One USB glitch stops H01 data until a person acts | Catch `SerialException`, reopen with back-off, find the RX board by **ST-LINK serial number** (pyserial `list_ports`), and run under `launchd` with `KeepAlive`. | **P1** |
| G4 | ~~SQLite `synchronous=FULL` on macOS does not flush the drive cache~~ **Closed 2026-10-12**: `fullfsync` and `checkpoint_fullfsync` on for the observation and nonce databases. Measured: commit 0.06 ms before (not durable), 5.3 ms median / 16 ms max after; two commits per frame use < 2 % of the 2 s ACK window. Simulations opt out explicitly (`WS0_UNSAFE_FAST_FSYNC=1`). Was: | A host power cut can lose a committed and ACKed row (I1 weakened) | Set `PRAGMA fullfsync=ON` (and `checkpoint_fullfsync=ON`) on macOS [[SQLite]](https://www.sqlite.org/pragma.html#pragma_fullfsync). Measure the commit latency after the change. | **P1** |
| G5 | **`WIPE` restarts epochs at 1** | Re-provisioning under the same station collides with history (C5) | `PROVISION` takes an epoch floor from the gateway (the maximum stored session + 1), or `WIPE` keeps the epoch maximum. | P2 |
| G6 | ~~First reading after each TX boot has unknown time~~ **Closed 2026-10-12** | — | **Done:** D (time trust across resets, backup registers) and C (draft 4 uptime field; gateway reconstruction). Evidence: bench warm reset `#time restored`; cold start reconstructed ±2 s; simulation `reboot-during-outage` 32/32 reconstructed. | — |
| G7 | **Power-loss behavior not tested** | E2–E6 are design claims only | Bench test: a relay or MOSFET cuts TX power at random points (≥ 200 cycles, power cut during write forced with a GPIO trigger). Check: no duplicate identity, no counter reuse, ≤ 1 lost per cut. | **P1** |
| G8 | **TX loss counters are local and RAM-only** | The gateway cannot see `lost` or `burned`; a reboot resets them | Persist the counters in the meta log. Send them in a periodic diagnostic frame (spec §5 "radio/storage health"). | P2 |
| G9 | **Host time correctness is not checked** | Wrong host time goes to all data (M6) | At startup and every hour, the gateway checks the NTP sync state and logs it. If the offset is > 1 s, it refuses to issue time in ACKs (ACKs still go out). | P2 |
| G10 | **The key is in plain flash (RDP level 0)** | Physical access to the board gives the key | Set RDP level 1 before field use. Document the recovery (a mass erase loses the journal). | P2 |
| G11 | **Backlog drain rate is 2/min** (design: [`radio-energy-policy.md`](radio-energy-policy.md) §5–6) | A long outage takes half its own length to clear | Review in H11 together with G13: drain faster **only while ACKs arrive** (cheap: the window closes early), never during an outage. | P3 |
| G12 | RX liveness is not monitored | An RX hang looks like a TX failure | RX prints `#alive` every 60 s; the gateway warns after 3 misses. | P3 |
| G13 | **No energy-aware back-off when the link is down** (design: [`radio-energy-policy.md`](radio-energy-policy.md) §6) | During an outage the node spends about 3× the normal radio energy every minute (§1.2), for up to days, on a link that is known to be down | After *K* consecutive minutes with no ACK: send the **live reading only**, and try one backlog item every *M* minutes. Return to full drain at the first authentic ACK. Live readings still go every minute, so no timeliness is lost when the link returns. | **P1 for deployment** |
| G14 | **No low-voltage inhibit** | At a marginal supply voltage, a flash write can tear and a radio burst can cause a brown-out loop (E11) | Set the brown-out reset (BOR) level in the option bytes. Do not start a journal write or a transmission below a measured voltage threshold (pack voltage from Stage 1 telemetry; VDD/VREFINT now). | P2 (Stage 1 interface) |
| G15 | **ACK link budget is not equal to the uplink** | Asymmetric link (L4, L10): data arrives but the node never clears its journal | The RX board uses the same SF and a TX power that gives the downlink at least the uplink's margin. Put the receiver antenna where the link test shows the best path (spec H01 branch). | P1 before H01 placement |
| G16 | **The ACK window is a blind 2 s window** | Each failed exchange costs a full 2 s of receive current (§1.2) | Use a timed receive slot: the gateway's turnaround is predictable, so open the receiver at a fixed delay after TxDone and close it with a symbol timeout sized for the SF (LoRaWAN Class A uses the same idea: RX1 delay + preamble timeout) [[LoRaWAN]](https://resources.lora-alliance.org/technical-specifications). Measure the gateway turnaround first. **Recalculate the symbol timeout for each SF** (see the 1.3 ms bug in `protocol-stack.md` §8.4). | P2 |

---

## 11. Verification status

| Evidence | Covers |
|---|---|
| Unit tests (33) | Frame agreement C ↔ Python, tamper/replay rejection, commit-failure no-ACK, nonce restart, canonical fillers |
| Simulation harness (12 scenarios × 1,440 samples) | Outages, reboots, ACK loss, duplication, corruption, commit failure, clock faults, identity collision. **The node is the Python simulator, not the firmware.** |
| Bench (2026-10-12) | Gateway down → journal → delivery; TX reboots → new epoch and counter skip; version mismatch rejection; reflash keeps state; foreign LoRa frames dropped; symbol-timeout failure and fix |
| **Not yet tested** | All power-cut cases (G7), journal overflow (S1), USB disconnect under load (P3), long RX outage (P4), asymmetric link (L4), watchdog (G1, not implemented), host sleep (P2) |

H01 needs the P1 gaps closed, or each one explicitly accepted by Clint, before the 24-hour run starts. Do not run H01 and then remove failures from the denominator.

H01 runs on USB power (spec Stage 0), so it does not test the energy behavior (§1.2, G13, G14, G16). Those behaviors are verified in Stage 1 with measured current (H02/H03). Implement G13 before the station runs from a battery for the first time.

---

## 12. Change control

When a change affects a behavior in this document:

1. Update the row in sections 5–8.
2. Update the **Verified** column only when there is evidence: a test, a log, or a measurement. Give its location.
3. If the change closes a gap, move the gap from section 10 to the row, and give the evidence.
4. If the change can lose data in a new way, add a row to the loss budget (3.2) and get approval.
