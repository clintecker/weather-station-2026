/* Host harness for the power acquisition (App/power_acq.c; docs/superpowers/specs/
 * 2026-10-29-power-telemetry-design.md section 9.4): the shared I2C bus (App/i2c_bus.c) on the host bus
 * model (i2c_sim.c, i2c_models.c) in the hub profile (-DWS_I2C_MUX=0), the board ADC and CHG edge seams
 * of sim_core.c (set by its h_power_adc() and h_charger_edges()), and the charger pins. Built once for
 * each power profile (-DWS_POWER_PROFILE=1, 2 or 3; 3 with the BQ25798, App/charger.c, and its console
 * line); tests/test_power_acq.py drives it through ctypes. */
#include <string.h>
#include "charger.h"
#include "i2c_bus.h"
#include "i2c_sim.h"
#include "power_acq.h"
#include "power_regs.h"
#include "sim_core.h"

#define TICK_MS 250U   /* WSMP_TICK_MS: the station ticks the power module this often */

const sim_config sim_cfg = { .name = "power_harness", .sources = (const sim_source *const[]){ &i2c_sim_source, NULL },
                             .reset_fatal = 1, .saturation_fatal = 1, .primask_leak_fatal = 1 };
int watchdog_healthy(void) { return 1; }   /* sim_core.c's watchdog; this harness never starts it */

void i2c_bus_done(enum i2c_client c, int rc) { power_acq_i2c_done(c, rc); }

static int charger_pins;
int board_charger_pins(void) { return charger_pins; }
void h_charger_pins(int pins) { charger_pins = pins; }

static uint32_t now_ms(void) { return (uint32_t)sim_ms(); }
static power_window_t win;

void h_init(void) { i2c_bus_init(); power_acq_init(now_ms()); }
uint32_t h_now_ms(void) { return now_ms(); }
void h_advance(uint32_t ms) { sim_advance(ms); }
/* ms of station time: a power tick, then the clock moves one tick. */
void h_run(uint32_t ms) { for (uint32_t t = 0; t < ms; t += TICK_MS) { power_acq_tick(now_ms()); sim_advance(TICK_MS); } }
void h_latch(void) { power_acq_latch(now_ms(), &win); }
int32_t h_value(int s) { return win.slot[s].value; }
int h_count(int s) { return win.slot[s].count; }
int h_quality(int s) { return win.slot[s].quality; }
uint32_t h_window_ms(void) { return win.window_ms; }
int h_first(void) { return win.first; }
int h_fitted(int s) { return power_acq_fitted((enum power_slot)s); }
int h_soc(void) { return win.slow.soc_256; }
int h_soc_rate(void) { return win.slow.soc_rate; }
int h_status(void) { return win.slow.charger_status; }
int h_monitor_temp(void) { return win.slow.monitor_temp; }
int h_vdda(void) { return win.slow.vdda_mv; }
int h_chg_batt_ma(void) { return win.slow.chg_batt_ma; }
int h_chg_input_mv(void) { return win.slow.chg_input_mv; }
int h_chg_input_ma(void) { return win.slow.chg_input_ma; }
int h_chg_batt_mv(void) { return win.slow.chg_batt_mv; }
int h_chg_temp(void) { return win.slow.chg_temp; }
static power_live_t live;
void h_live(void) { power_acq_live(&live); }
int h_live_batt_ok(void) { return live.batt_ok; }
int h_live_batt_ma_x100(void) { return live.batt_ma_x100; }
int h_live_out_mv(void) { return live.out_mv; }
int h_live_gauge_ok(void) { return live.gauge_ok; }
int h_live_vcell_mv(void) { return live.vcell_mv; }
int h_live_soc_x10(void) { return live.soc_pct_x10; }
int h_live_charging(void) { return live.charging; }
int h_live_charger(void) { return live.charger; }
int h_live_rail(int k, int what)   /* what: 0 fitted, 1 ok, 2 ma_x100, 3 mv */
{
  const power_rail_live_t *l = &live.rail[k];
  return what == 0 ? l->fitted : what == 1 ? l->ok : what == 2 ? (int)l->ma_x100 : (int)l->mv;
}
int h_rail_count(void) { return (int)POWER_RAIL_COUNT; }
int h_rail_addr(int i) { return POWER_RAILS[i].addr; }
int h_rail_sign(int i) { return POWER_RAILS[i].sign; }
int h_shunt_cal(int i) { return ina228_shunt_cal(POWER_RAILS[i].shunt_uohm, POWER_RAILS[i].current_lsb_ua); }

