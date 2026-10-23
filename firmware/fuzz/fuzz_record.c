/* The module record v1.0 (firmware/common/wsmp.c), its calibration check (wsmp_cal.c) and the
 * admission verdict (wsmp_ident.c), driven with arbitrary EEPROM contents.
 * Input: byte 0 bit 0 set seals the record (writes a good CRC, so the structural and calibration
 * checks are reached); bytes 1-128 are the record (padded with zero); the next 8 bytes give the
 * verdict's probe: probed type, port, sensor-serial flag and value, and one holder on another port.
 * Properties, checked against an independent reading of
 * docs/superpowers/specs/2026-10-21-sensor-module-ports-design.md sections 6.7 and 6.9:
 *  - wsmp_record_parse returns exactly the status of the spec's ordered checks 2-6;
 *  - wsmp_cal_check accepts exactly the entries the frozen table allows (check 7: a table quantity, a
 *    (quantity, kind) that is a channel of the type or kind 0 over one, revision not 0, within bounds);
 *  - an accepted minor-0 record packs back to the same bytes; any accepted record packs to one that
 *    parses again;
 *  - the verdict's serial namespace is its source, id_flags is source and status, record_crc is the
 *    record's CRC exactly when the record is applied (valid, of the probed type, its bind confirmed,
 *    its calibration accepted) and 0 otherwise, and a quarantine is exactly a valid record of another type;
 *  - no memory error (ASan/UBSan). */
#include <string.h>
#include "fuzz.h"
#include "wsmp.h"
#include "wsmp_cal.h"
#include "wsmp_ident.h"

#define SPEC_LEN 128U
#define SPEC_CRC_AT 124U
#define SPEC_CAL_AT 64U
#define SPEC_ENTRY 16U
#define SPEC_ENTRIES 3U
#define SPEC_TYPES 7U
#define SPEC_WSMP_KIND_MAX 10U
#define SPEC_PART_AT 32U
#define SPEC_PART 16U
enum { S_APPLIED, S_READ, S_BLANK, S_NO_MAGIC, S_VERSION, S_MALFORMED, S_CRC, S_CAL_REJECTED, S_SENSOR_CHANGED };

/* WSMP section 4.4 again: each module type's channels as quantity and kind pairs (0, 0 ends a list). */
static const uint8_t spec_channels[SPEC_TYPES][8][2] = {
  { { 1, 2 }, { 2, 2 } }, { { 3, 2 } }, { { 8, 2 } }, { { 1, 2 }, { 2, 2 } },
  { { 9, 2 }, { 11, 6 }, { 12, 6 }, { 13, 6 }, { 14, 6 }, { 15, 1 }, { 16, 10 } },
  { { 17, 6 }, { 5, 7 }, { 6, 8 }, { 6, 9 } }, { { 7, 6 } } };
/* Section 6.9, check 6: the one module type whose part has a serial to bind (kind 1), the SHT4x. */
#define SPEC_SERIAL_TYPE 1U
/* Section 6.9's table: quantity, offset bound, gain min, gain max. */
static const uint32_t spec_cal[4][4] = { { 1, 200, 980000, 1020000 }, { 2, 1000, 900000, 1100000 },
                                         { 3, 50, 990000, 1010000 }, { 8, 16, 100000, 10000000 } };

static uint32_t be(const uint8_t *p, unsigned n)
{
  uint32_t v = 0;
  for (unsigned i = 0; i < n; i++) v = v << 8 | p[i];
  return v;
}

static int all(const uint8_t *p, unsigned n, uint8_t v)
{
  for (unsigned i = 0; i < n; i++)
    if (p[i] != v) return 0;
  return 1;
}

