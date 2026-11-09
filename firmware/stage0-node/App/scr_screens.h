/* The bench OLED's screens (docs/superpowers/specs/2026-11-04-node-oled-and-e2e-design.md, "The screens"):
 * HOME and its packet banner, the detail screens, the interludes, each drawn from a view of what the TX
 * knows and a frame number. Pure C, no HAL: the host tests check it (tests/test_scr_view.py, test_scr_calc.py)
 * and tools/scr_render.py renders every screen to PNG.
 *   App/scr_screens.c     the screens as data: scr_defs[], their names, frames and redraws
 *   App/scr_view.c        scr_draw, the text helpers (scr_view.h)
 *   App/scr_widget.c      labels, series, scales, frames, bars, the trace, rays, the glitch, drops
 *   App/scr_calc.c        the arithmetic and the choices: histories, dew point, tendency, icon, scales, fortune
 *   App/scr_home.c        HOME, its condition icons and the banner
 *   App/scr_detail.c      AIR, PRESSURE, POWER, RADIO and their sparklines and bars
 *   App/scr_interludes.c  the packet burst, SCOPE, VANE, SYSTEM, HACK THE PLANET
 *   App/scr_boot.c        the LGTM SYSTEMS boot splash and the module checklist (its wordmark: scr_mark.h)
 *   App/scr_rain.c        RAIN
 *   App/scr_silly.c       the fortune cookie, the frog, the digital rain, the packet pinball
 * Only in WS_BENCH_OLED=1 builds. */
#ifndef SCR_SCREENS_H
#define SCR_SCREENS_H

#include <stdint.h>
#include "oled_draw.h"
#include "oled_font.h"
#include "oled_row.h"
#include "scr_art.h"
#include "scr_calc.h"
#include "scr_view.h"
#include "scr_widget.h"

enum scr_id { SCR_HOME, SCR_BURST, SCR_BANNER, SCR_AIR, SCR_PRESSURE, SCR_POWER, SCR_RADIO, SCR_SCOPE, SCR_VANE,
              SCR_RAIN, SCR_SYSTEM, SCR_BOOT, SCR_HACK, SCR_FORTUNE, SCR_FROG, SCR_MATRIX, SCR_PINBALL,
              SCR_MODULES, SCR_COUNT };

/* The screens as data, indexed by enum scr_id. frames: a play's length (scr_frames: BURST 16, BANNER 24, HACK 24, BOOT 72,
   HOME 1, AIR, PRESSURE, POWER and RADIO 8 as their bars and lines grow in, MODULES 16: the boot checklist
   holds until the modules settle, then shows its outcome for these frames; the others 64). A base screen (the
   scheduler, App/scr_sched.h) is drawn at each of its first anim steps, then every `every` steps. */
typedef void scr_draw_fn(const oled_surf *s, unsigned frame, const scr_view_t *v);
#define SCR_F_BASE    1U   /* dwells SCHED_DWELL_STEPS when picked (HOME and the detail screens) */
#define SCR_F_ENDLESS 2U   /* draws past its frames (HOME, BANNER: the icon); the others clamp to the last */
/* The screens' names ("HOME") are for tools/scr_render.py, which builds with SCR_NAMES: the image keeps none. */
#ifdef SCR_NAMES
#define SCR_NAME(x) x,
#else
#define SCR_NAME(x)
#endif
typedef struct {
#ifdef SCR_NAMES
  const char *name;
#endif
  scr_draw_fn *draw;
  uint8_t frames, anim, every, flags;
} scr_def;
extern const scr_def scr_defs[SCR_COUNT];
const scr_def *scr_def_of(enum scr_id id);   /* id's entry, HOME's for an id out of range */
unsigned scr_frames(enum scr_id id);
/* Clears the surface s and draws frame `frame` of screen id (frame counts from 0); a screen not SCR_F_ENDLESS
   draws a frame past its last as the last. In scr_view.c, apart from the table, so that the scheduler's host
   test links the table without the screens. */
void scr_draw(const oled_surf *s, enum scr_id id, unsigned frame, const scr_view_t *v);

/* The screens, for scr_defs. Each draws on a cleared surface. */
scr_draw_fn scr_home, scr_banner;                         /* scr_home.c: HOME, and HOME with the packet banner */
scr_draw_fn scr_air, scr_pressure, scr_power, scr_radio;  /* scr_detail.c */
scr_draw_fn scr_burst, scr_scope, scr_vane, scr_system, scr_hack;   /* scr_interludes.c */
scr_draw_fn scr_boot, scr_modules;                        /* scr_boot.c */
scr_draw_fn scr_rain;                                     /* scr_rain.c */
scr_draw_fn scr_fortune, scr_frog, scr_pinball;           /* scr_silly.c */
/* The digital rain, in gray: each glyph at its own level, on a copy of s with its own ink. scr_matrix_glyph: the
   glyph (scr_kana.h) at (c, r), each changing now and then on its own, the head's every frame. */
scr_draw_fn scr_matrix;
unsigned scr_matrix_glyph(unsigned c, unsigned r, unsigned frame, int head);

#endif
