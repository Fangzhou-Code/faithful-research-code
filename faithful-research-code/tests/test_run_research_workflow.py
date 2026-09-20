from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import research_progress as progress
import run_research_workflow as runner


def node(identifier, code, dependencies=(), timeout=5):
    return {"id": identifier, "label": identifier, "track": "execution", "depends_on": list(dependencies),
            "argv": ["{python}", "-c", code], "timeout_seconds": timeout}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cwd = Path(self.temp.name)
        self.run = self.cwd / "run"

    def plan(self, nodes, workers=1):
        return {"title": "Runtime validation", "max_parallel": workers, "process_scope": "direct_children_only",
                "parallelism_source": "isolated independent test commands", "required_checks": [nodes[0]["id"]],
                "nodes": nodes}

    def test_parallel_dependencies_and_manifest(self):
        plan = self.plan([node("a", "import time; time.sleep(.2)"), node("b", "import time; time.sleep(.2)"),
                          node("join", "print('checked')", ["a", "b"])], 2)
        runner.run(plan, self.run, self.cwd)
        state = progress.snapshot(self.run)
        self.assertEqual(state["observation"], "finished")
        self.assertEqual([n["state"] for n in state["nodes"]], ["succeeded"] * 3)
        events = [json.loads(line) for line in (self.run / "events.jsonl").read_text().splitlines()[1:]]
        self.assertEqual([(e["node"], e["state"]) for e in events[:2]], [("a", "running"), ("b", "running")])
        manifest = json.loads((self.run / "RUN_COMPLETE.json").read_text())
        self.assertEqual(set(manifest["outcomes"]), {"a", "b", "join"})
        self.assertEqual(len(manifest["log_sha256"]["join"]), 64)

    def test_failure_cancels_inflight_and_never_launches_join(self):
        plan = self.plan([node("bad", "import time; time.sleep(.2); raise ValueError('injected')"),
                          node("slow", "import time; time.sleep(30)", timeout=40),
                          node("join", "raise AssertionError('must not run')", ["bad", "slow"])], 2)
        with self.assertRaises(subprocess.CalledProcessError):
            runner.run(plan, self.run, self.cwd)
        states = {n["id"]: n["state"] for n in progress.snapshot(self.run)["nodes"]}
        self.assertEqual(states, {"bad": "failed", "slow": "cancelled", "join": "pending"})
        self.assertFalse((self.run / "join").exists())
        self.assertFalse((self.run / "RUN_COMPLETE.json").exists())
        self.assertIn("ValueError", (self.run / "bad" / "stage.log").read_text())

    def test_timeout_stops_and_preserves_logs(self):
        with self.assertRaises(TimeoutError):
            runner.run(self.plan([node("slow", "import time; time.sleep(30)", timeout=.2)]), self.run, self.cwd)
        self.assertTrue((self.run / "slow" / "stage.log").exists())
        self.assertFalse((self.run / "RUN_COMPLETE.json").exists())
        self.assertEqual(progress.snapshot(self.run)["nodes"][0]["state"], "failed")

    def test_timeout_with_unconfirmed_termination_keeps_failure_and_shows_unknown(self):
        children = []
        original_popen = subprocess.Popen

        def capture(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            children.append(process)
            return process

        try:
            with patch.object(runner.subprocess, "Popen", side_effect=capture), \
                    patch.object(runner, "terminate_owned", side_effect=PermissionError("injected denial")), \
                    self.assertRaises(TimeoutError):
                runner.run(self.plan([node("slow", "import time; time.sleep(30)", timeout=.1),
                                      node("next", "raise AssertionError('must not launch')", ["slow"])]), self.run, self.cwd)
            self.assertIsNone(children[0].poll())
            state = progress.snapshot(self.run)
            self.assertEqual(state["nodes"][0]["state"], "failed")
            self.assertEqual(state["nodes"][0]["display_state"], "unknown")
            self.assertEqual(state["nodes"][0]["termination_status"], "unknown")
            self.assertEqual(state["tracks"]["execution"], "stopped")
            self.assertIn('unknown', progress.mermaid(state))
            self.assertEqual(json.loads((self.run / "RUN_FAILED.json").read_text())["termination_unknown"], ["slow"])
            self.assertFalse((self.run / "RUN_COMPLETE.json").exists())
            self.assertFalse((self.run / "next").exists())
        finally:
            for process in children:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)

    def test_missing_required_checks_block_before_execution(self):
        plan = self.plan([node("a", "print('must not run')")])
        plan["required_checks"] = ["missing"]
        with self.assertRaises(ValueError):
            runner.run(plan, self.run, self.cwd)
        self.assertFalse(self.run.exists())

    def test_atomic_publication_failure_has_no_completion_manifest(self):
        original = Path.replace
        def replace(path, target):
            if Path(target).name == "RUN_COMPLETE.json":
                raise OSError("publication failure")
            return original(path, target)
        with patch.object(Path, "replace", replace), self.assertRaises(OSError):
            runner.run(self.plan([node("a", "print('done')")]), self.run, self.cwd)
        self.assertFalse((self.run / "RUN_COMPLETE.json").exists())
        self.assertTrue((self.run / "RUN_COMPLETE.json.pending").exists())

    def test_stale_supervisor_is_unknown_without_fabricating_failure(self):
        progress.initialize(self.run, self.plan([node("a", "print('unused')")]))
        progress.record(self.run, "a", "running")
        stale = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
        runner.atomic_json(self.run / "supervisor.json", {"state": "running", "last_seen": stale,
                                                          "pid": 1, "stale_after_seconds": 5})
        state = progress.snapshot(self.run)
        self.assertEqual(state["observation"], "unknown")
        self.assertEqual(state["nodes"][0]["state"], "running")
        self.assertEqual(state["nodes"][0]["display_state"], "unknown")


if __name__ == "__main__":
    unittest.main()
