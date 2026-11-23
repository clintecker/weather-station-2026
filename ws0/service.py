"""Single-process gateway: authenticated frames, SQLite, read-only HTTP and MQTT."""
import csv
import hashlib
import hmac
import io
import json
import os
import socket
import sys
import socketserver
import threading
import time
from http import HTTPStatus
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from gateway import CURRENT_MAX_AGE_S, Store
from . import web
from .descsets import ALARMS_SHOWN, DescriptorSets, module_discovery, modules_payload, station_key
import sqlite3
import struct
from .fields import BY_NAME, DERIVED, DIAGNOSTIC_FIELDS, ENERGY, LABELS, MEASURED
from .protocol import (CHARGER_INPUTS, CHARGER_STAGES, CRASH_PC_NONE, DIAG, FIT_CHARGE_CURRENT, FIT_CHARGER_REGS,
                       FIT_CHARGER_STATUS, FIT_GAUGE, FIT_MCU_SUPPLY, FIT_MONITOR_TEMP, FIT_PACK_TEMP, I16_NONE, KEY_LEN,
                       SIGNAL_NONE, KIND_ACK, KIND_DIAG,
                       KIND_NACK, KIND_OBS, LINK_STATES, NACK_COLLISION, NACK_INVALID, RESET_CAUSES, STATION_MAX, U16_NONE,
                       Nonces, charger_keys, decode_observation, diag_problems, frame_counter, frame_kind, pack_reply, seal,
                       unpack_diag, unseal)


def load_config(path):
    """Load secrets locally; bind the diagnostic API to loopback only."""
    cfg = json.loads(path.read_text())
    # The file holds the radio key and API token. A run directory copied by AirDrop, a USB stick or
    # cp can arrive readable by other users; say so (the gateway itself creates it 0600).
    if os.name == 'posix' and Path(path).stat().st_mode & 0o077:
        print(f'#gateway warning: {path} is readable by other users; run chmod 600 on it',
              file=sys.stderr, flush=True)
    if not isinstance(cfg.get('station'), str) or not cfg['station'].replace('-','').isalnum():
        raise ValueError('Invalid station name')
    if type(cfg.get('station_id')) is not int or not 1 <= cfg['station_id'] <= STATION_MAX:
        raise ValueError('Invalid numeric station ID')
    if len(bytes.fromhex(cfg['radio_key'])) != KEY_LEN or len(cfg['api_token']) < API_TOKEN_MIN:
        raise ValueError('Invalid key/token')
    return cfg


API_TOKEN_MIN = 32   # characters; ws0 init makes a 43-character token
KEY_REUSE_ALARM = 'possible key reuse: re-key the node'


def _named(value, names):
    return names[value] if value < len(names) else 'unknown'


def _scaled(value, none, divisor):
    """A health report value in its unit; None for its none code (power telemetry design section 6.1)."""
    return None if value == none else value / divisor


def _plain(value, none):
    return None if value == none else value


def station_keys(d):
    """The version 5 keys of an unpacked health report (docs/protocol-design.md section 4)."""
    return {'epoch':d['epoch'],'uptime_s':d['uptime'],'journal_pending':d['pending'],'journal_lost_total':d['lost'],
            'journal_torn_slots':d['torn'],'abandoned_total':d['abandoned'],'missed_acks_since_boot':d['no_ack'],
            'rejected_replies_since_boot':d['rejects'],'reset_cause':_named(d['reset_cause'],RESET_CAUSES),
            'link':_named(d['link'],LINK_STATES),'firmware_build':f"{d['build']:08x}",
            'ack_rssi_dbm':_plain(d['rssi'],SIGNAL_NONE),'ack_snr_db':_plain(d['snr'],SIGNAL_NONE),
            'crashes_since_power_up':d['crashes'],'energy_state':_named(d['energy'],ENERGY)}


# The gateway keys behind each bit of the fitted byte (design section 6.1, protocol.FIT_*).
FIT_KEYS = {
    FIT_MCU_SUPPLY: ('mcu_supply_mv',),
    FIT_MONITOR_TEMP: ('power_monitor_temp_c',),
    FIT_GAUGE: ('battery_soc_pct', 'battery_soc_rate_pct_h'),
    FIT_CHARGER_STATUS: ('charger_input_power_ok', 'charger_charging', 'charger_fault'),
    FIT_CHARGER_REGS: ('charger_stage', 'charger_active_input', 'charger_reported_input_mv',
                       'charger_reported_input_ma', 'charger_reported_battery_mv', 'charger_temp_c'),
    FIT_CHARGE_CURRENT: ('charger_reported_battery_ma',),
    FIT_PACK_TEMP: ('pack_temp_c', 'charger_cold_hold'),
}

# The TX stack's charger stops charging below about 3.9 degC and starts again above about 6.3 degC
# (BQ25798 VT1 with the pack's B 3950 NTC on the EVM divider, App/power_config.h). The node reports the
# hold as no fault, power good, stage not_charging, with the pack temperature beside it.
COLD_HOLD_BELOW_C = 6.3


