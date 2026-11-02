import copy
import hashlib
import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_execution_contracts import SCRIPTS, plan, task, brief, result
from tests.test_execution_management import policy
from tests.test_execution_controls import batch_controls_policy
from artifact_contracts import ContractIssue


LIMITS = {
    "maxCalls": 8, "maxToolCalls": 16, "maxWallMs": 60000,
    "maxInputBytes": 65536, "maxOutputBytes": 65536,
}
ATTEMPT_LIMITS = {
    "maxIterations": 4, "maxToolCalls": 8, "maxInputBytes": 32768,
    "maxOutputBytes": 32768, "maxWallMs": 30000,
}


def batch(value, *, tasks=None):
    task_brief = brief(value)
    task_brief["allowedActions"] = ["read", "search", "edit"]
    task_items = tasks or [{
        "taskId": "implement", "role": "developer",
        "attempts": [
            {"attemptId": "attempt-one", "modelId": "model-one", "limits": ATTEMPT_LIMITS,
             "brief": task_brief},
            {"attemptId": "attempt-two", "modelId": "model-two", "limits": ATTEMPT_LIMITS,
             "brief": {**task_brief, "attemptId": "attempt-two"}},
        ],
    }]
    return {
        "schemaVersion": 1, "batchId": "review-batch",
        "executionId": value["executionId"], "planRevision": value["revision"],
        "tasks": task_items, "limits": LIMITS, "maxSpendMinor": None,
    }


class ExecutionOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((SCRIPTS / "execution_orchestration.py").is_file(),
                        "AC-6: finite local batch orchestration is not provided")
        self.api = importlib.import_module("execution_orchestration")
        self.manager = importlib.import_module("execution_manager")
        self.controls = importlib.import_module("execution_controls")
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.plan = plan()
        source = self.root / self.plan["sourcePlan"]["path"]
        source.parent.mkdir(parents=True)
        source.write_bytes(b"Approved orchestration fixture\n")
        self.plan["sourcePlan"]["digest"] = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
        guidance = self.root / "skills" / "sdlc-testing" / "SKILL.md"
        guidance.parent.mkdir(parents=True)
        guidance.write_text("# Synthetic approved guidance\n", encoding="utf-8")
        owned = self.root / "src" / "feature.py"
        owned.parent.mkdir(parents=True)
        owned.write_text("before\n", encoding="utf-8")
        self.runtime = importlib.import_module("bounded_runtime")

    def activate(self):
        self.manager.configure_policy(self.root, policy())
        self.manager.import_plan(self.root, self.plan)
        current = self.manager.inspect_execution(self.root, "feature-one")
        self.manager.approve_plan(self.root, "feature-one", current["planDigest"], current["policyDigest"])
        self.controls.configure_controls(self.root, batch_controls_policy())
        current = self.manager.inspect_execution(self.root, "feature-one")
        controls = self.controls.inspect_controls(self.root)
        self.controls.approve_controls(
            self.root, "feature-one", current["planDigest"], current["policyDigest"],
            controls["controlsDigest"],
        )

    def assert_issue(self, callback, code):
        with self.assertRaises(ContractIssue) as caught:
            callback()
        self.assertEqual(code, caught.exception.code)

    def test_preview_is_disabled_read_only_and_spend_cap_fails_before_dispatch(self):
        request = batch(self.plan)
        before = set(self.root.rglob("*"))
        self.assert_issue(lambda: self.api.preview_batch(self.root, request), "E_EXECUTION_DISABLED")
        self.assertEqual(before, set(self.root.rglob("*")))

        self.activate()
        request["maxSpendMinor"] = 1
        before = self.manager.inspect_execution(self.root, "feature-one")
        self.assert_issue(lambda: self.api.preview_batch(self.root, request),
                          "E_ORCHESTRATION_SPEND_UNAVAILABLE")
        self.assertEqual(before, self.manager.inspect_execution(self.root, "feature-one"))

    def fill_waiting_history(self, event_count):
        with self.manager._transaction(self.root, "feature-one") as (_, _, revision):
            while len(revision["events"]) < event_count:
                self.manager._append(revision, "TASK_BLOCKED", "implement", payload={"reason": "Fixture barrier"})
                self.manager._append(revision, "TASK_UNBLOCKED", "implement")

    def test_batch_admission_rejects_valid_near_capacity_history_before_dispatch(self):
        self.activate()
        request = batch(self.plan)
        request["tasks"][0]["attempts"] = request["tasks"][0]["attempts"][:1]
        self.fill_waiting_history(250)
        before = self.manager.execution_path(self.root, "feature-one").read_bytes()
        self.assert_issue(lambda: self.api.preview_batch(self.root, request), "E_ORCHESTRATION_CAPACITY")
        self.assertEqual(before, self.manager.execution_path(self.root, "feature-one").read_bytes())

    def test_start_rechecks_capacity_after_approval_without_writing_runtime(self):
        self.activate()
        import execution_profiles
        import execution_state
        execution_profiles.install_profiles(self.root, dry_run=False)
        request = batch(self.plan)
        request["tasks"][0]["attempts"] = request["tasks"][0]["attempts"][:1]
        preview = self.api.preview_batch(self.root, request)
        self.api.approve_batch(self.root, request, preview["batchDigest"])
        attempt = request["tasks"][0]["attempts"][0]
        envelope = self.runtime.prepare_batch(
            self.root, request, preview["batchDigest"], "implement", attempt["attemptId"],
            attempt["brief"], "developer",
            {"id": attempt["modelId"], "vendor": "synthetic", "family": "test", "version": "1"},
            attempt["limits"],
        )
        self.fill_waiting_history(250)
        before = self.manager.execution_path(self.root, "feature-one").read_bytes()
        self.assert_issue(lambda: self.runtime.start(
            self.root, envelope, execution_state.digest(envelope), execution_state.digest(envelope["request"])
        ), "E_ORCHESTRATION_CAPACITY")
        self.assertEqual(before, self.manager.execution_path(self.root, "feature-one").read_bytes())
        self.assertFalse((self.root / ".git" / "sdlc" / "bounded-runtime.json").exists())

    def test_inflight_batch_reserves_receipt_accounting_and_judgment_capacity(self):
        self.activate()
        import execution_profiles
        import execution_state
        execution_profiles.install_profiles(self.root, dry_run=False)
        request = batch(self.plan)
        request["tasks"][0]["attempts"] = request["tasks"][0]["attempts"][:1]
        self.fill_waiting_history(248)
        preview = self.api.preview_batch(self.root, request)
        self.api.approve_batch(self.root, request, preview["batchDigest"])
        attempt = request["tasks"][0]["attempts"][0]
        envelope = self.runtime.prepare_batch(
            self.root, request, preview["batchDigest"], "implement", attempt["attemptId"],
            attempt["brief"], "developer",
            {"id": attempt["modelId"], "vendor": "synthetic", "family": "test", "version": "1"},
            attempt["limits"],
        )
        self.runtime.start(
            self.root, envelope, execution_state.digest(envelope), execution_state.digest(envelope["request"])
        )
        self.assert_issue(lambda: self.manager.record_task(
            self.root, "feature-one", "implement", "progress", attempt["attemptId"], "Extra progress"
        ), "E_ORCHESTRATION_CAPACITY")
        self.runtime.step(self.root, envelope, "synthetic prompt")
        self.runtime.observe(self.root, envelope, "synthetic response")
        failed = result(self.plan)
        failed["status"] = "failed"
        failed["verification"][0].update(result="failed", command=None, revision=None, summary="failed")
        self.runtime.receive(self.root, envelope, failed)
        self.assertEqual(255, len(self.manager.inspect_execution(self.root, "feature-one")["events"]))
        self.manager.record_task(
            self.root, "feature-one", "implement", "reject", attempt["attemptId"], "Independent rejection"
        )
        self.assertEqual(256, len(self.manager.inspect_execution(self.root, "feature-one")["events"]))

    def test_pending_retry_reserves_capacity_until_real_second_start(self):
        other = task("other")
        other.update(ownership=["src/other.py"], produces=["other-output"])
        self.plan["tasks"].append(other)
        self.activate()
        import execution_profiles
        import execution_state
        execution_profiles.install_profiles(self.root, dry_run=False)
        request = batch(self.plan)
        self.fill_waiting_history(240)
        preview = self.api.preview_batch(self.root, request)
        self.api.approve_batch(self.root, request, preview["batchDigest"])

        def prepare(attempt):
            return self.runtime.prepare_batch(
                self.root, request, preview["batchDigest"], "implement", attempt["attemptId"],
                attempt["brief"], "developer",
                {"id": attempt["modelId"], "vendor": "synthetic", "family": "test", "version": "1"},
                attempt["limits"],
            )

        envelope = prepare(request["tasks"][0]["attempts"][0])
        self.runtime.start(
            self.root, envelope, execution_state.digest(envelope), execution_state.digest(envelope["request"])
        )
        self.runtime.step(self.root, envelope, "synthetic prompt")
        self.runtime.observe(self.root, envelope, "synthetic response")
        failed = result(self.plan)
        failed["status"] = "failed"
        failed["verification"][0].update(result="failed", command=None, revision=None, summary="failed")
        self.runtime.receive(self.root, envelope, failed)
        self.api.next_attempt(self.root, request, preview["batchDigest"])
        self.assertEqual(248, len(self.manager.inspect_execution(self.root, "feature-one")["events"]))
        self.assert_issue(lambda: self.manager.record_task(
            self.root, "feature-one", "other", "block", reason="Unrelated waiting task"
        ), "E_ORCHESTRATION_CAPACITY")
        envelope = prepare(request["tasks"][0]["attempts"][1])
        self.runtime.start(
            self.root, envelope, execution_state.digest(envelope), execution_state.digest(envelope["request"])
        )
        self.runtime.step(self.root, envelope, "synthetic retry prompt")
        self.runtime.observe(self.root, envelope, "synthetic retry response")
        failed["attemptId"] = "attempt-two"
        self.runtime.receive(self.root, envelope, failed)
        self.manager.record_task(
            self.root, "feature-one", "implement", "reject", "attempt-two", "Independent rejection"
        )
        inspected = self.manager.inspect_execution(self.root, "feature-one")
        self.assertEqual(255, len(inspected["events"]))
        self.assertEqual("failed", inspected["state"]["tasks"]["implement"]["status"])

    def test_pending_retry_reservation_survives_barriers_and_releases_on_cancellation(self):
        events = [
            {"type": "TASK_RETRY_READY", "taskId": "implement", "attemptId": "attempt-one",
             "payload": {"nextAttemptId": "attempt-two"}},
            {"type": "TASK_BLOCKED", "taskId": "implement", "attemptId": None, "payload": {}},
            {"type": "TASK_UNBLOCKED", "taskId": "implement", "attemptId": None, "payload": {}},
        ]
        self.assertEqual(8, self.api.terminal_reservations(events))
        events.append({"type": "TASK_CANCELLED", "taskId": "implement", "attemptId": None, "payload": {}})
        self.assertEqual(0, self.api.terminal_reservations(events))

    def test_controller_schemas_are_closed_and_all_references_resolve(self):
        schemas = {}
        for path in (SCRIPTS.parent / "contracts").glob("*.schema.json"):
            schema = json.loads(path.read_text(encoding="utf-8"))
            if "$id" in schema:
                schemas[schema["$id"]] = schema

        def verify(node, root):
            if isinstance(node, dict):
                if "$ref" in node:
                    base, _, pointer = node["$ref"].partition("#")
                    target = schemas[base] if base else root
                    for part in pointer.lstrip("/").split("/") if pointer else ():
                        part = part.replace("~1", "/").replace("~0", "~")
                        target = target[int(part)] if isinstance(target, list) else target[part]
                for child in node.values():
                    verify(child, root)
            elif isinstance(node, list):
                for child in node:
                    verify(child, root)

        expected = {
            "urn:sdlc:execution-batch:1",
            "urn:sdlc:execution-controls-policy:3",
            "urn:sdlc:execution-controls-record:3",
            "urn:sdlc:execution-event:2",
            "urn:sdlc:execution-record:2",
        }
        self.assertTrue(expected <= set(schemas))
        for name in expected:
            schema = schemas[name]
            self.assertFalse(schema["additionalProperties"], name)
            verify(schema, schema)

    def test_batch_receipt_rejects_worker_free_text_before_manager_persistence(self):
        self.activate()
        import execution_profiles
        import execution_state
        execution_profiles.install_profiles(self.root, dry_run=False)
        request = batch(self.plan)
        request["tasks"][0]["attempts"] = request["tasks"][0]["attempts"][:1]
        preview = self.api.preview_batch(self.root, request)
        self.api.approve_batch(self.root, request, preview["batchDigest"])
        attempt = request["tasks"][0]["attempts"][0]
        model = {"id": attempt["modelId"], "vendor": "synthetic", "family": "test", "version": "1"}
        envelope = self.runtime.prepare_batch(
            self.root, request, preview["batchDigest"], "implement", attempt["attemptId"],
            attempt["brief"], "developer", model, attempt["limits"],
        )
        self.runtime.start(
            self.root, envelope, execution_state.digest(envelope), execution_state.digest(envelope["request"])
        )
        self.runtime.step(self.root, envelope, "synthetic prompt")
        self.runtime.observe(self.root, envelope, "synthetic response")
        reported = result(self.plan)
        reported["attemptId"] = attempt["attemptId"]
        reported["findings"] = ["RAW_WORKER_TEXT_MUST_NOT_BE_PERSISTED"]
        self.assert_issue(
            lambda: self.runtime.receive(self.root, envelope, reported), "E_RUNTIME_PROTOCOL"
        )
        self.runtime.stop(self.root, envelope)
        stored = self.manager.inspect_execution(self.root, "feature-one")
        self.assertEqual({}, stored["record"]["revisions"][-1]["receipts"])

    def test_failed_batch_receipt_is_digest_only_and_permits_only_prebound_retry(self):
        self.activate()
        import execution_profiles
        import execution_state
        execution_profiles.install_profiles(self.root, dry_run=False)
        request = batch(self.plan)
        request["tasks"][0]["attempts"][0]["brief"]["verification"] = "RAW_BATCH_PROMPT_MUST_NOT_PERSIST"
        preview = self.api.preview_batch(self.root, request)
        self.api.approve_batch(self.root, request, preview["batchDigest"])
        first = request["tasks"][0]["attempts"][0]
        model = {"id": first["modelId"], "vendor": "synthetic", "family": "test", "version": "1"}
        envelope = self.runtime.prepare_batch(
            self.root, request, preview["batchDigest"], "implement", first["attemptId"],
            first["brief"], "developer", model, first["limits"],
        )
        self.runtime.start(
            self.root, envelope, execution_state.digest(envelope), execution_state.digest(envelope["request"])
        )
        self.runtime.step(self.root, envelope, "RAW_MODEL_PROMPT_MUST_NOT_PERSIST")
        self.runtime.observe(self.root, envelope, "RAW_PROVIDER_TRANSCRIPT_MUST_NOT_PERSIST")
        failed = result(self.plan)
        failed["attemptId"] = first["attemptId"]
        failed["status"] = "failed"
        failed["verification"][0].update(
            result="failed", command=None, revision=None, summary="failed"
        )
        receipt = self.runtime.receive(self.root, envelope, failed)
        self.assertEqual("not-assessed", receipt["semanticApproval"])

        inspected = self.manager.inspect_execution(self.root, "feature-one")
        runtime_store = json.loads(
            (self.root / ".git" / "sdlc" / "bounded-runtime.json").read_text(encoding="utf-8")
        )
        saved = inspected["record"]["revisions"][-1]["receipts"][runtime_store["callId"]]
        self.assertEqual({"briefDigest", "resultScope", "result"}, set(saved))
        self.assertEqual(execution_state.digest(first["brief"]), saved["briefDigest"])
        serialized = (self.manager.execution_path(self.root, "feature-one")).read_bytes()
        self.assertNotIn(b"RAW_BATCH_PROMPT_MUST_NOT_PERSIST", serialized)
        self.assertNotIn(b"RAW_MODEL_PROMPT_MUST_NOT_PERSIST", serialized)
        self.assertNotIn(b"RAW_PROVIDER_TRANSCRIPT_MUST_NOT_PERSIST", serialized)

        next_attempt = self.api.next_attempt(self.root, request, preview["batchDigest"])
        self.assertEqual(("attempt-two", "model-two", True), (
            next_attempt["attemptId"], next_attempt["modelId"], next_attempt["dispatch"]
        ))
        after = self.manager.inspect_execution(self.root, "feature-one")
        self.assertEqual("ready", after["state"]["tasks"]["implement"]["status"])
        self.assertEqual("attempt-two", after["state"]["tasks"]["implement"]["pendingAttemptId"])

    def test_batch_approval_binds_exact_digest_and_current_policy(self):
        self.activate()
        request = batch(self.plan)
        marker = "RAW_BATCH_PROMPT_MUST_NOT_BE_PERSISTED"
        request["tasks"][0]["attempts"][0]["brief"]["verification"] = marker
        preview = self.api.preview_batch(self.root, request)
        approved = self.api.approve_batch(self.root, request, preview["batchDigest"])
        self.assertEqual(preview["batchDigest"], approved["batchDigest"])
        controls_path = self.controls.controls_path(self.root)
        self.assertNotIn(marker.encode(), controls_path.read_bytes())

        changed = copy.deepcopy(request)
        changed["tasks"][0]["attempts"][0]["modelId"] = "model-two"
        self.assert_issue(
            lambda: self.api.next_attempt(self.root, changed, preview["batchDigest"]),
            "E_ORCHESTRATION_APPROVAL",
        )

    def test_strict_cli_preview_preserves_batch_digest_and_rejects_duplicate_input_keys(self):
        self.activate()
        request = batch(self.plan)
        command = [sys.executable, "-I", "-S", str(SCRIPTS / "manage_runtime.py"),
                   "preview_batch_json", "--project-root", str(self.root)]
        raw = json.dumps(request, indent=2)
        duplicate = raw.replace(
            '"batchId": "review-batch"', '"batchId": "review-batch",\n      "batchId": "shadow"', 1
        )
        refused = subprocess.run(
            command, input=json.dumps({"batchJson": duplicate}), capture_output=True, text=True
        )
        self.assertNotEqual(0, refused.returncode)
        self.assertIn("E_JSON_DUPLICATE", refused.stderr)

        completed = subprocess.run(
            command, input=json.dumps({"batchJson": raw}), capture_output=True, text=True
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        preview = json.loads(completed.stdout)
        self.assertEqual(request, preview["batch"])
        self.assertEqual(self.api.preview_batch(self.root, request)["batchDigest"], preview["batchDigest"])

    def test_dependency_waits_for_independent_acceptance(self):
        child = task("verify")
        child.update(prerequisites=["implement"], consumes=["implementation"],
                     produces=["verified"], ownership=["tests/feature.py"])
        self.plan["tasks"].append(child)
        self.activate()
        request = batch(self.plan, tasks=[
            {"taskId": identifier, "role": "developer",
             "attempts": [{"attemptId": identifier + "-first", "modelId": "model-one",
                           "limits": ATTEMPT_LIMITS,
                           "brief": {
                               **batch(self.plan)["tasks"][0]["attempts"][0]["brief"],
                               "taskId": identifier, "attemptId": identifier + "-first",
                               "ownership": ["src/feature.py" if identifier == "implement"
                                             else "tests/feature.py"],
                           }}]}
            for identifier in ("implement", "verify")
        ])
        preview = self.api.preview_batch(self.root, request)
        self.api.approve_batch(self.root, request, preview["batchDigest"])
        first = self.api.next_attempt(self.root, request, preview["batchDigest"])
        self.assertEqual(("implement", "implement-first"),
                         (first["taskId"], first["attemptId"]))

        self.manager.record_task(self.root, "feature-one", "implement", "ready")
        self.manager.record_task(self.root, "feature-one", "implement", "start", "implement-first")
        first_brief = request["tasks"][0]["attempts"][0]["brief"]
        first_result = result(self.plan)
        first_result["attemptId"] = "implement-first"
        first_result["verification"][0]["revision"] = "checked-revision"
        self.manager.receive_result(self.root, "feature-one", "result-one", first_brief, first_result)
        waiting = self.api.next_attempt(self.root, request, preview["batchDigest"])
        self.assertEqual("waiting-for-acceptance", waiting["status"])

        self.manager.accept_task(self.root, "feature-one", {
            "schemaVersion": 1, "taskId": "implement", "attemptId": "implement-first",
            "resultId": "result-one", "acceptanceCriteria": ["AC-1"],
            "revision": "checked-revision", "command": "python -B -m unittest",
            "summary": "Independent manager judgment",
        })
        next_task = self.api.next_attempt(self.root, request, preview["batchDigest"])
        self.assertEqual(("verify", "verify-first"),
                         (next_task["taskId"], next_task["attemptId"]))

    def test_version_two_retry_event_preserves_version_one_replay_failure(self):
        self.activate()
        self.manager.record_task(self.root, "feature-one", "implement", "ready")
        self.manager.record_task(self.root, "feature-one", "implement", "start", "attempt-one")
        failed = result(self.plan)
        failed["status"] = "failed"
        failed["verification"][0]["result"] = "failed"
        self.manager.receive_result(self.root, "feature-one", "result-one", brief(self.plan), failed)

        with self.assertRaises(ContractIssue) as missing_accounting:
            with self.manager._transaction(self.root, "feature-one") as (_, record, revision):
                self.manager._append_controller(record, revision, "TASK_RETRY_READY", "implement", "attempt-one", {
                    "batchId": "review-batch", "batchDigest": "sha256:" + "a" * 64,
                    "resultId": "result-one", "nextAttemptId": "attempt-two", "modelId": "model-two",
                })
        self.assertEqual("E_EXECUTION_TRANSITION", missing_accounting.exception.code)

        with self.manager._transaction(self.root, "feature-one") as (_, record, revision):
            batch_digest = "sha256:" + "a" * 64
            self.manager._append_controller(record, revision, "BATCH_ATTEMPT_ACCOUNTED", "implement", "attempt-one", {
                "batchId": "review-batch", "batchDigest": batch_digest, "resultId": "result-one",
                "briefDigest": self.api.state.digest(revision["receipts"]["result-one"]["brief"]),
                "modelCalls": 1, "toolCalls": 0, "elapsedMs": 1, "inputBytes": 1, "outputBytes": 1,
            })
            self.manager._append_controller(record, revision, "TASK_RETRY_READY", "implement", "attempt-one", {
                "batchId": "review-batch", "batchDigest": batch_digest,
                "resultId": "result-one", "nextAttemptId": "attempt-two", "modelId": "model-two",
            })

        inspected = self.manager.inspect_execution(self.root, "feature-one")
        self.assertEqual(2, inspected["record"]["schemaVersion"])
        self.assertEqual("ready", inspected["state"]["tasks"]["implement"]["status"])
        self.assertNotIn("attempt-two", inspected["state"]["attemptIds"])
        with self.assertRaises(ContractIssue) as caught:
            self.api.state.replay_execution(
                inspected["plan"], inspected["events"], inspected["receipts"],
                inspected["recordedPolicyDigest"], inspected["acceptances"], inspected["approvals"],
            )
        self.assertEqual("E_EXECUTION_VERSION", caught.exception.code)

        self.manager.record_task(self.root, "feature-one", "implement", "start", "attempt-two")
        self.assertEqual(["attempt-one", "attempt-two"],
                         self.manager.inspect_execution(self.root, "feature-one")["state"]["attemptIds"])

    def test_retry_replay_rejects_nonfailed_or_mismatched_receipt(self):
        self.activate()
        self.manager.record_task(self.root, "feature-one", "implement", "ready")
        self.manager.record_task(self.root, "feature-one", "implement", "start", "attempt-one")
        self.manager.receive_result(self.root, "feature-one", "result-one", brief(self.plan), result(self.plan))
        with self.assertRaises(ContractIssue) as caught:
            with self.manager._transaction(self.root, "feature-one") as (_, record, revision):
                self.manager._append_controller(record, revision, "TASK_RETRY_READY", "implement", "attempt-one", {
                    "batchId": "review-batch", "batchDigest": "sha256:" + "a" * 64,
                    "resultId": "result-one", "nextAttemptId": "attempt-two", "modelId": "model-two",
                })
        self.assertEqual("E_EXECUTION_TRANSITION", caught.exception.code)
