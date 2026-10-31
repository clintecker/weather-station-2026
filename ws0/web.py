"""Web dashboard back end: radio/receiver telemetry tables, a live event stream and history.

docs/web-dashboard.md describes the page. Server side, three things live here:

* Telemetry: what the serve loop learns that is not an observation, persisted in the gateway's
  SQLite database (observations.sqlite3): one row per radio frame with the RX board's RSSI/SNR
  (radio_events), the RX board's 60 s #alive reports (rx_alive), gateway/receiver events
  (gateway_events) and every bad reception the RX reports, with the bytes of a CRC failure
  (rx_faults; tools/rx_faults.py). receiver.log stays the raw evidence; these tables are what the
  page queries.
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
from http import HTTPStatus
from pathlib import Path

from gateway import DAY_S, FAR_FUTURE, HOUR_S, MINUTE_S

from .fields import BY_NAME, DIAGNOSTIC_FIELDS, FIELDS, LABELS, MEASURED
from .protocol import HEADER_LEN, KIND_ACK, KIND_DIAG, KIND_NACK, KIND_OBS, frame_counter, frame_kind

STATIC = Path(__file__).parent / 'static'
# Fixed table: no path from the request ever reaches the file system.
STATIC_FILES = {'/': ('index.html', 'text/html'), '/dashboard': ('index.html', 'text/html'),
                '/static/app.js': ('app.js', 'text/javascript'), '/static/app.css': ('app.css', 'text/css')}
STATIC_HEADERS = {
    'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
                               "img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
    'Cache-Control': 'no-cache'}

HEX_PER_BYTE = 2
TEXT_MAX = 300          # characters kept of a detail or event text
WORD_MAX = 32           # characters kept of an identifier in an #alive report
MAX_STREAMS = 8         # one server thread per open stream (ThreadingHTTPServer)
HEARTBEAT_S = 15.0      # comment line on an idle stream: keeps proxies open, detects gone clients
RING = 5000             # events kept for resume (~1 day at one station's rate)
PENDING_RSSI_S = 2.0    # wait this long for the RX's '#rx obs rssi=' line after a frame

TABLES = (
    '''CREATE TABLE IF NOT EXISTS radio_events (id INTEGER PRIMARY KEY AUTOINCREMENT, station TEXT,
        received_at REAL, kind TEXT, counter INTEGER, outcome TEXT, delivered INTEGER, session TEXT,
        sequence INTEGER, length INTEGER, rssi_dbm INTEGER, snr_db INTEGER, detail TEXT, frame_hex TEXT)''',
    'CREATE INDEX IF NOT EXISTS radio_time ON radio_events(station,received_at)',
    '''CREATE TABLE IF NOT EXISTS rx_alive (id INTEGER PRIMARY KEY AUTOINCREMENT, station TEXT, received_at REAL,
        uptime_s INTEGER, forwarded INTEGER, dropped INTEGER, acks INTEGER, diag INTEGER, listening INTEGER,
        relistens INTEGER, uart_errors INTEGER, stack_peak INTEGER, crc_errors INTEGER, hdr_errors INTEGER,
        fault_overruns INTEGER, task_peak_us INTEGER, task_peak TEXT, isr_peak_us INTEGER, isr_peak TEXT, trace_drops INTEGER)''',
    'CREATE INDEX IF NOT EXISTS rx_alive_time ON rx_alive(station,received_at)',
    '''CREATE TABLE IF NOT EXISTS gateway_events (id INTEGER PRIMARY KEY AUTOINCREMENT, station TEXT, at REAL,
        source TEXT, kind TEXT, level TEXT, text TEXT)''',
    'CREATE INDEX IF NOT EXISTS gateway_events_time ON gateway_events(station,at)',
    'CREATE INDEX IF NOT EXISTS diag_received ON diagnostics(station,received_at)',
    # One row per '#rx crc' (header decoded, payload CRC failed: the bytes as received) or '#rx hdr'
    # (header CRC failed: no payload). Throttled like other radio noise.
    '''CREATE TABLE IF NOT EXISTS rx_faults (id INTEGER PRIMARY KEY AUTOINCREMENT, station TEXT, received_at REAL,
        kind TEXT, length INTEGER, rssi_dbm INTEGER, snr_db INTEGER, data TEXT)''',
    'CREATE INDEX IF NOT EXISTS rx_faults_time ON rx_faults(station,received_at)',
)
ALIVE_FIELDS = ('uptime_s', 'forwarded', 'dropped', 'acks', 'diag', 'listening', 'relistens', 'uart_errors',
                'stack_peak', 'crc_errors', 'hdr_errors', 'fault_overruns', 'task_peak_us', 'task_peak', 'isr_peak_us', 'isr_peak',
                'trace_drops')
ALIVE_WORDS = ('task_peak', 'isr_peak')   # identifiers (the task or ISR that set the peak), kept as text
# Peaks since RX boot: a history bucket keeps its highest, with the word of the report it came from.
ALIVE_PEAKS = {'stack_peak': None, 'task_peak_us': 'task_peak', 'isr_peak_us': 'isr_peak'}
KIND_NAMES = {KIND_OBS: 'obs', KIND_ACK: 'ack', KIND_NACK: 'nack', KIND_DIAG: 'diag'}
# radio_events outcomes of authentic frames. Only these rows keep the frame's bytes (frame_hex): a
# corrupted capture in rx_faults is compared with them (tools/rx_faults.py). A rejected frame's
# bytes are anyone's radio traffic and are not stored.
ACCEPTED_OUTCOMES = ('ack', 'duplicate', 'diag', 'nack')
# RX console lines worth keeping as events (firmware/stage0-node/App/app_rx.c).
RX_EVENTS = (('#boot role=rx', 'rx_boot', 'warn'), ('#relisten', 'relisten', 'warn'),
             ('#tx timeout', 'tx_timeout', 'warn'),
             ('#watchdog', 'rx_watchdog', 'warn'), ('#host reject', 'host_reject', 'warn'),
             ('#tx busy', 'tx_busy', 'warn'), ('#rx frame-lost', 'rx_frame_lost', 'warn'))
# Bad receptions ('#rx crc', '#rx hdr'): ambient 915 MHz traffic and noise cause a few an hour, so
# they are stored and counted, not raised one by one. More than this many in the trailing hour is
# abnormal (a jammer, a failing antenna, a node transmitting into a bad link): one warning, and the
# next only after the rate has fallen to half of it.
RX_FAULT_WINDOW_S = HOUR_S
RX_FAULT_WARN_PER_H = 30
# rx_faults rows older than this are deleted (checked hourly by Telemetry.tick): at the noise rate
# limit a flood adds at most ~560 rows an hour, so the table stays bounded.
RX_FAULT_RETENTION_S = 30 * DAY_S
# When the trailing-hour summary changes without a new stored bad reception (old ones leave the
# window, the rate limit drops some), the gateway re-publishes it (SSE 'rx_fault_summary') at most
# this often, so an open page's count stays current without polling.
RX_FAULT_SUMMARY_S = MINUTE_S
# Integer columns: SQLite stores signed 64-bit integers; a larger value from a garbled or hostile
# line would raise OverflowError on insert.
INT64 = 2 ** 63
# What a '#rx crc' / '#rx hdr' line may hold (SX126x: RSSI about -148..0 dBm, SNR -32..+32 dB).
RX_FAULT_RANGES = {'rssi': (-200, 20), 'snr': (-64, 64), 'len': (0, 255)}


class SchemaDrift(RuntimeError):
    """A telemetry table in the database predates this gateway version (greenfield: no migrations)."""


class Throttle:
    """Token bucket per noise class. Anyone with a 915 MHz radio can send
    frames that fail authentication, and each one used to add a radio row, an event row and
    receiver.log lines: a sustained flood could fill the disk. Real data (stored observations,
    their ACKs, node health reports) is never throttled; rejected frames, replays and RX drop
    reports are, after a burst. Suppressed lines are counted and reported in one summary."""
    def __init__(self, burst=200, per_s=0.1):
        self.burst, self.per_s = burst, per_s
        self.tokens, self.updated, self.suppressed = {}, {}, {}
        self.refused = collections.Counter()   # per key, since the gateway started
        # Recent refusals per key, as [second, count] buckets, for refused_since(); pruned to
        # RX_FAULT_WINDOW_S. HTTP threads read them, hence the lock.
        self.recent, self.lock = {}, threading.Lock()

    def allow(self, key, now):
        """(allowed, suppressed_since_last_allowed). A refused call counts as suppressed."""
        tokens = min(self.burst, self.tokens.get(key, self.burst) + (now - self.updated.get(key, now)) * self.per_s)
        self.updated[key] = now
        if tokens < 1:
            self.tokens[key] = tokens
            self.suppressed[key] = self.suppressed.get(key, 0) + 1
            self.refused[key] += 1
            second = int(now)
            with self.lock:
                buckets = self.recent.setdefault(key, collections.deque())
                if buckets and buckets[-1][0] == second:
                    buckets[-1][1] += 1
                else:
                    buckets.append([second, 1])
                while buckets and buckets[0][0] < now - RX_FAULT_WINDOW_S:
                    buckets.popleft()
            return False, 0
        self.tokens[key] = tokens - 1
        return True, self.suppressed.pop(key, 0)

    def refused_since(self, key, since):
        """Refusals of `key` at or after `since` (to the second; at most RX_FAULT_WINDOW_S back)."""
        with self.lock:
            return sum(n for second, n in self.recent.get(key, ()) if second >= int(since))


def utc_stamp(t):
    """Whole-second ISO-8601 UTC, as written in logs and receiver reports."""
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(t))


def line_fields(text):
    """'#alive uptime=5 forwarded=2' -> {'uptime': '5', ...}; text without '=' is skipped."""
    return dict(f.split('=', 1) for f in text.split()[1:] if '=' in f)


def as_int(value, low=-INT64, high=INT64 - 1):
    """An integer field of a console line, or None if it is missing, not an integer or outside
    low..high (by default what an SQLite INTEGER holds)."""
    try:
        number = int(value)
    except (TypeError, ValueError):   # ValueError also for digit strings beyond int's limit
        return None
    return number if low <= number <= high else None


def parse_rx_fault(text):
    """'#rx crc len=<n> rssi= snr= data=<hex>' or '#rx hdr rssi=' -> rx_faults row, None if malformed
    (len 0..255, data exactly len bytes of hex, rssi and snr integers in RX_FAULT_RANGES)."""
    words = text.split()
    if len(words) < 2 or words[0] != '#rx' or words[1] not in ('crc', 'hdr'):
        return None
    f = line_fields(text)
    rssi = as_int(f.get('rssi'), *RX_FAULT_RANGES['rssi'])
    if rssi is None:
        return None
    if words[1] == 'hdr':
        return dict(kind='hdr', length=None, rssi_dbm=rssi, snr_db=None, data=None)
    length, snr = as_int(f.get('len'), *RX_FAULT_RANGES['len']), as_int(f.get('snr'), *RX_FAULT_RANGES['snr'])
    data = f.get('data')
    if length is None or snr is None or data is None or len(data) != HEX_PER_BYTE * length:
        return None
    try:
        data = bytes.fromhex(data).hex()   # normalized lowercase; ValueError for anything but hex digits
    except ValueError:
        return None
    return dict(kind='crc', length=length, rssi_dbm=rssi, snr_db=snr, data=data)


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


TELEMETRY_TABLES = ('radio_events', 'rx_alive', 'gateway_events', 'rx_faults')


def expected_columns():
    """{table: [column, ...]} of this version's telemetry tables, from TABLES itself."""
    db = sqlite3.connect(':memory:')
    try:
        for sql in TABLES:
            if sql.startswith('CREATE TABLE'):
                db.execute(sql)
        return {t: [row[1] for row in db.execute(f'PRAGMA table_info({t})')] for t in TELEMETRY_TABLES}
    finally:
        db.close()


