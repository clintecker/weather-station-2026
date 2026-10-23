/* GENERATED from wsmp.lit.md by tools/tangle.py: do not edit. Edit the document, then run
 * tools/tangle.py firmware/common/wsmp.lit.md (tests/test_tangle.py checks this file). */
#include "wsmp.h"
#include <string.h>
#include "ws_be.h"

#define DESC_WIDTH_SHIFT 5U
#define DESC_WIDTH_MASK  0x07U
#define DESC_SIGNED_BIT  0x10U
#define DESC_RESERVED    0x0FU
#define BYTE_BITS        8U
#define QUALITY_BITS     2U
#define CRC32C_POLY      0x82F63B78UL   /* the reflected Castagnoli polynomial */
#define CRC32C_INIT      0xFFFFFFFFUL
#define TEXT_PAD         0U
#define ID_FLAGS_RESERVED 0xFF0CU   /* identity flags: bits 2-3 and 8-15 */

void wsmp_pack_identity(const wsmp_identity *id, uint8_t out[WSMP_IDENTITY_LEN])
{
  uint8_t *p = ws_write_be16(out, WSMP_MAGIC);
  p = ws_write_u8(p, WSMP_VERSION_MAJOR);
  p = ws_write_u8(p, WSMP_VERSION_MINOR);
  p = ws_write_be16(p, id->type);
  p = ws_write_u8(p, id->schema);
  p = ws_write_u8(p, id->channels);
  p = ws_write_be(p, id->serial, sizeof id->serial);
  p = ws_write_u8(p, id->fw_major);
  p = ws_write_u8(p, id->fw_minor);
  p = ws_write_be16(p, id->fw_build);
  p = ws_write_be32(p, id->boot_id);
  p = ws_write_be16(p, id->caps);
  p = ws_write_be32(p, id->desc_digest);
  (void)ws_write_be16(p, id->id_flags);
}

int wsmp_unpack_identity(const uint8_t in[WSMP_IDENTITY_LEN], wsmp_identity *id)
{
  uint32_t v;
  uint64_t serial;
  if (ws_get_be16(in) != WSMP_MAGIC) return WSMP_EMAGIC;
  if (in[2] != WSMP_VERSION_MAJOR) return WSMP_EVERSION;
  id->type = ws_get_be16(in + 4);
  id->schema = in[6];
  id->channels = in[7];
  (void)ws_read_be(in + 8, &serial, sizeof serial);
  id->serial = serial;
  id->fw_major = in[16];
  id->fw_minor = in[17];
  id->fw_build = ws_get_be16(in + 18);
  (void)ws_read_be32(in + 20, &v);
  id->boot_id = v;
  id->caps = ws_get_be16(in + 24);
  (void)ws_read_be32(in + 26, &v);
  id->desc_digest = v;
  id->id_flags = ws_get_be16(in + 30);
  if (id->channels == 0 || id->channels > WSMP_MAX_CHANNELS || id->serial == 0) return WSMP_ELEN;
  if ((id->id_flags & ID_FLAGS_RESERVED) != 0) return WSMP_ERESERVED;
  return WSMP_OK;
}

void wsmp_pack_desc(const wsmp_desc *d, unsigned n, uint8_t out[WSMP_DESC_BLOCK_LEN])
{
  memset(out, 0, WSMP_DESC_BLOCK_LEN);
  uint8_t *p = out;
  for (unsigned i = 0; i < n && i < WSMP_MAX_CHANNELS; i++)
  {
    uint8_t form = (uint8_t)(((d[i].width - 1U) & DESC_WIDTH_MASK) << DESC_WIDTH_SHIFT);
    if (d[i].is_signed) form |= DESC_SIGNED_BIT;
    p = ws_write_be16(p, d[i].quantity);
    p = ws_write_u8(p, d[i].unit);
    p = ws_write_u8(p, (uint8_t)d[i].scale);
    p = ws_write_u8(p, form);
    p = ws_write_u8(p, d[i].kind);
  }
}

static int every(const uint8_t *p, size_t n, uint8_t v)
{
  for (size_t i = 0; i < n; i++)
    if (p[i] != v) return 0;
  return 1;
}

