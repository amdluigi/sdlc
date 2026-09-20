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


class ReplaceWithShortlistTest(unittest.TestCase):
    """replaceWith accepts an undecided shortlist of candidate providers."""

    def config(self, testing):
        return {
            "schemaVersion": 4,
            "phases": {"verification": {"testing": testing}},
            "extensions": {"project": {}, "global": {}},
            "measurement": {"enabled": False},
        }

    def normalize(self, testing):
        return config_contract.normalize_config(
            self.config(testing), set(phase_of()), phase_of()
        )

    def test_accepts_a_shortlist_of_two_or_more_candidates(self):
        normalized = self.normalize({"replaceWith": ["acme-a", "acme-b"]})
        self.assertEqual(
            normalized["modules"]["testing"],
            {"replaceWith": ["acme-a", "acme-b"]},
        )

    def test_rejects_a_shortlist_with_only_one_candidate(self):
        with self.assertRaises(config_contract.ConfigError) as caught:
            self.normalize({"replaceWith": ["acme-a"]})
        self.assertIn("two or more", str(caught.exception))

    def test_rejects_a_shortlist_with_a_repeated_candidate(self):
        with self.assertRaises(config_contract.ConfigError) as caught:
            self.normalize({"replaceWith": ["acme-a", "acme-a"]})
        self.assertIn("repeats candidate", str(caught.exception))

    def test_rejects_a_shortlist_with_a_malformed_candidate(self):
        with self.assertRaises(config_contract.ConfigError):
            self.normalize({"replaceWith": ["acme-a", "Not_Kebab"]})

    def test_rejects_a_shortlist_member_that_creates_a_provider_cycle(self):
        with self.assertRaises(config_contract.ConfigError) as caught:
            self.normalize({"replaceWith": ["acme-a", "review"]})
        self.assertIn("provider cycle", str(caught.exception))

    def test_rejects_a_shortlist_member_already_assigned_elsewhere(self):
        config = {
            "schemaVersion": 4,
            "phases": {
                "verification": {
                    "testing": {"replaceWith": ["acme-a", "acme-b"]},
                    "review": True,
                },
                "triage": {"debugging": {"replaceWith": "acme-a"}},
            },
            "extensions": {"project": {}, "global": {}},
            "measurement": {"enabled": False},
        }
        with self.assertRaises(config_contract.ConfigError) as caught:
            config_contract.normalize_config(
                config, set(phase_of()), phase_of()
            )
        self.assertIn("assigned to both", str(caught.exception))


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

    def test_template_disables_evaluation_by_default(self):
        self.assertEqual(TEMPLATE["evaluation"], {"enabled": False})


class EvaluationConfigTest(unittest.TestCase):
    """evaluation.enabled gates the sdlc-evaluator run-record capture,
    independent of measurement.enabled."""

    def config(self, **overrides) -> dict:
        base = {
            "schemaVersion": 3,
            "modules": {},
            "extensions": {"project": {}, "global": {}},
            "measurement": {"enabled": False},
        }
        base.update(overrides)
        return base

    def test_defaults_to_disabled_when_absent(self):
        normalized = config_contract.normalize_config(
            self.config(), set(phase_of())
        )
        self.assertEqual(normalized["evaluation"], {"enabled": False})

    def test_accepts_an_explicit_enabled_flag(self):
        normalized = config_contract.normalize_config(
            self.config(evaluation={"enabled": True}), set(phase_of())
        )
        self.assertEqual(normalized["evaluation"], {"enabled": True})

    def test_rejects_a_non_boolean_enabled_value(self):
        with self.assertRaises(config_contract.ConfigError) as caught:
            config_contract.normalize_config(
                self.config(evaluation={"enabled": "yes"}), set(phase_of())
            )
        self.assertIn("evaluation.enabled must be boolean", str(caught.exception))

    def test_rejects_an_unknown_evaluation_field(self):
        with self.assertRaises(config_contract.ConfigError) as caught:
            config_contract.normalize_config(
                self.config(evaluation={"enabled": True, "window": 30}),
                set(phase_of()),
            )
        self.assertIn("unknown evaluation field", str(caught.exception))

    def test_is_independent_of_measurement(self):
        normalized = config_contract.normalize_config(
            self.config(
                measurement={"enabled": True}, evaluation={"enabled": False}
            ),
            set(phase_of()),
        )
        self.assertEqual(normalized["measurement"], {"enabled": True})
        self.assertEqual(normalized["evaluation"], {"enabled": False})

    def test_round_trips_through_the_phase_shape(self):
        normalized = config_contract.normalize_config(
            self.config(evaluation={"enabled": True}), set(phase_of())
        )
        document = config_contract.config_to_document(normalized, phase_of())
        self.assertEqual(document["evaluation"], {"enabled": True})
        again = config_contract.normalize_config(
            document, set(phase_of()), phase_of()
        )
        self.assertEqual(again["evaluation"], {"enabled": True})


if __name__ == "__main__":
    unittest.main()
