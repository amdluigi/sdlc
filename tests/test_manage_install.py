"""Initialization, checking, and completion are separate, testable acts.

These three ran as prose in ``SKILL.md``: configuration appeared as a side
effect of the first non-trivial task, and the missing-implementation
protocol was four numbered steps an agent could paraphrase. Prose cannot be
tested, so none of it was. Each is now a command with a verdict.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "sdlc" / "scripts"))

import manage_install  # noqa: E402

REGISTRY = ROOT / "skills" / "sdlc" / "modules" / "registry.json"
SKILLS = ROOT / "skills"
COMMANDS = ROOT / "commands"


def survey_stub(capabilities, missing=None, repair=None):
    return {
        "schemaVersion": 1,
        "capabilities": capabilities,
        "missing": missing or [],
        "repair": repair,
        "skipped": [],
        "choicesRequired": [],
    }


def capability(name, phase, **overrides):
    row = {
        "capability": name,
        "deliveryPhase": phase,
        "entryGate": None,
        "state": "enabled",
        "decision": "settled",
        "active": {"type": "bundled"},
    }
    row.update(overrides)
    return row


class InitializeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_it_creates_the_configuration_from_the_template(self):
        result = manage_install.initialize(self.root)
        self.assertEqual(result["action"], "created")
        written = json.loads(
            (self.root / ".sdlc" / "config.json").read_text(
                encoding="utf-8"
            )
        )
        template = json.loads(
            manage_install.TEMPLATE.read_text(encoding="utf-8")
        )
        self.assertEqual(written, template)
        self.assertEqual(result["capabilities"], 22)

    def test_it_refuses_to_overwrite_a_configuration(self):
        """A configuration records decisions, so it is never regenerated.

        Rewriting it from the template would silently re-enable every
        phase the developer had switched off.
        """

        manage_install.initialize(self.root)
        path = self.root / ".sdlc" / "config.json"
        path.write_text('{"schemaVersion": 4, "phases": {}}', "utf-8")
        result = manage_install.initialize(self.root)
        self.assertEqual(result["action"], "kept")
        self.assertEqual(
            json.loads(path.read_text(encoding="utf-8")),
            {"schemaVersion": 4, "phases": {}},
        )

    def test_a_missing_project_root_is_refused(self):
        with self.assertRaises(manage_install.InstallError):
            manage_install.initialize(self.root / "absent")


class CheckTest(unittest.TestCase):
    def test_an_enabled_capability_with_a_provider_is_ok(self):
        report = manage_install.check(survey_stub([
            capability("testing", "verification"),
        ]))
        self.assertTrue(report["healthy"])
        self.assertEqual(report["capabilities"][0]["status"], "ok")

    def test_a_disabled_capability_is_not_a_gap(self):
        report = manage_install.check(survey_stub([
            capability("testing", "verification", state="disabled"),
        ]))
        self.assertTrue(report["healthy"])
        self.assertEqual(
            report["capabilities"][0]["status"], "disabled"
        )

    def test_an_absent_capability_is_reported_under_its_phase(self):
        """A gap has no survey row, so its phase comes from the registry.

        Without that the one line a developer most needs to see prints
        under no phase at all.
        """

        report = manage_install.check(
            survey_stub(
                [],
                missing=[{"capability": "testing",
                          "requires": "sdlc-testing",
                          "source": "bundled"}],
                repair="npx skills add amdluigi/sdlc --skill sdlc-testing",
            ),
            placement={"testing": {"deliveryPhase": "verification",
                                   "entryGate": 5}},
        )
        self.assertFalse(report["healthy"])
        row = report["capabilities"][0]
        self.assertEqual(row["status"], "missing")
        self.assertEqual(row["deliveryPhase"], "verification")
        self.assertEqual(row["detail"], "install sdlc-testing")

    def test_an_uninstalled_external_provider_is_reported_without_a_command(
        self
    ):
        report = manage_install.check(
            survey_stub(
                [capability(
                    "testing", "verification",
                    active={"type": "replacement", "id": "acme-testing"},
                )],
                missing=[{"capability": "testing",
                          "requires": "acme-testing",
                          "source": "external"}],
            ),
        )
        self.assertFalse(report["healthy"])
        self.assertIn("acme-testing", report["capabilities"][0]["detail"])
        self.assertIsNone(report["repair"])

    def test_phases_render_in_lifecycle_order(self):
        """Registry order groups capabilities, not phases.

        Rendered in survey order the report opened with inception,
        triage, operate, which is not a lifecycle anyone recognizes.
        """

        report = manage_install.check(survey_stub([
            capability("continuous-improvement", "operate"),
            capability("project-memory", "inception"),
            capability("testing", "verification"),
        ]))
        text = manage_install.render(
            report, True, ["inception", "verification", "operate"]
        )
        self.assertLess(
            text.index("inception"), text.index("verification")
        )
        self.assertLess(text.index("verification"), text.index("operate"))

    def test_an_empty_phase_is_not_rendered(self):
        report = manage_install.check(survey_stub([
            capability("testing", "verification"),
        ]))
        text = manage_install.render(
            report, True, ["inception", "verification"]
        )
        self.assertNotIn("inception", text)


class DownloadTest(unittest.TestCase):
    def test_it_proposes_the_command_instead_of_running_it(self):
        """Printing and running are separate, so consent stays real."""

        calls = []
        result = manage_install.download(
            {"repair": "npx skills add amdluigi/sdlc --skill sdlc-testing"},
            runner=calls.append,
        )
        self.assertEqual(result["action"], "proposed")
        self.assertEqual(calls, [])

    def test_it_runs_the_command_when_asked(self):
        calls = []

        def runner(command):
            calls.append(command)
            return 0

        result = manage_install.download(
            {"repair": "npx skills add amdluigi/sdlc --skill sdlc-testing"},
            run=True,
            runner=runner,
        )
        self.assertEqual(result["action"], "installed")
        self.assertEqual(
            calls, ["npx skills add amdluigi/sdlc --skill sdlc-testing"]
        )

    def test_a_failed_install_is_reported_as_failed(self):
        result = manage_install.download(
            {"repair": "npx skills add amdluigi/sdlc --skill sdlc-testing"},
            run=True,
            runner=lambda command: 1,
        )
        self.assertEqual(result["action"], "failed")

    def test_nothing_to_install_is_not_an_error(self):
        result = manage_install.download({"repair": None}, run=True)
        self.assertEqual(result["action"], "nothing-to-do")


class CommandLineTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def run_main(self, argv):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = manage_install.main(argv)
        return code, stream.getvalue()

    def check_argv(self):
        return [
            "check",
            "--project-root", str(self.root),
            "--registry", str(REGISTRY),
            "--sdlc-version", "1.0.0",
            "--provider-root", str(SKILLS),
            "--host-profile", "filesystem",
        ]

    def test_a_complete_installation_checks_clean(self):
        code, output = self.run_main(self.check_argv())
        self.assertEqual(code, 0)
        self.assertIn("22 capabilities", output)
        self.assertIn("0 missing", output)

    def test_the_report_names_every_delivery_phase(self):
        _, output = self.run_main(self.check_argv())
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        for phase in registry["deliveryPhases"]:
            self.assertIn(phase, output)

    def test_init_then_check_leaves_the_installation_whole(self):
        code, _ = self.run_main(["init", "--project-root", str(self.root)])
        self.assertEqual(code, 0)
        self.assertTrue((self.root / ".sdlc" / "config.json").is_file())
        code, output = self.run_main(self.check_argv())
        self.assertEqual(code, 0)
        self.assertIn(".sdlc/config.json", output)

    def test_download_has_nothing_to_do_for_a_complete_installation(self):
        code, output = self.run_main(
            ["download"] + self.check_argv()[1:]
        )
        self.assertEqual(code, 0)
        self.assertIn("nothing to install", output)


class ShippedCommandsTest(unittest.TestCase):
    """The commands and the script cannot drift apart.

    Commands exist only in hosts that support them, so the script is
    where the behavior lives. A command naming an operation the script
    does not have would fail only for the developer who typed it.
    """

    def test_every_operation_ships_a_command(self):
        for operation in ("init", "check", "download"):
            path = COMMANDS / f"sdlc-{operation}.md"
            self.assertTrue(path.is_file(), f"missing {path.name}")
            text = path.read_text(encoding="utf-8")
            self.assertIn(f"name: sdlc-{operation}", text)
            self.assertIn(
                f"manage_install.py {operation}", text
            )

    def test_every_command_names_an_operation_the_script_has(self):
        for path in sorted(COMMANDS.glob("*.md")):
            operation = path.stem.removeprefix("sdlc-")
            self.assertIn(
                operation,
                manage_install.OPERATIONS,
                f"{path.name} names an unknown operation",
            )

    def test_every_command_is_available_to_the_skill_itself(self):
        """The control plane invokes these, not only the developer.

        A command the model may not invoke, or whose description does not
        say when it applies, leaves the skill where it started: carrying
        the procedure as prose nobody can test.
        """

        for path in sorted(COMMANDS.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("disable-model-invocation: true", text)
            description = next(
                line for line in text.splitlines()
                if line.startswith("description:")
            )
            self.assertIn(
                "Use ", description,
                f"{path.name} does not say when to use it",
            )


if __name__ == "__main__":
    unittest.main()
