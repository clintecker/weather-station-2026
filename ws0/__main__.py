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
from .protocol import KIND_NACK, Nonces, frame_kind
from .service import Gateway, MQTT, http_server, load_config
from .simulator import BACKLOG_PER_MINUTE, DemoReceiver, Node
from .link import ReceiverLink
from .clock import HostClock
from .logfile import RotatingLog


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
    for name,kind in ([('gateway',2)] if hardware else [('node',1),('gateway',2)]):
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
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
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
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
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
        fields = dict(f.split('=',1) for f in status[1:].split()[1:] if '=' in f)
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


def handle_receiver_line(gateway, link, line, receiver_log, now=None):
    """One line from the RX board: a '#' diagnostic, or a hex frame to authenticate, store and
    answer. Everything goes to receiver.log (evidence); radio frames with their RSSI/SNR, RX
    #alive reports and RX events also go to SQLite for the dashboard (ws0/web.py Telemetry)."""
    telemetry = gateway.telemetry
    text = line.decode('ascii','replace')
    rx_seen = time.time() if now is None else now
    stamp = time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(rx_seen))
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
        if text.startswith('#rx drop') and quiet('rx_drop'):
            return
        if text.startswith('#'):
            # Receiver diagnostics (RSSI/SNR, drops, boots, alive): evidence, not data.
            receiver_log.write(f'{stamp} {text}\n')
            if text.startswith(('#alive ','#boot role=rx')):
                fields = dict(f.split('=',1) for f in text.split()[1:] if '=' in f)
                gateway.receiver = {'alive':True,'last_report':stamp,'last_seen':rx_seen,**fields}
            telemetry.rx_line(text,rx_seen)
        elif text:
            telemetry.muted = False
            frame = bytes.fromhex(text)
            ack = gateway.receive(frame)
            if ack is None:  # node health report: stored, never answered
                receiver_log.write(f'{stamp} diag {text}\n')
                telemetry.frame(frame,'diag',at=rx_seen)
                return
            kind = 'nack' if frame_kind(ack) == KIND_NACK else 'ack'
            sent = link.write(ack.hex().encode()+b'\n')
            duplicate = kind == 'ack' and (gateway.last_ingested or {}).get('duplicate')
            if duplicate and quiet('duplicate'):   # a replayed frame is answered, but not logged forever
                return
            receiver_log.write(f'{stamp} frame {text} -> {kind} {ack.hex()}'
                               f'{"" if sent else " (not delivered: serial link down)"}\n')
            telemetry.frame(frame,'duplicate' if duplicate else kind,delivered=sent,at=rx_seen)
            if kind == 'ack':  # the frame just stored, not the newest reading (backlog)
                print(json.dumps({'received_at':stamp,'observation':gateway.last_ingested}),flush=True)
    except (ValueError,UnicodeError,InvalidTag) as exc:
        if quiet('rejected'):
            return
        receiver_log.write(f'{stamp} rejected {type(exc).__name__}: {exc} {text}\n')
        print(f'Rejected frame: {type(exc).__name__}: {exc}',file=sys.stderr)
        telemetry.frame(frame,'rejected',detail=f'{type(exc).__name__}: {exc}',at=rx_seen)
    except (OSError, sqlite3.Error) as exc:
        # Commit failed (sqlite3 raises its own errors, not OSError): no ACK, the node keeps the
        # record and retries. The process must not exit: under a service manager it would only
        # restart into the same failure, and from a terminal it would stay down.
        receiver_log.write(f'{stamp} commit-failed {type(exc).__name__}: {exc}\n')
        print(f'Commit failed: {exc}',file=sys.stderr)
        telemetry.frame(frame,'commit_failed',detail=f'{type(exc).__name__}: {exc}',at=rx_seen)


