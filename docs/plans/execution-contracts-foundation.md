---
type: implementation-plan
prd-path: docs/prds/execution-contracts-foundation.md
prd-id: execution-contracts-foundation
prd-version: 1
---

# Execution contract foundation implementation plan

Add four version-1 schemas and an inactive standard-library validator.
Reuse strict JSON/error helpers without modifying existing runtime behavior.
Keep event reduction, storage, dispatch, models, telemetry and UI excluded.

| Task | PRD refs | Outcome | Prerequisites | Consumes | Produces | Execution | Verification |
|------|----------|---------|---------------|----------|----------|-----------|--------------|
| scope | FR-6, FR-7, AC-6, AC-7 | Approve scope and protect existing defaults | none | none | approved-contract | sequential | PRD and plan validate; baseline is recorded |
| tests | FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, AC-1, AC-2, AC-3, AC-4, AC-5, AC-6 | Sensitive contract assertions before implementation | scope | approved-contract | failure-assertions | sequential | Observe expected missing-behavior red |
| contracts | FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, AC-1, AC-2, AC-3, AC-4, AC-5, AC-6 | Strict schemas and isolated validation | tests | failure-assertions | execution-contracts | sequential | Valid, invalid, relationship and side-effect tests pass |
| qualification | FR-7, AC-7 | Complete packaging and documentation | contracts | execution-contracts | qualified-contracts | sequential | Exact inventories and copy/link parity pass |
| verification | FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7, AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7 | Current compatibility and review evidence | qualification | qualified-contracts | acceptance-evidence | sequential | Targeted/full tests, repository validation, manifest and final review pass |

## Compatibility and reversal

Old skills, schemas, configuration, providers, commands and runtime helpers
remain unchanged. The new library is called explicitly, never from existing
entrypoints. Reversal removes the additive files and their inventory updates
together, with no user data migration.
