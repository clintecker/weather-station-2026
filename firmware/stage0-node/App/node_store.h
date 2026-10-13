#ifndef NODE_STORE_H
#define NODE_STORE_H
#include <stdint.h>
#include "flash_layout.h"
/* Durable TX node state in internal flash: provisioning, monotonic counters, journal. */

/* Provisioning */
int store_config_load(uint32_t *station, uint8_t key[16]); /* 0 if provisioned and intact */
int store_config_write(uint32_t station, const uint8_t key[16]);
int store_wipe(void); /* erases config (key) and journal; counters and epoch are kept (G17) */

/* Monotonic values. Each call durably reserves before returning; never repeats. */
int store_meta_init(void);
int store_next_epoch(uint32_t *epoch);     /* once per boot, before sampling */
int store_next_counter(uint64_t *counter); /* one per transmission */
int store_epoch_floor(uint32_t floor);     /* G5: raise the epoch base (never lowers) */
int store_note_abandoned(void);            /* G8: persist one more abandoned record */
uint32_t store_abandoned_total(void);

/* Journal of 24-byte observation plaintexts, retained until an authenticated ACK. */
typedef struct { uint16_t page; uint16_t slot; } jref_t;
#define JOURNAL_SLOTS_PER_PAGE 51U
#define JOURNAL_CAPACITY (JOURNAL_SLOTS_PER_PAGE * WS_JOURNAL_PAGES)
int store_journal_init(void);
int store_journal_append(const uint8_t plain[24], jref_t *ref);
int store_journal_read(jref_t ref, uint8_t plain[24]);
int store_journal_ack(jref_t ref);
/* Oldest pending entries, skipping 'except' (may be NULL); returns count written to out. */
unsigned store_journal_oldest(jref_t *out, unsigned max, const jref_t *except);
int store_journal_find(uint32_t epoch, uint32_t seq, jref_t *ref); /* pending only */
uint32_t store_journal_pending(void);
uint32_t store_journal_lost(void);   /* pending records overwritten, cumulative across boots */
uint32_t store_journal_burned(void); /* torn slots found at boot */
uint32_t store_ecc_faults(void);      /* double-ECC reads caught since boot (torn writes) */
uint64_t store_counter_next(void);    /* next transmission counter (diagnostics, G7 test) */
/* Acknowledge (drop) every pending entry whose epoch equals 'marker'; returns how many. */
uint32_t store_journal_scrub(uint32_t marker);
#endif
