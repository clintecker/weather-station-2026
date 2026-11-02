#ifndef NODE_FIELDS_H
#define NODE_FIELDS_H
#include "ws_obs.h"
/* The catalog fields this build can measure (docs/protocol-design.md 5.5). A record carries the
 * fields of its minute's modules (its own bitmap); the journal slot size follows from the widest at
 * compile time. The journal page magic encodes the slot size, so a build with another field set
 * ignores and recycles pages written with the old layout. */
/* The WSMP bench station (App/wsmp_catalog_map.c): every field the local modules can fill. A reading
   carries the subset of the modules in the layout (and of the power slots its build fits); the journal
   slot fits the widest. One field set for power phases A to C
   (docs/superpowers/specs/2026-10-29-power-telemetry-design.md sections 3.2 and 5.4): it holds every
   power field of every phase, so a phase change moves neither the journal slot nor the page magic.
   77 bytes of plaintext: the v5 bench set (61 B) without the retired fields 17 and 18, plus the
   battery current (12), the rails 26-30, 32 and 33, and the 2-byte extension word. */
#define WS_F_WSMP_POWER (WS_F(WS_FI_BATT_MV) | WS_F(WS_FI_BATT_CURRENT_MA) | WS_F(WS_FI_ENERGY_IN_MWH) | \
                         WS_F(WS_FI_ENERGY_OUT_MWH) | WS_F(WS_FI_CHARGE_IN_MAH) | WS_F(WS_FI_CHARGE_OUT_MAH) | \
                         WS_F(WS_FI_LOAD_MV) | WS_F(WS_FI_LOAD_CURRENT_MA) | WS_F(WS_FI_CHARGER_INPUT_MV) | \
                         WS_F(WS_FI_SOLAR_MV) | WS_F(WS_FI_SOLAR_CURRENT_MA) | WS_F(WS_FI_USB_MV) | \
                         WS_F(WS_FI_USB_CURRENT_MA))
#define WS_F_WSMP_BENCH (WS_F_TEMPERATURE_C | WS_F_HUMIDITY_PCT | WS_F(WS_FI_TH_SAMPLES) | WS_F(WS_FI_PRESSURE_HPA) | \
                         WS_F(WS_FI_WIND_SPEED_MS) | WS_F(WS_FI_WIND_GUST_MS) | WS_F(WS_FI_WIND_DIR_DEG) | \
                         WS_F(WS_FI_RAIN_TIPS) | WS_F(WS_FI_UVA_RAW) | WS_F(WS_FI_ENCLOSURE_TEMP_C) | \
                         WS_F(WS_FI_ENCLOSURE_RH_PCT) | WS_F_WSMP_POWER)
#ifndef WS_NODE_FIELDS
#define WS_NODE_FIELDS WS_F_WSMP_BENCH
#endif
#define WS_OBS_PLAIN_MAX WS_OBS_PLAIN_LEN(WS_NODE_FIELDS)
_Static_assert((WS_NODE_FIELDS) != 0 && !(WS_NODE_FIELDS & ~WS_FIELDS_DEFINED), "a build measures catalog fields");
_Static_assert(WS_OBS_PLAIN_LEN(WS_F_WSMP_BENCH) == 77U, "the version-6 field set is 77 bytes (power design section 5.4)");
#endif
