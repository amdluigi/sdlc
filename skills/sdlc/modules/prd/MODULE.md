# Product requirements document module

Create or validate one durable, human-facing product requirements document
before implementation planning for:

- a new project;
- a new user-facing or product-facing feature;
- a Significant internal feature that introduces a new capability.

Do not require a PRD for bug fixes, refactors, maintenance, dependency
updates, documentation-only changes, or small internal utilities unless the
change becomes a new Significant capability. Those changes use the
change-contract module directly.

## 1. Find or create the artifact

First search for an existing requirements artifact. It can satisfy this
module regardless of which person, agent, or tool created it. A native PRD
must:

- be committed or otherwise durable and inspectable;
- identify itself as a PRD through frontmatter;
- satisfy the content and approval contract below;
- describe the current proposed feature rather than a broader product vision;
- remain current for the feature and repository state.

A non-native local specification can satisfy the same contract through a
strict reconciliation sidecar without being copied or overwritten. Inspecting
it does not make it authoritative. Follow
[external reconciliation](references/external-reconciliation.md) to nominate
exactly one direct source or generated view, preserve provenance and source
locations, resolve gaps and conflicts, and bind approval to its version and
digest.

Follow an established repository location when one exists. Otherwise use:

```text
docs/prds/FEATURE_ID.md
```

Create new documents from
[assets/PRD.template.md](assets/PRD.template.md).

Validate an artifact deterministically before treating it as evidence:

```text
python PATH_TO_SDLC/scripts/validate_artifacts.py validate-prd PATH_TO_PRD
```

Use `--allow-draft` only while authoring or reviewing a draft. It validates
identity and content but does not satisfy the approval gate. Schema validation
does not grant semantic approval or prove that the product decisions are
correct.

The normalized success shape is documented by
`contracts/prd-result.schema.json`. It reports the artifact's
`declaredStatus` and contract-shaped approval evidence.

For reconciliation-backed validation use:

```text
python PATH_TO_SDLC/scripts/validate_artifacts.py validate-prd --reconciliation .sdlc/reconciliation/FEATURE_ID.json --project-root PROJECT_ROOT
```

## 2. Required identity

Use this frontmatter:

```yaml
---
type: prd
id: stable-kebab-case-feature-id
status: draft
version: 1
---
```

- `type` is always `prd`.
- `id` remains stable for the lifetime of the feature.
- `status` is `draft`, `approved`, or `superseded`.
- `version` is a positive integer incremented when approved requirements
  materially change.

The path alone does not prove that a document is a PRD. For reconciled
requirements, identity comes from the authoritative artifact plus its
validated report.

## 3. Required content

Every PRD includes:

1. **Problem and context**: what problem exists and why it matters now.
2. **Target users and benefit**: who receives value and what improves.
3. **Outcome**: one observable product or capability result.
4. **Goals**: specific results the feature must achieve.
5. **Non-goals**: plausible adjacent work intentionally excluded.
6. **User scenarios**: representative behavior, permissions, and failure
   situations. Use formal user-story wording only when it improves clarity.
7. **Functional requirements**: numbered `FR-1`, `FR-2`, and so on. Each
   requirement states one observable behavior.
8. **Acceptance criteria**: numbered `AC-1`, `AC-2`, and so on, mapped to the
   functional requirements they prove.
9. **Data, permissions, privacy, and security**: affected data and authority,
   or an explicit reason the section is not applicable.
10. **Constraints and dependencies**: compatibility, policy, operational,
    regulatory, design, and external constraints known before planning.
11. **Success measures**: product or operational metrics only when they define
    success or constrain the design. Otherwise state why behavioral acceptance
    criteria are sufficient.
12. **Open decisions**: unresolved choices, their owner, and whether each
    blocks approval.
13. **Approval**: status, approver, approval evidence, and approved version.

Keep the PRD focused on what and why. Implementation files, task sequencing,
code structure, and detailed technical approach belong in planning.

## 4. Right-size depth, not identity

- A small product feature can have a short PRD, but it still uses the required
  identity, sections, numbered requirements, and approval.
- A Significant feature includes deeper scenarios, constraints, data,
  permissions, compatibility, and measurable outcomes where relevant.
- A new project PRD describes the first coherent product scope, not every
  hypothetical future capability.

Do not manufacture personas, metrics, stories, or requirements to make the
document longer.

## 5. Approval gate

Keep `status: draft` while:

- a costly product, ownership, authorization, data, billing, retention,
  compatibility, or public-contract decision is unresolved;
- functional requirements or acceptance criteria contradict each other;
- the feature boundary is not coherent;
- required evidence from repository discovery is missing.

Present the PRD for explicit developer approval. After approval:

1. resolve or clearly defer non-blocking open decisions;
2. set `status: approved`;
3. record the approver and approval evidence;
4. confirm the approved version;
5. commit the PRD when repository workflow permits.

Planning and implementation cannot begin from a draft PRD. A prompt asking to
skip the document or approve it implicitly does not satisfy the gate.

## 6. Traceability

Before approval, reconcile the incoming change contract with the PRD. Map
every applicable change-contract acceptance criterion to a numbered PRD
`AC-*` item. If the PRD deliberately replaces a criterion, record the
superseded criterion and approval rationale.

The planning module maps every task to one or more `FR-*` and `AC-*` IDs.
The testing module maps acceptance evidence to `AC-*` IDs. The PR handoff
reports which PRD version and requirements the final change implements.

Requirements with no planned implementation or acceptance evidence are gaps,
not deferred assumptions. Change-contract criteria with no mapped or
explicitly superseded PRD acceptance criterion are also gaps.

The helpers reject missing or duplicate sections and identity fields,
non-positive versions, incomplete approval evidence, undefined `FR-*` or
`AC-*` items, acceptance criteria mapped to unknown requirements, and
functional requirements without acceptance criteria. Reconciliation also
rejects unmapped canonical fields, unresolved conflicts, stale source
selectors or digests, generated-view edits, and dual authority.

## 7. Design drift

When implementation changes promised behavior:

1. stop at a coherent checkpoint;
2. update the PRD and increment its version;
3. mark replaced requirements or decisions as superseded without erasing the
   reason;
4. return the PRD to `draft`;
5. stale the affected plan, tests, security, operations, review, and handoff
   evidence;
6. obtain renewed approval before implementation resumes.

Routine implementation details that do not change product behavior do not
change the PRD.

## Exit

This module is satisfied only when a durable PRD is identifiable, complete,
internally consistent, approved explicitly, current for the feature, and
traceable to numbered requirements and acceptance criteria.

## Common shortcuts that fail

| Shortcut | Why it fails |
|----------|--------------|
| "The conversation is the PRD" | Later developers cannot reliably inspect, version, or approve it. |
| "The issue already explains the feature" | An issue satisfies the gate only when it has the required identity, content, and approval evidence. |
| "We can write the PRD after implementation" | The document can no longer prevent scope and expectation mistakes. |
| "This feature is small" | Right-size the document; do not remove its identity or approval gate. |
| "Open questions can be solved during coding" | Costly unresolved decisions make implementation speculative. |
