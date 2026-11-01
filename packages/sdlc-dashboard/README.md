# SDLC execution snapshot dashboard

An optional CommonJS JavaScript VS Code extension, separate from the portable
Python skill bundle. It uses only host-provided `vscode` and Node built-ins.
There are no dependencies, build downloads, background collectors or global
installation steps.

## Read-only workflow

1. Explicitly export one execution snapshot using the portable manager CLI:

   ```powershell
   $json = python -B skills\sdlc\scripts\manage_insights.py snapshot --project-root $project --execution-id example
   if ($LASTEXITCODE -ne 0) { throw 'Execution snapshot export failed' }
   [IO.File]::WriteAllText((Join-Path $project 'execution-snapshot.json'), ($json -join "`n"), [Text.UTF8Encoding]::new($false))
   ```

   Check the CLI exit status before writing its stdout. The extension never
   runs this command, discovers histories, changes telemetry consent, or
   modifies manager state.

2. In a trusted local workspace, invoke **SDLC: Open Execution Snapshot** from
   the Command Palette. Choose the confining workspace folder, then its
   exported JSON file. No directory search or automatic selection occurs.
3. Navigate **SDLC Execution Snapshot** in Explorer with Up/Down and
   Left/Right. The tree exposes state names, native focus semantics and theme
   icons. All task text is plain metadata, not markup or executable content.
4. Re-export explicitly and invoke **SDLC: Refresh Execution Snapshot**.
   Refresh retains a surviving selected node without requesting keyboard
   focus. Loading, cancellation, invalid input and failed refresh clear the
   previous validated view.
   Overlapping refreshes retain only the in-flight source/binding, not displayed
   data; only the newest validated result can restore the view.

Only two extension commands exist: `sdlc.execution.openSnapshot` and
`sdlc.execution.refreshSnapshot`. The contributed view is context-hidden
until a command opens it. The only internal VS Code command is documented
`setContext`, used solely to expose that native view. There are no Webviews,
HTML, MarkdownString tooltips, command URIs, messages, file watchers, network
requests, subprocesses, approval controls or arbitrary command dispatch.

## Snapshot contract and trust boundary

- Exact version 1, kind `sdlc-execution-snapshot`, required closed fields at
  every level, unique task IDs, at most 256 tasks and 2 MiB of file/canonical
  data. Duplicate JSON keys, malformed UTF-8, unknown fields, unsupported
  versions and noninteger/out-of-range numbers fail closed.
- Digests use SHA-256 of all fields except `snapshotDigest`, encoded as
  sorted-key compact ASCII JSON. The parser preserves full signed-64-bit
  nonnegative contract integers using BigInt when necessary. Python Unicode
  and surrogate escaping are preserved without lossy JS number conversion.
- The selected file must be below the explicitly selected local workspace.
  Ancestors are checked with `lstat` and `realpath`; exposed symbolic links
  and Windows junctions, path substitutions, directories, Windows network/
  device/alternate-stream paths, oversized files and detected read races
  are rejected. Reads use a bounded buffer and recheck file and ancestor
  identities after reading.
- A refresh cannot change execution ID, roll back a known plan revision or
  rewrite a plan digest at the same revision. Failures discard both data and
  the active selection; explicitly reopen a valid export to recover.

**An export is never proof of live freshness or authenticity.** This fixed
schema has no source timestamp or manager connection. A recomputed digest
proves consistency, not authorship. Approval, lock and controls are explicitly
labelled *at export*, without UI authority. An older export with an otherwise
valid binding cannot be identified as old on initial open, nor can this
watcher-free interface discover later file changes until refresh. Declared
estimates, manager-recorded intervals and requested models are labelled
separately; unknown values stay unknown, not zero or observed host evidence.

### Filesystem qualification limits

Node's documented Windows `lstat` API exposes symbolic links/junctions but
does not expose every arbitrary Windows reparse tag. This package does not
claim a complete all-reparse-tag rejection proof, hostile concurrent
filesystem isolation, or cloud-placeholder filesystem qualification.
Use an ordinary local filesystem and trusted local exports. Environments
requiring proof against every reparse tag or adversarial directory swapping
must not enable this dashboard until a separately qualified native boundary
exists. No process-based attribute inspection is silently substituted.

## Development and qualification

```powershell
Set-Location packages\sdlc-dashboard
npm test
npm run check
npm run qualify
```

These commands need Node 20 or newer and install nothing. Unit tests cover the
strict contract, provider states and real filesystem reads. Provider tests
declare a simulated VS Code API seam; they are not actual-host evidence.

For an actual-host run, create an isolated disposable workspace containing
`python-snapshot.json`: an actual `build_snapshot` export whose first task
has estimate `9223372036854775807` and a title containing `Ω 😀`. Do not use a
consumer workspace. Derive the installed executable from `code.cmd`:

```powershell
$exe = Join-Path (Split-Path (Split-Path (Get-Command code.cmd).Source)) 'Code.exe'
& $exe --new-window --user-data-dir $isolatedUserData --extensions-dir $isolatedExtensions `
  --extensionDevelopmentPath=$package --extensionTestsPath=(Join-Path $package 'test\host.js') `
  --disable-extensions --disable-workspace-trust --skip-welcome --skip-release-notes $disposableWorkspace
```

All four paths must be explicitly chosen absolute paths outside consumer
configuration. `test\host.js` exercises the installed extension API and
actual file/TreeView transport, writes `host-result.json` only inside that
disposable workspace, and returns. It tests inactive-until-command behavior,
Unicode/int64 Python parity, native selection preservation and failed/
unconfined reloads. This is not a replacement for GUI or assistive-input
qualification.

See [QUALIFICATION.md](QUALIFICATION.md) for observed host evidence and
remaining limitations. Do not infer supported Marketplace distribution,
automatic packaging, minimum-engine qualification, or full accessibility
certification from a development-host test.

## Rollback

Close the isolated development host or disable/remove this optional package.
Delete exported files only by an explicit user action. The portable manager,
skill installation, policies, execution records and telemetry remain
unchanged.

## Native API references

- [Tree View guide](https://code.visualstudio.com/api/extension-guides/tree-view)
- [Extension API](https://code.visualstudio.com/api/references/vscode-api)
- [Activation events](https://code.visualstudio.com/api/references/activation-events)
- [Extension testing](https://code.visualstudio.com/api/working-with-extensions/testing-extension)
- [Node filesystem API](https://nodejs.org/api/fs.html)
