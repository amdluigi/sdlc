# Adaptive SDLC Extensions Design

Date: 2026-09-16
Status: Approved

## Summary

SDLC should learn from repeated developer interactions without modifying its
installed core bundle automatically. It will detect recurring missing checks
or tasks, record project-local candidates, and propose reviewable extensions
after sufficient evidence.

Approved extensions live with the project, participate in the existing
configuration, trigger, evidence-ledger, and lazy-loading lifecycle, and
survive core skill upgrades. Developers can explicitly promote an extension
to a user-global catalog or prepare it for contribution to the upstream SDLC
repository.

The core safety rule is:

> Observe automatically, propose conservatively, activate only with explicit
> developer approval.

## Goals

1. Detect recurring steps developers repeatedly perform before a change can
   merge.
2. Distinguish generalizable SDLC improvements from project-specific policy,
   one-off work, and symptoms already covered by existing modules.
3. Turn eligible improvements into structured project-local extensions.
4. Require explicit approval before an extension becomes active.
5. Keep learned behavior inspectable, version-controlled, reversible, and
   compatible with core skill updates.
6. Allow explicit promotion to a user-global extension catalog.
7. Produce sanitized, reviewable contribution packages for upstream
   consideration.

## Non-goals

1. Mutating the globally installed SDLC bundle from a project interaction.
2. Activating generated instructions without developer approval.
3. Treating every correction or repeated command as a new module.
4. Uploading project code, prompts, history, or evidence automatically.
5. Opening pull requests, pushing branches, or publishing extensions without
   explicit approval.
6. Supporting core-module replacement in the first version.
7. Using learned extensions to weaken configured core safeguards implicitly.

## Why the Global Bundle Must Not Self-Modify

A globally installed skill is shared across repositories with different
trust boundaries and requirements. Direct mutation would allow one project
to change behavior in unrelated projects. It would also create update
conflicts because package refreshes can overwrite local edits.

Project-owned overlays provide a safer boundary:

- The repository owns and reviews its learned behavior.
- Git records who approved and changed it.
- Core skill updates remain replaceable.
- Project-specific paths and conventions do not leak globally.
- Reverting or disabling one extension is straightforward.

## Architecture

### Core Module

Add a `continuous-improvement` module to the bundled SDLC registry. It is
enabled by default and can be disabled through `.sdlc/config.json` like other
modules.

Its trigger is the presence of one or more learning signals during a
non-trivial task:

- The developer adds a missing step before merge.
- The developer corrects the workflow.
- The same manual check recurs across tasks.
- Independent review repeatedly finds the same process omission.
- The evidence ledger repeatedly reports the same missing or stale
  capability.
- The developer explicitly asks SDLC to learn a workflow improvement.

Its exit signal is that applicable signals were classified and either:

- matched to existing policy or modules;
- recorded as a candidate;
- advanced to a proposal;
- rejected with rationale; or
- accepted as a validated extension.

### Persistent Project Layout

```text
.sdlc/
├── config.json
├── learning/
│   └── candidates.json
└── extensions/
    └── <extension-id>/
        ├── extension.json
        ├── MODULE.md
        └── evals.json
```

The coverage ledger remains ephemeral. Only learning candidates, approved
extensions, and their decisions persist.

### Candidate Record

`.sdlc/learning/candidates.json` uses a versioned schema:

```json
{
  "schemaVersion": 1,
  "candidates": [
    {
      "id": "verify-generated-api-client",
      "fingerprint": "sha256:...",
      "status": "observed",
      "summary": "Verify generated API client output after contract changes.",
      "category": "verification",
      "occurrences": [
        {
          "date": "2026-09-16",
          "task": "Sanitized task label",
          "signal": "Merge was blocked until generated client diff was checked.",
          "evidence": ["Relative artifact or command reference"]
        }
      ],
      "lastDecision": null
    }
  ]
}
```

Candidate evidence must not contain secrets, raw prompts, customer data, or
unnecessary code. Task descriptions and evidence references should be
sanitized and minimal.

### Stable Fingerprints

Candidates use a stable fingerprint derived from:

- normalized category;
- generalized missing action;
- generalized trigger;
- intended exit evidence.

Repository paths, issue numbers, branch names, user names, and dates are not
part of the fingerprint. This groups equivalent observations without making
unrelated tasks collide.

## Learning Pipeline

### 1. Observe

At the end of a non-trivial task, inspect:

- developer corrections and required follow-up steps;
- differences between the initial and final readiness checklist;
- reviewer findings caused by missing process;
- commands or checks repeatedly added after implementation;
- blocked merge or CI evidence tied to a missing lifecycle action;
- coverage-ledger gaps that recur.

