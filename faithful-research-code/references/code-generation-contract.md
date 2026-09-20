# Research code-generation contract

Use this reference to translate scientific specifications into executable code without changing their meaning.

Record this project's scientific contract in project-root `idea.md` before implementation. Follow [idea-and-review.md](idea-and-review.md) for active clarification, stable requirement IDs, concrete workflow nodes, authorized changes, and fresh independent-agent review. Keep original sources/developer decisions authoritative; README and graphs reference the same specification rather than creating competing requirements.

## Contents

1. Task modes and claims
2. Evidence inventory and conflicts
3. Source-to-code translation
4. End-to-end workflow and module map
5. Claim-to-result provenance
6. Selection, statistics, and baseline parity
7. Semantic-delta ledger
8. Semantic fallback test
9. Safety and operational boundaries
10. Verification design
11. Reviewer-executable artifacts
12. README deliverable contract
13. Evidence and reporting templates
14. API, concurrency, and random-stream controls
15. Statistical boundary conditions

## Task modes and claims

| Mode | Required fidelity | Permitted differences | Maximum claim before execution |
|---|---|---|---|
| `EXACT_REPRODUCTION` | All claim-relevant behavior matches the identified source set | Only source-defined or explicitly authorized deltas | Unexecuted reproduction attempt |
| `SPEC_IMPLEMENTATION` | Supplied equations, algorithm, and protocol are implemented | Unspecified architecture choices that do not change semantics | Method-faithful implementation |
| `ADAPTATION` | Named preserved components remain traceable | Explicit deltas recorded and tested | Adaptation, never reproduction |
| `ABLATION` | Baseline is held fixed except for the named factor | Exactly the declared intervention | Ablation implementation |
| `AUDIT` | Existing behavior is compared with the contract | No edits unless separately requested | Static or executed audit |

State the task mode before coding. A working program is not automatically a reproduction, and matching one reported number is not proof of method fidelity.

## Evidence inventory and conflicts

Inventory all applicable artifacts:

- user requirements and authorized decisions;
- main paper, appendix, supplement, errata, and released prompts;
- pseudocode, equations, diagrams, tables, and example calculations;
- reference code, commits, configurations, checkpoints, and environment manifests;
- dataset cards, schemas, split files, benchmark rules, and official evaluators.

For each scientific component, cite the exact artifact and location. Do not invent a universal source precedence: a benchmark may intentionally differ from a paper, and released code may contain undocumented behavior or bugs.

Use a conflict ledger:

| Conflict ID | Component | Source A | Source B | Observable difference | Claim impact | Resolution |
|---|---|---|---|---|---|---|

Resolve a conflict only through an explicit task definition, source clarification, or user decision. Actively ask about consequential unresolved choices, record the question in `idea.md`, and `BLOCK` dependent work until answered. `PARAMETERIZE` and `EXCLUDE` require explicit developer authorization; neither is a substitute for clarification. Already resolved independent work may continue.

Classify choices as `METHOD_DEFINED`, `PROTOCOL_DEFINED`, `USER_DEFINED`, or `UNKNOWN`. Do not call a customary choice method-defined without evidence.

## Source-to-code translation

### Equations and numerical operations

For every equation, record:

- the code symbol for every mathematical symbol;
- shape, dtype, device, valid domain, and units where applicable;
- parameter, observation, constant, mask, or cached-value roles;
- reduction axes and sum/mean/weighted/token/sample/batch semantics;
- normalization, clipping, and masking order;
- detach or stop-gradient boundaries;
- numerical precision and source-required stability operations;
- where the result enters the objective, state update, or metric.

Do not replace an inconvenient equation with a conventional approximation. Treat associativity changes, fused kernels, mixed precision, alternative solvers, interpolation, clipping, and epsilon additions as scientific choices when they can change results.

### Algorithms and state

Map pseudocode to executable order. Record:

- loop unit, initial state, and termination condition;
- state read before and written after each step;
- frozen versus trainable components;
- sampling-before-update and update-before-evaluation relationships;
- synchronous versus asynchronous behavior;
- optimizer, scheduler, EMA, target-network, and checkpoint timing;
- random-number generators, seed scope, stream reuse, and worker behavior.

Do not reorder steps for cleanliness or efficiency when order changes the causal process.

### Prompts, trajectories, and generated actions

Record exact roles, separators, templates, tool schemas, insertion points, visible context, prohibited information, tokenization, sampling configuration, raw tokens/text/log-probabilities, parsing, environment-consumed action, and reward/label attachment.

