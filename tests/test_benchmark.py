import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_execution_contracts import SCRIPTS
from artifact_contracts import ContractIssue
import execution_state as state


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "benchmark.py"
SPEC = importlib.util.spec_from_file_location("benchmark", SCRIPT)
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)
HASH = "sha256:" + "a" * 64
RUBRIC = ("correctness", "verification", "security", "scope")
TOKENS = ("providerInputTokens", "providerOutputTokens", "cachedInputTokens",
          "billableInputTokens", "billableOutputTokens")


def manifest():
    return {
        "schemaVersion": 1, "kind": "sdlc-efficiency-manifest", "id": "test-cohort",
        "sourceRevision": "a" * 40, "configurationDigest": HASH, "repetitions": 2,
        "requestedModel": "existing-host", "effectiveModel": None, "hostVersion": "test-1",
        "maxAttempts": 2, "maxRequestsPerAttempt": 4,
        "tasks": [{"id": "bug-fix", "objective": "Preserve the boundary predicate.",
                   "permittedActions": ["read", "edit"], "acceptanceCriteria": ["Zero is valid."],
                   "verification": ["Run the boundary regression."], "rubric": list(RUBRIC)}],
    }


def request(request_id="request-1", **changes):
    return {"id": request_id, "state": "completed", "adapterInvoked": True,
            "inputBytes": 12, "outputBytes": 7,
            **dict.fromkeys(TOKENS), "authoritativeCost": None, **changes}


def observations(current=None):
    current = current or manifest()
    return {
        "schemaVersion": 1, "kind": "sdlc-efficiency-observations",
        "manifestDigest": state.digest(current), "evidenceKind": "synthetic",
        "usageSource": "unavailable", "usageEvidenceDigest": None,
        "attempts": [{"taskId": "bug-fix", "repetition": 1, "attempt": 1,
                      "attemptId": "attempt-1", "producerId": "worker",
                      "outcome": "completed", "elapsedMs": 15, "toolCalls": 2,
                      "handoffs": None, "quality": None, "requests": [request()]}],
    }


