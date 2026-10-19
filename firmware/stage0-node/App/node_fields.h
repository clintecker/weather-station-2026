#ifndef NODE_FIELDS_H
#define NODE_FIELDS_H
#include "ws_obs.h"
/* The catalog fields this build can measure (docs/protocol-design.md 5.5). A record carries the
 * fields of its minute's modules (its own bitmap); the journal slot size follows from the widest at
 * compile time. The journal page magic encodes the slot size, so a build with another field set
 * ignores and recycles pages written with the old layout. */
/* The WSMP bench station (App/wsmp_catalog_map.c): every field the local modules can fill. A reading
   carries the subset of the modules in the layout; the journal slot fits the widest. */
#define WS_F_WSMP_BENCH (WS_F_TEMPERATURE_C | WS_F_HUMIDITY_PCT | WS_F(WS_FI_TH_SAMPLES) | WS_F(WS_FI_PRESSURE_HPA) | \
                         WS_F(WS_FI_WIND_SPEED_MS) | WS_F(WS_FI_WIND_GUST_MS) | WS_F(WS_FI_WIND_DIR_DEG) | \
                         WS_F(WS_FI_RAIN_TIPS) | WS_F(WS_FI_UVA_RAW) | WS_F(WS_FI_BATT_MV) | WS_F(WS_FI_ENERGY_IN_MWH) | \
                         WS_F(WS_FI_ENERGY_OUT_MWH) | WS_F(WS_FI_CHARGE_IN_MAH) | WS_F(WS_FI_CHARGE_OUT_MAH) | \
                         WS_F(WS_FI_SOC_GAUGE_PCT) | WS_F(WS_FI_CHARGER_PINS) | WS_F(WS_FI_ENCLOSURE_TEMP_C) | \
                         WS_F(WS_FI_ENCLOSURE_RH_PCT))
#ifndef WS_NODE_FIELDS
#define WS_NODE_FIELDS WS_F_WSMP_BENCH
#endif
#define WS_OBS_PLAIN_MAX WS_OBS_PLAIN_LEN(WS_NODE_FIELDS)
_Static_assert((WS_NODE_FIELDS) != 0 && !(WS_NODE_FIELDS & ~WS_FIELDS_DEFINED), "a build measures catalog fields");
#endif
