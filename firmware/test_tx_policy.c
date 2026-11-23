#include "common/ws_policy.h"
#include "common/ws_obs.h"
#undef NDEBUG /* the checks below are assert()s: keep them in every build */
#include <assert.h>
#include <math.h>
#include <string.h>
/* Host tests for the TX transmission policy (firmware/common/ws_policy.c,
 * docs/radio-energy-policy.md). Expected values come from the policy text and Semtech's formula,
 * not from the code under test. */

/* Semtech AN1200.13 time on air, in floating point: explicit header, CRC on. */
static double airtime_ref_ms(int payload, int sf, double bw_hz, int preamble, int cr) {
 double t_sym = pow(2, sf) / bw_hz * 1000.0;
 int de = t_sym > 16.0;
 double blocks = ceil((8.0 * payload - 4.0 * sf + 28 + 16) / (4.0 * (sf - 2 * de)));
 if (blocks < 0) blocks = 0;
 return (preamble + 4.25 + 8 + blocks * (cr + 4)) * t_sym;
}

static void airtime(void) {
 const double bws[] = { 125000, 250000, 500000 };
 for (int sf = 7; sf <= 12; sf++)
  for (int b = 0; b < 3; b++)
   for (int pl = 0; pl <= 255; pl += 17) {
    double ref = airtime_ref_ms(pl, sf, bws[b], 8, 1);
    uint32_t got = ws_lora_airtime_ms((uint32_t)pl, (uint32_t)sf, (uint32_t)bws[b], 8, 1);
    assert(got >= ref && got <= ref + 1.0);            /* rounded up, by at most 1 ms */
   }
 assert(ws_lora_airtime_ms(51, 7, 500000, 8, 1) == 26);  /* the T/RH-only frame: 25.7 ms at SF7/500 kHz */
 assert(ws_lora_airtime_ms(77, 7, 500000, 8, 1) == 35);  /* the WSMP bench build's widest frame (OBS_FRAME_MAX): 34.6 ms */
 assert(ws_lora_airtime_ms(42, 7, 500000, 8, 1) == 22);  /* 21.8 ms */
 assert(ws_lora_airtime_ms(10, 12, 125000, 8, 1) == 992);   /* low data rate optimisation: 991.2 ms */
 /* The frames of the node's exchange (power telemetry design 5.4, 6.4), 500 kHz: the widest
    observation (OBS_FRAME_MAX, 77 + 16 = 93 B), the ACK (33 B) and the health report (64 + 16 = 80 B). */
 assert(ws_lora_airtime_ms(93, 7, 500000, 8, 1) == 42);   /* 41.024 ms */
 assert(ws_lora_airtime_ms(33, 7, 500000, 8, 1) == 18);   /* 17.984 ms */
 assert(ws_lora_airtime_ms(80, 7, 500000, 8, 1) == 36);   /* 35.904 ms */
 assert(ws_lora_airtime_ms(93, 12, 500000, 8, 1) == 822); /* 821.248 ms */
 assert(ws_lora_airtime_ms(33, 12, 500000, 8, 1) == 412); /* 411.648 ms */
 assert(ws_lora_airtime_ms(80, 12, 500000, 8, 1) == 740); /* 739.328 ms */
}

static void link(void) {
 ws_link l = { 0 };
 /* Two silent minutes: still linked. The third: probing, first probe 120 s after that exchange. */
 assert(ws_link_minute(&l, 0, 1000) == WS_LINK_SAME && ws_link_minute(&l, 0, 1060) == WS_LINK_SAME);
 assert(!l.probing && l.silent == 2);
 assert(ws_link_minute(&l, 0, 1120) == WS_LINK_PROBING);
 assert(l.probing && l.silent == 3 && l.next_probe_s == 1120 + 120 && ws_link_probe_interval(&l) == 120);
 /* Unanswered probes back off 240, 480, then 900 s and stay there. */
 const uint32_t backoff[] = { 240, 480, 900, 900, 900 };
 for (unsigned i = 0; i < 5; i++) {
  uint32_t at = 2000 + 1000 * i;
  assert(ws_link_minute(&l, 0, at) == WS_LINK_PROBE_MISSED);
  assert(l.next_probe_s == at + backoff[i] && ws_link_probe_interval(&l) == backoff[i]);
 }
 assert(l.silent == 8);
 /* Any reply relinks and starts the count again; a reply while linked changes nothing. */
 assert(ws_link_minute(&l, 1, 9000) == WS_LINK_RELINKED);
 assert(!l.probing && l.silent == 0 && l.probe_step == 0);
 assert(ws_link_minute(&l, 1, 9060) == WS_LINK_SAME);
 assert(ws_link_minute(&l, 0, 9120) == WS_LINK_SAME && l.silent == 1);
}

