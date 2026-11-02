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
    ) + (("maxBatchTasks", "maxBatchCalls", "maxBatchToolCalls", "maxBatchWallMs", "maxBatchInputBytes",
          "maxBatchOutputBytes") if isinstance(value, dict) and value.get("schemaVersion") == 3 else ()))
    batch = type(data["schemaVersion"]) is int and data["schemaVersion"] == 3
    if type(data["schemaVersion"]) is int and data["schemaVersion"] == 2:
        contracts._enum(data["mode"], "/mode", ("supervised",))
    elif not batch:
        contracts._version(data)
    if type(data["enabled"]) is not bool or type(data["allowEscalation"]) is not bool:
        raise ContractIssue("E_SCHEMA_TYPE", "/", "controls flags must be booleans")
    if batch and data["mode"] != "batch":
        raise ContractIssue("E_CONTROLS_CAPABILITY", "/mode", "version 3 requires explicit batch mode")
    contracts._enum(data["mode"], "/mode", ("batch",) if batch else ("manual", "supervised", "autonomous"))
    if contracts._number(data["maxAttempts"], "/maxAttempts") > contracts.MAX_ITEMS:
        raise ContractIssue("E_CONTROLS_LIMIT", "/maxAttempts", "attempt limit exceeds record capacity")
    _models(data["permittedModels"])
    if batch:
        limits = {
            "maxBatchTasks": contracts.MAX_ITEMS,
            "maxBatchCalls": contracts.MAX_ITEMS,
            "maxBatchToolCalls": contracts.MAX_ITEMS,
            "maxBatchWallMs": 300000,
            "maxBatchInputBytes": 262144,
            "maxBatchOutputBytes": 262144,
        }
        for field, ceiling in limits.items():
            if contracts._number(data[field], "/" + field) > ceiling:
                raise ContractIssue("E_CONTROLS_LIMIT", "/" + field, "batch bound exceeds the supported ceiling")
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


def _batch_approval_metadata(batch):
    return {
        "taskIds": [item["taskId"] for item in batch["tasks"]],
        "attempts": [{
            "taskId": item["taskId"], "attemptId": attempt["attemptId"], "role": item["role"],
            "modelId": attempt["modelId"], "briefDigest": state.digest(attempt["brief"]),
            "limits": _copy(attempt["limits"]),
        } for item in batch["tasks"] for attempt in item["attempts"]],
        "limits": _copy(batch["limits"]),
        "maxSpendMinor": None,
    }


