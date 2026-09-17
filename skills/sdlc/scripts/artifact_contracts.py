"""Strict, deterministic contracts shared by SDLC artifact commands."""

import json
import re
from pathlib import Path, PurePosixPath


MAX_INPUT_BYTES = 2 * 1024 * 1024
NOTICE = (
    "Structural validation does not approve product decisions, evidence quality, "
    "risk acceptance, or PR readiness."
)
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REF_PATTERN = re.compile(r"^(?:FR|AC)-[1-9][0-9]*$")
PLACEHOLDER = re.compile(
    r"^(?:tbd|todo|none provided|not approved|draft|n/?a|placeholder)$",
    re.IGNORECASE,
)
URL_LIKE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]{1,}:")


class ContractIssue(ValueError):
    def __init__(self, code, pointer=None, message=None, exit_code=3):
        if message is None:
            message = code
            code = "E_CONTRACT"
            pointer = pointer or "/"
        super().__init__(message)
        self.code = code
        self.pointer = pointer
        self.message = message
        self.exit_code = exit_code

    def cli_message(self):
        line = f"error[{self.code}] {self.pointer}: {self.message}".replace(
            "\r", " "
        ).replace("\n", " ")
        return line[:240]


class _Pairs:
    def __init__(self, pairs):
        self.pairs = pairs


def _escape_pointer(value):
    return str(value).replace("~", "~0").replace("/", "~1")


def _materialize(value, pointer=""):
    if isinstance(value, _Pairs):
        result = {}
        for key, child in value.pairs:
            child_pointer = f"{pointer}/{_escape_pointer(key)}"
            if key in result:
                raise ContractIssue(
                    "E_JSON_DUPLICATE",
                    child_pointer or "/",
                    f'duplicate object key "{key}"',
                    2,
                )
            result[key] = _materialize(child, child_pointer)
        return result
    if isinstance(value, list):
        return [
            _materialize(child, f"{pointer}/{index}")
            for index, child in enumerate(value)
        ]
    return value


def strict_load_json(path):
    path = Path(path)
    if str(path) == "-" or URL_LIKE.match(str(path)):
        raise ContractIssue("E_LOCAL_PATH", str(path), "expected a local filesystem path", 2)
    try:
        size = path.stat().st_size
    except OSError as error:
        raise ContractIssue("E_INPUT_READ", str(path), "cannot read local file", 2) from error
    if size > MAX_INPUT_BYTES:
        raise ContractIssue(
            "E_INPUT_TOO_LARGE",
            str(path),
            f"input exceeds {MAX_INPUT_BYTES} bytes",
            2,
        )
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeError as error:
        raise ContractIssue("E_UTF8", str(path), "input is not valid UTF-8", 2) from error
    except OSError as error:
        raise ContractIssue("E_INPUT_READ", str(path), "cannot read local file", 2) from error
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_Pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"invalid constant {value}")
            ),
        )
    except json.JSONDecodeError as error:
        raise ContractIssue(
            "E_JSON_SYNTAX",
            str(path),
            f"malformed JSON at line {error.lineno} column {error.colno}",
            2,
        ) from error
    except ValueError as error:
        raise ContractIssue("E_JSON_SYNTAX", str(path), str(error), 2) from error
    return _materialize(parsed)


def semantic_fields():
    return {
        "contractValid": True,
        "semanticApproval": "not-assessed",
        "notice": NOTICE,
    }


def require_object(value, pointer, allowed, required=None):
    if not isinstance(value, dict):
        raise ContractIssue("E_SCHEMA_TYPE", pointer, "expected object")
    required = set(required if required is not None else allowed)
    for field in allowed:
        if field in required and field not in value:
            raise ContractIssue(
                "E_SCHEMA_REQUIRED", f"{pointer}/{field}", "required field is missing"
            )
    for field in value:
        if field not in allowed:
            raise ContractIssue(
                "E_SCHEMA_UNKNOWN",
                f"{pointer}/{_escape_pointer(field)}",
                "unknown field",
            )
    return value


def require_array(value, pointer, nonempty=False):
    if not isinstance(value, list):
        raise ContractIssue("E_SCHEMA_TYPE", pointer, "expected array")
    if nonempty and not value:
        raise ContractIssue("E_SCHEMA_REQUIRED", pointer, "must not be empty")
    return value


