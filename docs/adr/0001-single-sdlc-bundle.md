---
status: accepted
---

# Ship one discoverable SDLC bundle

The repository ships one discoverable `sdlc` skill and keeps lifecycle
capabilities as internal modules. This avoids competing always-on skills,
supports one configuration and evidence model, and lets modules evolve or
load independently without requiring developers to coordinate separate
installations.

## Considered Options

- Multiple independently discoverable lifecycle skills.
- One orchestrator with internal modules.

## Consequences

The complete skill directory must be installed as a unit. New lifecycle
capabilities normally become modules or extensions rather than new top-level
skills.
