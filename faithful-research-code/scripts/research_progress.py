#!/usr/bin/env python3
"""Single-writer research progress journal and read-only loopback viewer (stdlib)."""
from __future__ import annotations

import argparse
from functools import lru_cache
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import socket
import struct
import time
from multiprocessing.connection import answer_challenge, deliver_challenge


STATES = {"pending", "running", "succeeded", "failed", "blocked", "cancelled", "skipped", "unknown"}
TRACKS = {"generation", "execution"}
EVENT_TIMEOUT = 30.0
TOKEN_FIELDS = ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_output_tokens")


class EventRejected(ValueError):
    """A proposed event was rejected before any journal append."""


def validate_plan(plan: dict) -> None:
    if not isinstance(plan.get("title"), str) or not plan["title"].strip():
        raise ValueError("Plan requires a title")
    nodes = plan.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("Plan requires nodes")
    seen = {}
    for node in nodes:
        identifier = node["id"]
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", identifier):
            raise ValueError("Node ID must be a stable ASCII identifier")
        if identifier in seen or node["track"] not in TRACKS:
            raise ValueError("Duplicate ID or invalid track")
        if not isinstance(node["label"], str) or not node["label"].strip():
            raise ValueError("Node requires a label")
        if "description" in node and (not isinstance(node["description"], str) or not node["description"].strip()):
            raise ValueError("Node description must be nonempty text")
        if "idea_refs" in node:
            refs = node["idea_refs"]
            if (not isinstance(refs, list) or not refs
                    or any(not isinstance(ref, str) or not ref.strip() for ref in refs)
                    or len(set(refs)) != len(refs)):
                raise ValueError("Idea references must be a nonempty array of distinct requirement IDs")
        deps = node.get("depends_on", [])
        if not isinstance(deps, list) or any(not isinstance(dep, str) for dep in deps):
            raise ValueError("Dependencies must be an array of IDs")
        if len(set(deps)) != len(deps) or any(dep not in seen for dep in deps):
            raise ValueError("Dependencies must precede the node, without duplicates or cycles")
        if any(seen[dep] != node["track"] for dep in deps):
            raise ValueError("Generation and execution tracks must stay independent")
        optional = node.get("optional_dependencies", [])
        if not isinstance(optional, list) or any(dep not in deps for dep in optional):
            raise ValueError("Optional dependencies must be declared dependency IDs")
        if "condition" in node and (not isinstance(node["condition"], str) or not node["condition"].strip()):
            raise ValueError("Conditional nodes require a nonempty condition")
        if "total" in node and (type(node["total"]) is not int or node["total"] < 0):
            raise ValueError("Declared work total must be a nonnegative integer")
        seen[identifier] = node["track"]


def transition(nodes: list[dict], event: dict) -> None:
    by_id = {node["id"]: node for node in nodes}
    node = by_id[event["node"]]
    target = event["state"]
    if target not in (STATES - {"pending"}) | {"update"}:
        raise ValueError("Invalid event state")
    peers = [n for n in nodes if n["track"] == node["track"]]
    stopped = any(n.get("stop_requested", False) for n in peers)
    dependencies_ready = all(by_id[dep]["state"] == "succeeded" or (
        by_id[dep]["state"] == "skipped" and dep in node.get("optional_dependencies", [])
    ) for dep in node.get("depends_on", []))
    if target == "running":
        if stopped or node["state"] != "pending":
            raise ValueError("Track stopped or node already started; no implicit restart")
        if not dependencies_ready:
            raise ValueError("Dependencies have not succeeded")
    elif target == "update":
        if node["state"] != "running":
            raise ValueError("Only an observed running stage can emit progress")
    elif target == "skipped":
        if stopped or not dependencies_ready or node["state"] != "pending" or not node.get("condition") or not event.get("detail"):
            raise ValueError("Skipping requires a predeclared condition and observed reason before work")
    elif target == "cancelled":
        if node["state"] not in {"pending", "running", "unknown", "blocked"} or not event.get("detail"):
            raise ValueError("Cancellation requires confirmation and a reason")
    elif target == "unknown":
        if node["state"] != "running" or not event.get("detail"):
            raise ValueError("Unknown requires lost observation of a running node and a reason")
    elif target == "blocked":
        if node["state"] not in {"pending", "running"}:
            raise ValueError("Completed node cannot be blocked")
    elif node["state"] not in {"running", "unknown"}:
        raise ValueError("Success/failure requires a running node")
    if not isinstance(event.get("detail", ""), str):
        raise ValueError("Event detail must be text")
    if "completed" in event:
        completed = event["completed"]
        if (type(completed) is not int or completed < node.get("completed", 0)
                or "total" not in node or completed > node["total"] or target not in {"update", "succeeded"}):
            raise ValueError("Progress requires monotonic counts within the declared total")
    if target == "succeeded" and "total" in node and event.get("completed", node.get("completed", 0)) != node["total"]:
        raise ValueError("Cannot succeed before completing the declared work total")
    if "completed" in event:
        node["completed"] = event["completed"]
    if target in {"failed", "blocked", "unknown", "cancelled"}:
        node["stop_requested"] = True  # Sticky: later evidence must not restart dispatch.
    if target == "running":
        node["started_at"] = event["at"]
    node.update(state=node["state"] if target == "update" else target,
                updated_at=event["at"], detail=event.get("detail", ""))


