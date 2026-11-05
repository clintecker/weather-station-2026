"""The bench screens' view of the node (firmware/stage0-node/App/oled_view.c) on the host.

oled_view.c is compiled unchanged over a shim of what it reads: the modules' live values, the port
states and snapshots (wsmp_host.h), the identity, the journal and the linker's symbols. The screen must
agree with the observation: a temperature, humidity, pressure or UV value shows only while its port has
the snapshot the observation's fields read (wsmp_catalog_map.c: wsmp_host_snapshot), whatever the module
itself still samples."""
import ctypes
import unittest

try:
    from toolchain import ROOT, fresh_copy, host_library, needs_cc          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import ROOT, fresh_copy, host_library, needs_cc    # python -m unittest tests.<module>

FW = ROOT/'firmware'
APP = FW/'stage0-node/App'
P_AIR_TH, P_PRESSURE, P_UVA, P_ENCL_TH = 1, 2, 3, 4
WH_IDENTIFYING, WH_ADMITTED, WH_ACTIVE, WH_SUSPECT, WH_QUARANTINED, WH_REFUSED = 2, 3, 4, 5, 6, 7

SHIM = r'''
#include <string.h>
#include "mod_rain.h"
#include "mod_reg.h"
#include "mod_th.h"
#include "mod_wind.h"
#include "node_store.h"
#include "oled_view.h"
#include "power_acq.h"
#include "stackmon.h"
#include "tx_exchange.h"
#include "tx_node.h"
#include "ws_policy.h"
#include "wsmp_host.h"
char _sidata[1], _sdata[1], _edata[1], _end[1], _estack[1], _Min_Heap_Size[1], _Min_Stack_Size[1];
static tx_identity_t idn;
static tx_node_t node;
const tx_identity_t *exchange_identity(void) { return &idn; }
const tx_node_t *node_state(void) { return &node; }
uint32_t store_journal_pending(void) { return 0; }
uint32_t stackmon_peak(void) { return 0; }
uint32_t ws_lora_airtime_ms(uint32_t payload, uint32_t sf, uint32_t bw_hz, uint32_t preamble, uint32_t cr)
{ (void)sf; (void)bw_hz; (void)preamble; (void)cr; return payload; }
/* The modules sample and answer whatever their port's state: the live values are always there. */
int mod_th_live(enum th_unit u, int32_t *centi_c, int32_t *centi_rh) { *centi_c = 2314 + (int)u; *centi_rh = 5080; return 1; }
int mod_reg_live(enum reg_unit u, int32_t *value) { *value = u == REG_PRESSURE ? 9830 : 7; return 1; }
int mod_wind_live(wind_live_t *w) { memset(w, 0, sizeof *w); return 1; }
uint32_t mod_rain_tips_since_boot(void) { return 0; }
void power_acq_live(power_live_t *p) { memset(p, 0, sizeof *p); }
/* The port states, and the snapshot the real wsmp_host.c gives an Active or Suspect port after a latch. */
int t_state[P_COUNT], t_snap[P_COUNT];
static wsmp_snapshot snap;
int wsmp_host_state(enum wsmp_port p) { return t_state[p]; }
const wsmp_snapshot *wsmp_host_snapshot(enum wsmp_port p) { return t_snap[p] ? &snap : NULL; }
static scr_view_t v;
void t_fill(void) { memset(&v, 0, sizeof v); oled_view_fill(&v, SCR_NORMAL, 0); }
int t_air_ok(void) { return v.air_ok; }
int t_box_ok(void) { return v.box_ok; }
int t_press_ok(void) { return v.press_ok; }
int t_uv_ok(void) { return v.uv_ok; }
int t_air_c(void) { return v.air_c; }
unsigned t_modules_active(void) { return v.modules_active; }
'''


@needs_cc
class OledView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built = host_library(cls, 'oledview', '-DWS_BENCH_OLED=1', '-DWS_I2C_MUX=0', '-I', FW/'host/include', '-I', FW/'host',
                                 '-I', APP, '-I', FW/'stage0-node/Core/Inc', '-I', FW, '-I', FW/'common', APP/'oled_view.c',
                                 files={'shim.c': SHIM})

    def setUp(self):
        self.lib = fresh_copy(type(self), self.built._name)

    def port(self, p, state, snap):
        (ctypes.c_int * 9).in_dll(self.lib, 't_state')[p] = state
        (ctypes.c_int * 9).in_dll(self.lib, 't_snap')[p] = int(snap)

    def oks(self):
        self.lib.t_fill()
        return (self.lib.t_air_ok(), self.lib.t_box_ok(), self.lib.t_press_ok(), self.lib.t_uv_ok())

    def test_values_only_from_ports_in_the_layout(self):
        for p in (P_AIR_TH, P_PRESSURE, P_UVA, P_ENCL_TH):
            self.port(p, WH_ACTIVE, True)
        self.assertEqual(self.oks(), (1, 1, 1, 1))
        self.assertEqual(self.lib.t_air_c(), 2314)
        # Identifying (not admitted yet), admitted before its first latch, quarantined, refused: the module
        # still samples, but the observation carries none of its values, and neither does the screen.
        for state in (WH_IDENTIFYING, WH_ADMITTED, WH_QUARANTINED, WH_REFUSED):
            with self.subTest(state=state):
                self.port(P_AIR_TH, state, False)
                self.port(P_UVA, state, False)
                self.assertEqual(self.oks(), (0, 1, 1, 0))
        self.port(P_AIR_TH, WH_SUSPECT, True)   # Suspect keeps its snapshot: in the layout, its values shown
        self.port(P_ENCL_TH, WH_REFUSED, False)
        self.port(P_PRESSURE, WH_REFUSED, False)
        self.assertEqual(self.oks(), (1, 0, 0, 0))


if __name__ == '__main__':
    unittest.main()
