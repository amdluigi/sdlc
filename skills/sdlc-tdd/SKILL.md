---
name: sdlc-tdd
description: 'Use when new behavior or a bug fix changes executable behavior.'
license: MIT
metadata:
  category: implementation
  version: "1.0.0"
  sdlc-provider-schema: "1"
  sdlc-compatible: ">=1.0.0 <2.0.0"
  sdlc-modules: "tdd"
---

# Test-driven development module

Use this module for new behavior and bug fixes. It owns implementation order
and proof that a test detects missing or defective behavior. The testing
module remains the final owner of acceptance coverage and verification.

Do not apply strict TDD to behavior-preserving documentation, formatting,
comments, metadata, or similarly small non-behavioral changes.

## Required cycle

For each behavior:

1. **Red**: write the smallest test of observable behavior before production
   implementation. Run it and confirm it fails for the expected missing
   behavior, not a syntax, fixture, import, or environment error.
2. **Minimal green**: add only enough implementation to pass that test. Run
   the focused test and relevant existing tests.
3. **Refactor**: improve names or structure only while tests remain green.
4. Repeat with the next behavior.

For a bug fix, reproduce the defect with a failing regression test before the
fix when technically safe. The first plausible fix is not a substitute for a
reproduction.

Tests exercise real behavior. Use mocks only at genuine external seams such as
a remote service, operating-system boundary, clock, or nondeterministic
hardware. Do not mock the unit under test or internal collaborators merely to
make a test easy to write.

## Evidence contract

Record inspectable evidence for each behavior:

- the test and acceptance criterion or change-contract behavior it covers;
- the red command and expected behavioral failure;
- the minimal implementation that made it green;
- the green command and result;
- any refactor and the passing result after it.

A test written after implementation, a test that passed on its first run, or a
description of a hypothetical failure does not satisfy the red state. Existing
code cannot be retained as a reference and then presented as test-first work.
Delete code-first implementation and restart from the failing test, or record
a valid technical exception.

## Technical exceptions

An exception is valid only for:

- generated output whose maintained source or generator is tested first;
- configuration-only behavior where the target system cannot be executed
  safely or deterministically in the repository;
- unsafe reproduction that could affect real users, production data, money,
  privacy, or irreversible state.

Record the applicable category, concrete technical reason, affected behavior,
and strongest safe alternative evidence. Suitable alternatives include a
generator test, schema or parser validation, dry run, isolated contract test,
captured pre-fix output tied to the defect, or a safe mutation proving the
assertion can fail.

Convenience, time pressure, small diff size, absent tests, legacy code, sunk
cost, or implementation already being written are not technical exceptions.
When no credible alternative exists, disclose the evidence gap and do not
claim TDD satisfaction.

## Relationship to testing

TDD answers whether implementation proceeded through sensitive red, minimal
green, and refactor steps. Testing answers whether the final revision has
complete, current acceptance coverage across the required test levels. Reuse
the same commands and results when they satisfy both contracts, but assess
each responsibility independently.

## Exit

This module is satisfied when every new or corrected behavior has inspectable
red-before-green evidence using real behavior, followed by a minimal passing
implementation and safe refactor, or a narrowly valid technical exception
with the strongest alternative evidence.

## Red flags

- Production implementation existed before the failing test.
- The new test passed on its first run.
- A mock verifies calls instead of observable behavior.
- A bug fix has no safe reproduction even though one is feasible.
- "The change is small" is used to avoid TDD for changed behavior.
- Final test coverage is mistaken for test-first evidence.

Any red flag means stop, restore the red state safely, and restart the cycle.
