#!/usr/bin/env python3
"""Fixed, allowlisted bridge from the native dashboard to the local manager."""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "sdlc" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import execution_controls as controls
import execution_manager as manager
import execution_renderers as renderers
import execution_state as state
from artifact_contracts import ContractIssue

MAX_BYTES = 1024 * 1024


def _input():
    raw = sys.stdin.buffer.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ContractIssue("E_DASHBOARD_INPUT", "/", "dashboard request exceeds its size bound")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite number")),
        )
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ContractIssue("E_DASHBOARD_INPUT", "/", "invalid dashboard request") from error
    if not isinstance(value, dict):
        raise ContractIssue("E_DASHBOARD_INPUT", "/", "dashboard request must be an object")
    return value


def _digest(value):
    return state.digest(value)


def _interval(start, end):
    if start is None or end is None:
        return None
    try:
        left = datetime.fromisoformat(start.replace("Z", "+00:00"))
        right = datetime.fromisoformat(end.replace("Z", "+00:00"))
        value = int((right - left).total_seconds() * 1000)
        return value if value >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def live_view(root, execution_id):
    current = manager.inspect_execution(root, execution_id)
    controls_view = controls.inspect_controls(root)
    plan = current["plan"]
    tasks_by_id = current["state"]["tasks"]
    events = current["events"]
    counts = {name: 0 for name in (
        "waiting", "ready", "running", "blocked", "reported", "accepted", "failed", "cancelled",
    )}
    tasks = []
    for planned in plan["tasks"]:
        status = tasks_by_id[planned["id"]]
        counts[status["status"]] += 1
        task_events = [event for event in events if event["taskId"] == planned["id"]]
        started = next((event["recordedAt"] for event in task_events if event["type"] == "TASK_STARTED"), None)
        ended = next((event["recordedAt"] for event in reversed(task_events) if event["type"] in (
            "TASK_RESULT_RECEIVED", "TASK_FAILED", "TASK_CANCELLED",
        )), None)
        model = planned["assignment"]["model"]
        if model is None:
            for event in task_events:
                message = event["payload"].get("message", "")
                if message.startswith("native-batch:"):
                    try:
                        model = json.loads(message[len("native-batch:"):])["modelId"]
                    except (ValueError, KeyError, TypeError):
                        model = None
        receipt = current["receipts"].get(status["resultId"]) if status["resultId"] else None
        acceptance_version = None
        if status["status"] == "reported" and receipt is not None:
            acceptance_version = 2 if set(receipt) == {"briefDigest", "resultScope", "result"} else 1
        tasks.append({
            "id": planned["id"], "title": planned["title"], "status": status["status"],
            "attemptId": status["attemptId"], "resultId": status["resultId"],
            "resultDigest": None if receipt is None else _digest(receipt["result"]),
            "acceptanceSchemaVersion": acceptance_version,
            "acceptanceBasis": state.acceptance_basis(status),
            "reportedStatus": status["reportedStatus"], "estimateMs": planned["estimateMs"],
            "recordedIntervalMs": _interval(started, ended), "requestedModel": model,
            "prerequisites": planned["prerequisites"],
            "acceptanceCriteria": planned["acceptanceCriteria"],
        })
    control_store = controls_view["store"]
    expected = {
        "planDigest": current["planDigest"], "executionPolicyDigest": current["policyDigest"],
        "controlsDigest": controls_view["controlsDigest"],
    }
    active_approval = None if control_store is None else control_store["approvals"].get(execution_id)
    pending = [] if control_store is None else [
        item for item in control_store["cancelRequests"]
        if item["binding"]["executionId"] == execution_id and item["status"] == "pending"
    ]
    unresolved = controls.reconcile_execution(root, execution_id)["unknownNativeAttempts"]
    view = {
        "schemaVersion": 2, "kind": "sdlc-live-execution-view",
        "binding": {
            "executionId": execution_id, "planRevision": plan["revision"],
            "planDigest": current["planDigest"],
        },
        "planDigest": current["planDigest"], "policyDigest": current["policyDigest"],
        "controlsDigest": controls_view["controlsDigest"],
        "controlsStateDigest": None if control_store is None else state.digest(control_store),
        "planApproved": current["state"]["approved"],
        "writerLockPresent": current["writerLockPresent"],
        "controls": {
            "enabled": controls_view["enabled"], "paused": controls_view["paused"],
            "autonomous": bool(controls_view["runtimeCapabilities"]["autonomous"]),
            "controlsApproved": active_approval == expected,
            "pendingCancellationCount": len(pending), "unknownNativeAttemptCount": len(unresolved),
            "hostCancellation": "unavailable", "spendEnforcement": False,
        },
        "progress": {"total": len(tasks), **counts},
        "tasks": tasks,
        "context": current["context"],
        "gantt": renderers.build_gantt(plan, current["state"], events),
        "events": [{
            "sequence": event["sequence"], "type": event["type"], "taskId": event["taskId"],
            "attemptId": event["attemptId"], "recordedAt": event["recordedAt"],
        } for event in events],
    }
    view["snapshotDigest"] = _digest(view)
    return view


def _expected(value):
    fields = (
        "executionId", "planRevision", "planDigest", "policyDigest", "controlsDigest", "controlsStateDigest",
    )
    expected = value.get("expectedBinding")
    if not isinstance(expected, dict) or set(expected) != set(fields):
        raise ContractIssue("E_DASHBOARD_BINDING", "/expectedBinding", "exact live-view binding is required")
    return expected


