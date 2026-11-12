#!/usr/bin/env python3
"""Read-only, explicit-input efficiency baseline tooling. No provider calls."""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "sdlc" / "scripts"))

from artifact_contracts import ContractIssue, strict_load_json
import execution_contracts as contracts
from execution_state import digest


RUBRIC = ("correctness", "verification", "security", "scope")
TOKEN_FIELDS = ("providerInputTokens", "providerOutputTokens", "cachedInputTokens",
                "billableInputTokens", "billableOutputTokens")
REQUEST_STATES = ("prepared", "dispatched", "completed", "interrupted", "unknown")
OUTCOMES = ("completed", "failed", "interrupted", "unknown")
MANIFEST_FIELDS = ("schemaVersion", "kind", "id", "sourceRevision", "configurationDigest",
                   "requestedModel", "effectiveModel", "hostVersion", "repetitions",
                   "maxAttempts", "maxRequestsPerAttempt", "tasks")
OBSERVATION_FIELDS = ("schemaVersion", "kind", "manifestDigest", "evidenceKind",
                      "usageSource", "usageEvidenceDigest", "attempts")
ATTEMPT_FIELDS = ("taskId", "repetition", "attempt", "attemptId", "producerId", "outcome",
                  "elapsedMs", "toolCalls", "handoffs", "quality", "requests")
REQUEST_FIELDS = ("id", "state", "adapterInvoked", "inputBytes", "outputBytes",
                  *TOKEN_FIELDS, "authoritativeCost")


def _issue(code, pointer, message):
    raise ContractIssue("E_BASELINE_" + code, pointer, message)


def _bounded(value, pointer, maximum):
    contracts._number(value, pointer)
    if value > maximum:
        _issue("LIMIT", pointer, "value exceeds the cohort limit")
    return value


def _header(value, kind, fields):
    contracts._object(value, "/", fields)
    if type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1:
        _issue("VERSION", "/schemaVersion", "unsupported version")
    if value["kind"] != kind:
        _issue("KIND", "/kind", "unexpected artifact kind")


def _total(values):
    return contracts._number(sum(values), "/totals", 0)


def validate_manifest(value):
    _header(value, "sdlc-efficiency-manifest", MANIFEST_FIELDS)
    contracts._id(value["id"], "/id")
    revision = contracts._text(value["sourceRevision"], "/sourceRevision", 64)
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", revision):
        _issue("REVISION", "/sourceRevision", "expected an immutable Git revision")
    contracts._digest(value["configurationDigest"], "/configurationDigest")
    contracts._id(value["requestedModel"], "/requestedModel")
    if value["effectiveModel"] is not None:
        contracts._id(value["effectiveModel"], "/effectiveModel")
    host = contracts._text(value["hostVersion"], "/hostVersion", 64)
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", host):
        _issue("HOST", "/hostVersion", "expected a bounded version label")
    repetitions = _bounded(value["repetitions"], "/repetitions", 10)
    attempts = _bounded(value["maxAttempts"], "/maxAttempts", 4)
    _bounded(value["maxRequestsPerAttempt"], "/maxRequestsPerAttempt", 32)
    tasks = contracts._array(value["tasks"], "/tasks", nonempty=True)
    seen = set()
    for index, task in enumerate(tasks):
        pointer = f"/tasks/{index}"
        contracts._object(task, pointer, ("id", "objective", "permittedActions",
                                        "acceptanceCriteria", "verification", "rubric"))
        task_id = contracts._id(task["id"], pointer + "/id")
        if task_id in seen:
            _issue("DUPLICATE", pointer, "duplicate task")
        seen.add(task_id)
        contracts._text(task["objective"], pointer + "/objective", 512)
        for field in ("permittedActions", "acceptanceCriteria", "verification", "rubric"):
            items = contracts._array(task[field], pointer + "/" + field, nonempty=True)
            for item in items:
                contracts._text(item, pointer + "/" + field, 512)
            if len(set(items)) != len(items):
                _issue("DUPLICATE", pointer + "/" + field, "duplicate entry")
        if not set(task["permittedActions"]) <= {"read", "search", "edit", "execute"}:
            _issue("ACTIONS", pointer + "/permittedActions", "unsupported action")
        if set(task["rubric"]) != set(RUBRIC):
            _issue("RUBRIC", pointer + "/rubric", "all four rubric dimensions are required")
    planned = len(tasks) * repetitions
    if planned * attempts > contracts.MAX_ITEMS:
        _issue("LIMIT", "/tasks", "cohort exceeds the bounded observation capacity")
    return {"schemaVersion": 1, "kind": "sdlc-efficiency-manifest-validation",
            "manifestId": value["id"], "manifestDigest": digest(value),
            "plannedRepetitions": planned, "plannedAttemptsMaximum": planned * attempts}


