"""Escaped read-only Markdown/Mermaid views; no scheduling or readiness authority."""

import html
from datetime import datetime

from artifact_contracts import ContractIssue
import execution_contracts as contracts
import execution_state

MAX_SIGNED_INTEGER = 2**63 - 1


def _timestamp(value):
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return None


def build_gantt(plan, task_state=None, events=None):
    plan = contracts.validate_execution_plan(plan)["data"]
    projected = execution_state.initial_execution_state(plan) if task_state is None else task_state
    expected_ids = {task["id"] for task in plan["tasks"]}
    tasks_by_id = None
    proposed = task_state is None
    if isinstance(projected, dict):
        tasks_by_id = projected if set(projected) == expected_ids else projected.get("tasks")
        proposed = proposed or (
            tasks_by_id is not None and not projected.get("approved", True) and
            all(item.get("status") == "waiting" for item in tasks_by_id.values())
        )
    if not isinstance(tasks_by_id, dict) or set(tasks_by_id) != expected_ids:
        raise ContractIssue("E_EXECUTION_GANTT", "/tasks", "execution state does not match the Gantt plan")
    planned_overflow = False
    planned_start = {}
    planned_end = {}
    pending = set(expected_ids)
    while pending:
        ready = [
            task for task in plan["tasks"]
            if task["id"] in pending and all(identifier in planned_end for identifier in task["prerequisites"])
        ]
        if not ready:
            raise ContractIssue("E_EXECUTION_GANTT", "/tasks", "plan dependencies cannot be ordered")
        for task in ready:
            dependencies = [planned_end[identifier] for identifier in task["prerequisites"]]
            start = None if any(value is None for value in dependencies) else max(dependencies, default=0)
            estimate = task["estimateMs"]
            end = None if start is None or estimate is None else start + estimate
            if end is not None and end > MAX_SIGNED_INTEGER:
                end = None
                planned_overflow = True
            planned_start[task["id"]] = start
            planned_end[task["id"]] = end
            pending.remove(task["id"])

    rows = []
    for task in plan["tasks"]:
        current = tasks_by_id[task["id"]]
        rows.append({
            "id": task["id"], "title": task["title"], "agent": task["assignment"]["agent"],
            "status": "proposed" if proposed else current["status"],
            "executionMode": task["execution"]["mode"], "executionGroup": task["execution"]["group"],
            "prerequisites": task["prerequisites"], "estimateMs": task["estimateMs"],
            "plannedStartMs": planned_start[task["id"]], "plannedEndMs": planned_end[task["id"]],
            "actualStartedAt": current.get("startedAt"), "actualEndedAt": current.get("endedAt"),
            "actualDurationMs": None,
        })

    for row in rows:
        if events is None:
            continue
        matching = [event for event in events if event["taskId"] == row["id"] and
                    event["attemptId"] == tasks_by_id[row["id"]].get("attemptId")]
        starts_for_attempt = [event["recordedAt"] for event in matching if event["type"] == "TASK_STARTED"]
        ends_for_attempt = [event["recordedAt"] for event in matching if event["type"] in (
            "TASK_RESULT_RECEIVED", "TASK_FAILED", "TASK_CANCELLED",
        )]
        if starts_for_attempt:
            row["actualStartedAt"] = starts_for_attempt[0]
        if ends_for_attempt:
            row["actualEndedAt"] = ends_for_attempt[-1]

    starts = [_timestamp(row["actualStartedAt"]) for row in rows]
    starts = [value for value in starts if value is not None]
    origin = min(starts) if starts else None
    for row in rows:
        started = _timestamp(row["actualStartedAt"])
        ended = _timestamp(row["actualEndedAt"])
        if origin is not None and started is not None:
            row["actualStartOffsetMs"] = int((started - origin).total_seconds() * 1000)
        else:
            row["actualStartOffsetMs"] = None
        if started is not None and ended is not None and ended >= started:
            row["actualDurationMs"] = int((ended - started).total_seconds() * 1000)
        row.pop("actualStartedAt")
        row.pop("actualEndedAt")

    known_ends = [value for value in planned_end.values() if value is not None]
    actual_ends = [
        row["actualStartOffsetMs"] + row["actualDurationMs"]
        for row in rows
        if row["actualStartOffsetMs"] is not None and row["actualDurationMs"] is not None
    ]
    return {
        "schemaVersion": 1, "kind": "sdlc-project-gantt", "executionId": plan["executionId"],
        "planRevision": plan["revision"], "plannedDurationMs": max(known_ends, default=None),
        "plannedComplete": all(value is not None for value in planned_end.values()),
        "plannedBasis": (
            "declared estimates and dependencies only; no resource schedule or calendar forecast" +
            ("; relative offsets beyond signed 64-bit range are shown as incomplete" if planned_overflow else "")
        ),
        "actualOrigin": None if origin is None else origin.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "actualDurationMs": max(actual_ends, default=None),
        "actualBasis": "manager event timestamps; not host execution timing",
        "tasks": rows,
    }


