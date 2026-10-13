#ifndef FLASH_LAYOUT_H
#define FLASH_LAYOUT_H
#include <stdint.h>
/* STM32WL55JC: 256 KB single-bank flash, 128 x 2 KB pages, 64-bit program granularity.
 * Firmware is linked into pages 0-31 (64 KB; enforced by STM32WL55JCIX_FLASH.ld). */
#define WS_FLASH_BASE        0x08000000UL
#define WS_PAGE_SIZE         2048UL
#define WS_PAGE_ADDR(p)      (WS_FLASH_BASE + (uint32_t)(p) * WS_PAGE_SIZE)
#define WS_CONFIG_PAGE       32U   /* provisioning: station id + key */
#define WS_META_PAGE_A       33U   /* append log of monotonic values (epoch, counter reservation) */
#define WS_META_PAGE_B       34U
#define WS_JOURNAL_FIRST     35U   /* observation ring: pages 35-127 */
#ifndef WS_JOURNAL_PAGES      /* host tests may shrink the ring (tests/test_store_powercut.py) */
#define WS_JOURNAL_PAGES     93U
#endif
/* Set by NMI_Handler when a read hits a double ECC error (interrupted program). */
extern volatile uint8_t ws_flash_ecc_fault;

/* The three flash primitives node_store.c uses (review P3), so the store builds and is
 * power-cut tested on the host (firmware/sim_flash.c). Addresses are absolute (0x0800xxxx);
 * every call returns 0 on success. read64 returns nonzero when the read hit a double-ECC
 * fault (a torn program). prog64 writes one erased, 8-byte-aligned double-word; erase takes a
 * page number. The target implementation is App/flash_stm32wl.c (HAL_FLASH_*). */
typedef struct {
 void *ctx;
 int (*read64)(void *ctx, uint32_t addr, uint64_t *out);
 int (*prog64)(void *ctx, uint32_t addr, uint64_t value);
 int (*erase)(void *ctx, uint32_t page);
} ws_flash;
/* The internal flash: App/flash_stm32wl.c on the board, the simulator in host tests. */
extern const ws_flash ws_flash_internal;
#endif