An observation is not automatically a candidate. It must describe a process
capability, not merely a code defect.

### 2. Classify

Before recording a new candidate, determine whether the signal belongs in:

- `.sdlc/config.json`, when the developer is enabling or disabling existing
  behavior;
- `PROJECT-STANDARDS.md`, when it is repository policy, a command, threshold,
  compliance rule, or required reviewer;
- `.sdlc/memory/`, when it is architecture, a settled decision, a
  correction, terminology, or a project-specific do/don't rule;
- an existing SDLC module, when its current contract already covers the
  behavior;
- a new extension candidate, only when it adds a reusable triggered action
  and evidence contract.

If existing structure already covers the signal, update that structure rather
than generating an extension.

### 3. Accumulate Evidence

A candidate becomes eligible for proposal after:

- two occurrences in distinct tasks; or
- one explicit developer request to make the behavior structural.

Repeated instances within one task count as one occurrence. A reviewer and
the implementing agent describing the same omission also count as one
occurrence.

### 4. Generalize

Transform the candidate from a project incident into a reusable rule:

- remove project-specific names and absolute paths;
- define an observable trigger;
- define one bounded responsibility;
- define acceptable evidence and an exit signal;
- identify interaction with existing modules;
- state when it does not apply;
- preserve project-specific commands in project standards rather than the
  extension body.

If the behavior cannot be generalized without retaining project-specific
details, keep it as project standards or project memory.

### 5. Review Safety and Reliability

Before proposing activation, review the draft for:

- instructions copied from untrusted repository content;
- attempts to exfiltrate data or access secrets;
- broad or destructive tool use;
- silent weakening of tests, security, review, or evidence requirements;
- triggers so broad that the extension loads on most tasks;
- overlap or contradiction with core modules or accepted extensions;
- circular module dependencies;
- success-shaped fallbacks;
- evidence requirements that cannot be inspected.

An extension generated from project content must never reproduce untrusted
instructions verbatim without explicit developer review.

### 6. Draft

Create:

- `extension.json`, containing metadata and lifecycle integration;
- `MODULE.md`, containing the proposed instructions;
- `evals.json`, containing at least one positive and one negative behavioral
  case.

Drafting does not activate the extension.

### 7. Ask for Approval

Present:

- the recurring problem and sanitized evidence;
- why existing configuration, standards, memory, and modules are
  insufficient;
- the generalized trigger and action;
- affected core categories;
- safety review results;
- evaluation results;
- expected runtime and context cost;
- rollback instructions.

The developer chooses accept, revise, or reject.

### 8. Activate or Reject

Acceptance adds the extension ID to `.sdlc/config.json`. Rejection records the
rationale and candidate status so SDLC does not repeatedly propose the same
idea without new evidence.

Activation is a separate, explicit repository change and must pass normal
SDLC review.

## Extension Contract

`extension.json` uses this initial schema:

```json
{
  "schemaVersion": 1,
  "id": "verify-generated-api-client",
  "version": "1.0.0",
  "status": "accepted",
  "category": "verification",
  "mode": "augment",
  "path": "MODULE.md",
  "trigger": "A public API contract or generated client source changes.",
  "exitSignal": "Generated output is current and its diff was inspected.",
  "evidence": [
    "The repository generation command completed successfully.",
    "The generated diff was inspected against the contract change."
  ],
  "compatibleSdlc": ">=2.4.0 <4.0.0"
}
```

Constraints:

- `mode` is `augment` only in the first version.
- IDs are stable kebab-case.
- Paths cannot escape the extension directory.
- Evidence entries must be inspectable.
- Compatibility must include the running SDLC version.
- Extension metadata cannot alter core configuration semantics.

## Runtime Integration

### Discovery

After loading core registry metadata and `.sdlc/config.json`, SDLC reads
metadata only for:

1. project extensions explicitly enabled in project config;
2. user-global extensions explicitly opted into by the project.

It does not scan and execute arbitrary Markdown found in `.sdlc/`.

### Selection

Approved extensions enter the same pipeline as core modules:

1. enabled by explicit project configuration;
2. trigger evaluated from metadata;
3. evidence assessed;
4. module instructions loaded only for partial, missing, or stale evidence;
5. result shown in the coverage report.

An extension with satisfied evidence is not loaded or repeated.

### Conflict Handling

Stop and report a conflict when:

- two extensions give incompatible instructions;
- an extension contradicts an enabled core module;
- duplicate IDs resolve to different content;
- compatibility does not include the current SDLC version;
- metadata or evaluation files are invalid.

