# Contributing

## Maintainer commands

| Intent | Command |
|--------|---------|
| Routine private check | `verify.bat` |
| Full release rehearsal | `publish.bat --dry-run` |
| Publish after approval | `publish.bat` |

Only the private authoritative repository contains these launchers. Public
contributors use the validation and qualification commands documented below.

## Public contribution flow

The public `skills` repository is a read-only distribution boundary, not the
authoritative development history. Open issues and pull requests against
`skills` as usual. Maintainers review accepted work into the private
`skills-internal` authoritative source, run the complete test and privacy gates
there, and include it in a later one-way export.

Do not include private correspondence, raw transcripts, local machine paths,
credentials, or proprietary evaluation data. There is no automatic
publication path. A maintainer reviews the generated public diff and makes a
separate human publication decision.

Do not remove or modify `PUBLIC-REPOSITORY.json` or
`RELEASE-MANIFEST.json` in the public repository. Both are enforced release
integrity contracts.

Contributions should improve one coherent SDLC capability without making the
bundle project-specific or harder to trust.

Read these sources before changing behavior:

- [Repository charter](docs/REPOSITORY-CHARTER.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Canonical language](CONTEXT.md)
- [Contributor-agent rules](AGENTS.md)
- [Core module registry](skills/sdlc/modules/registry.json)

## Choose the Right Change Type

### Edit an existing module

Use this when the capability already has the correct trigger and exit signal.
Keep the module's responsibility stable and add the minimum missing guidance.

### Add a core module

Use this when the capability:

- is broadly useful across repositories;
- has a distinct trigger and evidence contract;
- is safe to enable by default;
- cannot fit cleanly into an existing module.

### Add or propose an extension

Use an extension when the capability is useful but not proven as a universal
default. Extensions augment core behavior and remain approval-gated.

### Update project standards or memory

Do not create a module for one repository's command, threshold, compliance
rule, architecture decision, correction, or domain term.

## Changing a Core Module

1. Define the behavioral gap and one coherent outcome.
2. Check the charter and existing registry for overlap.
3. Update the applicable `MODULE.md`.
4. Update `REFERENCE.md` or module assets only when progressive detail is
   necessary.
5. Update the registry evidence contract when exit requirements change.
6. Add positive, negative, counterexample, and pressure evaluations.
7. Add deterministic unit coverage for script behavior.
8. Update README and architecture documentation when public behavior changes.
9. Bump the skill and plugin version for meaningful behavior changes.
10. Run the complete validation sequence.

## Adding a Core Module

Create:

```text
skills/sdlc/modules/MODULE_ID/
└── MODULE.md
```

Optional detail belongs beside it:

```text
skills/sdlc/modules/MODULE_ID/
├── MODULE.md
├── REFERENCE.md
└── assets/
```

Then update:

- `skills/sdlc/modules/registry.json`;
- `skills/sdlc/assets/sdlc-config.template.json`;
- `evals/sdlc/cases.json`;
- `scripts/validate.py`;
- `skills/sdlc/scripts/validate_artifacts.py`;
- `README.md`;
- `docs/ARCHITECTURE.md`;
- plugin version metadata.

Module IDs are stable kebab-case. Registry order values are unique and
contiguous. Every module needs a category, trigger, exit signal, instruction
path, and non-empty evidence contract.

## Contributing an Extension

An extension bundle contains exactly:

```text
EXTENSION_ID/
├── extension.json
├── MODULE.md
└── evals.json
```

Extensions:

- use a stable kebab-case ID;
- use `mode: "augment"`;
- declare a compatible SDLC version range;
- define one bounded responsibility;
- provide an observable trigger and inspectable exit evidence;
- contain at least one positive and one negative evaluation;
- contain no scripts;
- remain inactive until explicitly approved and configured.

Before proposing an extension upstream, explain:

- the generalized recurring problem;
- why configuration, standards, memory, and existing modules are insufficient;
- the occurrence count and sanitized evidence;
- expected runtime and context cost;
- safety review results;
- rollback behavior;
- whether the capability should become core or remain an extension example.

Do not include secrets, personal data, proprietary code, raw prompts,
absolute paths, repository names, customer identifiers, or unnecessary task
history.

## Specifications and ADRs

