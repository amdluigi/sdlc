"""Explicit non-inference SDK transport qualification, outside the portable bundle."""

import argparse
import asyncio
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "sdlc" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from artifact_contracts import ContractIssue, semantic_fields, strict_load_json
import execution_contracts as contracts
import execution_state
import manage_metrics

SDK_VERSION = "1.0.28"
RUNTIME_VERSION = "1.0.105"
PROTOCOL_VERSION = 3
MAX_RUNTIME_BYTES = 512 * 1024 * 1024


def validate_config(value):
    data = contracts._object(value, "", ("schemaVersion", "sdkVersion", "runtime", "timeoutSeconds"))
    contracts._version(data)
    if data["sdkVersion"] != SDK_VERSION:
        raise ContractIssue("E_SDK_VERSION", "/sdkVersion", "only the pinned qualified SDK version is supported")
    timeout = contracts._number(data["timeoutSeconds"], "/timeoutSeconds")
    if timeout > 300:
        raise ContractIssue("E_SDK_LIMIT", "/timeoutSeconds", "qualification timeout must be at most 300 seconds")
    runtime = contracts._object(data["runtime"], "/runtime", ("root", "version", "entrypoint", "files"))
    root = Path(contracts._text(runtime["root"], "/runtime/root", 1024))
    if not root.is_absolute() or str(root).startswith("\\\\"):
        raise ContractIssue("E_SDK_PATH", "/runtime/root", "expected an absolute local runtime directory")
    if runtime["version"] != RUNTIME_VERSION:
        raise ContractIssue("E_SDK_VERSION", "/runtime/version", "only the SDK-pinned native runtime is supported")
    entrypoint = contracts._path(runtime["entrypoint"], "/runtime/entrypoint")
    if Path(entrypoint).name not in ("copilot-runtime", "copilot-runtime.exe"):
        raise ContractIssue("E_SDK_PATH", "/runtime/entrypoint", "expected the native SDK runtime, not the CLI host")
    entries = contracts._array(runtime["files"], "/runtime/files", True)
    paths, exact_paths, total = set(), set(), 0
    for index, raw in enumerate(entries):
        pointer = f"/runtime/files/{index}"
        item = contracts._object(raw, pointer, ("path", "bytes", "sha256"))
        relative = contracts._path(item["path"], pointer + "/path")
        if any(component.endswith((".", " ")) for component in relative.split("/")):
            raise ContractIssue("E_SDK_PATH", pointer + "/path", "noncanonical filesystem alias")
        if relative.casefold() in paths:
            raise ContractIssue("E_SDK_INVENTORY", pointer + "/path", "duplicate or case-alias runtime entry")
        paths.add(relative.casefold())
        exact_paths.add(relative)
        total += contracts._number(item["bytes"], pointer + "/bytes", 0)
        contracts._digest(item["sha256"], pointer + "/sha256")
    companion = str(Path(entrypoint).parent / "runtime.node").replace("\\", "/")
    if entrypoint not in exact_paths or companion not in exact_paths:
        raise ContractIssue("E_SDK_INVENTORY", "/runtime/files", "native entrypoint and companion must be inventoried")
    if total > MAX_RUNTIME_BYTES:
        raise ContractIssue("E_SDK_LIMIT", "/runtime/files", "runtime inventory exceeds the 512 MiB capacity")
    return json.loads(contracts._encoded(data))


def _safe(root, path):
    try:
        return manage_metrics._verify_existing_components(root, path)
    except (manage_metrics.MetricsError, OSError, ValueError) as error:
        raise ContractIssue("E_SDK_PATH", "/runtime", "unsafe runtime path") from error


