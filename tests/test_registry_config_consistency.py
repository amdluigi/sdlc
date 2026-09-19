from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "skills" / "sdlc" / "modules" / "registry.json"
CONFIG_SCHEMA = (
    ROOT / "skills" / "sdlc" / "contracts" / "sdlc-config.schema.json"
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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
