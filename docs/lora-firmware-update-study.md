# Firmware updates over LoRa: design study

Written 2026-10-14 as a design study only. **Nothing here is built, and nothing in the firmware or
the gateway changed.** It answers Clint's question: *"Once both ends of the system have their 16 MB
flash, can we remotely reprogram units over LoRa somehow?"*

Numbers marked **measured** come from this repository's builds, or from the firmware's own air-time
formula (`ws_lora_airtime_ms()` in `firmware/common/ws_policy.c`, which matches `protocol-stack.md` §8.2 to the tenth of a
millisecond). Numbers marked **estimate** are planning figures and must be checked on the bench.

## 0. Short answer

**Yes, for the station (TX).** The station can fetch a signed image over the existing LoRa link,
store it in its SPI flash and install it with a small bootloader. The receiver (RX) does not need
any of this. It is on a USB cable to the gateway Mac, so it is reflashed by wire (ST-LINK) from that
Mac, as it is today, also over SSH.

| Question | Answer |
|---|---|
| Is it legal at our radio settings? | Yes. We transmit as a §15.247(a)(2) "digital modulation" system (500 kHz bandwidth). That class has **no dwell-time or duty-cycle limit**. Only power and power density are limited (§3) |
| How long does a full image take? | 54 KB (today's TX image): **about 40 s of radio time at SF7**, about 8 min at SF12. Spread over normal minutes inside the existing per-minute air-time cap: **about 9 min at SF7**, 40 min at SF10, 4 h at SF12 (§3.4) |
| How much do delta updates save? | A **binary diff** (only the changes) between real releases measured **1.0–7.4 KB** instead of 54 KB (§3.5). A typical fix then takes seconds of air time |
| Does the RX need the 16 MB flash for this? | **No.** The gateway keeps the image and streams it through the RX, a few chunks per request (§4.3) |
| Energy | Below 0.01 Wh for a full update, against a 6 Wh/day core budget (§4.6) |
| What protects against bad or hostile code? | A signature on every image (ECDSA P-256; the STM32WL has a hardware unit that checks it), checked by a bootloader that is never updated over the air. The update must prove itself (an observation that the gateway acknowledges) or the bootloader puts the old image back (§5) |
| Off-the-shelf? | LoRaWAN FUOTA does not fit a single point-to-point link, and ST removed its FUOTA examples from STM32CubeWL in v1.5.0. MCUboot fits, but has no STM32WL bare-metal port. **Recommendation: a minimal custom bootloader and a pull-based chunk transfer inside our own protocol** (§6) |
| Is it in scope? | **Not today.** The PRD says *"Wired programming and recovery … No over-radio firmware updates in the required implementation."* Building it needs Clint to expand the scope (decision U1, §9) |

Main prerequisites: the H01 gate, flash layout v2 (gap G18) and the SPI NOR flash (H11). Over-the-air
updates come after those, not before.

## 1. Terms used here

| Term | Plain meaning |
|---|---|
| Image | The firmware file that is programmed into the chip (`stage0-tx.bin`) |
| Bootloader | A small, separate program that runs first after every reset. It checks the image and starts it, or installs a new one |
| Slot | A fixed area of flash that holds one image |
| Staging area | A slot in the external SPI flash where a downloaded image waits until the bootloader copies it in |
| SPI NOR flash | The external 16 MB memory chip (Winbond W25Q128JV) on a 4-wire SPI bus. "NOR" flash can be read at any address and is erased in 4 KB sectors |
| Chunk | One piece of the image that fits in one LoRa packet |
| Delta update | Sending only the differences between the old and the new image. The node rebuilds the new image from its current image plus the differences |
| Signature | A cryptographic proof, made with a private key that only Clint holds, that an image is genuine. Anyone with the public key can check it, but nobody can make one without the private key |
| Rollback protection | The node refuses an older (possibly vulnerable) signed image |
| Trial boot / confirm | A new image runs "on probation". If it does not confirm itself in time, the bootloader puts the old image back |
| Air time | How long one packet occupies the radio channel |
| SF, BW | LoRa spreading factor and bandwidth. A higher SF reaches further but each packet takes about twice as long per SF step |

## 2. What the system has today

| Fact | Value | Source |
|---|---|---|
| MCU | STM32WL55JC: Cortex-M4 at 48 MHz plus an unused Cortex-M0+; 256 KB flash in 128 pages of 2 KB; 64 KB RAM | `App/flash_layout.h`, `firmware-budget.md` |
| TX image | **53,752 B** (release `bc5e6ede429c`), 82.0 % of its 64 KB region; 54,384 B with the pending 15-s sampling | `RELEASES.md`, `firmware-budget.md` |
| RX image | 31,696 B | `RELEASES.md` |
| Final TX image budget | Stage 1–3 features add an estimated 18–33 KB. Layout v2 grows the application region to 128 KB or more; target ≤ 75 % used | `firmware-budget.md` (G18) |
| Flash map now | Pages 0–31 code, 32 key, 33–34 counter/epoch log, 35–127 journal. "A firmware update programs only pages 0–31" | `protocol-stack.md` §5.1 |
| Radio | 915.0 MHz, LoRa, **500 kHz**, SF7, CR 4/5, 8-symbol preamble, explicit header, CRC on, 0 dBm (bench). "Never bandwidth below 500 kHz" | `App/radio_cfg.h` |
| Largest LoRa packet | 255 B (radio limit) | SubGHz_Phy |
| Envelope | 8-byte header + AES-128-CCM ciphertext + 8-byte tag; kinds 1–4 used; per-direction counter spaces | `protocol.md` §1–2 |
| Exchange pattern | The node sends; then it listens up to 2,000 ms for the reply. The node can only be reached right after it transmits | `protocol.md` §9 |
| Per-minute air-time cap | 15 / 5 / 2 / 0 s for SURPLUS / NORMAL / CONSERVE / CRITICAL | `firmware/common/ws_policy.c` `airtime_cap_ms` |
| RX bridge | Holds no key. Forwards node frames as hex lines; transmits one 33-byte ACK/NACK line from the host. Lines ≤ 256 B. Drops input while it holds a complete line | `App/app_rx.c`, `protocol.md` §8 |
| Watchdog | Independent watchdog (IWDG), about 8 s, started by the firmware | `App/watchdog.c` |
| Read protection | RDP level 0: the key is readable with a debugger (gap G10) | `failure-modes.md` |
| External flash planned | Winbond **W25Q128JVSIM** (16 MB, −40 °C), Adafruit 5643 breakout for the bench; for the 30-day buffer (H11) | `next-stages-plan.md` §4, `poc-shopping-list.md` |
| Scope | PRD: *"Firmware delivery: Wired programming and recovery … No over-radio firmware updates in the required implementation."* Scope rule: *"Future features receive documented … accommodation where cheap, but not speculative firmware"* | PRD/TRD v0.2 §1 |

## 3. Feasibility and air-time arithmetic

### 3.1 Payload per packet

A LoRa packet carries at most 255 bytes. A firmware chunk frame in our envelope would be:

| Part | Bytes |
|---|---:|
| Header (version/kind, station, counter) | 8 |
| Plaintext: bundle ID (4) + chunk index (2) | 6 |
| Plaintext: image data | **224** |
| CCM tag | 8 |
| **Frame** | **246** |

224 data bytes is 7 × 32, so chunks line up with the 8-byte internal flash program unit and the
256-byte NOR program page. A 54 KB image is 240 chunks; a 96 KB image (the 75 % target of a 128 KB
region) is 439 chunks.

**Why keep the encryption on chunks?** The image itself is not secret (the source is published). But
CCM proves that the chunk came from the gateway, so a stranger cannot fill the staging area with
junk or stall an update. It costs 16 bytes per frame and reuses code that already exists.

### 3.2 Air time per packet (measured with the firmware's formula)

CR 4/5, 8-symbol preamble, explicit header, CRC on. Low-data-rate optimisation applies only at
125 kHz SF11–12.

| SF | 500 kHz, 246-B chunk | 500 kHz, 33-B request/ACK | 125 kHz, 246-B chunk | 125 kHz, 33-B frame |
|---:|---:|---:|---:|---:|
| 7 | **96 ms** | 18 ms | 384 ms | 72 ms |
| 8 | 169 ms | 33 ms | 676 ms | 134 ms |
| 9 | 302 ms | 62 ms | 1,209 ms | 247 ms |
| 10 | 554 ms | 113 ms | 2,214 ms | 453 ms |
| 11 | 1,005 ms | 206 ms | 4,837 ms | 987 ms |
| 12 | 1,845 ms | 412 ms | 8,856 ms | 1,810 ms |

At the same SF, 125 kHz is 4 times slower and about 6 dB more sensitive. So SF7/125 kHz reaches
about as far as SF9/500 kHz, and SF9/500 kHz is faster (302 vs 384 ms per chunk). **500 kHz is never
worse for bulk transfer.**

### 3.3 US 915 MHz rules (FCC Part 15.247) against what the code does

The text of 47 CFR §15.247 [FCC247]:

| Rule | What it says | Our system |
|---|---|---|
| (a)(1)(i) frequency hopping, 902–928 MHz | Channels under 250 kHz wide: at least 50 channels and **at most 0.4 s on any one frequency in 20 s** (0.4 s in 10 s for channels ≥ 250 kHz) | **Not used.** We stay on one frequency |
| (a)(2) digital modulation | "The minimum 6 dB bandwidth shall be at least 500 kHz." **No dwell or duty-cycle limit** | **Used.** 500 kHz LoRa (`radio_cfg.h`, approved 2026-10-12) |
| (b)(3) | Digital modulation: up to 1 W (+30 dBm) conducted | 0 dBm on the bench; planned up to +22 dBm |
| (b)(4) | Reduce power for antenna gain above 6 dBi | Antenna gain not yet known |
| (e) | Power spectral density ≤ 8 dBm in any 3 kHz band | About −22 dBm/3 kHz at 0 dBm (`protocol-stack.md` §8.3). At +22 dBm the margin depends on the measurement method. Check it when the power goes up |
| §15.249 (other option) | ≤ 50 mV/m at 3 m (about −1.25 dBm EIRP) | Not used |

What this means for updates:

1. **At 500 kHz a long burst of chunks is allowed.** No rule limits how long or how often we transmit
   in the digital-modulation class. Our own per-minute air-time cap (`radio-energy-policy.md`, goal
   6 "be a good neighbor") is the real limit, and this design keeps it.
2. **125 kHz is not an option on one channel.** It would need hopping over at least 50 channels with
   each packet under 400 ms. A 246-byte chunk at SF7/125 kHz takes 384 ms: just inside. At SF8 or
   higher no full chunk fits. This is why LoRaWAN US915 caps its SF10/125 kHz uplink payload at 11
   bytes [RP002]. Hopping would also need both boards to follow a hop sequence. No benefit for us.
3. **Two open items from the bring-up remain.** Nobody has measured the 6 dB bandwidth of these
   boards with a spectrum analyzer, and the antenna gain is unknown
   (`hardware/nucleo-wl55jc-bringup.md`). This is an engineering reading of Part 15, not a compliance
   certificate. An update does not change these items, but it does add air time.

### 3.4 How long a full update takes

Two ways to schedule the download:

- **Trickle mode (recommended).** Each minute, after the live reading and its ACK (and any backlog),
  the node asks for as many chunks as fit in what is left of that minute's air-time cap. Live data
  always goes first, so the H01 latency (committed within 120 s) is not affected.
- **Session mode.** The node stays in receive mode until the whole image has arrived. This is faster
  but takes the radio for minutes, outside the per-minute cap. Use it only on the bench.

Assumptions: 246-byte chunks, a 60 ms gap between chunks (about 43 ms for the 492-character hex line
on the 115,200-baud USB link to the RX, plus margin), one 33-byte request plus 300 ms turnaround per
burst, 16 chunks per burst in session mode. For trickle mode, the live reading (51-byte frame + ACK +
300 ms) is subtracted from the cap first.

| Image | SF7 | SF9 | SF10 | SF12 |
|---|---:|---:|---:|---:|
| **Session mode: radio time** | | | | |
| 54 KB (today) | 42 s | 92 s | 2.6 min | 7.8 min |
| 96 KB (75 % of a 128 KB region) | 79 s | 2.9 min | 4.8 min | 14.6 min |
| 128 KB | 104 s | 3.8 min | 6.3 min | 19.2 min |
| **Trickle mode, NORMAL (5 s cap)** | 27 chunks/min | 11/min | 6/min | 1/min |
| 54 KB | **9 min** | 22 min | 40 min | 4 h |
| 96 KB | 17 min | 40 min | 74 min | 7.3 h |
| **Trickle mode, SURPLUS (15 s cap)** | 91 chunks/min | 39/min | 22/min | 6/min |
| 54 KB | 3 min | 7 min | 11 min | 40 min |
| 96 KB | 5 min | 12 min | 20 min | 74 min |

Lost packets add retries in proportion. With 10 % chunk loss, add about 10 %.

Even the slowest case (4 h at SF12, NORMAL) is acceptable for a weather station that keeps measuring
and sending during the download. The image is installed only once it is complete and verified.

### 3.5 Delta updates (measured on our own builds)

A delta update sends a compressed binary diff. I measured it with `detools` 0.53.0 [DETOOLS]
(sequential patch type, the one its C library can apply on a microcontroller) on pairs of real TX
`.bin` files found in this repository and the scratch area:

| Change between two TX builds | New image | Diff, heatshrink | Diff, LZMA |
|---|---:|---:|---:|
| Adjacent builds (`483bb3…` → release `45f43e78fe91`) | 52,896 B | **1,017 B** | 383 B |
| Two 2026-10-13 scratch builds, small source change | 53,177 B | 1,073 B | 419 B |
| Two scratch builds, about 300 B of new code | 53,480 B | 3,136 B | 2,312 B |
| **Release to release: `45f43e78fe91` → `bc5e6ede429c`** (protocol draft 5, +856 B) | 53,752 B | **7,415 B** | 5,801 B |
| Toolchain-level change: same source, link-time optimisation on | 46,584 B | 32,728 B | 24,446 B |
| No diff: whole image compressed | 53,752 B | 50,431 B | 36,028 B |

The scratch builds' exact commits were not recorded; their sizes and hashes are in the scratch
directory. Conclusions:

- **heatshrink** is the codec to use on the node. It needs only a few hundred bytes of RAM. LZMA is
  20–60 % smaller but needs a large dictionary in RAM. 64 KB of RAM rules out useful LZMA settings.
- **Delta updates shrink an update 7–50 times** (7 times for a whole protocol release, 50 for a
  small fix). The draft-5 release would be 34 chunks: about
  6 s of radio time at SF7, or 34 min trickled at SF12 NORMAL.
- **Whole-image compression gains almost nothing with heatshrink** (54 → 50 KB). Send whole images
  uncompressed and save the effort for deltas.
- **A compiler or option change produces a near-full diff.** Ship those as full images.
- **Deltas need the exact base image.** The release process already makes bit-identical `.bin` files
  (`RELEASES.md`), so the gateway can rebuild any base. The node must report the hash of the image
  it runs, and the diff must name the base image's hash. The node refuses a diff for another base.

## 4. Architecture

### 4.1 Where things live

```text
 Clint's Mac (offline)            Gateway Mac (ws0)              RX board            TX station
 ┌───────────────────┐  bundle   ┌──────────────────┐  USB hex  ┌──────────┐ LoRa ┌──────────────────────┐
 │ signing key       │ ───────▶  │ bundle store     │ ────────▶ │ stateless│ ───▶ │ app: chunk client    │
 │ make + sign       │           │ answers FW-REQ   │ ◀──────── │ bridge   │ ◀─── │ NOR: staging, backup │
 └───────────────────┘           │ per-node progress│           └──────────┘      │ bootloader: verify,  │
                                 └──────────────────┘                             │ copy in, trial,revert│
                                                                                  └──────────────────────┘
```

### 4.2 Bootloader: A/B in internal flash, or staging in external flash?

| | A/B in internal flash | **Staging in SPI NOR, copy-in (recommended)** |
|---|---|---|
| How it works | Two internal slots; the bootloader runs one or swaps them | One internal slot runs the image. The download goes to NOR; the bootloader verifies it and copies it in. The previous image stays in NOR for a revert |
| Room for the application | 256 KB − bootloader − node state, then halved: about **110 KB per slot**. The final budget (about 72–87 KB before LTO) would be at about 75–80 % of a slot. Tight | About **192 KB** for the application |
| Needs the NOR chip | No | Yes, and the bootloader needs a small SPI read driver |
| Install risk | Low with swapping | A power cut during copy-in is safe: the source in NOR is untouched, so the bootloader restarts the copy (idempotent) |
| Install time | Swap of up to 110 KB | Copy of up to 192 KB: about 4 s (96 page erases at about 23 ms each, measured by WIPE; plus about 2 s of 8-byte programming, an estimate) |
| Zephyr's default for this board | 48 KB MCUboot + 98 KB + 100 KB slots, all internal [ZEPHYR-DTS] | — |

Internal A/B would squeeze the firmware budget that G18 is about to fix. The NOR chip arrives anyway
for H11, and 16 MB is far more than needed. **Recommended: staging in NOR plus copy-in.**

Proposed internal flash map (this would become part of layout v2, G18):

| Pages | Size | Contents |
|---|---|---|
| 0–7 | 16 KB | Bootloader. Write-protected (option-byte WRP area A). Holds the signing public key |
| 8–9 | 4 KB | Boot-status log, two pages, append-only like today's counter log: install request, trial state, boots left, rollback floor |
| 10–105 | 192 KB | Application slot: signed header (manifest + signature) then the image. Vector table at `0x08005000` (`VECT_TAB_OFFSET`) |
| 106–119 | 28 KB | Reserved |
| 120–127 | 16 KB | Node state at the top of flash, as G18 already plans: key page, counter/epoch log A/B, spare. **The bootloader never writes here** |

Proposed NOR map (16 MB):

| Offset | Size | Contents |
|---|---|---|
| `0x000000` | 256 KB | Image slot X |
| `0x040000` | 256 KB | Image slot Y. X and Y alternate: one holds the last confirmed image (the revert source), the other the next download |
| `0x080000` | 256 KB | Received diff (delta updates only) |
| `0x0C0000` | 64 KB | Update session log: which chunks arrived (resume after a reset) |
| `0x0D0000` | about 15.2 MB | 30-day journal (H11): about 2.4 MB at one 56-byte record per minute |

The update uses 5 % of the chip. NOR timing from the W25Q128JV datasheet [W25Q]: a 256-byte page
programs in under 3 ms (maximum) and a 4 KB sector erases in about 45 ms typical, 400 ms maximum.
Erase the target slot before the download starts, so that no erase happens between chunks.
Re-check these values in the current datasheet revision.

### 4.3 The RX side: the gateway streams; the RX needs no flash

The RX stays a stateless bridge. The gateway keeps the bundle and sends chunks as hex lines when the
node asks. The RX transmits each line once, as it does with ACKs today. The RX does not need the NOR
chip. **The 16 MB flash is needed only at the station.**

RX bridge changes (estimate: under 1 KB of code):

| Change | Why |
|---|---|
| Accept the new downlink kind and its length in `ws_host_reply_ok()`, and the request kind in `ws_air_frame_ok()` | Today only 33-byte ACK/NACK go down, and OBS/DIAG go up |
| Raise the line limit from 256 to at least 512 characters (C `WS_LINE_MAX`, Python `ws0/link.py`) | A 246-byte chunk is 492 hex characters |
| Print `#tx done` after each transmission | The RX drops input while it holds a line, so the gateway sends the next chunk only after this line. Pacing stays on the host |

The RX itself is updated by wire. It sits next to the gateway Mac on USB with its ST-LINK, so
`make ROLE=rx flash` over SSH already reprograms it remotely.

### 4.4 Pull, not push

The node listens only right after it transmits (`protocol.md` §9), and the battery node will sleep
between minutes from Stage 1. The gateway cannot reach it at other times. So **the node asks, and the
gateway answers**. That is the same rule as the ACK, and it keeps the radio policy in the node.

One minute in trickle mode, SF7, NORMAL:

| Time | Direction | Frame |
|---|---|---|
| 0 | node → gw | Live OBS (51 B) |
| +40 ms | gw → node | ACK, with a new "update offered" flag |
| … | | Backlog drain, if any (it has priority) |
| +0.4 s | node → gw | **FW-REQ**: bundle ID, active-image hash, first missing chunk, a 64-bit map of missing chunks after it, how many chunks fit in this minute's cap, node status |
| +0.45 s | gw → node | Up to *n* **FW-DATA** frames back to back (*n* = 27 at SF7 NORMAL). The node writes each one to NOR in the gap |
| about +4.6 s | | The node stops listening after *n* frames or a short silence |

**Resume** follows from the design. The node writes each verified chunk to NOR and records it in
the session log. After a reset, a link outage or a gateway restart, the next FW-REQ simply names
what is still missing. The gateway keeps no session state that matters. It is a server for "send me
chunks *i…j* of bundle *B*".

A proposed wire sketch (this would become protocol draft 6, a wired release of both ends with a new
key, as for every format change; `protocol.md` §2):

| Kind | Direction | Counter space | Plaintext |
|---|---|---|---|
| 2 ACK | gw → node | gateway | Today's 17 B + **1 flags byte** (bit 0: an update bundle is waiting for this node) |
| 5 FW-REQ | node → gw | node | Bundle ID (4), active-image hash prefix (8), first missing chunk (2), missing map (8), chunks wanted (1), status (1): 24 B → 40-byte frame |
| 6 FW-DATA | gw → node | gateway | Bundle ID (4), chunk index (2), data (≤ 224): 246-byte frame |

The bundle is the update file. Its first chunk(s) hold the **manifest**: format version, target
(board role `tx`, protocol draft, node-state layout version), image size, image SHA-256, security
counter, the base-image hash (diffs only), and an ECDSA signature over all of it. The node checks the
target fields at the start and stops at once if they do not match its own.

### 4.5 Node behaviour (application side)

1. **Gating.** Ask for chunks only when LINKED, energy SURPLUS or NORMAL, the journal backlog is below
   a threshold, and the per-minute cap has room. A download never takes air time from live readings
   or the backlog (`radio-energy-policy.md` priority ladder: the update goes below "backlog drain").
2. **Download** into the free NOR slot. Each chunk is already authenticated by CCM.
3. **Delta:** read the active image from internal flash and the diff from NOR; write the rebuilt
   image into the free NOR slot.
4. **Check:** SHA-256 of the staged image = the manifest hash. Optionally also the signature (the
   bootloader checks it in any case).
5. **Install:** only on a healthy supply (G14: brown-out level set, measured voltage above a
   threshold). Append "install slot X" to the boot-status log, report in DIAG, reset.
6. **Trial:** see §5.3.

### 4.6 Energy

The node's added cost is receive time (about 5 mA, the datasheet-class value in
`radio-energy-policy.md` §3), a few short request transmissions, NOR writes and one copy-in.

