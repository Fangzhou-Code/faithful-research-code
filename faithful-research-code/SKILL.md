---
name: faithful-research-code
description: Generates, audits, or packages concise scientific code traceable from equations and protocols through experiments, paper claims, and reported results. Use for reproduction, adaptation, ablation, simulation, training, data pipelines, evaluation, publication artifacts, or reviewer-facing releases when defaults, selection, statistics, or fallbacks could change conclusions. Does not weaken genuine security controls.
---

# Faithful Research Code

Treat research code as an executable scientific claim. Optimize for fidelity, causal transparency, and falsifiability rather than production-style availability.

Read [references/code-generation-contract.md](references/code-generation-contract.md) before generating or materially changing research code.

## Classify the research task

Choose one mode before planning:

- `EXACT_REPRODUCTION`: reproduce a source result without unapproved semantic changes.
- `SPEC_IMPLEMENTATION`: implement the supplied equations, algorithm, or protocol without claiming numerical reproduction.
- `ADAPTATION`: preserve named source components while making explicit authorized changes.
- `ABLATION`: change exactly the named factor while holding all other scientific factors fixed.
- `AUDIT`: inspect existing code for divergence without changing it unless requested.

Do not apply exact-reproduction requirements to an adaptation, or describe an adaptation as a reproduction. If the requested mode is unclear and changes the claim, ask or restrict the claim.

## Establish the scientific contract

Create a compact source-to-code table before implementation:

| Component | Required behavior | Source | Classification | Unknown/conflict | Code site | Observable invariant |
|---|---|---|---|---|---|---|
| loss, update, data, evaluation, or state step | equation, order, scope, timing | exact section, protocol, or user decision | defined/unknown | unresolved alternatives | planned symbol | assertion, test, or artifact |

Classify every material choice as:

- `METHOD_DEFINED`: required by the scientific method or source artifact.
- `PROTOCOL_DEFINED`: required by the dataset, environment, schema, benchmark, or evaluator.
- `USER_DEFINED`: explicitly authorized for this implementation or experiment.
- `UNKNOWN`: not recoverable from available evidence.

Do not impose a universal precedence when a paper, supplement, erratum, reference code, benchmark, or user request conflicts. Record the conflict and its scientific effect. Block when choosing a side could change the algorithm, data distribution, comparison, metric, or claim. Otherwise parameterize the alternatives and keep them out of unsupported claims.

## Model the complete research workflow

Before coding, express the method as an ordered workflow, including phases, rounds, loops, branches, and nested substeps. Include every stage that creates, transforms, selects, trains on, evaluates, or reports a scientifically relevant artifact.

For each stage, record:

| Stage/round | Purpose | Invocation/condition | Inputs | Rule and technical principle | Code site | Outputs | Downstream use | Failure behavior | Verification |
|---|---|---|---|---|---|---|---|---|---|

Explain the technical principle briefly but concretely: state how the source-defined operation transforms its inputs, why that operation is required by the method, and how its output is consumed. Avoid generic textbook background that does not help audit the implementation.

Expand hidden causal work into substeps. For retrieval, prompts, memory or sample construction, training, and evaluation, show the selection rule, data flow, and attachment of labels, rewards, or metrics. Show an exact source-defined prompt template when it is short; otherwise cite its code or artifact and show roles, variables, insertion points, retrieved context placement, expected output, parsing, and downstream use.

For iterative methods, identify round initialization, state carried between rounds, termination, and which artifacts each round reads and writes. After implementation, reconcile the planned workflow with the actual code. Record any difference as a conflict, unknown, or authorized semantic delta rather than silently updating the explanation.

Show the minimum usage path needed to run the method: top-level entry point or command, required configuration, stage order, and expected artifacts. Do not bury the scientific workflow in exhaustive option documentation.

## Trace claims to executable results

For experimental work, maintain a claim-to-artifact manifest. Include each main paper claim and every table or figure needed to support it; omit purely explanatory figures.

