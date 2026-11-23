/* PODWRITE (pod_write.h): one job at a time, on one port's record client. Each step is a module tick or a
 * bus completion; nothing waits.
 *   PW_S_WAIT    port_id_lock is on; waits until no identity read is past its start and the driver is idle
 *   PW_S_READ    the 128-byte record (3 tries back to back): a valid record there is refused
 *   PW_S_SERIAL  the sensor serial, as the driver's own step (the SHT45's 0x89, 3 tries back to back)
 *   PW_S_PAGE    one 32-byte page write: the word address and 32 bytes
 *   PW_S_POLL    acknowledge polling: a 1-byte read that the 24LC32 NACKs while its write cycle runs
 *                (5 ms at most, from its datasheet); POLL_MAX back to back, then a timeout
 *   PW_S_VERIFY  the 128 bytes read back (3 tries), byte for byte against the image, then parsed */
#define WS_CHECK_FILE 20
#include "pod_write.h"
#include <string.h>
#include "i2c_bus.h"
#include "port_id.h"
#include "ws_be.h"
#include "ws_check.h"
#include "ws_console.h"

#define REC_ADDR 0x50U
#define PAGE_LEN 32U                  /* the 24LC32's write page */
#define PAGES (WSMP_RECORD_LEN / PAGE_LEN)
#define WORD_LEN 2U
#define BYTE_BITS 8U
#define TRIES 3U                      /* reads and the sensor serial, back to back, as port_id.c */
#define POLL_MAX 32U                  /* a poll is a mux select, a read and a deselect: 32 cover 5 ms many times */
#define SERIAL_NS 0x01U               /* a programmed record's serial namespace (section 6.7) */
#define NS_SHIFT 56U
#define SERIAL_LOW 0x00FFFFFFFFFFFFFFULL
#define DEC_DIGITS 5U                 /* a port or a type: up to 65535 */
#define SERIAL_HEX 16U

typedef enum { PW_S_IDLE, PW_S_WAIT, PW_S_READ, PW_S_SERIAL, PW_S_PAGE, PW_S_POLL, PW_S_VERIFY } pw_step;

static struct {
  pw_step step;
  enum wsmp_port port;
  uint8_t tries, page, polls, poll_byte;
  uint32_t utc;
  pod_write_result res;
  uint8_t buf[WORD_LEN + PAGE_LEN];   /* a page write; also the word address of a read */
  uint8_t back[WSMP_RECORD_LEN];      /* what the EEPROM holds */
} pw;

/* ---- the console arguments ---- */

static const char *parse_dec(const char *p, unsigned max, unsigned *out)
{
  unsigned v = 0, n = 0;
  while (n < DEC_DIGITS && p[n] >= '0' && p[n] <= '9') { v = v * 10U + (unsigned)(p[n] - '0'); n++; }   /* bound: DEC_DIGITS */
  if (n == 0 || (p[n] >= '0' && p[n] <= '9') || v > max) return NULL;
  *out = v;
  return p + n;
}

static const char *parse_serial(const char *p, uint64_t *out)
{
  uint8_t b[SERIAL_HEX / WS_HEX_PER_BYTE];
  for (unsigned i = 0; i < sizeof b; i++)   /* bound: 8 bytes */
  {
    int v = ws_hex_byte(p + WS_HEX_PER_BYTE * i);
    if (v < 0) return NULL;
    b[i] = (uint8_t)v;
  }
  *out = ws_get_be64(b, sizeof b);
  return p + SERIAL_HEX;
}

int pod_write_parse(const char *args, unsigned *port, unsigned *type, uint64_t *serial)
{
  const char *p = parse_dec(args, P_COUNT - 1U, port);
  if (p && *p++ == ' ') p = parse_dec(p, UINT16_MAX, type); else p = NULL;
  if (p && *p++ == ' ') p = parse_serial(p, serial); else p = NULL;
  if (!p || *p++ != ' ') return -1;
  return strcmp(p, POD_WRITE_CONFIRM) == 0 ? 0 : -1;
}

/* ---- the job ---- */

static enum i2c_client client(void) { return port_id_client(pw.port); }

static void finish(uint8_t outcome)
{
  pw.res.outcome = outcome;
  pw.step = PW_S_IDLE;
  port_id_lock(pw.port, 0);
  pod_write_report(&pw.res);
}

static void read_record(pw_step step)
{
  pw.step = step;
  pw.buf[0] = 0; pw.buf[1] = 0;
  /* The bus refuses only a busy client or a bad form; the job's one step at a time makes neither. */
  (void)WS_CHECK(i2c_bus_submit(client(), REC_ADDR, pw.buf, WORD_LEN, pw.back, WSMP_RECORD_LEN) == 0);
}

static void write_page(void)
{
  uint16_t at = (uint16_t)(pw.page * PAGE_LEN);
  pw.step = PW_S_PAGE;
  pw.buf[0] = (uint8_t)(at >> BYTE_BITS); pw.buf[1] = (uint8_t)at;
  memcpy(pw.buf + WORD_LEN, pw.res.image + at, PAGE_LEN);
  (void)WS_CHECK(i2c_bus_submit(client(), REC_ADDR, pw.buf, WORD_LEN + PAGE_LEN, NULL, 0) == 0);
}

static void poll(void)
{
  pw.step = PW_S_POLL;
  pw.buf[0] = 0; pw.buf[1] = 0;
  (void)WS_CHECK(i2c_bus_submit(client(), REC_ADDR, pw.buf, WORD_LEN, &pw.poll_byte, 1) == 0);
}

