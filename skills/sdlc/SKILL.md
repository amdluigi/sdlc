---
name: sdlc
description: 'Use when creating, modifying, debugging, fixing, or reviewing code, including work likely to become a pull request, before implementation begins. Also use when scope is unclear, a request bundles outcomes, verification or review might be skipped, delegated coding needs guardrails, project context must persist, or a change affects production data, rollout, rollback, or public contracts. Skip only for answers that do not change code.'
license: MIT
metadata:
  category: process
  architecture: modular
  version: "1.0.0"
---

# SDLC

Act as a disciplined senior engineer. For every task that creates, modifies,
fixes, debugs, or reviews code, select and orchestrate the modules below.

**Default outcome:** produce one reviewable change with one coherent outcome,
the minimum complete diff needed to achieve it, durable project context, and
fresh evidence that it is correct and safe. Explicit configuration can remove
those safeguards; always disclose the configured-disabled modules.

## Gated delivery lifecycle

Treat every non-trivial change as a state machine. Do not advance to the next
phase until its exit evidence exists. A phase may be marked
`not-applicable` only when the reason is explicit, scope-aligned, and recorded
in the current change contract.

### 1. Triage and invariant discovery

**Entry:** the request and repository authority are identified.

Before adding a file, package, abstraction, or public surface, perform a
dependency and code-path audit. Inspect the relevant callers, consumers,
existing helpers, schemas, configuration, external boundaries, tests, and
current revision. Identify invariants, failure modes, compatibility risks,
data or operational risks, and the smallest coherent outcome. Cite the
artifacts inspected. If a critical ambiguity affects an interface, invariant,
data migration, security boundary, or production behavior, stop and ask one
focused question.

**Exit:** the change contract names the scope, non-goals, affected paths,
dependencies, invariants, failure modes, and risk class, or records a
defensible `not-applicable` decision for a trivial change.

### 2. Interface and schema lockdown

**Entry:** triage has no unresolved critical ambiguity.

Define the interfaces before implementation: API signatures, types, schemas,
invariants, error shapes, compatibility rules, persistence boundaries, and
observable behavior. Reuse existing contracts and helpers when they fit.
Record any intentional contract change and its consumers. Do not write
implementation code while a required contract is still speculative.

**Exit:** the authoritative design, change contract, PRD when triggered, or
equivalent repository artifact is approved and maps each acceptance criterion
to observable evidence.

### 3. Contract testing and failure assertions

**Entry:** interfaces and schemas are locked.

Write or identify executable assertions for every changed behavior and every
failure mode or boundary condition found in triage. For behavior changes,
observe the required red state before implementation when the `tdd` module is
applicable. Tests must exercise real behavior; mocks may represent only a
declared external seam and must not erase the integration boundary.

**Exit:** the planned test set covers happy paths, invalid input, failure
recovery, compatibility, and important timing or concurrency boundaries, with
any justified exception recorded.

### 4. Minimal-diff implementation

**Entry:** the contract and failure assertions are ready.

Implement only the smallest change that satisfies the locked contract. Before
adding a utility, cite the existing helper search and explain why reuse is
insufficient. Do not bypass repository lint, type-check, test, qualification,
or release rules. Do not include opportunistic refactors, speculative
abstractions, or unrelated formatting. If discovery adds an independent
outcome, materially expands blast radius, or invalidates acceptance criteria,
stop, re-triage, and synchronize the authoritative artifacts before resuming.

**Exit:** the implementation satisfies the locked interfaces and all changed
paths are covered by current evidence.

### 5. Verification and PR gate

**Entry:** implementation is complete for the current slice.

Run the narrowest sufficient checks, then escalate when results or risk
require it. Reassess evidence freshness after every fix. Inspect the final
diff, regression surface, dependency impact, migration or rollback needs,
operational readiness, and review findings. Produce a human-readable
readiness decision and PR breakdown; never substitute a passing happy path or
an unsupported completion claim for proof.

