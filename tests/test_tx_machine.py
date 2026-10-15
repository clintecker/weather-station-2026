"""The TX node's event-driven firmware (firmware/stage0-node/App/app_tx.c, unchanged) on the host.

firmware/host/tx_harness.c simulates the board: a virtual clock, timers, the sequencer, a radio that
finishes a frame in 30 ms and times out its receive window, the SHT45, and the flash under the real
node_store.c. These tests check the exchange state machine (docs/firmware-event-model.md): every
state is left by an event that is certain to come, gaps are timers (no busy-wait), unexpected
events are counted, and flash is never written while the radio is busy. Host-model results, not
bench evidence."""
import ctypes
import random
import re
import shutil
import tempfile
import unittest
from pathlib import Path
try:                                        # first: sets WS0_UNSAFE_FAST_FSYNC before ws0 is imported
    from toolchain import MBEDTLS, ROOT, host_library, needs_cc, needs_vendor
except ImportError:
    from tests.toolchain import MBEDTLS, ROOT, host_library, needs_cc, needs_vendor
from ws0.fields import decode
from ws0.protocol import KIND_ACK, KIND_NACK, KIND_OBS, frame_counter, frame_kind, pack_reply, seal, unseal

STATION = 7
KEY = bytes(range(16, 32))
R_SLEEP, R_STANDBY, R_TX, R_RX = range(4)
FIRST_REPORT_MS = 45_000 + 10   # samples at 0, 15, 30, 45 s; the report follows the 4th (10 ms)
SOURCES = ['host/tx_harness.c', 'stage0-node/App/app_tx.c', 'stage0-node/App/node_store.c',
          'stage0-node/App/busymon.c', 'stage0.c', 'common/ws_frame.c', 'common/ws_obs.c', 'sim_flash.c']


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
        for name in ('h_now', 'h_send_at', 'h_last_rx_timeout', 'h_flash_ops_during_radio', 'h_flash_erases'):
            getattr(self.lib, name).restype = ctypes.c_uint32
        self.replies = Replies()
        self.log = ''
        self.lib.h_reset()
        key = (ctypes.c_uint8 * 16)(*KEY)
        assert self.lib.h_provision(STATION, key) == 0
        self.lib.h_boot()

    def out(self):
        text = self.lib.h_output().decode()
        self.log += text
        return text

    def advance(self, ms):
        self.lib.h_advance(ms)

    def radio(self):
        return self.lib.h_radio_state()

    def frame(self):
        buf = (ctypes.c_uint8 * 256)()
        n = self.lib.h_last_frame(buf)
        return bytes(buf[:n])

    def last_observation(self):
        frame = self.frame()
        assert frame_kind(frame) == KIND_OBS
        head, _ = decode(unseal(KEY, STATION, KIND_OBS, frame))
        return frame, head

    def reply(self, kind=KIND_ACK, utc=1_792_000_000, echo=None):
        """The gateway's authentic reply to the frame just sent, received now."""
        frame, head = self.last_observation()
        echo = frame_counter(frame) if echo is None else echo
        packet = seal(KEY, STATION, kind, self.replies, pack_reply(head['epoch'], head['sequence'], utc, echo))
        self.rx(packet)

    def rx(self, packet, rssi=-40, snr=10):
        self.lib.h_rx((ctypes.c_uint8 * len(packet))(*packet), len(packet), rssi, snr)

    def timing(self):
        self.out()
        self.lib.h_line(b'STATUS')
        line = re.search(r'#timing .*', self.out())[0]
        return dict(kv.split('=') for kv in line.split()[1:])


