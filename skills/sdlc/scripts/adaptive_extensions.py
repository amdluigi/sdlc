import hashlib
import json
import re
import shutil
import stat
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import config_contract


class AdaptiveError(ValueError):
    pass


_KEBAB_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_HOME_PATH_PATTERN = re.compile(
    r"(?:[A-Za-z]:\\Users\\[^\\\s]+|/(?:home|Users)/[^/\s]+)"
)
_SENSITIVE_PATTERN = re.compile(
    r"(?:"
    r"authorization\s*:|"
    r"bearer\s+[A-Za-z0-9._~+/=-]{4,}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"AKIA[0-9A-Z]{16}|"
    r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}|"
    r"(?:password|passwd|token|api[_-]?key|secret|credential)"
    r"\s*[:=]\s*\S+"
    r")",
    re.IGNORECASE,
)
_ESCAPED_REFERENCE_CHARACTERS = frozenset("AbBdDsSwWZfnrtv")
_ESCAPED_REFERENCE_QUANTIFIERS = frozenset("+*?")
_SLASH_COMMANDS = frozenset({"/help", "/review", "/skills"})
_FILE_CONTEXT_WORDS = frozenset(
    {"artifact", "directory", "file", "folder", "location", "path"}
)
_CANDIDATE_STATUSES = {
    "observed",
    "eligible",
    "drafted",
    "accepted",
    "rejected",
    "promoted",
    "superseded",
}
_ALLOWED_TRANSITIONS = {
    "observed": {"eligible"},
    "eligible": {"drafted", "rejected"},
    "drafted": {"accepted", "rejected"},
    "accepted": {"promoted", "superseded"},
    "rejected": {"eligible"},
    "promoted": {"superseded"},
    "superseded": set(),
}
_EXPLICIT_REQUEST_REASON = "Explicit developer request"
_EXTENSION_STATUSES = {
    "drafted",
    "accepted",
    "rejected",
    "promoted",
    "superseded",
}
_EXTENSION_FILES = {"extension.json", "MODULE.md", "evals.json"}
_PROJECT_REFERENCE_CANDIDATE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._:/\\-])"
    r"(?:\.[\\/])?"
    r"(?:[A-Za-z0-9._-]+[\\/])+"
    r"[A-Za-z0-9._-]+"
    r"(?![A-Za-z0-9_-])"
)
_IDENTIFIER_PATTERN = re.compile(
    r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)+"
)
_GENERIC_PATH_PARTS = frozenset(
    {
        "app",
        "docs",
        "internal",
        "lib",
        "release",
        "scripts",
        "src",
        "test",
        "tests",
        "tools",
    }
)
_REPARSE_POINT_ATTRIBUTE = getattr(
    stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
)
_UNSAFE_EXTENSION_PATTERNS = (
    ("network", re.compile(
        r"(?:https?://|\bcurl\b|\bwget\b|"
        r"\binvoke-(?:webrequest|restmethod)\b|"
        r"\brequests\s*\.\s*"
        r"(?:Session\s*\([^)]*\)\s*\.\s*)?"
        r"(?:get|post|put|patch|delete|request|stream)\s*\(|"
        r"\bhttpx\s*\.\s*"
        r"(?:(?:AsyncClient|Client)\s*\([^)]*\)\s*\.\s*)?"
        r"(?:get|post|put|patch|delete|request|stream)\s*\(|"
        r"\baiohttp\s*\.\s*ClientSession\s*\([^)]*\)\s*\.\s*"
        r"(?:get|post|put|patch|delete|request)\s*\(|"
        r"\burllib(?:\.request)?\s*\.\s*"
        r"(?:urlopen|urlretrieve|request)\b|"
        r"\b(?:upload_file|upload_fileobj|put_object)\s*\(|"
        r"\b(?:http\.client|ftplib|smtplib)\b|"
        r"\b(?:make|perform|send|use)\s+(?:a\s+)?network\s+"
        r"(?:access|request|call))",
        re.IGNORECASE,
    )),
    ("publish", re.compile(
        r"(?:\b(?:cargo|npm|pnpm|yarn)\s+publish\b|"
        r"\b(?:python\s+-m\s+)?twine\s+upload\b|"
        r"\bdotnet\s+nuget\s+push\b|"
        r"\bgem\s+push\b|"
        r"\bgit\s+push\b|"
        r"\b(?:open|publish|submit)\s+(?:a\s+|the\s+|this\s+)?"
        r"(?:content|extension|package|pull request)\b)",
        re.IGNORECASE,
    )),
    ("core", re.compile(
        r"(?:\b(?:change|edit|modify|mutate|override|replace|update|write)\s+"
        r"(?:the\s+)?(?:installed|global)(?:\s+sdlc)?\s+"
        r"(?:core|skill|installation)\b|"
        r"\b(?:bypass|disable|override|replace)\s+(?:the\s+)?"
        r"(?:core|testing|security|review|evidence)\b)",
        re.IGNORECASE,
    )),
    ("raw", re.compile(
        r"\b(?:copy|export|include|persist|record|save|store|write)\s+"
        r"(?:the\s+)?(?:"
        r"(?:raw|original|unredacted|unchanged|verbatim)\s+"
        r"(?:content|issue|log|prompt|review)s?|"
        r"raw[_ -](?:content|issue|log|prompt|review)s?"
        r")\b",
        re.IGNORECASE,
    )),
)
_WRITE_VERB_PATTERN = re.compile(
    r"\b(?:change|copy|edit|export|modify|move|persist|replace|save|store|"
    r"update|write)\b",
    re.IGNORECASE,
)
_INSTALLED_SKILL_PATH_PATTERN = re.compile(
    r"(?:~[\\/]|/(?:home|Users)/[^/\s]+[\\/]|"
    r"[A-Za-z]:[\\/]Users[\\/][^\\/\s]+[\\/])"
    r"(?:\.agents|\.claude)[\\/]skills[\\/]"
    r"[A-Za-z0-9][A-Za-z0-9-]*(?:[\\/]|$)",
    re.IGNORECASE,
)
_ACTIONABLE_CLAUSE_BOUNDARY_PATTERN = re.compile(
    r"(?<=[.!?;])\s+(?=(?:[-*]\s*)?"
    r"(?:do not|must not|never|call|change|copy|disable|edit|export|"
    r"explain|document|modify|move|open|persist|publish|replace|run|"
    r"save|store|submit|update|use|write)\b)|\r?\n+|"
    r"\s+\b(?:and|but|then)\b\s+(?="
    r"(?:do not|must not|never|call|change|copy|disable|edit|export|"
    r"explain|document|modify|move|open|persist|publish|replace|run|"
    r"save|store|submit|update|use|write)\b)",
    re.IGNORECASE,
)
_DOCUMENTATION_CLAUSE_PATTERN = re.compile(
    r"^\s*(?:[-*]\s*)?(?:describe|discuss|document|explain|summarize)\b",
    re.IGNORECASE,
)
_NEGATED_ACTION_PATTERN = re.compile(
    r"(?:do not|must not|never)\s+(?:[A-Za-z-]+\s+){0,2}$",
    re.IGNORECASE,
)


def _validate_text(value, field: str, maximum: int = 200) -> str:
    if not isinstance(value, str):
        raise AdaptiveError(f"{field} must be a string")
    if not value or value != value.strip():
        raise AdaptiveError(f"{field} must be non-empty and trimmed")
    if len(value) > maximum:
        raise AdaptiveError(f"{field} exceeds {maximum} characters")
    if any(character in value for character in ("\r", "\n", "\x00")):
        raise AdaptiveError(f"{field} must be a single-line description")
    if _SENSITIVE_PATTERN.search(value):
        raise AdaptiveError(f"{field} contains sensitive data")
    if _HOME_PATH_PATTERN.search(value):
        raise AdaptiveError(
            f"{field} contains a project-specific absolute path"
        )
    return value


