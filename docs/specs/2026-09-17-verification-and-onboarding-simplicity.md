# Verification and onboarding simplicity

## Status

Approved for implementation.

## Problem

SDLC has strong lifecycle and release safeguards, but maintainers currently
pay for repeated full test execution and users must read advanced architecture
before finding the path relevant to them.

The simplification must reduce repeated work and navigation cost without
weakening release, privacy, evidence, or compatibility guarantees.

## Goals

1. Give users and maintainers three obvious commands:
   - `verify.bat` for routine local confidence;
   - `publish.bat --dry-run` for a complete release rehearsal;
   - `publish.bat` for verified publication.
2. Run each expensive suite at most once for one unchanged release tree.
3. Keep the public snapshot, privacy scan, installation matrix, manifest,
   release tag, and public CI requirements unchanged.
4. Make the README lead with three paths:
   - use SDLC;
   - configure or extend SDLC;
   - maintain and release SDLC.
5. Add no lifecycle modules, provider concepts, schemas, or external
   dependencies.

## Non-goals

- Reducing the final release evidence contract.
- Adding live-host evidence in this change.
- Adding public contribution ingestion.
- Caching successful evidence across different Git tree digests.
- Automatically selecting focused tests from an untrusted diff.

## Verification tiers

### Fast local tier

`verify.bat` resolves its own repository and invokes a private standard-library
orchestrator. It runs:

1. dedicated side-effect-free private verification contract tests;
2. repository structural validation;
3. qualification manifest verification;
4. Git diff, cache, and prohibited-trailer hygiene.

It does not run the complete public unit suite or perform network, commit,
tag, or push operations.

### Release rehearsal tier

`publish.bat --dry-run` runs the complete release workflow without remote
effects:

1. the fast private tier;
2. the remaining private publication and recovery tests once;
3. exact-ref audit and deterministic export;
4. the complete public unit and installation suite once;
5. public release verification and shell syntax checks;
6. outgoing public change summary.

### Publication tier

`publish.bat` reuses the rehearsal result produced in the same process and
bound to the same private commit, public base, candidate tree digest, version,
and configuration. It does not rerun a suite after the candidate has already
passed and no relevant bytes changed.

Publication still requires final authorization, private-first push order,
public commit and push, publication tag, and remote verification.

## Evidence binding

Reused verification is process-local only. A release preparation record
contains:

- private commit;
- fetched private and public bases;
- release version;
- exported tree digest;
- commands completed and their successful exit status.

Any changed commit, base, version, exported digest, configuration, or checkout
state invalidates the preparation and requires fresh verification.

No persistent success cache is introduced.

## Documentation structure

The public README begins with a short chooser:

1. **Use SDLC**: install and start in a project.
2. **Configure or extend SDLC**: modules, providers, extensions, memory, and
   external specifications.
3. **Maintain and release SDLC**: validation, contribution, qualification,
   and publication.

Advanced material remains in the repository and is linked from the chooser.
No public capability documentation is removed.

## Error handling

- Every command fails nonzero with one clear failing tier and command.
- Fast verification never reports release readiness.
- Release rehearsal never commits, tags, or pushes.
- Publication never proceeds from partial, stale, or differently bound
  verification.
- Existing fail-closed privacy and repository-identity errors remain
  authoritative.

## Testing

Tests must prove:

- batch launchers resolve their own repository, forward arguments, suppress
  bytecode, and preserve exit codes;
- the fast tier runs only its declared commands;
- one publication process runs private publication tests once and the public
  full suite once;
- changed evidence bindings prevent reuse;
- dry-run has no commit, tag, or push effects;
- public and private documentation expose the three entry paths;
- all existing publication recovery and privacy tests remain green.

## Success criteria

- Routine `verify.bat` completes materially faster than the prior full release
  command.
- One unchanged publication performs no duplicate complete public test suite.
- The full release gate and public CI remain green.
- A new user can choose the correct path from the first README screen.
