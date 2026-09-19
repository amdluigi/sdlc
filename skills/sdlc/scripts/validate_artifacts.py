#!/usr/bin/env python3

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath

sys.dont_write_bytecode = True

from artifact_contracts import (
    ContractIssue,
    NOTICE,
    semantic_fields,
    strict_load_json,
    validate_handoff_model,
    URL_LIKE,
)
from operator_reports import build_report
from handoff_renderers import (
    apply_template,
    metadata_json,
    read_template,
    render_handoff,
    result_envelope,
    write_output,
)
from reconcile_artifacts import validate_reconciliation


# Deprecated import compatibility; all violations now carry ContractIssue data.
ContractError = ContractIssue


PRD_SECTIONS = (
    "Problem and context",
    "Target users and benefit",
    "Outcome",
    "Goals",
    "Non-goals",
    "User scenarios",
    "Functional requirements",
    "Acceptance criteria",
    "Data, permissions, privacy, and security",
    "Constraints and dependencies",
    "Success measures",
    "Open decisions",
    "Approval",
)
PLAN_COLUMNS = (
    "Task",
    "PRD refs",
    "Outcome",
    "Prerequisites",
    "Consumes",
    "Produces",
    "Execution",
    "Verification",
)
PLACEHOLDER = re.compile(
    r"^(?:tbd|todo|none provided|not approved|draft|n/?a)$",
    re.IGNORECASE,
)
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REF_PATTERN = re.compile(r"\b(?:FR|AC)-[1-9][0-9]*\b")
FR_DEFINITION = re.compile(
    r"^\s*[-*]\s+\*\*(FR-[1-9][0-9]*)\*\*:\s*(.+?)\s*$",
    re.MULTILINE,
)
AC_DEFINITION = re.compile(
    r"^\s*[-*]\s+\*\*(AC-[1-9][0-9]*)\*\*\s*"
    r"\(([^)]*)\):\s*(.+?)\s*$",
    re.MULTILINE,
)


def _read_text(path):
    path = Path(path)
    if str(path) == "-" or URL_LIKE.match(str(path)):
        raise ContractIssue(
            "E_LOCAL_PATH", str(path), "expected a local filesystem path", 2
        )
    try:
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ContractIssue(
                "E_INPUT_TOO_LARGE",
                str(path),
                "input exceeds 2097152 bytes",
                2,
            )
    except OSError as error:
        raise ContractIssue(
            "E_INPUT_READ", str(path), "cannot read local file", 2
        ) from error
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeError as error:
        raise ContractIssue(
            "E_UTF8", str(path), "input is not valid UTF-8", 2
        ) from error
    except OSError as error:
        raise ContractIssue(
            "E_INPUT_READ", str(path), "cannot read local file", 2
        ) from error


