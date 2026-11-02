/* The WSMP descriptor set (firmware/common/wsmp.c: wsmp_unpack_set, wsmp_pack_set), driven with
 * arbitrary sets. Byte 0 bit 0 seals the input with a good digest (its CRC-32C over everything after
 * the header), so the checks before the digest's are reached; the rest of the input is the set.
 * Properties, checked against an independent reading of docs/module-protocol.md section 11.1, whose
 * module entry is the one of docs/firmware-current-design.md (section 6.7,
 * "The serial reaches the gateway", and its WSMP edit in section 13.1):
 *  - wsmp_unpack_set accepts exactly the sets the specification allows, and refuses the others with
 *    the code of the first fault (length and counts, reserved bits, port order, digest);
 *  - an accepted set packs back to the same bytes;
 *  - no memory error (ASan/UBSan). */
#include <string.h>
#include "fuzz.h"
#include "wsmp.h"

#define SPEC_HEAD 8U
#define SPEC_ENTRY 18U
#define SPEC_DESC 6U
#define SPEC_MODULES 8U
#define SPEC_CHANNELS 8U
#define SPEC_TOTAL 24U
#define SPEC_MAX (SPEC_HEAD + SPEC_MODULES * SPEC_ENTRY + SPEC_TOTAL * SPEC_DESC)   /* 296 */
#define SPEC_STATUS_MAX 8U                                                            /* SENSOR_CHANGED */

static uint32_t spec_crc32c(const uint8_t *p, size_t n)
{
  uint32_t crc = 0xFFFFFFFFU;
  for (size_t i = 0; i < n; i++)
  {
    crc ^= p[i];
    for (unsigned k = 0; k < 8; k++) crc = (crc >> 1) ^ ((crc & 1U) ? 0x82F63B78U : 0U);
  }
  return ~crc;
}

/* The specification's verdict on the set in[0..len): the WSMP_E* code of the first fault, or 0. */
static int spec_set(const uint8_t *in, size_t len)
{
  if (len < SPEC_HEAD || len > SPEC_MAX) return WSMP_ELEN;
  if (in[3] != 0) return WSMP_ERESERVED;
  unsigned count = in[2], total = 0, last_port = 0;
  if (count > SPEC_MODULES) return WSMP_ELEN;
  size_t at = SPEC_HEAD;
  for (unsigned i = 0; i < count; i++)
  {
    if (len - at < SPEC_ENTRY) return WSMP_ELEN;
    const uint8_t *e = in + at;
    unsigned channels = e[4];
    int serial = 0;
    for (unsigned k = 5; k < 13; k++) serial |= e[k];
    if (channels == 0 || channels > SPEC_CHANNELS || !serial) return WSMP_ELEN;
    total += channels;
    if (total > SPEC_TOTAL) return WSMP_ELEN;
    if ((e[13] & 0x0CU) || (e[13] >> 4) > SPEC_STATUS_MAX) return WSMP_ERESERVED;
    at += SPEC_ENTRY;
    if (len - at < channels * SPEC_DESC) return WSMP_ELEN;
    for (unsigned c = 0; c < channels; c++)
      if (in[at + c * SPEC_DESC + 4] & 0x0FU) return WSMP_ERESERVED;
    at += channels * SPEC_DESC;
    if (i > 0 && e[0] <= last_port) return WSMP_ETYPE;
    last_port = e[0];
  }
  if (at != len) return WSMP_ELEN;
  uint32_t digest = (uint32_t)in[4] << 24 | (uint32_t)in[5] << 16 | (uint32_t)in[6] << 8 | in[7];
  return spec_crc32c(in + SPEC_HEAD, len - SPEC_HEAD) == digest ? WSMP_OK : WSMP_EDIGEST;
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
  uint8_t in[SPEC_MAX + 8], back[WSMP_SET_MAX_LEN];
  wsmp_set s;
  if (size == 0) return 0;
  size_t len = size - 1 < sizeof in ? size - 1 : sizeof in;
  memcpy(in, data + 1, len);
  if ((data[0] & 1U) && len >= SPEC_HEAD)
  {
    uint32_t d = spec_crc32c(in + SPEC_HEAD, len - SPEC_HEAD);
    in[4] = (uint8_t)(d >> 24); in[5] = (uint8_t)(d >> 16); in[6] = (uint8_t)(d >> 8); in[7] = (uint8_t)d;
  }
  int rc = wsmp_unpack_set(in, len, &s);
  FUZZ_CHECK(rc == spec_set(in, len));
  if (rc != WSMP_OK) return 0;
  FUZZ_CHECK(wsmp_pack_set(&s, back) == len && memcmp(back, in, len) == 0);
  return 0;
}
