#!/usr/bin/env python3
"""Deterministically reconcile local requirement artifacts with the SDLC PRD contract."""

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath

sys.dont_write_bytecode = True

from artifact_contracts import ContractIssue, semantic_fields, strict_load_json


TOOL_VERSION = "3.5.3"
SOURCE_KINDS = (
    "generic-spec",
    "feature-design",
    "issue-export",
    "structured-spec",
    "repository-prd",
)
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REF_PATTERN = re.compile(r"\b(?:FR|AC)-[1-9][0-9]*\b")
PLACEHOLDER = re.compile(
    r"^(?:tbd|todo|none provided|not approved|draft|n/?a)$", re.IGNORECASE
)
FR_LINE = re.compile(
    r"^\s*[-*]\s+(?:\*\*)?(?:(FR-[1-9][0-9]*)(?:\*\*)?:\s*)?(.+?)\s*$"
)
AC_LINE = re.compile(
    r"^\s*[-*]\s+(?:\*\*)?(?:(AC-[1-9][0-9]*)(?:\*\*)?\s*)?"
    r"(?:\(([^)]*)\):\s*)?(.+?)\s*$"
)
REPARSE_POINT = 0x400

FIELD_ALIASES = {
    "problemContext": ("problem and context", "problem", "background"),
    "targetUsersBenefit": (
        "target users and benefit",
        "users and value",
        "audience and value",
        "users",
    ),
    "outcome": ("outcome", "objective", "desired outcome"),
    "goals": ("goals",),
    "nonGoals": ("non-goals", "out of scope", "non goals"),
    "scenarios": ("user scenarios", "scenarios", "use cases", "flows"),
    "functionalRequirements": (
        "functional requirements",
        "requirements",
        "behaviors",
    ),
    "acceptanceCriteria": ("acceptance criteria", "acceptance", "validation"),
    "dataSecurity": (
        "data, permissions, privacy, and security",
        "security considerations",
        "data and security",
    ),
    "constraints": (
        "constraints and dependencies",
        "constraints",
        "dependencies",
    ),
    "successMeasures": ("success measures", "metrics", "measures"),
    "openDecisions": ("open decisions", "open questions", "decisions"),
    "approval": ("approval", "decision record"),
}
STRUCTURED_FIELDS = {
    "problemContext": ("problemContext", "problem", "background"),
    "targetUsersBenefit": ("targetUsersBenefit", "targetUsers", "audience"),
    "outcome": ("outcome", "objective"),
    "goals": ("goals",),
    "nonGoals": ("nonGoals",),
    "scenarios": ("scenarios", "useCases", "flows"),
    "functionalRequirements": ("requirements", "functionalRequirements"),
    "acceptanceCriteria": ("acceptance", "acceptanceCriteria"),
    "dataSecurity": ("dataSecurity", "security"),
    "constraints": ("constraints", "dependencies"),
    "successMeasures": ("successMeasures", "metrics"),
    "openDecisions": ("openDecisions", "openQuestions"),
    "approval": ("approval",),
}
REQUIRED_TARGETS = tuple(f"/{name}" for name in FIELD_ALIASES)
TEXT_FIELDS = ("problemContext", "targetUsersBenefit", "outcome", "dataSecurity")
ARRAY_FIELDS = (
    "goals",
    "nonGoals",
    "scenarios",
    "constraints",
    "successMeasures",
)
REPORT_FIELDS = {
    "schemaVersion",
    "prdId",
    "authority",
    "source",
    "normalized",
    "mappings",
    "assignedIds",
    "missing",
    "conflicts",
    "superseded",
    "overlay",
    "approval",
    "generated",
}


class ReconciliationError(ContractIssue):
    pass


def fail(code, pointer, message, exit_code=3):
    raise ReconciliationError(code, pointer, message, exit_code)


def _json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def atomic_write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        fail("E_ATOMIC_WRITE", str(path), "atomic write failed", 4)


def _relative_path(root, path, pointer, *, must_exist=True):
    root = Path(root).resolve()
    raw = Path(path)
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]+:", str(path)) or "://" in str(path):
        fail("E_LOCAL_PATH", pointer, "expected a local filesystem path", 2)
    candidate = raw if raw.is_absolute() else root / raw
    lexical = Path(os.path.abspath(candidate))
    try:
        relative_lexical = lexical.relative_to(root)
    except ValueError:
        fail("E_PATH_CONFINEMENT", pointer, "path must stay within the project", 2)
    current = root
    for part in relative_lexical.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            try:
                stat = current.lstat()
            except OSError:
                fail("E_INPUT_READ", pointer, "cannot inspect local path", 2)
            if current.is_symlink() or (
                getattr(stat, "st_file_attributes", 0) & REPARSE_POINT
            ):
                fail(
                    "E_PATH_LINK",
                    pointer,
                    "linked or reparse paths are not allowed",
                    2,
                )
    resolved = lexical.resolve()
    if resolved != root and root not in resolved.parents:
        fail("E_PATH_CONFINEMENT", pointer, "path must stay within the project", 2)
    if must_exist and not resolved.exists():
        fail("E_INPUT_READ", pointer, "local path does not exist", 2)
    return resolved, PurePosixPath(relative_lexical.as_posix()).as_posix()


def _source_bytes(path):
    if path.is_file():
        return path.read_bytes(), None
    if not path.is_dir():
        fail("E_INPUT_READ", "/source/path", "source must be a file or directory", 2)
    files = sorted(
        item for item in path.rglob("*") if item.is_file() and not item.is_symlink()
    )
    if not files:
        fail("E_INPUT_READ", "/source/path", "structured source directory is empty", 2)
    digest_input = bytearray()
    listed = []
    for item in files:
        relative = item.relative_to(path).as_posix()
        content = item.read_bytes()
        name = relative.encode("utf-8")
        digest_input.extend(len(name).to_bytes(8, "big"))
        digest_input.extend(name)
        digest_input.extend(len(content).to_bytes(8, "big"))
        digest_input.extend(content)
        listed.append({"path": relative, "digest": _digest(content)})
    return bytes(digest_input), listed


def _digest(content):
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _frontmatter(lines):
    if not lines or lines[0].strip() != "---":
        return {}, 0
    result = {}
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return result, index + 1
        match = re.fullmatch(r"([a-zA-Z][a-zA-Z0-9_-]*):\s*(.*?)\s*", lines[index])
        if match:
            key, value = match.groups()
            if key in result:
                fail("E_SOURCE_DUPLICATE", f"/source/line/{index + 1}", f"duplicate field {key}")
            result[key] = value.strip("\"'")
    fail("E_SOURCE_FORMAT", "/source", "unterminated frontmatter", 2)


def _section_records(lines, start):
    records = []
    headings = []
    for index in range(start, len(lines)):
        match = re.match(r"^##\s+(.+?)\s*$", lines[index])
        if match:
            headings.append((index, match.group(1).strip()))
    for position, (index, heading) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        records.append(
            {
                "heading": heading,
                "normalized": re.sub(r"\s+", " ", heading.lower()),
                "line": index + 1,
                "start": index + 1,
                "end": end,
                "text": "\n".join(lines[index + 1 : end]).strip(),
            }
        )
    return records


