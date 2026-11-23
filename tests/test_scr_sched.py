"""The bench OLED's screen scheduler and its glue (firmware/stage0-node/App/scr_sched.c, oled_app.c).

scr_sched.c is pure: the tests step it as oled_app.c does, every 125 ms. oled_app.c is compiled unchanged
against a shim (below) that stands in for the DMA driver (a busy flag the test holds, the sends and
draws into it it counts), the screens (scr_draw records what it was asked to draw, and the view it saw), the
node's view (oled_view.c, which only reads the modules), ST's timer and sequencer, and the clock.

The field build (WS_BENCH_OLED=0, the default) must keep the exchange's hooks empty: its tx_exchange.o
references no oled_note_ symbol. That needs the ARM toolchain and vendor/, and skips without them."""
import ctypes
import os
import subprocess
import unittest
from pathlib import Path

try:
    from toolchain import ROOT, fresh_copy, host_library, needs_cc          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import ROOT, fresh_copy, host_library, needs_cc    # python -m unittest tests.<module>

NODE = ROOT/'firmware/stage0-node'
APP = NODE/'App'
TOOLCHAIN_GCC = Path.home()/'.local/opt/xpack-arm-none-eabi-gcc-15.2.1-1.1/bin/arm-none-eabi-gcc'
HAVE_ARM = TOOLCHAIN_GCC.exists() and (ROOT/'vendor/STM32CubeWL').exists()

SCREENS = ['HOME', 'BURST', 'BANNER', 'AIR', 'PRESSURE', 'POWER', 'RADIO', 'SCOPE', 'VANE', 'RAIN', 'SYSTEM', 'BOOT',
           'HACK', 'FORTUNE', 'FROG', 'MATRIX', 'PINBALL', 'MODULES']   # enum scr_id
FRAMES = {'HOME': 1, 'BURST': 16, 'BANNER': 24, 'AIR': 8, 'PRESSURE': 8, 'POWER': 8, 'RADIO': 8, 'SCOPE': 64, 'VANE': 64,
          'RAIN': 64, 'SYSTEM': 64, 'BOOT': 72, 'HACK': 24, 'FORTUNE': 64, 'FROG': 64, 'MATRIX': 64, 'PINBALL': 64,
          'MODULES': 16}
DETAILS = ['AIR', 'PRESSURE', 'POWER', 'RADIO', 'SCOPE', 'VANE', 'RAIN', 'SYSTEM']
INTERLUDES = ['FORTUNE', 'SCOPE', 'FROG', 'VANE', 'MATRIX', 'RAIN', 'PINBALL', 'SYSTEM', 'HACK']
B1_ORDER = ['HOME', *DETAILS, 'FORTUNE', 'FROG', 'MATRIX', 'PINBALL', 'HACK']
DWELL = 120   # a base screen's 15 s of steps
EV_SENT_LIVE, EV_SENT_EXTRA, EV_ACK, EV_NO_ACK, EV_B1, EV_B2, EV_B3, EV_SETTLED = range(8)
CAP_MS = 60000   # SCHED_MODULES_CAP_MS
CHECK_WAIT, CHECK_DONE, CHECK_TIMEOUT = range(3)   # enum scr_check
BOOT_STEPS = FRAMES['BOOT'] + FRAMES['MODULES'] + FRAMES['HACK']   # settled from the start
SCR_TX_NONE, SCR_TX_WAIT, SCR_TX_NO_ACK, SCR_TX_ACK = -2, -1, 0, 1
STEP_MS = 125
SENT_BACKLOG, SENT_LIVE, SENT_REPORT = range(3)   # enum oled_sent (App/oled_hooks.h)

