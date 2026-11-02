'use strict';
const crypto = require('node:crypto');
function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') {
    return '{' + Object.keys(value).sort().map(key => canonical(key) + ':' + canonical(value[key])).join(',') + '}';
  }
  if (typeof value === 'bigint') return value.toString();
  return JSON.stringify(value).replace(/[\u007f-\uffff]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
}
function sign(value) {
  delete value.snapshotDigest;
  value.snapshotDigest = 'sha256:' + crypto.createHash('sha256').update(canonical(value)).digest('hex');
  return value;
}
function digest(value) {
  return 'sha256:' + crypto.createHash('sha256').update(canonical(value)).digest('hex');
}
function fixture() {
  return sign({
    schemaVersion: 1, kind: 'sdlc-execution-snapshot',
    binding: {executionId: 'example', planRevision: 1, planDigest: 'sha256:' + 'a'.repeat(64)},
    approved: false, writerLockPresent: false,
    tasks: [{
      id: 'task-a', title: 'Plain <script> Ω 😀', status: 'waiting', attemptId: null,
      reportedStatus: null, estimateMs: 100, recordedIntervalMs: null, requestedModel: null
    }],
    controls: {enabled: false, paused: false, pendingCancellationCount: 0, unknownNativeAttemptCount: 0}
  });
}
function acceptedSnapshotFixture() {
  const value = fixture();
  value.schemaVersion = 2;
  value.tasks = [
    {...value.tasks[0], status: 'accepted', attemptId: 'attempt-a', reportedStatus: 'completed',
      acceptanceBasis: 'independent-operator-validation'},
    {id: 'task-b', title: 'Dependent', status: 'waiting', attemptId: null, reportedStatus: null,
      estimateMs: null, recordedIntervalMs: null, requestedModel: null, acceptanceBasis: null}
  ];
  return sign(value);
}
function acceptedLiveFixture() {
  const value = liveFixture();
  Object.assign(value.tasks[0], {status: 'accepted', acceptanceSchemaVersion: null,
    acceptanceBasis: 'independent-operator-validation'});
  value.progress.reported = 0; value.progress.accepted = 1;
  return sign(value);
}
function liveFixture() {
  const task = {
    id:'task-a',title:'Inspect a bounded task',status:'reported',attemptId:'attempt-a',resultId:'result-a',
    resultDigest:'sha256:' + 'e'.repeat(64),acceptanceSchemaVersion:2,acceptanceBasis:null,
    reportedStatus:'completed',estimateMs:null,recordedIntervalMs:null,requestedModel:null,
    prerequisites:[],acceptanceCriteria:['AC-1']
  };
  return sign({
    schemaVersion:1,kind:'sdlc-live-execution-view',
    binding:{executionId:'feature-one',planRevision:1,planDigest:'sha256:' + 'a'.repeat(64)},
    planDigest:'sha256:' + 'a'.repeat(64),policyDigest:'sha256:' + 'b'.repeat(64),
    controlsDigest:'sha256:' + 'c'.repeat(64),controlsStateDigest:'sha256:' + 'd'.repeat(64),
    planApproved:true,writerLockPresent:false,
    controls:{
      enabled:true,paused:false,autonomous:true,controlsApproved:true,pendingCancellationCount:0,
      unknownNativeAttemptCount:0,hostCancellation:'unavailable',spendEnforcement:false
    },
    progress:{
      total:1,waiting:0,ready:0,running:0,blocked:0,reported:1,accepted:0,failed:0,cancelled:0
    },
    tasks:[task],
    events:[{sequence:1,type:'TASK_RESULT_RECEIVED',taskId:'task-a',attemptId:'attempt-a',
      recordedAt:'2026-01-01T00:00:00Z'}]
  });
}
function liveV2Fixture() {
  const value = liveFixture();
  delete value.snapshotDigest;
  value.schemaVersion = 2;
  value.tasks[0].estimateMs = 100;
  const shared = {
    content:'API contract agreed; tests pending.', source:'operator', author:'operator', agent:null,
    updatedAt:'2026-01-01T00:00:00Z', planRevision:1
  };
  shared.digest = digest(shared.content);
  const agent = {
    content:'Own the API and contract tests.', source:'worker', author:'developer', agent:'developer',
    updatedAt:'2026-01-01T00:01:00Z', planRevision:1
  };
  agent.digest = digest(agent.content);
  const context = {schemaVersion:1,revision:2,shared,agents:{developer:agent}};
  context.digest = digest(context);
  value.context = context;
  value.gantt = {
    schemaVersion:1,kind:'sdlc-project-gantt',executionId:'feature-one',planRevision:1,
    plannedDurationMs:100,plannedComplete:true,
    plannedBasis:'declared estimates and dependencies only; no resource schedule or calendar forecast',
    actualOrigin:'2026-01-01T00:00:00Z',actualDurationMs:20,
    actualBasis:'manager event timestamps; not host execution timing',
    tasks:[{
      id:'task-a',title:'Inspect a bounded task',agent:'developer',status:'reported',
      executionMode:'sequential',executionGroup:null,prerequisites:[],estimateMs:100,
      plannedStartMs:0,plannedEndMs:100,actualStartOffsetMs:0,actualDurationMs:20
    }]
  };
  return sign(value);
}
module.exports = {canonical, sign, digest, fixture, liveFixture, liveV2Fixture, acceptedSnapshotFixture, acceptedLiveFixture};
