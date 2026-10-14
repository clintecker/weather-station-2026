"""Deterministic virtual-time campaigns against real Stage-0 protocol/storage code.

Only time, sensor input, delivery and injected failures are simulated. AES-CCM,
SQLite commits, nonce allocation, journaling, deduplication and freshness use the
same implementations as the runnable demo. No RF or power claims follow.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict, dataclass, field
import hashlib
import heapq
import os
# The harness models networks and restarts, not power loss: skip the slow drive-cache flush (G4).
os.environ.setdefault('WS0_UNSAFE_FAST_FSYNC', '1')
import html
import json
from pathlib import Path
import random
import sqlite3
import tempfile
from cryptography.exceptions import InvalidTag
from .protocol import HEADER_LEN, KIND_ACK, KIND_NACK, KIND_OBS, NACK_COLLISION, Nonces, frame_counter, frame_kind, unpack_reply, unseal
from .service import CounterRegression, Gateway, Replay
from .simulator import BACKLOG_PER_MINUTE, Node

START = 1_800_000_000  # Fixed virtual UTC origin, independent of wall-clock date.


@dataclass
class Scenario:
    """All minute intervals are half-open; rates apply independently per send."""
    name: str
    description: str
    minutes: int = 1440
    seed: int = 73
    uplink_loss: float = 0.0
    ack_loss: float = 0.0
    corruption: float = 0.0
    duplicates: float = 0.0
    max_delay_seconds: int = 0
    link_outages: list[list[int]] = field(default_factory=list)
    host_outages: list[list[int]] = field(default_factory=list)
    commit_failures: list[list[int]] = field(default_factory=list)
    sensor_faults: list[list[int]] = field(default_factory=list)
    unknown_clock: list[list[int]] = field(default_factory=list)
    clock_steps: list[list[int]] = field(default_factory=list)  # start, end, offset seconds
    node_reboots: list[int] = field(default_factory=list)
    gateway_reboots: list[int] = field(default_factory=list)
    inject_identity_collision: bool = False
    require_latency_target: bool = False
    expect_unavailable: bool = False
    expect_latency_failure: bool = False
    # Draft 4: every unsynchronized sample must end with a reconstructed (or synchronized) time.
    require_time_reconstruction: bool = False

    def validate(self):
        """Reject ambiguous scenario settings before mutating simulation state."""
        if not self.name or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in self.name):
            raise ValueError('Scenario name must use lowercase letters, digits, - or _')
        if type(self.minutes) is not int or not 1 <= self.minutes <= 10080:
            raise ValueError('minutes must be an integer from 1 to 10080')
        for name in ('uplink_loss','ack_loss','corruption','duplicates'):
            value = getattr(self,name)
            if type(value) not in (int,float) or not 0 <= value <= 1:
                raise ValueError(f'{name} must be a probability')
        if type(self.max_delay_seconds) is not int or not 0 <= self.max_delay_seconds <= 600:
            raise ValueError('max_delay_seconds must be 0..600')
        for name in ('link_outages','host_outages','commit_failures','sensor_faults','unknown_clock','clock_steps'):
            for span in getattr(self,name):
                size = 3 if name == 'clock_steps' else 2
                if len(span) != size or any(type(n) is not int for n in span):
                    raise ValueError(f'Invalid interval in {name}')
                if not 0 <= span[0] < span[1] <= self.minutes:
                    raise ValueError(f'Out-of-range interval in {name}')
        for minute in self.node_reboots+self.gateway_reboots:
            if type(minute) is not int or not 0 <= minute < self.minutes:
                raise ValueError('Reboot outside sampling interval')
        if self.require_latency_target and self.expect_latency_failure:
            raise ValueError('Contradictory latency expectations')


def inside(minute: int, spans: list[list[int]]) -> bool:
    return any(start <= minute < end for start,end,*_ in spans)


def key(record):
    """Identity deliberately excludes timestamps and payload values."""
    return record['session'],record['sequence']


# Gateway-derived columns that are not part of the immutable observation payload.
DERIVED = ('received_at','_effective','_basis')


def assess(expected, rows, now):
    """Account against scheduled samples; never shrink the denominator on failure."""
    by_key = {key(row):row for row in rows}
    missing = [list(k) for k in expected if k not in by_key]
    mismatches = []
    on_time = unknown = invalid = 0
    latencies = []
    for identity, info in expected.items():
        expected_record, acquired = info
        row = by_key.get(identity)
        unknown += expected_record['time_quality'] != 'synchronized'
        invalid += expected_record['quality'] != 'valid'
        if row is None:
            continue
        actual = {k:v for k,v in row.items() if k not in DERIVED}
        if actual != expected_record:
            mismatches.append(list(identity))
        # Ground-truth delivery latency is available to the simulator even for bad clocks.
        latency = row['received_at']-acquired
        latencies.append(latency)
        # H01-like eligibility also needs a known time close to simulated acquisition. Per
        # Clint's 2026-10-12 decision, a gateway-reconstructed time (draft 4) is a known time
        # when it is within the same 5 s tolerance; it is reported separately below.
        trustworthy_time = (row['_basis'] in ('synchronized','reconstructed') and
                            row['_effective'] is not None and abs(row['_effective']-acquired) <= 5)
        on_time += int(trustworthy_time and 0 <= latency <= 120)
    return {'scheduled':len(expected),'stored':len(rows),'missing':missing,
            'unexpected_rows':[list(k) for k in by_key if k not in expected],
            'payload_mismatches':mismatches,'duplicate_rows':len(rows)-len(by_key),
            'within_120s_with_trustworthy_time':on_time,
            'live_delivery_percent':round(100*on_time/len(expected),4) if expected else 0,
            'latency_target_met':bool(expected) and on_time >= (99*len(expected)+99)//100,
            'maximum_ground_truth_latency_seconds':max(latencies,default=None),
            'unknown_clock_samples':unknown,'sensor_fault_samples':invalid,
            'reconstructed_time_samples':sum(r['_basis']=='reconstructed' for r in rows),
            'unresolved_time_samples':sum(r['_basis']=='unknown' for r in rows)}


class Campaign:
    """A seeded lossy network around genuine persistent node/gateway instances."""
    def __init__(self, scenario: Scenario, output: Path, negative_control=False):
        scenario.validate()
        self.s = scenario
        self.output = output
        self.negative_control = negative_control
        self.random = random.Random(scenario.seed)
        self.events = []
        self.event_number = 0
        self.now = START
        self.expected = {}
        self.first_receipt = {}
        self.tx_nonces = set()
        self.nonce_collisions = 0
        self.counts = {name:0 for name in ['uplink_sent','ack_sent','random_drops','outage_drops',
                                         'corrupted','duplicates','rejected','commit_errors','nacks',
                                         'identity_collision_rejections','node_reboots','gateway_reboots',
                                         'counter_regressions','expected_counter_regressions',
                                         'replays','expected_replays']}
        # P4 oracle: the node must seal strictly increasing counters in send order, and the
        # gateway must flag exactly the authentic arrivals at or below the highest counter that
        # has already arrived (wire duplicates and reordering), across gateway restarts.
        self.last_sealed_counter = 0
        self.node_counter_not_increasing = 0
        self.highest_arrived_counter = 0
        self.first_arrival = {}   # counter -> bytes of the first authentic frame accepted under it
        self.availability = []

    def log(self, event, **details):
        """Raw trace contains frames and events, never working deployment credentials."""
        self.trace.write(json.dumps({'virtual_utc':self.now,'event':event,**details},sort_keys=True)+'\n')

    def minute(self):
        return (self.now-START)//60

    def allocate_frame(self, record):
        packet = self.node.packet(record)
        self.track_nonce(packet)
        counter = frame_counter(packet)
        self.node_counter_not_increasing += int(counter <= self.last_sealed_counter)
        self.last_sealed_counter = counter
        return packet

    def expect_regression(self, packet):
        """Independent of the gateway: authentic and not above every earlier authentic arrival."""
        try:
            unseal(bytes.fromhex(self.cfg['radio_key']),self.cfg['station_id'],1,packet)
        except (ValueError,InvalidTag):
            return False
        counter = frame_counter(packet)
        if counter > self.highest_arrived_counter:
            self.highest_arrived_counter = counter
            self.first_arrival[counter] = packet
            return False
        # At or below the mark: an exact copy of the accepted frame is a replay; anything else
        # (reordered older frame, different bytes) is a regression (draft-5 design section 8).
        replay = self.first_arrival.get(counter) == packet
        self.counts['expected_replays' if replay else 'expected_counter_regressions'] += 1
        return not replay

    def track_nonce(self, packet):
        # Observe new encryption operations only; byte-for-byte network duplication is legal.
        nonce = (frame_kind(packet), packet[1:3], frame_counter(packet))  # what CCM's nonce is built from
        if nonce in self.tx_nonces:
            self.nonce_collisions += 1
        self.tx_nonces.add(nonce)

    def send(self, direction, packet):
        """Drop/corrupt/delay/duplicate after encryption, like an unreliable wire."""
        self.counts[direction+'_sent'] += 1
        self.log('send',direction=direction,frame=packet.hex())
        if inside(self.minute(),self.s.link_outages):
            self.counts['outage_drops'] += 1
            self.log('link_drop',direction=direction)
            return
        probability = self.s.uplink_loss if direction == 'uplink' else self.s.ack_loss
        if self.random.random() < probability:
            self.counts['random_drops'] += 1
            self.log('random_drop',direction=direction)
            return
        if self.random.random() < self.s.corruption:
            offset = self.random.randrange(HEADER_LEN,len(packet))  # ciphertext or tag, never the header
            packet = packet[:offset]+bytes([packet[offset]^1])+packet[offset+1:]
            self.counts['corrupted'] += 1
        copies = 2 if self.random.random() < self.s.duplicates else 1
        self.counts['duplicates'] += copies-1
        for _ in range(copies):
            delay = self.random.randint(0,self.s.max_delay_seconds)
            self.event_number += 1
            heapq.heappush(self.events,(self.now+delay,self.event_number,direction,packet))

    def advance(self, deadline):
        """Process each arrival with its actual virtual receipt time, including delayed ACKs."""
        while self.events and self.events[0][0] <= deadline:
            self.now,_,direction,packet = heapq.heappop(self.events)
            if inside(self.minute(),self.s.link_outages) or inside(self.minute(),self.s.host_outages):
                self.counts['outage_drops'] += 1
                self.log('arrival_drop',direction=direction)
                continue
            try:
                if direction == 'uplink':
                    self.expect_regression(packet)
                    # Inject real commit-boundary failure without making a fake ACK.
                    original = self.gateway.store.ingest
                    if inside(self.minute(),self.s.commit_failures):
                        def failed_commit(*args,**kwargs):
                            # What SQLite really raises on a full or failing disk (not OSError).
                            raise sqlite3.OperationalError('disk I/O error (injected)')
                        self.gateway.store.ingest = failed_commit
                    try:
                        ack = self.gateway.receive(packet,self.now)
                    finally:
                        self.gateway.store.ingest = original
                    self.track_nonce(ack)
                    if frame_kind(ack) == KIND_NACK:
                        reason = unpack_reply(unseal(bytes.fromhex(self.cfg['radio_key']),1,KIND_NACK,ack))[2]
                        self.counts['nacks'] += 1
                        self.counts['identity_collision_rejections'] += int(reason == NACK_COLLISION)
                        self.log('rejected_nack',frame=packet.hex(),reason=reason)
                    else:
                        self.log('committed_or_duplicate',frame=packet.hex())
                    self.send('ack',ack)
                else:
                    self.node.handle_reply(packet)
                    self.log('ack_accepted' if frame_kind(packet) != KIND_NACK else 'nack_accepted',frame=packet.hex())
            except (OSError, sqlite3.Error):
                self.counts['commit_errors'] += 1
                self.log('commit_failed_no_ack')
            except Replay:
                # An exact duplicate of an accepted frame: never answered, never stored, no alarm.
                self.counts['replays'] += 1
                self.log('replay_no_reply',frame=packet.hex())
            except CounterRegression:
                # A reordered older frame or different bytes under a used counter: never answered,
                # never stored, raises the key-reuse alarm (P4).
                self.counts['counter_regressions'] += 1
                self.log('counter_regression_no_reply',frame=packet.hex())
            except (ValueError,InvalidTag) as exc:
                self.counts['rejected'] += 1
                collision = str(exc)=='Identity collision'
                self.counts['identity_collision_rejections'] += int(collision)
                self.log('rejected',direction=direction,reason=type(exc).__name__,identity_collision=collision)
        self.now = deadline

    def restart(self, node=False, gateway=False):
        """Close/reopen real databases; queued wire packets can arrive after reboot."""
        if node:
            self.node.db.close(); self.node.nonces.db.close()
            self.node = Node(self.cfg,self.state)
            self.counts['node_reboots'] += 1
            self.log('node_reboot',new_sample_epoch=self.node.epoch)
        if gateway:
            self.gateway.store.db.close(); self.gateway.nonces.db.close()
            self.gateway = Gateway(self.cfg,self.state)
            self.counts['gateway_reboots'] += 1
            self.log('gateway_reboot')

    def snapshot(self):
        state = self.gateway.store.latest(self.cfg['station'],self.now)
        truth = None
        if state.get('observation'):
            truth = self.expected.get(key(state['observation']),(None,None))[1]
        self.availability.append({'virtual_utc':self.now,'minute':self.minute(),
                                  'available':state['available'],'reason':state.get('reason'),
                                  'time_basis':state.get('time_basis'),
                                  'effective_sampled_at':state.get('effective_sampled_at'),'true_sampled_at':truth})

    def run(self):
        self.output.mkdir(parents=True,exist_ok=False)
        with tempfile.TemporaryDirectory(prefix='ws0-harness-') as temporary, \
                (self.output/'trace.jsonl').open('w') as self.trace:
            self.state = Path(temporary)
            # Fixed public test key makes traces reproducible. It is never deployment provisioning.
            radio_key = hashlib.sha256(('PUBLIC-TEST-KEY/'+self.s.name).encode()).digest()[:16]
            self.cfg = {'station':'simulation-01','station_id':1,'mode':'simulation',
                        'radio_key':radio_key.hex(),'api_token':'not-a-deployment-token','mqtt':{'enabled':False}}
            for name,kind in [('node',KIND_OBS),('gateway',KIND_ACK)]:
                Nonces(self.state/f'{name}-nonces.sqlite3',radio_key,1,kind,create=True).db.close()
            self.node = Node(self.cfg,self.state)
            self.gateway = Gateway(self.cfg,self.state)
            try:
                for minute in range(self.s.minutes):
                    self.advance(START+minute*60)
                    self.restart(minute in self.s.node_reboots,minute in self.s.gateway_reboots)
                    clock_offset = next((offset for start,end,offset in self.s.clock_steps if start<=minute<end),0)
                    record = self.node.sample(self.now,inside(minute,self.s.sensor_faults),clock_offset,
                                              not inside(minute,self.s.unknown_clock))
                    self.expected[key(record)] = (record.copy(),self.now)
                    self.log('sample',record=record)
                    self.send('uplink',self.allocate_frame(record))
                    self.advance(self.now)  # Zero-delay link may ACK live sample before backfill.
                    # Never intentionally send the live record again in the same period.
                    old = [r for r in self.node.backfill(BACKLOG_PER_MINUTE+1) if key(r)!=key(record)][:BACKLOG_PER_MINUTE]
                    for r in old:
                        self.send('uplink',self.allocate_frame(r))
                    if self.s.inject_identity_collision and minute == 30:
                        altered = record | {'temperature_c':record['temperature_c']+1}
                        self.send('uplink',self.allocate_frame(altered))
                    self.advance(START+minute*60+59)
                    self.snapshot()
                # Finite drain budget is explicit; no free infinite recovery is assumed.
                drain_periods = 0
                for offset in range(1,self.s.minutes+121):
                    self.advance(START+(self.s.minutes+offset-1)*60)
                    for record in self.node.backfill(BACKLOG_PER_MINUTE):
                        self.send('uplink',self.allocate_frame(record))
                    self.advance(self.now+59)
                    drain_periods += 1
                    if not self.node.backfill(1) and not self.events:
                        break
                rows = []
                for payload,received,effective,basis in self.gateway.store.db.execute(
                        'SELECT payload,received_at,effective_at,time_basis FROM observations'):
                    rows.append(json.loads(payload)|{'received_at':received,'_effective':effective,'_basis':basis})
                # Deliberately break the oracle's input to prove the verdict catches lost data.
                if self.negative_control and rows:
                    rows = rows[1:]
                metrics = assess(self.expected,rows,self.now)
                pending = self.node.db.execute('SELECT count(*) FROM pending').fetchone()[0]
                failures = []
                for field in ('missing','unexpected_rows','payload_mismatches','duplicate_rows'):
                    if metrics[field]: failures.append(field)
                if pending: failures.append('unacknowledged_journal_records')
                if self.nonce_collisions: failures.append('nonce_reuse')
                if self.node_counter_not_increasing: failures.append('node_counter_not_increasing')
                # The durable count must survive every gateway restart in the scenario.
                if self.counts['counter_regressions'] != self.counts['expected_counter_regressions'] or \
                        self.gateway.node_counter['counter_regression'] != self.counts['counter_regressions']:
                    failures.append('counter_regression_mismatch')
                if self.counts['replays'] != self.counts['expected_replays'] or \
                        self.gateway.node_counter['replays'] != self.counts['replays']:
                    failures.append('replay_mismatch')
                # Wire duplicates are replays now; without reordering, any regression is a false
                # key-reuse alarm.
                if self.counts['counter_regressions'] and not self.s.max_delay_seconds:
                    failures.append('counter_regression_false_positive')
                if self.s.require_latency_target and not metrics['latency_target_met']:
                    failures.append('live_latency_target')
                if self.s.expect_latency_failure and metrics['latency_target_met']:
                    failures.append('expected_latency_failure_not_observed')
                if self.s.expect_unavailable and not any(not row['available'] for row in self.availability):
                    failures.append('unavailable_not_observed')
                for snapshot in self.availability:
                    minute = snapshot['minute']
                    if inside(minute,self.s.sensor_faults+self.s.clock_steps) and snapshot['available']:
                        failures.append('fault_or_bad_clock_presented_as_current')
                        break
                    # Unknown node clock: current only with a reconstructed time that is correct.
                    if inside(minute,self.s.unknown_clock) and snapshot['available'] and (
                            snapshot['time_basis'] not in ('synchronized','reconstructed') or
                            abs(snapshot['effective_sampled_at']-snapshot['true_sampled_at']) > 5):
                        failures.append('unknown_clock_presented_with_wrong_time')
                        break
                    if snapshot['available'] and snapshot['true_sampled_at'] is not None and \
                            abs(snapshot['effective_sampled_at']-snapshot['true_sampled_at']) > 5:
                        failures.append('current_value_with_wrong_time')
                        break
                if self.s.require_time_reconstruction and metrics['unresolved_time_samples']:
                    failures.append('time_not_reconstructed')
                # With no clock/sensor fault at the end, normal sampling should recover freshness.
                end_minute = self.s.minutes-1
                end_fault = inside(end_minute,self.s.sensor_faults+self.s.unknown_clock+self.s.clock_steps)
                end_outage = inside(end_minute,self.s.link_outages+self.s.host_outages+self.s.commit_failures)
                if not end_fault and not end_outage and not self.availability[-1]['available']:
                    failures.append('availability_not_recovered')
                if self.s.inject_identity_collision and self.counts['identity_collision_rejections'] != 1:
                    failures.append('identity_collision_not_rejected')
                result = {'name':self.s.name,'description':self.s.description,'seed':self.s.seed,
                          'scenario_pass':not failures,'failures':failures,'metrics':metrics,
                          'network':self.counts,'pending_journal':pending,'nonce_collisions':self.nonce_collisions,
                          'counter_regressions':self.counts['counter_regressions'],
                          'expected_counter_regressions':self.counts['expected_counter_regressions'],
                          'replays':self.counts['replays'],'expected_replays':self.counts['expected_replays'],
                          'gateway_counter_status':self.gateway.status()['node_counter'],
                          'drain_minutes':drain_periods,'physical_H01':'NOT RUN',
                          'negative_control':self.negative_control}
                # Portable backup includes committed observations without relying on leftover WAL files.
                backup=sqlite3.connect(self.output/'observations.sqlite3')
                self.gateway.store.db.backup(backup); backup.close()
                (self.output/'scenario.json').write_text(json.dumps(asdict(self.s),indent=2)+'\n')
                (self.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
                (self.output/'availability.json').write_text(json.dumps(self.availability,indent=2)+'\n')
                return result
            finally:
                self.node.db.close(); self.node.nonces.db.close()
                self.gateway.store.db.close(); self.gateway.nonces.db.close()


def suite(minutes=1440):
    """Each scenario states which outcomes should pass, including deliberate degradation."""
    if minutes < 120:
        raise ValueError('Built-in suite requires at least 120 minutes')
    common={'minutes':minutes}
    return [
        Scenario('baseline','Lossless 60-second acquisition and authenticated delivery.',require_latency_target=True,**common),
        *[Scenario(f'noisy-link-{seed}','10% uplink loss, 10% ACK loss, 1% corruption, 15% duplication, up to 20s delay.',
                   seed=seed,uplink_loss=.10,ack_loss=.10,corruption=.01,duplicates=.15,max_delay_seconds=20,
                   require_latency_target=False,**common) for seed in (7,73,2026)],
        Scenario('radio-outage','20-minute radio outage; stale state then complete bounded recovery.',
                 link_outages=[[20,40]],expect_unavailable=True,expect_latency_failure=minutes<=1440,**common),
        Scenario('host-outage','10-minute host outage followed by gateway restart and journal recovery.',
                 host_outages=[[20,30]],gateway_reboots=[30],expect_unavailable=True,**common),
        Scenario('reboots','Node and gateway restarts, independently and together, with packet delay.',
                 node_reboots=[10,45,90],gateway_reboots=[20,45,95],max_delay_seconds=20,
                 require_latency_target=True,**common),
        Scenario('sensor-fault','Five minutes of failed sensor reads remain null, then recover.',
                 sensor_faults=[[20,25]],expect_unavailable=True,require_latency_target=True,**common),
        Scenario('clock-errors','Unknown clock and +1-hour clock step followed by corrected time.',
                 unknown_clock=[[20,25]],clock_steps=[[30,35,3600]],expect_unavailable=True,**common),
        Scenario('reboot-during-outage','Deployment case: station reboots during a 60-minute link outage, so it has '
                 'no clock until the link returns; every buffered sample must recover a correct time.',
                 link_outages=[[20,80]],node_reboots=[50],expect_unavailable=True,
                 expect_latency_failure=minutes<=1440,require_time_reconstruction=True,**common),
        Scenario('storage-failure','Five-minute commit failures must not ACK or delete uncommitted samples.',
                 commit_failures=[[20,25]],expect_unavailable=True,**common),
        Scenario('ack-loss','50% ACK loss and 15% duplication; records stay journaled until acknowledged.',
                 ack_loss=.50,duplicates=.15,require_latency_target=True,**common),
        Scenario('identity-collision','An authenticated altered payload reuses an existing sample identity and must be rejected.',
                 inject_identity_collision=True,require_latency_target=True,**common),
    ]


def render_report(results, output, minutes):
    """Small static report; source JSON and raw event evidence remain alongside it."""
    escape=html.escape
    rows=[]
    for r in results:
        m=r['metrics']; status='PASS' if r['scenario_pass'] else 'FAIL'
        rows.append(f"<tr><td><a href='{escape(r['name'])}/result.json'>{escape(r['name'])}</a><small>{escape(r['description'])}</small></td>"
                    f"<td class='{status.lower()}'>{status}</td><td>{m['stored']:,}/{m['scheduled']:,}</td>"
                    f"<td>{m['live_delivery_percent']:.2f}%</td><td>{len(m['missing'])}</td>"
                    f"<td>{r['nonce_collisions']}</td><td>{r['drain_minutes']}</td></tr>")
    passed=sum(r['scenario_pass'] for r in results)
    content=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Stage 0 simulation campaign</title><style>
body{{font:16px/1.55 system-ui;background:#f3f5f7;color:#172534;max-width:1150px;margin:40px auto;padding:0 24px}}
h1{{font-size:34px}}.notice{{background:#fff4d6;padding:18px;border-left:4px solid #bf8500}}table{{border-collapse:collapse;width:100%;background:white;margin:24px 0;font-size:14px}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #ddd}}small{{display:block;max-width:420px;color:#526070}}.pass{{color:#167044;font-weight:bold}}.fail{{color:#bd2828;font-weight:bold}}a{{color:#08677d}}code{{background:#e4e9ee;padding:2px 4px}}
</style><h1>Stage 0 · simulation campaign</h1><p><b>{passed}/{len(results)} scenario contracts passed.</b> Each scenario schedules {minutes:,} one-minute observations using virtual time.</p>
<p class="notice"><b>Physical H01: NOT RUN.</b> These are software fault/recovery tests, not measurements of RF range, airtime, current consumption, MCU timing, flash durability or 24-hour real-world reliability.</p>
<table><thead><tr><th>Scenario</th><th>Contract</th><th>Stored / scheduled</th><th>≤120s + valid clock</th><th>Missing</th><th>Nonce reuse</th><th>Drain minutes</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<p>PASS means the scenario's declared integrity/recovery expectations passed. It does not mean every scenario met 99% live delivery. Deliberate outages and clock faults retain their full denominator. Noisy-link scenarios measure delivery; the report does not assume their fault rates match real RF conditions.</p>
<p>Drain time is additional virtual time after sampling ends, with at most two queued observations attempted per minute. Real backfill still needs an airtime and receive-window budget.</p>
<h2>What ran</h2><p>Actual Python gateway, AES-CCM authentication, SQLite commit/ACK boundary, persistent transmitter queue, restart recovery, durable nonce allocator and freshness logic. Seeded network faults are injected after encryption.</p>
<h2>Evidence</h2><p>Each scenario directory contains <code>scenario.json</code>, <code>result.json</code>, <code>trace.jsonl</code>, <code>availability.json</code> and a committed <code>observations.sqlite3</code> snapshot. The campaign summary is <a href="summary.json">summary.json</a>.</p>
<h2>Limits</h2><p>Simulation uses host SQLite and public test keys. It does not model RF physics, FCC configuration, duty cycle, firmware power loss mid-flash-write, buffer capacity/overflow, energy use, environmental effects, a live MQTT broker or Home Assistant. Never deploy the deterministic test keys.</p></html>'''
    (output/'report.html').write_text(content)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('simulation-results'))
    parser.add_argument('--minutes',type=int,default=1440)
    parser.add_argument('--scenario',type=Path,help='Run one custom JSON Scenario instead of the built-in suite')
    parser.add_argument('--negative-control',action='store_true',help='Deliberately omit a stored row from the oracle; should exit 1')
    args=parser.parse_args()
    scenarios=[Scenario(**json.loads(args.scenario.read_text()))] if args.scenario else suite(args.minutes)
    # Fail before making any output if an input scenario is invalid.
    for s in scenarios: s.validate()
    args.output.mkdir(parents=True,exist_ok=False)
    results=[]
    for s in scenarios:
        result=Campaign(s,args.output/s.name,args.negative_control).run()
        results.append(result)
        print(f"{s.name}: {'PASS' if result['scenario_pass'] else 'FAIL'}; "
              f"{result['metrics']['live_delivery_percent']:.2f}% timely; "
              f"{len(result['metrics']['missing'])} missing",flush=True)
    (args.output/'summary.json').write_text(json.dumps({'physical_H01':'NOT RUN','results':results},indent=2)+'\n')
    render_report(results,args.output,scenarios[0].minutes)
    return 0 if all(r['scenario_pass'] for r in results) else 1

if __name__=='__main__':
    raise SystemExit(main())
