from __future__ import annotations

import importlib.util
import json
import socket
import struct
import threading
import time
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import urlopen
from urllib.error import HTTPError


SCRIPT = Path(__file__).parents[1] / "scripts" / "research_progress.py"
spec = importlib.util.spec_from_file_location("research_progress", SCRIPT)
progress = importlib.util.module_from_spec(spec)
spec.loader.exec_module(progress)


class ResearchProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / "run"
        self.plan = {"title": "真实进度", "nodes": [
            {"id": "code", "track": "generation", "label": "生成"},
            {"id": "load", "track": "execution", "label": "读取"},
            {"id": "metric", "track": "execution", "label": "统计", "depends_on": ["load"]},
        ]}
        progress.initialize(self.run, self.plan)

    def test_tracks_dependencies_and_no_implicit_restart(self):
        with progress.stage(self.run, "code"):
            pass
        state = progress.snapshot(self.run)
        self.assertEqual([n["state"] for n in state["nodes"]], ["succeeded", "pending", "pending"])
        with self.assertRaises(ValueError):
            progress.record(self.run, "metric", "running")
        with self.assertRaises(ValueError):
            progress.record(self.run, "code", "running")
        with progress.stage(self.run, "load"):
            pass
        with progress.stage(self.run, "metric"):
            pass
        self.assertEqual(progress.snapshot(self.run)["events"], 6)
        self.assertIn("n_load --> n_metric", progress.mermaid(progress.snapshot(self.run)))

    def test_requirement_metadata_survives_events_without_implying_review(self):
        run = Path(self.temp.name) / "metadata"
        description = '固定测试数据 → 校验全部三行 → 有效数据\n检查：禁止缺失行 <not-html>'
        node = {"id": "load", "track": "execution", "label": "Validate local fixture",
                "idea_refs": ["DATA-01", "CHECK-01"], "description": description}
        progress.initialize(run, {"title": "Metadata", "nodes": [node]})
        progress.record(run, "load", "running", "Observed start")
        actual = progress.snapshot(run)["nodes"][0]
        self.assertEqual(actual["idea_refs"], node["idea_refs"])
        self.assertEqual(actual["description"], description)
        self.assertEqual(actual["detail"], "Observed start")
        self.assertEqual(actual["state"], "running")

    def test_invalid_requirement_metadata_rejected_before_run_creation(self):
        for metadata in ({"idea_refs": "DATA-01"}, {"idea_refs": []},
                         {"idea_refs": ["DATA-01", "DATA-01"]}, {"idea_refs": [{}]},
                         {"idea_refs": [" "]}, {"description": []}, {"description": " "}):
            with self.subTest(metadata=metadata):
                run = Path(self.temp.name) / "invalid"
                plan = {"title": "Invalid", "nodes": [dict(self.plan["nodes"][0], **metadata)]}
                with self.assertRaises(ValueError):
                    progress.initialize(run, plan)
                self.assertFalse(run.exists())

    def parallel_run(self):
        run = Path(self.temp.name) / "parallel"
        plan = {"title": "Parallel", "nodes": [
            {"id": "a", "track": "execution", "label": "A", "total": 2},
            {"id": "b", "track": "execution", "label": "B"},
            {"id": "merge", "track": "execution", "label": "Merge", "depends_on": ["a", "b"]},
        ]}
        progress.initialize(run, plan)
        return run

    def test_parallel_fanout_and_join_wait_for_all_inputs(self):
        run = self.parallel_run()
        progress.record(run, "a", "running")
        progress.record(run, "b", "running")
        self.assertEqual(sum(n["state"] == "running" for n in progress.snapshot(run)["nodes"]), 2)
        progress.record(run, "a", "update", completed=1)
        with self.assertRaises(ValueError):
            progress.record(run, "a", "succeeded")
        with self.assertRaises(ValueError):
            progress.record(run, "a", "update", completed=0)
        progress.record(run, "a", "succeeded", completed=2)
        with self.assertRaises(ValueError):
            progress.record(run, "merge", "running")
        progress.record(run, "b", "succeeded")
        with progress.stage(run, "merge"):
            pass
        self.assertEqual(progress.snapshot(run)["tracks"]["execution"], "complete")

    def test_failed_branch_stops_dispatch_but_allows_inflight_evidence(self):
        run = self.parallel_run()
        progress.record(run, "a", "running")
        progress.record(run, "b", "running")
        progress.record(run, "a", "failed", "ValueError")
        progress.record(run, "b", "succeeded", "In-flight work completed after failure")
        state = progress.snapshot(run)
        self.assertEqual([n["state"] for n in state["nodes"]], ["failed", "succeeded", "pending"])
        self.assertEqual(state["nodes"][2]["display_state"], "blocked")
        self.assertEqual(state["tracks"]["execution"], "stopped")
        with self.assertRaises(ValueError):
            progress.record(run, "merge", "running")
        progress.record(run, "merge", "cancelled", "Scheduler confirmed task never launched")

    def test_unknown_never_implies_success_or_automatic_restart(self):
        progress.record(self.run, "load", "running")
        progress.record(self.run, "load", "unknown", "Worker observation lost")
        progress.record(self.run, "load", "succeeded", "Exit status and output later verified")
        state = progress.snapshot(self.run)
        self.assertEqual(state["tracks"]["execution"], "stopped")
        with self.assertRaises(ValueError):
            progress.record(self.run, "metric", "running")

    def test_conditional_skip_requires_predeclared_optional_join(self):
        run = Path(self.temp.name) / "conditional"
        progress.initialize(run, {"title": "Branch", "nodes": [
            {"id": "arm", "track": "execution", "label": "Arm", "condition": "config.arm_enabled"},
            {"id": "join", "track": "execution", "label": "Join", "depends_on": ["arm"], "optional_dependencies": ["arm"]},
        ]})
        with self.assertRaises(ValueError):
            progress.record(self.run, "load", "skipped", "Invented skip")
        progress.record(run, "arm", "skipped", "Frozen config has arm_enabled=false")
        with progress.stage(run, "join"):
            pass
        self.assertEqual(progress.snapshot(run)["tracks"]["execution"], "complete")

    def test_collector_serializes_independent_worker_processes(self):
        run = self.parallel_run()
        endpoint = Path(self.temp.name) / "collector.json"
        collector = subprocess.Popen(
            [sys.executable, str(SCRIPT), "collect", str(run), "--endpoint", str(endpoint)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            self.assertEqual(collector.stdout.readline().strip(), "Progress collector ready")
            with self.assertRaises(RuntimeError):
                progress.record(run, "a", "running")
            workers = [subprocess.Popen(
                [sys.executable, str(SCRIPT), "event", str(run), node, "running", "--collector", str(endpoint)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            ) for node in ("a", "b")]
            for worker in workers:
                _, stderr = worker.communicate(timeout=10)
                self.assertEqual(worker.returncode, 0, stderr)
            self.assertEqual(sum(n["state"] == "running" for n in progress.snapshot(run)["nodes"]), 2)
            progress.emit(endpoint, "a", "failed", "Injected failure")
            progress.emit(endpoint, "b", "cancelled", "Worker confirmed cancellation")
            with self.assertRaises(progress.EventRejected):
                progress.emit(endpoint, "merge", "running")
            state = progress.snapshot(run)
            self.assertEqual(state["events"], 4)
            self.assertEqual(state["tracks"]["execution"], "stopped")
            lines = (run / "events.jsonl").read_text(encoding="utf-8").splitlines()[1:]
            self.assertEqual([json.loads(line)["seq"] for line in lines], [1, 2, 3, 4])
        finally:
            collector.terminate()
            collector.communicate(timeout=5)

    def test_emit_deadline_covers_authentication_and_partial_acknowledgement(self):
        for authenticate in (False, True):
            with self.subTest(authenticate=authenticate), socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(1)
                listener.settimeout(3)
                endpoint = Path(self.temp.name) / "stalled-endpoint.json"
                key = b"k" * 32
                endpoint.write_text(json.dumps({"address": listener.getsockname(), "key": key.hex()}))
                release = threading.Event()
                errors = []

                def stalled_peer():
                    try:
                        sock, _ = listener.accept()
                        with sock:
                            if authenticate:
                                connection = progress.DeadlineConnection(sock, time.monotonic() + 3)
                                progress.deliver_challenge(connection, key)
                                progress.answer_challenge(connection, key)
                                connection.recv_bytes()
                                sock.sendall(struct.pack("!i", 12) + b'{')
                            release.wait(3)
                    except Exception as error:
                        errors.append(error)

                peer = threading.Thread(target=stalled_peer)
                peer.start()
                try:
                    started = time.monotonic()
                    with patch.object(progress, "EVENT_TIMEOUT", .5), self.assertRaises(TimeoutError):
                        progress.emit(endpoint, "a", "running")
                    self.assertLess(time.monotonic() - started, 2)
                finally:
                    release.set()
                    peer.join(timeout=4)
                self.assertFalse(peer.is_alive())
                self.assertEqual(errors, [])

    def test_partial_frame_traffic_does_not_reset_deadline(self):
        receiver, sender = socket.socketpair()
        with receiver, sender:
            release = threading.Event()

            def trickle():
                sender.sendall(struct.pack("!i", 30))
                for _ in range(30):
                    if release.wait(.04):
                        break
                    sender.sendall(b'x')

            peer = threading.Thread(target=trickle)
            peer.start()
            try:
                started = time.monotonic()
                connection = progress.DeadlineConnection(receiver, started + .2)
                with self.assertRaises(TimeoutError):
                    connection.recv_bytes()
                self.assertLess(time.monotonic() - started, 1)
            finally:
                release.set()
                peer.join(timeout=2)
            self.assertFalse(peer.is_alive())

    def test_collector_stops_when_producer_stalls_during_authentication(self):
        endpoint = Path(self.temp.name) / "auth-endpoint.json"
        command = ("import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
                   "import research_progress as p; p.EVENT_TIMEOUT=.5; p.collect(Path(sys.argv[2]), Path(sys.argv[3]))")
        collector = subprocess.Popen([sys.executable, "-c", command, str(SCRIPT.parent), str(self.run), str(endpoint)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(collector.stdout.readline().strip(), "Progress collector ready")
            address = json.loads(endpoint.read_text())["address"]
            with socket.create_connection(tuple(address), timeout=2) as sock:
                self.assertTrue(sock.recv(512))
                _, stderr = collector.communicate(timeout=3)
            self.assertNotEqual(collector.returncode, 0)
            self.assertIn("TimeoutError", stderr)
            self.assertEqual(progress.snapshot(self.run)["events"], 0)
        finally:
            if collector.poll() is None:
                collector.kill()
            collector.communicate(timeout=3)

    def test_required_skipped_dependency_blocks_all_descendants(self):
        run = Path(self.temp.name) / "required-branch"
        progress.initialize(run, {"title": "Required branch", "nodes": [
            {"id": "arm", "track": "execution", "label": "Arm", "condition": "declared condition"},
            {"id": "join", "track": "execution", "label": "Join", "depends_on": ["arm"]},
            {"id": "report", "track": "execution", "label": "Report", "depends_on": ["join"]},
        ]})
        progress.record(run, "arm", "skipped", "Condition false")
        state = progress.snapshot(run)
        self.assertEqual([n.get("display_state") for n in state["nodes"]], [None, "blocked", "blocked"])
        with self.assertRaises(ValueError):
            progress.record(run, "join", "running")

    def test_failure_keeps_original_exception_and_partial_artifacts(self):
        error = ValueError("original failure")
        artifact = self.run / "partial.txt"
        with self.assertRaises(ValueError) as caught:
            with progress.stage(self.run, "load"):
                artifact.write_text("partial result")
                raise error
        self.assertIs(caught.exception, error)
        self.assertEqual(artifact.read_text(), "partial result")
        self.assertEqual(progress.snapshot(self.run)["nodes"][1]["state"], "failed")
        for node in ("load", "metric"):
            with self.assertRaises(ValueError):
                progress.record(self.run, node, "running")
        self.assertNotIn("original failure", (self.run / "events.jsonl").read_text(encoding="utf-8"))

    def test_recording_error_does_not_mask_scientific_error(self):
        manager = progress.stage(self.run, "code")
        manager.__enter__()
        original = RuntimeError("second scientific failure")
        with patch.object(progress, "write_record", side_effect=OSError("disk full")):
            self.assertFalse(manager.__exit__(type(original), original, original.__traceback__))
        self.assertIn("OSError", original.__notes__[0])

    def test_existing_run_and_concurrent_writer_rejected(self):
        with self.assertRaises(FileExistsError):
            progress.initialize(self.run, self.plan)
        before = (self.run / "events.jsonl").read_bytes()
        (self.run / ".writer.lock").write_text("existing writer")
        with self.assertRaises(FileExistsError):
            progress.record(self.run, "load", "running")
        self.assertEqual((self.run / "events.jsonl").read_bytes(), before)
        self.assertTrue((self.run / ".writer.lock").exists())

    def test_cycles_cross_tracks_and_duplicate_ids_rejected(self):
        for plan in (
            {"title": "bad", "nodes": [{"id": "a", "track": "execution", "label": "A", "depends_on": ["a"]}]},
            {"title": "bad", "nodes": [self.plan["nodes"][0], self.plan["nodes"][0]]},
            {"title": "bad", "nodes": [self.plan["nodes"][0], dict(self.plan["nodes"][1], depends_on=["code"])]},
        ):
            with self.assertRaises(ValueError):
                progress.validate_plan(plan)

    def test_corrupt_journal_is_not_repaired_or_reported_success(self):
        journal = self.run / "events.jsonl"
        with journal.open("a") as stream:
            stream.write('{"partial":')
        original = journal.read_bytes()
        with self.assertRaises(ValueError):
            progress.snapshot(self.run)
        with self.assertRaises(ValueError):
            progress.record(self.run, "load", "running")
        self.assertEqual(journal.read_bytes(), original)

    def test_viewer_reflects_events_without_serving_artifacts(self):
        process = subprocess.Popen(
            [sys.executable, str(SCRIPT), "serve", str(self.run)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            url = process.stdout.readline().strip()
            self.assertTrue(url.startswith("http://127.0.0.1:"))
            with urlopen(url, timeout=5) as response:
                self.assertIn(b"<script>", response.read())
            progress.record(self.run, "load", "running")
            with urlopen(url + "/state", timeout=5) as response:
                state = json.load(response)
            self.assertEqual(state["nodes"][1]["state"], "running")
            for path in ("/events.jsonl", "/../secret", "/state?other=run"):
                with self.assertRaises(HTTPError) as caught:
                    urlopen(url + path, timeout=5)
                self.assertEqual(caught.exception.code, 404)
        finally:
            process.terminate()
            process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
