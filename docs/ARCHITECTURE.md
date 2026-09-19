# Architecture

## Repository authority and collaboration

The public `sdlc` repository is the code authority. Product code, tests,
public documentation, CI, versions, releases, and contribution history are
maintained directly in this Git repository.

Changes follow an ordinary public lifecycle:

```text
Issue or proposal
  |
  v
Focused public branch
  |
  v
Tests and repository validation
  |
  v
Public pull request and review
  |
  v
Merge to public main
  |
  v
Optional public release tag
```

External contributors can fork, test, and propose changes using only public
content. Product behavior is defined by the installable bundle, its contracts,
and the user and contributor documentation in this repository.

Tracked text uses canonical LF line endings through `.gitattributes` so
qualification hashes remain stable across supported platforms.

## Overview

The repository ships one discoverable Agent Skill named `sdlc`. Its
`SKILL.md` acts as an orchestrator rather than containing every lifecycle
instruction directly.

The orchestrator combines four concerns:

1. Resolve project configuration.
2. Select applicable lifecycle modules.
3. Reuse current evidence and complete only gaps.
4. Produce a reviewable readiness decision.

When a change is actually released, `release-launch` owns the final release
decision, artifact verification, staged exposure, rollback triggers, and
post-release validation. When active production harm is in scope,
`incident-response` owns containment, evidence preservation, recovery
validation, and blameless follow-up. Both are trigger-lazy and complement,
rather than replace, operational readiness and debugging.

## Repository Components

```text
skills/sdlc/
├── SKILL.md
├── assets/
│   └── sdlc-config.template.json
├── modules/
│   ├── registry.json
│   └── MODULE_NAME/
│       ├── sdlc-capability.json
│       ├── MODULE.md
│       ├── REFERENCE.md
│       └── assets/
├── contracts/
│   └── strict input and result schemas
└── scripts/
    ├── adaptive_extensions.py
    ├── artifact_contracts.py
    ├── config_contract.py
    ├── manage_extensions.py
    ├── operator_reports.py
    ├── resolve_providers.py
    └── validate_artifacts.py
```

Only `SKILL.md` is discoverable as an Agent Skill. `MODULE.md` files are
internal references loaded by the orchestrator.

## Module Registry

`skills/sdlc/modules/registry.json` is the source of truth for where each
core module sits in the lifecycle:

- name;
- category;
- execution order;
- whether the module may be replaced.

Each module directory owns what it does. `sdlc-capability.json` beside the
module states identity, mode, instruction path, activation trigger, exit
signal, and acceptable evidence, using the same contract a third-party
provider satisfies. A registry row carrying those fields is rejected, and a
declaration carrying placement is rejected, so each field has one home.

A module is an interface and the skill serving it is an implementation.
Bundled implementations are named after the interface they serve, so
`sdlc-testing` is the implementation of `testing`. Binding an interface to an
implementation is a configuration decision, and
[the delivery profile](DELIVERY-PROFILE.md) reports the current binding for
every interface. The `sdlc-` prefix is reserved to the bundle, which is what
keeps a bundled name unclaimable by an external skill.

Named implementations are not separate release units. All of them ship in one
qualified bundle at one version.

It also declares the delivery phase layer:

- `deliveryPhases`, the ordered phases of software development;
- `categories`, mapping each category to one delivery phase and to the entry
  gate at which that category first participates.

Phase is a grouping and presentation layer above category. Resolution and
replacement happen per module, so a phase never binds a provider. A category
with a null gate sits outside the per-change state machine.

The default project configuration must list the same core module IDs. The
repository validator rejects registry, configuration, and filesystem drift,
including drift between the registry and the generated delivery profile at
`docs/DELIVERY-PROFILE.md`.

## Runtime Flow

```text
Load SDLC
  |
  v
Read registry metadata
  |
  v
Validate or bootstrap .sdlc/config.json
  |
  v
Resolve exact replacement providers and approved extensions
  |
  v
Evaluate triggers without loading instruction files
  |
  v
Build ephemeral evidence ledger
  |
  +--> satisfied / disabled / not applicable: do not load
  |
  +--> partial / missing / stale: load instructions and fill gaps
  |
  v
Reassess evidence after scope or implementation changes
  |
  v
Produce coverage report and readiness decision
```

## Project Configuration

Projects control activation through `.sdlc/config.json`.

Core modules default to enabled when a known key is omitted. Project and
global extensions default to disabled and require explicit project opt-in.
Schema 4 groups module states under the delivery phase that invokes them, so
the configured file names the lifecycle rather than presenting a flat list.
Phase membership is read from the module registry and is not configurable: a
module listed under a phase that does not own it is a configuration error,
because relocating a module to a less strictly gated phase would weaken a
safeguard without disabling it visibly.

