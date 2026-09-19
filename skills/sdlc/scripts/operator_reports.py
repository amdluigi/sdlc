"""Read-only projections of a caller-supplied SDLC coverage ledger."""

from artifact_contracts import (
    ContractIssue,
    ID_PATTERN,
    require_array,
    require_object,
    require_string,
    require_string_array,
    semantic_fields,
)


FACTS = (
    "nonTrivial", "beforeCompletion", "bugOrUnexplainedFailure", "newCapability",
    "userOrProductFacing", "significantInternalCapability",
    "codeOrConfigurationChange", "newOrChangedBehavior", "verificationInScope",
    "securitySurfaceAffected", "operationalSurfaceAffected",
    "learningSignalPresent", "coreUpgrade",
)
SOURCES = ("core", "project-extension", "global-extension")
PROVIDER_TYPES = ("bundled", "disabled", "replacement")
TRIGGERS = ("matched", "not-matched", "undetermined")
EVIDENCE = (
    "satisfied", "partial", "missing", "stale/unverified",
    "configured-disabled", "not-applicable",
)
INSTRUCTION = (
    "would-load", "loaded", "reused", "skipped", "blocked", "undetermined"
)
EXTENSION_DIGEST = __import__("re").compile(r"^sha256:[0-9a-f]{64}$")


def _bool_fact(facts, name):
    value = facts.get(name)
    return value if type(value) is bool else None


def _tri_or(left, right):
    if left is True or right is True:
        return True
    if left is False and right is False:
        return False
    return None


def _tri_and(left, right):
    if left is False or right is False:
        return False
    if left is True and right is True:
        return True
    return None


def deterministic_core_trigger(module_id, task):
    facts = task["facts"]
    rigor = task["rigor"]
    if module_id in ("project-memory", "project-standards", "change-contract"):
        return "matched"
    rules = {
        "prd": lambda: _tri_and(
            _bool_fact(facts, "newCapability"),
            _tri_or(
                _bool_fact(facts, "userOrProductFacing")
                , _bool_fact(facts, "significantInternalCapability")
            ),
        ),
        "debugging": lambda: _bool_fact(facts, "bugOrUnexplainedFailure"),
        "planning": lambda: rigor in ("standard", "significant"),
        "tdd": lambda: _bool_fact(facts, "newOrChangedBehavior"),
        "implementation": lambda: _bool_fact(facts, "codeOrConfigurationChange"),
        "testing": lambda: _bool_fact(facts, "verificationInScope"),
        "security-auth": lambda: _bool_fact(facts, "securitySurfaceAffected"),
        "operational-readiness": lambda: _bool_fact(facts, "operationalSurfaceAffected"),
        "review": lambda: _bool_fact(facts, "beforeCompletion"),
        "pr-handoff": lambda: _bool_fact(facts, "beforeCompletion"),
        "continuous-improvement": lambda: _tri_or(
            _bool_fact(facts, "learningSignalPresent"),
            _bool_fact(facts, "coreUpgrade"),
        ),
    }
    if module_id not in rules:
        return "undetermined"
    try:
        result = rules[module_id]()
    except (KeyError, TypeError):
        return "undetermined"
    if result is True:
        return "matched"
    if result is False:
        return "not-matched"
    return "undetermined"