static int zero(const uint8_t *p, size_t n) { return every(p, n, 0); }

int wsmp_unpack_desc(const uint8_t in[WSMP_DESC_BLOCK_LEN], unsigned n, wsmp_desc *d)
{
  if (n > WSMP_MAX_CHANNELS) return WSMP_ELEN;
  for (unsigned i = 0; i < n; i++)
  {
    const uint8_t *p = in + i * WSMP_DESC_LEN;
    if (p[4] & DESC_RESERVED) return WSMP_ERESERVED;
    d[i] = (wsmp_desc){ .quantity = ws_get_be16(p), .unit = p[2], .scale = (int8_t)p[3],
                        .width = (uint8_t)(((p[4] >> DESC_WIDTH_SHIFT) & DESC_WIDTH_MASK) + 1U),
                        .is_signed = (p[4] & DESC_SIGNED_BIT) != 0, .kind = p[5] };
  }
  return zero(in + n * WSMP_DESC_LEN, (size_t)(WSMP_MAX_CHANNELS - n) * WSMP_DESC_LEN) ? WSMP_OK : WSMP_ERESERVED;
}

static const uint8_t unit_of[WSMP_UNIT_OF_COUNT] = WSMP_UNIT_OF_INIT;
static const wsmp_type_entry types[WSMP_TYPE_COUNT] = WSMP_TYPES_INIT;
static const wsmp_cal_limits cal_limits[WSMP_CAL_COUNT] = WSMP_CAL_INIT;

uint8_t wsmp_canonical_unit(uint16_t quantity) { return quantity < WSMP_UNIT_OF_COUNT ? unit_of[quantity] : 0U; }

const wsmp_type_entry *wsmp_type(uint16_t type)
{
  for (unsigned i = 0; i < WSMP_TYPE_COUNT; i++)   /* bound: WSMP_TYPE_COUNT entries */
    if (types[i].type == type) return &types[i];
  return NULL;
}

const wsmp_cal_limits *wsmp_cal_limits_of(uint16_t quantity)
{
  for (unsigned i = 0; i < WSMP_CAL_COUNT; i++)   /* bound: WSMP_CAL_COUNT entries */
    if (cal_limits[i].quantity == quantity) return &cal_limits[i];
  return NULL;
}

static int desc_one_ok(const wsmp_desc *d)
{
  uint8_t unit = wsmp_canonical_unit(d->quantity);
  if (unit == 0 || d->kind == 0 || d->kind > WSMP_KIND_MAX) return WSMP_ECODE;
  if (d->unit != unit) return WSMP_EUNIT;
  if (d->scale > WSMP_SCALE_MAX || d->scale < -WSMP_SCALE_MAX) return WSMP_ESCALE;
  if (d->width == 0 || d->width > WSMP_WIDTH_MAX) return WSMP_ELEN;
  return WSMP_OK;
}

int wsmp_desc_check(const wsmp_desc *d, unsigned n, uint16_t type, uint8_t schema)
{
  if (n > WSMP_MAX_CHANNELS) return WSMP_ELEN;
  for (unsigned i = 0; i < n; i++)
  {
    int rc = desc_one_ok(&d[i]);
    if (rc != WSMP_OK) return rc;
  }
  const wsmp_type_entry *t = wsmp_type(type);
  if (!t || t->schema != schema || t->channels != n) return WSMP_ETYPE;
  for (unsigned i = 0; i < n; i++)
    if (d[i].quantity != t->ch[i].quantity || d[i].kind != t->ch[i].kind) return WSMP_ETYPE;
  return WSMP_OK;
}

void wsmp_pack_snapshot(const wsmp_snapshot *s, uint8_t out[WSMP_SNAPSHOT_LEN])
{
  uint8_t *p = ws_write_be16(out, s->token);
  p = ws_write_be16(p, s->boot16);
  p = ws_write_be16(p, s->window_ms);
  p = ws_write_u8(p, s->flags);
  p = ws_write_u8(p, s->desc_tag);
  for (unsigned i = 0; i < WSMP_MAX_CHANNELS; i++)
  {
    p = ws_write_be32(p, s->slot[i].value);
    p = ws_write_be16(p, s->slot[i].count);
    p = ws_write_u8(p, s->slot[i].quality);
    p = ws_write_u8(p, 0);
  }
}

