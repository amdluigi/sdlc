'use strict';
const vscode = require('vscode');
const {SnapshotProvider, SnapshotController} = require('./provider');
const VIEW = 'sdlc.execution.snapshot';
function activate(context) {
  const provider = new SnapshotProvider(vscode);
  const controller = new SnapshotController(provider);
  let tree;
  let creating;
  let commandSerial = 0;
  let refreshSelectionId;
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
    })
  );
  return {provider,controller,get tree() {return tree;}};
}
exports.activate = activate;
