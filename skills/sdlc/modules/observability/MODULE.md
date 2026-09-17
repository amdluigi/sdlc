# Observability module

## Bounded responsibility

Use this module to assure that changed telemetry and diagnostically
significant production paths emit useful, bounded, privacy-aware logs,
metrics, traces, and alert signals. It owns signal design and diagnostic
validation, not rollout authority, incident response policy, or all
application logging.

## Positive trigger

Load this module when a change adds, removes, or modifies logs, metrics,
traces, dashboards, or alerts; introduces or changes a service, queue,
scheduled job, or other asynchronous production boundary; or has an accepted
requirement for new diagnostic or operational signals.

A normal in-process path with no telemetry, asynchronous-boundary, or accepted
signal change does not trigger this module.

## Non-trigger counterexamples

- A local debug print is removed without changing production telemetry.
- A pure library function changes behind an unchanged service boundary.
- Test-only logging changes.
- A README explains existing metrics without changing their contract.
- Operational readiness reuses current signals without requiring new telemetry.

## Evidence contract

1. Map affected boundaries and important failure modes to named signals and
   state the diagnostic question each signal answers.
2. Use current sample output or a deterministic telemetry test to prove names,
   fields, units, status, correlation, and failure classification at the real
   instrumentation boundary.
3. Show that secrets, credentials, sensitive payloads, and unnecessary
   personal data are excluded or transformed according to project policy.
4. Review metric and attribute cardinality and bound material log or trace
   volume, sampling, and retention implications.
5. For changed alerts, identify destination or owner, threshold, window,
   severity, response, and validated fire and no-fire behavior.
6. Preserve or explicitly migrate dashboards, alerts, queries, and collectors
   when signal names or semantics change.

Evidence must be inspectable, scope-aligned, and current. Reuse qualifying
evidence regardless of producer.

## Overlap rules

- Change contract and PRD own product and operational outcomes. This module
  turns accepted diagnostic needs into a signal map.
- Planning owns work sequencing. This module identifies instrumentation,
  consumer updates, and verification tasks.
- TDD owns red-before-green. Instrumentation tests may participate, but this
  module separately judges signal usefulness, bounds, and privacy.
- Implementation owns telemetry code and configuration.
- Testing owns final acceptance checks and may cite this module's signal
  assertions and sample or query evidence.
- Security-auth owns leakage and access threats. This module minimizes
  sensitive telemetry and validates redaction without replacing security
  analysis.
- Operational readiness chooses rollout signals and actors. This module proves
  those signals exist, mean what the plan assumes, and can be queried.
- API compatibility owns transition for telemetry consumers when signal names
  are contracts. This module owns diagnostic semantics.
- Review triages stale dashboards, noisy signals, and privacy findings when
  this module triggers.

## Right-sizing

- Instrument only changed production boundaries and diagnostically important
  outcomes. Do not require logs in every function.
- Prefer the minimum signal set that answers defined questions.
- Reuse established naming, units, correlation, sampling, and field
  conventions rather than adding parallel telemetry patterns.

## Steps

1. Inventory affected boundaries, consumers, and important success and failure
   modes.
2. Start with diagnostic questions, then choose the minimum necessary signals.
3. Follow existing naming, units, correlation, sampling, and structure.
4. Exclude sensitive and high-cardinality values by design.
5. Preserve or migrate existing signal consumers when semantics change.
6. Exercise success and failure paths and inspect emitted or queryable output.
7. Validate alert fire and no-fire behavior and actionability when alerts
   change.
8. Record volume, cardinality, retention, and unresolved gaps. Mark evidence
   stale after relevant instrumentation or control-flow changes.

## Exit

This module is satisfied when each affected production boundary and failure
mode has current, queryable, privacy-safe diagnostic evidence with defined
meaning and bounded cardinality or volume, and applicable alerts have
actionable thresholds and validated routing or remain explicit missing
evidence.

## Common shortcuts to reject

- One unstructured failure log is treated as sufficient diagnosis.
- Raw payload logging is used to accelerate incident debugging.
- Unbounded labels or fields are accepted without volume review.
- An alert definition is assumed to work without fire and no-fire evidence.

## Behavioral cases

| Case ID | Type | Observable expectation |
|---|---|---|
| `obs-queue-boundary-positive` | positive | A new queue consumer triggers correlation, outcome, retry, dead-letter, latency, cardinality, privacy, and queryable-sample evidence. |
| `obs-pure-library-negative` | negative | A pure-library refactor without telemetry or production-boundary change does not load this module. |
| `obs-existing-rollout-signals-counterexample` | counterexample | Operational readiness can reuse current rollout signals without triggering this module when no telemetry contract changes. |
| `obs-log-everything-pressure` | pressure | Incident pressure does not permit raw payload logging; the response uses minimum correlated, privacy-safe, bounded, validated signals. |
