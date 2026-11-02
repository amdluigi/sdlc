"""Explicit local batch consent, dependency scheduling and receipt-bound retries."""

import json
import re

from artifact_contracts import ContractIssue, semantic_fields
import execution_contracts as contracts
import execution_controls as controls
import execution_manager as manager
import execution_state as state


_ATTEMPT_LIMITS = {
    "maxIterations": 16, "maxToolCalls": 32, "maxInputBytes": 262144,
    "maxOutputBytes": 262144, "maxWallMs": 300000,
}
_BATCH_LIMITS = {
    "maxCalls": 256, "maxToolCalls": 256, "maxWallMs": 300000,
    "maxInputBytes": 262144, "maxOutputBytes": 262144,
}


def _copy(value):
    return json.loads(contracts._encoded(value))


def terminal_reservations(events):
    from native_execution import BATCH_MARKER, RECEIPT_MARKER, REQUEST_MARKER
    pending = {}
    for event in events:
        identity = (event["taskId"], event["attemptId"])
        kind = event["type"]
        message = event["payload"].get("message", "")
        if kind == "TASK_PROGRESS_UPDATED" and message.startswith(BATCH_MARKER):
            pending[identity] = 4
        elif kind == "TASK_RETRY_READY":
            pending.pop(identity, None)
            pending[(event["taskId"], event["payload"]["nextAttemptId"])] = 8
        elif kind in ("VALIDATION_PASSED", "VALIDATION_FAILED", "TASK_FAILED"):
            pending.pop(identity, None)
        elif kind == "TASK_CANCELLED":
            pending = {key: count for key, count in pending.items() if key[0] != event["taskId"]}
        elif identity in pending and (
            kind in ("TASK_STARTED", "TASK_RESULT_RECEIVED", "BATCH_ATTEMPT_ACCOUNTED")
            or kind == "TASK_PROGRESS_UPDATED" and message.startswith((REQUEST_MARKER, RECEIPT_MARKER))
        ):
            pending[identity] -= 1
    return sum(pending.values())


def check_event_capacity(revision, kind, task_id, attempt_id, payload):
    proposed = {"type": kind, "taskId": task_id, "attemptId": attempt_id, "payload": payload or {}}
    events = [*revision["events"], proposed]
    reserved = terminal_reservations(events)
    if reserved and len(events) + reserved > contracts.MAX_ITEMS:
        raise ContractIssue("E_ORCHESTRATION_CAPACITY", "/events",
                            "batch receipt, accounting and independent judgment slots are reserved")


