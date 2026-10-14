"""Single-process gateway: authenticated frames, SQLite, read-only HTTP and MQTT."""
import csv
import hmac
import io
import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from gateway import Store
import struct
from .protocol import (ACK, DIAG, KIND_DIAG, KIND_NACK, LINK_STATES, NACK, NACK_COLLISION, NACK_INVALID,
                       RESET_CAUSES, Nonces, decode_observation, frame_counter, seal, unseal)


def load_config(path):
    """Load secrets locally; bind the diagnostic API to loopback only."""
    cfg = json.loads(path.read_text())
    if not isinstance(cfg.get('station'), str) or not cfg['station'].replace('-','').isalnum():
        raise ValueError('Invalid station name')
    if type(cfg.get('station_id')) is not int or not 1 <= cfg['station_id'] < 2**32:
        raise ValueError('Invalid numeric station ID')
    if len(bytes.fromhex(cfg['radio_key'])) != 16 or len(cfg['api_token']) < 32:
        raise ValueError('Invalid key/token')
    return cfg


KEY_REUSE_ALARM = 'possible key reuse: re-key the node'


class CounterRegression(ValueError):
    """An authentic node frame whose counter is at or below the stored high-water mark: a
    replay, or the node sealing under a nonce it has already used (key reuse, C7-C9)."""


class Gateway:
    """The sole ACK authority is the host after durable database commit."""
    def __init__(self, cfg, directory):
        self.cfg, self.directory = cfg, directory
        self.key = bytes.fromhex(cfg['radio_key'])
        self.store = Store(directory / 'observations.sqlite3')
        self.nonces = Nonces(directory / 'gateway-nonces.sqlite3',self.key,cfg['station_id'],2)
        self.accepted = self.rejected = self.nacked = 0
        self.node_counter = self.nonces.node_counter()  # cached for the HTTP/MQTT threads
        self.clock = None  # ws0.clock.HostClock when serving hardware (gap G9); None = trust host
        self.receiver = None  # RX board liveness, set by the serial loop (gap G12)
        self.last_ingested = None  # the observation in the frame just ACKed, for the serve log
        self.lock = threading.Lock()

    def check_counter(self, frame, payload, now, sequence):
        """Review item P4. Every node transmission, retries included, gets a fresh, strictly
        increasing counter from one space shared by OBS and DIAG (firmware store_next_counter;
        WIPE keeps it), so an authentic frame at or below the mark is a replay or nonce reuse.
        It is never answered or stored as data; the raw frame is kept as a rejection."""
        counter = frame_counter(frame)
        received = time.time() if now is None else now
        fresh = self.nonces.advance_node_counter(counter,received)
        self.node_counter = self.nonces.node_counter()
        if fresh:
            return
        epoch = struct.unpack('>I',payload[:4])[0]
        detail = (f"counter {counter} <= high-water mark {self.node_counter['max_node_counter']}: "
                  + KEY_REUSE_ALARM)
        self.store.reject(self.cfg['station'],str(epoch),sequence,'counter_regression',detail,frame.hex(),now)
        self.rejected += 1
        raise CounterRegression(detail)

    def receive_diagnostic(self, frame, now=None):
        """Node health report (kind 4): authenticate and store; never answered."""
        payload = unseal(self.key,self.cfg['station_id'],KIND_DIAG,frame)
        self.check_counter(frame,payload,now,None)
        epoch, uptime, pending, lost, burned, abandoned, no_ack, rejects, reset, link = DIAG.unpack(payload)
        report = {'epoch':epoch,'uptime_s':uptime,'journal_pending':pending,'journal_lost_total':lost,
                  'journal_torn_slots':burned,'abandoned_total':abandoned,'missed_acks_since_boot':no_ack,
                  'rejected_replies_since_boot':rejects,
                  'reset_cause':RESET_CAUSES[reset] if reset < len(RESET_CAUSES) else 'unknown',
                  'link':LINK_STATES[link] if link < len(LINK_STATES) else 'unknown'}
        self.store.diagnostic(self.cfg['station'],report,now)
        return report

    def receive(self, frame, now=None):
        """Authenticate, validate and commit before returning an encrypted receipt."""
        with self.lock:
            if len(frame) > 3 and frame[3] == KIND_DIAG:
                self.receive_diagnostic(frame,now)
                return None  # fire-and-forget: no reply on air
            try:
                payload = unseal(self.key,self.cfg['station_id'],1,frame)
            except Exception:
                self.rejected += 1  # unauthenticated: never answered (a NACK would let anyone drop data)
                raise
            # Raised durably before the commit, so a crash cannot leave it below this frame.
            self.check_counter(frame,payload,now,struct.unpack('>I',payload[4:8])[0])
            try:
                record = decode_observation(payload,self.cfg['station'])
                inserted = self.store.ingest(record,now)
            except ValueError as exc:
                # Authentic but permanently unacceptable: record it, then tell the node to stop
                # retrying it (gap G2). Commit failures (OSError) still propagate with no reply.
                reason = NACK_COLLISION if str(exc) == 'Identity collision' else NACK_INVALID
                epoch, sequence = struct.unpack('>II',payload[:8])
                self.store.reject(self.cfg['station'],str(epoch),sequence,
                                  'identity_collision' if reason == NACK_COLLISION else 'invalid_record',
                                  str(exc),frame.hex(),now)
                self.rejected += 1
                self.nacked += 1
                return seal(self.key,self.cfg['station_id'],KIND_NACK,self.nonces,
                            NACK.pack(epoch,sequence,reason,0,frame_counter(frame)))
            except OSError:
                self.rejected += 1  # commit failed: no ACK, the node keeps the record
                raise
            try:
                # Host UTC rides in the authenticated ACK: the node's only time source. A host
                # clock measured as wrong sends 0 instead: the node then keeps its own clock (G9).
                host_utc = int(time.time() if now is None else now)
                if self.clock and not self.clock.may_issue_time():
                    host_utc = 0
                ack = seal(self.key,self.cfg['station_id'],2,self.nonces,
                           ACK.pack(int(record['session']),record['sequence'],host_utc,
                                    frame_counter(frame)))
                self.accepted += int(inserted)
                self.last_ingested = dict(record,duplicate=not inserted)
                return ack
            except Exception:
                self.rejected += 1
                raise

    def counter_alarm(self):
        """Key-reuse alarm (P4). It persists across restarts; the cure is a new key, i.e. a new
        state directory (runbook R5), which starts with a fresh mark."""
        state = self.node_counter
        return {'alarm':KEY_REUSE_ALARM if state['counter_regression'] else None,
                'counter_regression':state['counter_regression'],
                'last_regression_counter':state['last_regression_counter']}

    def status(self):
        """Expose no credentials or raw keys in diagnostics."""
        return {'stage':0,'h01':'NOT RUN','mode':self.cfg['mode'],
                'alarm':self.counter_alarm()['alarm'],'node_counter':dict(self.node_counter),
                'station':self.cfg['station'],'accepted_this_process':self.accepted,
                'rejected_this_process':self.rejected,'nacked_this_process':self.nacked,
                'host_clock':self.clock.status() if self.clock else None,
                'node_diagnostics':self.store.latest_diagnostic(self.cfg['station']),
                'receiver':self.receiver,
                'latest':self.store.latest(self.cfg['station'])}