def validate_operator_state(data):
    require_object(
        data, "",
        ("schemaVersion", "task", "modules", "configuredDisabledModules", "blockers"),
    )
    if data["schemaVersion"] != 1:
        raise ContractIssue("E_SCHEMA_VERSION", "/schemaVersion", "expected 1")
    task = require_object(data["task"], "/task", ("id", "rigor", "facts"))
    if not isinstance(task["id"], str) or not ID_PATTERN.fullmatch(task["id"]):
        raise ContractIssue("E_TASK_ID", "/task/id", "expected kebab-case ID")
    if task["rigor"] not in ("trivial", "standard", "significant"):
        raise ContractIssue("E_TASK_RIGOR", "/task/rigor", "invalid rigor")
    facts = require_object(task["facts"], "/task/facts", FACTS, required=())
    for name, value in facts.items():
        if type(value) is not bool:
            raise ContractIssue("E_TASK_FACT", f"/task/facts/{name}", "expected boolean")

    ids = set()
    previous_order = -1
    disabled = []
    for index, module in enumerate(require_array(data["modules"], "/modules")):
        pointer = f"/modules/{index}"
        allowed = (
            "id", "source", "order", "configured", "trigger", "evidence",
            "instruction", "contentDigest", "sources", "provider",
        )
        require_object(
            module, pointer, allowed,
            required=("id", "source", "order", "configured", "trigger", "evidence", "instruction"),
        )
        module_id = module["id"]
        if not isinstance(module_id, str) or not ID_PATTERN.fullmatch(module_id):
            raise ContractIssue("E_MODULE_ID", f"{pointer}/id", "expected kebab-case ID")
        if module_id in ids:
            raise ContractIssue("E_MODULE_DUPLICATE", f"{pointer}/id", f"duplicate module {module_id}")
        ids.add(module_id)
        if module["source"] not in SOURCES:
            raise ContractIssue("E_MODULE_SOURCE", f"{pointer}/source", "invalid source")
        if type(module["order"]) is not int or module["order"] < 0:
            raise ContractIssue("E_MODULE_ORDER", f"{pointer}/order", "expected non-negative integer")
        if module["order"] <= previous_order:
            raise ContractIssue("E_MODULE_ORDER", f"{pointer}/order", "modules must be in ascending unique order")
        previous_order = module["order"]
        if module["configured"] not in ("enabled", "disabled"):
            raise ContractIssue("E_MODULE_CONFIGURED", f"{pointer}/configured", "invalid configured state")
        if module["source"] != "core":
            if "provider" in module:
                raise ContractIssue(
                    "E_MODULE_FIELD", f"{pointer}/provider",
                    "provider descriptor is valid only for core modules",
                )
        else:
            if "provider" in module:
                provider = module["provider"]
                provider = require_object(
                    provider, f"{pointer}/provider", ("type", "id"),
                    required=("type",),
                )
                provider_type = provider["type"]
                if provider_type not in PROVIDER_TYPES:
                    raise ContractIssue(
                        "E_PROVIDER_TYPE", f"{pointer}/provider/type",
                        "expected bundled, disabled, or replacement",
                    )
                if provider_type == "replacement":
                    provider_id = provider.get("id")
                    if (
                        not isinstance(provider_id, str)
                        or len(provider_id) > 64
                        or not ID_PATTERN.fullmatch(provider_id)
                    ):
                        raise ContractIssue(
                            "E_PROVIDER_ID", f"{pointer}/provider/id",
                            "replacement requires an exact kebab-case provider ID",
                        )
                elif "id" in provider:
                    raise ContractIssue(
                        "E_PROVIDER_ID", f"{pointer}/provider/id",
                        f"{provider_type} provider must not include an ID",
                    )
                if (
                    module["configured"] == "disabled"
                    and provider_type != "disabled"
                ) or (
                    module["configured"] == "enabled"
                    and provider_type == "disabled"
                ):
                    raise ContractIssue(
                        "E_PROVIDER_CONFIGURED", f"{pointer}/provider/type",
                        "provider type conflicts with configured state",
                    )

        trigger = require_object(
            module["trigger"], f"{pointer}/trigger", ("state", "basis", "assertedBy")
        )
        if trigger["state"] not in TRIGGERS:
            raise ContractIssue("E_TRIGGER_STATE", f"{pointer}/trigger/state", "invalid trigger state")
        require_string_array(trigger["basis"], f"{pointer}/trigger/basis")
        if trigger["assertedBy"] not in ("deterministic-core-rule", "runtime"):
            raise ContractIssue("E_TRIGGER_ASSERTION", f"{pointer}/trigger/assertedBy", "invalid assertion source")
        if (
            module["source"] != "core"
            and trigger["assertedBy"] != "runtime"
        ):
            raise ContractIssue(
                "E_TRIGGER_ASSERTION",
                f"{pointer}/trigger/assertedBy",
                "extension triggers must be asserted by runtime",
            )
        if module["source"] == "core":
            calculated = deterministic_core_trigger(module_id, task)
            if calculated != "undetermined" and calculated != trigger["state"]:
                raise ContractIssue(
                    "E_TRIGGER_CONFLICT", f"{pointer}/trigger/state",
                    f"conflicts with deterministic result {calculated}",
                )

        evidence = require_object(
            module["evidence"], f"{pointer}/evidence", ("status", "items", "gaps")
        )
        if evidence["status"] not in EVIDENCE:
            raise ContractIssue("E_EVIDENCE_STATUS", f"{pointer}/evidence/status", "invalid evidence status")
        for item_index, item in enumerate(require_array(evidence["items"], f"{pointer}/evidence/items")):
            item_pointer = f"{pointer}/evidence/items/{item_index}"
            require_object(item, item_pointer, ("kind", "reference", "summary", "current"))
            for name in ("kind", "reference", "summary"):
                require_string(item[name], f"{item_pointer}/{name}", substantive=True)
            if type(item["current"]) is not bool:
                raise ContractIssue("E_EVIDENCE_CURRENT", f"{item_pointer}/current", "expected boolean")
        require_string_array(evidence["gaps"], f"{pointer}/evidence/gaps", substantive=True)

        instruction = require_object(
            module["instruction"], f"{pointer}/instruction", ("state", "reason")
        )
        if instruction["state"] not in INSTRUCTION:
            raise ContractIssue("E_INSTRUCTION_STATE", f"{pointer}/instruction/state", "invalid instruction state")
        require_string(instruction["reason"], f"{pointer}/instruction/reason", substantive=True)
        if module["configured"] == "disabled":
            disabled.append(module_id)
            if evidence["status"] != "configured-disabled" or instruction["state"] != "skipped":
                raise ContractIssue("E_STATE_CONSISTENCY", pointer, "disabled module must be configured-disabled and skipped")
        elif evidence["status"] == "configured-disabled":
            raise ContractIssue("E_STATE_CONSISTENCY", f"{pointer}/evidence/status", "enabled module cannot be configured-disabled")
        if evidence["status"] == "satisfied" and instruction["state"] not in ("reused", "skipped"):
            raise ContractIssue("E_STATE_CONSISTENCY", pointer, "satisfied evidence must be reused or skipped")
        if instruction["state"] == "would-load" and not (
            module["configured"] == "enabled"
            and trigger["state"] == "matched"
            and evidence["status"] in ("partial", "missing", "stale/unverified")
        ):
            raise ContractIssue("E_STATE_CONSISTENCY", pointer, "would-load state is inconsistent")
        if module["source"] != "core" and module["configured"] == "enabled":
            digest = module.get("contentDigest")
            if not isinstance(digest, str) or not EXTENSION_DIGEST.fullmatch(digest):
                raise ContractIssue("E_EXTENSION_DIGEST", f"{pointer}/contentDigest", "expected sha256 digest")
            require_string_array(module.get("sources"), f"{pointer}/sources", nonempty=True)
    declared_disabled = require_string_array(
        data["configuredDisabledModules"], "/configuredDisabledModules"
    )
    if declared_disabled != disabled:
        raise ContractIssue(
            "E_DISABLED_MISMATCH", "/configuredDisabledModules",
            "must exactly match disabled modules in module order",
        )
    blockers = require_array(data["blockers"], "/blockers")
    for index, blocker in enumerate(blockers):
        pointer = f"/blockers/{index}"
        require_object(blocker, pointer, ("module", "message"))
        if blocker["module"] not in ids:
            raise ContractIssue("E_BLOCKER_MODULE", f"{pointer}/module", "unknown module")
        require_string(blocker["message"], f"{pointer}/message", substantive=True)
    return data


