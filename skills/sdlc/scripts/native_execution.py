"""Digest-bound native delegation bookkeeping; the active host invokes workers."""

import json
import stat

from artifact_contracts import ContractIssue, semantic_fields
import execution_contracts as contracts
import execution_manager as manager
import execution_profiles as profiles
import execution_state as state

REQUEST_MARKER = "native-request:"
RECEIPT_MARKER = "native-receipt:"


def _host(value):
    host = contracts._object(value, "/host", ("id", "build", "delegationTool", "allowedActions"))
    contracts._id(host["id"], "/host/id")
    for field in ("build", "delegationTool"):
        contracts._text(host[field], "/host/" + field, 128)
    actions = contracts._strings(host["allowedActions"], "/host/allowedActions", True)
    for action in actions:
        contracts._enum(action, "/host/allowedActions", ("read", "search", "edit", "execute"))
    return host


def _request(value):
    request = contracts._object(value, "", (
        "schemaVersion", "projectRoot", "binding", "policyDigest", "role", "profileDigest", "host", "brief", "outcome",
    ))
    contracts._version(request)
    binding = contracts._object(request["binding"], "/binding", ("executionId", "planRevision", "planDigest"))
    contracts._id(binding["executionId"], "/binding/executionId")
    contracts._number(binding["planRevision"], "/binding/planRevision")
    contracts._digest(binding["planDigest"], "/binding/planDigest")
    supplied = contracts._object(request["brief"], "/brief", (
        "schemaVersion", "binding", "taskId", "attemptId", "allowedActions",
        "ownership", "guidance", "acceptanceCriteria", "verification",
    ))
    contracts._version(supplied)
    if supplied["binding"] != binding:
        raise ContractIssue("E_NATIVE_BINDING", "/binding", "request binding differs from its brief")
    for field in ("taskId", "attemptId"):
        contracts._id(supplied[field], "/brief/" + field)
    contracts._text(request["projectRoot"], "/projectRoot", 2048)
    for field in ("policyDigest", "profileDigest"):
        contracts._digest(request[field], "/" + field)
    contracts._enum(request["role"], "/role", ("architecture", "developer", "testing", "review"))
    _host(request["host"])
    contracts._text(request["outcome"], "/outcome")
    return json.loads(contracts._encoded(request))


def _validate(root, request, revision, *, check_guidance=True):
    request = _request(request)
    if request["projectRoot"] != str(root) or request["policyDigest"] != state.digest(revision["consent"]):
        raise ContractIssue("E_NATIVE_APPROVAL", "/", "request root or consent binding changed")
    brief = contracts.validate_task_brief(request["brief"], revision["plan"])["data"]
    if request["binding"] != brief["binding"]:
        raise ContractIssue("E_NATIVE_BINDING", "/binding", "request binding differs from its brief")
    task = next(item for item in revision["plan"]["tasks"] if item["id"] == brief["taskId"])
    info = profiles.inspect_profile(root, request["role"])
    accepted_names = {request["role"], "sdlc-" + request["role"], info["name"].casefold()}
    if task["assignment"]["agent"].casefold() not in accepted_names:
        raise ContractIssue("E_NATIVE_ROLE", "/role", "role does not match the approved task assignment")
    if request["profileDigest"] != info["digest"] or request["outcome"] != task["outcome"]:
        raise ContractIssue("E_NATIVE_APPROVAL", "/", "profile or planned outcome changed")
    if not set(brief["allowedActions"]) <= set(info["allowedActions"]):
        raise ContractIssue("E_NATIVE_ROLE", "/brief/allowedActions", "brief escalates the role's actions")
    if not set(brief["allowedActions"]) <= set(request["host"]["allowedActions"]):
        raise ContractIssue("E_NATIVE_CAPABILITY", "/host", "observed native host lacks required actions")
    if task["assignment"]["model"] is not None or task["assignment"]["modelProfile"] != "host-default":
        raise ContractIssue("E_NATIVE_CAPABILITY", "/assignment", "effective explicit model routing is not qualified")
    manager._ownership(root, revision["plan"], brief["taskId"])
    for claim in brief["ownership"]:
        claim = claim.casefold()
        if claim.split("/")[0] in (".git", ".sdlc") or claim.startswith(".github/agents/"):
            raise ContractIssue("E_NATIVE_SCOPE", "/ownership", "worker cannot own execution or profile controls")
    if check_guidance:
        for relative in brief["guidance"]:
            path = manager._safe(root, root.joinpath(*relative.split("/")))
            if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
                raise ContractIssue("E_NATIVE_GUIDANCE", "/guidance", "guidance must name existing regular project files")
    if not manager._projection(revision)["approved"]:
        raise ContractIssue("E_NATIVE_APPROVAL", "/", "current immutable plan must be explicitly approved")
    return request


