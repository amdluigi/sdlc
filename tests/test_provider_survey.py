"""The control plane can report what serves each capability.

A developer could configure a replacement but could not see which provider
was connected, and was never told that an installed alternative existed.
The survey answers both questions without changing resolution: an
alternative is reported as a decision for the developer, never adopted.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "sdlc" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import capability_contract  # noqa: E402
import config_contract  # noqa: E402
import resolve_providers  # noqa: E402

from test_filesystem_providers import (  # noqa: E402
    capability_names,
    config,
    registry_modules,
    skill_document,
    write_provider,
)

SDLC_VERSION = "1.0.0"

REGISTRY_PATH = ROOT / "skills" / "sdlc" / "modules" / "registry.json"

SURVEY_SCHEMA = (
    ROOT / "skills" / "sdlc" / "contracts" / "provider-survey.schema.json"
)


def registry_categories() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["categories"]


def survey_from(root, project_config=None, roots=None):
    providers = capability_contract.FilesystemProviders(
        roots if roots is not None else [root],
        capabilities=capability_names(),
        reserved=capability_names() | {"sdlc"},
    )
    adapter = providers.adapter()
    return resolve_providers.survey(
        project_config if project_config is not None
        else {
            "schemaVersion": 3,
            "modules": {name: True for name in capability_names()},
            "extensions": {"project": {}, "global": {}},
            "measurement": {"enabled": False},
        },
        registry_modules(),
        adapter,
        SDLC_VERSION,
        host_profile="filesystem",
        skipped=providers.skipped,
        modes=providers.declared_modes(),
        categories=registry_categories(),
    )


def entry_for(document, capability):
    return next(
        row for row in document["capabilities"]
        if row["capability"] == capability
    )


class LifecyclePlacementTest(unittest.TestCase):
    """Where a capability is invoked must be visible, not inferred.

    A developer judging whether an installed skill is a better fit needs to
    know which phase the capability is invoked in and which categories share
    that phase. Requiring them to join the registry by hand is the reason
    placement was invisible.
    """

    def test_every_capability_reports_its_category_and_phase(self):
        categories = registry_categories()
        with tempfile.TemporaryDirectory() as temporary:
            document = survey_from(Path(temporary))
            for row, entry in zip(
                document["capabilities"], registry_modules()
            ):
                category = entry["category"]
                self.assertEqual(row["category"], category)
                self.assertEqual(
                    row["deliveryPhase"], categories[category]["deliveryPhase"]
                )
                self.assertEqual(
                    row["entryGate"], categories[category]["gate"]
                )

    def test_a_phase_outside_the_state_machine_reports_no_entry_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            document = survey_from(Path(temporary))
            row = entry_for(document, "project-memory")
            self.assertEqual(row["deliveryPhase"], "inception")
            self.assertIsNone(row["entryGate"])

    def test_placement_is_reported_even_when_a_provider_replaces(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root)
            document = survey_from(root, project_config=config())
            testing = entry_for(document, "testing")
            self.assertEqual(
                testing["active"],
                {"type": "replacement", "id": "acme-testing"},
            )
            self.assertEqual(testing["deliveryPhase"], "verification")
            self.assertEqual(testing["entryGate"], 5)

    def test_placement_is_omitted_when_the_registry_declares_no_categories(
        self,
    ):
        document = resolve_providers.survey(
            {
                "schemaVersion": 3,
                "modules": {name: True for name in capability_names()},
                "extensions": {"project": {}, "global": {}},
                "measurement": {"enabled": False},
            },
            registry_modules(),
            None,
            SDLC_VERSION,
            host_profile="filesystem",
        )
        for row in document["capabilities"]:
            self.assertIsNone(row["deliveryPhase"])
            self.assertIsNone(row["entryGate"])

    def test_a_provider_may_not_declare_its_own_lifecycle_placement(self):
        """Placement is the registry's, not the provider's.

        If a provider could name its phase it could claim a phase the
        control plane does not gate, escaping the evidence gate that governs
        the capability it replaces.
        """

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root, deliveryPhase="operate")
            document = survey_from(root)
            self.assertEqual(len(document["skipped"]), 1)
            self.assertEqual(
                entry_for(document, "testing")["alternatives"], []
            )


class SurveyContractTest(unittest.TestCase):
    """The published contract must match what the survey emits.

    Nothing in this repository validates a document against a schema at
    runtime, so a schema can drift from its producer silently. Bind the two
    by key here, because a field that exists only in one of them is the
    failure a reader would hit.
    """

    def schema(self) -> dict:
        return json.loads(SURVEY_SCHEMA.read_text(encoding="utf-8"))

    def test_the_schema_is_published_beside_the_other_contracts(self):
        self.assertTrue(SURVEY_SCHEMA.is_file())
        self.assertEqual(self.schema()["$id"], "urn:sdlc:provider-survey:1")

    def test_the_document_keys_match_the_schema(self):
        schema = self.schema()
        with tempfile.TemporaryDirectory() as temporary:
            document = survey_from(Path(temporary))

        self.assertEqual(
            sorted(document), sorted(schema["properties"])
        )
        self.assertEqual(
            sorted(document), sorted(schema["required"])
        )

    def test_the_capability_keys_match_the_schema(self):
        capability = self.schema()["$defs"]["capability"]
        with tempfile.TemporaryDirectory() as temporary:
            document = survey_from(Path(temporary))

        for row in document["capabilities"]:
            self.assertEqual(sorted(row), sorted(capability["properties"]))
            self.assertEqual(sorted(row), sorted(capability["required"]))

    def test_the_schema_admits_every_decision_the_survey_emits(self):
        allowed = set(
            self.schema()["$defs"]["capability"]["properties"]["decision"][
                "enum"
            ]
        )
        emitted = set()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root)
            write_provider(
                root,
                name="acme-review",
                capability="review",
                evaluations=True,
            )
            document = survey_from(root)
            emitted.update(
                row["decision"] for row in document["capabilities"]
            )

        self.assertEqual(
            emitted,
            {"settled", "developer-choice-required", "refused"},
        )
        self.assertTrue(emitted <= allowed)

    def test_the_schema_admits_every_alternative_key_emitted(self):
        alternative = self.schema()["$defs"]["alternative"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root)
            write_provider(
                root,
                name="acme-review",
                capability="review",
                evaluations=True,
            )
            document = survey_from(root)
            seen = [
                key
                for row in document["capabilities"]
                for item in row["alternatives"]
                for key in item
            ]

        self.assertTrue(seen)
        self.assertTrue(set(seen) <= set(alternative["properties"]))


class ConnectedProviderTest(unittest.TestCase):
    def test_every_capability_reports_a_connected_provider(self):
        with tempfile.TemporaryDirectory() as temporary:
            document = survey_from(Path(temporary))
            names = [row["capability"] for row in document["capabilities"]]
            self.assertEqual(
                names, [entry["name"] for entry in registry_modules()]
            )
            for row in document["capabilities"]:
                self.assertEqual(row["active"], {"type": "bundled"})
                self.assertEqual(row["decision"], "settled")

    def test_a_configured_replacement_is_reported_as_connected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root)
            document = survey_from(root, project_config=config())
            testing = entry_for(document, "testing")
            self.assertEqual(
                testing["active"],
                {"type": "replacement", "id": "acme-testing"},
            )
            self.assertEqual(testing["decision"], "settled")
            self.assertEqual(testing["alternatives"], [])

    def test_a_disabled_capability_reports_its_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            modules = {name: True for name in capability_names()}
            modules["prd"] = False
            document = survey_from(
                Path(temporary),
                project_config={
                    "schemaVersion": 3,
                    "modules": modules,
                    "extensions": {"project": {}, "global": {}},
                    "measurement": {"enabled": False},
                },
            )
            self.assertEqual(entry_for(document, "prd")["state"], "disabled")
            self.assertEqual(
                entry_for(document, "testing")["state"], "enabled"
            )


class DeveloperChoiceTest(unittest.TestCase):
    def test_an_unconfigured_alternative_becomes_a_developer_choice(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root)
            document = survey_from(root)
            testing = entry_for(document, "testing")
            self.assertEqual(testing["active"], {"type": "bundled"})
            self.assertEqual(
                testing["decision"], "developer-choice-required"
            )
            self.assertEqual(
                testing["alternatives"],
                [{"id": "acme-testing", "mode": "replace", "eligible": True}],
            )
            self.assertEqual(document["choicesRequired"], ["testing"])

    def test_an_alternative_is_never_adopted_by_the_survey(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root)
            providers = capability_contract.FilesystemProviders(
                [root],
                capabilities=capability_names(),
                reserved=capability_names() | {"sdlc"},
            )
            plain = {
                "schemaVersion": 3,
                "modules": {name: True for name in capability_names()},
                "extensions": {"project": {}, "global": {}},
                "measurement": {"enabled": False},
            }
            resolution = resolve_providers.resolve(
                plain, registry_modules(), providers.adapter(),
                SDLC_VERSION, "filesystem",
            )
            self.assertEqual(resolution["providers"], {})

    def test_two_alternatives_are_both_offered(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root, name="acme-testing")
            write_provider(
                root,
                name="beta-testing",
                instructions=skill_document(name="beta-testing"),
            )
            document = survey_from(root)
            testing = entry_for(document, "testing")
            self.assertEqual(
                [item["id"] for item in testing["alternatives"]],
                ["acme-testing", "beta-testing"],
            )
            self.assertEqual(
                testing["decision"], "developer-choice-required"
            )

    def test_an_incompatible_alternative_is_reported_ineligible(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(
                root,
                compatibleSdlc=">=9.0.0 <10.0.0",
                instructions=skill_document(compatible=">=9.0.0 <10.0.0"),
            )
            document = survey_from(root)
            testing = entry_for(document, "testing")
            self.assertEqual(
                testing["alternatives"],
                [
                    {
                        "id": "acme-testing",
                        "mode": "replace",
                        "eligible": False,
                        "reason": "provider-incompatible",
                    }
                ],
            )
            self.assertEqual(testing["decision"], "settled")
            self.assertEqual(document["choicesRequired"], [])

    def test_an_augmenting_alternative_is_offered_without_displacing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root, mode="augment", evaluations=False)
            document = survey_from(root)
            testing = entry_for(document, "testing")
            self.assertEqual(testing["active"], {"type": "bundled"})
            self.assertEqual(
                testing["alternatives"][0]["mode"], "augment"
            )


def shortlist_config(shortlist=("acme-a", "acme-b")) -> dict:
    modules = {name: True for name in capability_names()}
    modules["testing"] = {"replaceWith": list(shortlist)}
    return {
        "schemaVersion": 3,
        "modules": modules,
        "extensions": {"project": {}, "global": {}},
        "measurement": {"enabled": False},
    }


class CandidateShortlistSurveyTest(unittest.TestCase):
    """A configured replaceWith shortlist is reported as settled or tied."""

    def test_the_only_installed_candidate_settles_the_shortlist(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root, name="acme-a", instructions=skill_document(
                name="acme-a"
            ))
            document = survey_from(root, project_config=shortlist_config())
            testing = entry_for(document, "testing")
            self.assertEqual(
                testing["active"], {"type": "replacement", "id": "acme-a"}
            )
            self.assertEqual(testing["decision"], "settled")
            self.assertEqual(testing["alternatives"], [])
            self.assertEqual(document["choicesRequired"], [])

    def test_no_installed_candidate_remains_a_developer_choice(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            document = survey_from(root, project_config=shortlist_config())
            testing = entry_for(document, "testing")
            self.assertEqual(
                testing["active"],
                {"type": "replacement", "candidates": ["acme-a", "acme-b"]},
            )
            self.assertEqual(
                testing["decision"], "developer-choice-required"
            )
            self.assertIn("testing", document["choicesRequired"])
            self.assertEqual(testing["alternatives"], [])

    def test_two_installed_candidates_are_both_offered_and_tied(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root, name="acme-a", instructions=skill_document(
                name="acme-a"
            ))
            write_provider(root, name="acme-b", instructions=skill_document(
                name="acme-b"
            ))
            document = survey_from(root, project_config=shortlist_config())
            testing = entry_for(document, "testing")
            self.assertEqual(
                testing["active"],
                {"type": "replacement", "candidates": ["acme-a", "acme-b"]},
            )
            self.assertEqual(
                testing["decision"], "developer-choice-required"
            )
            self.assertEqual(
                [item["id"] for item in testing["alternatives"]],
                ["acme-a", "acme-b"],
            )
            self.assertTrue(
                all(item["eligible"] for item in testing["alternatives"])
            )

    def test_an_installed_provider_outside_the_shortlist_is_not_offered(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root, name="acme-a", instructions=skill_document(
                name="acme-a"
            ))
            write_provider(
                root, name="unlisted-testing",
                instructions=skill_document(name="unlisted-testing"),
            )
            document = survey_from(root, project_config=shortlist_config())
            testing = entry_for(document, "testing")
            self.assertEqual(
                testing["active"], {"type": "replacement", "id": "acme-a"}
            )
            self.assertEqual(testing["alternatives"], [])


class NonDelegatableSurveyTest(unittest.TestCase):
    def test_an_alternative_for_a_protected_capability_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(
                root,
                name="acme-review",
                capability="review",
                instructions=skill_document(
                    name="acme-review", capability="review"
                ),
            )
            document = survey_from(root)
            review = entry_for(document, "review")
            self.assertFalse(review["replaceable"])
            self.assertEqual(review["decision"], "refused")
            self.assertEqual(
                review["alternatives"],
                [
                    {
                        "id": "acme-review",
                        "mode": "replace",
                        "eligible": False,
                        "reason": "capability-non-delegatable",
                    }
                ],
            )
            self.assertEqual(document["choicesRequired"], [])


class ExplicitDecisionTest(unittest.TestCase):
    def test_an_explicit_bundled_choice_stops_the_question(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root)
            modules = {name: True for name in capability_names()}
            modules["testing"] = {"provider": "bundled"}
            document = survey_from(
                root,
                project_config={
                    "schemaVersion": 3,
                    "modules": modules,
                    "extensions": {"project": {}, "global": {}},
                    "measurement": {"enabled": False},
                },
            )
            testing = entry_for(document, "testing")
            self.assertEqual(testing["active"], {"type": "bundled"})
            self.assertTrue(testing["explicit"])
            self.assertEqual(testing["decision"], "settled")
            self.assertEqual(document["choicesRequired"], [])
            self.assertEqual(
                [item["id"] for item in testing["alternatives"]],
                ["acme-testing"],
            )

    def test_the_default_true_is_not_an_explicit_decision(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root)
            document = survey_from(root)
            self.assertFalse(entry_for(document, "testing")["explicit"])

    def test_an_explicit_bundled_choice_normalizes(self):
        names = capability_names()
        modules = {name: True for name in names}
        modules["testing"] = {"provider": "bundled"}
        normalized = config_contract.normalize_config(
            {
                "schemaVersion": 3,
                "modules": modules,
                "extensions": {"project": {}, "global": {}},
                "measurement": {"enabled": False},
            },
            names,
        )
        self.assertEqual(
            normalized["modules"]["testing"], {"provider": "bundled"}
        )

    def test_an_explicit_bundled_choice_resolves_no_provider(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root)
            names = capability_names()
            modules = {name: True for name in names}
            modules["testing"] = {"provider": "bundled"}
            providers = capability_contract.FilesystemProviders(
                [root], capabilities=names, reserved=names | {"sdlc"}
            )
            resolution = resolve_providers.resolve(
                {
                    "schemaVersion": 3,
                    "modules": modules,
                    "extensions": {"project": {}, "global": {}},
                    "measurement": {"enabled": False},
                },
                registry_modules(),
                providers.adapter(),
                SDLC_VERSION,
                "filesystem",
            )
            self.assertEqual(resolution["providers"], {})
            self.assertEqual(
                resolve_providers.module_provider(
                    {"modules": modules}, "testing"
                ),
                {"type": "bundled", "id": None},
            )

    def test_a_protected_capability_still_refuses_an_object(self):
        names = capability_names()
        modules = {name: True for name in names}
        modules["review"] = {"provider": "bundled"}
        with self.assertRaises(config_contract.ConfigError):
            config_contract.normalize_config(
                {
                    "schemaVersion": 3,
                    "modules": modules,
                    "extensions": {"project": {}, "global": {}},
                    "measurement": {"enabled": False},
                },
                names,
            )

    def test_an_unknown_provider_keyword_is_refused(self):
        names = capability_names()
        modules = {name: True for name in names}
        modules["testing"] = {"provider": "acme-testing"}
        with self.assertRaises(config_contract.ConfigError):
            config_contract.normalize_config(
                {
                    "schemaVersion": 3,
                    "modules": modules,
                    "extensions": {"project": {}, "global": {}},
                    "measurement": {"enabled": False},
                },
                names,
            )


class VisibilityTest(unittest.TestCase):
    def test_a_malformed_alternative_is_reported_not_hidden(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            broken = root / "broken"
            broken.mkdir()
            (broken / capability_contract.DECLARATION_FILENAME).write_text(
                "{ not json", encoding="utf-8", newline="\n"
            )
            document = survey_from(root)
            self.assertEqual(len(document["skipped"]), 1)
            self.assertIn("broken", document["skipped"][0]["path"])

    def test_the_survey_runs_without_any_provider_root(self):
        document = resolve_providers.survey(
            {
                "schemaVersion": 3,
                "modules": {name: True for name in capability_names()},
                "extensions": {"project": {}, "global": {}},
                "measurement": {"enabled": False},
            },
            registry_modules(),
            None,
            SDLC_VERSION,
        )
        self.assertEqual(document["choicesRequired"], [])
        self.assertEqual(document["skipped"], [])
        self.assertEqual(
            len(document["capabilities"]), len(registry_modules())
        )


if __name__ == "__main__":
    unittest.main()
