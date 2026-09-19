---
name: sdlc-implementation
description: "Use when code or configuration changes are required."
metadata:
  sdlc-provider-schema: "1"
  sdlc-compatible: ">=1.0.0 <2.0.0"
  sdlc-modules: "implementation"
---

# Incremental implementation module

Implement the agreed change in the thinnest complete, independently
verifiable slices. Each slice should leave the repository in a coherent,
working state and reduce uncertainty without expanding the change contract.

For a trivial single-function or one-file change, the whole change can be one
slice. Do not invent slices that add ceremony without isolation or feedback
value.

## 1. Choose a slicing strategy

Use the smallest strategy that fits:

- **Vertical slice (default)**: deliver one observable path through every
  required layer, such as storage, API, and a minimal UI, before adding the
  next user behavior.
- **Contract-first**: define and verify an interface first when teams,
  components, or frontend/backend work must progress independently. Implement
  each side against the same contract, then integrate.
- **Risk-first**: prove the highest-risk assumption before investing in
  dependent work. Keep feasibility probes throwaway unless the change
  contract and tests promote them into maintained code.
- **Migration sequence**: use additive/expand steps, compatibility behavior,
  migration or backfill, consumer switch, and removal as separate slices when
  old and new versions must coexist.

Prefer vertical slices over completing every layer horizontally. A database
layer with no usable path is progress only when contract-first or risk-first
sequencing justifies it.

## 2. Define the next slice

Before editing, state:

- **Outcome**: one behavior or risk reduction this slice completes.
- **In scope**: exact files, interfaces, and supporting work needed now.
- **Out of scope**: later slices and unrelated improvements.
- **Verification**: the narrowest tests, build, type, lint, integration, or
  manual check that proves this slice.
- **Exposure**: whether users can reach it safely.
- **Reversal**: how this slice can be reverted independently.

One slice changes one logical thing. Necessary cross-layer work belongs in the
same vertical slice; independently valuable behavior belongs in another.

## 3. Implement simply and safely

When the TDD module is selected, enter each behavior slice through its failing
test. Do not begin production implementation until the module's red state is
observed or a valid technical exception is recorded. A later passing test
cannot retroactively prove test-first order.

- Follow established stack, naming, formatting, error handling, and directory
  patterns.
- Prefer the naive, obviously correct implementation over speculative
  abstractions. Add an abstraction when current repeated use justifies it,
  not for hypothetical flexibility.
- Prefer existing dependencies. Introduce a dependency only when its value,
  security, maintenance, and compatibility cost are justified.
- Use conservative defaults. New behavior should be opt-in when unintended
  activation creates risk.
- Keep errors explicit. Do not hide failure behind silent defaults or
  success-shaped fallbacks.
- Do not absorb adjacent cleanup, modernization, dependency upgrades,
  refactors, or extra features. Record useful observations as deferred work.
- Respect unrelated worktree changes. Do not revert, overwrite, or claim work
  you do not own.

## 4. Keep incomplete work unexposed

Every slice must be safe to integrate even when the full feature is not
finished.

- Prefer a repository-standard feature flag for incomplete user-visible
  behavior.
- Default new flags off unless the approved rollout says otherwise.
- When no flag system exists, keep incomplete paths unreachable through
  additive internals, contract-compatible stubs, or an isolated branch.
- Do not ship a fake-success stub or expose a half-complete workflow.

Use the operational-readiness module when a flag, migration, compatibility
period, or staged rollout affects production behavior.

## 5. Reach a verified checkpoint

After each slice:

1. Run only the checks affected by the slice, using repository commands.
2. Confirm the project remains buildable and existing covered behavior still
   works.
3. Exercise the slice's observable path or contract.
4. Record fresh evidence and update the coverage ledger.
5. Reassess which downstream evidence became stale. Do not rerun successful
   checks when no relevant code or dependency changed.
6. Inspect the slice diff for scope, temporary code, debug output, secrets,
   and accidental files.

Do not begin the next slice while the current checkpoint is broken. Fix it,
revise the slice, or explicitly stop as blocked.

A checkpoint may be a Git commit only when the user requested commits or
repository policy permits autonomous commits. Otherwise preserve a clean,
described checkpoint without committing.

## 6. Preserve reversibility

- Make slices additive where practical.
- Keep modifications focused so a slice can be reverted independently.
- Separate destructive removal from the compatible replacement that precedes
  it.
- Pair data migrations with a rollback or tested mitigation.
- Avoid mixing a feature, unrelated refactor, and build-system change in one
  slice.

If a slice cannot be independently reversible, state why and load
operational-readiness when its trigger applies.

## 7. Continue or stop

Move to the next slice only when:

- this slice's outcome is complete;
- its verification is fresh;
- the repository is in a coherent state;
- the next slice still belongs to the same change contract.

Stop and revisit planning or the change contract when discoveries add an
independent outcome, invalidate acceptance criteria, or make the remaining
sequence unsafe.

## 8. Synchronize design drift

When implementation reveals that an accepted requirement, public contract,
or architecture decision must change:

1. Stop the current slice at a coherent checkpoint.
2. Update the authoritative specification or design artifact when one exists.
   Mark the old decision superseded rather than leaving contradictory text.
3. When a PRD is selected and promised behavior changes, update its numbered
   requirements, increment its version, return it to draft, and obtain renewed
   approval.
4. When project memory is selected, record the decision, rationale, rejected
   alternatives, and affected architecture or rules.
5. Revise the plan and slice sequence.
6. Mark dependent tests, security analysis, operational evidence, review, and
   handoff stale.
7. Obtain renewed approval when the change is costly, public, irreversible,
   or changes the promised outcome.

Do not update a design document for routine implementation detail. Synchronize
only decisions that would otherwise make the accepted design misleading.
Do not resume implementation while an authoritative design still contradicts
the accepted change or dependent evidence still appears current.

## Exit

The implementation module is satisfied when every acceptance criterion is
implemented through verified slices, the final work product remains within
the coherent boundary, accepted design artifacts describe the final
decisions, the approved PRD version remains accurate when selected,
incomplete behavior is safely hidden, and each increment has a credible
reversal path.

## Common shortcuts that fail

| Shortcut | Why it fails |
|----------|--------------|
| "I will test everything at the end" | Faults compound across slices and become harder to localize. |
| "It is faster to implement all layers first" | Horizontal batches delay usable feedback and hide integration mistakes. |
| "I will add the feature flag later" | Incomplete behavior can become reachable before it is safe. |
| "This cleanup is in the same files" | File proximity does not make it part of the same outcome. |
| "I should commit every checkpoint" | Commit policy belongs to the user or repository, not this module. |
| "We can update the design after coding" | Continuing against a known-stale design compounds incorrect plans, tests, and review. |
