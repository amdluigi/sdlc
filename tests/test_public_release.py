from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY_PATH = ROOT / "scripts" / "verify_public_release.py"
TEST_ROOT = ROOT / ".test-tmp" / "public-release"
PUBLIC_MARKER = b'{"repository":"skills","schemaVersion":1}\n'


def release_manifest(files: dict[str, tuple[str, bytes]]) -> dict:
    entries = [
        {"path": path, "mode": mode, "sha256": hashlib.sha256(data).hexdigest()}
        for path, (mode, data) in sorted(files.items())
    ]
    digest = hashlib.sha256(
        b"".join(
            f"{entry['mode']} {entry['path']}\0{entry['sha256']}\n".encode()
            for entry in entries
        )
    ).hexdigest()
    return {
        "schemaVersion": 1,
        "releaseVersion": 1,
        "files": entries,
        "treeDigest": digest,
    }


class PublicReleaseVerifierTest(unittest.TestCase):
    def setUp(self) -> None:
        TEST_ROOT.mkdir(parents=True, exist_ok=True)
        self.root = TEST_ROOT / uuid.uuid4().hex
        self.root.mkdir()
        self.addCleanup(self._remove_root)
        self.files = {
            "PUBLIC-REPOSITORY.json": ("100644", PUBLIC_MARKER),
            "README.md": ("100644", b"public\n"),
        }
        for name, (_, data) in self.files.items():
            (self.root / name).write_bytes(data)
        (self.root / "RELEASE-MANIFEST.json").write_text(
            json.dumps(release_manifest(self.files), sort_keys=True, indent=2) + "\n"
        )

    def _remove_root(self) -> None:
        if not self.root.exists():
            return

        def make_writable(function, target, _error):
            os.chmod(target, stat.S_IWRITE)
            function(target)

        shutil.rmtree(self.root, onexc=make_writable)

    def verify(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VERIFY_PATH), str(self.root)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_valid_release_passes(self) -> None:
        self.assertEqual(0, self.verify().returncode)

    def test_actions_allocate_a_runner_only_for_public_repositories(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "if: ${{ github.event.repository.private == false }}",
            workflow,
        )

    def test_readme_exposes_three_entry_paths(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        entry_paths = {
            "## Use SDLC": "use-sdlc",
            "## Configure or extend SDLC": "configure-or-extend-sdlc",
            "## Maintain and release SDLC": "maintain-and-release-sdlc",
        }

        self.assertIn("## Choose your path", readme)
        chooser = readme.split("## Choose your path", 1)[1].split("\n## ", 1)[0]
        anchors = {
            "#" + re.sub(r"[^a-z0-9 -]", "", heading.lower()).replace(" ", "-")
            for heading in re.findall(r"^#{1,6} (.+)$", readme, re.MULTILINE)
        }
        for heading, anchor in entry_paths.items():
            self.assertIn(heading, readme)
            self.assertIn(f"](#{anchor})", chooser)

            section = readme.split(heading, 1)[1].split("\n## ", 1)[0]
            local_targets = [
                target
                for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", section)
                if target and "://" not in target
            ]
            self.assertTrue(local_targets, f"{heading} must link to detailed docs")
            for target in local_targets:
                if target.startswith("#"):
                    self.assertIn(target, anchors)
                else:
                    self.assertTrue((ROOT / target.split("#", 1)[0]).exists(), target)

    def test_public_repository_marker_requires_canonical_bytes(self) -> None:
        (self.root / "PUBLIC-REPOSITORY.json").write_text(
            '{\n  "repository": "skills",\n  "schemaVersion": 1\n}\n'
        )
        result = self.verify()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("marker invalid", result.stderr.lower())

    def test_public_repository_marker_makes_release_manifest_mandatory(self) -> None:
        scripts = self.root / "scripts"
        scripts.mkdir()
        shutil.copy2(VERIFY_PATH, scripts / VERIFY_PATH.name)
        (self.root / "RELEASE-MANIFEST.json").unlink()
        spec = importlib.util.spec_from_file_location(
            "repository_validate_public_marker", ROOT / "scripts" / "validate.py"
        )
        validator = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(validator)
        with self.assertRaisesRegex(ValueError, "requires RELEASE-MANIFEST"):
            validator.validate_publication_contracts(self.root)

    def test_private_manifest_cannot_bypass_marked_public_validation(self) -> None:
        scripts = self.root / "scripts"
        scripts.mkdir()
        shutil.copy2(VERIFY_PATH, scripts / VERIFY_PATH.name)
        publication = self.root / "internal" / "publication"
        publication.mkdir(parents=True)
        publication_manifest = {
            "schemaVersion": 1,
            "publicationVersion": 7,
            "sourceRepository": "skills-internal",
            "publicRepository": "skills",
            "sourceVisibility": "private",
            "publicVisibility": "public",
            "public": ["README.md"],
            "private": [".sdlc/**", "internal/**"],
            "textExtensions": [".md"],
        }
        (publication / "manifest.json").write_text(
            json.dumps(publication_manifest)
        )
        (self.root / "RELEASE-MANIFEST.json").unlink()
        spec = importlib.util.spec_from_file_location(
            "repository_validate_adversarial_marker",
            ROOT / "scripts" / "validate.py",
        )
        validator = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(validator)
        with self.assertRaisesRegex(ValueError, "requires RELEASE-MANIFEST"):
            validator.validate_publication_contracts(self.root)

    def test_missing_changed_and_unexpected_files_fail(self) -> None:
        original = (self.root / "README.md").read_bytes()
        for mutation, marker in [
            (lambda: (self.root / "README.md").unlink(), "missing"),
            (lambda: (self.root / "README.md").write_text("changed"), "hash"),
            (lambda: (self.root / "unexpected").write_text("x"), "unexpected"),
        ]:
            with self.subTest(marker=marker):
                mutation()
                result = self.verify()
                self.assertNotEqual(0, result.returncode)
                self.assertIn(marker, result.stderr.lower())
                if (self.root / "unexpected").exists():
                    (self.root / "unexpected").unlink()
                (self.root / "README.md").write_bytes(original)


if __name__ == "__main__":
    unittest.main()
