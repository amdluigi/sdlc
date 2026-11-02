"""Pure, bounded replay for explicitly managed manual executions."""

import hashlib
import json

from artifact_contracts import ContractIssue
import execution_contracts as contracts


def digest(value):
    return "sha256:" + hashlib.sha256(contracts._encoded(value).encode("utf-8")).hexdigest()


def context_digest(value):
    material = {key: value[key] for key in ("schemaVersion", "revision", "shared", "agents")}
    return digest(material)


def empty_context():
    context = {"schemaVersion": 1, "revision": 0, "shared": None, "agents": {}}
    return {**context, "digest": context_digest(context)}


def _context_entry(value, pointer, role, plan_revision):
    entry = contracts._object(value, pointer, (
        "content", "source", "author", "agent", "updatedAt", "planRevision", "digest",
    ))
    contracts._text(entry["content"], pointer + "/content", 2048)
    contracts._enum(entry["source"], pointer + "/source", ("operator", "worker"))
    contracts._text(entry["author"], pointer + "/author", 128)
    if role is None:
        if entry["agent"] is not None or entry["source"] != "operator" or entry["author"] != "operator":
            raise ContractIssue("E_EXECUTION_CONTEXT", pointer, "shared context must be operator-authored")
    else:
        contracts._id(role, pointer + "/agent")
        if entry["agent"] != role or (entry["source"] == "worker" and entry["author"] != role):
            raise ContractIssue("E_EXECUTION_CONTEXT", pointer, "agent context attribution is inconsistent")
        if entry["source"] == "operator" and entry["author"] != "operator":
            raise ContractIssue("E_EXECUTION_CONTEXT", pointer, "operator context attribution is inconsistent")
    contracts._time(entry["updatedAt"], pointer + "/updatedAt")
    contracts._number(entry["planRevision"], pointer + "/planRevision")
    if entry["planRevision"] > plan_revision:
        raise ContractIssue("E_EXECUTION_CONTEXT", pointer + "/planRevision",
                            "context cannot reference a future plan revision")
    contracts._digest(entry["digest"], pointer + "/digest")
    if entry["digest"] != digest(entry["content"]):
        raise ContractIssue("E_EXECUTION_CONTEXT", pointer + "/digest", "context content digest changed")
    return entry


def validate_context(value, plan_revision):
    context = contracts._object(json.loads(contracts._encoded(value)), "/context", (
        "schemaVersion", "revision", "shared", "agents", "digest",
    ))
    if type(context["schemaVersion"]) is not int or context["schemaVersion"] != 1:
        raise ContractIssue("E_EXECUTION_VERSION", "/context/schemaVersion",
                            "only context schema version 1 is supported")
    contracts._number(context["revision"], "/context/revision", 0)
    if context["shared"] is not None:
        context["shared"] = _context_entry(context["shared"], "/context/shared", None, plan_revision)
    agents = _mapping(context["agents"], "/context/agents")
    context["agents"] = {
        role: _context_entry(entry, "/context/agents/" + role, role, plan_revision)
        for role, entry in agents.items()
    }
    contracts._digest(context["digest"], "/context/digest")
    if context["digest"] != context_digest(context):
        raise ContractIssue("E_EXECUTION_CONTEXT", "/context/digest", "context snapshot digest changed")
    return json.loads(contracts._encoded(context))


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


def validate_acceptance(value, *, allow_independent=True):
    if isinstance(value, dict) and value.get("schemaVersion") == 2 and type(value["schemaVersion"]) is int:
        if not allow_independent:
            raise ContractIssue("E_EXECUTION_VERSION", "/schemaVersion",
                                "independent validation acceptance requires a version-3 record")
        data = contracts._object(value, "", (
            "schemaVersion", "taskId", "attemptId", "resultId", "resultDigest", "acceptanceCriteria",
            "revision", "command", "summary",
        ))
        contracts._digest(data["resultDigest"], "/resultDigest")
    else:
        if isinstance(value, dict) and "schemaVersion" in value:
            contracts._version(value)
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


