"""The bundle satisfies its own capability provider contract on disk.

A bundled capability declares itself in ``sdlc-capability.json`` beside its
``MODULE.md``, exactly as a third-party provider does. The registry keeps
placement. These tests pin the split and the assembly that rejoins them.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "sdlc" / "scripts"
MODULES = ROOT / "skills" / "sdlc" / "modules"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import capability_contract  # noqa: E402


PLACEMENT_FIELDS = ("name", "category", "order", "replaceable")
DECLARED_FIELDS = (
    "trigger", "exitSignal", "evidence", "instructions", "capability"
)


def write_registry(directory, modules):
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
    (directory / "registry.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return directory / "registry.json"


def write_declaration(directory, name, **overrides):
    capability_dir = directory / name
    capability_dir.mkdir(parents=True, exist_ok=True)
    (capability_dir / "MODULE.md").write_text("# module\n", encoding="utf-8")
    declaration = {
        "schemaVersion": 1,
        "id": capability_contract.bundled_provider_id(name),
        "capability": name,
        "mode": "default",
        "instructions": "MODULE.md",
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
            path = MODULES / entry["name"] / "sdlc-capability.json"
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
                (MODULES / name / "sdlc-capability.json").read_text(
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
                (MODULES / name / "sdlc-capability.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(declaration["id"], f"sdlc-{name}")

    def test_a_third_party_may_not_claim_a_bundled_name(self):
        for identity in ("sdlc", "sdlc-testing", "sdlc-anything"):
            with self.subTest(identity=identity):
                declaration = json.loads(
                    (MODULES / "testing" / "sdlc-capability.json").read_text(
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
            (MODULES / "testing" / "sdlc-capability.json").read_text(
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
        self.assertEqual(entry["path"], "testing/MODULE.md")

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
            self.dir, "testing", instructions="../review/MODULE.md"
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
        (declaration.parent / "MODULE.md").unlink()
        with self.assertRaises(capability_contract.ContractError) as caught:
            capability_contract.load_registry(path)
        self.assertIn("MODULE.md", str(caught.exception))

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


if __name__ == "__main__":
    unittest.main()