| Case | Added radio time | Charge (estimate) | Energy at 3.7 V |
|---|---:|---:|---:|
| 54 KB image, SF7 | about 45 s | under 0.15 mAh with the MCU awake | under 0.001 Wh |
| 54 KB image, SF12 | about 8 min | about 1.5 mAh | about 0.005 Wh |
| 7 KB diff, SF12 | about 70 s | about 0.2 mAh | under 0.001 Wh |
| Copy-in at reset | about 4 s of flash work | about 0.01 mAh | negligible |

The core budget is 6 Wh/day, and the PoC cell holds about 24 Wh. **Energy does not limit updates.**
Air time and link quality do. The one energy rule that matters is the install gate in step 5: never
start a flash copy on a sagging battery.

## 5. Security and anti-brick

### 5.1 Two keys with two jobs

| Key | Where it lives | What it protects | If it leaks |
|---|---|---|---|
| Link key (AES-128-CCM, per station; exists today) | Node key page; gateway state directory | **Transport:** who may talk to the node, and the privacy of readings. Also who may send chunks | An attacker can forge readings and ACKs and send chunks. **They still cannot make the node run their code** |
| Signing private key (ECDSA P-256; new) | **Offline**, on Clint's Mac, outside the ws0 state directory, passphrase-protected, with a backup | **Code:** which images may run | An attacker can sign code, but must also hold the link key, or physical access, to deliver it. Fix: reflash the bootloader with a new public key, by wire |
| Signing public key | Inside the write-protected bootloader | — | It is public |

