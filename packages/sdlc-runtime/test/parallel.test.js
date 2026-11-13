'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const Module = require('node:module');
const { spawnSync } = require('node:child_process');
const test = require('node:test');

function activate(vscode) {
  const callbacks = new Map();
  vscode.commands = { registerCommand(name, callback) {
    callbacks.set(name, callback);
    return { dispose() {} };
  } };
  const original = Module._load;
  try {
    Module._load = function (name, ...args) {
      return name === 'vscode' ? vscode : original.call(this, name, ...args);
    };
    delete require.cache[require.resolve('../extension')];
    require('../extension').activate({ subscriptions: [] });
  } finally { Module._load = original; }
  assert.equal(typeof callbacks.get('sdlc.runtime.runParallelBatches'), 'function',
    'AC-18/AC-24: explicitly isolated parallel batches are not provided');
  return callbacks;
}

async function workspace(t) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'sdlc-isolated-pair-'));
  t.after(() => fs.rm(root, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 }));
  const folders = [];
  for (const name of ['one', 'two']) {
    const directory = path.join(root, name);
    await fs.mkdir(directory);
    folders.push({ name, uri: { scheme: 'file', fsPath: directory } });
  }
  const errors = [];
  const confirmations = [];
  const vscode = {
    workspace: { isTrusted: true, workspaceFolders: folders },
    env: {},
    window: {
      async showQuickPick(items, options) {
        assert.equal(options.canPickMany, true);
        assert.match(options.title, /two.*independent/i);
        return items;
      },
      async showWarningMessage(message, options) {
        confirmations.push({ message, detail: options.detail });
        return undefined;
      },
      async showErrorMessage(message) { errors.push(message); },
      async showOpenDialog() { assert.fail('Declined group consent cannot open batch inputs'); },
      async withProgress() { assert.fail('Declined group consent cannot start work'); }
    }
  };
  return { root, folders, vscode, errors, confirmations };
}

test('isolated parallel command requires explicit root consent and declining starts nothing', async t => {
  const fixture = await workspace(t);
  const callbacks = activate(fixture.vscode);
  await callbacks.get('sdlc.runtime.runParallelBatches')();
  assert.deepEqual(fixture.errors, []);
  assert.equal(fixture.confirmations.length, 1);
  for (const folder of fixture.folders) {
    assert.ok(fixture.confirmations[0].detail.includes(await fs.realpath(folder.uri.fsPath)));
    await assert.rejects(fs.stat(path.join(folder.uri.fsPath, '.git')), { code: 'ENOENT' });
  }
});

for (const kind of ['same', 'alias', 'nested', 'one', 'three', 'untrusted', 'remote']) {
  test(`parallel selection rejects ${kind} before consent or manager access`, async t => {
    const fixture = await workspace(t);
    if (kind === 'same') fixture.folders[1].uri.fsPath = fixture.folders[0].uri.fsPath;
    if (kind === 'alias') {
      const alias = path.join(fixture.root, 'alias');
      await fs.symlink(fixture.folders[0].uri.fsPath, alias, 'junction');
      fixture.folders[1].uri.fsPath = alias;
    }
    if (kind === 'nested') fixture.folders[1].uri.fsPath = fixture.root;
    if (kind === 'one') fixture.folders.pop();
    if (kind === 'three') fixture.folders.push(fixture.folders[0]);
    if (kind === 'untrusted') fixture.vscode.workspace.isTrusted = false;
    if (kind === 'remote') fixture.vscode.env.remoteName = 'synthetic-remote';
    const callbacks = activate(fixture.vscode);
    await callbacks.get('sdlc.runtime.runParallelBatches')();
    assert.equal(fixture.errors.length, 1);
    assert.equal(fixture.confirmations.length, 0);
  });
}

