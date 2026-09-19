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


class LifecycleOrderTest(unittest.TestCase):
    """Configuration should read top to bottom as the lifecycle.

    A developer opens the config to answer 'what serves this phase, and can
    I swap it?'. A flat list in arbitrary order forces them to join modules
    to categories to phases by hand before they can even find the entry
    they want.
    """

    def test_the_config_template_is_ordered_by_phase(self) -> None:
        template = load(CONFIG_TEMPLATE)

        self.assertEqual(list(template["modules"]), lifecycle_order())

    def test_the_config_schema_is_ordered_by_phase(self) -> None:
        schema = load(CONFIG_SCHEMA)

        self.assertEqual(
            list(schema["properties"]["modules"]["properties"]),
            lifecycle_order(),
        )

    def test_the_first_and_last_entries_are_the_outer_phases(self) -> None:
        order = lifecycle_order()

        self.assertEqual(order[0], "project-memory")
        self.assertEqual(order[-1], "continuous-improvement")


class RegistryConfigConsistencyTest(unittest.TestCase):
    def test_every_registry_module_is_configurable(self) -> None:
        registry = {entry["name"] for entry in load(REGISTRY)["modules"]}
        schema = set(
            load(CONFIG_SCHEMA)["properties"]["modules"]["properties"]
        )

        self.assertEqual(
            registry,
            schema,
            "Registry modules and configurable modules must match exactly",
        )

    def test_configuration_schema_rejects_unknown_modules(self) -> None:
        modules = load(CONFIG_SCHEMA)["properties"]["modules"]

        self.assertFalse(modules["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