The gateway only stores bundles that are already signed. It never holds the signing key.
The image is signed, not the chunks or the diff: the node checks the final rebuilt image, so a bad
diff cannot pass.

### 5.2 Signature algorithm

| Option | Code in the bootloader | Notes |
|---|---|---|
| **ECDSA P-256 with the STM32WL's PKA (recommended)** | HAL PKA plus software SHA-256 (Mbed TLS `sha256`, already vendored): **estimate 3–5 KB** | The STM32WL55 has a public-key accelerator. `HAL_PKA_ECDSAVerif()` is in the pinned HAL (`stm32wlxx_hal_pka.h`). The host signs with Python `cryptography`, which ws0 already uses. The chip has no SHA hardware |
| Ed25519 in software (for example Monocypher) | estimate 6–10 KB | Simple and well reviewed; no hardware help; needs SHA-512 |
| ECDSA P-256 in software (Mbed TLS bignum/ECP) | estimate 15–20 KB | Too large for a 16 KB bootloader |

Check the STM32WL errata sheet for PKA notes before choosing it.

### 5.3 Anti-brick: how a bad update undoes itself

| Layer | Mechanism |
|---|---|
| 1. The bootloader is never updated over the air | Changed only by wire. Write-protected with option-byte WRP area A. Kept small and host-tested like `node_store.c`, using the `sim_flash` power-cut harness |
| 2. Verify before copy | Manifest signature, image hash, target fields, security counter ≥ the rollback floor. Any failure: keep the current image and report the reason |
| 3. Verify after copy and at every boot | SHA-256 of the internal application slot against its signed header (about 30–60 ms at 48 MHz, an estimate). On a mismatch, copy the last confirmed image back from NOR |
| 4. Trial boot | The bootloader records "trial, 3 boots left" and starts the IWDG before it jumps (once started, the IWDG cannot be stopped). A crash, a hang (watchdog) or the application's own trial timeout (for example 30 min without a confirm, then a deliberate reset) each use up one boot |
| 5. Confirm on proof of work | The new image confirms itself **only after it receives an authentic ACK for an observation it sent**. That proves the sensor path, the key, the counter store, the radio and the gateway all work with the new code. The confirm also raises the rollback floor and makes this image's NOR slot the new revert source |
| 6. Automatic revert | 0 boots left: the bootloader copies the last confirmed image back and records "reverted". The next DIAG shows the old build ID plus a revert reason |
| 7. Last resort | Wired SWD/ST-LINK recovery, as the PRD requires. If both NOR images are invalid, the bootloader stays in a safe loop (red LED) and waits for the wire |

