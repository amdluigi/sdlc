"""Pure task-aware model planning; proposals never approve or dispatch work."""

import json

from artifact_contracts import ContractIssue
import execution_contracts as contracts
import execution_controls as controls
import execution_orchestration as orchestration
import execution_state as state


def _copy(value):
    return json.loads(contracts._encoded(value))


def _capacity(value, pointer):
    if contracts._number(value, pointer) > 3:
        raise ContractIssue("E_ROUTING_CAPACITY", pointer, "capacity must be between 1 and 3")
    return value


def validate_routing_policy(value):
    data = contracts._object(value, "", (
        "schemaVersion", "kind", "permittedModels", "models", "profiles",
    ))
    contracts._version(data)
    contracts._enum(data["kind"], "/kind", ("sdlc-model-routing-policy",))
    permitted = controls._models(data["permittedModels"])
    models = {}
    for raw in contracts._array(data["models"], "/models"):
        model = contracts._object(raw, "/models", ("id", "capacity", "costRank"))
        identifier = controls._model_id(model["id"])
        if identifier in models:
            raise ContractIssue("E_ROUTING_DUPLICATE", "/models", "duplicate model identity")
        _capacity(model["capacity"], "/models/capacity")
        contracts._number(model["costRank"], "/models/costRank", 0)
        models[identifier] = model
    if not set(permitted) <= models.keys():
        raise ContractIssue("E_ROUTING_MODEL", "/permittedModels", "model declaration is missing")
    profiles = set()
    for raw in contracts._array(data["profiles"], "/profiles"):
        profile = contracts._object(raw, "/profiles", ("id", "minimumCapacity", "candidates"))
        identifier = contracts._id(profile["id"], "/profiles/id")
        if identifier in profiles:
            raise ContractIssue("E_ROUTING_DUPLICATE", "/profiles", "duplicate profile identity")
        profiles.add(identifier)
        _capacity(profile["minimumCapacity"], "/profiles/minimumCapacity")
        if not set(controls._models(profile["candidates"])) <= models.keys():
            raise ContractIssue("E_ROUTING_MODEL", "/profiles/candidates", "model declaration is missing")
    return _copy(data)


def _shape_capacity(task):
    paths = len(task["ownership"])
    criteria = len(task["acceptanceCriteria"])
    prerequisites = len(task["prerequisites"])
    if paths >= 4 or criteria >= 4 or prerequisites >= 2:
        return 3
    return 2 if paths or prerequisites or criteria > 1 else 1


def propose_routing(plan, batch, inventory, policy):
    plan = contracts.validate_execution_plan(plan)["data"]
    batch = orchestration.validate_batch_contract(batch)
    inventory = controls.validate_inventory(inventory)
    policy = validate_routing_policy(policy)
    if (batch["executionId"], batch["planRevision"]) != (plan["executionId"], plan["revision"]):
        raise ContractIssue("E_ROUTING_BINDING", "/", "batch and supplied plan differ")
    if batch["maxSpendMinor"] is not None:
        raise ContractIssue("E_ORCHESTRATION_SPEND_UNAVAILABLE", "/maxSpendMinor",
                            "authoritative provider usage and pricing are unavailable")
    if sum(len(item["attempts"]) for item in batch["tasks"]) > contracts.MAX_ITEMS:
        raise ContractIssue("E_ROUTING_LIMIT", "/tasks", "routing attempt count exceeds the supported bound")
    tasks = {item["id"]: item for item in plan["tasks"]}
    profiles = {item["id"]: item for item in policy["profiles"]}
    models = {item["id"]: item for item in policy["models"]}
    available = {item["id"] for item in inventory["models"] if item["available"]}
    decisions = []
    for item in batch["tasks"]:
        task = tasks.get(item["taskId"])
        if task is None:
            raise ContractIssue("E_ROUTING_BINDING", "/tasks", "batch task is absent from the plan")
        if task["assignment"]["agent"].casefold() not in (item["role"], "sdlc-" + item["role"]):
            raise ContractIssue("E_NATIVE_ROLE", "/tasks/role", "role differs from the plan assignment")
        profile = profiles.get(task["assignment"]["modelProfile"])
        if profile is None:
            raise ContractIssue("E_ROUTING_PROFILE", "/profiles", "task model profile is missing")
        shape = _shape_capacity(task)
        required = max(shape, profile["minimumCapacity"])
        candidates = set(profile["candidates"]) & set(policy["permittedModels"]) & available
        suitable = [models[name] for name in candidates if models[name]["capacity"] >= required]
        suitable.sort(key=lambda model: (model["costRank"], model["id"]))
        current = None
        for index, attempt in enumerate(item["attempts"]):
            contracts.validate_task_brief(attempt["brief"], plan)
            if "execute" in attempt["brief"]["allowedActions"]:
                raise ContractIssue("E_ORCHESTRATION_UNSUPPORTED", "/tasks/attempts",
                                    "batch attempts do not authorize process execution")
            pinned = task["assignment"]["model"] if index == 0 else None
            if pinned is not None:
                controls.resolve_model(inventory, {
                    "id": profile["id"], "candidates": profile["candidates"],
                }, policy["permittedModels"], pinned)
                current = models[pinned]
                if current["capacity"] < required:
                    raise ContractIssue("E_ROUTING_CAPACITY", "/tasks",
                                        "explicit model is below the required declared capacity")
                reason = "explicit-model"
            elif current is None:
                if not suitable:
                    raise ContractIssue("E_MODEL_UNAVAILABLE", "/tasks", "no suitable available permitted model")
                current, reason = suitable[0], "lowest-ranked-suitable"
            else:
                stronger = [model for model in suitable if model["capacity"] > current["capacity"]]
                if stronger:
                    current, reason = stronger[0], "stronger-fallback"
                else:
                    reason = "same-model-retry"
            controls.resolve_model(inventory, {
                "id": profile["id"], "candidates": profile["candidates"],
            }, policy["permittedModels"], current["id"])
            decisions.append({
                "taskId": task["id"], "attemptId": attempt["attemptId"], "profileId": profile["id"],
                "modelId": current["id"], "shapeCapacity": shape, "requiredCapacity": required,
                "costRank": current["costRank"], "reason": reason,
            })
    proposal = {
        "schemaVersion": 1, "kind": "sdlc-model-routing-proposal", "active": False,
        "planDigest": state.digest(plan), "batchDigest": state.digest(batch),
        "inventoryDigest": state.digest(inventory), "policyDigest": state.digest(policy),
        "decisions": decisions,
    }
    return {**proposal, "proposalDigest": state.digest(proposal)}


def materialize_routing(plan, batch, inventory, policy, proposal):
    expected = propose_routing(plan, batch, inventory, policy)
    if contracts._encoded(proposal) != contracts._encoded(expected):
        raise ContractIssue("E_ROUTING_PROPOSAL", "/", "proposal differs from the bound inputs or derived choices")
    output = orchestration.validate_batch_contract(batch)
    selected = {(item["taskId"], item["attemptId"]): item["modelId"] for item in expected["decisions"]}
    for item in output["tasks"]:
        for attempt in item["attempts"]:
            attempt["modelId"] = selected[(item["taskId"], attempt["attemptId"])]
    return orchestration.validate_batch_contract(output)
