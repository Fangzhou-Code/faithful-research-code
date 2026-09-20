import copy
import hashlib
import json
import math
import unittest
import sys
from unittest.mock import patch
import research_progress
import importlib.util
from pathlib import Path
candidate_path = Path(sys.argv.pop(1)).resolve()
candidate_source = Path(sys.argv.pop(1)).read_bytes()
expected_candidate_hash = sys.argv.pop(1)
if hashlib.sha256(candidate_source).hexdigest() != expected_candidate_hash:
    raise ValueError("Frozen candidate source does not match its recorded hash")
RUNS = Path(sys.argv.pop(1))
CHECKS_PATH = Path(sys.argv.pop(1))
sys.path.insert(0, str(candidate_path.parent))
spec = importlib.util.spec_from_file_location("behavior_candidate", candidate_path)
candidate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = candidate
exec(compile(candidate_source, str(candidate_path), "exec"), candidate.__dict__)
DomainError, MockHTTPError = candidate.DomainError, candidate.MockHTTPError
bootstrap_indices, run, snis, stream_rng = candidate.bootstrap_indices, candidate.run, candidate.snis, candidate.stream_rng
from research_progress import snapshot

ROWS = [{"id":"one", "weight":1.0}, {"id":"two", "weight":3.0}, {"id":"three", "weight":2.0}]
CONFIG = {"root_seed":2026, "branch":"baseline", "bootstrap_replicates":4, "failure":"none", "rewards":{"one":2.0,"two":4.0,"three":8.0}}


