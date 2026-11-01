#!/usr/bin/env python3
"""Explicit supervised native bookkeeping; the active host delegates workers."""

import argparse
import json
import sys

from artifact_contracts import ContractIssue, strict_load_json
import execution_profiles as profiles
import native_execution as native


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("install-profiles", "inspect-profile", "prepare", "digest", "start", "receive"):
        command = commands.add_parser(name)
        command.add_argument("--project-root", required=True)
        if name == "install-profiles":
            command.add_argument("--mode", choices=("copy", "link"), default="copy")
            command.add_argument("--run", action="store_true", help="Explicitly authorize project profile installation")
        if name in ("inspect-profile", "prepare"):
            command.add_argument("--role", choices=tuple(profiles.ROLES), required=True)
        if name == "prepare":
            command.add_argument("--execution-id", required=True)
            command.add_argument("--brief", required=True)
            command.add_argument("--host", required=True)
        if name == "digest":
            command.add_argument("--input", required=True)
        if name in ("start", "receive"):
            command.add_argument("--request", required=True)
        if name == "start":
            command.add_argument("--approved-request-digest", required=True)
        if name == "receive":
            command.add_argument("--receipt", required=True)
            command.add_argument("--result-id", required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        project = args.project_root
        if args.command == "install-profiles":
            output = profiles.install_profiles(project, args.mode, dry_run=not args.run)
        elif args.command == "inspect-profile":
            output = profiles.inspect_profile(project, args.role)
        elif args.command == "prepare":
            output = native.prepare_request(project, args.execution_id, strict_load_json(args.brief),
                                            args.role, strict_load_json(args.host))
        elif args.command == "digest":
            output = native.request_digest(strict_load_json(args.input))
        elif args.command == "start":
            output = native.start_request(project, strict_load_json(args.request), args.approved_request_digest)
        else:
            output = native.receive_receipt(project, strict_load_json(args.request),
                                            strict_load_json(args.receipt), args.result_id)
        print(json.dumps(output, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False))
        return 0
    except ContractIssue as error:
        print(error.cli_message(), file=sys.stderr)
        return error.exit_code
    except RecursionError:
        print("error[E_NATIVE_JSON] /: JSON nesting exceeds supported depth", file=sys.stderr)
        return 3
    except OSError:
        print("error[E_NATIVE_IO] /: native bookkeeping I/O failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
