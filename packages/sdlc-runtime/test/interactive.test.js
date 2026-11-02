'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');

async function load(root, run, written) {
  const source = await fs.readFile(path.join(__dirname, 'interactive', 'extension.js'), 'utf8');
  const exported = {};
  const errors = [];
  vm.runInNewContext(source, {
    exports: exported, setImmediate, console: { error: (...args) => errors.push(args) },
    require(name) {
      if (name === 'node:path') return path;
      if (name === 'node:fs/promises') return {
        ...fs,
        async writeFile(...args) {
          await fs.writeFile(...args);
          written?.();
        }
      };
      if (name === 'vscode') return { workspace: { workspaceFolders: [{ uri: { fsPath: root } }] } };
      if (name === '../host') return { run };
      throw new Error('Unexpected qualification dependency');
    }
  }, { filename: 'offline-qualification-extension.js' });
  return { api: exported.activate(), errors };
}

for (const marker of [null, 'not an approved synthetic workspace\n']) {
  test(`offline harness never runs or writes failure metadata without its exact marker: ${marker === null ? 'absent' : 'different'}`,
    { timeout: 5000 }, async t => {
      const root = await fs.mkdtemp(path.join(os.tmpdir(), 'sdlc-host-guard-'));
      t.after(() => fs.rm(root, { recursive: true, force: true }));
      if (marker !== null) await fs.writeFile(path.join(root, '.synthetic-runtime-host'), marker);
      let calls = 0;
      const { api, errors } = await load(root, () => { calls++; });
      await assert.rejects(api.running);
      assert.equal(calls, 0);
      assert.equal(errors.length, 1);
      await assert.rejects(fs.stat(path.join(root, 'host-failure.json')), { code: 'ENOENT' });
    });
}

test('marked synthetic workspace retains explicit failure evidence without invoking a real provider',
  { timeout: 5000 }, async t => {
    const root = await fs.mkdtemp(path.join(os.tmpdir(), 'sdlc-host-failure-'));
    t.after(() => fs.rm(root, { recursive: true, force: true }));
    await fs.writeFile(path.join(root, '.synthetic-runtime-host'), 'offline synthetic provider only\n');
    let written;
    const completion = new Promise(resolve => { written = resolve; });
    const { api, errors } = await load(root, () => { throw new Error('Synthetic test failure'); }, written);
    await assert.rejects(api.running, /Synthetic test failure/);
    await completion;
    assert.equal(errors.length, 1);
    assert.deepEqual(JSON.parse(await fs.readFile(path.join(root, 'host-failure.json'), 'utf8')),
      { message: 'Synthetic test failure', name: 'Error', actualProviderCalls: 0 });
  });
