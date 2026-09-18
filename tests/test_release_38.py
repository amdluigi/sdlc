import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NEW_MODULES = ("incident-response", "release-launch")
NEW_CASES = {
    "incident-active-harm-positive",
    "incident-development-bug-negative",
    "incident-containment-counterexample",
    "incident-blameless-pressure",
    "release-launch-positive",
    "release-merged-not-published-negative",
    "release-rollback-counterexample",
    "release-deadline-pressure",
}


class Release38ContractTests(unittest.TestCase):
    def test_release_and_incident_modules_are_registered_and_default_enabled(self):
        registry = json.loads(
            (ROOT / "skills" / "sdlc" / "modules" / "registry.json").read_text(
                encoding="utf-8"
            )
        )
        names = [entry["name"] for entry in registry["modules"]]
        self.assertEqual(NEW_MODULES, tuple(names[5:7]))
        self.assertEqual(list(range(22)), [entry["order"] for entry in registry["modules"]])

        config = json.loads(
            (
                ROOT
                / "skills"
                / "sdlc"
                / "assets"
                / "sdlc-config.template.json"
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(all(config["modules"][name] for name in NEW_MODULES))

    def test_new_modules_have_all_behavioral_case_types(self):
        cases = json.loads(
            (ROOT / "evals" / "sdlc" / "cases.json").read_text(encoding="utf-8")
        )["cases"]
        case_ids = {case["id"] for case in cases}
        self.assertTrue(NEW_CASES.issubset(case_ids))
        for case in cases:
            if case["id"] in NEW_CASES:
                self.assertTrue(case["expected"])
                self.assertTrue(case["forbidden"])

    def test_evaluation_scorecard_and_host_qualification_policy_are_public(self):
        scorecard = ROOT / "evals" / "sdlc" / "SCORECARD.md"
        qualification = ROOT / "qualification" / "HOST-QUALIFICATION.md"
        self.assertTrue(scorecard.is_file())
        self.assertTrue(qualification.is_file())
        self.assertIn("control", scorecard.read_text(encoding="utf-8").lower())
        self.assertIn("experimental", qualification.read_text(encoding="utf-8").lower())