def check_schema(db, path, tables=TELEMETRY_TABLES):
    """Raise SchemaDrift, naming each table and the remedy, if a telemetry table's columns are not
    this version's. The tables are created with IF NOT EXISTS and never migrated (greenfield), so a
    table from an older gateway would otherwise fail every insert, silently (best_effort)."""
    expected = expected_columns()
    stale, details = [], []
    for table in tables:
        have = [row[1] for row in db.execute(f'PRAGMA table_info({table})')]
        if have == expected[table]:
            continue
        stale.append(table)
        if not have:
            details.append(f'{table}: missing (not a gateway database, or one older than this version)')
            continue
        missing = [c for c in expected[table] if c not in have]
        extra = [c for c in have if c not in expected[table]]
        parts = [f'lacks {", ".join(missing)}'] if missing else []
        parts += [f'has unknown {", ".join(extra)}'] if extra else []
        details.append(f'{table}: {"; ".join(parts) or "columns in a different order"}')
    if stale:
        names = ', '.join(stale)
        raise SchemaDrift(
            f'{path}: table {names} predates this gateway version ({"; ".join(details)}). There are no '
            f'migrations: stop the gateway, rename or drop table {names} (for example sqlite3 {path} '
            f'"ALTER TABLE {stale[0]} RENAME TO {stale[0]}_old") and start it again; it creates the '
            'table afresh.')


