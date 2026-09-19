import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash")
if not BASH:
    candidate = Path("C:/Program Files/Git/bin/bash.exe")
    BASH = str(candidate) if candidate.exists() else None


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.work = ROOT / ".test-tmp" / "qualification" / self.id().split(".")[-1]
        shutil.rmtree(self.work, ignore_errors=True)
        self.work.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def run_command(self, command):
        return subprocess.run(command, cwd=ROOT, text=True, capture_output=True)

    def test_powershell_legacy_and_profile_json_dry_runs(self):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            self.skipTest("PowerShell unavailable")
        project = self.work / "project"
        project.mkdir()
        legacy = self.run_command([
            shell, "-NoProfile", "-File", "scripts/install.ps1",
            "-TargetProject", str(project), "-ClientDir", ".agents/skills", "-DryRun", "-Json",
        ])
        self.assertEqual(0, legacy.returncode, legacy.stderr)
        value = json.loads(legacy.stdout)
        self.assertEqual(("generic-agent-skills", "project", "copy"),
                         (value["profile"], value["scope"], value["mode"]))
        named = self.run_command([
            shell, "-NoProfile", "-File", "scripts/install.ps1",
            "-Profile", "copilot-vscode", "-Scope", "global", "-Mode", "link",
            "-HomeRoot", str(self.work / "home"), "-DryRun", "-Json",
        ])
        self.assertEqual(0, named.returncode, named.stderr)
        value = json.loads(named.stdout)
        self.assertEqual(("copilot-vscode", "global", "link"),
                         (value["profile"], value["scope"], value["mode"]))

    def test_powershell_rejects_conflicting_old_and_new_arguments(self):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            self.skipTest("PowerShell unavailable")
        project = self.work / "project"
        project.mkdir()
        result = self.run_command([
            shell, "-NoProfile", "-File", "scripts/install.ps1",
            "-TargetProject", str(project), "-Profile", "copilot-vscode",
            "-ClientDir", ".agents/skills", "-DryRun",
        ])
        self.assertNotEqual(0, result.returncode)
        self.assertIn("cannot be combined", result.stderr.lower())

    def test_bash_legacy_and_profile_json_dry_runs(self):
        bash = BASH
        if not bash:
            self.skipTest("Bash unavailable")
        project = self.work / "project"
        project.mkdir()
        legacy = self.run_command([
            bash, "scripts/install.sh", str(project), "--client-dir", ".agents/skills",
            "--dry-run", "--json",
        ])
        self.assertEqual(0, legacy.returncode, legacy.stderr)
        self.assertEqual("generic-agent-skills", json.loads(legacy.stdout)["profile"])
        named = self.run_command([
            bash, "scripts/install.sh", "--profile", "claude-code", "--scope", "global",
            "--mode", "copy", "--home-root", str(self.work / "home"), "--dry-run", "--json",
        ])
        self.assertEqual(0, named.returncode, named.stderr)
        self.assertEqual("global", json.loads(named.stdout)["scope"])

    def test_bash_rejects_mode_alias_conflict(self):
        bash = BASH
        if not bash:
            self.skipTest("Bash unavailable")
        project = self.work / "project"
        project.mkdir()
        result = self.run_command([
            bash, "scripts/install.sh", str(project), "--link", "--mode", "copy",
            "--dry-run",
        ])
        self.assertNotEqual(0, result.returncode)
        self.assertIn("conflict", result.stderr.lower())

    def test_bash_named_generic_profile_honors_destination_override(self):
        bash = BASH
        if not bash:
            self.skipTest("Bash unavailable")
        project = self.work / "project"
        project.mkdir()
        destination_root = project / "custom-skills"
        result = self.run_command([
            bash, "scripts/install.sh", str(project),
            "--profile", "generic-agent-skills", "--scope", "project",
            "--mode", "copy", "--destination-root", str(destination_root), "--json",
        ])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((destination_root / "sdlc" / "SKILL.md").is_file())
        self.assertFalse((project / ".agents" / "skills" / "sdlc").exists())


if __name__ == "__main__":
    unittest.main()
