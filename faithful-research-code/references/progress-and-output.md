# Compact output and observable progress

## Output policy

Keep scientific fidelity first, auditability second, and token economy third. Reuse existing code only after checking semantic equivalence. Avoid speculative wrappers, repeated explanations, whole-file echoes, and verbose success logs. Do not minify scientific code or omit required work, provenance, failing cases, or uncertainty to save tokens. Put complete tables, commands, raw logs, and evidence in files; link them from a short response. No fixed token reduction is promised without measurement.

This policy references [Ponytail's minimality approach](https://github.com/DietrichGebert/ponytail/blob/main/skills/ponytail/SKILL.md), reviewed 2026-09-20. It is independently written and requires no Ponytail plugin, hooks, network access, or persistent activation. Ponytail's general-purpose shortest-solution and intensity settings must not override the scientific route. If users separately enable it, apply only compatible simplifications.

## Before generating code

Show a complete Mermaid plan with two separate tracks:

1. **Generation**: source/idea.md and clarification → actual functions in implementation order → negative/formula/API checks → fallback audit → README → fresh independent-agent review and any fixes/recheck → report.
2. **Execution**: actual scientific data/state flow, including initialization, transformations, training/inference, evaluation, aggregation, and artifact commitment as applicable.

Use stable node IDs. Include branch conditions and loop/round boundaries in labels and the linked workflow contract. Never replace actual function names with a generic “implement everything” node. Independent stages may run simultaneously once their dependencies succeed. On failure/blockage/cancellation/lost observation, the tracker rejects NEW starts on that track, while accepting truthful terminal events from already running workers. The track remains stopped even if in-flight work later succeeds. A changed plan or restarted experiment gets a new run directory; keep previous evidence.

Use [idea-and-review.md](idea-and-review.md) for node specificity: each scientific node names the actual dataset/split or algorithm substep, carries `idea_refs` (an array of requirement IDs) and a `description` (plain-text inputs, rule/source, outputs, code symbol, and check). The viewer shows IDs and expandable descriptions; chat snapshots link `idea.md`. These optional tracker fields are required by the skill for new scientific plans, not by the general observer API for older or operational plans. They are declarations, not automatic semantic validation. Keep blocked clarification questions visible before dispatch; do not emit a runtime stop merely to annotate a future stage.

The tracker accepts a topologically ordered DAG per track and displays siblings side by side with fan-out/join edges. Scientific loops are one stage with its stopping rule in the label, or explicitly expanded predeclared rounds; it does not execute or schedule the method. A conditional node must declare `condition` in the frozen plan before it may emit `skipped` with a reason. A join accepts that skipped input only if it explicitly lists that dependency under `optional_dependencies`; otherwise the join is blocked. Never mark an unexecuted branch successful. Use finer nodes only when actual events can support them.

## Live viewer and event journal

Requires Python 3.11+; uses only the standard library. Use the host's available Python executable. Create a task-specific plan using [../assets/progress-plan.example.json](../assets/progress-plan.example.json) as a schema example, replacing all stages with the actual method. Include only applicable tracks. Write plan files in the project, never in the installed skill.

```bash
python <skill-dir>/scripts/research_progress.py init <new-run-dir> --plan <project-plan.json>
python <skill-dir>/scripts/research_progress.py serve <new-run-dir>
```

Choose interface language with `serve <new-run-dir> --lang en` or `--lang zh-CN` (default). This translates only viewer controls and labels. Project titles, node descriptions and event evidence remain verbatim; author them in the developer's requested language.

Open the printed loopback URL for the user, using the host's browser-panel tool when available. Run the viewer as a background process using the host's normal facilities (hidden window on Windows). It checks the local read-only status endpoint once per second, showing all nodes and dependency arrows from the outset. The graph and Token panel refresh at stage transitions or explicit batch/round progress events; request failures and supervisor observation changes also trigger an update. Successful per-request usage remains logged and is displayed at the next boundary. The persistent viewer reads newly appended events rather than replaying the full history on every poll. It does not call research APIs or launch work. Polling checks the monitor connection, not experiment retry. Only this run's plan/events are served; no directory browsing, external CDN, telemetry, or remote binding.

The same page includes a Token/request panel and current workflow stages. For LLM work, follow [usage-dashboard.md](usage-dashboard.md) to record actual request observations; uninstrumented runs explicitly show no usage connection, not zero consumption. The collector serializes usage and stage events together. Reported usage, estimates and unknown fields remain separate.

At real generation boundaries:

```bash
python <skill-dir>/scripts/research_progress.py event <new-run-dir> contract running
python <skill-dir>/scripts/research_progress.py event <new-run-dir> contract succeeded
python <skill-dir>/scripts/research_progress.py show <new-run-dir> --mermaid
```

Use `failed` for attempted work that raised an error and `blocked` for a missing prerequisite. The event detail is short, public-safe evidence (for example a test report path), never an API key or private raw response. CLI event commands are observer declarations, not independent proof. Only record success after checking the relevant artifact/exit status.

Use `cancelled` only after a worker/scheduler confirms cancellation; never mark already running requests cancelled merely because another request failed. Use `unknown` with an observation-loss reason when a worker disappears; this is not proof of failure or success. A later verified terminal event may resolve that node, but cannot restart the stopped track. The caller must stop new submissions and cancel pending jobs; this observer does not terminate processes or revoke external requests. No failed/stopped track may commit reportable artifacts, even if another branch succeeded.

For measurable work, declare `total` in the plan and send `update --completed N` while running. Counts must be monotonic and cannot exceed that frozen total. Success requires the full declared total. Without a known total, show only the stage and real event details; never estimate progress from elapsed time. Loop round details can be recorded as public-safe event text. These updates do not grant permission for retries or sample exclusion.

## Concurrent producer integration

If using the [optional local command runner](runtime-verification.md), the parent supervisor already owns event recording, child cancellation and heartbeat updates; do not also start a collector for that run. The collector below is for independently instrumented workers with an existing scheduler.

Start exactly one collector per run, in addition to the read-only viewer:

```bash
python <skill-dir>/scripts/research_progress.py collect <new-run-dir> --endpoint <private-endpoint.json>
python <skill-dir>/scripts/research_progress.py event <new-run-dir> loader running --collector <private-endpoint.json>
python <skill-dir>/scripts/research_progress.py event <new-run-dir> estimator running --collector <private-endpoint.json>
```

The example generation nodes `loader` and `estimator` depend only on `contract`, which must already have succeeded. Every concurrent worker uses the collector. It receives authenticated loopback IPC events, serializes validation and fsynced journal writes, then acknowledges each event. It never runs scientific work. Each client interaction has one 30-second monotonic deadline covering connection, standard-library mutual authentication, sending, and complete acknowledgement receipt; partial frames cannot extend it. The collector applies the same communication deadline to each accepted connection. There are no automatic client retries: a timeout or missing acknowledgement stops that worker with an uncertain observation; inspect evidence instead of resending or falling back to direct writes. A collector lease prevents a second collector and direct event writes. Protect the endpoint file using the run directory's access controls: it contains a local authentication key, is not a scientific artifact, and must not be published. The read-only viewer never serves it.

In worker code use `with stage(run_dir, node_id, collector=endpoint_path): ...`. For counted work call `emit(endpoint_path, node_id, "update", completed=N)` inside that context. `stage()` verifies that the collector belongs to the requested run. Do not use direct `record()` from concurrent workers. The collector provides event serialization, not scientific scheduling, ordering, cancellation, or RNG isolation; the experiment's runner must implement and test those protocol requirements. It also must not commit output until all required tasks succeeded and the track was never stopped.

For live experimental execution, copy the bundled script to the generated project's support directory and instrument **actual execution boundaries** with its `stage` context manager. Preserve its relative imports/path in the documented entry point. Initialize a fresh execution run before invoking the pipeline; do not reuse smoke-test progress as full-run evidence.

```python
from research_progress import stage

with stage(run_dir, "load"):
    data = load_required_data(config)
with stage(run_dir, "estimate"):
    result = estimate(data, config)
```

Adapt symbols to the actual code; these two functions are illustrative, not provided APIs. A context manager records start, then success or failure and re-raises the original exception. Keep scientific outputs and stderr/tracebacks in the run's own files using the project's failure recorder. The progress journal contains exception type only, not the traceback. Never use the observer to catch-and-continue, retry, change seeds, filter results, or clean scientific artifacts. A failure to persist progress stops the next scientific step; if science already failed, a progress-write failure annotates but does not replace the original exception.

### Final publication boundary

Do not publish the formal result inside a normal `stage()` body: its exit still performs a fallible progress write. Instead track a node named **prepare_commit**, stage and validate the complete result, finish all worker/observer acknowledgements, and verify that the execution track is complete and was never stopped. Then perform the final atomic publication as the last fallible operation on the scientific success path. Keep the staged artifact if publication fails; propagate the original error and preserve failure evidence. No post-publication observer error may retroactively masquerade as an earlier scientific failure.

```python
with stage(run_dir, "prepare_commit", collector=endpoint):
    write_and_validate_staged_result(staged_path, result)
# All scientific workers have joined; the collector has acknowledged every event.
if snapshot(run_dir)["tracks"]["execution"] != "complete":
    raise RuntimeError("Run is not eligible for publication")
staged_path.replace(final_manifest_path)  # Same-filesystem, fresh run; atomic success marker.
```

These are integration examples, not provided result-writing functions. A track's `complete` means its declared stages finished; **prepare_commit success is readiness, not publication**. The frozen workflow/README must include the final publication step and identify its committed manifest as the authority for scientific success. A supervising agent may show that final outcome only after observing the process exit and manifest, independently of the scientific process. If the final rename fails, the preparation graph may remain complete but the run is not successful. Inject both observer-write and publication failures in generated-project tests; require no committed result in either case. For multi-file results, retain files in a unique staging/run directory and atomically publish only the manifest that makes them reportable.

## Truthful limitations

The journal is append-only through the API, fsynced, single-writer, and rejects invalid transitions, dependency bypass, and reusing completed/failed nodes. Multiple producers are supported through the collector; competing direct writers fail. It is not tamper-proof. An interrupted write, stale lease, or uncertain acknowledgement requires inspection and a new run, not automatic truncation, replay, or repair. The viewer may briefly show unavailable state during a partial write; it never invents success. In event-only mode, a hard kill can leave a node running as its last known state until an external supervisor reports `unknown`. With the optional runner, stale heartbeat detection displays unknown automatically without fabricating a scientific failure. Connected browser polling alone never proves science is alive. No duration estimates or fabricated percentages.

Chat Mermaid is a snapshot and cannot update an earlier message in place. Without a usable viewer, explicitly use snapshot mode and emit the current node/status at stage boundaries, on failures, and in brief updates during long stages; do not claim continuous runtime monitoring. Stop the viewer after the task unless the user still needs it. Keep the journal and render a final Mermaid snapshot for durable review.
