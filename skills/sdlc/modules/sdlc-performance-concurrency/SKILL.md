---
name: sdlc-performance-concurrency
description: "Use when a change has an explicit latency, throughput, capacity, or resource objective; modifies an evidenced hot path; or introduces or changes concurrency, parallel work, batching, caching, streaming, queueing, rate control, or shared mutable state."
metadata:
  sdlc-provider-schema: "1"
  sdlc-compatible: ">=1.0.0 <2.0.0"
  sdlc-modules: "performance-concurrency"
---

# Performance and concurrency module

## Bounded responsibility

Use this module to assure measured performance and concurrency behavior for
changed hot paths, resource-sensitive work, caches, batching, queues,
parallelism, streaming, and explicit latency or throughput objectives. It
owns hypotheses, budgets, representative measurements, contention, and
correctness-under-load evidence, not generic micro-optimization.

## Positive trigger

Load this module when a change has an explicit latency, throughput, capacity,
or resource objective; modifies an evidenced hot path; or introduces or
changes concurrency, parallel work, batching, caching, streaming, queueing,
rate control, or shared mutable state.

An evidenced hot path is identified by repository documentation, profiling,
production diagnostics, an accepted requirement, or a reproducible benchmark.
Async syntax or a large diff alone is not enough.

## Non-trigger counterexamples

- A cold admin command is renamed without a performance objective.
- A sequential pure function is refactored without changing complexity or an
  evidenced hot path.
- Test workers run in parallel while production behavior is unchanged.
- An existing cache library is present but untouched and irrelevant.
- Documentation describes performance without changing behavior or a contract.

## Evidence contract

1. State a measurable hypothesis with operation, workload, baseline or budget,
   metric, environment, and expected direction or threshold.
2. Compare before and after with the same representative workload and method,
   enough repetitions to expose variance, and stated environmental limits.
3. Cover applicable race, ordering, cancellation, timeout, retry, duplicate
   work, deadlock, starvation, backpressure, and shared-state behavior.
4. Report applicable CPU, memory, I/O, network, connection, queue-depth, or
   cache metrics, including warm and cold conditions when caching changes.
5. Demonstrate functional correctness and invariants at the measured load.
6. Record the current revision and command, harness, profile, or
   production-like source.

Evidence must be inspectable, scope-aligned, and current. Reuse qualifying
evidence regardless of producer.

## Overlap rules

- Change contract and PRD own promised performance outcomes. This module turns
  an accepted objective into a budget and workload.
- Planning owns sequence and risk. This module supplies measurement and
  concurrency work items.
- TDD owns behavior implementation order. A deterministic race regression may
  be red evidence; a benchmark improvement alone is not TDD evidence.
- Implementation owns algorithms, synchronization, caches, and resource
  management. This module rejects speculative optimization.
- Testing owns final functional coverage. This module owns benchmark validity,
  load and concurrency scenarios, variance, and resource evidence.
- Security-auth owns denial-of-service and abuse risk. This module owns
  resource and contention behavior under an agreed workload.
- Operational readiness owns rollout thresholds and response. This module
  supplies budgets and measured signals.
- Review checks the final diff and evidence from a performance and concurrency
  perspective rather than substituting intuition.

## Right-sizing

- For an explicit localized budget, measure only the affected operation and
  its correctness invariants.
- For new shared state, queues, caches, or parallelism, include contention,
  cancellation, saturation, and relevant resource behavior.
- Do not invent benchmarks for cold paths or optimize without a baseline,
  budget, or evidenced bottleneck.

## Steps

1. State why the trigger applies and identify the system boundary.
2. Establish a baseline or explicit budget before optimization.
3. Define workload, data shape, concurrency, warm or cold state, environment,
   metrics, and repetitions.
4. Identify correctness invariants and likely bottlenecks.
5. Implement the smallest measured improvement or safe concurrency mechanism.
6. Run targeted correctness, race, cancellation, saturation, and benchmark
   checks as applicable.
7. Compare distributions or stable summaries and record resource trade-offs
   and uncertainty.
8. Mark evidence stale after relevant algorithm, dependency, workload,
   runtime, resource, cache, queue, or schema changes.

## Exit

This module is satisfied when the relevant budget or baseline is explicit,
representative current measurements meet it without correctness, contention,
or resource regressions, and remaining capacity limits or measurement
uncertainty are disclosed.

## Common shortcuts to reject

- Theoretical complexity, fewer lines, or one favorable timing proves a gain.
- A higher throughput number excuses races, ordering errors, or data loss.
- A developer workstation's best result is treated as representative.
- Every async or parallel test change is classified as production concurrency.

## Behavioral cases

| Case ID | Type | Observable expectation |
|---|---|---|
| `perf-cache-hot-path-positive` | positive | A cache on an evidenced hot endpoint triggers baseline, warm/cold, hit/miss, invalidation, correctness, latency, and memory evidence. |
| `perf-cold-refactor-negative` | negative | A cold sequential refactor without a budget, hot-path evidence, or concurrency change does not load this module. |
| `perf-test-parallelism-counterexample` | counterexample | Parallel test workers remain testing scope unless production code or an accepted delivery objective is affected. |
| `perf-racy-deadline-pressure` | pressure | A throughput deadline does not waive repeated measurement, ordering, race, cancellation, saturation, correctness, and resource evidence. |
