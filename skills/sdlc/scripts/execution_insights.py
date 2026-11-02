"""Selected, read-only execution evidence and inactive, reproducible proposals."""

import importlib
import json
from datetime import datetime

from artifact_contracts import ContractIssue
import execution_contracts as contracts
import execution_controls as controls
import execution_manager as manager
import execution_state as state


LIMITS = {
    "minimumSamples": 3,
    "sampling": "selected-local-records",
    "quality": "independent-acceptance-required",
    "timing": "separate-sources-no-speed-or-savings-claim",
    "routing": "qualified-comparable-model-evidence-unavailable",
    "adoption": "inactive-review-is-not-adoption",
}
SUMMARY_FIELDS = (
    "executionCount", "revisionCount", "taskCount", "attemptCount", "acceptedCount",
    "failedCount", "rejectedCount", "cancelledCount", "reportedCount", "reworkTaskCount",
    "missingEstimateCount", "missingRecordedIntervalCount", "missingTelemetryAttemptCount",
)


def _copy(value):
    return json.loads(contracts._encoded(value))


def _signed(value, field):
    return _copy({**value, field: state.digest(value)})


def _check_digest(value, field):
    contracts._digest(value[field], "/" + field)
    if value[field] != state.digest({key: item for key, item in value.items() if key != field}):
        raise ContractIssue("E_INSIGHTS_DIGEST", "/" + field, "artifact digest differs")


def _binding(plan):
    return {"executionId": plan["executionId"], "planRevision": plan["revision"],
            "planDigest": state.digest(plan)}


def _interval(current):
    if current["startedAt"] is None or current["endedAt"] is None:
        return None
    start = datetime.strptime(current["startedAt"], "%Y-%m-%dT%H:%M:%SZ")
    end = datetime.strptime(current["endedAt"], "%Y-%m-%dT%H:%M:%SZ")
    return contracts._number(int((end - start).total_seconds()) * 1000, "/recordedIntervalMs", 0)


def build_snapshot(project_root, execution_id):
    current = manager.inspect_execution(project_root, execution_id)
    reconciled = controls.reconcile_execution(project_root, execution_id)
    barrier = reconciled["controls"]
    tasks = []
    # Version 2 adds acceptance provenance only when an independent-validation acceptance exists,
    # so version-1 readers refuse it instead of presenting it as worker-verified acceptance.
    independent = any(projected["status"] == "accepted" and projected["acceptance"]["schemaVersion"] == 2
                      for projected in current["state"]["tasks"].values())
    for task in current["plan"]["tasks"]:
        projected = current["state"]["tasks"][task["id"]]
        tasks.append({
            "id": task["id"], "title": task["title"], "status": projected["status"],
            "attemptId": projected["attemptId"], "reportedStatus": projected["reportedStatus"],
            "estimateMs": task["estimateMs"], "recordedIntervalMs": _interval(projected),
            "requestedModel": task["assignment"]["model"],
            **({"acceptanceBasis": state.acceptance_basis(projected)} if independent else {}),
        })
    return _signed({
        "schemaVersion": 2 if independent else 1, "kind": "sdlc-execution-snapshot", "binding": _binding(current["plan"]),
        "approved": current["state"]["approved"], "writerLockPresent": current["writerLockPresent"],
        "tasks": tasks,
        "controls": {
            "enabled": barrier["enabled"], "paused": barrier["paused"],
            "pendingCancellationCount": sum(item["status"] == "pending" for item in barrier["cancelRequests"]),
            "unknownNativeAttemptCount": len(reconciled["unknownNativeAttempts"]),
        },
    }, "snapshotDigest")


def _telemetry_module():
    try:
        return importlib.import_module("execution_telemetry")
    except ModuleNotFoundError as error:
        if error.name != "execution_telemetry":
            raise
        raise ContractIssue("E_INSIGHTS_DEPENDENCY", "/", "execution telemetry inspection is unavailable") from error


def _identity(binding, task_id, attempt_id):
    return (binding["executionId"], binding["planRevision"], binding["planDigest"], task_id, attempt_id)


def _attempts(sources):
    for source in sources:
        for revision in source["record"]["revisions"]:
            projected = manager._projection(revision)
            binding = _binding(revision["plan"])
            for task in revision["plan"]["tasks"]:
                yield source, revision, binding, task, projected["tasks"][task["id"]]


