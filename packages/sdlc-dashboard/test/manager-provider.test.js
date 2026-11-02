'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {LiveProvider,LiveController} = require('../manager_provider');
const {liveFixture,acceptedLiveFixture} = require('./fixture');

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
