"""The gateway's descriptor sets (docs/module-protocol.md section 11.2, WSMP-E5 to E7) and what
it shows of each module's identity (docs/superpowers/specs/2026-10-21-sensor-module-ports-design.md
section 6.7: the serial, its source, the record status and the record CRC).

A set arrives whole (the radio frame kind and its fragments are WSMP-E9, a later step) and is
decoded by ``ws0/wsmp_set.py``:

- WSMP-E5: a set whose digest or layout is wrong is not accepted. It is kept for diagnosis.
- WSMP-E6: a second, different set under a generation already held for the station key is an
  alarm, like key reuse. The first set stays.
- WSMP-E7: a set that fails the check (registry, serial namespace, one module per type) is stored
  for diagnosis but not used, with an alarm.

Sets are keyed by the station key (``station_key``: the station ID and a fingerprint of its radio
key), because a generation is unique only under one key (WSMP-E1): a re-keyed station starts a new
generation space. Each stored set records the registry version it was checked against (WSMP-G4).

**The current set** is the set of the generation that the station's newest frame carries, newest by
the frame's authenticated counter, never by arrival: the counter is strictly increasing, shared by
readings and health reports, and survives a WIPE, so a set that arrives late (an answer to an old
describe request), a reused generation (WSMP-E2) or a host clock step cannot make an old set
current. Readings carry the generation from WSMP section 11.3 on (with WSMP-E9);
until then nothing calls ``note_generation`` and no set is current.

The alarm on one serial in the current sets of two stations (section 6.7, "Duplicates") is
``serial_alarms``. It needs a gateway that serves several stations; this gateway serves one, so it
is not wired to any output yet.

Concurrency, as ``gateway.Store``: writes take ``self.lock`` on the writer connection; reads (the
HTTP and MQTT threads) use a read-only connection of their own, so they never wait on a write.
"""
import contextlib
import hashlib
import sqlite3
import threading
import time
from pathlib import Path

from gateway import full_flush

from . import wsmp_registry as reg
from . import wsmp_set

TWO_STATIONS_S = 600        # one serial in two stations' sets for longer than this is an alarm
HEARD_S = 600               # ... counting only stations heard from within this
GLOBAL_NAMESPACES = (0x01, 0x02)   # namespace 0x00 repeats across stations by design
ALARMS_SHOWN = 5            # the newest descriptor-set alarms on the diagnostics topic


def station_key(station_id, radio_key):
    """The key that sets are stored under: the station ID and a key fingerprint, the first 64 bits of
    SHA-256 over a domain label and the key (so the fingerprint is no hash of the bare key)."""
    return f'{station_id}:{hashlib.sha256(b"ws0-station-key\0" + bytes(radio_key)).hexdigest()[:16]}'


