---
type: implementation-plan
prd-path: docs/prds/efficiency-baseline.md
prd-id: efficiency-baseline
prd-version: 2
---

# Offline efficiency baseline implementation

## Outcome and approach

Provide a repository-local, read-only CLI that validates a frozen workload
manifest and reports explicitly supplied observations. Reuse
`artifact_contracts.strict_load_json`, `ContractIssue`, execution contract
validators and canonical digest handling. Existing execution insights inspect
manager records but do not validate repeated benchmark cohorts, request-level
usage attribution or missing repetitions; keep this tool separate rather than
changing manager records, metrics, events or qualification formats.

The CLI has `validate-manifest --input FILE` and
`report --manifest FILE --observations FILE`. It emits JSON to stdout only.
It never invokes a provider, dispatches tasks, enables telemetry or writes a
store. Unknown versions, extra fields, duplicate identifiers and inconsistent
bindings are errors, not partial-success reports. The caller deliberately
selects both local inputs. Missing observations are valid and visible.

## Contracts and compatibility

Both new input formats use schemaVersion 1 and explicit kind identifiers.
Manifest fields bind a source revision, configuration digest, repetitions,
finite attempt/request limits and tasks with objectives, permitted actions,
acceptance criteria and a four-part rubric.

Observations bind the exact canonical manifest digest and contain synthetic
or recorded evidence, source/evidence-digest provenance and attempts. Each
attempt binds task, repetition, attempt ordinal, producer, duration, observed
tool/handoff counts, outcome, nullable declared quality and ordered requests.
Request IDs are unique inside their attempt. Prepared requests cannot claim
invocation/output/usage. Unknown invocation is not counted as confirmed.
Tokens require a reported usage source and evidence digest. Reports label
all imported data unverified; actual cost and all savings conclusions are
always null.

The report includes only identifiers/digests, closed states and numeric
aggregates; it never copies task instructions or unknown input fields.
All sums reject overflow. Partial coverage is not zero consumption.
Repetition/task/attempt/request limits bound accepted input structures.
Existing contracts have no delta; the new CLI has no previous consumer.
Errors use ContractIssue codes and sanitized stderr, with no JSON on failure.
Reversal removes only the additive tool, tests, manifest and documentation.

## Dependency-aware tasks

| Task | PRD refs | Outcome | Prerequisites | Consumes | Produces | Execution | Verification |
|------|----------|---------|---------------|----------|----------|-----------|--------------|
| contracts | FR-1, FR-7, AC-1, AC-6 | Freeze manifest and metadata-only observation contracts | none | none | baseline-contracts | sequential | Sensitive invalid/valid input tests before implementation |
| reporter | FR-2, FR-3, FR-4, FR-5, FR-6, FR-8, AC-2, AC-3, AC-4, AC-5, AC-7 | Validate and aggregate observations without authority or savings claims | contracts | baseline-contracts | baseline-reporter | sequential | Red/green tests for retries, missing usage, unknown invocation, self-review, duplicates, privacy and totals |
| integration | FR-1, FR-7, FR-8, AC-1, AC-6, AC-7 | Publish the CLI, representative manifest and documentation | reporter | baseline-reporter | baseline-delivery | sequential | Real CLI success/error tests, Python suite, runtime regression tests, artifact/repository/manifest checks and independent read-only review |

## Files and verification

- `scripts/benchmark.py`: standalone standard-library validator/reporter.
- `tests/test_benchmark.py`: behavior and actual CLI contract coverage.
- `benchmarks/manifest.json`, `benchmarks/README.md`: frozen initial five-task
  protocol and user instructions; no claimed benchmark results.
- `docs/prds/efficiency-baseline.md`, this plan and
  `docs/ARCHITECTURE.md`: accepted scope and authority boundary.
- `PROJECT-STANDARDS.md`: preserve the existing public-tree prohibition on
  project `.sdlc/` scaffolding. Public requirements, this plan and architecture
  retain durable context; no project policy or telemetry is enabled.

No dependency, installed helper, runtime store, event or manager schema changes.
The installed qualification manifest stays unchanged. Test with unittest,
repository/artifact/manifest validators and existing JavaScript runtime tests.
Review privacy, accounting, contract errors and manager isolation independently.
No live-provider test or demonstrated token reduction is a delivery criterion.
