#!/usr/bin/env python3
"""Profile retained executables after measuring them; never rebuild or time profiles."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from threading import Thread

from svg_compare import retained_binary


def run_process(arguments, directory, name):
    with (directory / f'{name}.log').open('w') as log:
        process = subprocess.Popen(arguments, stdout=log, stderr=subprocess.STDOUT,
                                   cwd=directory, start_new_session=True)
        try:
            return process.wait(timeout=120)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            return 124


def run_worker(configuration):
    case = json.loads(configuration.read_text())
    for _ in range(case['repetitions']):
        result = subprocess.run(case['command'], capture_output=True, text=True, timeout=45)
        if result.returncode != 0 or json.loads(result.stdout) != case['expected']:
            raise RuntimeError(f'profile evaluation failed: {result.returncode}, {result.stderr}')
    print(f"{case['repetitions']} profile evaluations matched the expected result")


def case_command(binary, url, expression, flags):
    return [str(binary), '--v8-flags', flags, 'fetch', url, '--allow-private-network',
            '--quiet', '--timeout', '20', '--wait', '0', '--eval', expression]


def write_case(directory, name, command, expected, repetitions):
    configuration = directory / f'{name}.json'
    configuration.write_text(json.dumps({'command': command, 'expected': expected,
                                         'repetitions': repetitions}, indent=2) + '\n')
    return [sys.executable, str(Path(__file__).resolve()), '--worker', str(configuration)]


def profile_v8(directory, command, expected):
    worker = write_case(directory, 'v8-case', command, expected, 5)
    status = run_process(worker, directory, 'v8-record')
    logs = sorted(directory.glob('*v8.log'))
    processor = None
    if logs:
        processor = run_process(['node', '--prof-process', str(logs[0])], directory, 'v8-summary')
    return {'exit': status, 'logs': len(logs), 'processor_exit': processor,
            'note': 'Node may warn that its V8 version differs; raw V8 logs are retained.'}


def profile_native(directory, command, expected, perf):
    worker = write_case(directory, 'native-case', command, expected, 15)
    maps_before = set(Path('/tmp').glob('perf-*.map'))
    recording = run_process([str(perf), 'record', '-e', 'cpu-clock:u', '-F', '997',
                              '--call-graph', 'dwarf', '-o', 'native.data', '--', *worker],
                             directory, 'native-record')
    for mapping in set(Path('/tmp').glob('perf-*.map')) - maps_before:
        shutil.copy2(mapping, directory / mapping.name)
    reporting = None
    if recording == 0:
        reporting = run_process([str(perf), 'report', '--stdio', '-i', 'native.data',
                                 '--no-children', '--comms=obscura', '--sort=dso,symbol'],
                                directory, 'native-summary')
    return {'record_exit': recording, 'report_exit': reporting,
            'event': 'cpu-clock:u', 'filter': 'obscura processes only'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--cache-mode', choices=('cold', 'warm'))
    parser.add_argument('--evaluator', type=Path)
    parser.add_argument('--scenario')
    parser.add_argument('--output', type=Path)
    arguments = parser.parse_args()
    if arguments.worker:
        run_worker(arguments.worker)
        return
    required = ('artifacts', 'cache_mode', 'evaluator', 'scenario', 'output')
    if any(getattr(arguments, name) is None for name in required):
        parser.error('all profiling arguments are required')
    specification = importlib.util.spec_from_file_location('frozen_ci', arguments.evaluator)
    evaluator = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(evaluator)
    expression, expected = evaluator.SCENARIOS[arguments.scenario]
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    tools = sorted(Path('/usr/lib').glob('linux-tools*/**/perf'))
    if not tools:
        raise SystemExit('no native perf executable installed')
    perf = tools[-1]
    run_process(['node', '--version'], output, 'node-version')
    run_process([str(perf), '--version'], output, 'perf-version')
    server = evaluator.ThreadingHTTPServer(('127.0.0.1', 0), evaluator.Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}/'
    results = {}
    try:
        for label in ('base', 'candidate'):
            artifact = arguments.artifacts / f'svg-{arguments.cache_mode}-{label}'
            for phase in ('before', 'after'):
                binary = retained_binary(artifact, phase)
                directory = output / f'{label}-{phase}'
                directory.mkdir(exist_ok=True)
                v8 = profile_v8(directory, case_command(binary, url, expression,
                                                         '--prof --logfile=v8.log'), expected)
                native = profile_native(directory, case_command(binary, url, expression,
                                                                 '--perf-basic-prof'), expected, perf)
                results[f'{label}-{phase}'] = {'v8': v8, 'native': native}
                (output / 'profiles.json').write_text(json.dumps(results, indent=2) + '\n')
    finally:
        server.shutdown()
        server.server_close()
    print(json.dumps(results, indent=2))
    if any(result['v8']['exit'] != 0 or result['native']['record_exit'] != 0
           for result in results.values()):
        raise SystemExit('profile failures retained; inspect logs')


if __name__ == '__main__':
    main()
