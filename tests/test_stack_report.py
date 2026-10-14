"""tools/stack_report.py: the worst-case stack bound must never be understated."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
try:
    from toolchain import load_tool          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import load_tool    # python -m unittest tests.<module>

stack_report = load_tool('stack_report')


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


class Roots(unittest.TestCase):
    def test_irq_handlers_are_interrupt_roots(self):
        """Vector-table handlers are named *_IRQHandler (USART2_IRQHandler) or *_Handler
        (SysTick_Handler); both are interrupts, never callbacks, in the estimate."""
        frames = {'app.c:main': 8, 'it.c:SUBGHZ_Radio_IRQHandler': 400, 'it.c:SysTick_Handler': 16}
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'g.ci').write_text(callgraph(frames, []))
            with patch.object(stack_report, 'address_taken',
                              return_value={'SUBGHZ_Radio_IRQHandler', 'SysTick_Handler'}):
                r = stack_report.analyse(tmp)
        self.assertEqual(r['worst_irq'], (400, 'it.c:SUBGHZ_Radio_IRQHandler'))
        self.assertEqual(r['cb'], (0, '-'))

    def test_unbounded_recursion_is_reported_quickly(self):
        """A large unbounded cycle is an error, found without exploring every path through it."""
        import time
        names = [f'x.c:f{i}' for i in range(12)]
        edges = [(a, b) for a in names for b in names if a != b] + [('app.c:main', names[0])]
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'g.ci').write_text(callgraph({'app.c:main': 8, **{n: 8 for n in names}}, edges))
            with patch.object(stack_report, 'address_taken', return_value=set()):
                began = time.monotonic()
                r = stack_report.analyse(tmp)
        self.assertLess(time.monotonic() - began, 5)
        self.assertTrue(r['recursion'])


if __name__ == '__main__':
    unittest.main()
