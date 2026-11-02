'use strict';
const {parseLiveView, canonical, validateReloadBinding} = require('./snapshot');
const STATUSES = ['waiting','ready','running','blocked','reported','accepted','failed','cancelled'];
const ICONS = {
  waiting:'clock', ready:'circle-outline', running:'sync', blocked:'warning',
  reported:'inbox', accepted:'check', failed:'error', cancelled:'circle-slash'
};
function label(value, maximum = 220) {
  const characters = Array.from(String(value));
  return characters.length > maximum ? characters.slice(0,maximum-1).join('') + '…' : characters.join('');
}
function ganttBar(start,end,scale) {
  if (start === null || end === null || scale === null) return 'unknown';
  const width = 20, total = BigInt(scale);
  if (total === 0n) return '*' + '.'.repeat(width-1);
  const left = Math.min(width-1,Number(BigInt(start) * BigInt(width) / total));
  const right = Math.min(width,Math.max(left+1,Number(BigInt(end) * BigInt(width) / total)));
  return '.'.repeat(left) + '#'.repeat(right-left) + '.'.repeat(width-right);
}
function contextParts(value, length = 160) {
  const characters = Array.from(value), parts = [];
  for (let offset=0; offset<characters.length; offset+=length) {
    parts.push(characters.slice(offset,offset+length).join(''));
  }
  return parts;
}
const ACCEPTED_BASIS = {
  'independent-operator-validation':
    'Accepted by independent operator validation; worker verification not treated as passed',
  'worker-verification-with-operator-judgment': 'Accepted by operator judgment of worker-reported verification'
};
class LiveProvider {
  constructor(vscode) {
    this.vscode = vscode;
    this.emitter = new vscode.EventEmitter();
    this.onDidChangeTreeData = this.emitter.event;
    this.snapshot = null;
    this.filter = 'all';
    this.nodes = [this.item('live-state','No live manager selected','warning')];
  }
  item(id, text, icon = 'info', children = []) {
    const item = new this.vscode.TreeItem(label(text),
      children.length ? this.vscode.TreeItemCollapsibleState.Collapsed : this.vscode.TreeItemCollapsibleState.None);
    item.id = id;
    item.tooltip = label(text,2048);
    item.iconPath = new this.vscode.ThemeIcon(icon);
    item.accessibilityInformation = {label:label(text,512),role:'treeitem'};
    item.children = children;
    for (const child of children) child.parent = item;
    return item;
  }
  show(snapshot) {
    this.snapshot = snapshot;
    const progress = Object.entries(snapshot.progress)
      .filter(([key]) => key !== 'total')
      .map(([key,value]) => `${key}: ${value}`).join(', ');
    const summary = this.item('live-progress',`Progress ${snapshot.progress.accepted}/${snapshot.progress.total} accepted`,
      'graph',[
        this.item('live-binding',`Execution ${snapshot.binding.executionId}, revision ${snapshot.binding.planRevision}`,'git-commit'),
        this.item('live-progress-detail',progress,'list-ordered'),
        this.item('live-freshness',snapshot.writerLockPresent
          ? 'Manager writer is active; actions will be revalidated' : 'Current local manager view','info'),
        this.item('live-approval',`Plan approval: ${snapshot.planApproved ? 'approved' : 'required'}`,'lock'),
        this.item('live-controls',`Controls: ${snapshot.controls.enabled ? 'enabled' : 'disabled'}; ` +
          `${snapshot.controls.paused ? 'paused' : 'not paused'}; ` +
          `${snapshot.controls.autonomous ? 'autonomous mode' : 'manual/supervised mode'}`,'shield'),
        this.item('live-limitations',`Host cancellation ${snapshot.controls.hostCancellation}; ` +
          `spend enforcement ${snapshot.controls.spendEnforcement ? 'available' : 'unavailable'}`,'warning')
      ]);
    const tasks = snapshot.tasks.filter(task => this.filter === 'all' || task.status === this.filter)
      .map(task => this.item('live-task:' + task.id,
        `${task.id} (${task.status}): ${task.title}`,ICONS[task.status],[
          this.item(`${task.id}:attempt`,`Attempt: ${task.attemptId || 'none'}`,'info'),
          this.item(`${task.id}:result`,`Result: ${task.resultId || 'none'}; reported ${task.reportedStatus || 'none'}`,'info'),
          ...(task.resultDigest ? [this.item(`${task.id}:result-digest`,`Result digest: ${task.resultDigest}`,'key')] : []),
          ...(task.acceptanceSchemaVersion === 2 ? [this.item(`${task.id}:acceptance-basis`,
            'Acceptance requires independent operator validation; worker verification is not treated as passed',
            'shield')] : []),
          ...(task.acceptanceBasis ? [this.item(`${task.id}:accepted-basis`,ACCEPTED_BASIS[task.acceptanceBasis],'verified')] : []),
          this.item(`${task.id}:dependencies`,`Prerequisites: ${task.prerequisites.join(', ') || 'none'}`,'references'),
          this.item(`${task.id}:criteria`,`Acceptance criteria: ${task.acceptanceCriteria.join(', ') || 'none'}`,'checklist'),
          this.item(`${task.id}:estimate`,`Estimate: ${task.estimateMs === null ? 'not declared' : task.estimateMs + ' ms'}`,'watch'),
          this.item(`${task.id}:model`,`Requested model: ${task.requestedModel || 'host default; not observed'}`,'symbol-misc')
        ]));
    const eventRows = snapshot.events.slice(-40).map(event => this.item(
      `live-event:${event.sequence}`,
      `${event.sequence}: ${event.type}${event.taskId ? ' · ' + event.taskId : ''}` +
        `${event.attemptId ? ' · ' + event.attemptId : ''} · ${event.recordedAt}`,
      'history'
    ));
    const additional = [];
    if (snapshot.schemaVersion === 2) {
      const gantt = snapshot.gantt;
      const ganttRows = gantt.tasks.map(task => {
        const planned = task.plannedStartMs === null || task.plannedEndMs === null
          ? 'unknown'
          : `${task.plannedStartMs}-${task.plannedEndMs} ms`;
        const actual = task.actualStartOffsetMs === null
          ? 'unknown'
          : task.actualDurationMs === null
            ? `started +${task.actualStartOffsetMs} ms; duration unknown`
            : `${task.actualDurationMs} ms from manager events (start +${task.actualStartOffsetMs} ms)`;
        const plannedBar = ganttBar(task.plannedStartMs,task.plannedEndMs,gantt.plannedDurationMs);
        const actualEnd = task.actualDurationMs === null || task.actualStartOffsetMs === null
          ? null : BigInt(task.actualStartOffsetMs) + BigInt(task.actualDurationMs);
        const actualBar = ganttBar(task.actualStartOffsetMs,actualEnd,gantt.actualDurationMs);
        return this.item(`live-gantt-task:${task.id}`,
          `${task.id}: ${task.title} (${task.agent}; ${task.status})`,'timeline',[
            this.item(`${task.id}:gantt-planned`,
              `Planned relative interval: ${planned}; estimate ${task.estimateMs === null ? 'unknown' : task.estimateMs + ' ms'}`,'watch'),
            this.item(`${task.id}:gantt-planned-bar`,`Planned bar: ${plannedBar}`,'graph'),
            this.item(`${task.id}:gantt-actual`,`Actual interval: ${actual}`,'history'),
            this.item(`${task.id}:gantt-actual-bar`,`Actual bar: ${actualBar}`,'graph'),
            this.item(`${task.id}:gantt-dependencies`,
              `Dependencies: ${task.prerequisites.join(', ') || 'none'}`,'references')
          ]);
      });
      additional.push(this.item('live-gantt',
        `Project Gantt · ${gantt.plannedComplete ? 'relative estimates complete' : 'planned timing incomplete'}`,'timeline',[
          this.item('live-gantt-planned-basis',`Planned basis: ${gantt.plannedBasis}`,'info'),
          this.item('live-gantt-actual-basis',
            `Actual basis: ${gantt.actualBasis}; origin ${gantt.actualOrigin || 'unknown'}`,'info'),
          ...ganttRows
        ]));
      const contextEntries = [];
      if (snapshot.context.shared) {
        const entry = snapshot.context.shared;
        const parts = contextParts(entry.content);
        contextEntries.push(this.item('live-context-shared',
          `Shared context (${entry.source}; updated ${entry.updatedAt}; plan revision ${entry.planRevision})`,'note',[
            ...parts.map((part,index) => this.item(
              `live-context-shared:content:${index+1}`,`Context ${index+1}/${parts.length}: ${part}`,'note')),
            this.item('live-context-shared:author',`Author: ${entry.author}`,'person'),
            this.item('live-context-shared:digest',`Content digest: ${entry.digest}`,'key')
          ]));
      }
      for (const [agent,entry] of Object.entries(snapshot.context.agents).sort(([a],[b]) => a.localeCompare(b))) {
        const parts = contextParts(entry.content);
        contextEntries.push(this.item(`live-context-agent:${agent}`,
          `${agent} context (${entry.source}; updated ${entry.updatedAt}; plan revision ${entry.planRevision})`,
          'account',[
            ...parts.map((part,index) => this.item(
              `live-context-agent:${agent}:content:${index+1}`,`Context ${index+1}/${parts.length}: ${part}`,'note')),
            this.item(`live-context-agent:${agent}:author`,`Author: ${entry.author}`,'person'),
            this.item(`live-context-agent:${agent}:digest`,`Content digest: ${entry.digest}`,'key')
          ]));
      }
      additional.push(this.item('live-context',`Project context · revision ${snapshot.context.revision}`,
        'note',contextEntries.length ? contextEntries : [
          this.item('live-context-empty','No shared or specialist context recorded','info')
        ]));
    }
    this.nodes = [
      summary,
      this.item('live-tasks',`Tasks (${tasks.length}${this.filter === 'all' ? '' : ', filtered: ' + this.filter})`,
        'list-tree',tasks),
      ...additional,
      this.item('live-events',`Recent manager events (${eventRows.length})`,'history',eventRows)
    ];
    this.emitter.fire(undefined);
  }
  fail(message) {
    this.snapshot = null;
    this.nodes = [this.item('live-state',message,'warning')];
    this.emitter.fire(undefined);
  }
  setFilter(value) {
    if (!['all',...STATUSES].includes(value)) throw new Error('Unsupported task filter');
    this.filter = value;
    if (this.snapshot) this.show(this.snapshot);
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
function expectedBinding(selection) {
  const {executionId,snapshot} = selection;
  return {
    executionId, planRevision:snapshot.binding.planRevision, planDigest:snapshot.planDigest,
    policyDigest:snapshot.policyDigest, controlsDigest:snapshot.controlsDigest,
    controlsStateDigest:snapshot.controlsStateDigest
  };
}
function confirmationMaterial(operation, selection, extra = {}) {
  const confirmation = {operation,expectedBinding:expectedBinding(selection)};
  if (operation === 'accept') confirmation.acceptance = extra.acceptance;
  if (operation === 'cancel') {
    confirmation.taskId = extra.taskId;
    confirmation.attemptId = extra.attemptId;
  }
  return confirmation;
}
function digestOf(value) {
  return 'sha256:' + require('node:crypto').createHash('sha256').update(canonical(value),'ascii').digest('hex');
}
// Pins only what the user confirmed: the explicit selection, the displayed bindings and the acted-on task.
function actionPin(operation, selection, extra = {}) {
  const taskId = operation === 'accept' ? extra.acceptance?.taskId : operation === 'cancel' ? extra.taskId : null;
  const task = taskId ? selection.snapshot.tasks.find(item => item.id === taskId) : null;
  return digestOf({
    epoch:selection.epoch, root:selection.root, confirmation:confirmationMaterial(operation,selection,extra),
    task:task ? {
      id:task.id,status:task.status,attemptId:task.attemptId,resultId:task.resultId,resultDigest:task.resultDigest
    } : null
  });
}
class LiveController {
  constructor(provider, bridge, parser = parseLiveView) {
    this.provider = provider;
    this.bridge = bridge;
    this.parser = parser;
    this.selection = null;
    this.serial = 0;
    this.epoch = 0;
    this.suspended = 0;
  }
  clear(message = 'No live manager selected') {
    this.serial++;
    this.epoch++;
    this.selection = null;
    this.provider.fail(message);
  }
  invalidate() {this.serial++;}
  // Confirmation and mutation suspend reads, and drop any in-flight read, so the confirmed view stays stable.
  suspend() {
    this.suspended++;
    this.serial++;
  }
  resume() {
    if (this.suspended > 0) this.suspended--;
  }
  async load(root, executionId) {
    const serial = ++this.serial;
    const epoch = ++this.epoch;
    this.selection = null;
    this.provider.fail('Loading selected manager execution');
    try {
      const response = await this.bridge(root,{operation:'inspect',executionId});
      if (response.operation !== 'inspect' || !response.view) throw new Error('invalid manager response');
      const snapshot = this.parser(Buffer.from(canonical(response.view),'utf8'));
      if (snapshot.binding.executionId !== executionId) throw new Error('manager selection changed');
      if (serial !== this.serial || epoch !== this.epoch) return false;
      this.selection = {root,executionId,epoch,binding:{...snapshot.binding},snapshot};
      this.provider.show(snapshot);
      return true;
    } catch {
      if (serial === this.serial) this.clear('Live manager view unavailable; select a local execution again');
      return false;
    }
  }
  async refresh() {
    if (!this.selection || this.suspended) return false;
    const {root,executionId,binding,epoch} = this.selection;
    const serial = ++this.serial;
    try {
      const response = await this.bridge(root,{operation:'inspect',executionId});
      if (response.operation !== 'inspect' || !response.view) throw new Error('invalid manager response');
      const snapshot = this.parser(Buffer.from(canonical(response.view),'utf8'));
      validateReloadBinding(snapshot.binding,binding);
      if (snapshot.binding.executionId !== executionId || serial !== this.serial || epoch !== this.epoch) return false;
      if (snapshot.snapshotDigest === this.selection.snapshot.snapshotDigest) return true;
      this.selection = {root,executionId,epoch,binding:{...snapshot.binding},snapshot};
      this.provider.show(snapshot);
      return true;
    } catch {
      if (serial === this.serial) {
        this.epoch++;
        this.selection = null;
        this.provider.fail('Live manager refresh failed; actions are disabled');
      }
      return false;
    }
  }
  pin(operation, extra = {}, selection = this.selection) {
    return selection ? actionPin(operation,selection,extra) : null;
  }
  // Returns the manager's post-write view, or null when the write was recorded after the user selected elsewhere.
  async action(operation, extra = {}, confirmedPin = this.pin(operation,extra)) {
    const selection = this.selection;
    if (!selection || !confirmedPin || actionPin(operation,selection,extra) !== confirmedPin) {
      throw new Error('Manager selection changed after confirmation; confirm the current view again');
    }
    const {root,executionId,snapshot,epoch} = selection;
    const confirmation = confirmationMaterial(operation,selection,extra);
    const response = await this.bridge(root,{
      operation,executionId,expectedBinding:confirmation.expectedBinding,
      confirmationDigest:digestOf(confirmation),...extra
    });
    if (response.operation !== operation || !response.view) throw new Error('Manager action response was invalid');
    const next = this.parser(Buffer.from(canonical(response.view),'utf8'));
    validateReloadBinding(next.binding,snapshot.binding);
    if (epoch !== this.epoch || !this.selection) return {recorded:true,view:null};
    this.serial++;
    this.selection = {root,executionId,epoch,binding:{...next.binding},snapshot:next};
    this.provider.show(next);
    return {recorded:true,view:next};
  }
}
module.exports = {LiveProvider, LiveController, STATUSES, confirmationMaterial, digestOf};
