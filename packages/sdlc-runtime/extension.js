'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');
const vscode = require('vscode');
const { createBridge, digest } = require('./bridge');
const { run } = require('./driver');

const LIMITS = Object.freeze({ maxIterations: 8, maxToolCalls: 16, maxInputBytes: 131072,
  maxOutputBytes: 131072, maxWallMs: 120000 });
const MAX_BATCH_FILE_BYTES = 2 * 1024 * 1024;
let busy = false;

async function command() {
  if (busy) throw new Error('A local bounded worker is already active');
  busy = true;
  try { await runCommand(); }
  finally { busy = false; }
}

async function runCommand() {
  if (!vscode.workspace.isTrusted) throw new Error('A trusted local workspace is required');
  if (vscode.env.remoteName) throw new Error('Only a local extension host is supported');
  const folders = (vscode.workspace.workspaceFolders || []).filter(folder => folder.uri.scheme === 'file');
  const folder = await vscode.window.showQuickPick(folders.map(item => ({
    label: item.name, description: item.uri.fsPath, folder: item
  })), { title: 'Select the explicitly approved execution project', ignoreFocusOut: true });
  if (!folder) return;
  const chosen = await vscode.window.showOpenDialog({ canSelectMany: false, filters: { 'Task brief': ['json'] },
    title: 'Select a current manager-bound task brief' });
  if (!chosen?.length || chosen[0].scheme !== 'file') return;
  const info = await fs.lstat(chosen[0].fsPath);
  if (!info.isFile() || info.isSymbolicLink() || info.size > 2 * 1024 * 1024) {
    throw new Error('Brief must be a bounded regular local JSON file');
  }
  const brief = JSON.parse(await fs.readFile(chosen[0].fsPath, 'utf8'));
  const role = await vscode.window.showQuickPick(['developer', 'architecture', 'testing', 'review'],
    { title: 'Select the role matching the approved task' });
  if (!role) return;
  const models = await vscode.lm.selectChatModels({});
  if (!models.length) {
    await vscode.window.showErrorMessage(
      'No language model is available. Configure a provider in this editor before running a bounded worker.'
    );
    return;
  }
  const selected = await vscode.window.showQuickPick(models.map(model => ({
    label: model.name, description: `${model.vendor} / ${model.id}`,
    detail: `${model.family} / ${model.version}`, model
  })), { title: 'Select the provider/model for this one bounded run; prices are unknown', ignoreFocusOut: true });
  if (!selected) return;
  const model = selected.model;
  const bridge = createBridge(folder.folder.uri.fsPath);
  let commands;
  if (brief.allowedActions.includes('execute')) {
    const selection = await vscode.window.showOpenDialog({ canSelectMany: false,
      filters: { 'Exact command definitions': ['json'] },
      title: 'Select separately approved exact executable/argv definitions; no shell or install' });
    if (!selection?.length || selection[0].scheme !== 'file') return;
    const metadata = await fs.lstat(selection[0].fsPath);
    if (!metadata.isFile() || metadata.isSymbolicLink() || metadata.size > 65536) {
      throw new Error('Command definitions must be a bounded regular local JSON file');
    }
    commands = JSON.parse(await fs.readFile(selection[0].fsPath, 'utf8'));
    const consent = await vscode.window.showWarningMessage('Authorize these exact local commands?', {
      modal: true, detail: [
        `Project/cwd: ${folder.folder.uri.fsPath}`,
        JSON.stringify(commands, null, 2),
        'Each executable, argument, cwd, timeout and output bound is separately authorized.',
        'No shell, install, network, OS sandbox, retry or automatic acceptance.',
        'Only command IDs will be offered to the worker. Commands run with your local account permissions.'
      ].join('\n')
    }, 'Authorize exact commands');
    if (consent !== 'Authorize exact commands') return;
  }
  const envelope = await bridge(commands ? 'prepare_execute' : 'prepare', {
    executionId: brief.binding.executionId, brief, role,
    model: { id: model.id, vendor: model.vendor, family: model.family, version: model.version }, limits: LIMITS,
    ...(commands ? { commands } : {})
  });
  const confirmed = await vscode.window.showWarningMessage('Authorize this one bounded model run?', {
    modal: true,
    detail: [
      `Project: ${envelope.request.projectRoot}`,
      `Provider/model: ${model.vendor} / ${model.id} / ${model.family} / ${model.version}`,
      `Native request digest: ${digest(envelope.request)}`,
      `Runtime/model/limits digest: ${digest(envelope)}`,
      `Limits: ${JSON.stringify(LIMITS)}`,
      `Actions: ${brief.allowedActions.join(', ')}`,
      `Owned files: ${brief.ownership.join(', ')}`,
      `Readable guidance: ${brief.guidance.join(', ')}`,
      ...(commands ? [`Exact version-2 commands and executable digests: ${JSON.stringify(envelope.commands)}`] : []),
      'This sends the brief and requested approved file content to the selected model.',
      `No monetary cap, ${commands ? 'unlisted command, ' : 'execute, '}retry, automatic acceptance, telemetry or transcript storage.`,
      'Cancellation stops local progress, not confirmed remote work. Real routing/billing remain unqualified.'
    ].join('\n')
  }, 'Authorize once');
  if (confirmed !== 'Authorize once') return;
  await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification,
      title: 'SDLC bounded worker (local cancellation only)', cancellable: true }, async (_, token) => {
      const controller = new AbortController();
      const subscription = token.onCancellationRequested(() => controller.abort());
      if (token.isCancellationRequested) controller.abort();
      try {
        await run({ envelope, bridge, signal: controller.signal,
          respond: async (prompt, signal) => {
            const cancellation = new vscode.CancellationTokenSource();
            const cancel = () => { cancellation.cancel(); cancellation.dispose(); };
            signal.addEventListener('abort', cancel, { once: true });
            if (signal.aborted) cancellation.cancel();
            try {
              const response = await model.sendRequest([vscode.LanguageModelChatMessage.User(prompt)], {}, cancellation.token);
              return (async function* () {
                try { for await (const text of response.text) yield text; }
                finally { signal.removeEventListener('abort', cancel); cancellation.dispose(); }
              })();
            } catch (error) {
              signal.removeEventListener('abort', cancel);
              cancellation.dispose();
              throw error;
            }
          }
        });
      } finally { subscription.dispose(); }
  });
  vscode.window.showInformationMessage('Worker receipt recorded. Independent manager acceptance is still required.');
}

