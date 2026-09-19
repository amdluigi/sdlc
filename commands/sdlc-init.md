---
name: sdlc-init
description: Create the SDLC project configuration when the project has none. Use before the first non-trivial change in a project with no .sdlc/config.json, or when a developer asks to configure, enable, disable, or replace lifecycle phases.
---

Create `.sdlc/config.json` for this project.

Use this before the first non-trivial change in a project that has no
configuration, or when a developer wants to enable, disable, or replace a
lifecycle capability and has nothing to edit yet. SDLC runs it without being
asked; a developer can also run it directly. Skip it for trivial work, which
needs no configuration.

Run, from the installed `sdlc` skill directory:

```bash
python scripts/manage_install.py init --project-root .
```

The configuration lists every capability grouped by delivery phase, all
enabled. Editing it is how a developer disables a phase or replaces a
capability with another skill.

This never overwrites an existing configuration. A configuration records
decisions a developer made, and regenerating it from the template would
silently re-enable phases they switched off. If one exists, report that and
leave it alone.

Say what was written and that the defaults enable every phase, so the
developer knows there is something to review. Then continue with the work
that prompted it.
