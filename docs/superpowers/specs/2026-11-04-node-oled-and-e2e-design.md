# Node OLED and the end-to-end bench link

Date: 2026-11-04. Status: draft for Clint's review (builder check done; its questions answered below).

## Intent

The TX node firmware (`firmware/stage0-node`, ROLE=tx) drives the bench OLED itself, and the r1 bench runs the real system
end to end: TX samples every sensor and the weather meter, sends them over the real authenticated LoRa protocol, the
RX relays the frames (unchanged, keyless), and the gateway (`ws0 serve`) decrypts, acknowledges, records and serves
them on the live station website. Today the r1 bench has only been proved with the bench tool (`firmware/i2cscan`),
which shows readings on the OLED but sends nothing.

Why now: everything but the power island is wired and checked (2026-11-04); the power parts arrive 2026-11-05. The
next proof the bench owes is that the station's data reaches the website, field by field.

The OLED is for the person at the bench: "the TX should only show the things it knows about, maybe when it
transmits a packet" (Clint), with cyberpunk touches: animated interludes drawn from the node's real data, within the
power, memory and bus bandwidth the node has.

## Goals

1. A **bench build** of the TX node firmware (`WS_BENCH_OLED=1`; Clint, 2026-11-04) drives the OLED with layout C and seven interludes (below), without blocking: `make waits`
   stays clean.
2. B1, B2 and B3 control the screen (below).
3. The internal flash is re-split: firmware 95 pages (190 KB), journal 30 pages (about 10 h of backlog), until the
   16 MiB SPI flash takes over the journal (H11).
4. The TX is built for power profile B (`WS_POWER_PROFILE=2`: INA228 0x40, 0x41, 0x45, 0x48 and the MAX17048), the
   r1 bench's wiring.
5. Both boards run `stage0-node` (TX and RX). Today: a dev build, to prove the OLED, weather and wind/rain end to
   end. After the power island (2026-11-05): one recorded release with the power acceptance drill, provisioned once
   (Clint, 2026-11-04).
6. A host check proves, from the gateway's own HTTP API, that every field of the station arrives with a plausible
   value, and a short hand checklist proves the moving parts (cups, vane, rain, a breath on the SHT45).

## Non-goals

- No protocol change: the version 6 observation (77 B plaintext) already carries every field (`App/node_fields.h`).
- No RX change: it stays a keyless bridge (`App/app_rx.c`). No display on the RX.
- No website change: `ws0/static` already shows wind (with calm), rain, UV, pressure, the enclosure, and the battery,
  solar, USB-C, energy, charge and state-of-charge panels.
- No migration of old journals or keys (greenfield: reflash everything together).
- Not H01 evidence, and not a qualified regional radio configuration.

## Anti-goals

- The OLED must never delay sampling, the radio exchange or the ACK window. A display fault (SPI or DMA error, or a DMA that does not end) turns
  the display off and is reported once; it never resets the node or stops a frame.
- The OLED shows nothing the TX does not itself know. It never claims the website has a reading; an ACK means only
  that the gateway authenticated and journaled that frame.
- Nothing here weakens the flash guard: the shared linker region stays the same for every project on the board, so a
  bench-tool image still cannot reach the node key or journal.

## Constraints

- STM32WL55JC, 256 KB flash in 2 KB pages. RAM: RAM1 32 KB holds .data, .bss, heap and the 8 KB stack, and a
  profile-B TX already uses about 29.2 KB of it (builder check, measured); RAM2 32 KB is unused and has a
  `.RAM2_region` output section. **The display buffers go in RAM2.** Code runs only from internal flash (no memory-mapped QSPI).
- The node's rules (`firmware/README.md`, `docs/firmware-event-model.md`): no run-time busy-wait (`make waits`), the
  strict warning set with `-Werror`, the code-space budget line (`FLASH_BUDGET_PCT`), the stack bound.
- The node runs with `LOW_POWER_DISABLE=1` (sleep only), so DMA keeps running between events.
- USART2 TX already uses DMA1 channel 5 (`board/nucleo-wl55jc/Core/Src/dma.c`); the OLED takes another channel
  through DMAMUX (SPI1_TX request).
- OLED: Adafruit #2674, SSD1325, 128 x 64, 4 bits a pixel; SPI1 mode 0 at most 1 MHz (750 kHz now); pins PA4 CS, PA5
  SCLK, PA7 DIN, PC2 DC, PC1 RST (as `i2cscan/App/oled.c`). One full frame is 4096 bytes, about 44 ms at 750 kHz.
  Mounted upside down on BB3 (DS1 rot 180): frames are turned 180° in software.
