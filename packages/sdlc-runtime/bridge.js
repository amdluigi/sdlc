'use strict';

const { execFile } = require('node:child_process');
const path = require('node:path');
const crypto = require('node:crypto');

const SCRIPT = path.resolve(__dirname, '..', '..', 'skills', 'sdlc', 'scripts', 'manage_runtime.py');
const OPERATIONS = new Set(['prepare', 'prepare_execute', 'start', 'check', 'step', 'observe', 'tool', 'receive', 'stop']);
const CAPACITY = 2 * 1024 * 1024;

function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value !== null && typeof value === 'object') {
    return '{' + Object.keys(value).sort().map(key => canonical(key) + ':' + canonical(value[key])).join(',') + '}';
  }
  const encoded = JSON.stringify(value);
  if (encoded === undefined) throw new Error('Unsupported runtime JSON');
  return encoded.replace(/[\u007f-\uffff]/g, char => '\\u' + char.charCodeAt(0).toString(16).padStart(4, '0'));
}

function digest(value) {
  return 'sha256:' + crypto.createHash('sha256').update(canonical(value), 'utf8').digest('hex');
}

function createBridge(projectRoot) {
  return function bridge(operation, payload) {
    if (!OPERATIONS.has(operation)) return Promise.reject(new Error('Unsupported manager operation'));
    const input = JSON.stringify(payload);
    if (Buffer.byteLength(input) > CAPACITY) return Promise.reject(new Error('Manager input exceeds capacity'));
    return new Promise((resolve, reject) => {
      const child = execFile('python', ['-B', '-I', '-S', SCRIPT, operation, '--project-root', projectRoot], {
        cwd: path.dirname(SCRIPT), encoding: 'utf8', windowsHide: true,
        timeout: 15000, maxBuffer: CAPACITY, shell: false
      }, (error, stdout, stderr) => {
        if (error) {
          const code = /\berror\[(E_[A-Z_]+)\]/.exec(stderr || '');
          const failure = new Error(code ? code[1] : 'Manager bridge failed; work may remain unresolved');
          if (code) failure.code = code[1];
          reject(failure);
          return;
        }
        try { resolve(JSON.parse(stdout)); }
        catch { reject(new Error('Invalid manager response; work remains unresolved')); }
      });
      child.stdin.on('error', () => {});
      child.stdin.end(input, 'utf8');
    });
  };
}

module.exports = { createBridge, digest, canonical };