def _selector(record, line=None):
    return f"heading:{record['heading']}#line-{line or record['line']}"


def _assigned(identifier_type, text, existing, ordinal):
    source_key = f"{identifier_type.lower()}:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"
    identifier = existing.get(source_key) or f"{identifier_type}-{ordinal}"
    return identifier, source_key


def _parse_markdown(path, existing_ids):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeError:
        fail("E_UTF8", "/source/path", "source is not valid UTF-8", 2)
    metadata, start = _frontmatter(lines)
    records = _section_records(lines, start)
    values = {}
    mappings = []
    missing = []
    conflicts = []
    assigned = []
    candidates = {}

    for field, aliases in FIELD_ALIASES.items():
        matches = [record for record in records if record["normalized"] in aliases]
        target = f"/{field}"
        if not matches:
            missing.append({"target": target, "reason": "no mapped source location"})
            continue
        candidates[target] = {
            _selector(record): record["text"] for record in matches
        }
        if len(matches) > 1:
            conflicts.append(
                {
                    "target": target,
                    "sources": sorted(_selector(item) for item in matches),
                    "question": f"Which source location controls {field}?",
                    "owner": "project decision owner",
                    "blocking": True,
                }
            )
            continue
        record = matches[0]
        if not record["text"]:
            missing.append({"target": target, "reason": "mapped source location is empty"})
            continue
        values[field] = record["text"]
        mappings.append(
            {
                "target": target,
                "source": {"selector": _selector(record)},
                "transform": "identity",
                "confidence": "exact",
            }
        )

    requirements = []
    requirement_record = next(
        (
            record
            for record in records
            if record["normalized"] in FIELD_ALIASES["functionalRequirements"]
        ),
        None,
    )
    if requirement_record and "/functionalRequirements" not in {c["target"] for c in conflicts}:
        for index in range(requirement_record["start"], requirement_record["end"]):
            match = FR_LINE.match(lines[index])
            if not match:
                continue
            explicit, text = match.groups()
            if not text.strip():
                continue
            identifier, source_key = (
                (explicit, f"explicit:{explicit}")
                if explicit
                else _assigned("FR", text.strip(), existing_ids, len(requirements) + 1)
            )
            if not explicit:
                assigned.append({"sourceKey": source_key, "targetId": identifier})
            requirements.append({"id": identifier, "text": text.strip()})
            mappings.append(
                {
                    "target": f"/functionalRequirements/{identifier}",
                    "source": {"selector": _selector(requirement_record, index + 1)},
                    "transform": "identity",
                    "confidence": "exact",
                }
            )

    acceptance = []
    acceptance_record = next(
        (
            record
            for record in records
            if record["normalized"] in FIELD_ALIASES["acceptanceCriteria"]
        ),
        None,
    )
    if acceptance_record and "/acceptanceCriteria" not in {c["target"] for c in conflicts}:
        for index in range(acceptance_record["start"], acceptance_record["end"]):
            match = AC_LINE.match(lines[index])
            if not match:
                continue
            explicit, mapping_text, text = match.groups()
            if not text.strip():
                continue
            identifier, source_key = (
                (explicit, f"explicit:{explicit}")
                if explicit
                else _assigned("AC", text.strip(), existing_ids, len(acceptance) + 1)
            )
            if not explicit:
                assigned.append({"sourceKey": source_key, "targetId": identifier})
            acceptance.append(
                {
                    "id": identifier,
                    "requirements": [
                        item
                        for item in REF_PATTERN.findall(mapping_text or "")
                        if item.startswith("FR-")
                    ],
                    "text": text.strip(),
                }
            )
            mappings.append(
                {
                    "target": f"/acceptanceCriteria/{identifier}",
                    "source": {"selector": _selector(acceptance_record, index + 1)},
                    "transform": "identity",
                    "confidence": "exact",
                }
            )

    return {
        "id": metadata.get("id") or metadata.get("feature-id"),
        "version": metadata.get("version") or metadata.get("revision"),
        "status": metadata.get("status"),
        "revision": metadata.get("revision"),
        "values": values,
        "requirements": requirements,
        "acceptance": acceptance,
        "mappings": mappings,
        "assigned": assigned,
        "missing": missing,
        "conflicts": conflicts,
        "selectors": {item["source"]["selector"] for item in mappings},
        "candidates": candidates,
    }


def _strict_json_value(path):
    return strict_load_json(path)


def _parse_structured(path, existing_ids):
    if path.is_dir():
        json_files = sorted(path.rglob("*.json"))
        if len(json_files) != 1:
            fail(
                "E_SOURCE_FORMAT",
                "/source/path",
                "structured directories must contain exactly one JSON model",
                2,
            )
        value = _strict_json_value(json_files[0])
    else:
        value = _strict_json_value(path)
    if not isinstance(value, dict):
        fail("E_SOURCE_FORMAT", "/source", "structured source must be an object", 2)
    values = {}
    mappings = []
    missing = []
    conflicts = []
    assigned = []
    selected = {}
    candidates = {}
    for field, aliases in STRUCTURED_FIELDS.items():
        present = [alias for alias in aliases if alias in value]
        target = f"/{field}"
        if not present:
            missing.append({"target": target, "reason": "no mapped source location"})
        else:
            candidates[target] = {f"/{item}": value[item] for item in present}
        if len(present) > 1:
            conflicts.append(
                {
                    "target": target,
                    "sources": sorted(f"/{item}" for item in present),
                    "question": f"Which source location controls {field}?",
                    "owner": "project decision owner",
                    "blocking": True,
                }
            )
        elif present:
            selected[field] = present[0]
            values[field] = value[present[0]]
            mappings.append(
                {
                    "target": target,
                    "source": {"selector": f"/{present[0]}"},
                    "transform": "identity",
                    "confidence": "exact",
                }
            )
    requirements = []
    raw_requirements = values.get("functionalRequirements", [])
    if not isinstance(raw_requirements, list):
        raw_requirements = []
    for index, item in enumerate(raw_requirements):
        item = item if isinstance(item, dict) else {"text": item}
        text = str(item.get("text", "")).strip()
        explicit = item.get("id")
        identifier, source_key = (
            (explicit, f"explicit:{explicit}")
            if explicit
            else _assigned("FR", text, existing_ids, len(requirements) + 1)
        )
        if not explicit:
            assigned.append({"sourceKey": source_key, "targetId": identifier})
        requirements.append({"id": identifier, "text": text})
        mappings.append(
            {
                "target": f"/functionalRequirements/{identifier}",
                "source": {"selector": f"/{selected.get('functionalRequirements', 'requirements')}/{index}"},
                "transform": "identity",
                "confidence": "exact",
            }
        )
    acceptance = []
    raw_acceptance = values.get("acceptanceCriteria", [])
    if not isinstance(raw_acceptance, list):
        raw_acceptance = []
    for index, item in enumerate(raw_acceptance):
        item = item if isinstance(item, dict) else {"text": item}
        text = str(item.get("text", "")).strip()
        explicit = item.get("id")
        identifier, source_key = (
            (explicit, f"explicit:{explicit}")
            if explicit
            else _assigned("AC", text, existing_ids, len(acceptance) + 1)
        )
        if not explicit:
            assigned.append({"sourceKey": source_key, "targetId": identifier})
        refs = item.get("requirements", [])
        acceptance.append(
            {
                "id": identifier,
                "requirements": list(refs) if isinstance(refs, list) else [],
                "text": text,
            }
        )
        mappings.append(
            {
                "target": f"/acceptanceCriteria/{identifier}",
                "source": {"selector": f"/{selected.get('acceptanceCriteria', 'acceptance')}/{index}"},
                "transform": "identity",
                "confidence": "exact",
            }
        )
    return {
        "id": value.get("id"),
        "version": value.get("version", value.get("revision")),
        "status": value.get("status"),
        "revision": value.get("revision"),
        "values": values,
        "requirements": requirements,
        "acceptance": acceptance,
        "mappings": mappings,
        "assigned": assigned,
        "missing": missing,
        "conflicts": conflicts,
        "selectors": {item["source"]["selector"] for item in mappings},
        "candidates": candidates,
    }