def _accepted_evidence(plan_task, result, acceptance, receipt=None):
    _transition(result["status"] == "completed")
    if result["blockers"] or set(acceptance["acceptanceCriteria"]) != set(plan_task["acceptanceCriteria"]):
        raise ContractIssue("E_EXECUTION_EVIDENCE", "/acceptanceCriteria",
                            "acceptance requires complete criteria and no reported blockers")
    verification = result["verification"]
    covered = [entry["acceptanceCriterion"] for entry in verification]
    if len(set(covered)) != len(covered) or set(covered) != set(plan_task["acceptanceCriteria"]):
        raise ContractIssue("E_EXECUTION_EVIDENCE", "/verification",
                            "verification must cover every criterion exactly once")
    if acceptance["schemaVersion"] == 2:
        # Batch receipts structurally cannot carry worker command provenance, so the operator's
        # independently supplied validation is the evidence; worker statuses are never treated as passed.
        if receipt is None or set(receipt) != {"briefDigest", "resultScope", "result"}:
            raise ContractIssue("E_EXECUTION_EVIDENCE", "/schemaVersion",
                                "independent validation acceptance applies only to bounded batch receipts")
        if any(entry["result"] == "failed" for entry in verification):
            raise ContractIssue("E_EXECUTION_EVIDENCE", "/verification",
                                "a worker-reported verification failure requires a new attempt")
        if acceptance["resultDigest"] != digest(result):
            raise ContractIssue("E_EXECUTION_EVIDENCE", "/resultDigest",
                                "independent validation must bind the exact recorded result")
        return
    if any(entry["result"] != "passed" or entry["revision"] != acceptance["revision"]
           or entry["command"] is None for entry in verification):
        raise ContractIssue("E_EXECUTION_EVIDENCE", "/verification",
                            "verification must pass at the independently checked revision with declared commands")


def _validate_receipt_result(receipt, plan, *, allow_controller):
    if not isinstance(receipt, dict):
        raise ContractIssue("E_EXECUTION_RECEIPT", "/receipts", "receipt must be an object")
    if set(receipt) == {"brief", "result"}:
        return contracts.validate_task_result(receipt["result"], plan, receipt["brief"])["data"]
    if not allow_controller or set(receipt) != {"briefDigest", "resultScope", "result"}:
        raise ContractIssue("E_EXECUTION_RECEIPT", "/receipts", "unsupported receipt representation")
    contracts._digest(receipt["briefDigest"], "/receipts/briefDigest")
    scope = contracts._object(receipt["resultScope"], "/receipts/resultScope", (
        "allowedActions", "ownership", "acceptanceCriteria",
    ))
    base_fields = (
        "schemaVersion", "binding", "taskId", "attemptId", "status",
        "artifacts", "verification", "findings", "blockers",
    )
    result_value = receipt["result"]
    fields = base_fields + (("contextUpdate",) if isinstance(result_value, dict)
                            and result_value.get("schemaVersion") == 2 else ())
    result = contracts._object(result_value, "/receipts/result", fields)
    task_id = contracts._id(result["taskId"], "/receipts/result/taskId")
    attempt_id = contracts._id(result["attemptId"], "/receipts/result/attemptId")
    brief = {
        "schemaVersion": 1,
        "binding": {"executionId": plan["executionId"], "planRevision": plan["revision"],
                    "planDigest": digest(plan)},
        "taskId": task_id, "attemptId": attempt_id,
        "allowedActions": scope["allowedActions"], "ownership": scope["ownership"],
        "guidance": [], "acceptanceCriteria": scope["acceptanceCriteria"],
        "verification": "Persisted batch result scope; full brief is not retained.",
    }
    return contracts.validate_task_result(receipt["result"], plan, brief)["data"]


