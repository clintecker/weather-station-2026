/* Host RAM model of the STM32WL55 internal flash that node_store.c uses.
 *
 * Rules modelled (RM0453 section 3.3):
 *  - erased = all ones; a page erase sets every double-word of one 2 KB page to all ones;
 *  - each 64-bit double-word may be programmed once after an erase; programming one that is
 *    not erased is a PROGERR on the chip and a reported violation here. The one exception
 *    the chip allows (RM0453 PROGERR: "except if the data to write is all zeros") is modelled
 *    and counted in zero_overwrites: the double-word becomes 0 with valid ECC;
 *  - a power cut during a program leaves the old (erased) value, the new value, or a torn
 *    double-word whose read raises a double-ECC fault (the NMI that sets ws_flash_ecc_fault);
 *  - a power cut during an erase leaves the page partially erased: some double-words erased,
 *    others still old, and (variant 4) some unreadable.
 * Addresses are the real 0x0800xxxx ones; the model covers pages WS_CONFIG_PAGE.. the last
 * journal page (flash_layout.h). The node firmware below WS_CONFIG_PAGE is not modelled. */
#ifndef SIM_FLASH_H
#define SIM_FLASH_H
#include <setjmp.h>
#include <stdint.h>
#include "flash_layout.h"

#define SIM_FIRST_PAGE WS_CONFIG_PAGE
#define SIM_PAGES (WS_JOURNAL_FIRST + WS_JOURNAL_PAGES - WS_CONFIG_PAGE)
#define SIM_DW_PER_PAGE (WS_PAGE_SIZE / 8U)
#define SIM_NEVER UINT64_MAX

enum { SIM_OP_PROG = 1, SIM_OP_ERASE = 2 };
/* Outcome of a power cut during a program. */
enum { SIM_PROG_OLD, SIM_PROG_NEW, SIM_PROG_TORN, SIM_PROG_VARIANTS };
/* Outcome of a power cut during an erase. */
enum { SIM_ERASE_NONE, SIM_ERASE_ALL, SIM_ERASE_RANDOM_A, SIM_ERASE_RANDOM_B, SIM_ERASE_RANDOM_ECC,
       SIM_ERASE_VARIANTS };
/* A failed op (HAL error, execution continues): refused with flash unchanged, or failed part
   way (a program leaves a torn, ECC-faulting double-word; an erase a partially erased page). */
enum { SIM_FAIL_CLEAN, SIM_FAIL_DAMAGED, SIM_FAIL_VARIANTS };

typedef struct {
 uint64_t mem[SIM_PAGES][SIM_DW_PER_PAGE];
 uint8_t ecc[SIM_PAGES][SIM_DW_PER_PAGE]; /* 1: the double-word reads back with a double-ECC fault */
 uint64_t ops;          /* programs + erases started so far (the cut-point index space) */
 uint64_t cut_at;       /* op index at which power is cut (SIM_NEVER: no cut) */
 int cut_variant;       /* SIM_PROG_* or SIM_ERASE_* for the cut op */
 uint32_t seed;         /* for the random partial-erase patterns */
 jmp_buf *cut_jump;     /* longjmp target once the cut has been applied (required with cut_at) */
 int cut_kind;          /* SIM_OP_* of the op that was cut, once it fired */
 uint32_t cut_addr;     /* address (program) or page (erase) of the cut op */
 uint64_t fail_at;      /* op index that fails like a HAL error (SIM_NEVER: none) */
 int fail_variant;      /* SIM_FAIL_*: what the failed op left behind */
 void (*on_fault)(void); /* optional: called when the cut or the failure fires, before its effect */
 uint8_t *kinds;        /* optional log: kinds[op] = SIM_OP_* for ops < kinds_cap */
 uint64_t kinds_cap;
 uint32_t violations;   /* program over a non-erased double-word, bad address or page */
 char last_violation[160];
 uint64_t progs, erases, ecc_reads, zero_overwrites;
 uint32_t page_erases[SIM_PAGES]; /* completed erases per page */
} sim_flash;

void sim_flash_reset(sim_flash *s); /* everything erased, counters zero, no cut, no failure */
/* The flash primitives over the model ctx (a sim_flash *); the host tests' ws_flash_* call these. */
int sim_flash_read64(void *ctx, uint32_t addr, uint64_t *out);
int sim_flash_prog64(void *ctx, uint32_t addr, uint64_t value);
int sim_flash_erase(void *ctx, uint32_t page);
/* Number of distinct cut outcomes for an op of this kind (SIM_OP_*). */
int sim_flash_variants(int kind);
#endif
