"""Opt-in local barriers and pure model resolution; no host or worker calls."""

import json
import re

from artifact_contracts import ContractIssue, semantic_fields
import execution_contracts as contracts
import execution_manager as manager
import execution_state as state


def _copy(value):
    return json.loads(contracts._encoded(value))


def _model_id(value):
    value = contracts._text(value, "/modelId", 128)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", value):
        raise ContractIssue("E_MODEL_ID", "/modelId", "invalid model identifier")
    return value


def _models(value):
    items = contracts._strings(value, "/models")
    for item in items:
        _model_id(item)
    return items


def validate_controls_policy(value):
    data = contracts._object(value, "", (
        "schemaVersion", "enabled", "mode", "maxAttempts", "allowEscalation", "permittedModels",
    ))
    if type(data["schemaVersion"]) is int and data["schemaVersion"] == 2:
        contracts._enum(data["mode"], "/mode", ("supervised",))
    else:
        contracts._version(data)
    if type(data["enabled"]) is not bool or type(data["allowEscalation"]) is not bool:
        raise ContractIssue("E_SCHEMA_TYPE", "/", "controls flags must be booleans")
    contracts._enum(data["mode"], "/mode", ("manual", "supervised", "autonomous"))
    if contracts._number(data["maxAttempts"], "/maxAttempts") > contracts.MAX_ITEMS:
        raise ContractIssue("E_CONTROLS_LIMIT", "/maxAttempts", "attempt limit exceeds record capacity")
    _models(data["permittedModels"])
    return _copy(data)


def controls_path(project_root):
    root = manager._root(project_root)
    path = manager._safe(root, manager.lock_path(root).parent / "execution-controls.json")
    if not (root / ".git").is_dir():
        relative = path.relative_to(root).as_posix()
        if manager.manage_metrics._run_git(
            root, ["check-ignore", "--no-index", "--quiet", "--", relative]
        ).returncode:
            raise ContractIssue("E_CONTROLS_STORAGE", "/", "controls storage is not proven ignored")
    return path


def _digest(store):
    return state.digest({key: store[key] for key in ("schemaVersion", "generation", "policy")})


def _store(value):
    supervised = isinstance(value, dict) and type(value.get("schemaVersion")) is int and value["schemaVersion"] == 2
    data = contracts._object(value, "", (
        "schemaVersion", "generation", "policy", "safetyActivated", "paused", "pauseReason", "approvals", "cancelRequests",
    ) + (("retainedManual",) if supervised else ()))
    if not supervised:
        contracts._version(data)
    contracts._number(data["generation"], "/generation")
    validate_controls_policy(data["policy"])
    if (data["policy"]["schemaVersion"], data["policy"]["mode"]) != (
        (2, "supervised") if supervised else (1, "manual")
    ) or type(data["paused"]) is not bool or (
        type(data["safetyActivated"]) is not bool or data["policy"]["enabled"] and not data["safetyActivated"]
    ):
        raise ContractIssue("E_CONTROLS_STORE", "/", "unsupported controls state")
    if supervised and data["retainedManual"] is not None:
        if not isinstance(data["retainedManual"], dict) or data["retainedManual"].get("schemaVersion") != 1:
            raise ContractIssue("E_CONTROLS_STORE", "/", "retained manual controls must remain version 1")
        _store(data["retainedManual"])
    if data["paused"]:
        contracts._text(data["pauseReason"], "/pauseReason")
    elif data["pauseReason"] is not None:
        raise ContractIssue("E_CONTROLS_STORE", "/pauseReason", "resumed controls have no pause reason")
    for approval in state._mapping(data["approvals"], "/approvals").values():
        approval = contracts._object(approval, "/approval", (
            "planDigest", "executionPolicyDigest", "controlsDigest",
        ))
        for key, digest in approval.items():
            contracts._digest(digest, "/" + key)
    identities = set()
    for entry in contracts._array(data["cancelRequests"], "/cancelRequests"):
        entry = contracts._object(entry, "/cancelRequest", ("binding", "taskId", "attemptId", "reason", "status"))
        binding = contracts._object(entry["binding"], "/binding", ("executionId", "planRevision", "planDigest"))
        contracts._id(binding["executionId"], "/executionId")
        contracts._number(binding["planRevision"], "/planRevision")
        contracts._digest(binding["planDigest"], "/planDigest")
        for key in ("taskId", "attemptId"):
            contracts._id(entry[key], "/" + key)
        contracts._text(entry["reason"], "/reason")
        contracts._enum(entry["status"], "/status", ("pending", "resolved"))
        identity = (binding["executionId"], entry["taskId"], entry["attemptId"])
        if identity in identities:
            raise ContractIssue("E_CONTROLS_STORE", "/cancelRequests", "duplicate cancellation identity")
        identities.add(identity)
    return _copy(data)