def parse_source(path, kind, existing_ids=None):
    existing_ids = existing_ids or {}
    model = (
        _parse_structured(path, existing_ids)
        if kind == "structured-spec"
        else _parse_markdown(path, existing_ids)
    )
    if not isinstance(model["id"], str) or not ID_PATTERN.fullmatch(model["id"]):
        model["missing"].append(
            {"target": "/id", "reason": "stable kebab-case identity is required"}
        )
    try:
        model["version"] = int(model["version"])
    except (TypeError, ValueError):
        model["version"] = None
    if not model["version"] or model["version"] < 1:
        model["missing"].append(
            {"target": "/version", "reason": "positive reconciliation version is required"}
        )
    if model["status"] not in ("draft", "approved", "superseded"):
        model["missing"].append(
            {"target": "/status", "reason": "explicit lifecycle status is required"}
        )
    return model


def _sort_report(report):
    report["mappings"] = sorted(
        report["mappings"], key=lambda item: (item["target"], item["source"]["selector"])
    )
    report["assignedIds"] = sorted(
        report["assignedIds"], key=lambda item: (item["targetId"], item["sourceKey"])
    )
    report["missing"] = sorted(
        report["missing"], key=lambda item: (item["target"], item["reason"])
    )
    report["conflicts"] = sorted(
        report["conflicts"], key=lambda item: (item["target"], item["sources"])
    )
    report["superseded"] = sorted(
        report["superseded"], key=lambda item: (item["replacedBy"], item["source"])
    )
    return report


def _read_existing_report(report_path):
    if not report_path.exists():
        return None
    report = strict_load_json(report_path)
    _validate_report_shape(report)
    return report


def _existing_assignments(report):
    if report is None:
        return {}
    return {
        item.get("sourceKey"): item.get("targetId")
        for item in report.get("assignedIds", [])
        if isinstance(item, dict)
    }


def _is_substantive(value):
    return (
        isinstance(value, str)
        and bool(value.strip())
        and not PLACEHOLDER.fullmatch(value.strip())
    )


def _approval_error(report, require_approved):
    approval = report["approval"]
    if not require_approved and approval["status"] != "approved":
        return None
    if approval["status"] != "approved":
        return ("E_APPROVAL", "/approval/status", "reconciliation approval is required")
    if report["normalized"]["status"] != "approved":
        return ("E_APPROVAL", "/normalized/status", "normalized status must be approved")
    if not _is_substantive(approval["approver"]) or not _is_substantive(
        approval["evidence"]
    ):
        return (
            "E_APPROVAL",
            "/approval",
            "substantive approver and approval evidence are required",
        )
    if approval["approvedVersion"] != report["normalized"]["version"]:
        return (
            "E_APPROVAL_BINDING",
            "/approval/approvedVersion",
            "approved version does not match",
        )
    if approval["approvedSourceDigest"] != report["source"]["digest"]:
        return (
            "E_APPROVAL_BINDING",
            "/approval/approvedSourceDigest",
            "approved source digest does not match",
        )
    prior_digest = report["source"].get("priorDigest")
    prior_version = report["source"].get("priorVersion")
    carry_forward_required = (
        prior_digest
        and prior_digest != report["source"]["digest"]
        and prior_version == report["normalized"]["version"]
    )
    if carry_forward_required and not _is_substantive(approval["carryForward"]):
        return (
            "E_APPROVAL_CARRY_FORWARD",
            "/approval/carryForward",
            "explicit substantive carry-forward approval is required after semantic no-op source drift",
        )
    if approval["carryForward"] is not None and not _is_substantive(
        approval["carryForward"]
    ):
        return (
            "E_APPROVAL_CARRY_FORWARD",
            "/approval/carryForward",
            "carry-forward approval must contain substantive content",
        )
    return None


def _last_approved_provenance(report):
    if report is None:
        return None, None
    prior_digest = report["source"].get("priorDigest")
    prior_version = report["source"].get("priorVersion")
    if _approval_error(report, True) is None:
        return report["source"]["digest"], report["normalized"]["version"]
    return prior_digest, prior_version


def build_report(
    root,
    source_path,
    source_relative,
    kind,
    report_relative,
    view_relative,
    existing_report=None,
):
    existing = _existing_assignments(existing_report)
    prior_digest, prior_version = _last_approved_provenance(existing_report)
    model = parse_source(source_path, kind, existing)
    source_content, files = _source_bytes(source_path)
    report = {
        "schemaVersion": 1,
        "prdId": model["id"] or "unresolved-prd-id",
        "authority": {
            "mode": "generated-view" if view_relative else "direct",
            "artifact": view_relative or source_relative,
            "generatedView": view_relative,
        },
        "source": {
            "kind": kind,
            "path": source_relative,
            "digest": _digest(source_content),
            "revision": model["revision"],
            "files": files,
            "priorDigest": prior_digest,
            "priorVersion": prior_version,
        },
        "normalized": {
            "version": model["version"],
            "status": model["status"] or "draft",
        },
        "mappings": model["mappings"],
        "assignedIds": model["assigned"],
        "missing": model["missing"],
        "conflicts": model["conflicts"],
        "superseded": [],
        "overlay": {
            "sections": {},
            "approvalEvidence": None,
        },
        "approval": {
            "status": "draft",
            "approver": None,
            "evidence": None,
            "approvedVersion": None,
            "approvedSourceDigest": None,
            "carryForward": None,
        },
        "generated": {
            "toolVersion": TOOL_VERSION,
            "viewDigest": None,
        },
    }
    if existing_report:
        old_pairs = {
            (item["target"], item["source"]["selector"]): item
            for item in existing_report["mappings"]
        }
        for mapping in report["mappings"]:
            old = old_pairs.get((mapping["target"], mapping["source"]["selector"]))
            if old and old["confidence"] == "reviewed":
                mapping["confidence"] = "reviewed"
        report["mappings"].extend(
            copy.deepcopy(item)
            for key, item in old_pairs.items()
            if item["confidence"] == "reviewed"
            and key
            not in {
                (mapping["target"], mapping["source"]["selector"])
                for mapping in report["mappings"]
            }
        )
        report["superseded"] = copy.deepcopy(existing_report["superseded"])
        report["overlay"] = copy.deepcopy(existing_report["overlay"])
    return _sort_report(report), model


