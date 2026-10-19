#ifndef WSMP_CATALOG_MAP_H
#define WSMP_CATALOG_MAP_H
/* The interim map from WSMP snapshots to today's observation catalog (protocol version 5,
 * docs/protocol-design.md section 5), until WSMP reaches the radio (sub-project 7, which removes this
 * file). The table is section 5 of docs/superpowers/specs/2026-10-18-wsmp-bench-station-design.md. */
#include <stdint.h>
#include "ws_obs.h"

/* What the minute's #sample line reports about the outside air. */
typedef struct { int th_valid; int16_t t; uint16_t h; unsigned th_samples; } wsmp_map_summary;

/* Fills o->bitmap and o->code[] from the snapshots of every port in the layout (wsmp_host.h):
   the fields of the modules in the layout, INVALID where a channel is missing. */
void wsmp_map_obs(ws_obs_t *o, wsmp_map_summary *sum);
#endif
