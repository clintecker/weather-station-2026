/* WSMP core (firmware/common/wsmp.c), driven with arbitrary module blocks.
 * Byte 0 of the input selects the block; the rest is the block (padded with zero). Properties,
 * checked against an independent reading of docs/module-protocol.md sections 4-6 and registry
 * version 2 (docs/superpowers/specs/2026-10-29-power-telemetry-design.md section 8.1: quantities
 * 18-24, module types 8 and 9; section 8.3: WSMP 1.1):
 *  - each unpack function accepts exactly the blocks the protocol allows, and a re-pack of an accepted
 *    block gives back the same bytes;
 *  - wsmp_desc_check accepts exactly the registry entry of a module type (the table below);
 *  - wsmp_text_ok accepts exactly the allowed padded text;
 *  - no memory error (ASan/UBSan). */
#include <string.h>
#include "fuzz.h"
#include "wsmp.h"

#define SPEC_MAGIC0 0x57U
#define SPEC_MAGIC1 0x53U
#define SPEC_MAJOR 1U
#define SPEC_MINOR 1U   /* WSMP 1.1: snapshot quality 6, not fitted (design section 8.3); this station's minor */
#define SPEC_CHANNELS 8U
#define SPEC_IDENTITY 32U
#define SPEC_DESC 6U
#define SPEC_SNAPSHOT 72U
#define SPEC_SLOT 8U
#define SPEC_FLAGS_UNDEFINED 0xF8U
#define SPEC_DESC_RESERVED 0x0FU
#define SPEC_TEXT 16U
#define SPEC_TYPES 9U       /* registry version 2: types 1-9 */
#define SPEC_QUANTITIES 25U /* registry version 2: quantities 0-24 (0 unused) */
#define SPEC_SCALE_MAX 6

/* WSMP section 4.4 written out again: type, number of channels, then quantity and kind pairs
 * (kind 2 = mean, 6 = counter). Type 8 (battery) and type 9 (power rails) from design section 8.1. */
static const uint8_t spec_types[SPEC_TYPES][1 + 2 * 7] = {
  { 2, 1, 2, 2, 2 }, { 1, 3, 2 }, { 1, 8, 2 }, { 2, 1, 2, 2, 2 },
  { 7, 9, 2, 11, 6, 12, 6, 13, 6, 14, 6, 15, 1, 16, 10 }, { 4, 17, 6, 5, 7, 6, 8, 6, 9 }, { 1, 7, 6 },
  { 6, 9, 2, 10, 2, 11, 6, 12, 6, 13, 6, 14, 6 },
  { 7, 18, 2, 19, 2, 20, 2, 21, 2, 22, 2, 23, 2, 24, 2 } };
/* WSMP section 4.1: the canonical unit of quantities 1-17, and of 18-24 from design section 8.1:
 * voltages (18, 20, 21, 23) in V = unit 8, currents (19, 22, 24) in A = unit 9. */
static const uint8_t spec_unit[SPEC_QUANTITIES] = { 0, 1, 2, 3, 4, 4, 5, 6, 7, 8, 9, 10, 10, 11, 11, 2, 12, 13,
                                                     8, 9, 8, 8, 9, 8, 9 };

static void identity(const uint8_t *in)
{
  wsmp_identity id;
  uint8_t back[SPEC_IDENTITY];
  int serial = 0;
  for (unsigned i = 8; i < 16; i++) serial |= in[i];
  /* identity flags (bytes 30-31): bits 8-15 and 2-3 reserved, 0 (spec 2026-10-21 section 6.7) */
  int ok = in[0] == SPEC_MAGIC0 && in[1] == SPEC_MAGIC1 && in[2] == SPEC_MAJOR && in[7] >= 1 && in[7] <= SPEC_CHANNELS && serial &&
           in[30] == 0 && (in[31] & 0x0CU) == 0;
  int rc = wsmp_unpack_identity(in, &id);
  FUZZ_CHECK((rc == WSMP_OK) == ok);
  if (rc != WSMP_OK) return;
  wsmp_pack_identity(&id, back);
  /* the minor is this station's; the identity flags (register 0x000F, bytes 30-31) are kept as read */
  FUZZ_CHECK(memcmp(back, in, 3) == 0 && back[3] == SPEC_MINOR && memcmp(back + 4, in + 4, 28) == 0);
}