def snapshot(run_dir: Path) -> dict:
    """Independent full reconstruction for CLI inspection and audit comparisons."""
    journal = Journal(run_dir)
    journal.sync()
    return journal.view()


def render_state(run_dir: Path, title: str, nodes: list[dict], requests: list[dict],
                 events: int, usage: dict, revision: int) -> dict:
    tracks = {}
    for track in TRACKS:
        peers = [node for node in nodes if node["track"] == track]
        halted = any(node["stop_requested"] for node in peers)
        tracks[track] = "stopped" if halted else (
            "complete" if peers and all(n["state"] in {"succeeded", "skipped"} for n in peers) else "incomplete")
    # Derived display only: journal states remain intact for in-flight and cancellation acknowledgements.
    by_id = {node["id"]: node for node in nodes}
    for node in nodes:
        if node["state"] == "pending" and (tracks[node["track"]] == "stopped" or any(
            by_id[dep].get("display_state", by_id[dep]["state"]) in {"blocked", "cancelled", "failed", "unknown"} or (
                by_id[dep]["state"] == "skipped" and dep not in node.get("optional_dependencies", []))
            for dep in node.get("depends_on", [])
        )):
            node["display_state"] = "blocked"
    observation = "events_only"
    health_path = run_dir / "supervisor.json"
    if health_path.exists():
        health = json.loads(health_path.read_text(encoding="utf-8"))
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(health["last_seen"])).total_seconds()
        observation = health["state"]
        if health["state"] == "running" and age > health["stale_after_seconds"]:
            observation = "unknown"
        if observation in {"unknown", "stopped"}:
            for node in nodes:
                if node["state"] == "running":
                    node["display_state"] = "unknown"
        for node in nodes:
            if node["id"] in health.get("termination_unknown", []):
                node["termination_status"] = "unknown"
                node["display_state"] = "unknown"
        if observation == "finished" and not (run_dir / "RUN_COMPLETE.json").exists():
            observation = "awaiting_publication"
    for request in requests:
        owner = by_id[request["node"]]
        if request["status"] == "running" and (observation in {"unknown", "stopped"}
                or owner.get("display_state", owner["state"]) in {"failed", "unknown", "cancelled", "blocked"}):
            request["display_status"] = "unknown"
    version = json.dumps([revision, observation,
                          [(n["id"], n.get("display_state", n["state"]), n.get("termination_status")) for n in nodes]])
    return {"title": title, "nodes": nodes, "tracks": tracks, "observation": observation, "events": events,
            "run_id": run_dir.name, "requests": requests, "usage": usage, "version": version}


def apply_event(nodes: list[dict], requests: dict[str, dict], event: dict) -> None:
    if event["state"] != "usage":
        if "usage" in event:
            raise ValueError("Token metadata requires a usage event")
        if event["state"] == "succeeded" and any(
                item["node"] == event["node"] and item["status"] != "succeeded" for item in requests.values()):
            raise ValueError("Stage cannot succeed with unfinished or unsuccessful LLM requests")
        transition(nodes, event)
        return
    value = event["usage"]
    required = {"request_id", "model", "status", "source", "evidence", *TOKEN_FIELDS}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("Usage requires the declared request identity, evidence and token fields")
    if any(not isinstance(value[key], str) or not value[key].strip() for key in ("request_id", "model", "evidence")):
        raise ValueError("Request identity and evidence must be nonempty text")
    if value["status"] not in {"running", "succeeded", "failed", "unknown"} or value["source"] not in {"reported", "estimated", "unknown"}:
        raise ValueError("Invalid request status or usage source")
    for key in TOKEN_FIELDS:
        count = value[key]
        if count is not None and (type(count) is not int or not 0 <= count <= 2**53 - 1):
            raise ValueError("Tokens must be nonnegative safe integers or null when unknown")
    if value["source"] == "unknown" and any(value[key] is not None for key in TOKEN_FIELDS):
        raise ValueError("Unknown usage cannot contain invented counts")
    if value["source"] != "unknown" and all(value[key] is None for key in TOKEN_FIELDS):
        raise ValueError("Reported/estimated usage needs at least one count")
    for part, total in (("cached_input_tokens", "input_tokens"), ("reasoning_output_tokens", "output_tokens")):
        if value[part] is not None and value[total] is not None and value[part] > value[total]:
            raise ValueError("Token breakdown cannot exceed its inclusive total")
    owner = {node["id"]: node for node in nodes}[event["node"]]
    previous = requests.get(value["request_id"])
    if previous is None:
        if owner["track"] != "execution" or owner["state"] != "running" or value["status"] != "running":
            raise ValueError("Register each LLM request before calling it, in a running execution stage")
        if any(node["stop_requested"] for node in nodes if node["track"] == owner["track"]):
            raise ValueError("Stopped track cannot register another request")
        previous = {"node": event["node"], "started_at": event["at"]}
        requests[value["request_id"]] = previous
    elif (previous["node"] != event["node"] or previous["model"] != value["model"]
          or previous["status"] != "running"):
        raise ValueError("Request identity is immutable; terminal usage cannot be resent or overwritten")
    elif previous["source"] == "reported" and (value["source"] != "reported" or any(
            previous[key] is not None and (value[key] is None or value[key] < previous[key]) for key in TOKEN_FIELDS)):
        raise ValueError("Reported cumulative usage cannot be downgraded, erased or decreased")
    previous.update(value, updated_at=event["at"])
    if value["status"] in {"failed", "unknown"}:
        owner["stop_requested"] = True