def _verify_runtime(runtime):
    def unavailable(error):
        raise error

    try:
        root = Path(runtime["root"])
        if not root.is_dir() or manage_metrics._is_link_or_reparse(root):
            raise ContractIssue("E_SDK_PATH", "/runtime/root", "runtime root must be a regular directory")
        _safe(Path(root.anchor), root)
        root = root.resolve(strict=True)
        expected = {item["path"]: item for item in runtime["files"]}
        directories = {parent.as_posix() for relative in expected
                       for parent in Path(relative).parents if parent != Path(".")}
        found = set()
        for directory, children, files in os.walk(root, onerror=unavailable):
            for name in children:
                child = _safe(root, Path(directory) / name)
                if child.relative_to(root).as_posix() not in directories:
                    raise ContractIssue("E_SDK_INVENTORY", "/runtime/files", "unexpected runtime directory")
            for name in files:
                path = _safe(root, Path(directory) / name)
                relative = path.relative_to(root).as_posix()
                if relative not in expected or not stat.S_ISREG(path.stat().st_mode):
                    raise ContractIssue("E_SDK_INVENTORY", "/runtime/files", "unexpected or nonregular runtime file")
                item = expected[relative]
                if path.stat().st_size != item["bytes"]:
                    raise ContractIssue("E_SDK_INTEGRITY", "/runtime/files", "runtime file size changed")
                digest = hashlib.sha256()
                observed = 0
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        observed += len(chunk)
                        if observed > item["bytes"]:
                            raise ContractIssue("E_SDK_INTEGRITY", "/runtime/files", "runtime file grew during verification")
                        digest.update(chunk)
                if observed != item["bytes"] or "sha256:" + digest.hexdigest() != item["sha256"]:
                    raise ContractIssue("E_SDK_INTEGRITY", "/runtime/files", "runtime file hash changed")
                found.add(relative)
        if found != set(expected):
            raise ContractIssue("E_SDK_INVENTORY", "/runtime/files", "runtime inventory is incomplete")
        return _safe(root, root.joinpath(*runtime["entrypoint"].split("/")))
    except OSError as error:
        raise ContractIssue("E_SDK_INTEGRITY", "/runtime/files", "cannot verify the runtime inventory") from error


def _sdk():
    try:
        if importlib.metadata.version("github-copilot-sdk") != SDK_VERSION:
            raise ContractIssue("E_SDK_VERSION", "/sdkVersion", "installed SDK does not match the locked version")
        specification = importlib.util.find_spec("copilot")
        expected = importlib.metadata.distribution("github-copilot-sdk").locate_file("copilot/__init__.py")
        if specification is None or specification.origin is None:
            raise ContractIssue("E_SDK_MISSING", "/", "optional SDK module is unavailable")
        if Path(specification.origin).resolve() != Path(expected).resolve():
            raise ContractIssue("E_SDK_INTEGRITY", "/", "SDK namespace is shadowed by another module")
        return importlib.import_module("copilot")
    except (importlib.metadata.PackageNotFoundError, ModuleNotFoundError) as error:
        raise ContractIssue("E_SDK_MISSING", "/", "install the isolated hash-locked optional SDK; no automatic install") from error


async def _shutdown(client, sdk, timeout, transport_errors):
    confirmed = False
    try:
        async with asyncio.timeout(timeout):
            stopped = await client.stop()
            if stopped is not None:
                raise ContractIssue("E_SDK_SHUTDOWN", "/", "unexpected SDK shutdown response")
        confirmed = True
    except (TimeoutError, *transport_errors) as error:
        raise ContractIssue("E_SDK_SHUTDOWN", "/", "owned SDK runtime graceful shutdown was not confirmed") from error
    except ExceptionGroup as error:
        handled, unhandled = error.split(sdk.StopError)
        if unhandled is not None:
            raise
        raise ContractIssue("E_SDK_SHUTDOWN", "/", "SDK reported owned-runtime cleanup errors") from handled
    finally:
        if not confirmed:
            try:
                async with asyncio.timeout(timeout):
                    forced = await client.force_stop()
                    if forced is not None:
                        raise ContractIssue("E_SDK_SHUTDOWN", "/", "unexpected SDK forced-cleanup response")
            except (TimeoutError, subprocess.TimeoutExpired, *transport_errors) as error:
                raise ContractIssue("E_SDK_SHUTDOWN", "/", "owned SDK runtime forced cleanup was not confirmed") from error