SHIM = r'''
#include <string.h>
#include "stm32_seq.h"
#include "stm32_timer.h"
#include "board_inputs.h"
#include "busymon.h"
#include "clock.h"
#include "oled_app.h"
#include "oled_dma.h"
#include "oled_view.h"
#include "scr_screens.h"
DWT_Type host_dwt;
bm_span busymon_begin(void) { bm_span s = { 0, 0 }; return s; }
void busymon_task_end(bm_span s, const char *task) { (void)s; (void)task; }

uint32_t t_now;
uint32_t clock_ms(void) { return t_now; }
uint32_t clock_s(void) { return t_now / 1000U; }

static UTIL_TIMER_Object_t *timer;
int UTIL_TIMER_Create(UTIL_TIMER_Object_t *t, uint32_t period, UTIL_TIMER_Mode_t mode, void (*cb)(void *), void *arg)
{ memset(t, 0, sizeof *t); t->period = period; t->mode = mode; t->cb = cb; t->arg = arg; timer = t; return UTIL_TIMER_OK; }
int UTIL_TIMER_Start(UTIL_TIMER_Object_t *t) { t->running = 1; return UTIL_TIMER_OK; }
int UTIL_TIMER_Stop(UTIL_TIMER_Object_t *t) { t->running = 0; return UTIL_TIMER_OK; }
int UTIL_TIMER_SetPeriod(UTIL_TIMER_Object_t *t, uint32_t period) { t->period = period; return UTIL_TIMER_OK; }
static void (*task)(void);
static uint32_t task_mask, posted;
void UTIL_SEQ_RegTask(uint32_t mask, uint32_t flags, void (*fn)(void)) { (void)flags; task_mask = mask; task = fn; }
void UTIL_SEQ_SetTask(uint32_t mask, uint32_t prio) { (void)prio; posted |= mask; }
uint32_t t_timer_period(void) { return timer && timer->running && timer->mode == UTIL_TIMER_PERIODIC ? timer->period : 0; }
/* One tick: the timer fires (it only posts the task), then the main loop runs what was posted. */
void t_adv(uint32_t ms) { t_now += ms; }
/* A step at the current clock, which does not move. */
int t_step(void)
{
  timer->cb(timer->arg);
  int ran = (posted & task_mask) != 0;
  posted = 0;
  if (ran) task();
  return ran;
}
int t_tick(void) { t_now += timer->period; return t_step(); }

int t_busy, t_inits, t_sends, t_expands, t_torn, t_faulted;
static uint8_t txbuf[OLED_FRAME_BYTES];
void oled_dma_init(void) { t_inits++; }
int oled_dma_busy(void) { return t_busy; }
int oled_dma_faulted(void) { return t_faulted; }
uint8_t *oled_dma_buffer(void) { return txbuf; }
int t_enable_calls, t_enabled = 1;
void oled_dma_enable(int on) { t_enable_calls++; t_enabled = on; }
int oled_dma_send(const uint8_t frame[OLED_FRAME_BYTES])
{ if (t_busy) { t_torn++; return -1; } if (frame != txbuf) return -3; t_sends++; return 0; }

/* The screens' table (scr_screens.c) is the real one; the screens it names draw nothing. */
#define SCREEN(f) void f(const oled_surf *s, unsigned frame, const scr_view_t *v) { (void)s; (void)frame; (void)v; }
SCREEN(scr_home) SCREEN(scr_banner) SCREEN(scr_burst) SCREEN(scr_air) SCREEN(scr_pressure) SCREEN(scr_power)
SCREEN(scr_radio) SCREEN(scr_scope) SCREEN(scr_vane) SCREEN(scr_rain) SCREEN(scr_system) SCREEN(scr_boot)
SCREEN(scr_hack) SCREEN(scr_fortune) SCREEN(scr_frog) SCREEN(scr_matrix) SCREEN(scr_pinball) SCREEN(scr_modules)
int t_draws, t_id = -1, t_frame = -1;
scr_view_t t_view;   /* what the last draw saw */
/* t_expands: draws on a surface over the send buffer, turned for the panel. */
void scr_draw(const oled_surf *s, enum scr_id id, unsigned frame, const scr_view_t *v)
{
  if (t_busy) t_torn++;
  if (s->px == txbuf && s->rot180) t_expands++;
  t_draws++; t_id = (int)id; t_frame = (int)frame; t_view = *v;
}
int t_fills;
void oled_view_fill(scr_view_t *v, enum scr_id id, unsigned frame) { (void)v; (void)id; (void)frame; t_fills++; }
void oled_view_build(scr_view_t *v) { (void)v; }
int t_samples;
void oled_view_sample(scr_view_t *v, uint32_t now_ms) { (void)v; (void)now_ms; t_samples++; }
uint32_t oled_view_airtime_ms(uint8_t len) { return len; }
int t_settled = 1, t_module_calls;   /* what oled_view_modules says: every port has its verdict */
int oled_view_modules(scr_view_t *v, uint32_t now_ms) { (void)v; (void)now_ms; t_module_calls++; return t_settled; }

/* The buttons' pins: t_down[b] 1 holds button b down (its pin low). t_bounce_on_read b: the next read of
   button b's pin first raises an edge, as a release that bounces between the step's take and its read. */
int t_down[4], t_bounce_on_read;
int board_button_up(unsigned b)
{
  if (b >= 4U) return 0;
  if (t_bounce_on_read == (int)b) { t_bounce_on_read = 0; oled_app_button(b); }
  return !t_down[b];
}

unsigned t_view_extras(void) { return t_view.extra_frames; }
int t_view_acked(void) { return t_view.last_acked; }
int t_view_rssi(void) { return t_view.ack_rssi; }
int t_view_snr(void) { return t_view.ack_snr; }
unsigned t_view_seq(void) { return t_view.last_seq; }
unsigned t_view_cipher_len(void) { return t_view.cipher_len; }
unsigned t_view_cipher(unsigned i) { return t_view.cipher[i]; }
unsigned t_view_airtime(void) { return t_view.airtime_pct; }
unsigned t_view_reports(void) { return t_view.reports; }
unsigned t_view_radio_n(void) { return t_view.radio.n; }
int t_view_radio_rssi(unsigned i) { return t_view.radio.rssi[i]; }
int t_view_radio_snr(unsigned i) { return t_view.radio.snr[i]; }
unsigned t_view_since_exchange(void) { return t_view.since_exchange_s; }
unsigned t_view_check(void) { return t_view.check; }
unsigned t_base(unsigned id) { return (scr_defs[id].flags & SCR_F_BASE) != 0U; }
'''


def build(owner, name):
    """scr_sched.c and oled_app.c (and the drawing surface) over the shim, as the bench build compiles them (RAM2 placement off)."""
    return host_library(owner, name, '-DWS_BENCH_OLED=1', '-DOLED_APP_RAM2=', '-I', ROOT/'firmware/host/include', '-I', APP,
                        '-I', NODE/'Core/Inc', '-I', ROOT/'firmware/common', '-I', ROOT/'firmware',
                        APP/'scr_sched.c', APP/'oled_app.c', APP/'scr_screens.c', APP/'scr_calc.c', APP/'scr_widget.c', ROOT/'firmware/common/oled_draw.c',
                        ROOT/'firmware/common/oled_font.c', ROOT/'firmware/common/font5x7.c', files={'shim.c': SHIM})


def ival(lib, name):
    return ctypes.c_int.in_dll(lib, name).value


