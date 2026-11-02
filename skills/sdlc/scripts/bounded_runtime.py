"""Optional bounded worker tools. No inference, shell, approval or telemetry API."""

import hashlib
import os
import stat
import time
import uuid
from pathlib import Path

from artifact_contracts import ContractIssue, semantic_fields
import execution_contracts as contracts
import execution_controls as controls
import execution_manager as manager
import execution_state as state
import native_execution as native
import runtime_process


HOST = {"id": "sdlc-vscode-runtime", "build": "0.1.0", "delegationTool": "vscode.lm",
        "allowedActions": ["read", "search", "edit"]}
CEILINGS = {"maxIterations": 16, "maxToolCalls": 32, "maxInputBytes": 262144,
            "maxOutputBytes": 262144, "maxWallMs": 300000}
FILE_BYTES = 65536
EXECUTE_HOST = {**HOST, "allowedActions": [*HOST["allowedActions"], "execute"]}


def _issue(code, message):
    raise ContractIssue("E_RUNTIME_" + code, "/", message)


def _limits(value):
    data = contracts._object(value, "/limits", tuple(CEILINGS))
    for key, ceiling in CEILINGS.items():
        if contracts._number(data[key], "/limits/" + key) > ceiling:
            _issue("LIMIT", "runtime limit exceeds the supported ceiling")
    return data


def _model(value):
    data = contracts._object(value, "/model", ("id", "vendor", "family", "version"))
    for key, item in data.items():
        contracts._text(item, "/model/" + key, 128)
    return data


def _envelope(value):
    execute = isinstance(value, dict) and type(value.get("schemaVersion")) is int and value["schemaVersion"] == 2
    data = contracts._object(value, "", (
        "schemaVersion", "request", "model", "limits", "controlsDigest", "guidanceDigests",
    ) + (("commands",) if execute else ()))
    if not execute:
        contracts._version(data)
    native._request(data["request"])
    if data["request"]["host"] != (EXECUTE_HOST if execute else HOST):
        _issue("UNSUPPORTED", "runtime requires its fixed bounded host identity")
    if execute:
        _commands(data["commands"], data["request"]["projectRoot"], bound=True)
    _model(data["model"])
    _limits(data["limits"])
    contracts._digest(data["controlsDigest"], "/controlsDigest")
    digests = data["guidanceDigests"]
    if not isinstance(digests, dict) or len(digests) > contracts.MAX_ITEMS:
        _issue("BINDING", "guidance digests require a bounded path mapping")
    for relative, digest in digests.items():
        contracts._path(relative, "/guidanceDigests")
        contracts._digest(digest, "/guidanceDigests")
    if set(digests) != set(data["request"]["brief"]["guidance"]):
        _issue("BINDING", "guidance inventory differs from the native brief")
    return data


def _path(root, relative):
    contracts._path(relative, "/path")
    parts = relative.split("/")
    reserved = {"con", "prn", "aux", "nul", *("com" + str(n) for n in range(1, 10)),
                *("lpt" + str(n) for n in range(1, 10))}
    aliases = any(part.endswith((".", " ")) or part.split(".")[0].casefold() in reserved for part in parts)
    if aliases or parts[0].casefold() in (".git", ".sdlc") or relative.casefold().startswith(".github/agents/"):
        _issue("SCOPE", "runtime cannot access execution or profile controls")
    path = manager._safe(root, root.joinpath(*parts))
    trusted = Path(__file__).resolve().parent.parent
    package = trusted.parents[1] / "packages" / "sdlc-runtime"
    if path == trusted or trusted in path.parents or path == package or package in path.parents:
        _issue("SCOPE", "worker cannot access trusted runtime implementation")
    if path.exists():
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            _issue("PATH", "tools require single-link regular files")
    return path


def _bytes(root, relative):
    path = _path(root, relative)
    with path.open("rb") as stream:
        content = stream.read(FILE_BYTES + 1)
    if len(content) > FILE_BYTES:
        _issue("LIMIT", "file exceeds the bounded tool input")
    return content


def _hash(content):
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _barriers(root):
    store = controls._read(root)
    if store and (store["paused"] or any(
        entry["status"] == "pending" for entry in store["cancelRequests"]
    )):
        _issue("CONTROLS", "pause or pending cancellation blocks bounded work")
    if store and store["policy"]["enabled"] and store["policy"]["mode"] != "supervised":
        _issue("CONTROLS", "enabled manual controls do not qualify native runtime dispatch")
    return state.digest(store)