def validate_batch_contract(value):
    data = contracts._object(value, "", (
        "schemaVersion", "batchId", "executionId", "planRevision", "tasks", "limits", "maxSpendMinor",
    ))
    contracts._version(data)
    for field in ("batchId", "executionId"):
        contracts._id(data[field], "/" + field)
    contracts._number(data["planRevision"], "/planRevision")
    if data["maxSpendMinor"] is not None:
        contracts._number(data["maxSpendMinor"], "/maxSpendMinor", 0)
    limits = contracts._object(data["limits"], "/limits", tuple(_BATCH_LIMITS))
    for field, ceiling in _BATCH_LIMITS.items():
        if contracts._number(limits[field], "/limits/" + field, 1) > ceiling:
            raise ContractIssue("E_ORCHESTRATION_LIMIT", "/limits/" + field,
                                "batch limit exceeds the supported ceiling")
    tasks = contracts._array(data["tasks"], "/tasks", True)
    task_ids, attempt_ids = set(), set()
    for index, raw_task in enumerate(tasks):
        pointer = f"/tasks/{index}"
        item = contracts._object(raw_task, pointer, ("taskId", "role", "attempts"))
        contracts._id(item["taskId"], pointer + "/taskId")
        if item["taskId"] in task_ids:
            raise ContractIssue("E_ORCHESTRATION_DUPLICATE", pointer + "/taskId",
                                "batch task identity is duplicated")
        task_ids.add(item["taskId"])
        contracts._enum(item["role"], pointer + "/role", ("architecture", "developer", "testing", "review"))
        attempts = contracts._array(item["attempts"], pointer + "/attempts", True)
        for attempt_index, raw_attempt in enumerate(attempts):
            attempt_pointer = f"{pointer}/attempts/{attempt_index}"
            attempt = contracts._object(raw_attempt, attempt_pointer, ("attemptId", "modelId", "limits", "brief"))
            contracts._id(attempt["attemptId"], attempt_pointer + "/attemptId")
            if attempt["attemptId"] in attempt_ids:
                raise ContractIssue("E_ORCHESTRATION_DUPLICATE", attempt_pointer + "/attemptId",
                                    "attempt identity is duplicated in the batch")
            attempt_ids.add(attempt["attemptId"])
            model_id = contracts._text(attempt["modelId"], attempt_pointer + "/modelId", 128)
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", model_id):
                raise ContractIssue("E_MODEL_ID", attempt_pointer + "/modelId", "invalid model identifier")
            attempt_limits = contracts._object(
                attempt["limits"], attempt_pointer + "/limits", tuple(_ATTEMPT_LIMITS)
            )
            for field, ceiling in _ATTEMPT_LIMITS.items():
                if contracts._number(attempt_limits[field], attempt_pointer + "/limits/" + field, 1) > ceiling:
                    raise ContractIssue("E_ORCHESTRATION_LIMIT", attempt_pointer + "/limits/" + field,
                                        "per-attempt limit exceeds the runtime ceiling")
            brief = contracts._object(attempt["brief"], attempt_pointer + "/brief", (
                "schemaVersion", "binding", "taskId", "attemptId", "allowedActions",
                "ownership", "guidance", "acceptanceCriteria", "verification",
            ))
            contracts._version(brief)
            contracts._id(brief["taskId"], attempt_pointer + "/brief/taskId")
            contracts._id(brief["attemptId"], attempt_pointer + "/brief/attemptId")
            if brief["taskId"] != item["taskId"] or brief["attemptId"] != attempt["attemptId"]:
                raise ContractIssue("E_ORCHESTRATION_BINDING", attempt_pointer + "/brief",
                                    "brief task and attempt identities must match the batch entry")
    return _copy(data)


def batch_digest(batch, plan_digest, execution_policy_digest, controls_digest):
    for value in (plan_digest, execution_policy_digest, controls_digest):
        contracts._digest(value, "/batchDigest")
    batch = validate_batch_contract(batch)
    return state.digest({
        "schemaVersion": 1, "batch": batch, "planDigest": plan_digest,
        "executionPolicyDigest": execution_policy_digest, "controlsDigest": controls_digest,
    })