**Exit:** every applicable enabled module is `satisfied`, the final revision is
covered by the required checks, blast radius and rollback posture are stated,
and the handoff contract is valid. Otherwise stop as blocked.

These gates complement the lazy module ledger, evidence freshness rules,
right-sizing, and provider boundaries below. They make the lifecycle explicit;
they do not replace the registry or permit a prompt to disable configured
safeguards.

## Hard constraints

- Never implement before triage and interface lockdown.
- Never conceal an integration boundary with an undeclared mock or fixture.
- Never bypass an existing repository check or report a skipped check as
  passing.
- Never add a duplicate helper without citing the existing-helper audit.
- Never expand scope silently; independent outcomes require a separate change.
- Never preserve stale evidence merely because an earlier phase completed.

## Module contract

A module is an interface. The skill serving it is an implementation. Each
implementation lives in `modules/sdlc-<capability>/` and ships an Agent Skill
`SKILL.md` beside its `sdlc-capability.json`, which is exactly the shape a
third-party provider ships. They are not separately discoverable, because a
host scanning the skills root sees only this skill.

Before reading any implementation `SKILL.md`, read
[modules/registry.json](modules/registry.json). It is the single source for
module placement: name, category, order, and whether the module may be
replaced. Triggers, exit signals, and evidence contracts belong to each
implementation's declaration. If a registered path is missing, report an
invalid installation.

The registry is organized by lifecycle category. Future bundles may connect
one module, multiple complementary modules, or an alternative module to a
category. Alternatives must satisfy the category's exit signal.

## Project configuration

Configuration is orchestrator policy, not a module, so it cannot disable
itself. Before reading any implementation `SKILL.md`, look for `.sdlc/config.json` at the
project root.

- If it is absent, treat every registered module as enabled. On the first
  non-trivial task, create it from
  [assets/sdlc-config.template.json](assets/sdlc-config.template.json), tell
  the user, and continue with all modules enabled. Defer scaffolding for
  trivial work.
- Accept `schemaVersion: 1`, `2`, and `3` for backward compatibility.
  Migrate any of them to schema 4 and persist the complete normalized
  configuration atomically before provider or extension resolution. Preserve
  every explicit boolean, replacement decision, and extension flag. Missing
  `measurement` becomes `{"enabled": false}`. Schema 4 requires `phases`,
  `extensions.project`, `extensions.global`, and the strict
  `measurement.enabled` boolean.
- Schema 4 groups module states under the delivery phase that invokes them,
  so the file names the lifecycle a developer is configuring. Phase
  membership is owned by
  [modules/registry.json](modules/registry.json). A module listed under any
  phase other than its registered one is a configuration error: configuration
  chooses how a phase is served, never where a module sits, because moving a
  module to a less strictly gated phase would weaken a safeguard without
  disabling it in the open.
- Each schema-4 module value is exactly `true`, `false`,
  `{"provider": "bundled"}`, or `{"replaceWith": "installed-skill-id"}`.
  Replacement objects contain only that field. Provider IDs are lowercase
  kebab-case, unique across module
  assignments, and cannot name `sdlc` or a core module. Unsupported versions,
  unknown fields or module names, duplicate keys or providers, and invalid
  union values are configuration errors: stop and identify the exact problem.
- A missing known module key defaults to `true`. This makes newly added
  safeguards active after bundle upgrades until a developer explicitly
  disables them.
- Missing extension entries default to disabled. An extension is considered
  for discovery only when its ID has an explicit `true` entry in project
  configuration.
- Only the committed config controls activation. A prompt to skip a module
  does not override it; changing activation is a separate explicit config
  edit.

Every module is enabled by default, but enabled does not mean loaded.

The six domain modules (`accessibility-browser`, `performance-concurrency`,
`observability`, `api-compatibility`, `data-migration`, and
`dependency-supply-chain`) are conditional specialist capabilities. Evaluate
their positive registry triggers from accepted scope and changed surfaces,
not repository technology alone. Each remains independently triggerable and
satisfiable.

