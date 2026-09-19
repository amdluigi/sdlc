import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "sdlc" / "scripts" / "validate_artifacts.py"
SCRATCH = ROOT / ".test-tmp" / "artifact-contracts"


def approved_prd(identifier="search-export", version=2):
    return f"""---
type: prd
id: {identifier}
status: approved
version: {version}
---

# Product requirements: Search export

## Problem and context
Users cannot export filtered results.

## Target users and benefit
Analysts can reuse filtered data.

## Outcome
Users export the current result set.

## Goals
- Export filtered results.

## Non-goals
- Scheduled exports are excluded.

## User scenarios
1. An analyst exports a filtered result set.

## Functional requirements
- **FR-1**: The system exports the active filtered result set.
- **FR-2**: The system reports an export failure.

## Acceptance criteria
- **AC-1** (`FR-1`): Exported rows match the active filter.
- **AC-2** (`FR-2`): A failed export returns an actionable error.

## Data, permissions, privacy, and security
Existing result permissions apply.

## Constraints and dependencies
- Existing CSV support is reused.

## Success measures
The acceptance criteria define success.

## Open decisions
None.

## Approval
- Status: Approved
- Approver: Product owner
- Evidence: Approved in issue 42.
- Approved version: {version}
"""


def valid_plan(prd_path="docs/prds/search-export.md"):
    return f"""---
type: implementation-plan
prd-path: {prd_path}
prd-id: search-export
prd-version: 2
---

# Search export implementation plan

| Task | PRD refs | Outcome | Prerequisites | Consumes | Produces | Execution | Verification |
|------|----------|---------|---------------|----------|----------|-----------|--------------|
| contract | FR-1, AC-1 | Define export contract | none | approved PRD | export interface | sequential | Contract test fails before implementation |
| behavior | FR-2, AC-2 | Implement export behavior | contract | export interface | export behavior | sequential | Unit and integration tests pass |
"""


def valid_handoff():
    return {
        "schemaVersion": 1,
        "title": "Add filtered search export",
        "outcome": "Users can export the active filtered result set.",
        "prd": {
            "applicability": "applicable",
            "path": "docs/prds/search-export.md",
            "id": "search-export",
            "version": 2,
            "declaredStatus": "approved",
        },
        "requirements": {
            "functional": ["FR-1", "FR-2"],
            "acceptance": ["AC-1", "AC-2"],
            "delivered": ["FR-1", "FR-2", "AC-1", "AC-2"],
        },
        "scope": ["Export the active filtered result set."],
        "acceptanceEvidence": [
            {
                "acceptanceCriterion": "AC-1",
                "kind": "test",
                "command": "python -m unittest tests.test_export",
                "result": "passed",
                "revision": "abc123",
                "summary": "Filtered rows matched the export.",
            },
            {
                "acceptanceCriterion": "AC-2",
                "kind": "test",
                "command": "python -m unittest tests.test_export_errors",
                "result": "passed",
                "revision": "abc123",
                "summary": "Failures returned actionable errors.",
            },
        ],
        "review": {
            "perspectives": ["correctness", "tests"],
            "findingsResolved": ["Handled empty result sets."],
            "unavailable": [],
        },
        "compatibility": {
            "applicability": "not-applicable",
            "details": [],
            "reason": "No public or persisted contract changed.",
        },
        "rollout": {
            "applicability": "applicable",
            "details": ["Deploy with the ordinary application release."],
            "reason": None,
        },
        "rollback": {
            "applicability": "applicable",
            "details": ["Revert the change and redeploy."],
            "reason": None,
        },
        "risks": [],
        "limitations": [],
        "deferredWork": ["Scheduled exports remain out of scope."],
        "repositoryState": {
            "statusInspected": True,
            "completeDiffInspected": True,
            "revision": "abc123",
            "unrelatedChanges": [],
        },
        "configuredDisabledModules": [],
        "blockers": [],
    }