test('parallel command holds the existing busy barrier throughout group consent', async t => {
  const fixture = await workspace(t);
  let release;
  let entered;
  const ready = new Promise(resolve => { entered = resolve; });
  fixture.vscode.window.showWarningMessage = async () => {
    entered();
    return new Promise(resolve => { release = resolve; });
  };
  const callbacks = activate(fixture.vscode);
  const running = callbacks.get('sdlc.runtime.runParallelBatches')();
  await ready;
  await callbacks.get('sdlc.runtime.runBatch')();
  assert.equal(fixture.errors.length, 1);
  release(undefined);
  await running;
  fixture.vscode.window.showWarningMessage = async () => undefined;
  await callbacks.get('sdlc.runtime.runParallelBatches')();
  assert.equal(fixture.errors.length, 1, 'Busy state must be released after settlement');
});

async function initialize(folders) {
  const script = [
    'import json,pathlib,sys',
    'from tests.test_bounded_runtime import fixture',
    'from tests.test_execution_orchestration import batch',
    'from tests.test_execution_contracts import result',
    'from tests.test_execution_controls import batch_controls_policy',
    'from execution_controls import configure_controls,approve_controls,inspect_controls',
    'from execution_manager import inspect_execution',
    'for folder in sys.argv[1:]:',
    ' p,b=fixture(folder)',
    ' configure_controls(folder,batch_controls_policy())',
    ' e=inspect_execution(folder,"feature-one");c=inspect_controls(folder)',
    ' approve_controls(folder,"feature-one",e["planDigest"],e["policyDigest"],c["controlsDigest"])',
    ' value=batch(p);value["tasks"][0]["attempts"]=value["tasks"][0]["attempts"][:1]',
    ' value["tasks"][0]["attempts"][0]["brief"]=b',
    ' response=result(p);response["verification"][0].update(result="unavailable",command=None,revision=None,summary="unavailable")',
    ' pathlib.Path(folder,"parallel-fixture.json").write_text(json.dumps({"batch":value,"result":response}),encoding="utf-8")'
  ].join('\n');
  const setup = spawnSync('python', ['-B', '-c', script, ...folders.map(folder => folder.uri.fsPath)], {
    cwd: path.resolve(__dirname, '..', '..', '..'), encoding: 'utf8',
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' }
  });
  assert.equal(setup.status, 0, setup.stderr);
  for (const folder of folders) {
    const data = JSON.parse(await fs.readFile(path.join(folder.uri.fsPath, 'parallel-fixture.json'), 'utf8'));
    await fs.writeFile(path.join(folder.uri.fsPath, 'batch.json'), JSON.stringify(data.batch));
    folder.result = data.result;
  }
}

function cancellationSource() {
  const listeners = new Set();
  const token = { isCancellationRequested: false, onCancellationRequested(callback) {
    listeners.add(callback); return { dispose() { listeners.delete(callback); } };
  } };
  return { token, cancel() {
    token.isCancellationRequested = true;
    for (const callback of listeners) callback();
  }, dispose() {} };
}