def _validate_report_shape(report):
    if not isinstance(report, dict) or set(report) != REPORT_FIELDS:
        fail("E_REPORT_SCHEMA", "/", "report fields do not match schema")
    if report.get("schemaVersion") != 1:
        fail("E_REPORT_SCHEMA", "/schemaVersion", "expected schema version 1")
    if not isinstance(report.get("prdId"), str) or not ID_PATTERN.fullmatch(
        report["prdId"]
    ):
        fail("E_REPORT_SCHEMA", "/prdId", "expected stable kebab-case ID")
    authority = report.get("authority")
    if not isinstance(authority, dict) or set(authority) != {
        "mode",
        "artifact",
        "generatedView",
    }:
        fail("E_REPORT_SCHEMA", "/authority", "invalid authority object")
    if authority["mode"] not in ("direct", "generated-view"):
        fail("E_AUTHORITY", "/authority/mode", "expected direct or generated-view")
    _validate_relative_path(authority["artifact"], "/authority/artifact")
    generated_view = authority["generatedView"]
    if authority["mode"] == "direct" and generated_view is not None:
        fail("E_AUTHORITY", "/authority", "direct authority cannot nominate a generated view")
    if authority["mode"] == "generated-view" and (
        not isinstance(generated_view, str) or authority["artifact"] != generated_view
    ):
        fail("E_AUTHORITY", "/authority", "generated-view authority must nominate one view")
    if generated_view is not None:
        _validate_relative_path(generated_view, "/authority/generatedView")
    source = report.get("source")
    if not isinstance(source, dict) or set(source) not in ({
        "kind",
        "path",
        "digest",
        "revision",
        "files",
    }, {
        "kind",
        "path",
        "digest",
        "revision",
        "files",
        "priorDigest",
        "priorVersion",
    }):
        fail("E_REPORT_SCHEMA", "/source", "invalid source object")
    if source["kind"] not in SOURCE_KINDS:
        fail("E_REPORT_SCHEMA", "/source/kind", "unsupported source kind")
    _validate_relative_path(source["path"], "/source/path")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(source["digest"])):
        fail("E_REPORT_SCHEMA", "/source/digest", "invalid SHA-256 digest")
    if "priorDigest" in source:
        if source["priorDigest"] is not None and not re.fullmatch(
            r"sha256:[0-9a-f]{64}", str(source["priorDigest"])
        ):
            fail("E_REPORT_SCHEMA", "/source/priorDigest", "invalid prior digest")
        if source["priorVersion"] is not None and (
            type(source["priorVersion"]) is not int or source["priorVersion"] < 1
        ):
            fail("E_REPORT_SCHEMA", "/source/priorVersion", "invalid prior version")
    if not isinstance(report.get("mappings"), list):
        fail("E_REPORT_SCHEMA", "/mappings", "expected array")
    for index, mapping in enumerate(report["mappings"]):
        if not isinstance(mapping, dict) or set(mapping) != {
            "target",
            "source",
            "transform",
            "confidence",
        }:
            fail("E_REPORT_SCHEMA", f"/mappings/{index}", "invalid mapping")
        if mapping["confidence"] not in ("exact", "reviewed"):
            fail("E_MAPPING_CONFIDENCE", f"/mappings/{index}/confidence", "expected exact or reviewed")
        if not isinstance(mapping["source"], dict) or set(mapping["source"]) != {"selector"}:
            fail("E_REPORT_SCHEMA", f"/mappings/{index}/source", "invalid source selector")
        if (
            not isinstance(mapping["target"], str)
            or not mapping["target"].startswith("/")
            or not isinstance(mapping["source"]["selector"], str)
            or not mapping["source"]["selector"].strip()
            or not isinstance(mapping["transform"], str)
            or not mapping["transform"].strip()
        ):
            fail("E_REPORT_SCHEMA", f"/mappings/{index}", "invalid mapping values")
    for field in ("assignedIds", "missing", "conflicts", "superseded"):
        if not isinstance(report.get(field), list):
            fail("E_REPORT_SCHEMA", f"/{field}", "expected array")
    normalized = report.get("normalized")
    if (
        not isinstance(normalized, dict)
        or set(normalized) != {"version", "status"}
        or type(normalized["version"]) is not int
        or normalized["version"] < 1
        or normalized["status"] not in ("draft", "approved", "superseded")
    ):
        fail("E_REPORT_SCHEMA", "/normalized", "invalid normalized identity")
    overlay = report.get("overlay")
    if (
        not isinstance(overlay, dict)
        or set(overlay) != {"sections", "approvalEvidence"}
        or not isinstance(overlay["sections"], dict)
        or any(
            not isinstance(key, str)
            or not isinstance(value, str)
            or not value.strip()
            for key, value in overlay["sections"].items()
        )
    ):
        fail("E_REPORT_SCHEMA", "/overlay", "invalid overlay object")
    approval = report.get("approval")
    if not isinstance(approval, dict) or set(approval) != {
        "status",
        "approver",
        "evidence",
        "approvedVersion",
        "approvedSourceDigest",
        "carryForward",
    }:
        fail("E_REPORT_SCHEMA", "/approval", "invalid approval object")
    if approval["status"] not in ("draft", "approved"):
        fail("E_REPORT_SCHEMA", "/approval/status", "expected draft or approved")
    for field in ("approver", "evidence"):
        if approval[field] is not None:
            _substantive(approval[field], f"/approval/{field}")
    if approval["approvedVersion"] is not None and (
        type(approval["approvedVersion"]) is not int
        or approval["approvedVersion"] < 1
    ):
        fail("E_REPORT_SCHEMA", "/approval/approvedVersion", "invalid approved version")
    if approval["approvedSourceDigest"] is not None and not re.fullmatch(
        r"sha256:[0-9a-f]{64}", str(approval["approvedSourceDigest"])
    ):
        fail("E_REPORT_SCHEMA", "/approval/approvedSourceDigest", "invalid approved digest")
    generated = report.get("generated")
    if (
        not isinstance(generated, dict)
        or set(generated) != {"toolVersion", "viewDigest"}
        or generated["toolVersion"] not in ("3.5.0", "3.5.1", "3.5.2", TOOL_VERSION)
        or (
            generated["viewDigest"] is not None
            and not re.fullmatch(
                r"sha256:[0-9a-f]{64}", str(generated["viewDigest"])
            )
        )
    ):
        fail("E_REPORT_SCHEMA", "/generated", "invalid generated metadata")
    for pointer, reference in (
        ("/approval/evidence", approval["evidence"]),
        ("/approval/carryForward", approval["carryForward"]),
        ("/overlay/approvalEvidence", report["overlay"].get("approvalEvidence")),
    ):
        _validate_opaque_reference(reference, pointer)
    for index, item in enumerate(report["superseded"]):
        if isinstance(item, dict):
            _validate_opaque_reference(
                item.get("approvalEvidence"),
                f"/superseded/{index}/approvalEvidence",
            )
    if report != _sort_report(json.loads(json.dumps(report))):
        fail("E_REPORT_ORDER", "/", "report arrays are not deterministically sorted")