def utc_filter(text, default):
    """History filters use timezone-aware ISO-8601 values, never local naive time."""
    if text is None:
        return default
    value = datetime.fromisoformat(text.replace('Z','+00:00'))
    if value.tzinfo is None:
        raise ValueError('UTC filter requires timezone')
    return value.timestamp()


def http_server(gateway, port):
    """All endpoints require a bearer token; HTTP cannot inject observations."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Avoid recording credentials or query strings in access logs.

        def do_GET(self):
            supplied = self.headers.get('Authorization','')
            expected = 'Bearer ' + gateway.cfg['api_token']
            if not hmac.compare_digest(supplied.encode(),expected.encode()):
                self.reply(401,{'error':'unauthorized'})
                return
            url = urlparse(self.path)
            query = parse_qs(url.query)
            try:
                if url.path == '/v1/status':
                    result = gateway.status()
                elif url.path == '/v1/observations/latest':
                    result = gateway.store.latest(gateway.cfg['station'])
                elif url.path == '/v1/observations':
                    limit = int(query.get('limit',['100'])[0])
                    offset = int(query.get('offset',['0'])[0])
                    start = utc_filter(query.get('from',[None])[0],0)
                    end = utc_filter(query.get('to',[None])[0],253402300800)
                    if not 1 <= limit <= 1000 or offset < 0 or end < start:
                        raise ValueError('Invalid pagination/time range')
                    rows = gateway.store.history(gateway.cfg['station'],start,end,limit,offset)
                    if query.get('format',['json'])[0] == 'csv':
                        stream = io.StringIO()
                        fields = ['station','session','sequence','sampled_at','received_at',
                                  'temperature_c','humidity_pct','quality','time_quality',
                                  'effective_sampled_at','time_basis','time_uncertainty_s','uptime_s']
                        writer = csv.DictWriter(stream,fields,extrasaction='ignore')
                        writer.writeheader()
                        writer.writerows(rows)
                        self.reply(200,stream.getvalue(),'text/csv')
                        return
                    result = {'observations':rows,'offset':offset,'limit':limit,
                              'units':{'temperature_c':'°C','humidity_pct':'%','sampled_at':'unix_seconds_UTC'}}
                else:
                    self.reply(404,{'error':'not_found'})
                    return
                self.reply(200,result)
            except (ValueError,OverflowError) as exc:
                self.reply(400,{'error':str(exc)})

        def reply(self, code, body, content_type='application/json'):
            data = (json.dumps(body,allow_nan=False) if content_type=='application/json' else body).encode()
            self.send_response(code)
            self.send_header('Content-Type',content_type+'; charset=utf-8')
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            self.wfile.write(data)
    server = ThreadingHTTPServer(('127.0.0.1',port),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server


def discovery(cfg):
    """Stable HA identities with both gateway and measurement availability."""
    root = f"weatherstation/v1/{cfg['station']}"
    result = {}
    for field, label, unit, device_class in [('temperature_c','Temperature','°C','temperature'),
                                            ('humidity_pct','Humidity','%','humidity')]:
        uid = f"{cfg['station']}_{field}"
        result[f'homeassistant/sensor/{uid}/config'] = {
            'name':label,'unique_id':uid,'state_topic':root+'/weather',
            'value_template':'{{ value_json.'+field+' }}','unit_of_measurement':unit,
            'device_class':device_class,'state_class':'measurement',
            'availability':[{'topic':root+'/availability'},{'topic':root+'/gateway_availability'}],
            'availability_mode':'all',
            'device':{'identifiers':[cfg['station']],'name':cfg['station'],
                      'manufacturer':'Weather Station Project','model':'Stage 0 '+cfg['mode']}}
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
            self.client.username_pw_set(settings['username'],mqtt_password(gateway.directory))
        if settings.get('tls'):
            self.client.tls_set()
        self.client.on_connect = self.on_connect
        self.published = None   # (weather payload, availability) last sent; None forces a send
        self.published_at = 0.0
        self.client.connect_async(settings['host'],settings.get('port',1883),keepalive=30)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, reason, properties):
        if reason.is_failure:
            # A refused login or bad TLS setup must not fail silently.
            print(f'#gateway mqtt connect refused: {reason}',file=sys.stderr,flush=True)
            return
        for topic,payload in discovery(self.gateway.cfg).items():
            client.publish(topic,json.dumps(payload),qos=1,retain=True)
        # Set availability from actual age before advertising a live gateway.
        self.published = None
        self.tick()
        client.publish(self.root+'/gateway_availability','online',qos=1,retain=True)

    REFRESH_S = 300  # republish unchanged retained state this often (cheap keep-fresh)

    def tick(self):
        """Publish only on change (new observation or availability flip) or every REFRESH_S."""
        if not self.client.is_connected():
            return
        latest = self.gateway.store.latest(self.gateway.cfg['station'])
        weather = json.dumps(latest['observation']) if latest.get('observation') else None
        state = (weather, 'online' if latest['available'] else 'offline')
        diag = self.gateway.store.latest_diagnostic(self.gateway.cfg['station'])
        alarm = self.gateway.counter_alarm()
        if diag or alarm['alarm']:
            diag = (diag or {}) | alarm  # key-reuse alarm (P4) rides on the diagnostics topic
        diagnostics = json.dumps(diag,sort_keys=True) if diag else None
        state = state + (diagnostics,)
        if state == self.published and time.time() - self.published_at < self.REFRESH_S:
            return
        if weather:
            self.client.publish(self.root+'/weather',weather,qos=1,retain=True)
        if diagnostics:
            self.client.publish(self.root+'/diagnostics',diagnostics,qos=1,retain=True)
        self.client.publish(self.root+'/availability',state[1],qos=1,retain=True)
        self.published, self.published_at = state, time.time()

    def close(self):
        if self.client.is_connected():
            self.client.publish(self.root+'/gateway_availability','offline',qos=1,retain=True).wait_for_publish(timeout=2)
        self.client.disconnect()
        self.client.loop_stop()
