/* GENERATED from sensor.lit.md by tools/tangle.py: do not edit. Edit the document, then run
 * tools/tangle.py firmware/stage0-node/App/sensor.lit.md (tests/test_tangle.py checks this file). */
#define WS_CHECK_FILE 6
#include "sensor.h"
#include <stddef.h>
#include "busymon.h"
#include "i2c_bus.h"
#include "stage0.h"
#include "stm32_seq.h"
#include "stm32_timer.h"
#include "utilities_def.h"
#include "ws_check.h"

typedef enum { S_IDLE, S_CMD, S_MEASURE, S_READ, S_RECOVER } sensor_state;
static sensor_state st = S_IDLE;
static uint8_t reply[WS_SHT45_REPLY_LEN];
static UTIL_TIMER_Object_t measure_timer;
static const uint8_t command[1] = { WS_SHT45_MEASURE };

static void submit(const uint8_t *tx, uint8_t txlen, uint8_t *rx, uint8_t rxlen)
{
  /* The bus refuses only a busy client or a bad form; this file never makes either. */
  (void)WS_CHECK(i2c_bus_submit(I2C_C_SHT45, WS_SHT45_ADDR, tx, txlen, rx, rxlen) == 0);
}

int sensor_start(void)
{
  if (st != S_IDLE) return -1;
  st = S_CMD;
  submit(command, sizeof command, NULL, 0);
  return 0;
}

static void on_measured(void *ctx) { (void)ctx; UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Sensor, CFG_SEQ_Prio_0); }

static void sensor_task(void)
{
  if (st != S_MEASURE) return;
  st = S_READ;
  submit(NULL, 0, reply, sizeof reply);
}
BUSYMON_TASK(sensor_task)

static int failed_rc;   /* the code that a recovery after a CRC mismatch reports */

static void report(int rc, int16_t t, uint16_t h)
{
  st = S_IDLE;
  sensor_done(rc, t, h);
}

static void read_done(int rc)
{
  int16_t t = 0; uint16_t h = 0;
  if (rc) { report(rc, 0, 0); return; }
  rc = ws_sht45_parse(reply, &t, &h);
  if (rc == 0) { report(0, t, h); return; }
  failed_rc = rc;
  st = S_RECOVER;
  submit(NULL, 0, NULL, 0);
}

void i2c_bus_done(enum i2c_client c, int rc)
{
  if (!WS_CHECK(c == I2C_C_SHT45)) return;
  if (st == S_CMD && rc == 0) { st = S_MEASURE; (void)WS_CHECK(UTIL_TIMER_Start(&measure_timer) == UTIL_TIMER_OK); }
  else if (st == S_CMD) report(rc, 0, 0);
  else if (st == S_READ) read_done(rc);
  else if (WS_CHECK(st == S_RECOVER)) report(rc ? SENSOR_BUS_STUCK : failed_rc, 0, 0);
}

void sensor_init(void)
{
  (void)UTIL_TIMER_Create(&measure_timer, WS_SHT45_MEASURE_MS, UTIL_TIMER_ONESHOT, on_measured, NULL);
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Sensor, UTIL_SEQ_RFU, sensor_task_timed);
  i2c_bus_init();
}
