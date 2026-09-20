from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import research_progress as p


class IncrementalProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / "run"
        p.initialize(self.run, {"title": "Incremental", "nodes": [
            {"id": "a", "label": "A", "track": "execution", "total": 2},
            {"id": "b", "label": "B", "track": "execution"},
        ]})
        p.record(self.run, "a", "running")
        p.record(self.run, "b", "running")

    def usage(self, **kwargs):
        fields = dict(model="fixture", status="running", source="unknown", evidence="test")
        fields.update(kwargs)
        p.record_usage(self.run, "a", "r1", **fields)

    def test_incremental_usage_matches_full_replay_and_waits_for_stage_boundary(self):
        reader = p.Journal(self.run)
        reader.sync()
        first = reader.view()["version"]
        for update in ({}, {"source": "estimated", "input_tokens": 90},
                       {"source": "reported", "input_tokens": 100, "output_tokens": 5},
                       {"source": "reported", "input_tokens": 100, "output_tokens": 8, "status": "succeeded"}):
            self.usage(**update)
            reader.sync()
            self.assertEqual(reader.view(), p.snapshot(self.run))
            self.assertEqual(reader.view()["version"], first)
        p.record(self.run, "a", "update", completed=1)
        reader.sync()
        self.assertNotEqual(reader.view()["version"], first)
        self.assertEqual(reader.view()["usage"]["reported"]["output_tokens"], 8)
        self.assertEqual(reader.view()["nodes"][1]["state"], "running")

    def test_unchanged_polls_and_new_writes_do_not_replay_old_events(self):
        reader = p.Journal(self.run)
        reader.sync()
        with patch.object(p, "apply_event", wraps=p.apply_event) as apply:
            reader.sync()
            reader.view(include_requests=False)
            self.assertEqual(apply.call_count, 0)
            self.usage()
            self.assertEqual(apply.call_count, 1)
            reader.sync()
            self.assertEqual(apply.call_count, 2)
            reader.sync()
            self.assertEqual(apply.call_count, 2)

    def test_rejected_event_does_not_mutate_cached_state(self):
        before = p.snapshot(self.run)
        with self.assertRaises(p.EventRejected):
            p.record(self.run, "a", "succeeded", completed=1)
        writer = p.writer_journal(self.run.resolve())
        self.assertEqual(writer.view(), before)
        self.usage()
        with self.assertRaises(p.EventRejected):
            self.usage(source="reported", input_tokens=1, output_tokens=-1)
        self.assertEqual(writer.view(), p.snapshot(self.run))

    def test_uncertain_write_stops_cached_writer_without_resend(self):
        with patch.object(p, "write_record", side_effect=OSError("injected")):
            with self.assertRaises(OSError):
                self.usage()
        with self.assertRaises(FileExistsError):
            self.usage()
        p.writer_journal.cache_clear()
        with self.assertRaises(FileExistsError):
            self.usage()
        self.assertTrue((self.run / ".writer.lock").exists())
        self.assertEqual(p.snapshot(self.run)["requests"], [])

    def test_partial_tail_is_unavailable_then_consumed_once_when_complete(self):
        reader = p.Journal(self.run)
        reader.sync()
        event = {"seq": 3, "node": "a", "state": "update", "completed": 1, "detail": "batch", "at": "test"}
        encoded = json.dumps(event).encode()
        with reader.path.open("ab") as stream:
            stream.write(encoded[:20])
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            reader.sync()
        self.assertEqual(reader.events, 2)
        with reader.path.open("ab") as stream:
            stream.write(encoded[20:] + b"\n")
        reader.sync()
        self.assertEqual(reader.events, 3)
        self.assertEqual(reader.view(), p.snapshot(self.run))

    def test_truncation_and_replacement_are_rejected(self):
        reader = p.Journal(self.run)
        reader.sync()
        content = reader.path.read_bytes()
        reader.path.write_bytes(content[:20])
        with self.assertRaisesRegex(ValueError, "truncated"):
            reader.sync()
        replacement = self.run / "replacement"
        replacement.write_bytes(content)
        replacement.replace(reader.path)
        with self.assertRaisesRegex(ValueError, "replaced"):
            reader.sync()

    def test_request_failure_and_termination_health_trigger_display_updates(self):
        reader = p.Journal(self.run)
        reader.sync()
        version = reader.view()["version"]
        self.usage()
        self.usage(status="failed")
        reader.sync()
        self.assertNotEqual(reader.view()["version"], version)
        self.assertEqual(reader.view()["tracks"]["execution"], "stopped")
        health = {"state": "stopped", "last_seen": "2026-01-01T00:00:00+00:00", "stale_after_seconds": 5,
                  "termination_unknown": []}
        path = self.run / "supervisor.json"
        path.write_text(json.dumps(health))
        version = reader.view()["version"]
        health["termination_unknown"] = ["a"]
        path.write_text(json.dumps(health))
        self.assertNotEqual(reader.view()["version"], version)

    def test_ten_thousand_requests_rebuild_matches_incremental_totals(self):
        path = self.run / "events.jsonl"
        sequence = 2
        with path.open("a", encoding="utf-8") as stream:
            for index in range(10000):
                for status in ("running", "succeeded"):
                    sequence += 1
                    usage = dict(request_id=f"r{index}", model="fixture", evidence="test", status=status,
                                 source="reported", input_tokens=10, output_tokens=2,
                                 cached_input_tokens=None, reasoning_output_tokens=None)
                    stream.write(json.dumps(dict(seq=sequence, node="a", state="usage", usage=usage, at="test")) + "\n")
        reader = p.Journal(self.run)
        with patch.object(p, "apply_event", wraps=p.apply_event) as apply:
            reader.sync()
            self.assertEqual(apply.call_count, 20002)
            reader.sync()
            self.assertEqual(apply.call_count, 20002)
        self.assertEqual(reader.view(), p.snapshot(self.run))
        self.assertEqual(reader.view()["usage"]["reported"]["input_tokens"], 100000)


if __name__ == "__main__":
    unittest.main()