Never attach the original sample's reward, label, token IDs, or likelihood to a guessed, repaired, or reconstructed representation unless identity is demonstrated and the protocol permits it.

### Data and evaluation

Record:

- dataset identity, version, hashes, licenses, and split membership;
- inclusion, exclusion, filtering, deduplication, missing-data, and preprocessing rules;
- task coverage, failed-attempt accounting, number of trials, and randomization;
- evaluator identity/version, checkpoint selection, aggregation denominator, tolerance, and official metric definition;
- information allowed during training, selection, generation, and final evaluation.

Separate training, tuning, model selection, final evaluation, and reporting. Record when each split or label first becomes visible. Preserve the complete population of scheduled tasks and trials, including failures, exclusions, retries, and incomplete outputs, so denominators can be reconstructed.

Prevent held-out, evaluator-only, future, or answer information from entering earlier causal stages.

## End-to-end workflow and module map

Describe the method twice: first as the source-defined plan, then as the workflow the completed code actually implements. Reconcile them before making a fidelity claim.

### Workflow hierarchy

Represent the method at the level needed to expose scientific causality:

1. phases or experimental rounds;
2. ordered stages within each phase;
3. nested operations that transform or select scientific artifacts;
4. branches, retries, and termination conditions;
5. artifact edges showing which later stage consumes each output.

Use this planning and reporting template:

| Phase/round | Stage | Purpose | Invocation/condition | Inputs and provenance | Technical principle and source rule | Code symbol | Outputs/artifacts | Downstream use | Failure behavior | Verification |
|---|---|---|---|---|---|---|---|---|---|---|

The technical principle should answer three questions concisely:

- What transformation, selection, optimization, retrieval, or evaluation is performed?
- Why is that operation part of the specified method rather than an engineering convenience?
- How is its output used by the next stage or final claim?

Do not replace this with a directory tree or generic architecture diagram. A reader must be able to follow data and state from source inputs to reported metrics.

Give a minimal usage path for the complete method: required entry point or command, required configuration, execution order, expected intermediate artifacts, and final outputs. Document only options that affect the method or are necessary to run it.

### Prompts, retrieval, and constructed artifacts

When a stage constructs prompts, memories, examples, trajectories, labels, rewards, or fine-tuning records, report:

- the source and selection rule for every inserted item;
- ranking, filtering, positive/negative partitioning, and tie behavior;
- the exact prompt when practical, or a faithful structural template with roles, variables, separators, and insertion points;
- raw retrieved or generated content separately from parsed or normalized content;
- the parser and validity rule;
- where the resulting representation, label, reward, or metric is consumed.

### Iterative and round-based methods

For every round, identify initialization, inherited model/state, newly generated artifacts, update rule, evaluation point, checkpoint, and stopping condition. State whether data, memories, prompts, evaluators, or checkpoints are reused or regenerated. Unstated carryover is an `UNKNOWN`.

### Minimum sufficient module map

Retain a code component only when it serves at least one current role:

| Component | Required workflow stage or invariant | Why separate | Scientific inputs/outputs | Test or safety justification |
|---|---|---|---|---|

Avoid generic managers, factories, registries, wrappers, extension hooks, compatibility layers, duplicated transforms, unused options, and speculative utilities unless the current method or environment requires them. A helper is justified when it makes an invariant, shared data contract, or genuine safety boundary clearer; deduplication alone does not justify hiding the causal sequence.

Perform a final minimality audit:

- every retained executable component maps to the workflow or a real operational boundary;
- no unused or unreachable method path remains;
- no two components implement competing versions of the same scientific transformation;
- configuration exposes only choices that are supported and scientifically interpretable;
- logging and validation observe or reject behavior without changing it;
- the final workflow report matches actual entry points, calls, and artifacts.

## Claim-to-result provenance

Treat each reportable result as a derivation, not a copied number. Maintain a manifest:

| Claim ID | Paper table/figure/text | Method/baseline | Exact command | Frozen config | Input versions/hashes | Seeds/runs | Raw artifacts | Aggregation/plot code | Expected result/tolerance | Execution status |
|---|---|---|---|---|---|---|---|---|---|---|

Require one manifest row for each main claim and each result-bearing table or figure needed to support it. A row may reference several commands when the result is an aggregation, but every dependency must be explicit. Minor diagnostics may be grouped when they share one execution path and do not support distinct claims.

