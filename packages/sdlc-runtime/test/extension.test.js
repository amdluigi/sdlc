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
        assert.equal(name, 'sdlc.runtime.run');
        registered = callback;
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
        commands: { registerCommand(name, handler) { callback = handler; return { dispose() {} }; } }
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
