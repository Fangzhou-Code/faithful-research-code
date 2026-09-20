# <Research idea / project>

Replace placeholders with source-backed facts. Mark unanswered choices OPEN/BLOCKED, ask the developer, and do not implement dependent work. Omit inapplicable sections with a reason. This document records scientific intent; observations and successful tests do not authorize changes to it.

## Problem and scope

- Task mode and research question: <problem, motivation and source>
- Hypothesis / supported claim: <claim to test, not a fabricated result>
- Inputs → intended outputs: <scientific objects>
- In scope / non-goals: <requested functionality and explicit exclusions>

## Sources and developer decisions

| Source/decision ID | Exact source location or developer statement | Version/date | Requirements affected |
|---|---|---|---|

## Requirements and implementation map

Use stable IDs such as DATA-01, METHOD-01, EXP-01, CHECK-01. Classification is METHOD_DEFINED, PROTOCOL_DEFINED, USER_DEFINED, or UNKNOWN. Status is RESOLVED or BLOCKED; track implementation/verification separately.

| ID | Required behavior | Source / classification | Status / open question | Workflow nodes | Planned/actual code symbols | Check and evidence status |
|---|---|---|---|---|---|---|---|

## Data and boundaries

| Requirement ID | Dataset identity/version/hash or acquisition requirement | Split/membership | Schema, units and access | Ordered preprocessing | Forbidden leakage / missing-data rule |
|---|---|---|---|---|---|

## Method, step by step

| Requirement ID / step | Inputs and state read | Exact equation/rule and source | Outputs and state written | Dependencies, branches, loops/stopping | Failure rule | Verification |
|---|---|---|---|---|---|---|

Specify initialization, shapes/reduction axes, operation order, RNG streams and their stable derivation, and concurrency when relevant. Expand causal substeps; “core algorithm” is insufficient. Cite exact prompt templates and parsing rules when applicable.

## Experiments and acceptance

| Experiment ID | Main/baseline/ablation and hypothesis | Method/data requirement IDs | Changed factor / fixed factors | Seeds, trials, tuning and test access | Metric, denominator and boundary rules | Acceptance criterion / source | Command/config and outputs |
|---|---|---|---|---|---|---|---|

Declare uncertainty, paired comparisons, quantile estimator, baseline parity, and failure accounting where relevant. Unknown thresholds or protocols are questions, not conventional defaults. State explicitly if no ablation was requested.

## Workflow

<Separate complete generation and scientific execution diagrams. Concrete node labels; requirement IDs and input → rule → output details. Show parallel dependencies/joins, loops, and verification stages. Include independent code review before handoff. Reference the project progress plan instead of duplicating its full detail.>

## Questions and conflicts

| Question ID | Missing/conflicting information and source | Alternatives / scientific effect | Affected requirements/nodes | Status | Actual developer reply / decision source |
|---|---|---|---|---|---|

## Authorized changes

| Change ID | Old → new behavior | Reason / affected requirements and claims | Authorization source | Isolation check / evidence | Earlier specification version |
|---|---|---|---|---|---|

Do not retroactively rewrite requirements to bless drifting code. Retain old run specifications and failed evidence.

## Evidence and review links

- Claim-to-result manifest and executed checks: <paths; distinguish planned from executed>
- Run binding: <retained idea.md revision/copy + hash, code identity and resolved config>
- Independent review: <report, reviewed versions, findings/fixes/recheck; or not performed>
- Remaining questions, deviations and limitations: <actual unresolved items or none>