for (const trial of [0, 1, 2, 'second-declined', 'already-cancelled', 'model-error', 'cancel-active']) {
  test(`two actual managers retain independent unaccepted receipts under parallel load ${trial}`, async t => {
    const fixture = await workspace(t);
    await initialize(fixture.folders);
    let files = 0;
    let active = 0;
    let maximum = 0;
    let calls = 0;
    let release;
    const both = new Promise(resolve => { release = resolve; });
    const progressTokens = [];
    const result = fixture.folders[0].result;
    fixture.vscode.version = 'synthetic-host';
    fixture.vscode.ProgressLocation = { Notification: 1 };
    fixture.vscode.LanguageModelChatMessage = { User: content => ({ content }) };
    fixture.vscode.CancellationTokenSource = function () { return cancellationSource(); };
    fixture.vscode.lm = { async selectChatModels() { return [{
      id: 'model-one', vendor: 'synthetic', family: 'test', version: '1',
      async sendRequest(messages, options, cancellation) {
        assert.notEqual(trial, 'already-cancelled', 'Group cancellation must prevent every adapter invocation');
        calls++;
        const ordinal = calls;
        active++;
        let finished = false;
        const finish = () => { if (!finished) { finished = true; active--; } };
        cancellation.onCancellationRequested(finish);
        maximum = Math.max(maximum, active);
        if (active === 2) {
          release();
          if (trial === 'cancel-active') progressTokens[0].cancel();
        }
        await both;
        if (trial === 'model-error' && ordinal === 1) {
          finish();
          throw new Error('Synthetic adapter failure');
        }
        if (cancellation.isCancellationRequested) finish();
        return { text: (async function* () {
          try { yield JSON.stringify({ type: 'result', result }); }
          finally { finish(); }
        })() };
      }
    }]; } };
    fixture.vscode.window.showOpenDialog = async () => [{
      scheme: 'file', fsPath: path.join(fixture.folders[files++].uri.fsPath, 'batch.json')
    }];
    let confirmations = 0;
    fixture.vscode.window.showWarningMessage = async (message, options, action) => {
      confirmations++;
      return trial === 'second-declined' && confirmations === 3 ? undefined : action;
    };
    fixture.vscode.window.showInformationMessage = async () => {};
    fixture.vscode.window.withProgress = async (options, callback) => {
      const source = cancellationSource();
      progressTokens.push(source);
      if (trial === 'already-cancelled' && progressTokens.length === 1) source.cancel();
      return callback({}, source.token);
    };
    const callbacks = activate(fixture.vscode);
    const started = performance.now();
    const heap = process.memoryUsage().heapUsed;
    const cpu = process.cpuUsage();
    await callbacks.get('sdlc.runtime.runParallelBatches')();
    const interrupted = trial === 'model-error' || trial === 'cancel-active';
    assert.equal(fixture.errors.length, interrupted ? 1 : 0, fixture.errors.join('\n'));
    if (interrupted) assert.match(fixture.errors[0], /unknown work must not be redispatched/);
    const notStarted = trial === 'already-cancelled' || trial === 'second-declined';
    assert.equal(calls, notStarted ? 0 : 2);
    assert.equal(maximum, notStarted ? 0 : 2,
      'The independently authorized adapters must actually overlap unless cancelled');
    assert.equal(active, 0);
    for (const folder of fixture.folders) {
      const record = JSON.parse(await fs.readFile(path.join(
        folder.uri.fsPath, '.git', 'sdlc', 'executions', 'feature-one.json'
      ), 'utf8'));
      const events = record.revisions.at(-1).events;
      assert.equal(events.filter(item => item.type === 'TASK_STARTED').length,
        notStarted ? 0 : 1);
      if (typeof trial === 'number') {
        assert.equal(events.filter(item => item.type === 'TASK_RESULT_RECEIVED').length, 1);
      }
      if (trial === 'cancel-active') {
        const runtime = JSON.parse(await fs.readFile(path.join(
          folder.uri.fsPath, '.git', 'sdlc', 'bounded-runtime.json'
        ), 'utf8'));
        assert.equal(runtime.status, 'unknown');
        assert.equal(runtime.iterations, 1, 'Already observed adapter invocation remains attributable');
        assert.equal(events.some(item => item.type === 'TASK_CANCELLED'), false,
          'Local cancellation cannot certify a remote stop');
      }
      assert.equal(events.some(item => item.type === 'TASK_COMPLETED' || item.type === 'VALIDATION_PASSED'), false);
    }
    if (trial === 'second-declined') {
      for (let index = 0; index < fixture.folders.length; index++) {
        const controls = JSON.parse(await fs.readFile(path.join(
          fixture.folders[index].uri.fsPath, '.git', 'sdlc', 'execution-controls.json'
        ), 'utf8'));
        assert.equal(Object.keys(controls.batchApprovals).length, index === 0 ? 1 : 0,
          'Keep the first explicit approval but never infer consent for the declined project');
      }
    }
    t.diagnostic(JSON.stringify({ trial, maximumConcurrentAdapters: maximum,
      syntheticCalls: calls, elapsedMs: Math.round(performance.now() - started),
      nodeHeapDeltaBytes: process.memoryUsage().heapUsed - heap, nodeCpuMicros: process.cpuUsage(cpu) }));
  });
}