def _validate_opaque_reference(value, pointer):
    if value is None:
        return
    if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value:
        fail("E_REFERENCE", pointer, "expected a stable single-line reference")
    if (
        "://" in value
        or value.startswith(("/", "\\", "~/", "~\\"))
        or re.match(r"^[A-Za-z]:[\\/]", value)
        or ".." in PurePosixPath(value.replace("\\", "/")).parts
    ):
        fail(
            "E_REFERENCE",
            pointer,
            "reference must be project-relative or stable opaque text",
        )


def _validate_relative_path(value, pointer):
    if not isinstance(value, str) or not value or "\\" in value:
        fail("E_PATH_CONFINEMENT", pointer, "expected project-relative POSIX path")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or "." in parsed.parts or ".." in parsed.parts:
        fail("E_PATH_CONFINEMENT", pointer, "expected project-relative POSIX path")


def _substantive(value, pointer):
    if not _is_substantive(value):
        fail("E_CANONICAL_CONTENT", pointer, "must contain substantive content")
    return value.strip()


def _structured_section(value, pointer):
    if isinstance(value, str):
        return _substantive(value, pointer)
    if not isinstance(value, dict):
        fail(
            "E_CANONICAL_TYPE",
            pointer,
            "must be substantive text or a named object",
        )
    if not value:
        fail("E_CANONICAL_CONTENT", pointer, "must contain substantive content")
    lines = []
    normalized_names = set()
    for name in sorted(value):
        if (
            not isinstance(name, str)
            or not name.strip()
            or name != name.strip()
            or PLACEHOLDER.fullmatch(name)
        ):
            fail(
                "E_CANONICAL_TYPE",
                pointer,
                "named object keys must be stable substantive strings",
            )
        normalized = name.casefold()
        if normalized in normalized_names:
            fail(
                "E_CANONICAL_TYPE",
                pointer,
                "named object keys must be unique after normalization",
            )
        normalized_names.add(normalized)
        content = _substantive(value[name], f"{pointer}/{name}")
        lines.append(f"- {name}: {content}")
    return "\n".join(lines)


def _list_value(value, pointer):
    if isinstance(value, str):
        items = []
        for line in value.splitlines():
            item = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
            if item:
                items.append(item)
    elif isinstance(value, list):
        items = value
    else:
        fail("E_CANONICAL_TYPE", pointer, "must be an array")
    if not items:
        fail("E_CANONICAL_CONTENT", pointer, "must contain substantive content")
    return [_substantive(item, f"{pointer}/{index}") for index, item in enumerate(items)]


def _overlay_requirements(value, kind):
    pattern = FR_LINE if kind == "FR" else AC_LINE
    result = []
    for line in value.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        if kind == "FR":
            identifier, text = match.groups()
            if not identifier:
                fail(
                    "E_REQUIREMENT_ID",
                    "/overlay/sections/functionalRequirements",
                    "overlay requirements require explicit FR-* identifiers",
                )
            result.append({"id": identifier, "text": text.strip()})
        else:
            identifier, mapping_text, text = match.groups()
            if not identifier:
                fail(
                    "E_REQUIREMENT_ID",
                    "/overlay/sections/acceptanceCriteria",
                    "overlay criteria require explicit AC-* identifiers",
                )
            result.append(
                {
                    "id": identifier,
                    "requirements": [
                        ref
                        for ref in REF_PATTERN.findall(mapping_text or "")
                        if ref.startswith("FR-")
                    ],
                    "text": text.strip(),
                }
            )
    return result


def _apply_field(model, field, value):
    if field == "functionalRequirements":
        if not isinstance(value, str):
            fail("E_CANONICAL_TYPE", f"/{field}", "overlay must use canonical Markdown")
        model["requirements"] = _overlay_requirements(value, "FR")
    elif field == "acceptanceCriteria":
        if not isinstance(value, str):
            fail("E_CANONICAL_TYPE", f"/{field}", "overlay must use canonical Markdown")
        model["acceptance"] = _overlay_requirements(value, "AC")
    else:
        model["values"][field] = value


def _resolve_model(raw_model, report):
    model = copy.deepcopy(raw_model)
    review_evidence = report["overlay"]["approvalEvidence"]
    mappings_by_target = {}
    for mapping in report["mappings"]:
        mappings_by_target.setdefault(mapping["target"], []).append(mapping)

    for conflict in raw_model["conflicts"]:
        target = conflict["target"]
        choices = [
            mapping
            for mapping in mappings_by_target.get(target, [])
            if mapping["source"]["selector"] in conflict["sources"]
        ]
        if len(choices) != 1 or choices[0]["confidence"] != "reviewed":
            fail(
                "E_RECONCILIATION_CONFLICT",
                target,
                "ambiguity requires one explicit reviewed selector",
            )
        if not review_evidence:
            fail(
                "E_REVIEW_EVIDENCE",
                "/overlay/approvalEvidence",
                "review approval evidence is required for ambiguity resolution",
            )
        selector = choices[0]["source"]["selector"]
        _apply_field(model, target[1:], raw_model["candidates"][target][selector])

    for field, value in report["overlay"]["sections"].items():
        if field not in FIELD_ALIASES:
            fail("E_OVERLAY_FIELD", f"/overlay/sections/{field}", "unknown canonical field")
        if not review_evidence:
            fail(
                "E_REVIEW_EVIDENCE",
                "/overlay/approvalEvidence",
                "review approval evidence is required for overlays",
            )
        _apply_field(model, field, value)

    unresolved = []
    for item in raw_model["missing"]:
        field = item["target"][1:]
        present = (
            model["requirements"]
            if field == "functionalRequirements"
            else model["acceptance"]
            if field == "acceptanceCriteria"
            else model["values"].get(field)
        )
        if present is None or present == "" or present == [] or present == {}:
            unresolved.append(item)
    model["missing"] = unresolved
    model["conflicts"] = []
    return model


