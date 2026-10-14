"""Web dashboard back end (ws0/web.py): event stream, resume, stream cap, history, telemetry tables."""
import http.client
import io
import json
import shutil
import subprocess
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

try:                                        # first: sets WS0_UNSAFE_FAST_FSYNC before ws0 is imported
    from toolchain import StationTest
except ImportError:
    from tests.toolchain import StationTest
from ws0 import web
from ws0.__main__ import handle_receiver_line
from ws0.service import http_server
from ws0.simulator import DemoReceiver

ROOT = Path(__file__).resolve().parent.parent


class Fixture(StationTest):
    def setUp(self):
        super().setUp()
        self.gateway.hub.heartbeat_s = 0.2
        self.server = None

    def tearDown(self):
        if self.server:
            self.gateway.hub.close()
            self.server.shutdown()
            self.server.server_close()
        super().tearDown()

    def serve(self):
        self.server = http_server(self.gateway, 0)
        self.port = self.server.server_port

    def get(self, path, auth=True, token=None):
        headers = {'Authorization': 'Bearer ' + (token or self.cfg['api_token'])} if auth else {}
        return urlopen(Request(f'http://127.0.0.1:{self.port}{path}', headers=headers), timeout=5)

    def get_json(self, path):
        with self.get(path) as r:
            return json.load(r)

    def observe(self, t, fault=False, clock_known=True):
        record = self.node.sample(t, fault, clock_known=clock_known)
        self.node.acknowledge(self.gateway.receive(self.node.packet(record), t + 1))
        return record

    # -- SSE client ---------------------------------------------------------------------------
    def open_stream(self, cursor=None, query=''):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        headers = {'Authorization': 'Bearer ' + self.cfg['api_token']}
        if cursor:
            headers['Last-Event-ID'] = cursor
        conn.request('GET', '/v1/events' + query, headers=headers)
        response = conn.getresponse()
        self.addCleanup(conn.close)
        return conn, response

    @staticmethod
    def read_block(response):
        """Lines of the next SSE block (up to a blank line)."""
        lines = []
        while True:
            line = response.readline()
            if not line:
                return lines or None
            line = line.decode().rstrip('\n')
            if line == '':
                if lines:
                    return lines
                continue
            lines.append(line)

    def next_event(self, response):
        """(id, type, data) of the next event, skipping comment-only blocks (heartbeats)."""
        while True:
            block = self.read_block(response)
            if block is None:
                return None
            fields = {}
            for line in block:
                if line.startswith(':'):
                    continue
                name, _, value = line.partition(': ')
                fields[name] = value
            if 'data' in fields:
                return fields.get('id'), fields.get('event'), json.loads(fields['data'])


