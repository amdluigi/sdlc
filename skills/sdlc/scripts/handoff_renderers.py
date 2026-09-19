"""Deterministic, local-only Markdown rendering for normalized SDLC handoffs."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from artifact_contracts import ContractIssue, MAX_INPUT_BYTES, URL_LIKE


MARKER = "<!-- SDLC:HANDOFF -->"
FORGES = {
    "github": "Pull request handoff",
    "gitlab": "Merge request handoff",
    "azure-devops": "Pull request handoff",
}


def _markdown(value):
    text = str(value)
    for source, replacement in (
        ("\\", "\\\\"),
        ("*", "\\*"),
        ("_", "\\_"),
        ("[", "\\["),
        ("]", "\\]"),
        ("<", "\\<"),
        (">", "\\>"),
        ("|", "\\|"),
    ):
        text = text.replace(source, replacement)
    return text


def _code(value):
    text = str(value).replace("\\", "\\\\").replace("|", "\\|")
    fence = "`"
    while fence in text:
        fence += "`"
    return f"{fence}{text}{fence}"


def _joined(values, formatter=_markdown, empty="None."):
    return ", ".join(formatter(value) for value in values) if values else empty


def _bullets(values, empty="None."):
    if not values:
        return [f"- {empty}"]
    return [f"- {_markdown(value)}" for value in values]


def _applicability(value):
    if value["applicability"] == "not-applicable":
        return [f"Not applicable: {_markdown(value['reason'])}"]
    return _bullets(value["details"])


def _product_requirements(handoff):
    prd = handoff["prd"]
    if prd["applicability"] == "not-applicable":
        prd_line = f"- PRD: Not applicable: {_markdown(prd['reason'])}"
    else:
        identity = _code(prd.get("path", prd.get("artifact")))
        prd_line = (
            f"- PRD: {identity} ({_code(prd['id'])}, "
            f"declared version {prd['version']}, status {_code(prd['declaredStatus'])})"
        )
        if "reconciliation" in prd:
            prd_line += f"; reconciliation {_code(prd['reconciliation'])}"
    delivered = handoff["requirements"]["delivered"]
    functional = [value for value in delivered if value.startswith("FR-")]
    acceptance = [value for value in delivered if value.startswith("AC-")]
    return [
        prd_line,
        "- Delivered functional requirements: " + _joined(functional, _code),
        "- Delivered acceptance criteria: " + _joined(acceptance, _code),
    ]


def _evidence(handoff):
    lines = [
        "| Criterion | Kind | Command | Result | Revision | Summary |",
        "|---|---|---|---|---|---|",
    ]
    for item in handoff["acceptanceEvidence"]:
        result = _code(item["result"])
        if item["result"] != "passed":
            result = f"**{result}**"
        lines.append(
            "| "
            + " | ".join(
                (
                    _code(item["acceptanceCriterion"]),
                    _markdown(item["kind"]),
                    _code(item["command"]),
                    result,
                    _code(item["revision"]),
                    _markdown(item["summary"]),
                )
            )
            + " |"
        )
    if len(lines) == 2:
        lines.append("| None | None | None | None | None | None |")
    return lines


def _review(handoff):
    review = handoff["review"]
    lines = [
        "- Perspectives: " + _joined(review["perspectives"]),
        "- Findings resolved: " + _joined(review["findingsResolved"]),
    ]
    if review["unavailable"]:
        lines.append("- Unavailable perspectives:")
        lines.extend(
            f"  - {_markdown(item['perspective'])}: {_markdown(item['reason'])}"
            for item in review["unavailable"]
        )
    else:
        lines.append("- Unavailable perspectives: None.")
    return lines


def _risks_and_limitations(handoff):
    lines = []
    if handoff["risks"]:
        lines.extend(f"- Risks: {_markdown(value)}" for value in handoff["risks"])
    else:
        lines.append("- Risks: None known.")
    if handoff["limitations"]:
        lines.extend(
            f"- Limitations: {_markdown(value)}" for value in handoff["limitations"]
        )
    else:
        lines.append("- Limitations: None known.")
    return lines


def _blockers(handoff):
    lines = _bullets(handoff["blockers"]) if handoff["blockers"] else []
    for item in handoff["acceptanceEvidence"]:
        if item["result"] != "passed":
            lines.append(
                f"- **{_code(item['acceptanceCriterion'])} evidence "
                f"{_markdown(item['result'])}:** {_markdown(item['summary'])}"
            )
    return lines or ["- None."]


def render_handoff(handoff, forge):
    if forge not in FORGES:
        raise ContractIssue("E_FORGE", "/forge", "unsupported forge", 2)
    sections = (
        ("Outcome", [_markdown(handoff["outcome"])]),
        ("Product requirements", _product_requirements(handoff)),
        ("Scope", _bullets(handoff["scope"])),
        ("Non-goals and deferred work", _bullets(handoff["deferredWork"])),
        ("Acceptance evidence", _evidence(handoff)),
        ("Review", _review(handoff)),
        ("Compatibility", _applicability(handoff["compatibility"])),
        ("Rollout", _applicability(handoff["rollout"])),
        ("Rollback", _applicability(handoff["rollback"])),
        ("Risks and limitations", _risks_and_limitations(handoff)),
        ("Blockers", _blockers(handoff)),
        (
            "Configured-disabled modules",
            (
                [f"- {_code(value)}" for value in handoff["configuredDisabledModules"]]
                or ["- None."]
            ),
        ),
    )
    lines = [f"# {_markdown(handoff['title'])}", ""]
    for heading, content in sections:
        lines.extend((f"## {heading}", *content, ""))
    return "\n".join(lines)


def _local_path(path):
    path = Path(path)
    if str(path) == "-" or URL_LIKE.match(str(path)):
        raise ContractIssue(
            "E_LOCAL_PATH", str(path), "expected a local filesystem path", 2
        )
    return path


def read_template(path):
    path = _local_path(path)
    try:
        size = path.stat().st_size
    except OSError as error:
        raise ContractIssue(
            "E_TEMPLATE_READ", str(path), "cannot read local template", 4
        ) from error
    if size > MAX_INPUT_BYTES:
        raise ContractIssue(
            "E_INPUT_TOO_LARGE",
            str(path),
            f"input exceeds {MAX_INPUT_BYTES} bytes",
            4,
        )
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeError as error:
        raise ContractIssue(
            "E_UTF8", str(path), "template is not valid UTF-8", 4
        ) from error
    except OSError as error:
        raise ContractIssue(
            "E_TEMPLATE_READ", str(path), "cannot read local template", 4
        ) from error
    return text.replace("\r\n", "\n").replace("\r", "\n")


def apply_template(template, rendered, path):
    marker_count = template.count(MARKER)
    if marker_count > 1:
        raise ContractIssue(
            "E_TEMPLATE_MARKER", str(path), "marker occurs more than once", 4
        )
    if marker_count == 0:
        if not template:
            return rendered
        separator = "" if template.endswith("\n\n") else (
            "\n" if template.endswith("\n") else "\n\n"
        )
        return template + separator + rendered
    lines = template.splitlines(keepends=True)
    matching = [
        index for index, line in enumerate(lines) if line.rstrip("\n") == MARKER
    ]
    if len(matching) != 1:
        raise ContractIssue(
            "E_TEMPLATE_MARKER",
            str(path),
            "marker must occupy a complete line",
            4,
        )
    lines[matching[0]] = rendered
    result = "".join(lines)
    return result if result.endswith("\n") else result + "\n"


def write_output(path, content, force=False):
    path = _local_path(path)
    parent = path.parent
    if not parent.is_dir():
        raise ContractIssue(
            "E_OUTPUT_PARENT", str(path), "parent directory does not exist", 4
        )
    if path.exists() and not force:
        raise ContractIssue(
            "E_OUTPUT_EXISTS", str(path), "use --force to replace this file", 4
        )
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists() and not force:
            raise ContractIssue(
                "E_OUTPUT_EXISTS", str(path), "use --force to replace this file", 4
            )
        temporary.replace(path)
        temporary = None
    except ContractIssue:
        raise
    except OSError as error:
        raise ContractIssue(
            "E_OUTPUT_WRITE", str(path), "cannot write output file", 4
        ) from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def result_envelope(forge, destination, template_applied, rendered):
    payload = rendered.encode("utf-8")
    return {
        "schemaVersion": 1,
        "command": "render-handoff",
        "valid": True,
        "result": {
            "forge": forge,
            "artifactLabel": FORGES[forge],
            "mediaType": "text/markdown",
            "destination": destination,
            "templateApplied": template_applied,
            "bytes": len(payload),
            "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
            "semanticApproval": "not-assessed",
        },
    }


def metadata_json(value):
    return json.dumps(value, indent=2, sort_keys=True) + "\n"
