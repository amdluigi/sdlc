#!/usr/bin/env python3
"""Deterministic extraction and reduction of sdlc run records.

This is the only supported way sdlc-evaluator is meant to read run-record
data: `extract` walks the project's run-record store (see manage_runs.py),
validates every record, and reduces it to a single bounded JSON digest —
closed-enum counts, friction signals, and blocker text — before any model
reasoning happens. This keeps the evaluator's prompt bounded regardless of
how many completed tasks a project has accumulated, and keeps the
reduction itself auditable and reproducible outside the model.

No prompts, code, diffs, or free-form artifact content are read or
emitted; only the closed fields already defined by
contracts/run-record.schema.json, plus the substantive-string fields the
schema already allows (blocker messages, evidence gaps/summaries,
correction references) which are themselves author-supplied, single-line,
and already bounded by the run-record contract.
"""

import argparse
import json
import sys

from manage_runs import RunsError, _validate_task_id, locate_runs_directory, _read_run_record
from manage_metrics import MetricsError
from adaptive_extensions import AdaptiveError
from config_contract import ConfigError

MAX_RUNS_PER_EXTRACT = 5_000


def _empty_counter(names):
    return {name: 0 for name in names}


def _increment(counter, key):
    counter[key] = counter.get(key, 0) + 1


def _reduce_module(module, aggregate):
    entry = aggregate.setdefault(
        module["id"],
        {
            "source": module["source"],
            "configuredEnabled": 0,
            "configuredDisabled": 0,
            "triggerStates": _empty_counter(("matched", "not-matched", "undetermined")),
            "evidenceStatuses": _empty_counter(
                (
                    "satisfied", "partial", "missing", "stale/unverified",
                    "configured-disabled", "not-applicable",
                )
            ),
            "instructionStates": _empty_counter(
                ("would-load", "loaded", "reused", "skipped", "blocked", "undetermined")
            ),
            "evidenceGaps": [],
        },
    )
    if module["configured"] == "enabled":
        entry["configuredEnabled"] += 1
    else:
        entry["configuredDisabled"] += 1
    _increment(entry["triggerStates"], module["trigger"]["state"])
    _increment(entry["evidenceStatuses"], module["evidence"]["status"])
    _increment(entry["instructionStates"], module["instruction"]["state"])
    for gap in module["evidence"]["gaps"]:
        if len(entry["evidenceGaps"]) < 50 and gap not in entry["evidenceGaps"]:
            entry["evidenceGaps"].append(gap)


def extract(project_root, task_ids=None):
    _, directory, category = locate_runs_directory(project_root, require_safe=False)
    if task_ids:
        for task_id in task_ids:
            _validate_task_id(task_id)
    if not directory.is_dir():
        paths = []
    elif task_ids:
        paths = [directory / f"{task_id}.json" for task_id in task_ids]
    else:
        paths = sorted(directory.glob("*.json"))
    if len(paths) > MAX_RUNS_PER_EXTRACT:
        raise RunsError("too many run records for a single extraction")

    rigor = _empty_counter(("trivial", "standard", "significant"))
    self_check = {
        "performed": 0,
        "producedCoverageReport": 0,
        "producedDisclosureLine": 0,
        "producedMemoryUpdate": _empty_counter((True, False, "not-applicable")),
        "retroactive": 0,
    }
    outcome = {"recorded": 0, "humanCorrected": 0, "correctionReferences": []}
    blockers_by_module = {}
    modules = {}
    facts = {}
    skipped = []
    considered = 0

    for path in paths:
        try:
            record = _read_run_record(path)
        except RunsError as error:
            skipped.append({"path": path.name, "reason": str(error)})
            continue
        considered += 1
        _increment(rigor, record["task"]["rigor"])
        for name, value in record["task"]["facts"].items():
            if value:
                facts[name] = facts.get(name, 0) + 1
        for module in record["modules"]:
            _reduce_module(module, modules)
        for blocker in record["blockers"]:
            bucket = blockers_by_module.setdefault(blocker["module"], [])
            if len(bucket) < 50 and blocker["message"] not in bucket:
                bucket.append(blocker["message"])
        check = record["selfCheck"]
        if check["performed"]:
            self_check["performed"] += 1
        if check["producedCoverageReport"]:
            self_check["producedCoverageReport"] += 1
        if check["producedDisclosureLine"]:
            self_check["producedDisclosureLine"] += 1
        if check["retroactive"]:
            self_check["retroactive"] += 1
        self_check["producedMemoryUpdate"][check["producedMemoryUpdate"]] += 1
        record_outcome = record.get("outcome")
        if record_outcome is not None:
            outcome["recorded"] += 1
            if record_outcome["humanCorrected"]:
                outcome["humanCorrected"] += 1
            for reference in record_outcome["correctionReferences"]:
                if (
                    len(outcome["correctionReferences"]) < 200
                    and reference not in outcome["correctionReferences"]
                ):
                    outcome["correctionReferences"].append(reference)

    self_check["producedMemoryUpdate"] = {
        "true" if key is True else "false" if key is False else key: value
        for key, value in self_check["producedMemoryUpdate"].items()
    }
    return {
        "schemaVersion": 1,
        "storeCategory": category,
        "runsConsidered": considered,
        "runsSkipped": skipped,
        "task": {"rigor": rigor, "facts": facts},
        "modules": modules,
        "blockers": blockers_by_module,
        "selfCheck": self_check,
        "outcome": outcome,
    }


def _parser():
    parser = argparse.ArgumentParser(
        description="Deterministically reduce sdlc run records for sdlc-evaluator."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    extract_command = commands.add_parser("extract")
    extract_command.add_argument("--project-root", required=True)
    extract_command.add_argument("--task", dest="task_ids", action="append", default=[])
    return parser


def main(argv=None):
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "extract":
            value = extract(arguments.project_root, arguments.task_ids or None)
        else:
            raise RunsError("unsupported command")
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
