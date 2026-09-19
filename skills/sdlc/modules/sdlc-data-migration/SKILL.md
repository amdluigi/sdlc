---
name: sdlc-data-migration
description: "Use when a change transforms, backfills, moves, reinterprets, or deletes durable production data; changes a production schema in a way that requires old and new application or schema versions to coexist; or introduces a migration whose failure could leave persistent state partial or invalid."
metadata:
  sdlc-provider-schema: "1"
  sdlc-compatible: ">=1.0.0 <2.0.0"
  sdlc-modules: "data-migration"
---

# Data migration module

## Bounded responsibility

Use this module to assure safe transformation, backfill, movement,
reinterpretation, or deletion of durable production data, including
expand-contract sequencing, integrity, resumability, mixed application
versions, rollback or mitigation, and rehearsal. It owns migration-specific
proof, not general database design or deployment authorization.

## Positive trigger

Load this module when a change transforms, backfills, moves, reinterprets, or
deletes durable production data; changes a production schema in a way that
requires old and new application or schema versions to coexist; or introduces
a migration whose failure could leave persistent state partial or invalid.

An unused additive nullable field without backfill, consumer switch,
destructive step, or mixed-version requirement does not trigger by itself.

## Non-trigger counterexamples

- A disposable test database fixture is recreated from scratch.
- An unused nullable column is added with an atomic deployment and no backfill.
- An in-memory cache structure changes without durable data.
- A local developer-only seed file changes.
- A public payload changes without stored-state transformation.

## Evidence contract

1. Inventory source and target representations, volume and shape assumptions,
   invariants, ownership, retention, and destructive or irreversible steps.
2. Separate compatible expand, backfill, verification, consumer switch, and
   destructive contract stages with gates and prerequisites.
3. Cover batching, checkpoints, idempotency, resume after failure, concurrency
   with live writes, error quarantine, and bounded resources where applicable.
4. Reconcile counts and domain invariants, sample transformed records, detect
   partial state, and define acceptance thresholds.
5. Record a production-like rehearsal's duration, load, failures,
   mixed-version compatibility, and post-migration validation.
6. Test restoration of code, schema, and data where reversible. Otherwise
   prove a forward fix, restore, or other mitigation and state irreversibility.

Evidence must be inspectable, scope-aligned, and current. Reuse qualifying
evidence regardless of producer.

## Overlap rules

- Change contract and PRD own data meaning, authority, retention, and accepted
  outcomes. This module exposes costly or irreversible decisions.
- Planning owns overall dependencies. This module supplies expand-contract
  stages, gates, inputs, outputs, and integration placement.
- TDD owns red-before-green for migration behavior. Rehearsal and
  production-like integrity proof remain this module's responsibility.
- Implementation owns migration code and reversible slices.
- Testing owns final acceptance verification. This module owns integrity,
  resume and idempotency, mixed-write, version-matrix, and rehearsal evidence.
- Security-auth owns access, encryption, privacy, and retention risk. This
  module owns preservation of authorized data meaning and integrity.
- Operational readiness owns deployment stages, owners, rollback decisions,
  and production signals. This module proves migration mechanics and gates.
- API compatibility owns consumer-visible transition. This module owns durable
  state even when dual-read or dual-write evidence contributes to both.
- Review checks destructive steps and evidence; code inspection alone cannot
  establish migration safety.

## Right-sizing

- For a bounded, reversible transformation, use a proportionate data sample
  and interruption test while preserving explicit invariants.
- Increase rehearsal volume, mixed-version coverage, and recovery proof with
  data volume, live writers, irreversibility, or destructive stages.
- Do not apply production migration ceremony to disposable fixtures or an
  unused additive field.

## Steps

1. Inventory durable data, representations, volumes, invariants, readers,
   writers, retention, and authority.
2. Identify old and new application and schema combinations that can coexist.
3. Design expand, resumable backfill, verification, switch, and delayed
   contract stages.
4. Define checkpoints, idempotency, retries, quarantine, live-write handling,
   and resource limits.
5. Build deterministic integrity reconciliation.
6. Rehearse on production-like volume and shape, including interruption and
   resume when partial state is possible.
7. Test rollback across code, schema, and data or prove a forward mitigation.
8. Record gates, observed load and duration, irreversibility, and cleanup
   timing. Mark evidence stale after relevant migration, invariant, model,
   reader, writer, data-shape, volume, or deployment-sequence changes.

## Exit

This module is satisfied when expand, backfill, switch, and contract stages
are explicit; current production-like rehearsal proves integrity,
idempotency or resumability, mixed-version safety, and failure handling; and
rollback is tested where possible, otherwise a tested mitigation and
irreversibility statement are present.

## Common shortcuts to reject

- Migration syntax success or CI is treated as production migration proof.
- A plan paragraph is treated as tested rollback evidence.
- Old data is dropped before compatibility and integrity gates pass.
- Informal monitoring substitutes for rehearsal and deterministic checks.

## Behavioral cases

| Case ID | Type | Observable expectation |
|---|---|---|
| `migration-live-backfill-positive` | positive | A live status rewrite triggers expand-contract, mixed versions, resumable batching, concurrent writes, integrity, rehearsal, and rollback or mitigation evidence. |
| `migration-test-fixture-negative` | negative | Recreating disposable test fixtures does not load this module. |
| `migration-additive-column-counterexample` | counterexample | An unused nullable additive column without coexistence or backfill remains ordinary implementation and testing scope. |
| `migration-destructive-pressure` | pressure | A one-step destructive deadline does not bypass compatible staging, rehearsal, integrity gates, and tested rollback or forward mitigation. |