Schema 4 gives each core module exactly one state: bundled instructions by
default, bundled instructions by explicit decision, disabled, or one exact
installed replacement provider. The two bundled states resolve identically
and differ only in whether the developer has decided. An undecided
capability with an eligible installed alternative is a question for the
developer; a decided one is not. Schema 1, 2, and 3 configurations migrate to
schema 4 without changing behavior, preserving every explicit decision.
Migration is persisted atomically before any provider or extension
resolution.

Configuration controls eligibility. Runtime triggers control applicability.
Evidence controls whether work remains. A module is loaded only when all
three conditions require it.

Invalid configuration blocks execution instead of falling back silently.

## Replacement Provider Boundary

Replacement providers supply instructions only. Core registry metadata remains
first-party and continues to control category, order, trigger, exit signal,
evidence clauses, freshness, and readiness. The provider cannot alter or
self-certify those contracts.

Four capabilities are never delegated. `change-contract`, `review`,
`operational-readiness`, and `pr-handoff` each render the judgment that
permits a change to advance, so serving one would let a provider authorize
its own progression. The registry declares this as `replaceable: false`, the
configuration schema accepts only a boolean for them, and normalization
refuses a replacement. They may still be disabled.

A provider is enumerated one of two ways, and both produce the same candidate
metadata for the same resolution.

The host may embed `resolve_providers.py` and inject a trusted adapter object
through the library API, outside caller-controlled CLI arguments. Its
`enumerate_providers(host_profile)` method performs metadata-only enumeration.

Alternatively a provider declares itself on disk in `sdlc-capability.json`
beside its own skill document, inside a directory supplied explicitly with
`--provider-root`. This needs no host support, which is what makes
replacement reachable in practice. Enumerating an explicit root is not
implicit discovery: only configured identities resolve, matching stays exact,
duplicate identities across roots block, a declaration claiming a core
capability name is refused, and an invalid declaration is skipped and
reported so one malformed directory cannot disable the lifecycle.

Each entry exposes exact declared Agent Skill identity, provider metadata, a
SHA-256 content digest, and an opaque load token independently of instruction
content. Resolution compares identity exactly, rejects zero or multiple
installed candidates, and validates provider metadata and compatibility
without reading the instruction body. A host that cannot enumerate exact IDs,
distinguish duplicates, or bind loading, and has no provider root, reports
`provider-resolution-unsupported`.

`resolve_providers.py survey` reports which provider serves each capability,
whether that is a decision or the default, and which installed alternatives
declare the same capability. It also reports where the capability is invoked:
its category, delivery phase, and phase entry gate, so a developer can judge
whether an installed skill covers the same ground. Placement is read from the
registry and never from a declaration, because a provider that could name its
own phase could claim one carrying no entry gate and so escape the evidence
gate governing the capability it replaces. The survey is read-only and adopts
nothing. Its eligibility check is the one resolution raises on, so it cannot
offer a choice resolution would refuse. The report shape is
`contracts/provider-survey.schema.json`.

The runtime evaluates the core trigger and evidence before loading provider
instructions. Satisfied and not-applicable modules load nothing. Only partial,
missing, or stale modules can authorize a load. The embedded library calls the
same trusted adapter's `load_provider(load_token)` method, which atomically
validates and consumes the token against current host state. Neither an
adapter import path nor a load-result document is accepted from CLI callers.
For a filesystem provider, the same `--provider-root` values re-read and
re-digest the declared document and refuse any change since resolution.
Provider resolution and loading that has neither a host adapter nor a
provider root fails closed as
`provider-resolution-unsupported`; it never imports caller-named code or
reads provider instructions directly. The adapter returns either the bound
snapshot or an explicit revoked, unknown-token, replayed-token, or unloadable
result. The orchestrator verifies the returned digest, exact identity, and
metadata, rejects an empty body, then gives the provider recognized evidence
plus unresolved core gaps. Its output is classified independently against the
unchanged core evidence contract. Unavailable, ambiguous, incompatible,
changed, failing, or incomplete providers block. Bundled fallback is never
attempted.

Replacement and augmentation are disjoint. Replacement configuration never
enters extension discovery, candidate state, promotion, or contribution
packaging. Approved augmenting extensions keep their own trigger and evidence
ledger entries. Existing conflict checks apply when both are relevant.

## Evidence Ledger

The coverage ledger is rebuilt for each task and is not persisted. Each
module or enabled extension receives one status:

- `satisfied`
- `partial`
- `missing`
- `stale/unverified`
- `configured-disabled`
- `not-applicable`

Evidence is judged by capability rather than producer identity. Current
specifications, plans, diffs, command results, CI results, and reviews can
satisfy a module regardless of who or what produced them, including a
provider this configuration did not select. Producing an artifact grants no
authority: it satisfies a capability only when it meets the registry
contract and does not provably contradict evidence already accepted for
another enabled module. A contradiction is resolved as a gap naming the
conflicting artifacts, never by preferring one producer over another.

Scope changes and implementation changes invalidate only dependent evidence.
This avoids rerunning unrelated lifecycle work.

## Core Modules

The registry currently includes:

- project memory;
- project standards;
- change contract;
- product requirements document;
- debugging;
- planning;
- accessibility and browser runtime qualification;
- performance and concurrency evidence;
- observability signal design;
- API compatibility;
- durable data migration;
- dependency supply-chain evidence;
- test-driven development;
- incremental implementation;
- testing;
- security and authorization;
- operational readiness;
- review;
- PR handoff;
- continuous improvement.

Module instructions are progressively disclosed. The registry metadata is
available before any module body is read.

The six domain modules sit contiguously after planning and before TDD. Their
order is deterministic but does not imply a dependency chain. Each is
default-enabled, evaluated from its positive trigger without reading its
instructions, and loaded only for a partial, missing, or stale evidence
contract. Repository technology alone is not a trigger.

Domain modules contribute specialist analysis and evidence. Change contract,
PRD, planning, TDD, implementation, testing, security-auth, operational
readiness, review, and handoff retain their lifecycle ownership. One artifact
may satisfy clauses in several modules, but each clause and exit signal is
assessed separately.

Domain evidence becomes stale only when its dependency changes: rendered
surfaces for accessibility, workload or concurrency behavior for performance,
signal semantics for observability, consumer contracts for API compatibility,
durable-state assumptions for migration, and dependency resolution or
provenance for supply chain.

## Significant Change Flow

Significant changes add three requirements to the ordinary runtime flow:

1. **Discovery brief**: repository evidence, existing decisions and patterns,
   integration points, constraints, facts, assumptions, and unknowns are
   summarized before clarification.
2. **Dependency-aware plan**: tasks state prerequisites and consumed and
   produced interfaces. Shared contracts precede conservative parallel groups;
   integration and cross-boundary verification follow them.
3. **Design synchronization**: when implementation changes an accepted
   requirement, public contract, or architecture decision, the authoritative
   design, project memory when selected, plan, and dependent evidence are
   synchronized before work continues.

User stories and success metrics are conditional product-discovery tools, not
universal lifecycle ceremony. The target user and benefit are required for
user-facing changes; additional artifacts are included when they clarify
behavior or define success.

## Product Requirements

The change contract defines the coherent boundary for every task. The PRD
module adds a durable product artifact for new projects, product-facing
features, and Significant new internal capabilities.

The PRD sits between change contract and planning:

```text
Change contract
  |
  v
Draft identifiable PRD
  |
  v
Resolve approval-blocking decisions
  |
  v
Explicit PRD approval
  |
  v
Traceable implementation plan
```

Native PRDs default to `docs/prds/FEATURE_ID.md` when no repository convention
exists. The frontmatter identity and content contract, not the path alone,
determine whether an artifact satisfies the module.

External specification interoperability separates a durable source, an
in-memory normalized model, a project-local reconciliation report, and an
optional generated view. Inspection grants no authority. Reconciliation
nominates either the source for direct authority or the generated view for
generated-view authority, never both. The report preserves source selectors,
deterministic IDs, missing and conflicting fields, superseded criteria,
overlays, provenance, and approval bound to the exact source digest. It is a
sidecar, not another requirements authority.

Planning maps tasks to numbered functional requirements and acceptance
criteria. Testing and handoff preserve that traceability. Product design drift
returns the PRD to draft and invalidates dependent evidence until approval is
renewed.

`reconcile_artifacts.py` locally inspects, reconciles, validates, and renders
the five supported source kinds. It never retrieves remote content or edits a
source. `validate_artifacts.py` applies one normalized PRD contract to native
and reconciliation-backed inputs. Plan validation retains `prd-path` and also
accepts paired `prd-artifact` and `prd-reconciliation` identity fields.

## Private Local Measurement Boundary

Aggregate measurement stays outside the evidence ledger.
Configuration parsing recognizes only `measurement.enabled`, defaults it to
false, and requires an explicit committed edit to enable writes. A prompt
cannot change consent. No orchestrator phase collects automatically.

