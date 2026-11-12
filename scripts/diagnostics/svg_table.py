#!/usr/bin/env python3
"""Run one frozen CI scenario with more samples and unchanged budgets."""
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
    parser.add_argument('--scenario', default='table-rows-hot')
    arguments = parser.parse_args()
    if arguments.rounds < 1:
        parser.error('--rounds must be positive')
    specification = importlib.util.spec_from_file_location('frozen_ci', arguments.evaluator)
    evaluator = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(evaluator)
    evaluator.ROUNDS = arguments.rounds
    if arguments.scenario not in evaluator.SCENARIOS:
        parser.error(f'unknown scenario: {arguments.scenario}')
    evaluator.SCENARIOS = {arguments.scenario: evaluator.SCENARIOS[arguments.scenario]}
    sys.argv = [str(arguments.evaluator), '--base', str(arguments.base.resolve()),
                '--candidate', str(arguments.candidate.resolve()),
                '--output', str(arguments.output.resolve())]
    evaluator.main()


if __name__ == '__main__':
    main()