/* CRC-32C, reflected 0x82F63B78, written out again (a nibble at a time, unlike wsmp.c). */
static uint32_t spec_crc(const uint8_t *p, unsigned n)
{
  uint32_t crc = 0xFFFFFFFFU;
  for (unsigned i = 0; i < 2 * n; i++)
  {
    crc ^= (uint32_t)(i % 2 ? p[i / 2] >> 4 : p[i / 2] & 0x0FU);
    for (unsigned b = 0; b < 4; b++) crc = crc & 1U ? (crc >> 1) ^ 0x82F63B78U : crc >> 1;
  }
  return ~crc;
}

static int spec_char(uint8_t c)
{
  return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == ' ' || c == '.' || c == '_' || c == '-';
}

static int spec_part(const uint8_t *p)
{
  int ended = 0;
  for (unsigned i = 0; i < SPEC_PART; i++)
  {
    if (!p[i]) ended = 1;
    else if (ended || !spec_char(p[i])) return 0;
  }
  return 1;
}

static int spec_entries(const uint8_t *r, int minor0)
{
  for (unsigned e = 0; e < SPEC_ENTRIES; e++)
  {
    const uint8_t *p = r + SPEC_CAL_AT + e * SPEC_ENTRY;
    if (all(p, SPEC_ENTRY, 0)) continue;
    if (p[2] > SPEC_WSMP_KIND_MAX || (minor0 && (p[3] || p[6] || p[7]))) return 0;
  }
  return 1;
}

static int spec_structure(const uint8_t *r)
{
  unsigned type = be(r + 8, 2), kind = r[20];
  int minor0 = r[5] == 0;
  if (r[12] != 1 || all(r + 13, 7, 0) || all(r + 13, 7, 0xFF)) return 0;
  if (type < 1 || type > SPEC_TYPES || kind > 1 || (kind == 0 && be(r + 24, 4)) || (type == SPEC_SERIAL_TYPE) != (kind == 1)) return 0;
  if (!spec_part(r + SPEC_PART_AT)) return 0;
  if (minor0 && (r[11] || !all(r + 21, 3, 0) || !all(r + 48, 16, 0) || !all(r + 112, 12, 0))) return 0;
  return spec_entries(r, minor0);
}

static int spec_status(const uint8_t *r)
{
  if (all(r, SPEC_LEN, 0xFF)) return S_BLANK;
  if (memcmp(r, "WSMR", 4) != 0) return S_NO_MAGIC;
  if (r[4] != 1) return S_VERSION;
  if (be(r + 6, 2) != SPEC_LEN) return S_MALFORMED;
  if (spec_crc(r, SPEC_CRC_AT) != be(r + SPEC_CRC_AT, 4)) return S_CRC;
  return spec_structure(r) ? S_APPLIED : S_MALFORMED;
}

/* An entry is used unless its fields (not its reserved bytes) are all zero. */
static int spec_used(const uint8_t *p) { return !all(p, 3, 0) || !all(p + 4, 2, 0) || !all(p + 8, 8, 0); }

static int spec_entry_ok(const uint8_t *p, unsigned type)
{
  unsigned q = be(p, 2), k = p[2], revision = be(p + 4, 2);
  int32_t offset = (int32_t)be(p + 8, 4);
  uint32_t gain = be(p + 12, 4);
  int in_type = 0;
  for (unsigned i = 0; i < 8; i++)
    in_type |= q != 0 && spec_channels[type - 1][i][0] == q && (k == 0 || spec_channels[type - 1][i][1] == k);
  if (revision == 0) return 0;   /* 0 is an uncorrected channel's revision */
  for (unsigned i = 0; i < 4; i++)
    if (spec_cal[i][0] == q)
      return in_type && offset >= -(int32_t)spec_cal[i][1] && offset <= (int32_t)spec_cal[i][1] && gain >= spec_cal[i][2] &&
             gain <= spec_cal[i][3];
  return 0;
}

