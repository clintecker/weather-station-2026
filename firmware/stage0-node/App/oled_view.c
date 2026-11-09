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
#include "tx_time.h"
#include "ws_policy.h"
#include "wsmp_host.h"

/* Linker symbols (STM32WL55JCIX_FLASH.ld): the flash image ends at _sidata plus .data; RAM1 runs from
   .data's start to the stack top, its statics up to _end, then the heap and the stack reserved. */
extern char _sidata[], _sdata[], _edata[], _end[], _estack[], _Min_Heap_Size[], _Min_Stack_Size[];

#define BW_HZ(index) (125000UL << (index))   /* radio_cfg.h's WS_LORA_BANDWIDTH 0:125 1:250 2:500 kHz */
#define AIR_EVERY_MS 60000U
#define PRESS_EVERY_MS 300000U
/* An Absent port has no module once every port has probed: the I2C modules sample (and probe) at boot and
   every WSMP_SAMPLE_MS, the on-board ones more often. One sample period and a margin. */
#define ABSENT_AFTER_MS (WSMP_SAMPLE_MS + 5000U)
#define JOURNAL_RECORDS ((WS_JOURNAL_PAGES - 1U) * JOURNAL_SLOTS_PER_PAGE)   /* the ring less the page being erased */

static uint8_t pct(uint32_t used, uint32_t of)
{
  uint32_t p = of ? (uint32_t)(((uint64_t)used * 100U) / of) : 100U;
  return (uint8_t)(p > 100U ? 100U : p);
}

/* Addresses as integers: the symbols are distinct objects to C, so their pointers do not subtract. */
#define ADDR(sym) ((uint32_t)(uintptr_t)(sym))

void oled_view_build(scr_view_t *v)
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
}

/* A port's mark on the boot checklist. Absent is a verdict only once every port has probed (probed). */
static uint8_t port_mark(int state, int probed)
{
  switch (state)
  {
    case WH_ACTIVE: return SCR_PORT_OK;
    case WH_ABSENT: return probed ? SCR_PORT_ABSENT : SCR_PORT_WAIT;
    case WH_SUSPECT: case WH_QUARANTINED: case WH_REFUSED: return SCR_PORT_FAULT;
    default: return SCR_PORT_WAIT;   /* probing, identifying, admitted until its first latch */
  }
}

_Static_assert(SCR_PORTS == (unsigned)P_COUNT - (unsigned)P_AIR_TH, "a checklist mark for every local port");

static int scanning;              /* the first oled_view_modules came */
static uint32_t scan_from;        /* then (clock_ms) */

int oled_view_modules(scr_view_t *v, uint32_t now_ms)
{
  if (!scanning) { scanning = 1; scan_from = now_ms; }
  int probed = now_ms - scan_from >= ABSENT_AFTER_MS, settled = 1;
  for (unsigned i = 0; i < SCR_PORTS; i++)
  {
    uint8_t m = port_mark(wsmp_host_state((enum wsmp_port)((unsigned)P_AIR_TH + i)), probed);
    v->port_mark[i] = m;
    settled &= m != SCR_PORT_WAIT;
  }
  return settled;
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
  v->utc = time_utc();
}

static int sampling;              /* the first sample was taken */
static uint32_t air_at, press_at; /* when the next falls due (clock_ms) */

void oled_view_sample(scr_view_t *v, uint32_t now_ms)
{
  if (!sampling) { sampling = 1; air_at = press_at = now_ms; }
  int32_t c, rh, p;
  if (scr_hist_due(now_ms, &air_at, AIR_EVERY_MS))
  {
    int ok = in_layout(P_AIR_TH) && mod_th_live(TH_AIR, &c, &rh);
    v->air.n = (uint8_t)scr_hist_push(v->air.s, SCR_AIR_HIST, v->air.n, ok ? scr_hist_value(c) : SCR_GAP);
  }
  if (scr_hist_due(now_ms, &press_at, PRESS_EVERY_MS))
  {
    int ok = in_layout(P_PRESSURE) && mod_reg_live(REG_PRESSURE, &p);
    v->press.n = (uint8_t)scr_hist_push(v->press.s, SCR_PRESS_HIST, v->press.n, ok ? scr_hist_value(p) : SCR_GAP);
  }
}

void oled_view_fill(scr_view_t *v, enum scr_id id, unsigned frame)
{
  fill_node(v);
  fill_live(v);
  /* The whole stack scan (stackmon_peak) is about 1.5 ms: only once, as the system bars start. */
  if (id == SCR_SYSTEM && frame == 0U) v->stack_pct = pct(stackmon_peak(), ADDR(_Min_Stack_Size));
}

uint32_t oled_view_airtime_ms(uint8_t len)
{
  return ws_lora_airtime_ms(len, WS_LORA_SF, BW_HZ(WS_LORA_BANDWIDTH), WS_LORA_PREAMBLE, WS_LORA_CR);
}
