#!/usr/bin/env python3
"""Run the frozen CI evaluator with only table-rows-hot and more samples."""
import argparse
import importlib.util
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluator', type=Path, required=True)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=50)
    arguments = parser.parse_args()
    if arguments.rounds < 1:
        parser.error('--rounds must be positive')
    specification = importlib.util.spec_from_file_location('frozen_ci', arguments.evaluator)
    evaluator = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(evaluator)
    evaluator.ROUNDS = arguments.rounds
    evaluator.SCENARIOS = {'table-rows-hot': evaluator.SCENARIOS['table-rows-hot']}
    sys.argv = [str(arguments.evaluator), '--base', str(arguments.base.resolve()),
                '--candidate', str(arguments.candidate.resolve()),
                '--output', str(arguments.output.resolve())]
    evaluator.main()


if __name__ == '__main__':
    main()
