"""Persistent simulated node: journal before send, delete only after valid ACK."""
import json
import math
import random
import sqlite3
import time
from gateway import full_flush
from .fields import quality
from .protocol import (CHG_CHARGING, CHG_POWER_GOOD, EPOCH_RESERVED, FIT_CHARGE_CURRENT, FIT_CHARGER_STATUS, FIT_GAUGE,
                       FIT_MCU_SUPPLY, FIT_MONITOR_TEMP, RESET_CAUSES, SIGNAL_NONE, VERSION, KIND_ACK, KIND_DIAG, KIND_NACK,
                       KIND_OBS, Nonces, encode_observation, frame_counter, frame_kind, pack_diag, seal, unpack_reply, unseal)
U16_MAX = 2**16 - 1   # the health report's u16 counts saturate
# The health slots a phase A node has a source for (the fitted byte, design section 6.1): VDDA, the
# INA228 die, the gauge, the CHG/PGOOD pins and ISET; 0x2F, as mod_power.c sends.
PHASE_A_FITTED = FIT_MCU_SUPPLY | FIT_MONITOR_TEMP | FIT_GAUGE | FIT_CHARGER_STATUS | FIT_CHARGE_CURRENT

# Simulated phase A power (power telemetry design sections 2 and 3): a 1S3P 6600 mAh pack, one
# charger input whose source is not identified, the station drawing LOAD_MA from the cell at night.
# The sun rises at 06:00 and sets at 18:00 UTC. Invented numbers, never evidence.
DAY_S, PACK_MAH, LOAD_MA, CHARGE_MA = 86_400, 6600, 35, 900
OUT_REG_MV = 4400   # the charger's OUT while it has input power (load_mv: the battery INA228 VBUS on OUT)
PHASE_A_POWER = ('batt_mv', 'batt_current_ma', 'energy_in_mwh', 'energy_out_mwh', 'charge_in_mah', 'charge_out_mah',
                 'load_mv', 'charger_input_mv')   # the phase A fields; the source rails (29-33) are absent


def power_state(now):
    """The simulated pack and charger at UTC time now: signed battery current (+ charging), SOC and its rate."""
    angle = 2 * math.pi * (now % DAY_S) / DAY_S
    sun = max(0.0, -math.cos(angle))                     # 0 at night, 1 at noon
    charge_ma = round(CHARGE_MA * sun)
    batt_ma = charge_ma - LOAD_MA
    soc = 65 - 15 * math.sin(angle)                      # rises through the day, falls through the night
    return dict(sun=sun, charge_ma=charge_ma, batt_ma=batt_ma, soc=soc, soc_rate=100 * batt_ma / PACK_MAH,
                batt_mv=round(3330 + 9 * soc + charge_ma / 10))

# Backlog records sent per minute after the live one: the firmware's NORMAL energy state
# (firmware/common/ws_policy.c backlog_limit). The bench prototype is always NORMAL. The firmware also
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
        self.flow = dict(energy_in_mwh=0.0, energy_out_mwh=0.0, charge_in_mah=0.0, charge_out_mah=0.0)
        self.flow_at = None    # battery counters since boot: they restart at 0 each epoch

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
                      **self.power(now,fault))
        record['quality'] = quality(record)
        with self.db:
            self.db.execute('INSERT INTO pending VALUES (?,?,?)',(self.epoch,self.sequence,json.dumps(record)))
        self.sequence += 1
        return record

    def power(self,now,fault=False):
        """The phase A power set of one minute: battery V and signed I, the battery counters (non-decreasing
        within an epoch), OUT and the unattributed charger input (0 mV at night). A faulted minute
        sends them INVALID, never absent (design section 5.3)."""
        state = power_state(now)
        hours = 0 if self.flow_at is None else max(0, now - self.flow_at) / 3600
        self.flow_at = now
        mah = abs(state['batt_ma']) * hours
        side = 'in' if state['batt_ma'] > 0 else 'out'
        self.flow[f'charge_{side}_mah'] += mah
        self.flow[f'energy_{side}_mwh'] += mah * state['batt_mv'] / 1000
        if fault:
            return dict.fromkeys(PHASE_A_POWER)
        powered = state['sun'] > 0
        return dict(batt_mv=state['batt_mv'], batt_current_ma=state['batt_ma'],
                    **{name: int(value) for name, value in self.flow.items()},
                    load_mv=OUT_REG_MV if powered else state['batt_mv'] - 10,
                    charger_input_mv=round(5000 + 1000 * state['sun']) if powered else 0)

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
        report = pack_diag(epoch=self.epoch, uptime=int(max(0,now-(self.boot or now))), pending=min(pending,U16_MAX),
                           lost=0, torn=0, abandoned=min(self.abandoned,U16_MAX), no_ack=0, rejects=0,
                           reset_cause=RESET_CAUSES.index(self.reset_cause()), link=0, build=0x5eed0001, rssi=rssi, snr=snr, crashes=0, energy=1, **self.health(now))
        return seal(self.key,self.cfg['station_id'],KIND_DIAG,self.nonces,report)

    def reset_cause(self):
        """The first boot (epoch 1) is a power-on; every later epoch is a pin reset (a reset button or
        a reflash), which keeps the backup registers and so the boot count."""
        return 'power' if self.epoch <= 1 else 'pin'

    def health(self,now):
        """The slow phase A items (design section 3.3). Boots since power-up follow fault_boot_note
        (design section 6.2): a power-on zeroes the count and adds one, so it is 1 after epoch 1; each
        pin reset adds one, so epoch n reports n. The charger-reported input, battery voltage and the
        temperatures are not measured in phase A: none codes, their fitted bits clear."""
        state = power_state(now)
        powered, charging = state['sun'] > 0, state['charge_ma'] > 0
        boots = 1 if self.reset_cause() == 'power' else min(self.epoch,U16_MAX)
        return dict(fitted=PHASE_A_FITTED, boots=boots, tx_timeouts=0, i2c_recoveries=0,
                    vdda_mv=3300 + round(4 * math.sin(now / 3000)), monitor_temp=round(250 + 80 * state['sun']),
                    soc=round(state['soc'] * 256), soc_rate=round(state['soc_rate'] * 10),
                    charger_status=(CHG_POWER_GOOD if powered else 0) | (CHG_CHARGING if charging else 0),
                    chg_batt_ma=state['charge_ma'] if powered else 0)

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
