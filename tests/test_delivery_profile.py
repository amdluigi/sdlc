from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "skills" / "sdlc" / "modules" / "registry.json"

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


if __name__ == "__main__":
    unittest.main()