def prepare_request(project_root, execution_id, brief, role, host):
    root = manager._root(project_root)
    manager._consent(root, enabled=True)
    record = manager._load(root, execution_id)
    revision = record["revisions"][-1]
    if manager._consent(root, enabled=True) != revision["consent"]:
        raise ContractIssue("E_NATIVE_APPROVAL", "/", "current consent differs from approved plan")
    supplied = contracts.validate_task_brief(brief, revision["plan"])["data"]
    task = next(item for item in revision["plan"]["tasks"] if item["id"] == supplied["taskId"])
    info = profiles.inspect_profile(root, role)
    request = {
        "schemaVersion": 1, "projectRoot": str(root), "binding": supplied["binding"],
        "policyDigest": state.digest(revision["consent"]), "role": role, "profileDigest": info["digest"],
        "host": host, "brief": supplied, "outcome": task["outcome"],
    }
    return _validate(root, request, revision)


def request_digest(request):
    """Compute a request digest without approving or starting work."""
    return {**semantic_fields(), "requestDigest": state.digest(_request(request))}


def start_request(project_root, request, approved_request_digest):
    request = _request(request)
    contracts._digest(approved_request_digest, "/approvedRequestDigest")
    if state.digest(request) != approved_request_digest:
        raise ContractIssue("E_NATIVE_APPROVAL", "/", "separate explicit native request digest approval is required")
    execution_id = request["binding"]["executionId"]
    with manager._transaction(project_root, execution_id, require_binding=False) as (root, _, revision):
        if manager._consent(root, enabled=True) != revision["consent"]:
            raise ContractIssue("E_NATIVE_APPROVAL", "/", "consent changed after request preparation")
        _validate(root, request, revision)
        brief = request["brief"]
        manager._project_attempt_available(root, execution_id)
        projected = manager._projection(revision)["tasks"][brief["taskId"]]
        if projected["status"] == "waiting":
            manager._append(revision, "TASK_READY", brief["taskId"])
        manager._append(revision, "TASK_STARTED", brief["taskId"], brief["attemptId"])
        manager._append(revision, "TASK_PROGRESS_UPDATED", brief["taskId"], brief["attemptId"],
                        {"message": REQUEST_MARKER + approved_request_digest})
    return {**semantic_fields(), "requestDigest": approved_request_digest, "hostInvocation": "required",
            "modelObservation": "unavailable", "cancellation": "unqualified"}


def _receipt(value):
    receipt = contracts._object(value, "", (
        "schemaVersion", "requestDigest", "hostId", "hostBuild", "callId", "result",
    ))
    contracts._version(receipt)
    contracts._digest(receipt["requestDigest"], "/requestDigest")
    contracts._id(receipt["hostId"], "/hostId")
    contracts._text(receipt["hostBuild"], "/hostBuild", 128)
    contracts._text(receipt["callId"], "/callId", 256)
    return json.loads(contracts._encoded(receipt))


def _request_markers(events, task_id, attempt_id):
    return [event["payload"]["message"][len(REQUEST_MARKER):]
            for previous, event in zip(events, events[1:])
            if previous["type"] == "TASK_STARTED" and event["type"] == "TASK_PROGRESS_UPDATED"
            and (previous["taskId"], previous["attemptId"]) == (task_id, attempt_id)
            and (event["taskId"], event["attemptId"]) == (task_id, attempt_id)
            and event["payload"]["message"].startswith(REQUEST_MARKER)
            and contracts.DIGEST_PATTERN.fullmatch(event["payload"]["message"][len(REQUEST_MARKER):])]


