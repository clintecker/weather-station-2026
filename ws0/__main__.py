"""Commands: provision an isolated demo, run it, or attach a future serial receiver."""
import argparse
import json
import os
import secrets
import signal
import sqlite3
import sys
import time
from cryptography.exceptions import InvalidTag
from pathlib import Path
from gateway import open_read_only

from .protocol import KIND_ACK, KIND_OBS, Nonces
from .service import CounterRegression, Gateway, MQTT, Replay, http_server, load_config
from .simulator import BACKLOG_PER_MINUTE, DemoReceiver, Node
from .link import ReceiverLink
from .clock import HostClock
from .logfile import RotatingLog
from .web import SchemaDrift, line_fields, utc_stamp


def provision(directory, hardware=False, station='simulation-01', station_id=1):
    """Generate unique local secrets; existing state is never reset implicitly.

    Hardware stations keep their node-direction nonce state on the MCU, so only the
    gateway (ACK) allocator is created here; the key reaches the node over USB only."""
    directory.mkdir(mode=0o700,parents=True,exist_ok=False)
    key = secrets.token_bytes(16)
    cfg = {'station':station,'station_id':station_id,'mode':'hardware' if hardware else 'simulation',
           'radio_key':key.hex(),'api_token':secrets.token_urlsafe(32),
           'http_port':8088,'mqtt':{'enabled':False,'host':'127.0.0.1','port':1883,'tls':False}}
    config = directory/'gateway.json'
    config.write_text(json.dumps(cfg,indent=2)+'\n')
    config.chmod(0o600)
    load_config(config)
    for name,kind in ([('gateway',KIND_ACK)] if hardware else [('node',KIND_OBS),('gateway',KIND_ACK)]):
        Nonces(directory/f'{name}-nonces.sqlite3',key,station_id,kind,create=True).db.close()
    print(f'Created {directory}; secrets stay in gateway.json')