def _provider_descriptor(module):
    provider = module.get("provider")
    if provider is not None:
        return dict(provider)
    return {
        "type": "disabled" if module["configured"] == "disabled" else "bundled"
    }


def _would_load(module):
    if module["configured"] == "disabled":
        return False
    trigger = module["trigger"]["state"]
    status = module["evidence"]["status"]
    if trigger == "undetermined":
        return None
    if status not in EVIDENCE:
        return None
    if trigger == "not-matched" or status in (
        "satisfied", "configured-disabled", "not-applicable"
    ):
        return False
    if status in ("partial", "missing", "stale/unverified"):
        return True if trigger == "matched" else False
    return None


def _reason_rows(module):
    trigger = module["trigger"]["state"]
    status = module["evidence"]["status"]
    return [
        (
            "Enabled by project configuration"
            if module["configured"] == "enabled"
            else "Disabled by project configuration"
        ),
        {
            "matched": "Trigger matched the supplied task facts",
            "not-matched": "Trigger did not match the supplied task facts",
            "undetermined": "Trigger remains undetermined from the supplied facts",
        }[trigger],
        (
            f"Evidence was supplied as {status}"
            if status != "configured-disabled"
            else "Runtime supplied the configured-disabled evidence state"
        ),
        f"Runtime supplied instruction state {module['instruction']['state']}: {module['instruction']['reason']}",
    ]


