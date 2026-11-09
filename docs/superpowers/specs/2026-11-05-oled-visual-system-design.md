# The bench OLED's visual system: layers, interfaces, migration

Date: 2026-11-05. Status: design for Clint's review. Nothing here is built yet.

Clint asked to "go back across all the visual elements and review them and abstract them and make them logical,
pragmatic, composable systems". This doc covers the drawing, formatting and animation code of the bench OLED
in `firmware/common/` (shared), `firmware/stage0-node/App/` (the TX bench build) and `firmware/i2cscan/App/` (the
bench tool), plus the host tools and tests that render it. It also takes in the open refactor findings 16 to 21
of the 2026-11-05 code review. The screens themselves do not change: every step below keeps every frame
byte-identical, and a golden test checks that (step 0).

Parent design: [`2026-11-04-node-oled-and-e2e-design.md`](2026-11-04-node-oled-and-e2e-design.md).

## 1. Inventory

### 1.1 The screens

`frames` is `scr_frames` (`scr_view.c:149`), `anim` is `sched_anim` (`scr_sched.c:53`) and `every` is
`sched_every` (`scr_sched.c:63`). Base screens dwell for 120 steps. The others play `frames` frames.

| Screen | Draw | frames / anim / every | Lists | What it draws with |
|---|---|---|---|---|
| HOME | `scr_home.c:233` | 1 (endless) / 1 / 2 | base, B1 | big digits right-aligned, 6 procedural icons (tick = frame/2), right-aligned rows, 2 fit-to-width rows, signal bars |
| BANNER | `scr_home.c:233` (`with_banner`) | 24 (endless) | packet | HOME, plus 2 rows inverted (`:230`) with fit forms |
| BURST | `scr_interludes.c:63` | 16 | packet | inverted header, scrolling chirp lines, hex rows, dashed rule |
| AIR | `scr_detail.c:84` | 8 / 8 / 8 | base, B1 | big digits, left+right row, sparkline with dotted frame, range text |
| PRESSURE | `scr_detail.c:134` | 8 / 8 / 8 | base, B1 | big digits and "hPa", trend arrow, sparkline, left/centre/right foot |
| POWER | `scr_detail.c:189` | 8 / 8 / 8 | base, B1 | header left+right, 5 label rows, each with a growing gauge |
| RADIO | `scr_detail.c:264` | 8 / 8 / 8 | base, B1 | header, two bar series (RSSI, SNR) with an x for a gap, 2 fit rows |
| SCOPE | `scr_interludes.c:106` | 64 / 1 / 2 | base, interlude, B1 | box, dot grid, line trace (truncating scale) |
| VANE | `scr_interludes.c:144` | 64 / 16 / 8 | base, interlude, B1 | art (rose), needle ray swinging, text column |
| RAIN | `scr_rain.c:127` | 64 / 1 / 8 | base, interlude, B1 | left+right rows with forms, a bar chart with a stepped scale, a dotted ceiling and an axis, left/centre/right foot |
| SYSTEM | `scr_interludes.c:158` | 64 / 8 / 8 | base, interlude, B1 | header, 5 boxed gauges growing in |
| BOOT | `scr_boot.c` | 72 (gray) | boot | scanline band, emblem lines and circle at ramped levels, wordmark font with a halo, letterspaced text, typed rows at 3 levels, glitch |
| MODULES | `scr_boot.c` | 16, held | boot | inverted header left+right, 2 columns of port rows with gray marks, dashed rule, centred foot |
| HACK | `scr_interludes.c:255` | 24 | interlude, B1 | art (face), eye disc, wink, glint, x2 text, squeezed x2 text, glitch |
| FORTUNE | `scr_silly.c:58` | 64 | interlude, B1 | box, typewriter rows, discs (cookie) |
| FROG | `scr_silly.c:149` | 64 | interlude, B1 | art (frog), pupils (discs), mouth polyline, drops, z text, streaks |
| MATRIX | `scr_silly.c:187` | 64 (gray) | interlude, B1 | kana glyphs at 16 levels, dim 5x7 footer, drawn straight into the send buffer |
| PINBALL | `scr_silly.c:256` | 64 | interlude, B1 | header left+right, box, circles, lit disc, inverted label, rays, flippers, envelope |
| bench tool | `i2cscan/App/bench_screen.c:54` | redrawn 1/s | n/a | 8 text rows, its own line builder |

### 1.2 Where the same thing is done more than once

**Text-row building.** There are two line builders. One is `scr_put` / `scr_put_dec` / `scr_put_uint` /
`scr_pad_to` (`scr_view.c:16-69`), with a fixed `SCR_LINE` capacity of 24 (`scr_view.h:205`). The other is
`append` / `append_fixed` / `append_uint` (`bench_screen.c:13-36`), which takes a size `n` and has `LINE_MAX 24`
(`:7`).
- `put_hex2` (`scr_interludes.c:44`) is the same function as `append_hex2` (`bench_screen.c:20`).
- `scr_put_dec` (`scr_view.c:24`) and `bench_fixed` (`i2cscan/App/bench_regs.c:27`) are the same formatter,
  with `drop + decimals` equal to `in_dec`. One difference: `bench_fixed` leaves the `+` off a zero.
- `put_lr` (`scr_rain.c:54`) is a verbatim copy of `scr_put_lr` (`scr_view.c:72`).
- Rows are drawn three ways. `scr_row` / `scr_row_right` / `scr_header` are at `scr_view.c:83-94`. The `row(r)`
  that does y = 8r is written twice, at `scr_rain.c:51` and `bench_screen.c:38`. Raw
  `oled_text(fb, 0, y, line, 1)` calls sit at `scr_interludes.c:60,87,116,127,134-141,172,175,192-195` and
  `scr_silly.c:70,137,169-175`.

