'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const Module = require('node:module');
const test = require('node:test');

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
