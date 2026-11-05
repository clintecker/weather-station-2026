# Node OLED and End-to-End Bench Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A bench build of the TX node firmware drives the OLED (layout C, six interludes, three buttons) without blocking, on a re-split flash, and a host check proves every station field reaches the gateway's API.

**Architecture:** The pure display code (frame buffer, font, drawing, SSD1325 expansion) moves to `firmware/common/` and is shared by the bench tool and the node. The node gains a DMA SPI1 driver and a screen state machine behind `WS_BENCH_OLED=1`, fed by small read-only "live" accessors on the existing modules and by three exchange hooks. A Python tool polls the gateway's `/v1/observations/latest` with a bearer token from `WS0_API_TOKEN`.

**Tech Stack:** C (gnu11, the strict warning set, `-Werror`), STM32CubeWL HAL/LL, GNU make, Python 3 `unittest` with `tests/toolchain.py` host builds, `ws0`.

**Spec:** `docs/superpowers/specs/2026-11-04-node-oled-and-e2e-design.md`

## Global Constraints

- No run-time busy-wait in the node: `make waits` (tools/blocking_report.py) stays OK for ROLE=tx with and without `WS_BENCH_OLED=1`.
- Our C builds with board.mk's strict warning set and `-Werror`; no dynamic allocation (`NO_HEAP = 1`).
- `WS_BENCH_OLED` defaults to 0. A field build links no `oled_`/`scr_` symbol and leaves PA4, PA5, PA7, PC1, PC2 untouched; PA0, PA1 and PC6 stay the board's pull-up falling-edge EXTI inputs (`MX_GPIO_Init`), with no vector that acts on them.
- Display buffers live in RAM2 (`__attribute__((section(".RAM2_region")))`); RAM1 has about 3.5 KB free.
- OLED: SSD1325, 128 × 64, 4 bits a pixel, 4096 bytes a frame, SPI1 mode 0 at ≤ 1 MHz; PA4 CS, PA5 SCLK, PA7 DIN, PC2 DC, PC1 RST; frames turned 180° (DS1 rot 180).
- Buttons: B1 PA0 next screen, B2 PA1 pause/resume rotation, B3 PC6 OLED on/off.
- Flash: `WS_FIRMWARE_PAGES 95`, `WS_JOURNAL_PAGES 30`, linker FLASH `LENGTH = 190K`, `APP_FLASH_BYTES 194560`.
- Never read or print anything under `run*/`. The host check takes its token only from `WS0_API_TOKEN`.
- Every screen string uses only glyphs in the font; a test enforces it.
- Commit to master after each task (Clint approved committing for this work); do not push.

## Review Focus

- A packet goes out while a 44 ms DMA frame is mid-transfer: the banner must start on the next frame, never corrupt or abort the one in flight (Task 6, `test_packet_waits_for_frame_in_flight`).
- SPI or DMA error, or no panel fitted: the display turns itself off, says `#oled fault` once, and the node keeps sampling and sending (Task 4, `test_dma_error_disables_display_once`).
- A backlog drain of 5 frames plus a health report: one burst, one banner counting "+5", rotation resumes after (Task 6, `test_drain_shows_one_burst`).
- B1 pressed repeatedly or bouncing within the debounce time: one step per press, and wrapping from the last interlude back to the normal screen (Task 7, `test_button_bounce_and_wrap`).
- The gateway is up but has no observation yet, or the token is wrong: the check exits non-zero with a plain message, not a traceback (Task 8, `test_no_observation_and_bad_token`).

---

### Task 1: Shared display library

