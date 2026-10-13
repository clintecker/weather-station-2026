"""Persistent simulated node: journal before send, delete only after valid ACK."""
import json
import math
import sqlite3
from .protocol import ACK, KIND_ACK, KIND_NACK, NACK, Nonces, encode_observation, frame_counter, seal, unseal


class Node:
    def __init__(self,cfg,directory):
        self.cfg = cfg
        self.key = bytes.fromhex(cfg['radio_key'])
        self.nonces = Nonces(directory/'node-nonces.sqlite3',self.key,cfg['station_id'],1)
        self.db = sqlite3.connect(directory/'node-journal.sqlite3')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS boot (epoch INTEGER)')
        self.db.execute('CREATE TABLE IF NOT EXISTS pending (epoch INTEGER, seq INTEGER, data TEXT, PRIMARY KEY(epoch,seq))')
        self.db.execute('BEGIN IMMEDIATE')
        row = self.db.execute('SELECT epoch FROM boot').fetchone()
        self.epoch = (row[0] if row else 0)+1
        if self.epoch >= 2**32:
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

    def sample(self,now,fault=False,clock_offset=0,clock_known=True):
        """Synthetic, clearly named station; timestamps follow real 60-second cadence."""
        if self.boot is None:
            self.boot = now
        clock_known = clock_known and self.synced
        record = dict(version=2,station=self.cfg['station'],session=str(self.epoch),
                      sequence=self.sequence,sampled_at=int(now+clock_offset) if clock_known else None,
                      uptime_s=int(now-self.boot),
                      time_quality='synchronized' if clock_known else 'unknown',
                      temperature_c=None if fault else round(21+math.sin(self.sequence/10),2),
                      humidity_pct=None if fault else round(45+math.cos(self.sequence/10),2),
                      quality='sensor_fault' if fault else 'valid')
        with self.db:
            self.db.execute('INSERT INTO pending VALUES (?,?,?)',(self.epoch,self.sequence,json.dumps(record)))
        self.sequence += 1
        return record

    def packet(self,record):
        frame = seal(self.key,self.cfg['station_id'],1,self.nonces,encode_observation(record))
        self.sent.add(frame_counter(frame))
        return frame

    def handle_reply(self,packet):
        """Route a gateway reply by its (authenticated) kind byte."""
        if len(packet) > 3 and packet[3] == KIND_NACK:
            return self.reject(packet)
        return self.acknowledge(packet)

    def reject(self,packet):
        """Authentic NACK: stop retrying that record (gap G2). Only a NACK that echoes a frame
        this node sent is accepted; the gateway has kept the rejected frame."""
        epoch,seq,reason,_reserved,echo = NACK.unpack(unseal(self.key,self.cfg['station_id'],KIND_NACK,packet))
        if echo not in self.sent:
            raise ValueError('NACK does not answer a frame from this node')
        with self.db:
            removed = self.db.execute('DELETE FROM pending WHERE epoch=? AND seq=?',(epoch,seq)).rowcount
        self.abandoned += removed
        return reason

    def acknowledge(self,packet):
        """A replayed ACK cannot remove a different observation."""
        epoch,seq,_host_utc,_echo = ACK.unpack(unseal(self.key,self.cfg['station_id'],2,packet))
        self.synced = True  # simulated clock follows the authenticated host time
        with self.db:
            self.db.execute('DELETE FROM pending WHERE epoch=? AND seq=?',(epoch,seq))

    def backfill(self,limit=2):
        return [json.loads(row[0]) for row in self.db.execute(
            'SELECT data FROM pending ORDER BY epoch,seq LIMIT ?',(limit,))]
