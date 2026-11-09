/* The bench screens' view of the node (WS_BENCH_OLED=1 only): the modules' live values, the radio
 * settings, the identity, and the flash, RAM, stack and journal use, read just before a frame is drawn.
 * Every source is read-only and cached (no bus or flash access), except the stack scan, which runs only
 * when the system bars start (about 1.5 ms). App/oled_app.c fills the exchange's fields itself. */
#ifndef OLED_VIEW_H
#define OLED_VIEW_H
#include <stdint.h>
#include "scr_screens.h"

/* The build's constants: flash and RAM use, the radio settings. Once, at start (oled_app_start). */
void oled_view_build(scr_view_t *v);
/* Everything but the build's constants, last_*, ack_*, extra_frames, reports, cipher*, airtime_pct,
   since_exchange_s, radio and the histories (oled_app.c's and oled_view_sample's). A temperature, humidity, pressure or UV row shows a value only while its port is in the layout (the
   snapshot the observation reads, wsmp_host_snapshot): otherwise the reading carries no value for it,
   and the row says NO <part>. */
void oled_view_fill(scr_view_t *v, enum scr_id id, unsigned frame);
/* The display's own histories, at every step whether drawn or not (cheap: two comparisons, and at most two
   cached reads when a sample is due): the SHT45 into air once a minute, the BMP581 into press
   every 5 minutes, each from the first call on; SCR_GAP while the port is not in the layout or has no
   value. No module keeps any of it. */
void oled_view_sample(scr_view_t *v, uint32_t now_ms);
/* The boot checklist's marks (port_mark), from each local port's WSMP host state, at every step (eight cached
   reads). Returns 1 when every port has its verdict (no SCR_PORT_WAIT): the scheduler's EV_SETTLED. An
   Absent port counts as waiting until ABSENT_AFTER_MS after the first call, when every port has probed. */
int oled_view_modules(scr_view_t *v, uint32_t now_ms);
/* LoRa time on air of a frame of len bytes at the node's radio settings (radio_cfg.h), ms. */
uint32_t oled_view_airtime_ms(uint8_t len);
#endif
