import copy
import importlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.test_execution_contracts import SCRIPTS, plan, brief, result
from tests.test_execution_management import policy
from tests.test_native_execution import HOST
from artifact_contracts import ContractIssue


def controls_policy(enabled=True):
    return {"schemaVersion": 1, "enabled": enabled, "mode": "manual",
            "maxAttempts": 2, "allowEscalation": False, "permittedModels": ["model-one"]}


def inventory():
    return {"schemaVersion": 1, "hostId": "observed-host", "hostBuild": "build-one",
            "source": "host-observation", "models": [
                {"id": "model-one", "available": True, "pricing": None},
                {"id": "model-two", "available": False, "pricing": None},
            ]}


def batch_controls_policy(enabled=True):
            return {
                "schemaVersion": 3, "enabled": enabled, "mode": "batch",
                "maxAttempts": 2, "allowEscalation": True, "permittedModels": ["model-one", "model-two"],
                "maxBatchTasks": 8, "maxBatchCalls": 32, "maxBatchToolCalls": 32, "maxBatchWallMs": 300000,
                "maxBatchInputBytes": 262144, "maxBatchOutputBytes": 262144,
            }


def autonomous_controls_policy(enabled=True):
    return {
        **batch_controls_policy(enabled),
        "schemaVersion": 4,
        "mode": "autonomous",
    }


class AutonomousPolicyContractTests(unittest.TestCase):
    def test_explicit_autonomous_policy_uses_version_four_finite_bounds(self):
        controls = importlib.import_module("execution_controls")
        policy = autonomous_controls_policy()
        self.assertEqual(policy, controls.validate_controls_policy(policy))
        invalid = {**policy, "mode": "batch"}
        with self.assertRaises(ContractIssue):
            controls.validate_controls_policy(invalid)


class ExecutionControlsTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((SCRIPTS / "execution_controls.py").is_file(), "Execution controls not provided")
        self.controls = importlib.import_module("execution_controls")
        self.manager = importlib.import_module("execution_manager")
        self.native = importlib.import_module("native_execution")
        self.state = importlib.import_module("execution_state")
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.plan = plan()

    def activate(self):
        self.manager.configure_policy(self.root, policy())
        self.manager.import_plan(self.root, self.plan)
        current = self.manager.inspect_execution(self.root, "feature-one")
        self.manager.approve_plan(self.root, "feature-one", current["planDigest"], current["policyDigest"])

    def approve(self, execution_id="feature-one"):
        current = self.manager.inspect_execution(self.root, execution_id)
        controls = self.controls.inspect_controls(self.root)
        return self.controls.approve_controls(
            self.root, execution_id, current["planDigest"], current["policyDigest"], controls["controlsDigest"])

    def start(self, attempt="attempt-one", execution_id="feature-one"):
        self.manager.record_task(self.root, execution_id, "implement", "ready")
        return self.manager.record_task(self.root, execution_id, "implement", "start", attempt)

    def issue(self, callback, code=None):
        with self.assertRaises(ContractIssue) as caught:
            callback()
        if code:
            self.assertEqual(code, caught.exception.code)

    def test_absent_and_dry_run_preserve_files_and_legacy_start(self):
        before = set(self.root.rglob("*"))
        self.assertFalse(self.controls.inspect_controls(self.root)["enabled"])
        self.controls.configure_controls(self.root, controls_policy(), dry_run=True)
        self.assertEqual(before, set(self.root.rglob("*")))
        self.activate()
        self.start()

    def test_controls_require_separate_fresh_approval(self):
        self.activate()
        self.controls.configure_controls(self.root, controls_policy())
        self.issue(lambda: self.start(), "E_CONTROLS_APPROVAL")
        self.approve()
        self.manager.record_task(self.root, "feature-one", "implement", "start", "attempt-one")

    def test_policy_round_trip_cannot_revive_controls_approval(self):
        self.activate()
        self.controls.configure_controls(self.root, controls_policy())
        self.approve()
        self.controls.configure_controls(self.root, controls_policy(False))
        self.controls.configure_controls(self.root, controls_policy())
        self.issue(lambda: self.start(), "E_CONTROLS_APPROVAL")

    def test_pause_blocks_new_work_even_after_disable(self):
        self.activate()
        self.controls.configure_controls(self.root, controls_policy())
        self.approve()
        self.controls.set_pause(self.root, True, "Explicit pause")
        self.controls.configure_controls(self.root, controls_policy(False))
        self.issue(lambda: self.start(), "E_CONTROLS_PAUSED")
        self.controls.configure_controls(self.root, controls_policy())
        self.controls.set_pause(self.root, False, "Explicit resume")
        self.approve()
        self.manager.record_task(self.root, "feature-one", "implement", "start", "attempt-one")

    def test_retry_limits_survive_revisions(self):
        self.activate()
        selected = {**controls_policy(), "maxAttempts": 1}
        self.controls.configure_controls(self.root, selected)
        self.approve()
        self.start()
        self.manager.record_task(self.root, "feature-one", "implement", "fail", "attempt-one", reason="Failed check")
        self.issue(lambda: self.manager.delete_execution(self.root, "feature-one"), "E_CONTROLS_HISTORY")
        newer = copy.deepcopy(self.plan)
        newer["revision"] += 1
        self.manager.import_plan(self.root, newer)
        current = self.manager.inspect_execution(self.root, "feature-one")
        self.manager.approve_plan(self.root, "feature-one", current["planDigest"], current["policyDigest"])
        self.approve()
        self.issue(lambda: self.start("attempt-two"), "E_CONTROLS_ATTEMPTS")

    def test_unapproved_escalation_and_disallowed_models_are_refused(self):
        self.activate()
        self.controls.configure_controls(self.root, controls_policy())
        self.approve()
        self.start()
        self.manager.record_task(self.root, "feature-one", "implement", "fail", "attempt-one", reason="Failed check")
        newer = copy.deepcopy(self.plan)
        newer["revision"] += 1
        newer["tasks"][0]["assignment"]["model"] = "model-one"
        self.manager.import_plan(self.root, newer)
        current = self.manager.inspect_execution(self.root, "feature-one")
        self.manager.approve_plan(self.root, "feature-one", current["planDigest"], current["policyDigest"])
        self.approve()
        self.issue(lambda: self.start("attempt-two"), "E_CONTROLS_ESCALATION")

    def test_batch_controls_version_retains_supervised_history_and_forbids_downgrade(self):
        self.activate()
        self.controls.configure_controls(self.root, controls_policy())
        self.approve()
        supervised = self.controls.inspect_controls(self.root)["store"]

        self.controls.configure_controls(self.root, batch_controls_policy())
        current = self.controls.inspect_controls(self.root)
        self.assertEqual(3, current["store"]["schemaVersion"])
        self.assertEqual(supervised, current["store"]["retainedPrevious"])
        self.assertFalse(current["store"]["approvals"])
        self.assertTrue(current["runtimeCapabilities"]["batchScheduling"])
        self.issue(lambda: self.controls.configure_controls(self.root, controls_policy()),
                   "E_CONTROLS_CAPABILITY")
        generation = current["store"]["generation"]
        updated = batch_controls_policy()
        updated["allowEscalation"] = False
        self.controls.configure_controls(self.root, updated)
        refreshed = self.controls.inspect_controls(self.root)["store"]
        self.assertEqual(generation + 1, refreshed["generation"])
        self.assertEqual(supervised, refreshed["retainedPrevious"])
        self.assertEqual({}, refreshed["batchApprovals"])

    def test_autonomous_controls_version_retains_batch_history_and_forbids_downgrade(self):
        self.activate()
        self.controls.configure_controls(self.root, batch_controls_policy())
        self.approve()
        previous = self.controls.inspect_controls(self.root)["store"]

        self.controls.configure_controls(self.root, autonomous_controls_policy())
        current = self.controls.inspect_controls(self.root)
        self.assertEqual(4, current["store"]["schemaVersion"])
        self.assertEqual(previous, current["store"]["retainedPrevious"])
        self.assertTrue(current["runtimeCapabilities"]["autonomous"])
        self.assertTrue(current["runtimeCapabilities"]["batchScheduling"])
        self.issue(lambda: self.controls.configure_controls(self.root, batch_controls_policy()),
                   "E_CONTROLS_CAPABILITY")
        generation = current["store"]["generation"]
        self.controls.configure_controls(self.root, autonomous_controls_policy())
        refreshed = self.controls.inspect_controls(self.root)["store"]
        self.assertEqual(generation + 1, refreshed["generation"])
        self.assertEqual(previous, refreshed["retainedPrevious"])
        self.assertEqual({}, refreshed["batchApprovals"])

    def test_batch_controls_reject_unbounded_or_unsupported_policy(self):
        invalid = batch_controls_policy()
        invalid["maxBatchCalls"] = 257
        self.issue(lambda: self.controls.configure_controls(self.root, invalid),
                   "E_CONTROLS_LIMIT")

        invalid = batch_controls_policy()
        invalid["mode"] = "autonomous"
        self.issue(lambda: self.controls.configure_controls(self.root, invalid),
                   "E_CONTROLS_CAPABILITY")

    def test_manual_cancel_intent_is_not_a_stop_and_requires_resolution(self):
        self.activate()
        self.controls.configure_controls(self.root, controls_policy())
        self.approve()
        self.start()
        self.controls.request_cancel(self.root, "feature-one", "implement", "Stop requested")
        self.assertEqual("running", self.manager.inspect_execution(
            self.root, "feature-one")["state"]["tasks"]["implement"]["status"])
        self.manager.record_task(self.root, "feature-one", "implement", "cancel", reason="Manual work stopped")
        self.assertEqual("pending", self.controls.inspect_controls(self.root)["cancelRequests"][0]["status"])
        self.controls.resolve_manual_cancel(self.root, "feature-one", "implement", "Checked manual work stopped")
        self.assertEqual("resolved", self.controls.inspect_controls(self.root)["cancelRequests"][0]["status"])

    def test_native_cancel_cannot_fake_host_stop(self):
        self.activate()
        importlib.import_module("execution_profiles").install_profiles(self.root, dry_run=False)
        supplied = brief(self.plan)
        supplied["guidance"] = []
        request = self.native.prepare_request(self.root, "feature-one", supplied, "developer", HOST)
        self.native.start_request(self.root, request, self.state.digest(request))
        self.controls.configure_controls(self.root, controls_policy())
        self.approve()
        self.controls.request_cancel(self.root, "feature-one", "implement", "Host stop requested")
        self.issue(lambda: self.manager.record_task(self.root, "feature-one", "implement", "cancel",
                                                    reason="Unconfirmed stop"), "E_CONTROLS_CANCELLATION")
        self.issue(lambda: self.controls.resolve_manual_cancel(
            self.root, "feature-one", "implement", "Cannot prove host stopped"), "E_CONTROLS_CANCELLATION")
        self.assertEqual("running", self.manager.inspect_execution(
            self.root, "feature-one")["state"]["tasks"]["implement"]["status"])

    def test_reconciliation_is_read_only_and_never_redispatches(self):
        self.activate()
        self.start()
        before = self.manager.execution_path(self.root, "feature-one").read_bytes()
        output = self.controls.reconcile_execution(self.root, "feature-one")
        self.assertFalse(output["redispatch"])
        self.assertEqual(["implement"], output["unresolvedTasks"])
        self.assertEqual(before, self.manager.execution_path(self.root, "feature-one").read_bytes())

    def test_failed_control_write_preserves_old_policy(self):
        self.activate()
        self.controls.configure_controls(self.root, controls_policy())
        before = self.controls.controls_path(self.root).read_bytes()
        with mock.patch.object(self.manager, "_replace", side_effect=OSError("synthetic failure")):
            self.issue(lambda: self.controls.configure_controls(self.root, controls_policy(False)))
        self.assertEqual(before, self.controls.controls_path(self.root).read_bytes())

    def test_unsupported_modes_do_not_write(self):
        self.activate()
        before = set(self.root.rglob("*"))
        for mode in ("supervised", "autonomous"):
            self.issue(lambda: self.controls.configure_controls(self.root, {**controls_policy(), "mode": mode}),
                       "E_CONTROLS_CAPABILITY")
        self.assertEqual(before, set(self.root.rglob("*")))

    def test_model_resolution_preserves_missing_price_and_observation(self):
        source = inventory()
        profile = {"id": "reasoning", "candidates": ["model-two", "model-one"]}
        output = self.controls.resolve_model(source, profile, ["model-one"])
        self.assertEqual("model-one", output["requestedModel"])
        self.assertIsNone(output["observedModel"])
        self.assertIsNone(output["pricing"])
        observation = {"hostId": source["hostId"], "hostBuild": source["hostBuild"],
                       "inventoryDigest": self.state.digest(source), "modelId": "model-one"}
        self.assertEqual("model-one", self.controls.resolve_model(
            source, profile, ["model-one"], observation=observation)["observedModel"])
        observation["modelId"] = "model-two"
        self.issue(lambda: self.controls.resolve_model(source, profile, ["model-one"], observation=observation))

    def test_missing_disallowed_and_unavailable_models_fail(self):
        source = inventory()
        profile = {"id": "reasoning", "candidates": ["model-one"]}
        self.issue(lambda: self.controls.resolve_model(source, profile, []), "E_MODEL_UNAVAILABLE")
        self.issue(lambda: self.controls.resolve_model(
            source, profile, ["model-one"], requested_model="model-two"), "E_MODEL_DENIED")
        source["source"], source["hostId"], source["hostBuild"], source["models"] = "unavailable", None, None, []
        self.issue(lambda: self.controls.resolve_model(source, profile, ["model-one"]), "E_MODEL_UNAVAILABLE")

    def test_price_estimates_require_units_rate_and_bounded_integers(self):
        model = {"id": "gpt-5.3-codex", "available": True, "pricing": None}
        self.assertIsNone(self.controls.estimate_cost(model, 7)["costMinor"])
        model["pricing"] = {"currency": "USD", "rateVersion": "rate-one",
                            "unit": "request", "units": 3, "priceMinor": 2}
        self.assertEqual(6, self.controls.estimate_cost(model, 8)["costMinor"])
        self.issue(lambda: self.controls.estimate_cost(model, True))
        model["pricing"]["units"] = 0
        self.issue(lambda: self.controls.estimate_cost(model, 8))

    def test_native_stop_cannot_be_faked_by_failure_or_disabling_controls(self):
        self.activate()
        importlib.import_module("execution_profiles").install_profiles(self.root, dry_run=False)
        supplied = brief(self.plan)
        supplied["guidance"] = []
        request = self.native.prepare_request(self.root, "feature-one", supplied, "developer", HOST)
        self.native.start_request(self.root, request, self.state.digest(request))
        self.controls.configure_controls(self.root, controls_policy())
        self.controls.configure_controls(self.root, controls_policy(False))
        before = self.manager.execution_path(self.root, "feature-one").read_bytes()
        for action in ("fail", "cancel"):
            self.issue(lambda: self.manager.record_task(self.root, "feature-one", "implement", action,
                                                        "attempt-one" if action == "fail" else None,
                                                        "Unconfirmed host outcome"),
                       "E_CONTROLS_CANCELLATION")
            self.assertEqual(before, self.manager.execution_path(self.root, "feature-one").read_bytes())

    def test_cli_controls_round_trip(self):
        self.activate()
        input_path = self.root / "controls.json"
        input_path.write_text(json.dumps(controls_policy()), encoding="utf-8")

        def cli(*arguments):
            output = subprocess.run([sys.executable, "-B", str(SCRIPTS / "manage_controls.py"),
                                     *arguments, "--project-root", str(self.root)], capture_output=True, text=True)
            self.assertEqual(0, output.returncode, output.stderr)
            return json.loads(output.stdout)

        cli("configure", "--input", str(input_path))
        selected = cli("inspect")
        current = self.manager.inspect_execution(self.root, "feature-one")
        cli("approve", "--execution-id", "feature-one", "--plan-digest", current["planDigest"],
            "--execution-policy-digest", current["policyDigest"], "--controls-digest", selected["controlsDigest"])
        cli("pause", "--reason", "Explicit pause")
        self.issue(lambda: self.start(), "E_CONTROLS_PAUSED")
        cli("resume", "--reason", "Explicit resume")
        self.manager.record_task(self.root, "feature-one", "implement", "start", "attempt-one")
        self.assertFalse(cli("reconcile", "--execution-id", "feature-one")["redispatch"])
        cli("request-cancel", "--execution-id", "feature-one", "--task-id", "implement", "--reason", "Stop")
        self.manager.record_task(self.root, "feature-one", "implement", "cancel", reason="Manual work stopped")
        cli("resolve-manual-cancel", "--execution-id", "feature-one", "--task-id", "implement",
            "--reason", "Manual stop checked")
        self.assertEqual("resolved", cli("inspect")["cancelRequests"][0]["status"])
        input_path.write_text(json.dumps({
            "schemaVersion": 1, "inventory": inventory(), "profile": {"id": "reasoning", "candidates": ["model-one"]},
            "permittedModels": ["model-one"], "requestedModel": None, "observation": None,
        }), encoding="utf-8")
        self.assertEqual("unverified", cli("resolve", "--input", str(input_path))["routing"])
        input_path.write_text(json.dumps({"model": inventory()["models"][0], "units": 1}), encoding="utf-8")
        self.assertIsNone(cli("estimate", "--input", str(input_path))["costMinor"])
        input_path.write_text('{"model":null,"model":null,"units":1}', encoding="utf-8")
        rejected = subprocess.run([sys.executable, "-B", str(SCRIPTS / "manage_controls.py"), "estimate",
                                   "--input", str(input_path), "--project-root", str(self.root)],
                                  capture_output=True, text=True)
        self.assertNotEqual(0, rejected.returncode)
        self.assertEqual("", rejected.stdout)
        self.assertIn("error[", rejected.stderr)
        self.assertNotIn("Traceback", rejected.stderr)

    def test_clean_disabled_controls_preserve_legacy_native_and_manual(self):
        self.activate()
        self.controls.configure_controls(self.root, controls_policy(False))
        self.assertFalse(self.controls.inspect_controls(self.root)["store"]["safetyActivated"])
        self.start()
        self.manager.record_task(self.root, "feature-one", "implement", "fail", "attempt-one", "Manual failed")
        newer = copy.deepcopy(self.plan)
        newer["revision"] += 1
        self.manager.import_plan(self.root, newer)
        inspected = self.manager.inspect_execution(self.root, "feature-one")
        self.manager.approve_plan(self.root, "feature-one", inspected["planDigest"], inspected["policyDigest"])
        supplied = brief(newer)
        supplied["attemptId"], supplied["guidance"] = "attempt-two", []
        importlib.import_module("execution_profiles").install_profiles(self.root, dry_run=False)
        request = self.native.prepare_request(self.root, "feature-one", supplied, "developer", HOST)
        self.native.start_request(self.root, request, self.state.digest(request))

    def test_enabled_manual_controls_reject_native_start_without_mutation(self):
        self.activate()
        importlib.import_module("execution_profiles").install_profiles(self.root, dry_run=False)
        supplied = brief(self.plan)
        supplied["guidance"] = []
        request = self.native.prepare_request(self.root, "feature-one", supplied, "developer", HOST)
        self.controls.configure_controls(self.root, controls_policy())
        self.approve()
        before = self.manager.execution_path(self.root, "feature-one").read_bytes()
        self.issue(lambda: self.native.start_request(self.root, request, self.state.digest(request)),
                   "E_CONTROLS_CAPABILITY")
        self.assertEqual(before, self.manager.execution_path(self.root, "feature-one").read_bytes())

    def test_pending_intent_blocks_peer_and_checks_original_revision(self):
        self.activate()
        self.controls.configure_controls(self.root, controls_policy())
        self.approve()
        self.start()
        self.controls.request_cancel(self.root, "feature-one", "implement", "Stop requested")
        self.manager.record_task(self.root, "feature-one", "implement", "cancel", reason="Manual stopped")
        peer = copy.deepcopy(self.plan)
        peer["executionId"] = "peer"
        self.manager.import_plan(self.root, peer)
        inspected = self.manager.inspect_execution(self.root, "peer")
        self.manager.approve_plan(self.root, "peer", inspected["planDigest"], inspected["policyDigest"])
        self.controls.configure_controls(self.root, controls_policy(False))
        self.issue(lambda: self.start(execution_id="peer"), "E_CONTROLS_CANCELLATION")
        newer = copy.deepcopy(self.plan)
        newer["revision"] += 1
        self.manager.import_plan(self.root, newer)
        self.controls.configure_controls(self.root, controls_policy())
        self.controls.resolve_manual_cancel(self.root, "feature-one", "implement", "Original manual stop checked")
        self.assertEqual("resolved", self.controls.inspect_controls(self.root)["cancelRequests"][0]["status"])

    def test_native_receipt_allows_failure_but_not_manual_cancel_resolution_after_revision(self):
        self.activate()
        importlib.import_module("execution_profiles").install_profiles(self.root, dry_run=False)
        supplied = brief(self.plan)
        supplied["guidance"] = []
        request = self.native.prepare_request(self.root, "feature-one", supplied, "developer", HOST)
        self.native.start_request(self.root, request, self.state.digest(request))
        self.controls.configure_controls(self.root, controls_policy())
        self.controls.request_cancel(self.root, "feature-one", "implement", "Native stop requested")
        receipt = {"schemaVersion": 1, "requestDigest": self.state.digest(request),
                   "hostId": HOST["id"], "hostBuild": HOST["build"], "callId": "call-one", "result": result(self.plan)}
        self.native.receive_receipt(self.root, request, receipt, "result-one")
        self.manager.record_task(self.root, "feature-one", "implement", "fail", "attempt-one", "Receipt checked")
        newer = copy.deepcopy(self.plan)
        newer["revision"] += 1
        self.manager.import_plan(self.root, newer)
        self.issue(lambda: self.controls.resolve_manual_cancel(
            self.root, "feature-one", "implement", "New manual revision"), "E_CONTROLS_CANCELLATION")

    def test_corrupt_controls_and_competing_lock_fail_closed(self):
        self.activate()
        self.controls.configure_controls(self.root, controls_policy())
        self.approve()
        path = self.controls.controls_path(self.root)
        original = path.read_bytes()
        lock = self.manager.lock_path(self.root)
        lock.write_text("other writer", encoding="ascii")
        self.issue(lambda: self.controls.set_pause(self.root, True, "Pause"), "E_EXECUTION_BUSY")
        self.assertEqual(original, path.read_bytes())
        lock.unlink()
        path.write_text('{"schemaVersion":1}', encoding="utf-8")
        self.issue(lambda: self.start())
        self.assertEqual('{"schemaVersion":1}', path.read_text(encoding="utf-8"))

    def test_absent_fallback_needs_no_new_ignore_but_writes_do(self):
        project = self.root / "project"
        project.mkdir()
        ignored = self.root / ".gitignore"
        ignored.write_text("project/.sdlc/local/executions\nproject/.sdlc/local/executions.lock\n", encoding="utf-8")
        before = set(project.rglob("*"))
        self.assertFalse(self.controls.inspect_controls(project)["enabled"])
        self.issue(lambda: self.controls.configure_controls(project, controls_policy(False)), "E_CONTROLS_STORAGE")
        self.assertEqual(before, set(project.rglob("*")))
        with ignored.open("a", encoding="utf-8") as output:
            output.write("project/.sdlc/local/execution-controls.json\n")
        self.controls.configure_controls(project, controls_policy(False))
        self.assertEqual(project / ".sdlc" / "local" / "execution-controls.json", self.controls.controls_path(project))

    def test_schema_roots_match_supplied_contracts(self):
        self.activate()
        self.controls.configure_controls(self.root, controls_policy())
        fixtures = {
            "execution-controls-policy": controls_policy(),
            "execution-controls-record": self.controls.inspect_controls(self.root)["store"],
            "model-inventory": inventory(),
            "model-resolution": {"schemaVersion": 1, "inventory": inventory(),
                                 "profile": {"id": "reasoning", "candidates": ["model-one"]},
                                 "permittedModels": ["model-one"], "requestedModel": None, "observation": None},
        }
        for name, fixture in fixtures.items():
            schema = json.loads((SCRIPTS.parent / "contracts" / (name + ".schema.json")).read_text(encoding="utf-8"))
            self.assertEqual("urn:sdlc:" + name + ":1", schema["$id"])
            self.assertEqual(set(fixture), set(schema["required"]))
            self.assertEqual(set(fixture), set(schema["properties"]))
            self.assertFalse(schema["additionalProperties"])
        invalid = self.controls.inspect_controls(self.root)["store"]
        invalid["safetyActivated"] = False
        self.issue(lambda: self.controls._store(invalid), "E_CONTROLS_STORE")
        self.controls.configure_controls(self.root, batch_controls_policy())
        batch_store = self.controls.inspect_controls(self.root)["store"]
        policy_schema = json.loads(
            (SCRIPTS.parent / "contracts" / "execution-controls-policy-v3.schema.json").read_text(
                encoding="utf-8"
            )
        )
        record_schema = json.loads(
            (SCRIPTS.parent / "contracts" / "execution-controls-record-v3.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(set(batch_store["policy"]), set(policy_schema["required"]))
        self.assertEqual(set(batch_store["policy"]), set(policy_schema["properties"]))
        self.assertEqual(set(batch_store), set(record_schema["required"]))
        self.assertEqual(set(batch_store), set(record_schema["properties"]))

    def test_invalid_models_snapshots_prices_and_policy_bounds_are_explicit(self):
        source = inventory()
        profile = {"id": "reasoning", "candidates": ["model-one"]}
        for key, invalid in (("maxAttempts", True), ("maxAttempts", 0), ("maxAttempts", 257),
                             ("allowEscalation", 1), ("extra", "unknown")):
            self.issue(lambda: self.controls.validate_controls_policy({**controls_policy(), key: invalid}))
        duplicate = copy.deepcopy(source)
        duplicate["models"].append(copy.deepcopy(duplicate["models"][0]))
        self.issue(lambda: self.controls.validate_inventory(duplicate), "E_MODEL_INVENTORY")
        observation = {"hostId": source["hostId"], "hostBuild": source["hostBuild"],
                       "inventoryDigest": self.state.digest(source), "modelId": "model-one"}
        for key, value in (("hostId", "other"), ("hostBuild", "other"), ("inventoryDigest", "0" * 64)):
            self.issue(lambda: self.controls.resolve_model(
                source, profile, ["model-one"], observation={**observation, key: value}), "E_MODEL_OBSERVATION")
        priced = {"id": "model-one", "available": True, "pricing": {
            "currency": "USD", "rateVersion": "rate-one", "unit": "request", "units": 1,
            "priceMinor": 2**63 - 1,
        }}
        self.issue(lambda: self.controls.estimate_cost(priced, 2))
        for value in (True, 1.5, -1, 2**63):
            self.issue(lambda: self.controls.estimate_cost(priced, value))
        for key in ("unit", "rateVersion", "units"):
            missing = copy.deepcopy(priced)
            del missing["pricing"][key]
            self.issue(lambda: self.controls.estimate_cost(missing, 1))

    def test_manual_receipt_cannot_release_a_native_worker_under_controls(self):
        self.activate()
        importlib.import_module("execution_profiles").install_profiles(self.root, dry_run=False)
        supplied = brief(self.plan)
        supplied["guidance"] = []
        request = self.native.prepare_request(self.root, "feature-one", supplied, "developer", HOST)
        self.native.start_request(self.root, request, self.state.digest(request))
        self.controls.configure_controls(self.root, controls_policy())
        before = self.manager.execution_path(self.root, "feature-one").read_bytes()
        self.issue(lambda: self.manager.receive_result(
            self.root, "feature-one", "result-one", supplied, result(self.plan)), "E_CONTROLS_CANCELLATION")
        self.assertEqual(before, self.manager.execution_path(self.root, "feature-one").read_bytes())

    def test_preexisting_unattributed_native_report_cannot_be_rejected_or_accepted(self):
        self.activate()
        importlib.import_module("execution_profiles").install_profiles(self.root, dry_run=False)
        supplied = brief(self.plan)
        supplied["guidance"] = []
        request = self.native.prepare_request(self.root, "feature-one", supplied, "developer", HOST)
        self.native.start_request(self.root, request, self.state.digest(request))
        self.manager.receive_result(self.root, "feature-one", "result-one", supplied, result(self.plan))
        self.controls.configure_controls(self.root, controls_policy())
        acceptance = {"schemaVersion": 1, "taskId": "implement", "attemptId": "attempt-one",
                      "resultId": "result-one", "acceptanceCriteria": ["AC-1"], "revision": "baseline",
                      "command": "python -m unittest", "summary": "Checked"}
        self.issue(lambda: self.manager.record_task(
            self.root, "feature-one", "implement", "reject", "attempt-one",
            reason="Unattributed report"), "E_CONTROLS_CANCELLATION")
        self.issue(lambda: self.manager.accept_task(self.root, "feature-one", acceptance), "E_CONTROLS_CANCELLATION")

    def test_recovery_does_not_trust_old_manual_native_cancellation(self):
        self.activate()
        importlib.import_module("execution_profiles").install_profiles(self.root, dry_run=False)
        supplied = brief(self.plan)
        supplied["guidance"] = []
        request = self.native.prepare_request(self.root, "feature-one", supplied, "developer", HOST)
        self.native.start_request(self.root, request, self.state.digest(request))
        self.manager.record_task(self.root, "feature-one", "implement", "cancel", reason="Legacy unconfirmed stop")
        newer = copy.deepcopy(self.plan)
        newer["revision"] += 1
        self.manager.import_plan(self.root, newer)
        current = self.manager.inspect_execution(self.root, "feature-one")
        self.manager.approve_plan(self.root, "feature-one", current["planDigest"], current["policyDigest"])
        self.controls.configure_controls(self.root, controls_policy())
        self.approve()
        self.assertEqual(1, len(self.controls.reconcile_execution(self.root, "feature-one")["unknownNativeAttempts"]))
        self.issue(lambda: self.manager.delete_execution(self.root, "feature-one"), "E_CONTROLS_CANCELLATION")
        self.issue(lambda: self.start("attempt-two"), "E_CONTROLS_CANCELLATION")

    def test_schema_string_boundaries_match_runtime_without_new_dependencies(self):
        directory = SCRIPTS.parent / "contracts"
        schemas = {value["$id"]: value for value in (
            json.loads(path.read_text(encoding="utf-8")) for path in directory.glob("*.schema.json")
        )}

        def string_valid(specification, text, document=None):
            if "$ref" in specification:
                identity, fragment = specification["$ref"].split("#/")
                document = schemas[identity] if identity else document
                target = document
                for part in fragment.split("/"):
                    target = target[part]
                if not string_valid(target, text, document):
                    return False
            return (specification.get("minLength", 0) <= len(text) <= specification.get("maxLength", len(text))
                    and ("pattern" not in specification or re.search(specification["pattern"], text) is not None))

        record_schema = schemas["urn:sdlc:execution-controls-record:1"]
        inventory_schema = schemas["urn:sdlc:model-inventory:1"]
        resolution_schema = schemas["urn:sdlc:model-resolution:1"]
        checks = [
            (record_schema["properties"]["pauseReason"]["oneOf"][1],
             lambda text: self.controls._store({**self.controls.inspect_controls(self.root)["store"],
                                                "paused": True, "pauseReason": text}),
             [("a" * 2048, True), ("a" * 2049, False), ("\t", False)]),
            (inventory_schema["properties"]["hostBuild"]["oneOf"][1],
             lambda text: self.controls.validate_inventory({**inventory(), "hostBuild": text}),
             [("a" * 128, True), ("a" * 129, False), ("\t", False), ("host\n", False)]),
            (inventory_schema["$defs"]["modelId"], self.controls._model_id,
             [("provider/model:version", True), ("model-one\n", False), ("a" * 129, False)]),
            (inventory_schema["$defs"]["pricing"]["properties"]["currency"],
             lambda text: self.controls._pricing({"currency": text, "rateVersion": "rate",
                                                  "unit": "request", "units": 1, "priceMinor": 1}),
             [("USD", True), ("USD\n", False), ("usd", False)]),
        ]
        self.activate()
        self.controls.configure_controls(self.root, controls_policy())
        self.assertEqual(inventory_schema["properties"]["hostBuild"]["oneOf"][1],
                         resolution_schema["properties"]["observation"]["oneOf"][1]["properties"]["hostBuild"])
        for specification, validator, samples in checks:
            for text, expected in samples:
                with self.subTest(text=repr(text[:20]), expected=expected):
                    self.assertEqual(expected, string_valid(specification, text))
                    if expected:
                        validator(text)
                    else:
                        self.issue(lambda: validator(text))

    def test_explicit_disallowed_assignment_model_is_denied(self):
        self.plan["tasks"][0]["assignment"]["model"] = "model-three"
        self.activate()
        self.controls.configure_controls(self.root, controls_policy())
        self.approve()
        self.issue(lambda: self.start(), "E_MODEL_DENIED")

    def test_explicit_escalation_permission_allows_bounded_retry(self):
        self.activate()
        self.controls.configure_controls(self.root, {**controls_policy(), "allowEscalation": True})
        self.approve()
        self.start()
        self.manager.record_task(self.root, "feature-one", "implement", "fail", "attempt-one", reason="Failed check")
        newer = copy.deepcopy(self.plan)
        newer["revision"] += 1
        newer["tasks"][0]["assignment"]["model"] = "model-one"
        self.manager.import_plan(self.root, newer)
        current = self.manager.inspect_execution(self.root, "feature-one")
        self.manager.approve_plan(self.root, "feature-one", current["planDigest"], current["policyDigest"])
        self.approve()
        self.start("attempt-two")
        self.assertEqual("running", self.manager.inspect_execution(
            self.root, "feature-one")["state"]["tasks"]["implement"]["status"])


if __name__ == "__main__":
    unittest.main()
