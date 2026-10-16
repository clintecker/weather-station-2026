#ifndef FLASH_LAYOUT_H
#define FLASH_LAYOUT_H
#include <stdint.h>
/* STM32WL55JC: 256 KB single-bank flash, 128 x 2 KB pages, 64-bit program granularity.
 * Firmware is linked into pages 0-31 (64 KB; enforced by STM32WL55JCIX_FLASH.ld). */
#define WS_FLASH_BASE        0x08000000UL
#define WS_PAGE_SIZE         2048UL
#define WS_FLASH_PAGES       128U
#define WS_DW_BYTES          8U    /* program granularity: one 64-bit double-word */
#define WS_FIRMWARE_BYTES    0x10000UL   /* pages 0-31; STM32WL55JCIX_FLASH.ld */
#define WS_PAGE_ADDR(p)      (WS_FLASH_BASE + (uint32_t)(p) * WS_PAGE_SIZE)
#define WS_CONFIG_PAGE       32U   /* provisioning: station id + key */
#define WS_META_PAGE_A       33U   /* append log of monotonic values (epoch, counter reservation) */
#define WS_META_PAGE_B       34U
#define WS_JOURNAL_FIRST     35U   /* observation ring: pages 35-127 */
#ifndef WS_JOURNAL_PAGES      /* host tests may shrink the ring (tests/test_store_powercut.py) */
#define WS_JOURNAL_PAGES     93U
_Static_assert(WS_JOURNAL_FIRST + WS_JOURNAL_PAGES == WS_FLASH_PAGES, "the journal runs to the last flash page");
#endif
/* Set by NMI_Handler when a read hits a double ECC error (interrupted program). */
extern volatile uint8_t ws_flash_ecc_fault;

/* The three flash primitives node_store.c uses (review P3), so the store builds and is power-cut
 * tested on the host. Addresses are absolute (0x0800xxxx); every call returns 0 on success.
 * read64 returns nonzero when the read hit a double-ECC fault (a torn program). prog64 writes one
 * erased, 8-byte-aligned double-word; erase takes a page number. A link-time seam, not a table of
 * function pointers (docs/power-of-ten.md, rule 9): App/flash_stm32wl.c (HAL_FLASH_*) defines them on
 * the board, firmware/test_store.c and firmware/host/tx_harness.c over firmware/sim_flash.c on the
 * host. */
int ws_flash_read64(uint32_t addr, uint64_t *out);
int ws_flash_prog64(uint32_t addr, uint64_t value);
int ws_flash_erase(uint32_t page);
#endif
