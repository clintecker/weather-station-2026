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
  memset(p, 0, (size_t)(out + WSMP_IDENTITY_LEN - p));
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
  if (id->channels == 0 || id->channels > WSMP_MAX_CHANNELS || id->serial == 0) return WSMP_ELEN;
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

static int zero(const uint8_t *p, size_t n)
{
  for (size_t i = 0; i < n; i++)
    if (p[i]) return 0;
  return 1;
}

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

uint8_t wsmp_canonical_unit(uint16_t quantity) { return quantity < WSMP_UNIT_OF_COUNT ? unit_of[quantity] : 0U; }

const wsmp_type_entry *wsmp_type(uint16_t type)
{
  for (unsigned i = 0; i < WSMP_TYPE_COUNT; i++)   /* bound: WSMP_TYPE_COUNT entries */
    if (types[i].type == type) return &types[i];
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