def _read(root):
    path = manager._safe(root, manager.lock_path(root).parent / "execution-controls.json")
    return _store(manager._read(controls_path(root))) if path.exists() else None


def _active(root):
    manager._consent(root, enabled=True)
    store = _read(root)
    if store is None or not store["policy"]["enabled"]:
        raise ContractIssue("E_CONTROLS_DISABLED", "/", "execution controls are disabled")
    return store


def configure_controls(project_root, policy, dry_run=False):
    policy = validate_controls_policy(policy)
    if type(dry_run) is not bool:
        raise ContractIssue("E_SCHEMA_TYPE", "/dryRun", "expected boolean")
    if policy["schemaVersion"] == 1 and policy["mode"] != "manual":
        raise ContractIssue("E_CONTROLS_CAPABILITY", "/mode", "live runtime mode is not qualified")
    root = manager._root(project_root)
    if dry_run:
        return {**semantic_fields(), "dryRun": True, "policy": policy}
    controls_path(root)
    with manager._writer(root):
        if policy["enabled"]:
            manager._consent(root, enabled=True)
        previous = _read(root)
        if previous is not None and previous["schemaVersion"] == 2 and policy["schemaVersion"] == 1:
            raise ContractIssue("E_CONTROLS_CAPABILITY", "/", "automatic controls downgrade would lose safety history")
        store = {
            "schemaVersion": policy["schemaVersion"], "generation": 1 if previous is None else previous["generation"] + 1,
            "policy": policy, "paused": False if previous is None else previous["paused"],
            "safetyActivated": policy["enabled"] or bool(previous and previous["safetyActivated"]),
            "pauseReason": None if previous is None else previous["pauseReason"],
            "approvals": {}, "cancelRequests": [] if previous is None else previous["cancelRequests"],
            **({"retainedManual": None if previous is None else (
                previous if previous["schemaVersion"] == 1 else previous["retainedManual"]
            )} if policy["schemaVersion"] == 2 else {}),
        }
        manager._write(root, controls_path(root), _store(store))
    return {**semantic_fields(), "controlsDigest": _digest(store)}


def inspect_controls(project_root):
    root = manager._root(project_root)
    store = _read(root)
    return {**semantic_fields(), "enabled": bool(store and store["policy"]["enabled"]),
            "paused": bool(store and store["paused"]),
            "cancelRequests": [] if store is None else store["cancelRequests"],
            "controlsDigest": None if store is None else _digest(store), "store": store,
            "runtimeCapabilities": {"nativeDispatch": bool(store and store["policy"]["mode"] == "supervised"),
                                    "autonomous": False,
                                    "hostCancellation": False, "spendEnforcement": False}}


def approve_controls(project_root, execution_id, plan_digest, execution_policy_digest, controls_digest):
    for value in (plan_digest, execution_policy_digest, controls_digest):
        contracts._digest(value, "/approval")
    with manager._writer(project_root) as root:
        store = _active(root)
        current = manager.inspect_execution(root, execution_id)
        expected = {"planDigest": current["planDigest"], "executionPolicyDigest": current["policyDigest"],
                    "controlsDigest": _digest(store)}
        if not current["state"]["approved"] or expected != {
            "planDigest": plan_digest, "executionPolicyDigest": execution_policy_digest,
            "controlsDigest": controls_digest,
        }:
            raise ContractIssue("E_CONTROLS_APPROVAL", "/", "base approval or explicit bindings are stale")
        store["approvals"][execution_id] = expected
        manager._write(root, controls_path(root), _store(store))
    return semantic_fields()


