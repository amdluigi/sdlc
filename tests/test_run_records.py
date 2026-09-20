import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "sdlc" / "scripts"
MANAGE_RUNS = SCRIPTS / "manage_runs.py"
EVALUATE_RUNS = SCRIPTS / "evaluate_runs.py"

sys.path.insert(0, str(SCRIPTS))
from run_record_contract import validate_run_record  # noqa: E402
from artifact_contracts import ContractIssue  # noqa: E402


def sample_run_record(task_id="sample-task", **overrides):
    record = {
        "schemaVersion": 1,
        "task": {"id": task_id, "rigor": "standard", "facts": {}},
        "modules": [],
        "configuredDisabledModules": [],
        "blockers": [],
        "selfCheck": {
            "performed": True,
            "producedCoverageReport": True,
            "producedDisclosureLine": True,
            "producedMemoryUpdate": "not-applicable",
            "retroactive": False,
        },
    }
    record.update(overrides)
    return record


class RunRecordContractTest(unittest.TestCase):
    def test_accepts_a_minimal_valid_record(self):
        validate_run_record(sample_run_record())

    def test_rejects_a_missing_self_check(self):
        record = sample_run_record()
        del record["selfCheck"]
        with self.assertRaises(ContractIssue):
            validate_run_record(record)

    def test_rejects_an_invalid_produced_memory_update_value(self):
        record = sample_run_record()
        record["selfCheck"]["producedMemoryUpdate"] = "maybe"
        with self.assertRaises(ContractIssue):
            validate_run_record(record)

    def test_rejects_a_non_boolean_retroactive_flag(self):
        record = sample_run_record()
        record["selfCheck"]["retroactive"] = "no"
        with self.assertRaises(ContractIssue):
            validate_run_record(record)

    def test_rejects_numeric_produced_memory_update_masquerading_as_boolean(self):
        record = sample_run_record()
        record["selfCheck"]["producedMemoryUpdate"] = 1
        with self.assertRaises(ContractIssue):
            validate_run_record(record)

    def test_accepts_an_optional_outcome_block(self):
        record = sample_run_record(
            outcome={
                "humanCorrected": True,
                "correctionReferences": ["https://example.com/pr/1"],
            }
        )
        validate_run_record(record)

    def test_rejects_an_outcome_with_a_non_boolean_human_corrected(self):
        record = sample_run_record(
            outcome={"humanCorrected": "yes", "correctionReferences": []}
        )
        with self.assertRaises(ContractIssue):
            validate_run_record(record)

    def test_delegates_task_and_module_shape_to_operator_state_rules(self):
        record = sample_run_record()
        record["task"]["rigor"] = "urgent"
        with self.assertRaises(ContractIssue):
            validate_run_record(record)


