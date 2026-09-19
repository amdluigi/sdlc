import contextlib
import hashlib
import importlib
import io
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True

from tests.test_artifact_contracts import valid_handoff


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "sdlc" / "scripts"
SCRIPT = SCRIPTS / "validate_artifacts.py"
SCRATCH = ROOT / ".test-tmp" / "handoff-renderers"
GOLDEN = ROOT / "tests" / "golden"

sys.path.insert(0, str(SCRIPTS))


class HandoffRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.renderers = importlib.import_module("handoff_renderers")

    def setUp(self):
        shutil.rmtree(SCRATCH, ignore_errors=True)
        SCRATCH.mkdir(parents=True)
        self.handoff = SCRATCH / "handoff.json"
        self.handoff.write_text(json.dumps(valid_handoff()), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(SCRATCH, ignore_errors=True)

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, arguments)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_golden_rendering_for_all_forges(self):
        for forge in ("github", "gitlab", "azure-devops"):
            with self.subTest(forge=forge):
                result = self.run_cli("render-handoff", self.handoff, "--forge", forge)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("", result.stderr)
                self.assertEqual(
                    (GOLDEN / f"handoff-{forge}.md").read_text(encoding="utf-8"),
                    result.stdout,
                )

    def test_every_forge_preserves_all_normalized_fields(self):
        handoff = valid_handoff()
        handoff["review"]["unavailable"] = [
            {"perspective": "security", "reason": "Reviewer was unavailable."}
        ]
        handoff["risks"] = ["Large exports can take longer."]
        handoff["limitations"] = ["Export is limited to current filters."]
        handoff["configuredDisabledModules"] = ["observability"]
        handoff["blockers"] = ["Manual product check remains."]
        self.handoff.write_text(json.dumps(handoff), encoding="utf-8")

        expected = [
            "search-export", "2", "FR-1", "FR-2", "AC-1", "AC-2",
            "passed", "correctness", "tests", "Handled empty result sets.",
            "security", "Reviewer was unavailable.",
            "No public or persisted contract changed.",
            "Deploy with the ordinary application release.",
            "Revert the change and redeploy.", "Large exports can take longer.",
            "Export is limited to current filters.",
            "Scheduled exports remain out of scope.",
            "Manual product check remains.", "observability",
        ]
        for forge in ("github", "gitlab", "azure-devops"):
            with self.subTest(forge=forge):
                result = self.run_cli("render-handoff", self.handoff, "--forge", forge)
                self.assertEqual(0, result.returncode, result.stderr)
                for value in expected:
                    self.assertIn(value, result.stdout)

    def test_failed_evidence_is_emphasized_and_repeated_as_a_blocker(self):
        handoff = valid_handoff()
        handoff["acceptanceEvidence"][1]["result"] = "unavailable"
        handoff["configuredDisabledModules"] = ["review"]
        self.handoff.write_text(json.dumps(handoff), encoding="utf-8")

        result = self.run_cli("render-handoff", self.handoff, "--forge", "github")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("**`unavailable`**", result.stdout)
        self.assertIn("**`AC-2` evidence unavailable:**", result.stdout)
        self.assertIn("`review`", result.stdout)

    def test_markdown_and_table_values_are_escaped(self):
        handoff = valid_handoff()
        handoff["title"] = "Add *safe* export"
        handoff["acceptanceEvidence"][0]["kind"] = "test|contract"
        handoff["acceptanceEvidence"][0]["command"] = "tool first | tool second"
        handoff["acceptanceEvidence"][0]["summary"] = "Matched | safely."
        self.handoff.write_text(json.dumps(handoff), encoding="utf-8")

        result = self.run_cli("render-handoff", self.handoff, "--forge", "github")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("# Add \\*safe\\* export", result.stdout)
        self.assertIn("test\\|contract", result.stdout)
        self.assertIn("`tool first \\| tool second`", result.stdout)
        self.assertIn("Matched \\| safely.", result.stdout)

    def test_template_without_marker_is_normalized_and_appended(self):
        template = SCRATCH / "template.md"
        template.write_bytes("Header\r\n{{ untouched }}".encode("utf-8"))

        result = self.run_cli(
            "render-handoff", self.handoff, "--forge", "gitlab",
            "--template", template,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(result.stdout.startswith("Header\n{{ untouched }}\n\n# Add"))
        self.assertNotIn("\r", result.stdout)

    def test_template_replaces_one_complete_marker_line_only(self):
        template = SCRATCH / "template.md"
        template.write_text(
            "Before\n<!-- SDLC:HANDOFF -->\nAfter <!-- expression -->\n",
            encoding="utf-8",
        )

        result = self.run_cli(
            "render-handoff", self.handoff, "--forge", "azure-devops",
            "--template", template,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(result.stdout.startswith("Before\n# Add"))
        self.assertTrue(result.stdout.endswith("After <!-- expression -->\n"))
        self.assertNotIn("<!-- SDLC:HANDOFF -->", result.stdout)

    def test_template_with_multiple_markers_fails_safely(self):
        template = SCRATCH / "template.md"
        template.write_text(
            "<!-- SDLC:HANDOFF -->\n<!-- SDLC:HANDOFF -->\n",
            encoding="utf-8",
        )

        result = self.run_cli(
            "render-handoff", self.handoff, "--forge", "github",
            "--template", template,
        )

        self.assertEqual(4, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertEqual(
            f"error[E_TEMPLATE_MARKER] {template}: marker occurs more than once\n",
            result.stderr,
        )

    def test_template_rejects_invalid_utf8_and_oversize(self):
        invalid = SCRATCH / "invalid.md"
        invalid.write_bytes(b"\xff")
        oversized = SCRATCH / "oversized.md"
        oversized.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
        cases = ((invalid, "E_UTF8"), (oversized, "E_INPUT_TOO_LARGE"))
        for path, code in cases:
            with self.subTest(path=path.name):
                result = self.run_cli(
                    "render-handoff", self.handoff, "--forge", "github",
                    "--template", path,
                )
                self.assertEqual(4, result.returncode)
                self.assertEqual("", result.stdout)
                self.assertIn(f"error[{code}] {path}:", result.stderr)

    def test_stdout_is_markdown_only_unless_metadata_requested(self):
        plain = self.run_cli("render-handoff", self.handoff, "--forge", "github")
        metadata = self.run_cli(
            "render-handoff", self.handoff, "--forge", "github", "--metadata-json"
        )

        self.assertEqual(0, plain.returncode, plain.stderr)
        self.assertEqual("", plain.stderr)
        self.assertTrue(plain.stdout.startswith("# Add"))
        self.assertEqual(0, metadata.returncode, metadata.stderr)
        payload = json.loads(metadata.stderr)
        self.assertEqual("stdout", payload["result"]["destination"])
        self.assertEqual(
            len(metadata.stdout.encode("utf-8")), payload["result"]["bytes"]
        )
        self.assertEqual(
            "sha256:" + hashlib.sha256(metadata.stdout.encode("utf-8")).hexdigest(),
            payload["result"]["sha256"],
        )

    def test_explicit_output_emits_metadata_and_requires_force(self):
        output = SCRATCH / "handoff.md"
        first = self.run_cli(
            "render-handoff", self.handoff, "--forge", "gitlab", "--output", output
        )
        original = output.read_bytes()
        refused = self.run_cli(
            "render-handoff", self.handoff, "--forge", "github", "--output", output
        )
        forced = self.run_cli(
            "render-handoff", self.handoff, "--forge", "github",
            "--output", output, "--force",
        )

        self.assertEqual(0, first.returncode, first.stderr)
        payload = json.loads(first.stdout)
        self.assertEqual(str(output), payload["result"]["destination"])
        self.assertEqual("Merge request handoff", payload["result"]["artifactLabel"])
        self.assertEqual(4, refused.returncode)
        self.assertEqual("", refused.stdout)
        self.assertEqual(original, output.read_bytes())
        self.assertIn("error[E_OUTPUT_EXISTS]", refused.stderr)
        self.assertEqual(0, forced.returncode, forced.stderr)
        self.assertEqual("Pull request handoff", json.loads(forced.stdout)["result"]["artifactLabel"])
        self.assertNotIn(b"\r", output.read_bytes())
        self.assertTrue(output.read_bytes().endswith(b"\n"))

    def test_missing_output_parent_and_nonlocal_paths_fail_without_writes(self):
        missing = SCRATCH / "missing" / "handoff.md"
        result = self.run_cli(
            "render-handoff", self.handoff, "--forge", "github", "--output", missing
        )
        remote = self.run_cli(
            "render-handoff", self.handoff, "--forge", "github",
            "--template", "https://example.invalid/template.md",
        )

        self.assertEqual(4, result.returncode)
        self.assertFalse(missing.exists())
        self.assertIn("error[E_OUTPUT_PARENT]", result.stderr)
        self.assertEqual(2, remote.returncode)
        self.assertEqual("", remote.stdout)
        self.assertIn("error[E_LOCAL_PATH]", remote.stderr)

    def test_force_requires_explicit_output(self):
        result = self.run_cli(
            "render-handoff", self.handoff, "--forge", "github", "--force"
        )

        self.assertEqual(2, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertIn("error[E_USAGE] /force:", result.stderr)

    def test_invalid_handoff_produces_no_markdown_or_output_file(self):
        handoff = valid_handoff()
        handoff["repositoryState"]["statusInspected"] = False
        self.handoff.write_text(json.dumps(handoff), encoding="utf-8")
        output = SCRATCH / "not-created.md"

        result = self.run_cli(
            "render-handoff", self.handoff, "--forge", "github", "--output", output
        )

        self.assertEqual(3, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertFalse(output.exists())

    def test_atomic_writer_cleans_temporary_file_after_replace_failure(self):
        output = SCRATCH / "handoff.md"
        with mock.patch.object(Path, "replace", side_effect=OSError("blocked")):
            with self.assertRaises(Exception) as caught:
                self.renderers.write_output(output, "content\n", force=False)

        self.assertEqual("E_OUTPUT_WRITE", caught.exception.code)
        self.assertFalse(output.exists())
        self.assertEqual([], list(SCRATCH.glob("*.tmp")))

    def test_rendering_does_not_use_network_subprocess_or_environment(self):
        handoff = valid_handoff()
        with (
            mock.patch("socket.socket", side_effect=AssertionError("network")),
            mock.patch("subprocess.run", side_effect=AssertionError("process")),
            mock.patch("urllib.request.urlopen", side_effect=AssertionError("url")),
            mock.patch("os.getenv", side_effect=AssertionError("environment")),
            mock.patch.dict("os.environ", {}, clear=True),
        ):
            rendered = self.renderers.render_handoff(handoff, "github")

        self.assertIn("## Outcome", rendered)

    def test_renderer_source_has_no_forge_or_network_dependencies(self):
        source = (SCRIPTS / "handoff_renderers.py").read_text(encoding="utf-8")
        forbidden = (
            "import requests", "import subprocess", "import socket",
            "import urllib", "github.", "gitlab.", "azure.devops",
            "selenium", "playwright", "os.environ", "getenv(",
        )
        for token in forbidden:
            self.assertNotIn(token, source.lower())

    def test_output_avoids_forge_actions_and_readiness_claims(self):
        for forge in ("github", "gitlab", "azure-devops"):
            rendered = self.run_cli(
                "render-handoff", self.handoff, "--forge", forge
            ).stdout.lower()
            for forbidden in (
                "/approve", "/merge", "closes #", "fixes #", "auto-complete",
                "pr-ready", "ready for review",
            ):
                self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