def _bar(start, end, scale):
    if start is None or end is None or scale is None:
        return "unknown"
    if scale <= 0:
        return "*"
    left = min(39, int(start * 40 / scale))
    right = min(40, max(left + 1, int(end * 40 / scale)))
    return "." * left + "#" * (right - left) + "." * (40 - right)


def render_gantt(plan, task_state=None, events=None):
    gantt = build_gantt(plan, task_state, events)
    lines = [
        "# Project Gantt", "",
        f"Execution: {_markdown(gantt['executionId'])}; plan revision: {gantt['planRevision']}",
        "Planned bars use relative estimates and dependencies only; they are not calendar or resource forecasts.",
        "Actual bars use manager event timestamps, not host timing. Missing values remain unknown.",
        "", "| Activity | Specialist | State | Planned estimate | Planned bar | Actual interval | Actual bar | Depends on |",
        "|----------|------------|-------|------------------|-------------|-----------------|------------|------------|",
    ]
    for row in gantt["tasks"]:
        estimate = "unknown" if row["estimateMs"] is None else f"{row['estimateMs']} ms"
        planned = _bar(row["plannedStartMs"], row["plannedEndMs"], gantt["plannedDurationMs"])
        actual_end = (
            None if row["actualDurationMs"] is None or row["actualStartOffsetMs"] is None
            else row["actualStartOffsetMs"] + row["actualDurationMs"]
        )
        actual = _bar(row["actualStartOffsetMs"], actual_end, gantt["actualDurationMs"])
        interval = "unknown"
        if row["actualStartOffsetMs"] is not None:
            interval = (
                "in progress" if row["actualDurationMs"] is None
                else f"{row['actualDurationMs']} ms from manager events"
            )
        values = (
            row["title"], row["agent"], row["status"], estimate, planned, interval, actual,
            ", ".join(row["prerequisites"]) or "none",
        )
        lines.append("| " + " | ".join(_markdown(value) for value in values) + " |")
    if not gantt["plannedComplete"]:
        lines += ["", "Planned schedule is incomplete because one or more estimates or dependency offsets are unknown."]
    if gantt["actualOrigin"] is None:
        lines += ["", "Actual interval: unknown because no task start event is recorded."]
    return "\n".join(lines)


def _markdown(value):
    text = html.escape(str(value), quote=True)
    for char in "\\|`[]()!*_":
        text = text.replace(char, "&#" + str(ord(char)) + ";")
    return text


def _mermaid(value):
    return "".join(char if char.isascii() and (char.isalnum() or char in " _.-")
                   else "#" + str(ord(char)) + ";" for char in str(value))


def _dependency_bound(tasks):
    by_id = {task["id"]: task for task in tasks}
    memo = {}

    def length(identifier):
        if identifier not in memo:
            task = by_id[identifier]
            previous = max((length(parent) for parent in task["prerequisites"]), default=0)
            memo[identifier] = previous + (task["estimateMs"] if task["estimateMs"] is not None else 0)
        return memo[identifier]

    known = [task for task in tasks if task["estimateMs"] is not None]
    if not known:
        return "unavailable; incomplete because all task estimates are unavailable"
    value = max(length(task["id"]) for task in tasks)
    if len(known) != len(tasks):
        return f"{value} ms known lower bound; incomplete because some estimates are unavailable"
    return f"{value} ms from declared estimates; incomplete scheduling model (dependencies only)"


