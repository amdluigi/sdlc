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
import execution_orchestration as orchestration


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "prepare_execute", "preview_batch", "preview_batch_json",
                                            "approve_batch",
                                            "next_attempt", "prepare_batch", "start", "check", "step",
                                            "dispatch", "abandon", "settle", "observe", "tool", "receive", "stop"))
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
            "preview_batch": ("batch",),
            "preview_batch_json": ("batchJson",),
            "approve_batch": ("batch", "batchDigest"),
            "next_attempt": ("batch", "batchDigest"),
            "prepare_batch": ("batch", "batchDigest", "taskId", "attemptId", "brief", "role", "model", "limits"),
            "start": ("envelope", "approvedRuntimeDigest", "approvedRequestDigest"),
            "check": ("envelope",), "step": ("envelope", "prompt", "componentBytes"),
            "dispatch": ("envelope", "requestId", "outcome"),
            "abandon": ("envelope", "requestId"),
            "settle": ("envelope", "requestId", "outputBytes", "outcome"),
            "observe": ("envelope", "response"), "tool": ("envelope", "name", "arguments"),
            "receive": ("envelope", "result"), "stop": ("envelope",),
        }
        contracts._object(data, "", fields[args.operation])
        if args.operation == "preview_batch":
            output = orchestration.preview_batch(args.project_root, data["batch"])
        elif args.operation == "preview_batch_json":
            raw_batch = data["batchJson"]
            if not isinstance(raw_batch, str) or not raw_batch:
                raise ContractIssue("E_SCHEMA_TYPE", "/batchJson", "expected nonempty JSON text")
            try:
                batch_bytes = raw_batch.encode("utf-8")
            except UnicodeEncodeError as error:
                raise ContractIssue("E_UTF8", "/batchJson", "batch text is not valid Unicode") from error
            if len(batch_bytes) > contracts.MAX_INPUT_BYTES:
                raise ContractIssue("E_INPUT_TOO_LARGE", "/batchJson", "batch text exceeds input capacity")
            try:
                batch = _materialize(json.loads(
                    raw_batch, object_pairs_hook=_Pairs,
                    parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON")),
                ))
            except ContractIssue:
                raise
            except (RecursionError, ValueError) as error:
                raise ContractIssue("E_JSON_SYNTAX", "/batchJson", "batch file is not valid strict JSON") from error
            output = {**orchestration.preview_batch(args.project_root, batch), "batch": batch}
        elif args.operation == "approve_batch":
            output = orchestration.approve_batch(args.project_root, data["batch"], data["batchDigest"])
        elif args.operation == "next_attempt":
            output = orchestration.next_attempt(args.project_root, data["batch"], data["batchDigest"])
        elif args.operation == "prepare_batch":
            output = runtime.prepare_batch(args.project_root, *(
                data[key] for key in fields[args.operation]
            ))
        else:
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