## Delivery profile

Every module belongs to a category, and every category belongs to one phase
of software development. `deliveryPhases` and `categories` in
[modules/registry.json](modules/registry.json) declare that grouping. Phase
is a grouping and presentation layer only. Resolution and replacement happen
per module; a phase never binds a provider and never carries authority of
its own.

A phase gate is the entry gate: the earliest gate at which any of its
categories participates. A phase with no gate lies outside the per-change
state machine and cannot block progression.

`scripts/delivery_profile.py` resolves the registry against project
configuration and renders one map showing which provider serves each
capability:

```
python skills/sdlc/scripts/delivery_profile.py render \
  --registry skills/sdlc/modules/registry.json \
  --output docs/DELIVERY-PROFILE.md
```

Pass `--config .sdlc/config.json` to see the resolved profile for a
configured project. The generated file is committed so a configuration
change that redirects a capability appears as a reviewable diff. Validation
fails when it is stale.

The profile reports resolution, not evidence. A provider named there has
still produced nothing until its exit evidence exists.

## Replacement providers

A replacement entry in project configuration changes only the instruction
provider for one core module. The core registry still controls its category, order, trigger, exit
signal, evidence clauses, freshness, and readiness. Never treat provider
selection, loading, output, or self-certification as evidence.

`change-contract`, `review`, `operational-readiness`, and `pr-handoff` may
never be replaced. Each renders the judgment that permits a change to
advance, so delegating one would let a provider authorize its own
progression. The registry declares this as `replaceable: false`, the
configuration schema accepts only a boolean for them, and configuration
normalization refuses a replacement. They may still be disabled.

A provider is enumerated one of two ways. Either the active host embeds the
provider helper and injects its trusted adapter object through the library
API, outside caller-controlled CLI arguments, or the provider declares
itself on disk under an explicitly supplied provider root. Both produce the
same candidate metadata and go through the same resolution.

The adapter's `enumerate_providers(host_profile)` method returns
metadata-only installed skill candidates. Each
candidate supplies its exact declared Agent Skill `name`, provider metadata,
content digest, and opaque load token without exposing or reading instruction
content. Resolve every configured provider by that exact declared identity.
Zero matches, duplicate candidates in any scopes, incompatible or malformed
provider metadata, and hosts unable to enumerate exact IDs and bind a stable
load target are blocking configuration errors. Never use fuzzy identity,
scope precedence, implicit discovery of unconfigured providers, remote
installation, or bundled fallback.

An eligible provider declares string metadata:

```yaml
metadata:
  sdlc-provider-schema: "1"
  sdlc-compatible: ">=1.0.0 <2.0.0"
  sdlc-modules: "testing"
```

Unknown `sdlc-*` fields block provider use. Preserve the returned digest,
provider metadata, and opaque load token.

### Filesystem provider declarations

A third-party skill may serve a capability without any host adapter by
shipping `sdlc-capability.json` beside its skill document, in a directory
passed explicitly with `--provider-root`. The declaration states
`schemaVersion`, `id`, `capability`, `mode`, `instructions`, `trigger`,
`exitSignal`, `evidence`, `compatibleSdlc`, and, when `mode` is `replace`,
`evaluations` demonstrating parity with the capability it displaces. See
`contracts/capability-provider.schema.json`.

Every bundled capability satisfies this same contract on disk: each
`modules/<name>/` directory ships its own `sdlc-capability.json`. A module is
an interface and the skill serving it is an implementation, so each bundled
declaration states `id` of `sdlc-<capability>` and `mode` of `default`. The
`sdlc-` prefix is reserved; a third-party declaration claiming one is refused.
The registry retains placement only, meaning `name`, `category`, `order`, and
`replaceable`. A bundled declaration may not claim placement, may not claim
another identity, and may not serve a capability other than its own
directory. A provider author copies a shipped declaration rather than
reconstructing one from prose.

