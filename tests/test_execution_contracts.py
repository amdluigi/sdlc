import copy
import hashlib
import importlib
import json
import re
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "sdlc" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from artifact_contracts import ContractIssue, strict_load_json


DIGEST = "sha256:" + "a" * 64
EVENTS = {
    "PLAN_PROPOSED": (False, False, {}),
    "PLAN_UPDATED": (False, False, {"previousRevision": 1}),
    "PLAN_APPROVED": (False, False, {"decisionId": "approve-plan"}),
    "TASK_READY": (True, False, {}),
    "TASK_STARTED": (True, True, {}),
    "TASK_PROGRESS_UPDATED": (True, True, {"message": "Validation prepared"}),
    "TASK_BLOCKED": (True, False, {"reason": "Input required"}),
    "TASK_UNBLOCKED": (True, False, {}),
    "TASK_RESULT_RECEIVED": (True, True, {"resultId": "result-one"}),
    "VALIDATION_PASSED": (True, True, {"acceptanceCriteria": ["AC-1"]}),
    "VALIDATION_FAILED": (
        True, True, {"acceptanceCriteria": ["AC-1"], "reason": "Assertion failed"}
    ),
    "TASK_COMPLETED": (True, True, {}),
    "TASK_FAILED": (True, True, {"reason": "Validation failed"}),
    "TASK_CANCELLED": (True, False, {"reason": "User requested cancellation"}),
    "APPROVAL_REQUESTED": (False, False, {"decisionId": "approve-one", "reason": "Review"}),
    "APPROVAL_GRANTED": (False, False, {"decisionId": "approve-one"}),
    "APPROVAL_REJECTED": (False, False, {"decisionId": "approve-one", "reason": "Revise"}),
}


def task(identifier="implement"):
    return {
        "id": identifier,
        "title": "Implement a bounded change",
        "outcome": "A validated change",
        "prdRefs": ["FR-1", "AC-1"],
        "prerequisites": [],
        "consumes": ["approved-contract"],
        "produces": ["implementation"],
        "execution": {"mode": "sequential", "group": None},
        "assignment": {"agent": "Developer", "modelProfile": "host-default", "model": None},
        "estimateMs": None,
        "ownership": ["src/feature.py"],
        "acceptanceCriteria": ["AC-1"],
        "verification": "Run the acceptance test",
    }


def plan():
    return {
        "schemaVersion": 1,
        "executionId": "feature-one",
        "revision": 2,
        "sourcePlan": {
            "path": "docs/plans/feature.md",
            "digest": DIGEST,
            "prd": {"id": "feature", "version": 1},
        },
        "tasks": [task()],
    }