A useful side effect: a release that cannot talk to the gateway (for example a protocol mismatch)
never gets an ACK, so it reverts by itself.

**Node state is outside the update.** The trial image uses the same key, counter log and epoch pages.
Counter reservations made during a failed trial stay in the log, so the reverted image continues
above them, and no nonce repeats (G17). This works only if **an over-the-air release never changes
the protocol draft or the node-state layout**. The manifest carries both versions, and the node
refuses a mismatch. Such changes stay wired releases of both ends with a new key, as today. That
fits the greenfield rule: no migration code, ever.

### 5.4 Rollback protection

The manifest carries a security counter. The bootloader refuses an image below the floor stored in
the boot-status log. The floor rises only when an image **confirms**, so a revert to the previous
image still works. To downgrade on purpose, re-sign the old code with a higher counter. The 1 KB
one-time-programmable area (`OTP_AREA_BASE`, `0x1FFF7000`) could hold a hardware floor later. Not
for the PoC: OTP bits can never be cleared.

### 5.5 STM32WL dual core, option bytes and read protection

| Item | Recommendation for the PoC |
|---|---|
| Cortex-M0+ (CPU2) | Keep it off, as now. ST's secure designs (SBSFU, KMS) run the secure boot, key store and radio stack on CPU2 with "secure mode" (option bytes ESE/SFSA, `OPTIONBYTE_SECURE_MODE`, with optional secure sub-GHz SPI access). That is a complete re-architecture of the radio side. Not worth it here |
| WRP (write protection) | Area A over the bootloader pages 0–7. The application cannot then overwrite the bootloader by mistake |
| RDP (read protection) | Level 1 before field use (already gap G10). A debugger cannot then read flash, but can still mass-erase and reflash, so wired recovery keeps working. Going back to level 0 erases everything, **including the key and counters**, so re-key afterwards (G17). **Never level 2**: it is permanent and ends wired recovery, against the PRD |
| BOR (brown-out reset) level | Set it before any field install (gap G14) |
| IWDG option bits | `IWDG_STOP`/`IWDG_STDBY` decide whether the watchdog counts in low-power modes. Choose them when Stage-1 sleep arrives, so the trial timer counts the right time |
| `BOOT_LOCK`, `nBOOT0`, `nSWBOOT0` | Leave as now. Read RM0453 before setting `BOOT_LOCK`: it changes how the chip boots and may block recovery paths |

