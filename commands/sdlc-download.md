---
name: sdlc-download
description: Install the bundled SDLC implementations this project is missing. Use after a check reports a gap and the developer agrees to install, or when asked to repair or complete an SDLC installation.
---

Install the implementations a check found missing.

Use this after `/sdlc-check` reports a gap, or when a developer asks to
repair or complete the installation. SDLC may reach for it on its own to
propose the remedy, but proposing and installing are different acts: see the
consent rule below.

Run, from the installed `sdlc` skill directory:

```bash
python scripts/manage_install.py download \
  --project-root . \
  --registry modules/registry.json \
  --sdlc-version <installed version> \
  --provider-root <skills directory> \
  --host-profile filesystem
```

This prints the single command that restores every missing bundled skill and
installs nothing. Show it to the developer.

Add `--run` only when the developer has agreed, or when running it was
itself their instruction. Never install software they have not accepted: an
agent that installs things unasked is not one a developer can leave alone
with a repository.

Only bundled implementations can be installed this way. When configuration
names an external provider that is not installed, there is no command to
offer, because SDLC does not know where a third party publishes. Report the
provider by name so the developer can install it or change the
configuration.