def key_check(key):
    """First 3 bytes of AES-ECB(key, 0^16): identifies a key without revealing it."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    return Cipher(algorithms.AES(key),modes.ECB()).encryptor().update(bytes(16))[:3].hex()


def console_lines(port, deadline):
    """Yield decoded '#' console lines from a node until the deadline."""
    while time.monotonic() < deadline:
        line = port.readline().decode('ascii','replace').strip()
        if line:
            yield line


def epoch_floor(directory, station):
    """Gap G5: one above every boot epoch the gateway has stored for this station, so a
    wiped and re-provisioned node can never reuse an observation identity."""
    path = directory/'observations.sqlite3'
    if not path.exists():
        return 0
    db = open_read_only(path)
    try:   # Store creates all three tables
        values = [db.execute(f'SELECT max(CAST(session AS INTEGER)) FROM {table} WHERE station=?',
                             (station,)).fetchone()[0] for table in ('observations','rejections','diagnostics')]
    finally:
        db.close()
    highest = max((v for v in values if v is not None and v < 0xFFFFFFFF), default=0)
    return highest + 1 if highest else 0


def node_counter_mark(directory):
    """Review item P4: the gateway's stored high-water mark of the node counter (OBS + DIAG)
    for this state directory, or None if there is no such state yet."""
    path = directory/'gateway-nonces.sqlite3'
    if not path.exists():
        return None
    db = open_read_only(path)
    try:
        row = db.execute('SELECT max_counter,regressions,last_regression FROM node_counter').fetchone()
    finally:
        db.close()
    if row is None:
        return {'max_node_counter':0,'counter_regression':0,'last_regression_counter':None}
    return {'max_node_counter':row[0],'counter_regression':row[1],'last_regression_counter':row[2]}


def print_counter_mark(state):
    if state is None:
        print('Gateway node-counter high-water mark: none (no gateway state yet)')
        return
    print(f"Gateway node-counter high-water mark: {state['max_node_counter']} "
          f"(counter regressions: {state['counter_regression']})")
    if state['counter_regression']:
        print(f"ALARM: possible key reuse (last offending counter {state['last_regression_counter']}): "
              're-key the node with a new state directory (failure-modes R5)')


def check_node_counter(fields, state):
    """A board whose next counter is at or below the mark would repeat nonces under this key."""
    if state is None:
        return
    ctr = fields.get('ctr', '')
    if not ctr.isdigit():   # STATUS always reports the full 64-bit counter (u64_text)
        raise SystemExit(f'Node STATUS has no usable ctr= ({ctr!r}): cannot check for nonce reuse.')
    mark = state['max_node_counter']
    if int(ctr) <= mark:
        raise SystemExit(f'Node counter ctr={ctr} is at or below the gateway high-water mark {mark}: '
                         'this key would repeat AES-CCM nonces. Use a NEW key (ws0 init into a new directory).')


def provision_node(cfg, device, floor=0, counter_state=None):
    """Wired provisioning: write station ID and key to an unprovisioned TX board, then
    confirm by key check value. Never wipes; a provisioned board must be wiped explicitly."""
    import serial
    expected = key_check(bytes.fromhex(cfg['radio_key']))
    with serial.Serial(device,115200,timeout=0.5,write_timeout=1) as port:
        port.reset_input_buffer()
        port.write(b'STATUS\n')
        status = next((l for l in console_lines(port,time.monotonic()+3) if l.startswith('#status role=')),None)
        if not status or 'role=tx' not in status:
            raise SystemExit(f'{device}: no TX node status (got {status!r}); is this the TX board?')
        fields = line_fields(status)
        check_node_counter(fields,counter_state)
        if fields.get('provisioned') == '1':
            if fields.get('station') == str(cfg['station_id']) and fields.get('kcv') == expected:
                print(f'Already provisioned with this station and key (kcv {expected}).')
                return
            raise SystemExit(f'Board already provisioned (station {fields.get("station")}, kcv {fields.get("kcv")}); '
                             'refusing to overwrite. Wipe it deliberately first.')
        port.write(f"PROVISION {cfg['station_id']} {cfg['radio_key']} {floor}\n".encode())
        reply = next((l for l in console_lines(port,time.monotonic()+5) if l.startswith(('#provisioned','#error'))),None)
        if reply != f"#provisioned station={cfg['station_id']} kcv={expected} epoch_floor={floor}":
            raise SystemExit(f'Provisioning failed: {reply!r}')
        boot = [l for l in console_lines(port,time.monotonic()+5)]
        print(f"Provisioned station {cfg['station_id']} (kcv {expected}); node says:")
        for line in boot:
            print('  '+line)


def _receiver_diagnostic(gateway, text, receiver_log, stamp, rx_seen):
    """Receiver diagnostics (RSSI/SNR, drops, boots, alive): evidence, not data."""
    receiver_log.write(f'{stamp} {text}\n')
    if text.startswith(('#alive ','#boot role=rx')):
        gateway.receiver_report(text,rx_seen)
    gateway.telemetry.rx_line(text,rx_seen)


def _answer_frame(gateway, link, frame, text, receiver_log, stamp, rx_seen, quiet):
    """Authenticate and store one frame and send its ACK/NACK; a node health report is stored
    but never answered. A replay is answered but its log line is rate-limited (quiet)."""
    telemetry = gateway.telemetry
    ack = gateway.receive(frame)
    outcome = gateway.last_outcome
    if ack is None:  # node health report: stored, never answered
        receiver_log.write(f'{stamp} diag {text}\n')
        telemetry.frame(frame,outcome,at=rx_seen)
        return
    sent = link.write(ack.hex().encode()+b'\n')
    if outcome == 'duplicate' and quiet('duplicate'):   # a replay is answered, not logged forever
        return
    kind = 'nack' if outcome == 'nack' else 'ack'
    receiver_log.write(f'{stamp} frame {text} -> {kind} {ack.hex()}'
                       f'{"" if sent else " (not delivered: serial link down)"}\n')
    telemetry.frame(frame,outcome,delivered=sent,at=rx_seen)
    if kind == 'ack':  # the frame just stored, not the newest reading (backlog)
        print(json.dumps({'received_at':stamp,'observation':gateway.last_ingested}),flush=True)


def handle_receiver_line(gateway, link, line, receiver_log, now=None):
    """One line from the RX board: a '#' diagnostic, or a hex frame to authenticate, store and
    answer. Everything goes to receiver.log (evidence); radio frames with their RSSI/SNR, RX
    #alive reports and RX events also go to SQLite for the dashboard (ws0/web.py Telemetry)."""
    telemetry = gateway.telemetry
    text = line.decode('ascii','replace')
    rx_seen = time.time() if now is None else now
    stamp = utc_stamp(rx_seen)
    frame = None

    def quiet(key):
        """GW6: True if this noise line is over budget (drop it); else log any suppressed count."""
        allowed, suppressed = telemetry.throttle.allow(key,rx_seen)
        telemetry.muted = not allowed
        if allowed and suppressed:
            note = f'#gateway suppressed {suppressed} {key} lines (rate limit; disk protection)'
            receiver_log.write(f'{stamp} {note}\n')
            telemetry.event(note,kind='suppressed',level='warn',at=rx_seen)
        return not allowed
    try:
        if text.startswith('#rx obs') and telemetry.muted:
            telemetry.muted = False   # RSSI of a throttled frame
            return
        # Lines any nearby radio can cause at will (bad packets, CRC errors): rate-limited (GW6).
        # CRC and header failures share one budget; what it drops is counted (fault_summary).
        for prefix, key in (('#rx drop', 'rx_drop'), ('#rx crc', 'rx_fault'), ('#rx hdr', 'rx_fault'),
                            ('#relisten', 'relisten')):
            if text.startswith(prefix) and quiet(key):
                return
        if text.startswith('#'):
            _receiver_diagnostic(gateway,text,receiver_log,stamp,rx_seen)
        elif text:
            telemetry.muted = False
            frame = bytes.fromhex(text)
            _answer_frame(gateway,link,frame,text,receiver_log,stamp,rx_seen,quiet)
    except (ValueError,UnicodeError,InvalidTag) as exc:
        # A counter regression (possible key reuse) is always logged: noise must not hide it.
        # Replays of captured frames have their own budget, so they cannot use up garbage's.
        if not isinstance(exc, CounterRegression) and quiet('replay' if isinstance(exc, Replay) else 'rejected'):
            return
        receiver_log.write(f'{stamp} rejected {type(exc).__name__}: {exc} {text}\n')
        print(f'Rejected frame: {type(exc).__name__}: {exc}',file=sys.stderr)
        telemetry.frame(frame,'rejected',detail=f'{type(exc).__name__}: {exc}',at=rx_seen)
    except (OSError, sqlite3.Error, OverflowError) as exc:
        # Commit failed (sqlite3 raises its own errors, not OSError; OverflowError is an integer
        # SQLite cannot store): no ACK, the node keeps the record and retries. The process must not exit: under a service manager it would only
        # restart into the same failure, and from a terminal it would stay down.
        receiver_log.write(f'{stamp} commit-failed {type(exc).__name__}: {exc}\n')
        print(f'Commit failed: {exc}',file=sys.stderr)
        telemetry.frame(frame,'commit_failed',detail=f'{type(exc).__name__}: {exc}',at=rx_seen)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['init','demo','serve','provision-node'])
    parser.add_argument('--directory',type=Path,default=Path('run-demo'))
    parser.add_argument('--serial',help='serve: RX board serial device; provision-node: TX board')
    parser.add_argument('--serial-number',help='serve: find the RX board by its ST-LINK USB serial number '
                        '(survives replug and renamed ports; preferred for H01)')
    parser.add_argument('--log-file',type=Path,help='serve/demo: write output and errors to this file, '
                        'rotated by size (ws0/logfile.py), instead of the terminal. For service managers.')
    parser.add_argument('--hardware',action='store_true',help='init: real station, not simulation')
    parser.add_argument('--station',default='simulation-01',help='init: station name')
    parser.add_argument('--station-id',type=int,default=1,help='init: numeric station ID')
    return parser


