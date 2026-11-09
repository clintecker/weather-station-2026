#!/usr/bin/env python3
"""Build the node for every board x role x power profile, with the checks, and print each image's budget.

    python3 tools/board_matrix.py            build every cell with the checks (CI's firmware job)
    python3 tools/board_matrix.py --list     print the cells only
    python3 tools/board_matrix.py --no-checks  build only (no analyzer, stack bound or blocking-wait report)

The boards are firmware/board/*/board.toml (issue #36), each with the roles its board.toml allows. A TX is
built in each power telemetry profile CI covers (the default, phase B's WS_POWER_PROFILE=2 and the mux bus
WS_I2C_MUX=1) and, where the board can drive it, with the bench OLED (WS_BENCH_OLED=1); an RX once. Each
cell builds in firmware/stage0-node/build/matrix/<cell> with GCC's analyzer (ANALYZE=1), then runs
`make stack` (tools/stack_report.py) and `make waits` (tools/blocking_report.py). The link prints the
cell's flash and RAM budget lines (firmware/board/stm32wl/rules.mk); the summary lists them, and goes to
$GITHUB_STEP_SUMMARY too when that is set. Exit status 1 if any cell fails.
"""
import argparse
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NODE = ROOT / 'firmware' / 'stage0-node'
PROFILES = (('default', ()), ('profile-2', ('WS_POWER_PROFILE=2',)), ('mux', ('OPT=-Os -DWS_I2C_MUX=1',)))


def cells():
    """(name, make arguments) of every cell."""
    out = []
    for toml in sorted((ROOT / 'firmware' / 'board').glob('*/board.toml')):
        board = tomllib.loads(toml.read_text())
        name, roles = board['board']['name'], board['board']['roles']
        for role in roles:
            base = (f'ROLE={role}', f'BOARD={name}')
            if role == 'rx':
                out.append((f'{name}-rx', base))
                continue
            out += [(f'{name}-tx-{p}', base + args) for p, args in PROFILES]
            if board.get('bench_oled', {}).get('ok'):
                out.append((f'{name}-tx-oled', base + ('WS_BENCH_OLED=1',)))
    return out


def run(name, args, checks, jobs):
    build = f'BUILD=build/matrix/{name}'
    # The same flags for the checks as for the build, so they reuse its objects (board.mk's .flags files).
    make = ['make', '-C', str(NODE), *args, build, *(['ANALYZE=1'] if checks else [])]
    steps = [make + [f'-j{jobs}']] + ([make + ['stack'], make + ['waits']] if checks else [])
    lines = []
    for step in steps:
        r = subprocess.run(step, capture_output=True, text=True)
        lines += [ln for ln in r.stdout.splitlines() if re.match(r'(flash|RAM) budget', ln) and ln not in lines]
        if r.returncode:
            print(r.stdout[-4000:], r.stderr[-4000:], sep='\n')
            return False, lines
    return True, lines


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--list', action='store_true', help='print the cells only')
    ap.add_argument('--no-checks', action='store_true', help='build only')
    ap.add_argument('-j', type=int, default=os.cpu_count() or 2, help='make jobs per build')
    args = ap.parse_args(argv)
    if args.list:
        for name, make in cells():
            print(f'{name}: make {" ".join(make)}')
        return 0
    summary, failed = ['| Cell | Result | Budget |', '|---|---|---|'], []
    for name, make in cells():
        print(f'== {name}: make {" ".join(make)}', flush=True)
        ok, lines = run(name, make, not args.no_checks, args.j)
        for ln in lines:
            print(f'   {ln}')
        budget = '<br>'.join(ln for ln in lines if 'budget' in ln)
        summary.append(f'| {name} | {"ok" if ok else "FAILED"} | {budget} |')
        if not ok:
            failed.append(name)
    print('\n'.join(summary))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f:
            f.write('### Board x role x profile\n\n' + '\n'.join(summary) + '\n')
    if failed:
        print(f'board matrix: FAILED ({", ".join(failed)})')
        return 1
    print(f'board matrix: OK ({len(summary) - 2} cells)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
