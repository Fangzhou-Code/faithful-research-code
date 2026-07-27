from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "audit_semantic_fallbacks.py"


class AuditSemanticFallbacksTests(unittest.TestCase):
    def run_audit(self, source: str, *args: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.py"
            path.write_text(source, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(SCRIPT), str(path), *args],
                text=True,
                capture_output=True,
                check=False,
            )

    def json_audit(self, source: str, *args: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        result = self.run_audit(source, "--json", *args)
        return result, json.loads(result.stdout)

    def test_broad_exception_continue_is_high(self) -> None:
        result, report = self.json_audit(
            "for item in items:\n    try:\n        run(item)\n    except Exception:\n        continue\n"
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("RF002", {item["rule"] for item in report["findings"]})

    def test_import_fallback_and_strict_checkpoint_are_high(self) -> None:
        result, report = self.json_audit(
            "try:\n    import required_backend\nexcept ImportError:\n    import alternate_backend\n"
            "model.load_state_dict(state, strict=False)\n"
        )
        self.assertEqual(result.returncode, 0)
        rules = {item["rule"] for item in report["findings"]}
        self.assertTrue({"RF005", "RF401"}.issubset(rules))

    def test_data_and_numeric_transforms_are_reported(self) -> None:
        _, report = self.json_audit(
            "clean = frame.dropna()\n"
            "filled = frame.fillna(0)\n"
            "bounded = values.clip(-1, 1)\n"
            "loader = DataLoader(data, drop_last=True)\n"
            "table = read_csv(path, on_bad_lines='skip')\n",
            "--min-severity",
            "low",
        )
        rules = {item["rule"] for item in report["findings"]}
        self.assertTrue({"RF201", "RF202", "RF301", "RF204", "RF205"}.issubset(rules))

    def test_source_authorized_suppression_is_auditable(self) -> None:
        result, report = self.json_audit(
            "# research-fidelity: allow=RF301 reason=\"Equation 4 requires clipping before reduction\"\n"
            "bounded = values.clip(-1, 1)\n",
            "--min-severity",
            "low",
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report["summary"]["suppressed"], 1)
        self.assertEqual(report["suppressed"][0]["rule"], "RF301")
        self.assertIn("Equation 4", report["suppressed"][0]["suppression_reason"])

    def test_short_or_wrong_rule_suppression_does_not_hide_finding(self) -> None:
        _, report = self.json_audit(
            "# research-fidelity: allow=RF202 reason=\"short\"\n"
            "bounded = values.clip(-1, 1)\n",
            "--min-severity",
            "low",
        )
        self.assertEqual(report["summary"]["suppressed"], 0)
        self.assertIn("RF301", {item["rule"] for item in report["findings"]})

    def test_cleanup_then_reraise_has_no_high_finding(self) -> None:
        _, report = self.json_audit(
            "try:\n    run()\nexcept Exception:\n    cleanup()\n    raise\n",
            "--min-severity",
            "low",
        )
        self.assertFalse(any(item["severity"] == "high" for item in report["findings"]))

    def test_parse_skip_nan_aggregation_and_truncation_are_reported(self) -> None:
        _, report = self.json_audit(
            "for row in rows:\n"
            "    try:\n"
            "        parse(row)\n"
            "    except JSONDecodeError:\n"
            "        continue\n"
            "score = np.nanmean(scores)\n"
            "tokens = tokenizer(text, truncation=True)\n",
            "--min-severity",
            "low",
        )
        rules = {item["rule"] for item in report["findings"]}
        self.assertTrue({"RF008", "RF206", "RF207"}.issubset(rules))

    def test_checkpoint_mismatch_resume_and_cache_are_reported(self) -> None:
        _, report = self.json_audit(
            "model = AutoModel.from_pretrained(path, ignore_mismatched_sizes=True)\n"
            "trainer.train(resume_from_checkpoint=checkpoint)\n"
            "data = dataset.map(transform, load_from_cache_file=True)\n",
            "--min-severity",
            "low",
        )
        rules = {item["rule"] for item in report["findings"]}
        self.assertTrue({"RF404", "RF502", "RF503"}.issubset(rules))

    def test_oom_parameter_mutation_is_high(self) -> None:
        _, report = self.json_audit(
            "try:\n"
            "    train(batch_size)\n"
            "except RuntimeError as error:\n"
            "    if 'out of memory' in str(error):\n"
            "        batch_size = batch_size // 2\n",
            "--min-severity",
            "low",
        )
        matches = [item for item in report["findings"] if item["rule"] == "RF403"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["severity"], "high")

    def test_precision_capability_branch_is_reported(self) -> None:
        _, report = self.json_audit(
            "dtype = torch.bfloat16 if is_bf16_supported() else torch.float16\n",
            "--min-severity",
            "low",
        )
        self.assertIn("RF402", {item["rule"] for item in report["findings"]})

    def test_parse_error_returns_two(self) -> None:
        result = self.run_audit("def broken(:\n    pass\n")
        self.assertEqual(result.returncode, 2)
        self.assertIn("parse-error", result.stdout)

    def test_fail_on_and_legacy_json_fields(self) -> None:
        result, report = self.json_audit(
            "try:\n    run()\nexcept Exception:\n    return_value = None\n",
            "--fail-on",
            "medium",
        )
        self.assertEqual(result.returncode, 1)
        self.assertTrue({"files", "findings", "suppressed_low_severity", "errors"}.issubset(report["summary"]))
        self.assertIn("findings", report)
        self.assertIn("errors", report)


if __name__ == "__main__":
    unittest.main()
