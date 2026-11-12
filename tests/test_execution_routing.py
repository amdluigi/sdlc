import copy
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_execution_contracts import SCRIPTS, plan, binding
from tests.test_execution_orchestration import batch
from artifact_contracts import ContractIssue


def routing_policy():
    return {
        "schemaVersion": 1, "kind": "sdlc-model-routing-policy",
        "permittedModels": ["model-one", "model-two", "model-three"],
        "models": [
            {"id": "model-one", "capacity": 2, "costRank": 1},
            {"id": "model-two", "capacity": 3, "costRank": 3},
            {"id": "model-three", "capacity": 3, "costRank": 2},
        ],
        "profiles": [{
            "id": "host-default", "minimumCapacity": 1,
            "candidates": ["model-two", "model-one", "model-three"],
        }],
    }


def inventory():
    return {
        "schemaVersion": 1, "hostId": "fixture-host", "hostBuild": "synthetic",
        "source": "host-observation",
        "models": [
            {"id": name, "available": True, "pricing": None}
            for name in ("model-one", "model-two", "model-three")
        ],
    }


class ExecutionRoutingTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(
            (SCRIPTS / "execution_routing.py").is_file(),
            "AC-5/AC-17: task-aware finite model planning is not provided",
        )
        self.api = importlib.import_module("execution_routing")
        self.plan = plan()
        self.batch = batch(self.plan)
        self.inventory = inventory()
        self.policy = routing_policy()

    def propose(self):
        return self.api.propose_routing(
            self.plan, self.batch, self.inventory, self.policy,
        )

    def materialize(self, proposal):
        return self.api.materialize_routing(
            self.plan, self.batch, self.inventory, self.policy, proposal,
        )

    def assert_issue(self, call, code):
        with self.assertRaises(ContractIssue) as caught:
            call()
        self.assertEqual(code, caught.exception.code)

    def rebind(self):
        for item in self.batch["tasks"]:
            for attempt in item["attempts"]:
                attempt["brief"]["binding"] = binding(self.plan)

    def test_selects_lowest_declared_rank_and_preplans_stronger_fallback(self):
        before = copy.deepcopy((self.plan, self.batch, self.inventory, self.policy))
        proposed = self.propose()
        self.assertFalse(proposed["active"])
        self.assertEqual(["model-one", "model-three"],
                         [item["modelId"] for item in proposed["decisions"]])
        self.assertEqual([2, 2], [item["requiredCapacity"] for item in proposed["decisions"]])
        self.assertEqual(["lowest-ranked-suitable", "stronger-fallback"],
                         [item["reason"] for item in proposed["decisions"]])
        self.assertEqual(proposed, self.propose())
        self.assertEqual(before, (self.plan, self.batch, self.inventory, self.policy))
        self.assertNotIn(self.plan["tasks"][0]["title"], json.dumps(proposed))
        self.assertNotIn("Run the acceptance test", json.dumps(proposed))

    def test_classification_and_profile_floor_cannot_be_lowered(self):
        self.plan["tasks"][0]["ownership"] = []
        for item in self.batch["tasks"][0]["attempts"]:
            item["brief"]["ownership"] = []
            item["brief"]["allowedActions"] = ["read", "search"]
        self.rebind()
        self.assertEqual(1, self.propose()["decisions"][0]["shapeCapacity"])
        self.policy["profiles"][0]["minimumCapacity"] = 3
        self.assertEqual(3, self.propose()["decisions"][0]["requiredCapacity"])
        self.plan["tasks"][0]["ownership"] = ["a.py", "b.py", "c.py", "d.py"]
        for item in self.batch["tasks"][0]["attempts"]:
            item["brief"]["ownership"] = self.plan["tasks"][0]["ownership"]
        self.rebind()
        self.policy["profiles"][0]["minimumCapacity"] = 1
        self.assertEqual(3, self.propose()["decisions"][0]["shapeCapacity"])
        self.assertEqual("model-three", self.propose()["decisions"][0]["modelId"])

    def test_unavailable_disallowed_and_out_of_profile_candidates_are_excluded(self):
        self.inventory["models"][0]["available"] = False
        self.assertEqual("model-three", self.propose()["decisions"][0]["modelId"])
        self.policy["permittedModels"].remove("model-three")
        self.assertEqual("model-two", self.propose()["decisions"][0]["modelId"])
        self.policy["profiles"][0]["candidates"] = ["model-one"]
        self.assert_issue(self.propose, "E_MODEL_UNAVAILABLE")

    def test_explicit_pin_is_respected_but_never_waives_suitability(self):
        self.plan["tasks"][0]["assignment"]["model"] = "model-two"
        self.rebind()
        proposed = self.propose()
        self.assertEqual(["model-two", "model-two"],
                         [item["modelId"] for item in proposed["decisions"]])
        self.assertEqual("explicit-model", proposed["decisions"][0]["reason"])
        self.assertEqual("same-model-retry", proposed["decisions"][1]["reason"])
        self.policy["models"][1]["capacity"] = 1
        self.assert_issue(self.propose, "E_ROUTING_CAPACITY")
        self.policy["models"][1]["capacity"] = 3
        self.policy["permittedModels"].remove("model-two")
        self.assert_issue(self.propose, "E_MODEL_DENIED")

    def test_tied_ranks_are_independent_of_candidate_order(self):
        self.policy["models"][1]["costRank"] = 2
        self.policy["models"][2]["costRank"] = 2
        proposed = self.propose()
        self.policy["profiles"][0]["candidates"].reverse()
        self.assertEqual(
            [item["modelId"] for item in proposed["decisions"]],
            [item["modelId"] for item in self.propose()["decisions"]],
        )

    def test_unknown_versions_fields_duplicate_ids_and_invalid_capacity_fail_closed(self):
        for key, value in (("schemaVersion", 2), ("unexpected", True)):
            with self.subTest(key=key):
                original = copy.deepcopy(self.policy)
                self.policy[key] = value
                with self.assertRaises(ContractIssue):
                    self.propose()
                self.policy = original
        for mutation in (
            lambda: self.policy["models"].append(copy.deepcopy(self.policy["models"][0])),
            lambda: self.policy["profiles"].append(copy.deepcopy(self.policy["profiles"][0])),
            lambda: self.policy["models"][0].update(capacity=True),
            lambda: self.policy["models"][0].update(capacity=4),
            lambda: self.policy["models"][0].update(costRank=-1),
            lambda: self.policy["profiles"][0].update(candidates=["missing-model"]),
            lambda: self.policy["permittedModels"].append("missing-model"),
        ):
            original = copy.deepcopy(self.policy)
            mutation()
            with self.assertRaises(ContractIssue):
                self.propose()
            self.policy = original

    def test_unavailable_inventory_and_missing_profile_are_explicit_errors(self):
        self.inventory = {
            "schemaVersion": 1, "hostId": None, "hostBuild": None,
            "source": "unavailable", "models": [],
        }
        self.assert_issue(self.propose, "E_MODEL_UNAVAILABLE")
        self.inventory = inventory()
        self.policy["profiles"] = []
        self.assert_issue(self.propose, "E_ROUTING_PROFILE")

    def test_stale_brief_or_batch_identity_and_wrong_role_are_rejected(self):
        self.batch["planRevision"] += 1
        self.assert_issue(self.propose, "E_ROUTING_BINDING")
        self.batch = batch(self.plan)
        self.batch["tasks"][0]["attempts"][0]["brief"]["binding"]["planDigest"] = "sha256:" + "b" * 64
        with self.assertRaises(ContractIssue):
            self.propose()
        self.batch = batch(self.plan)
        self.batch["tasks"][0]["role"] = "review"
        self.assert_issue(self.propose, "E_NATIVE_ROLE")

    def test_materialization_changes_only_exact_model_fields(self):
        proposal = self.propose()
        expected = copy.deepcopy(self.batch)
        expected["tasks"][0]["attempts"][1]["modelId"] = "model-three"
        self.assertEqual(expected, self.materialize(proposal))
        self.assertNotEqual(expected, self.batch)

    def test_materialized_choices_still_require_current_manager_consent(self):
        existing = importlib.import_module("tests.test_execution_orchestration")
        fixture = existing.ExecutionOrchestrationTests(
            "test_preview_is_disabled_read_only_and_spend_cap_fails_before_dispatch",
        )
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.plan, self.batch = fixture.plan, batch(fixture.plan)
        routed = self.materialize(self.propose())
        self.assert_issue(
            lambda: fixture.api.preview_batch(fixture.root, routed), "E_EXECUTION_DISABLED",
        )
        fixture.activate()
        self.assert_issue(
            lambda: fixture.api.preview_batch(fixture.root, routed), "E_MODEL_DENIED",
        )
        self.inventory["models"][2]["available"] = False
        routed = self.materialize(self.propose())
        preview = fixture.api.preview_batch(fixture.root, routed)
        before = fixture.manager.execution_path(fixture.root, "feature-one").read_bytes()
        self.assert_issue(
            lambda: fixture.api.next_attempt(fixture.root, routed, preview["batchDigest"]),
            "E_ORCHESTRATION_APPROVAL",
        )
        self.assertEqual(before, fixture.manager.execution_path(fixture.root, "feature-one").read_bytes())
        fixture.api.approve_batch(fixture.root, routed, preview["batchDigest"])
        self.assertEqual("attempt-one", fixture.api.next_attempt(
            fixture.root, routed, preview["batchDigest"],
        )["attemptId"])

    def test_materialization_rejects_tampering_or_changed_inputs(self):
        proposed = self.propose()
        for field in ("active", "proposalDigest", "extra"):
            altered = copy.deepcopy(proposed)
            altered[field] = True
            self.assert_issue(lambda: self.materialize(altered), "E_ROUTING_PROPOSAL")
        proposed["decisions"][0]["modelId"] = "model-two"
        self.assert_issue(lambda: self.materialize(proposed), "E_ROUTING_PROPOSAL")
        proposed = self.propose()
        for target, key, value in (
            (self.policy["models"][0], "costRank", 0),
            (self.inventory, "hostBuild", "changed"),
            (self.batch["tasks"][0]["attempts"][0]["limits"], "maxWallMs", 20000),
        ):
            previous = target[key]
            target[key] = value
            self.assert_issue(lambda: self.materialize(proposed), "E_ROUTING_PROPOSAL")
            target[key] = previous

    def test_actual_cli_success_errors_and_no_implicit_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            values = {"plan": self.plan, "batch": self.batch,
                      "inventory": self.inventory, "policy": self.policy}
            args = []
            for name, value in values.items():
                path = root / (name + ".json")
                path.write_text(json.dumps(value), encoding="utf-8")
                args.extend(["--" + name, str(path)])
            before = {path.name: path.read_bytes() for path in root.iterdir()}
            command = [sys.executable, "-B", str(SCRIPTS / "manage_routing.py")]
            env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
            run = subprocess.run([*command, "propose", *args], capture_output=True, text=True, env=env)
            self.assertEqual(0, run.returncode, run.stderr)
            proposal = json.loads(run.stdout)
            self.assertEqual(self.propose(), proposal)
            self.assertEqual(before, {path.name: path.read_bytes() for path in root.iterdir()})
            selected = root / "proposal.json"
            selected.write_text(json.dumps(proposal), encoding="utf-8")
            run = subprocess.run(
                [*command, "materialize", *args, "--proposal", str(selected)],
                capture_output=True, text=True, env=env,
            )
            self.assertEqual(0, run.returncode, run.stderr)
            self.assertEqual(self.materialize(proposal), json.loads(run.stdout))
            private = root / "policy.json"
            private.write_text('{"schemaVersion":1,"schemaVersion":1}', encoding="utf-8")
            run = subprocess.run([*command, "propose", *args], capture_output=True, text=True, env=env)
            self.assertNotEqual(0, run.returncode)
            self.assertEqual("", run.stdout)
            self.assertIn("E_JSON_DUPLICATE", run.stderr)
            self.assertNotIn(str(root), run.stderr)


if __name__ == "__main__":
    unittest.main()
