#!/usr/bin/env python3
"""Report Python constructs that may silently change research semantics.

This is a triage tool, not a proof or policy engine. A finding is not
automatically a bug; review it against the scientific contract. The analyzer is
intentionally Python-specific and cannot detect every semantic divergence.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator


RANK = {"high": 3, "medium": 2, "low": 1}
SUPPRESSION_RE = re.compile(
    r"#\s*research-fidelity:\s*allow=(RF\d{3})\s+reason=(.+?)\s*$"
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    column: int
    severity: str
    rule: str
    category: str
    detail: str
    evidence: str
    suppressed: bool = False
    suppression_reason: str | None = None


def is_empty_default(node: ast.AST | None) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Constant):
        return node.value in (None, False, 0, 0.0, "", b"")
    if isinstance(node, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
        return not getattr(node, "elts", None) and not getattr(node, "keys", None)
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"dict", "list", "set", "tuple"}
        and not node.args
        and not node.keywords
    )


def dotted_name(node: ast.AST | None) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def literal_bool(node: ast.AST | None) -> bool | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return node.value
    return None


def keyword(call: ast.Call, name: str) -> ast.AST | None:
    for item in call.keywords:
        if item.arg == name:
            return item.value
    return None


def exception_names(node: ast.AST | None) -> set[str]:
    if node is None:
        return {"bare"}
    if isinstance(node, ast.Tuple):
        return {dotted_name(item).split(".")[-1] for item in node.elts}
    return {dotted_name(node).split(".")[-1]}


def is_broad_handler(handler: ast.ExceptHandler) -> bool:
    return bool(exception_names(handler.type) & {"bare", "Exception", "BaseException"})


def handler_nodes(statements: list[ast.stmt]) -> Iterator[ast.AST]:
    """Walk handler statements without entering nested definitions."""

    stack: list[ast.AST] = list(reversed(statements))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(node))))


CAPABILITY_PROBES = {
    "is_available",
    "is_bf16_supported",
    "is_fp16_supported",
    "is_mps_available",
    "is_torch_bf16_available",
    "is_torch_fp16_available",
    "is_torch_mps_available",
    "is_torch_xpu_available",
}


def contains_capability_probe(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.Call)
        and dotted_name(child.func).split(".")[-1] in CAPABILITY_PROBES
        for child in ast.walk(node)
    )


def assigned_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = child.targets if isinstance(child, ast.Assign) else [child.target]
            for target in targets:
                for nested in ast.walk(target):
                    if isinstance(nested, ast.Name):
                        names.add(nested.id.lower())
                    elif isinstance(nested, ast.Attribute):
                        names.add(nested.attr.lower())
    return names


def contains_string(node: ast.AST, fragment: str) -> bool:
    fragment = fragment.lower()
    return any(
        isinstance(child, ast.Constant)
        and isinstance(child.value, str)
        and fragment in child.value.lower()
        for child in ast.walk(node)
    )


class Auditor(ast.NodeVisitor):
    def __init__(self, path: Path, source: str) -> None:
        self.path = path
        self.lines = source.splitlines()
        self.findings: list[Finding] = []

    def suppression_for(self, rule: str, line: int) -> str | None:
        for candidate in (line, line - 1):
            if candidate < 1 or candidate > len(self.lines):
                continue
            match = SUPPRESSION_RE.search(self.lines[candidate - 1])
            if not match or match.group(1) != rule:
                continue
            reason = match.group(2).strip()
            if len(reason) >= 2 and reason[0] == reason[-1] and reason[0] in {'"', "'"}:
                reason = reason[1:-1].strip()
            if len(reason) >= 8:
                return reason
        return None

    def add(
        self,
        node: ast.AST,
        severity: str,
        rule: str,
        category: str,
        detail: str,
        evidence: str,
    ) -> None:
        line = int(getattr(node, "lineno", 1))
        reason = self.suppression_for(rule, line)
        self.findings.append(
            Finding(
                path=str(self.path),
                line=line,
                column=int(getattr(node, "col_offset", 0)) + 1,
                severity=severity,
                rule=rule,
                category=category,
                detail=detail,
                evidence=evidence,
                suppressed=reason is not None,
                suppression_reason=reason,
            )
        )

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        broad = is_broad_handler(node)
        parsing_errors = {
            "JSONDecodeError",
            "ParserError",
            "UnicodeDecodeError",
            "ValueError",
        }
        for child in handler_nodes(node.body):
            if isinstance(child, ast.Pass) and broad:
                self.add(
                    child,
                    "high",
                    "RF001",
                    "control-flow",
                    "Broad exception is silently passed.",
                    "The handler can hide a failed scientific operation.",
                )
            elif isinstance(child, (ast.Continue, ast.Break)) and broad:
                self.add(
                    child,
                    "high",
                    "RF002",
                    "data-selection",
                    "Broad exception skips remaining work.",
                    "A failed sample, task, or trial may disappear from coverage.",
                )
            elif isinstance(child, ast.Return) and broad and is_empty_default(child.value):
                self.add(
                    child,
                    "high",
                    "RF003",
                    "default-substitution",
                    "Broad exception returns a benign or empty default.",
                    "Failure can become a usable scientific value.",
                )
            elif isinstance(child, ast.Return) and broad:
                self.add(
                    child,
                    "medium",
                    "RF007",
                    "alternate-result",
                    "Broad exception returns an alternate result.",
                    "Verify that the returned path is source-defined and provenance-preserving.",
                )
            elif isinstance(child, (ast.Assign, ast.AnnAssign)) and broad:
                if is_empty_default(child.value):
                    self.add(
                        child,
                        "medium",
                        "RF004",
                        "default-substitution",
                        "Broad exception assigns a benign or empty default.",
                        "The default may later enter training, evaluation, or reporting.",
                    )

            if (
                isinstance(child, (ast.Continue, ast.Break))
                and not broad
                and exception_names(node.type) & parsing_errors
            ):
                self.add(
                    child,
                    "medium",
                    "RF008",
                    "parsing-repair",
                    "Parse-related exception skips remaining work.",
                    "Malformed samples may disappear from coverage even when the exception is narrow.",
                )

        if exception_names(node.type) & {"ImportError", "ModuleNotFoundError"}:
            if any(
                isinstance(child, (ast.Import, ast.ImportFrom))
                for child in handler_nodes(node.body)
            ):
                self.add(
                    node,
                    "high",
                    "RF005",
                    "compatibility",
                    "Missing dependency selects an alternate import or backend.",
                    "The alternate implementation may have different scientific semantics.",
                )

        if contains_string(node, "out of memory"):
            changed = assigned_names(node)
            semantic_names = {
                name
                for name in changed
                if any(
                    token in name
                    for token in (
                        "batch",
                        "microbatch",
                        "precision",
                        "dtype",
                        "accumulation",
                        "sequence_length",
                        "max_length",
                    )
                )
            }
            if semantic_names:
                self.add(
                    node,
                    "high",
                    "RF403",
                    "resource-fallback",
                    "Out-of-memory handling changes experiment parameters.",
                    "Automatic resource recovery mutates claim-relevant settings: "
                    + ", ".join(sorted(semantic_names)),
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = dotted_name(node.func)
        leaf = name.split(".")[-1]

        if leaf == "getattr" and len(node.args) >= 3:
            self.add(
                node,
                "low",
                "RF101",
                "default-substitution",
                "getattr supplies a default.",
                "A missing method-defined field may be masked.",
            )
        if leaf == "get" and len(node.args) >= 2 and is_empty_default(node.args[1]):
            self.add(
                node,
                "low",
                "RF102",
                "default-substitution",
                "Mapping lookup supplies an empty default.",
                "Verify that the field is optional in the scientific contract.",
            )
        if name == "contextlib.suppress":
            names = {dotted_name(arg).split(".")[-1] for arg in node.args}
            if names & {"Exception", "BaseException"}:
                self.add(
                    node,
                    "high",
                    "RF006",
                    "control-flow",
                    "contextlib suppresses a broad exception.",
                    "A failed operation may be treated as successful.",
                )

        if leaf in {"dropna", "drop_nulls", "drop_missing"}:
            self.add(
                node,
                "medium",
                "RF201",
                "data-selection",
                f"{leaf} removes observations with missing values.",
                "Sample membership and aggregation denominators may change.",
            )
        if leaf in {"fillna", "interpolate", "nan_to_num"}:
            self.add(
                node,
                "medium",
                "RF202",
                "data-imputation",
                f"{leaf} replaces or constructs values.",
                "Imputation can change the data distribution or numerical result.",
            )
        errors = literal_string(keyword(node, "errors"))
        if errors in {"ignore", "coerce", "replace"}:
            self.add(
                node,
                "medium",
                "RF203",
                "parsing-repair",
                f"errors={errors!r} suppresses or coerces parse failures.",
                "Malformed scientific inputs may be altered or accepted silently.",
            )
        if literal_string(keyword(node, "on_bad_lines")) == "skip":
            self.add(
                node,
                "high",
                "RF204",
                "data-selection",
                "on_bad_lines='skip' drops malformed records.",
                "Dataset membership and coverage can change without an explicit failure.",
            )
        if literal_bool(keyword(node, "drop_last")) is True:
            self.add(
                node,
                "medium",
                "RF205",
                "data-selection",
                "drop_last=True removes an incomplete batch.",
                "Samples and optimization steps may differ from the protocol.",
            )
        if leaf in {"nanmean", "nanmedian", "nansum", "nanmin", "nanmax"}:
            self.add(
                node,
                "medium",
                "RF206",
                "aggregation",
                f"{leaf} excludes or neutralizes NaN values during aggregation.",
                "Failed or invalid observations may disappear from the reported denominator.",
            )
        if literal_bool(keyword(node, "truncation")) is True:
            self.add(
                node,
                "medium",
                "RF207",
                "data-transformation",
                "truncation=True permits input shortening.",
                "Token or sequence membership may change unless truncation is protocol-defined and accounted.",
            )

        if leaf in {"clip", "clamp", "clamp_", "clip_by_value", "clip_by_norm"}:
            self.add(
                node,
                "low",
                "RF301",
                "numeric-transform",
                f"{leaf} bounds numerical values.",
                "Clipping is scientifically valid only when its source and order are defined.",
            )

        if leaf == "load_state_dict" and literal_bool(keyword(node, "strict")) is False:
            self.add(
                node,
                "high",
                "RF401",
                "compatibility",
                "load_state_dict(strict=False) accepts incomplete or extra state.",
                "The executed model may differ from the required checkpoint architecture.",
            )
        if literal_bool(keyword(node, "ignore_mismatched_sizes")) is True:
            self.add(
                node,
                "high",
                "RF404",
                "compatibility",
                "ignore_mismatched_sizes=True accepts an architecture/checkpoint mismatch.",
                "Model parameters may be missing or reinitialized while the requested checkpoint appears loaded.",
            )

        if leaf in {"retry", "stop_after_attempt", "retry_if_exception_type"}:
            self.add(
                node,
                "low",
                "RF501",
                "retry",
                f"{leaf} configures automatic retry behavior.",
                "Verify attempt counting, resampling, and protocol authorization.",
            )
        if leaf in {"get_last_checkpoint", "auto_resume", "resume_from_checkpoint"}:
            self.add(
                node,
                "medium",
                "RF502",
                "checkpoint-selection",
                f"{leaf} may resume from automatically selected state.",
                "Inherited optimizer, scheduler, data-order, or random state can change the experimental run.",
            )
        for resume_key in ("auto_resume", "resume_from_checkpoint"):
            resume_value = keyword(node, resume_key)
            if resume_value is not None and not (
                isinstance(resume_value, ast.Constant)
                and resume_value.value in (False, None, "")
            ):
                self.add(
                    node,
                    "medium",
                    "RF502",
                    "checkpoint-selection",
                    f"{resume_key} enables checkpoint reuse or automatic resumption.",
                    "Verify checkpoint identity and restoration of optimizer, scheduler, data-order, and RNG state.",
                )
                break
        cache_value = keyword(node, "load_from_cache_file")
        if literal_bool(cache_value) is True:
            self.add(
                node,
                "low",
                "RF503",
                "artifact-reuse",
                "load_from_cache_file=True permits reuse of transformed data.",
                "A stale cache can cross code, data, preprocessing, or ablation boundaries.",
            )
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        if isinstance(node.op, ast.Or) and len(node.values) > 1:
            if any(is_empty_default(value) for value in node.values[1:]):
                self.add(
                    node,
                    "low",
                    "RF103",
                    "default-substitution",
                    "Boolean-or selects an empty or default value.",
                    "Falsy values may be scientifically meaningful.",
                )
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        if contains_capability_probe(node.test):
            self.add(
                node,
                "medium",
                "RF402",
                "backend-selection",
                "Runtime availability selects between alternate values.",
                "A device or backend fallback may change precision, kernels, or behavior.",
            )
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        if node.orelse and contains_capability_probe(node.test):
            self.add(
                node,
                "medium",
                "RF402",
                "backend-selection",
                "Runtime availability selects an alternate branch.",
                "A device or backend fallback may change precision, kernels, or behavior.",
            )
        self.generic_visit(node)


def python_files(paths: Iterable[str]) -> list[Path]:
    files: set[Path] = set()
    for raw in paths:
        path = Path(raw)
        if path.is_file() and path.suffix == ".py":
            files.add(path)
        elif path.is_dir():
            for candidate in path.rglob("*.py"):
                if not any(
                    part in {".git", ".venv", "venv", "node_modules", "__pycache__"}
                    for part in candidate.parts
                ):
                    files.add(candidate)
    return sorted(files)


def audit(path: Path) -> tuple[list[Finding], str | None]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [], str(exc)
    visitor = Auditor(path, source)
    visitor.visit(tree)
    return visitor.findings, None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report possible semantic fallbacks in Python research code."
    )
    parser.add_argument("paths", nargs="+", help="Python files or directories")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument(
        "--min-severity",
        choices=("high", "medium", "low"),
        default="medium",
        help="Lowest severity to print (default: medium)",
    )
    parser.add_argument(
        "--fail-on",
        choices=("none", "high", "medium", "low"),
        default="none",
        help="Return exit status 1 at or above this severity (default: report only)",
    )
    parser.add_argument(
        "--show-suppressed",
        action="store_true",
        help="Show source-authorized findings suppressed with a reason",
    )
    args = parser.parse_args()

    files = python_files(args.paths)
    findings: list[Finding] = []
    errors: list[dict[str, str]] = []
    for path in files:
        found, error = audit(path)
        findings.extend(found)
        if error:
            errors.append({"path": str(path), "error": error})

    findings.sort(key=lambda row: (row.path, row.line, -RANK[row.severity], row.rule))
    unsuppressed = [item for item in findings if not item.suppressed]
    suppressed = [item for item in findings if item.suppressed]
    visible = [
        item
        for item in unsuppressed
        if RANK[item.severity] >= RANK[args.min_severity]
    ]
    lower_severity = len(unsuppressed) - len(visible)

    if args.json:
        print(
            json.dumps(
                {
                    "summary": {
                        "files": len(files),
                        "findings": len(visible),
                        "suppressed_low_severity": lower_severity,
                        "errors": len(errors),
                        "suppressed": len(suppressed),
                        "total_candidates": len(findings),
                    },
                    "findings": [asdict(item) for item in visible],
                    "suppressed": [asdict(item) for item in suppressed],
                    "errors": errors,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for item in visible:
            print(
                f"{item.path}:{item.line}:{item.column}: "
                f"{item.severity} {item.rule} [{item.category}] {item.detail}"
            )
        if args.show_suppressed:
            for item in suppressed:
                print(
                    f"{item.path}:{item.line}:{item.column}: suppressed {item.rule} "
                    f"[{item.category}] {item.suppression_reason}"
                )
        for error in errors:
            print(f"{error['path']}: parse-error: {error['error']}")
        print(
            f"Audited {len(files)} Python files; {len(visible)} displayed findings; "
            f"{lower_severity} lower-severity findings suppressed by display threshold; "
            f"{len(suppressed)} source-authorized findings suppressed; "
            f"{len(errors)} parse errors."
        )

    if errors:
        return 2
    if args.fail_on != "none":
        threshold = RANK[args.fail_on]
        if any(RANK[item.severity] >= threshold for item in unsuppressed):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