Physical access without RDP 1 defeats every software measure: an attacker can read the link key or
reflash the chip. Signed updates protect the radio path, not the box on the mast.

## 6. Off-the-shelf options compared

| | LoRaWAN FUOTA (TS003/004/005) and ST's example | MCUboot | **Minimal custom (recommended)** |
|---|---|---|---|
| What it is | LoRa Alliance packages: TS004 splits a file into fragments with forward error correction (redundant fragments rebuild lost ones without asking); TS005 sets up a multicast group so one transmission reaches many devices; TS003 synchronises clocks [LORA-FUOTA] | A widely used open-source secure bootloader: signed images, test/confirm/revert, security counter [MCUBOOT] | Our bootloader (verify, copy-in, trial, revert) plus FW-REQ/FW-DATA in our protocol |
| Fits a point-to-point link with one node? | **No.** It needs a LoRaWAN stack on the node, a LoRaWAN gateway (an 8-channel concentrator, not one SX126x), a network server (ChirpStack or similar) and a FUOTA server. US915 uplinks hop over 125 kHz channels. It would replace protocol draft 5 entirely. Multicast and FEC help fleets; we have one station | Yes. It is only the bootloader; the transport stays ours | Yes |
| STM32WL status | ST's AN5554 (Rev 6, 2026) describes single-core, dual-core and dual-core + external-flash FUOTA [AN5554]. **But STM32CubeWL v1.5.0 (Feb 2026) "Remove[d] all LoRaWAN projects based on legacy LoRaWAN Mac-Node middleware", and the pinned v1.6.0 has no FUOTA or SBSFU project for this board** (`vendor/STM32CubeWL/Release_Notes.html`, `Projects/`). Older notes say the dual-core SBSFU builds needed IAR EWARM ≥ 9.30.1 "due to flash size constraints", and low power is disabled in the external-flash FUOTA project. Community reports show end-of-transfer and image-swap problems [ST-COMM]. Actility has a third-party FUOTA v1 project for this Nucleo, on Cube 1.3.0 [ACTILITY] | No bare-metal STM32WL port found. Zephyr supports `nucleo_wl55jc` with an MCUboot partition map (48 KB bootloader, two internal ~100 KB slots) [ZEPHYR-DTS]. Signing keys: RSA-2048/3072, ECDSA P-256, Ed25519 [IMGTOOL] | Uses only the pinned HAL (flash, SPI, PKA, IWDG) |
| Size | Large: the LoRaWAN stack plus SBSFU/KMS | Estimate 24–48 KB (Zephyr reserves 48 KB) | Estimate 12–16 KB |
| Fit with external staging + copy-in | Built in (external-flash variant) | Its swap modes move data between both slots and have sector-size rules (2 KB internal pages, 4 KB NOR sectors); revert is tied to swapping. "Overwrite-only" mode has no revert [MCUBOOT] | Designed for it: the NOR keeps both the new and the last good image, so revert is just "copy the other one" |
| Work | Highest: a new radio protocol, new infrastructure | Port: flash-map back end for internal + SPI NOR, config, Makefile integration, learn about 10k lines | Write about 800–1,200 lines of C (estimate), with our host power-cut tests |
| Main risk | Everything | Integration surprises in an unfamiliar codebase | Our own bootloader bugs: mitigated by size, host tests, WRP and wired recovery |