def _validate_kebab(value, field: str) -> str:
    _validate_text(value, field, 64)
    if not _KEBAB_PATTERN.fullmatch(value):
        raise AdaptiveError(f"{field} must be kebab-case")
    return value


def _is_reference_boundary(value: str, index: int) -> bool:
    if index == 0:
        return True
    previous = value[index - 1]
    return not (previous.isalnum() or previous in "._-/\\:")


def _reference_token(value: str, start: int) -> str:
    end = start
    while end < len(value) and not value[end].isspace():
        end += 1
    return value[start:end].rstrip(",.;!?)]}'\"")


def _is_escaped_reference_token(value: str) -> bool:
    index = 0
    while index < len(value):
        if (
            value[index] != "\\"
            or index + 1 >= len(value)
            or value[index + 1] not in _ESCAPED_REFERENCE_CHARACTERS
        ):
            return False
        index += 2
        if (
            index < len(value)
            and value[index] in _ESCAPED_REFERENCE_QUANTIFIERS
        ):
            index += 1
    return True


def _has_file_context(value: str, start: int) -> bool:
    preceding_words = value[:start].casefold().split()
    return any(
        word.strip(",:;=()[]{}") in _FILE_CONTEXT_WORDS
        for word in preceding_words[-2:]
    )


def _is_posix_absolute_reference(
    value: str, start: int, candidate: str
) -> bool:
    if candidate.startswith("//"):
        return False
    if candidate in _SLASH_COMMANDS and not _has_file_context(value, start):
        return False
    return True


def _contains_absolute_reference(value: str) -> bool:
    for index, character in enumerate(value):
        if not _is_reference_boundary(value, index):
            continue

        if (
            character.isalpha()
            and value[index + 1 : index + 2] == ":"
            and value[index + 2 : index + 3] in ("\\", "/")
        ):
            return True

        if character == "/":
            candidate = _reference_token(value, index)
            if _is_posix_absolute_reference(value, index, candidate):
                return True

        if character == "\\":
            candidate = _reference_token(value, index)
            if not _is_escaped_reference_token(candidate):
                return True

        if character == "~" and value[index + 1 : index + 2] in ("\\", "/"):
            return True

    return False


@dataclass(frozen=True)
class Observation:
    task_id: str
    date: str
    summary: str
    category: str
    action: str
    trigger: str
    exit_signal: str
    evidence: tuple[str, ...]
    explicit_request: bool = False

    def __post_init__(self):
        _validate_kebab(self.task_id, "task_id")
        _validate_kebab(self.category, "category")
        _validate_text(self.summary, "summary")
        _validate_text(self.action, "action")
        _validate_text(self.trigger, "trigger")
        _validate_text(self.exit_signal, "exit_signal")
        if not isinstance(self.date, str):
            raise AdaptiveError("date must be an ISO date")
        try:
            parsed_date = date.fromisoformat(self.date)
        except ValueError as error:
            raise AdaptiveError("date must be an ISO date") from error
        if parsed_date.isoformat() != self.date:
            raise AdaptiveError("date must be an ISO date")
        if not isinstance(self.evidence, tuple) or not self.evidence:
            raise AdaptiveError("evidence must be a non-empty tuple")
        if len(self.evidence) > 10:
            raise AdaptiveError("evidence exceeds 10 references")
        for index, reference in enumerate(self.evidence):
            _validate_text(reference, f"evidence[{index}]")
            if _contains_absolute_reference(reference):
                raise AdaptiveError(
                    f"evidence[{index}] must be a relative description"
                )
        if type(self.explicit_request) is not bool:
            raise AdaptiveError("explicit_request must be boolean")


