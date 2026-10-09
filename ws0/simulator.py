"""Persistent simulated node: journal before send, delete only after valid ACK."""
import json
import math
import sqlite3
from .protocol import ACK, Nonces, encode_observation, seal, unseal


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

    def sample(self,now,fault=False):
        """Synthetic, clearly named station; timestamps follow real 60-second cadence."""
        record = dict(version=1,station=self.cfg['station'],session=str(self.epoch),
                      sequence=self.sequence,sampled_at=int(now),time_quality='synchronized',
                      temperature_c=None if fault else round(21+math.sin(self.sequence/10),2),
                      humidity_pct=None if fault else round(45+math.cos(self.sequence/10),2),
                      quality='sensor_fault' if fault else 'valid')
        with self.db:
            self.db.execute('INSERT INTO pending VALUES (?,?,?)',(self.epoch,self.sequence,json.dumps(record)))
        self.sequence += 1
        return record

    def packet(self,record):
        return seal(self.key,self.cfg['station_id'],1,self.nonces,encode_observation(record))

    def acknowledge(self,packet):
        """A replayed ACK cannot remove a different observation."""
        epoch,seq = ACK.unpack(unseal(self.key,self.cfg['station_id'],2,packet))
        with self.db:
            self.db.execute('DELETE FROM pending WHERE epoch=? AND seq=?',(epoch,seq))

    def backfill(self,limit=2):
        return [json.loads(row[0]) for row in self.db.execute(
            'SELECT data FROM pending ORDER BY epoch,seq LIMIT ?',(limit,))]
