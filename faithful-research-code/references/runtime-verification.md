# Minimal runtime verification

## Close a verification gap with evidence, not another heuristic

Static analysis cannot prove arbitrary dynamic SDK or cross-module behavior. For each claim-relevant dynamic surface, name a concrete runtime check in the source-to-code table. For an HTTP/LLM pipeline that includes the actual client/transport, this means injected 429, 500, connection/timeout and malformed-response cases asserting exactly one outbound attempt, propagated failure, no next sample, and no reportable result. A test of a mock function alone is not evidence about a real SDK.

Snapshot the resolved settings and pinned client identity used by these checks; retain the commands, logs and versions. If the client is unavailable or a required check is not implemented, mark it `UNVERIFIED` and block the corresponding runtime-verification/reproduction claim. Do not mark the software implementation itself impossible: deliver it with a restricted static-only claim when that is what the task permits.

Use `required_checks` in the command plan to enforce that every declared check really executes and exits successfully before a run gets a completion manifest. The runner cannot know whether a test is meaningful: review its assertions against the source contract. Never list `print('passed')`, a mocked-away client, or a swallowed failure as a verification command. Keep the static scan and runtime claim distinct.

## Optional local command runner

Use the small standard-library runner when a project lacks its own suitable supervisor. Reuse an existing scientifically compatible runner instead of adding a second scheduler. The viewer alone still performs no scheduling or process cancellation.

```bash
python <skill-dir>/scripts/run_research_workflow.py <execution-plan.json> <fresh-run-dir> --cwd <project-dir>
python <skill-dir>/scripts/research_progress.py serve <fresh-run-dir>
```

The [example plan](../assets/execution-plan.example.json) is runnable from any directory and demonstrates only local command execution, not a paper result. Replace it with actual commands and checks. Every node has an argument array, dependencies, and a finite `timeout_seconds`. `{python}` resolves to the runner's interpreter; all other arguments are literal. No shell parsing, implicit retries, resume, or command substitution. Only execution-track unconditional command nodes are supported. Expand conditions/loops explicitly before invoking this runner, or retain the project's existing protocol-aware runner.

`max_parallel` is frozen in the plan. Values above one require `parallelism_source`; this is a recorded scientific authorization, not an automatic inference from diagram layout. Required checks identify existing nodes. An empty list requires an explicit `no_runtime_checks_reason` and does not establish runtime verification.

The sole supervisor writes progress events, so its children do not write the same journal or use a collector. Each command receives `RESEARCH_RUN_DIR` and its own `RESEARCH_NODE_DIR`; stdout/stderr stay in `<node>/stage.log`. Commands must stage their outputs in the run directory. Only an existing `RUN_COMPLETE.json` makes this run eligible for further reviewed publication. This marker contains command exit codes and log hashes; it does not prove scientific correctness or publish a paper claim. Never aggregate partial outputs based merely on a file existing.

First observed nonzero exit, timeout, launch failure, or observer error stops new dispatch. The supervisor terminates active owned children, waits for their exit, preserves independent outcomes and logs, and re-raises the original failure. If termination cannot be confirmed, `termination_unknown` records the affected node in supervisor/failure metadata and the viewer displays unknown, including when the original stage already failed due to timeout. The original failed journal event remains intact; a failed stage does not prove that its process exited. No completion manifest is published for a failed run. Plan, logs, pending manifest, failure metadata and available events remain for inspection.

To keep this runner small and portable, plans must declare `process_scope: direct_children_only`: commands may use threads but must not spawn additional processes, daemons, remote jobs, or detached workers. Such methods require their existing process-tree-aware scheduler; do not silently disable source-defined multiprocessing to fit this runner. The capability boundary is explicit and validated before launch, not a promise to manage arbitrary process trees.

The supervisor updates an atomic heartbeat once per second. After five seconds without a heartbeat, the viewer labels observed running nodes unknown; it does not invent failed/succeeded events. If the supervisor is hard-killed, surviving direct children may finish staging outputs, but no supervisor completion marker exists and those outputs are not reportable. A finished preparation heartbeat without a completion marker is displayed as awaiting publication, never as verified success.

## Repeatable model-candidate evaluation

Use [the frozen behavior prompt](../assets/behavior-eval/prompt.md) in a fresh task for each model/configuration being evaluated. Give the model the skill and prompt, not the reference candidate. Save each generated module separately. Then run:

```bash
python <skill-dir>/scripts/evaluate_behavior.py <candidate.py> <fresh-evaluation-dir> --generator-id <actual-model-and-settings>
```

The bundled eight test methods exercise formula/domain checks, complete population accounting, four mock failure types, branch-order independence, paired generation RNGs, bootstrap isolation, observer failure before publication, and successful publication. The successful path checks the hand-computed result (5, numerator 30, denominator 6), returned-versus-published report equality, and completed progress. The supplied `reference_candidate.py` came from a previous local forward test and exists to verify that the evaluation harness itself works; rerunning it is not a new model evaluation.

PASS requires exit code zero **and** `checks.json` proving every required test method completed successfully, with the exact expected test names and count. Required names are read from the frozen test source. Early process exit, skipped/missing tests, missing completion evidence, incorrect final results, and missing publication cannot receive PASS. The receipt is test evidence, not a security boundary against a malicious candidate running in the same process.

The evaluator snapshots candidate and test source bytes before launch and retains those snapshots, their hashes, test output, failed runs, commands, and PASS/FAIL/TIMEOUT. It compiles the verified candidate snapshot directly instead of accepting an existing `.pyc`; hashes describe the evaluated snapshot even if the original file subsequently changes. The original candidate directory remains the working directory and local import location, and `__file__` remains the original candidate path. Imported helper modules and dependencies are not frozen by this single-module fixture; preserve their versions separately when applicable. `generator-id` is user-supplied provenance, not independently verified identity. Run all predeclared candidates and report the full denominator; do not retain only passing samples. The tool uses no model API and does not silently choose a model or incur model charges. Candidate modules are executable code and use the current host's execution permissions; this is not an untrusted-code sandbox.

This supplies a reusable comparison procedure, not a universal cross-model guarantee. Report only the model/candidate/scenario combinations actually executed. The separate `tests/behavior-cases.json` remains a prompt inventory, not measured automatic activation accuracy. A claim about selection accuracy requires real host/model invocations with recorded selection traces, including negative cases.