**Files:**
- Create: `firmware/common/oled_fb.c`, `firmware/common/oled_fb.h` (moved from `firmware/i2cscan/App/`), `firmware/common/font5x7.c`, `firmware/common/font5x7.h` (moved), `firmware/common/oled_draw.c`, `firmware/common/oled_draw.h`
- Move: `firmware/i2cscan/tools/make_font.py` → `firmware/common/tools/make_font.py` (writes `firmware/common/font5x7.c`)
- Modify: `firmware/i2cscan/Makefile` (sources from `../common`), `firmware/i2cscan/App/i2cscan.c` (uses `ssd1325_frame`)
- Test: `tests/test_oled_fb.py` (the `BenchScreen` font/fb/rotation tests move here from `tests/test_i2cscan.py`; layout tests stay)

**Interfaces:**
- Produces (oled_fb.h, unchanged): `oled_clear`, `oled_set`, `oled_get`, `oled_text(fb,x,y,s,scale)`, `oled_rotate180`, `ssd1325_column`, `OLED_W 128`, `OLED_H 64`.
- Produces (oled_draw.h): `void oled_line(oled_fb *fb, int x0, int y0, int x1, int y1, unsigned dash);` (dash 0 = solid, else on/off run length), `void oled_box(oled_fb *fb, int x, int y, int w, int h);`, `void oled_fill(oled_fb *fb, int x, int y, int w, int h, int on);`, `void oled_dotgrid(oled_fb *fb, int x, int y, int w, int h, int step);`, `void oled_invert(oled_fb *fb, int x, int y, int w, int h);`, `void oled_circle(oled_fb *fb, int cx, int cy, int r);`, `void oled_disc(oled_fb *fb, int cx, int cy, int r, int on);`, `void oled_shift_row(oled_fb *fb, int y, int dx);` (glitch slice), `void ssd1325_frame(const oled_fb *fb, int rotate180, uint8_t out[4096]);` (all 64 column pairs in send order).
- Font adds glyphs `z # > < : * |` and lowercase `d b g o i n t p e l c u r k` (whatever the screens of Tasks 5-6 use).

- [ ] **Step 1: Write the failing tests** in `tests/test_oled_fb.py`: the moved font/fb/rotation tests unchanged, plus
```python
def test_line_endpoints_and_dash(self):   # oled_line(fb,0,0,9,0,0) lights x 0..9 on y 0; dash=2 lights 0,1,4,5,8,9
def test_box_is_outline_only(self):       # oled_box(fb,2,2,5,4): perimeter 14 pixels lit, (4,3) dark
def test_invert_twice_is_identity(self):
def test_dotgrid_spacing(self):           # oled_dotgrid(fb,0,0,32,16,16): (0,0),(16,0),(0,2),(2,0) lit; (1,1) dark
def test_shift_row(self):                 # a pixel at (10,5) after oled_shift_row(fb,5,4) is at (14,5); row 4 unchanged
def test_ssd1325_frame_matches_columns(self):  # ssd1325_frame(fb,0,out)[cp*64:(cp+1)*64] == ssd1325_column(fb,cp) for every cp
def test_ssd1325_frame_rotated(self):     # a pixel at (0,0) lands where ssd1325_column of the rotated fb puts (127,63)
```
- [ ] **Step 2: Run** `.venv/bin/python -m unittest tests.test_oled_fb -v` → FAIL (no oled_draw).
- [ ] **Step 3: Move the files with `git mv`, add `oled_draw.c` and the glyphs, point `make_font.py`'s OUT at `firmware/common/font5x7.c`, and switch i2cscan to `ssd1325_frame(&drawn, 1, buf)` in place of its own rotate copy.**
- [ ] **Step 4: Run** `.venv/bin/python -m unittest tests.test_oled_fb tests.test_i2cscan -v` → PASS; `make -C firmware/i2cscan` and `make -C firmware/benchlink ROLE=tx` and `ROLE=rx` build.
- [ ] **Step 5: Commit** `git commit -m "common: shared OLED frame buffer, font and drawing for the bench tool and the node"`

### Task 2: Flash re-split 95 / 30