class ManageRunsCliTest(unittest.TestCase):
    def setUp(self):
        self.project = ROOT / ".test-tmp" / "runs" / self.id().split(".")[-1]
        shutil.rmtree(self.project, ignore_errors=True)
        (self.project / ".git").mkdir(parents=True)
        self.write_config(False)

    def tearDown(self):
        shutil.rmtree(self.project, ignore_errors=True)

    def write_config(self, enabled):
        path = self.project / ".sdlc" / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schemaVersion": 3,
                    "modules": {},
                    "extensions": {"project": {}, "global": {}},
                    "measurement": {"enabled": False},
                    "evaluation": {"enabled": enabled},
                }
            ),
            encoding="utf-8",
        )

    def write_input(self, name, record):
        path = self.project / name
        path.write_text(json.dumps(record), encoding="utf-8")
        return path

    @property
    def store(self):
        return self.project / ".git" / "sdlc" / "runs"

    def run_cli(self, script, *arguments):
        return subprocess.run(
            [sys.executable, "-B", str(script), *arguments, "--project-root", str(self.project)],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

    def test_disabled_record_writes_nothing(self):
        input_path = self.write_input("run.json", sample_run_record())
        result = self.run_cli(MANAGE_RUNS, "record", "--input", str(input_path))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("disabled", json.loads(result.stdout)["status"])
        self.assertFalse(self.store.exists())

    def test_enabled_record_is_written_and_listed(self):
        self.write_config(True)
        input_path = self.write_input("run.json", sample_run_record())
        result = self.run_cli(MANAGE_RUNS, "record", "--input", str(input_path))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((self.store / "sample-task.json").is_file())

        listing = self.run_cli(MANAGE_RUNS, "list")
        self.assertEqual(0, listing.returncode, listing.stderr)
        self.assertEqual(["sample-task"], json.loads(listing.stdout)["taskIds"])

    def test_invalid_input_is_rejected_without_writing(self):
        self.write_config(True)
        record = sample_run_record()
        del record["selfCheck"]
        input_path = self.write_input("run.json", record)
        result = self.run_cli(MANAGE_RUNS, "record", "--input", str(input_path))
        self.assertEqual(2, result.returncode)
        self.assertFalse(self.store.exists())

    def test_set_outcome_round_trips_onto_an_existing_record(self):
        self.write_config(True)
        input_path = self.write_input("run.json", sample_run_record())
        self.run_cli(MANAGE_RUNS, "record", "--input", str(input_path))
        result = self.run_cli(
            MANAGE_RUNS, "set-outcome",
            "--task", "sample-task",
            "--human-corrected", "true",
            "--reference", "https://example.com/pr/1",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        stored = json.loads((self.store / "sample-task.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {
                "humanCorrected": True,
                "correctionReferences": ["https://example.com/pr/1"],
            },
            stored["outcome"],
        )

    def test_set_outcome_fails_without_an_existing_record(self):
        self.write_config(True)
        result = self.run_cli(
            MANAGE_RUNS, "set-outcome",
            "--task", "missing-task",
            "--human-corrected", "false",
        )
        self.assertEqual(2, result.returncode)

    def test_set_outcome_rejects_a_path_traversal_task_id(self):
        self.write_config(True)
        result = self.run_cli(
            MANAGE_RUNS, "set-outcome",
            "--task", "../../victim",
            "--human-corrected", "false",
        )
        self.assertEqual(2, result.returncode)
        self.assertFalse((self.project / "victim.json").exists())

    def test_record_rejects_a_record_larger_than_the_storage_limit(self):
        self.write_config(True)
        record = sample_run_record(
            outcome={
                "humanCorrected": False,
                "correctionReferences": ["x" * 70_000],
            }
        )
        input_path = self.write_input("run.json", record)
        result = self.run_cli(MANAGE_RUNS, "record", "--input", str(input_path))
        self.assertEqual(2, result.returncode)
        self.assertFalse(self.store.exists())


class EvaluateRunsCliTest(unittest.TestCase):
    def setUp(self):
        self.project = ROOT / ".test-tmp" / "runs-extract" / self.id().split(".")[-1]
        shutil.rmtree(self.project, ignore_errors=True)
        (self.project / ".git").mkdir(parents=True)
        path = self.project / ".sdlc" / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schemaVersion": 3,
                    "modules": {},
                    "extensions": {"project": {}, "global": {}},
                    "measurement": {"enabled": False},
                    "evaluation": {"enabled": True},
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.project, ignore_errors=True)

    def run_cli(self, script, *arguments):
        return subprocess.run(
            [sys.executable, "-B", str(script), *arguments, "--project-root", str(self.project)],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

    def record(self, task_id, **overrides):
        path = self.project / f"{task_id}-input.json"
        path.write_text(json.dumps(sample_run_record(task_id, **overrides)), encoding="utf-8")
        result = self.run_cli(MANAGE_RUNS, "record", "--input", str(path))
        self.assertEqual(0, result.returncode, result.stderr)

    def test_extract_reduces_across_multiple_records(self):
        self.record("task-one")
        self.record(
            "task-two",
            selfCheck={
                "performed": True,
                "producedCoverageReport": False,
                "producedDisclosureLine": True,
                "producedMemoryUpdate": True,
                "retroactive": True,
            },
        )
        result = self.run_cli(EVALUATE_RUNS, "extract")
        self.assertEqual(0, result.returncode, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(2, value["runsConsidered"])
        self.assertEqual(2, value["selfCheck"]["performed"])
        self.assertEqual(1, value["selfCheck"]["retroactive"])
        self.assertEqual(1, value["selfCheck"]["producedMemoryUpdate"]["true"])
        self.assertEqual(1, value["selfCheck"]["producedMemoryUpdate"]["not-applicable"])

    def test_extract_with_no_records_returns_a_zeroed_digest(self):
        result = self.run_cli(EVALUATE_RUNS, "extract")
        self.assertEqual(0, result.returncode, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(0, value["runsConsidered"])
        self.assertEqual([], value["runsSkipped"])

    def test_extract_rejects_a_path_traversal_task_id(self):
        result = self.run_cli(EVALUATE_RUNS, "extract", "--task", "../../secret")
        self.assertEqual(2, result.returncode)


if __name__ == "__main__":
    unittest.main()
