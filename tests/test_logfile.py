"""Size-rotated gateway logs (ws0/logfile.py, gateway review GW7)."""
import tempfile
import threading
import unittest
from pathlib import Path

from ws0.logfile import RotatingLog


class Rotation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'receiver.log'

    def tearDown(self):
        self.tmp.cleanup()

    def test_rotates_by_size_and_keeps_a_bounded_number_of_files(self):
        log = RotatingLog(self.path, max_bytes=100, keep=3)
        for i in range(60):
            log.write(f'line {i:04d} ' + 'x' * 9 + '\n')   # 20 bytes a line: 5 lines a file
        log.close()
        names = sorted(p.name for p in Path(self.tmp.name).iterdir())
        self.assertEqual(names, ['receiver.log', 'receiver.log.1', 'receiver.log.2', 'receiver.log.3'])
        for p in Path(self.tmp.name).iterdir():
            self.assertLessEqual(p.stat().st_size, 100)
        # newest lines in the live file, then .1, .2, .3 going back in time, nothing lost between
        lines = []
        for name in ('receiver.log.3', 'receiver.log.2', 'receiver.log.1', 'receiver.log'):
            lines += (Path(self.tmp.name) / name).read_text().splitlines()
        numbers = [int(line.split()[1]) for line in lines]
        self.assertEqual(numbers, list(range(40, 60)))

    def test_appends_to_an_existing_file(self):
        self.path.write_text('old\n')
        log = RotatingLog(self.path, max_bytes=1000)
        log.write('new\n')
        log.close()
        self.assertEqual(self.path.read_text(), 'old\nnew\n')

    def test_a_line_longer_than_the_limit_is_still_written(self):
        log = RotatingLog(self.path, max_bytes=10, keep=2)
        log.write('a' * 50 + '\n')
        log.write('b\n')
        log.close()
        self.assertEqual(self.path.read_text(), 'b\n')
        self.assertEqual((self.path.parent / 'receiver.log.1').read_text(), 'a' * 50 + '\n')

    def test_threads_never_interleave_or_lose_lines(self):
        log = RotatingLog(self.path, max_bytes=2000, keep=50)
        def writer(tag):
            for i in range(200):
                log.write(f'{tag} {i}\n')
        threads = [threading.Thread(target=writer, args=(t,)) for t in 'abcd']
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        log.close()
        lines = []
        for p in Path(self.tmp.name).iterdir():
            lines += p.read_text().splitlines()
        self.assertEqual(len(lines), 800)
        self.assertEqual(len(set(lines)), 800)


if __name__ == '__main__':
    unittest.main()