static void minute(void) {
 ws_link linked = { 0 }, probing = { .probing = 1, .next_probe_s = 5000 };
 uint32_t one = 100;   /* ms per answered exchange: no airtime limit below 15 s / 5 s */
 /* Backlog per energy state while linked (docs/radio-energy-policy.md): 20, 5, 0; CRITICAL silent. */
 assert(ws_minute_backlog(WS_ENERGY_SURPLUS, &linked, 4000, 3940, one, 0, 20) == 20);
 assert(ws_minute_backlog(WS_ENERGY_NORMAL, &linked, 4000, 3940, one, 0, 20) == 5);
 assert(ws_minute_backlog(WS_ENERGY_CRITICAL, &linked, 4000, 3000, one, 0, 20) == -1);
 assert(ws_minute_backlog(4, &linked, 4000, 3000, one, 0, 20) == -1);   /* unknown energy: never sends */
 assert(ws_minute_backlog(-1, &linked, 4000, 3000, one, 0, 20) == -1);
 /* CONSERVE: live reading only, at most every 300 s. */
 assert(ws_minute_backlog(WS_ENERGY_CONSERVE, &linked, 4000, 3701, one, 0, 20) == -1);
 assert(ws_minute_backlog(WS_ENERGY_CONSERVE, &linked, 4000, 3700, one, 0, 20) == 0);
 /* Probing: the live reading every minute with healthy energy; CONSERVE waits for the probe time. */
 assert(ws_minute_backlog(WS_ENERGY_NORMAL, &probing, 4000, 3940, one, 0, 20) == 0);
 assert(ws_minute_backlog(WS_ENERGY_SURPLUS, &probing, 4000, 3940, one, 0, 20) == 0);
 assert(ws_minute_backlog(WS_ENERGY_CONSERVE, &probing, 4999, 3000, one, 0, 20) == -1);
 assert(ws_minute_backlog(WS_ENERGY_CONSERVE, &probing, 5000, 3000, one, 0, 20) == 0);
 /* The airtime budget (15 s, 5 s, 2 s per minute) caps the frames; the live reading always goes. */
 assert(ws_minute_backlog(WS_ENERGY_NORMAL, &linked, 4000, 3940, 1000, 0, 20) == 4);   /* 5 frames of 1 s */
 assert(ws_minute_backlog(WS_ENERGY_SURPLUS, &linked, 4000, 3940, 1000, 0, 20) == 14);
 assert(ws_minute_backlog(WS_ENERGY_NORMAL, &linked, 4000, 3940, 6000, 0, 20) == 0);  /* over budget: live only */
 assert(ws_minute_backlog(WS_ENERGY_NORMAL, &linked, 4000, 3940, 0, 0, 20) == 0);     /* no estimate: live only */
 /* And the send queue. */
 assert(ws_minute_backlog(WS_ENERGY_SURPLUS, &linked, 4000, 3940, one, 0, 7) == 7);
 /* Wrap-safe: the next probe time is compared as a signed difference. */
 ws_link wrap = { .probing = 1, .next_probe_s = 10 };
 assert(ws_minute_backlog(WS_ENERGY_CONSERVE, &wrap, 0xFFFFFFF0u, 0, one, 0, 20) == -1);
 assert(ws_minute_backlog(WS_ENERGY_CONSERVE, &wrap, 11, 0xFFFFFE00u, one, 0, 20) == 0);
}

/* The health report's airtime is reserved from the minute's cap when a report follows the exchange
 * (power telemetry design 6.4): by_airtime = cap > reserve ? (cap - reserve) / exchange : 0, and
 * backlog = by_airtime > 1 ? min(backlog, by_airtime - 1) : 0. One answered exchange is the
 * observation + the ACK + 300 ms turnaround; the airtimes are those of airtime() above.
 *   SF7:  42 + 18 + 300 = 360 ms (formula 41.0 + 18.0 + 300 = 359.0); report 36 ms.
 *   SF12: 822 + 412 + 300 = 1534 ms (formula 821.2 + 411.6 + 300 = 1532.8); report 740 ms. */