@needs_cc
class Scheduler(unittest.TestCase):
    """scr_sched.c on its own (with the shim's frame counts)."""
    @classmethod
    def setUpClass(cls):
        cls.built = build(cls, 'scrsched')

    def setUp(self):
        self.lib = fresh_copy(type(self), self.built._name)
        self.lib.sched_step.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_uint),
                                        ctypes.POINTER(ctypes.c_int)]
        self.lib.sched_event.argtypes = [ctypes.c_int, ctypes.c_uint32]
        self.lib.sched_init.argtypes = [ctypes.c_uint32]
        self.lib.sched_check.restype = ctypes.c_int
        self.now = 0
        self.lib.sched_init(self.now)
        self.event(EV_SETTLED)   # every port has its verdict at once: the checklist shows only its outcome

    def boot(self):
        """sched_init again, the modules not settled."""
        self.now = 0
        self.lib.sched_init(self.now)

    def step(self):
        """One 125 ms step: (drawn, screen, frame)."""
        sid, frame, on = ctypes.c_int(), ctypes.c_uint(), ctypes.c_int()
        drawn = self.lib.sched_step(self.now, ctypes.byref(sid), ctypes.byref(frame), ctypes.byref(on))
        self.assertEqual(on.value, 1)
        self.now = (self.now + STEP_MS) & 0xFFFFFFFF
        return drawn, SCREENS[sid.value], frame.value

    def event(self, ev):
        self.lib.sched_event(ev, self.now)

    def steps(self, n):
        return [self.step() for _ in range(n)]

    def to_home(self):
        """Steps through the boot screens; returns them. The step that showed HOME is taken."""
        seen = []
        while True:
            s = self.step()
            if s[1] == 'HOME':
                return seen
            seen.append(s)
            self.assertLess(len(seen), 1000)

    @staticmethod
    def runs(steps):
        """The screens in turn: [(screen, steps it stayed)], whatever was drawn."""
        out = []
        for _, screen, frame in steps:
            if out and out[-1][0] == screen and frame != 0:
                out[-1][1] += 1
            else:
                out.append([screen, 1])
        return [tuple(r) for r in out]

    @staticmethod
    def plays(steps):
        """The plays drawn (interludes, packet and boot screens, whatever is not a base screen): [(screen, [frames])]."""
        out = []
        for drawn, screen, frame in steps:
            if screen in ('HOME', 'AIR', 'PRESSURE', 'POWER', 'RADIO') or not drawn:
                continue
            if out and out[-1][0] == screen and frame == out[-1][1][-1] + 1:
                out[-1][1].append(frame)
            else:
                out.append((screen, [frame]))
        return out

    def test_boot_then_hack(self):
        # From sched_init: the 72 boot splash frames, the checklist's 16 (settled already), then the 24 of HACK THE
        # PLANET, then HOME.
        seen = self.to_home()
        self.assertEqual(seen, [(1, 'BOOT', f) for f in range(72)] + [(1, 'MODULES', f) for f in range(16)] +
                         [(1, 'HACK', f) for f in range(24)])
        self.assertEqual(self.lib.sched_check(), CHECK_DONE)

    def test_the_checklist_holds_until_the_modules_settle(self):
        # Not settled: the checklist holds, every frame drawn, its frame counting on; EV_SETTLED at its frame 200
        # ends the wait at the next step, and it shows the outcome for its 16 frames, still counting, then HACK.
        self.boot()
        self.steps(FRAMES['BOOT'])
        held = self.steps(200)
        self.assertEqual(held, [(1, 'MODULES', f) for f in range(200)])
        self.assertEqual(self.lib.sched_check(), CHECK_WAIT)
        self.event(EV_SETTLED)
        tail = self.steps(17)
        self.assertEqual(tail[:16], [(1, 'MODULES', f) for f in range(200, 216)])
        self.assertEqual(tail[16], (1, 'HACK', 0))
        self.assertEqual(self.lib.sched_check(), CHECK_DONE)
        self.event(EV_SETTLED)   # more do nothing
        self.assertEqual(self.to_home()[-1], (1, 'HACK', 23))

    def test_the_checklist_ends_at_its_cap(self):
        # Never settled: the wait ends at the first step at or after 60 s from sched_init (frame 408 of the checklist,
        # which starts at 9 s), with the outcome TIMEOUT.
        self.boot()
        seen = self.to_home()
        modules = [f for _, s, f in seen if s == 'MODULES']
        self.assertEqual(modules, list(range(len(modules))))
        self.assertEqual(len(modules), (CAP_MS - FRAMES['BOOT'] * STEP_MS) // STEP_MS + 16)
        self.assertEqual(self.lib.sched_check(), CHECK_TIMEOUT)

    def test_settled_during_the_splash(self):
        # EV_SETTLED before the checklist is up: the checklist shows only its outcome.
        self.boot()
        self.steps(10)
        self.event(EV_SETTLED)
        self.assertEqual(len(self.to_home()), BOOT_STEPS - 10)

    def test_the_cap_counts_from_sched_init_across_the_wrap(self):
        self.now = 0xFFFFFFFF - 20000
        start = self.now
        self.lib.sched_init(self.now)
        seen = self.to_home()
        hack = next(i for i, (_, s, _) in enumerate(seen) if s == 'HACK')
        self.assertEqual(seen[hack - 17][1], 'MODULES')   # the wait, then the outcome's 16 frames
        self.assertGreaterEqual((start + (hack - 16) * STEP_MS) & 0xFFFFFFFF, (start + CAP_MS) & 0xFFFFFFFF)
        self.assertEqual(self.lib.sched_check(), CHECK_TIMEOUT)

    def test_home_then_each_detail_screen_for_15_s(self):
        # HOME 15 s, a detail screen 15 s, HOME, the next one: AIR, PRESSURE, POWER, RADIO, SCOPE, VANE, RAIN, SYSTEM.
        self.to_home()
        got = self.runs(self.steps(DWELL - 1 + 2 * DWELL * 3))   # before the first interlude
        self.assertEqual(got[0], ('HOME', DWELL - 1))
        self.assertEqual(got[1:], [r for d in DETAILS[:3] for r in ((d, DWELL), ('HOME', DWELL))])

    def test_the_detail_list_goes_round(self):
        self.to_home()
        got = [s for s, n in self.runs(self.steps(DWELL - 1 + 2 * DWELL * 12)) if s != 'HOME' and n == DWELL]
        self.assertEqual(got[:9], DETAILS + ['AIR'])

    def test_the_base_screens_are_home_and_the_detail_list(self):
        # scr_defs' SCR_F_BASE (a screen B1 picks dwells) and scr_sched.c's details[] (the detail list, pinned by
        # test_the_detail_list_goes_round) must name the same screens.
        self.assertEqual([s for i, s in enumerate(SCREENS) if self.lib.t_base(i)], ['HOME', *DETAILS])

    def test_base_screens_redraw(self):
        # HOME: every second step (its icon at 4 frames a second); AIR: its 8 frames of growing lines, then
        # once a second; VANE its 16 needle frames; an ACK redraws at the next step.
        self.to_home()
        home = self.steps(16)
        self.assertEqual([d for d, _, _ in home], [0, 1] * 8)   # the step that showed HOME (frame 0) was drawn
        self.event(EV_ACK)
        self.assertEqual(self.step()[0], 1)
        self.event(EV_B1)   # AIR
        air = self.steps(24)
        self.assertEqual([d for d, _, _ in air], [1] * 8 + [1] + [0] * 7 + [1] + [0] * 7)
        self.assertEqual([f for _, _, f in air], list(range(24)))
        for _ in range(5):
            self.event(EV_B1)   # PRESSURE, POWER, RADIO, SCOPE, VANE
        vane = self.steps(24)
        self.assertEqual({s for _, s, _ in vane}, {'VANE'})
        self.assertEqual([d for d, _, _ in vane], [1] * 16 + [1] + [0] * 7)

    def timed_runs(self, ms):
        """[(start ms, screen, steps)] over ms of steps."""
        out, t0 = [], self.now
        for screen, n in self.runs(self.steps(ms // STEP_MS)):
            out.append((t0, screen, n))
            t0 += n * STEP_MS
        return out

    @staticmethod
    def interludes_of(runs):
        """The runs that are interludes: a screen of the pool for its frames (a base screen dwells 120 steps)."""
        return [(t, s) for t, s, n in runs if s in INTERLUDES and n == FRAMES[s]]

    def test_interludes_every_two_minutes_in_their_order_when_home_is_up(self):
        # Each falls due 120 s after the last on a fixed phase from sched_init, starts at the first step HOME is up
        # at or after that (within a detail screen's 15 s), and the pool goes in its own order.
        start = self.now
        self.to_home()
        runs = self.timed_runs(10 * 120000 + 20000)
        got = self.interludes_of(runs)
        self.assertEqual([s for _, s in got], INTERLUDES + ['FORTUNE'])
        for k, (t, _) in enumerate(got, 1):
            due = start + k * 120000
            self.assertGreaterEqual(t, due)
            self.assertLess(t - due, DWELL * STEP_MS + STEP_MS)
        for i, (t, screen, _n) in enumerate(runs):   # after each one HOME
            if (t, screen) in got:
                self.assertEqual(runs[i + 1][1], 'HOME')

    def test_the_interlude_waits_for_home(self):
        # The first falls due at 120 s while RADIO is up (HOME 14-29 s, AIR, HOME, PRESSURE, HOME, POWER, HOME,
        # RADIO 119-134 s): it starts at 134 s, where HOME would come, and RADIO keeps its 15 s.
        self.to_home()
        runs = self.timed_runs(140000)
        self.assertIn((119000, 'RADIO', DWELL), runs)
        self.assertEqual(self.interludes_of(runs)[0], (134000, 'FORTUNE'))

    def test_packet_preempts_an_interlude_and_ends_on_home(self):
        # EV_SENT_LIVE while the fortune cookie is at its frame 10: the next step is BURST frame 0, then the 16 burst
        # frames, the 24 of the banner, and HOME, its full 15 s; the cookie does not come back.
        self.to_home()
        while self.step()[1:] != ('FORTUNE', 10):
            pass
        self.event(EV_SENT_LIVE)
        got = self.steps(16 + 24 + DWELL)
        self.assertEqual(got[0], (1, 'BURST', 0))
        self.assertEqual(self.runs(got), [('BURST', 16), ('BANNER', 24), ('HOME', DWELL)])
        self.assertEqual([d for d, s, _ in got if s in ('BURST', 'BANNER')], [1] * 40)

    def test_packet_preempts_a_detail_screen(self):
        # The detail screen does not come back: HOME, then the cycle's next (AIR: the one B1 picked was no turn).
        self.to_home()
        self.event(EV_B1)
        self.steps(30)
        self.event(EV_SENT_LIVE)
        self.assertEqual(self.runs(self.steps(16 + 24 + DWELL + 1)), [('BURST', 16), ('BANNER', 24), ('HOME', DWELL), ('AIR', 1)])

    def test_packet_during_the_boot_screens(self):
        # The splash and the checklist go on through a packet (the first latch sends one as the modules settle):
        # no burst, every frame drawn. HACK, after them, is preempted as any screen.
        self.boot()
        self.steps(5)
        self.event(EV_SENT_LIVE)
        self.assertEqual(self.step(), (1, 'BOOT', 5))
        self.steps(FRAMES['BOOT'] - 6)
        self.steps(30)   # the checklist, waiting
        self.event(EV_SENT_LIVE)
        self.event(EV_SETTLED)
        self.assertEqual(self.step(), (1, 'MODULES', 30))
        self.assertEqual(self.runs(self.steps(15 + 2)), [('MODULES', 15), ('HACK', 2)])
        self.event(EV_SENT_LIVE)
        self.assertEqual(self.step(), (1, 'BURST', 0))

    def test_an_interlude_due_during_a_packet_waits(self):
        # The first falls due while the banner is up: it starts after the banner, at HOME, never over it.
        self.to_home()
        while self.now < 118000:
            self.step()
        self.event(EV_SENT_LIVE)
        got = self.runs(self.steps(16 + 24 + 64 + 1))
        self.assertEqual(got, [('BURST', 16), ('BANNER', 24), ('FORTUNE', 64), ('HOME', 1)])

    def test_extras_count_since_the_live_frame(self):
        self.to_home()
        self.event(EV_SENT_LIVE)
        for _ in range(3):
            self.event(EV_SENT_EXTRA)
        self.assertEqual(self.lib.sched_extras(), 3)
        self.event(EV_SENT_LIVE)
        self.assertEqual(self.lib.sched_extras(), 0)

    def test_the_clock_may_wrap(self):
        # clock_ms wraps after 49 days. Init 60 s before the wrap: the 120 s interlude time is already past it
        # while the clock is still above 0x80000000, where a plain `now >= at` comparison fires at once.
        self.now = 0xFFFFFFFF - 60000
        start = self.now
        self.lib.sched_init(self.now)
        self.to_home()
        got = self.interludes_of(self.timed_runs(140000))
        self.assertLess(self.now, 0x80000000)   # the steps did cross the wrap
        self.assertEqual([s for _, s in got], ['FORTUNE'])
        self.assertGreaterEqual((got[0][0] - start) & 0xFFFFFFFF, 120000)

    def test_b1_goes_through_every_screen(self):
        # B1: HOME, the detail screens, the silly ones and HACK, then HOME; each from its frame 0. Its order is
        # its own: not the interludes'.
        self.to_home()
        seen = []
        for _ in range(len(B1_ORDER)):
            self.event(EV_B1)
            seen.append(self.step()[1:])
        self.assertEqual(seen, [(s, 0) for s in B1_ORDER[1:] + ['HOME']])
        self.assertNotEqual(B1_ORDER[1:], INTERLUDES)

    def test_a_b1_screen_then_the_cycle(self):
        # A detail screen B1 picks stays its 15 s, then HOME; a silly one plays its frames, then HOME; then the
        # cycle's next detail screen (B1 is no turn of it).
        self.to_home()
        self.event(EV_B1)   # AIR
        self.assertEqual(self.runs(self.steps(DWELL + DWELL + 1)), [('AIR', DWELL), ('HOME', DWELL), ('AIR', 1)])
        for _ in range(9):
            self.event(EV_B1)   # ... FORTUNE, then FROG
        self.assertEqual(self.runs(self.steps(64 + DWELL + 1)), [('FROG', 64), ('HOME', DWELL), ('PRESSURE', 1)])

    def test_pause_stops_the_cycle_and_the_interludes(self):
        self.to_home()
        self.event(EV_B2)
        self.assertEqual(self.held_for(300000 // STEP_MS), {'HOME'})
        self.event(EV_SENT_LIVE)   # no burst, no banner: HOME stays
        self.assertEqual(self.held_for(16 + 24 + 1), {'HOME'})
        # Resume: HOME ends its dwell, the cycle goes on; the interludes start a full period from the press.
        self.event(EV_B2)
        runs = self.timed_runs(130000)
        self.assertEqual(runs[1][1], 'AIR')
        resumed = runs[0][0]
        got = self.interludes_of(runs)
        self.assertEqual([s for _, s in got], ['FORTUNE'])
        self.assertGreaterEqual(got[0][0] - resumed, 120000)

    def held_for(self, n):
        """The screens of n steps, as a set."""
        return {screen for _, screen, _ in self.steps(n)}

    def test_pause_holds_the_b1_screen(self):
        # Paused, the screen stays where B1 put it: a base screen again from frame 0 after each 15 s (its lines grow
        # in again), a play from frame 0 after its frames; no cycle, no interlude.
        self.to_home()
        self.event(EV_B1)
        self.event(EV_B2)
        got = self.steps(3 * DWELL)
        self.assertEqual(self.runs(got), [('AIR', DWELL)] * 3)
        self.assertEqual(self.held_for(300000 // STEP_MS), {'AIR'})
        for _ in range(9):
            self.event(EV_B1)   # FROG
        self.assertEqual(self.runs(self.steps(3 * 64)), [('FROG', 64)] * 3)

    def test_a_packet_keeps_the_held_screen(self):
        # Paused on PRESSURE: a packet plays no burst and no banner; PRESSURE goes on at its frame (no restart
        # from 0), drawn at the next step though it is between its redraws, then once a second as before.
        self.to_home()
        self.event(EV_B1)
        self.event(EV_B1)   # PRESSURE
        self.steps(5)
        self.event(EV_B2)
        self.steps(12)   # PRESSURE at its frame 17: a step between its once-a-second redraws
        self.event(EV_SENT_LIVE)
        got = self.steps(DWELL - 17 + 10)
        self.assertEqual(got[0], (1, 'PRESSURE', 17))
        self.assertEqual([d for d, _, _ in got[1:7]], [0] * 6)
        self.assertEqual(got[7], (1, 'PRESSURE', 24))
        self.assertEqual(self.runs(got), [('PRESSURE', DWELL - 17), ('PRESSURE', 10)])

    def test_a_packet_does_not_restart_a_held_play(self):
        # Paused on FROG at its frame 30: the frame counter is not reset by a packet, every frame still drawn.
        self.to_home()
        for _ in range(10):
            self.event(EV_B1)   # ... FORTUNE, FROG
        self.event(EV_B2)
        self.steps(30)
        self.event(EV_SENT_LIVE)
        got = self.steps(34 + 1)
        self.assertEqual(got[:34], [(1, 'FROG', f) for f in range(30, 64)])
        self.assertEqual(got[34], (1, 'FROG', 0))   # its own end: again from frame 0

    def test_a_packet_up_at_the_press_ends_on_home(self):
        # B2 during the burst: the burst and banner play out (they were up at the press), then HOME is held.
        self.to_home()
        self.event(EV_SENT_LIVE)
        self.steps(3)
        self.event(EV_B2)
        self.assertEqual(self.runs(self.steps(13 + 24 + 1)), [('BURST', 13), ('BANNER', 24), ('HOME', 1)])
        self.assertEqual(self.held_for(300000 // STEP_MS), {'HOME'})

    def test_b1_while_paused_moves_the_held_screen(self):
        self.to_home()
        self.event(EV_B1)
        self.event(EV_B2)
        self.steps(10)
        self.event(EV_B1)   # paused on AIR: PRESSURE is held now, from its frame 0
        self.assertEqual(self.step()[1:], ('PRESSURE', 0))
        self.assertEqual(self.held_for(300), {'PRESSURE'})
        for _ in range(len(B1_ORDER) - 2):   # round to HOME: HOME held is HOME
            self.event(EV_B1)
        self.assertEqual(self.held_for(300000 // STEP_MS), {'HOME'})
        self.event(EV_SENT_LIVE)
        self.assertEqual(self.held_for(16 + 24 + 1), {'HOME'})

    def test_b1_while_paused_during_a_packet(self):
        # B1 during a burst that was up at the B2 press: the next screen after the held one (HOME), as B1 always
        # leaves a packet.
        self.to_home()
        self.event(EV_SENT_LIVE)
        self.event(EV_B2)
        self.steps(3)
        self.event(EV_B1)
        self.assertEqual(self.step()[1:], ('AIR', 0))

    def test_resume_lets_the_held_screen_end(self):
        # B2 again: the held AIR stays to the end of its dwell, HOME follows, then the cycle's own next (AIR: B1 is
        # no turn of it).
        self.to_home()
        self.event(EV_B1)
        self.event(EV_B2)
        self.steps(DWELL + 20)   # the second dwell, at its frame 20
        self.event(EV_B2)
        self.assertEqual(self.runs(self.steps(DWELL - 20 + DWELL + 1)), [('AIR', DWELL - 20), ('HOME', DWELL), ('AIR', 1)])

    def test_pause_during_an_interlude_holds_it(self):
        self.to_home()
        while self.step()[1:] != ('FORTUNE', 30):
            pass
        self.event(EV_B2)
        self.assertEqual(self.held_for(300), {'FORTUNE'})

    def test_pause_during_the_boot_screens_holds_home(self):
        # A boot screen is in no order B1 knows: the boot splash and HACK play out, then HOME is held.
        self.steps(5)
        self.event(EV_B2)
        seen = self.to_home()
        self.assertEqual([s for s, _ in self.plays(seen)], ['BOOT', 'MODULES', 'HACK'])
        self.assertEqual(self.held_for(300000 // STEP_MS), {'HOME'})

    def test_b3_turns_display_off(self):
        self.to_home()
        self.steps(1)
        self.event(EV_B3)
        sid, frame, on = ctypes.c_int(), ctypes.c_uint(), ctypes.c_int()
        self.lib.sched_step(self.now, ctypes.byref(sid), ctypes.byref(frame), ctypes.byref(on))
        self.assertEqual(on.value, 0)
        self.now += STEP_MS
        self.event(EV_B3)
        self.assertEqual(self.step()[0], 1)   # on again, and HOME is redrawn at an odd frame too

    def test_display_on_is_known_before_the_step(self):
        self.to_home()
        self.assertEqual(self.lib.sched_display_on(), 1)
        self.event(EV_B3)
        self.assertEqual(self.lib.sched_display_on(), 0)
        self.event(EV_B3)
        self.assertEqual(self.lib.sched_display_on(), 1)

    def test_b2_while_off_does_nothing(self):
        # Like B1: a B2 press in the dark would pause unseen. Back on, the cycle goes on.
        self.to_home()
        self.event(EV_B3)
        self.event(EV_B2)
        self.event(EV_B3)
        self.assertEqual(self.runs(self.steps(DWELL)), [('HOME', DWELL - 1), ('AIR', 1)])


@needs_cc
class OledApp(unittest.TestCase):
    """oled_app.c: the timer only posts, the task draws; the exchange's hooks only note."""
    @classmethod
    def setUpClass(cls):
        cls.built = build(cls, 'oledapp')

    def setUp(self):
        self.lib = fresh_copy(type(self), self.built._name)
        self.lib.oled_note_sent.argtypes = [ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint8, ctypes.c_int]
        self.lib.oled_note_ack.argtypes = [ctypes.c_uint32, ctypes.c_int16, ctypes.c_int8]
        self.lib.oled_note_no_ack.argtypes = [ctypes.c_uint32]
        self.lib.oled_app_button.argtypes = [ctypes.c_uint]
        self.lib.oled_app_start()

    def set(self, name, value):
        ctypes.c_int.in_dll(self.lib, name).value = value

    def get(self, name):
        return ival(self.lib, name)

    def tick(self):
        self.assertEqual(self.lib.t_tick(), 1)   # every tick posts the task: the timer itself draws nothing
        return self.get('t_id'), self.get('t_frame')

    def to_home(self):
        for _ in range(BOOT_STEPS + 1):
            self.tick()
        self.assertEqual(SCREENS[self.get('t_id')], 'HOME')

    def test_start(self):
        # The driver starts, the 125 ms periodic timer runs; the view says nothing was sent yet.
        self.assertEqual((self.get('t_inits'), self.lib.t_timer_period()), (1, STEP_MS))
        self.tick()
        self.assertEqual((SCREENS[self.get('t_id')], self.get('t_frame'), self.lib.t_view_acked()), ('BOOT', 0, SCR_TX_NONE))
        self.assertEqual((self.get('t_expands'), self.get('t_sends')), (1, 1))

    def test_the_checklist_waits_for_the_modules(self):
        # oled_view_modules at every step tells the scheduler when the ports have their verdicts: until then the
        # checklist holds, the view saying WAIT; then it shows DONE for its 16 frames, and HACK follows.
        self.set('t_settled', 0)
        for _ in range(FRAMES['BOOT'] + 100):
            self.tick()
        self.assertEqual((SCREENS[self.get('t_id')], self.get('t_frame'), self.lib.t_view_check()), ('MODULES', 99, 0))
        self.assertEqual(self.get('t_module_calls'), FRAMES['BOOT'] + 100)
        self.set('t_settled', 1)
        self.assertEqual(self.tick(), (SCREENS.index('MODULES'), 100))
        self.assertEqual(self.lib.t_view_check(), 1)   # SCR_CHECK_DONE
        for _ in range(15):
            self.tick()
        self.assertEqual(self.tick(), (SCREENS.index('HACK'), 0))

    def test_packet_waits_for_frame_in_flight(self):
        # A frame is still going out (oled_dma_busy) when the live frame is sent: the hook draws nothing,
        # the tick that finds the driver busy does nothing (no draw into the buffer being sent, no send), and the burst starts at the next tick, from its frame 0.
        self.to_home()
        draws, sends = self.get('t_draws'), self.get('t_sends')
        self.set('t_busy', 1)
        self.lib.oled_note_sent(1234, bytes(range(40)), 40, 1)
        self.assertEqual(self.get('t_draws'), draws)
        self.tick()
        self.assertEqual((self.get('t_draws'), self.get('t_sends'), self.get('t_torn')), (draws, sends, 0))
        self.set('t_busy', 0)
        self.assertEqual(self.tick(), (SCREENS.index('BURST'), 0))
        self.assertEqual((self.get('t_sends'), self.get('t_expands') > 0, self.get('t_torn')), (sends + 1, True, 0))
        self.assertEqual((self.lib.t_view_seq(), self.lib.t_view_cipher_len()), (1234, 40))
        self.assertEqual([self.lib.t_view_cipher(i) for i in range(40)], list(range(40)))
        self.assertEqual(self.tick(), (SCREENS.index('BURST'), 1))

    def test_drain_shows_one_burst(self):
        # The live frame, its ACK, then 5 more (4 backlog and the health report): one burst, one banner that
        # counts the 4 and the report apart and shows the live frame's ACK, then HOME.
        self.to_home()
        cipher = bytes(range(100, 200))
        self.lib.oled_note_exchange()
        self.lib.oled_note_sent(77, cipher, len(cipher), SENT_LIVE)
        seen = [self.tick()]
        self.lib.oled_note_ack(77, -41, 9)
        for i in range(5):
            seen.append(self.tick())
            if i < 4:
                self.lib.oled_note_sent(60 + i, bytes(50), 50, SENT_BACKLOG)
            else:
                self.lib.oled_note_sent(0, bytes(50), 50, SENT_REPORT)   # the last is the health report
            if i < 4:
                self.lib.oled_note_ack(60 + i, -90, -12)   # the backlog's ACKs leave the live frame's outcome
        for _ in range(16 + 24 + 8 - len(seen)):
            seen.append(self.tick())
        bursts = [s for s in seen if s == (SCREENS.index('BURST'), 0)]
        self.assertEqual(len(bursts), 1)
        banner = [s for s in seen if s[0] == SCREENS.index('BANNER')]
        self.assertEqual(len(banner), 24)
        self.assertEqual(SCREENS[seen[-1][0]], 'HOME')
        self.assertEqual((self.lib.t_view_extras(), self.lib.t_view_reports(), self.lib.t_view_acked(), self.lib.t_view_rssi(),
                          self.lib.t_view_snr()), (4, 1, SCR_TX_ACK, -41, 9))   # 4 from the backlog, then the report
        self.assertEqual((self.lib.t_view_seq(), self.lib.t_view_cipher_len()), (77, 96))
        self.assertEqual([self.lib.t_view_cipher(i) for i in range(96)], list(cipher[:96]))
        # Airtime this minute: the shim's airtime is the length in ms, 100 + 5 x 50 = 350 ms of 60 s, rounded up.
        self.assertEqual(self.lib.t_view_airtime(), 1)

    def test_airtime_is_this_minutes_even_without_a_live_frame(self):
        # Each minute's exchange starts the airtime again (oled_note_exchange), also one whose journal append
        # failed and that sends backlog only. The shim's airtime is the length in ms.
        self.to_home()
        self.lib.oled_note_exchange()
        self.lib.oled_note_sent(1, bytes(250), 250, SENT_LIVE)
        for i in range(11):
            self.lib.oled_note_sent(100 + i, bytes(250), 250, SENT_BACKLOG)
        for _ in range(16 + 24 + 8):
            self.tick()
        self.assertEqual(self.lib.t_view_airtime(), 5)   # 3000 ms of 60 s
        self.lib.oled_note_exchange()   # the next minute: no live frame, 4 backlog frames
        for i in range(4):
            self.lib.oled_note_sent(200 + i, bytes(150), 150, SENT_BACKLOG)
        for _ in range(8):
            self.tick()
        self.assertEqual(self.lib.t_view_airtime(), 1)   # 600 ms, not 3600 ms on top of the last minute's

    def test_b3_on_redraws_at_once(self):
        # B3 on: the panel's power command, then HOME redrawn at the first step the driver is free, not at the
        # next 1 s redraw: the panel would show its stale frame until then.
        self.to_home()
        self.press(3)
        self.tick()
        draws = self.get('t_draws')
        for _ in range(3):
            self.tick()
        self.press(3)
        self.tick()   # the shim's driver is free at once
        self.assertEqual((self.get('t_enabled'), self.get('t_draws'), SCREENS[self.get('t_id')]), (1, draws + 1, 'HOME'))
        # And with a frame still going out (the power command follows it): drawn when the driver is free.
        self.press(3)
        self.tick()
        for _ in range(3):
            self.tick()
        draws = self.get('t_draws')
        self.set('t_busy', 1)
        self.press(3)
        self.tick()
        self.assertEqual((self.get('t_enabled'), self.get('t_draws')), (1, draws))   # B3 reached the driver while busy
        self.set('t_busy', 0)
        self.tick()
        self.assertEqual((self.get('t_draws'), SCREENS[self.get('t_id')]), (draws + 1, 'HOME'))

    def test_b3_reaches_a_driver_that_stays_busy(self):
        # A driver busy for good (a lost DMA interrupt, before its timeout): B3 off and on still reach it.
        self.to_home()
        self.set('t_busy', 1)
        calls = self.get('t_enable_calls')
        self.press(3)
        self.tick()
        self.assertEqual((self.get('t_enable_calls'), self.get('t_enabled')), (calls + 1, 0))
        self.press(3)
        self.tick()
        self.assertEqual((self.get('t_enable_calls'), self.get('t_enabled')), (calls + 2, 1))

    def test_no_ack_for_the_live_frame(self):
        self.to_home()
        self.lib.oled_note_sent(5, bytes(30), 30, 1)
        self.tick()
        self.assertEqual(self.lib.t_view_acked(), SCR_TX_WAIT)
        self.lib.oled_note_no_ack(5)
        self.tick()
        self.assertEqual(self.lib.t_view_acked(), SCR_TX_NO_ACK)

    def press(self, b):
        self.lib.oled_app_button(b)

    def test_button_bounce_and_wrap(self):
        # Three B1 edges within one step are one press; the interrupt only sets a flag (no draw, no event).
        self.to_home()
        for _ in range(3):
            self.press(1)
        self.assertEqual(SCREENS[self.get('t_id')], 'HOME')
        self.assertEqual(SCREENS[self.tick()[0]], 'AIR')
        self.assertEqual(self.tick(), (SCREENS.index('AIR'), 1))   # not skipped on to PRESSURE
        # A press a step from AIR comes round every screen to HOME.
        self.press(1)
        got = []
        for _ in range(len(B1_ORDER) - 1):
            got.append(SCREENS[self.tick()[0]])
            self.press(1)
        self.assertEqual(got, B1_ORDER[2:] + ['HOME'])

    def test_the_radio_history_and_the_exchange_clock(self):
        # Every frame's outcome goes into the radio history, the backlog's and the report's too: an ACK's RSSI and
        # SNR, a gap in both for none. The seconds since the minute's exchange started reach the view.
        self.to_home()
        self.lib.oled_note_exchange()
        self.lib.oled_note_sent(5, bytes(30), 30, SENT_LIVE)
        self.lib.oled_note_ack(5, -41, 9)
        self.lib.oled_note_sent(3, bytes(30), 30, SENT_BACKLOG)
        self.lib.oled_note_no_ack(3)
        self.lib.oled_note_sent(0, bytes(30), 30, SENT_REPORT)
        self.lib.oled_note_ack(0, -97, -8)
        for _ in range(8 * 3):
            self.tick()
        n = self.lib.t_view_radio_n()
        self.assertEqual([(self.lib.t_view_radio_rssi(i), self.lib.t_view_radio_snr(i)) for i in range(n)],
                         [(-41, 9), (-32768, -32768), (-97, -8)])
        self.assertEqual(self.lib.t_view_since_exchange(), 3)
        self.assertGreater(ival(self.lib, 't_samples'), 8 * 3)   # the histories are sampled at every step
        for i in range(40):
            self.lib.oled_note_ack(100 + i, -50 - i, 1)
        self.tick()
        self.assertEqual(self.lib.t_view_radio_n(), 30)
        self.assertEqual((self.lib.t_view_radio_rssi(0), self.lib.t_view_radio_rssi(29)), (-60, -89))   # the last 30

    def test_no_exchange_yet(self):
        self.to_home()
        self.assertEqual(self.lib.t_view_since_exchange() & 0xFFFFFFFF, 0xFFFFFFFF)   # SCR_NONE_S

    def adv(self, ms):
        self.lib.t_adv(ms)

    def step_now(self):
        """A step at the current clock (time does not move): (screen, frame) drawn."""
        self.assertEqual(self.lib.t_step(), 1)
        return self.get('t_id'), self.get('t_frame')

    def test_bounce_across_a_step_boundary_is_one_press(self):
        # B1 goes down, a step takes it, and 20 ms after the first edge the contact bounces: that edge, in the
        # next step, must not be a second press.
        self.to_home()
        self.adv(115)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('AIR'), 0))
        self.adv(20)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('AIR'), 1))   # not on to the vane

    def test_presses_200_ms_apart_with_a_step_between_are_two(self):
        self.to_home()
        self.adv(115)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('AIR'), 0))
        self.adv(200)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('PRESSURE'), 0))

    def test_a_long_bounce_train_stays_one_press(self):
        # An edge every 10 ms for 400 ms, steps every 125 ms in between: each edge is within 50 ms of the one
        # before, so only the first is a press and the scope plays on.
        self.to_home()
        seen = []
        for i in range(40):
            self.adv(10)
            self.press(1)
            if i % 12 == 11:
                seen.append(self.step_now())
        self.assertEqual(seen, [(SCREENS.index('AIR'), f) for f in range(len(seen))])

    def hold(self, b, down):
        """Button b's pin held down (low) or let up."""
        (ctypes.c_int * 4).in_dll(self.lib, 't_down')[b] = int(down)

    def test_release_bounce_after_the_debounce_is_no_second_press(self):
        # B1 goes down and a step takes it. 150 ms later, the button still down at every step, the contact
        # bounces: an edge 150 ms after the press passes the 50 ms edge filter, but no step has read B1 up
        # since the press, so it is no press. Up, a step sees it, then a real press: the vane.
        self.to_home()
        self.hold(1, True)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('AIR'), 0))
        self.adv(150)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('AIR'), 1))
        self.hold(1, False)
        self.adv(125)
        self.assertEqual(self.step_now(), (SCREENS.index('AIR'), 2))
        self.adv(100)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('PRESSURE'), 0))

    def test_release_bounce_before_a_step_saw_it_up(self):
        # The release and its bounce edge both come between two steps: the step that reads B1 up takes the edge
        # first, while B1 is not yet armed, so it is no press.
        self.to_home()
        self.hold(1, True)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('AIR'), 0))
        self.adv(100)
        self.hold(1, False)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('AIR'), 1))
        self.adv(200)
        self.press(1)   # a true second press: a step saw B1 up since the first
        self.assertEqual(self.step_now(), (SCREENS.index('PRESSURE'), 0))

    def test_a_bounce_between_the_take_and_the_pin_read(self):
        # B1 reads up, but an edge came after the step took the presses: the release may still be bouncing, so
        # B1 stays disarmed, and that edge, in the next step, is no press. The step after arms it.
        self.to_home()
        self.hold(1, True)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('AIR'), 0))
        self.adv(100)
        self.hold(1, False)
        ctypes.c_int.in_dll(self.lib, 't_bounce_on_read').value = 1
        self.assertEqual(self.step_now(), (SCREENS.index('AIR'), 1))
        self.adv(125)
        self.assertEqual(self.step_now(), (SCREENS.index('AIR'), 2))
        self.adv(125)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('PRESSURE'), 0))

    def test_each_button_is_armed_on_its_own(self):
        # B2 held down blocks only B2: B1 presses still count.
        self.to_home()
        self.hold(2, True)
        self.press(2)
        self.tick()
        self.press(1)
        self.assertEqual(SCREENS[self.tick()[0]], 'AIR')
        self.press(2)   # bounce while B2 is still down: no resume
        self.tick()
        for _ in range(64):   # still paused: the scope is held and plays again
            self.tick()
        self.assertEqual(SCREENS[self.get('t_id')], 'AIR')

    def test_b3_twice_restarts_a_faulted_display(self):
        # After "#oled fault" the steps draw nothing; B3 (off) then B3 (on) is oled_dma_enable(0), then
        # oled_dma_enable(1), which runs the driver's start-up again (test_oled_dma.py).
        self.to_home()
        self.set('t_faulted', 1)
        calls = self.get('t_enable_calls')
        self.press(3)
        self.tick()
        self.press(3)
        self.tick()
        self.assertEqual((self.get('t_enable_calls'), self.get('t_enabled')), (calls + 2, 1))

    def test_b3_turns_display_off(self):
        # B3: oled_dma_enable(0), and the steps draw nothing; B3 again: oled_dma_enable(1), and drawing resumes.
        self.to_home()
        calls, draws = self.get('t_enable_calls'), self.get('t_draws')
        self.press(3)
        self.tick()
        self.assertEqual((self.get('t_enable_calls'), self.get('t_enabled')), (calls + 1, 0))
        self.press(1)   # B1 does nothing while the display is off
        for _ in range(20):
            self.tick()
        self.assertEqual(self.get('t_draws'), draws)
        self.press(3)
        self.tick()
        self.assertEqual((self.get('t_enable_calls'), self.get('t_enabled')), (calls + 2, 1))
        for _ in range(8):   # the step that powered it did not draw; HOME is redrawn within a second
            self.tick()
        self.assertGreater(self.get('t_draws'), draws)
        self.assertEqual(SCREENS[self.get('t_id')], 'HOME')   # B1 while off changed nothing

    def test_a_press_while_the_driver_is_busy_is_kept(self):
        self.to_home()
        self.set('t_busy', 1)
        self.press(1)
        self.tick()
        draws = self.get('t_draws')
        self.set('t_busy', 0)
        self.tick()
        self.assertEqual((SCREENS[self.get('t_id')], self.get('t_draws') > draws), ('AIR', True))

    def test_a_gray_screen_draws_into_the_send_buffer_as_any_other(self):
        # MATRIX, gray, is drawn as every screen is: by scr_draw, on the send buffer turned for the panel, and
        # that buffer goes out.
        self.to_home()
        for _ in B1_ORDER[1:B1_ORDER.index('MATRIX') + 1]:
            self.press(1)
            self.tick()
        expands, sends = self.get('t_expands'), self.get('t_sends')
        self.assertEqual(SCREENS[self.get('t_id')], 'MATRIX')
        self.tick()
        self.assertEqual((SCREENS[self.get('t_id')], self.get('t_expands'), self.get('t_sends')), ('MATRIX', expands + 1, sends + 1))

    def test_a_faulted_display_is_not_drawn(self):
        # After a fault (oled_dma_send refuses with -2) the step draws nothing: no CPU spent on frames.
        self.to_home()
        draws = self.get('t_draws')
        self.set('t_faulted', 1)
        self.lib.oled_note_sent(5, bytes(30), 30, 1)
        for _ in range(10):
            self.tick()
        self.assertEqual(self.get('t_draws'), draws)


