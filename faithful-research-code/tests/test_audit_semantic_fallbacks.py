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

    def test_sdk_defaults_and_aliases_fail_gate(self) -> None:
        for source in (
            "from openai import OpenAI as Client\nc = Client()\n",
            "import anthropic as a\nc = a.AsyncAnthropic()\n",
            "import openai\nc = openai.AzureOpenAI(max_retries=2)\n",
            "import openai\nc = openai.OpenAI(**config)\n",
        ):
            with self.subTest(source=source):
                result, report = self.json_audit(source, "--fail-on", "medium")
                self.assertEqual(result.returncode, 1)
                self.assertIn("RF504", {item["rule"] for item in report["findings"]})

    def test_explicit_disabled_retries_are_not_flagged(self) -> None:
        result, report = self.json_audit(
            "from openai import OpenAI\nc = OpenAI(max_retries=0)\n"
            "adapter = HTTPAdapter(max_retries=0)\n"
            "transport = HTTPTransport(retries=0)\n",
            "--fail-on", "medium",
        )
        self.assertEqual(result.returncode, 0)
        self.assertFalse(report["findings"])

    def test_retry_decorators_and_http_policy(self) -> None:
        result, report = self.json_audit(
            "from tenacity import retry as again\n"
            "import backoff as b\n"
            "@again\ndef query():\n    return call()\n"
            "@b.on_exception(b.expo, IOError)\ndef fetch():\n    return call()\n"
            "adapter = HTTPAdapter(max_retries=3)\n",
            "--fail-on", "medium",
        )
        self.assertEqual(result.returncode, 1)
        self.assertTrue({"RF501", "RF505"}.issubset({item["rule"] for item in report["findings"]}))

    def test_concurrent_calls_and_exception_results(self) -> None:
        _, report = self.json_audit(
            "from asyncio import gather as collect\n"
            "from concurrent.futures import ThreadPoolExecutor as Pool\n"
            "pool = Pool(4)\ncollect(a, b, return_exceptions=True)\n",
        )
        self.assertTrue({"RF601", "RF602"}.issubset({item["rule"] for item in report["findings"]}))

    def test_quantile_method_explicit_or_missing(self) -> None:
        _, report = self.json_audit(
            "import numpy as np\nfrom numpy import percentile as pct\n"
            "a = np.quantile(x, .5)\nb = pct(x, 50)\n"
            "c = np.quantile(x, .5, method='linear')\n"
            "d = np.quantile(x, .5, None, None, False, 'linear')\n",
        )
        self.assertEqual([f["line"] for f in report["findings"] if f["rule"] == "RF701"], [3, 4])

    def test_all_quantile_methods_and_unpacked_arguments(self) -> None:
        for function in ("quantile", "percentile", "nanquantile", "nanpercentile"):
            with self.subTest(function=function):
                _, report = self.json_audit(
                    "import numpy as np\n"
                    f"np.{function}(x, .5, None, None, False)\n"
                    f"np.{function}(x, .5, None, None, False, 'linear')\n"
                    f"np.{function}(x, .5, method='linear')\n"
                    f"np.{function}(*args)\n"
                    f"np.{function}(x, .5, **options)\n"
                    f"np.{function}(x, .5, *args, None, None, 'linear')\n"
                )
                findings = [f for f in report["findings"] if f["rule"] == "RF701"]
                self.assertEqual([f["line"] for f in findings], [2, 5, 6, 7])
                self.assertTrue(all("unpacked" in f["detail"] for f in findings[1:]))

    def test_function_imports_and_bindings_do_not_leak(self) -> None:
        _, report = self.json_audit(
            "from openai import OpenAI\n"
            "def unrelated():\n    from local_backend import OpenAI\n"
            "def parameter(OpenAI):\n    OpenAI()\n"
            "def lexical_local():\n    OpenAI()\n    OpenAI = factory\n"
            "def local_client():\n    from openai import OpenAI\n    OpenAI()\n"
            "OpenAI()\n"
            "OpenAI = factory\nOpenAI()\n"
        )
        self.assertEqual([f["line"] for f in report["findings"] if f["rule"] == "RF504"], [11, 12])

    def test_annotated_assignment_reads_rhs_before_rebinding(self) -> None:
        _, report = self.json_audit(
            "from openai import OpenAI\n"
            "OpenAI: object\nOpenAI()\n"
            "OpenAI: object = OpenAI()\nOpenAI()\n"
        )
        self.assertEqual([f["line"] for f in report["findings"] if f["rule"] == "RF504"], [3, 4])

    def test_class_scope_is_not_method_scope(self) -> None:
        _, report = self.json_audit(
            "from openai import OpenAI\n"
            "class Example:\n"
            "    from local_backend import OpenAI\n"
            "    client = OpenAI()\n"
            "    def method(self):\n        OpenAI()\n"
            "OpenAI()\n"
            "def enclosing():\n"
            "    from openai import OpenAI as Client\n"
            "    class Inner:\n"
            "        Client = factory\n"
            "        def method(self):\n            Client()\n"
        )
        self.assertEqual([f["line"] for f in report["findings"] if f["rule"] == "RF504"], [6, 7, 13])

    def test_decorators_use_defining_scope_and_async_functions_are_isolated(self) -> None:
        _, report = self.json_audit(
            "from tenacity import retry\nfrom openai import OpenAI\n"
            "@retry\nasync def run(OpenAI):\n    OpenAI()\n"
            "    from local_backend import retry\n"
            "OpenAI()\n"
            "callback = lambda OpenAI: OpenAI()\n"
        )
        self.assertEqual([f["line"] for f in report["findings"] if f["rule"] == "RF501"], [3])
        self.assertEqual([f["line"] for f in report["findings"] if f["rule"] == "RF504"], [7])

    def test_function_numeric_import_does_not_imply_execution(self) -> None:
        _, report = self.json_audit(
            "import os\ndef unused():\n    import numpy\n"
            "os.environ['OMP_NUM_THREADS'] = '1'\n"
            "def configure():\n    os.environ['MKL_NUM_THREADS'] = '1'\n"
            "import numpy\n"
            "def configure_later():\n    os.environ['OMP_NUM_THREADS'] = '2'\n"
            "os.environ['MKL_NUM_THREADS'] = '2'\n"
        )
        findings = [f for f in report["findings"] if f["rule"] == "RF702"]
        self.assertEqual([(f["line"], f["severity"]) for f in findings],
                         [(6, "medium"), (9, "medium"), (10, "high")])
        self.assertTrue(all("unresolved" in f["detail"] for f in findings[:2]))

    def test_class_body_import_executes_in_defining_scope(self) -> None:
        _, report = self.json_audit(
            "import os\nclass Loader:\n    import numpy\n"
            "os.environ['OMP_NUM_THREADS'] = '1'\n"
        )
        self.assertEqual([f["line"] for f in report["findings"] if f["rule"] == "RF702"], [4])

    def test_comprehension_targets_do_not_shadow_enclosing_import(self) -> None:
        _, report = self.json_audit(
            "from openai import OpenAI\n"
            "def run():\n"
            "    local = [OpenAI() for OpenAI in factories]\n"
            "    OpenAI()\n"
            "local = {OpenAI() for OpenAI in factories}\nOpenAI()\n"
        )
        self.assertEqual([f["line"] for f in report["findings"] if f["rule"] == "RF504"], [4, 6])

    def test_global_read_and_nonlocal_read_keep_enclosing_import(self) -> None:
        _, report = self.json_audit(
            "from openai import OpenAI\n"
            "def global_read():\n    global OpenAI\n    OpenAI()\n"
            "def enclosing():\n    from openai import OpenAI as Client\n"
            "    def inner():\n        nonlocal Client\n        Client()\n"
            "    OpenAI = factory\n"
            "    def global_inner():\n        global OpenAI\n        OpenAI()\n"
        )
        self.assertEqual([f["line"] for f in report["findings"] if f["rule"] == "RF504"], [4, 9, 13])

    def test_thread_environment_order(self) -> None:
        for late in (True, False):
            source = "import os\n"
            source += "import numpy as np\n" if late else ""
            source += "os.environ['OMP_NUM_THREADS'] = '1'\n"
            source += "" if late else "import numpy as np\n"
            _, report = self.json_audit(source)
            self.assertEqual("RF702" in {f["rule"] for f in report["findings"]}, late)

    def test_missing_and_empty_inputs_do_not_report_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for path in (directory, str(Path(directory) / "missing.py")):
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), path, "--json"], capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 2)
                self.assertGreater(json.loads(result.stdout)["summary"]["errors"], 0)

    def test_string_literal_cannot_suppress_findings(self) -> None:
        _, report = self.json_audit(
            "text = '# research-fidelity: allow=RF301 reason=not an actual comment'\n"
            "x = values.clip(-1, 1)\n", "--min-severity", "low",
        )
        self.assertEqual(report["summary"]["suppressed"], 0)
        self.assertIn("RF301", {f["rule"] for f in report["findings"]})

    def test_narrow_exception_default_is_not_invisible(self) -> None:
        result, report = self.json_audit(
            "def estimate():\n    try:\n        return run()\n"
            "    except ValueError:\n        return 0\n", "--fail-on", "medium",
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("RF009", {f["rule"] for f in report["findings"]})

    def test_resolved_json_and_toml_retry_and_concurrency_policies(self):
        with tempfile.TemporaryDirectory() as directory:
            for filename, content, expected in (
                ("bad.json", '{"client":{"max_retries":"${RETRIES}"},"workers":{"max_workers":4}}', {"RF801", "RF802"}),
                ("bad.toml", '[client]\ntotal_max_attempts = 3\n', {"RF801"}),
                ("good.json", '{"client":{"max_retries":0},"workers":{"max_workers":1}}', set()),
            ):
                path = Path(directory) / filename
                path.write_text(content, encoding="utf-8")
                result = subprocess.run([sys.executable, str(SCRIPT), "--config", str(path),
                                         "--json", "--fail-on", "medium"], capture_output=True, text=True)
                report = json.loads(result.stdout)
                self.assertEqual(result.returncode, 1 if expected else 0)
                self.assertEqual({f["rule"] for f in report["findings"]}, expected)
                self.assertEqual(report["summary"]["config_files"], 1)
                self.assertTrue(report["coverage"]["unverified"])

    def test_config_parse_failure_and_unsupported_format_are_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            for filename in ("invalid.json", "unsupported.yaml"):
                path = Path(directory) / filename
                path.write_text("not valid", encoding="utf-8")
                result = subprocess.run([sys.executable, str(SCRIPT), "--config", str(path), "--json"],
                                         capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
