const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { performance } = require('node:perf_hooks');
const { spawnSync } = require('node:child_process');
const { run } = require('../driver');
const { createBridge, digest } = require('../bridge');

const ROOT = path.resolve(__dirname, '..', '..', '..');

async function fixture(t, limits = {}) {
  const project = fs.mkdtempSync(path.join(os.tmpdir(), 'sdlc-runtime-'));
  t.after(() => fs.rmSync(project, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 }));
  const setup = spawnSync('python', ['-B', '-c', [
    'import json,sys',
    'from tests.test_bounded_runtime import fixture,LIMITS,MODEL',
    'from tests.test_execution_contracts import result',
    'from bounded_runtime import prepare',
    'p,b=fixture(sys.argv[1])',
    'r=result(p)',
    'r["verification"][0]["result"]="unavailable"',
    'print(json.dumps({"envelope":prepare(sys.argv[1],"feature-one",b,"developer",MODEL,{**LIMITS,**json.loads(sys.argv[2])}),"result":r}))'
  ].join(';'), project, JSON.stringify(limits)], { cwd: ROOT, encoding: 'utf8' });
  assert.equal(setup.status, 0, setup.stderr);
  return { ...JSON.parse(setup.stdout), project, bridge: createBridge(project) };
}

function response(value) {
  return (async function* () { yield JSON.stringify(value); })();
}

function status(project) {
  return JSON.parse(fs.readFileSync(path.join(project, '.git', 'sdlc', 'bounded-runtime.json'), 'utf8')).status;
}

test('a bounded runtime driver is executable', () => {
  assert.equal(typeof run, 'function');
});

test('real CLI tools edit exact owned files and manager receives an unaccepted receipt', async t => {
  const context = await fixture(t);
  let count = 0;
  const output = await run({ ...context, respond: async prompt => {
    count++;
    if (count === 1) return response({ type: 'tool', name: 'read', arguments: { path: 'src/feature.py' } });
    if (count === 2) {
      const read = JSON.parse(prompt.slice(prompt.lastIndexOf('\n') + 1)).history[0].output;
      return response({ type: 'tool', name: 'edit', arguments: {
        path: 'src/feature.py', expectedDigest: read.digest, content: 'synthetic change\n'
      } });
    }
    return response({ type: 'result', result: context.result });
  } });
  assert.equal(output.acceptance, 'not-assessed');
  assert.equal(count, 3);
  assert.equal(fs.readFileSync(path.join(context.project, 'src', 'feature.py'), 'utf8'), 'synthetic change\n');
  assert.equal(status(context.project), 'reported');
  const record = JSON.parse(fs.readFileSync(path.join(context.project, '.git', 'sdlc', 'executions', 'feature-one.json')));
  assert.equal(Object.keys(record.revisions.at(-1).acceptances).length, 0);
  const lease = fs.readFileSync(path.join(context.project, '.git', 'sdlc', 'bounded-runtime.json'), 'utf8');
  assert.equal(lease.includes('synthetic change'), false);
  await assert.rejects(run({ ...context, respond: async () => { throw new Error('must not dispatch'); } }));
  assert.equal(count, 3);
});

for (const scenario of ['provider-failure', 'invalid-json', 'execute', 'oversize', 'iteration-exhaustion', 'source-drift']) {
  test(`${scenario} leaves unknown native work without a success fallback or retry`, async t => {
    const context = await fixture(t, scenario === 'iteration-exhaustion' ? { maxIterations: 1 } : {});
    let calls = 0;
    await assert.rejects(run({ ...context, respond: async () => {
      calls++;
      if (scenario === 'provider-failure') throw new Error('external provider failed');
      if (scenario === 'invalid-json') return (async function* () { yield 'not JSON'; })();
      if (scenario === 'oversize') return (async function* () { yield 'x'.repeat(32769); })();
      if (scenario === 'execute') return response({ type: 'tool', name: 'execute', arguments: { command: 'echo nope' } });
      if (scenario === 'source-drift') {
        fs.appendFileSync(path.join(context.project, 'docs', 'plans', 'feature.md'), 'changed');
        return response({ type: 'result', result: context.result });
      }
      return response({ type: 'tool', name: 'read', arguments: { path: 'guide.md' } });
    } }));
    assert.equal(calls, 1);
    assert.equal(status(context.project), 'unknown');
    const record = JSON.parse(fs.readFileSync(path.join(context.project, '.git', 'sdlc', 'executions', 'feature-one.json')));
    assert.equal(Object.keys(record.revisions.at(-1).receipts).length, 0);
  });
}