def cold_hold(values):
    """charger_cold_hold: True while the charger holds charge off for a cold pack (power good, no fault,
    not charging, the pack under COLD_HOLD_BELOW_C); None without a pack temperature or a charger stage."""
    temp, stage = values['pack_temp_c'], values['charger_stage']
    if temp is None or stage is None:
        return None
    return bool(values['charger_input_power_ok'] and not values['charger_fault'] and stage == 'not_charging'
                and temp < COLD_HOLD_BELOW_C)


def why_null(values, fitted):
    """The power keys that are None, split by the fitted byte: (not measured in this build, sensor
    fault). A key with a value is in neither; a None key whose bit is set is a fitted source that
    failed (design section 6.1)."""
    unmeasured, faults = [], []
    for bit, keys in FIT_KEYS.items():
        for key in keys:
            if values[key] is None:
                (faults if fitted & bit else unmeasured).append(key)
    return sorted(unmeasured), sorted(faults)


def _crash_pc(pc):
    """last_crash_pc: None for no crash since power-up (CRASH_PC_NONE); otherwise 8 hex digits, where
    'ffffffff' (CRASH_PC_UNTRUSTED) says a crash happened but its stacked frame was not trusted, so no PC
    was recorded (fault.c). The dashboard shows that value as text, never as an address."""
    if pc == CRASH_PC_NONE:
        return None
    return f"{pc:08x}"


def power_keys(d):
    """The version 6 keys at offsets 32-63 (design section 6.1), none codes as None. The charger
    keys come from protocol.charger_keys; the fitted byte becomes power_not_measured and
    power_sensor_faults, the None power keys by reason."""
    values = {'last_crash_pc':_crash_pc(d['crash_pc']),
            'boots_since_power_up':d['boots'],'tx_timeouts_since_boot':d['tx_timeouts'],
            'i2c_recoveries_since_boot':d['i2c_recoveries'],'mcu_supply_mv':_plain(d['vdda_mv'],U16_NONE),
            'power_monitor_temp_c':_scaled(d['monitor_temp'],I16_NONE,10),
            'battery_soc_pct':_scaled(d['soc'],U16_NONE,256),
            'battery_soc_rate_pct_h':_scaled(d['soc_rate'],I16_NONE,10),
            'charger_reported_input_mv':_plain(d['chg_input_mv'],U16_NONE),
            'charger_reported_input_ma':_plain(d['chg_input_ma'],I16_NONE),
            'charger_reported_battery_mv':_plain(d['chg_batt_mv'],U16_NONE),
            'charger_reported_battery_ma':_plain(d['chg_batt_ma'],I16_NONE),
            'charger_temp_c':_scaled(d['chg_temp'],I16_NONE,10),'pack_temp_c':_scaled(d['pack_temp'],I16_NONE,10),
            **charger_keys(d['charger_status'])}
    values['charger_cold_hold'] = cold_hold(values)
    unmeasured, faults = why_null(values, d['fitted'])
    return values | {'power_not_measured':unmeasured,'power_sensor_faults':faults}


def health_report(payload):
    """Gateway keys of a health report plaintext, and the canonical rules it breaks (design section
    6.1). A non-canonical report is kept: charger_keys gives None for a reserved stage or input."""
    d = unpack_diag(payload)
    return station_keys(d) | power_keys(d), diag_problems(d)


# Every key a stored health report carries (design section 6.1). Disjoint from fields.MEASURED, so a
# name has one meaning in the API, the dashboard and Home Assistant (design section 10.2).
HEALTH_KEYS = tuple(health_report(bytes(DIAG.size))[0])


class CounterRegression(ValueError):
    """An authentic node frame whose counter is at or below the stored high-water mark and whose
    bytes differ from (or were never seen as) the frame accepted under that counter: the node
    sealed under a nonce it already used (key reuse)."""


class Replay(ValueError):
    """An exact copy of a node frame already accepted (radio duplicate or a recorded frame played
    back). Harmless: never answered or stored as data, counted, and no key-reuse alarm."""


RECEIVER_SILENT_S = 180   # no RX #alive (every 60 s) for this long: the receiver is silent