def _store(value):
    version = value.get("schemaVersion") if isinstance(value, dict) else None
    supervised = type(version) is int and version == 2
    batch = type(version) is int and version == 3
    data = contracts._object(value, "", (
        "schemaVersion", "generation", "policy", "safetyActivated", "paused", "pauseReason", "approvals", "cancelRequests",
    ) + (("retainedManual",) if supervised else ()) +
        (("batchApprovals", "retainedPrevious") if batch else ()))
    if not supervised and not batch:
        contracts._version(data)
    contracts._number(data["generation"], "/generation")
    validate_controls_policy(data["policy"])
    if (data["policy"]["schemaVersion"], data["policy"]["mode"]) != (
        (3, "batch") if batch else (2, "supervised") if supervised else (1, "manual")
    ) or type(data["paused"]) is not bool or (
        type(data["safetyActivated"]) is not bool or data["policy"]["enabled"] and not data["safetyActivated"]
    ):
        raise ContractIssue("E_CONTROLS_STORE", "/", "unsupported controls state")
    if supervised and data["retainedManual"] is not None:
        if not isinstance(data["retainedManual"], dict) or data["retainedManual"].get("schemaVersion") != 1:
            raise ContractIssue("E_CONTROLS_STORE", "/", "retained manual controls must remain version 1")
        _store(data["retainedManual"])
    if batch:
        previous = data["retainedPrevious"]
        if previous is not None:
            if not isinstance(previous, dict) or previous.get("schemaVersion") not in (1, 2):
                raise ContractIssue("E_CONTROLS_STORE", "/retainedPrevious",
                                    "batch controls must retain the complete prior version 1 or 2 record")
            _store(previous)
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
    if batch:
        approvals = data["batchApprovals"]
        if not isinstance(approvals, dict) or len(approvals) > contracts.MAX_ITEMS:
            raise ContractIssue("E_CONTROLS_STORE", "/batchApprovals", "batch approvals must be bounded")
        for batch_id, approval in approvals.items():
            contracts._id(batch_id, "/batchApprovals")
            approval = contracts._object(approval, "/batchApprovals/" + batch_id, (
                "planDigest", "executionPolicyDigest", "controlsDigest", "batchDigest",
                "taskIds", "attempts", "limits", "maxSpendMinor",
            ))
            for key in ("planDigest", "executionPolicyDigest", "controlsDigest", "batchDigest"):
                digest = approval[key]
                contracts._digest(digest, "/batchApprovals/" + batch_id + "/" + key)
            task_ids = contracts._strings(approval["taskIds"], "/batchApprovals/" + batch_id + "/taskIds", True)
            for identifier in task_ids:
                contracts._id(identifier, "/batchApprovals/" + batch_id + "/taskIds")
            if len(set(task_ids)) != len(task_ids):
                raise ContractIssue("E_CONTROLS_STORE", "/batchApprovals/" + batch_id + "/taskIds",
                                    "batch task identities must be unique")
            attempt_specs = contracts._array(
                approval["attempts"], "/batchApprovals/" + batch_id + "/attempts", True
            )
            attempt_ids, attempt_tasks = set(), set()
            for spec in attempt_specs:
                spec = contracts._object(spec, "/batchApprovals/" + batch_id + "/attempts", (
                    "taskId", "attemptId", "role", "modelId", "briefDigest", "limits",
                ))
                contracts._id(spec["taskId"], "/batchApprovals/" + batch_id + "/attempts/taskId")
                contracts._id(spec["attemptId"], "/batchApprovals/" + batch_id + "/attempts/attemptId")
                contracts._enum(spec["role"], "/batchApprovals/" + batch_id + "/attempts/role",
                                ("architecture", "developer", "testing", "review"))
                _model_id(spec["modelId"])
                contracts._digest(spec["briefDigest"], "/batchApprovals/" + batch_id + "/attempts/briefDigest")
                if spec["attemptId"] in attempt_ids or spec["taskId"] not in task_ids:
                    raise ContractIssue("E_CONTROLS_STORE", "/batchApprovals/" + batch_id + "/attempts",
                                        "attempt metadata must be unique and reference an approved task")
                attempt_ids.add(spec["attemptId"])
                attempt_tasks.add(spec["taskId"])
                attempt_limits = contracts._object(spec["limits"], "/batchApprovals/attempts/limits", (
                    "maxIterations", "maxToolCalls", "maxInputBytes", "maxOutputBytes", "maxWallMs",
                ))
                attempt_ceilings = {
                    "maxIterations": 16, "maxToolCalls": 32, "maxInputBytes": 262144,
                    "maxOutputBytes": 262144, "maxWallMs": 300000,
                }
                if any(contracts._number(attempt_limits[key], "/batchApprovals/attempts/limits/" + key, 1)
                       > ceiling for key, ceiling in attempt_ceilings.items()):
                    raise ContractIssue("E_CONTROLS_STORE", "/batchApprovals/" + batch_id + "/attempts/limits",
                                        "per-attempt limits exceed supported bounds")
            limits = contracts._object(
                approval["limits"], "/batchApprovals/" + batch_id + "/limits",
                ("maxCalls", "maxToolCalls", "maxWallMs", "maxInputBytes", "maxOutputBytes"),
            )
            for key, bound in limits.items():
                contracts._number(bound, "/batchApprovals/" + batch_id + "/limits/" + key, 1)
            ceilings = {
                "maxCalls": contracts.MAX_ITEMS, "maxToolCalls": contracts.MAX_ITEMS,
                "maxWallMs": 300000, "maxInputBytes": 262144, "maxOutputBytes": 262144,
            }
            if any(limits[key] > ceiling for key, ceiling in ceilings.items()):
                raise ContractIssue("E_CONTROLS_STORE", "/batchApprovals/" + batch_id + "/limits",
                                    "batch approval limits exceed supported bounds")
            if approval["maxSpendMinor"] is not None:
                raise ContractIssue("E_CONTROLS_STORE", "/batchApprovals/" + batch_id,
                                    "authoritative spend limits are unavailable")
            if not task_ids or not attempt_specs or attempt_tasks != set(task_ids):
                raise ContractIssue("E_CONTROLS_STORE", "/batchApprovals/" + batch_id,
                                    "batch approval metadata must retain its finite identities")
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
    if policy["schemaVersion"] == 2 and policy["mode"] != "supervised":
        raise ContractIssue("E_CONTROLS_CAPABILITY", "/mode", "version 2 requires supervised mode")
    if policy["schemaVersion"] == 3 and policy["mode"] != "batch":
        raise ContractIssue("E_CONTROLS_CAPABILITY", "/mode", "version 3 requires explicit batch mode")
    root = manager._root(project_root)
    if dry_run:
        return {**semantic_fields(), "dryRun": True, "policy": policy}
    controls_path(root)
    with manager._writer(root):
        if policy["enabled"]:
            manager._consent(root, enabled=True)
        previous = _read(root)
        if previous is not None and previous["schemaVersion"] > policy["schemaVersion"]:
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
            **({"batchApprovals": {}, "retainedPrevious": (
                previous.get("retainedPrevious") if previous and previous["schemaVersion"] == 3 else previous
            )} if policy["schemaVersion"] == 3 else {}),
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
                                    "batchScheduling": bool(store and store["schemaVersion"] == 3
                                                            and store["policy"]["enabled"]),
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


