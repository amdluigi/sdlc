---
name: sdlc-testing
description: 'Use when behavior, bug, refactor, tests, or non-trivial verification are in scope.'
license: MIT
metadata:
  category: verification
  version: "1.0.0"
  sdlc-provider-schema: "1"
  sdlc-compatible: ">=1.0.0 <2.0.0"
  sdlc-modules: "testing"
---

# Testing checklist

Testing owns final coverage, test-level selection, and verification of the
current revision. The TDD module separately owns implementation order and
red-before-green sensitivity. Reuse valid evidence across both modules without
collapsing their exit signals.

## Before writing tests

- Identify the project's existing test framework and conventions (look at
  `PROJECT-STANDARDS.md` first, then existing test files). Don't introduce a
  second test framework without a strong reason.
- Identify the test command(s) (unit, integration, e2e, lint/typecheck) from
  `PROJECT-STANDARDS.md`, `package.json`/`Makefile`/CI config, etc.

## What to test

- **Acceptance criteria**: map every behavioral criterion in the change
  contract to at least one automated test. Use an explicit verification step
  only for non-behavioral criteria or behavior that cannot reasonably be
  automated, and state why.
- **PRD traceability**: when a PRD is selected, label acceptance evidence with
  its `AC-*` identifier and confirm every approved `AC-*` has evidence. For
  reconciled requirements, retain the authoritative artifact and report
  references so source selectors remain inspectable.
- **New behavior**: at least one happy-path test and the realistic edge
  cases (empty input, boundary values, error/exception paths, permissions
  denied, concurrent access if relevant).
- **Bug fixes**: confirm the TDD evidence demonstrates the regression test
  failed before the fix, or assess its recorded technical exception. Then
  include the test in final verification.
- **Refactors**: existing tests should continue to pass unchanged; if they
  need to change, make sure that's because the observable contract actually
  changed, not because the test was weakened to pass.
- **Public APIs/contracts**: test the contract (inputs/outputs, error
  shapes), not just internal implementation details.

## Confirm test sensitivity

- **Bug fixes**: before implementing the fix, run the smallest regression
  test or deterministic reproduction and confirm it fails for the expected
  reason. Run it again after the fix and confirm it passes.
- **Fix already present**: when safe, prove the red state from an isolated
  baseline checkout, worktree, temporary reversal, or focused mutation. Do
  not disrupt shared work or unsafe environments merely to manufacture a
  failure.
- **Red state impractical**: explain the technical or safety constraint and
  provide the strongest alternative evidence, such as captured pre-fix
  output, production traces tied to the root cause, or a mutation that proves
  the assertion detects the defect.
- **New behavior**: require the TDD module's observed missing-behavior failure
  before implementation. Generated output, configuration-only changes, and
  unsafe reproduction use only the TDD module's narrow technical-exception
  contract.

A test that only ever passed demonstrates coverage, not that it can detect
the missing or defective behavior. User preference, deadline pressure, sunk
implementation cost, or a desire to avoid an isolated check are not technical
limitations. If direct reversal is disallowed, use a non-destructive baseline
or mutation method. If no credible method is safe or possible, disclose the
evidence gap and do not claim the regression test has been proven sensitive.

## Running tests

- Actually run the relevant test command(s); do not claim "this should work"
  without running it. Prefer the narrowest command that covers the change,
  escalate to the full suite when the change is cross-cutting or before
  declaring the task done.
- If tests fail for reasons unrelated to your change (pre-existing flake/
  failure), say so explicitly rather than silently ignoring it.
- If the project has no test infrastructure at all, say so explicitly and
  ask whether to add minimal test scaffolding, rather than skipping silently.
- For changes spanning boundaries such as API/database, UI/API, service/
  queue, or auth/session, run the narrowest relevant integration or contract
  test. Slow tests are a reason to target the command, not to skip boundary
  verification.
- Record the command and result used as evidence. A previous run or expected
  CI result is not fresh evidence.

## Definition of done for this phase

- New/changed behavior has test coverage.
- Bug regression tests demonstrated sensitivity through a red-before-green
  run, or the limitation and alternative evidence are documented.
- Every behavioral acceptance criterion has an automated test unless a
  stated technical limitation makes that impractical; all other criteria
  have explicit verification.
- The relevant test command was run and passed (or failures are explained).
- Linting/type-checking (if configured) passes.