class Gateway:
    """The sole ACK authority is the host after durable database commit."""
    def __init__(self, cfg, directory):
        self.cfg, self.directory = cfg, directory
        self.key = bytes.fromhex(cfg['radio_key'])
        self.store = Store(directory / 'observations.sqlite3')
        try:
            self.nonces = Nonces(directory / 'gateway-nonces.sqlite3',self.key,cfg['station_id'],KIND_ACK)
        except BaseException:
            self.store.db.close()
            raise
        try:
            self._init_state(cfg)
        except BaseException:  # e.g. SchemaDrift: an open handle would keep the files locked (Windows)
            self.close()
            raise

    def _init_state(self, cfg):
        self.accepted = self.rejected = self.nacked = 0
        self.node_counter = self.nonces.node_counter()  # cached for the HTTP/MQTT threads
        self.clock = None  # ws0.clock.HostClock when serving hardware; None = trust host
        self.receiver = None  # RX board liveness, set by the serial loop
        self.expects_receiver = False  # a serial link to an RX board is configured (serve)
        self.started = time.time()
        self.last_ingested = None  # the observation in the frame just ACKed, for the serve log
        self.last_outcome = None   # what receive() did with the last frame: ack, duplicate, nack, diag
        self.lock = threading.Lock()
        self.hub = web.EventHub()  # live events for the dashboard stream (GET /v1/events)
        self.telemetry = web.Telemetry(self)
        self.descsets = DescriptorSets(self.directory / 'descriptor-sets.sqlite3')
        self.station_key = station_key(cfg['station_id'], self.key)   # sets live under the station key (WSMP-E1)

    def check_counter(self, frame, epoch, sequence, now):
        """Every node transmission, retries included, gets a fresh, strictly increasing
        counter from one space shared by observations and health reports (firmware
        store_next_counter; WIPE keeps it). So an authentic frame at or below the mark is a replay or nonce reuse.
        It is never answered or stored as data; the raw frame is kept as a rejection."""
        counter = frame_counter(frame)
        verdict = self.nonces.advance_node_counter(counter,now,hashlib.sha256(frame).hexdigest())
        self.node_counter = self.nonces.node_counter()
        if verdict == 'fresh':
            return
        if verdict == 'replay':
            self.store.reject(self.cfg['station'],str(epoch),sequence,'replay',
                              f'identical copy of the frame accepted under counter {counter}',frame.hex(),now,
                              once=True)
            self.rejected += 1
            raise Replay(f'replay of counter {counter}')
        detail = (f"counter {counter} <= high-water mark {self.node_counter['max_node_counter']}: "
                  + KEY_REUSE_ALARM)
        self.store.reject(self.cfg['station'],str(epoch),sequence,'counter_regression',detail,frame.hex(),now)
        self.rejected += 1
        raise CounterRegression(detail)

    def receive_diagnostic(self, frame, payload, now):
        """Node health report (kind 4), already authenticated: store; never answered."""
        self.check_counter(frame,struct.unpack_from('>I',payload)[0],None,now)
        report, problems = health_report(payload)
        if problems:   # never answered, so keep the report; charger keys are already None (design 6.1)
            print(f"#gateway warning: non-canonical health report (epoch {report['epoch']}, uptime "
                  f"{report['uptime_s']} s): {', '.join(problems)}",file=sys.stderr,flush=True)
        self.store.diagnostic(self.cfg['station'],report,now)
        self.telemetry.diagnostic(report,now)
        return report

    def receive(self, frame, now=None):
        """Authenticate, validate and commit before returning an encrypted receipt."""
        now = time.time() if now is None else now
        with self.lock:
            diag = frame_kind(frame) == KIND_DIAG
            try:
                payload = unseal(self.key,self.cfg['station_id'],KIND_DIAG if diag else KIND_OBS,frame)
            except Exception:
                self.rejected += 1  # unauthenticated: never answered (a NACK would let anyone drop data)
                raise
            if diag:
                self.receive_diagnostic(frame,payload,now)
                self.last_outcome = 'diag'
                return None  # fire-and-forget: no reply on air
            epoch, sequence = struct.unpack_from('>II',payload)
            # Raised durably before the commit, so a crash cannot leave it below this frame.
            self.check_counter(frame,epoch,sequence,now)
            try:
                record = decode_observation(payload,self.cfg['station'])
                inserted = self.store.ingest(record,now)
            except ValueError as exc:
                # Authentic but permanently unacceptable: record it, then tell the node to stop
                # retrying it. Commit failures (OSError) still propagate with no reply.
                reason = NACK_COLLISION if str(exc) == 'Identity collision' else NACK_INVALID
                self.store.reject(self.cfg['station'],str(epoch),sequence,
                                  'identity_collision' if reason == NACK_COLLISION else 'invalid_record',
                                  str(exc),frame.hex(),now)
                self.rejected += 1
                self.nacked += 1
                self.last_outcome = 'nack'
                return seal(self.key,self.cfg['station_id'],KIND_NACK,self.nonces,
                            pack_reply(epoch,sequence,reason,frame_counter(frame)))
            except (OSError, sqlite3.Error):
                # Commit failed (disk full, I/O error, database locked): no ACK, the node keeps the
                # record and retries. sqlite3 raises its own errors, not OSError.
                self.rejected += 1
                raise
            try:
                # Host UTC rides in the authenticated ACK: the node's only time source. A host
                # clock measured as wrong sends 0 instead: the node then keeps its own clock.
                host_utc = int(now)
                if self.clock and not self.clock.may_issue_time():
                    host_utc = 0
                ack = seal(self.key,self.cfg['station_id'],KIND_ACK,self.nonces,
                           pack_reply(int(record['session']),record['sequence'],host_utc,
                                      frame_counter(frame)))
                self.accepted += int(inserted)
                self.last_ingested = dict(record,duplicate=not inserted)
                self.last_outcome = 'ack' if inserted else 'duplicate'
                if inserted:
                    self.telemetry.observation(record,now)
                return ack
            except Exception:
                self.rejected += 1
                raise

    def receiver_report(self, text, at):
        """An RX '#alive' or '#boot' line: the receiver is alive."""
        self.receiver = {'alive':True,'last_report':web.utc_stamp(at),'last_seen':at,**web.line_fields(text)}

    def receiver_silent(self, now=None):
        """The receiver-silent alert: True once no RX report came for RECEIVER_SILENT_S (or none at all
        that long after start with a serial link configured), False while it reports, None when no
        receiver is expected (e.g. the demo before its simulated receiver reports)."""
        now = time.time() if now is None else now
        if self.receiver:
            return not self.receiver.get('alive', True) or now - self.receiver['last_seen'] > RECEIVER_SILENT_S
        if self.expects_receiver:
            return now - self.started > RECEIVER_SILENT_S
        return None

    def counter_alarm(self):
        """Key-reuse alarm. It persists across restarts; the cure is a new key, i.e. a new
        state directory (re-key procedure, docs/failure-modes.md §9.5), which starts with a fresh mark."""
        state = self.node_counter
        return {'alarm':KEY_REUSE_ALARM if state['counter_regression'] else None,
                'counter_regression':state['counter_regression'],
                'last_regression_counter':state['last_regression_counter']}

    def receive_descriptor_set(self, raw, now=None):
        """A whole descriptor set from the station (WSMP-E5 to E7). The radio frame kind that carries
        it and its fragments is WSMP-E9, a later step; this is where it will hand the set over. A
        conflict (E6) or a failed check (E7) is an alarm: on stderr now, and on the diagnostics topic."""
        now = time.time() if now is None else now
        with self.lock:
            result = self.descsets.accept(self.station_key, raw, now)
        if result['outcome'] in ('conflict', 'registry'):
            print(f"#gateway alarm descriptor set {result['outcome']}: {result['detail']}", file=sys.stderr, flush=True)
        return result

    def note_generation(self, generation, counter):
        """The generation that an authenticated reading or health report with this frame counter carries
        (WSMP section 11.3, with WSMP-E9): the newest by counter names the current set."""
        self.descsets.note_generation(self.station_key, generation, counter)

    def modules(self):
        """The current set's modules, type id -> serial, source, record status; None without a current set."""
        return modules_payload(self.descsets.current(self.station_key))

    def descriptor_set_alarms(self):
        """The newest descriptor-set alarms (WSMP-E6, E7), for the diagnostics topic."""
        return self.descsets.alarms(self.station_key)[:ALARMS_SHOWN]

    def close(self):
        self.store.db.close()
        self.nonces.db.close()
        if getattr(self, 'descsets', None):
            self.descsets.close()

    def status(self):
        """Expose no credentials or raw keys in diagnostics."""
        return {'stage':0,'h01':'NOT RUN','mode':self.cfg['mode'],
                'alarm':self.counter_alarm()['alarm'],'node_counter':dict(self.node_counter),
                'station':self.cfg['station'],'accepted_this_process':self.accepted,
                'rejected_this_process':self.rejected,'nacked_this_process':self.nacked,
                'host_clock':self.clock.status() if self.clock else None,
                'node_diagnostics':self.store.latest_diagnostic(self.cfg['station']),
                'receiver':self.receiver,'rx_faults':self.telemetry.fault_summary(),
                'latest':self.store.latest(self.cfg['station'])}


