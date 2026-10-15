#include "events.h"
#include "stm32_seq.h"
#include "utilities_def.h"

void events_post(volatile uint32_t *pending, uint32_t bits)
{
  uint32_t primask = irq_lock();
  *pending |= bits;
  irq_unlock(primask);
  UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_SubGHz_Phy_App_Process, CFG_SEQ_Prio_0);
}

uint32_t events_take(volatile uint32_t *pending)
{
  uint32_t primask = irq_lock();
  uint32_t bits = *pending;
  *pending = 0;
  irq_unlock(primask);
  return bits;
}
