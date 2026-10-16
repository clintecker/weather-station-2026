"""Size-rotated text logs the gateway writes itself.

receiver.log and the service output used to grow without limit. Rotation lives in the gateway,
not in newsyslog/logrotate, so it works the same on macOS, Linux and Windows and under any service
manager: launchd keeps its StandardOutPath file open and cannot rotate it."""
import os
import threading
from pathlib import Path

MAX_BYTES = 50 * 1024 * 1024   # ~2 months of receiver.log at one station (~1 MB a day)
KEEP = 10                      # name.1 (newest) .. name.10 (oldest): at most ~550 MB in all


class RotatingLog:
    """Append-only, line-buffered text file: when it would pass max_bytes it becomes name.1, the
    older files shift up by one and the oldest is deleted. Safe to share between threads."""
    def __init__(self, path, max_bytes=MAX_BYTES, keep=KEEP):
        self.path, self.max_bytes, self.keep = Path(path), max_bytes, keep
        self.lock = threading.Lock()
        self.file = self._open()

    def _open(self):
        # newline='': no \n -> \r\n translation on Windows, so the bytes counted are the bytes written.
        return self.path.open('a', buffering=1, encoding='utf-8', errors='replace', newline='')

    def _rotate(self):
        self.file.close()
        for n in range(self.keep - 1, 0, -1):
            older = self.path.with_name(f'{self.path.name}.{n}')
            if older.exists():
                os.replace(older, self.path.with_name(f'{self.path.name}.{n + 1}'))
        os.replace(self.path, self.path.with_name(f'{self.path.name}.1'))
        self.file = self._open()

    def write(self, text):
        with self.lock:
            if self.file.tell() and self.file.tell() + len(text.encode('utf-8', 'replace')) > self.max_bytes:
                self._rotate()
            return self.file.write(text)

    def flush(self):
        with self.lock:
            self.file.flush()

    def close(self):
        with self.lock:
            self.file.close()
