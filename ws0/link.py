"""USB serial link to the RX board that survives unplug, replug, and renamed ports.

The RX board is found by its ST-LINK USB serial number, not by its /dev name, which changes
when the cable moves. Any serial error closes the port and schedules a reconnect with
back-off; the gateway keeps serving its API meanwhile. The TX board journals everything
while the link is down, so a reconnect loses no data.

A port can also stay open and deliver nothing (decision record H8(f),
docs/superpowers/specs/2026-10-29-build-progression-decisions.md): after SILENT_REOPEN_S with no
byte the link closes and reopens the same path at once, without back-off and without counting a
failure. The wait doubles after each reopen that brings nothing back, up to SILENT_REOPEN_MAX_S,
and returns to SILENT_REOPEN_S on any line. The RX prints '#alive' every 60 s
(firmware/stage0-node/App/app_rx.c), so a working link never waits that long; the gateway's
receiver-silent alarm (ws0/__main__.py RECEIVER_SILENT_S) stays the outer alarm.
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
SILENT_REOPEN_S = 90        # open port, no byte for this long: reopen it in place (H8 f)
SILENT_REOPEN_MAX_S = 400   # the doubled wait stops here


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
        self.last_byte = 0.0            # clock() of the last byte read, or of the last (re)open
        self.silent_s = SILENT_REOPEN_S  # current open-but-silent threshold

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
        self.last_byte = self.clock()
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
            self._reopen_if_silent()
            return []
        self.last_byte = self.clock()
        if self.discarding:   # the rest of an oversized line
            self.discarding = not fragment.endswith(b'\n')
            return []
        self.buffer += fragment
        if self.buffer.endswith(b'\n'):
            line, self.buffer = self.buffer[:-1], b''
            if len(line) <= MAX_LINE:
                self.silent_s = SILENT_REOPEN_S
                return [line.strip()]
        elif len(self.buffer) > MAX_LINE:
            self.buffer, self.discarding = b'', True
        else:
            return []
        self.log('#gateway rejected oversized serial line')
        return []

    def _reopen_if_silent(self):
        """Open port, nothing for silent_s: close and reopen the same path in place. Not a
        failure and no back-off; only an open error falls back to _drop and its back-off."""
        silent = self.clock() - self.last_byte
        if silent < self.silent_s:
            return
        self.silent_s = min(self.silent_s * 2, SILENT_REOPEN_MAX_S)
        self.log(f'#gateway serial-reopen path={self.path} silent_s={int(silent)} next_s={self.silent_s}')
        try:
            self.port.close()
        except self.errors:
            pass
        self.port, self.buffer, self.discarding = None, b'', False
        try:
            self.port = self.opener(self.path)
        except self.errors as exc:
            self.port = None
            self._drop(f'reopen-failed:{type(exc).__name__}')
            return
        self.last_byte = self.clock()
        self.write(b'\n')   # end any partial line on the receiver, as _connect does

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