test('cancellation of a nonresponsive provider does not wait, retry, receive or confirm remote stop', async t => {
  const context = await fixture(t);
  const controller = new AbortController();
  let calls = 0;
  await assert.rejects(run({ ...context, signal: controller.signal, respond: async () => {
    calls++;
    controller.abort();
    return new Promise(() => {});
  } }), /remote work is unconfirmed/);
  assert.equal(calls, 1);
  assert.equal(status(context.project), 'unknown');
});

test('Python and Node digest binding agree including Unicode metadata', async t => {
  const context = await fixture(t);
  context.envelope.model.version = 'é-😀';
  await context.bridge('start', { envelope: context.envelope,
    approvedRuntimeDigest: digest(context.envelope),
    approvedRequestDigest: digest(context.envelope.request) });
  await context.bridge('stop', { envelope: context.envelope });
  assert.equal(status(context.project), 'unknown');
});

test('a provider timeout is unknown and never automatically retried', async t => {
  const context = await fixture(t, { maxWallMs: 5000 });
  let calls = 0;
  await assert.rejects(run({ ...context, respond: async () => {
    calls++;
    return new Promise(() => {});
  } }), /remote work is unconfirmed/);
  assert.equal(calls, 1);
  assert.equal(status(context.project), 'unknown');
});

test('cancellation before dispatch starts no attempt or provider call', async t => {
  const context = await fixture(t);
  const controller = new AbortController();
  controller.abort();
  let calls = 0;
  await assert.rejects(run({ ...context, signal: controller.signal, respond: async () => {
    calls++;
    throw new Error('must not dispatch');
  } }));
  assert.equal(calls, 0);
  assert.equal(fs.existsSync(path.join(context.project, '.git', 'sdlc', 'bounded-runtime.json')), false);
});

test('fixture allocator uses the standard temporary directory', async t => {
  const context = await fixture(t);
  assert.equal(path.dirname(context.project), os.tmpdir());
});

function assertUnresolved(context) {
  assert.equal(status(context.project), 'unknown');
  const record = JSON.parse(fs.readFileSync(path.join(context.project, '.git', 'sdlc', 'executions', 'feature-one.json')));
  assert.equal(Object.keys(record.revisions.at(-1).receipts).length, 0);
}

test('immediately resolving empty chunks have a bounded no-progress allowance', async t => {
  const context = await fixture(t);
  let calls = 0;
  let chunks = 0;
  await assert.rejects(run({ ...context, respond: async () => {
    calls++;
    return (async function* () {
      for (let i = 0; i < 1024; i++) { chunks++; yield ''; }
    })();
  } }));
  assert.equal(calls, 1);
  assert.ok(chunks <= 128, `consumed ${chunks} no-progress chunks`);
  assertUnresolved(context);
});

test('immediate nonempty chunks yield to event-loop cancellation without retry or receipt', async t => {
  const context = await fixture(t);
  const controller = new AbortController();
  let calls = 0;
  let chunks = 0;
  await assert.rejects(run({ ...context, signal: controller.signal, respond: async () => {
    calls++;
    setImmediate(() => controller.abort());
    return (async function* () {
      for (let i = 0; i < 16384; i++) { chunks++; yield 'x'; }
    })();
  } }));
  assert.equal(calls, 1);
  assert.ok(chunks < 128, `stream starved cancellation for ${chunks} chunks`);
  assertUnresolved(context);
});

test('each immediate stream iteration checks its monotonic deadline before consuming another chunk', async t => {
  const context = await fixture(t, { maxWallMs: 3000 });
  let calls = 0;
  let chunks = 0;
  await assert.rejects(run({ ...context, respond: async () => {
    calls++;
    return (async function* () {
      for (let i = 0; i < 1024; i++) {
        if (i === 0) {
          const until = performance.now() + 3500;
          while (performance.now() < until) { /* Synchronous work at the external stream seam. */ }
        }
        chunks++;
        yield '';
      }
    })();
  } }));
  assert.equal(calls, 1);
  assert.equal(chunks, 1);
  assertUnresolved(context);
});