static int spec_cal_ok(const uint8_t *r)
{
  for (unsigned e = 0; e < SPEC_ENTRIES; e++)
  {
    const uint8_t *p = r + SPEC_CAL_AT + e * SPEC_ENTRY;
    if (!spec_used(p)) continue;
    if (!spec_entry_ok(p, be(r + 8, 2))) return 0;
    for (unsigned d = 0; d < e; d++)
    {
      const uint8_t *o = r + SPEC_CAL_AT + d * SPEC_ENTRY;
      if (spec_used(o) && memcmp(o, p, 3) == 0) return 0;   /* the same quantity and kind */
    }
  }
  return 1;
}

static void verdict(const uint8_t *r, const uint8_t *probe, int status, int cal_ok)
{
  const wsmp_observed o = { .port = (uint8_t)(1U + probe[1] % 8U), .read_ok = (uint8_t)(probe[2] & 1U),
                            .has_sensor_serial = (uint8_t)((probe[2] >> 1) & 1U), .probed_type = (uint16_t)(1U + probe[0] % SPEC_TYPES),
                            .record = r, .sensor_serial = be(probe + 3, 4) };
  const wsmp_port_held h = { .port = (uint8_t)(1U + probe[7] % 8U), .holding = 1, .type = (uint16_t)(1U + probe[7] % SPEC_TYPES),
                             .serial = be(r + 12, 4) == 0 ? 1U : (uint64_t)be(r + 12, 4) << 32 | be(r + 16, 4) };
  wsmp_verdict v;
  wsmp_identify(&o, &h, 1, &v);
  FUZZ_CHECK(v.id_flags == (v.source | v.status << 4));
  FUZZ_CHECK(v.serial >> 56 == v.source && v.serial != 0);
  int conflict = o.read_ok && status == S_APPLIED && be(r + 8, 2) != o.probed_type;
  int bound = r[20] == 0 || (o.has_sensor_serial && o.sensor_serial == be(r + 24, 4));
  int applied = o.read_ok && status == S_APPLIED && !conflict && bound && cal_ok;
  FUZZ_CHECK(v.record_crc == (applied ? be(r + SPEC_CRC_AT, 4) : 0U));
  FUZZ_CHECK((v.status == S_APPLIED && !conflict) == applied);
  FUZZ_CHECK((v.verdict == WSMP_V_TYPE_CONFLICT) == conflict);
  if (!o.read_ok) FUZZ_CHECK(v.status == S_READ && v.source != WSMP_SRC_RECORD);
  if (v.verdict == WSMP_V_DUP_SERIAL) FUZZ_CHECK(v.serial == h.serial && v.holder_port == h.port && h.port != o.port);
  if (v.verdict == WSMP_V_DUP_TYPE) FUZZ_CHECK(o.probed_type == h.type && v.holder_port == h.port && h.port != o.port);
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
  uint8_t in[SPEC_LEN + 8] = { 0 }, back[SPEC_LEN];
  wsmp_record r;
  if (size == 0) return 0;
  memcpy(in, data + 1, size - 1 < sizeof in ? size - 1 : sizeof in);
  if (data[0] & 1U)
  {
    uint32_t crc = spec_crc(in, SPEC_CRC_AT);
    for (unsigned i = 0; i < 4; i++) in[SPEC_CRC_AT + i] = (uint8_t)(crc >> (24 - 8 * i));
  }
  int status = spec_status(in);
  int cal_ok = status == S_APPLIED && spec_cal_ok(in);
  FUZZ_CHECK(wsmp_record_parse(in, &r) == status);
  if (status == S_APPLIED)
  {
    FUZZ_CHECK((wsmp_cal_check(&r) == S_APPLIED) == cal_ok);
    wsmp_record_pack(&r, back);
    if (in[5] == 0) FUZZ_CHECK(memcmp(back, in, SPEC_LEN) == 0);
    FUZZ_CHECK(wsmp_record_parse(back, &r) == S_APPLIED);
  }
  verdict(in, in + SPEC_LEN, status, cal_ok);
  return 0;
}
