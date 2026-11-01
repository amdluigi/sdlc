"""Explicit local telemetry consent and supplied observations; no collection."""

import json

from artifact_contracts import ContractIssue, semantic_fields
import execution_contracts as contracts
import execution_controls as controls
import execution_manager as manager
import execution_state as state


def _copy(value):
    return json.loads(contracts._encoded(value))


def validate_telemetry_policy(value):
    data = contracts._object(value, "", ("schemaVersion", "enabled"))
    contracts._version(data)
    if type(data["enabled"]) is not bool:
        raise ContractIssue("E_SCHEMA_TYPE", "/enabled", "expected boolean")
    return _copy(data)


def telemetry_path(project_root):
    root = manager._root(project_root)
    path = manager._safe(root, manager.lock_path(root).parent / "execution-telemetry.json")
    if not (root / ".git").is_dir() and manager.manage_metrics._run_git(
        root, ["check-ignore", "--no-index", "--quiet", "--", path.relative_to(root).as_posix()]
    ).returncode:
        raise ContractIssue("E_TELEMETRY_STORAGE", "/", "telemetry storage is not proven ignored")
    return path


def validate_observation(value):
    data = contracts._object(value, "", (
        "schemaVersion", "id", "binding", "taskId", "attemptId", "source", "requestedModel",
        "observedModel", "inventoryDigest", "window", "durationMs", "usage", "pricing",
    ))
    contracts._version(data)
    for field in ("id", "taskId", "attemptId"):
        contracts._id(data[field], "/" + field)
    binding = contracts._object(data["binding"], "/binding", ("executionId", "planRevision", "planDigest"))
    contracts._id(binding["executionId"], "/executionId")
    contracts._number(binding["planRevision"], "/planRevision")
    contracts._digest(binding["planDigest"], "/planDigest")
    source = contracts._object(data["source"], "/source", ("kind", "hostId", "hostBuild", "callId"))
    contracts._enum(source["kind"], "/source/kind", ("manual-declaration", "host-observation"))
    if source["kind"] == "host-observation":
        contracts._id(source["hostId"], "/source/hostId")
        contracts._text(source["hostBuild"], "/source/hostBuild", 128)
        contracts._text(source["callId"], "/source/callId", 256)
    elif any(source[field] is not None for field in ("hostId", "hostBuild", "callId")):
        raise ContractIssue("E_TELEMETRY_ATTRIBUTION", "/source", "manual declarations cannot claim a host")
    if data["requestedModel"] is not None:
        contracts._text(data["requestedModel"], "/requestedModel", 128)
    if data["observedModel"] is not None:
        controls._model_id(data["observedModel"])
    if data["inventoryDigest"] is not None:
        contracts._digest(data["inventoryDigest"], "/inventoryDigest")
    window = contracts._object(data["window"], "/window", ("clockId", "startMs", "endMs"))
    contracts._id(window["clockId"], "/window/clockId")
    for field in ("startMs", "endMs"):
        contracts._number(window[field], "/window/" + field, 0)
    if window["endMs"] < window["startMs"]:
        raise ContractIssue("E_TELEMETRY_WINDOW", "/window", "observation interval is reversed")
    if data["durationMs"] is not None:
        contracts._number(data["durationMs"], "/durationMs", 0)
        if data["durationMs"] > window["endMs"] - window["startMs"]:
            raise ContractIssue("E_TELEMETRY_WINDOW", "/durationMs", "duration exceeds its supplied clock interval")
    usage = contracts._object(data["usage"], "/usage", ("requests", "inputTokens", "outputTokens"))
    for field, quantity in usage.items():
        if quantity is not None:
            contracts._number(quantity, "/usage/" + field, 0)
    controls._pricing(data["pricing"])
    if source["kind"] == "manual-declaration" and (
        any(data[field] is not None for field in ("observedModel", "inventoryDigest", "pricing"))
        or any(quantity is not None for quantity in usage.values())
    ):
        raise ContractIssue("E_TELEMETRY_ATTRIBUTION", "/", "manual declarations cannot claim observed model or usage")
    if data["observedModel"] is None:
        if data["pricing"] is not None or data["inventoryDigest"] is not None:
            raise ContractIssue("E_TELEMETRY_ATTRIBUTION", "/", "model and inventory are required for pricing")
    elif data["inventoryDigest"] is None:
        raise ContractIssue("E_TELEMETRY_ATTRIBUTION", "/inventoryDigest", "observed model requires inventory binding")
    if data["pricing"] is not None:
        field = {"request": "requests", "input-token": "inputTokens", "output-token": "outputTokens"}[
            data["pricing"]["unit"]]
        if usage[field] is not None:
            controls.estimate_cost({"id": data["observedModel"], "available": True, "pricing": data["pricing"]},
                                   usage[field])
    return _copy(data)