def require_string(value, pointer, substantive=False, maximum=None):
    if not isinstance(value, str):
        raise ContractIssue("E_SCHEMA_TYPE", pointer, "expected string")
    if "\n" in value or "\r" in value:
        raise ContractIssue("E_SCHEMA_STRING", pointer, "must be a single line")
    if substantive and (not value.strip() or PLACEHOLDER.fullmatch(value.strip())):
        raise ContractIssue("E_SCHEMA_CONTENT", pointer, "must contain substantive content")
    if maximum is not None and len(value) > maximum:
        raise ContractIssue("E_SCHEMA_STRING", pointer, f"must be at most {maximum} characters")
    return value


def require_string_array(value, pointer, nonempty=False, substantive=False):
    items = require_array(value, pointer, nonempty)
    seen = set()
    for index, item in enumerate(items):
        require_string(item, f"{pointer}/{index}", substantive=substantive)
        if item in seen:
            raise ContractIssue(
                "E_SCHEMA_UNIQUE", f"{pointer}/{index}", f'duplicate value "{item}"'
            )
        seen.add(item)
    return items


def _reference_key(identifier):
    return (0 if identifier.startswith("FR-") else 1, int(identifier.split("-")[1]))


def _validate_reference_array(value, pointer, prefix=None):
    items = require_string_array(value, pointer)
    for index, item in enumerate(items):
        if not REF_PATTERN.fullmatch(item) or (
            prefix is not None and not item.startswith(prefix)
        ):
            raise ContractIssue("E_REQUIREMENT_ID", f"{pointer}/{index}", "invalid requirement ID")
    if items != sorted(items, key=_reference_key):
        raise ContractIssue("E_REQUIREMENT_ORDER", pointer, "requirement IDs must be in numeric order")
    return items


def _local_posix_path(value, pointer):
    require_string(value, pointer, substantive=True)
    parsed = PurePosixPath(value)
    if (
        "\\" in value
        or parsed.is_absolute()
        or "." in parsed.parts
        or ".." in parsed.parts
        or str(parsed) != value
    ):
        raise ContractIssue(
            "E_PATH_CONFINEMENT", pointer, "expected a project-relative POSIX path"
        )
    return value


def confined_project_path(root, relative, pointer):
    _local_posix_path(relative, pointer)
    root = Path(root).resolve()
    result = root.joinpath(*PurePosixPath(relative).parts).resolve()
    if result != root and root not in result.parents:
        raise ContractIssue("E_PATH_CONFINEMENT", pointer, "path must stay within the project")
    return result


def _validate_applicability(value, pointer):
    require_object(value, pointer, ("applicability", "details", "reason"))
    applicability = value["applicability"]
    if applicability not in ("applicable", "not-applicable"):
        raise ContractIssue(
            "E_HANDOFF_APPLICABILITY",
            f"{pointer}/applicability",
            "expected applicable or not-applicable",
        )
    details = require_string_array(
        value["details"], f"{pointer}/details", substantive=True
    )
    reason = value["reason"]
    if applicability == "applicable":
        if not details:
            raise ContractIssue("E_HANDOFF_DETAILS", f"{pointer}/details", "must not be empty")
        if reason is not None:
            raise ContractIssue("E_HANDOFF_REASON", f"{pointer}/reason", "expected null")
    else:
        if details:
            raise ContractIssue("E_HANDOFF_DETAILS", f"{pointer}/details", "expected an empty array")
        require_string(reason, f"{pointer}/reason", substantive=True)


