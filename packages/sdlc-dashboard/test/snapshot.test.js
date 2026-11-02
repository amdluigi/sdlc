'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {fixture, sign, canonical, acceptedSnapshotFixture} = require('./fixture');
const target = path.join(__dirname, '..', 'snapshot.js');
test('missing feature: a real strict snapshot validator must exist', () => {
  assert.ok(fs.existsSync(target), 'Missing read-only snapshot validator');
});
function api() { return require(target); }
test('accepts exact version-1 snapshot with Unicode digest parity', () => {
  const value = fixture();
  assert.deepEqual(JSON.parse(canonical(api().parseSnapshot(Buffer.from(canonical(value))))), value);
});
test('canonical ASCII JSON retains full int64 and Python surrogate escaping', () => {
  assert.equal(api().canonical({z: '\u007f😀Ω', a: 9223372036854775807n}),
    '{"a":9223372036854775807,"z":"\\u007f\\ud83d\\ude00\\u03a9"}');
  assert.equal(api().canonical({'😀':1,'\uffff':2}), '{"\\uffff":2,"\\ud83d\\ude00":1}');
  const value = fixture();
  value.tasks[0].estimateMs = 9223372036854775807n;
  const parsed = api().parseSnapshot(Buffer.from(canonical(sign(value))));
  assert.equal(parsed.tasks[0].estimateMs, 9223372036854775807n);
});
test('preserves zero estimates, intervals and empty task exports without inventing observations', () => {
  const value = fixture();
  value.tasks[0].estimateMs = 0; value.tasks[0].recordedIntervalMs = 0;
  assert.equal(api().parseSnapshot(Buffer.from(canonical(sign(value)))).tasks[0].estimateMs,0);
  value.tasks = [];
  assert.equal(api().parseSnapshot(Buffer.from(canonical(sign(value)))).tasks.length,0);
});
test('accepts every fixed task/report status and explicit exported boolean controls', () => {
  for (const status of ['waiting','ready','running','blocked','reported','accepted','failed','cancelled']) {
    const value = fixture();
    value.tasks[0].status = status;
    value.tasks[0].attemptId = 'attempt-one';
    value.tasks[0].reportedStatus = 'completed';
    value.controls.enabled = value.controls.paused = value.approved = value.writerLockPresent = true;
    assert.equal(api().parseSnapshot(Buffer.from(canonical(sign(value)))).tasks[0].status,status);
  }
  for (const reportedStatus of ['completed','failed','blocked','cancelled']) {
    const value = fixture(); value.tasks[0].reportedStatus = reportedStatus;
    assert.equal(api().parseSnapshot(Buffer.from(canonical(sign(value)))).tasks[0].reportedStatus,reportedStatus);
  }
});
for (const [name, mutate] of [
  ['unknown top field', v => {v.extra = true;}],
  ['unknown task field', v => {v.tasks[0].action = 'run';}],
  ['unknown control field', v => {v.controls.approve = true;}],
  ['unknown binding field', v => {v.binding.root = 'outside';}],
  ['missing required field', v => {delete v.approved;}],
  ['future version', v => {v.schemaVersion = 2;}],
  ['wrong kind', v => {v.kind = 'other';}],
  ['invalid execution ID', v => {v.binding.executionId = '../outside';}],
  ['invalid plan digest', v => {v.binding.planDigest = 'x';}],
  ['nonpositive revision', v => {v.binding.planRevision = 0;}],
  ['boolean revision', v => {v.binding.planRevision = true;}],
  ['invalid status', v => {v.tasks[0].status = 'done';}],
  ['invalid report', v => {v.tasks[0].reportedStatus = 'accepted';}],
  ['invalid attempt', v => {v.tasks[0].attemptId = '../../x';}],
  ['duplicate tasks', v => {v.tasks.push({...v.tasks[0]});}],
  ['too many tasks', v => {v.tasks = Array.from({length:257}, (_, i) => ({...v.tasks[0], id:'task-'+i}));}],
  ['negative interval', v => {v.tasks[0].recordedIntervalMs = -1;}],
  ['negative estimate', v => {v.tasks[0].estimateMs = -1;}],
  ['fractional number', v => {v.tasks[0].estimateMs = 1.5;}],
  ['beyond int64', v => {v.controls.pendingCancellationCount = 9223372036854775808n;}],
  ['control character title', v => {v.tasks[0].title = 'a\nb';}],
  ['oversized title', v => {v.tasks[0].title = 'a'.repeat(2049);}],
  ['nonboolean flag', v => {v.controls.enabled = 1;}]
]) {
  test('rejects ' + name + ' even when digest is recomputed', () => {
    const {parseSnapshot} = api();
    const value = fixture(); mutate(value); sign(value);
    assert.throws(() => parseSnapshot(Buffer.from(canonical(value))));
  });
}
test('rejects corrupt, duplicate, malformed UTF-8, oversized and trailing input', () => {
  const {parseSnapshot} = api();
  for (const input of [
    Buffer.from('{"schemaVersion":1,"schemaVersion":1}'),
    Buffer.from('{"a":{"x":1,"x":2}}'), Buffer.from('{}x'),
    Buffer.from('['.repeat(40)), Buffer.from([0xff]),
    Buffer.alloc(2 * 1024 * 1024 + 1, 32),
    Buffer.from(JSON.stringify({...fixture(), snapshotDigest:'sha256:' + '0'.repeat(64)}))
  ]) assert.throws(() => parseSnapshot(input));
});
test('refresh binding rejects another execution, rollback and rewritten same revision', () => {
  const {validateReloadBinding} = api();
  const original = fixture().binding;
  for (const next of [
    {...original, executionId:'other'}, {...original, planRevision:0},
    {...original, planDigest:'sha256:'+'b'.repeat(64)}
  ]) assert.throws(() => validateReloadBinding(next, original));
  assert.doesNotThrow(() => validateReloadBinding({...original,planRevision:2}, original));
});
test('version-2 export snapshot keeps independent-validation acceptance provenance', () => {
  const value = acceptedSnapshotFixture();
  const parsed = api().parseSnapshot(Buffer.from(canonical(value)));
  assert.equal(parsed.schemaVersion, 2);
  assert.deepEqual(parsed.tasks.map(task => task.acceptanceBasis), ['independent-operator-validation', null]);
});
test('snapshot acceptance basis must match version and accepted status exactly', () => {
  const bad = [
    value => { delete value.tasks[0].acceptanceBasis; },
    value => { value.tasks[1].acceptanceBasis = 'independent-operator-validation'; },
    value => { value.tasks[0].acceptanceBasis = null; },
    value => { value.tasks[0].acceptanceBasis = 'worker-passed'; },
    value => { value.schemaVersion = 1; },
    value => { value.schemaVersion = 3; }
  ];
  for (const mutate of bad) {
    const value = acceptedSnapshotFixture();
    mutate(value);
    assert.throws(() => api().parseSnapshot(Buffer.from(canonical(sign(value)))));
  }
  const legacy = fixture();
  legacy.tasks[0].acceptanceBasis = null;
  assert.throws(() => api().parseSnapshot(Buffer.from(canonical(sign(legacy)))));
});