def _scope(observation):
    source, window = observation["source"], observation["window"]
    if source["kind"] == "host-observation":
        return (source["kind"], source["hostId"], source["hostBuild"], source["callId"], window["clockId"])
    binding = observation["binding"]
    return (source["kind"], binding["executionId"], binding["planRevision"],
            observation["taskId"], observation["attemptId"], window["clockId"])


def _overlap(left, right):
    a, b = left["window"], right["window"]
    if (a["startMs"], a["endMs"]) == (b["startMs"], b["endMs"]):
        return True
    return (max(a["startMs"], b["startMs"]) < min(a["endMs"], b["endMs"])
            or a["startMs"] == a["endMs"] and b["startMs"] <= a["startMs"] < b["endMs"]
            or b["startMs"] == b["endMs"] and a["startMs"] <= b["startMs"] < a["endMs"])


def _store(value):
    data = contracts._object(value, "", ("schemaVersion", "generation", "enabled", "observations"))
    contracts._version(data)
    contracts._number(data["generation"], "/generation")
    if type(data["enabled"]) is not bool:
        raise ContractIssue("E_SCHEMA_TYPE", "/enabled", "expected boolean")
    known, previous = set(), []
    for supplied in contracts._array(data["observations"], "/observations"):
        row = contracts._object(supplied, "/observation", ("consentGeneration", "observation"))
        contracts._number(row["consentGeneration"], "/consentGeneration")
        observation = validate_observation(row["observation"])
        if row["consentGeneration"] > data["generation"] or observation["id"] in known:
            raise ContractIssue("E_TELEMETRY_STORE", "/", "invalid observation generation or duplicate identity")
        if any(_scope(observation) == _scope(old) and _overlap(observation, old) for old in previous):
            raise ContractIssue("E_TELEMETRY_WINDOW", "/", "stored observation windows overlap")
        known.add(observation["id"])
        previous.append(observation)
    return _copy(data)


def _read(root):
    potential = manager._safe(root, manager.lock_path(root).parent / "execution-telemetry.json")
    return _store(manager._read(telemetry_path(root))) if potential.exists() else None


def inspect_telemetry(project_root):
    root = manager._root(project_root)
    store = _read(root)
    return {**semantic_fields(), "enabled": bool(store and store["enabled"]),
            "storeDigest": None if store is None else state.digest(store), "store": store}


def configure_telemetry(project_root, policy, dry_run=False):
    policy = validate_telemetry_policy(policy)
    if type(dry_run) is not bool:
        raise ContractIssue("E_SCHEMA_TYPE", "/dryRun", "expected boolean")
    root = manager._root(project_root)
    if dry_run:
        return {**semantic_fields(), "dryRun": True, "policy": policy}
    telemetry_path(root)
    with manager._writer(root):
        if policy["enabled"]:
            manager._consent(root, enabled=True)
        previous = _read(root)
        store = {"schemaVersion": 1, "generation": 1 if previous is None else previous["generation"] + 1,
                 "enabled": policy["enabled"], "observations": [] if previous is None else previous["observations"]}
        manager._write(root, telemetry_path(root), _store(store))
    return {**semantic_fields(), "enabled": policy["enabled"], "storeDigest": state.digest(store)}


