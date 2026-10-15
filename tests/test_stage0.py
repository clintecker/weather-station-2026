"""Failure tests; accelerated records are not physical H01 evidence."""
import json
import subprocess
import sys
import tempfile
import unittest
try:                                        # first: sets WS0_UNSAFE_FAST_FSYNC before ws0 is imported
    from toolchain import SAN, CC_STRICT, Station, StationTest, host_library, needs_cc, quiet_provision
except ImportError:
    from tests.toolchain import SAN, CC_STRICT, Station, StationTest, host_library, needs_cc, quiet_provision
import ctypes
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from cryptography.exceptions import InvalidTag
from ws0.protocol import Nonces,unseal
from ws0.service import MQTT,Replay,discovery,http_server
from ws0.simulator import Node


def fake_mqtt(gateway):
 """An MQTT publisher for gateway whose client records publish() calls instead of sending."""
 class Fake:
  def __init__(self): self.messages=[]
  def is_connected(self): return True
  def publish(self,*a,**kw): self.messages.append((a,kw))
 publisher=object.__new__(MQTT); publisher.gateway=gateway; publisher.client=Fake()
 publisher.root='weatherstation/v1/simulation-01'; publisher.published=None; publisher.published_at=0.0
 publisher.advertised={'temperature_c','humidity_pct','dew_point_c'}
 return publisher


