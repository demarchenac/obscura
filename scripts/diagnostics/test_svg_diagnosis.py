"""Ensure a failed comparison cannot erase evidence or skip later controls."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import svg_compare
import svg_capture


class DiagnosticEvidenceTests(unittest.TestCase):
    def test_missing_optional_metadata_tool_is_recorded(self):
        result = svg_capture.command(['obscura-diagnostic-nonexistent-tool'], Path.cwd())
        self.assertEqual(result['exit'], 127)

    def test_rejects_modified_artifact_before_running_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'before').mkdir()
            binary = directory / 'before/obscura'
            binary.write_bytes(b'original')
            (directory / 'before.json').write_text(json.dumps({
                'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
            }))
            binary.write_bytes(b'modified')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                svg_compare.retained_binary(directory, 'before')

    def test_nonzero_exit_preserves_output_and_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            result = svg_compare.run_command(
                [sys.executable, '-c', "print('retained evidence'); raise SystemExit(7)"],
                output, 'failed')
            self.assertEqual(result['exit'], 7)
            self.assertIn('retained evidence', (output / 'failed.log').read_text())
            self.assertEqual(json.loads((output / 'failed-command.json').read_text())['exit'], 7)

    def test_budget_failure_does_not_skip_remaining_comparisons(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            arguments = argparse.Namespace(obstacles=Path('obstacles.py'))
            binaries = {f'{label}_{phase}': Path(f'{label}_{phase}')
                        for label in ('base', 'candidate') for phase in ('before', 'after')}
            def failed_benchmark(arguments, output, name, *binaries, **options):
                (output / f'{name}.json').write_text('{"retained": true}')
                return {'name': name, 'exit': 1}
            with patch.object(svg_compare, 'benchmark', side_effect=failed_benchmark), \
                 patch.object(svg_compare, 'run_command', return_value={'name': 'obstacles', 'exit': 0}):
                results = svg_compare.compare(arguments, output, binaries)
            self.assertEqual(len(results), 10)
            self.assertEqual(results[-1]['name'], 'candidate-test-effect')
            self.assertEqual(len(list(output.glob('*.json'))), 9)


if __name__ == '__main__':
    unittest.main()
