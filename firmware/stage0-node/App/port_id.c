/* The identity reads of an I2C port module (port_id.h). One engine for each port module, each with
 * its own record client (0x50 on the port's channel) and a 128-byte buffer. Each step is a bus
 * completion or a module tick; nothing waits.
 *   Identify: hold the driver, wait for its idle state, read the record (3 tries back to back on a
 *   transfer error; a CRC failure is read once more), then the sensor's serial as the driver's own
 *   step (the SHT45's 0x89, 3 tries back to back), then release the driver. A sensor serial that
 *   failed all 3 tries leaves the identification incomplete: a read error is not a verdict, so the
 *   host decides nothing and identifies again at the next probe slot.
 *   Holder check: hold, wait for idle, the driver's ID check (two address NACKs back to back: gone;
 *   another chip: gone), then, for a module admitted with a record, its serial at 0x0C (8 bytes); a
 *   different serial is confirmed by a full read that parses and names another serial. A sensor
 *   serial that differs is read once more: two reads that agree on another serial are gone. Any
 *   failed read is not absence: the holder is present (section 6.7). */
#define WS_CHECK_FILE 17
#include "port_id.h"
#include <string.h>
#include "i2c_bus.h"
#include "ws_be.h"
#include "ws_check.h"

#define REC_ADDR 0x50U
#define REC_TRIES 3U
#define SERIAL_TRIES 3U   /* the sensor serial (0x89), back to back like the record */
#define ID_NACKS 2U
#define SERIAL_AT 0x0CU   /* the record's serial (section 6.9) */
#define SERIAL_LEN 8U
#define WORD_LEN 2U
#define BYTE_BITS 8U
#define ID_PORTS 3U       /* P_AIR_TH, P_PRESSURE, P_UVA: the port modules of the static channel map */

typedef enum { PI_IDLE, PI_WAIT, PI_REC, PI_SERIAL, PI_H_ID, PI_H_SHORT, PI_H_FULL, PI_H_SERIAL2, PI_DONE } pi_step;
typedef enum { JOB_IDENTIFY, JOB_HOLDER } pi_job;
typedef struct {
  pi_step step;
  pi_job job;
  uint8_t tries, crc_reread, read_ok, has_serial, nacks, gone, serial_tries, incomplete;
  uint32_t sensor_serial;
  port_id_expect expect;
  uint8_t word[WORD_LEN];
  uint8_t img[WSMP_RECORD_LEN];
} pi_t;

static pi_t pi[ID_PORTS];

int port_id_is_port(enum wsmp_port p) { return p >= P_AIR_TH && p <= P_UVA; }
static pi_t *eng(enum wsmp_port p) { return &pi[(unsigned)p - (unsigned)P_AIR_TH]; }

void port_id_init(void) { memset(pi, 0, sizeof pi); }

static void rec_read(enum wsmp_port p, uint16_t at, uint16_t len)
{
  pi_t *s = eng(p);
  enum i2c_client c = (enum i2c_client)((unsigned)I2C_C_REC_AIR + (unsigned)p - (unsigned)P_AIR_TH);
  s->word[0] = (uint8_t)(at >> BYTE_BITS);
  s->word[1] = (uint8_t)at;
  /* The bus refuses only a busy client or a bad form; one step at a time makes neither. */
  (void)WS_CHECK(i2c_bus_submit(c, REC_ADDR, s->word, WORD_LEN, s->img, len) == 0);
}

static void finish(enum wsmp_port p)
{
  eng(p)->step = PI_DONE;
  local_hold(p, 0);
}

static void start(enum wsmp_port p, pi_job job)
{
  pi_t *s = eng(p);
  s->job = job; s->step = PI_WAIT;
  s->tries = s->crc_reread = s->read_ok = s->has_serial = s->nacks = s->gone = s->serial_tries = s->incomplete = 0;
  s->sensor_serial = 0;
  local_hold(p, 1);
}

void port_id_identify(enum wsmp_port p) { start(p, JOB_IDENTIFY); }

void port_id_holder(enum wsmp_port p, const port_id_expect *e)
{
  start(p, JOB_HOLDER);
  eng(p)->expect = *e;
}

static void begin_work(enum wsmp_port p)
{
  pi_t *s = eng(p);
  if (s->job == JOB_IDENTIFY) { s->step = PI_REC; rec_read(p, 0, WSMP_RECORD_LEN); return; }
  s->step = PI_H_ID;
  local_id_check(p);
}

static void after_record(enum wsmp_port p)
{
  if (!local_has_sensor_serial(p)) { finish(p); return; }
  eng(p)->step = PI_SERIAL;
  local_id_check(p);
}