async function batchCommand() {
  if (busy) throw new Error('A local bounded worker is already active');
  busy = true;
  try { await runBatchCommand(); }
  finally { busy = false; }
}

async function runBatchCommand({ folder: suppliedFolder, prepareOnly = false } = {}) {
  if (!vscode.workspace.isTrusted) throw new Error('A trusted local workspace is required');
  if (vscode.env.remoteName) throw new Error('Only a local extension host is supported');
  const folders = (vscode.workspace.workspaceFolders || []).filter(folder => folder.uri.scheme === 'file');
  const folder = suppliedFolder || await vscode.window.showQuickPick(folders.map(item => ({
    label: item.name, description: item.uri.fsPath, folder: item
  })), { title: 'Select the explicitly approved execution project', ignoreFocusOut: true });
  if (!folder) return;
  const chosen = await vscode.window.showOpenDialog({ canSelectMany: false,
    filters: { 'Execution batch': ['json'] },
    title: suppliedFolder ? `Select the exact finite batch for ${folder.label}` :
      'Select the exact finite local batch definition' });
  if (!chosen?.length || chosen[0].scheme !== 'file') return;
  const info = await fs.lstat(chosen[0].fsPath);
  if (!info.isFile() || info.isSymbolicLink() || info.size > MAX_BATCH_FILE_BYTES) {
    throw new Error('Batch must be a bounded regular local JSON file');
  }
  const handle = await fs.open(chosen[0].fsPath, 'r');
  let batchBytes;
  try {
    const opened = await handle.stat();
    if (!opened.isFile() || opened.size > MAX_BATCH_FILE_BYTES) {
      throw new Error('Batch must be a bounded regular local JSON file');
    }
    const buffer = Buffer.alloc(MAX_BATCH_FILE_BYTES + 1);
    let offset = 0;
    while (offset < buffer.length) {
      const { bytesRead } = await handle.read(buffer, offset, buffer.length - offset, offset);
      if (!bytesRead) break;
      offset += bytesRead;
    }
    if (offset > MAX_BATCH_FILE_BYTES || offset !== opened.size) {
      throw new Error('Batch changed while being read or exceeds the bounded input capacity');
    }
    batchBytes = buffer.subarray(0, offset);
  } finally { await handle.close(); }
  if (batchBytes.length > MAX_BATCH_FILE_BYTES) {
    throw new Error('Batch exceeds the bounded local input capacity');
  }
  let batchJson;
  try { batchJson = new TextDecoder('utf-8', { fatal: true }).decode(batchBytes); }
  catch {
    const error = new Error('Batch must be valid UTF-8 JSON');
    error.code = 'E_UTF8';
    throw error;
  }
  const bridge = createBridge(folder.folder.uri.fsPath);
  const preview = await bridge('preview_batch_json', { batchJson });
  const models = await vscode.lm.selectChatModels({});
  const modelById = new Map();
  for (const attempt of preview.batch.tasks.flatMap(task => task.attempts)) {
    const matches = models.filter(model => model.id === attempt.modelId);
    if (matches.length !== 1) {
      const error = new Error('Every preapproved exact model must be uniquely available in this IDE');
      error.code = 'E_MODEL_UNAVAILABLE';
      throw error;
    }
    modelById.set(attempt.modelId, matches[0]);
  }
  const attemptLines = preview.batch.tasks.flatMap(task => task.attempts.map(attempt =>
    `${task.taskId}/${attempt.attemptId}: ${attempt.modelId}, brief ${digest(attempt.brief)}, ` +
    `limits ${JSON.stringify(attempt.limits)}`));
  const confirmed = await vscode.window.showWarningMessage('Authorize this exact finite local batch?', {
    modal: true,
    detail: [
      `Current IDE: ${vscode.env.appName} ${vscode.version}`,
      `Project: ${folder.folder.uri.fsPath}`,
      `Batch: ${preview.batchId}`,
      `Batch digest: ${preview.batchDigest}`,
      `Current plan/policy/controls digests: ${preview.planDigest} / ${preview.executionPolicyDigest} / ${preview.controlsDigest}`,
      `Exact task/attempt/model/brief digests:`,
      `Initial schedule: ${preview.schedule.map(item => `${item.taskId} (${item.status}, ${item.attempts} attempts)`).join('; ')}`,
      ...attemptLines,
      `Cumulative limits: ${JSON.stringify(preview.cumulativeLimits)}`,
      'A monetary spend cap and authoritative usage/billing data are unavailable. If a spend cap is required, do not authorize this batch.',
      'IDE model availability does not prove effective routing. Local stream completion does not confirm billing or remote termination.',
      'No execute, shell, install, automatic acceptance, manager approval, policy adoption, telemetry or transcript storage.',
      'Only the exact approved attempts and their ordered retry/model choices can be dispatched.'
    ].join('\n')
  }, 'Authorize exact batch');
  if (confirmed !== 'Authorize exact batch') return;
  await bridge('approve_batch', { batch: preview.batch, batchDigest: preview.batchDigest });
  const prepared = { folder, bridge, preview, modelById };
  return prepareOnly ? prepared : executeBatch(prepared);
}