def usage_totals(requests: list[dict]) -> dict:
    totals = {}
    for source in ("reported", "estimated", "unknown"):
        selected = [item for item in requests if item["source"] == source]
        totals[source] = {"requests": len(selected)}
        for key in TOKEN_FIELDS:
            known = [item[key] for item in selected if item[key] is not None]
            totals[source][key] = sum(known) if known else None
            totals[source][key + "_unknown"] = len(selected) - len(known)
    return totals


class Journal:
    """Incremental reader of one immutable-plan, append-only journal; no file repair."""

    def __init__(self, run_dir: Path):
        self.run_dir = run_dir.resolve()
        self.path = self.run_dir / "events.jsonl"
        self.offset = 0
        self.identity = None
        self.stamp = None
        self.plan = None
        self.nodes = []
        self.requests = {}
        self.totals = usage_totals([])
        self.events = 0
        self.revision = 0
        self.write_uncertain = False

    @staticmethod
    def file_stamp(info):
        return (info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def sync(self) -> None:
        if self.write_uncertain:
            raise RuntimeError("Journal write outcome uncertain; stop and inspect evidence")
        with self.path.open("rb") as stream:
            info = os.fstat(stream.fileno())
            identity = (info.st_dev, info.st_ino)
            if self.identity is not None and identity != self.identity:
                raise ValueError("Append-only journal was replaced")
            if info.st_size < self.offset:
                raise ValueError("Append-only journal was truncated")
            stamp = self.file_stamp(info)
            if info.st_size == self.offset and self.stamp is not None:
                if stamp != self.stamp:
                    raise ValueError("Append-only journal was modified without an append")
                return
            self.identity = identity
            stream.seek(self.offset)
            appended = stream.read(info.st_size - self.offset)
        for line in appended.splitlines(keepends=True):
            if not line.endswith(b"\n"):
                raise ValueError("Incomplete journal record; observation unavailable")
            value = json.loads(line)
            if self.plan is None:
                plan = value["plan"]
                validate_plan(plan)
                self.plan = plan
                self.nodes = [dict(n, state="pending", detail="", completed=0, stop_requested=False)
                              for n in plan["nodes"]]
            else:
                self.accept(value)
            self.offset += len(line)
        if self.plan is None:
            raise ValueError("Journal has no plan")
        self.stamp = stamp

    def adjust_usage(self, item: dict, sign: int) -> None:
        group = self.totals[item["source"]]
        group["requests"] += sign
        for field in TOKEN_FIELDS:
            if item[field] is None:
                group[field + "_unknown"] += sign
            else:
                group[field] = (0 if group[field] is None else group[field]) + sign * item[field]
            if group["requests"] == group[field + "_unknown"]:
                group[field] = None

    def accept(self, event: dict) -> None:
        if event["seq"] != self.events + 1:
            raise ValueError("Journal sequence mismatch")
        previous = None
        if event["state"] == "usage" and isinstance(event.get("usage"), dict):
            request_id = event["usage"].get("request_id")
            if isinstance(request_id, str) and request_id in self.requests:
                previous = dict(self.requests[request_id])
        apply_event(self.nodes, self.requests, event)
        if event["state"] == "usage":
            if previous is not None:
                self.adjust_usage(previous, -1)
            self.adjust_usage(self.requests[event["usage"]["request_id"]], 1)
            if event["usage"]["status"] in {"failed", "unknown"}:
                self.revision += 1  # Show a request failure immediately, even before stage exit.
        else:
            self.revision += 1
        self.events += 1

    def view(self, *, include_requests: bool = True) -> dict:
        # Display-only state must never contaminate the accepted journal state.
        nodes = [dict(n) for n in self.nodes]
        requests = [dict(r) for r in self.requests.values()] if include_requests else []
        return render_state(self.run_dir, self.plan["title"], nodes, requests, self.events,
                            {name: dict(value) for name, value in self.totals.items()}, self.revision)


@lru_cache(maxsize=1)
def writer_journal(run_dir: Path) -> Journal:
    # Bound memory when a long-lived process runs many separate experiments.
    return Journal(run_dir)


def write_record(stream, record: dict) -> None:
    stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def initialize(run_dir: Path, plan: dict) -> None:
    validate_plan(plan)
    run_dir.mkdir(parents=True, exist_ok=False)
    with (run_dir / "events.jsonl").open("x", encoding="utf-8") as stream:
        write_record(stream, {"plan": plan})


def record(run_dir: Path, node: str, state: str, detail: str = "", *, completed: int | None = None,
           usage: dict | None = None, _from_collector: bool = False) -> None:
    if (run_dir / ".collector.lock").exists() and not _from_collector:
        raise RuntimeError("Collector owns this run; send all events through its endpoint")
    # Never retry a contended/stale lock. Preserve it for inspection after a hard kill.
    lock = run_dir / ".writer.lock"
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))
    release_lock = True
    try:
        journal = writer_journal(run_dir.resolve())
        journal.sync()
        event = {"seq": journal.events + 1, "node": node, "state": state,
                 "detail": detail, "at": datetime.now(timezone.utc).isoformat()}
        if completed is not None:
            event["completed"] = completed
        if usage is not None:
            event["usage"] = usage
        try:
            journal.accept(event)
        except (ValueError, KeyError, TypeError) as error:
            raise EventRejected(str(error)) from error
        try:
            with (run_dir / "events.jsonl").open("a", encoding="utf-8") as stream:
                write_record(stream, event)
                info = os.fstat(stream.fileno())
            journal.offset = info.st_size
            journal.stamp = journal.file_stamp(info)
        except BaseException:
            journal.write_uncertain = True
            # research-fidelity: allow=RF004 reason="False retains the writer lock to prohibit continuation after uncertain persistence; the original error is re-raised."
            release_lock = False  # Persist the stop across cache eviction and process restart.
            raise
    finally:
        if release_lock:
            lock.unlink()  # Only the owned coordination lock, never scientific evidence.