HTTP_TIMEOUT_S = 10       # a request (headers and body) must arrive within this; SSE sets its own
HTTP_MAX_CONNECTIONS = 32  # beyond the 8 event streams: the API is for one household's browsers


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """At most HTTP_MAX_CONNECTIONS handler threads. Unbounded, a slow or half-open client per
    connection (slowloris) took a thread and a file descriptor each until the process ran out of
    descriptors (security audit, 2026-10-14); then serial reconnects and log rotation fail too.
    A connection over the cap is closed at once."""
    def __init__(self, *args, **kwargs):
        self.slots = threading.BoundedSemaphore(HTTP_MAX_CONNECTIONS)
        super().__init__(*args, **kwargs)

    def server_bind(self):
        """HTTPServer.server_bind also looks up the host's name (socket.getfqdn, reverse DNS) for a
        display name nobody reads. With slow DNS that blocked the gateway's start for over 20 s."""
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def http_server(gateway, port):
    """All endpoints require a bearer token; HTTP cannot inject observations."""
    class Handler(BaseHTTPRequestHandler):
        timeout = HTTP_TIMEOUT_S   # socket timeout for reading a request (None waited forever)
        def log_message(self, *args):
            pass  # Avoid recording credentials or query strings in access logs.

        def do_GET(self):
            url = urlparse(self.path)
            if web.serve_static(self,url.path):
                return  # the dashboard page itself: fixed files, no data
            supplied = self.headers.get('Authorization','')
            expected = 'Bearer ' + gateway.cfg['api_token']
            if not hmac.compare_digest(supplied.encode(),expected.encode()):
                self.reply(HTTPStatus.UNAUTHORIZED,{'error':'unauthorized'})
                return
            query = parse_qs(url.query)
            try:
                if url.path == '/v1/status':
                    result = gateway.status()
                elif url.path == '/v1/observations/latest':
                    result = gateway.store.latest(gateway.cfg['station'])
                elif url.path == '/v1/observations':
                    limit = web.int_param(query,'limit',100,1,1000)
                    offset = web.int_param(query,'offset',0,0,2**31)
                    start = web.utc_param(query,'from',0)
                    end = web.utc_param(query,'to',web.FAR_FUTURE)
                    if end < start:
                        raise ValueError('Invalid time range')
                    rows = gateway.store.history(gateway.cfg['station'],start,end,limit,offset)
                    if query.get('format',['json'])[0] == 'csv':
                        stream = io.StringIO()
                        # Every key a stored record can carry; extrasaction='raise' turns a
                        # forgotten column into an error instead of a silently dropped value.
                        fields = ['version','station','session','sequence','sampled_at','received_at',
                                  'effective_sampled_at','time_basis','time_uncertainty_s','uptime_s',
                                  'time_quality','energy_state','calibration_revision','quality',
                                  *MEASURED,'wind_calm','qualifiers']
                        writer = csv.DictWriter(stream,fields,extrasaction='raise')
                        writer.writeheader()
                        writer.writerows(dict(r,qualifiers=json.dumps(r['qualifiers'],sort_keys=True))
                                         if 'qualifiers' in r else r for r in rows)
                        self.reply(HTTPStatus.OK,stream.getvalue(),'text/csv')
                        return
                    result = {'observations':rows,'offset':offset,'limit':limit,
                              'units':{**{n:BY_NAME[n].unit for n in MEASURED},
                                       'sampled_at':'unix_seconds_UTC'}}
                elif url.path in web.ROUTES:
                    web.route(self,gateway,url.path,query)  # dashboard data and the event stream
                    return
                else:
                    self.reply(HTTPStatus.NOT_FOUND,{'error':'not_found'})
                    return
                self.reply(HTTPStatus.OK,result)
            except (ValueError,OverflowError) as exc:
                self.reply(HTTPStatus.BAD_REQUEST,{'error':str(exc)})

        def reply(self, code, body, content_type='application/json'):
            data = (json.dumps(body,allow_nan=False) if content_type=='application/json' else body).encode()
            self.send_response(code)
            self.send_header('Content-Type',content_type+'; charset=utf-8')
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            self.wfile.write(data)
    host = web.bind_address(gateway.cfg)
    server_class = BoundedThreadingHTTPServer
    if ':' in host:   # IPv6 literal: the stock server class is AF_INET only
        server_class = type('ThreadingHTTPServerV6',(BoundedThreadingHTTPServer,),{'address_family':socket.AF_INET6})
    server = server_class((host,port),Handler)
    # shutdown() waits up to one poll interval: 0.5 s by default, paid on every gateway stop and
    # by every test that starts a server. 0.05 s costs an idle select() wakeup 20 times a second.
    threading.Thread(target=server.serve_forever,kwargs={'poll_interval':0.05},daemon=True).start()
    return server


