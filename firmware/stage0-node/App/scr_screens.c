/* The bench screens as data: see scr_screens.h. anim and every only count for a base screen (SCR_F_BASE);
   the ones that only play have 1 and 8. */
#include "scr_screens.h"

#define GROW SCR_GROW_FRAMES   /* the bars and lines grow in */

const scr_def scr_defs[] = {
  [SCR_HOME]     = { "HOME", scr_home, 1, 1, 2, SCR_F_BASE | SCR_F_ENDLESS },
  [SCR_BURST]    = { "BURST", scr_burst, 16, 1, 8, 0 },
  [SCR_BANNER]   = { "BANNER", scr_banner, 24, 1, 8, SCR_F_ENDLESS },
  [SCR_AIR]      = { "AIR", scr_air, GROW, GROW, 8, SCR_F_BASE },
  [SCR_PRESSURE] = { "PRESSURE", scr_pressure, GROW, GROW, 8, SCR_F_BASE },
  [SCR_POWER]    = { "POWER", scr_power, GROW, GROW, 8, SCR_F_BASE },
  [SCR_RADIO]    = { "RADIO", scr_radio, GROW, GROW, 8, SCR_F_BASE },
  [SCR_SCOPE]    = { "SCOPE", scr_scope, 64, 1, 2, SCR_F_BASE },
  [SCR_VANE]     = { "VANE", scr_vane, 64, 16, 8, SCR_F_BASE },   /* the needle swings round from N, a point a frame */
  [SCR_RAIN]     = { "RAIN", scr_rain, 64, 1, 8, SCR_F_BASE },
  [SCR_SYSTEM]   = { "SYSTEM", scr_system, 64, GROW, 8, SCR_F_BASE },
  [SCR_BOOT]     = { "BOOT", scr_boot, 64, 1, 8, 0 },
  [SCR_HACK]     = { "HACK", scr_hack, 24, 1, 8, 0 },
  [SCR_FORTUNE]  = { "FORTUNE", scr_fortune, 64, 1, 8, 0 },
  [SCR_FROG]     = { "FROG", scr_frog, 64, 1, 8, 0 },
  [SCR_MATRIX]   = { "MATRIX", scr_matrix, 64, 1, 8, 0 },
  [SCR_PINBALL]  = { "PINBALL", scr_pinball, 64, 1, 8, 0 },
};
_Static_assert(sizeof scr_defs / sizeof scr_defs[0] == SCR_COUNT, "a screen for every enum scr_id");

unsigned scr_frames(enum scr_id id) { return (unsigned)id < SCR_COUNT ? scr_defs[id].frames : 1U; }