static const char *part_of(uint16_t type)
{
  if (type == WSMP_T_AIR_TH) return "WS-POD-TH-R1";
  return type == WSMP_T_PRESSURE ? "WS-POD-BARO-R1" : "WS-POD-UV-R1";
}

/* The record, packed: no calibration (a measured correction is a later write that keeps the serial). */
static void build_and_write(uint32_t bind_value)
{
  wsmp_record r;
  const char *part = part_of(pw.res.type);
  memset(&r, 0, sizeof r);
  r.type = pw.res.type; r.hw_rev = POD_WRITE_HW_REV; r.serial = pw.res.serial; r.programmed = pw.utc;
  r.bind_kind = local_has_sensor_serial(pw.port) ? WSMP_BIND_SHT4X : WSMP_BIND_NONE;
  r.bind_value = bind_value;
  memcpy(r.part, part, strlen(part));
  wsmp_record_pack(&r, pw.res.image);
  pw.res.bind_value = bind_value;
  pw.res.crc = ws_get_be32(pw.res.image + WSMP_RECORD_LEN - sizeof(uint32_t));
  /* pod_write_start checked the serial and the type, so the station's own parse must pass. */
  if (!WS_CHECK(wsmp_record_parse(pw.res.image, &r) == WSMP_REC_APPLIED)) { finish(PW_WRITE); return; }
  pw.page = 0;
  write_page();
}

static void serial_step(void)
{
  pw.tries = 0;
  pw.step = PW_S_SERIAL;
  local_id_check(pw.port);
}

/* The record there now: a read error is tried again; a valid record is refused, anything else is
   written over (blank, the breakout's factory bytes, a broken record). */
static void read_done(int rc)
{
  wsmp_record r;
  if (rc != I2C_OK) { if (++pw.tries < TRIES) read_record(PW_S_READ); else finish(PW_NO_EEPROM); return; }
  if (wsmp_record_parse(pw.back, &r) == WSMP_REC_APPLIED) { finish(PW_HAS_RECORD); return; }
  if (local_has_sensor_serial(pw.port)) serial_step();
  else build_and_write(0);
}

static void page_done(int rc)
{
  if (rc != I2C_OK) { finish(PW_WRITE); return; }
  pw.polls = 0;
  poll();
}

/* A NACK of the address: the write cycle still runs. Anything else after a NACK-free poll: the page is in. */
static void poll_done(int rc)
{
  if (rc == I2C_ENACK_ADDR) { if (++pw.polls < POLL_MAX) poll(); else finish(PW_TIMEOUT); return; }
  if (rc != I2C_OK) { finish(PW_WRITE); return; }
  if (++pw.page < PAGES) { write_page(); return; }
  pw.tries = 0;
  read_record(PW_S_VERIFY);
}

static void verify_done(int rc)
{
  wsmp_record r;
  if (rc != I2C_OK) { if (++pw.tries < TRIES) read_record(PW_S_VERIFY); else finish(PW_VERIFY); return; }
  int same = memcmp(pw.back, pw.res.image, WSMP_RECORD_LEN) == 0;
  finish(same && wsmp_record_parse(pw.back, &r) == WSMP_REC_APPLIED ? PW_OK : PW_VERIFY);
}

void pod_write_i2c_done(enum wsmp_port p, int rc)
{
  if (!WS_CHECK(pod_write_owns(p))) return;
  switch (pw.step)
  {
    case PW_S_READ: read_done(rc); break;
    case PW_S_PAGE: page_done(rc); break;
    case PW_S_POLL: poll_done(rc); break;
    default: verify_done(rc); break;   /* PW_S_VERIFY: pod_write_owns holds no other step on the bus */
  }
}

void pod_write_tick(enum wsmp_port p)
{
  uint32_t serial = 0;
  int r;
  if (pw.step == PW_S_IDLE || p != pw.port) return;
  if (pw.step == PW_S_WAIT)
  {
    if (port_id_quiet(p) && local_idle(p)) { pw.tries = 0; read_record(PW_S_READ); }
    return;
  }
  if (pw.step != PW_S_SERIAL) return;
  r = local_id_result(p, &serial);
  if (r == 0) return;   /* the driver's step still runs */
  if (r == 1) { build_and_write(serial); return; }
  if (++pw.tries < TRIES) local_id_check(p);
  else finish(PW_NO_SERIAL);
}

int pod_write_busy(void) { return pw.step != PW_S_IDLE; }

int pod_write_owns(enum wsmp_port p)
{
  return p == pw.port && pw.step != PW_S_IDLE && pw.step != PW_S_WAIT && pw.step != PW_S_SERIAL;
}

static int serial_ok(uint64_t s)
{
  uint64_t low = s & SERIAL_LOW;
  return (s >> NS_SHIFT) == SERIAL_NS && low != 0 && low != SERIAL_LOW;
}

int pod_write_start(enum wsmp_port p, uint16_t type, uint64_t serial, uint32_t utc)
{
  if (pod_write_busy()) return PW_START_BUSY;
  if (!port_id_is_port(p)) return PW_START_PORT;
  if (type != local_type(p)) return PW_START_TYPE;
  if (!serial_ok(serial)) return PW_START_SERIAL;
  memset(&pw, 0, sizeof pw);
  pw.port = p; pw.utc = utc; pw.step = PW_S_WAIT;
  pw.res.port = (uint8_t)p; pw.res.type = type; pw.res.serial = serial;
  port_id_lock(p, 1);
  return PW_START_OK;
}
