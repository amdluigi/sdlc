'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {LiveProvider,LiveController} = require('../manager_provider');
const {digest,sign,liveFixture,liveV2Fixture,acceptedLiveFixture} = require('./fixture');

class EventEmitter {
  constructor() {this.listeners=[];this.event=fn=>{this.listeners.push(fn);return {dispose(){}};};}
  fire(value) {this.listeners.forEach(fn=>fn(value));}
  dispose() {}
}
const vscode = {
  EventEmitter,
  ThemeIcon:class {constructor(id){this.id=id;}},
  TreeItem:class {constructor(label,state){this.label=label;this.collapsibleState=state;}},
  TreeItemCollapsibleState:{None:0,Collapsed:1}
};

test('live tree renders current task detail, progress and events with native accessible labels', () => {
  const provider = new LiveProvider(vscode);
  provider.show(liveFixture());
  const task = provider.find('live-task:task-a');
  assert.match(task.label,/reported/);
  assert.equal(task.accessibilityInformation.role,'treeitem');
  assert.ok(provider.find('task-a:criteria'));
  assert.ok(provider.find('live-events'));
  provider.setFilter('waiting');
  assert.equal(provider.find('live-task:task-a'),undefined);
  provider.setFilter('reported');
  assert.ok(provider.find('live-task:task-a'));
});

test('live controller reads only after explicit selection and binds every action to current view', async () => {
  const calls = [];
  const provider = new LiveProvider(vscode);
  const controller = new LiveController(provider,async (root,request) => {
    calls.push({root,request});
    return {operation:request.operation,view:liveFixture()};
  });
  assert.deepEqual(calls,[]);
  assert.equal(await controller.load('C:\\project','feature-one'),true);
  assert.equal(await controller.refresh(),true);
  assert.deepEqual(calls.map(call=>call.request.operation),['inspect','inspect']);
  await controller.action('approve-plan');
  const action = calls.at(-1);
  assert.equal(action.request.operation,'approve-plan');
  assert.equal(action.request.expectedBinding.controlsStateDigest,'sha256:' + 'd'.repeat(64));
  assert.match(action.request.confirmationDigest,/^sha256:[0-9a-f]{64}$/);
});


test('live tree shows recorded acceptance provenance for accepted tasks', () => {
  const provider = new LiveProvider(vscode);
  provider.show(acceptedLiveFixture());
  const basis = provider.find('task-a:accepted-basis');
  assert.equal(basis.label,'Accepted by independent operator validation; worker verification not treated as passed');
  assert.equal(provider.find('task-a:acceptance-basis'),undefined);
  provider.show(liveFixture());
  assert.equal(provider.find('task-a:accepted-basis'),undefined);
  assert.ok(provider.find('task-a:acceptance-basis'));
});

test('live tree exposes a readable project Gantt and shared and role-specific context', () => {
  const provider = new LiveProvider(vscode);
  provider.show(liveV2Fixture());
  const gantt = provider.find('live-gantt');
  const row = provider.find('live-gantt-task:task-a');
  const shared = provider.find('live-context-shared');
  const role = provider.find('live-context-agent:developer');
  assert.ok(gantt,'Gantt summary is available in the keyboard-operable tree');
  assert.ok(row,'every project activity has a Gantt text alternative');
  assert.ok(shared,'shared project context is readable');
  assert.ok(role,'role-specific worker context is readable');
  assert.match(gantt.label,/Project Gantt/);
  assert.match(row.label,/Inspect a bounded task/);
  assert.equal(row.accessibilityInformation.label,row.label);
  assert.equal(provider.find('task-a:gantt-planned').label,
    'Planned relative interval: 0-100 ms; estimate 100 ms');
  assert.equal(provider.find('task-a:gantt-actual').label,
    'Actual interval: 20 ms from manager events (start +0 ms)');
  assert.match(shared.label,/Shared context \(operator;/);
  assert.equal(provider.find('live-context-shared:content:1').label,
    'Context 1/1: API contract agreed; tests pending.');
  assert.match(role.label,/developer context \(worker;/);
  assert.equal(provider.find('live-context-agent:developer:content:1').label,
    'Context 1/1: Own the API and contract tests.');
});

test('live tree preserves unknown timing and exposes every bounded context character', () => {
  const provider = new LiveProvider(vscode);
  const snapshot = liveV2Fixture();
  const note = 'x'.repeat(2048);
  snapshot.context.shared.content = note;
  snapshot.context.shared.digest = digest(note);
  const unsignedContext = {...snapshot.context};
  delete unsignedContext.digest;
  snapshot.context.digest = digest(unsignedContext);
  snapshot.gantt.plannedDurationMs = null;
  snapshot.gantt.plannedComplete = false;
  snapshot.gantt.actualOrigin = null;
  snapshot.gantt.actualDurationMs = null;
  Object.assign(snapshot.gantt.tasks[0], {
    estimateMs:null,plannedStartMs:null,plannedEndMs:null,actualStartOffsetMs:null,actualDurationMs:null
  });
  provider.show(sign(snapshot));
  assert.match(provider.find('task-a:gantt-planned').label,/unknown/);
  assert.equal(provider.find('task-a:gantt-actual').label,'Actual interval: unknown');
  const parts = Array.from({length:13},(_,index) =>
    provider.find(`live-context-shared:content:${index+1}`).label);
  assert.equal(parts[0].slice('Context 1/13: '.length).length,160);
  assert.equal(parts.map(part => part.replace(/^Context \d+\/\d+: /,'')).join(''),note);
});
