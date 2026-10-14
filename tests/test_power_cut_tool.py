"""tools/power_cut_test.py: the per-boot invariant checks and the run summary, with the board,
the serial console and the USB hub replaced by scripted fakes (no hardware is touched)."""
import io
import json
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock
try:                                        # first: sets WS0_UNSAFE_FAST_FSYNC before gateway is imported
    from toolchain import load_tool
except ImportError:
    from tests.toolchain import load_tool

tool = load_tool('power_cut_test')


def status(epoch, ctr, reset='power', kat='pass', **more):
    return {'epoch': str(epoch), 'ctr': str(ctr), 'reset': reset, 'kat': kat, **more}


class PowerCutToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / 'observations.sqlite3'
        db = sqlite3.connect(self.db)
        db.execute('CREATE TABLE observations (session TEXT)')
        db.execute('CREATE TABLE rejections (received_at REAL)')
        with db:
            db.executemany('INSERT INTO observations VALUES (?)', [('4294967295',), ('4294967295',), ('7',)])
            db.executemany('INSERT INTO rejections VALUES (?)', [(0,), (time.time() + 3600,)])
        db.close()
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, *argv, ports=(), statuses=(), storms=()):
        ports, statuses, storms = list(ports), list(statuses), list(storms)
        def find_port(serial_number, timeout):
            self.calls.append(('find', timeout))
            return ports.pop(0)
        def read_status(device, timeout=15):
            self.calls.append(('status', device))
            return statuses.pop(0)
        def storm_then_cut(device, cut, run_s):
            self.calls.append(('storm', device))
            cut()
            return storms.pop(0)
        out = io.StringIO()
        with mock.patch.object(sys, 'argv', ['power_cut_test.py', *argv]), \
                mock.patch.object(tool, 'find_port', find_port), \
                mock.patch.object(tool, 'read_status', read_status), \
                mock.patch.object(tool, 'storm_then_cut', storm_then_cut), \
                mock.patch.object(tool, 'power', lambda hub, port, state: self.calls.append(('power', hub, port, state))), \
                mock.patch.object(tool, 'nrst', lambda serial: self.calls.append(('nrst', serial))), \
                redirect_stdout(out), redirect_stderr(io.StringIO()) as err:
            try:
                tool.main()
                code = None
            except SystemExit as exc:
                code = exc.code
        self.assertEqual((ports, statuses, storms), ([], [], []))     # the script was used up
        return code, out.getvalue(), err.getvalue()

    def test_power_run_checks_every_invariant(self):
        output = self.root / 'evidence'
        boot = ['#boot role=tx', '#storm-scrub dropped=3', '#storm-scrub dropped=4']
        code, out, _ = self.run_tool(
            '--hub', '1-1', '--port', '3', '--serial-number', 'abc', '--cycles', '4', '--off', '0',
            '--gateway-db', str(self.db), '--output', str(output),
            ports=['/dev/a', None, '/dev/b', '/dev/c', '/dev/d'],
            statuses=[(boot, status(5, 10, reset='software', burned=2, ecc=1)),
                      (['#boot'], None),
                      (['#boot'], status(5, 19, reset='pin', kat='fail', burned=1, ecc=0)),
                      (['#boot'], status(6, 30, ecc=2))],
            storms=[['#storm ctr=12', '#storm ctr=20', 'noise'], ['#storm'], ['#storm ctr=25']])
        self.assertEqual(code, 1)
        summary = json.loads((output / 'summary.json').read_text())
        self.assertEqual(summary['totals'], {'cycles': 3, 'boots_ok': 3, 'burned_max': 2, 'ecc_boot_events': 2,
                                             'scrubbed': 7})
        self.assertEqual(summary['failures'], [
            {'cycle': 1, 'error': 'board did not enumerate'},
            {'cycle': 2, 'error': 'no status after boot'},
            {'cycle': 3, 'error': "reset cause 'pin', expected 'power'"},
            {'cycle': 3, 'error': 'self-test failed'},
            {'cycle': 3, 'error': 'epoch did not increase (5 -> 5)'},
            {'cycle': 3, 'error': 'counter went back (19 -> 19)'},
            {'error': '2 storm records reached the gateway'}])
        self.assertEqual((summary['storm_rows_at_gateway'], summary['gateway_rejections'], summary['pass'],
                          summary['method'], summary['hub'], summary['port'], summary['seed']),
                         (2, 1, False, 'power', '1-1', 3, 2026))
        cycles = [json.loads(line) for line in (output / 'cycles.jsonl').read_text().splitlines()]
        self.assertEqual([c['cycle'] for c in cycles], [0, 2, 3, 4])
        self.assertEqual([c.get('max_ctr_used') for c in cycles], [19, 19, 24, None])
        self.assertEqual(cycles[0]['boot'], boot)
        self.assertEqual(cycles[0]['storm'], ['#storm ctr=12', '#storm ctr=20', 'noise'])
        self.assertIsNone(cycles[1]['status'])
        self.assertTrue(0.3 <= cycles[0]['run_s'] <= 4.0)
        self.assertEqual([c for c in self.calls if c[0] == 'power'],
                         [('power', '1-1', 3, 'off'), ('power', '1-1', 3, 'on'),     # cycle 0
                          ('power', '1-1', 3, 'on'),                                 # cycle 1: re-enable
                          ('power', '1-1', 3, 'off'), ('power', '1-1', 3, 'on'),     # cycle 2
                          ('power', '1-1', 3, 'off'), ('power', '1-1', 3, 'on')])    # cycle 3
        progress = [line for line in out.splitlines() if line.startswith('cycle ')]
        self.assertEqual(len(progress), 3)
        self.assertTrue(progress[0].startswith('cycle 1/4 cut after '))
        self.assertTrue(progress[0].endswith('s; epoch=5 failures=0'))
        self.assertTrue(progress[1].endswith('s; epoch=None failures=2'))

    def test_reset_run_passes_and_never_switches_the_hub(self):
        self.db.unlink()
        db = sqlite3.connect(self.db)
        db.execute('CREATE TABLE observations (session TEXT)')
        db.execute('CREATE TABLE rejections (received_at REAL)')
        db.close()
        output = self.root / 'evidence'
        code, _, _ = self.run_tool(
            '--method', 'reset', '--serial-number', 'abc', '--cycles', '2', '--gateway-db', str(self.db),
            '--output', str(output), '--seed', '1', '--min-run', '0', '--max-run', '0',
            ports=['/dev/a', None, '/dev/c'],
            statuses=[(['#boot'], status(1, 1, reset='power')), (['#boot'], status(3, 2, reset='pin'))],
            storms=[['#storm ctr=1']])
        self.assertEqual(code, 1)          # one enumeration failure
        summary = json.loads((output / 'summary.json').read_text())
        self.assertEqual(summary['failures'], [{'cycle': 1, 'error': 'board did not enumerate'}])
        self.assertEqual(summary['totals']['cycles'], 1)
        self.assertEqual([c for c in self.calls if c[0] in ('power', 'nrst')], [('nrst', 'abc')])
        cycles = [json.loads(line) for line in (output / 'cycles.jsonl').read_text().splitlines()]
        self.assertEqual((cycles[0]['run_s'], [c['cycle'] for c in cycles]), (0.0, [0, 2]))

    def test_clean_run_exits_zero(self):
        self.db.unlink()
        db = sqlite3.connect(self.db)
        db.execute('CREATE TABLE observations (session TEXT)')
        db.execute('CREATE TABLE rejections (received_at REAL)')
        db.close()
        code, _, _ = self.run_tool(
            '--method', 'reset', '--serial-number', 'abc', '--cycles', '1', '--gateway-db', str(self.db),
            '--output', str(self.root / 'evidence'),
            ports=['/dev/a', '/dev/a'], statuses=[(['#boot'], status(1, 1)), (['#boot'], status(2, 5, reset='pin'))],
            storms=[['#storm ctr=4']])
        self.assertEqual(code, 0)

    def test_hub_check(self):
        for gone_port, reset, verdict in ((None, 'power', 'PASS: hub cuts power'),
                                          ('/dev/a', 'power', 'FAIL: hub does not cut VBUS'),
                                          (None, 'pin', 'FAIL: hub does not cut VBUS')):
            self.calls = []
            code, out, _ = self.run_tool('--check', '--hub', '1-1', '--port', '3', '--serial-number', 'abc', '--off', '0',
                                         ports=['/dev/a', gone_port, '/dev/a'], statuses=[([], {'reset': reset})])
            self.assertIsNone(code)
            self.assertIn(f'enumeration removed while off: {gone_port is None}; boot reset cause: {reset}; '
                          'status: True', out)
            self.assertIn(verdict, out)
            self.assertEqual([c for c in self.calls if c[0] == 'power'],
                             [('power', '1-1', 3, 'off'), ('power', '1-1', 3, 'on')])
        code, out, _ = self.run_tool('--check', '--hub', '1-1', '--port', '3', '--serial-number', 'abc', '--off', '0',
                                     ports=['/dev/a', None, None])
        self.assertIn('boot reset cause: None; status: False', out)
        self.assertIn('FAIL', out)

    def test_usage_errors(self):
        for argv, message in ((('--serial-number', 'x', '--output', 'o'), '--method power needs --hub and --port'),
                              (('--serial-number', 'x', '--hub', 'h', '--output', 'o'),
                               '--method power needs --hub and --port'),
                              (('--method', 'reset', '--check', '--serial-number', 'x'),
                               '--check tests a hub power cut: use it with --method power'),
                              (('--method', 'reset', '--serial-number', 'x'), '--output is required for a test run')):
            code, _, err = self.run_tool(*argv)
            self.assertEqual(code, 2, argv)
            self.assertIn(message, err, argv)


if __name__ == '__main__':
    unittest.main()
