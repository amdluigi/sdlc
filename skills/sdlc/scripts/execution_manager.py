"""Confined cooperative single-writer management; no command or worker execution."""

import os
import stat
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from artifact_contracts import ContractIssue, strict_load_json, semantic_fields
import execution_contracts as contracts
import execution_state as state
import manage_metrics


def _safe(root, candidate, *, _writer_lock=False):
    try:
        return manage_metrics._verify_existing_components(root, candidate, ephemeral_lock=_writer_lock)
    except (manage_metrics.MetricsError, OSError, ValueError) as error:
        raise ContractIssue("E_EXECUTION_PATH", "/", "unsafe execution path") from error


def _root(project_root):
    root = Path(os.path.abspath(project_root))
    try:
        if not root.is_dir() or manage_metrics._is_link_or_reparse(root):
            raise ContractIssue("E_EXECUTION_PATH", "/", "project root must be a regular directory")
        return root.resolve(strict=True)
    except OSError as error:
        raise ContractIssue("E_EXECUTION_PATH", "/", "cannot inspect project root") from error


def _directory(project_root, execution_id=None):
    root = _root(project_root)
    git = root / ".git"
    try:
        _safe(root, git)
        if git.is_dir():
            directory = git / "sdlc" / "executions"
        else:
            if git.exists() and not manage_metrics._valid_gitfile_project(root, git):
                raise ContractIssue("E_EXECUTION_STORAGE", "/", "unsupported Git metadata")
            directory = root / ".sdlc" / "local" / "executions"
            targets = [".sdlc/local/executions", ".sdlc/local/executions.lock"]
            if execution_id is not None:
                targets.append(f".sdlc/local/executions/{execution_id}.json")
            for target in targets:
                ignored = manage_metrics._run_git(
                    root, ["check-ignore", "--no-index", "--quiet", "--", target]
                )
                if ignored.returncode != 0:
                    raise ContractIssue("E_EXECUTION_STORAGE", "/", "local execution storage is not proven ignored")
        return root, _safe(root, directory)
    except (manage_metrics.MetricsError, OSError) as error:
        raise ContractIssue("E_EXECUTION_STORAGE", "/", "cannot verify local execution storage") from error


def execution_path(project_root, execution_id):
    contracts._id(execution_id, "/executionId")
    root, directory = _directory(project_root, execution_id)
    return _safe(root, directory / (execution_id + ".json"))


def lock_path(project_root):
    root, directory = _directory(project_root)
    return _safe(root, directory.parent / "executions.lock", _writer_lock=True)


def _consent_path(root):
    return _safe(root, root / ".sdlc" / "execution-policy.json")


def _read(path):
    try:
        if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
            raise ContractIssue("E_EXECUTION_READ", "/", "execution input is not a regular file")
        return strict_load_json(path)
    except ContractIssue as error:
        raise ContractIssue(error.code, "/", "invalid stored execution input", error.exit_code) from error
    except RecursionError as error:
        raise ContractIssue("E_EXECUTION_JSON", "/", "stored JSON nesting exceeds supported depth") from error
    except OSError as error:
        raise ContractIssue("E_EXECUTION_READ", "/", "cannot read stored execution input") from error


def _consent(root, enabled=False):
    path = _consent_path(root)
    consent = state.validate_consent(_read(path)) if path.exists() else None
    if enabled and (consent is None or not consent["policy"]["enabled"]):
        raise ContractIssue("E_EXECUTION_DISABLED", "/", "local execution policy is disabled")
    return consent