def _replay_execution(plan, events, receipts=None, policy_digest=None, acceptances=None, approvals=None,
                      *, allow_controller=False, allow_autonomous=False):
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
    accounted_attempts = set()
    autonomous_starts = {}
    started_autonomous = {}
    for position, raw in enumerate(events):
        if isinstance(raw, dict) and raw.get("schemaVersion") in (2, 3):
            event_version = raw.get("schemaVersion")
            if event_version == 2 and not allow_controller or event_version == 3 and not allow_autonomous:
                raise ContractIssue("E_EXECUTION_VERSION", "/schemaVersion",
                                    "version-1 replay does not accept controller events")
            event = contracts.validate_controller_event(raw, plan)["data"]
            kind, event_id = event["type"], event["eventId"]
            _transition(event["sequence"] == position + 1 and event_id not in event_ids, "/sequence")
            if state["lastRecordedAt"] is not None:
                _transition(event["recordedAt"] >= state["lastRecordedAt"], "/recordedAt")
            _transition(event["occurredAt"] == event["recordedAt"], "/occurredAt")
            event_ids.add(event_id)
            task_id, attempt = event["taskId"], event["attemptId"]
            current = state["tasks"].get(task_id)
            payload = event["payload"]
            if kind == "AUTONOMOUS_ATTEMPT_STARTED":
                identity = (task_id, attempt)
                _transition(state["approved"] and current is not None
                            and current["status"] in ("waiting", "ready")
                            and identity not in autonomous_starts
                            and attempt not in state["attemptIds"], "/attemptId")
                if current["status"] == "ready":
                    _transition(current.get("pendingAttemptId") == attempt, "/attemptId")
                _transition(not any(item["status"] in ("running", "blocked")
                                    for item in state["tasks"].values()), "/taskId")
                _transition(all(state["tasks"][parent]["status"] == "accepted"
                                for parent in plans[task_id]["prerequisites"]), "/taskId")
                autonomous_starts[identity] = payload
            elif kind == "BATCH_ATTEMPT_ACCOUNTED":
                start = started_autonomous.get((task_id, attempt))
                if start is not None and (
                    start["batchId"] != payload["batchId"]
                    or start["batchDigest"] != payload["batchDigest"]
                    or start["briefDigest"] != payload["briefDigest"]
                ):
                    raise ContractIssue("E_EXECUTION_RECEIPT", "/payload",
                                        "accounting differs from the autonomous start binding")
                accounting_key = (
                    payload["batchId"], payload["batchDigest"], task_id, attempt, payload["resultId"]
                )
                _transition(current is not None and current["status"] == "reported"
                            and current["attemptId"] == attempt
                            and current["resultId"] == payload["resultId"]
                            and accounting_key not in accounted_attempts, "/payload/resultId")
                receipt = receipts.get(payload["resultId"])
                if receipt is None or receipt["result"]["taskId"] != task_id or (
                    receipt["result"]["attemptId"] != attempt
                ) or (
                    receipt.get("briefDigest", digest(receipt.get("brief")))
                    != payload["briefDigest"]
                ):
                    raise ContractIssue("E_EXECUTION_RECEIPT", "/payload/resultId",
                                        "accounting requires the matching complete manager receipt")
                accounted_attempts.add(accounting_key)
            elif kind == "TASK_RETRY_READY":
                accounting_key = (
                    payload["batchId"], payload["batchDigest"], task_id, attempt, payload["resultId"]
                )
                _transition(current is not None and current["status"] == "reported"
                            and current["reportedStatus"] == "failed"
                            and current["attemptId"] == attempt
                            and current["resultId"] == payload["resultId"]
                            and accounting_key in accounted_attempts, "/payload/resultId")
                receipt = receipts.get(payload["resultId"])
                if receipt is None or receipt["result"]["status"] != "failed" or (
                    receipt["result"]["taskId"], receipt["result"]["attemptId"]
                ) != (task_id, attempt):
                    raise ContractIssue("E_EXECUTION_RETRY", "/payload/resultId",
                                        "retry requires the matching complete failed receipt")
                _transition(payload["nextAttemptId"] not in state["attemptIds"]
                            and payload["nextAttemptId"] != attempt, "/payload/nextAttemptId")
                current.update(
                    status="ready", attemptId=None, resultId=None, reportedStatus=None,
                    startedAt=None, endedAt=None, blockedFrom=None,
                )
                current["pendingAttemptId"] = payload["nextAttemptId"]
            else:
                _transition(False)
            state.update(sequence=event["sequence"], lastRecordedAt=event["recordedAt"])
            continue
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
                pending = current.get("pendingAttemptId")
                _transition(status == "ready" and attempt not in state["attemptIds"]
                            and (pending is None or attempt == pending))
                autonomous_marker = autonomous_starts.pop((task_id, attempt), None)
                autonomous = autonomous_marker is not None
                if any(item["status"] in ("running", "blocked") or (
                    not autonomous and item["status"] == "reported"
                ) for item in state["tasks"].values()):
                    raise ContractIssue("E_EXECUTION_CONFLICT", "/taskId",
                                        "manual attempts are serialized; resolve the active attempt first")
                if autonomous:
                    _transition(all(state["tasks"][parent]["status"] == "accepted"
                                    for parent in plans[task_id]["prerequisites"]), "/taskId")
                    started_autonomous[(task_id, attempt)] = autonomous_marker
                state["attemptIds"].append(attempt)
                current.update(status="running", attemptId=attempt, startedAt=event["recordedAt"])
                current.pop("pendingAttemptId", None)
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
                receipt = receipts.get(result_id)
                result = _validate_receipt_result(receipt, plan, allow_controller=allow_controller)
                _transition(result["taskId"] == task_id and result["attemptId"] == attempt)
                used_receipts.add(result_id)
                current.update(status="reported", resultId=result_id, reportedStatus=result["status"],
                               endedAt=event["recordedAt"])
            elif kind == "VALIDATION_PASSED":
                _transition(status == "reported" and attempt == current["attemptId"])
                acceptance = validate_acceptance(acceptances.get(event_id), allow_independent=allow_autonomous)
                _transition(acceptance["taskId"] == task_id and acceptance["attemptId"] == attempt
                            and acceptance["resultId"] == current["resultId"]
                            and set(payload["acceptanceCriteria"]) == set(acceptance["acceptanceCriteria"]))
                receipt = receipts[current["resultId"]]
                _accepted_evidence(plans[task_id], receipt["result"], acceptance, receipt)
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
    _transition(not autonomous_starts, "/events")
    _transition(set(acceptances) == used_acceptances, "/acceptances")
    _transition(set(approvals) == used_approvals, "/approvals")
    return json.loads(contracts._encoded(state))


