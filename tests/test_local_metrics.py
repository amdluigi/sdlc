import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "sdlc" / "scripts" / "manage_metrics.py"
MAX_COUNTER = (1 << 63) - 1


class LocalMetricsTests(unittest.TestCase):
    def setUp(self):
        self.project = (
            ROOT / ".test-tmp" / "metrics" / self.id().split(".")[-1]
        )
        shutil.rmtree(self.project, ignore_errors=True)
        (self.project / ".git").mkdir(parents=True)
        self.write_config(False)

    def tearDown(self):
        shutil.rmtree(self.project, ignore_errors=True)

    def write_config(self, enabled):
        path = self.project / ".sdlc" / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schemaVersion": 2,
                    "modules": {},
                    "extensions": {"project": {}, "global": {}},
                    "measurement": {"enabled": enabled},
                }
            ),
            encoding="utf-8",
        )

    @property
    def store(self):
        return self.project / ".git" / "sdlc" / "metrics.json"

    def run_cli(self, *arguments):
        return subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPT),
                *arguments,
                "--project-root",
                str(self.project),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

    def load_module(self):
        self.assertTrue(SCRIPT.is_file(), "manage_metrics.py is missing")
        spec = importlib.util.spec_from_file_location("manage_metrics", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        previous_bytecode_policy = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path.remove(str(SCRIPT.parent))
            sys.dont_write_bytecode = previous_bytecode_policy
        return module

    def test_disabled_record_is_machine_readable_and_creates_nothing(self):
        result = self.run_cli("record", "--event", "module.enabled")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("disabled", json.loads(result.stdout)["status"])
        self.assertFalse(self.store.exists())

    def test_status_is_read_only_and_reports_absent_store(self):
        before = sorted(str(path) for path in self.project.rglob("*"))
        result = self.run_cli("status")
        self.assertEqual(0, result.returncode, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(
            (False, "git-local", False, None),
            (
                value["enabled"],
                value["storeCategory"],
                value["dataExists"],
                value["generation"],
            ),
        )
        self.assertEqual(before, sorted(str(path) for path in self.project.rglob("*")))

    def test_enabled_counter_events_use_closed_aggregate_schema(self):
        self.write_config(True)
        events = (
            "module.enabled",
            "module.triggered",
            "module.loaded",
            "module.reused",
            "module.disabled",
            "evidence.reused",
            "evidence.refreshed",
            "clarification.asked",
            "clarification.avoidedByEvidence",
            "extension.observed",
            "extension.accepted",
            "extension.rejected",
            "extension.promoted",
            "extension.superseded",
            "report.concise",
            "report.normal",
            "report.detailed",
        )
        for event in events:
            result = self.run_cli("record", "--event", event)
            self.assertEqual(0, result.returncode, (event, result.stderr))
        value = json.loads(self.store.read_text(encoding="utf-8"))
        self.assertEqual(1, value["schemaVersion"])
        self.assertEqual(1, value["generation"])
        self.assertEqual(set(events), set(value["counters"]))
        self.assertTrue(all(value["counters"][event] == 1 for event in events))
        serialized = json.dumps(value).lower()
        for forbidden in (
            "prompt",
            "response",
            "repository",
            "username",
            "model",
            "timestamp",
            "path",
            "command",
            "task",
            "credential",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_duration_boundaries_are_bounded_and_optional(self):
        self.write_config(True)
        for duration in (0, 1000, 1001, 10_000, 60_000, 600_000, 3_600_000, 86_400_000, 86_400_001):
            result = self.run_cli(
                "record",
                "--event",
                "phase.configuration",
                "--duration-ms",
                str(duration),
            )
            self.assertEqual(0, result.returncode, result.stderr)
        value = json.loads(self.store.read_text(encoding="utf-8"))
        self.assertEqual(
            {"count": 9, "bucketsMs": [2, 2, 1, 1, 1, 2]},
            value["phaseDurations"]["configuration"],
        )
        self.assertNotIn("durationMs", json.dumps(value))

    def test_invalid_event_and_duration_shapes_do_not_write(self):
        self.write_config(True)
        for arguments in (
            ("record", "--event", "module.custom"),
            ("record", "--event", "module.enabled", "--duration-ms", "1"),
            ("record", "--event", "phase.handoff"),
            ("record", "--event", "phase.handoff", "--duration-ms", "-1"),
        ):
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments)
                self.assertNotEqual(0, result.returncode)
        self.assertFalse(self.store.exists())

    def test_disable_stops_writes_but_inspect_remains_available(self):
        self.write_config(True)
        self.assertEqual(
            0, self.run_cli("record", "--event", "module.loaded").returncode
        )
        before = self.store.read_bytes()
        self.write_config(False)
        result = self.run_cli("record", "--event", "module.loaded")
        self.assertEqual("disabled", json.loads(result.stdout)["status"])
        self.assertEqual(before, self.store.read_bytes())
        inspected = self.run_cli("inspect", "--json")
        self.assertEqual(0, inspected.returncode, inspected.stderr)
        self.assertEqual(1, json.loads(inspected.stdout)["counters"]["module.loaded"])

    def test_concurrent_disable_after_lock_returns_disabled_without_store(self):
        module = self.load_module()
        self.write_config(True)

        @contextmanager
        def disable_before_lock_yields(_path):
            self.write_config(False)
            yield

        with mock.patch.object(
            module, "_store_lock", disable_before_lock_yields
        ):
            value = module.record_event(
                self.project, "module.loaded", None
            )

        self.assertEqual({"status": "disabled", "written": False}, value)
        self.assertFalse(self.store.exists())

    def test_supported_disable_at_pre_replace_boundary_is_linearized(self):
        module = self.load_module()
        self.write_config(True)
        original_write = module._write_atomic
        replace_finished = threading.Event()
        disable_attempted = threading.Event()
        disable_finished = threading.Event()
        disable_observed_replace = []
        configure = getattr(module, "configure_measurement", None)

        def disable():
            disable_attempted.set()
            if configure is None:
                self.write_config(False)
            else:
                configure(self.project, False)
            disable_observed_replace.append(replace_finished.is_set())
            disable_finished.set()

        def disable_at_boundary(path, value):
            thread = threading.Thread(target=disable)
            thread.start()
            self.assertTrue(disable_attempted.wait(1))
            if configure is None:
                self.assertTrue(disable_finished.wait(1))
            original_write(path, value)
            replace_finished.set()
            return thread

        threads = []

        def capture_thread(path, value):
            threads.append(disable_at_boundary(path, value))

        with mock.patch.object(module, "_write_atomic", capture_thread):
            module.record_event(self.project, "module.loaded", None)
        for thread in threads:
            thread.join(2)
            self.assertFalse(thread.is_alive())

        self.assertEqual([True], disable_observed_replace)
        before = self.store.read_bytes()
        self.assertEqual(
            {"status": "disabled", "written": False},
            module.record_event(self.project, "module.loaded", None),
        )
        self.assertEqual(before, self.store.read_bytes())

    def test_supported_configure_preserves_config_and_controls_consent(self):
        module = self.load_module()
        config_path = self.project / ".sdlc" / "config.json"
        original = json.loads(config_path.read_text(encoding="utf-8"))
        original["extensions"]["project"]["local-check"] = False
        config_path.write_text(json.dumps(original), encoding="utf-8")

        disabled = module.configure_measurement(self.project, False)
        self.assertEqual({"enabled": False, "changed": False}, disabled)
        configured = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(
            {"local-check": False}, configured["extensions"]["project"]
        )
        self.assertFalse(configured["measurement"]["enabled"])

        enabled_result = self.run_cli(
            "configure", "--enabled", "true"
        )
        self.assertEqual(0, enabled_result.returncode, enabled_result.stderr)
        self.assertEqual(
            {"enabled": True, "changed": True},
            json.loads(enabled_result.stdout),
        )
        self.assertEqual(
            1,
            module.record_event(
                self.project, "module.loaded", None
            )["counters"]["module.loaded"],
        )
        disabled = module.configure_measurement(self.project, False)
        self.assertEqual({"enabled": False, "changed": True}, disabled)
        before = self.store.read_bytes()
        self.assertEqual(
            {"status": "disabled", "written": False},
            module.record_event(self.project, "module.loaded", None),
        )
        self.assertEqual(before, self.store.read_bytes())

    def test_inspect_absent_is_honestly_unavailable(self):
        result = self.run_cli("inspect", "--json")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("unavailable", json.loads(result.stdout)["status"])

    def test_reset_delete_and_delete_then_recreate_have_distinct_semantics(self):
        self.write_config(True)
        self.run_cli("record", "--event", "evidence.reused")
        reset = self.run_cli("reset")
        self.assertEqual(0, reset.returncode, reset.stderr)
        value = json.loads(self.store.read_text(encoding="utf-8"))
        self.assertEqual(2, value["generation"])
        self.assertEqual(0, value["counters"]["evidence.reused"])
        deleted = self.run_cli("delete")
        self.assertEqual(0, deleted.returncode, deleted.stderr)
        self.assertFalse(self.store.exists())
        self.assertEqual("absent", json.loads(self.run_cli("delete").stdout)["status"])
        self.run_cli("record", "--event", "evidence.refreshed")
        self.assertEqual(
            1,
            json.loads(self.store.read_text(encoding="utf-8"))["counters"][
                "evidence.refreshed"
            ],
        )

    def test_reset_requires_valid_existing_store(self):
        self.write_config(True)
        self.assertNotEqual(0, self.run_cli("reset").returncode)
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.store.write_text("{", encoding="utf-8")
        result = self.run_cli("reset")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("corrupt", result.stderr.lower())

    def test_corrupt_oversized_and_unknown_store_data_block_writes(self):
        self.write_config(True)
        self.store.parent.mkdir(parents=True)
        bad_values = (
            "{",
            "x" * 70_000,
            json.dumps(
                {
                    "schemaVersion": 1,
                    "generation": 1,
                    "counters": {"module.enabled": 0, "label": "secret"},
                    "phaseDurations": {},
                }
            ),
        )
        for text in bad_values:
            with self.subTest(length=len(text)):
                self.store.write_text(text, encoding="utf-8")
                result = self.run_cli("record", "--event", "module.enabled")
                self.assertNotEqual(0, result.returncode)

    def test_counters_saturate_instead_of_wrapping(self):
        module = self.load_module()
        value = module.zero_store()
        value["counters"]["module.enabled"] = MAX_COUNTER
        self.write_config(True)
        self.store.parent.mkdir(parents=True)
        self.store.write_text(json.dumps(value), encoding="utf-8")
        result = self.run_cli("record", "--event", "module.enabled")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            MAX_COUNTER,
            json.loads(self.store.read_text(encoding="utf-8"))["counters"][
                "module.enabled"
            ],
        )

    def test_duration_count_saturation_keeps_histogram_consistent(self):
        module = self.load_module()
        value = module.zero_store()
        observation = value["phaseDurations"]["handoff"]
        observation["count"] = MAX_COUNTER
        observation["bucketsMs"][0] = MAX_COUNTER - 1
        observation["bucketsMs"][-1] = 1
        self.write_config(True)
        self.store.parent.mkdir(parents=True)
        self.store.write_text(json.dumps(value), encoding="utf-8")

        try:
            result = module.record_event(
                self.project, "phase.handoff", 0
            )
        except module.MetricsError as error:
            self.fail(f"saturated histogram must remain valid: {error}")

        self.assertEqual(MAX_COUNTER, result["phaseDurations"]["handoff"]["count"])
        self.assertEqual(
            MAX_COUNTER - 1,
            result["phaseDurations"]["handoff"]["bucketsMs"][0],
        )

    def test_non_git_store_requires_explicit_local_exclusion(self):
        enclosing = self.project.parent / f"{self.project.name}-safe-repository"
        shutil.rmtree(enclosing, ignore_errors=True)
        enclosing.mkdir()
        self.addCleanup(shutil.rmtree, enclosing, True)
        initialized = subprocess.run(
            ["git", "init", "--quiet", str(enclosing)],
            text=True,
            capture_output=True,
        )
        if initialized.returncode != 0:
            self.skipTest("git unavailable")
        self.project = enclosing / "child"
        self.project.mkdir()
        self.write_config(True)
        refused = self.run_cli("record", "--event", "module.enabled")
        self.assertNotEqual(0, refused.returncode)
        self.assertIn("local-store-not-ignored", refused.stderr)
        (self.project / ".gitignore").write_text(".sdlc/local/\n", encoding="utf-8")
        accepted = self.run_cli("record", "--event", "module.enabled")
        self.assertEqual(0, accepted.returncode, accepted.stderr)
        self.assertTrue((self.project / ".sdlc" / "local" / "metrics.json").is_file())

    def test_non_git_exclusion_honors_order_and_negation(self):
        enclosing = self.project.parent / f"{self.project.name}-ignore-repository"
        shutil.rmtree(enclosing, ignore_errors=True)
        enclosing.mkdir()
        self.addCleanup(shutil.rmtree, enclosing, True)
        initialized = subprocess.run(
            ["git", "init", "--quiet", str(enclosing)],
            text=True,
            capture_output=True,
        )
        if initialized.returncode != 0:
            self.skipTest("git unavailable")
        self.project = enclosing / "child"
        self.project.mkdir()
        self.write_config(True)
        ignore = self.project / ".gitignore"
        ignore.write_text(
            ".sdlc/local/\n!.sdlc/local/\n!.sdlc/local/metrics.json\n",
            encoding="utf-8",
        )
        refused = self.run_cli("record", "--event", "module.enabled")
        self.assertNotEqual(0, refused.returncode)
        self.assertFalse(
            (self.project / ".sdlc" / "local" / "metrics.json").exists()
        )

        ignore.write_text(
            "!.sdlc/local/\n!.sdlc/local/metrics.json\n.sdlc/local/\n",
            encoding="utf-8",
        )
        accepted = self.run_cli("record", "--event", "module.enabled")
        self.assertEqual(0, accepted.returncode, accepted.stderr)

    def test_nested_project_honors_enclosing_worktree_ignore_rules(self):
        module = self.load_module()
        enclosing = self.project.parent / f"{self.project.name}-enclosing"
        shutil.rmtree(enclosing, ignore_errors=True)
        enclosing.mkdir()
        self.addCleanup(shutil.rmtree, enclosing, True)
        initialized = subprocess.run(
            ["git", "init", "--quiet", str(enclosing)],
            text=True,
            capture_output=True,
        )
        if initialized.returncode != 0:
            self.skipTest("git unavailable")
        child = enclosing / "child"
        child.mkdir()
        self.project = child
        self.write_config(True)
        (enclosing / ".gitignore").write_text(
            "/child/.sdlc/local/\n", encoding="utf-8"
        )

        value = module.record_event(child, "module.enabled", None)

        self.assertEqual(1, value["counters"]["module.enabled"])
        self.assertTrue(
            (child / ".sdlc" / "local" / "metrics.json").is_file()
        )

    def test_git_worktree_gitfile_uses_confined_ignored_local_store(self):
        module = self.load_module()
        shutil.rmtree(self.project, ignore_errors=True)
        self.project.mkdir()
        admin = self.project.parent / f"{self.project.name}-git-admin"
        shutil.rmtree(admin, ignore_errors=True)
        self.addCleanup(shutil.rmtree, admin, True)
        initialized = subprocess.run(
            [
                "git",
                "init",
                "--quiet",
                "--separate-git-dir",
                str(admin),
                str(self.project),
            ],
            text=True,
            capture_output=True,
        )
        if initialized.returncode != 0:
            self.skipTest("gitfile fixtures unavailable")
        self.write_config(True)
        (self.project / ".gitignore").write_text(
            ".sdlc/local/\n", encoding="utf-8"
        )

        value = module.record_event(self.project, "module.enabled", None)

        self.assertEqual(1, value["counters"]["module.enabled"])
        self.assertTrue((self.project / ".git").is_file())
        self.assertTrue(
            (self.project / ".sdlc" / "local" / "metrics.json").is_file()
        )

    def test_store_link_is_rejected(self):
        self.write_config(True)
        outside = self.project.parent / f"{self.project.name}-outside"
        shutil.rmtree(outside, ignore_errors=True)
        outside.mkdir()
        self.addCleanup(shutil.rmtree, outside, True)
        try:
            (self.project / ".git" / "sdlc").symlink_to(
                outside, target_is_directory=True
            )
        except OSError:
            result = subprocess.run(
                [
                    "cmd.exe",
                    "/d",
                    "/c",
                    "mklink",
                    "/J",
                    str(self.project / ".git" / "sdlc"),
                    str(outside),
                ],
                text=True,
                capture_output=True,
            )
            if result.returncode != 0:
                self.skipTest("directory links unavailable")
        result = self.run_cli("record", "--event", "module.enabled")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("link", result.stderr.lower())

    def test_atomic_replace_failure_preserves_previous_store(self):
        module = self.load_module()
        self.write_config(True)
        module.record_event(self.project, "module.enabled", None)
        before = self.store.read_bytes()
        with mock.patch.object(Path, "replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                module.record_event(self.project, "module.enabled", None)
        self.assertEqual(before, self.store.read_bytes())
        self.assertEqual([], list(self.store.parent.glob("*.tmp")))

    def test_lock_contention_is_bounded_and_preserves_store(self):
        module = self.load_module()
        self.write_config(True)
        module.record_event(self.project, "module.enabled", None)
        lock = self.store.with_suffix(".lock")
        lock.write_text("", encoding="utf-8")
        with mock.patch.object(module, "LOCK_TIMEOUT_SECONDS", 0):
            with self.assertRaises(module.MetricsError):
                module.record_event(self.project, "module.enabled", None)
        self.assertEqual(
            1,
            json.loads(self.store.read_text(encoding="utf-8"))["counters"][
                "module.enabled"
            ],
        )

    def test_monotonic_timing_failure_cannot_change_lifecycle_result(self):
        module = self.load_module()
        self.write_config(True)
        with mock.patch.object(module.time, "monotonic", side_effect=OSError("clock")):
            result = module.record_optional_phase(
                self.project, "verification", lambda: "lifecycle-result"
            )
        self.assertEqual("lifecycle-result", result)
        self.assertFalse(self.store.exists())

    def test_helper_has_no_network_or_upload_imports(self):
        source = SCRIPT.read_text(encoding="utf-8").lower()
        for token in (
            "import socket",
            "import urllib",
            "http.client",
            "import requests",
            "telemetry",
            "analytics",
            "upload",
            "export",
        ):
            self.assertNotIn(token, source)

    def test_corrupt_store_diagnostics_are_stable_and_path_neutral(self):
        self.write_config(True)
        self.store.parent.mkdir(parents=True)
        self.store.write_text("{", encoding="utf-8")

        result = self.run_cli("inspect", "--json")

        self.assertNotEqual(0, result.returncode)
        reason = json.loads(result.stdout)["reason"]
        self.assertEqual("store-corrupt:invalid-json", reason)
        self.assertIn("store-corrupt:invalid-json", result.stderr)
        self.assertNotIn(str(self.project), result.stdout + result.stderr)

        invalid_value = self.load_module().zero_store()
        invalid_value["counters"]["module.enabled"] = -1
        self.store.write_text(json.dumps(invalid_value), encoding="utf-8")
        result = self.run_cli("inspect", "--json")
        self.assertEqual(
            "store-corrupt:invalid-value",
            json.loads(result.stdout)["reason"],
        )
        self.assertNotIn(str(self.project), result.stdout + result.stderr)

    def test_recording_never_calls_network_entry_points(self):
        module = self.load_module()
        self.write_config(True)
        with mock.patch.object(socket, "socket") as network_socket:
            value = module.record_event(self.project, "module.reused", None)
        network_socket.assert_not_called()
        self.assertEqual(1, value["counters"]["module.reused"])


if __name__ == "__main__":
    unittest.main()