/* The bus model and its parts. */
int h_add_device(int kind, int addr7) { return i2c_sim_add(kind, (uint8_t)addr7); }
void h_remove_device(int dev) { i2c_sim_remove(dev); }
void h_restore_device(int dev) { i2c_sim_restore(dev); }
void h_device_mode(int dev, int mode, int sda_hold, uint32_t latency_ms) { i2c_sim_mode(dev, mode, sda_hold, latency_ms); }
int h_pin_errors(void) { return i2c_sim_pin_errors(); }
uint32_t h_addr_transfers(int addr7) { return i2c_sim_addr_transfers(addr7); }
void h_ina228_set(int dev, int32_t uv, int32_t ua) { model_ina228_set(dev, uv, ua); }
void h_ina228_die(int dev, int32_t mc) { model_ina228_die(dev, mc); }
void h_ina228_power_cycle(int dev) { model_ina228_power_cycle(dev); }
void h_max17048_cell(int32_t uv) { model_max17048_cell(uv); }
void h_max17048_soc_256(int soc) { model_max17048_soc_256((uint16_t)soc); }
void h_max17048_rate(int32_t mpct_h) { model_max17048_rate(mpct_h); }

/* The BQ25798 (phase C): the model's setters and the driver's state and console line. */
void h_bq_power_cycle(int dev) { model_bq25798_power_cycle(dev); }
void h_bq_cells(int dev, unsigned cells) { model_bq25798_cells(dev, cells); }
void h_bq_set(int dev, int32_t vbus, int32_t ibus, int32_t vbat, int32_t ibat, int32_t vsys) { model_bq25798_set(dev, vbus, ibus, vbat, ibat, vsys); }
void h_bq_ts(int dev, unsigned permille, int bits) { model_bq25798_ts(dev, permille, (uint8_t)bits); }
void h_bq_die(int dev, int32_t deci_c) { model_bq25798_die(dev, deci_c); }
void h_bq_status(int dev, int ac1, int ac2, unsigned chg_stat, int f0, int f1) { model_bq25798_status(dev, ac1, ac2, chg_stat, (uint8_t)f0, (uint8_t)f1); }
void h_bq_watchdog_expire(int dev) { model_bq25798_watchdog_expire(dev); }
void h_bq_ignore_limits(int dev, int ignore) { model_bq25798_ignore_limits(dev, ignore); }
int h_bq_reg(int dev, int reg) { return model_bq25798_reg(dev, (uint8_t)reg); }
void h_bq_poke(int dev, int reg, int v) { model_bq25798_poke(dev, (uint8_t)reg, (uint8_t)v); }
uint32_t h_bq_limit_writes(int dev) { return model_bq25798_limit_writes(dev); }
uint32_t h_bq_kicks(int dev) { return model_bq25798_kicks(dev); }
uint32_t h_bq_reg_resets(int dev) { return model_bq25798_reg_resets(dev); }
int h_chg(int what)   /* charger_t: 0 present, 1 ok, 2 configured, 3 hold, 4 applies, 5 resets, 6 failures, 7 mppt_sets */
{
  const charger_t *c = charger_state();
  const int v[8] = { c->present, c->ok, c->configured, c->hold, c->applies, c->resets, c->failures, c->mppt_sets };
  return what >= 0 && what < 8 ? v[what] : -1;
}
int h_pack_temp(void) { return win.slow.pack_temp; }
int h_pack_temp_dc(unsigned ts_raw) { return charger_pack_temp_dc((uint16_t)ts_raw); }
int h_chg_status_byte(void) { return charger_status_byte(); }
static char line[CHARGER_LINE_MAX];
const char *h_charger_line(unsigned len) { (void)charger_line(line, len < sizeof line ? len : sizeof line, now_ms()); return line; }