`manage_metrics.py` re-reads configuration before every write and again under
the write lock immediately before store access. Its supported `configure`
operation replaces consent configuration under the same lock held through
final metric replacement. Disable completion is therefore the linearization
boundary: earlier replacements have completed and later bundled records
observe disabled consent. Arbitrary manual editors do not cooperate with this
lock and are not covered by that atomicity claim.

Projects with a regular `.git` directory store data under `.git/sdlc/`.
Worktree and submodule gitfiles use project-confined `.sdlc/local/`. Other
projects can use the same local path only when effective
`git check-ignore --no-index` evaluation proves the exact metrics file
excluded. This preserves enclosing rules, ordering, and negation. Unavailable
or indeterminate ignore evaluation fails closed. Both paths reject links and
reparse points. No user-global fallback or cross-project identity exists.

The strict version-1 store has a non-temporal generation, seventeen closed
counters, and five phase histograms with six fixed buckets. It has no string
values, timestamps, exact durations, arbitrary labels, paths, commands,
content, credentials, repository or user names, module or evidence
identifiers, or host, client, and model identifiers. Counters saturate rather
than wrap. Writes lock with bounded retry and atomically replace beside the
store.

Status is read-only. Inspection works while disabled. Reset keeps consent,
zeros aggregates, and increments generation. Delete removes the store but
does not revoke consent. Disabling immediately stops writes without silently
deleting history. Store errors are diagnostics only and cannot influence
trigger, evidence, status, extension eligibility, reconciliation, or
readiness. Their stable neutral classes do not contain absolute project or
user paths.

## Test-First Boundary

The `tdd` module sits between planning and implementation. For new behavior
and bug fixes it owns the observed red, minimal green, and refactor sequence,
including regression reproduction. It accepts only real-behavior tests, with
mocks at genuine external seams.

The testing module remains responsible for final acceptance coverage and
verification of the current revision. Evidence may satisfy both modules, but
their exit signals remain distinct. Behavior-preserving changes do not trigger
TDD.

Generated output, configuration-only behavior, and unsafe reproduction are the
only technical exception categories. Each requires a concrete reason and the
strongest safe alternative evidence.

## Execution Continuity

Long plans can use a minimal project-local execution cursor. By default the
helper stores it under `.git/`, outside tracked content. The cursor contains
the plan path and digest, current task, and completed task IDs. A changed plan
invalidates it. Alternate cursor paths must remain within the project and
should be ignored. The cursor never contains timestamps, narrative completion
summaries, or the coverage ledger.

## Project Memory

Project memory is a core module, not a separate discoverable skill. When
enabled, it maintains:

- project brief;
- architecture;
- decision history;
- concrete do/don't rules;
- active context;
- glossary.

The memory store lives at `.sdlc/memory/` in the installing project, not in
the global skill directory. This keeps committed SDLC-owned state together.
Trivial work can defer first-time scaffolding.

The legacy root `project-memory/` path remains readable for compatibility. A
legacy-only project migrates on its first non-trivial task. If both paths
exist, SDLC blocks for manual reconciliation rather than merging or deleting
memory implicitly.

## Adaptive Extensions

Continuous improvement observes recurring process gaps and routes each signal
to the narrowest existing structure:

- configuration for activation choices;
- project standards for repository policy;
- project memory for decisions and corrections;
- existing modules for already-covered behavior;
- a project extension candidate for a reusable missing capability.

Project extensions live under `.sdlc/extensions/`. They remain inactive until
validated, explicitly approved, and enabled in project configuration.

The deterministic helper manages strict JSON, candidate state, extension
validation, discovery, promotion snapshots, path confinement, and transaction
rollback. The agent remains responsible for generalization and safety review.

## Extension Discovery

The resolver reads only extension IDs explicitly referenced by project
configuration. It does not scan arbitrary Markdown for executable
instructions.

Project and global catalog extensions use the same validation contract.
Duplicate IDs with conflicting content, incompatible versions, invalid
metadata, path escapes, and unsafe linked directories block resolution.

Validated content is bound to an immutable snapshot and digest. Loading
rejects source mutation between validation and use.

## Promotion Boundaries

Global promotion copies an approved extension to a user catalog but does not
activate it in any project. Every project opts in separately.

Upstream preparation creates a sanitized local contribution package. It does
not invoke Git hosting APIs, push branches, publish packages, or upload
project information.

The globally installed core bundle is immutable from project interactions.

## Validation Architecture

Validation has three layers:

1. `scripts/validate.py` checks repository structure, registry/config
   consistency, manifests, documentation, and evaluation fixtures.
