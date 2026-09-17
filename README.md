# amdluigi/skills

A modular [Agent Skills](https://agentskills.io) bundle that makes AI coding
agents follow a consistent software delivery lifecycle without repeatedly
prompting them for requirements, tests, security, review, or project context.

The repository ships one discoverable skill: [`sdlc`](skills/sdlc).

## Source and distribution

Development is maintained in the private authoritative `skills-internal`
repository. The public `skills` repository is a deterministic, one-way
distribution of the installable product, tests, sanitized evaluations, stable
documentation, and contribution guidance. These names preserve the existing
public project identity while moving full source history behind the private
boundary.

Public releases are prepared locally from an exact clean Git ref, verified,
and reviewed as a complete snapshot. The exported public verifier and snapshot
tooling do not authenticate, commit, push, or call GitHub. Private maintainers
use a separate one-command release wrapper whose final publication requires an
exact interactive confirmation or explicit non-interactive authorization.

Public contributions remain welcome. Maintainers review accepted changes into
the private source and include them in a later public export. The public
repository is never merged back as an authority. When present,
`RELEASE-MANIFEST.json` can be checked without private tooling:

```powershell
python scripts\verify_public_release.py
```

`PUBLIC-REPOSITORY.json` marks the public distribution. In a public tree its
presence makes `RELEASE-MANIFEST.json` mandatory, and repository validation
always invokes the standalone verifier. Removing both files does not bypass
verification because the marker itself is required.

SDLC coordinates by evidence rather than by tool identity. If another skill,
agent, human, or CI workflow already produced current proof for a lifecycle
capability, SDLC recognizes it and performs only the missing work.

## Repository documentation

- [Repository charter](docs/REPOSITORY-CHARTER.md): why the repository exists,
  what belongs in it, and the stability and acceptance promises.
- [Architecture](docs/ARCHITECTURE.md): how the orchestrator, modules,
  configuration, evidence, memory, and extensions work together.
- [Canonical language](CONTEXT.md): precise meanings for repository-specific
  terms.
- [Contributing](CONTRIBUTING.md): how to change modules, propose extensions,
  add evaluations, validate behavior, and prepare a focused pull request.
- [Architecture decisions](docs/adr/): major decisions that are difficult to
  reverse and surprising without context.
- [Specifications](docs/specs/): dated designs for substantial individual
  capabilities.

## What SDLC provides

`sdlc` is a compact orchestrator backed by internal modules:

| Module | Responsibility |
|--------|----------------|
| `project-memory` | Preserve architecture, decisions, rules, active context, and terminology |
| `project-standards` | Apply repository-specific stack and delivery policy |
| `change-contract` | Define one coherent outcome, acceptance criteria, non-goals, impact, and PR boundary |
| `prd` | Require an identifiable, approved product requirements document before new project and feature planning |
| `debugging` | Reproduce, localize, and fix root causes |
| `planning` | Plan the minimum complete change |
| `accessibility-browser` | Qualify changed rendered flows, assistive input, focus, responsive states, and browser or app runtime behavior |
| `performance-concurrency` | Establish budgets and measured performance, contention, resource, and correctness-under-load evidence |
| `observability` | Design and validate useful, bounded, privacy-aware logs, metrics, traces, and alerts |
| `api-compatibility` | Classify consumer-visible contract changes and prove version, transition, and mixed-consumer behavior |
| `data-migration` | Prove expand-contract sequencing, resumability, integrity, mixed versions, rehearsal, and recovery |
| `dependency-supply-chain` | Prove third-party necessity, provenance, reproducibility, advisory, license, and update risk |
| `tdd` | Enforce red, minimal green, and refactor for changed behavior |
| `implementation` | Deliver thin, verified, safe, independently reversible slices |
| `testing` | Own final acceptance coverage and verification |
| `security-auth` | Check security, authentication, and authorization risks |
| `operational-readiness` | Plan reversibility, rollout, observability, and post-change validation |
| `review` | Run risk-scaled independent review perspectives |
| `pr-handoff` | Inspect the final diff and prepare a human-readable readiness decision |
| `continuous-improvement` | Turn recurring process gaps into inactive, reviewable extension candidates |

Modules are ordinary Markdown references inside the skill, not separately
discoverable skills. The orchestrator first resolves project configuration,
then uses `modules/registry.json` to evaluate triggers, exit signals, and
existing evidence before loading only unresolved modules.

Project memory is bundled and enabled by default. When active, existing
`.sdlc/memory/` files are read before non-trivial work and updated when
durable knowledge changes. The module bootstraps that folder on the first
non-trivial task; trivial work does not gain unrelated scaffolding.

The six specialist domain modules are also enabled by default but remain
trigger-lazy. A backend-only change does not load accessibility guidance, a
cold refactor does not require performance evidence, and using an unchanged
locked dependency does not trigger supply-chain review. When several domain
triggers apply, each retains its own exit signal. Core requirements,
planning, TDD, implementation, testing, security, operational readiness,
review, and handoff ownership does not move into a domain module.

## Significant change discovery and planning

For a Significant change in an existing repository, SDLC presents a concise
discovery brief before asking the first clarification question. It identifies:

- evidence inspected and what it establishes;
- existing decisions and patterns;
- integration points and consumers;
- relevant constraints and technical debt;
- facts, assumptions, and unknowns.

For user-facing changes, the contract also identifies the target user and
benefit. User stories and product metrics are included only when they clarify
behavior or materially define success.

Significant plans describe task prerequisites and the interfaces or artifacts
each task consumes and produces. Shared contracts come first, independent
ownership surfaces can form conservative parallel groups, and integration
follows the group.

If implementation changes an accepted requirement, public contract, or
architecture decision, SDLC stops the current slice, updates the authoritative
design and project memory when selected, revises the plan, and marks dependent
evidence stale before continuing.

## Product requirements documents

New projects, new user/product-facing features, and Significant internal
capabilities require a durable PRD before planning or implementation. Bug
fixes, refactors, maintenance, and small internal utilities continue to use
the lighter change-contract path unless they become a new Significant
capability.

SDLC reuses any current PRD that satisfies the artifact contract, regardless
of its location or author. When the repository has no convention, the default
for a native PRD is:

```text
docs/prds/FEATURE_ID.md
```

A PRD identifies itself through `type: prd`, a stable feature ID, status, and
version. It defines the problem, users and benefit, outcome, goals,
non-goals, scenarios, numbered functional requirements and acceptance
criteria, data and authority concerns, constraints, conditional success
measures, open decisions, and approval evidence.

Draft PRDs cannot authorize planning. After explicit approval, planning maps
tasks to `FR-*` and `AC-*` identifiers, testing maps evidence to `AC-*`, and
the PR handoff reports the approved PRD version. Material product design drift
increments the PRD version, returns it to draft, stales dependent evidence,
and requires renewed approval.

The bundled deterministic helper validates PRD identity, every required
section, status, positive version, approval evidence, and `FR-*` to `AC-*`
mappings:

```powershell
python .agents\skills\sdlc\scripts\validate_artifacts.py validate-prd docs\prds\FEATURE_ID.md
```

Use `--allow-draft` only to check work in progress. Validation confirms the
artifact contract, not the quality or approval of product decisions.

### External specification reconciliation

A local generic specification, feature design, issue Markdown export,
structured JSON specification, or repository PRD in another location can
satisfy the same normalized contract without creating a competing document.
Inspection is read-only and grants no authority:

```powershell
python .agents\skills\sdlc\scripts\reconcile_artifacts.py inspect --project-root . --source docs\specifications\FEATURE_ID.md --kind generic-spec
```

Running `reconcile` explicitly nominates the source for direct authority.
Adding `--view` instead nominates the generated view as the sole SDLC
authority. Both write a draft sidecar and never edit the source:

```powershell
python .agents\skills\sdlc\scripts\reconcile_artifacts.py reconcile --project-root . --source docs\specifications\FEATURE_ID.md --kind generic-spec --report .sdlc\reconciliation\FEATURE_ID.json
python .agents\skills\sdlc\scripts\reconcile_artifacts.py reconcile --project-root . --source docs\specifications\FEATURE_ID.md --kind generic-spec --report .sdlc\reconciliation\FEATURE_ID.json --view docs\prds\FEATURE_ID.generated.md
python .agents\skills\sdlc\scripts\reconcile_artifacts.py reconcile --project-root . --source docs\specifications\FEATURE_ID.md --kind generic-spec --report .sdlc\reconciliation\FEATURE_ID.json --update
python .agents\skills\sdlc\scripts\reconcile_artifacts.py reconcile --project-root . --source docs\specifications\FEATURE_ID.md --kind generic-spec --report .sdlc\reconciliation\FEATURE_ID.json --replace --confirm-destructive-replace FEATURE_ID
python .agents\skills\sdlc\scripts\reconcile_artifacts.py validate --project-root . --report .sdlc\reconciliation\FEATURE_ID.json --require-approved
python .agents\skills\sdlc\scripts\reconcile_artifacts.py render --project-root . --report .sdlc\reconciliation\FEATURE_ID.json --output docs\prds\FEATURE_ID.generated.md
python .agents\skills\sdlc\scripts\validate_artifacts.py validate-prd --reconciliation .sdlc\reconciliation\FEATURE_ID.json --project-root .
```

The strict sidecar records location-based mappings, stable assigned `FR-*`
and `AC-*` IDs, missing fields, conflicts, superseded requirements, overlays,
source digest, and approval provenance. Reconciliation does not infer
requirements or approval. Unmapped fields, conflicting authority, stale
selectors, source drift, generated-view edits, and approval tied to another
version or digest block planning. Issue support consumes an existing local
export and never fetches or refreshes remote content.

## Test-first implementation

The default-enabled `tdd` module runs between planning and implementation for
new behavior and bug fixes. Each behavior requires an observed failing test,
the minimum implementation needed to pass, and refactoring only while green.
Tests exercise real behavior; mocks are limited to genuine external seams.
Code written before the red state is not accepted as TDD evidence.

Technical exceptions are limited to generated output, configuration-only
behavior, and unsafe reproduction. They require a concrete reason and the
strongest safe alternative evidence. Small behavior-preserving changes do not
trigger TDD.

TDD owns implementation order and sensitivity. The testing module separately
owns final acceptance coverage and verification, and can reuse the same
evidence when it satisfies both contracts.

## Validated plans and execution continuity

Plans tied to a native PRD identify its project-relative path, ID, and
approved version. Reconciliation-backed plans identify both the authoritative
artifact and report through `prd-artifact` and `prd-reconciliation`. Their
task table maps all `FR-*` and `AC-*` identifiers and states
prerequisites, consumed and produced interfaces, execution groups, and
verification. Validate before implementation:

```powershell
python .agents\skills\sdlc\scripts\validate_artifacts.py validate-plan docs\plans\FEATURE_ID.md --project-root .
```

Long plans can resume from a minimal cursor:

```powershell
python .agents\skills\sdlc\scripts\validate_artifacts.py cursor docs\plans\FEATURE_ID.md --project-root . --task TASK_ID --complete PREVIOUS_TASK_ID
python .agents\skills\sdlc\scripts\validate_artifacts.py cursor-status docs\plans\FEATURE_ID.md --project-root .
```

The cursor defaults under `.git/`, remains untracked, and contains no
timestamps, completion summaries, or coverage ledger. `--cursor` selects
another project-local ignored path.

## Operator reports and artifact contracts

Release 3.3 adds read-only operator commands to the existing helper:

```powershell
python .agents\skills\sdlc\scripts\validate_artifacts.py explain --input .sdlc\operator-state.json --detail normal
python .agents\skills\sdlc\scripts\validate_artifacts.py preview --input .sdlc\operator-state.json --detail concise
python .agents\skills\sdlc\scripts\validate_artifacts.py render-coverage --input .sdlc\operator-state.json --detail detailed
python .agents\skills\sdlc\scripts\validate_artifacts.py validate-handoff .sdlc\handoff.json --project-root .
```

`explain` reports why supplied module states were enabled, triggered, reused,
loaded, or skipped. `preview` projects instruction loading from supplied task
facts and ledger state. `render-coverage` emits deterministic coverage JSON.
They consume `contracts/operator-state.schema.json`; the caller must resolve
configured extensions before creating that input. Inspection never loads
`MODULE.md`, discovers artifacts, runs scripts, reads git state, or mutates
configuration. A prose-only extension trigger remains `undetermined` unless
the runtime supplies an assertion.

Core module entries carry a strict provider descriptor. For example:

```json
{
  "id": "testing",
  "source": "core",
  "configured": "enabled",
  "provider": {
    "type": "replacement",
    "id": "custom-testing-provider"
  }
}
```

The descriptor type is `bundled`, `disabled`, or `replacement`.
`replacement` requires the exact provider ID; the other types reject an ID.
Legacy schema-1 operator state may omit `provider`: enabled core modules then
default to `bundled`, while disabled core modules default to `disabled`.
Extensions cannot declare a provider. All three commands preserve the
normalized descriptor at every detail level without resolving or reading
provider instructions.

The normalized handoff contract is strict JSON described by
`contracts/handoff.schema.json`. `validate-handoff` checks only the supplied
packet and, when `--project-root` is present, its explicitly referenced local
PRD. It does not discover artifacts, execute evidence commands, inspect git,
render forge text, write an output file, or decide readiness.

Every new command accepts only local file paths. `--detail` is `concise`,
`normal`, or `detailed`. Concise reports retain blockers, failed or
unavailable evidence, stale evidence, and configured-disabled safeguards.
Successful machine reports use sorted, indented UTF-8 JSON and a final
newline. Structural validation always includes:

```json
{
  "contractValid": true,
  "semanticApproval": "not-assessed",
  "notice": "Structural validation does not approve product decisions, evidence quality, risk acceptance, or PR readiness."
}
```

That result does not approve product decisions, evidence quality, risk
acceptance, or PR readiness. Invalid input emits one bounded stderr line in
the form `error[E_CODE] JSON_POINTER: message`, with no success JSON:

- exit `2`: usage, unreadable input, invalid UTF-8, duplicate JSON keys, or
  malformed JSON;
- exit `3`: a well-formed artifact violates its contract;
- exit `4`: reserved for a local rendering failure in a later release.

The existing `validate-prd`, `validate-plan`, `cursor`, and `cursor-status`
command lines remain available. PRD and plan success payloads retain their
prior fields and add schema version, normalized details, and the semantic
disclaimer.

## Forge handoff rendering

Release 3.4 renders one validated handoff packet for GitHub, GitLab, or Azure
DevOps without contacting a forge:

```powershell
python .agents\skills\sdlc\scripts\validate_artifacts.py render-handoff .sdlc\handoff.json --forge github
python .agents\skills\sdlc\scripts\validate_artifacts.py render-handoff .sdlc\handoff.json --forge gitlab --template .gitlab\merge_request_templates\default.md
python .agents\skills\sdlc\scripts\validate_artifacts.py render-handoff .sdlc\handoff.json --forge azure-devops --output handoff.md
```

The default is Markdown on stdout. `--output` is the only renderer write and
requires an existing parent directory. Existing files require `--force`.
`--metadata-json` adds deterministic result metadata on stderr only when
Markdown goes to stdout; file output prints that metadata on stdout.

Templates are optional and never auto-discovered. A single
`<!-- SDLC:HANDOFF -->` line is replaced. With no marker, the complete
rendering is appended after two newlines. Multiple markers fail without
output. Template expressions are copied literally and never evaluated.

All inputs and destinations must be local filesystem paths. The renderer uses
no network, API, authentication, credential, remote, browser, git, publish,
open, update, approval, or merge operation. It preserves failed or unavailable
evidence and blockers and does not infer readiness.

## Configuring modules

All modules are enabled by default. On the first non-trivial task, SDLC creates
`.sdlc/config.json` from its bundled template when the file does not exist.
Commit this project-owned configuration so developers and agents use the same
module policy.

```json
{
  "schemaVersion": 3,
  "modules": {
    "project-memory": true,
    "accessibility-browser": true,
    "performance-concurrency": true,
    "observability": true,
    "api-compatibility": true,
    "data-migration": true,
    "dependency-supply-chain": true,
    "tdd": true,
    "testing": true,
    "review": true,
    "continuous-improvement": true
  },
  "extensions": {
    "project": {},
    "global": {}
  },
  "measurement": {
    "enabled": false
  }
}
```

The generated file lists all modules. Set a module to `false` to disable it,
leave it `true` for bundled instructions, or select one exact installed skill
as its instruction provider:

```json
"prd": {"replaceWith": "generic-prd-provider"}
```

Omitted known modules default to `true`, so bundle upgrades safely activate
new safeguards. Project and global extensions instead default to disabled and
must have an explicit `true` entry before SDLC considers them. Invalid values,
unknown module names, duplicate keys or provider assignments, and unsupported
schema versions stop execution with a configuration error.

Schema 1 and schema 2 configuration remain readable for upgrades. SDLC
normalizes either to schema 3 and writes the migration atomically before
provider or extension resolution. The migration preserves every explicit
module boolean and extension flag, adds omitted known modules as enabled, and
defaults measurement to disabled. Schema 3 module values are the strict union
`true`, `false`, or an object containing only a lowercase kebab-case
`replaceWith` ID. Unknown measurement fields and non-boolean `enabled` values
block.
Downgrading to Release 3.1 requires removing the six Release 3.2 keys or
restoring the earlier config because older bundles reject unknown module
names.

Enabled and loaded are different:

- **Enabled** means the module is eligible.
- **Triggered** means the current task needs it.
- **Loaded** means both are true, so the agent reads its `MODULE.md`.

Disabled and untriggered module files are not read. Every final response
discloses configured-disabled modules, even when the PR-handoff module itself
is disabled. Developers may disable every module; the orchestrator still
loads configuration and reports the resulting safeguard policy.

## Replaceable module providers

Release 3.7 can replace one core module's instructions with one installed
Agent Skill. Replacement does not change the core registry's trigger, order,
exit signal, evidence clauses, freshness, or readiness authority. A provider
must declare provider schema 1, compatibility with SDLC 3.7, and the core
module IDs it supports in string-valued frontmatter metadata.

The active host embeds the provider helper and injects a trusted adapter
object through the library API, outside caller-controlled CLI arguments. Its
`enumerate_providers(host_profile)` method returns a metadata-only candidate
document conforming to `contracts/provider-adapter.schema.json`, without
reading `SKILL.md` instruction bodies. Its `load_provider(load_token)` method
must atomically validate and consume that opaque token against current host
state, then return `contracts/provider-adapter-load.schema.json`. A host
integration invokes resolution and loading like this:

```python
resolve_status = provider_cli.main(
    [
        "resolve", "--project-root", project_root,
        "--registry", registry_path, "--host-profile", host_profile,
        "--sdlc-version", "3.7.0",
    ],
    host_adapter=trusted_adapter,
)
load_status = provider_cli.main(
    [
        "load-module", "--resolution", resolution_path,
        "--inspection", inspection_path, "--registry", registry_path,
        "--module", "prd", "--provider-context", context_path,
    ],
    host_adapter=trusted_adapter,
)
```

The host must enumerate exact declared IDs and provider metadata, report
duplicates across scopes, and bind a stable digest and load token. When load
is authorized, the library passes the bound token directly to
`load_provider`. Neither an adapter import path nor a load-result document is
accepted from CLI callers. Standalone provider resolution or loading reports
`provider-resolution-unsupported`; it never imports caller-named code or reads
provider instructions directly. Revoked, unknown, replayed, unloadable,
changed, fabricated, or identity-mismatched snapshots block without scope
precedence, direct filesystem access, or bundled fallback.
Provider instructions remain unloaded for untriggered or already-satisfied
modules. Provider results are reclassified against the unchanged core
evidence contract. Replacement providers are separate from approved
augmenting extensions and never enter extension resolution, promotion, or
packaging.

## Private local aggregate measurement

Release 3.6 adds optional process measurement with no telemetry. It is
disabled unless committed `.sdlc/config.json` contains:

```json
"measurement": {"enabled": true}
```

Chat prompts, environment variables, and command flags cannot grant consent.
There is no automatic collection. The orchestrator explicitly records only
closed counters for module, evidence, clarification, extension-transition,
and report-mode events. Optional monotonic phase intervals become one of six
fixed buckets: 1 second, 10 seconds, 1 minute, 10 minutes, 1 hour, and 24
hours. Longer intervals enter the final bucket. Exact durations, sums,
minimums, maximums, averages, and timestamps are never retained.

Projects with a regular `.git` directory use `.git/sdlc/metrics.json`.
Worktrees and submodules with a normal `.git` file use the project-confined
`.sdlc/local/metrics.json`. Other projects can use that local path only when
`git check-ignore --no-index` proves the exact
`.sdlc/local/metrics.json` file is excluded. This effective check honors rule
order, negation, nested files, and enclosing repository rules. If Git is
unavailable or cannot establish exclusion, recording fails closed rather than
using a partial ignore parser. Linked, reparse, and out-of-project store paths
are rejected. There is no user-global or cross-project store.

Run the helper from the installed skill:

```powershell
python .agents\skills\sdlc\scripts\manage_metrics.py status --project-root .
python .agents\skills\sdlc\scripts\manage_metrics.py configure --project-root . --enabled true
python .agents\skills\sdlc\scripts\manage_metrics.py configure --project-root . --enabled false
python .agents\skills\sdlc\scripts\manage_metrics.py inspect --project-root . --json
python .agents\skills\sdlc\scripts\manage_metrics.py record --project-root . --event module.reused
python .agents\skills\sdlc\scripts\manage_metrics.py record --project-root . --event phase.verification --duration-ms 1250
python .agents\skills\sdlc\scripts\manage_metrics.py reset --project-root .
python .agents\skills\sdlc\scripts\manage_metrics.py delete --project-root .
```

`status` never creates data. `inspect` returns the complete aggregate store
and remains available while disabled. `reset` requires a valid existing store,
zeros it, and increments a generation with no time meaning. `delete` removes
the store but leaves consent enabled, so later eligible events recreate it.
Disabling stops writes immediately but retains old data. To stop and erase,
disable measurement and then run `delete`.

The bundled `configure` command is the supported consent-change flow. It
atomically edits the project configuration under the same project-local lock
used for final metric replacement. Commit that explicit edit after running
the command. When `configure --enabled false` returns, earlier replacements
have finished and later bundled records observe disabled consent. Recording
also re-reads consent under the lock immediately before store access.

This atomic ordering applies to cooperating bundled `configure` and `record`
operations. A manual editor does not participate in the lock protocol, so no
atomicity claim is made for an arbitrary concurrent manual rewrite. Such a
rewrite is still honored by the under-lock recheck when it completes before
that check. Corrupt-store diagnostics use stable neutral classes such as
`store-corrupt:invalid-json`; stderr and result reasons do not expose project
or user paths.

The store contains no prompts, transcripts, responses, code, credentials,
raw paths, commands, repository or user names, task or revision identifiers,
evidence or module identifiers, model, host, or client identifiers, arbitrary
labels, or exact time values. Aggregate workflow volume may still be visible
to anyone who can read the local machine. Measurement failures are reported
separately and never affect SDLC trigger, evidence, status, or readiness
decisions.

## Reusing work from other workflows

SDLC does not detect or special-case installed skill names. It assesses
capabilities using inspectable evidence, so work from external skills,
another agent, a human, CI, or any other process is treated equally.

Accepted evidence must be:

- Inspectable rather than an unsupported completion claim.
- Aligned with the current outcome, acceptance criteria, and scope.
- Specific enough to satisfy the module's registry evidence contract.
- Current for the task, implementation revision, or final diff.

Each applicable module receives one status:

- `satisfied`: sufficient current evidence exists; do not load or repeat it.
- `partial`: preserve valid work and load the module only for gaps.
- `missing`: load the module and complete its work.
- `stale/unverified`: refresh evidence affected by later changes or lacking
  inspectable proof.
- `configured-disabled`: do not load it; disclose the omitted safeguard.
- `not-applicable`: its task trigger does not apply.

Implementation changes can stale tests, security analysis, review, and
handoff evidence. Scope changes can also stale planning. SDLC reassesses
dependent evidence instead of preserving a success label from an earlier
revision.

Every non-trivial final response includes a compact module coverage report
showing recognized evidence, remaining gaps, and actions taken. The report is
not persisted, because stored coverage state becomes stale easily.

## Incremental implementation

For multi-file and significant changes, the implementation module avoids one
large coding pass. It selects:

- **Vertical slices** by default, completing one observable path through all
  required layers.
- **Contract-first slices** when components or teams must progress
  independently.
- **Risk-first slices** when one uncertain assumption could invalidate later
  work.
- **Migration sequences** when old and new versions must coexist.

Each slice declares its outcome, exact scope, verification, user exposure,
and reversal path. It reaches a verified checkpoint before the next slice
begins and leaves the repository buildable and testable. Incomplete
user-visible work stays behind an existing feature flag or remains
unreachable. A checkpoint becomes a Git commit only when the user requested
commits or repository policy allows autonomous commits.

## How it triggers

The skill is model-invoked. Once installed, ask for a feature, fix, refactor,
or review normally. Its broad `description` tells compatible agents to load
it before coding; there is no command to remember.

Subagents do not reliably inherit loaded instructions. The orchestrator
passes the change contract, applicable module expectations, project standards,
and project-memory paths into delegated work.

## Adaptive extensions

SDLC can learn that a reusable process capability is missing, but it does not
learn code fixes, arbitrary commands, or every developer correction. At the
end of a non-trivial task, the `continuous-improvement` module considers
missing merge steps, workflow corrections, recurring review findings,
repeatedly added checks, blocked merge evidence, and recurring coverage gaps.
It first routes repository policy to `PROJECT-STANDARDS.md`, durable decisions
to project memory, activation choices to `.sdlc/config.json`, and behavior
already covered by a core module back to that module.

Only a reusable action with an observable trigger and inspectable exit
evidence becomes a candidate. Equivalent signals become eligible after two
occurrences in distinct tasks, or immediately when a developer explicitly
asks to make the behavior structural. Repeated reports within one task count
once.

Project-owned adaptive data is separate from the installed skill:

```text
.sdlc/
├── learning/
│   └── candidates.json
└── extensions/
    └── <extension-id>/
        ├── extension.json
        ├── MODULE.md
        └── evals.json
```

Candidate records contain sanitized summaries and minimal evidence
references. Draft extensions remain inactive. Before approval, SDLC presents
the recurring problem, why existing structures are insufficient, the
generalized trigger and action, safety and evaluation results, expected cost,
and rollback instructions. A developer must explicitly approve both the
extension and the configuration change that activates it.

### Inspect, reject, disable, or remove

The installed helper uses only the Python standard library. Set its path for
the client directory used by the project:

```powershell
$manage = ".agents\skills\sdlc\scripts\manage_extensions.py"
$extension = "verify-generated-output"
$candidate = "verify-generated-output"

# Inspect sanitized candidates and validate a drafted extension.
python $manage list-candidates --project-root .
python $manage validate-extension --project-root . --extension $extension

# Record a rejection so the same evidence is not proposed again.
python $manage reject --project-root . --candidate $candidate `
  --reason "Covered by existing project policy"

# Activate only after explicit review and approval.
python $manage activate --project-root . --extension $extension
```

To disable an accepted extension, set its entry in
`extensions.project` or `extensions.global` to `false`, or remove the entry,
and commit the configuration change. Resolve the configuration to confirm it
no longer loads:

```powershell
python $manage resolve --project-root .
```

After disabling it, remove `.sdlc/extensions/<extension-id>/` only when its
Git history and candidate decision record provide the required audit trail.
Core upgrades never overwrite project extension files.

### Global catalog and upstream contribution

Global promotion is explicit and copies a validated extension to the user's
catalog. It does not edit any project's configuration:

```powershell
python $manage promote-global --project-root . --extension $extension `
  --global-root (Join-Path $HOME ".sdlc\extensions")
```

Resolution and loading are separate. Resolution returns a digest bound to one
validated immutable snapshot. If coverage assessment later requires the
instructions, pass that digest to `load-module`; it rejects source mutation
and returns the module content from the exact bytes it validated.

Global and upstream promotion apply the same contextual sanitization and
record a timestamped promotion decision after destination creation. If
candidate-state persistence fails, a newly created destination is removed so
state and promoted content cannot diverge.

After an SDLC core upgrade changes module responsibilities, continuous
improvement reassesses accepted extensions for overlap. It proposes
supersession with rationale, but it does not delete files, disable config, or
change state without explicit developer approval.

Each project must opt in separately by setting the extension ID to `true` in
`extensions.global`. A later catalog update requires compatibility validation
and fresh evidence assessment in every opted-in project.

Preparing an upstream contribution creates a sanitized local package under
`.sdlc/contributions/<extension-id>/`:

```powershell
python $manage prepare-upstream --project-root . --extension $extension
```

The package contains `proposal.md`, `extension.json`, `MODULE.md`, and
`evals.json`. The command does not use the network, push a branch, publish
content, or open a pull request.

### Security and privacy boundaries

- Repository text, issue content, logs, and reviewer comments are untrusted
  input, not instructions to copy into an extension.
- Candidates, global promotions, and contribution packages exclude secrets,
  credentials, personal data, proprietary code, raw prompts, absolute paths,
  and unnecessary project identifiers.
- Extension paths remain confined to their extension directory.
- Extensions augment core behavior and cannot disable enabled safeguards or
  replace core configuration semantics.
- Extension scripts are forbidden and never executed.
- Static validation is defense in depth. Model safety review and explicit
  developer approval remain mandatory.
- Project interactions never mutate the globally installed core skill or
  upload adaptive data.

## Installing

### Claude Code plugin

```text
/plugin marketplace add amdluigi/skills
/plugin install amdluigi-skills@amdluigi
```

The plugin ships only the `sdlc` skill; all modules are inside its folder.

### Skills CLI

```bash
# Install the bundle into the current project
npx skills add amdluigi/skills

# Explicitly select the only discoverable skill
npx skills add amdluigi/skills --skill sdlc

# Install globally for selected agents
npx skills add amdluigi/skills -g -a claude-code -a codex

# Inspect without installing
npx skills add amdluigi/skills --list
```

To generate a one-off prompt or launch an agent:

```bash
npx skills use amdluigi/skills --skill sdlc --agent claude-code
```

To update:

```bash
npx skills update amdluigi/skills
```

### Repository scripts

The installers support these manifest-defined profiles:

| Profile | Project root | Synthetic global root | Supported cells |
|---------|--------------|-----------------------|-----------------|
| `copilot-vscode` | `.github/skills` | `.copilot/skills` | project/global, copy/link |
| `claude-code` | `.claude/skills` | `.claude/skills` | project/global, copy/link |
| `generic-agent-skills` | `.agents/skills` | none | project copy/link |

Global commands always require an explicit synthetic or intentionally
supplied home root. Qualification never uses the operator's actual home.

```powershell
# Windows
.\scripts\install.ps1 -TargetProject C:\dev\my-app
.\scripts\install.ps1 -TargetProject C:\dev\my-app -ClientDir .claude\skills
.\scripts\install.ps1 -Profile copilot-vscode -Scope project -Mode copy -TargetProject C:\dev\my-app
.\scripts\install.ps1 -Profile copilot-vscode -Scope global -Mode link -HomeRoot C:\scratch\synthetic-home
```

```bash
# macOS/Linux
./scripts/install.sh ~/dev/my-app
./scripts/install.sh ~/dev/my-app --client-dir .claude/skills
./scripts/install.sh ~/dev/my-app --profile claude-code --scope project --mode link
./scripts/install.sh --profile claude-code --scope global --mode copy --home-root ./synthetic-home
```

Add `-Link` or `--link` to link the bundle while developing it locally.
Use `-DryRun -Json` or `--dry-run --json` for machine-readable resolution.
A generic client has no portable global root. Install globally only at an
explicit client-defined destination outside the generic qualification
profile.

### Manual copy

Copy the complete `skills/sdlc/` folder. Do not copy only `SKILL.md`, because
the internal modules and templates are required.

```text
<project-root>/.agents/skills/sdlc/
```

Claude Code can instead use:

```text
<project-root>/.claude/skills/sdlc/
```

## Upgrading from versions before 2.0

Version 2.0 moves project memory inside the SDLC bundle and removes the
standalone `project-memory` skill.

1. Remove the old installed `.agents/skills/project-memory/` or
   `.claude/skills/project-memory/` skill folder.
2. Reinstall or update `sdlc`.
3. Keep the project's existing `project-memory/` data folder. The bundled
   module recognizes it as the legacy location so project knowledge is
   preserved.

## Upgrading the memory layout in 2.6

Version 2.6 stores committed project memory under `.sdlc/memory/` with the
rest of the project-owned SDLC metadata.

- If only `project-memory/` exists, the first non-trivial task moves the
  complete directory to `.sdlc/memory/`, verifies the contents, and reports
  the migration.
- If only `.sdlc/memory/` exists, SDLC uses it normally.
- If neither exists, the first non-trivial task bootstraps
  `.sdlc/memory/`.
- If both exist, SDLC stops for manual reconciliation and never merges or
  deletes either store automatically.

Commit the directory move so history follows the memory files. Trivial work
can continue using a legacy-only store and defer the migration.

## Project setup

On the first non-trivial task:

1. The orchestrator creates `.sdlc/config.json` when it is missing.
2. If enabled, the `project-memory` module creates `.sdlc/memory/` from its
   bundled templates when neither canonical nor legacy memory exists.
3. If enabled, the `project-standards` module proposes `PROJECT-STANDARDS.md` when it is
   missing.
4. Review the inferred content and commit the project-level resources so
   every teammate and agent receives the same context.

Never store secrets, credentials, raw sensitive data, or customer PII in
project memory.

## Repository structure

```text
.
├── README.md
├── AGENTS.md
├── CONTRIBUTING.md
├── CONTEXT.md
├── LICENSE
├── docs/
│   ├── REPOSITORY-CHARTER.md
│   ├── ARCHITECTURE.md
│   ├── adr/
│   └── specs/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── evals/
│   └── sdlc/
│       ├── cases.json
│       ├── evaluator-prompt.md
│       └── README.md
├── scripts/
│   ├── install.ps1
│   ├── install.sh
│   └── validate.py
├── tests/
│   ├── test_adaptive_extensions.py
│   ├── test_artifact_contracts.py
│   └── test_artifact_reconciliation.py
└── skills/
    └── sdlc/
        ├── SKILL.md
        ├── assets/
        │   └── sdlc-config.template.json
        ├── modules/
            ├── registry.json
            ├── project-memory/
            ├── project-standards/
            ├── change-contract/
            ├── prd/
            ├── debugging/
            ├── planning/
            ├── accessibility-browser/
            ├── performance-concurrency/
            ├── observability/
            ├── api-compatibility/
            ├── data-migration/
            ├── dependency-supply-chain/
            ├── tdd/
            ├── implementation/
            ├── testing/
            ├── security-auth/
            ├── operational-readiness/
            ├── review/
            ├── pr-handoff/
            └── continuous-improvement/
        └── scripts/
            ├── adaptive_extensions.py
            ├── config_contract.py
            ├── manage_extensions.py
            ├── manage_metrics.py
            ├── reconcile_artifacts.py
            ├── resolve_providers.py
            └── validate_artifacts.py
```

Each module uses `MODULE.md`. `modules/registry.json` is the single source for
module paths, triggers, exit signals, and evidence contracts. Module-specific
references and assets stay inside that module directory so a copied `sdlc`
folder remains self-contained.

## Evaluating changes

Behavior changes use the host-neutral pressure cases in
[`evals/sdlc`](evals/sdlc). Compare control and skilled runs using its blind
scoring contract.

Before release:

1. Run `python -m unittest -q` and require all deterministic tests to run.
2. Run `python scripts/validate.py` for release-neutral structural validation.
3. Run `python scripts/qualify.py verify-manifest` to verify the canonical
   bundle inventory and digest.
4. Exercise every manifest-required cell with repository-local synthetic
   roots. Copy and link installs must match the canonical bytes exactly.
5. Run the nineteen dedicated live cases five times for every required profile,
   sanitize the reviewed verdicts, and delete raw material.
6. Run `python scripts/qualify.py gate --release 3.7.0`. Missing host evidence,
   incomplete repetitions, and any critical failure block release.

The deterministic/live split prevents static installation checks from being
reported as model behavior. Retained summaries under
`qualification/results/3.7.0/` contain only schema-bounded IDs, versions,
model classes, statuses, booleans, and counters.

## License

MIT, see [LICENSE](LICENSE).
