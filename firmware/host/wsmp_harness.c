/* Host harness for the WSMP bench station (docs/superpowers/plans/2026-10-18-wsmp-bench-station.md):
 * the shared I2C bus (App/i2c_bus.c) on firmware/host/i2c_sim.c, and later the local modules and the
 * station host. Built with -DWSMP_BUS_ONLY, it defines i2c_bus_done itself and records every
 * completion (tests/test_i2c_bus.py). tests drive it through ctypes. */
#include <string.h>
#include "i2c_bus.h"
#include "i2c_sim.h"
#include "sim_core.h"

const sim_config sim_cfg = { .name = "wsmp_harness", .sources = (const sim_source *const[]){ &i2c_sim_source, NULL },
                             .reset_fatal = 1, .saturation_fatal = 1, .primask_leak_fatal = 1 };
int watchdog_healthy(void) { return 1; }   /* sim_core.c's watchdog; this harness never starts it */

void h_advance(uint32_t ms) { sim_advance(ms); }
int h_add_device(int kind, int addr7) { return i2c_sim_add(kind, (uint8_t)addr7); }
void h_remove_device(int dev) { i2c_sim_remove(dev); }
void h_device_mode(int dev, int mode, int sda_hold, uint32_t latency_ms) { i2c_sim_mode(dev, mode, sda_hold, latency_ms); }
uint32_t h_transfers(void) { return i2c_sim_transfers(); }
uint32_t h_deinits(void) { return i2c_sim_deinits(); }
int h_scl_edges(void) { return i2c_sim_scl_edges(); }
int h_i2c_ready(void) { return i2c_sim_ready(); }
int h_pin_errors(void) { return i2c_sim_pin_errors(); }
int h_power(void) { return i2c_sim_power(); }
int h_complete_at_guard(int error) { return i2c_sim_complete_at_guard(error); }