Enumerating a provider root is not implicit discovery. Only configured
identities resolve, matching stays exact, duplicate identities across roots
are ambiguous and blocking, and a declaration claiming `sdlc` or a core
capability name is refused. A declaration that cannot be validated is
skipped and reported rather than raised, so one malformed directory cannot
disable the lifecycle. The declared instruction document is the provider's
own skill document, so its frontmatter name and `sdlc-*` metadata must match
its declaration; a mismatch is refused at load.

### Seeing and choosing what serves a capability

`resolve_providers.py survey` reports, for every capability, the connected
provider, whether that is a deliberate decision or the default, which
installed alternatives declare the same capability, and which declarations
were skipped. It also reports where the capability is invoked: its category,
its delivery phase, and that phase's entry gate. Placement lets a developer
judge whether an installed skill covers the same ground, because a category
is the unit a competing skill tends to cover. The report is read-only and
adopts nothing, so discovery stays explicit. Its shape is
[contracts/provider-survey.schema.json](contracts/provider-survey.schema.json).

Placement is always read from the registry and never from a declaration. A
provider that could name its own phase could claim one the control plane does
not gate, escaping the evidence gate that governs the capability it replaces.
A declaration names the capability it serves; the registry decides where that
capability participates.

In configuration, `true` enables the bundled module as the default and
leaves the choice open. `{"provider": "bundled"}` records a deliberate
decision to keep it, and `{"replaceWith": "<id>"}` selects an external
provider. Both object forms are explicit decisions.

Do not raise provider selection with the developer routinely. Ask only when
the choice is genuinely undecided or has become confused, specifically:

- an eligible installed alternative declares an enabled capability whose
  state is still the default `true`, which `survey` reports as
  `developer-choice-required`; or
- artifacts attributable to a provider this configuration did not select
  appear during implementation, which makes the effective owner of a
  capability ambiguous.

Present the competing options, the capability at stake, and the evidence
each would be accountable for, then let the developer decide. Record the
outcome as an explicit configuration decision so the same question is not
asked again. Never adopt an alternative to resolve the ambiguity yourself,
and never stall the lifecycle waiting on this: proceed with the connected
provider and assess any unselected provider's artifacts as ordinary
evidence under the coverage ledger rules.

Evaluate the unchanged core trigger and evidence contract before loading
instructions. If the module is not applicable or existing evidence satisfies
the contract, load neither provider. For `partial`, `missing`, or
`stale/unverified`, run `resolve_providers.py inspect`, then ask the host
adapter to consume the exact opaque token through the same host-controlled
embedding boundary. The library calls `load_provider(load_token)` directly
and does not accept an adapter import path or caller-supplied load response.
For a filesystem provider, pass the same `--provider-root` values to
`resolve_providers.py load-module`, which re-reads and re-digests the
declared document and refuses any change since resolution.
Standalone CLI resolution or loading that needs a provider and has neither a
host adapter nor a provider root reports
`provider-resolution-unsupported`; it never imports a caller-named adapter or
reads provider instructions directly. The adapter must atomically validate
and consume the token against current host state, then return the bound
snapshot or an explicit
revoked, unknown-token, replayed-token, or unloadable result. Revalidate the
returned content digest, declared identity, and provider metadata before
using a non-empty instruction body. Give the provider the core trigger, exit
signal, evidence clauses, recognized evidence, and only the unresolved gaps.
Independently inspect and validate its results against every core evidence
clause afterward. Provider failure or missing evidence blocks without reading
the bundled implementation.

Coverage identifies the core module, provider type (`bundled`, `disabled`, or
`replacement`), replacement ID when present, recognized evidence, gaps,
status, and whether instructions were loaded or reused.

## Extension discovery

