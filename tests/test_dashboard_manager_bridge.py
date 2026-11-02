import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_execution_contracts import ROOT, SCRIPTS, plan, brief, result
from tests.test_execution_management import policy
from tests.test_execution_controls import autonomous_controls_policy

import execution_controls
import execution_manager
import execution_state
from artifact_contracts import ContractIssue


BRIDGE_PATH = ROOT / "packages" / "sdlc-dashboard" / "manager_bridge.py"
SPEC = importlib.util.spec_from_file_location("sdlc_dashboard_manager_bridge", BRIDGE_PATH)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class DashboardManagerBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.plan = plan()
        execution_manager.configure_policy(self.root, policy())
        execution_manager.import_plan(self.root, self.plan)

    def action(self, operation, expected, **extra):
        material = {"operation": operation, "expectedBinding": expected}
        if operation == "accept":
            material["acceptance"] = extra["acceptance"]
        if operation == "cancel":
            material.update(taskId=extra["taskId"], attemptId=extra["attemptId"])
        return {
            "operation": operation, "projectRoot": str(self.root), "executionId": "feature-one",
            "expectedBinding": expected, "confirmationDigest": execution_state.digest(material), **extra,
        }

    def test_live_view_is_manager_owned_digest_bound_and_does_not_dispatch(self):
        before = set(self.root.rglob("*"))
        inspected = bridge.run({"operation": "inspect", "projectRoot": str(self.root),
                                "executionId": "feature-one"})["view"]
        self.assertEqual("sdlc-live-execution-view", inspected["kind"])
        self.assertEqual(execution_state.digest({
            key: value for key, value in inspected.items() if key != "snapshotDigest"
        }), inspected["snapshotDigest"])
        self.assertEqual("waiting", inspected["tasks"][0]["status"])
        self.assertEqual(before, set(self.root.rglob("*")))

    def test_fixed_python_bridge_process_returns_only_selected_execution_metadata(self):
        request = json.dumps({
            "operation": "inspect", "projectRoot": str(self.root), "executionId": "feature-one",
        }, separators=(",", ":"))
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        completed = subprocess.run(
            ["python", "-B", "-I", str(BRIDGE_PATH)], input=request, text=True, capture_output=True,
            cwd=BRIDGE_PATH.parent, env=environment, check=True,
        )
        response = json.loads(completed.stdout)
        self.assertEqual("sdlc-live-execution-view", response["view"]["kind"])
        self.assertEqual("feature-one", response["view"]["binding"]["executionId"])
        self.assertEqual(["implement"], [task["id"] for task in response["view"]["tasks"]])
        self.assertNotIn("guidance", response["view"]["tasks"][0])

    def test_node_bridge_spawns_only_fixed_python_manager_bridge(self):
        source = (
            "const root=process.argv[1];"
            "require('./packages/sdlc-dashboard/manager').requestManager(root,"
            "{operation:'inspect',executionId:'feature-one'}).then(value=>"
            "process.stdout.write(JSON.stringify(value))).catch(()=>process.exitCode=2);"
        )
        completed = subprocess.run(
            ["node", "-e", source, str(self.root)], text=True, capture_output=True,
            cwd=ROOT, timeout=20, check=True,
        )
        response = json.loads(completed.stdout)
        self.assertEqual("feature-one", response["view"]["binding"]["executionId"])
        self.assertFalse(response["view"]["controls"]["enabled"])

    def test_confirmed_approvals_and_pause_revalidate_current_manager_bindings(self):
        view = bridge.run({"operation": "inspect", "projectRoot": str(self.root),
                           "executionId": "feature-one"})["view"]
        expected = {
            "executionId": "feature-one", "planRevision": view["binding"]["planRevision"],
            "planDigest": view["planDigest"], "policyDigest": view["policyDigest"],
            "controlsDigest": view["controlsDigest"], "controlsStateDigest": view["controlsStateDigest"],
        }
        bridge.run(self.action("approve-plan", expected))
        execution_controls.configure_controls(self.root, autonomous_controls_policy())
        current = execution_manager.inspect_execution(self.root, "feature-one")
        controls_view = execution_controls.inspect_controls(self.root)
        expected = {
            "executionId": "feature-one", "planRevision": current["plan"]["revision"],
            "planDigest": current["planDigest"], "policyDigest": current["policyDigest"],
            "controlsDigest": controls_view["controlsDigest"],
            "controlsStateDigest": execution_state.digest(controls_view["store"]),
        }
        approved_controls = bridge.run(self.action("approve-controls", expected))["view"]
        expected = {**expected, "controlsStateDigest": approved_controls["controlsStateDigest"]}
        paused = bridge.run(self.action("pause", expected))["view"]
        self.assertTrue(paused["controls"]["paused"])
        with self.assertRaises(ContractIssue) as caught:
            bridge.run(self.action("resume", expected))
        self.assertEqual("E_EXECUTION_STALE_VIEW", caught.exception.code)
        fresh = bridge.run({"operation": "inspect", "projectRoot": str(self.root),
                            "executionId": "feature-one"})["view"]
        fresh_expected = {
            **expected, "controlsDigest": fresh["controlsDigest"],
            "controlsStateDigest": fresh["controlsStateDigest"],
        }
        resumed = bridge.run(self.action("resume", fresh_expected))["view"]
        self.assertFalse(resumed["controls"]["paused"])

    def test_independent_acceptance_is_explicit_and_never_comes_from_worker_report(self):
        execution_manager.approve_plan(
            self.root, "feature-one",
            execution_manager.inspect_execution(self.root, "feature-one")["planDigest"],
            execution_state.digest(execution_manager._consent(self.root, enabled=True)),
        )
        execution_manager.record_task(self.root, "feature-one", "implement", "ready")
        execution_manager.record_task(self.root, "feature-one", "implement", "start", "attempt-one")
        execution_manager.receive_result(
            self.root, "feature-one", "result-one", brief(self.plan), result(self.plan)
        )
        current = execution_manager.inspect_execution(self.root, "feature-one")
        self.assertEqual("reported", current["state"]["tasks"]["implement"]["status"])
        view = bridge.live_view(self.root, "feature-one")
        self.assertEqual(
            (1, execution_state.digest(current["receipts"]["result-one"]["result"])),
            (view["tasks"][0]["acceptanceSchemaVersion"], view["tasks"][0]["resultDigest"]),
        )
        expected = {
            "executionId": "feature-one", "planRevision": view["binding"]["planRevision"],
            "planDigest": view["planDigest"], "policyDigest": view["policyDigest"],
            "controlsDigest": view["controlsDigest"], "controlsStateDigest": view["controlsStateDigest"],
        }
        acceptance = {
            "schemaVersion": 1, "taskId": "implement", "attemptId": "attempt-one",
            "resultId": "result-one", "acceptanceCriteria": ["AC-1"], "revision": "baseline",
            "command": "python -m unittest", "summary": "Independently checked the task evidence",
        }
        accepted = bridge.run(self.action("accept", expected, acceptance=acceptance))["view"]
        self.assertEqual("accepted", accepted["tasks"][0]["status"])

    def test_action_requires_digest_bound_user_confirmation(self):
        view = bridge.live_view(self.root, "feature-one")
        expected = {
            "executionId": "feature-one", "planRevision": view["binding"]["planRevision"],
            "planDigest": view["planDigest"], "policyDigest": view["policyDigest"],
            "controlsDigest": view["controlsDigest"], "controlsStateDigest": view["controlsStateDigest"],
        }
        request = self.action("approve-plan", expected)
        request["confirmationDigest"] = "sha256:" + "0" * 64
        with self.assertRaises(ContractIssue) as caught:
            bridge.run(request)
        self.assertEqual("E_DASHBOARD_CONFIRMATION", caught.exception.code)

    @unittest.skipUnless(os.name == "nt", "Windows path restrictions")
    def test_manager_bridge_rejects_network_and_alternate_stream_roots(self):
        for root in ("\\\\server\\share", str(self.root) + ":stream"):
            with self.subTest(root=root):
                with self.assertRaises(ContractIssue) as caught:
                    bridge.run({"operation": "list", "projectRoot": root})
                self.assertEqual("E_DASHBOARD_PATH", caught.exception.code)

    def test_cancellation_records_intent_without_claiming_host_stop(self):
        current = execution_manager.inspect_execution(self.root, "feature-one")
        execution_manager.approve_plan(
            self.root, "feature-one", current["planDigest"], current["policyDigest"]
        )
        execution_controls.configure_controls(self.root, autonomous_controls_policy())
        current = execution_manager.inspect_execution(self.root, "feature-one")
        control = execution_controls.inspect_controls(self.root)
        execution_controls.approve_controls(
            self.root, "feature-one", current["planDigest"], current["policyDigest"],
            control["controlsDigest"],
        )
        execution_manager.record_task(self.root, "feature-one", "implement", "ready")
        execution_manager.record_task(self.root, "feature-one", "implement", "start", "attempt-one")
        view = bridge.live_view(self.root, "feature-one")
        expected = {
            "executionId": "feature-one", "planRevision": view["binding"]["planRevision"],
            "planDigest": view["planDigest"], "policyDigest": view["policyDigest"],
            "controlsDigest": view["controlsDigest"],
            "controlsStateDigest": view["controlsStateDigest"],
        }
        result_view = bridge.run(self.action(
            "cancel", expected, taskId="implement", attemptId="attempt-one",
        ))["view"]
        self.assertEqual(1, result_view["controls"]["pendingCancellationCount"])
        self.assertEqual("unavailable", result_view["controls"]["hostCancellation"])


if __name__ == "__main__":
    unittest.main()
