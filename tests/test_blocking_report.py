"""tools/blocking_report.py: no busy-wait or blocking call may be reachable at run time."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
try:
    from toolchain import load_tool          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import load_tool    # python -m unittest tests.<module>

blocking_report = load_tool('blocking_report')


def callgraph(funcs, edges):
    """A GCC -fcallgraph-info file defining `funcs` (8-byte frames) with these direct calls."""
    nodes = ''.join(f'node: {{ title: "{t}" label: "{t}\\n{t.split(":")[0] if ":" in t else "app.c"}:1:1\\n'
                    f'8 bytes (static)" }}\n' for t in funcs)
    links = ''.join(f'edge: {{ sourcename: "{e[0]}" targetname: "{e[1]}"'
                    + (f' label: "{e[2]}:1"' if len(e) > 2 else '') + ' }\n' for e in edges)
    return 'graph: {\n' + nodes + links + '}\n'


def analyse(edges, taken=(), funcs=(), sources=None):
    """Analyse a synthetic build: every function named in `edges` (plus `funcs`) is defined.
    `sources` maps C file names to text, compiled (listed in .d files) into the build."""
    names = {n for e in edges for n in e[:2] if n != blocking_report.INDIRECT} | set(funcs)
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp)/'g.ci').write_text(callgraph(sorted(names), edges))
        for name, text in (sources or {}).items():
            (Path(tmp)/name).write_text(text)
            (Path(tmp)/name).with_suffix('.d').write_text(f'{Path(name).stem}.o: {name}\n')
        return blocking_report.analyse(tmp, taken=taken)


def banned(r):
    return [k for k, _path, _callers in r['run']]


class RunTime(unittest.TestCase):
    def test_banned_wait_reachable_from_an_interrupt_fails(self):
        r = analyse([('it.c:USART2_IRQHandler', 'app.c:handle'), ('app.c:handle', 'HAL_Delay')])
        self.assertTrue(r['failed'])
        self.assertEqual(r['run'], [('HAL_Delay', 'USART2_IRQHandler > handle > HAL_Delay', ['handle'])])

    def test_banned_wait_in_a_callback_fails(self):
        """A sequencer task (address-taken) is a run-time root."""
        r = analyse([('app.c:sample', 'bus_read'), ('bus_read', 'HAL_I2C_Master_Receive')], taken={'sample'})
        self.assertTrue(r['failed'])
        self.assertEqual(banned(r), ['HAL_I2C_Master_Receive'])

    def test_banned_wait_reached_only_from_boot_is_a_boot_wait(self):
        r = analyse([('main', 'SystemClock_Config'), ('SystemClock_Config', 'HAL_Delay'),
                     ('main', 'MX_SubGHz_Phy_Process'), ('MX_SubGHz_Phy_Process', 'UTIL_SEQ_Run')])
        self.assertFalse(r['failed'])
        self.assertIn(('HAL_Delay', 'main > SystemClock_Config > HAL_Delay', 'BANNED'), r['boot'])

    def test_the_main_loop_is_run_time(self):
        """main's while(1) body is run time even though only main calls it."""
        r = analyse([('main', 'MX_SubGHz_Phy_Process'), ('MX_SubGHz_Phy_Process', 'HAL_Delay')])
        self.assertTrue(r['failed'])
        self.assertEqual(r['boot'], [])

    def test_boot_code_also_called_at_run_time_is_run_time(self):
        r = analyse([('main', 'init'), ('init', 'HAL_Delay'), ('app.c:on_timer', 'init')], taken={'on_timer'})
        self.assertTrue(r['failed'])
        self.assertEqual(r['run'][0][1], 'on_timer > init > HAL_Delay')

    def test_banned_wait_only_through_a_test_only_command_passes(self):
        r = analyse([('app.c:on_line', 'fault_test'), ('fault_test', 'HAL_Delay'),
                     ('app.c:on_line', 'test_hang'), ('test_hang', 'HAL_Delay')], taken={'on_line'})
        self.assertFalse(r['failed'])
        self.assertEqual(r['test'], [('HAL_Delay', 'fault_test > HAL_Delay', 'BANNED')])
        self.assertEqual(r['test_commands'], ['on_line > fault_test', 'on_line > test_hang'])

    def test_the_same_wait_outside_the_test_command_still_fails(self):
        r = analyse([('app.c:on_line', 'fault_test'), ('fault_test', 'HAL_Delay'),
                     ('app.c:on_line', 'reboot_soon'), ('reboot_soon', 'HAL_Delay')], taken={'on_line'})
        self.assertTrue(r['failed'])
        self.assertEqual(r['run'][0][1], 'on_line > reboot_soon > HAL_Delay')

    def test_banned_wait_inside_an_allowed_one_is_still_found(self):
        """Traversal continues through ALLOWED waits (it stops only at BANNED ones)."""
        r = analyse([('it.c:FLASH_IRQHandler', 'HAL_FLASHEx_Erase'), ('HAL_FLASHEx_Erase', 'HAL_Delay')])
        self.assertTrue(r['failed'])
        self.assertIn('HAL_FLASHEx_Erase', [k for k, _ in r['allowed']])

    def test_allowed_wait_is_reported_not_failed(self):
        r = analyse([('app.c:store_task', 'HAL_FLASHEx_Erase'), ('HAL_FLASHEx_Erase', 'FLASH_WaitForLastOperation'),
                     ('FLASH_WaitForLastOperation', 'HAL_GetTick')], taken={'store_task'})
        self.assertFalse(r['failed'])
        self.assertEqual([k for k, _ in r['allowed']], ['FLASH_WaitForLastOperation', 'HAL_FLASHEx_Erase'])


