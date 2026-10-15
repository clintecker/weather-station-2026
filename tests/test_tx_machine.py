"""The TX node's event-driven firmware (firmware/stage0-node/App/app_tx.c and the tx_*.c modules, as built) on the host.

firmware/host/tx_harness.c simulates the board: a virtual clock, timers and sequencer with ST's
semantics, a radio that follows ST's SubGHz_Phy driver, the SHT45, and the flash under the real
node_store.c. These tests check the exchange state machine (docs/firmware-event-model.md): every
state is left by an event that is certain to come, gaps are timers (no busy-wait), unexpected
events are counted, flash is never written while the radio is busy, and the link, health-report,
strike and watchdog policies. Every loop is bounded by simulated time, so a regression fails
instead of hanging. The library is built with UBSan; TxUnderAddressSanitizer reruns the suite with
ASan where the platform can preload its runtime. Host-model results, not bench evidence."""
import ctypes
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
try:                                        # first: sets WS0_UNSAFE_FAST_FSYNC before ws0 is imported
    from toolchain import MBEDTLS, ROOT, SAN, host_library, needs_cc, needs_vendor
except ImportError:
    from tests.toolchain import MBEDTLS, ROOT, SAN, host_library, needs_cc, needs_vendor
from ws0.fields import decode
from ws0.protocol import (KIND_ACK, KIND_DIAG, KIND_NACK, KIND_OBS, frame_counter, frame_kind, pack_reply, seal,
                          unseal)

STATION = 7
KEY = bytes(range(16, 32))
R_SLEEP, R_STANDBY, R_TX, R_RX = range(4)
SOURCES = ['host/tx_harness.c', 'sim_flash.c', 'stage0.c',
           *(f'stage0-node/App/{name}.c' for name in ('app_tx', 'tx_exchange', 'tx_policy', 'tx_time', 'tx_console', 'selftest',
                                                      'node_store', 'busymon', 'clock', 'events', 'bench')),
           *(f'common/{name}.c' for name in ('ws_console', 'ws_frame', 'ws_obs', 'ws_policy'))]
ASAN_ENV = 'WS_TX_ASAN'   # set by TxUnderAddressSanitizer for its child run

# What the firmware must do (docs/firmware-event-model.md, docs/radio-energy-policy.md, PRD 9). Written
# here once, from the specification, not read back from the firmware: a test that took its expectations
# from the code under test could not notice the code changing them.
SENSOR_MS = 10              # the harness SHT45's measurement time
SAMPLE_MS = 15_000
MINUTE_MS = 60_000
FIRST_REPORT_MS = 3 * SAMPLE_MS + SENSOR_MS   # samples at 0, 15, 30, 45 s; the report follows the 4th
ACK_WINDOW_MS = 2000
GAP_MS = 50                 # before every further frame of an exchange
TX_TIMEOUT_MS = 3000        # ST driver's transmit timeout (radio_cfg.h WS_TX_TIMEOUT_MS)
REBOOT_DELAY_MS = 200
TX_FAIL_LIMIT = 10          # transmit failures in a row the watchdog tolerates
STRIKE_LIMIT = 10
LINK_K_SILENT = 3
NORMAL_BACKLOG = 5          # backlog frames per minute at NORMAL energy (Stage 0 is USB powered)
DIAG_PERIOD_MS = 900_000
EVENTS = ['tx-done', 'tx-timeout', 'rx-done', 'rx-timeout', 'rx-error', 'gap', 'ack-end']
# The radio in each exchange state (a gap after a refused first Send still has the radio asleep).
RADIO_IN_STATE = {'idle': {R_SLEEP}, 'gap': {R_STANDBY, R_SLEEP}, 'sending': {R_TX}, 'ack-wait': {R_RX},
                  'diag-sending': {R_TX}}
SEEDS = (2026, 1, 2, 3, 4)


def minute(k):
    """When minute k's report is journaled and its exchange starts (the live frame goes on air)."""
    return FIRST_REPORT_MS + k * MINUTE_MS


def exchange_limit_s(frames):
    """The watchdog's bound on one exchange (docs/firmware-event-model.md)."""
    return (frames + 1) * (TX_TIMEOUT_MS + ACK_WINDOW_MS + GAP_MS) // 1000 + 5


def ctr_block():
    """node_store.c's durable counter reservation step: an implementation detail the sweep must straddle."""
    return int(re.search(r'#define CTR_BLOCK (\d+)U', (ROOT/'firmware/stage0-node/App/node_store.c').read_text())[1])


class Replies:
    """The gateway's ACK counter allocator, as ws0.protocol.seal expects it."""
    station, kind = STATION, KIND_ACK

    def __init__(self):
        self.counter = 0

    def next(self):
        self.counter += 1
        return self.counter


