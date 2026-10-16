#ifndef NODE_STORE_H
#define NODE_STORE_H
#include <stdint.h>
#include "flash_layout.h"
#include "node_fields.h"
#include "ws_frame.h"
/* Durable TX node state in internal flash: provisioning, monotonic counters, journal.
 * All flash access goes through the ws_flash_* primitives (flash_layout.h). Mutators of the monotonic
 * values need a successful store_meta_init; journal mutators also need store_journal_init
 * (and a fresh one after store_wipe). Before that they return STORE_ENOTREADY and touch
 * nothing. */
/* Return codes: 0 on success, a negative STORE_E* on failure. Callers test for nonzero; the value
 * is printed in #error lines. */
enum {
 STORE_OK = 0,
 STORE_EFLASH = -1,      /* a program or erase failed, or an address outside the node pages was refused */
 STORE_ENODATA = -2,     /* no valid record: erased, unreadable, or not committed; or not found */
 STORE_EKEY = -3,        /* the key check value cannot be computed, or the stored one does not match */
 STORE_ERANGE = -4,      /* station id outside 1..WS_STATION_MAX, or a meta value over 56 bits */
 STORE_EEXISTS = -5,     /* the provisioning page is not erased: WIPE first */
 STORE_EEXHAUSTED = -6,  /* no epoch or counter left */
 STORE_EINVAL = -7,      /* a jref_t this file did not issue (WS_CHECK records the site) */
 STORE_ENOTREADY = -16,  /* init has not succeeded */
};
/* store_next_epoch never returns this epoch: the bench storm test (TEST-FLASH-STORM) uses it. */
#define STORE_EPOCH_RESERVED UINT32_MAX

/* Provisioning */
/* 0 if provisioned and intact; then kcv also holds the key check value (ws_key_check), verified
   against the stored one. On failure key is zeroed and kcv is untouched. */
int store_config_load(uint32_t *station, uint8_t key[WS_KEY_LEN], uint8_t kcv[WS_KCV_LEN]);
int store_config_write(uint32_t station, const uint8_t key[WS_KEY_LEN], uint8_t kcv[WS_KCV_LEN]);   /* kcv: out, the key check value */
int store_wipe(void); /* erases config (key) and journal; counters and epoch are kept (no nonce reuse) */

/* Monotonic values. Each call durably reserves before returning; never repeats. */
int store_meta_init(void);
int store_next_epoch(uint32_t *epoch);     /* once per boot, before sampling */
int store_next_counter(uint64_t *counter); /* one per transmission; refuses past WS_COUNTER_MAX */
int store_epoch_floor(uint32_t floor);     /* after WIPE: raise the epoch base (never lowers) */
int store_note_abandoned(void);            /* persist one more abandoned record */
uint32_t store_abandoned_total(void);

/* Journal of observation plaintexts (WS_OBS_PLAIN_MAX bytes, node_fields.h), retained until an
 * authenticated ACK. A slot is the plaintext rounded up to double-words, a commit double-word
 * (magic + CRC) and an ACK double-word; a page is an 8-byte header plus its slots. */
typedef struct { uint16_t page; uint16_t slot; } jref_t;
#define JOURNAL_HDR_BYTES WS_DW_BYTES   /* page header: magic | slot size, sequence */
#define JOURNAL_PLAIN_DW ((WS_OBS_PLAIN_MAX + WS_DW_BYTES - 1U) / WS_DW_BYTES)
#define JOURNAL_SLOT_BYTES ((JOURNAL_PLAIN_DW + 2U) * WS_DW_BYTES)   /* + commit and ACK double-words */
#define JOURNAL_SLOTS_PER_PAGE ((WS_PAGE_SIZE - JOURNAL_HDR_BYTES) / JOURNAL_SLOT_BYTES)
#define JOURNAL_CAPACITY (JOURNAL_SLOTS_PER_PAGE * WS_JOURNAL_PAGES)
int store_journal_init(void);
int store_journal_append(const uint8_t plain[WS_OBS_PLAIN_MAX], jref_t *ref);
int store_journal_read(jref_t ref, uint8_t plain[WS_OBS_PLAIN_MAX]);
int store_journal_ack(jref_t ref);
/* Oldest pending entries, skipping 'except' (may be NULL); returns count written to out. */
unsigned store_journal_oldest(jref_t *out, unsigned max, const jref_t *except);
int store_journal_find(uint32_t epoch, uint32_t seq, jref_t *ref); /* pending only */
uint32_t store_journal_pending(void);
uint32_t store_journal_lost(void);   /* pending records overwritten, cumulative across boots */
uint32_t store_journal_burned(void); /* torn slots found at boot */
uint32_t store_ecc_faults(void);      /* double-ECC reads caught since boot (torn writes) */
uint64_t store_counter_next(void);    /* next transmission counter (diagnostics, power-cut test) */
/* Acknowledge (drop) every pending entry whose epoch equals 'marker'; returns how many. */
uint32_t store_journal_scrub(uint32_t marker);
#endif