**Files:**
- Modify: `firmware/stage0-node/App/flash_layout.h` (`WS_FIRMWARE_PAGES 95U`, `WS_JOURNAL_PAGES 30U` and its comment: about 10 h), `firmware/board/nucleo-wl55jc/STM32WL55JCIX_FLASH.ld` (`LENGTH = 190K`, comment pages 95..127), `firmware/board/nucleo-wl55jc/board.mk` (`APP_FLASH_BYTES ?= 194560`, header comment), `firmware/stage0-node/Makefile` (budget comment: 190 KB, pages 0-94), `firmware/stage0-node/App/node_store.h`, `node_store.lit.md` and the tangled `node_store.c` (any 24 h / page-count text; run `tools/tangle.py`), `docs/firmware-budget.md`, `firmware/README.md`, `firmware/stage0-node/README.md` ("Flash layout and outage capacity": the new record count and hours)
- Test: `tests/test_flash_layout.py`, `tests/test_store_powercut.py`, `tests/test_loop_bounds.py` (update the constants they pin)

**Interfaces:**
- Produces: `WS_FIRMWARE_BYTES == 194560`, `WS_JOURNAL_FIRST == 95`, the journal ring of 30 pages.

- [ ] **Step 1: Update the tests first**: `test_flash_layout.py` asserts `WS_FIRMWARE_PAGES == 95`, `WS_JOURNAL_PAGES == 30`, `WS_JOURNAL_FIRST >= WS_FIRMWARE_PAGES`, the linker `LENGTH = 190K` equals `WS_FIRMWARE_BYTES`, and `APP_FLASH_BYTES` in board.mk equals it too; the outage-capacity test asserts `(30 - 1) × slots_per_page` records and ≥ 9.5 h at one record a minute.
- [ ] **Step 2: Run** `.venv/bin/python -m unittest tests.test_flash_layout tests.test_store_powercut tests.test_loop_bounds -v` → FAIL.
- [ ] **Step 3: Change the constants, comments and docs listed above.**
- [ ] **Step 4: Run** the same tests → PASS; `make -C firmware/stage0-node ROLE=tx` and `ROLE=rx` build and print a budget line against 194560; `make -C firmware/i2cscan` and `benchlink` still link (they share the linker script).
- [ ] **Step 5: Commit** `git commit -m "flash: 190 KB firmware, 30-page journal (about 10 h) until H11 moves the journal off-chip"`

### Task 3: Live values for the screen

**Files:**
- Modify: `firmware/stage0-node/App/mod_th.{c,h}`, `mod_reg.{c,h}`, `mod_wind.{c,h}`, `mod_rain.{c,h}`, `power_acq.{c,h}`
- Test: `tests/test_modules.py`, `tests/test_power_acq.py`

**Interfaces:**
- Produces:
  - `int mod_th_live(enum th_unit u, int32_t *centi_c, int32_t *centi_rh);` 1 and the latest valid sample, 0 if none in the last 30 s.
  - `int mod_reg_live(enum reg_unit u, int32_t *value);` pressure in 0.1 hPa, UVA in raw counts; same 30 s rule.
  - `typedef struct { uint16_t speed_cms, gust_cms; uint16_t vane_mv; int8_t point; uint8_t bins[120]; uint8_t nbins; } wind_live_t;` and `int mod_wind_live(wind_live_t *w);` speed over the last 3 s, gust over the window so far, `point` 0..15 or -1 out of table, `bins` the last 30 s of 250 ms pulse counts, oldest first.
  - `uint32_t mod_rain_tips_since_boot(void);`
  - `typedef struct { int batt_ok; int32_t batt_ma_x100, out_mv; int gauge_ok; uint16_t vcell_mv, soc_pct_x10; int charging; } power_live_t;` and `void power_acq_live(power_live_t *p);`
  - No writes and no side effects: reading never changes a window or a probe.