Use `docs/specs/` for dated designs of substantial capabilities.

PRDs created by an installing project are product artifacts, not
specifications for this skill repository. Changes to the bundled PRD module or
template require trigger, approval, traceability, reuse, draft-blocking,
counterexample, and design-drift evaluations.

Create an ADR in `docs/adr/` only when a decision is difficult to reverse,
surprising without context, and based on a real trade-off. Keep ADRs concise.

Do not commit temporary implementation plans. Durable repository documents
use neutral paths and names.

## Behavioral Evaluations

Behavior changes require cases in `evals/sdlc/cases.json`.

Each case must:

- use a unique stable ID;
- describe a realistic pressured prompt;
- state observable expected behavior;
- mark core requirements as critical;
- list at least one forbidden shortcut;
- use valid, complete, sanitized fixtures;
- avoid testing preferred wording instead of behavior.

Discovery, planning, or implementation-process changes should include
pressure cases for rushed clarification, costly assumptions, unsafe
parallelism, and design drift when those risks apply.

TDD changes must cover strict red-green order, code-first rejection, valid
technical exceptions, safe bug reproduction, and a non-behavioral
counterexample. Artifact helper changes must use executable tests that first
fail for the missing behavior.

New domain modules require at least four cases: positive trigger, negative
non-trigger, boundary counterexample, and pressure resistance. Default-enabled
does not mean always loaded. Each case must prove applicability from accepted
scope or changed surfaces rather than repository technology alone.

Use fresh conversations for agent runs. Keep evaluated agents blind to the
rubric. Apply `evals/sdlc/evaluator-prompt.md` in a separate evaluation
context.

## Deterministic Tests

Runtime helpers use the Python standard library. Add focused tests under
`tests/` for:

- strict schemas and duplicate keys;
- state transitions;
- path and reparse-point confinement;
- immutable snapshots and content digests;
- compatibility;
- sanitization;
- transaction rollback;
- conflict behavior;
- absence of network, publication, and global mutation side effects.

A behavior-changing bug fix needs regression sensitivity: observe the test
fail for the expected reason before the fix when technically safe.

## Validation

Run:

```powershell
python -m unittest -q
python scripts\validate.py
& "C:\Program Files\Git\bin\bash.exe" -n scripts/install.sh
git --no-pager diff --check
```

Before release, also:

1. Review the canonical hash diff after an explicit refresh:

   ```powershell
   python scripts\qualify.py refresh-manifest --bundle skills\sdlc
   python scripts\qualify.py verify-manifest
   ```

2. Run every required installation cell in repository-local synthetic project
   and home roots. Never use the operator's actual home for qualification.
3. Run the manifest-selected live cases five times on a project-copy baseline
   for each required profile, plus at least one manifest-supported link cell.
4. Keep raw verdicts under ignored `qualification/raw/`, sanitize them, then
   delete the raw material after review:

   ```powershell
   python scripts\qualify.py sanitize-live --input qualification\raw\verdict.json --output qualification\results\3.3.0\PROFILE.project-copy.live.json
   ```

5. Have a maintainer review every generated hash change and each sanitized
   summary. The summary contains no prompts, responses, logs, project code,
   paths, user or machine identifiers, timestamps, secrets, or model IDs.
6. Run the complete release gate and final checks:

   ```powershell
   python scripts\qualify.py gate --release 3.3.0
   python -m unittest -q
   python scripts\validate.py
   & "C:\Program Files\Git\bin\bash.exe" -n scripts/install.sh
   git --no-pager diff --check
   ```

Routine `scripts/validate.py` validates structure and any retained summaries
without requiring live results. Only `qualify.py gate` enforces release
evidence completeness.

## Pull Requests

A pull request should:

- deliver one coherent outcome;
- explain non-goals and deferred work;
- map acceptance criteria to evidence;
- identify affected modules and public contracts;
- disclose compatibility, migration, security, and rollback concerns;
- include evaluation and test results;
- avoid unrelated cleanup;
- contain no generated caches, temporary plans, or sensitive content.

Do not add `Co-authored-by` trailers to commits in this repository.

Use repository-owned or generic names in public examples and documentation.
Provider examples use placeholders such as `custom-prd-provider`. Add a named
provider only through a separately approved adapter.
