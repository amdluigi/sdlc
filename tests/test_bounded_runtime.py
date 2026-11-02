import hashlib
import importlib
import json
import shutil
import subprocess
import sys
import os
import time
import tempfile
import unittest
from pathlib import Path

from tests.test_execution_contracts import SCRIPTS, plan, brief, result
from tests.test_execution_management import policy
from artifact_contracts import ContractIssue
import execution_manager as manager
import execution_profiles as profiles
import execution_state as state
import execution_controls as controls


LIMITS = {"maxIterations": 4, "maxToolCalls": 4, "maxInputBytes": 32768,
          "maxOutputBytes": 32768, "maxWallMs": 30000}
MODEL = {"id": "synthetic-model", "vendor": "synthetic", "family": "test", "version": "1"}


def fixture(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "src").mkdir()
    (root / "src" / "feature.py").write_text("before\n", encoding="utf-8", newline="\n")
    (root / "guide.md").write_text("bounded guidance\n", encoding="utf-8", newline="\n")
    source = root / "docs" / "plans" / "feature.md"
    source.parent.mkdir(parents=True)
    source.write_text("Approved fixture source\n", encoding="utf-8")
    value = plan()
    value["sourcePlan"]["digest"] = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    supplied = brief(value)
    supplied["guidance"] = ["guide.md"]
    supplied["allowedActions"] = ["read", "search", "edit"]
    profiles.install_profiles(root, dry_run=False)
    manager.configure_policy(root, policy())
    manager.import_plan(root, value)
    current = manager.inspect_execution(root, value["executionId"])
    manager.approve_plan(root, value["executionId"], current["planDigest"], current["policyDigest"])
    return value, supplied


def remove_fixture(root):
    for attempt in range(10):
        try:
            if root.exists():
                shutil.rmtree(root)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.5)


class BoundedRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((SCRIPTS / "bounded_runtime.py").is_file(),
                        "A runnable bounded native driver is missing")
        self.api = importlib.import_module("bounded_runtime")
        self.work = tempfile.TemporaryDirectory(prefix="sdlc-runtime-")
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.plan, self.brief = fixture(self.root)

    def prepare(self, **kwargs):
        return self.api.prepare(self.root, "feature-one", self.brief, "developer",
                                kwargs.get("model", MODEL), kwargs.get("limits", LIMITS))

    def start(self, envelope=None):
        self.envelope = envelope or self.prepare()
        return self.api.start(self.root, self.envelope, state.digest(self.envelope),
                              state.digest(self.envelope["request"]))

    def issue(self, callback, code=None):
        with self.assertRaises(ContractIssue) as caught:
            callback()
        if code:
            self.assertEqual(code, caught.exception.code)

    def tool(self, name, arguments):
        return self.api.tool(self.root, self.envelope, name, arguments)

    def test_fixture_allocator_uses_standard_temporary_storage(self):
        self.assertTrue(self.root.is_relative_to(Path(tempfile.gettempdir())))

    def test_prepare_is_read_only_disabled_and_execute_are_rejected(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.prepare()
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        self.brief["allowedActions"].append("execute")
        self.issue(self.prepare, "E_RUNTIME_UNSUPPORTED")
        manager.configure_policy(self.root, policy(False))
        self.issue(self.prepare, "E_EXECUTION_DISABLED")

    def test_default_disabled_operations_do_not_even_create_manager_storage(self):
        envelope = self.prepare()
        disabled = self.root / "disabled"
        disabled.mkdir()
        subprocess.run(["git", "init", "-q", str(disabled)], check=True)
        before = set(disabled.rglob("*"))
        for callback in (
            lambda: self.api.check(disabled, envelope),
            lambda: self.api.step(disabled, envelope, "prompt"),
            lambda: self.api.observe(disabled, envelope, "response"),
            lambda: self.api.tool(disabled, envelope, "read", {"path": "guide.md"}),
        ):
            self.issue(callback)
        self.assertEqual(before, set(disabled.rglob("*")))

    def test_explicit_digests_start_once_and_real_tools_preserve_acceptance(self):
        envelope = self.prepare()
        self.issue(lambda: self.api.start(self.root, envelope, "sha256:" + "0" * 64,
                                         state.digest(envelope["request"])), "E_RUNTIME_APPROVAL")
        self.start(envelope)
        self.issue(lambda: self.start(envelope))
        read = self.tool("read", {"path": "src/feature.py"})
        self.assertEqual("before\n", read["content"])
        found = self.tool("search", {"path": "guide.md", "query": "guidance"})
        self.assertEqual([{"line": 1, "text": "bounded guidance"}], found["matches"])
        self.tool("edit", {"path": "src/feature.py", "expectedDigest": read["digest"], "content": "after\n"})
        self.assertEqual("after\n", (self.root / "src" / "feature.py").read_text())
        supplied = result(self.plan)
        supplied["verification"][0]["result"] = "unavailable"
        self.api.receive(self.root, self.envelope, supplied)
        self.assertEqual("reported", manager.inspect_execution(
            self.root, "feature-one")["state"]["tasks"]["implement"]["status"])
        self.issue(lambda: self.tool("read", {"path": "guide.md"}))
        store = self.api.inspect(self.root)
        self.assertNotIn("after", json.dumps(store))
        self.assertNotIn("bounded guidance", json.dumps(store))

    def test_paths_tools_and_compare_and_swap_are_confined(self):
        self.start()
        for name, args in (
            ("execute", {"command": "echo unsafe"}),
            ("read", {"path": ".git/config"}),
            ("read", {"path": "src/../guide.md"}),
            ("edit", {"path": "guide.md", "content": "wrong", "expectedDigest": "sha256:" + "0" * 64}),
            ("edit", {"path": "src/feature.py", "content": "wrong", "expectedDigest": "sha256:" + "0" * 64}),
        ):
            self.issue(lambda: self.tool(name, args))
        self.assertEqual("before\n", (self.root / "src" / "feature.py").read_text())

    def test_source_consent_profile_and_control_drift_stop_operations(self):
        for kind in ("source", "consent", "profile", "controls"):
            with self.subTest(kind=kind):
                if hasattr(self, "envelope"):
                    shutil.rmtree(self.root)
                    self.plan, self.brief = fixture(self.root)
                self.start()
                if kind == "source":
                    (self.root / "docs" / "plans" / "feature.md").write_text("drift")
                elif kind == "consent":
                    manager.configure_policy(self.root, policy())
                elif kind == "profile":
                    with (self.root / ".github" / "agents" / "sdlc-developer.agent.md").open("a") as stream:
                        stream.write("drift")
                else:
                    controls.configure_controls(self.root, {
                        "schemaVersion": 1, "enabled": True, "mode": "manual",
                        "maxAttempts": 1, "allowEscalation": False, "permittedModels": [],
                    })
                    controls.set_pause(self.root, True, "operator pause")
                self.issue(lambda: self.tool("read", {"path": "guide.md"}))
                self.issue(lambda: self.api.receive(self.root, self.envelope, result(self.plan)))
                self.assertEqual({}, manager.inspect_execution(self.root, "feature-one")["receipts"])

    def test_enabled_manual_controls_are_not_weakened(self):
        controls.configure_controls(self.root, {
            "schemaVersion": 1, "enabled": True, "mode": "manual",
            "maxAttempts": 1, "allowEscalation": False, "permittedModels": [],
        })
        self.issue(self.prepare, "E_RUNTIME_CONTROLS")
        self.assertTrue(controls.inspect_controls(self.root)["enabled"])

    def test_budget_and_cancel_leave_unknown_work_unresolved(self):
        self.start(self.prepare(limits={**LIMITS, "maxIterations": 1, "maxToolCalls": 1}))
        self.api.step(self.root, self.envelope, "small prompt")
        self.issue(lambda: self.api.step(self.root, self.envelope, "second"), "E_RUNTIME_LIMIT")
        self.tool("read", {"path": "guide.md"})
        self.issue(lambda: self.tool("read", {"path": "guide.md"}), "E_RUNTIME_LIMIT")
        self.api.stop(self.root, self.envelope)
        self.issue(lambda: self.api.check(self.root, self.envelope), "E_RUNTIME_UNRESOLVED")
        self.issue(lambda: self.start())
        self.assertEqual("running", manager.inspect_execution(
            self.root, "feature-one")["state"]["tasks"]["implement"]["status"])
        self.assertEqual("unknown", self.api.inspect(self.root)["status"])

    def test_cli_uses_real_manager_and_rejects_unknown_operations(self):
        envelope = self.prepare()
        command = [sys.executable, "-I", str(SCRIPTS / "manage_runtime.py"),
                   "start", "--project-root", str(self.root)]
        payload = {"envelope": envelope, "approvedRuntimeDigest": state.digest(envelope),
                   "approvedRequestDigest": state.digest(envelope["request"])}
        completed = subprocess.run(command, input=json.dumps(payload), capture_output=True, text=True)
        self.assertEqual(0, completed.returncode, completed.stderr)
        refused = subprocess.run(command, input=json.dumps(payload), capture_output=True, text=True)
        self.assertNotEqual(0, refused.returncode)
        invalid = subprocess.run(command[:3] + ["approve", "--project-root", str(self.root)],
                                 input="{}", capture_output=True, text=True)
        self.assertNotEqual(0, invalid.returncode)

    def test_expired_input_output_and_tool_bounds_never_produce_a_receipt(self):
        self.start(self.prepare(limits={**LIMITS, "maxWallMs": 10}))
        time.sleep(0.03)
        self.issue(lambda: self.api.check(self.root, self.envelope), "E_RUNTIME_LIMIT")
        self.api.stop(self.root, self.envelope)
        shutil.rmtree(self.root)
        self.plan, self.brief = fixture(self.root)
        self.start(self.prepare(limits={**LIMITS, "maxInputBytes": 5, "maxOutputBytes": 5}))
        self.issue(lambda: self.api.step(self.root, self.envelope, "123456"), "E_RUNTIME_LIMIT")
        self.issue(lambda: self.api.observe(self.root, self.envelope, "123456"), "E_RUNTIME_LIMIT")
        self.assertEqual({}, manager.inspect_execution(self.root, "feature-one")["receipts"])

    def test_hardlinks_writer_conflicts_and_unapproved_guidance_cannot_be_used(self):
        self.start()
        owned = self.root / "src" / "feature.py"
        alias = self.root / "alias.py"
        os.link(owned, alias)
        self.issue(lambda: self.tool("read", {"path": "src/feature.py"}), "E_RUNTIME_PATH")
        alias.unlink()
        with manager._writer(self.root):
            self.issue(lambda: self.tool("read", {"path": "guide.md"}), "E_EXECUTION_BUSY")
        self.tool("read", {"path": "guide.md"})
        (self.root / "guide.md").write_text("changed")
        self.issue(lambda: self.api.step(self.root, self.envelope, "next"), "E_RUNTIME_SOURCE")

    def test_model_binding_and_verification_claims_are_not_fabricated(self):
        self.start()
        altered = json.loads(json.dumps(self.envelope))
        altered["model"]["id"] = "different-model"
        self.issue(lambda: self.api.check(self.root, altered), "E_RUNTIME_BINDING")
        self.issue(lambda: self.api.receive(self.root, self.envelope, result(self.plan)), "E_RUNTIME_UNSUPPORTED")
        self.assertEqual({}, manager.inspect_execution(self.root, "feature-one")["receipts"])

    def test_allowed_action_subset_cannot_be_escalated_by_tool_arguments(self):
        self.brief["allowedActions"] = ["read"]
        self.start()
        self.issue(lambda: self.tool("edit", {"path": "src/feature.py",
                    "expectedDigest": "sha256:" + "0" * 64, "content": "no"}), "E_RUNTIME_UNSUPPORTED")
        self.issue(lambda: self.tool("read", {"path": "guide.md", "approval": True}))
        self.assertEqual("before\n", (self.root / "src" / "feature.py").read_text())

    def test_cli_rejects_duplicate_keys_and_import_injection(self):
        command = [sys.executable, "-I", "-S", str(SCRIPTS / "manage_runtime.py"),
                   "check", "--project-root", str(self.root)]
        for payload in ('{"envelope":{},"envelope":{}}', '{"envelope":{},"adapter":"attacker"}',
                        '{"envelope":NaN}'):
            refused = subprocess.run(command, input=payload, capture_output=True, text=True)
            self.assertNotEqual(0, refused.returncode)
        (self.root / "bounded_runtime.py").write_text("raise RuntimeError('untrusted import')\n")
        self.start()
        completed = subprocess.run(command, input=json.dumps({"envelope": self.envelope}),
                                   capture_output=True, text=True, cwd=self.root)
        self.assertEqual(0, completed.returncode, completed.stderr)