**Fit to 21 columns.** Each of these sites has its own form loop: `scr_home.c:151-160` (wind/rain),
`:187-197` (link, 18 columns), `:211-219` (banner), `scr_detail.c:274-278` (ACK), `:285-291` (signal next to
NEXT, through `scr_put_lr`), `scr_rain.c:73-79` (a forms array) and `scr_rain.c:82-93` (rate: the forms worked
out from string lengths by hand). "Left+right, else left alone" appears at `scr_detail.c:104,112`. A centre
between a left and a right label is written twice: `scr_detail.c:156-158` (-3h .. now) and `scr_rain.c:115-125`
(-60m .. now). Both use the same `(21 - len) / 2`.

**Number formatting.** Rain mm is formatted three ways:
- `scr_put_rain_mm` (`scr_view.c:50`): 2 decimals, clamped;
- HOME's own copy (`scr_home.c:147-148`): 1 decimal, not clamped;
- `bench_screen.c:9,118`: a private 0.2794 mm constant instead of `WSMP_RAIN_NM_PER_TIP`.

Percentages: `scr_detail.c:244` and `oled_view.c:29`. "Sum of the last k samples" is `scr_rain_tips`
(`scr_calc.c:106`), the same loop again inside `scr_rain_rate_umh` (`scr_rain.c:31-33`), and the scope's
recent sum (`scr_interludes.c:109-111`).

**Charts and bars.**
- Line traces: the sparkline (`scr_detail.c:45-68`: slot x, rounded y through `scr_spark_y`, broken at a gap,
  grows in) and the scope trace (`scr_interludes.c:90-104`: x counted from the right, y truncated, no gaps).
- Bar series: rain (`scr_rain.c:96-112`: 2 px wide on a 2 px pitch, `scr_rain_bar_px`) and radio
  (`scr_detail.c:215-233`: 3 px wide on a 4 px pitch, `scr_bar_px`, grows in, an x for a gap). `scr_rain_bar_px`
  (`scr_rain.c:44`) gives the same results as `scr_bar_px` (`scr_calc.c:123`).
- Gauges: POWER (`scr_detail.c:162`: a dotted track, 2 rows filled), SYSTEM (`scr_interludes.c:166-176`: a box
  with a 3-row inset fill) and HOME's signal bars (`scr_home.c:176`).
- Scales: stepped doubling (`scr_rain_full`, `scr_rain.c:37`), the largest value with a floor of 4
  (`scr_interludes.c:92-94`), and a range fitted with a minimum span (`scr_spark_range`, `scr_calc.c:130`).
- Plot frames: hand-drawn four times (`scr_detail.c:48-51`, `scr_rain.c:102-105`, `scr_detail.c:218`,
  `scr_interludes.c:117-118`).
- `grown()` (`scr_detail.c:39`) is written again inline at `scr_interludes.c:165`. `upto()` (`scr_detail.c:41`)
  is written again at `scr_interludes.c:54,92,109`.

**Sprites, icons, animation.**
- Four walkers over bitmap rows, with three bit conventions: `oled_text` (`oled_fb.c:35`, u8, bit 4 leftmost),
  `scr_big_text` (`scr_view.c:114`, u16, bit 15 leftmost), `scr_blit` (`scr_view.c:132`, u64, bit 63 leftmost)
  and `ssd1325_blit4` (`oled_draw.c:114`, u8, bit w-1 leftmost).
- `squeezed_text` (`scr_interludes.c:212`) re-walks the 5x7 font (finding 17).
- Polar rays ("a line from r0 to r1 at compass point p") are written out four times: sun (`scr_home.c:39`),
  snow (`:84-87`), the vane needle (`scr_interludes.c:152`) and pinball (`scr_silly.c:282-284`).
- The glitch is written twice (`scr_interludes.c:202-206`, `:247-253`). Falling drops are written twice
  (`scr_home.c:72-76`, `scr_silly.c:129-133`). Scrolling dashed streaks are written twice (`scr_home.c:95-101`,
  `scr_silly.c:143`).
- Icons and the frog's weather are dispatched by `switch` (`scr_home.c:106`, `scr_silly.c:124`).

**Fonts and glyph lookup.** Four lookups behave three ways when the font lacks a character:
- `oled_fb.c:28` draws a `?`;
- `oled_draw.c:129` draws a `?`;
- `scr_view.c:96` draws nothing and does not advance;
- `scr_interludes.c:218` draws nothing but advances.

The 5x7 font, the big digits and the kana have three different header shapes (`font5x7.h`, `scr_font.h`,
`scr_kana.h`). Their three generators share the same `--check` main (`make_font.py`, `make_scr_font.py`,
`make_scr_kana.py`).

**Discs.** `face_eye` hand-rolls a disc with the test `i²+j² ≤ 16` (`scr_interludes.c:235-237`, finding 17).
`oled_disc` uses `≤ r²+r` (`oled_draw.c:81`), so the two disagree for r = 4. Pinball's `near`
(`scr_silly.c:237`) is a third circle test.

**1-bit and 4-bit surfaces.** Every screen draws into a 1 KB 1-bit buffer. The frame is then repacked into the
4 KB send buffer by `ssd1325_frame` (`oled_draw.c:95`), which makes 8192 `oled_get` calls across translation
units (finding 20). MATRIX alone draws straight into the send buffer through `ssd1325_put4` / `blit4` / `text4`
(`oled_draw.c:106-133`), and `rotate180` is passed on every call. That one special case costs the extra
`scr_draw_gray` path (`scr_view.c:162`), a branch in `oled_app.c:143-147`, and three render paths in
`tools/scr_render.py:219-240`.