async def qualify(config):
    data = validate_config(config)
    runtime = data["runtime"]
    entrypoint = _verify_runtime(runtime)
    sdk = _sdk()
    transport_errors = (OSError, RuntimeError, sdk._jsonrpc.JsonRpcError, sdk._jsonrpc.ProcessExitedError)
    timeout = data["timeoutSeconds"]
    with tempfile.TemporaryDirectory(prefix="sdlc-sdk-qualification-") as directory:
        try:
            connection = sdk.RuntimeConnection.for_stdio(path=str(entrypoint))
            connection.env = {
                "COPILOT_SKIP_CLI_DOWNLOAD": "1",
                "COPILOT_GITHUB_TELEMETRY_DISABLED": "true",
                "OTEL_SDK_DISABLED": "true",
                "GITHUB_TOKEN": "",
                "GH_TOKEN": "",
            }
            client = sdk.CopilotClient(
                connection=connection, base_directory=directory, working_directory=directory,
                mode="empty", use_logged_in_user=False, log_level="error", builtin_plugin_directories=[],
            )
        except (*transport_errors, ValueError) as error:
            raise ContractIssue("E_SDK_TRANSPORT", "/", "cannot construct the pinned SDK transport") from error
        nonce = "sdlc-sdk-qualification-" + uuid.uuid4().hex
        try:
            async with asyncio.timeout(timeout):
                await client.start()
                try:
                    status = await client.get_status()
                    pong = await client.ping(nonce)
                except (ValueError, TypeError, KeyError, AssertionError) as error:
                    raise ContractIssue("E_SDK_RESPONSE", "/", "SDK could not parse the protocol response") from error
                try:
                    version, protocol = status.version, status.protocol_version
                    message, ping_protocol = pong.message, pong.protocol_version
                except AttributeError as error:
                    raise ContractIssue("E_SDK_RESPONSE", "/", "SDK response is missing required fields") from error
                if version != RUNTIME_VERSION or type(protocol) is not int or protocol != PROTOCOL_VERSION:
                    raise ContractIssue("E_SDK_RESPONSE", "/", "observed runtime version or protocol is unsupported")
                if message != "pong: " + nonce or type(ping_protocol) is not int or ping_protocol != protocol:
                    raise ContractIssue("E_SDK_RESPONSE", "/", "SDK ping response does not match the request")
        except TimeoutError as error:
            raise ContractIssue("E_SDK_TIMEOUT", "/", "SDK startup or protocol qualification timed out") from error
        except transport_errors as error:
            raise ContractIssue("E_SDK_TRANSPORT", "/", "SDK transport qualification failed") from error
        finally:
            await _shutdown(client, sdk, timeout, transport_errors)
    return {
        **semantic_fields(),
        "schemaVersion": 1, "adapter": "copilot-sdk", "sdkVersion": SDK_VERSION,
        "runtimeVersion": version, "protocolVersion": protocol, "transport": "stdio",
        "runtimeDigest": execution_state.digest({
            "version": runtime["version"], "entrypoint": runtime["entrypoint"], "files": runtime["files"],
        }),
        "runtimeFileCount": len(runtime["files"]),
        "runtimeBytes": sum(item["bytes"] for item in runtime["files"]),
        "connectionQualification": "passed", "workerQualification": "not-run",
        "modelRouting": "not-assessed", "cancellation": "not-assessed",
        "telemetryRequested": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    args = parser.parse_args(argv)
    try:
        output = asyncio.run(qualify(strict_load_json(args.input)))
        print(json.dumps(output, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False))
        return 0
    except ContractIssue as error:
        print(error.cli_message(), file=sys.stderr)
        return error.exit_code
    except (OSError, RecursionError):
        print("error[E_SDK_IO] /: SDK qualification I/O failed or input is too deeply nested", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
