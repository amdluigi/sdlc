import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "version.py"


class VersioningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sdlc-version-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Version test")
        self.git("config", "user.email", "version@example.invalid")
        self.write_version("1.0.0")
        self.commit("baseline")
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        result = subprocess.run(
            ["git", "-c", "core.hooksPath=" + str(self.root / "no-hooks"), *args],
            cwd=self.root, text=True, capture_output=True, check=True,
        )
        return result.stdout

    def write_version(self, version):
        path = self.root / ".claude-plugin" / "plugin.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"version": version}), encoding="utf-8")

    def commit(self, message):
        self.git("add", ".")
        self.git("commit", "-qm", message)

    def tool(self, *args):
        self.assertTrue(TOOL.is_file(), "Per-commit version enforcement is missing")
        return subprocess.run(
            [sys.executable, "-B", str(TOOL), "--root", str(self.root), *args],
            text=True, capture_output=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

    def test_checks_every_commit_not_only_final_version(self):
        (self.root / "change.txt").write_text("first\n", encoding="utf-8")
        self.commit("forgot version")
        self.write_version("1.0.1")
        self.commit("late version")
        result = self.tool("check", "--base", self.base, "--head", "HEAD")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must advance", result.stderr)

    def test_accepts_advances_and_rejects_regressions_and_invalid_versions(self):
        for version in ["1.0.1", "1.1.0"]:
            self.write_version(version)
            self.commit(version)
        self.assertEqual(self.tool("check", "--base", self.base).returncode, 0)
        for version in ["1.0.9", "01.2.3", "1.2", "1.2.3+build"]:
            with self.subTest(version=version):
                self.write_version(version)
                self.commit("invalid or decreasing version")
                result = self.tool("check", "--base", "HEAD^")
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.git("revert", "--no-edit", "HEAD")

    def test_merge_reuses_tested_parent_tree_but_rejects_unversioned_merge_edits(self):
        self.git("checkout", "-qb", "feature")
        self.write_version("1.0.1")
        self.commit("versioned change")
        feature = self.git("rev-parse", "HEAD").strip()
        self.git("checkout", "-q", "-")
        self.git("merge", "--no-ff", "-qm", "merge tested tree", "feature")
        result = self.tool("check", "--base", self.base)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD^{tree}"),
                         self.git("rev-parse", feature + "^{tree}"))
        (self.root / "merge-only.txt").write_text("untested merge edit", encoding="utf-8")
        self.git("add", ".")
        tree = self.git("write-tree").strip()
        merge = self.git("commit-tree", tree, "-p", self.base, "-p", feature,
                         "-m", "unversioned merge edits").strip()
        result = self.tool("check", "--base", self.base, "--head", merge)
        self.assertNotEqual(result.returncode, 0)

    def test_empty_commit_can_reuse_version_and_nonancestor_base_is_rejected(self):
        self.git("commit", "--allow-empty", "-qm", "empty")
        self.assertEqual(self.tool("check", "--base", self.base).returncode, 0)
        self.git("checkout", "-qb", "other", self.base)
        self.write_version("1.0.2")
        self.commit("other")
        result = self.tool("check", "--base", "HEAD", "--head", "HEAD^")
        self.assertNotEqual(result.returncode, 0)

    def test_bump_synchronizes_metadata_and_refreshes_inventory(self):
        for name in [".claude-plugin", "skills", "qualification"]:
            shutil.copytree(ROOT / name, self.root / name, dirs_exist_ok=True)
        before = json.loads((self.root / "qualification" / "manifest.json").read_text())
        result = self.tool("bump", "--part", "patch")
        self.assertEqual(result.returncode, 0, result.stderr)
        plugin = json.loads((self.root / ".claude-plugin" / "plugin.json").read_text())
        manifest = json.loads((self.root / "qualification" / "manifest.json").read_text())
        old = tuple(map(int, before["release"].split(".")))
        expected = f"{old[0]}.{old[1]}.{old[2] + 1}"
        self.assertEqual(plugin["version"], expected)
        self.assertEqual(manifest["release"], expected)
        self.assertEqual(manifest["skill"]["version"], expected)
        self.assertNotEqual(before["skill"]["bundleSha256"], manifest["skill"]["bundleSha256"])
        self.assertIn(f'  version: "{expected}"',
                      (self.root / "skills" / "sdlc" / "SKILL.md").read_text())
        marketplace = json.loads((self.root / ".claude-plugin" / "marketplace.json").read_text())
        self.assertEqual(marketplace["plugins"][0]["version"], expected)

    def test_bump_restores_metadata_when_inventory_validation_fails(self):
        for name in [".claude-plugin", "skills", "qualification"]:
            shutil.copytree(ROOT / name, self.root / name, dirs_exist_ok=True)
        paths = [self.root / name for name in [
            ".claude-plugin/plugin.json", ".claude-plugin/marketplace.json",
            "skills/sdlc/SKILL.md", "qualification/manifest.json",
        ]]
        before = [path.read_bytes() for path in paths]
        (self.root / "skills" / "sdlc" / "unexpected.txt").write_text("extra", encoding="utf-8")
        result = self.tool("bump")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, [path.read_bytes() for path in paths])


if __name__ == "__main__":
    unittest.main()