def _prepared_batch(project_root, value):
    batch = validate_batch_contract(value)
    if batch["maxSpendMinor"] is not None:
        raise ContractIssue("E_ORCHESTRATION_SPEND_UNAVAILABLE", "/maxSpendMinor",
                            "authoritative provider usage and pricing are unavailable")
    root = manager._root(project_root)
    manager._consent(root, enabled=True)
    store = controls._active(root)
    if store["schemaVersion"] not in (3, 4):
        raise ContractIssue("E_CONTROLS_CAPABILITY", "/", "explicit finite batch or autonomous controls are required")
    policy = store["policy"]
    if len(batch["tasks"]) > policy["maxBatchTasks"]:
        raise ContractIssue("E_ORCHESTRATION_LIMIT", "/tasks", "batch task count exceeds approved policy")
    for key, policy_key in (
        ("maxCalls", "maxBatchCalls"), ("maxToolCalls", "maxBatchToolCalls"),
        ("maxWallMs", "maxBatchWallMs"), ("maxInputBytes", "maxBatchInputBytes"),
        ("maxOutputBytes", "maxBatchOutputBytes"),
    ):
        if batch["limits"][key] > policy[policy_key]:
            raise ContractIssue("E_ORCHESTRATION_LIMIT", "/limits/" + key,
                                "batch exceeds the currently approved controls policy")
    attempts = 0
    reservations = {key: 0 for key in ("maxCalls", "maxToolCalls", "maxWallMs",
                                        "maxInputBytes", "maxOutputBytes")}
    permitted = set(policy["permittedModels"])
    record = manager._load(root, batch["executionId"])
    revision = record["revisions"][-1]
    current = manager.inspect_execution(root, batch["executionId"])
    plan_tasks = {task["id"]: task for task in current["plan"]["tasks"]}
    for index, item in enumerate(batch["tasks"]):
        if len(item["attempts"]) > min(policy["maxAttempts"], contracts.MAX_ITEMS):
            raise ContractIssue("E_ORCHESTRATION_LIMIT", f"/tasks/{index}/attempts",
                                "attempt allowance exceeds the approved controls policy")
        models = [attempt["modelId"] for attempt in item["attempts"]]
        if any(model not in permitted for model in models):
            raise ContractIssue("E_MODEL_DENIED", f"/tasks/{index}/attempts",
                                "every exact attempt model must already be permitted")
        if not policy["allowEscalation"] and len(set(models)) > 1:
            raise ContractIssue("E_CONTROLS_ESCALATION", f"/tasks/{index}/attempts",
                                "ordered model escalation is not permitted")
        for attempt in item["attempts"]:
            limits = attempt["limits"]
            reservations["maxCalls"] += limits["maxIterations"]
            reservations["maxToolCalls"] += limits["maxToolCalls"]
            reservations["maxWallMs"] += limits["maxWallMs"]
            reservations["maxInputBytes"] += limits["maxInputBytes"]
            reservations["maxOutputBytes"] += limits["maxOutputBytes"]
            validated_brief = contracts.validate_task_brief(attempt["brief"], revision["plan"])["data"]
            if validated_brief["taskId"] != item["taskId"] or validated_brief["attemptId"] != attempt["attemptId"]:
                raise ContractIssue("E_ORCHESTRATION_BINDING", f"/tasks/{index}/attempts",
                                    "attempt brief identity differs from its batch entry")
            planned = plan_tasks.get(item["taskId"])
            accepted_roles = {item["role"], "sdlc-" + item["role"]}
            if planned is None or planned["assignment"]["agent"].casefold() not in {
                name.casefold() for name in accepted_roles
            }:
                raise ContractIssue("E_NATIVE_ROLE", f"/tasks/{index}/role",
                                    "batch role does not match the approved plan assignment")
            if "execute" in validated_brief["allowedActions"]:
                raise ContractIssue("E_ORCHESTRATION_UNSUPPORTED", f"/tasks/{index}/attempts",
                                    "batch attempts do not authorize process execution")
            attempts += 1
    if any(reservations[key] > batch["limits"][key] for key in reservations):
        raise ContractIssue("E_ORCHESTRATION_LIMIT", "/limits",
                            "cumulative limit does not cover every approved bounded attempt")
    if batch["planRevision"] != current["plan"]["revision"]:
        raise ContractIssue("E_ORCHESTRATION_BINDING", "/planRevision", "batch does not bind the current plan")
    if not current["state"]["approved"]:
        raise ContractIssue("E_EXECUTION_APPROVAL", "/", "current manager plan approval is required")
    remaining = sum(
        8 for item in batch["tasks"]
        if current["state"]["tasks"][item["taskId"]]["status"] != "accepted"
        for attempt in item["attempts"]
        if attempt["attemptId"] not in current["state"]["attemptIds"]
        and attempt["attemptId"] != current["state"]["tasks"][item["taskId"]].get("pendingAttemptId")
    )
    remaining += terminal_reservations(revision["events"])
    if len(revision["events"]) + remaining > contracts.MAX_ITEMS:
        raise ContractIssue("E_ORCHESTRATION_CAPACITY", "/events",
                            "remaining ledger cannot hold all bounded attempts and terminal judgments")
    selected = {item["taskId"] for item in batch["tasks"]}
    selected_order = {item["taskId"]: index for index, item in enumerate(batch["tasks"])}
    for item in batch["tasks"]:
        planned = plan_tasks.get(item["taskId"])
        if planned is None:
            raise ContractIssue("E_ORCHESTRATION_REFERENCE", "/tasks", "batch references an unknown task")
        accepted = current["state"]["tasks"][item["taskId"]]["status"] == "accepted"
        missing = [parent for parent in planned["prerequisites"]
                   if current["state"]["tasks"][parent]["status"] != "accepted" and (
                       parent not in selected or selected_order[parent] > selected_order[item["taskId"]]
                   )]
        if missing and not accepted:
            raise ContractIssue("E_ORCHESTRATION_DEPENDENCY", "/tasks",
                                "unaccepted prerequisites must be included in the batch or accepted first")
    return root, batch, store, current