class Clocks(unittest.TestCase):
    EDGES = [('app.c:task', 'app.c:poll_ready'), ('app.c:poll_ready', 'HAL_GetTick')]

    def test_unclassified_hal_gettick_caller_fails(self):
        """A hand-written timeout loop is caught by its HAL_GetTick call."""
        r = analyse(self.EDGES, taken={'task'})
        self.assertTrue(r['failed'])
        self.assertEqual(r['unclassified'], [('poll_ready', 'task > poll_ready', ['HAL_GetTick'])])

    def test_classified_timestamp_caller_passes(self):
        with patch.dict(blocking_report.TIMESTAMP, {'app.c:poll_ready': 'reads the time once'}):
            r = analyse(self.EDGES, taken={'task'})
        self.assertFalse(r['failed'])

    def test_a_static_of_the_same_name_in_another_file_is_not_classified(self):
        with patch.dict(blocking_report.TIMESTAMP, {'other.c:poll_ready': 'reads the time once'}):
            r = analyse(self.EDGES, taken={'task'})
        self.assertTrue(r['failed'])

    def test_timer_server_clock_counts_too(self):
        r = analyse([('it.c:EXTI_IRQHandler', 'spin'), ('spin', 'UTIL_TIMER_GetElapsedTime')])
        self.assertEqual(r['unclassified'], [('spin', 'EXTI_IRQHandler > spin', ['UTIL_TIMER_GetElapsedTime'])])

    def test_unclassified_clock_caller_at_boot_is_listed_not_failed(self):
        r = analyse([('main', 'clock_init'), ('clock_init', 'HAL_GetTick')])
        self.assertFalse(r['failed'])
        self.assertEqual(r['boot'], [('clock_init', 'main > clock_init', 'unclassified clock caller')])


class Inlining(unittest.TestCase):
    """GCC inlines static functions: the .ci call site (file:line) still names the source line, so
    the function written around the call decides, not the node it was inlined into."""
    APP = ('static void handle(int ev)\n{\n  deadline = HAL_GetTick() + 100;\n}\n'          # lines 1-4
           'static void fault_test(void)\n{\n  HAL_Delay(50);\n}\n'                        # lines 5-8
           'static void task(void)\n{\n  handle(1);\n  fault_test();\n}\n')                # lines 9-13

    def test_clock_call_inlined_from_a_classified_function_passes(self):
        edges = [('app.c:task', 'HAL_GetTick', 'app.c:3')]
        r = analyse(edges, taken={'task'}, sources={'app.c': self.APP})
        self.assertEqual(r['unclassified'], [('task', 'task', ['HAL_GetTick at app.c:3 in handle'])])
        with patch.dict(blocking_report.TIMESTAMP, {'app.c:handle': 'deadline'}):
            self.assertFalse(analyse(edges, taken={'task'}, sources={'app.c': self.APP})['failed'])

    def test_banned_call_inlined_from_a_test_only_function_is_test_only(self):
        r = analyse([('app.c:task', 'HAL_Delay', 'app.c:7')], taken={'task'}, sources={'app.c': self.APP})
        self.assertFalse(r['failed'])
        self.assertEqual(r['test'], [('HAL_Delay', 'task > fault_test (inlined) > HAL_Delay', 'BANNED')])

    def test_the_same_call_also_written_outside_the_test_function_fails(self):
        edges = [('app.c:task', 'HAL_Delay', 'app.c:7'), ('app.c:task', 'HAL_Delay', 'app.c:3')]
        r = analyse(edges, taken={'task'}, sources={'app.c': self.APP})
        self.assertTrue(r['failed'])


class Pointers(unittest.TestCase):
    def test_any_address_taken_function_is_a_root(self):
        """An indirect call can reach any address-taken function: each is checked as a root, even
        one that nothing calls directly."""
        edges = [('it.c:TIM_IRQHandler', blocking_report.INDIRECT), ('app.c:cb', 'HAL_Delay')]
        self.assertTrue(analyse(edges, taken={'cb'})['failed'])
        self.assertFalse(analyse(edges, taken=set())['failed'])

    def test_reset_handler_is_not_a_root(self):
        r = analyse([('Reset_Handler', 'main'), ('main', 'HAL_Delay')], taken={'Reset_Handler'})
        self.assertFalse(r['failed'])


