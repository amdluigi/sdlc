---
name: sdlc-check
description: Report which SDLC delivery phases have an implementation and which are missing. Use at the start of SDLC work, before relying on a lifecycle phase, or whenever a capability appears unavailable.
---

Report the health of this SDLC installation.

Use this when SDLC work begins, before depending on a phase, or when a
capability seems absent. SDLC runs it without being asked; a developer can
also run it directly. It reads two files and stats the installed skills,
never contacts the network, and changes nothing, so running it is always
safe.

Run, from the installed `sdlc` skill directory:

```bash
python scripts/manage_install.py check \
  --project-root . \
  --registry modules/registry.json \
  --sdlc-version <installed version> \
  --provider-root <skills directory> \
  --host-profile filesystem
```

The report lists every capability under its delivery phase and marks it
`ok`, `MISSING`, or `disabled`. Configuration decides what is required: a
disabled capability is never reported missing, and a capability replaced by
another skill requires that skill rather than the bundled one.

Exit code 0 means the installation is whole; 1 means something enabled has
no implementation.

Show the report as printed; it is already grouped and ordered for reading.
When something is missing, name the phase that loses its entry gate, then
offer `/sdlc-download`. Do not quietly continue without a phase the
developer expects to run.
