#!/usr/bin/env python3
"""Explicit telemetry consent and supplied observations; no automatic collection."""

import argparse
import json
import sys

from artifact_contracts import ContractIssue, strict_load_json
import execution_contracts as contracts
import execution_telemetry as telemetry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("configure", "inspect", "record", "delete"):
        command = commands.add_parser(name)
        command.add_argument("--project-root", required=True)
        if name in ("configure", "record"):
            command.add_argument("--input", required=True)
        if name == "configure":
            command.add_argument("--dry-run", action="store_true")
        if name == "delete":
            command.add_argument("--store-digest", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            output = telemetry.inspect_telemetry(args.project_root)
        elif args.command == "configure":
            output = telemetry.configure_telemetry(args.project_root, strict_load_json(args.input), args.dry_run)
        elif args.command == "delete":
            output = telemetry.delete_observations(args.project_root, args.store_digest)
        else:
            supplied = contracts._object(strict_load_json(args.input), "", ("schemaVersion", "observation", "inventory"))
            contracts._version(supplied)
            output = telemetry.record_observation(args.project_root, supplied["observation"], supplied["inventory"])
        print(json.dumps(output, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False))
        return 0
    except ContractIssue as error:
        print(error.cli_message(), file=sys.stderr)
        return error.exit_code
    except RecursionError:
        print("error[E_TELEMETRY_JSON] /: JSON nesting exceeds supported depth", file=sys.stderr)
        return 3
    except OSError:
        print("error[E_TELEMETRY_IO] /: local telemetry I/O failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