static void health_reserve(void) {
 ws_link linked = { 0 };
 const uint32_t sf7 = 42 + 18 + 300, sf7_diag = 36, sf12 = 822 + 412 + 300, sf12_diag = 740;
 assert(sf7 == 360 && sf12 == 1534);
 /* SF7: 5000 / 360 = 13 exchanges, (5000 - 36) / 360 = 13 in a health minute: NORMAL's 5 binds. */
 assert(ws_minute_backlog(WS_ENERGY_NORMAL, &linked, 4000, 3940, sf7, 0, 20) == 5);
 assert(ws_minute_backlog(WS_ENERGY_NORMAL, &linked, 4000, 3940, sf7, sf7_diag, 20) == 5);
 /* SURPLUS: 15000 / 360 = 41, (15000 - 36) / 360 = 41: its 20 binds. */
 assert(ws_minute_backlog(WS_ENERGY_SURPLUS, &linked, 4000, 3940, sf7, sf7_diag, 20) == 20);
 /* SF12 NORMAL: 5000 / 1534 = 3 exchanges (backlog 2); (5000 - 740) / 1534 = 4260 / 1534 = 2 (backlog 1). */
 assert(ws_minute_backlog(WS_ENERGY_NORMAL, &linked, 4000, 3940, sf12, 0, 20) == 2);
 assert(ws_minute_backlog(WS_ENERGY_NORMAL, &linked, 4000, 3940, sf12, sf12_diag, 20) == 1);
 /* SF12 CONSERVE: 2000 / 1534 = 1; (2000 - 740) / 1534 = 0: the live reading only, never a wrapped
    count. Live + report = 1534 + 740 = 2274 ms, over the 2 s cap once per health report (R3). */
 assert(ws_minute_backlog(WS_ENERGY_CONSERVE, &linked, 4000, 3700, sf12, 0, 20) == 0);
 assert(ws_minute_backlog(WS_ENERGY_CONSERVE, &linked, 4000, 3700, sf12, sf12_diag, 20) == 0);
 /* A reserve at or above the cap: by_airtime = 0, the live reading only (no unsigned wrap). */
 assert(ws_minute_backlog(WS_ENERGY_NORMAL, &linked, 4000, 3940, sf7, 5000, 20) == 0);
 assert(ws_minute_backlog(WS_ENERGY_NORMAL, &linked, 4000, 3940, sf7, 5001, 20) == 0);
 assert(ws_minute_backlog(WS_ENERGY_SURPLUS, &linked, 4000, 3940, sf7, UINT32_MAX, 20) == 0);
 assert(ws_minute_backlog(WS_ENERGY_NORMAL, &linked, 4000, 3940, 0, 5000, 20) == 0);
 /* Just inside: 5000 - 4279 = 721 = 2 x 360 + 1: by_airtime 2, backlog 1. */
 assert(ws_minute_backlog(WS_ENERGY_NORMAL, &linked, 4000, 3940, sf7, 4279, 20) == 1);
 /* The energy and link gates still come first. */
 assert(ws_minute_backlog(WS_ENERGY_CRITICAL, &linked, 4000, 3000, sf7, sf7_diag, 20) == -1);
 assert(ws_minute_backlog(WS_ENERGY_CONSERVE, &linked, 4000, 3701, sf12, sf12_diag, 20) == -1);
}

/* Only an answer AFTER an unanswered frame earns it a strike. */
static void strike_targets(void) {
 uint8_t s[5];
 const uint8_t a[5] = { 1, 0, 1, 0, 0 };              /* live answered, b1 missed, b2 answered, b3 b4 missed */
 ws_strike_targets(a, 5, s);
 assert(s[0] == 0 && s[1] == 1 && s[2] == 0 && s[3] == 0 && s[4] == 0);
 const uint8_t b[2] = { 1, 0 };                        /* the last frame missed: nothing after it answered */
 ws_strike_targets(b, 2, s);
 assert(s[0] == 0 && s[1] == 0);
 const uint8_t c[3] = { 0, 0, 1 };                     /* both earlier misses were followed by an answer */
 ws_strike_targets(c, 3, s);
 assert(s[0] == 1 && s[1] == 1 && s[2] == 0);
 ws_strike_targets(c, 0, s);                           /* empty exchange */
}