MODULES_UNPUBLISHED = object()   # nothing sent on …/modules on this connection yet

DEFAULT_DISCOVERY = ('temperature_c','humidity_pct')   # advertised before the first reading


def ha_device(cfg):
    return {'identifiers':[cfg['station']],'name':cfg['station'],
            'manufacturer':'Weather Station Project','model':'Stage 0 '+cfg['mode']}


# Home Assistant entities for the power keys of the health report (power telemetry design section
# 10.2): key -> (component, name, unit, device class). The station counters stay JSON-only.
HEALTH_ENTITIES = {
    'battery_soc_pct':('sensor','Battery state of charge (gauge)','%','battery'),
    'battery_soc_rate_pct_h':('sensor','Battery state of charge rate (gauge)','%/h',None),
    'charger_charging':('binary_sensor','Charger charging',None,'battery_charging'),
    'charger_input_power_ok':('binary_sensor','Charger input power good',None,'power'),
    'charger_fault':('binary_sensor','Charger fault',None,'problem'),
    'charger_stage':('sensor','Charger stage',None,'enum'),
    'charger_active_input':('sensor','Charger active input',None,'enum'),
    'power_monitor_temp_c':('sensor','Power monitor temperature','°C','temperature'),
    'charger_temp_c':('sensor','Charger temperature','°C','temperature'),
    'pack_temp_c':('sensor','Battery pack temperature','°C','temperature'),
    'mcu_supply_mv':('sensor','MCU supply voltage','mV','voltage'),
    'charger_reported_input_mv':('sensor','Charger-reported input voltage','mV','voltage'),
    'charger_reported_battery_mv':('sensor','Charger-reported battery voltage','mV','voltage'),
    'charger_reported_input_ma':('sensor','Charger-reported input current','mA','current'),
    'charger_reported_battery_ma':('sensor','Charger-reported charge current','mA','current'),
}
# A health report is due every 15 minutes (and after boot and each link-state change). Its Home
# Assistant entities go unavailable once the newest one is older than two periods plus slack, the
# same limit as the dashboard's "health report overdue" chip (static/app.js DIAG_OVERDUE_S).
HEALTH_PERIOD_S = 900
HEALTH_MAX_AGE_S = 2 * HEALTH_PERIOD_S + 100
HEALTH_OPTIONS = {'charger_stage':[s for s in CHARGER_STAGES if s],'charger_active_input':[s for s in CHARGER_INPUTS if s]}


