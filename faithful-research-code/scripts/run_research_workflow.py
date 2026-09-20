#!/usr/bin/env python3
"""Run an explicit local command DAG once; failed work never gets a completion manifest."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from research_progress import initialize, record, snapshot, validate_plan, write_record


def validate_execution(plan: dict) -> None:
    validate_plan(plan)
    if plan.get("process_scope") != "direct_children_only":
        raise ValueError("Declare direct_children_only: detached/nested worker processes are unsupported")
    workers = plan["max_parallel"]
    if type(workers) is not int or workers < 1:
        raise ValueError("max_parallel must be a positive integer")
    if workers > 1 and not plan.get("parallelism_source"):
        raise ValueError("Concurrent execution needs a predeclared scientific source/protocol")
    checks = plan["required_checks"]
    ids = {node["id"] for node in plan["nodes"]}
    if not isinstance(checks, list) or any(check not in ids for check in checks):
        raise ValueError("required_checks must identify declared check nodes")
    if not checks and not plan.get("no_runtime_checks_reason"):
        raise ValueError("Declare required runtime checks, or justify why none apply")
    for node in plan["nodes"]:
        if node["track"] != "execution" or "condition" in node or "total" in node:
            raise ValueError("Runner supports unconditional command nodes on the execution track")
        argv = node["argv"]
        if not isinstance(argv, list) or not argv or any(not isinstance(arg, str) or not arg for arg in argv):
            raise ValueError("argv must be a nonempty string array; no shell command strings")
        timeout = node["timeout_seconds"]
        if type(timeout) not in {int, float} or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Each command requires a finite positive timeout")


def atomic_json(path: Path, value: dict) -> None:
    pending = path.with_suffix(path.suffix + ".pending")
    with pending.open("w", encoding="utf-8") as stream:
        write_record(stream, value)
    pending.replace(path)


def terminate_owned(process: subprocess.Popen) -> None:
    """Use the owned child handle directly; never enumerate or target unrelated PIDs."""
    process.kill()
    process.wait(timeout=10)


def run(plan: dict, run_dir: Path, cwd: Path) -> None:
    validate_execution(plan)
    cwd = cwd.resolve(strict=True)
    run_dir = run_dir.resolve()
    initialize(run_dir, plan)
    active = {}
    completed = set()
    outcomes = {}
    nodes = {node["id"]: node for node in plan["nodes"]}
    health = {"pid": os.getpid(), "state": "running", "stale_after_seconds": 5,
              "termination_unknown": []}

    def heartbeat(state="running"):
        health.update(state=state, last_seen=datetime.now(timezone.utc).isoformat())
        atomic_json(run_dir / "supervisor.json", health)

    try:
        heartbeat()
        next_heartbeat = time.monotonic() + 1
        while len(completed) < len(nodes):
            # Reap all known failures before dispatching any new work.
            for identifier, (process, started, log) in list(active.items()):
                code = process.poll()
                if code is None and time.monotonic() - started < nodes[identifier]["timeout_seconds"]:
                    continue
                if code is None:
                    record(run_dir, identifier, "failed", "Declared command timeout exceeded")
                    raise TimeoutError(f"Stage {identifier} exceeded its declared timeout")
                log.close()
                del active[identifier]
                outcomes[identifier] = {"returncode": code, "pid": process.pid}
                if code != 0:
                    record(run_dir, identifier, "failed", f"Command exited {code}; see stage.log")
                    raise subprocess.CalledProcessError(code, nodes[identifier]["argv"])
                record(run_dir, identifier, "succeeded", "Command exited 0; runtime assertions are in stage.log")
                completed.add(identifier)
            for identifier, node in nodes.items():
                if len(active) >= plan["max_parallel"]:
                    break
                if identifier in completed or identifier in active or not set(node.get("depends_on", [])) <= completed:
                    continue
                record(run_dir, identifier, "running")
                directory = run_dir / identifier
                directory.mkdir()
                argv = [sys.executable if arg == "{python}" else arg for arg in node["argv"]]
                environment = dict(os.environ, RESEARCH_RUN_DIR=str(run_dir), RESEARCH_NODE_DIR=str(directory))
                log = (directory / "stage.log").open("xb")
                try:
                    process = subprocess.Popen(argv, cwd=cwd, env=environment, stdout=log, stderr=subprocess.STDOUT,
                                               start_new_session=os.name != "nt")
                except BaseException:
                    log.close()
                    record(run_dir, identifier, "failed", "Process could not be started")
                    raise
                active[identifier] = (process, time.monotonic(), log)
            if not active and len(completed) != len(nodes):
                raise RuntimeError("No runnable stage; dependency contract is incomplete")
            if time.monotonic() >= next_heartbeat:
                heartbeat()
                next_heartbeat = time.monotonic() + 1
            if active:
                time.sleep(0.05)
        if not set(plan["required_checks"]) <= completed:
            raise RuntimeError("Required runtime evidence is missing")
        if snapshot(run_dir)["tracks"]["execution"] != "complete":
            raise RuntimeError("Execution was stopped; publication is forbidden")
        logs = {identifier: hashlib.sha256((run_dir / identifier / "stage.log").read_bytes()).hexdigest()
                for identifier in nodes}
        heartbeat("finished")
        # The last fallible action publishes command-execution evidence, not a scientific conclusion.
        atomic_json(run_dir / "RUN_COMPLETE.json", {
            "status": "COMMANDS_VERIFIED", "claim": "Only the declared commands/checks ran successfully",
            "plan_sha256": hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest(),
            "required_checks": plan["required_checks"], "outcomes": outcomes, "log_sha256": logs,
        })
    except BaseException as original:
        for identifier, (process, _, log) in list(active.items()):
            # research-fidelity: allow=RF004 reason="False means process exit is unconfirmed; original failure is re-raised and publication remains forbidden."
            exit_confirmed = False
            try:
                exit_code = process.poll()
                if exit_code is None:
                    terminate_owned(process)
                    state, detail = "cancelled", "Owned direct child terminated; exit confirmed"
                else:
                    state = "succeeded" if exit_code == 0 else "failed"
                    detail = f"In-flight process independently exited {exit_code}"
                exit_confirmed = True
                current = {n["id"]: n["state"] for n in snapshot(run_dir)["nodes"]}
                if current[identifier] == "running":
                    record(run_dir, identifier, state, detail)
            except BaseException as cleanup_error:
                original.add_note(f"Cancellation/evidence uncertain for {identifier}: {type(cleanup_error).__name__}")
                if not exit_confirmed:
                    health["termination_unknown"].append(identifier)
                try:
                    if next(n for n in snapshot(run_dir)["nodes"] if n["id"] == identifier)["state"] == "running":
                        record(run_dir, identifier, "unknown", "Could not confirm process termination")
                except BaseException as observation_error:
                    original.add_note(f"Unknown-state write failed: {type(observation_error).__name__}")
            finally:
                log.close()
        try:
            heartbeat("stopped")
            atomic_json(run_dir / "RUN_FAILED.json", {"error_type": type(original).__name__,
                                                      "termination_unknown": health["termination_unknown"],
                                                      "notes": getattr(original, "__notes__", [])})
        except BaseException as recording_error:
            original.add_note(f"Failure evidence write failed: {type(recording_error).__name__}")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    args = parser.parse_args()
    run(json.loads(args.plan.read_text(encoding="utf-8")), args.run_dir, args.cwd)


if __name__ == "__main__":
    main()
