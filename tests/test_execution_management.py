import copy
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.test_execution_contracts import SCRIPTS, plan, brief, result, task
from artifact_contracts import ContractIssue


def policy(enabled=True):
    return {
        "schemaVersion": 1, "enabled": enabled, "mode": "manual",
        "retention": "manual", "detailedTelemetry": False,
    }


class ExecutionManagementTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((SCRIPTS / "execution_manager.py").is_file(),
                        "Local execution management is not provided")
        self.manager = importlib.import_module("execution_manager")
        self.state = importlib.import_module("execution_state")
        self.renderer = importlib.import_module("execution_renderers")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.plan = plan()

    def activate(self):
        self.manager.configure_policy(self.root, policy())
        self.manager.import_plan(self.root, self.plan)

    def approve(self):
        inspected = self.manager.inspect_execution(self.root, "feature-one")
        self.manager.approve_plan(
            self.root, "feature-one", inspected["planDigest"], inspected["policyDigest"]
        )

    def start(self):
        self.manager.record_task(self.root, "feature-one", "implement", "ready")
        self.manager.record_task(self.root, "feature-one", "implement", "start", "attempt-one")

    def receipt(self):
        self.manager.receive_result(
            self.root, "feature-one", "result-one", brief(self.plan), result(self.plan)
        )

    def accept(self):
        self.manager.accept_task(self.root, "feature-one", {
            "schemaVersion": 1, "taskId": "implement", "attemptId": "attempt-one",
            "resultId": "result-one", "acceptanceCriteria": ["AC-1"],
            "revision": "baseline", "command": "python -m unittest",
            "summary": "Independent controller checked the evidence",
        })

    def assert_issue(self, callback, code):
        with self.assertRaises(ContractIssue) as caught:
            callback()
        self.assertEqual(code, caught.exception.code)

    def test_disabled_and_dry_run_write_nothing(self):
        before = set(self.root.rglob("*"))
        self.assert_issue(lambda: self.manager.import_plan(self.root, self.plan), "E_EXECUTION_DISABLED")
        self.assertEqual(before, set(self.root.rglob("*")))
        self.manager.configure_policy(self.root, policy(), dry_run=True)
        self.assertEqual(before, set(self.root.rglob("*")))
        self.assertFalse((self.root / ".sdlc" / "config.json").exists())

    def test_manual_end_to_end_receipt_is_not_accepted_completion(self):
        self.activate()
        self.assert_issue(lambda: self.start(), "E_EXECUTION_APPROVAL")
        self.approve()
        self.start()
        self.receipt()
        inspected = self.manager.inspect_execution(self.root, "feature-one")
        self.assertEqual("reported", inspected["state"]["tasks"]["implement"]["status"])
        self.accept()
        inspected = self.manager.inspect_execution(self.root, "feature-one")
        self.assertEqual("accepted", inspected["state"]["tasks"]["implement"]["status"])
        report = self.renderer.render_execution(inspected)
        self.assertIn("## Gantt", report)
        self.assertIn("| implement |", report)
        self.assertIn("accepted", report)
        self.assertIn("unavailable", report)
        self.assertIn("Structural", report)
        self.assertNotIn("PR-ready", report)
        self.assertIn("Mode: manual metadata recording only; no worker or command dispatch.", report)
        self.assertIn("- Independent judgment: ", report)
        self.assertIn("; controller command ", report)
        self.assertNotIn("Independent operator validation", report)
        import execution_insights
        snapshot = execution_insights.build_snapshot(self.root, "feature-one")
        self.assertEqual(1, snapshot["schemaVersion"])
        self.assertNotIn("acceptanceBasis", snapshot["tasks"][0])

    def test_replay_is_immutable_and_reproducible(self):
        self.activate()
        self.approve()
        self.start()
        self.receipt()
        inspected = self.manager.inspect_execution(self.root, "feature-one")
        original = copy.deepcopy(inspected)
        replayed = self.state.replay_execution(
            inspected["plan"], inspected["events"], inspected["receipts"],
            inspected["recordedPolicyDigest"], inspected["acceptances"], inspected["approvals"]
        )
        self.assertEqual(inspected["state"], replayed)
        self.assertEqual(original, inspected)

    def test_receipt_idempotence_and_conflict_are_atomic(self):
        self.activate()
        self.approve()
        self.start()
        self.receipt()
        before = self.manager.inspect_execution(self.root, "feature-one")
        self.receipt()
        self.assertEqual(before, self.manager.inspect_execution(self.root, "feature-one"))
        changed = result(self.plan)
        changed["findings"] = ["A changed receipt"]
        self.assert_issue(
            lambda: self.manager.receive_result(self.root, "feature-one", "result-one", brief(self.plan), changed),
            "E_EXECUTION_DUPLICATE",
        )
        self.assertEqual(before, self.manager.inspect_execution(self.root, "feature-one"))

    def test_policy_drift_revokes_approval_and_disable_prevents_writes(self):
        self.activate()
        self.approve()
        self.manager.configure_policy(self.root, policy(False))
        before = self.manager.inspect_execution(self.root, "feature-one")
        self.assert_issue(lambda: self.start(), "E_EXECUTION_DISABLED")
        self.assertEqual(before, self.manager.inspect_execution(self.root, "feature-one"))
        self.assert_issue(
            lambda: self.manager.approve_plan(self.root, "feature-one", "sha256:" + "0" * 64, before["policyDigest"]),
            "E_EXECUTION_DISABLED",
        )

    def test_revisions_are_immutable_and_new_plan_needs_approval(self):
        self.activate()
        self.approve()
        changed = copy.deepcopy(self.plan)
        changed["revision"] = 3
        changed["tasks"][0]["title"] = "Revised task"
        self.manager.import_plan(self.root, changed)
        self.assertFalse(self.manager.inspect_execution(self.root, "feature-one")["state"]["approved"])
        self.assert_issue(lambda: self.start(), "E_EXECUTION_APPROVAL")
        changed["tasks"][0]["title"] = "Illegal same-revision overwrite"
        self.assert_issue(lambda: self.manager.import_plan(self.root, changed), "E_EXECUTION_REVISION")

    def test_dependencies_require_independent_acceptance(self):
        other = task("verify")
        other.update(prerequisites=["implement"], consumes=["implementation"], produces=["verified"],
                     ownership=["tests/verify.py"])
        self.plan["tasks"].append(other)
        self.activate()
        self.approve()
        self.assert_issue(
            lambda: self.manager.record_task(self.root, "feature-one", "verify", "ready"),
            "E_EXECUTION_TRANSITION",
        )
        self.start()
        self.receipt()
        self.assert_issue(
            lambda: self.manager.record_task(self.root, "feature-one", "verify", "ready"),
            "E_EXECUTION_TRANSITION",
        )
        self.accept()
        self.manager.record_task(self.root, "feature-one", "verify", "ready")

    def test_shared_case_aliases_and_serial_edits_block_start(self):
        other = task("other")
        other.update(produces=["other"], ownership=["SRC/FEATURE.PY"])
        self.plan["tasks"].append(other)
        self.activate()
        self.approve()
        self.start()
        self.manager.record_task(self.root, "feature-one", "other", "ready")
        self.assert_issue(
            lambda: self.manager.record_task(self.root, "feature-one", "other", "start", "attempt-other"),
            "E_EXECUTION_CONFLICT",
        )

    def test_separate_executions_cannot_hold_concurrent_project_attempts(self):
        self.activate()
        self.approve()
        other = copy.deepcopy(self.plan)
        other["executionId"] = "other-execution"
        self.manager.import_plan(self.root, other)
        inspected = self.manager.inspect_execution(self.root, "other-execution")
        self.manager.approve_plan(self.root, "other-execution",
                                  inspected["planDigest"], inspected["policyDigest"])
        self.start()
        self.manager.record_task(self.root, "other-execution", "implement", "ready")
        self.assert_issue(lambda: self.manager.record_task(
            self.root, "other-execution", "implement", "start", "other-attempt"), "E_EXECUTION_CONFLICT")
        self.receipt()
        self.assert_issue(lambda: self.manager.record_task(
            self.root, "other-execution", "implement", "start", "other-attempt"), "E_EXECUTION_CONFLICT")
        self.accept()
        self.manager.record_task(self.root, "other-execution", "implement", "start", "other-attempt")

    def test_deletion_cannot_release_an_unresolved_attempt_claim(self):
        self.activate()
        self.approve()
        self.start()
        self.assert_issue(
            lambda: self.manager.delete_execution(self.root, "feature-one"), "E_EXECUTION_TRANSITION")

    def test_corrupt_peer_record_blocks_start_without_changing_selected_history(self):
        self.activate()
        self.approve()
        other = copy.deepcopy(self.plan)
        other["executionId"] = "other-execution"
        self.manager.import_plan(self.root, other)
        self.manager.execution_path(self.root, "other-execution").write_text("{", encoding="utf-8")
        self.manager.record_task(self.root, "feature-one", "implement", "ready")
        selected = self.manager.execution_path(self.root, "feature-one")
        before = selected.read_bytes()
        self.assert_issue(lambda: self.manager.record_task(
            self.root, "feature-one", "implement", "start", "attempt-one"), "E_JSON_SYNTAX")
        self.assertEqual(before, selected.read_bytes())

    def test_exact_project_record_capacity_rejects_next_import_without_pruning(self):
        self.activate()
        template = self.manager.inspect_execution(self.root, "feature-one")["record"]
        directory = self.manager.execution_path(self.root, "feature-one").parent
        for index in range(254):
            identifier = "execution-" + str(index)
            record = copy.deepcopy(template)
            record["executionId"] = identifier
            revision = record["revisions"][0]
            revision["plan"]["executionId"] = identifier
            revision["events"][0]["binding"]["executionId"] = identifier
            revision["events"][0]["binding"]["planDigest"] = self.state.digest(revision["plan"])
            (directory / (identifier + ".json")).write_text(
                json.dumps(self.state.validate_record(record)), encoding="utf-8")
        last = copy.deepcopy(self.plan)
        last["executionId"] = "last-slot"
        self.manager.import_plan(self.root, last)
        self.assertEqual(256, len(self.manager._record_ids(self.root)))
        overflow = copy.deepcopy(last)
        overflow["executionId"] = "over-capacity"
        self.assert_issue(lambda: self.manager.import_plan(self.root, overflow), "E_EXECUTION_LIMIT")
        self.assertEqual(256, len(self.manager._record_ids(self.root)))
        self.assertFalse(self.manager.execution_path(self.root, "over-capacity").exists())

    def test_corrupt_record_lock_and_failed_promotion_preserve_state(self):
        self.activate()
        path = self.manager.execution_path(self.root, "feature-one")
        before = path.read_bytes()
        with mock.patch.object(self.manager, "_replace", side_effect=OSError("promotion failed")):
            self.assert_issue(lambda: self.approve(), "E_EXECUTION_WRITE")
        self.assertEqual(before, path.read_bytes())
        self.assertFalse(list(path.parent.glob("*.tmp")))
        lock = self.manager.lock_path(self.root)
        lock.write_text("active or abandoned writer", encoding="utf-8")
        self.assert_issue(lambda: self.approve(), "E_EXECUTION_BUSY")
        self.assertEqual(before, path.read_bytes())
        lock.unlink()
        path.write_text('{"schemaVersion":', encoding="utf-8")
        self.assert_issue(lambda: self.manager.inspect_execution(self.root, "feature-one"), "E_JSON_SYNTAX")
        self.assertEqual('{"schemaVersion":', path.read_text())

    def test_unsafe_ids_unignored_storage_and_linked_record_are_rejected(self):
        self.activate()
        self.assert_issue(lambda: self.manager.inspect_execution(self.root, "../outside"), "E_EXECUTION_ID")
        outside = self.root / "ordinary"
        outside.mkdir()
        self.assert_issue(
            lambda: self.manager.configure_policy(outside, policy()),
            "E_EXECUTION_STORAGE",
        )
        path = self.manager.execution_path(self.root, "feature-one")
        destination = self.root / "real-records"
        destination.mkdir()
        path.rename(destination / path.name)
        path.parent.rmdir()
        try:
            path.parent.symlink_to(destination, target_is_directory=True)
        except OSError as error:
            if os.name != "nt" or error.winerror != 1314:
                raise
            subprocess.run(["cmd", "/c", "mklink", "/J", str(path.parent), str(destination)],
                           check=True, capture_output=True)
        self.assert_issue(
            lambda: self.manager.inspect_execution(self.root, "feature-one"), "E_EXECUTION_PATH"
        )

    def test_controller_acceptance_cannot_be_a_worker_report(self):
        self.activate()
        self.approve()
        self.start()
        self.receipt()
        self.assert_issue(
            lambda: self.manager.accept_task(self.root, "feature-one", result(self.plan)),
            "E_SCHEMA_REQUIRED",
        )
        inspected = self.manager.inspect_execution(self.root, "feature-one")
        self.assertEqual("reported", inspected["state"]["tasks"]["implement"]["status"])

    def test_disable_reenable_cannot_revive_old_approval(self):
        self.activate()
        self.approve()
        self.manager.configure_policy(self.root, policy(False))
        self.manager.configure_policy(self.root, policy(True))
        inspected = self.manager.inspect_execution(self.root, "feature-one")
        self.assertFalse(inspected["state"]["approved"])
        self.assert_issue(lambda: self.start(), "E_EXECUTION_APPROVAL")

    def test_failed_unavailable_and_stale_verification_cannot_be_accepted(self):
        self.activate()
        self.approve()
        self.start()
        bad = result(self.plan)
        bad["verification"][0]["result"] = "unavailable"
        self.manager.receive_result(self.root, "feature-one", "result-one", brief(self.plan), bad)
        self.assert_issue(lambda: self.accept(), "E_EXECUTION_EVIDENCE")
        self.assertEqual("reported", self.manager.inspect_execution(
            self.root, "feature-one")["state"]["tasks"]["implement"]["status"])

    def test_active_and_reported_attempts_block_revision_and_other_start(self):
        self.activate()
        self.approve()
        self.start()
        revised = copy.deepcopy(self.plan)
        revised["revision"] = 3
        self.assert_issue(lambda: self.manager.import_plan(self.root, revised), "E_EXECUTION_TRANSITION")
        self.receipt()
        self.assert_issue(lambda: self.manager.import_plan(self.root, revised), "E_EXECUTION_TRANSITION")

    def test_record_capacity_and_privileged_event_corruption_fail_closed(self):
        self.activate()
        path = self.manager.execution_path(self.root, "feature-one")
        original = path.read_bytes()
        inspected = self.manager.inspect_execution(self.root, "feature-one")
        record = inspected["record"]
        record["revisions"] *= 257
        self.assert_issue(lambda: self.state.validate_record(record), "E_EXECUTION_LIMIT")
        self.assertEqual(original, path.read_bytes())
        self.approve()
        inspected = self.manager.inspect_execution(self.root, "feature-one")
        inspected["record"]["revisions"][-1]["approvals"] = {}
        self.assert_issue(lambda: self.state.validate_record(inspected["record"]), "E_SCHEMA_TYPE")

    def test_exact_event_capacity_and_next_event_failure(self):
        self.activate()
        self.approve()
        self.start()
        record = self.manager.inspect_execution(self.root, "feature-one")["record"]
        revision = record["revisions"][-1]
        while len(revision["events"]) < 256:
            self.manager._append(revision, "TASK_PROGRESS_UPDATED", "implement", "attempt-one",
                                 {"message": "Manual progress"})
        validated = self.state.validate_record(record)
        self.assertEqual(256, len(validated["revisions"][-1]["events"]))
        self.manager._append(revision, "TASK_PROGRESS_UPDATED", "implement", "attempt-one",
                             {"message": "Over capacity"})
        self.assert_issue(lambda: self.state.validate_record(record), "E_EXECUTION_LIMIT")

    def test_windows_alias_and_directory_ownership_fail_before_start(self):
        self.plan["tasks"][0]["ownership"] = ["src/NUL.txt"]
        self.activate()
        self.approve()
        self.manager.record_task(self.root, "feature-one", "implement", "ready")
        self.assert_issue(lambda: self.manager.record_task(
            self.root, "feature-one", "implement", "start", "attempt-one"), "E_EXECUTION_PATH")

    def test_recovery_inspection_never_steals_a_writer_lock(self):
        self.activate()
        lock = self.manager.lock_path(self.root)
        lock.write_text("unknown writer", encoding="ascii")
        self.assertTrue(self.manager.inspect_execution(self.root, "feature-one")["writerLockPresent"])
        self.assertEqual("unknown writer", lock.read_text())

    def test_real_competing_manager_cannot_write_or_remove_owner_lock(self):
        self.activate()
        source = self.root / "policy-input.json"
        source.write_text(json.dumps(policy(False)), encoding="utf-8")
        before = self.manager.inspect_execution(self.root, "feature-one")
        with self.manager._writer(self.root):
            lock = self.manager.lock_path(self.root)
            owner = lock.read_bytes()
            competing = subprocess.run(
                [sys.executable, "-B", str(SCRIPTS / "manage_execution.py"), "configure",
                 "--project-root", str(self.root), "--input", str(source)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(0, competing.returncode)
            self.assertIn("E_EXECUTION_BUSY", competing.stderr)
            self.assertEqual(owner, lock.read_bytes())
        self.assertEqual(before, self.manager.inspect_execution(self.root, "feature-one"))

    def test_abrupt_exit_before_promotion_leaves_valid_history_and_recovery_barrier(self):
        self.activate()
        path = self.manager.execution_path(self.root, "feature-one")
        original = path.read_bytes()
        inspected = self.manager.inspect_execution(self.root, "feature-one")
        program = (
            "import os,sys; sys.path.insert(0,sys.argv[1]); import execution_manager as m; "
            "m._replace=lambda *args: os._exit(17); "
            "m.approve_plan(sys.argv[2], 'feature-one', sys.argv[3], sys.argv[4])"
        )
        interrupted = subprocess.run(
            [sys.executable, "-B", "-c", program, str(SCRIPTS), str(self.root),
             inspected["planDigest"], inspected["policyDigest"]], capture_output=True, text=True,
        )
        self.assertEqual(17, interrupted.returncode, interrupted.stderr)
        self.assertEqual(original, path.read_bytes())
        self.assertTrue(self.manager.inspect_execution(self.root, "feature-one")["writerLockPresent"])
        self.assert_issue(lambda: self.approve(), "E_EXECUTION_BUSY")

    def test_strict_json_and_diagnostics_do_not_expose_stored_content(self):
        self.activate()
        path = self.manager.execution_path(self.root, "feature-one")
        sentinel = "private-evidence-sentinel"
        for content, code in (
            ('{"' + sentinel + '":0,"' + sentinel + '":1}', "E_JSON_DUPLICATE"),
            ('{"value":NaN}', "E_JSON_SYNTAX"),
            ("x" * (2 * 1024 * 1024 + 1), "E_INPUT_TOO_LARGE"),
        ):
            path.write_text(content, encoding="utf-8")
            with self.assertRaises(ContractIssue) as caught:
                self.manager.inspect_execution(self.root, "feature-one")
            self.assertEqual(code, caught.exception.code)
            self.assertNotIn(sentinel, caught.exception.cli_message())
            self.assertNotIn(str(self.root), caught.exception.cli_message())

    def test_excessively_nested_stored_json_has_a_stable_error(self):
        self.activate()
        path = self.manager.execution_path(self.root, "feature-one")
        path.write_text("[" * 10000 + "0" + "]" * 10000, encoding="utf-8")
        self.assert_issue(
            lambda: self.manager.inspect_execution(self.root, "feature-one"), "E_EXECUTION_JSON")

    def test_nonregular_git_projects_use_only_proven_ignored_local_storage(self):
        outer = self.root / "enclosing"
        outer.mkdir()
        subprocess.run(["git", "init", "-q", str(outer)], check=True)
        project = outer / "project"
        project.mkdir()
        (outer / ".gitignore").write_text("project/.sdlc/local/\n", encoding="utf-8")
        self.manager.configure_policy(project, policy())
        self.manager.import_plan(project, self.plan)
        expected = project / ".sdlc" / "local" / "executions" / "feature-one.json"
        self.assertEqual(expected, self.manager.execution_path(project, "feature-one"))
        (outer / ".gitignore").write_text(
            "project/.sdlc/local/\n!project/.sdlc/local/\n", encoding="utf-8")
        self.assert_issue(lambda: self.manager.inspect_execution(project, "feature-one"), "E_EXECUTION_STORAGE")

    def test_schema_roots_and_offline_references_match_new_contracts(self):
        self.activate()
        inspected = self.manager.inspect_execution(self.root, "feature-one")
        fixtures = {
            "execution-policy": policy(),
            "execution-consent": inspected["record"]["revisions"][-1]["consent"],
            "execution-record": inspected["record"],
            "execution-state": inspected["state"],
            "execution-acceptance": {
                "schemaVersion": 1, "taskId": "implement", "attemptId": "attempt-one",
                "resultId": "result-one", "acceptanceCriteria": ["AC-1"],
                "revision": "baseline", "command": "python -m unittest", "summary": "Checked",
            },
        }
        schemas = {
            data["$id"]: data for data in (
                json.loads(path.read_text(encoding="utf-8"))
                for path in (SCRIPTS.parent / "contracts").glob("*.schema.json")
            ) if "$id" in data
        }
        for name, fixture in fixtures.items():
            schema = schemas["urn:sdlc:" + name + ":1"]
            self.assertEqual(set(fixture), set(schema["required"]))
            self.assertEqual(set(fixture), set(schema["properties"]))
            self.assertFalse(schema["additionalProperties"])

            def check_refs(node):
                if isinstance(node, dict):
                    if "$ref" in node:
                        base, _, pointer = node["$ref"].partition("#")
                        target = schemas[base] if base else schema
                        for component in pointer.lstrip("/").split("/") if pointer else ():
                            target = target[component]
                    for child in node.values():
                        check_refs(child)
                elif isinstance(node, list):
                    for child in node:
                        check_refs(child)

            check_refs(schema)

    def test_closed_policy_rejects_telemetry_and_unknown_fields(self):
        bad = policy()
        bad["detailedTelemetry"] = True
        self.assert_issue(lambda: self.manager.configure_policy(self.root, bad), "E_EXECUTION_POLICY")
        bad = policy()
        bad["enabled"] = 1
        self.assert_issue(lambda: self.manager.configure_policy(self.root, bad), "E_SCHEMA_TYPE")

    def test_reports_escape_labels_and_do_not_invent_schedule(self):
        self.plan["tasks"][0]["title"] = "Unsafe | <script>alert(1)</script>"
        self.activate()
        report = self.renderer.render_execution(self.manager.inspect_execution(self.root, "feature-one"))
        self.assertNotIn("<script>", report)
        self.assertIn("pending approval", report.lower())
        self.assertIn("incomplete", report.lower())
        self.assertNotIn("0 ms", report)

    def test_explicit_deletion_removes_only_selected_execution(self):
        self.activate()
        other = copy.deepcopy(self.plan)
        other["executionId"] = "other-execution"
        self.manager.import_plan(self.root, other)
        self.manager.delete_execution(self.root, "feature-one")
        self.assertTrue(self.manager.execution_path(self.root, "other-execution").is_file())
        self.assertFalse(self.manager.execution_path(self.root, "feature-one").exists())

    def test_cli_inspect_and_report_are_read_only(self):
        self.activate()
        path = self.manager.execution_path(self.root, "feature-one")
        before = path.read_bytes()
        completed = subprocess.run(
            [sys.executable, "-B", str(SCRIPTS / "manage_execution.py"), "report",
             "--project-root", str(self.root), "--execution-id", "feature-one"],
            capture_output=True, text=True,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("feature-one", completed.stdout)
        self.assertEqual(before, path.read_bytes())


if __name__ == "__main__":
    unittest.main()
