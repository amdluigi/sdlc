"""Side-effect-free validation of explicitly supplied version-1 execution data."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import NoReturn

from artifact_contracts import (
    ContractIssue,
    ID_PATTERN,
    MAX_INPUT_BYTES,
    REF_PATTERN,
    require_array,
    require_object,
    require_string,
    require_string_array,
    semantic_fields,
)


MAX_ITEMS = 256
MAX_NUMBER = 2**63 - 1
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
PATH_PATTERN = re.compile(r"[A-Za-z0-9_.@ -]+(?:/[A-Za-z0-9_.@ -]+)*")
TIME_PATTERN = re.compile(r"[0-9]{4}(?:-[0-9]{2}){2}T[0-9]{2}(?::[0-9]{2}){2}Z")
EVENT_FIELDS = {
    "PLAN_PROPOSED": (False, False, ()),
    "PLAN_UPDATED": (False, False, ("previousRevision",)),
    "PLAN_APPROVED": (False, False, ("decisionId",)),
    "TASK_READY": (True, False, ()),
    "TASK_STARTED": (True, True, ()),
    "TASK_PROGRESS_UPDATED": (True, True, ("message",)),
    "TASK_BLOCKED": (True, False, ("reason",)),
    "TASK_UNBLOCKED": (True, False, ()),
    "TASK_RESULT_RECEIVED": (True, True, ("resultId",)),
    "VALIDATION_PASSED": (True, True, ("acceptanceCriteria",)),
    "VALIDATION_FAILED": (True, True, ("acceptanceCriteria", "reason")),
    "TASK_COMPLETED": (True, True, ()),
    "TASK_FAILED": (True, True, ("reason",)),
    "TASK_CANCELLED": (True, False, ("reason",)),
    "APPROVAL_REQUESTED": (False, False, ("decisionId", "reason")),
    "APPROVAL_GRANTED": (False, False, ("decisionId",)),
    "APPROVAL_REJECTED": (False, False, ("decisionId", "reason")),
}
CONTROLLER_EVENT_FIELDS = {
    "AUTONOMOUS_ATTEMPT_STARTED": ("batchId", "batchDigest", "briefDigest", "modelId"),
    "TASK_RETRY_READY": ("batchId", "batchDigest", "resultId", "nextAttemptId", "modelId"),
    "BATCH_ATTEMPT_ACCOUNTED": (
        "batchId", "batchDigest", "resultId", "briefDigest", "modelCalls", "toolCalls",
        "elapsedMs", "inputBytes", "outputBytes",
    ),
}
PROMPT_COMPONENT_FIELDS = (
    "executionProtocol", "taskBrief", "selectedRole", "sharedContext", "specialistContext",
    "requirements", "securityConstraints", "permittedTools", "history",
)
CONTROLLER_EVENT_V4_FIELDS = {
    "BATCH_ATTEMPT_ACCOUNTED": (
        "batchId", "batchDigest", "resultId", "briefDigest", "modelCalls", "toolCalls",
        "elapsedMs", "inputBytes", "outputBytes", "totalInputBytes", "promptComponents",
        "retries", "modelId", "providerId", "hostId", "hostBuild", "providerInputTokens",
        "providerOutputTokens", "cachedInputTokens", "billableInputTokens",
        "billableOutputTokens", "authoritativeCost",
    ),
}
CONTROLLER_EVENT_V5_FIELDS = {
    "BATCH_ATTEMPT_ACCOUNTED": (
        "batchId", "batchDigest", "resultId", "briefDigest", "modelCalls", "toolCalls",
        "elapsedMs", "inputBytes", "outputBytes", "totalInputBytes", "promptComponents",
        "retries", "modelId", "providerId", "hostId", "hostBuild", "providerInputTokens",
        "providerOutputTokens", "cachedInputTokens", "billableInputTokens",
        "billableOutputTokens", "authoritativeCost", "requestAccounting",
    ),
    "BATCH_ATTEMPT_ACCOUNTING_UNKNOWN": (
        "batchId", "batchDigest", "briefDigest", "modelCalls", "toolCalls", "elapsedMs",
        "inputBytes", "outputBytes", "totalInputBytes", "promptComponents", "retries",
        "modelId", "providerId", "hostId", "hostBuild", "providerInputTokens",
        "providerOutputTokens", "cachedInputTokens", "billableInputTokens",
        "billableOutputTokens", "authoritativeCost", "requestAccounting",
    ),
}


def _issue(code: str, pointer: str, message: str) -> NoReturn:
    raise ContractIssue(code, pointer or "/", message)


def _object(value: object, pointer: str, fields: tuple[str, ...]) -> dict[str, object]:
    if not isinstance(value, dict):
        _issue("E_SCHEMA_TYPE", pointer, "expected object")
    return require_object(value, pointer, fields)


def _text(value: object, pointer: str, maximum: int = 2048) -> str:
    text = require_string(value, pointer, maximum=maximum)
    if not text.strip() or any(ord(char) < 32 or ord(char) == 127 for char in text):
        _issue("E_SCHEMA_CONTENT", pointer, "expected nonempty text without control characters")
    return text


def _id(value: object, pointer: str) -> str:
    text = _text(value, pointer, 128)
    if not ID_PATTERN.fullmatch(text):
        _issue("E_EXECUTION_ID", pointer, "expected a lowercase kebab-case ID")
    return text


def _number(value: object, pointer: str, minimum: int = 1) -> int:
    if not isinstance(value, int) or type(value) is not int or not minimum <= value <= MAX_NUMBER:
        _issue("E_EXECUTION_NUMBER", pointer, "expected a bounded integer")
    return value


def _enum(value: object, pointer: str, choices: tuple[str, ...]) -> str:
    text = _text(value, pointer, 128)
    if text not in choices:
        _issue("E_EXECUTION_ENUM", pointer, "unsupported value")
    return text


def _array(value: object, pointer: str, nonempty: bool = False) -> list[object]:
    items = require_array(value, pointer, nonempty=nonempty)
    if len(items) > MAX_ITEMS:
        _issue("E_EXECUTION_LIMIT", pointer, f"expected at most {MAX_ITEMS} items")
    return items


def _strings(value: object, pointer: str, nonempty: bool = False) -> list[str]:
    _array(value, pointer, nonempty)
    try:
        items = require_string_array(value, pointer)
    except ContractIssue as error:
        if error.code != "E_SCHEMA_UNIQUE":
            raise
        raise ContractIssue(error.code, error.pointer, "duplicate array value") from None
    for index, item in enumerate(items):
        _text(item, f"{pointer}/{index}")
    return items


def _ids(value: object, pointer: str, nonempty: bool = False) -> list[str]:
    items = _strings(value, pointer, nonempty)
    for index, item in enumerate(items):
        _id(item, f"{pointer}/{index}")
    return items


def _refs(value: object, pointer: str, acceptance_only: bool = False) -> list[str]:
    items = _strings(value, pointer, True)
    for index, item in enumerate(items):
        if len(item) > 128 or not REF_PATTERN.fullmatch(item) or (
            acceptance_only and not item.startswith("AC-")
        ):
            _issue("E_EXECUTION_REFERENCE", f"{pointer}/{index}", "invalid requirement reference")
    return items


def _path(value: object, pointer: str) -> str:
    text = _text(value, pointer, 1024)
    if not PATH_PATTERN.fullmatch(text) or any(
        part in (".", "..") or part != part.strip() for part in text.split("/")
    ):
        _issue("E_EXECUTION_PATH", pointer, "expected a canonical project-relative portable path")
    return text


def _paths(value: object, pointer: str) -> list[str]:
    items = _strings(value, pointer)
    for index, item in enumerate(items):
        _path(item, f"{pointer}/{index}")
    return items


def _digest(value: object, pointer: str) -> str:
    text = _text(value, pointer, 71)
    if not DIGEST_PATTERN.fullmatch(text):
        _issue("E_EXECUTION_BINDING", pointer, "expected a lowercase SHA-256 digest")
    return text


def _version(value: dict[str, object]) -> None:
    if type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1:
        _issue("E_EXECUTION_VERSION", "/schemaVersion", "only schema version 1 is supported")


def _encoded(value: object) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                             allow_nan=False)
    except (TypeError, ValueError, RecursionError) as error:
        raise ContractIssue("E_EXECUTION_JSON", "/", "expected finite, acyclic JSON data") from error
    if len(encoded.encode("utf-8")) > MAX_INPUT_BYTES:
        _issue("E_INPUT_TOO_LARGE", "/", f"input exceeds {MAX_INPUT_BYTES} canonical bytes")
    return encoded


def _result(value: dict[str, object]) -> dict[str, object]:
    return {**semantic_fields(), "data": json.loads(_encoded(value))}


def _task(value: object, pointer: str) -> dict[str, object]:
    task = _object(value, pointer, (
        "id", "title", "outcome", "prdRefs", "prerequisites", "consumes", "produces",
        "execution", "assignment", "estimateMs", "ownership", "acceptanceCriteria", "verification",
    ))
    _id(task["id"], f"{pointer}/id")
    for field in ("title", "outcome", "verification"):
        _text(task[field], f"{pointer}/{field}")
    refs = _refs(task["prdRefs"], f"{pointer}/prdRefs")
    if not any(ref.startswith("FR-") for ref in refs):
        _issue("E_EXECUTION_REFERENCE", f"{pointer}/prdRefs", "expected a functional requirement")
    acceptance = _refs(task["acceptanceCriteria"], f"{pointer}/acceptanceCriteria", True)
    if not set(acceptance) <= set(refs):
        _issue("E_EXECUTION_REFERENCE", f"{pointer}/acceptanceCriteria", "criteria must be in prdRefs")
    for field in ("prerequisites", "consumes", "produces"):
        _ids(task[field], f"{pointer}/{field}")
    _paths(task["ownership"], f"{pointer}/ownership")
    execution = _object(task["execution"], f"{pointer}/execution", ("mode", "group"))
    mode = _enum(execution["mode"], f"{pointer}/execution/mode", ("sequential", "parallel"))
    if mode == "parallel":
        _id(execution["group"], f"{pointer}/execution/group")
    elif execution["group"] is not None:
        _issue("E_EXECUTION_SCOPE", f"{pointer}/execution/group", "sequential tasks require null group")
    assignment = _object(task["assignment"], f"{pointer}/assignment", ("agent", "modelProfile", "model"))
    _text(assignment["agent"], f"{pointer}/assignment/agent", 128)
    _id(assignment["modelProfile"], f"{pointer}/assignment/modelProfile")
    if assignment["model"] is not None:
        _text(assignment["model"], f"{pointer}/assignment/model", 128)
    if task["estimateMs"] is not None:
        _number(task["estimateMs"], f"{pointer}/estimateMs", 0)
    return task


def _plan(value: object) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    data = _object(value, "", ("schemaVersion", "executionId", "revision", "sourcePlan", "tasks"))
    _version(data)
    _id(data["executionId"], "/executionId")
    _number(data["revision"], "/revision")
    source = _object(data["sourcePlan"], "/sourcePlan", ("path", "digest", "prd"))
    _path(source["path"], "/sourcePlan/path")
    _digest(source["digest"], "/sourcePlan/digest")
    prd = _object(source["prd"], "/sourcePlan/prd", ("id", "version"))
    _id(prd["id"], "/sourcePlan/prd/id")
    _number(prd["version"], "/sourcePlan/prd/version")
    tasks: dict[str, dict[str, object]] = {}
    predecessors: dict[str, set[str]] = {}
    producers: dict[str, str] = {}
    groups: dict[str, list[str]] = {}
    for index, raw in enumerate(_array(data["tasks"], "/tasks", True)):
        pointer = f"/tasks/{index}"
        task = _task(raw, pointer)
        identifier = _id(task["id"], f"{pointer}/id")
        if identifier in tasks:
            _issue("E_EXECUTION_GRAPH", f"{pointer}/id", "duplicate task ID")
        tasks[identifier] = task
        predecessors[identifier] = set(_ids(task["prerequisites"], f"{pointer}/prerequisites"))
        for artifact in _ids(task["produces"], f"{pointer}/produces"):
            if artifact in producers:
                _issue("E_EXECUTION_GRAPH", f"{pointer}/produces", "artifact has multiple producers")
            producers[artifact] = identifier
        execution = _object(task["execution"], f"{pointer}/execution", ("mode", "group"))
        if execution["group"] is not None:
            groups.setdefault(_id(execution["group"], f"{pointer}/execution/group"), []).append(identifier)
    for identifier, dependencies in predecessors.items():
        if identifier in dependencies or not dependencies <= tasks.keys():
            _issue("E_EXECUTION_GRAPH", "/tasks", "unknown or self prerequisite")
    ancestors: dict[str, set[str]] = {}
    pending = set(tasks)
    while pending:
        ready = sorted(identifier for identifier in pending if predecessors[identifier] <= ancestors.keys())
        if not ready:
            _issue("E_EXECUTION_GRAPH", "/tasks", "prerequisite cycle")
        for identifier in ready:
            inherited = set(predecessors[identifier])
            for parent in predecessors[identifier]:
                inherited.update(ancestors[parent])
            ancestors[identifier] = inherited
            pending.remove(identifier)
    for identifier, task in tasks.items():
        for artifact in _ids(task["consumes"], "/tasks/consumes"):
            if artifact in producers and producers[artifact] not in ancestors[identifier]:
                _issue("E_EXECUTION_GRAPH", "/tasks", "consumer must depend on its artifact producer")
    for members in groups.values():
        owned: set[str] = set()
        for identifier in members:
            if ancestors[identifier].intersection(members):
                _issue("E_EXECUTION_GRAPH", "/tasks", "parallel group contains dependent tasks")
            paths = set(_paths(tasks[identifier]["ownership"], "/tasks/ownership"))
            if owned.intersection(paths):
                _issue("E_EXECUTION_GRAPH", "/tasks", "parallel group has overlapping ownership")
            owned.update(paths)
    _encoded(data)
    return data, tasks


def _bound_task(
    data: dict[str, object], plan: dict[str, object], tasks: dict[str, dict[str, object]]
) -> dict[str, object]:
    _binding(data["binding"], plan)
    identifier = _id(data["taskId"], "/taskId")
    if identifier not in tasks:
        _issue("E_EXECUTION_REFERENCE", "/taskId", "task is not in the supplied plan")
    return tasks[identifier]


def _binding(value: object, plan: dict[str, object]) -> None:
    binding = _object(value, "/binding", ("executionId", "planRevision", "planDigest"))
    _id(binding["executionId"], "/binding/executionId")
    _number(binding["planRevision"], "/binding/planRevision")
    _digest(binding["planDigest"], "/binding/planDigest")
    expected = {
        "executionId": plan["executionId"],
        "planRevision": plan["revision"],
        "planDigest": "sha256:" + hashlib.sha256(_encoded(plan).encode("utf-8")).hexdigest(),
    }
    for field in expected:
        if binding[field] != expected[field]:
            _issue("E_EXECUTION_BINDING", f"/binding/{field}", "binding does not match supplied plan")


def _brief(
    value: object, plan: dict[str, object], tasks: dict[str, dict[str, object]]
) -> dict[str, object]:
    data = _object(value, "", (
        "schemaVersion", "binding", "taskId", "attemptId", "allowedActions",
        "ownership", "guidance", "acceptanceCriteria", "verification",
    ))
    _version(data)
    task = _bound_task(data, plan, tasks)
    _id(data["attemptId"], "/attemptId")
    actions = _strings(data["allowedActions"], "/allowedActions", True)
    for index, action in enumerate(actions):
        _enum(action, f"/allowedActions/{index}", ("read", "search", "edit", "execute"))
    ownership = _paths(data["ownership"], "/ownership")
    if not set(ownership) <= set(_paths(task["ownership"], "/tasks/ownership")):
        _issue("E_EXECUTION_SCOPE", "/ownership", "ownership is outside the planned task")
    if "edit" in actions and not ownership:
        _issue("E_EXECUTION_SCOPE", "/ownership", "edit action requires explicit file ownership")
    _paths(data["guidance"], "/guidance")
    acceptance = _refs(data["acceptanceCriteria"], "/acceptanceCriteria", True)
    if set(acceptance) != set(_refs(task["acceptanceCriteria"], "/tasks/acceptanceCriteria", True)):
        _issue("E_EXECUTION_REFERENCE", "/acceptanceCriteria", "must cover the planned task criteria")
    _text(data["verification"], "/verification")
    _encoded(data)
    return data


def validate_execution_plan(data: object) -> dict[str, object]:
    """Check plan declarations, not source approval, readiness, or assignments."""
    plan, _ = _plan(data)
    return _result(plan)


def validate_task_brief(data: object, plan: object) -> dict[str, object]:
    """Check a brief against a supplied plan without granting execution permissions."""
    validated, tasks = _plan(plan)
    return _result(_brief(data, validated, tasks))


def validate_task_result(data: object, plan: object, brief: object) -> dict[str, object]:
    """Check a worker report, not whether verification ran or completion was accepted."""
    validated, tasks = _plan(plan)
    supplied = _brief(brief, validated, tasks)
    base_fields = (
        "schemaVersion", "binding", "taskId", "attemptId", "status",
        "artifacts", "verification", "findings", "blockers",
    )
    if not isinstance(data, dict):
        _issue("E_SCHEMA_TYPE", "/", "expected an object")
    if "schemaVersion" not in data:
        _issue("E_SCHEMA_REQUIRED", "/", "required field 'schemaVersion' is missing")
    version = data.get("schemaVersion")
    if type(version) is not int or version not in (1, 2):
        _issue("E_EXECUTION_VERSION", "/schemaVersion", "worker results require schema version 1 or 2")
    fields = base_fields if version == 1 else base_fields + ("contextUpdate",)
    value = _object(data, "", fields)
    if version == 1:
        _version(value)
    _bound_task(value, validated, tasks)
    _id(value["attemptId"], "/attemptId")
    for field in ("taskId", "attemptId"):
        if value[field] != supplied[field]:
            _issue("E_EXECUTION_BINDING", f"/{field}", "result does not match the supplied brief")
    _enum(value["status"], "/status", ("completed", "failed", "blocked", "cancelled"))
    artifacts = _paths(value["artifacts"], "/artifacts")
    if not set(artifacts) <= set(_paths(supplied["ownership"], "/ownership")) or (
        artifacts and "edit" not in _strings(supplied["allowedActions"], "/allowedActions")
    ):
        _issue("E_EXECUTION_SCOPE", "/artifacts", "artifacts are outside the brief's edit scope")
    acceptance = set(_refs(supplied["acceptanceCriteria"], "/acceptanceCriteria", True))
    for index, raw in enumerate(_array(value["verification"], "/verification")):
        pointer = f"/verification/{index}"
        entry = _object(raw, pointer, ("acceptanceCriterion", "command", "result", "revision", "summary"))
        criterion = _text(entry["acceptanceCriterion"], f"{pointer}/acceptanceCriterion", 128)
        if criterion not in acceptance:
            _issue("E_EXECUTION_REFERENCE", f"{pointer}/acceptanceCriterion", "criterion is outside brief")
        _enum(entry["result"], f"{pointer}/result", ("passed", "failed", "not-run", "skipped", "unavailable"))
        for field in ("command", "revision"):
            if entry[field] is not None:
                _text(entry[field], f"{pointer}/{field}")
        _text(entry["summary"], f"{pointer}/summary")
    for field in ("findings", "blockers"):
        _strings(value[field], f"/{field}")
    if version == 2 and value["contextUpdate"] is not None:
        _text(value["contextUpdate"], "/contextUpdate", 2048)
    return _result(value)


def _time(value: object, pointer: str) -> datetime:
    text = _text(value, pointer, 128)
    if not TIME_PATTERN.fullmatch(text):
        _issue("E_EXECUTION_TIME", pointer, "expected a UTC timestamp with whole seconds and Z")
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise ContractIssue("E_EXECUTION_TIME", pointer, "invalid UTC calendar timestamp") from error


def validate_execution_event(data: object, plan: object) -> dict[str, object]:
    """Check one declared event, not authenticity, stream order, transitions, or approval."""
    validated, tasks = _plan(plan)
    value = _object(data, "", (
        "schemaVersion", "eventId", "binding", "sequence", "occurredAt", "recordedAt",
        "actor", "type", "taskId", "attemptId", "payload",
    ))
    _version(value)
    _id(value["eventId"], "/eventId")
    _binding(value["binding"], validated)
    _number(value["sequence"], "/sequence")
    occurred = _time(value["occurredAt"], "/occurredAt")
    if _time(value["recordedAt"], "/recordedAt") < occurred:
        _issue("E_EXECUTION_TIME", "/recordedAt", "recordedAt precedes occurredAt")
    actor = _object(value["actor"], "/actor", ("role", "id"))
    role = _enum(actor["role"], "/actor/role", ("user", "host", "manager", "worker", "validator"))
    _id(actor["id"], "/actor/id")
    kind = _enum(value["type"], "/type", tuple(EVENT_FIELDS))
    if kind in ("PLAN_APPROVED", "APPROVAL_GRANTED", "APPROVAL_REJECTED") and role not in ("user", "host"):
        _issue("E_EXECUTION_ACTOR", "/actor/role", "approval declarations require user or host role")
    has_task, has_attempt, fields = EVENT_FIELDS[kind]
    if has_task:
        _bound_task(value, validated, tasks)
    elif value["taskId"] is not None:
        _issue("E_EXECUTION_REFERENCE", "/taskId", "execution-level event requires null task")
    if has_attempt:
        if value["attemptId"] is None:
            _issue("E_EXECUTION_REFERENCE", "/attemptId", "attempt ID is required")
        _id(value["attemptId"], "/attemptId")
    elif value["attemptId"] is not None:
        _issue("E_EXECUTION_REFERENCE", "/attemptId", "event requires null attempt")
    payload = _object(value["payload"], "/payload", fields)
    for field in fields:
        pointer = f"/payload/{field}"
        if field == "previousRevision":
            if _number(payload[field], pointer) >= _number(validated["revision"], "/revision"):
                _issue("E_EXECUTION_BINDING", pointer, "previous revision must precede current revision")
        elif field == "acceptanceCriteria":
            criteria = _refs(payload[field], pointer, True)
            task = tasks[_id(value["taskId"], "/taskId")]
            if not set(criteria) <= set(_refs(task["acceptanceCriteria"], "/tasks/acceptanceCriteria", True)):
                _issue("E_EXECUTION_REFERENCE", pointer, "criteria are outside the planned task")
        elif field in ("decisionId", "resultId"):
            _id(payload[field], pointer)
        else:
            _text(payload[field], pointer)
    return _result(value)


def validate_controller_event(data: object, plan: object) -> dict[str, object]:
    """Validate an explicitly versioned retry/accounting event."""
    validated, tasks = _plan(plan)
    value = _object(data, "", (
        "schemaVersion", "eventId", "binding", "sequence", "occurredAt", "recordedAt",
        "actor", "type", "taskId", "attemptId", "payload",
    ))
    version = value["schemaVersion"]
    if type(version) is not int or version not in (2, 3, 4, 5):
        _issue("E_EXECUTION_VERSION", "/schemaVersion", "controller events require schema version 2, 3, 4 or 5")
    _id(value["eventId"], "/eventId")
    _binding(value["binding"], validated)
    _number(value["sequence"], "/sequence")
    occurred = _time(value["occurredAt"], "/occurredAt")
    if _time(value["recordedAt"], "/recordedAt") < occurred:
        _issue("E_EXECUTION_TIME", "/recordedAt", "recordedAt precedes occurredAt")
    actor = _object(value["actor"], "/actor", ("role", "id"))
    if actor != {"role": "manager", "id": "local-orchestrator"}:
        _issue("E_EXECUTION_ACTOR", "/actor", "controller event is outside the manager boundary")
    event_fields = (
        CONTROLLER_EVENT_V5_FIELDS if version == 5 else
        CONTROLLER_EVENT_V4_FIELDS if version == 4 else CONTROLLER_EVENT_FIELDS
    )
    kind = _enum(value["type"], "/type", tuple(event_fields))
    if (kind == "AUTONOMOUS_ATTEMPT_STARTED") != (version == 3) or (
        version == 4 and kind != "BATCH_ATTEMPT_ACCOUNTED"
    ) or (
        version == 5 and kind not in ("BATCH_ATTEMPT_ACCOUNTED", "BATCH_ATTEMPT_ACCOUNTING_UNKNOWN")
    ):
        _issue("E_EXECUTION_VERSION", "/schemaVersion",
               "autonomous starts require version 3; detailed and unresolved accounting require versions 4 and 5")
    _bound_task(value, validated, tasks)
    _id(value["attemptId"], "/attemptId")
    fields = event_fields[kind]
    payload = _object(value["payload"], "/payload", fields)
    _id(payload["batchId"], "/payload/batchId")
    _digest(payload["batchDigest"], "/payload/batchDigest")
    if kind == "AUTONOMOUS_ATTEMPT_STARTED":
        _digest(payload["briefDigest"], "/payload/briefDigest")
        model_id = _text(payload["modelId"], "/payload/modelId", 128)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", model_id):
            _issue("E_MODEL_ID", "/payload/modelId", "invalid model identifier")
    elif kind == "TASK_RETRY_READY":
        _id(payload["resultId"], "/payload/resultId")
        _id(payload["nextAttemptId"], "/payload/nextAttemptId")
        model_id = _text(payload["modelId"], "/payload/modelId", 128)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", model_id):
            _issue("E_MODEL_ID", "/payload/modelId", "invalid model identifier")
    elif version in (4, 5):
        for field in ("modelCalls", "toolCalls", "elapsedMs", "inputBytes", "outputBytes",
                      "totalInputBytes", "retries"):
            _number(payload[field], "/payload/" + field, 0)
        if payload["totalInputBytes"] > payload["inputBytes"]:
            _issue("E_EXECUTION_ACCOUNTING", "/payload/totalInputBytes",
                   "model-facing input bytes exceed bounded input bytes")
        if payload["retries"] > 1:
            _issue("E_EXECUTION_ACCOUNTING", "/payload/retries", "retry count exceeds the attempt bound")
        components = _object(payload["promptComponents"], "/payload/promptComponents", PROMPT_COMPONENT_FIELDS)
        for component in PROMPT_COMPONENT_FIELDS:
            _number(components[component], "/payload/promptComponents/" + component, 0)
        if sum(components.values()) != payload["totalInputBytes"]:
            _issue("E_EXECUTION_ACCOUNTING", "/payload/promptComponents",
                   "component totals differ from model-facing input bytes")
        model_id = _text(payload["modelId"], "/payload/modelId", 128)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", model_id):
            _issue("E_MODEL_ID", "/payload/modelId", "invalid model identifier")
        _text(payload["providerId"], "/payload/providerId", 128)
        _id(payload["hostId"], "/payload/hostId")
        _text(payload["hostBuild"], "/payload/hostBuild", 128)
        for field in ("providerInputTokens", "providerOutputTokens", "cachedInputTokens",
                      "billableInputTokens", "billableOutputTokens"):
            if payload[field] is not None:
                _number(payload[field], "/payload/" + field, 0)
        if payload["authoritativeCost"] is not None:
            _issue("E_EXECUTION_ACCOUNTING", "/payload/authoritativeCost",
                   "authoritative cost is unavailable from the current host")
        if version == 5:
            _digest(payload["briefDigest"], "/payload/briefDigest")
            if kind == "BATCH_ATTEMPT_ACCOUNTED":
                _id(payload["resultId"], "/payload/resultId")
            accounting = _object(payload["requestAccounting"], "/payload/requestAccounting", (
                "prepared", "dispatched", "completed", "interrupted", "unknown",
            ))
            for field in ("prepared", "dispatched", "completed", "interrupted", "unknown"):
                _number(accounting[field], "/payload/requestAccounting/" + field, 0)
            if (
                accounting["prepared"] < accounting["dispatched"]
                or accounting["prepared"] < accounting["completed"] + accounting["interrupted"]
                + accounting["unknown"]
                or accounting["dispatched"] < accounting["completed"] + accounting["interrupted"]
            ):
                _issue("E_EXECUTION_ACCOUNTING", "/payload/requestAccounting",
                       "request lifecycle totals are inconsistent")
            for field in ("providerInputTokens", "providerOutputTokens", "cachedInputTokens",
                          "billableInputTokens", "billableOutputTokens"):
                if payload[field] is not None:
                    _issue("E_EXECUTION_ACCOUNTING", "/payload/" + field,
                           "provider usage is unavailable from the current host")
            if payload["authoritativeCost"] is not None:
                _issue("E_EXECUTION_ACCOUNTING", "/payload/authoritativeCost",
                       "authoritative provider pricing is unavailable")
    else:
        _id(payload["resultId"], "/payload/resultId")
        _digest(payload["briefDigest"], "/payload/briefDigest")
        for field in ("modelCalls", "toolCalls", "elapsedMs", "inputBytes", "outputBytes"):
            _number(payload[field], "/payload/" + field, 0)
    return _result(value)
