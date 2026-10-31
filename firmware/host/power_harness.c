/* Host harness for the power acquisition (App/power_acq.c; docs/superpowers/specs/
 * 2026-10-29-power-telemetry-design.md section 9.4): the shared I2C bus (App/i2c_bus.c) on the host bus
 * model (i2c_sim.c, i2c_models.c) in the hub profile (-DWS_I2C_MUX=0), the board ADC and CHG edge seams
 * of sim_core.c (set by its h_power_adc() and h_charger_edges()), and the charger pins. Built once for
 * each power profile (-DWS_POWER_PROFILE=1 or 2); tests/test_power_acq.py drives it through ctypes. */
#include <string.h>
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
