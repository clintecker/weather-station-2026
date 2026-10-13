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
#define WS_JOURNAL_PAGES     93U
/* Set by NMI_Handler when a read hits a double ECC error (interrupted program). */
extern volatile uint8_t ws_flash_ecc_fault;
#endif
