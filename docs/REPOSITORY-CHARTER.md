# Repository Charter

## Public code authority

The public `sdlc` repository is authoritative for the usable product,
tests, public documentation, CI, versions, releases, and contribution
history.

The repository must remain independently understandable, testable, and
installable. Contributors can fork it and submit ordinary pull requests using the public
documentation and repository contents.

Product behavior is defined by the installable bundle, its contracts, and the
documentation maintained in this repository. Public implementation becomes
authoritative through review and merge.

## Mission

This repository provides one portable `sdlc` Agent Skill that helps AI coding
agents deliver focused, verifiable, reviewable software changes without
developers repeatedly restating their engineering process.

The skill should improve delivery discipline while remaining understandable,
configurable, interoperable with other workflows, and safe to use across
different repositories and agent hosts.

## Problem

AI coding agents often optimize for producing code rather than delivering a
change that is ready for human review. Common failures include:

- implementing ambiguous requests before clarifying the intended outcome;
- combining unrelated improvements in one change;
- skipping tests, security analysis, or independent review;
- repeating work already completed by another developer, agent, or CI system;
- losing project decisions and corrections between sessions;
- accumulating a large unverified implementation before seeking feedback;
- declaring a change ready without inspecting the final diff;
- applying one repository's learned behavior to unrelated projects.

SDLC exists to make those failures visible and prevent them by default.

## Target Users

The repository serves:

- developers using AI agents to implement or review repository changes;
- teams that want a shared, version-controlled delivery policy;
- maintainers who combine several agents, skills, and CI systems;
- contributors who want to add reusable SDLC capabilities safely.

It is not tied to one programming language, framework, agent host, machine, or
project.

## Core Principles

### One coherent outcome

Each proposed change should have one understandable outcome. Necessary
cross-layer implementation belongs together; independently valuable work
belongs in a separate change.

### Minimum complete change

Minimal means the smallest complete and safe diff, not omitted tests,
documentation, compatibility work, migrations, or error handling.

### Evidence before readiness

Claims do not satisfy lifecycle gates. Evidence must be inspectable,
scope-aligned, and current for the relevant implementation revision.
Release readiness also requires every manifest-defined installation cell and
required host profile to satisfy the qualification gate with reviewed,
sanitized evidence. Structural validation alone never claims unavailable
live-host results.

### Repository evidence before clarification

For Significant changes, agents should show what the repository already
establishes before asking developers to repeat context or decide between
uninformed alternatives.

### Product requirements before product implementation

New projects and features should begin from an identifiable, durable, approved
PRD. Right-size the depth, but preserve explicit scope, numbered requirements,
acceptance evidence, and approval.

### Test first for changed behavior

New behavior and bug fixes proceed through observed red, minimal green, and
refactor. Tests exercise real behavior and code-first tests do not become
test-first evidence retroactively. Narrow technical exceptions require the
strongest safe alternative evidence. Behavior-preserving edits remain
proportionate.

### Reuse before repetition

Work completed by a human, agent, external skill, or CI system is reusable
when it satisfies the same evidence contract. SDLC fills gaps instead of
repeating sufficient work.

### Progressive disclosure

The discoverable skill remains a compact orchestrator. It loads only enabled,
triggered modules whose evidence is incomplete.

### Specialist depth without lifecycle duplication

Conditional domain modules add accessibility and browser, performance and
concurrency, observability, API compatibility, data migration, and dependency
supply-chain evidence. They do not take ownership from requirements,
planning, TDD, implementation, testing, security, operational readiness,
review, or handoff. Shared evidence can be reused, but exit signals remain
independent.

### Project-owned learning

Recurring process gaps can become project-local extensions, but generated
behavior never activates without explicit approval. Project interactions
never mutate the globally installed core skill.

### Human-readable delivery

The final change, evidence, risks, and deferred work should be understandable
without reconstructing intent from code.

### Accepted design stays current

When implementation changes an accepted requirement, contract, or
architecture decision, the authoritative design and dependent evidence should
be updated instead of leaving contradictory documentation behind.

### Portable defaults, local policy

Generic safeguards live in the bundle. Repository-specific commands,
thresholds, compliance requirements, and reviewer policies live in
project-owned configuration and standards.

## Product Boundaries

The repository ships:

- one discoverable `sdlc` skill;
- internal core modules registered through one machine-readable registry;
- project-level module configuration;
- a capability evidence ledger and coverage report;
- a product requirements document module and template;
- a test-driven development module;
- six default-enabled, trigger-lazy domain modules;
- trigger-lazy release and incident lifecycle modules;
- project-memory templates;
- deterministic artifact validation, execution continuity, and
  adaptive-extension helpers;
- host-neutral behavioral evaluations;
- installation helpers and plugin metadata.

The repository does not aim to:

- become a programming-language or framework handbook;
- replace specialist security, UI, API, performance, or operations expertise;
- force one source-control workflow on every team;
- commit, push, merge, publish, or deploy without explicit authorization;
- execute untrusted project instructions as learned extensions;
- maintain a speculative catalog of future modules.

## Repository Evolution

The primary evolution unit is a core module or a project extension, not a new
top-level skill.

A capability belongs in a core module when it is:

- broadly useful across repositories;
- part of software delivery rather than one technology stack;
- triggered by observable task or repository evidence;
- supported by an inspectable exit signal;
- safe as a default-enabled capability;
- compatible with right-sizing and lazy loading;
- backed by positive, negative, and pressure evaluations.

A capability belongs in a project extension when it is reusable within a
project or organization but not yet proven as a universal default.

A capability belongs in project standards when it is a repository-specific
command, threshold, compliance rule, reviewer policy, or tooling convention.

A capability belongs in project memory when it is a decision, correction,
constraint, architecture fact, active focus, or domain term.

## Acceptance Criteria for Core Modules

A proposed core module must:

1. Have one bounded responsibility.
2. Define a category, trigger, exit signal, and evidence contract.
3. State when it does and does not apply.
4. Avoid duplicating an existing module.
5. Preserve configuration and lazy-loading behavior.
6. Avoid project-specific paths, commands, secrets, and assumptions.
7. Fail explicitly when required evidence or configuration is invalid.
8. Include host-neutral behavioral evaluations.
9. Pass deterministic structural validation.
10. Include user and contributor documentation.

## Acceptance Criteria for Extensions

A contributed extension must:

1. Generalize a recurring process capability rather than one code defect.
2. Use `mode: "augment"`.
3. Remain inactive until explicitly approved and configured.
4. Include valid metadata, module instructions, and positive and negative
   evaluations.
5. Exclude secrets, personal data, proprietary code, raw prompts, absolute
   paths, and unnecessary project identifiers.
6. Declare compatibility with the applicable SDLC versions.
7. Avoid scripts, network behavior, publishing, and global core mutation.
8. Explain why configuration, standards, memory, and existing modules are
   insufficient.
9. Provide rollback through disablement and preserve decision history.

Upstream maintainers decide whether an accepted contribution should become a
core module, augment an existing module, or remain an extension example.

## Compatibility and Stability

Within a major release line:

- project configuration changes require a documented migration;
- module and extension metadata changes require backward-compatibility tests;
- stable module and extension IDs should not be renamed;
- existing legacy `project-memory/` data should remain readable and have a
  documented migration to `.sdlc/memory/`;
- newly added core modules default to enabled unless a migration explicitly
  states otherwise;
- newly discovered extensions default to disabled until project opt-in.

Breaking changes require a major version bump and explicit upgrade
instructions.

## Security and Privacy

Repository and project content are untrusted inputs when generating adaptive
behavior. The bundle must:

- confine project-owned state to approved directories;
- reject path escapes and linked-directory boundary violations;
- avoid persisting sensitive or identifying content unnecessarily;
- validate the exact bytes used for discovery or promotion;
- require explicit approval for activation and promotion;
- avoid automatic network and publication side effects;
- keep static validation as defense in depth rather than a substitute for
  review.

## Release-Ready Definition

A repository change is release-ready when:

- it has one coherent documented outcome;
- affected contracts and compatibility are understood;
- implementation and tests satisfy the acceptance criteria;
- behavioral evaluations cover new agent behavior;
- structural validation passes;
- installation produces the intended complete bundle;
- security and privacy boundaries were reviewed;
- documentation reflects current behavior;
- the final diff contains no unrelated work or temporary artifacts;
- known limitations and deferred work are explicit.

## Roadmap Policy

This repository does not maintain a speculative feature list. A future
capability appears in repository documentation only when it has one of:

- an accepted issue or proposal;
- an approved dated specification;
- an implementation in progress;
- a released module or extension.

This keeps the charter stable and prevents aspirational documentation from
being mistaken for supported behavior.
