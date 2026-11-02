'use strict';
const fs = require('node:fs/promises');
const constants = require('node:fs').constants;
const path = require('node:path');
const crypto = require('node:crypto');
const {TextDecoder} = require('node:util');
const MAX_BYTES = 2 * 1024 * 1024;
const MAX_INT = 9223372036854775807n;
const DIGEST = /^sha256:[0-9a-f]{64}$/;
const ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const STATUSES = ['waiting','ready','running','blocked','reported','accepted','failed','cancelled'];
function reject() { throw new Error('Invalid or unavailable execution snapshot'); }
function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value !== null && typeof value === 'object') {
    const keys = Object.keys(value).sort((a,b) => {
      const aa = Array.from(a, c => c.codePointAt(0)), bb = Array.from(b, c => c.codePointAt(0));
      for (let i=0; i<Math.min(aa.length,bb.length); i++) if (aa[i] !== bb[i]) return aa[i]-bb[i];
      return aa.length-bb.length;
    });
    return '{' + keys.map(k => canonical(k) + ':' + canonical(value[k])).join(',') + '}';
  }
  if (typeof value === 'bigint') return value.toString();
  if (typeof value === 'number' && !Number.isSafeInteger(value)) reject();
  const encoded = JSON.stringify(value);
  if (encoded === undefined) reject();
  return encoded.replace(/[\u007f-\uffff]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
}
// JSON.parse loses int64 precision and silently accepts duplicate object keys.
function strictJSON(text) {
  let offset = 0;
  function space() {while (/[ \r\n\t]/.test(text[offset] || '\0')) offset++;}
  function string() {
    const start = offset++;
    for (; offset < text.length; offset++) {
      if (text[offset] === '\\') {offset++; continue;}
      if (text[offset] === '"') return JSON.parse(text.slice(start, ++offset));
      if (text.charCodeAt(offset) < 32) reject();
    }
    reject();
  }
  function value(depth = 0) {
    if (depth > 12) reject();
    space();
    const char = text[offset];
    if (char === '"') return string();
    if (char === '{' || char === '[') {
      const object = char === '{';
      const result = object ? Object.create(null) : [];
      offset++; space();
      const end = object ? '}' : ']';
      if (text[offset] === end) {offset++; return result;}
      let count = 0;
      while (offset < text.length) {
        if (++count > 1024) reject();
        space();
        if (object) {
          if (text[offset] !== '"') reject();
          const key = string(); space();
          if (Object.hasOwn(result,key) || text[offset++] !== ':') reject();
          result[key] = value(depth+1);
        } else result.push(value(depth+1));
        space();
        if (text[offset] === end) {offset++; return result;}
        if (text[offset++] !== ',') reject();
      }
      reject();
    }
    for (const [literal, result] of [['true',true],['false',false],['null',null]]) {
      if (text.startsWith(literal,offset)) {offset += literal.length; return result;}
    }
    const match = /^(?:-?(?:0|[1-9][0-9]*))/.exec(text.slice(offset));
    if (!match || match[0].length > 20) reject();
    offset += match[0].length;
    const integer = BigInt(match[0]);
    if (integer < -MAX_INT || integer > MAX_INT) reject();
    return integer <= BigInt(Number.MAX_SAFE_INTEGER) && integer >= BigInt(Number.MIN_SAFE_INTEGER)
      ? Number(integer) : integer;
  }
  const result = value(); space();
  if (offset !== text.length) reject();
  return result;
}
function shape(value, fields) {
  if (!value || Array.isArray(value) || typeof value !== 'object') reject();
  const keys = Object.keys(value);
  if (keys.length !== fields.length || fields.some(k => !Object.hasOwn(value,k))) reject();
}
function text(value, maximum = 2048) {
  if (typeof value !== 'string' || !value.trim() || Array.from(value).length > maximum ||
      /[\u0000-\u001f\u007f]/.test(value)) reject();
}
function id(value) {text(value,128); if (!ID.test(value)) reject();}
function number(value, minimum = 0) {
  if (!(typeof value === 'bigint' || (typeof value === 'number' && Number.isSafeInteger(value))) ||
      BigInt(value) < BigInt(minimum) || BigInt(value) > MAX_INT) reject();
}
function boolean(value) {if (typeof value !== 'boolean') reject();}
function digest(value) {if (typeof value !== 'string' || !DIGEST.test(value)) reject();}
function binding(value) {
  shape(value,['executionId','planRevision','planDigest']);
  id(value.executionId); number(value.planRevision,1); digest(value.planDigest);
}
const ACCEPTANCE_BASES = ['worker-verification-with-operator-judgment','independent-operator-validation'];
function acceptanceBasis(task) {
  if (task.status === 'accepted' ? !ACCEPTANCE_BASES.includes(task.acceptanceBasis) : task.acceptanceBasis !== null) reject();
}
function validateSnapshot(value) {
  shape(value,['schemaVersion','kind','binding','approved','writerLockPresent','tasks','controls','snapshotDigest']);
  if (![1,2].includes(value.schemaVersion) || value.kind !== 'sdlc-execution-snapshot') reject();
  binding(value.binding); boolean(value.approved); boolean(value.writerLockPresent);
  shape(value.controls,['enabled','paused','pendingCancellationCount','unknownNativeAttemptCount']);
  boolean(value.controls.enabled); boolean(value.controls.paused);
  number(value.controls.pendingCancellationCount); number(value.controls.unknownNativeAttemptCount);
  if (!Array.isArray(value.tasks) || value.tasks.length > 256) reject();
  const ids = new Set();
  for (const task of value.tasks) {
    shape(task,['id','title','status','attemptId','reportedStatus','estimateMs','recordedIntervalMs','requestedModel']
      .concat(value.schemaVersion === 2 ? ['acceptanceBasis'] : []));
    id(task.id); text(task.title);
    if (ids.has(task.id) || !STATUSES.includes(task.status)) reject();
    if (value.schemaVersion === 2) acceptanceBasis(task);
    ids.add(task.id);
    if (task.attemptId !== null) id(task.attemptId);
    if (task.reportedStatus !== null && !['completed','failed','blocked','cancelled'].includes(task.reportedStatus)) reject();
    if (task.estimateMs !== null) number(task.estimateMs);
    if (task.recordedIntervalMs !== null) number(task.recordedIntervalMs);
    if (task.requestedModel !== null) text(task.requestedModel,128);
  }
  digest(value.snapshotDigest);
  const unsigned = {...value}; delete unsigned.snapshotDigest;
  const encoded = canonical(unsigned);
  if (Buffer.byteLength(encoded) > MAX_BYTES ||
      'sha256:' + crypto.createHash('sha256').update(encoded,'ascii').digest('hex') !== value.snapshotDigest) reject();
  return value;
}
function parseSnapshot(bytes) {
  if (!(bytes instanceof Uint8Array) || bytes.byteLength > MAX_BYTES) reject();
  const decoded = new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes);
  return validateSnapshot(strictJSON(decoded));
}
function validateLiveView(value) {
  shape(value,['schemaVersion','kind','binding','planDigest','policyDigest','controlsDigest',
    'controlsStateDigest','planApproved','writerLockPresent','controls','progress','tasks','events','snapshotDigest']);
  if (value.schemaVersion !== 1 || value.kind !== 'sdlc-live-execution-view') reject();
  binding(value.binding); digest(value.planDigest);
  if (value.planDigest !== value.binding.planDigest) reject();
  for (const field of ['policyDigest','controlsDigest','controlsStateDigest']) {
    if (value[field] !== null) digest(value[field]);
  }
  boolean(value.planApproved); boolean(value.writerLockPresent);
  shape(value.controls,['enabled','paused','autonomous','controlsApproved','pendingCancellationCount',
    'unknownNativeAttemptCount','hostCancellation','spendEnforcement']);
  for (const field of ['enabled','paused','autonomous','controlsApproved']) boolean(value.controls[field]);
  number(value.controls.pendingCancellationCount); number(value.controls.unknownNativeAttemptCount);
  if (value.controls.hostCancellation !== 'unavailable' || value.controls.spendEnforcement !== false) reject();
  const statuses = ['waiting','ready','running','blocked','reported','accepted','failed','cancelled'];
  shape(value.progress,statuses.concat('total'));
  for (const field of statuses.concat('total')) number(value.progress[field]);
  if (!Array.isArray(value.tasks) || value.tasks.length > 256 || value.progress.total !== value.tasks.length) reject();
  const tasks = new Map();
  for (const task of value.tasks) {
    shape(task,['id','title','status','attemptId','resultId','resultDigest','acceptanceSchemaVersion','acceptanceBasis',
      'reportedStatus','estimateMs','recordedIntervalMs','requestedModel','prerequisites','acceptanceCriteria']);
    id(task.id); text(task.title);
    if (!statuses.includes(task.status) || tasks.has(task.id)) reject();
    acceptanceBasis(task);
    for (const field of ['attemptId','resultId']) if (task[field] !== null) id(task[field]);
    if ((task.resultId === null) !== (task.resultDigest === null)) reject();
    if (task.resultDigest !== null) digest(task.resultDigest);
    if (![1,2,null].includes(task.acceptanceSchemaVersion) ||
        (task.acceptanceSchemaVersion !== null && (task.status !== 'reported' || task.resultId === null))) reject();
    if (task.reportedStatus !== null && !['completed','failed','blocked','cancelled'].includes(task.reportedStatus)) reject();
    for (const field of ['estimateMs','recordedIntervalMs']) if (task[field] !== null) number(task[field]);
    if (task.requestedModel !== null) {
      text(task.requestedModel,128);
      if (!/^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/.test(task.requestedModel)) reject();
    }
    if (!Array.isArray(task.prerequisites) || task.prerequisites.length > 256 ||
        new Set(task.prerequisites).size !== task.prerequisites.length) reject();
    task.prerequisites.forEach(id);
    if (!Array.isArray(task.acceptanceCriteria) || task.acceptanceCriteria.length > 256 ||
        new Set(task.acceptanceCriteria).size !== task.acceptanceCriteria.length) reject();
    task.acceptanceCriteria.forEach(value => text(value));
    tasks.set(task.id,task);
  }
  const counts = Object.fromEntries(statuses.map(status => [status,0]));
  for (const task of value.tasks) {
    counts[task.status]++;
    if (task.prerequisites.some(parent => !tasks.has(parent))) reject();
  }
  if (statuses.some(status => value.progress[status] !== counts[status])) reject();
  if (!Array.isArray(value.events) || value.events.length > 256) reject();
  let sequence = 0;
  for (const event of value.events) {
    shape(event,['sequence','type','taskId','attemptId','recordedAt']);
    number(event.sequence,1);
    if (event.sequence !== sequence + 1) reject();
    sequence = event.sequence;
    text(event.type,64);
    if (!/^[A-Z][A-Z_]*$/.test(event.type)) reject();
    if (event.taskId !== null) id(event.taskId);
    if (event.attemptId !== null) id(event.attemptId);
    text(event.recordedAt,32);
    if (!/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/.test(event.recordedAt) ||
        !Number.isFinite(Date.parse(event.recordedAt))) reject();
  }
  if (value.snapshotDigest !== undefined) digest(value.snapshotDigest);
  const unsigned = {...value}; delete unsigned.snapshotDigest;
  const encoded = canonical(unsigned);
  if (Buffer.byteLength(encoded) > MAX_BYTES ||
      'sha256:' + crypto.createHash('sha256').update(encoded,'ascii').digest('hex') !== value.snapshotDigest) reject();
  return value;
}
function parseLiveView(bytes) {
  if (!(bytes instanceof Uint8Array) || bytes.byteLength > MAX_BYTES) reject();
  const decoded = new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes);
  return validateLiveView(strictJSON(decoded));
}
function validateReloadBinding(next, previous) {
  binding(next); binding(previous);
  if (next.executionId !== previous.executionId || BigInt(next.planRevision) < BigInt(previous.planRevision) ||
      (BigInt(next.planRevision) === BigInt(previous.planRevision) && next.planDigest !== previous.planDigest)) reject();
}
function comparable(value) {return process.platform === 'win32' ? value.toLowerCase() : value;}
function fingerprint(stat) {
  return ['dev','ino','mode','size','mtimeNs','ctimeNs','birthtimeNs'].map(k => String(stat[k])).join(':');
}
async function inspectPath(absolute) {
  const parsed = path.parse(absolute);
  const paths = [parsed.root];
  let current = parsed.root;
  for (const component of absolute.slice(parsed.root.length).split(path.sep).filter(Boolean)) {
    current = path.join(current,component); paths.push(current);
  }
  const result = [];
  for (const item of paths) {
    const stat = await fs.lstat(item,{bigint:true});
    if (stat.isSymbolicLink()) reject();
    if (comparable(await fs.realpath(item)) !== comparable(item)) reject();
    result.push([item,fingerprint(stat)]);
  }
  return result;
}
async function readSnapshot(root, selected) {
  if (typeof root !== 'string' || typeof selected !== 'string' ||
      !path.isAbsolute(root) || !path.isAbsolute(selected)) reject();
  if (process.platform === 'win32' && (
    !/^[a-z]:\\/i.test(root) || !/^[a-z]:\\/i.test(selected) ||
    root.slice(2).includes(':') || selected.slice(2).includes(':')
  )) reject();
  root = path.resolve(root); selected = path.resolve(selected);
  const relative = path.relative(root,selected);
  if (!relative || relative === '..' || relative.startsWith('..' + path.sep) || path.isAbsolute(relative)) reject();
  const before = await inspectPath(selected);
  const rootStat = await fs.lstat(root,{bigint:true});
  if (!rootStat.isDirectory() || rootStat.isSymbolicLink()) reject();
  const initial = await fs.lstat(selected,{bigint:true});
  if (!initial.isFile() || initial.size > BigInt(MAX_BYTES)) reject();
  let handle;
  try {
    handle = await fs.open(selected,constants.O_RDONLY | (constants.O_NOFOLLOW || 0));
    const opened = await handle.stat({bigint:true});
    if (!opened.isFile() || fingerprint(opened) !== fingerprint(initial)) reject();
    const bytes = Buffer.alloc(MAX_BYTES+1);
    let length = 0;
    while (length < bytes.length) {
      const read = await handle.read(bytes,length,bytes.length-length,null);
      if (!read.bytesRead) break;
      length += read.bytesRead;
    }
    if (length > MAX_BYTES || BigInt(length) !== opened.size ||
        fingerprint(await handle.stat({bigint:true})) !== fingerprint(opened)) reject();
    const after = await inspectPath(selected);
    if (JSON.stringify(before) !== JSON.stringify(after) ||
        fingerprint(await fs.lstat(root,{bigint:true})) !== fingerprint(rootStat)) reject();
    return parseSnapshot(bytes.subarray(0,length));
  } finally {
    if (handle) await handle.close();
  }
}
module.exports = {
  MAX_BYTES, canonical, parseSnapshot, validateSnapshot, validateReloadBinding, readSnapshot,
  parseLiveView, validateLiveView
};
