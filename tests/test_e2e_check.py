"""tools/e2e_check.py against a stub of the gateway's /v1/observations/latest."""
import json
import os
import re
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / 'tools' / 'e2e_check.py'
TOKEN = 'stub-token'
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT))
import e2e_check  # noqa: E402
from ws0 import fields  # noqa: E402

POWER = e2e_check.POWER


# A v6 record as the gateway stores it (field set WS_F_WSMP_BENCH), written out by hand and not
# built from the tool's POWER tuple. No soc_gauge_pct or charger_pins: v6 does not send them.
V6_POWER = dict(batt_mv=3920, batt_current_ma=-12, energy_in_mwh=85, energy_out_mwh=40, charge_in_mah=21,
                charge_out_mah=10, load_mv=3880, load_current_ma=15, charger_input_mv=5010,
                solar_mv=5050, solar_current_ma=120, usb_mv=0, usb_current_ma=0)
V6_REST = dict(temperature_c=21.5, humidity_pct=48.0, th_samples=60, pressure_hpa=1013.2, wind_speed_ms=2.5,
               wind_gust_ms=4.0, wind_dir_deg=270, wind_calm=False, rain_tips=3, uva_raw=1234,
               enclosure_temp_c=24.0, enclosure_rh_pct=40.0)


def observation(age=10, power=True, **over):
    now = time.time()
    record = dict(V6_REST, sampled_at=now - age, quality='valid' if power else 'partial')
    record.update(V6_POWER if power else dict.fromkeys(V6_POWER))
    record.update(over)
    return {'available': True, 'reason': 'fresh', 'age_seconds': age, 'observation': record,
            'effective_sampled_at': now - age}


class Stub:
    """Serves `reply` as (status, body) on a free port; checks the bearer token like the gateway."""
    def __init__(self, status, body, raw=None):
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                stub.paths.append(self.path)
                ok = self.headers.get('Authorization') == 'Bearer ' + TOKEN
                code, payload = (status, body) if ok else (401, {'error': 'unauthorized'})
                data = json.dumps(payload).encode() if raw is None else raw
                self.send_response(code)
                self.send_header('Content-Length', str(len(data) + (50 if raw == b'{"observ' else 0)))
                self.end_headers()
                self.wfile.write(data)

        self.paths = []
        self.server = HTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def run(url, *args, token=TOKEN):
    env = {k: v for k, v in os.environ.items() if k != 'WS0_API_TOKEN'}
    if token is not None:
        env['WS0_API_TOKEN'] = token
    done = subprocess.run([sys.executable, str(TOOL), '--url', url, *args], env=env,
                          capture_output=True, text=True, timeout=30)
    return done.returncode, done.stdout + done.stderr


