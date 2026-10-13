"""Single-process gateway: authenticated frames, SQLite, read-only HTTP and MQTT."""
import csv
import hmac
import io
import json
import os
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from gateway import Store
import struct
from .protocol import (ACK, KIND_NACK, NACK, NACK_COLLISION, NACK_INVALID, Nonces,
                       decode_observation, frame_counter, seal, unseal)


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


class Gateway:
    """The sole ACK authority is the host after durable database commit."""
    def __init__(self, cfg, directory):
        self.cfg, self.directory = cfg, directory
        self.key = bytes.fromhex(cfg['radio_key'])
        self.store = Store(directory / 'observations.sqlite3')
        self.nonces = Nonces(directory / 'gateway-nonces.sqlite3',self.key,cfg['station_id'],2)
        self.accepted = self.rejected = self.nacked = 0
        self.clock = None  # ws0.clock.HostClock when serving hardware (gap G9); None = trust host
        self.lock = threading.Lock()

    def receive(self, frame, now=None):
        """Authenticate, validate and commit before returning an encrypted receipt."""
        with self.lock:
            try:
                payload = unseal(self.key,self.cfg['station_id'],1,frame)
            except Exception:
                self.rejected += 1  # unauthenticated: never answered (a NACK would let anyone drop data)
                raise
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
                return ack
            except Exception:
                self.rejected += 1
                raise

    def status(self):
        """Expose no credentials or raw keys in diagnostics."""
        return {'stage':0,'h01':'NOT RUN','mode':self.cfg['mode'],
                'station':self.cfg['station'],'accepted_this_process':self.accepted,
                'rejected_this_process':self.rejected,'nacked_this_process':self.nacked,
                'host_clock':self.clock.status() if self.clock else None,
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
            self.client.username_pw_set(settings['username'],os.environ.get('WS_MQTT_PASSWORD'))
        if settings.get('tls'):
            self.client.tls_set()
        self.client.on_connect = self.on_connect
        self.published = None   # (weather payload, availability) last sent; None forces a send
        self.published_at = 0.0
        self.client.connect_async(settings['host'],settings.get('port',1883),keepalive=30)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, reason, properties):
        if reason.is_failure:
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
        if state == self.published and time.time() - self.published_at < self.REFRESH_S:
            return
        if weather:
            self.client.publish(self.root+'/weather',weather,qos=1,retain=True)
        self.client.publish(self.root+'/availability',state[1],qos=1,retain=True)
        self.published, self.published_at = state, time.time()

    def close(self):
        if self.client.is_connected():
            self.client.publish(self.root+'/gateway_availability','offline',qos=1,retain=True).wait_for_publish(timeout=2)
        self.client.disconnect()
        self.client.loop_stop()