def _frontmatter(text, source):
    if not text.startswith("---\n"):
        raise ContractError(f"{source}: missing frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ContractError(f"{source}: unterminated frontmatter")
    values = {}
    for line_number, line in enumerate(text[4:end].splitlines(), 2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([a-z][a-z0-9-]*):\s*(.*?)\s*", line)
        if match is None:
            raise ContractError(
                f"{source}:{line_number}: frontmatter must use scalar key/value fields"
            )
        key, value = match.groups()
        if key in values:
            raise ContractError(f"{source}: duplicate frontmatter field {key}")
        values[key] = value.strip("\"'")
    return values, text[end + 5 :]


def _sections(body):
    matches = list(re.finditer(r"^## ([^\r\n]+)\s*$", body, re.MULTILINE))
    result = {}
    for index, match in enumerate(matches):
        name = match.group(1)
        if name in result:
            raise ContractError(f"duplicate section: {name}")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        result[name] = body[match.end() : end].strip()
    return result


def _require_content(value, label, errors):
    if not value or PLACEHOLDER.fullmatch(value.strip()):
        errors.append(f"{label} must contain substantive content")


def _number_key(identifier):
    return int(identifier.split("-", 1)[1])


def _approval_blocking_decisions(section):
    blockers = []
    lines = section.splitlines()
    for index, line in enumerate(lines):
        cells = _split_cells(line)
        if tuple(cell.lower() for cell in cells) != (
            "decision",
            "owner",
            "blocks approval",
            "resolution",
        ):
            continue
        for row in lines[index + 2 :]:
            values = _split_cells(row)
            if not values:
                break
            if (
                len(values) == 4
                and values[2].lower() == "yes"
                and values[3].lower() == "unresolved"
            ):
                identifier = re.sub(r"[^a-z0-9]+", "-", values[0].lower()).strip("-")
                if identifier and identifier not in blockers:
                    blockers.append(identifier)
        break
    return blockers


def validate_prd(path, require_approved=True):
    path = Path(path)
    metadata, body = _frontmatter(_read_text(path), str(path))
    errors = []
    expected_fields = {"type", "id", "status", "version"}
    unknown = set(metadata) - expected_fields
    for field in sorted(unknown):
        errors.append(f"unknown PRD frontmatter field: {field}")
    for field in sorted(expected_fields - set(metadata)):
        errors.append(f"missing PRD frontmatter field: {field}")
    if metadata.get("type") != "prd":
        errors.append("type must be prd")
    identifier = metadata.get("id", "")
    if ID_PATTERN.fullmatch(identifier) is None:
        errors.append("PRD id must be stable kebab-case")
    status = metadata.get("status")
    if status not in {"draft", "approved", "superseded"}:
        errors.append("PRD status must be draft, approved, or superseded")
    elif require_approved and status != "approved":
        errors.append("PRD status must be approved")
    version_text = metadata.get("version", "")
    if re.fullmatch(r"[1-9][0-9]*", version_text) is None:
        errors.append("PRD version must be a positive integer")
        version = None
    else:
        version = int(version_text)

    try:
        sections = _sections(body)
    except ContractError as error:
        sections = {}
        errors.append(str(error))
    for name in PRD_SECTIONS:
        if name not in sections:
            errors.append(f"missing required section: {name}")
        else:
            _require_content(sections[name], f"section {name}", errors)

    functional_requirements = []
    acceptance_criteria = []
    mappings = {}
    if "Functional requirements" in sections:
        definitions = FR_DEFINITION.findall(sections["Functional requirements"])
        functional_requirements = [identifier for identifier, _ in definitions]
        if not definitions:
            errors.append("Functional requirements must define at least one FR-* item")
        if len(functional_requirements) != len(set(functional_requirements)):
            errors.append("functional requirement IDs must be unique")
        for identifier_value, definition in definitions:
            _require_content(
                definition, f"functional requirement {identifier_value}", errors
            )
    if "Acceptance criteria" in sections:
        definitions = AC_DEFINITION.findall(sections["Acceptance criteria"])
        acceptance_criteria = [identifier for identifier, _, _ in definitions]
        if not definitions:
            errors.append("Acceptance criteria must define at least one AC-* item")
        if len(acceptance_criteria) != len(set(acceptance_criteria)):
            errors.append("acceptance criterion IDs must be unique")
        known = set(functional_requirements)
        for ac_identifier, mapping_text, definition in definitions:
            refs = REF_PATTERN.findall(mapping_text)
            fr_refs = [ref for ref in refs if ref.startswith("FR-")]
            if not fr_refs:
                errors.append(
                    f"acceptance criterion {ac_identifier} must map to FR-*"
                )
            for ref in fr_refs:
                if ref not in known:
                    errors.append(
                        f"{ac_identifier} maps unknown functional requirement {ref}"
                    )
            mappings[ac_identifier] = fr_refs
            _require_content(
                definition, f"acceptance criterion {ac_identifier}", errors
            )
        mapped = {ref for refs in mappings.values() for ref in refs}
        for ref in functional_requirements:
            if ref not in mapped:
                errors.append(f"{ref} has no acceptance criterion")

    if functional_requirements != sorted(
        functional_requirements, key=_number_key
    ):
        errors.append("functional requirements must be in numeric order")
    if acceptance_criteria != sorted(acceptance_criteria, key=_number_key):
        errors.append("acceptance criteria must be in numeric order")

    approval_blockers = _approval_blocking_decisions(
        sections.get("Open decisions", "")
    )
    approval = sections.get("Approval", "")
    approval_fields = {}
    for match in re.finditer(
        r"^\s*[-*]\s+(Status|Approver|Evidence|Approved version):\s*(.+?)\s*$",
        approval,
        re.MULTILINE | re.IGNORECASE,
    ):
        field = match.group(1).lower()
        if field in approval_fields:
            errors.append(f"duplicate approval field: {field}")
        else:
            approval_fields[field] = match.group(2).strip()
    if status == "approved":
        if approval_blockers:
            errors.append("approval-blocking decision remains unresolved")
        if approval_fields.get("status", "").lower() != "approved":
            errors.append("approval section status must be Approved")
        for field in ("approver", "evidence"):
            value = approval_fields.get(field, "")
            if not value or PLACEHOLDER.fullmatch(value):
                errors.append(f"approval {field} must be explicit")
        if approval_fields.get("approved version") != version_text:
            errors.append("approval version must match PRD version")

    if errors:
        raise ContractError(errors[0])
    return {
        "schemaVersion": 1,
        **semantic_fields(),
        "path": str(path),
        "id": identifier,
        "status": status,
        "declaredStatus": status,
        "version": version,
        "functionalRequirements": functional_requirements,
        "acceptanceCriteria": acceptance_criteria,
        "mappings": mappings,
        "approvalEvidencePresent": bool(
            approval_fields.get("approver")
            and approval_fields.get("evidence")
            and not PLACEHOLDER.fullmatch(approval_fields["evidence"])
        ),
        "approvalBlockingDecisions": approval_blockers,
    }


def _split_cells(line):
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _parse_task_table(body):
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if tuple(_split_cells(line)) != PLAN_COLUMNS:
            continue
        if index + 1 >= len(lines) or not all(
            re.fullmatch(r":?-{3,}:?", cell)
            for cell in _split_cells(lines[index + 1])
        ):
            raise ContractError("plan task table separator is invalid")
        rows = []
        for row_line in lines[index + 2 :]:
            cells = _split_cells(row_line)
            if not cells:
                break
            if len(cells) != len(PLAN_COLUMNS):
                raise ContractError("plan task row has the wrong number of columns")
            rows.append(dict(zip(PLAN_COLUMNS, cells)))
        if not rows:
            raise ContractError("plan task table must contain at least one task")
        return rows
    raise ContractError(
        "plan must contain the required dependency-aware task table"
    )


def _safe_project_path(project_root, relative, label):
    if not relative or "\\" in relative:
        raise ContractError(f"{label} must be a project-relative POSIX path")
    parsed = PurePosixPath(relative)
    if parsed.is_absolute() or "." in parsed.parts or ".." in parsed.parts:
        raise ContractError(f"{label} must stay within the project")
    root = Path(project_root).resolve()
    result = root.joinpath(*parsed.parts).resolve()
    if result != root and root not in result.parents:
        raise ContractError(f"{label} must stay within the project")
    return result


def _list_field(value):
    if value.lower() == "none":
        return []
    return [
        " ".join(item.split())
        for item in value.split(",")
        if item.strip()
    ]


def _interface_list(value, task_id, column, errors):
    items = _list_field(value)
    if any(item.lower() == "none" for item in items):
        errors.append(f"task {task_id} {column} must use none alone")
        return [item for item in items if item.lower() != "none"]
    return items


def validate_plan(path, project_root=None):
    raw_path = Path(path)
    if str(raw_path) == "-" or URL_LIKE.match(str(raw_path)):
        raise ContractIssue(
            "E_LOCAL_PATH",
            str(raw_path),
            "expected a local filesystem path",
            2,
        )
    path = raw_path.resolve()
    root = Path(project_root).resolve() if project_root else path.parent
    if path != root and root not in path.parents:
        raise ContractError("plan path must stay within the project")
    metadata, body = _frontmatter(_read_text(path), str(path))
    errors = []
    expected_fields = {
        "type",
        "prd-path",
        "prd-artifact",
        "prd-reconciliation",
        "prd-id",
        "prd-version",
    }
    unknown = set(metadata) - expected_fields
    if unknown:
        errors.append(f"unknown plan frontmatter field: {sorted(unknown)[0]}")
    required_fields = {"type", "prd-id", "prd-version"}
    missing = required_fields - set(metadata)
    for field in sorted(missing):
        errors.append(f"missing plan frontmatter field: {field}")
    legacy_identity = "prd-path" in metadata
    reconciled_identity = {
        "prd-artifact",
        "prd-reconciliation",
    }.issubset(metadata)
    if legacy_identity == reconciled_identity:
        errors.append(
            "plan must use either prd-path or prd-artifact with prd-reconciliation"
        )
    if any(
        field in metadata for field in ("prd-artifact", "prd-reconciliation")
    ) and not reconciled_identity:
        errors.append(
            "prd-artifact and prd-reconciliation must be provided together"
        )
    if metadata.get("type") != "implementation-plan":
        errors.append("plan type must be implementation-plan")
    try:
        if legacy_identity:
            prd_path = _safe_project_path(
                root, metadata.get("prd-path", ""), "prd-path"
            )
            prd = validate_prd(prd_path)
        elif reconciled_identity:
            artifact_path = _safe_project_path(
                root, metadata["prd-artifact"], "prd-artifact"
            )
            reconciliation_path = _safe_project_path(
                root,
                metadata["prd-reconciliation"],
                "prd-reconciliation",
            )
            prd = validate_reconciliation(
                root, reconciliation_path, require_approved=True
            )
            if artifact_path != _safe_project_path(
                root, prd["path"], "reconciliation authority artifact"
            ):
                errors.append(
                    "plan PRD artifact does not match reconciliation authority"
                )
            prd_path = artifact_path
        else:
            prd_path = None
            prd = None
    except ContractError as error:
        prd_path = None
        prd = None
        errors.append(str(error))
    if prd:
        if metadata.get("prd-id") != prd["id"]:
            errors.append("plan PRD id does not match the approved PRD")
        if metadata.get("prd-version") != str(prd["version"]):
            errors.append("plan PRD version does not match the approved PRD")

    try:
        rows = _parse_task_table(body)
    except ContractError as error:
        rows = []
        errors.append(str(error))
    task_ids = [row["Task"] for row in rows]
    if len(task_ids) != len(set(task_ids)):
        errors.append("plan task IDs must be unique")
    for task_id in task_ids:
        if ID_PATTERN.fullmatch(task_id) is None:
            errors.append(f"invalid task ID: {task_id}")
    known_tasks = set(task_ids)
    references = set()
    dependencies = {}
    consumed_interfaces = {}
    produced_interfaces = {}
    execution_groups = {}
    parallel_outputs = {}
    for row in rows:
        task_id = row["Task"]
        _require_content(row["Outcome"], f"task {task_id} outcome", errors)
        _require_content(row["Verification"], f"task {task_id} verification", errors)
        for column in ("Prerequisites", "Consumes", "Produces"):
            if not row[column]:
                errors.append(f"task {task_id} {column.lower()} must use a value or none")
        refs = REF_PATTERN.findall(row["PRD refs"])
        references.update(refs)
        if (
            not any(ref.startswith("FR-") for ref in refs)
            or not any(ref.startswith("AC-") for ref in refs)
        ):
            errors.append(f"task {task_id} must map at least one FR-* and AC-*")
        prerequisites = _list_field(row["Prerequisites"])
        dependencies[task_id] = prerequisites
        consumed_interfaces[task_id] = _interface_list(
            row["Consumes"], task_id, "consumes", errors
        )
        produced_interfaces[task_id] = _interface_list(
            row["Produces"], task_id, "produces", errors
        )
        for prerequisite in prerequisites:
            if prerequisite not in known_tasks:
                errors.append(
                    f"task {task_id} has unknown prerequisite {prerequisite}"
                )
            elif prerequisite == task_id:
                errors.append(f"task {task_id} cannot depend on itself")
        execution = row["Execution"]
        group_match = re.fullmatch(
            r"parallel group ([a-z0-9]+(?:-[a-z0-9]+)*)", execution
        )
        if execution != "sequential" and group_match is None:
            errors.append(
                f"task {task_id} execution must be sequential or parallel group NAME"
            )
        if group_match:
            group = group_match.group(1)
            execution_groups[task_id] = group
            parallel_outputs.setdefault(group, []).append(task_id)

    visiting = set()
    visited = set()

    def visit(task_id):
        if task_id in visiting:
            errors.append(f"plan prerequisite cycle includes {task_id}")
            return
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in dependencies.get(task_id, []):
            if dependency in known_tasks:
                visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in task_ids:
        visit(task_id)

    ancestors = {
        task_id: {
            dependency
            for dependency in dependencies.get(task_id, [])
            if dependency in known_tasks
        }
        for task_id in task_ids
    }
    changed = True
    while changed:
        changed = False
        for task_id in task_ids:
            expanded = set(ancestors[task_id])
            for dependency in tuple(ancestors[task_id]):
                expanded.update(ancestors.get(dependency, set()))
            if expanded != ancestors[task_id]:
                ancestors[task_id] = expanded
                changed = True

    for group, group_task_list in parallel_outputs.items():
        group_tasks = set(group_task_list)
        for task_id in group_task_list:
            if group_tasks.intersection(ancestors[task_id]):
                errors.append(
                    f"parallel group {group} contains dependency for task {task_id}"
                )

    interface_producers = {}
    for task_id in task_ids:
        for interface in produced_interfaces.get(task_id, []):
            interface_producers.setdefault(interface, []).append(task_id)
    for interface, producers in interface_producers.items():
        if len(producers) > 1:
            errors.append(
                f"interface {interface} has multiple producers: "
                f"{', '.join(producers)}"
            )
    for consumer in task_ids:
        for interface in consumed_interfaces.get(consumer, []):
            for producer in interface_producers.get(interface, []):
                consumer_group = execution_groups.get(consumer)
                if (
                    consumer_group is not None
                    and consumer_group == execution_groups.get(producer)
                ):
                    errors.append(
                        f"consumer {consumer} and producer {producer} share "
                        f"parallel group {consumer_group}"
                    )
                if producer not in ancestors[consumer]:
                    errors.append(
                        f"task {consumer} consumes {interface} without depending "
                        f"on producer {producer}"
                    )

    if prd:
        expected_refs = set(
            prd["functionalRequirements"] + prd["acceptanceCriteria"]
        )
        unknown_refs = sorted(references - expected_refs)
        missing_refs = sorted(expected_refs - references)
        if unknown_refs:
            errors.append(f"unknown PRD references: {', '.join(unknown_refs)}")
        if missing_refs:
            errors.append(f"missing PRD references: {', '.join(missing_refs)}")
        known_acceptance_criteria = set(prd["acceptanceCriteria"])
        for row in rows:
            task_refs = set(REF_PATTERN.findall(row["PRD refs"]))
            task_fr_refs = {
                ref for ref in task_refs if ref.startswith("FR-")
            }
            for ac_ref in sorted(task_refs & known_acceptance_criteria):
                if not task_fr_refs.intersection(prd["mappings"][ac_ref]):
                    errors.append(
                        f"task {row['Task']} references {ac_ref} without one of "
                        "its mapped functional requirements"
                    )
    if errors:
        raise ContractError(errors[0])
    return {
        "schemaVersion": 1,
        **semantic_fields(),
        "path": str(path),
        "prd": (
            {
                "path": metadata["prd-path"],
                "id": prd["id"],
                "version": prd["version"],
            }
            if legacy_identity
            else {
                "artifact": metadata["prd-artifact"],
                "reconciliation": metadata["prd-reconciliation"],
                "id": prd["id"],
                "version": prd["version"],
            }
        ),
        "tasks": task_ids,
        "taskDetails": {
            row["Task"]: {
                "prdRefs": sorted(
                    set(REF_PATTERN.findall(row["PRD refs"])),
                    key=lambda value: (
                        0 if value.startswith("FR-") else 1,
                        _number_key(value),
                    ),
                ),
                "prerequisites": dependencies[row["Task"]],
                "consumes": consumed_interfaces[row["Task"]],
                "produces": produced_interfaces[row["Task"]],
                "execution": {
                    "mode": (
                        "parallel"
                        if row["Task"] in execution_groups
                        else "sequential"
                    ),
                    "group": execution_groups.get(row["Task"]),
                },
                "verification": row["Verification"],
            }
            for row in rows
        },
        "requirementCoverage": {
            "functionalRequirements": prd["functionalRequirements"],
            "acceptanceCriteria": prd["acceptanceCriteria"],
        },
    }


def _plan_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _confined_cursor(project_root, cursor_path):
    root = Path(project_root).resolve()
    path = Path(cursor_path)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if path != root and root not in path.parents:
        raise ContractError("cursor path must stay within the project")
    return path


def _validate_completed_tasks(plan, completed):
    if not isinstance(completed, list) or any(
        not isinstance(item, str) for item in completed
    ):
        raise ContractError("cursor completed tasks are invalid")
    if len(completed) != len(set(completed)):
        raise ContractError("cursor completed tasks must be unique")
    unknown = set(completed) - set(plan["tasks"])
    if unknown:
        raise ContractError(f"unknown completed task {sorted(unknown)[0]}")
    for completed_task in completed:
        for prerequisite in plan["taskDetails"][completed_task]["prerequisites"]:
            if prerequisite not in completed:
                raise ContractError(
                    f"completed task {completed_task} has incomplete "
                    f"prerequisite {prerequisite}"
                )


def _validate_current_task(plan, task, completed):
    for prerequisite in plan["taskDetails"][task]["prerequisites"]:
        if prerequisite not in completed:
            raise ContractError(f"incomplete prerequisite {prerequisite}")


def update_cursor(plan_path, task, completed, project_root=None, cursor_path=None):
    plan_path = Path(plan_path).resolve()
    root = Path(project_root).resolve() if project_root else plan_path.parent
    plan = validate_plan(plan_path, root)
    if task not in plan["tasks"]:
        raise ContractError(f"unknown cursor task {task}")
    completed = list(dict.fromkeys(completed))
    _validate_completed_tasks(plan, completed)
    _validate_current_task(plan, task, completed)
    cursor_path = _confined_cursor(
        root,
        cursor_path or Path(".git") / "sdlc-execution-cursor.json",
    )
    try:
        plan_relative = plan_path.relative_to(root).as_posix()
    except ValueError as error:
        raise ContractError("plan path must stay within the project") from error
    payload = {
        "schemaVersion": 1,
        "planPath": plan_relative,
        "planDigest": _plan_digest(plan_path),
        "currentTask": task,
        "completedTasks": completed,
    }
    cursor_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cursor_path.with_name(f"{cursor_path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(cursor_path)
    return payload


def read_cursor(plan_path, project_root=None, cursor_path=None):
    plan_path = Path(plan_path).resolve()
    root = Path(project_root).resolve() if project_root else plan_path.parent
    plan = validate_plan(plan_path, root)
    cursor_path = _confined_cursor(
        root,
        cursor_path or Path(".git") / "sdlc-execution-cursor.json",
    )
    try:
        payload = json.loads(_read_text(cursor_path))
    except json.JSONDecodeError as error:
        raise ContractError(f"invalid cursor JSON: {error}") from error
    expected = {
        "schemaVersion",
        "planPath",
        "planDigest",
        "currentTask",
        "completedTasks",
    }
    if not isinstance(payload, dict) or set(payload) != expected:
        raise ContractError("cursor fields are invalid")
    if payload["schemaVersion"] != 1:
        raise ContractError("cursor schemaVersion must be 1")
    try:
        expected_plan_path = plan_path.relative_to(root).as_posix()
    except ValueError as error:
        raise ContractError("plan path must stay within the project") from error
    if payload["planPath"] != expected_plan_path:
        raise ContractError("cursor does not identify the current plan")
    if payload["planDigest"] != _plan_digest(plan_path):
        raise ContractError("cursor does not match the current plan")
    if payload["currentTask"] not in plan["tasks"]:
        raise ContractError("cursor current task is not in the plan")
    _validate_completed_tasks(plan, payload["completedTasks"])
    _validate_current_task(
        plan, payload["currentTask"], payload["completedTasks"]
    )
    return payload


class _ContractArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ContractIssue("E_USAGE", "/command", message, 2)


def _parser():
    parser = _ContractArgumentParser(
        description="Validate SDLC product artifacts and execution continuity."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    prd = commands.add_parser("validate-prd")
    prd.add_argument("path", nargs="?", type=Path)
    prd.add_argument("--reconciliation", type=Path)
    prd.add_argument("--project-root", type=Path)
    prd.add_argument("--allow-draft", action="store_true")
    plan = commands.add_parser("validate-plan")
    plan.add_argument("path", type=Path)
    plan.add_argument("--project-root", type=Path)
    handoff = commands.add_parser("validate-handoff")
    handoff.add_argument("path", type=Path)
    handoff.add_argument("--project-root", type=Path)
    render = commands.add_parser("render-handoff")
    render.add_argument("path", type=Path)
    render.add_argument(
        "--forge", required=True, choices=("github", "gitlab", "azure-devops")
    )
    render.add_argument("--template", type=Path)
    render.add_argument("--output", type=Path)
    render.add_argument("--force", action="store_true")
    render.add_argument("--metadata-json", action="store_true")
    for name in ("explain", "preview", "render-coverage"):
        report = commands.add_parser(name)
        report.add_argument("--input", dest="input_path", required=True, type=Path)
        report.add_argument(
            "--detail",
            choices=("concise", "normal", "detailed"),
            default="normal",
        )
    cursor = commands.add_parser("cursor")
    cursor.add_argument("path", type=Path)
    cursor.add_argument("--project-root", type=Path)
    cursor.add_argument("--cursor", dest="cursor_path", type=Path)
    cursor.add_argument("--task", required=True)
    cursor.add_argument("--complete", action="append", default=[])
    status = commands.add_parser("cursor-status")
    status.add_argument("path", type=Path)
    status.add_argument("--project-root", type=Path)
    status.add_argument("--cursor", dest="cursor_path", type=Path)
    return parser


def _legacy_issue(error):
    message = str(error)
    mappings = (
        ("PRD status must be approved", "E_PRD_STATUS", "/status"),
        ("plan prerequisite cycle includes ", "E_PLAN_CYCLE", "/tasks"),
        ("approval-blocking decision remains unresolved", "E_PRD_DECISION", "/openDecisions"),
        ("unknown PRD frontmatter field", "E_PRD_FIELD", "/"),
        ("missing PRD frontmatter field", "E_PRD_FIELD", "/"),
        ("duplicate section", "E_PRD_SECTION_DUPLICATE", "/"),
        ("duplicate frontmatter field", "E_FRONTMATTER_DUPLICATE", "/"),
        ("duplicate approval field", "E_PRD_APPROVAL_DUPLICATE", "/approval"),
        ("functional requirements must be in numeric order", "E_PRD_FR_ORDER", "/functionalRequirements"),
        ("acceptance criteria must be in numeric order", "E_PRD_AC_ORDER", "/acceptanceCriteria"),
        ("missing required section", "E_PRD_SECTION", "/"),
        ("plan task IDs must be unique", "E_PLAN_TASK_DUPLICATE", "/tasks"),
        ("interface ", "E_PLAN_INTERFACE", "/tasks"),
        ("unknown PRD references", "E_PLAN_REFERENCE", "/tasks"),
        ("missing PRD references", "E_PLAN_REFERENCE", "/tasks"),
        ("task ", "E_PLAN_TASK", "/tasks"),
        ("plan path must stay within the project", "E_PATH_CONFINEMENT", "/path"),
        ("prd-path must stay within the project", "E_PATH_CONFINEMENT", "/prd/path"),
    )
    for prefix, code, pointer in mappings:
        if message.startswith(prefix) or prefix in message:
            if code == "E_PRD_STATUS":
                message = "expected approved; use --allow-draft to inspect a draft"
            return ContractIssue(code, pointer, message)
    return ContractIssue("E_CONTRACT", "/", message)


def main(argv=None):
    try:
        arguments = _parser().parse_args(argv)
    except ContractIssue as error:
        print(error.cli_message(), file=sys.stderr)
        return error.exit_code
    except SystemExit as error:
        return int(error.code)
    try:
        if (
            arguments.command == "render-handoff"
            and arguments.force
            and arguments.output is None
        ):
            raise ContractIssue(
                "E_USAGE", "/force", "--force requires --output", 2
            )
        if arguments.command == "validate-prd":
            if (arguments.path is None) == (arguments.reconciliation is None):
                raise ContractIssue(
                    "E_USAGE",
                    "/path",
                    "provide exactly one native PRD path or --reconciliation",
                    2,
                )
            if arguments.reconciliation is not None:
                if arguments.project_root is None:
                    raise ContractIssue(
                        "E_USAGE",
                        "/project-root",
                        "--project-root is required with --reconciliation",
                        2,
                    )
                result = validate_reconciliation(
                    arguments.project_root,
                    arguments.reconciliation,
                    require_approved=not arguments.allow_draft,
                )
            else:
                result = validate_prd(
                    arguments.path, require_approved=not arguments.allow_draft
                )
        elif arguments.command == "validate-plan":
            result = validate_plan(arguments.path, arguments.project_root)
        elif arguments.command == "validate-handoff":
            data = strict_load_json(arguments.path)
            result = validate_handoff_model(
                data,
                arguments.path,
                arguments.project_root,
                validate_prd=validate_prd,
                validate_reconciliation=validate_reconciliation,
            )
        elif arguments.command == "render-handoff":
            data = strict_load_json(arguments.path)
            validate_handoff_model(
                data,
                arguments.path,
                validate_prd=validate_prd,
                validate_reconciliation=validate_reconciliation,
            )
            rendered = render_handoff(data, arguments.forge)
            if arguments.template:
                rendered = apply_template(
                    read_template(arguments.template),
                    rendered,
                    arguments.template,
                )
            result = result_envelope(
                arguments.forge,
                str(arguments.output) if arguments.output else "stdout",
                arguments.template is not None,
                rendered,
            )
            if arguments.output:
                write_output(arguments.output, rendered, arguments.force)
            else:
                sys.stdout.write(rendered)
                if arguments.metadata_json:
                    sys.stderr.write(metadata_json(result))
                return 0
        elif arguments.command in ("explain", "preview", "render-coverage"):
            result = build_report(
                strict_load_json(arguments.input_path),
                arguments.command,
                arguments.detail,
            )
        elif arguments.command == "cursor":
            result = update_cursor(
                arguments.path,
                arguments.task,
                arguments.complete,
                arguments.project_root,
                arguments.cursor_path,
            )
        elif arguments.command == "cursor-status":
            result = read_cursor(
                arguments.path, arguments.project_root, arguments.cursor_path
            )
        else:
            raise ContractIssue("E_COMMAND", "/command", "unsupported command", 2)
    except ContractIssue as error:
        if error.code == "E_CONTRACT":
            error = _legacy_issue(error)
        print(error.cli_message(), file=sys.stderr)
        return error.exit_code
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