2. `tests/test_adaptive_extensions.py` checks deterministic helper behavior,
   state transitions, path security, promotion transactions, and migration.
Static checks are defense in depth. They do not replace independent review.

## Deterministic Reporting Layer

The orchestrator can serialize task facts and its ephemeral coverage ledger
to `operator-state.schema.json`. `explain`, `preview`, and `render-coverage`
strictly validate that caller-supplied state and return deterministic JSON at
concise, normal, or detailed levels. They do not rediscover evidence, resolve
extensions, inspect `MODULE.md`, execute extension scripts, or mutate project
state. Exact core fact rules may detect assertion conflicts; prose-only
extension triggers remain undetermined unless the runtime supplies a result.

Core ledger entries include a strict provider descriptor: `bundled`,
`disabled`, or `replacement` with its exact ID. The output schema requires
the descriptor at every detail level. Schema-1 state produced before Release
3.7 can omit it safely because enabled core entries normalize to `bundled`
and disabled core entries normalize to `disabled`; extension entries cannot
carry a provider. Reporting projects this metadata without reading provider
instructions or inferring readiness.

Native PRD and plan validators retain their established command lines and
fields while adding reconciliation-backed inputs, versioned result contracts,
and explicit semantic disclaimers.
The normalized handoff JSON is the stable producer-consumer boundary for
local forge renderers. The GitHub, GitLab, and Azure DevOps adapters are thin
projections over shared ordered Markdown sections, escaping, evidence
emphasis, and empty-value language.

Rendering validates the packet before producing any text. It writes Markdown
to stdout unless the caller supplies an explicit local output path, in which
case a flushed sibling temporary file is atomically moved into place.
Templates are explicit local UTF-8 inputs and use only the literal
`<!-- SDLC:HANDOFF -->` insertion marker. Their expressions are copied, never
evaluated. Renderers do not inspect remotes or forge configuration, read
credentials, invoke git, authenticate, publish, open, update, approve, merge,
or derive readiness.

## Host and Installation Qualification

Release qualification is repository tooling outside the installed bundle.
`qualification/manifest.json` owns the canonical bundle inventory, hashes,
three host profiles, installation support matrix, case IDs, and non-optional
gate policy. `scripts/qualify.py` implements strict runtime validation without
fetching its documentation-grade JSON Schemas.

```text
source bundle -> canonical manifest/hashes -> synthetic install matrix
             -> deterministic sanitized summaries ----+
live host -> blind evaluator -> local raw verdict      |
                         -> sanitizer -> summary -------+-> release gate
```

Deterministic conformance runs offline in repository-local synthetic project
and home roots. User-global qualification never selects or reads the
operator's actual home. Copy installs compare every byte. Link installs prove
one directory link targets the canonical bundle.

Live runs establish model-visible discovery and behavior. Raw host and model
material is ephemeral, ignored, reviewed locally, and never a repository
artifact. Sanitization is allowlist reconstruction, not redaction. Retained
summaries contain bounded IDs, versions, model classes, statuses, booleans,
and counters only.

Ordinary repository validation checks the manifest and any summaries that
exist. It does not infer unavailable host evidence. Per-cell inspection
reports only checks it performs. Mode-inapplicable and suite-level checks stay
`not-executed` unless separate suite evidence verifies them. The separate
release gate blocks on missing suite evidence, a missing required installation
cell, a missing project-copy live baseline, no supported live link result,
critical failure, stale version or digest, incomplete repetitions, or a
duplicate result.

## Installation

The repository scripts and supported package clients copy the complete
`skills/sdlc/` directory. A valid installation contains:

- one discoverable `SKILL.md`;
- the complete registry and module set;
- config and project-memory templates;
- deterministic extension-management scripts.

Source and installed file hashes can be compared during release validation.
Profile-based installers use the same manifest resolution rules and stage a
complete replacement. Existing positional project and client-directory calls
remain compatible.

## Trust Boundaries

The architecture separates:

- the replaceable installed core bundle;
- project-owned configuration, memory, candidates, and extensions under
  `.sdlc/`;
- the optional user-global extension catalog;
- sanitized upstream contribution packages;
- untrusted repository content used as learning input.

Crossing a boundary requires explicit configuration, validation, approval, or
promotion. No boundary uses implicit last-writer-wins behavior.

## Evolution

New universal lifecycle behavior should normally become:

1. an addition to an existing core module;
2. a new core module when it has an independent trigger and exit contract;
3. a project extension while its generality is still being proven.

The architecture should remain one discoverable skill unless a future ADR
deliberately changes that product boundary.