def preview_batch(project_root, value):
    root, batch, store, current = _prepared_batch(project_root, value)
    digest = batch_digest(batch, current["planDigest"], current["policyDigest"], controls._digest(store))
    projection = current["state"]["tasks"]
    eligible = []
    for item in batch["tasks"]:
        task_state = projection[item["taskId"]]
        eligible.append({
            "taskId": item["taskId"], "status": task_state["status"],
            "attempts": len(item["attempts"]), "nextAttemptId": item["attempts"][0]["attemptId"],
        })
    return {
        **semantic_fields(), "batchId": batch["batchId"], "batchDigest": digest,
        "planDigest": current["planDigest"], "executionPolicyDigest": current["policyDigest"],
        "controlsDigest": controls._digest(store),
        "taskCount": len(batch["tasks"]), "cumulativeLimits": batch["limits"],
        "schedule": eligible, "spend": "unavailable-not-capped",
        "dispatch": "not-started",
    }


def approve_batch(project_root, value, approved_digest):
    root, batch, store, current = _prepared_batch(project_root, value)
    expected = batch_digest(batch, current["planDigest"], current["policyDigest"], controls._digest(store))
    if approved_digest != expected:
        raise ContractIssue("E_ORCHESTRATION_APPROVAL", "/batchDigest",
                            "explicit consent must bind the exact current batch digest")
    return controls.approve_batch(
        root, batch, current["planDigest"], current["policyDigest"], controls._digest(store), expected
    )


