'use strict';
const vscode = require('vscode');
const path = require('node:path');
const {SnapshotProvider, SnapshotController} = require('./provider');
const {LiveProvider, LiveController, STATUSES, confirmationMaterial, digestOf} = require('./manager_provider');
const {requestManager} = require('./manager');
const VIEW = 'sdlc.execution.snapshot';
const LIVE_VIEW = 'sdlc.execution.manager';
function activate(context) {
  const provider = new SnapshotProvider(vscode);
  const controller = new SnapshotController(provider);
  const liveProvider = new LiveProvider(vscode);
  const liveController = new LiveController(liveProvider,requestManager);
  let tree;
  let liveTree;
  let creating;
  let liveCreating;
  let liveTimer;
  let livePollPending = false;
  let commandSerial = 0;
  let liveCommandSerial = 0;
  let refreshSelectionId;
  function describeLive() {
    if (!liveTree) return;
    liveTree.description = liveController.selection
      ? (liveTimer ? 'Current manager state · live updates on' : 'Current manager state · updates off')
      : 'No manager execution selected';
  }
  function stopLivePolling() {
    if (liveTimer) clearInterval(liveTimer);
    liveTimer = undefined;
    liveController.invalidate();
    describeLive();
  }
  // Holds polling for a whole confirmation or mutation; afterwards only a still-enabled, visible poller
  // resumes, and only after one actual current refresh.
  let refreshAfterSuspension = false;
  async function withSuspendedPolling(work) {
    liveController.suspend();
    try {
      return await work();
    } finally {
      liveController.resume();
      if (!liveController.suspended) {
        const rejected = refreshAfterSuspension;
        refreshAfterSuspension = false;
        if (liveController.selection && (rejected || (!livePollPending && liveTimer && liveTree?.visible))) {
          livePollPending = true;
          try {await refreshLiveSelection();} finally {livePollPending = false;}
        }
      }
    }
  }
  async function view() {
    if (!tree) {
      if (!creating) creating = (async () => {
        await vscode.commands.executeCommand('setContext','sdlc.execution.snapshotOpened',true);
        tree = vscode.window.createTreeView(VIEW,{treeDataProvider:provider,showCollapseAll:false,canSelectMany:false});
        const describe = () => {tree.description = provider.snapshot ? 'Export, not live state' : 'No valid snapshot';};
        describe();
        context.subscriptions.push(tree,provider.onDidChangeTreeData(describe));
      })();
      await creating;
    }
    return tree;
  }
  async function liveView() {
    if (!liveTree) {
      if (!liveCreating) liveCreating = (async () => {
        await vscode.commands.executeCommand('setContext','sdlc.execution.managerOpened',true);
        liveTree = vscode.window.createTreeView(LIVE_VIEW,{
          treeDataProvider:liveProvider,showCollapseAll:false,canSelectMany:false
        });
        context.subscriptions.push(liveTree,liveProvider.onDidChangeTreeData(describeLive));
        context.subscriptions.push(liveTree.onDidChangeVisibility(({visible}) => {
          if (!visible) stopLivePolling();
          describeLive();
        }));
      })();
      await liveCreating;
    }
    return liveTree;
  }
  const workspaceChange = vscode.workspace.onDidChangeWorkspaceFolders?.(() => {
    if (liveController.selection && !localRootOpen(liveController.selection.root)) {
      stopLivePolling();
      liveController.clear('Selected project was removed from the trusted workspace');
    }
  });
  if (workspaceChange) context.subscriptions.push(workspaceChange);
  function localWorkspace(folder) {
    return Boolean(folder && folder.uri.scheme === 'file' &&
      vscode.workspace.isTrusted &&
      (vscode.workspace.workspaceFolders || []).some(item => item.uri.toString() === folder.uri.toString()));
  }
  function localRootOpen(root) {
    const comparable = value => process.platform === 'win32' ? value.toLowerCase() : value;
    return vscode.workspace.isTrusted && (vscode.workspace.workspaceFolders || []).some(item =>
      item.uri.scheme === 'file' && comparable(path.resolve(item.uri.fsPath)) === comparable(path.resolve(root)));
  }
  async function selectLiveExecution() {
    const serial = ++liveCommandSerial;
    stopLivePolling();
    await liveView();
    liveController.clear('Selecting a project and execution; live updates remain off');
    if (!vscode.workspace.isTrusted) {
      vscode.window.showWarningMessage('A trusted local workspace is required for the manager view');
      return;
    }
    const folder = await vscode.window.showWorkspaceFolderPick({
      placeHolder:'Choose the local project whose managed executions you want to inspect'
    });
    if (serial !== liveCommandSerial) return;
    if (!localWorkspace(folder)) {
      liveController.clear('No current local project selected');
      return;
    }
    let response;
    try {response = await requestManager(folder.uri.fsPath,{operation:'list'});}
    catch (error) {
      liveController.clear('No readable manager executions in the selected project');
      vscode.window.showWarningMessage(error.message);
      return;
    }
    if (serial !== liveCommandSerial) return;
    const executions = response.executions || [];
    if (!executions.length) {
      liveController.clear('Selected project has no managed execution records');
      vscode.window.showInformationMessage('No managed executions were found in this project');
      return;
    }
    const selected = await vscode.window.showQuickPick(executions.map(item => ({
      label:item.executionId, description:`revision ${item.revision}`,
      detail:`${item.counts.accepted}/${item.counts.total} tasks independently accepted`
    })),{placeHolder:'Select one manager-owned execution; no workers or polling will start'});
    if (serial !== liveCommandSerial) return;
    if (!selected) {
      liveController.clear('No manager execution selected');
      return;
    }
    if (!localWorkspace(folder)) {
      liveController.clear('Selected project is no longer open and trusted');
      return;
    }
    await liveController.load(folder.uri.fsPath,selected.label);
    if (serial === liveCommandSerial) await liveView();
  }
  async function refreshLiveSelection() {
    const refreshed = await liveController.refresh();
    if (!liveController.selection) stopLivePolling();
    return refreshed;
  }
  async function confirmAction(operation, extra = {}, selection = liveController.selection) {
    const snapshot = selection?.snapshot;
    if (!selection || !snapshot) {
      vscode.window.showWarningMessage('Open a current manager execution first');
      return false;
    }
    const shown = value => value || 'not configured';
    const detail = [
      `Operation: ${operation}`,`Project: ${selection.root}`,`Execution: ${snapshot.binding.executionId}`,
      `Plan revision: ${snapshot.binding.planRevision}`,`Plan digest: ${snapshot.planDigest}`,
      `Execution policy digest: ${snapshot.policyDigest}`,
      `Controls policy digest: ${shown(snapshot.controlsDigest)}`,
      `Controls state digest: ${shown(snapshot.controlsStateDigest)}`
    ];
    if (operation === 'accept') {
      detail.push(
        `Task ${extra.acceptance.taskId}, attempt ${extra.acceptance.attemptId}, result ${extra.acceptance.resultId}`,
        ...(extra.acceptance.schemaVersion === 2 ? [
          `Result digest: ${extra.acceptance.resultDigest}`,
          'Acceptance basis: independent operator validation; worker verification is not treated as passed'
        ] : ['Acceptance basis: worker-reported evidence checked against your independent judgment']),
        `Independently checked revision: ${extra.acceptance.revision}`,
        `Verification command: ${extra.acceptance.command}`,
        `Verification result: ${extra.acceptance.summary}`
      );
    } else if (operation === 'cancel') {
      detail.push(`Task ${extra.taskId}, attempt ${extra.attemptId}; records intent only`);
    }
    const pin = liveController.pin(operation,extra,selection);
    const digest = digestOf(confirmationMaterial(operation,selection,extra));
    const answer = await vscode.window.showWarningMessage(
      `Confirm ${operation} for ${snapshot.binding.executionId}?`,
      {modal:true,detail:`${detail.join('\n')}\nConfirmation digest: ${digest}`},'Confirm'
    );
    return answer === 'Confirm' ? pin : false;
  }
  function action(operation, extra = {}) {
    return withSuspendedPolling(async () => {
      if (liveController.selection && !localRootOpen(liveController.selection.root)) {
        stopLivePolling();
        liveController.clear('Selected project is no longer open and trusted');
        vscode.window.showWarningMessage('Select a current trusted local project before acting');
        return false;
      }
      const confirmedPin = await confirmAction(operation,extra,liveController.selection);
      if (!confirmedPin) return false;
      let outcome;
      try {
        outcome = await liveController.action(operation,extra,confirmedPin);
      } catch (error) {
        vscode.window.showWarningMessage(error.message);
        refreshAfterSuspension = true;
        return false;
      }
      vscode.window.showInformationMessage(outcome.view
        ? `Manager action recorded: ${operation}`
        : `Manager action recorded: ${operation}; the selection changed, so refresh to view it`);
      return true;
    });
  }
  function selectedTask() {
    const id = liveTree?.selection?.[0]?.id || '';
    const match = /^live-task:([a-z0-9]+(?:-[a-z0-9]+)*)$/.exec(id);
    if (!match || !liveController.selection) return null;
    return liveController.selection.snapshot.tasks.find(task => task.id === match[1]) || null;
  }
  function collectAcceptance() {
    return withSuspendedPolling(collectSuspendedAcceptance);
  }
  async function collectSuspendedAcceptance() {
    const task = selectedTask();
    if (!task || task.status !== 'reported' || !task.resultId || !task.attemptId || !task.acceptanceSchemaVersion) {
      vscode.window.showWarningMessage('Select a reported task with a manager-recorded result');
      return;
    }
    const revision = await vscode.window.showInputBox({
      prompt:'Enter the revision you independently checked',ignoreFocusOut:true
    });
    if (!revision) return;
    const command = await vscode.window.showInputBox({
      prompt:'Enter the verification command you independently ran',ignoreFocusOut:true
    });
    if (!command) return;
    const summary = await vscode.window.showInputBox({
      prompt:'Summarize your independent verification result',ignoreFocusOut:true
    });
    if (!summary) return;
    const binding = task.acceptanceSchemaVersion === 2
      ? {schemaVersion:2,taskId:task.id,attemptId:task.attemptId,resultId:task.resultId,resultDigest:task.resultDigest}
      : {schemaVersion:1,taskId:task.id,attemptId:task.attemptId,resultId:task.resultId};
    await action('accept',{acceptance:{
      ...binding,acceptanceCriteria:task.acceptanceCriteria,revision,command,summary
    }});
  }
  async function cancelSelectedTask() {
    const task = selectedTask();
    if (!task || !task.attemptId || !['running','blocked','reported'].includes(task.status)) {
      vscode.window.showWarningMessage('Select unresolved work with a manager-recorded attempt');
      return;
    }
    if (await action('cancel',{taskId:task.id,attemptId:task.attemptId})) {
      vscode.window.showWarningMessage('Cancellation intent was recorded; this host cannot be stopped remotely');
    }
  }
  async function togglePause() {
    const snapshot = liveController.selection?.snapshot;
    if (!snapshot) return vscode.window.showWarningMessage('Open a current manager execution first');
    if (!snapshot.controls.enabled) return vscode.window.showWarningMessage('Execution controls are disabled');
    await action(snapshot.controls.paused ? 'resume' : 'pause');
  }
  async function reveal(id, focus) {
    const current = await view();
    const node = provider.find(id) || provider.getChildren()[0];
    try {await current.reveal(node,{select:true,focus,expand:false});}
    catch { /* A hidden or disposed view must not change validation state. */ }
  }
  context.subscriptions.push(provider,
    vscode.commands.registerCommand('sdlc.execution.openSnapshot',async () => {
      const serial = ++commandSerial;
      refreshSelectionId = undefined;
      controller.clear('Selecting snapshot; no current data');
      await view();
      if (!vscode.workspace.isTrusted) {controller.clear('Trusted local workspace required'); return;}
      const folder = await vscode.window.showWorkspaceFolderPick({placeHolder:'Choose the local workspace that confines the snapshot'});
      if (serial !== commandSerial) return;
      if (!folder || folder.uri.scheme !== 'file') {controller.clear('No local workspace selected'); return;}
      const selected = await vscode.window.showOpenDialog({
        title:'Select an exported execution snapshot inside this workspace',
        defaultUri:folder.uri, canSelectFiles:true, canSelectFolders:false, canSelectMany:false,
        filters:{'Execution snapshot JSON':['json']}, openLabel:'Read snapshot'
      });
      if (serial !== commandSerial) return;
      if (!selected || selected.length !== 1 || selected[0].scheme !== 'file') {
        controller.clear('No local snapshot selected'); return;
      }
      if (!(vscode.workspace.workspaceFolders || []).some(f => f.uri.toString() === folder.uri.toString())) {
        controller.clear('Selected workspace is no longer open'); return;
      }
      await controller.load(folder.uri.fsPath,selected[0].fsPath);
      if (serial === commandSerial) await reveal('binding',true);
    }),
    vscode.commands.registerCommand('sdlc.execution.refreshSnapshot',async () => {
      const serial = ++commandSerial;
      const selectedId = tree?.selection[0]?.id || refreshSelectionId;
      refreshSelectionId = selectedId;
      const selected = controller.pendingSelection || controller.selection;
      if (!vscode.workspace.isTrusted || (selected && !(vscode.workspace.workspaceFolders || []).some(
        f => f.uri.scheme === 'file' && f.uri.fsPath === selected.root
      ))) {
        controller.clear('Selected trusted workspace is no longer available');
      } else await controller.refresh();
      if (serial === commandSerial) {
        await reveal(selectedId,false);
        if (serial === commandSerial) refreshSelectionId = undefined;
      }
    }),
    vscode.commands.registerCommand('sdlc.execution.openLive',selectLiveExecution),
    vscode.commands.registerCommand('sdlc.execution.refreshLive',async () => {
      if (!liveController.selection) return selectLiveExecution();
      if (!localRootOpen(liveController.selection.root)) {
        stopLivePolling();
        liveController.clear('Selected trusted project is no longer open');
        return;
      }
      await refreshLiveSelection();
    }),
    vscode.commands.registerCommand('sdlc.execution.startLiveUpdates',async () => {
      if (!liveController.selection) return selectLiveExecution();
      if (!localRootOpen(liveController.selection.root)) {
        stopLivePolling();
        liveController.clear('Selected trusted project is no longer open');
        return;
      }
      if (!liveTree?.visible) {
        vscode.window.showWarningMessage('Show the selected manager view before enabling live updates');
        return;
      }
      if (liveTimer) clearInterval(liveTimer);
      liveTimer = setInterval(() => {
        if (livePollPending || liveController.suspended) return;
        if (!localRootOpen(liveController.selection?.root)) {
          stopLivePolling();
          liveController.clear('Workspace trust was revoked or the project was closed');
          return;
        }
        livePollPending = true;
        void refreshLiveSelection().finally(() => {livePollPending=false;});
      },3000);
      describeLive();
      vscode.window.showInformationMessage('Live manager updates enabled for the selected execution');
    }),
    vscode.commands.registerCommand('sdlc.execution.stopLiveUpdates',() => {
      stopLivePolling();
      vscode.window.showInformationMessage('Live manager updates stopped');
    }),
    vscode.commands.registerCommand('sdlc.execution.filterLiveTasks',async () => {
      const selected = await vscode.window.showQuickPick(['all',...STATUSES],{
        placeHolder:'Filter the selected manager task tree by current status'
      });
      if (selected) liveProvider.setFilter(selected);
    }),
    vscode.commands.registerCommand('sdlc.execution.approvePlan',() => action('approve-plan')),
    vscode.commands.registerCommand('sdlc.execution.approveControls',() => action('approve-controls')),
    vscode.commands.registerCommand('sdlc.execution.acceptTask',collectAcceptance),
    vscode.commands.registerCommand('sdlc.execution.togglePause',togglePause),
    vscode.commands.registerCommand('sdlc.execution.cancelTask',cancelSelectedTask)
  );
  context.subscriptions.push(liveProvider);
  context.subscriptions.push({dispose() {
    if (liveTimer) clearInterval(liveTimer);
    liveTimer = undefined;
    liveController.invalidate();
    liveController.clear('Extension deactivated');
  }});
  return {
    provider,controller,liveProvider,liveController,
    get tree() {return tree;},get liveTree() {return liveTree;}
  };
}
exports.activate = activate;
