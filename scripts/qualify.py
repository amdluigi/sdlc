#!/usr/bin/env python3
"""Offline qualification tooling for the SDLC bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import unicodedata
import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = ROOT / "qualification" / "manifest.json"
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
MODEL_RE = re.compile(r"^(?:general|reasoning|lightweight)$")
VERSION_RE = re.compile(
    r"^v?[0-9]+(?:\.[0-9]+){1,3}"
    r"(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?"
    r"(?:\+[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$"
)
SECRET_TERM_RE = re.compile(
    r"(?:password|passwd|secret|token|credential|api[\s_-]*key)", re.I
)
PROFILES = {"copilot-vscode", "claude-code", "generic-agent-skills"}
SCOPES = {"project", "global"}
MODES = {"copy", "link"}
SUPPORT = {"required", "unsupported"}
DETERMINISTIC_CASES = {
    "manifest-contract",
    "bundle-inventory",
    "discoverable-skill-count",
    "module-count",
    "config-template",
    "helper-scripts",
    "trigger-discovery-metadata",
    "copy-byte-identity",
    "link-target-identity",
    "project-global-isolation",
    "installer-idempotence",
    "legacy-install-conflict",
    "path-confinement",
    "installer-no-network",
    "shell-contract",
}
LIVE_CASES = {
    "qualification-standard-change-trigger",
    "qualification-non-code-counterexample",
    "qualification-lazy-module-loading",
    "qualification-invalid-installation",
    "qualification-disabled-disclosure",
    "qualification-review-fallback",
    "measurement-consent-refusal",
    "measurement-private-aggregate-boundary",
    "measurement-timing-unavailable",
    "provider-successful-specialization",
    "provider-unavailable-blocks",
    "provider-ambiguous-blocks",
    "provider-incompatible-blocks",
    "provider-core-authority-pressure",
    "provider-satisfied-without-loading",
    "provider-unsupported-success-claim",
    "provider-partial-evidence",
    "provider-unsupported-host-enumeration",
    "provider-disabled-and-no-automatic-selection",
}
PROFILE_CONTRACT = {
    "copilot-vscode": {
        "label": "GitHub Copilot / VS Code",
        "projectRoot": ".github/skills",
        "globalRoot": ".copilot/skills",
        "requiredCells": {
            ("project", "copy"),
            ("project", "link"),
            ("global", "copy"),
            ("global", "link"),
        },
    },
    "claude-code": {
        "label": "Claude Code",
        "projectRoot": ".claude/skills",
        "globalRoot": ".claude/skills",
        "requiredCells": {
            ("project", "copy"),
            ("project", "link"),
            ("global", "copy"),
            ("global", "link"),
        },
    },
    "generic-agent-skills": {
        "label": "Generic Agent Skills client",
        "projectRoot": ".agents/skills",
        "globalRoot": None,
        "requiredCells": {
            ("project", "copy"),
            ("project", "link"),
        },
    },
}
SUITE_ONLY_CASES = {
    "project-global-isolation",
    "installer-idempotence",
    "legacy-install-conflict",
    "path-confinement",
    "installer-no-network",
    "shell-contract",
}
HELPERS = {
    "scripts/adaptive_extensions.py",
    "scripts/artifact_contracts.py",
    "scripts/config_contract.py",
    "scripts/delivery_profile.py",
    "scripts/handoff_renderers.py",
    "scripts/manage_extensions.py",
    "scripts/manage_metrics.py",
    "scripts/operator_reports.py",
    "scripts/reconcile_artifacts.py",
    "scripts/resolve_providers.py",
    "scripts/validate_artifacts.py",
}
BUNDLE_FILE_COUNT = 62
DETERMINISTIC_EVIDENCE = {
    "manifest-valid",
    "file-count",
    "hashes-match",
    "skill-count",
    "module-count",
    "config-valid",
    "helpers-match",
    "metadata-valid",
    "copy-identical",
    "link-target-identical",
    "roots-isolated",
    "idempotent",
    "legacy-conflict-blocked",
    "paths-confined",
    "network-unused",
    "shell-valid",
}
LIVE_EVIDENCE = {
    "triggered",
    "critical-expectations-present",
    "forbidden-observed",
}
TRANSIENT_NAMES = {"__pycache__", ".DS_Store"}
MAX_FILE_COUNT = 256
MAX_FILE_SIZE = 2 * 1024 * 1024
MAX_TOTAL_SIZE = 16 * 1024 * 1024
MAX_JSON_SIZE = 4 * 1024 * 1024
MAX_JSON_DEPTH = 16
MAX_JSON_NODES = 10000
MAX_RESULT_COUNT = 128


def fail(message: str) -> None:
    raise ValueError(message)


def _object_no_duplicates(pairs):
    value = {}
    for key, child in pairs:
        if key in value:
            fail(f"Duplicate JSON key: {key}")
        value[key] = child
    return value


def load_json_strict(path: Path) -> object:
    try:
        if Path(path).stat().st_size > MAX_JSON_SIZE:
            fail(f"JSON input exceeds size limit: {path}")
        text = Path(path).read_text(encoding="utf-8")
    except (UnicodeError, OSError) as error:
        fail(f"Cannot read strict JSON {path}: {error}")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_no_duplicates,
            parse_constant=lambda value: fail(f"Invalid JSON constant: {value}"),
        )
        _validate_json_shape(value)
        return value
    except (json.JSONDecodeError, RecursionError) as error:
        fail(f"Invalid JSON in {path}: {error}")


def _validate_json_shape(value: object) -> None:
    stack = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if depth > MAX_JSON_DEPTH or nodes > MAX_JSON_NODES:
            fail("JSON input exceeds structural limits")
        if isinstance(current, dict):
            stack.extend((child, depth + 1) for child in current.values())
        elif isinstance(current, list):
            stack.extend((child, depth + 1) for child in current)


def _fields(value: object, required: set[str], context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{context} must be an object")
    actual = set(value)
    missing = required - actual
    extra = actual - required
    if missing or extra:
        fail(f"{context} fields invalid; missing={sorted(missing)}, unknown={sorted(extra)}")
    return value


def _is_bool(value: object) -> bool:
    return type(value) is bool


def _text(value: object, context: str, limit: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        fail(f"{context} must be a non-empty string of at most {limit} characters")
    if unicodedata.normalize("NFC", value) != value or any(
        ord(character) < 32 or ord(character) == 127 for character in value
    ):
        fail(f"{context} must be normalized printable text")
    return value


def _id(value: object, context: str) -> str:
    text = _text(value, context, 64)
    if not ID_RE.fullmatch(text):
        fail(f"{context} must be a kebab-case ID")
    return text


def _safe_relative(value: object, context: str) -> str:
    text = _text(value, context, 256)
    if "\\" in text or "://" in text or PureWindowsPath(text).drive:
        fail(f"{context} must be a safe relative POSIX path")
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        fail(f"{context} must be a safe relative POSIX path")
    if str(path) != text:
        fail(f"{context} must be canonical")
    return text


def is_directory_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def _is_reparse(path: Path) -> bool:
    try:
        return bool(
            getattr(path.lstat(), "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        )
    except OSError:
        return False


def _reject_source_links(bundle: Path) -> None:
    if is_directory_link(bundle):
        fail(f"Bundle root must not be a link: {bundle}")
    for base, directories, files in os.walk(bundle, followlinks=False):
        base_path = Path(base)
        for name in directories + files:
            candidate = base_path / name
            if is_directory_link(candidate) or candidate.is_symlink():
                fail(f"Bundle contains a link: {candidate}")


def inventory_bundle(bundle: Path) -> tuple[list[dict[str, str]], str]:
    bundle = Path(bundle)
    if not bundle.is_dir():
        fail(f"Bundle directory not found: {bundle}")
    _reject_source_links(bundle)
    rows: list[dict[str, str]] = []
    total = 0
    for path in sorted(bundle.rglob("*"), key=lambda item: item.relative_to(bundle).as_posix()):
        relative = path.relative_to(bundle)
        if any(part in TRANSIENT_NAMES or part.endswith((".pyc", ".pyo")) for part in relative.parts):
            fail(f"Transient file in bundle: {relative.as_posix()}")
        if path.is_dir():
            continue
        if not path.is_file() or path.is_symlink():
            fail(f"Non-regular bundle entry: {relative.as_posix()}")
        size = path.stat().st_size
        if size > MAX_FILE_SIZE:
            fail(f"Bundle file exceeds size limit: {relative.as_posix()}")
        total += size
        if total > MAX_TOTAL_SIZE:
            fail("Bundle exceeds total size limit")
        rows.append(
            {
                "path": _safe_relative(relative.as_posix(), "bundle file"),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
        if len(rows) > MAX_FILE_COUNT:
            fail("Bundle exceeds file-count limit")
    payload = "".join(f"{row['path']}\0{row['sha256']}\n" for row in rows).encode("utf-8")
    return rows, hashlib.sha256(payload).hexdigest()


def validate_manifest(value: object, root: Path) -> dict[str, object]:
    manifest = _fields(
        value,
        {"schemaVersion", "kind", "release", "skill", "profiles",
         "deterministicCases", "liveCases", "gate"},
        "manifest",
    )
    if manifest["schemaVersion"] != 1 or manifest["kind"] != "sdlc-qualification-manifest":
        fail("Unsupported qualification manifest identity")
    release = _text(manifest["release"], "manifest release", 32)
    if release != "1.0.0":
        fail("Release 1.0 manifest must identify version 1.0.0")
    skill = _fields(
        manifest["skill"],
        {"id", "version", "source", "discoverableSkillCount", "moduleCount",
         "configTemplate", "helperScripts", "files", "bundleSha256"},
        "manifest skill",
    )
    if skill["id"] != "sdlc" or skill["version"] != release:
        fail("Manifest release and skill version must agree")
    source = _safe_relative(skill["source"], "skill source")
    if type(skill["discoverableSkillCount"]) is not int or skill["discoverableSkillCount"] != 1:
        fail("discoverableSkillCount must be 1")
    if type(skill["moduleCount"]) is not int or skill["moduleCount"] != 22:
        fail("moduleCount must be 22")
    _safe_relative(skill["configTemplate"], "config template")
    if (
        not isinstance(skill["helperScripts"], list)
        or skill["helperScripts"] != sorted(HELPERS)
    ):
        fail("Manifest helper scripts do not match the required helper set")
    if len(skill["helperScripts"]) != len(HELPERS):
        fail("Manifest helper scripts must be unique")
    for helper in skill["helperScripts"]:
        _safe_relative(helper, "helper script")
    files = skill["files"]
    if not isinstance(files, list) or len(files) != BUNDLE_FILE_COUNT:
        fail(
            "Release 1.0 manifest must contain exactly "
            f"{BUNDLE_FILE_COUNT} bundle files"
        )
    seen: set[str] = set()
    previous = ""
    for index, row in enumerate(files):
        item = _fields(row, {"path", "sha256"}, f"manifest file {index}")
        path = _safe_relative(item["path"], f"manifest file {index} path")
        if path in seen or (previous and path <= previous):
            fail("Manifest files must be unique and sorted by path")
        if not isinstance(item["sha256"], str) or not HASH_RE.fullmatch(item["sha256"]):
            fail(f"Invalid manifest file hash: {path}")
        seen.add(path)
        previous = path
    if not isinstance(skill["bundleSha256"], str) or not HASH_RE.fullmatch(skill["bundleSha256"]):
        fail("Invalid bundleSha256")
    profiles = manifest["profiles"]
    if not isinstance(profiles, list) or len(profiles) != 3:
        fail("Manifest must contain exactly three profiles")
    profile_ids: set[str] = set()
    for profile_index, profile_value in enumerate(profiles):
        profile = _fields(
            profile_value,
            {"id", "label", "projectRoot", "globalRoot", "required", "cells"},
            f"profile {profile_index}",
        )
        profile_id = _id(profile["id"], "profile ID")
        profile_ids.add(profile_id)
        label = _text(profile["label"], "profile label", 96)
        project_root = _safe_relative(profile["projectRoot"], "project skills root")
        global_root = profile["globalRoot"]
        if profile["globalRoot"] is not None:
            global_root = _safe_relative(profile["globalRoot"], "global skills root")
        contract = PROFILE_CONTRACT.get(profile_id)
        if contract is None or (
            label,
            project_root,
            global_root,
        ) != (
            contract["label"],
            contract["projectRoot"],
            contract["globalRoot"],
        ):
            fail(f"Profile {profile_id} identity and roots do not match the manifest")
        if not _is_bool(profile["required"]) or not profile["required"]:
            fail("Every qualification profile must be required")
        cells = profile["cells"]
        if not isinstance(cells, list) or len(cells) != 4:
            fail(f"Profile {profile_id} must declare all four installation cells")
        pairs = set()
        for cell_index, cell_value in enumerate(cells):
            if not isinstance(cell_value, dict):
                fail("Installation cell must be an object")
            expected = {"scope", "mode", "support"}
            support = cell_value.get("support")
            if support == "unsupported":
                expected.add("reason")
            cell = _fields(cell_value, expected, f"profile {profile_id} cell {cell_index}")
            if cell["scope"] not in SCOPES or cell["mode"] not in MODES or support not in SUPPORT:
                fail(f"Invalid installation cell for {profile_id}")
            pair = (cell["scope"], cell["mode"])
            if pair in pairs:
                fail(f"Duplicate installation cell for {profile_id}")
            pairs.add(pair)
            if support == "unsupported":
                _text(cell["reason"], "unsupported reason", 160)
            expected_support = (
                "required" if pair in contract["requiredCells"] else "unsupported"
            )
            if support != expected_support:
                fail(f"Profile {profile_id} support matrix is fixed")
        if pairs != {(scope, mode) for scope in SCOPES for mode in MODES}:
            fail(f"Incomplete installation matrix for {profile_id}")
    if profile_ids != PROFILES:
        fail("Qualification manifest has the wrong profile IDs")
    _validate_cases(manifest["deterministicCases"], DETERMINISTIC_CASES, "deterministic", False)
    _validate_cases(manifest["liveCases"], LIVE_CASES, "live", True)
    gate = _fields(
        manifest["gate"],
        {
            "requireEverySupportedCell",
            "requireEveryProfileLive",
            "failOnCriticalNotPassed",
            "liveBaseline",
            "requireSupportedLiveLink",
        },
        "gate policy",
    )
    if not all(
        _is_bool(gate[key]) and gate[key]
        for key in (
            "requireEverySupportedCell",
            "requireEveryProfileLive",
            "failOnCriticalNotPassed",
            "requireSupportedLiveLink",
        )
    ):
        fail("Qualification gate requirements cannot be weakened")
    baseline = _fields(gate["liveBaseline"], {"scope", "mode"}, "live baseline")
    if baseline != {"scope": "project", "mode": "copy"}:
        fail("Release 1.0 live baseline must be project copy")
    source_path = Path(root) / Path(*PurePosixPath(source).parts)
    actual_files, actual_digest = inventory_bundle(source_path)
    if actual_files != files or actual_digest != skill["bundleSha256"]:
        fail("Manifest bundle inventory does not match the source bundle")
    return manifest


def _validate_cases(value: object, required: set[str], context: str, repetitions: bool) -> None:
    if not isinstance(value, list) or len(value) != len(required):
        fail(f"Manifest must declare every required {context} case")
    ids = set()
    for index, case_value in enumerate(value):
        fields = {"id", "critical"} | ({"repetitions"} if repetitions else set())
        case = _fields(case_value, fields, f"{context} case {index}")
        ids.add(_id(case["id"], f"{context} case ID"))
        if not _is_bool(case["critical"]) or not case["critical"]:
            fail(f"Required {context} cases must be critical")
        if repetitions and (type(case["repetitions"]) is not int or case["repetitions"] != 5):
            fail("Live qualification cases require exactly five repetitions")
    if ids != required or len(ids) != len(value):
        fail(f"Manifest {context} case IDs do not match repository contracts")


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _reject_linked_ancestors(path: Path, root: Path) -> None:
    if _is_reparse(root) and not is_directory_link(root):
        fail(f"Supplied root is an unknown reparse point: {root}")
    if is_directory_link(root):
        fail(f"Supplied root must not be a link: {root}")
    current = root
    relative = path.relative_to(root)
    for part in relative.parts[:-1]:
        current = current / part
        if _is_reparse(current) and not is_directory_link(current):
            fail(f"Destination ancestor is an unknown reparse point: {current}")
        if current.exists() and is_directory_link(current):
            fail(f"Destination ancestor is a link: {current}")


def resolve_destination(
    profile: dict[str, object],
    scope: str,
    project_root: Path | None,
    home_root: Path | None,
    override: Path | None = None,
) -> Path:
    if scope not in SCOPES:
        fail(f"Invalid scope: {scope}")
    root = Path(project_root) if scope == "project" and project_root else None
    if scope == "global":
        root = Path(home_root) if home_root else None
    if root is None:
        fail(f"{scope} scope requires an explicit {'project' if scope == 'project' else 'home'} root")
    root = root.absolute()
    if scope == "global" and profile.get("globalRoot") is None:
        fail(f"Profile {profile['id']} does not support global installation")
    skills_root = (
        Path(override).absolute()
        if override is not None
        else root / str(profile["projectRoot" if scope == "project" else "globalRoot"])
    )
    if not _within(skills_root, root):
        fail("Destination override must remain beneath the supplied root")
    destination = skills_root / "sdlc"
    _reject_linked_ancestors(destination, root)
    return destination


def _remove_link(path: Path) -> None:
    if path.is_symlink():
        path.unlink()
    elif getattr(path, "is_junction", lambda: False)():
        path.rmdir()
    else:
        fail(f"Refusing to remove unknown reparse point: {path}")


def _rename_with_retry(
    source: Path,
    destination: Path,
    *,
    rename=None,
    sleep=time.sleep,
    windows: bool | None = None,
) -> None:
    rename = rename or source.rename
    windows = os.name == "nt" if windows is None else windows
    for attempt in range(5):
        try:
            rename(destination)
            return
        except PermissionError:
            if not windows or attempt == 4:
                raise
            sleep(0.05 * (attempt + 1))


def install_bundle(source: Path, destination: Path, mode: str) -> None:
    if mode not in MODES:
        fail(f"Invalid installation mode: {mode}")
    source = Path(source).resolve()
    destination = Path(destination).absolute()
    inventory_bundle(source)
    if _within(destination, source) or _within(source, destination):
        fail("Source and destination must not overlap")
    legacy = destination.parent / "project-memory"
    if legacy.exists() or legacy.is_symlink():
        fail("Legacy standalone project-memory install blocks installation")
    if destination.exists() and not destination.is_dir() and not is_directory_link(destination):
        fail("Destination must be absent, a directory, or a directory link")
    if _is_reparse(destination) and not is_directory_link(destination):
        fail("Destination is an unknown reparse point")
    destination.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    staging = destination.parent / f".sdlc-staging-{token}"
    backup = destination.parent / f".sdlc-backup-{token}"
    replaced = False
    promoted = False
    try:
        if mode == "copy":
            shutil.copytree(source, staging, symlinks=False)
            if inventory_bundle(staging) != inventory_bundle(source):
                fail("Staged copy does not match source")
        else:
            try:
                os.symlink(source, staging, target_is_directory=True)
            except OSError:
                if os.name != "nt":
                    raise
                completed = subprocess.run(
                    ["cmd.exe", "/d", "/c", "mklink", "/J", str(staging), str(source)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if completed.returncode != 0:
                    raise OSError(completed.stderr or completed.stdout)
        if destination.exists() or destination.is_symlink() or is_directory_link(destination):
            _rename_with_retry(destination, backup)
            replaced = True
        _rename_with_retry(staging, destination)
        promoted = True
        if mode == "copy" and inventory_bundle(destination) != inventory_bundle(source):
            fail("Installed copy does not match source")
        if mode == "link" and destination.resolve() != source:
            fail("Installed link does not target the canonical source")
        if replaced:
            _remove_link(backup) if is_directory_link(backup) else shutil.rmtree(backup)
    except Exception:
        if staging.exists() or staging.is_symlink():
            _remove_link(staging) if is_directory_link(staging) else shutil.rmtree(staging)
        if promoted and (
            destination.exists() or destination.is_symlink()
            or is_directory_link(destination)
        ):
            _remove_link(destination) if is_directory_link(destination) else shutil.rmtree(destination)
        if replaced and (backup.exists() or is_directory_link(backup)):
            _rename_with_retry(backup, destination)
        raise


def _read_frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        fail("SKILL.md frontmatter is missing")
    result = {}
    parent = ""
    for line in lines[1:]:
        if line == "---":
            break
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            parent = key.strip() if not value.strip() else ""
            result[key.strip()] = value.strip().strip("'\"")
        elif parent and ":" in line:
            key, value = line.strip().split(":", 1)
            result[f"{parent}.{key}"] = value.strip().strip("'\"")
    return result


def deterministic_result(
    manifest: dict[str, object],
    profile_id: str,
    scope: str,
    mode: str,
    *,
    installation_status: str = "not-executed",
    performed: dict[str, list[dict[str, object]]] | None = None,
) -> dict[str, object]:
    performed = performed or {}
    unknown = set(performed) - DETERMINISTIC_CASES
    if unknown:
        fail(f"Unknown performed deterministic checks: {sorted(unknown)}")
    for case_id, evidence in performed.items():
        if case_id in SUITE_ONLY_CASES:
            fail("Suite-only checks cannot be emitted by per-cell result production")
        if (
            case_id == "copy-byte-identity"
            and mode != "copy"
            or case_id == "link-target-identity"
            and mode != "link"
        ):
            fail(f"Deterministic check {case_id} was not performed for mode {mode}")
        if evidence != _deterministic_evidence(case_id):
            fail(f"Deterministic check {case_id} does not have passing evidence")
    return {
        "schemaVersion": 1,
        "kind": "sdlc-qualification-summary",
        "release": manifest["release"],
        "resultType": "deterministic-installation",
        "profile": profile_id,
        "clientVersion": "not-applicable",
        "modelClass": "not-applicable",
        "skillVersion": manifest["skill"]["version"],
        "bundleSha256": f"sha256:{manifest['skill']['bundleSha256']}",
        "installation": {
            "scope": scope,
            "mode": mode,
            "status": installation_status,
        },
        "cases": [
            {
                "id": case["id"],
                "critical": case["critical"],
                "status": "pass" if case["id"] in performed else "not-executed",
                "evidence": performed.get(case["id"], []),
            }
            for case in manifest["deterministicCases"]
        ],
    }


def _deterministic_evidence(case_id: str) -> list[dict[str, object]]:
    mapping = {
        "manifest-contract": [{"code": "manifest-valid", "value": True}],
        "bundle-inventory": [
            {"code": "file-count", "value": BUNDLE_FILE_COUNT},
            {"code": "hashes-match", "value": True},
        ],
        "discoverable-skill-count": [{"code": "skill-count", "value": 1}],
        "module-count": [{"code": "module-count", "value": 22}],
        "config-template": [{"code": "config-valid", "value": True}],
        "helper-scripts": [{"code": "helpers-match", "value": True}],
        "trigger-discovery-metadata": [{"code": "metadata-valid", "value": True}],
        "copy-byte-identity": [{"code": "copy-identical", "value": True}],
        "link-target-identity": [{"code": "link-target-identical", "value": True}],
        "project-global-isolation": [{"code": "roots-isolated", "value": True}],
        "installer-idempotence": [{"code": "idempotent", "value": True}],
        "legacy-install-conflict": [{"code": "legacy-conflict-blocked", "value": True}],
        "path-confinement": [{"code": "paths-confined", "value": True}],
        "installer-no-network": [{"code": "network-unused", "value": True}],
        "shell-contract": [{"code": "shell-valid", "value": True}],
    }
    return mapping[case_id]


def inspect_install(
    manifest: dict[str, object],
    destination: Path,
    profile_id: str,
    scope: str,
    mode: str,
) -> dict[str, object]:
    destination = Path(destination)
    validate_manifest(manifest, ROOT)
    performed = {
        "manifest-contract": _deterministic_evidence("manifest-contract"),
    }
    if mode == "link":
        if not is_directory_link(destination):
            fail("Expected one directory link")
        target = destination.resolve()
        expected = (ROOT / str(manifest["skill"]["source"])).resolve()
        if target != expected:
            fail("Installed link does not target the canonical bundle")
        performed["link-target-identity"] = _deterministic_evidence(
            "link-target-identity"
        )
    else:
        if is_directory_link(destination) or not destination.is_dir():
            fail("Expected a copied directory")
    files, digest = inventory_bundle(destination.resolve() if mode == "link" else destination)
    if files != manifest["skill"]["files"] or digest != manifest["skill"]["bundleSha256"]:
        fail("Installed bundle bytes do not match the manifest")
    performed["bundle-inventory"] = [
        {"code": "file-count", "value": len(files)},
        {"code": "hashes-match", "value": True},
    ]
    if mode == "copy":
        performed["copy-byte-identity"] = _deterministic_evidence(
            "copy-byte-identity"
        )
    skill_files = [
        child / "SKILL.md"
        for child in destination.parent.iterdir()
        if not child.name.startswith(".sdlc-") and (child / "SKILL.md").is_file()
    ]
    if len(skill_files) != 1:
        fail("Installed skills root must expose exactly one discoverable skill")
    performed["discoverable-skill-count"] = [
        {"code": "skill-count", "value": len(skill_files)}
    ]
    registry = load_json_strict(destination / "modules" / "registry.json")
    config = load_json_strict(destination / str(manifest["skill"]["configTemplate"]))
    module_names = {item["name"] for item in registry["modules"]}
    module_dirs = {path.name for path in (destination / "modules").iterdir() if path.is_dir()}
    if (
        len(registry["modules"]) != manifest["skill"]["moduleCount"]
        or module_dirs != module_names
    ):
        fail("Installed module registry and filesystem do not match")
    performed["module-count"] = [
        {"code": "module-count", "value": len(registry["modules"])}
    ]
    if set(config) != {
        "schemaVersion",
        "modules",
        "extensions",
        "measurement",
    }:
        fail("Installed config template fields are invalid")
    if config.get("schemaVersion") != 3 or set(config.get("modules", {})) != module_names:
        fail("Installed config template does not match the module registry")
    if not all(value is True for value in config["modules"].values()):
        fail("Installed config template must enable every module")
    if config.get("extensions") != {"project": {}, "global": {}}:
        fail("Installed config template extension maps must be empty")
    if config.get("measurement") != {"enabled": False}:
        fail("Installed config template measurement must be disabled")
    performed["config-template"] = _deterministic_evidence("config-template")
    frontmatter = _read_frontmatter(destination / "SKILL.md")
    if (
        frontmatter.get("name") != "sdlc"
        or not frontmatter.get("description", "").startswith("Use when")
        or frontmatter.get("metadata.version") != manifest["skill"]["version"]
    ):
        fail("Installed discovery metadata does not match the manifest")
    performed["trigger-discovery-metadata"] = _deterministic_evidence(
        "trigger-discovery-metadata"
    )
    for helper in manifest["skill"]["helperScripts"]:
        if not (destination / helper).is_file():
            fail(f"Installed helper missing: {helper}")
    performed["helper-scripts"] = _deterministic_evidence("helper-scripts")
    return deterministic_result(
        manifest,
        profile_id,
        scope,
        mode,
        installation_status="pass",
        performed=performed,
    )


def _safe_retained_string(value: object, context: str, *, identifier=False) -> str:
    text = _text(value, context, 64)
    if identifier and not ID_RE.fullmatch(text):
        fail(f"{context} must be kebab-case")
    lowered = text.lower()
    if (
        "://" in text
        or "\\" in text
        or text.startswith(("/", "~"))
        or SECRET_TERM_RE.search(text)
        or any(marker in lowered for marker in ("users/", "users\\", "home/", "repository"))
    ):
        fail(f"{context} contains forbidden retained content")
    return text


def validate_result(value: object, manifest: dict[str, object]) -> dict[str, object]:
    result = _fields(
        value,
        {"schemaVersion", "kind", "release", "resultType", "profile", "clientVersion",
         "modelClass", "skillVersion", "bundleSha256", "installation", "cases"},
        "qualification result",
    )
    if result["schemaVersion"] != 1 or result["kind"] != "sdlc-qualification-summary":
        fail("Unsupported qualification result identity")
    if result["release"] != manifest["release"] or result["skillVersion"] != manifest["skill"]["version"]:
        fail("Qualification result release/version is stale")
    if result["bundleSha256"] != f"sha256:{manifest['skill']['bundleSha256']}":
        fail("Qualification result bundle digest is stale")
    if result["resultType"] not in {"deterministic-installation", "live-host"}:
        fail("Invalid qualification result type")
    if result["profile"] not in PROFILES:
        fail("Invalid result profile")
    client = _safe_retained_string(result["clientVersion"], "clientVersion")
    model = _safe_retained_string(result["modelClass"], "modelClass")
    if result["resultType"] == "deterministic-installation":
        if client != "not-applicable" or model != "not-applicable":
            fail("Deterministic results use not-applicable client and model")
        expected_cases = DETERMINISTIC_CASES
        evidence_codes = DETERMINISTIC_EVIDENCE
    else:
        if not VERSION_RE.fullmatch(client) or not MODEL_RE.fullmatch(model):
            fail("Live result clientVersion or modelClass is not sanitized")
        expected_cases = LIVE_CASES
        evidence_codes = LIVE_EVIDENCE
    installation = _fields(result["installation"], {"scope", "mode", "status"}, "installation")
    if installation["scope"] not in SCOPES or installation["mode"] not in MODES:
        fail("Invalid result installation cell")
    if installation["status"] not in {"pass", "fail", "not-executed", "unsupported"}:
        fail("Invalid installation status")
    profile = next(
        profile for profile in manifest["profiles"] if profile["id"] == result["profile"]
    )
    cell = next(
        cell
        for cell in profile["cells"]
        if cell["scope"] == installation["scope"] and cell["mode"] == installation["mode"]
    )
    if cell["support"] != "required":
        fail("Qualification result uses a manifest-unsupported installation cell")
    cases = result["cases"]
    if not isinstance(cases, list) or len(cases) != len(expected_cases):
        fail("Qualification result must contain every required case exactly once")
    seen = set()
    for index, case_value in enumerate(cases):
        fields = {"id", "critical", "status", "evidence"}
        if result["resultType"] == "live-host":
            fields.add("repetitions")
        case = _fields(case_value, fields, f"result case {index}")
        case_id = _id(case["id"], "result case ID")
        if case_id not in expected_cases or case_id in seen:
            fail("Unknown or duplicate result case")
        seen.add(case_id)
        if not _is_bool(case["critical"]) or not case["critical"]:
            fail("Required result cases must remain critical")
        if case["status"] not in {"pass", "fail", "not-executed"}:
            fail("Invalid result case status")
        if result["resultType"] == "live-host":
            required = next(item["repetitions"] for item in manifest["liveCases"] if item["id"] == case_id)
            if type(case["repetitions"]) is not int or not (0 <= case["repetitions"] <= required):
                fail("Invalid live repetition count")
        evidence = case["evidence"]
        if not isinstance(evidence, list) or len(evidence) > 8:
            fail("Result evidence must be a small array")
        if not evidence and case["status"] != "not-executed":
            fail("Executed result cases require evidence")
        if evidence and case["status"] == "not-executed":
            fail("Unexecuted result cases cannot retain evidence")
        codes = set()
        for evidence_index, evidence_value in enumerate(evidence):
            item = _fields(evidence_value, {"code", "value"}, f"evidence {evidence_index}")
            if item["code"] not in evidence_codes or item["code"] in codes:
                fail("Unknown or duplicate evidence code")
            codes.add(item["code"])
            if type(item["value"]) not in {bool, int} or (
                type(item["value"]) is int and not 0 <= item["value"] <= 10000
            ):
                fail("Evidence values must be bounded booleans or counters")
        if result["resultType"] == "deterministic-installation":
            supported_pass = evidence == _deterministic_evidence(case_id)
            if case["status"] == "pass" and not supported_pass:
                fail("Deterministic case evidence does not support its verdict")
            if case["status"] == "pass" and case_id in SUITE_ONLY_CASES:
                fail("Suite-only checks require separate verifiable suite evidence")
            if (
                case["status"] == "pass"
                and case_id == "copy-byte-identity"
                and installation["mode"] != "copy"
            ):
                fail("Copy identity was not performed for this installation mode")
            if (
                case["status"] == "pass"
                and case_id == "link-target-identity"
                and installation["mode"] != "link"
            ):
                fail("Link identity was not performed for this installation mode")
            if case["status"] == "fail" and supported_pass:
                fail("Deterministic failure conflicts with passing evidence")
        else:
            values = {item["code"]: item["value"] for item in evidence}
            if codes != LIVE_EVIDENCE:
                fail("Live case evidence is incomplete")
            supported_pass = (
                values["triggered"] is True
                and values["critical-expectations-present"] == case["repetitions"]
                and values["forbidden-observed"] is False
            )
            if (case["status"] == "pass") != supported_pass:
                fail("Live case status conflicts with normalized evidence")
    return result


def sanitize_live_result(raw: object, manifest: dict[str, object]) -> dict[str, object]:
    allowed = {
        "profile", "clientVersion", "modelClass", "installation", "cases", "rawResponse"
    }
    if not isinstance(raw, dict) or not set(raw) <= allowed or not allowed - {"rawResponse"} <= set(raw):
        fail("Raw live result fields are invalid")
    installation = _fields(raw["installation"], {"scope", "mode", "status"}, "raw installation")
    if not isinstance(raw["cases"], list) or len(raw["cases"]) != len(LIVE_CASES):
        fail("Raw live result must contain every required case")
    manifest_cases = {case["id"]: case for case in manifest["liveCases"]}
    cases = []
    for index, value in enumerate(raw["cases"]):
        case = _fields(
            value,
            {"id", "repetitions", "passes", "triggered", "forbiddenObserved"},
            f"raw case {index}",
        )
        case_id = _id(case["id"], "raw case ID")
        if case_id not in manifest_cases:
            fail("Unknown raw live case ID")
        required = manifest_cases[case_id]["repetitions"]
        if any(type(case[key]) is not int for key in ("repetitions", "passes")):
            fail("Raw live repetition values must be integers")
        if not _is_bool(case["triggered"]) or not _is_bool(case["forbiddenObserved"]):
            fail("Raw live verdicts must be booleans")
        passed = (
            case["repetitions"] == required
            and case["passes"] == required
            and case["triggered"]
            and not case["forbiddenObserved"]
        )
        cases.append(
            {
                "id": case_id,
                "critical": True,
                "status": "pass" if passed else "fail",
                "repetitions": case["repetitions"],
                "evidence": [
                    {"code": "triggered", "value": case["triggered"]},
                    {"code": "critical-expectations-present", "value": case["passes"]},
                    {"code": "forbidden-observed", "value": case["forbiddenObserved"]},
                ],
            }
        )
    result = {
        "schemaVersion": 1,
        "kind": "sdlc-qualification-summary",
        "release": manifest["release"],
        "resultType": "live-host",
        "profile": raw["profile"],
        "clientVersion": raw["clientVersion"],
        "modelClass": raw["modelClass"],
        "skillVersion": manifest["skill"]["version"],
        "bundleSha256": f"sha256:{manifest['skill']['bundleSha256']}",
        "installation": dict(installation),
        "cases": cases,
    }
    return validate_result(result, manifest)


def evaluate_gate(
    manifest: dict[str, object],
    results: list[dict[str, object]],
    source_root: Path,
) -> dict[str, object]:
    blockers: list[str] = []
    if len(results) > MAX_RESULT_COUNT:
        return {
            "schemaVersion": 1,
            "kind": "sdlc-qualification-gate",
            "release": manifest["release"],
            "pass": False,
            "blockers": ["qualification result count exceeds limit"],
            "counts": {
                "requiredDeterministicCells": 0,
                "validatedResults": 0,
                "liveProfiles": 0,
            },
        }
    try:
        validate_manifest(manifest, source_root)
    except ValueError as error:
        blockers.append(f"source/manifest: {error}")
    validated = []
    for index, result in enumerate(results):
        try:
            validated.append(validate_result(result, manifest))
        except ValueError as error:
            blockers.append(f"result {index}: {error}")
    expected_cells = {
        (profile["id"], cell["scope"], cell["mode"])
        for profile in manifest["profiles"]
        for cell in profile["cells"]
        if cell["support"] == "required"
    }
    observed_cells: dict[tuple[str, str, str], int] = {}
    result_keys: set[tuple[str, str, str, str]] = set()
    live_profiles = set()
    live_baselines = set()
    live_supported_link = False
    suite_passes: set[str] = set()
    baseline = (
        manifest["gate"]["liveBaseline"]["scope"],
        manifest["gate"]["liveBaseline"]["mode"],
    )
    for result in validated:
        key = (
            result["profile"],
            result["installation"]["scope"],
            result["installation"]["mode"],
        )
        result_key = (result["resultType"], *key)
        if result_key in result_keys:
            blockers.append(f"duplicate qualification result: {result_key}")
        result_keys.add(result_key)
        if result["resultType"] == "deterministic-installation":
            observed_cells[key] = observed_cells.get(key, 0) + 1
            if key not in expected_cells:
                blockers.append(f"unsupported deterministic installation result: {key}")
        else:
            live_profiles.add(result["profile"])
            if key not in expected_cells:
                blockers.append(f"unsupported live-host installation result: {key}")
            if key[1:] == baseline:
                live_baselines.add(result["profile"])
            live_supported_link = (
                live_supported_link
                or key in expected_cells
                and result["installation"]["mode"] == "link"
            )
        if result["installation"]["status"] != "pass":
            blockers.append(f"installation not passed: {key}")
        for case in result["cases"]:
            if (
                result["resultType"] == "deterministic-installation"
                and case["id"] in SUITE_ONLY_CASES
            ):
                if case["status"] == "pass":
                    suite_passes.add(case["id"])
                continue
            relevant_mode_case = (
                result["resultType"] == "deterministic-installation"
                and (
                    case["id"] == "copy-byte-identity"
                    and result["installation"]["mode"] != "copy"
                    or case["id"] == "link-target-identity"
                    and result["installation"]["mode"] != "link"
                )
            )
            if case["critical"] and case["status"] != "pass" and not relevant_mode_case:
                blockers.append(f"critical case not passed: {result['profile']}/{case['id']}")
            if result["resultType"] == "live-host":
                required = next(item["repetitions"] for item in manifest["liveCases"] if item["id"] == case["id"])
                if case["repetitions"] != required:
                    blockers.append(f"live repetitions incomplete: {result['profile']}/{case['id']}")
    for cell in sorted(expected_cells):
        count = observed_cells.get(cell, 0)
        if count != 1:
            blockers.append(f"deterministic installation cell requires exactly one result: {cell}")
    for profile in sorted(PROFILES - live_profiles):
        blockers.append(f"required profile has no live-host result: {profile}")
    for profile in sorted(PROFILES - live_baselines):
        blockers.append(f"required profile has no project-copy live baseline: {profile}")
    if live_profiles and not live_supported_link:
        blockers.append("at least one supported live-host link result is required")
    for case_id in sorted(SUITE_ONLY_CASES - suite_passes):
        blockers.append(f"deterministic suite evidence is missing: {case_id}")
    _check_release_versions(manifest, Path(source_root), blockers)
    return {
        "schemaVersion": 1,
        "kind": "sdlc-qualification-gate",
        "release": manifest["release"],
        "pass": not blockers,
        "blockers": blockers,
        "counts": {
            "requiredDeterministicCells": len(expected_cells),
            "validatedResults": len(validated),
            "liveProfiles": len(live_profiles),
        },
    }


def _check_release_versions(
    manifest: dict[str, object], root: Path, blockers: list[str]
) -> None:
    try:
        skill = _read_frontmatter(root / "skills" / "sdlc" / "SKILL.md")
        plugin = load_json_strict(root / ".claude-plugin" / "plugin.json")
        marketplace = load_json_strict(root / ".claude-plugin" / "marketplace.json")
        plugins = marketplace.get("plugins")
        marketplace_version = (
            plugins[0].get("version")
            if isinstance(plugins, list) and len(plugins) == 1
            else None
        )
        versions = {
            skill.get("metadata.version"),
            plugin.get("version"),
            marketplace_version,
            manifest["release"],
        }
        if versions != {manifest["release"]}:
            blockers.append("skill, plugin, marketplace, and manifest versions disagree")
    except (OSError, ValueError) as error:
        blockers.append(f"release version metadata: {error}")


def _write_json_atomic(path: Path, value: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.{uuid.uuid4().hex}.staging")
    try:
        staging.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(staging, path)
    finally:
        if staging.exists():
            staging.unlink()


def _manifest(path: Path) -> dict[str, object]:
    return validate_manifest(load_json_strict(path), ROOT)


def _profile(manifest: dict[str, object], profile_id: str) -> dict[str, object]:
    for profile in manifest["profiles"]:
        if profile["id"] == profile_id:
            return profile
    fail(f"Unknown profile: {profile_id}")


def _emit(value: object, output: Path | None = None) -> None:
    if output:
        _write_json_atomic(output, value)
    print(json.dumps(value, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify-manifest")
    verify.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    refresh = sub.add_parser("refresh-manifest")
    refresh.add_argument("--bundle", type=Path, required=True)
    refresh.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    inventory = sub.add_parser("inventory")
    inventory.add_argument("--bundle", type=Path, required=True)
    for name in ("install", "check-install"):
        command = sub.add_parser(name)
        command.add_argument("--profile", required=True)
        command.add_argument("--scope", choices=sorted(SCOPES), required=True)
        command.add_argument("--mode", choices=sorted(MODES), required=True)
        command.add_argument("--project-root", type=Path)
        command.add_argument("--home-root", type=Path)
        command.add_argument("--destination-root", type=Path)
        command.add_argument("--output", type=Path)
        if name == "install":
            command.add_argument("--dry-run", action="store_true")
    sanitize = sub.add_parser("sanitize-live")
    sanitize.add_argument("--input", type=Path, required=True)
    sanitize.add_argument("--output", type=Path, required=True)
    result = sub.add_parser("validate-result")
    result.add_argument("paths", nargs="+", type=Path)
    gate = sub.add_parser("gate")
    gate.add_argument("--release", required=True)
    gate.add_argument("--results", type=Path)
    gate.add_argument("--source-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        if args.command == "verify-manifest":
            manifest = _manifest(args.manifest)
            _emit({"pass": True, "release": manifest["release"], "bundleSha256": manifest["skill"]["bundleSha256"]})
        elif args.command == "refresh-manifest":
            value = load_json_strict(args.manifest)
            files, digest = inventory_bundle(args.bundle)
            value["skill"]["files"] = files
            value["skill"]["bundleSha256"] = digest
            validate_manifest(value, ROOT)
            _write_json_atomic(args.manifest, value)
            _emit({"pass": True, "files": len(files), "bundleSha256": digest})
        elif args.command == "inventory":
            files, digest = inventory_bundle(args.bundle)
            _emit({"files": files, "bundleSha256": digest})
        elif args.command in {"install", "check-install"}:
            manifest = _manifest(DEFAULT_MANIFEST)
            profile = _profile(manifest, args.profile)
            destination = resolve_destination(
                profile, args.scope, args.project_root, args.home_root, args.destination_root
            )
            cell = next(c for c in profile["cells"] if c["scope"] == args.scope and c["mode"] == args.mode)
            if cell["support"] != "required":
                fail(f"Installation cell is unsupported: {cell['reason']}")
            if args.command == "install" and not args.dry_run:
                source = ROOT / str(manifest["skill"]["source"])
                install_bundle(source, destination, args.mode)
            value = (
                {
                    "profile": args.profile,
                    "scope": args.scope,
                    "mode": args.mode,
                    "status": "dry-run",
                    "destinationClass": f"{args.scope}-skills-root",
                }
                if args.command == "install" and args.dry_run
                else inspect_install(manifest, destination, args.profile, args.scope, args.mode)
            )
            _emit(value, args.output)
        elif args.command == "sanitize-live":
            manifest = _manifest(DEFAULT_MANIFEST)
            value = sanitize_live_result(load_json_strict(args.input), manifest)
            _write_json_atomic(args.output, value)
            print("Raw input remains local; delete it after human review.", file=sys.stderr)
            _emit(value)
        elif args.command == "validate-result":
            manifest = _manifest(DEFAULT_MANIFEST)
            for path in args.paths:
                validate_result(load_json_strict(path), manifest)
            _emit({"pass": True, "results": len(args.paths)})
        elif args.command == "gate":
            manifest = _manifest(DEFAULT_MANIFEST)
            if args.release != manifest["release"]:
                fail("Requested release does not match manifest")
            results_dir = args.results or ROOT / "qualification" / "results" / args.release
            paths = sorted(Path(results_dir).glob("*.json")) if Path(results_dir).exists() else []
            if len(paths) > MAX_RESULT_COUNT:
                fail("Qualification result count exceeds limit")
            results = [load_json_strict(path) for path in paths]
            value = evaluate_gate(manifest, results, args.source_root)
            _emit(value)
            return 0 if value["pass"] else 1
        return 0
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1 if args.command == "check-install" else 2


if __name__ == "__main__":
    raise SystemExit(main())
