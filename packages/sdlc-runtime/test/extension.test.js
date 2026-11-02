'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const Module = require('node:module');
const test = require('node:test');
const { spawnSync } = require('node:child_process');

test('empty native model inventory reports a blocker before model consent or dispatch', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'sdlc-runtime-ui-'));
  try {
    const file = path.join(root, 'brief.json');
    await fs.writeFile(file, JSON.stringify({ binding: { executionId: 'example' } }));
    let registered;
    let pickers = 0;
    const errors = [];
    const vscode = {
      workspace: { isTrusted: true, workspaceFolders: [{ name: 'synthetic', uri: { scheme: 'file', fsPath: root } }] },
      env: {},
      window: {
        async showQuickPick(items) { pickers++; return items[0]; },
        async showOpenDialog() { return [{ scheme: 'file', fsPath: file }]; },
        async showErrorMessage(message) { errors.push(message); },
        async showWarningMessage() { assert.fail('No model is available to authorize'); },
        async withProgress() { assert.fail('No worker may start without a model'); }
      },
      lm: { async selectChatModels() { return []; } },
      commands: { registerCommand(name, callback) {
        if (name === 'sdlc.runtime.run') registered = callback;
        else assert.equal(name, 'sdlc.runtime.runBatch');
        return { dispose() {} };
      } }
    };
    const original = Module._load;
    let extension;
    try {
      Module._load = function (name, ...args) {
        return name === 'vscode' ? vscode : original.call(this, name, ...args);
      };
      delete require.cache[require.resolve('../extension')];
      extension = require('../extension');
    } finally { Module._load = original; }
    extension.activate({ subscriptions: [] });
    await registered();
    assert.equal(pickers, 2, 'Never present an empty model picker as a usable execution path');
    assert.equal(errors.length, 1);
    assert.match(errors[0], /no.*model.*available/i);
    assert.equal(await fs.stat(path.join(root, '.git')).then(() => true, error => {
      if (error.code === 'ENOENT') return false;
      throw error;
    }), false);
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});

test('batch consent binds the previewed exact digest and declining it writes no batch approval', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'sdlc-runtime-batch-ui-'));
  try {
    const setup = spawnSync('python', ['-B', '-c', [
      'import json,sys',
      'from tests.test_bounded_runtime import fixture',
      'from tests.test_execution_orchestration import batch',
      'from tests.test_execution_controls import batch_controls_policy',
      'from execution_controls import configure_controls,approve_controls,inspect_controls',
      'from execution_manager import inspect_execution',
      'p,_=fixture(sys.argv[1])',
      'configure_controls(sys.argv[1],batch_controls_policy())',
      'e=inspect_execution(sys.argv[1],"feature-one")',
      'c=inspect_controls(sys.argv[1])',
      'approve_controls(sys.argv[1],"feature-one",e["planDigest"],e["policyDigest"],c["controlsDigest"])',
      'print(json.dumps(batch(p)))'
    ].join(';'), root], { cwd: path.resolve(__dirname, '..', '..', '..'), encoding: 'utf8' });
    assert.equal(setup.status, 0, setup.stderr);
    const batch = JSON.parse(setup.stdout);
    const file = path.join(root, 'batch.json');
    await fs.writeFile(file, JSON.stringify(batch));
    let callback;
    let progressCalls = 0;
    const confirmations = [];
    const errors = [];
    const infos = [];
    const vscode = {
      workspace: { isTrusted: true, workspaceFolders: [{ name: 'synthetic', uri: { scheme: 'file', fsPath: root } }] },
      env: { appName: 'Visual Studio Code Insiders' },
      version: '1.145.0-insider',
      window: {
        async showQuickPick(items) { return items[0]; },
        async showOpenDialog() { return [{ scheme: 'file', fsPath: file }]; },
        async showErrorMessage(message) { errors.push(message); },
        async showInformationMessage(message) { infos.push(message); },
        async showWarningMessage(message, options) {
          confirmations.push({ message, detail: options.detail });
          assert.equal(message, 'Authorize this exact finite local batch?');
          assert.match(options.detail, /1\.145\.0-insider/);
          assert.match(options.detail, /review-batch/);
          assert.match(options.detail, /attempt-one.*model-one.*brief sha256:/);
          assert.match(options.detail, /monetary spend cap.*unavailable/i);
          assert.doesNotMatch(options.detail, /Run the acceptance test/);
          return undefined;
        },
        async withProgress() { progressCalls++; assert.fail('Declined consent cannot dispatch'); }
      },
      lm: { async selectChatModels() { return ['model-one', 'model-two'].map(id => ({
        name: id, id, vendor: 'synthetic', family: 'test', version: '1'
      })); } },
      commands: { registerCommand(name, handler) {
        if (name === 'sdlc.runtime.runBatch') callback = handler;
        return { dispose() {} };
      } }
    };
    const original = Module._load;
    let extension;
    try {
      Module._load = function (name, ...args) {
        return name === 'vscode' ? vscode : original.call(this, name, ...args);
      };
      delete require.cache[require.resolve('../extension')];
      extension = require('../extension');
    } finally { Module._load = original; }
    extension.activate({ subscriptions: [] });
    assert.equal(typeof callback, 'function');
    await callback();
    assert.equal(confirmations.length, 1);
    assert.equal(progressCalls, 0);
    assert.deepEqual(errors, []);
    assert.deepEqual(infos, []);
    const controls = JSON.parse(await fs.readFile(
      path.join(root, '.git', 'sdlc', 'execution-controls.json'), 'utf8'
    ));
    assert.deepEqual(controls.batchApprovals, {});
    assert.equal(await fs.stat(path.join(root, '.git', 'sdlc', 'bounded-runtime.json')).then(
      () => true, error => { if (error.code === 'ENOENT') return false; throw error; }
    ), false);
  } finally { await fs.rm(root, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 }); }
});

