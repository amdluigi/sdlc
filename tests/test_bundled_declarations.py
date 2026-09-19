"""The bundle satisfies its own capability provider contract on disk.

A bundled capability declares itself in ``sdlc-capability.json`` beside its
``SKILL.md``, exactly as a third-party provider does. The registry keeps
placement. These tests pin the split and the assembly that rejoins them.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "sdlc" / "scripts"
SKILLS = ROOT / "skills"
MODULES = SKILLS / "sdlc" / "modules"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import capability_contract  # noqa: E402
import resolve_providers  # noqa: E402


PLACEMENT_FIELDS = ("name", "category", "order", "replaceable")
DECLARED_FIELDS = (
    "trigger", "exitSignal", "evidence", "instructions", "capability"
)


def write_registry(directory, modules):
    """Write a registry where the real one lives, relative to the root.

    Implementations are siblings of the control plane, so the fixture
    reproduces that shape rather than asserting it separately.
    """

    payload = {
        "schemaVersion": 1,
        "deliveryPhases": ["inception", "verification"],
        "categories": {
            "context": {"deliveryPhase": "inception", "gate": None,
                        "order": 0},
            "verification": {"deliveryPhase": "verification", "gate": 5,
                             "order": 1},
        },
        "modules": modules,
    }
    registry_path = directory / "sdlc" / "modules" / "registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(payload), encoding="utf-8")
    return registry_path


def write_declaration(directory, name, **overrides):
    capability_dir = directory / capability_contract.bundled_directory_name(
        name
    )
    capability_dir.mkdir(parents=True, exist_ok=True)
    (capability_dir / "SKILL.md").write_text("# module\n", encoding="utf-8")
    declaration = {
        "schemaVersion": 1,
        "id": capability_contract.bundled_provider_id(name),
        "capability": name,
        "mode": "default",
        "instructions": "SKILL.md",
        "trigger": "Always when enabled.",
        "exitSignal": "The capability is satisfied.",
        "evidence": ["Inspectable evidence supports the outcome."],
        "compatibleSdlc": ">=1.0.0 <2.0.0",
    }
    declaration.update(overrides)
    for key, value in list(declaration.items()):
        if value is None:
            del declaration[key]
    (capability_dir / "sdlc-capability.json").write_text(
        json.dumps(declaration), encoding="utf-8"
    )
    return capability_dir / "sdlc-capability.json"


class ShippedBundleTest(unittest.TestCase):
    """The declarations the project actually ships."""

    def setUp(self):
        self.registry = json.loads(
            (MODULES / "registry.json").read_text(encoding="utf-8")
        )

    def test_every_capability_ships_a_declaration(self):
        for entry in self.registry["modules"]:
            path = SKILLS / ("sdlc-" + entry["name"]) / "sdlc-capability.json"
            self.assertTrue(
                path.is_file(),
                f"{entry['name']} ships no sdlc-capability.json",
            )

    def test_registry_carries_placement_only(self):
        for entry in self.registry["modules"]:
            for field in DECLARED_FIELDS:
                self.assertNotIn(
                    field,
                    entry,
                    f"{entry['name']} keeps {field} in the registry",
                )
            self.assertNotIn("path", entry)

    def test_shipped_declarations_satisfy_the_contract(self):
        names = {entry["name"] for entry in self.registry["modules"]}
        for name in names:
            declaration = json.loads(
                (SKILLS / ("sdlc-" + name) / "sdlc-capability.json").read_text(
                    encoding="utf-8"
                )
            )
            normalized = capability_contract.validate_declaration(
                declaration, capabilities=names
            )
            self.assertEqual(normalized["capability"], name)
            self.assertEqual(
                normalized["id"],
                capability_contract.bundled_provider_id(name),
            )
            self.assertEqual(normalized["mode"], "default")

    def test_every_implementation_is_named_after_its_interface(self):
        """A module is an interface; the skill serving it is named."""
        for entry in self.registry["modules"]:
            name = entry["name"]
            declaration = json.loads(
                (SKILLS / ("sdlc-" + name) / "sdlc-capability.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(declaration["id"], f"sdlc-{name}")

    def test_a_third_party_may_not_claim_a_bundled_name(self):
        for identity in ("sdlc", "sdlc-testing", "sdlc-anything"):
            with self.subTest(identity=identity):
                declaration = json.loads(
                    (SKILLS / "sdlc-testing" / "sdlc-capability.json").read_text(
                        encoding="utf-8"
                    )
                )
                declaration["id"] = identity
                declaration["mode"] = "replace"
                declaration["evaluations"] = "evaluations.json"
                with self.assertRaises(capability_contract.ContractError):
                    capability_contract.validate_declaration(
                        declaration, reserved={"sdlc"}
                    )

    def test_a_shipped_declaration_is_a_usable_example(self):
        """A contributor copies this file and changes three fields."""
        declaration = json.loads(
            (SKILLS / "sdlc-testing" / "sdlc-capability.json").read_text(
                encoding="utf-8"
            )
        )
        declaration["id"] = "acme-testing"
        declaration["mode"] = "replace"
        declaration["evaluations"] = "evaluations.json"
        normalized = capability_contract.validate_declaration(
            declaration, reserved={"sdlc"}
        )
        self.assertEqual(normalized["id"], "acme-testing")
        self.assertEqual(normalized["mode"], "replace")


class LoadRegistryTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_assembly_restores_the_record_consumers_expect(self):
        path = write_registry(self.dir, [
            {"name": "testing", "category": "verification", "order": 0,
             "replaceable": True},
        ])
        write_declaration(self.dir, "testing")
        registry = capability_contract.load_registry(path)
        entry = registry["modules"][0]
        self.assertEqual(entry["name"], "testing")
        self.assertEqual(entry["category"], "verification")
        self.assertEqual(entry["order"], 0)
        self.assertTrue(entry["replaceable"])
        self.assertEqual(entry["trigger"], "Always when enabled.")
        self.assertEqual(entry["exitSignal"], "The capability is satisfied.")
        self.assertEqual(
            entry["evidence"],
            ["Inspectable evidence supports the outcome."],
        )
        self.assertEqual(entry["path"], "sdlc-testing/SKILL.md")

    def test_registry_metadata_is_preserved(self):
        path = write_registry(self.dir, [
            {"name": "testing", "category": "verification", "order": 0,
             "replaceable": True},
        ])
        write_declaration(self.dir, "testing")
        registry = capability_contract.load_registry(path)
        self.assertEqual(
            registry["deliveryPhases"], ["inception", "verification"]
        )
        self.assertIn("verification", registry["categories"])

    def test_a_missing_declaration_is_refused(self):
        path = write_registry(self.dir, [
            {"name": "testing", "category": "verification", "order": 0,
             "replaceable": True},
        ])
        (self.dir / "testing").mkdir()
        with self.assertRaises(capability_contract.ContractError) as caught:
            capability_contract.load_registry(path)
        self.assertIn("testing", str(caught.exception))

    def test_an_absent_implementation_keeps_its_registered_name(self):
        """Presence is a fact about disk, not about the registry.

        Report mode once dropped absent capabilities from the module
        list. Configuration was validated against what remained, so
        disabling or replacing a capability whose bundled skill was not
        installed was rejected as an unknown core module. Only
        configuration can say whether an absent implementation is
        actually needed, so every registered name must survive.
        """

        path = write_registry(self.dir, [
            {"name": "testing", "category": "verification", "order": 0,
             "replaceable": True},
            {"name": "review", "category": "verification", "order": 1,
             "replaceable": True},
        ])
        write_declaration(self.dir, "review")
        registry = capability_contract.load_registry(
            path, on_missing="report"
        )
        self.assertEqual(
            [entry["name"] for entry in registry["modules"]], ["review"]
        )
        self.assertEqual(registry["absent"], ["testing"])
        self.assertEqual(
            [entry["name"] for entry in registry["placement"]],
            ["testing", "review"],
        )

    def test_a_complete_install_reports_nothing_absent(self):
        path = write_registry(self.dir, [
            {"name": "testing", "category": "verification", "order": 0,
             "replaceable": True},
        ])
        write_declaration(self.dir, "testing")
        registry = capability_contract.load_registry(
            path, on_missing="report"
        )
        self.assertEqual(registry["absent"], [])

    def test_missing_implementations_produce_one_repair_command(self):
        """The remedy is a command to run, not a description of one.

        No host resolves skill dependencies, so the control plane cannot
        have its requirements installed for it. Naming them is not enough;
        the developer needs the exact line.
        """

        missing = [
            {"capability": "testing", "requires": "sdlc-testing",
             "source": "bundled"},
            {"capability": "review", "requires": "sdlc-review",
             "source": "bundled"},
        ]
        self.assertEqual(
            resolve_providers.repair_command(missing),
            "npx skills add amdluigi/sdlc "
            "--skill sdlc-review --skill sdlc-testing",
        )

    def test_an_external_requirement_gets_no_repair_command(self):
        """We know where our own skills live, not where a third party's do.

        Emitting an install line for a provider the project chose in
        configuration would be a guess at a publisher we have never seen.
        """

        missing = [
            {"capability": "testing", "requires": "acme-testing",
             "source": "external"},
            {"capability": "review", "requires": "sdlc-review",
             "source": "bundled"},
        ]
        self.assertEqual(
            resolve_providers.repair_command(missing),
            "npx skills add amdluigi/sdlc --skill sdlc-review",
        )
        self.assertIsNone(resolve_providers.repair_command(
            [missing[0]]
        ))

    def test_nothing_missing_produces_no_repair_command(self):
        self.assertIsNone(resolve_providers.repair_command([]))
        self.assertIsNone(resolve_providers.repair_command(None))

    def test_a_disabled_capability_requires_nothing(self):
        """Configuration decides requirements, not the registry.

        A project that switched a phase off should never be asked to
        download the implementation for it.
        """

        entry = {"name": "testing"}
        self.assertIsNone(resolve_providers._required_providers(
            entry, False, absent=["testing"], installed=set()
        ))

    def test_an_enabled_capability_requires_its_bundled_skill(self):
        entry = {"name": "testing"}
        self.assertEqual(
            resolve_providers._required_providers(
                entry, True, absent=["testing"], installed=set()
            ),
            {"capability": "testing", "requires": "sdlc-testing",
             "source": "bundled"},
        )

    def test_a_present_bundled_skill_requires_nothing(self):
        entry = {"name": "testing"}
        self.assertIsNone(resolve_providers._required_providers(
            entry, True, absent=[], installed=set()
        ))

    def test_a_replaced_capability_does_not_require_the_bundled_skill(self):
        """An external provider discharges the dependency.

        The bundled implementation is absent here, but the project asked
        for someone else's, so installing ours would be pointless.
        """

        entry = {"name": "testing"}
        self.assertIsNone(resolve_providers._required_providers(
            entry,
            {"replaceWith": "acme-testing"},
            absent=["testing"],
            installed={"acme-testing"},
        ))

    def test_a_replacement_that_is_not_installed_is_reported(self):
        entry = {"name": "testing"}
        self.assertEqual(
            resolve_providers._required_providers(
                entry,
                {"replaceWith": "acme-testing"},
                absent=["testing"],
                installed=set(),
            ),
            {"capability": "testing", "requires": "acme-testing",
             "source": "external"},
        )

    def test_a_declaration_may_not_serve_another_capability(self):
        path = write_registry(self.dir, [
            {"name": "testing", "category": "verification", "order": 0,
             "replaceable": True},
        ])
        write_declaration(self.dir, "testing", capability="review")
        with self.assertRaises(capability_contract.ContractError) as caught:
            capability_contract.load_registry(path)
        self.assertIn("review", str(caught.exception))

    def test_a_bundled_declaration_may_not_claim_another_identity(self):
        path = write_registry(self.dir, [
            {"name": "testing", "category": "verification", "order": 0,
             "replaceable": True},
        ])
        write_declaration(self.dir, "testing", id="acme-testing")
        with self.assertRaises(capability_contract.ContractError) as caught:
            capability_contract.load_registry(path)
        self.assertIn("sdlc", str(caught.exception))

    def test_a_bundled_declaration_is_always_the_default(self):
        path = write_registry(self.dir, [
            {"name": "testing", "category": "verification", "order": 0,
             "replaceable": True},
        ])
        write_declaration(
            self.dir, "testing", mode="replace", evaluations="cases.json"
        )
        with self.assertRaises(capability_contract.ContractError) as caught:
            capability_contract.load_registry(path)
        self.assertIn("default", str(caught.exception))

    def test_a_declaration_may_not_claim_placement(self):
        """D15 and D21 extended: placement is registry-owned everywhere."""
        path = write_registry(self.dir, [
            {"name": "testing", "category": "verification", "order": 0,
             "replaceable": True},
        ])
        write_declaration(self.dir, "testing", category="inception")
        with self.assertRaises(capability_contract.ContractError) as caught:
            capability_contract.load_registry(path)
        self.assertIn("category", str(caught.exception))

    def test_instructions_are_confined_to_the_capability_directory(self):
        path = write_registry(self.dir, [
            {"name": "testing", "category": "verification", "order": 0,
             "replaceable": True},
        ])
        write_declaration(
            self.dir, "testing", instructions="../sdlc-review/SKILL.md"
        )
        with self.assertRaises(capability_contract.ContractError):
            capability_contract.load_registry(path)

    def test_a_registry_row_may_not_carry_declared_fields(self):
        path = write_registry(self.dir, [
            {"name": "testing", "category": "verification", "order": 0,
             "replaceable": True, "trigger": "Always."},
        ])
        write_declaration(self.dir, "testing")
        with self.assertRaises(capability_contract.ContractError) as caught:
            capability_contract.load_registry(path)
        self.assertIn("trigger", str(caught.exception))

    def test_a_missing_instruction_document_is_refused(self):
        path = write_registry(self.dir, [
            {"name": "testing", "category": "verification", "order": 0,
             "replaceable": True},
        ])
        declaration = write_declaration(self.dir, "testing")
        (declaration.parent / "SKILL.md").unlink()
        with self.assertRaises(capability_contract.ContractError) as caught:
            capability_contract.load_registry(path)
        self.assertIn("SKILL.md", str(caught.exception))

    def test_assembly_preserves_registry_order(self):
        path = write_registry(self.dir, [
            {"name": "project-memory", "category": "context", "order": 0,
             "replaceable": True},
            {"name": "testing", "category": "verification", "order": 1,
             "replaceable": True},
        ])
        write_declaration(self.dir, "project-memory")
        write_declaration(self.dir, "testing")
        registry = capability_contract.load_registry(path)
        self.assertEqual(
            [entry["name"] for entry in registry["modules"]],
            ["project-memory", "testing"],
        )


class SurveyConfigurationTest(unittest.TestCase):
    """A partial install must survive configuration that mentions the gap.

    This reproduces the failure end to end: disabling a capability whose
    bundled skill is not installed once aborted the survey with "unknown
    core module", because report mode had already removed the name that
    configuration referred to.
    """

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.skills = self.dir / "skills"
        self.project = self.dir / "project"
        (self.project / ".sdlc").mkdir(parents=True)
        self.registry = write_registry(self.skills, [
            {"name": "project-memory", "category": "context", "order": 0,
             "replaceable": True},
            {"name": "testing", "category": "verification", "order": 1,
             "replaceable": True},
        ])
        write_declaration(self.skills, "project-memory")

    def write_config(self, testing):
        (self.project / ".sdlc" / "config.json").write_text(
            json.dumps({
                "schemaVersion": 3,
                "modules": {"project-memory": True, "testing": testing},
                "extensions": {"project": {}, "global": {}},
                "measurement": {"enabled": False},
            }),
            encoding="utf-8",
        )

    def run_survey(self):
        import contextlib
        import io

        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            resolve_providers.main([
                "survey",
                "--registry", str(self.registry),
                "--project-root", str(self.project),
                "--sdlc-version", "1.0.0",
                "--provider-root", str(self.skills),
                "--host-profile", "filesystem",
            ])
        return json.loads(stream.getvalue())

    def test_disabling_an_absent_capability_requires_nothing(self):
        self.write_config(False)
        result = self.run_survey()
        self.assertEqual(result["missing"], [])
        self.assertIsNone(result["repair"])

    def test_an_enabled_absent_capability_is_reported_with_its_remedy(self):
        self.write_config(True)
        result = self.run_survey()
        self.assertEqual(
            result["missing"],
            [{"capability": "testing", "requires": "sdlc-testing",
              "source": "bundled"}],
        )
        self.assertEqual(
            result["repair"],
            "npx skills add amdluigi/sdlc --skill sdlc-testing",
        )

    def test_bundled_implementations_are_not_reported_as_skipped(self):
        """Siblings are the bundle, not rejected third-party providers.

        Scanning the skills root now finds them, and the reserved prefix
        would otherwise record every healthy one as a skipped candidate,
        burying the malformed provider the list exists to surface.
        """

        self.write_config(True)
        self.assertEqual(self.run_survey()["skipped"], [])


if __name__ == "__main__":
    unittest.main()
