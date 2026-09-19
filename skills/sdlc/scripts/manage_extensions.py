import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adaptive_extensions import (
    AdaptiveError,
    Observation,
    _core_module_names,
    _phase_index,
    _load_candidates,
    _validate_kebab,
    activate_extension,
    load_resolved_module,
    load_json_strict,
    load_project_config,
    prepare_upstream,
    promote_global,
    record_observation,
    reject_extension,
    resolve_extensions,
    set_candidate_status,
    validate_extension,
)


def _public_candidate(candidate: dict) -> dict:
    return {
        "id": candidate["id"],
        "fingerprint": candidate["fingerprint"],
        "status": candidate["status"],
        "summary": candidate["summary"],
        "category": candidate["category"],
        "occurrenceCount": len(candidate["occurrences"]),
        "createdAt": candidate["createdAt"],
        "updatedAt": candidate["updatedAt"],
        "lastDecision": candidate["lastDecision"],
    }


def _public_extension(extension: dict) -> dict:
    return {
        "id": extension["id"],
        "version": extension["version"],
        "status": extension["status"],
        "category": extension["category"],
        "mode": extension["mode"],
        "compatibleSdlc": extension["compatibleSdlc"],
    }


def _observation_from_file(path: Path) -> Observation:
    value = load_json_strict(path)
    if not isinstance(value, dict):
        raise AdaptiveError("observation input must be an object")
    required = {
        "task_id",
        "date",
        "summary",
        "category",
        "action",
        "trigger",
        "exit_signal",
        "evidence",
    }
    unknown = set(value) - required - {"explicit_request"}
    missing = required - set(value)
    if unknown:
        raise AdaptiveError(f"unknown observation field: {sorted(unknown)[0]}")
    if missing:
        raise AdaptiveError(f"missing observation field: {sorted(missing)[0]}")
    if not isinstance(value["evidence"], list):
        raise AdaptiveError("evidence must be an array")
    value["evidence"] = tuple(value["evidence"])
    try:
        return Observation(**value)
    except TypeError as error:
        raise AdaptiveError(f"invalid observation: {error}") from error


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Static extension validation is defense in depth, not an "
            "exhaustive safety check; mandatory model safety review remains "
            "required."
        )
    )
    subparsers = parser.add_subparsers(dest="command")

    record = subparsers.add_parser("record")
    record.add_argument("--project-root", required=True, type=Path)
    record.add_argument("--input", required=True, type=Path)

    status = subparsers.add_parser("status")
    status.add_argument("--project-root", required=True, type=Path)
    status.add_argument("--candidate", required=True)
    status.add_argument("--status", required=True)
    status.add_argument("--reason", required=True)

    list_candidates = subparsers.add_parser("list-candidates")
    list_candidates.add_argument("--project-root", required=True, type=Path)

    validate = subparsers.add_parser("validate-extension")
    validate.add_argument("--project-root", required=True, type=Path)
    validate.add_argument("--extension", required=True)

    activate = subparsers.add_parser("activate")
    activate.add_argument("--project-root", required=True, type=Path)
    activate.add_argument("--extension", required=True)
    activate.add_argument("--scope", choices=("project",), default="project")

    reject = subparsers.add_parser("reject")
    reject.add_argument("--project-root", required=True, type=Path)
    reject.add_argument("--candidate", required=True)
    reject.add_argument("--reason", required=True)

    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("--project-root", required=True, type=Path)
    resolve.add_argument("--global-root", type=Path)

    load_module = subparsers.add_parser("load-module")
    load_module.add_argument("--project-root", required=True, type=Path)
    load_module.add_argument("--extension", required=True)
    load_module.add_argument(
        "--source", required=True, choices=("project", "global")
    )
    load_module.add_argument("--expected-digest", required=True)
    load_module.add_argument("--global-root", type=Path)

    promote = subparsers.add_parser("promote-global")
    promote.add_argument("--project-root", required=True, type=Path)
    promote.add_argument("--extension", required=True)
    promote.add_argument("--global-root", required=True, type=Path)

    upstream = subparsers.add_parser("prepare-upstream")
    upstream.add_argument("--project-root", required=True, type=Path)
    upstream.add_argument("--extension", required=True)
    return parser


def _installed_context():
    skill_root = SCRIPT_DIR.parent
    registry = load_json_strict(skill_root / "modules" / "registry.json")
    skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    for line in skill_text.splitlines():
        if line.strip().startswith("version:"):
            version = line.split(":", 1)[1].strip().strip("\"'")
            return version, registry
    raise AdaptiveError("cannot determine SDLC version")


def main(argv=None) -> int:
    try:
        arguments = _build_parser().parse_args(argv)
        if arguments.command is None:
            raise AdaptiveError("a subcommand is required")
        if arguments.command == "record":
            candidate = record_observation(
                arguments.project_root,
                _observation_from_file(arguments.input),
            )
            result = _public_candidate(candidate)
        elif arguments.command == "status":
            candidate = set_candidate_status(
                arguments.project_root,
                arguments.candidate,
                arguments.status,
                arguments.reason,
            )
            result = _public_candidate(candidate)
        elif arguments.command == "list-candidates":
            state = _load_candidates(arguments.project_root)
            result = {
                "schemaVersion": state["schemaVersion"],
                "candidates": [
                    _public_candidate(candidate)
                    for candidate in state["candidates"]
                ],
            }
        elif arguments.command == "validate-extension":
            _validate_kebab(arguments.extension, "extension")
            version, registry = _installed_context()
            result = _public_extension(
                validate_extension(
                    arguments.project_root
                    / ".sdlc"
                    / "extensions"
                    / arguments.extension,
                    version,
                    registry,
                )
            )
        elif arguments.command == "activate":
            result = activate_extension(
                arguments.project_root, arguments.extension
            )
        elif arguments.command == "reject":
            candidate = reject_extension(
                arguments.project_root,
                arguments.candidate,
                arguments.reason,
            )
            result = _public_candidate(candidate)
        elif arguments.command == "promote-global":
            result = {
                "path": str(
                    promote_global(
                        arguments.project_root,
                        arguments.extension,
                        arguments.global_root,
                    )
                )
            }
        elif arguments.command == "prepare-upstream":
            result = {
                "path": str(
                    prepare_upstream(
                        arguments.project_root, arguments.extension
                    )
                )
            }
        elif arguments.command == "load-module":
            _validate_kebab(arguments.extension, "extension")
            if arguments.source == "global" and arguments.global_root is None:
                raise AdaptiveError(
                    "global extension root is required for global loading"
                )
            source_root = (
                arguments.project_root
                if arguments.source == "project"
                else arguments.global_root
            )
            version, registry = _installed_context()
            result = {
                "module": load_resolved_module(
                    source_root
                    / ".sdlc"
                    / "extensions"
                    / arguments.extension,
                    arguments.expected_digest,
                    version,
                    registry,
                )
            }
        else:
            version, registry = _installed_context()
            registry_names = _core_module_names(registry)
            config = load_project_config(
                arguments.project_root,
                registry_names,
                _phase_index(registry),
            )
            result = resolve_extensions(
                arguments.project_root,
                arguments.global_root,
                config,
                version,
                registry,
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except AdaptiveError as error:
        print(error, file=sys.stderr)
        return 2
    except OSError as error:
        detail = str(error).splitlines()[0] if str(error) else "I/O error"
        print(f"operation failed: {detail}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
