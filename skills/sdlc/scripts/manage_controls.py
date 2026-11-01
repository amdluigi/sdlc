#!/usr/bin/env python3
"""Explicit opt-in execution controls; never invoke a worker or billing API."""

import argparse
import json
import sys

from artifact_contracts import ContractIssue, strict_load_json
import execution_contracts as contracts
import execution_controls as controls


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("configure", "inspect", "approve", "pause", "resume", "request-cancel",
                 "resolve-manual-cancel", "reconcile", "resolve", "estimate"):
        command = commands.add_parser(name)
        command.add_argument("--project-root", required=True)
        if name in ("configure", "resolve", "estimate"):
            command.add_argument("--input", required=True)
        if name == "configure":
            command.add_argument("--dry-run", action="store_true")
        if name in ("approve", "request-cancel", "resolve-manual-cancel", "reconcile"):
            command.add_argument("--execution-id", required=True)
        if name == "approve":
            for field in ("plan-digest", "execution-policy-digest", "controls-digest"):
                command.add_argument("--" + field, required=True)
        if name in ("request-cancel", "resolve-manual-cancel"):
            command.add_argument("--task-id", required=True)
        if name in ("pause", "resume", "request-cancel", "resolve-manual-cancel"):
            command.add_argument("--reason", required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        project = args.project_root
        if args.command == "configure":
            output = controls.configure_controls(project, strict_load_json(args.input), args.dry_run)
        elif args.command == "inspect":
            output = controls.inspect_controls(project)
        elif args.command == "approve":
            output = controls.approve_controls(project, args.execution_id, args.plan_digest,
                                               args.execution_policy_digest, args.controls_digest)
        elif args.command in ("pause", "resume"):
            output = controls.set_pause(project, args.command == "pause", args.reason)
        elif args.command == "request-cancel":
            output = controls.request_cancel(project, args.execution_id, args.task_id, args.reason)
        elif args.command == "resolve-manual-cancel":
            output = controls.resolve_manual_cancel(project, args.execution_id, args.task_id, args.reason)
        elif args.command == "reconcile":
            output = controls.reconcile_execution(project, args.execution_id)
        elif args.command == "resolve":
            data = contracts._object(strict_load_json(args.input), "", (
                "schemaVersion", "inventory", "profile", "permittedModels", "requestedModel", "observation",
            ))
            contracts._version(data)
            output = controls.resolve_model(data["inventory"], data["profile"], data["permittedModels"],
                                             data["requestedModel"], data["observation"])
        else:
            data = contracts._object(strict_load_json(args.input), "", ("model", "units"))
            output = controls.estimate_cost(data["model"], data["units"])
        print(json.dumps(output, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False))
        return 0
    except ContractIssue as error:
        print(error.cli_message(), file=sys.stderr)
        return error.exit_code
    except RecursionError:
        print("error[E_CONTROLS_JSON] /: JSON nesting exceeds supported depth", file=sys.stderr)
        return 3
    except OSError:
        print("error[E_CONTROLS_IO] /: execution controls I/O failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
