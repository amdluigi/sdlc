const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { performance } = require('node:perf_hooks');
const { spawnSync } = require('node:child_process');
const { createRequire } = require('node:module');
const vm = require('node:vm');
const { run, buildPrompt } = require('../driver');
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

async function fixture(t, limits = {}, withContext = false) {
  const project = fs.mkdtempSync(path.join(os.tmpdir(), 'sdlc-runtime-'));
  t.after(() => fs.rmSync(project, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 }));
  const setup = spawnSync('python', ['-B', '-c', [
    'import json,sys',
    'from tests.test_bounded_runtime import fixture,LIMITS,MODEL',
    'from tests.test_execution_contracts import result',
    'from bounded_runtime import prepare',
    'import execution_manager as manager',
    'p,b=fixture(sys.argv[1])',
    'if sys.argv[3] == "1":',
    ' current=manager.inspect_execution(sys.argv[1],"feature-one")',
    ' manager.update_context(sys.argv[1],"feature-one","shared",None,"Shared runtime context.",current["planDigest"],current["context"]["revision"])',
    ' current=manager.inspect_execution(sys.argv[1],"feature-one")',
    ' manager.update_context(sys.argv[1],"feature-one","agent","developer","Developer specialist context.",current["planDigest"],current["context"]["revision"])',
    ' current=manager.inspect_execution(sys.argv[1],"feature-one")',
    ' manager.update_context(sys.argv[1],"feature-one","agent","architecture","Unselected specialist context.",current["planDigest"],current["context"]["revision"])',
    'r=result(p)',
    'r["verification"][0]["result"]="unavailable"',
    'print(json.dumps({"envelope":prepare(sys.argv[1],"feature-one",b,"developer",MODEL,{**LIMITS,**json.loads(sys.argv[2])}),"result":r}))'
  ].join('\n'), project, JSON.stringify(limits), withContext ? '1' : '0'], { cwd: ROOT, encoding: 'utf8' });
  assert.equal(setup.status, 0, setup.stderr);
  return { ...JSON.parse(setup.stdout), project, bridge: createBridge(project) };
}

function response(value) {
  return (async function* () { yield JSON.stringify(value); })();
}

function promptHistory(prompt) {
  const marker = '\n## history\n';
  const content = prompt.slice(prompt.indexOf(marker) + marker.length);
  return content === 'No prior tool interactions.' ? [] : JSON.parse(content);
}

