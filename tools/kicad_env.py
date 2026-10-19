"""Where KiCad 10 and the pinned KiCadRoutingTools are (hardware/bench-breadboard-r0).

KICAD_APP names KiCad.app; the default is the KiCad 10.0.6 disk image this Mac mounts. The router
and its Python come from tools/fetch-router.sh."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_APP = ('/Users/clint/Documents/Codex/2026-10-09/referenced-chatgpt-conversation-this-is-an/'
               'work/tools/mount-kicad/KiCad/KiCad.app')


@dataclass(frozen=True)
class Env:
    python: Path         # KiCad's own Python, with pcbnew
    cli: Path            # kicad-cli
    router: Path         # vendor/KiCadRoutingTools
    router_python: Path  # vendor/krt-venv/bin/python


def _paths():
    app = Path(os.environ.get('KICAD_APP', DEFAULT_APP))
    return {'KiCad Python (KICAD_APP)': app/'Contents/Frameworks/Python.framework/Versions/3.9/bin/python3',
            'kicad-cli (KICAD_APP)': app/'Contents/MacOS/kicad-cli',
            'KiCadRoutingTools (tools/fetch-router.sh)': ROOT/'vendor/KiCadRoutingTools/py_router/route.py',
            'router Python (tools/fetch-router.sh)': ROOT/'vendor/krt-venv/bin/python'}


def find():
    """The toolchain, or None if any part is missing (missing() says which)."""
    p = list(_paths().values())
    if not all(path.exists() for path in p):
        return None
    return Env(python=p[0], cli=p[1], router=p[2].parent.parent, router_python=p[3])


def missing():
    absent = [f'{name}: {path}' for name, path in _paths().items() if not path.exists()]
    return 'missing ' + '; '.join(absent) if absent else ''
