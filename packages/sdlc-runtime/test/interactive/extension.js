'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');
const vscode = require('vscode');

exports.activate = function () {
  const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  let syntheticWorkspace = false;
  const running = new Promise(resolve => setImmediate(resolve)).then(async () => {
    if (!root || await fs.readFile(path.join(root, '.synthetic-runtime-host'), 'utf8') !==
        'offline synthetic provider only\n') {
      throw new Error('Select only a marked disposable synthetic workspace');
    }
    syntheticWorkspace = true;
    return require('../host').run();
  });
  running.catch(async error => {
    console.error('Offline native qualification failed:', error);
    if (syntheticWorkspace) {
      await fs.writeFile(path.join(root, 'host-failure.json'), JSON.stringify({
        message: error.message, name: error.name, actualProviderCalls: 0
      }, null, 2));
    }
  });
  return { running };
};