class Node:
    """One fresh boot of the firmware: its own copy of the library, so every static starts at zero."""
    def __init__(self, library, tmp):
        path = Path(tmp)/f'node{random.getrandbits(48):x}.so'
        shutil.copy(library, path)
        self.lib = ctypes.CDLL(str(path))
        self.lib.h_output.restype = ctypes.c_char_p
        for name in ('h_now', 'h_send_at', 'h_last_rx_timeout', 'h_flash_ops_during_radio', 'h_flash_erases',
                     'h_tx_air_ms', 'h_timer_start_refused'):
            getattr(self.lib, name).restype = ctypes.c_uint32
        self.air = self.lib.h_tx_air_ms()
        self.replies = Replies()
        self.log = ''
        self.served = 0                     # frames serve() has already answered (or not)
        self.answers = []                   # (time, head) of every reply serve() sent
        self.lib.h_reset()
        key = (ctypes.c_uint8 * 16)(*KEY)
        if self.lib.h_provision(STATION, key) != 0:
            raise RuntimeError('tx_harness: provisioning the simulated flash failed')
        self.lib.h_boot()

    def out(self):
        text = self.lib.h_output().decode()
        self.log += text
        return text

    def now(self):
        return self.lib.h_now()

    def advance(self, ms):
        self.lib.h_advance(ms)

    def advance_to(self, t):
        if t < self.now():
            raise AssertionError(f'advance_to({t}) is in the past (now {self.now()})')
        self.lib.h_advance(t - self.now())

    def until(self, cond, limit_ms, what, step=1):
        """Advance in steps until cond(); fail (not hang) if it takes longer than limit_ms."""
        end = self.now() + limit_ms
        while not cond():
            if self.now() >= end:
                raise AssertionError(f'{what}: not within {limit_ms} ms\n{self.log[-1500:]}{self.out()}')
            self.advance(step)

    def radio(self):
        return self.lib.h_radio_state()

    def sent(self):
        return self.lib.h_frames_sent()

    def sends(self, start=0, kind=None):
        """[(time, kind)] of transmissions start.. (only `kind` if given)."""
        all_ = [(self.lib.h_send_at(i), frame_kind(bytes([self.lib.h_send_kind(i)]))) for i in range(start, self.sent())]
        return [s for s in all_ if kind is None or s[1] == kind]

    def frame(self):
        buf = (ctypes.c_uint8 * 256)()
        n = self.lib.h_last_frame(buf)
        return bytes(buf[:n])

    def last_observation(self):
        frame = self.frame()
        if frame_kind(frame) != KIND_OBS:
            raise AssertionError(f'the last frame is kind {frame_kind(frame)}, not an observation')
        head, _ = decode(unseal(KEY, STATION, KIND_OBS, frame))
        return frame, head

    def reply_packet(self, kind=KIND_ACK, utc=1_792_000_000, echo=None, seq=None):
        """The gateway's authentic reply to the frame just sent (or, with echo/seq, to another one)."""
        frame, head = self.last_observation()
        echo = frame_counter(frame) if echo is None else echo
        seq = head['sequence'] if seq is None else seq
        return seal(KEY, STATION, kind, self.replies, pack_reply(head['epoch'], seq, utc, echo))

    def reply(self, kind=KIND_ACK, utc=1_792_000_000, echo=None, seq=None):
        """Receive that reply now."""
        packet = self.reply_packet(kind, utc, echo, seq)
        self.rx(packet)
        return packet

    def rx(self, packet, rssi=-40, snr=10):
        self.lib.h_rx((ctypes.c_uint8 * len(packet))(*packet), len(packet), rssi, snr)

    def rx_crc(self, packet):
        self.lib.h_rx_crc((ctypes.c_uint8 * len(packet))(*packet), len(packet))

    def status(self):
        """STATUS, parsed: the #status, #counts and #timing fields in one dict."""
        self.out()
        self.lib.h_line(b'STATUS')
        fields = {}
        for line in self.lib.h_output().decode().splitlines():   # not kept in self.log
            if line.startswith(('#status', '#counts', '#timing')):
                fields.update(kv.split('=', 1) for kv in line.split()[1:] if '=' in kv)
        return fields

    def state(self):
        return self.status()['state']

    def serve(self, ms, answer=lambda head: KIND_ACK, step=10):
        """Run for ms as the gateway: once per ACK window (soon after it opens), answer(head) of the
        observation just sent gives the reply kind, None for silence, or a callable to run instead."""
        end = self.now() + ms
        while self.now() < end:
            sleeping = self.radio() == R_SLEEP
            self.advance(min(500 if sleeping else step, end - self.now()))
            if self.radio() == R_RX and self.sent() != self.served:
                self.served = self.sent()
                head = self.last_observation()[1]
                action = answer(head)
                if callable(action):
                    action(self)
                elif action is not None:
                    self.reply(kind=action)
                    self.answers.append((self.now(), head))


