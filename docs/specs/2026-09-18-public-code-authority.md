# Public Code Authority

## Status: Approved

## Outcome

The public `skills` repository is the authoritative home for SDLC product
code, tests, public documentation, CI, versions, releases, and contributions.

## Contribution model

Contributors fork the public repository, create focused branches, run the
documented checks, and open pull requests against public `main`. Public CI and
review determine whether a change merges.

Contributing does not require access to private maintainer context or another
repository.

## Authority boundaries

- Public code and public documentation are authoritative only after merge to
  public `main`.
- Optional private roadmap, research, or decision material does not define or
  duplicate public product code.
- Versions and release tags belong to the public repository.
- Public scripts never read private files or paths.
- Public pull request discussions contain the review record for public code.

## Repository guarantees

The public repository remains:

- independently understandable;
- independently testable;
- independently installable;
- compatible with ordinary forks and pull requests;
- free of private paths, credentials, raw transcripts, and proprietary
  evaluation data.

## Verification

Every public pull request runs:

- the complete unit suite;
- structural repository validation;
- qualification-manifest validation;
- Bash and PowerShell syntax checks;
- cache, whitespace, and prohibited-trailer checks.

## Migration

The former generated-snapshot workflow is retired. Its marker, release
manifest, standalone snapshot verifier, and private publication dependency are
removed from the public repository.

The historical design remains available in the superseded specification for
decision context. It is not an active implementation requirement.
