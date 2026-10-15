"""The RX bridge's event-driven firmware (firmware/stage0-node/App/app_rx.c and App/console.c,
unchanged) on the host.

firmware/host/rx_harness.c simulates the board: a clock in 1/1024 s RTC ticks with ST's timer server,
the sequencer, a radio in continuous receive that follows ST's SubGHz_Phy (a CRC failure is RxDone
with the HAL's CRC flag then RxError, a header failure is RxTimeout, the radio keeps receiving through
both; Send, TxDone, the driver's TxTimeout), the console UART's per-character receive interrupt, the
trace FIFO and the watchdog's 1 s health check. These tests check the bridge through its console
output and the radio calls (docs/firmware-event-model.md, RX): every valid frame is forwarded once,
nothing else is; failed receptions are logged whole and never forwarded; only a valid host ACK/NACK
goes on air, and the radio is listening again after it; the 60 s report comes from the main loop.
Host-model results, not bench evidence.

WS_RX_APP=<path> builds a modified copy of app_rx.c instead (mutation testing)."""
import ctypes
import os
import random
import re
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path
try:
    from toolchain import ROOT, host_library, needs_cc
except ImportError:
    from tests.toolchain import ROOT, host_library, needs_cc

RF_IDLE, RF_RX_RUNNING, RF_TX_RUNNING = range(3)
TX_NORMAL, TX_STUCK, TX_HANG = range(3)
LED_BLUE, LED_GREEN, LED_RED = range(3)
SOURCES = ['host/rx_harness.c', 'stage0-node/App/console.c', 'stage0-node/App/busymon.c', 'common/ws_console.c']
ALIVE_KEYS = ['uptime', 'forwarded', 'dropped', 'acks', 'diag', 'listening', 'relistens', 'uart_errors', 'stack_peak',
              'crc_errors', 'hdr_errors', 'fault_overruns', 'task_peak_us', 'task_peak', 'isr_peak_us', 'isr_peak',
              'trace_drops', 'frames_lost']
ALIVE_MS = 60_000
RELISTEN_S = 17 * 60    # silence > 16 min at a minute report: the first relisten comes at 1020 s
BOOT_LINE = '\n#boot role=rx fw=host reset=power freq=915000000 bw=2 sf=7 power=0\n'


def fields(line):
    return dict(kv.split('=', 1) for kv in line.split()[1:])


class Bridge:
    """One fresh boot of the RX firmware: its own copy of the library, so every static starts at zero."""
    def __init__(self, library, tmp, start_s=0):
        path = Path(tmp)/f'rx{random.getrandbits(48):x}.so'
        shutil.copy(library, path)
        self.lib = lib = ctypes.CDLL(str(path))
        lib.h_output.restype = ctypes.c_char_p
        for name in ('h_now_ms', 'h_now_ticks'):
            getattr(lib, name).restype = ctypes.c_uint64
        for name in ('h_rx_calls', 'h_standby_calls', 'h_sleep_calls', 'h_send_calls', 'h_sends', 'h_last_rx_timeout',
                     'h_max_not_rx_ms', 'h_wd_resets', 'h_wd_unhealthy', 'h_wd_checks', 'h_trace_drops', 'h_overlong',
                     'h_capture_overflow', 'h_primask_leaks', 'h_task_saturations', 'h_task_pending', 'h_uart_rearms',
                     'h_led_flashes', 'h_task_runs', 'h_sends_while_tx', 'h_rx_after_timeout_no_standby'):
            getattr(lib, name).restype = ctypes.c_uint32
        self.obs_min, self.obs_max, self.diag_len, self.ack_len, self.line_max, self.version = (lib.h_const(i) for i in range(6))
        self.log = ''
        lib.h_boot(start_s)

    # ---- console ----
    def out(self):
        text = self.lib.h_output().decode('latin-1')
        self.log += text
        return text

    def uart(self, data, run_each=True):
        data = data.encode('latin-1') if isinstance(data, str) else bytes(data)
        return self.lib.h_uart((ctypes.c_uint8 * max(1, len(data)))(*data), len(data), int(run_each))

    def line(self, text):
        self.uart(text + '\n')
        self.poll()

    # ---- time ----
    def advance(self, ms, run=True):
        self.lib.h_advance(ms, int(run))

    def poll(self):
        self.lib.h_poll()

    def now(self):
        return self.lib.h_now_ms()

    def mcu_ms(self):
        """ms_now() as the firmware computes it (SysTimeGetMcuTime), modulo 2^32."""
        t = self.lib.h_now_ticks()
        return ((t >> 10) * 1000 + ((t & 1023) * 1000 >> 10)) & 0xFFFFFFFF

    # ---- radio ----
    def radio(self):
        return self.lib.h_radio_state()

    def _inject(self, fn, frame, rssi, snr, run):
        frame = bytes(frame)
        got = fn((ctypes.c_uint8 * max(1, len(frame)))(*frame), len(frame), rssi, snr)
        if run:
            self.poll()
        return got

    def rx(self, frame, rssi=-40, snr=9, run=True):
        return self._inject(self.lib.h_rx, frame, rssi, snr, run)

    def crc(self, frame, rssi=-100, snr=-12, run=True):
        return self._inject(self.lib.h_rx_crc, frame, rssi, snr, run)

    def rx_error_only(self, frame, rssi=-101, snr=-13, run=True):
        return self._inject(self.lib.h_rx_error_only, frame, rssi, snr, run)

    def hdr(self, rssi=-97, run=True):
        got = self.lib.h_rx_hdr(rssi)
        if run:
            self.poll()
        return got

    def sent(self):
        buf = (ctypes.c_uint8 * 256)()
        return bytes(buf[:self.lib.h_last_sent(buf)])

    # ---- reports ----
    def status(self):
        self.out()
        self.line('STATUS')
        text = self.out()
        self.assertion(re.fullmatch(r'#status role=rx forwarded=\d+ dropped=\d+ acks=\d+ relistens=\d+ uart_errors=\d+\n', text), text)
        return fields(text)

    def alive_lines(self, text):
        return [fields(m) for m in re.findall(r'^#alive .*$', text, re.M)]

    @staticmethod
    def assertion(ok, msg):
        if not ok:
            raise AssertionError(msg)


