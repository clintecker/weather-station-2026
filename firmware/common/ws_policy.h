#ifndef WS_POLICY_H
#define WS_POLICY_H
#include <stdint.h>
/* The TX node's transmission policy as pure functions (docs/radio-energy-policy.md, approved
 * 2026-10-12), host-tested in firmware/test_tx_policy.c. App/tx_policy.c holds the node's
 * state and feeds these from the journal and the clock. Energy is a WS_ENERGY_* code (ws_obs.h).
 * Times are seconds of the node's monotonic RTC clock (App/clock.h); differences wrap safely. */

#define WS_BACKLOG_MAX 20U   /* the largest per-minute backlog (SURPLUS) */
const char *ws_energy_name(int energy);   /* "surplus", "normal", "conserve", "critical"; "?" otherwise */

/* What the node knows about its battery this minute (docs/radio-energy-policy.md section 3, D1).
   soc_ok: the gauge answered, soc_x10 is its SOC in 0.1 %. v_ok: a cell voltage, v_mv (the gauge's
   VCELL, else the charger's VBAT). full: the charger's evidence of a full pack (power good, no fault,
   top-off or terminated, the battery not discharging), to enter SURPLUS. powered: the charger shows
   power good with no fault, to stay in SURPLUS (down to 90 % SOC). */
typedef struct { uint8_t soc_ok, v_ok, full, powered; uint16_t soc_x10, v_mv; } ws_energy_in;
/* The next energy state from the last one, with hysteresis on SOC and on voltage; the worse signal
   wins. No SOC: never better than CONSERVE (fail closed). A last state out of range counts as CONSERVE. */
int ws_energy_next(int last, const ws_energy_in *in);

/* LoRa time on air in ms, rounded up (Semtech formula, explicit header, CRC on): spreading factor
 * sf (7-12), bandwidth bw_hz, preamble symbols, coding rate cr 1-4 (4/5 .. 4/8). */
uint32_t ws_lora_airtime_ms(uint32_t payload, uint32_t sf, uint32_t bw_hz, uint32_t preamble, uint32_t cr);

/* Link state, updated at the end of every minute that sent something. WS_LINK_K_SILENT minutes
 * with no reply -> probing: the live reading only, no backlog. With healthy energy (SURPLUS,
 * NORMAL) the live reading still goes every minute (ws_link_may_send, firmware/stage0.c), so the
 * node relinks within a minute; only CONSERVE backs off 2, 4, 8, then 15 minutes, counted from
 * the start of the exchange that went unanswered (on the minute grid). Any reply: linked. */
#define WS_LINK_K_SILENT 3U
typedef struct { uint8_t probing, probe_step; uint32_t silent, next_probe_s; } ws_link;
enum { WS_LINK_SAME, WS_LINK_RELINKED, WS_LINK_PROBING, WS_LINK_PROBE_MISSED };
/* answered: the gateway answered something in the exchange that started at sent_s. Returns what
   changed (WS_LINK_*); silent keeps the count of silent minutes until a relink resets it. */
int ws_link_minute(ws_link *l, int answered, uint32_t sent_s);
uint32_t ws_link_probe_interval(const ws_link *l);   /* the current back-off step, s */

/* What one minute may send: -1 nothing (the reading stays journaled), else how many backlog
 * frames may follow the live reading. The stricter of the energy and link states wins:
 * CRITICAL (or an energy code out of range) never transmits. CONSERVE sends at most every 5
 * minutes (the product spec's conservation reports). Probing sends no backlog. The backlog is
 * capped per energy state, by the minute's airtime budget, and by max_backlog (the send queue).
 * The budget is the energy state's cap less reserve_ms (the health report's airtime in a minute
 * whose report follows the exchange, else 0), over exchange_ms (one answered exchange's radio
 * time), saturating: a reserve at or above the cap, or an exchange longer than what is left, leaves
 * the live reading only. The live reading always goes, and so does a due health report: in
 * CONSERVE at SF12 the two together exceed the 2 s cap once per health report (power telemetry
 * design 6.4). last_send_s: the last minute that sent. */
int ws_minute_backlog(int energy, const ws_link *l, uint32_t now_s, uint32_t last_send_s, uint32_t exchange_ms,
                      uint32_t reserve_ms, unsigned max_backlog);

/* Strikes (the safety net against records the gateway keeps refusing): a record that stays
 * unanswered while a frame sent AFTER it in the same exchange is answered gets a strike; at the
 * limit it is abandoned. An answer to an earlier frame proves nothing (on a weak link the next
 * frame may simply be lost), so it never strikes (the drain sends one more frame after a miss so
 * that a refused record can still be told apart). Keyed by the record's identity (epoch, seq), not
 * its journal slot: a slot is reused after the ring wraps, and a record can leave the journal
 * without its entry being cleared. A new identity takes the slot with the fewest strikes. */
typedef struct { uint32_t epoch, seq; uint8_t n; } ws_strike;
/* One more strike; 1 when it reaches limit (the entry is then cleared), else 0. */
int ws_strike_note(ws_strike *t, unsigned slots, uint32_t epoch, uint32_t seq, unsigned limit);
void ws_strike_forget(ws_strike *t, unsigned slots, uint32_t epoch, uint32_t seq);
/* Which records of an exchange earn a strike: struck[i] = 1 if queue[i] got no reply but a later
   frame of the same exchange did. */
void ws_strike_targets(const uint8_t *replied, unsigned n, uint8_t *struck);
#endif
