/* ws_flash ops for the STM32WL55 internal flash (review P3): the HAL calls node_store.c used
 * to make directly. A double-ECC error on a read raises the NMI; NMI_Handler (stm32wlxx_it.c)
 * clears it and sets ws_flash_ecc_fault, which read64 turns into a nonzero return.
 * Program and erase stall the CPU until the flash is done (it cannot fetch code meanwhile, RM0453
 * 3.3.6); each one is timed (busymon BM_PROG / BM_ERASE) so the stall is a measured number. */
#include "busymon.h"
#include "flash_layout.h"
#include "stm32wlxx_hal.h"

static int read64(void *ctx, uint32_t addr, uint64_t *out) {
 (void)ctx;
 ws_flash_ecc_fault = 0;
 *out = *(volatile const uint64_t *)addr;
 __DSB();
 return ws_flash_ecc_fault ? -1 : 0;
}
static int prog64(void *ctx, uint32_t addr, uint64_t v) {
 HAL_StatusTypeDef st;
 (void)ctx;
 uint32_t t0 = busymon_now();
 HAL_FLASH_Unlock();
 __HAL_FLASH_CLEAR_FLAG(FLASH_FLAG_ALL_ERRORS);
 st = HAL_FLASH_Program(FLASH_TYPEPROGRAM_DOUBLEWORD, addr, v);
 HAL_FLASH_Lock();
 busymon_end(BM_PROG, t0, "prog");
 return st == HAL_OK ? 0 : -1;
}
static int erase(void *ctx, uint32_t page) {
 FLASH_EraseInitTypeDef e = { .TypeErase = FLASH_TYPEERASE_PAGES, .Page = page, .NbPages = 1 };
 uint32_t err = 0; HAL_StatusTypeDef st;
 (void)ctx;
 uint32_t t0 = busymon_now();
 HAL_FLASH_Unlock();
 __HAL_FLASH_CLEAR_FLAG(FLASH_FLAG_ALL_ERRORS);
 st = HAL_FLASHEx_Erase(&e, &err);
 HAL_FLASH_Lock();
 busymon_end(BM_ERASE, t0, "erase");
 return st == HAL_OK ? 0 : -1;
}

const ws_flash ws_flash_internal = { 0, read64, prog64, erase };