static void snapshot(const uint8_t *in)
{
  wsmp_snapshot s;
  uint8_t back[SPEC_SNAPSHOT];
  int ok = !(in[6] & SPEC_FLAGS_UNDEFINED);
  for (unsigned i = 0; i < SPEC_CHANNELS; i++) ok = ok && in[SPEC_SLOT + i * SPEC_SLOT + 7] == 0;
  int rc = wsmp_unpack_snapshot(in, &s);
  FUZZ_CHECK((rc == WSMP_OK) == ok);
  if (rc != WSMP_OK) return;
  wsmp_pack_snapshot(&s, back);
  FUZZ_CHECK(memcmp(back, in, SPEC_SNAPSHOT) == 0);
}

static int spec_desc_ok(const uint8_t *in, unsigned n, unsigned type)
{
  if (type == 0 || type > SPEC_TYPES || spec_types[type - 1][0] != n) return 0;
  for (unsigned i = 0; i < n; i++)
  {
    const uint8_t *p = in + i * SPEC_DESC;
    unsigned quantity = (unsigned)p[0] << 8 | p[1];
    int scale = (int8_t)p[3];
    unsigned width = (p[4] >> 5) + 1U;
    if (quantity != spec_types[type - 1][1 + 2 * i] || p[5] != spec_types[type - 1][2 + 2 * i]) return 0;
    /* quantity is a registry code here (the row above matched), so spec_unit[quantity] is in bounds */
    if (p[2] != spec_unit[quantity] || scale > SPEC_SCALE_MAX || scale < -SPEC_SCALE_MAX || width > 4) return 0;
  }
  return 1;
}

static void descriptors(const uint8_t *in, unsigned n, unsigned type)
{
  wsmp_desc d[SPEC_CHANNELS];
  uint8_t back[SPEC_CHANNELS * SPEC_DESC];
  int ok = n <= SPEC_CHANNELS;
  for (unsigned i = 0; ok && i < SPEC_CHANNELS * SPEC_DESC; i++)
    ok = i < n * SPEC_DESC ? (i % SPEC_DESC != 4 || !(in[i] & SPEC_DESC_RESERVED)) : in[i] == 0;
  int rc = wsmp_unpack_desc(in, n, d);
  FUZZ_CHECK((rc == WSMP_OK) == ok);
  if (rc != WSMP_OK) return;
  wsmp_pack_desc(d, n, back);
  FUZZ_CHECK(memcmp(back, in, sizeof back) == 0);
  FUZZ_CHECK((wsmp_desc_check(d, n, (uint16_t)type, 1) == WSMP_OK) == spec_desc_ok(in, n, type));
}

static int spec_char(uint8_t c)
{
  return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == ' ' || c == '.' || c == '_' || c == '-';
}

static void text(const uint8_t *in)
{
  int ok = 1, ended = 0;
  for (unsigned i = 0; i < SPEC_TEXT; i++)
  {
    if (!in[i]) ended = 1;
    else if (ended || !spec_char(in[i])) ok = 0;
  }
  FUZZ_CHECK(wsmp_text_ok(in, SPEC_TEXT) == ok);
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
  uint8_t in[2 + SPEC_SNAPSHOT] = { 0 };
  if (size == 0) return 0;
  memcpy(in, data + 1, size - 1 < sizeof in ? size - 1 : sizeof in);
  switch (data[0] & 3U)
  {
    case 0: identity(in); break;
    case 1: snapshot(in); break;
    case 2: descriptors(in + 2, in[0] % (SPEC_CHANNELS + 2U), in[1] % (SPEC_TYPES + 2U)); break;
    default: text(in); break;
  }
  return 0;
}