def next_attempt(project_root, value, approved_digest):
    root, batch, store, current = _prepared_batch(project_root, value)
    approval = controls.batch_approval(root, batch)
    if approved_digest != approval["batchDigest"]:
        raise ContractIssue("E_ORCHESTRATION_APPROVAL", "/batchDigest", "batch consent digest differs")
    expected = batch_digest(batch, current["planDigest"], current["policyDigest"], controls._digest(store))
    if expected != approved_digest:
        raise ContractIssue("E_ORCHESTRATION_APPROVAL", "/batchDigest", "batch approval is stale")
    autonomous = store["policy"]["mode"] == "autonomous"
    if autonomous and store["paused"]:
        return {**semantic_fields(), "status": "paused", "dispatch": False}
    if autonomous and any(item["status"] == "pending" for item in store["cancelRequests"]):
        return {**semantic_fields(), "status": "cancellation-pending", "dispatch": False}
    tasks = current["state"]["tasks"]
    if autonomous:
        active = next((task_id for task_id, projected in tasks.items()
                       if projected["status"] in ("running", "blocked")), None)
        if active is not None:
            return {**semantic_fields(), "status": "unknown-barrier", "taskId": active, "dispatch": False}
    plan_tasks = {item["id"]: item for item in current["plan"]["tasks"]}
    deferred_barrier = None
    for item in batch["tasks"]:
        task_id = item["taskId"]
        projected = tasks[task_id]
        prerequisites = plan_tasks[task_id]["prerequisites"]
        if autonomous and projected["status"] in ("running", "blocked"):
            return {**semantic_fields(), "status": "unknown-barrier", "taskId": task_id, "dispatch": False}
        if any(tasks[parent]["status"] != "accepted" for parent in prerequisites):
            if autonomous and projected["status"] not in ("running", "blocked"):
                if deferred_barrier is None:
                    deferred_barrier = {**semantic_fields(), "status": "waiting-for-acceptance",
                                        "taskId": task_id, "dispatch": False}
                continue
            return {**semantic_fields(), "status": "waiting-for-acceptance", "taskId": task_id,
                    "dispatch": False}
        if projected["status"] == "accepted":
            continue
        if projected["status"] in ("running", "blocked"):
            return {**semantic_fields(), "status": "unknown-barrier", "taskId": task_id, "dispatch": False}
        if projected["status"] == "ready":
            pending_id = projected.get("pendingAttemptId")
            spec = next((candidate for candidate in item["attempts"]
                         if candidate["attemptId"] == pending_id), None) if pending_id else item["attempts"][0]
            if spec is None or (pending_id is None and spec["attemptId"] in current["state"]["attemptIds"]):
                return {**semantic_fields(), "status": "history-conflict", "taskId": task_id, "dispatch": False}
            return {**semantic_fields(), "status": "ready", "taskId": task_id,
                    "attemptId": spec["attemptId"], "modelId": spec["modelId"],
                    "brief": spec["brief"], "limits": spec["limits"],
                    "batchId": batch["batchId"], "batchDigest": approved_digest, "dispatch": True}
        if projected["status"] == "reported" or (
            projected["status"] == "failed" and projected["reportedStatus"] == "failed"
        ):
            if projected["reportedStatus"] != "failed":
                if autonomous:
                    if deferred_barrier is None:
                        deferred_barrier = {**semantic_fields(), "status": "waiting-for-acceptance",
                                            "taskId": task_id, "dispatch": False}
                    continue
                return {**semantic_fields(), "status": "waiting-for-acceptance", "taskId": task_id,
                        "dispatch": False}
            record = manager._load(root, batch["executionId"])
            prior = projected["attemptId"]
            candidates = item["attempts"]
            prior_index = next((index for index, candidate in enumerate(candidates)
                                if candidate["attemptId"] == prior), None)
            if prior_index is None:
                return {**semantic_fields(), "status": "not-retryable", "taskId": task_id, "dispatch": False}
            from native_execution import _metadata
            if not any(entry["resultId"] == projected["resultId"] for entry in _metadata(record)):
                return {**semantic_fields(), "status": "unknown-barrier", "taskId": task_id, "dispatch": False}
            revision = record["revisions"][-1]
            receipt = revision["receipts"].get(projected["resultId"])
            if receipt is None or not _retryable(receipt["result"]):
                if autonomous:
                    if deferred_barrier is None:
                        deferred_barrier = {**semantic_fields(), "status": "not-retryable",
                                            "taskId": task_id, "dispatch": False}
                    continue
                return {**semantic_fields(), "status": "not-retryable", "taskId": task_id, "dispatch": False}
            accounted = any(
                isinstance(event, dict) and event.get("schemaVersion") == 2
                and event["type"] == "BATCH_ATTEMPT_ACCOUNTED"
                and event["payload"]["batchId"] == batch["batchId"]
                and event["payload"]["batchDigest"] == approved_digest
                and event["payload"]["resultId"] == projected["resultId"]
                for event in revision["events"]
            )
            if not accounted:
                return {**semantic_fields(), "status": "unknown-barrier", "taskId": task_id, "dispatch": False}
            if prior_index + 1 >= len(candidates):
                if autonomous:
                    if deferred_barrier is None:
                        deferred_barrier = {**semantic_fields(), "status": "attempts-exhausted",
                                            "taskId": task_id, "dispatch": False}
                    continue
                return {**semantic_fields(), "status": "attempts-exhausted", "taskId": task_id,
                        "dispatch": False}
            next_spec = candidates[prior_index + 1]
            with manager._transaction(root, batch["executionId"], require_binding=False) as (locked, active_record, active):
                current_controls = controls._active(locked)
                current_digest = batch_digest(
                    batch, state.digest(active["plan"]), state.digest(active["consent"]),
                    controls._digest(current_controls),
                )
                if current_digest != approved_digest:
                    raise ContractIssue("E_ORCHESTRATION_APPROVAL", "/batchDigest",
                                        "batch policy or plan changed before retry authorization")
                controls.batch_approval(locked, batch)
                projection = manager._projection(active)
                state_task = projection["tasks"][task_id]
                if (
                    state_task["status"] != "reported" or state_task["reportedStatus"] != "failed"
                    or state_task["resultId"] != projected["resultId"] or state_task["attemptId"] != prior
                ):
                    raise ContractIssue("E_ORCHESTRATION_RETRY", "/", "failed receipt changed before retry authorization")
                manager._append_controller(active_record, active, "TASK_RETRY_READY", task_id, prior, {
                    "batchId": batch["batchId"], "batchDigest": approved_digest,
                    "resultId": projected["resultId"], "nextAttemptId": next_spec["attemptId"],
                    "modelId": next_spec["modelId"],
                })
            return {**semantic_fields(), "status": "ready", "taskId": task_id,
                    "attemptId": next_spec["attemptId"], "modelId": next_spec["modelId"],
                    "brief": next_spec["brief"], "limits": next_spec["limits"],
                    "batchId": batch["batchId"], "batchDigest": approved_digest, "dispatch": True}
        if projected["status"] == "waiting":
            first = item["attempts"][0]
            if first["attemptId"] in current["state"]["attemptIds"]:
                return {**semantic_fields(), "status": "history-conflict", "taskId": task_id, "dispatch": False}
            return {**semantic_fields(), "status": "ready", "taskId": task_id,
                    "attemptId": first["attemptId"], "modelId": first["modelId"],
                    "brief": first["brief"], "limits": first["limits"],
                    "batchId": batch["batchId"], "batchDigest": approved_digest, "dispatch": True}
        return {**semantic_fields(), "status": "waiting-for-review", "taskId": task_id, "dispatch": False}
    return deferred_barrier or {**semantic_fields(), "status": "complete", "dispatch": False}