static void strikes(void) {
 ws_strike t[3];
 memset(t, 0, sizeof t);
 /* The 10th strike of one record reaches the limit and clears its entry. */
 for (int i = 1; i < 10; i++) assert(ws_strike_note(t, 3, 1, 7, 10) == 0);
 assert(ws_strike_note(t, 3, 1, 7, 10) == 1);
 assert(ws_strike_note(t, 3, 1, 7, 10) == 0);        /* counting starts again */
 /* Keyed by identity: another seq (or epoch) is another record. */
 memset(t, 0, sizeof t);
 for (int i = 1; i < 10; i++) { ws_strike_note(t, 3, 1, 7, 10); ws_strike_note(t, 3, 2, 7, 10); }
 assert(ws_strike_note(t, 3, 1, 8, 10) == 0);
 assert(ws_strike_note(t, 3, 1, 7, 10) == 1 && ws_strike_note(t, 3, 2, 7, 10) == 1);
 /* Forgetting (an ACK) ends a record's strikes. */
 memset(t, 0, sizeof t);
 for (int i = 1; i < 10; i++) ws_strike_note(t, 3, 1, 7, 10);
 ws_strike_forget(t, 3, 1, 7);
 for (int i = 1; i < 10; i++) assert(ws_strike_note(t, 3, 1, 7, 10) == 0);
 /* Full table: a new record takes the entry with the fewest strikes; the others keep theirs. */
 memset(t, 0, sizeof t);
 for (int i = 0; i < 5; i++) { ws_strike_note(t, 3, 1, 1, 10); ws_strike_note(t, 3, 1, 3, 10); }
 ws_strike_note(t, 3, 1, 2, 10);                      /* 5, 5 and 1 strikes */
 ws_strike_note(t, 3, 1, 4, 10);                      /* replaces seq 2 */
 for (int i = 0; i < 4; i++) assert(ws_strike_note(t, 3, 1, 1, 10) == 0);
 assert(ws_strike_note(t, 3, 1, 1, 10) == 1);         /* seq 1 kept its 5 */
 for (int i = 0; i < 8; i++) assert(ws_strike_note(t, 3, 1, 4, 10) == 0);
 assert(ws_strike_note(t, 3, 1, 4, 10) == 1);         /* seq 4 started at 1 */
}

/* ws_energy_next: the thresholds are the D1 call (docs/radio-energy-policy.md section 3), written here
   from the document, not read from ws_policy.c. SOC in 0.1 %, voltage in mV. */
enum { S = WS_ENERGY_SURPLUS, N = WS_ENERGY_NORMAL, C = WS_ENERGY_CONSERVE, X = WS_ENERGY_CRITICAL };
static int gauge(int last, unsigned soc_x10, unsigned mv) {
 ws_energy_in in = { .soc_ok = 1, .v_ok = 1, .soc_x10 = (uint16_t)soc_x10, .v_mv = (uint16_t)mv };
 return ws_energy_next(last, &in);
}
static int volts(int last, unsigned mv) {   /* the gauge missing: the charger's VBAT only */
 ws_energy_in in = { .v_ok = 1, .v_mv = (uint16_t)mv };
 return ws_energy_next(last, &in);
}
static int full(int last, unsigned soc_x10, unsigned mv) {   /* full implies power good with no fault */
 ws_energy_in in = { .soc_ok = 1, .v_ok = 1, .full = 1, .powered = 1, .soc_x10 = (uint16_t)soc_x10, .v_mv = (uint16_t)mv };
 return ws_energy_next(last, &in);
}
static int powered(int last, unsigned soc_x10, unsigned mv) {   /* power good, no fault, but not full */
 ws_energy_in in = { .soc_ok = 1, .v_ok = 1, .powered = 1, .soc_x10 = (uint16_t)soc_x10, .v_mv = (uint16_t)mv };
 return ws_energy_next(last, &in);
}

