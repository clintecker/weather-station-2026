"""Web dashboard back end: radio/receiver telemetry tables, a live event stream and history.

docs/web-dashboard.md describes the page. Server side, three things live here:

* Telemetry: what the serve loop learns that is not an observation, persisted in the gateway's
  SQLite database (observations.sqlite3): one row per radio frame with the RX board's RSSI/SNR
  (radio_events), the RX board's 60 s #alive reports (rx_alive) and gateway/receiver events
  (gateway_events). receiver.log stays the raw evidence; these tables are what the page queries.
* EventHub: an in-memory, numbered log of recent events (observations, health reports, radio
  frames, RX reports, gateway events), pushed to browsers as Server-Sent Events (GET /v1/events).
  Event ids are "<instance>-<n>"; a client that reconnects with Last-Event-ID (or ?since=) gets
  every event it missed, or a `resync` event (gateway restarted, or it fell more than RING events
  behind), after which it reloads from the history endpoints. Nothing is lost either way: every
  event is also in SQLite.
* History queries for the page, downsampled server side so a week or a month stays small.

Standard library only. The static page (ws0/static/) is served without authentication and holds
no data; every /v1/ endpoint, the stream included, needs the bearer token.
"""
import collections
import functools
import ipaddress
import itertools
import json
import math
import secrets
import sqlite3
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from gateway import FAR_FUTURE

from .fields import BY_NAME, FIELDS, LABELS, MEASURED
from .protocol import frame_counter, frame_kind

STATIC = Path(__file__).parent / 'static'
# Fixed table: no path from the request ever reaches the file system.
STATIC_FILES = {'/': ('index.html', 'text/html'), '/dashboard': ('index.html', 'text/html'),
                '/static/app.js': ('app.js', 'text/javascript'), '/static/app.css': ('app.css', 'text/css')}
STATIC_HEADERS = {
    'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
                               "img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
    'Cache-Control': 'no-cache'}

MAX_STREAMS = 8         # one server thread per open stream (ThreadingHTTPServer)
HEARTBEAT_S = 15.0      # comment line on an idle stream: keeps proxies open, detects gone clients
RING = 5000             # events kept for resume (~1 day at one station's rate)
PENDING_RSSI_S = 2.0    # wait this long for the RX's '#rx obs rssi=' line after a frame

TABLES = (
    '''CREATE TABLE IF NOT EXISTS radio_events (id INTEGER PRIMARY KEY AUTOINCREMENT, station TEXT,
        received_at REAL, kind TEXT, counter INTEGER, outcome TEXT, delivered INTEGER, session TEXT,
        sequence INTEGER, length INTEGER, rssi_dbm INTEGER, snr_db INTEGER, detail TEXT)''',
    'CREATE INDEX IF NOT EXISTS radio_time ON radio_events(station,received_at)',
    '''CREATE TABLE IF NOT EXISTS rx_alive (id INTEGER PRIMARY KEY AUTOINCREMENT, station TEXT, received_at REAL,
        uptime_s INTEGER, forwarded INTEGER, dropped INTEGER, acks INTEGER, diag INTEGER, listening INTEGER,
        relistens INTEGER, uart_errors INTEGER, stack_peak INTEGER)''',
    'CREATE INDEX IF NOT EXISTS rx_alive_time ON rx_alive(station,received_at)',
    '''CREATE TABLE IF NOT EXISTS gateway_events (id INTEGER PRIMARY KEY AUTOINCREMENT, station TEXT, at REAL,
        source TEXT, kind TEXT, level TEXT, text TEXT)''',
    'CREATE INDEX IF NOT EXISTS gateway_events_time ON gateway_events(station,at)',
    'CREATE INDEX IF NOT EXISTS diag_received ON diagnostics(station,received_at)',
)
ALIVE_FIELDS = ('uptime_s', 'forwarded', 'dropped', 'acks', 'diag', 'listening', 'relistens', 'uart_errors',
                'stack_peak')