def _metadata(record):
    for revision in record["revisions"]:
        for index, event in enumerate(revision["events"]):
            message = event["payload"].get("message", "")
            if event["type"] == "TASK_PROGRESS_UPDATED" and message.startswith(RECEIPT_MARKER):
                following = revision["events"][index + 1] if index + 1 < len(revision["events"]) else None
                if following is None or following["type"] != "TASK_RESULT_RECEIVED" or (
                    following["taskId"], following["attemptId"]
                ) != (event["taskId"], event["attemptId"]):
                    continue
                requests = _request_markers(revision["events"][:index], event["taskId"], event["attemptId"])
                if not requests:
                    continue
                if len(requests) != 1:
                    raise ContractIssue("E_NATIVE_HISTORY", "/", "attribution has no unique native request")
                try:
                    value = json.loads(message[len(RECEIPT_MARKER):])
                except (ValueError, RecursionError) as error:
                    raise ContractIssue("E_NATIVE_HISTORY", "/", "invalid native attribution marker") from error
                data = contracts._object(value, "/attribution", (
                    "requestDigest", "hostId", "hostBuild", "callId", "resultId", "receiptDigest",
                ))
                for field in ("requestDigest", "receiptDigest"):
                    contracts._digest(data[field], "/attribution/" + field)
                contracts._id(data["hostId"], "/attribution/hostId")
                contracts._id(data["resultId"], "/attribution/resultId")
                contracts._text(data["hostBuild"], "/attribution/hostBuild", 128)
                contracts._text(data["callId"], "/attribution/callId", 256)
                stored = revision["receipts"].get(data["resultId"])
                if stored is None or data["resultId"] != following["payload"]["resultId"] or (
                    data["requestDigest"] != requests[0]
                    or contracts._encoded(data) != message[len(RECEIPT_MARKER):]
                ):
                    raise ContractIssue("E_NATIVE_HISTORY", "/", "attribution differs from its request or result")
                envelope = {
                    "schemaVersion": 1, "requestDigest": data["requestDigest"],
                    "hostId": data["hostId"], "hostBuild": data["hostBuild"],
                    "callId": data["callId"], "result": stored["result"],
                }
                if state.digest(envelope) != data["receiptDigest"]:
                    raise ContractIssue("E_NATIVE_HISTORY", "/", "attribution receipt digest changed")
                yield data


def receive_receipt(project_root, request, receipt, result_id):
    request, receipt = _request(request), _receipt(receipt)
    contracts._id(result_id, "/resultId")
    digest = state.digest(request)
    if receipt["requestDigest"] != digest or receipt["hostId"] != request["host"]["id"] or receipt["hostBuild"] != request["host"]["build"]:
        raise ContractIssue("E_NATIVE_BINDING", "/", "receipt does not match the prepared native host request")
    with manager._transaction(project_root, request["binding"]["executionId"]) as (root, record, revision):
        _validate(root, request, revision, check_guidance=False)
        brief = request["brief"]
        markers = [item for item in _request_markers(revision["events"], brief["taskId"], brief["attemptId"])
                   if item == digest]
        if len(markers) != 1:
            raise ContractIssue("E_NATIVE_BINDING", "/", "attempt has no unique recorded native request")
        validated = contracts.validate_task_result(receipt["result"], revision["plan"], brief)["data"]
        attribution = {
            "requestDigest": digest, "hostId": receipt["hostId"], "hostBuild": receipt["hostBuild"],
            "callId": receipt["callId"], "resultId": result_id, "receiptDigest": state.digest(receipt),
        }
        for identifier in manager._record_ids(root):
            peer = record if identifier == record["executionId"] else manager._load(root, identifier)
            for prior in _metadata(peer):
                if (prior["hostId"], prior["callId"]) == (receipt["hostId"], receipt["callId"]):
                    existing = revision["receipts"].get(result_id)
                    if prior == attribution and existing == {"brief": brief, "result": validated}:
                        return {**semantic_fields(), "idempotent": True}
                    raise ContractIssue("E_NATIVE_DUPLICATE", "/callId", "native call identity already has a receipt")
        if any(result_id in old["receipts"] for old in record["revisions"]):
            raise ContractIssue("E_NATIVE_DUPLICATE", "/resultId", "receipt ID already belongs to recorded work")
        manager._append(revision, "TASK_PROGRESS_UPDATED", brief["taskId"], brief["attemptId"],
                        {"message": RECEIPT_MARKER + contracts._encoded(attribution)})
        revision["receipts"][result_id] = {"brief": brief, "result": validated}
        manager._append(revision, "TASK_RESULT_RECEIVED", brief["taskId"], brief["attemptId"],
                        {"resultId": result_id})
    return {**semantic_fields(), "idempotent": False, "acceptance": "not-assessed"}