def best_effort(method):
    """Telemetry never stops the data path: a failed SQLite write (disk full, I/O error, locked)
    is reported on stderr, at most once a minute, and the serve loop carries on. Observations,
    ACKs and the counter mark do not go through here."""

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except (sqlite3.Error, OverflowError) as exc:   # OverflowError: an integer SQLite cannot hold
            now = time.time()
            if now - getattr(self, '_last_failure_note', 0) >= MINUTE_S:
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
        # Bad receptions of the trailing hour (time, kind), for the count the page shows and the
        # rate warning; HTTP threads read it, hence the lock. hour: the clock hour being tallied
        # for its info summary event. faults is reloaded from rx_faults at start, but fault_alarm
        # and hour_counts are in memory only: after a restart a high rate warns again, and the
        # hour in progress is summarized from the faults seen since the start.
        self.faults, self.faults_lock, self.fault_alarm = collections.deque(), threading.Lock(), False
        self.hour, self.hour_counts = None, collections.Counter()
        self.summary_at, self.summary_sent = 0.0, None   # last summary published (RX_FAULT_SUMMARY_S)
        self.pruned_at = 0.0                             # last rx_faults retention pass
        with self.store.lock, self.store.db:
            for sql in TABLES:
                self.store.db.execute(sql)
            check_schema(self.store.db, self.store.path)
            self.faults.extend(self.store.db.execute(
                'SELECT received_at,kind FROM rx_faults WHERE station=? AND received_at>=? ORDER BY received_at',
                (self.station, time.time() - RX_FAULT_WINDOW_S)))
        self.summary_sent = self.fault_summary()

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
        if isinstance(frame, (bytes, bytearray)) and len(frame) >= HEADER_LEN:
            kind = KIND_NAMES.get(frame_kind(frame), 'unknown')
            counter = frame_counter(frame)
        session = sequence = None
        if outcome in ('ack', 'duplicate') and self.gateway.last_ingested:
            session, sequence = self.gateway.last_ingested['session'], self.gateway.last_ingested['sequence']
        self.pending = dict(received_at=at, kind=kind, counter=counter, outcome=outcome,
                            delivered=None if delivered is None else int(bool(delivered)), session=session,
                            sequence=sequence, length=len(frame) if frame is not None else None,
                            detail=None if detail is None else str(detail)[:TEXT_MAX],
                            frame_hex=frame.hex() if isinstance(frame, (bytes, bytearray)) and
                            outcome in ACCEPTED_OUTCOMES else None)
        if outcome in ('rejected', 'commit_failed'):
            self.event(f'{outcome}: {detail}', source='gateway', kind=outcome, level='warn', at=at)

    def flush(self, rssi=None, snr=None):
        if self.pending is None:
            return
        row, self.pending = dict(self.pending, rssi_dbm=rssi, snr_db=snr), None
        self._radio(row)

    def tick(self, now=None):
        """Called continually by the serve loop (with or without a serial link). Write a frame whose
        RSSI line never came (older RX firmware, lost serial line); close the hour of bad receptions
        once it is over; re-publish the trailing-hour summary when it changed without a new stored
        bad reception (old ones left the window, or the rate limit dropped some);
        delete bad receptions past RX_FAULT_RETENTION_S once an hour."""
        now = time.time() if now is None else now
        if self.pending and now - self.pending['received_at'] > PENDING_RSSI_S:
            self.flush()
        if self.hour is not None and now // HOUR_S > self.hour:
            self._close_hour()
        if now - self.summary_at >= RX_FAULT_SUMMARY_S:
            self.summary_at = now
            summary = self.fault_summary(now)
            if any(summary[k] != self.summary_sent[k] for k in ('crc', 'hdr', 'throttled')):
                self.summary_sent = summary
                self.hub.publish('rx_fault_summary', {'summary': summary})
        if now - self.pruned_at >= HOUR_S:
            self.pruned_at = now
            self._prune_faults(now)

    def rx_line(self, text, at=None):
        """A '#' diagnostic line from the RX board."""
        at = time.time() if at is None else at
        if text.startswith('#rx obs'):
            f = line_fields(text)
            if self.pending is None:  # RSSI for a frame line that never reached us intact
                self.pending = dict(received_at=at, kind=None, counter=None, outcome='unparsed', delivered=None,
                                    session=None, sequence=None, length=None, detail=None, frame_hex=None)
            self.flush(as_int(f.get('rssi')), as_int(f.get('snr')))
        elif text.startswith('#rx drop'):
            self.flush()
            f = line_fields(text)
            self._radio(dict(received_at=at, kind='dropped', counter=None, outcome='dropped_by_rx', delivered=None,
                             session=None, sequence=None, length=as_int(f.get('len')),
                             rssi_dbm=as_int(f.get('rssi')), snr_db=as_int(f.get('snr')), detail=None,
                             frame_hex=None))
        elif text.startswith(('#rx crc', '#rx hdr')):
            self.flush()
            row = parse_rx_fault(text)
            if row is None:   # firmware and gateway disagree on the format, or a garbled serial line
                self.event(text, source='rx', kind='rx_fault_malformed', level='warn', at=at)
            else:
                self.rx_fault(row, at)
        elif text.startswith('#alive '):
            self.alive(line_fields(text), at)
        else:
            for prefix, kind, level in RX_EVENTS:
                if text.startswith(prefix):
                    self.event(text, source='rx', kind=kind, level=level, at=at)
                    break

    # -- bad receptions -------------------------------------------------------------------------
    def rx_fault(self, row, at):
        """Store one bad reception and count it; warn only when the rate is abnormal. Counted only
        once stored, so the page's count and the rows tools/rx_faults.py lists agree."""
        fault_id = self._store_fault(row, at)
        if fault_id is None:   # not stored (best_effort reported why)
            return
        if self.hour is not None and at // HOUR_S != self.hour:
            self._close_hour()
        self.hour = at // HOUR_S
        self.hour_counts[row['kind']] += 1
        with self.faults_lock:
            self.faults.append((at, row['kind']))
        summary = self.summary_sent = self.fault_summary(at)
        self.hub.publish('rx_fault', dict(row, id=fault_id, received_at=at, summary=summary))
        total = summary['crc'] + summary['hdr']
        if not self.fault_alarm and total > RX_FAULT_WARN_PER_H:
            self.fault_alarm = True
            self.event(f'#gateway rx-faults {total} bad receptions in the last hour ({summary["crc"]} CRC, '
                       f'{summary["hdr"]} header; normally a few): interference, antenna or a weak link? '
                       'See tools/rx_faults.py', kind='rx-fault-rate', level='warn', at=at)
        elif self.fault_alarm and total <= RX_FAULT_WARN_PER_H // 2:
            self.fault_alarm = False

    def fault_summary(self, now=None):
        """Bad receptions in the trailing hour by kind, and how many more the rate limit dropped
        (throttled) in the same window."""
        now = time.time() if now is None else now
        with self.faults_lock:
            while self.faults and self.faults[0][0] < now - RX_FAULT_WINDOW_S:
                self.faults.popleft()
            counts = collections.Counter(kind for _, kind in self.faults)
            last = self.faults[-1][0] if self.faults else None
        return {'window_s': RX_FAULT_WINDOW_S, 'crc': counts['crc'], 'hdr': counts['hdr'], 'last_at': last,
                'warn_per_hour': RX_FAULT_WARN_PER_H,
                'throttled': self.throttle.refused_since('rx_fault', now - RX_FAULT_WINDOW_S)}

    def _close_hour(self):
        """One info event per clock hour that had bad receptions, instead of a warning for each."""
        counts, start = self.hour_counts, self.hour * HOUR_S
        self.hour, self.hour_counts = None, collections.Counter()
        if counts:
            self.event(f'bad receptions {utc_stamp(start)} + 1 h: {counts["crc"]} CRC, {counts["hdr"]} header',
                       source='rx', kind='rx_faults', level='info', at=start + HOUR_S)

    @best_effort
    def _store_fault(self, row, at):
        """The new row's id; None (from best_effort) if the insert failed."""
        cols = ('kind', 'length', 'rssi_dbm', 'snr_db', 'data')
        with self.store.lock, self.store.db:
            cur = self.store.db.execute(f'INSERT INTO rx_faults (station,received_at,{",".join(cols)}) '
                                        f'VALUES (?,?,{",".join("?" * len(cols))})',
                                        (self.station, at, *(row[c] for c in cols)))
        return cur.lastrowid

    @best_effort
    def _prune_faults(self, now):
        with self.store.lock, self.store.db:
            self.store.db.execute('DELETE FROM rx_faults WHERE received_at<?', (now - RX_FAULT_RETENTION_S,))

    @best_effort
    def alive(self, fields, at):
        """An '#alive' report: numbers as integers, the peak words as short text. A field this
        gateway does not know is ignored (it stays in receiver.log)."""
        def value(k):
            text = fields.get('uptime' if k == 'uptime_s' else k)
            return (None if text is None else text[:WORD_MAX]) if k in ALIVE_WORDS else as_int(text)
        values = {k: value(k) for k in ALIVE_FIELDS}
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
        text = str(text)[:TEXT_MAX]
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
                'rssi_dbm', 'snr_db', 'detail', 'frame_hex')
        with self.store.lock, self.store.db:
            cur = self.store.db.execute(f'INSERT INTO radio_events (station,{",".join(cols)}) '
                                        f'VALUES (?,{",".join("?" * len(cols))})',
                                        (self.station, *(row[c] for c in cols)))
        self.hub.publish('radio', {**{k: v for k, v in row.items() if k != 'frame_hex'}, 'id': cur.lastrowid})


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
    handler.send_response(HTTPStatus.OK)
    handler.send_header('Content-Type', entry[1] + '; charset=utf-8')
    handler.send_header('Content-Length', str(len(data)))
    for name, value in STATIC_HEADERS.items():
        handler.send_header(name, value)
    handler.end_headers()
    handler.wfile.write(data)
    return True