def _quality(value, producer, pointer):
    if value is None:
        return "missing"
    contracts._object(value, pointer, ("reviewerId", "evidenceDigest", "criteria"))
    reviewer = contracts._id(value["reviewerId"], pointer + "/reviewerId")
    if reviewer == producer:
        _issue("SELF_REVIEW", pointer, "producer cannot be the declared reviewer")
    contracts._digest(value["evidenceDigest"], pointer + "/evidenceDigest")
    criteria = contracts._object(value["criteria"], pointer + "/criteria", RUBRIC)
    for verdict in criteria.values():
        contracts._enum(verdict, pointer + "/criteria", ("passed", "failed", "unavailable"))
    if "failed" in criteria.values():
        return "declaredFailed"
    return "unavailable" if "unavailable" in criteria.values() else "declaredPassed"


def _requests(values, maximum, usage_available, pointer):
    requests = contracts._array(values, pointer)
    if len(requests) > maximum:
        _issue("LIMIT", pointer, "request count exceeds the manifest bound")
    seen = set()
    for index, item in enumerate(requests):
        path = f"{pointer}/{index}"
        contracts._object(item, path, REQUEST_FIELDS)
        request_id = contracts._id(item["id"], path + "/id")
        if request_id in seen:
            _issue("DUPLICATE", path, "duplicate request inside attempt")
        seen.add(request_id)
        status = contracts._enum(item["state"], path + "/state", REQUEST_STATES)
        invoked = item["adapterInvoked"]
        if invoked is not None and type(invoked) is not bool:
            _issue("INVOCATION", path, "expected true, false or null")
        if status == "prepared" and invoked is not False:
            _issue("LIFECYCLE", path, "prepared request cannot claim invocation")
        if status in ("dispatched", "completed") and invoked is not True:
            _issue("LIFECYCLE", path, "dispatch or completion requires observed invocation")
        contracts._number(item["inputBytes"], path + "/inputBytes", 0)
        contracts._number(item["outputBytes"], path + "/outputBytes", 0)
        if invoked is not True and item["outputBytes"] != 0:
            _issue("LIFECYCLE", path, "output requires observed invocation")
        for field in TOKEN_FIELDS:
            if item[field] is not None:
                contracts._number(item[field], path + "/" + field, 0)
                if invoked is not True or not usage_available:
                    _issue("USAGE", path, "usage requires invocation and source provenance")
        if item["authoritativeCost"] is not None:
            _issue("COST", path, "billing authentication is unavailable")
    return requests


def _summarize(attempts, planned_repetitions, evidence, usage_available):
    requests = [request for attempt in attempts for request in attempt["requests"]]
    repetitions = {(item["taskId"], item["repetition"]) for item in attempts}
    outcomes = {status: sum(item["outcome"] == status for item in attempts) for status in OUTCOMES}
    quality = dict.fromkeys(("declaredPassed", "declaredFailed", "missing", "unavailable"), 0)
    for attempt in attempts:
        quality[_quality(attempt["quality"], attempt["producerId"], "/quality")] += 1
    request_counts = {status: sum(item["state"] == status for item in requests)
                      for status in REQUEST_STATES}
    invoked = [item for item in requests if item["adapterInvoked"] is True]
    unknown_invocations = sum(item["adapterInvoked"] is None for item in requests)
    accounting = {
        "observedModelCalls": len(invoked), "unknownInvocations": unknown_invocations,
        "observedInputBytes": _total(item["inputBytes"] for item in invoked),
        "totalInputBytes": None if unknown_invocations else _total(item["inputBytes"] for item in invoked),
        "observedOutputBytes": _total(item["outputBytes"] for item in requests),
        "toolCalls": _total(item["toolCalls"] for item in attempts),
        "attemptElapsedMs": _total(item["elapsedMs"] for item in attempts),
        "endToEndElapsedMs": None,
        "observedHandoffs": _total(item["handoffs"] for item in attempts if item["handoffs"] is not None),
        "handoffsComplete": bool(attempts) and all(item["handoffs"] is not None for item in attempts),
        "authoritativeCost": None,
    }
    for field in TOKEN_FIELDS:
        complete = (usage_available and bool(invoked) and not unknown_invocations
                    and all(item[field] is not None for item in invoked))
        accounting[field] = _total(item[field] for item in invoked) if complete else None
    missing = planned_repetitions - len(repetitions)
    partial = (bool(missing) or bool(unknown_invocations) or outcomes["unknown"] > 0
               or request_counts["unknown"] > 0 or request_counts["dispatched"] > 0
               or request_counts["prepared"] > 0 or quality["missing"] > 0
               or quality["unavailable"] > 0
               or accounting["providerInputTokens"] is None
               or accounting["providerOutputTokens"] is None)
    return {
        "measurementStatus": ("synthetic" if evidence == "synthetic" else
                              "partial-recorded-unverified" if partial else "recorded-unverified"),
        "coverage": {"plannedRepetitions": planned_repetitions,
                     "observedRepetitions": len(repetitions),
                     "missingRepetitions": missing, "observedAttempts": len(attempts),
                     "observedRetries": sum(item["attempt"] > 1 for item in attempts)},
        "outcomes": outcomes, "requests": request_counts, "accounting": accounting, "quality": quality,
    }


