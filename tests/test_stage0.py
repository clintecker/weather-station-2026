"""Failure tests; accelerated records are not physical H01 evidence."""
import ctypes
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from cryptography.exceptions import InvalidTag
from ws0.__main__ import provision
from ws0.protocol import Nonces,OBS,unseal
from ws0.service import Gateway,discovery,http_server,load_config
from ws0.simulator import Node

class PipelineTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/'state'
  provision(self.root); self.cfg=load_config(self.root/'gateway.json')
  self.gateway=Gateway(self.cfg,self.root); self.node=Node(self.cfg,self.root)
 def tearDown(self):
  for db in (self.gateway.store.db,self.gateway.nonces.db,self.node.db,self.node.nonces.db): db.close()
  self.tmp.cleanup()
 def test_commit_ack_replay(self):
  frame=self.node.packet(self.node.sample(1000)); ack=self.gateway.receive(frame,1001)
  self.node.acknowledge(ack); self.assertEqual(self.node.backfill(),[])
  self.gateway.receive(frame,1100)
  self.assertEqual(len(self.gateway.store.history(self.cfg['station'])),1)
  self.assertEqual(self.gateway.store.latest(self.cfg['station'],1100)['received_at'],1001)
 def test_tamper_key_direction(self):
  frame=self.node.packet(self.node.sample(1000))
  with self.assertRaises(InvalidTag): self.gateway.receive(frame[:-1]+bytes([frame[-1]^1]))
  with self.assertRaises(InvalidTag): unseal(b'x'*16,1,1,frame)
  with self.assertRaises(ValueError): self.node.acknowledge(frame)
  self.assertEqual(self.gateway.store.history(self.cfg['station']),[])
 def test_commit_failure_no_ack(self):
  frame=self.node.packet(self.node.sample(1000)); old=self.gateway.store.ingest
  self.gateway.store.ingest=lambda *a: (_ for _ in ()).throw(OSError('disk full'))
  with self.assertRaises(OSError): self.gateway.receive(frame)
  self.assertEqual(len(self.node.backfill()),1); self.gateway.store.ingest=old
 def test_nonce_restart_and_missing_state(self):
  record=self.node.sample(1000); first=self.node.packet(record); self.node.nonces.db.close()
  self.node.nonces=Nonces(self.root/'node-nonces.sqlite3',self.node.key,1,1)
  self.assertNotEqual(first,self.node.packet(record))
  with self.assertRaises(ValueError): Nonces(self.root/'missing.sqlite3',self.node.key,1,1)
 def test_fault_unknown_recovery(self):
  for stamp,fault in [(1000,False),(1060,True)]:
   self.gateway.receive(self.node.packet(self.node.sample(stamp,fault)),stamp)
  self.assertFalse(self.gateway.store.latest(self.cfg['station'],1061)['available'])
  r=self.node.sample(1120); r['sampled_at']=None; r['time_quality']='unknown'
  self.gateway.receive(self.node.packet(r),1120)
  self.assertFalse(self.gateway.store.latest(self.cfg['station'],1121)['available'])
  self.gateway.receive(self.node.packet(self.node.sample(1180)),1180)
  self.assertTrue(self.gateway.store.latest(self.cfg['station'],1181)['available'])
 def test_outage_restart_backfill_stale(self):
  for stamp in (1000,1060,1120): self.node.sample(stamp)
  self.node.db.close(); self.node.nonces.db.close(); self.node=Node(self.cfg,self.root)
  self.node.acknowledge(self.gateway.receive(self.node.packet(self.node.sample(1300)),1301))
  for r in self.node.backfill(10): self.node.acknowledge(self.gateway.receive(self.node.packet(r),1302))
  self.assertEqual(len(self.gateway.store.history(self.cfg['station'])),4)
  self.assertEqual(self.gateway.store.latest(self.cfg['station'],1303)['observation']['sampled_at'],1300)
  self.assertFalse(self.gateway.store.latest(self.cfg['station'],1480)['available'])
  self.assertEqual(self.node.backfill(),[])
 def test_accelerated_1440_records(self):
  for i in range(1440):
   now=100000+i*60
   self.node.acknowledge(self.gateway.receive(self.node.packet(self.node.sample(now)),now+1))
  self.assertEqual(len(self.gateway.store.history(self.cfg['station'],limit=2000)),1440)
  self.assertEqual(self.node.backfill(),[])
 def test_http_auth_csv_pagination(self):
  self.gateway.receive(self.node.packet(self.node.sample(1000)),1001)
  server=http_server(self.gateway,0); base=f'http://127.0.0.1:{server.server_port}'
  def get(path,auth=True):
   return urlopen(Request(base+path,headers={'Authorization':'Bearer '+self.cfg['api_token']} if auth else {}))
  try:
   with self.assertRaises(HTTPError) as exc: get('/v1/status',False)
   self.assertEqual(exc.exception.code,401)
   with get('/v1/observations?limit=1') as r: self.assertEqual(len(json.load(r)['observations']),1)
   with get('/v1/observations?format=csv') as r: self.assertIn('temperature_c',r.read().decode())
   with self.assertRaises(HTTPError): get('/v1/observations?limit=1001')
   with get('/v1/status') as r: self.assertNotIn('radio_key',r.read().decode())
  finally: server.shutdown(); server.server_close()
 def test_ha_discovery(self):
  entries=discovery(self.cfg); self.assertEqual(len(entries),2)
  for entry in entries.values():
   self.assertEqual(entry['availability_mode'],'all'); self.assertEqual(len(entry['availability']),2)

class FirmwareTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(); path=Path(cls.tmp.name)/'stage0.so'
  subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC','firmware/stage0.c','-o',str(path)],check=True)
  cls.lib=ctypes.CDLL(str(path))
  cls.lib.ws_pack_observation.argtypes=[ctypes.POINTER(ctypes.c_uint8),ctypes.c_uint32,ctypes.c_uint32,ctypes.c_uint64,ctypes.c_int16,ctypes.c_uint16,ctypes.c_uint8,ctypes.c_uint8]
  cls.lib.ws_crc8.argtypes=[ctypes.POINTER(ctypes.c_uint8),ctypes.c_size_t]; cls.lib.ws_crc8.restype=ctypes.c_uint8
 @classmethod
 def tearDownClass(cls): cls.tmp.cleanup()
 def test_c_python_wire(self):
  for valid in (0,1):
   for timed in (0,1):
    output=(ctypes.c_uint8*24)()
    self.lib.ws_pack_observation(output,17,42,100000,-1234,4567,valid,timed)
    self.assertEqual(bytes(output),OBS.pack(17,42,100000 if timed else 0,-1234 if valid else 0,4567 if valid else 0,valid,timed,0))
 def test_sensirion_crc(self):
  self.assertEqual(self.lib.ws_crc8((ctypes.c_uint8*2)(0xbe,0xef),2),0x92)

class AdditionalFailures(unittest.TestCase):
 setUp=PipelineTests.setUp
 tearDown=PipelineTests.tearDown
 # Reuse fixture setup without duplicating inherited test execution below.
 def test_clock_quarantine_and_corrected_clock(self):
  self.gateway.receive(self.node.packet(self.node.sample(2000)),1000)
  self.assertFalse(self.gateway.store.latest(self.cfg['station'],2001)['available'])
  self.gateway.receive(self.node.packet(self.node.sample(1060)),1061)
  self.assertTrue(self.gateway.store.latest(self.cfg['station'],1062)['available'])
 def test_ack_tamper_keeps_pending(self):
  ack=self.gateway.receive(self.node.packet(self.node.sample(1000)),1001)
  with self.assertRaises(InvalidTag): self.node.acknowledge(ack[:-1]+bytes([ack[-1]^1]))
  self.assertEqual(len(self.node.backfill()),1)

class SensorBusTests(unittest.TestCase):
 def test_bus_failures_crc_and_conversion(self):
  with tempfile.TemporaryDirectory() as temp:
   exe=str(Path(temp)/'sensor-test')
   subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','firmware/stage0.c','firmware/test_sensor.c','-o',exe],check=True)
   subprocess.run([exe],check=True)

class ServiceSmokeTests(unittest.TestCase):
 def test_cli_demo_starts_and_persists(self):
  import socket,sys,time
  with tempfile.TemporaryDirectory() as tmp:
   directory=Path(tmp)/'state'; provision(directory)
   cfg=json.loads((directory/'gateway.json').read_text())
   with socket.socket() as sock:
    sock.bind(('127.0.0.1',0)); cfg['http_port']=sock.getsockname()[1]
   (directory/'gateway.json').write_text(json.dumps(cfg))
   proc=subprocess.Popen([sys.executable,'-m','ws0','demo','--directory',str(directory)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   try:
    self.assertIn(b'Stage 0 simulation',proc.stdout.readline())
    line=json.loads(proc.stdout.readline()); self.assertTrue(line['simulation'])
    req=Request(f"http://127.0.0.1:{cfg['http_port']}/v1/status",headers={'Authorization':'Bearer '+cfg['api_token']})
    with urlopen(req,timeout=3) as response:
     status=json.load(response); self.assertTrue(status['latest']['available'])
     self.assertEqual(status['h01'],'NOT RUN')
   finally:
    import signal
    proc.send_signal(signal.SIGINT); proc.communicate(timeout=5)
   self.assertEqual(proc.returncode,0)

 def test_mqtt_stale_payload_and_availability(self):
  from unittest.mock import patch
  from ws0.service import MQTT
  from gateway import Store
  class Fake:
   def __init__(self): self.messages=[]
   def is_connected(self): return True
   def publish(self,*a,**kw): self.messages.append((a,kw))
  with tempfile.TemporaryDirectory() as tmp:
   directory=Path(tmp)/'state'; provision(directory); cfg=load_config(directory/'gateway.json')
   gateway=Gateway(cfg,directory); node=Node(cfg,directory)
   try:
    gateway.receive(node.packet(node.sample(1000)),1001)
    publisher=object.__new__(MQTT); publisher.gateway=gateway
    publisher.root='weatherstation/v1/simulation-01'; publisher.client=Fake()
    with patch('gateway.time.time',return_value=1180): publisher.tick()
    self.assertEqual(publisher.client.messages[-1][0][1],'offline')
    self.assertEqual(json.loads(publisher.client.messages[0][0][1])['sampled_at'],1000)
   finally:
    for db in (gateway.store.db,gateway.nonces.db,node.db,node.nonces.db): db.close()