def _confirm(value, operation, expected):
    fields = {"operation": operation, "expectedBinding": expected}
    if operation == "accept":
        fields["acceptance"] = value.get("acceptance")
    elif operation == "cancel":
        fields["taskId"] = value.get("taskId")
        fields["attemptId"] = value.get("attemptId")
    elif operation == "update-context":
        fields["context"] = value.get("context")
    if value.get("confirmationDigest") != _digest(fields):
        raise ContractIssue("E_DASHBOARD_CONFIRMATION", "/confirmationDigest",
                            "explicit confirmation must bind the exact live-view action")


def run(value):
    allowed = {
        "list", "inspect", "approve-plan", "approve-controls", "accept", "pause", "resume", "cancel",
        "update-context",
    }
    operation = value.get("operation")
    if operation not in allowed:
        raise ContractIssue("E_DASHBOARD_OPERATION", "/operation", "unsupported dashboard operation")
    fields = {"operation", "projectRoot"}
    if operation != "list":
        fields.add("executionId")
    if operation not in ("list", "inspect"):
        fields.update(("expectedBinding", "confirmationDigest"))
        if operation == "accept":
            fields.add("acceptance")
        if operation == "cancel":
            fields.update(("taskId", "attemptId"))
        if operation == "update-context":
            fields.add("context")
    if set(value) != fields:
        raise ContractIssue("E_DASHBOARD_INPUT", "/", "dashboard request fields do not match the operation")
    project_root = value.get("projectRoot")
    if not isinstance(project_root, str) or not Path(project_root).is_absolute():
        raise ContractIssue("E_DASHBOARD_PATH", "/projectRoot", "select an absolute local project path")
    if os.name == "nt" and (
        not re.match(r"^[A-Za-z]:\\", project_root) or ":" in project_root[2:]
    ):
        raise ContractIssue("E_DASHBOARD_PATH", "/projectRoot", "network and alternate-stream paths are unsupported")
    root = manager._root(project_root)
    if operation == "list":
        results = []
        for execution_id in manager._record_ids(root):
            current = manager.inspect_execution(root, execution_id)
            results.append({
                "executionId": execution_id, "revision": current["plan"]["revision"],
                "planDigest": current["planDigest"],
                "counts": live_view(root, execution_id)["progress"],
            })
        return {"operation": operation, "executions": results}

    execution_id = value.get("executionId")
    if not isinstance(execution_id, str):
        raise ContractIssue("E_DASHBOARD_BINDING", "/executionId", "execution identity is required")
    if operation == "inspect":
        return {"operation": operation, "view": live_view(root, execution_id)}

    expected = _expected(value)
    if expected["executionId"] != execution_id:
        raise ContractIssue("E_DASHBOARD_BINDING", "/expectedBinding/executionId",
                            "selected execution differs from live-view binding")
    _confirm(value, operation, expected)
    current = manager.inspect_execution(root, execution_id)
    if expected["planRevision"] != current["plan"]["revision"] or (
        expected["planDigest"] != current["planDigest"] or expected["policyDigest"] != current["policyDigest"]
    ):
        raise ContractIssue("E_EXECUTION_STALE_VIEW", "/expectedBinding", "live manager view is stale")
    if operation == "approve-plan":
        manager.approve_plan(root, execution_id, expected["planDigest"], expected["policyDigest"],
                             expected_binding=expected)
    elif operation == "approve-controls":
        if expected["controlsDigest"] is None:
            raise ContractIssue("E_CONTROLS_DISABLED", "/", "execution controls are not configured")
        controls.approve_controls(
            root, execution_id, expected["planDigest"], expected["policyDigest"], expected["controlsDigest"],
            expected_binding=expected,
        )
    elif operation == "accept":
        manager.accept_task(root, execution_id, value.get("acceptance"), expected_binding=expected)
    elif operation in ("pause", "resume"):
        if expected["controlsDigest"] is None:
            raise ContractIssue("E_CONTROLS_DISABLED", "/", "execution controls are not configured")
        controls.set_pause(
            root, operation == "pause", "Explicit dashboard pause" if operation == "pause"
            else "Explicit dashboard resume", expected_controls_digest=expected["controlsDigest"],
            expected_binding=expected,
        )
    elif operation == "cancel":
        cancellation_binding = {
            **expected, "taskId": value.get("taskId"), "attemptId": value.get("attemptId"),
        }
        controls.request_cancel(
            root, execution_id, value.get("taskId"), "Explicit dashboard cancellation intent",
            expected_binding=cancellation_binding,
        )
    elif operation == "update-context":
        context = value.get("context")
        if not isinstance(context, dict) or set(context) != {
            "scope", "agentId", "content", "expectedRevision",
        }:
            raise ContractIssue("E_DASHBOARD_CONTEXT", "/context", "context update fields do not match")
        manager.update_context(
            root, execution_id, context["scope"], context["agentId"], context["content"],
            expected["planDigest"], context["expectedRevision"], expected_binding=expected,
        )
    return {"operation": operation, "view": live_view(root, execution_id)}


def main():
    try:
        result = run(_input())
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        if len(encoded.encode("utf-8")) > MAX_BYTES:
            raise ContractIssue("E_DASHBOARD_OUTPUT", "/", "manager response exceeds its size bound")
        sys.stdout.write(encoded + "\n")
    except ContractIssue as error:
        sys.stderr.write(error.code + "\n")
        raise SystemExit(2)
    except Exception:
        sys.stderr.write("E_DASHBOARD_UNAVAILABLE\n")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