| Claim/result | Paper location | Exact command | Frozen config | Inputs and hashes | Seeds/runs | Raw output | Aggregation/plot | Expected result/tolerance | Status |
|---|---|---|---|---|---|---|---|---|---|

Generate tables and figures from retained raw outputs through explicit aggregation or plotting code. Never hand-copy a reportable value. Record excluded, failed, and incomplete runs and their effect on the denominator. A successful smoke test does not verify a paper result.

## Predeclare selection, statistics, and comparisons

Before result-producing execution, record the hyperparameter search space, search method, budget, validation data, selection metric, stopping rule, tie rule, checkpoint rule, and test-set access boundary. Do not select seeds, trials, checkpoints, thresholds, or metrics after observing the final test result unless this is the declared protocol.

For stochastic claims, predeclare the experimental unit, seeds or sampling rule, number of runs, estimator, an uncertainty measure appropriate to the claim or an explicit reason for omitting it, comparison design, failed-run handling, and acceptance criterion. Add effect sizes or significance tests only when the scientific claim requires them; define multiple-comparison handling when several inferential claims are made. In exact reproduction, preserve the source's primary reporting protocol and describe a missing uncertainty analysis as a limitation or separately authorized extension.

For every reported baseline, record its source, implementation identity, data and preprocessing, tuning and compute budget, checkpoint selection, evaluator, and any unavoidable mismatch. Do not describe a comparison as controlled when these claim-relevant factors differ.

## Enforce a zero-default semantic-change budget

Assume the semantic-change budget is zero unless the method, protocol, or user authorizes a deviation.

Maintain a semantic-delta ledger for every authorized difference:

| Delta | Authorization | Affected causal link | Expected effect | Isolation test | Claim limitation |
|---|---|---|---|---|---|

Include changes to equations, ordering, data membership, preprocessing, retries, repair, filtering, truncation, clipping, imputation, precision, device/backend, dependencies, evaluator, seeds, trial counts, aggregation, and checkpoint selection when they can affect results.

Do not silently implement `UNKNOWN`. Use one of `BLOCK`, `PARAMETERIZE`, `USER_DEFINED`, or `EXCLUDE`, and state the resulting claim boundary.

## Implement the minimum sufficient causal path

Map each contract component to one implementation site and verification mechanism. Trace inputs through scientifically relevant preprocessing, state transitions, sampling, actions, observations, labels or rewards, loss, updates, checkpoints, and metrics.

Prefer the smallest direct implementation that exposes this path. Do not add alternate algorithms, speculative abstractions, generalized extension points, compatibility branches, production orchestration, or unrelated improvements unless requested.

Require every new module, class, function, command, configuration option, and persistent artifact to map to at least one workflow stage, cross-stage data contract, verification need, or genuine safety boundary. Do not introduce generic managers, factories, plugin systems, wrappers, duplicate transformations, unused configuration knobs, or future-proofing without a present requirement. Keep validation, logging, and safety support minimal and non-semantic. Simplicity means that a reviewer can follow the scientific causal path directly, not merely that the code has fewer lines.

Preserve source-defined:

- equations, operation order, reductions, normalization, detach boundaries, shapes, dtypes, precision, schedules, and update timing;
- data identity, versions, split membership, ordering, filtering, trial counts, seeds, prompts, tokenization, sampling, and evaluator semantics;
- raw inputs and outputs separately from parsed, normalized, repaired, or executed representations;
- provenance for facts, assumptions, configuration, data, checkpoints, environment, and authorized deltas.

Raise a specific error when a required dependency, field, backend, model, checkpoint, task, trial, sample, or signal is missing. Never catch a failure and return a usable scientific artifact as though the requested path ran.

Treat retries, resampling, repair, clipping, truncation, filtering, imputation, fallback, or compatibility behavior as valid only when its source, activation conditions, attempt accounting, and effect are explicit and tested.

