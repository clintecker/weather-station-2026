"""Commands: provision an isolated demo, run it, or attach a future serial receiver."""
import argparse
import json
import os
import secrets
import signal
import sys
import time
from cryptography.exceptions import InvalidTag
from pathlib import Path
from .protocol import Nonces
from .service import Gateway, MQTT, http_server, load_config
from .simulator import Node
from .link import ReceiverLink
from .clock import HostClock


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


def provision_node(cfg, device):
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
        if fields.get('provisioned') == '1':
            if fields.get('station') == str(cfg['station_id']) and fields.get('kcv') == expected:
                print(f'Already provisioned with this station and key (kcv {expected}).')
                return
            raise SystemExit(f'Board already provisioned (station {fields.get("station")}, kcv {fields.get("kcv")}); '
                             'refusing to overwrite. Wipe it deliberately first.')
        port.write(f"PROVISION {cfg['station_id']} {cfg['radio_key']}\n".encode())
        reply = next((l for l in console_lines(port,time.monotonic()+5) if l.startswith(('#provisioned','#error'))),None)
        if reply != f"#provisioned station={cfg['station_id']} kcv={expected}":
            raise SystemExit(f'Provisioning failed: {reply!r}')
        boot = [l for l in console_lines(port,time.monotonic()+5)]
        print(f"Provisioned station {cfg['station_id']} (kcv {expected}); node says:")
        for line in boot:
            print('  '+line)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['init','demo','serve','provision-node'])
    parser.add_argument('--directory',type=Path,default=Path('run-demo'))
    parser.add_argument('--serial',help='serve: RX board serial device; provision-node: TX board')
    parser.add_argument('--serial-number',help='serve: find the RX board by its ST-LINK USB serial number '
                        '(survives replug and renamed ports; preferred for H01)')
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
        provision_node(cfg,args.serial)
        return
    if args.command=='demo' and cfg['mode']!='simulation':
        parser.error('Demo requires a dedicated simulation configuration')
    if args.command=='serve' and not (args.serial or args.serial_number):
        parser.error('serve requires --serial or --serial-number')
    # launchd/systemd stop a service with SIGTERM: shut down as cleanly as Ctrl-C.
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    gateway = Gateway(cfg,args.directory)
    server = http_server(gateway,cfg['http_port'])
    mqtt = MQTT(gateway) if cfg['mqtt']['enabled'] else None
    link = None
    node = Node(cfg,args.directory) if args.command=='demo' else None
    if node:
        # The demo node runs inside the gateway process and shares the host clock, so it
        # starts synchronized. A real node starts time-unknown (see TimeReconstruction tests).
        node.synced = True
    receiver_log = None
    if args.command == 'serve':
        receiver_log = (args.directory/'receiver.log').open('a',buffering=1)
        def note(text):
            stamp = time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
            receiver_log.write(f'{stamp} {text}\n')
            print(f'{stamp} {text}',file=sys.stderr,flush=True)
        # Short read timeout: the node's ACK window is 2 s, so frames are answered immediately.
        link = ReceiverLink(args.serial,args.serial_number,note)
        gateway.clock = HostClock(cfg.get('ntp_server','pool.ntp.org'),log=note).start()
    print(f"Stage 0 {cfg['mode']}; API http://127.0.0.1:{cfg['http_port']}/v1/status",flush=True)
    next_sample = time.monotonic()
    dropping = False
    next_tick = 0
    try:
        while True:
            if node and time.monotonic()>=next_sample:
                record = node.sample(time.time(),(args.directory/'sensor-fault').exists())
                dropping = (args.directory/'link-down').exists()
                if not dropping:
                    # Live first, then at most two history records per reporting period.
                    node.acknowledge(gateway.receive(node.packet(record)))
                    for old in node.backfill(2):
                        node.acknowledge(gateway.receive(node.packet(old)))
                print(json.dumps({'simulation':True,'sequence':record['sequence'],'link_down':dropping}),flush=True)
                next_sample = time.monotonic()+60
            if link:
                for line in link.poll():
                    text = line.decode('ascii','replace')
                    stamp = time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
                    try:
                        if text.startswith('#'):
                            # Receiver diagnostics (RSSI/SNR, drops, boots): evidence, not data.
                            receiver_log.write(f'{stamp} {text}\n')
                        elif text:
                            frame = bytes.fromhex(text)
                            ack = gateway.receive(frame)
                            kind = 'nack' if ack[3] == 3 else 'ack'
                            sent = link.write(ack.hex().encode()+b'\n')
                            receiver_log.write(f'{stamp} frame {text} -> {kind} {ack.hex()}'
                                               f'{"" if sent else " (not delivered: serial link down)"}\n')
                            print(json.dumps({'received_at':stamp,'latest':gateway.store.latest(cfg['station'])['observation']}),flush=True)
                    except (ValueError,UnicodeError,InvalidTag) as exc:
                        receiver_log.write(f'{stamp} rejected {type(exc).__name__}: {exc} {text}\n')
                        print(f'Rejected frame: {type(exc).__name__}: {exc}',file=sys.stderr)
                    except OSError as exc:
                        # Commit failed: no ACK, the node keeps the record and retries.
                        receiver_log.write(f'{stamp} commit-failed {type(exc).__name__}: {exc}\n')
                        print(f'Commit failed: {exc}',file=sys.stderr)
                if not link.connected:
                    time.sleep(0.2)
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
