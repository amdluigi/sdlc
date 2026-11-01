"""Escaped read-only Markdown/Mermaid views; no scheduling or readiness authority."""

import html
from datetime import datetime

from artifact_contracts import ContractIssue
import execution_state


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
    state = execution_state.replay_execution(
        revision["plan"], revision["events"], revision["receipts"],
        execution_state.digest(revision["consent"]), revision["acceptances"], revision["approvals"],
    )
    approved = bool(state["approved"] and inspected["policyDigest"] == state["policyDigest"])
    plan = revision["plan"]
    lines = [
        "# Execution " + _markdown(plan["executionId"]), "",
        "Mode: manual metadata recording only; no worker or command dispatch.",
        "Approval: " + ("recorded for current bindings" if approved else "pending approval or stale policy"),
        f"Plan revision: {plan['revision']}",
        "Plan digest: `" + execution_state.digest(plan) + "`",
        "Policy digest: " + _markdown(inspected["policyDigest"] or "unavailable"),
        "Writer lock: " + ("present; inspect before recovery" if inspected["writerLockPresent"] else "not present"),
        "", "Structural validation does not assess evidence quality, PR readiness, release or deployment.",
        "Acceptance is an explicit independent operator judgment, not worker self-certification.",
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
        if acceptance is not None and acceptance["resultId"] == result_id:
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