After validating core registry metadata and normalizing project
configuration, run `manage_extensions.py resolve`. Resolve configured
entries in this order:

1. project extensions explicitly enabled in `extensions.project`;
2. user-global catalog entries explicitly enabled in `extensions.global`.

Resolve only explicit configuration references. Do not scan `.sdlc/` or a
global catalog for arbitrary Markdown. Validate every configured ID first.
For enabled entries, validate the confined extension path, metadata,
compatibility, required files, and content digest before returning metadata.
An explicit `false` entry becomes a `configured-disabled` coverage entry
without reading its instructions.

Resolution binds metadata and `contentDigest` to one immutable byte snapshot.
When an extension later reaches `partial`, `missing`, or `stale/unverified`,
load it through `manage_extensions.py load-module` with that exact digest.
The loader reads and validates one new snapshot, rejects any digest mismatch,
and returns the instruction document from the bytes it validated. Never load the live path
directly after resolution.

Before loading any returned module instructions, compare extension metadata
with enabled core modules and other extensions for semantic conflicts. The
helper rejects structural conflicts it can prove, including one normalized
trigger assigned to different categories and duplicate IDs with different
content. Stop on any remaining incompatible instruction. Project order does
not silently override a conflicting global entry. Never execute extension
scripts.

Static extension validation covers representative dangerous instructions as
defense in depth. It is not an exhaustive safety verdict. Model safety review
is mandatory before an extension can be approved.

An accepted extension remains an augmentation: it cannot replace core
configuration semantics or disable an enabled safeguard. Generated or
promoted content remains inactive until the developer explicitly approves a
config change. Project interactions never mutate the installed core skill.
Replacement providers never enter extension discovery, candidate state,
promotion, or contribution packaging. A replacement and an augmentation may
both apply, and existing semantic conflict checks still block incompatibility.

## Deterministic operator reports

For a non-trivial task, the orchestrator may serialize its ephemeral ledger
to the strict `contracts/operator-state.schema.json` shape and call:

```text
python scripts/validate_artifacts.py explain --input STATE.json
python scripts/validate_artifacts.py preview --input STATE.json
python scripts/validate_artifacts.py render-coverage --input STATE.json
```

Use `--detail concise`, `normal`, or `detailed`. These read-only commands
explain and project only supplied facts. They do not resolve extensions,
inspect artifacts, load instructions, execute scripts, inspect the worktree, or
mutate configuration. The orchestrator remains responsible for semantic
trigger interpretation, evidence quality and freshness, and readiness.
Concise output still preserves blockers and configured-disabled safeguards.

Every core module state may carry the exact provider selection:

```json
{"provider": {"type": "replacement", "id": "custom-testing-provider"}}
```

The other valid descriptors are `{"type": "bundled"}` and
`{"type": "disabled"}`. Only `replacement` includes `id`; the other types
reject it. For compatibility with operator-state schema-1 producers that
predate providers, an omitted descriptor on an enabled core module normalizes
to `bundled`, and one on a disabled core module normalizes to `disabled`.
Extensions reject provider descriptors. Every command preserves the
normalized descriptor at concise, normal, and detailed output levels without
resolving or loading provider instructions.

PRD, plan, and normalized handoff contracts can be checked with
`validate-prd`, `validate-plan`, and `validate-handoff`. Structural success is
always reported as `semanticApproval: not-assessed`; it never approves product
decisions, evidence quality, risk acceptance, or PR readiness.

Non-native local requirements can be inspected and reconciled with
`reconcile_artifacts.py`. Inspection is non-authoritative. Reconciliation
nominates exactly one direct source or generated view, writes a draft
project-local sidecar, preserves provenance and stable requirement IDs, and
never edits the source or infers approval. Digest drift, unmapped fields,
conflicts, stale selectors, view edits, and approval-binding mismatch block
downstream readiness.

