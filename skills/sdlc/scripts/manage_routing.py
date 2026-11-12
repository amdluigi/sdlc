#!/usr/bin/env python3
"""Explicit offline model proposals and finite-batch materialization."""

import argparse
import sys

from artifact_contracts import ContractIssue, strict_load_json
import execution_contracts as contracts
import execution_routing as routing


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("propose", "materialize"):
        command = commands.add_parser(name)
        for field in ("plan", "batch", "inventory", "policy"):
            command.add_argument("--" + field, required=True)
        if name == "materialize":
            command.add_argument("--proposal", required=True)
    args = parser.parse_args(argv)
    try:
        values = [strict_load_json(getattr(args, field))
                  for field in ("plan", "batch", "inventory", "policy")]
        if args.command == "propose":
            output = routing.propose_routing(*values)
        else:
            output = routing.materialize_routing(*values, strict_load_json(args.proposal))
        print(contracts._encoded(output))
        return 0
    except ContractIssue as error:
        print(error.cli_message(), file=sys.stderr)
        return error.exit_code
    except RecursionError:
        print("error[E_ROUTING_JSON] /: JSON nesting exceeds supported depth", file=sys.stderr)
        return 3
    except OSError:
        print("error[E_ROUTING_IO] /: routing input/output failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
