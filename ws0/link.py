"""USB serial link to the RX board that survives unplug, replug, and renamed ports.

The RX board is found by its ST-LINK USB serial number, not by its /dev name, which changes
when the cable moves. Any serial error closes the port and schedules a reconnect with
back-off; the gateway keeps serving its API meanwhile. The TX board journals everything
while the link is down, so a reconnect loses no data.
"""
import time

BAUD = 115200   # the boards' ST-LINK virtual COM port
BACKOFF_S = (1, 2, 4, 8, 15)
# Longest serial line accepted, newline excluded. The RX firmware prints at most one trace buffer
# per line (UTIL_ADV_TRACE_TMP_BUF_SIZE = 640 B, firmware/board/nucleo-wl55jc/Core/Inc/utilities_conf.h);
# its longest line is a 255-byte '#rx crc ... data=<510 hex>' capture, about 560 characters.
# Anything longer is not from our firmware (garbled stream, wrong device): it is dropped whole,
# up to and including its newline, so its tail is never taken for a line of its own.
MAX_LINE = 1024


def open_port(path, timeout, write_timeout=1):
    """A board's serial port, held exclusively (pyserial uses flock on POSIX). A second program that
    opens it fails, instead of taking lines from the same buffer and losing frames."""
    import serial
    return serial.Serial(path, BAUD, timeout=timeout, write_timeout=write_timeout, exclusive=True)


class ReceiverLink:
    def __init__(self, device=None, serial_number=None, log=print, opener=None, ports=None, clock=time.monotonic):
        if not device and not serial_number:
            raise ValueError('Need a device path or an ST-LINK serial number')
        import serial
        from serial.tools import list_ports
        self.device, self.serial_number, self.log, self.clock = device, serial_number, log, clock
        self.opener = opener or (lambda path: open_port(path, timeout=0.05))
        self.ports = ports or list_ports.comports
        self.errors = (serial.SerialException, OSError)
        self.port = None
        self.path = None
        self.buffer = b''
        self.discarding = False   # inside an oversized line: drop bytes through its newline
        self.failures = 0
        self.retry_at = 0.0
        self.reconnects = 0

    @property
    def connected(self):
        return self.port is not None

    def resolve(self):
        if not self.serial_number:
            return self.device
        for info in self.ports():
            if (info.serial_number or '').upper() == self.serial_number.upper():
                return info.device
        return None

    def _drop(self, why):
        if self.port is not None:
            try:
                self.port.close()
            except self.errors:
                pass
            self.log(f'#gateway serial-lost path={self.path} reason={why}')
        self.port = None
        self.buffer = b''
        self.discarding = False
        delay = BACKOFF_S[min(self.failures, len(BACKOFF_S) - 1)]
        self.failures += 1
        self.retry_at = self.clock() + delay

    def _connect(self):
        if self.clock() < self.retry_at:
            return False
        path = self.resolve()
        if path is None:
            self._drop('board-not-present')
            return False
        try:
            self.port = self.opener(path)
        except self.errors as exc:
            self.port = None
            self._drop(f'open-failed:{type(exc).__name__}')
            return False
        self.path = path
        if self.failures:
            self.reconnects += 1
        self.failures = 0
        self.log(f'#gateway serial-open path={path}')
        # End any line the receiver assembled before we (re)connected: an empty line is ignored, and
        # a partial one is discarded instead of prefixing the next ACK.
        self.write(b'\n')
        return True

    def poll(self):
        """Return complete lines (stripped bytes). Never raises on serial errors."""
        if self.port is None and not self._connect():
            return []
        try:
            fragment = self.port.read_until(b'\n', size=MAX_LINE + 1)
        except self.errors as exc:
            self._drop(f'read:{type(exc).__name__}')
            return []
        if not fragment:
            return []
        if self.discarding:   # the rest of an oversized line
            self.discarding = not fragment.endswith(b'\n')
            return []
        self.buffer += fragment
        if self.buffer.endswith(b'\n'):
            line, self.buffer = self.buffer[:-1], b''
            if len(line) <= MAX_LINE:
                return [line.strip()]
        elif len(self.buffer) > MAX_LINE:
            self.buffer, self.discarding = b'', True
        else:
            return []
        self.log('#gateway rejected oversized serial line')
        return []

    def write(self, data):
        """True if written. On failure the link reconnects; the node retries the frame."""
        if self.port is None:
            return False
        try:
            self.port.write(data)
            return True
        except self.errors as exc:
            self._drop(f'write:{type(exc).__name__}')
            return False

    def close(self):
        if self.port is not None:
            try:
                self.port.close()
            except self.errors:
                pass
            self.port = None
