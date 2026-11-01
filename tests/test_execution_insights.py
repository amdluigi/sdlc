import copy
import importlib
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.test_execution_contracts import ROOT, SCRIPTS, binding, brief, plan, result
from tests.test_execution_management import policy
from artifact_contracts import ContractIssue
import execution_manager as manager
import execution_state as state
import execution_controls as controls
import execution_telemetry as telemetry


class ExecutionInsightsTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((SCRIPTS / "execution_insights.py").is_file(),
                        "Selected execution snapshots, analytics and inactive proposals are unavailable")
        self.insights = importlib.import_module("execution_insights")
        self.temporary = tempfile.TemporaryDirectory(prefix=".insights-test-", dir=ROOT)
        self.addCleanup(self.cleanup_fixture)
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.plan = plan()
        manager.configure_policy(self.root, policy())
        manager.import_plan(self.root, self.plan)

    def cleanup_fixture(self):
        for attempt in range(6):
            try:
                self.temporary.cleanup()
                return
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.1 * (attempt + 1))

    def approve(self):
        current = manager.inspect_execution(self.root, "feature-one")
        manager.approve_plan(self.root, "feature-one", current["planDigest"], current["policyDigest"])

    def complete(self, attempt="attempt-one", outcome="accepted"):
        self.approve()
        manager.record_task(self.root, "feature-one", "implement", "ready")
        manager.record_task(self.root, "feature-one", "implement", "start", attempt)
        if outcome == "failed":
            manager.record_task(self.root, "feature-one", "implement", "fail", attempt, reason="Run failed")
            return
        task_brief, task_result = brief(self.plan), result(self.plan)
        task_brief["attemptId"] = task_result["attemptId"] = attempt
        result_id = "result-" + attempt
        manager.receive_result(self.root, "feature-one", result_id, task_brief, task_result)
        if outcome == "rejected":
            manager.record_task(self.root, "feature-one", "implement", "reject", attempt, reason="Evidence rejected")
        elif outcome == "accepted":
            manager.accept_task(self.root, "feature-one", {
                "schemaVersion": 1, "taskId": "implement", "attemptId": attempt,
                "resultId": result_id, "acceptanceCriteria": ["AC-1"],
                "revision": "baseline", "command": "python -m unittest",
                "summary": "Independent evidence check",
            })

    def revise(self):
        self.plan = copy.deepcopy(self.plan)
        self.plan["revision"] += 1
        manager.import_plan(self.root, self.plan)

    def files(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob("*") if path.is_file()}

    def issue(self, callback):
        with self.assertRaises(ContractIssue):
            callback()

    def test_snapshot_exact_contract_nulls_and_digest(self):
        before = self.files()
        snapshot = self.insights.build_snapshot(self.root, "feature-one")
        self.assertEqual({
            "schemaVersion", "kind", "binding", "approved", "writerLockPresent",
            "tasks", "controls", "snapshotDigest",
        }, set(snapshot))
        self.assertEqual("sdlc-execution-snapshot", snapshot["kind"])
        self.assertEqual(binding(self.plan), snapshot["binding"])
        self.assertFalse(snapshot["approved"])
        self.assertEqual({
            "id": "implement", "title": self.plan["tasks"][0]["title"], "status": "waiting",
            "attemptId": None, "reportedStatus": None, "estimateMs": None,
            "recordedIntervalMs": None, "requestedModel": None,
        }, snapshot["tasks"][0])
        self.assertEqual({"enabled": False, "paused": False, "pendingCancellationCount": 0,
                          "unknownNativeAttemptCount": 0}, snapshot["controls"])
        self.assertEqual(state.digest({k: v for k, v in snapshot.items() if k != "snapshotDigest"}),
                         snapshot["snapshotDigest"])
        self.assertEqual(before, self.files())
        self.assertEqual(snapshot, self.insights.build_snapshot(self.root, "feature-one"))

    def test_snapshot_current_consent_approval_and_plain_labels(self):
        self.plan["revision"] += 1
        self.plan["tasks"][0]["title"] = '<img src="local"> [metadata] & text'
        self.plan["tasks"][0]["estimateMs"] = 0
        manager.import_plan(self.root, self.plan)
        self.approve()
        snapshot = self.insights.build_snapshot(self.root, "feature-one")
        self.assertTrue(snapshot["approved"])
        self.assertEqual(self.plan["tasks"][0]["title"], snapshot["tasks"][0]["title"])
        self.assertEqual(0, snapshot["tasks"][0]["estimateMs"])
        manager.configure_policy(self.root, policy(False))
        self.assertFalse(self.insights.build_snapshot(self.root, "feature-one")["approved"])

    def test_snapshot_reports_unaccepted_failed_and_controls(self):
        self.complete(outcome="reported")
        snapshot = self.insights.build_snapshot(self.root, "feature-one")
        self.assertEqual("reported", snapshot["tasks"][0]["status"])
        self.assertEqual("completed", snapshot["tasks"][0]["reportedStatus"])
        self.assertIsInstance(snapshot["tasks"][0]["recordedIntervalMs"], int)
        controls.configure_controls(self.root, {
            "schemaVersion": 1, "enabled": True, "mode": "manual", "maxAttempts": 4,
            "allowEscalation": False, "permittedModels": [],
        })
        controls.set_pause(self.root, True, "Inspect work")
        controls.request_cancel(self.root, "feature-one", "implement", "Stop requested")
        snapshot = self.insights.build_snapshot(self.root, "feature-one")
        self.assertEqual({"enabled": True, "paused": True, "pendingCancellationCount": 1,
                          "unknownNativeAttemptCount": 0}, snapshot["controls"])
        manager.record_task(self.root, "feature-one", "implement", "reject", "attempt-one", reason="Failed evidence")
        self.assertEqual("failed", self.insights.build_snapshot(self.root, "feature-one")["tasks"][0]["status"])

    def test_snapshot_ready_running_blocked_and_cancelled_context(self):
        self.approve()
        for action, expected, attempt, reason in (
            ("ready", "ready", None, None),
            ("start", "running", "attempt-one", None),
            ("block", "blocked", None, "Awaiting evidence"),
            ("unblock", "running", None, None),
            ("cancel", "cancelled", None, "User stopped work"),
        ):
            manager.record_task(self.root, "feature-one", "implement", action, attempt, reason)
            snapshot = self.insights.build_snapshot(self.root, "feature-one")
            self.assertEqual(expected, snapshot["tasks"][0]["status"])
        analysis = self.insights.analyze_executions(self.root, ["feature-one"])
        self.assertEqual(1, analysis["summary"]["cancelledCount"])
        self.assertEqual(1, analysis["summary"]["attemptCount"])
        self.assertEqual([], self.insights.propose_estimates(self.root, ["feature-one"])["estimates"])

    def test_explicit_selection_never_reads_unselected_history(self):
        path = manager.execution_path(self.root, "unselected")
        path.write_text('{"corrupt":true}', encoding="utf-8")
        self.insights.build_snapshot(self.root, "feature-one")
        analysis = self.insights.analyze_executions(self.root, ["feature-one"])
        self.assertEqual(["feature-one"], [item["executionId"] for item in analysis["sources"]])
        self.issue(lambda: self.insights.analyze_executions(self.root, ["unselected"]))
        self.issue(lambda: self.insights.analyze_executions(self.root, ["../feature-one"]))
        self.issue(lambda: self.insights.analyze_executions(self.root, ["feature-one", "feature-one"]))
        self.issue(lambda: self.insights.analyze_executions(self.root, []))
        self.issue(lambda: self.insights.analyze_executions(self.root, [f"record-{i}" for i in range(257)]))

    def test_analytics_retains_all_revisions_rejection_failure_and_rework(self):
        self.complete(outcome="rejected")
        self.revise()
        self.complete("attempt-two", "failed")
        self.revise()
        self.complete("attempt-three", "accepted")
        before = self.files()
        analysis = self.insights.analyze_executions(self.root, ["feature-one"])
        source = analysis["sources"][0]
        self.assertEqual(manager.inspect_execution(self.root, "feature-one")["record"], source["record"])
        self.assertEqual(state.digest(source["record"]), source["recordDigest"])
        self.assertEqual(3, analysis["summary"]["revisionCount"])
        self.assertEqual(3, analysis["summary"]["attemptCount"])
        self.assertEqual(1, analysis["summary"]["acceptedCount"])
        self.assertEqual(2, analysis["summary"]["failedCount"])
        self.assertEqual(1, analysis["summary"]["rejectedCount"])
        self.assertEqual(1, analysis["summary"]["reworkTaskCount"])
        self.assertEqual(3, analysis["summary"]["missingTelemetryAttemptCount"])
        self.assertIsNone(analysis["telemetry"]["storeDigest"])
        self.assertEqual([], analysis["telemetry"]["observations"])
        self.assertEqual(before, self.files())
        self.assertEqual(analysis, self.insights.analyze_executions(self.root, ["feature-one"]))

    def test_analytics_selected_order_is_canonical(self):
        other = copy.deepcopy(self.plan)
        other["executionId"] = "another"
        manager.import_plan(self.root, other)
        left = self.insights.analyze_executions(self.root, ["feature-one", "another"])
        right = self.insights.analyze_executions(self.root, ["another", "feature-one"])
        self.assertEqual(left, right)

    def test_analysis_corruption_is_not_hidden_and_writer_lock_is_read_only(self):
        lock = manager.lock_path(self.root)
        lock.write_text("unowned", encoding="ascii")
        before = self.files()
        self.assertTrue(self.insights.build_snapshot(self.root, "feature-one")["writerLockPresent"])
        self.insights.analyze_executions(self.root, ["feature-one"])
        self.assertEqual(before, self.files())
        manager.execution_path(self.root, "feature-one").write_text("{}", encoding="ascii")
        self.issue(lambda: self.insights.build_snapshot(self.root, "feature-one"))
        self.issue(lambda: self.insights.analyze_executions(self.root, ["feature-one"]))

    def test_proposals_are_inactive_insufficient_and_review_never_adopts(self):
        self.complete()
        before = self.files()
        proposal = self.insights.propose_estimates(self.root, ["feature-one"])
        self.assertFalse(proposal["active"])
        self.assertEqual("proposed", proposal["status"])
        self.assertEqual([], proposal["routingRecommendations"])
        self.assertTrue(proposal["estimates"])
        self.assertTrue(all(item["estimateMs"] is None for item in proposal["estimates"]))
        self.assertEqual(proposal, self.insights.validate_proposal(proposal))
        for approved, status in ((True, "approved"), (False, "rejected")):
            reviewed = self.insights.review_proposal(proposal, approved, "Independent proposal review")
            self.assertEqual(status, reviewed["status"])
            self.assertFalse(reviewed["active"])
            self.assertEqual(proposal["proposalDigest"], reviewed["review"]["proposalDigest"])
            self.assertEqual(reviewed, self.insights.validate_proposal(reviewed))
        self.assertEqual(before, self.files())
        self.assertEqual("proposed", proposal["status"])

    def test_proposal_complete_samples_and_metadata_changes_are_separate(self):
        for index in range(3):
            self.complete(f"attempt-{index}")
            if index < 2:
                self.revise()
        proposal = self.insights.propose_estimates(self.root, ["feature-one"])
        declared = [item for item in proposal["estimates"] if item["basis"] == "manager-recorded-interval"]
        self.assertEqual(1, len(declared))
        self.assertEqual(3, declared[0]["sampleCount"])
        self.assertIsInstance(declared[0]["estimateMs"], int)
        self.revise()
        self.plan["tasks"][0]["title"] = "Different work"
        self.plan["revision"] += 1
        manager.import_plan(self.root, self.plan)
        self.complete("attempt-four")
        proposal = self.insights.propose_estimates(self.root, ["feature-one"])
        declared = [item for item in proposal["estimates"] if item["basis"] == "manager-recorded-interval"]
        self.assertEqual([1, 3], sorted(item["sampleCount"] for item in declared))

    def test_proposal_tampering_unknown_fields_versions_and_forged_evidence(self):
        self.complete()
        proposal = self.insights.propose_estimates(self.root, ["feature-one"])
        for key, value in (("active", True), ("schemaVersion", 2), ("unexpected", 1)):
            changed = copy.deepcopy(proposal)
            changed[key] = value
            self.issue(lambda: self.insights.validate_proposal(changed))
        changed = copy.deepcopy(proposal)
        changed["estimates"][0]["estimateMs"] = 999
        changed["proposalDigest"] = state.digest({k: v for k, v in changed.items() if k != "proposalDigest"})
        self.issue(lambda: self.insights.validate_proposal(changed))
        changed = copy.deepcopy(proposal)
        changed["analysis"]["sources"][0]["record"]["revisions"][0]["acceptances"] = {}
        self.issue(lambda: self.insights.validate_proposal(changed))
        self.issue(lambda: self.insights.review_proposal(proposal, 1, "Not a boolean"))
        self.issue(lambda: self.insights.review_proposal(proposal, True, ""))

    def observation(self, identifier="observation-one"):
        return {
            "schemaVersion": 1, "id": identifier, "binding": binding(self.plan),
            "taskId": "implement", "attemptId": "attempt-one",
            "source": {"kind": "manual-declaration", "hostId": None, "hostBuild": None, "callId": None},
            "requestedModel": None, "observedModel": None, "inventoryDigest": None,
            "window": {"clockId": "clock-one", "startMs": 100, "endMs": 150},
            "durationMs": 25, "usage": {"requests": None, "inputTokens": None, "outputTokens": None},
            "pricing": None,
        }

    def test_real_telemetry_retention_filtering_and_source_separation(self):
        self.complete()
        telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True})
        telemetry.record_observation(self.root, self.observation())
        other_plan = copy.deepcopy(self.plan)
        other_plan["executionId"] = "another"
        manager.import_plan(self.root, other_plan)
        current = manager.inspect_execution(self.root, "another")
        manager.approve_plan(self.root, "another", current["planDigest"], current["policyDigest"])
        manager.record_task(self.root, "another", "implement", "ready")
        manager.record_task(self.root, "another", "implement", "start", "other-attempt")
        other = self.observation("observation-other")
        other["binding"], other["attemptId"] = binding(other_plan), "other-attempt"
        telemetry.record_observation(self.root, other)
        telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": False})
        before = self.files()
        analysis = self.insights.analyze_executions(self.root, ["feature-one"])
        self.assertFalse(analysis["telemetry"]["enabled"])
        self.assertEqual(1, len(analysis["telemetry"]["observations"]))
        self.assertEqual(0, analysis["summary"]["missingTelemetryAttemptCount"])
        self.assertEqual(25, analysis["telemetry"]["observations"][0]["observation"]["durationMs"])
        self.assertIsNone(analysis["telemetry"]["costs"][0]["costMinor"])
        proposal = self.insights.propose_estimates(self.root, ["feature-one"])
        self.assertTrue(all(item["basis"] != "host-observed-duration" for item in proposal["estimates"]))
        self.assertEqual(proposal, self.insights.validate_proposal(proposal))
        self.assertEqual(before, self.files())
        telemetry.telemetry_path(self.root).write_text('{"schemaVersion":1}', encoding="ascii")
        self.issue(lambda: self.insights.analyze_executions(self.root, ["feature-one"]))

    def test_recomputed_digest_cannot_hide_float_counts(self):
        self.complete()
        telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True})
        telemetry.record_observation(self.root, self.observation())
        proposal = self.insights.propose_estimates(self.root, ["feature-one"])
        changed = copy.deepcopy(proposal)
        changed["estimates"][0]["sampleCount"] = 1.0
        changed["proposalDigest"] = state.digest({k: v for k, v in changed.items() if k != "proposalDigest"})
        self.issue(lambda: self.insights.validate_proposal(changed))

    def test_recomputed_digest_cannot_hide_forged_host_context(self):
        self.complete()
        telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True})
        telemetry.record_observation(self.root, self.observation())
        proposal = self.insights.propose_estimates(self.root, ["feature-one"])
        changed = copy.deepcopy(proposal)
        observation = changed["analysis"]["telemetry"]["observations"][0]["observation"]
        observation["source"] = {"kind": "host-observation", "hostId": "fake-host", "hostBuild": "fake",
                                 "callId": "fake-call"}
        fake_estimate = copy.deepcopy(changed["estimates"][0])
        fake_estimate.update(basis="host-observed-duration", source={
            "hostId": "fake-host", "hostBuild": "fake", "observedModel": None, "inventoryDigest": None,
        })
        fake_estimate["samples"][0].update(observationId=observation["id"], durationMs=25)
        changed["estimates"].insert(0, fake_estimate)
        changed["analysis"]["analysisDigest"] = state.digest({
            k: v for k, v in changed["analysis"].items() if k != "analysisDigest"
        })
        changed["proposalDigest"] = state.digest({k: v for k, v in changed.items() if k != "proposalDigest"})
        self.issue(lambda: self.insights.validate_proposal(changed))

    def test_cli_snapshot_analyze_propose_review_validate_and_strict_errors(self):
        def run(*args):
            return subprocess.run([sys.executable, "-B", str(SCRIPTS / "manage_insights.py"), *args],
                                  capture_output=True, text=True, cwd=self.root)

        for command in ("snapshot", "analyze", "propose"):
            output = run(command, "--project-root", str(self.root), "--execution-id", "feature-one")
            self.assertEqual(0, output.returncode, output.stderr)
            self.assertEqual(1, json.loads(output.stdout)["schemaVersion"])
        proposal = self.insights.propose_estimates(self.root, ["feature-one"])
        path = self.root / "proposal.json"
        path.write_text(json.dumps(proposal), encoding="utf-8")
        before = self.files()
        for command in ("validate", "review"):
            args = [command, "--project-root", str(self.root), "--input", str(path)]
            if command == "review":
                args += ["--decision", "approved", "--reason", "Reviewed"]
            output = run(*args)
            self.assertEqual(0, output.returncode, output.stderr)
            self.assertFalse(json.loads(output.stdout)["active"])
        self.assertEqual(before, self.files())
        path.write_text('{"schemaVersion":1,"schemaVersion":1}', encoding="ascii")
        output = run("validate", "--project-root", str(self.root), "--input", str(path))
        self.assertNotEqual(0, output.returncode)
        self.assertIn("error[", output.stderr)
        self.assertEqual("", output.stdout)
        self.assertNotEqual(0, run("snapshot", "--execution-id", "feature-one").returncode)

    def test_cli_snapshot_repeated_id_is_rejected(self):
        output = subprocess.run([
            sys.executable, "-B", str(SCRIPTS / "manage_insights.py"), "snapshot",
            "--project-root", str(self.root), "--execution-id", "feature-one", "--execution-id", "feature-one",
        ], capture_output=True, text=True, cwd=self.root)
        self.assertNotEqual(0, output.returncode)
        self.assertEqual("", output.stdout)
        self.assertIn("error[", output.stderr)

    def test_real_native_receipt_attribution_cost_rates_and_unknown_work(self):
        from tests.test_native_execution import HOST
        import execution_profiles
        import native_execution

        execution_profiles.install_profiles(self.root, dry_run=False)
        self.approve()
        task_brief = brief(self.plan)
        task_brief["guidance"] = []
        request = native_execution.prepare_request(self.root, "feature-one", task_brief, "developer", HOST)
        native_execution.start_request(self.root, request, state.digest(request))
        snapshot = self.insights.build_snapshot(self.root, "feature-one")
        self.assertEqual(1, snapshot["controls"]["unknownNativeAttemptCount"])
        receipt = {"schemaVersion": 1, "requestDigest": state.digest(request),
                   "hostId": HOST["id"], "hostBuild": HOST["build"], "callId": "call-one",
                   "result": result(self.plan)}
        native_execution.receive_receipt(self.root, request, receipt, "result-one")
        manager.accept_task(self.root, "feature-one", {
            "schemaVersion": 1, "taskId": "implement", "attemptId": "attempt-one", "resultId": "result-one",
            "acceptanceCriteria": ["AC-1"], "revision": "baseline", "command": "python -m unittest",
            "summary": "Independent check",
        })
        telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True})
        for index, currency in enumerate(("USD", "EUR")):
            pricing = {"currency": currency, "rateVersion": f"rate-{index}", "unit": "input-token",
                       "units": 1000, "priceMinor": 2}
            inventory = {"schemaVersion": 1, "hostId": HOST["id"], "hostBuild": HOST["build"],
                         "source": "host-observation",
                         "models": [{"id": "model-one", "available": True, "pricing": pricing}]}
            supplied = self.observation(f"observation-{index}")
            supplied.update(observedModel="model-one", inventoryDigest=state.digest(inventory), pricing=pricing)
            supplied["source"] = {"kind": "host-observation", "hostId": HOST["id"],
                                  "hostBuild": HOST["build"], "callId": "call-one"}
            supplied["window"].update(startMs=100 + index * 100, endMs=150 + index * 100)
            supplied["usage"]["inputTokens"] = 1500
            telemetry.record_observation(self.root, supplied, inventory)
        analysis = self.insights.analyze_executions(self.root, ["feature-one"])
        self.assertEqual(["USD", "EUR"], [item["currency"] for item in analysis["telemetry"]["costs"]])
        self.assertEqual([3, 3], [item["costMinor"] for item in analysis["telemetry"]["costs"]])
        self.assertNotIn("totalCost", analysis["summary"])
        proposal = self.insights.propose_estimates(self.root, ["feature-one"])
        self.assertFalse(any(item["basis"] == "host-observed-duration" for item in proposal["estimates"]))
        self.assertEqual(proposal, self.insights.validate_proposal(proposal))

    def test_project_local_ignore_proof_and_negation_are_real_git_checks(self):
        project = self.root / "enclosed"
        project.mkdir()
        ignore = self.root / ".gitignore"
        ignore.write_text("enclosed/.sdlc/local/\n", encoding="utf-8")
        manager.configure_policy(project, policy())
        manager.import_plan(project, self.plan)
        self.insights.build_snapshot(project, "feature-one")
        self.insights.analyze_executions(project, ["feature-one"])
        ignore.write_text("enclosed/.sdlc/local/\n!enclosed/.sdlc/local/\n", encoding="utf-8")
        self.issue(lambda: self.insights.build_snapshot(project, "feature-one"))
        self.issue(lambda: self.insights.analyze_executions(project, ["feature-one"]))

    def test_snapshot_unicode_and_large_integer_digest_contract(self):
        self.plan["revision"] += 1
        self.plan["tasks"][0].update(title="<script> Ω 😀 plain metadata", estimateMs=2**63 - 1)
        manager.import_plan(self.root, self.plan)
        snapshot = self.insights.build_snapshot(self.root, "feature-one")
        self.assertEqual(2**63 - 1, snapshot["tasks"][0]["estimateMs"])
        self.assertEqual("<script> Ω 😀 plain metadata", snapshot["tasks"][0]["title"])
        self.assertEqual(state.digest({k: v for k, v in snapshot.items() if k != "snapshotDigest"}),
                         snapshot["snapshotDigest"])

    def test_corrupt_selected_stored_attribution_fails_analysis_without_fallback(self):
        self.complete()
        telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True})
        telemetry.record_observation(self.root, self.observation())
        store = telemetry.inspect_telemetry(self.root)["store"]
        store["observations"][0]["observation"]["source"] = {
            "kind": "host-observation", "hostId": "fake-host", "hostBuild": "fake", "callId": "fake-call",
        }
        path = telemetry.telemetry_path(self.root)
        path.write_text(json.dumps(store), encoding="utf-8")
        before = self.files()
        self.issue(lambda: self.insights.analyze_executions(self.root, ["feature-one"]))
        self.assertEqual(before, self.files())

    def test_aggregate_capacity_is_explicit_without_pruning_records(self):
        from tests.test_execution_contracts import task

        large = plan()
        large["tasks"] = []
        for index in range(130):
            item = task(f"task-{index}")
            item.update(title="Ω" * 2000, produces=[f"output-{index}"], ownership=[f"src/file-{index}.py"])
            large["tasks"].append(item)
        for identifier in ("large-one", "large-two"):
            large["executionId"] = identifier
            manager.import_plan(self.root, large)
        before = self.files()
        self.issue(lambda: self.insights.analyze_executions(self.root, ["large-one", "large-two"]))
        self.assertEqual(before, self.files())
        self.assertEqual(130, len(self.insights.build_snapshot(self.root, "large-one")["tasks"]))

    def test_new_schema_roots_and_offline_refs(self):
        fixtures = {
            "execution-snapshot": self.insights.build_snapshot(self.root, "feature-one"),
            "execution-analysis": self.insights.analyze_executions(self.root, ["feature-one"]),
            "execution-proposal": self.insights.propose_estimates(self.root, ["feature-one"]),
        }
        schemas = {}
        for path in (SCRIPTS.parent / "contracts").glob("*.schema.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            if "$id" in data:
                schemas[data["$id"]] = data
        for name, fixture in fixtures.items():
            path = SCRIPTS.parent / "contracts" / (name + ".schema.json")
            self.assertTrue(path.is_file(), f"Strict {name} contract is unavailable")
            schema = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(set(fixture), set(schema["required"]))
            self.assertEqual(set(fixture), set(schema["properties"]))
            self.assertFalse(schema["additionalProperties"])

            def refs(node):
                if isinstance(node, dict):
                    if "$ref" in node:
                        base, _, pointer = node["$ref"].partition("#")
                        target = schemas[base] if base else schema
                        for component in pointer.lstrip("/").split("/") if pointer else ():
                            target = target[component]
                    for child in node.values():
                        refs(child)
                elif isinstance(node, list):
                    for child in node:
                        refs(child)

            refs(schema)


if __name__ == "__main__":
    unittest.main()