def render_execution(inspected):
    if not isinstance(inspected, dict) or "record" not in inspected:
        raise ContractIssue("E_SCHEMA_REQUIRED", "/", "report requires an inspected execution record")
    record = execution_state.validate_record(inspected["record"])
    revision = record["revisions"][-1]
    state = execution_state.replay_record_revision(record["schemaVersion"], revision)
    approved = bool(state["approved"] and inspected["policyDigest"] == state["policyDigest"])
    plan = revision["plan"]
    lines = [
        "# Execution " + _markdown(plan["executionId"]), "",
        ("Mode: manual metadata recording only; no worker or command dispatch." if record["schemaVersion"] == 1
         else "Mode: manager-recorded controller metadata; this report does not dispatch workers or commands."),
        "Approval: " + ("recorded for current bindings" if approved else "pending approval or stale policy"),
        f"Plan revision: {plan['revision']}",
        "Plan digest: `" + execution_state.digest(plan) + "`",
        "Policy digest: " + _markdown(inspected["policyDigest"] or "unavailable"),
        "Writer lock: " + ("present; inspect before recovery" if inspected["writerLockPresent"] else "not present"),
        "", "Structural validation does not assess evidence quality, PR readiness, release or deployment.",
        "Acceptance is an explicit independent operator judgment, not worker self-certification.",
        "", "## Gantt", "",
        render_gantt(plan, state["tasks"], revision["events"]),
        "", "## Tasks", "",
        "| Task | Title | State | Attempt | Reported outcome | Estimate (declared) | Recorded interval |",
        "|------|-------|-------|---------|------------------|---------------------|-------------------|",
    ]
    for task in plan["tasks"]:
        current = state["tasks"][task["id"]]
        estimate = "unavailable" if task["estimateMs"] is None else f"{task['estimateMs']} ms"
        interval = "unavailable"
        if current["startedAt"] and current["endedAt"]:
            start = datetime.strptime(current["startedAt"], "%Y-%m-%dT%H:%M:%SZ")
            end = datetime.strptime(current["endedAt"], "%Y-%m-%dT%H:%M:%SZ")
            interval = f"{int((end - start).total_seconds())} s (manager event interval, not host timing)"
        values = (task["id"], task["title"], current["status"], current["attemptId"] or "unavailable",
                  current["reportedStatus"] or "unavailable", estimate, interval)
        lines.append("| " + " | ".join(_markdown(value) for value in values) + " |")
    lines += ["", "## Dependency view", "", "Critical-path view: " + _dependency_bound(plan["tasks"]),
              "No wall-clock forecast, resource-aware schedule or host timing is inferred.",
              "", "```mermaid", "flowchart TD"]
    node_ids = {task["id"]: f"n{index}" for index, task in enumerate(plan["tasks"])}
    for task in plan["tasks"]:
        label = f"{task['id']}: {task['title']} ({state['tasks'][task['id']]['status']})"
        lines.append(f'  {node_ids[task["id"]]}["{_mermaid(label)}"]')
        for parent in task["prerequisites"]:
            lines.append(f'  {node_ids[parent]} --> {node_ids[task["id"]]}')
    lines += ["```", "", "## Retained evidence", ""]
    for result_id, receipt in revision["receipts"].items():
        result = receipt["result"]
        lines.append("### " + _markdown(result_id) + " (" + _markdown(result["status"]) + ")")
        for verification in result["verification"]:
            lines.append("- " + _markdown(verification["acceptanceCriterion"]) + ": "
                         + _markdown(verification["result"]) + "; revision "
                         + _markdown(verification["revision"] or "unavailable") + "; "
                         + _markdown(verification["summary"]))
        for field in ("findings", "blockers"):
            for value in result[field]:
                lines.append("- " + field + ": " + _markdown(value))
        current = state["tasks"][result["taskId"]]
        acceptance = current["acceptance"]
        if acceptance is not None and acceptance["resultId"] == result_id and acceptance["schemaVersion"] == 2:
            lines.append("- Independent operator validation (acceptance schema 2): " + _markdown(acceptance["summary"])
                         + "; checked revision " + _markdown(acceptance["revision"])
                         + "; operator command " + _markdown(acceptance["command"])
                         + "; bound result digest " + _markdown(acceptance["resultDigest"])
                         + "; worker verification is not treated as passed")
        elif acceptance is not None and acceptance["resultId"] == result_id:
            lines.append("- Independent judgment: " + _markdown(acceptance["summary"])
                         + "; checked revision " + _markdown(acceptance["revision"])
                         + "; controller command " + _markdown(acceptance["command"]))
    if not revision["receipts"]:
        lines.append("No receipts recorded; evidence is unavailable.")
    lines += ["", "## Recorded blockers and decisions", ""]
    for event in revision["events"]:
        if "reason" in event["payload"]:
            lines.append("- " + _markdown(event["type"]) + " "
                         + _markdown(event["taskId"] or "execution") + ": "
                         + _markdown(event["payload"]["reason"]))
    lines += ["", "## Recovery", "",
              "Unfinished manual attempts remain unresolved. Inspection never redispatches work or steals locks.",
              "Retention is manual; no automatic export, pruning, telemetry or policy adoption.", ""]
    return "\n".join(lines)