def start_demo(tmp):
 """`python -m ws0 demo` on a fresh station in tmp, on a free HTTP port: (process, config)."""
 import socket
 directory=Path(tmp)/'state'; quiet_provision(directory)
 cfg=json.loads((directory/'gateway.json').read_text())
 with socket.socket() as sock:
  sock.bind(('127.0.0.1',0)); cfg['http_port']=sock.getsockname()[1]
 (directory/'gateway.json').write_text(json.dumps(cfg))
 # Windows has no SIGINT for another process: run it in its own group and send Ctrl-Break,
 # which the gateway treats like Ctrl-C (ws0/__main__.py).
 windows=sys.platform=='win32'
 proc=subprocess.Popen([sys.executable,'-m','ws0','demo','--directory',str(directory)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                       creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if windows else 0)
 return proc,cfg


# Most tests are not about the boot clock: StationTest starts from a node that already has time.
# Boot-time reconstruction (draft 4) has its own tests in TimeReconstruction.
class PipelineTests(StationTest):
 def test_commit_ack_replay(self):
  frame=self.node.packet(self.node.sample(1000)); ack=self.gateway.receive(frame,1001)
  self.node.acknowledge(ack); self.assertEqual(self.node.backfill(),[])
  # A replayed frame repeats a counter the gateway already accepted: no reply, nothing stored,
  # and no key-reuse alarm (identical bytes, so no nonce was reused).
  with self.assertRaises(Replay): self.gateway.receive(frame,1100)
  self.assertIsNone(self.gateway.status()['alarm'])
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
  # An unknown-clock sample in an epoch with an earlier trusted reference is reconstructed
  # from the monotonic uptime (draft 4), so it is correctly current.
  r=self.node.sample(1120); r['sampled_at']=None; r['time_quality']='unknown'
  self.gateway.receive(self.node.packet(r),1120)
  latest=self.gateway.store.latest(self.cfg['station'],1121)
  self.assertTrue(latest['available']); self.assertEqual(latest['time_basis'],'reconstructed')
  self.assertEqual(latest['effective_sampled_at'],1120)
  self.gateway.receive(self.node.packet(self.node.sample(1180)),1180)
  self.assertTrue(self.gateway.store.latest(self.cfg['station'],1181)['available'])
 def test_outage_restart_backfill_stale(self):
  for stamp in (1000,1060,1120): self.node.sample(stamp)
  self.node.db.close(); self.node.nonces.db.close(); self.node=Node(self.cfg,self.root)
  # The restarted node has no clock: its first sample is time-unknown until the next one.
  self.node.acknowledge(self.gateway.receive(self.node.packet(self.node.sample(1300)),1301))
  for r in self.node.backfill(10): self.node.acknowledge(self.gateway.receive(self.node.packet(r),1302))
  self.assertEqual(len(self.gateway.store.history(self.cfg['station'])),3)  # unknown time is not in history yet
  self.assertEqual(self.gateway.store.latest(self.cfg['station'],1303)['reason'],'unknown_clock')
  self.node.acknowledge(self.gateway.receive(self.node.packet(self.node.sample(1360)),1361))
  self.assertEqual(len(self.gateway.store.history(self.cfg['station'])),5)
  first=[r for r in self.gateway.store.history(self.cfg['station']) if r['session']=='2' and r['sequence']==0][0]
  self.assertEqual((first['effective_sampled_at'],first['time_basis']),(1300,'reconstructed'))
  self.assertEqual(self.gateway.store.latest(self.cfg['station'],1363)['observation']['sampled_at'],1360)
  self.assertFalse(self.gateway.store.latest(self.cfg['station'],1540)['available'])
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
   with get('/v1/observations?format=csv') as r: header=r.read().decode().splitlines()[0].split(',')
   from ws0.fields import MEASURED
   self.assertTrue(set(MEASURED) <= set(header))   # every catalog field, not just T/RH
   with get('/v1/observations') as r: self.assertEqual(json.load(r)['units']['humidity_max_pct'],'%')
   # A calm reading (wind_calm) and a qualifier must survive the CSV export, not vanish.
   import csv,io
   from ws0 import fields as F
   calm=dict(version=5,station=self.cfg['station'],session='7',sequence=1,sampled_at=2000,uptime_s=60,
             time_quality='synchronized',energy_state='normal',calibration_revision=0,temperature_c=-1.5,
             humidity_pct=90.0,wind_speed_ms=0.0,wind_dir_deg=None,wind_calm=True,
             qualifiers={'temperature_c':'suspected_icing'})
   calm['quality']=F.quality(calm)
   self.gateway.store.ingest(calm,2001)
   with get('/v1/observations?format=csv') as r: rows=list(csv.DictReader(io.StringIO(r.read().decode())))
   row=next(x for x in rows if x['session']=='7')
   self.assertEqual((row['wind_calm'],json.loads(row['qualifiers'])),('True',{'temperature_c':'suspected_icing'}))
   with self.assertRaises(HTTPError): get('/v1/observations?limit=1001')
   with get('/v1/status') as r: self.assertNotIn('radio_key',r.read().decode())
  finally: server.shutdown(); server.server_close()
 def test_ha_discovery(self):
  entries=discovery(self.cfg); self.assertEqual(len(entries),2)
  for entry in entries.values():
   self.assertEqual(entry['availability_mode'],'all'); self.assertEqual(len(entry['availability']),3)
   self.assertIn('is not none',entry['availability'][2]['value_template'])   # a null field is unavailable
  more=discovery(self.cfg,['pressure_hpa','rain_tips','batt_mv','qualifiers','wind_calm'])
  self.assertEqual(sorted(k.split('/')[2] for k in more),['simulation-01_batt_mv','simulation-01_pressure_hpa','simulation-01_rain_tips'])
  rain=more['homeassistant/sensor/simulation-01_rain_tips/config']; batt=more['homeassistant/sensor/simulation-01_batt_mv/config']
  self.assertEqual((rain['state_class'],batt['entity_category'],batt['device_class']),('total_increasing','diagnostic','voltage'))
  self.assertEqual([e['name'] for e in entries.values()],['Temperature','Humidity'])
  from ws0.fields import MEASURED; from ws0.fields import DERIVED, LABELS; self.assertEqual(set(LABELS),set(MEASURED)|set(DERIVED))
  dew=discovery(self.cfg,['dew_point_c'])['homeassistant/sensor/simulation-01_dew_point_c/config']
  self.assertEqual((dew['name'],dew['unit_of_measurement'],dew['device_class']),('Dew point (derived)','°C','temperature'))

@needs_cc
class FirmwareTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.lib=host_library(cls,'stage0','firmware/stage0.c')
  cls.lib.ws_crc8.argtypes=[ctypes.POINTER(ctypes.c_uint8),ctypes.c_size_t]; cls.lib.ws_crc8.restype=ctypes.c_uint8
 def test_sensirion_crc(self):
  self.assertEqual(self.lib.ws_crc8((ctypes.c_uint8*2)(0xbe,0xef),2),0x92)

class AdditionalFailures(StationTest):
 def test_clock_quarantine_and_corrected_clock(self):
  self.gateway.receive(self.node.packet(self.node.sample(1000,clock_offset=1000)),1000)
  self.assertFalse(self.gateway.store.latest(self.cfg['station'],2001)['available'])
  self.gateway.receive(self.node.packet(self.node.sample(1060)),1061)
  self.assertTrue(self.gateway.store.latest(self.cfg['station'],1062)['available'])
 def test_ack_tamper_keeps_pending(self):
  ack=self.gateway.receive(self.node.packet(self.node.sample(1000)),1001)
  with self.assertRaises(InvalidTag): self.node.acknowledge(ack[:-1]+bytes([ack[-1]^1]))
  self.assertEqual(len(self.node.backfill()),1)

@needs_cc
class SensorBusTests(unittest.TestCase):
 def test_bus_failures_crc_and_conversion(self):
  with tempfile.TemporaryDirectory() as temp:
   exe=str(Path(temp)/'sensor-test')
   subprocess.run([*CC_STRICT,*SAN,'firmware/stage0.c','firmware/test_sensor.c','-o',exe],check=True)
   subprocess.run([exe],check=True)
 def test_bus_recovery_waveform_and_link_gate(self):
  with tempfile.TemporaryDirectory() as temp:
   exe=str(Path(temp)/'policy-test')
   subprocess.run([*CC_STRICT,*SAN,'firmware/stage0.c','firmware/test_policy.c','-o',exe],check=True)
   subprocess.run([exe],check=True)
 def test_tx_transmission_policy(self):
  # firmware/common/ws_policy.c: airtime, link state, what a minute may send, strikes.
  with tempfile.TemporaryDirectory() as temp:
   exe=str(Path(temp)/'tx-policy-test')
   subprocess.run([*CC_STRICT,*SAN,'-Ifirmware','firmware/stage0.c','firmware/common/ws_policy.c',
                   'firmware/common/ws_check.c','firmware/test_tx_policy.c','-o',exe,'-lm'],check=True)
   subprocess.run([exe],check=True)


class ServiceSmokeTests(unittest.TestCase):
 def test_cli_demo_starts_and_persists(self):
  with tempfile.TemporaryDirectory() as tmp:
   proc,cfg=start_demo(tmp)
   windows=sys.platform=='win32'
   try:
    self.assertIn(b'Stage 0 simulation',proc.stdout.readline())
    line=json.loads(proc.stdout.readline()); self.assertTrue(line['simulation'])
    req=Request(f"http://127.0.0.1:{cfg['http_port']}/v1/status",headers={'Authorization':'Bearer '+cfg['api_token']})
    with urlopen(req,timeout=3) as response:
     status=json.load(response); self.assertTrue(status['latest']['available'])
     self.assertEqual(status['h01'],'NOT RUN')
   finally:
    import signal
    proc.send_signal(signal.CTRL_BREAK_EVENT if windows else signal.SIGINT)
    try: proc.communicate(timeout=10)
    except subprocess.TimeoutExpired: proc.kill(); proc.communicate(); raise
   self.assertEqual(proc.returncode,0)

 @unittest.skipIf(sys.platform=='win32','POSIX signals')
 def test_cli_second_stop_signal_during_shutdown_is_ignored(self):
  # A service manager may send SIGTERM more than once; a second one during cleanup used to
  # raise KeyboardInterrupt inside server.shutdown() and leave a traceback in serve.log.
  import signal,time
  with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
   proc,_=start_demo(tmp)
   try:
    self.assertIn(b'Stage 0 simulation',proc.stdout.readline())
    proc.stdout.readline()
    for _ in range(5):
     proc.send_signal(signal.SIGTERM); time.sleep(0.05)
    _,err=proc.communicate(timeout=10)
   except subprocess.TimeoutExpired:
    proc.kill(); proc.communicate(); raise
   self.assertNotIn(b'Traceback',err)
   self.assertEqual(proc.returncode,0)

 def test_mqtt_advertises_a_field_when_it_first_appears(self):
  with Station(node=False) as s:
   gateway,cfg=s.gateway,s.cfg
   publisher=fake_mqtt(gateway)
   record=dict(version=5,station=cfg['station'],session='1',sequence=0,sampled_at=1000,uptime_s=60,
               time_quality='synchronized',energy_state='normal',calibration_revision=0,
               temperature_c=20.5,humidity_pct=40,pressure_hpa=1001.3,quality='valid')
   gateway.store.ingest(record,1001)
   publisher.tick()
   configs=[m[0][0] for m in publisher.client.messages if m[0][0].startswith('homeassistant/')]
   self.assertEqual(configs,['homeassistant/sensor/simulation-01_pressure_hpa/config'])
   publisher.client.messages.clear(); publisher.published_at-=MQTT.REFRESH_S; publisher.tick()
   self.assertFalse([m for m in publisher.client.messages if m[0][0].startswith('homeassistant/')])

 def test_last_ingested_is_the_frame_just_received(self):
  # serve.log printed the newest stored reading after each frame, so a backlog burst
  # (live seq 4, then backfilled 0..2) logged 'seq 4' four times (2026-10-14 15:19:50Z).
  with Station() as s:
   gateway,node=s.gateway,s.node
   old=node.sample(1000); new=node.sample(1060)
   gateway.receive(node.packet(new),1061)
   self.assertEqual((gateway.last_ingested['sequence'],gateway.last_ingested['duplicate']),(new['sequence'],False))
   gateway.receive(node.packet(old),1062)
   self.assertEqual((gateway.last_ingested['sequence'],gateway.last_ingested['duplicate']),(old['sequence'],False))
   gateway.receive(node.packet(old),1063)
   self.assertTrue(gateway.last_ingested['duplicate'])

 def test_mqtt_stale_payload_and_availability(self):
  from unittest.mock import patch
  with Station() as s:
   gateway,node=s.gateway,s.node
   gateway.receive(node.packet(node.sample(1000)),1001)
   publisher=fake_mqtt(gateway)
   with patch('gateway.time.time',return_value=1180): publisher.tick()
   self.assertEqual(publisher.client.messages[-1][0][1],'offline')
   self.assertEqual(json.loads(publisher.client.messages[0][0][1])['sampled_at'],1000)
   sent=len(publisher.client.messages)
   with patch('gateway.time.time',return_value=1181): publisher.tick()   # unchanged: no republish
   self.assertEqual(len(publisher.client.messages),sent)
   publisher.published_at-=MQTT.REFRESH_S                                 # refresh interval elapsed
   with patch('gateway.time.time',return_value=1182): publisher.tick()
   self.assertEqual(len(publisher.client.messages),sent+2)


class TimeReconstruction(StationTest):
 """Draft 4: unsynchronized samples get UTC from the same boot epoch's uptime counter."""
 def boot(self):
  self.node.db.close(); self.node.nonces.db.close(); self.node=Node(self.cfg,self.root)
 def test_boot_sample_reconstructed_after_first_sync(self):
  self.boot()
  self.node.acknowledge(self.gateway.receive(self.node.packet(self.node.sample(5000)),5001))
  self.assertEqual(self.gateway.store.latest(self.cfg['station'],5002)['reason'],'unknown_clock')
  self.node.acknowledge(self.gateway.receive(self.node.packet(self.node.sample(5060)),5061))
  rows={r['sequence']:r for r in self.gateway.store.history(self.cfg['station'],4000,6000)}
  self.assertEqual((rows[0]['effective_sampled_at'],rows[0]['time_basis']),(5000,'reconstructed'))
  self.assertIsNone(rows[0]['sampled_at'])  # the raw payload stays honest and immutable
  self.assertAlmostEqual(rows[0]['time_uncertainty_s'],2+60*150e-6)
 def test_outage_after_reboot_whole_backlog_recovers_time(self):
  self.boot()  # station reboots while the gateway is unreachable: nothing is synced
  for minute in range(30): self.node.sample(7000+60*minute)
  self.node.acknowledge(self.gateway.receive(self.node.packet(self.node.sample(7000+60*30)),9000))
  self.node.acknowledge(self.gateway.receive(self.node.packet(self.node.sample(7000+60*31)),9061))
  for r in self.node.backfill(100): self.node.acknowledge(self.gateway.receive(self.node.packet(r),9062))
  rows=self.gateway.store.history(self.cfg['station'],0,10**10,1000)
  self.assertEqual(len(rows),32)
  for r in rows:
   self.assertEqual(r['effective_sampled_at'],7000+60*r['sequence'])
  self.assertEqual({r['time_basis'] for r in rows},{'reconstructed','synchronized'})
 def test_quarantined_reference_is_never_used(self):
  self.boot()
  self.node.acknowledge(self.gateway.receive(self.node.packet(self.node.sample(3000)),3001))
  self.gateway.receive(self.node.packet(self.node.sample(3060,clock_offset=3600)),3061)  # clock far ahead
  first=self.gateway.store.db.execute("SELECT time_basis FROM observations WHERE session='2' AND sequence=0").fetchone()
  self.assertEqual(first[0],'unknown')
 def test_uncertainty_grows_with_distance(self):
  self.boot()  # no ACK for three days: every sample is time-unknown
  for day in range(4): self.node.sample(10000+86400*day)
  for r in self.node.backfill(10): self.node.acknowledge(self.gateway.receive(self.node.packet(r),10000+86400*3+5))
  self.node.acknowledge(self.gateway.receive(self.node.packet(self.node.sample(10000+86400*3+60)),10000+86400*3+61))
  rows=dict(self.gateway.store.db.execute("SELECT sequence,time_uncertainty_s FROM observations WHERE session='2'").fetchall())
  self.assertAlmostEqual(rows[0],2+(86400*3+60)*150e-6)  # ~41 s after a 3-day span
  self.assertAlmostEqual(rows[3],2+60*150e-6)             # nearest reference: 60 s away
  self.assertEqual(rows[4],0)                             # the synchronized reference itself

class NackTests(StationTest):
 """Gap G2: authentic but permanently rejected frames get an authenticated NACK."""
 def test_collision_is_nacked_recorded_and_dropped_by_node(self):
  from ws0.protocol import KIND_NACK,NACK_COLLISION,frame_kind
  record=self.node.sample(1000)
  self.node.handle_reply(self.gateway.receive(self.node.packet(record),1001))
  altered=record|{'temperature_c':record['temperature_c']+1}
  self.node.db.execute('INSERT INTO pending VALUES (?,?,?)',(self.node.epoch,record['sequence'],json.dumps(altered)))
  reply=self.gateway.receive(self.node.packet(altered),1002)
  self.assertEqual(frame_kind(reply),KIND_NACK)
  self.assertEqual(self.node.handle_reply(reply),NACK_COLLISION)
  self.assertEqual(self.node.backfill(),[]); self.assertEqual(self.node.abandoned,1)
  rows=self.gateway.store.db.execute('SELECT reason,frame_hex FROM rejections').fetchall()
  self.assertEqual(len(rows),1); self.assertEqual(rows[0][0],'identity_collision'); self.assertTrue(rows[0][1])
  self.assertEqual(self.gateway.store.latest(self.cfg['station'],1003)['observation']['temperature_c'],record['temperature_c'])
 def test_invalid_authentic_record_is_nacked(self):
  from ws0 import fields
  from ws0.protocol import KIND_NACK,NACK_INVALID,frame_kind,seal,unpack_reply
  good=fields.encode(self.node.epoch,7,1000,0,1,0,{0:4000,1:5000})
  bad=good[:16]+bytes([good[16]&~1])+good[17:]  # UTC set but time-known flag clear: noncanonical
  frame=seal(self.node.key,1,1,self.node.nonces,bad)
  reply=self.gateway.receive(frame,1001)
  self.assertEqual(frame_kind(reply),KIND_NACK)
  self.assertEqual(unpack_reply(unseal(self.node.key,1,KIND_NACK,reply))[2],NACK_INVALID)
 def test_unauthenticated_frame_gets_no_reply(self):
  frame=self.node.packet(self.node.sample(1000))
  with self.assertRaises(InvalidTag): self.gateway.receive(frame[:-1]+bytes([frame[-1]^1]),1001)
  self.assertEqual(self.gateway.store.db.execute('SELECT count(*) FROM rejections').fetchone()[0],0)
 def test_nack_for_a_frame_the_node_did_not_send_is_refused(self):
  from ws0.protocol import KIND_NACK,pack_reply,seal
  self.node.sample(1000)
  forged=seal(self.node.key,1,KIND_NACK,self.gateway.nonces,pack_reply(self.node.epoch,0,1,999999))
  with self.assertRaises(ValueError): self.node.handle_reply(forged)
  self.assertEqual(len(self.node.backfill()),1)
 def test_commit_failure_still_gets_no_reply(self):
  frame=self.node.packet(self.node.sample(1000))
  self.gateway.store.ingest=lambda *a: (_ for _ in ()).throw(OSError('disk full'))
  with self.assertRaises(OSError): self.gateway.receive(frame)


class DiagnosticsAndEpochFloor(StationTest):
 """Gaps G8 (health reports) and G5 (epoch floor after a wipe)."""
 def diag(self,epoch,uptime,lost=0):
  from ws0.protocol import DIAG,KIND_DIAG,seal
  return seal(self.node.key,1,KIND_DIAG,self.node.nonces,DIAG.pack(epoch,uptime,1,lost,0,2,3,0,5,0,0x45f43e78,-61,9,2,1))
 def test_report_is_stored_unanswered_and_ordered_by_epoch_uptime(self):
  self.assertIsNone(self.gateway.receive(self.diag(4,600,lost=7),1000))
  late=self.diag(4,300)                       # older report arriving later (delay or replay)
  self.assertIsNone(self.gateway.receive(late,1001))
  d=self.gateway.status()['node_diagnostics']
  self.assertEqual((d['epoch'],d['uptime_s'],d['journal_lost_total'],d['reset_cause'],d['link']),(4,600,7,'watchdog','linked'))
  self.assertEqual((d['firmware_build'],d['ack_rssi_dbm'],d['ack_snr_db'],d['crashes_since_power_up'],d['energy_state']),
                   ('45f43e78',-61,9,2,'normal'))
  self.gateway.receive(self.diag(5,10),1002)
  self.assertEqual(self.gateway.status()['node_diagnostics']['epoch'],5)
  self.assertEqual(self.gateway.store.history(self.cfg['station']),[])   # never an observation
 def test_tampered_report_is_rejected(self):
  frame=self.diag(4,600)
  with self.assertRaises(InvalidTag): self.gateway.receive(frame[:-1]+bytes([frame[-1]^1]),1000)
 def test_epoch_floor_is_above_all_stored_epochs(self):
  from ws0.__main__ import epoch_floor
  self.assertEqual(epoch_floor(self.root,self.cfg['station']),0)        # empty database: no floor
  self.gateway.receive(self.node.packet(self.node.sample(1000)),1001)  # epoch 1
  self.gateway.receive(self.diag(9,60),1002)                             # a later epoch seen only in a report
  self.assertEqual(epoch_floor(self.root,self.cfg['station']),10)


class CommandLineTests(unittest.TestCase):
 """Characterization of `python -m ws0` argument handling and the demo's log file and link-down
 switch (ws0/__main__.py main)."""
 def ws0(self,*args,timeout=60):
  return subprocess.run([sys.executable,'-m','ws0',*args],capture_output=True,timeout=timeout)
 def test_command_and_mode_mismatches_are_usage_errors(self):
  with tempfile.TemporaryDirectory() as tmp:
   sim,hw=Path(tmp)/'sim',Path(tmp)/'hw'
   self.assertEqual(self.ws0('init','--directory',str(sim)).returncode,0)
   created=self.ws0('init','--hardware','--station','station-01','--station-id','7','--directory',str(hw))
   self.assertEqual(created.returncode,0)
   self.assertIn(b'Created',created.stdout)
   cfg=json.loads((hw/'gateway.json').read_text())
   self.assertEqual((cfg['mode'],cfg['station'],cfg['station_id']),('hardware','station-01',7))
   self.assertEqual(sorted(p.name for p in hw.iterdir()),['gateway-nonces.sqlite3','gateway.json'])
   for args,message in [(('demo','--directory',str(hw)),b'Demo requires a dedicated simulation configuration'),
                        (('serve','--directory',str(sim)),b'serve requires --serial or --serial-number'),
                        (('provision-node','--directory',str(sim),'--serial','/dev/null'),
                         b'provision-node requires a --hardware state directory and --serial'),
                        (('provision-node','--directory',str(hw)),
                         b'provision-node requires a --hardware state directory and --serial'),
                        (('bogus',),b'invalid choice')]:
    result=self.ws0(*args)
    self.assertEqual(result.returncode,2,args)
    self.assertIn(message,result.stderr,args)
   self.assertFalse((hw/'observations.sqlite3').exists())    # nothing started
 def test_demo_log_file_and_link_down(self):
  import signal,time
  with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
   directory=Path(tmp)/'state'; quiet_provision(directory)
   import socket
   cfg=json.loads((directory/'gateway.json').read_text())
   with socket.socket() as sock:
    sock.bind(('127.0.0.1',0)); cfg['http_port']=sock.getsockname()[1]
   (directory/'gateway.json').write_text(json.dumps(cfg))
   (directory/'link-down').touch()
   log=Path(tmp)/'serve.log'
   windows=sys.platform=='win32'
   proc=subprocess.Popen([sys.executable,'-m','ws0','demo','--directory',str(directory),'--log-file',str(log)],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if windows else 0)
   try:
    deadline=time.monotonic()+20
    while time.monotonic()<deadline and b'"simulation": true' not in (log.read_bytes() if log.exists() else b''):
     time.sleep(0.1)
   finally:
    proc.send_signal(signal.CTRL_BREAK_EVENT if windows else signal.SIGINT)
    try: out,err=proc.communicate(timeout=10)
    except subprocess.TimeoutExpired: proc.kill(); proc.communicate(); raise
   self.assertEqual(proc.returncode,0)
   self.assertEqual((out,err),(b'',b''))                          # everything went to the log file
   lines=log.read_text().splitlines()
   self.assertTrue(lines[0].startswith('Stage 0 simulation; API http://127.0.0.1:'))
   sample=json.loads(next(l for l in lines if l.startswith('{')))
   self.assertEqual((sample['simulation'],sample['link_down']),(True,True))
   from gateway import open_read_only
   db=open_read_only(directory/'observations.sqlite3')
   try:
    self.assertEqual(db.execute('SELECT count(*) FROM observations').fetchone()[0],0)   # link down: nothing sent
    kinds=[r[0] for r in db.execute('SELECT kind FROM gateway_events ORDER BY id')]
   finally:
    db.close()
   self.assertEqual((kinds[0],kinds[-1]),('start','stop'))
