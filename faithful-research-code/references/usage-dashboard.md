# LLM usage in the existing HTML monitor

Use this only when the generated research program calls an LLM. The existing viewer combines workflow status with usage records; it does not measure Codex's own conversation usage, infer consumption from elapsed time, intercept arbitrary SDKs, enforce model context limits, or calculate bills. No extra web server, telemetry service, provider dependency, or automatic request is introduced.

## Recording contract

Use `research_progress.record_usage` at actual call boundaries inside a running **execution** stage. Register a unique request ID before the outbound call. Keep the model identity and owning node stable; include the provider in the model label if needed. Every event is a complete cumulative snapshot for that request, not a delta. Streaming estimates can be updated while running and replaced by the final reported snapshot. A terminal record is immutable; never resend after an uncertain acknowledgement or reuse an ID for another attempt.

Required fields: `model`, `status` (`running`, `succeeded`, `failed`, `unknown`), `source` (`reported`, `estimated`, `unknown`), and public-safe `evidence` identifying the usage field/measurement method or why it is unknown. Numeric fields are `input_tokens`, `output_tokens`, `cached_input_tokens`, and `reasoning_output_tokens`; absent values are `None`, never guessed zero. Cached input and reasoning output are inclusive subcounts of the respective input/output totals. Normalize the chosen provider's documented semantics explicitly; do not add subcounts again. Preserve raw provider usage in private experiment evidence, not the public viewer.

`reported` requires counts actually observed from the provider/runtime and an evidence reference; `estimated` requires the tokenizer/estimation method and version; `unknown` requires all counts to be `None`. Preserve already reported counts on partial-stream failure. Reported cumulative values cannot be erased, downgraded to estimates, or decreased. If a provider emits token deltas, the project adapter must accumulate them before recording snapshots. A different endpoint/model identity convention must be resolved in `idea.md` before integration.

The dashboard totals each request's latest snapshot once, and separates reported and estimated counts. It shows unknown components explicitly and never presents a partial sum as a fully known total. Failed requests with known consumption remain included. Zero is shown only when explicitly supplied. Without registered requests, the panel says usage is not connected. Coverage is limited to instrumented calls; it cannot discover bypassed SDK calls, hidden retries or server-internal attempts.

## Minimal integration

This is an integration sketch: `configured_client_call` and the provider's usage extraction are project-specific. The caller must use the actual pinned SDK with retries disabled, preserve evidence, validate the response/stream completion, and test actual outbound attempts. These operations are not performed by `record_usage`.

```python
from research_progress import record_usage, stage

with stage(run_dir, "inference"):
    record_usage(run_dir, "inference", request_id, model=model_id,
                 status="running", source="unknown", evidence="Registered before outbound call")
    try:
        response = configured_client_call()  # Exactly the source-defined request.
    except Exception as error:
        try:
            record_usage(run_dir, "inference", request_id, model=model_id,
                         status="failed", source="unknown", evidence=type(error).__name__)
        except Exception as recording_error:
            error.add_note(f"Usage observation failed: {type(recording_error).__name__}")
        raise
    # Validate complete response and normalize usage using this provider's contract.
    # input_count/output_count are known counts or None; do not invent them.
    record_usage(run_dir, "inference", request_id, model=model_id,
                 status="succeeded", source=usage_source, evidence=usage_evidence,
                 input_tokens=input_count, output_tokens=output_count)
```

This non-streaming sketch has no previously reported partial usage. For streaming failure, retain those known cumulative fields in the terminal failed record. A valid completed response can have `source="unknown"` if usage is unavailable; this does not itself fabricate a scientific failure. Conversely, a successful usage report does not verify the content or method. Request failures/unknown outcomes stop new submissions on the execution track. A stage cannot succeed while any of its registered requests remains unfinished or unsuccessful. Records from already in-flight requests may still arrive after a failure; they cannot restart the stopped run. All fallible usage writes must finish before final atomic scientific publication.

## Parallel workers and command-runner boundary

Parallel producers use the existing authenticated collector: pass the same `collector=endpoint` to both `stage` and `record_usage`. The single writer validates and appends both kinds of event to the same journal. Requests are indexed by ID and cumulative totals are updated from each request's previous and new snapshots. The persistent writer and viewer read only newly appended events after their initial reconstruction; a standalone `show` still reconstructs the complete journal for inspection. Keep the plan and earlier journal records immutable.

The viewer checks the lightweight `/status` endpoint once per second. It retrieves `/state` and redraws the graph and Token panel on stage transitions, explicit batch/round `update` events, request failure/unknown outcomes, or supervisor observation changes. Successful per-request usage updates remain in the audit journal and appear in the panel at the next stage/progress boundary; they do not trigger a redraw individually. Independent branches update independently. A newly opened page shows the latest recorded state. Long stages may emit progress only at real, predeclared batch/round boundaries; no time-based progress is inferred.

An uncertain journal write preserves the writer lock and stops further writes, including after a process restart or cache eviction. Do not remove that lock to continue the experiment or resend an event; inspect the retained evidence and use a new run for any authorized new experiment. Partial journal tails produce an unavailable observation until the same append completes; truncation or replacement is rejected, never repaired or silently restarted.

The optional `run_research_workflow.py` remains a command supervisor and owns its journal. Do not let its children directly write that journal or start a competing collector. For token-instrumented pipelines, use the existing in-process stage/collector integration with the project's scientifically compatible scheduler. The command runner does not automatically intercept or import child usage. A project needing both must explicitly integrate usage forwarding through its single supervisor before claiming coverage.

The panel shows recent request details (up to 50), while all request snapshots remain in the journal. Never place API keys, authorization headers, raw prompts, private responses, or sensitive sample identifiers in public metadata. Use an opaque request ID and private evidence references. Preserve original exceptions if observation fails; no retry, fallback, truncation, sample exclusion, or guessed accounting.
