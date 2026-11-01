#!/usr/bin/env python3
"""Explicit read-only snapshots, selected analytics and inactive proposal review."""

import argparse
import sys

from artifact_contracts import ContractIssue, strict_load_json
import execution_contracts as contracts
import execution_insights as insights
import execution_manager as manager


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("snapshot", "analyze", "propose", "review", "validate"):
        command = commands.add_parser(name)
        command.add_argument("--project-root", required=True)
        if name in ("snapshot", "analyze", "propose"):
            command.add_argument("--execution-id", required=True, action="append")
        else:
            command.add_argument("--input", required=True)
        if name == "review":
            command.add_argument("--decision", required=True, choices=("approved", "rejected"))
            command.add_argument("--reason", required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        project = manager._root(args.project_root)
        if args.command == "snapshot":
            if len(args.execution_id) != 1:
                raise ContractIssue("E_INSIGHTS_SELECTION", "/executionIds", "snapshot requires exactly one execution ID")
            output = insights.build_snapshot(project, args.execution_id[0])
        elif args.command == "analyze":
            output = insights.analyze_executions(project, args.execution_id)
        elif args.command == "propose":
            output = insights.propose_estimates(project, args.execution_id)
        elif args.command == "review":
            output = insights.review_proposal(strict_load_json(args.input), args.decision == "approved", args.reason)
        else:
            output = insights.validate_proposal(strict_load_json(args.input))
        print(contracts._encoded(output))
        return 0
    except ContractIssue as error:
        print(error.cli_message(), file=sys.stderr)
        return error.exit_code
    except RecursionError:
        print("error[E_INSIGHTS_JSON] /: JSON nesting exceeds supported depth", file=sys.stderr)
        return 3
    except OSError:
        print("error[E_INSIGHTS_IO] /: execution insights I/O failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