def health_discovery(cfg, keys=tuple(HEALTH_ENTITIES)):
    """HA entities for health report keys, read from the …/diagnostics topic. Their own namespace:
    unique_id <station>_diag_<key> and config topic homeassistant/<component>/<station>_diag_<key>/config,
    so they never overwrite an observation entity <station>_<field>. Available while the gateway is
    online, the newest report is fresh (…/diagnostics/availability, HEALTH_MAX_AGE_S) and the key is
    not null in it (an older report without the key: unavailable)."""
    root = f"weatherstation/v1/{cfg['station']}"
    result = {}
    for key in keys:
        if key not in HEALTH_ENTITIES:
            continue
        component, name, unit, ha_class = HEALTH_ENTITIES[key]
        uid = f"{cfg['station']}_diag_{key}"
        value = "{{ 'ON' if value_json."+key+" else 'OFF' }}" if component == 'binary_sensor' else '{{ value_json.'+key+' }}'
        entry = {'name':name,'unique_id':uid,'state_topic':root+'/diagnostics','value_template':value,
                 'entity_category':'diagnostic',
                 'availability':[{'topic':root+'/gateway_availability'},{'topic':root+'/diagnostics/availability'},
                                 {'topic':root+'/diagnostics','value_template':
                                  "{{ 'online' if value_json.get('"+key+"') is not none else 'offline' }}"}],
                 'availability_mode':'all','device':ha_device(cfg)}
        if ha_class:
            entry['device_class'] = ha_class
        if unit:
            entry |= {'unit_of_measurement':unit,'state_class':'measurement'}
        if key in HEALTH_OPTIONS:
            entry['options'] = HEALTH_OPTIONS[key]
        result[f'homeassistant/{component}/{uid}/config'] = entry
    return result


def health_fresh(report, now):
    """True while the newest health report (latest_diagnostic, with its gateway receipt time) is younger
    than HEALTH_MAX_AGE_S, so a node that stops sending does not leave its SOC and charger state live."""
    if not report or report.get('received_at') is None:
        return False
    return 0 <= now - report['received_at'] < HEALTH_MAX_AGE_S


# Home Assistant alert entities (binary_sensor, device class problem: ON = something is wrong), computed
# by the gateway each tick and published on …/alerts. They depend on the gateway only, so a stale station
# shows as an alert that is on, never as an unavailable one. charger_cold_hold is advertised only once a
# health report carries a value for it (a build with a pack temperature, cold_hold).
ALERTS = {'station_stale':'Station stale','battery_low':'Battery low','charger_fault':'Charger fault (alert)',
          'charger_cold_hold':'Charger cold hold','receiver_silent':'Receiver silent'}
ALERTS_ALWAYS = ('station_stale','battery_low','charger_fault','receiver_silent')
BATTERY_LOW_SOC_PCT = 20                      # gauge SOC below this: battery low
LOW_ENERGY_STATES = ('conserve','critical')   # the node's own energy state says the same


def alerts(latest, diag, receiver_silent, now):
    """The alert values: True (problem), False (fine) or None (not known: the entity goes unavailable).
    station_stale: the newest reading is not fresh (CURRENT_MAX_AGE_S) or there is none; a fresh reading
    flagged sensor_fault is not stale. battery_low: gauge SOC < BATTERY_LOW_SOC_PCT in a fresh health
    report, or an energy state of conserve/critical (the fresh reading's, else the fresh report's).
    charger_fault and charger_cold_hold: from a fresh health report."""
    age = latest.get('age_seconds')
    fresh_reading = age is not None and 0 <= age < CURRENT_MAX_AGE_S and \
        latest.get('reason') in ('fresh', 'sensor_fault')
    report = diag if health_fresh(diag, now) else {}
    soc = report.get('battery_soc_pct')
    energy = (latest.get('observation') or {}).get('energy_state') if fresh_reading else None
    energy = energy or report.get('energy_state')
    known = [v for v in (None if soc is None else soc < BATTERY_LOW_SOC_PCT,
                         None if energy is None else energy in LOW_ENERGY_STATES) if v is not None]
    return {'station_stale':not fresh_reading,'battery_low':any(known) if known else None,
            'charger_fault':report.get('charger_fault'),'charger_cold_hold':report.get('charger_cold_hold'),
            'receiver_silent':receiver_silent}


def alert_discovery(cfg, keys=ALERTS_ALWAYS):
    """HA binary sensors for the alerts (unique_id <station>_alert_<key>), read from …/alerts. Available
    while the gateway is online and the key is not null; never tied to the station's availability."""
    root = f"weatherstation/v1/{cfg['station']}"
    result = {}
    for key in keys:
        uid = f"{cfg['station']}_alert_{key}"
        result[f'homeassistant/binary_sensor/{uid}/config'] = {
            'name':ALERTS[key],'unique_id':uid,'state_topic':root+'/alerts','device_class':'problem',
            'value_template':"{{ 'ON' if value_json."+key+" else 'OFF' }}",
            'availability':[{'topic':root+'/gateway_availability'},
                            {'topic':root+'/alerts','value_template':
                             "{{ 'online' if value_json.get('"+key+"') is not none else 'offline' }}"}],
            'availability_mode':'all','device':ha_device(cfg)}
    return result


