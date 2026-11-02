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
module.exports = {canonical, sign, fixture, liveFixture, acceptedSnapshotFixture, acceptedLiveFixture};