def run_provision_node(parser, args, cfg):
    if cfg['mode'] != 'hardware' or not args.serial:
        parser.error('provision-node requires a --hardware state directory and --serial')
    counter_state = node_counter_mark(args.directory)
    print_counter_mark(counter_state)
    provision_node(cfg,args.serial,epoch_floor(args.directory,cfg['station']),counter_state)


def check_serving_args(parser, args, cfg):
    if args.command=='demo' and cfg['mode']!='simulation':
        parser.error('Demo requires a dedicated simulation configuration')
    if args.command=='serve' and not (args.serial or args.serial_number):
        parser.error('serve requires --serial or --serial-number')


def install_stop_handlers():
    """launchd/systemd stop a service with SIGTERM: shut down as cleanly as Ctrl-C.
    Windows: Ctrl-Break (sent by service wrappers and by `tests/test_stage0.py`) does the same.
    Only the first stop request interrupts: a repeat (a second Ctrl-C, a service manager that
    signals twice) would otherwise land inside the cleanup and abort it with a traceback.
    After the first one, further stop signals are ignored by the OS itself (SIG_IGN): Python resets
    its own handlers to the default while the interpreter exits, so a repeat arriving then
    would otherwise kill the process with SIGTERM instead of a clean exit 0."""
    stop_signals = [getattr(signal, n) for n in ('SIGINT', 'SIGTERM', 'SIGBREAK') if hasattr(signal, n)]
    def stop(*_):
        for s in stop_signals:
            signal.signal(s, signal.SIG_IGN)
        raise KeyboardInterrupt
    for s in stop_signals:
        signal.signal(s, stop)


