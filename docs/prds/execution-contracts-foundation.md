---
type: prd
id: execution-contracts-foundation
status: approved
version: 1
---

# Product requirements: Execution contract foundation

## Problem and context

The suite has delivery guidance, validated dependency plans, and limited
plan continuity. Future execution tooling needs explicit data boundaries
without changing existing workflows or activating orchestration.

## Target users and benefit

Maintainers and future first-party consumers gain strict, testable contracts.
Existing users retain their current default workflow and configuration.

## Outcome

Ship inactive, additive execution-data schemas and explicitly callable
validators, with compatibility and side-effect evidence.

## Goals

- Define execution plan, task brief, task result, and event contracts.
- Reject malformed data and inconsistent declared relationships.
- Preserve existing interfaces, defaults, skill behavior, and installation.

## Non-goals

- Scheduling, event reduction, storage, live monitoring, and new CLI commands.
- Dispatch, approval enforcement, authentication, or evidence acceptance.
- Agent installation, model routing, retries, telemetry, or dashboards.
- Existing contract/configuration migration, release tags, or automatic
  updates of user installations.

## User scenarios

1. A consumer explicitly validates a plan without dispatching or recording work.
2. Invalid prerequisites, references, or parallel groups produce stable errors.
3. A result or event for another task or plan is refused.
4. Existing plans, cursors, providers, metrics, and evaluator records continue
   working without importing the new helper.

## Functional requirements

- **FR-1**: Provide four strict version-1 JSON Schemas and matching Python
  validation APIs for plans, briefs, results, and events.
- **FR-2**: Validate task identity, source bindings, prerequisites,
  consumes/produces, and conservative dependency/parallel-group invariants,
  without claiming scheduling readiness.
- **FR-3**: Validate plan/task/attempt bindings, artifact scope and declared
  verification outcomes in briefs/results without authenticating or accepting
  evidence.
- **FR-4**: Validate event envelopes, applicable references, sequence/time
  representations and known type-specific payloads without applying events.
- **FR-5**: Reject unknown versions/fields, duplicate JSON keys, unsafe
  artifact paths, malformed identifiers and invalid numbers with stable errors.
- **FR-6**: Preserve existing defaults and contracts; new validation must not
  dispatch, write, access the network, migrate configuration, record telemetry,
  or load skills.
- **FR-7**: Include new files in qualified installations and document their
  structural-only, inactive, versioned boundary.

## Acceptance criteria

- **AC-1** (`FR-1`): All schemas have unique strict versioned identities;
  valid/invalid contract fixtures cover each API and schema field constraints.
- **AC-2** (`FR-2`): Tests cover valid sequential/parallel plans, duplicate
  tasks/producers, unknown/self/cyclic dependencies and dependency conflicts
  inside parallel groups.
- **AC-3** (`FR-3`): Tests reject mismatched plan/task/attempt bindings, scope
  violations and invalid outcomes; valid receipts do not approve or complete
  work.
- **AC-4** (`FR-4`): Tests cover every event type, payload/reference rule,
  malformed time and invalid sequence; validation produces no reduced state.
- **AC-5** (`FR-5`): Boundary tests cover duplicate keys, missing/extra fields,
  versions, booleans as integers, non-finite/negative numbers, IDs and unsafe
  paths with stable error codes/pointers.
- **AC-6** (`FR-6`): Tests show immutable caller input and absent runtime
  side effects; existing regressions and required repository checks pass
  without relaxing safeguards.
- **AC-7** (`FR-7`): Synthetic installations preserve source/file parity and
  existing skill/module/profile semantics; documentation distinguishes
  structural validity from approval, acceptance and execution.

## Data, permissions, privacy, and security

Only explicitly supplied data is inspected. Artifact paths remain
project-relative and are not dereferenced to assess evidence. The existing
strict reader may load an explicitly named input file. No records are created.
Actor and verification fields are claims, not authenticated observations.

Logging consent, retention, approval provenance, execution permissions and
runtime budgets require separately approved future work.

## Constraints and dependencies

- Python standard library only; reuse suitable existing strict JSON/error
  helpers.
- Preserve old schema meanings, configuration, runtime helpers and commands.
- New contracts are not a scheduler, reducer, telemetry source or gate.
- Qualification must include the exact new inventory and canonical hashes.
- No private management content is required by public consumers.

## Success measures

The mapped acceptance tests, unchanged existing behavior and absence of
activation define success. No cost or speed improvement is claimed.

## Open decisions

None for this inactive slice. Runtime policy is explicitly deferred.

## Approval

- Status: Approved
- Approver: Maintainer
- Evidence: Explicit maintainer approval of contracts-only requirements and
  implementation plan on 2026-11-01.
- Approved version: 1