def _validate_model(model):
    if model["missing"]:
        fail(
            "E_RECONCILIATION_MISSING",
            model["missing"][0]["target"],
            "missing canonical field",
        )
    blocking = [item for item in model["conflicts"] if item.get("blocking") is True]
    if blocking:
        fail("E_RECONCILIATION_CONFLICT", blocking[0]["target"], "approval-blocking conflict")
    for field in TEXT_FIELDS:
        if field == "dataSecurity":
            model["values"][field] = _structured_section(
                model["values"].get(field), f"/{field}"
            )
        else:
            model["values"][field] = _substantive(
                model["values"].get(field), f"/{field}"
            )
    for field in ARRAY_FIELDS:
        model["values"][field] = _list_value(model["values"].get(field), f"/{field}")
    decisions = model["values"].get("openDecisions")
    if isinstance(decisions, str):
        model["values"]["openDecisions"] = _list_value(decisions, "/openDecisions")
    elif isinstance(decisions, list):
        if not decisions:
            fail(
                "E_CANONICAL_CONTENT",
                "/openDecisions",
                "must contain substantive content",
            )
        for index, decision in enumerate(decisions):
            pointer = f"/openDecisions/{index}"
            if isinstance(decision, str):
                _substantive(decision, pointer)
                continue
            if not isinstance(decision, dict):
                fail("E_CANONICAL_TYPE", pointer, "must be a string or decision object")
            for component in ("decision", "owner", "resolution"):
                _substantive(decision.get(component), f"{pointer}/{component}")
            if type(decision.get("blocking")) is not bool:
                fail("E_CANONICAL_TYPE", f"{pointer}/blocking", "must be a boolean")
            if decision["blocking"] and decision["resolution"].strip().lower() == "unresolved":
                fail("E_RECONCILIATION_CONFLICT", pointer, "approval-blocking decision")
    else:
        fail("E_CANONICAL_TYPE", "/openDecisions", "must be an array")
    source_approval = model["values"].get("approval")
    if isinstance(source_approval, str):
        source_approval = _approval_fields_from_source(model)
    if not isinstance(source_approval, dict):
        fail("E_CANONICAL_TYPE", "/approval", "must be an approval object")
    normalized_approval = {
        re.sub(r"\s+", "", str(key).lower()): value
        for key, value in source_approval.items()
    }
    for component in ("status", "approver", "evidence"):
        _substantive(normalized_approval.get(component), f"/approval/{component}")
    if (
        model.get("status") == "approved"
        and str(normalized_approval["status"]).strip().lower() != "approved"
    ):
        fail(
            "E_CANONICAL_CONTENT",
            "/approval/status",
            "must contain substantive approved status",
        )
    approved_version = normalized_approval.get(
        "approvedversion", normalized_approval.get("version")
    )
    if type(approved_version) is not int:
        try:
            approved_version = int(approved_version)
        except (TypeError, ValueError):
            fail(
                "E_CANONICAL_TYPE",
                "/approval/approvedVersion",
                "must be a positive integer",
            )
    if approved_version < 1:
        fail(
            "E_CANONICAL_CONTENT",
            "/approval/approvedVersion",
            "must contain substantive content",
        )
    if model.get("version") and approved_version != model["version"]:
        fail(
            "E_APPROVAL_BINDING",
            "/approval/approvedVersion",
            "approved version does not match normalized version",
        )
    if any(not isinstance(item, dict) for item in model["requirements"]):
        fail("E_CANONICAL_TYPE", "/functionalRequirements", "items must be objects")
    identifiers = [item.get("id") for item in model["requirements"]]
    if not identifiers:
        fail(
            "E_CANONICAL_CONTENT",
            "/functionalRequirements",
            "must contain substantive content",
        )
    for index, item in enumerate(model["requirements"]):
        _substantive(item.get("text"), f"/functionalRequirements/{item.get('id', index)}/text")
    if len(identifiers) != len(set(identifiers)) or any(
        not re.fullmatch(r"FR-[1-9][0-9]*", str(item)) for item in identifiers
    ):
        fail("E_REQUIREMENT_ID", "/functionalRequirements", "invalid or duplicate FR identifier")
    if identifiers != sorted(
        identifiers,
        key=lambda item: int(item.split("-", 1)[1])
        if isinstance(item, str) and re.fullmatch(r"FR-[1-9][0-9]*", item)
        else 0,
    ):
        fail(
            "E_REQUIREMENT_ORDER",
            "/functionalRequirements",
            "functional requirements must be in numeric order",
        )
    if any(not isinstance(item, dict) for item in model["acceptance"]):
        fail("E_CANONICAL_TYPE", "/acceptanceCriteria", "items must be objects")
    acceptance_ids = [item.get("id") for item in model["acceptance"]]
    if not acceptance_ids:
        fail(
            "E_CANONICAL_CONTENT",
            "/acceptanceCriteria",
            "must contain substantive content",
        )
    for index, item in enumerate(model["acceptance"]):
        _substantive(item.get("text"), f"/acceptanceCriteria/{item.get('id', index)}/text")
        if not isinstance(item.get("requirements"), list):
            fail(
                "E_CANONICAL_TYPE",
                f"/acceptanceCriteria/{item.get('id', index)}/requirements",
                "must be an array",
            )
    if acceptance_ids != sorted(
        acceptance_ids,
        key=lambda item: int(item.split("-", 1)[1])
        if isinstance(item, str) and re.fullmatch(r"AC-[1-9][0-9]*", item)
        else 0,
    ):
        fail(
            "E_REQUIREMENT_ORDER",
            "/acceptanceCriteria",
            "acceptance criteria must be in numeric order",
        )
    if len(acceptance_ids) != len(set(acceptance_ids)) or any(
        not re.fullmatch(r"AC-[1-9][0-9]*", str(item)) for item in acceptance_ids
    ):
        fail("E_REQUIREMENT_ID", "/acceptanceCriteria", "invalid or duplicate AC identifier")
    known = set(identifiers)
    mapped = set()
    for item in model["acceptance"]:
        if not item["requirements"]:
            fail("E_REQUIREMENT_MAPPING", f"/acceptanceCriteria/{item['id']}", "must map to FR-*")
        for reference in item["requirements"]:
            if reference not in known:
                fail(
                    "E_REQUIREMENT_MAPPING",
                    f"/acceptanceCriteria/{item['id']}",
                    f"unknown functional requirement {reference}",
                )
            mapped.add(reference)
    for identifier in identifiers:
        if identifier not in mapped:
            fail(
                "E_REQUIREMENT_COVERAGE",
                f"/functionalRequirements/{identifier}",
                f"{identifier} has no acceptance criterion",
            )


def _approval_fields_from_source(model):
    value = model["values"].get("approval")
    if isinstance(value, dict):
        return value
    result = {}
    for line in str(value or "").splitlines():
        match = re.match(
            r"^\s*[-*]\s+(Status|Approver|Evidence|Approved version):\s*(.+?)\s*$",
            line,
            re.IGNORECASE,
        )
        if match:
            result[re.sub(r"\s+", "", match.group(1).lower())] = match.group(2)
    return result