/* The record read: a transfer error is tried again back to back (3 tries); a CRC failure once more. */
static void rec_done(enum wsmp_port p, int rc)
{
  pi_t *s = eng(p);
  wsmp_record r;
  if (rc != I2C_OK)
  {
    if (++s->tries < REC_TRIES) { rec_read(p, 0, WSMP_RECORD_LEN); return; }
    s->read_ok = 0;
    after_record(p);
    return;
  }
  if (!s->crc_reread && wsmp_record_parse(s->img, &r) == WSMP_REC_CRC) { s->crc_reread = 1; rec_read(p, 0, WSMP_RECORD_LEN); return; }
  s->read_ok = 1;
  after_record(p);
}

/* The holder's sensor serial: one that differs is read once more. */
static void holder_serial(enum wsmp_port p)
{
  const pi_t *s = eng(p);
  if (!s->expect.has_sensor_serial || !local_has_sensor_serial(p) || s->sensor_serial == s->expect.sensor_serial)
  {
    finish(p);
    return;
  }
  eng(p)->step = PI_H_SERIAL2;
  local_id_check(p);
}

static void holder_id(enum wsmp_port p, int r, uint32_t serial)
{
  pi_t *s = eng(p);
  if (r == I2C_ENACK_ADDR && ++s->nacks < ID_NACKS) { local_id_check(p); return; }   /* back to back */
  if (r == I2C_ENACK_ADDR || r == I2C_EID) { s->gone = 1; finish(p); return; }
  if (r != 1) { finish(p); return; }   /* a failed read: present, unverified */
  s->sensor_serial = serial;
  if (!s->expect.with_record) { holder_serial(p); return; }
  s->step = PI_H_SHORT;
  rec_read(p, SERIAL_AT, SERIAL_LEN);
}

/* The identification's sensor serial: a failed read is tried again back to back (3 tries); after the
   third the identification is incomplete, not a verdict. */
static void serial_done(enum wsmp_port p, int r, uint32_t serial)
{
  pi_t *s = eng(p);
  if (r != 1 && ++s->serial_tries < SERIAL_TRIES) { local_id_check(p); return; }
  s->has_serial = r == 1; s->sensor_serial = serial; s->incomplete = r != 1;
  finish(p);
}

static int waits_on_driver(pi_step step) { return step == PI_SERIAL || step == PI_H_ID || step == PI_H_SERIAL2; }

void port_id_tick(enum wsmp_port p)
{
  pi_t *s = eng(p);
  uint32_t serial = 0;
  int r;
  if (s->step == PI_WAIT) { if (local_idle(p)) begin_work(p); return; }
  if (!waits_on_driver(s->step)) return;
  r = local_id_result(p, &serial);
  if (r == 0) return;   /* the driver's step still runs */
  if (s->step == PI_H_ID) { holder_id(p, r, serial); return; }
  if (s->step == PI_SERIAL) { serial_done(p, r, serial); return; }
  s->gone = r == 1 && serial == s->sensor_serial && serial != s->expect.sensor_serial;   /* PI_H_SERIAL2 */
  finish(p);
}

static void holder_record_done(enum wsmp_port p, int rc)
{
  pi_t *s = eng(p);
  wsmp_record r;
  if (rc != I2C_OK) { finish(p); return; }   /* present, unverified */
  if (s->step == PI_H_SHORT)
  {
    if (ws_get_be64(s->img, SERIAL_LEN) == s->expect.serial) { holder_serial(p); return; }
    s->step = PI_H_FULL;   /* a different serial: confirmed only by a whole record that names it */
    rec_read(p, 0, WSMP_RECORD_LEN);
    return;
  }
  s->gone = wsmp_record_parse(s->img, &r) == WSMP_REC_APPLIED && r.serial != s->expect.serial;
  finish(p);
}

void port_id_i2c_done(enum wsmp_port p, int rc)
{
  pi_step step = eng(p)->step;
  if (step == PI_REC) rec_done(p, rc);
  else if (WS_CHECK(step == PI_H_SHORT || step == PI_H_FULL)) holder_record_done(p, rc);
}

int port_id_state(enum wsmp_port p)
{
  pi_step step = eng(p)->step;
  return step == PI_DONE || step == PI_IDLE ? PORT_ID_DONE : PORT_ID_BUSY;
}

void port_id_observed(enum wsmp_port p, wsmp_observed *o)
{
  const pi_t *s = eng(p);
  *o = (wsmp_observed){ .port = (uint8_t)p, .read_ok = s->read_ok, .has_sensor_serial = s->has_serial,
                        .probed_type = local_type(p), .record = s->img, .sensor_serial = s->sensor_serial };
}

int port_id_incomplete(enum wsmp_port p) { return eng(p)->incomplete; }

int port_id_holder_result(enum wsmp_port p) { return eng(p)->gone ? PORT_ID_GONE : PORT_ID_PRESENT; }
