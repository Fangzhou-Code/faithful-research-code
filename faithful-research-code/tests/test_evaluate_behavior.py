import hashlib
import json
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
EVALUATOR = ROOT / "scripts" / "evaluate_behavior.py"
CANDIDATE = ROOT / "assets" / "behavior-eval" / "reference_candidate.py"


class CandidateEvaluationTests(unittest.TestCase):
    def test_reference_passes_with_saved_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "candidate.py"
            candidate.write_text(CANDIDATE.read_text(encoding="utf-8") +
                                 "\nfrom dataclasses import dataclass\n@dataclass\nclass Metadata:\n    name: str\n",
                                 encoding="utf-8")
            output = Path(directory) / "evaluation"
            result = subprocess.run([sys.executable, str(EVALUATOR), str(candidate), str(output),
                                     "--generator-id", "reference-harness-check"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((output / "evaluation.json").read_text())
            self.assertEqual(report["status"], "PASS")
            self.assertTrue(report["checks_verified"])
            self.assertEqual(report["checks"]["tests_run"], 8)
            self.assertEqual(report["checks"]["successful_tests"], report["expected_checks"])
            self.assertEqual(len(report["candidate_sha256"]), 64)
            self.assertTrue(report["unverified"])
            self.assertTrue((output / "runs" / "failure-429" / "failed-run" / "traceback.txt").is_file())

    def test_wrong_estimator_fails_and_retains_report(self):
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / "bad.py"
            source = CANDIDATE.read_text(encoding="utf-8")
            self.assertIn("value = numerator / denominator", source)
            bad.write_text(source.replace("value = numerator / denominator", "value = 0.0"), encoding="utf-8")
            output = Path(directory) / "evaluation"
            result = subprocess.run([sys.executable, str(EVALUATOR), str(bad), str(output),
                                     "--generator-id", "deliberately-wrong-fixture"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads((output / "evaluation.json").read_text())["status"], "FAIL")
            self.assertIn("FAIL", (output / "test.log").read_text())

    def test_stale_bytecode_cannot_pass_a_changed_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "candidate.py"
            source = CANDIDATE.read_bytes()
            candidate.write_bytes(source)
            before = candidate.stat()
            py_compile.compile(str(candidate), doraise=True,
                               invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
            original = b"value = numerator / denominator"
            changed = source.replace(original, b"value = 0.0".ljust(len(original)))
            self.assertNotEqual(source, changed)
            candidate.write_bytes(changed)
            os.utime(candidate, ns=(before.st_atime_ns, before.st_mtime_ns))
            self.assertEqual(candidate.stat().st_size, before.st_size)
            output = Path(directory) / "evaluation"
            result = subprocess.run([sys.executable, str(EVALUATOR), str(candidate), str(output),
                                     "--generator-id", "stale-bytecode-regression"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            report = json.loads((output / "evaluation.json").read_text())
            self.assertEqual(report["status"], "FAIL")
            self.assertIn("AssertionError: 0.0 != 5.0", (output / "test.log").read_text())
            self.assertEqual(report["candidate_sha256"], hashlib.sha256(changed).hexdigest())
            self.assertEqual(Path(report["candidate_snapshot"]).read_bytes(), changed)
            self.assertEqual(report["test_sha256"], hashlib.sha256(Path(report["test_snapshot"]).read_bytes()).hexdigest())

    def test_frozen_source_preserves_local_imports_and_execution_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "candidate.py"
            (candidate.parent / "local_helper.py").write_text("MARKER = 'local helper'\n", encoding="utf-8")
            source = CANDIDATE.read_bytes() + (
                b"\nfrom local_helper import MARKER\nassert MARKER == 'local helper'\n"
                b"assert Path(__file__).parent.joinpath('local_helper.py').is_file()\n"
                b"Path(__file__).write_text('raise RuntimeError(\"changed after loading\")\\n', encoding='utf-8')\n")
            candidate.write_bytes(source)
            output = Path(directory) / "evaluation"
            result = subprocess.run([sys.executable, str(EVALUATOR), str(candidate), str(output),
                                     "--generator-id", "frozen-source-regression"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((output / "evaluation.json").read_text())
            self.assertEqual(report["status"], "PASS")
            self.assertNotEqual(candidate.read_bytes(), source)
            self.assertEqual(report["candidate_sha256"], hashlib.sha256(source).hexdigest())
            self.assertEqual(Path(report["candidate_snapshot"]).read_bytes(), source)

    def test_incomplete_or_incorrect_candidates_cannot_pass(self):
        source = CANDIDATE.read_text(encoding="utf-8")
        candidates = {
            "early-exit": "raise SystemExit(0)\n",
            "wrong-run-result": source.replace('result["status"] = "COMPLETE_LOCAL_FIXTURE"',
                                                 'result["status"] = "COMPLETE_LOCAL_FIXTURE"\n            result["value"] = 123456789.0'),
            "missing-publication": source.replace('(out / "report.pending.json").replace(out / "report.json")', 'pass'),
            "skipped-checks": source + "\nimport unittest\nunittest.TestCase.setUp = lambda self: self.skipTest('injected skip')\n",
        }
        for name, candidate_source in candidates.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                candidate = Path(directory) / "candidate.py"
                candidate.write_text(candidate_source, encoding="utf-8")
                output = Path(directory) / "evaluation"
                result = subprocess.run([sys.executable, str(EVALUATOR), str(candidate), str(output),
                                         "--generator-id", "negative-regression"], capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 1, result.stderr)
                report = json.loads((output / "evaluation.json").read_text())
                self.assertEqual(report["status"], "FAIL")
                self.assertFalse(report["checks_verified"])
                if name in {"early-exit", "skipped-checks"}:
                    self.assertEqual(report["returncode"], 0)
                else:
                    self.assertIn("test_successful_run_publishes_checked_result", (output / "test.log").read_text())


if __name__ == "__main__":
    unittest.main()
