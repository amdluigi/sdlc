#!/usr/bin/env python3
"""Explicit local manual execution CLI; no arbitrary event injection."""

import argparse
import json
import sys

from artifact_contracts import ContractIssue, strict_load_json
import execution_manager as manager
from execution_renderers import render_execution


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("configure", "import", "inspect", "approve", "record", "receive", "accept",
                 "report", "recover", "delete"):
        command = commands.add_parser(name)
        command.add_argument("--project-root", required=True)
        if name not in ("configure", "import"):
            command.add_argument("--execution-id", required=True)
        if name in ("configure", "import", "accept"):
            command.add_argument("--input", required=True)
        if name == "configure":
            command.add_argument("--dry-run", action="store_true")
        if name == "approve":
            command.add_argument("--plan-digest", required=True)
            command.add_argument("--policy-digest", required=True)
        if name == "record":
            command.add_argument("--task-id", required=True)
            command.add_argument("--action", required=True,
                                 choices=("ready", "start", "progress", "block", "unblock", "fail", "cancel", "reject"))
            command.add_argument("--attempt-id")
            command.add_argument("--reason")
        if name == "receive":
            command.add_argument("--result-id", required=True)
            command.add_argument("--brief", required=True)
            command.add_argument("--result", required=True)
        if name == "delete":
            command.add_argument("--confirm-delete", required=True,
                                 help="Repeat the exact execution ID to authorize deletion")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        project = args.project_root
        if args.command == "configure":
            output = manager.configure_policy(project, strict_load_json(args.input), args.dry_run)
        elif args.command == "import":
            output = manager.import_plan(project, strict_load_json(args.input))
        elif args.command in ("inspect", "report", "recover"):
            output = manager.inspect_execution(project, args.execution_id)
            if args.command == "report":
                sys.stdout.write(render_execution(output))
                return 0
            if args.command == "recover":
                output["recovery"] = "inspection-only; no redispatch, lock theft or record truncation"
        elif args.command == "approve":
            output = manager.approve_plan(project, args.execution_id, args.plan_digest, args.policy_digest)
        elif args.command == "record":
            output = manager.record_task(project, args.execution_id, args.task_id,
                                         args.action, args.attempt_id, args.reason)
        elif args.command == "receive":
            output = manager.receive_result(project, args.execution_id, args.result_id,
                                            strict_load_json(args.brief), strict_load_json(args.result))
        elif args.command == "accept":
            output = manager.accept_task(project, args.execution_id, strict_load_json(args.input))
        else:
            if args.confirm_delete != args.execution_id:
                raise ContractIssue("E_EXECUTION_DELETE", "/confirm-delete", "explicit deletion identity does not match")
            output = manager.delete_execution(project, args.execution_id)
        print(json.dumps(output, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False))
        return 0
    except ContractIssue as error:
        print(error.cli_message(), file=sys.stderr)
        return error.exit_code
    except RecursionError:
        print("error[E_EXECUTION_JSON] /: JSON nesting exceeds supported depth", file=sys.stderr)
        return 3
    except OSError:
        print("error[E_EXECUTION_IO] /: local execution I/O failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