def set_pause(project_root, paused, reason):
    if type(paused) is not bool:
        raise ContractIssue("E_SCHEMA_TYPE", "/paused", "expected boolean")
    contracts._text(reason, "/reason")
    with manager._writer(project_root) as root:
        store = _active(root)
        store["paused"], store["pauseReason"] = paused, reason if paused else None
        manager._write(root, controls_path(root), _store(store))
    return {**semantic_fields(), "paused": paused}


def _native_attempt(revision, task_id, attempt_id):
    from native_execution import _request_markers
    return bool(_request_markers(revision["events"], task_id, attempt_id))

def _unknown_native_attempts(record):
    from native_execution import _metadata, _request_markers
    confirmed = {entry["requestDigest"] for entry in _metadata(record)}
    unknown = []
    for revision in record["revisions"]:
        for event in revision["events"]:
            if event["type"] != "TASK_STARTED":
                continue
            for digest in _request_markers(revision["events"], event["taskId"], event["attemptId"]):
                if digest not in confirmed:
                    unknown.append({"planRevision": revision["plan"]["revision"], "taskId": event["taskId"],
                                    "attemptId": event["attemptId"], "requestDigest": digest})
    return unknown


def request_cancel(project_root, execution_id, task_id, reason):
    contracts._id(task_id, "/taskId")
    contracts._text(reason, "/reason")
    with manager._writer(project_root) as root:
        store = _active(root)
        revision = manager._load(root, execution_id)["revisions"][-1]
        task = manager._projection(revision)["tasks"].get(task_id)
        if task is None or task["attemptId"] is None or task["status"] not in ("running", "blocked", "reported"):
            raise ContractIssue("E_CONTROLS_CANCELLATION", "/", "cancellation requires unresolved started work")
        binding = {"executionId": execution_id, "planRevision": revision["plan"]["revision"],
                   "planDigest": state.digest(revision["plan"])}
        entry = {"binding": binding, "taskId": task_id, "attemptId": task["attemptId"],
                 "reason": reason, "status": "pending"}
        previous = next((item for item in store["cancelRequests"]
                         if item["binding"] == binding and item["taskId"] == task_id
                         and item["attemptId"] == task["attemptId"]), None)
        if previous is not None:
            if previous != entry:
                raise ContractIssue("E_CONTROLS_CANCELLATION", "/", "cancellation intent already differs")
            return {**semantic_fields(), "idempotent": True, "cancellation": "pending"}
        store["cancelRequests"].append(entry)
        manager._write(root, controls_path(root), _store(store))
    return {**semantic_fields(), "idempotent": False, "cancellation": "pending"}


def resolve_manual_cancel(project_root, execution_id, task_id, reason):
    contracts._id(task_id, "/taskId")
    contracts._text(reason, "/reason")
    with manager._writer(project_root) as root:
        store = _active(root)
        record = manager._load(root, execution_id)
        entries = [entry for entry in store["cancelRequests"]
                   if entry["binding"]["executionId"] == execution_id and entry["taskId"] == task_id
                   and entry["status"] == "pending"]
        if not entries:
            raise ContractIssue("E_CONTROLS_CANCELLATION", "/", "no pending cancellation to reconcile")
        for entry in entries:
            revision = next((item for item in record["revisions"]
                             if state.digest(item["plan"]) == entry["binding"]["planDigest"]), None)
            if revision is None or _native_attempt(revision, task_id, entry["attemptId"]):
                raise ContractIssue("E_CONTROLS_CANCELLATION", "/", "native host stop evidence is unavailable")
            task = manager._projection(revision)["tasks"][task_id]
            if task["attemptId"] != entry["attemptId"] or task["status"] not in ("accepted", "failed", "cancelled"):
                raise ContractIssue("E_CONTROLS_CANCELLATION", "/", "manual attempt remains unresolved")
            entry["status"] = "resolved"
        manager._write(root, controls_path(root), _store(store))
    return {**semantic_fields(), "cancellation": "resolved-manual-only"}


