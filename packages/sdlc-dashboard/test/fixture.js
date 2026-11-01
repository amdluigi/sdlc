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
module.exports = {canonical, sign, fixture};