- [ ] **Step 1: Write the failing tests** in the existing harnesses:
```python
# test_modules.py
def test_th_live_after_sample(self):      # after one simulated SHT45 reply of 25.00 C / 56.50 %: (1, 2500, 5650)
def test_th_live_goes_stale(self):        # 31 s with no reply: returns 0
def test_reg_live_pressure_and_uva(self): # a BMP581 reply of 101325*64 Pa raw -> 10133; LTR390 0x00007B -> 123
def test_wind_live_bins_and_point(self):  # 8 pulses in one 250 ms bin -> bins[-1] == 8; vane at 595 mV -> point 6 (SE)
def test_rain_tips_since_boot(self):      # three tips 200 ms apart -> 3; two within 100 ms -> 1
def test_live_reads_do_not_change_window(self):  # a latch after many *_live calls equals one without them
# test_power_acq.py
def test_power_live_absent_parts(self):   # no INA228, no gauge answering: batt_ok == 0, gauge_ok == 0
```
- [ ] **Step 2: Run** `.venv/bin/python -m unittest tests.test_modules tests.test_power_acq -v` → FAIL.
- [ ] **Step 3: Implement the accessors** from each module's existing state (keep a "last valid sample at" ms in mod_th and mod_reg; the wind ring of 120 bins is new, filled in `mod_wind_tick`).
- [ ] **Step 4: Run** the same tests → PASS; `make -C firmware/stage0-node ROLE=tx` builds; `make waits` OK.
- [ ] **Step 5: Commit** `git commit -m "node: read-only live values from each module for the bench screen"`

### Task 4: DMA OLED driver behind WS_BENCH_OLED

**Files:**
- Create: `firmware/stage0-node/App/oled_dma.{c,h}`
- Modify: `firmware/stage0-node/Makefile` (`WS_BENCH_OLED ?= 0`; when 1: `-DWS_BENCH_OLED=1`, the display sources, `HAL_EXTRA += spi dma` as needed; a `field-check` target), `firmware/stage0-node/App/app_tx.lit.md` (init when built in; tangle)
- Test: `tests/test_oled_dma.py` (host build with a register shim, as `tests/test_board_inputs.py` does)

