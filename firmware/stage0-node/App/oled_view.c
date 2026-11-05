/* The bench screens' view of the node (App/oled_view.h). Main loop only; every value is a cached one
 * that its module keeps (no bus, ADC or flash access here). */
#include "oled_view.h"
#include "clock.h"
#include "flash_layout.h"
#include "mod_rain.h"
#include "mod_reg.h"
#include "mod_th.h"
#include "mod_wind.h"
#include "node_store.h"
#include "power_acq.h"
#include "radio_cfg.h"
#include "stackmon.h"
#include "tx_exchange.h"
#include "tx_node.h"
#include "ws_policy.h"
#include "wsmp_host.h"

/* Linker symbols (STM32WL55JCIX_FLASH.ld): the flash image ends at _sidata plus .data; RAM1 runs from
   .data's start to the stack top, its statics up to _end, then the heap and the stack reserved. */
extern char _sidata[], _sdata[], _edata[], _end[], _estack[], _Min_Heap_Size[], _Min_Stack_Size[];

#define BW_HZ(index) (125000UL << (index))   /* radio_cfg.h's WS_LORA_BANDWIDTH 0:125 1:250 2:500 kHz */
#define JOURNAL_RECORDS ((WS_JOURNAL_PAGES - 1U) * JOURNAL_SLOTS_PER_PAGE)   /* the ring less the page being erased */

static uint8_t pct(uint32_t used, uint32_t of)
{
  uint32_t p = of ? (uint32_t)(((uint64_t)used * 100U) / of) : 100U;
  return (uint8_t)(p > 100U ? 100U : p);
}

/* Addresses as integers: the symbols are distinct objects to C, so their pointers do not subtract. */
#define ADDR(sym) ((uint32_t)(uintptr_t)(sym))

static void fill_build(scr_view_t *v)
{
  uint32_t flash = ADDR(_sidata) - WS_FLASH_BASE + (ADDR(_edata) - ADDR(_sdata));
  uint32_t ram = ADDR(_end) - ADDR(_sdata) + ADDR(_Min_Heap_Size) + ADDR(_Min_Stack_Size);
  v->flash_pct = pct(flash, WS_FIRMWARE_BYTES);
  v->ram_pct = pct(ram, ADDR(_estack) - ADDR(_sdata));
  v->sf = WS_LORA_SF;
  v->bw_khz_div125 = (uint8_t)(1U << WS_LORA_BANDWIDTH);
  v->freq_khz = (uint32_t)(WS_RF_FREQUENCY_HZ / 1000UL);
}

static void fill_node(scr_view_t *v)
{
  const tx_identity_t *idn = exchange_identity();
  v->key_ok = idn->provisioned;
  v->station = (uint16_t)(idn->station > UINT16_MAX ? UINT16_MAX : idn->station);
  v->epoch = node_state()->boot_epoch;
  v->pending = store_journal_pending();
  v->journal_pct = pct(v->pending, JOURNAL_RECORDS);
  unsigned found = 0, active = 0;
  for (int p = P_AIR_TH; p < P_COUNT; p++)   /* bound: the 8 local ports */
  {
    int s = wsmp_host_state((enum wsmp_port)p);
    found += s != WH_ABSENT && s != WH_PROBING;
    active += s == WH_ACTIVE;
  }
  v->modules = found;
  v->modules_active = active;
}

/* The port is in the layout: the predicate the observation's fields use (wsmp_catalog_map.c). A module
   identifying, quarantined or refused still samples, but the reading carries none of its values. */
static int in_layout(enum wsmp_port p) { return wsmp_host_snapshot(p) != NULL; }

static void fill_live(scr_view_t *v)
{
  v->air_ok = in_layout(P_AIR_TH) && mod_th_live(TH_AIR, &v->air_c, &v->air_rh);
  v->box_ok = in_layout(P_ENCL_TH) && mod_th_live(TH_ENCL, &v->box_c, &v->box_rh);
  v->press_ok = in_layout(P_PRESSURE) && mod_reg_live(REG_PRESSURE, &v->press_dhpa);
  v->uv_ok = in_layout(P_UVA) && mod_reg_live(REG_UVA, &v->uv_counts);
  (void)mod_wind_live(&v->wind);
  mod_rain_history(clock_ms(), &v->rain);
  power_acq_live(&v->power);
}

void oled_view_fill(scr_view_t *v, enum scr_id id, unsigned frame)
{
  fill_build(v);
  fill_node(v);
  fill_live(v);
  /* The whole stack scan (stackmon_peak) is about 1.5 ms: only once, as the system bars start. */
  if (id == SCR_SYSTEM && frame == 0U) v->stack_pct = pct(stackmon_peak(), ADDR(_Min_Stack_Size));
}

uint32_t oled_view_airtime_ms(uint8_t len)
{
  return ws_lora_airtime_ms(len, WS_LORA_SF, BW_HZ(WS_LORA_BANDWIDTH), WS_LORA_PREAMBLE, WS_LORA_CR);
}
