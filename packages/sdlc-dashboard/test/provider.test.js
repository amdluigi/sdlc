'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {fixture, acceptedSnapshotFixture} = require('./fixture');
class Emitter {
  constructor() {this.event = () => ({dispose(){}}); this.fired = 0;}
  fire() {this.fired++;}
  dispose() {}
}
const vscode = {
  EventEmitter: Emitter, TreeItemCollapsibleState: {None:0,Collapsed:1,Expanded:2},
  TreeItem: class {constructor(label,state) {this.label=label; this.collapsibleState=state;}},
  ThemeIcon: class {constructor(id){this.id=id;}}
};
test('provider preserves literal labels, explicit unknowns and accessible read-only states', () => {
  const {SnapshotProvider} = require('../provider');
  const provider = new SnapshotProvider(vscode);
  assert.match(provider.getChildren()[0].label, /No snapshot/);
  provider.show(fixture());
  const nodes = provider.getChildren();
  const taskGroup = nodes.find(n => n.id === 'tasks');
  const task = provider.getChildren(taskGroup)[0];
  assert.match(task.label, /Plain <script> Ω 😀/);
  assert.match(task.accessibilityInformation.label, /waiting/);
  assert.equal(task.command, undefined);
  assert.equal(typeof task.tooltip, 'string');
  const details = provider.getChildren(task);
  assert.ok(details.some(n => /Recorded interval: unknown/.test(n.label)));
  assert.ok(nodes.some(n => /not verified/.test(n.label)));
  assert.equal(provider.getParent(task), taskGroup);
  provider.fail('Snapshot unavailable');
  assert.equal(provider.getChildren().length, 1);
  assert.match(provider.getChildren()[0].label, /unavailable/);
  assert.equal(provider.snapshot, null);
});
test('reload invalidates success immediately and only newest request may commit', async () => {
  const {SnapshotProvider, SnapshotController} = require('../provider');
  const provider = new SnapshotProvider(vscode);
  let finish;
  const controller = new SnapshotController(provider, () => new Promise(resolve => {finish=resolve;}));
  const first = controller.load('root', 'file');
  assert.match(provider.getChildren()[0].label, /Loading/);
  controller.clear('No snapshot selected');
  finish(fixture()); await first;
  assert.equal(provider.snapshot, null);
  assert.equal(controller.selection, null);
  const good = new SnapshotController(provider, async () => fixture());
  await good.load('root','file');
  assert.equal(provider.snapshot.binding.executionId, 'example');
  good.reader = async () => {throw Error('raw-secret-file-name');};
  await good.refresh();
  assert.equal(provider.snapshot, null);
  assert.doesNotMatch(provider.getChildren()[0].label, /raw-secret/);
  assert.equal(good.selection, null);
});
test('bounded long titles cannot truncate the accessible state prefix', () => {
  const {SnapshotProvider} = require('../provider');
  const provider = new SnapshotProvider(vscode);
  const value = fixture(); value.tasks[0].title = '😀'.repeat(2048); value.tasks[0].status = 'failed';
  provider.show(value);
  const item = provider.find('task:task-a');
  assert.ok(Array.from(item.label).length <= 180);
  assert.match(item.label,/^task-a \(failed\):/);
  assert.match(item.accessibilityInformation.label,/^task-a \(failed\):/);
  assert.match(item.tooltip,/^State: failed/);
});
test('overlapping refreshes retain their source and only the newest result survives', async () => {
  const {SnapshotProvider, SnapshotController} = require('../provider');
  const provider = new SnapshotProvider(vscode);
  const controller = new SnapshotController(provider, async () => fixture());
  await controller.load('root','file');
  const reads = [];
  controller.reader = (root,file) => new Promise((resolve,reject) => reads.push({root,file,resolve,reject}));
  const first = controller.refresh();
  const second = controller.refresh();
  assert.equal(reads.length,2);
  assert.equal(provider.snapshot,null);
  assert.equal(controller.selection,null);
  assert.deepEqual(reads.map(({root,file}) => ({root,file})), [
    {root:'root',file:'file'}, {root:'root',file:'file'}
  ]);
  reads[1].resolve(fixture());
  assert.equal(await second,true);
  reads[0].reject(Error('obsolete failure'));
  assert.equal(await first,false);
  assert.ok(provider.snapshot);
  assert.equal(controller.selection.file,'file');
  assert.equal(controller.pendingSelection,null);
  controller.reader = (root,file) => new Promise(resolve => reads.push({root,file,resolve}));
  const cancelled = controller.refresh();
  controller.clear('Cancelled');
  reads[2].resolve(fixture());
  assert.equal(await cancelled,false);
  assert.equal(provider.snapshot,null);
  assert.equal(controller.selection,null);
  assert.equal(controller.pendingSelection,null);
});
test('export provider shows recorded acceptance provenance without claiming worker verification passed', () => {
  const {SnapshotProvider} = require('../provider');
  const provider = new SnapshotProvider(vscode);
  provider.show(acceptedSnapshotFixture());
  const [accepted, waiting] = provider.getChildren(provider.getChildren().find(n => n.id === 'tasks'));
  const basis = provider.getChildren(accepted).find(n => n.id === 'task-a:acceptance-basis');
  assert.equal(basis.label, 'Acceptance basis: independent operator validation; worker verification not treated as passed');
  assert.match(basis.accessibilityInformation.label, /independent operator validation/);
  assert.equal(provider.getChildren(waiting).some(n => /acceptance-basis/.test(n.id)), false);
  provider.show(fixture());
  const legacy = provider.getChildren(provider.getChildren().find(n => n.id === 'tasks'))[0];
  assert.equal(provider.getChildren(legacy).some(n => /acceptance-basis/.test(n.id)), false);
});
