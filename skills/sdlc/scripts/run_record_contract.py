"""Validation for sdlc-evaluator run records.

A run record extends the operator-state shape (task, modules,
configuredDisabledModules, blockers) — see operator_reports.py — with two
additive objects: selfCheck (whether the turn-end self-check produced or
found the coverage report/disclosure line/memory update) and outcome
(filled in later, asynchronously and read-only, by reconcile_runs.py).

See contracts/run-record.schema.json for the documented shape.
"""

from artifact_contracts import ContractIssue, require_object, require_string_array
from operator_reports import validate_operator_state

RUN_RECORD_FIELDS = (
    "schemaVersion", "task", "modules", "configuredDisabledModules",
    "blockers", "selfCheck", "outcome",
)
REQUIRED_RUN_RECORD_FIELDS = (
    "schemaVersion", "task", "modules", "configuredDisabledModules",
    "blockers", "selfCheck",
)
SELF_CHECK_FIELDS = (
    "performed", "producedCoverageReport", "producedDisclosureLine",
    "producedMemoryUpdate", "retroactive",
)
SELF_CHECK_BOOLEAN_FIELDS = (
    "performed", "producedCoverageReport", "producedDisclosureLine", "retroactive",
)
OUTCOME_FIELDS = ("humanCorrected", "correctionReferences")


def _validate_self_check(value):
    self_check = require_object(value, "/selfCheck", SELF_CHECK_FIELDS)
    for name in SELF_CHECK_BOOLEAN_FIELDS:
        if type(self_check[name]) is not bool:
            raise ContractIssue(
                "E_SELF_CHECK", f"/selfCheck/{name}", "expected boolean"
            )
    produced_memory = self_check["producedMemoryUpdate"]
    if not (
        type(produced_memory) is bool
        or produced_memory == "not-applicable"
    ):
        raise ContractIssue(
            "E_SELF_CHECK", "/selfCheck/producedMemoryUpdate",
            "expected true, false, or not-applicable",
        )
    return self_check


def _validate_outcome(value):
    outcome = require_object(value, "/outcome", OUTCOME_FIELDS)
    if type(outcome["humanCorrected"]) is not bool:
        raise ContractIssue(
            "E_OUTCOME", "/outcome/humanCorrected", "expected boolean"
        )
    require_string_array(
        outcome["correctionReferences"], "/outcome/correctionReferences",
        substantive=True,
    )
    return outcome


def validate_run_record(data):
    require_object(
        data, "", RUN_RECORD_FIELDS, required=REQUIRED_RUN_RECORD_FIELDS
    )
    if data["schemaVersion"] != 1:
        raise ContractIssue("E_SCHEMA_VERSION", "/schemaVersion", "expected 1")

    validate_operator_state(
        {
            "schemaVersion": 1,
            "task": data["task"],
            "modules": data["modules"],
            "configuredDisabledModules": data["configuredDisabledModules"],
            "blockers": data["blockers"],
        }
    )
    _validate_self_check(data["selfCheck"])
    if "outcome" in data:
        _validate_outcome(data["outcome"])
    return data