def build_report(data, command, detail="normal"):
    if command not in ("explain", "preview", "render-coverage"):
        raise ContractIssue("E_COMMAND", "/command", "unsupported report command", 2)
    if detail not in ("concise", "normal", "detailed"):
        raise ContractIssue("E_DETAIL", "/detail", "invalid detail", 2)
    state = validate_operator_state(data)
    blockers_by_module = {}
    for blocker in state["blockers"]:
        blockers_by_module.setdefault(blocker["module"], []).append(blocker["message"])
    result_modules = []
    for module in state["modules"]:
        module_blockers = blockers_by_module.get(module["id"], [])
        if command in ("explain", "preview"):
            reasons = _reason_rows(module)
            projected = {
                "id": module["id"],
                "source": module["source"],
                "configured": module["configured"],
                "triggered": (
                    True if module["trigger"]["state"] == "matched"
                    else False if module["trigger"]["state"] == "not-matched"
                    else None
                ),
                "evidenceStatus": module["evidence"]["status"],
                "instructionState": module["instruction"]["state"],
                "reasons": reasons[:1] if detail == "concise" else reasons,
                "blockers": module_blockers,
            }
            if module["source"] == "core":
                projected["provider"] = _provider_descriptor(module)
            if command == "preview":
                projected["wouldLoad"] = _would_load(module)
            if detail == "detailed":
                projected["evidenceItems"] = module["evidence"]["items"]
                projected["gaps"] = module["evidence"]["gaps"]
                projected["triggerBasis"] = module["trigger"]["basis"]
                for name in ("contentDigest", "sources"):
                    if name in module:
                        projected[name] = module[name]
        else:
            evidence = [
                item["summary"] for item in module["evidence"]["items"]
            ] + list(module["evidence"]["gaps"])
            if not evidence:
                evidence = [f"Runtime supplied status {module['evidence']['status']}"]
            projected = {
                "id": module["id"],
                "source": module["source"],
                "status": module["evidence"]["status"],
                "recognizedEvidenceOrGap": (
                    evidence if detail != "normal" else evidence[:1]
                ),
                "action": module["instruction"]["state"],
                "blockers": module_blockers,
            }
            if module["source"] == "core":
                projected["provider"] = _provider_descriptor(module)
            if detail == "detailed":
                projected.update(
                    {
                        "configured": module["configured"],
                        "triggerBasis": module["trigger"]["basis"],
                        "reasons": _reason_rows(module),
                        "evidenceItems": module["evidence"]["items"],
                        "gaps": module["evidence"]["gaps"],
                    }
                )
                for name in ("contentDigest", "sources"):
                    if name in module:
                        projected[name] = module[name]
        result_modules.append(projected)
    return {
        "schemaVersion": 1,
        "command": command,
        "valid": True,
        "result": {
            "taskId": state["task"]["id"],
            "detail": detail,
            "modules": result_modules,
            "configuredDisabledModules": state["configuredDisabledModules"],
            "blockers": state["blockers"],
            "semanticApproval": semantic_fields()["semanticApproval"],
        },
    }
