#!/usr/bin/env python3
"""Synchronize bundle versions and reject unversioned content commits."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import qualify


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ".claude-plugin/plugin.json"
MARKETPLACE = ".claude-plugin/marketplace.json"
SKILL = "skills/sdlc/SKILL.md"
MANIFEST = "qualification/manifest.json"
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
SKILL_VERSION = re.compile(r'^  version: "([^"]+)"$', re.MULTILINE)


def parse_version(value: object) -> tuple[int, int, int]:
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise ValueError(f"Expected a stable major.minor.patch version, got {value!r}")
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "--no-pager", *arguments], cwd=root,
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if result.returncode:
        raise ValueError(f"Git failed ({arguments[0]}): {result.stderr.strip()}")
    return result.stdout.strip()


def committed_version(root: Path, revision: str) -> tuple[int, int, int]:
    return parse_version(json.loads(git(root, "show", f"{revision}:{PLUGIN}"))["version"])


def check_history(root: Path, base: str, head: str) -> int:
    base = git(root, "rev-parse", "--verify", base + "^{commit}")
    head = git(root, "rev-parse", "--verify", head + "^{commit}")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base, head], cwd=root, check=False,
    )
    if ancestor.returncode:
        raise ValueError("Version-check base must be an ancestor of head")
    commits = git(root, "rev-list", "--reverse", f"{base}..{head}").splitlines()
    for commit in commits:
        parents = git(root, "rev-list", "--parents", "-n", "1", commit).split()[1:]
        current = committed_version(root, commit)
        previous = [committed_version(root, parent) for parent in parents]
        tree = git(root, "rev-parse", commit + "^{tree}")
        unchanged = any(tree == git(root, "rev-parse", parent + "^{tree}") for parent in parents)
        if previous and (current < max(previous) or
                         (not unchanged and current <= max(previous))):
            raise ValueError(
                f"{commit[:12]}: bundle version must advance for every content-changing "
                "commit (including documentation). Run python scripts/version.py bump."
            )
    return len(commits)


def bump(root: Path, part: str) -> str:
    paths = {name: root / name for name in (PLUGIN, MARKETPLACE, SKILL, MANIFEST)}
    original = {name: path.read_bytes() for name, path in paths.items()}
    plugin = qualify.load_json_strict(paths[PLUGIN])
    marketplace = qualify.load_json_strict(paths[MARKETPLACE])
    manifest = qualify.load_json_strict(paths[MANIFEST])
    skill = original[SKILL].decode("utf-8")
    match = SKILL_VERSION.search(skill)
    if not match:
        raise ValueError("Core skill metadata version is missing")
    version = plugin["version"]
    major, minor, patch = parse_version(version)
    if (marketplace["plugins"][0]["version"] != version or match.group(1) != version
            or manifest["release"] != version or manifest["skill"]["version"] != version):
        raise ValueError("Bundle version metadata disagrees; repair it before bumping")
    next_version = f"{major}.{minor + 1}.0" if part == "minor" else f"{major}.{minor}.{patch + 1}"
    plugin["version"] = next_version
    marketplace["plugins"][0]["version"] = next_version
    manifest["release"] = manifest["skill"]["version"] = next_version
    contents = {
        PLUGIN: (json.dumps(plugin, indent=2) + "\n").encode("utf-8"),
        MARKETPLACE: (json.dumps(marketplace, indent=2) + "\n").encode("utf-8"),
        SKILL: SKILL_VERSION.sub(f'  version: "{next_version}"', skill).encode("utf-8"),
    }
    complete = False
    try:
        for name, content in contents.items():
            paths[name].write_bytes(content)
        files, digest = qualify.inventory_bundle(root / "skills" / "sdlc")
        manifest["skill"]["files"] = files
        manifest["skill"]["bundleSha256"] = digest
        manifest["implementations"] = qualify.discover_implementations(root / "skills" / "sdlc")
        qualify.validate_manifest(manifest, root)
        paths[MANIFEST].write_bytes((json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
        complete = True
    finally:
        if not complete:
            for name, content in original.items():
                paths[name].write_bytes(content)
    return next_version


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    update = commands.add_parser("bump")
    update.add_argument("--part", choices=("patch", "minor"), default="patch")
    check = commands.add_parser("check")
    check.add_argument("--base", default="HEAD^")
    check.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    try:
        if args.command == "bump":
            print(f"Bundle version: {bump(args.root, args.part)}; review and stage the updated files.")
        else:
            print(f"Version policy passed for {check_history(args.root, args.base, args.head)} commits.")
    except (ValueError, KeyError, IndexError, OSError) as error:
        print(f"Version policy failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