class FieldBuild(unittest.TestCase):
    @unittest.skipUnless(HAVE_ARM or os.environ.get('WS_REQUIRE_ARM') == '1', 'needs the ARM toolchain and vendor/')
    def test_field_build_hooks_are_noops(self):
        # WS_BENCH_OLED=0: tx_exchange.o references no oled_note_ symbol (the hooks are empty inline
        # functions). The bench build's does, so the check can see one.
        nm = TOOLCHAIN_GCC.with_name('arm-none-eabi-nm')
        for bench, build in ((0, 'build/tx'), (1, 'build/tx-oled')):
            with self.subTest(WS_BENCH_OLED=bench):
                r = subprocess.run(['make', '-C', str(NODE), 'ROLE=tx', f'WS_BENCH_OLED={bench}'], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-1500:])
                syms = subprocess.run([str(nm), str(NODE/build/'app/tx_exchange.o')], capture_output=True, text=True,
                                      check=True).stdout
                hooks = sorted(line.split()[-1] for line in syms.splitlines() if ' oled_note_' in line)
                self.assertEqual(hooks, ['oled_note_ack', 'oled_note_exchange', 'oled_note_no_ack', 'oled_note_sent'] if bench else [])

    def test_utilities_def_task_only_in_the_bench_build(self):
        # The display's sequencer task id exists only with WS_BENCH_OLED, so the field build's task table
        # (UTIL_SEQ_CONF_TASK_NBR) keeps its size.
        lines = (NODE/'Core/Inc/utilities_def.h').read_text().splitlines()
        at = next(i for i, line in enumerate(lines) if 'CFG_SEQ_Task_Oled' in line)
        self.assertIn('WS_BENCH_OLED', lines[at - 1])
        self.assertTrue(lines[at - 1].startswith('#if'))
        self.assertTrue(lines[at + 1].startswith('#endif'))


if __name__ == '__main__':
    unittest.main()
