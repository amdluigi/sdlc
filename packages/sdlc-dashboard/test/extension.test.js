'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {fixture, liveFixture, sign} = require('./fixture');
function hostSeam() {
  const commands = new Map(), dispatched = [], subscriptions = [], bridgeCalls = [], warnings = [], infos = [], timers = new Map();
  let failInspect = false;
  let mutateView = () => {};
  let actionGate = null;
  let timerId = 0;
  class Emitter {
    constructor() {this.listeners=[]; this.event=fn => {this.listeners.push(fn);return {dispose(){}};};}
    fire(value) {this.listeners.forEach(fn=>fn(value));}
    dispose() {}
  }
  const folder = {uri:{scheme:'file',fsPath:'selected-root',toString:()=> 'file:selected-root'}};
  const trees = [];
  async function bridge(root,request) {
    bridgeCalls.push({root,request});
    if (request.operation === 'list') return {operation:'list',executions:[{
      executionId:'feature-one',revision:1,counts:{accepted:0,total:1}
    }]};
    if (failInspect && request.operation === 'inspect') throw Error('manager unavailable');
    const snapshot = liveFixture();
    mutateView(snapshot);
    sign(snapshot);
    if (request.operation !== 'inspect') {
      if (actionGate) await actionGate;
      if (request.expectedBinding.controlsStateDigest !== snapshot.controlsStateDigest) {
        throw Error('E_EXECUTION_STALE_VIEW');
      }
    }
    return {operation:request.operation,view:snapshot};
  }
  const vscode = {
    EventEmitter:Emitter, ThemeIcon:class {constructor(id){this.id=id;}},
    TreeItem:class {constructor(label,state){this.label=label;this.collapsibleState=state;}},
    TreeItemCollapsibleState:{None:0,Collapsed:1,Expanded:2},
    workspace:{isTrusted:true,workspaceFolders:[folder]},
    commands:{
      registerCommand(id,fn) {commands.set(id,fn);return {dispose(){}};},
      async executeCommand(...args) {dispatched.push(args);}
    },
    window:{
      async showWarningMessage(...args) {warnings.push(args);return 'Confirm';},
      async showInformationMessage(...args) {infos.push(args);},
      async showInputBox() {return 'independent evidence';},
      async showWorkspaceFolderPick() {return folder;},
      async showOpenDialog() {return [{scheme:'file',fsPath:'selected-file'}];},
      async showQuickPick(items,options) {
        return options?.placeHolder?.startsWith('Filter') ? 'reported' : Array.isArray(items) ? items[0] : undefined;
      },
      createTreeView(id,options) {
        const visibilityListeners = [];
        const tree = {id,options,selection:[],visible:true,dispose(){},
          onDidChangeVisibility(listener) {
            visibilityListeners.push(listener);
            return {dispose(){}};
          },
          setVisible(visible) {
            this.visible=visible;
            visibilityListeners.forEach(listener=>listener({visible}));
          },
          async reveal(node,options){this.selection=[node];this.lastReveal=options;}};
        trees.push(tree);return tree;
      }
    }
  };
  const sandbox = {exports:{},process,
    setInterval(callback,delay) {const id=++timerId;timers.set(id,{callback,delay});return id;},
    clearInterval(id) {timers.delete(id);},
    require(name) {
    if(name==='vscode') return vscode;
    if(name==='./provider') return require('../provider');
    if(name==='./manager_provider') return require('../manager_provider');
    if(name==='./manager') return {requestManager:bridge};
    if(name==='./snapshot') return require('../snapshot');
    if(name==='node:path') return require('node:path');
    if(name==='node:crypto') return require('node:crypto');
    throw Error('Undeclared dependency');
  }};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'..','extension.js'),'utf8'),sandbox);
  const api = sandbox.exports.activate({subscriptions});
  api.controller.reader = async () => fixture();
  return {commands,dispatched,trees,vscode,api,bridgeCalls,warnings,timers,infos,
    setInspectFailure(value) {failInspect=value;},
    setView(value) {mutateView=value;},
    setActionGate(value) {actionGate=value;}};
}
test('commands are closed, view is lazy and cancellation clears a previous success', async () => {
  const host = hostSeam();
  assert.ok(host.commands.has('sdlc.execution.openSnapshot'));
  assert.ok(host.commands.has('sdlc.execution.refreshSnapshot'));
  assert.ok(host.commands.has('sdlc.execution.openLive'));
  assert.equal(host.trees.length,0);
  await host.commands.get('sdlc.execution.openSnapshot')();
  assert.ok(host.api.provider.snapshot);
  assert.equal(host.trees.length,1);
  assert.equal(host.dispatched.length,1);
  assert.deepEqual(Array.from(host.dispatched[0]),['setContext','sdlc.execution.snapshotOpened',true]);
  host.vscode.window.showOpenDialog = async () => undefined;
  await host.commands.get('sdlc.execution.openSnapshot')();
  assert.equal(host.api.provider.snapshot,null);
  assert.equal(host.api.controller.selection,null);
});
test('opening manager view performs one read-only inspection and never enables polling or dispatch', async () => {
  const host = hostSeam();
  assert.equal(host.trees.length,0);
  await host.commands.get('sdlc.execution.openLive')();
  assert.equal(host.api.liveController.selection.executionId,'feature-one');
  assert.equal(host.trees.length,1);
  assert.deepEqual(host.bridgeCalls.map(call=>call.request.operation),['list','inspect']);
  assert.equal(host.bridgeCalls.some(call=>call.request.operation.includes('dispatch')),false);
  await host.commands.get('sdlc.execution.filterLiveTasks')();
  assert.equal(host.api.liveProvider.filter,'reported');
  assert.ok(host.api.liveProvider.find('live-task:task-a'));
  await host.commands.get('sdlc.execution.refreshLive')();
  assert.deepEqual(host.bridgeCalls.map(call=>call.request.operation),['list','inspect','inspect']);
  await host.commands.get('sdlc.execution.startLiveUpdates')();
  assert.equal(host.timers.size,1);
  assert.equal(host.timers.values().next().value.delay,3000);
  assert.deepEqual(host.bridgeCalls.map(call=>call.request.operation),['list','inspect','inspect']);
  host.timers.values().next().value.callback();
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(host.bridgeCalls.map(call=>call.request.operation),['list','inspect','inspect','inspect']);
  await host.commands.get('sdlc.execution.stopLiveUpdates')();
  assert.equal(host.timers.size,0);
});
test('hiding the manager view stops polling until the user explicitly starts it again', async () => {
  const host = hostSeam();
  await host.commands.get('sdlc.execution.openLive')();
  await host.commands.get('sdlc.execution.startLiveUpdates')();
  assert.equal(host.timers.size,1);
  host.api.liveTree.setVisible(false);
  assert.equal(host.timers.size,0);
  host.api.liveTree.setVisible(true);
  assert.equal(host.timers.size,0);
  await host.commands.get('sdlc.execution.startLiveUpdates')();
  assert.equal(host.timers.size,1);
});
test('changing manager selection or losing a refresh stops its existing polling consent', async () => {
  const host = hostSeam();
  await host.commands.get('sdlc.execution.openLive')();
  await host.commands.get('sdlc.execution.startLiveUpdates')();
  assert.equal(host.timers.size,1);
  await host.commands.get('sdlc.execution.openLive')();
  assert.equal(host.timers.size,0);
  await host.commands.get('sdlc.execution.startLiveUpdates')();
  host.setInspectFailure(true);
  await host.commands.get('sdlc.execution.refreshLive')();
  assert.equal(host.timers.size,0);
  assert.equal(host.api.liveController.selection,null);
});
test('accept command requires independent user evidence and confirms the exact task action', async () => {
  const host = hostSeam();
  await host.commands.get('sdlc.execution.openLive')();
  const task = host.api.liveProvider.find('live-task:task-a');
  host.api.liveTree.selection = [task];
  await host.commands.get('sdlc.execution.acceptTask')();
  const request = host.bridgeCalls.at(-1).request;
  assert.equal(request.operation,'accept');
  assert.equal(request.acceptance.taskId,'task-a');
  assert.equal(request.acceptance.revision,'independent evidence');
  assert.match(request.confirmationDigest,/^sha256:[0-9a-f]{64}$/);
  assert.ok(host.warnings.some(args=>String(args[0]).includes('Confirm accept')));
  const confirmation = host.warnings.find(args=>args[1]?.modal);
  assert.match(confirmation[1].detail,/Task task-a, attempt attempt-a, result result-a/);
  assert.match(confirmation[1].detail,/Verification command: independent evidence/);
});
function pendingModal(host) {
  const modal = {};
  host.vscode.window.showWarningMessage = (...args) => {
    host.warnings.push(args);
    if (!args[1]?.modal) return Promise.resolve();
    return new Promise(resolve => {modal.confirm=resolve;});
  };
  return modal;
}
const settle = () => new Promise(resolve=>setImmediate(resolve));
const inspections = host => host.bridgeCalls.filter(call=>call.request.operation === 'inspect').length;
test('unchanged live polls and refreshes while a confirmation is open do not invalidate it', async () => {
  const host = hostSeam();
  await host.commands.get('sdlc.execution.openLive')();
  await host.commands.get('sdlc.execution.startLiveUpdates')();
  host.api.liveTree.selection = [host.api.liveProvider.find('live-task:task-a')];
  const modal = pendingModal(host);
  const accepting = host.commands.get('sdlc.execution.acceptTask')();
  await settle();
  assert.equal(typeof modal.confirm,'function');
  const before = inspections(host);
  host.timers.values().next().value.callback();
  await host.commands.get('sdlc.execution.refreshLive')();
  await settle();
  assert.equal(inspections(host),before,'polling and refresh are suspended while the modal is open');
  modal.confirm('Confirm');
  await accepting;
  const accepted = host.bridgeCalls.filter(call=>call.request.operation === 'accept');
  assert.equal(accepted.length,1);
  assert.deepEqual(host.infos.map(args=>args[0]).filter(text=>/Manager action/.test(text)),
    ['Manager action recorded: accept']);
  assert.equal(host.warnings.filter(args=>!args[1]?.modal).length,0);
  assert.equal(host.timers.size,1,'previously enabled polling resumes for the visible view');
  assert.equal(inspections(host),before + 1,'resumption performs one actual current refresh');
});
test('real manager state change during confirmation is rejected by the manager and refreshed', async () => {
  const host = hostSeam();
  await host.commands.get('sdlc.execution.openLive')();
  const modal = pendingModal(host);
  const pausing = host.commands.get('sdlc.execution.togglePause')();
  await settle();
  host.setView(view => {view.controls.paused = true; view.controlsStateDigest = 'sha256:' + 'f'.repeat(64);});
  modal.confirm('Confirm');
  assert.equal(await pausing,undefined);
  assert.ok(host.warnings.some(args=>/E_EXECUTION_STALE_VIEW/.test(String(args[0]))));
  assert.equal(host.infos.some(args=>/Manager action recorded/.test(String(args[0]))),false);
  assert.equal(host.api.liveController.selection.snapshot.controlsStateDigest,'sha256:' + 'f'.repeat(64));
});
test('real state change during nested acceptance confirmation is still refreshed after rejection', async () => {
  const host = hostSeam();
  await host.commands.get('sdlc.execution.openLive')();
  host.api.liveTree.selection = [host.api.liveProvider.find('live-task:task-a')];
  const modal = pendingModal(host);
  const accepting = host.commands.get('sdlc.execution.acceptTask')();
  await settle();
  host.setView(view => {view.controlsStateDigest = 'sha256:' + 'f'.repeat(64);});
  modal.confirm('Confirm');
  await accepting;
  assert.ok(host.warnings.some(args=>/E_EXECUTION_STALE_VIEW/.test(String(args[0]))));
  assert.equal(host.infos.some(args=>/Manager action recorded/.test(String(args[0]))),false);
  assert.equal(host.api.liveController.suspended,0);
  assert.equal(host.api.liveController.selection.snapshot.controlsStateDigest,'sha256:' + 'f'.repeat(64));
});
test('changing the manager selection during confirmation invalidates the action', async () => {
  const host = hostSeam();
  await host.commands.get('sdlc.execution.openLive')();
  const modal = pendingModal(host);
  const approving = host.commands.get('sdlc.execution.approvePlan')();
  await settle();
  host.vscode.window.showWarningMessage = async (...args) => {host.warnings.push(args);};
  await host.commands.get('sdlc.execution.openLive')();
  modal.confirm('Confirm');
  await approving;
  assert.equal(host.bridgeCalls.some(call=>call.request.operation === 'approve-plan'),false);
  assert.ok(host.warnings.some(args=>/selection changed/i.test(String(args[0]))));
});
test('a poll racing a successful manager write never reports a false failure', async () => {
  const host = hostSeam();
  await host.commands.get('sdlc.execution.openLive')();
  await host.commands.get('sdlc.execution.startLiveUpdates')();
  let release;
  host.setActionGate(new Promise(resolve => {release=resolve;}));
  const pausing = host.commands.get('sdlc.execution.togglePause')();
  await settle();
  const before = inspections(host);
  host.timers.values().next().value.callback();
  await host.commands.get('sdlc.execution.refreshLive')();
  await settle();
  assert.equal(inspections(host),before,'no poll runs while the confirmed mutation is in flight');
  release();
  await pausing;
  assert.ok(host.infos.some(args=>String(args[0]) === 'Manager action recorded: pause'));
  assert.equal(host.warnings.filter(args=>!args[1]?.modal).length,0);
});
test('hiding the view during confirmation keeps polling off after the action', async () => {
  const host = hostSeam();
  await host.commands.get('sdlc.execution.openLive')();
  await host.commands.get('sdlc.execution.startLiveUpdates')();
  const modal = pendingModal(host);
  const approving = host.commands.get('sdlc.execution.approvePlan')();
  await settle();
  host.api.liveTree.setVisible(false);
  modal.confirm('Confirm');
  await approving;
  assert.equal(host.bridgeCalls.filter(call=>call.request.operation === 'approve-plan').length,1);
  assert.equal(host.timers.size,0);
});
test('live update state is described as soon as polling starts or stops', async () => {
  const host = hostSeam();
  await host.commands.get('sdlc.execution.openLive')();
  assert.match(host.api.liveTree.description,/updates off/);
  await host.commands.get('sdlc.execution.startLiveUpdates')();
  assert.match(host.api.liveTree.description,/live updates on/);
  await host.commands.get('sdlc.execution.stopLiveUpdates')();
  assert.match(host.api.liveTree.description,/updates off/);
});
test('batch results are accepted only through bound independent validation', async () => {
  const host = hostSeam();
  await host.commands.get('sdlc.execution.openLive')();
  host.api.liveTree.selection = [host.api.liveProvider.find('live-task:task-a')];
  assert.ok(host.api.liveProvider.find('task-a:result-digest'));
  await host.commands.get('sdlc.execution.acceptTask')();
  const request = host.bridgeCalls.at(-1).request;
  assert.equal(request.acceptance.schemaVersion,2);
  assert.equal(request.acceptance.resultDigest,'sha256:' + 'e'.repeat(64));
  const detail = host.warnings.find(args=>args[1]?.modal)[1].detail;
  assert.match(detail,new RegExp('Result digest: sha256:' + 'e'.repeat(64)));
  assert.match(detail,/independent operator validation; worker verification is not treated as passed/);
});
test('confirmation shows full current digests and exact selected action context', async () => {
  const host = hostSeam();
  await host.commands.get('sdlc.execution.openLive')();
  const snapshot = host.api.liveController.selection.snapshot;
  const digests = [snapshot.planDigest,snapshot.policyDigest,snapshot.controlsDigest,snapshot.controlsStateDigest];
  const context = [
    'Project: selected-root',`Execution: ${snapshot.binding.executionId}`,
    `Plan revision: ${snapshot.binding.planRevision}`
  ];
  const detailFor = operation => host.warnings.filter(args=>args[1]?.modal && String(args[0]).includes(operation)).at(-1)[1].detail;
  await host.commands.get('sdlc.execution.approveControls')();
  host.api.liveTree.selection = [host.api.liveProvider.find('live-task:task-a')];
  await host.commands.get('sdlc.execution.cancelTask')();
  host.api.liveTree.selection = [host.api.liveProvider.find('live-task:task-a')];
  await host.commands.get('sdlc.execution.acceptTask')();
  for (const operation of ['approve-controls','cancel','accept']) {
    const detail = detailFor(operation);
    for (const value of [...digests,...context]) assert.ok(typeof value === 'string' && detail.includes(value),
      `${operation} confirmation must show ${value}`);
    assert.match(detail,new RegExp(`Plan digest: ${snapshot.planDigest}`));
    assert.match(detail,new RegExp(`Execution policy digest: ${snapshot.policyDigest}`));
    assert.match(detail,new RegExp(`Controls policy digest: ${snapshot.controlsDigest}`));
    assert.match(detail,new RegExp(`Controls state digest: ${snapshot.controlsStateDigest}`));
    assert.doesNotMatch(detail,/…/);
  }
  assert.match(detailFor('cancel'),/Task task-a, attempt attempt-a; records intent only/);
  assert.match(detailFor('accept'),/Task task-a, attempt attempt-a, result result-a/);
});
test('view description follows data recovery rather than retaining an error heading', async () => {
  const host = hostSeam();
  await host.commands.get('sdlc.execution.refreshSnapshot')();
  assert.equal(host.api.provider.snapshot,null);
  await host.commands.get('sdlc.execution.openSnapshot')();
  assert.equal(host.api.tree.description,'Export, not live state');
  host.api.controller.reader = async () => {throw Error('failure');};
  await host.commands.get('sdlc.execution.refreshSnapshot')();
  assert.equal(host.api.tree.description,'No valid snapshot');
});
test('concurrent explicit commands create one tree and removed workspace clears state', async () => {
  const host = hostSeam();
  await Promise.all([host.commands.get('sdlc.execution.refreshSnapshot')(),host.commands.get('sdlc.execution.openSnapshot')()]);
  assert.equal(host.trees.length,1);
  host.vscode.workspace.workspaceFolders = [];
  await host.commands.get('sdlc.execution.refreshSnapshot')();
  assert.equal(host.api.provider.snapshot,null);
});
test('overlapping refresh commands preserve the selected task through loading invalidation', async () => {
  const host = hostSeam();
  await host.commands.get('sdlc.execution.openSnapshot')();
  const task = host.api.provider.find('task:task-a');
  await host.api.tree.reveal(task,{select:true});
  const reads = [];
  host.api.controller.reader = () => new Promise(resolve => reads.push(resolve));
  const first = host.commands.get('sdlc.execution.refreshSnapshot')();
  host.api.tree.selection = [];
  const second = host.commands.get('sdlc.execution.refreshSnapshot')();
  reads[1](fixture());
  await second;
  assert.equal(host.api.tree.selection[0].id,task.id);
  reads[0](fixture());
  await first;
  assert.equal(host.api.tree.selection[0].id,task.id);
});
test('refresh rechecks a pending source against the currently open workspace', async () => {
  const host = hostSeam();
  await host.commands.get('sdlc.execution.openSnapshot')();
  const reads = [];
  host.api.controller.reader = () => new Promise(resolve => reads.push(resolve));
  const first = host.commands.get('sdlc.execution.refreshSnapshot')();
  host.vscode.workspace.workspaceFolders = [];
  const second = host.commands.get('sdlc.execution.refreshSnapshot')();
  assert.equal(reads.length,1);
  await second;
  assert.equal(host.api.provider.snapshot,null);
  assert.equal(host.api.controller.pendingSelection,null);
  reads[0](fixture());
  await first;
  assert.equal(host.api.provider.snapshot,null);
});
