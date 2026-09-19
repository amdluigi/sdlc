from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "skills" / "sdlc" / "modules" / "registry.json"
CONFIG_SCHEMA = (
    ROOT / "skills" / "sdlc" / "contracts" / "sdlc-config.schema.json"
)
CONFIG_TEMPLATE = (
    ROOT / "skills" / "sdlc" / "assets" / "sdlc-config.template.json"
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def lifecycle_order() -> list:
    """Module names in the order a change moves through the lifecycle.

    Phase first, then category within the phase, then module within the
    category, so the sequence matches the published delivery phases.
    """

    registry = load(REGISTRY)
    categories = registry["categories"]
    phases = registry["deliveryPhases"]
    return [
        entry["name"]
        for entry in sorted(
            registry["modules"],
            key=lambda item: (
                phases.index(categories[item["category"]]["deliveryPhase"]),
                categories[item["category"]]["order"],
                item["order"],
            ),
        )
    ]


def schema_modules() -> list:
    """Configurable module names, read out of the phase groups in order."""

    groups = load(CONFIG_SCHEMA)["properties"]["phases"]["properties"]
    return [
        name
        for phase in groups.values()
        for name in phase["properties"]
    ]


def template_modules() -> list:
    """Template module names, read out of the phase groups in order."""

    return [
        name
        for group in load(CONFIG_TEMPLATE)["phases"].values()
        for name in group
    ]


class LifecycleOrderTest(unittest.TestCase):
    """Configuration should read top to bottom as the lifecycle.

    A developer opens the config to answer 'what serves this phase, and can
    I swap it?'. A flat list in arbitrary order forces them to join modules
    to categories to phases by hand before they can even find the entry
    they want.
    """

    def test_the_config_template_is_ordered_by_phase(self) -> None:
        self.assertEqual(template_modules(), lifecycle_order())

    def test_the_config_schema_is_ordered_by_phase(self) -> None:
        self.assertEqual(schema_modules(), lifecycle_order())

    def test_both_files_group_modules_under_the_same_phases(self) -> None:
        template = load(CONFIG_TEMPLATE)["phases"]
        schema = load(CONFIG_SCHEMA)["properties"]["phases"]["properties"]

        self.assertEqual(list(template), list(schema))
        for phase, group in template.items():
            self.assertEqual(list(group), list(schema[phase]["properties"]))

    def test_the_first_and_last_entries_are_the_outer_phases(self) -> None:
        order = lifecycle_order()

        self.assertEqual(order[0], "project-memory")
        self.assertEqual(order[-1], "continuous-improvement")


class RegistryConfigConsistencyTest(unittest.TestCase):
    def test_every_registry_module_is_configurable(self) -> None:
        registry = {entry["name"] for entry in load(REGISTRY)["modules"]}

        self.assertEqual(
            registry,
            set(schema_modules()),
            "Registry modules and configurable modules must match exactly",
        )

    def test_configuration_schema_rejects_unknown_modules(self) -> None:
        phases = load(CONFIG_SCHEMA)["properties"]["phases"]

        self.assertFalse(phases["additionalProperties"])
        for group in phases["properties"].values():
            self.assertFalse(group["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
