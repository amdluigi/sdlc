#!/usr/bin/env python3
"""Initialize, check, and complete an SDLC installation.

Three responsibilities the control plane used to carry as prose in
``SKILL.md``, where they ran at unpredictable moments and could not be
tested:

``init``
    Write ``.sdlc/config.json`` when the project has none.

``check``
    Report which capability each delivery phase has, and which it lacks.

``download``
    Install the bundled implementations ``check`` found missing.

Separating them makes each one an explicit act. Configuration is created
because someone asked for it, not as a side effect of the first
non-trivial task, and nothing is installed except by a command a
developer ran.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import config_contract
from config_contract import ConfigError
from capability_contract import load_registry
from resolve_providers import (
    ProviderError,
    survey_install,
)

TEMPLATE = Path(__file__).resolve().parents[1] / (
    "assets/sdlc-config.template.json"
)
CONFIG_RELATIVE = Path(".sdlc") / "config.json"

STATUS_OK = "ok"
STATUS_MISSING = "missing"
STATUS_DISABLED = "disabled"
STATUS_CHOICE = "choice-required"

OPERATIONS = ("init", "check", "download")

_LABELS = {
    STATUS_OK: "ok",
    STATUS_MISSING: "MISSING",
    STATUS_DISABLED: "disabled",
    STATUS_CHOICE: "choose",
}


class InstallError(ValueError):
    pass


def config_path(project_root):
    return Path(project_root) / CONFIG_RELATIVE


def initialize(project_root, template=TEMPLATE):
    """Create the project configuration, or report that one exists.

    Refuses to overwrite. A configuration records decisions a developer
    made about their lifecycle, and regenerating it from the template
    would silently re-enable phases they had switched off.
    """

    root = Path(project_root)
    if not root.is_dir():
        raise InstallError("project root must be an existing directory")
    path = config_path(root)
    if path.exists() or path.is_symlink():
        return {
            "action": "kept",
            "path": str(CONFIG_RELATIVE.as_posix()),
            "reason": "configuration already exists",
        }
    try:
        document = json.loads(Path(template).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise InstallError(
            "configuration template is unreadable"
        ) from error
    path.parent.mkdir(parents=True, exist_ok=True)
    config_contract.write_json_atomic(path, document)
    phases = list(document.get("phases") or {})
    return {
        "action": "created",
        "path": str(CONFIG_RELATIVE.as_posix()),
        "phases": phases,
        "capabilities": sum(
            len(document["phases"][phase]) for phase in phases
        ),
    }


def placement_index(registry_path):
    """Read delivery phase order and per-capability placement.

    A capability whose bundled skill is absent never reaches the survey's
    capability list, so its phase has to come from the registry. Without
    it the one line a developer most needs to see, the gap, prints under
    no phase at all.
    """

    registry = load_registry(registry_path, on_missing="report")
    rows = registry.get("placement") or registry["modules"]
    categories = registry.get("categories") or {}
    index = {}
    for row in rows:
        meta = categories.get(row.get("category")) or {}
        index[row["name"]] = {
            "deliveryPhase": meta.get("deliveryPhase"),
            "entryGate": meta.get("gate"),
        }
    return list(registry.get("deliveryPhases") or ()), index


def _phase_order(rows, phases=None):
    order = [phase for phase in phases or ()]
    for row in rows:
        phase = row.get("deliveryPhase") or "unplaced"
        if phase not in order:
            order.append(phase)
    return [
        phase for phase in order
        if any(
            (row.get("deliveryPhase") or "unplaced") == phase
            for row in rows
        )
    ]


def check(survey_result, placement=None):
    """Turn a survey into a per-phase verdict.

    The survey answers "what is connected"; this answers "is this
    installation whole". They differ because a survey omits a capability
    whose bundled skill is absent, and an absent capability is precisely
    what a developer running a check wants to see.
    """

    placement = placement or {}
    rows = []
    for entry in survey_result.get("capabilities") or []:
        active = entry.get("active") or {}
        if entry.get("state") == "disabled":
            status = STATUS_DISABLED
            detail = "disabled in configuration"
        elif entry.get("decision") == "developer-choice-required":
            status = STATUS_CHOICE
            detail = "an installed alternative is available"
        else:
            status = STATUS_OK
            detail = active.get("id") or "bundled"
        rows.append({
            "capability": entry["capability"],
            "deliveryPhase": entry.get("deliveryPhase"),
            "entryGate": entry.get("entryGate"),
            "status": status,
            "detail": detail,
        })

    placed = {row["capability"] for row in rows}
    for gap in survey_result.get("missing") or []:
        capability = gap["capability"]
        detail = (
            f"install {gap['requires']}"
            if gap.get("source") == "bundled"
            else f"configured provider {gap['requires']} is not installed"
        )
        if capability in placed:
            for row in rows:
                if row["capability"] == capability:
                    row["status"] = STATUS_MISSING
                    row["detail"] = detail
            continue
        where = placement.get(capability) or {}
        rows.append({
            "capability": capability,
            "deliveryPhase": where.get("deliveryPhase"),
            "entryGate": where.get("entryGate"),
            "status": STATUS_MISSING,
            "detail": detail,
        })

    counts = {
        status: sum(1 for row in rows if row["status"] == status)
        for status in (
            STATUS_OK, STATUS_MISSING, STATUS_DISABLED, STATUS_CHOICE
        )
    }
    return {
        "schemaVersion": 1,
        "healthy": counts[STATUS_MISSING] == 0,
        "counts": counts,
        "capabilities": rows,
        "repair": survey_result.get("repair"),
        "skipped": survey_result.get("skipped") or [],
    }


def render(report, configured, phases=None):
    """Render the check as the report a developer reads."""

    lines = ["SDLC check", ""]
    lines.append(
        f"configuration: {CONFIG_RELATIVE.as_posix()}"
        if configured
        else "configuration: none, so every capability is expected"
    )
    lines.append("")

    rows = report["capabilities"]
    for phase in _phase_order(rows, phases):
        gates = {
            row["entryGate"] for row in rows
            if (row.get("deliveryPhase") or "unplaced") == phase
            and row["entryGate"] is not None
        }
        heading = phase
        if len(gates) == 1:
            heading = f"{phase} (enters at gate {gates.pop()})"
        lines.append(heading)
        for row in rows:
            current = row.get("deliveryPhase") or "unplaced"
            if current != phase:
                continue
            label = _LABELS[row["status"]]
            lines.append(
                f"  {label:<8} {row['capability']:<26} {row['detail']}"
            )
        lines.append("")

    counts = report["counts"]
    total = sum(counts.values())
    lines.append(
        f"{total} capabilities: {counts[STATUS_OK]} ok, "
        f"{counts[STATUS_MISSING]} missing, "
        f"{counts[STATUS_DISABLED]} disabled"
    )
    if counts[STATUS_CHOICE]:
        lines.append(
            f"{counts[STATUS_CHOICE]} awaiting a choice between an "
            "installed alternative and the bundled implementation"
        )
    if report["skipped"]:
        lines.append(
            f"{len(report['skipped'])} provider(s) could not be read; "
            "run survey for detail"
        )
    if report["repair"]:
        lines.append("")
        lines.append("to complete this installation:")
        lines.append(f"  {report['repair']}")
    external = [
        row for row in rows
        if row["status"] == STATUS_MISSING
        and row["detail"].startswith("configured provider")
    ]
    if external:
        lines.append("")
        lines.append(
            "configuration names providers SDLC cannot locate. Install "
            "them yourself or change the configuration:"
        )
        for row in external:
            lines.append(f"  {row['capability']}: {row['detail']}")
    return "\n".join(lines)


def download(report, *, run=False, runner=None):
    """Install the bundled implementations the check found missing.

    Printing the command and running it are separated deliberately. The
    Agent Skills format has no dependency field, so this is the only way
    the requirement gets satisfied, and it is still a developer's
    decision to install software into their machine.
    """

    command = report.get("repair")
    if not command:
        return {"action": "nothing-to-do", "command": None}
    if not run:
        return {"action": "proposed", "command": command}
    if runner is None:
        if shutil.which("npx") is None:
            raise InstallError(
                "npx is not available; install the skills listed by "
                "check with your own package runner"
            )
        runner = _run
    code = runner(command)
    return {
        "action": "installed" if code == 0 else "failed",
        "command": command,
        "exitCode": code,
    }


def _run(command):
    return subprocess.run(command.split(), check=False).returncode


def _survey(args):
    return survey_install(
        args.registry,
        args.project_root,
        args.sdlc_version,
        provider_root=args.provider_root,
        host_profile=args.host_profile,
    )


def _add_survey_arguments(parser):
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--sdlc-version", required=True)
    parser.add_argument("--provider-root", type=Path, action="append")
    parser.add_argument("--host-profile")
    parser.add_argument("--json", action="store_true")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Initialize, check, and complete an SDLC installation."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--project-root", type=Path, required=True)
    init_parser.add_argument("--json", action="store_true")

    _add_survey_arguments(subparsers.add_parser("check"))

    download_parser = subparsers.add_parser("download")
    _add_survey_arguments(download_parser)
    download_parser.add_argument(
        "--run",
        action="store_true",
        help="run the install command instead of proposing it",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result = initialize(args.project_root)
            if args.json:
                print(json.dumps(result, indent=2, sort_keys=True))
            elif result["action"] == "created":
                print(
                    f"created {result['path']} with "
                    f"{result['capabilities']} capabilities across "
                    f"{len(result['phases'])} delivery phases"
                )
            else:
                print(f"{result['path']} already exists, leaving it alone")
            return 0

        phases, placement = placement_index(args.registry)
        report = check(_survey(args), placement)
        if args.command == "check":
            if args.json:
                print(json.dumps(report, indent=2, sort_keys=True))
            else:
                print(render(
                    report,
                    config_path(args.project_root).exists(),
                    phases,
                ))
            return 0 if report["healthy"] else 1

        result = download(report, run=args.run)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        elif result["action"] == "nothing-to-do":
            print("nothing to install, every required skill is present")
        elif result["action"] == "proposed":
            print(result["command"])
            print()
            print("run this command, or repeat with --run to have SDLC "
                  "run it")
        else:
            print(f"{result['action']}: {result['command']}")
        if result["action"] == "failed":
            return 1
        return 0
    except (ConfigError, InstallError, ProviderError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