class ArtifactContractCliTests(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(SCRATCH, ignore_errors=True)
        (SCRATCH / "docs" / "prds").mkdir(parents=True)
        self.prd = SCRATCH / "docs" / "prds" / "search-export.md"
        self.plan = SCRATCH / "plan.md"
        self.prd.write_text(approved_prd(), encoding="utf-8")
        self.plan.write_text(valid_plan(), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(SCRATCH, ignore_errors=True)
        (SCRATCH.parent / "outside-plan.md").unlink(missing_ok=True)

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, arguments)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_validate_prd_accepts_complete_approved_artifact(self):
        result = self.run_cli("validate-prd", self.prd)

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("search-export", payload["id"])
        self.assertEqual(["FR-1", "FR-2"], payload["functionalRequirements"])
        self.assertEqual(["AC-1", "AC-2"], payload["acceptanceCriteria"])
        self.assertEqual(1, payload["schemaVersion"])
        self.assertTrue(payload["contractValid"])
        self.assertEqual("approved", payload["declaredStatus"])
        self.assertEqual("not-assessed", payload["semanticApproval"])
        self.assertIn("Structural validation", payload["notice"])

    def test_validate_prd_rejects_draft_without_explicit_allowance(self):
        self.prd.write_text(
            approved_prd().replace("status: approved", "status: draft", 1),
            encoding="utf-8",
        )

        result = self.run_cli("validate-prd", self.prd)

        self.assertEqual(3, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertIn("error[E_PRD_STATUS] /status:", result.stderr)

    def test_validate_prd_rejects_missing_requirement_mapping(self):
        self.prd.write_text(
            approved_prd().replace("(`FR-2`)", "(`FR-9`)"),
            encoding="utf-8",
        )

        result = self.run_cli("validate-prd", self.prd)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("unknown functional requirement FR-9", result.stderr)
        self.assertEqual(1, len(result.stderr.splitlines()))

    def test_validate_prd_rejects_unknown_identity_field_and_zero_version(self):
        self.prd.write_text(
            approved_prd()
            .replace("version: 2", "version: 0", 1)
            .replace("status: approved", "status: approved\nowner: team-a", 1),
            encoding="utf-8",
        )

        result = self.run_cli("validate-prd", self.prd)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("unknown PRD frontmatter field: owner", result.stderr)
        self.assertEqual(1, len(result.stderr.splitlines()))

    def test_validate_prd_rejects_missing_required_section(self):
        self.prd.write_text(
            approved_prd().replace(
                "## Success measures\nThe acceptance criteria define success.\n\n",
                "",
            ),
            encoding="utf-8",
        )

        result = self.run_cli("validate-prd", self.prd)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("missing required section: Success measures", result.stderr)

    def test_validate_prd_rejects_incomplete_approval_evidence(self):
        self.prd.write_text(
            approved_prd().replace(
                "- Evidence: Approved in issue 42.",
                "- Evidence: Not approved",
            ),
            encoding="utf-8",
        )

        result = self.run_cli("validate-prd", self.prd)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("approval evidence", result.stderr)

    def test_validate_prd_rejects_approved_unresolved_blocking_decision(self):
        self.prd.write_text(
            approved_prd().replace(
                "## Open decisions\nNone.",
                "## Open decisions\n"
                "| Decision | Owner | Blocks approval | Resolution |\n"
                "|----------|-------|-----------------|------------|\n"
                "| Export format | Product | yes | unresolved |",
            ),
            encoding="utf-8",
        )

        result = self.run_cli("validate-prd", self.prd)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("approval-blocking decision remains unresolved", result.stderr)

    def test_validate_prd_draft_preserves_stable_approval_blockers(self):
        self.prd.write_text(
            approved_prd()
            .replace("status: approved", "status: draft", 1)
            .replace(
                "## Open decisions\nNone.",
                "## Open decisions\n"
                "| Decision | Owner | Blocks approval | Resolution |\n"
                "|----------|-------|-----------------|------------|\n"
                "| Export format | Product | yes | unresolved |",
            ),
            encoding="utf-8",
        )

        result = self.run_cli("validate-prd", self.prd, "--allow-draft")

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("draft", payload["declaredStatus"])
        self.assertEqual(["export-format"], payload["approvalBlockingDecisions"])

    def test_validate_plan_checks_prd_identity_and_complete_mapping(self):
        result = self.run_cli(
            "validate-plan", self.plan, "--project-root", SCRATCH
        )

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(["contract", "behavior"], payload["tasks"])
        self.assertEqual("search-export", payload["prd"]["id"])
        self.assertEqual(["FR-1", "AC-1"], payload["taskDetails"]["contract"]["prdRefs"])
        self.assertEqual(["approved PRD"], payload["taskDetails"]["contract"]["consumes"])
        self.assertEqual(
            {"mode": "sequential", "group": None},
            payload["taskDetails"]["contract"]["execution"],
        )
        self.assertEqual("not-assessed", payload["semanticApproval"])

    def test_validate_handoff_cross_checks_prd_without_readiness_claim(self):
        handoff = SCRATCH / "handoff.json"
        handoff.write_text(json.dumps(valid_handoff()), encoding="utf-8")

        result = self.run_cli(
            "validate-handoff", handoff, "--project-root", SCRATCH
        )

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["contractValid"])
        self.assertTrue(payload["prd"]["identityMatchedLocalArtifact"])
        self.assertEqual(["AC-1", "AC-2"], payload["evidencedAcceptanceCriteria"])
        self.assertEqual("not-assessed", payload["semanticApproval"])
        self.assertNotIn("ready", result.stdout.lower())

    def test_validate_handoff_missing_ac_evidence_is_contract_error(self):
        handoff = valid_handoff()
        handoff["acceptanceEvidence"] = handoff["acceptanceEvidence"][:1]
        path = SCRATCH / "handoff.json"
        path.write_text(json.dumps(handoff), encoding="utf-8")

        result = self.run_cli("validate-handoff", path)

        self.assertEqual(3, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertEqual(
            "error[E_HANDOFF_AC_EVIDENCE] /acceptanceEvidence: "
            "missing evidence for AC-2\n",
            result.stderr,
        )

    def test_validate_handoff_failed_evidence_creates_visible_blocker(self):
        handoff = valid_handoff()
        handoff["acceptanceEvidence"][1]["result"] = "failed"
        path = SCRATCH / "handoff.json"
        path.write_text(json.dumps(handoff), encoding="utf-8")

        result = self.run_cli("validate-handoff", path)

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("failed", payload["failedOrUnavailableEvidence"][0]["result"])
        self.assertIn("AC-2 evidence failed", payload["blockers"])

    def test_validate_handoff_accepts_substantive_non_applicable_prd(self):
        handoff = valid_handoff()
        handoff["prd"] = {
            "applicability": "not-applicable",
            "reason": "Documentation-only correction with no product capability change.",
        }
        handoff["requirements"] = {
            "functional": [],
            "acceptance": [],
            "delivered": [],
        }
        handoff["acceptanceEvidence"] = []
        path = SCRATCH / "handoff.json"
        path.write_text(json.dumps(handoff), encoding="utf-8")

        result = self.run_cli("validate-handoff", path, "--project-root", SCRATCH)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            "not-applicable", json.loads(result.stdout)["prd"]["applicability"]
        )

    def test_validate_handoff_rejects_requirement_absent_from_local_prd(self):
        handoff = valid_handoff()
        handoff["requirements"]["functional"].append("FR-3")
        handoff["requirements"]["delivered"].insert(2, "FR-3")
        path = SCRATCH / "handoff.json"
        path.write_text(json.dumps(handoff), encoding="utf-8")

        result = self.run_cli(
            "validate-handoff", path, "--project-root", SCRATCH
        )

        self.assertEqual(3, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertIn("error[E_HANDOFF_PRD_REQUIREMENT]", result.stderr)

    def test_malformed_json_failure_is_stable_and_single_line(self):
        path = SCRATCH / "handoff.json"
        path.write_text('{"schemaVersion":', encoding="utf-8")

        result = self.run_cli("validate-handoff", path)

        self.assertEqual(2, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertEqual(1, len(result.stderr.splitlines()))
        self.assertTrue(result.stderr.startswith("error[E_JSON_SYNTAX] "))

    def test_validate_plan_rejects_unknown_prerequisite_and_missing_reference(self):
        self.plan.write_text(
            valid_plan()
            .replace("| behavior | FR-2, AC-2", "| behavior | AC-2")
            .replace("| contract | export interface", "| missing | export interface"),
            encoding="utf-8",
        )

        result = self.run_cli(
            "validate-plan", self.plan, "--project-root", SCRATCH
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("task behavior must map at least one FR-* and AC-*", result.stderr)
        self.assertEqual(1, len(result.stderr.splitlines()))

    def test_validate_plan_rejects_plan_outside_project_root(self):
        outside_plan = SCRATCH.parent / "outside-plan.md"
        outside_plan.write_text(valid_plan(), encoding="utf-8")

        result = self.run_cli(
            "validate-plan", outside_plan, "--project-root", SCRATCH
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("plan path must stay within the project", result.stderr)

    def test_validate_plan_rejects_stdin_alias_as_non_local_path(self):
        result = self.run_cli("validate-plan", "-")

        self.assertEqual(2, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertEqual(
            "error[E_LOCAL_PATH] -: expected a local filesystem path\n",
            result.stderr,
        )

    def test_validate_plan_requires_fr_and_ac_on_each_task(self):
        self.plan.write_text(
            valid_plan()
            .replace("FR-1, AC-1", "FR-1")
            .replace("FR-2, AC-2", "FR-2, AC-1, AC-2"),
            encoding="utf-8",
        )

        result = self.run_cli(
            "validate-plan", self.plan, "--project-root", SCRATCH
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("task contract must map at least one FR-* and AC-*", result.stderr)

    def test_validate_plan_rejects_swapped_fr_ac_pairs(self):
        self.plan.write_text(
            valid_plan()
            .replace("FR-1, AC-1", "FR-2, AC-1")
            .replace("FR-2, AC-2", "FR-1, AC-2"),
            encoding="utf-8",
        )

        result = self.run_cli(
            "validate-plan", self.plan, "--project-root", SCRATCH
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "task contract references AC-1 without one of its mapped functional requirements",
            result.stderr,
        )
        self.assertEqual(1, len(result.stderr.splitlines()))

    def test_validate_plan_accepts_multi_fr_ac_task_mappings(self):
        self.prd.write_text(
            approved_prd().replace(
                "**AC-1** (`FR-1`)",
                "**AC-1** (`FR-1`, `FR-2`)",
            ),
            encoding="utf-8",
        )
        self.plan.write_text(
            valid_plan().replace(
                "| contract | FR-1, AC-1 |",
                "| contract | FR-1, FR-2, AC-1 |",
            ),
            encoding="utf-8",
        )

        result = self.run_cli(
            "validate-plan", self.plan, "--project-root", SCRATCH
        )

        self.assertEqual(0, result.returncode, result.stderr)

    def test_validate_plan_rejects_same_parallel_group_producer_consumer(self):
        self.plan.write_text(
            valid_plan()
            .replace(
                "| contract | FR-1, AC-1 | Define export contract | none | "
                "approved PRD | export interface | sequential |",
                "| contract | FR-1, AC-1 | Define export contract | none | "
                "approved PRD | export interface | parallel group work |",
            )
            .replace(
                "| behavior | FR-2, AC-2 | Implement export behavior | contract | "
                "export interface | export behavior | sequential |",
                "| behavior | FR-2, AC-2 | Implement export behavior | contract | "
                "export interface | export behavior | parallel group work |",
            ),
            encoding="utf-8",
        )

        result = self.run_cli(
            "validate-plan", self.plan, "--project-root", SCRATCH
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "parallel group work contains dependency for task behavior",
            result.stderr,
        )

    def test_validate_plan_rejects_transitive_ancestor_in_parallel_group(self):
        self.plan.write_text(
            valid_plan()
            .replace(
                "| contract | FR-1, AC-1 | Define export contract | none | "
                "approved PRD | export interface | sequential |",
                "| contract | FR-1, AC-1 | Define export contract | none | "
                "approved PRD | export interface | parallel group work |",
            )
            .replace(
                "| behavior | FR-2, AC-2 | Implement export behavior | contract | "
                "export interface | export behavior | sequential |",
                "| bridge | FR-1, AC-1 | Prepare integration | contract | "
                "export interface | integration adapter | sequential | Adapter test passes |\n"
                "| behavior | FR-2, AC-2 | Implement export behavior | bridge | "
                "integration adapter | export behavior | parallel group work |",
            ),
            encoding="utf-8",
        )

        result = self.run_cli(
            "validate-plan", self.plan, "--project-root", SCRATCH
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "parallel group work contains dependency for task behavior",
            result.stderr,
        )

    def test_validate_plan_accepts_independent_diamond_parallel_tasks(self):
        self.plan.write_text(
            valid_plan().replace(
                "| behavior | FR-2, AC-2 | Implement export behavior | contract | "
                "export interface | export behavior | sequential | "
                "Unit and integration tests pass |",
                "| left | FR-1, AC-1 | Build left branch | contract | "
                "export interface | none | parallel group branches | Left test passes |\n"
                "| right | FR-2, AC-2 | Build right branch | contract | "
                "export interface | none | parallel group branches | Right test passes |\n"
                "| behavior | FR-2, AC-2 | Integrate branches | left, right | "
                "none | export behavior | sequential | Integration test passes |",
            ),
            encoding="utf-8",
        )

        result = self.run_cli(
            "validate-plan", self.plan, "--project-root", SCRATCH
        )

        self.assertEqual(0, result.returncode, result.stderr)

    def test_validate_plan_accepts_transitive_dependencies_across_groups(self):
        self.plan.write_text(
            valid_plan()
            .replace(
                "| contract | FR-1, AC-1 | Define export contract | none | "
                "approved PRD | export interface | sequential |",
                "| contract | FR-1, AC-1 | Define export contract | none | "
                "approved PRD | export interface | parallel group foundation |",
            )
            .replace(
                "| behavior | FR-2, AC-2 | Implement export behavior | contract | "
                "export interface | export behavior | sequential |",
                "| bridge | FR-1, AC-1 | Prepare integration | contract | "
                "export interface | integration adapter | parallel group integration | "
                "Adapter test passes |\n"
                "| behavior | FR-2, AC-2 | Implement export behavior | bridge | "
                "integration adapter | export behavior | parallel group delivery |",
            ),
            encoding="utf-8",
        )

        result = self.run_cli(
            "validate-plan", self.plan, "--project-root", SCRATCH
        )

        self.assertEqual(0, result.returncode, result.stderr)

    def test_validate_plan_rejects_consumer_without_producer_dependency(self):
        self.plan.write_text(
            valid_plan().replace(
                "| behavior | FR-2, AC-2 | Implement export behavior | contract |",
                "| behavior | FR-2, AC-2 | Implement export behavior | none |",
            ),
            encoding="utf-8",
        )

        result = self.run_cli(
            "validate-plan", self.plan, "--project-root", SCRATCH
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "task behavior consumes export interface without depending on producer contract",
            result.stderr,
        )

    def test_validate_plan_rejects_ambiguous_duplicate_producers(self):
        self.plan.write_text(
            valid_plan().replace(
                "| export interface | export behavior | sequential |",
                "| approved PRD | export interface | sequential |",
            ),
            encoding="utf-8",
        )

        result = self.run_cli(
            "validate-plan", self.plan, "--project-root", SCRATCH
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "interface export interface has multiple producers: contract, behavior",
            result.stderr,
        )

    def test_validate_plan_normalizes_interface_whitespace_before_duplicates(self):
        self.plan.write_text(
            valid_plan().replace(
                "| export interface | export behavior | sequential |",
                "| approved PRD | export   interface | sequential |",
            ),
            encoding="utf-8",
        )

        result = self.run_cli(
            "validate-plan", self.plan, "--project-root", SCRATCH
        )

        self.assertEqual(3, result.returncode)
        self.assertIn(
            "interface export interface has multiple producers: contract, behavior",
            result.stderr,
        )

    def test_validate_plan_accepts_transitive_interface_dependency_chain(self):
        self.plan.write_text(
            valid_plan().replace(
                "| behavior | FR-2, AC-2 | Implement export behavior | contract | "
                "export interface | export behavior | sequential |",
                "| bridge | FR-1, AC-1 | Prepare integration | contract | "
                "approved PRD | integration adapter | sequential | Adapter test passes |\n"
                "| behavior | FR-2, AC-2 | Implement export behavior | bridge | "
                "export interface | export behavior | sequential |",
            ),
            encoding="utf-8",
        )

        result = self.run_cli(
            "validate-plan", self.plan, "--project-root", SCRATCH
        )

        self.assertEqual(0, result.returncode, result.stderr)

    def test_validate_plan_treats_none_as_an_empty_interface_list(self):
        self.plan.write_text(
            valid_plan()
            .replace("approved PRD | export interface", "none | export interface")
            .replace("export behavior | sequential", "none | sequential"),
            encoding="utf-8",
        )

        result = self.run_cli(
            "validate-plan", self.plan, "--project-root", SCRATCH
        )

        self.assertEqual(0, result.returncode, result.stderr)

    def test_validate_plan_rejects_none_combined_with_an_interface(self):
        self.plan.write_text(
            valid_plan().replace(
                "approved PRD | export interface",
                "none, approved PRD | export interface",
            ),
            encoding="utf-8",
        )

        result = self.run_cli(
            "validate-plan", self.plan, "--project-root", SCRATCH
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "task contract consumes must use none alone",
            result.stderr,
        )

    def test_cursor_enforces_prerequisites_and_resumes_from_saved_task(self):
        cursor = SCRATCH / ".sdlc" / "execution-cursor.json"
        blocked = self.run_cli(
            "cursor",
            self.plan,
            "--project-root",
            SCRATCH,
            "--cursor",
            cursor,
            "--task",
            "behavior",
        )
        self.assertNotEqual(0, blocked.returncode)
        self.assertIn("incomplete prerequisite contract", blocked.stderr)

        saved = self.run_cli(
            "cursor",
            self.plan,
            "--project-root",
            SCRATCH,
            "--cursor",
            cursor,
            "--task",
            "behavior",
            "--complete",
            "contract",
        )
        self.assertEqual(0, saved.returncode, saved.stderr)
        self.assertTrue(cursor.is_file())

        resumed = self.run_cli(
            "cursor-status",
            self.plan,
            "--project-root",
            SCRATCH,
            "--cursor",
            cursor,
        )
        self.assertEqual(0, resumed.returncode, resumed.stderr)
        payload = json.loads(resumed.stdout)
        self.assertEqual("behavior", payload["currentTask"])
        self.assertEqual(["contract"], payload["completedTasks"])
        self.assertNotIn("timestamp", payload)
        self.assertNotIn("summary", payload)

    def test_cursor_rejects_stale_plan_digest(self):
        cursor = SCRATCH / ".sdlc" / "execution-cursor.json"
        saved = self.run_cli(
            "cursor",
            self.plan,
            "--project-root",
            SCRATCH,
            "--cursor",
            cursor,
            "--task",
            "contract",
        )
        self.assertEqual(0, saved.returncode, saved.stderr)
        self.plan.write_text(valid_plan() + "\nChanged.\n", encoding="utf-8")

        result = self.run_cli(
            "cursor-status",
            self.plan,
            "--project-root",
            SCRATCH,
            "--cursor",
            cursor,
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("cursor does not match the current plan", result.stderr)

    def test_cursor_rejects_completed_task_with_incomplete_prerequisite(self):
        cursor = SCRATCH / ".sdlc" / "execution-cursor.json"

        result = self.run_cli(
            "cursor",
            self.plan,
            "--project-root",
            SCRATCH,
            "--cursor",
            cursor,
            "--task",
            "contract",
            "--complete",
            "behavior",
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "completed task behavior has incomplete prerequisite contract",
            result.stderr,
        )

    def test_cursor_status_rejects_tampered_dependency_state(self):
        cursor = SCRATCH / ".sdlc" / "execution-cursor.json"
        saved = self.run_cli(
            "cursor",
            self.plan,
            "--project-root",
            SCRATCH,
            "--cursor",
            cursor,
            "--task",
            "contract",
        )
        self.assertEqual(0, saved.returncode, saved.stderr)
        payload = json.loads(cursor.read_text(encoding="utf-8"))
        payload["completedTasks"] = ["behavior"]
        cursor.write_text(json.dumps(payload), encoding="utf-8")

        result = self.run_cli(
            "cursor-status",
            self.plan,
            "--project-root",
            SCRATCH,
            "--cursor",
            cursor,
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "completed task behavior has incomplete prerequisite contract",
            result.stderr,
        )

    def test_cursor_status_rejects_current_task_with_incomplete_prerequisite(self):
        cursor = SCRATCH / ".sdlc" / "execution-cursor.json"
        saved = self.run_cli(
            "cursor",
            self.plan,
            "--project-root",
            SCRATCH,
            "--cursor",
            cursor,
            "--task",
            "contract",
        )
        self.assertEqual(0, saved.returncode, saved.stderr)
        payload = json.loads(cursor.read_text(encoding="utf-8"))
        payload["currentTask"] = "behavior"
        cursor.write_text(json.dumps(payload), encoding="utf-8")

        result = self.run_cli(
            "cursor-status",
            self.plan,
            "--project-root",
            SCRATCH,
            "--cursor",
            cursor,
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("incomplete prerequisite contract", result.stderr)

    def test_cursor_status_rejects_tampered_plan_identity(self):
        cursor = SCRATCH / ".sdlc" / "execution-cursor.json"
        saved = self.run_cli(
            "cursor",
            self.plan,
            "--project-root",
            SCRATCH,
            "--cursor",
            cursor,
            "--task",
            "contract",
        )
        self.assertEqual(0, saved.returncode, saved.stderr)
        payload = json.loads(cursor.read_text(encoding="utf-8"))
        payload["planPath"] = "different-plan.md"
        cursor.write_text(json.dumps(payload), encoding="utf-8")

        result = self.run_cli(
            "cursor-status",
            self.plan,
            "--project-root",
            SCRATCH,
            "--cursor",
            cursor,
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("cursor does not identify the current plan", result.stderr)


if __name__ == "__main__":
    unittest.main()