def _cost(entry):
    observation = entry["observation"]
    pricing = observation["pricing"]
    cost = {"observationId": observation["id"], "costMinor": None, "currency": None,
            "rateVersion": None, "unit": None}
    if pricing is not None:
        key = {"request": "requests", "input-token": "inputTokens", "output-token": "outputTokens"}[pricing["unit"]]
        units = observation["usage"][key]
        cost.update(currency=pricing["currency"], rateVersion=pricing["rateVersion"], unit=pricing["unit"])
        if units is not None:
            model = {"id": observation["observedModel"], "available": True, "pricing": pricing}
            cost["costMinor"] = controls.estimate_cost(model, units)["costMinor"]
    return cost


def _analysis(sources, telemetry):
    summary = dict.fromkeys(SUMMARY_FIELDS, 0)
    summary["executionCount"] = len(sources)
    observed = {
        _identity(item["observation"]["binding"], item["observation"]["taskId"], item["observation"]["attemptId"])
        for item in telemetry["observations"]
    }
    started = {}
    for source in sources:
        summary["revisionCount"] += len(source["record"]["revisions"])
        for revision in source["record"]["revisions"]:
            summary["rejectedCount"] += sum(event["type"] == "VALIDATION_FAILED" for event in revision["events"])
    for source, _, binding, task, current in _attempts(sources):
        summary["taskCount"] += 1
        summary["missingEstimateCount"] += task["estimateMs"] is None
        for status in ("accepted", "failed", "cancelled", "reported"):
            summary[status + "Count"] += current["status"] == status
        if current["attemptId"] is not None:
            summary["attemptCount"] += 1
            key = (source["executionId"], task["id"])
            started[key] = started.get(key, 0) + 1
            summary["missingRecordedIntervalCount"] += _interval(current) is None
            summary["missingTelemetryAttemptCount"] += _identity(binding, task["id"], current["attemptId"]) not in observed
    summary["reworkTaskCount"] = sum(count > 1 for count in started.values())
    return _signed({
        "schemaVersion": 1, "kind": "sdlc-execution-analysis", "sources": sources,
        "telemetry": {**telemetry, "costs": [_cost(item) for item in telemetry["observations"]]},
        "summary": summary,
    }, "analysisDigest")


def analyze_executions(project_root, execution_ids):
    identifiers = sorted(contracts._ids(execution_ids, "/executionIds", True))
    root = manager._root(project_root)
    sources = []
    for identifier in identifiers:
        inspected = manager.inspect_execution(root, identifier)
        sources.append({
            "executionId": identifier, "recordDigest": state.digest(inspected["record"]),
            "currentPolicyDigest": inspected["policyDigest"], "record": inspected["record"],
        })
    identities = {_identity(binding, task["id"], current["attemptId"])
                  for _, _, binding, task, current in _attempts(sources) if current["attemptId"] is not None}
    inspected = _telemetry_module().inspect_telemetry(root)
    observations = [] if inspected["store"] is None else inspected["store"]["observations"]
    selected = [entry for entry in observations if _identity(
        entry["observation"]["binding"], entry["observation"]["taskId"], entry["observation"]["attemptId"],
    ) in identities]
    selected.sort(key=lambda entry: entry["observation"]["id"])
    return _validate_analysis(_analysis(
        sources, {"enabled": inspected["enabled"], "storeDigest": inspected["storeDigest"], "observations": selected},
    ))


