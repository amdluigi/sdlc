'use strict';

const fs = require('node:fs/promises');
const vscode = require('vscode');
const { createBridge, digest } = require('./bridge');
const { run } = require('./driver');

const LIMITS = Object.freeze({ maxIterations: 8, maxToolCalls: 16, maxInputBytes: 131072,
  maxOutputBytes: 131072, maxWallMs: 120000 });
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

function activate(context) {
  context.subscriptions.push(vscode.commands.registerCommand('sdlc.runtime.run', () =>
    command().catch(() => vscode.window.showErrorMessage(
      'Bounded run did not complete. Inspect the local manager; unknown work must not be redispatched.'
    ))
  ));
}

module.exports = { activate };