class DeadlineConnection:
    """Bounded socket frames for the standard-library mutual authentication protocol."""

    def __init__(self, sock: socket.socket, deadline: float):
        self.sock = sock
        self.deadline = deadline

    def remaining(self) -> float:
        seconds = self.deadline - time.monotonic()
        if seconds <= 0:
            raise TimeoutError("Progress communication deadline exceeded; do not resend")
        return seconds

    def send_bytes(self, data: bytes) -> None:
        if len(data) > 65536:
            raise ValueError("Progress frame exceeds size limit")
        self.sock.settimeout(self.remaining())
        self.sock.sendall(struct.pack("!i", len(data)) + data)

    def _read_exact(self, size: int) -> bytes:
        data = bytearray()
        while len(data) < size:
            self.sock.settimeout(self.remaining())
            chunk = self.sock.recv(size - len(data))
            if not chunk:
                raise EOFError("Progress connection closed before a complete frame")
            data.extend(chunk)
        return bytes(data)

    def recv_bytes(self, maxlength: int = 65536) -> bytes:
        size = struct.unpack("!i", self._read_exact(4))[0]
        if not 0 <= size <= maxlength:
            raise ValueError("Progress frame exceeds size limit")
        return self._read_exact(size)


def emit(endpoint: Path, node: str, state: str, detail: str = "", *, completed: int | None = None,
         usage: dict | None = None) -> None:
    """Send one event to the serial collector. Never retry uncertain acknowledgements."""
    config = json.loads(endpoint.read_text(encoding="utf-8"))
    deadline = time.monotonic() + EVENT_TIMEOUT
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        connection = DeadlineConnection(sock, deadline)
        sock.settimeout(connection.remaining())
        sock.connect(tuple(config["address"]))
        key = bytes.fromhex(config["key"])
        answer_challenge(connection, key)
        deliver_challenge(connection, key)
        event = {"node": node, "state": state, "detail": detail, "completed": completed}
        if usage is not None:
            event["usage"] = usage
        connection.send_bytes(json.dumps(event, allow_nan=False).encode("utf-8"))
        response = json.loads(connection.recv_bytes(65536))
        if not response["ok"]:
            if response.get("rejected") is True:
                raise EventRejected(response["error"])
            raise RuntimeError(response["error"])


def collect(run_dir: Path, endpoint: Path) -> None:
    lease = run_dir / ".collector.lock"
    with lease.open("x", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))
    try:
        _serve_collector(run_dir, endpoint)
    finally:
        lease.unlink()


def _serve_collector(run_dir: Path, endpoint: Path) -> None:
    """Authenticated local IPC, one journal writer for concurrent worker processes."""
    snapshot(run_dir)
    key = secrets.token_bytes(32)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with endpoint.open("x", encoding="utf-8") as stream:
            write_record(stream, {"address": listener.getsockname(), "key": key.hex(),
                                  "run_dir": str(run_dir.resolve())})
        print("Progress collector ready", flush=True)
        while True:
            sock, _ = listener.accept()
            with sock:
                connection = DeadlineConnection(sock, time.monotonic() + EVENT_TIMEOUT)
                deliver_challenge(connection, key)
                answer_challenge(connection, key)
                try:
                    event = json.loads(connection.recv_bytes(65536))
                    fields = {"node", "state", "detail", "completed"}
                    if not isinstance(event, dict) or set(event) not in (fields, fields | {"usage"}):
                        raise ValueError("Invalid event fields")
                    record(run_dir, **event, _from_collector=True)
                    response = {"ok": True}
                except (OSError, ValueError, KeyError, TypeError) as error:
                    response = {"ok": False, "error": f"Event rejected: {type(error).__name__}",
                                "rejected": isinstance(error, EventRejected)}
                connection.send_bytes(json.dumps(response).encode("utf-8"))


