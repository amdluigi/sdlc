# Release and launch module

## Bounded responsibility

Use this module when a completed change is being published, deployed, released,
or launched to users. It owns the release decision, version and audience,
release notes, rollout execution, rollback triggers, and post-release
acceptance. Operational readiness owns preparation before a release decision.

## Positive trigger

Trigger when a user asks to publish, deploy, release, launch, roll out, tag,
or make a completed change available to an external audience.

## Non-trigger counterexamples

Do not trigger for a local test run, a merge that has no release action, a
draft release note, or ordinary code implementation without a planned launch.

## Evidence contract

- Identify the exact revision, version, release audience, compatibility
  declaration, and approved release criteria.
- Provide release notes that state user-visible changes, migration or upgrade
  steps, known limitations, and rollback implications.
- Define rollout cohorts, success and failure signals, monitoring owner,
  decision window, and explicit rollback triggers.
- Verify the actual release artifact or deployment target before declaring
  release success.
- Record post-release smoke checks and the final launch, pause, rollback, or
  recovery decision. Never publish, deploy, tag, or push without explicit
  authorization.

## Overlap rules

Operational readiness supplies rollout and reversibility preparation.
API compatibility and data migration supply consumer and data evidence.
Observability supplies signals. Incident response takes ownership when active
harm occurs. This module never replaces a repository's release tooling.

## Right-sizing

A low-risk internal release may use one cohort and one smoke check. Public,
breaking, irreversible, or high-impact launches require explicit approval,
staged exposure, rollback ownership, and post-release monitoring evidence.

## Steps

1. Bind the release decision to the exact revision, version, and criteria.
2. Confirm the release artifact and user-facing notes.
3. Start the smallest safe rollout and observe the defined signals.
4. Pause or roll back when a trigger fires; otherwise expand only after the
   required decision window.
5. Record final post-release validation and residual risk.

## Exit

The release state is explicitly launch, pause, rollback, or recovery; current
artifact, rollout, signal, and post-release evidence support that state; and
any unresolved limitation is visible to the owner.

## Common shortcuts to reject

- Treating merge completion as proof of publication.
- Publishing before the artifact or target is verified.
- Using an informal monitoring promise instead of rollback triggers.
- Expanding rollout because a deadline exists rather than evidence supports it.

## Behavioral cases

| Case | Type | Required behavior |
|---|---|---|
| `release-launch-positive` | positive | Bind release criteria, stage rollout, and verify post-release state. |
| `release-merged-not-published-negative` | negative | Do not invoke launch work for a merge without a release action. |
| `release-rollback-counterexample` | counterexample | Require explicit signals and rollback ownership before expansion. |
| `release-deadline-pressure` | pressure | Refuse unverified publication or full rollout under deadline pressure. |