After `validate-handoff` succeeds, `render-handoff` can project the same
normalized packet as local Markdown for GitHub, GitLab, or Azure DevOps.
Rendering writes to stdout by default and writes a file only with an explicit
`--output` path. Templates are used only when explicitly supplied. Rendering
does not inspect remotes, authenticate, run git, publish, open, update,
approve, or merge a request.

## Private local aggregate measurement

Measurement is disabled by default and can be enabled only by an explicit
project configuration edit that is then committed:

```json
"measurement": {"enabled": true}
```

A prompt cannot enable it. Use `manage_metrics.py configure --enabled true`
or `false` for the supported consent-change flow, then commit the resulting
configuration edit. Configuration replacement and final metric replacement
use the same project-local metrics lock. When an official disable command
returns, every earlier metric replacement has finished and later official
records observe disabled consent.

This linearizable boundary applies to the bundled `configure` and `record`
operations. An arbitrary editor or other non-cooperating process that rewrites
configuration without the lock is detected by the in-lock consent recheck
when ordering permits, but is not claimed to be atomic with metric
replacement.

When enabled, invoke `manage_metrics.py record` only at the event boundary.
Do not derive events later or collect
automatically. Record at most once per module and applicable module event in
one orchestrator run, once per distinct evidence-ledger entry, once after an
extension lifecycle transaction succeeds, and once when the final report is
emitted. Record a phase only when the host supplies monotonic start and end
boundaries. Timing failures omit the observation and never affect readiness.

Use the closed events literally:

- `module.enabled` follows resolved enabled core eligibility;
  `module.triggered` follows an applicable core trigger; `module.loaded`
  follows actual instruction loading; `module.reused` follows accepted
  evidence that avoided loading; and `module.disabled` follows explicit
  disabled configuration and disclosure.
- `evidence.reused` counts distinct ledger entries accepted without refresh.
  `evidence.refreshed` counts distinct stale or partial entries replaced and
  accepted for the current revision.
- `clarification.asked` counts only a user-facing question needed for a
  readiness ambiguity. `clarification.avoidedByEvidence` counts only when a
  specific inspectable artifact supplies a field that otherwise required a
  question. Tie that decision to the current in-memory ledger and never
  estimate avoided questions later.
- Extension events follow newly persisted observations or successful
  accepted, rejected, promoted, and superseded transitions, never reads.
  Report events follow the one final concise, normal, or detailed report.

Projects with a regular `.git` directory use `.git/sdlc/metrics.json`. Normal
worktree and submodule gitfiles use the project-confined
`.sdlc/local/metrics.json`. Other projects may use that local path only when
effective Git ignore evaluation for the exact metrics file proves it excluded,
including enclosing repository rules, order, and negation. If local Git
cannot establish exclusion, fail closed rather than approximating ignore
semantics. There is no global store.

Immediately after acquiring the metrics write lock and before reading or
writing the store, re-read consent from committed configuration. If it was
disabled concurrently, return the disabled no-write result. The schema
contains only closed aggregate counters, a reset generation, and six fixed
duration buckets. It contains no prompts, responses, code, credentials,
paths, names, task or revision IDs, host or model IDs, timestamps, exact
durations, or arbitrary labels. Measurement is irrelevant to triggers,
evidence, module status, and readiness. Store diagnostics use stable neutral
classes and never include project or user paths.

Use `configure`, `status`, `inspect`, `record`, `reset`, and `delete`
explicitly. Supported disabling stops writes at command completion and retains
existing data for inspection, reset, or deletion. Reset preserves consent and
increments the non-temporal generation. Delete removes data but leaves consent
unchanged, so a later eligible event can recreate the store. To stop and
erase, disable first and then delete. Corrupt or unavailable measurement is
reported honestly and cannot block otherwise satisfied lifecycle work.

## Coverage assessment and lazy activation

1. Resolve the enabled/disabled state from project configuration.
2. Run `resolve` to obtain explicitly configured extension coverage entries
   and validated metadata.
