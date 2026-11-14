#!/usr/bin/env python3
"""Deterministic acceptance gate; all artifacts live in fresh report directories."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import tempfile

from propose_patch import propose

ROOT = Path(__file__).resolve().parent
PINNED = ('spec.md', 'tb_fifo.sv', 'fifo_checks.sv', 'run.py', 'propose_patch.py')
BINS = ('empty_to_nonempty', 'full', 'full_replacement', 'partial_simultaneous',
        'pointer_wrap', 'multi_cycle_stall', 'reset_queued')
FIXTURES = ('bad_repair', 'count_bug', 'no_wrap', 'reset_state', 'stall_pointer')


def hashes():
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in PINNED}


def process(args, directory, name, timeout, input_text=None):
    """Save output even on failure; a timeout kills the whole child process group."""
    try:
        with subprocess.Popen(args, cwd=directory, stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, start_new_session=True,
                              env={**os.environ, 'LC_ALL': 'C'}) as child:
            try:
                stdout, stderr = child.communicate(input_text, timeout=timeout)
                code = child.returncode
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                stdout, stderr = child.communicate()
                stderr += '\nTIMEOUT'
                code = 124
    except OSError as exc:
        stdout, stderr, code = '', str(exc), 127
    (directory / f'{name}.log').write_text(stdout + stderr)
    return subprocess.CompletedProcess(args, code, stdout, stderr)


def test_result(result, name, seed, wave):
    lines = result.stdout.splitlines()
    traces = [s for s in lines if s.startswith('TRACE ')]
    markers = [s for s in lines if s.startswith('RESULT ')]
    match = re.fullmatch(r'RESULT pass=1 coverage=(\d+) seed=(\d+) cycles=(\d+)',
                         markers[0]) if len(markers) == 1 else None
    sampled_mask = re.search(r'coverage=(\d+)', traces[-1]) if traces else None
    mask = int(match[1]) if match else None
    if mask is None and sampled_mask:
        mask = int(sampled_mask[1])
    diagnostic = next((s for s in (result.stdout + result.stderr).splitlines()
                       if '%Fatal:' in s or '%Error:' in s), None)
    kind, failure = None, None
    if diagnostic:
        checker = re.search(r'%Fatal: (?:tb_fifo|fifo_checks)\.sv:\d+:', diagnostic)
        kind, failure = ('check' if checker else 'process'), diagnostic
    elif result.returncode:
        kind, failure = 'process', result.stderr.strip() or f'exit code {result.returncode}'
    elif not match:
        kind, failure = 'report', 'missing, malformed, or duplicate completion marker'
    elif int(match[2]) != seed or int(match[3]) <= 0:
        kind, failure = 'report', 'completion seed or cycle count is invalid'
    elif name != 'repro' and mask != (1 << len(BINS)) - 1:
        kind, failure = 'coverage', 'missing required coverage bins'
    failing_cycle = re.search(r'cycle=(\d+)', failure or '')
    return dict(name=name, seed=seed, returncode=result.returncode, passed=kind is None,
                failure_kind=kind, failure=failure,
                first_failing_cycle=int(failing_cycle[1]) if failing_cycle else None,
                coverage={b: bool(mask & (1 << i)) if mask is not None else None
                          for i, b in enumerate(BINS)}, wave=str(wave), last_cycles=traces[-8:])


def qualification(report, is_baseline):
    detected = [dict(test=t['name'], failure=t['failure']) for t in report['tests']
                if t['failure_kind'] == 'check']
    qualified = report['accepted'] if is_baseline else (
        report['build_returncode'] == 0 and report['tool_returncode'] == 0
        and report['checkers_unchanged'] and bool(detected))
    return dict(accepted=report['accepted'], qualified=qualified,
                repro_passed=bool(report['tests']) and report['tests'][0]['passed'],
                detected_by=detected)


def verify(candidate, baseline):
    reports = ROOT / 'reports'
    reports.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='attempt-', dir=reports))
    source = Path(candidate).read_text()
    (directory / 'fifo.sv').write_text(source)
    for p in ('tb_fifo.sv', 'fifo_checks.sv'):
        shutil.copyfile(ROOT / p, directory / p)
    (directory / 'patch.diff').write_text(''.join(difflib.unified_diff(
        (ROOT / 'fifo.sv').read_text().splitlines(True), source.splitlines(True),
        fromfile='baseline/fifo.sv', tofile='candidate/fifo.sv')))
    version = process(['verilator', '--version'], directory, 'tool-version', 10)
    report = dict(candidate_hash=hashlib.sha256(source.encode()).hexdigest(),
                  tool=version.stdout.strip(), tool_returncode=version.returncode,
                  checker_hashes=baseline, tests=[], accepted=False)
    build = process(['verilator', '--binary', '--timing', '--assert', '--trace',
                     '-Wno-fatal', '-MAKEFLAGS', 'CFG_CXXFLAGS_STD=-std=c++20',
                     '--top-module', 'tb_fifo', 'fifo.sv', 'fifo_checks.sv', 'tb_fifo.sv'],
                    directory, 'build', 120)
    report['build_returncode'] = build.returncode
    report['build_failure'] = next((s for s in (build.stdout + build.stderr).splitlines()
                                    if '%Error' in s or 'error:' in s or 'TIMEOUT' in s),
                                   (build.stderr or build.stdout)[-1000:]) if build.returncode else None
    if build.returncode == 0:
        for name, seed, extra in [('repro', 1, ['+repro'])] + [
                (f'suite-{s}', s, []) for s in (1, 7, 42)]:
            wave = directory / f'{name}.vcd'
            result = process([str(directory / 'obj_dir/Vtb_fifo'),
                              f'+seed={seed}', f'+wave={wave}', *extra], directory, name, 15)
            report['tests'].append(test_result(result, name, seed, wave))
        report['accepted'] = version.returncode == 0 and all(t['passed'] for t in report['tests'])
    report['checkers_unchanged'] = hashes() == baseline
    report['accepted'] &= report['checkers_unchanged']
    (directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f"{'ACCEPT' if report['accepted'] else 'REJECT'} {candidate}: {directory}", flush=True)
    return report, directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate', nargs='?', default=str(ROOT / 'fifo.sv'))
    parser.add_argument('--demo', action='store_true', help='baseline and five manual mutants')
    parser.add_argument('--repair-command', help='external model command; see README')
    args = parser.parse_args()
    baseline = hashes()
    paths = [ROOT / 'fifo.sv', *(ROOT / 'fixtures' / f'{name}.sv' for name in FIXTURES)]
    for path in paths if args.demo else [Path(args.candidate)]:
        if not path.is_file():
            parser.error(f'missing candidate: {path}')
    if args.demo:
        results = {}
        for path in paths:
            report, directory = verify(path, baseline)
            results[path.name] = qualification(report, path == ROOT / 'fifo.sv')
            results[path.name]['report'] = str(directory / 'report.json')
        (ROOT / 'reports/qualification.json').write_text(json.dumps(results, indent=2) + '\n')
        return 0 if (all(v['qualified'] for v in results.values())
                     and results['bad_repair.sv']['repro_passed']) else 1
    candidate = Path(args.candidate)
    for attempt in range(4):  # Initial candidate, then at most three proposed repairs.
        report, directory = verify(candidate, baseline)
        if report['accepted']:
            return 0
        if not args.repair_command or attempt == 3:
            return 1
        try:
            candidate = propose(candidate, directory, args.repair_command, process)
        except ValueError as exc:
            print(f'Invalid repair command: {exc}', file=sys.stderr)
            return 1
        if candidate is None:
            print(f'Patch command failed or returned no RTL; see {directory}/model.json', file=sys.stderr)
            return 1
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