def normalized_result(report, model, report_path=None):
    _validate_model(model)
    requirements = sorted(
        (item["id"] for item in model["requirements"]),
        key=lambda item: int(item.split("-")[1]),
    )
    acceptance = sorted(
        (item["id"] for item in model["acceptance"]),
        key=lambda item: int(item.split("-")[1]),
    )
    mappings = {
        item["id"]: item["requirements"]
        for item in sorted(
            model["acceptance"], key=lambda item: int(item["id"].split("-")[1])
        )
    }
    return {
        "schemaVersion": 1,
        **semantic_fields(),
        "path": report["authority"]["artifact"],
        "id": report["prdId"],
        "status": report["normalized"]["status"],
        "declaredStatus": report["normalized"]["status"],
        "version": report["normalized"]["version"],
        "functionalRequirements": requirements,
        "acceptanceCriteria": acceptance,
        "mappings": mappings,
        "approvalEvidencePresent": bool(
            report["approval"]["approver"] and report["approval"]["evidence"]
        ),
        "approvalBlockingDecisions": [
            item["target"] for item in model["conflicts"] if item.get("blocking") is True
        ],
    }


def validate_reconciliation(project_root, report_path, require_approved=False):
    root = Path(project_root).resolve()
    report_file, report_relative = _relative_path(root, report_path, "/report")
    report = strict_load_json(report_file)
    _validate_report_shape(report)
    if report_relative != f".sdlc/reconciliation/{report['prdId']}.json":
        fail(
            "E_REPORT_PATH",
            "/report",
            "report path must match its PRD identity",
            2,
        )
    source_path, source_relative = _relative_path(
        root, report["source"]["path"], "/source/path"
    )
    if source_relative != report["source"]["path"]:
        fail("E_PATH_CONFINEMENT", "/source/path", "source path is not canonical")
    source_content, source_files = _source_bytes(source_path)
    if _digest(source_content) != report["source"]["digest"]:
        fail("E_SOURCE_DRIFT", "/source/digest", "source digest no longer matches")
    if source_files != report["source"]["files"]:
        fail("E_SOURCE_DRIFT", "/source/files", "source file inventory no longer matches")
    existing = {
        item["sourceKey"]: item["targetId"] for item in report["assignedIds"]
    }
    model = parse_source(source_path, report["source"]["kind"], existing)
    if report["prdId"] != model["id"]:
        fail("E_IDENTITY", "/prdId", "report identity does not match source")
    if report["normalized"]["version"] != model["version"]:
        fail("E_IDENTITY", "/normalized/version", "normalized version does not match source")
    if report["normalized"]["status"] != model["status"]:
        fail("E_IDENTITY", "/normalized/status", "normalized status does not match source")
    selectors = model["selectors"]
    for index, mapping in enumerate(report["mappings"]):
        all_selectors = selectors | {
            selector
            for candidates in model["candidates"].values()
            for selector in candidates
        }
        if mapping["source"]["selector"] not in all_selectors:
            fail(
                "E_SELECTOR_STALE",
                f"/mappings/{index}/source/selector",
                "source selector no longer resolves",
            )
    expected_pairs = {
        (item["target"], item["source"]["selector"]) for item in model["mappings"]
    }
    report_pairs = {
        (item["target"], item["source"]["selector"]) for item in report["mappings"]
    }
    if not expected_pairs.issubset(report_pairs):
        fail(
            "E_MAPPING_COMPLETENESS",
            "/mappings",
            "mappings do not cover the normalized source model",
        )
    if sorted(report["assignedIds"], key=lambda item: (item["targetId"], item["sourceKey"])) != sorted(
        model["assigned"], key=lambda item: (item["targetId"], item["sourceKey"])
    ):
        fail(
            "E_ASSIGNED_ID",
            "/assignedIds",
            "assigned IDs do not match the normalized source model",
        )
    model = _resolve_model(model, report)
    _validate_model(model)
    for index, item in enumerate(report["superseded"]):
        if not isinstance(item, dict) or set(item) != {
            "source",
            "replacedBy",
            "reason",
            "approvalEvidence",
        }:
            fail("E_REPORT_SCHEMA", f"/superseded/{index}", "invalid superseded record")
        if item["replacedBy"] not in {
            value["id"] for value in model["requirements"] + model["acceptance"]
        } or not all(item[field] for field in ("source", "reason", "approvalEvidence")):
            fail("E_SUPERSEDED", f"/superseded/{index}", "incomplete superseded record")
    approval_error = _approval_error(report, require_approved)
    if approval_error is not None:
        fail(*approval_error)
    if report["authority"]["mode"] == "generated-view":
        view, _ = _relative_path(
            root, report["authority"]["generatedView"], "/authority/generatedView"
        )
        expected = report["generated"]["viewDigest"]
        expected_content = render_view(report, model, report_relative).encode("utf-8")
        if (
            not expected
            or _digest(view.read_bytes()) != expected
            or view.read_bytes() != expected_content
        ):
            fail("E_VIEW_DRIFT", "/generated/viewDigest", "generated view digest no longer matches")
    elif report["authority"]["artifact"] != report["source"]["path"]:
        fail("E_AUTHORITY", "/authority/artifact", "direct authority must be the source")
    return normalized_result(report, model, report_file)


def render_view(report, model, report_relative):
    values = model["values"]
    approval = report["approval"]
    sections = {
        "Problem and context": values["problemContext"],
        "Target users and benefit": values["targetUsersBenefit"],
        "Outcome": values["outcome"],
        "Goals": "\n".join(f"- {item}" for item in values["goals"]),
        "Non-goals": "\n".join(f"- {item}" for item in values["nonGoals"]),
        "User scenarios": "\n".join(f"- {item}" for item in values["scenarios"]),
        "Functional requirements": "\n".join(
            f"- **{item['id']}**: {item['text']}" for item in model["requirements"]
        ),
        "Acceptance criteria": "\n".join(
            f"- **{item['id']}** (`{', '.join(item['requirements'])}`): {item['text']}"
            for item in model["acceptance"]
        ),
        "Data, permissions, privacy, and security": values["dataSecurity"],
        "Constraints and dependencies": "\n".join(
            f"- {item}" for item in values["constraints"]
        ),
        "Success measures": "\n".join(
            f"- {item}" for item in values["successMeasures"]
        ),
        "Open decisions": "\n".join(
            (
                f"- {item}"
                if isinstance(item, str)
                else (
                    f"- {item['decision']} (owner: {item['owner']}; "
                    f"blocks approval: {'yes' if item['blocking'] else 'no'}; "
                    f"resolution: {item['resolution']})"
                )
            )
            for item in values["openDecisions"]
        ),
        "Approval": "\n".join(
            (
                f"- Status: {approval['status'].title()}",
                f"- Approver: {approval['approver'] or 'Pending'}",
                f"- Evidence: {approval['evidence'] or 'Pending'}",
                f"- Approved version: {approval['approvedVersion'] or report['normalized']['version']}",
            )
        ),
    }
    command = (
        "python PATH_TO_SDLC/scripts/reconcile_artifacts.py render "
        f"--project-root PROJECT_ROOT --report {report_relative} "
        f"--output {report['authority']['generatedView']}"
    )
    notice = "\n".join(
        (
            "<!-- GENERATED FILE: do not edit generated regions. -->",
            f"<!-- Source: {report['source']['path']} -->",
            f"<!-- Source digest: {report['source']['digest']} -->",
            f"<!-- Reconciliation report: {report_relative} -->",
            f"<!-- Generation command: {command} -->",
        )
    )
    body = "\n\n".join(f"## {heading}\n{content}" for heading, content in sections.items())
    return (
        "---\n"
        "type: prd\n"
        f"id: {report['prdId']}\n"
        f"status: {report['normalized']['status']}\n"
        f"version: {report['normalized']['version']}\n"
        "---\n\n"
        f"{notice}\n\n# Product requirements: {report['prdId']}\n\n{body}\n"
    )


