#!/usr/bin/env python3
"""Verify a deterministic public release without private publication tooling."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import re
from pathlib import Path, PurePosixPath


MANIFEST_NAME = "RELEASE-MANIFEST.json"
MARKER_NAME = "PUBLIC-REPOSITORY.json"
EXPECTED_MARKER_BYTES = b'{"repository":"skills","schemaVersion":1}\n'


def fail(message: str) -> None:
    raise ValueError(message)


def _load_manifest(root: Path) -> dict:
    path = root / MANIFEST_NAME
    try:
        def no_duplicates(pairs):
            value = {}
            for key, child in pairs:
                if key in value:
                    fail(f"release manifest duplicate key: {key}")
                value[key] = child
            return value

        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=no_duplicates,
            parse_constant=lambda constant: fail(
                f"release manifest invalid constant: {constant}"
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"release manifest invalid: {error}")
    if not isinstance(value, dict) or set(value) != {
        "schemaVersion",
        "releaseVersion",
        "files",
        "treeDigest",
    }:
        fail("release manifest fields invalid")
    if value["schemaVersion"] != 1 or value["releaseVersion"] != 1:
        fail("release manifest version unsupported")
    if not isinstance(value["files"], list):
        fail("release manifest files must be an array")
    return value


def verify(root: Path | str) -> dict:
    root = Path(root).resolve()
    try:
        marker = (root / MARKER_NAME).read_bytes()
    except OSError as error:
        fail(f"public repository marker invalid: {error}")
    if marker != EXPECTED_MARKER_BYTES:
        fail("public repository marker invalid")
    manifest = _load_manifest(root)
    expected: dict[str, dict] = {}
    for item in manifest["files"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"path", "mode", "sha256"}
            or item["mode"] not in {"100644", "100755"}
            or not isinstance(item["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is None
        ):
            fail("release manifest file entry invalid")
        path = item["path"]
        if (
            not isinstance(path, str)
            or not path
            or "\\" in path
            or path.startswith("/")
            or ".." in PurePosixPath(path).parts
            or path.split("/", 1)[0] == ".git"
            or path.split("/", 1)[0] in {"internal", ".sdlc"}
            or path in expected
        ):
            fail("release manifest path invalid")
        expected[path] = item
    actual: set[str] = set()
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = [name for name in directories if name != ".git"]
        for name in list(directories) + files:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink() or (
                hasattr(path, "is_junction") and path.is_junction()
            ):
                fail(f"symlink or junction prohibited: {relative}")
        actual.update(
            (current_path / name).relative_to(root).as_posix() for name in files
        )
    expected_with_manifest = set(expected) | {MANIFEST_NAME}
    missing = sorted(set(expected) - actual)
    unexpected = sorted(actual - expected_with_manifest)
    if missing:
        fail(f"missing exported file: {missing[0]}")
    if unexpected:
        fail(f"unexpected exported file: {unexpected[0]}")
    for path, item in sorted(expected.items()):
        target = root / Path(*PurePosixPath(path).parts)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != item["sha256"]:
            fail(f"hash mismatch: {path}")
        executable = bool(target.stat().st_mode & stat.S_IXUSR)
        if os.name != "nt" and executable != (item["mode"] == "100755"):
            fail(f"mode mismatch: {path}")
    tree_digest = hashlib.sha256(
        b"".join(
            f"{item['mode']} {path}\0{item['sha256']}\n".encode()
            for path, item in sorted(expected.items())
        )
    ).hexdigest()
    if tree_digest != manifest["treeDigest"]:
        fail("tree digest mismatch")
    return {"schemaVersion": 1, "fileCount": len(expected), "treeDigest": tree_digest}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        print(json.dumps(verify(args.path), sort_keys=True, separators=(",", ":")))
        return 0
    except ValueError as error:
        print(f"E_RELEASE_VERIFY {str(error).replace(chr(10), ' ')}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