Preserve raw per-example or per-run results before aggregation. Generate reportable tables and figures through checked-in code. Record:

- the exact revision and configuration used;
- immutable identities for data, models, prompts, evaluators, and external services where available;
- scheduled, successful, failed, excluded, retried, and reported runs;
- aggregation order, denominator, weighting, rounding, and plotting transforms;
- the expected numerical range, qualitative trend, or tolerance and its justification;
- whether the command was unexecuted, smoke-tested, fully author-run, officially benchmarked, or independently rerun.

Do not reuse a raw artifact when its method, data, configuration, code revision, precision, or evaluator identity is incompatible. Do not hand-edit reportable outputs. If manual annotation or curation is method-defined, preserve the decision record and reviewer protocol.

Trace resolved configuration across YAML/TOML/JSON files, environment variables, shell or scheduler launchers, notebooks, and framework defaults. The configuration declared in documentation is not evidence until the executed process records the resolved values.

## Selection, statistics, and baseline parity

### Hyperparameter and model selection

Before final evaluation, record:

| Item | Required record |
|---|---|
| Search space | parameter names, candidate values or distributions, bounds, conditional branches |
| Search procedure | grid, random, Bayesian, manual, inherited, or source-defined procedure |
| Budget | configurations, trials, seeds, compute/time ceiling, early termination |
| Selection data | split identity and information visible during selection |
| Selection rule | metric, direction, aggregation, tie rule, and checkpoint rule |
| Test boundary | when final-test labels or metrics become visible and who may act on them |
| Outcome | all attempted configurations, failures, chosen configuration, and reason |

Treat seed selection, threshold choice, prompt choice, metric choice, checkpoint choice, and early stopping as model selection when they can improve the reported result. Never present a best-of-many result as a representative run. Any post-test adjustment is a protocol change and claim limitation unless the source explicitly defines an adaptive evaluation.

### Statistical protocol

For every stochastic or inferential claim, predeclare only the elements needed to support that claim:

- experimental unit and independence assumptions;
- population or condition being generalized to;
- seed list or sampling procedure and number of runs;
- primary estimand and aggregation order;
- uncertainty measure and interval construction, or a claim-specific reason for omission;
- paired or unpaired comparison design;
- failed, missing, censored, and outlier-run handling;
- effect size, hypothesis test, significance level, and multiple-comparison procedure when inferential language is used;
- acceptance criterion for reproduction, including numerical and practical relevance.

Report all scheduled runs. Distinguish variability across examples, trials, seeds, data splits, and hardware repetitions. Do not substitute standard deviation for uncertainty of the mean without saying so, and do not infer equivalence merely from a non-significant difference. In exact reproduction, keep source-reported primary statistics unchanged; label additional uncertainty analysis as an authorized extension and keep it out of the reproduction claim when it changes the protocol.

### Baseline parity

Use a baseline provenance table:

| Baseline | Source/commit | Published or rerun | Data/preprocessing | Tuning budget | Compute/model budget | Selection rule | Evaluator | Mismatch and claim effect |
|---|---|---|---|---|---|---|---|---|

Match claim-relevant conditions where the comparison is described as controlled. When exact parity is impossible, report the mismatch rather than silently improving or weakening either side. Separate published numbers from locally rerun numbers, and never mix their uncertainty or resource assumptions without qualification.

## Semantic-delta ledger

Assume no semantic changes are allowed until authorized. Record every authorized difference from the selected source baseline:

| Delta ID | Original behavior | New behavior | Authorization | Causal link | Expected effect | Isolation test | Claim restriction |
|---|---|---|---|---|---|---|---|

Include architecture substitutions, dependency or backend changes, device/precision changes, numerical transforms, data membership changes, retries, repair, compatibility behavior, evaluator differences, seed/trial changes, and unavailable components.

For an ablation, the ledger should contain the ablated factor and no unrelated scientific delta. If more factors change, describe a compound intervention instead of a clean ablation.

## Semantic fallback test

For every default, catch, retry, repair, alternate path, or compatibility branch, ask:

> Can this path produce an artifact or result that is consumed, trained on, evaluated, aggregated, or reported as though the requested method executed?

