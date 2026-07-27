# <Method or project name>

## Background

<Define the scientific problem, setting, inputs, outputs, and scope from supplied evidence.>

## Gap / Challenges

- <Source-grounded scientific gap or challenge.>
- <Explain why it affects the target problem or evaluation.>

## Method contributions

- <Scientific contribution and the gap it addresses.>
- <Distinguish inherited method components, authorized adaptations, and implementation contributions.>

## Scope and limitations

- **Supported claim/scope:** `<what this implementation can establish>`
- **Known limitations or unimplemented components:** `<source-grounded boundaries>`
- **Intended use and material risks:** `<include only when applicable>`

## Code

### Requirements and artifacts

- **Working directory:** `<path>`
- **Frozen code revision:** `<commit or archive identifier>`
- **Environment:** `<lockfile, environment file, or container recipe>`
- **Required data:** `<identity, version, hash, license/access, and expected location>`
- **Required models/checkpoints:** `<identity, version/hash, license/access, and expected location>`
- **Generated artifacts:** `<locations and meanings>`
- **Resources:** `<accelerator/CPU, memory, storage, network, expected wall time and external cost>`

### Quick validation

```bash
<clean-environment setup or smoke-test command>
```

- **Purpose:** `<installation/shape/data-path validation; explicitly not full reproduction>`
- **Expected output:** `<observable success condition>`
- **Status:** `<executed with evidence coordinates, or unverified>`

### Result reproduction map

| Claim/result | Paper location | Method/baseline | Exact command/config | Inputs + hashes | Seeds/runs | Raw output | Aggregation/plot | Expected result/tolerance | Status |
|---|---|---|---|---|---|---|---|---|---|
| `<claim>` | `<Table/Figure/section>` | `<identity>` | `<command/config>` | `<versions>` | `<policy>` | `<path>` | `<script>` | `<value, range, or trend>` | `<evidence coordinates>` |

### Main experiments

```bash
<exact main-experiment command>
```

- **Inputs:** `<required inputs>`
- **Outputs:** `<intermediate, raw, and final artifacts>`
- **Metric/evaluator:** `<official identity, version, definition, and output>`
- **Expected result:** `<predeclared numerical tolerance or qualitative trend>`
- **Status:** `<execution scope + support type + artifact status, or unverified>`

#### Main-experiment parameters

| Parameter | Value/default | Scope | Source | Operational role | Scientific effect |
|---|---|---|---|---|---|
| `<name>` | `<value>` | `<main/round/stage>` | `<method/protocol/user>` | `<how code uses it>` | `<what causal link or result it can change>` |

#### Hyperparameter and model selection

| Item | Protocol |
|---|---|
| Search space and procedure | `<values/bounds and grid/random/inherited/manual rule>` |
| Budget and stopping | `<configurations, trials, seeds, compute, early stopping>` |
| Selection data | `<split identity and visible information>` |
| Selection rule | `<metric, direction, aggregation, ties, checkpoint>` |
| Test boundary | `<when final-test information becomes visible>` |
| Attempt record | `<location of all attempted, failed, and selected configurations>` |

#### Statistical protocol

- **Experimental unit/population:** `<unit and generalization target>`
- **Seeds/runs:** `<predeclared list or sampling rule and count>`
- **Estimator and aggregation:** `<including denominator and order>`
- **Uncertainty/comparison:** `<interval, pairing, effect size/test if required>`
- **Failed/missing runs:** `<predeclared treatment>`
- **Acceptance criterion:** `<numerical, statistical, or practical criterion>`

#### Baseline parity

| Baseline | Source/commit | Published or rerun | Data/preprocessing | Tuning + compute budget | Selection | Evaluator | Mismatch/claim effect |
|---|---|---|---|---|---|---|---|
| `<baseline>` | `<identity>` | `<status>` | `<conditions>` | `<budget>` | `<rule>` | `<identity>` | `<none or limitation>` |

### Ablation experiments

<State explicitly if no ablation is implemented. Otherwise give each ablation a separate subsection.>

#### <Ablation name>

```bash
<exact ablation command>
```

| Item | Description |
|---|---|
| Main baseline | `<main configuration/checkpoint>` |
| Single intended change | `<one scientific factor>` |
| Held fixed | `<data, seed policy, training, selection, evaluator, and other factors>` |
| Output location | `<isolated artifact directory>` |
| Claim | `<bounded ablation claim>` |

#### Ablation parameters

| Parameter | Main value | Ablation value | Operational role | Scientific effect |
|---|---|---|---|---|
| `<changed name>` | `<main>` | `<ablation>` | `<how code uses it>` | `<isolated intervention>` |

### Code workflow

| Phase/round | Module or entry point | Invocation/configuration | Technical principle and implementation | Inputs -> outputs | Downstream use | Failure behavior | Verification |
|---|---|---|---|---|---|---|---|
| `<stage>` | `<symbol>` | `<how to invoke>` | `<how it works and why the method requires it>` | `<artifacts>` | `<consumer>` | `<fail-fast or source-defined behavior>` | `<executed check>` |

#### Prompt, retrieval, or constructed-data flow

<When applicable, show selection/ranking rules, prompt roles and variables, inserted context, parsing, labels/rewards, and downstream use. Remove only when inapplicable.>

### Artifact release and validation

- **Release state:** `<LOCAL / ANONYMOUS_REVIEW / ARCHIVAL_RELEASE / INDEPENDENT_EVALUATION>`
- **Artifact inventory:** `<path to inventory or concise list>`
- **License and citation:** `<code/data/model licenses and citation>`
- **Immutable archive:** `<DOI, Software Heritage ID, or explicitly unavailable>`
- **Commands actually executed:** `<commands>`
- **Execution scope:** `<STATIC/LOCAL/END_TO_END/OFFICIAL_BENCHMARK/INDEPENDENT_REPRODUCTION>`
- **Support type:** `<DETERMINISTIC/NUMERICAL/STATISTICAL/QUALITATIVE>`
- **Artifact status:** `<DOCUMENTED/FUNCTIONAL/REUSABLE/ARCHIVED as demonstrated>`
- **Unavailable or unverified checks:** `<explicit limitations>`
- **Applicable disclosures:** `<ethics, consent, privacy, annotation, external API or material AI assistance; evidence only>`
