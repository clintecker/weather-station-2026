"""MQTT credentials and connection diagnostics, portable across macOS, Linux and Windows."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ws0.service import MQTT, mqtt_password


class PasswordSource(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_file_in_run_directory(self):
        (self.dir / 'mqtt-password').write_text('s3cret\n')
        (self.dir / 'mqtt-password').chmod(0o600)   # else the permission warning reaches real stderr
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('WS_MQTT_PASSWORD', None)
            self.assertEqual(mqtt_password(self.dir), 's3cret')   # trailing newline stripped

    def test_environment_wins(self):
        (self.dir / 'mqtt-password').write_text('from-file')
        with patch.dict(os.environ, {'WS_MQTT_PASSWORD': 'from-env'}):
            self.assertEqual(mqtt_password(self.dir), 'from-env')

    def test_none_when_unset(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('WS_MQTT_PASSWORD', None)
            self.assertIsNone(mqtt_password(self.dir))

    @unittest.skipIf(sys.platform == 'win32', 'POSIX permission bits')
    def test_warns_when_readable_by_others(self):
        path = self.dir / 'mqtt-password'
        path.write_text('x')
        path.chmod(0o644)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), patch.dict(os.environ, {}, clear=False):
            os.environ.pop('WS_MQTT_PASSWORD', None)
            mqtt_password(self.dir)
        self.assertIn('readable by other users', err.getvalue())
        path.chmod(0o600)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            mqtt_password(self.dir)
        self.assertEqual(err.getvalue(), '')


class ConnectDiagnostics(unittest.TestCase):
    def test_refused_connection_is_logged(self):
        class Reason:
            is_failure = True
            def __str__(self): return 'Not authorized'
        publisher = object.__new__(MQTT)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            publisher.on_connect(None, None, None, Reason(), None)
        self.assertIn('mqtt connect refused: Not authorized', err.getvalue())


class StartAndClose(unittest.TestCase):
    def test_username_without_password_fails_at_start(self):
        """Refuse to start rather than connect with no password and fail vaguely later."""
        with tempfile.TemporaryDirectory() as tmp:
            gateway = type('G', (), {'directory': tmp,
                                     'cfg': {'station': 's', 'mqtt': {'username': 'weatherstation'}}})()
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop('WS_MQTT_PASSWORD', None)
                with self.assertRaises(ValueError) as exc:
                    MQTT(gateway)
            self.assertIn('mqtt-password', str(exc.exception))

    def test_close_survives_a_failed_final_publish(self):
        """wait_for_publish raises if the link drops; close must still stop the client."""
        calls = []
        class Info:
            def wait_for_publish(self, timeout=None):
                raise RuntimeError('The client is not currently connected.')
        class Client:
            def is_connected(self): return True
            def publish(self, *a, **k): return Info()
            def disconnect(self): calls.append('disconnect')
            def loop_stop(self): calls.append('loop_stop')
        publisher = object.__new__(MQTT)
        publisher.client, publisher.root = Client(), 'weatherstation/v1/s'
        publisher.close()
        self.assertEqual(calls, ['disconnect', 'loop_stop'])


if __name__ == '__main__':
    unittest.main()