def enforce_start(root, execution_id, task_id, attempt_id, native=False, bounded=False):
    store = _read(root)
    if store is None:
        return
    if store["paused"]:
        raise ContractIssue("E_CONTROLS_PAUSED", "/", "project execution is explicitly paused")
    if any(entry["status"] == "pending" for entry in store["cancelRequests"]):
        raise ContractIssue("E_CONTROLS_CANCELLATION", "/", "pending stop intent requires reconciliation")
    if store["safetyActivated"]:
        for identifier in manager._record_ids(root):
            if _unknown_native_attempts(manager._load(root, identifier)):
                raise ContractIssue("E_CONTROLS_CANCELLATION", "/", "unconfirmed native work requires host evidence")
    if not store["policy"]["enabled"]:
        return
    record = manager._load(root, execution_id)
    revision = record["revisions"][-1]
    expected = {"planDigest": state.digest(revision["plan"]),
                "executionPolicyDigest": state.digest(manager._consent(root, enabled=True)),
                "controlsDigest": _digest(store)}
    if not manager._projection(revision)["approved"] or store["approvals"].get(execution_id) != expected:
        raise ContractIssue("E_CONTROLS_APPROVAL", "/", "separate current controls approval is required")
    if native and not (bounded and store["policy"]["mode"] == "supervised"):
        raise ContractIssue("E_CONTROLS_CAPABILITY", "/", "manual controls do not qualify native dispatch")
    contracts._id(task_id, "/taskId")
    contracts._id(attempt_id, "/attemptId")
    started = []
    for old in record["revisions"]:
        for event in old["events"]:
            if event["type"] == "TASK_STARTED" and event["taskId"] == task_id:
                started.append(next(item for item in old["plan"]["tasks"] if item["id"] == task_id))
    if len(started) >= store["policy"]["maxAttempts"]:
        raise ContractIssue("E_CONTROLS_ATTEMPTS", "/", "explicit task attempt allowance is exhausted")
    planned = next((item for item in revision["plan"]["tasks"] if item["id"] == task_id), None)
    if planned is None:
        raise ContractIssue("E_EXECUTION_REFERENCE", "/taskId", "unknown planned task")
    assignment = planned["assignment"]
    if started and not store["policy"]["allowEscalation"] and assignment != started[-1]["assignment"]:
        raise ContractIssue("E_CONTROLS_ESCALATION", "/", "assignment escalation is not explicitly permitted")
    if assignment["model"] is not None and assignment["model"] not in store["policy"]["permittedModels"]:
        raise ContractIssue("E_MODEL_DENIED", "/model", "explicit model is not permitted")


def enforce_terminal(root, execution_id, task_id, action):
    store = _read(root)
    if store is None or not store["safetyActivated"]:
        return
    record = manager._load(root, execution_id)
    revision = record["revisions"][-1]
    task = manager._projection(revision)["tasks"].get(task_id)
    if task is not None and _native_attempt(revision, task_id, task["attemptId"]):
        if action in ("fail", "reject", "accept") and task["status"] == "reported":
            from native_execution import _metadata
            if any(entry["resultId"] == task["resultId"] for entry in _metadata(record)):
                return
        raise ContractIssue("E_CONTROLS_CANCELLATION", "/", "manual outcome cannot confirm a native host stop")

def enforce_deletion(root, record):
    store = _read(root)
    if store is None:
        return
    if any(entry["status"] == "pending" and entry["binding"]["executionId"] == record["executionId"]
           for entry in store["cancelRequests"]) or store["safetyActivated"] and _unknown_native_attempts(record):
        raise ContractIssue("E_CONTROLS_CANCELLATION", "/", "retain history needed for stop reconciliation")
    if store["safetyActivated"] and any(event["type"] == "TASK_STARTED"
                                       for revision in record["revisions"] for event in revision["events"]):
        raise ContractIssue("E_CONTROLS_HISTORY", "/", "retain consumed attempt history after controls activation")


def reconcile_execution(project_root, execution_id):
    current = manager.inspect_execution(project_root, execution_id)
    controls = inspect_controls(project_root)
    return {**semantic_fields(), "redispatch": False, "hostCancellation": "unavailable",
            "unknownNativeAttempts": _unknown_native_attempts(current["record"]),
            "unresolvedTasks": [key for key, task in current["state"]["tasks"].items()
                                if task["status"] in ("running", "blocked", "reported")],
            "writerLockPresent": current["writerLockPresent"], "controls": controls}