async function executeBatch({ folder, bridge, preview, modelById }, group) {
  let finalStatus = 'unknown-barrier';
  await vscode.window.withProgress({
    location: vscode.ProgressLocation.Notification,
    title: 'SDLC bounded batch (local cancellation only)', cancellable: true
  }, async (_, token) => {
    const controller = new AbortController();
    const cancel = () => controller.abort();
    const subscription = token.onCancellationRequested(() => {
      controller.abort();
      group?.abort();
    });
    group?.signal.addEventListener('abort', cancel, { once: true });
    if (group?.signal.aborted) controller.abort();
    if (token.isCancellationRequested) {
      controller.abort();
      group?.abort();
    }
    try {
      const maximumAttempts = preview.batch.tasks.reduce((total, task) => total + task.attempts.length, 0);
      for (let count = 0; count <= maximumAttempts; count++) {
        if (controller.signal.aborted) return;
        const next = await bridge('next_attempt', {
          batch: preview.batch, batchDigest: preview.batchDigest
        });
        if (controller.signal.aborted) return;
        finalStatus = next.status;
        if (!next.dispatch) return;
        const model = modelById.get(next.modelId);
        if (!model) {
          const error = new Error('The preapproved model is no longer available');
          error.code = 'E_MODEL_UNAVAILABLE';
          throw error;
        }
        const envelope = await bridge('prepare_batch', {
          batch: preview.batch, batchDigest: preview.batchDigest,
          taskId: next.taskId, attemptId: next.attemptId, brief: next.brief,
          role: preview.batch.tasks.find(task => task.taskId === next.taskId).role,
          model: { id: model.id, vendor: model.vendor, family: model.family, version: model.version },
          limits: next.limits
        });
        if (controller.signal.aborted) return;
        await run({ envelope, bridge, signal: controller.signal,
          respond: async (prompt, signal) => {
            const cancellation = new vscode.CancellationTokenSource();
            const cancel = () => { cancellation.cancel(); cancellation.dispose(); };
            signal.addEventListener('abort', cancel, { once: true });
            if (signal.aborted) cancellation.cancel();
            try {
              const response = await model.sendRequest(
                [vscode.LanguageModelChatMessage.User(prompt)], {}, cancellation.token
              );
              return (async function* () {
                try { for await (const text of response.text) yield text; }
                finally { signal.removeEventListener('abort', cancel); cancellation.dispose(); }
              })();
            } catch (error) {
              signal.removeEventListener('abort', cancel);
              cancellation.dispose();
              throw error;
            }
          }
        });
      }
      finalStatus = 'attempts-exhausted';
    } finally {
      subscription.dispose();
      group?.signal.removeEventListener('abort', cancel);
    }
  });
  const prefix = group ? `[${folder.label}] ` : '';
  if (finalStatus === 'complete') {
    vscode.window.showInformationMessage(prefix +
      'Batch attempts are complete. Independent manager acceptance is still required.');
  } else {
    vscode.window.showInformationMessage(
      `${prefix}Batch paused (${finalStatus}); no implicit acceptance or unconfirmed-work redispatch occurred.`
    );
  }
}