ROUTES = ('/v1/events', '/v1/history', '/v1/radio', '/v1/receiver/alive', '/v1/diagnostics', '/v1/gateway/events',
          '/v1/radio/faults')


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
        start = end - DAY_S if start is None else start
        if not start < end:
            raise ValueError('Invalid time range')
        handler.reply(HTTPStatus.OK, history(gateway, start, end, int_param(query, 'max_points', 1500, 10, 10000)))
        return
    start, end = (0 if start is None else start), (FAR_FUTURE if end is None else end)
    limit = int_param(query, 'limit', 100, 1, 5000)
    offset = int_param(query, 'offset', 0, 0, 2**31)
    order = query.get('order', ['asc'])[0]
    if end < start or order not in ('asc', 'desc'):
        raise ValueError('Invalid time range or order')
    table = {'/v1/radio': 'radio_events', '/v1/receiver/alive': 'rx_alive', '/v1/diagnostics': 'diagnostics',
             '/v1/gateway/events': 'gateway_events', '/v1/radio/faults': 'rx_faults'}[path]
    with gateway.store.reader() as db:
        rows = rows_between(db, gateway.cfg['station'], table, start, end, limit, offset, order)
    body = {'rows': rows, 'offset': offset, 'limit': limit}
    if table == 'rx_faults':   # plus the trailing-hour count and what the throttle dropped
        body['summary'] = gateway.telemetry.fault_summary()
    handler.reply(HTTPStatus.OK, body)


