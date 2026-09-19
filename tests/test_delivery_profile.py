from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "skills" / "sdlc" / "modules" / "registry.json"
ARTIFACT = ROOT / "docs" / "DELIVERY-PROFILE.md"

EXPECTED_PHASES = [
    "inception",
    "triage",
    "design",
    "implementation",
    "verification",
    "delivery",
    "operate",
]

GATELESS_PHASES = {"inception", "operate"}

SKILL_GATES = {1, 2, 3, 4, 5}


def registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


class DeliveryPhaseRegistryTest(unittest.TestCase):
    def test_phases_are_declared_in_lifecycle_order(self) -> None:
        self.assertEqual(registry()["deliveryPhases"], EXPECTED_PHASES)

    def test_every_category_declares_a_phase(self) -> None:
        data = registry()
        categories = data["categories"]
        used = {entry["category"] for entry in data["modules"]}

        self.assertEqual(set(categories), used)
        for name, entry in categories.items():
            self.assertIn(entry["deliveryPhase"], EXPECTED_PHASES, name)

    def test_every_module_resolves_to_exactly_one_phase(self) -> None:
        data = registry()
        categories = data["categories"]

        resolved = [
            categories[entry["category"]]["deliveryPhase"]
            for entry in data["modules"]
        ]

        self.assertEqual(len(resolved), len(data["modules"]))
        self.assertEqual(len(data["modules"]), 22)

    def test_every_phase_has_at_least_one_capability(self) -> None:
        data = registry()
        categories = data["categories"]
        covered = {
            categories[entry["category"]]["deliveryPhase"]
            for entry in data["modules"]
        }

        self.assertEqual(covered, set(EXPECTED_PHASES))

    def test_category_order_is_contiguous_from_zero(self) -> None:
        categories = registry()["categories"]
        orders = [entry["order"] for entry in categories.values()]

        self.assertEqual(sorted(orders), list(range(len(categories))))

    def test_gate_references_are_valid_or_null(self) -> None:
        for name, entry in registry()["categories"].items():
            gate = entry["gate"]
            if gate is None:
                continue
            self.assertIn(gate, SKILL_GATES, name)

    def test_entry_gates_do_not_decrease_across_phase_order(self) -> None:
        data = registry()
        order = {name: index for index, name in enumerate(EXPECTED_PHASES)}
        seen = []

        for entry in data["categories"].values():
            if entry["gate"] is None:
                continue
            seen.append((order[entry["deliveryPhase"]], entry["gate"]))

        seen.sort()
        gates = [gate for _, gate in seen]

        self.assertEqual(gates, sorted(gates))

    def test_phases_outside_the_state_machine_declare_no_gate(self) -> None:
        for name, entry in registry()["categories"].items():
            if entry["deliveryPhase"] in GATELESS_PHASES:
                self.assertIsNone(entry["gate"], name)


SCRIPTS = ROOT / "skills" / "sdlc" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import delivery_profile  # noqa: E402


def base_config() -> dict:
    return {
        "schemaVersion": 3,
        "modules": {},
        "extensions": {"project": {}, "global": {}},
        "measurement": {"enabled": False},
    }


def find(profile: dict, name: str) -> dict:
    for phase in profile["phases"]:
        for capability in phase["capabilities"]:
            if capability["name"] == name:
                return capability
    raise AssertionError(f"capability not found: {name}")