KIND_NAMES = {1: 'obs', 2: 'ack', 3: 'nack', 4: 'diag'}
# RX console lines worth keeping as events (firmware/stage0-node/App/app_rx.c).
RX_EVENTS = (('#boot role=rx', 'rx_boot', 'warn'), ('#relisten', 'relisten', 'warn'),
             ('#rx error', 'rx_error', 'warn'), ('#tx timeout', 'tx_timeout', 'warn'),
             ('#watchdog', 'rx_watchdog', 'warn'), ('#host reject', 'host_reject', 'warn'),
             ('#tx busy', 'tx_busy', 'warn'))


class Throttle:
    """Token bucket per noise class (gateway review GW6). Anyone with a 915 MHz radio can send
    frames that fail authentication, and each one used to add a radio row, an event row and
    receiver.log lines: a sustained flood could fill the disk. Real data (stored observations,
    their ACKs, node health reports) is never throttled; rejected frames, replays and RX drop
    reports are, after a burst. Suppressed lines are counted and reported in one summary."""
    def __init__(self, burst=200, per_s=0.1):
        self.burst, self.per_s = burst, per_s
        self.tokens, self.updated, self.suppressed = {}, {}, {}

    def allow(self, key, now):
        """(allowed, suppressed_since_last_allowed). A refused call counts as suppressed."""
        tokens = min(self.burst, self.tokens.get(key, self.burst) + (now - self.updated.get(key, now)) * self.per_s)
        self.updated[key] = now
        if tokens < 1:
            self.tokens[key] = tokens
            self.suppressed[key] = self.suppressed.get(key, 0) + 1
            return False, 0
        self.tokens[key] = tokens - 1
        return True, self.suppressed.pop(key, 0)


def utc_stamp(t):
    """Whole-second ISO-8601 UTC, as written in logs and receiver reports."""
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(t))


def line_fields(text):
    """'#alive uptime=5 forwarded=2' -> {'uptime': '5', ...}; text without '=' is skipped."""
    return dict(f.split('=', 1) for f in text.split()[1:] if '=' in f)


def as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class EventHub:
    """Numbered recent events for the SSE streams; publish() never blocks on a slow client."""
    def __init__(self, size=RING, max_streams=MAX_STREAMS, heartbeat_s=HEARTBEAT_S):
        self.instance = secrets.token_hex(4)   # changes on every gateway start: old cursors resync
        self.events = collections.deque(maxlen=size)
        self.seq = 0
        self.cond = threading.Condition()
        self.closed = False
        self.max_streams, self.heartbeat_s = max_streams, heartbeat_s
        self.streams = 0

    def publish(self, kind, data):
        text = json.dumps(data, allow_nan=False, separators=(',', ':'), default=str)
        with self.cond:
            self.seq += 1
            self.events.append((self.seq, kind, text))
            self.cond.notify_all()
            return self.seq

    def event_id(self, seq):
        return f'{self.instance}-{seq}'

    def resume_point(self, cursor):
        """Sequence number to stream after, or None if the cursor cannot be resumed exactly."""
        instance, _, number = (cursor or '').strip().rpartition('-')
        if instance != self.instance or not number.isdigit():
            return None
        seq = int(number)
        with self.cond:
            oldest = self.events[0][0] if self.events else self.seq + 1
            if seq > self.seq or seq < oldest - 1:
                return None
        return seq

    def after(self, seq, timeout):
        """Events after seq (waiting up to timeout); None once closed; 'overflow' if seq fell out."""
        with self.cond:
            self.cond.wait_for(lambda: self.closed or self.seq > seq, timeout)
            if self.closed:
                return None
            oldest = self.events[0][0] if self.events else self.seq + 1
            if oldest > seq + 1:
                return 'overflow'
            # Numbers are consecutive, so the events after seq start at a known index.
            return list(itertools.islice(self.events, seq + 1 - oldest, None))

    def acquire(self):
        with self.cond:
            if self.closed or self.streams >= self.max_streams:
                return False
            self.streams += 1
            return True

    def release(self):
        with self.cond:
            self.streams -= 1

    def close(self):
        with self.cond:
            self.closed = True
            self.cond.notify_all()


def best_effort(method):
    """Telemetry never stops the data path: a failed SQLite write (disk full, I/O error, locked)
    is reported on stderr, at most once a minute, and the serve loop carries on. Observations,
    ACKs and the counter mark do not go through here."""

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except sqlite3.Error as exc:
            now = time.time()
            if now - getattr(self, '_last_failure_note', 0) >= 60:
                self._last_failure_note = now
                print(f'#gateway telemetry write failed ({method.__name__}): {type(exc).__name__}: {exc}',
                      file=sys.stderr, flush=True)
            return None
    return wrapper


