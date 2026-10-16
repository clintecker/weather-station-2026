#ifndef NODE_FIELDS_H
#define NODE_FIELDS_H
#include "ws_obs.h"
/* The catalog fields this build measures (docs/protocol-design.md 5.5). Every record of
 * the build carries exactly these, so the observation and journal slot sizes follow from them at
 * compile time. The journal page magic encodes the slot size, so a build with another field set
 * ignores and recycles pages written with the old layout. */
#ifndef WS_NODE_FIELDS
#define WS_NODE_FIELDS (WS_F_TEMPERATURE_C | WS_F_HUMIDITY_PCT | WS_F_TH_SUMMARY)  /* temperature and humidity: 15-s samples, minute mean + extrema */
#endif
#define WS_OBS_PLAIN_MAX WS_OBS_PLAIN_LEN(WS_NODE_FIELDS)
_Static_assert((WS_NODE_FIELDS) != 0 && !(WS_NODE_FIELDS & ~WS_FIELDS_DEFINED), "a build measures catalog fields");
#endif