**Refresh rates.** A screen's animation length is written in three places that nothing ties together:
- the draw code (`GROW_FRAMES 8`, `scr_detail.c:16`; `BAR_FILL_FRAMES 8`, `scr_interludes.c:39`; VANE's
  `point ≤ 15`);
- `sched_anim`'s `switch`;
- `scr_frames`'s `switch`.

`scr_draw`'s own `switch` (`scr_view.c:171`) and `scr_render.py:21`'s `SCREENS` list both mirror the enum by hand.

**History rings.** `scr_hist_push` (`scr_calc.c:25`, memmove) is called at `oled_view.c:94,99` and
`oled_app.c:47-48`. Each ring's count sits apart from its array (`scr_view.h:67-71`), so every reader clamps
with `upto`. The rain minutes (`mod_rain`, u8) and the wind bins (`mod_wind`, u8) are module-owned arrays with
different element types. No chart can take all of these sources without a copy or a cast.

**Driver and dead code (findings 16, 18, 19, 21).**
- 16: the SSD1325 set-up table, the window and `prescaler()` are duplicated (`i2cscan/App/oled.c:21,43,81`
  against `oled_dma.c:58,81,188`), and so is the pin and SPI1 setup (`oled.c:94-119` against
  `oled_dma.c:201-229`).
- 18: `ssd1325_column` (`oled_fb.c:52`) and `oled_rotate180` (`:59`) are used only by tests. `LIT_LEFT` and
  `LIT_RIGHT` are defined twice (`oled_fb.c:7`, `oled_draw.c:6`). `oled_circle` and `oled_disc` are now used by
  HOME, FORTUNE, FROG and PINBALL, so they stay.
- 19: `wish_on` and `inited` (`oled_dma.c:92-93,262,286`) are dead, because `oled_app_start` always calls
  `oled_dma_init` first.
- 21: already fixed in f3aaf85. `step()` now reads `sched_display_on()` and calls `oled_dma_enable` before
  `sched_step` (`oled_app.c:129-133`). Only the fault check comes after the scheduler step, which is intended:
  the scheduler keeps running while the display is faulted.

## 2. Architecture

Six layers. Each depends only on the ones below it. The lower three are in `firmware/common/`, pure C, and
shared with i2cscan. The upper three are in `App/`, also pure C (no HAL), except the pipeline glue in
`oled_app.c`.

```
 App/      screens-as-data   scr_screens.c       scr_defs[]: name, draw, frames, anim, every, flags
           screens           scr_home.c ...      draw(surf, frame, view): composition only
           widgets           scr_widget.{c,h}    labels, series, scales, bars, trace, gauge, ray, glitch, drops
 common/   text layout       oled_row.{c,h}      oled_row, put/dec/uint/hex2/pad/lr/lcr, oled_fit
           fonts and text    oled_font.{c,h}     oled_bits, oled_font, oled_draw_text, oled_text_w
           surface           oled_draw.{c,h}     oled_surf (4-bit, send order), oled_set/get/level + primitives
           panel             ssd1325.{c,h}       set-up and window tables, prescaler choice (pure data)
 board/    SPI1 + pins       nucleo-wl55jc/oled_spi1.{c,h}   (HAL; listed by both Makefiles, not Core/Src)
```

Every new symbol keeps the `oled_`, `scr_`, `ssd1325_` or `font5x7` prefix. That way the field build's linker
check (`stage0-node/Makefile:122`) still catches any display code that leaks into it.

### 2.1 Surface: one 4-bit target, not two

The recommendation is to drop the 1-bit frame buffer and draw every screen straight into the 4 KB send buffer, in
the SSD1325's order and turned as the panel needs. MATRIX already works this way, and so does
`oled_dma_buffer()`. The repack (finding 20), the gray special case, the 1 KB buffer and the
`rotate180` arguments all go. A pixel costs the same as today: one bounds check, one index and a nibble
read-modify-write instead of a bit read-modify-write. Clearing writes 4 KB instead of 1 KB.

The surface carries an **ink** level. `oled_set(s, x, y, 1)` writes `s->ink` (15 unless a screen chooses
otherwise), so every existing call site stays as it is. A gray screen copies the surface and changes the copy's
ink, so the caller's surface is never changed.

```c
/* firmware/common/oled_draw.h  (oled_fb.{c,h} are removed) */
#define OLED_W 128
#define OLED_H 64
#define OLED_COLPAIRS (OLED_W / 2)
#define OLED_FRAME_BYTES (OLED_COLPAIRS * OLED_H)   /* 4096: column pair, then row; left pixel high nibble */
#define OLED_FULL 15U

typedef struct {
  uint8_t *px;       /* OLED_FRAME_BYTES in the SSD1325's send order */
  uint8_t rot180;    /* panel upside down: logical (x, y) is stored at (127 - x, 63 - y) */
  uint8_t ink;       /* the level oled_set(.., 1) writes: 1..15 */
} oled_surf;

oled_surf oled_surf_on(uint8_t px[OLED_FRAME_BYTES], int rot180);   /* ink OLED_FULL; does not clear */
void oled_clear(const oled_surf *s);
void oled_level(const oled_surf *s, int x, int y, unsigned level);   /* 0..15, more is 15; off screen ignored */
unsigned oled_get(const oled_surf *s, int x, int y);                 /* the level; 0 off screen */
void oled_set(const oled_surf *s, int x, int y, int on);             /* on: s->ink, else 0 */

/* Primitives: unchanged semantics, surface in place of oled_fb. */
void oled_line(const oled_surf *s, int x0, int y0, int x1, int y1, unsigned dash);
void oled_box(const oled_surf *s, int x, int y, int w, int h);
void oled_fill(const oled_surf *s, int x, int y, int w, int h, int on);
void oled_dotgrid(const oled_surf *s, int x, int y, int w, int h, int step);
void oled_invert(const oled_surf *s, int x, int y, int w, int h);     /* lit -> 0, dark -> ink */
void oled_circle(const oled_surf *s, int cx, int cy, int r);
/* The disc of the points with i² + j² <= r2 (|i|, |j| <= r). oled_disc is r2 = r² + r. */
void oled_disc_r2(const oled_surf *s, int cx, int cy, int r, int r2, int on);
void oled_disc(const oled_surf *s, int cx, int cy, int r, int on);
void oled_shift_row(const oled_surf *s, int y, int dx);
```