def _pricing(value):
    if value is None:
        return None
    data = contracts._object(value, "/pricing", ("currency", "rateVersion", "unit", "units", "priceMinor"))
    if not re.fullmatch(r"[A-Z]{3}", contracts._text(data["currency"], "/currency", 3)):
        raise ContractIssue("E_MODEL_PRICE", "/currency", "expected an uppercase currency code")
    contracts._text(data["rateVersion"], "/rateVersion", 128)
    contracts._enum(data["unit"], "/unit", ("request", "input-token", "output-token"))
    contracts._number(data["units"], "/units")
    contracts._number(data["priceMinor"], "/priceMinor", 0)
    return data


def _model(value):
    data = contracts._object(value, "/model", ("id", "available", "pricing"))
    _model_id(data["id"])
    if type(data["available"]) is not bool:
        raise ContractIssue("E_SCHEMA_TYPE", "/available", "expected boolean")
    _pricing(data["pricing"])
    return data


def validate_inventory(value):
    data = contracts._object(value, "", ("schemaVersion", "hostId", "hostBuild", "source", "models"))
    contracts._version(data)
    contracts._enum(data["source"], "/source", ("host-observation", "unavailable"))
    models = contracts._array(data["models"], "/models")
    if data["source"] == "unavailable":
        if data["hostId"] is not None or data["hostBuild"] is not None or models:
            raise ContractIssue("E_MODEL_INVENTORY", "/", "unavailable inventory cannot claim observations")
    else:
        contracts._id(data["hostId"], "/hostId")
        contracts._text(data["hostBuild"], "/hostBuild", 128)
    identities = set()
    for raw in models:
        item = _model(raw)
        if item["id"] in identities:
            raise ContractIssue("E_MODEL_INVENTORY", "/models", "duplicate model identity")
        identities.add(item["id"])
    return _copy(data)


def resolve_model(inventory, profile, permitted_models, requested_model=None, observation=None):
    inventory = validate_inventory(inventory)
    profile = contracts._object(profile, "/profile", ("id", "candidates"))
    contracts._id(profile["id"], "/profile/id")
    candidates, permitted = _models(profile["candidates"]), _models(permitted_models)
    available = {item["id"]: item for item in inventory["models"] if item["available"]}
    if requested_model is not None:
        _model_id(requested_model)
        if requested_model not in candidates or requested_model not in permitted:
            raise ContractIssue("E_MODEL_DENIED", "/requestedModel", "requested model is not permitted by the profile")
        choices = [requested_model] if requested_model in available else []
    else:
        choices = [item for item in candidates if item in permitted and item in available]
    if not choices:
        raise ContractIssue("E_MODEL_UNAVAILABLE", "/", "no permitted available model in supplied inventory")
    selected, observed = choices[0], None
    if observation is not None:
        value = contracts._object(observation, "/observation", ("hostId", "hostBuild", "inventoryDigest", "modelId"))
        if value != {"hostId": inventory["hostId"], "hostBuild": inventory["hostBuild"],
                     "inventoryDigest": state.digest(inventory), "modelId": selected}:
            raise ContractIssue("E_MODEL_OBSERVATION", "/", "effective model or host snapshot differs")
        observed = selected
    return {**semantic_fields(), "requestedModel": selected, "observedModel": observed,
            "pricing": _copy(available[selected]["pricing"]), "inventoryDigest": state.digest(inventory),
            "routing": "unverified" if observed is None else "matched-supplied-observation"}


def estimate_cost(model, units):
    model = _model(model)
    units = contracts._number(units, "/units", 0)
    pricing = model["pricing"]
    if pricing is None:
        return {**semantic_fields(), "costMinor": None, "currency": None, "basis": "unavailable"}
    cost = (units * pricing["priceMinor"] + pricing["units"] - 1) // pricing["units"]
    contracts._number(cost, "/costMinor", 0)
    return {**semantic_fields(), "costMinor": cost, "currency": pricing["currency"],
            "basis": _copy(pricing)}