**Interfaces:**
- Produces: `void oled_dma_init(void);` (pins, SPI1 ≤ 1 MHz, a free DMA1 channel through DMAMUX with the SPI1_TX request, the reset pulse and Adafruit's SSD1325 set-up sequence as `i2cscan/App/oled.c`, all timed by UTIL timers, no waits), `int oled_dma_send(const uint8_t frame[4096]);` (0 started, -1 busy, -2 disabled), `int oled_dma_busy(void);`, `void oled_dma_enable(int on);` (off: display-off command, no traffic), `int oled_dma_faulted(void);`
- On a DMA or SPI error: stop, disable, print `#oled fault` once, never retry until `oled_dma_enable(1)`.

- [ ] **Step 1: Write the failing tests**:
```python
def test_send_while_busy_is_refused(self):           # second oled_dma_send before the TC interrupt returns -1
def test_dma_error_disables_display_once(self):      # inject TE: one "#oled fault" line, oled_dma_send returns -2 after
def test_init_uses_no_busy_wait(self):               # the reset and set-up steps run from timer callbacks; no HAL_Delay
def test_field_build_has_no_display_symbols(self):   # make ROLE=tx (WS_BENCH_OLED=0): nm shows no oled_ or scr_ symbol
```
- [ ] **Step 2: Run** `.venv/bin/python -m unittest tests.test_oled_dma -v` → FAIL.
- [ ] **Step 3: Implement** `oled_dma.c` and the Makefile flag; the send buffer is `static uint8_t txbuf[4096] __attribute__((section(".RAM2_region")));`.
- [ ] **Step 4: Run** the tests → PASS; `make -C firmware/stage0-node ROLE=tx WS_BENCH_OLED=1` and `make waits` (both settings) OK.
- [ ] **Step 5: Commit** `git commit -m "node: non-blocking SPI1 DMA driver for the bench OLED (WS_BENCH_OLED=1)"`

### Task 5: Screens: layout C and the interludes

**Files:**
- Create: `firmware/stage0-node/App/scr_view.{c,h}` (pure: draws one screen from a view struct and a frame number; host-tested)
- Test: `tests/test_scr_view.py`

**Interfaces:**
- Consumes: Task 1 drawing API; Task 3 types `wind_live_t`, `power_live_t`.
- Produces:
```c
enum scr_id { SCR_NORMAL, SCR_BURST, SCR_BANNER, SCR_SCOPE, SCR_VANE, SCR_SYSTEM, SCR_BOOT, SCR_HACK, SCR_COUNT };
typedef struct {
  int air_ok, box_ok, press_ok, uv_ok; int32_t air_c, air_rh, box_c, box_rh, press_dhpa, uv_counts;
  wind_live_t wind; uint32_t tips; power_live_t power;
  uint32_t last_seq, last_age_s; int last_acked; int16_t ack_rssi; int8_t ack_snr; unsigned pending, extra_frames;
  uint8_t cipher[96]; uint8_t cipher_len;                 /* the last frame's bytes, for the burst */
  uint8_t sf, bw_khz_div125; uint32_t freq_khz;          /* radio settings */
  uint8_t flash_pct, ram_pct, stack_pct, journal_pct, airtime_pct; uint16_t station; uint32_t epoch; unsigned modules, modules_active;
} scr_view_t;
void scr_draw(oled_fb *fb, enum scr_id id, unsigned frame, const scr_view_t *v);
unsigned scr_frames(enum scr_id id);   /* frames in one play: NORMAL 1, BANNER 24, BURST 16, HACK 24, others 64 */
```
- The rows of layout C exactly as the spec's table, `NO <part>` per absent part, the banner rows as the spec's mockup; interludes as `.superpowers/brainstorm/83868-1793832625/content/oled-interludes-v2.html` and `oled-hack-the-planet.html` (HACK THE PLANET: type-in by frame, wink at frame 16, glint at 18, glitch frames 20-23).

- [ ] **Step 1: Write the failing tests**:
```python
def test_normal_rows(self):            # a full view draws the spec's eight rows exactly (compare with oled_text per row at y = 8*i)
def test_absent_parts(self):           # all *_ok 0: rows read "AIR NO SHT45", "BOX NO SHTC3", "P NO BMP581 UV NO", "BATT NO INA228", "CELL NO MAX17048"
def test_every_string_in_font(self):   # draw every screen at every frame with extreme values; no '?' glyph pixels from a missing character
def test_burst_shows_cipher_hex(self):  # cipher bytes A4 C1 23 appear as text "A4 C1 23" on frame 8
def test_hack_sequence(self):          # frame 0 shows HACK only; frame 12 HACK THE PLANET; frame 16 wink (no left-eye disc); frame 21 a shifted row
def test_scope_plots_bins(self):       # bins rising 0..15: the trace's rightmost column is higher than its leftmost
```
- [ ] **Step 2: Run** `.venv/bin/python -m unittest tests.test_scr_view -v` → FAIL.
- [ ] **Step 3: Implement `scr_view.c`** (pure C, no HAL).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `git commit -m "node: bench screens, layout C and six interludes (pure, host-tested)"`

### Task 6: The screen scheduler and the exchange hooks

**Files:**
- Create: `firmware/stage0-node/App/scr_sched.{c,h}` (pure state machine), `firmware/stage0-node/App/oled_app.{c,h}` (glue: 125 ms UTIL timer, fills `scr_view_t` from Task 3 and node counters, draws into the RAM2 frame buffer, `ssd1325_frame`, `oled_dma_send`)
- Create: `firmware/stage0-node/App/oled_hooks.h` (`static inline` no-ops when `WS_BENCH_OLED` is 0)
- Modify: `firmware/stage0-node/App/tx_exchange.lit.md` and `app_tx.lit.md` (the `.c` files are tangled from these: edit the `.lit.md`, run `tools/tangle.py`, commit both) — in tx_exchange: call `oled_note_sent` after a successful `ws_radio_send` in `send_obs` and `send_diag`, `oled_note_ack` in `on_ack`, `oled_note_no_ack` in `no_reply`; in app_tx: start `oled_app` and play SCR_BOOT then SCR_HACK)
- Test: `tests/test_scr_sched.py`

