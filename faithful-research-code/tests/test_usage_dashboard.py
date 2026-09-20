from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import research_progress as progress


class UsageDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / "run"
        progress.initialize(self.run, {"title": "Usage test", "nodes": [
            {"id": "llm", "track": "execution", "label": "Inference"},
            {"id": "parallel", "track": "execution", "label": "Independent branch"},
            {"id": "join", "track": "execution", "label": "Join", "depends_on": ["llm", "parallel"]},
        ]})
        progress.record(self.run, "llm", "running")
        progress.record(self.run, "parallel", "running")

    def usage(self, request_id="request-1", node="llm", **kwargs):
        values = dict(model="fixture-model", status="running", source="unknown", evidence="test fixture")
        values.update(kwargs)
        progress.record_usage(self.run, node, request_id, **values)

    def test_uninstrumented_does_not_mean_zero(self):
        state = progress.snapshot(self.run)
        self.assertEqual(state["requests"], [])
        self.assertIsNone(state["usage"]["reported"]["input_tokens"])

    def test_cumulative_estimates_are_replaced_not_added_to_reported_usage(self):
        self.usage()
        self.usage(source="estimated", input_tokens=90, output_tokens=4)
        self.usage(source="estimated", input_tokens=90, output_tokens=8)
        self.usage(source="reported", status="succeeded", input_tokens=100, output_tokens=12,
                   cached_input_tokens=60, reasoning_output_tokens=5)
        state = progress.snapshot(self.run)
        self.assertEqual(len(state["requests"]), 1)
        self.assertEqual(state["usage"]["estimated"]["requests"], 0)
        self.assertEqual(state["usage"]["reported"]["input_tokens"], 100)
        self.assertEqual(state["usage"]["reported"]["output_tokens"], 12)
        self.assertEqual(state["usage"]["reported"]["cached_input_tokens"], 60)
        with self.assertRaises(ValueError):
            self.usage(status="succeeded", source="reported", input_tokens=100, output_tokens=12)
        progress.record(self.run, "llm", "succeeded")

    def test_invalid_or_unregistered_usage_never_enters_journal(self):
        before = (self.run / "events.jsonl").read_bytes()
        for arguments in ({"status": "succeeded"}, {"input_tokens": 0},
                          {"source": "reported"}, {"source": "reported", "input_tokens": -1},
                          {"source": "reported", "input_tokens": True},
                          {"source": "reported", "input_tokens": 3, "cached_input_tokens": 4},
                          {"node": "join"}, {"node": "missing"}):
            with self.subTest(arguments=arguments), self.assertRaises((ValueError, KeyError)):
                self.usage(**arguments)
            self.assertEqual((self.run / "events.jsonl").read_bytes(), before)

    def test_pending_request_blocks_stage_success_and_failure_stops_new_requests(self):
        self.usage()
        self.usage("other", node="parallel")
        with self.assertRaises(ValueError):
            progress.record(self.run, "llm", "succeeded")
        self.usage(status="failed", evidence="TimeoutError; usage unavailable")
        with self.assertRaises(ValueError):
            self.usage("must-not-start", node="parallel")
        self.usage("other", node="parallel", status="succeeded", source="reported", input_tokens=10, output_tokens=2)
        progress.record(self.run, "llm", "failed", "TimeoutError")
        progress.record(self.run, "parallel", "succeeded")
        state = progress.snapshot(self.run)
        self.assertEqual(state["tracks"]["execution"], "stopped")
        self.assertIsNone(state["usage"]["unknown"]["input_tokens"])
        self.assertEqual(state["usage"]["reported"]["input_tokens"], 10)
        with self.assertRaises(ValueError):
            progress.record(self.run, "join", "running")

    def test_unknown_usage_does_not_fabricate_failed_science(self):
        self.usage()
        self.usage(status="succeeded", evidence="Response complete; provider omitted usage")
        progress.record(self.run, "llm", "succeeded")
        state = progress.snapshot(self.run)
        self.assertEqual(state["requests"][0]["status"], "succeeded")
        self.assertEqual(state["usage"]["unknown"]["input_tokens_unknown"], 1)

    def test_reported_partial_usage_is_preserved_and_lost_request_is_unknown(self):
        self.usage(source="reported", input_tokens=20)
        with self.assertRaises(ValueError):
            self.usage(source="estimated", input_tokens=21)
        with self.assertRaises(ValueError):
            self.usage(source="reported", input_tokens=19)
        with self.assertRaises(ValueError):
            self.usage(source="reported", output_tokens=3)
        progress.record(self.run, "llm", "failed", "ConnectionError")
        state = progress.snapshot(self.run)
        self.assertEqual(state["requests"][0]["display_status"], "unknown")
        self.assertEqual(state["usage"]["reported"]["input_tokens"], 20)
        self.assertIsNone(state["usage"]["reported"]["output_tokens"])

    def test_usage_updates_use_existing_authenticated_collector(self):
        endpoint = Path(self.temp.name) / "private.json"
        collector = subprocess.Popen([sys.executable, str(SCRIPTS / "research_progress.py"), "collect",
                                      str(self.run), "--endpoint", str(endpoint)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(collector.stdout.readline().strip(), "Progress collector ready")
            self.usage(collector=endpoint)
            with self.assertRaises(RuntimeError):
                self.usage("direct-write")
            self.usage(status="succeeded", source="reported", input_tokens=25, output_tokens=0, collector=endpoint)
            state = progress.snapshot(self.run)
            self.assertEqual(state["usage"]["reported"]["output_tokens"], 0)
            self.assertEqual(state["usage"]["reported"]["input_tokens"], 25)
            lines = [json.loads(line) for line in (self.run / "events.jsonl").read_text().splitlines()[1:]]
            self.assertEqual([item["seq"] for item in lines], list(range(1, len(lines) + 1)))
            with self.assertRaises(progress.EventRejected):
                with progress.stage(self.run, "join", collector=endpoint):
                    self.fail("Unmet dependencies cannot start")
        finally:
            collector.terminate()
            collector.communicate(timeout=5)

    def test_stage_exit_rejection_stops_track_for_direct_and_collector_writers(self):
        for remote in (False, True):
            with self.subTest(remote=remote):
                run = Path(self.temp.name) / ("remote" if remote else "direct")
                progress.initialize(run, {"title": "Incomplete request", "nodes": [
                    {"id": "call", "track": "execution", "label": "Call"},
                    {"id": "later", "track": "execution", "label": "Independent"},
                ]})
                endpoint = Path(self.temp.name) / "exit-check.json" if remote else None
                collector = None
                try:
                    if remote:
                        collector = subprocess.Popen([sys.executable, str(SCRIPTS / "research_progress.py"), "collect",
                                                      str(run), "--endpoint", str(endpoint)],
                                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        self.assertEqual(collector.stdout.readline().strip(), "Progress collector ready")
                    with self.assertRaises(progress.EventRejected):
                        with progress.stage(run, "call", collector=endpoint):
                            progress.record_usage(run, "call", "unfinished", model="fixture", status="running",
                                                  source="unknown", evidence="test", collector=endpoint)
                    state = progress.snapshot(run)
                    self.assertEqual(state["nodes"][0]["state"], "failed")
                    self.assertEqual(state["tracks"]["execution"], "stopped")
                    self.assertEqual(state["requests"][0]["display_status"], "unknown")
                    with self.assertRaises(progress.EventRejected):
                        with progress.stage(run, "later", collector=endpoint):
                            self.fail("Stopped track cannot dispatch")
                finally:
                    if collector:
                        collector.terminate()
                        collector.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