function promptEnvelope(overrides = {}) {
  const request = {
    role: 'developer',
    profileDigest: `sha256:${'a'.repeat(64)}`,
    policyDigest: `sha256:${'b'.repeat(64)}`,
    outcome: 'Implement the approved behavior.',
    host: { allowedActions: ['read', 'search', 'edit'] },
    brief: {
      schemaVersion: 1, taskId: 'implement', attemptId: 'attempt-one',
      allowedActions: ['read', 'search', 'edit'], ownership: ['src/feature.js'],
      guidance: ['docs/guide.md'], acceptanceCriteria: ['AC-1'],
      verification: 'Run the focused test.'
    },
    context: {
      schemaVersion: 1, revision: 3, digest: `sha256:${'c'.repeat(64)}`,
      shared: { content: 'Shared context.', digest: `sha256:${'d'.repeat(64)}` },
      agents: {
        developer: { content: 'Developer context.', digest: `sha256:${'e'.repeat(64)}` },
        architecture: { content: 'Unselected architecture context.', digest: `sha256:${'f'.repeat(64)}` }
      }
    }
  };
  return {
    schemaVersion: 1,
    request,
    roleInstructions: 'Follow the selected developer role.',
    promptContext: {
      role: request.role, profileDigest: request.profileDigest,
      contextRevision: request.context.revision, contextDigest: request.context.digest,
      shared: request.context.shared, specialist: request.context.agents.developer
    },
    limits: { maxInputBytes: 32768 },
    ...overrides
  };
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
        if (operation === 'stop') {
          boundaries.push(['stop-error', performance.now(), error.code || error.message]);
          if (/E_EXECUTION_BUSY/.test(error.message)) busyStops++;
        }
        throw error;
      } finally {
        if (operation === 'stop') boundaries.push(['stop-settled', performance.now()]);
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

test('prompt builder includes validated role, selected context, requirements and permitted tools in fixed order', () => {
  const envelope = promptEnvelope();
  const first = buildPrompt(envelope);
  const second = buildPrompt(envelope);
  assert.deepEqual(first, second, 'identical validated input must produce byte-identical prompt output');
  const ids = first.components.map(component => component.id);
  assert.deepEqual(ids, [
    'executionProtocol', 'taskBrief', 'selectedRole', 'sharedContext', 'specialistContext',
    'requirements', 'securityConstraints', 'permittedTools', 'history'
  ]);
  const text = first.prompt;
  for (const required of [
    'developer', envelope.request.profileDigest, envelope.roleInstructions,
    'Shared context.', 'Developer context.', 'AC-1', 'Run the focused test.',
    'src/feature.js', 'docs/guide.md', 'read', 'search', 'edit'
  ]) assert.ok(text.includes(required), `prompt must include ${required}`);
  assert.equal(text.includes('Unselected architecture context.'), false);
  assert.equal(first.promptBytes, Buffer.byteLength(first.prompt, 'utf8'));
  assert.equal(first.components.reduce((total, component) => total + component.bytes, 0), first.promptBytes);
  for (const component of first.components) {
    assert.equal(component.bytes, Buffer.byteLength(component.text, 'utf8'));
  }
});

test('history compacts only consecutive exact duplicate observations and preserves occurrence counts', () => {
  const read = { request: { type: 'tool', name: 'read', arguments: { path: 'src/feature.js' } },
    output: { path: 'src/feature.js', digest: 'digest-one', content: 'before' } };
  const changedRead = { request: read.request, output: { ...read.output, digest: 'digest-two', content: 'after' } };
  const search = { request: { type: 'tool', name: 'search', arguments: {
    path: 'src/feature.js', query: 'feature'
  } }, output: { matches: ['src/feature.js'] } };
  const edit = { request: { type: 'tool', name: 'edit', arguments: {
    path: 'src/feature.js', expectedDigest: 'digest-two', content: 'replacement source'
  } }, output: { digest: `sha256:${'3'.repeat(64)}` } };
  const built = buildPrompt(promptEnvelope(), [read, read, changedRead, search, read, edit, edit]);
  const history = JSON.parse(built.components.find(component => component.id === 'history').content);
  assert.deepEqual(history, [
    { observation: read, occurrenceCount: 2 },
    changedRead,
    search,
    read,
    { artifactReference: {
      type: 'edited-file', path: 'src/feature.js', expectedDigest: 'digest-two',
      digest: `sha256:${'3'.repeat(64)}`
    } },
    { artifactReference: {
      type: 'edited-file', path: 'src/feature.js', expectedDigest: 'digest-two',
      digest: `sha256:${'3'.repeat(64)}`
    } }]);
  assert.equal(JSON.stringify(history).includes('replacement source'), false,
    'validated edits should be referenced by path and digest, not repeated as file content');
});

test('prompt limits fail visibly without truncating required components', () => {
  const envelope = promptEnvelope({ limits: { maxInputBytes: 512 } });
  assert.throws(() => buildPrompt(envelope), error => {
    assert.equal(error.code, 'E_RUNTIME_PROMPT_LIMIT');
    assert.match(error.message, /exceeds.*512.*narrow/i);
    return true;
  });
});

test('model-facing prompt receives only the manager-selected role and context', async t => {
  const context = await fixture(t, {}, true);
  const prompts = [];
  const receipt = await run({ ...context, respond: async prompt => {
    prompts.push(prompt);
    return response({ type: 'result', result: context.result });
  } });
  assert.equal(prompts.length, 1);
  assert.match(prompts[0], /"role":"developer"/);
  assert.ok(prompts[0].includes(JSON.stringify(context.envelope.roleInstructions).slice(1, -1)));
  assert.match(prompts[0], /Shared runtime context\./);
  assert.match(prompts[0], /Developer specialist context\./);
  assert.equal(prompts[0].includes('Unselected specialist context.'), false);
  assert.equal(receipt.acceptance, 'not-assessed');
});

test('an oversized assembled prompt fails before a model request and is visibly unknown', async t => {
  const context = await fixture(t, { maxInputBytes: 512 });
  let calls = 0;
  await assert.rejects(run({ ...context, respond: async () => {
    calls++;
    return response({ type: 'result', result: context.result });
  } }), error => {
    assert.equal(error.code, 'E_RUNTIME_PROMPT_LIMIT');
    assert.match(error.message, /narrow optional scope or context/i);
    return true;
  });
  assert.equal(calls, 0);
  assert.equal(status(context.project), 'unknown');
});

test('stop retry window counts real busy helper latency without exhausting eight process starts', async t => {
  const context = await fixture(t);
  const lock = path.join(context.project, '.git', 'sdlc', 'executions.lock');
  let now = 0;
  let stops = 0;
  const runWithClock = driverWithClock({ now: () => now });
  const bridge = async (operation, payload) => {
    if (operation === 'stop') stops++;
    try { return await context.bridge(operation, payload); }
    catch (error) {
      if (operation === 'stop' && error.code === 'E_EXECUTION_BUSY') now += 1100;
      throw error;
    }
  };
  try {
    await assert.rejects(runWithClock({
      ...context, bridge,
      respond: async () => {
        fs.writeFileSync(lock, 'test-owned writer contention', { flag: 'wx' });
        throw new Error('Synthetic external provider failure');
      }
    }), { code: 'E_RUNTIME_STOP_UNCONFIRMED' });
    assert.equal(stops, 2, 'Elapsed helper time, not only retry count, must bound stop persistence');
    assert.equal(status(context.project), 'active', 'A busy writer must not be bypassed to claim a persisted stop');
  } finally {
    fs.rmSync(lock, { force: true });
    await context.bridge('stop', { envelope: context.envelope });
  }
  assertUnresolved(context);
});

test('retry window does not abandon an in-flight real stop helper after its admission deadline', async t => {
  const context = await fixture(t);
  let now = 0;
  let enterStop;
  let releaseStop;
  const entered = new Promise(resolve => { enterStop = resolve; });
  const release = new Promise(resolve => { releaseStop = resolve; });
  let settled = false;
  let stops = 0;
  const runWithClock = driverWithClock({ now: () => now });
  const bridge = async (operation, payload) => {
    if (operation !== 'stop') return context.bridge(operation, payload);
    stops++;
    const pending = context.bridge(operation, payload);
    enterStop();
    await release;
    return pending;
  };
  const outcome = runWithClock({
    ...context, bridge,
    respond: async () => { throw new Error('Synthetic external provider failure'); }
  }).then(() => assert.fail('Provider failure cannot create a receipt'), error => error)
    .finally(() => { settled = true; });
  try {
    await entered;
    now = 3000;
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(settled, false, 'Retry admission deadline must not abandon an already-started helper');
  } finally { releaseStop(); }
  const error = await outcome;
  assert.match(error.message, /Synthetic external provider failure/);
  assert.equal(stops, 1);
  assertUnresolved(context);
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
    const observed = promptHistory(prompt)[0].output;
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
      const read = promptHistory(prompt)[0].output;
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

test('cancellation after prompt preparation but before adapter invocation is not a dispatched call', async t => {
  const context = await fixture(t);
  const controller = new AbortController();
  let calls = 0;
  const bridge = async (operation, payload) => {
    const result = await context.bridge(operation, payload);
    if (operation === 'step') controller.abort();
    return result;
  };
  await assert.rejects(run({ ...context, bridge, signal: controller.signal, respond: async () => {
    calls++;
    return response({ type: 'result', result: context.result });
  } }));
  assert.equal(calls, 0);
  const store = JSON.parse(fs.readFileSync(
    path.join(context.project, '.git', 'sdlc', 'bounded-runtime.json'), 'utf8'));
  assert.equal(store.iterations, 0);
  assert.equal(store.inputBytes, 0);
  assert.equal(store.requestAccounting.prepared, 1);
  assert.equal(store.requestAccounting.dispatched, 0);
});

test('provider invocation precedes durable dispatch confirmation', async t => {
  const context = await fixture(t);
  const order = [];
  const bridge = async (operation, payload) => {
    order.push(`bridge:${operation}`);
    return context.bridge(operation, payload);
  };
  await run({ ...context, bridge, respond: async () => {
    order.push('adapter');
    return response({ type: 'result', result: context.result });
  } });
  assert.ok(order.indexOf('adapter') >= 0);
  assert.ok(order.indexOf('bridge:dispatch') > order.indexOf('adapter'));
});

test('a helper without request lifecycle support fails before adapter invocation', async t => {
  const context = await fixture(t);
  let calls = 0;
  const bridge = async (operation, payload) => {
    const output = await context.bridge(operation, payload);
    if (operation === 'step') delete output.requestId;
    return output;
  };
  await assert.rejects(run({ ...context, bridge, respond: async () => {
    calls++;
    return response({ type: 'result', result: context.result });
  } }), /request lifecycle/);
  assert.equal(calls, 0);
  assertUnresolved(context);
});

test('an oversized delivered chunk records observed bytes and never reaches a tool or receipt', async t => {
  const context = await fixture(t, { maxOutputBytes: 64 });
  const prefix = 'é😀';
  const overflow = 'x'.repeat(65);
  const operations = [];
  const bridge = async (operation, payload) => {
    operations.push(operation);
    return context.bridge(operation, payload);
  };
  await assert.rejects(run({ ...context, bridge, respond: async () => (async function* () {
    yield prefix;
    yield overflow;
  })() }), /remaining output bound/);
  const store = JSON.parse(fs.readFileSync(
    path.join(context.project, '.git', 'sdlc', 'bounded-runtime.json'), 'utf8'));
  assert.equal(store.outputBytes, Buffer.byteLength(prefix + overflow));
  assert.equal(store.requestAccounting.unknown, 1);
  assert.equal(JSON.stringify(store).includes(overflow), false);
  assert.equal(operations.includes('tool'), false);
  assert.equal(operations.includes('receive'), false);
  assertUnresolved(context);
});

test('provider callback source drift still records the invoked request and observed output', async t => {
  const context = await fixture(t);
  let calls = 0;
  const output = JSON.stringify({ type: 'result', result: context.result });
  await assert.rejects(run({ ...context, respond: async () => {
    calls++;
    fs.writeFileSync(path.join(context.project, 'docs', 'plans', 'feature.md'), 'changed source');
    return (async function* () { yield output; })();
  } }));
  const store = JSON.parse(fs.readFileSync(
    path.join(context.project, '.git', 'sdlc', 'bounded-runtime.json'), 'utf8'));
  assert.equal(calls, 1);
  assert.equal(store.iterations, 1);
  assert.equal(store.requestAccounting.dispatched, 1);
  assert.equal(store.outputBytes, Buffer.byteLength(output));
  assert.equal(store.status, 'unknown');
  assertUnresolved(context);
});

for (const persisted of [false, true]) {
  test(`dispatch confirmation loss preserves uncertainty without duplicate settlement; persisted ${persisted}`, async t => {
    const context = await fixture(t);
    let invocations = 0;
    let dispatches = 0;
    const bridge = async (operation, payload) => {
      if (operation === 'dispatch') {
        dispatches++;
        if (dispatches === 1) {
          if (persisted) await context.bridge(operation, payload);
          throw new Error('dispatch confirmation lost');
        }
      }
      return context.bridge(operation, payload);
    };
    await assert.rejects(run({ ...context, bridge, respond: async () => {
      invocations++;
      return response({ type: 'result', result: context.result });
    } }), /dispatch confirmation lost/);
    assert.equal(invocations, 1);
    const store = JSON.parse(fs.readFileSync(
      path.join(context.project, '.git', 'sdlc', 'bounded-runtime.json'), 'utf8'));
    const built = buildPrompt(context.envelope);
    assert.equal(store.iterations, 1);
    assert.equal(store.inputBytes, built.promptBytes);
    assert.equal(store.totalInputBytes, built.promptBytes);
    assert.deepEqual(store.promptComponents, Object.fromEntries(
      built.components.map(component => [component.id, component.bytes])));
    assert.equal(store.requestAccounting.prepared, 1);
    assert.equal(store.requestAccounting.dispatched, persisted ? 1 : 0);
    assert.equal(store.requestAccounting.unknown, 1);
    assert.equal(store.requestAccounting.completed, 0);
    assert.equal(store.activeRequest, null);
    assertUnresolved(context);
  });
}

test('synchronous adapter throws are counted as unknown invocations without a receipt', async t => {
  const context = await fixture(t);
  let calls = 0;
  await assert.rejects(run({ ...context, respond: () => {
    calls++;
    throw new Error('synchronous provider failure');
  } }), /synchronous provider failure/);
  assert.equal(calls, 1);
  const store = JSON.parse(fs.readFileSync(
    path.join(context.project, '.git', 'sdlc', 'bounded-runtime.json'), 'utf8'));
  assert.equal(store.iterations, 1);
  assert.equal(store.requestAccounting.unknown, 1);
  assert.equal(store.requestAccounting.dispatched, 0);
  assertUnresolved(context);
});

test('interruption persists the exact partial UTF-8 output once without retaining text', async t => {
  const context = await fixture(t);
  const controller = new AbortController();
  let yielded;
  let release;
  const firstChunk = new Promise(resolve => { yielded = resolve; });
  const held = new Promise(resolve => { release = resolve; });
  try {
    const outcome = run({ ...context, signal: controller.signal, respond: async () => (async function* () {
      yield 'é😀';
      yielded();
      await held;
      yield 'unconsumed';
    })() });
    await firstChunk;
    controller.abort();
    await assert.rejects(outcome, /remote work is unconfirmed/);
  } finally { release(); }
  const store = JSON.parse(fs.readFileSync(
    path.join(context.project, '.git', 'sdlc', 'bounded-runtime.json'), 'utf8'));
  assert.equal(store.outputBytes, Buffer.byteLength('é😀', 'utf8'));
  assert.equal(store.requestAccounting.interrupted, 1);
  assert.equal(JSON.stringify(store).includes('é😀'), false);
  assertUnresolved(context);
});

test('a chunk delivered at the abort boundary is counted before stopping', async t => {
  const context = await fixture(t);
  const controller = new AbortController();
  await assert.rejects(run({ ...context, signal: controller.signal, respond: async () => ({
    [Symbol.asyncIterator]() {
      let first = true;
      return {
        next() {
          if (!first) return new Promise(() => {});
          first = false;
          controller.abort();
          return Promise.resolve({ done: false, value: 'é😀' });
        },
        return() { return Promise.resolve({ done: true }); }
      };
    }
  }) }), /remote work is unconfirmed/);
  const store = JSON.parse(fs.readFileSync(
    path.join(context.project, '.git', 'sdlc', 'bounded-runtime.json'), 'utf8'));
  assert.equal(store.outputBytes, Buffer.byteLength('é😀', 'utf8'));
  assert.equal(store.requestAccounting.interrupted, 1);
});

test('provider stream failure keeps prior partial output in unknown accounting', async t => {
  const context = await fixture(t);
  await assert.rejects(run({ ...context, respond: async () => (async function* () {
    yield 'é😀';
    throw new Error('provider stream failed');
  })() }), /provider stream failed/);
  const store = JSON.parse(fs.readFileSync(
    path.join(context.project, '.git', 'sdlc', 'bounded-runtime.json'), 'utf8'));
  assert.equal(store.outputBytes, Buffer.byteLength('é😀', 'utf8'));
  assert.equal(store.requestAccounting.unknown, 1);
  assertUnresolved(context);
});

test('UTF-8 response limits treat a surrogate pair split across chunks as one scalar', async t => {
  const baseline = await fixture(t);
  baseline.result.blockers = ['😀'];
  const value = { type: 'result', result: baseline.result };
  const serialized = JSON.stringify(value);
  const pairStart = serialized.indexOf('😀');
  assert.ok(pairStart >= 0);
  const context = await fixture(t, { maxOutputBytes: Buffer.byteLength(serialized, 'utf8') });
  context.result.blockers = ['😀'];
  const chunks = [
    serialized.slice(0, pairStart + 1),
    serialized.slice(pairStart + 1, pairStart + 2),
    serialized.slice(pairStart + 2)
  ];
  await run({ ...context, respond: async () => (async function* () {
    for (const chunk of chunks) yield chunk;
  })() });
  const store = JSON.parse(fs.readFileSync(
    path.join(context.project, '.git', 'sdlc', 'bounded-runtime.json'), 'utf8'));
  assert.equal(store.outputBytes, Buffer.byteLength(serialized, 'utf8'));
});