def approve_batch(project_root, batch, plan_digest, execution_policy_digest, controls_digest, batch_digest):
    for value in (plan_digest, execution_policy_digest, controls_digest, batch_digest):
        contracts._digest(value, "/batchApproval")
    from execution_orchestration import batch_digest as digest_batch, validate_batch_contract
    batch = validate_batch_contract(batch)
    if batch["maxSpendMinor"] is not None:
        raise ContractIssue("E_ORCHESTRATION_SPEND_UNAVAILABLE", "/maxSpendMinor",
                            "authoritative provider usage and pricing are unavailable")
    if digest_batch(batch, plan_digest, execution_policy_digest, controls_digest) != batch_digest:
        raise ContractIssue("E_ORCHESTRATION_APPROVAL", "/batchDigest", "batch approval digest differs")
    with manager._writer(project_root) as root:
        store = _active(root)
        if store["schemaVersion"] != 3 or not store["policy"]["enabled"]:
            raise ContractIssue("E_CONTROLS_CAPABILITY", "/", "version 3 batch controls are required")
        current = manager.inspect_execution(root, batch["executionId"])
        expected = {
            "planDigest": current["planDigest"],
            "executionPolicyDigest": current["policyDigest"],
            "controlsDigest": _digest(store),
        }
        if (
            batch["planRevision"] != current["plan"]["revision"]
            or not current["state"]["approved"]
            or expected != {
                "planDigest": plan_digest,
                "executionPolicyDigest": execution_policy_digest,
                "controlsDigest": controls_digest,
            }
            or store["approvals"].get(batch["executionId"]) != expected
        ):
            raise ContractIssue("E_ORCHESTRATION_APPROVAL", "/", "batch policy or plan approval is stale")
        store["batchApprovals"][batch["batchId"]] = {
            **expected, "batchDigest": batch_digest, **_batch_approval_metadata(batch),
        }
        manager._write(root, controls_path(root), _store(store))
    return {**semantic_fields(), "batchId": batch["batchId"], "batchDigest": batch_digest}


def batch_approval(root, batch):
    store = _active(root)
    if store["schemaVersion"] != 3:
        raise ContractIssue("E_CONTROLS_CAPABILITY", "/", "version 3 batch controls are required")
    approval = store["batchApprovals"].get(batch["batchId"])
    current = manager.inspect_execution(root, batch["executionId"])
    if approval is None:
        raise ContractIssue("E_ORCHESTRATION_APPROVAL", "/", "exact batch consent is required")
    expected = {
        "planDigest": current["planDigest"],
        "executionPolicyDigest": current["policyDigest"],
        "controlsDigest": _digest(store),
        "batchDigest": approval["batchDigest"],
        **_batch_approval_metadata(batch),
    }
    if (
        approval != expected
        or batch["planRevision"] != current["plan"]["revision"]
        or not current["state"]["approved"]
        or store["approvals"].get(batch["executionId"]) != {
            key: expected[key] for key in ("planDigest", "executionPolicyDigest", "controlsDigest")
        }
    ):
        raise ContractIssue("E_ORCHESTRATION_APPROVAL", "/", "batch approval bindings are stale")
    from execution_orchestration import batch_digest as digest_batch
    if digest_batch(
        batch, expected["planDigest"], expected["executionPolicyDigest"], expected["controlsDigest"]
    ) != expected["batchDigest"]:
        raise ContractIssue("E_ORCHESTRATION_APPROVAL", "/batchDigest", "batch digest changed")
    return approval


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


def enforce_start(root, execution_id, task_id, attempt_id, native=False, bounded=False, batch=None):
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
    batch_dispatch = bool(
        native and bounded and batch is not None and store["schemaVersion"] == 3
        and store["policy"]["mode"] == "batch"
    )
    if native and not (bounded and store["policy"]["mode"] == "supervised") and not batch_dispatch:
        raise ContractIssue("E_CONTROLS_CAPABILITY", "/", "manual controls do not qualify native dispatch")
    if batch_dispatch:
        batch_approval(root, batch)
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
