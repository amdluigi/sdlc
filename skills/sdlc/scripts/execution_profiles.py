"""Explicit project-only profile installation; no execution or policy activation."""

import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

from artifact_contracts import ContractIssue, semantic_fields
import execution_contracts as contracts
import execution_manager as manager
import execution_state as state
from validate_artifacts import _frontmatter

SOURCE = Path(__file__).resolve().parent.parent / "assets" / "native-profiles"
ROLES = {
    "controller": (["read", "search", "execute"], ["read", "search", "execute", "agent"]),
    "architecture": (["read", "search"], ["read", "search"]),
    "developer": (["read", "search", "edit", "execute"], ["read", "search", "edit", "execute"]),
    "testing": (["read", "search", "execute"], ["read", "search", "execute"]),
    "review": (["read", "search"], ["read", "search"]),
}


def role_info(role):
    contracts._enum(role, "/role", tuple(ROLES))
    path = SOURCE / f"sdlc-{role}.agent.md"
    try:
        manager._safe(SOURCE, path)
        if not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size > 65536:
            raise ContractIssue("E_PROFILE_SOURCE", "/", "profile source must be a bounded regular file")
        content = path.read_bytes()
        metadata, body = _frontmatter(content.decode("utf-8").replace("\r\n", "\n"), "native-profile")
    except (OSError, UnicodeError) as error:
        raise ContractIssue("E_PROFILE_SOURCE", "/", "cannot read the bundled profile") from error
    fields = ("name", "description", "tools", "agents", "user-invocable", "disable-model-invocation")
    contracts._object(metadata, "/profile", fields)
    name = "SDLC " + role.capitalize()
    agents = ["SDLC " + item.capitalize() for item in ROLES if item != "controller"] if role == "controller" else []
    expected = {
        "name": name, "tools": json.dumps(ROLES[role][1]), "agents": json.dumps(agents),
        "user-invocable": "true" if role == "controller" else "false",
        "disable-model-invocation": "true" if role == "controller" else "false",
    }
    if any(metadata[key] != value for key, value in expected.items()) or not body.strip():
        raise ContractIssue("E_PROFILE_SOURCE", "/", "bundled profile does not match its restricted role")
    contracts._text(metadata["description"], "/description")
    data = {"role": role, "name": name, "file": path.name, "allowedActions": list(ROLES[role][0]),
            "tools": list(ROLES[role][1]), "contentDigest": "sha256:" + hashlib.sha256(content).hexdigest()}
    return {**data, "digest": state.digest(data)}


def _snapshot():
    expected = {f"sdlc-{role}.agent.md" for role in ROLES}
    try:
        if {path.name for path in SOURCE.iterdir()} != expected:
            raise ContractIssue("E_PROFILE_SOURCE", "/", "bundled profile inventory is incomplete or unexpected")
        return [role_info(role) for role in ROLES]
    except OSError as error:
        raise ContractIssue("E_PROFILE_SOURCE", "/", "cannot inspect bundled profile inventory") from error


def _paths(project_root):
    root = manager._root(project_root)
    parent = manager._safe(root, root / ".github")
    metadata = manager._safe(root, manager.lock_path(root).parent / "native-profiles.json")
    if not (root / ".git").is_dir():
        relative = metadata.relative_to(root).as_posix()
        if manager.manage_metrics._run_git(root, ["check-ignore", "--no-index", "--quiet", "--", relative]).returncode:
            raise ContractIssue("E_PROFILE_STORAGE", "/", "profile ownership storage is not proven ignored")
    return root, parent / "agents", metadata


def _manifest(value):
    data = contracts._object(value, "/profiles", ("schemaVersion", "hostFormat", "mode", "status", "digest"))
    contracts._version(data)
    contracts._enum(data["hostFormat"], "/hostFormat", ("vscode",))
    contracts._enum(data["mode"], "/mode", ("copy", "link"))
    contracts._enum(data["status"], "/status", ("pending", "installed"))
    contracts._digest(data["digest"], "/digest")
    return data


def _inspect(root, destination, metadata, snapshot):
    if not metadata.exists():
        if destination.exists() or destination.is_symlink():
            raise ContractIssue("E_PROFILE_COLLISION", "/", "existing agents directory is not owned by this installer")
        raise ContractIssue("E_PROFILE_MISSING", "/", "explicit profile installation is required")
    owned = _manifest(manager._read(metadata))
    if owned["status"] != "installed":
        raise ContractIssue("E_PROFILE_PENDING", "/", "interrupted installation requires inspection")
    if owned["digest"] != state.digest(snapshot):
        raise ContractIssue("E_PROFILE_DRIFT", "/", "bundled roles changed; explicit installation review is required")
    try:
        if owned["mode"] == "link":
            if not manager.manage_metrics._is_link_or_reparse(destination) or destination.resolve(strict=True) != SOURCE:
                raise ContractIssue("E_PROFILE_DRIFT", "/", "installed link does not match the exact bundled source")
        else:
            manager._safe(root, destination)
        if not destination.is_dir() or {path.name for path in destination.iterdir()} != {item["file"] for item in snapshot}:
            raise ContractIssue("E_PROFILE_DRIFT", "/", "installed profile inventory changed")
        for item in snapshot:
            path = destination / item["file"]
            manager._safe(SOURCE if owned["mode"] == "link" else root, path.resolve() if owned["mode"] == "link" else path)
            if not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size > 65536:
                raise ContractIssue("E_PROFILE_DRIFT", "/", "installed profile is not a bounded regular file")
            if "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() != item["contentDigest"]:
                raise ContractIssue("E_PROFILE_DRIFT", "/", "installed profile bytes changed")
    except OSError as error:
        raise ContractIssue("E_PROFILE_DRIFT", "/", "cannot verify installed profile identity") from error
    return owned