## Create the project README

For `EXACT_REPRODUCTION`, `SPEC_IMPLEMENTATION`, `ADAPTATION`, and `ABLATION` implementation tasks, create or update the project-root `README.md` as part of the code deliverable. Preserve unrelated existing content. In `AUDIT` mode, do not modify documentation unless requested.

Use [assets/research-readme-template.md](assets/research-readme-template.md) and the README contract in [references/code-generation-contract.md](references/code-generation-contract.md). Replace every placeholder with facts traceable to the source set and actual code. Do not invent motivation, novelty, contributions, commands, results, or supported configurations.

Write in the user-requested language; otherwise match the existing project documentation.

Require these sections:

- **Background**: scientific setting, problem, and scope.
- **Gap / Challenges**: source-grounded limitations or technical obstacles addressed by the method.
- **Method contributions**: the method's actual scientific contributions, distinguished from implementation or release contributions.
- **Code**: prerequisites and artifacts, separate main- and ablation-experiment instructions, concise parameter explanations, the complete as-implemented workflow, and a claim-to-result reproduction map.

Separate `Main experiments` and `Ablation experiments` with distinct commands or entry points, configurations, output locations, and claims. For each ablation, name the one intended changed factor and the factors held fixed. If no ablation exists, say so explicitly instead of fabricating one.

For every required or user-exposed parameter, state its value or default, source, experiment scope, operational role, and scientific effect. Do not enumerate internal library arguments that users cannot or need not set. Ensure all documented commands, flags, paths, defaults, and artifacts exist in the delivered code; label commands that were not executed as unverified.

When the deliverable supports a paper, benchmark claim, public release, or artifact review, also document the selection/statistical protocol, baseline parity, expected results and tolerances, compute requirements, licenses and access restrictions, known limitations, and immutable release identifier. Include ethics, privacy, consent, annotation, intended-use, or material AI-assistance disclosures only when applicable to the research or venue; do not fabricate compliance claims.

## Package a reviewer-executable artifact

For paper reproduction, public release, or artifact-evaluation tasks, provide the minimum package that lets a reviewer validate the claimed results:

- a frozen revision plus dependency lock or container recipe when environment drift can affect execution;
- a clean-environment setup check and a small smoke path distinct from full reproduction;
- one exact command per claimed result or a manifest-driven runner, with expected outputs and tolerances;
- data/model acquisition, versions, hashes, licenses, and access restrictions;
- estimated wall time, accelerator/CPU, memory, storage, network, and external-service cost for each result path;
- an artifact inventory, raw-to-report transformation path, and immutable archive identifier when publishing.

Do not add containerization, orchestration, download mirrors, or packaging machinery to a local specification-only task when they do not support its claim. Never label author-run evidence as independently reproduced. Maintain separate anonymous-review and archival-release instructions when the venue requires them.

## Separate safety from semantic substitution

Retain authentication, authorization, secret redaction, sandboxing, dangerous-operation approval, resource limits, corruption detection, atomic persistence, rollback before result commitment, and cleanup.

Prefer validation that rejects invalid state over logic that changes the experiment to continue. Allow representation normalization only when equivalence is demonstrated; retain the original value, record the transformation, and reject ambiguity.

Never use “safe,” “robust,” “compatible,” or “graceful” as authorization to change samples, values, control flow, capabilities, or metrics.

## Verify scientific behavior

Choose tests from the causal risk, not from software convention alone:

1. Test formulas, reductions, shapes, domains, gradients, state transitions, ordering, schedules, and evaluator behavior.
2. Add negative tests proving that missing or invalid required inputs fail before producing reportable artifacts.
3. Test split isolation, hidden-information exclusion, coverage, attempt counts, and aggregation denominators.
4. Compare with hand calculations, source examples, gold outputs, or reference implementations at matched checkpoints.
5. For stochastic claims, distinguish seed replay from distributional replication; use repeated trials and predeclared tolerances when the claim requires them.
6. For ablations, prove that only the named factor changes and that incompatible artifacts are not reused.
7. Capture dependency, hardware, precision, data, seed, and nondeterminism details only to the extent they can change the claim.