`ssd1325_frame`, `ssd1325_put4`, `ssd1325_blit4`, `ssd1325_text4`, `ssd1325_column`, `oled_rotate180` and the
duplicate `LIT_*` constants all go. The surface already holds the frame in send order.

### 2.2 Bitmaps, fonts and one text renderer

There is one bit convention everywhere: **bit (w - 1) of a row is the leftmost column.** The 5x7 font, the
kana, the art and `blit4` already follow it. Only the big digits (bit 15 leftmost) need regenerating to fit.

```c
/* firmware/common/oled_font.h */
typedef struct {
  uint8_t w, h;
  uint8_t bits;        /* the row type: 8, 16 or 64 */
  const void *rows;    /* h rows of that type */
} oled_bits;

typedef struct {
  uint8_t h, w;              /* w: every glyph's width, unless widths */
  uint8_t bits, gap;         /* row type; pixels after each glyph */
  uint8_t n;
  const char *chars;         /* the glyphs' characters in order; NULL: by number only (the kana) */
  const uint8_t *widths;     /* NULL: all w */
  const void *rows;          /* n * h rows */
  char missing;              /* drawn for a character not in chars; '\0': nothing, no advance */
} oled_font;

typedef struct {
  uint8_t sx, sy;            /* a font pixel is sx x sy */
  uint8_t pitch;             /* 0: (glyph w + gap) * sx; else a fixed advance */
  const uint8_t *col_x;      /* NULL: column c at c * sx; else at col_x[c] (the squeezed PLANET) */
} oled_style;
extern const oled_style oled_x1, oled_x2;

void oled_blit(const oled_surf *s, int x, int y, const oled_bits *b);           /* the lit pixels, at ink */
int oled_glyph(const oled_font *f, char c);                                      /* -1: none and no missing */
void oled_draw_glyph(const oled_surf *s, int x, int y, const oled_font *f, unsigned g, const oled_style *st);
/* Returns the pen x after the last glyph and its gap. oled_text_w: from the first glyph's left to the
   last one's right edge (no trailing gap). */
int oled_draw_text(const oled_surf *s, int x, int y, const char *str, const oled_font *f, const oled_style *st);
int oled_text_w(const char *str, const oled_font *f, const oled_style *st);
int oled_text(const oled_surf *s, int x, int y, const char *str, int scale);   /* font5x7, as today */

/* font5x7.h (generated): extern const oled_font font5x7;    missing '?', gap 1
   App/scr_font.h (generated): extern const oled_font scr_big;  widths, bits 16, gap 2, missing '\0'
   App/scr_kana.h (generated): extern const oled_font scr_kana; chars NULL, n 55 */
```

What this replaces: `scr_big_text` and `scr_big_width` (`scr_view.c:96-130`), `squeezed_text`, `text4`,
`blit4`, and `scr_blit` (which becomes `oled_blit` with `scr_art { int8_t x, y; oled_bits bits; }`). For
`face_eye` the disc is `oled_disc_r2(s, .., 4, 16, 1)`. One width rule for every font: the 5x7 rows give
`128 - oled_text_w` = `OLED_W - 6n + 1` (`scr_view.c:87`), and the big digits give the same values as
`scr_big_width`. The one call that changes is PRESSURE's "hPa": the big text's pen now includes its
trailing gap, so `x + 3` becomes `x + 1`.

### 2.3 Text layout: one row builder, shared with i2cscan

```c
/* firmware/common/oled_row.h */
#define OLED_COLS 21                 /* 5x7 characters across at scale 1 */
#define OLED_ROW_CAP 24
typedef struct { char s[OLED_ROW_CAP]; } oled_row;   /* always terminated; appends stop at CAP - 1 */

void oled_put(oled_row *r, const char *s);
/* v with in_dec decimals (<= 6) shown with out_dec, rounded half away from zero. OLED_PLUS: '+' on v >= 0. */
#define OLED_PLUS 1U
void oled_put_dec(oled_row *r, int64_t v, unsigned in_dec, unsigned out_dec, unsigned flags);
void oled_put_uint(oled_row *r, uint32_t v);
void oled_put_hex2(oled_row *r, uint8_t b);
void oled_pad_to(oled_row *r, unsigned col);
/* r = left, then right ending at column cols; 0 and r untouched if they need more than cols with a space. */
int oled_put_lr(oled_row *r, const char *left, const char *right, unsigned cols);
/* left, right, and centre at (cols - len) / 2 when that leaves a space on each side; else left and right only. */
int oled_put_lcr(oled_row *r, const char *left, const char *centre, const char *right, unsigned cols);
/* Builds form 0, 1, ... n - 1 into r until one fits in cols; the last is kept as built. Returns the form. */
typedef void oled_form_fn(oled_row *r, const void *ctx, unsigned form);
unsigned oled_fit(oled_row *r, oled_form_fn *build, const void *ctx, unsigned n, unsigned cols);
```

