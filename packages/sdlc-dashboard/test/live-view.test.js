'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {canonical, sign, liveFixture, liveV2Fixture, acceptedLiveFixture} = require('./fixture');

test('live manager view has a strict digest-verified parser', () => {
  const {parseLiveView} = require('../snapshot');
  assert.equal(typeof parseLiveView, 'function');
  const value = liveFixture();
  const parsed = parseLiveView(Buffer.from(canonical(value)));
  assert.equal(parsed.kind, 'sdlc-live-execution-view');
  assert.equal(parsed.binding.executionId, 'feature-one');
});

test('live manager view parser rejects unknown and altered manager data', () => {
  const {parseLiveView} = require('../snapshot');
  assert.equal(typeof parseLiveView,'function');
  const unknown = liveFixture();
  unknown.controls.dispatch = true;
  sign(unknown);
  assert.throws(() => parseLiveView(Buffer.from(canonical(unknown))));

  const altered = liveFixture();
  altered.controls.autonomous = false;
  assert.throws(() => parseLiveView(Buffer.from(canonical(altered))));
});
test('live view carries acceptance provenance only for accepted tasks', () => {
  const {parseLiveView} = require('../snapshot');
  const accepted = parseLiveView(Buffer.from(canonical(acceptedLiveFixture())));
  assert.equal(accepted.tasks[0].acceptanceBasis, 'independent-operator-validation');
  for (const mutate of [
    value => { value.tasks[0].acceptanceBasis = null; },
    value => { value.tasks[0].acceptanceBasis = 'worker-passed'; },
    value => { delete value.tasks[0].acceptanceBasis; }
  ]) {
    const value = acceptedLiveFixture(); mutate(value);
    assert.throws(() => parseLiveView(Buffer.from(canonical(sign(value)))));
  }
  const reported = liveFixture();
  reported.tasks[0].acceptanceBasis = 'independent-operator-validation';
  assert.throws(() => parseLiveView(Buffer.from(canonical(sign(reported)))));
});
test('live view version 2 validates context and the matching project Gantt', () => {
  const {parseLiveView} = require('../snapshot');
  const parsed = parseLiveView(Buffer.from(canonical(liveV2Fixture())));
  assert.equal(parsed.context.shared.content,'API contract agreed; tests pending.');
  assert.equal(parsed.gantt.tasks[0].actualDurationMs,20);
  for (const mutate of [
    value => { value.context.shared.content = 'unbound note'; },
    value => { value.gantt.executionId = 'another-execution'; },
    value => { value.gantt.tasks[0].status = 'accepted'; },
    value => { value.gantt.tasks[0].plannedEndMs = 99; },
    value => { value.gantt.plannedDurationMs = 101; }
  ]) {
    const value = liveV2Fixture(); mutate(value);
    assert.throws(() => parseLiveView(Buffer.from(canonical(sign(value)))));
  }
});

test('unapproved live execution projects proposed Gantt rows before task approval', () => {
  const {parseLiveView} = require('../snapshot');
  const value = liveV2Fixture();
  value.planApproved = false;
  Object.assign(value.tasks[0], {
    status:'waiting', attemptId:null, resultId:null, resultDigest:null,
    acceptanceSchemaVersion:null, reportedStatus:null
  });
  value.progress = {
    total:1, waiting:1, ready:0, running:0, blocked:0, reported:0, accepted:0, failed:0, cancelled:0
  };
  value.gantt.tasks[0].status = 'proposed';
  value.gantt.tasks[0].actualStartOffsetMs = null;
  value.gantt.tasks[0].actualDurationMs = null;
  value.gantt.actualOrigin = null;
  value.gantt.actualDurationMs = null;
  value.events = [];

  const parsed = parseLiveView(Buffer.from(canonical(sign(value))));
  assert.equal(parsed.planApproved, false);
  assert.equal(parsed.tasks[0].status, 'waiting');
  assert.equal(parsed.gantt.tasks[0].status, 'proposed');
});
