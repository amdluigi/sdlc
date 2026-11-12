const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { run } = require('../driver');
const { createBridge } = require('../bridge');

const ROOT = path.resolve(__dirname, '..', '..', '..');

function python(project, code) {
  const output = spawnSync('python', ['-B', '-c', code, project],
    { cwd: ROOT, encoding: 'utf8' });
  assert.equal(output.status, 0, output.stderr);
  return JSON.parse(output.stdout);
}

test('AC-1 context is frozen between real step validation and adapter invocation, then rebound', async t => {
  const project = fs.mkdtempSync(path.join(os.tmpdir(), 'sdlc-context-'));
  t.after(() => fs.rmSync(project, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 }));
  const initial = python(project, `
import json,sys
from tests.test_bounded_runtime import fixture,LIMITS,MODEL
from tests.test_execution_contracts import result
from bounded_runtime import prepare
import execution_manager as manager
p,b=fixture(sys.argv[1])
c=manager.inspect_execution(sys.argv[1],"feature-one")
manager.update_context(sys.argv[1],"feature-one","shared",None,"Context A.",c["planDigest"],c["context"]["revision"])
r=result(p)
r["verification"][0]["result"]="unavailable"
print(json.dumps({"envelope":prepare(sys.argv[1],"feature-one",b,"developer",MODEL,LIMITS),"result":r}))
`);
  const realBridge = createBridge(project);
  let protectedSteps = 0;
  const bridge = async (operation, payload) => {
    const output = await realBridge(operation, payload);
    if (operation === 'step') {
      // This is the original race window: validation finished, adapter not invoked.
      const attempts = python(project, `
import json,sys
from tests.test_bounded_runtime import fixture
from artifact_contracts import ContractIssue
import execution_manager as manager
c=manager.inspect_execution(sys.argv[1],"feature-one")
out=[]
for scope,agent in (("shared",None),("agent","developer")):
 try:
  manager.update_context(sys.argv[1],"feature-one",scope,agent,"Context B.",c["planDigest"],c["context"]["revision"])
  out.append("updated")
 except ContractIssue as error:
  out.append(error.code)
print(json.dumps(out))
`);
      assert.deepEqual(attempts, ['E_EXECUTION_CONTEXT_ACTIVE', 'E_EXECUTION_CONTEXT_ACTIVE']);
      protectedSteps++;
    }
    return output;
  };
  let firstCalls = 0;
  const receipt = await run({ envelope: initial.envelope, bridge, respond: async prompt => {
    firstCalls++;
    assert.equal(protectedSteps, 1);
    assert.ok(prompt.includes('Context A.'));
    assert.equal(prompt.includes('Context B.'), false);
    return (async function* () { yield JSON.stringify({ type: 'result', result: initial.result }); })();
  } });
  assert.equal(firstCalls, 1);
  assert.equal(receipt.acceptance, 'not-assessed');
  const next = python(project, `
import json,sys
from tests.test_bounded_runtime import LIMITS,MODEL
from tests.test_execution_contracts import brief,result
from bounded_runtime import prepare
import execution_manager as manager
c=manager.inspect_execution(sys.argv[1],"feature-one")
assert c["state"]["tasks"]["implement"]["status"]=="reported"
manager.update_context(sys.argv[1],"feature-one","shared",None,"Context B.",c["planDigest"],c["context"]["revision"])
manager.record_task(sys.argv[1],"feature-one","implement","reject","attempt-one","Independent review requires another attempt.")
p=c["plan"]
p["revision"]+=1
manager.import_plan(sys.argv[1],p)
c=manager.inspect_execution(sys.argv[1],"feature-one")
manager.approve_plan(sys.argv[1],"feature-one",c["planDigest"],c["policyDigest"])
b=brief(p)
b["attemptId"]="attempt-two"
b["guidance"]=["guide.md"]
b["allowedActions"]=["read","search","edit"]
r=result(p)
r["attemptId"]="attempt-two"
r["verification"][0]["result"]="unavailable"
print(json.dumps({"envelope":prepare(sys.argv[1],"feature-one",b,"developer",MODEL,LIMITS),"result":r}))
`);
  assert.ok(next.envelope.request.context.revision > initial.envelope.request.context.revision);
  assert.notEqual(next.envelope.request.context.digest, initial.envelope.request.context.digest);
  let nextCalls = 0;
  await run({ envelope: next.envelope, bridge: realBridge, respond: async prompt => {
    nextCalls++;
    assert.ok(prompt.includes('Context B.'));
    assert.equal(prompt.includes('Context A.'), false);
    return (async function* () { yield JSON.stringify({ type: 'result', result: next.result }); })();
  } });
  assert.equal(nextCalls, 1);
});
