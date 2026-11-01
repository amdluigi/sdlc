'use strict';
// Run only in an isolated extension-development host, never the user's editor.
const vscode = require('vscode');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const {parseSnapshot} = require('../snapshot');
function gate() {
  let resolve;
  const promise = new Promise(done => {resolve = done;});
  return {promise,resolve};
}
async function bounded(promise) {
  let timer;
  try {
    return await Promise.race([promise,new Promise((_,reject) => {
      timer = setTimeout(() => reject(Error('Native refresh qualification timed out')),15000);
    })]);
  } finally {
    clearTimeout(timer);
  }
}
async function concurrentRefresh(api, root, file, original, taskId) {
  const reader = api.controller.reader;
  assert.equal(reader,require('../snapshot').readSnapshot,'Wrap the original real filesystem reader');
  const entries = Array.from({length:4},() => ({ready:gate(),release:gate()}));
  const running = [];
  let reads = 0;
  api.controller.reader = async (selectedRoot,selectedFile) => {
    const entry = entries[reads++];
    assert.ok(entry,'No extra filesystem reads may be dispatched');
    assert.equal(selectedRoot,root);
    assert.equal(selectedFile,file);
    try {entry.value = await reader(selectedRoot,selectedFile);}
    catch (error) {entry.error = error;}
    entry.ready.resolve();
    await entry.release.promise;
    if (entry.error) throw entry.error;
    return entry.value;
  };
  const refresh = () => {
    const command = vscode.commands.executeCommand('sdlc.execution.refreshSnapshot');
    running.push(command);
    return command;
  };
  try {
    await api.tree.reveal(api.provider.find(taskId),{select:true,focus:true});
    const first = refresh();
    await bounded(entries[0].ready.promise);
    assert.equal(api.provider.snapshot,null,'Loading must remove validated display data');
    assert.equal(api.controller.selection,null);
    assert.equal(api.controller.pendingSelection.root,root);
    assert.equal(api.controller.pendingSelection.file,file);
    assert.equal(api.controller.pendingSelection.binding.planDigest,entries[0].value.binding.planDigest);
    await api.tree.reveal(api.provider.getChildren()[0],{select:false,focus:false});
    await bounded((async () => {
      const deadline = Date.now()+15000;
      while (api.tree.selection.length) {
        if (Date.now() >= deadline) throw Error('Native loading selection did not invalidate');
        await new Promise(done => setTimeout(done,10));
      }
    })());
    const second = refresh();
    await bounded(entries[1].ready.promise);
    assert.equal(reads,2,'Overlapping registered commands must both perform real reads');
    assert.ok(entries[0].value && entries[1].value);
    assert.notEqual(entries[0].value,entries[1].value);
    entries[1].release.resolve();
    await bounded(second);
    const newest = api.provider.snapshot;
    assert.equal(newest,entries[1].value,'Only the newest real read may promote its result');
    assert.equal(api.controller.pendingSelection,null);
    assert.equal(api.tree.selection[0]?.id,taskId,'Retain the task through native loading-selection invalidation');
    entries[0].release.resolve();
    await bounded(first);
    assert.equal(api.provider.snapshot,newest,'Older completion cannot replace the newest result');
    assert.equal(api.tree.selection[0]?.id,taskId);

    const stale = refresh();
    await bounded(entries[2].ready.promise);
    await fs.writeFile(file,'{}');
    const failed = refresh();
    await bounded(entries[3].ready.promise);
    assert.ok(entries[2].value,'Older read must have consumed the valid real export');
    assert.ok(entries[3].error,'Newest read must reject the actually corrupted file');
    entries[3].release.resolve();
    await bounded(failed);
    assert.equal(api.provider.snapshot,null);
    assert.equal(api.controller.selection,null);
    assert.equal(api.controller.pendingSelection,null);
    assert.match(api.provider.getChildren()[0].label,/unavailable/);
    entries[2].release.resolve();
    await bounded(stale);
    assert.equal(api.provider.snapshot,null,'A late valid read cannot resurrect data after newest failure');
    assert.equal(api.controller.selection,null);
    assert.equal(api.controller.pendingSelection,null);
    assert.equal(reads,4);
    return {
      realReads:reads, overlapReads:2, loadingClearsDisplay:true,
      nativeLoadingSelectionInvalidated:true, newestResultPromoted:true,
      selectedTaskPreserved:true, staleSuccessIgnored:true,
      latestRealCorruptionClears:true, staleCompletionCannotResurrect:true
    };
  } finally {
    for (const entry of entries) entry.release.resolve();
    try {await bounded(Promise.allSettled(running));}
    finally {
      api.controller.reader = reader;
      await fs.writeFile(file,original);
    }
  }
}
exports.run = async function () {
  const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  assert.ok(root, 'Select the disposable qualification workspace');
  const extension = vscode.extensions.getExtension('sdlc.sdlc-dashboard');
  assert.ok(extension, 'Dashboard development extension must be loaded');
  assert.equal(extension.isActive,false,'Must remain inactive before explicit command');
  await vscode.commands.executeCommand('sdlc.execution.refreshSnapshot');
  assert.equal(extension.isActive,true);
  const commands = await vscode.commands.getCommands(true);
  assert.ok(commands.includes('sdlc.execution.openSnapshot'));
  assert.ok(commands.includes('sdlc.execution.refreshSnapshot'));
  const api = extension.exports;
  assert.equal(api.provider.snapshot,null);
  assert.match(api.provider.getChildren()[0].label,/No snapshot/);
  const file = path.join(root,'python-snapshot.json');
  const original = await fs.readFile(file);
  const value = parseSnapshot(original);
  assert.ok(value.tasks.some(t => t.title.includes('Ω 😀')));
  assert.equal(value.tasks[0].estimateMs,9223372036854775807n);
  assert.equal(await api.controller.load(root,file),true);
  assert.equal(api.tree.description,'Export, not live state');
  const task = api.provider.find('task:' + value.tasks[0].id);
  assert.equal(typeof task.tooltip,'string');
  assert.equal(task.command,undefined);
  assert.match(task.accessibilityInformation.label,/waiting/);
  await api.tree.reveal(task,{select:true,focus:true,expand:true});
  assert.equal(api.tree.visible,true);
  assert.equal(api.tree.selection[0].id,task.id);
  await vscode.commands.executeCommand('sdlc.execution.refreshSnapshot');
  assert.equal(api.tree.selection[0].id,task.id,'Retain task selection on refresh');
  assert.ok(api.provider.snapshot);
  const overlap = await concurrentRefresh(api,root,file,original,task.id);
  assert.equal(await api.controller.load(root,file),true);
  try {
    await fs.writeFile(file,'{"schemaVersion":1}');
    await vscode.commands.executeCommand('sdlc.execution.refreshSnapshot');
    assert.equal(api.provider.snapshot,null,'Failed reload must clear validated content');
    assert.equal(api.controller.selection,null);
    assert.match(api.provider.getChildren()[0].label,/unavailable/);
    assert.equal(await api.controller.load(root,path.join(root,'..','outside.json')),false);
    assert.equal(api.provider.snapshot,null);
  } finally {
    await fs.writeFile(file,original);
  }
  assert.equal(await api.controller.load(root,file),true);
  await api.tree.reveal(api.provider.find('task:' + value.tasks[0].id),{select:true,focus:true,expand:true});
  const evidence = {
    host:'Visual Studio Code', version:vscode.version, platform:process.platform,
    node:process.versions.node, electron:process.versions.electron || null,
    inactiveUntilCommand:true, fileTransport:true, nativeTreeView:true,
    literalUnicode:true, int64DigestParity:true, selectedRefresh:true,
    failedReloadClears:true, unconfinedRejected:true,
    concurrentRefresh:overlap,
    snapshotDigest:value.snapshotDigest
  };
  await fs.writeFile(path.join(root,'host-result.json'),JSON.stringify(evidence,null,2)+'\n');
};
