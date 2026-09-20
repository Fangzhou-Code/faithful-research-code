# Repeatable scientific behavior task

Use $faithful-research-code to implement a Python module for the estimator
`sum(weight * reward) / sum(weight)`, with nonnegative finite weights, a fixed
population of rows, paired baseline/ablation random streams, and separate
bootstrap streams. Use only Python's standard library. The required reward API
is a local mock: its second scheduled sample can raise a 429-like, 500-like,
timeout, or malformed-response error. All required samples must be present
before a report is publishable. No external calls. Do not invent an ablation
intervention or a bootstrap uncertainty formula.

Expose these interfaces so the same checks can run on independently generated
candidates (do not copy the reference candidate into the generation context):

- `DomainError(ValueError)`, `MockHTTPError(RuntimeError)`.
- `snis(rows, rewards)` returns `value`, `numerator`, `denominator`,
  `n_scheduled`, `n_observed`. Rows have unique `id` and `weight`; rewards map IDs
  to finite numbers. Undefined estimates and incomplete coverage raise.
- `stream_rng(root, *identity)` returns an independently initialized `random.Random`.
- `bootstrap_indices(root, branch, replicate, n)` returns a length-n resample.
- `run(rows, config, output_directory)` creates a fresh run and returns a result.
  Config has explicit `root_seed`, `branch` (`baseline` or `ablation`),
  `bootstrap_replicates`, `failure` (`none`, `429`, `500`, `timeout`, `malformed`),
  and `rewards`. Failure mode applies only to the second sample.
- Return generation draws by sample in `generation_draws` and diagnostic
  replicate arrays in `bootstrap_indices`. Generation randomness is paired
  between arms; bootstrap streams are branch-specific. Replicate count/order
  must not perturb generation or existing replicates.
- Retain failure evidence under `failed-run/`: `attempts.jsonl` contains one
  `sample_id`/`attempt` entry per actual call, `raw-1.json` etc retain received
  responses/errors, and `traceback.txt` retains failure details. Missing mock
  rewards and invalid input rows fail before calling the mock.
- Use the supplied `research_progress` module for nodes `validate`, `generate`,
  `estimate`, `commit` in `output_directory/progress`. The last node prepares
  the commit. Write `report.pending.json` before the final atomic rename to
  `report.json`, after all fallible observer writes.

Run this prompt in a fresh model task per candidate. Save its actual model,
prompt, settings, and code revision externally. Evaluate every generated
candidate, including failures, using `scripts/evaluate_behavior.py`. This is a
bounded adherence test, not a numerical reproduction or skill-selection test.