int wsmp_unpack_snapshot(const uint8_t in[WSMP_SNAPSHOT_LEN], wsmp_snapshot *s)
{
  if (in[6] & (uint8_t)~WSMP_FLAGS_DEFINED) return WSMP_ERESERVED;
  s->token = ws_get_be16(in);
  s->boot16 = ws_get_be16(in + 2);
  s->window_ms = ws_get_be16(in + 4);
  s->flags = in[6];
  s->desc_tag = in[7];
  for (unsigned i = 0; i < WSMP_MAX_CHANNELS; i++)
  {
    const uint8_t *p = in + WSMP_SNAPSHOT_HEAD_LEN + i * WSMP_SLOT_LEN;
    uint32_t v;
    if (p[7]) return WSMP_ERESERVED;
    (void)ws_read_be32(p, &v);
    s->slot[i] = (wsmp_slot){ .value = v, .count = ws_get_be16(p + 4), .quality = p[6] };
  }
  return WSMP_OK;
}

uint32_t wsmp_crc32c(const uint8_t *p, size_t n)
{
  uint32_t crc = CRC32C_INIT;
  for (size_t i = 0; i < n; i++)
  {
    crc ^= p[i];
    for (unsigned b = 0; b < BYTE_BITS; b++) crc = (crc >> 1) ^ (CRC32C_POLY & (0U - (crc & 1U)));
  }
  return ~crc;
}

uint8_t wsmp_quality_air(uint8_t quality)
{
  static const uint8_t air[] = { WSMP_QUAL_GOOD, WSMP_QUAL_PARTIAL, WSMP_QUAL_SUSPECT, WSMP_QUAL_MISSING,
                                 WSMP_QUAL_PARTIAL, WSMP_QUAL_MISSING };
  return quality < sizeof air ? air[quality] : (uint8_t)WSMP_QUAL_MISSING;
}

unsigned wsmp_values_bytes(const wsmp_desc *d, unsigned n)
{
  unsigned bytes = 0;
  for (unsigned i = 0; i < n && i < WSMP_MAX_CHANNELS; i++) bytes += d[i].width;
  return bytes;
}

unsigned wsmp_quality_bytes(unsigned channels)
{
  return (channels * QUALITY_BITS + BYTE_BITS - 1U) / BYTE_BITS;
}

static int text_char_ok(uint8_t c)
{
  return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == ' ' || c == '.' ||
         c == '_' || c == '-';
}

int wsmp_text_ok(const uint8_t *p, size_t n)
{
  size_t i = 0;
  while (i < n && p[i] != TEXT_PAD)   /* bound: n bytes */
  {
    if (!text_char_ok(p[i])) return 0;
    i++;
  }
  return zero(p + i, n - i);
}

#define REC_MAGIC      0x57534D52UL   /* "WSMR" */
#define REC_BLANK      0xFFU          /* an erased EEPROM */
#define REC_NS_SHIFT   56U            /* the serial's top byte is its namespace */
#define REC_SERIAL_LOW 0x00FFFFFFFFFFFFFFULL
#define REC_ENTRY_LEN  16U
#define REC_STATUS_SHIFT 4U
#define REC_SOURCE_MASK  0x03U
#define REC_STATUS_MASK  0x0FU
enum { AT_MAJOR = 0x04, AT_MINOR = 0x05, AT_LENGTH = 0x06, AT_TYPE = 0x08, AT_HW = 0x0A, AT_FLAGS = 0x0B,
       AT_SERIAL = 0x0C, AT_BIND_KIND = 0x14, AT_RESERVED1 = 0x15, AT_BIND = 0x18, AT_PROGRAMMED = 0x1C,
       AT_PART = 0x20, AT_RESERVED2 = 0x30, AT_CAL = 0x40, AT_RESERVED3 = 0x70, AT_CRC = 0x7C };
