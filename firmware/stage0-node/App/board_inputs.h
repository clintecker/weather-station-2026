#ifndef BOARD_INPUTS_H
#define BOARD_INPUTS_H
/* The board inputs of the WSMP local modules (App/board_inputs.c): the cup counter, the board ADC
 * sequence (vane, ISET, charger input, VREFINT), the rain gauge interrupt, the charger pins and the
 * counter link probe. It defines the board seams of mod_wind.h and mod_power.h, the two power seams
 * and the link probe seams below. On the host,
 * firmware/host/sim_core.c defines the power seams once, with the setters h_power_adc() and
 * h_charger_edges(). */
#include <stdint.h>

void board_inputs_init(void);

/* The latest complete ADC sequence (power telemetry design, section 9.5). The counts are 12-bit
 * results of 16 oversampled conversions (shift 4), unscaled: clipping (>= 4080) and the conversions
 * to volts and amps belong to the caller (App/power_acq.c, firmware/common/power_regs.h).
 *   iset_raw  PB1, ADC1_IN5: the bq24074 ISET pin (charge current monitor)
 *   vin_raw   PA10, ADC1_IN6: the charger input through the 20k/10k divider (VIN = pin x
 *             POWER_VIN_DIVIDER_PPM / 1e6, nominal 3, measured per record 4.4 step 12)
 *   vref_raw  VREFINT
 *   vdda_mv   VDDA from VREFINT: 3300 x VREFINT_CAL / vref_raw (VREFINT_CAL taken at VDDA = 3.3 V)
 *   seq       sequences completed since boot (1 for the first): a caller sees a new result by it. A call
 *             returns the latest sequence again, with the same seq, until a new one completes, so
 *             a stalled ADC returns its last values: App/power_acq.c samples each seq once. */
typedef struct
{
  uint16_t iset_raw, vin_raw, vref_raw, vdda_mv;
  uint32_t seq;
} board_power_adc_t;

/* 0 with the latest complete sequence in *out; -1 if no sequence has completed yet or the ADC failed
   (it did not initialise, or VREFINT read 0). A call that takes a new sequence starts the next one. */
int board_power_adc(board_power_adc_t *out);

/* 1 if bench button b (1 B1 PA0, 2 B2 PA1, 3 B3 PC6) reads up (high: released; the buttons pull the pin
   low), 0 if down or b is no button. WS_BENCH_OLED=1 builds only: App/oled_app.c reads it each step. */
int board_button_up(unsigned b);

/* CHG (PB10) edges since boot, both directions, counted by EXTI10: monotonic (it wraps at 2^32). The
   2 Hz fault flash rule (section 6.3) lives in App/power_acq.c. */
uint32_t board_charger_edges(void);

/* The counter link probe (build-progression record M7, with its dated notes of 2026-10-30): once at
 * boot and every BOARD_LINK_PROBE_MS, the cups (PB5) and rain (PB4) inputs swap their internal
 * pull-ups for pull-downs for about 1 ms (a UTIL one-shot, no wait) and are read. The 10 kOhm
 * pull-ups sit at the jack end, so an intact link reads high and an open one low. The probe's own
 * edge on an open cups link is taken out of the cup count (board_pulse_count) and is never an edge
 * here; the rain line is masked through the probe, so a probe never makes a rain tip.
 *   board_link_lows       probes in a row that read the link low with no real edge since the first
 *                         of them (0 after a high read or a real edge); it saturates at UINT16_MAX
 *   board_link_edge_seen  1 if a real edge (a cup pulse, a rain tip) came since the last probe
 * On the host, firmware/host/wsmp_harness.c and tx_harness.c define both, with setters. */
#define BOARD_LINK_PROBE_MS 900000U   /* 15 minutes */
#define BOARD_LINK_LOWS 3U            /* low reads in a row, with no edge, that make a verdict */
enum board_link { BOARD_LINK_CUPS, BOARD_LINK_RAIN, BOARD_LINK_COUNT };
unsigned board_link_lows(enum board_link link);
int board_link_edge_seen(enum board_link link);

/* The meter link verdicts (M7), worst last, as #status meter_link= prints them (App/tx_console.c):
 * ok, cups-suspect, vane-out-of-table, cups-open, rain-open. Each module gives its own (App/mod_wind.c,
 * App/mod_rain.c); the status line prints the worst. */
enum meter_link { METER_LINK_OK, METER_LINK_CUPS_SUSPECT, METER_LINK_VANE_OUT, METER_LINK_CUPS_OPEN, METER_LINK_RAIN_OPEN,
                  METER_LINK_COUNT };
enum meter_link mod_wind_link(void);
enum meter_link mod_rain_link(void);
#endif
