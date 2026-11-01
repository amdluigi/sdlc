"""Pure, bounded replay for explicitly managed manual executions."""

import hashlib
import json

from artifact_contracts import ContractIssue
import execution_contracts as contracts


def digest(value):
    return "sha256:" + hashlib.sha256(contracts._encoded(value).encode("utf-8")).hexdigest()


def validate_policy(value):
    data = contracts._object(value, "", (
        "schemaVersion", "enabled", "mode", "retention", "detailedTelemetry",
    ))
    contracts._version(data)
    if type(data["enabled"]) is not bool or type(data["detailedTelemetry"]) is not bool:
        raise ContractIssue("E_SCHEMA_TYPE", "/", "policy flags must be booleans")
    contracts._enum(data["mode"], "/mode", ("manual",))
    contracts._enum(data["retention"], "/retention", ("manual",))
    if data["detailedTelemetry"]:
        raise ContractIssue("E_EXECUTION_POLICY", "/detailedTelemetry",
                            "detailed telemetry is not supported by manual execution")
    return json.loads(contracts._encoded(data))


def validate_consent(value):
    data = contracts._object(value, "", ("schemaVersion", "generation", "policy"))
    contracts._version(data)
    contracts._number(data["generation"], "/generation")
    validate_policy(data["policy"])
    return json.loads(contracts._encoded(data))


def validate_acceptance(value):
    data = contracts._object(value, "", (
        "schemaVersion", "taskId", "attemptId", "resultId", "acceptanceCriteria",
        "revision", "command", "summary",
    ))
    contracts._version(data)
    for field in ("taskId", "attemptId", "resultId"):
        contracts._id(data[field], "/" + field)
    contracts._refs(data["acceptanceCriteria"], "/acceptanceCriteria", True)
    for field in ("revision", "command", "summary"):
        contracts._text(data[field], "/" + field)
    return json.loads(contracts._encoded(data))


def initial_execution_state(plan):
    validated = contracts.validate_execution_plan(plan)["data"]
    return {
        "schemaVersion": 1,
        "executionId": validated["executionId"],
        "planRevision": validated["revision"],
        "planDigest": digest(validated),
        "policyDigest": None,
        "approved": False,
        "sequence": 0,
        "lastRecordedAt": None,
        "attemptIds": [],
        "tasks": {
            item["id"]: {
                "status": "waiting", "attemptId": None, "resultId": None,
                "reportedStatus": None, "startedAt": None, "endedAt": None,
                "blockedFrom": None, "acceptance": None,
            }
            for item in validated["tasks"]
        },
    }


def _transition(condition, pointer="/type"):
    if not condition:
        raise ContractIssue("E_EXECUTION_TRANSITION", pointer,
                            "event is not permitted in the current execution state")


def _mapping(value, pointer):
    if not isinstance(value, dict):
        raise ContractIssue("E_SCHEMA_TYPE", pointer, "expected a keyed object")
    if len(value) > contracts.MAX_ITEMS:
        raise ContractIssue("E_EXECUTION_LIMIT", pointer, "too many records")
    for key in value:
        contracts._id(key, pointer)
    return value


def _accepted_evidence(plan_task, result, acceptance):
    _transition(result["status"] == "completed")
    if result["blockers"] or set(acceptance["acceptanceCriteria"]) != set(plan_task["acceptanceCriteria"]):
        raise ContractIssue("E_EXECUTION_EVIDENCE", "/acceptanceCriteria",
                            "acceptance requires complete criteria and no reported blockers")
    verification = result["verification"]
    covered = [entry["acceptanceCriterion"] for entry in verification]
    if len(set(covered)) != len(covered) or set(covered) != set(plan_task["acceptanceCriteria"]):
        raise ContractIssue("E_EXECUTION_EVIDENCE", "/verification",
                            "verification must cover every criterion exactly once")
    if any(entry["result"] != "passed" or entry["revision"] != acceptance["revision"]
           or entry["command"] is None for entry in verification):
        raise ContractIssue("E_EXECUTION_EVIDENCE", "/verification",
                            "verification must pass at the independently checked revision with declared commands")