@contextmanager
def stage(run_dir: str | Path, node: str, *, collector: str | Path | None = None):
    """Wrap actual work. Failure is recorded and the original exception re-raised."""
    directory = Path(run_dir) if collector is None else Path(collector)
    if collector is not None:
        config = json.loads(directory.read_text(encoding="utf-8"))
        if Path(config["run_dir"]).resolve() != Path(run_dir).resolve():
            raise ValueError("Collector belongs to a different run")
    send = record if collector is None else emit
    send(directory, node, "running")
    try:
        yield
    except BaseException as error:
        try:
            # Do not copy exception messages that could contain credentials into the UI.
            send(directory, node, "failed", type(error).__name__)
        except BaseException as recording_error:
            # Keep the original failure, including if the journal is out of disk space.
            error.add_note(f"Progress event could not be recorded: {type(recording_error).__name__}")
        raise
    else:
        try:
            send(directory, node, "succeeded")
        except EventRejected as error:
            # A definite validation rejection is not an uncertain write/acknowledgement.
            try:
                send(directory, node, "failed", type(error).__name__)
            except BaseException as recording_error:
                error.add_note(f"Failure observation could not be recorded: {type(recording_error).__name__}")
            raise


def record_usage(run_dir: str | Path, node: str, request_id: str, *, model: str, status: str,
                 source: str, evidence: str, input_tokens: int | None = None,
                 output_tokens: int | None = None, cached_input_tokens: int | None = None,
                 reasoning_output_tokens: int | None = None, collector: str | Path | None = None) -> None:
    """Append an observed cumulative usage snapshot, never inferred science or a new API call."""
    value = dict(request_id=request_id, model=model, status=status, source=source, evidence=evidence,
                 input_tokens=input_tokens, output_tokens=output_tokens,
                 cached_input_tokens=cached_input_tokens, reasoning_output_tokens=reasoning_output_tokens)
    if collector is None:
        record(Path(run_dir), node, "usage", usage=value)
    else:
        endpoint = Path(collector)
        config = json.loads(endpoint.read_text(encoding="utf-8"))
        if Path(config["run_dir"]).resolve() != Path(run_dir).resolve():
            raise ValueError("Collector belongs to a different run")
        emit(endpoint, node, "usage", usage=value)


def mermaid(state: dict) -> str:
    lines = ["flowchart TD"]
    for track in ("generation", "execution"):
        lines.append(f"  subgraph {track}")
        for node in state["nodes"]:
            if node["track"] != track:
                continue
            label = (node["label"].replace("&", "#38;").replace('"', "#34;")
                     .replace("<", "#60;").replace(">", "#62;").replace("\n", " "))
            status = node.get("display_state", node["state"])
            lines.append(f'    n_{node["id"]}["{label} · {status}"]:::{status}')
            for dep in node.get("depends_on", []):
                lines.append(f'    n_{dep} --> n_{node["id"]}')
        lines.append("  end")
    for state_name, color in {"pending": "#e5e7eb", "running": "#bfdbfe",
                              "succeeded": "#bbf7d0", "failed": "#fecaca", "blocked": "#fde68a",
                              "unknown": "#e9d5ff", "cancelled": "#cbd5e1", "skipped": "#f1f5f9"}.items():
        lines.append(f"  classDef {state_name} fill:{color},color:#111827")
    return "\n".join(lines)