# Per table: time column, tie-break order, and the columns a dashboard row carries.
TABLE_ROWS = {
    'radio_events': ('received_at', 'id', ('id', 'received_at', 'kind', 'counter', 'outcome', 'delivered',
                                           'session', 'sequence', 'length', 'rssi_dbm', 'snr_db', 'detail')),
    'rx_alive': ('received_at', 'id', ('id', 'received_at', *ALIVE_FIELDS)),
    'diagnostics': ('received_at', 'session,uptime_s', ('received_at', 'report')),
    'gateway_events': ('at', 'id', ('id', 'at', 'source', 'kind', 'level', 'text')),
    'rx_faults': ('received_at', 'id', ('id', 'received_at', 'kind', 'length', 'rssi_dbm', 'snr_db', 'data')),
}


def iter_rows(db, station, table, start, end, limit=-1, offset=0, order='asc'):
    """Rows of one dashboard table in [start, end), as dicts (diagnostics: the decoded report),
    streamed from the cursor. limit -1: all of them (history never truncates a range).
    db is a Store.reader() connection: never the ingest connection or its lock."""
    column, tiebreak, names = TABLE_ROWS[table]
    direction = 'DESC' if order == 'desc' else 'ASC'
    cur = db.execute(f'SELECT {",".join(names)} FROM {table} WHERE station=? AND {column}>=? AND {column}<? '
                     f'ORDER BY {column} {direction},{tiebreak} {direction} LIMIT ? OFFSET ?',
                     (station, start, end, limit, offset))
    if table == 'diagnostics':
        return (json.loads(report) | {'received_at': at} for at, report in cur)
    return (dict(zip(names, r, strict=True)) for r in cur)