def replay_execution(plan, events, receipts=None, policy_digest=None, acceptances=None, approvals=None):
    """Replay declarations and explicit manager records, never authenticating a caller."""
    state = initial_execution_state(plan)
    plans = {item["id"]: item for item in plan["tasks"]}
    if policy_digest is not None:
        contracts._digest(policy_digest, "/policyDigest")
    state["policyDigest"] = policy_digest
    events = contracts._array(events, "/events")
    receipts = _mapping({} if receipts is None else receipts, "/receipts")
    acceptances = _mapping({} if acceptances is None else acceptances, "/acceptances")
    approvals = _mapping({} if approvals is None else approvals, "/approvals")
    used_receipts, used_acceptances, used_approvals, event_ids = set(), set(), set(), set()
    for position, raw in enumerate(events):
        event = contracts.validate_execution_event(raw, plan)["data"]
        kind, event_id = event["type"], event["eventId"]
        _transition(event["sequence"] == position + 1 and event_id not in event_ids, "/sequence")
        if state["lastRecordedAt"] is not None:
            _transition(event["recordedAt"] >= state["lastRecordedAt"], "/recordedAt")
        _transition(event["occurredAt"] == event["recordedAt"], "/occurredAt")
        event_ids.add(event_id)
        task_id, attempt = event["taskId"], event["attemptId"]
        current = state["tasks"].get(task_id)
        payload = event["payload"]
        expected_actor = (
            {"role": "user", "id": "operator"}
            if kind in ("PLAN_APPROVED", "VALIDATION_PASSED", "VALIDATION_FAILED", "TASK_CANCELLED")
            else {"role": "manager", "id": "local-manager"}
        )
        if event["actor"] != expected_actor:
            raise ContractIssue("E_EXECUTION_ACTOR", "/actor", "event is outside the manual manager boundary")
        if position == 0:
            _transition(kind in ("PLAN_PROPOSED", "PLAN_UPDATED"))
        elif kind in ("PLAN_PROPOSED", "PLAN_UPDATED"):
            _transition(False)
        if kind == "PLAN_APPROVED":
            _transition(not state["approved"] and all(
                item["status"] == "waiting" for item in state["tasks"].values()
            ))
            decision = contracts._object(approvals.get(event_id), "/approvals", ("planDigest", "policyDigest"))
            if decision != {"planDigest": state["planDigest"], "policyDigest": policy_digest} or policy_digest is None:
                raise ContractIssue("E_EXECUTION_APPROVAL", "/approvals", "approval binding is missing or stale")
            _transition(payload["decisionId"] == event_id)
            used_approvals.add(event_id)
            state["approved"] = True
        elif kind in ("PLAN_PROPOSED", "PLAN_UPDATED"):
            pass
        elif current is None:
            _transition(False)
        else:
            if kind not in ("TASK_CANCELLED",):
                if not state["approved"]:
                    raise ContractIssue("E_EXECUTION_APPROVAL", "/type", "plan approval is required")
            status = current["status"]
            if kind == "TASK_READY":
                _transition(status == "waiting" and all(
                    state["tasks"][parent]["status"] == "accepted"
                    for parent in plans[task_id]["prerequisites"]
                ))
                current["status"] = "ready"
            elif kind == "TASK_STARTED":
                _transition(status == "ready" and attempt not in state["attemptIds"])
                if any(item["attemptId"] is not None and item["status"] in ("running", "blocked", "reported")
                       for item in state["tasks"].values()):
                    raise ContractIssue("E_EXECUTION_CONFLICT", "/taskId",
                                        "manual attempts are serialized; resolve the active attempt first")
                state["attemptIds"].append(attempt)
                current.update(status="running", attemptId=attempt, startedAt=event["recordedAt"])
            elif kind == "TASK_PROGRESS_UPDATED":
                _transition(status == "running" and attempt == current["attemptId"])
            elif kind == "TASK_BLOCKED":
                _transition(status in ("waiting", "ready", "running"))
                current.update(status="blocked", blockedFrom=status)
            elif kind == "TASK_UNBLOCKED":
                _transition(status == "blocked")
                current.update(status=current["blockedFrom"], blockedFrom=None)
            elif kind == "TASK_RESULT_RECEIVED":
                _transition(status == "running" and attempt == current["attemptId"])
                result_id = payload["resultId"]
                _transition(result_id not in used_receipts)
                receipt = contracts._object(receipts.get(result_id), "/receipts", ("brief", "result"))
                result = contracts.validate_task_result(receipt["result"], plan, receipt["brief"])["data"]
                _transition(result["taskId"] == task_id and result["attemptId"] == attempt)
                used_receipts.add(result_id)
                current.update(status="reported", resultId=result_id, reportedStatus=result["status"],
                               endedAt=event["recordedAt"])
            elif kind == "VALIDATION_PASSED":
                _transition(status == "reported" and attempt == current["attemptId"])
                acceptance = validate_acceptance(acceptances.get(event_id))
                _transition(acceptance["taskId"] == task_id and acceptance["attemptId"] == attempt
                            and acceptance["resultId"] == current["resultId"]
                            and set(payload["acceptanceCriteria"]) == set(acceptance["acceptanceCriteria"]))
                _accepted_evidence(plans[task_id], receipts[current["resultId"]]["result"], acceptance)
                used_acceptances.add(event_id)
                current.update(status="accepted", acceptance=acceptance)
            elif kind == "VALIDATION_FAILED":
                _transition(status == "reported" and attempt == current["attemptId"])
                current["status"] = "failed"
            elif kind == "TASK_COMPLETED":
                _transition(status == "reported" and attempt == current["attemptId"]
                            and current["reportedStatus"] == "completed")
            elif kind == "TASK_FAILED":
                _transition(status in ("running", "blocked", "reported") and attempt == current["attemptId"])
                current.update(status="failed", endedAt=event["recordedAt"], blockedFrom=None)
            elif kind == "TASK_CANCELLED":
                _transition(status not in ("accepted", "failed", "cancelled"))
                current.update(status="cancelled", endedAt=event["recordedAt"], blockedFrom=None)
            else:
                _transition(False)
        state.update(sequence=event["sequence"], lastRecordedAt=event["recordedAt"])
    _transition(set(receipts) == used_receipts, "/receipts")
    _transition(set(acceptances) == used_acceptances, "/acceptances")
    _transition(set(approvals) == used_approvals, "/approvals")
    return json.loads(contracts._encoded(state))


