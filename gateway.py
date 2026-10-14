"""SQLite observation store. Used by the authenticated gateway and regression tests."""
import json
import os
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


def full_flush(db):
    """Write-ahead log, and each commit reaches stable storage (gap G4). macOS fsync() does not
    flush the drive cache; F_FULLFSYNC does. Measured on the bench Mac: commit 0.06 ms without
    (not durable), 5.3 ms median / 16 ms max with. WAL: one flush per commit instead of the
    rollback journal's several (a nonce commit 14 ms -> 5 ms; gateway efficiency review). The
    WAL file is part of the database: copy all of name, name-wal and name-shm or none (R7).
    Harmless no-ops on Linux. Simulations and unit tests may opt out with
    WS0_UNSAFE_FAST_FSYNC=1; they never claim power-loss durability."""
    fast = os.environ.get('WS0_UNSAFE_FAST_FSYNC') == '1'
    db.execute('PRAGMA journal_mode=WAL')
    db.execute(f"PRAGMA synchronous={'OFF' if fast else 'FULL'}")
    db.execute(f"PRAGMA fullfsync={'OFF' if fast else 'ON'}")
    db.execute(f"PRAGMA checkpoint_fullfsync={'OFF' if fast else 'ON'}")


BASE_KEYS = frozenset({'version','station','session','sequence','sampled_at','uptime_s','time_quality',
                       'energy_state','calibration_revision','quality'})


