#ifndef FLASH_LAYOUT_H
#define FLASH_LAYOUT_H
#include <stdint.h>
/* STM32WL55JC: 256 KB single-bank flash, 128 x 2 KB pages, 64-bit program granularity.
 * Page map: firmware 0-54 (110 KB; the linker script STM32WL55JCIX_FLASH.ld and board.mk's
 * APP_FLASH_BYTES enforce it, tests/test_flash_layout.py checks that they agree), journal 55-124,
 * meta log A 125 and B 126, provisioning 127. The node state sits at the top of flash, so the
 * firmware region can grow by changing WS_FIRMWARE_PAGES and the journal size alone. */
#define WS_FLASH_BASE        0x08000000UL
#define WS_PAGE_SIZE         2048UL
#define WS_FLASH_PAGES       128U
#define WS_DW_BYTES          8U    /* program granularity: one 64-bit double-word */
#define WS_FIRMWARE_PAGES    55U
#define WS_FIRMWARE_BYTES    (WS_FIRMWARE_PAGES * WS_PAGE_SIZE)
#define WS_PAGE_ADDR(p)      (WS_FLASH_BASE + (uint32_t)(p) * WS_PAGE_SIZE)
#define WS_CONFIG_PAGE       (WS_FLASH_PAGES - 1U)   /* provisioning: station id + key */
#define WS_META_PAGE_B       (WS_CONFIG_PAGE - 1U)   /* append log of monotonic values (epoch, counter reservation) */
#define WS_META_PAGE_A       (WS_CONFIG_PAGE - 2U)
#ifndef WS_JOURNAL_PAGES      /* host tests may shrink the ring (tests/test_store_powercut.py) */
#define WS_JOURNAL_PAGES     70U   /* 24 h for a full station: (70 - 1) x 21 slots */
#define WS_JOURNAL_DEFAULT   1     /* the board's ring, not a shrunken host test ring */
#endif
#define WS_JOURNAL_FIRST     (WS_META_PAGE_A - WS_JOURNAL_PAGES)   /* observation ring, up to meta log A */
#define WS_STATE_FIRST       WS_JOURNAL_FIRST                      /* the lowest node-state page */
_Static_assert(WS_JOURNAL_FIRST >= WS_FIRMWARE_PAGES, "the node state starts above the firmware region");
/* Set by NMI_Handler when a read hits a double ECC error (interrupted program). */
extern volatile uint8_t ws_flash_ecc_fault;

/* The three flash primitives node_store.c uses, so the store builds and is power-cut
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