# Station fields that are diagnostic in Home Assistant only (the dashboard keeps them with the weather):
# the raw rain tip count, now that rain_mm carries the rain.
HA_DIAGNOSTIC_FIELDS = DIAGNOSTIC_FIELDS | {'rain_tips'}


def discovery(cfg, names=DEFAULT_DISCOVERY):
    """Stable HA identities, one sensor per catalog field the station sends (docs/protocol-design.md section 6).
    Availability needs all three: the reading is fresh, the gateway is up, and this field is not
    null in the latest reading, so a faulted sensor shows as unavailable, never as a number."""
    root = f"weatherstation/v1/{cfg['station']}"
    result = {}
    for field in names:
        if field not in MEASURED and field not in DERIVED:
            continue
        uid = f"{cfg['station']}_{field}"
        f = BY_NAME.get(field)
        entry = {'name':LABELS[field],'unique_id':uid,'state_topic':root+'/weather',
                 'value_template':"{{ value_json.get('"+field+"') }}",
                 # Since-boot counters restart at 0 each boot; HA's total_increasing treats a decrease as a reset.
                 'state_class':('total_increasing' if f.counter else 'measurement') if f else
                                DERIVED[field].get('state_class','measurement'),
                 # .get() here and in value_template: a field the payload lacks (a pod unplugged, a build
                 # without it) is None, so the entity goes unavailable; value_json.<field> on a missing key
                 # is an undefined-variable template error in HA.
                 'availability':[{'topic':root+'/availability'},{'topic':root+'/gateway_availability'},
                                 {'topic':root+'/weather','value_template':
                                  "{{ 'online' if value_json.get('"+field+"') is not none else 'offline' }}"}],
                 'availability_mode':'all','device':ha_device(cfg)}
        unit = f.unit if f else DERIVED[field]['unit']
        ha_class = f.ha_class if f else DERIVED[field]['ha_class']
        if unit:
            entry['unit_of_measurement'] = unit
        if ha_class:
            entry['device_class'] = ha_class
        if ha_class == 'wind_direction':   # a compass angle: HA must not average 350 and 10 into 180
            entry['state_class'] = 'measurement_angle'
        if field in HA_DIAGNOSTIC_FIELDS:
            entry['entity_category'] = 'diagnostic'
        result[f'homeassistant/sensor/{uid}/config'] = entry
    return result


def mqtt_password(directory):
    """Broker password: WS_MQTT_PASSWORD if set, else the first line of <run dir>/mqtt-password.

    A file in the private run directory works the same on macOS and Linux and under any service
    manager (launchd, systemd), and stays out of gateway.json and git."""
    if os.environ.get('WS_MQTT_PASSWORD'):
        return os.environ['WS_MQTT_PASSWORD']
    path = Path(directory) / 'mqtt-password'
    if not path.exists():
        return None
    if os.name == 'posix' and path.stat().st_mode & 0o077:
        print(f'#gateway warning: {path} is readable by other users; run chmod 600 on it',
              file=sys.stderr, flush=True)
    lines = path.read_text().splitlines()
    return lines[0] if lines else ''


