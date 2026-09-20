import copy
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("qualify", ROOT / "scripts" / "qualify.py")
qualify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qualify)


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.work = ROOT / ".test-tmp" / "qualification" / self.id().split(".")[-1]
        shutil.rmtree(self.work, ignore_errors=True)
        self.work.mkdir(parents=True)
        self.manifest = qualify.load_json_strict(ROOT / "qualification" / "manifest.json")
        self.manifest = qualify.validate_manifest(self.manifest, ROOT)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def test_directory_promotion_retries_transient_windows_access_denied(self):
        rename = mock.Mock(
            side_effect=[
                PermissionError(13, "busy"),
                PermissionError(13, "busy"),
                None,
            ]
        )

        qualify._rename_with_retry(
            self.work / "source",
            self.work / "destination",
            rename=rename,
            sleep=lambda _seconds: None,
            windows=True,
        )

        self.assertEqual(3, rename.call_count)

    def test_strict_json_rejects_duplicate_nonfinite_and_invalid_utf8(self):
        cases = [b'{"a":1,"a":2}', b'{"a":NaN}', b'"\xff"']
        for index, content in enumerate(cases):
            path = self.work / f"{index}.json"
            path.write_bytes(content)
            with self.assertRaises(ValueError):
                qualify.load_json_strict(path)
        deep = self.work / "deep.json"
        deep.write_text("[" * 20 + "0" + "]" * 20, encoding="utf-8")
        with self.assertRaises(ValueError):
            qualify.load_json_strict(deep)

    def test_inventory_digest_uses_sorted_nul_records(self):
        bundle = self.work / "bundle"
        bundle.mkdir()
        (bundle / "b").write_bytes(b"B")
        (bundle / "a").write_bytes(b"A")
        files, digest = qualify.inventory_bundle(bundle)
        expected_files = [
            {"path": "a", "sha256": hashlib.sha256(b"A").hexdigest()},
            {"path": "b", "sha256": hashlib.sha256(b"B").hexdigest()},
        ]
        expected = hashlib.sha256(
            "".join(f"{row['path']}\0{row['sha256']}\n" for row in expected_files).encode()
        ).hexdigest()
        self.assertEqual(expected_files, files)
        self.assertEqual(expected, digest)

    def test_inventory_rejects_links(self):
        source = self.work / "source"
        target = self.work / "target"
        source.mkdir()
        target.mkdir()
        try:
            (source / "linked").symlink_to(target, target_is_directory=True)
        except OSError:
            completed = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(source / "linked"), str(target)],
                capture_output=True,
                text=True,
            )
            if completed.returncode:
                self.fail(completed.stderr or completed.stdout)
        with self.assertRaises(ValueError):
            qualify.inventory_bundle(source)

    def test_manifest_has_exact_profile_matrix_and_inventory(self):
        profiles = {row["id"]: row for row in self.manifest["profiles"]}
        self.assertEqual(
            {"copilot-vscode", "claude-code", "generic-agent-skills"}, set(profiles)
        )
        for profile in profiles.values():
            self.assertEqual(4, len(profile["cells"]))
        generic = profiles["generic-agent-skills"]
        unsupported = [c for c in generic["cells"] if c["support"] == "unsupported"]
        self.assertEqual({("global", "copy"), ("global", "link")},
                         {(c["scope"], c["mode"]) for c in unsupported})
        files, digest = qualify.inventory_bundle(ROOT / "skills" / "sdlc")
        self.assertEqual(files, self.manifest["skill"]["files"])
        self.assertEqual(digest, self.manifest["skill"]["bundleSha256"])

    def test_discover_implementations_excludes_standalone_skills_without_capability_json(self):
        bundle_root = self.work / "skills"
        bundle_root.mkdir()
        bundle = bundle_root / "sdlc"
        bundle.mkdir()
        (bundle / "SKILL.md").write_text("# sdlc\n", encoding="utf-8")

        real_impl = bundle_root / "sdlc-fake-impl"
        real_impl.mkdir()
        (real_impl / "SKILL.md").write_text("# fake-impl\n", encoding="utf-8")
        (real_impl / "sdlc-capability.json").write_text("{}", encoding="utf-8")

        standalone = bundle_root / "sdlc-standalone-tool"
        standalone.mkdir()
        (standalone / "SKILL.md").write_text("# standalone\n", encoding="utf-8")

        implementations = qualify.discover_implementations(bundle)
        self.assertEqual(["sdlc-fake-impl"], [row["id"] for row in implementations])

    def test_manifest_rejects_unknown_fields_unsafe_paths_and_unsorted_files(self):
        for mutate in (
            lambda value: value.update({"extra": True}),
            lambda value: value["skill"].update({"source": "../sdlc"}),
            lambda value: value["skill"]["files"].reverse(),
        ):
            value = copy.deepcopy(self.manifest)
            mutate(value)
            with self.assertRaises(ValueError):
                qualify.validate_manifest(value, ROOT)

    def test_manifest_rejects_mutated_profile_labels_roots_and_support(self):
        mutations = (
            lambda value: value["profiles"][0].update({"label": "VS Code"}),
            lambda value: value["profiles"][0].update({"projectRoot": ".agents/skills"}),
            lambda value: value["profiles"][1].update({"globalRoot": ".agents/skills"}),
            lambda value: value["profiles"][2]["cells"][0].update(
                {"support": "unsupported", "reason": "mutated"}
            ),
        )
        for mutate in mutations:
            value = copy.deepcopy(self.manifest)
            mutate(value)
            with self.assertRaises(ValueError):
                qualify.validate_manifest(value, ROOT)

    def test_destination_resolution_requires_explicit_root_and_confinement(self):
        profile = self.manifest["profiles"][0]
        with self.assertRaises(ValueError):
            qualify.resolve_destination(profile, "global", None, None)
        project = self.work / "project"
        project.mkdir()
        destination = qualify.resolve_destination(profile, "project", project, None)
        self.assertEqual(project / profile["projectRoot"] / "sdlc", destination)
        with self.assertRaises(ValueError):
            qualify.resolve_destination(profile, "project", project, None, self.work.parent)

    def test_destination_resolution_rejects_linked_supplied_root(self):
        profile = self.manifest["profiles"][0]
        target = self.work / "outside"
        linked_root = self.work / "linked-project"
        target.mkdir()
        try:
            linked_root.symlink_to(target, target_is_directory=True)
        except OSError:
            completed = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(linked_root), str(target)],
                capture_output=True,
                text=True,
            )
            if completed.returncode:
                self.fail(completed.stderr or completed.stdout)
        with self.assertRaises(ValueError):
            qualify.resolve_destination(profile, "project", linked_root, None)

    def test_copy_install_is_exact_and_idempotent(self):
        destination = self.work / "skills" / "sdlc"
        qualify.install_suite(ROOT, self.manifest, destination, "copy")
        first = qualify.inspect_install(
            self.manifest, destination, "generic-agent-skills", "project", "copy"
        )
        qualify.install_suite(ROOT, self.manifest, destination, "copy")
        second = qualify.inspect_install(
            self.manifest, destination, "generic-agent-skills", "project", "copy"
        )
        self.assertEqual("pass", first["installation"]["status"])
        self.assertEqual(first, second)
        self.assertFalse(list(destination.parent.glob(".sdlc-*")))

    def test_install_inspection_ignores_unrelated_skills_sharing_the_root(self):
        destination = self.work / "skills" / "sdlc"
        qualify.install_suite(ROOT, self.manifest, destination, "copy")
        unrelated = destination.parent / "some-other-skill"
        unrelated.mkdir()
        (unrelated / "SKILL.md").write_text(
            "---\nname: some-other-skill\n---\n", encoding="utf-8"
        )
        result = qualify.inspect_install(
            self.manifest, destination, "generic-agent-skills", "project", "copy"
        )
        self.assertEqual("pass", result["installation"]["status"])

    def test_link_install_targets_canonical_bundle(self):
        destination = self.work / "skills" / "sdlc"
        try:
            qualify.install_suite(ROOT, self.manifest, destination, "link")
        except OSError as error:
            self.skipTest(str(error))
        result = qualify.inspect_install(
            self.manifest, destination, "generic-agent-skills", "project", "link"
        )
        self.assertEqual("pass", result["installation"]["status"])
        self.assertTrue(destination.is_symlink() or qualify.is_directory_link(destination))

    def test_every_required_installation_cell_conforms_in_synthetic_roots(self):
        project = self.work / "project"
        home = self.work / "home"
        project.mkdir()
        home.mkdir()
        count = 0
        for profile in self.manifest["profiles"]:
            for cell in profile["cells"]:
                if cell["support"] != "required":
                    continue
                destination = qualify.resolve_destination(
                    profile, cell["scope"], project, home
                )
                qualify.install_suite(
                    ROOT, self.manifest, destination, cell["mode"]
                )
                result = qualify.inspect_install(
                    self.manifest, destination, profile["id"],
                    cell["scope"], cell["mode"]
                )
                self.assertEqual("pass", result["installation"]["status"])
                count += 1
        self.assertEqual(10, count)
        self.assertFalse(list(self.work.rglob(".sdlc-staging-*")))
        self.assertFalse(list(self.work.rglob(".sdlc-backup-*")))

    def test_copy_failure_preserves_existing_install_and_cleans_staging(self):
        destination = self.work / "skills" / "sdlc"
        destination.mkdir(parents=True)
        marker = destination / "marker"
        marker.write_text("preserve", encoding="utf-8")
        with mock.patch.object(qualify.shutil, "copytree", side_effect=OSError("injected")):
            with self.assertRaises(OSError):
                qualify.install_bundle(ROOT / "skills" / "sdlc", destination, "copy")
        self.assertEqual("preserve", marker.read_text(encoding="utf-8"))
        self.assertFalse(list(destination.parent.glob(".sdlc-*")))

    def test_post_promotion_failure_restores_existing_install(self):
        destination = self.work / "skills" / "sdlc"
        destination.mkdir(parents=True)
        marker = destination / "marker"
        marker.write_text("preserve", encoding="utf-8")
        real_inventory = qualify.inventory_bundle

        def fail_installed_check(path):
            if Path(path).absolute() == destination.absolute():
                raise OSError("injected verification failure")
            return real_inventory(path)

        with mock.patch.object(
            qualify, "inventory_bundle", side_effect=fail_installed_check
        ):
            with self.assertRaises(OSError):
                qualify.install_bundle(
                    ROOT / "skills" / "sdlc", destination, "copy"
                )
        self.assertEqual("preserve", marker.read_text(encoding="utf-8"))
        self.assertFalse(list(destination.parent.glob(".sdlc-*")))

    def test_deterministic_install_does_not_use_network(self):
        destination = self.work / "skills" / "sdlc"
        real_run = subprocess.run
        network_commands = {"curl", "wget", "git", "npm", "npx", "pip"}

        def guarded_run(command, *args, **kwargs):
            self.assertNotIn(Path(str(command[0])).stem.lower(), network_commands)
            return real_run(command, *args, **kwargs)

        with mock.patch.object(socket, "socket", side_effect=AssertionError("network used")):
            with mock.patch.object(qualify.subprocess, "run", side_effect=guarded_run):
                qualify.install_suite(
                    ROOT, self.manifest, destination, "link"
                )
                qualify.inspect_install(
                    self.manifest, destination, "generic-agent-skills",
                    "project", "link"
                )

    def test_install_rejects_source_overlap_file_destination_and_legacy(self):
        source = ROOT / "skills" / "sdlc"
        with self.assertRaises(ValueError):
            qualify.install_bundle(source, source / "nested", "copy")
        file_destination = self.work / "file"
        file_destination.write_text("x", encoding="utf-8")
        with self.assertRaises(ValueError):
            qualify.install_bundle(source, file_destination, "copy")
        root = self.work / "skills"
        (root / "project-memory").mkdir(parents=True)
        with self.assertRaises(ValueError):
            qualify.install_bundle(source, root / "sdlc", "copy")

    def test_result_schema_rejects_raw_or_free_form_content(self):
        result = qualify.deterministic_result(
            self.manifest, "generic-agent-skills", "project", "copy"
        )
        self.assertEqual(result, qualify.validate_result(result, self.manifest))
        for mutate in (
            lambda value: value.update({"prompt": "raw"}),
            lambda value: value["cases"][0]["evidence"].append(
                {"code": "comment", "value": "free form"}
            ),
            lambda value: value.update({"clientVersion": "https://example.invalid"}),
            lambda value: value.update({"clientVersion": "copilot-vscode"}),
        ):
            value = copy.deepcopy(result)
            mutate(value)
            with self.assertRaises(ValueError):
                qualify.validate_result(value, self.manifest)

    def test_deterministic_result_does_not_invent_unperformed_evidence(self):
        result = qualify.deterministic_result(
            self.manifest, "generic-agent-skills", "project", "copy"
        )
        self.assertEqual("not-executed", result["installation"]["status"])
        self.assertFalse(any(case["status"] == "pass" for case in result["cases"]))
        self.assertTrue(all(case["evidence"] == [] for case in result["cases"]))

    def test_install_inspection_only_passes_checks_it_performed(self):
        destination = self.work / "skills" / "sdlc"
        qualify.install_suite(ROOT, self.manifest, destination, "copy")
        result = qualify.inspect_install(
            self.manifest, destination, "generic-agent-skills", "project", "copy"
        )
        statuses = {case["id"]: case["status"] for case in result["cases"]}
        self.assertEqual("pass", result["installation"]["status"])
        self.assertEqual("pass", statuses["copy-byte-identity"])
        self.assertEqual("not-executed", statuses["link-target-identity"])
        for case_id in qualify.SUITE_ONLY_CASES:
            self.assertEqual("not-executed", statuses[case_id])

    def test_result_validation_rejects_fabricated_deterministic_passes(self):
        result = qualify.deterministic_result(
            self.manifest, "generic-agent-skills", "project", "copy"
        )
        cases = {case["id"]: case for case in result["cases"]}
        for case_id in ("link-target-identity", "installer-idempotence"):
            mutated = copy.deepcopy(result)
            case = next(item for item in mutated["cases"] if item["id"] == case_id)
            case["status"] = "pass"
            case["evidence"] = qualify._deterministic_evidence(case_id)
            with self.assertRaises(ValueError):
                qualify.validate_result(mutated, self.manifest)
        with self.assertRaises(ValueError):
            qualify.deterministic_result(
                self.manifest,
                "generic-agent-skills",
                "project",
                "copy",
                performed={
                    "installer-idempotence": qualify._deterministic_evidence(
                        "installer-idempotence"
                    )
                },
            )
        with self.assertRaises(ValueError):
            qualify.deterministic_result(
                self.manifest,
                "generic-agent-skills",
                "project",
                "copy",
                performed={
                    "manifest-contract": [{"code": "manifest-valid", "value": False}]
                },
            )

    def test_sanitizer_reconstructs_allowlisted_live_summary(self):
        raw = {
            "profile": "copilot-vscode",
            "clientVersion": "1.2.3",
            "modelClass": "general",
            "installation": {"scope": "project", "mode": "copy", "status": "pass"},
            "cases": [
                {
                    "id": case["id"],
                    "repetitions": case["repetitions"],
                    "passes": case["repetitions"],
                    "triggered": True,
                    "forbiddenObserved": False,
                }
                for case in self.manifest["liveCases"]
            ],
            "rawResponse": "must not be copied",
        }
        clean = qualify.sanitize_live_result(raw, self.manifest)
        self.assertNotIn("rawResponse", json.dumps(clean))
        self.assertEqual("live-host", clean["resultType"])
        self.assertEqual(clean, qualify.validate_result(clean, self.manifest))
        provider_version = copy.deepcopy(raw)
        provider_version["clientVersion"] = "copilot-vscode"
        with self.assertRaises(ValueError):
            qualify.sanitize_live_result(provider_version, self.manifest)
        raw["cases"][0]["unknown"] = "unsafe"
        with self.assertRaises(ValueError):
            qualify.sanitize_live_result(raw, self.manifest)

    def test_client_versions_accept_real_versions_and_reject_identifiers_and_secrets(self):
        raw = {
            "profile": "copilot-vscode",
            "clientVersion": "1.2.3",
            "modelClass": "general",
            "installation": {"scope": "project", "mode": "copy", "status": "pass"},
            "cases": [
                {
                    "id": case["id"],
                    "repetitions": case["repetitions"],
                    "passes": case["repetitions"],
                    "triggered": True,
                    "forbiddenObserved": False,
                }
                for case in self.manifest["liveCases"]
            ],
        }
        for version in ("1.95.3", "v1.2.3", "2026.9.0-insider.1", "1.2.3+build.7"):
            value = copy.deepcopy(raw)
            value["clientVersion"] = version
            qualify.sanitize_live_result(value, self.manifest)
        for version in (
            "copilot-vscode",
            "build123",
            "credential 1.2.3",
            "secret-1.2.3",
            "token:1.2.3",
            "password 1.2.3",
            "api_key-1.2.3",
        ):
            value = copy.deepcopy(raw)
            value["clientVersion"] = version
            with self.assertRaises(ValueError):
                qualify.sanitize_live_result(value, self.manifest)

    def test_live_results_require_manifest_supported_cells(self):
        raw = {
            "profile": "generic-agent-skills",
            "clientVersion": "1.2.3",
            "modelClass": "general",
            "installation": {"scope": "global", "mode": "link", "status": "pass"},
            "cases": [
                {
                    "id": case["id"],
                    "repetitions": case["repetitions"],
                    "passes": case["repetitions"],
                    "triggered": True,
                    "forbiddenObserved": False,
                }
                for case in self.manifest["liveCases"]
            ],
        }
        with self.assertRaises(ValueError):
            qualify.sanitize_live_result(raw, self.manifest)
        supported = copy.deepcopy(raw)
        supported["installation"] = {
            "scope": "project",
            "mode": "link",
            "status": "pass",
        }
        unsupported_result = qualify.sanitize_live_result(supported, self.manifest)
        unsupported_result["installation"] = {
            "scope": "global",
            "mode": "link",
            "status": "pass",
        }
        gate = qualify.evaluate_gate(self.manifest, [unsupported_result], ROOT)
        self.assertFalse(gate["pass"])
        self.assertTrue(
            any("manifest-unsupported installation cell" in item for item in gate["blockers"])
        )
        for profile in self.manifest["profiles"]:
            raw["profile"] = profile["id"]
            for cell in profile["cells"]:
                if cell["support"] != "required":
                    continue
                raw["installation"] = {
                    "scope": cell["scope"],
                    "mode": cell["mode"],
                    "status": "pass",
                }
                qualify.sanitize_live_result(raw, self.manifest)

    def test_gate_requires_live_baselines_supported_link_and_suite_evidence(self):
        deterministic = []
        for profile in self.manifest["profiles"]:
            for cell in profile["cells"]:
                if cell["support"] == "required":
                    deterministic.append(
                        qualify.deterministic_result(
                            self.manifest, profile["id"], cell["scope"], cell["mode"]
                        )
                    )
        blocked = qualify.evaluate_gate(self.manifest, deterministic, ROOT)
        self.assertFalse(blocked["pass"])
        self.assertTrue(any("live-host" in item for item in blocked["blockers"]))
        complete = list(deterministic)
        for profile in self.manifest["profiles"]:
            raw = {
                "profile": profile["id"],
                "clientVersion": "1.0.0",
                "modelClass": "general",
                "installation": {
                    "scope": "project",
                    "mode": "copy",
                    "status": "pass",
                },
                "cases": [
                    {
                        "id": case["id"],
                        "repetitions": case["repetitions"],
                        "passes": case["repetitions"],
                        "triggered": True,
                        "forbiddenObserved": False,
                    }
                    for case in self.manifest["liveCases"]
                ],
            }
            complete.append(qualify.sanitize_live_result(raw, self.manifest))
        link = copy.deepcopy(raw)
        link["profile"] = "copilot-vscode"
        link["installation"]["mode"] = "link"
        complete.append(qualify.sanitize_live_result(link, self.manifest))
        evaluated = qualify.evaluate_gate(self.manifest, complete, ROOT)
        self.assertFalse(evaluated["pass"])
        self.assertFalse(
            any("live-host result" in item or "live baseline" in item for item in evaluated["blockers"]),
            evaluated["blockers"],
        )
        self.assertTrue(
            any("deterministic suite evidence is missing" in item for item in evaluated["blockers"])
        )

        duplicate = qualify.evaluate_gate(self.manifest, complete + [complete[0]], ROOT)
        self.assertFalse(duplicate["pass"])
        failed = copy.deepcopy(complete)
        failed[-1]["cases"][0]["status"] = "not-executed"
        self.assertFalse(qualify.evaluate_gate(self.manifest, failed, ROOT)["pass"])


if __name__ == "__main__":
    unittest.main()