for (const declined of ['commands', 'runtime']) {
  test(`execute selection requires separate exact-command consent; declining ${declined} starts nothing`,
    { skip: declined === 'runtime' && process.platform !== 'win32' }, async () => {
    const root = await fs.mkdtemp(path.join(os.tmpdir(), 'sdlc-runtime-execute-ui-'));
    try {
      const setup = spawnSync('python', ['-B', '-c', [
        'import json,pathlib,sys',
        'from tests.test_bounded_runtime import fixture',
        'p,b=fixture(sys.argv[1])',
        'b["allowedActions"].append("execute")',
        'print(json.dumps({"brief":b,"executable":str(pathlib.Path(sys.executable).resolve())}))'
      ].join(';'), root], { cwd: path.resolve(__dirname, '..', '..', '..'), encoding: 'utf8' });
      assert.equal(setup.status, 0, setup.stderr);
      const data = JSON.parse(setup.stdout);
      const briefFile = path.join(root, 'brief.json');
      const commandsFile = path.join(root, 'commands.json');
      await fs.writeFile(briefFile, JSON.stringify(data.brief));
      const commands = [{ id: 'check', executable: data.executable,
        argv: ['-I', '-S', '-c', 'pass'], cwd: root, timeoutMs: 1000, maxOutputBytes: 1024 }];
      await fs.writeFile(commandsFile, JSON.stringify(commands));
      let callback;
      let files = 0;
      const confirmations = [];
      const errors = [];
      const vscode = {
        workspace: { isTrusted: true, workspaceFolders: [{ name: 'synthetic', uri: { scheme: 'file', fsPath: root } }] },
        env: {},
        window: {
          async showQuickPick(items) { return items[0]; },
          async showOpenDialog() { return [{ scheme: 'file', fsPath: files++ ? commandsFile : briefFile }]; },
          async showErrorMessage(message) { errors.push(message); },
          async showWarningMessage(message, options) {
            confirmations.push({ message, detail: options.detail });
            if (confirmations.length === 1) {
              assert.match(options.detail, /Each executable, argument, cwd, timeout and output bound/);
              assert.match(options.detail, /"timeoutMs": 1000/);
              return declined === 'commands' ? undefined : 'Authorize exact commands';
            }
            assert.match(options.detail, /Exact version-2 commands and executable digests/);
            assert.match(options.detail, /sha256:/);
            return undefined;
          },
          async withProgress() { assert.fail('Declined consent must not dispatch'); }
        },
        lm: { async selectChatModels() { return [{ name: 'synthetic', id: 'synthetic-model',
          vendor: 'synthetic', family: 'test', version: '1' }]; } },
        commands: { registerCommand(name, handler) {
          if (name === 'sdlc.runtime.run') callback = handler;
          return { dispose() {} };
        } }
      };
      const original = Module._load;
      let extension;
      try {
        Module._load = function (name, ...args) {
          return name === 'vscode' ? vscode : original.call(this, name, ...args);
        };
        delete require.cache[require.resolve('../extension')];
        extension = require('../extension');
      } finally { Module._load = original; }
      extension.activate({ subscriptions: [] });
      await callback();
      assert.deepEqual(errors, []);
      assert.equal(files, 2);
      assert.equal(confirmations.length, declined === 'commands' ? 1 : 2);
      const record = JSON.parse(await fs.readFile(path.join(root, '.git', 'sdlc', 'executions', 'feature-one.json'), 'utf8'));
      assert.equal(record.revisions.at(-1).events.some(item => item.type === 'TASK_STARTED'), false);
      await assert.rejects(fs.stat(path.join(root, '.git', 'sdlc', 'bounded-runtime.json')), { code: 'ENOENT' });
    } finally { await fs.rm(root, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 }); }
  });
}