def main():
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
    args = parser.parse_args()
    os.umask(0o077)
    if args.command == 'init':
        provision(args.directory,args.hardware,args.station,args.station_id)
        return
    cfg = load_config(args.directory/'gateway.json')
    if args.command == 'provision-node':
        if cfg['mode'] != 'hardware' or not args.serial:
            parser.error('provision-node requires a --hardware state directory and --serial')
        counter_state = node_counter_mark(args.directory)
        print_counter_mark(counter_state)
        provision_node(cfg,args.serial,epoch_floor(args.directory,cfg['station']),counter_state)
        return
    if args.command=='demo' and cfg['mode']!='simulation':
        parser.error('Demo requires a dedicated simulation configuration')
    if args.command=='serve' and not (args.serial or args.serial_number):
        parser.error('serve requires --serial or --serial-number')
    if args.log_file:
        sys.stdout = sys.stderr = RotatingLog(args.log_file)
    # launchd/systemd stop a service with SIGTERM: shut down as cleanly as Ctrl-C.
    # Windows: Ctrl-Break (sent by service wrappers and by `tests/test_stage0.py`) does the same.
    # Only the first stop request interrupts: a repeat (a second Ctrl-C, a service manager that
    # signals twice) would otherwise land inside the cleanup below and abort it with a traceback.
    stopping = []
    def stop(*_):
        if not stopping:
            stopping.append(True)
            raise KeyboardInterrupt
    for name in ('SIGINT', 'SIGTERM', 'SIGBREAK'):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), stop)
    gateway = Gateway(cfg,args.directory)
    server = http_server(gateway,cfg['http_port'])
    mqtt = MQTT(gateway) if cfg['mqtt']['enabled'] else None
    link = None
    node = Node(cfg,args.directory) if args.command=='demo' else None
    if node:
        # The demo node runs inside the gateway process and shares the host clock, so it
        # starts synchronized. A real node starts time-unknown (see TimeReconstruction tests).
        node.synced = True
    # Demo only: invented RSSI/SNR, RX #alive reports and node health reports, so the dashboard
    # has every panel to show without boards.
    demo_rx = DemoReceiver(gateway,node) if node else None
    receiver_log = None
    if args.command == 'serve':
        receiver_log = RotatingLog(args.directory/'receiver.log')
        def note(text):
            stamp = time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
            receiver_log.write(f'{stamp} {text}\n')
            print(f'{stamp} {text}',file=sys.stderr,flush=True)
            gateway.telemetry.event(text)
        # Short read timeout: the node's ACK window is 2 s, so frames are answered immediately.
        link = ReceiverLink(args.serial,args.serial_number,note)
        gateway.clock = HostClock(cfg.get('ntp_server','pool.ntp.org'),log=note).start()
    print(f"Stage 0 {cfg['mode']}; API http://127.0.0.1:{cfg['http_port']}/v1/status",flush=True)
    gateway.telemetry.event(f"#gateway start {args.command} mode={cfg['mode']}",kind='start',level='info')
    next_sample = time.monotonic()
    dropping = False
    next_tick = 0
    try:
        while True:
            if node and time.monotonic()>=next_sample:
                record = node.sample(time.time(),(args.directory/'sensor-fault').exists())
                dropping = (args.directory/'link-down').exists()
                if not dropping:
                    # Live first, then up to BACKLOG_PER_MINUTE history records (firmware NORMAL).
                    node.acknowledge(demo_rx.deliver(node.packet(record)))
                    for old in node.backfill(BACKLOG_PER_MINUTE):
                        node.acknowledge(demo_rx.deliver(node.packet(old)))
                print(json.dumps({'simulation':True,'sequence':record['sequence'],'link_down':dropping}),flush=True)
                next_sample = time.monotonic()+60
            if demo_rx:
                demo_rx.tick(link_down=dropping)
            if link:
                for line in link.poll():
                    handle_receiver_line(gateway,link,line,receiver_log)
                gateway.telemetry.tick()
                if not link.connected:
                    time.sleep(0.2)
                # RX liveness (gap G12): it reports every 60 s; three missed reports = silent.
                if gateway.receiver and gateway.receiver.get('alive') and \
                        time.time() - gateway.receiver['last_seen'] > 180:
                    gateway.receiver['alive'] = False
                    note('#gateway receiver-silent: no RX report for 180 s (check RX board, USB, watchdog)')
                if gateway.receiver and not gateway.receiver.get('alive') and \
                        time.time() - gateway.receiver['last_seen'] < 5:
                    gateway.receiver['alive'] = True
            if mqtt and time.monotonic()>=next_tick:
                mqtt.tick()
                next_tick = time.monotonic()+1
            if not link:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        if mqtt:
            mqtt.close()
        gateway.telemetry.event('#gateway stop',kind='stop',level='info')
        gateway.hub.close()  # ends open event streams, so their threads exit
        server.shutdown()
        server.server_close()
        gateway.store.db.close()
        gateway.nonces.db.close()
        if node:
            node.db.close()
            node.nonces.db.close()
        if link:
            link.close()
        if receiver_log:
            receiver_log.close()


if __name__=='__main__':
    main()
