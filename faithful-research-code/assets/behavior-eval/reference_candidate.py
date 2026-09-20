"""Local SNIS fixture evaluator: Python standard library only."""
import argparse
import hashlib
import json
import math
import platform
import random
import traceback
from pathlib import Path
from research_progress import initialize, stage


class DomainError(ValueError):
    pass


class MockHTTPError(RuntimeError):
    pass


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def finite_number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise DomainError(f"{name} must be a finite number")


def validate_rows(rows):
    if not rows:
        raise DomainError("SNIS needs at least one scheduled row")
    ids = []
    for row in rows:
        if set(row) != {"id", "weight"} or not isinstance(row["id"], str):
            raise DomainError("Each row requires exactly string id and weight")
        ids.append(row["id"])
        finite_number(row["weight"], "weight")
        if row["weight"] < 0:
            raise DomainError("SNIS weights must be nonnegative")
    if len(set(ids)) != len(ids):
        raise DomainError("Row identities must be unique")
    denominator = sum(row["weight"] for row in rows)
    if not math.isfinite(denominator) or denominator <= 0:
        raise DomainError("SNIS weight sum must be positive and finite")


def snis(rows, rewards):
    validate_rows(rows)
    if len(rewards) != len(rows) or set(rewards) != {r["id"] for r in rows}:
        raise DomainError("Every scheduled row needs exactly one reward")
    for value in rewards.values():
        finite_number(value, "reward")
    numerator = sum(row["weight"] * rewards[row["id"]] for row in rows)
    denominator = sum(row["weight"] for row in rows)
    value = numerator / denominator
    if not math.isfinite(numerator) or not math.isfinite(value):
        raise DomainError("SNIS numerator and result must be finite")
    return {"value": value, "numerator": numerator, "denominator": denominator,
            "n_scheduled": len(rows), "n_observed": len(rewards)}


def stream_rng(root, *identity):
    key = json.dumps([root, *identity], separators=(",", ":"))
    return random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest(), "big"))


def bootstrap_indices(root, branch, replicate, n):
    # Diagnostic resampling only: no source-defined bootstrap interval was supplied.
    rng = stream_rng(root, "bootstrap", branch, replicate)
    return [rng.randrange(n) for _ in range(n)]


def mock_generate(row_id, position, reward_table, failure, draw, evidence):
    request = {"sample_id": row_id, "position": position, "attempt": 1,
               "model": "local-fixture-v1", "generation_draw": draw}
    with (evidence / "attempts.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(request, allow_nan=False) + "\n")
    if position == 2 and failure in ("429", "500", "timeout"):
        write_json(evidence / f"raw-{position}.json", {"error": failure, "request": request})
        if failure == "timeout":
            raise TimeoutError("Local mock timeout at required sample two")
        raise MockHTTPError(f"HTTP {failure}: local mock failed at required sample two")
    if position == 2 and failure == "malformed":
        raw = {"wrong_field": "unparseable reward"}
    else:
        raw = {"sample_id": row_id, "reward": reward_table[row_id]}
    write_json(evidence / f"raw-{position}.json", raw)
    if set(raw) != {"sample_id", "reward"} or raw["sample_id"] != row_id:
        raise DomainError("Required reward response schema/identity violated")
    finite_number(raw["reward"], "generated reward")
    return raw["reward"]


def run(rows, config, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    evidence = out / "failed-run"
    evidence.mkdir()
    plan = {"title": "SNIS execution", "nodes": [
        {"id": "validate", "track": "execution", "label": "Validate fixed rows and explicit config"},
        {"id": "generate", "track": "execution", "label": "One serial call per row; failure stops", "depends_on": ["validate"]},
        {"id": "estimate", "track": "execution", "label": "Require complete rewards; SNIS; bootstrap diagnostics", "depends_on": ["generate"]},
        {"id": "commit", "track": "execution", "label": "Prepare validated atomic report commit", "depends_on": ["estimate"]}]}
    initialize(out / "progress", plan)
    try:
        write_json(evidence / "rows.json", rows)
        write_json(evidence / "config.json", config)
        write_json(evidence / "environment.json", {"python": platform.python_version(), "precision": "Python float binary64", "transport": "local-fixture-v1", "retries": 0})
        with stage(out / "progress", "validate"):
            validate_rows(rows)
            if set(config) != {"root_seed", "branch", "bootstrap_replicates", "failure", "rewards"}:
                raise DomainError("All config choices must be explicit; no defaults")
            if type(config["root_seed"]) is not int or type(config["bootstrap_replicates"]) is not int or config["bootstrap_replicates"] < 0:
                raise DomainError("Integer root seed and nonnegative replicate count required")
            if config["branch"] not in ("baseline", "ablation") or config["failure"] not in ("none", "429", "500", "timeout", "malformed"):
                raise DomainError("Unsupported branch or local failure fixture")
            if set(config["rewards"]) != {r["id"] for r in rows}:
                raise DomainError("Mock reward table must cover every scheduled row")
        with stage(out / "progress", "generate"):
            rewards = {}
            draws = {}
            for position, row in enumerate(rows, 1):
                draw = stream_rng(config["root_seed"], "generation", row["id"]).random()
                draws[row["id"]] = draw
                rewards[row["id"]] = mock_generate(row["id"], position, config["rewards"], config["failure"], draw, evidence)
        with stage(out / "progress", "estimate"):
            result = snis(rows, rewards)
            result["generation_draws"] = draws
            result["bootstrap_indices"] = [bootstrap_indices(config["root_seed"], config["branch"], k, len(rows)) for k in range(config["bootstrap_replicates"])]
            result["status"] = "COMPLETE_LOCAL_FIXTURE"
        with stage(out / "progress", "commit"):
            evidence.rename(out / "evidence")
            evidence = out / "evidence"
            write_json(out / "report.pending.json", result)
        (out / "report.pending.json").replace(out / "report.json")
        return result
    except Exception as original:
        # research-fidelity: allow=RF009 reason="Preserve traceback and re-raise original failure; no recovery or partial metric."
        try:
            if evidence.name != "failed-run":
                evidence.rename(out / "failed-run")
                evidence = out / "failed-run"
            (evidence / "traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
        except OSError as logging_error:
            original.add_note(f"Failure evidence write failed: {logging_error}")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    run(json.loads(args.rows.read_text(encoding="utf-8-sig")), json.loads(args.config.read_text(encoding="utf-8-sig")), args.out)
