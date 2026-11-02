'use strict';
const {spawn} = require('node:child_process');
const path = require('node:path');
const MAX_BYTES = 2 * 1024 * 1024;
function requestManager(projectRoot, request) {
  if (typeof projectRoot !== 'string' || !path.isAbsolute(projectRoot)) {
    return Promise.reject(new Error('Select a local project before opening the manager view'));
  }
  if (process.platform === 'win32' &&
      (!/^[a-z]:\\/i.test(projectRoot) || projectRoot.slice(2).includes(':'))) {
    return Promise.reject(new Error('Network and alternate-stream project paths are unsupported'));
  }
  const script = path.join(__dirname,'manager_bridge.py');
  const payload = Buffer.from(JSON.stringify({...request,projectRoot}));
  if (payload.byteLength > 1024 * 1024) return Promise.reject(new Error('Manager request exceeds its size bound'));
  return new Promise((resolve,reject) => {
    let child;
    try {
      child = spawn('python',['-B','-I',script],{
        cwd:__dirname, shell:false, windowsHide:true, stdio:['pipe','pipe','pipe']
      });
    } catch {
      reject(new Error('Local execution manager is unavailable'));
      return;
    }
    const output = [], errors = [];
    let outputBytes = 0, errorBytes = 0, finished = false;
    const timer = setTimeout(() => {
      if (finished) return;
      finished = true;
      child.kill();
      reject(new Error('Local execution manager did not respond within its bound'));
    },15000);
    child.stdout.on('data',chunk => {
      outputBytes += chunk.length;
      if (outputBytes > MAX_BYTES) {
        finished = true;
        clearTimeout(timer);
        reject(new Error('Manager response exceeds its size bound'));
        child.stdin.destroy();
        child.kill();
        return;
      }
      output.push(chunk);
    });
    child.stderr.on('data',chunk => {
      errorBytes += chunk.length;
      if (errorBytes <= 4096) errors.push(chunk);
    });
    child.on('error',() => {
      if (!finished) {
        finished = true;
        clearTimeout(timer);
        reject(new Error('Local execution manager is unavailable'));
      }
    });
    child.on('close',code => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      if (code !== 0) {
        const codeName = Buffer.concat(errors).toString('utf8').trim().split(/\s+/)[0];
        reject(new Error(/^[A-Z][A-Z0-9_]{2,80}$/.test(codeName)
          ? `Manager operation blocked (${codeName})`
          : 'Manager operation was unavailable'));
        return;
      }
      try {
        const value = JSON.parse(Buffer.concat(output).toString('utf8'));
        if (!value || Array.isArray(value) || typeof value !== 'object') throw new Error();
        resolve(value);
      } catch {
        reject(new Error('Manager response was invalid'));
      }
    });
    child.stdin.end(payload);
  });
}
module.exports = {requestManager, MAX_BYTES};