**Interfaces:**
- Produces (oled_hooks.h): `void oled_note_sent(uint32_t seq, const uint8_t *frame, uint8_t len, int live);`, `void oled_note_ack(uint32_t seq, int16_t rssi, int8_t snr, unsigned pending);`, `void oled_note_no_ack(uint32_t seq);`
- Produces (scr_sched.h): `void sched_init(uint32_t now_ms);`, `void sched_event(enum sched_ev e, uint32_t now_ms);` with `enum sched_ev { EV_SENT_LIVE, EV_SENT_EXTRA, EV_ACK, EV_NO_ACK, EV_B1, EV_B2, EV_B3 };`, `void sched_step(uint32_t now_ms, enum scr_id *id, unsigned *frame, int *display_on);` called every 125 ms.
- Rules: one interlude from {SCOPE, VANE, SYSTEM, HACK} in turn every 120 s for 64 frames (8 s at 8 fps); EV_SENT_LIVE plays BURST (16 frames) then BANNER (24 frames, about 3 s); EV_SENT_EXTRA only increments the banner's count; a packet preempts an interlude at its next frame; NORMAL redraws once a second (every 8th step).

- [ ] **Step 1: Write the failing tests**:
```python
def test_interlude_every_two_minutes(self):    # 120 s of steps from boot (after BOOT+HACK): exactly one interlude of 64 frames
def test_packet_preempts_interlude(self):      # EV_SENT_LIVE at interlude frame 10: the next step is BURST frame 0
def test_packet_waits_for_frame_in_flight(self):  # oled_app with oled_dma_busy() true: the burst starts on the next tick, the busy frame is not resent
def test_drain_shows_one_burst(self):          # EV_SENT_LIVE then 5 × EV_SENT_EXTRA and an EV_ACK: one BURST, BANNER extra_frames == 5
def test_boot_then_hack(self):                 # from sched_init: BOOT frames, then HACK frames, then NORMAL
def test_field_build_hooks_are_noops(self):    # WS_BENCH_OLED=0: tx_exchange.o references no oled_note_ symbol
```
- [ ] **Step 2: Run** `.venv/bin/python -m unittest tests.test_scr_sched -v` → FAIL.
- [ ] **Step 3: Implement** `scr_sched.c`, `oled_app.c`, the hooks, and the `tx_exchange.c` and `app_tx.c` calls.
- [ ] **Step 4: Run** the tests, then `.venv/bin/python -m unittest discover -s tests` → PASS; `make -C firmware/stage0-node ROLE=tx WS_BENCH_OLED=1 waits` OK; the budget line printed.
- [ ] **Step 5: Commit** `git commit -m "node: screen scheduler, packet burst and banner from the exchange"`

### Task 7: Buttons

**Files:**
- Modify: `firmware/stage0-node/App/oled_app.c` (PA0 EXTI0, PA1 EXTI1 falling edges with pull-ups; PC6 already armed: its EXTI9_5 handler in `board_inputs.c` forwards line 6 to `oled_app_button(3)` when `WS_BENCH_OLED`), `firmware/stage0-node/App/board_inputs.c` (the forward, inside the existing `HAL_GPIO_EXTI_Callback`)
- Test: `tests/test_scr_sched.py`

**Interfaces:**
- Produces: `void oled_app_button(unsigned b);` (1..3, from interrupt: sets a flag; the 125 ms step debounces at 50 ms and posts EV_B1..EV_B3).
- B1: next of NORMAL, SCOPE, VANE, SYSTEM, HACK, then NORMAL; B2: pause or resume rotation (paused: no automatic interludes; packets still show); B3: `oled_dma_enable` toggled, steps stop drawing while off.