class Telemetry:
    """Persist and publish what the serve loop sees besides observations (one per Gateway)."""
    def __init__(self, gateway):
        self.gateway, self.store, self.station = gateway, gateway.store, gateway.cfg['station']
        self.hub = gateway.hub
        self.pending = None   # frame waiting for the RX's RSSI/SNR line
        self.throttle = Throttle()
        self.muted = False    # the last frame was throttled: drop its RSSI line too
        with self.store.lock, self.store.db:
            for sql in TABLES:
                self.store.db.execute(sql)

    # -- events published by the Gateway itself ------------------------------------------------
    @best_effort
    def observation(self, record, received_at=None):
        """A newly stored observation, as the history endpoint shows it, plus the new 'latest'."""
        with self.store.lock:
            row = self.store.db.execute(
                'SELECT received_at,effective_at,time_basis,time_uncertainty_s FROM observations '
                'WHERE station=? AND session=? AND sequence=?',
                (record['station'], record['session'], record['sequence'])).fetchone()
        if row is None:
            return
        full = dict(record, received_at=row[0], effective_sampled_at=row[1], time_basis=row[2],
                    time_uncertainty_s=row[3])
        self.hub.publish('observation', {'record': full, 'latest': self.store.latest(self.station)})

    def diagnostic(self, report, received_at=None):
        self.hub.publish('diagnostic', dict(report, received_at=time.time() if received_at is None else received_at))

    # -- serve loop hooks -----------------------------------------------------------------------
    def frame(self, frame, outcome, delivered=None, detail=None, at=None):
        """A frame line from the RX board and what the gateway did with it. The RX prints the
        frame's RSSI/SNR on the next line ('#rx obs'), so the row is written when that arrives."""
        at = time.time() if at is None else at
        self.flush()
        kind = counter = None
        if isinstance(frame, (bytes, bytearray)) and len(frame) >= 8:
            kind = KIND_NAMES.get(frame_kind(frame), 'unknown')
            counter = frame_counter(frame)
        session = sequence = None
        if outcome in ('ack', 'duplicate') and self.gateway.last_ingested:
            session, sequence = self.gateway.last_ingested['session'], self.gateway.last_ingested['sequence']
        self.pending = dict(received_at=at, kind=kind, counter=counter, outcome=outcome,
                            delivered=None if delivered is None else int(bool(delivered)), session=session,
                            sequence=sequence, length=len(frame) if frame is not None else None,
                            detail=None if detail is None else str(detail)[:300])
        if outcome in ('rejected', 'commit_failed'):
            self.event(f'{outcome}: {detail}', source='gateway', kind=outcome, level='warn', at=at)

    def flush(self, rssi=None, snr=None):
        if self.pending is None:
            return
        row, self.pending = dict(self.pending, rssi_dbm=rssi, snr_db=snr), None
        self._radio(row)

    def tick(self, now=None):
        """Write a frame whose RSSI line never came (older RX firmware, lost serial line)."""
        now = time.time() if now is None else now
        if self.pending and now - self.pending['received_at'] > PENDING_RSSI_S:
            self.flush()

    def rx_line(self, text, at=None):
        """A '#' diagnostic line from the RX board."""
        at = time.time() if at is None else at
        if text.startswith('#rx obs'):
            f = line_fields(text)
            if self.pending is None:  # RSSI for a frame line that never reached us intact
                self.pending = dict(received_at=at, kind=None, counter=None, outcome='unparsed', delivered=None,
                                    session=None, sequence=None, length=None, detail=None)
            self.flush(as_int(f.get('rssi')), as_int(f.get('snr')))
        elif text.startswith('#rx drop'):
            self.flush()
            f = line_fields(text)
            self._radio(dict(received_at=at, kind='dropped', counter=None, outcome='dropped_by_rx', delivered=None,
                             session=None, sequence=None, length=as_int(f.get('len')),
                             rssi_dbm=as_int(f.get('rssi')), snr_db=as_int(f.get('snr')), detail=None))
        elif text.startswith('#alive '):
            self.alive(line_fields(text), at)
        else:
            for prefix, kind, level in RX_EVENTS:
                if text.startswith(prefix):
                    self.event(text, source='rx', kind=kind, level=level, at=at)
                    break

    @best_effort
    def alive(self, fields, at):
        values = {'uptime_s': as_int(fields.get('uptime')), **{k: as_int(fields.get(k)) for k in ALIVE_FIELDS[1:]}}
        with self.store.lock, self.store.db:
            cur = self.store.db.execute(
                f'INSERT INTO rx_alive (station,received_at,{",".join(ALIVE_FIELDS)}) '
                f'VALUES (?,?,{",".join("?" * len(ALIVE_FIELDS))})',
                (self.station, at, *(values[k] for k in ALIVE_FIELDS)))
        self.hub.publish('rx', dict(values, id=cur.lastrowid, received_at=at))

    @best_effort
    def event(self, text, source='gateway', kind=None, level=None, at=None):
        """A gateway or receiver event: serial link, host clock, receiver silent, RX boots, rejects."""
        at = time.time() if at is None else at
        text = str(text)[:300]
        if kind is None:
            kind = text.split()[1] if text.startswith('#gateway ') and len(text.split()) > 1 else 'gateway'
        if level is None:
            calm = kind in ('serial-open', 'start', 'stop') or (kind == 'host-clock' and ' ok ' in text + ' ')
            level = 'info' if calm else 'warn'
        with self.store.lock, self.store.db:
            cur = self.store.db.execute('INSERT INTO gateway_events (station,at,source,kind,level,text) '
                                        'VALUES (?,?,?,?,?,?)', (self.station, at, source, kind, level, text))
        self.hub.publish('gateway', {'id': cur.lastrowid, 'at': at, 'source': source, 'kind': kind,
                                     'level': level, 'text': text})

    @best_effort
    def _radio(self, row):
        cols = ('received_at', 'kind', 'counter', 'outcome', 'delivered', 'session', 'sequence', 'length',
                'rssi_dbm', 'snr_db', 'detail')
        with self.store.lock, self.store.db:
            cur = self.store.db.execute(f'INSERT INTO radio_events (station,{",".join(cols)}) '
                                        f'VALUES (?,{",".join("?" * len(cols))})',
                                        (self.station, *(row[c] for c in cols)))
        self.hub.publish('radio', dict(row, id=cur.lastrowid))


