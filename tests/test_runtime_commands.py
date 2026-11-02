import importlib
import copy
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from tests import test_bounded_runtime as bounded_tests
from tests.test_bounded_runtime import MODEL, LIMITS
from tests.test_execution_contracts import result, SCRIPTS
from tests.test_execution_controls import controls_policy
import execution_controls as controls
import execution_manager as manager
import execution_state as state
from artifact_contracts import ContractIssue


class RuntimeCommandsTests(unittest.TestCase):
    setUp = bounded_tests.BoundedRuntimeTests.setUp
    prepare = bounded_tests.BoundedRuntimeTests.prepare
    start = bounded_tests.BoundedRuntimeTests.start
    issue = bounded_tests.BoundedRuntimeTests.issue
    tool = bounded_tests.BoundedRuntimeTests.tool

    def command(self, code, **changes):
        return {"id": "check", "executable": str(Path(sys.executable).resolve()),
                "argv": ["-I", "-S", "-c", code], "cwd": str(self.root),
                "timeoutMs": 1500, "maxOutputBytes": 2048, **changes}

    def test_regular_or_missing_leaf_swapped_to_outside_link_is_rejected(self):
        project = self.root / "boundary"
        project.mkdir()
        outside = self.root / "outside-boundary"
        outside.mkdir()
        leaf = project / "record"
        original_lstat = Path.lstat

        def link():
            try:
                leaf.symlink_to(outside, target_is_directory=True)
            except OSError as error:
                if os.name != "nt" or error.winerror != 1314:
                    raise
                subprocess.run(["cmd", "/c", "mklink", "/J", str(leaf), str(outside)],
                               check=True, capture_output=True)

        for existing, writer_lock in ((True, False), (False, False), (True, True), (False, True)):
            with self.subTest(existing=existing, writer_lock=writer_lock):
                if existing:
                    leaf.write_bytes(b"regular")
                swapped = False

                def swap_after_metadata(path, *args, **kwargs):
                    nonlocal swapped
                    if path != leaf or swapped:
                        return original_lstat(path, *args, **kwargs)
                    swapped = True
                    try:
                        metadata = original_lstat(path, *args, **kwargs)
                    except FileNotFoundError:
                        link()
                        raise
                    leaf.unlink()
                    link()
                    return metadata

                try:
                    with mock.patch.object(Path, "lstat", swap_after_metadata):
                        with self.assertRaises(ContractIssue) as caught:
                            manager._safe(project, leaf, _writer_lock=writer_lock)
                    self.assertEqual("E_EXECUTION_PATH", caught.exception.code)
                    self.assertTrue(swapped)
                finally:
                    if leaf.is_symlink():
                        leaf.unlink()
                    elif leaf.exists():
                        leaf.rmdir()

    @unittest.skipUnless(os.name == "nt", "Windows deleted-file final-path race")
    def test_deleted_identity_exception_is_exclusive_to_writer_lock_checks(self):
        metrics = importlib.import_module("manage_metrics")
        leaf = self.root / ".git" / "sdlc" / "executions.lock"
        leaf.parent.mkdir(parents=True, exist_ok=True)
        leaf.write_bytes(b"regular")
        original_resolve = Path.resolve
        tombstone = Path(self.root.anchor) / "$Extend" / "$Deleted" / "deleted-lock-id"

        def deleted_identity(path, *args, **kwargs):
            return tombstone if path == leaf else original_resolve(path, *args, **kwargs)

        with mock.patch.object(Path, "resolve", deleted_identity):
            with self.assertRaises(metrics.MetricsError):
                metrics._verify_existing_components(self.root, leaf)
            self.assertEqual(leaf, metrics._verify_existing_components(
                self.root, leaf, ephemeral_lock=True))
            leaf.unlink()
            self.assertEqual(leaf, metrics._verify_existing_components(
                self.root, leaf, ephemeral_lock=True))

    @unittest.skipUnless(os.name == "nt", "Windows deleted-file final-path race")
    def test_disappearing_regular_lock_keeps_its_checked_parent_boundary(self):
        lock = self.root / ".git" / "sdlc" / "executions.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        stop = threading.Event()
        errors = []

        def churn():
            try:
                while not stop.is_set():
                    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    os.close(descriptor)
                    lock.unlink()
            except BaseException as error:
                errors.append(error)

        worker = threading.Thread(target=churn)
        worker.start()
        try:
            for _ in range(2000):
                self.assertEqual(lock, manager._safe(self.root, lock, _writer_lock=True))
        finally:
            stop.set()
            worker.join()
        self.assertEqual([], errors)

    @unittest.skipUnless(os.name == "nt", "Windows atomic replacement sharing")
    def test_repeated_atomic_promotions_keep_exact_unicode_path_and_content(self):
        path = self.root / "record-\u6f22.json"
        before = set(self.root.iterdir())
        for generation in range(100):
            manager._write(self.root, path, {"generation": generation})
            self.assertEqual({"generation": generation}, manager._read(path))
        self.assertEqual(before | {path}, set(self.root.iterdir()))

    @unittest.skipUnless(os.name == "nt", "Windows atomic replacement sharing")
    def test_json_reader_allows_atomic_manager_replace_and_keeps_old_snapshot(self):
        contracts = importlib.import_module("artifact_contracts")
        path = self.root / ".git" / "sdlc" / "execution-controls.json"
        manager._write(self.root, path, {"generation": 1})
        with contracts._open_json_text(path) as reader:
            manager._write(self.root, path, {"generation": 2})
            self.assertEqual({"generation": 1}, json.load(reader))
        self.assertEqual({"generation": 2}, manager._read(path))
        with path.open(encoding="utf-8") as reader:
            with self.assertRaises(ContractIssue) as caught:
                manager._write(self.root, path, {"generation": 3})
            self.assertEqual("E_EXECUTION_WRITE", caught.exception.code)
            self.assertEqual({"generation": 2}, json.load(reader))
        self.assertEqual({"generation": 2}, manager._read(path))
        self.assertEqual([], list(path.parent.glob("execution-*.tmp")))
        with self.assertRaises(OSError):
            with contracts._open_json_text(path.parent):
                self.fail("a directory must not become a JSON input")

    @unittest.skipUnless(os.name == "nt", "Windows extended resolved-path spelling")
    def test_resolved_windows_prefix_preserves_confinement_without_retry(self):
        metrics = importlib.import_module("manage_metrics")
        root = self.root.resolve(strict=True)
        candidate = root / ".git" / "sdlc" / "executions.lock"
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(b"")
        extended = Path("\\\\?\\" + str(candidate))
        self.assertTrue(candidate.samefile(extended))
        self.assertEqual(candidate, metrics._resolved_spelling(extended.resolve(strict=True)))
        self.assertEqual(candidate.relative_to(root),
                         metrics._resolved_spelling(extended).relative_to(metrics._resolved_spelling(root)))
        outside = Path("\\\\?\\" + str(root.parent / "outside" / "executions.lock"))
        with self.assertRaises(ValueError):
            metrics._resolved_spelling(outside).relative_to(metrics._resolved_spelling(root))
        unc = Path(r"\\?\UNC\server\share\project\executions.lock")
        self.assertEqual(Path(r"\\server\share\project\executions.lock"), metrics._resolved_spelling(unc))
        device = Path(r"\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy1\outside")
        self.assertEqual(device, metrics._resolved_spelling(device))

    def test_posix_execute_is_rejected_before_spawn_or_writes(self):
        process = importlib.import_module("runtime_process")
        self.brief["allowedActions"].append("execute")
        existing = None
        if os.name == "nt":
            existing = self.api.prepare_execute(self.root, "feature-one", self.brief,
                                                "developer", MODEL, LIMITS, [self.command("pass")])
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with mock.patch.object(process, "PLATFORM", "posix", create=True):
            self.issue(lambda: self.api.prepare_execute(
                self.root, "feature-one", self.brief, "developer", MODEL, LIMITS,
                [self.command("pass")]), "E_RUNTIME_UNSUPPORTED")
            if existing is not None:
                self.issue(lambda: self.start(existing), "E_RUNTIME_UNSUPPORTED")
            self.issue(lambda: self.api.tool(self.root, {"schemaVersion": 2}, "execute",
                                             {"commandId": "check"}), "E_RUNTIME_UNSUPPORTED")
            with self.assertRaisesRegex(OSError, "owner-death process containment unavailable"):
                process.run(self.command("pass"), lambda: self.fail("unsupported execute cannot reach its guard"))
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def activate_supervised(self):
        controls.configure_controls(self.root, {
            "schemaVersion": 2, "enabled": True, "mode": "supervised",
            "maxAttempts": 1, "allowEscalation": False, "permittedModels": [MODEL["id"]],
        })
        current = manager.inspect_execution(self.root, "feature-one")
        controls.approve_controls(self.root, "feature-one", current["planDigest"],
                                 current["policyDigest"], controls.inspect_controls(self.root)["controlsDigest"])

    def execute_start(self, command):
        self.brief["allowedActions"].append("execute")
        envelope = self.api.prepare_execute(self.root, "feature-one", self.brief,
                                            "developer", MODEL, LIMITS, [command])
        self.start(envelope)

    def test_supervised_requires_separate_controls_approval_and_rechecks_pause(self):
        self.activate_supervised()
        self.start()
        self.assertEqual("before\n", self.tool("read", {"path": "src/feature.py"})["content"])
        controls.set_pause(self.root, True, "operator pause")
        self.issue(lambda: self.tool("read", {"path": "src/feature.py"}))

    @unittest.skipUnless(os.name == "nt", "execute requires Windows owner-death Job containment")
    def test_execute_exact_id_nonzero_and_no_raw_persistence(self):
        self.execute_start(self.command("print('private-output'); raise SystemExit(7)"))
        output = self.tool("execute", {"commandId": "check"})
        self.assertEqual("nonzero", output["evidence"]["status"])
        self.assertEqual(7, output["evidence"]["exitCode"])
        self.assertIn("private-output", output["output"])
        self.assertNotIn("private-output", str(self.api.inspect(self.root)))
        self.issue(lambda: self.tool("execute", {"commandId": "check", "argv": ["bad"]}))
        self.issue(lambda: self.tool("execute", {"commandId": "check"}), "E_RUNTIME_UNRESOLVED")

    @unittest.skipUnless(os.name == "nt", "execute requires Windows owner-death Job containment")
    def test_timeout_kills_real_descendant_heartbeat(self):
        heartbeat = self.root / "beat"
        child = ("import pathlib,time; p=pathlib.Path(" + repr(str(heartbeat)) +
                 ");\nwhile True: p.write_text(str(time.time_ns())); time.sleep(.02)")
        code = ("import subprocess,sys,time; subprocess.Popen([sys.executable,'-I','-S','-c'," +
                repr(child) + "]); time.sleep(30)")
        self.execute_start(self.command(code, timeoutMs=700))
        output = self.tool("execute", {"commandId": "check"})
        self.assertEqual("timeout", output["evidence"]["status"])
        self.assertEqual("unknown", self.api.inspect(self.root)["status"])
        self.assertTrue(heartbeat.exists(), "real descendant must run before containment proof")
        before = heartbeat.read_bytes()
        time.sleep(.2)
        self.assertEqual(before, heartbeat.read_bytes())

    @unittest.skipUnless(os.name == "nt", "execute requires Windows owner-death Job containment")
    def test_output_flood_is_bounded_and_stopped(self):
        self.execute_start(self.command("import os\nwhile True: os.write(1,b'x'*4096)"))
        output = self.tool("execute", {"commandId": "check"})
        self.assertEqual("output-limit", output["evidence"]["status"])
        self.assertLessEqual(len(output["output"].encode()), 2048)

    def test_legacy_envelope_cannot_gain_execute(self):
        envelope = self.prepare()
        envelope["commands"] = [self.command("pass")]
        self.issue(lambda: self.start(envelope))

    @unittest.skipUnless(os.name == "nt", "execute requires Windows owner-death Job containment")
    def test_receipt_requires_unique_exact_observed_provenance(self):
        self.execute_start(self.command("print('private-output')"))
        output = self.tool("execute", {"commandId": "check"})
        declared = result(self.plan)
        self.issue(lambda: self.api.receive(self.root, self.envelope, declared))
        verification = declared["verification"][0]
        verification.update(command="runtime-command:check",
                            revision=output["evidence"]["commandDigest"], summary="passed")
        declared["findings"] = ["private-output"]
        self.issue(lambda: self.api.receive(self.root, self.envelope, declared), "E_RUNTIME_PROTOCOL")
        declared["findings"] = []
        self.api.receive(self.root, self.envelope, declared)
        self.assertEqual("reported", self.api.inspect(self.root)["status"])
        stored = manager.inspect_execution(self.root, "feature-one")
        self.assertEqual({}, stored["acceptances"])
        self.assertNotIn("private-output", json.dumps(stored))

    @unittest.skipUnless(os.name == "nt", "execute requires Windows owner-death Job containment")
    def test_command_definition_and_runtime_approval_are_exact(self):
        self.brief["allowedActions"].append("execute")
        for definition in (self.command("pass", cwd=str(self.root.parent)),
                           self.command("pass", executable="python"),
                           self.command("pass", executable=str(Path(sys.executable).with_name("cmd.exe"))),
                           self.command("pass", argv="echo nope"),
                           self.command("pass", timeoutMs=10001)):
            self.issue(lambda: self.api.prepare_execute(self.root, "feature-one", self.brief,
                                                       "developer", MODEL, LIMITS, [definition]))
        envelope = self.api.prepare_execute(self.root, "feature-one", self.brief,
                                           "developer", MODEL, LIMITS, [self.command("pass")])
        approved = state.digest(envelope)
        envelope["commands"][0]["argv"].append("changed")
        self.issue(lambda: self.api.start(self.root, envelope, approved,
                                         state.digest(envelope["request"])), "E_RUNTIME_APPROVAL")

    def test_new_controls_version_explicit_selection_retains_legacy_and_blocks_downgrade(self):
        controls.configure_controls(self.root, controls_policy())
        current = manager.inspect_execution(self.root, "feature-one")
        controls.approve_controls(self.root, "feature-one", current["planDigest"],
                                 current["policyDigest"], controls.inspect_controls(self.root)["controlsDigest"])
        retained = controls.inspect_controls(self.root)["store"]
        self.assertTrue(retained["approvals"])
        self.activate_supervised()
        store = controls.inspect_controls(self.root)["store"]
        self.assertEqual(retained, store["retainedManual"])
        # Execute the actual pre-change reader in memory, not a reconstruction.
        original = subprocess.run(["git", "show",
            "f99e09c1b254592d28b9b08172c416d067ce5652:skills/sdlc/scripts/execution_controls.py"],
            cwd=SCRIPTS.parents[2], capture_output=True, text=True, check=True).stdout
        legacy = {"__name__": "legacy_controls"}
        exec(compile(original, "<baseline-controls>", "exec"), legacy)
        self.issue(lambda: legacy["_store"](store), "E_SCHEMA_UNKNOWN")
        self.issue(lambda: legacy["validate_controls_policy"](store["policy"]), "E_EXECUTION_VERSION")
        self.issue(lambda: controls.configure_controls(self.root, controls_policy(False)),
                   "E_CONTROLS_CAPABILITY")
        self.assertEqual(store, controls.inspect_controls(self.root)["store"])

    def test_supervised_missing_reapproval_and_old_native_dispatch_fail_closed(self):
        self.activate_supervised()
        request = self.prepare()["request"]
        native = importlib.import_module("native_execution")
        self.issue(lambda: native.start_request(self.root, request, state.digest(request)),
                   "E_CONTROLS_CAPABILITY")
        selected = controls.inspect_controls(self.root)["store"]["policy"]
        controls.configure_controls(self.root, selected)
        self.issue(self.prepare, "E_RUNTIME_APPROVAL")
        self.activate_supervised()
        self.start()
        self.api.stop(self.root, self.envelope)
        self.issue(lambda: self.start())
        self.issue(lambda: manager.delete_execution(self.root, "feature-one"))

    def test_supervised_attempt_budget_survives_new_plan_revision(self):
        self.activate_supervised()
        manager.record_task(self.root, "feature-one", "implement", "ready")
        manager.record_task(self.root, "feature-one", "implement", "start", "attempt-one")
        manager.record_task(self.root, "feature-one", "implement", "fail", "attempt-one",
                            reason="controller recorded failed manual attempt")
        newer = copy.deepcopy(self.plan)
        newer["revision"] += 1
        manager.import_plan(self.root, newer)
        current = manager.inspect_execution(self.root, "feature-one")
        manager.approve_plan(self.root, "feature-one", current["planDigest"], current["policyDigest"])
        self.activate_supervised()
        self.brief["binding"]["planRevision"] = newer["revision"]
        self.brief["binding"]["planDigest"] = state.digest(newer)
        self.brief["attemptId"] = "attempt-two"
        self.issue(self.start, "E_CONTROLS_ATTEMPTS")

    @unittest.skipUnless(os.name == "nt", "execute requires Windows owner-death Job containment")
    def test_execute_cli_is_real_and_default_disabled_does_not_write(self):
        self.brief["allowedActions"].append("execute")
        payload = {"executionId": "feature-one", "brief": self.brief, "role": "developer",
                   "model": MODEL, "limits": LIMITS, "commands": [self.command("print('ok')")]}
        cli = [sys.executable, "-I", "-S", str(SCRIPTS / "manage_runtime.py"),
               "prepare_execute", "--project-root", str(self.root)]
        prepared = subprocess.run(cli, input=json.dumps(payload), capture_output=True, text=True)
        self.assertEqual(0, prepared.returncode, prepared.stderr)
        self.assertEqual(2, json.loads(prepared.stdout)["schemaVersion"])
        manager.configure_policy(self.root, bounded_tests.policy(False))
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        rejected = subprocess.run(cli, input=json.dumps(payload), capture_output=True, text=True)
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn("E_EXECUTION_DISABLED", rejected.stderr)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_exact_bundle_inventory_installs_new_helpers_and_contracts(self):
        from tests.test_qualification import qualify, ROOT
        manifest = qualify.validate_manifest(
            qualify.load_json_strict(ROOT / "qualification" / "manifest.json"), ROOT)
        for mode in ("copy", "link"):
            target = self.root / mode / "skills" / "sdlc"
            qualify.install_suite(ROOT, manifest, target, mode)
            inspected = qualify.inspect_install(manifest, target, "generic-agent-skills", "project", mode)
            self.assertEqual("pass", inspected["installation"]["status"])
            for relative in (
                "scripts/runtime_process.py", "scripts/bounded_runtime.py",
                "contracts/execution-controls-policy-v2.schema.json",
                "contracts/execution-controls-record-v2.schema.json", "contracts/runtime-command.schema.json",
                "contracts/execution-batch.schema.json",
                "contracts/execution-controls-policy-v3.schema.json",
                "contracts/execution-controls-record-v3.schema.json",
                "contracts/execution-event-v2.schema.json",
                "contracts/execution-record-v2.schema.json",
                "scripts/execution_orchestration.py",
            ):
                self.assertEqual((ROOT / "skills" / "sdlc" / relative).read_bytes(),
                                 (target / relative).read_bytes())

    def _interrupt_real_command(self, cancellation):
        self.activate_supervised()
        heartbeat = self.root / "beat"
        child = ("import pathlib,time; p=pathlib.Path(" + repr(str(heartbeat)) +
                 ");\nwhile True: p.write_text(str(time.time_ns())); time.sleep(.02)")
        code = ("import subprocess,sys,time; subprocess.Popen([sys.executable,'-I','-S','-c'," +
                repr(child) + "]); time.sleep(30)")
        self.execute_start(self.command(code, timeoutMs=5000))
        errors = []
        def execute():
            try:
                self.tool("execute", {"commandId": "check"})
            except BaseException as error:
                errors.append(error)
        worker = threading.Thread(target=execute)
        worker.start()
        try:
            deadline = time.monotonic() + 4
            while not heartbeat.exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(heartbeat.exists())
            for attempt in range(100):
                try:
                    if cancellation:
                        controls.request_cancel(self.root, "feature-one", "implement", "explicit cancellation")
                    else:
                        controls.set_pause(self.root, True, "explicit stop while process runs")
                    break
                except ContractIssue as error:
                    if error.code != "E_EXECUTION_BUSY" or attempt == 99:
                        raise
                    time.sleep(.01)
        finally:
            worker.join(8)
        self.assertFalse(worker.is_alive())
        self.assertTrue(errors)
        before = heartbeat.read_bytes()
        time.sleep(.2)
        self.assertEqual(before, heartbeat.read_bytes())
        self.assertEqual("unknown", self.api.inspect(self.root)["status"],
                         [(type(error).__name__, str(error), repr(error.__cause__),
                           repr(getattr(error.__cause__, "__cause__", None))) for error in errors])
        self.assertEqual({}, manager.inspect_execution(self.root, "feature-one")["receipts"])

    @unittest.skipUnless(os.name == "nt", "execute requires Windows owner-death Job containment")
    def test_pause_during_real_command_kills_descendant_and_retains_unknown(self):
        self._interrupt_real_command(False)

    @unittest.skipUnless(os.name == "nt", "execute requires Windows owner-death Job containment")
    def test_cancel_during_real_command_kills_descendant_without_remote_stop_claim(self):
        self._interrupt_real_command(True)
        store = controls.inspect_controls(self.root)
        self.assertEqual("pending", store["cancelRequests"][0]["status"])
        self.assertFalse(store["runtimeCapabilities"]["hostCancellation"])

    @unittest.skipUnless(os.name == "nt", "execute requires Windows owner-death Job containment")
    def test_real_spawn_failure_starts_no_instruction(self):
        process = importlib.import_module("runtime_process")
        marker = self.root / "not-started"
        command = self.command("from pathlib import Path; Path(" + repr(str(marker)) + ").touch()",
                               cwd=str(self.root / "missing"))
        observation = process.run(command, lambda: None)
        self.assertEqual("spawn-failed", observation["evidence"]["status"])
        self.assertFalse(marker.exists())

    @unittest.skipUnless(os.name == "nt", "Windows-only suspended-job fault injection")
    def test_windows_assignment_failure_never_resumes_real_suspended_process(self):
        process = importlib.import_module("runtime_process")
        marker = self.root / "not-started"
        original = ctypes.WinDLL
        resumes = []
        class InjectedFunction:
            def __init__(self, callback):
                self.callback = callback
            def __call__(self, *args):
                return self.callback(*args)
        def library(*args, **kwargs):
            api = original(*args, **kwargs)
            def denied(*unused):
                ctypes.set_last_error(5)
                return False
            api.AssignProcessToJobObject = InjectedFunction(denied)
            api.ResumeThread = InjectedFunction(lambda *unused: resumes.append(True))
            return api
        with mock.patch.object(ctypes, "WinDLL", library):
            with self.assertRaises(OSError):
                process.run(self.command("from pathlib import Path; Path(" +
                                         repr(str(marker)) + ").touch()"), lambda: None)
        self.assertEqual([], resumes)
        self.assertFalse(marker.exists(), "real suspended process must execute no user instruction")


if __name__ == "__main__":
    unittest.main()