@contextmanager
def _writer(project_root):
    root, directory = _directory(project_root)
    lock = lock_path(root)
    descriptor = None
    owned = False
    try:
        directory.parent.mkdir(parents=True, exist_ok=True)
        _safe(root, lock, _writer_lock=True)
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as error:
            raise ContractIssue("E_EXECUTION_BUSY", "/", "another or abandoned writer lock requires inspection") from error
        owned = True
        with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as stream:
            descriptor = None
            stream.write(str(os.getpid()) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        yield root
    except OSError as error:
        raise ContractIssue("E_EXECUTION_WRITE", "/", "local execution transaction failed") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        # A lock belonging to another writer must never be removed.
        if owned:
            _safe(root, lock, _writer_lock=True)
            try:
                lock.unlink()
            except OSError as error:
                raise ContractIssue("E_EXECUTION_WRITE", "/", "cannot release owned execution lock") from error


def _replace(temporary, path):
    if os.name != "nt" or not path.exists():
        os.replace(temporary, path)
        return
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    rename = kernel.SetFileInformationByHandle
    rename.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    rename.restype = wintypes.BOOL

    class RenameInfo(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("RootDirectory", wintypes.HANDLE),
                    ("FileNameLength", wintypes.DWORD), ("FileName", wintypes.WCHAR * 1)]

    name = str(path).encode("utf-16-le")
    size = RenameInfo.FileName.offset + len(name) + 2
    buffer = ctypes.create_string_buffer(max(size, ctypes.sizeof(RenameInfo)))
    info = RenameInfo.from_buffer(buffer)
    # FileRenameInfoEx: atomic replacement with POSIX semantics keeps open,
    # delete-shared snapshots alive, without ReplaceFileW's metadata merge.
    info.Flags = 0x1 | 0x2
    info.FileNameLength = len(name)
    ctypes.memmove(ctypes.addressof(buffer) + RenameInfo.FileName.offset, name, len(name))
    handle = create(str(temporary), 0x10000, 0x1 | 0x2 | 0x4, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not rename(handle, 22, buffer, size):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        close(handle)


def _write(root, path, value):
    encoded = contracts._encoded(value) + "\n"
    if len(encoded.encode("utf-8")) > contracts.MAX_INPUT_BYTES:
        raise ContractIssue("E_INPUT_TOO_LARGE", "/", "execution record capacity exceeded")
    temporary = None
    try:
        _safe(root, path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _safe(root, path)
        descriptor, name = tempfile.mkstemp(prefix="execution-", suffix=".tmp", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            os.chmod(temporary, 0o600)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        _safe(root, path)
        _replace(temporary, path)
    except OSError as error:
        raise ContractIssue("E_EXECUTION_WRITE", "/", "cannot atomically persist execution record") from error
    finally:
        if temporary is not None and temporary.exists():
            _safe(root, temporary)
            try:
                temporary.unlink()
            except OSError as error:
                raise ContractIssue("E_EXECUTION_WRITE", "/", "cannot remove execution transaction temporary") from error


def configure_policy(project_root, policy, dry_run=False):
    policy = state.validate_policy(policy)
    root, _ = _directory(project_root)
    if dry_run:
        return {**semantic_fields(), "dryRun": True, "policy": policy}
    with _writer(root):
        existing = _consent(root)
        generation = 1 if existing is None else existing["generation"] + 1
        consent = state.validate_consent({"schemaVersion": 1, "generation": generation, "policy": policy})
        _write(root, _consent_path(root), consent)
    return {**semantic_fields(), "consent": consent, "policyDigest": state.digest(consent)}


def _load(root, execution_id):
    return state.validate_record(_read(execution_path(root, execution_id)))


def _projection(revision, *, allow_controller=False):
    replay = state.replay_execution_v3 if any(
        isinstance(event, dict) and event.get("schemaVersion") == 3 for event in revision["events"]
    ) or any(
        isinstance(item, dict) and item.get("schemaVersion") == 2 for item in revision["acceptances"].values()
    ) else state.replay_execution_v2 if allow_controller or any(
        isinstance(event, dict) and event.get("schemaVersion") == 2 for event in revision["events"]
    ) else state.replay_execution
    return replay(
        revision["plan"], revision["events"], revision["receipts"],
        state.digest(revision["consent"]), revision["acceptances"], revision["approvals"],
    )


def _record_ids(root):
    _, directory = _directory(root)
    identifiers = []
    if not directory.exists():
        return identifiers
    for path in directory.iterdir():
        _safe(root, path)
        if path.name.startswith("execution-") and path.suffix == ".tmp":
            continue
        if path.suffix != ".json":
            raise ContractIssue("E_EXECUTION_STORAGE", "/", "unexpected entry in execution storage")
        identifiers.append(contracts._id(path.stem, "/executionId"))
        if len(identifiers) > contracts.MAX_ITEMS:
            raise ContractIssue("E_EXECUTION_LIMIT", "/", "project execution-record capacity exceeded")
    return sorted(identifiers)


def _unresolved(projected):
    return any(item["status"] in ("running", "blocked", "reported")
               for item in projected["tasks"].values())


def _project_attempt_available(root, execution_id, task_id=None, attempt_id=None, native=False, bounded=False,
                               batch=None):
    import execution_controls
    execution_controls.enforce_start(root, execution_id, task_id, attempt_id, native, bounded, batch=batch)
    for identifier in _record_ids(root):
        if identifier != execution_id and _unresolved(_projection(_load(root, identifier)["revisions"][-1])):
            raise ContractIssue("E_EXECUTION_CONFLICT", "/executionId",
                                "resolve the other execution's unfinished manual work before starting")


def inspect_execution(project_root, execution_id):
    root = _root(project_root)
    record = _load(root, execution_id)
    revision = record["revisions"][-1]
    consent = _consent(root)
    policy_digest = state.digest(consent) if consent is not None else None
    projected = _projection(revision)
    projected["approved"] = bool(
        projected["approved"] and policy_digest == projected["policyDigest"]
        and consent is not None and consent["policy"]["enabled"]
    )
    return {
        **semantic_fields(), "record": record, "plan": revision["plan"],
        "planDigest": state.digest(revision["plan"]), "policyDigest": policy_digest,
        "recordedPolicyDigest": state.digest(revision["consent"]),
        "events": revision["events"], "receipts": revision["receipts"],
        "acceptances": revision["acceptances"], "approvals": revision["approvals"],
        "state": projected, "writerLockPresent": lock_path(root).exists(),
        "mode": "manual",
    }

def _check_live_binding(root, execution_id, revision, expected):
    expected = contracts._object(expected, "/expectedBinding", (
        "executionId", "planRevision", "planDigest", "policyDigest", "controlsDigest", "controlsStateDigest",
    ))
    contracts._id(expected["executionId"], "/expectedBinding/executionId")
    contracts._number(expected["planRevision"], "/expectedBinding/planRevision")
    contracts._digest(expected["planDigest"], "/expectedBinding/planDigest")
    contracts._digest(expected["policyDigest"], "/expectedBinding/policyDigest")
    if expected["controlsDigest"] is not None:
        contracts._digest(expected["controlsDigest"], "/expectedBinding/controlsDigest")
    for field in ("executionId", "planRevision"):
        if expected[field] != (execution_id if field == "executionId" else revision["plan"]["revision"]):
            raise ContractIssue("E_EXECUTION_STALE_VIEW", "/expectedBinding/" + field,
                                "live manager view is stale")
    current_plan = state.digest(revision["plan"])
    current_policy = state.digest(_consent(root, enabled=True))
    import execution_controls
    store = execution_controls._read(root)
    current_controls = None if store is None else execution_controls._digest(store)
    current_control_state = None if store is None else state.digest(store)
    if expected["planDigest"] != current_plan or expected["policyDigest"] != current_policy or (
        expected["controlsDigest"] != current_controls
        or expected["controlsStateDigest"] != current_control_state
    ):
        raise ContractIssue("E_EXECUTION_STALE_VIEW", "/expectedBinding",
                            "live manager view is stale")


def _append(revision, kind, task_id=None, attempt_id=None, payload=None):
    import execution_orchestration
    execution_orchestration.check_event_capacity(revision, kind, task_id, attempt_id, payload)
    sequence = len(revision["events"]) + 1
    when = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if revision["events"] and when < revision["events"][-1]["recordedAt"]:
        raise ContractIssue("E_EXECUTION_TIME", "/", "local clock precedes the last recorded event")
    event_id = "event-" + str(sequence)
    actor = (
        {"role": "user", "id": "operator"}
        if kind in ("PLAN_APPROVED", "VALIDATION_PASSED", "VALIDATION_FAILED", "TASK_CANCELLED")
        else {"role": "manager", "id": "local-manager"}
    )
    plan = revision["plan"]
    revision["events"].append({
        "schemaVersion": 1, "eventId": event_id,
        "binding": {"executionId": plan["executionId"], "planRevision": plan["revision"],
                    "planDigest": state.digest(plan)},
        "sequence": sequence, "occurredAt": when, "recordedAt": when, "actor": actor,
        "type": kind, "taskId": task_id, "attemptId": attempt_id,
        "payload": {} if payload is None else payload,
    })
    return event_id


def _append_controller(record, revision, kind, task_id, attempt_id, payload, *, version=2):
    import execution_orchestration
    execution_orchestration.check_event_capacity(revision, kind, task_id, attempt_id, payload)
    record["schemaVersion"] = max(record["schemaVersion"], version)
    sequence = len(revision["events"]) + 1
    when = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if revision["events"] and when < revision["events"][-1]["recordedAt"]:
        raise ContractIssue("E_EXECUTION_TIME", "/", "local clock precedes the last recorded event")
    plan = revision["plan"]
    event_id = "event-" + str(sequence)
    revision["events"].append({
        "schemaVersion": version, "eventId": event_id,
        "binding": {"executionId": plan["executionId"], "planRevision": plan["revision"],
                    "planDigest": state.digest(plan)},
        "sequence": sequence, "occurredAt": when, "recordedAt": when,
        "actor": {"role": "manager", "id": "local-orchestrator"},
        "type": kind, "taskId": task_id, "attemptId": attempt_id, "payload": payload,
    })
    return event_id


def _persist(root, record):
    validated = state.validate_record(record)
    _write(root, execution_path(root, record["executionId"]), validated)


def import_plan(project_root, plan):
    plan = contracts.validate_execution_plan(plan)["data"]
    root = _root(project_root)
    _consent(root, enabled=True)
    with _writer(root):
        consent = _consent(root, enabled=True)
        path = execution_path(root, plan["executionId"])
        identifiers = _record_ids(root)
        if not path.exists() and len(identifiers) >= contracts.MAX_ITEMS:
            raise ContractIssue("E_EXECUTION_LIMIT", "/", "project execution-record capacity exceeded")
        record = _load(root, plan["executionId"]) if path.exists() else {
            "schemaVersion": 1, "executionId": plan["executionId"], "revisions": [],
        }
        previous = record["revisions"][-1] if record["revisions"] else None
        if previous is not None:
            if plan == previous["plan"] and consent == previous["consent"]:
                return {**semantic_fields(), "idempotent": True}
            if plan["revision"] <= previous["plan"]["revision"]:
                raise ContractIssue("E_EXECUTION_REVISION", "/revision", "import requires a newer immutable revision")
            if _unresolved(_projection(previous)):
                raise ContractIssue("E_EXECUTION_TRANSITION", "/revision", "resolve unfinished attempts before revision")
        revision = {"plan": plan, "consent": consent, "events": [], "receipts": {},
                    "acceptances": {}, "approvals": {}}
        _append(revision, "PLAN_PROPOSED" if previous is None else "PLAN_UPDATED",
                payload={} if previous is None else {"previousRevision": previous["plan"]["revision"]})
        record["revisions"].append(revision)
        _persist(root, record)
    return {**semantic_fields(), "executionId": plan["executionId"], "revision": plan["revision"]}


@contextmanager
def _transaction(project_root, execution_id, require_binding=True):
    root = _root(project_root)
    _consent(root, enabled=True)
    with _writer(root):
        consent = _consent(root, enabled=True)
        record = _load(root, execution_id)
        revision = record["revisions"][-1]
        if require_binding and consent != revision["consent"]:
            raise ContractIssue("E_EXECUTION_APPROVAL", "/", "policy changed; import a newer plan revision and approve it")
        original = contracts._encoded(record)
        yield root, record, revision
        if contracts._encoded(record) != original:
            _persist(root, record)


def approve_plan(project_root, execution_id, plan_digest, policy_digest, *, expected_binding=None):
    contracts._digest(plan_digest, "/planDigest")
    contracts._digest(policy_digest, "/policyDigest")
    with _transaction(project_root, execution_id) as (root, _, revision):
        if expected_binding is not None:
            _check_live_binding(root, execution_id, revision, expected_binding)
        decision = {"planDigest": state.digest(revision["plan"]),
                    "policyDigest": state.digest(revision["consent"])}
        if decision != {"planDigest": plan_digest, "policyDigest": policy_digest}:
            raise ContractIssue("E_EXECUTION_APPROVAL", "/", "explicit approval digests are stale")
        event_id = "event-" + str(len(revision["events"]) + 1)
        _append(revision, "PLAN_APPROVED", payload={"decisionId": event_id})
        revision["approvals"][event_id] = decision
    return semantic_fields()


def _ownership(root, plan, task_id):
    planned = next((item for item in plan["tasks"] if item["id"] == task_id), None)
    if planned is None:
        raise ContractIssue("E_EXECUTION_REFERENCE", "/taskId", "unknown planned task")
    reserved = {"con", "prn", "aux", "nul", *("com" + str(n) for n in range(1, 10)),
                *("lpt" + str(n) for n in range(1, 10))}
    for claim in planned["ownership"]:
        for component in claim.split("/"):
            if component.endswith((".", " ")) or component.split(".")[0].casefold() in reserved:
                raise ContractIssue("E_EXECUTION_PATH", "/ownership", "nonportable filesystem ownership alias")
        target = _safe(root, root.joinpath(*claim.split("/")))
        if target.is_dir():
            raise ContractIssue("E_EXECUTION_PATH", "/ownership", "ownership must name exact files, not directories")


def record_task(project_root, execution_id, task_id, action, attempt_id=None, reason=None):
    contracts._id(task_id, "/taskId")
    choices = {"ready": "TASK_READY", "start": "TASK_STARTED", "block": "TASK_BLOCKED",
               "unblock": "TASK_UNBLOCKED", "progress": "TASK_PROGRESS_UPDATED",
               "fail": "TASK_FAILED", "cancel": "TASK_CANCELLED", "reject": "VALIDATION_FAILED"}
    contracts._enum(action, "/action", tuple(choices))
    kind = choices[action]
    _, has_attempt, fields = contracts.EVENT_FIELDS[kind]
    if has_attempt:
        contracts._id(attempt_id, "/attemptId")
    elif attempt_id is not None:
        raise ContractIssue("E_EXECUTION_REFERENCE", "/attemptId", "operation does not accept an attempt argument")
    payload = {}
    for field in fields:
        if field != "acceptanceCriteria":
            payload[field] = contracts._text(reason, "/reason")
    with _transaction(project_root, execution_id, require_binding=action != "cancel") as (root, _, revision):
        if action == "start":
            _project_attempt_available(root, execution_id, task_id, attempt_id)
            _ownership(root, revision["plan"], task_id)
        if action in ("cancel", "fail", "reject"):
            import execution_controls
            execution_controls.enforce_terminal(root, execution_id, task_id, action)
        if action == "reject":
            planned = next((item for item in revision["plan"]["tasks"] if item["id"] == task_id), None)
            if planned is None:
                raise ContractIssue("E_EXECUTION_REFERENCE", "/taskId", "unknown planned task")
            payload["acceptanceCriteria"] = planned["acceptanceCriteria"]
        _append(revision, kind, task_id, attempt_id if has_attempt else None, payload)
    return semantic_fields()


def receive_result(project_root, execution_id, result_id, brief, result):
    contracts._id(result_id, "/resultId")
    with _transaction(project_root, execution_id) as (root, record, revision):
        validated_brief = contracts.validate_task_brief(brief, revision["plan"])["data"]
        validated_result = contracts.validate_task_result(result, revision["plan"], validated_brief)["data"]
        receipt = {"brief": validated_brief, "result": validated_result}
        existing = revision["receipts"].get(result_id)
        if existing is not None:
            if existing != receipt:
                raise ContractIssue("E_EXECUTION_DUPLICATE", "/resultId", "receipt identity has conflicting content")
            return {**semantic_fields(), "idempotent": True}
        if any(result_id in old["receipts"] for old in record["revisions"][:-1]):
            raise ContractIssue("E_EXECUTION_DUPLICATE", "/resultId", "receipt identity belongs to an earlier revision")
        import execution_controls
        execution_controls.enforce_terminal(root, execution_id, validated_result["taskId"], "manual-receipt")
        revision["receipts"][result_id] = receipt
        _append(revision, "TASK_RESULT_RECEIVED", validated_result["taskId"], validated_result["attemptId"],
                {"resultId": result_id})
    return semantic_fields()


def accept_task(project_root, execution_id, acceptance, *, expected_binding=None):
    acceptance = state.validate_acceptance(acceptance)
    with _transaction(project_root, execution_id) as (root, record, revision):
        if expected_binding is not None:
            _check_live_binding(root, execution_id, revision, expected_binding)
        import execution_controls
        execution_controls.enforce_terminal(root, execution_id, acceptance["taskId"], "accept")
        if acceptance["schemaVersion"] == 2:
            # Older readers must refuse independent-validation acceptances instead of misreading them.
            record["schemaVersion"] = max(record["schemaVersion"], 3)
        event_id = _append(revision, "VALIDATION_PASSED", acceptance["taskId"], acceptance["attemptId"],
                           {"acceptanceCriteria": acceptance["acceptanceCriteria"]})
        revision["acceptances"][event_id] = acceptance
    return semantic_fields()


def delete_execution(project_root, execution_id):
    path = execution_path(project_root, execution_id)
    with _writer(project_root) as root:
        _safe(root, path)
        if not path.is_file():
            raise ContractIssue("E_EXECUTION_READ", "/", "selected execution record does not exist")
        record = _load(root, execution_id)
        import execution_controls
        execution_controls.enforce_deletion(root, record)
        if _unresolved(_projection(record["revisions"][-1])):
            raise ContractIssue("E_EXECUTION_TRANSITION", "/", "resolve unfinished manual work before deletion")
        path.unlink()
    return {**semantic_fields(), "deleted": execution_id}
