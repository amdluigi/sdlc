'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const {fixture, canonical} = require('./fixture');
const scratch = path.join(__dirname, '.io-fixtures');
test('real confined IO rejects escapes, links, corrupt and oversized files', async () => {
  await fs.mkdir(scratch, {recursive:true});
  try {
    const root = path.join(scratch, 'root');
    await fs.mkdir(root, {recursive:true});
    const selected = path.join(root, 'selected.json');
    await fs.writeFile(selected, canonical(fixture()));
    const {readSnapshot} = require('../snapshot');
    assert.equal((await readSnapshot(root, selected)).binding.executionId, 'example');
    await assert.rejects(readSnapshot(root, path.join(scratch, 'outside.json')));
    await assert.rejects(readSnapshot(root, root));
    await fs.writeFile(selected, '{}');
    await assert.rejects(readSnapshot(root, selected));
    await fs.writeFile(selected, Buffer.alloc(2 * 1024 * 1024 + 1));
    await assert.rejects(readSnapshot(root, selected));
    const link = path.join(scratch, 'linked-root');
    await fs.symlink(root, link, process.platform === 'win32' ? 'junction' : 'dir');
    await assert.rejects(readSnapshot(link, path.join(link,'selected.json')));
    const nested = path.join(root, 'linked');
    await fs.symlink(root, nested, process.platform === 'win32' ? 'junction' : 'dir');
    await assert.rejects(readSnapshot(root, path.join(nested,'selected.json')));
  } finally {
    await fs.rm(scratch, {recursive:true, force:true});
  }
});
