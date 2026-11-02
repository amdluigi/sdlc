# SDLC execution dashboard

An optional CommonJS JavaScript VS Code extension, separate from the portable
Python skill bundle. It uses the host-provided `vscode` API, Node built-ins
and one fixed local Python bridge to the existing execution manager. There
are no dependencies, build downloads, background collectors or global
installation steps.

## Exported snapshot workflow

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

The exported snapshot remains read-only. Its open and refresh commands retain
their existing behavior and never contact the execution manager.

## Live manager workflow

1. In a trusted local workspace, invoke **SDLC: Open Live Execution Manager**.
   Choose one currently open local project and one manager-owned execution.
   The command reads only the selected project's execution records.
2. Navigate **SDLC Execution Manager** for current task details, status
   filters, aggregate progress and recent manager events. Opening the view
   performs one read-only inspection. It does not start a worker, resume
   autonomous dispatch or enable polling.
3. Use **SDLC: Refresh Live Execution Manager** for one explicit refresh.
   Live updates are off by default. **SDLC: Start Live Manager Updates**
   enables three-second reads for that selected execution; use **Stop Live
   Manager Updates** to turn them off. Hiding the manager view also stops
   polling; changing the selected execution or losing a refresh stops it too.
   Showing the view again does not restart polling automatically. Start
   updates explicitly while the view is visible.
4. Plan approval, controls approval, independent acceptance, pause/resume and
   cancellation intent are separate commands. Each shows an explicit modal
   confirmation that shows the selected project, execution, plan revision and
   the full current plan, execution policy, controls policy and controls state
   digests, plus the selected task, attempt and result where relevant. The
   confirmation is bound to those values, and the manager rechecks the exact binding under its writer before
   changing state. Acceptance requires user-entered revision, command and
   verification summary, and never accepts a worker declaration by itself.
   A bounded batch or autonomous result is accepted only through
   independent operator validation bound to its exact result digest, which
   the modal and task details show; worker verification is never treated as
   passed, and a worker-reported failure needs a new attempt.
   Live polling is suspended while a confirmation or acceptance input is open
   and while the write runs, so an unchanged refresh never invalidates the
   confirmation and a successful write never reports a false failure.
   Afterwards polling resumes only if it was enabled and the view is still
   visible, starting with one current refresh. A real state change is still
   rejected by the manager writer and then refreshed; changing the selected
   execution invalidates the pending action.
   Cancellation records local intent only; this host has no qualified remote
   stop operation.

The bridge invokes only the package's fixed `manager_bridge.py` with
`python -B -I`, JSON stdin, no shell and a closed operation allowlist. It does not
accept caller-supplied scripts, discover other histories, call the network,
or expose prompts, transcripts or raw task output. Manager event refresh is
read-only and is never an autonomous dispatch trigger.

Both contributed views remain context-hidden until their corresponding open
command is used. There are no Webviews, HTML, MarkdownString tooltips or
command URIs. VS Code commands are explicit palette actions; opening a view
does not silently approve policy or control changes.

## Snapshot contract and trust boundary

- Exact version 1 or 2, kind `sdlc-execution-snapshot`, required closed fields
  at every level. Version 2 requires task `acceptanceBasis`, non-null exactly
  for accepted tasks, and the tree shows it as recorded provenance
  (independent operator validation is never shown as worker verification
  passing). Live manager views carry the same task field. Task IDs are
  unique, with at most 256 tasks and 2 MiB of file/canonical data. Duplicate JSON keys, malformed UTF-8, unknown fields, unsupported
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

The live manager view uses its own closed version-1 contract. It is produced
by the local manager, digest-checks its structured projection and binds
mutations to plan, policy, control and control-state digests. A displayed
digest is not independent authentication and is never sufficient authority
for an action. The manager writer revalidates the live binding. Unknown,
stale or malformed state disables actions. Only task metadata and a bounded
recent event list are rendered.

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
strict contracts, provider states, manager bridge against real manager files,
and export filesystem reads. VS Code API tests use a declared simulated host
seam; they are not actual-host evidence.

The existing actual-host procedure below qualifies the export TreeView and
filesystem boundary only. It does not qualify live-manager actions, polling
timing, worker dispatch, accessibility certification or remote cancellation.
For an actual-host export run, create an isolated disposable workspace containing
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
