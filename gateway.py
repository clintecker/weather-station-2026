"""SQLite observation store. Used by the authenticated gateway and regression tests."""
import json
import math
import re
import sqlite3
import threading
import time


def validate(record):
    """Enforce a closed schema and reject NaN, booleans and impossible readings."""
    required = {'version','station','session','sequence','sampled_at','time_quality',
                'temperature_c','humidity_pct','quality'}
    if not isinstance(record, dict) or set(record) != required:
        raise ValueError('Unexpected record fields')
    if type(record['version']) is not int or record['version'] != 1:
        raise ValueError('Unsupported version')
    for name in ('station','session'):
        if not isinstance(record[name], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', record[name]):
            raise ValueError('Invalid identity')
    if type(record['sequence']) is not int or not 0 <= record['sequence'] < 2**32:
        raise ValueError('Invalid sequence')
    if record['quality'] not in ('valid','sensor_fault'):
        raise ValueError('Invalid quality')
    if record['time_quality'] not in ('synchronized','unknown'):
        raise ValueError('Invalid time quality')
    stamp = record['sampled_at']
    if record['time_quality'] == 'unknown':
        if stamp is not None:
            raise ValueError('Unknown clock must have null time')
    elif type(stamp) not in (int,float) or not math.isfinite(stamp) or not 0 <= stamp < 253402300800:
        raise ValueError('Invalid UTC timestamp')
    for name, low, high in [('temperature_c',-40,125),('humidity_pct',0,100)]:
        value = record[name]
        if record['quality'] == 'sensor_fault':
            if value is not None:
                raise ValueError('Fault readings must be null')
        elif type(value) not in (int,float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError('Invalid measurement')


class Store:
    """Serialize concurrent HTTP/ingestion access; immutable identities survive restart."""
    def __init__(self, path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('''CREATE TABLE IF NOT EXISTS observations (
            station TEXT, session TEXT, sequence INTEGER, sampled_at REAL,
            received_at REAL, payload TEXT, PRIMARY KEY(station,session,sequence))''')
        self.db.execute('CREATE INDEX IF NOT EXISTS obs_time ON observations(station,sampled_at)')
        self.db.commit()

    def ingest(self, record, received_at=None):
        """Return only after commit; exact repeats are harmless, collisions are errors."""
        validate(record)
        payload = json.dumps(record, sort_keys=True, separators=(',',':'), allow_nan=False)
        key = (record['station'],record['session'],record['sequence'])
        with self.lock, self.db:
            old = self.db.execute('SELECT payload FROM observations WHERE station=? AND session=? AND sequence=?',key).fetchone()
            if old:
                if old[0] != payload:
                    raise ValueError('Identity collision')
                return False
            self.db.execute('INSERT INTO observations VALUES (?,?,?,?,?,?)',
                            (*key,record['sampled_at'],time.time() if received_at is None else received_at,payload))
        return True

    def latest(self, station, now=None):
        """Fail closed on bad clocks; old replay traffic cannot reset the age timer."""
        now = time.time() if now is None else now
        with self.lock:
            # The immutable sample identity defines order, even across clock corrections.
            row = self.db.execute('''SELECT payload,received_at FROM observations WHERE station=?
                ORDER BY CAST(session AS INTEGER) DESC,sequence DESC,received_at DESC LIMIT 1''',(station,)).fetchone()
        if row is None:
            return {'available':False,'reason':'no_observation'}
        record = json.loads(row[0])
        age = None if record['sampled_at'] is None else now-record['sampled_at']
        # A future sample at receipt stays quarantined; waiting does not validate its clock.
        future = record['sampled_at'] is not None and record['sampled_at'] > row[1]+5
        available = age is not None and 0 <= age < 180 and not future and record['quality']=='valid'
        reason = ('future_clock_at_receipt' if future else 'unknown_clock' if age is None else
                  'sensor_fault' if record['quality']!='valid' else 'fresh' if available else 'stale_or_clock_step')
        return {'available':available,'reason':reason,'age_seconds':age,'received_at':row[1],
                'observation':record,'units':{'temperature_c':'°C','humidity_pct':'%'}}

    def history(self, station, start=0, end=253402300800, limit=100, offset=0):
        """Stable page ordering; UTC-unknown records remain in DB but outside time queries."""
        with self.lock:
            rows = self.db.execute('''SELECT payload,received_at FROM observations WHERE station=?
                AND sampled_at>=? AND sampled_at<? ORDER BY sampled_at,session,sequence LIMIT ? OFFSET ?''',
                (station,start,end,limit,offset)).fetchall()
        return [json.loads(r[0]) | {'received_at':r[1]} for r in rows]
