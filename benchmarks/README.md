# Offline efficiency baseline tooling

This repository tool validates a workload manifest and reports user-supplied
observations. It does not run tasks, call a model, read manager stores, enable
telemetry, accept work, authenticate evidence or prove savings.

```powershell
python -B scripts\benchmark.py validate-manifest --input benchmarks\manifest.json
python -B scripts\benchmark.py report --manifest benchmarks\manifest.json --observations observations.json
```

Both operations print deterministic JSON to stdout. Only explicitly selected
local files are read; nothing is automatically persisted. Redirect output
only when you intend to retain it. Exit zero means valid input and successful
reporting, not successful execution or complete measurements. Invalid JSON,
duplicate keys, unsupported versions, unknown fields and semantic mismatches
produce a nonzero exit, sanitized stderr and no report.

## Freeze your workload before measuring

`manifest.json` is an illustrative five-category protocol, five repetitions
per category. It is not a runnable harness or completed benchmark. Supply your
own public/synthetic fixtures and select an actual source revision, requested
model, known effective model, host version and configuration digest before
collecting observations. The initial configuration digest is an example,
not proof that any provider or execution configuration was used.

Changing any manifest field changes its canonical SHA-256 digest and creates
a different cohort. Copy the digest from `validate-manifest` into observations.
Use your source-control revision, not a mutable branch name. Manifest limits
are repetitions 1..10, attempts per repetition 1..4 and requests per attempt
1..32, with at most 256 planned attempts.

Task fields are `id`, `objective`, `permittedActions`, `acceptanceCriteria`,
`verification` and `rubric`. All arrays are nonempty and contain unique strings.
All four rubric dimensions are required: correctness, verification, security
and scope. Actions describe the workload; they do not authorize a manager or
shell operation. The tool never executes the verification instructions.

## Observation format

Use schemaVersion 1 and kind `sdlc-efficiency-observations`:

```json
{
  "schemaVersion": 1,
  "kind": "sdlc-efficiency-observations",
  "manifestDigest": "sha256:REPLACE_WITH_VALIDATED_MANIFEST_DIGEST",
  "evidenceKind": "recorded",
  "usageSource": "unavailable",
  "usageEvidenceDigest": null,
  "attempts": []
}
```

`evidenceKind` is `synthetic` or `recorded`. Recorded does not mean
authenticated. To import reported token counts, use `caller-reported` and a
`sha256:` evidence digest. Source authenticity is always `not-assessed`.
Do not upload prompts, responses, raw logs, source code, account information
or credentials. Every object rejects extra fields.

Each attempt has these required fields:

| Field | Meaning |
|-------|---------|
| `taskId`, `repetition` | Existing task and 1-based repetition within the manifest bound |
| `attempt`, `attemptId` | 1-based ordinal and unique ID; retries require all preceding attempts |
| `producerId` | Bounded lowercase kebab-case producer label, not authentication |
| `outcome` | `completed`, `failed`, `interrupted` or `unknown`, never manager acceptance |
| `elapsedMs` | Observed attempt duration, nonnegative integer |
| `toolCalls` | Dispatched tool operations, including errors |
| `handoffs` | Observed transfers to another worker attempt, or null if unavailable |
| `quality` | Null, or the declared review object described below |
| `requests` | Ordered unique request snapshots, bounded by the manifest |

A request contains `id`, `state`, `adapterInvoked`, `inputBytes`, `outputBytes`,
`providerInputTokens`, `providerOutputTokens`, `cachedInputTokens`,
`billableInputTokens`, `billableOutputTokens` and `authoritativeCost`.
All token fields are nonnegative integers or null. Actual cost must be null:
this tool cannot authenticate billing. List prices are not actual cost.

Request states are `prepared`, `dispatched`, `completed`, `interrupted` and
`unknown`. Invocation is true, false or null. Prepared means false; dispatched
and completed require true. Output or token observations require a known
invocation. Input bytes describe the prepared request but count as dispatched
input only when invocation is true. Record one latest observation per
request, not successive snapshots as separate requests.

UTF-8 byte values must come from the collector's actual observed boundaries;
the reporter cannot reconstruct bytes from transcripts and does not request
them. Partial output is its observed prefix, not a completed response.

Declared quality is an object containing `reviewerId`, `evidenceDigest` and
`criteria`, with all four rubric keys mapped to `passed`, `failed` or
`unavailable`. The reviewer label must differ from the producer. This checks
declared separation only; it authenticates neither identity nor evidence.
Quality counts are per observed attempt, not accepted tasks.

## Reading the report

- `observedModelCalls` counts known adapter invocation, not remote delivery.
- `unknownInvocations` stays separate; `observedInputBytes` preserves known
  observations while `totalInputBytes` is null if invocation is uncertain.
- Token totals are null if any contributing request lacks that field or any
  invocation is unknown. Cached and billable fields are never inferred from
  other tokens. No usage source means null, not zero consumption.
- `attemptElapsedMs` sums attempt durations. `endToEndElapsedMs` is null;
  the tool does not invent a wall-clock interval from that sum.
- Handoff totals are observed lower bounds; `handoffsComplete` exposes
  missing observations. Retry counts count observed ordinals above one.
- Missing repetitions, unknown outcomes and absent assessments stay visible.
  Synthetic status remains synthetic even if every numeric field is filled.
- `tasks` includes every planned task and each repetition, including entirely
  missing ones, with the same coverage, outcomes, accounting and declared
  quality breakdowns as the cohort summary.
- Recorded reports are always explicitly unverified. Token savings, cost
  savings and quality non-regression remain null. Manager acceptance is
  always false.

Existing execution, telemetry, runtime-store and qualification schemas are
unchanged. This is repository tooling, not an installed runtime command.
Users evaluate efficiency themselves. The software tests validate accounting
and safety, not a reduction in tokens.
