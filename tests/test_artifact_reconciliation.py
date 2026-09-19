import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests.test_artifact_contracts import valid_handoff


ROOT = Path(__file__).resolve().parents[1]
RECONCILE = ROOT / "skills" / "sdlc" / "scripts" / "reconcile_artifacts.py"
VALIDATE = ROOT / "skills" / "sdlc" / "scripts" / "validate_artifacts.py"
SCRATCH = ROOT / ".test-tmp" / "artifact-reconciliation"


SECTIONS = {
    "Problem": "Teams maintain duplicate requirements documents.",
    "Users and value": "Maintainers reuse one durable specification.",
    "Outcome": "One external specification satisfies the PRD contract.",
    "Goals": "- Reuse the source.",
    "Out of scope": "- Remote retrieval.",
    "Scenarios": "1. A maintainer reconciles a local specification.",
    "Requirements": (
        "- **FR-1**: The tool maps local requirements.\n"
        "- **FR-2**: The tool rejects stale approval."
    ),
    "Validation": (
        "- **AC-1** (`FR-1`): Mapped requirements retain stable IDs.\n"
        "- **AC-2** (`FR-2`): Digest drift blocks validation."
    ),
    "Security considerations": "Only project-confined local files are read.",
    "Dependencies": "- Python standard library.",
    "Metrics": "Behavioral acceptance criteria are sufficient.",
    "Open questions": "None.",
    "Approval": (
        "- Status: Approved\n"
        "- Approver: Product owner\n"
        "- Evidence: decisions/spec-approval.md\n"
        "- Approved version: 2"
    ),
}


def markdown_source(kind="generic-spec", *, identifier="external-search", version=2):
    title = {
        "generic-spec": "Specification",
        "feature-design": "Feature design",
        "issue-export": "Issue export",
        "repository-prd": "Repository requirements",
    }[kind]
    frontmatter = (
        "---\n"
        f"id: {identifier}\n"
        f"version: {version}\n"
        "status: approved\n"
        "---\n\n"
    )
    return frontmatter + f"# {title}\n\n" + "\n\n".join(
        f"## {heading}\n{content}" for heading, content in SECTIONS.items()
    ) + "\n"


def structured_source():
    return {
        "id": "external-search",
        "version": 2,
        "status": "approved",
        "problem": SECTIONS["Problem"],
        "targetUsers": SECTIONS["Users and value"],
        "outcome": SECTIONS["Outcome"],
        "goals": ["Reuse the source."],
        "nonGoals": ["Remote retrieval."],
        "scenarios": ["A maintainer reconciles a local specification."],
        "requirements": [
            {"id": "FR-1", "text": "The tool maps local requirements."},
            {"id": "FR-2", "text": "The tool rejects stale approval."},
        ],
        "acceptance": [
            {
                "id": "AC-1",
                "requirements": ["FR-1"],
                "text": "Mapped requirements retain stable IDs.",
            },
            {
                "id": "AC-2",
                "requirements": ["FR-2"],
                "text": "Digest drift blocks validation.",
            },
        ],
        "dataSecurity": "Only project-confined local files are read.",
        "constraints": ["Python standard library."],
        "successMeasures": ["Behavioral acceptance criteria are sufficient."],
        "openDecisions": [],
        "approval": {
            "status": "approved",
            "approver": "Product owner",
            "evidence": "decisions/spec-approval.md",
            "approvedVersion": 2,
        },
    }


