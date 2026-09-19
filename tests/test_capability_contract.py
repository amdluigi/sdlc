"""The capability provider contract states one vocabulary for every path.

The load-bearing test is ContractProjectionTest.test_every_bundled_module_
is_conformant. If the bundled registry cannot project onto the contract,
the claim that the vocabularies already agree is false, and the contract is
a redesign rather than a consolidation.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "sdlc" / "SKILL.md"
REGISTRY = ROOT / "skills" / "sdlc" / "modules" / "registry.json"
SCHEMA = (
    ROOT / "skills" / "sdlc" / "contracts" / "capability-provider.schema.json"
)
sys.path.insert(0, str(ROOT / "skills" / "sdlc" / "scripts"))

import capability_contract  # noqa: E402


def sdlc_version() -> str:
    match = re.search(
        r'^  version:\s+"([^"]+)"$',
        SKILL.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert match is not None
    return match.group(1)


def registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def valid_declaration(**overrides) -> dict:
    declaration = {
        "schemaVersion": 1,
        "id": "acme-review",
        "capability": "testing",
        "mode": "augment",
        "instructions": "MODULE.md",
        "trigger": "When the change alters behavior.",
        "exitSignal": "Tests cover the changed behavior.",
        "evidence": ["A failing test was observed before the fix."],
        "compatibleSdlc": ">=1.0.0 <2.0.0",
    }
    declaration.update(overrides)
    for key, value in list(declaration.items()):
        if value is None:
            del declaration[key]
    return declaration


class ContractProjectionTest(unittest.TestCase):
    def test_every_bundled_module_is_conformant(self):
        data = registry()
        capabilities = {entry["name"] for entry in data["modules"]}
        version = sdlc_version()
        self.assertTrue(capabilities)
        for entry in data["modules"]:
            with self.subTest(module=entry["name"]):
                declaration = (
                    capability_contract.declaration_from_registry_entry(
                        entry, version, capabilities
                    )
                )
                self.assertEqual(declaration["id"], "sdlc")
                self.assertEqual(declaration["capability"], entry["name"])
                self.assertEqual(declaration["mode"], "default")
                self.assertEqual(declaration["trigger"], entry["trigger"])
                self.assertEqual(
                    declaration["exitSignal"], entry["exitSignal"]
                )
                self.assertEqual(declaration["evidence"], entry["evidence"])

    def test_projection_preserves_every_evidence_clause(self):
        data = registry()
        version = sdlc_version()
        for entry in data["modules"]:
            declaration = capability_contract.declaration_from_registry_entry(
                entry, version
            )
            self.assertEqual(
                len(declaration["evidence"]), len(entry["evidence"])
            )

    def test_bundled_projection_is_compatible_with_itself(self):
        entry = registry()["modules"][0]
        declaration = capability_contract.declaration_from_registry_entry(
            entry, "1.2.3"
        )
        self.assertEqual(declaration["compatibleSdlc"], "==1.2.3")

    def test_registry_entry_missing_a_contract_field_is_rejected(self):
        entry = dict(registry()["modules"][0])
        del entry["exitSignal"]
        with self.assertRaises(capability_contract.ContractError):
            capability_contract.declaration_from_registry_entry(
                entry, sdlc_version()
            )


class ExtensionProjectionTest(unittest.TestCase):
    def metadata(self, **overrides) -> dict:
        value = {
            "schemaVersion": 1,
            "id": "acme-telemetry",
            "version": "0.1.0",
            "status": "active",
            "category": "observability",
            "mode": "augment",
            "path": "MODULE.md",
            "trigger": "When telemetry changes.",
            "exitSignal": "Telemetry is documented.",
            "evidence": ["Telemetry fields were listed in the report."],
            "compatibleSdlc": ">=1.0.0 <2.0.0",
        }
        value.update(overrides)
        return value

    def test_current_extension_field_set_is_conformant(self):
        declaration = capability_contract.declaration_from_extension(
            self.metadata()
        )
        self.assertEqual(declaration["mode"], "augment")
        self.assertEqual(declaration["id"], "acme-telemetry")
        self.assertNotIn("evaluations", declaration)

    def test_extension_may_not_claim_a_core_capability_identity(self):
        data = registry()
        reserved = {entry["name"] for entry in data["modules"]} | {"sdlc"}
        with self.assertRaises(capability_contract.ContractError):
            capability_contract.declaration_from_extension(
                self.metadata(id="review"), reserved=reserved
            )

    def test_replacing_extension_mode_is_refused(self):
        with self.assertRaises(capability_contract.ContractError):
            capability_contract.declaration_from_extension(
                self.metadata(mode="replace")
            )


class DeclarationValidationTest(unittest.TestCase):
    def test_valid_declaration_round_trips(self):
        declaration = capability_contract.validate_declaration(
            valid_declaration()
        )
        self.assertEqual(declaration["id"], "acme-review")

    def test_unknown_field_is_rejected(self):
        with self.assertRaises(capability_contract.ContractError):
            capability_contract.validate_declaration(
                valid_declaration(surprise="yes")
            )

    def test_missing_field_is_rejected(self):
        with self.assertRaises(capability_contract.ContractError):
            capability_contract.validate_declaration(
                valid_declaration(evidence=None)
            )

    def test_wrong_schema_version_is_rejected(self):
        with self.assertRaises(capability_contract.ContractError):
            capability_contract.validate_declaration(
                valid_declaration(schemaVersion=2)
            )

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(capability_contract.ContractError):
            capability_contract.validate_declaration(
                valid_declaration(mode="override")
            )

    def test_replacing_provider_must_declare_evaluations(self):
        with self.assertRaises(capability_contract.ContractError) as caught:
            capability_contract.validate_declaration(
                valid_declaration(mode="replace")
            )
        self.assertIn("parity", str(caught.exception))

    def test_replacing_provider_with_evaluations_is_accepted(self):
        declaration = capability_contract.validate_declaration(
            valid_declaration(mode="replace", evaluations="evals.json")
        )
        self.assertEqual(declaration["evaluations"], "evals.json")

    def test_augmenting_provider_may_declare_evaluations(self):
        declaration = capability_contract.validate_declaration(
            valid_declaration(evaluations="evals.json")
        )
        self.assertEqual(declaration["evaluations"], "evals.json")

    def test_traversing_instruction_path_is_rejected(self):
        for path in ("../MODULE.md", "/etc/MODULE.md", "a/../../b.md"):
            with self.subTest(path=path):
                with self.assertRaises(capability_contract.ContractError):
                    capability_contract.validate_declaration(
                        valid_declaration(instructions=path)
                    )

    def test_absolute_windows_instruction_path_is_rejected(self):
        with self.assertRaises(capability_contract.ContractError):
            capability_contract.validate_declaration(
                valid_declaration(instructions="C:/MODULE.md")
            )

    def test_instructions_must_name_a_markdown_file(self):
        with self.assertRaises(capability_contract.ContractError):
            capability_contract.validate_declaration(
                valid_declaration(instructions="MODULE.txt")
            )

    def test_non_kebab_identity_is_rejected(self):
        with self.assertRaises(capability_contract.ContractError):
            capability_contract.validate_declaration(
                valid_declaration(id="Acme_Review")
            )

    def test_unknown_capability_is_rejected(self):
        with self.assertRaises(capability_contract.ContractError):
            capability_contract.validate_declaration(
                valid_declaration(capability="invented"),
                capabilities={"testing", "review"},
            )

    def test_empty_evidence_is_rejected(self):
        with self.assertRaises(capability_contract.ContractError):
            capability_contract.validate_declaration(
                valid_declaration(evidence=[])
            )

    def test_reserved_identity_is_rejected(self):
        with self.assertRaises(capability_contract.ContractError):
            capability_contract.validate_declaration(
                valid_declaration(id="sdlc"), reserved={"sdlc"}
            )


class DeclarationParsingTest(unittest.TestCase):
    def test_duplicate_keys_are_rejected(self):
        with self.assertRaises(capability_contract.ContractError):
            capability_contract.parse_declaration(
                '{"id": "a", "id": "b"}'
            )

    def test_invalid_json_is_rejected(self):
        with self.assertRaises(capability_contract.ContractError):
            capability_contract.parse_declaration("{")

    def test_invalid_encoding_is_rejected(self):
        with self.assertRaises(capability_contract.ContractError):
            capability_contract.parse_declaration(b"\xff\xfe{}")

    def test_bytes_are_accepted(self):
        self.assertEqual(
            capability_contract.parse_declaration(b'{"a": 1}'), {"a": 1}
        )


class ContractSchemaTest(unittest.TestCase):
    def test_schema_and_module_declare_the_same_fields(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(
            set(schema["required"]), set(capability_contract.REQUIRED_FIELDS)
        )
        self.assertEqual(
            set(schema["properties"]),
            set(capability_contract.REQUIRED_FIELDS)
            | set(capability_contract.OPTIONAL_FIELDS),
        )

    def test_schema_declares_the_same_modes(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(
            schema["properties"]["mode"]["enum"],
            list(capability_contract.MODES),
        )

    def test_schema_requires_evaluations_when_replacing(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        conditionals = schema["allOf"]
        self.assertTrue(
            any(
                rule["if"]["properties"]["mode"]["const"] == "replace"
                and rule["then"]["required"] == ["evaluations"]
                for rule in conditionals
            )
        )

    def test_schema_forbids_unknown_fields(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
