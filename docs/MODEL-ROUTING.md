# Task-aware finite model planning

The optional installed `scripts/manage_routing.py` helper prepares model
choices for an existing finite batch. Nothing calls it automatically. It
does not execute tasks, invoke models, approve a plan or adopt a policy.
The existing manager remains the sole execution writer and independent
acceptance authority.

## Inputs and selection

Supply four explicit UTF-8 JSON files:

- A version-1 execution plan, including task model-profile assignments.
- An existing version-1 finite batch with exact attempt IDs, briefs and
  runtime/cumulative limits.
- A model inventory using the existing
  [controls contract](EXECUTION-CONTROLS.md). Its supplied observations are
  not authenticated by this helper.
- A version-1 routing policy such as:

```json
{
  "schemaVersion": 1,
  "kind": "sdlc-model-routing-policy",
  "permittedModels": ["small-model", "strong-model"],
  "models": [
    {"id": "small-model", "capacity": 2, "costRank": 1},
    {"id": "strong-model", "capacity": 3, "costRank": 2}
  ],
  "profiles": [
    {
      "id": "development",
      "minimumCapacity": 2,
      "candidates": ["small-model", "strong-model"]
    }
  ]
}
```

Use your actual permitted model IDs. `capacity` is a declared tier (1..3),
not a provider qualification. `costRank` is a nonnegative integer preference:
lower ranks are preferred, but they do not represent actual prices, billing
or demonstrated savings. Profile IDs must match the plan. All candidate and
permitted IDs require model declarations. Duplicate identities, unknown
fields/versions and invalid values are rejected.

The fixed task-shape heuristic uses declared metadata, never source content:

| Declared shape | Tier |
|----------------|------|
| At least four owned paths, four acceptance criteria, or two prerequisites | 3 |
| Otherwise any owned path, prerequisite, or multiple criteria | 2 |
| Otherwise | 1 |

The profile's `minimumCapacity` can increase this requirement. These are
transparent planning heuristics, not semantic complexity or quality
assessments. Choose an appropriately strong profile for security-sensitive
or otherwise difficult work regardless of file count.

For the first attempt, an explicit plan model is respected and checked for
suitability, profile membership, permission and supplied availability.
Otherwise the helper selects the suitable available permitted candidate with
the lowest declared rank, breaking ties by model ID. Each existing fallback
slot selects the lowest ranked strictly stronger candidate, or repeats the
current model when none exists. It does not create attempts or enlarge limits.

## Propose, inspect and materialize

```text
python scripts/manage_routing.py propose --plan plan.json --batch batch.json --inventory inventory.json --policy routing-policy.json
python scripts/manage_routing.py materialize --plan plan.json --batch batch.json --inventory inventory.json --policy routing-policy.json --proposal proposal.json
```

Both commands emit JSON only to stdout and write no files. Deliberately save
the first output as UTF-8 `proposal.json` when you want to inspect and use it.
Materialization emits the proposed finite batch; save it separately and
present it to the existing
[runtime batch preview and confirmation](EXECUTION-ORCHESTRATION.md).
Do not overwrite a previously approved batch and assume its consent survives.

Proposals contain only identifiers, tier/rank values, closed reason codes and
canonical input/decision digests. They have `active: false`, never include
briefs or task instructions, and never establish effective model identity.
Materialization rederives every choice from all four inputs and rejects any
changed input, stale brief, edited decision, digest mismatch or extra field.
Its only changes to the batch are exact model IDs.

The current manager still requires enabled execution and controls, current
plan/control approval, permitted models, escalation consent, finite budgets
and explicit consent to the new exact batch digest. Unknown outcomes,
unaccepted prerequisites, pauses and cancellation intent remain barriers.
Only a manager-confirmed retryable failure can advance to an already approved
fallback. Low confidence or a worker's self-assessment alone cannot authorize
another request. Worker completion never becomes independent acceptance.

The existing attempt ledger records actual chosen model IDs and outcomes;
match task/attempt IDs to the proposal for analysis. Planning does not prove
remote receipt, effective routing, billing, improved quality or lower cost.
No telemetry, credentials, provider calls, historical discovery, scheduler,
parallel execution, production migration or automatic policy adoption is added.

## Compatibility and errors

The policy and proposal are separate version-1 formats with distinct `kind`
identifiers. The existing execution-insights version-1 proposal, whose routing
recommendations must stay empty, is unchanged. Manager, event, runtime-store,
controls and finite-batch versions are unchanged.

The CLI uses the existing strict JSON loader and sanitized `ContractIssue`
diagnostics. Invalid input produces a nonzero exit code and no successful JSON.
Policies may be empty, but a missing task profile or lack of a suitable model
is an explicit error, never a silent fallback to a host default.

Removing the additive helpers disables this planning convenience without
rewriting any execution history or active configuration.