class Services:
    """A running gateway, its HTTP server and optional MQTT publisher, and what feeds it: the
    in-process demo node with its simulated receiver (demo) or the RX board's serial link (serve)."""
    def __init__(self, command, directory, cfg):
        self.directory = directory
        self.gateway = Gateway(cfg,directory)
        self.server = http_server(self.gateway,cfg['http_port'])
        self.mqtt = MQTT(self.gateway) if cfg['mqtt']['enabled'] else None
        self.link = self.node = self.demo_rx = self.receiver_log = None
        if command == 'demo':
            self.node = Node(cfg,directory)
            # The demo node runs inside the gateway process and shares the host clock, so it
            # starts synchronized. A real node starts time-unknown (see TimeReconstruction tests).
            self.node.synced = True
            # Demo only: invented RSSI/SNR, RX #alive reports and node health reports, so the
            # dashboard has every panel to show without boards.
            self.demo_rx = DemoReceiver(self.gateway,self.node)
        self.dropping = False

    def attach_receiver(self, cfg, serial, serial_number):
        self.receiver_log = RotatingLog(self.directory/'receiver.log')
        # Short read timeout: the node's ACK window is 2 s, so frames are answered immediately.
        self.link = ReceiverLink(serial,serial_number,self.note)
        self.gateway.clock = HostClock(cfg.get('ntp_server','pool.ntp.org'),log=self.note).start()

    def note(self, text):
        stamp = utc_stamp(time.time())
        self.receiver_log.write(f'{stamp} {text}\n')
        print(f'{stamp} {text}',file=sys.stderr,flush=True)
        self.gateway.telemetry.event(text)

    def sample_demo(self):
        """One demo minute: sample (a sensor-fault file fails the sensor), then unless a link-down
        file exists deliver the live record and up to BACKLOG_PER_MINUTE history records
        (firmware NORMAL)."""
        node, directory = self.node, self.directory
        record = node.sample(time.time(),(directory/'sensor-fault').exists())
        self.dropping = (directory/'link-down').exists()
        if not self.dropping:
            node.acknowledge(self.demo_rx.deliver(node.packet(record)))
            for old in node.backfill(BACKLOG_PER_MINUTE):
                node.acknowledge(self.demo_rx.deliver(node.packet(old)))
        print(json.dumps({'simulation':True,'sequence':record['sequence'],'link_down':self.dropping}),flush=True)

    def poll_receiver(self):
        gateway = self.gateway
        for line in self.link.poll():
            handle_receiver_line(gateway,self.link,line,self.receiver_log)
        if not self.link.connected:
            time.sleep(0.2)
        # RX liveness (gap G12): it reports every 60 s; three missed reports = silent.
        if gateway.receiver and gateway.receiver.get('alive') and \
                time.time() - gateway.receiver['last_seen'] > 180:
            gateway.receiver['alive'] = False
            self.note('#gateway receiver-silent: no RX report for 180 s (check RX board, USB, watchdog)')

    def serve_forever(self):
        """Until KeyboardInterrupt (a stop signal): demo samples each minute, the serial link is
        polled continuously, MQTT ticks each second."""
        next_sample = time.monotonic()
        next_tick = 0
        while True:
            if self.node and time.monotonic()>=next_sample:
                self.sample_demo()
                next_sample = time.monotonic()+60
            if self.demo_rx:
                self.demo_rx.tick(link_down=self.dropping)
            if self.link:
                self.poll_receiver()
            self.gateway.telemetry.tick()   # demo too: its simulated RX reports bad receptions
            if self.mqtt and time.monotonic()>=next_tick:
                self.mqtt.tick()
                next_tick = time.monotonic()+1
            if not self.link:
                time.sleep(1)

    def close(self):
        if self.mqtt:
            self.mqtt.close()
        self.gateway.telemetry.event('#gateway stop',kind='stop',level='info')
        self.gateway.hub.close()  # ends open event streams, so their threads exit
        self.server.shutdown()
        self.server.server_close()
        self.gateway.close()
        if self.node:
            self.node.close()
        if self.link:
            self.link.close()
        if self.receiver_log:
            self.receiver_log.close()


def main():
    parser = build_parser()
    args = parser.parse_args()
    os.umask(0o077)
    if args.command == 'init':
        provision(args.directory,args.hardware,args.station,args.station_id)
        return
    cfg = load_config(args.directory/'gateway.json')
    if args.command == 'provision-node':
        run_provision_node(parser,args,cfg)
        return
    check_serving_args(parser,args,cfg)
    if args.log_file:
        sys.stdout = sys.stderr = RotatingLog(args.log_file)
    install_stop_handlers()
    try:
        services = Services(args.command,args.directory,cfg)
    except SchemaDrift as exc:
        raise SystemExit(f'ws0: {exc}') from None
    if args.command == 'serve':
        services.attach_receiver(cfg,args.serial,args.serial_number)
    print(f"Stage 0 {cfg['mode']}; API http://127.0.0.1:{cfg['http_port']}/v1/status",flush=True)
    services.gateway.telemetry.event(f"#gateway start {args.command} mode={cfg['mode']}",kind='start',level='info')
    try:
        services.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        services.close()


if __name__=='__main__':
    main()