If yes, prohibit operational recovery: fail immediately, preserve evidence, and propagate an exception. Merely documenting, testing, logging, or authorizing a convenience fallback is insufficient. Only a step explicitly defined in the selected scientific algorithm/protocol before execution (including a user-designed method) can be retained as part of that method. Record its exact source, trigger, bounded attempt budget, original and transformed values, and denominator accounting. If the source conflicts with the user's no-retry requirement, block that component and resolve the scientific conflict; do not silently change the algorithm. A changed failure policy requires a new experiment identity and cannot inherit the original reproduction claim.

### Common prohibited patterns

- required backend, device, precision, model, or checkpoint unavailable → select another;
- dependency import fails → activate an alternate implementation;
- parser failure → guess, coerce, repair, or ignore malformed output;
- missing label, reward, likelihood, or state → use zero, `None`, empty data, or a heuristic;
- invalid/over-budget input → silently truncate, summarize, filter, clip, impute, or drop;
- failed sample, task, or trial → skip it and aggregate the remainder;
- official evaluator unavailable → report a proxy metric or execution success;
- broad exception → warn and return a usable partial result;
- failed generation → operational retry or resampling to obtain a successful output;
- old schema/configuration → run a compatibility algorithm with different semantics;
- unavailable accelerator → change precision, batch semantics, or algorithm to continue.

Prefer an error that names the violated invariant, expected and observed values, affected scientific component, and required recovery.

## Safety and operational boundaries

Retain controls that reject or contain failure without manufacturing scientific output or destroying evidence:

- authentication, authorization, secrets, sandboxing, and destructive-action approval;
- schema, type, shape, domain, dependency, version, coverage, and hash validation;
- resource ceilings that stop before committing a result;
- atomic result publication and corruption detection; retain incomplete files separately from committed results;
- transaction rollback only to prevent publication, while preserving available inputs, partial artifacts, raw outputs, attempt records, config, seeds, and traceback outside the transaction;
- release resources and locks, but never automatically delete, overwrite, or reuse failed-run evidence;
- explicit unsupported-mode errors;
- deterministic representation normalization with proven equivalence and retained originals.

Do not treat availability as safety. A fallback that keeps a service running but changes samples, numerical values, control flow, model capability, or metrics is a scientific semantic change.

Use a fresh run ID/output directory for a subsequent invocation. Never let a failed run enter successful-run aggregation or silently reduce the scheduled denominator. Capture failure evidence with secret redaction and applicable data access controls; a disk-full or logging failure must not replace the original scientific exception. Hard kills may leave a last-known running state; do not infer success or invent a traceback.

## API, concurrency, and random-stream controls

### External requests

Default to one application-level outbound attempt per declared sample and serial execution. Pin SDK/transport versions and disable retries at every layer: for example `OpenAI(max_retries=0)`, `Anthropic(max_retries=0)`, Requests adapters, urllib3 policies, HTTPX transport retries, cloud SDK retry configs, decorators, middleware, and any controllable proxy. Missing configuration or `None` is not proof of disabled retry. HTTP 429/5xx, timeouts, connection errors, and invalid responses must propagate; Requests/HTTPX callers must explicitly reject unsuccessful status codes (for example `raise_for_status()`). Do not regenerate output, switch models/providers, repair JSON, or drop samples after failure.

For each supported client, test against a deterministic local failing transport/server: 429, 500, timeout/connection failure, and malformed response. Assert exactly one outbound attempt, raised failure, preserved attempt identity, no downstream metric, and no next sample. Log requested/resolved model identity, SDK version, sampling parameters, sample/request ID, raw response or error, and observed attempts, without secrets. Service-side nondeterminism or retries beyond client control remain a stated limitation; client seeds do not prove server reproducibility.

Concurrency is not inherently invalid, and `asyncio.gather` preserves result order even though scheduling/completion order can differ. Default to serial. Enable concurrency only when the selected protocol predeclares its worker count, sample-to-stream mapping, dispatch/order constraints, deterministic aggregation, shared-state isolation, and failure propagation. On the first failure stop new submissions, cancel pending work where possible, record already in-flight work, and publish no result from the failed run. Never use `return_exceptions=True` to treat errors as observations. Threads used solely by the progress viewer are outside the scientific request path.

### Initialization and random streams