Grade evidence on independent axes rather than a false linear ladder:

- execution scope: `STATIC`, `LOCAL`, `END_TO_END`, `OFFICIAL_BENCHMARK`, or `INDEPENDENT_REPRODUCTION`;
- support type: `DETERMINISTIC`, `NUMERICAL`, `STATISTICAL`, or `QUALITATIVE`;
- artifact status, when relevant: `DOCUMENTED`, `FUNCTIONAL`, `REUSABLE`, and `ARCHIVED` as separate demonstrated properties.

Report the strongest demonstrated value on each applicable axis. `STATISTICAL` does not imply official benchmark coverage, and an author-run benchmark does not imply `INDEPENDENT_REPRODUCTION`.

After editing Python, run:

```bash
python <skill-dir>/scripts/audit_semantic_fallbacks.py <changed-path> [<changed-path> ...]
```

Use `--min-severity low` for heuristic candidates and `--json` for an audit trail. A source-authorized construct may use a line-local or immediately preceding directive:

```python
# research-fidelity: allow=RF301 reason="Equation 4 requires clipping to [-1, 1]"
value = value.clip(-1, 1)
```

Use suppression only with a specific scientific reason. The JSON report retains suppressed findings. Treat all findings as review leads, not automatic bugs; the Python auditor cannot prove semantic fidelity.

Manually audit non-Python causal surfaces, including YAML/TOML/JSON configuration, shell or scheduler launchers, notebooks, data-preparation scripts, result aggregation, and plotting code. Check resolved runtime configuration rather than assuming the declared file was used.

## Audit and report

Before completion, determine whether any failure path can emit data, checkpoints, success, or metrics; any missing capability can select another capability; or any repair, retry, filtering, truncation, clipping, precision, device, or compatibility path can alter provenance or aggregation.

Reconstruct and present the workflow that the completed code actually implements. Do not report only filenames or a high-level architecture. Show the ordered phases, rounds, nested steps, loops, branches, and artifact handoffs. Use a compact table such as:

| Phase/round | Module or entry point | Invocation and required configuration | Technical principle and implementation | Inputs -> outputs | How the output is used | Verification |
|---|---|---|---|---|---|---|

Expand any stage whose internal behavior can change the scientific result. Include prompt structure and retrieval usage when applicable. Explain supporting modules only when they transform scientific data or control flow, enforce an invariant, or provide a genuine safety boundary.

Report:

- task mode and strongest justified claim;
- the complete as-implemented workflow, with each stage's invocation, technical principle, code location, inputs, outputs, and downstream use;
- a concise module-responsibility map and confirmation that each retained component is scientifically or operationally necessary;
- the created or updated `README.md`, including grounded background, gap, contributions, separate main/ablation instructions, parameter roles, and the actual code workflow;
- the claim-to-artifact manifest, including exact commands, frozen configurations, raw outputs, aggregation or plotting paths, expected results, and execution status;
- hyperparameter/model-selection, statistical, and baseline-comparison protocols when they affect a reported claim;
- reviewer-facing artifact requirements, resource estimates, limitations, licenses, disclosure needs, and immutable release information when applicable;
- implemented components and their evidence;
- conflicts, unknowns, user-defined choices, exclusions, and semantic deltas;
- prohibited fallbacks removed and source-defined transformations retained;
- unnecessary features, abstractions, compatibility paths, and duplicate logic removed or deliberately excluded;
- validation actually executed, evidence coordinates reached, artifact status, and unavailable validation.

Never claim official, byte-exact, full, numerical, benchmark, or statistical reproduction without the corresponding artifacts and executed evidence.
