# SDLC Skill Bundle

This context defines the canonical language used to describe the repository's
delivery model. It contains terminology only; behavior and implementation
belong in the charter, architecture, registry, modules, and specifications.

## Language

**Public code authority**:
The public `sdlc` repository where product code, tests, public
documentation, CI, versions, releases, and contributions are maintained.
_Avoid_: distribution mirror, generated repository

**Public contribution**:
A branch and pull request proposed directly against public `sdlc`, reviewed
and merged through public CI.
_Avoid_: contribution ingestion, reverse synchronization

**Private management context**:
Maintainer-only material that is not part of the installable product or its
user documentation.
_Avoid_: hidden product behavior, undocumented customer contract

**SDLC bundle**:
The complete installable package containing the orchestrator, core modules,
assets, and deterministic helpers.
_Avoid_: skill collection, independent skill pack

**Orchestrator**:
The discoverable `sdlc` skill that selects capabilities, reconciles evidence,
and coordinates readiness.
_Avoid_: master module, workflow script

**Core module**:
A bundled lifecycle capability with a registry-defined trigger, exit signal,
and evidence contract.
_Avoid_: sub-skill, plugin

**Replacement provider**:
One explicitly configured installed Agent Skill that supplies instructions for
a core module while the core registry and orchestrator retain trigger,
evidence, freshness, and readiness authority.
_Avoid_: replacement module, provider chain, automatic skill selection

**Domain module**:
A default-enabled, trigger-lazy core module that adds bounded specialist
analysis and evidence without taking ownership of the delivery lifecycle.
_Avoid_: always-on review, lifecycle replacement

**Module registry**:
The machine-readable source of truth for core module identity, order,
triggers, exit signals, paths, and evidence contracts.
_Avoid_: module list, routing table

**Project configuration**:
The project-owned policy that enables core modules and explicitly opts into
extensions or private local aggregate measurement.
_Avoid_: global settings, module registry

**Private local aggregate measurement**:
Disabled-by-default project-local counters and bounded duration buckets that
contain no content, identifiers, paths, timestamps, or cross-project data and
never influence lifecycle readiness.
_Avoid_: telemetry, analytics, activity log

**Trigger**:
Observable task or repository evidence that makes an enabled capability
applicable.
_Avoid_: prompt keyword

**Exit signal**:
The condition that indicates a capability's required work is complete.
_Avoid_: completion claim

**Evidence contract**:
The inspectable proof required to satisfy an exit signal.
_Avoid_: checklist, assertion

**Discovery brief**:
A concise evidence-based summary of the repository decisions, patterns,
integration points, constraints, facts, assumptions, and unknowns relevant to
a Significant change.
_Avoid_: repository tour, generic analysis

**Product requirements document**:
A durable, explicitly approved description of a new project's or feature's
problem, users, outcome, scope, numbered requirements, acceptance criteria,
constraints, open decisions, and approval.
_Avoid_: change contract, implementation plan, informal design note

**External requirements artifact**:
A durable local specification, design, issue export, structured file, or
repository PRD whose fields can be reconciled with the PRD evidence contract.
_Avoid_: remote issue, implicitly authoritative document

**Reconciliation report**:
A project-local sidecar that maps source locations into the normalized PRD
model and records authority, provenance, gaps, conflicts, supersession,
overlays, freshness, and approval binding.
_Avoid_: copied PRD, second requirements authority

**Generated PRD view**:
An explicitly nominated, reproducible canonical rendering whose source and
report remain provenance and whose generated regions are not edited.
_Avoid_: independently maintained requirements copy, automatic source rewrite

**Functional requirement**:
A numbered observable product behavior in a PRD, identified by an `FR-*` ID.
_Avoid_: implementation task

**Acceptance criterion**:
A numbered observable condition that proves one or more functional
requirements, identified by an `AC-*` ID.
_Avoid_: test command, completion claim

**TDD evidence**:
Inspectable proof that a real-behavior test was written and observed failing
for the expected reason before the minimum production implementation made it
pass, followed by any refactor while green.
_Avoid_: final test coverage, tests written after implementation

**Technical TDD exception**:
A recorded generated-output, configuration-only, or unsafe-reproduction
constraint with a concrete reason and the strongest safe alternative evidence.
_Avoid_: convenience waiver, small behavior change

**Dependency map**:
A plan view that states each task's prerequisites and the interfaces or
artifacts it consumes and produces.
_Avoid_: unordered task list

**Parallel group**:
A named set of tasks that can execute concurrently because they have complete
shared prerequisites and do not depend on each other's unfinished output.
_Avoid_: simultaneous edits, horizontal layer split

**Execution cursor**:
A minimal project-local, untracked record of a validated plan digest, current
task, and completed task IDs used to resume a long plan.
_Avoid_: coverage ledger, progress journal, timestamped completion log

**Design drift**:
A discovered difference between an accepted design and the behavior or
architecture now required for the change.
_Avoid_: routine implementation detail

**Coverage ledger**:
The ephemeral task-level assessment of each capability as satisfied, partial,
missing, stale or unverified, configured disabled, or not applicable.
_Avoid_: persistent status file, progress log

**Project memory**:
Version-controlled project knowledge containing architecture, decisions,
rules, active context, and domain terminology under `.sdlc/memory/`.
_Avoid_: chat memory, coverage ledger

**Learning signal**:
Evidence that a reusable process capability may be missing, such as a
recurring merge step or workflow correction.
_Avoid_: code bug, arbitrary suggestion

**Candidate**:
A sanitized project-local record of a possible reusable process capability
that has not yet become an active extension.
_Avoid_: active module, proposal

**Project extension**:
An approval-gated project-owned capability that augments core behavior.
_Avoid_: core module, automatic learning

**Global extension catalog**:
A user-level library of promoted extensions that remain inactive until each
project explicitly opts in.
_Avoid_: globally enabled extensions

**Contribution package**:
A sanitized local package prepared for upstream review without network,
publishing, or pull-request side effects.
_Avoid_: published extension, automatic pull request

**Coherent outcome**:
One observable improvement that can be understood and reviewed as a single
change, including all necessary cross-layer support.
_Avoid_: one-file change, smallest line count

**Minimum complete change**:
The smallest diff that safely delivers the coherent outcome with required
tests, documentation, compatibility, migration, and error handling.
_Avoid_: minimal code, partial implementation

**Verified checkpoint**:
A coherent implementation slice whose affected checks are current and whose
result can be continued or reversed safely.
_Avoid_: automatic commit

**PR-ready**:
A readiness decision supported by the active capabilities' current evidence
and a final repository-state inspection.
_Avoid_: implementation complete, tests probably pass

**Host profile**:
A stable manifest ID that defines one client's project and synthetic
user-global skill roots and its supported installation cells.
_Avoid_: inferred client name, operator machine

**Installation cell**:
One manifest-defined combination of host profile, project or global scope,
and copy or link mode.
_Avoid_: ad hoc destination

**Deterministic conformance result**:
A network-free result proving an installed bundle's structure and bytes in
repository-local synthetic roots.
_Avoid_: live-host behavior claim

**Live-host result**:
A sanitized summary of repeated model-visible discovery and behavior on one
host profile, tied to a client version, model class, skill version, and case
IDs.
_Avoid_: raw response, deterministic install result

**Sanitized qualification summary**:
The allowlist-reconstructed, schema-validated retained result containing only
bounded identifiers, statuses, booleans, and counters.
_Avoid_: redacted transcript, raw evaluator output
