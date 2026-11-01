'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {fixture} = require('./fixture');
function hostSeam() {
  const commands = new Map(), dispatched = [], subscriptions = [];
  class Emitter {
    constructor() {this.listeners=[]; this.event=fn => {this.listeners.push(fn);return {dispose(){}};};}
    fire(value) {this.listeners.forEach(fn=>fn(value));}
    dispose() {}
  }
  const folder = {uri:{scheme:'file',fsPath:'selected-root',toString:()=> 'file:selected-root'}};
  const trees = [];
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
      async showWorkspaceFolderPick() {return folder;},
      async showOpenDialog() {return [{scheme:'file',fsPath:'selected-file'}];},
      createTreeView(id,options) {
        const tree = {id,options,selection:[],visible:true,dispose(){},
          async reveal(node,options){this.selection=[node];this.lastReveal=options;}};
        trees.push(tree);return tree;
      }
    }
  };
  const sandbox = {exports:{},require(name) {
    if(name==='vscode') return vscode;
    if(name==='./provider') return require('../provider');
    throw Error('Undeclared dependency');
  }};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'..','extension.js'),'utf8'),sandbox);
  const api = sandbox.exports.activate({subscriptions});
  api.controller.reader = async () => fixture();
  return {commands,dispatched,trees,vscode,api};
}
test('commands are closed, view is lazy and cancellation clears a previous success', async () => {
  const host = hostSeam();
  assert.deepEqual([...host.commands.keys()],['sdlc.execution.openSnapshot','sdlc.execution.refreshSnapshot']);
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
