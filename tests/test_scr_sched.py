"""The bench OLED's screen scheduler and its glue (firmware/stage0-node/App/scr_sched.c, oled_app.c).

scr_sched.c is pure: the tests step it as oled_app.c does, every 125 ms. oled_app.c is compiled unchanged
against a shim (below) that stands in for the DMA driver (a busy flag the test holds, the sends and
expansions it counts), the screens (scr_draw records what it was asked to draw, and the view it saw), the
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

SCREENS = ['NORMAL', 'BURST', 'BANNER', 'SCOPE', 'VANE', 'SYSTEM', 'BOOT', 'HACK']   # enum scr_id
FRAMES = {'NORMAL': 1, 'BURST': 16, 'BANNER': 24, 'SCOPE': 64, 'VANE': 64, 'SYSTEM': 64, 'BOOT': 64, 'HACK': 24}
EV_SENT_LIVE, EV_SENT_EXTRA, EV_ACK, EV_NO_ACK, EV_B1, EV_B2, EV_B3 = range(7)
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
#include "scr_view.h"
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
void ssd1325_frame(const oled_fb *fb, int rotate180, uint8_t out[OLED_FRAME_BYTES])
{ (void)fb; (void)rotate180; if (t_busy) t_torn++; if (out == txbuf) t_expands++; }

static const unsigned frames[SCR_COUNT] = { 1, 16, 24, 64, 64, 64, 64, 24 };
unsigned scr_frames(enum scr_id id) { return (unsigned)id < SCR_COUNT ? frames[id] : 1U; }
int t_draws, t_id = -1, t_frame = -1;
scr_view_t t_view;   /* what the last draw saw */
void scr_draw(oled_fb *fb, enum scr_id id, unsigned frame, const scr_view_t *v)
{ (void)fb; if (t_busy) t_torn++; t_draws++; t_id = (int)id; t_frame = (int)frame; t_view = *v; }
int t_fills;
void oled_view_fill(scr_view_t *v, enum scr_id id, unsigned frame) { (void)v; (void)id; (void)frame; t_fills++; }
uint32_t oled_view_airtime_ms(uint8_t len) { return len; }

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
'''


def build(owner, name):
    """scr_sched.c and oled_app.c over the shim, as the bench build compiles them (RAM2 placement off)."""
    return host_library(owner, name, '-DWS_BENCH_OLED=1', '-DOLED_APP_RAM2=', '-I', ROOT/'firmware/host/include', '-I', APP,
                        '-I', NODE/'Core/Inc', '-I', ROOT/'firmware/common', '-I', ROOT/'firmware',
                        APP/'scr_sched.c', APP/'oled_app.c', files={'shim.c': SHIM})


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

    def to_normal(self):
        """Steps through the boot screens; returns them."""
        seen = []
        while True:
            s = self.step()
            if s[1] == 'NORMAL':
                return seen
            seen.append(s)
            self.assertLess(len(seen), 1000)

    @staticmethod
    def plays(steps):
        """The interludes and packet screens drawn: [(screen, [frames])] in order."""
        out = []
        for drawn, screen, frame in steps:
            if screen == 'NORMAL' or not drawn:
                continue
            if out and out[-1][0] == screen and frame == out[-1][1][-1] + 1:
                out[-1][1].append(frame)
            else:
                out.append((screen, [frame]))
        return out

    def test_boot_then_hack(self):
        # From sched_init: the 64 boot splash frames, then the 24 of HACK THE PLANET, then NORMAL.
        seen = self.to_normal()
        self.assertEqual(seen, [(1, 'BOOT', f) for f in range(64)] + [(1, 'HACK', f) for f in range(24)])

    def test_interlude_every_two_minutes(self):
        # 120 s of steps after the boot screens: exactly one interlude, all 64 frames of the scope.
        self.to_normal()
        got = self.plays(self.steps(120000 // STEP_MS))
        self.assertEqual(got, [('SCOPE', list(range(64)))])
        # The rest come in turn, one every 120 s: vane, system bars, HACK THE PLANET, then the scope again.
        got = self.plays(self.steps(4 * 120000 // STEP_MS))
        self.assertEqual([s for s, _ in got], ['VANE', 'SYSTEM', 'HACK', 'SCOPE'])
        self.assertEqual([len(f) for _, f in got], [64, 64, 24, 64])

    def test_normal_redraws_once_a_second(self):
        # NORMAL is drawn at its first step and then every 8th; an ACK redraws it at the next step.
        self.to_normal()
        self.assertEqual([d for d, _, _ in self.steps(16)], ([0] * 7 + [1]) * 2)
        self.steps(3)
        self.event(EV_ACK)
        self.assertEqual(self.step()[0], 1)

    def test_packet_preempts_interlude(self):
        # EV_SENT_LIVE while the scope is at its frame 10: the next step is BURST frame 0, then the 16 burst
        # frames, the 24 of the banner, and NORMAL again; the scope does not come back.
        self.to_normal()
        while self.step()[1:] != ('SCOPE', 10):
            pass
        self.event(EV_SENT_LIVE)
        got = self.steps(16 + 24 + 8)
        self.assertEqual(got[0], (1, 'BURST', 0))
        self.assertEqual(self.plays(got), [('BURST', list(range(16))), ('BANNER', list(range(24)))])
        self.assertEqual(got[-1][1], 'NORMAL')

    def test_packet_during_the_boot_screens(self):
        # The radio exchange wins over the boot splash too.
        self.steps(5)
        self.event(EV_SENT_LIVE)
        self.assertEqual(self.step(), (1, 'BURST', 0))

    def test_an_interlude_due_during_a_packet_waits(self):
        # The scope falls due while the banner is up: it starts after the banner, never over it.
        self.to_normal()
        while self.now < 118000:
            self.step()
        self.event(EV_SENT_LIVE)
        got = self.plays(self.steps(16 + 24 + 64 + 8))
        self.assertEqual([s for s, _ in got], ['BURST', 'BANNER', 'SCOPE'])

    def test_extras_count_since_the_live_frame(self):
        self.to_normal()
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
        self.lib.sched_init(self.now)
        self.to_normal()
        self.assertEqual(self.plays(self.steps(100000 // STEP_MS)), [])   # nothing early, wrap or no wrap
        got = self.plays(self.steps(20000 // STEP_MS))
        self.assertLess(self.now, 0x80000000)   # the steps did cross the wrap
        self.assertEqual(got, [('SCOPE', list(range(64)))])

    def test_the_interlude_phase_does_not_drift(self):
        # The interludes start 120 s apart on the clock, not 120 s after the previous one ended its wait for NORMAL:
        # a packet delays one, the next stays on schedule.
        self.to_normal()
        starts = []
        while self.now < 11000 + 5 * 120000:
            if self.now == 119000:
                self.event(EV_SENT_LIVE)   # the first falls due at 120 s, inside the packet: it waits for NORMAL (124 s)
            drawn, screen, frame = self.step()
            if drawn and frame == 0 and screen in ('SCOPE', 'VANE', 'SYSTEM', 'HACK'):
                starts.append(self.now - STEP_MS)
        self.assertEqual(starts, [124000, 240000, 360000, 480000, 600000])

    def test_button_bounce_and_wrap(self):
        # B1 steps NORMAL, SCOPE, VANE, SYSTEM, HACK, NORMAL; the screen it picks plays from its frame 0.
        self.to_normal()
        seen = []
        for _ in range(5):
            self.event(EV_B1)
            seen.append(self.step()[1:])
        self.assertEqual(seen, [('SCOPE', 0), ('VANE', 0), ('SYSTEM', 0), ('HACK', 0), ('NORMAL', 0)])
        self.event(EV_B1)
        self.assertEqual(self.step()[1], 'SCOPE')   # round again

    def test_pause_stops_rotation(self):
        self.to_normal()
        self.event(EV_B2)
        self.assertEqual(self.plays(self.steps(300000 // STEP_MS)), [])
        self.event(EV_SENT_LIVE)   # packets still show
        got = self.plays(self.steps(16 + 24 + 8))
        self.assertEqual([s for s, _ in got], ['BURST', 'BANNER'])
        # Resume: the rotation starts a full period from the press, not at once for the time it was held.
        self.event(EV_B2)
        self.assertEqual(self.plays(self.steps(110000 // STEP_MS)), [])
        self.assertEqual([s for s, _ in self.plays(self.steps(20000 // STEP_MS))], ['SCOPE'])

    def held_for(self, n):
        """The screens of n steps, as a set."""
        return {screen for _, screen, _ in self.steps(n)}

    def test_pause_holds_the_b1_screen(self):
        # The design ("The buttons"): paused, the screen stays where B1 put it. The scope plays to its end and
        # again from frame 0, three times over, and NORMAL never comes back.
        self.to_normal()
        self.event(EV_B1)
        self.event(EV_B2)
        got = self.steps(3 * 64)
        self.assertEqual(self.plays(got), [('SCOPE', list(range(64)))] * 3)
        self.assertEqual({screen for _, screen, _ in got}, {'SCOPE'})
        self.assertEqual(self.held_for(300000 // STEP_MS), {'SCOPE'})   # no interlude either

    def test_a_packet_returns_to_the_held_screen(self):
        self.to_normal()
        self.event(EV_B1)
        self.event(EV_B1)   # the vane
        self.steps(5)
        self.event(EV_B2)
        self.steps(10)
        self.event(EV_SENT_LIVE)   # packets still show, then the vane again, from its frame 0
        got = self.plays(self.steps(16 + 24 + 64 + 10))
        self.assertEqual(got[:3], [('BURST', list(range(16))), ('BANNER', list(range(24))), ('VANE', list(range(64)))])
        self.assertEqual(got[3], ('VANE', list(range(10))))

    def test_b1_while_paused_moves_the_held_screen(self):
        self.to_normal()
        self.event(EV_B1)
        self.event(EV_B2)
        self.steps(10)
        self.event(EV_B1)   # paused on the scope: the vane is held now, from its frame 0
        self.assertEqual(self.step()[1:], ('VANE', 0))
        self.assertEqual(self.held_for(200), {'VANE'})
        for _ in range(3):   # system, HACK, then NORMAL: NORMAL held is NORMAL, as before any B1
            self.event(EV_B1)
        self.assertEqual(self.held_for(300000 // STEP_MS), {'NORMAL'})
        self.event(EV_SENT_LIVE)
        got = self.steps(16 + 24 + 8)
        self.assertEqual([s for s, _ in self.plays(got)], ['BURST', 'BANNER'])
        self.assertEqual(got[-1][1], 'NORMAL')

    def test_b1_while_paused_during_a_packet(self):
        # B1 during the burst while paused: the next screen after the held one, as B1 always leaves a packet.
        self.to_normal()
        self.event(EV_B1)
        self.event(EV_B2)
        self.event(EV_SENT_LIVE)
        self.steps(3)
        self.event(EV_B1)
        self.assertEqual(self.step()[1:], ('VANE', 0))

    def test_resume_lets_the_held_screen_end(self):
        # B2 again: the held scope plays to its end, NORMAL follows, and the rotation's next interlude is a full
        # period after the press.
        self.to_normal()
        self.event(EV_B1)
        self.event(EV_B2)
        self.steps(64 + 20)   # the second play, at its frame 20
        self.event(EV_B2)
        got = self.steps(44 + 8)
        self.assertEqual(self.plays(got), [('SCOPE', list(range(20, 64)))])
        self.assertEqual(got[-1][1], 'NORMAL')
        self.assertEqual(self.plays(self.steps(110000 // STEP_MS)), [])
        self.assertEqual([s for s, _ in self.plays(self.steps(20000 // STEP_MS))], ['SCOPE'])   # the rotation's first: B1 is no turn of it

    def test_pause_during_an_interlude_holds_it(self):
        # B2 while the rotation's scope is up: the scope is where the screen is, so it stays.
        self.to_normal()
        while self.step()[1:] != ('SCOPE', 30):
            pass
        self.event(EV_B2)
        self.assertEqual(self.held_for(200), {'SCOPE'})

    def test_pause_during_the_boot_screens_holds_normal(self):
        # A boot screen is in no order B1 knows: the boot splash and HACK play out, then NORMAL is held.
        self.steps(5)
        self.event(EV_B2)
        seen = self.to_normal()
        self.assertEqual([s for s, _ in self.plays(seen)], ['BOOT', 'HACK'])
        self.assertEqual(self.held_for(300000 // STEP_MS), {'NORMAL'})

    def test_b3_turns_display_off(self):
        self.to_normal()
        self.event(EV_B3)
        sid, frame, on = ctypes.c_int(), ctypes.c_uint(), ctypes.c_int()
        self.lib.sched_step(self.now, ctypes.byref(sid), ctypes.byref(frame), ctypes.byref(on))
        self.assertEqual(on.value, 0)
        self.event(EV_B3)
        self.assertEqual(self.step()[0], 1)   # on again, and NORMAL is redrawn

    def test_display_on_is_known_before_the_step(self):
        # oled_app.c powers the panel before it steps: sched_display_on says what B3 set, at once.
        self.to_normal()
        self.assertEqual(self.lib.sched_display_on(), 1)
        self.event(EV_B3)
        self.assertEqual(self.lib.sched_display_on(), 0)
        self.event(EV_B3)
        self.assertEqual(self.lib.sched_display_on(), 1)

    def test_b2_while_off_does_nothing(self):
        # Like B1: a B2 press in the dark would pause the rotation unseen. Back on, the interludes still come.
        self.to_normal()
        self.event(EV_B3)
        self.event(EV_B2)
        self.event(EV_B3)
        got = self.plays(self.steps(120000 // STEP_MS))
        self.assertEqual([s for s, _ in got], ['SCOPE'])


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

    def to_normal(self):
        for _ in range(64 + 24 + 1):
            self.tick()
        self.assertEqual(SCREENS[self.get('t_id')], 'NORMAL')

    def test_start(self):
        # The driver starts, the 125 ms periodic timer runs; the view says nothing was sent yet.
        self.assertEqual((self.get('t_inits'), self.lib.t_timer_period()), (1, STEP_MS))
        self.tick()
        self.assertEqual((SCREENS[self.get('t_id')], self.get('t_frame'), self.lib.t_view_acked()), ('BOOT', 0, SCR_TX_NONE))
        self.assertEqual((self.get('t_expands'), self.get('t_sends')), (1, 1))

    def test_packet_waits_for_frame_in_flight(self):
        # A frame is still going out (oled_dma_busy) when the live frame is sent: the hook draws nothing,
        # the tick that finds the driver busy does nothing (no draw, no expansion into the buffer being
        # sent, no send), and the burst starts at the next tick, from its frame 0.
        self.to_normal()
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
        # counts the 4 and the report apart and shows the live frame's ACK, then NORMAL.
        self.to_normal()
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
        self.assertEqual(SCREENS[seen[-1][0]], 'NORMAL')
        self.assertEqual((self.lib.t_view_extras(), self.lib.t_view_reports(), self.lib.t_view_acked(), self.lib.t_view_rssi(),
                          self.lib.t_view_snr()), (4, 1, SCR_TX_ACK, -41, 9))   # 4 from the backlog, then the report
        self.assertEqual((self.lib.t_view_seq(), self.lib.t_view_cipher_len()), (77, 96))
        self.assertEqual([self.lib.t_view_cipher(i) for i in range(96)], list(cipher[:96]))
        # Airtime this minute: the shim's airtime is the length in ms, 100 + 5 x 50 = 350 ms of 60 s, rounded up.
        self.assertEqual(self.lib.t_view_airtime(), 1)

    def test_airtime_is_this_minutes_even_without_a_live_frame(self):
        # Each minute's exchange starts the airtime again (oled_note_exchange), also one whose journal append
        # failed and that sends backlog only. The shim's airtime is the length in ms.
        self.to_normal()
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
        # B3 on: the panel's power command, then NORMAL redrawn at the first step the driver is free, not at the
        # next 1 s redraw: the panel would show its stale frame until then.
        self.to_normal()
        self.press(3)
        self.tick()
        draws = self.get('t_draws')
        for _ in range(3):
            self.tick()
        self.press(3)
        self.tick()   # the shim's driver is free at once
        self.assertEqual((self.get('t_enabled'), self.get('t_draws'), SCREENS[self.get('t_id')]), (1, draws + 1, 'NORMAL'))
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
        self.assertEqual((self.get('t_draws'), SCREENS[self.get('t_id')]), (draws + 1, 'NORMAL'))

    def test_b3_reaches_a_driver_that_stays_busy(self):
        # A driver busy for good (a lost DMA interrupt, before its timeout): B3 off and on still reach it.
        self.to_normal()
        self.set('t_busy', 1)
        calls = self.get('t_enable_calls')
        self.press(3)
        self.tick()
        self.assertEqual((self.get('t_enable_calls'), self.get('t_enabled')), (calls + 1, 0))
        self.press(3)
        self.tick()
        self.assertEqual((self.get('t_enable_calls'), self.get('t_enabled')), (calls + 2, 1))

    def test_no_ack_for_the_live_frame(self):
        self.to_normal()
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
        self.to_normal()
        for _ in range(3):
            self.press(1)
        self.assertEqual(SCREENS[self.get('t_id')], 'NORMAL')
        self.assertEqual(SCREENS[self.tick()[0]], 'SCOPE')
        self.assertEqual(self.tick(), (SCREENS.index('SCOPE'), 1))   # not skipped on to the vane
        # Five presses (one a step) from NORMAL come round to NORMAL: SCOPE VANE SYSTEM HACK NORMAL.
        self.press(1)
        got = []
        for _ in range(4):
            got.append(SCREENS[self.tick()[0]])
            self.press(1)
        self.assertEqual(got, ['VANE', 'SYSTEM', 'HACK', 'NORMAL'])

    def adv(self, ms):
        self.lib.t_adv(ms)

    def step_now(self):
        """A step at the current clock (time does not move): (screen, frame) drawn."""
        self.assertEqual(self.lib.t_step(), 1)
        return self.get('t_id'), self.get('t_frame')

    def test_bounce_across_a_step_boundary_is_one_press(self):
        # B1 goes down, a step takes it, and 20 ms after the first edge the contact bounces: that edge, in the
        # next step, must not be a second press.
        self.to_normal()
        self.adv(115)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('SCOPE'), 0))
        self.adv(20)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('SCOPE'), 1))   # not on to the vane

    def test_presses_200_ms_apart_with_a_step_between_are_two(self):
        self.to_normal()
        self.adv(115)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('SCOPE'), 0))
        self.adv(200)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('VANE'), 0))

    def test_a_long_bounce_train_stays_one_press(self):
        # An edge every 10 ms for 400 ms, steps every 125 ms in between: each edge is within 50 ms of the one
        # before, so only the first is a press and the scope plays on.
        self.to_normal()
        seen = []
        for i in range(40):
            self.adv(10)
            self.press(1)
            if i % 12 == 11:
                seen.append(self.step_now())
        self.assertEqual(seen, [(SCREENS.index('SCOPE'), f) for f in range(len(seen))])

    def hold(self, b, down):
        """Button b's pin held down (low) or let up."""
        (ctypes.c_int * 4).in_dll(self.lib, 't_down')[b] = int(down)

    def test_release_bounce_after_the_debounce_is_no_second_press(self):
        # B1 goes down and a step takes it. 150 ms later, the button still down at every step, the contact
        # bounces: an edge 150 ms after the press passes the 50 ms edge filter, but no step has read B1 up
        # since the press, so it is no press. Up, a step sees it, then a real press: the vane.
        self.to_normal()
        self.hold(1, True)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('SCOPE'), 0))
        self.adv(150)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('SCOPE'), 1))
        self.hold(1, False)
        self.adv(125)
        self.assertEqual(self.step_now(), (SCREENS.index('SCOPE'), 2))
        self.adv(100)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('VANE'), 0))

    def test_release_bounce_before_a_step_saw_it_up(self):
        # The release and its bounce edge both come between two steps: the step that reads B1 up takes the edge
        # first, while B1 is not yet armed, so it is no press.
        self.to_normal()
        self.hold(1, True)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('SCOPE'), 0))
        self.adv(100)
        self.hold(1, False)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('SCOPE'), 1))
        self.adv(200)
        self.press(1)   # a true second press: a step saw B1 up since the first
        self.assertEqual(self.step_now(), (SCREENS.index('VANE'), 0))

    def test_a_bounce_between_the_take_and_the_pin_read(self):
        # B1 reads up, but an edge came after the step took the presses: the release may still be bouncing, so
        # B1 stays disarmed, and that edge, in the next step, is no press. The step after arms it.
        self.to_normal()
        self.hold(1, True)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('SCOPE'), 0))
        self.adv(100)
        self.hold(1, False)
        ctypes.c_int.in_dll(self.lib, 't_bounce_on_read').value = 1
        self.assertEqual(self.step_now(), (SCREENS.index('SCOPE'), 1))
        self.adv(125)
        self.assertEqual(self.step_now(), (SCREENS.index('SCOPE'), 2))
        self.adv(125)
        self.press(1)
        self.assertEqual(self.step_now(), (SCREENS.index('VANE'), 0))

    def test_each_button_is_armed_on_its_own(self):
        # B2 held down blocks only B2: B1 presses still count.
        self.to_normal()
        self.hold(2, True)
        self.press(2)
        self.tick()
        self.press(1)
        self.assertEqual(SCREENS[self.tick()[0]], 'SCOPE')
        self.press(2)   # bounce while B2 is still down: no resume
        self.tick()
        for _ in range(64):   # still paused: the scope is held and plays again
            self.tick()
        self.assertEqual(SCREENS[self.get('t_id')], 'SCOPE')

    def test_b3_twice_restarts_a_faulted_display(self):
        # After "#oled fault" the steps draw nothing; B3 (off) then B3 (on) is oled_dma_enable(0), then
        # oled_dma_enable(1), which runs the driver's start-up again (test_oled_dma.py).
        self.to_normal()
        self.set('t_faulted', 1)
        calls = self.get('t_enable_calls')
        self.press(3)
        self.tick()
        self.press(3)
        self.tick()
        self.assertEqual((self.get('t_enable_calls'), self.get('t_enabled')), (calls + 2, 1))

    def test_b3_turns_display_off(self):
        # B3: oled_dma_enable(0), and the steps draw nothing; B3 again: oled_dma_enable(1), and drawing resumes.
        self.to_normal()
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
        for _ in range(8):   # the step that powered it did not draw; NORMAL is redrawn within a second
            self.tick()
        self.assertGreater(self.get('t_draws'), draws)
        self.assertEqual(SCREENS[self.get('t_id')], 'NORMAL')   # B1 while off changed nothing

    def test_a_press_while_the_driver_is_busy_is_kept(self):
        self.to_normal()
        self.set('t_busy', 1)
        self.press(1)
        self.tick()
        draws = self.get('t_draws')
        self.set('t_busy', 0)
        self.tick()
        self.assertEqual((SCREENS[self.get('t_id')], self.get('t_draws') > draws), ('SCOPE', True))

    def test_a_faulted_display_is_not_drawn(self):
        # After a fault (oled_dma_send refuses with -2) the step draws nothing: no CPU spent on frames.
        self.to_normal()
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
