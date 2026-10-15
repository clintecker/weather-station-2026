/* Host stand-in (firmware/host/tx_harness.c): the few CMSIS names the TX application uses. */
#ifndef HOST_STM32WLXX_H
#define HOST_STM32WLXX_H
#include <stdint.h>
typedef struct { volatile uint32_t CTRL, CYCCNT; } DWT_Type;
typedef struct { volatile uint32_t DEMCR; } CoreDebug_Type;
extern DWT_Type host_dwt;
extern CoreDebug_Type host_coredebug;
#define DWT (&host_dwt)
#define CoreDebug (&host_coredebug)
#define DWT_CTRL_CYCCNTENA_Msk 1U
#define CoreDebug_DEMCR_TRCENA_Msk (1U << 24)
extern uint32_t SystemCoreClock;
extern uint32_t host_primask;
static inline uint32_t __get_PRIMASK(void) { return host_primask; }
static inline void __set_PRIMASK(uint32_t v) { host_primask = v; }
static inline void __disable_irq(void) { host_primask = 1; }
void NVIC_SystemReset(void);
#endif
