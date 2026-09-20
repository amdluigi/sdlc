"""A third-party skill on disk can serve a capability end to end.

Replacement providers have been unreachable because resolution required a
host adapter no host is recorded as implementing. These tests exercise the
filesystem path with no host adapter at all, and assert that every existing
guarantee still holds along it.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "skills" / "sdlc" / "modules" / "registry.json"
sys.path.insert(0, str(ROOT / "skills" / "sdlc" / "scripts"))

import capability_contract  # noqa: E402
import resolve_providers  # noqa: E402


def skill_document(name="acme-testing", capability="testing",
                   compatible=">=1.0.0 <2.0.0", body="Run the acme suite.\n"):
    return (
        "---\n"
        f"name: {name}\n"
        "description: Replacement testing capability for acme projects.\n"
        "metadata:\n"
        '  sdlc-provider-schema: "1"\n'
        f'  sdlc-compatible: "{compatible}"\n'
        f'  sdlc-modules: "{capability}"\n'
        "---\n"
        f"\n# Acme testing\n\n{body}"
    )


INSTRUCTIONS = skill_document()


def registry_modules() -> list:
    return capability_contract.load_registry(REGISTRY)["modules"]


def capability_names() -> set:
    return {entry["name"] for entry in registry_modules()}


def declaration(**overrides) -> dict:
    value = {
        "schemaVersion": 1,
        "id": "acme-testing",
        "capability": "testing",
        "mode": "replace",
        "instructions": "SKILL.md",
        "trigger": "When behavior changes.",
        "exitSignal": "The acme suite passes.",
        "evidence": ["The acme suite reported a result for the change."],
        "evaluations": "evals.json",
        "compatibleSdlc": ">=1.0.0 <2.0.0",
    }
    value.update(overrides)
    for key, item in list(value.items()):
        if item is None:
            del value[key]
    return value


def write_provider(root: Path, name="acme-testing", instructions=INSTRUCTIONS,
                   evaluations=True, **overrides) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    (directory / capability_contract.DECLARATION_FILENAME).write_text(
        json.dumps(declaration(id=name, **overrides)),
        encoding="utf-8",
        newline="\n",
    )
    if instructions is not None:
        (directory / "SKILL.md").write_text(
            instructions, encoding="utf-8", newline="\n"
        )
    if evaluations:
        (directory / "evals.json").write_text(
            json.dumps({"schemaVersion": 1, "cases": []}),
            encoding="utf-8",
            newline="\n",
        )
    return directory


def config(module="testing", provider="acme-testing") -> dict:
    modules = {name: True for name in capability_names()}
    modules[module] = {"replaceWith": provider}
    return {
        "schemaVersion": 3,
        "modules": modules,
        "extensions": {"project": {}, "global": {}},
        "measurement": {"enabled": False},
    }


ORCHESTRATION_CONTEXT = {
    "changeContract": "Replace the testing capability for this change.",
    "projectStandards": "Acme standards apply.",
    "projectMemory": "No prior acme decisions recorded.",
}


class DiscoveryTest(unittest.TestCase):
    def test_a_declared_provider_is_enumerated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root)
            adapter = capability_contract.FilesystemProviders(
                [root], capabilities=capability_names()
            ).adapter()
            self.assertEqual(adapter["hostProfile"], "filesystem")
            self.assertEqual(len(adapter["candidates"]), 1)
            candidate = adapter["candidates"][0]
            self.assertEqual(candidate["declaredName"], "acme-testing")
            self.assertEqual(
                candidate["contentDigest"],
                "sha256:"
                + hashlib.sha256(INSTRUCTIONS.encode("utf-8")).hexdigest(),
            )
            self.assertEqual(
                candidate["providerMetadata"]["sdlc-modules"], "testing"
            )

    def test_a_malformed_provider_is_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            broken = root / "broken-provider"
            broken.mkdir()
            (broken / capability_contract.DECLARATION_FILENAME).write_text(
                "{ not json", encoding="utf-8", newline="\n"
            )
            write_provider(root)
            providers = capability_contract.FilesystemProviders(
                [root], capabilities=capability_names()
            )
            adapter = providers.adapter()
            self.assertEqual(len(adapter["candidates"]), 1)
            self.assertEqual(len(providers.skipped), 1)
            self.assertIn("broken-provider", providers.skipped[0]["path"])

    def test_a_replacing_provider_without_evaluations_is_skipped(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root, evaluations=False)
            providers = capability_contract.FilesystemProviders(
                [root], capabilities=capability_names()
            )
            self.assertEqual(providers.adapter()["candidates"], [])
            self.assertIn("evaluations", providers.skipped[0]["reason"])

    def test_missing_instructions_are_skipped(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root, instructions=None)
            providers = capability_contract.FilesystemProviders(
                [root], capabilities=capability_names()
            )
            self.assertEqual(providers.adapter()["candidates"], [])

    def test_a_provider_may_not_claim_a_core_capability_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root, name="testing")
            names = capability_names()
            providers = capability_contract.FilesystemProviders(
                [root], capabilities=names, reserved=names | {"sdlc"}
            )
            self.assertEqual(providers.adapter()["candidates"], [])
            self.assertIn("reserved", providers.skipped[0]["reason"])

    def test_a_provider_may_not_claim_the_bundle_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root, name="sdlc")
            names = capability_names()
            providers = capability_contract.FilesystemProviders(
                [root], capabilities=names, reserved=names | {"sdlc"}
            )
            self.assertEqual(providers.adapter()["candidates"], [])

    def test_only_the_bundle_may_declare_mode_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root, mode="default", evaluations=False)
            providers = capability_contract.FilesystemProviders(
                [root], capabilities=capability_names()
            )
            self.assertEqual(providers.adapter()["candidates"], [])
            self.assertIn("mode default", providers.skipped[0]["reason"])

    def test_a_domain_scoped_provider_declaring_a_known_domain_is_enumerated(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root, appliesTo=["mobile"])
            providers = capability_contract.FilesystemProviders(
                [root],
                capabilities=capability_names(),
                domains={"web", "mobile", "desktop"},
            )
            self.assertEqual(len(providers.adapter()["candidates"]), 1)
            self.assertEqual(providers.skipped, [])

    def test_a_provider_declaring_an_unknown_domain_is_skipped(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root, appliesTo=["quantum"])
            providers = capability_contract.FilesystemProviders(
                [root],
                capabilities=capability_names(),
                domains={"web", "mobile", "desktop"},
            )
            self.assertEqual(providers.adapter()["candidates"], [])
            self.assertIn("domain", providers.skipped[0]["reason"])

    def test_a_domain_scoped_declaration_without_a_known_domain_set_is_not_checked(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root, appliesTo=["anything-kebab-case"])
            providers = capability_contract.FilesystemProviders(
                [root], capabilities=capability_names()
            )
            self.assertEqual(len(providers.adapter()["candidates"]), 1)

    def test_a_missing_root_is_reported_not_fatal(self):
        providers = capability_contract.FilesystemProviders(
            [Path("does-not-exist-anywhere")]
        )
        self.assertEqual(providers.adapter()["candidates"], [])
        self.assertEqual(len(providers.skipped), 1)

    def test_directories_without_a_declaration_are_ignored(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "unrelated-skill").mkdir()
            providers = capability_contract.FilesystemProviders([root])
            self.assertEqual(providers.adapter()["candidates"], [])
            self.assertEqual(providers.skipped, [])


class ResolutionTest(unittest.TestCase):
    def test_resolution_succeeds_without_any_host_adapter(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root)
            names = capability_names()
            adapter = capability_contract.FilesystemProviders(
                [root], capabilities=names, reserved=names | {"sdlc"}
            ).adapter()
            resolution = resolve_providers.resolve(
                config(), registry_modules(), adapter, "1.0.0", "filesystem"
            )
            self.assertEqual(resolution["hostProfile"], "filesystem")
            binding = resolution["providers"]["testing"]
            self.assertEqual(binding["id"], "acme-testing")

    def test_resolution_without_a_provider_root_still_fails_closed(self):
        with self.assertRaises(resolve_providers.ProviderError) as caught:
            resolve_providers.resolve(
                config(), registry_modules(), None, "1.0.0", "filesystem"
            )
        self.assertIn("provider-resolution-unsupported", str(caught.exception))

    def test_an_absent_provider_is_refused_rather_than_falling_back(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            adapter = capability_contract.FilesystemProviders(
                [root], capabilities=capability_names()
            ).adapter()
            with self.assertRaises(resolve_providers.ProviderError) as caught:
                resolve_providers.resolve(
                    config(), registry_modules(), adapter, "1.0.0",
                    "filesystem",
                )
            self.assertIn("provider-unavailable", str(caught.exception))

    def test_an_incompatible_provider_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root, compatibleSdlc=">=9.0.0")
            adapter = capability_contract.FilesystemProviders(
                [root], capabilities=capability_names()
            ).adapter()
            with self.assertRaises(resolve_providers.ProviderError) as caught:
                resolve_providers.resolve(
                    config(), registry_modules(), adapter, "1.0.0",
                    "filesystem",
                )
            self.assertIn("provider-incompatible", str(caught.exception))

    def test_a_provider_serving_another_capability_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root, capability="debugging")
            adapter = capability_contract.FilesystemProviders(
                [root], capabilities=capability_names()
            ).adapter()
            with self.assertRaises(resolve_providers.ProviderError) as caught:
                resolve_providers.resolve(
                    config(), registry_modules(), adapter, "1.0.0",
                    "filesystem",
                )
            self.assertIn("provider-module-unsupported", str(caught.exception))

    def test_duplicate_identities_across_roots_are_ambiguous(self):
        with tempfile.TemporaryDirectory() as first:
            with tempfile.TemporaryDirectory() as second:
                write_provider(Path(first))
                write_provider(Path(second))
                adapter = capability_contract.FilesystemProviders(
                    [Path(first), Path(second)],
                    capabilities=capability_names(),
                ).adapter()
                with self.assertRaises(
                    resolve_providers.ProviderError
                ) as caught:
                    resolve_providers.resolve(
                        config(), registry_modules(), adapter, "1.0.0",
                        "filesystem",
                    )
                self.assertIn("provider-ambiguous", str(caught.exception))


class LoadTest(unittest.TestCase):
    def binding_and_inspection(self, root):
        names = capability_names()
        providers = capability_contract.FilesystemProviders(
            [root], capabilities=names, reserved=names | {"sdlc"}
        )
        resolution = resolve_providers.resolve(
            config(), registry_modules(), providers.adapter(), "1.0.0",
            "filesystem",
        )
        binding = resolution["providers"]["testing"]
        inspection = resolve_providers.inspect_module(
            "testing", binding, "matched", "missing", [], ["no acme run"]
        )
        return providers, binding, inspection

    def registry_entry(self):
        return next(
            entry for entry in registry_modules() if entry["name"] == "testing"
        )

    def test_instructions_load_through_the_filesystem_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root)
            providers, binding, inspection = self.binding_and_inspection(root)
            result = resolve_providers.load_module(
                binding, inspection, self.registry_entry(),
                providers.load, ORCHESTRATION_CONTEXT,
            )
            self.assertIn("Acme testing", json.dumps(result))

    def test_content_changed_after_resolution_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = write_provider(root)
            providers, binding, inspection = self.binding_and_inspection(root)
            (directory / "SKILL.md").write_text(
                "# Swapped\n", encoding="utf-8", newline="\n"
            )
            swapped = capability_contract.FilesystemProviders(
                [root], capabilities=capability_names()
            )
            with self.assertRaises(resolve_providers.ProviderError) as caught:
                resolve_providers.load_module(
                    binding, inspection, self.registry_entry(),
                    swapped.load, ORCHESTRATION_CONTEXT,
                )
            self.assertIn("provider-digest-mismatch", str(caught.exception))

    def test_an_unknown_token_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root)
            providers, binding, inspection = self.binding_and_inspection(root)
            binding = dict(binding, loadToken="not-a-real-token")
            with self.assertRaises(resolve_providers.ProviderError) as caught:
                resolve_providers.load_module(
                    binding, inspection, self.registry_entry(),
                    providers.load, ORCHESTRATION_CONTEXT,
                )
            self.assertIn("provider-load-token-unknown", str(caught.exception))

    def test_loading_without_an_evidence_gap_is_not_authorized(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root)
            names = capability_names()
            providers = capability_contract.FilesystemProviders(
                [root], capabilities=names, reserved=names | {"sdlc"}
            )
            resolution = resolve_providers.resolve(
                config(), registry_modules(), providers.adapter(), "1.0.0",
                "filesystem",
            )
            binding = resolution["providers"]["testing"]
            inspection = resolve_providers.inspect_module(
                "testing", binding, "matched", "satisfied",
                ["the acme suite reported a result"], [],
            )
            with self.assertRaises(resolve_providers.ProviderError) as caught:
                resolve_providers.load_module(
                    binding, inspection, self.registry_entry(),
                    providers.load, ORCHESTRATION_CONTEXT,
                )
            self.assertIn(
                "provider-load-not-authorized", str(caught.exception)
            )


class NonDelegatableFilesystemTest(unittest.TestCase):
    def test_a_judgment_capability_cannot_be_served_from_disk(self):
        import config_contract

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provider(root, name="acme-review", capability="review")
            with self.assertRaises(config_contract.ConfigError):
                config_contract.normalize_config(
                    config(module="review", provider="acme-review"),
                    capability_names(),
                )


if __name__ == "__main__":
    unittest.main()
