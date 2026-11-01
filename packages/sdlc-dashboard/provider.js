'use strict';
const {validateReloadBinding, readSnapshot} = require('./snapshot');
const STATUS_ICON = {
  waiting:'clock', ready:'circle-outline', running:'sync', blocked:'warning',
  reported:'inbox', accepted:'check', failed:'error', cancelled:'circle-slash'
};
function plain(value, maximum = 180) {
  const characters = Array.from(String(value));
  return characters.length > maximum ? characters.slice(0,maximum-1).join('') + '…' : characters.join('');
}
function known(value) {return value === null ? 'unknown' : String(value);}
class SnapshotProvider {
  constructor(vscode) {
    this.vscode = vscode;
    this.emitter = new vscode.EventEmitter();
    this.onDidChangeTreeData = this.emitter.event;
    this.snapshot = null;
    this.nodes = [];
    this.fail('No snapshot selected');
  }
  item(id, label, icon, children = [], tooltip = label) {
    const item = new this.vscode.TreeItem(plain(label),
      children.length ? this.vscode.TreeItemCollapsibleState.Collapsed : this.vscode.TreeItemCollapsibleState.None);
    item.id = id;
    item.tooltip = plain(tooltip,2048);
    item.iconPath = new this.vscode.ThemeIcon(icon);
    item.accessibilityInformation = {label:plain(label,512) + ', read only', role:'treeitem'};
    item.children = children;
    for (const child of children) child.parent = item;
    return item;
  }
  show(snapshot) {
    this.snapshot = snapshot;
    const detail = (id,label) => this.item(id,label,'info');
    const tasks = snapshot.tasks.map(task => this.item('task:' + task.id,
      `${task.id} (${task.status}): ${task.title}`, STATUS_ICON[task.status], [
        detail(`${task.id}:attempt`, 'Attempt: ' + known(task.attemptId)),
        detail(`${task.id}:report`, 'Reported result: ' + known(task.reportedStatus)),
        detail(`${task.id}:estimate`, 'Declared estimate: ' + known(task.estimateMs) + (task.estimateMs === null ? '' : ' ms')),
        detail(`${task.id}:interval`, 'Recorded interval: ' + known(task.recordedIntervalMs) +
          (task.recordedIntervalMs === null ? '' : ' ms') + ' (manager events, not host duration)'),
        detail(`${task.id}:model`, 'Requested model: ' + known(task.requestedModel) + ' (not observed)')
      ], `State: ${task.status}; read-only task metadata; ${task.title}`));
    this.nodes = [
      detail('notice','Exported snapshot only; live freshness and authenticity not verified'),
      this.item('binding', `Execution: ${snapshot.binding.executionId}, revision ${snapshot.binding.planRevision}`, 'git-commit', [
        detail('plan-digest','Plan digest: ' + snapshot.binding.planDigest),
        detail('snapshot-digest','Snapshot digest: ' + snapshot.snapshotDigest)
      ]),
      detail('approval','Exported policy approval: ' + (snapshot.approved ? 'bound at export, not UI authority' : 'not approved')),
      detail('writer','Writer lock at export: ' + (snapshot.writerLockPresent ? 'present' : 'absent')),
      this.item('controls','Exported controls (no actions)', 'lock', [
        detail('enabled','Execution: ' + (snapshot.controls.enabled ? 'enabled at export' : 'disabled at export')),
        detail('paused','Pause: ' + (snapshot.controls.paused ? 'paused at export' : 'not paused at export')),
        detail('cancellations','Pending cancellations: ' + snapshot.controls.pendingCancellationCount),
        detail('unknown-attempts','Unknown native attempts: ' + snapshot.controls.unknownNativeAttemptCount)
      ]),
      this.item('tasks',tasks.length ? `Tasks: ${tasks.length}` : 'Tasks: none', 'list-tree', tasks)
    ];
    this.emitter.fire(undefined);
  }
  fail(message, loading = false) {
    this.snapshot = null;
    this.nodes = [this.item('state',message,loading ? 'loading' : 'warning')];
    this.emitter.fire(undefined);
  }
  getChildren(element) {return element ? element.children : this.nodes;}
  getTreeItem(element) {return element;}
  getParent(element) {return element.parent;}
  find(id, nodes = this.nodes) {
    for (const item of nodes) {
      if (item.id === id) return item;
      const child = this.find(id,item.children);
      if (child) return child;
    }
  }
  dispose() {this.emitter.dispose();}
}
class SnapshotController {
  constructor(provider, reader = readSnapshot) {
    this.provider = provider;
    this.reader = reader;
    this.serial = 0;
    this.selection = null;
    this.pendingSelection = null;
  }
  clear(message = 'No snapshot selected') {
    this.serial++;
    this.selection = null;
    this.pendingSelection = null;
    this.provider.fail(message);
  }
  async load(root, file, previous = null) {
    const serial = ++this.serial;
    this.selection = null;
    this.pendingSelection = {root,file,binding:previous};
    this.provider.fail('Loading selected snapshot; no current data', true);
    try {
      const value = await this.reader(root,file);
      if (previous) validateReloadBinding(value.binding,previous);
      if (serial !== this.serial) return false;
      this.pendingSelection = null;
      this.selection = {root,file,binding:{...value.binding}};
      this.provider.show(value);
      return true;
    } catch {
      if (serial === this.serial) this.clear('Snapshot unavailable or invalid; reopen a confined export');
      return false;
    }
  }
  refresh() {
    const selected = this.pendingSelection || this.selection;
    if (!selected) {this.clear('No snapshot selected; use Open Execution Snapshot'); return Promise.resolve(false);}
    return this.load(selected.root,selected.file,selected.binding);
  }
}
module.exports = {SnapshotProvider, SnapshotController};