def inspect_command(arguments):
    root = arguments.project_root.resolve()
    source, _ = _relative_path(root, arguments.source, "/source/path")
    model = parse_source(source, arguments.kind)
    result = {
        "schemaVersion": 1,
        "id": model["id"],
        "version": model["version"],
        "status": model["status"],
        "functionalRequirements": [item["id"] for item in model["requirements"]],
        "acceptanceCriteria": [item["id"] for item in model["acceptance"]],
        "mappedCount": len(model["mappings"]),
        "missingCount": len(model["missing"]),
        "conflictCount": len(model["conflicts"]),
    }
    print(json.dumps(result, indent=2, sort_keys=True))


def reconcile_command(arguments):
    root = arguments.project_root.resolve()
    source, source_relative = _relative_path(root, arguments.source, "/source/path")
    report_path, report_relative = _relative_path(
        root, arguments.report, "/report", must_exist=False
    )
    view_path = None
    view_relative = None
    if arguments.view:
        view_path, view_relative = _relative_path(
            root, arguments.view, "/view", must_exist=False
        )
    existing_report = None
    if not report_path.exists() and (arguments.update or arguments.replace):
        fail(
            "E_REPORT_MISSING",
            "/report",
            "report does not exist; omit --update/--replace to create it",
        )
    if report_path.exists():
        if not arguments.update and not arguments.replace:
            fail(
                "E_REPORT_EXISTS",
                "/report",
                "report exists; use --update or --replace with destructive confirmation",
            )
        if arguments.replace:
            if arguments.confirm_destructive_replace is None:
                fail(
                    "E_REPLACE_CONFIRMATION",
                    "/report",
                    "--replace requires --confirm-destructive-replace PRD_ID",
                )
            existing_report = _read_existing_report(report_path)
            if arguments.confirm_destructive_replace != existing_report["prdId"]:
                fail(
                    "E_REPLACE_CONFIRMATION",
                    "/report",
                    "destructive confirmation must equal the existing PRD ID",
                )
            existing_report = None
        else:
            existing_report = _read_existing_report(report_path)
            if (
                arguments.view is None
                and existing_report["authority"]["mode"] == "generated-view"
            ):
                view_path, view_relative = _relative_path(
                    root,
                    existing_report["authority"]["generatedView"],
                    "/view",
                    must_exist=False,
                )
    report, model = build_report(
        root,
        source,
        source_relative,
        arguments.kind,
        report_relative,
        view_relative,
        existing_report,
    )
    expected_report = f".sdlc/reconciliation/{report['prdId']}.json"
    if report_relative != expected_report:
        fail("E_REPORT_PATH", "/report", f"report must be stored at {expected_report}", 2)
    if view_path:
        model = _resolve_model(model, report)
        _validate_model(model)
        rendered = render_view(report, model, report_relative)
        atomic_write_text(view_path, rendered)
        report["generated"]["viewDigest"] = _digest(rendered.encode("utf-8"))
    atomic_write_text(
        report_path, json.dumps(_sort_report(report), indent=2, sort_keys=True) + "\n"
    )
    print(
        json.dumps(
            {
                "report": report_relative,
                "authority": report["authority"]["mode"],
                "approval": "draft",
            },
            indent=2,
            sort_keys=True,
        )
    )


def validate_command(arguments):
    result = validate_reconciliation(
        arguments.project_root,
        arguments.report,
        arguments.require_approved,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


def render_command(arguments):
    root = arguments.project_root.resolve()
    report_path, report_relative = _relative_path(root, arguments.report, "/report")
    report = strict_load_json(report_path)
    _validate_report_shape(report)
    if report["authority"]["mode"] != "generated-view":
        fail("E_AUTHORITY", "/authority/mode", "render requires generated-view authority")
    output, output_relative = _relative_path(
        root, arguments.output, "/output", must_exist=False
    )
    if output_relative != report["authority"]["generatedView"]:
        fail("E_AUTHORITY", "/output", "output is not the nominated generated view")
    source, _ = _relative_path(root, report["source"]["path"], "/source/path")
    existing = {
        item["sourceKey"]: item["targetId"] for item in report["assignedIds"]
    }
    model = parse_source(source, report["source"]["kind"], existing)
    source_content, source_files = _source_bytes(source)
    if (
        _digest(source_content) != report["source"]["digest"]
        or source_files != report["source"]["files"]
    ):
        fail("E_SOURCE_DRIFT", "/source", "source provenance no longer matches")
    model = _resolve_model(model, report)
    _validate_model(model)
    rendered = render_view(report, model, report_relative)
    atomic_write_text(output, rendered)
    report["generated"]["viewDigest"] = _digest(rendered.encode("utf-8"))
    atomic_write_text(report_path, json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": output_relative, "digest": report["generated"]["viewDigest"]}, indent=2, sort_keys=True))


def parser():
    root = argparse.ArgumentParser(
        description="Inspect, reconcile, validate, and render local requirement artifacts."
    )
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("inspect", "reconcile"):
        command = commands.add_parser(name)
        command.add_argument("--project-root", required=True, type=Path)
        command.add_argument("--source", required=True, type=Path)
        command.add_argument("--kind", required=True, choices=SOURCE_KINDS)
        if name == "reconcile":
            command.add_argument("--report", required=True, type=Path)
            command.add_argument("--view", type=Path)
            mode = command.add_mutually_exclusive_group()
            mode.add_argument("--update", action="store_true")
            mode.add_argument("--replace", action="store_true")
            command.add_argument("--confirm-destructive-replace")
    validate = commands.add_parser("validate")
    validate.add_argument("--project-root", required=True, type=Path)
    validate.add_argument("--report", required=True, type=Path)
    validate.add_argument("--require-approved", action="store_true")
    render = commands.add_parser("render")
    render.add_argument("--project-root", required=True, type=Path)
    render.add_argument("--report", required=True, type=Path)
    render.add_argument("--output", required=True, type=Path)
    return root


def main(argv=None):
    try:
        arguments = parser().parse_args(argv)
        {
            "inspect": inspect_command,
            "reconcile": reconcile_command,
            "validate": validate_command,
            "render": render_command,
        }[arguments.command](arguments)
        return 0
    except ReconciliationError as error:
        print(error.cli_message(), file=sys.stderr)
        return error.exit_code
    except ContractIssue as error:
        print(error.cli_message(), file=sys.stderr)
        return error.exit_code
    except (OSError, ValueError, TypeError, KeyError) as error:
        issue = ReconciliationError("E_RECONCILIATION", "/", str(error))
        print(issue.cli_message(), file=sys.stderr)
        return issue.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