class BuildProfileTest(unittest.TestCase):
    def test_profile_lists_phases_in_registry_order(self) -> None:
        profile = delivery_profile.build_profile(registry(), base_config())

        self.assertEqual(
            [phase["name"] for phase in profile["phases"]],
            EXPECTED_PHASES,
        )

    def test_every_module_appears_exactly_once(self) -> None:
        profile = delivery_profile.build_profile(registry(), base_config())

        names = [
            capability["name"]
            for phase in profile["phases"]
            for capability in phase["capabilities"]
        ]

        self.assertEqual(len(names), 22)
        self.assertEqual(len(set(names)), 22)

    def test_unconfigured_module_resolves_to_bundled_default(self) -> None:
        profile = delivery_profile.build_profile(registry(), base_config())

        capability = find(profile, "review")

        self.assertEqual(capability["plugin"], "sdlc")
        self.assertEqual(capability["source"], "bundled")
        self.assertEqual(capability["role"], "default")

    def test_replacement_is_reported_with_its_plugin(self) -> None:
        config = base_config()
        config["modules"]["testing"] = {"replaceWith": "acme-testing"}

        profile = delivery_profile.build_profile(registry(), config)
        capability = find(profile, "testing")

        self.assertEqual(capability["plugin"], "acme-testing")
        self.assertEqual(capability["source"], "external")
        self.assertEqual(capability["role"], "replace")

    def test_an_explicit_bundled_choice_is_distinguished_from_default(
        self,
    ) -> None:
        config = base_config()
        config["modules"]["testing"] = {"provider": "bundled"}

        profile = delivery_profile.build_profile(registry(), config)
        capability = find(profile, "testing")

        self.assertEqual(capability["source"], "bundled")
        self.assertEqual(capability["role"], "chosen")
        self.assertTrue(capability["enabled"])

    def test_disabled_module_is_reported_but_not_hidden(self) -> None:
        config = base_config()
        config["modules"]["prd"] = False

        profile = delivery_profile.build_profile(registry(), config)
        capability = find(profile, "prd")

        self.assertFalse(capability["enabled"])

    def test_missing_config_is_treated_as_all_defaults(self) -> None:
        profile = delivery_profile.build_profile(registry(), None)

        self.assertTrue(
            all(
                capability["role"] == "default"
                for phase in profile["phases"]
                for capability in phase["capabilities"]
            )
        )

    def test_phase_gate_matches_the_registry(self) -> None:
        profile = delivery_profile.build_profile(registry(), None)
        gates = {phase["name"]: phase["gate"] for phase in profile["phases"]}

        self.assertIsNone(gates["inception"])
        self.assertIsNone(gates["operate"])
        self.assertEqual(gates["triage"], 1)
        self.assertEqual(gates["design"], 2)
        self.assertEqual(gates["implementation"], 3)
        self.assertEqual(gates["verification"], 5)


class RenderMarkdownTest(unittest.TestCase):
    def test_render_is_deterministic(self) -> None:
        profile = delivery_profile.build_profile(registry(), base_config())

        self.assertEqual(
            delivery_profile.render_markdown(profile),
            delivery_profile.render_markdown(profile),
        )

    def test_render_names_every_phase_and_capability(self) -> None:
        profile = delivery_profile.build_profile(registry(), base_config())
        text = delivery_profile.render_markdown(profile)

        for phase in EXPECTED_PHASES:
            self.assertIn(phase, text)
        self.assertIn("operational-readiness", text)
        self.assertIn("release-launch", text)
        self.assertIn("incident-response", text)

    def test_render_marks_gateless_phases(self) -> None:
        profile = delivery_profile.build_profile(registry(), base_config())
        text = delivery_profile.render_markdown(profile)

        self.assertIn("## inception (no gate)", text)
        self.assertIn("## triage (gate 1)", text)

    def test_render_contains_no_em_dash(self) -> None:
        profile = delivery_profile.build_profile(registry(), base_config())

        self.assertNotIn("\u2014", delivery_profile.render_markdown(profile))

    def test_replacement_changes_the_rendered_output(self) -> None:
        default_text = delivery_profile.render_markdown(
            delivery_profile.build_profile(registry(), base_config())
        )

        config = base_config()
        config["modules"]["testing"] = {"replaceWith": "acme-testing"}
        replaced_text = delivery_profile.render_markdown(
            delivery_profile.build_profile(registry(), config)
        )

        self.assertNotEqual(default_text, replaced_text)
        self.assertIn("acme-testing", replaced_text)


class ProfileArtifactTest(unittest.TestCase):
    """The committed artifact must match what the renderer produces."""

    def test_artifact_exists(self) -> None:
        self.assertTrue(ARTIFACT.is_file(), f"missing artifact: {ARTIFACT}")

    def test_artifact_matches_regenerated_output(self) -> None:
        expected = delivery_profile.render_markdown(
            delivery_profile.build_profile(registry(), None)
        )
        actual = ARTIFACT.read_text(encoding="utf-8")

        self.assertEqual(
            actual,
            expected,
            "docs/DELIVERY-PROFILE.md is stale. Regenerate it with "
            "scripts/delivery_profile.py render.",
        )

    def test_artifact_warns_against_hand_editing(self) -> None:
        self.assertIn(
            "Do not edit by hand", ARTIFACT.read_text(encoding="utf-8")
        )

    def test_artifact_contains_no_em_dash(self) -> None:
        self.assertNotIn("\u2014", ARTIFACT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