# -- HTTP ---------------------------------------------------------------------------------------
def bind_address(cfg):
    """`http_bind` in gateway.json (default 127.0.0.1). Only an IP literal; anything other than
    loopback is an explicit decision and is announced on every start (docs/web-dashboard.md)."""
    host = cfg.get('http_bind', '127.0.0.1')
    address = ipaddress.ip_address(host)   # ValueError for names and junk
    if not address.is_loopback:
        print(f'#gateway warning: HTTP API listening on {host} (http_bind), not loopback only: plain HTTP, '
              'the bearer token crosses the network in clear text', file=sys.stderr, flush=True)
    return str(address)


def serve_static(handler, path):
    """Serve the dashboard's fixed files (no data, no auth). False if path is not one of them."""
    entry = STATIC_FILES.get(path)
    if entry is None:
        return False
    data = (STATIC / entry[0]).read_bytes()
    handler.send_response(200)
    handler.send_header('Content-Type', entry[1] + '; charset=utf-8')
    handler.send_header('Content-Length', str(len(data)))
    for name, value in STATIC_HEADERS.items():
        handler.send_header(name, value)
    handler.end_headers()
    handler.wfile.write(data)
    return True


ROUTES = ('/v1/events', '/v1/history', '/v1/radio', '/v1/receiver/alive', '/v1/diagnostics', '/v1/gateway/events')


def utc_param(query, name, default):
    text = query.get(name, [None])[0]
    if text is None:
        return default
    value = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('UTC filter requires timezone')
    return value.timestamp()


def int_param(query, name, default, low, high):
    value = int(query.get(name, [str(default)])[0])
    if not low <= value <= high:
        raise ValueError(f'{name} must be {low}..{high}')
    return value