The six form loops become `oled_fit`, the two left/centre/right feet become `oled_put_lcr`, and `bench_screen.c`'s
`append*` functions go. App-only formatters stay in App as `scr_put_age(oled_row *, s)` and
`scr_put_rain_mm(oled_row *, tips, decimals)`. That second one replaces HOME's private copy.
`bench_screen.c:118` uses `WSMP_RAIN_NM_PER_TIP` through it, or through `oled_put_dec` with
`wsmp_registry.h` (see Q3). The console's `bench_fixed` stays: it writes `printf` fields, not rows.

### 2.4 Widgets: draw into a place, from data

```c
/* App/scr_widget.h */
#define SCR_ROW_PX 8
#define SCR_GROW_FRAMES 8U             /* the single source: the table's anim reads it too */
enum scr_align { SCR_LEFT, SCR_RIGHT, SCR_CENTRE };
void scr_label(const oled_surf *s, int y, const char *text, enum scr_align a);   /* 5x7, x1 */
void scr_header(const oled_surf *s, const char *text);                           /* row 0, inverted */

/* A read-only series over any history: n samples, newest last, in cap slots (slot of i = cap - n + i). */
typedef struct { const void *v; uint8_t i16, n, cap; } scr_series;   /* i16: int16_t with SCR_GAP; else uint8_t */
scr_series scr_series_i16(const int16_t *v, unsigned n, unsigned cap);   /* clamps n to cap: no more upto() */
scr_series scr_series_u8(const uint8_t *v, unsigned n, unsigned cap);
int32_t scr_at(const scr_series *d, unsigned i);                         /* SCR_GAP for a gap */
int32_t scr_sum_last(const scr_series *d, unsigned k);                   /* rain tips, the rate, the scope */
int32_t scr_max(const scr_series *d);                                    /* 0 if none */

/* Scales (pure). scr_bar_px stays (scr_rain_bar_px goes). */
unsigned scr_scale_steps(unsigned largest, unsigned floor, unsigned cap);   /* floor doubled until it holds largest */
unsigned scr_spark_range(const scr_series *d, int32_t min_span, int32_t *lo, int32_t *hi);
static inline unsigned scr_grow(unsigned v, unsigned frame, unsigned frames)
{ return v * (frame + 1U < frames ? frame + 1U : frames) / frames; }

/* Plot frame: a top and bottom edge (none, solid, dotted) and solid sides if sides. */
enum { SCR_EDGE_NONE, SCR_EDGE_SOLID, SCR_EDGE_DOTTED };
void scr_frame(const oled_surf *s, int x0, int y0, int x1, int y1, unsigned top, unsigned bottom, int sides);

/* Bars standing on base_y, up to px tall: bar i at x + pitch * slot(i), height scr_bar_px(v - floor, span, px),
   grown by frame if grows. A gap: an x (gap_x) or nothing. */
typedef struct { uint8_t bar_w, pitch, gap_x, grows; } scr_bars_style;
void scr_bars(const oled_surf *s, int x, int base_y, unsigned px, const scr_series *d, int32_t floor,
              int32_t span, unsigned frame, const scr_bars_style *st);

/* The sparkline: slot x across w, y by scr_spark_y in [top, top + h), broken at a gap, the first
   scr_grow(cap, frame) slots drawn. */
void scr_trace(const oled_surf *s, int x, int top, int w, int h, const scr_series *d, int32_t lo, int32_t hi,
               unsigned frame);

/* A gauge of w x h at (x, y) filled fill_px: POWER {track dotted under, 2 rows}, SYSTEM {box, inset 2, 3 rows}. */
typedef struct { uint8_t w, h, inset, fill_h, boxed; } scr_gauge_style;
void scr_gauge(const oled_surf *s, int x, int y, unsigned fill_px, const scr_gauge_style *st);

/* Motion. */
void scr_ray(const oled_surf *s, int cx, int cy, int r0, int r1, int p, unsigned dash);   /* scr_sin20 compass */
void scr_glitch(const oled_surf *s, const int8_t *rows, unsigned n, int dy, int dx, int band_y, int band_h);
void scr_drops(const oled_surf *s, unsigned n, int x0, int dx, int y0, unsigned t, unsigned phase, unsigned span);
static inline int scr_tri(int p, int lo, int hi);   /* pinball's bounce(), a triangle wave */
```

The widgets do not include HOME's signal bars, the arrow, the cookie, the envelope or the flippers: each of those
is used once and stays a local function of its screen. Icons and the frog's weather become arrays of functions
indexed by the enum (`static void (*const icons[])(const oled_surf *, unsigned)`), so their `switch` statements go.

### 2.5 Screens as data

```c
/* App/scr_screens.h (scr_view.h keeps only the view and its constants; scr_calc.h the arithmetic) */
typedef void scr_draw_fn(const oled_surf *s, unsigned frame, const scr_view_t *v);
#define SCR_F_BASE    1U   /* dwells SCHED_DWELL_STEPS when picked (HOME and the detail screens) */
#define SCR_F_ENDLESS 2U   /* draws past its frames (HOME, BANNER: the icon); others clamp to the last */
typedef struct {
  const char *name;        /* "HOME": tools/scr_render.py reads these, its SCREENS list goes */
  scr_draw_fn *draw;
  uint8_t frames;          /* a play's length (scr_frames) */
  uint8_t anim, every;     /* a base screen: frames drawn one by one, then a redraw every `every` steps */
  uint8_t flags;
} scr_def;
extern const scr_def scr_defs[SCR_COUNT];   /* indexed by enum scr_id; a _Static_assert checks the count */

void scr_draw(const oled_surf *s, enum scr_id id, unsigned frame, const scr_view_t *v);   /* clear, clamp, draw */
```

