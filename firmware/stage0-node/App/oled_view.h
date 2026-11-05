/* The bench screens' view of the node (WS_BENCH_OLED=1 only): the modules' live values, the radio
 * settings, the identity, and the flash, RAM, stack and journal use, read just before a frame is drawn.
 * Every source is read-only and cached (no bus or flash access), except the stack scan, which runs only
 * when the system bars start (about 1.5 ms). App/oled_app.c fills the exchange's fields itself. */
#ifndef OLED_VIEW_H
#define OLED_VIEW_H
#include <stdint.h>
#include "scr_view.h"

/* Everything but last_*, ack_*, extra_frames, reports, cipher* and airtime_pct (oled_app.c's). A
   temperature, humidity, pressure or UV row shows a value only while its port is in the layout (the
   snapshot the observation reads, wsmp_host_snapshot): otherwise the reading carries no value for it,
   and the row says NO <part>. */
void oled_view_fill(scr_view_t *v, enum scr_id id, unsigned frame);
/* LoRa time on air of a frame of len bytes at the node's radio settings (radio_cfg.h), ms. */
uint32_t oled_view_airtime_ms(uint8_t len);
#endif