class DescriptorSets:
    """Durable descriptor sets by station key and generation (one SQLite file in the run directory)."""

    def __init__(self, path):
        self.lock = threading.RLock()
        self.path = Path(path).resolve()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        full_flush(self.db)   # WAL and synchronous=FULL, as the observation store
        with self.db:
            self.db.execute('CREATE TABLE IF NOT EXISTS sets (station TEXT NOT NULL, generation INTEGER NOT NULL, '
                            'raw BLOB NOT NULL, usable INTEGER NOT NULL, fault TEXT, registry_version INTEGER NOT NULL, '
                            'received_at REAL NOT NULL, PRIMARY KEY (station, generation))')
            self.db.execute('CREATE TABLE IF NOT EXISTS refused (station TEXT NOT NULL, reason TEXT NOT NULL, '
                            'detail TEXT NOT NULL, raw BLOB NOT NULL, received_at REAL NOT NULL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS current (station TEXT PRIMARY KEY, generation INTEGER NOT NULL, '
                            'counter INTEGER NOT NULL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS serial_pairs (serial INTEGER NOT NULL, a TEXT NOT NULL, '
                            'b TEXT NOT NULL, since REAL NOT NULL, PRIMARY KEY (serial, a, b))')

    def close(self):
        self.db.close()

    @contextlib.contextmanager
    def reader(self):
        """A read-only connection with one consistent snapshot; it never takes self.lock."""
        db = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, check_same_thread=False)
        try:
            db.execute('BEGIN')
            yield db
        finally:
            db.close()

    def _refuse(self, station, reason, detail, raw, now):
        with self.lock, self.db:
            self.db.execute('INSERT INTO refused VALUES (?,?,?,?,?)', (station, reason, detail, bytes(raw), now))
        return {'outcome': reason, 'detail': detail}

    def accept(self, station, raw, now=None):
        """Store one whole set. Returns {'outcome': 'accepted' | 'duplicate' | 'invalid' | 'conflict' |
        'registry', ...}; 'conflict' (WSMP-E6) and 'registry' (WSMP-E7) are alarms."""
        now = time.time() if now is None else now
        try:
            s = wsmp_set.unpack(raw)
        except wsmp_set.SetError as e:                       # WSMP-E5
            return self._refuse(station, 'invalid', str(e), raw, now)
        with self.lock:
            row = self.db.execute('SELECT raw FROM sets WHERE station=? AND generation=?',
                                  (station, s.generation)).fetchone()
            if row is not None:
                if bytes(row[0]) == bytes(raw):
                    return {'outcome': 'duplicate', 'generation': s.generation}
                return self._refuse(station, 'conflict',                                # WSMP-E6
                                    f'generation {s.generation} already holds a different set', raw, now)
            fault = wsmp_set.check(s)                                                   # WSMP-E7
            with self.db:
                self.db.execute('INSERT INTO sets VALUES (?,?,?,?,?,?,?)',
                                (station, s.generation, bytes(raw), int(fault is None), fault,
                                 reg.REGISTRY_VERSION, now))
        if fault is not None:
            return {'outcome': 'registry', 'generation': s.generation, 'detail': fault}
        return {'outcome': 'accepted', 'generation': s.generation}

    def note_generation(self, station, generation, counter):
        """An authenticated reading or health report with this frame counter carried this generation
        (WSMP section 11.3). Only a frame newer than every one noted before moves the current generation."""
        with self.lock, self.db:
            row = self.db.execute('SELECT counter FROM current WHERE station=?', (station,)).fetchone()
            if row is None or counter > row[0]:
                self.db.execute('INSERT OR REPLACE INTO current VALUES (?,?,?)', (station, generation, counter))

    def set_of(self, station, generation):
        """The usable set of that generation, or None (unknown, or it failed the check)."""
        with self.reader() as db:
            row = db.execute('SELECT raw FROM sets WHERE station=? AND generation=? AND usable=1',
                             (station, generation)).fetchone()
        return wsmp_set.unpack(row[0]) if row else None

    def current_generation(self, station):
        with self.reader() as db:
            row = db.execute('SELECT generation FROM current WHERE station=?', (station,)).fetchone()
        return row[0] if row else None

    def current(self, station):
        """The set of the generation the station's newest reading carries, or None (no reading with a
        generation yet, or that generation's set is not held: WSMP-E8 asks for it)."""
        generation = self.current_generation(station)
        return None if generation is None else self.set_of(station, generation)

    def alarms(self, station):
        """The station's conflicts (WSMP-E6) and check failures (WSMP-E7), newest first."""
        with self.reader() as db:
            out = [{'reason': 'conflict', 'detail': d, 'received_at': t} for d, t in db.execute(
                "SELECT detail, received_at FROM refused WHERE station=? AND reason='conflict'", (station,))]
            out += [{'reason': 'registry', 'detail': f'generation {g}: {f}', 'received_at': t} for g, f, t in db.execute(
                'SELECT generation, fault, received_at FROM sets WHERE station=? AND usable=0', (station,))]
        return sorted(out, key=lambda a: -a['received_at'])

    def serial_alarms(self, heard, now=None):
        """One namespace-0x01 or 0x02 serial in the current sets of two stations heard within HEARD_S
        (heard: station key -> last time heard), for longer than TWO_STATIONS_S. Returns
        [{'serial', 'stations', 'since'}]; a pair that ends is forgotten. Needs a multi-station
        gateway: not wired to an output yet (see the module docstring)."""
        now = time.time() if now is None else now
        live = sorted(st for st, t in heard.items() if now - t <= HEARD_S)
        holders = {}
        for st in live:
            s = self.current(st)
            for m in (s.modules if s else ()):
                if m.namespace in GLOBAL_NAMESPACES:
                    holders.setdefault(m.serial, set()).add(st)
        pairs = {(serial, a, b) for serial, sts in holders.items() for a in sts for b in sts if a < b}
        with self.lock, self.db:
            known = {(s, a, b): since for s, a, b, since in self.db.execute('SELECT * FROM serial_pairs')}
            for key in set(known) - pairs:
                self.db.execute('DELETE FROM serial_pairs WHERE serial=? AND a=? AND b=?', key)
            for key in pairs - set(known):
                self.db.execute('INSERT INTO serial_pairs VALUES (?,?,?,?)', (*key, now))
                known[key] = now
        return [{'serial': s, 'stations': [a, b], 'since': known[(s, a, b)]}
                for s, a, b in sorted(pairs) if now - known[(s, a, b)] > TWO_STATIONS_S]