`scr_frames`, `sched_anim` and `sched_every` become one-line table reads. They stay exported, so the tests do
not change. `scr_draw` becomes 4 lines, and `scr_draw_gray` goes.

The three orders (B1, details, interludes) **stay as arrays** in `scr_sched.c:10-15`. The order is part of the
design, a flag cannot carry it, and a flag next to an array would be two sources. `is_base` reads
`SCR_F_BASE` instead of searching the details array.

### 2.6 The view model

- `fill_build` (`oled_view.c:38`) reads link-time constants. It runs once, in `oled_app_start`, instead of at
  every drawn step.
- Everything else stays as it is: one fill per drawn step. A per-screen "needs" mask is a non-goal. Those
  sources are cached reads, and the cost finding 20 measured was the repack, which is gone.
- Histories keep their owners (`oled_view.c`, `oled_app.c`) and their memmove push. Each history's count moves
  next to its array as `SCR_HIST(cap)`, defined as `struct { uint8_t n; int16_t s[cap]; }`. The radio history
  is `struct { uint8_t n; int16_t rssi[30], snr[30]; }`. Readers make an `scr_series` from it, so the module
  arrays (`rain.per_min`, `wind.bins`) and the view's histories go through the same chart code.
  `scr_render.View` changes to match, and `test_check_view_layout` checks the size.

### 2.7 The display pipeline

```
sched_step -> oled_view_fill -> scr_draw(&surf on oled_dma_buffer(), rot180 1) -> oled_dma_send(buffer)
```

There is no repack step. `step()` (`oled_app.c:123`) keeps its current order of gates, which already answers
finding 21.

The panel driver data moves to `firmware/common/ssd1325.{c,h}`:

```c
extern const uint8_t ssd1325_setup[];  extern const uint8_t ssd1325_setup_len;   /* Adafruit begin() */
extern const uint8_t ssd1325_window[6];                                           /* 0x15 0 63 0x75 0 63 */
#define SSD1325_DISPLAY_OFF 0xAEU
#define SSD1325_DISPLAY_ON  0xAFU
#define SSD1325_SPI_MAX_HZ  1000000U
unsigned ssd1325_spi_div_log2(uint32_t pclk_hz);   /* the least k in 1..8 with pclk >> k <= 1 MHz: the fastest clock */
```

The HAL pin and SPI1 setup that both drivers share goes in `board/nucleo-wl55jc/oled_spi1.c`, as
`unsigned oled_spi1_init(void)` (it returns the SPI clock in Hz). It is kept out of `Core/Src`, whose wildcard
compiles every file into every project. i2cscan's polled `oled_show` and the node's DMA state machine stay
separate: they work differently on purpose. `wish_on` and `inited` are deleted (finding 19).

## 3. Before and after

**HOME** (today `scr_home.c:121-240`):

```c
/* before: 3 hand loops like this one, and a switch over the icons */
static void wind_rain_row(oled_fb *fb, const scr_view_t *v)
{ char line[SCR_LINE];
  for (unsigned form = 0; form < 3U; form++) { wind_rain_line(line, v, form); if (strlen(line) <= SCR_COLS) break; }
  scr_row(fb, WIND_Y, line); }

/* after */
static void sun(const oled_surf *s, unsigned t)
{
  oled_disc(s, ICON_CX, ICON_CY, 6, 1);
  for (int k = 0; k < 8; k++) scr_ray(s, ICON_CX, ICON_CY, 9, (k & 1) ? 13 : 15, 2 * k + (int)(t & 1U), 0);
}
static void (*const icons[])(const oled_surf *, unsigned) = { sun, moon, cloud_icon, rain, snow, wind };

static void readings(const oled_surf *s, const scr_view_t *v)
{
  oled_row t = { "" }, rh = { "" }, p = { "" };
  if (v->air_ok) { oled_put_dec(&t, v->air_c, 2, 1, 0); oled_put(&t, "^C"); } else oled_put(&t, "--^C");
  (void)oled_draw_text(s, OLED_W - oled_text_w(t.s, &scr_big, &oled_x1), TEMP_Y, t.s, &scr_big, &oled_x1);
  if (v->air_ok) { oled_put_dec(&rh, v->air_rh, 2, 0, 0); oled_put(&rh, "% RH"); } else oled_put(&rh, "NO SHT45");
  scr_label(s, RH_Y, rh.s, SCR_RIGHT);
  if (v->press_ok) { oled_put_dec(&p, v->press_dhpa, 1, 1, 0); oled_put(&p, " hPa"); } else oled_put(&p, "NO BMP581");
  scr_label(s, PRESS_Y, p.s, SCR_RIGHT);
}

void scr_home(const oled_surf *s, unsigned frame, const scr_view_t *v)
{
  oled_row r;
  icons[scr_icon_pick(v)](s, frame / 2U);
  readings(s, v);
  (void)oled_fit(&r, wind_rain_form, v, 3, OLED_COLS);  scr_label(s, WIND_Y, r.s, SCR_LEFT);
  (void)oled_fit(&r, link_form, v, 3, LINK_COLS);       scr_label(s, LINK_Y, r.s, SCR_LEFT);
  signal_bars(s, v);                                      /* HOME's own: used once */
}
void scr_banner(const oled_surf *s, unsigned frame, const scr_view_t *v);   /* icon, readings, the banner rows */
```

**RAIN** (today `scr_rain.c:51-138`: a private `row`, a private `put_lr`, a forms array, length arithmetic, the
chart drawn by hand):