**Recommendation: minimal custom.** The project already owns its envelope, its power-cut test harness
and reproducible builds. The bootloader's job here is narrow: check a signature, copy one slot, count
trial boots. Borrow from MCUboot the ideas that matter: a signed header in front of the image, the
image-OK/confirm flag, a security counter separate from the version. **Fallback:** port MCUboot
(ECDSA P-256, `MCUBOOT_HW_ROLLBACK_PROT`) if the custom bootloader fails its power-cut tests or
grows past about 16 KB. Do not use LoRaWAN FUOTA.

## 7. Staged plan

Precondition for all stages: H01 passed, flash layout v2 (G18) and the NOR journal (H11) built.
**Accommodation now, at no code cost:** when layout v2 is designed, reserve pages 0–9 for a future
bootloader and boot-status log, and put the application vector table at `0x08005000`. This matches
the PRD rule "documented accommodation where cheap". Without it, adding updates later means one more
wired layout change.

| Stage | Content | Bench pass criterion |
|---|---|---|
| **U0** Decide | Decisions U1–U8 below; signing-key custody written in a runbook | Clint's decisions recorded; PRD amended or not |
| **U1** Bootloader, wired only | Bundle format; `tools/fw_sign.py` (Python `cryptography`); the Makefile adds the signed header; bootloader (verify, copy-in, trial, revert, WRP); test bundles put into NOR by a wired console command | Host tests: power cut at every erase/program step of copy-in and of the boot-status log, always ending in a valid image. Bench: genuine bundle installs; **1 flipped byte, a wrong key, a lower security counter, a wrong target each refused**; 20 resets (reset pin) at random points during copy-in, always boots; a trial image that hangs (`TEST-HANG`) or never confirms is reverted after 3 boots; key page and counter log byte-identical before and after |
| **U2** Transfer over USB | The same FW-REQ/FW-DATA frames, carried over the TX's USB console from the host instead of the radio | Transfer cut at 10 random points, then resumed, finishes with the right hash; a corrupted chunk is refused by CCM and fetched again; confirm happens on the first ACKed observation |
| **U3** Over the air, full images | Protocol draft 6 (ACK flag, kinds 5/6) on both ends (wired release with a new key); RX `#tx done` and 512-character lines; ws0 `fw stage`, `fw status`, `/v1/status` progress; trickle mode inside the cap | 54 KB at SF7 NORMAL in ≤ 12 min; **every live reading committed within 120 s during the update** (H01 rule); with 20 % of chunks dropped on purpose by the gateway it still completes; RX unplugged mid-transfer resumes; a deliberately broken signed image (never ACKed) reverts by itself and DIAG reports it |
| **U4** Delta updates | Gateway makes diffs from released `.bin` files (detools sequential + heatshrink); node applier; base-hash check | The real `45f43e78fe91 → bc5e6ede429c` diff (7.4 KB) rebuilds the exact release hash on the node; a diff for the wrong base is refused before download |
| **U5** Field readiness | RDP 1, WRP, BOR level, written key-custody and recovery runbook; repeat at the H01 radio settings (SF and power) | 24 h soak with 3 updates and 1 forced revert while the H01 criterion still passes |

