/* The bench screens as data: see scr_screens.h. anim and every only count for a base screen (SCR_F_BASE);
   the ones that only play have 1 and 8. */
#include "scr_screens.h"

#define GROW SCR_GROW_FRAMES   /* the bars and lines grow in */

const scr_def scr_defs[] = {
  [SCR_HOME]     = { SCR_NAME("HOME") scr_home, 1, 1, 2, SCR_F_BASE | SCR_F_ENDLESS },
  [SCR_BURST]    = { SCR_NAME("BURST") scr_burst, 16, 1, 8, 0 },
  [SCR_BANNER]   = { SCR_NAME("BANNER") scr_banner, 24, 1, 8, SCR_F_ENDLESS },
  [SCR_AIR]      = { SCR_NAME("AIR") scr_air, GROW, GROW, 8, SCR_F_BASE },
  [SCR_PRESSURE] = { SCR_NAME("PRESSURE") scr_pressure, GROW, GROW, 8, SCR_F_BASE },
  [SCR_POWER]    = { SCR_NAME("POWER") scr_power, GROW, GROW, 8, SCR_F_BASE },
  [SCR_RADIO]    = { SCR_NAME("RADIO") scr_radio, GROW, GROW, 8, SCR_F_BASE },
  [SCR_SCOPE]    = { SCR_NAME("SCOPE") scr_scope, 64, 1, 2, SCR_F_BASE },
  [SCR_VANE]     = { SCR_NAME("VANE") scr_vane, 64, 16, 8, SCR_F_BASE },   /* the needle swings round from N, a point a frame */
  [SCR_RAIN]     = { SCR_NAME("RAIN") scr_rain, 64, 1, 8, SCR_F_BASE },
  [SCR_SYSTEM]   = { SCR_NAME("SYSTEM") scr_system, 64, GROW, 8, SCR_F_BASE },
  [SCR_BOOT]     = { SCR_NAME("BOOT") scr_boot, 72, 1, 8, 0 },
  [SCR_HACK]     = { SCR_NAME("HACK") scr_hack, 24, 1, 8, 0 },
  [SCR_FORTUNE]  = { SCR_NAME("FORTUNE") scr_fortune, 64, 1, 8, 0 },
  [SCR_FROG]     = { SCR_NAME("FROG") scr_frog, 64, 1, 8, 0 },
  [SCR_MATRIX]   = { SCR_NAME("MATRIX") scr_matrix, 64, 1, 8, 0 },
  [SCR_PINBALL]  = { SCR_NAME("PINBALL") scr_pinball, 64, 1, 8, 0 },
  [SCR_MODULES]  = { SCR_NAME("MODULES") scr_modules, 16, 1, 8, SCR_F_ENDLESS },   /* its frame counts on through the wait */
};
_Static_assert(sizeof scr_defs / sizeof scr_defs[0] == SCR_COUNT, "a screen for every enum scr_id");

const scr_def *scr_def_of(enum scr_id id) { return &scr_defs[(unsigned)id < SCR_COUNT ? id : SCR_HOME]; }

unsigned scr_frames(enum scr_id id) { return scr_def_of(id)->frames; }