def obs(rnd, n=None, lo=None, hi=None):
    """A version-5 observation frame of a length ws_air_frame_ok accepts (contents are opaque to the bridge)."""
    n = n if n is not None else rnd.randint(lo, hi)
    return bytes([0x51]) + bytes(rnd.getrandbits(8) for _ in range(n - 1))


def reply(rnd, kind=2, n=33):
    return bytes([0x50 | kind]) + bytes(rnd.getrandbits(8) for _ in range(n - 1))


@needs_cc
class RxStateMachine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fw = ROOT/'firmware'
        app = Path(os.environ.get('WS_RX_APP') or fw/'stage0-node/App/app_rx.c')
        lib = host_library(cls, 'rxmachine', '-I', fw/'host/include', '-I', fw/'stage0-node/App',
                           '-I', fw/'stage0-node/Core/Inc', '-I', fw, '-I', fw/'common', '-DHOST_RADIO_GETSTATUS',
                           '-DWS_FW_VERSION="host"', app, *[fw/s for s in SOURCES])
        cls.library = lib._name
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.addClassCleanup(cls.tmp.cleanup)

    def bridge(self, start_s=0, drops_ok=False):
        b = Bridge(self.library, self.tmp.name, start_s)
        self.rnd = random.Random(self.id())

        def checks():
            lib = b.lib
            self.assertEqual(lib.h_primask_leaks(), 0, 'a task left interrupts masked')
            self.assertEqual(lib.h_task_saturations(), 0, 'main-loop tasks never settled')
            self.assertEqual(lib.h_overlong(), 0, 'a console line longer than the 640-byte trace buffer was cut')
            self.assertEqual(lib.h_capture_overflow(), 0)
            self.assertEqual(lib.h_continuous(), 1, 'the bridge must configure continuous receive')
            self.assertEqual(lib.h_last_rx_timeout(), 0, 'Rx(0): continuous receive, no driver timeout')
            if not drops_ok:
                self.assertEqual(lib.h_trace_drops(), 0, 'console lines dropped')
        self.addCleanup(checks)
        return b

    def obs(self, b, n=None):
        return obs(self.rnd, n, b.obs_min, b.obs_max)

    def diag(self, b):
        return bytes([0x54]) + bytes(self.rnd.getrandbits(8) for _ in range(b.diag_len - 1))

    def alive_now(self, b):
        """The next #alive report: wait for its timer, then the main loop."""
        b.out()
        b.advance(ALIVE_MS - b.now() % ALIVE_MS)
        lines = b.alive_lines(b.out())
        self.assertEqual(len(lines), 1)
        return lines[0]

    # ---- boot ----
    def test_boot_listens_in_continuous_receive(self):
        b = self.bridge()
        self.assertEqual(b.out(), BOOT_LINE)
        self.assertEqual((b.radio(), b.lib.h_rx_calls(), b.lib.h_sends()), (RF_RX_RUNNING, 1, 0))
        self.assertEqual(b.lib.h_healthy(), 1)
        b.advance(10_000)
        self.assertEqual(b.out(), '')
        self.assertGreaterEqual(b.lib.h_wd_checks(), 10)
        self.assertEqual((b.lib.h_wd_unhealthy(), b.lib.h_wd_resets()), (0, 0))

    # ---- upstream ----
    def test_valid_frames_are_forwarded_once_as_lowercase_hex(self):
        b = self.bridge()
        b.out()
        frames = [self.obs(b, b.obs_min), self.obs(b, b.obs_max), self.obs(b), self.diag(b), bytes([0x51]) + bytes([0xab]) * (b.obs_min - 1)]
        for i, f in enumerate(frames):
            self.assertEqual(b.rx(f, rssi=-40 - i, snr=9 - i), 1)
            self.assertEqual(b.out(), f'{f.hex()}\n#rx obs rssi={-40 - i} snr={9 - i}\n')
            b.poll()
            self.assertEqual(b.out(), '', 'forwarded twice')
        self.assertEqual((b.radio(), b.lib.h_rx_calls()), (RF_RX_RUNNING, 1), 'continuous receive: no re-arm after RxDone')
        self.assertEqual(b.lib.h_led_flashes(LED_BLUE), len(frames))
        a = self.alive_now(b)
        self.assertEqual((a['forwarded'], a['dropped'], a['diag']), (str(len(frames)), '0', '1'))

    def test_invalid_frames_are_dropped_not_forwarded(self):
        b = self.bridge()
        b.out()
        bad = [bytes([0x41]) + bytes(40),                        # version 4
               bytes([0x61]) + bytes(40),                        # version 6
               self.obs(b, b.obs_min - 1), self.obs(b, b.obs_max + 1),
               bytes([0x54]) + bytes(b.diag_len - 2), bytes([0x54]) + bytes(b.diag_len),
               reply(self.rnd), reply(self.rnd, kind=3),        # an ACK/NACK heard on air is not forwarded
               bytes([0x50]) + bytes(40), bytes([0x55]) + bytes(40), b'', bytes([0x51]), self.obs(b, 255)]
        for f in bad:
            self.assertEqual(b.rx(f, rssi=-70, snr=-3), 1)
            self.assertEqual(b.out(), f'#rx drop len={len(f)} rssi=-70 snr=-3\n')
        self.assertEqual(b.lib.h_led_flashes(LED_RED), len(bad))
        self.assertEqual(b.status(), {'role': 'rx', 'forwarded': '0', 'dropped': str(len(bad)), 'acks': '0', 'relistens': '0',
                                      'uart_errors': '0'})

    def test_a_crc_failed_packet_is_logged_whole_and_never_forwarded(self):
        b = self.bridge()
        b.out()
        f = self.obs(b)                 # bytes that would pass the frame check, but the payload CRC failed
        self.assertEqual(b.crc(f, rssi=-100, snr=-12), 1)
        self.assertEqual(b.out(), f'#rx crc len={len(f)} rssi=-100 snr=-12 data={f.hex()}\n')
        self.assertEqual((b.radio(), b.lib.h_rx_calls(), b.lib.h_standby_calls()), (RF_RX_RUNNING, 1, 0),
                         'the radio stays in continuous receive: nothing re-arms it')
        self.assertEqual(b.rx(f), 1)    # the retry, received whole, is forwarded
        self.assertEqual(b.out(), f'{f.hex()}\n#rx obs rssi=-40 snr=9\n')
        s = b.status()
        self.assertEqual((s['forwarded'], s['dropped']), ('1', '0'), 'a CRC failure is neither forwarded nor dropped')
        a = self.alive_now(b)
        self.assertEqual((a['crc_errors'], a['hdr_errors'], a['fault_overruns']), ('1', '0', '0'))

    def test_a_crc_failure_without_rx_done_reads_the_radio_buffer(self):
        b = self.bridge()
        b.out()
        f = bytes(range(40))
        self.assertEqual(b.rx_error_only(f, rssi=-105, snr=-14), 1)
        self.assertEqual(b.out(), f'#rx crc len=40 rssi=-105 snr=-14 data={f.hex()}\n')
        self.assertEqual((b.radio(), b.lib.h_rx_calls()), (RF_RX_RUNNING, 1))
        self.assertEqual(self.alive_now(b)['crc_errors'], '1')

    def test_a_header_failure_is_logged_with_the_channel_rssi(self):
        b = self.bridge()
        b.out()
        self.assertEqual(b.hdr(rssi=-97), 1)
        self.assertEqual(b.out(), '#rx hdr rssi=-97\n')
        self.assertEqual((b.radio(), b.lib.h_rx_calls(), b.lib.h_standby_calls()), (RF_RX_RUNNING, 1, 0))
        a = self.alive_now(b)
        self.assertEqual((a['crc_errors'], a['hdr_errors'], a['forwarded'], a['dropped']), ('0', '1', '0', '0'))

    def test_a_255_byte_capture_is_one_complete_line(self):
        b = self.bridge()
        b.out()
        f = bytes(self.rnd.getrandbits(8) for _ in range(255))
        b.crc(f, rssi=-128, snr=-128)
        text = b.out()
        self.assertEqual(text, f'#rx crc len=255 rssi=-128 snr=-128 data={f.hex()}\n')
        self.assertLess(len(text), 640)

    def test_failures_before_the_main_loop_runs_are_counted(self):
        b = self.bridge()
        b.out()
        f1, f2 = bytes([1]) * 20, bytes([2]) * 21
        b.crc(f1, run=False)
        b.crc(f2, run=False)
        b.hdr(rssi=-90, run=False)
        b.hdr(rssi=-91, run=False)
        b.rx_error_only(bytes([3]) * 22, run=False)
        self.assertEqual(b.out(), '', 'nothing is printed from interrupt context')
        b.poll()
        self.assertEqual(b.out(), f'#rx crc len=20 rssi=-100 snr=-12 data={f1.hex()}\n#rx hdr rssi=-90\n')
        a = self.alive_now(b)
        self.assertEqual((a['crc_errors'], a['hdr_errors'], a['fault_overruns']), ('3', '2', '3'))

    def test_a_frame_replaced_before_forwarding_is_counted(self):
        b = self.bridge()
        b.out()
        f1, f2 = self.obs(b, b.obs_max), self.obs(b, b.obs_min)
        b.rx(f1, rssi=-41, snr=1, run=False)
        b.rx(f2, rssi=-42, snr=2, run=False)
        b.poll()
        self.assertEqual(b.out(), f'{f2.hex()}\n#rx obs rssi=-42 snr=2\n'
                                  '#rx frame-lost total=1 (a valid frame replaced before it was forwarded)\n')
        a = self.alive_now(b)
        self.assertEqual((a['forwarded'], a['fault_overruns'], a['frames_lost']), ('1', '0', '1'))

    def test_one_main_loop_pass_handles_every_kind_of_event(self):
        b = self.bridge()
        b.out()
        good, damaged = self.obs(b), self.obs(b)
        b.crc(damaged, run=False)
        b.rx(good, run=False)
        b.hdr(rssi=-95, run=False)
        b.poll()
        self.assertEqual(b.out(), f'{good.hex()}\n#rx obs rssi=-40 snr=9\n#rx crc len={len(damaged)} rssi=-100 snr=-12 '
                                  f'data={damaged.hex()}\n#rx hdr rssi=-95\n')
        self.assertEqual(self.alive_now(b)['fault_overruns'], '0')

    # ---- downstream ----
    def test_a_host_ack_or_nack_is_transmitted_once_then_the_radio_listens(self):
        b = self.bridge()
        b.out()
        for n, kind in enumerate((2, 3), 1):
            f = reply(self.rnd, kind)
            rx_calls = b.lib.h_rx_calls()
            b.line(f.hex())
            self.assertEqual(b.out(), '')
            self.assertEqual((b.lib.h_sends(), b.sent(), b.radio()), (n, f, RF_TX_RUNNING))
            self.assertEqual(b.lib.h_healthy(), 1)
            b.advance(30)                                  # TxDone
            self.assertEqual((b.radio(), b.lib.h_rx_calls()), (RF_RX_RUNNING, rx_calls + 1))
            self.assertEqual(b.lib.h_sends(), n, 'transmitted once')
        b.line(reply(self.rnd).hex().upper())              # hex digits of either case
        self.assertEqual(b.lib.h_sends(), 3)
        b.advance(30)
        self.assertEqual(b.status()['acks'], '3')
        self.assertEqual(b.lib.h_led_flashes(LED_GREEN), 3)
        self.assertLessEqual(b.lib.h_max_not_rx_ms(), 25)

    def test_a_frame_arriving_right_after_the_ack_is_received(self):
        b = self.bridge()
        b.line(reply(self.rnd).hex())
        f = self.obs(b)
        self.assertEqual(b.rx(f), 0, 'not received while transmitting')
        b.advance(30)
        b.out()
        self.assertEqual(b.rx(f), 1)
        self.assertIn(f.hex(), b.out())

    def test_a_transmit_timeout_returns_to_listening(self):
        b = self.bridge()
        b.out()
        b.lib.h_tx_mode(TX_STUCK)
        b.line(reply(self.rnd).hex())
        b.advance(2990)
        self.assertEqual((b.radio(), b.out()), (RF_TX_RUNNING, ''))
        self.assertEqual(b.lib.h_healthy(), 1)
        b.advance(20)
        self.assertEqual(b.out(), '#tx timeout\n')
        self.assertEqual(b.radio(), RF_RX_RUNNING)
        self.assertEqual(b.lib.h_led_flashes(LED_RED), 1)
        self.assertLessEqual(b.lib.h_max_not_rx_ms(), 3001)
        b.lib.h_tx_mode(TX_NORMAL)
        b.advance(20_000)
        self.assertEqual((b.lib.h_wd_unhealthy(), b.lib.h_wd_resets()), (0, 0))

    def test_a_refused_send_listens_again(self):
        b = self.bridge()
        b.out()
        b.lib.h_send_fails(1)
        b.line(reply(self.rnd).hex())
        self.assertEqual(b.out(), '#tx busy\n')
        self.assertEqual((b.radio(), b.lib.h_sends(), b.lib.h_send_calls()), (RF_RX_RUNNING, 0, 1))
        self.assertEqual(b.lib.h_healthy(), 1)
        self.assertEqual(b.status()['acks'], '0')

    def test_invalid_host_lines_are_rejected_and_never_transmitted(self):
        b = self.bridge()
        b.out()
        ack = reply(self.rnd)
        cases = [(ack.hex()[:-1], -1),                          # odd length
                 ('zz' + ack.hex()[2:], -1),                    # not hex
                 (ack.hex() + '0', -1),
                 (ack.hex()[:-2], 32), (ack.hex() + '00', 34),  # one byte short / long
                 (ack.hex() + '0000', -1),                      # more than the decode buffer
                 ('41' + ack.hex()[2:], 33),                    # version 4
                 ('51' + ack.hex()[2:], 33), ('54' + ack.hex()[2:], 33), ('50' + ack.hex()[2:], 33),   # not ACK/NACK
                 ('hello', -1), ('status', -1), (' ' + ack.hex(), -1), (ack.hex() + ' ', -1), ('0' * 256, -1),
                 ('TEST-FAULTS', -1), ('STATUS ', -1)]
        for text, n in cases:
            b.line(text)
            self.assertEqual(b.out(), f'#host reject len={n}\n', text)
        self.assertEqual((b.lib.h_sends(), b.lib.h_send_calls(), b.radio()), (0, 0, RF_RX_RUNNING))
        self.assertEqual(b.lib.h_led_flashes(LED_RED), len(cases))

    def test_comment_lines_are_ignored(self):
        b = self.bridge()
        b.out()
        for text in ('#', '# note', '#' + reply(self.rnd).hex(), '#STATUS'):
            b.line(text)
        self.assertEqual((b.out(), b.lib.h_send_calls()), ('', 0))
        b.uart('\n\r\n\n')                                 # empty lines: nothing
        b.poll()
        self.assertEqual(b.out(), '')

    def test_an_over_long_line_is_discarded_whole(self):
        b = self.bridge()
        b.out()
        ack = reply(self.rnd)
        b.line('0' * (b.line_max + 1 - 66) + ack.hex())     # 257 characters ending in a valid ACK
        self.assertEqual((b.out(), b.lib.h_send_calls()), ('', 0))
        b.line('x' * 5000)
        self.assertEqual(b.out(), '')
        b.line('0' * (b.line_max - 66) + ack.hex())         # exactly WS_LINE_MAX: accepted, then rejected
        self.assertEqual(b.out(), '#host reject len=-1\n')
        b.line(ack.hex())                                    # the assembler starts clean afterwards
        self.assertEqual((b.lib.h_sends(), b.sent()), (1, ack))

    def test_crlf_line_endings_are_accepted(self):
        b = self.bridge()
        ack = reply(self.rnd)
        b.uart(ack.hex() + '\r\n')
        b.poll()
        self.assertEqual((b.lib.h_sends(), b.sent()), (1, ack))

    def test_a_second_line_while_one_is_pending_is_dropped(self):
        b = self.bridge()
        b.out()
        a1, a2 = reply(self.rnd), reply(self.rnd, kind=3)
        b.uart(f'{a1.hex()}\n{a2.hex()}\n', run_each=False)   # both arrive before the main loop runs
        b.poll()
        self.assertEqual((b.lib.h_sends(), b.sent(), b.out()), (1, a1, ''))
        b.advance(30)
        b.uart(f'{a1.hex()}\nST', run_each=False)            # a partial second line: its head is dropped too
        b.uart('ATUS\n')
        b.poll()
        self.assertNotIn('#status', b.out())
        self.assertEqual(b.lib.h_sends(), 2)

    def test_uart_characters_are_lost_while_the_receive_is_not_armed(self):
        b = self.bridge()
        b.out()
        b.lib.h_uart_deaf()
        self.assertEqual(b.uart(reply(self.rnd).hex() + '\n'), 0)
        self.assertEqual(b.lib.h_send_calls(), 0)

    def test_status(self):
        b = self.bridge()
        b.rx(self.obs(b))
        b.rx(b'\x00')
        b.line(reply(self.rnd).hex())
        b.lib.h_uart_error()
        b.lib.h_uart_error()
        b.uart('\n')                                        # ends the line the errors damaged (discarded)
        b.advance(30)
        self.assertEqual(b.status(), {'role': 'rx', 'forwarded': '1', 'dropped': '1', 'acks': '1', 'relistens': '0',
                                      'uart_errors': '2'})

    def test_test_fault_goes_to_the_fault_handler(self):
        b = self.bridge()
        b.out()
        b.line('TEST-FAULT')
        self.assertEqual((b.lib.h_fault_tests(), b.lib.h_send_calls()), (1, 0))
        # TEST-HANG is an endless loop by design (the watchdog test); not run here.

    # ---- the minute report ----
    def test_alive_is_printed_by_the_main_loop_not_the_timer_interrupt(self):
        b = self.bridge()
        b.out()
        b.advance(ALIVE_MS, run=False)                     # the timer fires; the main loop is held back
        self.assertEqual(b.out(), '')
        self.assertNotEqual(b.lib.h_task_pending(), 0)
        b.poll()
        text = b.out()
        self.assertRegex(text, r'^#alive [^\n]*\n$')
        a = b.alive_lines(text)[0]
        self.assertEqual(list(a), ALIVE_KEYS)
        self.assertEqual(a, {'uptime': '60', 'forwarded': '0', 'dropped': '0', 'acks': '0', 'diag': '0', 'listening': '1',
                             'relistens': '0', 'uart_errors': '0', 'stack_peak': '0', 'crc_errors': '0', 'hdr_errors': '0',
                             'fault_overruns': '0', 'task_peak_us': '0', 'task_peak': 'none', 'isr_peak_us': '0',
                             'isr_peak': 'none', 'trace_drops': '0', 'frames_lost': '0'})

    def test_alive_every_minute_with_uptime_in_seconds(self):
        b = self.bridge(start_s=1234)                       # the RTC keeps counting through a reset
        b.out()
        b.advance(ALIVE_MS - 1)
        self.assertEqual(b.out(), '')
        b.advance(1)
        self.assertEqual(b.alive_lines(b.out())[0]['uptime'], '60')
        b.advance(3600_000 - ALIVE_MS)
        ups = [int(a['uptime']) for a in b.alive_lines(b.out())]
        self.assertEqual(ups, list(range(120, 3601, 60)))

    def test_alive_across_the_millisecond_wrap(self):
        b = self.bridge(start_s=4294967 - 150)              # ms_now() wraps 150 s after boot (49.7 days)
        b.out()
        b.hdr()
        b.advance(RELISTEN_S * 1000)
        text = b.out()
        self.assertEqual([int(a['uptime']) for a in b.alive_lines(text)], list(range(60, RELISTEN_S + 1, 60)))
        self.assertEqual(re.findall(r'#relisten after (\d+) s', text), [str(RELISTEN_S)])

    def test_relisten_after_sixteen_minutes_without_a_radio_event(self):
        # Longer than the node's longest legitimate silence (15 min, PROBING in CONSERVE).
        b = self.bridge()
        b.out()
        b.advance(RELISTEN_S * 1000 - ALIVE_MS)
        self.assertNotIn('#relisten', b.out())
        self.assertEqual(b.lib.h_standby_calls(), 0)
        b.advance(ALIVE_MS)
        text = b.out()
        self.assertIn(f'#relisten after {RELISTEN_S} s without a radio event\n', text)
        self.assertLess(text.index('#alive'), text.index('#relisten'))
        self.assertEqual((b.lib.h_standby_calls(), b.lib.h_rx_calls(), b.radio()), (1, 2, RF_RX_RUNNING))
        self.assertEqual(b.lib.h_wd_resets(), 0)       # one relisten is a self-heal, not yet a reset
        b.hdr()                                        # the radio hears something: the quiet count restarts
        b.advance(RELISTEN_S * 1000)
        self.assertEqual(re.findall(r'#relisten after (\d+) s', b.out()), [str(RELISTEN_S)])
        a = self.alive_now(b)
        self.assertEqual(a['relistens'], '2')
        self.assertEqual(b.status()['relistens'], '2')
        self.assertEqual(b.lib.h_wd_resets(), 0)

    def test_every_kind_of_reception_counts_as_radio_life(self):
        for name, event in (('hdr', lambda b: b.hdr()), ('crc', lambda b: b.crc(bytes(30))),
                            ('rxerr', lambda b: b.rx_error_only(bytes(30))), ('frame', lambda b: b.rx(bytes(30))),
                            ('good', lambda b: b.rx(self.obs(b)))):
            with self.subTest(name):
                b = self.bridge()
                b.advance(200_000)
                event(b)
                b.advance(1_140_000 - 200_000)              # alives up to 1140 s: at most 940 s of silence
                self.assertNotIn('#relisten', b.out())
                b.advance(ALIVE_MS)                         # 1200 s: 1000 s
                self.assertIn('#relisten after 1000 s', b.out())

    def test_a_transmission_is_not_a_radio_event(self):
        b = self.bridge()
        b.out()
        for _ in range(RELISTEN_S // 60 - 1):
            b.advance(ALIVE_MS)
            b.line(reply(self.rnd).hex())
        b.advance(ALIVE_MS)
        self.assertIn(f'#relisten after {RELISTEN_S} s', b.out())

    def test_no_relisten_while_transmitting(self):
        b = self.bridge()
        b.out()
        b.advance(RELISTEN_S * 1000 - 10)
        b.line(reply(self.rnd).hex())                       # on air when the 1020 s report runs
        b.advance(40)
        self.assertNotIn('#relisten', b.out())
        self.assertEqual(b.radio(), RF_RX_RUNNING)
        b.advance(20_000)
        b.hdr()                                             # the next main-loop pass: the radio is alive
        self.assertEqual(b.out(), '#rx hdr rssi=-97\n')
        b.advance(ALIVE_MS)
        self.assertNotIn('#relisten', b.out())
        b.advance(15 * ALIVE_MS)                            # to 2000 s: 960 s since the header error
        self.assertNotIn('#relisten', b.out())
        b.advance(ALIVE_MS)
        self.assertIn('#relisten after 999 s', b.out())

    # ---- watchdog health ----
    def test_transmitting_more_than_5_s_is_unhealthy(self):
        b = self.bridge()
        b.out()
        b.lib.h_tx_mode(TX_HANG)                            # neither TxDone nor the driver's timeout
        b.advance(700)                                      # mid-second: the 5 s are measured in ms, not whole seconds
        b.line(reply(self.rnd).hex())
        b.advance(4990)
        self.assertEqual((b.lib.h_healthy(), b.lib.h_wd_unhealthy()), (1, 0))
        b.advance(10)
        self.assertEqual(b.lib.h_healthy(), 0)
        b.advance(9000)
        self.assertGreaterEqual(b.lib.h_wd_unhealthy(), 8)
        self.assertEqual(b.lib.h_wd_resets(), 1)

    def test_console_not_armed_is_rearmed_once_then_unhealthy(self):
        b = self.bridge()
        b.out()
        b.lib.h_uart_deaf()
        b.advance(1000)                                     # the watchdog's check
        self.assertEqual(b.out(), '#watchdog console not receiving; re-arming\n')
        self.assertEqual((b.lib.h_uart_armed(), b.lib.h_uart_rearms(), b.lib.h_wd_unhealthy()), (1, 1, 0))
        ack = reply(self.rnd)
        b.line(ack.hex())
        self.assertEqual(b.sent(), ack)
        b.advance(5000)
        b.lib.h_uart_deaf()                                 # again later: a fresh re-arm
        b.lib.h_uart_rearm_fails(1)
        b.advance(1000)
        self.assertEqual(b.out(), '#watchdog console not receiving; re-arming\n')
        self.assertEqual(b.lib.h_wd_unhealthy(), 0)
        b.advance(1000)
        self.assertEqual((b.out(), b.lib.h_wd_unhealthy(), b.lib.h_healthy()), ('', 1, 0))
        b.advance(8000)
        self.assertEqual(b.lib.h_wd_resets(), 1)

    def test_radio_not_listening_is_relistened_once_then_unhealthy(self):
        b = self.bridge()
        b.out()
        b.lib.h_radio_force_idle()
        b.advance(1000)
        self.assertEqual(b.out(), '#watchdog radio not listening; re-arming\n')
        self.assertEqual((b.radio(), b.lib.h_rx_calls(), b.lib.h_wd_unhealthy()), (RF_RX_RUNNING, 2, 0))
        b.advance(5000)
        b.lib.h_radio_force_idle()                          # again later: a fresh attempt
        b.lib.h_rx_ignored(1)
        b.advance(1000)
        self.assertEqual(b.out(), '#watchdog radio not listening; re-arming\n')
        self.assertEqual(b.lib.h_wd_unhealthy(), 0)
        b.advance(1000)
        self.assertEqual((b.out(), b.lib.h_wd_unhealthy(), b.lib.h_healthy()), ('', 1, 0))
        b.advance(8000)
        self.assertEqual(b.lib.h_wd_resets(), 1)
        b.advance(ALIVE_MS)                                 # (the board would have reset; the report says why)
        self.assertEqual(b.alive_lines(b.out())[0]['listening'], '0')

    # ---- 2026-10-15 review findings (each failed before its fix) ----
    def test_review_m1_a_radio_that_hears_nothing_is_eventually_reset(self):
        b = self.bridge()
        b.advance(2 * RELISTEN_S * 1000 - 1000)             # the first relisten brought nothing back
        self.assertEqual(b.lib.h_wd_resets(), 0)
        b.advance(1000 + 10_000)                            # the second: the health check fails, the watchdog resets
        text = b.log + b.out()
        self.assertEqual(text.count('#relisten after'), 2)
        self.assertIn('#watchdog radio silent after 2 relistens; reset', text)
        self.assertGreaterEqual(b.lib.h_wd_resets(), 1)

    def test_review_m1_a_second_ack_line_does_not_cut_the_first_short(self):
        b = self.bridge()
        b.out()
        b.line(reply(self.rnd).hex())
        b.advance(10)                                       # the first is still on air
        b.line(reply(self.rnd, kind=3).hex())
        b.advance(5000)
        self.assertNotIn('#tx timeout', b.out())
        self.assertEqual(b.lib.h_sends_while_tx(), 0, 'Radio.Send while the radio was still transmitting')

    def test_review_m3_a_transmit_timeout_stops_the_transmitter_first(self):
        b = self.bridge()
        b.lib.h_tx_mode(TX_STUCK)
        b.line(reply(self.rnd).hex())
        b.advance(3100)
        self.assertIn('#tx timeout', b.out())
        self.assertEqual(b.lib.h_rx_after_timeout_no_standby(), 0)

    def test_review_m4_listening_after_an_ack_restores_the_payload_length(self):
        b = self.bridge()
        self.assertEqual(b.lib.h_pkt_len(), 255)
        b.line(reply(self.rnd).hex())
        b.advance(30)
        self.assertEqual(b.radio(), RF_RX_RUNNING)
        self.assertEqual(b.lib.h_pkt_len(), 255, 'harness models the driver parameter only; chip effect not modelled')

    def test_review_m6_no_relisten_while_a_probing_node_sends_every_15_minutes(self):
        b = self.bridge()
        b.out()
        for _ in range(4):
            b.rx(self.obs(b))
            b.advance(15 * ALIVE_MS)
        self.assertNotIn('#relisten', b.out())

    def test_review_m7_boot_line_starts_on_a_fresh_line(self):
        b = self.bridge()
        self.assertTrue(b.out().startswith('\n#boot '))

    def test_review_m8_the_tail_of_a_dropped_line_is_not_a_line(self):
        b = self.bridge()
        b.out()
        b.uart(f'{reply(self.rnd).hex()}\nST', run_each=False)
        b.uart('ATUS\n')
        b.poll()
        self.assertEqual(b.out(), '')                       # today: '#host reject len=-1' for 'ATUS'

    def test_review_m8_a_nul_inside_a_host_line_is_rejected(self):
        b = self.bridge()
        b.out()
        b.uart(reply(self.rnd).hex().encode() + b'\0junk\n')
        b.poll()
        self.assertEqual(b.lib.h_send_calls(), 0)

    def test_review_m10_forwarded_counts_only_frames_that_reached_the_host(self):
        b = self.bridge(drops_ok=True)
        b.out()
        for _ in range(20):                                 # no time passes: the 2 KB FIFO cannot drain
            b.rx(self.obs(b, b.obs_max))
        printed = sum(1 for ln in b.out().splitlines() if not ln.startswith('#'))
        self.assertGreater(b.lib.h_trace_drops(), 0)
        b.advance(ALIVE_MS)
        self.assertEqual(b.alive_lines(b.out())[0]['forwarded'], str(printed))

    def test_review_m11_a_lost_frame_is_told_apart_from_a_skipped_capture(self):
        def run(lose_frame):
            b = self.bridge()
            f1, f2 = self.obs(b), self.obs(b)
            b.rx(f1, run=not lose_frame)
            if lose_frame:
                b.rx(f2)                                    # replaces f1 before it was forwarded
                b.crc(bytes(30))
                b.crc(bytes(30))
            else:
                b.crc(bytes(30), run=False)
                b.crc(bytes(30))                            # this capture is skipped
            b.out()
            b.advance(ALIVE_MS)
            return b.alive_lines(b.out())[0]
        self.assertNotEqual(run(True), run(False))

    # m12 (TEST-HANG / TEST-FAULT live in the production image) is a build-configuration question:
    # there is no production/bench build split to test here; test_test_fault_goes_to_the_fault_handler
    # shows TEST-FAULT is reachable in this build.

    # ---- everything at once ----
    def test_six_hours_of_mixed_traffic_keep_every_invariant(self):
        b = self.bridge()
        Mixed(self, b, random.Random(2026)).run(6 * 3600_000)


def hex_decode(text, maxn):
    """ws_hex_decode (firmware/common/ws_console.c)."""
    out = bytearray()
    i = 0
    while i + 1 < len(text):
        hi, lo = int(text[i], 16) if text[i] in '0123456789abcdefABCDEF' else -1, \
            int(text[i + 1], 16) if text[i + 1] in '0123456789abcdefABCDEF' else -1
        if hi < 0 or lo < 0 or len(out) >= maxn:
            return -1, b''
        out.append(hi << 4 | lo)
        i += 2
    return (-1, b'') if i < len(text) else (len(out), bytes(out))


class Mixed:
    """A randomized run against a reference model of the bridge: frames, CRC and header failures,
    bursts before the main loop runs, host ACK/NACK lines (some stuck or refused by the radio), bad
    host lines and UART noise, quiet spells. Every output line must be predicted by the model."""
    def __init__(self, test, bridge, rnd):
        self.t, self.b, self.rnd = test, bridge, rnd
        self.n = Counter()                  # forwarded, dropped, acks, diag, crc, hdr, overruns, relistens, uart_errors
        self.pend = {}                      # the firmware's one-deep capture slots
        self.asm, self.overflow, self.ready = bytearray(), False, None
        self.sends = 0
        self.tx_deadline = None             # a stuck transmission's TxTimeout
        self.last_event = 0
        self.relistened_since = False
        self.alive_seen = 0
        self.failure_lines = 0               # #rx crc / #rx hdr lines this minute (20 at most)

    # ---- the model ----
    def radio_event(self, kind, frame=b'', rssi=0, snr=0):
        self.last_event, self.relistened_since = self.b.now(), False
        if kind in ('crc', 'rxerr', 'hdr'):
            self.n[kind if kind != 'rxerr' else 'crc'] += 1
        slot = {'rx': 'rx', 'crc': 'crc', 'rxerr': 'crc', 'hdr': 'hdr'}[kind]
        if slot in self.pend:
            if slot != 'rx':
                self.n['overruns'] += 1                     # a capture skipped
                return
            self.n['frames_lost'] += 1                      # a valid frame replaced before forwarding
        self.pend[slot] = (frame, rssi, snr)

    def expected_process(self):
        lines = []
        if 'rx' in self.pend:
            f, rssi, snr = self.pend['rx']
            ok = len(f) >= 1 and f[0] >> 4 == self.b.version and (
                (f[0] & 15 == 1 and self.b.obs_min <= len(f) <= self.b.obs_max) or (f[0] & 15 == 4 and len(f) == self.b.diag_len))
            if ok:
                self.n['forwarded'] += 1
                self.n['diag'] += f[0] & 15 == 4
                lines += [f.hex(), f'#rx obs rssi={rssi} snr={snr}']
            else:
                self.n['dropped'] += 1
                lines.append(f'#rx drop len={len(f)} rssi={rssi} snr={snr}')
        for slot in ('crc', 'hdr'):                         # 20 failure lines a minute; then counted only
            if slot in self.pend:
                f, rssi, snr = self.pend[slot]
                self.failure_lines += 1
                if self.failure_lines > 20:
                    self.n['overruns'] += 1
                elif slot == 'crc':
                    lines.append(f'#rx crc len={len(f)} rssi={rssi} snr={snr} data={f.hex()}')
                else:
                    lines.append(f'#rx hdr rssi={rssi}')
        if self.n['frames_lost'] != self.n['frames_lost_told']:
            self.n['frames_lost_told'] = self.n['frames_lost']
            lines.append(f'#rx frame-lost total={self.n["frames_lost"]} (a valid frame replaced before it was forwarded)')
        self.pend = {}
        return lines

    def discard(self):
        self.asm, self.overflow = bytearray(), True

    def feed(self, data):
        for c in data:
            if self.ready is not None:                      # console.c: a dropped byte discards its whole line,
                self.discard()                              # which ends at its (dropped) newline
                self.overflow = c != 10
                continue
            if c == 13:
                continue
            if c == 10:
                if not self.overflow and self.asm:
                    self.ready = bytes(self.asm)
                self.asm, self.overflow = bytearray(), False
            elif self.overflow:
                continue
            elif len(self.asm) >= self.b.line_max or c < 0x20 or c > 0x7e:
                self.discard()                              # over-long, or not printable ASCII
            else:
                self.asm.append(c)

    def expected_console(self):
        if self.ready is None:
            return []
        line, self.ready = self.ready.decode('ascii'), None
        if line.startswith('#'):
            return []
        assert line not in ('TEST-FAULT', 'TEST-HANG')
        if line == 'STATUS':
            n = self.n
            return [f'#status role=rx forwarded={n["forwarded"]} dropped={n["dropped"]} acks={n["acks"]} '
                    f'relistens={n["relistens"]} uart_errors={n["uart_errors"]}']
        size, frame = hex_decode(line, self.b.ack_len + 1)
        if size != self.b.ack_len or frame[0] not in (0x52, 0x53):
            return [f'#host reject len={size}']
        if self.tx_deadline is not None:
            return ['#tx busy']                             # one ACK on air at a time
        if self.send_fails:
            self.send_fails = 0
            self.tx_deadline = None                         # listen() again
            return ['#tx busy']
        self.sends += 1
        self.n['acks'] += 1
        self.tx_deadline = self.b.lib.h_now_ticks() + 3072 if self.tx_mode == TX_STUCK else None   # ST's TxTimeoutTimer
        return []

    # ---- checks ----
    def check_lines(self, got, expected, where):
        self.t.assertEqual(got, expected, f'{where} at {self.b.now()} ms\n{self.b.log[-3000:]}')

    def after_advance(self, text, crossed_deadline):
        lines = text.splitlines()
        other = []
        for line in lines:
            if line.startswith('#alive '):
                a = fields(line)
                self.alive_seen += 1
                n = self.n
                want = {'uptime': str(60 * self.alive_seen), 'forwarded': str(n['forwarded']), 'dropped': str(n['dropped']),
                        'acks': str(n['acks']), 'diag': str(n['diag']), 'listening': '1', 'relistens': str(n['relistens']),
                        'uart_errors': str(n['uart_errors']), 'crc_errors': str(n['crc']), 'hdr_errors': str(n['hdr']),
                        'fault_overruns': str(n['overruns']), 'trace_drops': '0', 'frames_lost': str(n['frames_lost'])}
                self.t.assertEqual({k: a[k] for k in want}, want, line)
                self.failure_lines = 0
            elif m := re.fullmatch(r'#relisten after (\d+) s without a radio event', line):
                self.t.assertGreaterEqual(int(m[1]), 960)      # more than 16 min, in whole seconds
                self.t.assertGreaterEqual(self.b.now() - self.last_event, 960_000)
                self.n['relistens'] += 1
                self.relistened_since = True
            else:
                other.append(line)
        self.check_lines(other, ['#tx timeout'] if crossed_deadline else [], 'advance')
        if self.b.now() - self.last_event > 960_000 + 62_000 and self.b.radio() == RF_RX_RUNNING and self.tx_deadline is None:
            self.t.assertTrue(self.relistened_since, 'silent for more than 6 minutes without a relisten')

    def run(self, duration):
        b, rnd, t = self.b, self.rnd, self.t
        self.tx_mode, self.send_fails = TX_NORMAL, 0
        self.check_lines(b.out().splitlines(), BOOT_LINE.splitlines(), 'boot')
        while b.now() < duration:
            quiet = rnd.random() < 0.002
            dt = rnd.randint(50, 3000) if not quiet else rnd.randint(1_000_000, 1_100_000)   # beyond the 16 min relisten
            b.advance(dt)
            crossed = self.tx_deadline is not None and b.lib.h_now_ticks() >= self.tx_deadline
            if crossed:
                self.tx_deadline = None
            self.after_advance(b.out(), crossed)
            t.assertIn(b.radio(), (RF_RX_RUNNING,) if self.tx_deadline is None else (RF_TX_RUNNING,))
            t.assertEqual((b.lib.h_wd_unhealthy(), b.lib.h_wd_resets()), (0, 0))
            if quiet and b.radio() == RF_RX_RUNNING:        # the radio hears something after a quiet spell (a
                self.inject()                               # second quiet spell in a row would rightly reset it)
                b.poll()
                self.check_lines(b.out().splitlines(), self.expected_process(), 'radio')
            self.step()
        t.assertEqual(self.alive_seen, b.now() // ALIVE_MS)                 # the last step may run past duration
        t.assertLessEqual(b.lib.h_max_not_rx_ms(), 3001, 'the radio was not back in receive soon after a transmission')
        t.assertEqual(b.lib.h_sends(), self.sends)
        for kind in ('forwarded', 'dropped', 'crc', 'hdr', 'overruns', 'acks', 'relistens'):
            t.assertGreater(self.n[kind], 3, kind)

    def radio_injection(self):
        b, rnd = self.b, self.rnd
        r = rnd.random()
        rssi, snr = rnd.randint(-128, -20), rnd.randint(-20, 12)
        if r < 0.45:
            f = obs(rnd, lo=b.obs_min, hi=b.obs_max) if rnd.random() < 0.8 else bytes([0x54]) + rnd.randbytes(b.diag_len - 1)
            return 'rx', b.rx, f, rssi, snr
        if r < 0.6:
            f = rnd.choice([rnd.randbytes(rnd.randint(0, 255)), obs(rnd, n=rnd.choice([b.obs_min - 1, b.obs_max + 1])),
                            reply(rnd)])
            return 'rx', b.rx, f, rssi, snr
        if r < 0.8:
            f = obs(rnd, lo=b.obs_min, hi=b.obs_max) if rnd.random() < 0.5 else rnd.randbytes(rnd.randint(1, 255))
            return 'crc', b.crc, f, rssi, snr
        if r < 0.85:
            return 'rxerr', b.rx_error_only, rnd.randbytes(rnd.randint(1, 255)), rssi, snr
        return 'hdr', None, b'', rssi, 0

    def inject(self):
        kind, fn, f, rssi, snr = self.radio_injection()
        if kind == 'hdr':
            self.t.assertEqual(self.b.hdr(rssi, run=False), 1)
            self.radio_event('hdr', rssi=rssi)
        else:
            self.t.assertEqual(fn(f, rssi, snr, run=False), 1)
            self.radio_event(kind, f, rssi, snr)

    def step(self):
        b, rnd = self.b, self.rnd
        r = rnd.random()
        listening = b.radio() == RF_RX_RUNNING
        if listening and r < 0.58:                           # radio interrupts; sometimes several before the main loop runs
            for _ in range(1 if r < 0.5 else rnd.randint(2, 4)):
                self.inject()
            b.poll()
            self.check_lines(b.out().splitlines(), self.expected_process(), 'radio')
            return
        if r < 0.72:                                         # the gateway's ACK or NACK
            self.tx_mode = TX_STUCK if rnd.random() < 0.05 else TX_NORMAL
            self.send_fails = int(rnd.random() < 0.05)
            b.lib.h_tx_mode(self.tx_mode)
            b.lib.h_send_fails(self.send_fails)
            sends = self.sends
            f = reply(rnd, kind=rnd.choice([2, 3]))
            self.feed_and_check((f.hex() + rnd.choice(['\n', '\r\n'])).encode(), run_each=True)
            if self.sends > sends:
                self.t.assertEqual(b.sent(), f)
            self.tx_mode = TX_NORMAL
            b.lib.h_tx_mode(TX_NORMAL)
            self.send_fails = 0                             # unused if the line was rejected
            b.lib.h_send_fails(0)
            return
        if r < 0.8:                                          # a bad host line, a comment, STATUS
            f = reply(rnd, kind=rnd.choice([1, 2, 3, 4]), n=rnd.choice([32, 33, 34]))
            text = rnd.choice([f.hex(), f.hex()[1:], '#' + f.hex(), 'STATUS', 'zz' * 33, f.hex().upper()])
            data = (text + '\n').encode()
        elif r < 0.9:                                        # UART noise
            data = rnd.randbytes(rnd.randint(1, 400))
            if rnd.random() < 0.3:
                data = data.replace(b'\n', b'')
        elif r < 0.95:
            b.lib.h_uart_error()
            self.n['uart_errors'] += 1
            self.discard()                                  # the damaged character's line is discarded
            return
        else:
            return
        self.feed_and_check(data, run_each=rnd.random() < 0.5)

    def feed_and_check(self, data, run_each):
        b = self.b
        if run_each:
            exp = []
            for c in data:
                self.feed(bytes([c]))
                b.uart(bytes([c]), run_each=True)
                exp += self.expected_console()
        else:
            self.feed(data)
            b.uart(data, run_each=False)
            b.poll()
            exp = self.expected_console()
        self.check_lines(b.out().splitlines(), exp, 'uart')
        self.t.assertEqual(b.lib.h_sends(), self.sends, 'transmitted something other than a valid host ACK/NACK')


if __name__ == '__main__':
    unittest.main()
