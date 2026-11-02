const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { performance } = require('node:perf_hooks');
const { spawnSync } = require('node:child_process');
const { createRequire } = require('node:module');
const vm = require('node:vm');
const { run } = require('../driver');
const { createBridge, digest } = require('../bridge');

const ROOT = path.resolve(__dirname, '..', '..', '..');

function driverWithClock(overrides) {
  const filename = path.resolve(__dirname, '..', 'driver.js');
  const module = { exports: {} };
  const originalRequire = createRequire(filename);
  vm.runInNewContext(fs.readFileSync(filename, 'utf8'), {
    module, AbortController, Buffer, setImmediate, setTimeout, clearTimeout,
    require(name) {
      if (name === 'node:perf_hooks' && overrides.now) return { performance: { now: overrides.now } };
      return originalRequire(name);
    },
    ...overrides
  }, { filename });
  return module.exports.run;
}

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

async function until(predicate, milliseconds) {
  const end = performance.now() + milliseconds;
  let matched;
  while (!(matched = predicate()) && performance.now() < end) await new Promise(resolve => setTimeout(resolve, 20));
  assert.ok(matched, 'Expected local runtime boundary was not reached within its test bound');
}

for (const holdWriter of [false, true, 'unresolved']) {
  test(`UI cancellation stops a real execute descendant before command timeout; writer contention ${holdWriter}`,
    { skip: process.platform !== 'win32' }, async t => {
    const context = await fixture(t);
    const interpreter = spawnSync('python', ['-I', '-S', '-c',
      'import pathlib,sys; print(pathlib.Path(sys.executable).resolve())'], { encoding: 'utf8' });
    assert.equal(interpreter.status, 0, interpreter.stderr);
    const heartbeat = path.join(context.project, 'heartbeat');
    const child = `import pathlib,time\np=pathlib.Path(${JSON.stringify(heartbeat)})\nwhile True:\n p.write_text(str(time.time_ns()))\n time.sleep(.02)`;
    const code = `import subprocess,sys,time\nsubprocess.Popen([sys.executable,'-I','-S','-c',${JSON.stringify(child)}])\ntime.sleep(30)`;
    context.envelope = await context.bridge('prepare_execute', {
      executionId: 'feature-one',
      brief: { ...context.envelope.request.brief, allowedActions: ['read', 'search', 'edit', 'execute'] },
      role: 'developer', model: context.envelope.model, limits: context.envelope.limits,
      commands: [{ id: 'check', executable: interpreter.stdout.trim(), argv: ['-I', '-S', '-c', code],
        cwd: context.project, timeoutMs: 10000, maxOutputBytes: 1024 }]
    });
    const controller = new AbortController();
    let stops = 0;
    let busyStops = 0;
    let calls = 0;
    let toolSettled = false;
    const boundaries = [];
    const bridge = async (operation, payload) => {
      if (operation === 'stop') { stops++; boundaries.push(['stop-request', performance.now()]); }
      try { return await context.bridge(operation, payload); }
      catch (error) {
        if (operation === 'stop' && /E_EXECUTION_BUSY/.test(error.message)) busyStops++;
        throw error;
      } finally {
        if (operation === 'tool') { toolSettled = true; boundaries.push(['tool-settled', performance.now()]); }
      }
    };
    const outcome = run({ ...context, bridge, signal: controller.signal, respond: async () => {
      calls++;
      return response({ type: 'tool', name: 'execute', arguments: { commandId: 'check' } });
    } }).then(() => ({ resolved: true }), error => ({ error }));
    const lock = path.join(context.project, '.git', 'sdlc', 'executions.lock');
    let release;
    try {
      await until(() => fs.existsSync(heartbeat), 8000);
      if (holdWriter) {
        await until(() => {
          try { fs.writeFileSync(lock, 'test-owned writer contention', { flag: 'wx' }); return true; }
          catch (error) { if (error.code !== 'EEXIST') throw error; return false; }
        }, 2000);
        if (holdWriter === true) release = setTimeout(() => fs.rmSync(lock, { force: true }), 800);
      }
      const abortedAt = performance.now();
      boundaries.push(['abort', abortedAt]);
      controller.abort();
      await until(() => stops > 0, 1500);
      const result = await outcome;
      assert.ok(result.error, 'UI cancellation must not produce a result');
      assert.ok(performance.now() - abortedAt < 5000,
        `Cancellation must not wait for the ten-second command timeout: ${JSON.stringify(boundaries)}`);
      assert.equal(toolSettled, true, 'Keep the actual helper alive and await its cleanup');
      if (holdWriter) assert.ok(busyStops > 0 && stops > 1, 'Real stop lock contention must be explicitly retried');
      if (holdWriter === 'unresolved') {
        assert.equal(result.error.code, 'E_RUNTIME_STOP_UNCONFIRMED',
          'Exhausted stop persistence must be explicit, not swallowed as successful cleanup');
        fs.rmSync(lock, { force: true });
        await context.bridge('stop', { envelope: context.envelope });
      }
      assert.equal(calls, 1);
      const before = fs.readFileSync(heartbeat, 'utf8');
      await new Promise(resolve => setTimeout(resolve, 200));
      assert.equal(fs.readFileSync(heartbeat, 'utf8'), before, 'Descendant heartbeat must stop');
      assertUnresolved(context);
      await assert.rejects(run({ ...context, respond: async () => assert.fail('Unknown work cannot redispatch') }));
    } finally {
      if (release) clearTimeout(release);
      if (holdWriter) fs.rmSync(lock, { force: true });
      await context.bridge('stop', { envelope: context.envelope }).catch(() => {});
      await outcome;
    }
  });
}