Set relevant `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, and other backend thread variables in the launcher **before any direct or transitive import** of NumPy/SciPy/Torch. Use protocol-defined values, not a universal value of one. Reject a conflicting inherited environment; `setdefault` alone does not enforce it. For an already initialized notebook/process, restart explicitly with the correct environment instead of claiming late assignments took effect. Verify and record effective thread pools and backend deterministic settings when claim-relevant.

Derive branch/replicate/worker RNGs from a recorded root and stable identifiers before execution; never inherit another branch's consumed global RNG. `SeedSequence.spawn()` is suitable with a frozen ordered branch registry and persisted spawn keys. Adding/reordering branches must not remap existing streams; explicit stable spawn keys are an alternative. Do not use Python's process-randomized `hash()` for seed derivation. Isolate bootstrap RNGs from training and data-split RNGs, and give each bootstrap replicate a stable identity. Preserve all relevant Python/NumPy/Torch/device RNG states for source-defined checkpoint restoration.

For paired ablations/common-random-number comparisons, create separate RNG objects initialized from the same declared stream identity for shared factors; use independent child streams only for factors intended to be independent. A universal rule assigning different seeds to every arm can itself break the comparison. Test running branch B alone and after A, and changing execution order, to verify B's intended randomness is unchanged.

## Statistical boundary conditions

For NumPy quantile/percentile calls, specify the source-defined `method` explicitly and freeze the dependency version, reduction axis, dtype, weighting, and missing-value policy. Do not silently choose `linear` when the source leaves the estimator unresolved. Older pinned versions may require an explicit `interpolation` argument instead: document that version-specific API; never implement exception-driven compatibility fallback. Explicit `method` removes estimator ambiguity but does not guarantee bitwise equality across versions/backends.

Before OPE or any weighted estimator, validate the domain prescribed by that estimator: sample count, finite rewards/weights, shape/alignment, behavior-policy support, and denominator. Check empty slices, zero/non-finite weight sums, and any estimator-specific negative-weight constraint. Preserve the source distinction between ordinary importance sampling (often divided by sample count) and self-normalized importance sampling (divided by weight sum); a zero weight sum is not universally undefined for all OPE estimators. Never add epsilon, clip weights, use `nan_to_num`, or report `0.000` to repair an undefined estimator.

Default: raise a specific error and stop before result commitment. Only when the reporting protocol explicitly defines structural non-estimability may reporting produce `{value: null, status: NOT_ESTIMABLE, reason: EMPTY_SLICE|ZERO_WEIGHT|..., n_scheduled: ..., n_observed: ...}` with a table label `NA`. This is a non-result, never a successful numeric observation or a recovery from an API/data failure. Keep it out of numeric aggregation without silently changing the planned population; report scheduled/valid/failed/non-estimable counts. Never serialize non-finite numbers as JSON NaN/Infinity. Test empty, zero-weight, invalid support, non-finite, and hand-computed valid cases.

## Verification design

Select the minimum tests that can falsify each claim-relevant link.

### Deterministic and reference tests

- hand-computed small cases for equations and aggregations;
- golden outputs from source examples at matched checkpoints;
- shape, dtype, unit, domain, and reduction assertions;
- gradient existence, absence, direction, and detach-boundary tests;
- state-transition and operation-order tests;
- negative tests for missing inputs and unsupported modes.

### Property and metamorphic tests

Use properties derived from the method, not generic expectations. Examples include permutation invariance only when defined, conservation laws, symmetry, monotonicity, scale behavior, idempotence, and equivalent-representation invariance.

Do not introduce a property merely because it is mathematically attractive; it must follow from the claim.

### Data, evaluator, and leakage tests

- exact split membership and disjointness;
- sample/task/trial coverage and denominator accounting;
- no hidden or evaluation-only information in earlier stages;
- failed-attempt and retry accounting;
- evaluator version, options, and checkpoint-selection behavior;
- provenance from raw inputs through transformed values to reported metrics.

### Stochastic and numerical tests

Distinguish:

- seed replay: same controlled environment and random streams;
- numerical agreement: predefined absolute/relative/ULP tolerances justified by the calculation;
- distributional replication: repeated trials, declared statistics, uncertainty, and acceptance criteria;
- benchmark replication: official trial counts, evaluator, aggregation, and coverage.

One successful seed does not establish a distributional claim. Exact bitwise equality is not required unless the task claims it; unexplained tolerance widening is not acceptable.

### Environment relevance

Record dependency versions, hardware, drivers, kernels, precision, deterministic settings, locale, threading, and data/checkpoint hashes when they can influence the result. Avoid production packaging work that does not strengthen the scientific claim.

Record model parameter count, wall-clock time, accelerator/CPU hours, peak device and host memory, storage, network use, and paid external-service cost when required to execute, compare, or assess the claim. Report energy or carbon estimates only when measured or calculated with a named method; do not fabricate precision.

## Reviewer-executable artifacts

Apply this section when the task targets a paper release, benchmark reproduction, public repository, or artifact evaluation. Do not impose it on a local equation-only implementation unless requested.

### Minimum package

- frozen source revision and immutable configuration snapshots;
- dependency lock, environment export, or container recipe proportionate to environment sensitivity;
- clean-environment setup validation and a fast smoke test clearly distinguished from result reproduction;
- one exact command per claim manifest row, or a manifest-driven runner with equivalent transparency;
- artifact inventory explaining code, data, checkpoints, prompts, raw results, logs, aggregation, plots, and generated reports;
- expected outputs, tolerances or qualitative checks, and explicit success criteria;
- required hardware/software plus estimated wall time, memory, storage, network, and external-service cost;
- acquisition instructions, versions, hashes, licenses, terms, and access restrictions for data and models;
- license and citation information for the released code and artifact;
- immutable public archive identifier when publication or long-term availability is required.

Do not require a full experiment to verify installation. Keep smoke, reduced, and full-result paths visibly separate; never use a reduced path to claim the full result. If cached or pretrained artifacts are supplied, state how they were produced, which results they support, and whether they replace an expensive stage.

### Release states

Distinguish:

- `LOCAL`: working research tree; no publication claim;
- `ANONYMOUS_REVIEW`: identity-bearing metadata and URLs removed as required, frozen at the submission revision;
- `ARCHIVAL_RELEASE`: authorship, license, citation, immutable revision, and permanent repository restored;
- `INDEPENDENT_EVALUATION`: reviewer instructions and results recorded separately from author-run evidence.

Never remove a third-party license or falsify provenance to anonymize a submission. Follow the target venue's current policy when it conflicts with a generic release convention.

### Data, people, and disclosure

When applicable, document data collection and annotation, annotator population and agreement, consent or review status, sensitive attributes, privacy controls, intended use, prohibited or risky use, dataset/model limitations, and access terms. Record material use of generative models or external APIs when a venue, institution, license, or scientific claim requires disclosure. The agent may prepare a disclosure record but must not assert ethical approval, consent, or legal permission without supplied evidence.

## README deliverable contract

Create or update the project-root `README.md` after the implementation and workflow reconciliation. Generate it from the actual source, configuration, commands, and artifacts, not from the initial plan alone. Preserve existing project information that remains correct.

Use the language requested by the user, or otherwise match the existing project documentation.

Use [../assets/research-readme-template.md](../assets/research-readme-template.md) as the structural starting point. Remove all placeholders and sections that are explicitly optional and inapplicable; retain the main and ablation headings, stating when no ablation is implemented.

### Scientific narrative

- **Background**: define the scientific problem, setting, inputs, outputs, and scope without turning the section into a general literature survey.
- **Gap / Challenges**: state only limitations or obstacles supported by the supplied sources or user decisions. Separate scientific gaps from engineering inconvenience.
- **Method contributions**: identify what the method adds scientifically and how each contribution addresses a stated gap. Distinguish inherited source components, authorized adaptations, implementation contributions, and unverified novelty claims.

Do not write “novel,” “first,” “state of the art,” or equivalent claims without supplied evidence. Do not present implementation cleanup, safety checks, or packaging as scientific contribution.

### Main experiments

Document the main experimental path separately:

- exact entry point or command and required configuration;
- required data, model, checkpoint, prompt, evaluator, and environment inputs;
- stage order and expected intermediate/final artifacts;
- output location and official metric or report produced;
- command execution status and achieved evidence coordinates.

Add a claim-to-result map that links every main result to its exact command, configuration, inputs, raw output, aggregation or plot code, expected result, and status. State which paper results are not reproducible from the delivered artifact.

### Selection, statistics, and comparisons

When applicable, include the hyperparameter/model-selection protocol, stochastic analysis plan, and baseline provenance table. Keep test-set access boundaries and failed-run accounting explicit. Do not list only the winning configuration.

### Ablation experiments

Document every ablation separately from the main experiment:

| Ablation | Main baseline | Single intended change | Held fixed | Command/config | Output location | Claim |
|---|---|---|---|---|---|---|

Use distinct outputs and compatible initialization artifacts. If an experiment changes more than one scientific factor, call it a compound intervention rather than a clean ablation. Never describe a configuration difference as an ablation unless its baseline and isolation are explicit.

### Parameters

Explain parameters concisely using:

| Parameter | Main value/default | Ablation value | Scope | Source | Operational role | Scientific effect |
|---|---|---|---|---|---|---|

Include parameters that users must set or that affect equations, data, sampling, optimization, state, retrieval, prompts, evaluation, randomness, precision, hardware-dependent semantics, or output selection. Group purely operational parameters only when they share one effect. Do not restate self-evident syntax or expose unsupported knobs.

Verify parameter documentation against argument parsers, configuration schemas, defaults, and call sites. A documented default that differs from runtime behavior is a scientific discrepancy.

### Code workflow and usage

Reuse the reconciled as-implemented workflow rather than writing a second inconsistent summary. Include phases, rounds, nested steps, entry points, technical principles, inputs, outputs, downstream use, failure behavior, and verification. Show prompt and retrieval structure when applicable.

Keep usage instructions minimal and executable. Every command must reference an existing entry point and supported flags. State prerequisites, working directory, required files, generated artifacts, and whether the command was actually run. Do not advertise examples, modes, datasets, backends, or automation that the code does not implement.

### README validation

Before completion, verify:

- background, gaps, and contributions are source-grounded;
- main and ablation experiments are visibly separated;
- each ablation has one declared change and isolated outputs;
- required/user-exposed parameters have concise roles and scientific effects;
- commands, flags, defaults, paths, and artifact names match the code;
- the workflow matches actual calls and artifact handoffs;
- unexecuted commands and unavailable results are labeled;
- each main claim, result table, and result figure maps to reproducible commands and raw-to-report code;
- tuning, checkpoint selection, stochastic aggregation, and baseline mismatches are disclosed when applicable;
- resource requirements, licenses, access restrictions, known limitations, and release identity are correct when publishing;
- no placeholder, unsupported feature, invented result, or project-external assumption remains.

## Evidence and reporting templates

Report evidence as coordinates, not a single promoted tier:

| Axis | Values | Meaning |
|---|---|---|
| Execution scope | `STATIC`, `LOCAL`, `END_TO_END`, `OFFICIAL_BENCHMARK`, `INDEPENDENT_REPRODUCTION` | What portion ran and who reran it |
| Support type | `DETERMINISTIC`, `NUMERICAL`, `STATISTICAL`, `QUALITATIVE` | What kind of conclusion the executed evidence supports |
| Artifact status | `DOCUMENTED`, `FUNCTIONAL`, `REUSABLE`, `ARCHIVED` | Separately demonstrated artifact properties; not an automatic ladder |

Use `INDEPENDENT_REPRODUCTION` only for evidence obtained by a person or team other than the authors. `STATISTICAL` does not establish official coverage; `OFFICIAL_BENCHMARK` does not establish distributional stability unless repeated-trial analysis was executed.

Final report:

| Field | Required content |
|---|---|
| Task mode | reproduction, implementation, adaptation, ablation, or audit |
| Implemented workflow | ordered phases, rounds, nested steps, artifact handoffs, and failure behavior |
| Usage path | minimal commands or entry points, required configuration, execution order, and expected artifacts |
| Technical principles | concise explanation of how each claim-relevant stage works and why it is method-required |
| Module map | code entry points, responsibilities, inputs/outputs, downstream consumers, and necessity |
| Prompt/retrieval flow | template or structure, selection rules, inserted context, parser, and use when applicable |
| README | grounded narrative, verified commands, separate main/ablation instructions, parameters, and reconciled workflow |
| Claim-result provenance | paper locations, commands, frozen configurations, raw outputs, aggregation/plot code, expected results, and status |
| Selection/statistics | search budget, selection boundary, stochastic analysis, failed-run handling, and baseline parity |
| Artifact package | environment, clean setup, resources, inventory, licenses, release state, and immutable identity when applicable |
| Source coverage | components and exact evidence |
| Conflicts/unknowns | unresolved items and chosen handling |
| Semantic deltas | authorized changes and isolation evidence |
| Fallback audit | prohibited, removed, retained, or unresolved paths |
| Minimality audit | unnecessary abstractions, options, compatibility paths, and duplicate logic excluded or removed |
| Validation | commands, artifacts, environments, execution scope, support type, and artifact status |
| Claim | strongest wording justified by executed evidence |

Never promote evidence across axes or omit failed, skipped, unavailable, or excluded components from the reported claim.