def _validate_analysis(value):
    data = contracts._object(value, "/analysis", (
        "schemaVersion", "kind", "sources", "telemetry", "summary", "analysisDigest",
    ))
    contracts._version(data)
    contracts._enum(data["kind"], "/kind", ("sdlc-execution-analysis",))
    sources = contracts._array(data["sources"], "/sources", True)
    identifiers = []
    for raw in sources:
        source = contracts._object(raw, "/source", ("executionId", "recordDigest", "currentPolicyDigest", "record"))
        identifiers.append(contracts._id(source["executionId"], "/executionId"))
        record = state.validate_record(source["record"])
        contracts._digest(source["recordDigest"], "/recordDigest")
        if source["currentPolicyDigest"] is not None:
            contracts._digest(source["currentPolicyDigest"], "/currentPolicyDigest")
        if record["executionId"] != source["executionId"] or state.digest(record) != source["recordDigest"]:
            raise ContractIssue("E_INSIGHTS_SOURCE", "/sources", "source identity or digest differs")
    if identifiers != sorted(set(identifiers)):
        raise ContractIssue("E_INSIGHTS_SOURCE", "/sources", "sources must be unique and canonical")
    telemetry = contracts._object(data["telemetry"], "/telemetry", ("enabled", "storeDigest", "observations", "costs"))
    if type(telemetry["enabled"]) is not bool:
        raise ContractIssue("E_SCHEMA_TYPE", "/enabled", "expected boolean")
    if telemetry["storeDigest"] is not None:
        contracts._digest(telemetry["storeDigest"], "/storeDigest")
    observations = contracts._array(telemetry["observations"], "/observations")
    identities = {_identity(binding, task["id"], current["attemptId"])
                  for _, _, binding, task, current in _attempts(sources) if current["attemptId"] is not None}
    contexts = {_identity(binding, task["id"], current["attemptId"]): (source, revision, task)
                for source, revision, binding, task, current in _attempts(sources)
                if current["attemptId"] is not None}
    observation_ids = []
    prior_observations = []
    for raw in observations:
        entry = contracts._object(raw, "/observationEntry", ("consentGeneration", "observation"))
        contracts._number(entry["consentGeneration"], "/consentGeneration")
        module = _telemetry_module()
        observation = module.validate_observation(entry["observation"])
        observation_ids.append(observation["id"])
        identity = _identity(observation["binding"], observation["taskId"], observation["attemptId"])
        if identity not in identities:
            raise ContractIssue("E_INSIGHTS_SOURCE", "/observation", "observation does not bind selected attempt")
        source, revision, task = contexts[identity]
        if observation["requestedModel"] != task["assignment"]["model"]:
            raise ContractIssue("E_INSIGHTS_SOURCE", "/requestedModel", "requested model differs from the bound plan")
        from native_execution import _metadata, _request_markers
        attribution = observation["source"]
        if attribution["kind"] == "manual-declaration":
            if _request_markers(revision["events"], observation["taskId"], observation["attemptId"]):
                raise ContractIssue("E_INSIGHTS_SOURCE", "/source", "manual timing cannot replace native observations")
        elif not any(
            entry["resultId"] in revision["receipts"]
            and revision["receipts"][entry["resultId"]]["result"]["taskId"] == observation["taskId"]
            and revision["receipts"][entry["resultId"]]["result"]["attemptId"] == observation["attemptId"]
            and all(entry[field] == attribution[field] for field in ("hostId", "hostBuild", "callId"))
            for entry in _metadata(source["record"])
        ):
            raise ContractIssue("E_INSIGHTS_SOURCE", "/source", "host timing has no retained native attribution")
        if any(module._scope(observation) == module._scope(prior) and module._overlap(observation, prior)
               for prior in prior_observations):
            raise ContractIssue("E_INSIGHTS_SOURCE", "/observations", "attributed observation windows overlap")
        prior_observations.append(observation)
    if observation_ids != sorted(set(observation_ids)) or observations and telemetry["storeDigest"] is None:
        raise ContractIssue("E_INSIGHTS_SOURCE", "/observations", "observation provenance is missing or ambiguous")
    summary = contracts._object(data["summary"], "/summary", SUMMARY_FIELDS)
    for key in SUMMARY_FIELDS:
        contracts._number(summary[key], "/" + key, 0)
    contracts._array(telemetry["costs"], "/costs")
    _check_digest(data, "analysisDigest")
    expected = _analysis(sources, {key: telemetry[key] for key in ("enabled", "storeDigest", "observations")})
    if contracts._encoded(data) != contracts._encoded(expected):
        raise ContractIssue("E_INSIGHTS_DERIVATION", "/analysis", "analysis differs from retained evidence")
    return expected