PAGE = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research progress</title><style>
body{font:16px system-ui,sans-serif;background:#f5f7fa;color:#172033;margin:32px auto;padding:0 20px;max-width:1400px}
h1{font-size:26px;margin-bottom:8px}p{line-height:1.6}#tracks{display:grid;gap:24px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:16px 0}
.stat{background:#f8fafc;border:1px solid #dde3ed;border-radius:8px;padding:14px}.stat strong{display:block;font-size:23px;margin-top:6px}
#dashboard{margin-bottom:24px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:10px;text-align:left;border-bottom:1px solid #e2e8f0;overflow-wrap:anywhere}th{white-space:nowrap}.table-wrap{overflow:auto}td{max-width:260px}
section{background:white;border:1px solid #dde3ed;border-radius:12px;padding:20px;min-width:0}
.node{position:relative;border:2px solid #d3dae4;background:#f8fafc;border-radius:8px;padding:14px;overflow-wrap:anywhere;box-sizing:border-box;width:230px;flex-shrink:0}
.node.running{border-color:#2563eb;background:#eff6ff}.node.succeeded{border-color:#15803d;background:#f0fdf4}
.node.failed{border-color:#dc2626;background:#fef2f2}.node.blocked{border-color:#a16207;background:#fefce8}
.node.unknown{border-color:#7e22ce;background:#faf5ff}.node.cancelled,.node.skipped{border-style:dashed}
.level{display:flex;gap:24px;justify-content:center;margin:40px 0}.viewport{overflow:auto}.halted{color:#b91c1c}
.meta{font-size:13px;color:#475569;margin-top:8px}#health{padding:12px;background:#e2e8f0}
details{margin-top:10px;font-size:13px}summary{cursor:pointer}details p{white-space:pre-wrap}
.diagram{position:relative;min-width:100%;width:max-content;padding:0 12px}.diagram svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
@media(max-width:700px){#tracks{grid-template-columns:1fr}body{margin:18px auto}section{padding:12px}.node{width:125px;padding:10px}.level{gap:16px}}
</style><h1 id="title">科研工作流</h1>
<p>蓝色：运行中 · 绿色：完成 · 红色：失败 · 黄色：阻塞 · 紫色：状态未知 · 虚线：取消/条件未执行<br>
代码生成完成不代表实验已运行。节点展示最近一次真实事件；长阶段仅在边界更新。<br>
需求编号对应项目 idea.md；展开节点查看科研规则。颜色不代表已通过语义审阅。</p>
<p id="health" role="status">正在读取事件…</p><section id="dashboard"></section><main id="tracks"></main>
<script>
const labels={generation:'代码生成进度',execution:'实验执行进度'};
const statuses={pending:'未开始',running:'运行中（最近事件）',succeeded:'完成',failed:'失败',blocked:'阻塞',unknown:'状态未知',cancelled:'已确认取消',skipped:'条件未执行'};
const el=(tag,text,cls)=>{const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;return e};
let last='';
const expanded=new Set();
const number=value=>value===null?'未知':value.toLocaleString();
const sources={reported:'服务端报告',estimated:'本地估算',unknown:'未知'};
function drawDashboard(data){
 const panel=document.getElementById('dashboard');panel.replaceChildren(el('h2','运行与 Token 监控'));
 const active=data.nodes.filter(n=>(n.display_state||n.state)==='running');
 panel.append(el('p','当前阶段：'+(active.length?active.map(n=>n.label).join('；'):'当前没有已确认运行的节点')));
 const requests=data.requests,stats=el('div','','stats');panel.append(stats);
 for(const source of ['reported','estimated']){
  const usage=data.usage[source];
  for(const [field,label] of [['input_tokens','输入 Token'],['output_tokens','输出 Token']]){
   const card=el('div','','stat');card.append(el('span',sources[source]+' · '+label));
   card.append(el('strong',usage.requests?number(usage[field]):'—'));
   card.append(el('div',usage.requests+' 个请求'+(usage[field+'_unknown']?'；其中 '+usage[field+'_unknown']+' 个用量未知':''),'meta'));stats.append(card);
  }
 }
 const unresolved=requests.filter(r=>r.input_tokens===null||r.output_tokens===null).length;
 const running=requests.filter(r=>(r.display_status||r.status)==='running').length;
 panel.append(el('p',requests.length?'已接入 '+requests.length+' 个请求；运行中 '+running+' 个；用量不完整 '+unresolved+' 个。':'未接入 LLM 用量记录，不能视为消耗为零。'));
 panel.append(el('p','仅统计已接入的科研程序请求，不包含 Codex 对话用量。已报告与估算分开显示；未知不计为零。缓存输入和推理输出是子项，不重复相加。','meta'));
 if(!requests.length)return;
 const wrapper=el('div','','table-wrap'),table=el('table',''),head=el('tr','');
 for(const label of ['请求 / 模型','阶段','状态 / 来源','输入 / 输出','缓存输入 / 推理输出','依据'])head.append(el('th',label));
 const thead=el('thead','');thead.append(head);table.append(thead);const body=el('tbody','');
 for(const request of requests.slice(-50).reverse()){
  const row=el('tr','');
  for(const value of [request.request_id+' / '+request.model,request.node,
    statuses[request.display_status||request.status]+' / '+sources[request.source],
    number(request.input_tokens)+' / '+number(request.output_tokens),
    number(request.cached_input_tokens)+' / '+number(request.reasoning_output_tokens),request.evidence])row.append(el('td',value));
  body.append(row);
 }
 table.append(body);wrapper.append(table);panel.append(wrapper,el('p','显示最近登记的 '+Math.min(50,requests.length)+' 个请求；完整历史保留在事件日志。','meta'));
}
function draw(data){
 document.getElementById('title').textContent=data.title;
 drawDashboard(data);
 const root=document.getElementById('tracks');root.replaceChildren();
 for(const track of ['generation','execution']){
  const section=el('section','');section.append(el('h2',labels[track]));root.append(section);
  const halted=data.tracks[track]==='stopped';
  section.append(el('p',halted?'已停止新任务：保留在途任务真实状态，本轨道禁止提交正式结果。':'状态由实际事件驱动；并列节点表示同一依赖层级。',halted?'halted':''));
  const viewport=el('div','','viewport');section.append(viewport);
  const diagram=el('div','','diagram');viewport.append(diagram);const boxes=new Map(),levels=new Map(),ranks=new Map();
  for(const n of data.nodes.filter(n=>n.track===track)){
   const rank=Math.max(-1,...(n.depends_on||[]).map(id=>ranks.get(id)))+1;ranks.set(n.id,rank);
   if(!levels.has(rank))levels.set(rank,el('div','','level'));
   const status=n.display_state||n.state;
   const box=el('div','','node '+status);box.append(el('strong',n.label));
   box.append(el('div',n.id+' · '+statuses[status],'meta'));
   if(n.termination_status==='unknown')box.append(el('div','进程终止未确认；原始阶段状态：'+statuses[n.state],'meta'));
   const calls=data.requests.filter(r=>r.node===n.id);if(calls.length)box.append(el('div','已接入 LLM 请求：'+calls.length,'meta'));
   if(n.idea_refs)box.append(el('div','idea.md · '+n.idea_refs.join(', '),'meta'));
   if(n.description){
    const details=el('details','');details.open=expanded.has(n.id);
    details.append(el('summary','查看节点说明'),el('p',n.description));box.append(details);
    details.addEventListener('toggle',()=>{if(details.open)expanded.add(n.id);else expanded.delete(n.id);drawEdges();});
   }
   if(n.total!==undefined)box.append(el('div',n.completed+' / '+n.total+'（预定总量）','meta'));
   if(n.condition)box.append(el('div','条件：'+n.condition,'meta'));
   if(n.detail)box.append(el('div',n.detail,'meta'));
   if(n.updated_at)box.append(el('div',n.updated_at,'meta'));
   levels.get(rank).append(box);boxes.set(n.id,box);
  }
  for(const rank of [...levels.keys()].sort((a,b)=>a-b))diagram.append(levels.get(rank));
  if(!boxes.size)diagram.append(el('p','未规划该类执行；不推断为已完成。'));
  const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');
  function drawEdges(){
  svg.replaceChildren();
  for(const n of data.nodes.filter(n=>n.track===track))for(const dep of n.depends_on||[]){
   const a=boxes.get(dep),b=boxes.get(n.id),rect=diagram.getBoundingClientRect();
   const ar=a.getBoundingClientRect(),br=b.getBoundingClientRect();
   const y1=ar.bottom-rect.top,y2=br.top-rect.top,x1=ar.left+ar.width/2-rect.left,x2=br.left+br.width/2-rect.left,mid=(y1+y2)/2;
   const path=document.createElementNS(ns,'path');
   path.setAttribute('d',`M ${x1} ${y1} C ${x1} ${mid},${x2} ${mid},${x2} ${y2} M ${x2-4} ${y2-6} L ${x2} ${y2} L ${x2+4} ${y2-6}`);
   path.setAttribute('fill','none');path.setAttribute('stroke','#64748b');svg.append(path);
  }
  }
  diagram.prepend(svg);drawEdges();
 }
}
async function poll(){
 try{
  const response=await fetch('/status',{cache:'no-store'});if(!response.ok)throw new Error('事件日志不可读');
  const status=await response.json();
  if(status.version!==last){
   const full=await fetch('/state',{cache:'no-store'});if(!full.ok)throw new Error('事件日志不可读');
   const data=await full.json();draw(data);last=data.version;
  }
  const monitor={events_only:'事件观察模式',running:'运行器在线',unknown:'运行器心跳过期，状态未知',stopped:'运行器已停止',finished:'命令运行凭据已提交',awaiting_publication:'准备完成，运行凭据尚未提交'};
  document.getElementById('health').textContent=(monitor[status.observation]||'观察状态未知')+' · '+status.run_id+' · '+status.events+' 个事件 · 检查时间 '+new Date().toLocaleTimeString()+'；面板在阶段变化或显式进度更新时刷新';
 }catch(error){document.getElementById('health').textContent='状态未知 / 连接中断：'+error.message+'。保留最后事件，不推断成功。';}
 setTimeout(poll,1000);
}
window.addEventListener('resize',()=>{last=-1});poll();
</script></html>'''


# Translate interface text only. Scientific labels, evidence and events stay verbatim.
ENGLISH_TEXT = {
    '科研工作流': 'Research workflow',
    '蓝色：运行中': 'Blue: running', '绿色：完成': 'Green: complete',
    '红色：失败': 'Red: failed', '黄色：阻塞': 'Yellow: blocked',
    '紫色：状态未知': 'Purple: unknown', '虚线：取消/条件未执行': 'Dashed: cancelled/skipped',
    '代码生成完成不代表实验已运行。节点展示最近一次真实事件；长阶段仅在边界更新。':
        'Generated code does not imply an executed experiment. Nodes show the latest recorded event; long stages update at boundaries.',
    '需求编号对应项目 idea.md；展开节点查看科研规则。颜色不代表已通过语义审阅。':
        'Requirement IDs refer to the project idea.md. Expand nodes for details. Colors do not certify scientific fidelity.',
    '正在读取事件…': 'Reading events…',
    '代码生成进度': 'Code generation', '实验执行进度': 'Experiment execution',
    '未开始': 'Pending', '运行中（最近事件）': 'Running (last event)',
    '完成': 'Complete', '失败': 'Failed', '阻塞': 'Blocked', '状态未知': 'Unknown state',
    '已确认取消': 'Cancellation confirmed', '条件未执行': 'Conditionally skipped', '未知': 'Unknown',
    '服务端报告': 'Reported', '本地估算': 'Estimated',
    '运行与 Token 监控': 'Workflow and Token usage',
    '当前阶段：': 'Active stages: ', '当前没有已确认运行的节点': 'No confirmed running stages',
    '输入 Token': 'Input Tokens', '输出 Token': 'Output Tokens',
    ' 个请求': ' requests', '；其中 ': '; ', ' 个用量未知': ' with unknown usage',
    '已接入 ': 'Instrumented: ', ' 个请求；运行中 ': ' requests; running: ',
    ' 个；用量不完整 ': '; incomplete usage: ', ' 个。': '.',
    '未接入 LLM 用量记录，不能视为消耗为零。': 'LLM usage is not connected; this does not mean zero consumption.',
    '仅统计已接入的科研程序请求，不包含 Codex 对话用量。已报告与估算分开显示；未知不计为零。缓存输入和推理输出是子项，不重复相加。':
        'Only instrumented research requests are counted, not Codex conversation usage. Reported and estimated counts stay separate. Unknown is not zero. Cached input and reasoning output are inclusive subcounts.',
    '请求 / 模型': 'Request / model', '阶段': 'Stage', '状态 / 来源': 'Status / source',
    '输入 / 输出': 'Input / output', '缓存输入 / 推理输出': 'Cached / reasoning', '依据': 'Evidence',
    '显示最近登记的 ': 'Showing the latest ',
    ' 个请求；完整历史保留在事件日志。': ' registered requests; the complete history remains in the journal.',
    '已停止新任务：保留在途任务真实状态，本轨道禁止提交正式结果。':
        'New work stopped. In-flight outcomes are retained; this track cannot publish scientific results.',
    '状态由实际事件驱动；并列节点表示同一依赖层级。':
        'States follow recorded events. Adjacent nodes share a dependency level.',
    '进程终止未确认；原始阶段状态：': 'Termination unconfirmed; original stage state: ',
    '已接入 LLM 请求：': 'Instrumented LLM requests: ', '查看节点说明': 'Show node details',
    '（预定总量）': ' (declared total)', '条件：': 'Condition: ',
    '未规划该类执行；不推断为已完成。': 'No stages planned for this track; completion is not inferred.',
    '事件日志不可读': 'Journal unavailable', '事件观察模式': 'Event observation',
    '运行器在线': 'Supervisor online', '运行器心跳过期，状态未知': 'Supervisor heartbeat stale; state unknown',
    '运行器已停止': 'Supervisor stopped', '命令运行凭据已提交': 'Command execution evidence committed',
    '准备完成，运行凭据尚未提交': 'Preparation complete; execution evidence not committed',
    '观察状态未知': 'Observation unknown', ' 个事件 · 检查时间 ': ' events · Checked at ',
    '；面板在阶段变化或显式进度更新时刷新': '; panel updates at stage or progress boundaries',
    '状态未知 / 连接中断：': 'Unknown state / disconnected: ',
    '。保留最后事件，不推断成功。': '. Last events retained; success is not inferred.',
    '；': '; ',
}


def viewer_page(language: str) -> str:
    if language == 'zh-CN':
        return PAGE
    if language != 'en':
        raise ValueError('Viewer language must be en or zh-CN')
    pattern = '|'.join(re.escape(key) for key in sorted(ENGLISH_TEXT, key=len, reverse=True))
    page = re.sub(pattern, lambda match: ENGLISH_TEXT[match.group()], PAGE)
    page = page.replace("usage.requests+' requests'", "usage.requests+(usage.requests===1?' request':' requests')")
    return page.replace('lang="zh-CN"', 'lang="en"')


def serve(run_dir: Path, port: int, language: str = 'zh-CN') -> None:
    page = viewer_page(language)
    journal = Journal(run_dir)
    journal.sync()  # Refuse to advertise an unreadable run.

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in {"/", "/state", "/status"}:
                self.send_error(404)
                return
            try:
                if self.path == "/":
                    content = page
                else:
                    journal.sync()
                    state = journal.view(include_requests=self.path == "/state")
                    if self.path == "/status":
                        state = {key: state[key] for key in ("version", "events", "observation", "run_id")}
                    content = json.dumps(state, ensure_ascii=False)
            except (OSError, ValueError, KeyError, IndexError, TypeError):
                self.send_error(503, "Progress journal unavailable")
                # research-fidelity: allow=RF009 reason="Read-only viewer sends explicit HTTP 503; no scientific value or success is produced."
                return
            body = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8" if self.path == "/" else "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            return  # Polling is display-only; the journal is the event evidence.

    with HTTPServer(("127.0.0.1", port), Handler) as server:
        print(f"http://127.0.0.1:{server.server_port}", flush=True)
        server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "event", "show", "serve", "collect"):
        command = sub.add_parser(name)
        command.add_argument("run_dir", type=Path)
        if name == "init":
            command.add_argument("--plan", type=Path, required=True)
        elif name == "event":
            command.add_argument("node")
            command.add_argument("state", choices=sorted((STATES - {"pending"}) | {"update"}))
            command.add_argument("--detail", default="")
            command.add_argument("--completed", type=int)
            command.add_argument("--collector", type=Path)
        elif name == "show":
            command.add_argument("--mermaid", action="store_true")
        elif name == "collect":
            command.add_argument("--endpoint", type=Path, required=True)
        else:
            command.add_argument("--port", type=int, default=0)
            command.add_argument("--lang", choices=("en", "zh-CN"), default="zh-CN")
    args = parser.parse_args()
    if args.command == "init":
        initialize(args.run_dir, json.loads(args.plan.read_text(encoding="utf-8")))
    elif args.command == "event":
        if args.collector is None:
            record(args.run_dir, args.node, args.state, args.detail, completed=args.completed)
        else:
            config = json.loads(args.collector.read_text(encoding="utf-8"))
            if Path(config["run_dir"]).resolve() != args.run_dir.resolve():
                raise ValueError("Collector belongs to a different run")
            emit(args.collector, args.node, args.state, args.detail, completed=args.completed)
    elif args.command == "show":
        state = snapshot(args.run_dir)
        print(mermaid(state) if args.mermaid else json.dumps(state, ensure_ascii=False, indent=2))
    elif args.command == "collect":
        collect(args.run_dir, args.endpoint)
    else:
        serve(args.run_dir, args.port, args.lang)


if __name__ == "__main__":
    main()