def _prepared(root, envelope, revision, *, in_flight=False):
    envelope = _envelope(envelope)
    if envelope["schemaVersion"] == 2 and not runtime_process.supported():
        _issue("UNSUPPORTED", "execute requires qualified owner-death containment; POSIX execute is unavailable")
    request = envelope["request"]
    native._validate(root, request, revision)
    if manager._consent(root, enabled=True) != revision["consent"]:
        _issue("APPROVAL", "execution consent changed")
    if envelope["controlsDigest"] != _barriers(root):
        _issue("APPROVAL", "control bindings changed")
    host = EXECUTE_HOST if envelope["schemaVersion"] == 2 else HOST
    if not set(request["brief"]["allowedActions"]) <= set(host["allowedActions"]):
        _issue("UNSUPPORTED", "command execution is not qualified")
    store = controls._read(root)
    if store and store["policy"]["enabled"]:
        expected = {"planDigest": state.digest(revision["plan"]),
                    "executionPolicyDigest": state.digest(revision["consent"]),
                    "controlsDigest": controls._digest(store)}
        if store["approvals"].get(request["binding"]["executionId"]) != expected:
            _issue("APPROVAL", "separate current supervised controls approval is required")
        if envelope["model"]["id"] not in store["policy"]["permittedModels"]:
            _issue("APPROVAL", "selected model is not explicitly permitted by supervised controls")
    if envelope["schemaVersion"] == 2:
        for command in envelope["commands"]:
            _executable(command["executable"], command["executableDigest"])
    for identifier in manager._record_ids(root):
        unknown = controls._unknown_native_attempts(manager._load(root, identifier))
        if any(not (in_flight and identifier == request["binding"]["executionId"]
                    and entry["requestDigest"] == state.digest(request)) for entry in unknown):
            _issue("UNRESOLVED", "unconfirmed native work requires explicit host reconciliation")
    source = revision["plan"]["sourcePlan"]
    if source["digest"] != _hash(_bytes(root, source["path"])):
        _issue("SOURCE", "approved source plan bytes changed")
    for relative, digest in envelope["guidanceDigests"].items():
        if digest != _hash(_bytes(root, relative)):
            _issue("SOURCE", "approved guidance bytes changed")
    protected = {source["path"].casefold(), *(p.casefold() for p in request["brief"]["guidance"])}
    for relative in request["brief"]["ownership"]:
        _path(root, relative)
        if relative.casefold() in protected:
            _issue("SCOPE", "worker ownership cannot modify source plan or guidance")
    return request


def prepare(project_root, execution_id, brief, role, model, limits):
    root = manager._root(project_root)
    manager._consent(root, enabled=True)
    _model(model)
    _limits(limits)
    if isinstance(brief, dict) and isinstance(brief.get("allowedActions"), list) and "execute" in brief["allowedActions"]:
        _issue("UNSUPPORTED", "execute has no qualified process-tree cancellation boundary")
    request = native.prepare_request(root, execution_id, brief, role, HOST)
    envelope = {
        "schemaVersion": 1, "request": request, "model": model, "limits": limits,
        "controlsDigest": _barriers(root),
        "guidanceDigests": {p: _hash(_bytes(root, p)) for p in request["brief"]["guidance"]},
    }
    _prepared(root, envelope, manager._load(root, execution_id)["revisions"][-1])
    return envelope


def _executable(value, expected=None):
    path = Path(contracts._text(value, "/executable", 2048))
    if not path.is_absolute() or path.is_symlink() or not path.is_file() or str(path.resolve()) != str(path):
        _issue("COMMAND", "executable must be an exact absolute resolved regular file")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    actual = "sha256:" + digest.hexdigest()
    if expected is not None and actual != expected:
        _issue("COMMAND", "approved executable bytes changed")
    return actual


