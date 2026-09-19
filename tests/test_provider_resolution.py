import hashlib
import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "skills" / "sdlc" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
try:
    config_contract = importlib.import_module("config_contract")
    resolve_providers = importlib.import_module("resolve_providers")
finally:
    sys.path.remove(str(SCRIPT_DIR))


CORE_MODULES = {"prd", "testing", "review"}


def provider_text(
    name="generic-prd-provider",
    compatible=">=1.0.0 <2.0.0",
    modules="prd",
    extra_metadata="",
):
    return (
        "---\n"
        f"name: {name}\n"
        "description: Use when a project requests a generic product definition provider.\n"
        "metadata:\n"
        '  sdlc-provider-schema: "1"\n'
        f'  sdlc-compatible: "{compatible}"\n'
        f'  sdlc-modules: "{modules}"\n'
        f"{extra_metadata}"
        "---\n\n"
        "# Generic product definition provider\n\n"
        "Produce inspectable product definition evidence.\n"
    )


def provider_metadata(
    compatible=">=1.0.0 <2.0.0",
    modules="prd",
):
    return {
        "sdlc-provider-schema": "1",
        "sdlc-compatible": compatible,
        "sdlc-modules": modules,
    }


class ProviderResolutionTests(unittest.TestCase):
    def setUp(self):
        self.work = ROOT / ".test-tmp" / "providers" / self.id().split(".")[-1]
        shutil.rmtree(self.work, ignore_errors=True)
        self.work.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.work, True)

    def config(self, modules=None, version=3):
        return {
            "schemaVersion": version,
            "modules": modules or {},
            "extensions": {"project": {}, "global": {}},
            "measurement": {"enabled": False},
        }

    def install_provider(self, scope="project", **overrides):
        root = self.work / scope
        skill = root / "generic-prd-provider"
        skill.mkdir(parents=True)
        content = provider_text(**overrides).encode()
        (skill / "SKILL.md").write_bytes(content)
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        return root, skill, digest

    def adapter(self, candidates, profile="generic-agent-skills"):
        return {
            "schemaVersion": 1,
            "hostProfile": profile,
            "candidates": candidates,
        }

    def candidate(self, relative, digest, token="bound-token"):
        return {
            "declaredName": relative,
            "providerMetadata": provider_metadata(),
            "contentDigest": digest,
            "loadToken": token,
        }

    def metadata_candidate(self, digest, token="bound-token", **overrides):
        candidate = {
            "declaredName": "generic-prd-provider",
            "providerMetadata": provider_metadata(),
            "contentDigest": digest,
            "loadToken": token,
        }
        candidate.update(overrides)
        return candidate

    def load_result(self, content, status="loaded", **overrides):
        result = {
            "schemaVersion": 1,
            "hostProfile": "generic-agent-skills",
            "status": status,
        }
        if status == "loaded":
            encoded = content.encode("utf-8")
            result["snapshot"] = {
                "declaredName": "generic-prd-provider",
                "providerMetadata": provider_metadata(),
                "contentDigest": "sha256:" + hashlib.sha256(encoded).hexdigest(),
                "content": content,
            }
        result.update(overrides)
        return result

    def write_json(self, name, value):
        path = self.work / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def write_capability(self, name, **overrides):
        """Write a bundled-style declaration beside a synthetic registry."""

        directory = self.work / ("sdlc-" + name)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "SKILL.md").write_text(
            f"# {name}\n", encoding="utf-8"
        )
        declaration = {
            "schemaVersion": 1,
            "id": "sdlc-" + name,
            "capability": name,
            "mode": "default",
            "instructions": "SKILL.md",
            "trigger": "Product change.",
            "exitSignal": "Evidence exists.",
            "evidence": ["Approved definition."],
            "compatibleSdlc": ">=1.0.0 <2.0.0",
        }
        declaration.update(overrides)
        (directory / "sdlc-capability.json").write_text(
            json.dumps(declaration), encoding="utf-8"
        )
        return directory

    def cli_load_files(self):
        content = provider_text()
        digest = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
        binding = {
            "id": "generic-prd-provider",
            "providerMetadata": provider_metadata(),
            "contentDigest": digest,
            "loadToken": "opaque-current-token",
            "hostProfile": "generic-agent-skills",
        }
        resolution = self.write_json(
            "resolution.json",
            {
                "schemaVersion": 1,
                "hostProfile": "generic-agent-skills",
                "providers": {"prd": binding},
            },
        )
        inspection = self.write_json(
            "inspection.json",
            {
                "module": "prd",
                "provider": {
                    "type": "replacement",
                    "id": "generic-prd-provider",
                },
                "bindingDigest": digest,
                "loadRequired": True,
                "recognizedEvidence": [],
                "gaps": ["approval"],
            },
        )
        self.write_capability("prd")
        registry = self.write_json(
            "registry.json",
            {
                "schemaVersion": 1,
                "modules": [{"name": "prd"}],
            },
        )
        context = self.write_json(
            "context.json",
            {
                "changeContract": {},
                "projectStandards": {},
                "projectMemory": {},
            },
        )
        return content, resolution, inspection, registry, context

    def run_embedded_callable_load(self, adapter):
        return self.run_embedded_load(
            types.SimpleNamespace(load_provider=adapter)
        )

    def run_embedded_load(self, adapter):
        _, resolution, inspection, registry, context = self.cli_load_files()
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = resolve_providers.main(
                [
                    "load-module",
                    "--resolution", str(resolution),
                    "--inspection", str(inspection),
                    "--registry", str(registry),
                    "--module", "prd",
                    "--provider-context", str(context),
                ],
                host_adapter=adapter,
            )
        return status, stdout.getvalue(), stderr.getvalue()

    def test_standalone_cli_cannot_import_caller_adapter_for_perfect_snapshot(self):
        content, resolution, inspection, registry, context = self.cli_load_files()
        marker = self.work / "caller-code-ran"
        module = self.work / "caller_adapter.py"
        module.write_text(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n"
            "def load_provider(token):\n"
            f"    content = {content!r}\n"
            "    import hashlib\n"
            "    return {\n"
            "        'schemaVersion': 1,\n"
            "        'hostProfile': 'generic-agent-skills',\n"
            "        'status': 'loaded',\n"
            "        'snapshot': {\n"
            "            'declaredName': 'generic-prd-provider',\n"
            f"            'providerMetadata': {provider_metadata()!r},\n"
            "            'contentDigest': 'sha256:' + "
            "hashlib.sha256(content.encode()).hexdigest(),\n"
            "            'content': content,\n"
            "        },\n"
            "    }\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "resolve_providers.py"),
                "load-module",
                "--resolution", str(resolution),
                "--inspection", str(inspection),
                "--registry", str(registry),
                "--module", "prd",
                "--host-adapter", "caller_adapter",
                "--provider-context", str(context),
            ],
            cwd=self.work,
            env={**os.environ, "PYTHONPATH": str(self.work)},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertFalse(marker.exists())
        self.assertNotIn('"instructions"', result.stdout)

    def test_standalone_cli_fails_closed_without_host_injection(self):
        content, resolution, inspection, registry, context = self.cli_load_files()
        del content
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = resolve_providers.main([
                "load-module",
                "--resolution", str(resolution),
                "--inspection", str(inspection),
                "--registry", str(registry),
                "--module", "prd",
                "--provider-context", str(context),
            ])
        self.assertEqual(2, status)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("provider-resolution-unsupported", stderr.getvalue())

        help_result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "resolve_providers.py"),
                "--help",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, help_result.returncode)
        self.assertIn("Standalone CLI execution", help_result.stdout)
        self.assertNotIn("--host-adapter", help_result.stdout)

    def test_embedding_adapter_preserves_success_replay_and_revocation(self):
        content, _, _, _, _ = self.cli_load_files()

        class Adapter:
            def __init__(self, revoked=False):
                self.revoked = revoked
                self.consumed = False

            def load_provider(self, token):
                if self.revoked:
                    return self_outer.load_result("", status="revoked")
                if self.consumed:
                    return self_outer.load_result("", status="token-replayed")
                self.consumed = True
                return self_outer.load_result(content)

        self_outer = self
        adapter = Adapter()
        status, output, error = self.run_embedded_load(adapter)
        self.assertEqual(0, status, error)
        self.assertIn('"instructions"', output)

        status, output, error = self.run_embedded_load(adapter)
        self.assertEqual(2, status)
        self.assertEqual("", output)
        self.assertIn("provider-load-token-replayed", error)

        status, output, error = self.run_embedded_load(Adapter(revoked=True))
        self.assertEqual(2, status)
        self.assertEqual("", output)
        self.assertIn("provider-load-revoked", error)

    def test_embedding_consumes_current_opaque_token_through_host_adapter(self):
        content, _, _, _, _ = self.cli_load_files()
        calls = []
        consumed = set()

        def load_provider(token):
            calls.append(token)
            if token in consumed:
                return self.load_result("", status="token-replayed")
            consumed.add(token)
            return self.load_result(content)

        status, output, error = self.run_embedded_callable_load(load_provider)
        self.assertEqual(0, status, error)
        self.assertIn('"instructions"', output)
        self.assertEqual(["opaque-current-token"], calls)

        status, _, error = self.run_embedded_callable_load(load_provider)
        self.assertEqual(2, status)
        self.assertIn("provider-load-token-replayed", error)
        self.assertEqual(
            ["opaque-current-token", "opaque-current-token"], calls
        )

    def test_embedding_gets_metadata_from_host_adapter_contract(self):
        project = self.work / "project"
        config_path = project / ".sdlc" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(
            json.dumps(
                self.config({
                    "prd": {"replaceWith": "generic-prd-provider"},
                })
            ),
            encoding="utf-8",
        )
        self.write_capability("prd")
        registry = self.write_json(
            "registry.json",
            {
                "schemaVersion": 1,
                "modules": [{"name": "prd"}],
            },
        )
        content = provider_text()
        digest = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
        calls = []

        def enumerate_providers(profile):
            calls.append(profile)
            return self.adapter([self.metadata_candidate(digest)], profile)

        adapter = types.SimpleNamespace(
            enumerate_providers=enumerate_providers
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = resolve_providers.main(
                [
                    "resolve",
                    "--project-root", str(project),
                    "--registry", str(registry),
                    "--host-profile", "generic-agent-skills",
                    "--sdlc-version", "1.0.0",
                ],
                host_adapter=adapter,
            )
        self.assertEqual(0, status, stderr.getvalue())
        self.assertIn('"loadToken": "bound-token"', stdout.getvalue())
        self.assertEqual(["generic-agent-skills"], calls)

    def test_embedding_rejects_adapter_failures_and_unbound_snapshots(self):
        content, _, _, _, _ = self.cli_load_files()
        cases = (
            (
                lambda token: self.load_result("", status="revoked"),
                "provider-load-revoked",
            ),
            (
                lambda token: self.load_result("", status="token-unknown"),
                "provider-load-token-unknown",
            ),
            (
                lambda token: self.load_result("", status="token-replayed"),
                "provider-load-token-replayed",
            ),
            (
                lambda token: self.load_result(
                    content,
                    snapshot={
                        **self.load_result(content)["snapshot"],
                        "declaredName": "fabricated-provider",
                    },
                ),
                "provider-identity-mismatch",
            ),
            (
                lambda token: self.load_result(content + "\nchanged\n"),
                "provider-digest-mismatch",
            ),
            (
                lambda token: self.load_result(
                    content,
                    snapshot={
                        **self.load_result(content)["snapshot"],
                        "providerMetadata": provider_metadata(modules="testing"),
                    },
                ),
                "provider-metadata-invalid",
            ),
        )
        for adapter, error_class in cases:
            with self.subTest(error_class=error_class):
                status, output, error = self.run_embedded_callable_load(adapter)
                self.assertEqual("", output)
                self.assertEqual(2, status)
                self.assertIn(error_class, error)

    def test_resolution_uses_adapter_metadata_without_reading_instruction_body(self):
        root, _, digest = self.install_provider()
        config = config_contract.normalize_config(
            self.config({"prd": {"replaceWith": "generic-prd-provider"}}),
            CORE_MODULES,
        )
        with mock.patch.object(
            Path,
            "read_bytes",
            side_effect=AssertionError("instruction body was read"),
        ):
            result = resolve_providers.resolve(
                config,
                [{"name": name} for name in sorted(CORE_MODULES)],
                self.adapter([self.metadata_candidate(digest)]),
                "1.0.0",
            )
            binding = result["providers"]["prd"]
            for status, trigger in (
                ("satisfied", "matched"),
                ("not-applicable", "not-matched"),
            ):
                inspection = resolve_providers.inspect_module(
                    "prd", binding, trigger, status, [], []
                )
                self.assertFalse(inspection["loadRequired"])

    def test_host_adapter_rejects_revoked_unknown_and_replayed_tokens(self):
        _, _, digest = self.install_provider()
        binding = {
            "id": "generic-prd-provider",
            "providerMetadata": provider_metadata(),
            "contentDigest": digest,
            "loadToken": "opaque-token",
            "hostProfile": "generic-agent-skills",
        }
        inspection = {
            "module": "prd",
            "provider": {"type": "replacement", "id": binding["id"]},
            "bindingDigest": digest,
            "loadRequired": True,
            "recognizedEvidence": [],
            "gaps": ["approval"],
        }
        registry = {
            "name": "prd",
            "trigger": "Product change.",
            "exitSignal": "Evidence exists.",
            "evidence": ["Approved definition."],
        }
        for status, error_class in (
            ("revoked", "provider-load-revoked"),
            ("token-unknown", "provider-load-token-unknown"),
            ("token-replayed", "provider-load-token-replayed"),
            ("unloadable", "provider-unloadable"),
        ):
            with self.subTest(status=status):
                calls = []

                def adapter_load(token):
                    calls.append(token)
                    return self.load_result("", status=status)

                with self.assertRaisesRegex(
                    resolve_providers.ProviderError, error_class
                ):
                    resolve_providers.load_module(
                        binding, inspection, registry, adapter_load, {}
                    )
                self.assertEqual(["opaque-token"], calls)

    def test_loaded_snapshot_identity_and_digest_are_revalidated(self):
        _, _, digest = self.install_provider()
        binding = {
            "id": "generic-prd-provider",
            "providerMetadata": provider_metadata(),
            "contentDigest": digest,
            "loadToken": "opaque-token",
            "hostProfile": "generic-agent-skills",
        }
        inspection = {
            "module": "prd",
            "provider": {"type": "replacement", "id": binding["id"]},
            "bindingDigest": digest,
            "loadRequired": True,
            "recognizedEvidence": [],
            "gaps": ["approval"],
        }
        registry = {
            "name": "prd",
            "trigger": "Product change.",
            "exitSignal": "Evidence exists.",
            "evidence": ["Approved definition."],
        }
        changed = provider_text() + "\nchanged\n"
        wrong_identity = provider_text(name="another-provider")
        wrong_identity_digest = (
            "sha256:" + hashlib.sha256(wrong_identity.encode()).hexdigest()
        )
        cases = [
            (binding, self.load_result(changed), "provider-digest-mismatch"),
            (
                {**binding, "contentDigest": wrong_identity_digest},
                self.load_result(
                    wrong_identity,
                    snapshot={
                        "declaredName": "generic-prd-provider",
                        "providerMetadata": provider_metadata(),
                        "contentDigest": wrong_identity_digest,
                        "content": wrong_identity,
                    },
                ),
                "provider-identity-mismatch",
            ),
        ]
        for case_binding, result, error_class in cases:
            with self.subTest(error_class=error_class):
                case_inspection = {
                    **inspection,
                    "bindingDigest": case_binding["contentDigest"],
                }
                with self.assertRaisesRegex(
                    resolve_providers.ProviderError, error_class
                ):
                    resolve_providers.load_module(
                        case_binding,
                        case_inspection,
                        registry,
                        lambda _: result,
                        {
                            "changeContract": {},
                            "projectStandards": {},
                            "projectMemory": {},
                        },
                    )

    def test_empty_instruction_body_fails_before_success_result(self):
        content = provider_text().split("---\n\n", 1)[0] + "---\n\n"
        digest = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
        binding = {
            "id": "generic-prd-provider",
            "providerMetadata": provider_metadata(),
            "contentDigest": digest,
            "loadToken": "opaque-token",
            "hostProfile": "generic-agent-skills",
        }
        inspection = {
            "module": "prd",
            "provider": {"type": "replacement", "id": binding["id"]},
            "bindingDigest": digest,
            "loadRequired": True,
            "recognizedEvidence": [],
            "gaps": ["approval"],
        }
        registry = {
            "name": "prd",
            "trigger": "Product change.",
            "exitSignal": "Evidence exists.",
            "evidence": ["Approved definition."],
        }
        with self.assertRaisesRegex(
            resolve_providers.ProviderError, "provider-instructions-empty"
        ):
            resolve_providers.load_module(
                binding,
                inspection,
                registry,
                lambda _: self.load_result(content),
                {
                    "changeContract": {},
                    "projectStandards": {},
                    "projectMemory": {},
                },
            )

    def test_schema_one_and_two_migrate_to_three_without_behavior_change(self):
        schema_one = {"schemaVersion": 1, "modules": {"testing": False}}
        schema_two = self.config({"testing": False}, version=2)
        for config in (schema_one, schema_two):
            with self.subTest(version=config["schemaVersion"]):
                normalized = config_contract.normalize_config(config, CORE_MODULES)
                self.assertEqual(3, normalized["schemaVersion"])
                self.assertFalse(normalized["modules"]["testing"])
                self.assertTrue(normalized["modules"]["prd"])
                self.assertEqual(
                    {"project": {}, "global": {}}, normalized["extensions"]
                )
                self.assertEqual({"enabled": False}, normalized["measurement"])

    def test_schema_three_accepts_mixed_states_and_rejects_invalid_union(self):
        normalized = config_contract.normalize_config(
            self.config(
                {
                    "prd": {"replaceWith": "generic-prd-provider"},
                    "testing": True,
                    "review": False,
                }
            ),
            CORE_MODULES,
        )
        self.assertEqual(
            {"replaceWith": "generic-prd-provider"},
            normalized["modules"]["prd"],
        )
        invalid = (
            None,
            "generic-prd-provider",
            1,
            [],
            {},
            {"replaceWith": ""},
            {"replaceWith": " Generic-prd-provider "},
            {"replaceWith": "generic-prd-provider", "extra": True},
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(config_contract.ConfigError):
                    config_contract.normalize_config(
                        self.config({"prd": value}), CORE_MODULES
                    )

    def test_duplicate_assignment_and_core_cycles_fail_closed(self):
        for modules in (
            {
                "prd": {"replaceWith": "generic-prd-provider"},
                "testing": {"replaceWith": "generic-prd-provider"},
            },
            {"prd": {"replaceWith": "sdlc"}},
            {"prd": {"replaceWith": "testing"}},
        ):
            with self.subTest(modules=modules):
                with self.assertRaises(config_contract.ConfigError):
                    config_contract.normalize_config(
                        self.config(modules), CORE_MODULES
                    )

    def test_schema_migration_is_persisted_before_resolution(self):
        project = self.work / "repo"
        path = project / ".sdlc" / "config.json"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps({"schemaVersion": 2, "modules": {"review": False},
                        "extensions": {"project": {}, "global": {}}}),
            encoding="utf-8",
        )
        normalized = config_contract.load_project_config(project, CORE_MODULES)
        self.assertEqual(3, normalized["schemaVersion"])
        self.assertEqual(normalized, json.loads(path.read_text(encoding="utf-8")))

    def test_exact_candidate_resolves_and_binds_digest_and_load_token(self):
        root, _, digest = self.install_provider()
        config = config_contract.normalize_config(
            self.config({"prd": {"replaceWith": "generic-prd-provider"}}),
            CORE_MODULES,
        )
        result = resolve_providers.resolve(
            config,
            [{"name": name} for name in sorted(CORE_MODULES)],
            self.adapter(
                [self.candidate("generic-prd-provider", digest)]
            ),
            "1.0.0",
        )
        binding = result["providers"]["prd"]
        self.assertEqual("generic-prd-provider", binding["id"])
        self.assertEqual(digest, binding["contentDigest"])
        self.assertEqual("bound-token", binding["loadToken"])

    def test_unavailable_ambiguous_and_unsupported_enumeration_fail_closed(self):
        config = config_contract.normalize_config(
            self.config({"prd": {"replaceWith": "generic-prd-provider"}}),
            CORE_MODULES,
        )
        with self.assertRaisesRegex(
            resolve_providers.ProviderError, "provider-unavailable"
        ):
            resolve_providers.resolve(
                config, [{"name": "prd"}], self.adapter([]), "1.0.0"
            )
        root_a, _, digest_a = self.install_provider("scope-a")
        root_b, _, digest_b = self.install_provider("scope-b")
        with self.assertRaisesRegex(
            resolve_providers.ProviderError, "provider-ambiguous"
        ):
            resolve_providers.resolve(
                config,
                [{"name": "prd"}],
                self.adapter(
                    [
                        self.candidate("generic-prd-provider", digest_a, "a"),
                        self.candidate("generic-prd-provider", digest_b, "b"),
                    ]
                ),
                "1.0.0",
            )
        with self.assertRaisesRegex(
            resolve_providers.ProviderError, "provider-resolution-unsupported"
        ):
            resolve_providers.resolve(
                config, [{"name": "prd"}], None, "1.0.0",
                host_profile="copilot-vscode",
            )

    def test_case_mismatch_incompatible_and_unsupported_module_fail_closed(self):
        config = config_contract.normalize_config(
            self.config({"prd": {"replaceWith": "generic-prd-provider"}}),
            CORE_MODULES,
        )
        cases = (
            (
                {"declaredName": "Generic-prd-provider"},
                "provider-adapter-invalid",
            ),
            (
                {
                    "providerMetadata": provider_metadata(
                        compatible=">=4.0.0 <5.0.0"
                    )
                },
                "provider-incompatible",
            ),
            (
                {"providerMetadata": provider_metadata(modules="testing")},
                "provider-module-unsupported",
            ),
            (
                {
                    "providerMetadata": {
                        **provider_metadata(),
                        "sdlc-moduels": "prd",
                    }
                },
                "provider-metadata-invalid",
            ),
        )
        for index, (overrides, error_class) in enumerate(cases):
            with self.subTest(error_class=error_class):
                _, _, digest = self.install_provider(f"case-{index}")
                candidate = self.metadata_candidate(digest, **overrides)
                with self.assertRaisesRegex(
                    resolve_providers.ProviderError, error_class
                ):
                    resolve_providers.resolve(
                        config,
                        [{"name": "prd"}],
                        self.adapter([candidate]),
                        "1.0.0",
                    )

    def test_satisfied_or_not_applicable_inspection_never_loads_provider(self):
        binding = {
            "id": "generic-prd-provider",
            "contentDigest": "sha256:" + "a" * 64,
            "loadToken": "bound-token",
            "providerMetadata": provider_metadata(),
            "hostProfile": "generic-agent-skills",
        }
        satisfied = resolve_providers.inspect_module(
            "prd", binding, "matched", "satisfied", ["approved PRD"], []
        )
        not_applicable = resolve_providers.inspect_module(
            "prd", binding, "not-matched", "not-applicable", [], []
        )
        self.assertEqual("reused", satisfied["action"])
        self.assertEqual("skipped", not_applicable["action"])
        self.assertFalse(satisfied["loadRequired"])
        self.assertFalse(not_applicable["loadRequired"])
        for status, gaps in (
            ("configured-disabled", []),
            ("satisfied", ["unresolved"]),
            ("partial", []),
        ):
            with self.subTest(status=status):
                with self.assertRaisesRegex(
                    resolve_providers.ProviderError,
                    "provider-inspection-invalid",
                ):
                    resolve_providers.inspect_module(
                        "prd", binding, "matched", status, [], gaps
                    )

    def test_evidence_gap_loads_exact_snapshot_and_exposes_core_authority(self):
        _, _, digest = self.install_provider()
        binding = {
            "id": "generic-prd-provider",
            "contentDigest": digest,
            "loadToken": "bound-token",
            "providerMetadata": provider_metadata(),
            "hostProfile": "generic-agent-skills",
        }
        inspection = resolve_providers.inspect_module(
            "prd",
            binding,
            "matched",
            "partial",
            ["stable identity"],
            ["approval evidence"],
        )
        registry = {
            "name": "prd",
            "trigger": "A product capability is in scope.",
            "exitSignal": "Approved product definition evidence exists.",
            "evidence": ["Stable identity.", "Approval evidence."],
        }
        with mock.patch.object(
            Path,
            "read_bytes",
            side_effect=AssertionError("direct filesystem bypass"),
        ):
            loaded = resolve_providers.load_module(
                binding,
                inspection,
                registry,
                lambda _: self.load_result(provider_text()),
                {
                    "changeContract": {"outcome": "Define the capability."},
                    "projectStandards": ["Use standard-library tooling."],
                    "projectMemory": ["The registry is authoritative."],
                },
            )
        self.assertIn("Generic product definition provider", loaded["instructions"])
        self.assertEqual(["approval evidence"], loaded["context"]["gaps"])
        self.assertEqual(registry["evidence"], loaded["context"]["coreEvidence"])
        self.assertEqual(
            "orchestrator", loaded["context"]["readinessAuthority"]
        )
        self.assertEqual(
            {"outcome": "Define the capability."},
            loaded["context"]["changeContract"],
        )
        self.assertEqual(
            "loaded replacement; core evidence requires reclassification",
            loaded["action"],
        )

    def test_changed_snapshot_digest_blocks_without_fallback(self):
        _, _, digest = self.install_provider()
        binding = {
            "id": "generic-prd-provider",
            "contentDigest": digest,
            "loadToken": "bound-token",
            "providerMetadata": provider_metadata(),
            "hostProfile": "generic-agent-skills",
        }
        inspection = resolve_providers.inspect_module(
            "prd", binding, "matched", "missing", [], ["all evidence"]
        )
        registry = {
            "name": "prd",
            "trigger": "Product change.",
            "exitSignal": "Evidence exists.",
            "evidence": ["Approved definition."],
        }
        changed = provider_text() + "\nChanged after resolution.\n"
        with self.assertRaisesRegex(
            resolve_providers.ProviderError, "provider-digest-mismatch"
        ):
            resolve_providers.load_module(
                binding,
                inspection,
                registry,
                lambda _: self.load_result(changed),
                {
                    "changeContract": {},
                    "projectStandards": {},
                    "projectMemory": {},
                },
            )

    def test_unloadable_provider_has_explicit_failure_contract(self):
        self.assertIn(
            "unloadable", resolve_providers._LOAD_FAILURES
        )

    def test_malformed_registry_load_fails_with_provider_contract(self):
        with self.assertRaisesRegex(
            resolve_providers.ProviderError, "provider-registry-invalid"
        ):
            resolve_providers.load_module(
                {}, {}, None, lambda _: {}, {}
            )

    def test_disabled_and_augmenting_extensions_remain_isolated(self):
        config = config_contract.normalize_config(
            self.config(
                {
                    "prd": {"replaceWith": "generic-prd-provider"},
                    "review": False,
                }
            ),
            CORE_MODULES,
        )
        self.assertEqual({"project": {}, "global": {}}, config["extensions"])
        disabled = resolve_providers.module_provider(config, "review")
        replacement = resolve_providers.module_provider(config, "prd")
        self.assertEqual({"type": "disabled", "id": None}, disabled)
        self.assertEqual(
            {"type": "replacement", "id": "generic-prd-provider"},
            replacement,
        )


if __name__ == "__main__":
    unittest.main()