class MQTT:
    """Publish current snapshots only; republish discovery on broker reconnect."""
    def __init__(self,gateway):
        import paho.mqtt.client as mqtt
        self.gateway = gateway
        cfg = gateway.cfg
        self.root = f"weatherstation/v1/{cfg['station']}"
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=cfg['station']+'-gateway')
        self.client.max_queued_messages_set(100)
        self.client.will_set(self.root+'/gateway_availability','offline',qos=1,retain=True)
        settings = cfg['mqtt']
        if settings.get('username'):
            password = mqtt_password(gateway.directory)
            if password is None:   # fail at start, not as a vague broker refusal later
                raise ValueError(f"mqtt.username is set but there is no password: write it to "
                                 f"{Path(gateway.directory) / 'mqtt-password'} or set WS_MQTT_PASSWORD")
            self.client.username_pw_set(settings['username'],password)
        if settings.get('tls'):
            self.client.tls_set()
        self.client.on_connect = self.on_connect
        self.published = None   # (weather, availability, diagnostics, health availability, alerts) last sent; None forces a send
        self.published_at = 0.0
        self.advertised = set()  # catalog fields with an HA discovery entry on this connection
        self.advertised_types = set()   # module type ids with an HA discovery entry on this connection
        self.advertised_health = set()  # health report keys with an HA discovery entry on this connection
        self.advertised_alerts = set()  # alert keys with an HA discovery entry on this connection
        self.published_modules = MODULES_UNPUBLISHED
        self.client.connect_async(settings['host'],settings.get('port',1883),keepalive=30)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, reason, properties):
        if reason.is_failure:
            # A refused login or bad TLS setup must not fail silently.
            print(f'#gateway mqtt connect refused: {reason}',file=sys.stderr,flush=True)
            return
        self.advertised = set()
        self.advertised_types = set()
        self.advertised_health = set()
        self.advertised_alerts = set()
        self.published_modules = MODULES_UNPUBLISHED
        self.advertise(self.gateway.store.latest(self.gateway.cfg['station']).get('observation'))
        # Set availability from actual age before advertising a live gateway.
        self.published = None
        self.tick()
        client.publish(self.root+'/gateway_availability','online',qos=1,retain=True)

    def advertise(self, observation):
        """Discovery for the fields the newest reading carries (temperature and humidity before the first reading);
        republished when a new field appears, e.g. after a sensor is added."""
        names = {n for n in (observation or {}) if n in MEASURED} or set(DEFAULT_DISCOVERY)
        names |= {d for d, spec in DERIVED.items() if all(n in names for n in spec['needs'])}
        if names <= self.advertised:
            return
        for topic,payload in discovery(self.gateway.cfg,sorted(names - self.advertised)).items():
            self.client.publish(topic,json.dumps(payload),qos=1,retain=True)
        self.advertised |= names

    def advertise_health(self, report):
        """Discovery for the power keys the newest health report carries and this build measures (design
        section 10.2), once a connection. A key the report lists in power_not_measured gets no entity,
        as an observation field the record does not carry gets none; a fitted key that faults does."""
        report = report or {}
        unmeasured = set(report.get('power_not_measured') or ())
        keys = {k for k in report if k in HEALTH_ENTITIES and k not in unmeasured} - self.advertised_health
        for topic,payload in health_discovery(self.gateway.cfg,sorted(keys)).items():
            self.client.publish(topic,json.dumps(payload),qos=1,retain=True)
        self.advertised_health |= keys

    def advertise_alerts(self, report):
        """Discovery for the alerts, once a connection; charger_cold_hold once a health report has a value for it."""
        keys = set(ALERTS_ALWAYS) | ({'charger_cold_hold'} if (report or {}).get('charger_cold_hold') is not None else set())
        for topic,payload in alert_discovery(self.gateway.cfg,sorted(keys - self.advertised_alerts)).items():
            self.client.publish(topic,json.dumps(payload),qos=1,retain=True)
        self.advertised_alerts |= keys

    REFRESH_S = 300  # republish unchanged retained state this often (cheap keep-fresh)

    def tick(self):
        """Publish only on change (new observation or availability flip) or every REFRESH_S."""
        if not self.client.is_connected():
            return
        latest = self.gateway.store.latest(self.gateway.cfg['station'])
        self.advertise(latest.get('observation'))
        # The weather topic carries the reading plus the gateway's derived values (e.g. dew point).
        weather = json.dumps(latest['observation'] | latest.get('derived', {})) if latest.get('observation') else None
        diag = self.gateway.store.latest_diagnostic(self.gateway.cfg['station'])
        self.advertise_health(diag)
        self.advertise_alerts(diag)
        now = time.time()
        health = 'online' if health_fresh(diag, now) else 'offline'
        alert = json.dumps(alerts(latest, diag, self.gateway.receiver_silent(now), now), sort_keys=True)
        alarm = self.gateway.counter_alarm()
        if diag or alarm['alarm']:
            diag = (diag or {}) | alarm  # key-reuse alarm rides on the diagnostics topic
        set_alarms = self.gateway.descriptor_set_alarms()
        if set_alarms:                   # so do descriptor-set conflicts and failed checks (WSMP-E6, E7)
            diag = (diag or {}) | {'descriptor_set_alarms': set_alarms}
        diagnostics = json.dumps(diag,sort_keys=True) if diag else None
        state = (weather, 'online' if latest['available'] else 'offline', diagnostics, health, alert)
        if state == self.published and time.time() - self.published_at < self.REFRESH_S:
            self.publish_modules()   # on change only, independent of the weather's publish cadence
            return
        if weather:
            self.client.publish(self.root+'/weather',weather,qos=1,retain=True)
        if diagnostics:
            self.client.publish(self.root+'/diagnostics',diagnostics,qos=1,retain=True)
        self.client.publish(self.root+'/availability',state[1],qos=1,retain=True)
        self.client.publish(self.root+'/diagnostics/availability',health,qos=1,retain=True)
        self.client.publish(self.root+'/alerts',alert,qos=1,retain=True)
        self.published, self.published_at = state, time.time()
        self.publish_modules()

    def publish_modules(self):
        """The current descriptor set's module identities (retained), with discovery for new type ids.
        A current set with no module publishes {}. Without a current set, an empty retained message
        clears …/modules (once), so a stale payload from an earlier run never stays."""
        modules = self.gateway.modules()
        if modules == self.published_modules:
            return
        if modules is None:
            self.client.publish(self.root+'/modules','',qos=1,retain=True)
            self.published_modules = None
            return
        for topic,payload in module_discovery(self.gateway.cfg,sorted(set(modules) - self.advertised_types),
                                              self.root).items():
            self.client.publish(topic,json.dumps(payload),qos=1,retain=True)
        self.advertised_types |= set(modules)
        self.client.publish(self.root+'/modules',json.dumps(modules,sort_keys=True),qos=1,retain=True)
        self.published_modules = modules

    def close(self):
        # Best effort: wait_for_publish raises (RuntimeError, ValueError) if the connection drops
        # meanwhile; shutdown must still disconnect and stop the network thread.
        try:
            if self.client.is_connected():
                self.client.publish(self.root+'/gateway_availability','offline',qos=1,retain=True).wait_for_publish(timeout=2)
        except (RuntimeError, ValueError, OSError):
            pass
        finally:
            self.client.disconnect()
            self.client.loop_stop()
