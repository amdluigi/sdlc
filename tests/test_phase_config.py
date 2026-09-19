"""The project configuration is shaped by delivery phase."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "sdlc" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import config_contract  # noqa: E402

REGISTRY = json.loads(
    (ROOT / "skills" / "sdlc" / "modules" / "registry.json").read_text(
        encoding="utf-8"
    )
)
TEMPLATE = json.loads(
    (ROOT / "skills" / "sdlc" / "assets" / "sdlc-config.template.json").read_text(
        encoding="utf-8"
    )
)


def phase_of():
    return config_contract.phase_index(REGISTRY)


class PhaseIndexTest(unittest.TestCase):
    def test_orders_modules_by_lifecycle(self):
        index = phase_of()
        self.assertEqual(
            list(index)[:4],
            ["project-memory", "project-standards", "prd", "planning"],
        )
        self.assertEqual(index["project-memory"], "inception")
        self.assertEqual(index["testing"], "verification")
        self.assertEqual(index["continuous-improvement"], "operate")

    def test_covers_every_registered_module(self):
        index = phase_of()
        names = {module["name"] for module in REGISTRY["modules"]}
        self.assertEqual(set(index), names)

    def test_groups_appear_in_delivery_phase_order(self):
        index = phase_of()
        seen = []
        for phase in index.values():
            if phase not in seen:
                seen.append(phase)
        self.assertEqual(seen, REGISTRY["deliveryPhases"])


class PhaseConfigReadTest(unittest.TestCase):
    def test_accepts_a_phase_shaped_config(self):
        config = {
            "schemaVersion": 4,
            "phases": {
                "inception": {"project-memory": False},
                "verification": {"testing": True},
            },
            "extensions": {"project": {}, "global": {}},
            "measurement": {"enabled": False},
        }
        normalized = config_contract.normalize_config(
            config, set(phase_of()), phase_of()
        )
        self.assertEqual(normalized["modules"]["project-memory"], False)
        self.assertEqual(normalized["modules"]["testing"], True)

    def test_rejects_a_module_placed_in_the_wrong_phase(self):
        config = {
            "schemaVersion": 4,
            "phases": {"operate": {"testing": True}},
            "extensions": {"project": {}, "global": {}},
            "measurement": {"enabled": False},
        }
        with self.assertRaises(config_contract.ConfigError) as caught:
            config_contract.normalize_config(config, set(phase_of()), phase_of())
        self.assertIn("verification", str(caught.exception))

    def test_rejects_an_unknown_phase(self):
        config = {
            "schemaVersion": 4,
            "phases": {"deployment": {}},
            "extensions": {"project": {}, "global": {}},
            "measurement": {"enabled": False},
        }
        with self.assertRaises(config_contract.ConfigError):
            config_contract.normalize_config(config, set(phase_of()), phase_of())

    def test_accepts_a_replacement_under_the_phase_shape(self):
        config = {
            "schemaVersion": 4,
            "phases": {"verification": {"testing": {"replaceWith": "acme"}}},
            "extensions": {"project": {}, "global": {}},
            "measurement": {"enabled": False},
        }
        normalized = config_contract.normalize_config(
            config, set(phase_of()), phase_of()
        )
        self.assertEqual(
            normalized["modules"]["testing"], {"replaceWith": "acme"}
        )

    def test_still_refuses_to_delegate_a_judgment_module(self):
        config = {
            "schemaVersion": 4,
            "phases": {"verification": {"review": {"replaceWith": "acme"}}},
            "extensions": {"project": {}, "global": {}},
            "measurement": {"enabled": False},
        }
        with self.assertRaises(config_contract.ConfigError):
            config_contract.normalize_config(config, set(phase_of()), phase_of())


class PhaseConfigWriteTest(unittest.TestCase):
    def test_renders_the_document_grouped_by_phase(self):
        normalized = config_contract.normalize_config(
            {"schemaVersion": 1, "modules": {}}, set(phase_of())
        )
        document = config_contract.config_to_document(normalized, phase_of())
        self.assertEqual(document["schemaVersion"], 4)
        self.assertNotIn("modules", document)
        self.assertEqual(
            list(document["phases"]), REGISTRY["deliveryPhases"]
        )
        self.assertEqual(
            list(document["phases"]["inception"]),
            ["project-memory", "project-standards", "prd", "planning"],
        )

    def test_keeps_the_flat_document_without_a_phase_index(self):
        normalized = config_contract.normalize_config(
            {"schemaVersion": 1, "modules": {}}, {"testing"}
        )
        document = config_contract.config_to_document(normalized)
        self.assertEqual(document["schemaVersion"], 3)
        self.assertIn("modules", document)

    def test_round_trips_through_the_phase_shape(self):
        normalized = config_contract.normalize_config(
            {
                "schemaVersion": 3,
                "modules": {"testing": {"replaceWith": "acme"}},
                "extensions": {"project": {}, "global": {}},
                "measurement": {"enabled": False},
            },
            set(phase_of()),
        )
        document = config_contract.config_to_document(normalized, phase_of())
        again = config_contract.normalize_config(
            document, set(phase_of()), phase_of()
        )
        self.assertEqual(again, normalized)


class PhaseConfigMigrationTest(unittest.TestCase):
    def test_migrates_a_flat_config_on_disk(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / ".sdlc").mkdir()
            path = root / ".sdlc" / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 3,
                        "modules": {"testing": True},
                        "extensions": {"project": {}, "global": {}},
                        "measurement": {"enabled": False},
                    }
                ),
                encoding="utf-8",
            )
            config_contract.load_project_config(
                root, set(phase_of()), phase_of()
            )
            written = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(written["schemaVersion"], 4)
        self.assertEqual(list(written["phases"]), REGISTRY["deliveryPhases"])

    def test_does_not_rewrite_an_already_migrated_config(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / ".sdlc").mkdir()
            path = root / ".sdlc" / "config.json"
            config_contract.load_project_config(
                root, set(phase_of()), phase_of()
            )
            path.write_text(
                json.dumps(
                    config_contract.config_to_document(
                        config_contract.normalize_config(
                            {"schemaVersion": 1, "modules": {}}, set(phase_of())
                        ),
                        phase_of(),
                    ),
                    indent=2,
                ),
                encoding="utf-8",
            )
            before = path.stat().st_mtime_ns
            config_contract.load_project_config(
                root, set(phase_of()), phase_of()
            )
            after = path.stat().st_mtime_ns
        self.assertEqual(before, after)


class PhaseTemplateTest(unittest.TestCase):
    def test_template_is_phase_shaped(self):
        self.assertEqual(TEMPLATE["schemaVersion"], 4)
        self.assertEqual(list(TEMPLATE["phases"]), REGISTRY["deliveryPhases"])

    def test_template_enables_every_module_in_its_own_phase(self):
        index = phase_of()
        flat = {}
        for phase, group in TEMPLATE["phases"].items():
            for name, value in group.items():
                self.assertEqual(index[name], phase)
                flat[name] = value
        self.assertEqual(set(flat), set(index))
        self.assertTrue(all(value is True for value in flat.values()))


if __name__ == "__main__":
    unittest.main()