def replay_execution(plan, events, receipts=None, policy_digest=None, acceptances=None, approvals=None):
    return _replay_execution(plan, events, receipts, policy_digest, acceptances, approvals)


def replay_execution_v2(plan, events, receipts=None, policy_digest=None, acceptances=None, approvals=None):
    return _replay_execution(plan, events, receipts, policy_digest, acceptances, approvals,
                             allow_controller=True)

def replay_execution_v3(plan, events, receipts=None, policy_digest=None, acceptances=None, approvals=None):
    return _replay_execution(plan, events, receipts, policy_digest, acceptances, approvals,
                             allow_controller=True, allow_autonomous=True)


def replay_record_revision(record_version, revision):
    """Replay one stored revision with the semantics its validated record version permits."""
    replay = replay_execution_v3 if record_version >= 3 else (
        replay_execution_v2 if record_version == 2 else replay_execution
    )
    return replay(revision["plan"], revision["events"], revision["receipts"], digest(revision["consent"]),
                  revision["acceptances"], revision["approvals"])


ACCEPTANCE_BASES = {1: "worker-verification-with-operator-judgment", 2: "independent-operator-validation"}


def acceptance_basis(task_state):
    """Provenance of a recorded acceptance; None unless the task is accepted."""
    if task_state["status"] != "accepted":
        return None
    return ACCEPTANCE_BASES[task_state["acceptance"]["schemaVersion"]]


def validate_record(value):
    if not isinstance(value, dict):
        raise ContractIssue("E_SCHEMA_TYPE", "/", "expected an object")
    version = value.get("schemaVersion")
    record_fields = ("schemaVersion", "executionId", "revisions") + (("context",) if version == 4 else ())
    record = contracts._object(value, "", record_fields)
    if type(record["schemaVersion"]) is not int or record["schemaVersion"] not in (1, 2, 3, 4):
        raise ContractIssue("E_EXECUTION_VERSION", "/schemaVersion", "unsupported execution record version")
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
        state = replay_record_revision(record["schemaVersion"], {**revision, "plan": plan, "consent": consent})
        if record["schemaVersion"] < 4 and any(
            isinstance(receipt, dict) and isinstance(receipt.get("result"), dict)
            and receipt["result"].get("schemaVersion") == 2
            for receipt in revision["receipts"].values()
        ):
            raise ContractIssue("E_EXECUTION_VERSION", "/revisions/receipts",
                                "version-2 task results require execution record version 4")
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
    if record["schemaVersion"] == 4:
        record["context"] = validate_context(record["context"], previous)
    return json.loads(contracts._encoded(record))