```c
static const scr_bars_style minute_bars = { 2, 2, 0, 0 };

void scr_rain(const oled_surf *s, unsigned frame, const scr_view_t *v)
{
  const rain_hist_t *h = &v->rain;
  oled_row r, mm = { "" }, scale = { "" };
  scr_put_rain_mm(&mm, h->tips, 2); oled_put(&mm, " mm");
  (void)oled_put_lr(&r, "RAIN", mm.s, OLED_COLS);                 scr_label(s, 0, r.s, SCR_LEFT);
  (void)oled_fit(&r, count_form, h, 4, OLED_COLS);                scr_label(s, 8, r.s, SCR_LEFT);
  (void)oled_fit(&r, rate_form, h, 3, OLED_COLS);                 scr_label(s, 16, r.s, SCR_LEFT);
  scr_series d = scr_series_u8(h->per_min, RAIN_HIST_MINUTES, RAIN_HIST_MINUTES);
  unsigned full = scr_scale_steps((unsigned)scr_max(&d), RAIN_MIN_FULL, 256U);
  scr_frame(s, SIDE_L, CEIL_Y, SIDE_R, AXIS_Y, SCR_EDGE_DOTTED, SCR_EDGE_SOLID, 1);
  scr_bars(s, BARS_X, AXIS_Y, BAR_PX, &d, 0, (int32_t)full, frame, &minute_bars);
  oled_put_uint(&scale, full); oled_put(&scale, "/m");
  (void)oled_put_lcr(&r, "-60m", scale.s, "now", OLED_COLS);      scr_label(s, 56, r.s, SCR_LEFT);
}
```

`count_form` builds forms 0 to 2 with `oled_put_lr`, and form 3 is the count alone. That is today's "fits ? line :
left". `rate_form` builds "RATE  x (10m)", then "RATE x (10m)", then "RATE  x". The lengths match
`scr_rain.c:87-89`.

**MATRIX** (today `scr_silly.c:187-217`: its own send-buffer path, `rotate180` passed on every call,
`blit4`/`text4`):

```c
void scr_matrix(const oled_surf *s, unsigned frame, const scr_view_t *v)
{
  oled_surf g = *s;                                    /* the same frame, its own ink */
  unsigned tips = (unsigned)scr_sum_last(&(scr_series){ v->rain.per_min, 0, 60, 60 }, SCR_RAIN_RECENT_MIN);
  unsigned speed = scr_matrix_speed(tips);
  for (unsigned c = 0; c < SCR_MATRIX_COLS; c++)
    for (unsigned r = 0; r < SCR_MATRIX_ROWS; r++)
    {
      int head;
      g.ink = (uint8_t)scr_matrix_cell(c, r, frame, speed, &head);   /* scr_matrix_level, with the head flag */
      if (g.ink) oled_draw_glyph(&g, (int)c * 6 + 1, (int)r * 8, &scr_kana, scr_matrix_glyph(c, r, frame, head), &oled_x1);
    }
  oled_row line = { "TIPS " };
  oled_put_uint(&line, tips); oled_put(&line, "/10m"); oled_pad_to(&line, 13); oled_put(&line, "SPEED x");
  oled_put_uint(&line, speed);
  g.ink = MATRIX_FOOTER;
  scr_label(&g, OLED_H - font5x7.h, line.s, SCR_LEFT);
}
```

MATRIX becomes an ordinary table entry. `scr_draw_gray`, the branch in `oled_app.c:143`, and `gray()`/`shade()`
in `scr_render.py` all go.

## 4. Migration plan

**The check for every step:** `tools/scr_render.py --digest` renders every screen, at every frame
(0..frames-1, and 0..63 for HOME and BANNER), for the demo view and every state in `views()`. It hashes the
4096-byte frame exactly as sent (rotated). The result goes to `tests/golden/scr_frames.json`, a few
thousand entries (well under a second), and `tests/test_scr_golden.py` compares against it. `tests/test_i2cscan.py` gets the same check for 4
`bench_view` states.

The field image is checked too. `make field-check FW_VERSION=000000000000` before and after each step must
give the same `.bin` SHA-256 (setting FW_VERSION on the command line pins the embedded version, and it passes
down to sub-makes).

The figures are estimates, measured at each step from the budget line and `#timing`'s `step` task. The bench
build is at 115,992 of 194,560 B now, and its display code is 25.4 KB of text (from `arm-none-eabi-size` of
`build/tx-oled`).