def validate(record):
    """Closed schema for protocol draft 5 (docs/protocol-draft5-design.md 5.7): identity and time as
    before, catalog fields with exact, representable values, and a quality that matches them."""
    from ws0 import fields as F
    if not isinstance(record, dict) or type(record.get('version')) is not int or record['version'] != 5:
        raise ValueError('Unsupported version')
    if not BASE_KEYS <= set(record):
        raise ValueError('Missing record fields')
    extra = set(record) - BASE_KEYS
    if extra - set(F.BY_NAME) - {'wind_calm'}:
        raise ValueError('Unexpected record fields')
    if ('wind_calm' in record) != ('wind_dir_deg' in record):
        raise ValueError('wind_calm goes with wind_dir_deg')
    for name in ('station','session'):
        if not isinstance(record[name], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', record[name]):
            raise ValueError('Invalid identity')
    for name, top in (('sequence',2**32),('uptime_s',2**32),('calibration_revision',256)):
        if type(record[name]) is not int or not 0 <= record[name] < top:
            raise ValueError(f'Invalid {name}')
    if record['energy_state'] not in F.ENERGY:
        raise ValueError('Invalid energy state')
    if record['time_quality'] not in ('synchronized','unknown'):
        raise ValueError('Invalid time quality')
    stamp = record['sampled_at']
    if record['time_quality'] == 'unknown':
        if stamp is not None:
            raise ValueError('Unknown clock must have null time')
    elif type(stamp) not in (int,float) or not math.isfinite(stamp) or not 0 < stamp < 2**32:
        raise ValueError('Invalid UTC timestamp')
    for name in extra & set(F.MEASURED):
        value, f = record[name], F.BY_NAME[name]
        if value is None:
            continue
        if type(value) not in (int,float) or not math.isfinite(value) or f.code(value) == f.invalid \
                or f.value(f.code(value)) != value:
            raise ValueError(f'{name}: not an exact catalog value')
    if 'wind_calm' in record:
        if type(record['wind_calm']) is not bool or (record['wind_calm'] and record['wind_dir_deg'] is not None):
            raise ValueError('Invalid wind_calm')
    if record.get('wind_speed_ms', 0) is None and (record.get('wind_dir_deg') is not None or record.get('wind_calm')):
        raise ValueError('Wind direction without a valid speed')
    if 'qualifiers' in record:
        q = record['qualifiers']
        if not isinstance(q, dict) or any(n not in {g.name for g in F.FIELDS[:16]} or v not in F.QUALIFIER[1:]
                                          for n, v in q.items()):
            raise ValueError('Invalid qualifiers')
    if record['quality'] != F.quality(record):
        raise ValueError('Quality does not match the field values')


class Store:
    """Serialize concurrent HTTP/ingestion access; immutable identities survive restart."""
    def __init__(self, path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        full_flush(self.db)
        # The JSON payload is immutable and the deduplication authority; the derived time columns
        # are recomputed when references arrive (reconstruct).
        self.db.execute('''CREATE TABLE IF NOT EXISTS observations (
            station TEXT, session TEXT, sequence INTEGER, sampled_at REAL, received_at REAL, payload TEXT,
            uptime_s INTEGER, effective_at REAL, time_basis TEXT, time_uncertainty_s REAL,
            PRIMARY KEY(station,session,sequence))''')
        self.db.execute('CREATE INDEX IF NOT EXISTS obs_time ON observations(station,sampled_at)')
        # latest() orders by identity; without this index every call sorted the whole table (337 ms
        # at a year of readings, under the store lock, on every ingest and every MQTT tick).
        self.db.execute('CREATE INDEX IF NOT EXISTS obs_latest ON observations'
                        '(station, CAST(session AS INTEGER) DESC, sequence DESC, received_at DESC)')
        # reconstruct() looks up a boot epoch's readings by time basis and uptime.
        self.db.execute('CREATE INDEX IF NOT EXISTS obs_basis ON observations(station, session, time_basis, uptime_s)')
        self.db.execute('CREATE INDEX IF NOT EXISTS obs_effective ON observations(station,effective_at)')
        # Authentic frames that were permanently rejected (and NACKed) are kept, never silently lost.
        self.db.execute('''CREATE TABLE IF NOT EXISTS rejections (station TEXT, session TEXT, sequence INTEGER,
            received_at REAL, reason TEXT, detail TEXT, frame_hex TEXT)''')
        # Node health reports (kind 4, gap G8). Ordered by (epoch, uptime), not arrival, so a
        # delayed or replayed report never replaces a newer one.
        self.db.execute('''CREATE TABLE IF NOT EXISTS diagnostics (station TEXT, session INTEGER, uptime_s INTEGER,
            received_at REAL, report TEXT, PRIMARY KEY(station,session,uptime_s))''')
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
            self.check_counters(record)
            received = time.time() if received_at is None else received_at
            synced = record['sampled_at'] is not None
            self.db.execute('INSERT INTO observations (station,session,sequence,sampled_at,received_at,payload,'
                            'uptime_s,effective_at,time_basis,time_uncertainty_s) VALUES (?,?,?,?,?,?,?,?,?,?)',
                            (*key,record['sampled_at'],received,payload,record.get('uptime_s'),record['sampled_at'],
                             'synchronized' if synced else 'unknown',0 if synced else None))
            # A new untimed reading needs only its own estimate; a new reference may improve them all.
            self.reconstruct(record['station'],record['session'],None if synced else record['sequence'])
        return True

    def check_counters(self, record):
        """Since-boot counters (rain tips, energy, charge) never decrease in sequence order within an
        epoch (design 5.3). Compared with the stored neighbours by sequence, not by arrival, so a
        backfilled older record is fine; a decrease is an invalid record."""
        from ws0.fields import FIELDS
        for f in FIELDS:
            value = record.get(f.name)
            if not f.counter or value is None:
                continue
            path = f'$.{f.name}'
            args = (path, record['station'], record['session'], path)
            before = self.db.execute('SELECT json_extract(payload,?) FROM observations WHERE station=? AND session=? '
                                     'AND json_extract(payload,?) IS NOT NULL AND sequence<? ORDER BY sequence DESC LIMIT 1',
                                     (*args, record['sequence'])).fetchone()
            after = self.db.execute('SELECT json_extract(payload,?) FROM observations WHERE station=? AND session=? '
                                    'AND json_extract(payload,?) IS NOT NULL AND sequence>? ORDER BY sequence LIMIT 1',
                                    (*args, record['sequence'])).fetchone()
            if (before and before[0] > value) or (after and after[0] < value):
                raise ValueError(f'{f.name} decreased within epoch {record["session"]}')

    def reconstruct(self, station, session, only=None):
        """Give unsynchronized samples of one boot epoch a UTC time from the nearest trusted
        synchronized sample of the same epoch (same monotonic uptime counter). A reference
        whose clock was ahead of its own receipt (quarantined) is never used. Targets are looked up
        first: most epochs have none, and then nothing else is read (every ingest calls this)."""
        targets = self.db.execute('SELECT sequence,uptime_s FROM observations WHERE station=? AND session=? '
                                  "AND time_basis IN ('unknown','reconstructed') AND uptime_s IS NOT NULL"
                                  + ('' if only is None else ' AND sequence=?'),
                                  (station,session) if only is None else (station,session,only)).fetchall()
        ref_sql = ('SELECT uptime_s,sampled_at FROM observations WHERE station=? AND session=? '
                   "AND time_basis='synchronized' AND uptime_s IS NOT NULL AND sampled_at<=received_at+5 "
                   'AND uptime_s {} ? ORDER BY uptime_s {} LIMIT 1')
        for sequence, uptime in targets:
            near = [r for r in (self.db.execute(ref_sql.format('<=','DESC'),(station,session,uptime)).fetchone(),
                                self.db.execute(ref_sql.format('>=','ASC'),(station,session,uptime)).fetchone()) if r]
            if not near:
                continue
            ref_uptime, ref_utc = min(near, key=lambda r: abs(r[0]-uptime))
            span = abs(uptime-ref_uptime)
            self.db.execute("UPDATE observations SET effective_at=?,time_basis='reconstructed',time_uncertainty_s=? "
                            'WHERE station=? AND session=? AND sequence=?',
                            (ref_utc+(uptime-ref_uptime),QUANTIZATION_S+span*DRIFT_PPM/1e6,station,session,sequence))

    def reject(self, station, session, sequence, reason, detail, frame_hex, received_at=None):
        """Durably record a permanently rejected authentic frame before the NACK is sent."""
        with self.lock, self.db:
            self.db.execute('INSERT INTO rejections VALUES (?,?,?,?,?,?,?)',
                            (station,session,sequence,time.time() if received_at is None else received_at,
                             reason,detail,frame_hex))

    def diagnostic(self, station, report, received_at=None):
        with self.lock, self.db:
            self.db.execute('INSERT OR IGNORE INTO diagnostics VALUES (?,?,?,?,?)',
                            (station,report['epoch'],report['uptime_s'],
                             time.time() if received_at is None else received_at,json.dumps(report,sort_keys=True)))

    def latest_diagnostic(self, station):
        with self.lock:
            row = self.db.execute('SELECT report,received_at FROM diagnostics WHERE station=? '
                                  'ORDER BY session DESC,uptime_s DESC LIMIT 1',(station,)).fetchone()
        return None if row is None else json.loads(row[0]) | {'received_at':row[1]}

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
        timely = age is not None and 0 <= age < 180 and not future and not vague
        # Availability is per field (design 5.7): one dead sensor never hides the others.
        from ws0.fields import BY_NAME, MEASURED
        fields = {name: timely and (record[name] is not None or (name == 'wind_dir_deg' and record.get('wind_calm', False)))
                  for name in MEASURED if name in record}
        available = timely and record['quality'] != 'sensor_fault'
        reason = ('future_clock_at_receipt' if future else 'unknown_clock' if age is None else
                  'time_uncertain' if vague else
                  'sensor_fault' if record['quality']=='sensor_fault' else 'fresh' if timely else 'stale_or_clock_step')
        from ws0.fields import derived
        return {'available':available,'reason':reason,'fields_available':fields,'age_seconds':age,'received_at':row[1],
                'observation':record,'derived':derived(record),'effective_sampled_at':effective,'time_basis':basis,
                'time_uncertainty_s':uncertainty,'units':{n: BY_NAME[n].unit for n in fields if BY_NAME[n].unit}}

    def history(self, station, start=0, end=253402300800, limit=100, offset=0):
        """Stable page ordering; UTC-unknown records remain in DB but outside time queries."""
        with self.lock:
            rows = self.db.execute('''SELECT payload,received_at,effective_at,time_basis,time_uncertainty_s
                FROM observations WHERE station=? AND effective_at>=? AND effective_at<?
                ORDER BY effective_at,session,sequence LIMIT ? OFFSET ?''',
                (station,start,end,limit,offset)).fetchall()
        return [json.loads(r[0]) | {'received_at':r[1],'effective_sampled_at':r[2],'time_basis':r[3],
                                    'time_uncertainty_s':r[4]} for r in rows]