def validate_handoff_model(
    data,
    path,
    project_root=None,
    validate_prd=None,
    validate_reconciliation=None,
):
    fields = (
        "schemaVersion", "title", "outcome", "prd", "requirements", "scope",
        "acceptanceEvidence", "review", "compatibility", "rollout", "rollback",
        "risks", "limitations", "deferredWork", "repositoryState",
        "configuredDisabledModules", "blockers",
    )
    require_object(data, "", fields)
    if data["schemaVersion"] != 1:
        raise ContractIssue("E_SCHEMA_VERSION", "/schemaVersion", "expected 1")
    title = require_string(data["title"], "/title", substantive=True, maximum=120)
    if not re.match(r"^[A-Z][A-Za-z0-9]", title):
        raise ContractIssue("E_HANDOFF_TITLE", "/title", "expected imperative title")
    require_string(data["outcome"], "/outcome", substantive=True)

    prd = data["prd"]
    if not isinstance(prd, dict) or "applicability" not in prd:
        raise ContractIssue("E_SCHEMA_REQUIRED", "/prd/applicability", "required field is missing")
    identity_matched = False
    local_prd = None
    if prd["applicability"] == "applicable":
        native_identity = "path" in prd
        reconciled_identity = {
            "artifact",
            "reconciliation",
        }.issubset(prd)
        if native_identity == reconciled_identity:
            raise ContractIssue(
                "E_HANDOFF_PRD",
                "/prd",
                "expected either path or artifact with reconciliation",
            )
        require_object(
            prd, "/prd",
            (
                ("applicability", "path", "id", "version", "declaredStatus")
                if native_identity
                else (
                    "applicability",
                    "artifact",
                    "reconciliation",
                    "id",
                    "version",
                    "declaredStatus",
                )
            ),
        )
        if native_identity:
            _local_posix_path(prd["path"], "/prd/path")
        else:
            _local_posix_path(prd["artifact"], "/prd/artifact")
            _local_posix_path(prd["reconciliation"], "/prd/reconciliation")
        if not isinstance(prd["id"], str) or not ID_PATTERN.fullmatch(prd["id"]):
            raise ContractIssue("E_HANDOFF_PRD_ID", "/prd/id", "expected kebab-case ID")
        if type(prd["version"]) is not int or prd["version"] < 1:
            raise ContractIssue("E_HANDOFF_PRD_VERSION", "/prd/version", "expected positive integer")
        if prd["declaredStatus"] not in ("draft", "approved", "superseded"):
            raise ContractIssue("E_HANDOFF_PRD_STATUS", "/prd/declaredStatus", "invalid declared status")
        if project_root is not None:
            if native_identity:
                local_path = confined_project_path(
                    project_root, prd["path"], "/prd/path"
                )
                if validate_prd is None:
                    raise RuntimeError("validate_prd callback is required")
                local_prd = validate_prd(local_path, require_approved=False)
            else:
                local_artifact = confined_project_path(
                    project_root, prd["artifact"], "/prd/artifact"
                )
                local_report = confined_project_path(
                    project_root,
                    prd["reconciliation"],
                    "/prd/reconciliation",
                )
                if validate_reconciliation is None:
                    raise RuntimeError(
                        "validate_reconciliation callback is required"
                    )
                local_prd = validate_reconciliation(
                    project_root, local_report, require_approved=False
                )
                expected_artifact = confined_project_path(
                    project_root,
                    local_prd["path"],
                    "/prd/artifact",
                )
                if local_artifact != expected_artifact:
                    raise ContractIssue(
                        "E_HANDOFF_PRD_IDENTITY",
                        "/prd/artifact",
                        "artifact does not match reconciliation authority",
                    )
            if local_prd["id"] != prd["id"] or local_prd["version"] != prd["version"]:
                raise ContractIssue(
                    "E_HANDOFF_PRD_IDENTITY", "/prd", "identity does not match local PRD"
                )
            identity_matched = True
    elif prd["applicability"] == "not-applicable":
        require_object(prd, "/prd", ("applicability", "reason"))
        require_string(prd["reason"], "/prd/reason", substantive=True)
    else:
        raise ContractIssue("E_HANDOFF_PRD", "/prd/applicability", "invalid applicability")

    requirements = require_object(
        data["requirements"], "/requirements", ("functional", "acceptance", "delivered")
    )
    functional = _validate_reference_array(requirements["functional"], "/requirements/functional", "FR-")
    acceptance = _validate_reference_array(requirements["acceptance"], "/requirements/acceptance", "AC-")
    delivered = _validate_reference_array(requirements["delivered"], "/requirements/delivered")
    if local_prd is not None:
        local_references = set(
            local_prd["functionalRequirements"] + local_prd["acceptanceCriteria"]
        )
        for reference in functional + acceptance:
            if reference not in local_references:
                raise ContractIssue(
                    "E_HANDOFF_PRD_REQUIREMENT",
                    "/requirements",
                    f"{reference} is absent from the local PRD",
                )
    declared = set(functional + acceptance)
    for index, reference in enumerate(delivered):
        if reference not in declared:
            raise ContractIssue(
                "E_HANDOFF_REQUIREMENT", f"/requirements/delivered/{index}",
                f"{reference} is not declared",
            )

    require_string_array(data["scope"], "/scope", nonempty=True, substantive=True)
    evidence_fields = (
        "acceptanceCriterion", "kind", "command", "result", "revision", "summary"
    )
    evidenced = set()
    failed = []
    for index, item in enumerate(require_array(data["acceptanceEvidence"], "/acceptanceEvidence")):
        pointer = f"/acceptanceEvidence/{index}"
        require_object(item, pointer, evidence_fields)
        criterion = item["acceptanceCriterion"]
        if criterion not in acceptance:
            raise ContractIssue("E_HANDOFF_EVIDENCE_AC", f"{pointer}/acceptanceCriterion", "unknown acceptance criterion")
        require_string(item["kind"], f"{pointer}/kind", substantive=True)
        require_string(item["command"], f"{pointer}/command", substantive=True)
        require_string(item["revision"], f"{pointer}/revision", substantive=True)
        require_string(item["summary"], f"{pointer}/summary", substantive=True)
        if item["result"] not in ("passed", "failed", "not-run", "unavailable"):
            raise ContractIssue("E_HANDOFF_EVIDENCE_RESULT", f"{pointer}/result", "invalid evidence result")
        evidenced.add(criterion)
        if item["result"] != "passed":
            failed.append(
                {
                    "acceptanceCriterion": criterion,
                    "result": item["result"],
                    "summary": item["summary"],
                }
            )
    for criterion in delivered:
        if criterion.startswith("AC-") and criterion not in evidenced:
            raise ContractIssue(
                "E_HANDOFF_AC_EVIDENCE", "/acceptanceEvidence",
                f"missing evidence for {criterion}",
            )

    review = require_object(
        data["review"], "/review", ("perspectives", "findingsResolved", "unavailable")
    )
    require_string_array(review["perspectives"], "/review/perspectives")
    require_string_array(review["findingsResolved"], "/review/findingsResolved", substantive=True)
    for index, item in enumerate(require_array(review["unavailable"], "/review/unavailable")):
        pointer = f"/review/unavailable/{index}"
        require_object(item, pointer, ("perspective", "reason"))
        require_string(item["perspective"], f"{pointer}/perspective", substantive=True)
        require_string(item["reason"], f"{pointer}/reason", substantive=True)

    for name in ("compatibility", "rollout", "rollback"):
        _validate_applicability(data[name], f"/{name}")
    for name in (
        "risks", "limitations", "deferredWork", "configuredDisabledModules", "blockers"
    ):
        require_string_array(data[name], f"/{name}", substantive=True)

    state = require_object(
        data["repositoryState"], "/repositoryState",
        ("statusInspected", "completeDiffInspected", "revision", "unrelatedChanges"),
    )
    for name in ("statusInspected", "completeDiffInspected"):
        if state[name] is not True:
            raise ContractIssue(
                "E_HANDOFF_REPOSITORY_STATE", f"/repositoryState/{name}",
                "expected true",
            )
    require_string(state["revision"], "/repositoryState/revision", substantive=True)
    require_string_array(
        state["unrelatedChanges"], "/repositoryState/unrelatedChanges", substantive=True
    )
    evidence_blockers = [
        f"{item['acceptanceCriterion']} evidence {item['result']}"
        for item in failed
    ]
    blockers = list(data["blockers"])
    for blocker in evidence_blockers:
        if blocker not in blockers:
            blockers.append(blocker)
    return {
        "schemaVersion": 1,
        **semantic_fields(),
        "path": str(Path(path).resolve()),
        "prd": (
            {
                "applicability": "applicable",
                "id": prd["id"],
                "version": prd["version"],
                "identityMatchedLocalArtifact": identity_matched,
            }
            if prd["applicability"] == "applicable"
            else {"applicability": "not-applicable"}
        ),
        "deliveredRequirements": delivered,
        "evidencedAcceptanceCriteria": sorted(evidenced, key=_reference_key),
        "failedOrUnavailableEvidence": failed,
        "configuredDisabledModules": data["configuredDisabledModules"],
        "blockers": blockers,
    }


def validate_prd(path, require_approved=True):
    """Validate a PRD through the compatibility-preserving parser."""
    from validate_artifacts import validate_prd as implementation

    return implementation(path, require_approved=require_approved)


def validate_plan(path, project_root=None):
    """Validate a plan through the compatibility-preserving parser."""
    from validate_artifacts import validate_plan as implementation

    return implementation(path, project_root=project_root)