3. Evaluate registry and extension triggers without opening module files.
4. For each core module and resolved extension, build an ephemeral coverage
   ledger using one status:
   `satisfied`, `partial`, `missing`, `stale/unverified`,
   `configured-disabled`, or `not-applicable`.
5. Assess capability evidence, not producer identity. Inspect relevant
   specifications, plans, diffs, project files, current-session tool results,
   CI results tied to the current revision, and review artifacts regardless of
   whether a human, an external skill, or another workflow created them.
6. Accept evidence only when it is inspectable, scope-aligned, specific enough
   to satisfy the registry contract, and current for the task or implementation
   revision. Unsupported completion claims are leads, not evidence.
7. Accept an artifact produced by another skill or workflow on the same
   terms, including one produced by a provider this configuration did not
   select. Producing an artifact never grants authority: it satisfies a
   capability only when it meets the registry contract for that capability
   and does not contradict evidence already accepted for another enabled
   module. Contradiction means a provable inconsistency, such as an
   artifact asserting a scope the approved change contract excludes, a
   result claiming a revision other than the one under assessment, or two
   artifacts making opposing claims about the same capability. Resolve a
   contradiction as a gap and state which artifacts conflict; never silently
   prefer one producer over another.
8. Do not load implementation instructions for `satisfied`,
   `configured-disabled`, or
   `not-applicable` entries. Do not repeat their work.
9. For `partial`, `missing`, or `stale/unverified` entries, read the
   instructions and perform only the unresolved work. Read a bundled
   its instruction document at its registry path; its integrity is bound at the bundle
   level by `qualification/manifest.json`, verified with
   `qualify.py verify-manifest`, not per module at load time. Load a
   replacement provider through `resolve_providers.py load-module` and an
   extension through `manage_extensions.py load-module`, both of which are
   digest-bound per load. Preserve core registry order, then resolved
   extension order.
10. Do not load a conditional module or extension merely to investigate
   whether it might apply. If later evidence triggers it, add it to the
   ledger then.
11. In every final response, list `Configured-disabled modules: ...` or
   `Configured-disabled modules: none`, even when `pr-handoff` is disabled.

PR readiness is judged against the selected modules. The disclosure makes
omitted safeguards visible without overriding developer policy.

## Evidence freshness

Reassess the coverage ledger whenever work changes evidence dependencies:

- Acceptance-criteria or scope changes can stale planning, tests, security,
  review, and handoff evidence.
- A PRD requirement, approval, or version change stales dependent planning,
  implementation, tests, security, operational, review, and handoff evidence.
- A changed accepted requirement, public contract, or architecture decision
  also stales the authoritative design until it is synchronized.
- A contract or PRD change can stale every applicable domain module.
- Implementation changes stale only domain evidence whose rendered surface,
  workload, signal map, consumer matrix, data path, or dependency resolution
  may have changed.
- Implementation changes can stale tests, security analysis, operational
  evidence, review, and handoff.
- Fixes made after review can stale the affected review perspectives and
  verification results.
- A changed revision invalidates CI or review evidence tied to an older
  revision unless the evidence still demonstrably covers the final state.

Never preserve `satisfied` merely because a phase ran earlier.

## Coverage report

Do not interrupt the user merely to announce a gap that can be filled
autonomously. Ask only when missing evidence exposes a genuine decision or
costly ambiguity.

For non-trivial work, include this compact final table:

| Module | Status | Recognized evidence or gap | Action |
|--------|--------|----------------------------|--------|
| `<name>` | `<status>` | `<artifact, command, result, or missing proof>` | `<reused, completed, refreshed, skipped, or blocked>` |

Include every registry module and every resolved extension so developers can
see what was checked.
For trivial work, use one line listing satisfied/reused, completed,
not-applicable, and configured-disabled modules. Do not persist the ledger;
rebuild it from current evidence on every task.

## Orchestration rules