def rows_between(*args, **kwargs):
    return list(iter_rows(*args, **kwargs))


def count_between(db, station, table, start, end):
    column = TABLE_ROWS[table][0]
    return db.execute(f'SELECT COUNT(*) FROM {table} WHERE station=? AND {column}>=? AND {column}<?',
                      (station, start, end)).fetchone()[0]


STREAM_SEND_TIMEOUT_S = 20


def stream(handler, hub, cursor):
    """GET /v1/events: text/event-stream. Frames are `id:`, `event:`, one `data:` JSON line."""
    if not hub.acquire():
        body = b'{"error":"too_many_streams"}'
        handler.send_response(HTTPStatus.SERVICE_UNAVAILABLE)
        handler.send_header('Content-Type', 'application/json; charset=utf-8')
        handler.send_header('Content-Length', str(len(body)))
        handler.send_header('Retry-After', '5')
        handler.end_headers()
        handler.wfile.write(body)
        return
    handler.close_connection = True
    try:
        # A client that stops reading would block a write forever and hold one of the stream slots.
        # With a send timeout the write fails and the slot is released.
        handler.connection.settimeout(STREAM_SEND_TIMEOUT_S)
        handler.send_response(HTTPStatus.OK)
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
    return 0 if count <= max_points else max(MINUTE_S, math.ceil(span / max_points))


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


