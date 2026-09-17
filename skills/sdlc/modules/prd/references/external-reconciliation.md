# External requirements reconciliation

Use reconciliation when a durable local requirements artifact contains the
feature contract but does not use the native PRD Markdown shape. Supported
source kinds are `generic-spec`, `feature-design`, `issue-export`,
`structured-spec`, and `repository-prd`.

## Authority

Inspection never grants authority. Running `reconcile` without `--view`
explicitly nominates the source as the sole direct authority. Supplying
`--view` nominates that generated view as the sole SDLC authority and keeps
the source as provenance. Never approve both. A second candidate must be
recorded as a reference or superseded before planning.

The sidecar at `.sdlc/reconciliation/PRD_ID.json` records exact source
locations, assigned IDs, gaps, conflicts, superseded requirements, overlays,
approval, and byte digests. It supplements direct authority but is not a
second requirements document. Reconciliation never edits the source and
never marks approval complete.

## Commands

```text
python PATH_TO_SDLC/scripts/reconcile_artifacts.py inspect --project-root PROJECT_ROOT --source SOURCE --kind KIND
python PATH_TO_SDLC/scripts/reconcile_artifacts.py reconcile --project-root PROJECT_ROOT --source SOURCE --kind KIND --report .sdlc/reconciliation/PRD_ID.json
python PATH_TO_SDLC/scripts/reconcile_artifacts.py reconcile --project-root PROJECT_ROOT --source SOURCE --kind KIND --report .sdlc/reconciliation/PRD_ID.json --view docs/prds/PRD_ID.generated.md
python PATH_TO_SDLC/scripts/reconcile_artifacts.py reconcile --project-root PROJECT_ROOT --source SOURCE --kind KIND --report .sdlc/reconciliation/PRD_ID.json --update
python PATH_TO_SDLC/scripts/reconcile_artifacts.py reconcile --project-root PROJECT_ROOT --source SOURCE --kind KIND --report .sdlc/reconciliation/PRD_ID.json --replace --confirm-destructive-replace PRD_ID
python PATH_TO_SDLC/scripts/reconcile_artifacts.py validate --project-root PROJECT_ROOT --report .sdlc/reconciliation/PRD_ID.json --require-approved
python PATH_TO_SDLC/scripts/reconcile_artifacts.py render --project-root PROJECT_ROOT --report .sdlc/reconciliation/PRD_ID.json --output docs/prds/PRD_ID.generated.md
python PATH_TO_SDLC/scripts/validate_artifacts.py validate-prd --reconciliation .sdlc/reconciliation/PRD_ID.json --project-root PROJECT_ROOT
```

`inspect` is read-only. A first `reconcile` writes a draft report and, only
when requested, an atomic generated view. It refuses to overwrite an existing
report. `--update` validates the old report, preserves reviewed mappings,
assigned IDs, overlays, and superseded history, records its digest/version,
and invalidates approval. `--replace` discards that state only when the
confirmation exactly matches the existing PRD ID. `render` is valid only for
the nominated generated-view path. All commands are local and reject URLs,
path escapes, links, reparse points, stale selectors, digest drift, dual
authority, unresolved canonical fields, and invalid approval bindings.

## Mapping and freshness

Mappings cite a Markdown heading and line or a JSON Pointer. Existing `FR-*`
and `AC-*` IDs are preserved. Deterministically assigned IDs are persisted in
the report. Exact and human-reviewed mappings can satisfy the contract. A source
ambiguity requires exactly one reviewed selector plus durable review approval
evidence. Approved overlays may fill a source gap. Validation resolves this
reviewed model before applying the same type and substantive-content rules as
a native PRD. Requirements are never invented to fill gaps.

Structured data, permissions, privacy, and security may be either substantive
text or a flat named object whose values are substantive strings. Object keys
are stable-sorted into canonical section lines. Empty objects, blank or
unstable keys, nested values, arrays, and non-string values block validation.

Approval identifies an approver, durable evidence, normalized version, and
exact source digest. Any byte change invalidates that binding. A semantic
no-op retains the digest and normalized version from the last approved state
across any number of draft updates, and still requires deterministic
revalidation plus a non-empty `carryForward` approval record. A material
change increments the normalized
version, returns status to draft, and stales downstream evidence.
Only an approval that passes the authoritative status, substantive approver
and evidence, version/digest binding, and carry-forward rules may replace the
provenance anchor.

Superseded entries retain their source selector, replacement ID, reason, and
approval evidence. They do not count toward current coverage.

The strict report shape is
`contracts/reconciliation-report.schema.json`. Reports contain project-relative
paths or opaque selectors only, never source bodies, credentials, discussion
history, or absolute user paths.