- The panel draws 50-150 mA from 3V3, far more than the animations cost; in mode B its link (JP2) or B3 turns it off.
- Font: the 5×7 font of `i2cscan/tools/make_font.py` (capitals, digits, a few symbols, lowercase a h m s); this work
  adds what the screens use (at least z and #). Every screen string must be in the font (a test checks).
- Buttons: B1 PA0, B2 PA1, B3 PC6, all free in the node (`docs/hardware/bench-station-wiring.md` "reserved"). The
  board's GPIO setup already arms PC6's EXTI; `board_inputs.c` serves EXTI9_5 for it.
- Rules for this repo: never read or print anything under `run*/` directories. The host check reads the gateway's
  HTTP API, not the run directory.

## Approaches (Clint chose A)

- **A. A shared display library plus a DMA-driven OLED module in the node.** The frame buffer, font, text and
  drawing primitives move from `i2cscan/App` to `firmware/common/`, so the bench tool and the node share one tested
  copy. The node adds a non-blocking SPI1 + DMA driver and a screen state machine fed by data it already has.
  Chosen: one copy to fix, and the only option that meets the no-busy-wait rule and allows animation.
- B. Copy the bench tool's OLED code into the node. Quick to start, but two copies drift, and the bench driver polls
  SPI, which the node forbids; it would be rewritten anyway.
- (Dropped) Send a slice of the frame each 250 ms tick without DMA: no new driver, but a few frames a second at most,
  which kills the animations.

## What was decided

### The screen

Layout C, 21 characters × 8 rows at 6 × 8 pixels, drawn in a 1-bit 128 × 64 frame buffer (1 KB), turned 180° and
expanded to the SSD1325's 4-bit column format into a 4 KB send buffer, sent by DMA.

```
AIR  23.1C  50.8%        SHT45 (outside air)
BOX  22.9C  52.2%        SHTC3 (enclosure)
P 983.0hPa   UV 0        BMP581, LTR390 counts
WIND 1.3m/s NE G2.7      speed, vane point, gust
RAIN 2 TIPS 0.56mm       tips since boot
BATT +37.6mA 3.85V       INA228 0x40 (NO INA228 when absent)
CELL 3.85V 78% CHG       MAX17048, charger state (NO MAX17048)
TX 1233 ACK 58s AGO      last frame, its outcome, age
```

Each row shows the part's name and "NO <part>" when the module is absent. Readings are the node's live values (its
latest sample of each module), redrawn once a second. Packet banner: when a frame goes out, the bottom two rows invert
and show the send, then the outcome (ACK with its RSSI and SNR, or NO ACK), for about 3 s.

### Field builds

`WS_BENCH_OLED` defaults to 0. Without it the TX carries no display code and leaves PA4, PA5, PA7, PC1 and PC2 as
reset left them; the buttons PA0, PA1 and PC6 stay what the board's GPIO setup (`MX_GPIO_Init`) makes them in every
build, pull-up inputs with a falling-edge EXTI line, and a press does nothing (no EXTI0 or EXTI1 vector; PC6's
EXTI9_5 vector is served but forwards nothing). Its budget line is the field figure. The bench build and its flag are what
`RELEASES.md` records for the r1 bench. A `make` check builds both and fails if the field build links any display
symbol.

### The interludes

All seven, drawn only from what the TX knows. Mockups (true scale, real font) are in
`.superpowers/brainstorm/83868-1793832625/content/` (oled-interludes-v2.html, oled-hack-the-planet.html).

1. **Packet burst**, once per minute's exchange, on its live reading (my call): backlog frames, the extra frame after
   a missed ACK and the health report do not each get a burst; the ACK banner counts them ("+3 BACKLOG", and "+HEALTH" for the report), so a drain
   cannot hold the screen. Before the ACK banner: LoRa up-chirps sweeping across, then the
   frame's real ciphertext scrolling as hex, and a footer of the radio settings (SF, BW, frequency, frame length).
2. **Wind scope**: the last 30 s of cup pulse rate (4 Hz bins) on a dotted grid, scrolling; speed and gust below.
3. **Vane compass**: a compass rose, the needle at the vane's position, its point, degrees and raw millivolts.
4. **System bars**: flash, RAM and stack use, journal fill, radio airtime used this minute, as bar meters.
5. **Boot splash with glitch**: radio settings, key present and epoch, modules found, a sliced-row glitch and a
   progress line, at start.
6. **HACK THE PLANET**: original pixel art, an eyepatch smiley (double ring, open eye, patch and strap, smile) with
   HACK, THE, PLANET typed in at double size, a wink, a glint on the patch, then a glitch out; about 3 s. It plays
   after the boot splash and in the rotation.
7. **Rain** (Clint, 2026-11-05): mm and tips since boot, the last tip's age, the rate of the last 10 minutes in
   mm/h, and a bar a minute for the last hour (tips a minute, scaled to the largest, at least 4). The history is
   the rain module's (`mod_rain_history`, in every build: 60 bytes of RAM and the last tip's time).