def _attribution(root, observation, inventory):
    binding = observation["binding"]
    record = manager._load(root, binding["executionId"])
    revision = next((item for item in record["revisions"] if item["plan"]["revision"] == binding["planRevision"]
                     and state.digest(item["plan"]) == binding["planDigest"]), None)
    if revision is None:
        raise ContractIssue("E_TELEMETRY_ATTRIBUTION", "/binding", "observation has no bound execution revision")
    planned = next((item for item in revision["plan"]["tasks"] if item["id"] == observation["taskId"]), None)
    if planned is None or planned["assignment"]["model"] != observation["requestedModel"] or not any(
        event["type"] == "TASK_STARTED" and event["taskId"] == observation["taskId"]
        and event["attemptId"] == observation["attemptId"] for event in revision["events"]
    ):
        raise ContractIssue("E_TELEMETRY_ATTRIBUTION", "/", "task, attempt or requested model differs")
    from native_execution import _metadata, _request_markers
    source = observation["source"]
    if source["kind"] == "manual-declaration":
        if inventory is not None or _request_markers(revision["events"], observation["taskId"], observation["attemptId"]):
            raise ContractIssue("E_TELEMETRY_ATTRIBUTION", "/", "manual declaration cannot replace a native observation")
        return
    matched = False
    for entry in _metadata(record):
        receipt = revision["receipts"].get(entry["resultId"])
        if receipt is not None and (receipt["result"]["taskId"], receipt["result"]["attemptId"]) == (
            observation["taskId"], observation["attemptId"]
        ) and all(entry[field] == source[field] for field in ("hostId", "hostBuild", "callId")):
            matched = True
    if not matched:
        raise ContractIssue("E_TELEMETRY_ATTRIBUTION", "/source", "no attributable native host receipt")
    if observation["observedModel"] is None:
        if inventory is not None:
            raise ContractIssue("E_TELEMETRY_ATTRIBUTION", "/inventory", "inventory cannot imply a missing observation")
        return
    if inventory is None:
        raise ContractIssue("E_TELEMETRY_ATTRIBUTION", "/inventory", "supplied inventory is required")
    inventory = controls.validate_inventory(inventory)
    model = next((item for item in inventory["models"] if item["id"] == observation["observedModel"]
                  and item["available"]), None)
    if model is None or inventory["source"] != "host-observation" or (
        inventory["hostId"], inventory["hostBuild"], state.digest(inventory)
    ) != (source["hostId"], source["hostBuild"], observation["inventoryDigest"]) or (
        model["pricing"] != observation["pricing"]
    ):
        raise ContractIssue("E_TELEMETRY_ATTRIBUTION", "/inventory", "observed model, price or snapshot differs")


def record_observation(project_root, observation, inventory=None):
    root = manager._root(project_root)
    current = _read(root)
    if current is None or not current["enabled"]:
        return {**semantic_fields(), "enabled": False, "recorded": False, "idempotent": False}
    with manager._writer(root):
        store = _read(root)
        if store is None or not store["enabled"]:
            return {**semantic_fields(), "enabled": False, "recorded": False, "idempotent": False}
        if store["generation"] != current["generation"]:
            raise ContractIssue("E_TELEMETRY_CONSENT", "/", "telemetry consent changed before capture")
        manager._consent(root, enabled=True)
        observation = validate_observation(observation)
        _attribution(root, observation, inventory)
        previous = next((item for item in store["observations"]
                         if item["observation"]["id"] == observation["id"]), None)
        if previous is not None:
            if previous["consentGeneration"] != store["generation"]:
                raise ContractIssue("E_TELEMETRY_CONSENT", "/", "old observation cannot renew consent")
            if previous["observation"] != observation:
                raise ContractIssue("E_TELEMETRY_DUPLICATE", "/", "observation identity conflicts")
            return {**semantic_fields(), "enabled": True, "recorded": False, "idempotent": True}
        if any(_scope(observation) == _scope(item["observation"]) and _overlap(observation, item["observation"])
               for item in store["observations"]):
            raise ContractIssue("E_TELEMETRY_WINDOW", "/", "observation window overlaps recorded usage")
        store["observations"].append({"consentGeneration": store["generation"], "observation": observation})
        manager._write(root, telemetry_path(root), _store(store))
    return {**semantic_fields(), "enabled": True, "recorded": True, "idempotent": False}


def delete_observations(project_root, expected_digest):
    contracts._digest(expected_digest, "/expectedDigest")
    with manager._writer(project_root) as root:
        store = _read(root)
        if store is None or state.digest(store) != expected_digest:
            raise ContractIssue("E_TELEMETRY_CONSENT", "/", "explicit current telemetry digest is required")
        store["observations"] = []
        store["generation"] += 1
        manager._write(root, telemetry_path(root), _store(store))
    return {**semantic_fields(), "enabled": store["enabled"], "storeDigest": state.digest(store)}
