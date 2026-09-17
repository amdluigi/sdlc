# SDLC v3 Capability Program

Date: 2026-09-17
Status: Approved

## Outcome

SDLC provides first-party product definition, strict test-first delivery,
cross-host qualification, specialist engineering depth, deterministic
operator tooling, forge-ready handoffs, specification interoperability, and
privacy-preserving local measurement without depending on another workflow.

## Principles

- Keep one discoverable `sdlc` skill.
- Keep modules lazy, configurable, evidence-aware, and independently
  reviewable.
- Use separate releases and commits for independent capability outcomes.
- Reuse valid external evidence without delegating lifecycle ownership.
- Keep project-specific policy in standards, memory, configuration, or
  extensions.
- Add no automatic network, push, publish, merge, PR, or telemetry side
  effect.
- Use the Python standard library for bundled deterministic tooling.
- Require pressure cases and deterministic tests for every behavior change.

## Release 3.0: Product and Test-First Core

### Goal

Make SDLC self-sufficient for approved product definition, executable
requirements traceability, strict TDD, and resumable feature execution.

### Requirements

1. Keep the existing PRD module as the authoritative product artifact.
2. Add deterministic commands that validate PRD identity, required sections,
   approval status, requirement mappings, and version.
3. Add a default-enabled `tdd` module between planning and implementation.
4. Require red, minimal green, and refactor for new behavior and bug fixes.
5. Require tests against real behavior; mocks are permitted only at genuine
   external seams.
6. Reject implementation written before the red state as TDD evidence.
7. Allow explicit technical exceptions for generated output,
   configuration-only changes, or unsafe reproduction. Record the reason and
   strongest alternative evidence.
8. Keep the testing module responsible for final coverage and verification;
   TDD owns implementation order and sensitivity.
9. Add deterministic plan validation for PRD path, ID, version, `FR-*` and
   `AC-*` mappings, dependencies, consumed/produced interfaces, and
   verification.
10. Add an ignored or project-configurable execution cursor for long-running
    plans. Do not require committed timestamps or completion summaries.

### Acceptance

- New features and bug fixes refuse code-first implementation.
- A test that passes before implementation is not accepted as red evidence.
- Bug fixes reproduce the defect before the fix when technically safe.
- PRD, plan, tests, and handoff remain traceable.
- Small non-behavioral changes do not incur strict TDD ceremony.

## Release 3.1: Host and Installation Qualification

### Goal

Prove that the complete bundle installs and behaves consistently across
representative hosts and installation modes.

### Requirements

1. Add a host-neutral qualification manifest and result schema.
2. Cover GitHub Copilot/VS Code, Claude Code, and a generic Agent Skills
   client profile.
3. Cover project/global and copy/link installation modes where supported.
4. Verify discoverable skill count, module count, config template, helper
   scripts, file hashes, and trigger discovery.
5. Separate deterministic installation conformance from live model behavior.
6. Store versioned sanitized qualification summaries, not prompts or project
   code.
7. Fail release qualification when a required host profile has no result or a
   critical behavioral case fails.

### Acceptance

- Installation conformance is reproducible without network access after
  source checkout.
- Live-host results identify host, client version, model class, skill version,
  case IDs, and pass/fail evidence without sensitive content.

## Release 3.2: Lazy Domain Modules

### Goal

Add broadly useful specialist depth without loading irrelevant guidance.

### Modules

1. `accessibility-browser`: user-visible web/mobile flows, accessibility,
   browser runtime, responsive and interaction states.
2. `performance-concurrency`: hot paths, resource use, concurrency,
   caching, latency, throughput, and measurement.
3. `observability`: logs, metrics, traces, alert signals, privacy, and
   diagnostic usefulness.
4. `api-compatibility`: interfaces, versioning, error contracts, consumer
   compatibility, and generated clients.
5. `data-migration`: expand-contract, backfill, integrity, mixed versions,
   rollback, and rehearsal.
6. `dependency-supply-chain`: dependency necessity, provenance, lockfiles,
   advisories, licensing, and update risk.

### Requirements

- Every module has a narrow positive trigger, not an always-on trigger.
- Every module defines measurable exit evidence.
- Each module includes positive, negative, counterexample, and pressure
  evaluations.
- Overlap with security, testing, implementation, and operational readiness
  is explicit and non-duplicative.

## Release 3.3: Operator Ergonomics

### Goal

Make module selection, evidence, and artifacts understandable without reading
the entire bundle.

### Commands

- `explain`: show why each module is enabled, triggered, loaded, reused, or
  skipped.
- `preview`: show modules and extensions that would load for supplied task
  metadata without executing them.
- `validate-prd`: validate PRD identity, completeness, approval, and
  traceability.
- `validate-plan`: validate requirements mapping and task dependencies.
- `validate-handoff`: validate readiness packet completeness.
- `render-coverage`: emit concise, normal, or detailed coverage reports.

### Requirements

- Commands are deterministic and read-only unless explicitly documented.
- Invalid artifacts return concise errors and non-zero status.
- Concise mode preserves blockers and disabled safeguards.
- No command claims semantic approval from schema validation alone.

## Release 3.4: Forge Handoff Adapters

### Goal

Render validated SDLC handoffs into forge-specific text without performing
network or repository publication actions.

### Adapters

- GitHub pull request Markdown.
- GitLab merge request Markdown.
- Azure DevOps pull request Markdown.