Costs (estimates unless marked):

| Item | Internal flash | RAM |
|---|---:|---:|
| Bootloader (custom) | 12–16 KB, in its own pages | Its own, during boot only |
| Application: update client (requests, map, resume, staging, SHA-256, confirm) | 3–5 KB | about 1 KB |
| Application: delta applier (detools + heatshrink) | 3–5 KB | 2–3 KB |
| SPI NOR driver | Shared with H11 (already in the 6–10 KB H11 estimate) | — |
| RX bridge | under 1 KB | +0.5 KB line buffer |
| Boot-status log | 4 KB (2 pages) | — |
| NOR | 832 KB of 16 MB | — |

The application grows by an estimated 6–10 KB. That is affordable only after layout v2, not in
today's 64 KB region (11.5 KB left).

## 8. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Bootloader bug | A brick that needs a ladder and a laptop | Wired-only bootloader updates, small code, host power-cut tests, WRP, U1 bench matrix |
| An OTA release changes the protocol or the node-state layout | Lost link, or nonce reuse (G17) | Manifest carries both versions and the node refuses a mismatch; such releases stay wired with a new key; an unconfirmed image reverts by itself |
| Install on a weak battery | Torn flash, brown-out loop (E11) | BOR level (G14), voltage gate before install, energy state ≥ NORMAL |
| Scope creep against the PRD | Work before the gates are passed | Only the free layout accommodation before H01/G18/H11; U1 onward only with an explicit PRD change |
| Signing-key loss | No more updates until a wired bootloader reflash with a new key | Encrypted offline backup |
| Signing-key theft | Code can be signed. Delivery still needs the link key or physical access | Keep it off the gateway; RDP 1 in the field |
| More air time on a not-yet-measured transmitter (6 dB bandwidth, antenna gain unknown) | Compliance doubt | Same open item as today; measure before the field. Trickle mode keeps the per-minute cap |
| NOR or internal-flash wear | — | Negligible: an update writes each sector once |
| Debugging gets harder | A field unit runs code nobody can attach to | DIAG reports build ID, update status, revert reason; RX logs every FW-REQ |