test('a bounded runtime driver is executable', () => {
  assert.equal(typeof run, 'function');
});

test('version-2 real command CLI reports exact observed evidence without automatic acceptance',
  { skip: process.platform !== 'win32' }, async t => {
  const context = await fixture(t);
  const interpreter = spawnSync('python', ['-I', '-S', '-c',
    'import pathlib,sys; print(pathlib.Path(sys.executable).resolve())'], { encoding: 'utf8' });
  assert.equal(interpreter.status, 0, interpreter.stderr);
  context.envelope = await context.bridge('prepare_execute', {
    executionId: 'feature-one',
    brief: { ...context.envelope.request.brief, allowedActions: ['read', 'search', 'edit', 'execute'] },
    role: 'developer', model: context.envelope.model, limits: context.envelope.limits,
    commands: [{ id: 'check', executable: interpreter.stdout.trim(),
      argv: ['-I', '-S', '-c', "print('in-memory-only-command-output')"],
      cwd: context.project, timeoutMs: 2000, maxOutputBytes: 1024 }]
  });
  let calls = 0;
  const output = await run({ ...context, respond: async prompt => {
    calls++;
    assert.match(prompt, /"commandIds":\["check"\]/);
    if (calls === 1) return response({ type: 'tool', name: 'execute', arguments: { commandId: 'check' } });
    const observed = JSON.parse(prompt.slice(prompt.lastIndexOf('\n') + 1)).history[0].output;
    assert.equal(observed.evidence.status, 'passed');
    assert.match(observed.output, /in-memory-only-command-output/);
    context.result.verification[0] = { acceptanceCriterion: 'AC-1', command: 'runtime-command:check',
      result: 'passed', revision: observed.evidence.commandDigest, summary: 'passed' };
    return response({ type: 'result', result: context.result });
  } });
  assert.equal(calls, 2);
  assert.equal(output.acceptance, 'not-assessed');
  assert.equal(status(context.project), 'reported');
  const marker = fs.readFileSync(path.join(context.project, '.git', 'sdlc', 'bounded-runtime.json'), 'utf8');
  assert.equal(marker.includes('in-memory-only-command-output'), false);
  const record = JSON.parse(fs.readFileSync(path.join(context.project, '.git', 'sdlc', 'executions', 'feature-one.json')));
  assert.equal(Object.keys(record.revisions.at(-1).acceptances).length, 0);
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

test('a provider timeout is unknown and never automatically retried', { timeout: 20000 }, async t => {
  const context = await fixture(t, { maxWallMs: 300000 });
  const watchdog = {};
  let expire;
  const timedRun = driverWithClock({
    setTimeout(callback, milliseconds) {
      if (milliseconds !== context.envelope.limits.maxWallMs) return setTimeout(callback, milliseconds);
      expire = callback;
      return watchdog;
    },
    clearTimeout(handle) { if (handle !== watchdog) clearTimeout(handle); }
  });
  let calls = 0;
  await assert.rejects(timedRun({ ...context, respond: async () => {
    calls++;
    assert.equal(typeof expire, 'function');
    expire();
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
  const context = await fixture(t, { maxWallMs: 300000 });
  let now = 0;
  const timedRun = driverWithClock({ now: () => now });
  let calls = 0;
  let chunks = 0;
  await assert.rejects(timedRun({ ...context, respond: async () => {
    calls++;
    return (async function* () {
      for (let i = 0; i < 1024; i++) {
        if (i === 0) {
          now = context.envelope.limits.maxWallMs + 1;
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
