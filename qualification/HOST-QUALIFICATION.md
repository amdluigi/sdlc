# Host qualification policy

This policy defines evidence levels for SDLC installation and behavior. It
prevents a host from being described as supported solely because it can read a
Markdown file.

## Levels

| Level | Meaning |
|---|---|
| Qualified | The manifest defines the host profile and current deterministic plus required live evidence satisfies the release gate. |
| Compatible by convention | The host supports the standard skill layout, but this repository has no host-specific qualification cell. |
| Experimental | A named host has a documented candidate profile or manual trial, but its qualification evidence is incomplete. Do not represent it as qualified. |
| Unsupported | The host cannot satisfy the required installation, discovery, or trusted replacement-provider boundary. |

## Promotion path

1. Add a candidate profile with project, global, copy, and link support stated
   explicitly.
2. Add deterministic installation coverage using only synthetic roots.
3. Run the manifest-selected behavioral cases on a project-copy baseline at
   least five times and retain only sanitized aggregates.
4. Verify discovery exposes only `sdlc`, the complete bundle hashes match, and
   default, disabled, invalid, and lazy-loading behavior is observed.
5. Record exact client version, skill version, installation cell, and review
   decision without personal paths, prompts, responses, or model identifiers.
6. Promote to Qualified only after the release gate accepts the profile.

Replacement providers are supported for a host only when it can enumerate
exact installed identities, detect duplicates, and bind an opaque load target.
Otherwise provider resolution remains unsupported even if ordinary bundle
installation is compatible.