def inspect_profile(project_root, role):
    snapshot = _snapshot()
    contracts._enum(role, "/role", tuple(ROLES))
    root, destination, metadata = _paths(project_root)
    _inspect(root, destination, metadata, snapshot)
    return next(item for item in snapshot if item["role"] == role)


def role_instructions(project_root, role, expected_digest):
    info = inspect_profile(project_root, role)
    contracts._digest(expected_digest, "/profileDigest")
    if info["digest"] != expected_digest:
        raise ContractIssue("E_PROFILE_DRIFT", "/profileDigest", "selected role profile digest is stale")
    try:
        content = (SOURCE / info["file"]).read_bytes()
        if "sha256:" + hashlib.sha256(content).hexdigest() != info["contentDigest"]:
            raise ContractIssue("E_PROFILE_SOURCE", "/", "profile source changed during instruction loading")
        _, body = _frontmatter(content.decode("utf-8").replace("\r\n", "\n"), "native-profile")
        return body
    except (OSError, UnicodeError) as error:
        raise ContractIssue("E_PROFILE_SOURCE", "/", "cannot read verified profile instructions") from error


def install_profiles(project_root, mode="copy", dry_run=True):
    contracts._enum(mode, "/mode", ("copy", "link"))
    if type(dry_run) is not bool:
        raise ContractIssue("E_SCHEMA_TYPE", "/dryRun", "expected boolean")
    snapshot = _snapshot()
    root, destination, metadata = _paths(project_root)
    if metadata.exists() or destination.exists() or destination.is_symlink():
        owned = _inspect(root, destination, metadata, snapshot)
        if owned["mode"] != mode:
            raise ContractIssue("E_PROFILE_COLLISION", "/", "explicit mode change is not an idempotent installation")
        return {**semantic_fields(), "dryRun": dry_run, "idempotent": True, "profiles": snapshot}
    if dry_run:
        return {**semantic_fields(), "dryRun": True, "idempotent": False, "profiles": snapshot}
    temporary = None
    with manager._writer(root):
        root, destination, metadata = _paths(root)
        if metadata.exists() or destination.exists() or destination.is_symlink():
            raise ContractIssue("E_PROFILE_COLLISION", "/", "installation destination changed")
        manifest = {"schemaVersion": 1, "hostFormat": "vscode", "mode": mode,
                    "status": "pending", "digest": state.digest(snapshot)}
        manager._write(root, metadata, manifest)
        destination.parent.mkdir(parents=True, exist_ok=True)
        manager._safe(root, destination.parent)
        temporary = Path(tempfile.mkdtemp(prefix="native-profiles-", dir=destination.parent))
        try:
            if mode == "copy":
                for item in snapshot:
                    content = (SOURCE / item["file"]).read_bytes()
                    if "sha256:" + hashlib.sha256(content).hexdigest() != item["contentDigest"]:
                        raise ContractIssue("E_PROFILE_SOURCE", "/", "profile source changed during staging")
                    (temporary / item["file"]).write_bytes(content)
            else:
                temporary.rmdir()
                try:
                    temporary.symlink_to(SOURCE, target_is_directory=True)
                except OSError as error:
                    if os.name != "nt":
                        raise ContractIssue("E_PROFILE_LINK", "/", "directory link creation failed") from error
                    # Creation paths are literal; PowerShell resolves junction targets as wildcard expressions.
                    completed = subprocess.run(
                        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
                         "$ErrorActionPreference = 'Stop'; New-Item -ItemType Junction "
                         "-Path $env:SDLC_NATIVE_LINK "
                         "-Target ([System.Management.Automation.WildcardPattern]::Escape($env:SDLC_NATIVE_SOURCE)) "
                         "| Out-Null"],
                        env={**os.environ, "SDLC_NATIVE_LINK": str(temporary), "SDLC_NATIVE_SOURCE": str(SOURCE)},
                        capture_output=True, timeout=5, check=False,
                    )
                    if completed.returncode:
                        raise ContractIssue("E_PROFILE_LINK", "/", "directory junction creation failed") from error
            if destination.exists() or destination.is_symlink():
                raise ContractIssue("E_PROFILE_COLLISION", "/", "installation destination became occupied")
            temporary.rename(destination)
            manifest["status"] = "installed"
            manager._write(root, metadata, manifest)
            _inspect(root, destination, metadata, snapshot)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ContractIssue("E_PROFILE_IO", "/", "profile staging or promotion failed; inspect pending ownership") from error
        finally:
            if temporary is not None and (temporary.exists() or temporary.is_symlink()):
                if manager.manage_metrics._is_link_or_reparse(temporary):
                    if temporary.resolve(strict=True) != SOURCE:
                        raise ContractIssue("E_PROFILE_PATH", "/", "temporary link changed before cleanup")
                    if temporary.is_symlink():
                        temporary.unlink()
                    else:
                        temporary.rmdir()
                else:
                    manager._safe(root, temporary)
                    shutil.rmtree(temporary)
    return {**semantic_fields(), "dryRun": False, "idempotent": False, "profiles": snapshot}