def report(manifest, observations):
    validated = validate_manifest(manifest)
    _header(observations, "sdlc-efficiency-observations", OBSERVATION_FIELDS)
    contracts._digest(observations["manifestDigest"], "/manifestDigest")
    if observations["manifestDigest"] != validated["manifestDigest"]:
        _issue("BINDING", "/manifestDigest", "observations bind a different manifest")
    evidence = contracts._enum(observations["evidenceKind"], "/evidenceKind",
                               ("synthetic", "recorded"))
    usage_source = contracts._enum(observations["usageSource"], "/usageSource",
                                   ("unavailable", "caller-reported"))
    usage_available = usage_source == "caller-reported"
    if usage_available:
        contracts._digest(observations["usageEvidenceDigest"], "/usageEvidenceDigest")
    elif observations["usageEvidenceDigest"] is not None:
        _issue("USAGE", "/usageEvidenceDigest", "unavailable usage has no evidence binding")
    tasks = {task["id"] for task in manifest["tasks"]}
    attempts = contracts._array(observations["attempts"], "/attempts")
    identities, attempt_ids, repetitions = set(), set(), set()
    for index, attempt in enumerate(attempts):
        path = f"/attempts/{index}"
        contracts._object(attempt, path, ATTEMPT_FIELDS)
        task = contracts._id(attempt["taskId"], path + "/taskId")
        if task not in tasks:
            _issue("BINDING", path, "task is not in the manifest")
        repetition = _bounded(attempt["repetition"], path + "/repetition", manifest["repetitions"])
        ordinal = _bounded(attempt["attempt"], path + "/attempt", manifest["maxAttempts"])
        attempt_id = contracts._id(attempt["attemptId"], path + "/attemptId")
        identity = (task, repetition, ordinal)
        if identity in identities or attempt_id in attempt_ids:
            _issue("DUPLICATE", path, "duplicate attempt identity")
        identities.add(identity)
        attempt_ids.add(attempt_id)
        repetitions.add((task, repetition))
        producer = contracts._id(attempt["producerId"], path + "/producerId")
        contracts._enum(attempt["outcome"], path + "/outcome", OUTCOMES)
        for field in ("elapsedMs", "toolCalls"):
            contracts._number(attempt[field], path + "/" + field, 0)
        if attempt["handoffs"] is not None:
            contracts._number(attempt["handoffs"], path + "/handoffs", 0)
        _quality(attempt["quality"], producer, path + "/quality")
        _requests(attempt["requests"], manifest["maxRequestsPerAttempt"],
                  usage_available, path + "/requests")
    for task, repetition in repetitions:
        ordinals = {ordinal for found_task, found_repetition, ordinal in identities
                    if (found_task, found_repetition) == (task, repetition)}
        if ordinals != set(range(1, max(ordinals) + 1)):
            _issue("MISSING_ATTEMPT", "/attempts", "retry is missing preceding attempt accounting")
    task_results = []
    for task in manifest["tasks"]:
        selected = [item for item in attempts if item["taskId"] == task["id"]]
        rows = [{"repetition": repetition,
                 **_summarize([item for item in selected if item["repetition"] == repetition],
                              1, evidence, usage_available)}
                for repetition in range(1, manifest["repetitions"] + 1)]
        task_results.append({"taskId": task["id"],
                             **_summarize(selected, manifest["repetitions"], evidence, usage_available),
                             "repetitions": rows})
    return {
        "schemaVersion": 1, "kind": "sdlc-efficiency-report",
        "manifestId": manifest["id"], "manifestDigest": validated["manifestDigest"],
        "observationsDigest": digest(observations), "sourceRevision": manifest["sourceRevision"],
        "configurationDigest": manifest["configurationDigest"],
        "evidenceKind": evidence, "evidenceVerification": "not-assessed",
        "usageSource": usage_source, "usageEvidenceDigest": observations["usageEvidenceDigest"],
        **_summarize(attempts, validated["plannedRepetitions"], evidence, usage_available),
        "tasks": task_results,
        "claims": {"tokenSavings": None, "costSavings": None,
                   "qualityNonRegression": None, "managerAcceptance": False},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-manifest")
    validate.add_argument("--input", required=True)
    summarize = commands.add_parser("report")
    summarize.add_argument("--manifest", required=True)
    summarize.add_argument("--observations", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-manifest":
            output = validate_manifest(strict_load_json(args.input))
        else:
            output = report(strict_load_json(args.manifest), strict_load_json(args.observations))
        print(contracts._encoded(output))
        return 0
    except ContractIssue as error:
        print(f"error[{error.code}] /: invalid baseline input; no report produced", file=sys.stderr)
        return error.exit_code
    except RecursionError:
        print("error[E_BASELINE_JSON] /: JSON nesting exceeds supported depth", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