def check_batch_attempt(project_root, batch, approved_digest, task_id, attempt_id, model_id, limits,
                        *, in_flight=False):
    root, batch, store, current = _prepared_batch(project_root, batch)
    approval = controls.batch_approval(root, batch)
    if approval["batchDigest"] != approved_digest or batch_digest(
        batch, current["planDigest"], current["policyDigest"], controls._digest(store)
    ) != approved_digest:
        raise ContractIssue("E_ORCHESTRATION_APPROVAL", "/batchDigest", "batch approval is stale")
    task = next((item for item in batch["tasks"] if item["taskId"] == task_id), None)
    attempt = None if task is None else next(
        (candidate for candidate in task["attempts"] if candidate["attemptId"] == attempt_id), None
    )
    if attempt is None or attempt["modelId"] != model_id or attempt["limits"] != limits:
        raise ContractIssue("E_ORCHESTRATION_BINDING", "/", "runtime choice differs from the exact batch attempt")
    projected = current["state"]["tasks"][task_id]
    ready_id = projected.get("pendingAttemptId")
    active = in_flight and projected["status"] == "running" and projected.get("attemptId") == attempt_id
    if (projected["status"] not in ("waiting", "ready") and not active) or (
        ready_id is not None and ready_id != attempt_id
    ) or (not active and ready_id is None and attempt_id != task["attempts"][0]["attemptId"]):
        raise ContractIssue("E_ORCHESTRATION_TRANSITION", "/", "attempt is not the next scheduled batch item")
    planned = next(item for item in current["plan"]["tasks"] if item["id"] == task_id)
    if any(current["state"]["tasks"][parent]["status"] != "accepted" for parent in planned["prerequisites"]):
        raise ContractIssue("E_ORCHESTRATION_DEPENDENCY", "/", "all prerequisite judgments must be accepted")
    return {**semantic_fields(), "batch": batch, "batchDigest": approved_digest,
            "attempt": attempt, "taskId": task_id}


