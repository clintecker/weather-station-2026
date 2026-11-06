"""The TX's bench screens, frame for frame (tools/scr_render.py digests): every screen at every frame, in the demo view
and every state of scr_render.views(), hashed exactly as the TX sends it (4096 bytes in the SSD1325's order, turned for
the panel), against tests/golden/scr_frames.json. A refactor of the drawing code keeps every hash; a deliberate change
to what a screen shows is accepted with `python3 tools/scr_render.py --update` (and a look at the PNGs)."""
import json
import tempfile
import unittest
try:
    from toolchain import load_tool, needs_cc   # discover -s tests
except ImportError:
    from tests.toolchain import load_tool, needs_cc

render = load_tool('scr_render')


@needs_cc
class Golden(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.addClassCleanup(tmp.cleanup)
        cls.lib = render.build(tmp.name)

    def test_every_frame_is_as_it_was(self):
        want = json.loads(render.GOLDEN.read_text())
        got = render.digests(self.lib)
        self.assertEqual(sorted(got), sorted(want))
        changed = sorted(k for k in want if got[k] != want[k])
        self.assertEqual(changed[:20], [], f'{len(changed)} frames differ: tools/scr_render.py --update accepts them')

    def test_the_frames_differ(self):
        # A digest that ignored the drawing would pass the test above: the frames must not all hash alike.
        got = render.digests(self.lib)
        self.assertGreater(len(set(got.values())), 500)
        self.assertNotEqual(got['demo/HOME/00'], got['demo/HOME/02'])     # the icon animates
        self.assertNotEqual(got['demo/MATRIX/00'], got['demo/MATRIX/01'])  # the gray screen too


if __name__ == '__main__':
    unittest.main()