1. Complete the gated delivery lifecycle above while resolving configuration,
   triggers, and existing evidence before loading
   modules.
2. When selected, load project memory and project standards before analysis.
3. When selected, establish the change contract before implementation. For a
   Significant existing-codebase change, present its discovery brief before
   asking the first focused question. Ask one question at a time when
   ambiguity changes the solution or is expensive to undo.
4. When the PRD trigger applies, require an explicitly approved PRD before
   planning or implementation. A non-native local specification qualifies
   only through a validated reconciliation report and one nominated
   authority. A conversation or draft is not a substitute.
5. When planning has a selected PRD, require deterministic PRD and plan
   validation before implementation. For long plans, reuse a current
   project-local execution cursor without treating it as lifecycle evidence.
6. When TDD triggers, require observed red, minimal green, and refactor before
   accepting implementation evidence. Code-first work is not TDD evidence.
7. Before TDD and implementation, evaluate the six domain-module triggers in
   registry order. Use each triggered module's specialist constraints to shape
   tests and slices without transferring lifecycle ownership.
8. If the active change-contract module identifies independent outcomes,
   propose separate changes.
   A coherent outcome may cross API, UI, data, tests, and documentation.
9. Classify the change:
   - **Trivial**: mechanical, obvious, low-risk, and behavior-preserving.
   - **Standard**: non-obvious bug fix or bounded behavioral change.
   - **Significant**: cross-cutting, public-contract, auth, money, PII, data,
     migration, infrastructure, or irreversible change.
10. Stop and revisit the active contract when discoveries add an independent outcome,
   expand risk materially, or invalidate acceptance criteria.
   Do not resume after design drift until the PRD when selected, authoritative
   design, selected project memory, plan, and dependent evidence are
   synchronized and required approvals are renewed.
11. Do not call work done or PR-ready until every applicable enabled module is
   `satisfied`.
12. If project memory is selected, finish by recording durable decisions and
   current context. Do not log routine mechanical noise.

## Delegated work

Modules are not inherited automatically by subagents or background tools.
Every delegation must include the context produced by selected or already
satisfied modules:

- the change contract and approved PRD when selected or satisfied; otherwise
  the original request and available scope;
- relevant project standards and `.sdlc/memory/` paths when their modules are
  selected;
- only the selected module expectations that apply;
- tests, security/operational checks, and evidence only when their modules are
  selected.

For bug fixes, require reproduction and root-cause evidence only when
debugging is selected, and regression sensitivity only when testing is
selected. Keep implementation and review roles independent when review is
selected and the host supports it. The orchestrator owns coverage
reconciliation and the PR-readiness decision.

## Right-sizing

- **Trivial**: one-sentence contract, no written plan, narrowest applicable
  automated check, concise final-diff review, and no first-time standards or
  memory scaffolding. Behavior-preserving changes do not trigger TDD.
- **Standard**: short analysis and plan, focused automated tests, applicable
  security categories, at least one independent reviewer when supported, and
  the full handoff gate.
- **Significant**: full impact analysis, explicit risky decisions, multiple
  independent review perspectives when supported, integration/contract
  evidence, and operational readiness when triggered.

New product features require a PRD even when their implementation is bounded.
Right-size its depth, not the durable artifact or approval.

Exploratory read-only questions and prose-only documentation work can
right-size modules to quick checks. Behavioral changes still require tests.
These defaults apply only to enabled modules.

## Stop signals

Stop and re-check the relevant module when reasoning becomes:

- "Put it in this PR while we are here."
- "CI will catch it."
- "The happy path passed."
- "The diff is too small to review."
- "Minimal means tests or docs can wait."
- "We can work out rollback later."
- "The test passes, so proving it fails is unnecessary."
- "The implementation already exists, so tests after are close enough."
- "The first plausible fix is probably the root cause."

These stop signals apply only when the corresponding module is enabled.
Urgency changes sequencing, not the active readiness gates.