static void energy(void) {
 const unsigned ok_mv = 3900;   /* a voltage that decides nothing below SURPLUS */
 /* SOC down: NORMAL holds to 30.0 %, CONSERVE below it, CRITICAL below 8.0 %. */
 assert(gauge(N, 300, ok_mv) == N && gauge(N, 299, ok_mv) == C);
 assert(gauge(C, 80, ok_mv) == C && gauge(C, 79, ok_mv) == X);
 assert(gauge(N, 79, ok_mv) == X);                     /* a fall past both goes straight to CRITICAL */
 /* SOC up, with the 5-point hysteresis: CRITICAL holds below 13.0 %, CONSERVE below 35.0 %. */
 assert(gauge(X, 129, ok_mv) == X && gauge(X, 130, ok_mv) == C);
 assert(gauge(X, 349, ok_mv) == C && gauge(X, 350, ok_mv) == N);
 assert(gauge(C, 349, ok_mv) == C && gauge(C, 350, ok_mv) == N);
 for (unsigned soc = 300; soc < 350; soc++) assert(gauge(C, soc, ok_mv) == C && gauge(N, soc, ok_mv) == N);
 for (unsigned soc = 80; soc < 130; soc++) assert(gauge(X, soc, ok_mv) == X && gauge(C, soc, ok_mv) == C);
 /* Voltage, with 100 mV of hysteresis: CONSERVE below 3600 (out at 3700), CRITICAL below 3450 (out at 3550). */
 assert(gauge(N, 800, 3600) == N && gauge(N, 800, 3599) == C);
 assert(gauge(C, 800, 3699) == C && gauge(C, 800, 3700) == N);
 assert(gauge(C, 800, 3450) == C && gauge(C, 800, 3449) == X && gauge(N, 800, 3449) == X);
 assert(gauge(X, 800, 3549) == X && gauge(X, 800, 3550) == C && gauge(X, 800, 3700) == N);
 /* The worse signal wins, so leaving a state needs both past their exits. */
 assert(gauge(N, 800, 3500) == C && gauge(N, 200, 4100) == C && gauge(N, 50, 3700) == X);
 assert(gauge(C, 400, 3650) == C && gauge(C, 340, 3800) == C && gauge(C, 400, 3800) == N);
 assert(gauge(X, 400, 3500) == X && gauge(X, 100, 3800) == X);
 /* The gauge missing (no SOC): never better than CONSERVE; the voltage still finds CRITICAL. */
 assert(volts(N, 4200) == C && volts(S, 4200) == C && volts(C, 3600) == C);
 assert(volts(C, 3449) == X && volts(X, 3549) == X && volts(X, 3550) == C && volts(X, 4200) == C);
 /* No input at all: CONSERVE, or CRITICAL kept. */
 ws_energy_in none = { 0 };
 assert(ws_energy_next(N, &none) == C && ws_energy_next(S, &none) == C && ws_energy_next(C, &none) == C);
 assert(ws_energy_next(X, &none) == X);
 /* SURPLUS: full, 4000 mV and 95.0 % in. It holds while SOC stays at 90.0 % or more and the charger
    shows power good with no fault, whatever the stage, the battery current and the voltage (the pack
    carries the load at times; that is what the 90 % is for); NORMAL's own thresholds still apply. */
 assert(full(N, 950, 4000) == S && full(N, 949, 4100) == N && full(N, 990, 3999) == N);
 assert(gauge(N, 990, 4150) == N && powered(N, 990, 4150) == N);   /* not full: NORMAL */
 assert(full(S, 900, 4100) == S && full(S, 899, 4100) == N);
 assert(powered(S, 900, 3950) == S && powered(S, 990, 3800) == S && powered(S, 899, 4100) == N);
 assert(gauge(S, 990, 4150) == N);                     /* no power good, or a fault: NORMAL */
 assert(powered(S, 990, 3599) == C && powered(S, 200, 4100) == C);   /* NORMAL's thresholds still rule */
 ws_energy_in full_no_soc = { .v_ok = 1, .full = 1, .powered = 1, .v_mv = 4150 };
 assert(ws_energy_next(S, &full_no_soc) == C);         /* full but the gauge gone: fail closed */
 assert(full(C, 990, 4150) == S);                       /* charged back from CONSERVE in one step */
 /* A last state out of range counts as CONSERVE. */
 assert(gauge(7, 320, ok_mv) == C && gauge(-1, 350, ok_mv) == N && ws_energy_next(9, &none) == C);
}

int main(void) {
 airtime();
 link();
 minute();
 health_reserve();
 strikes();
 strike_targets();
 energy();
 assert(!strcmp(ws_energy_name(WS_ENERGY_NORMAL), "normal") && !strcmp(ws_energy_name(4), "?"));
 return 0;
}
