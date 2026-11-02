import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_execution_contracts import ROOT, brief, plan, result
from tests.test_execution_management import policy

import execution_manager
import execution_state
import execution_renderers
from artifact_contracts import ContractIssue


BRIDGE_PATH = ROOT / "packages" / "sdlc-dashboard" / "manager_bridge.py"
SPEC = importlib.util.spec_from_file_location("sdlc_project_orchestration_bridge", BRIDGE_PATH)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class ProjectOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        execution_manager.configure_policy(self.root, policy())
        execution_manager.import_plan(self.root, plan())

    def context_request(self, content, expected_revision, scope="shared", agent_id=None):
        view = bridge.live_view(self.root, "feature-one")
        expected = {
            "executionId": "feature-one",
            "planRevision": view["binding"]["planRevision"],
            "planDigest": view["planDigest"],
            "policyDigest": view["policyDigest"],
            "controlsDigest": view["controlsDigest"],
            "controlsStateDigest": view["controlsStateDigest"],
        }
        context = {
            "scope": scope, "agentId": agent_id, "content": content,
            "expectedRevision": expected_revision,
        }
        material = {
            "operation": "update-context", "expectedBinding": expected, "context": context,
        }
        return {
            "operation": "update-context", "projectRoot": str(self.root),
            "executionId": "feature-one", "expectedBinding": expected,
            "context": context, "confirmationDigest": execution_state.digest(material),
        }

    def test_ac22_context_is_manager_owned_persistent_and_digest_confirmed(self):
        before = bridge.live_view(self.root, "feature-one")
        self.assertEqual(1, execution_manager._load(self.root, "feature-one")["schemaVersion"])
        self.assertEqual("proposed", before["gantt"]["tasks"][0]["status"])
        response = bridge.run(self.context_request("API contract agreed; tests pending.", 0))

        self.assertEqual("API contract agreed; tests pending.", response["view"]["context"]["shared"]["content"])
        self.assertEqual("operator", response["view"]["context"]["shared"]["source"])
        self.assertEqual(4, execution_manager._load(self.root, "feature-one")["schemaVersion"])
        self.assertEqual(before["tasks"], response["view"]["tasks"])

    def test_ac23_stale_context_revision_is_rejected_without_overwriting(self):
        bridge.run(self.context_request("Current decision.", 0))
        stale = self.context_request("Stale overwrite.", 0)

        with self.assertRaises(ContractIssue) as caught:
            bridge.run(stale)

        self.assertEqual("E_EXECUTION_STALE_VIEW", caught.exception.code)
        current = bridge.live_view(self.root, "feature-one")
        self.assertEqual("Current decision.", current["context"]["shared"]["content"])

    def test_ac22_operator_can_record_attributed_specialist_context(self):
        response = bridge.run(self.context_request(
            "Own the public API compatibility tests.", 0, "agent", "developer",
        ))
        entry = response["view"]["context"]["agents"]["developer"]
        self.assertEqual("operator", entry["source"])
        self.assertEqual("operator", entry["author"])
        self.assertEqual("developer", entry["agent"])
        self.assertEqual("Own the public API compatibility tests.", entry["content"])

    def test_ac23_context_update_rejects_stale_plan_and_over_limit_note(self):
        view = bridge.live_view(self.root, "feature-one")
        with self.assertRaises(ContractIssue) as stale:
            execution_manager.update_context(
                self.root, "feature-one", "shared", None, "Stale plan note.",
                "sha256:" + "f" * 64, 0,
            )
        self.assertEqual("E_EXECUTION_STALE_VIEW", stale.exception.code)
        with self.assertRaises(ContractIssue):
            execution_manager.update_context(
                self.root, "feature-one", "shared", None, "x" * 2049,
                view["planDigest"], 0,
            )
        self.assertEqual(0, bridge.live_view(self.root, "feature-one")["context"]["revision"])

    def test_ac25_execution_report_includes_time_scaled_gantt(self):
        inspected = execution_manager.inspect_execution(self.root, "feature-one")
        from execution_renderers import render_execution

        report = render_execution(inspected)

        self.assertIn("## Gantt", report)
        self.assertIn("relative estimate", report.lower())
        self.assertIn("unknown", report.lower())

    def test_ac25_gantt_uses_dependency_offsets_and_recorded_event_intervals(self):
        project = plan()
        first = project["tasks"][0]
        first["estimateMs"] = 100
        second = dict(first)
        second.update(
            id="verify", title="Verify the implementation", prerequisites=["implement"],
            consumes=["implementation"], produces=["verification"], ownership=["tests/test_feature.py"],
            estimateMs=50,
        )
        project["tasks"].append(second)
        projected = execution_state.initial_execution_state(project)
        projected["tasks"]["implement"]["attemptId"] = "attempt-one"
        events = [
            {"taskId": "implement", "attemptId": "attempt-one", "type": "TASK_STARTED",
             "recordedAt": "2026-01-01T00:00:00Z"},
            {"taskId": "implement", "attemptId": "attempt-one", "type": "TASK_RESULT_RECEIVED",
             "recordedAt": "2026-01-01T00:00:05Z"},
        ]

        gantt = execution_renderers.build_gantt(project, projected["tasks"], events)

        self.assertEqual(0, gantt["tasks"][0]["plannedStartMs"])
        self.assertEqual(100, gantt["tasks"][0]["plannedEndMs"])
        self.assertEqual(100, gantt["tasks"][1]["plannedStartMs"])
        self.assertEqual(150, gantt["tasks"][1]["plannedEndMs"])
        self.assertEqual(0, gantt["tasks"][0]["actualStartOffsetMs"])
        self.assertEqual(5000, gantt["tasks"][0]["actualDurationMs"])
        self.assertIsNone(gantt["tasks"][1]["actualDurationMs"])
        self.assertEqual(gantt["tasks"][0]["agent"], gantt["tasks"][1]["agent"])

    def test_ac25_gantt_offsets_do_not_depend_on_task_list_order(self):
        project = plan()
        first = project["tasks"][0]
        second = dict(first)
        first["estimateMs"] = 100
        second.update(
            id="verify", title="Verify the implementation", prerequisites=["implement"],
            consumes=["implementation"], produces=["verification"], ownership=["tests/test_feature.py"],
            estimateMs=50,
        )
        project["tasks"] = [second, first]

        gantt = execution_renderers.build_gantt(project)

        self.assertEqual(["verify", "implement"], [task["id"] for task in gantt["tasks"]])
        self.assertEqual((100, 150), (gantt["tasks"][0]["plannedStartMs"], gantt["tasks"][0]["plannedEndMs"]))
        self.assertEqual((0, 100), (gantt["tasks"][1]["plannedStartMs"], gantt["tasks"][1]["plannedEndMs"]))
        self.assertTrue(gantt["plannedComplete"])

    def test_ac25_gantt_marks_offsets_outside_signed_integer_range_incomplete(self):
        project = plan()
        first = project["tasks"][0]
        first["estimateMs"] = 2**63 - 1
        second = dict(first)
        second.update(
            id="verify", title="Verify the implementation", prerequisites=["implement"],
            consumes=["implementation"], produces=["verification"], ownership=["tests/test_feature.py"],
            estimateMs=1,
        )
        project["tasks"].append(second)

        gantt = execution_renderers.build_gantt(project)

        self.assertEqual(2**63 - 1, gantt["tasks"][0]["plannedEndMs"])
        self.assertEqual(2**63 - 1, gantt["tasks"][1]["plannedStartMs"])
        self.assertIsNone(gantt["tasks"][1]["plannedEndMs"])
        self.assertFalse(gantt["plannedComplete"])
        self.assertIn("signed 64-bit", gantt["plannedBasis"])

    def test_ac23_manual_worker_context_is_saved_without_accepting_result(self):
        inspected = execution_manager.inspect_execution(self.root, "feature-one")
        execution_manager.approve_plan(
            self.root, "feature-one", inspected["planDigest"], inspected["policyDigest"],
        )
        execution_manager.record_task(self.root, "feature-one", "implement", "ready")
        execution_manager.record_task(self.root, "feature-one", "implement", "start", "attempt-one")
        worker_result = {**result(plan()), "schemaVersion": 2,
                         "contextUpdate": "The migration contract is ready for independent review."}

        execution_manager.receive_result(self.root, "feature-one", "manual-one", brief(plan()), worker_result)

        inspected = execution_manager.inspect_execution(self.root, "feature-one")
        entry = inspected["context"]["agents"]["developer"]
        self.assertEqual("worker", entry["source"])
        self.assertEqual("developer", entry["author"])
        self.assertEqual("The migration contract is ready for independent review.", entry["content"])
        self.assertEqual("reported", inspected["state"]["tasks"]["implement"]["status"])
        self.assertIsNone(inspected["state"]["tasks"]["implement"]["acceptance"])


if __name__ == "__main__":
    unittest.main()
