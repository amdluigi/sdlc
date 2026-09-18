import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "repository_validate", ROOT / "scripts" / "validate.py"
)
repository_validate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(repository_validate)

DOMAIN_MODULES = (
    "accessibility-browser",
    "performance-concurrency",
    "observability",
    "api-compatibility",
    "data-migration",
    "dependency-supply-chain",
)
DOMAIN_CASE_IDS = {
    "a11y-browser-dialog-flow-positive",
    "a11y-browser-backend-only-negative",
    "a11y-browser-email-counterexample",
    "a11y-browser-release-pressure",
    "perf-cache-hot-path-positive",
    "perf-cold-refactor-negative",
    "perf-test-parallelism-counterexample",
    "perf-racy-deadline-pressure",
    "obs-queue-boundary-positive",
    "obs-pure-library-negative",
    "obs-existing-rollout-signals-counterexample",
    "obs-log-everything-pressure",
    "api-error-shape-positive",
    "api-private-helper-negative",
    "api-storage-schema-counterexample",
    "api-breaking-deadline-pressure",
    "migration-live-backfill-positive",
    "migration-test-fixture-negative",
    "migration-additive-column-counterexample",
    "migration-destructive-pressure",
    "supply-new-package-positive",
    "supply-existing-import-negative",
    "supply-first-party-counterexample",
    "supply-emergency-update-pressure",
}


class Release32ContractTests(unittest.TestCase):
    def test_validator_requires_every_release_32_behavioral_case(self):
        repository_validate.validate_release_32_case_coverage(DOMAIN_CASE_IDS)

        with self.assertRaisesRegex(
            ValueError,
            "Release 3.2 domain-module evaluation coverage is incomplete",
        ):
            repository_validate.validate_release_32_case_coverage(
                DOMAIN_CASE_IDS - {"supply-emergency-update-pressure"}
            )

    def test_registry_places_domain_modules_contiguously_before_tdd(self):
        registry = json.loads(
            (ROOT / "skills" / "sdlc" / "modules" / "registry.json").read_text(
                encoding="utf-8"
            )
        )
        names = [entry["name"] for entry in registry["modules"]]

        self.assertEqual(list(DOMAIN_MODULES), names[8:14])
        self.assertEqual("tdd", names[14])
        self.assertEqual(list(range(22)), [entry["order"] for entry in registry["modules"]])

    def test_evaluation_suite_contains_four_contract_types_per_domain_module(self):
        evaluations = json.loads(
            (ROOT / "evals" / "sdlc" / "cases.json").read_text(encoding="utf-8")
        )
        cases = {case["id"]: case for case in evaluations["cases"]}

        self.assertEqual(set(), DOMAIN_CASE_IDS - set(cases))
        for case_id in DOMAIN_CASE_IDS:
            self.assertTrue(cases[case_id]["expected"])
            self.assertTrue(cases[case_id]["forbidden"])

    def test_validator_enforces_domain_module_instruction_contract(self):
        module_path = (
            ROOT
            / "skills"
            / "sdlc"
            / "modules"
            / "accessibility-browser"
            / "MODULE.md"
        )
        text = module_path.read_text(encoding="utf-8")
        expected_cases = {
            case_id
            for case_id in DOMAIN_CASE_IDS
            if case_id.startswith("a11y-browser-")
        }

        repository_validate.validate_domain_module_contract(
            "accessibility-browser", text, expected_cases
        )
        with self.assertRaisesRegex(
            ValueError,
            "Domain module accessibility-browser is missing section: Exit",
        ):
            repository_validate.validate_domain_module_contract(
                "accessibility-browser",
                text.replace("## Exit", "## Removed", 1),
                expected_cases,
            )

    def test_new_modules_default_enabled_and_preserve_explicit_opt_out(self):
        registry_names = set(DOMAIN_MODULES) | {"testing"}

        upgraded = repository_validate.adaptive_extensions.normalize_config(
            {"schemaVersion": 1, "modules": {"testing": False}},
            registry_names,
        )
        self.assertFalse(upgraded["modules"]["testing"])
        self.assertTrue(all(upgraded["modules"][name] for name in DOMAIN_MODULES))

        explicit = repository_validate.adaptive_extensions.normalize_config(
            {
                "schemaVersion": 2,
                "modules": {name: False for name in DOMAIN_MODULES},
                "extensions": {"project": {}, "global": {}},
            },
            registry_names,
        )
        self.assertTrue(all(not explicit["modules"][name] for name in DOMAIN_MODULES))

        with self.assertRaisesRegex(
            repository_validate.adaptive_extensions.AdaptiveError,
            "modules.accessibility-browser must be boolean",
        ):
            repository_validate.adaptive_extensions.normalize_config(
                {
                    "schemaVersion": 2,
                    "modules": {"accessibility-browser": "yes"},
                    "extensions": {"project": {}, "global": {}},
                },
                registry_names,
            )

    def test_supply_chain_contract_requires_inspectable_advisory_freshness(self):
        registry = json.loads(
            (ROOT / "skills" / "sdlc" / "modules" / "registry.json").read_text(
                encoding="utf-8"
            )
        )
        supply_chain = next(
            entry
            for entry in registry["modules"]
            if entry["name"] == "dependency-supply-chain"
        )
        registry_evidence = " ".join(supply_chain["evidence"]).lower()
        module_text = (
            ROOT
            / "skills"
            / "sdlc"
            / "modules"
            / "dependency-supply-chain"
            / "MODULE.md"
        ).read_text(encoding="utf-8").lower()

        for text in (registry_evidence, module_text):
            text = " ".join(text.split())
            self.assertIn("result time", text)
            self.assertIn("advisory-database identity", text)
            self.assertIn("advisory-database changes", text)


if __name__ == "__main__":
    unittest.main()
