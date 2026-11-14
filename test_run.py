"""Checks for false acceptance, inconclusive qualification and repair failures."""
import contextlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import run
from propose_patch import propose

PASS = 'RESULT pass=1 coverage=127 seed=1 cycles=300\n'


def result(stdout='', code=0, stderr=''):
    return subprocess.CompletedProcess([], code, stdout, stderr)


class GateTests(unittest.TestCase):
    def test_completion_requires_success_seed_coverage_and_one_valid_marker(self):
        cases = [result(PASS), result(), result(PASS, 1), result(PASS + PASS),
                 result(PASS.replace('seed=1', 'seed=7')),
                 result(PASS.replace('cycles=300', 'cycles=0')),
                 result(PASS.replace('coverage=127', 'coverage=63')),
                 result(PASS + '[1] %Fatal: tb_fifo.sv:1: failed check cycle=0\n'),
                 result('RESULT malformed\n' + PASS), result(PASS, 124, 'TIMEOUT')]
        for i, value in enumerate(cases):
            with self.subTest(i=i):
                self.assertEqual(run.test_result(value, 'suite-1', 1, 'wave.vcd')['passed'], i == 0)
        self.assertTrue(run.test_result(result(PASS.replace('127', '3')), 'repro', 1, '')['passed'])

    def test_failed_check_keeps_actual_coverage_cycle_and_last_eight_samples(self):
        trace = ''.join(f'TRACE cycle={i} coverage=3\n' for i in range(12))
        value = run.test_result(result(trace + '[125] %Fatal: tb_fifo.sv:1: data mismatch cycle=12\n', 1),
                                'suite-1', 1, 'wave.vcd')
        self.assertEqual(value['first_failing_cycle'], 12)
        self.assertEqual(len(value['last_cycles']), 8)
        self.assertEqual(sum(value['coverage'].values()), 2)
        self.assertEqual(value['failure_kind'], 'check')

    def test_qualification_requires_a_behavioral_failure_and_unchanged_checkers(self):
        check = run.test_result(result('%Fatal: tb_fifo.sv:1: data mismatch cycle=1\n', 1), 'suite-1', 1, '')
        report = dict(accepted=False, build_returncode=0, tool_returncode=0,
                      checkers_unchanged=True, tests=[check])
        self.assertTrue(run.qualification(report, False)['qualified'])
        for key, value in [('build_returncode', 1), ('tool_returncode', 1),
                           ('checkers_unchanged', False), ('tests', []),
                           ('tests', [run.test_result(result('%Fatal: fifo.sv:1: DUT stopped\n', 1), 'suite-1', 1, '')]),
                           ('tests', [run.test_result(result('', 124, 'TIMEOUT'), 'suite-1', 1, '')])]:
            with self.subTest(key=key, value=value):
                self.assertFalse(run.qualification({**report, key: value}, False)['qualified'])

    def test_process_timeout_preserves_both_streams_and_kills_children(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            grandchild = "import time; from pathlib import Path; time.sleep(.5); Path('leaked').touch()"
            script = (f'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",{grandchild!r}]); '
                      'print("partial stdout",flush=True); print("partial stderr",file=sys.stderr,flush=True); '
                      'time.sleep(10)')
            value = run.process([sys.executable, '-c', script], directory, 'timeout', .2)
            self.assertEqual(value.returncode, 124)
            self.assertIn('partial stdout', value.stdout)
            self.assertIn('partial stderr', value.stderr)
            self.assertIn('TIMEOUT', (directory / 'timeout.log').read_text())
            time.sleep(.6)
            self.assertFalse((directory / 'leaked').exists())
            missing = run.process([str(directory / 'missing')], directory, 'missing', 1)
            self.assertNotEqual(missing.returncode, 0)

    def test_patch_failure_saves_response_and_status(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / 'report.json').write_text('{"accepted":false}')
            script = 'import sys; print("partial response"); print("adapter error",file=sys.stderr); sys.exit(2)'
            command = shlex.join([sys.executable, '-c', script])
            self.assertIsNone(propose(run.ROOT / 'fifo.sv', directory, command, run.process))
            self.assertEqual(json.loads((directory / 'model.json').read_text())['returncode'], 2)
            self.assertIn('partial response', (directory / 'response.txt').read_text())
            self.assertIn('adapter error', (directory / 'model.stderr').read_text())
            self.assertTrue((directory / 'prompt.json').exists())
            self.assertFalse((directory / 'proposed.sv').exists())

    def test_repair_loop_stops_after_three_proposals_or_acceptance(self):
        for outcomes, proposals in [([False] * 4, 3), ([False, True], 1)]:
            with self.subTest(outcomes=outcomes), \
                 patch.object(sys, 'argv', ['run.py', '--repair-command', 'manual-adapter']), \
                 patch('run.verify', side_effect=[({'accepted': x}, run.ROOT) for x in outcomes]) as verify, \
                 patch('run.propose', return_value=run.ROOT / 'fifo.sv') as adapter:
                self.assertEqual(run.main(), 0 if outcomes[-1] else 1)
                self.assertEqual(verify.call_count, len(outcomes))
                self.assertEqual(adapter.call_count, proposals)

    def test_demo_requires_all_five_fixtures(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'fifo.sv').touch()
            with patch.object(sys, 'argv', ['run.py', '--demo']), patch('run.ROOT', root), \
                 patch('run.hashes', return_value={}), patch('run.verify') as verify, \
                 contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                run.main()
            self.assertEqual(error.exception.code, 2)
            verify.assert_not_called()


if __name__ == '__main__':
    unittest.main()
