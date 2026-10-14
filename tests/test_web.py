"""Web dashboard back end (ws0/web.py): event stream, resume, stream cap, history, telemetry tables."""
import os
os.environ.setdefault('WS0_UNSAFE_FAST_FSYNC', '1')  # unit tests do not claim power-loss durability (G4)

import http.client
import io
import json
import shutil
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ws0 import web
from ws0.__main__ import handle_receiver_line, provision
from ws0.service import Gateway, http_server, load_config
from ws0.simulator import DemoReceiver, Node

ROOT = Path(__file__).resolve().parent.parent


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'state'
        provision(self.root)
        self.cfg = load_config(self.root / 'gateway.json')
        self.gateway = Gateway(self.cfg, self.root)
        self.gateway.hub.heartbeat_s = 0.2
        self.node = Node(self.cfg, self.root)
        self.node.synced = True
        self.server = None

    def tearDown(self):
        if self.server:
            self.gateway.hub.close()
            self.server.shutdown()
            self.server.server_close()
        for db in (self.gateway.store.db, self.gateway.nonces.db, self.node.db, self.node.nonces.db):
            db.close()
        self.tmp.cleanup()

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