# Ordered by the index obs_effective_order (gateway.py): no sort in a temp B-tree.
HISTORY_SQL = ('SELECT payload,effective_at,time_basis FROM observations WHERE station=? '
               'AND effective_at>=? AND effective_at<? ORDER BY effective_at,session,sequence')


def _history(db, station, start, end, max_points):
    obs = observation_series(db, station, start, end, max_points)
    radio = radio_series(db, station, start, end, max_points)
    alive = receiver_series(db, station, start, end, max_points)
    diags = diagnostic_series(db, station, start, end, max_points)
    events = rows_between(db, station, 'gateway_events', start, end, limit=500, order='desc')[::-1]
    return {'from': start, 'to': end, 'server_time': time.time(), 'observations': obs, 'diagnostics': diags,
            'radio': radio, 'receiver': alive, 'events': events}


def _summarize(name, column):
    """One bucket's value of one field: direction and counters keep their last valid value."""
    return _last(column) if name == 'wind_dir_deg' or BY_NAME[name].counter else _mean(column)


def observation_series(db, station, start, end, max_points):
    rows = db.execute(HISTORY_SQL, (station, start, end)).fetchall()
    unknown = db.execute('SELECT count(*) FROM observations WHERE station=? AND effective_at IS NULL '
                         'AND received_at>=? AND received_at<?', (station, start, end)).fetchone()[0]
    records = [(json.loads(p), t, b) for p, t, b in rows]
    present = {name for r, _, _ in records for name in MEASURED if name in r}
    names = [f.name for f in FIELDS if f.name in present]
    bucket = _bucket_of(end - start, len(records), max_points)
    # 'diagnostic': every catalog field that describes the station, not the weather (fields.py
    # DIAGNOSTIC_FIELDS), present or not, with its label: the page splits its tiles and charts
    # with it and names a rail that this build does not measure.
    diagnostic = [f.name for f in FIELDS if f.name in DIAGNOSTIC_FIELDS]
    obs = {'bucket_s': bucket, 'fields': names, 'units': {n: BY_NAME[n].unit for n in names},
           'labels': {n: LABELS[n] for n in (*names, *diagnostic)}, 'diagnostic': diagnostic,
           'unknown_time_count': unknown, 't': [], 'basis': [], 'quality': [], 'session': [],
           'values': {n: [] for n in names}}
    for t, group in _groups(records, lambda r: r[1], start, bucket):
        _add_observation_point(obs, t, group)
    return obs


