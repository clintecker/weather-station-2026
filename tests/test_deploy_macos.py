"""tools/deploy/macos/install.sh without launchctl: the plist it renders, and the root check. Runs on
macOS and Linux (it needs sh and python3, nothing from macOS)."""
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools' / 'deploy' / 'macos' / 'install.sh'


@unittest.skipIf(sys.platform == 'win32' or not shutil.which('sh'), 'needs a POSIX sh')
class InstallScript(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, *args, env=None):
        return subprocess.run(['sh', str(SCRIPT), *args], capture_output=True, text=True, timeout=60,
                              env=env or os.environ.copy())

    def state_dir(self, name):
        state = self.dir / name
        state.mkdir()
        return state.resolve()

    def test_render_escapes_sed_and_xml_characters(self):
        """A state directory with &, |, \\ and < in its name comes through intact and the plist parses."""
        state = self.state_dir('a&b|c\\d <e>')
        result = self.run_script('render', str(state), 'RX&1|2')
        self.assertEqual(result.returncode, 0, result.stderr)
        plist = plistlib.loads(result.stdout.encode())
        args = plist['ProgramArguments']
        self.assertEqual(args[args.index('--directory') + 1], str(state))
        self.assertEqual(args[args.index('--serial-number') + 1], 'RX&1|2')
        self.assertEqual(args[args.index('--log-file') + 1], f'{state}/serve.out')
        self.assertEqual(plist['StandardErrorPath'], f'{state}/serve.err')
        self.assertNotIn('UserName', plist)

    def test_daemon_render_runs_as_the_user(self):
        state = self.state_dir('s&t')
        env = os.environ | {'HOME': str(self.dir / 'h&o|m\\e')}
        result = self.run_script('--daemon', 'render', str(state), 'RX', env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        plist = plistlib.loads(result.stdout.encode())
        self.assertEqual(plist['UserName'], subprocess.run(['id', '-un'], capture_output=True, text=True).stdout.strip())
        self.assertEqual(plist['EnvironmentVariables'], {'HOME': env['HOME']})

    def test_daemon_refuses_root(self):
        """Under sudo, id -un and HOME are root's: the daemon would run as root. A fake id says uid 0."""
        bin_dir = self.dir / 'bin'
        bin_dir.mkdir()
        real_id = shutil.which('id')
        fake = bin_dir / 'id'
        fake.write_text(f'#!/bin/sh\nif [ "${{1:-}}" = -u ]; then echo 0; else exec {real_id} "$@"; fi\n')
        fake.chmod(0o755)
        env = os.environ | {'PATH': f'{bin_dir}{os.pathsep}{os.environ["PATH"]}'}
        result = self.run_script('--daemon', 'render', str(self.state_dir('s')), 'RX', env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('root', result.stderr)
        self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