async function parallelBatchCommand() {
  if (busy) throw new Error('A local bounded worker is already active');
  busy = true;
  try {
    if (!vscode.workspace.isTrusted) throw new Error('A trusted local workspace is required');
    if (vscode.env.remoteName) throw new Error('Only a local extension host is supported');
    const folders = (vscode.workspace.workspaceFolders || []).filter(folder => folder.uri.scheme === 'file');
    const selected = await vscode.window.showQuickPick(folders.map(folder => ({
      label: folder.name, description: folder.uri.fsPath, folder
    })), { title: 'Select exactly two independent isolated projects', canPickMany: true, ignoreFocusOut: true });
    if (!selected) return;
    if (selected.length !== 2) throw new Error('Exactly two independent project roots are required');
    const roots = await Promise.all(selected.map(item => fs.realpath(item.folder.uri.fsPath)));
    const info = await Promise.all(roots.map(root => fs.stat(root, { bigint: true })));
    const nested = (parent, child) => {
      const relative = path.relative(parent, child);
      return relative === '' || (relative !== '..' && !relative.startsWith('..' + path.sep) &&
        !path.isAbsolute(relative));
    };
    if (info.some(item => !item.isDirectory()) ||
        info[0].dev === info[1].dev && info[0].ino === info[1].ino ||
        nested(roots[0], roots[1]) || nested(roots[1], roots[0])) {
      throw new Error('Parallel project roots must be distinct and nonoverlapping');
    }
    const confirmed = await vscode.window.showWarningMessage('Run two independent project batches in parallel?', {
      modal: true,
      detail: [
        ...roots.map((root, index) => `Project ${index + 1}: ${root}`),
        'Use independent checkouts/worktrees only; no shared editable project or cross-project dependencies.',
        'Each project requires its own current exact batch/model/budget confirmation before either starts.',
        'At most two existing finite serial controllers run. No automatic acceptance or policy adoption.',
        'Cancellation or failure stops local progress in both; remote termination and billing remain unknown.'
      ].join('\n')
    }, 'Review both exact batches');
    if (confirmed !== 'Review both exact batches') return;
    const prepared = [];
    for (let index = 0; index < selected.length; index++) {
      const folder = { ...selected[index], folder: {
        ...selected[index].folder, uri: { scheme: 'file', fsPath: roots[index] }
      } };
      const batch = await runBatchCommand({ folder, prepareOnly: true });
      if (!batch) return;
      prepared.push(batch);
    }
    const group = new AbortController();
    const outcomes = await Promise.allSettled(prepared.map(async batch => {
      try { await executeBatch(batch, group); }
      catch (error) { group.abort(); throw error; }
    }));
    const failures = outcomes.filter(item => item.status === 'rejected');
    if (failures.length) throw new AggregateError(failures.map(item => item.reason), 'Parallel batch failure');
  } finally { busy = false; }
}

function activate(context) {
  context.subscriptions.push(vscode.commands.registerCommand('sdlc.runtime.run', () =>
    command().catch(() => vscode.window.showErrorMessage(
      'Bounded run did not complete. Inspect the local manager; unknown work must not be redispatched.'
    ))
  ));
  context.subscriptions.push(vscode.commands.registerCommand('sdlc.runtime.runBatch', () =>
    batchCommand().catch(error => {
      const code = /^E_[A-Z_]+$/.test(error?.code || '') ? error.code : 'E_RUNTIME_UNKNOWN';
      vscode.window.showErrorMessage(
        `Bounded batch stopped (${code}). Inspect local manager history before taking further action.`
      );
    })
  ));
  context.subscriptions.push(vscode.commands.registerCommand('sdlc.runtime.runParallelBatches', () =>
    parallelBatchCommand().catch(error => {
      const failures = error instanceof AggregateError ? error.errors : [error];
      const codes = [...new Set(failures.map(item =>
        /^E_[A-Z_]+$/.test(item?.code || '') ? item.code : 'E_RUNTIME_UNKNOWN'))];
      vscode.window.showErrorMessage(
        `Parallel batches stopped (${codes.join(', ')}). Inspect both local managers; unknown work must not be redispatched.`
      );
    })
  ));
}

module.exports = { activate };
