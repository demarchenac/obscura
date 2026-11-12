#!/usr/bin/env python3
"""Compare preserved build/test artifacts without changing upstream budgets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from svg_capture import environment


def retained_binary(directory, phase):
    binary = (directory / phase / 'obscura').resolve()
    report = json.loads((directory / f'{phase}.json').read_text())
    actual = hashlib.sha256(binary.read_bytes()).hexdigest()
    if actual != report['binary_sha256']:
        raise ValueError(f'retained binary hash mismatch: {binary}')
    binary.chmod(0o755)  # Actions artifact extraction does not retain permissions.
    return binary


def run_command(arguments, output, name, environment=None):
    started = time.monotonic()
    with (output / f'{name}.log').open('w') as log:
        try:
            result = subprocess.run(arguments, stdout=log, stderr=subprocess.STDOUT,
                                    env=environment, timeout=900)
            status = result.returncode
        except subprocess.TimeoutExpired:
            log.write('\nDiagnostic command exceeded 900 seconds.\n')
            status = 124
    report = {'name': name, 'command': arguments, 'exit': status,
              'elapsed_seconds': time.monotonic() - started}
    (output / f'{name}-command.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def benchmark(arguments, output, name, base, candidate, full=False):
    command = [sys.executable]
    if not full:
        command.extend([str(Path(__file__).with_name('svg_table.py')),
                        '--evaluator', str(arguments.evaluator),
                        '--rounds', str(arguments.rounds)])
    if full:
        command.append(str(arguments.evaluator))
    command.extend(['--base', str(base), '--candidate', str(candidate),
                    '--output', str(output / f'{name}.json')])
    return run_command(command, output, name)


def compare(arguments, output, binaries):
    results = []
    # Original performance-job order: base obstacles first, then candidate.
    for label, binary in (('base', binaries['base_before']),
                          ('candidate', binaries['candidate_after'])):
        process_environment = dict(os.environ, OBSCURA_BIN=str(binary))
        results.append(run_command(
            [sys.executable, str(arguments.obstacles), '--json', '--runs', '3', '--warmup', '1'],
            output, f'obstacles-{label}', process_environment))
    results.append(benchmark(arguments, output, 'full-original-order',
                             binaries['base_before'], binaries['candidate_after'], full=True))
    comparisons = (
        ('aa-base', 'base_before', 'base_before'),
        ('aa-candidate', 'candidate_after', 'candidate_after'),
        ('ab-before-tests', 'base_before', 'candidate_before'),
        ('ab-original-order', 'base_before', 'candidate_after'),
        ('ab-after-tests', 'base_after', 'candidate_after'),
        ('base-test-effect', 'base_before', 'base_after'),
        ('candidate-test-effect', 'candidate_before', 'candidate_after'),
    )
    for name, baseline, candidate in comparisons:
        result = benchmark(arguments, output, name, binaries[baseline], binaries[candidate])
        results.append(result)
        # Persist progress even if a subsequent command crashes or times out.
        (output / 'commands.json').write_text(json.dumps(results, indent=2) + '\n')
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--cache-mode', choices=('cold', 'warm'), required=True)
    parser.add_argument('--evaluator', type=Path, required=True)
    parser.add_argument('--obstacles', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=50)
    arguments = parser.parse_args()
    if arguments.rounds < 1:
        parser.error('--rounds must be positive')
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    binaries = {}
    tests = {}
    for label in ('base', 'candidate'):
        directory = arguments.artifacts / f'svg-{arguments.cache_mode}-{label}'
        tests[label] = (directory / 'nextest-exit.txt').read_text().strip()
        for phase in ('before', 'after'):
            binaries[f'{label}_{phase}'] = retained_binary(directory, phase)
    provenance = environment(arguments.evaluator.resolve().parents[2])
    provenance.update({'tests_exit': tests, 'rounds': arguments.rounds,
                       'binary_sha256': {name: hashlib.sha256(binary.read_bytes()).hexdigest()
                                         for name, binary in binaries.items()}})
    (output / 'environment.json').write_text(json.dumps(provenance, indent=2) + '\n')
    results = compare(arguments, output, binaries)
    summary = ['## SVG binary diagnosis\n\n',
               f'Cache: **{arguments.cache_mode}**. Workspace test exits: {tests}.\n\n',
               'A/A uses the identical executable. A/B and test-effect comparisons use '
               '50 alternating rounds by default. All CI thresholds are unchanged.\n\n',
               '| Experiment | Exit |\n| --- | ---: |\n']
    summary.extend(f"| {result['name']} | {result['exit']} |\n" for result in results)
    (output / 'summary.md').write_text(''.join(summary))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as destination:
            destination.write(''.join(summary))
    print(''.join(summary))
    if any(result['exit'] != 0 for result in results):
        raise SystemExit('diagnostic failures retained; inspect raw JSON and logs')


if __name__ == '__main__':
    main()
