/* Host harness for the SHT45 driver (App/sensor.c, compiled unchanged) on the shared I2C bus
 * (App/i2c_bus.c) and the host bus model (firmware/host/i2c_sim.c).
 *
 * The board is firmware/host/sim_core.c: ST's timer server in 1/1024 s ticks (rounded down, at least
 * 3 ticks: timer_if.c), the sequencer and the event loop; tasks that never settle abort the test. The
 * bus model holds one SHT45 whose behaviour the test chooses. tests/test_sensor_machine.py drives it
 * through ctypes. */
#include "i2c_sim.h"
#include "sensor.h"
#include "sim_core.h"
#include "stage0.h"

const sim_config sim_cfg = { .name = "sensor_harness", .sources = (const sim_source *const[]){ &i2c_sim_source, NULL },
                             .reset_fatal = 1, .saturation_fatal = 1, .primask_leak_fatal = 1 };
int watchdog_healthy(void) { return 1; }   /* sim_core.c's watchdog; this harness never starts it */

/* The test's device modes (tests/test_sensor_machine.py), in the bus model's terms. */
enum { DEV_OK, DEV_NACK_CMD, DEV_NACK_READ, DEV_BAD_CRC, DEV_HANG_CMD, DEV_HANG_READ, DEV_BUSY };
static int dev;

static int done_calls, done_rc;
static int16_t done_t;
static uint16_t done_h;
static uint64_t done_at, started_at;
void sensor_done(int rc, int16_t t, uint16_t h) { done_calls++; done_rc = rc; done_t = t; done_h = h; done_at = sim_now(); }
void h_advance(uint32_t ms) { sim_advance(ms); }
void h_init(void)
{
  dev = i2c_sim_add(DEVK_SHT45, WS_SHT45_ADDR);
  sensor_init();
}
void h_device(int mode, int sda_hold, uint32_t latency_ms)
{
  static const int bus_mode[] = { DM_OK, DM_NACK_ADDR, DM_NACK_DATA, DM_OK, DM_HANG, DM_HANG_READ, DM_BUSY };
  i2c_sim_mode(dev, bus_mode[mode], sda_hold, latency_ms);
  model_sht45_set(dev, 0x8000, 0x8000, mode == DEV_BAD_CRC);
}
int h_start(void) { started_at = sim_now(); return sensor_start(); }
int h_done_calls(void) { return done_calls; }
int h_done_rc(void) { return done_rc; }
int h_done_t(void) { return done_t; }
int h_done_h(void) { return done_h; }
uint32_t h_done_after(void) { return (uint32_t)((done_at - started_at) / SIM_UNITS_PER_MS); }   /* whole ms */
uint32_t h_transfers(void) { return i2c_sim_transfers(); }
uint32_t h_deinits(void) { return i2c_sim_deinits(); }
int h_scl_edges(void) { return i2c_sim_scl_edges(); }
int h_i2c_ready(void) { return i2c_sim_ready(); }
int h_read_too_early(void) { return model_sht45_read_too_early(); }
int h_pin_errors(void) { return i2c_sim_pin_errors(); }
/* A read left hanging now ends exactly when its 30 ms guard expires (App/i2c_bus.c I2C_GUARD_MS,
   started with the read): completes (error = 0) or fails with an I2C error (error = 1). */
int h_complete_read_at_guard(int error) { return i2c_sim_complete_at_guard(error); }
