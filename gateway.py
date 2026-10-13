"""SQLite observation store. Used by the authenticated gateway and regression tests."""
import json
import math
import re
import sqlite3
import threading
import time

# Reconstructed time (draft 4): an unsynchronized sample gets UTC from the nearest synchronized
# sample of the same boot epoch: utc = ref_utc + (uptime - ref_uptime). Error bound: 1 s
# quantization on each of the two whole-second fields, plus crystal drift. The 32.768 kHz
# tuning-fork crystal is ~20 ppm at room temperature but drifts quadratically with
# temperature (~120 ppm at -35 degC), so the bound uses 150 ppm.
DRIFT_PPM = 150
QUANTIZATION_S = 2
# Time with a larger error bound is never presented as a current measurement.
CURRENT_MAX_UNCERTAINTY_S = 10


def validate(record):
    """Enforce a closed schema and reject NaN, booleans and impossible readings."""
    required = {'version','station','session','sequence','sampled_at','time_quality',
                'temperature_c','humidity_pct','quality'}
    if not isinstance(record, dict) or type(record.get('version')) is not int:
        raise ValueError('Unsupported version')
    if record['version'] == 2:  # protocol draft 4 adds seconds since boot
        required = required | {'uptime_s'}
    elif record['version'] != 1:
        raise ValueError('Unsupported version')
    if set(record) != required:
        raise ValueError('Unexpected record fields')
    if record['version'] == 2 and (type(record['uptime_s']) is not int or not 0 <= record['uptime_s'] < 2**32):
        raise ValueError('Invalid uptime')
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
        # Derived time columns (draft 4). The JSON payload stays immutable and remains the
        # deduplication authority; these columns are recomputed when references arrive.
        columns = {row[1] for row in self.db.execute('PRAGMA table_info(observations)')}
        for name, kind in (('uptime_s','INTEGER'),('effective_at','REAL'),('time_basis','TEXT'),
                           ('time_uncertainty_s','REAL')):
            if name not in columns:
                self.db.execute(f'ALTER TABLE observations ADD COLUMN {name} {kind}')
        self.db.execute("UPDATE observations SET effective_at=sampled_at, "
                        "time_basis=CASE WHEN sampled_at IS NULL THEN 'unknown' ELSE 'synchronized' END, "
                        "time_uncertainty_s=CASE WHEN sampled_at IS NULL THEN NULL ELSE 0 END "
                        "WHERE time_basis IS NULL")
        self.db.execute('CREATE INDEX IF NOT EXISTS obs_effective ON observations(station,effective_at)')
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
            received = time.time() if received_at is None else received_at
            synced = record['sampled_at'] is not None
            self.db.execute('INSERT INTO observations (station,session,sequence,sampled_at,received_at,payload,'
                            'uptime_s,effective_at,time_basis,time_uncertainty_s) VALUES (?,?,?,?,?,?,?,?,?,?)',
                            (*key,record['sampled_at'],received,payload,record.get('uptime_s'),record['sampled_at'],
                             'synchronized' if synced else 'unknown',0 if synced else None))
            self.reconstruct(record['station'],record['session'])
        return True

    def reconstruct(self, station, session):
        """Give unsynchronized samples of one boot epoch a UTC time from the nearest trusted
        synchronized sample of the same epoch (same monotonic uptime counter). A reference
        whose clock was ahead of its own receipt (quarantined) is never used."""
        refs = self.db.execute('SELECT uptime_s,sampled_at FROM observations WHERE station=? AND session=? '
                               "AND time_basis='synchronized' AND uptime_s IS NOT NULL AND sampled_at<=received_at+5",
                               (station,session)).fetchall()
        if not refs:
            return
        targets = self.db.execute('SELECT sequence,uptime_s FROM observations WHERE station=? AND session=? '
                                  "AND time_basis IN ('unknown','reconstructed') AND uptime_s IS NOT NULL",
                                  (station,session)).fetchall()
        for sequence, uptime in targets:
            ref_uptime, ref_utc = min(refs, key=lambda r: abs(r[0]-uptime))
            span = abs(uptime-ref_uptime)
            self.db.execute("UPDATE observations SET effective_at=?,time_basis='reconstructed',time_uncertainty_s=? "
                            'WHERE station=? AND session=? AND sequence=?',
                            (ref_utc+(uptime-ref_uptime),QUANTIZATION_S+span*DRIFT_PPM/1e6,station,session,sequence))

    def latest(self, station, now=None):
        """Fail closed on bad clocks; old replay traffic cannot reset the age timer."""
        now = time.time() if now is None else now
        with self.lock:
            # The immutable sample identity defines order, even across clock corrections.
            row = self.db.execute('''SELECT payload,received_at,effective_at,time_basis,time_uncertainty_s
                FROM observations WHERE station=?
                ORDER BY CAST(session AS INTEGER) DESC,sequence DESC,received_at DESC LIMIT 1''',(station,)).fetchone()
        if row is None:
            return {'available':False,'reason':'no_observation'}
        record = json.loads(row[0])
        effective, basis, uncertainty = row[2], row[3], row[4]
        age = None if effective is None else now-effective
        # A future sample at receipt stays quarantined; waiting does not validate its clock.
        future = effective is not None and effective > row[1]+5
        vague = uncertainty is not None and uncertainty > CURRENT_MAX_UNCERTAINTY_S
        available = (age is not None and 0 <= age < 180 and not future and not vague
                     and record['quality']=='valid')
        reason = ('future_clock_at_receipt' if future else 'unknown_clock' if age is None else
                  'time_uncertain' if vague else
                  'sensor_fault' if record['quality']!='valid' else 'fresh' if available else 'stale_or_clock_step')
        return {'available':available,'reason':reason,'age_seconds':age,'received_at':row[1],
                'observation':record,'effective_sampled_at':effective,'time_basis':basis,
                'time_uncertainty_s':uncertainty,'units':{'temperature_c':'°C','humidity_pct':'%'}}

    def history(self, station, start=0, end=253402300800, limit=100, offset=0):
        """Stable page ordering; UTC-unknown records remain in DB but outside time queries."""
        with self.lock:
            rows = self.db.execute('''SELECT payload,received_at,effective_at,time_basis,time_uncertainty_s
                FROM observations WHERE station=? AND effective_at>=? AND effective_at<?
                ORDER BY effective_at,session,sequence LIMIT ? OFFSET ?''',
                (station,start,end,limit,offset)).fetchall()
        return [json.loads(r[0]) | {'received_at':r[1],'effective_sampled_at':r[2],'time_basis':r[3],
                                    'time_uncertainty_s':r[4]} for r in rows]
