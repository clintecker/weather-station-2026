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
 *   failed read is not absence: the holder is present (section 6.7).
 *   Identity check (the pre-latch slot): a lane of its own beside the identification and the holder
 *   check. It begins from the driver's idle state as soon as no other job is past its start, and a
 *   job that has not begun waits for it; in the slot no other job begins at all. Each part ends as
 *   agreeing, changed or failed; the outcome is changed if any part changed, matched if a part agreed,
 *   else unverified. */
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
#define CRC_AT 0x7CU      /* the record's CRC-32C */
#define CRC_LEN 4U
#define ID_PORTS 3U       /* P_AIR_TH, P_PRESSURE, P_UVA: the port modules of the static channel map */

typedef enum { PI_IDLE, PI_WAIT, PI_REC, PI_SERIAL, PI_H_ID, PI_H_SHORT, PI_H_FULL, PI_H_SERIAL2, PI_DONE } pi_step;
typedef enum { JOB_IDENTIFY, JOB_HOLDER } pi_job;
/* The identity check's lane: its steps, and how each part ended. */
typedef enum { C_IDLE, C_WAIT, C_SERIAL, C_SERIAL2, C_SHORT_SERIAL, C_SHORT_CRC, C_FULL, C_FULL2, C_READ, C_IMG1, C_IMG2, C_DONE } pc_step;
typedef enum { PART_AGREES, PART_CHANGED, PART_FAILED, PART_PENDING } pc_part;   /* pending: its next read is out */
typedef struct {
  pi_step step;
  pi_job job;
  uint8_t tries, crc_reread, read_ok, has_serial, nacks, gone, serial_tries, incomplete;
  uint32_t sensor_serial;
  port_id_expect expect;
  uint8_t slot;
  /* The identity check: */
  pc_step cstep;
  uint8_t agreed, changed, c_has_serial, c_nack;
  uint32_t c_serial, c_img;     /* the sensor serial it read; the CRC-32C of its first full read (c_nack: it NACKed) */
  port_id_expect cexpect;
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
  /* The bus refuses only a busy client or a bad form; one step at a time on one lane makes neither. */
  enum i2c_client c = (enum i2c_client)((unsigned)I2C_C_REC_AIR + (unsigned)p - (unsigned)P_AIR_TH);
  s->word[0] = (uint8_t)(at >> BYTE_BITS);
  s->word[1] = (uint8_t)at;
  (void)WS_CHECK(i2c_bus_submit(c, REC_ADDR, s->word, WORD_LEN, s->img, len) == 0);
}

static int job_running(pi_step step) { return step != PI_IDLE && step != PI_DONE; }
static int check_running(pc_step step) { return step != C_IDLE && step != C_DONE; }
static int check_on_bus(pc_step step) { return step >= C_SHORT_SERIAL && step <= C_IMG2; }

/* The driver starts no new sample while a job waits or runs, or in the slot. */
static void update_hold(enum wsmp_port p)
{
  const pi_t *s = eng(p);
  local_hold(p, job_running(s->step) || check_running(s->cstep) || s->slot);
}

static void finish(enum wsmp_port p)
{
  eng(p)->step = PI_DONE;
  update_hold(p);
}

static void start(enum wsmp_port p, pi_job job)
{
  pi_t *s = eng(p);
  s->job = job; s->step = PI_WAIT;
  s->tries = s->crc_reread = s->read_ok = s->has_serial = s->nacks = s->gone = s->serial_tries = s->incomplete = 0;
  s->sensor_serial = 0;
  update_hold(p);
}

