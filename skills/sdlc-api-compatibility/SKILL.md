---
name: sdlc-api-compatibility
description: 'Use when a change adds, removes, or modifies a consumer-visible request, response, command, event, schema, serialization, error, SDK, generated-client, or versioning contract, including behavior observable by an independently deployed or external consumer.'
license: MIT
metadata:
  category: compatibility
  version: "1.0.0"
  sdlc-provider-schema: "1"
  sdlc-compatible: ">=1.0.0 <2.0.0"
  sdlc-modules: "api-compatibility"
---

# API compatibility module

## Bounded responsibility

Use this module to assure compatibility of changed consumer-visible
interfaces, including HTTP or RPC APIs, events, schemas, SDKs, CLIs, file
formats, error contracts, and generated clients. It owns consumer inventory,
compatibility classification, versioning, and transition evidence, not
general implementation correctness or data transformation.

## Positive trigger

Load this module when a change adds, removes, or modifies a consumer-visible
request, response, command, event, schema, serialization, error, SDK,
generated-client, or versioning contract, including behavior observable by an
independently deployed or external consumer.

Internal function signatures trigger only when consumed across an
independently versioned component boundary.

## Non-trigger counterexamples

- A private helper signature changes with all callers in one atomic build.
- An endpoint is optimized while requests, responses, errors, timing promises,
  and side effects remain compatible.
- Internal database columns change without crossing a serialization boundary.
- Test fixtures are reorganized without changing a maintained contract.
- A private method is added behind an unchanged public interface.

## Evidence contract

1. Produce a before and after contract delta covering operations, fields,
   types, defaults, validation, side effects, ordering, errors, and versions.
2. Inventory internal, external, generated, and independently deployed
   consumers, or provide bounded evidence that none exist.
3. Classify each delta as compatible, conditionally compatible, or breaking
   for those consumers, including relevant serialization differences.
4. Exercise success and error shapes with current contract tests and prove the
   required old and new consumer or provider combinations.
5. Regenerate and check clients, schemas, documentation, examples, fixtures,
   and compatibility baselines through maintained sources when applicable.
6. For breaking changes, record explicit approval, versioning, deprecation or
   migration guidance, and rollout sequencing. Silent fallback is not
   compatibility evidence.

Evidence must be inspectable, scope-aligned, and current. Reuse qualifying
evidence regardless of producer.

## Overlap rules

- Change contract and PRD own promised external behavior and approval of
  breaking choices. This module does not silently choose compatibility policy.
- Planning owns tasks and sequencing. This module supplies contract-first,
  consumer-update, versioning, and mixed-version requirements.
- TDD owns implementation order. A consumer contract test may be red evidence;
  this module owns the breadth of combinations and generated-client checks.
- Implementation owns adapters, versions, deprecations, and contract code.
- Testing owns final acceptance coverage. This module owns semantic contract
  deltas, representative consumers, error contracts, and version matrices.
- Security-auth owns authorization, exposure, and unsafe input. This module
  owns stability of consumer-visible auth and error contracts.
- Operational readiness owns coexistence rollout and rollback. This module
  defines and proves the required provider and consumer version window.
- Data migration owns stored-state transformation and integrity. This module
  owns serialized and interface transition.
- Review consumes compatibility evidence and verifies the final contract diff.

## Right-sizing

- For a strictly additive compatible field, prove tolerant-reader behavior and
  affected generated artifacts without inventing a broad migration.
- For changed errors, defaults, validation, removal, or semantics, include the
  affected consumer matrix and transition policy.
- Private atomic interfaces remain implementation and testing scope.

## Steps

1. Identify authoritative interface artifacts and independently versioned
   consumers.
2. Produce a semantic before and after delta, including errors and promises.
3. Classify compatibility per consumer and resolve costly ambiguity.
4. Choose the smallest compatible strategy: additive field, tolerant reader,
   adapter, explicit version, or approved breaking release.
5. Update contract tests and generated artifacts from maintained sources.
6. Exercise required old and new combinations and representative clients.
7. Record deprecation, migration, rollout, rollback, and removal gates without
   duplicating operational readiness.
8. Mark evidence stale after contract, generator, serialization, validation,
   version, or consumer changes.

## Exit

This module is satisfied when affected consumers and contract deltas are
explicit; compatible and breaking changes are classified; required
versioning, deprecation, generated artifacts, and mixed-version behavior are
implemented; and current contract plus representative consumer evidence
passes.

## Common shortcuts to reject

- An unchanged status code or compiling schema is treated as semantic proof.
- Server unit tests substitute for old-client or generated-client evidence.
- Consumers are assumed to adapt without inventory or approval.
- Silent fallback is used instead of an explicit compatibility strategy.

## Behavioral cases

| Case ID | Type | Observable expectation |
|---|---|---|
| `api-error-shape-positive` | positive | An endpoint error-shape change triggers semantic diff, consumer inventory, old-client evidence, generated artifacts, and version or deprecation handling. |
| `api-private-helper-negative` | negative | A private helper changed with atomic callers does not load this module. |
| `api-storage-schema-counterexample` | counterexample | A stored-schema backfill without a consumer-visible contract remains data-migration scope. |
| `api-breaking-deadline-pressure` | pressure | A removal deadline does not bypass consumer inventory, approved version or deprecation handling, coordinated cutover, and mixed-version evidence. |