class ScientificChecks(unittest.TestCase):
    def test_successful_run_publishes_checked_result(self):
        out = RUNS / "successful-publication"
        result = run(ROWS, CONFIG, out)
        expected = {"value": 5.0, "numerator": 30.0, "denominator": 6.0,
                    "n_scheduled": 3, "n_observed": 3}
        for key, value in expected.items():
            self.assertEqual(result[key], value, key)
        published = json.loads((out / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(published, result)
        self.assertFalse((out / "report.pending.json").exists())
        self.assertEqual(snapshot(out / "progress")["tracks"]["execution"], "complete")

    def test_hand_formula_and_zero_weight_row(self):
        self.assertEqual(snis(ROWS, CONFIG["rewards"])["value"], 5.0)
        self.assertEqual(snis([{"id":"a","weight":0.0},{"id":"b","weight":2.0}], {"a":900.0,"b":3.0})["value"], 3.0)

    def test_domains_and_complete_coverage(self):
        cases = [([], {}), ([{"id":"a","weight":0}], {"a":2}),
                 ([{"id":"a","weight":-1}], {"a":2}),
                 ([{"id":"a","weight":math.inf}], {"a":2}),
                 ([{"id":"a","weight":1}], {"a":math.nan}),
                 ([{"id":"a","weight":1}], {}),
                 ([{"id":"a","weight":1}], {"a":2,"b":3}),
                 ([{"id":"a","weight":1},{"id":"a","weight":1}], {"a":2}),
                 ([{"id":"a","weight":1e308}], {"a":1e308}),
                 ([{"id":"a","weight":1e308},{"id":"b","weight":1e308}], {"a":1,"b":1})]
        for rows, rewards in cases:
            with self.subTest(rows=rows, rewards=rewards):
                with self.assertRaises(DomainError):
                    snis(rows, rewards)

    def test_failures_stop_no_retry_no_result(self):
        for failure, error in [("429",MockHTTPError),("500",MockHTTPError),("timeout",TimeoutError),("malformed",DomainError)]:
            with self.subTest(failure=failure):
                config = dict(CONFIG, failure=failure)
                out = RUNS / ("failure-" + failure)
                with self.assertRaises(error):
                    run(ROWS, config, out)
                attempts = [json.loads(line) for line in (out / "failed-run/attempts.jsonl").read_text().splitlines()]
                self.assertEqual([a["sample_id"] for a in attempts], ["one","two"])
                self.assertEqual([a["attempt"] for a in attempts], [1,1])
                self.assertFalse((out / "report.json").exists())
                self.assertFalse((out / "report.pending.json").exists())
                self.assertTrue((out / "failed-run/raw-1.json").exists())
                self.assertTrue((out / "failed-run/raw-2.json").exists())
                self.assertTrue((out / "failed-run/traceback.txt").exists())
                states = {n["id"]:n["state"] for n in snapshot(out / "progress")["nodes"]}
                self.assertEqual(states["generate"], "failed")
                self.assertEqual(states["estimate"], "pending")
                self.assertEqual(states["commit"], "pending")

    def test_branch_order_pairing_and_bootstrap_isolation(self):
        b_alone = run(ROWS, dict(CONFIG, branch="ablation"), RUNS / "b-alone")
        a_then = run(ROWS, CONFIG, RUNS / "a-then")
        b_after = run(ROWS, dict(CONFIG, branch="ablation"), RUNS / "b-after")
        b_first = run(ROWS, dict(CONFIG, branch="ablation"), RUNS / "b-first")
        a_after = run(ROWS, CONFIG, RUNS / "a-after")
        more = run(ROWS, dict(CONFIG, bootstrap_replicates=9), RUNS / "more-bootstrap")
        self.assertEqual(b_alone, b_after)
        self.assertEqual(b_alone, b_first)
        self.assertEqual(a_then, a_after)
        self.assertEqual(a_then["generation_draws"], b_alone["generation_draws"])
        self.assertEqual(a_then["generation_draws"], more["generation_draws"])
        self.assertEqual(a_then["bootstrap_indices"], more["bootstrap_indices"][:4])
        self.assertNotEqual(stream_rng(2026,"generation","one").getstate(), stream_rng(2026,"bootstrap","baseline",0).getstate())
        self.assertNotEqual(stream_rng(2026,"bootstrap","baseline",0).getstate(), stream_rng(2026,"bootstrap","ablation",0).getstate())
        forward = {k:bootstrap_indices(2026,"baseline",k,3) for k in range(4)}
        backward = {k:bootstrap_indices(2026,"baseline",k,3) for k in reversed(range(4))}
        self.assertEqual(forward, backward)
        self.assertEqual(a_then["n_scheduled"], 3)
        self.assertEqual(a_then["n_observed"], 3)

    def test_progress_failure_before_publication(self):
        original = research_progress.record
        def failing_record(run_dir, node, state, detail=""):
            if node == "commit" and state == "succeeded":
                raise OSError("Injected progress persistence failure")
            return original(run_dir, node, state, detail)
        out = RUNS / "observer-failure"
        with patch("research_progress.record", side_effect=failing_record):
            with self.assertRaises(OSError):
                run(ROWS, CONFIG, out)
        self.assertFalse((out / "report.json").exists())
        self.assertTrue((out / "failed-run/traceback.txt").exists())

    def test_missing_rewards_block_before_api(self):
        config = copy.deepcopy(CONFIG)
        del config["rewards"]["two"]
        out = RUNS / "missing-reward"
        with self.assertRaises(DomainError):
            run(ROWS, config, out)
        self.assertFalse((out / "failed-run/attempts.jsonl").exists())
        self.assertFalse((out / "report.json").exists())

    def test_empty_pipeline_blocks_before_api(self):
        out = RUNS / "empty-pipeline"
        with self.assertRaises(DomainError):
            run([], CONFIG, out)
        self.assertFalse((out / "failed-run/attempts.jsonl").exists())
        self.assertFalse((out / "report.json").exists())


if __name__ == "__main__":
    class CompletedChecks(unittest.TextTestResult):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.successful_tests = []

        def addSuccess(self, test):
            super().addSuccess(test)
            self.successful_tests.append(test.id().rsplit(".", 1)[1])

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ScientificChecks)
    result = unittest.TextTestRunner(verbosity=2, resultclass=CompletedChecks).run(suite)
    CHECKS_PATH.write_text(json.dumps({"tests_run": result.testsRun,
                                      "successful_tests": sorted(result.successful_tests),
                                      "successful": result.wasSuccessful()}), encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
