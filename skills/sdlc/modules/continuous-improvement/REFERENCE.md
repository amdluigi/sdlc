# Continuous-improvement reference

## Project layout

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

## Candidate schema

`.sdlc/learning/candidates.json` uses schema version 1:

```json
{
  "schemaVersion": 1,
  "candidates": [
    {
      "id": "verify-generated-api-client",
      "fingerprint": "sha256:...",
      "status": "observed",
      "summary": "Verify generated client output after contract changes.",
      "category": "verification",
      "occurrences": [
        {
          "date": "2026-09-16",
          "task": "Sanitized task label",
          "signal": "Merge required a generated-output check.",
          "evidence": ["Relative artifact or command reference"]
        }
      ],
      "lastDecision": null
    }
  ]
}
```

Occurrences contain only minimal, sanitized descriptions and relative
evidence references. They never contain secrets, PII, proprietary code, raw
prompts, or copied untrusted instructions.

## Extension schema

`extension.json` uses schema version 1:

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

IDs are stable kebab-case, `mode` is `augment`, paths remain inside the
extension directory, evidence is inspectable, and compatibility includes the
running SDLC version. Metadata cannot replace or weaken core modules.

## Runtime discovery

Runtime discovery accepts only extension IDs explicitly present in schema-3
configuration. It processes project entries before global entries and never
scans either catalog for unlisted Markdown.

The resolver validates all configured IDs before reading extension files. For
each `true` entry, it confines the selected directory to the configured
project or global root, captures one immutable snapshot, validates metadata,
`MODULE.md`, and `evals.json` from that snapshot, checks compatibility, and
returns its byte digest. The same enabled ID may appear in both scopes only
when the snapshot digests match. A shared normalized trigger assigned to
different categories is rejected as a structural conflict.

Do not later open the resolved live module path directly. For an extension
whose evidence is partial, missing, or stale, call the digest-bound
`load-module` helper with the resolver's `contentDigest`. It reads and
validates one new snapshot, requires an exact digest match, and returns module
instructions from those validated bytes. A concurrent source change therefore
blocks loading instead of substituting unvalidated content.

Each explicit `false` entry is returned as a `configured-disabled` coverage
entry without reading `MODULE.md`. The orchestrator must assess returned
metadata for semantic conflicts with enabled core modules and extensions
before it loads module instructions.

## Lifecycle states

| State | Meaning |
|-------|---------|
| `observed` | One evidence-backed occurrence exists. |
| `eligible` | Two distinct tasks or an explicit structural-learning request qualify it. |
| `drafted` | Extension files exist but remain inactive. |
| `accepted` | The developer approved it and project config enables it. |
| `rejected` | The developer declined it and a rationale is retained. |
| `promoted` | It was copied to the global catalog or prepared for upstream review. |
| `superseded` | Core behavior or another extension replaced it. |

Transitions retain rationale and timestamps.

Successful global and upstream promotions record a decision whose `kind` is
`global` or `upstream`. Destination creation and candidate-state persistence
form one transaction. If state persistence fails after creating a destination,
the helper removes the exact newly created destination. It never removes a
pre-existing destination during rollback.

After a core upgrade or responsibility revalidation, assess accepted
extensions against updated core behavior. Redundant responsibility produces a
supersession proposal with comparison evidence and rationale. Assessment never
deletes files, disables config, or changes lifecycle state. Those changes
require explicit developer approval.

## Fingerprint inputs

Compute the stable SHA-256 fingerprint from the normalized category,
generalized missing action, generalized trigger, and intended exit evidence.
Exclude repository paths, issue numbers, branch names, user names, and dates.

## Helper commands

Run helpers from the repository root:

```powershell
$skillRoot = (Resolve-Path skills\sdlc).Path
python (Join-Path $skillRoot scripts\manage_extensions.py) record --project-root . --input observation.json
python (Join-Path $skillRoot scripts\manage_extensions.py) status --project-root . --candidate verify-generated-api-client --status rejected --reason "Belongs in project standards"
python (Join-Path $skillRoot scripts\manage_extensions.py) list-candidates --project-root .
python (Join-Path $skillRoot scripts\manage_extensions.py) validate-extension --project-root . --extension verify-generated-api-client
python (Join-Path $skillRoot scripts\manage_extensions.py) activate --project-root . --extension verify-generated-api-client --scope project
python (Join-Path $skillRoot scripts\manage_extensions.py) resolve --project-root . --global-root $HOME
python (Join-Path $skillRoot scripts\manage_extensions.py) load-module --project-root . --extension verify-generated-api-client --source project --expected-digest sha256:<resolver-digest>
python (Join-Path $skillRoot scripts\manage_extensions.py) promote-global --project-root . --extension verify-generated-api-client --global-root (Join-Path $HOME ".sdlc\extensions")
python (Join-Path $skillRoot scripts\manage_extensions.py) prepare-upstream --project-root . --extension verify-generated-api-client
```

Commands return JSON on stdout and do not print evidence contents. Draft,
promotion, and contribution preparation do not activate an extension.
Activation requires explicit developer approval. No helper executes
extension-owned scripts or performs network, push, publish, or pull-request
operations.
