#!/usr/bin/env python3
"""Execute the same scientific behavior checks against a supplied generated candidate."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--generator-id", required=True, help="Recorded provenance, not independently verified model identity")
    args = parser.parse_args()
    candidate = args.candidate.resolve(strict=True)
    tests = Path(__file__).resolve().parents[1] / "assets" / "behavior-eval" / "test_candidate.py"
    args.output.mkdir(parents=True, exist_ok=False)
    output = args.output.resolve()
    candidate_source = candidate.read_bytes()
    tests_source = tests.read_bytes()
    candidate_hash = hashlib.sha256(candidate_source).hexdigest()
    tests_hash = hashlib.sha256(tests_source).hexdigest()
    candidate_snapshot = output / "candidate.snapshot.py"
    tests_snapshot = output / "tests.snapshot.py"
    candidate_snapshot.write_bytes(candidate_source)
    tests_snapshot.write_bytes(tests_source)
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parent), PYTHONUTF8="1")
    checks_path = output / "checks.json"
    expected_checks = sorted(method.name for cls in ast.parse(tests_source, filename=str(tests)).body
                             if isinstance(cls, ast.ClassDef) and cls.name == "ScientificChecks"
                             for method in cls.body if isinstance(method, ast.FunctionDef) and method.name.startswith("test_"))
    command = [sys.executable, str(tests_snapshot), str(candidate), str(candidate_snapshot), candidate_hash,
               str(output / "runs"), str(checks_path)]
    checks = None
    checks_verified = False
    try:
        with (output / "test.log").open("xb") as log:
            result = subprocess.run(command, env=env, cwd=candidate.parent, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=60, check=False)
        returncode = result.returncode
        if checks_path.is_file():
            try:
                checks = json.loads(checks_path.read_text(encoding="utf-8"))
                checks_verified = bool(expected_checks) and isinstance(checks, dict) and (
                    checks.get("successful_tests") == expected_checks
                    and checks.get("tests_run") == len(expected_checks)
                    and checks.get("successful") is True)
            except (OSError, ValueError):
                # research-fidelity: allow=RF009 reason="Invalid test completion evidence forces FAIL; never a scientific fallback."
                checks_verified = False
        status = "PASS" if returncode == 0 and checks_verified else "FAIL"
    except subprocess.TimeoutExpired:
        returncode, status = None, "TIMEOUT"
    report = {
        "status": status, "returncode": returncode,
        "checks_verified": checks_verified, "expected_checks": expected_checks, "checks": checks,
        "generator_id_as_supplied": args.generator_id, "candidate": str(candidate),
        "candidate_sha256": candidate_hash, "candidate_snapshot": str(candidate_snapshot),
        "test_sha256": tests_hash, "test_snapshot": str(tests_snapshot), "command": command,
        "claim": "Only this candidate passed/failed these local mock scenarios; no cross-model or live-service claim",
        "unverified": ["automatic skill selection", "live SDK/server behavior", "other prompts/models"],
    }
    (output / "evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"{report['status']}: {output / 'evaluation.json'}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
