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
import io
import re
import tokenize
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator


RANK = {"high": 3, "medium": 2, "low": 1}
THREAD_VARIABLES = {"OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                    "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS"}
CONCURRENT_CALLS = {"asyncio.gather", "asyncio.create_task", "asyncio.ensure_future",
                    "asyncio.TaskGroup", "asyncio.as_completed", "asyncio.to_thread",
                    "concurrent.futures.ThreadPoolExecutor", "concurrent.futures.ProcessPoolExecutor",
                    "multiprocessing.Pool", "multiprocessing.pool.Pool", "joblib.Parallel"}
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


def literal_zero(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and type(node.value) is int and node.value == 0


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


class LocalBindings(ast.NodeVisitor):
    """Find lexical bindings without entering a nested execution scope."""

    def __init__(self) -> None:
        self.names: set[str] = set()
        self.outer_names: set[str] = set()
        self.global_names: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.names.add(node.id)

    def visit_Import(self, node: ast.Import) -> None:
        self.names.update(item.asname or item.name.split('.')[0] for item in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.names.update(item.asname or item.name for item in node.names)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.names.add(node.name)

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_ClassDef = visit_FunctionDef

    def visit_Lambda(self, node: ast.Lambda) -> None:
        pass

    def visit_comprehension(self, node: ast.comprehension) -> None:
        # Iteration targets belong to the comprehension, not the enclosing function.
        self.visit(node.iter)
        for condition in node.ifs:
            self.visit(condition)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.names.add(node.name)
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        # Runtime writes through global/nonlocal are not propagated to other scopes.
        self.outer_names.update(node.names)
        self.global_names.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.outer_names.update(node.names)


class Auditor(ast.NodeVisitor):
    def __init__(self, path: Path, source: str) -> None:
        self.path = path
        self.lines = source.splitlines()
        self.comments = {token.start[0]: token.string
                         for token in tokenize.generate_tokens(io.StringIO(source).readline)
                         if token.type == tokenize.COMMENT}
        self.findings: list[Finding] = []
        self.scopes: list[tuple[str, dict[str, str | None]]] = [("module", {})]
        self.numeric_import_seen = False
        self.function_depth = 0

    @property
    def aliases(self) -> dict[str, str | None]:
        return self.scopes[-1][1]

    def resolve(self, node: ast.AST) -> str:
        name = dotted_name(node)
        root, dot, rest = name.partition(".")
        for index in range(len(self.scopes) - 1, -1, -1):
            kind, bindings = self.scopes[index]
            # A class namespace is not an enclosing lexical scope for methods.
            if kind == "class" and index != len(self.scopes) - 1:
                continue
            if root in bindings:
                root = bindings[root] or "<unresolved>"
                break
        return root + (dot + rest if dot else "")

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.aliases[node.id] = None

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        # Assignment expressions escape a comprehension's iteration scope.
        for kind, bindings in reversed(self.scopes):
            if kind != "comprehension":
                bindings[node.target.id] = None
                break

    def visit_Import(self, node: ast.Import) -> None:
        for item in node.names:
            self.aliases[item.asname or item.name.split(".")[0]] = (
                item.name if item.asname else item.name.split(".")[0]
            )
            self.numeric_import_seen |= item.name.split(".")[0] in {"numpy", "scipy", "torch"}

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for item in node.names:
            self.aliases[item.asname or item.name] = f"{node.module}.{item.name}"
        self.numeric_import_seen |= (node.module or "").split(".")[0] in {"numpy", "scipy", "torch"}

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if (isinstance(target, ast.Subscript)
                    and self.resolve(target.value) == "os.environ"
                    and literal_string(target.slice) in THREAD_VARIABLES
                    and (self.numeric_import_seen or self.function_depth)):
                self.add(target, "high" if self.numeric_import_seen else "medium", "RF702", "determinism",
                         "Thread environment is assigned after a numerical import." if self.numeric_import_seen
                         else "Function execution order is unresolved; verify thread configuration in the launcher.",
                         "Configure the launcher before any direct or transitive numerical import.")
        self.visit(node.value)
        for target in node.targets:
            self.visit(target)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        # Evaluate the RHS before rebinding the target, as for ordinary assignment.
        # A module/class annotation alone does not replace an existing binding.
        if node.value is not None:
            self.visit(node.value)
            self.visit(node.target)
        elif not isinstance(node.target, ast.Name):
            self.visit(node.target)
        self.visit(node.annotation)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) and self.resolve(decorator) in {
                "tenacity.retry", "retry.retry"
            }:
                self.add(decorator, "high", "RF501", "retry",
                         "Bare decorator enables automatic retries.",
                         "Operational retries are prohibited; retain only source-defined method steps.")
            self.visit(decorator)
        # Defaults and annotations execute in the defining scope, not the body.
        self.visit(node.args)
        if node.returns:
            self.visit(node.returns)
        bindings = LocalBindings()
        for statement in node.body:
            bindings.visit(statement)
        for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
            bindings.names.add(argument.arg)
        for argument in (node.args.vararg, node.args.kwarg):
            if argument:
                bindings.names.add(argument.arg)
        self.aliases[node.name] = None
        previous_numeric = self.numeric_import_seen
        self.numeric_import_seen = False
        self.function_depth += 1
        local = dict.fromkeys(bindings.names - bindings.outer_names)
        local.update({name: self.scopes[0][1].get(name) for name in bindings.global_names})
        self.scopes.append(("function", local))
        for statement in node.body:
            self.visit(statement)
        self.scopes.pop()
        self.function_depth -= 1
        self.numeric_import_seen = previous_numeric

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for expression in (*node.decorator_list, *node.bases, *node.keywords):
            self.visit(expression)
        self.scopes.append(("class", {}))
        for statement in node.body:
            self.visit(statement)
        self.scopes.pop()
        self.aliases[node.name] = None

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.visit(node.args)
        bindings = LocalBindings()
        bindings.visit(node.body)
        bindings.names.update(arg.arg for arg in (*node.args.posonlyargs, *node.args.args,
                                                  *node.args.kwonlyargs))
        bindings.names.update(arg.arg for arg in (node.args.vararg, node.args.kwarg) if arg)
        previous_numeric = self.numeric_import_seen
        self.numeric_import_seen = False
        self.function_depth += 1
        self.scopes.append(("function", dict.fromkeys(bindings.names)))
        self.visit(node.body)
        self.scopes.pop()
        self.function_depth -= 1
        self.numeric_import_seen = previous_numeric

    def visit_ListComp(self, node: ast.ListComp) -> None:
        # Only the first iterable is evaluated in the defining scope.
        self.visit(node.generators[0].iter)
        targets = {child.id for generator in node.generators
                   for child in ast.walk(generator.target) if isinstance(child, ast.Name)}
        self.scopes.append(("comprehension", dict.fromkeys(targets)))
        for index, generator in enumerate(node.generators):
            if index:
                self.visit(generator.iter)
            for condition in generator.ifs:
                self.visit(condition)
        if isinstance(node, ast.DictComp):
            self.visit(node.key)
            self.visit(node.value)
        else:
            self.visit(node.elt)
        self.scopes.pop()

    visit_SetComp = visit_ListComp
    visit_DictComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp

    def suppression_for(self, rule: str, line: int) -> str | None:
        for candidate in (line, line - 1):
            if candidate < 1 or candidate > len(self.lines):
                continue
            match = SUPPRESSION_RE.search(self.comments.get(candidate, ""))
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
        if node.name:
            self.aliases[node.name] = None
        broad = is_broad_handler(node)
        parsing_errors = {
            "JSONDecodeError",
            "ParserError",
            "UnicodeDecodeError",
            "ValueError",
        }
        for child in handler_nodes(node.body):
            if not broad and (
                isinstance(child, (ast.Pass, ast.Continue, ast.Break, ast.Return))
            ):
                self.add(child, "medium", "RF009", "control-flow",
                         "Typed exception handler can swallow failure or substitute a result.",
                         "A narrow exception type does not make skipping or default output scientifically valid.")
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
        name = self.resolve(node.func)
        leaf = name.split(".")[-1]

        # This is deliberately a candidate detector, not cross-module data-flow analysis.
        llm_client = name in {
            f"{module}.{client}" for module in ("openai", "anthropic")
            for client in ("OpenAI", "AsyncOpenAI", "AzureOpenAI", "AsyncAzureOpenAI",
                           "Anthropic", "AsyncAnthropic", "AnthropicBedrock",
                           "AsyncAnthropicBedrock", "AnthropicVertex", "AsyncAnthropicVertex")
        }
        if llm_client and not literal_zero(keyword(node, "max_retries")):
            self.add(node, "high", "RF504", "implicit-retry",
                     "LLM client does not explicitly disable SDK retries.",
                     "Use max_retries=0 and verify the pinned SDK and transport at runtime.")
        for item in node.keywords:
            if item.arg in {"max_retries", "retries", "retry", "retry_config"} and not (
                literal_zero(item.value) or literal_bool(item.value) is False
            ):
                self.add(node, "high", "RF505", "retry",
                         f"{item.arg} may enable retries or has an unresolved policy.",
                         "Disable operational retries at every SDK, transport, and proxy layer.")
        if name.startswith(("tenacity.", "backoff.")) or leaf in {"Retry", "Retrying", "AsyncRetrying"}:
            self.add(node, "high", "RF501", "retry",
                     f"{name} constructs a retry policy.",
                     "Inspect defaults and attempts; a logged policy is not authorization.")
        if name in CONCURRENT_CALLS or leaf in {"ThreadPoolExecutor", "ProcessPoolExecutor"}:
            self.add(node, "high", "RF601", "concurrency",
                     f"{name} schedules concurrent work.",
                     "Default to serial execution; require predeclared worker seeds, ordering, and failure propagation.")
        if literal_bool(keyword(node, "return_exceptions")) is True:
            self.add(node, "high", "RF602", "control-flow",
                     "return_exceptions=True turns task failures into result values.",
                     "Failures must stop the research path and remain outside aggregation.")
        if name in {f"numpy.{x}" for x in ("quantile", "percentile", "nanquantile", "nanpercentile")}:
            # a, q, axis, out, overwrite_input, method (NumPy >= 1.22).
            positional = not any(isinstance(arg, ast.Starred) for arg in node.args[:6])
            method = keyword(node, "method")
            if method is None and positional and len(node.args) >= 6:
                method = node.args[5]
            unpacked = any(isinstance(arg, ast.Starred) for arg in node.args) or any(
                item.arg is None for item in node.keywords)
            if method is None or unpacked:
                self.add(node, "medium", "RF701", "statistics",
                         "Quantile arguments are unpacked; verify the resolved method at runtime." if unpacked
                         else "Quantile estimator method is implicit.",
                         "Specify the source-defined method and pin NumPy; do not invent linear interpolation.")
        if name in {"numpy.nanquantile", "numpy.nanpercentile"}:
            self.add(node, "medium", "RF206", "aggregation",
                     "NaN quantiles exclude invalid observations.",
                     "Verify explicit population and failure accounting.")
        if name in {"os.environ.setdefault", "os.environ.update", "os.putenv"}:
            keys = [literal_string(arg) for arg in node.args[:1]]
            if name.endswith("update") and node.args and isinstance(node.args[0], ast.Dict):
                keys = [literal_string(k) for k in node.args[0].keys]
            keys.extend(item.arg for item in node.keywords)
            if set(keys) & THREAD_VARIABLES:
                self.add(node, "high" if self.numeric_import_seen else "medium", "RF702", "determinism",
                         "Thread environment mutation needs launcher-order review.",
                         "Set exact values before numerical imports; setdefault can inherit conflicting values.")

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
                "high",
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
        # research-fidelity: allow=RF009 reason="Audit parse failure is explicit error data; main exits 2 and reports the affected file."
        return [], str(exc)
    visitor = Auditor(path, source)
    visitor.visit(tree)
    return visitor.findings, None


def audit_config(path: Path) -> tuple[list[Finding], str | None]:
    """Inspect explicitly supplied resolved JSON/TOML without executing configuration."""
    try:
        source = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            config = json.loads(source)
        elif path.suffix.lower() == ".toml":
            config = tomllib.loads(source)
        else:
            raise ValueError("Only resolved JSON/TOML supported; export other formats explicitly")
    except (OSError, UnicodeError, ValueError) as error:
        # research-fidelity: allow=RF009 reason="Configuration parse errors are reported and cause CLI exit 2; no valid config is substituted."
        return [], str(error)
    findings = []

    def walk(value, location):
        if isinstance(value, dict):
            for key, item in value.items():
                address = f"{location}.{key}"
                normalized = key.lower()
                rule = None
                if normalized in {"max_retries", "retries", "retry", "retry_config"}:
                    disabled = (type(item) is int and item == 0) or item is False
                    if not disabled:
                        rule = "RF801"
                elif normalized in {"max_attempts", "total_max_attempts"}:
                    if type(item) is not int or item != 1:
                        rule = "RF801"
                elif normalized in {"max_workers", "concurrency", "parallelism", "n_jobs"}:
                    if type(item) is not int or item != 1:
                        rule = "RF802"
                if rule:
                    findings.append(Finding(str(path), 1, 1, "high", rule, "resolved-config",
                        f"{address}: retry/concurrency policy is not statically disabled or serial; review required.",
                        "Location is a structural key, not a source line. Verify effective client settings and outbound attempts."))
                walk(item, address)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{location}[{index}]")

    walk(config, "$")
    return findings, None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report possible semantic fallbacks in Python research code."
    )
    parser.add_argument("paths", nargs="*", help="Python files or directories")
    parser.add_argument("--config", nargs="+", default=[], help="Resolved JSON/TOML snapshots; never executable config")
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
    for raw in args.paths:
        path = Path(raw)
        if not path.exists() or (path.is_file() and path.suffix != ".py"):
            errors.append({"path": raw, "error": "Missing path or unsupported file type; nothing audited."})
    if not files and not args.config:
        errors.append({"path": ", ".join(args.paths), "error": "No Python files found; audit is incomplete."})
    for path in files:
        found, error = audit(path)
        findings.extend(found)
        if error:
            errors.append({"path": str(path), "error": error})
    config_paths = sorted({Path(raw) for raw in args.config})
    for path in config_paths:
        found, error = audit_config(path)
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
                        "files": len(files) + len(config_paths),
                        "python_files": len(files),
                        "config_files": len(config_paths),
                        "findings": len(visible),
                        "suppressed_low_severity": lower_severity,
                        "errors": len(errors),
                        "suppressed": len(suppressed),
                        "total_candidates": len(findings),
                    },
                    "findings": [asdict(item) for item in visible],
                    "suppressed": [asdict(item) for item in suppressed],
                    "errors": errors,
                    "coverage": {
                        "claim": "heuristic review only; absence of findings is not fidelity proof",
                        "unverified": ["dynamic/cross-module configuration", "custom SDKs and wrappers",
                                       "effective runtime settings", "outbound attempt counts", "non-Python code"],
                    },
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
            f"Audited {len(files)} Python files and {len(config_paths)} resolved config files; {len(visible)} displayed findings; "
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