enum { RESERVED1_LEN = 3, RESERVED2_LEN = 16, RESERVED3_LEN = 12 };
/* In an entry: the reserved byte after the kind, and the two after the revision. */
enum { ENTRY_KIND = 2, ENTRY_RES_A = 3, ENTRY_REVISION = 4, ENTRY_RES_B = 6, ENTRY_RES_C = 7, ENTRY_OFFSET = 8,
       ENTRY_GAIN = 12 };

static uint8_t record_head(const uint8_t *in)
{
  if (every(in, WSMP_RECORD_LEN, REC_BLANK)) return WSMP_REC_BLANK;
  if (ws_get_be32(in) != REC_MAGIC) return WSMP_REC_NO_MAGIC;
  if (in[AT_MAJOR] != WSMP_RECORD_MAJOR) return WSMP_REC_VERSION;
  if (ws_get_be16(in + AT_LENGTH) != WSMP_RECORD_LEN) return WSMP_REC_MALFORMED;
  if (wsmp_crc32c(in, AT_CRC) != ws_get_be32(in + AT_CRC)) return WSMP_REC_CRC;
  return WSMP_REC_APPLIED;
}

static void entry_fields(const uint8_t *p, wsmp_cal_entry *e)
{
  *e = (wsmp_cal_entry){ .quantity = ws_get_be16(p), .kind = p[ENTRY_KIND], .revision = ws_get_be16(p + ENTRY_REVISION),
                         .offset = (int32_t)ws_get_be32(p + ENTRY_OFFSET), .gain = ws_get_be32(p + ENTRY_GAIN) };
}

static void record_fields(const uint8_t *in, wsmp_record *r)
{
  r->minor = in[AT_MINOR];
  r->type = ws_get_be16(in + AT_TYPE);
  r->hw_rev = in[AT_HW];
  r->flags = in[AT_FLAGS];
  r->serial = ws_get_be64(in + AT_SERIAL, sizeof r->serial);
  r->bind_kind = in[AT_BIND_KIND];
  r->bind_value = ws_get_be32(in + AT_BIND);
  r->programmed = ws_get_be32(in + AT_PROGRAMMED);
  memcpy(r->part, in + AT_PART, WSMP_RECORD_PART_LEN);
  for (unsigned i = 0; i < WSMP_RECORD_CAL_N; i++) entry_fields(in + AT_CAL + i * REC_ENTRY_LEN, &r->cal[i]);
  r->crc = ws_get_be32(in + AT_CRC);
}

static int serial_ok(uint64_t serial)
{
  uint64_t low = serial & REC_SERIAL_LOW;
  return (serial >> REC_NS_SHIFT) == WSMP_SRC_RECORD && low != 0 && low != REC_SERIAL_LOW;
}

static int bind_ok(const wsmp_record *r)
{
  if (r->bind_kind > WSMP_BIND_SHT4X) return 0;
  if (r->bind_kind == WSMP_BIND_NONE && r->bind_value != 0) return 0;
  return (r->bind_kind == WSMP_BIND_SHT4X) == (r->type == WSMP_T_AIR_TH);
}

static int reserved_ok(const uint8_t *in)
{
  return in[AT_FLAGS] == 0 && zero(in + AT_RESERVED1, RESERVED1_LEN) && zero(in + AT_RESERVED2, RESERVED2_LEN) &&
         zero(in + AT_RESERVED3, RESERVED3_LEN);
}

static int entries_ok(const uint8_t *in, int check_reserved)
{
  for (unsigned i = 0; i < WSMP_RECORD_CAL_N; i++)
  {
    const uint8_t *p = in + AT_CAL + i * REC_ENTRY_LEN;
    if (zero(p, REC_ENTRY_LEN)) continue;   /* unused: skipped before any check */
    if (p[ENTRY_KIND] > WSMP_KIND_MAX) return 0;
    if (check_reserved && (p[ENTRY_RES_A] | p[ENTRY_RES_B] | p[ENTRY_RES_C]) != 0) return 0;
  }
  return 1;
}

static uint8_t record_body(const uint8_t *in, const wsmp_record *r)
{
  int minor0 = r->minor == 0;
  int ok = serial_ok(r->serial) && wsmp_type(r->type) != NULL && bind_ok(r) &&
           wsmp_text_ok(r->part, WSMP_RECORD_PART_LEN) && (!minor0 || reserved_ok(in)) && entries_ok(in, minor0);
  return ok ? (uint8_t)WSMP_REC_APPLIED : (uint8_t)WSMP_REC_MALFORMED;
}

