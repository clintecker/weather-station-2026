#ifndef WSMP_H
#define WSMP_H
/* WSMP core (docs/module-protocol.md, firmware/common/wsmp.lit.md): the module blocks, their checks
 * against the registry, the module record v1.0, CRC-32C and the radio budget. Portable C: no HAL, no heap, no state. The
 * station and, later, the remote module adapter use the same file. */
#include <stddef.h>
#include <stdint.h>
#include "wsmp_registry.h"

#define WSMP_MAGIC          0x5753U   /* "WS" */
#define WSMP_VERSION_MAJOR  1U
#define WSMP_VERSION_MINOR  1U       /* 1.1: snapshot quality 6, not fitted (WSMP-V2) */
#define WSMP_MAX_CHANNELS   8U
#define WSMP_IDENTITY_LEN   32U
#define WSMP_DESC_LEN       6U
#define WSMP_DESC_BLOCK_LEN (WSMP_MAX_CHANNELS * WSMP_DESC_LEN)
#define WSMP_SNAPSHOT_HEAD_LEN 8U
#define WSMP_SLOT_LEN       8U
#define WSMP_SNAPSHOT_LEN   (WSMP_SNAPSHOT_HEAD_LEN + WSMP_MAX_CHANNELS * WSMP_SLOT_LEN)
#define WSMP_RADIO_BUDGET   60U       /* bytes of values and quality in one radio reading (WSMP-A1): the planned
                                         * plaintext (80 B, the journal's per-build limit) less a 20-byte header */
#define WSMP_SCALE_MAX      6         /* WSMP-D2: the scale is -6 to +6 */
#define WSMP_WIDTH_MAX      4U        /* WSMP-D3: 1 to 4 bytes on the radio */

/* Snapshot header flags (WSMP section 6.4). */
#define WSMP_FLAG_FIRST_WINDOW 0x01U
#define WSMP_FLAG_LONG_WINDOW  0x02U
#define WSMP_FLAG_FAULT        0x04U
#define WSMP_FLAGS_DEFINED     0x07U

/* Snapshot quality codes (WSMP section 9). WSMP_QUAL_NOT_FITTED (6, WSMP 1.1): this hardware build has
 * no source for the channel; carried as missing (3) on the radio; the distinction holds locally and
 * through the catalog map only (spec section 8.3, docs/superpowers/specs/2026-10-29-power-telemetry-design.md). */
enum { WSMP_QUAL_GOOD, WSMP_QUAL_PARTIAL, WSMP_QUAL_SUSPECT, WSMP_QUAL_MISSING, WSMP_QUAL_WARMING_UP, WSMP_QUAL_FAULT,
       WSMP_QUAL_NOT_FITTED };

/* Identity capability bits (WSMP section 6.1). */
#define WSMP_CAP_METADATA   0x0001U
#define WSMP_CAP_PERSISTENT 0x0002U

enum { WSMP_OK = 0, WSMP_EMAGIC = -1, WSMP_EVERSION = -2, WSMP_ECODE = -3, WSMP_EUNIT = -4,
       WSMP_ESCALE = -5, WSMP_ERESERVED = -6, WSMP_ETYPE = -7, WSMP_ELEN = -8, WSMP_EDIGEST = -9 };

typedef struct { uint16_t quantity; uint8_t unit; int8_t scale; uint8_t width, is_signed, kind; } wsmp_desc;
typedef struct {
  uint16_t type; uint8_t schema, channels, fw_major, fw_minor;
  uint16_t fw_build, caps; uint64_t serial; uint32_t boot_id, desc_digest;
  uint16_t id_flags;   /* register 0x000F: wsmp_id_flags() in the low byte, the high byte 0 */
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

/* Module record v1.0, the 128 bytes at word address 0 of a module board's ID EEPROM
 * (docs/superpowers/specs/2026-10-21-sensor-module-ports-design.md section 6.9). Big-endian. */
#define WSMP_RECORD_LEN      128U
#define WSMP_RECORD_MAJOR    1U
#define WSMP_RECORD_PART_LEN 16U
#define WSMP_RECORD_CAL_N    3U
#define WSMP_BIND_NONE       0U
#define WSMP_BIND_SHT4X      1U   /* the SHT4x's own serial (command 0x89) */

/* Record status: identity-flag bits 4-7. READ to CRC are NO_RECORD reasons (section 6.9, Checks). */
enum { WSMP_REC_APPLIED, WSMP_REC_READ, WSMP_REC_BLANK, WSMP_REC_NO_MAGIC, WSMP_REC_VERSION, WSMP_REC_MALFORMED,
       WSMP_REC_CRC, WSMP_REC_CAL_REJECTED, WSMP_REC_SENSOR_CHANGED };
/* Serial source: identity-flag bits 0-1, and also the serial's top byte (its namespace, section 6.7). */
enum { WSMP_SRC_PORT, WSMP_SRC_RECORD, WSMP_SRC_SENSOR, WSMP_SRC_ADAPTER };

typedef struct { uint16_t quantity, revision; uint8_t kind; int32_t offset; uint32_t gain; } wsmp_cal_entry;
typedef struct {
  uint16_t type; uint8_t minor, hw_rev, flags, bind_kind;
  uint64_t serial; uint32_t bind_value, programmed, crc;
  uint8_t part[WSMP_RECORD_PART_LEN];
  wsmp_cal_entry cal[WSMP_RECORD_CAL_N];   /* an all-zero entry is unused */
} wsmp_record;

/* Checks 2-6 of section 6.9, in order: WSMP_REC_APPLIED (the record is structurally valid; check 7,
   the calibration, is wsmp_cal_check) or the first failure, BLANK to MALFORMED. r is filled once the
   CRC passes. Check 1 (READ) and the second read after a CRC failure are the caller's. */
uint8_t wsmp_record_parse(const uint8_t in[WSMP_RECORD_LEN], wsmp_record *r);
/* The record's bytes: magic, major 1, r->minor, length 128, its fields, reserved bytes 0, the CRC. */
void wsmp_record_pack(const wsmp_record *r, uint8_t out[WSMP_RECORD_LEN]);
/* The identity flags' low byte, the descriptor set's id_flags: source in bits 0-1, status in 4-7. */
uint8_t wsmp_id_flags(uint8_t source, uint8_t status);

/* The descriptor set (WSMP section 11.1, wsmp.lit.md section 9): a header, then one entry for each
 * module in increasing port order, each followed by its descriptors. Big-endian. */
#define WSMP_SET_HEAD_LEN      8U
#define WSMP_SET_ENTRY_LEN     18U    /* port, type, schema, channels, serial, id_flags, record_crc */
#define WSMP_SET_MODULES_MAX   8U     /* WSMP-P8 */
#define WSMP_SET_CHANNELS_MAX  24U    /* WSMP-P8 */
#define WSMP_SET_MAX_LEN (WSMP_SET_HEAD_LEN + WSMP_SET_MODULES_MAX * WSMP_SET_ENTRY_LEN + \
                          WSMP_SET_CHANNELS_MAX * WSMP_DESC_LEN)   /* 296 bytes, WSMP-E4 */
typedef struct {
  uint8_t port, schema, channels, id_flags;   /* id_flags: wsmp_id_flags(source, status) */
  uint16_t type;
  uint64_t serial;
  uint32_t record_crc;                         /* the applied record's CRC-32C; 0 when none is applied */
  wsmp_desc desc[WSMP_MAX_CHANNELS];
} wsmp_set_module;
typedef struct { uint16_t generation; uint8_t count; uint32_t digest; wsmp_set_module m[WSMP_SET_MODULES_MAX]; } wsmp_set;
/* Writes the set with its digest; returns its length (at most WSMP_SET_MAX_LEN), or 0 and nothing for
   a set outside the counts (more than 8 modules, channels outside 1-8, more than 24 in all). */
unsigned wsmp_pack_set(const wsmp_set *s, uint8_t out[WSMP_SET_MAX_LEN]);
/* WSMP_OK, or the first fault (wsmp.lit.md section 9): WSMP_ELEN, WSMP_ERESERVED, WSMP_ETYPE, WSMP_EDIGEST. */
int wsmp_unpack_set(const uint8_t *in, size_t len, wsmp_set *s);
/* WSMP-E7: every module of an unpacked set passes the registry check (WSMP-D7, its code); WSMP_ETYPE
   for a serial namespace that is not its source, or a module type twice (v1: one module per type). */
int wsmp_set_check(const wsmp_set *s);
#endif
