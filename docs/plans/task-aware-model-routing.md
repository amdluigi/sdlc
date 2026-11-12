---
type: implementation-plan
prd-path: docs/prds/staged-execution-orchestration.md
prd-id: staged-execution-orchestration
prd-version: 3
---

# Task-aware model planning at the finite batch boundary

## Change contract

Complete the approved routing-proposal capability (`FR-5`, `FR-6`, `FR-17`,
`FR-18`) without adding a scheduler or changing execution authority. A user
supplies a plan, finite batch, model inventory and routing preferences. The
tool classifies declared task shape, selects the lowest declared cost rank
among suitable candidates, and proposes stronger models for the batch's
already bounded fallback slots. Explicit materialization produces a batch
for the existing preview and consent flow, not an execution approval.

This Significant additive CLI change serves operators preparing exact
finite batches. It does not infer economic savings or semantic task
difficulty, authenticate supplied inventories or prices, invoke a model,
approve policy, accept results, alter task instructions, or dispatch work.
Parallel workers, live experiments and automatic proposal adoption are
separate outcomes. The maintainer deferred savings proof to users.

## Interface lockdown

Reuse `execution_contracts` plan/brief validation,
`execution_orchestration.validate_batch_contract`, `execution_controls`
inventory/model resolution, canonical digests and the strict JSON loader.
Existing insights proposals require empty routing recommendations; preserve
that version-1 contract rather than repurposing it.

The new version-1 routing policy has `schemaVersion`, `kind`
(`sdlc-model-routing-policy`), `permittedModels`, `models` and `profiles`.
Each unique model declares `id`, integer `capacity` (1..3) and nonnegative
integer `costRank`. Each unique profile declares `id`, `minimumCapacity`
(1..3) and candidate model IDs. Ranks are user preferences, not billing.
All candidates and permitted IDs must have model declarations.

Classification uses declared plan shape only: level 3 for at least four
owned paths, four acceptance criteria or two prerequisites; otherwise
level 2 for any owned path, prerequisite or multiple criteria; otherwise
level 1. A profile floor can increase, never decrease, the required level.
This transparent heuristic does not inspect source or infer security needs.
The operator must declare a sufficiently strong profile.

`propose_routing(plan, batch, inventory, policy)` returns a strict
version-1 `sdlc-model-routing-proposal`: `active: false`, `planDigest`,
`batchDigest`, `inventoryDigest`, `policyDigest`, `decisions` and
`proposalDigest`. Decisions contain only task/attempt/profile/model IDs,
shape and required capacity, cost rank and selection reason. No instructions
or raw task text are retained. The first slot uses a task's explicit model
when supplied, otherwise the lowest suitable rank; ties use model ID.
Later slots use the lowest ranked strictly stronger candidate, or repeat
the current model if no stronger candidate exists. Requested and observed
identities remain separate. Supplied inventory is not proof of dispatch.

`materialize_routing(plan, batch, inventory, policy, proposal)` rederives
the complete proposal and rejects any mismatch, then changes only batch
model IDs. Every other field, including briefs, bounds and identities,
remains identical. The existing manager still checks live consent,
permitted models, escalation, current digests, unknown work and independent
acceptance. A proposal cannot change those checks or serve as approval.

The CLI has `propose` and `materialize`, both requiring explicit `--plan`,
`--batch`, `--inventory` and `--policy` paths. Materialization additionally
requires `--proposal`. JSON goes only to stdout; errors use sanitized
ContractIssue diagnostics and nonzero exit codes. Unknown fields/versions,
missing profiles/models, stale bindings and unsuitable pins fail closed.
No automatic files, network access, providers or telemetry are introduced.

## Dependency-aware tasks

| Task | PRD refs | Outcome | Prerequisites | Consumes | Produces | Execution | Verification |
|------|----------|---------|---------------|----------|----------|-----------|--------------|
| contracts | FR-5, FR-17, AC-5, AC-17 | Lock policy and metadata-only proposal contracts | none | none | routing-contracts | sequential | Red tests for classification, selection, pins, unavailable inventory and strict inputs |
| planner | FR-5, FR-6, FR-17, AC-5, AC-6, AC-17 | Deterministic bounded selection and proposal validation | contracts | routing-contracts | routing-proposals | sequential | Red/green tests for ranking, stronger slots, no suitable model, privacy and tampering |
| materialize | FR-1, FR-2, FR-8, FR-9, FR-18, AC-1, AC-2, AC-8, AC-9, AC-18 | Explicitly materialize only model choices into existing finite batches | planner | routing-proposals | routing-cli | sequential | Actual CLI success/error, changed-input rejection and existing manager consent integration |
| qualification | FR-4, FR-7, FR-14, AC-4, AC-7, AC-14 | Deliver additive helpers without changing manager authority or old formats | materialize | routing-cli | routing-delivery | sequential | Focused controls/orchestration tests, complete CI, manifest/repository/plan validation and independent read-only review |
| baseline-regressions | FR-3, FR-10, FR-11, FR-12, FR-13, FR-15, FR-16, FR-19, FR-20, FR-21, FR-22, FR-23, FR-24, FR-25, FR-26, AC-3, AC-10, AC-11, AC-12, AC-13, AC-15, AC-16, AC-19, AC-20, AC-21, AC-22, AC-23, AC-24, AC-25, AC-26 | Preserve other staged capabilities and explicit existing qualification limitations | materialize | routing-cli | routing-regressions | sequential | Existing full Python CI and unchanged dashboard/runtime evidence; no new claim of live-host qualification or resolution of Windows issue 42 |

## Files, risks and reversal

- Add `execution_routing.py` and `manage_routing.py` to the installed scripts.
- Add focused tests and `docs/MODEL-ROUTING.md`.
- Update architecture and qualification inventory for those helpers.
- Update the qualification helper allowlist and existing installed-file
  regression so both helpers are required in actual copy/link deliveries.
- Existing manager, controls, runtime, events, insights and batch schemas
  have no delta. Existing independently deployed consumers remain unchanged.
- Public decisions remain here and in architecture, not root `.sdlc/`.

Check input validation/injection, consent separation and data minimization.
Authentication, credentials, transport, migrations, production stores,
concurrency and new dependencies are not changed. Selection is unverified
planning, never a claim of effective routing, billing or output quality.
Rollback removes the additive CLI/helpers/docs; no stored state is migrated
and no policy is activated. Review correctness, compatibility, security and
regression coverage before ordinary CI-gated merge.
