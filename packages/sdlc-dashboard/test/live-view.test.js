'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {canonical, sign, liveFixture, acceptedLiveFixture} = require('./fixture');

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