class BenchmarkTests(unittest.TestCase):
    def test_ac1_manifest_has_stable_digest_and_does_not_mutate_input(self):
        source = manifest()
        before = copy.deepcopy(source)
        result = benchmark.validate_manifest(source)
        self.assertEqual(state.digest(source), result["manifestDigest"])
        self.assertEqual(4, result["plannedAttemptsMaximum"])
        self.assertEqual(source, before)

    def test_ac1_rejects_bad_versions_types_bounds_and_duplicate_tasks(self):
        cases = []
        for field, value in (("schemaVersion", 2), ("repetitions", True),
                             ("repetitions", 0), ("maxAttempts", 100000),
                             ("sourceRevision", "working-tree")):
            item = manifest()
            item[field] = value
            cases.append(item)
        item = manifest()
        item["tasks"].append(copy.deepcopy(item["tasks"][0]))
        cases.append(item)
        item = manifest()
        item["tasks"][0]["rubric"].remove("security")
        cases.append(item)
        for item in cases:
            with self.subTest(item=item), self.assertRaises(ContractIssue):
                benchmark.validate_manifest(item)

    def test_ac2_rejects_stale_binding_duplicate_attempt_and_duplicate_request(self):
        cases = []
        item = observations()
        item["manifestDigest"] = "sha256:" + "b" * 64
        cases.append(item)
        item = observations()
        item["attempts"].append(copy.deepcopy(item["attempts"][0]))
        cases.append(item)
        item = observations()
        item["attempts"][0]["requests"] *= 2
        cases.append(item)
        item = observations()
        item["attempts"][0]["taskId"] = "other-task"
        cases.append(item)
        for item in cases:
            with self.subTest(item=item), self.assertRaises(ContractIssue):
                benchmark.report(manifest(), item)

    def test_ac3_prepared_interrupted_and_unknown_invocations_are_not_confirmed(self):
        item = observations()
        item["attempts"][0]["outcome"] = "unknown"
        item["attempts"][0]["requests"] = [
            request("prepared", state="prepared", adapterInvoked=False, outputBytes=0),
            request("interrupted", state="interrupted", outputBytes=len("😀é".encode("utf-8"))),
            request("unknown", state="unknown", adapterInvoked=None, outputBytes=0),
        ]
        result = benchmark.report(manifest(), item)
        self.assertEqual(1, result["accounting"]["observedModelCalls"])
        self.assertEqual(1, result["accounting"]["unknownInvocations"])
        self.assertIsNone(result["accounting"]["totalInputBytes"])
        self.assertEqual(6, result["accounting"]["observedOutputBytes"])
        self.assertEqual(1, result["requests"]["prepared"])
        self.assertEqual(0, result["requests"]["completed"])
        self.assertFalse(result["claims"]["managerAcceptance"])

    def test_ac3_attempts_retries_and_request_ids_are_bound_to_the_attempt(self):
        source = manifest()
        source["repetitions"] = 1
        item = observations(source)
        retry = copy.deepcopy(item["attempts"][0])
        retry.update(attempt=2, attemptId="attempt-2", elapsedMs=25, handoffs=1)
        item["attempts"].append(retry)
        result = benchmark.report(source, item)
        self.assertEqual(1, result["coverage"]["observedRetries"])
        self.assertEqual(1, result["coverage"]["observedRepetitions"])
        self.assertEqual(2, result["accounting"]["observedModelCalls"])
        self.assertEqual(24, result["accounting"]["totalInputBytes"])
        self.assertEqual(40, result["accounting"]["attemptElapsedMs"])
        self.assertEqual(1, result["accounting"]["observedHandoffs"])
        self.assertFalse(result["accounting"]["handoffsComplete"])

    def test_ac3_retry_with_missing_initial_accounting_cannot_form_a_complete_cohort(self):
        item = observations()
        item["attempts"][0]["attempt"] = 2
        with self.assertRaises(ContractIssue):
            benchmark.report(manifest(), item)

    def test_ac3_unknown_total_preserves_observed_input_and_does_not_infer_wall_time(self):
        item = observations()
        item["attempts"][0]["requests"].append(
            request("unknown", state="unknown", adapterInvoked=None, outputBytes=0))
        result = benchmark.report(manifest(), item)
        self.assertEqual(12, result["accounting"]["observedInputBytes"])
        self.assertIsNone(result["accounting"]["totalInputBytes"])
        self.assertIsNone(result["accounting"]["endToEndElapsedMs"])

    def test_ac2_usage_requires_provenance_and_partial_fields_stay_null(self):
        source = manifest()
        source["repetitions"] = 1
        item = observations(source)
        item["attempts"][0]["requests"][0]["providerInputTokens"] = 20
        with self.assertRaises(ContractIssue):
            benchmark.report(source, item)
        item.update(usageSource="caller-reported", usageEvidenceDigest=HASH)
        item["attempts"][0]["requests"].append(request("second"))
        result = benchmark.report(source, item)
        self.assertIsNone(result["accounting"]["providerInputTokens"])
        item["attempts"][0]["requests"][1]["providerInputTokens"] = 30
        result = benchmark.report(source, item)
        self.assertEqual(50, result["accounting"]["providerInputTokens"])
        self.assertIsNone(result["accounting"]["cachedInputTokens"])
        self.assertEqual("not-assessed", result["evidenceVerification"])

    def test_ac2_cached_and_billable_tokens_are_not_subtracted_or_reclassified(self):
        source = manifest()
        source["repetitions"] = 1
        item = observations(source)
        item.update(usageSource="caller-reported", usageEvidenceDigest=HASH)
        item["attempts"][0]["requests"][0].update(
            providerInputTokens=100, providerOutputTokens=20, cachedInputTokens=80,
            billableInputTokens=25, billableOutputTokens=20)
        result = benchmark.report(source, item)
        self.assertEqual(100, result["accounting"]["providerInputTokens"])
        self.assertEqual(80, result["accounting"]["cachedInputTokens"])
        self.assertEqual(25, result["accounting"]["billableInputTokens"])
        self.assertEqual(12, result["accounting"]["totalInputBytes"])

    def test_ac3_rejects_impossible_lifecycle_counts_and_overflow(self):
        for changes in ({"state": "prepared"}, {"adapterInvoked": False},
                        {"inputBytes": True}, {"outputBytes": -1},
                        {"providerInputTokens": float("inf")}):
            item = observations()
            item["attempts"][0]["requests"][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ContractIssue):
                benchmark.report(manifest(), item)
        item = observations()
        item["attempts"][0]["requests"] = [
            request("one", inputBytes=2**63 - 1), request("two", inputBytes=1)]
        with self.assertRaises(ContractIssue):
            benchmark.report(manifest(), item)

    def test_ac4_non_null_actual_cost_is_rejected_without_billing_adapter(self):
        item = observations()
        item["attempts"][0]["requests"][0]["authoritativeCost"] = 1
        with self.assertRaises(ContractIssue):
            benchmark.report(manifest(), item)

    def test_ac5_declared_quality_requires_other_reviewer_and_evidence(self):
        item = observations()
        quality = {"reviewerId": "worker", "evidenceDigest": HASH,
                   "criteria": dict.fromkeys(RUBRIC, "passed")}
        item["attempts"][0]["quality"] = quality
        with self.assertRaises(ContractIssue):
            benchmark.report(manifest(), item)
        quality["reviewerId"] = "reviewer"
        result = benchmark.report(manifest(), item)
        self.assertEqual(1, result["quality"]["declaredPassed"])
        self.assertFalse(result["claims"]["managerAcceptance"])
        quality["criteria"]["security"] = "failed"
        result = benchmark.report(manifest(), item)
        self.assertEqual(1, result["quality"]["declaredFailed"])

    def test_ac6_raw_fields_are_rejected_and_task_instructions_are_not_copied(self):
        for location in ("root", "attempt", "request"):
            item = observations()
            target = {"root": item, "attempt": item["attempts"][0],
                      "request": item["attempts"][0]["requests"][0]}[location]
            target["rawPrompt"] = "private content"
            with self.subTest(location=location), self.assertRaises(ContractIssue):
                benchmark.report(manifest(), item)
        source = manifest()
        source["tasks"][0]["objective"] = "Distinctive instruction never copied."
        result = benchmark.report(source, observations(source))
        self.assertNotIn("Distinctive instruction", json.dumps(result))

    def test_ac7_empty_cohort_and_synthetic_evidence_never_claim_savings(self):
        item = observations()
        item["attempts"] = []
        result = benchmark.report(manifest(), item)
        self.assertEqual(2, result["coverage"]["missingRepetitions"])
        self.assertEqual(0, result["coverage"]["observedAttempts"])
        self.assertIsNone(result["accounting"]["providerInputTokens"])
        self.assertIsNone(result["accounting"]["authoritativeCost"])
        self.assertEqual("synthetic", result["measurementStatus"])
        self.assertEqual({"tokenSavings": None, "costSavings": None,
                          "qualityNonRegression": None, "managerAcceptance": False}, result["claims"])

    def test_ac7_recorded_data_is_still_unverified_and_inputs_are_unchanged(self):
        item = observations()
        item["evidenceKind"] = "recorded"
        before = copy.deepcopy(item)
        result = benchmark.report(manifest(), item)
        self.assertEqual("partial-recorded-unverified", result["measurementStatus"])
        self.assertEqual(before, item)

    def test_ac7_each_task_and_repetition_keeps_results_and_missingness(self):
        source = manifest()
        second = copy.deepcopy(source["tasks"][0])
        second["id"] = "documentation"
        source["tasks"].append(second)
        item = observations(source)
        result = benchmark.report(source, item)
        tasks = {task["taskId"]: task for task in result["tasks"]}
        self.assertEqual(1, tasks["bug-fix"]["coverage"]["missingRepetitions"])
        self.assertEqual(12, tasks["bug-fix"]["accounting"]["observedInputBytes"])
        self.assertEqual(2, tasks["documentation"]["coverage"]["missingRepetitions"])
        self.assertEqual([1, 2], [row["repetition"] for row in tasks["documentation"]["repetitions"]])
        self.assertTrue(all(row["coverage"]["missingRepetitions"] == 1
                            for row in tasks["documentation"]["repetitions"]))
        self.assertEqual(1, tasks["bug-fix"]["repetitions"][0]["outcomes"]["completed"])

    def test_ac7_missing_repetitions_do_not_turn_observed_usage_into_cohort_totals(self):
        source = manifest()
        item = observations(source)
        item.update(usageSource="caller-reported", usageEvidenceDigest=HASH)
        item["attempts"][0]["requests"][0].update(
            providerInputTokens=100, providerOutputTokens=20)
        result = benchmark.report(source, item)
        self.assertIsNone(result["accounting"]["totalInputBytes"])
        self.assertIsNone(result["accounting"]["providerInputTokens"])
        self.assertEqual(100, result["accounting"]["observedUsage"]["providerInputTokens"])
        self.assertIsNone(result["tasks"][0]["accounting"]["totalInputBytes"])
        missing = result["tasks"][0]["repetitions"][1]
        self.assertIsNone(missing["accounting"]["totalInputBytes"])
        self.assertIsNone(missing["accounting"]["providerInputTokens"])

    def test_cli_selected_inputs_success_and_error_have_no_file_side_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "manifest.json"
            data = root / "observations.json"
            source.write_text(json.dumps(manifest()), encoding="utf-8")
            data.write_text(json.dumps(observations()), encoding="utf-8")
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            command = [sys.executable, "-B", str(SCRIPT), "report",
                       "--manifest", str(source), "--observations", str(data)]
            result = subprocess.run(command, cwd=root, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(1, json.loads(result.stdout)["accounting"]["observedModelCalls"])
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})
            data.write_text('{"schemaVersion":1,"schemaVersion":1,"secret-value":"do-not-echo"}',
                            encoding="utf-8")
            result = subprocess.run(command, cwd=root, capture_output=True, text=True)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual("", result.stdout)
            self.assertIn("E_JSON_DUPLICATE", result.stderr)
            self.assertNotIn("do-not-echo", result.stderr)
            self.assertNotIn(str(root), result.stderr)


if __name__ == "__main__":
    unittest.main()
