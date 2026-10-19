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
#endif
