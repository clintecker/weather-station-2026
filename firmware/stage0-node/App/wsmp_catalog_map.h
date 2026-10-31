#ifndef WSMP_CATALOG_MAP_H
#define WSMP_CATALOG_MAP_H
/* The interim map from WSMP snapshots to the observation catalog (protocol version 6, catalog v2:
 * docs/protocol-design.md section 5 and docs/superpowers/specs/2026-10-29-power-telemetry-design.md
 * sections 5 and 9.7), until WSMP reaches the radio (sub-project 7, which removes this file). The
 * weather table is section 5 of docs/superpowers/specs/2026-10-18-wsmp-bench-station-design.md; the
 * power fields follow the power design's per-phase fill table (section 3.2). */
#include <stdint.h>
#include "ws_obs.h"

/* What the minute's #sample line reports about the outside air. */
typedef struct { int th_valid, h_valid; int16_t t; uint16_t h; unsigned th_samples; } wsmp_map_summary;   /* h_valid: RH not missing */

/* Fills o->bitmap and o->code[] from the snapshots of every port in the layout (wsmp_host.h): the
   fields of the modules in the layout, INVALID where a channel is missing, faulted or (for a mean) over
   a long window, and no field where the build has no source (a "not fitted" slot). The battery and
   rails modules are always in the layout, so a dead power part gives INVALID fields, never absent
   ones; the charger input voltage never stands in for solar or USB-C. */
void wsmp_map_obs(ws_obs_t *o, wsmp_map_summary *sum);
#endif
