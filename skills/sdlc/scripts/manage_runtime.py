#!/usr/bin/env python3
"""Fixed bounded-runtime CLI bridge. JSON stdin; no caller module imports."""

import argparse
import json
from pathlib import Path
import sys

# -I deliberately ignores project PYTHONPATH and the current working directory.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_contracts import ContractIssue, _Pairs, _materialize
import execution_contracts as contracts
import bounded_runtime as runtime


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "prepare_execute", "start", "check", "step",
                                            "observe", "tool", "receive", "stop"))
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(contracts.MAX_INPUT_BYTES + 1)
        if len(raw) > contracts.MAX_INPUT_BYTES:
            raise ContractIssue("E_INPUT_TOO_LARGE", "/", "bridge input exceeds capacity")
        data = _materialize(json.loads(
            raw.decode("utf-8"), object_pairs_hook=_Pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON")),
        ))
        fields = {
            "prepare": ("executionId", "brief", "role", "model", "limits"),
            "prepare_execute": ("executionId", "brief", "role", "model", "limits", "commands"),
            "start": ("envelope", "approvedRuntimeDigest", "approvedRequestDigest"),
            "check": ("envelope",), "step": ("envelope", "prompt"),
            "observe": ("envelope", "response"), "tool": ("envelope", "name", "arguments"),
            "receive": ("envelope", "result"), "stop": ("envelope",),
        }
        contracts._object(data, "", fields[args.operation])
        output = getattr(runtime, args.operation)(args.project_root, *(
            data[key] for key in fields[args.operation]
        ))
        print(json.dumps(output, sort_keys=True, ensure_ascii=True, allow_nan=False))
        return 0
    except ContractIssue as error:
        print(error.cli_message(), file=sys.stderr)
        return error.exit_code
    except (OSError, UnicodeError, RecursionError, ValueError, TypeError):
        print("error[E_RUNTIME_IO] /: bounded bridge input or local operation failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