- [ ] **Step 1: Write the failing tests**:
```python
def test_button_bounce_and_wrap(self):   # three B1 edges within 50 ms -> one step; six presses from NORMAL -> NORMAL again
def test_pause_stops_rotation(self):     # B2, then 300 s: no interlude; EV_SENT_LIVE still plays BURST
def test_b3_turns_display_off(self):     # B3: display_on 0 and no draw; B3 again: 1
```
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; `make waits` OK.
- [ ] **Step 5: Commit** `git commit -m "node: B1 next screen, B2 pause rotation, B3 OLED on/off"`

### Task 8: Host end-to-end check

**Files:**
- Create: `tools/e2e_check.py`
- Test: `tests/test_e2e_check.py` (against a stub HTTP server in the test)

**Interfaces:**
- CLI: `python tools/e2e_check.py [--url http://127.0.0.1:8088] [--power-pending] [--max-age 180]`; token from `WS0_API_TOKEN` only; GET `/v1/observations/latest` with `Authorization: Bearer <token>`.
- Checks (field names as `ws0/fields.py`): present, valid, in range, and the observation younger than `--max-age` s: `temperature_c` −40..60, `humidity_pct` 0..100, `enclosure_temp_c`, `enclosure_rh_pct`, `pressure_hpa` 850..1090, `uva_raw` ≥ 0, `wind_speed_ms` 0..75, `wind_gust_ms` ≥ speed, `wind_dir_deg` 0..359 or calm, `rain_tips` ≥ 0, and each power field (`batt_mv`, `batt_current_ma`, `soc_gauge_pct` and the rest named in `ws0/fields.py`): valid without `--power-pending`, INVALID with it.
- Output: one line a field, `ok`/`FAIL`/`pending`, then a summary; exit 0 only if no FAIL.

- [ ] **Step 1: Write the failing tests**:
```python
def test_all_fields_ok(self):                 # a full plausible observation: exit 0, every line "ok"
def test_power_pending(self):                 # power fields INVALID with --power-pending: exit 0, lines "pending"
def test_power_invalid_without_flag_fails(self):
def test_stale_observation_fails(self):       # 10 min old with --max-age 180: exit 1, "stale"
def test_no_observation_and_bad_token(self):  # 404 / empty and 401: exit 1 with a one-line message, no traceback
def test_token_only_from_env(self):           # WS0_API_TOKEN unset: exit 2, "set WS0_API_TOKEN"; the tool opens no file
```
- [ ] **Step 2: Run** `.venv/bin/python -m unittest tests.test_e2e_check -v` → FAIL. **Step 3: Implement** (read `ws0/service.py:373-390` and `ws0/fields.py` for the response shape and names). **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `git commit -m "tools: e2e_check, every station field from the gateway API"`

### Task 9: Dev bring-up on the r1 bench (with Clint)

No code. Commands are run with Clint watching; provisioning and the token are his.

- [ ] Build: `make -C firmware/stage0-node ROLE=tx WS_POWER_PROFILE=2 WS_BENCH_OLED=1` and `ROLE=rx`; record the budget lines.
- [ ] Flash RX (`SERIAL=0016001E4142500E20353451`), ending the benchlink run, and TX (`SERIAL=003B00194142500E20353451`).
- [ ] Clint: `python -m ws0 init` a new hardware run directory, `provision-node` the TX, `serve` on the RX port, and `export WS0_API_TOKEN=…` in his shell.
- [ ] Watch: boot splash, HACK THE PLANET, then layout C; a burst and an ACK banner each minute; B1/B2/B3 work.
- [ ] `python tools/e2e_check.py --power-pending` → exit 0.
- [ ] Hand checklist on the website within two minutes each: spin the cups, turn the vane to two points, tip the bucket three times (+3), breathe on the SHT45, shade and light the LTR390.
- [ ] Note the results in `firmware/stage0-node/README.md` "Bench status" (dev build, not a release); the release with the power drill follows the power island.
