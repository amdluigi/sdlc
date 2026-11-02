'use strict';

// Run only with an isolated development host and a disposable synthetic project.
const vscode = require('vscode');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');

async function bounded(promise) {
  let timer;
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error('Native synthetic qualification timed out')), 240000);
    })]);
  } finally { clearTimeout(timer); }
}

function inspect(root) {
  const scripts = path.resolve(__dirname, '..', '..', '..', 'skills', 'sdlc', 'scripts');
  const code = 'import json,sys;sys.path.insert(0,sys.argv[1]);import execution_manager as m;' +
    'print(json.dumps(m.inspect_execution(sys.argv[2],"feature-one")))';
  return JSON.parse(execFileSync('python', ['-I', '-B', '-S', '-c', code, scripts, root],
    { encoding: 'utf8', windowsHide: true, timeout: 15000, maxBuffer: 2 * 1024 * 1024 }));
}

exports.run = async function () {
  const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  assert.ok(root, 'Select only the disposable synthetic host workspace');
  assert.equal(await fs.readFile(path.join(root, '.synthetic-runtime-host'), 'utf8'),
    'offline synthetic provider only\n');
  assert.equal(vscode.env.remoteName, undefined);
  const fixture = JSON.parse(await fs.readFile(path.join(root, 'host-fixture.json'), 'utf8'));
  assert.ok(!fixture.cancelDuringExecute || fixture.execute,
    'The cancellation trial must include an actual exact command');
  const before = inspect(root);
  assert.deepEqual(before.state.attemptIds, []);
  const extension = vscode.extensions.getExtension('sdlc.sdlc-runtime');
  assert.ok(extension);
  assert.equal(extension.isActive, false, 'The package must remain inactive before the explicit command');

  const descriptor = Object.getOwnPropertyDescriptor(vscode.lm, 'selectChatModels');
  assert.ok(descriptor && (descriptor.configurable || descriptor.writable),
    'The external provider discovery seam must be replaceable for an offline trial');
  let selections = 0;
  let requests = 0;
  const expectedDigest = 'sha256:' + crypto.createHash('sha256').update('before\n').digest('hex');
  const responses = [
    { type: 'tool', name: 'read', arguments: { path: 'src/feature.py' } },
    { type: 'tool', name: 'edit', arguments: {
      path: 'src/feature.py', expectedDigest, content: 'after native\n'
    } },
    ...(fixture.execute ? [{ type: 'tool', name: 'execute', arguments: { commandId: 'check' } }] : []),
    { type: 'result', result: fixture.result }
  ];
  const model = {
    id: 'synthetic-native-model', name: 'OFFLINE SYNTHETIC TEST ONLY',
    vendor: 'synthetic-offline', family: 'native-test', version: '1',
    async sendRequest(messages, options, cancellation) {
      assert.equal(messages.length, 1);
      assert.deepEqual(options, {});
      assert.equal(cancellation.isCancellationRequested, false);
      assert.ok(requests < responses.length, 'No additional model iteration may be requested');
      const response = responses[requests++];
      if (fixture.execute && response.type === 'result') {
        const prompt = messages[0].content.map(part => part.value || '').join('');
        const context = JSON.parse(prompt.slice(prompt.lastIndexOf('\n') + 1));
        const observed = context.history.find(item => item.request.name === 'execute').output.evidence;
        assert.equal(observed.exitCode, 0);
        response.result.verification[0] = {
          acceptanceCriterion: 'AC-1', command: 'runtime-command:check', result: 'passed',
          revision: observed.commandDigest, summary: 'passed'
        };
      }
      const text = JSON.stringify(response);
      return { text: (async function* () {
        yield text.slice(0, Math.floor(text.length / 2));
        await new Promise(resolve => setImmediate(resolve));
        yield text.slice(Math.floor(text.length / 2));
      })() };
    }
  };
  Object.defineProperty(vscode.lm, 'selectChatModels', {
    ...descriptor,
    value: async selector => {
      assert.deepEqual(selector, {});
      selections++;
      return [model];
    }
  });
  const phase = async value => fs.writeFile(path.join(root, 'host-phase.json'), JSON.stringify({ phase: value }));
  const expectedSelections = fixture.cancelDuringExecute ? 1 : fixture.execute ? 3 : 2;
  try {
    if (fixture.execute && !fixture.cancelDuringExecute) {
      await phase('reject-exact-command-ui');
      await bounded(vscode.commands.executeCommand('sdlc.runtime.run'));
      assert.equal(selections, 1);
      assert.equal(requests, 0, 'Dismissing exact-command consent must not start a provider or process');
      assert.deepEqual(inspect(root).state, before.state);
    }
    if (!fixture.cancelDuringExecute) {
      await phase('reject-native-consent-ui');
      await bounded(vscode.commands.executeCommand('sdlc.runtime.run'));
      assert.equal(extension.isActive, true);
      assert.equal(selections, fixture.execute ? 2 : 1);
      assert.equal(requests, 0, 'Dismissing native consent must not request a model response');
      assert.deepEqual(inspect(root).state, before.state);
    }

    await phase(fixture.cancelDuringExecute ? 'cancel-running-command-ui' : 'native-success-ui');
    const heartbeat = path.join(root, '.synthetic-command-heartbeat');
    await bounded(vscode.commands.executeCommand('sdlc.runtime.run'));
    assert.equal(extension.isActive, true);
    assert.equal(selections, expectedSelections);
    assert.equal(requests, fixture.cancelDuringExecute ? 3 : responses.length);
    assert.equal(await fs.readFile(path.join(root, 'src', 'feature.py'), 'utf8'), 'after native\n');
    const reported = inspect(root);
    let heartbeatDurationMs = null;
    if (fixture.cancelDuringExecute) {
      const observed = await fs.stat(heartbeat);
      assert.ok(observed.birthtimeMs > 0, 'Heartbeat creation must be observable on this host');
      heartbeatDurationMs = observed.mtimeMs - observed.birthtimeMs;
      assert.ok(heartbeatDurationMs >= 0 && heartbeatDurationMs < 5000,
        'UI cancellation must stop the command before its approved ten-second timeout');
      const stopped = await fs.readFile(heartbeat, 'utf8');
      await new Promise(resolve => setTimeout(resolve, 300));
      assert.equal(await fs.readFile(heartbeat, 'utf8'), stopped,
        'The actual command heartbeat must stop after native UI cancellation');
      assert.notEqual(reported.state.tasks.implement.status, 'reported');
    } else {
      assert.equal(reported.state.tasks.implement.status, 'reported');
    }
    assert.equal(reported.state.tasks.implement.acceptance, null);
    assert.deepEqual(reported.state.attemptIds, ['attempt-one']);
    assert.equal(Object.keys(reported.receipts).length, fixture.cancelDuringExecute ? 0 : 1);

    await phase('escape-project-ui');
    await bounded(vscode.commands.executeCommand('sdlc.runtime.run'));
    assert.equal(selections, expectedSelections, 'Project-picker cancellation must not rediscover a model');
    assert.equal(requests, fixture.cancelDuringExecute ? 3 : responses.length);
    const cancelled = inspect(root);
    assert.deepEqual(cancelled.state, reported.state);
    const evidence = {
      host: 'Visual Studio Code', version: vscode.version, platform: process.platform,
      node: process.versions.node, electron: process.versions.electron || null,
      inactiveUntilCommand: true, nativeCommandsAndDialogs: true,
      externalSeam: 'Only model discovery and model response stream are synthetic',
      syntheticModelCalls: requests, syntheticModelSelections: selections, actualProviderCalls: 0,
      actualCliAndFilesystem: true, actualReadAndCasEdit: true,
      receiptStatus: fixture.cancelDuringExecute ? null : 'reported', independentAcceptance: false,
      modalDeclinedStartsNothing: !fixture.cancelDuringExecute,
      exactCommandConsentDeclinedStartsNothing: fixture.execute === true && !fixture.cancelDuringExecute,
      actualContainedCommand: fixture.execute === true,
      nativeInFlightCommandCancellation: fixture.cancelDuringExecute === true,
      stoppedBeforeApprovedCommandTimeout: fixture.cancelDuringExecute === true,
      actualCommandHeartbeatMs: heartbeatDurationMs,
      escapeBeforeDispatchPreservesState: true
    };
    await fs.writeFile(path.join(root, 'host-result.json'), JSON.stringify(evidence, null, 2) + '\n');
    await phase('complete');
  } finally {
    Object.defineProperty(vscode.lm, 'selectChatModels', descriptor);
  }
};
