"""tools/e2e_check.py against a stub of the gateway's /v1/observations/latest."""
import json
import os
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
import e2e_check  # noqa: E402

POWER = e2e_check.POWER


def observation(age=10, power=True, **over):
    now = time.time()
    record = dict(temperature_c=21.5, humidity_pct=48.0, enclosure_temp_c=24.0, enclosure_rh_pct=40.0,
                  pressure_hpa=1013.2, uva_raw=1234, wind_speed_ms=2.5, wind_gust_ms=4.0, wind_dir_deg=270,
                  wind_calm=False, rain_tips=3, sampled_at=now - age)
    for name in POWER:
        record[name] = (87 if name == 'soc_gauge_pct' else 3900) if power else None
    record.update(over)
    return {'available': True, 'reason': 'fresh', 'age_seconds': age, 'observation': record,
            'effective_sampled_at': now - age}


class Stub:
    """Serves `reply` as (status, body) on a free port; checks the bearer token like the gateway."""
    def __init__(self, status, body):
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                stub.paths.append(self.path)
                ok = self.headers.get('Authorization') == 'Bearer ' + TOKEN
                code, payload = (status, body) if ok else (401, {'error': 'unauthorized'})
                data = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header('Content-Length', str(len(data)))
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
        self.assertGreaterEqual(len(fields), 20)
        self.assertTrue(all(line.startswith('ok') for line in fields), out)
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
            self.assertIn(f'{name}: INVALID', out)
        self.assertEqual(sum(line.startswith('pending') for line in out.splitlines()), len(POWER))

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