class DriverTables(unittest.TestCase):
    """A Radio_s slot function (address taken only in the Radio table): a call through
    `Radio.Slot(` is an edge from its caller; boot_radio (global, app.c) is boot code."""

    def run_with(self, app_c):
        edges = [('radio.c:RadioSleep', 'HAL_Delay'), ('main', 'boot_radio')]
        return analyse(edges, taken={'RadioSleep': {'.rodata.Radio'}}, sources={'app.c': app_c})

    def test_slot_called_only_at_boot_is_a_boot_wait(self):
        r = self.run_with('void boot_radio(void) { Radio.Sleep(); }\n')
        self.assertFalse(r['failed'])
        self.assertIn(('HAL_Delay', 'main > boot_radio > RadioSleep > HAL_Delay', 'BANNED'), r['boot'])

    def test_slot_called_from_a_task_fails(self):
        r = analyse([('radio.c:RadioSleep', 'HAL_Delay'), ('app.c:task', 'app.c:idle')],
                    taken={'RadioSleep': {'.rodata.Radio'}, 'task': {'.text'}},
                    sources={'app.c': '/* { */ static void idle(void)\n{\n  if (x) { Radio . Sleep (); }\n}\n'})
        self.assertTrue(r['failed'])
        self.assertEqual(r['run'][0][1], 'task > idle > RadioSleep > HAL_Delay')
        self.assertEqual(r['via_slot'], {'RadioSleep': ['idle']})

    def test_slot_call_from_a_function_without_call_graph_is_a_root(self):
        """A static function GCC inlined away has no node: the call cannot be placed, so the slot's
        function is checked as a root."""
        r = self.run_with('void boot_radio(void) { go(); }\nstatic void go(void) { Radio.Sleep(); }\n')
        self.assertTrue(r['failed'])
        self.assertIn('no call graph', r['escaped']['RadioSleep'])

    def test_slot_call_inlined_into_another_function_is_placed_by_its_call_site(self):
        """go() was inlined into boot_radio; the .ci indirect call site (app.c:2) places it there."""
        r = analyse([('radio.c:RadioSleep', 'HAL_Delay'), ('main', 'boot_radio'),
                     ('boot_radio', blocking_report.INDIRECT, 'app.c:2')],
                    taken={'RadioSleep': {'.rodata.Radio'}},
                    sources={'app.c': 'void boot_radio(void) { go(); }\nstatic void go(void) { Radio.Sleep(); }\n'})
        self.assertFalse(r['failed'])
        self.assertIn(('HAL_Delay', 'main > boot_radio > RadioSleep > HAL_Delay', 'BANNED'), r['boot'])

    def test_slot_never_read_is_not_a_root(self):
        r = self.run_with('void boot_radio(void) { /* Radio.Sleep(); */ }\n')
        self.assertFalse(r['failed'])
        self.assertEqual(r['via_slot'], {'RadioSleep': []})

    def test_slot_stored_is_a_root(self):
        r = self.run_with('void boot_radio(void) { register_cb(Radio.Sleep); }\n')
        self.assertTrue(r['failed'])
        self.assertIn('stored or passed', r['escaped']['RadioSleep'])

    def test_object_passed_whole_makes_every_slot_a_root(self):
        r = self.run_with('extern const struct Radio_s Radio;\nvoid boot_radio(void) { use(&Radio); }\n')
        self.assertTrue(r['failed'])

    def test_function_also_taken_elsewhere_stays_a_root(self):
        r = analyse([('radio.c:RadioSleep', 'HAL_Delay')], taken={'RadioSleep': {'.rodata.Radio', '.text.x'}})
        self.assertTrue(r['failed'])


class LinkedOnly(unittest.TestCase):
    def test_a_leftover_call_graph_resolves_no_call(self):
        """A .ci left by a deleted source (not in the .map) must not resolve `handle` to its wait."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'app').mkdir()
            (Path(tmp)/'app'/'it.ci').write_text(callgraph(['it.c:USART2_IRQHandler'],
                                                           [('it.c:USART2_IRQHandler', 'handle')]))
            (Path(tmp)/'app'/'old.ci').write_text(callgraph(['old.c:handle'], [('old.c:handle', 'HAL_Delay')]))
            (Path(tmp)/'fw.elf').write_bytes(b'')
            (Path(tmp)/'fw.map').write_text('LOAD build/x/app/it.o\n')
            r = blocking_report.analyse(tmp, taken=set())
        self.assertFalse(r['failed'])
        self.assertEqual(r['run'], [])


if __name__ == '__main__':
    unittest.main()