def route(handler, gateway, path, query):
    """Authenticated /v1/ dashboard endpoints; the caller has checked the token."""
    if path == '/v1/events':
        cursor = handler.headers.get('Last-Event-ID') or query.get('since', [None])[0]
        stream(handler, gateway.hub, cursor)
        return
    start = utc_param(query, 'from', None)
    end = utc_param(query, 'to', None)
    if path == '/v1/history':
        end = time.time() if end is None else end
        start = end - 86400 if start is None else start
        if not start < end:
            raise ValueError('Invalid time range')
        handler.reply(200, history(gateway, start, end, int_param(query, 'max_points', 1500, 10, 10000)))
        return
    start, end = (0 if start is None else start), (FAR_FUTURE if end is None else end)
    limit = int_param(query, 'limit', 100, 1, 5000)
    offset = int_param(query, 'offset', 0, 0, 2**31)
    order = query.get('order', ['asc'])[0]
    if end < start or order not in ('asc', 'desc'):
        raise ValueError('Invalid time range or order')
    table, column = {'/v1/radio': ('radio_events', 'received_at'), '/v1/receiver/alive': ('rx_alive', 'received_at'),
                     '/v1/diagnostics': ('diagnostics', 'received_at'),
                     '/v1/gateway/events': ('gateway_events', 'at')}[path]
    with gateway.store.reader() as db:
        rows = rows_between(db, gateway.cfg['station'], table, start, end, limit, offset, order)
    handler.reply(200, {'rows': rows, 'offset': offset, 'limit': limit})


# Per table: time column, tie-break order, and the columns a dashboard row carries.
TABLE_ROWS = {
    'radio_events': ('received_at', 'id', ('id', 'received_at', 'kind', 'counter', 'outcome', 'delivered',
                                           'session', 'sequence', 'length', 'rssi_dbm', 'snr_db', 'detail')),
    'rx_alive': ('received_at', 'id', ('id', 'received_at', *ALIVE_FIELDS)),
    'diagnostics': ('received_at', 'session,uptime_s', ('received_at', 'report')),
    'gateway_events': ('at', 'id', ('id', 'at', 'source', 'kind', 'level', 'text')),
}


def rows_between(db, station, table, start, end, limit=100000, offset=0, order='asc'):
    """Rows of one dashboard table in [start, end), as dicts (diagnostics: the decoded report).
    db is a Store.reader() connection: never the ingest connection or its lock."""
    column, tiebreak, names = TABLE_ROWS[table]
    direction = 'DESC' if order == 'desc' else 'ASC'
    cur = db.execute(f'SELECT {",".join(names)} FROM {table} WHERE station=? AND {column}>=? AND {column}<? '
                     f'ORDER BY {column} {direction},{tiebreak} {direction} LIMIT ? OFFSET ?',
                     (station, start, end, limit, offset))
    if table == 'diagnostics':
        return [json.loads(report) | {'received_at': at} for at, report in cur]
    return [dict(zip(names, r, strict=True)) for r in cur]


STREAM_SEND_TIMEOUT_S = 20


def stream(handler, hub, cursor):
    """GET /v1/events: text/event-stream. Frames are `id:`, `event:`, one `data:` JSON line."""
    if not hub.acquire():
        body = b'{"error":"too_many_streams"}'
        handler.send_response(503)
        handler.send_header('Content-Type', 'application/json; charset=utf-8')
        handler.send_header('Content-Length', str(len(body)))
        handler.send_header('Retry-After', '5')
        handler.end_headers()
        handler.wfile.write(body)
        return
    handler.close_connection = True
    try:
        # A client that stops reading would block a write forever and hold one of the stream slots
        # (gateway review GW8). With a send timeout the write fails and the slot is released.
        handler.connection.settimeout(STREAM_SEND_TIMEOUT_S)
        handler.send_response(200)
        handler.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        handler.send_header('Cache-Control', 'no-store')
        handler.send_header('X-Accel-Buffering', 'no')
        handler.end_headers()
        position = hub.resume_point(cursor) if cursor else None
        resumed = position is not None
        if position is None:
            with hub.cond:
                position = hub.seq

        def send(kind, data, seq):
            handler.wfile.write(f'id: {hub.event_id(seq)}\nevent: {kind}\ndata: {data}\n\n'.encode())

        handler.wfile.write(b': ws0 event stream\nretry: 2000\n\n')
        hello = {'instance': hub.instance, 'server_time': time.time(), 'resumed': resumed,
                 'cursor_was_valid': resumed if cursor else None}
        if cursor and not resumed:
            send('resync', json.dumps({'reason': 'cursor not resumable (gateway restarted or too far behind)'}),
                 position)
        send('hello', json.dumps(hello), position)
        while True:
            events = hub.after(position, hub.heartbeat_s)
            if events is None:
                return
            if events == 'overflow':
                with hub.cond:
                    position = hub.seq
                send('resync', json.dumps({'reason': 'client fell behind the event buffer'}), position)
                continue
            if not events:
                handler.wfile.write(b': heartbeat\n\n')
            for seq, kind, data in events:
                send(kind, data, seq)
                position = seq
    except (OSError, ValueError):
        return   # client went away (BrokenPipe, ConnectionReset, closed file)
    finally:
        hub.release()


