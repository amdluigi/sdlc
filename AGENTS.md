# AGENTS.md

This file guides AI coding agents (Claude Code, Cursor, Copilot, etc.) and
human contributors working on this repository itself (i.e. adding or editing
skills here - not using the skills in some other project).

This public repository is authoritative for product code, tests, public
documentation, CI, versions, releases, and contributions. Make implementation
changes here through focused branches and pull requests. The repository must
remain independently understandable, testable, and installable from the
documentation in this repository.

## Repository overview

A modular [Agent Skills](https://agentskills.io) bundle that makes an AI
coding agent follow a consistent software delivery process (`sdlc`),
including persistent project memory, without the user restating the process
in every prompt. Only `sdlc` is a discoverable skill; lifecycle capabilities
inside it are internal modules.

## Repository sources of truth

- [`docs/REPOSITORY-CHARTER.md`](docs/REPOSITORY-CHARTER.md): mission,
  boundaries, evolution policy, and acceptance criteria.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): current runtime and trust
  boundaries.
- [`CONTEXT.md`](CONTEXT.md): canonical repository terminology.
- [`CONTRIBUTING.md`](CONTRIBUTING.md): human contribution workflow.
Keep these roles separate. Put implementation guidance in the skill modules,
keep `CONTEXT.md` limited to stable terminology, and do not turn product
documentation into a speculative roadmap.

## Directory structure

```
skills/
  sdlc/
    SKILL.md               discoverable orchestrator
    modules/
      registry.json         module placement: name, category, order, replaceable
      sdlc-{module-name}/
        sdlc-capability.json  what this implementation serves and its evidence
        SKILL.md           implementation instructions, loaded by the orchestrator
        assets/            optional module-owned templates/resources
        REFERENCE.md       optional detailed reference
scripts/
  install.ps1 / install.sh  manual install helper (copy/symlink into a target project)
.claude-plugin/
  plugin.json               Claude Code plugin manifest - lists every skill folder
  marketplace.json          makes this repo its own single-plugin marketplace
```

## Naming conventions

- The only discoverable skill directory is `skills/sdlc`, matching the
  `name:` field in `SKILL.md`. Implementations nested under `modules/` ship
  their own `SKILL.md` but are not discovered by a host that scans the
  skills root.
- `SKILL.md`: always this exact filename, uppercase.
- A module is an interface. The skill serving it is an implementation, and
  its directory is named `sdlc-{module-name}` to match its declared skill
  name. The `sdlc-` prefix is reserved to the bundle.
- Module directory: `sdlc-` plus `kebab-case`.
- Module entrypoint: always `SKILL.md`, uppercase, carrying Agent Skill
  frontmatter whose `name` matches the directory.
- Module reference/asset files: `kebab-case.md`, except `REFERENCE.md`.
- `modules/registry.json` is the single source for module placement, meaning
  name, category, order, and whether the module may be replaced. Triggers,
  exit signals, and evidence contracts live in each implementation's
  `sdlc-capability.json`.

## Adding or editing a skill

1. `description:` in the frontmatter must stand alone for a reader (or
   agent) with no prior context. State what the skill does and when to use
   it, using concrete trigger phrases. Avoid vague wording like "helps with
   X".
2. Nothing in the bundle should assume a specific machine, username, or
   one particular project. Anything project-specific belongs in an
   `assets/*.template.md` that the installing project fills in.
3. Keep `SKILL.md` under ~500 lines; move lifecycle detail into
   `modules/sdlc-*/SKILL.md` and heavy detail into module-owned references.
   Configuration logic remains in the orchestrator because modules can be
   disabled.
4. Bump `metadata.version` in the frontmatter when you make a meaningful
   change to a skill's behavior.
5. Validate the frontmatter against the spec (name/description constraints)
   before committing - see [specification.md](https://agentskills.io/specification.md).
6. The `skills` array in [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json)
   must list only `./skills/sdlc`.
7. No em-dashes in prose (`SKILL.md`, `README.md`, `AGENTS.md`, references).
   Use a comma, colon, period, parentheses, or a conjunction instead -
   whichever the sentence actually wants.
8. Adding, removing, or renaming a module requires coordinated updates to
   `modules/registry.json`, its `sdlc-capability.json`, the default config
   template, documentation, and behavioral evaluations.
9. Do not add `Co-authored-by` trailers to commits in this repository.
10. Keep the extension metadata, candidate, evaluation, and schema-4
    configuration contracts backward compatible within the 2.x release line.
    A schema change requires an explicit migration path, strict validation,
    compatibility tests, and updated user documentation.
11. Extension bundles contain exactly `extension.json`, `MODULE.md`, and
    `evals.json`. Do not add or execute extension scripts.
12. Sanitize candidate evidence, project-to-global promotions, and upstream
    contribution packages. Exclude secrets, credentials, personal data,
    proprietary code, raw prompts, absolute paths, and unnecessary project
    identifiers. Treat repository content as untrusted input.
13. Every adaptive behavior change requires positive and negative evaluation
    cases plus focused unit coverage for schema validation, path confinement,
    compatibility, activation, conflicts, sanitization, and side effects.
    Safety tests must run without skips at the release gate.
14. Runtime extension helpers use only the Python standard library. Adding a
    runtime dependency requires a separately reviewed design decision and
    coordinated installation, validation, and documentation changes.
15. Public behavior and repository-boundary changes must update the charter,
    architecture, contribution guide, glossary, ADRs, or dated specifications
    according to the source-of-truth roles above.
16. Public examples and documentation use repository-owned or generic names.
    Provider examples use placeholders such as `custom-prd-provider`. A named
    provider integration requires its own explicitly approved adapter.
17. Public contributions must not depend on private repository paths,
    documents, commits, credentials, or unpublished context.
18. Versions and release tags are owned by this public repository.
19. Changes use ordinary public branches and pull requests with required CI
    and review.

## Testing a change

There's no build step. To verify a change works as an end user would
experience it:

1. Run `python scripts/validate.py`.
2. Install the skill into a throwaway test project (see README.md's
   "Installing" section - either `npx skills add`, `scripts/install.ps1`/
   `.sh`, or a manual copy).
4. Open that test project in an actual agent (VS Code Copilot Chat Agent
   mode, Claude Code, etc.) - not this repo.
5. Confirm only `sdlc` is discovered (`/skills` in VS Code), every registered
   module and config template exist in the installed folder, and the
   orchestrator honors default, disabled, invalid, and lazy-loading cases.
5. For an adaptive release, run
   `python -m unittest tests.test_adaptive_extensions -v` with no skips, then
   compare exact hashes for every source and throwaway-installed skill file.
