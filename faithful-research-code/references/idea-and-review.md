# Idea, concrete nodes, and independent review

## Establish the specification

Create project-root `idea.md` before writing research implementation, using the bundled template. Fill only evidence-backed facts; omit inapplicable sections with a reason. For an existing project, preserve developer decisions and distinguish desired behavior from observed code. Never turn existing behavior into an approved requirement merely because it already runs.

Give each scientific requirement a stable ID, for example `DATA-01`, `METHOD-02`, `EXP-01`, or `CHECK-03`. IDs remain stable when wording changes; do not reuse deleted IDs. Keep exact source locations and developer decisions alongside requirements. `idea.md` is the canonical specification record; README and graphs summarize or reference it. Tests and a graph are evidence about implementation, not authorities that can rewrite intent.

Ask concise questions about missing or conflicting dataset identities, split/preprocessing rules, equations, step order, baselines, ablations, metrics, thresholds, randomness, concurrency, and requested scope. State the alternatives and which nodes depend on the answer. Record the question as `OPEN` and the affected requirement as `BLOCKED`; do not substitute a recommendation, parameter default, exclusion, or elapsed waiting time for an answer. Record the actual reply and provenance when resolved. Known independent requirements may proceed. A document may be partially resolved; it must never label guesses approved. No separate approval ceremony is needed for choices the developer already specified.

Clarification blockage happens before dispatch: keep affected graph nodes pending with the open question in their description. The progress track's runtime `blocked` event is a sticky stop and is appropriate only when stopping that run. After resolving or changing a frozen plan, initialize a fresh progress run; never edit an existing journal to unblock or relabel it.

## Concrete workflow nodes

Before implementation, show the whole known plan including unresolved stages marked as such. Complete the affected portion after clarification and before its implementation. A generic “implement data loader” or “implement core algorithm” is only an overview, never sufficient as the reviewable task plan.

Each scientific node must have:

- a short label naming the actual operation and dataset/split or algorithm step;
- `idea_refs`: the relevant requirement IDs from project-root `idea.md`;
- `description`: concise inputs → operation/rule → outputs, exact source/equation, planned or actual code symbol, verification condition/test, and any unresolved question;
- actual dependencies, conditions, and loop/round boundaries.

For data stages, use the real dataset name, version, split, and required transforms from the supplied protocol. For algorithms, split causally distinct operations such as weight construction, normalization, estimation, and updates; name the actual rule instead of inventing those example steps for an unrelated method. Do not fabricate dataset names to make the graph look complete. Use “dataset unresolved — Q-01” until answered. Details belong in `idea.md` and the node description, keeping the graph label readable.

The live viewer renders requirement IDs and expandable descriptions as plain text. Mermaid snapshots carry short operation labels; link `idea.md` for detail. The viewer does not verify that IDs exist or that prose matches code: the implementing agent and independent reviewer must check these mappings. Do not put secrets or private records in viewer metadata.

Show parallel stages as separate branches and joins. Generation tasks may run concurrently after their shared interfaces and requirements are resolved; scientific execution requires separately declared concurrency and RNG rules. Never infer true independence merely from a visual layout. Progress colors represent observed execution status, not semantic approval.

## Prevent drift while working

Before each stage, read the referenced requirements and check its inputs, intended outputs, and acceptance conditions. On completing it, update the code/test coordinates and evidence status. Report a concise requirement-level difference if behavior diverges; do not hide it by renaming a graph node or editing the requirement to match the implementation.

For a proposed change, record old → new behavior, reason, affected IDs and downstream experiments, and authorization. If not already authorized by a clear developer instruction, ask and pause affected work. Update the current document only after resolution. Preserve the earlier text via version control or a retained snapshot and change record. Before result-producing execution, retain the exact `idea.md` version or copy and hash with the run's resolved config/code identity. Changed scientific choices get a new run identity; never relabel old results with the new idea.

README should link to the specification and show how to run the implemented method. Keep detailed scientific decisions in `idea.md`; do not maintain duplicate authoritative tables in multiple documents.

## Fresh independent review before handoff

After implementation and applicable local checks, create a new reviewing agent. It must not be the implementing agent or inherit that agent's claimed conclusions as evidence. Supply the current `idea.md`, original requests/decision records and source artifacts, code/config/tests, the changed scope, and locations of actual validation results. For an existing project, include a diff or file/hash change inventory. Request read-only review; the reviewer must not silently redefine requirements or edit the implementation.

Use this review brief, adapted to actual paths:

> Read the developer's requirements and original sources, then idea.md, then the actual implementation and relevant tests/configuration. Reconstruct the scientific path yourself. Check (1) idea.md faithfully records the request and unresolved choices, (2) every required operation is present with correct data, equations, order, randomness, failures, and experiment protocol, (3) every executable component serves a requirement, necessary validation, or genuine safety boundary, and (4) nodes, README, and claims match code and executed evidence. Inspect tests rather than trusting a passing summary. Report only actionable findings, each with requirement ID, evidence location, expected versus observed behavior, and consequence; if none, say “无”. Separately state review scope and unavailable evidence without inventing findings. Do not change files.

The implementing agent must verify each finding, fix actual defects, rerun affected checks, and request re-review of fixes plus their affected paths. Record reviewed idea/code versions or hashes, findings, resolution evidence, and remaining limitations in the existing verification report (or `review.md` when none exists). New semantic changes invalidate the affected review. Unresolved consequential ambiguity or drift prevents claiming the deliverable satisfies the idea.

If no independent-agent capability is available, finish authorized implementation/checks that remain possible, report “independent review not performed,” and identify the review material. Do not present self-review or a second prompt in the same agent as an independent review. Independent review reduces risk; it is not proof of scientific correctness or independent experimental reproduction.
