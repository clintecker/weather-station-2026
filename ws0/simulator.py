"""Persistent simulated node: journal before send, delete only after valid ACK."""
import json
import math
import random
import sqlite3
import time
from gateway import full_flush
from .protocol import (EPOCH_RESERVED, SIGNAL_NONE, VERSION, DIAG, KIND_ACK, KIND_DIAG, KIND_NACK, KIND_OBS, Nonces, encode_observation, frame_counter, frame_kind, seal, unpack_reply,
                       unseal)
U16_MAX = 2**16 - 1   # the DIAG report's u16 counts saturate

# Backlog records sent per minute after the live one: the firmware's NORMAL energy state
# (firmware/common/ws_policy.c backlog_limit). Stage 0 is always NORMAL. The firmware also
# stops a minute's drain at the first missed reply; the simulator does not model that, which
# does not change timeliness because the live reading still goes first every minute.
BACKLOG_PER_MINUTE = 5


class Node:
    def __init__(self,cfg,directory):
        self.cfg = cfg
        self.key = bytes.fromhex(cfg['radio_key'])
        self.nonces = Nonces(directory/'node-nonces.sqlite3',self.key,cfg['station_id'],KIND_OBS)
        self.db = sqlite3.connect(directory/'node-journal.sqlite3')
        full_flush(self.db)
        self.db.execute('CREATE TABLE IF NOT EXISTS boot (epoch INTEGER)')
        self.db.execute('CREATE TABLE IF NOT EXISTS pending (epoch INTEGER, seq INTEGER, data TEXT, PRIMARY KEY(epoch,seq))')
        self.db.execute('BEGIN IMMEDIATE')
        row = self.db.execute('SELECT epoch FROM boot').fetchone()
        self.epoch = (row[0] if row else 0)+1
        if self.epoch >= EPOCH_RESERVED:
            raise ValueError('Observation epoch exhausted')
        self.db.execute('DELETE FROM boot')
        self.db.execute('INSERT INTO boot VALUES (?)',(self.epoch,))
        self.db.commit()
        self.sequence = 0
        # Like the firmware: no trusted clock after boot until an authentic ACK arrives,
        # and a monotonic seconds-since-boot counter that clock faults do not affect.
        self.synced = False
        self.boot = None
        self.sent = set()      # counters of frames this node sealed (NACK echo check)
        self.abandoned = 0     # records dropped on an authentic NACK

    def close(self):
        self.db.close()
        self.nonces.db.close()

    def sample(self,now,fault=False,clock_offset=0,clock_known=True):
        """Synthetic, clearly named station; timestamps follow real 60-second cadence."""
        if self.boot is None:
            self.boot = now
        clock_known = clock_known and self.synced
        record = dict(version=VERSION,station=self.cfg['station'],session=str(self.epoch),
                      sequence=self.sequence,sampled_at=int(now+clock_offset) if clock_known else None,
                      uptime_s=int(now-self.boot),
                      time_quality='synchronized' if clock_known else 'unknown',
                      energy_state='normal',calibration_revision=0,
                      temperature_c=None if fault else round(21+math.sin(self.sequence/10),2),
                      humidity_pct=None if fault else round(45+math.cos(self.sequence/10),2),
                      quality='sensor_fault' if fault else 'valid')
        with self.db:
            self.db.execute('INSERT INTO pending VALUES (?,?,?)',(self.epoch,self.sequence,json.dumps(record)))
        self.sequence += 1
        return record

    def packet(self,record):
        frame = seal(self.key,self.cfg['station_id'],KIND_OBS,self.nonces,encode_observation(record))
        self.sent.add(frame_counter(frame))
        return frame

    def handle_reply(self,packet):
        """Route a gateway reply by its (authenticated) kind byte."""
        if frame_kind(packet) == KIND_NACK:
            return self.reject(packet)
        return self.acknowledge(packet)

    def reject(self,packet):
        """Authentic NACK: stop retrying that record. Only a NACK that echoes a frame
        this node sent is accepted; the gateway has kept the rejected frame."""
        epoch,seq,reason,echo = unpack_reply(unseal(self.key,self.cfg['station_id'],KIND_NACK,packet))
        if echo not in self.sent:
            raise ValueError('NACK does not answer a frame from this node')
        with self.db:
            removed = self.db.execute('DELETE FROM pending WHERE epoch=? AND seq=?',(epoch,seq)).rowcount
        self.abandoned += removed
        return reason

    def acknowledge(self,packet):
        """A replayed ACK cannot remove a different observation."""
        epoch,seq,_host_utc,_echo = unpack_reply(unseal(self.key,self.cfg['station_id'],KIND_ACK,packet))
        self.synced = True  # simulated clock follows the authenticated host time
        with self.db:
            self.db.execute('DELETE FROM pending WHERE epoch=? AND seq=?',(epoch,seq))

    def diagnostic(self,now,ack_signal=None):
        """A sealed health report (kind 4) with this simulated node's journal state."""
        pending = self.db.execute('SELECT count(*) FROM pending').fetchone()[0]
        rssi, snr = ack_signal or (SIGNAL_NONE, SIGNAL_NONE)
        report = DIAG.pack(self.epoch, int(max(0,now-(self.boot or now))), min(pending,U16_MAX), 0, 0,
                           min(self.abandoned,U16_MAX), 0, 0, 1, 0, 0x5eed0001, rssi, snr, 0, 1)
        return seal(self.key,self.cfg['station_id'],KIND_DIAG,self.nonces,report)

    def backfill(self,limit=None):
        limit = BACKLOG_PER_MINUTE if limit is None else limit
        return [json.loads(row[0]) for row in self.db.execute(
            'SELECT data FROM pending ORDER BY epoch,seq LIMIT ?',(limit,))]