def _commands(value, project_root, bound=False):
    commands = contracts._array(value, "/commands")
    if not commands or len(commands) > 16:
        _issue("COMMAND", "execute requires one to sixteen explicitly approved command definitions")
    identities = set()
    for command in commands:
        contracts._object(command, "/commands", (
            "id", "executable", "argv", "cwd", "timeoutMs", "maxOutputBytes",
        ) + (("executableDigest",) if bound else ()))
        contracts._id(command["id"], "/commands/id")
        if command["id"] in identities:
            _issue("COMMAND", "duplicate command identity")
        identities.add(command["id"])
        contracts._text(command["executable"], "/executable", 2048)
        name = Path(command["executable"]).name.casefold()
        if name.removesuffix(".exe") in ("cmd", "powershell", "pwsh", "sh", "bash", "zsh", "dash", "fish", "csh", "ksh"):
            _issue("COMMAND", "shell executables are not supported command tools")
        argv = command["argv"]
        if not isinstance(argv, list) or len(argv) > 64 or any(
            not isinstance(arg, str) or "\0" in arg or len(arg) > 8192 for arg in argv
        ):
            _issue("COMMAND", "argv must be a bounded exact string list")
        if command["cwd"] != project_root:
            _issue("COMMAND", "command cwd must exactly match the approved project root")
        if contracts._number(command["timeoutMs"], "/timeoutMs") > 10000 or (
            contracts._number(command["maxOutputBytes"], "/maxOutputBytes") > 65536
        ):
            _issue("COMMAND", "command bounds exceed local ceilings")
        if bound:
            contracts._digest(command["executableDigest"], "/executableDigest")
    return commands


def prepare_execute(project_root, execution_id, brief, role, model, limits, commands):
    root = manager._root(project_root)
    manager._consent(root, enabled=True)
    if not runtime_process.supported():
        _issue("UNSUPPORTED", "execute requires qualified owner-death containment; POSIX execute is unavailable")
    _model(model)
    _limits(limits)
    _commands(commands, str(root))
    request = native.prepare_request(root, execution_id, brief, role, EXECUTE_HOST)
    if "execute" not in request["brief"]["allowedActions"]:
        _issue("COMMAND", "execute envelope requires an explicitly approved execute brief")
    envelope = {
        "schemaVersion": 2, "request": request, "model": model, "limits": limits,
        "controlsDigest": _barriers(root),
        "guidanceDigests": {p: _hash(_bytes(root, p)) for p in request["brief"]["guidance"]},
        "commands": [{**command, "executableDigest": _executable(command["executable"])}
                     for command in commands],
    }
    _prepared(root, envelope, manager._load(root, execution_id)["revisions"][-1])
    return envelope


def _store_path(root):
    path = manager._safe(root, manager.lock_path(root).parent / "bounded-runtime.json")
    if not (root / ".git").is_dir():
        if manager.manage_metrics._run_git(
            root, ["check-ignore", "--no-index", "--quiet", "--", path.relative_to(root).as_posix()]
        ).returncode:
            _issue("STORAGE", "runtime storage is not proven ignored")
    return path


def _store(root):
    value = manager._read(_store_path(root))
    execute = isinstance(value, dict) and type(value.get("schemaVersion")) is int and value["schemaVersion"] == 2
    contracts._object(value, "", (
        "schemaVersion", "runtimeDigest", "requestDigest", "callId", "status",
        "startedNs", "startedWallNs", "iterations", "toolCalls", "inputBytes", "outputBytes",
    ) + (("commandEvidence",) if execute else ()))
    if not execute:
        contracts._version(value)
    if execute:
        for evidence in contracts._array(value["commandEvidence"], "/commandEvidence"):
            contracts._object(evidence, "/commandEvidence", (
                "commandId", "commandDigest", "status", "exitCode", "outputBytes", "containment",
            ))
            contracts._id(evidence["commandId"], "/commandId")
            contracts._digest(evidence["commandDigest"], "/commandDigest")
            contracts._enum(evidence["status"], "/status",
                            ("running", "unknown", "passed", "nonzero", "timeout", "output-limit", "spawn-failed"))
            contracts._enum(evidence["containment"], "/containment",
                            ("windows-suspended-job", "posix-session", "unavailable"))
            if evidence["exitCode"] is not None:
                if type(evidence["exitCode"]) is not int:
                    _issue("BINDING", "command exit code must be an integer or unavailable")
            contracts._number(evidence["outputBytes"], "/outputBytes", 0)
    for key in ("runtimeDigest", "requestDigest"):
        contracts._digest(value[key], "/" + key)
    contracts._id(value["callId"], "/callId")
    contracts._enum(value["status"], "/status", ("active", "unknown", "reported"))
    for key in ("startedNs", "startedWallNs", "iterations", "toolCalls", "inputBytes", "outputBytes"):
        contracts._number(value[key], "/" + key, 0)
    return value