Timing: one interlude from the rotation (2, 3, 7, 4, 6) about every 2 minutes, about 8 s, at about 8 frames a second.
Never during a packet burst or banner (the radio exchange wins); an interlude in progress yields to a packet.

### The buttons (my call, to confirm)

- **B1**: next screen (normal, then each interlude of the rotation in turn: scope, vane, rain, system, HACK; then back).
- **B2**: pause or resume the automatic rotation (paused: the screen stays where B1 put it; packets still show).
- **B3**: OLED on or off (off: no SPI traffic, panel commanded to sleep).

Debounced in software from the existing EXTI lines; a press never blocks.

### Bandwidth and memory

During an interlude, 8 frames a second of 44 ms is about 35 % of SPI1 time; otherwise one frame a second, about 4 %.
RAM: 1 KB frame buffer, 4 KB send buffer, small state; about 5.5 KB, all in RAM2 (RAM1 has about 3.5 KB free). Flash: the library, font, screens and
driver, expected 6-10 KB; inside the new 190 KB region.

### The flash re-split

`WS_FIRMWARE_PAGES` 55 → 95, `WS_JOURNAL_PAGES` 70 → 30 (`App/flash_layout.h`), the shared linker script's FLASH
`LENGTH` 110K → 190K (`board/nucleo-wl55jc/*.ld`), and every comment, budget line and test that names 110 KB, pages
0-54 or 24 h. The backlog becomes (30 - 1) × slots, about 10 h at the 77-byte record. A new journal page layout
means a new run directory and key (greenfield). H11 (the 16 MiB SPI flash) later moves the journal off-chip.

### The end-to-end bring-up

1. Build TX (ROLE=tx, WS_POWER_PROFILE=2) and RX; record both in `stage0-node/RELEASES.md` (hashes, budget lines).
2. Flash both. This ends the long `benchlink` run on the RX.
3. `ws0 init` a new hardware run directory, `ws0 provision-node` the TX, `ws0 serve` on the RX (as
   `stage0-node/README.md`). Clint runs the provisioning; nothing prints the key.
4. Host check (new, under `tools/`): polls the gateway's HTTP API for the station's latest observations and fails
   unless every expected field is present, in range and recent: outside T and RH, enclosure T and RH, pressure, UV,
   wind speed, gust, direction (or calm), rain tips, and each power field the profile fits. Profile 2 always sends
   the battery, load, solar and USB-C slots, so before the power island they arrive **INVALID**, not "not fitted";
   with `--power-pending` the check expects exactly that and says so, and without it the power fields must be valid.
   The API needs the gateway's bearer token: the check reads it from the environment variable `WS0_API_TOKEN`, which
   Clint sets in his own shell (Clint, 2026-11-04). The check never opens the run directory.
5. Hand checklist, each seen on the website within two minutes: spin the cups (speed and gust rise), turn the vane to
   two points (direction follows), tip the bucket three times (tips +3), breathe on the SHT45 (RH rises), shade and
   light the LTR390 (UV changes). The OLED's banner shows ACK for each frame.

## Order of work

1. Commit the bench-tool work of 2026-11-04 (`firmware/i2cscan` meters, sensors, font, screen, tests, README) as
   the baseline (Clint, 2026-11-04).
2. Move the display library to `firmware/common/`; the bench tool uses it, its tests pass unchanged.
3. The flash re-split.
4. The node's DMA driver, screens, interludes and buttons behind `WS_BENCH_OLED`.
5. The host check.
6. Today's dev bring-up; the release after the power island.

## Left to the builder

- The module and file names inside `firmware/common/` and `stage0-node/App/`, and how the node exposes its live
  values to the screen (accessors next to the existing `mod_*_snapshot` functions, or a view struct filled each tick).
- The DMA channel, the frame scheduler's exact timing, and the debounce time.
- The pixel art itself, within the mockups.
- Which existing tests move with the shared library, and the new tests: font coverage of every screen string,
  rotation, layout rows, the SSD1325 column expansion, the scheduler (a packet preempts an interlude), the buttons.
- The host check's API calls, after reading `ws0/web.py`.
