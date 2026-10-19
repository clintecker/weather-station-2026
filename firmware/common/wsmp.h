#ifndef WSMP_H
#define WSMP_H
/* WSMP core (docs/module-protocol.md, firmware/common/wsmp.lit.md): the module blocks, their checks
 * against the registry, CRC-32C and the radio budget. Portable C: no HAL, no heap, no state. The
 * station and, later, the remote module adapter use the same file. */
#include <stddef.h>
#include <stdint.h>
#include "wsmp_registry.h"

#define WSMP_MAGIC          0x5753U   /* "WS" */
#define WSMP_VERSION_MAJOR  1U
#define WSMP_VERSION_MINOR  0U
#define WSMP_MAX_CHANNELS   8U
#define WSMP_IDENTITY_LEN   32U
#define WSMP_DESC_LEN       6U
#define WSMP_DESC_BLOCK_LEN (WSMP_MAX_CHANNELS * WSMP_DESC_LEN)
#define WSMP_SNAPSHOT_HEAD_LEN 8U
#define WSMP_SLOT_LEN       8U
#define WSMP_SNAPSHOT_LEN   (WSMP_SNAPSHOT_HEAD_LEN + WSMP_MAX_CHANNELS * WSMP_SLOT_LEN)
#define WSMP_RADIO_BUDGET   58U       /* bytes of values and quality in one radio reading (WSMP-A1) */
#define WSMP_SCALE_MAX      6         /* WSMP-D2: the scale is -6 to +6 */
#define WSMP_WIDTH_MAX      4U        /* WSMP-D3: 1 to 4 bytes on the radio */

/* Snapshot header flags (WSMP section 6.4). */
#define WSMP_FLAG_FIRST_WINDOW 0x01U
#define WSMP_FLAG_LONG_WINDOW  0x02U
#define WSMP_FLAG_FAULT        0x04U
#define WSMP_FLAGS_DEFINED     0x07U

/* Snapshot quality codes (WSMP section 9). */
enum { WSMP_QUAL_GOOD, WSMP_QUAL_PARTIAL, WSMP_QUAL_SUSPECT, WSMP_QUAL_MISSING, WSMP_QUAL_WARMING_UP, WSMP_QUAL_FAULT };

/* Identity capability bits (WSMP section 6.1). */
#define WSMP_CAP_METADATA   0x0001U
#define WSMP_CAP_PERSISTENT 0x0002U

enum { WSMP_OK = 0, WSMP_EMAGIC = -1, WSMP_EVERSION = -2, WSMP_ECODE = -3, WSMP_EUNIT = -4,
       WSMP_ESCALE = -5, WSMP_ERESERVED = -6, WSMP_ETYPE = -7, WSMP_ELEN = -8 };

typedef struct { uint16_t quantity; uint8_t unit; int8_t scale; uint8_t width, is_signed, kind; } wsmp_desc;
typedef struct {
  uint16_t type; uint8_t schema, channels, fw_major, fw_minor;
  uint16_t fw_build, caps; uint64_t serial; uint32_t boot_id, desc_digest;
} wsmp_identity;
typedef struct { uint32_t value; uint16_t count; uint8_t quality; } wsmp_slot;
typedef struct { uint16_t token, boot16, window_ms; uint8_t flags, desc_tag; wsmp_slot slot[WSMP_MAX_CHANNELS]; } wsmp_snapshot;

void wsmp_pack_identity(const wsmp_identity *id, uint8_t out[WSMP_IDENTITY_LEN]);
int wsmp_unpack_identity(const uint8_t in[WSMP_IDENTITY_LEN], wsmp_identity *id);
void wsmp_pack_desc(const wsmp_desc *d, unsigned n, uint8_t out[WSMP_DESC_BLOCK_LEN]);   /* n <= 8, rest zero */
int wsmp_unpack_desc(const uint8_t in[WSMP_DESC_BLOCK_LEN], unsigned n, wsmp_desc *d);
void wsmp_pack_snapshot(const wsmp_snapshot *s, uint8_t out[WSMP_SNAPSHOT_LEN]);
int wsmp_unpack_snapshot(const uint8_t in[WSMP_SNAPSHOT_LEN], wsmp_snapshot *s);
/* WSMP-D7: n descriptors against the registry entry of (type, schema). */
int wsmp_desc_check(const wsmp_desc *d, unsigned n, uint16_t type, uint8_t schema);
uint32_t wsmp_crc32c(const uint8_t *p, size_t n);
uint8_t wsmp_quality_air(uint8_t quality);        /* snapshot quality to the 2-bit radio code */
unsigned wsmp_values_bytes(const wsmp_desc *d, unsigned n);
unsigned wsmp_quality_bytes(unsigned channels);   /* 2 bits a channel, padded to a byte */
int wsmp_text_ok(const uint8_t *p, size_t n);     /* WSMP-M1: 1 if the padded text is allowed */
#endif
