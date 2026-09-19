---
name: sdlc-dependency-supply-chain
description: "Use when a change adds, removes, replaces, updates, pins, vendors, generates, downloads, or changes the resolution or execution of a third-party dependency, package manager, registry, lockfile, build plugin, action, container base, or fetched build artifact."
metadata:
  sdlc-provider-schema: "1"
  sdlc-compatible: ">=1.0.0 <2.0.0"
  sdlc-modules: "dependency-supply-chain"
---

# Dependency supply chain module

## Bounded responsibility

Use this module to assure necessity, provenance, reproducibility, advisory and
license posture, transitive impact, and update risk for third-party dependency
changes and package acquisition behavior. It owns dependency-specific
evidence, not a general security audit or automatic package updating.

## Positive trigger

Load this module when a change adds, removes, replaces, updates, pins, vendors,
generates, downloads, or changes the resolution or execution of a third-party
dependency, package manager, registry, lockfile, build plugin, action,
container base, or fetched build artifact.

Using an already-declared, unchanged dependency through an existing supported
API does not trigger this module.

## Non-trigger counterexamples

- Code imports an existing locked dependency without resolution changes.
- First-party internal modules are renamed in one repository.
- A formatting-only lockfile difference is discarded without resolution change.
- Runtime application data is fetched but is not a build or dependency artifact.
- A first-party vulnerability is handled by security-auth.

## Evidence contract

1. Identify direct and transitive additions, removals, versions, sources,
   integrity data, lockfile changes, scripts or plugins, and build-time or
   runtime placement.
2. Explain why platform, standard-library, or current dependency capabilities
   cannot meet the accepted outcome and compare the cost of no change.
3. Record configured source, available publisher or owner, integrity or
   signature mechanism, release identity, and vendored or generated origin.
4. Record current advisory and maintenance evidence using repository-approved
   sources, including source identity, result time or advisory-database
   identity, severity disposition, supported versions, and signs of
   abandonment or compromise. Treat evidence as stale after the
   advisory-database changes unless its recorded identity still matches.
5. Identify declared licenses and compatibility with project policy,
   escalating ambiguity instead of guessing.
6. Run focused changed-API tests and a clean or frozen restore or equivalent
   reproducibility check that detects unexpected artifacts or lifecycle
   scripts where supported.
7. For high-risk updates, inspect release guidance and transitive changes and
   record rollback and residual risk. Evaluation alone causes no network,
   install, or update action.

Evidence must be inspectable, scope-aligned, and current. Reuse qualifying
evidence regardless of producer.

## Overlap rules

- Change contract and PRD own the feature need and accepted constraints. This
  module challenges dependency necessity without changing the outcome.
- Planning owns sequencing. This module supplies resolution, compatibility,
  license, advisory, and rollback work.
- TDD owns implementation order for behavior. Provenance and reproducibility
  remain outside TDD.
- Implementation owns manifest, lockfile, adapters, and code. This module
  requires the minimum footprint and review of generated and transitive deltas.
- Testing owns final project verification. This module owns clean restore,
  resolution diff, package compatibility, and lifecycle-script evidence.
- Security-auth owns exploitability, threat exposure, secrets, and mitigation.
  This module owns necessity, provenance, advisories, transitive components,
  and supply-chain mechanics.
- Operational readiness owns staged rollout and rollback for risky runtime
  updates. This module supplies update and compatibility risk.
- API compatibility owns this project's consumer contract. This module checks
  compatibility with the changed dependency API and release.
- Review inspects manifests, lockfiles, generated files, source changes, and
  evidence. A scanner result does not replace human delta review.

## Right-sizing

- Scope evidence to changed third-party components and their transitive delta,
  not the entire unchanged graph.
- Use repository-approved package, advisory, and license tooling. Do not add a
  second package manager or scanner solely for this module.
- Increase migration, rollback, and transitive review for high-risk runtime,
  build, action, base-image, or major-version changes.

## Steps

1. Identify exact direct, transitive, source, integrity, script, and lockfile
   deltas before installation or update.
2. Prove necessity and prefer existing capabilities when sufficient.
3. Follow repository package manager, source, lock, advisory, and license
   policy.
4. Verify provenance, integrity, maintenance, release guidance, supported
   runtimes, advisories, and license.
5. Inspect transitive additions, lifecycle scripts, generated code, plugins,
   and unexpected resolution changes.
6. Update the smallest coherent component set and preserve the lockfile.
7. Run focused compatibility tests and a clean or frozen restore.
8. Record rollback, residual advisories, exceptions, and freshness. Never
   auto-publish, auto-merge, or contact a registry merely because the module
   triggered.

## Exit

This module is satisfied when each changed third-party component is necessary,
resolves reproducibly from approved provenance, has current advisory and
license assessment, has reviewed transitive and build-script impact, and
passes focused compatibility plus repository verification with residual risk
disclosed.

## Common shortcuts to reject

- Popularity, successful installation, or no critical advisory is the whole
  assessment.
- The newest version is accepted without compatibility and rollback evidence.
- Unrelated bulk upgrades are bundled into an urgent update.
- Evaluation automatically installs, updates, publishes, merges, or contacts
  an external source.

## Behavioral cases

| Case ID | Type | Observable expectation |
|---|---|---|
| `supply-new-package-positive` | positive | A new package triggers necessity, provenance, integrity, advisory, license, transitive and script, lockfile, clean-restore, focused-test, and rollback evidence. |
| `supply-existing-import-negative` | negative | Using an unchanged locked dependency does not load this module. |
| `supply-first-party-counterexample` | counterexample | A first-party package refactor remains implementation and testing scope. |
| `supply-emergency-update-pressure` | pressure | An emergency release still requires scoped exploitability, provenance, transitive and script review, license, compatibility, frozen restore, tests, and rollback without automatic side effects. |