class E2ECheckTests(unittest.TestCase):
    def serve(self, status, body):
        stub = Stub(status, body)
        self.addCleanup(stub.close)
        return stub

    def test_all_fields_ok(self):
        stub = self.serve(200, observation())
        code, out = run(stub.url)
        self.assertEqual(code, 0, out)
        self.assertEqual(stub.paths, ['/v1/observations/latest'])
        fields = [line for line in out.splitlines() if ': ' in line and not line.startswith('e2e')]
        self.assertGreaterEqual(len(fields), 22)
        self.assertTrue(all(line.startswith('ok') for line in fields), out)
        self.assertNotIn('(fitted)', out)
        self.assertNotIn('FAIL', out)

    def test_calm_wind_is_ok(self):
        stub = self.serve(200, observation(wind_speed_ms=0.0, wind_gust_ms=0.0, wind_dir_deg=None, wind_calm=True))
        code, out = run(stub.url)
        self.assertEqual(code, 0, out)

    def test_power_pending(self):
        stub = self.serve(200, observation(power=False))
        code, out = run(stub.url, '--power-pending')
        self.assertEqual(code, 0, out)
        for name in POWER:
            self.assertRegex(out, rf'(?m)^pending \(INVALID, expected\) {name}$')
        self.assertEqual(sum(line.startswith('pending (INVALID, expected)') for line in out.splitlines()), len(POWER))

    def test_power_pending_accepts_fitted_values(self):
        stub = self.serve(200, observation(batt_mv=None, batt_current_ma=None))
        code, out = run(stub.url, '--power-pending')
        self.assertEqual(code, 0, out)
        self.assertIn('ok (fitted) load_mv: 3880', out)
        self.assertIn('pending (INVALID, expected) batt_mv', out)

    def test_power_set_is_what_v6_sends(self):
        header = (ROOT / 'firmware/stage0-node/App/node_fields.h').read_text()
        block = re.search(r'#define WS_F_WSMP_POWER \((.*?)\)\n#define', header, re.S).group(1)
        sent = {m.lower() for m in re.findall(r'WS_FI_(\w+)', block)}
        self.assertEqual(len(sent), 13)
        self.assertEqual(set(POWER), sent)
        self.assertEqual(set(POWER), set(V6_POWER))
        self.assertTrue(set(POWER) <= set(fields.BY_NAME))

    def test_power_invalid_without_flag_fails(self):
        stub = self.serve(200, observation(power=False))
        code, out = run(stub.url)
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL    batt_mv: INVALID', out)

    def test_out_of_range_and_gust_below_speed_fail(self):
        for over, name in (({'pressure_hpa': 700.0}, 'pressure_hpa'), ({'wind_gust_ms': 1.0}, 'wind_gust_ms'),
                           ({'temperature_c': None}, 'temperature_c'), ({'wind_dir_deg': 360}, 'wind_dir_deg'),
                           ({'rain_tips': -1}, 'rain_tips')):
            with self.subTest(name):
                stub = self.serve(200, observation(**over))
                code, out = run(stub.url)
                self.assertEqual(code, 1, out)
                self.assertIn(f'FAIL    {name}:', out)

    def test_stale_observation_fails(self):
        stub = self.serve(200, observation(age=600))
        code, out = run(stub.url, '--max-age', '180')
        self.assertEqual(code, 1, out)
        self.assertIn('stale', out)
        code, out = run(stub.url, '--max-age', '900')
        self.assertEqual(code, 0, out)

    def test_untimely_observation_fails(self):
        # The gateway holds the record untimely (no effective time: an unknown or rejected clock). Its own
        # sampled_at is fresh, but the age must not come from it.
        reply = observation(age=10)
        reply.update(effective_sampled_at=None, available=False, reason='unknown_clock', age_seconds=None)
        stub = self.serve(200, reply)
        code, out = run(stub.url)
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL    age: untimely (no effective time)', out)
        self.assertNotIn('Traceback', out)

    def test_gateway_verdict_not_current_fails(self):
        # Fields in range and a young age, but the gateway itself does not serve the record as current.
        for reason in ('time_uncertain', 'future_clock_at_receipt', 'sensor_fault', 'stale_or_clock_step'):
            with self.subTest(reason):
                reply = observation(age=10)
                reply.update(available=False, reason=reason)
                stub = self.serve(200, reply)
                code, out = run(stub.url)
                self.assertEqual(code, 1, out)
                self.assertIn(f'FAIL    gateway: not current ({reason})', out)
                self.assertIn('e2e: FAILED', out)
        stub = self.serve(200, observation())
        code, out = run(stub.url)
        self.assertEqual(code, 0, out)
        self.assertIn('ok      gateway: fresh', out)

    def test_age_is_the_gateways(self):
        # The gateway's clock is 3 min behind this host's: its effective time looks 190 s old here, but its
        # own age_seconds says 10 s.
        reply = observation(age=10)
        reply['effective_sampled_at'] = time.time() - 190
        stub = self.serve(200, reply)
        code, out = run(stub.url)
        self.assertEqual(code, 0, out)
        self.assertIn('ok      age: 10 s', out)
        reply['age_seconds'] = 600   # and a stale one by the gateway's clock fails, though it looks fresh here
        reply['effective_sampled_at'] = time.time() - 10
        stub = self.serve(200, reply)
        code, out = run(stub.url)
        self.assertEqual(code, 1, out)
        self.assertIn('stale   age: 600 s', out)

    def test_no_observation_and_bad_token(self):
        for status, body in ((404, {'error': 'not_found'}),
                             (200, {'available': False, 'reason': 'no_observation'})):
            stub = self.serve(status, body)
            code, out = run(stub.url)
            self.assertEqual(code, 1, out)
            self.assertEqual(len(out.strip().splitlines()), 1, out)
            self.assertIn('no observation', out)
        stub = self.serve(200, observation())
        code, out = run(stub.url, token='wrong')
        self.assertEqual(code, 1, out)
        self.assertEqual(len(out.strip().splitlines()), 1, out)
        self.assertIn('401', out)
        self.assertNotIn('wrong', out)
        self.assertNotIn('Traceback', out)

    def test_unreachable_gateway(self):
        stub = Stub(200, {})
        url = stub.url
        stub.close()
        code, out = run(url)
        self.assertEqual(code, 1, out)
        self.assertEqual(out.strip(), f'FAIL: gateway not reachable at {url}')

    def test_bad_urls_and_replies_never_traceback(self):
        def one_line(code, out, *needles):
            self.assertEqual(code, 1, out)
            self.assertEqual(len(out.strip().splitlines()), 1, out)
            self.assertNotIn('Traceback', out)
            for needle in needles:
                self.assertIn(needle, out)
        one_line(*run('http://[::1'), 'http')
        one_line(*run('http://'), 'FAIL')
        one_line(*run('file:///etc/hosts'), 'http')
        one_line(*run('ftp://127.0.0.1/'), 'http')
        one_line(*run('not a url'), 'http')
        for status, body in ((200, []), (200, 'text'), (200, None), (200, {'available': True})):
            with self.subTest(body=body):
                stub = self.serve(status, body)
                one_line(*run(stub.url), 'FAIL')
        stub = Stub(200, None, raw=b'garbage, not json')
        self.addCleanup(stub.close)
        one_line(*run(stub.url), 'no usable reply')
        stub = Stub(200, None, raw=b'{"observ')   # Content-Length promises more than is sent
        self.addCleanup(stub.close)
        one_line(*run(stub.url), 'FAIL')

    def test_token_only_from_env(self):
        stub = self.serve(200, observation())
        code, out = run(stub.url, token=None)
        self.assertEqual(code, 2, out)
        self.assertIn('set WS0_API_TOKEN', out)
        self.assertEqual(stub.paths, [])
        source = TOOL.read_text()
        self.assertNotRegex(source, r'(?<![\w.])open\(')
        self.assertNotIn('read_text', source)
        self.assertNotIn('gateway.json', source)


if __name__ == '__main__':
    unittest.main()
