import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "sdlc" / "scripts"
SCRIPT = SCRIPTS / "validate_artifacts.py"
sys.path.insert(0, str(SCRIPTS))


def operator_state():
    return {
        "schemaVersion": 1,
        "task": {
            "id": "search-export",
            "rigor": "standard",
            "facts": {
                "nonTrivial": True,
                "beforeCompletion": False,
                "bugOrUnexplainedFailure": False,
                "newCapability": True,
                "userOrProductFacing": True,
                "significantInternalCapability": False,
                "codeOrConfigurationChange": True,
                "newOrChangedBehavior": True,
                "verificationInScope": True,
                "securitySurfaceAffected": False,
                "operationalSurfaceAffected": False,
                "learningSignalPresent": False,
                "coreUpgrade": False,
            },
        },
        "modules": [
            {
                "id": "prd",
                "source": "core",
                "order": 3,
                "configured": "enabled",
                "trigger": {
                    "state": "matched",
                    "basis": [
                        "task.facts.newCapability",
                        "task.facts.userOrProductFacing",
                    ],
                    "assertedBy": "runtime",
                },
                "evidence": {
                    "status": "stale/unverified",
                    "items": [],
                    "gaps": ["Approval evidence targets an older version"],
                },
                "instruction": {
                    "state": "would-load",
                    "reason": "Evidence must be refreshed",
                },
            },
            {
                "id": "review",
                "source": "core",
                "order": 17,
                "configured": "disabled",
                "trigger": {
                    "state": "not-matched",
                    "basis": ["task.facts.beforeCompletion"],
                    "assertedBy": "deterministic-core-rule",
                },
                "evidence": {
                    "status": "configured-disabled",
                    "items": [],
                    "gaps": [],
                },
                "instruction": {
                    "state": "skipped",
                    "reason": "Disabled by project configuration",
                },
            },
        ],
        "configuredDisabledModules": ["review"],
        "blockers": [
            {"module": "prd", "message": "Approval evidence is stale"}
        ],
    }


def extension_module(source="project-extension", asserted_by="runtime"):
    return {
        "id": "legacy-check",
        "source": source,
        "order": 18,
        "configured": "enabled",
        "trigger": {
            "state": "matched",
            "basis": ["Extension trigger matched at runtime"],
            "assertedBy": asserted_by,
        },
        "evidence": {
            "status": "missing",
            "items": [],
            "gaps": ["Extension evidence is missing"],
        },
        "instruction": {
            "state": "would-load",
            "reason": "Matched extension evidence is missing",
        },
        "contentDigest": f"sha256:{'a' * 64}",
        "sources": [".sdlc/extensions/legacy-check"],
    }


def replacement_operator_state():
    state = operator_state()
    state["modules"][0]["provider"] = {
        "type": "replacement",
        "id": "custom-prd-provider",
    }
    return state


class OperatorReportTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / ".test-tmp" / "operator-state.json"
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps(operator_state()), encoding="utf-8")

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, arguments)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_explain_is_ordered_and_preserves_disclosures(self):
        result = self.run_cli("explain", "--input", self.path, "--detail", "normal")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("explain", payload["command"])
        self.assertEqual(["prd", "review"], [m["id"] for m in payload["result"]["modules"]])
        self.assertEqual(["review"], payload["result"]["configuredDisabledModules"])
        self.assertIn("supplied as", " ".join(payload["result"]["modules"][0]["reasons"]))
        self.assertEqual("not-assessed", payload["result"]["semanticApproval"])

    def test_preview_marks_stale_matched_module_for_loading(self):
        result = self.run_cli("preview", "--input", self.path, "--detail", "concise")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        modules = {m["id"]: m for m in payload["result"]["modules"]}
        self.assertIs(True, modules["prd"]["wouldLoad"])
        self.assertIs(False, modules["review"]["wouldLoad"])
        self.assertEqual(operator_state()["blockers"], payload["result"]["blockers"])

    def test_render_coverage_concise_keeps_stale_gap_and_disabled_module(self):
        result = self.run_cli(
            "render-coverage", "--input", self.path, "--detail", "concise"
        )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        modules = {m["id"]: m for m in payload["result"]["modules"]}
        self.assertEqual("stale/unverified", modules["prd"]["status"])
        self.assertIn(
            "Approval evidence targets an older version",
            modules["prd"]["recognizedEvidenceOrGap"],
        )
        self.assertEqual(["review"], payload["result"]["configuredDisabledModules"])

    def test_inspection_does_not_read_module_instructions(self):
        import operator_reports

        original = Path.read_text

        def guarded(path, *args, **kwargs):
            if path.name == "MODULE.md":
                raise AssertionError("operator inspection opened MODULE.md")
            return original(path, *args, **kwargs)

        with patch.object(Path, "read_text", guarded):
            for command in ("explain", "preview", "render-coverage"):
                for detail in ("concise", "normal", "detailed"):
                    result = operator_reports.build_report(
                        replacement_operator_state(), command, detail
                    )
                    self.assertEqual(command, result["command"])

    def test_schema_1_omitted_provider_defaults_safely_from_core_configuration(self):
        import operator_reports

        report = operator_reports.build_report(operator_state(), "explain", "normal")
        modules = {module["id"]: module for module in report["result"]["modules"]}
        self.assertEqual({"type": "bundled"}, modules["prd"]["provider"])
        self.assertEqual({"type": "disabled"}, modules["review"]["provider"])

    def test_replacement_provider_round_trips_through_cli(self):
        self.path.write_text(
            json.dumps(replacement_operator_state()), encoding="utf-8"
        )
        result = self.run_cli("preview", "--input", self.path, "--detail", "normal")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(
            {"type": "replacement", "id": "custom-prd-provider"},
            payload["result"]["modules"][0]["provider"],
        )

    def test_every_projection_and_detail_preserves_provider_descriptor(self):
        import operator_reports

        state = replacement_operator_state()
        for command in ("explain", "preview", "render-coverage"):
            for detail in ("concise", "normal", "detailed"):
                with self.subTest(command=command, detail=detail):
                    report = operator_reports.build_report(state, command, detail)
                    self.assertEqual(
                        {"type": "replacement", "id": "custom-prd-provider"},
                        report["result"]["modules"][0]["provider"],
                    )
                    self.assertEqual(
                        {"type": "disabled"},
                        report["result"]["modules"][1]["provider"],
                    )

    def test_provider_descriptor_is_strict_and_configuration_consistent(self):
        import operator_reports
        from artifact_contracts import ContractIssue

        invalid = (
            (None, "E_SCHEMA_TYPE"),
            ({"type": "replacement"}, "E_PROVIDER_ID"),
            ({"type": "replacement", "id": "Not-Kebab"}, "E_PROVIDER_ID"),
            ({"type": "replacement", "id": "a" * 65}, "E_PROVIDER_ID"),
            ({"type": "bundled", "id": "custom-provider"}, "E_PROVIDER_ID"),
            ({"type": "disabled", "id": "custom-provider"}, "E_PROVIDER_ID"),
            ({"type": "other"}, "E_PROVIDER_TYPE"),
        )
        for provider, code in invalid:
            with self.subTest(provider=provider):
                state = operator_state()
                state["modules"][0]["provider"] = provider
                with self.assertRaises(ContractIssue) as raised:
                    operator_reports.validate_operator_state(state)
                self.assertEqual(code, raised.exception.code)

        state = operator_state()
        state["modules"][0]["provider"] = {"type": "disabled"}
        with self.assertRaises(ContractIssue) as raised:
            operator_reports.validate_operator_state(state)
        self.assertEqual("E_PROVIDER_CONFIGURED", raised.exception.code)

        state = operator_state()
        state["modules"][1]["provider"] = {"type": "bundled"}
        with self.assertRaises(ContractIssue) as raised:
            operator_reports.validate_operator_state(state)
        self.assertEqual("E_PROVIDER_CONFIGURED", raised.exception.code)

    def test_explicit_bundled_and_disabled_descriptors_are_preserved(self):
        import operator_reports

        state = operator_state()
        state["modules"][0]["provider"] = {"type": "bundled"}
        state["modules"][1]["provider"] = {"type": "disabled"}
        report = operator_reports.build_report(state, "explain", "concise")
        self.assertEqual(
            [{"type": "bundled"}, {"type": "disabled"}],
            [module["provider"] for module in report["result"]["modules"]],
        )

    def test_provider_selection_does_not_infer_readiness(self):
        import operator_reports

        bundled = operator_reports.build_report(
            operator_state(), "preview", "normal"
        )
        replacement = operator_reports.build_report(
            replacement_operator_state(), "preview", "normal"
        )
        for field in ("evidenceStatus", "instructionState", "wouldLoad", "blockers"):
            self.assertEqual(
                bundled["result"]["modules"][0][field],
                replacement["result"]["modules"][0][field],
            )

    def test_extension_modules_reject_provider_descriptors(self):
        import operator_reports
        from artifact_contracts import ContractIssue

        state = operator_state()
        extension = extension_module()
        extension["provider"] = {"type": "replacement", "id": "extension-provider"}
        state["modules"].append(extension)
        with self.assertRaises(ContractIssue) as raised:
            operator_reports.validate_operator_state(state)
        self.assertEqual("E_MODULE_FIELD", raised.exception.code)

        state = operator_state()
        state["modules"].append(extension_module())
        report = operator_reports.build_report(state, "render-coverage", "detailed")
        self.assertNotIn("provider", report["result"]["modules"][-1])

    def test_operator_schemas_define_conditional_strict_provider_descriptors(self):
        import operator_reports
        from artifact_contracts import ContractIssue

        state_schema = json.loads(
            (
                ROOT
                / "skills"
                / "sdlc"
                / "contracts"
                / "operator-state.schema.json"
            ).read_text(encoding="utf-8")
        )
        result_schema = json.loads(
            (
                ROOT
                / "skills"
                / "sdlc"
                / "contracts"
                / "operator-result.schema.json"
            ).read_text(encoding="utf-8")
        )
        state_module = state_schema["$defs"]["module"]
        result_module = result_schema["$defs"]["module"]
        self.assertIn("provider", state_module["properties"])
        self.assertIn("provider", result_module["properties"])
        self.assertIn("allOf", result_module)
        for schema in (state_schema, result_schema):
            provider = schema["$defs"]["provider"]
            self.assertEqual(
                ["bundled", "disabled", "replacement"],
                provider["properties"]["type"]["enum"],
            )
            self.assertEqual(
                [
                    {
                        "if": {"properties": {"type": {"const": "replacement"}}},
                        "then": {"required": ["id"]},
                        "else": {"not": {"required": ["id"]}},
                    }
                ],
                provider["allOf"],
            )
        self.assertIn(
            {
                "if": {
                    "properties": {"source": {"const": "core"}},
                    "required": ["source"],
                },
                "then": {"required": ["provider"]},
            },
            result_module["allOf"],
        )

        operator_reports.validate_operator_state(replacement_operator_state())
        invalid = replacement_operator_state()
        del invalid["modules"][0]["provider"]["id"]
        with self.assertRaises(ContractIssue) as raised:
            operator_reports.validate_operator_state(invalid)
        self.assertEqual("E_PROVIDER_ID", raised.exception.code)

        invalid = replacement_operator_state()
        invalid["modules"][0]["provider"] = {
            "type": "bundled",
            "id": "custom-prd-provider",
        }
        with self.assertRaises(ContractIssue) as raised:
            operator_reports.validate_operator_state(invalid)
        self.assertEqual("E_PROVIDER_ID", raised.exception.code)

        for command in ("explain", "preview", "render-coverage"):
            for detail in ("concise", "normal", "detailed"):
                with self.subTest(schema_command=command, schema_detail=detail):
                    report = operator_reports.build_report(
                        replacement_operator_state(), command, detail
                    )
                    self.assertEqual(
                        {"type": "replacement", "id": "custom-prd-provider"},
                        report["result"]["modules"][0]["provider"],
                    )

    def test_duplicate_json_key_has_strict_one_line_error(self):
        self.path.write_text(
            '{"schemaVersion":1,"schemaVersion":1}', encoding="utf-8"
        )
        result = self.run_cli("explain", "--input", self.path)
        self.assertEqual(2, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertRegex(
            result.stderr,
            r'^error\[E_JSON_DUPLICATE\] /schemaVersion: duplicate object key "schemaVersion"\n$',
        )

    def test_exact_core_trigger_rules_do_not_guess_missing_facts(self):
        import operator_reports

        task = operator_state()["task"]
        expected = {
            "prd": "matched",
            "debugging": "not-matched",
            "planning": "matched",
            "tdd": "matched",
            "implementation": "matched",
            "testing": "matched",
            "security-auth": "not-matched",
            "operational-readiness": "not-matched",
            "review": "not-matched",
            "pr-handoff": "not-matched",
            "continuous-improvement": "not-matched",
            "accessibility-browser": "undetermined",
        }
        self.assertEqual(
            expected,
            {
                module_id: operator_reports.deterministic_core_trigger(module_id, task)
                for module_id in expected
            },
        )
        del task["facts"]["newCapability"]
        self.assertEqual(
            "undetermined",
            operator_reports.deterministic_core_trigger("prd", task),
        )

    def test_legacy_extension_trigger_accepts_runtime_attribution(self):
        import operator_reports

        for source in ("project-extension", "global-extension"):
            with self.subTest(source=source):
                state = operator_state()
                state["modules"].append(extension_module(source=source))
                report = operator_reports.build_report(state, "preview", "normal")
                extension = report["result"]["modules"][-1]
                self.assertEqual("legacy-check", extension["id"])
                self.assertTrue(extension["triggered"])

    def test_legacy_extension_trigger_rejects_core_rule_attribution(self):
        import operator_reports
        from artifact_contracts import ContractIssue

        for source in ("project-extension", "global-extension"):
            with self.subTest(source=source):
                state = operator_state()
                state["modules"].append(
                    extension_module(
                        source=source,
                        asserted_by="deterministic-core-rule",
                    )
                )
                with self.assertRaises(ContractIssue) as raised:
                    operator_reports.validate_operator_state(state)
                self.assertEqual("E_TRIGGER_ASSERTION", raised.exception.code)
                self.assertEqual(
                    "/modules/2/trigger/assertedBy",
                    raised.exception.pointer,
                )

    def test_enabled_extension_binding_schema_matches_runtime_requirements(self):
        import operator_reports
        from artifact_contracts import ContractIssue

        schema_path = (
            ROOT / "skills" / "sdlc" / "contracts" / "operator-state.schema.json"
        )
        module_schema = json.loads(schema_path.read_text(encoding="utf-8"))[
            "$defs"
        ]["module"]
        self.assertIn(
            {
                "if": {
                    "properties": {
                        "source": {
                            "enum": ["project-extension", "global-extension"]
                        },
                        "configured": {"const": "enabled"},
                    },
                    "required": ["source", "configured"],
                },
                "then": {"required": ["contentDigest", "sources"]},
            },
            module_schema["allOf"],
        )

        state = operator_state()
        extension = extension_module()
        del extension["contentDigest"]
        state["modules"].append(extension)
        with self.assertRaises(ContractIssue) as raised:
            operator_reports.validate_operator_state(state)
        self.assertEqual("E_EXTENSION_DIGEST", raised.exception.code)

        disabled_state = operator_state()
        disabled_extension = extension_module()
        disabled_extension["configured"] = "disabled"
        disabled_extension["trigger"]["state"] = "not-matched"
        disabled_extension["evidence"]["status"] = "configured-disabled"
        disabled_extension["evidence"]["gaps"] = []
        disabled_extension["instruction"] = {
            "state": "skipped",
            "reason": "Disabled by project configuration",
        }
        del disabled_extension["contentDigest"]
        del disabled_extension["sources"]
        disabled_state["modules"].append(disabled_extension)
        disabled_state["configuredDisabledModules"].append("legacy-check")
        operator_reports.validate_operator_state(disabled_state)


if __name__ == "__main__":
    unittest.main()
