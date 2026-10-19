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
from gateway import Store
from . import web
import sqlite3
import struct
from .fields import BY_NAME, DERIVED, DIAGNOSTIC_FIELDS, ENERGY, LABELS, MEASURED
from .protocol import (KEY_LEN, SIGNAL_NONE, DIAG, KIND_ACK, KIND_DIAG, KIND_NACK, KIND_OBS, LINK_STATES, NACK_COLLISION, NACK_INVALID,
                       RESET_CAUSES, STATION_MAX, Nonces, decode_observation, frame_counter, frame_kind, pack_reply, seal,
                       unseal)


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


class CounterRegression(ValueError):
    """An authentic node frame whose counter is at or below the stored high-water mark and whose
    bytes differ from (or were never seen as) the frame accepted under that counter: the node
    sealed under a nonce it already used (key reuse)."""


class Replay(ValueError):
    """An exact copy of a node frame already accepted (radio duplicate or a recorded frame played
    back). Harmless: never answered or stored as data, counted, and no key-reuse alarm."""


class Gateway:
    """The sole ACK authority is the host after durable database commit."""
    def __init__(self, cfg, directory):
        self.cfg, self.directory = cfg, directory
        self.key = bytes.fromhex(cfg['radio_key'])
        self.store = Store(directory / 'observations.sqlite3')
        self.nonces = Nonces(directory / 'gateway-nonces.sqlite3',self.key,cfg['station_id'],KIND_ACK)
        self.accepted = self.rejected = self.nacked = 0
        self.node_counter = self.nonces.node_counter()  # cached for the HTTP/MQTT threads
        self.clock = None  # ws0.clock.HostClock when serving hardware; None = trust host
        self.receiver = None  # RX board liveness, set by the serial loop
        self.last_ingested = None  # the observation in the frame just ACKed, for the serve log
        self.last_outcome = None   # what receive() did with the last frame: ack, duplicate, nack, diag
        self.lock = threading.Lock()
        self.hub = web.EventHub()  # live events for the dashboard stream (GET /v1/events)
        self.telemetry = web.Telemetry(self)

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
        (epoch, uptime, pending, lost, burned, abandoned, no_ack, rejects, reset, link,
         build, rssi, snr, crashes, energy) = DIAG.unpack(payload)
        report = {'epoch':epoch,'uptime_s':uptime,'journal_pending':pending,'journal_lost_total':lost,
                  'journal_torn_slots':burned,'abandoned_total':abandoned,'missed_acks_since_boot':no_ack,
                  'rejected_replies_since_boot':rejects,
                  'reset_cause':RESET_CAUSES[reset] if reset < len(RESET_CAUSES) else 'unknown',
                  'link':LINK_STATES[link] if link < len(LINK_STATES) else 'unknown',
                  'firmware_build':f'{build:08x}','ack_rssi_dbm':None if rssi == SIGNAL_NONE else rssi,
                  'ack_snr_db':None if snr == SIGNAL_NONE else snr,'crashes_since_power_up':crashes,
                  'energy_state':ENERGY[energy] if energy < len(ENERGY) else 'unknown'}
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

    def counter_alarm(self):
        """Key-reuse alarm. It persists across restarts; the cure is a new key, i.e. a new
        state directory (re-key procedure, docs/failure-modes.md §9.5), which starts with a fresh mark."""
        state = self.node_counter
        return {'alarm':KEY_REUSE_ALARM if state['counter_regression'] else None,
                'counter_regression':state['counter_regression'],
                'last_regression_counter':state['last_regression_counter']}

    def close(self):
        self.store.db.close()
        self.nonces.db.close()

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


DEFAULT_DISCOVERY = ('temperature_c','humidity_pct')   # advertised before the first reading


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
                 'value_template':'{{ value_json.'+field+' }}',
                 # Since-boot counters restart at 0 each boot; HA's total_increasing treats a decrease as a reset.
                 'state_class':'total_increasing' if f and f.counter else 'measurement',
                 'availability':[{'topic':root+'/availability'},{'topic':root+'/gateway_availability'},
                                 {'topic':root+'/weather','value_template':
                                  "{{ 'online' if value_json."+field+" is not none else 'offline' }}"}],
                 'availability_mode':'all',
                 'device':{'identifiers':[cfg['station']],'name':cfg['station'],
                           'manufacturer':'Weather Station Project','model':'Stage 0 '+cfg['mode']}}
        unit = f.unit if f else DERIVED[field]['unit']
        ha_class = f.ha_class if f else DERIVED[field]['ha_class']
        if unit:
            entry['unit_of_measurement'] = unit
        if ha_class:
            entry['device_class'] = ha_class
        if field in DIAGNOSTIC_FIELDS:
            entry['entity_category'] = 'diagnostic'
        result[f'homeassistant/sensor/{uid}/config'] = entry
    return result


def mqtt_password(directory):
    """Broker password: WS_MQTT_PASSWORD if set, else the first line of <run dir>/mqtt-password.

    A file in the private run directory works the same on macOS, Linux and Windows and under any
    service manager (launchd, systemd, Task Scheduler), and stays out of gateway.json and git."""
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
        self.published = None   # (weather payload, availability) last sent; None forces a send
        self.published_at = 0.0
        self.advertised = set()  # catalog fields with an HA discovery entry on this connection
        self.client.connect_async(settings['host'],settings.get('port',1883),keepalive=30)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, reason, properties):
        if reason.is_failure:
            # A refused login or bad TLS setup must not fail silently.
            print(f'#gateway mqtt connect refused: {reason}',file=sys.stderr,flush=True)
            return
        self.advertised = set()
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
        alarm = self.gateway.counter_alarm()
        if diag or alarm['alarm']:
            diag = (diag or {}) | alarm  # key-reuse alarm rides on the diagnostics topic
        diagnostics = json.dumps(diag,sort_keys=True) if diag else None
        state = (weather, 'online' if latest['available'] else 'offline', diagnostics)
        if state == self.published and time.time() - self.published_at < self.REFRESH_S:
            return
        if weather:
            self.client.publish(self.root+'/weather',weather,qos=1,retain=True)
        if diagnostics:
            self.client.publish(self.root+'/diagnostics',diagnostics,qos=1,retain=True)
        self.client.publish(self.root+'/availability',state[1],qos=1,retain=True)
        self.published, self.published_at = state, time.time()

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
