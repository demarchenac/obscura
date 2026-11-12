# SVG native CI diagnosis

Fork-only experiment for the `table-rows-hot` failure on PR #1506. It changes
neither engine code nor the upstream performance budgets.

Push `diagnostics/svg-native-ci` to the fork to run
[the workflow](../../.github/workflows/svg-diagnostic.yml). The push trigger
works before this workflow is registered on the default branch.

- Frozen base: `74b4bec959117b9da309f113bb2b08aea39539ac`.
- Frozen SVG candidate: `e90e0f3afb26bf5caa0407c23f9eeb5290e0deaf`.
- Native Ubuntu 22.04; Rust 1.99.1 and nextest 0.9.143 from the original log;
  original release flags and nextest command.
- Two builds start without Cargo artifacts. The cold base seeds a run-specific
  dependency cache; both warm builds restore that same cache using the pinned
  upstream cache action and V8 repair step. This reconstructs a warm cache; it
  cannot retrieve the upstream repository's historical cache.
- Preserve executables and snapshot files before and after workspace nextest,
  plus SHA-256, V8 archive hashes, feature trees, CPU, image, and tool versions.
- Explicitly retain nextest failures. A successful diagnostic build job does
  not imply a passing test suite; inspect `nextest-exit.txt` and `nextest.log`.
- On a separate idle runner, warm the original base-before/candidate-after
  pair using the pinned obstacle course, then run the full unchanged evaluator.
- Run identical-binary A/A controls, matched before/before and after/after
  comparisons, the original asymmetric comparison, and each revision's
  before/after comparison. Each focused comparison has 50 alternating rounds.
- Upload every sample and executable for 30 days, including failed comparisons.
  Do not rerun selectively or discard failures to obtain a green result.

The original hosted executable expired. Rebuilt binaries are identified by
their own hashes, and the current runner image/CPU may differ from the old run.
Neither differing hashes nor a single failed comparison establish causation.
If a penalty recurs with stable A/A controls, profile the retained pair on the
same runner configuration before attributing it to SVG normalization.

Helpers use only Python's standard library. `svg_table.py` imports the frozen
base evaluator and changes only scenario selection and sample count; its
measurement function, fixture, correctness check, and budgets remain intact.
