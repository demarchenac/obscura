#!/usr/bin/env python3
"""Record native build provenance and retain binaries before/after nextest."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys


def digest(path):
    checksum = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            checksum.update(chunk)
    return checksum.hexdigest()


def command(arguments, source):
    try:
        result = subprocess.run(arguments, cwd=source, capture_output=True, text=True, timeout=60)
    except FileNotFoundError as error:
        return {'exit': 127, 'stdout': '', 'stderr': str(error)}
    return {'exit': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}


def environment(source):
    # Never dump the whole environment: Actions tokens must stay private.
    names = ('ImageOS', 'ImageVersion', 'CARGO_BUILD_JOBS', 'CARGO_INCREMENTAL',
             'OPENSSL_NO_VENDOR', 'RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS',
             'CC', 'CXX', 'CFLAGS', 'CXXFLAGS', 'CARGO_PROFILE_RELEASE_OPT_LEVEL')
    return {
        'environment': {name: os.environ.get(name) for name in names},
        'platform': platform.platform(),
        'affinity': sorted(os.sched_getaffinity(0)),
        'cpu': command(['lscpu'], source),
        'rustc': command(['rustc', '-vV'], source),
        'clang': command(['clang', '--version'], source),
        'nextest': command(['cargo', 'nextest', '--version'], source),
        'packages': command(['dpkg-query', '-W', 'libc6', 'libstdc++6'], source),
        'revision': command(['git', 'rev-parse', 'HEAD'], source),
        'lock_sha256': digest(source / 'Cargo.lock'),
    }


def capture(source, output, phase):
    stage = output / phase
    stage.mkdir(parents=True, exist_ok=True)
    binary = source / 'target/release/obscura'
    shutil.copy2(binary, stage / 'obscura')
    snapshots = {}
    for snapshot in sorted((source / 'target/release/build').glob('obscura-js-*/out/OBSCURA_SNAPSHOT.bin')):
        retained = stage / f'{snapshot.parents[1].name}-snapshot.bin'
        shutil.copy2(snapshot, retained)
        snapshots[str(snapshot.relative_to(source))] = digest(retained)
    archives = {}
    for archive in (source / 'target').glob('release/**/librusty_v8.a'):
        archives[str(archive.relative_to(source))] = digest(archive)
    return {
        'binary_sha256': digest(stage / 'obscura'),
        'binary_bytes': binary.stat().st_size,
        'snapshots': snapshots,
        'v8_archives': archives,
        'features': command(['cargo', 'tree', '-p', 'obscura-cli', '--features', 'render', '-e', 'features'], source),
        'elf': command(['readelf', '-n', str(binary.resolve())], source),
    }


def main():
    source, output = (Path(value).resolve() for value in sys.argv[1:3])
    phase = sys.argv[3]
    if phase not in ('environment', 'before', 'after'):
        raise SystemExit('phase must be environment, before, or after')
    output.mkdir(parents=True, exist_ok=True)
    report = environment(source) if phase == 'environment' else capture(source, output, phase)
    (output / f'{phase}.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