# -- history ------------------------------------------------------------------------------------
def _bucket_of(span, count, max_points):
    return 0 if count <= max_points else max(60, math.ceil(span / max_points))


def _mean(values):
    good = [v for v in values if v is not None]
    if len(good) < 2:
        return good[0] if good else None   # one reading: its exact value
    return round(sum(good) / len(good), 3)


def _last(values):
    good = [v for v in values if v is not None]
    return good[-1] if good else None


def history(gateway, start, end, max_points=1500):
    """Everything the page charts for [start, end): observations, node health, RX health, radio,
    events. A series longer than max_points is reduced to time buckets (bucket_s > 0); a bucket
    with no valid value stays null, and empty buckets are absent, so gaps remain gaps."""
    with gateway.store.reader() as db:   # one snapshot, and never the ACK path's lock
        return _history(db, gateway.cfg['station'], start, end, max_points)


# Covered by the index obs_effective_order (gateway.py): no sort in a temp B-tree.
HISTORY_SQL = ('SELECT payload,effective_at,time_basis FROM observations WHERE station=? '
               'AND effective_at>=? AND effective_at<? ORDER BY effective_at,session,sequence')


def _history(db, station, start, end, max_points):
    rows = db.execute(HISTORY_SQL, (station, start, end)).fetchall()
    unknown = db.execute('SELECT count(*) FROM observations WHERE station=? AND effective_at IS NULL '
                         'AND received_at>=? AND received_at<?', (station, start, end)).fetchone()[0]
    records = [(json.loads(p), t, b) for p, t, b in rows]
    present = {name for r, _, _ in records for name in MEASURED if name in r}
    names = [f.name for f in FIELDS if f.name in present]
    bucket = _bucket_of(end - start, len(records), max_points)
    obs = {'bucket_s': bucket, 'fields': names, 'units': {n: BY_NAME[n].unit for n in names},
           'labels': {n: LABELS[n] for n in names},
           'unknown_time_count': unknown, 't': [], 'basis': [], 'quality': [], 'session': [],
           'values': {n: [] for n in names}}
    for t, group in _groups(records, lambda r: r[1], start, bucket):
        obs['t'].append(t)
        bases = {b for _, _, b in group}
        obs['basis'].append('reconstructed' if 'reconstructed' in bases else 'synchronized')
        qualities = {r['quality'] for r, _, _ in group}
        obs['quality'].append(qualities.pop() if len(qualities) == 1 else 'partial')
        obs['session'].append(group[-1][0]['session'])
        for n in names:
            column = [r.get(n) for r, _, _ in group]
            if n == 'wind_dir_deg' or BY_NAME[n].counter:
                obs['values'][n].append(_last(column))
            else:
                obs['values'][n].append(_mean(column))

    radio = radio_series(db, station, start, end, max_points)

    alive_rows = rows_between(db, station, 'rx_alive', start, end)
    abucket = _bucket_of(end - start, len(alive_rows), max_points)
    alive = {'bucket_s': abucket, 't': [], **{k: [] for k in ALIVE_FIELDS}}
    for t, group in _groups(alive_rows, lambda r: r['received_at'], start, abucket):
        alive['t'].append(t)
        for k in ALIVE_FIELDS:   # cumulative since RX boot: the bucket's last report
            values = [r[k] for r in group]
            alive[k].append(max((v for v in values if v is not None), default=None) if k == 'stack_peak'
                            else _last(values))

    diags = rows_between(db, station, 'diagnostics', start, end)
    if len(diags) > max_points:   # keep every change of epoch, firmware, energy or link state
        step = math.ceil(len(diags) / max_points)
        keys = ('epoch', 'firmware_build', 'energy_state', 'link')
        diags = [d for i, d in enumerate(diags)
                 if i % step == 0 or i == len(diags) - 1 or any(d[k] != diags[i - 1][k] for k in keys)]
    events = rows_between(db, station, 'gateway_events', start, end, limit=500, order='desc')[::-1]
    return {'from': start, 'to': end, 'server_time': time.time(), 'observations': obs, 'diagnostics': diags,
            'radio': radio, 'receiver': alive, 'events': events}