class DemoReceiver:
    """`ws0 demo` only: stands in for the RX board and the node's health reports, so the dashboard
    shows every panel without hardware. RSSI/SNR and the RX counters are invented (a slow wander
    around a bench-like -40 dBm); nothing here is evidence."""
    ALIVE_S, DIAG_S = 60, 900

    def __init__(self, gateway, node, clock=time.time):
        self.gateway, self.node, self.clock = gateway, node, clock
        self.boot = clock()
        self.rng = random.Random()
        self.forwarded = self.acks = self.diags = self.crc_errors = self.hdr_errors = 0
        self.last_frame = b''
        self.next_alive = self.boot
        self.next_diag = self.boot + 5
        self.ack_signal = None

    def signal(self):
        phase = (self.clock() - self.boot) / 600
        return (round(-40 + 6 * math.sin(phase) + self.rng.uniform(-2, 2)),
                round(9 + 2 * math.cos(phase) + self.rng.uniform(-1, 1)))

    def deliver(self, frame):
        """Hand one node frame to the gateway as the serve loop would, recording radio telemetry."""
        telemetry = self.gateway.telemetry
        self.last_frame = bytes(frame)
        reply = self.gateway.receive(frame)
        self.forwarded += 1
        telemetry.frame(frame, self.gateway.last_outcome, delivered=None if reply is None else True)
        if reply is not None:
            self.acks += 1
            self.ack_signal = self.signal()
        rssi, snr = self.signal()
        telemetry.rx_line(f'#rx obs rssi={rssi} snr={snr}')
        return reply

    def bad_reception(self, now):
        """About two an hour, like ambient 915 MHz traffic: a CRC failure (the last frame with a few
        bits flipped) or a header failure."""
        if self.rng.random() >= 1 / 30:
            return
        if self.last_frame and self.rng.random() < 0.7:
            data = bytearray(self.last_frame)
            for _ in range(self.rng.randint(1, 4)):
                data[self.rng.randrange(len(data))] ^= 1 << self.rng.randrange(8)
            self.crc_errors += 1
            rssi, snr = self.signal()
            line = f'#rx crc len={len(data)} rssi={rssi} snr={snr} data={data.hex()}'
        else:
            self.hdr_errors += 1
            line = f'#rx hdr rssi={self.rng.randint(-125, -110)}'
        self.gateway.telemetry.rx_line(line, now)

    def tick(self, link_down=False):
        now = self.clock()
        if now >= self.next_alive:
            self.next_alive = now + self.ALIVE_S
            line = (f'#alive uptime={int(now - self.boot)} forwarded={self.forwarded} dropped=0 acks={self.acks} '
                    f'diag={self.diags} listening=1 relistens=0 uart_errors=0 stack_peak=1184 '
                    f'crc_errors={self.crc_errors} hdr_errors={self.hdr_errors} task_peak_us=850 task_peak=process '
                    f'isr_peak_us=40 isr_peak=SUBGHZ_Radio trace_drops=0')
            self.gateway.receiver_report(line, now)
            self.gateway.telemetry.rx_line(line, now)
            self.bad_reception(now)
        if now >= self.next_diag and not link_down:
            self.next_diag = now + self.DIAG_S
            self.diags += 1
            self.deliver(self.node.diagnostic(now, self.ack_signal))