def validate_record(value):
    record = contracts._object(value, "", ("schemaVersion", "executionId", "revisions"))
    contracts._version(record)
    contracts._id(record["executionId"], "/executionId")
    revisions = contracts._array(record["revisions"], "/revisions", True)
    previous, attempts, receipt_ids = 0, set(), set()
    for raw in revisions:
        revision = contracts._object(raw, "/revisions", (
            "plan", "consent", "events", "receipts", "acceptances", "approvals",
        ))
        plan = contracts.validate_execution_plan(revision["plan"])["data"]
        consent = validate_consent(revision["consent"])
        _transition(consent["policy"]["enabled"], "/consent")
        _transition(plan["executionId"] == record["executionId"] and plan["revision"] > previous, "/revision")
        state = replay_execution(
            plan, revision["events"], revision["receipts"], digest(consent),
            revision["acceptances"], revision["approvals"],
        )
        _transition(bool(revision["events"]), "/events")
        first = revision["events"][0]
        _transition(first["type"] == ("PLAN_PROPOSED" if previous == 0 else "PLAN_UPDATED"))
        if previous:
            _transition(first["payload"]["previousRevision"] == previous)
        _transition(not attempts.intersection(state["attemptIds"]), "/attemptIds")
        _transition(not receipt_ids.intersection(revision["receipts"]), "/receipts")
        if raw is not revisions[-1]:
            _transition(not any(item["status"] in ("running", "blocked", "reported")
                                for item in state["tasks"].values()), "/revisions")
        attempts.update(state["attemptIds"])
        receipt_ids.update(revision["receipts"])
        previous = plan["revision"]
    return json.loads(contracts._encoded(record))
