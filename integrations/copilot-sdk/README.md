# Optional isolated Copilot SDK adapter

This component is outside the portable skill bundle. The maintainer explicitly
selected an isolated official SDK adapter after the local execution milestone.
The portable runtime, installed skills and consumer execution policy remain
unchanged. This component is part of M2 preparation, not complete worker
qualification or automatic execution activation.

## Locked qualification boundary

Use official stable `github-copilot-sdk==1.0.28`, not a preview, from PyPI.
Published provenance is `github/copilot-sdk`, release `v1.0.28`, MIT license.
Use binary-only, hash-locked direct and transitive dependencies in an isolated
virtual environment with system packages disabled. Never install globally.
The portable bundle does not import or depend on this SDK.

The 14-package locked graph was checked against exact PyPI release metadata
and OSV on 2026-11-01: no matching advisories were returned. This is a dated
check, not a guarantee of absence. Declared licenses:

| Packages | License |
|----------|---------|
| annotated-types, anyio, github-copilot-sdk, h11, httpx, pydantic, pydantic_core, typing-inspection | MIT |
| certifi | MPL-2.0 |
| httpcore, idna, python-dateutil | BSD-3-Clause |
| typing_extensions | PSF-2.0 |
| tzdata | Apache-2.0 |

The native runtime is separately distributed by GitHub and retains its
publisher's terms; the SDK license does not relicense that binary. No runtime
binaries, vendor source or credentials are committed here.

For an explicitly selected isolated directory, restore using Python 3.12+
and the lock, not the unpinned dependency input:

```powershell
python -m venv $IsolatedDirectory
$IsolatedPython = Join-Path $IsolatedDirectory 'Scripts\python.exe'
$env:PIP_CONFIG_FILE = 'nul'
foreach ($name in @('PIP_INDEX_URL', 'PIP_EXTRA_INDEX_URL')) {
    if (Test-Path "Env:$name") { Remove-Item "Env:$name" }
}
& $IsolatedPython -m pip install --no-cache-dir -r integrations\copilot-sdk\requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Isolated SDK restore failed' }
& $IsolatedPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Isolated SDK dependency check failed' }
```

Run these environment overrides in a dedicated shell. Dependency updates
require renewed release/hash/license/advisory checks and a clean restore.
Windows restore and `pip check` passed for this lock; other native platform
restores and runtime qualification remain separate verification work.

The SDK may download its pinned native runtime automatically. This adapter
must never rely on that behavior. Explicitly provision the SDK-pinned runtime
in an isolated directory, using the official checksum-verifying downloader;
verify a complete local inventory before invoking it. Disable automatic
downloads for all qualification use. Do not update an existing Copilot CLI.
Installed CLI version is not evidence of SDK transport compatibility.

Qualification API: `async qualify(config)`. The strict version-1 input has:

- `schemaVersion: 1`;
- `sdkVersion: "1.0.28"`;
- `runtime`: `root`, `version`, `entrypoint`, and complete `files` inventory
  (`path`, `sha256`, `bytes`);
- explicitly supplied bounded positive `timeoutSeconds`.

The locked native runtime is `github/copilot-cli` release `v1.0.105`, SDK
protocol 3. The native runtime is distinct from the installed CLI host.
Current actual qualification is Windows x64 with Python 3.14; other platform
runtime trials remain unverified.
Inventory limits are 256 files, 512 MiB total and 2 MiB canonical input.
Timeout must be 1-300 seconds and separately bounds startup/status/ping and
shutdown, not local inventory hashing. These are qualification limits, not
paid worker or spend defaults. The verified response is `pong: <nonce>`.

Reject links/reparse points, traversal, unknown fields, duplicate/case-alias
inventory entries, missing/extra files, altered hashes, unsupported SDK/runtime
versions, invalid response shapes and unsuccessful shutdown. Reuse bundled
strict contract primitives and safe local filesystem checks without modifying
legacy helpers. All invocation inputs and operations remain explicit.

The adapter starts the verified native runtime over official SDK stdio with
an isolated base directory and empty client mode, ambient logged-in-user use
disabled and native direct telemetry plus OpenTelemetry disabled. Qualification
only performs a version check and SDK ping with a synthetic nonce. It does not
create a worker session, send a model prompt, access project files, enable
session stores or make an inference request.

Success explicitly qualifies only transport/runtime binding. Worker/tool
boundaries, effective model routing, billing, cancellation, filesystem
isolation and lifecycle acceptance remain `not-assessed` or `not-run`.
No success-shaped fallback for missing or incompatible integration.

Run from a checkout using the isolated environment's Python:

```powershell
& $IsolatedPython integrations\copilot-sdk\copilot_adapter.py --input $LocalConfig
```

The caller supplies both paths explicitly. No runtime is provisioned by this
command. The input inventory must come from an independently verified official
release; accepting caller hashes does not establish publisher authenticity.
The local owner must prevent concurrent artifact modification. This is not an
OS sandbox or a race-proof boundary against a hostile filesystem owner.
Success is metadata-only JSON with semantic approval explicitly unassessed,
the observed SDK/runtime/protocol, inventory digest/count/bytes and the
qualification limitations above. It omits local root paths and SDK messages.
Failures produce the existing `error[CODE] POINTER: MESSAGE` CLI form and a
nonzero exit; shutdown failure supersedes any earlier transport failure.
Failed or interrupted graceful shutdown invokes a separately bounded official
SDK `force_stop()` before releasing temporary storage. Successful forced
cleanup does not turn failed qualification into success. If it also fails,
the adapter reports that cleanup is unconfirmed; no arbitrary process is killed.
Pinned SDK RPC exception classes are used only to normalize transport
diagnostics; the adapter does not implement a separate RPC protocol.

## Verification and next gate

Use the existing standard-library unittest runner for contract and SDK-seam
tests. A mock may prove callback/configuration behavior but never actual SDK
integration. Separately record the actual pinned SDK/native-runtime ping and
shutdown trial in an isolated environment.

Run `verify_sdk_seams.py` with the isolated Python to exercise the actual
pinned SDK response parsers and shutdown/forced-cleanup implementations against
explicit in-memory RPC/process seams. It forbids process launch and inference;
it complements, never replaces, the actual verified-runtime qualification.
This optional check requires the SDK, while ordinary unittest discovery
remains dependency-free and has no skipped SDK tests.

Assess direct/transitive integrity, licenses and current advisories; test a
clean hash-enforced restore. Preserve source/release/integrity identities, not
third-party package source or runtime binaries in Git.

A real harmless worker/tool/receipt trial requires explicitly approved model,
timeout, request/spend constraints and supported cancellation. No paid worker
trial is authorized by this qualification step. M2 is not complete until that
gate and profile/delegation integration evidence exist.