def _normalize_generalized_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def candidate_fingerprint(observation: Observation) -> str:
    if not isinstance(observation, Observation):
        raise AdaptiveError("observation must be an Observation")
    fingerprint_fields = {
        "action": _normalize_generalized_text(observation.action),
        "category": _normalize_generalized_text(observation.category),
        "exitSignal": _normalize_generalized_text(observation.exit_signal),
        "trigger": _normalize_generalized_text(observation.trigger),
    }
    canonical = json.dumps(
        fingerprint_fields,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def _candidate_path(project_root: Path) -> Path:
    return Path(project_root) / ".sdlc" / "learning" / "candidates.json"


def _validate_iso_date(value, field: str) -> None:
    if not isinstance(value, str):
        raise AdaptiveError(f"{field} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise AdaptiveError(f"{field} must be an ISO date") from error
    if parsed.isoformat() != value:
        raise AdaptiveError(f"{field} must be an ISO date")


def _validate_timestamp(value, field: str) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise AdaptiveError(f"{field} must be a UTC timestamp")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise AdaptiveError(f"{field} must be a UTC timestamp") from error


def _validate_evidence(value, field: str) -> None:
    if not isinstance(value, list) or not value or len(value) > 10:
        raise AdaptiveError(f"{field} must contain 1 to 10 references")
    for index, reference in enumerate(value):
        _validate_text(reference, f"{field}[{index}]")
        if _contains_absolute_reference(reference):
            raise AdaptiveError(
                f"{field}[{index}] must be a relative description"
            )


def _validate_candidate(candidate: dict) -> None:
    expected_fields = {
        "id",
        "fingerprint",
        "status",
        "summary",
        "category",
        "occurrences",
        "createdAt",
        "updatedAt",
        "lastDecision",
        "decisionHistory",
    }
    if not isinstance(candidate, dict) or set(candidate) != expected_fields:
        raise AdaptiveError("invalid candidate record")
    _validate_kebab(candidate["id"], "candidate.id")
    if not isinstance(candidate["fingerprint"], str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", candidate["fingerprint"]
    ):
        raise AdaptiveError("invalid candidate fingerprint")
    if candidate["status"] not in _CANDIDATE_STATUSES:
        raise AdaptiveError("invalid candidate status")
    _validate_text(candidate["summary"], "candidate.summary")
    _validate_kebab(candidate["category"], "candidate.category")
    _validate_timestamp(candidate["createdAt"], "candidate.createdAt")
    _validate_timestamp(candidate["updatedAt"], "candidate.updatedAt")

    occurrences = candidate["occurrences"]
    if not isinstance(occurrences, list) or not occurrences:
        raise AdaptiveError("candidate occurrences must be a non-empty array")
    task_ids = set()
    for occurrence in occurrences:
        if not isinstance(occurrence, dict) or set(occurrence) != {
            "date",
            "task",
            "signal",
            "evidence",
        }:
            raise AdaptiveError("invalid candidate occurrence")
        _validate_iso_date(occurrence["date"], "occurrence.date")
        _validate_kebab(occurrence["task"], "occurrence.task")
        if occurrence["task"] in task_ids:
            raise AdaptiveError("duplicate candidate occurrence task")
        task_ids.add(occurrence["task"])
        _validate_text(occurrence["signal"], "occurrence.signal")
        _validate_evidence(occurrence["evidence"], "occurrence.evidence")

    history = candidate["decisionHistory"]
    if not isinstance(history, list):
        raise AdaptiveError("candidate decisionHistory must be an array")
    previous_status = "observed"
    previous_occurrence_count = 0
    rejection_occurrence_count = None
    for decision in history:
        expected_decision_fields = {
            "timestamp",
            "from",
            "to",
            "reason",
            "occurrenceCount",
        }
        if (
            not isinstance(decision, dict)
            or set(decision) not in (
                expected_decision_fields,
                expected_decision_fields | {"kind"},
            )
        ):
            raise AdaptiveError("invalid candidate decision")
        if "kind" in decision:
            _validate_kebab(decision["kind"], "decision.kind")
            if decision["to"] != "promoted":
                raise AdaptiveError(
                    "candidate transition kind is only valid for promotion"
                )
        _validate_timestamp(decision["timestamp"], "decision.timestamp")
        _validate_text(decision["reason"], "decision.reason")
        repeated_promotion = (
            previous_status == "promoted"
            and decision["to"] == "promoted"
            and "kind" in decision
        )
        if decision["from"] != previous_status or (
            decision["to"] not in _ALLOWED_TRANSITIONS[previous_status]
            and not repeated_promotion
        ):
            raise AdaptiveError("invalid candidate decision transition")
        occurrence_count = decision["occurrenceCount"]
        if (
            type(occurrence_count) is not int
            or occurrence_count < 1
            or occurrence_count > len(occurrences)
        ):
            raise AdaptiveError("invalid candidate decision occurrenceCount")
        if occurrence_count < previous_occurrence_count:
            raise AdaptiveError(
                "candidate decision occurrenceCount must not decrease"
            )
        if (
            previous_status == "observed"
            and decision["to"] == "eligible"
            and occurrence_count < 2
            and decision["reason"] != _EXPLICIT_REQUEST_REASON
        ):
            raise AdaptiveError(
                "candidate eligibility requires two distinct tasks "
                "or an explicit request"
            )
        if (
            previous_status == "rejected"
            and decision["to"] == "eligible"
            and occurrence_count <= rejection_occurrence_count
        ):
            raise AdaptiveError(
                "candidate eligibility requires new evidence after rejection"
            )
        if decision["to"] == "rejected":
            rejection_occurrence_count = occurrence_count
        previous_occurrence_count = occurrence_count
        previous_status = decision["to"]
    if candidate["status"] != previous_status:
        raise AdaptiveError("candidate status does not match decision history")
    expected_last = history[-1] if history else None
    if candidate["lastDecision"] != expected_last:
        raise AdaptiveError("candidate lastDecision does not match history")


def _load_candidates(project_root: Path) -> dict:
    path = _candidate_path(project_root)
    if not _require_project_state_path(
        project_root, path, "candidate state", leaf_kind="file"
    ):
        return {"schemaVersion": 1, "candidates": []}
    state = load_json_strict(path)
    if not isinstance(state, dict) or state.get("schemaVersion") != 1:
        raise AdaptiveError("unsupported candidates schema")
    if set(state) != {"schemaVersion", "candidates"}:
        raise AdaptiveError("invalid candidates document")
    if not isinstance(state["candidates"], list):
        raise AdaptiveError("candidates must be an array")
    identifiers = set()
    fingerprints = set()
    for candidate in state["candidates"]:
        _validate_candidate(candidate)
        if candidate["id"] in identifiers:
            raise AdaptiveError("duplicate candidate id")
        if candidate["fingerprint"] in fingerprints:
            raise AdaptiveError("duplicate candidate fingerprint")
        identifiers.add(candidate["id"])
        fingerprints.add(candidate["fingerprint"])
    return state


def _candidate_id(action: str) -> str:
    identifier = re.sub(
        r"[^a-z0-9]+", "-", _normalize_generalized_text(action)
    ).strip("-")
    if not identifier:
        raise AdaptiveError("action must contain letters or numbers")
    return identifier[:64].rstrip("-")


def _timestamp_for_date(value: str) -> str:
    return f"{value}T00:00:00Z"


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _record_transition(
    candidate: dict,
    status: str,
    reason: str,
    timestamp: str,
    *,
    kind: str | None = None,
) -> None:
    source = candidate["status"]
    decision = {
        "timestamp": timestamp,
        "from": source,
        "to": status,
        "reason": reason,
        "occurrenceCount": len(candidate["occurrences"]),
    }
    if kind is not None:
        decision["kind"] = kind
    candidate["status"] = status
    candidate["updatedAt"] = timestamp
    candidate["decisionHistory"].append(decision)
    candidate["lastDecision"] = decision


def _last_rejection_occurrence_count(candidate: dict) -> int:
    for decision in reversed(candidate["decisionHistory"]):
        if decision["to"] == "rejected":
            return decision["occurrenceCount"]
    raise AdaptiveError("rejected candidate has no rejection decision")


def record_observation(
    project_root: Path, observation: Observation
) -> dict:
    if not isinstance(observation, Observation):
        raise AdaptiveError("observation must be an Observation")

    state = _load_candidates(project_root)
    fingerprint = candidate_fingerprint(observation)
    candidate = next(
        (
            item
            for item in state["candidates"]
            if item.get("fingerprint") == fingerprint
        ),
        None,
    )
    changed = False
    if candidate is None:
        identifier = _candidate_id(observation.action)
        existing_ids = {item.get("id") for item in state["candidates"]}
        if identifier in existing_ids:
            identifier = f"{identifier[:55].rstrip('-')}-{fingerprint[7:15]}"
        timestamp = _timestamp_for_date(observation.date)
        candidate = {
            "id": identifier,
            "fingerprint": fingerprint,
            "status": "observed",
            "summary": observation.summary,
            "category": observation.category,
            "occurrences": [],
            "createdAt": timestamp,
            "updatedAt": timestamp,
            "lastDecision": None,
            "decisionHistory": [],
        }
        state["candidates"].append(candidate)
        changed = True

    task_ids = {
        occurrence["task"] for occurrence in candidate["occurrences"]
    }
    if observation.task_id not in task_ids:
        candidate["occurrences"].append(
            {
                "date": observation.date,
                "task": observation.task_id,
                "signal": observation.summary,
                "evidence": list(observation.evidence),
            }
        )
        candidate["updatedAt"] = _timestamp_for_date(observation.date)
        changed = True

    eligible = (
        len(candidate["occurrences"]) >= 2 or observation.explicit_request
    )
    if candidate["status"] == "observed" and eligible:
        reason = (
            _EXPLICIT_REQUEST_REASON
            if observation.explicit_request
            else "Observed in two distinct tasks"
        )
        _record_transition(
            candidate,
            "eligible",
            reason,
            _timestamp_for_date(observation.date),
        )
        changed = True
    elif candidate["status"] == "rejected" and eligible:
        if (
            len(candidate["occurrences"])
            > _last_rejection_occurrence_count(candidate)
        ):
            _record_transition(
                candidate,
                "eligible",
                "New evidence after rejection",
                _timestamp_for_date(observation.date),
            )
            changed = True

    if changed:
        _write_project_json(
            project_root, _candidate_path(project_root), state
        )
    return candidate


def set_candidate_status(
    project_root: Path, candidate_id: str, status: str, reason: str
) -> dict:
    state, candidate = _prepare_candidate_status(
        project_root, candidate_id, status, reason
    )
    if status == "promoted":
        raise AdaptiveError(
            "promoted status requires a global or upstream promotion command"
        )
    _write_project_json(project_root, _candidate_path(project_root), state)
    return candidate


def _prepare_candidate_status(
    project_root: Path,
    candidate_id: str,
    status: str,
    reason: str,
    *,
    kind: str | None = None,
) -> tuple[dict, dict]:
    _validate_kebab(candidate_id, "candidate_id")
    _validate_text(reason, "reason")
    if status not in _CANDIDATE_STATUSES:
        raise AdaptiveError(f"unknown candidate status: {status}")

    state = _load_candidates(project_root)
    candidate = next(
        (
            item
            for item in state["candidates"]
            if item.get("id") == candidate_id
        ),
        None,
    )
    if candidate is None:
        raise AdaptiveError(f"unknown candidate: {candidate_id}")

    source = candidate["status"]
    if status not in _ALLOWED_TRANSITIONS.get(source, set()):
        raise AdaptiveError(
            f"invalid candidate transition: {source} -> {status}"
        )
    if (
        source == "observed"
        and status == "eligible"
        and len(candidate["occurrences"]) < 2
    ):
        raise AdaptiveError(
            "candidate eligibility requires two distinct tasks "
            "or an explicit request"
        )
    if (
        source == "rejected"
        and len(candidate["occurrences"])
        <= _last_rejection_occurrence_count(candidate)
    ):
        raise AdaptiveError(
            "rejected candidate requires new evidence before eligibility"
        )

    if kind is not None:
        _validate_kebab(kind, "candidate transition kind")
    _record_transition(
        candidate,
        status,
        reason,
        _current_timestamp(),
        kind=kind,
    )
    _validate_candidate(candidate)
    return state, candidate


def _reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AdaptiveError(f"duplicate key: {key}")
        result[key] = value
    return result


def _reject_non_finite(value):
    raise AdaptiveError(f"invalid JSON constant: {value}")


def _load_json_bytes(content: bytes, label: str):
    try:
        return json.loads(
            content,
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_non_finite,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise AdaptiveError(f"invalid JSON in {label}: {error}") from error


def load_json_strict(path: Path):
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_non_finite,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AdaptiveError(f"invalid JSON at {path}: {error}") from error


def write_json_atomic(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _restore_file_atomic(path: Path, content: bytes) -> None:
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.rollback.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _require_boolean_map(value, field: str) -> dict:
    if not isinstance(value, dict):
        raise AdaptiveError(f"{field} must be an object")
    for name, enabled in value.items():
        if not isinstance(name, str):
            raise AdaptiveError(f"{field} names must be strings")
        if type(enabled) is not bool:
            raise AdaptiveError(f"{field}.{name} must be boolean")
    return dict(value)


def normalize_config(config, registry_names, phase_of=None) -> dict:
    try:
        return config_contract.normalize_config(
            config, registry_names, phase_of
        )
    except config_contract.ConfigError as error:
        raise AdaptiveError(str(error)) from error


def load_project_config(
    project_root: Path, registry_names, phase_of=None
) -> dict:
    try:
        return config_contract.load_project_config(
            project_root, registry_names, phase_of
        )
    except config_contract.ConfigError as error:
        raise AdaptiveError(str(error)) from error


def confined_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise AdaptiveError(f"path escapes extension root: {relative}")
    return candidate


def _path_is_reparse_point(path: Path) -> bool:
    metadata = path.lstat()
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0)
        & _REPARSE_POINT_ATTRIBUTE
    )


def _require_project_state_path(
    project_root: Path,
    target: Path,
    label: str,
    *,
    leaf_kind: str,
    require_leaf: bool = False,
) -> bool:
    project_root = Path(project_root).absolute()
    target = Path(target).absolute()
    if leaf_kind not in {"file", "directory"}:
        raise AdaptiveError(f"invalid state path kind: {leaf_kind}")
    try:
        relative = target.relative_to(project_root)
    except ValueError:
        raise AdaptiveError(f"{label} escapes project root") from None
    if not relative.parts or relative.parts[0] != ".sdlc":
        raise AdaptiveError(f"{label} must be under project .sdlc")

    paths = [project_root]
    current = project_root
    for part in relative.parts:
        current = current / part
        paths.append(current)

    missing = False
    leaf_exists = False
    closest_existing = None
    for index, path in enumerate(paths):
        path_label = "project root" if index == 0 else (
            label if index == len(paths) - 1 else str(relative.parts[index - 1])
        )
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            if index == 0 or (
                require_leaf and index == len(paths) - 1
            ):
                raise AdaptiveError(f"{path_label} does not exist") from None
            missing = True
            continue
        except OSError as error:
            raise AdaptiveError(
                f"cannot inspect {path_label}: {error}"
            ) from error
        if missing:
            raise AdaptiveError(
                f"{path_label} exists beneath a missing state ancestor"
            )
        if _path_is_reparse_point(path):
            raise AdaptiveError(f"{path_label} must not be a reparse point")
        expected_kind = (
            leaf_kind if index == len(paths) - 1 else "directory"
        )
        actual_is_expected = (
            stat.S_ISREG(metadata.st_mode)
            if expected_kind == "file"
            else stat.S_ISDIR(metadata.st_mode)
        )
        if not actual_is_expected:
            raise AdaptiveError(
                f"{path_label} must be a {expected_kind}"
            )
        if index == len(paths) - 1:
            leaf_exists = True
        closest_existing = path

    try:
        resolved_root = project_root.resolve(strict=True)
        resolved_existing = closest_existing.resolve(strict=True)
    except OSError as error:
        raise AdaptiveError(f"cannot resolve {label}: {error}") from error
    if (
        resolved_existing != resolved_root
        and resolved_root not in resolved_existing.parents
    ):
        raise AdaptiveError(f"{label} escapes project root")
    return leaf_exists


def _write_project_json(project_root: Path, path: Path, value) -> None:
    _require_project_state_path(
        project_root, path, path.name, leaf_kind="file"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    _require_project_state_path(
        project_root, path.parent, str(path.parent.name),
        leaf_kind="directory", require_leaf=True
    )
    _require_project_state_path(
        project_root, path, path.name, leaf_kind="file"
    )
    write_json_atomic(path, value)


def _require_owned_extensions_path(
    project_root: Path,
    extension_dir: Path,
    *,
    require_extension: bool,
) -> bool:
    project_root = Path(project_root)
    extension_dir = Path(extension_dir)
    sdlc_root = project_root / ".sdlc"
    extensions_root = sdlc_root / "extensions"
    expected_extension = extensions_root / extension_dir.name
    if extension_dir != expected_extension:
        raise AdaptiveError("extension path escapes project extensions root")

    extension_exists = _require_project_state_path(
        project_root,
        extension_dir,
        "extension root",
        leaf_kind="directory",
        require_leaf=require_extension,
    )
    if not sdlc_root.exists():
        raise AdaptiveError(".sdlc root does not exist")
    if extension_exists:
        try:
            owned_root = (
                project_root.resolve(strict=True)
                / ".sdlc"
                / "extensions"
            )
            resolved_root = extensions_root.resolve(strict=True)
            resolved_extension = extension_dir.resolve(strict=True)
        except OSError as error:
            raise AdaptiveError(
                f"cannot resolve extension root: {error}"
            ) from error
        if (
            resolved_root != owned_root
            or resolved_extension.parent != resolved_root
        ):
            raise AdaptiveError(
                "extension path escapes project extensions root"
            )
    return extension_exists


_VERSION_COMPONENT = r"(?:0|[1-9][0-9]*)"
_VERSION_PATTERN = re.compile(
    rf"^{_VERSION_COMPONENT}\.{_VERSION_COMPONENT}\.{_VERSION_COMPONENT}$"
)
_COMPARISON_PATTERN = re.compile(
    rf"^(>=|>|<=|<|==)"
    rf"({_VERSION_COMPONENT}\.{_VERSION_COMPONENT}\.{_VERSION_COMPONENT})$"
)


def parse_version(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not _VERSION_PATTERN.fullmatch(value):
        raise AdaptiveError(f"invalid version: {value}")
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


def version_satisfies(version: str, constraint: str) -> bool:
    parsed_version = parse_version(version)
    if not isinstance(constraint, str) or not constraint.split():
        raise AdaptiveError(f"invalid version constraint: {constraint}")

    comparisons = {
        ">=": lambda left, right: left >= right,
        ">": lambda left, right: left > right,
        "<=": lambda left, right: left <= right,
        "<": lambda left, right: left < right,
        "==": lambda left, right: left == right,
    }
    parsed_comparisons = []
    for part in constraint.split():
        match = _COMPARISON_PATTERN.fullmatch(part)
        if match is None:
            raise AdaptiveError(f"invalid version constraint: {part}")
        operator, expected = match.groups()
        parsed_comparisons.append((operator, parse_version(expected)))

    return all(
        comparisons[operator](parsed_version, expected)
        for operator, expected in parsed_comparisons
    )


def _core_module_names(core_registry) -> set[str]:
    if not isinstance(core_registry, dict):
        raise AdaptiveError("core registry must be an object")
    modules = core_registry.get("modules")
    if not isinstance(modules, list):
        raise AdaptiveError("core registry modules must be an array")
    names = set()
    for module in modules:
        if not isinstance(module, dict):
            raise AdaptiveError("invalid core registry module")
        name = module.get("name")
        _validate_kebab(name, "core module name")
        if name in names:
            raise AdaptiveError(f"duplicate core module: {name}")
        names.add(name)
    return names


def _phase_index(core_registry):
    """Module name to delivery phase, or None when the registry lacks it."""
    try:
        return config_contract.phase_index(core_registry)
    except config_contract.ConfigError:
        return None


def _unsafe_extension_matches(value: str):
    for label, pattern in _UNSAFE_EXTENSION_PATTERNS:
        for match in pattern.finditer(value):
            yield label, match.start()

    write_match = _WRITE_VERB_PATTERN.search(value)
    if write_match is None:
        return
    if _INSTALLED_SKILL_PATH_PATTERN.search(value):
        yield "core", write_match.start()
    if _contains_absolute_reference(value):
        yield "system", write_match.start()


def _actionable_clauses(value: str):
    return (
        clause
        for clause in _ACTIONABLE_CLAUSE_BOUNDARY_PATTERN.split(value)
        if clause.strip()
    )


def _is_negated_action(value: str, start: int) -> bool:
    return _NEGATED_ACTION_PATTERN.search(value[:start]) is not None


def _validate_extension_content(value, field: str) -> None:
    """Apply defense-in-depth checks; model safety review remains required."""
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise AdaptiveError(f"{field} keys must be strings")
            if key.casefold().startswith("raw"):
                raise AdaptiveError(f"{field} contains raw content")
            _validate_extension_content(child, f"{field}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _validate_extension_content(child, f"{field}[{index}]")
        return
    if not isinstance(value, str):
        return
    if _SENSITIVE_PATTERN.search(value) or _HOME_PATH_PATTERN.search(value):
        raise AdaptiveError(f"{field} contains sensitive data")
    for clause in _actionable_clauses(value):
        if _DOCUMENTATION_CLAUSE_PATTERN.match(clause):
            continue
        for label, start in _unsafe_extension_matches(clause):
            if not _is_negated_action(clause, start):
                raise AdaptiveError(
                    f"{field} requests prohibited {label} behavior"
                )


def _validate_evaluations_data(evaluations) -> None:
    if not isinstance(evaluations, dict):
        raise AdaptiveError("evals.json must contain an object")
    _validate_extension_content(evaluations, "evals.json")
    if set(evaluations) != {"schemaVersion", "cases"}:
        raise AdaptiveError("invalid evals.json fields")
    if type(evaluations.get("schemaVersion")) is not int or (
        evaluations["schemaVersion"] != 1
    ):
        raise AdaptiveError("evals.json must use schema version 1")
    cases = evaluations.get("cases")
    if not isinstance(cases, list) or not cases:
        raise AdaptiveError("evals.json cases must be a non-empty array")
    kinds = set()
    identifiers = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise AdaptiveError(f"evaluation case {index} must be an object")
        allowed_fields = {"id", "type", "kind", "prompt", "expected"}
        for required_field in ("id", "prompt", "expected"):
            if required_field not in case:
                raise AdaptiveError(
                    f"evaluation case {index} requires {required_field}"
                )
        if (
            not set(case) <= allowed_fields
            or not ({"type", "kind"} & set(case))
        ):
            raise AdaptiveError(f"invalid evaluation case fields at {index}")
        identifier = case.get("id")
        _validate_kebab(identifier, f"evaluation case {index} id")
        if identifier in identifiers:
            raise AdaptiveError(f"duplicate evaluation id: {identifier}")
        identifiers.add(identifier)
        if (
            "type" in case
            and "kind" in case
            and case["type"] != case["kind"]
        ):
            raise AdaptiveError(
                f"evaluation case {identifier} type and kind disagree"
            )
        kind = case.get("type", case.get("kind"))
        if not isinstance(kind, str) or kind not in {"positive", "negative"}:
            raise AdaptiveError(
                f"evaluation case {identifier} must be positive or negative"
            )
        kinds.add(kind)
        _validate_text(case["prompt"], f"evaluation case {identifier} prompt", 1000)
        _validate_text(
            case["expected"],
            f"evaluation case {identifier} expected",
            1000,
        )
        _validate_extension_content(case, f"evaluation case {identifier}")
    if kinds != {"positive", "negative"}:
        raise AdaptiveError(
            "evals.json requires at least one positive and negative case"
        )


@dataclass(frozen=True)
class _ExtensionSnapshot:
    files: tuple[tuple[str, bytes], ...]
    digest: str

    def read(self, name: str) -> bytes:
        for filename, content in self.files:
            if filename == name:
                return content
        raise AdaptiveError(f"extension snapshot is missing {name}")

    def contents(self) -> dict[str, bytes]:
        return dict(self.files)


def _content_digest(contents) -> str:
    digest = hashlib.sha256()
    for name, content in sorted(contents):
        encoded_name = name.encode("utf-8")
        digest.update(len(encoded_name).to_bytes(8, "big"))
        digest.update(encoded_name)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"


def _read_extension_snapshot(extension_dir: Path) -> _ExtensionSnapshot:
    extension_dir = Path(extension_dir)
    if (
        extension_dir.parent.name != "extensions"
        or extension_dir.parent.parent.name != ".sdlc"
    ):
        raise AdaptiveError("extension path must be under .sdlc/extensions")
    project_root = extension_dir.parent.parent.parent
    _require_owned_extensions_path(
        project_root, extension_dir, require_extension=True
    )
    entries = {entry.name for entry in extension_dir.iterdir()}
    if entries != _EXTENSION_FILES:
        raise AdaptiveError(
            "extension directory must contain exactly "
            "extension.json, MODULE.md, and evals.json"
        )
    try:
        files = []
        for name in sorted(_EXTENSION_FILES):
            path = extension_dir / name
            metadata = path.lstat()
            if (
                _path_is_reparse_point(path)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_mode
                & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            ):
                raise AdaptiveError(
                    "extension files must be regular, non-executable files "
                    "and not reparse points"
                )
            files.append((name, path.read_bytes()))
    except OSError as error:
        raise AdaptiveError(
            f"cannot read extension snapshot: {error}"
        ) from error
    immutable_files = tuple(files)
    return _ExtensionSnapshot(
        files=immutable_files, digest=_content_digest(immutable_files)
    )


def _validate_extension_snapshot(
    extension_dir: Path,
    snapshot: _ExtensionSnapshot,
    sdlc_version: str,
    core_registry,
) -> tuple[dict, dict]:
    metadata = _load_json_bytes(
        snapshot.read("extension.json"), "extension.json"
    )
    expected_fields = {
        "schemaVersion",
        "id",
        "version",
        "status",
        "category",
        "mode",
        "path",
        "trigger",
        "exitSignal",
        "evidence",
        "compatibleSdlc",
    }
    if not isinstance(metadata, dict) or set(metadata) != expected_fields:
        raise AdaptiveError("invalid extension metadata fields")
    if type(metadata["schemaVersion"]) is not int or (
        metadata["schemaVersion"] != 1
    ):
        raise AdaptiveError("extension metadata must use schema version 1")
    identifier = _validate_kebab(metadata["id"], "extension id")
    if identifier != extension_dir.name:
        raise AdaptiveError("extension id must match its directory name")
    if identifier in _core_module_names(core_registry):
        raise AdaptiveError(f"extension conflicts with core module: {identifier}")
    parse_version(metadata["version"])
    if (
        not isinstance(metadata["status"], str)
        or metadata["status"] not in _EXTENSION_STATUSES
    ):
        raise AdaptiveError("invalid extension status")
    if not isinstance(metadata["mode"], str) or metadata["mode"] != "augment":
        raise AdaptiveError("extension mode must be augment")
    _validate_kebab(metadata["category"], "category")
    _validate_text(metadata["trigger"], "trigger")
    _validate_text(metadata["exitSignal"], "exitSignal")
    _validate_evidence(metadata["evidence"], "evidence")

    _validate_text(metadata["path"], "path")
    module_path = confined_path(extension_dir, metadata["path"])
    if module_path != (extension_dir / "MODULE.md").resolve():
        raise AdaptiveError("extension path must identify MODULE.md")
    if not version_satisfies(sdlc_version, metadata["compatibleSdlc"]):
        raise AdaptiveError(
            f"extension is not compatible with SDLC {sdlc_version}"
        )

    _validate_extension_content(metadata, "extension metadata")
    try:
        module_content = snapshot.read("MODULE.md").decode("utf-8")
    except UnicodeError as error:
        raise AdaptiveError(f"invalid MODULE.md: {error}") from error
    if not module_content.strip():
        raise AdaptiveError("MODULE.md must not be empty")
    _validate_extension_content(module_content, "MODULE.md")
    evaluations = _load_json_bytes(snapshot.read("evals.json"), "evals.json")
    _validate_evaluations_data(evaluations)
    return metadata, evaluations


def validate_extension(
    extension_dir: Path, sdlc_version: str, core_registry
) -> dict:
    extension_dir = Path(extension_dir)
    snapshot = _read_extension_snapshot(extension_dir)
    metadata, _ = _validate_extension_snapshot(
        extension_dir, snapshot, sdlc_version, core_registry
    )
    return metadata


def load_resolved_module(
    extension_dir: Path,
    expected_digest: str,
    sdlc_version: str,
    core_registry,
) -> str:
    if not isinstance(expected_digest, str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", expected_digest
    ):
        raise AdaptiveError("expected extension digest is invalid")
    snapshot = _read_extension_snapshot(extension_dir)
    if snapshot.digest != expected_digest:
        raise AdaptiveError("validated extension snapshot changed before loading")
    _validate_extension_snapshot(
        Path(extension_dir), snapshot, sdlc_version, core_registry
    )
    try:
        return snapshot.read("MODULE.md").decode("utf-8")
    except UnicodeError as error:
        raise AdaptiveError(f"invalid MODULE.md: {error}") from error


def _normalized_trigger(value: str) -> str:
    return " ".join(value.casefold().split())


def _core_triggers(core_registry) -> dict:
    triggers = {}
    for module in core_registry["modules"]:
        category = module.get("category")
        trigger = module.get("trigger")
        if category is None or trigger is None:
            continue
        _validate_kebab(category, "core module category")
        _validate_text(trigger, "core module trigger", 512)
        normalized = _normalized_trigger(trigger)
        previous = triggers.get(normalized)
        if previous is not None and previous["category"] != category:
            raise AdaptiveError(
                "core trigger conflict between "
                f"{previous['id']} and {module['name']}: "
                "categories differ"
            )
        if previous is not None:
            continue
        triggers[normalized] = {
            "id": module["name"],
            "category": category,
        }
    return triggers


def resolve_extensions(
    project_root: Path,
    global_root: Path | None,
    config,
    sdlc_version: str,
    core_registry,
) -> list[dict]:
    registry_names = _core_module_names(core_registry)
    triggers = _core_triggers(core_registry)
    normalized = normalize_config(
        config, registry_names, _phase_index(core_registry)
    )
    configured = []
    for source in ("project", "global"):
        for identifier, enabled in normalized["extensions"][source].items():
            _validate_kebab(identifier, f"extensions.{source} id")
            configured.append((source, identifier, enabled))

    resolved = []
    enabled_by_id = {}
    enabled_metadata = []
    for source, identifier, enabled in configured:
        if not enabled:
            resolved.append(
                {
                    "id": identifier,
                    "source": source,
                    "coverageStatus": "configured-disabled",
                }
            )
            continue
        if source == "global" and global_root is None:
            raise AdaptiveError(
                f"global extension root is required for {identifier}"
            )
        source_root = (
            Path(project_root) if source == "project" else Path(global_root)
        )
        extension_dir = (
            source_root / ".sdlc" / "extensions" / identifier
        )
        snapshot = _read_extension_snapshot(extension_dir)
        metadata, _ = _validate_extension_snapshot(
            extension_dir, snapshot, sdlc_version, core_registry
        )
        if metadata["status"] != "accepted":
            raise AdaptiveError(
                f"extension is not accepted: {identifier}"
            )
        digest = snapshot.digest

        existing = enabled_by_id.get(identifier)
        if existing is not None:
            if existing["contentDigest"] != digest:
                raise AdaptiveError(
                    f"conflicting extension content for duplicate id: "
                    f"{identifier}"
                )
            existing["sources"].append(source)
            continue

        item = dict(metadata)
        item.update(
            {
                "source": source,
                "sources": [source],
                "contentDigest": digest,
            }
        )
        enabled_by_id[identifier] = item
        enabled_metadata.append(item)
        resolved.append(item)

    for item in enabled_metadata:
        trigger = _normalized_trigger(item["trigger"])
        previous = triggers.get(trigger)
        if previous is not None and previous["category"] != item["category"]:
            raise AdaptiveError(
                "extension trigger conflict between "
                f"{previous['id']} and {item['id']}: categories differ"
            )
        triggers[trigger] = item
    return resolved


def load_candidates(project_root: Path) -> dict:
    return _load_candidates(project_root)


def _installed_registry() -> dict:
    return load_json_strict(
        Path(__file__).resolve().parents[1] / "modules" / "registry.json"
    )


def _installed_sdlc_version() -> str:
    skill_path = Path(__file__).resolve().parents[1] / "SKILL.md"
    try:
        text = skill_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise AdaptiveError(f"cannot read SDLC version: {error}") from error
    match = re.search(r'^\s*version:\s*["\']([^"\']+)["\']\s*$', text, re.MULTILINE)
    if match is None:
        raise AdaptiveError("cannot determine SDLC version")
    parse_version(match.group(1))
    return match.group(1)


def activate_extension(project_root: Path, extension_id: str) -> dict:
    project_root = Path(project_root)
    _validate_kebab(extension_id, "extension_id")
    registry = _installed_registry()
    extension_dir = (
        project_root / ".sdlc" / "extensions" / extension_id
    )
    metadata = validate_extension(
        extension_dir, _installed_sdlc_version(), registry
    )
    if metadata["status"] != "accepted":
        raise AdaptiveError(
            "extension activation requires explicit approval "
            "and accepted status"
        )

    registry_names = _core_module_names(registry)
    phase_of = _phase_index(registry)
    config = load_project_config(project_root, registry_names, phase_of)
    config["extensions"]["project"][extension_id] = True
    config_path = project_root / ".sdlc" / "config.json"
    _write_project_json(
        project_root,
        config_path,
        config_contract.config_to_document(config, phase_of),
    )
    return {
        "changedPaths": [".sdlc/config.json"],
        "rollback": (
            f"Set extensions.project.{extension_id} to false "
            "or remove that entry."
        ),
    }


def _accepted_extension(
    project_root: Path, extension_id: str
) -> tuple[Path, _ExtensionSnapshot, dict, dict]:
    project_root = Path(project_root)
    _validate_kebab(extension_id, "extension_id")
    extension_dir = (
        project_root / ".sdlc" / "extensions" / extension_id
    )
    snapshot = _read_extension_snapshot(extension_dir)
    metadata, evaluations = _validate_extension_snapshot(
        extension_dir,
        snapshot,
        _installed_sdlc_version(),
        _installed_registry(),
    )
    if metadata["status"] != "accepted":
        raise AdaptiveError("promotion requires an accepted extension")
    return extension_dir, snapshot, metadata, evaluations


def _directory_has_content(path: Path, contents: dict[str, bytes]) -> bool:
    try:
        if _path_is_reparse_point(path) or not stat.S_ISDIR(
            path.lstat().st_mode
        ):
            return False
        entries = {entry.name: entry for entry in path.iterdir()}
        if set(entries) != set(contents):
            return False
        for name, expected in contents.items():
            entry = entries[name]
            metadata = entry.lstat()
            if (
                _path_is_reparse_point(entry)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_mode
                & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                or entry.read_bytes() != expected
            ):
                return False
    except OSError:
        return False
    return True


def _write_directory_atomically(
    target: Path,
    contents: dict[str, bytes],
    differing_message: str,
    validate_target=None,
) -> tuple[Path, bool]:
    if validate_target is not None:
        validate_target()
    if target.exists() or target.is_symlink():
        if _directory_has_content(target, contents):
            return target, False
        raise AdaptiveError(differing_message)

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent)
    )
    staging = temporary_root / target.name
    try:
        staging.mkdir()
        for name, content in contents.items():
            (staging / name).write_bytes(content)
        if validate_target is not None:
            validate_target()
        staging.replace(target)
    except FileExistsError:
        if _directory_has_content(target, contents):
            return target, False
        raise AdaptiveError(differing_message) from None
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)
    return target, True


def _prepare_promotion_state(
    project_root: Path,
    extension_id: str,
    kind: str,
    reason: str,
) -> tuple[dict, bool]:
    state = _load_candidates(project_root)
    candidate = next(
        (
            item
            for item in state["candidates"]
            if item["id"] == extension_id
        ),
        None,
    )
    if candidate is None:
        raise AdaptiveError(
            f"promotion requires a candidate record: {extension_id}"
        )
    if candidate["status"] == "promoted":
        if any(
            decision.get("kind") == kind
            for decision in candidate["decisionHistory"]
        ):
            return state, False
    elif candidate["status"] != "accepted":
        raise AdaptiveError(
            f"promotion requires accepted candidate state: {extension_id}"
        )

    _record_transition(
        candidate,
        "promoted",
        reason,
        _current_timestamp(),
        kind=kind,
    )
    _validate_candidate(candidate)
    return state, True


def _persist_promotion_state(
    project_root: Path,
    state: dict,
    target: Path,
    contents: dict[str, bytes],
    created: bool,
) -> Path:
    try:
        _write_project_json(
            project_root, _candidate_path(project_root), state
        )
    except (OSError, AdaptiveError) as write_error:
        if created:
            if not _directory_has_content(target, contents):
                raise OSError(
                    "promotion state write failed and destination rollback "
                    "could not verify created content"
                ) from write_error
            try:
                shutil.rmtree(target)
            except OSError as rollback_error:
                raise OSError(
                    "promotion state write failed and destination rollback "
                    f"failed: {rollback_error}"
                ) from write_error
        raise
    return target


def _require_global_catalog(global_root: Path) -> Path:
    global_root = Path(global_root)
    if (
        global_root.name != "extensions"
        or global_root.parent.name != ".sdlc"
    ):
        raise AdaptiveError(
            "global_root must identify a global extension catalog"
        )
    installed_core = Path(__file__).resolve().parents[1]
    resolved_catalog = global_root.resolve()
    if (
        resolved_catalog == installed_core
        or installed_core in resolved_catalog.parents
    ):
        raise AdaptiveError(
            "global extension catalog must not modify installed SDLC core"
        )
    catalog_owner = global_root.parent.parent
    for label, path in (
        ("global root", catalog_owner),
        (".sdlc root", global_root.parent),
        ("global extension catalog", global_root),
    ):
        if not path.exists():
            continue
        try:
            if _path_is_reparse_point(path):
                raise AdaptiveError(f"{label} must not be a reparse point")
            if not stat.S_ISDIR(path.lstat().st_mode):
                raise AdaptiveError(f"{label} must be a directory")
        except OSError as error:
            raise AdaptiveError(f"cannot inspect {label}: {error}") from error
    global_root.mkdir(parents=True, exist_ok=True)
    for label, path in (
        ("global root", catalog_owner),
        (".sdlc root", global_root.parent),
        ("global extension catalog", global_root),
    ):
        try:
            if _path_is_reparse_point(path):
                raise AdaptiveError(f"{label} must not be a reparse point")
            if not stat.S_ISDIR(path.lstat().st_mode):
                raise AdaptiveError(f"{label} must be a directory")
        except OSError as error:
            raise AdaptiveError(f"cannot inspect {label}: {error}") from error
    return global_root


def promote_global(
    project_root: Path, extension_id: str, global_root: Path
) -> Path:
    project_root = Path(project_root)
    _, snapshot, metadata, evaluations = _accepted_extension(
        project_root, extension_id
    )
    _, context = _candidate_context(project_root, extension_id)
    _validate_promotion_sanitization(
        snapshot, metadata, evaluations, context, "promotion"
    )
    contents = snapshot.contents()
    if _content_digest(contents.items()) != snapshot.digest:
        raise AdaptiveError("extension snapshot digest changed")
    state, state_changed = _prepare_promotion_state(
        project_root,
        extension_id,
        "global",
        "Promoted to the user-global extension catalog",
    )
    catalog = _require_global_catalog(global_root)
    target, created = _write_directory_atomically(
        catalog / extension_id,
        contents,
        f"global extension already exists with different content: "
        f"{extension_id}",
        validate_target=lambda: _require_global_catalog(global_root),
    )
    if not state_changed:
        return target
    return _persist_promotion_state(
        project_root, state, target, contents, created
    )


def _candidate_context(project_root: Path, extension_id: str) -> tuple[int, dict]:
    project_identifier = Path(project_root).absolute().name.casefold()
    candidates = _load_candidates(project_root)["candidates"]
    candidate = next(
        (item for item in candidates if item["id"] == extension_id), None
    )
    if candidate is None:
        return 0, {
            "task_ids": (),
            "evidence": (),
            "identifiers": (project_identifier,),
        }

    task_ids = []
    evidence = []
    identifiers = set()
    for occurrence in candidate["occurrences"]:
        task_ids.append(occurrence["task"])
        evidence.extend(occurrence["evidence"])
        sources = [
            occurrence["task"],
            occurrence["signal"],
            *occurrence["evidence"],
        ]
        for source in sources:
            for match in _IDENTIFIER_PATTERN.findall(source):
                parts = re.split(r"[-_]", match)
                for size in range(2, len(parts) + 1):
                    for start in range(len(parts) - size + 1):
                        identifier = "-".join(parts[start : start + size])
                        if identifier != extension_id:
                            identifiers.add(identifier.casefold())
            for part in re.split(r"[\\/]", source):
                normalized = part.casefold().strip(" ._-")
                if (
                    len(normalized) >= 4
                    and "." not in normalized
                    and normalized not in _GENERIC_PATH_PARTS
                ):
                    identifiers.add(normalized)
    identifiers.add(project_identifier)
    return len(candidate["occurrences"]), {
        "task_ids": tuple(task_ids),
        "evidence": tuple(evidence),
        "identifiers": tuple(sorted(identifiers, key=len, reverse=True)),
    }


def _iter_snapshot_text(
    snapshot: _ExtensionSnapshot, metadata: dict, evaluations: dict
):
    yield "extension.json", metadata
    try:
        module = snapshot.read("MODULE.md").decode("utf-8")
    except UnicodeError as error:
        raise AdaptiveError(f"invalid MODULE.md: {error}") from error
    yield "MODULE.md", module
    yield "evals.json", evaluations


def _iter_text_values(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from _iter_text_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_text_values(child)
    elif isinstance(value, str):
        yield value


def _sanitization_error(
    filename: str, reason: str, operation: str
) -> None:
    raise AdaptiveError(
        f"{operation} sanitization required: "
        f"{filename} contains {reason}; developer revision is required "
        "before promotion"
    )


def _contains_normalized_identifier(value: str, identifier: str) -> bool:
    normalized_value = value.casefold().replace("_", "-")
    normalized_identifier = identifier.casefold().replace("_", "-")
    pattern = re.compile(
        rf"(?<!\w){re.escape(normalized_identifier)}(?!\w)"
    )
    return pattern.search(normalized_value) is not None


def _contains_project_relative_path(value: str) -> bool:
    for match in _PROJECT_REFERENCE_CANDIDATE_PATTERN.finditer(value):
        reference = match.group(0).rstrip(".,;:!?)]}'\"")
        parts = re.split(r"[\\/]", reference)
        if parts and parts[0] == ".":
            parts = parts[1:]
        if len(parts) >= 3:
            return True
        if (
            len(parts) == 2
            and parts[0].casefold() in _GENERIC_PATH_PARTS
        ):
            return True
        if re.search(r"\.[A-Za-z0-9]{1,10}$", parts[-1]):
            return True
    return False


def _validate_promotion_sanitization(
    snapshot: _ExtensionSnapshot,
    metadata: dict,
    evaluations: dict,
    context: dict,
    operation: str,
) -> None:
    task_ids = tuple(value.casefold() for value in context["task_ids"])
    evidence = tuple(value.casefold() for value in context["evidence"])
    identifiers = context["identifiers"]
    for filename, value in _iter_snapshot_text(
        snapshot, metadata, evaluations
    ):
        for text in _iter_text_values(value):
            if any(
                _contains_normalized_identifier(text, token)
                for token in task_ids
            ):
                _sanitization_error(
                    filename, "candidate task identifier", operation
                )
            if any(
                _contains_normalized_identifier(text, reference)
                for reference in evidence
            ):
                _sanitization_error(
                    filename, "candidate evidence reference", operation
                )
            if any(
                _contains_normalized_identifier(text, identifier)
                for identifier in identifiers
            ):
                _sanitization_error(
                    filename, "known project identifier", operation
                )
            if _contains_absolute_reference(text):
                _sanitization_error(filename, "absolute path", operation)
            if _contains_project_relative_path(text):
                _sanitization_error(
                    filename, "project-specific relative path", operation
                )


def _upstream_proposal(
    metadata: dict, occurrence_count: int, evaluations: dict
) -> bytes:
    noun = "occurrence" if occurrence_count == 1 else "occurrences"
    category = metadata["category"]
    trigger = metadata["trigger"]
    trigger_clause = trigger.rstrip(".!?")
    exit_signal = metadata["exitSignal"]
    evidence = "\n".join(
        f"- {reference}" for reference in metadata["evidence"]
    )
    positive_count = sum(
        case.get("type", case.get("kind")) == "positive"
        for case in evaluations["cases"]
    )
    negative_count = sum(
        case.get("type", case.get("kind")) == "negative"
        for case in evaluations["cases"]
    )
    proposal = f"""# Upstream Extension Proposal

## Generalized problem

When {trigger_clause[:1].casefold() + trigger_clause[1:]}, teams need a reusable,
opt-in {category} check with a measurable completion signal.

## Why core behavior does not already cover it

Core modules do not define this bounded trigger and exit contract together.
The proposal augments the existing lifecycle instead of changing core
behavior.

## Anonymized occurrence summary

{occurrence_count} qualifying {noun} indicated this generalized signal:
{trigger}

## Proposed category and trigger

Category: `{category}`.

Trigger: {trigger}

## Evidence and exit contract

Exit signal: {exit_signal}

Evidence:
{evidence}

## Safety review

The package passed checks for sensitive content, project identifiers,
candidate task and evidence references, absolute and project-specific paths,
extension scripts, core mutation, network access, and publishing behavior.
Model safety review remains required.

## Behavior evaluation results

Validated behavior coverage includes {positive_count} positive and {negative_count} negative cases.

## Compatibility and migration notes

Compatibility range: `{metadata["compatibleSdlc"]}`.

Migration is additive: review and install the extension separately, then opt
in explicitly. This preparation does not edit project configuration or core
modules.

## Recommended disposition

This should remain an extension example that augments the `{category}`
lifecycle.
Reconsider core inclusion only after broader, project-independent evidence.
"""
    return proposal.encode("utf-8")


def _require_contributions_root(project_root: Path) -> Path:
    project_root = Path(project_root)
    contributions = project_root / ".sdlc" / "contributions"
    _require_project_state_path(
        project_root,
        contributions,
        "contributions root",
        leaf_kind="directory",
    )
    contributions.mkdir(parents=True, exist_ok=True)
    _require_project_state_path(
        project_root,
        contributions,
        "contributions root",
        leaf_kind="directory",
        require_leaf=True,
    )
    return contributions


def prepare_upstream(project_root: Path, extension_id: str) -> Path:
    project_root = Path(project_root)
    _, snapshot, metadata, evaluations = _accepted_extension(
        project_root, extension_id
    )
    occurrence_count, context = _candidate_context(
        project_root, extension_id
    )
    _validate_promotion_sanitization(
        snapshot, metadata, evaluations, context, "upstream"
    )
    contents = snapshot.contents()
    contents["proposal.md"] = _upstream_proposal(
        metadata, occurrence_count, evaluations
    )
    state, state_changed = _prepare_promotion_state(
        project_root,
        extension_id,
        "upstream",
        "Prepared for upstream contribution review",
    )
    target = _require_contributions_root(project_root) / extension_id
    target, created = _write_directory_atomically(
        target,
        contents,
        f"upstream package already exists with different content: "
        f"{extension_id}",
        validate_target=lambda: _require_project_state_path(
            project_root,
            target,
            "contribution package",
            leaf_kind="directory",
        ),
    )
    if not state_changed:
        return target
    return _persist_promotion_state(
        project_root, state, target, contents, created
    )


def reject_extension(
    project_root: Path, candidate_id: str, reason: str
) -> dict:
    project_root = Path(project_root)
    _validate_kebab(candidate_id, "candidate_id")
    _validate_text(reason, "reason")
    extension_dir = (
        project_root / ".sdlc" / "extensions" / candidate_id
    )
    has_draft = _require_owned_extensions_path(
        project_root, extension_dir, require_extension=False
    )
    state, candidate = _prepare_candidate_status(
        project_root, candidate_id, "rejected", reason
    )
    updated_metadata = None
    metadata_path = extension_dir / "extension.json"
    if has_draft:
        metadata = validate_extension(
            extension_dir, _installed_sdlc_version(), _installed_registry()
        )
        if metadata.get("status") == "drafted":
            updated_metadata = dict(metadata)
            updated_metadata["status"] = "rejected"

    candidate_path = _candidate_path(project_root)
    _require_project_state_path(
        project_root,
        candidate_path,
        "candidate state",
        leaf_kind="file",
        require_leaf=True,
    )
    original_candidate_content = candidate_path.read_bytes()
    _write_project_json(project_root, candidate_path, state)
    if updated_metadata is not None:
        try:
            _write_project_json(project_root, metadata_path, updated_metadata)
        except OSError as write_error:
            try:
                _require_project_state_path(
                    project_root,
                    candidate_path,
                    "candidate state",
                    leaf_kind="file",
                    require_leaf=True,
                )
                _restore_file_atomic(
                    candidate_path, original_candidate_content
                )
            except OSError as rollback_error:
                raise OSError(
                    "draft update failed and candidate rollback failed: "
                    f"{rollback_error}"
                ) from write_error
            raise
    return candidate