| # | Step | Pixels | Flash / RAM / CPU (bench) | Tests |
|---|---|---|---|---|
| 0 | Golden harness: `scr_render.py --digest/--update`, a `frame()` helper (scr_draw + ssd1325_frame or the gray path, rot 1), `test_scr_golden.py`, i2cscan digests. Baseline taken from master. | baseline | none | new |
| 1 | Dead and duplicate code: `ssd1325_column`, `oled_rotate180`, one `LIT_*`, `wish_on`/`inited`; `scr_rain.c`'s `put_lr` → `scr_put_lr`; `scr_rain_bar_px` → `scr_bar_px`; one `grown`/`upto` | identical | −0.15 KB | `test_oled_fb`: drop the column/rotate180 tests (frame order already covered by `test_ssd1325_frame_*`); `test_oled_dma`: drop `test_enable_before_init_waits_for_init`; `test_scr_view.test_rain_bar_scale` calls `scr_bar_px` |
| 2 | `common/ssd1325.{c,h}` and `board/.../oled_spi1.{c,h}`, used by both drivers (finding 16) | identical (node); i2cscan image changes, its frames do not | node ±0 | `test_oled_dma.setup_bytes()` reads `ssd1325.c` (or a literal Adafruit list in the test) |
| 3a | `oled_surf` and the primitives on the 4-bit surface, next to `oled_fb`; screens take `const oled_surf *` (mechanical: `oled_fb *fb` → `const oled_surf *s`) | identical | ±0 | `scr_render.py` draws through the surface; `test_scr_view`'s `oled_get` reads the surface |
| 3b | `oled_app` and i2cscan draw into the send buffer; MATRIX on `ink`; `oled_fb.{c,h}`, `ssd1325_frame`, `*4` functions and `scr_draw_gray` go (finding 20) | identical | −0.3 KB, RAM2 −1 KB (i2cscan RAM −1 KB), CPU about −3 ms a frame (8192 calls at ~18 cycles at 48 MHz; ~2.5 % of the main loop at 8 fps) | `test_oled_fb.py` → `test_oled_draw.py` (surface tests; the put4 nibble tests become `oled_level` tests); `scr_render` collapses `gray/draw/shade` into one |
| 4 | Fonts: `oled_bits`, `oled_font`, one renderer; generators emit descriptors; `make_scr_font.py` writes bit w-1 leftmost; `squeezed_text`, `scr_big_*`, `scr_blit`, `face_eye` disc (`oled_disc_r2`, finding 17) | identical | −0.3 KB | `*_file_is_current` regenerated; `test_big_digits` calls `oled_draw_text(scr_big)`; the shim wraps `oled_draw_text` (font coverage for every font with `chars`) |
| 5 | `common/oled_row`; `scr_put*` → `oled_put*`; `oled_fit` at the 6 sites; `oled_put_lcr` at 2; `bench_screen.c` onto it; `scr_put_rain_mm(.., decimals)` for HOME | identical (node); i2cscan per Q3 | −0.4 KB | `test_scr_view.test_rows_that_would_overflow_*` unchanged (it is the spec); `test_i2cscan.BenchScreen` sources |
| 6 | `scr_widget`: labels, series, scales, frame, bars, trace (the sparkline), gauge, ray, glitch, drops; `SCR_HIST`; icon/weather tables | identical | −0.5 KB | `test_scr_view`: `scr_rain_full` → `scr_scale_steps`; `test_scr_calc`: `scr_spark_range` takes a series; new widget unit tests (small, pure) |
| 6b | Only if Q1 is yes: SCOPE on `scr_trace` | **re-baselined** (SCOPE only; ≤1 px) | −0.1 KB | `test_scope_plots_bins` updated; before and after PNGs for Clint |
| 7 | `scr_defs[]`; `scr_frames`/`sched_anim`/`sched_every`/`scr_draw` read it; `scr_render` reads names; headers split (`scr_view.h` → view, `scr_calc.h`, `scr_widget.h`, `scr_screens.h`); `fill_build` once | identical | ±0.1 KB | `test_frames` unchanged; `test_scr_sched` unchanged |
| 8 | (Optional) the three glyph generators share `firmware/common/tools/glyphgen.py` (art parsing, C emission, `--check`) | identical | none | the `--check` tests unchanged |

**Overall:** flash about −1.5 KB, ±1 KB (the copies listed in 1.2, four glyph walkers, three `switch`
statements, the repack). Against that, about 0.4 KB is added: the table, the style constants and the font
descriptors. RAM2 drops by 1 KB, and RAM1 does not change. The main loop saves about 3 ms per drawn frame.

The field build does not change, and the pinned-version `.bin` hash proves it. Steps 2, 3b and 7 move
interfaces, so a bench look after them is worth having: see Q4. Each step is one commit, small enough to revert
alone.

## 5. Open questions (recommended answer first)

1. **SCOPE's trace.** Should SCOPE move onto the sparkline's mapping (rounded y, slot x from the left)?
   Today it truncates y and counts x from the right, which shifts some points by up to 1 px.
   *Recommend yes,* as step 6b on its own with before and after PNGs, so that one trace widget serves both
   screens. No means SCOPE keeps its own 15-line trace, and every other step stays identical.
2. **One 4-bit surface,** with the 1-bit buffer removed. The alternative is a tagged surface over both.
   *Recommend the single 4-bit surface:* one backend, no repack, gray anywhere for free, and 1 KB less RAM. The
   two-backend option keeps the 1 KB buffer and still needs a fast packer.
3. **The bench tool's `+0.00mA`.** Should i2cscan's BATT row show a zero current as `+0.00mA`, the node's rule,
   instead of `0.00mA`? *Recommend yes* (greenfield, a bench tool): one formatter, no flag. No means
   `OLED_PLUS_NONZERO` in `oled_put_dec`'s flags.
4. **A bench look.** Should the panel be flashed and checked after steps 3b and 7, or only at the end?
   *Recommend after 3b and at the end.* The golden test proves the bytes, and the bench proves that the DMA
   still sends a buffer drawn in place for every screen. The boards are at home, and auto mode blocks flashing,
   so Clint runs it.
5. **Keep the golden test after the migration?** *Recommend yes,* with `scr_render.py --update` to accept a
   deliberate change. It costs one command for each visual change, and it catches any accidental drift from
   then on.

## 6. Non-goals

- No change to what any screen shows: no new screens, layouts or gray use on other screens (step 6b only if Q1 is
  yes).
- No layout engine, flex or grid, and no widget objects or vtables. Widgets are plain functions over a place and
  data.
- No dirty rectangles, partial updates or double buffering. The frame is always drawn whole into the one send
  buffer.
- No per-screen "needs" mask for the view fill (only the build constants move, filled once).
- No head-index ring buffer and no generic ring type beyond `SCR_HIST`. A memmove over 60 samples once a minute
  is fine.
- Single-use art stays local to its screen: signal bars, the arrow, the cookie, the envelope, the flippers, the
  frog's mouth.
- The scheduler's state machine does not change, beyond reading the table.
- `bench_fixed` and the console's formatting stay as they are.
- No support for other panels (SSD1306 and the like), no font compression and no Python codegen of screens.
- No change to the order lists (B1, details, interludes) as data: they stay arrays.