uint8_t wsmp_record_parse(const uint8_t in[WSMP_RECORD_LEN], wsmp_record *r)
{
  uint8_t status = record_head(in);
  if (status != WSMP_REC_APPLIED) return status;
  record_fields(in, r);
  return record_body(in, r);
}

static uint8_t *pack_entry(uint8_t *p, const wsmp_cal_entry *e)
{
  p = ws_write_be16(p, e->quantity);
  p = ws_write_u8(p, e->kind);
  p = ws_write_u8(p, 0);
  p = ws_write_be16(p, e->revision);
  p = ws_write_be16(p, 0);
  p = ws_write_be32(p, (uint32_t)e->offset);
  return ws_write_be32(p, e->gain);
}

void wsmp_record_pack(const wsmp_record *r, uint8_t out[WSMP_RECORD_LEN])
{
  memset(out, 0, WSMP_RECORD_LEN);
  uint8_t *p = ws_write_be32(out, REC_MAGIC);
  p = ws_write_u8(p, WSMP_RECORD_MAJOR);
  p = ws_write_u8(p, r->minor);
  p = ws_write_be16(p, WSMP_RECORD_LEN);
  p = ws_write_be16(p, r->type);
  p = ws_write_u8(p, r->hw_rev);
  p = ws_write_u8(p, r->flags);
  p = ws_write_be(p, r->serial, sizeof r->serial);
  p = ws_write_u8(p, r->bind_kind) + RESERVED1_LEN;
  p = ws_write_be32(p, r->bind_value);
  p = ws_write_be32(p, r->programmed);
  memcpy(p, r->part, WSMP_RECORD_PART_LEN);
  p = out + AT_CAL;
  for (unsigned i = 0; i < WSMP_RECORD_CAL_N; i++) p = pack_entry(p, &r->cal[i]);
  ws_put_be32(out + AT_CRC, wsmp_crc32c(out, AT_CRC));
}

uint8_t wsmp_id_flags(uint8_t source, uint8_t status)
{
  return (uint8_t)((source & REC_SOURCE_MASK) | (status & REC_STATUS_MASK) << REC_STATUS_SHIFT);
}

static uint8_t *pack_entry_set(uint8_t *p, const wsmp_set_module *m)
{
  p = ws_write_u8(p, m->port);
  p = ws_write_be16(p, m->type);
  p = ws_write_u8(p, m->schema);
  p = ws_write_u8(p, m->channels);
  p = ws_write_be(p, m->serial, sizeof m->serial);
  p = ws_write_u8(p, m->id_flags);
  p = ws_write_be32(p, m->record_crc);
  uint8_t block[WSMP_DESC_BLOCK_LEN];
  wsmp_pack_desc(m->desc, m->channels, block);
  size_t n = (size_t)m->channels * WSMP_DESC_LEN;
  memcpy(p, block, n);
  return p + n;
}

/* Power of Ten rule 5: the counts bound the writes into out[WSMP_SET_MAX_LEN]. A set outside them is a
   bug of the caller; the recovery is to pack nothing (length 0), which no reader accepts. */
static int set_fits(const wsmp_set *s)
{
  unsigned total = 0;
  if (s->count > WSMP_SET_MODULES_MAX) return 0;
  for (unsigned i = 0; i < s->count; i++)
  {
    if (s->m[i].channels == 0U || s->m[i].channels > WSMP_MAX_CHANNELS) return 0;
    total += s->m[i].channels;
  }
  return total <= WSMP_SET_CHANNELS_MAX;
}

unsigned wsmp_pack_set(const wsmp_set *s, uint8_t out[WSMP_SET_MAX_LEN])
{
  if (!set_fits(s)) return 0;
  uint8_t *p = out + WSMP_SET_HEAD_LEN;
  for (unsigned i = 0; i < s->count; i++) p = pack_entry_set(p, &s->m[i]);
  unsigned len = (unsigned)(p - out);
  uint8_t *h = ws_write_be16(out, s->generation);
  h = ws_write_u8(h, s->count);
  h = ws_write_u8(h, 0U);
  (void)ws_write_be32(h, wsmp_crc32c(out + WSMP_SET_HEAD_LEN, len - WSMP_SET_HEAD_LEN));
  return len;
}