@needs_cc
@needs_vendor
class TxStateMachine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not MBEDTLS.exists():
            raise AssertionError(f'WS_REQUIRE_VENDOR=1 but {MBEDTLS} is missing; run tools/fetch-vendor.sh')
        fw = ROOT/'firmware'
        mbed = [MBEDTLS/'library'/f'{n}.c' for n in ('aes', 'ccm', 'block_cipher', 'platform_util', 'constant_time')]
        # UBSan works in a library ctypes loads; ASan needs its runtime loaded first (TxUnderAddressSanitizer).
        san = SAN if os.environ.get(ASAN_ENV) == '1' else [f.replace('address,', '') for f in SAN]
        lib = host_library(cls, 'txmachine', *san, '-I', fw/'host/include', '-I', fw/'stage0-node/App',
                           '-I', fw/'stage0-node/Core/Inc', '-I', fw, '-I', fw/'common', '-I', MBEDTLS/'include',
                           '-DMBEDTLS_CONFIG_FILE="ws_mbedtls_config.h"', '-DWS_FW_VERSION="host"',
                           '-DWS_FW_BUILD_ID=0UL', *[fw/s for s in SOURCES], *mbed)
        cls.library = lib._name
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.addClassCleanup(cls.tmp.cleanup)

    def node(self, storm=False):
        """A fresh node, with the invariants every test must keep checked at its end."""
        node = Node(self.library, self.tmp.name)
        self.addCleanup(lambda: self.assertEqual(node.lib.h_flash_ops_during_radio(), 0, 'flash written while the radio was busy'))
        self.addCleanup(lambda: self.assertEqual(node.lib.h_timer_start_refused(), 0, 'a running timer was started again (ST ignores that)'))
        if not storm:   # only the storm task re-posts itself forever; anything else is a livelock
            self.addCleanup(lambda: self.assertEqual(node.lib.h_task_saturations(), 0, 'main-loop tasks never settled'))
        return node

    def window(self, n, k=0, into=100):
        """Minute k's live frame is on air and its ACK window has been open `into` ms."""
        n.advance_to(minute(k) + n.air + into)
        self.assertEqual((n.radio(), n.state()), (R_RX, 'ack-wait'))

    # ---- the exchange, step by step ----

    def test_minute_exchange_then_health_report_after_a_gap(self):
        n = self.node()
        self.assertIn('#boot role=tx', n.out())
        n.advance(SENSOR_MS + 5)
        self.assertIn('#sensor ok t=2150 rh=4500', n.out())
        n.advance_to(minute(0))
        self.assertEqual((n.sent(), n.radio()), (1, R_TX))
        n.advance(n.air)                               # TxDone: the ACK window opens
        # Rx(0): no driver timer (ST's is left running by a CRC error); the firmware's own ends the window
        self.assertEqual((n.radio(), n.lib.h_last_rx_timeout(), n.lib.h_sw_rx_armed()), (R_RX, 0, 0))
        self.assertEqual(n.state(), 'ack-wait')
        n.advance(200)
        acked_at = n.now()
        n.reply()
        self.assertRegex(n.out(), r'#ack epoch=\d+ seq=0 found=1 time_sync=1 .* pending=0\n')  # journal marked
        self.assertEqual(n.state(), 'gap')             # the health report waits for the gap timer
        n.advance(GAP_MS - 1)
        self.assertEqual(n.sent(), 1)
        n.advance(1)
        self.assertEqual(n.sends(1), [(acked_at + GAP_MS, KIND_DIAG)])
        self.assertIn('#diag sent', n.out())
        n.advance(n.air)
        self.assertEqual((n.radio(), n.state(), n.status()['unexpected']), (R_SLEEP, 'idle', '0'))
        self.assertEqual(n.lib.h_healthy(), 1)

    def test_no_reply_closes_the_window_by_its_own_timeout(self):
        n = self.node()
        n.advance_to(minute(0) + n.air + ACK_WINDOW_MS - 1)
        self.assertEqual(n.radio(), R_RX)
        self.assertNotIn('#ack none', n.out())
        n.advance(1)
        self.assertIn('#ack none', n.out())
        self.assertEqual(n.radio(), R_STANDBY)         # the window's end stops the receiver
        n.advance(GAP_MS + n.air)                      # the health report after its gap, then idle
        self.assertEqual((n.sent(), n.radio(), n.state()), (2, R_SLEEP, 'idle'))

    def test_backlog_frames_follow_the_live_one_after_timer_gaps(self):
        n = self.node()
        n.advance_to(minute(2) - 1000)                 # minutes 0 and 1: no reply, both stay journaled
        start = n.sent()
        n.serve(MINUTE_MS - 2000)                      # minute 2: every frame answered
        obs = n.sends(start, KIND_OBS)
        self.assertEqual([h['sequence'] for _, h in n.answers], [2, 0, 1])   # live first, then the oldest
        self.assertEqual(len(obs), 3)
        for (answered, _), (sent, _) in zip(n.answers, obs[1:], strict=False):
            self.assertEqual(sent - answered, GAP_MS)  # a timer gap after each answered frame
        self.assertEqual(n.status()['unexpected'], '0')

    def test_every_frame_gets_its_own_full_window(self):
        # The window timer of an answered frame is stopped: ST's UTIL_TIMER_Start ignores a running
        # timer, so a forgotten one would end the next frame's window early.
        n = self.node()
        n.advance_to(minute(2) - 1)                    # two readings pending
        n.until(lambda: n.radio() == R_RX, 1000, 'live window')
        start = n.sent()
        n.reply()
        n.until(lambda: n.sent() == start + 1, 1000, 'first backlog frame')
        n.out()
        done = n.sends()[-1][0] + n.air
        n.advance_to(done + ACK_WINDOW_MS - 1)
        self.assertNotIn('#ack none', n.out())
        self.assertEqual(n.state(), 'ack-wait')
        n.advance(1)
        self.assertIn('#ack none', n.out())

    def test_stray_and_damaged_packets_keep_the_rest_of_the_window(self):
        n = self.node()
        self.window(n, into=500)
        n.rx(b'\x51' + bytes(40))                      # foreign, fails authentication
        self.assertIn('#ack reject', n.out())
        self.assertEqual(n.radio(), R_RX)              # listening again, same window, still no driver timer
        n.advance(300)
        n.rx_crc(bytes(33))                            # RxDone + RxError, as ST delivers it
        out = n.out()
        self.assertIn('#ack damaged payload; still listening', out)
        self.assertNotIn('#ack reject', out)           # the CRC-failed RxDone is the RxError's, not a frame
        n.advance(300)
        n.lib.h_rx_hdr()                               # a header failure
        self.assertIn('#ack damaged header; still listening', n.out())
        self.assertEqual((n.radio(), n.lib.h_sw_rx_armed()), (R_RX, 0))
        n.reply()                                      # the real ACK, 1.1 s into the window
        self.assertIn('#ack epoch=', n.out())
        n.advance(5000)
        t = n.status()
        self.assertEqual((t['unexpected'], t['state'], t['ack_rejects']), ('0', 'idle', '1'))
        self.assertNotIn('#ack none', n.log)

    def test_a_damaged_reply_does_not_end_the_window_early(self):
        n = self.node()
        self.window(n)
        n.rx_crc(bytes(33))
        n.advance(ACK_WINDOW_MS - 100 - 1)
        self.assertNotIn('#ack none', n.out())
        n.advance(1)                                   # the window still ends at 2 s
        self.assertIn('#ack none', n.out())
        n.advance(5000)
        self.assertEqual(n.status()['unexpected'], '0')

    def test_a_transmit_timeout_puts_the_stuck_radio_in_standby(self):
        n = self.node()
        n.advance_to(minute(0) + 5)
        self.assertEqual(n.radio(), R_TX)
        n.lib.h_tx_timeout()                           # ST's software timer: the radio is still transmitting
        self.assertIn('#error tx-timeout', n.out())
        self.assertEqual((n.radio(), n.state()), (R_STANDBY, 'gap'))   # the health report is due
        n.advance(5000)
        self.assertEqual(n.status()['unexpected'], '0')

    # ---- events that arrive together, or where no state expects them ----

    def test_two_events_before_the_main_loop_are_both_handled_in_bit_order(self):
        # The ACK arrives, then the window timer fires before the main loop has run: both bits are
        # pending. RxDone (bit 2) is handled before ack-end (bit 6), so the ACK counts and the late
        # window end is only an unexpected event in the gap.
        n = self.node()
        self.window(n)
        n.lib.h_hold(1)
        n.reply()
        n.advance(ACK_WINDOW_MS)
        n.lib.h_hold(0)
        out = n.out()
        self.assertIn('#ack epoch=', out)
        self.assertNotIn('#ack none', out)
        self.assertIn('#error unexpected event=ack-end state=gap', out)
        self.assertEqual(n.status()['unexpected'], '1')
        # TxTimeout (bit 1) and TxDone (bit 0) together: the frame did leave, so the window opens.
        n = self.node()
        n.advance_to(minute(0) + 5)
        n.lib.h_hold(1)
        n.lib.h_raw_event(1)                           # the driver's timeout callback ...
        n.advance(n.air)                               # ... and the TxDone, both before the main loop
        n.lib.h_hold(0)
        self.assertIn('#error unexpected event=tx-timeout state=ack-wait', n.out())
        self.assertEqual((n.state(), n.radio()), ('ack-wait', R_RX))

    def test_every_unlisted_state_event_pair_is_only_counted(self):
        # docs/firmware-event-model.md: every (state, event) pair not in its table is counted, printed
        # and otherwise ignored: the state, the radio and the transmissions do not change.
        raise_event = {
            'tx-done': lambda n: n.lib.h_raw_event(0), 'tx-timeout': lambda n: n.lib.h_raw_event(1),
            'rx-timeout': lambda n: n.lib.h_raw_event(2), 'rx-error': lambda n: n.lib.h_raw_event(3),
            'rx-done': lambda n: n.lib.h_raw_event(4),
            'gap': lambda n: self.assertEqual(n.lib.h_fire_timer(GAP_MS), 1),
            'ack-end': lambda n: self.assertEqual(n.lib.h_fire_timer(ACK_WINDOW_MS), 1)}
        listed = {'idle': [], 'gap': ['gap'], 'sending': ['tx-done', 'tx-timeout'],
                  'ack-wait': ['rx-done', 'rx-error', 'rx-timeout', 'ack-end'], 'diag-sending': ['tx-done', 'tx-timeout']}

        def reach(state):
            n = self.node()
            if state == 'idle':
                n.advance(1000)
            elif state == 'sending':
                n.advance_to(minute(0) + 5)
            else:
                self.window(n)
                if state != 'ack-wait':
                    n.reply()
                if state == 'diag-sending':
                    n.advance(GAP_MS + 5)
            return n

        for state, ok in listed.items():
            with self.subTest(state=state):
                n = reach(state)
                self.assertEqual(n.state(), state)
                count = 0
                for event in [e for e in EVENTS if e not in ok]:
                    before = (n.radio(), n.sent())
                    raise_event[event](n)
                    count += 1
                    self.assertIn(f'#error unexpected event={event} state={state}\n', n.out())
                    t = n.status()
                    self.assertEqual((t['state'], t['unexpected'], n.radio(), n.sent()), (state, str(count), *before), event)
                n.advance(10_000)                      # and the exchange still ends normally
                t = n.status()
                self.assertEqual((t['state'], t['unexpected'], n.radio()), ('idle', str(count), R_SLEEP))

    # ---- whose reply it is, and what it may change ----

    def test_an_authentic_ack_for_another_frame_keeps_the_window_open(self):
        n = self.node()
        self.window(n)
        frame, _ = n.last_observation()
        n.reply(echo=frame_counter(frame) - 1)         # authentic, but it echoes another transmission
        self.assertIn('time_sync=0', n.out())
        self.assertEqual((n.radio(), n.state()), (R_RX, 'ack-wait'))
        n.advance(100)
        n.reply()                                      # the real one still ends it
        self.assertEqual(n.state(), 'gap')
        n.advance(5000)
        self.assertNotIn('#ack none', n.out())

    def test_a_nack_for_another_frame_is_ignored(self):
        n = self.node()
        self.window(n)
        frame, _ = n.last_observation()
        n.reply(kind=KIND_NACK, echo=frame_counter(frame) - 1)
        self.assertIn('#nack ignored: not for the frame just sent', n.out())
        self.assertEqual((n.radio(), n.state()), (R_RX, 'ack-wait'))
        n.advance(ACK_WINDOW_MS)
        self.assertIn('#ack none', n.out())
        t = n.status()
        self.assertEqual((t['abandoned'], t['pending']), ('0', '1'))

    def test_a_nack_for_this_frame_abandons_the_record(self):
        n = self.node()
        self.window(n)
        n.reply(kind=KIND_NACK)
        self.assertRegex(n.out(), r'#nack epoch=\d+ seq=0 reason=\d+ abandoned=1\n')
        start = n.sent()
        n.serve(MINUTE_MS)                             # minute 1: nothing older is resent
        self.assertEqual(len(n.sends(start, KIND_OBS)), 1)
        self.assertEqual(n.status()['pending'], '0')

    def test_only_an_ack_for_the_frame_just_sent_sets_the_clock(self):
        n = self.node()
        self.window(n)
        u0 = 1_792_000_000
        old = n.reply(utc=u0)
        synced_at = n.now() // 1000
        self.assertIn('time_sync=1', n.out())
        self.assertEqual(int(n.status()['utc']), u0)
        self.window(n, k=1)
        n.rx(old)                                      # a replay: authentic, but for minute 0's frame
        self.assertRegex(n.out(), r'#ack .* time_sync=0 ')
        self.assertEqual(int(n.status()['utc']), u0 + n.now() // 1000 - synced_at)   # not set back
        self.assertEqual(n.state(), 'ack-wait')
        n.reply(utc=1_000_000)                         # this frame's ACK, but an implausible time
        self.assertRegex(n.out(), r'#ack .* time_sync=0 ')
        self.assertEqual(int(n.status()['utc']), u0 + n.now() // 1000 - synced_at)

    # ---- flash only with the radio idle ----

    def test_counter_reservations_never_meet_a_busy_radio(self):
        # A counter reservation writes flash once every CTR_BLOCK counters. Move that write across
        # every transmission of an exchange with a backlog, relistens and a health report.
        def junk_then_ack(n):
            n.rx(b'\x51' + bytes(40))
            n.advance(5)
            n.reply()
        for j in range(16):
            with self.subTest(before_boundary=j):
                n = self.node()
                self.assertEqual(n.lib.h_burn(ctr_block() - j), ctr_block() - j)
                n.advance_to(minute(2) - 1000)         # two unanswered minutes: a backlog of two
                n.serve(MINUTE_MS, answer=lambda head: junk_then_ack)
                self.assertEqual(n.lib.h_flash_ops_during_radio(), 0)
                self.assertEqual(n.status()['pending'], '0')

    def test_flash_commands_wait_for_the_radio_exchange(self):
        n = self.node()
        self.window(n)
        erases = n.lib.h_flash_erases()
        for cmd in (b'WIPE ERASE-ALL-NODE-STATE', b'TEST-FLASH-STORM', b'PROVISION 9 ' + b'00' * 16):
            n.lib.h_line(cmd)
            self.assertIn('#error busy', n.out())
        self.assertEqual((n.lib.h_flash_erases(), n.lib.h_resets()), (erases, 0))
        n.advance(5000)                                # the exchange ends; now it runs
        n.lib.h_line(b'WIPE ERASE-ALL-NODE-STATE')
        self.assertIn('#wipe ok', n.out())

    def test_console_commands_match_whole_names(self):
        n = self.node()
        n.out()
        n.lib.h_line(b'KAT')
        self.assertEqual(n.out(), '#kat pass\n')
        for line in (b'STATUS ', b'status', b'KAT2', b'PROVISION', b'WIPE', b'TEST-FLASH-STORMS', b'TEST-HANGS', b''):
            n.lib.h_line(line)
            self.assertEqual(n.out(), '#error unknown command\n', line)
        n.lib.h_line(b'PROVISION 9 ' + b'00' * 16)     # arguments follow the name's space
        self.assertEqual(n.out(), '#error already-provisioned (WIPE first)\n')
        self.assertEqual((n.lib.h_resets(), n.status()['provisioned']), (0, '1'))

    def test_commanded_reboot_comes_from_a_timer_and_stops_sampling(self):
        n = self.node()
        n.advance(100)
        n.lib.h_line(b'WIPE ERASE-ALL-NODE-STATE')
        self.assertIn('#wipe ok', n.out())
        self.assertEqual(n.lib.h_resets(), 0)          # no wait inside the command
        n.lib.h_line(b'WIPE ERASE-ALL-NODE-STATE')     # a retry while the reboot is pending
        self.assertIn('#error busy', n.out())
        n.advance(REBOOT_DELAY_MS - 1)
        self.assertEqual(n.lib.h_resets(), 0)
        n.advance(1)
        self.assertEqual(n.lib.h_resets(), 1)
        starts = n.lib.h_sensor_starts()               # (the harness does not really reset)
        n.advance(MINUTE_MS)
        self.assertEqual(n.lib.h_sensor_starts(), starts)

    def test_flash_storm_stops_sampling_and_exchanges(self):
        n = self.node(storm=True)
        n.advance_to(minute(0) - 5)                    # the minute's 4th measurement is in flight
        n.lib.h_line(b'TEST-FLASH-STORM')
        self.assertIn('#storm start', n.out())
        frames, starts = n.sent(), n.lib.h_sensor_starts()
        n.advance(3 * MINUTE_MS)
        self.assertEqual((n.sent(), n.lib.h_sensor_starts()), (frames, starts))
        self.assertNotIn('#sample ', n.out())
        self.assertEqual(n.lib.h_healthy(), 1)         # sampling stopped on purpose: not a fault

    # ---- policy: drain, failures, link, health reports, strikes ----

    def test_a_missed_reply_stops_the_drain(self):
        n = self.node()
        n.advance_to(minute(2) - 1000)                 # two readings pending
        start = n.sent()
        n.serve(MINUTE_MS - 2000, answer=lambda head: KIND_ACK if head['sequence'] == 2 else None)
        self.assertEqual(len(n.sends(start, KIND_OBS)), 2)   # live (answered), the oldest (not); no third

    def test_a_transmit_timeout_stops_the_drain(self):
        n = self.node()
        n.advance_to(minute(2) + 5)
        start = n.sent() - 1
        n.lib.h_tx_timeout()
        n.advance(MINUTE_MS - 2000)
        self.assertEqual(len(n.sends(start, KIND_OBS)), 1)

    def test_a_send_failure_on_a_backlog_frame_moves_on(self):
        n = self.node()
        n.advance_to(minute(2) - 1)                    # two readings pending
        n.until(lambda: n.radio() == R_RX, 1000, 'live window')
        answered = n.now()
        n.reply()
        n.lib.h_radio_send_fails(1)                    # the first backlog frame's Send is refused
        n.advance(GAP_MS + 1)
        self.assertIn('#error radio-busy', n.out())
        self.assertEqual(n.status()['tx_air_run'], '1')
        n.advance(GAP_MS)
        self.assertEqual(n.sends()[-1], (answered + 2 * GAP_MS, KIND_OBS))   # after another gap
        self.assertEqual(n.last_observation()[1]['sequence'], 1)

    def test_a_failed_health_report_ends_the_exchange(self):
        for fail in ('tx-timeout', 'send'):
            with self.subTest(fail=fail):
                n = self.node()
                self.window(n)
                n.reply()
                if fail == 'send':
                    n.lib.h_radio_send_fails(1)
                    n.advance(GAP_MS)
                else:
                    n.advance(GAP_MS + 5)
                    self.assertEqual((n.radio(), n.sends()[-1][1]), (R_TX, KIND_DIAG))
                    n.lib.h_tx_timeout()
                t = n.status()
                self.assertEqual((t['state'], n.radio(), t['tx_air_run']), ('idle', R_SLEEP, '1'))
                n.advance(MINUTE_MS)                   # the next minute runs normally
                self.assertEqual(n.status()['unexpected'], '0')

    def test_a_health_report_that_leaves_clears_the_transmit_failure_run(self):
        n = self.node()
        n.advance_to(minute(0) + 5)
        n.lib.h_tx_timeout()
        self.assertEqual(n.status()['tx_air_run'], '1')
        n.advance(GAP_MS + n.air)                      # the health report goes and finishes
        self.assertEqual((n.sends()[-1][1], n.status()['tx_air_run']), (KIND_DIAG, '0'))

    def test_transmit_failures_in_a_row_trip_the_watchdog_and_a_tx_done_clears_them(self):
        n = self.node()
        failures, end = 0, 30 * MINUTE_MS
        while failures <= TX_FAIL_LIMIT:
            n.until(lambda f=failures: n.radio() == R_TX and n.sent() > f, end - n.now(), f'transmission {failures + 1}')
            n.lib.h_tx_timeout()
            failures += 1
            self.assertEqual(n.status()['tx_air_run'], str(failures))
            self.assertEqual(n.lib.h_healthy(), int(failures <= TX_FAIL_LIMIT), failures)
        n.until(lambda: n.radio() == R_RX, end - n.now(), 'a transmission that finishes')
        self.assertEqual((n.status()['tx_air_run'], n.lib.h_healthy()), ('0', 1))

    def test_a_radio_that_never_finishes_trips_the_exchange_bound(self):
        # Send accepted, then neither TxDone nor the driver's TxTimeout: the watchdog check fails once
        # the exchange outlasts its worst case, and (on the board, the reset comes first) a minute that
        # still finds it busy holds its reading in RAM and starts no second exchange. Nothing touches
        # the flash while the hung radio counts as transmitting (node() checks that at the end).
        for pending in (0, 2):
            with self.subTest(backlog=pending):
                n = self.node()
                k = pending                            # `pending` unanswered minutes first
                n.advance_to(minute(k) - 1)
                n.lib.h_radio_hang(1)
                n.advance(1)
                start_s = minute(k) // 1000
                limit = exchange_limit_s(1 + pending)
                n.advance_to((start_s + limit + 1) * 1000 - 1)
                self.assertEqual(n.lib.h_healthy(), 1)
                n.advance(1)
                self.assertEqual(n.lib.h_healthy(), 0)
                frames = n.sent()
                self.assertEqual(n.lib.h_flash_ops_during_radio(), 0)
                journaled = n.status()['pending']
                n.advance_to(minute(k + 1) + 100)      # the next minute does not start another exchange
                out = n.out()
                self.assertIn('#busy previous exchange still running', out)
                self.assertRegex(out, rf'#sample epoch=\d+ seq={k + 1} .* journal=held ')
                self.assertEqual((n.sent(), n.status()['pending']), (frames, journaled))

    def test_a_reading_made_during_an_exchange_is_journaled_when_the_radio_goes_idle(self):
        # Flash is only written with the radio idle: minute 1's reading waits in RAM while minute 0's
        # frame hangs, is journaled as soon as that exchange (and its health report) ends, before the
        # next minute, and minute 2 sends it as backlog.
        n = self.node()
        n.advance_to(minute(0) - 1)
        n.lib.h_radio_hang(1)
        n.advance_to(minute(1) + 100)
        out = n.out()
        self.assertRegex(out, r'#sample epoch=\d+ seq=1 .* journal=held pending=1 ')
        self.assertIn('#busy previous exchange still running; reading held until it ends', out)
        self.assertEqual((n.status()['pending'], n.radio()), ('1', R_TX))
        n.lib.h_radio_hang(0)
        n.lib.h_tx_timeout()                           # the driver's timeout ends the hung frame at last
        self.assertEqual(n.state(), 'gap')             # the health report is still due: not idle yet
        self.assertNotIn('#held', n.out())
        n.advance(GAP_MS + n.air)                      # the report leaves; the radio sleeps
        out = n.out()
        self.assertRegex(out, r'#diag sent [^\n]*\n#held journaled seq=1 rc=0 pending=2\n$')
        t = n.status()
        self.assertEqual((t['state'], t['pending'], t['held_lost'], t['tx_fail_run']), ('idle', '2', '0', '0'))
        n.serve(minute(2) + MINUTE_MS - 1000 - n.now())
        self.assertEqual([h['sequence'] for _, h in n.answers], [2, 0, 1])   # live, then the oldest two
        self.assertEqual(n.status()['pending'], '0')

    def test_held_readings_keep_the_newest_when_more_minutes_wait(self):
        # Only a hung radio (which the watchdog resets within ~2 minutes) keeps an exchange busy for
        # minutes; two readings are held, and a third replaces the oldest, counted as held_lost.
        n = self.node()
        n.advance_to(minute(0) - 1)
        n.lib.h_radio_hang(1)
        n.advance_to(minute(2) + 100)
        self.assertNotIn('held-lost', n.out())
        n.advance_to(minute(3) + 100)
        self.assertIn('#error held-lost seq=1 (a newer reading replaced it; held_lost=1)', n.out())
        self.assertEqual((n.status()['held_lost'], n.status()['pending']), ('1', '1'))
        n.lib.h_radio_hang(0)
        n.lib.h_tx_timeout()
        n.advance(GAP_MS + n.air)
        out = n.out()
        self.assertEqual(re.findall(r'#held journaled seq=(\d+) rc=0', out), ['2', '3'])   # oldest first
        self.assertEqual(n.status()['pending'], '3')   # seq 0, 2 and 3; seq 1 was dropped

    def test_three_silent_minutes_mean_probing_with_no_backlog_until_a_reply(self):
        n = self.node()
        other = lambda head: lambda n: n.reply(seq=head['sequence'] + 1000)   # an ACK for no frame of ours  # noqa: E731
        for k in range(LINK_K_SILENT):
            n.serve(minute(k) + MINUTE_MS - 1000 - n.now(), answer=other)
            self.assertEqual('#link probing' in n.out(), k == LINK_K_SILENT - 1, k)
        start = n.sent()
        n.serve(3 * MINUTE_MS, answer=lambda head: None)
        self.assertEqual(len(n.sends(start, KIND_OBS)), 3)   # the live reading only, every minute
        self.assertEqual(n.status()['link'], 'probing')
        start = n.sent()
        n.serve(MINUTE_MS)                             # a probe answered: linked, and a health report says so
        self.assertIn('#link linked after', n.out())
        self.assertEqual([k for _, k in n.sends(start)], [KIND_OBS, KIND_DIAG])
        start = n.sent()
        n.serve(MINUTE_MS)                             # the backlog drains again, within the minute's limit
        self.assertEqual(len(n.sends(start, KIND_OBS)), 1 + NORMAL_BACKLOG)

    def test_a_health_report_at_least_every_15_minutes(self):
        n = self.node()
        n.serve(minute(62))
        diags = [t for t, _ in n.sends(kind=KIND_DIAG)]
        self.assertGreaterEqual(len(diags), 4)
        self.assertLess(diags[0], minute(1))           # the first right after boot
        for a, b in zip(diags, diags[1:], strict=False):
            self.assertTrue(DIAG_PERIOD_MS - 1000 <= b - a < DIAG_PERIOD_MS + MINUTE_MS, diags)   # whole RTC seconds

    def test_strikes_abandon_a_record_that_alone_stays_unanswered(self):
        n = self.node()
        n.serve(minute(1) - 1000, answer=lambda head: None)   # record seq 0: never answered from here on
        answer = lambda head: None if head['sequence'] == 0 else KIND_ACK   # noqa: E731
        for k in range(1, STRIKE_LIMIT + 1):
            n.serve(MINUTE_MS, answer=answer)          # live answered, seq 0 not: one strike each minute
            self.assertEqual('#abandon epoch=' in n.out(), k == STRIKE_LIMIT, k)
        self.assertEqual(n.status()['abandoned'], '1')
        start = n.sent()
        n.serve(MINUTE_MS, answer=answer)
        self.assertEqual(len(n.sends(start, KIND_OBS)), 1)    # no longer sent

    def test_no_strikes_while_nothing_is_answered(self):
        # The gateway answers only the probe that relinks: no exchange that resent the old reading
        # had an answer, so it never gets a strike however often it was sent.
        n = self.node()
        for k in range(4 * (LINK_K_SILENT + 1)):
            n.advance_to(minute(k) - 100)
            probing = n.status()['link'] == 'probing'
            if not probing:
                n.lib.h_radio_send_fails(1)            # the live frame fails, so the backlog goes
            n.serve(MINUTE_MS - 200, answer=lambda head, p=probing: KIND_ACK if p else None)
        self.assertGreater(len(re.findall(r'#ack none epoch=\d+ seq=0\n', n.log)), STRIKE_LIMIT)
        self.assertNotIn('#abandon', n.log)

    # ---- sensor ----

    def test_sensor_failure_and_a_measurement_that_never_ends(self):
        n = self.node()
        n.lib.h_sensor(-2, 0)
        n.advance(20)
        self.assertIn('#sensor fault rc=-2', n.out())
        n.lib.h_sensor(0, 1)                           # the 15 s measurement never completes (a driver bug:
        n.advance(MINUTE_MS)                           # sensor.c's guard timer makes it impossible) ...
        self.assertRegex(n.out(), r'#sample .* valid=0 rc=-1 n=0 ')  # ... later ones are refused, not waited for
        self.assertEqual((n.lib.h_sensor_starts(), n.lib.h_healthy()), (2, 1))

    # ---- everything at once ----

    def test_three_hours_of_mixed_link_keep_every_invariant(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                self.mixed_link(seed, 3 * 3600_000)

    def mixed_link(self, seed, duration):
        """Lost ACKs (whole windows run out), NACKs, junk, CRC and header failures, another frame's
        ACK, transmit timeouts, refused sends and moved counter reservations, at random; checked on
        every step: the radio matches the state, the watchdog check holds, and nothing unexpected."""
        n = self.node()
        rnd = random.Random(seed)
        while n.now() < duration:
            state = n.state()
            self.assertIn(n.radio(), RADIO_IN_STATE[state], (state, n.now()))
            if state == 'idle':
                if rnd.random() < 0.01:
                    n.lib.h_burn(rnd.randrange(64))
                n.advance(1000)
            else:
                n.advance(10)
            if n.radio() == R_RX and rnd.random() < 0.006:   # ~30 % of windows run out
                roll = rnd.random()
                frame, _ = n.last_observation()
                if roll < 0.5:
                    n.reply()
                elif roll < 0.58:
                    n.reply(kind=KIND_NACK)
                elif roll < 0.68:
                    n.rx(bytes(rnd.getrandbits(8) for _ in range(33)))
                elif roll < 0.78:
                    n.rx_crc(bytes(rnd.getrandbits(8) for _ in range(33)))
                elif roll < 0.88:
                    n.lib.h_rx_hdr()
                else:
                    n.reply(echo=frame_counter(frame) - 1)
            elif n.radio() == R_TX and rnd.random() < 0.01:
                n.lib.h_tx_timeout()
            if rnd.random() < 0.001:
                n.lib.h_radio_send_fails(1)
            self.assertEqual(n.lib.h_healthy(), 1, n.log[-2000:])
        n.out()
        self.assertEqual(n.status()['unexpected'], '0', n.log[-2000:])
        self.assertGreaterEqual(n.log.count('#sample '), duration // MINUTE_MS - 1)
        self.assertGreaterEqual(n.lib.h_flash_erases(), 5)   # 36 readings per journal page: pages started
        self.assertNotIn('#error journal', n.log)
        for what, least in (('#ack none', 20), ('#ack epoch=', 50), ('#ack damaged', 10), ('#nack epoch=', 5),
                            ('#ack reject', 5), ('#error tx-timeout', 2)):
            self.assertGreaterEqual(n.log.count(what), least, what)   # the run did reach these paths


def asan_runtime():
    """The ASan runtime to preload into Python (it must be loaded first), or None."""
    name = {'darwin': 'libclang_rt.asan_osx_dynamic.dylib', 'linux': 'libasan.so'}.get(sys.platform)
    if not name or not shutil.which('cc'):
        return None
    path = subprocess.run(['cc', f'-print-file-name={name}'], capture_output=True, text=True).stdout.strip()
    return path if os.path.isabs(path) and os.path.exists(path) else None


@needs_cc
@needs_vendor
class TxUnderAddressSanitizer(unittest.TestCase):
    """TxStateMachine again with the library built under ASan + UBSan, in a child Python with the
    ASan runtime preloaded (a library ctypes loads cannot start ASan itself)."""
    def test_state_machine_suite_under_asan(self):
        if os.environ.get(ASAN_ENV) == '1':
            self.skipTest('already the ASan run')
        runtime = asan_runtime()
        if not runtime:
            self.skipTest('no ASan runtime for this compiler')
        preload = 'DYLD_INSERT_LIBRARIES' if sys.platform == 'darwin' else 'LD_PRELOAD'
        env = dict(os.environ, **{ASAN_ENV: '1', preload: runtime, 'ASAN_OPTIONS': 'detect_leaks=0'})
        r = subprocess.run([sys.executable, '-m', 'unittest', 'tests.test_tx_machine.TxStateMachine'],
                           cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
        report = r.stderr[-6000:]
        if r.returncode and 'Ran ' not in r.stderr and 'Sanitizer:' not in r.stderr:
            self.skipTest(f'ASan could not start in this Python: {report[-300:]}')
        self.assertEqual(r.returncode, 0, report)


if __name__ == '__main__':
    unittest.main()
