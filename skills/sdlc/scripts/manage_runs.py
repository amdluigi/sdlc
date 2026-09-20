#!/usr/bin/env python3
"""Manage per-task run records for the sdlc-evaluator meta-skill.

Run records are written by the sdlc orchestrator's turn-end self-check,
gated by the project-local `evaluation.enabled` config flag (independent
of `measurement.enabled`; see contracts/run-record.schema.json). They are
stored the same way private local metrics are: alongside real git metadata
when available (`.git/sdlc/runs/<task-id>.json`), or in a git-ignore-
verified `.sdlc/local/runs/<task-id>.json` for worktrees, submodules, and
non-git projects. There is no global, cross-project store.

Each write replaces the record for its task ID in full; a run record is
not a counter and is not append-only. This lets the turn-end self-check
correct its own `selfCheck` block if it discovers a gap after the fact
within the same task, and lets `reconcile_runs.py` fill in `outcome` later
without a separate merge step.
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from adaptive_extensions import AdaptiveError, load_json_strict
from config_contract import ConfigError, normalize_config
import manage_metrics
from manage_metrics import MetricsError
from artifact_contracts import ContractIssue, ID_PATTERN, strict_load_json
from run_record_contract import validate_run_record

MAX_RUN_RECORD_BYTES = 65_536


class RunsError(ValueError):
    pass


def _is_link_or_reparse(path):
    return manage_metrics._is_link_or_reparse(path)


def _run_git(root, arguments, capture=False):
    return manage_metrics._run_git(root, arguments, capture=capture)


def _local_runs_are_ignored(root):
    result = _run_git(
        root, ["check-ignore", "--no-index", "--quiet", "--", ".sdlc/local/runs"]
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise RunsError("ignore-verification-unavailable")


def locate_runs_directory(project_root, require_safe=True):
    root = Path(project_root)
    if not root.is_dir():
        raise RunsError("project root must be an existing directory")
    root = root.resolve(strict=True)
    git = root / ".git"
    if git.is_dir() and not _is_link_or_reparse(git):
        directory = git / "sdlc" / "runs"
        category = "git-local"
    elif git.exists() or git.is_symlink():
        if not manage_metrics._valid_gitfile_project(root, git):
            raise RunsError("git-metadata-unsupported")
        directory = root / ".sdlc" / "local" / "runs"
        category = "gitfile-local"
        if require_safe and not _local_runs_are_ignored(root):
            raise RunsError("local-store-not-ignored")
    else:
        directory = root / ".sdlc" / "local" / "runs"
        category = "non-git-local"
        if require_safe and not _local_runs_are_ignored(root):
            raise RunsError("local-store-not-ignored")
    return root, manage_metrics._verify_existing_components(root, directory), category


def _registry_names():
    return manage_metrics._registry_names()


def _phase_index():
    return manage_metrics._phase_index()


def evaluation_enabled(project_root):
    root = Path(project_root).resolve(strict=True)
    path = root / ".sdlc" / "config.json"
    if not path.is_file():
        return False
    if _is_link_or_reparse(path):
        raise RunsError("project config must not be a link or reparse point")
    try:
        config = normalize_config(
            load_json_strict(path), _registry_names(), _phase_index()
        )
    except (AdaptiveError, ConfigError) as error:
        raise RunsError(str(error)) from error
    return config["evaluation"]["enabled"]


def _write_atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        )
        temporary_path = Path(temporary_name)
        os.chmod(temporary_path, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _read_run_record(path):
    if not path.is_file():
        raise RunsError("run-record-unavailable:absent")
    if _is_link_or_reparse(path):
        raise RunsError("run-record-invalid-path:link")
    if path.stat().st_size > MAX_RUN_RECORD_BYTES:
        raise RunsError("run-record-corrupt:too-large")
    try:
        value = load_json_strict(path)
    except AdaptiveError as error:
        raise RunsError("run-record-corrupt:invalid-json") from error
    except UnicodeError as error:
        raise RunsError("run-record-corrupt:invalid-encoding") from error
    except OSError as error:
        raise RunsError("run-record-unavailable:read-failed") from error
    try:
        return validate_run_record(value)
    except ContractIssue as error:
        raise RunsError(f"run-record-corrupt:{error.code}") from error


def _serialized_size(data):
    return len(json.dumps(data, sort_keys=True, indent=2).encode("utf-8")) + 1


def record(project_root, input_path):
    try:
        data = strict_load_json(input_path)
        data = validate_run_record(data)
    except ContractIssue as error:
        raise RunsError(f"run-record-invalid:{error.code}:{error.pointer}") from error
    if _serialized_size(data) > MAX_RUN_RECORD_BYTES:
        raise RunsError("run-record-invalid:too-large")
    if not evaluation_enabled(project_root):
        return {"status": "disabled", "written": False}
    _, directory, _ = locate_runs_directory(project_root)
    path = directory / f"{data['task']['id']}.json"
    _write_atomic(path, data)
    return {"status": "written", "written": True, "path": str(path)}


def _validate_task_id(task_id):
    if not isinstance(task_id, str) or not ID_PATTERN.fullmatch(task_id):
        raise RunsError("task id must be a kebab-case identifier")
    return task_id


def set_outcome(project_root, task_id, human_corrected, references):
    _validate_task_id(task_id)
    if type(human_corrected) is not bool:
        raise RunsError("human-corrected must be boolean")
    if not isinstance(references, list) or not all(
        isinstance(item, str) for item in references
    ):
        raise RunsError("references must be a list of strings")
    if not evaluation_enabled(project_root):
        return {"status": "disabled", "written": False}
    _, directory, _ = locate_runs_directory(project_root)
    path = directory / f"{task_id}.json"
    data = _read_run_record(path)
    data = dict(data)
    data["outcome"] = {
        "humanCorrected": human_corrected,
        "correctionReferences": references,
    }
    data = validate_run_record(data)
    if _serialized_size(data) > MAX_RUN_RECORD_BYTES:
        raise RunsError("run-record-invalid:too-large")
    _write_atomic(path, data)
    return {"status": "written", "written": True, "path": str(path)}


def list_runs(project_root):
    _, directory, category = locate_runs_directory(project_root, require_safe=False)
    if not directory.is_dir():
        return {"storeCategory": category, "taskIds": []}
    task_ids = sorted(
        path.stem for path in directory.glob("*.json") if path.is_file()
    )
    return {"storeCategory": category, "taskIds": task_ids}


def _parser():
    parser = argparse.ArgumentParser(
        description="Manage private project-local sdlc-evaluator run records."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    record_command = commands.add_parser("record")
    record_command.add_argument("--project-root", required=True)
    record_command.add_argument("--input", dest="input_path", required=True, type=Path)
    outcome_command = commands.add_parser("set-outcome")
    outcome_command.add_argument("--project-root", required=True)
    outcome_command.add_argument("--task", dest="task_id", required=True)
    outcome_command.add_argument(
        "--human-corrected", choices=("true", "false"), required=True
    )
    outcome_command.add_argument(
        "--reference", dest="references", action="append", default=[]
    )
    list_command = commands.add_parser("list")
    list_command.add_argument("--project-root", required=True)
    return parser


def main(argv=None):
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "record":
            value = record(arguments.project_root, arguments.input_path)
        elif arguments.command == "set-outcome":
            value = set_outcome(
                arguments.project_root,
                arguments.task_id,
                arguments.human_corrected == "true",
                arguments.references,
            )
        else:
            value = list_runs(arguments.project_root)
        print(json.dumps(value, sort_keys=True, indent=2))
        return 0
    except (RunsError, MetricsError, AdaptiveError, ConfigError, UnicodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except OSError:
        print("error: operation-failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
