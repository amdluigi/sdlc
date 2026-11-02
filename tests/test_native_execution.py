import copy
from contextlib import nullcontext
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.test_execution_contracts import SCRIPTS, plan, brief, result
from tests.test_execution_management import policy
from artifact_contracts import ContractIssue


HOST = {"id": "native-test-host", "build": "observed-1", "delegationTool": "agent",
        "allowedActions": ["read", "search", "edit", "execute"]}


class NativeExecutionTests(unittest.TestCase):
    def setUp(self):
        for filename in ("execution_profiles.py", "native_execution.py"):
            self.assertTrue((SCRIPTS / filename).is_file(), "Native supervised execution is not provided")
        self.profiles = importlib.import_module("execution_profiles")
        self.native = importlib.import_module("native_execution")
        self.manager = importlib.import_module("execution_manager")
        self.state = importlib.import_module("execution_state")
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.plan = plan()
        self.brief = brief(self.plan)
        self.brief["guidance"] = []

    def activate(self):
        self.profiles.install_profiles(self.root, dry_run=False)
        self.manager.configure_policy(self.root, policy())
        self.manager.import_plan(self.root, self.plan)
        inspected = self.manager.inspect_execution(self.root, "feature-one")
        self.manager.approve_plan(self.root, "feature-one", inspected["planDigest"], inspected["policyDigest"])

    def prepare(self):
        return self.native.prepare_request(self.root, "feature-one", self.brief, "developer", HOST)

    def start(self, request):
        return self.native.start_request(self.root, request, self.state.digest(request))

    def receipt(self, request, call_id="call-one"):
        return {"schemaVersion": 1, "requestDigest": self.state.digest(request),
                "hostId": HOST["id"], "hostBuild": HOST["build"], "callId": call_id,
                "result": result(self.plan)}

    def assert_issue(self, callback, code=None):
        with self.assertRaises(ContractIssue) as caught:
            callback()
        if code:
            self.assertEqual(code, caught.exception.code)

    def test_profile_dry_run_is_read_only_and_no_execution_activation(self):
        before = set(self.root.rglob("*"))
        preview = self.profiles.install_profiles(self.root)
        self.assertTrue(preview["dryRun"])
        self.assertEqual(before, set(self.root.rglob("*")))
        self.profiles.install_profiles(self.root, dry_run=False)
        self.assertFalse((self.root / ".sdlc" / "execution-policy.json").exists())
        self.assertEqual(5, len(list((self.root / ".github" / "agents").glob("*.agent.md"))))

    def test_profile_collisions_drift_and_extra_files_preserve_user_content(self):
        folder = self.root / ".github" / "agents"
        folder.mkdir(parents=True)
        owned = folder / "existing.agent.md"
        owned.write_text("user agent", encoding="utf-8")
        self.assert_issue(lambda: self.profiles.install_profiles(self.root, dry_run=False), "E_PROFILE_COLLISION")
        self.assertEqual("user agent", owned.read_text(encoding="utf-8"))
        owned.unlink()
        folder.rmdir()
        self.profiles.install_profiles(self.root, dry_run=False)
        first = self.profiles.install_profiles(self.root, dry_run=False)
        self.assertTrue(first["idempotent"])
        (folder / "extra.agent.md").write_text("extra", encoding="utf-8")
        self.assert_issue(lambda: self.profiles.inspect_profile(self.root, "developer"), "E_PROFILE_DRIFT")

    def test_profile_copy_and_link_have_exact_source_identity(self):
        for mode in ("copy", "link"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                subprocess.run(["git", "init", "-q", str(root)], check=True)
                self.profiles.install_profiles(root, mode, dry_run=False)
                for role in ("controller", "architecture", "developer", "testing", "review"):
                    installed = self.profiles.inspect_profile(root, role)
                    self.assertEqual(self.profiles.role_info(role)["digest"], installed["digest"])

    def test_prepare_and_refused_start_write_nothing(self):
        self.activate()
        before = self.manager.execution_path(self.root, "feature-one").read_bytes()
        request = self.prepare()
        self.assertEqual(before, self.manager.execution_path(self.root, "feature-one").read_bytes())
        self.assert_issue(lambda: self.native.start_request(self.root, request, "sha256:" + "0" * 64),
                          "E_NATIVE_APPROVAL")
        self.assertEqual(before, self.manager.execution_path(self.root, "feature-one").read_bytes())

    def test_native_flow_records_attribution_but_requires_independent_acceptance(self):
        self.activate()
        request = self.prepare()
        self.start(request)
        receipt = self.receipt(request)
        self.native.receive_receipt(self.root, request, receipt, "result-one")
        inspected = self.manager.inspect_execution(self.root, "feature-one")
        self.assertEqual("reported", inspected["state"]["tasks"]["implement"]["status"])
        self.assertTrue(any("call-one" in event["payload"].get("message", "")
                            for event in inspected["events"]))
        self.assertTrue(self.native.receive_receipt(self.root, request, receipt, "result-one")["idempotent"])
        self.manager.accept_task(self.root, "feature-one", {
            "schemaVersion": 1, "taskId": "implement", "attemptId": "attempt-one",
            "resultId": "result-one", "acceptanceCriteria": ["AC-1"],
            "revision": "baseline", "command": "python -m unittest", "summary": "Independent check",
        })
        self.assertEqual("accepted", self.manager.inspect_execution(
            self.root, "feature-one")["state"]["tasks"]["implement"]["status"])

    def test_edited_request_and_policy_drift_cannot_start(self):
        self.activate()
        request = self.prepare()
        self.manager.configure_policy(self.root, policy())
        self.assert_issue(lambda: self.start(request), "E_NATIVE_APPROVAL")
        self.assertEqual("waiting", self.manager.inspect_execution(
            self.root, "feature-one")["state"]["tasks"]["implement"]["status"])

    def test_missing_host_actions_explicit_models_and_role_escalation_fail(self):
        self.activate()
        bad_host = {**HOST, "allowedActions": ["read", "search"]}
        self.assert_issue(lambda: self.native.prepare_request(
            self.root, "feature-one", self.brief, "developer", bad_host), "E_NATIVE_CAPABILITY")
        self.assert_issue(lambda: self.native.prepare_request(
            self.root, "feature-one", self.brief, "review", HOST), "E_NATIVE_ROLE")
        bad = copy.deepcopy(self.plan)
        bad["revision"] += 1
        bad["tasks"][0]["assignment"]["model"] = "unobserved-model"
        self.manager.import_plan(self.root, bad)
        current = self.manager.inspect_execution(self.root, "feature-one")
        self.manager.approve_plan(self.root, "feature-one", current["planDigest"], current["policyDigest"])
        supplied = brief(bad)
        supplied["guidance"] = []
        self.assert_issue(lambda: self.native.prepare_request(
            self.root, "feature-one", supplied, "developer", HOST), "E_NATIVE_CAPABILITY")

    def test_duplicate_dispatch_and_cross_execution_claims_are_blocked(self):
        self.activate()
        request = self.prepare()
        self.start(request)
        self.assert_issue(lambda: self.start(request))
        second = copy.deepcopy(self.plan)
        second["executionId"] = "feature-two"
        self.manager.import_plan(self.root, second)
        current = self.manager.inspect_execution(self.root, "feature-two")
        self.manager.approve_plan(self.root, "feature-two", current["planDigest"], current["policyDigest"])
        supplied = brief(second)
        supplied["guidance"] = []
        other = self.native.prepare_request(self.root, "feature-two", supplied, "developer", HOST)
        self.assert_issue(lambda: self.start(other), "E_EXECUTION_CONFLICT")

    def test_spoofed_or_edited_receipts_are_atomic_failures(self):
        self.activate()
        request = self.prepare()
        self.start(request)
        before = self.manager.execution_path(self.root, "feature-one").read_bytes()
        for field, value in (("hostId", "another-host"), ("requestDigest", "sha256:" + "0" * 64),
                             ("approved", True)):
            receipt = self.receipt(request)
            receipt[field] = value
            self.assert_issue(lambda: self.native.receive_receipt(self.root, request, receipt, "result-one"))
            self.assertEqual(before, self.manager.execution_path(self.root, "feature-one").read_bytes())

    def test_manual_attempt_cannot_be_relabelled_as_native_dispatch(self):
        self.activate()
        request = self.prepare()
        self.manager.record_task(self.root, "feature-one", "implement", "ready")
        self.manager.record_task(self.root, "feature-one", "implement", "start", "attempt-one")
        self.assert_issue(lambda: self.native.receive_receipt(
            self.root, request, self.receipt(request), "result-one"), "E_NATIVE_BINDING")

    def test_native_atomic_failure_does_not_release_or_promote_a_claim(self):
        self.activate()
        request = self.prepare()
        before = self.manager.execution_path(self.root, "feature-one").read_bytes()
        with mock.patch.object(self.manager, "_replace", side_effect=OSError("synthetic promotion failure")):
            self.assert_issue(lambda: self.start(request))
        self.assertEqual(before, self.manager.execution_path(self.root, "feature-one").read_bytes())

    def test_profile_install_interruption_is_explicit_not_a_success(self):
        with mock.patch.object(self.profiles.os, "replace", side_effect=OSError("synthetic interrupted write")):
            self.assert_issue(lambda: self.profiles.install_profiles(self.root, dry_run=False))
        self.assertFalse((self.root / ".github" / "agents").exists())

    def test_malformed_binding_and_brief_fail_without_writes(self):
        self.activate()
        before = self.manager.execution_path(self.root, "feature-one").read_bytes()
        for field, value in (("binding", []), ("binding", {}), ("brief", [])):
            with self.subTest(field=field, value=value):
                request = self.prepare()
                request[field] = value
                self.assert_issue(lambda: self.start(request))
                self.assertEqual(before, self.manager.execution_path(self.root, "feature-one").read_bytes())

    def test_case_aliased_control_ownership_is_refused(self):
        self.plan["tasks"][0]["ownership"] = [".GiT/worker.txt"]
        self.brief = brief(self.plan)
        self.brief["ownership"] = [".GiT/worker.txt"]
        self.brief["guidance"] = []
        self.activate()
        self.assert_issue(lambda: self.prepare(), "E_NATIVE_SCOPE")

    def test_role_metadata_is_not_a_mutable_authority(self):
        info = self.profiles.role_info("review")
        info["allowedActions"].append("edit")
        info["tools"].append("execute")
        self.assertEqual(["read", "search"], self.profiles.role_info("review")["allowedActions"])
        self.assertEqual(["read", "search"], self.profiles.role_info("review")["tools"])

    def test_cli_native_flow_and_stable_invalid_input_errors(self):
        def cli(*arguments):
            return subprocess.run(
                [sys.executable, "-B", str(SCRIPTS / "manage_native.py"), *arguments,
                 "--project-root", str(self.root)],
                text=True, capture_output=True, check=False,
            )
        self.activate()
        brief_path, host_path = self.root / "brief.json", self.root / "host.json"
        brief_path.write_text(json.dumps(self.brief), encoding="utf-8")
        host_path.write_text(json.dumps(HOST), encoding="utf-8")
        prepared = cli("prepare", "--execution-id", "feature-one", "--brief", str(brief_path),
                       "--role", "developer", "--host", str(host_path))
        self.assertEqual(0, prepared.returncode, prepared.stderr)
        request = json.loads(prepared.stdout)
        request_path = self.root / "request.json"
        request_path.write_text(prepared.stdout, encoding="utf-8")
        digested = cli("digest", "--input", str(request_path))
        self.assertEqual(0, digested.returncode, digested.stderr)
        self.assertEqual(self.state.digest(request), json.loads(digested.stdout)["requestDigest"])
        started = cli("start", "--request", str(request_path),
                      "--approved-request-digest", self.state.digest(request))
        self.assertEqual(0, started.returncode, started.stderr)
        receipt_path = self.root / "receipt.json"
        receipt_path.write_text(json.dumps(self.receipt(request)), encoding="utf-8")
        received = cli("receive", "--request", str(request_path), "--receipt", str(receipt_path),
                       "--result-id", "result-one")
        self.assertEqual(0, received.returncode, received.stderr)
        self.assertEqual("reported", self.manager.inspect_execution(
            self.root, "feature-one")["state"]["tasks"]["implement"]["status"])
        request_path.write_text('{"schemaVersion":1,"schemaVersion":1}', encoding="utf-8")
        refused = cli("digest", "--input", str(request_path))
        self.assertNotEqual(0, refused.returncode)
        self.assertIn("error[", refused.stderr)
        self.assertNotIn("Traceback", refused.stderr)

    def test_source_drift_is_detected_before_visible_promotion(self):
        source = self.root / "bundle-source"
        shutil.copytree(self.profiles.SOURCE, source)
        original = self.profiles._snapshot

        def changed_snapshot():
            snapshot = original()
            path = source / "sdlc-developer.agent.md"
            path.write_bytes(path.read_bytes() + b"\nChanged during staging.\n")
            return snapshot

        with mock.patch.object(self.profiles, "SOURCE", source), \
                mock.patch.object(self.profiles, "_snapshot", side_effect=changed_snapshot):
            self.assert_issue(lambda: self.profiles.install_profiles(self.root, dry_run=False), "E_PROFILE_SOURCE")
        self.assertFalse((self.root / ".github" / "agents").exists())
        self.assert_issue(lambda: self.profiles.inspect_profile(self.root, "developer"), "E_PROFILE_PENDING")

    def test_promotion_failure_retains_pending_ownership(self):
        with mock.patch.object(Path, "rename", side_effect=OSError("synthetic profile promotion failure")):
            self.assert_issue(lambda: self.profiles.install_profiles(self.root, dry_run=False), "E_PROFILE_IO")
        self.assertFalse((self.root / ".github" / "agents").exists())
        self.assert_issue(lambda: self.profiles.inspect_profile(self.root, "developer"), "E_PROFILE_PENDING")
        self.assertFalse(list((self.root / ".github").glob("native-profiles-*")))

    def test_worker_cannot_return_approval_fields(self):
        self.activate()
        request = self.prepare()
        self.start(request)
        receipt = self.receipt(request)
        receipt["result"]["approved"] = True
        self.assert_issue(lambda: self.native.receive_receipt(self.root, request, receipt, "result-one"))
        self.assertEqual("running", self.manager.inspect_execution(
            self.root, "feature-one")["state"]["tasks"]["implement"]["status"])

    def test_receipt_call_identity_is_unique_across_executions(self):
        self.test_native_flow_records_attribution_but_requires_independent_acceptance()
        second = copy.deepcopy(self.plan)
        second["executionId"] = "feature-two"
        self.manager.import_plan(self.root, second)
        current = self.manager.inspect_execution(self.root, "feature-two")
        self.manager.approve_plan(self.root, "feature-two", current["planDigest"], current["policyDigest"])
        supplied = brief(second)
        supplied["guidance"] = []
        request = self.native.prepare_request(self.root, "feature-two", supplied, "developer", HOST)
        self.start(request)
        receipt = self.receipt(request)
        receipt["result"] = result(second)
        self.assert_issue(lambda: self.native.receive_receipt(self.root, request, receipt, "result-two"),
                          "E_NATIVE_DUPLICATE")

    def test_published_schema_fields_match_runtime_envelopes(self):
        self.activate()
        request = self.prepare()
        for name, envelope in (("request", request), ("receipt", self.receipt(request))):
            schema = json.loads((SCRIPTS.parent / "contracts" / f"native-{name}.schema.json").read_text())
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(set(envelope), set(schema["required"]))
            self.assertEqual(set(envelope), set(schema["properties"]))
            self.assertEqual(1, schema["properties"]["schemaVersion"]["const"])

    def test_ordinary_manual_progress_does_not_block_peer_native_receipts(self):
        self.activate()
        self.manager.record_task(self.root, "feature-one", "implement", "ready")
        self.manager.record_task(self.root, "feature-one", "implement", "start", "attempt-one")
        self.manager.record_task(self.root, "feature-one", "implement", "progress", "attempt-one",
                                 "native-receipt: waiting for host output")
        self.manager.receive_result(self.root, "feature-one", "manual-one", self.brief, result(self.plan))
        self.manager.accept_task(self.root, "feature-one", {
            "schemaVersion": 1, "taskId": "implement", "attemptId": "attempt-one",
            "resultId": "manual-one", "acceptanceCriteria": ["AC-1"],
            "revision": "baseline", "command": "python -m unittest", "summary": "Independent manual check",
        })
        second = copy.deepcopy(self.plan)
        second["executionId"] = "feature-two"
        self.manager.import_plan(self.root, second)
        current = self.manager.inspect_execution(self.root, "feature-two")
        self.manager.approve_plan(self.root, "feature-two", current["planDigest"], current["policyDigest"])
        supplied = brief(second)
        supplied["guidance"] = []
        request = self.native.prepare_request(self.root, "feature-two", supplied, "developer", HOST)
        self.start(request)
        self.manager.record_task(self.root, "feature-two", "implement", "progress", "attempt-one",
                                 "native-receipt: ordinary progress during a native attempt")
        self.manager.record_task(self.root, "feature-two", "implement", "progress", "attempt-one",
                                 "native-request: waiting for host output")
        self.manager.record_task(self.root, "feature-two", "implement", "progress", "attempt-one",
                                 "native-request:sha256:" + "0" * 64)
        receipt = self.receipt(request)
        receipt["result"] = result(second)
        self.native.receive_receipt(self.root, request, receipt, "result-two")
        self.assertTrue(self.native.receive_receipt(self.root, request, receipt, "result-two")["idempotent"])
        self.manager.accept_task(self.root, "feature-two", {
            "schemaVersion": 1, "taskId": "implement", "attemptId": "attempt-one",
            "resultId": "result-two", "acceptanceCriteria": ["AC-1"],
            "revision": "baseline", "command": "python -m unittest", "summary": "Independent native check",
        })
        third = copy.deepcopy(self.plan)
        third["executionId"] = "feature-three"
        self.manager.import_plan(self.root, third)
        current = self.manager.inspect_execution(self.root, "feature-three")
        self.manager.approve_plan(self.root, "feature-three", current["planDigest"], current["policyDigest"])
        supplied = brief(third)
        supplied["guidance"] = []
        request = self.native.prepare_request(self.root, "feature-three", supplied, "developer", HOST)
        self.start(request)
        receipt = self.receipt(request, "call-three")
        receipt["result"] = result(third)
        self.native.receive_receipt(self.root, request, receipt, "result-three")

    def test_shell_sensitive_project_and_source_paths_link_exactly(self):
        root = self.root / "project&native-%SDLC_TEST_SENTINEL%-[literal]!"
        source = self.root / "source&native-%SDLC_TEST_SENTINEL%-[literal]!"
        root.mkdir()
        shutil.copytree(self.profiles.SOURCE, source)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        fallback = mock.patch.object(Path, "symlink_to", side_effect=OSError("force Windows junction")) \
            if os.name == "nt" else nullcontext()
        with mock.patch.object(self.profiles, "SOURCE", source), \
                mock.patch.dict(os.environ, {"SDLC_TEST_SENTINEL": "expanded"}), fallback:
            self.profiles.install_profiles(root, "link", dry_run=False)
            self.assertEqual(source, (root / ".github" / "agents").resolve(strict=True))
            self.assertEqual(self.profiles.role_info("developer")["digest"],
                             self.profiles.inspect_profile(root, "developer")["digest"])
        self.assertFalse((self.root / "expanded").exists())


if __name__ == "__main__":
    unittest.main()