def _add_observation_point(obs, t, group):
    """One point per row or bucket: a reconstructed time anywhere marks the point reconstructed,
    mixed qualities make it partial, the session is the last row's."""
    obs['t'].append(t)
    bases = {b for _, _, b in group}
    obs['basis'].append('reconstructed' if 'reconstructed' in bases else 'synchronized')
    qualities = {r['quality'] for r, _, _ in group}
    obs['quality'].append(qualities.pop() if len(qualities) == 1 else 'partial')
    obs['session'].append(group[-1][0]['session'])
    for n in obs['fields']:
        obs['values'][n].append(_summarize(n, [r.get(n) for r, _, _ in group]))


def receiver_series(db, station, start, end, max_points):
    """RX health. A year of 60 s reports is ~525,000 rows: counted first, then streamed through
    the buckets. Every field is cumulative since RX boot: the bucket's last report, except the
    peaks (ALIVE_PEAKS), the bucket's highest with the word of that report."""
    bucket = _bucket_of(end - start, count_between(db, station, 'rx_alive', start, end), max_points)
    alive = {'bucket_s': bucket, 't': [], **{k: [] for k in ALIVE_FIELDS}}
    for t, group in _groups(iter_rows(db, station, 'rx_alive', start, end), lambda r: r['received_at'],
                            start, bucket):
        alive['t'].append(t)
        for k in ALIVE_FIELDS:
            if k in ALIVE_PEAKS:
                top = max((r for r in group if r[k] is not None), key=lambda r: r[k], default=None)
                alive[k].append(None if top is None else top[k])
                if ALIVE_PEAKS[k]:
                    alive[ALIVE_PEAKS[k]].append(None if top is None else top[ALIVE_PEAKS[k]])
            elif k not in ALIVE_PEAKS.values():
                alive[k].append(_last([r[k] for r in group]))
    return alive


# Health-report keys whose every change survives thinning: the state bands and boot markers of the
# page (power telemetry design section 10.2; the charger status, stage and active-input bands are
# drawCharger in static/app.js). A report from before a key existed lacks it (None).
DIAGNOSTIC_STATE = ('epoch', 'firmware_build', 'energy_state', 'link', 'reset_cause', 'charger_charging',
                    'charger_input_power_ok', 'charger_fault', 'charger_stage', 'charger_active_input')


def diagnostic_series(db, station, start, end, max_points):
    """Node health reports, thinned past max_points; every change of a DIAGNOSTIC_STATE key (epoch,
    firmware, energy, link, reset cause, charger state) is kept, as are the first and last report."""
    diags = rows_between(db, station, 'diagnostics', start, end)
    if len(diags) <= max_points:
        return diags
    step = math.ceil(len(diags) / max_points)
    return [d for i, d in enumerate(diags)
            if i % step == 0 or i == len(diags) - 1
            or any(d.get(k) != diags[i - 1].get(k) for k in DIAGNOSTIC_STATE)]


def radio_series(db, station, start, end, max_points):
    """Radio chart for [start, end). Small ranges: one point per frame. Large ones: buckets
    averaged inside SQLite, so every frame counts however many there are (a row limit would
    silently drop the later frames off the chart)."""
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