void port_id_slot(enum wsmp_port p, int on)
{
  eng(p)->slot = (uint8_t)(on != 0);
  update_hold(p);
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

static int check_tick(enum wsmp_port p);

/* 1 while the job has not begun: it begins from the driver's idle state, never in the slot. */
static int job_waits(enum wsmp_port p)
{
  if (eng(p)->step != PI_WAIT) return 0;
  if (!eng(p)->slot && local_idle(p)) begin_work(p);
  return 1;
}

void port_id_tick(enum wsmp_port p)
{
  pi_t *s = eng(p);
  uint32_t serial = 0;
  int r;
  if (check_tick(p) || job_waits(p)) return;   /* the identity check first: it has priority */
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

static void check_i2c_done(enum wsmp_port p, int rc);

void port_id_i2c_done(enum wsmp_port p, int rc)
{
  pi_step step = eng(p)->step;
  if (check_on_bus(eng(p)->cstep)) { check_i2c_done(p, rc); return; }
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

/* ---- The identity check (section 6.7, "Re-identification") ---- */

void port_id_check(enum wsmp_port p, const port_id_expect *e)
{
  pi_t *s = eng(p);
  if (!WS_CHECK(!check_running(s->cstep))) return;   /* one check a latch: the host asks once */
  s->cexpect = *e;
  s->cstep = C_WAIT;
  s->agreed = s->changed = s->c_has_serial = 0;
  update_hold(p);
}

int port_id_check_result(enum wsmp_port p)
{
  const pi_t *s = eng(p);
  if (s->cstep != C_DONE) return PORT_ID_CHECKING;
  if (s->changed) return PORT_ID_CHANGED;
  return s->agreed ? PORT_ID_MATCHED : PORT_ID_UNVERIFIED;
}

/* A check still running at the latch runs on (its bus transfer is out) and is forgotten at the next. */
void port_id_check_end(enum wsmp_port p)
{
  pi_t *s = eng(p);
  if (s->cstep == C_WAIT || s->cstep == C_DONE) s->cstep = C_IDLE;
  update_hold(p);
}

static void check_done(enum wsmp_port p)
{
  eng(p)->cstep = C_DONE;
  update_hold(p);
}

static void c_read(enum wsmp_port p, pc_step step, uint16_t at, uint16_t len)
{
  eng(p)->cstep = step;
  rec_read(p, at, len);
}

/* The record part, by the record status at admission. */
static void check_record(enum wsmp_port p)
{
  uint8_t status = eng(p)->cexpect.status;
  if (status == WSMP_REC_APPLIED || status == WSMP_REC_SENSOR_CHANGED) c_read(p, C_SHORT_SERIAL, SERIAL_AT, SERIAL_LEN);
  else if (status == WSMP_REC_READ) c_read(p, C_READ, 0, WSMP_RECORD_LEN);
  else c_read(p, C_IMG1, 0, WSMP_RECORD_LEN);
}

static void part(enum wsmp_port p, pc_part r)
{
  pi_t *s = eng(p);
  if (r == PART_AGREES) s->agreed = 1;
  if (r == PART_CHANGED) s->changed = 1;
}

static void check_begin(enum wsmp_port p)
{
  pi_t *s = eng(p);
  if (!s->cexpect.has_sensor_serial) { check_record(p); return; }
  s->cstep = C_SERIAL;
  local_id_check(p);
}

/* The sensor serial: a different one is read once more; two that agree on it are a change. A
   confirmed change needs no more parts. */
static void check_serial(enum wsmp_port p, int r, uint32_t serial)
{
  pi_t *s = eng(p);
  int differs = r == 1 && serial != s->cexpect.sensor_serial;
  if (s->cstep == C_SERIAL && differs) { s->c_serial = serial; s->cstep = C_SERIAL2; local_id_check(p); return; }
  if (s->cstep == C_SERIAL2 && differs && serial == s->c_serial) { part(p, PART_CHANGED); check_done(p); return; }
  if (r == 1 && !differs) { s->c_has_serial = 1; s->c_serial = serial; part(p, PART_AGREES); }
  check_record(p);
}

/* 1 while the check holds the engine (this tick is its own). */
static int check_tick(enum wsmp_port p)
{
  const pi_t *s = eng(p);
  uint32_t serial = 0;
  if (s->cstep == C_WAIT)
  {
    if (job_running(s->step) && s->step != PI_WAIT) return 0;   /* a job past its start finishes first */
    if (local_idle(p)) check_begin(p);
    return 1;
  }
  if (s->cstep != C_SERIAL && s->cstep != C_SERIAL2) return check_running(s->cstep);
  int r = local_id_result(p, &serial);
  if (r != 0) check_serial(p, r, serial);
  return 1;
}

/* Applied or SENSOR_CHANGED at admission: the 8-byte serial, then the CRC; a difference is confirmed
   by a full read that is structurally valid and names another serial or CRC. A full read that is not a
   valid record (blank, corrupt, or a NACK at 0x50) is read once more: two that agree with each other
   (the same image by its CRC-32C, or both NACKed) differ from the record admitted, a change; two that
   disagree, or another failure, are unverified. */
static pc_part same_full(const pi_t *s, int nack, uint32_t crc)
{
  return nack == s->c_nack && crc == s->c_img ? PART_CHANGED : PART_FAILED;
}

static pc_part valid_full(const pi_t *s, const wsmp_record *r)
{
  return r->serial != s->cexpect.serial || r->crc != s->cexpect.rec_crc ? PART_CHANGED : PART_AGREES;
}

static pc_part check_full(enum wsmp_port p, int rc)
{
  pi_t *s = eng(p);
  wsmp_record r;
  int nack = rc == I2C_ENACK_ADDR;
  if (rc != I2C_OK && !nack) return PART_FAILED;
  uint32_t crc = nack ? 0U : wsmp_crc32c(s->img, WSMP_RECORD_LEN);
  if (s->cstep == C_FULL2) return same_full(s, nack, crc);
  if (!nack && wsmp_record_parse(s->img, &r) == WSMP_REC_APPLIED) return valid_full(s, &r);
  s->c_nack = (uint8_t)nack; s->c_img = crc;
  c_read(p, C_FULL2, 0, WSMP_RECORD_LEN);
  return PART_PENDING;
}

static pc_part check_short(enum wsmp_port p, int rc)
{
  const pi_t *s = eng(p);
  if (s->cstep == C_FULL || s->cstep == C_FULL2) return check_full(p, rc);
  if (rc != I2C_OK) return PART_FAILED;
  if (s->cstep == C_SHORT_SERIAL)
  {
    if (ws_get_be64(s->img, SERIAL_LEN) != s->cexpect.serial) c_read(p, C_FULL, 0, WSMP_RECORD_LEN);
    else c_read(p, C_SHORT_CRC, CRC_AT, CRC_LEN);
    return PART_PENDING;
  }
  if (ws_get_be32(s->img) == s->cexpect.rec_crc) return PART_AGREES;
  c_read(p, C_FULL, 0, WSMP_RECORD_LEN);
  return PART_PENDING;
}

/* A content NO_RECORD or CAL_REJECTED at admission: the image's CRC-32C. A different one is read again;
   two that agree are parsed as at admission (steps 2-3c), a change if the verdict, status or serial
   differs. */
static pc_part check_image(enum wsmp_port p)
{
  pi_t *s = eng(p);
  uint32_t crc = wsmp_crc32c(s->img, WSMP_RECORD_LEN);
  wsmp_verdict v;
  if (s->cstep == C_IMG1)
  {
    if (crc == s->cexpect.img_crc) return PART_AGREES;
    s->c_img = crc;
    c_read(p, C_IMG2, 0, WSMP_RECORD_LEN);
    return PART_PENDING;
  }
  if (crc != s->c_img) return PART_FAILED;   /* two full reads that disagree: unverified */
  const wsmp_observed o = { .port = (uint8_t)p, .read_ok = 1, .has_sensor_serial = s->cexpect.has_sensor_serial,
                            .probed_type = local_type(p), .record = s->img,
                            .sensor_serial = s->c_has_serial ? s->c_serial : s->cexpect.sensor_serial };
  wsmp_identify(&o, NULL, 0, &v);
  int same = v.verdict == WSMP_V_ADMIT && v.status == s->cexpect.status && v.serial == s->cexpect.id_serial;
  return same ? PART_AGREES : PART_CHANGED;
}

/* READ at admission: a NACK at 0x50 agrees; a record that passes a full read is a change. */
static pc_part check_read(enum wsmp_port p, int rc)
{
  wsmp_record r;
  if (rc == I2C_ENACK_ADDR) return PART_AGREES;
  if (rc != I2C_OK) return PART_FAILED;
  return wsmp_record_parse(eng(p)->img, &r) == WSMP_REC_APPLIED ? PART_CHANGED : PART_FAILED;
}

static void check_i2c_done(enum wsmp_port p, int rc)
{
  pc_step was = eng(p)->cstep;
  pc_part r;
  if (was == C_READ) r = check_read(p, rc);
  else if (was != C_IMG1 && was != C_IMG2) r = check_short(p, rc);
  else if (rc != I2C_OK) r = PART_FAILED;
  else r = check_image(p);
  if (r == PART_PENDING) return;
  part(p, r);
  check_done(p);
}
