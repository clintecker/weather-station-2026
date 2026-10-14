"""tools/stack_report.py: the worst-case stack bound must never be understated."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('stack_report', ROOT/'tools/stack_report.py')
stack_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stack_report)


def callgraph(frames, edges):
    """A GCC -fcallgraph-info file with these frame sizes and direct calls."""
    nodes = ''.join(f'node: {{ title: "{t}" label: "{t}\\n{size} bytes (static)" }}\n' for t, size in frames.items())
    links = ''.join(f'edge: {{ sourcename: "{a}" targetname: "{b}" }}\n' for a, b in edges)
    return 'graph: {\n' + nodes + links + '}\n'


class BoundedCycle(unittest.TestCase):
    def test_a_partial_result_from_a_cut_cycle_is_not_reused(self):
        """main reaches the bounded cycle at RadioSetPublicNetwork (P); a callback reaches it at
        RadioSetModem (M). Exploring from main, M is computed while the cycle is cut at P, without
        P's deep callee. Reused for the callback, that partial M understated its chain by 1000 B."""
        P, M = 'radio.c:RadioSetPublicNetwork', 'radio.c:RadioSetModem'
        frames = {'app.c:main': 8, P: 16, M: 32, 'radio.c:big': 1000, 'app.c:on_event': 4}
        edges = [('app.c:main', P), (P, M), (M, P), (P, 'radio.c:big'), ('app.c:on_event', M)]
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'g.ci').write_text(callgraph(frames, edges))
            with patch.object(stack_report, 'address_taken', return_value={'on_event'}):
                r = stack_report.analyse(tmp)
        self.assertEqual(r['cb'], (4 + 32 + 16 + 1000, 'app.c:on_event'))
        self.assertEqual(r['main_cost'], 8 + 16 + 1000)
        self.assertEqual(r['recursion'], [])


if __name__ == '__main__':
    unittest.main()