## 9. Decisions for Clint

| # | Decision | Options (recommendation first) |
|---|---|---|
| U1 | Scope | (a) Reserve the layout now, build U1–U5 after H01/G18/H11, with a PRD amendment; (b) keep wired-only (PRD as written); (c) a cheaper middle way: a sealed external SWD/USB service port on the enclosure |
| U2 | Bootloader | (a) Minimal custom; (b) MCUboot port |
| U3 | Signature | (a) ECDSA P-256 with the PKA; (b) Ed25519 in software |
| U4 | Signing-key custody | Where the private key lives and how it is backed up (file on the Mac with a passphrase; a hardware token). Never in the ws0 state directory |
| U5 | Confirm rule | (a) First authentic ACK for an observation from the new image; (b) also require a valid sensor reading (a broken sensor would then revert good code); (c) also require a gateway "commit" command |
| U6 | Scheduling | (a) Trickle inside the existing per-minute cap, NORMAL and SURPLUS only; (b) also allow session mode outside the cap; (c) allow full images only in SURPLUS when SF ≥ 10 |
| U7 | Delta updates | (a) Later stage (U4) after full images work; (b) in the first OTA release |
| U8 | Rollback | (a) Floor rises at confirm; downgrade only by re-signing with a higher counter; (b) no rollback protection in the PoC |
| U9 | Read protection | RDP 1 before field use (already G10): confirm, and accept that going back to RDP 0 erases the key |

## Sources

- [FCC247] 47 CFR §15.247 — <https://www.law.cornell.edu/cfr/text/47/15.247> (also eCFR:
  <https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-15/subpart-C/section-15.247>).
  Read 2026-10-14: (a)(1)(i) 0.4 s in 20 s / 10 s for hopping; (a)(2) 6 dB bandwidth ≥ 500 kHz with
  no dwell limit; (b)(3) 1 W; (b)(4) antenna above 6 dBi; (e) 8 dBm/3 kHz.
- [RP002] LoRa Alliance, *RP002 Regional Parameters* (US915 data rates and the 400 ms dwell limit
  behind the 11-byte DR0 payload) — <https://resources.lora-alliance.org/technical-specifications>
- [LORA-FUOTA] LoRa Alliance FUOTA building blocks (TS003, TS004 v2.0.0, TS005 v2.0.0, TS006) —
  <https://lora-alliance.org/event/lora-alliance-building-block-specifications-of-firmware-updates-over-the-air-fuota/>;
  AWS IoT Core for LoRaWAN FUOTA overview —
  <https://docs.aws.amazon.com/iot-wireless/latest/developerguide/lorawan-mc-fuota-overview.html>
- [AN5554] ST AN5554, *LoRaWAN firmware update over the air with STM32CubeWL* —
  <https://www.st.com/resource/en/application_note/an5554-lorawan-firmware-update-over-the-air-with-stm32cubewl-stmicroelectronics.pdf>
  (the PDF timed out here; content from the search summary of Rev 6, March 2026).
- STM32CubeWL v1.6.0 release notes, pinned in `tools/fetch-vendor.sh` —
  `vendor/STM32CubeWL/Release_Notes.html` (v1.5.0 removed the legacy LoRaWAN projects; IAR and
  low-power notes for SBSFU/FUOTA projects); HAL headers `stm32wlxx_hal_pka.h`,
  `stm32wlxx_hal_flash.h`; CMSIS `stm32wl55xx.h` (`OTP_AREA_BASE`, 1 KB).
- [ST-COMM] ST community, *STM32WL FUOTA firmware swapping issue* —
  <https://community.st.com/stm32-mcus-wireless-35/stm32wl-fuota-firmware-swapping-issue-152460>
- [ACTILITY] Actility, `nucleo-stm32wl55jc-fuotav1` — <https://github.com/actility/nucleo-stm32wl55jc-fuotav1>
- [MCUBOOT] MCUboot design — <https://docs.mcuboot.com/design.html> (upgrade modes, image trailer and
  confirm, `MCUBOOT_HW_ROLLBACK_PROT`)
- [IMGTOOL] MCUboot imgtool — <https://docs.mcuboot.com/imgtool> (rsa-2048, rsa-3072, ecdsa-p256, ed25519)
- [ZEPHYR-DTS] Zephyr `nucleo_wl55jc.dts` —
  <https://github.com/zephyrproject-rtos/zephyr/blob/main/boards/st/nucleo_wl55jc/nucleo_wl55jc.dts>;
  board page <https://docs.zephyrproject.org/latest/boards/st/nucleo_wl55jc/doc/nucleo_wl55jc.html>
- [DETOOLS] detools — <https://detools.readthedocs.io/en/latest/> (version 0.53.0 used for §3.5)
- [W25Q] Winbond W25Q128JV datasheet — <https://cdn.sparkfun.com/assets/7/2/4/9/e/w25q128jv.pdf>
  (timing values to re-check against the current revision)
- Repository: `docs/protocol.md`, `docs/protocol-stack.md` §5.1, §8, `docs/firmware-budget.md`,
  `docs/radio-energy-policy.md`, `docs/failure-modes.md` (G10, G14, G17, G18),
  `docs/next-stages-plan.md`, `docs/poc-shopping-list.md`, `firmware/stage0-node/RELEASES.md`,
  `App/radio_cfg.h`, `App/flash_layout.h`, `App/app_rx.c`, `App/app_tx.c`, `App/watchdog.c`, PRD/TRD v0.2.
