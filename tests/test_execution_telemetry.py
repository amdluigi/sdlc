import copy
import importlib
import json
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.test_execution_contracts import SCRIPTS, plan, brief, result
from tests.test_execution_management import policy
from tests.test_native_execution import HOST
from artifact_contracts import ContractIssue


class ExecutionTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((SCRIPTS / "execution_telemetry.py").is_file(), "Attributed telemetry is not provided")
        self.telemetry = importlib.import_module("execution_telemetry")
        self.manager = importlib.import_module("execution_manager")
        self.state = importlib.import_module("execution_state")
        self.native = importlib.import_module("native_execution")
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.plan = plan()

    def activate(self, native=False):
        self.manager.configure_policy(self.root, policy())
        self.manager.import_plan(self.root, self.plan)
        inspected = self.manager.inspect_execution(self.root, "feature-one")
        self.manager.approve_plan(self.root, "feature-one", inspected["planDigest"], inspected["policyDigest"])
        if native:
            importlib.import_module("execution_profiles").install_profiles(self.root, dry_run=False)
            supplied = brief(self.plan)
            supplied["guidance"] = []
            request = self.native.prepare_request(self.root, "feature-one", supplied, "developer", HOST)
            self.native.start_request(self.root, request, self.state.digest(request))
            receipt = {"schemaVersion": 1, "requestDigest": self.state.digest(request), "hostId": HOST["id"],
                       "hostBuild": HOST["build"], "callId": "call-one", "result": result(self.plan)}
            self.native.receive_receipt(self.root, request, receipt, "result-one")
        else:
            self.manager.record_task(self.root, "feature-one", "implement", "ready")
            self.manager.record_task(self.root, "feature-one", "implement", "start", "attempt-one")

    def observation(self, native=False):
        return {
            "schemaVersion": 1, "id": "observation-one",
            "binding": {"executionId": "feature-one", "planRevision": self.plan["revision"],
                        "planDigest": self.state.digest(self.plan)},
            "taskId": "implement", "attemptId": "attempt-one",
            "source": {"kind": "host-observation" if native else "manual-declaration",
                       "hostId": HOST["id"] if native else None, "hostBuild": HOST["build"] if native else None,
                       "callId": "call-one" if native else None},
            "requestedModel": None, "observedModel": None, "inventoryDigest": None,
            "window": {"clockId": "clock-one", "startMs": 100, "endMs": 130},
            "durationMs": 20, "usage": {"requests": None, "inputTokens": None, "outputTokens": None},
            "pricing": None,
        }

    def issue(self, callback, code=None):
        with self.assertRaises(ContractIssue) as caught:
            callback()
        if code:
            self.assertEqual(code, caught.exception.code)

    def test_absent_disabled_and_dry_run_never_capture_or_write(self):
        before = set(self.root.rglob("*"))
        self.assertFalse(self.telemetry.inspect_telemetry(self.root)["enabled"])
        self.assertFalse(self.telemetry.record_observation(self.root, self.observation())["recorded"])
        self.telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True}, dry_run=True)
        self.assertEqual(before, set(self.root.rglob("*")))
        self.activate()
        self.assertIsNone(self.telemetry.inspect_telemetry(self.root)["store"])
        self.telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": False})
        stored = self.telemetry.inspect_telemetry(self.root)["store"]
        self.assertFalse(self.telemetry.record_observation(self.root, self.observation())["recorded"])
        self.assertEqual(stored, self.telemetry.inspect_telemetry(self.root)["store"])
        self.assertFalse((self.root / ".sdlc" / "config.json").exists())

    def test_manual_declarations_have_no_observed_model_usage_or_cost(self):
        self.activate()
        self.telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True})
        self.assertTrue(self.telemetry.record_observation(self.root, self.observation())["recorded"])
        stored = self.telemetry.inspect_telemetry(self.root)["store"]["observations"][0]
        self.assertEqual("manual-declaration", stored["observation"]["source"]["kind"])
        self.assertEqual(1, stored["consentGeneration"])
        self.assertIsNone(stored["observation"]["pricing"])
        altered = self.observation()
        altered["id"], altered["usage"]["requests"] = "observation-two", 1
        self.issue(lambda: self.telemetry.record_observation(self.root, altered), "E_TELEMETRY_ATTRIBUTION")

    def test_legacy_model_label_is_preserved_without_claiming_inventory_identity(self):
        label = "GPT 5.4"
        self.plan["tasks"][0]["assignment"]["model"] = label
        self.activate()
        self.telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True})
        supplied = self.observation()
        supplied["requestedModel"] = label
        self.assertTrue(self.telemetry.record_observation(self.root, supplied)["recorded"])
        saved = self.telemetry.inspect_telemetry(self.root)["store"]["observations"][0]["observation"]
        self.assertEqual(label, saved["requestedModel"])
        self.assertIsNone(saved["observedModel"])

    def test_host_observation_requires_bound_native_receipt(self):
        self.activate()
        self.telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True})
        self.issue(lambda: self.telemetry.record_observation(self.root, self.observation(True)),
                   "E_TELEMETRY_ATTRIBUTION")

    def test_host_model_and_price_match_supplied_inventory_without_authentication_claim(self):
        self.activate(native=True)
        self.telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True})
        pricing = {"currency": "USD", "rateVersion": "rate-one", "unit": "input-token",
                   "units": 1000, "priceMinor": 2}
        inventory = {"schemaVersion": 1, "hostId": HOST["id"], "hostBuild": HOST["build"],
                     "source": "host-observation", "models": [
                         {"id": "model-one", "available": True, "pricing": pricing},
                     ]}
        supplied = self.observation(True)
        supplied["observedModel"], supplied["inventoryDigest"] = "model-one", self.state.digest(inventory)
        supplied["pricing"], supplied["usage"]["inputTokens"] = pricing, 1500
        self.issue(lambda: self.telemetry.record_observation(self.root, supplied), "E_TELEMETRY_ATTRIBUTION")
        self.assertTrue(self.telemetry.record_observation(self.root, supplied, inventory)["recorded"])
        self.assertEqual(1500, self.telemetry.inspect_telemetry(self.root)["store"]["observations"][0][
            "observation"]["usage"]["inputTokens"])
        altered = copy.deepcopy(supplied)
        altered["id"], altered["pricing"]["rateVersion"] = "observation-two", "unknown-rate"
        self.issue(lambda: self.telemetry.record_observation(self.root, altered, inventory),
                   "E_TELEMETRY_ATTRIBUTION")

    def test_missing_host_model_price_and_usage_remain_null(self):
        self.activate(native=True)
        self.telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True})
        supplied = self.observation(True)
        supplied["durationMs"] = None
        self.telemetry.record_observation(self.root, supplied)
        saved = self.telemetry.inspect_telemetry(self.root)["store"]["observations"][0]["observation"]
        for key in ("durationMs", "observedModel", "pricing", "inventoryDigest"):
            self.assertIsNone(saved[key])
        self.assertEqual({"requests": None, "inputTokens": None, "outputTokens": None}, saved["usage"])

    def test_exact_repeat_idempotent_conflict_and_overlap_refused(self):
        self.activate()
        self.telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True})
        supplied = self.observation()
        self.telemetry.record_observation(self.root, supplied)
        self.assertTrue(self.telemetry.record_observation(self.root, supplied)["idempotent"])
        changed = copy.deepcopy(supplied)
        changed["durationMs"] += 1
        self.issue(lambda: self.telemetry.record_observation(self.root, changed), "E_TELEMETRY_DUPLICATE")
        overlapping = copy.deepcopy(supplied)
        overlapping["id"] = "observation-two"
        self.issue(lambda: self.telemetry.record_observation(self.root, overlapping), "E_TELEMETRY_WINDOW")
        overlapping["window"]["startMs"], overlapping["window"]["endMs"] = 130, 160
        self.telemetry.record_observation(self.root, overlapping)
        self.assertEqual(2, len(self.telemetry.inspect_telemetry(self.root)["store"]["observations"]))

    def test_invalid_clock_interval_values_and_sensitive_fields_rejected(self):
        self.activate()
        self.telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True})
        invalid = []
        for field, value in (("durationMs", True), ("durationMs", -1), ("durationMs", 31),
                             ("durationMs", 1.5), ("durationMs", 2**63), ("prompt", "Never retain this")):
            invalid.append({**self.observation(), field: value})
        reversed_window = self.observation()
        reversed_window["window"]["endMs"] = 99
        invalid.append(reversed_window)
        for supplied in invalid:
            self.issue(lambda: self.telemetry.record_observation(self.root, supplied))
        self.assertEqual([], self.telemetry.inspect_telemetry(self.root)["store"]["observations"])

    def test_stale_binding_wrong_attempt_and_host_call_are_not_attributable(self):
        self.activate(native=True)
        self.telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True})
        for field, value in (("taskId", "unknown"), ("attemptId", "other-attempt"), ("requestedModel", "model-one")):
            self.issue(lambda: self.telemetry.record_observation(
                self.root, {**self.observation(True), field: value}), "E_TELEMETRY_ATTRIBUTION")
        wrong = self.observation(True)
        wrong["source"]["callId"] = "other-call"
        self.issue(lambda: self.telemetry.record_observation(self.root, wrong), "E_TELEMETRY_ATTRIBUTION")
        wrong = self.observation(True)
        wrong["binding"]["planDigest"] = "sha256:" + "0" * 64
        self.issue(lambda: self.telemetry.record_observation(self.root, wrong), "E_TELEMETRY_ATTRIBUTION")

    def test_revocation_retains_data_and_cannot_renew_old_observation_consent(self):
        self.activate()
        self.telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True})
        supplied = self.observation()
        self.telemetry.record_observation(self.root, supplied)
        self.telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": False})
        self.assertFalse(self.telemetry.record_observation(self.root, supplied)["recorded"])
        self.assertEqual(1, len(self.telemetry.inspect_telemetry(self.root)["store"]["observations"]))
        self.telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True})
        self.issue(lambda: self.telemetry.record_observation(self.root, supplied), "E_TELEMETRY_CONSENT")

    def test_delete_requires_current_digest_preserves_consent_and_changes_generation(self):
        self.activate()
        self.telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True})
        self.telemetry.record_observation(self.root, self.observation())
        current = self.telemetry.inspect_telemetry(self.root)
        self.issue(lambda: self.telemetry.delete_observations(self.root, "sha256:" + "0" * 64),
                   "E_TELEMETRY_CONSENT")
        self.telemetry.delete_observations(self.root, current["storeDigest"])
        after = self.telemetry.inspect_telemetry(self.root)
        self.assertTrue(after["enabled"])
        self.assertEqual([], after["store"]["observations"])
        self.assertGreater(after["store"]["generation"], current["store"]["generation"])

    def test_locks_atomic_failures_and_corrupt_state_fail_explicitly(self):
        self.activate()
        self.telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True})
        path = self.telemetry.telemetry_path(self.root)
        before = path.read_bytes()
        lock = self.manager.lock_path(self.root)
        lock.write_text("other owner", encoding="ascii")
        self.issue(lambda: self.telemetry.configure_telemetry(
            self.root, {"schemaVersion": 1, "enabled": False}), "E_EXECUTION_BUSY")
        self.assertEqual(before, path.read_bytes())
        lock.unlink()
        with mock.patch.object(self.manager.os, "replace", side_effect=OSError("synthetic promotion failure")):
            self.issue(lambda: self.telemetry.record_observation(self.root, self.observation()))
        self.assertEqual(before, path.read_bytes())
        path.write_text('{"schemaVersion":1}', encoding="utf-8")
        self.issue(lambda: self.telemetry.inspect_telemetry(self.root))

    def test_fallback_no_new_ignore_requirement_when_absent_but_exact_proof_on_write(self):
        project = self.root / "project"
        project.mkdir()
        ignore = self.root / ".gitignore"
        ignore.write_text("project/.sdlc/local/executions\nproject/.sdlc/local/executions.lock\n", encoding="utf-8")
        before = set(project.rglob("*"))
        self.assertFalse(self.telemetry.inspect_telemetry(project)["enabled"])
        self.issue(lambda: self.telemetry.configure_telemetry(
            project, {"schemaVersion": 1, "enabled": False}), "E_TELEMETRY_STORAGE")
        self.assertEqual(before, set(project.rglob("*")))
        with ignore.open("a", encoding="utf-8") as output:
            output.write("project/.sdlc/local/execution-telemetry.json\n")
        self.telemetry.configure_telemetry(project, {"schemaVersion": 1, "enabled": False})
        self.assertTrue(self.telemetry.telemetry_path(project).is_file())

    def test_cli_consent_record_inspect_delete_and_error_shapes(self):
        self.assertTrue((SCRIPTS / "manage_telemetry.py").is_file(), "Explicit telemetry CLI is not provided")
        self.activate()
        supplied = self.root / "telemetry-input.json"

        def command(*arguments):
            completed = subprocess.run([sys.executable, "-B", str(SCRIPTS / "manage_telemetry.py"),
                                        *arguments, "--project-root", str(self.root)],
                                       capture_output=True, text=True)
            self.assertEqual(0, completed.returncode, completed.stderr)
            return json.loads(completed.stdout)

        supplied.write_text(json.dumps({"schemaVersion": 1, "enabled": True}), encoding="utf-8")
        self.assertTrue(command("configure", "--input", str(supplied), "--dry-run")["dryRun"])
        self.assertIsNone(command("inspect")["store"])
        command("configure", "--input", str(supplied))
        supplied.write_text(json.dumps({"schemaVersion": 1, "observation": self.observation(), "inventory": None}),
                            encoding="utf-8")
        self.assertTrue(command("record", "--input", str(supplied))["recorded"])
        inspected = command("inspect")
        self.assertEqual(1, len(inspected["store"]["observations"]))
        command("delete", "--store-digest", inspected["storeDigest"])
        self.assertTrue(command("inspect")["enabled"])
        supplied.write_text('{"schemaVersion":1,"schemaVersion":1}', encoding="utf-8")
        rejected = subprocess.run([sys.executable, "-B", str(SCRIPTS / "manage_telemetry.py"), "record",
                                   "--input", str(supplied), "--project-root", str(self.root)],
                                  capture_output=True, text=True)
        self.assertNotEqual(0, rejected.returncode)
        self.assertEqual("", rejected.stdout)
        self.assertIn("error[", rejected.stderr)
        self.assertNotIn("Traceback", rejected.stderr)

    def test_zero_length_windows_cannot_be_counted_twice_and_capacity_fails_without_pruning(self):
        self.activate()
        self.telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True})
        empty = self.observation()
        empty["window"]["endMs"], empty["durationMs"] = empty["window"]["startMs"], 0
        self.telemetry.record_observation(self.root, empty)
        self.issue(lambda: self.telemetry.record_observation(
            self.root, {**empty, "id": "observation-two"}), "E_TELEMETRY_WINDOW")
        current = self.telemetry.inspect_telemetry(self.root)["store"]
        rows = []
        for index in range(256):
            supplied = self.observation()
            supplied["id"] = "observation-" + str(index)
            supplied["window"]["startMs"], supplied["window"]["endMs"] = index * 30, index * 30 + 30
            rows.append({"consentGeneration": current["generation"], "observation": supplied})
        current["observations"] = rows
        with self.manager._writer(self.root):
            self.manager._write(self.root, self.telemetry.telemetry_path(self.root), self.telemetry._store(current))
        before = self.telemetry.telemetry_path(self.root).read_bytes()
        extra = self.observation()
        extra["id"] = "observation-extra"
        extra["window"]["startMs"], extra["window"]["endMs"] = 9000, 9030
        self.issue(lambda: self.telemetry.record_observation(self.root, extra), "E_EXECUTION_LIMIT")
        self.assertEqual(before, self.telemetry.telemetry_path(self.root).read_bytes())

    def test_new_schema_roots_references_and_text_boundaries_match_runtime(self):
        directory = SCRIPTS.parent / "contracts"
        schemas = {item["$id"]: item for item in (
            json.loads(path.read_text(encoding="utf-8")) for path in directory.glob("*.schema.json"))}
        fixtures = {
            "execution-telemetry-policy": {"schemaVersion": 1, "enabled": False},
            "execution-observation": self.observation(),
            "execution-telemetry-record": {"schemaVersion": 1, "generation": 1,
                                           "enabled": False, "observations": []},
        }

        def resolve(specification, document):
            identity, separator, fragment = specification["$ref"].partition("#")
            target_document = schemas[identity] if identity else document
            target = target_document
            if separator:
                for part in fragment.lstrip("/").split("/"):
                    target = target[part]
            return target, target_document

        def references(value, document):
            if isinstance(value, dict):
                if "$ref" in value:
                    resolve(value, document)
                for child in value.values():
                    references(child, document)
            elif isinstance(value, list):
                for child in value:
                    references(child, document)

        def text_valid(specification, text, document):
            if "$ref" in specification:
                target, target_document = resolve(specification, document)
                if not text_valid(target, text, target_document):
                    return False
            return (specification.get("minLength", 0) <= len(text)
                    <= specification.get("maxLength", len(text))
                    and ("pattern" not in specification
                         or re.search(specification["pattern"], text) is not None))

        for name, fixture in fixtures.items():
            document = schemas["urn:sdlc:" + name + ":1"]
            self.assertEqual(set(fixture), set(document["required"]))
            self.assertEqual(set(fixture), set(document["properties"]))
            self.assertFalse(document["additionalProperties"])
            references(document, document)
        observation_schema = schemas["urn:sdlc:execution-observation:1"]
        source = observation_schema["properties"]["source"]["properties"]
        for field, maximum in (("hostBuild", 128), ("callId", 256), ("requestedModel", 128)):
            specification = (observation_schema["properties"] if field == "requestedModel" else source)[
                field]["oneOf"][1]
            for text, expected in (("a" * maximum, True), ("a" * (maximum + 1), False),
                                   ("\t", False), ("host\n", False), (" \x7f", False)):
                with self.subTest(field=field, length=len(text)):
                    self.assertEqual(expected, text_valid(specification, text, observation_schema))
                    supplied = self.observation(True)
                    (supplied if field == "requestedModel" else supplied["source"])[field] = text
                    if expected:
                        self.telemetry.validate_observation(supplied)
                    else:
                        self.issue(lambda: self.telemetry.validate_observation(supplied))

    def test_base_revocation_and_native_manual_masquerade_never_capture(self):
        self.activate(native=True)
        self.telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True})
        before = self.telemetry.telemetry_path(self.root).read_bytes()
        self.issue(lambda: self.telemetry.record_observation(self.root, self.observation()),
                   "E_TELEMETRY_ATTRIBUTION")
        self.manager.configure_policy(self.root, {**policy(), "enabled": False})
        self.issue(lambda: self.telemetry.record_observation(self.root, self.observation(True)))
        self.assertEqual(before, self.telemetry.telemetry_path(self.root).read_bytes())

    def test_real_selected_snapshot_cli_keeps_unicode_digest_and_is_read_only(self):
        self.plan["tasks"][0]["title"] = "Review caf\u00e9 \U0001f680"
        self.activate()
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        completed = subprocess.run([sys.executable, "-B", str(SCRIPTS / "manage_insights.py"),
                                    "snapshot", "--project-root", str(self.root),
                                    "--execution-id", "feature-one"], capture_output=True, text=True)
        self.assertEqual(0, completed.returncode, completed.stderr)
        snapshot = json.loads(completed.stdout)
        expected_digest = snapshot.pop("snapshotDigest")
        self.assertEqual(expected_digest, self.state.digest(snapshot))
        self.assertEqual("sdlc-execution-snapshot", snapshot["kind"])
        self.assertEqual(self.plan["tasks"][0]["title"], snapshot["tasks"][0]["title"])
        self.assertEqual("running", snapshot["tasks"][0]["status"])
        self.assertTrue(snapshot["approved"])
        self.assertEqual(before, {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()})

    def test_actual_competing_revocation_is_rechecked_before_recording(self):
        self.competing_consent_change(False)

    def test_actual_disable_reenable_cannot_authorize_a_preexisting_capture(self):
        self.competing_consent_change(True)

    def competing_consent_change(self, reenable):
        self.activate()
        self.telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True})
        data = self.root / "observation.json"
        data.write_text(json.dumps(self.observation()), encoding="utf-8")
        ready, release = self.root / "ready.signal", self.root / "release.signal"
        child = (
            "import json,pathlib,sys,time\n"
            "sys.path.insert(0,sys.argv[1])\n"
            "import execution_telemetry as telemetry\n"
            "ready,release=pathlib.Path(sys.argv[4]),pathlib.Path(sys.argv[5])\n"
            "def trace(frame,event,arg):\n"
            "    if event=='line' and frame.f_code.co_name=='record_observation':\n"
            "        line=pathlib.Path(frame.f_code.co_filename).read_text().splitlines()[frame.f_lineno-1]\n"
            "        if line.strip()=='with manager._writer(root):':\n"
            "            ready.write_text('preflight-read')\n"
            "            deadline=time.monotonic()+20\n"
            "            while not release.exists():\n"
            "                if time.monotonic()>deadline: raise TimeoutError('test synchronization')\n"
            "                time.sleep(0.02)\n"
            "            sys.settrace(None)\n"
            "    return trace\n"
            "sys.settrace(trace)\n"
            "value=json.loads(pathlib.Path(sys.argv[3]).read_text())\n"
            "try:\n"
            "    print(json.dumps(telemetry.record_observation(sys.argv[2],value)))\n"
            "except telemetry.ContractIssue as error:\n"
            "    print(error.cli_message(),file=sys.stderr)\n"
            "    sys.exit(error.exit_code)\n"
        )
        process = subprocess.Popen([sys.executable, "-B", "-c", child, str(SCRIPTS), str(self.root),
                                    str(data), str(ready), str(release)], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 20
            while not ready.exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    self.fail("Child did not reach the consent boundary")
                time.sleep(0.02)
            self.telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": False})
            if reenable:
                self.telemetry.configure_telemetry(self.root, {"schemaVersion": 1, "enabled": True})
            disabled = self.telemetry.telemetry_path(self.root).read_bytes()
            release.write_text("continue", encoding="ascii")
            stdout, stderr = process.communicate(timeout=20)
            if reenable:
                self.assertNotEqual(0, process.returncode)
                self.assertIn("E_TELEMETRY_CONSENT", stderr)
                self.assertEqual("", stdout)
            else:
                self.assertEqual(0, process.returncode, stderr)
                self.assertFalse(json.loads(stdout)["recorded"])
            self.assertEqual(disabled, self.telemetry.telemetry_path(self.root).read_bytes())
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)


if __name__ == "__main__":
    unittest.main()