class ReconciliationCliTests(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(SCRATCH, ignore_errors=True)
        (SCRATCH / "docs").mkdir(parents=True)
        self.source = SCRATCH / "docs" / "spec.md"
        self.report = SCRATCH / ".sdlc" / "reconciliation" / "external-search.json"

    def tearDown(self):
        shutil.rmtree(SCRATCH, ignore_errors=True)

    def run_reconcile(self, *arguments):
        return subprocess.run(
            [sys.executable, str(RECONCILE), *map(str, arguments)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def run_validate(self, *arguments):
        return subprocess.run(
            [sys.executable, str(VALIDATE), *map(str, arguments)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def reconcile(self, kind="generic-spec", *, view=None, extra=()):
        arguments = [
            "reconcile",
            "--project-root",
            SCRATCH,
            "--source",
            self.source,
            "--kind",
            kind,
            "--report",
            self.report,
        ]
        if view is not None:
            arguments.extend(["--view", view])
        arguments.extend(extra)
        result = self.run_reconcile(*arguments)
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(self.report.read_text(encoding="utf-8"))

    def approve_report(self, report=None):
        report = report or json.loads(self.report.read_text(encoding="utf-8"))
        report["approval"] = {
            "status": "approved",
            "approver": "Product owner",
            "evidence": "decisions/spec-approval.md",
            "approvedVersion": report["normalized"]["version"],
            "approvedSourceDigest": report["source"]["digest"],
            "carryForward": None,
        }
        self.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return report

    def test_reviewed_selector_and_approved_overlay_resolve_raw_conflict_and_gap(self):
        source = markdown_source().replace(
            f"## Out of scope\n{SECTIONS['Out of scope']}\n\n", ""
        )
        source += "\n## Goals\n- Prefer the explicitly reviewed goal.\n"
        self.source.write_text(source, encoding="utf-8")
        report = self.reconcile()
        goal_conflict = next(
            item for item in report["conflicts"] if item["target"] == "/goals"
        )
        report["mappings"].append(
            {
                "target": "/goals",
                "source": {"selector": goal_conflict["sources"][1]},
                "transform": "identity",
                "confidence": "reviewed",
            }
        )
        report["overlay"] = {
            "sections": {"nonGoals": "- Do not retrieve remote content."},
            "approvalEvidence": "decisions/reconciliation-review.md",
        }
        report["mappings"] = sorted(
            report["mappings"],
            key=lambda item: (item["target"], item["source"]["selector"]),
        )
        self.approve_report(report)

        result = self.run_reconcile(
            "validate",
            "--project-root",
            SCRATCH,
            "--report",
            self.report,
            "--require-approved",
        )
        self.assertEqual(0, result.returncode, result.stderr)

        report["overlay"]["approvalEvidence"] = None
        self.report.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
        result = self.run_reconcile(
            "validate", "--project-root", SCRATCH, "--report", self.report
        )
        self.assertEqual(3, result.returncode)
        self.assertIn("review approval evidence", result.stderr)

    def test_structured_canonical_values_require_native_equivalent_substance(self):
        invalid_cases = {
            "empty canonical array": ("goals", []),
            "empty canonical text": ("problem", "  "),
            "empty requirement text": (
                "requirements",
                [{"id": "FR-1", "text": ""}],
            ),
            "empty criterion text": (
                "acceptance",
                [{"id": "AC-1", "requirements": ["FR-1"], "text": ""}],
            ),
            "empty open decision component": (
                "openDecisions",
                [
                    {
                        "decision": "Choose storage",
                        "owner": "",
                        "blocking": False,
                        "resolution": "Use local storage",
                    }
                ],
            ),
            "empty approval component": (
                "approval",
                {
                    "status": "approved",
                    "approver": "",
                    "evidence": "decisions/spec-approval.md",
                    "approvedVersion": 2,
                },
            ),
        }
        self.source = SCRATCH / "docs" / "spec.json"
        for label, (field, value) in invalid_cases.items():
            with self.subTest(label=label):
                data = structured_source()
                data["openDecisions"] = [
                    {
                        "decision": "No open decisions remain",
                        "owner": "Product owner",
                        "blocking": False,
                        "resolution": "Resolved before approval",
                    }
                ]
                data[field] = value
                self.source.write_text(json.dumps(data), encoding="utf-8")
                self.report.unlink(missing_ok=True)
                report = self.reconcile("structured-spec")
                self.approve_report(report)
                result = self.run_reconcile(
                    "validate",
                    "--project-root",
                    SCRATCH,
                    "--report",
                    self.report,
                    "--require-approved",
                )
                self.assertEqual(3, result.returncode, label)
                self.assertIn("substantive", result.stderr, label)

    def test_structured_data_security_object_normalizes_stably_and_rejects_boundaries(self):
        self.source = SCRATCH / "docs" / "spec.json"
        data = structured_source()
        data["openDecisions"] = [
            {
                "decision": "No open decisions remain",
                "owner": "Product owner",
                "blocking": False,
                "resolution": "Resolved before approval",
            }
        ]
        data["dataSecurity"] = {
            "security": "No network access",
            "privacy": "Local processing",
            "permissions": "Project files only",
        }
        self.source.write_text(json.dumps(data), encoding="utf-8")
        view = SCRATCH / "docs" / "generated-prd.md"
        report = self.reconcile("structured-spec", view=view)
        self.approve_report(report)
        result = self.run_reconcile(
            "render",
            "--project-root",
            SCRATCH,
            "--report",
            self.report,
            "--output",
            view,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        rendered = view.read_text(encoding="utf-8")
        self.assertIn(
            "## Data, permissions, privacy, and security\n"
            "- permissions: Project files only\n"
            "- privacy: Local processing\n"
            "- security: No network access",
            rendered,
        )

        invalid_objects = (
            {},
            {"privacy": ""},
            {"": "Local processing"},
            {"privacy": {"scope": "local"}},
            {"privacy": ["local"]},
            {"privacy": 1},
        )
        for value in invalid_objects:
            with self.subTest(value=value):
                data["dataSecurity"] = value
                self.source.write_text(json.dumps(data), encoding="utf-8")
                self.report.unlink(missing_ok=True)
                report = self.reconcile("structured-spec")
                self.approve_report(report)
                result = self.run_reconcile(
                    "validate",
                    "--project-root",
                    SCRATCH,
                    "--report",
                    self.report,
                    "--require-approved",
                )
                self.assertEqual(3, result.returncode)
                self.assertRegex(result.stderr, "canonical|substantive|named object")

    def test_reconcile_refuses_overwrite_and_update_preserves_reviewed_state(self):
        self.source.write_text(markdown_source(), encoding="utf-8")
        result = self.run_reconcile(
            "reconcile",
            "--project-root",
            SCRATCH,
            "--source",
            self.source,
            "--kind",
            "generic-spec",
            "--report",
            self.report,
            "--update",
        )
        self.assertEqual(3, result.returncode)
        self.assertIn("does not exist", result.stderr)
        report = self.reconcile()
        report["mappings"][0]["confidence"] = "reviewed"
        report["overlay"]["approvalEvidence"] = "decisions/reconciliation-review.md"
        report["superseded"] = [
            {
                "source": "heading:Validation#line-30",
                "replacedBy": "AC-2",
                "reason": "Approved scope decision",
                "approvalEvidence": "decisions/spec-approval.md",
            }
        ]
        self.approve_report(report)
        before = json.dumps(report, indent=2, sort_keys=True) + "\n"
        self.report.write_text(before, encoding="utf-8")

        result = self.run_reconcile(
            "reconcile",
            "--project-root",
            SCRATCH,
            "--source",
            self.source,
            "--kind",
            "generic-spec",
            "--report",
            self.report,
        )
        self.assertEqual(3, result.returncode)
        self.assertIn("--update or --replace", result.stderr)
        self.assertEqual(before, self.report.read_text(encoding="utf-8"))

        self.source.write_text(markdown_source() + "\n", encoding="utf-8")
        updated = self.reconcile(extra=("--update",))
        self.assertEqual("draft", updated["approval"]["status"])
        self.assertEqual(report["source"]["digest"], updated["source"]["priorDigest"])
        self.assertEqual(2, updated["source"]["priorVersion"])
        self.assertEqual(report["superseded"], updated["superseded"])
        self.assertEqual(
            "reviewed",
            next(
                item
                for item in updated["mappings"]
                if item["target"] == report["mappings"][0]["target"]
            )["confidence"],
        )
        self.assertEqual(
            "decisions/reconciliation-review.md",
            updated["overlay"]["approvalEvidence"],
        )

        self.report.write_text("{malformed", encoding="utf-8")
        malformed = self.report.read_bytes()
        result = self.run_reconcile(
            "reconcile",
            "--project-root",
            SCRATCH,
            "--source",
            self.source,
            "--kind",
            "generic-spec",
            "--report",
            self.report,
            "--update",
        )
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(malformed, self.report.read_bytes())

    def test_replace_requires_deliberate_confirmation_and_carry_forward_on_noop_drift(self):
        self.source.write_text(markdown_source(), encoding="utf-8")
        report = self.approve_report(self.reconcile())
        old_digest = report["source"]["digest"]
        self.source.write_text(markdown_source() + "\n", encoding="utf-8")
        updated = self.reconcile(extra=("--update",))
        self.assertEqual(old_digest, updated["source"]["priorDigest"])
        updated["approval"] = {
            "status": "approved",
            "approver": "Product owner",
            "evidence": "decisions/spec-approval.md",
            "approvedVersion": 2,
            "approvedSourceDigest": updated["source"]["digest"],
            "carryForward": None,
        }
        self.report.write_text(
            json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        result = self.run_reconcile(
            "validate", "--project-root", SCRATCH, "--report", self.report
        )
        self.assertEqual(3, result.returncode)
        self.assertIn("carry-forward", result.stderr)

        updated["approval"]["carryForward"] = "decisions/noop-carry-forward.md"
        self.report.write_text(
            json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        result = self.run_reconcile(
            "validate", "--project-root", SCRATCH, "--report", self.report
        )
        self.assertEqual(0, result.returncode, result.stderr)

        result = self.run_reconcile(
            "reconcile",
            "--project-root",
            SCRATCH,
            "--source",
            self.source,
            "--kind",
            "generic-spec",
            "--report",
            self.report,
            "--replace",
            "--confirm-destructive-replace",
            "wrong-id",
        )
        self.assertEqual(3, result.returncode)
        replaced = self.reconcile(
            extra=(
                "--replace",
                "--confirm-destructive-replace",
                "external-search",
            )
        )
        self.assertIsNone(replaced["source"]["priorDigest"])

    def test_repeated_updates_retain_last_approved_provenance_and_version_controls(self):
        self.source.write_text(markdown_source(), encoding="utf-8")
        approved_a = self.approve_report(self.reconcile())
        digest_a = approved_a["source"]["digest"]

        self.source.write_text(markdown_source() + "\nB\n", encoding="utf-8")
        self.reconcile(extra=("--update",))
        updated_b = self.reconcile(extra=("--update",))
        self.assertEqual(digest_a, updated_b["source"]["priorDigest"])
        self.assertEqual(2, updated_b["source"]["priorVersion"])

        updated_b = self.approve_report(updated_b)
        result = self.run_reconcile(
            "validate", "--project-root", SCRATCH, "--report", self.report
        )
        self.assertEqual(3, result.returncode)
        self.assertIn("carry-forward", result.stderr)

        updated_b["approval"]["carryForward"] = "decisions/noop-carry-forward.md"
        self.report.write_text(
            json.dumps(updated_b, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result = self.run_reconcile(
            "validate", "--project-root", SCRATCH, "--report", self.report
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_unvalidated_carry_forward_cannot_become_provenance_anchor(self):
        self.source.write_text(markdown_source(), encoding="utf-8")
        approved_a = self.approve_report(self.reconcile())
        digest_a = approved_a["source"]["digest"]
        self.source.write_text(markdown_source() + "\nB\n", encoding="utf-8")
        updated_b = self.reconcile(extra=("--update",))
        updated_b = self.approve_report(updated_b)
        updated_b["approval"]["carryForward"] = "TBD"
        self.report.write_text(
            json.dumps(updated_b, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        repeated_b = self.reconcile(extra=("--update",))

        self.assertEqual(digest_a, repeated_b["source"]["priorDigest"])
        self.assertEqual(2, repeated_b["source"]["priorVersion"])

        self.source.write_text(
            markdown_source(version=3).replace(
                "Approved version: 2", "Approved version: 3"
            )
            + "\nC\n",
            encoding="utf-8",
        )
        self.reconcile(extra=("--update",))
        updated_c = self.reconcile(extra=("--update",))
        self.assertEqual(2, updated_c["source"]["priorVersion"])
        self.approve_report(updated_c)
        result = self.run_reconcile(
            "validate", "--project-root", SCRATCH, "--report", self.report
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_invalid_approved_identity_cannot_replace_last_valid_anchor(self):
        self.source.write_text(markdown_source(), encoding="utf-8")
        approved_a = self.approve_report(self.reconcile())
        digest_a = approved_a["source"]["digest"]
        self.source.write_text(markdown_source() + "\nB\n", encoding="utf-8")
        forged_b = self.reconcile(extra=("--update",))
        forged_b["approval"] = {
            "status": "approved",
            "approver": None,
            "evidence": None,
            "approvedVersion": 2,
            "approvedSourceDigest": forged_b["source"]["digest"],
            "carryForward": "decisions/forged-carry-forward.md",
        }
        self.report.write_text(
            json.dumps(forged_b, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        repeated_b = self.reconcile(extra=("--update",))

        self.assertEqual(digest_a, repeated_b["source"]["priorDigest"])
        self.assertEqual(2, repeated_b["source"]["priorVersion"])
        self.approve_report(repeated_b)
        result = self.run_reconcile(
            "validate", "--project-root", SCRATCH, "--report", self.report
        )
        self.assertEqual(3, result.returncode)
        self.assertIn("carry-forward", result.stderr)

    def test_valid_approved_identity_advances_provenance_anchor(self):
        self.source.write_text(markdown_source(), encoding="utf-8")
        self.approve_report(self.reconcile())
        self.source.write_text(markdown_source() + "\nB\n", encoding="utf-8")
        approved_b = self.reconcile(extra=("--update",))
        approved_b = self.approve_report(approved_b)
        approved_b["approval"]["carryForward"] = "decisions/noop-carry-forward.md"
        self.report.write_text(
            json.dumps(approved_b, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        repeated_b = self.reconcile(extra=("--update",))

        self.assertEqual(approved_b["source"]["digest"], repeated_b["source"]["priorDigest"])
        self.assertEqual(2, repeated_b["source"]["priorVersion"])

    def test_update_preserves_generated_view_authority_when_view_is_omitted(self):
        self.source.write_text(markdown_source(), encoding="utf-8")
        view = SCRATCH / "docs" / "generated-prd.md"
        original = self.reconcile(view=view)
        self.source.write_text(markdown_source() + "\n", encoding="utf-8")

        updated = self.reconcile(extra=("--update",))

        self.assertEqual("generated-view", updated["authority"]["mode"])
        self.assertEqual(
            original["authority"]["generatedView"],
            updated["authority"]["generatedView"],
        )
        self.assertTrue(view.exists())

    def test_inspect_normalizes_all_five_source_kinds_without_writing(self):
        for kind in (
            "generic-spec",
            "feature-design",
            "issue-export",
            "repository-prd",
        ):
            with self.subTest(kind=kind):
                self.source.write_text(markdown_source(kind), encoding="utf-8")
                result = self.run_reconcile(
                    "inspect",
                    "--project-root",
                    SCRATCH,
                    "--source",
                    self.source,
                    "--kind",
                    kind,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual("external-search", payload["id"])
                self.assertEqual(["FR-1", "FR-2"], payload["functionalRequirements"])
                self.assertEqual(0, payload["missingCount"])
                self.assertFalse(self.report.exists())

        structured = SCRATCH / "docs" / "spec.json"
        structured.write_text(
            json.dumps(structured_source(), sort_keys=True), encoding="utf-8"
        )
        result = self.run_reconcile(
            "inspect",
            "--project-root",
            SCRATCH,
            "--source",
            structured,
            "--kind",
            "structured-spec",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("external-search", json.loads(result.stdout)["id"])

    def test_reconcile_writes_draft_direct_report_with_provenance_and_stable_order(self):
        self.source.write_text(markdown_source(), encoding="utf-8")
        report = self.reconcile()

        self.assertEqual(1, report["schemaVersion"])
        self.assertEqual("direct", report["authority"]["mode"])
        self.assertEqual("docs/spec.md", report["authority"]["artifact"])
        self.assertIsNone(report["authority"]["generatedView"])
        self.assertEqual(
            "sha256:" + hashlib.sha256(self.source.read_bytes()).hexdigest(),
            report["source"]["digest"],
        )
        self.assertEqual("draft", report["approval"]["status"])
        self.assertEqual("3.5.3", report["generated"]["toolVersion"])
        self.assertEqual(
            sorted(
                report["mappings"],
                key=lambda item: (item["target"], item["source"]["selector"]),
            ),
            report["mappings"],
        )

    def test_assigned_ids_are_stable_across_reruns_and_structured_key_reordering(self):
        data = structured_source()
        for item in data["requirements"] + data["acceptance"]:
            item.pop("id")
        self.source = SCRATCH / "docs" / "spec.json"
        self.source.write_text(json.dumps(data), encoding="utf-8")
        first = self.reconcile("structured-spec")
        first_ids = first["assignedIds"]

        self.source.write_text(
            json.dumps(dict(reversed(list(data.items())))), encoding="utf-8"
        )
        second = self.reconcile("structured-spec", extra=("--update",))
        self.assertEqual(first_ids, second["assignedIds"])

    def test_validate_accepts_exact_and_reviewed_mappings_and_matches_native_result(self):
        self.source.write_text(markdown_source(), encoding="utf-8")
        report = self.reconcile()
        report["mappings"][0]["confidence"] = "reviewed"
        self.approve_report(report)

        result = self.run_reconcile(
            "validate",
            "--project-root",
            SCRATCH,
            "--report",
            self.report,
            "--require-approved",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(["FR-1", "FR-2"], payload["functionalRequirements"])

        result = self.run_validate(
            "validate-prd",
            "--reconciliation",
            self.report,
            "--project-root",
            SCRATCH,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("external-search", json.loads(result.stdout)["id"])

    def test_missing_sections_and_conflicting_alias_sections_block_approval(self):
        missing = markdown_source().replace(
            f"## Out of scope\n{SECTIONS['Out of scope']}\n\n", ""
        )
        self.source.write_text(missing, encoding="utf-8")
        report = self.reconcile()
        self.assertIn("/nonGoals", [item["target"] for item in report["missing"]])

        result = self.run_reconcile(
            "validate",
            "--project-root",
            SCRATCH,
            "--report",
            self.report,
            "--require-approved",
        )
        self.assertEqual(3, result.returncode)
        self.assertIn("missing canonical field", result.stderr)

        self.source.write_text(
            markdown_source()
            + "\n## Non-goals\n- Contradictory replacement scope.\n",
            encoding="utf-8",
        )
        report = self.reconcile(extra=("--update",))
        self.assertTrue(report["conflicts"])

    def test_unknown_fr_and_incomplete_ac_coverage_block_validation(self):
        self.source.write_text(
            markdown_source().replace("(`FR-2`)", "(`FR-9`)"), encoding="utf-8"
        )
        report = self.reconcile()
        self.approve_report(report)
        result = self.run_reconcile(
            "validate",
            "--project-root",
            SCRATCH,
            "--report",
            self.report,
            "--require-approved",
        )
        self.assertEqual(3, result.returncode)
        self.assertIn("unknown functional requirement FR-9", result.stderr)

        self.source.write_text(
            markdown_source().replace(
                "- **AC-2** (`FR-2`): Digest drift blocks validation.", ""
            ),
            encoding="utf-8",
        )
        report = self.reconcile(extra=("--update",))
        self.approve_report(report)
        result = self.run_reconcile(
            "validate",
            "--project-root",
            SCRATCH,
            "--report",
            self.report,
            "--require-approved",
        )
        self.assertEqual(3, result.returncode)
        self.assertIn("FR-2 has no acceptance criterion", result.stderr)

    def test_digest_drift_and_wrong_approval_binding_block(self):
        self.source.write_text(markdown_source(), encoding="utf-8")
        report = self.reconcile()
        report = self.approve_report(report)
        report["approval"]["approvedVersion"] = 1
        self.report.write_text(json.dumps(report), encoding="utf-8")
        result = self.run_reconcile(
            "validate", "--project-root", SCRATCH, "--report", self.report
        )
        self.assertEqual(3, result.returncode)
        self.assertIn("approved version", result.stderr)

        report["approval"]["approvedVersion"] = 2
        self.report.write_text(json.dumps(report), encoding="utf-8")
        self.source.write_text(markdown_source() + "\n", encoding="utf-8")
        result = self.run_reconcile(
            "validate", "--project-root", SCRATCH, "--report", self.report
        )
        self.assertEqual(3, result.returncode)
        self.assertIn("source digest", result.stderr)

    def test_generated_view_nomination_render_and_tamper_detection(self):
        self.source.write_text(markdown_source(), encoding="utf-8")
        view = SCRATCH / "docs" / "generated-prd.md"
        report = self.reconcile(view=view)
        self.assertEqual("generated-view", report["authority"]["mode"])
        rendered = view.read_text(encoding="utf-8")
        self.assertIn("GENERATED FILE", rendered)
        self.assertIn("Source digest:", rendered)
        self.assertIn("Generation command:", rendered)
        self.approve_report(report)

        result = self.run_reconcile(
            "validate", "--project-root", SCRATCH, "--report", self.report
        )
        self.assertEqual(3, result.returncode)
        self.assertIn("generated view", result.stderr)
        result = self.run_reconcile(
            "render",
            "--project-root",
            SCRATCH,
            "--report",
            self.report,
            "--output",
            view,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        rendered = view.read_text(encoding="utf-8")
        result = self.run_reconcile(
            "validate", "--project-root", SCRATCH, "--report", self.report
        )
        self.assertEqual(0, result.returncode, result.stderr)
        view.write_text(rendered + "\nmanual edit\n", encoding="utf-8")
        result = self.run_reconcile(
            "validate", "--project-root", SCRATCH, "--report", self.report
        )
        self.assertEqual(3, result.returncode)
        self.assertIn("generated view digest", result.stderr)

        other = SCRATCH / "docs" / "other.md"
        result = self.run_reconcile(
            "render",
            "--project-root",
            SCRATCH,
            "--report",
            self.report,
            "--output",
            other,
        )
        self.assertEqual(3, result.returncode)
        self.assertIn("nominated", result.stderr)

    def test_duplicate_authority_and_superseded_record_validation(self):
        self.source.write_text(markdown_source(), encoding="utf-8")
        report = self.reconcile()
        report["authority"]["generatedView"] = "docs/generated-prd.md"
        report["superseded"] = [
            {
                "source": "heading:Validation#line-30",
                "replacedBy": "AC-2",
                "reason": "Approved scope decision",
                "approvalEvidence": "decisions/spec-approval.md",
            }
        ]
        self.approve_report(report)
        result = self.run_reconcile(
            "validate", "--project-root", SCRATCH, "--report", self.report
        )
        self.assertEqual(3, result.returncode)
        self.assertIn("authority", result.stderr)

    def test_rejects_duplicate_json_keys_paths_links_and_remote_sources(self):
        self.source.write_text(markdown_source(), encoding="utf-8")
        self.report.parent.mkdir(parents=True)
        self.report.write_text(
            '{"schemaVersion":1,"schemaVersion":1}', encoding="utf-8"
        )
        result = self.run_reconcile(
            "validate", "--project-root", SCRATCH, "--report", self.report
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("duplicate", result.stderr.lower())

        result = self.run_reconcile(
            "inspect",
            "--project-root",
            SCRATCH,
            "--source",
            "https://example.invalid/issue/1",
            "--kind",
            "issue-export",
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("local", result.stderr)

        result = self.run_reconcile(
            "inspect",
            "--project-root",
            SCRATCH,
            "--source",
            SCRATCH.parent / "outside.md",
            "--kind",
            "generic-spec",
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("within the project", result.stderr)

        if hasattr(os, "symlink"):
            outside = SCRATCH.parent / "outside-spec.md"
            outside.write_text(markdown_source(), encoding="utf-8")
            link = SCRATCH / "docs" / "linked.md"
            try:
                link.symlink_to(outside)
            except OSError:
                pass
            else:
                result = self.run_reconcile(
                    "inspect",
                    "--project-root",
                    SCRATCH,
                    "--source",
                    link,
                    "--kind",
                    "generic-spec",
                )
                self.assertEqual(2, result.returncode)
                self.assertIn("linked or reparse", result.stderr)
            outside.unlink(missing_ok=True)

    def test_atomic_write_failure_preserves_existing_report(self):
        spec = importlib.util.spec_from_file_location("reconcile_artifacts", RECONCILE)
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(RECONCILE.parent))
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        self.report.parent.mkdir(parents=True)
        self.report.write_text("original\n", encoding="utf-8")
        with mock.patch.object(module.os, "replace", side_effect=OSError("blocked")):
            with self.assertRaises(module.ReconciliationError):
                module.atomic_write_text(self.report, "replacement\n")
        self.assertEqual("original\n", self.report.read_text(encoding="utf-8"))
        self.assertEqual([], list(self.report.parent.glob("*.tmp")))

    def test_plan_accepts_new_identity_fields_and_legacy_prd_path(self):
        self.source.write_text(markdown_source(), encoding="utf-8")
        report = self.reconcile()
        self.approve_report(report)
        plan = SCRATCH / "plan.md"
        plan.write_text(
            """---
type: implementation-plan
prd-artifact: docs/spec.md
prd-reconciliation: .sdlc/reconciliation/external-search.json
prd-id: external-search
prd-version: 2
---

# Plan

| Task | PRD refs | Outcome | Prerequisites | Consumes | Produces | Execution | Verification |
|------|----------|---------|---------------|----------|----------|-----------|--------------|
| mapping | FR-1, FR-2, AC-1, AC-2 | Implement mapping | none | approved requirements | mapper | sequential | Focused tests pass |
""",
            encoding="utf-8",
        )
        result = self.run_validate(
            "validate-plan", plan, "--project-root", SCRATCH
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            ".sdlc/reconciliation/external-search.json",
            json.loads(result.stdout)["prd"]["reconciliation"],
        )

        native = SCRATCH / "docs" / "native.md"
        native.write_text(
            markdown_source()
            .replace("id: external-search", "type: prd\nid: external-search")
            .replace("## Problem\n", "## Problem and context\n")
            .replace("## Users and value\n", "## Target users and benefit\n")
            .replace("## Out of scope\n", "## Non-goals\n")
            .replace("## Scenarios\n", "## User scenarios\n")
            .replace("## Requirements\n", "## Functional requirements\n")
            .replace("## Validation\n", "## Acceptance criteria\n")
            .replace(
                "## Security considerations\n",
                "## Data, permissions, privacy, and security\n",
            )
            .replace("## Dependencies\n", "## Constraints and dependencies\n")
            .replace("## Metrics\n", "## Success measures\n")
            .replace("## Open questions\n", "## Open decisions\n"),
            encoding="utf-8",
        )
        legacy_plan = plan.read_text(encoding="utf-8").replace(
            "prd-artifact: docs/spec.md\n"
            "prd-reconciliation: .sdlc/reconciliation/external-search.json",
            "prd-path: docs/native.md",
        )
        plan.write_text(legacy_plan, encoding="utf-8")
        result = self.run_validate(
            "validate-plan", plan, "--project-root", SCRATCH
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_handoff_accepts_authoritative_artifact_and_reconciliation_identity(self):
        self.source.write_text(markdown_source(), encoding="utf-8")
        report = self.reconcile()
        self.approve_report(report)
        handoff = valid_handoff()
        handoff["prd"] = {
            "applicability": "applicable",
            "artifact": "docs/spec.md",
            "reconciliation": ".sdlc/reconciliation/external-search.json",
            "id": "external-search",
            "version": 2,
            "declaredStatus": "approved",
        }
        handoff["requirements"] = {
            "functional": ["FR-1", "FR-2"],
            "acceptance": ["AC-1", "AC-2"],
            "delivered": ["FR-1", "FR-2", "AC-1", "AC-2"],
        }
        handoff_path = SCRATCH / "handoff.json"
        handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

        result = self.run_validate(
            "validate-handoff", handoff_path, "--project-root", SCRATCH
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(
            json.loads(result.stdout)["prd"]["identityMatchedLocalArtifact"]
        )
        result = self.run_validate(
            "render-handoff", handoff_path, "--forge", "github"
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("docs/spec.md", result.stdout)
        self.assertIn(".sdlc/reconciliation/external-search.json", result.stdout)