def _retryable(result):
    verification = result["verification"]
    return (
        result["status"] == "failed" and not result["blockers"] and not result["findings"]
        and bool(verification)
        and any(item["result"] == "failed" for item in verification)
        and all(item["result"] in ("failed", "passed") for item in verification)
    )


def record_accounting_locked(root, record, revision, batch_id, batch_digest_value, task_id,
                             attempt_id, result_id, usage):
    batch_id = contracts._id(batch_id, "/batchId")
    contracts._digest(batch_digest_value, "/batchDigest")
    for value, pointer in ((task_id, "/taskId"), (attempt_id, "/attemptId"), (result_id, "/resultId")):
        contracts._id(value, pointer)
    usage = contracts._object(usage, "/usage", (
        "modelCalls", "toolCalls", "elapsedMs", "inputBytes", "outputBytes",
    ))
    for field in usage:
        contracts._number(usage[field], "/usage/" + field, 0)
    store = controls._active(root)
    approval = store["batchApprovals"].get(batch_id)
    if approval is None or approval["batchDigest"] != batch_digest_value:
        raise ContractIssue("E_ORCHESTRATION_APPROVAL", "/", "attempt accounting is not bound to approved batch")
    attempt = next(
        (candidate for candidate in approval["attempts"]
         if candidate["taskId"] == task_id and candidate["attemptId"] == attempt_id), None
    )
    if attempt is None:
        raise ContractIssue("E_ORCHESTRATION_BINDING", "/", "attempt is absent from the approved batch")
    receipt = revision["receipts"].get(result_id)
    if receipt is None or receipt.get("briefDigest") != attempt["briefDigest"]:
        raise ContractIssue("E_ORCHESTRATION_RECEIPT", "/resultId",
                            "batch accounting requires the exact digest-only batch receipt")
    limits = attempt["limits"]
    mapping = {
        "modelCalls": "maxIterations", "toolCalls": "maxToolCalls",
        "elapsedMs": "maxWallMs", "inputBytes": "maxInputBytes", "outputBytes": "maxOutputBytes",
    }
    if any(usage[field] > limits[limit] for field, limit in mapping.items()):
        raise ContractIssue("E_ORCHESTRATION_LIMIT", "/usage", "observed attempt exceeded its approved bound")
    existing = [event for event in revision["events"] if isinstance(event, dict)
                and event.get("schemaVersion") == 2
                and event["type"] == "BATCH_ATTEMPT_ACCOUNTED"
                and event["payload"]["batchId"] == batch_id]
    existing = [event for event in existing if event["payload"]["batchDigest"] == batch_digest_value]
    if any(event["attemptId"] == attempt_id for event in existing):
        raise ContractIssue("E_ORCHESTRATION_DUPLICATE", "/attemptId",
                            "attempt accounting already exists")
    totals = {field: usage[field] for field in usage}
    for event in existing:
        for field in totals:
            totals[field] += event["payload"][field]
    batch_limits = {
        "modelCalls": "maxCalls", "toolCalls": "maxToolCalls", "elapsedMs": "maxWallMs",
        "inputBytes": "maxInputBytes", "outputBytes": "maxOutputBytes",
    }
    if any(totals[field] > approval["limits"][limit] for field, limit in batch_limits.items()):
        raise ContractIssue("E_ORCHESTRATION_LIMIT", "/usage", "observed cumulative batch bound exceeded")
    projected = manager._projection(revision, allow_controller=True)["tasks"][task_id]
    if (
        projected["status"] != "reported" or projected["attemptId"] != attempt_id
        or projected["resultId"] != result_id
    ):
        raise ContractIssue("E_ORCHESTRATION_RECEIPT", "/resultId",
                            "accounting requires the matching reported manager receipt")
    manager._append_controller(record, revision, "BATCH_ATTEMPT_ACCOUNTED", task_id, attempt_id, {
        "batchId": batch_id, "batchDigest": batch_digest_value, "resultId": result_id,
        "briefDigest": attempt["briefDigest"], **usage,
    })
    return {"batchId": batch_id, "attemptId": attempt_id, "usage": usage}