class StaticAndAuth(Fixture):
    def test_page_is_served_without_auth_and_holds_no_data(self):
        self.observe(1000)
        self.serve()
        for path in ('/', '/dashboard', '/static/app.js', '/static/app.css'):
            with self.get(path, auth=False) as r:
                body = r.read().decode()
                self.assertEqual(r.status, 200)
                self.assertIn("default-src 'none'", r.headers['Content-Security-Policy'])
                self.assertEqual(r.headers['X-Content-Type-Options'], 'nosniff')
                self.assertNotIn(self.cfg['api_token'], body)
                self.assertNotIn(self.cfg['station'], body)
        with self.get('/', auth=False) as r:
            self.assertTrue(r.headers['Content-Type'].startswith('text/html'))
        # Only the fixed table is served: no path reaches the run directory or the package.
        for path in ('/static/../gateway.json', '/static/web.py', '/gateway.json', '/static/'):
            with self.assertRaises(HTTPError) as exc:
                self.get(path, auth=False)
            self.assertEqual(exc.exception.code, 401)

    def test_every_dashboard_endpoint_needs_the_token(self):
        self.serve()
        for path in web.ROUTES:
            for token in (None, 'x' * 43):
                with self.assertRaises(HTTPError) as exc:
                    self.get(path, auth=token is not None, token=token)
                self.assertEqual(exc.exception.code, 401, path)
        self.assertEqual(self.gateway.hub.streams, 0)

    def test_page_never_uses_inner_html_or_puts_the_token_in_a_url(self):
        script = (ROOT / 'ws0' / 'static' / 'app.js').read_text()
        for unsafe in ('innerHTML', 'outerHTML', 'insertAdjacentHTML', 'document.write', 'eval(', 'localStorage.setItem(TOKEN'):
            self.assertNotIn(unsafe, script)
        self.assertIn("sessionStorage", script)
        self.assertNotIn('token=', script.replace('TOKEN_KEY', ''))

    def test_page_script_has_no_syntax_errors(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node not installed')
        result = subprocess.run([node, '--check', str(ROOT / 'ws0' / 'static' / 'app.js')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_bind_address(self):
        self.assertEqual(web.bind_address({}), '127.0.0.1')
        self.assertEqual(web.bind_address({'http_bind': '::1'}), '::1')
        with self.assertRaises(ValueError):
            web.bind_address({'http_bind': 'example.com'})
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(web.bind_address({'http_bind': '0.0.0.0'}), '0.0.0.0')
        self.assertIn('not loopback', err.getvalue())
        self.assertNotIn(self.cfg['api_token'], err.getvalue())


class EventStream(Fixture):
    def test_half_open_requests_cannot_exhaust_the_server(self):
        """Security audit: slowloris. Half-sent requests are capped and time out, so an
        authorised request gets through once they are dropped."""
        import socket
        from ws0 import service
        for name, value in (('HTTP_MAX_CONNECTIONS', 4), ('HTTP_TIMEOUT_S', 0.5)):
            self.addCleanup(setattr, service, name, getattr(service, name))
            setattr(service, name, value)
        self.serve()
        held = []
        for _ in range(20):                       # five times the cap, none ever finishes its headers
            s = socket.create_connection(('127.0.0.1', self.port))
            s.sendall(b'GET /v1/status HTTP/1.1\r\nHost: x\r\n')
            held.append(s)
            self.addCleanup(s.close)
        began = time.monotonic()
        for s in held:                             # the server closes every one: over the cap at
            s.settimeout(3)                        # once, the rest when their request times out
            try:
                self.assertIn(s.recv(1024), (b'',))
            except ConnectionResetError:
                pass
        self.assertLess(time.monotonic() - began, 2)
        self.assertEqual(self.get_json('/v1/status')['station'], self.cfg['station'])

    def test_connections_over_the_cap_are_closed_at_once(self):
        import socket
        from ws0 import service
        for name, value in (('HTTP_MAX_CONNECTIONS', 4), ('HTTP_TIMEOUT_S', 30)):
            self.addCleanup(setattr, service, name, getattr(service, name))
            setattr(service, name, value)
        self.serve()
        held = []
        for _ in range(10):
            s = socket.create_connection(('127.0.0.1', self.port))
            s.sendall(b'GET /v1/status HTTP/1.1\r\n')
            s.settimeout(0.3)
            held.append(s)
            self.addCleanup(s.close)
        closed = 0
        for s in held:
            try:
                closed += s.recv(1024) == b''
            except ConnectionResetError:
                closed += 1
            except socket.timeout:
                pass                               # within the cap: still waiting for its headers
        self.assertEqual(closed, 6)

    def test_ipv6_bind_serves(self):
        """GW9: an IPv6 http_bind used to crash (the stock server is AF_INET only)."""
        import socket
        if not socket.has_ipv6:
            self.skipTest('no IPv6')
        try:
            with socket.socket(socket.AF_INET6) as probe:
                probe.bind(('::1', 0))
        except OSError:
            self.skipTest('no IPv6 loopback')
        self.cfg['http_bind'] = '::1'
        self.serve()
        request = Request(f'http://[::1]:{self.port}/v1/status',
                          headers={'Authorization': 'Bearer ' + self.cfg['api_token']})
        with urlopen(request, timeout=5) as r:
            self.assertEqual(r.status, 200)

    def test_framing_live_observation_and_heartbeat(self):
        self.serve()
        _, response = self.open_stream()
        self.assertEqual(response.status, 200)
        self.assertTrue(response.headers['Content-Type'].startswith('text/event-stream'))
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.read_block(response), [': ws0 event stream', 'retry: 2000'])
        hello = self.read_block(response)
        self.assertEqual(hello[0], f'id: {self.gateway.hub.instance}-0')
        self.assertEqual(hello[1], 'event: hello')
        data = json.loads(hello[2].removeprefix('data: '))
        self.assertFalse(data['resumed'])
        self.assertEqual(self.read_block(response), [': heartbeat'])   # idle stream
        sent = time.monotonic()
        record = self.observe(time.time())
        event_id, kind, data = self.next_event(response)
        self.assertLess(time.monotonic() - sent, 1.0)
        self.assertEqual((kind, event_id), ('observation', f'{self.gateway.hub.instance}-1'))
        self.assertEqual(data['record']['sequence'], record['sequence'])
        self.assertEqual(data['record']['time_basis'], 'synchronized')
        self.assertTrue(data['latest']['available'])
        diag = self.node.diagnostic(time.time())
        self.gateway.receive(diag)
        _, kind, data = self.next_event(response)
        self.assertEqual((kind, data['journal_pending']), ('diagnostic', 0))

    def test_resume_replays_exactly_what_was_missed(self):
        self.serve()
        _, response = self.open_stream()
        self.next_event(response)   # hello
        for i in range(3):
            self.gateway.telemetry.event(f'#gateway test {i}', at=1000 + i)
        first, _, _ = self.next_event(response)
        response.close()
        self.gateway.telemetry.event('#gateway test 3', at=1003)   # while disconnected
        for query, cursor in (('', first), (f'?since={first}', None)):
            _, again = self.open_stream(cursor=cursor, query=query)
            _, kind, hello = self.next_event(again)
            self.assertEqual(kind, 'hello')
            self.assertTrue(hello['resumed'])
            texts = [self.next_event(again)[2]['text'] for _ in range(3)]
            self.assertEqual(texts, ['#gateway test 1', '#gateway test 2', '#gateway test 3'])
            again.close()

    def test_unknown_or_expired_cursor_gets_resync(self):
        self.gateway.hub.events = web.collections.deque(maxlen=3)
        self.serve()
        for i in range(6):
            self.gateway.telemetry.event(f'#gateway test {i}')
        hub = self.gateway.hub
        for cursor in ('deadbeef-2', f'{hub.instance}-1', f'{hub.instance}-99', 'garbage'):
            _, response = self.open_stream(cursor=cursor)
            _, kind, data = self.next_event(response)
            self.assertEqual(kind, 'resync', cursor)
            _, kind, hello = self.next_event(response)
            self.assertEqual(kind, 'hello')
            self.assertFalse(hello['resumed'])
            response.close()
        self.assertEqual(hub.resume_point(f'{hub.instance}-3'), 3)   # oldest kept is 4: 3 is still exact

    def test_stream_cap_and_release(self):
        self.gateway.hub.max_streams = 2
        self.serve()
        streams = [self.open_stream()[1] for _ in range(2)]
        for s in streams:
            self.assertEqual(self.next_event(s)[1], 'hello')
        with self.assertRaises(HTTPError) as exc:
            self.get('/v1/events')
        self.assertEqual(exc.exception.code, 503)
        self.assertEqual(exc.exception.headers['Retry-After'], '5')
        streams[0].close()
        deadline = time.monotonic() + 3
        while self.gateway.hub.streams > 1 and time.monotonic() < deadline:   # noticed at the next heartbeat
            time.sleep(0.05)
        self.assertEqual(self.gateway.hub.streams, 1)
        _, response = self.open_stream()
        self.assertEqual(response.status, 200)

    def test_stuck_client_releases_its_slot(self):
        """GW8: a client that connects and never reads must not hold a stream slot forever."""
        import socket
        old = web.STREAM_SEND_TIMEOUT_S
        web.STREAM_SEND_TIMEOUT_S = 0.5
        self.addCleanup(setattr, web, 'STREAM_SEND_TIMEOUT_S', old)
        self.serve()
        client = socket.socket()
        client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        client.connect(('127.0.0.1', self.port))
        self.addCleanup(client.close)
        client.sendall(f'GET /v1/events HTTP/1.1\r\nHost: x\r\n'
                       f'Authorization: Bearer {self.cfg["api_token"]}\r\n\r\n'.encode())
        deadline = time.monotonic() + 3
        while not self.gateway.hub.streams and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(self.gateway.hub.streams, 1)
        blob = 'x' * 8000                     # fill both socket buffers; the client never reads
        deadline = time.monotonic() + 10
        while self.gateway.hub.streams and time.monotonic() < deadline:
            self.gateway.hub.publish('noise', json.dumps(blob))
            time.sleep(0.005)
        self.assertEqual(self.gateway.hub.streams, 0)

    def test_close_ends_streams(self):
        self.serve()
        _, response = self.open_stream()
        self.next_event(response)
        self.gateway.hub.close()
        self.assertIsNone(self.next_event(response))
        deadline = time.monotonic() + 3
        while self.gateway.hub.streams and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(self.gateway.hub.streams, 0)


class History(Fixture):
    def test_history_keeps_gaps_faults_and_time_basis(self):
        base = 1_700_000_000
        for i in range(10):
            self.observe(base + 60 * i, fault=i in (4, 5))
        self.observe(base + 60 * 12)   # minutes 10 and 11 missing: a gap, not zeros
        self.serve()
        h = self.get_json('/v1/history?from=2023-11-14T00:00:00Z&to=2023-11-15T00:00:00Z')
        o = h['observations']
        self.assertEqual(o['bucket_s'], 0)
        self.assertEqual(o['fields'], ['temperature_c', 'humidity_pct'])
        self.assertEqual(o['units']['temperature_c'], '°C')
        self.assertEqual(len(o['t']), 11)
        self.assertEqual(o['values']['temperature_c'][4:6], [None, None])
        self.assertNotIn(0, o['values']['humidity_pct'])
        self.assertEqual(o['quality'][4], 'sensor_fault')
        self.assertEqual(set(o['basis']), {'synchronized'})
        self.assertEqual(o['t'][-1] - o['t'][-2], 180)
        # Downsampled: a bucket whose readings are all faults stays null.
        h = self.get_json('/v1/history?from=2023-11-14T22:13:00Z&to=2023-11-14T22:33:00Z&max_points=10')
        o = h['observations']
        self.assertEqual(o['bucket_s'], 120)
        self.assertIn(None, o['values']['temperature_c'])
        self.assertLess(len(o['t']), 11)

    def test_history_bucket_rules_per_series(self):
        """Characterization of each history series when bucketed: observations (mean, or last for
        direction and counters; mixed quality is partial; reconstructed wins), receiver (last, max
        for stack_peak), diagnostics thinning (keeps every state change) and the newest 500 events."""
        base, station, db = 1_700_000_000, self.cfg['station'], self.gateway.store.db
        rows = [  # offset, basis, quality, session, temperature, wind dir, rain tips
            (0, 'synchronized', 'valid', '1', 20, 90, 1), (10, 'reconstructed', 'valid', '1', 21, None, 2),
            (20, 'synchronized', 'partial', '2', None, 180, None),
            (130, 'synchronized', 'valid', '2', 22.25, 10, 5), (140, 'synchronized', 'valid', '2', 22.5, None, None)]
        with db:
            for seq, (dt, basis, quality, session, temp, wdir, tips) in enumerate(rows):
                payload = {'session': session, 'quality': quality, 'temperature_c': temp, 'wind_dir_deg': wdir,
                           'rain_tips': tips}
                db.execute('INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?)',
                           (station, session, seq, base + dt, base + dt + 1, json.dumps(payload), 0, base + dt,
                            basis, 0))
            db.execute('INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (station, '9', 0, None, base + 5, json.dumps({'session': '9'}), 0, None, None, None))
            for dt, forwarded, peak in ((0, 1, 5), (30, 2, None), (60, None, 3), (150, 7, None)):
                db.execute('INSERT INTO rx_alive (station,received_at,forwarded,stack_peak) VALUES (?,?,?,?)',
                           (station, base + dt, forwarded, peak))
            db.executemany('INSERT INTO gateway_events (station,at,source,kind,level,text) VALUES (?,?,?,?,?,?)',
                           ((station, base + i * 0.25, 'gw', 'k', 'info', str(i)) for i in range(502)))
        for i in range(7):
            self.gateway.store.diagnostic(station, {'epoch': 1, 'uptime_s': i, 'firmware_build': 'b', 'link': 'up',
                                                    'energy_state': 'conserve' if i >= 2 else 'normal'}, base + i)
        h = web.history(self.gateway, base, base + 240, 2)
        o = h['observations']
        self.assertEqual((o['bucket_s'], o['t'], o['unknown_time_count']), (120, [base, base + 120], 1))
        self.assertEqual(o['fields'], ['temperature_c', 'wind_dir_deg', 'rain_tips'])
        self.assertEqual(o['values'], {'temperature_c': [20.5, 22.375], 'wind_dir_deg': [180, 10],
                                       'rain_tips': [2, 5]})
        self.assertEqual((o['basis'], o['quality'], o['session']),
                         (['reconstructed', 'synchronized'], ['partial', 'valid'], ['2', '2']))
        r = h['receiver']
        self.assertEqual((r['bucket_s'], r['t'], r['forwarded'], r['stack_peak'], r['uptime_s']),
                         (120, [base, base + 120], [2, 7], [5, None], [None, None]))
        self.assertEqual([d['uptime_s'] for d in h['diagnostics']], [0, 2, 4, 6])
        self.assertEqual((len(h['events']), h['events'][0]['text'], h['events'][-1]['text']), (500, '2', '501'))
        whole = web.history(self.gateway, base, base + 240, 1500)     # small enough: one point per row
        self.assertEqual(whole['observations']['values']['wind_dir_deg'], [90, None, 180, 10, None])
        self.assertEqual(whole['receiver']['stack_peak'], [5, None, 3, None])
        self.assertEqual(len(whole['diagnostics']), 7)

    def radio(self, start, end, max_points):
        with self.gateway.store.reader() as db:
            return web.radio_series(db, self.cfg['station'], start, end, max_points)

    def test_history_never_waits_for_the_ingest_lock(self):
        """Dashboard reads use their own read-only connection: a long history query must not hold
        (or wait for) the store lock that the radio receive path needs before its ACK."""
        import threading
        self.observe(1_700_000_000)
        held, release = threading.Event(), threading.Event()
        def hold():
            with self.gateway.store.lock:
                held.set()
                release.wait(10)
        t = threading.Thread(target=hold)
        t.start()
        held.wait(5)
        try:
            began = time.monotonic()
            h = web.history(self.gateway, 1_699_999_000, 1_700_001_000)
            self.assertLess(time.monotonic() - began, 1)
            self.assertEqual(len(h['observations']['t']), 1)
        finally:
            release.set()
            t.join()

    def test_receiver_history_covers_a_range_past_100000_reports(self):
        """GW11 for RX reports: a long range is bucketed whole, not cut at a row limit."""
        base, n = 1_700_000_000, 120_000
        station = self.cfg['station']
        with self.gateway.store.db:
            self.gateway.store.db.executemany(
                'INSERT INTO rx_alive (station,received_at,uptime_s,forwarded) VALUES (?,?,?,?)',
                ((station, base + 60 * i, 60 * i, i) for i in range(n)))
        h = web.history(self.gateway, base, base + 60 * n, 1500)
        receiver = h['receiver']
        self.assertGreater(receiver['bucket_s'], 0)
        self.assertEqual(receiver['forwarded'][-1], n - 1)      # the newest report is in the last bucket
        self.assertGreater(receiver['t'][-1], base + 60 * (n - 1) - receiver['bucket_s'])

    def test_history_query_uses_its_index(self):
        plan = ' '.join(r[-1] for r in self.gateway.store.db.execute('EXPLAIN QUERY PLAN ' + web.HISTORY_SQL,
                                                                     ('s', 0, 1)))
        self.assertIn('obs_effective_order', plan)
        self.assertNotIn('TEMP B-TREE', plan)

    def test_radio_buckets_match_python_and_count_every_frame(self):
        """GW11: bucketed radio points are computed in SQLite and match the per-row Python rule
        (mean, exact single values, nulls, outcome counts); a range past 100,000 frames is whole."""
        import collections
        import random
        rng = random.Random(7)
        base, n = 1_700_000_000, 120_000
        outcomes = ('ack', 'rejected', 'duplicate', 'dropped_by_rx')
        rows = []
        for i in range(n):
            rssi = None if rng.random() < 0.05 else rng.randint(-120, -40)
            snr = None if rng.random() < 0.05 else rng.randint(-20, 12)
            rows.append(('station-x', base + i * 0.5 + rng.random() * 0.4, rng.choice(('obs', 'diag', None)),
                         i, rng.choice(outcomes), rssi, snr))
        station = self.cfg['station']
        rows = [(station, *r[1:]) for r in rows]
        with self.gateway.store.db:
            self.gateway.store.db.executemany(
                'INSERT INTO radio_events (station,received_at,kind,counter,outcome,rssi_dbm,snr_db) '
                'VALUES (?,?,?,?,?,?,?)', rows)
        start, end = base, base + n * 0.5
        got = self.radio(start, end, 1500)
        self.assertEqual(sum(got['frames']), n)                        # nothing cut off
        bucket = got['bucket_s']
        self.assertGreater(bucket, 0)
        want = collections.defaultdict(list)
        for r in rows:
            want[start + (r[1] - start) // bucket * bucket].append(r)
        self.assertEqual(got['t'], sorted(want))
        for i, t in enumerate(got['t']):
            group = want[t]
            self.assertEqual(got['frames'][i], len(group))
            self.assertEqual(got['rssi_dbm'][i], web._mean([r[5] for r in group]))
            self.assertEqual(got['snr_db'][i], web._mean([r[6] for r in group]))
            self.assertEqual(got['rssi_min'][i], min((r[5] for r in group if r[5] is not None), default=None))
            self.assertEqual(got['outcome'][i], dict(collections.Counter(r[4] for r in group)))
        # sparse buckets: no reading, exactly one reading, and one reading beside a null
        b2 = base + 10_000_000
        sparse = [(station, b2 + i, 'obs', i, 'ack', -50 - i, 5) for i in range(9)]
        sparse += [(station, b2 + 600, 'obs', 20, 'rejected', None, None),
                   (station, b2 + 1200, 'obs', 21, 'ack', -61, 4),
                   (station, b2 + 1800, None, 22, 'ack', None, None), (station, b2 + 1801, None, 23, 'rejected', -70, None),
                   (station, b2 + 2400, None, 24, 'dropped_by_rx', None, None), (station, b2 + 2401, None, 25, 'ack', None, None)]
        with self.gateway.store.db:
            self.gateway.store.db.executemany(
                'INSERT INTO radio_events (station,received_at,kind,counter,outcome,rssi_dbm,snr_db) '
                'VALUES (?,?,?,?,?,?,?)', sparse)
        got = self.radio(b2, b2 + 6000, 10)
        self.assertEqual(got['bucket_s'], 600)
        self.assertEqual(got['frames'], [9, 1, 1, 2, 2])
        self.assertEqual(got['rssi_dbm'], [-54, None, -61, -70, None])
        self.assertEqual(got['snr_db'], [5, None, 4, None, None])
        self.assertEqual(got['outcome'][1:3], ['rejected', 'ack'])
        self.assertEqual((got['kind'][1:3], got['counter'][1:3]), (['obs', 'obs'], [20, 21]))
        self.assertEqual(got['outcome'][3], {'ack': 1, 'rejected': 1})
        # a small range is per frame, as before
        small = self.radio(start, start + 30, 1500)
        self.assertEqual((small['bucket_s'], len(small['t'])), (0, 60))
        self.assertEqual(small['outcome'][0], rows[0][4])

    def test_reconstructed_and_unknown_time(self):
        base = 1_700_000_000
        self.node.synced = False
        self.observe(base, clock_known=False)          # no time yet: counted, not plotted
        self.serve()
        h = self.get_json('/v1/history?from=2023-11-14T00:00:00Z&to=2023-11-15T00:00:00Z')
        self.assertEqual((h['observations']['t'], h['observations']['unknown_time_count']), ([], 1))
        self.node.synced = True
        self.observe(base + 60)                        # gives the first one a reconstructed time
        h = self.get_json('/v1/history?from=2023-11-14T00:00:00Z&to=2023-11-15T00:00:00Z')
        self.assertEqual(h['observations']['basis'], ['reconstructed', 'synchronized'])

    def test_raw_tables_and_parameters(self):
        t = self.gateway.telemetry
        for i in range(5):
            t.frame(self.node.packet(self.node.sample(1000 + i)), 'ack', delivered=True, at=1000 + i)
            t.rx_line(f'#rx obs rssi={-40 - i} snr={9 - i}', 1000 + i)
        t.rx_line('#alive uptime=60 forwarded=5 dropped=0 acks=5 diag=0 listening=1 relistens=0 uart_errors=0 stack_peak=900', 1010)
        self.gateway.receive(self.node.diagnostic(1020), 1020)
        t.event('#gateway serial-lost path=/dev/x reason=read:OSError', at=1030)
        self.serve()
        rows = self.get_json('/v1/radio?order=desc&limit=2')['rows']
        self.assertEqual([r['rssi_dbm'] for r in rows], [-44, -43])
        self.assertEqual(rows[0]['outcome'], 'ack')
        self.assertNotIn('station', rows[0])
        alive = self.get_json('/v1/receiver/alive')['rows']
        self.assertEqual((alive[0]['forwarded'], alive[0]['stack_peak'], alive[0]['uptime_s']), (5, 900, 60))
        diags = self.get_json('/v1/diagnostics')['rows']
        self.assertEqual((diags[0]['firmware_build'], diags[0]['received_at']), ('5eed0001', 1020))
        events = self.get_json('/v1/gateway/events?from=1970-01-01T00:16:00Z')['rows']
        self.assertEqual((events[0]['kind'], events[0]['level']), ('serial-lost', 'warn'))
        h = self.get_json('/v1/history?from=1970-01-01T00:00:00Z&to=1970-01-01T01:00:00Z')
        self.assertEqual(h['radio']['rssi_dbm'], [-40, -41, -42, -43, -44])
        self.assertEqual(h['receiver']['forwarded'], [5])
        self.assertEqual(len(h['diagnostics']), 1)
        self.assertEqual(h['events'][0]['text'], '#gateway serial-lost path=/dev/x reason=read:OSError')
        for bad in ('/v1/radio?limit=0', '/v1/radio?order=sideways', '/v1/history?from=2024-01-01T00:00:00',
                    '/v1/history?from=2024-01-02T00:00:00Z&to=2024-01-01T00:00:00Z', '/v1/history?max_points=5'):
            with self.assertRaises(HTTPError) as exc:
                self.get(bad)
            self.assertEqual(exc.exception.code, 400, bad)


class ServeLoopTelemetry(Fixture):
    class Link:
        def __init__(self):
            self.written = []

        def write(self, data):
            self.written.append(data)
            return True

    def lines(self, *texts, now=2000):
        log = io.StringIO()
        link = self.Link()
        with redirect_stderr(io.StringIO()), redirect_stdout_quiet():
            for i, text in enumerate(texts):
                handle_receiver_line(self.gateway, link, text.encode(), log, now + i)
        return log.getvalue(), link

    def rows(self, sql):
        return self.gateway.store.db.execute(sql).fetchall()

    def test_forged_frame_flood_is_bounded_and_real_data_still_lands(self):
        """GW6: a flood of junk frames (each with its RSSI line) and RX drop reports writes at most
        the burst, then a summary with the suppressed count; real frames are never throttled."""
        throttle = self.gateway.telemetry.throttle
        burst, rate = throttle.burst, throttle.per_s
        throttle.per_s = 0                                 # lines() steps the clock 1 s per line
        flood = []
        for _ in range(3 * burst):
            flood += ['ab' * 30, '#rx obs rssi=-90 snr=-5', '#rx drop len=3 rssi=-110 snr=-12']
        log, _ = self.lines(*flood, now=2000)
        count = lambda outcome: self.rows(f"SELECT COUNT(*) FROM radio_events WHERE outcome='{outcome}'")[0][0]
        self.assertEqual(count('rejected'), burst)
        self.assertEqual(count('dropped_by_rx'), burst)
        self.assertEqual(count('unparsed'), 0)            # throttled frames' RSSI lines are dropped too
        self.assertLess(log.count('\n'), 4 * burst)
        # a real observation in the middle of the flood still lands with its RSSI
        obs = self.node.packet(self.node.sample(time.time()))
        _, link = self.lines(obs.hex(), '#rx obs rssi=-51 snr=8', now=2000 + len(flood))
        self.assertEqual(len(link.written), 1)
        self.assertEqual(self.rows("SELECT rssi_dbm FROM radio_events WHERE outcome='ack'"), [(-51,)])
        # once the bucket refills, the next junk frame carries the suppressed count
        throttle.per_s = rate
        log, _ = self.lines('ab' * 30, now=2000 + len(flood) + 2 + 2 / rate)
        self.assertIn(f'suppressed {2 * burst} rejected lines', log)
        events = self.rows("SELECT text FROM gateway_events WHERE kind='suppressed'")
        self.assertEqual(len(events), 1)

    def test_rx_error_flood_is_bounded_and_a_regression_is_never_hidden(self):
        """Security audit: '#rx error' (any radio can cause it) is rate-limited like other noise,
        and a counter regression is logged even while garbage frames are being suppressed."""
        throttle = self.gateway.telemetry.throttle
        throttle.per_s = 0
        burst = throttle.burst
        log, _ = self.lines(*['#rx error'] * (3 * burst), now=5000)
        self.assertEqual(log.count('#rx error'), burst)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM gateway_events WHERE kind='rx_error'")[0][0], burst)
        log, _ = self.lines(*['ab' * 30] * (2 * burst), now=6000)          # garbage uses up 'rejected'
        frames = [self.node.packet(self.node.sample(time.time() + 60 * i)) for i in range(3)]
        log, _ = self.lines(frames[0].hex(), frames[2].hex(), frames[1].hex(), now=7000)
        self.assertIn('CounterRegression', log)

    def test_frames_alive_and_events_reach_sqlite(self):
        obs = self.node.packet(self.node.sample(time.time()))
        diag = self.node.diagnostic(time.time())
        log, link = self.lines('#boot role=rx fw=abc reset=power freq=915000000 bw=500 sf=7 power=0',
                               obs.hex(), '#rx obs rssi=-51 snr=8',
                               diag.hex(), '#rx obs rssi=-52 snr=7',
                               obs.hex(), '#rx obs rssi=-53 snr=6',          # replay: rejected, never answered
                               'zz-not-hex', '#rx obs rssi=-99 snr=-9',
                               '#rx drop len=3 rssi=-110 snr=-12',
                               '#alive uptime=61 forwarded=4 dropped=1 acks=1 diag=1 listening=1 relistens=2 uart_errors=0 stack_peak=1100',
                               '#relisten after 30 s without a radio event')
        self.assertEqual(len(link.written), 1)                        # one ACK
        self.assertIn('#rx obs rssi=-51 snr=8', log)                  # receiver.log keeps everything
        self.assertIn(' frame ', log)
        radio = self.rows('SELECT kind,outcome,rssi_dbm,snr_db,delivered,sequence FROM radio_events ORDER BY id')
        self.assertEqual(radio, [('obs', 'ack', -51, 8, 1, 0), ('diag', 'diag', -52, 7, None, None),
                                 ('obs', 'rejected', -53, 6, None, None), (None, 'rejected', -99, -9, None, None),
                                 ('dropped', 'dropped_by_rx', -110, -12, None, None)])
        alive = self.rows('SELECT uptime_s,forwarded,dropped,relistens,stack_peak FROM rx_alive')
        self.assertEqual(alive, [(61, 4, 1, 2, 1100)])
        self.assertEqual(self.gateway.receiver['relistens'], '2')
        kinds = [r[0] for r in self.rows('SELECT kind FROM gateway_events ORDER BY id')]
        self.assertEqual(kinds, ['rx_boot', 'rejected', 'rejected', 'relisten'])

    def test_database_failure_never_stops_the_serve_loop(self):
        """Review GW1 (2026-10-14): SQLite raises sqlite3.OperationalError (disk full, I/O error,
        locked), not OSError. A failed commit must give no ACK and leave the process running, even
        when the telemetry writes in the error path fail too."""
        import sqlite3
        from unittest.mock import patch
        def broken(*args, **kwargs):
            raise sqlite3.OperationalError('disk I/O error (injected)')
        record = self.node.sample(time.time())
        obs = self.node.packet(record)
        class BrokenDB:                                       # every telemetry write fails too
            execute = staticmethod(broken)
            def __enter__(self): return self
            def __exit__(self, *exc): return False
        with patch.object(self.gateway.store, 'ingest', broken), patch.object(self.gateway.store, 'db', BrokenDB()):
            log, link = self.lines(obs.hex(), '#rx obs rssi=-51 snr=8',
                                   '#alive uptime=61 forwarded=1 dropped=0 acks=0 diag=0 listening=1 relistens=0 '
                                   'uart_errors=0 stack_peak=400')
        self.assertEqual(link.written, [])                    # no ACK: the node keeps the record
        self.assertIn('commit-failed OperationalError', log)  # receiver.log still records it
        # The database works again: the retry (a fresh frame for the same record) is stored and ACKed.
        _, link = self.lines(self.node.packet(record).hex(), '#rx obs rssi=-52 snr=8')
        self.assertEqual(len(link.written), 1)
        self.assertEqual(self.rows('SELECT count(*) FROM observations'), [(1,)])

    def test_ack_nack_duplicate_and_link_down_paths(self):
        """Characterization of each answered-frame path of handle_receiver_line: what is logged,
        printed and written to the link."""
        from contextlib import redirect_stdout
        class DownLink(self.Link):
            def write(self, data):
                self.written.append(data)
                return False
        record = self.node.sample(time.time())
        throttle = self.gateway.telemetry.throttle
        throttle.per_s = 0
        log, out, link = io.StringIO(), io.StringIO(), DownLink()
        retransmits = [self.node.packet(record) for _ in range(throttle.burst + 3)]
        collision = self.node.packet(record | {'temperature_c': record['temperature_c'] + 1})
        with redirect_stderr(io.StringIO()), redirect_stdout(out):
            for i, frame in enumerate(retransmits + [collision]):
                handle_receiver_line(self.gateway, link, frame.hex().encode(), log, 4000 + i)
            handle_receiver_line(self.gateway, link, b'', log, 4100)
        lines = log.getvalue().splitlines()
        self.assertEqual(len(link.written), len(retransmits) + 1)            # every frame is answered
        self.assertEqual(sum(' -> ack ' in line for line in lines), 1 + throttle.burst)   # the rest: throttled
        self.assertTrue(all(line.endswith('(not delivered: serial link down)') for line in lines))
        self.assertTrue(lines[-1].split(' frame ')[1].startswith(collision.hex() + ' -> nack '))
        printed = [json.loads(line) for line in out.getvalue().splitlines()]
        # Answered with an ACK and logged (not throttled, not a NACK): the stored-or-duplicate record.
        self.assertEqual([p['observation']['duplicate'] for p in printed], [False] + [True] * throttle.burst)
        self.assertEqual({p['observation']['sequence'] for p in printed}, {record['sequence']})
        self.gateway.telemetry.tick(5000 + web.PENDING_RSSI_S)
        rows = self.rows('SELECT outcome,delivered FROM radio_events ORDER BY id')
        self.assertEqual(rows, [('ack', 0)] + [('duplicate', 0)] * throttle.burst + [('nack', 0)])

    def test_rssi_line_of_a_throttled_frame_is_dropped(self):
        self.gateway.telemetry.muted = True
        log, _ = self.lines('#rx obs rssi=-90 snr=-5', '#rx obs rssi=-91 snr=-5')
        self.assertEqual(log.splitlines()[0][-len('#rx obs rssi=-91 snr=-5'):], '#rx obs rssi=-91 snr=-5')
        self.assertEqual(len(log.splitlines()), 1)
        self.assertFalse(self.gateway.telemetry.muted)

    def test_frame_without_rssi_line_is_written_after_a_timeout(self):
        obs = self.node.packet(self.node.sample(time.time()))
        self.lines(obs.hex(), now=3000)
        self.assertEqual(self.rows('SELECT count(*) FROM radio_events'), [(0,)])
        self.gateway.telemetry.tick(3001)
        self.assertEqual(self.rows('SELECT count(*) FROM radio_events'), [(0,)])
        self.gateway.telemetry.tick(3000 + web.PENDING_RSSI_S + 1)
        self.assertEqual(self.rows('SELECT outcome,rssi_dbm FROM radio_events'), [('ack', None)])

    def test_demo_receiver_fills_every_table(self):
        clock = [5000.0]
        demo = DemoReceiver(self.gateway, self.node, clock=lambda: clock[0])
        demo.tick()                                    # first #alive
        self.node.acknowledge(demo.deliver(self.node.packet(self.node.sample(time.time()))))
        clock[0] += 10
        demo.tick()                                    # first health report
        self.assertEqual(self.rows('SELECT kind,outcome FROM radio_events ORDER BY id'), [('obs', 'ack'), ('diag', 'diag')])
        self.assertEqual(self.rows('SELECT count(*) FROM rx_alive'), [(1,)])
        self.assertTrue(self.gateway.receiver['alive'])
        self.assertIsNotNone(self.gateway.store.latest_diagnostic(self.cfg['station']))


class redirect_stdout_quiet:
    """The serve loop prints each stored observation to stdout; keep test output clean."""
    def __enter__(self):
        from contextlib import redirect_stdout
        self.cm = redirect_stdout(io.StringIO())
        return self.cm.__enter__()

    def __exit__(self, *exc):
        return self.cm.__exit__(*exc)


if __name__ == '__main__':
    unittest.main()
