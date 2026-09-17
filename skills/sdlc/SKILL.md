---
name: sdlc
description: 'Use when creating, modifying, debugging, fixing, or reviewing code, including work likely to become a pull request, before implementation begins. Also use when scope is unclear, a request bundles outcomes, verification or review might be skipped, delegated coding needs guardrails, project context must persist, or a change affects production data, rollout, rollback, or public contracts. Skip only for answers that do not change code.'
license: MIT
metadata:
  category: process
  architecture: modular
  version: "3.7.1"
---

# SDLC

Act as a disciplined senior engineer. For every task that creates, modifies,
fixes, debugs, or reviews code, select and orchestrate the modules below.

**Default outcome:** produce one reviewable change with one coherent outcome,
the minimum complete diff needed to achieve it, durable project context, and
fresh evidence that it is correct and safe. Explicit configuration can remove
those safeguards; always disclose the configured-disabled modules.

## Module contract

`modules/` contains internal SDLC modules, not separately discoverable skills.
Before reading any `MODULE.md`, read
[modules/registry.json](modules/registry.json). It is the single source for
module names, categories, order, paths, triggers, exit signals, and lightweight
evidence contracts. If a registered path is missing, report an invalid
installation.

The registry is organized by lifecycle category. Future bundles may connect
one module, multiple complementary modules, or an alternative module to a
category. Alternatives must satisfy the category's exit signal.

## Project configuration

Configuration is orchestrator policy, not a module, so it cannot disable
itself. Before reading any `MODULE.md`, look for `.sdlc/config.json` at the
project root.

- If it is absent, treat every registered module as enabled. On the first
  non-trivial task, create it from
  [assets/sdlc-config.template.json](assets/sdlc-config.template.json), tell
  the user, and continue with all modules enabled. Defer scaffolding for
  trivial work.
- Accept `schemaVersion: 1` and `schemaVersion: 2` for backward compatibility.
  Migrate either to schema 3 and persist the complete normalized configuration
  atomically before provider or extension resolution. Preserve every explicit
  boolean and extension flag. Missing `measurement` becomes
  `{"enabled": false}`. Schema 3 requires `modules`, `extensions.project`,
  `extensions.global`, and the strict `measurement.enabled` boolean.
- Each schema-3 module value is exactly `true`, `false`, or
  `{"replaceWith": "installed-skill-id"}`. Replacement objects contain only
  that field. Provider IDs are lowercase kebab-case, unique across module
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

## Replacement providers

A schema-3 replacement changes only the instruction provider for one core
module. The core registry still controls its category, order, trigger, exit
signal, evidence clauses, freshness, and readiness. Never treat provider
selection, loading, output, or self-certification as evidence.

After configuration migration, the active host embeds the provider helper and
injects its trusted adapter object through the library API, outside
caller-controlled CLI arguments. The adapter's
`enumerate_providers(host_profile)` method returns metadata-only installed
skill candidates. Each
candidate supplies its exact declared Agent Skill `name`, provider metadata,
content digest, and opaque load token without exposing or reading instruction
content. Resolve every configured provider by that exact declared identity.
Zero matches, duplicate candidates in any scopes, incompatible or malformed
provider metadata, and hosts unable to enumerate exact IDs and bind a stable
load target are blocking configuration errors. Never use fuzzy identity,
scope precedence, directory scanning, remote installation, or bundled
fallback.

An eligible provider declares string metadata:

```yaml
metadata:
  sdlc-provider-schema: "1"
  sdlc-compatible: ">=3.7.0 <4.0.0"
  sdlc-modules: "testing"
```

Unknown `sdlc-*` fields block provider use. Preserve the returned digest,
provider metadata, and opaque load token.

Evaluate the unchanged core trigger and evidence contract before loading
instructions. If the module is not applicable or existing evidence satisfies
the contract, load neither provider. For `partial`, `missing`, or
`stale/unverified`, run `resolve_providers.py inspect`, then ask the host
adapter to consume the exact opaque token through the same host-controlled
embedding boundary. The library calls `load_provider(load_token)` directly
and does not accept an adapter import path or caller-supplied load response.
Standalone CLI resolution or loading that needs a provider reports
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
the bundled `MODULE.md`.

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
without reading its `MODULE.md`.

Resolution binds metadata and `contentDigest` to one immutable byte snapshot.
When an extension later reaches `partial`, `missing`, or `stale/unverified`,
load it through `manage_extensions.py load-module` with that exact digest.
The loader reads and validates one new snapshot, rejects any digest mismatch,
and returns `MODULE.md` from the bytes it validated. Never load the live path
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
inspect artifacts, load `MODULE.md`, execute scripts, inspect the worktree, or
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
7. Do not load `MODULE.md` instructions for `satisfied`,
   `configured-disabled`, or
   `not-applicable` entries. Do not repeat their work.
8. For `partial`, `missing`, or `stale/unverified` entries, use the
   digest-bound loader to read the module and perform only the unresolved
   work. Preserve core registry order, then resolved extension order.
9. Do not load a conditional module or extension merely to investigate
   whether it might apply. If later evidence triggers it, add it to the
   ledger then.
10. In every final response, list `Configured-disabled modules: ...` or
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

1. Resolve configuration, triggers, and existing evidence before loading
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