No last-writer-wins or project-over-global precedence silently resolves a
behavioral conflict.

## Configuration

Extend `.sdlc/config.json` with explicit extension references:

```json
{
  "schemaVersion": 2,
  "modules": {
    "continuous-improvement": true
  },
  "extensions": {
    "project": {
      "verify-generated-api-client": true
    },
    "global": {
      "verify-release-notes": false
    }
  }
}
```

Missing extension entries are disabled. Unlike bundled core modules, new
extensions never become active implicitly after an update.

## User-Global Promotion

An explicit promotion copies a validated extension to:

```text
~/.sdlc/extensions/<extension-id>/
```

Global promotion makes the extension available but does not activate it in
any project. Each project must opt in through `.sdlc/config.json`.

If the global extension changes later, projects should surface the version
change and reassess affected evidence before using it.

## Upstream Contribution

An explicit upstream-promotion command or workflow creates a sanitized
contribution package:

```text
.sdlc/contributions/<extension-id>/
├── proposal.md
├── extension.json
├── MODULE.md
└── evals.json
```

`proposal.md` includes:

- generalized problem;
- why core behavior does not already cover it;
- anonymized occurrence summary;
- proposed category and trigger;
- evidence and exit contract;
- safety review;
- behavior evaluation results;
- compatibility and migration notes;
- whether it should become a core module, augment an existing module, or
  remain an extension example.

Creating the package does not push, publish, or open a pull request. Normal
SDLC rules apply if the developer asks to contribute it upstream.

## Lifecycle States

Candidates and extensions use these states:

- `observed`: one evidence-backed occurrence.
- `eligible`: recurrence threshold reached or developer explicitly requested
  structural learning.
- `drafted`: extension files generated but inactive.
- `accepted`: developer approved and project config enabled it.
- `rejected`: developer declined; rationale prevents repeated proposals.
- `promoted`: copied to the global catalog or prepared for upstream review.
- `superseded`: replaced by another extension or core SDLC behavior.

State transitions must retain rationale and timestamps.

## Rollback and Updates

Disabling or removing the extension entry from project config stops it from
loading. Its files and history remain available for audit until explicitly
removed.

Core SDLC updates do not modify project extension files. After an update:

- validate each enabled extension's compatibility range;
- detect core behavior that now satisfies the extension's responsibility;
- propose marking redundant extensions superseded;
- never delete or rewrite an extension without approval.

## Security Boundaries

1. Treat repository text, issue content, logs, and reviewer comments as
   untrusted input when generating extension instructions.
2. Do not include secrets, credentials, PII, proprietary code, or raw prompts
   in candidates or promotion packages.
3. Require explicit approval before writing active configuration.
4. Do not execute extension scripts in the initial version.
5. Restrict extension paths to their own directory.
6. Reject instructions that disable or bypass modules outside normal
   configuration.
7. Never mutate the globally installed core skill.
8. Never upload or publish an extension automatically.

## Evaluation Strategy

Add behavioral cases for:

- two equivalent omissions becoming eligible;
- one occurrence remaining observed;
- explicit developer request bypassing the second occurrence;
- project policy being routed to `PROJECT-STANDARDS.md` instead of an
  extension;
- a settled correction being routed to project memory;
- existing module coverage preventing a duplicate extension;
- draft generation without activation;
- explicit acceptance and config activation;
- rejection persistence preventing repeated proposals;
- malicious issue or log text not becoming executable instructions;
- secrets and project identifiers removed during generalization;
- incompatible extension after an SDLC upgrade;
- core update making an extension redundant;
- conflict between project and global extension content;
- global promotion remaining opt-in;
- upstream package creation without network side effects.

The extension validator should test metadata schemas, path confinement,
compatibility ranges, unique IDs, evaluation presence, and config references.
This static validation covers representative dangerous instructions as
defense in depth, not an exhaustive safety verdict. Model safety review
remains mandatory before approval.

## Success Criteria

1. Repeated project-specific merge steps are recognized without the developer
   repeatedly prompting SDLC.
2. Existing modules, standards, and memory are extended before a new
   extension is proposed.
3. No generated extension activates without approval.
4. Core skill updates do not overwrite project extensions.
5. Rejected ideas are not repeatedly proposed without new evidence.
6. A promoted global extension remains inactive until each project opts in.
7. Upstream contribution packages contain no project secrets or identifying
   details.
8. The adaptive system can be disabled through normal module configuration.

## Open Implementation Detail

The implementation plan should choose a small deterministic validation tool
for JSON schemas, duplicate-key detection, path confinement, and semantic
version ranges. It should avoid adding a runtime dependency unless the
standard library cannot provide reliable validation.