def inspect(project_root):
    return _store(manager._root(project_root))


def start(project_root, envelope, approved_runtime_digest, approved_request_digest):
    envelope = _envelope(envelope)
    if state.digest(envelope) != approved_runtime_digest:
        _issue("APPROVAL", "separate runtime/model/limits digest approval is required")

    def guard(root, revision):
        _prepared(root, envelope, revision)
        path = _store_path(root)
        if path.exists() and _store(root)["status"] != "reported":
            _issue("UNRESOLVED", "previous bounded work requires explicit host reconciliation")
        manager._write(root, path, {
            "schemaVersion": envelope["schemaVersion"], "runtimeDigest": state.digest(envelope),
            "requestDigest": state.digest(envelope["request"]),
            "callId": "runtime-" + uuid.uuid4().hex, "status": "active",
            "startedNs": time.monotonic_ns(), "startedWallNs": time.time_ns(), "iterations": 0, "toolCalls": 0,
            "inputBytes": 0, "outputBytes": 0,
            **({"commandEvidence": []} if envelope["schemaVersion"] == 2 else {}),
        })

    return native.start_request(project_root, envelope["request"], approved_request_digest,
                                _guard=guard, _bounded=True)


def _current(root, envelope, revision=None, *, allow_command=False):
    envelope = _envelope(envelope)
    revision = revision or manager._load(root, envelope["request"]["binding"]["executionId"])["revisions"][-1]
    request = _prepared(root, envelope, revision, in_flight=True)
    store = _store(root)
    if store["runtimeDigest"] != state.digest(envelope) or store["requestDigest"] != state.digest(request):
        _issue("BINDING", "active runtime differs from this request")
    if store["status"] != "active":
        _issue("UNRESOLVED", "runtime is stopped, unknown or already reported")
    if not allow_command and any(item["status"] == "running" for item in store.get("commandEvidence", [])):
        _issue("UNRESOLVED", "in-flight command work blocks other runtime operations")
    brief = request["brief"]
    task = manager._projection(revision)["tasks"][brief["taskId"]]
    if task["status"] != "running" or task["attemptId"] != brief["attemptId"] or (
        native._request_markers(revision["events"], brief["taskId"], brief["attemptId"]) != [state.digest(request)]
    ):
        _issue("BINDING", "no unique current running native attempt")
    elapsed = time.monotonic_ns() - store["startedNs"]
    wall_elapsed = time.time_ns() - store["startedWallNs"]
    maximum = envelope["limits"]["maxWallMs"] * 1000000
    if elapsed < 0 or elapsed >= maximum or wall_elapsed < 0 or wall_elapsed >= maximum:
        _issue("LIMIT", "runtime wall-time lease expired")
    return store


def check(project_root, envelope):
    manager._consent(manager._root(project_root), enabled=True)
    with manager._writer(project_root) as root:
        _current(root, envelope)
    return semantic_fields()


def _charge(store, envelope, field, amount, limit):
    if store[field] + amount > envelope["limits"][limit]:
        _issue("LIMIT", "approved runtime budget exhausted")
    store[field] += amount


def step(project_root, envelope, prompt):
    manager._consent(manager._root(project_root), enabled=True)
    if not isinstance(prompt, str):
        _issue("PROTOCOL", "prompt must be text")
    with manager._writer(project_root) as root:
        store = _current(root, envelope)
        _charge(store, envelope, "iterations", 1, "maxIterations")
        _charge(store, envelope, "inputBytes", len(prompt.encode("utf-8")), "maxInputBytes")
        manager._write(root, _store_path(root), store)
    return {**semantic_fields(), "remainingOutputBytes": envelope["limits"]["maxOutputBytes"] - store["outputBytes"]}


def observe(project_root, envelope, response):
    manager._consent(manager._root(project_root), enabled=True)
    if not isinstance(response, str):
        _issue("PROTOCOL", "response must be text")
    with manager._writer(project_root) as root:
        store = _current(root, envelope)
        _charge(store, envelope, "outputBytes", len(response.encode("utf-8")), "maxOutputBytes")
        manager._write(root, _store_path(root), store)
    return semantic_fields()