#ifdef WSMP_BUS_ONLY
#define LOG_MAX 64
static int log_client[LOG_MAX], log_rc[LOG_MAX], nlog;
static uint64_t log_at[LOG_MAX];
static uint8_t rx[I2C_C_COUNT][I2C_SIM_BUF], tx[I2C_C_COUNT][I2C_SIM_BUF];
void i2c_bus_done(enum i2c_client c, int rc)
{
  if (nlog < LOG_MAX) { log_client[nlog] = (int)c; log_rc[nlog] = rc; log_at[nlog] = sim_now(); nlog++; }
}
void h_init(void) { i2c_bus_init(); }
int h_submit(int client, int addr7, int txlen, int reg, int rxlen)
{
  if (client < 0 || client >= I2C_C_COUNT) return -2;
  memset(rx[client], 0, sizeof rx[client]);
  tx[client][0] = (uint8_t)reg;
  for (int i = 1; i < txlen && i < I2C_SIM_BUF; i++) tx[client][i] = (uint8_t)i;
  return i2c_bus_submit((enum i2c_client)client, (uint8_t)addr7, tx[client], (uint8_t)txlen, rx[client], (uint8_t)rxlen);
}
int h_log_count(void) { return nlog; }
int h_log_client(int i) { return i >= 0 && i < nlog ? log_client[i] : -1; }
int h_log_rc(int i) { return i >= 0 && i < nlog ? log_rc[i] : 99; }
uint32_t h_log_ms(int i) { return i >= 0 && i < nlog ? (uint32_t)(log_at[i] / SIM_UNITS_PER_MS) : 0U; }
int h_rx(int client, int i) { return rx[client][i]; }
#else
#include "stage0.h"
#include "wsmp.h"
#include "wsmp_local.h"
static uint32_t now_ms(void) { return (uint32_t)sim_ms(); }
void h_init(uint32_t boot) { local_init(boot); }
uint32_t h_now_ms(void) { return now_ms(); }
void h_tick_all(void) { for (int p = P_AIR_TH; p < P_COUNT; p++) local_tick((enum wsmp_port)p, now_ms()); }
/* ms of station time: a module tick for every port, then the clock moves one tick. */
void h_run(uint32_t ms) { for (uint32_t t = 0; t < ms; t += WSMP_TICK_MS) { h_tick_all(); sim_advance(WSMP_TICK_MS); } }
void h_latch(int port, int token, uint32_t utc) { local_latch((enum wsmp_port)port, (uint16_t)token, utc, now_ms()); }
void h_snapshot(int port, uint8_t *out) { local_snapshot((enum wsmp_port)port, out); }
void h_identity(int port, uint8_t *id, uint8_t *desc) { local_identity((enum wsmp_port)port, id, desc); }
int h_probe(int port) { uint16_t seq; return local_probe_result((enum wsmp_port)port, &seq); }
int h_probe_seq(int port) { uint16_t seq; (void)local_probe_result((enum wsmp_port)port, &seq); return seq; }
/* The module's own descriptors against the registry (WSMP-D7). */
int h_desc_check(int port)
{
  uint8_t id[WSMP_IDENTITY_LEN], desc[WSMP_DESC_BLOCK_LEN];
  wsmp_identity ident; wsmp_desc d[WSMP_MAX_CHANNELS];
  local_identity((enum wsmp_port)port, id, desc);
  int rc = wsmp_unpack_identity(id, &ident);
  if (rc == WSMP_OK) rc = wsmp_unpack_desc(desc, ident.channels, d);
  return rc == WSMP_OK ? wsmp_desc_check(d, ident.channels, ident.type, ident.schema) : rc;
}
void h_sht45_set(int dev, int t_raw, int h_raw, int bad) { model_sht45_set(dev, (uint16_t)t_raw, (uint16_t)h_raw, bad); }
void h_shtc3_set(int dev, int t_raw, int h_raw) { model_shtc3_set(dev, (uint16_t)t_raw, (uint16_t)h_raw); }
int h_shtc3_asleep(int dev) { return model_shtc3_asleep(dev); }
void h_reg_set_id(int dev, int id) { model_reg_set_id(dev, (uint8_t)id); }
void h_reg_power_cycle(int dev) { model_reg_power_cycle(dev); }
void h_bmp581_set(int dev, uint32_t pa64) { model_reg_set_data(dev, pa64); }
void h_ltr390_set(int dev, uint32_t counts) { model_reg_set_data(dev, counts); }
void h_ina228_set(int dev, int32_t uv, int32_t ua) { model_ina228_set(dev, uv, ua); }
void h_max17048_set(int dev, int soc) { model_max17048_set(dev, (uint8_t)soc); }
static int charger_pins;
int board_charger_pins(void) { return charger_pins; }
void h_charger_pins(int pins) { charger_pins = pins; }
/* The cup counter (LPTIM1, 16 bits) and the vane ADC. A tear makes the counter move by one pulse
   right after the next read, as a pulse that arrives between two reads does. */
static uint16_t pulse_counter;
static int pulse_tears;
static uint16_t vane;
uint16_t board_pulse_count(void)
{
  uint16_t v = pulse_counter;
  if (pulse_tears > 0) { pulse_counter++; pulse_tears--; }
  return v;
}
int board_vane_mv(uint16_t *mv) { *mv = vane; return 1; }
void h_pulses_add(int n) { pulse_counter = (uint16_t)(pulse_counter + n); }
void h_pulse_counter_set(int v) { pulse_counter = (uint16_t)v; }
void h_pulse_tear(int n) { pulse_tears = n; }
void h_vane_mv(int mv) { vane = (uint16_t)mv; }
/* The SHT45 conversion of the driver in use (firmware/stage0.c), as the test's oracle for one sample. */
int h_sht45_parse(int t_raw, int h_raw, int16_t *t, uint16_t *h)
{
  uint8_t b[WS_SHT45_REPLY_LEN] = { (uint8_t)(t_raw >> 8), (uint8_t)t_raw, 0, (uint8_t)(h_raw >> 8), (uint8_t)h_raw, 0 };
  b[2] = ws_crc8(b, 2); b[5] = ws_crc8(b + 3, 2);
  return ws_sht45_parse(b, t, h);
}
#endif