#define SET_FLAGS_RESERVED 0x0CU                       /* id_flags bits 2-3 */
#define SET_STATUS_MAX     WSMP_REC_SENSOR_CHANGED     /* the last defined record status */

static int unpack_entry_set(const uint8_t **pp, const uint8_t *end, wsmp_set_module *m, unsigned *total)
{
  const uint8_t *p = *pp;
  if ((size_t)(end - p) < WSMP_SET_ENTRY_LEN) return WSMP_ELEN;
  m->port = p[0];
  m->type = ws_get_be16(p + 1);
  m->schema = p[3];
  m->channels = p[4];
  m->serial = ws_get_be64(p + 5, sizeof m->serial);
  m->id_flags = p[13];
  m->record_crc = ws_get_be32(p + 14);
  p += WSMP_SET_ENTRY_LEN;
  if (m->channels == 0U || m->channels > WSMP_MAX_CHANNELS || m->serial == 0U) return WSMP_ELEN;
  *total += m->channels;
  if (*total > WSMP_SET_CHANNELS_MAX) return WSMP_ELEN;
  if ((m->id_flags & SET_FLAGS_RESERVED) != 0U || (m->id_flags >> REC_STATUS_SHIFT) > SET_STATUS_MAX) return WSMP_ERESERVED;
  size_t n = (size_t)m->channels * WSMP_DESC_LEN;
  if ((size_t)(end - p) < n) return WSMP_ELEN;
  uint8_t block[WSMP_DESC_BLOCK_LEN] = { 0 };
  memcpy(block, p, n);
  *pp = p + n;
  return wsmp_unpack_desc(block, m->channels, m->desc);
}

static int unpack_head_set(const uint8_t *in, size_t len, wsmp_set *s)
{
  if (len < WSMP_SET_HEAD_LEN || len > WSMP_SET_MAX_LEN) return WSMP_ELEN;
  s->generation = ws_get_be16(in);
  s->count = in[2];
  s->digest = ws_get_be32(in + 4);
  if (in[3] != 0U) return WSMP_ERESERVED;
  return s->count > WSMP_SET_MODULES_MAX ? WSMP_ELEN : WSMP_OK;
}

int wsmp_unpack_set(const uint8_t *in, size_t len, wsmp_set *s)
{
  int head = unpack_head_set(in, len, s);
  if (head != WSMP_OK) return head;
  const uint8_t *p = in + WSMP_SET_HEAD_LEN, *end = in + len;
  unsigned total = 0;
  for (unsigned i = 0; i < s->count; i++)
  {
    int rc = unpack_entry_set(&p, end, &s->m[i], &total);
    if (rc != WSMP_OK) return rc;
    if (i > 0U && s->m[i].port <= s->m[i - 1U].port) return WSMP_ETYPE;
  }
  if (p != end) return WSMP_ELEN;
  return wsmp_crc32c(in + WSMP_SET_HEAD_LEN, len - WSMP_SET_HEAD_LEN) == s->digest ? WSMP_OK : WSMP_EDIGEST;
}

static int module_ok_set(const wsmp_set *s, unsigned i)
{
  const wsmp_set_module *m = &s->m[i];
  int rc = wsmp_desc_check(m->desc, m->channels, m->type, m->schema);
  if (rc != WSMP_OK) return rc;
  if ((m->serial >> REC_NS_SHIFT) != (m->id_flags & REC_SOURCE_MASK)) return WSMP_ETYPE;
  for (unsigned j = 0; j < i; j++)
    if (s->m[j].type == m->type) return WSMP_ETYPE;
  return WSMP_OK;
}

int wsmp_set_check(const wsmp_set *s)
{
  for (unsigned i = 0; i < s->count && i < WSMP_SET_MODULES_MAX; i++)
  {
    int rc = module_ok_set(s, i);
    if (rc != WSMP_OK) return rc;
  }
  return WSMP_OK;
}