def tool(project_root, envelope, name, arguments):
    manager._consent(manager._root(project_root), enabled=True)
    if name == "execute":
        return _execute(project_root, envelope, arguments)
    with manager._writer(project_root) as root:
        store = _current(root, envelope)
        brief = envelope["request"]["brief"]
        if name not in ("read", "search", "edit") or name not in brief["allowedActions"]:
            _issue("UNSUPPORTED", "tool is not in the approved bounded action set")
        fields = {"read": ("path",), "search": ("path", "query"),
                  "edit": ("path", "expectedDigest", "content")}[name]
        args = contracts._object(arguments, "/arguments", fields)
        relative = contracts._path(args["path"], "/path")
        allowed = brief["ownership"] if name == "edit" else brief["ownership"] + brief["guidance"]
        if relative not in allowed:
            _issue("SCOPE", "tool requires an exact approved file path")
        path = _path(root, relative)
        _charge(store, envelope, "toolCalls", 1, "maxToolCalls")
        _charge(store, envelope, "inputBytes", len(contracts._encoded(args).encode()), "maxInputBytes")
        # Consume authorization before touching a file; interrupted edits are never retried.
        manager._write(root, _store_path(root), store)
        content = _bytes(root, relative) if path.exists() else b""
        try:
            text = content.decode("utf-8")
        except UnicodeError as error:
            raise ContractIssue("E_RUNTIME_ENCODING", "/", "tools require UTF-8 files") from error
        if name == "read":
            output = {"content": text, "digest": _hash(content), "exists": path.exists()}
        elif name == "search":
            query = contracts._text(args["query"], "/query", 256)
            output = {"matches": [{"line": index, "text": line}
                                  for index, line in enumerate(text.splitlines(), 1) if query in line]}
        else:
            contracts._digest(args["expectedDigest"], "/expectedDigest")
            if not isinstance(args["content"], str) or "\r" in args["content"]:
                _issue("ENCODING", "edit requires LF text")
            replacement = args["content"].encode("utf-8")
            if len(replacement) > FILE_BYTES or _hash(content) != args["expectedDigest"]:
                _issue("EDIT", "edit exceeds bounds or compare-and-swap content changed")
            output = {"digest": _hash(replacement)}
        _charge(store, envelope, "outputBytes", len(contracts._encoded(output).encode()), "maxOutputBytes")
        if name == "edit":
            # Cooperative same-user boundary, not a sandbox against hostile filesystem races.
            _current(root, envelope)
            _path(root, relative)
            if (_bytes(root, relative) if path.exists() else b"") != content:
                _issue("EDIT", "file changed before replacement")
            staging = manager._safe(root, path.parent / (".sdlc-edit-" + uuid.uuid4().hex))
            mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
            descriptor = os.open(staging, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(replacement)
                    stream.flush()
                    os.fsync(stream.fileno())
                _current(root, envelope)
                _path(root, relative)
                if (_bytes(root, relative) if path.exists() else b"") != content:
                    _issue("EDIT", "file changed before atomic replacement")
                os.replace(staging, path)
            finally:
                if staging.exists():
                    manager._safe(root, staging).unlink()
        manager._write(root, _store_path(root), store)
        return output


def _execute(project_root, envelope, arguments):
    if not runtime_process.supported():
        _issue("UNSUPPORTED", "execute requires qualified owner-death containment; POSIX execute is unavailable")
    with manager._writer(project_root) as root:
        store = _current(root, envelope)
        if envelope["schemaVersion"] != 2 or "execute" not in envelope["request"]["brief"]["allowedActions"]:
            _issue("UNSUPPORTED", "legacy runtime has no execute authority")
        args = contracts._object(arguments, "/arguments", ("commandId",))
        command = next((item for item in envelope["commands"] if item["id"] == args["commandId"]), None)
        if command is None:
            _issue("COMMAND", "worker may select only an approved command ID")
        if any(item["status"] == "running" for item in store["commandEvidence"]):
            _issue("UNRESOLVED", "previous command work is unconfirmed")
        if any(item["commandId"] == command["id"] for item in store["commandEvidence"]):
            _issue("UNRESOLVED", "each approved command ID is single-use; retries require separate controller authority")
        _charge(store, envelope, "toolCalls", 1, "maxToolCalls")
        _charge(store, envelope, "inputBytes", len(contracts._encoded(args).encode()), "maxInputBytes")
        # Reserve enough output before dispatch, never discover missing budget after side effects.
        if store["outputBytes"] + 6 * command["maxOutputBytes"] + 1024 > envelope["limits"]["maxOutputBytes"]:
            _issue("LIMIT", "remaining output budget cannot cover the approved command")
        evidence = {"commandId": command["id"], "commandDigest": state.digest(command),
                    "status": "running", "exitCode": None, "outputBytes": 0,
                    "containment": "unavailable"}
        store["commandEvidence"].append(evidence)
        manager._write(root, _store_path(root), store)
    try:
        def command_guard():
            with manager._writer(project_root) as locked:
                _current(locked, envelope, allow_command=True)
        output = runtime_process.run(command, command_guard)
    except BaseException:
        _stop_command(project_root, envelope)
        raise
    try:
        with manager._writer(project_root) as root:
            store = _current(root, envelope, allow_command=True)
            evidence.update(output["evidence"])
            output["evidence"] = evidence
            store["commandEvidence"][-1] = evidence
            _charge(store, envelope, "outputBytes", len(contracts._encoded(output).encode()), "maxOutputBytes")
            if evidence["status"] in ("timeout", "output-limit"):
                store["status"] = "unknown"
            manager._write(root, _store_path(root), store)
    except BaseException:
        _stop_command(project_root, envelope)
        raise
    return output


def _stop_command(project_root, envelope):
    # Only the metadata lock is retried, never a command or provider operation.
    for attempt in range(50):
        try:
            return stop(project_root, envelope)
        except ContractIssue as error:
            if error.code != "E_EXECUTION_BUSY" or attempt == 49:
                raise
            time.sleep(.02)


def stop(project_root, envelope):
    envelope = _envelope(envelope)
    _store(manager._root(project_root))
    with manager._writer(project_root) as root:
        store = _store(root)
        if store["runtimeDigest"] != state.digest(envelope):
            _issue("BINDING", "cannot stop a different runtime")
        if store["status"] == "active":
            store["status"] = "unknown"
            for entry in store.get("commandEvidence", []):
                if entry["status"] == "running":
                    entry["status"] = "unknown"
            manager._write(root, _store_path(root), store)
    return {**semantic_fields(), "localStop": "requested", "remoteStop": "unconfirmed",
            "redispatch": False}


def receive(project_root, envelope, result):
    envelope = _envelope(envelope)
    root = manager._root(project_root)
    store = _store(root)
    revision = manager._load(root, envelope["request"]["binding"]["executionId"])["revisions"][-1]
    result = contracts.validate_task_result(result, revision["plan"], envelope["request"]["brief"])["data"]
    if envelope["schemaVersion"] == 2:
        if result["findings"] or result["blockers"]:
            _issue("PROTOCOL", "execute receipts cannot persist worker free text or command output")
        for item in result["verification"]:
            if item["result"] not in ("passed", "failed") and (
                item["command"] is not None or item["revision"] is not None or item["summary"] != item["result"]
            ):
                _issue("PROTOCOL", "unobserved execute verification requires null provenance and a closed status summary")

    def receipt_guard(locked, revision):
        current = _current(locked, envelope, revision)
        evidence = current.get("commandEvidence", [])
        if any(item["status"] == "running" for item in evidence):
            _issue("UNRESOLVED", "command work is not confirmed")
        for item in result["verification"]:
            if item["result"] not in ("passed", "failed"):
                continue
            matches = [entry for entry in evidence if
                       item["command"] == "runtime-command:" + entry["commandId"]
                       and item["revision"] == entry["commandDigest"]]
            expected = "passed" if item["result"] == "passed" else "nonzero"
            if len(matches) != 1 or matches[0]["status"] != expected or item["summary"] != expected:
                _issue("UNSUPPORTED", "verification must exactly reference unique observed command evidence")
    receipt = {"schemaVersion": 1, "requestDigest": state.digest(envelope["request"]),
               "hostId": HOST["id"], "hostBuild": HOST["build"], "callId": store["callId"], "result": result}
    output = native.receive_receipt(
        root, envelope["request"], receipt, store["callId"],
        _guard=receipt_guard,
    )
    with manager._writer(root):
        store = _store(root)
        if store["runtimeDigest"] != state.digest(envelope):
            _issue("BINDING", "runtime changed after receipt")
        store["status"] = "reported"
        manager._write(root, _store_path(root), store)
    return output