def binding(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {
        "executionId": value["executionId"],
        "planRevision": value["revision"],
        "planDigest": "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    }


def brief(value):
    return {
        "schemaVersion": 1,
        "binding": binding(value),
        "taskId": "implement",
        "attemptId": "attempt-one",
        "allowedActions": ["read", "search", "edit", "execute"],
        "ownership": ["src/feature.py"],
        "guidance": ["skills/sdlc-testing/SKILL.md"],
        "acceptanceCriteria": ["AC-1"],
        "verification": "Run the acceptance test",
    }


def result(value):
    return {
        "schemaVersion": 1,
        "binding": binding(value),
        "taskId": "implement",
        "attemptId": "attempt-one",
        "status": "completed",
        "artifacts": ["src/feature.py"],
        "verification": [{
            "acceptanceCriterion": "AC-1",
            "command": "python -m unittest",
            "result": "passed",
            "revision": "baseline",
            "summary": "Declared assertion result",
        }],
        "findings": [],
        "blockers": [],
    }


def event(value, event_type="TASK_STARTED"):
    has_task, has_attempt, payload = EVENTS[event_type]
    return {
        "schemaVersion": 1,
        "eventId": "event-one",
        "binding": binding(value),
        "sequence": 1,
        "occurredAt": "2026-11-01T15:00:00Z",
        "recordedAt": "2026-11-01T15:00:01Z",
        "actor": {"role": "user", "id": "operator"},
        "type": event_type,
        "taskId": "implement" if has_task else None,
        "attemptId": "attempt-one" if has_attempt else None,
        "payload": copy.deepcopy(payload),
    }


class ExecutionContractTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(
            (SCRIPTS / "execution_contracts.py").is_file(),
            "AC-1: execution contract validation is not provided",
        )
        self.api = importlib.import_module("execution_contracts")
        self.plan = plan()
        self.brief = brief(self.plan)

    def assert_issue(self, callback, code):
        with self.assertRaises(ContractIssue) as caught:
            callback()
        self.assertEqual(code, caught.exception.code)
        self.assertTrue(caught.exception.pointer.startswith("/"))
        self.assertNotIn("\n", caught.exception.cli_message())

    def test_ac1_valid_contracts_are_structural_only_and_immutable(self):
        inputs = [self.plan, self.brief, result(self.plan), event(self.plan)]
        original = copy.deepcopy(inputs)
        outputs = [
            self.api.validate_execution_plan(inputs[0]),
            self.api.validate_task_brief(inputs[1], self.plan),
            self.api.validate_task_result(inputs[2], self.plan, self.brief),
            self.api.validate_execution_event(inputs[3], self.plan),
        ]
        for output, value in zip(outputs, inputs):
            self.assertTrue(output["contractValid"])
            self.assertEqual("not-assessed", output["semanticApproval"])
            self.assertEqual(value, output["data"])
            self.assertIsNot(value, output["data"])
            self.assertNotIn("ready", output)
            self.assertNotIn("state", output)
        self.assertEqual(original, inputs)
        outputs[0]["data"]["tasks"].clear()
        self.assertEqual(original[0], self.plan)

    def test_ac2_accepts_chain_and_independent_diamond(self):
        second = task("verify")
        second.update(prerequisites=["implement"], consumes=["implementation"],
                      produces=["verified"], ownership=["tests/feature.py"])
        self.plan["tasks"].append(second)
        self.api.validate_execution_plan(self.plan)
        for identifier in ("research-a", "research-b"):
            independent = task(identifier)
            independent.update(
                consumes=["verified"], produces=[identifier],
                prerequisites=["verify"],
                execution={"mode": "parallel", "group": "research"},
                ownership=[],
            )
            self.plan["tasks"].append(independent)
        self.api.validate_execution_plan(self.plan)

    def test_ac2_rejects_invalid_graphs_and_parallel_conflicts(self):
        mutations = [
            lambda p: p["tasks"].append(copy.deepcopy(p["tasks"][0])),
            lambda p: p["tasks"][0].update(prerequisites=["unknown"]),
            lambda p: p["tasks"][0].update(prerequisites=["implement"]),
            lambda p: p["tasks"].append(task("duplicate-producer")),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                value = plan()
                mutate(value)
                self.assert_issue(lambda: self.api.validate_execution_plan(value), "E_EXECUTION_GRAPH")
        second = task("verify")
        second.update(prerequisites=["implement"], produces=["verified"],
                      consumes=["implementation"])
        self.plan["tasks"].append(second)
        self.plan["tasks"][0]["prerequisites"] = ["verify"]
        self.assert_issue(lambda: self.api.validate_execution_plan(self.plan), "E_EXECUTION_GRAPH")
        self.plan["tasks"][0]["prerequisites"] = []
        for value in self.plan["tasks"]:
            value["execution"] = {"mode": "parallel", "group": "shared"}
        self.assert_issue(lambda: self.api.validate_execution_plan(self.plan), "E_EXECUTION_GRAPH")
        self.plan["tasks"][1]["execution"] = {"mode": "sequential", "group": None}
        self.plan["tasks"][1]["prerequisites"] = []
        self.assert_issue(lambda: self.api.validate_execution_plan(self.plan), "E_EXECUTION_GRAPH")

    def test_ac2_rejects_transitive_dependencies_in_parallel_group(self):
        self.plan["tasks"][0]["execution"] = {"mode": "parallel", "group": "shared"}
        middle = task("middle")
        middle.update(prerequisites=["implement"], consumes=["implementation"], produces=["middle"])
        last = task("last")
        last.update(prerequisites=["middle"], consumes=["middle"], produces=["last"],
                    execution={"mode": "parallel", "group": "shared"})
        self.plan["tasks"].extend([middle, last])
        self.assert_issue(lambda: self.api.validate_execution_plan(self.plan), "E_EXECUTION_GRAPH")

    def test_ac3_rejects_stale_bindings_unknown_tasks_and_attempts(self):
        for field, replacement in (
            ("executionId", "different"),
            ("planRevision", 1),
            ("planDigest", "sha256:" + "b" * 64),
        ):
            with self.subTest(field=field):
                value = brief(self.plan)
                value["binding"][field] = replacement
                self.assert_issue(
                    lambda: self.api.validate_task_brief(value, self.plan), "E_EXECUTION_BINDING"
                )
        value = brief(self.plan)
        value["taskId"] = "unknown"
        self.assert_issue(lambda: self.api.validate_task_brief(value, self.plan), "E_EXECUTION_REFERENCE")
        value = result(self.plan)
        value["attemptId"] = "another-attempt"
        self.assert_issue(
            lambda: self.api.validate_task_result(value, self.plan, self.brief),
            "E_EXECUTION_BINDING",
        )

    def test_ac3_scopes_artifacts_and_verification_without_accepting_claims(self):
        value = result(self.plan)
        for outcome in ("passed", "failed", "not-run", "skipped", "unavailable"):
            value["verification"][0]["result"] = outcome
            self.api.validate_task_result(value, self.plan, self.brief)
        value["verification"][0]["result"] = "probably-passed"
        self.assert_issue(
            lambda: self.api.validate_task_result(value, self.plan, self.brief), "E_EXECUTION_ENUM"
        )
        value = result(self.plan)
        value["artifacts"] = ["src/another.py"]
        self.assert_issue(
            lambda: self.api.validate_task_result(value, self.plan, self.brief), "E_EXECUTION_SCOPE"
        )
        value = brief(self.plan)
        value["ownership"] = ["src/another.py"]
        self.assert_issue(lambda: self.api.validate_task_brief(value, self.plan), "E_EXECUTION_SCOPE")
        value = result(self.plan)
        value["verification"][0]["acceptanceCriterion"] = "AC-2"
        self.assert_issue(
            lambda: self.api.validate_task_result(value, self.plan, self.brief),
            "E_EXECUTION_REFERENCE",
        )

    def test_ac4_covers_every_event_type_and_payload(self):
        for event_type in EVENTS:
            with self.subTest(event_type=event_type):
                value = event(self.plan, event_type)
                output = self.api.validate_execution_event(value, self.plan)
                self.assertEqual(value, output["data"])
                value["payload"]["unexpected"] = True
                self.assert_issue(
                    lambda: self.api.validate_execution_event(value, self.plan), "E_SCHEMA_UNKNOWN"
                )

    def test_ac4_rejects_time_sequence_scope_and_actor_errors(self):
        for field, replacement, code in (
            ("occurredAt", "2026-02-30T15:00:00Z", "E_EXECUTION_TIME"),
            ("occurredAt", "2026-11-01T15:00:00+02:00", "E_EXECUTION_TIME"),
            ("recordedAt", "2026-11-01T14:00:00Z", "E_EXECUTION_TIME"),
            ("sequence", True, "E_EXECUTION_NUMBER"),
            ("sequence", 0, "E_EXECUTION_NUMBER"),
            ("taskId", "unknown", "E_EXECUTION_REFERENCE"),
            ("attemptId", None, "E_EXECUTION_REFERENCE"),
            ("type", "TASK_RETRIED", "E_EXECUTION_ENUM"),
        ):
            with self.subTest(field=field, replacement=replacement):
                value = event(self.plan)
                value[field] = replacement
                self.assert_issue(
                    lambda: self.api.validate_execution_event(value, self.plan), code
                )
        value = event(self.plan, "PLAN_APPROVED")
        value["actor"]["role"] = "worker"
        self.assert_issue(
            lambda: self.api.validate_execution_event(value, self.plan), "E_EXECUTION_ACTOR"
        )
        value = event(self.plan, "PLAN_PROPOSED")
        value["taskId"] = "implement"
        self.assert_issue(
            lambda: self.api.validate_execution_event(value, self.plan), "E_EXECUTION_REFERENCE"
        )

    def test_ac5_rejects_versions_types_unknown_and_missing_fields(self):
        for field, replacement, code in (
            ("schemaVersion", True, "E_EXECUTION_VERSION"),
            ("schemaVersion", 2, "E_EXECUTION_VERSION"),
            ("revision", True, "E_EXECUTION_NUMBER"),
            ("revision", 1.0, "E_EXECUTION_NUMBER"),
            ("revision", -1, "E_EXECUTION_NUMBER"),
            ("executionId", "../unsafe", "E_EXECUTION_ID"),
        ):
            with self.subTest(field=field):
                value = plan()
                value[field] = replacement
                self.assert_issue(lambda: self.api.validate_execution_plan(value), code)
        value = plan()
        value["extra"] = "ignored"
        self.assert_issue(lambda: self.api.validate_execution_plan(value), "E_SCHEMA_UNKNOWN")
        del value["extra"]
        del value["tasks"]
        self.assert_issue(lambda: self.api.validate_execution_plan(value), "E_SCHEMA_REQUIRED")

    def test_ac5_rejects_nonfinite_estimates_and_unsafe_paths(self):
        for estimate in (True, -1, 0.5, float("nan"), float("inf"), 2**63):
            with self.subTest(estimate=estimate):
                value = plan()
                value["tasks"][0]["estimateMs"] = estimate
                self.assert_issue(lambda: self.api.validate_execution_plan(value), "E_EXECUTION_NUMBER")
        for path in ("../outside.py", "/outside.py", "C:/outside.py", "C:\\outside.py",
                     "src\\file.py", "src//file.py", "./src/file.py", "https://example.com/file",
                     "src/file.py:stream", "src/%2e%2e/file.py"):
            with self.subTest(path=path):
                value = plan()
                value["tasks"][0]["ownership"] = [path]
                self.assert_issue(lambda: self.api.validate_execution_plan(value), "E_EXECUTION_PATH")

    def test_ac5_strict_input_reader_rejects_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text('{"schemaVersion":1,"schemaVersion":2}', encoding="utf-8")
            with self.assertRaises(ContractIssue) as caught:
                strict_load_json(path)
            self.assertEqual("E_JSON_DUPLICATE", caught.exception.code)

    def test_ac5_all_contracts_reject_versions_unknown_fields_and_wrong_roots(self):
        cases = [
            (plan(), self.api.validate_execution_plan),
            (brief(self.plan), lambda value: self.api.validate_task_brief(value, self.plan)),
            (result(self.plan), lambda value: self.api.validate_task_result(value, self.plan, self.brief)),
            (event(self.plan), lambda value: self.api.validate_execution_event(value, self.plan)),
        ]
        for fixture, validate in cases:
            for version in (True, 1.0, 0, 2, "1", None):
                with self.subTest(contract=set(fixture), version=version):
                    value = copy.deepcopy(fixture)
                    value["schemaVersion"] = version
                    self.assert_issue(lambda: validate(value), "E_EXECUTION_VERSION")
            value = copy.deepcopy(fixture)
            value["unexpected"] = True
            self.assert_issue(lambda: validate(value), "E_SCHEMA_UNKNOWN")
            del value["unexpected"]
            del value["schemaVersion"]
            self.assert_issue(lambda: validate(value), "E_SCHEMA_REQUIRED")
            for value in (None, [], "object"):
                self.assert_issue(lambda: validate(value), "E_SCHEMA_TYPE")

    def test_ac5_nested_unknown_fields_and_collection_boundaries(self):
        for field in ("assignment", "execution"):
            value = plan()
            value["tasks"][0][field]["unexpected"] = True
            self.assert_issue(lambda: self.api.validate_execution_plan(value), "E_SCHEMA_UNKNOWN")
        for field in ("prerequisites", "consumes", "produces", "ownership"):
            for replacement, code in (
                (["same", "same"], "E_SCHEMA_UNIQUE"),
                ("not-an-array", "E_SCHEMA_TYPE"),
                ([f"id-{index}" for index in range(257)], "E_EXECUTION_LIMIT"),
            ):
                value = plan()
                value["tasks"][0][field] = replacement
                self.assert_issue(lambda: self.api.validate_execution_plan(value), code)
        for estimate in (0, 1, 2**63 - 1, None):
            value = plan()
            value["tasks"][0]["estimateMs"] = estimate
            self.api.validate_execution_plan(value)
        self.plan["tasks"] = []
        self.assert_issue(lambda: self.api.validate_execution_plan(self.plan), "E_SCHEMA_REQUIRED")

    def test_ac5_duplicate_diagnostics_do_not_echo_declared_evidence(self):
        value = result(self.plan)
        value["findings"] = ["Declared diagnostic sample", "Declared diagnostic sample"]
        with self.assertRaises(ContractIssue) as caught:
            self.api.validate_task_result(value, self.plan, self.brief)
        self.assertEqual("E_SCHEMA_UNIQUE", caught.exception.code)
        self.assertNotIn("Declared diagnostic sample", caught.exception.cli_message())

    def test_ac3_supplied_plan_and_brief_are_validated_before_reports(self):
        self.plan["unexpected"] = True
        self.assert_issue(
            lambda: self.api.validate_task_result({}, self.plan, {}),
            "E_SCHEMA_UNKNOWN",
        )
        del self.plan["unexpected"]
        self.brief["allowedActions"] = ["dispatch"]
        self.assert_issue(
            lambda: self.api.validate_task_result(result(self.plan), self.plan, self.brief),
            "E_EXECUTION_ENUM",
        )

    def test_ac3_wrong_task_result_identifies_the_mismatched_field(self):
        other = task("other")
        other.update(produces=["other"], ownership=["src/other.py"])
        self.plan["tasks"].append(other)
        value = result(self.plan)
        value["taskId"] = "other"
        with self.assertRaises(ContractIssue) as caught:
            self.api.validate_task_result(value, self.plan, brief(self.plan))
        self.assertEqual("E_EXECUTION_BINDING", caught.exception.code)
        self.assertEqual("/taskId", caught.exception.pointer)

    def test_ac3_binding_is_insensitive_to_object_key_order_but_not_task_changes(self):
        reordered = dict(reversed(list(self.plan.items())))
        self.api.validate_task_brief(self.brief, reordered)
        self.plan["tasks"][0]["title"] = "A changed task"
        self.assert_issue(
            lambda: self.api.validate_task_brief(self.brief, self.plan), "E_EXECUTION_BINDING"
        )

    def test_ac3_edit_scope_and_criteria_cannot_be_dropped(self):
        self.brief["ownership"] = []
        self.assert_issue(lambda: self.api.validate_task_brief(self.brief, self.plan), "E_EXECUTION_SCOPE")
        self.brief["allowedActions"] = ["read"]
        self.api.validate_task_brief(self.brief, self.plan)
        self.plan["tasks"][0]["prdRefs"].append("AC-2")
        self.plan["tasks"][0]["acceptanceCriteria"].append("AC-2")
        self.brief["binding"] = binding(self.plan)
        self.assert_issue(
            lambda: self.api.validate_task_brief(self.brief, self.plan), "E_EXECUTION_REFERENCE"
        )

    def test_ac4_payload_required_fields_and_declared_references(self):
        for kind, (_, _, payload) in EVENTS.items():
            for field in payload:
                value = event(self.plan, kind)
                del value["payload"][field]
                self.assert_issue(
                    lambda: self.api.validate_execution_event(value, self.plan), "E_SCHEMA_REQUIRED"
                )
        value = event(self.plan, "PLAN_UPDATED")
        value["payload"]["previousRevision"] = self.plan["revision"]
        self.assert_issue(
            lambda: self.api.validate_execution_event(value, self.plan), "E_EXECUTION_BINDING"
        )
        value = event(self.plan, "VALIDATION_PASSED")
        value["payload"]["acceptanceCriteria"] = ["AC-2"]
        self.assert_issue(
            lambda: self.api.validate_execution_event(value, self.plan), "E_EXECUTION_REFERENCE"
        )

    def test_ac5_strict_reader_rejects_nonfinite_malformed_and_oversized_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            for content in (b'{"estimateMs":NaN}', b'{"estimateMs":Infinity}', b'{', b'"\xff"'):
                path.write_bytes(content)
                with self.assertRaises(ContractIssue):
                    strict_load_json(path)
            path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
            with self.assertRaises(ContractIssue) as caught:
                strict_load_json(path)
            self.assertEqual("E_INPUT_TOO_LARGE", caught.exception.code)

    def test_ac1_schema_vocabulary_and_scalar_bounds_match_runtime(self):
        schemas = {
            name: json.loads((SCRIPTS.parent / "contracts" / f"{name}.schema.json").read_text())
            for name in ("execution-plan", "task-brief", "task-result", "execution-event")
        }
        definitions = schemas["execution-plan"]["$defs"]
        self.assertEqual(self.api.MAX_NUMBER, definitions["positiveInteger"]["maximum"])
        self.assertEqual(self.api.MAX_ITEMS, schemas["execution-plan"]["properties"]["tasks"]["maxItems"])
        self.assertEqual(set(EVENTS), set(schemas["execution-event"]["properties"]["type"]["enum"]))
        path_pattern = re.compile(definitions["path"]["pattern"])
        for path in ("src/feature.py", "docs/a file.md", ".sdlc/memory/context.md"):
            self.assertIsNotNone(path_pattern.fullmatch(path))
        for path in ("../x", "/x", "C:/x", "src//x", "src/../x", "src/ x", "src/x "):
            self.assertIsNone(path_pattern.fullmatch(path))
        outcomes = schemas["task-result"]["properties"]["verification"]["items"]["properties"]["result"]["enum"]
        self.assertEqual(["passed", "failed", "not-run", "skipped", "unavailable"], outcomes)

    def test_ac1_schema_patterns_reject_trailing_newlines_like_runtime(self):
        schema = json.loads(
            (SCRIPTS.parent / "contracts" / "execution-plan.schema.json").read_text()
        )
        for name, text in (
            ("id", "task"),
            ("ref", "FR-1"),
            ("acceptanceRef", "AC-1"),
            ("path", "src/feature.py"),
            ("digest", DIGEST),
            ("text", "Declared text"),
        ):
            with self.subTest(definition=name):
                self.assertIsNone(re.search(schema["$defs"][name]["pattern"], text + "\n"))
        schema = json.loads(
            (SCRIPTS.parent / "contracts" / "execution-event.schema.json").read_text()
        )
        self.assertIsNone(
            re.search(schema["$defs"]["time"]["pattern"], "2026-11-01T15:00:00Z\n")
        )

    def test_ac6_validation_has_no_external_side_effects(self):
        with mock.patch.object(Path, "write_text", side_effect=AssertionError("write")), \
             mock.patch.object(Path, "read_text", side_effect=AssertionError("implicit read")), \
             mock.patch.object(subprocess, "run", side_effect=AssertionError("dispatch")), \
             mock.patch.object(socket, "socket", side_effect=AssertionError("network")):
            self.api.validate_execution_plan(self.plan)
            self.api.validate_task_brief(self.brief, self.plan)
            self.api.validate_task_result(result(self.plan), self.plan, self.brief)
            self.api.validate_execution_event(event(self.plan), self.plan)

    def test_ac1_schema_root_fields_match_fixtures_and_are_versioned(self):
        fixtures = {
            "execution-plan": self.plan,
            "task-brief": self.brief,
            "task-result": result(self.plan),
            "execution-event": event(self.plan),
        }
        for name, fixture in fixtures.items():
            with self.subTest(name=name):
                path = SCRIPTS.parent / "contracts" / f"{name}.schema.json"
                self.assertTrue(path.is_file(), f"Missing {name} contract")
                schema = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(f"urn:sdlc:{name}:1", schema["$id"])
                self.assertFalse(schema["additionalProperties"])
                self.assertEqual(set(fixture), set(schema["required"]))
                self.assertEqual(set(fixture), set(schema["properties"]))
                self.assertEqual({"const": 1}, schema["properties"]["schemaVersion"])


if __name__ == "__main__":
    unittest.main()
