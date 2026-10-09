"""Read local gateway status without echoing credentials to the terminal."""
import argparse
import json
from pathlib import Path
from urllib.request import Request,urlopen
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--directory',type=Path,default=Path('run-demo'))
args=parser.parse_args()
config=json.loads((args.directory/'gateway.json').read_text())
request=Request(f"http://127.0.0.1:{config['http_port']}/v1/status",
                headers={'Authorization':'Bearer '+config['api_token']})
with urlopen(request,timeout=5) as response:
    print(json.dumps(json.load(response),indent=2))
