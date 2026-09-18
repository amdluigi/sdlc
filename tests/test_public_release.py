from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PublicRepositoryAuthorityTest(unittest.TestCase):
    def test_public_repository_is_code_authority(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8").lower()

        self.assertIn("public code authority", readme)
        self.assertIn("pull request", readme)
        self.assertIn("public repository is authoritative", agents)

    def test_public_tree_has_no_private_publication_contract(self) -> None:
        for path in (
            "PUBLIC-REPOSITORY.json",
            "RELEASE-MANIFEST.json",
            "scripts/verify_public_release.py",
            "publish.bat",
            "verify.bat",
            "internal",
            ".sdlc",
        ):
            self.assertFalse((ROOT / path).exists(), path)

    def test_public_docs_do_not_require_private_access(self) -> None:
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                ROOT / "README.md",
                ROOT / "CONTRIBUTING.md",
                ROOT / "AGENTS.md",
            )
        )

        self.assertNotIn(r"C:\dev\skills-internal", text)
        self.assertNotIn("internal/publication", text)
        self.assertNotIn("later public export", text.lower())

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

    def test_actions_validate_public_contributions_without_private_tools(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("pull_request:", workflow)
        self.assertIn("python -m unittest discover -v", workflow)
        self.assertIn("python scripts/validate.py", workflow)
        self.assertNotIn("internal/publication", workflow)
        self.assertNotIn("verify_public_release.py", workflow)


if __name__ == "__main__":
    unittest.main()