def type_id(m):
    """The module's name in Home Assistant: its type's registry id (air_th, pressure, ...). v1 admits
    at most one module of each type (sensor module ports design, section 6.7; the design's proposed
    WSMP-P10 text), and, as WSMP-H1 asks of every entity ID, it holds no port and no serial, so a
    module's entity survives a move to another port."""
    t = reg.MODULE_TYPES.get(m.type)
    return t['id'].lower() if t else f'type{m.type}'


def record_status(m):
    """The record status as shown: 'none' for a module that never has a record (source port, status
    0: the meters and the power module), else the status name."""
    return 'none' if m.source == 'port' and m.status == 'applied' else m.status


def module_view(m):
    """What the gateway shows of one module (JSON-ready)."""
    return {'port': m.port, 'type': m.type, 'serial': f'{m.serial:016x}', 'serial_source': m.source,
            'record_status': record_status(m), 'no_record': m.no_record, 'record_crc': f'{m.record_crc:08x}'}


def modules_payload(s):
    """The retained MQTT payload of a station's current set: type id -> module_view. None if there is
    no current set; {} for a current set with no module."""
    return None if s is None else {type_id(m): module_view(m) for m in s.modules}


def module_discovery(cfg, type_ids, root):
    """Home Assistant discovery: one diagnostic sensor per module type id, its state the record status
    (applied, a NO_RECORD reason, CAL_REJECTED, SENSOR_CHANGED or none), the rest as attributes. A type
    absent from the current set is unavailable; the templates read with .get, so they never fail."""
    out = {}
    for t in type_ids:
        uid = f"{cfg['station']}_module_{t}"
        out[f'homeassistant/sensor/{uid}/config'] = {
            'name': f'Module {t} record', 'unique_id': uid, 'entity_category': 'diagnostic',
            'state_topic': root + '/modules',
            'value_template': "{{ value_json.get('%s', {}).get('record_status') }}" % t,
            'json_attributes_topic': root + '/modules',
            'json_attributes_template': "{{ value_json.get('%s', {}) | tojson }}" % t,
            'availability': [{'topic': root + '/gateway_availability'},
                             {'topic': root + '/modules',
                              'value_template': "{{ 'online' if '%s' in value_json else 'offline' }}" % t}],
            'availability_mode': 'all',
            'device': {'identifiers': [cfg['station']], 'name': cfg['station'],
                       'manufacturer': 'Weather Station Project', 'model': 'Stage 0 ' + cfg['mode']}}
    return out