def radio_series(db, station, start, end, max_points):
    """Radio chart for [start, end). Small ranges: one point per frame. Large ones: buckets
    averaged inside SQLite, so every frame counts however many there are (gateway review GW11:
    the rows were fetched with a 100,000 limit and later frames silently fell off the chart)."""
    radio = {'bucket_s': 0, 't': [], 'rssi_dbm': [], 'snr_db': [], 'rssi_min': [], 'frames': [],
             'kind': [], 'outcome': [], 'counter': []}
    where = 'station=? AND received_at>=? AND received_at<?'
    count = db.execute(f'SELECT COUNT(*) FROM radio_events WHERE {where}', (station, start, end)).fetchone()[0]
    bucket = radio['bucket_s'] = _bucket_of(end - start, count, max_points)
    if not bucket:
        for r in rows_between(db, station, 'radio_events', start, end):
            radio['t'].append(r['received_at'])
            radio['rssi_dbm'].append(r['rssi_dbm'])
            radio['snr_db'].append(r['snr_db'])
            radio['rssi_min'].append(r['rssi_dbm'])
            radio['frames'].append(1)
            radio['kind'].append(r['kind'])
            radio['outcome'].append(r['outcome'])
            radio['counter'].append(r['counter'])
        return radio
    b = 'CAST((received_at-?)/? AS INTEGER)'
    groups = db.execute(
        f'SELECT {b} AS b, COUNT(*), COUNT(rssi_dbm), AVG(rssi_dbm), MIN(rssi_dbm), COUNT(snr_db), AVG(snr_db), '
        f'MIN(snr_db), MIN(kind), MIN(counter) FROM radio_events WHERE {where} GROUP BY b ORDER BY b',
        (start, bucket, station, start, end)).fetchall()
    outcomes = collections.defaultdict(dict)
    for key, outcome, n in db.execute(
            f'SELECT {b} AS b, outcome, COUNT(*) FROM radio_events WHERE {where} GROUP BY b, outcome',
            (start, bucket, station, start, end)):
        outcomes[key][outcome] = n

    def mean(n, avg, only):   # same rule as _mean: one reading keeps its exact value
        return None if n == 0 else only if n == 1 else round(avg, 3)
    for key, frames, n_rssi, avg_rssi, min_rssi, n_snr, avg_snr, min_snr, kind, counter in groups:
        radio['t'].append(start + key * bucket)
        radio['rssi_dbm'].append(mean(n_rssi, avg_rssi, min_rssi))
        radio['snr_db'].append(mean(n_snr, avg_snr, min_snr))
        radio['rssi_min'].append(min_rssi)
        radio['frames'].append(frames)
        single = frames == 1
        radio['kind'].append(kind if single else None)
        radio['outcome'].append(next(iter(outcomes[key])) if single else outcomes[key])
        radio['counter'].append(counter if single else None)
    return radio


def _groups(rows, when, start, bucket):
    """(time, rows) per row (bucket 0) or per non-empty bucket of `bucket` seconds."""
    if not bucket:
        for r in rows:
            yield when(r), [r]
        return
    current, group = None, []
    for r in rows:
        b = start + (when(r) - start) // bucket * bucket
        if b != current and group:
            yield current, group
            group = []
        current = b
        group.append(r)
    if group:
        yield current, group