### Requirements

- Consume one normalized handoff model.
- Preserve PRD identity/version, `FR-*` and `AC-*`, test evidence, review,
  compatibility, rollout, rollback, risk, and deferred work.
- Respect an existing repository template when supplied.
- Render locally to stdout or an explicit file.
- Do not authenticate, push, publish, open, update, or merge a request.

## Release 3.5: Specification Interoperability

### Goal

Reuse common external requirement artifacts without maintaining competing
authoritative documents.

### Supported mappings

- Generic `SPEC.md`.
- Generic feature `design.md`.
- GitHub issue Markdown export.
- Third-party structured specification.
- Existing repository PRD documents with different locations.

### Requirements

- Map source fields to the SDLC PRD contract.
- Produce a reconciliation report: mapped, missing, conflicting, and
  superseded requirements.
- Never overwrite the source artifact automatically.
- Nominate one authoritative artifact or create an explicitly generated view.
- Preserve source references and approval evidence.
- Block planning when required identity, content, or approval cannot be
  established.

## Release 3.6: Opt-In Local Measurement

### Goal

Measure whether SDLC reduces repeated work and context cost without telemetry.

### Metrics

- modules enabled, triggered, loaded, reused, and disabled;
- evidence items reused and refreshed;
- clarification questions asked and avoided through existing evidence;
- extensions observed, accepted, rejected, promoted, and superseded;
- elapsed local phase durations when the host can provide them;
- concise/normal/detailed report mode usage.

### Privacy

- Disabled by default.
- Project-local only.
- Aggregate counters and bounded durations only.
- No prompts, responses, code, paths, user names, repository names, secrets,
  or external upload.
- Clear reset and deletion commands.

### Acceptance

- Enabling measurement is an explicit config change.
- Metrics do not affect readiness decisions.
- Disabling measurement stops writes immediately.
- The complete metrics store can be inspected and deleted locally.

## Release 3.7: Replaceable Module Providers

### Goal

Let projects replace a core module's instructions with another installed
skill without replacing SDLC as the lifecycle orchestrator.

### Configuration

Use schema version 3. Keep the existing boolean form and add one explicit
replacement object:

```json
{
  "schemaVersion": 3,
  "modules": {
    "testing": true,
    "review": false,
    "prd": {
      "replaceWith": "custom-prd-provider"
    }
  }
}
```

- `true`: use the bundled core module.
- `false`: disable the module and disclose the omitted safeguard.
- `{ "replaceWith": "SKILL_ID" }`: use the installed skill as the module
  provider.

Schema-1 and schema-2 booleans migrate without behavior changes.

### Runtime Contract

1. The core registry remains the source of category, trigger, exit signal,
   evidence contract, order, freshness dependencies, and readiness behavior.
2. Replacement changes the instruction provider only. It cannot weaken or
   replace the module's evidence contract.
3. Evaluate the core trigger before loading the replacement skill.
4. If existing evidence already satisfies the core contract, load neither
   provider.
5. Resolve replacement skills by exact installed skill ID through the host's
   available skill discovery mechanism.
6. If the skill is unavailable, ambiguous, incompatible, or cannot be loaded,
   block with a clear configuration error.
7. After execution, classify the provider's output against the core evidence
   contract. Missing evidence keeps the module partial or missing.
8. Do not silently fall back to core instructions. A fallback would hide
   configuration mistakes and make behavior host-dependent.
9. Coverage reports identify the module, provider type, replacement skill ID,
   evidence recognized, and resulting status.

### Scope

- One replacement provider per core module.
- No provider chains.
- No automatic replacement based on whichever skills happen to be installed.
- No replacement of orchestrator configuration, registry, evidence ledger,
  or readiness semantics.
- A replacement skill can itself use subagents or specialist tools according
  to host and project policy.

### Validation

- Strictly validate the mixed boolean/object module schema.
- Require exactly one `replaceWith` field with a valid skill ID.
- Reject unknown fields, empty IDs, duplicate providers, and replacement
  cycles.
- Add migration, core/disabled/replacement, unavailable skill, evidence-gap,
  satisfied-without-loading, and coverage-report cases.
- Qualify replacement behavior on every supported host profile because skill
  discovery differs by host.

### Acceptance

- Existing configurations behave identically after migration.
- Users can understand all three module states from the config alone.
- Replacements remain lazy and evidence-driven.
- External skills can provide specialized behavior without becoming a second
  top-level orchestrator.
- Readiness never succeeds with weaker evidence than the core module requires.

## Cross-Release Requirements

1. Preserve `.sdlc/memory/` and schema compatibility.
2. Preserve project extension approval and digest-bound loading.
3. Keep new core modules enabled by default and lazy by trigger.
4. Update registry, config template, validator, docs, tests, and behavior
   cases together.
5. Use one independent review per release and a final program review.
6. Keep commits and release boundaries aligned with the eight outcomes.
7. Do not add co-author trailers.
8. Do not commit temporary implementation plans or generated caches.

## Verification

Every release must pass:

- deterministic unit tests;
- repository structural validation;
- relevant blind-scored behavioral cases;
- exact throwaway installation file hashes;
- shell syntax validation;
- final diff and documentation review;
- compatibility checks against the prior released config and artifact
  schemas.

The program is complete only when all eight releases satisfy their own
acceptance criteria independently.
