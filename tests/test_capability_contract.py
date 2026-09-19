"""The capability provider contract states one vocabulary for every path.

The load-bearing test is BundledDeclarationTest.test_every_bundled_module_
is_conformant. The bundle no longer projects onto the contract from registry
rows; each capability declares itself on disk in the same file a third-party
provider authors. If those declarations do not satisfy the contract, the
claim that one vocabulary serves every path is false.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "sdlc" / "SKILL.md"
MODULES = ROOT / "skills" / "sdlc" / "modules"
REGISTRY = MODULES / "registry.json"
SCHEMA = (
    ROOT / "skills" / "sdlc" / "contracts" / "capability-provider.schema.json"
)
sys.path.insert(0, str(ROOT / "skills" / "sdlc" / "scripts"))

import capability_contract  # noqa: E402
import config_contract  # noqa: E402


def sdlc_version() -> str:
    match = re.search(
        r'^  version:\s+"([^"]+)"$',
        SKILL.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert match is not None
    return match.group(1)


def registry() -> dict:
    """The assembled registry, as every consumer reads it."""

    return capability_contract.load_registry(REGISTRY)


def placement_registry() -> dict:
    """The registry file itself, carrying placement only."""

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


class BundledDeclarationTest(unittest.TestCase):
    def test_every_bundled_module_is_conformant(self):
        data = placement_registry()
        capabilities = {entry["name"] for entry in data["modules"]}
        self.assertTrue(capabilities)
        for entry in data["modules"]:
            with self.subTest(module=entry["name"]):
                declaration = capability_contract.load_bundled_declaration(
                    MODULES, entry, capabilities
                )
                self.assertEqual(
                    declaration["id"],
                    capability_contract.bundled_provider_id(entry["name"]),
                )
                self.assertEqual(declaration["capability"], entry["name"])
                self.assertEqual(declaration["mode"], "default")
                self.assertTrue(declaration["trigger"])
                self.assertTrue(declaration["exitSignal"])
                self.assertTrue(declaration["evidence"])

    def test_assembly_exposes_every_evidence_clause(self):
        for entry in registry()["modules"]:
            declaration = json.loads(
                (MODULES / ("sdlc-" + entry["name"]) / "sdlc-capability.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                len(entry["evidence"]), len(declaration["evidence"])
            )

    def test_a_bundled_declaration_accepts_the_running_release(self):
        import adaptive_extensions

        version = sdlc_version()
        for entry in placement_registry()["modules"]:
            declaration = capability_contract.load_bundled_declaration(
                MODULES, entry
            )
            self.assertTrue(
                adaptive_extensions.version_satisfies(
                    version, declaration["compatibleSdlc"]
                ),
                f"{entry['name']} refuses its own release {version}",
            )

    def test_a_registry_entry_without_a_declaration_is_rejected(self):
        with self.assertRaises(capability_contract.ContractError):
            capability_contract.load_bundled_declaration(
                MODULES, {"name": "no-such-capability"}
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
        for identity in ("sdlc", "sdlc-review", "sdlc-not-a-capability"):
            with self.subTest(identity=identity):
                with self.assertRaises(capability_contract.ContractError):
                    capability_contract.validate_declaration(
                        valid_declaration(id=identity), reserved={"sdlc"}
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


class NonDelegatableTest(unittest.TestCase):
    """The four capabilities that permit progression may not be delegated."""

    def config(self, **modules) -> dict:
        return {
            "schemaVersion": 3,
            "modules": modules,
            "extensions": {"project": {}, "global": {}},
            "measurement": {"enabled": False},
        }

    def names(self) -> set:
        return {entry["name"] for entry in registry()["modules"]}

    def test_replacing_a_judgment_capability_is_refused(self):
        for name in config_contract.NON_DELEGATABLE:
            with self.subTest(module=name):
                with self.assertRaises(config_contract.ConfigError) as caught:
                    config_contract.normalize_config(
                        self.config(**{name: {"replaceWith": "acme-plugin"}}),
                        self.names(),
                    )
                self.assertIn("may not be replaced", str(caught.exception))

    def test_a_judgment_capability_may_still_be_disabled(self):
        normalized = config_contract.normalize_config(
            self.config(review=False), self.names()
        )
        self.assertIs(normalized["modules"]["review"], False)

    def test_a_delegatable_capability_may_still_be_replaced(self):
        normalized = config_contract.normalize_config(
            self.config(testing={"replaceWith": "acme-testing"}),
            self.names(),
        )
        self.assertEqual(
            normalized["modules"]["testing"], {"replaceWith": "acme-testing"}
        )

    def test_registry_flags_match_the_non_delegatable_set(self):
        flagged = {
            entry["name"]
            for entry in registry()["modules"]
            if not entry["replaceable"]
        }
        self.assertEqual(flagged, set(config_contract.NON_DELEGATABLE))

    def test_every_module_declares_replaceability(self):
        for entry in registry()["modules"]:
            with self.subTest(module=entry["name"]):
                self.assertIsInstance(entry["replaceable"], bool)

    def test_config_schema_declares_the_restriction(self):
        schema = json.loads(
            (
                ROOT
                / "skills"
                / "sdlc"
                / "contracts"
                / "sdlc-config.schema.json"
            ).read_text(encoding="utf-8")
        )
        states = {
            name: state
            for group in schema["properties"]["phases"]["properties"].values()
            for name, state in group["properties"].items()
        }
        restricted = {
            name
            for name, state in states.items()
            if state["$ref"].endswith("nonDelegatableState")
        }
        self.assertEqual(restricted, set(config_contract.NON_DELEGATABLE))

    def test_restricted_schema_state_forbids_replacement(self):
        schema = json.loads(
            (
                ROOT
                / "skills"
                / "sdlc"
                / "contracts"
                / "sdlc-config.schema.json"
            ).read_text(encoding="utf-8")
        )
        state = schema["$defs"]["nonDelegatableState"]
        self.assertEqual(state["type"], "boolean")


if __name__ == "__main__":
    unittest.main()