def _estimates(analysis):
    groups = {}
    observations = {}
    for entry in analysis["telemetry"]["observations"]:
        observation = entry["observation"]
        identity = _identity(observation["binding"], observation["taskId"], observation["attemptId"])
        observations.setdefault(identity, []).append(observation)
    for source, _, binding, task, current in _attempts(analysis["sources"]):
        if current["status"] != "accepted" or current["attemptId"] is None:
            continue
        definition = state.digest({key: item for key, item in task.items() if key != "estimateMs"})
        candidates = [("manager-recorded-interval", _interval(current), None, None)]
        host = [item for item in observations.get(_identity(binding, task["id"], current["attemptId"]), [])
                if item["source"]["kind"] == "host-observation" and item["durationMs"] is not None]
        # Separate windows are not independent attempts or a complete task-duration claim.
        if len(host) == 1:
            observation = host[0]
            attribution = {key: observation["source"][key] for key in ("hostId", "hostBuild")}
            attribution.update(observedModel=observation["observedModel"], inventoryDigest=observation["inventoryDigest"])
            candidates.append(("host-observed-duration", observation["durationMs"], observation["id"], attribution))
        for basis, duration, observation_id, attribution in candidates:
            if duration is None:
                continue
            key = (source["executionId"], task["id"], definition, basis, contracts._encoded(attribution))
            if key not in groups:
                groups[key] = {
                    "executionId": source["executionId"], "taskId": task["id"], "taskDefinitionDigest": definition,
                    "basis": basis, "source": attribution, "sampleCount": 0, "estimateMs": None, "samples": [],
                }
            groups[key]["samples"].append({
                "binding": binding, "taskId": task["id"], "attemptId": current["attemptId"],
                "observationId": observation_id, "durationMs": duration,
            })
    estimates = []
    for key in sorted(groups):
        group = groups[key]
        contracts._array(group["samples"], "/samples", True)
        group["sampleCount"] = len(group["samples"])
        if group["sampleCount"] >= LIMITS["minimumSamples"]:
            ordered = sorted(sample["durationMs"] for sample in group["samples"])
            middle = len(ordered) // 2
            group["estimateMs"] = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) // 2
        estimates.append(group)
    return contracts._array(estimates, "/estimates")


def propose_estimates(project_root, execution_ids):
    analysis = analyze_executions(project_root, execution_ids)
    return _signed({
        "schemaVersion": 1, "kind": "sdlc-execution-proposal", "active": False, "status": "proposed",
        "analysis": analysis, "estimates": _estimates(analysis), "routingRecommendations": [],
        "limits": LIMITS, "review": None,
    }, "proposalDigest")


def validate_proposal(value):
    data = contracts._object(value, "", (
        "schemaVersion", "kind", "active", "status", "analysis", "estimates",
        "routingRecommendations", "limits", "review", "proposalDigest",
    ))
    contracts._version(data)
    contracts._enum(data["kind"], "/kind", ("sdlc-execution-proposal",))
    if data["active"] is not False:
        raise ContractIssue("E_INSIGHTS_INACTIVE", "/active", "proposals cannot activate policy")
    contracts._enum(data["status"], "/status", ("proposed", "approved", "rejected"))
    analysis = _validate_analysis(data["analysis"])
    contracts._array(data["estimates"], "/estimates")
    contracts._array(data["routingRecommendations"], "/routingRecommendations")
    if (contracts._encoded(data["estimates"]) != contracts._encoded(_estimates(analysis))
            or data["routingRecommendations"] != []
            or contracts._encoded(data["limits"]) != contracts._encoded(LIMITS)):
        raise ContractIssue("E_INSIGHTS_DERIVATION", "/", "proposal differs from evidence or fixed safety limits")
    if data["status"] == "proposed":
        if data["review"] is not None:
            raise ContractIssue("E_INSIGHTS_REVIEW", "/review", "proposed artifact has no review")
    else:
        review = contracts._object(data["review"], "/review", ("decision", "reason", "proposalDigest"))
        contracts._enum(review["decision"], "/decision", ("approved", "rejected"))
        contracts._text(review["reason"], "/reason")
        base = {key: item for key, item in data.items() if key != "proposalDigest"}
        base.update(status="proposed", review=None)
        if review["decision"] != data["status"] or review["proposalDigest"] != state.digest(base):
            raise ContractIssue("E_INSIGHTS_REVIEW", "/review", "review does not bind the inactive proposal")
    _check_digest(data, "proposalDigest")
    return _copy(data)


def review_proposal(value, approved, reason):
    data = validate_proposal(value)
    if type(approved) is not bool:
        raise ContractIssue("E_SCHEMA_TYPE", "/approved", "expected boolean")
    contracts._text(reason, "/reason")
    if data["status"] != "proposed":
        raise ContractIssue("E_INSIGHTS_REVIEW", "/status", "only an unreviewed proposal can be reviewed")
    data["status"] = "approved" if approved else "rejected"
    data["review"] = {"decision": data["status"], "reason": reason, "proposalDigest": data.pop("proposalDigest")}
    return validate_proposal(_signed(data, "proposalDigest"))
