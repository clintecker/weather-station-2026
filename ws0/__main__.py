"""Commands: provision an isolated demo, run it, or attach a future serial receiver."""
import argparse
import json
import os
import secrets
import sys
import time
from cryptography.exceptions import InvalidTag
from pathlib import Path
from .protocol import Nonces
from .service import Gateway, MQTT, http_server, load_config
from .simulator import Node


def provision(directory):
    """Generate unique local secrets; existing state is never reset implicitly."""
    directory.mkdir(mode=0o700,parents=True,exist_ok=False)
    key = secrets.token_bytes(16)
    cfg = {'station':'simulation-01','station_id':1,'mode':'simulation',
           'radio_key':key.hex(),'api_token':secrets.token_urlsafe(32),
           'http_port':8088,'mqtt':{'enabled':False,'host':'127.0.0.1','port':1883,'tls':False}}
    config = directory/'gateway.json'
    config.write_text(json.dumps(cfg,indent=2)+'\n')
    config.chmod(0o600)
    for name,kind in [('node',1),('gateway',2)]:
        Nonces(directory/f'{name}-nonces.sqlite3',key,1,kind,create=True).db.close()
    print(f'Created {directory}; secrets stay in gateway.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['init','demo','serve'])
    parser.add_argument('--directory',type=Path,default=Path('run-demo'))
    parser.add_argument('--serial',help='Receiver serial device; future firmware emits hex frames')
    args = parser.parse_args()
    os.umask(0o077)
    if args.command == 'init':
        provision(args.directory)
        return
    cfg = load_config(args.directory/'gateway.json')
    if args.command=='demo' and cfg['mode']!='simulation':
        parser.error('Demo requires a dedicated simulation configuration')
    if args.command=='serve' and not args.serial:
        parser.error('serve requires --serial')
    gateway = Gateway(cfg,args.directory)
    server = http_server(gateway,cfg['http_port'])
    mqtt = MQTT(gateway) if cfg['mqtt']['enabled'] else None
    serial_port = None
    node = Node(cfg,args.directory) if args.command=='demo' else None
    if args.serial:
        import serial
        serial_port = serial.Serial(args.serial,115200,timeout=1,write_timeout=1)
    print(f"Stage 0 {cfg['mode']}; API http://127.0.0.1:{cfg['http_port']}/v1/status",flush=True)
    next_sample = time.monotonic()
    dropping = False
    serial_buffer = b''
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
            if serial_port:
                # Accumulate partial reads until a newline; bound memory and reject overlong frames.
                fragment = serial_port.read_until(b'\n',size=257)
                if fragment:
                    serial_buffer += fragment
                    if len(serial_buffer)>256:
                        serial_buffer = b''
                        print('Rejected oversized serial frame',file=sys.stderr)
                    elif serial_buffer.endswith(b'\n'):
                        try:
                            frame = bytes.fromhex(serial_buffer.decode('ascii').strip())
                            ack = gateway.receive(frame)
                            serial_port.write(ack.hex().encode()+b'\n')
                        except (ValueError,UnicodeError,InvalidTag) as exc:
                            print(f'Rejected frame: {type(exc).__name__}',file=sys.stderr)
                        finally:
                            serial_buffer = b''
            if mqtt:
                mqtt.tick()
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
        if serial_port:
            serial_port.close()


if __name__=='__main__':
    main()