@needs_cc
@needs_vendor
class TxStateMachine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not MBEDTLS.exists():
            raise AssertionError(f'WS_REQUIRE_VENDOR=1 but {MBEDTLS} is missing; run tools/fetch-vendor.sh')
        fw = ROOT/'firmware'
        mbed = [MBEDTLS/'library'/f'{n}.c' for n in ('aes', 'ccm', 'block_cipher', 'platform_util', 'constant_time')]
        lib = host_library(cls, 'txmachine', '-I', fw/'host/include', '-I', fw/'stage0-node/App',
                           '-I', fw/'stage0-node/Core/Inc', '-I', fw, '-I', fw/'common', '-I', MBEDTLS/'include',
                           '-DMBEDTLS_CONFIG_FILE="ws_mbedtls_config.h"', '-DWS_FW_VERSION="host"',
                           '-DWS_FW_BUILD_ID=0UL', *[fw/s for s in SOURCES], *mbed)
        cls.library = lib._name
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.addClassCleanup(cls.tmp.cleanup)

    def node(self, storm=False):
        node = Node(self.library, self.tmp.name)
        self.addCleanup(lambda: self.assertEqual(node.lib.h_flash_ops_during_radio(), 0, 'flash written while the radio was busy'))
        if not storm:   # only the storm task re-posts itself forever; anything else is a livelock
            self.addCleanup(lambda: self.assertEqual(node.lib.h_task_saturations(), 0, 'main-loop tasks never settled'))
        return node

    def test_minute_exchange_then_health_report_after_a_gap(self):
        n = self.node()
        self.assertIn('#boot role=tx', n.out())
        n.advance(15)
        self.assertIn('#sensor ok t=2150 rh=4500', n.out())
        n.advance(FIRST_REPORT_MS - 15)
        self.assertEqual((n.lib.h_frames_sent(), n.radio()), (1, R_TX))
        n.advance(30)                                  # TxDone: the ACK window opens
        # Rx(0): no driver timer (ST's is left running by a CRC error); the firmware's own ends the window
        self.assertEqual((n.radio(), n.lib.h_last_rx_timeout(), n.lib.h_sw_rx_armed()), (R_RX, 0, 0))
        self.assertEqual(n.timing()['state'], 'ack-wait')
        n.advance(200)
        acked_at = n.lib.h_now()
        n.reply()
        self.assertIn('#ack epoch=', n.out())
        self.assertEqual(n.timing()['state'], 'gap')   # the health report waits for the gap timer
        n.advance(49)
        self.assertEqual(n.lib.h_frames_sent(), 1)
        n.advance(1)
        self.assertEqual(n.lib.h_frames_sent(), 2)
        self.assertEqual(n.lib.h_send_at(1) - acked_at, 50)
        self.assertIn('#diag sent', n.out())
        n.advance(30)
        self.assertEqual((n.radio(), n.timing()['state'], n.timing()['unexpected']), (R_SLEEP, 'idle', '0'))
        self.assertEqual(n.lib.h_healthy(), 1)

    def test_no_reply_closes_the_window_by_its_own_timeout(self):
        n = self.node()
        n.advance(FIRST_REPORT_MS + 30 + 1999)
        self.assertEqual(n.radio(), R_RX)
        n.advance(1)
        self.assertIn('#ack none', n.out())
        self.assertEqual(n.radio(), R_STANDBY)         # the window's end stops the receiver
        n.advance(50 + 30)                             # the health report after its gap, then idle
        self.assertEqual((n.lib.h_frames_sent(), n.radio()), (2, R_SLEEP))

    def test_backlog_frames_are_separated_by_timer_gaps(self):
        n = self.node()
        n.advance(FIRST_REPORT_MS + 2 * 60_000)        # minutes 1 and 2: no reply, both stay journaled
        start = n.lib.h_frames_sent()
        while n.radio() != R_TX:                       # minute 3's live frame
            n.advance(10)
        while n.timing()['state'] != 'idle':
            if n.radio() == R_RX:
                n.reply()
            n.advance(1)
        obs = n.log.count('#ack epoch=')
        self.assertEqual(obs, 3)                       # live + the 2 backlog readings
        sends = [n.lib.h_send_at(i) for i in range(start, n.lib.h_frames_sent())]
        self.assertTrue(all(b - a >= 30 + 50 for a, b in zip(sends, sends[1:], strict=False)), sends)  # air time + gap
        self.assertEqual(n.timing()['unexpected'], '0')

    def test_stray_and_damaged_packets_keep_the_rest_of_the_window(self):
        n = self.node()
        n.advance(FIRST_REPORT_MS + 30 + 500)
        n.rx(b'\x51' + bytes(40))                      # foreign, fails authentication
        self.assertIn('#ack reject', n.out())
        self.assertEqual(n.radio(), R_RX)              # listening again, same window
        n.advance(300)
        n.lib.h_rx_crc((ctypes.c_uint8 * 33)(*bytes(33)), 33)   # RxDone + RxError, as ST delivers it
        self.assertIn('#ack damaged payload; still listening', n.out())
        n.advance(300)
        n.lib.h_rx_hdr()                               # a header failure
        self.assertIn('#ack damaged header; still listening', n.out())
        self.assertEqual(n.radio(), R_RX)
        n.reply()                                      # the real ACK, 1.1 s into the window
        self.assertIn('#ack epoch=', n.out())
        n.advance(5000)
        t = n.timing()
        self.assertEqual((t['unexpected'], t['state']), ('0', 'idle'))
        self.assertNotIn('#ack none', n.log)

    def test_a_damaged_reply_does_not_end_the_window_early(self):
        n = self.node()
        n.advance(FIRST_REPORT_MS + 30 + 100)
        n.lib.h_rx_crc((ctypes.c_uint8 * 33)(*bytes(33)), 33)
        n.advance(1899)
        self.assertNotIn('#ack none', n.out())
        n.advance(1)                                   # the window still ends at 2 s
        self.assertIn('#ack none', n.out())
        n.advance(5000)
        self.assertEqual(n.timing()['unexpected'], '0')

    def test_a_transmit_timeout_puts_the_stuck_radio_in_standby(self):
        n = self.node()
        n.advance(FIRST_REPORT_MS + 5)
        self.assertEqual(n.radio(), R_TX)
        n.lib.h_tx_timeout()                           # ST's software timer: the radio is still transmitting
        self.assertIn('#error tx-timeout', n.out())
        self.assertNotEqual(n.radio(), R_TX)
        n.advance(5000)
        self.assertEqual(n.timing()['unexpected'], '0')

    def test_unexpected_events_are_counted_not_acted_on(self):
        n = self.node()
        n.advance(1000)
        n.lib.h_raw_event(0)                           # a TxDone with nothing on air
        self.assertIn('#error unexpected event=tx-done state=idle', n.out())
        n.lib.h_raw_event(2)                           # an RxTimeout with no window open
        self.assertIn('#error unexpected event=rx-timeout state=idle', n.out())
        self.assertEqual((n.timing()['unexpected'], n.timing()['state']), ('2', 'idle'))

    def test_sensor_failure_and_a_measurement_that_never_ends(self):
        n = self.node()
        n.lib.h_sensor(-2, 0)
        n.advance(20)
        self.assertIn('#sensor fault rc=-2', n.out())
        n.lib.h_sensor(0, 1)                           # the 15 s measurement never completes (a driver bug:
        n.advance(60_000)                              # sensor.c's guard timer makes it impossible) ...
        self.assertRegex(n.out(), r'#sample .* valid=0 rc=-1 n=0 ')  # ... later ones are refused, not waited for
        self.assertEqual((n.lib.h_sensor_starts(), n.lib.h_healthy()), (2, 1))

    def test_commanded_reboot_comes_from_a_timer(self):
        n = self.node()
        n.advance(100)
        n.lib.h_line(b'WIPE ERASE-ALL-NODE-STATE')
        self.assertIn('#wipe ok', n.out())
        self.assertEqual(n.lib.h_resets(), 0)          # no wait inside the command
        n.lib.h_line(b'WIPE ERASE-ALL-NODE-STATE')     # a retry while the reboot is pending
        self.assertIn('#error busy', n.out())
        n.advance(199)
        self.assertEqual(n.lib.h_resets(), 0)
        n.advance(1)
        self.assertEqual(n.lib.h_resets(), 1)

    def test_flash_commands_wait_for_the_radio_exchange(self):
        n = self.node()
        n.advance(FIRST_REPORT_MS + 30 + 100)          # in the ACK window
        erases = n.lib.h_flash_erases()
        for cmd in (b'WIPE ERASE-ALL-NODE-STATE', b'TEST-FLASH-STORM', b'PROVISION 9 ' + b'00' * 16):
            n.lib.h_line(cmd)
            self.assertIn('#error busy', n.out())
        self.assertEqual((n.lib.h_flash_erases(), n.lib.h_resets()), (erases, 0))
        n.advance(5000)                                # the exchange ends; now it runs
        n.lib.h_line(b'WIPE ERASE-ALL-NODE-STATE')
        self.assertIn('#wipe ok', n.out())

    def test_flash_storm_stops_sampling_and_exchanges(self):
        n = self.node(storm=True)
        n.advance(20)
        n.lib.h_line(b'TEST-FLASH-STORM')
        self.assertIn('#storm start', n.out())
        frames = n.lib.h_frames_sent()
        n.advance(3 * 60_000)
        self.assertEqual(n.lib.h_frames_sent(), frames)
        self.assertNotIn('#sample ', n.out())

    def test_three_hours_of_mixed_link_keep_every_invariant(self):
        n = self.node()
        rnd = random.Random(2026)
        while n.lib.h_now() < 3 * 3600_000:
            idle = n.radio() == R_SLEEP and n.timing()['state'] == 'idle'
            n.advance(1000 if idle else 10)
            if n.radio() == R_RX and rnd.random() < 0.3:
                roll = rnd.random()
                if roll < 0.6:
                    n.reply()
                elif roll < 0.7:
                    n.reply(kind=KIND_NACK)
                elif roll < 0.8:
                    n.rx(bytes(rnd.getrandbits(8) for _ in range(33)))
                elif roll < 0.9:
                    junk = bytes(rnd.getrandbits(8) for _ in range(33))
                    n.lib.h_rx_crc((ctypes.c_uint8 * 33)(*junk), 33)
                else:
                    n.lib.h_rx_hdr()
            elif n.radio() == R_TX and rnd.random() < 0.01:
                n.lib.h_tx_timeout()
            if rnd.random() < 0.001:
                n.lib.h_radio_send_fails(1)
            self.assertEqual(n.lib.h_healthy(), 1, n.log[-2000:])
        n.out()
        self.assertEqual(n.timing()['unexpected'], '0', n.log[-2000:])
        self.assertGreaterEqual(n.log.count('#sample '), 179)
        self.assertGreaterEqual(n.lib.h_flash_erases(), 5)  # 36 readings per journal page: pages started during the run
        self.assertNotIn('#error journal', n.log)


if __name__ == '__main__':
    unittest.main()
