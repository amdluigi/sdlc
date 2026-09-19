import contextlib
import copy
import importlib.util
import io
import json
import re
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = (
    Path(__file__).resolve().parents[1] / "skills" / "sdlc" / "scripts"
)
PYTHON_NO_BYTECODE = [sys.executable, "-B"]
previous_bytecode_policy = sys.dont_write_bytecode
sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPT_DIR))
try:
    import adaptive_extensions
    import manage_extensions
    from adaptive_extensions import (
        AdaptiveError,
        Observation,
        activate_extension,
        candidate_fingerprint,
        confined_path,
        load_resolved_module,
        load_candidates,
        load_project_config,
        load_json_strict,
        normalize_config,
        parse_version,
        prepare_upstream,
        promote_global,
        record_observation,
        reject_extension,
        set_candidate_status,
        validate_extension,
        version_satisfies,
        write_json_atomic,
    )
finally:
    sys.path.remove(str(SCRIPT_DIR))
    sys.dont_write_bytecode = previous_bytecode_policy

VALIDATOR_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate.py"
VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "repository_validate", VALIDATOR_PATH
)
repository_validate = importlib.util.module_from_spec(VALIDATOR_SPEC)
VALIDATOR_SPEC.loader.exec_module(repository_validate)


def observation(**overrides):
    values = {
        "task_id": "task-a",
        "date": "2026-09-16",
        "summary": "Verify generated output after contract changes.",
        "category": "verification",
        "action": "Verify generated API client",
        "trigger": "A contract changes",
        "exit_signal": "Generated output is checked",
        "evidence": ("tests/test_client.py",),
    }
    values.update(overrides)
    return Observation(**values)


def core_registry():
    return {
        "schemaVersion": 1,
        "modules": [{"name": "testing"}, {"name": "review"}],
    }


def create_extension_fixture(test_case, **overrides):
    temporary = tempfile.TemporaryDirectory()
    test_case.addCleanup(temporary.cleanup)
    root = Path(temporary.name)
    return create_extension_at(root, **overrides)


def create_extension_at(root, **overrides):
    root = Path(root)
    identifier = overrides.pop("id", "verify-generated-api-client")
    extension = root / ".sdlc" / "extensions" / identifier
    extension.mkdir(parents=True)
    metadata = {
        "schemaVersion": 1,
        "id": identifier,
        "version": "1.0.0",
        "status": "accepted",
        "category": "verification",
        "mode": "augment",
        "path": "MODULE.md",
        "trigger": "A public API contract changes.",
        "exitSignal": "Generated output is current and inspected.",
        "evidence": ["The generated diff was inspected."],
        "compatibleSdlc": ">=1.0.0 <2.0.0",
    }
    metadata.update(overrides)
    (extension / "extension.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    (extension / "MODULE.md").write_text(
        "# Verify generated API client\n\nInspect generated output.\n",
        encoding="utf-8",
    )
    (extension / "evals.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "cases": [
                    {
                        "id": "contract-changed",
                        "type": "positive",
                        "prompt": "The API contract changed.",
                        "expected": "Generated output is inspected.",
                    },
                    {
                        "id": "unrelated-change",
                        "type": "negative",
                        "prompt": "Only prose changed.",
                        "expected": "The extension does not apply.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return extension


def schema_two_config(project=None, global_extensions=None):
    return {
        "schemaVersion": 2,
        "modules": {},
        "extensions": {
            "project": {} if project is None else project,
            "global": (
                {} if global_extensions is None else global_extensions
            ),
        },
    }


class MeasurementConfigTests(unittest.TestCase):
    def test_schema_one_migration_adds_disabled_measurement(self):
        normalized = normalize_config(
            {"schemaVersion": 1, "modules": {}}, {"testing"}
        )
        self.assertEqual({"enabled": False}, normalized.get("measurement"))

    def test_schema_two_without_measurement_normalizes_disabled(self):
        normalized = normalize_config(schema_two_config(), {"testing"})
        self.assertEqual({"enabled": False}, normalized.get("measurement"))

    def test_measurement_requires_exact_boolean_contract(self):
        base = schema_two_config()
        for measurement in (
            {},
            {"enabled": 1},
            {"enabled": False, "extra": False},
        ):
            with self.subTest(measurement=measurement):
                config = copy.deepcopy(base)
                config["measurement"] = measurement
                with self.assertRaises(AdaptiveError):
                    normalize_config(config, {"testing"})

    def test_schema_two_missing_measurement_migrates_to_schema_three(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / ".sdlc" / "config.json"
            path.parent.mkdir()
            original = schema_two_config()
            original["modules"] = {"testing": True}
            path.write_text(json.dumps(original), encoding="utf-8")

            normalized = load_project_config(root, {"testing"})

            self.assertEqual({"enabled": False}, normalized.get("measurement"))
            self.assertEqual(normalized, json.loads(path.read_text(encoding="utf-8")))
            self.assertEqual(3, normalized["schemaVersion"])


def create_candidate_fixture(test_case, status="eligible"):
    temporary = tempfile.TemporaryDirectory()
    test_case.addCleanup(temporary.cleanup)
    root = Path(temporary.name)
    candidate = record_observation(
        root, observation(explicit_request=True)
    )
    if status != "eligible":
        candidate = set_candidate_status(
            root, candidate["id"], status, f"Move to {status}"
        )
    return root, candidate


def create_accepted_extension_fixture(test_case):
    root, candidate = create_candidate_fixture(test_case)
    candidate = set_candidate_status(
        root, candidate["id"], "drafted", "Draft extension"
    )
    candidate = set_candidate_status(
        root, candidate["id"], "accepted", "Approve extension"
    )
    create_extension_at(root, id=candidate["id"])
    return root, candidate["id"]


def create_directory_link(test_case, link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as error:
        if sys.platform != "win32":
            test_case.fail(f"cannot create symlink fixture: {error}")
        result = subprocess.run(
            [
                "cmd.exe",
                "/d",
                "/c",
                "mklink",
                "/J",
                str(link),
                str(target),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            test_case.fail(
                "cannot create junction fixture: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )


class SanitizationTests(unittest.TestCase):
    def test_secret_like_observation_is_rejected(self):
        with self.assertRaisesRegex(AdaptiveError, "sensitive"):
            observation(
                task_id="task-a",
                evidence=("Authorization: ******",),
            )

    def test_absolute_home_path_is_rejected(self):
        with self.assertRaisesRegex(AdaptiveError, "project-specific"):
            observation(
                task_id="task-a",
                action="Run C:\\Users\\" + "person\\private-tool.exe",
            )


class StrictInfrastructureTests(unittest.TestCase):
    def test_duplicate_json_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text('{"id":"one","id":"two"}', encoding="utf-8")
            with self.assertRaisesRegex(AdaptiveError, "duplicate key: id"):
                load_json_strict(path)

    def test_non_finite_json_numbers_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            for value in ("NaN", "Infinity", "-Infinity"):
                with self.subTest(value=value):
                    path.write_text(value, encoding="utf-8")
                    with self.assertRaisesRegex(AdaptiveError, "invalid JSON"):
                        load_json_strict(path)

    def test_invalid_utf8_is_reported_as_adaptive_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_bytes(b'{"value":"\xff"}')
            with self.assertRaisesRegex(AdaptiveError, "invalid JSON"):
                load_json_strict(path)

    def test_confined_path_rejects_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(AdaptiveError, "escapes"):
                confined_path(Path(directory), "../outside")

    def test_confined_path_accepts_nested_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(
                root / "nested" / "extension.json",
                confined_path(root, "nested/extension.json"),
            )

    def test_confined_path_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "root"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            link = root / "link"
            create_directory_link(self, link, outside)
            with self.assertRaisesRegex(AdaptiveError, "escapes"):
                confined_path(root, "link/extension.json")

    def test_atomic_write_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            write_json_atomic(path, {"schemaVersion": 1})
            self.assertEqual({"schemaVersion": 1}, json.loads(path.read_text()))

    def test_atomic_write_overwrites_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text('{"old":true}\n', encoding="utf-8")
            write_json_atomic(path, {"new": True})
            self.assertEqual({"new": True}, json.loads(path.read_text()))

    def test_atomic_write_cleans_up_after_replace_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text('{"old":true}\n', encoding="utf-8")
            with mock.patch.object(
                Path, "replace", side_effect=OSError("replace failed")
            ):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    write_json_atomic(path, {"new": True})
            self.assertEqual([path], list(Path(directory).iterdir()))
            self.assertEqual({"old": True}, json.loads(path.read_text()))

    def test_atomic_write_uses_independent_temporary_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            temporary_paths = []

            def fail_replace(temporary, destination):
                temporary_paths.append(temporary)
                raise OSError("replace failed")

            with mock.patch.object(Path, "replace", autospec=True) as replace:
                replace.side_effect = fail_replace
                for value in (1, 2):
                    with self.assertRaises(OSError):
                        write_json_atomic(path, {"value": value})

            self.assertEqual(2, len(set(temporary_paths)))

    def test_supported_semver_range(self):
        self.assertTrue(version_satisfies("1.0.1", ">=1.0.0 <2.0.0"))
        self.assertFalse(version_satisfies("2.0.0", ">=1.0.0 <2.0.0"))

    def test_each_supported_version_operator(self):
        cases = (
            (">1.0.0", True),
            (">2.0.0", False),
            (">=2.0.0", True),
            ("<2.0.0", False),
            ("<=2.0.0", True),
            ("==2.0.0", True),
            ("==2.0.1", False),
        )
        for constraint, expected in cases:
            with self.subTest(constraint=constraint):
                self.assertEqual(
                    expected, version_satisfies("2.0.0", constraint)
                )

    def test_semver_components_reject_leading_zeroes(self):
        for version in ("01.2.3", "1.02.3", "1.2.03"):
            with self.subTest(version=version):
                with self.assertRaisesRegex(AdaptiveError, "invalid version"):
                    parse_version(version)

    def test_unsupported_constraint_is_rejected_after_failed_comparison(self):
        with self.assertRaisesRegex(
            AdaptiveError, "invalid version constraint: \\^2.0.0"
        ):
            version_satisfies("1.0.0", ">=2.0.0 ^2.0.0")

    def test_cli_validation_error_uses_stderr_and_exit_code_two(self):
        result = subprocess.run(
            [*PYTHON_NO_BYTECODE, str(SCRIPT_DIR / "manage_extensions.py")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertIn("a subcommand is required", result.stderr)

    def test_cli_operational_error_uses_stderr_and_exit_code_two(self):
        stderr = io.StringIO()
        with mock.patch.object(
            manage_extensions,
            "_load_candidates",
            side_effect=OSError("disk unavailable\ninternal detail"),
        ):
            with contextlib.redirect_stderr(stderr):
                result = manage_extensions.main(
                    ["list-candidates", "--project-root", "project"]
                )
        self.assertEqual(2, result)
        self.assertEqual("operation failed: disk unavailable\n", stderr.getvalue())


class ConfigTests(unittest.TestCase):
    def test_schema_one_is_normalized_to_schema_three(self):
        config = normalize_config(
            {"schemaVersion": 1, "modules": {"testing": False}},
            {"testing", "review", "continuous-improvement"},
        )
        self.assertEqual(3, config["schemaVersion"])
        self.assertFalse(config["modules"]["testing"])
        self.assertTrue(config["modules"]["review"])
        self.assertTrue(config["modules"]["continuous-improvement"])
        self.assertEqual({"project": {}, "global": {}}, config["extensions"])

    def test_new_extensions_default_disabled(self):
        config = normalize_config(
            {
                "schemaVersion": 2,
                "modules": {},
                "extensions": {"project": {}, "global": {}},
            },
            {"continuous-improvement"},
        )
        self.assertEqual({}, config["extensions"]["project"])

    def test_unknown_top_level_field_is_rejected(self):
        with self.assertRaisesRegex(AdaptiveError, "unknown config field"):
            normalize_config(
                {"schemaVersion": 1, "modules": {}, "extra": True},
                {"testing"},
            )

    def test_unknown_core_module_is_rejected(self):
        with self.assertRaisesRegex(AdaptiveError, "unknown core module"):
            normalize_config(
                {"schemaVersion": 1, "modules": {"unknown": True}},
                {"testing"},
            )

    def test_non_boolean_activation_values_are_rejected(self):
        cases = (
            {"schemaVersion": 1, "modules": {"testing": 1}},
            {
                "schemaVersion": 2,
                "modules": {},
                "extensions": {
                    "project": {"extension": "yes"},
                    "global": {},
                },
            },
        )
        for config in cases:
            with self.subTest(config=config):
                with self.assertRaisesRegex(AdaptiveError, "must be boolean"):
                    normalize_config(config, {"testing"})

    def test_unknown_extensions_field_is_rejected(self):
        with self.assertRaisesRegex(AdaptiveError, "unknown extensions field"):
            normalize_config(
                {
                    "schemaVersion": 2,
                    "modules": {},
                    "extensions": {
                        "project": {},
                        "global": {},
                        "other": {},
                    },
                },
                {"testing"},
            )

    def test_unsupported_schema_version_is_rejected(self):
        for version in (True, 5):
            with self.subTest(version=version):
                with self.assertRaisesRegex(
                    AdaptiveError, "unsupported schema version"
                ):
                    normalize_config(
                        {"schemaVersion": version, "modules": {}},
                        {"testing"},
                    )

    def test_load_project_config_migrates_schema_one_on_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / ".sdlc" / "config.json"
            path.parent.mkdir()
            path.write_text(
                '{"schemaVersion":1,"modules":{"testing":false}}\n',
                encoding="utf-8",
            )

            config = load_project_config(root, {"testing", "review"})

            self.assertEqual(config, json.loads(path.read_text("utf-8")))
            self.assertEqual(3, config["schemaVersion"])
            self.assertFalse(config["modules"]["testing"])
            self.assertTrue(config["modules"]["review"])

    def test_load_project_config_does_not_create_missing_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = load_project_config(root, {"testing"})
            self.assertFalse((root / ".sdlc" / "config.json").exists())
            self.assertTrue(config["modules"]["testing"])

    def test_load_project_config_rejects_reparse_config_before_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / ".sdlc" / "config.json"
            config.parent.mkdir()
            config.write_text(
                '{"schemaVersion":2,"modules":{},'
                '"extensions":{"project":{},"global":{}}}',
                encoding="utf-8",
            )
            real_lstat = Path.lstat

            def mark_config_as_reparse(path):
                result = real_lstat(path)
                if path == config:
                    return types.SimpleNamespace(
                        st_mode=result.st_mode,
                        st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
                    )
                return result

            with mock.patch.object(
                Path,
                "lstat",
                autospec=True,
                side_effect=mark_config_as_reparse,
            ), mock.patch.object(
                Path,
                "read_text",
                side_effect=AssertionError("reparse config was read"),
            ):
                with self.assertRaisesRegex(AdaptiveError, "reparse"):
                    load_project_config(root, {"testing"})


class CandidateTests(unittest.TestCase):
    def test_learning_reparse_escape_is_rejected_before_external_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            outside = Path(directory) / "outside"
            (root / ".sdlc").mkdir(parents=True)
            outside.mkdir()
            create_directory_link(self, root / ".sdlc" / "learning", outside)

            with self.assertRaisesRegex(AdaptiveError, "reparse"):
                record_observation(root, observation())

            self.assertFalse((outside / "candidates.json").exists())

    def test_project_root_reparse_is_rejected_before_candidate_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real_lstat = Path.lstat

            def mark_project_as_reparse(path):
                result = real_lstat(path)
                if path == root:
                    return types.SimpleNamespace(
                        st_mode=result.st_mode,
                        st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
                    )
                return result

            with mock.patch.object(
                Path,
                "lstat",
                autospec=True,
                side_effect=mark_project_as_reparse,
            ), mock.patch.object(
                Path,
                "read_text",
                side_effect=AssertionError("escaped candidate was read"),
            ):
                with self.assertRaisesRegex(AdaptiveError, "project root.*reparse"):
                    load_candidates(root)

    def test_two_distinct_tasks_make_candidate_eligible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record_observation(root, observation(task_id="task-a"))
            candidate = record_observation(
                root, observation(task_id="task-b")
            )
            self.assertEqual("eligible", candidate["status"])
            self.assertEqual(2, len(candidate["occurrences"]))

    def test_same_task_does_not_increment_occurrence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record_observation(root, observation(task_id="task-a"))
            candidate = record_observation(
                root, observation(task_id="task-a")
            )
            self.assertEqual("observed", candidate["status"])
            self.assertEqual(1, len(candidate["occurrences"]))

    def test_explicit_request_is_immediately_eligible(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = record_observation(
                Path(directory),
                observation(task_id="task-a", explicit_request=True),
            )
            self.assertEqual("eligible", candidate["status"])

    def test_fingerprint_uses_only_normalized_generalized_fields(self):
        first = observation(
            task_id="task-a",
            date="2026-09-16",
            summary="First wording",
            action="VERIFY   generated API CLIENT",
            evidence=("first/reference.txt",),
        )
        second = observation(
            task_id="task-b",
            date="2026-09-17",
            summary="Second wording",
            action="verify generated api client",
            evidence=("second/reference.txt",),
            explicit_request=True,
        )
        self.assertEqual(
            candidate_fingerprint(first), candidate_fingerprint(second)
        )
        self.assertTrue(candidate_fingerprint(first).startswith("sha256:"))

    def test_observation_rejects_unsafe_or_unbounded_values(self):
        cases = (
            ("task_id", "Task A"),
            ("category", "Verification"),
            ("summary", ""),
            ("action", "x" * 201),
            ("trigger", "Authorization: Bearer secret-value"),
            ("exit_signal", "-----BEGIN " + "PRIVATE KEY-----"),
            ("evidence", ("C:\\Users\\person\\secret.txt",)),
            ("evidence", ("line one\nline two",)),
        )
        cases += (
            ("evidence", ("See C:\\repo\\secret.txt",)),
            ("evidence", ("See /repo/secret.txt",)),
            ("evidence", ("\\repo\\secret.txt",)),
            ("evidence", ("See \\repo\\secret.txt",)),
            ("evidence", ("\\\\server\\share\\secret.txt",)),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                with self.assertRaises(AdaptiveError):
                    observation(**{field: value})

    def test_observation_allows_ordinary_prose_with_slashes(self):
        value = observation(
            evidence=(
                "Compare input/output behavior using the /skills command.",
                "See https://example.com/docs and match \\d+ expressions.",
            )
        )
        self.assertEqual(
            "Compare input/output behavior using the /skills command.",
            value.evidence[0],
        )
        self.assertEqual(
            "See https://example.com/docs and match \\d+ expressions.",
            value.evidence[1],
        )

    def test_observation_absolute_path_corpus(self):
        cases = (
            (False, "/secret.txt"),
            (False, "artifact at /secret.txt"),
            (False, "/etc/secret"),
            (False, "artifact at /var/tmp/output.log"),
            (False, "C:\\repo\\secret.txt"),
            (False, "Path=C:\\repo\\secret.txt"),
            (False, "\\secret.txt"),
            (False, "\\repo\\secret.txt"),
            (False, "\\\\server\\share\\secret.txt"),
            (True, "regex \\d+\\s+"),
            (True, "escaped token \\n"),
            (True, "relative path docs/plan.md"),
            (True, "command npm test -- parser"),
            (True, "URL https://example.com/path"),
            (True, "/help"),
            (True, "/skills"),
            (True, "/review"),
        )
        for accepted, reference in cases:
            with self.subTest(reference=reference):
                if accepted:
                    self.assertEqual(
                        (reference,),
                        observation(evidence=(reference,)).evidence,
                    )
                else:
                    with self.assertRaisesRegex(
                        AdaptiveError, "relative description"
                    ):
                        observation(evidence=(reference,))

    def test_candidate_file_has_schema_and_minimal_occurrence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = record_observation(root, observation())
            stored = json.loads(
                (
                    root / ".sdlc" / "learning" / "candidates.json"
                ).read_text("utf-8")
            )
            self.assertEqual(1, stored["schemaVersion"])
            self.assertEqual([candidate], stored["candidates"])
            self.assertEqual(
                {
                    "date": "2026-09-16",
                    "task": "task-a",
                    "signal": "Verify generated output after contract changes.",
                    "evidence": ["tests/test_client.py"],
                },
                candidate["occurrences"][0],
            )

    def test_exact_status_transitions_are_enforced_and_recorded(self):
        allowed = (
            ("eligible", "drafted"),
            ("drafted", "accepted"),
            ("accepted", "superseded"),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = record_observation(
                root, observation(explicit_request=True)
            )
            for source, target in allowed:
                self.assertEqual(source, candidate["status"])
                candidate = set_candidate_status(
                    root, candidate["id"], target, f"Move to {target}"
                )
            self.assertEqual("superseded", candidate["status"])
            self.assertEqual(4, len(candidate["decisionHistory"]))
            self.assertEqual(
                candidate["decisionHistory"][-1], candidate["lastDecision"]
            )

    def test_manual_status_cannot_record_promotion_without_destination(self):
        root, candidate_id = create_accepted_extension_fixture(self)

        with self.assertRaisesRegex(
            AdaptiveError, "global or upstream promotion command"
        ):
            set_candidate_status(
                root,
                candidate_id,
                "promoted",
                "Claim promotion without creating a destination",
            )

        self.assertEqual(
            "accepted",
            next(
                item
                for item in load_candidates(root)["candidates"]
                if item["id"] == candidate_id
            )["status"],
        )

    def test_invalid_status_transition_leaves_file_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = record_observation(root, observation())
            path = root / ".sdlc" / "learning" / "candidates.json"
            before = path.read_bytes()
            with self.assertRaisesRegex(
                AdaptiveError, "invalid candidate transition"
            ):
                set_candidate_status(
                    root, candidate["id"], "promoted", "Skip review"
                )
            self.assertEqual(before, path.read_bytes())

    def test_alternative_rejection_and_supersession_transitions(self):
        scenarios = (
            (("drafted",), "rejected"),
            (("drafted", "accepted"), "superseded"),
        )
        for intermediate_statuses, target in scenarios:
            with self.subTest(
                intermediate_statuses=intermediate_statuses, target=target
            ):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    candidate = record_observation(
                        root, observation(explicit_request=True)
                    )
                    for status in intermediate_statuses:
                        candidate = set_candidate_status(
                            root,
                            candidate["id"],
                            status,
                            f"Move to {status}",
                        )
                    candidate = set_candidate_status(
                        root, candidate["id"], target, f"Move to {target}"
                    )
                    self.assertEqual(target, candidate["status"])

    def test_manual_eligibility_requires_recurrence_or_explicit_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = record_observation(root, observation())
            path = root / ".sdlc" / "learning" / "candidates.json"
            before = path.read_bytes()

            with self.assertRaisesRegex(
                AdaptiveError, "two distinct tasks or an explicit request"
            ):
                set_candidate_status(
                    root,
                    candidate["id"],
                    "eligible",
                    "Manually mark eligible",
                )

            self.assertEqual(before, path.read_bytes())

    def test_manual_eligibility_accepts_two_distinct_tasks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = record_observation(root, observation())
            path = root / ".sdlc" / "learning" / "candidates.json"
            state = json.loads(path.read_text("utf-8"))
            state["candidates"][0]["occurrences"].append(
                {
                    "date": "2026-09-17",
                    "task": "task-b",
                    "signal": "Observed in another task.",
                    "evidence": ["tests/test_other.py"],
                }
            )
            path.write_text(json.dumps(state), encoding="utf-8")

            candidate = set_candidate_status(
                root,
                candidate["id"],
                "eligible",
                "Observed in two distinct tasks",
            )

            self.assertEqual("eligible", candidate["status"])
            self.assertEqual(2, candidate["lastDecision"]["occurrenceCount"])

    def test_rejected_candidate_needs_new_task_evidence_for_eligibility(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = record_observation(
                root, observation(explicit_request=True)
            )
            candidate = set_candidate_status(
                root, candidate["id"], "rejected", "Not generalized"
            )
            with self.assertRaisesRegex(AdaptiveError, "new evidence"):
                set_candidate_status(
                    root, candidate["id"], "eligible", "Try again"
                )
            record_observation(root, observation(task_id="task-a"))
            with self.assertRaisesRegex(AdaptiveError, "new evidence"):
                set_candidate_status(
                    root, candidate["id"], "eligible", "Try again"
                )
            candidate = record_observation(
                root, observation(task_id="task-b")
            )
            self.assertEqual("eligible", candidate["status"])

    def test_persisted_reconsideration_requires_increased_occurrence_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = record_observation(
                root, observation(explicit_request=True)
            )
            candidate = set_candidate_status(
                root, candidate["id"], "rejected", "Not generalized"
            )
            path = root / ".sdlc" / "learning" / "candidates.json"
            state = json.loads(path.read_text("utf-8"))
            decision = {
                "timestamp": "2026-09-16T01:00:00Z",
                "from": "rejected",
                "to": "eligible",
                "reason": "Tampered reconsideration",
                "occurrenceCount": 1,
            }
            stored = state["candidates"][0]
            stored["status"] = "eligible"
            stored["updatedAt"] = decision["timestamp"]
            stored["decisionHistory"].append(decision)
            stored["lastDecision"] = decision
            path.write_text(json.dumps(state), encoding="utf-8")

            result = self._run_cli_raw(
                "list-candidates", "--project-root", str(root)
            )

            self.assertEqual(2, result.returncode)
            self.assertEqual("", result.stdout)
            self.assertIn("new evidence after rejection", result.stderr)

    def test_cli_commands_return_json_without_evidence_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "observation.json"
            input_path.write_text(
                json.dumps(
                    {
                        "task_id": "task-a",
                        "date": "2026-09-16",
                        "summary": "Verify generated output.",
                        "category": "verification",
                        "action": "Verify generated API client",
                        "trigger": "A contract changes",
                        "exit_signal": "Generated output is checked",
                        "evidence": ["private/reference-name.txt"],
                        "explicit_request": True,
                    }
                ),
                encoding="utf-8",
            )
            record_result = self._run_cli(
                "record",
                "--project-root",
                str(root),
                "--input",
                str(input_path),
            )
            recorded = json.loads(record_result.stdout)
            self.assertEqual("eligible", recorded["status"])
            self.assertNotIn("private/reference-name.txt", record_result.stdout)

            status_result = self._run_cli(
                "status",
                "--project-root",
                str(root),
                "--candidate",
                recorded["id"],
                "--status",
                "rejected",
                "--reason",
                "Belongs in project standards",
            )
            self.assertEqual(
                "rejected", json.loads(status_result.stdout)["status"]
            )
            self.assertNotIn(
                "private/reference-name.txt", status_result.stdout
            )

            list_result = self._run_cli(
                "list-candidates", "--project-root", str(root)
            )
            listed = json.loads(list_result.stdout)
            self.assertEqual("rejected", listed["candidates"][0]["status"])
            self.assertNotIn("private/reference-name.txt", list_result.stdout)

    def test_cli_rejects_tampered_candidate_data_without_echoing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / ".sdlc" / "learning" / "candidates.json"
            path.parent.mkdir(parents=True)
            sensitive_input = "password=" + "actual-sensitive-value"
            path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "candidates": [
                            {
                                "id": "unsafe-candidate",
                                "fingerprint": "sha256:" + ("0" * 64),
                                "status": "observed",
                                "summary": sensitive_input,
                                "category": "verification",
                                "occurrences": [],
                                "createdAt": "2026-09-16T00:00:00Z",
                                "updatedAt": "2026-09-16T00:00:00Z",
                                "lastDecision": None,
                                "decisionHistory": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = self._run_cli_raw(
                "list-candidates", "--project-root", str(root)
            )
            self.assertEqual(2, result.returncode)
            self.assertEqual("", result.stdout)
            self.assertNotIn(sensitive_input, result.stdout)
            self.assertNotIn(sensitive_input, result.stderr)

    def _run_cli(self, *arguments):
        result = self._run_cli_raw(*arguments)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        return result

    def _run_cli_raw(self, *arguments):
        return subprocess.run(
            [
                *PYTHON_NO_BYTECODE,
                str(SCRIPT_DIR / "manage_extensions.py"),
                *arguments,
            ],
            capture_output=True,
            text=True,
            check=False,
        )


class ExtensionValidationTests(unittest.TestCase):
    def test_valid_augment_extension_passes(self):
        extension = create_extension_fixture(self, mode="augment")
        metadata = validate_extension(extension, "1.0.0", core_registry())
        self.assertEqual("verify-generated-api-client", metadata["id"])

    def test_validation_rejects_invalid_metadata_contracts(self):
        cases = (
            ("schemaVersion", 2, "schema"),
            ("id", "Invalid ID", "kebab-case"),
            ("version", "1.0", "invalid version"),
            ("status", "eligible", "status"),
            ("mode", "replace", "augment"),
            ("category", "", "category"),
            ("trigger", "", "trigger"),
            ("exitSignal", "", "exitSignal"),
            ("evidence", [], "evidence"),
            ("compatibleSdlc", ">=2.0.0", "compatible"),
        )
        for field, value, message in cases:
            with self.subTest(field=field):
                extension = create_extension_fixture(
                    self, **{field: value}
                )
                with self.assertRaisesRegex(AdaptiveError, message):
                    validate_extension(
                        extension, "1.0.0", core_registry()
                    )

    def test_extension_id_must_match_directory_and_not_core(self):
        extension = create_extension_fixture(self, id="testing")
        with self.assertRaisesRegex(AdaptiveError, "core module"):
            validate_extension(extension, "1.0.0", core_registry())

        extension = create_extension_fixture(self)
        metadata_path = extension / "extension.json"
        metadata = json.loads(metadata_path.read_text("utf-8"))
        metadata["id"] = "different-id"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        with self.assertRaisesRegex(AdaptiveError, "directory"):
            validate_extension(extension, "1.0.0", core_registry())

    def test_path_escape_is_rejected(self):
        extension = create_extension_fixture(self, path="../outside.md")
        with self.assertRaisesRegex(AdaptiveError, "escapes"):
            validate_extension(extension, "1.0.0", core_registry())

    def test_extension_root_symlink_is_rejected_before_external_read(self):
        extension = create_extension_fixture(self)
        real_lstat = Path.lstat

        def mark_extension_as_reparse(path):
            result = real_lstat(path)
            if path == extension:
                return types.SimpleNamespace(
                    st_mode=result.st_mode,
                    st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
                )
            return result

        with mock.patch.object(
            Path, "lstat", autospec=True, side_effect=mark_extension_as_reparse
        ), mock.patch.object(
            Path,
            "iterdir",
            side_effect=AssertionError("external root was read"),
        ):
            with self.assertRaisesRegex(AdaptiveError, "reparse"):
                validate_extension(extension, "1.0.0", core_registry())

    def test_extensions_ancestor_symlink_is_rejected_before_external_read(self):
        extension = create_extension_fixture(self)
        extensions = extension.parent
        real_lstat = Path.lstat

        def mark_extensions_as_reparse(path):
            result = real_lstat(path)
            if path == extensions:
                return types.SimpleNamespace(
                    st_mode=result.st_mode,
                    st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
                )
            return result

        with mock.patch.object(
            Path, "lstat", autospec=True, side_effect=mark_extensions_as_reparse
        ), mock.patch.object(
            Path,
            "iterdir",
            side_effect=AssertionError("external root was read"),
        ):
            with self.assertRaisesRegex(AdaptiveError, "reparse"):
                validate_extension(extension, "1.0.0", core_registry())

    def test_resolved_extension_outside_owned_root_is_rejected_before_read(self):
        extension = create_extension_fixture(self)
        real_resolve = Path.resolve

        def escape_extension(path, strict=False):
            if path == extension:
                return extension.parents[2] / "outside" / extension.name
            return real_resolve(path, strict=strict)

        with mock.patch.object(
            Path, "resolve", autospec=True, side_effect=escape_extension
        ), mock.patch.object(
            Path,
            "iterdir",
            side_effect=AssertionError("external root was read"),
        ):
            with self.assertRaisesRegex(AdaptiveError, "escapes"):
                validate_extension(extension, "1.0.0", core_registry())

    def test_only_exact_extension_files_are_allowed(self):
        extension = create_extension_fixture(self)
        scripts = extension / "scripts"
        scripts.mkdir()
        (scripts / "run.py").write_text("print('unsafe')", encoding="utf-8")
        with self.assertRaisesRegex(AdaptiveError, "exactly"):
            validate_extension(extension, "1.0.0", core_registry())

    def test_positive_and_negative_evaluations_are_required(self):
        extension = create_extension_fixture(self)
        evals_path = extension / "evals.json"
        evaluations = json.loads(evals_path.read_text("utf-8"))
        evaluations["cases"] = evaluations["cases"][:1]
        evals_path.write_text(json.dumps(evaluations), encoding="utf-8")
        with self.assertRaisesRegex(AdaptiveError, "positive and negative"):
            validate_extension(extension, "1.0.0", core_registry())

    def test_evaluation_schema_rejects_unknown_or_missing_fields(self):
        mutations = (
            (
                "unknown top-level field",
                lambda value: value.update({"extra": True}),
                "evals.json fields",
            ),
            (
                "unknown case field",
                lambda value: value["cases"][0].update({"extra": True}),
                "evaluation case fields",
            ),
            (
                "missing prompt",
                lambda value: value["cases"][0].pop("prompt"),
                "prompt",
            ),
            (
                "missing expected behavior",
                lambda value: value["cases"][0].pop("expected"),
                "expected",
            ),
            (
                "inconsistent type and kind",
                lambda value: value["cases"][0].update({"kind": "negative"}),
                "type and kind",
            ),
        )
        for name, mutate, message in mutations:
            with self.subTest(name=name):
                extension = create_extension_fixture(self)
                evals_path = extension / "evals.json"
                evaluations = json.loads(evals_path.read_text("utf-8"))
                mutate(evaluations)
                evals_path.write_text(json.dumps(evaluations), encoding="utf-8")
                with self.assertRaisesRegex(AdaptiveError, message):
                    validate_extension(
                        extension, "1.0.0", core_registry()
                    )

    def test_sensitive_or_unsafe_content_is_rejected(self):
        cases = (
            ("Authorization: ******", "sensitive"),
            ("Run curl https://example.invalid/upload", "network"),
            ("Run git push after validation", "publish"),
            ("Modify ~/.agents/skills/sdlc/SKILL.md", "core"),
            ("Copy the raw prompt into the report", "raw"),
            ("Disable testing for this workflow", "core"),
        )
        for content, message in cases:
            with self.subTest(content=content):
                extension = create_extension_fixture(self)
                (extension / "MODULE.md").write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(AdaptiveError, message):
                    validate_extension(
                        extension, "1.0.0", core_registry()
                    )

    def test_representative_dangerous_instructions_are_rejected(self):
        cases = (
            ("Run npm publish when checks pass.", "publish"),
            ("Use requests.post(endpoint, files=data).", "network"),
            ("Call urllib.request.urlopen(target).", "network"),
            ("Call aiohttp.ClientSession().post(target).", "network"),
            ("Use client.upload_file(report, bucket, key).", "network"),
            ("Save the verbatim prompt in an artifact.", "raw"),
            ("Copy raw_prompt to the report unchanged.", "raw"),
            ("Write the result to /etc/sdlc.conf.", "system"),
            ("Save output at /project-owned/result.txt.", "system"),
            ("Run PowerShell Invoke-RestMethod against the endpoint.", "network"),
            ("Update the installed SDLC skill with these rules.", "core"),
            ("Change the global skill installation.", "core"),
        )
        for content, message in cases:
            with self.subTest(content=content):
                extension = create_extension_fixture(self)
                (extension / "MODULE.md").write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(AdaptiveError, message):
                    validate_extension(
                        extension, "1.0.0", core_registry()
                    )

    def test_chained_python_clients_are_rejected(self):
        cases = (
            "requests.Session().post(endpoint)",
            "REQUESTS . Session ( ) . POST ( endpoint )",
            "httpx.Client().put(endpoint)",
            "httpx . AsyncClient ( timeout=5 ) . get ( endpoint )",
            "aiohttp.ClientSession().delete(endpoint)",
        )
        for content in cases:
            with self.subTest(content=content):
                extension = create_extension_fixture(self)
                (extension / "MODULE.md").write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(AdaptiveError, "network"):
                    validate_extension(
                        extension, "1.0.0", core_registry()
                    )

    def test_package_publish_commands_are_rejected(self):
        cases = (
            "cargo publish",
            "CARGO    PUBLISH --dry-run",
            "dotnet nuget push package.nupkg",
            "gem push package.gem",
        )
        for content in cases:
            with self.subTest(content=content):
                extension = create_extension_fixture(self)
                (extension / "MODULE.md").write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(AdaptiveError, "publish"):
                    validate_extension(
                        extension, "1.0.0", core_registry()
                    )

    def test_raw_prompt_and_cross_skill_writes_are_rejected(self):
        cases = (
            ("Write the verbatim prompt into the report.", "raw"),
            ("WRITE   VERBATIM   PROMPTS to disk.", "raw"),
            ("Update ~/.agents/skills/other-skill/SKILL.md.", "core"),
            ("update  ~/.CLAUDE/skills/Other-Skill/SKILL.md", "core"),
        )
        for content, message in cases:
            with self.subTest(content=content):
                extension = create_extension_fixture(self)
                (extension / "MODULE.md").write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(AdaptiveError, message):
                    validate_extension(
                        extension, "1.0.0", core_registry()
                    )

    def test_slash_command_prose_is_allowed_but_path_writes_are_rejected(self):
        allowed = (
            "Write /help usage guidance.",
            "Document /skills behavior.",
            "Explain /review output.",
        )
        for content in allowed:
            with self.subTest(content=content):
                extension = create_extension_fixture(self)
                (extension / "MODULE.md").write_text(content, encoding="utf-8")
                self.assertEqual(
                    extension.name,
                    validate_extension(
                        extension, "1.0.0", core_registry()
                    )["id"],
                )


        rejected = (
            "Write /etc/sdlc.conf.",
            "Store output in C:\\Windows\\Temp\\sdlc.txt.",
            "Save the result to \\\\server\\share\\sdlc.txt.",
        )
        for content in rejected:
            with self.subTest(content=content):
                extension = create_extension_fixture(self)
                (extension / "MODULE.md").write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(AdaptiveError, "system"):
                    validate_extension(
                        extension, "1.0.0", core_registry()
                    )

    def test_validation_help_requires_model_safety_review(self):
        help_text = manage_extensions._build_parser().format_help()
        normalized = " ".join(help_text.split())
        self.assertIn(
            "Static extension validation is defense in depth", normalized
        )
        self.assertIn("mandatory", normalized)
        self.assertIn(
            "model safety review remains required",
            normalized,
        )

    def test_safety_prohibitions_are_allowed(self):
        extension = create_extension_fixture(self)
        (extension / "MODULE.md").write_text(
            "Do not use the network. Do not publish content. "
            "Do not copy raw prompts. Do not mutate the installed core.",
            encoding="utf-8",
        )
        self.assertEqual(
            extension.name,
            validate_extension(
                extension, "1.0.0", core_registry()
            )["id"],
        )

    def test_negation_is_scoped_to_its_own_actionable_clause(self):
        cases = (
            (
                "Do not write a summary. "
                "Update ~/.agents/skills/other-skill/SKILL.md.",
                "core",
            ),
            (
                "Do not save raw prompts. Copy them to /tmp/prompts.txt.",
                "system",
            ),
            (
                "Do not update the skill. Document /help usage guidance.",
                None,
            ),
            (
                "Never publish this package. Explain cargo publish policy.",
                None,
            ),
        )
        for content, error in cases:
            with self.subTest(content=content):
                extension = create_extension_fixture(self)
                (extension / "MODULE.md").write_text(content, encoding="utf-8")
                if error is None:
                    self.assertEqual(
                        extension.name,
                        validate_extension(
                            extension, "1.0.0", core_registry()
                        )["id"],
                    )
                else:
                    with self.assertRaisesRegex(AdaptiveError, error):
                        validate_extension(
                            extension, "1.0.0", core_registry()
                        )

    def test_raw_evaluation_fields_are_rejected(self):
        extension = create_extension_fixture(self)
        evals_path = extension / "evals.json"
        evaluations = json.loads(evals_path.read_text("utf-8"))
        evaluations["rawPrompt"] = "copied input"
        evals_path.write_text(json.dumps(evaluations), encoding="utf-8")
        with self.assertRaisesRegex(AdaptiveError, "raw content"):
            validate_extension(extension, "1.0.0", core_registry())

    def test_invalid_metadata_types_are_adaptive_errors(self):
        cases = (
            ("schemaVersion", True, "schema"),
            ("status", [], "status"),
            ("path", None, "path"),
        )
        for field, value, message in cases:
            with self.subTest(field=field):
                extension = create_extension_fixture(
                    self, **{field: value}
                )
                with self.assertRaisesRegex(AdaptiveError, message):
                    validate_extension(
                        extension, "1.0.0", core_registry()
                    )

    def test_activation_requires_accepted_status(self):
        extension = create_extension_fixture(self, status="drafted")
        with self.assertRaisesRegex(AdaptiveError, "explicit approval"):
            activate_extension(extension.parents[2], extension.name)
        self.assertFalse(
            (extension.parents[2] / ".sdlc" / "config.json").exists()
        )

    def test_activation_enables_only_project_extension(self):
        extension = create_extension_fixture(self)
        root = extension.parents[2]
        config_path = root / ".sdlc" / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "modules": {"testing": False},
                }
            ),
            encoding="utf-8",
        )

        result = activate_extension(root, extension.name)

        config = json.loads(config_path.read_text("utf-8"))
        self.assertTrue(config["extensions"]["project"][extension.name])
        self.assertEqual({}, config["extensions"]["global"])
        self.assertFalse(config["phases"]["verification"]["testing"])
        self.assertEqual(4, config["schemaVersion"])
        self.assertEqual([".sdlc/config.json"], result["changedPaths"])
        self.assertIn(extension.name, result["rollback"])

    def test_rejection_is_persisted_without_activation_or_deletion(self):
        root, candidate = create_candidate_fixture(self, status="eligible")
        extension = root / ".sdlc" / "extensions" / candidate["id"]
        extension.mkdir(parents=True)
        create_extension_fixture_path = create_extension_fixture(
            self, id=candidate["id"], status="drafted"
        )
        for source in create_extension_fixture_path.iterdir():
            source.replace(extension / source.name)

        reject_extension(root, candidate["id"], "Existing module covers it")

        persisted = load_candidates(root)
        self.assertEqual("rejected", persisted["candidates"][0]["status"])
        self.assertEqual(
            "Existing module covers it",
            persisted["candidates"][0]["lastDecision"]["reason"],
        )
        self.assertEqual(
            "rejected",
            json.loads((extension / "extension.json").read_text("utf-8"))[
                "status"
            ],
        )
        self.assertTrue(extension.exists())
        self.assertFalse((root / ".sdlc" / "config.json").exists())

    def test_rejection_validates_both_documents_before_first_write(self):
        root, candidate = create_candidate_fixture(self, status="eligible")
        extension = root / ".sdlc" / "extensions" / candidate["id"]
        extension.mkdir(parents=True)
        fixture = create_extension_fixture(
            self, id=candidate["id"], status="drafted"
        )
        for source in fixture.iterdir():
            source.replace(extension / source.name)
        metadata_path = extension / "extension.json"
        metadata = json.loads(metadata_path.read_text("utf-8"))
        metadata["unexpected"] = True
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        candidate_path = root / ".sdlc" / "learning" / "candidates.json"
        before = candidate_path.read_bytes()

        with self.assertRaisesRegex(AdaptiveError, "metadata"):
            reject_extension(root, candidate["id"], "Invalid draft")

        self.assertEqual(before, candidate_path.read_bytes())

    def test_rejection_checks_extensions_root_before_candidate_read(self):
        root, candidate = create_candidate_fixture(self, status="eligible")
        extensions = root / ".sdlc" / "extensions"
        extensions.mkdir()
        real_lstat = Path.lstat

        def mark_extensions_as_reparse(path):
            result = real_lstat(path)
            if path == extensions:
                return types.SimpleNamespace(
                    st_mode=result.st_mode,
                    st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
                )
            return result

        with mock.patch.object(
            Path, "lstat", autospec=True, side_effect=mark_extensions_as_reparse
        ), mock.patch.object(
            adaptive_extensions,
            "_load_candidates",
            side_effect=AssertionError("candidate data was read"),
        ):
            with self.assertRaisesRegex(AdaptiveError, "reparse"):
                reject_extension(root, candidate["id"], "Reject unsafe root")

    def test_rejection_restores_candidate_when_draft_write_fails(self):
        root, candidate = create_candidate_fixture(self, status="eligible")
        extension = root / ".sdlc" / "extensions" / candidate["id"]
        extension.mkdir(parents=True)
        fixture = create_extension_fixture(
            self, id=candidate["id"], status="drafted"
        )
        for source in fixture.iterdir():
            source.replace(extension / source.name)
        candidate_path = root / ".sdlc" / "learning" / "candidates.json"
        metadata_path = extension / "extension.json"
        candidate_before = candidate_path.read_bytes()
        metadata_before = metadata_path.read_bytes()
        real_write = adaptive_extensions.write_json_atomic
        calls = 0

        def fail_second_write(path, value):
            nonlocal calls
            calls += 1
            if calls >= 2:
                raise OSError("injected second write failure")
            return real_write(path, value)

        with mock.patch.object(
            adaptive_extensions,
            "write_json_atomic",
            side_effect=fail_second_write,
        ):
            with self.assertRaisesRegex(
                OSError, "injected second write failure"
            ):
                reject_extension(root, candidate["id"], "Reject draft")

        self.assertEqual(candidate_before, candidate_path.read_bytes())
        self.assertEqual(metadata_before, metadata_path.read_bytes())

    def test_cli_validation_activation_and_rejection(self):
        extension = create_extension_fixture(self)
        root = extension.parents[2]
        validation = self._run_cli(
            "validate-extension",
            "--project-root",
            str(root),
            "--extension",
            extension.name,
        )
        self.assertEqual(extension.name, json.loads(validation.stdout)["id"])
        self.assertNotIn("The generated diff was inspected", validation.stdout)

        activation = self._run_cli(
            "activate",
            "--project-root",
            str(root),
            "--extension",
            extension.name,
        )
        self.assertEqual(
            [".sdlc/config.json"],
            json.loads(activation.stdout)["changedPaths"],
        )

        candidate = record_observation(
            root, observation(explicit_request=True)
        )
        rejection = self._run_cli(
            "reject",
            "--project-root",
            str(root),
            "--candidate",
            candidate["id"],
            "--reason",
            "Existing module covers it",
        )
        self.assertEqual("rejected", json.loads(rejection.stdout)["status"])

    def test_cli_validation_rejects_extension_path_escape(self):
        extension = create_extension_fixture(self)
        result = subprocess.run(
            [
                *PYTHON_NO_BYTECODE,
                str(SCRIPT_DIR / "manage_extensions.py"),
                "validate-extension",
                "--project-root",
                str(extension.parents[2]),
                "--extension",
                "../outside",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("kebab-case", result.stderr)

    def _run_cli(self, *arguments):
        result = subprocess.run(
            [
                *PYTHON_NO_BYTECODE,
                str(SCRIPT_DIR / "manage_extensions.py"),
                *arguments,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        return result


class PromotionTests(unittest.TestCase):
    def test_global_promotion_does_not_activate_project(self):
        root, extension_id = create_accepted_extension_fixture(self)
        global_root = root / "fake-home" / ".sdlc" / "extensions"

        promoted = promote_global(root, extension_id, global_root)

        config = load_project_config(
            root, adaptive_extensions._core_module_names(core_registry())
        )
        self.assertNotIn(extension_id, config["extensions"]["global"])
        self.assertFalse((root / ".sdlc" / "config.json").exists())
        self.assertEqual(global_root / extension_id, promoted)
        self.assertTrue((promoted / "extension.json").is_file())

    def test_global_promotion_validates_before_copying(self):
        root, extension_id = create_accepted_extension_fixture(self)
        extension = root / ".sdlc" / "extensions" / extension_id
        (extension / "scripts").mkdir()
        global_root = root / "fake-home" / ".sdlc" / "extensions"

        with self.assertRaisesRegex(AdaptiveError, "exactly"):
            promote_global(root, extension_id, global_root)

        self.assertFalse(global_root.exists())

    def test_global_promotion_requires_contextual_sanitization(self):
        root, extension_id = create_accepted_extension_fixture(self)
        extension = root / ".sdlc" / "extensions" / extension_id
        candidates_path = root / ".sdlc" / "learning" / "candidates.json"
        candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
        candidates["candidates"][0]["occurrences"][0][
            "task"
        ] = "service-orchid-release"
        candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
        (extension / "MODULE.md").write_text(
            "# Verify output\n\nInspect services/orchid for service-orchid.\n",
            encoding="utf-8",
        )
        global_root = root / "fake-home" / ".sdlc" / "extensions"

        with self.assertRaisesRegex(
            AdaptiveError, "promotion sanitization required"
        ):
            promote_global(root, extension_id, global_root)

        self.assertFalse(global_root.exists())

    def test_global_promotion_records_promoted_lifecycle_state(self):
        root, extension_id = create_accepted_extension_fixture(self)
        global_root = root / "fake-home" / ".sdlc" / "extensions"

        promote_global(root, extension_id, global_root)

        candidate = next(
            item
            for item in load_candidates(root)["candidates"]
            if item["id"] == extension_id
        )
        self.assertEqual("promoted", candidate["status"])
        self.assertEqual("global", candidate["lastDecision"]["kind"])
        self.assertIn("global", candidate["lastDecision"]["reason"])
        self.assertRegex(
            candidate["lastDecision"]["timestamp"],
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
        )

    def test_global_promotion_rolls_back_destination_when_state_write_fails(self):
        root, extension_id = create_accepted_extension_fixture(self)
        global_root = root / "fake-home" / ".sdlc" / "extensions"
        target = global_root / extension_id
        candidate_path = root / ".sdlc" / "learning" / "candidates.json"
        real_write = adaptive_extensions.write_json_atomic

        def fail_candidate_write(path, value):
            if path == candidate_path:
                raise OSError("candidate state unavailable")
            return real_write(path, value)

        with mock.patch.object(
            adaptive_extensions,
            "write_json_atomic",
            side_effect=fail_candidate_write,
        ):
            with self.assertRaisesRegex(OSError, "candidate state unavailable"):
                promote_global(root, extension_id, global_root)

        self.assertFalse(target.exists())
        self.assertEqual(
            "accepted",
            next(
                item
                for item in load_candidates(root)["candidates"]
                if item["id"] == extension_id
            )["status"],
        )

    def test_global_promotion_refuses_differing_overwrite(self):
        root, extension_id = create_accepted_extension_fixture(self)
        global_root = root / "fake-home" / ".sdlc" / "extensions"
        target = promote_global(root, extension_id, global_root)
        (target / "MODULE.md").write_text(
            "# Different\n\nInspect a different artifact.\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(AdaptiveError, "different content"):
            promote_global(root, extension_id, global_root)

    def test_global_promotion_is_idempotent_for_identical_content(self):
        root, extension_id = create_accepted_extension_fixture(self)
        global_root = root / "fake-home" / ".sdlc" / "extensions"

        first = promote_global(root, extension_id, global_root)
        second = promote_global(root, extension_id, global_root)

        self.assertEqual(first, second)

    def test_global_promotion_writes_validated_snapshot_after_source_changes(self):
        root, extension_id = create_accepted_extension_fixture(self)
        extension = root / ".sdlc" / "extensions" / extension_id
        module_path = extension / "MODULE.md"
        validated_content = module_path.read_bytes()
        global_root = root / "fake-home" / ".sdlc" / "extensions"
        real_read_snapshot = adaptive_extensions._read_extension_snapshot

        def mutate_source(path):
            snapshot = real_read_snapshot(path)
            module_path.write_text(
                "# Changed\n\nCopy raw prompt content.\n",
                encoding="utf-8",
            )
            return snapshot

        with mock.patch.object(
            adaptive_extensions,
            "_read_extension_snapshot",
            side_effect=mutate_source,
        ):
            promoted = promote_global(root, extension_id, global_root)

        self.assertEqual(
            validated_content, (promoted / "MODULE.md").read_bytes()
        )

    def test_global_promotion_accepts_identical_concurrent_winner(self):
        root, extension_id = create_accepted_extension_fixture(self)
        extension = root / ".sdlc" / "extensions" / extension_id
        global_root = root / "fake-home" / ".sdlc" / "extensions"
        target = global_root / extension_id
        real_replace = Path.replace

        def install_winner(staging, destination):
            if destination == target:
                target.mkdir(parents=True)
                for source in extension.iterdir():
                    (target / source.name).write_bytes(source.read_bytes())
                raise FileExistsError("concurrent winner")
            return real_replace(staging, destination)

        with mock.patch.object(
            Path, "replace", autospec=True, side_effect=install_winner
        ):
            promoted = promote_global(root, extension_id, global_root)

        self.assertEqual(target, promoted)

    def test_global_promotion_rejects_different_concurrent_winner(self):
        root, extension_id = create_accepted_extension_fixture(self)
        global_root = root / "fake-home" / ".sdlc" / "extensions"
        target = global_root / extension_id
        real_replace = Path.replace

        def install_winner(staging, destination):
            if destination == target:
                target.mkdir(parents=True)
                (target / "MODULE.md").write_text(
                    "# Different\n", encoding="utf-8"
                )
                raise FileExistsError("concurrent winner")
            return real_replace(staging, destination)

        with mock.patch.object(
            Path, "replace", autospec=True, side_effect=install_winner
        ):
            with self.assertRaisesRegex(AdaptiveError, "different content"):
                promote_global(root, extension_id, global_root)

    def test_global_promotion_refuses_non_catalog_destination(self):
        root, extension_id = create_accepted_extension_fixture(self)

        with self.assertRaisesRegex(AdaptiveError, "global extension catalog"):
            promote_global(root, extension_id, root / "skills" / "sdlc")

    def test_global_catalog_cannot_be_inside_installed_core(self):
        installed_core = Path(adaptive_extensions.__file__).resolve().parents[1]

        with self.assertRaisesRegex(AdaptiveError, "installed SDLC core"):
            adaptive_extensions._require_global_catalog(
                installed_core / ".sdlc" / "extensions"
            )

    def test_upstream_package_is_sanitized_and_has_no_side_effect(self):
        root, extension_id = create_accepted_extension_fixture(self)
        candidates_path = root / ".sdlc" / "learning" / "candidates.json"
        candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
        occurrence = candidates["candidates"][0]["occurrences"][0]
        occurrence["task"] = "account-nova-private-release"
        occurrence["signal"] = "Secret repository release was blocked."
        occurrence["evidence"] = ["internal/account-nova/release.log"]
        candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
        git_marker = root / ".git" / "refs" / "heads" / "extension"

        package = prepare_upstream(root, extension_id)

        self.assertEqual(
            root / ".sdlc" / "contributions" / extension_id, package
        )
        self.assertEqual(
            {"proposal.md", "extension.json", "MODULE.md", "evals.json"},
            {path.name for path in package.iterdir()},
        )
        proposal = (package / "proposal.md").read_text(encoding="utf-8")
        for heading in (
            "## Generalized problem",
            "## Why core behavior does not already cover it",
            "## Anonymized occurrence summary",
            "## Proposed category and trigger",
            "## Evidence and exit contract",
            "## Safety review",
            "## Behavior evaluation results",
            "## Compatibility and migration notes",
            "## Recommended disposition",
        ):
            self.assertIn(heading, proposal)
        self.assertIn("1 qualifying occurrence", proposal)
        self.assertNotIn("account-nova", proposal)
        self.assertNotIn("release.log", proposal)
        self.assertNotIn("Secret repository", proposal)
        self.assertFalse(git_marker.exists())

    def test_upstream_preparation_records_promoted_lifecycle_state(self):
        root, extension_id = create_accepted_extension_fixture(self)

        prepare_upstream(root, extension_id)

        candidate = next(
            item
            for item in load_candidates(root)["candidates"]
            if item["id"] == extension_id
        )
        self.assertEqual("promoted", candidate["status"])
        self.assertEqual("upstream", candidate["lastDecision"]["kind"])
        self.assertIn("upstream", candidate["lastDecision"]["reason"])

    def test_upstream_preparation_rolls_back_package_when_state_write_fails(self):
        root, extension_id = create_accepted_extension_fixture(self)
        target = root / ".sdlc" / "contributions" / extension_id
        candidate_path = root / ".sdlc" / "learning" / "candidates.json"
        real_write = adaptive_extensions.write_json_atomic

        def fail_candidate_write(path, value):
            if path == candidate_path:
                raise AdaptiveError("candidate state escaped")
            return real_write(path, value)

        with mock.patch.object(
            adaptive_extensions,
            "write_json_atomic",
            side_effect=fail_candidate_write,
        ):
            with self.assertRaisesRegex(AdaptiveError, "candidate state escaped"):
                prepare_upstream(root, extension_id)

        self.assertFalse(target.exists())
        self.assertEqual(
            "accepted",
            next(
                item
                for item in load_candidates(root)["candidates"]
                if item["id"] == extension_id
            )["status"],
        )

    def test_upstream_preparation_validates_before_writing(self):
        root, extension_id = create_accepted_extension_fixture(self)
        extension = root / ".sdlc" / "extensions" / extension_id
        (extension / "MODULE.md").write_text(
            "# Unsafe\n\nRun curl https://example.invalid.\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(AdaptiveError, "prohibited network"):
            prepare_upstream(root, extension_id)

        self.assertFalse((root / ".sdlc" / "contributions").exists())

    def test_upstream_preparation_rejects_project_specific_extension_content(self):
        cases = (
            (
                "extension.json",
                "candidate task identifier",
                lambda extension, root: self._replace_metadata_value(
                    extension, "trigger", "The task-a workflow recurs."
                ),
            ),
            (
                "MODULE.md",
                "absolute path",
                lambda extension, root: (
                    extension / "MODULE.md"
                ).write_text(
                    "# Verify output\n\nInspect C:\\workspace\\service\\api.py.\n",
                    encoding="utf-8",
                ),
            ),
            (
                "evals.json",
                "project-specific relative path",
                lambda extension, root: self._replace_eval_prompt(
                    extension,
                    "Inspect internal/account-nova/release.py output.",
                ),
            ),
            (
                "MODULE.md",
                "known project identifier",
                self._add_known_project_identifier,
            ),
            (
                "evals.json",
                "candidate evidence reference",
                lambda extension, root: self._replace_eval_prompt(
                    extension, "Inspect tests/test_client.py."
                ),
            ),
        )
        for filename, reason, contaminate in cases:
            with self.subTest(filename=filename, reason=reason):
                root, extension_id = create_accepted_extension_fixture(self)
                extension = root / ".sdlc" / "extensions" / extension_id
                contaminate(extension, root)

                with self.assertRaisesRegex(
                    AdaptiveError,
                    rf"sanitization required.*{re.escape(filename)}.*"
                    rf"{re.escape(reason)}.*developer revision",
                ):
                    prepare_upstream(root, extension_id)

                self.assertFalse(
                    (root / ".sdlc" / "contributions").exists()
                )

    def test_upstream_preparation_rejects_project_root_identifier(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "customerZephyr"
        root.mkdir()
        candidate = record_observation(
            root, observation(explicit_request=True)
        )
        set_candidate_status(
            root, candidate["id"], "drafted", "Draft extension"
        )
        set_candidate_status(
            root, candidate["id"], "accepted", "Approve extension"
        )
        extension = create_extension_at(root, id=candidate["id"])
        (extension / "MODULE.md").write_text(
            "# Verify output\n\nCheck customerZephyr output.\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            AdaptiveError,
            r"sanitization required.*MODULE.md.*known project identifier",
        ):
            prepare_upstream(root, candidate["id"])

        self.assertFalse((root / ".sdlc" / "contributions").exists())

    def test_upstream_preparation_rejects_extensionless_project_path(self):
        cases = (
            "src/config",
            "internal/config",
            "docs/private",
            "path src/config in prose",
        )
        for content in cases:
            with self.subTest(content=content):
                root, extension_id = create_accepted_extension_fixture(self)
                extension = root / ".sdlc" / "extensions" / extension_id
                (extension / "MODULE.md").write_text(
                    f"# Verify output\n\nInspect {content}.\n",
                    encoding="utf-8",
                )

                with self.assertRaisesRegex(
                    AdaptiveError,
                    r"sanitization required.*MODULE.md.*"
                    r"project-specific relative path",
                ):
                    prepare_upstream(root, extension_id)

                self.assertFalse(
                    (root / ".sdlc" / "contributions").exists()
                )

    def test_upstream_preparation_rejects_exact_candidate_identifier(self):
        root, extension_id = create_accepted_extension_fixture(self)
        extension = root / ".sdlc" / "extensions" / extension_id
        (extension / "MODULE.md").write_text(
            "# Verify output\n\nCheck task-a output.\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            AdaptiveError,
            r"sanitization required.*MODULE.md.*candidate task identifier",
        ):
            prepare_upstream(root, extension_id)

    def test_upstream_preparation_allows_identifier_prefix_in_ordinary_word(self):
        root, extension_id = create_accepted_extension_fixture(self)
        extension = root / ".sdlc" / "extensions" / extension_id
        (extension / "MODULE.md").write_text(
            "# Verify output\n\nUse a task-aware review.\n",
            encoding="utf-8",
        )
        expected = (extension / "MODULE.md").read_bytes()

        package = prepare_upstream(root, extension_id)

        self.assertEqual(expected, (package / "MODULE.md").read_bytes())

    def test_upstream_preparation_allows_non_path_slash_tokens(self):
        cases = (
            "https://example.com/path",
            "/help and /skills",
            "version >=1.0.0 <2.0.0",
            "ratio 1/2",
            "phrase input/output",
            "scoped package @org/pkg",
        )
        for content in cases:
            with self.subTest(content=content):
                root, extension_id = create_accepted_extension_fixture(self)
                extension = root / ".sdlc" / "extensions" / extension_id
                (extension / "MODULE.md").write_text(
                    f"# Verify output\n\nDocument {content}.\n",
                    encoding="utf-8",
                )
                expected = (extension / "MODULE.md").read_bytes()

                package = prepare_upstream(root, extension_id)

                self.assertEqual(
                    expected, (package / "MODULE.md").read_bytes()
                )

    def test_upstream_preparation_writes_validated_snapshot_after_source_changes(
        self,
    ):
        root, extension_id = create_accepted_extension_fixture(self)
        extension = root / ".sdlc" / "extensions" / extension_id
        module_path = extension / "MODULE.md"
        validated_content = module_path.read_bytes()
        real_read_snapshot = adaptive_extensions._read_extension_snapshot

        def mutate_source(path):
            snapshot = real_read_snapshot(path)
            module_path.write_text(
                "# Changed\n\nCopy raw prompt content.\n",
                encoding="utf-8",
            )
            return snapshot

        with mock.patch.object(
            adaptive_extensions,
            "_read_extension_snapshot",
            side_effect=mutate_source,
        ):
            package = prepare_upstream(root, extension_id)

        self.assertEqual(
            validated_content, (package / "MODULE.md").read_bytes()
        )

    def test_upstream_proposal_contains_substantive_review_information(self):
        root, extension_id = create_accepted_extension_fixture(self)

        package = prepare_upstream(root, extension_id)

        proposal = (package / "proposal.md").read_text(encoding="utf-8")
        self.assertIn(
            "A public API contract changes.",
            proposal,
        )
        self.assertIn(
            "Generated output is current and inspected.",
            proposal,
        )
        self.assertIn(
            "- The generated diff was inspected.",
            proposal,
        )
        self.assertIn("1 positive and 1 negative", proposal)
        self.assertIn(">=1.0.0 <2.0.0", proposal)
        self.assertIn("Category: `verification`.", proposal)
        self.assertIn("1 qualifying occurrence", proposal)
        self.assertIn("remain an extension example", proposal)
        self.assertNotIn(
            "metadata contains the proposed generalized trigger", proposal
        )
        self.assertNotIn(
            "metadata contains the evidence and exit contract", proposal
        )

    def test_upstream_preparation_refuses_differing_overwrite(self):
        root, extension_id = create_accepted_extension_fixture(self)
        package = prepare_upstream(root, extension_id)
        (package / "proposal.md").write_text("different\n", encoding="utf-8")

        with self.assertRaisesRegex(AdaptiveError, "different content"):
            prepare_upstream(root, extension_id)

    def test_upstream_preparation_rejects_contributions_symlink(self):
        root, extension_id = create_accepted_extension_fixture(self)
        contributions = root / ".sdlc" / "contributions"
        contributions.mkdir()
        real_lstat = Path.lstat

        def mark_contributions_as_reparse(path):
            result = real_lstat(path)
            if path == contributions:
                return types.SimpleNamespace(
                    st_mode=result.st_mode,
                    st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
                )
            return result

        with mock.patch.object(
            Path,
            "lstat",
            autospec=True,
            side_effect=mark_contributions_as_reparse,
        ):
            with self.assertRaisesRegex(AdaptiveError, "reparse"):
                prepare_upstream(root, extension_id)

        self.assertEqual([], list(contributions.iterdir()))

    def test_promotion_commands_are_separate_cli_actions(self):
        root, extension_id = create_accepted_extension_fixture(self)
        global_root = root / "fake-home" / ".sdlc" / "extensions"

        promote = self._run_cli(
            "promote-global",
            "--project-root",
            str(root),
            "--extension",
            extension_id,
            "--global-root",
            str(global_root),
        )
        upstream = self._run_cli(
            "prepare-upstream",
            "--project-root",
            str(root),
            "--extension",
            extension_id,
        )

        self.assertEqual(
            {"path": str(global_root / extension_id)},
            json.loads(promote.stdout),
        )
        self.assertEqual(
            {
                "path": str(
                    root / ".sdlc" / "contributions" / extension_id
                )
            },
            json.loads(upstream.stdout),
        )

    def _run_cli(self, *arguments):
        result = subprocess.run(
            [
                *PYTHON_NO_BYTECODE,
                str(SCRIPT_DIR / "manage_extensions.py"),
                *arguments,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        return result

    def _replace_metadata_value(self, extension, field, value):
        path = extension / "extension.json"
        metadata = json.loads(path.read_text(encoding="utf-8"))
        metadata[field] = value
        path.write_text(json.dumps(metadata), encoding="utf-8")

    def _replace_eval_prompt(self, extension, value):
        path = extension / "evals.json"
        evaluations = json.loads(path.read_text(encoding="utf-8"))
        evaluations["cases"][0]["prompt"] = value
        path.write_text(json.dumps(evaluations), encoding="utf-8")

    def _add_known_project_identifier(self, extension, root):
        candidates_path = root / ".sdlc" / "learning" / "candidates.json"
        candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
        candidates["candidates"][0]["occurrences"][0][
            "task"
        ] = "account-nova-release"
        candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
        (extension / "MODULE.md").write_text(
            "# Verify output\n\nCheck the account-nova release workflow.\n",
            encoding="utf-8",
        )


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "project"
        self.global_root = Path(self.temporary.name) / "home"
        self.root.mkdir()
        self.global_root.mkdir()

    def resolve(self, config, global_root=None):
        return adaptive_extensions.resolve_extensions(
            self.root,
            global_root,
            config,
            "1.0.0",
            core_registry(),
        )

    def test_only_explicitly_enabled_extensions_are_resolved(self):
        create_extension_at(self.root, id="enabled")
        unlisted = create_extension_at(self.root, id="unlisted")
        (unlisted / "MODULE.md").write_text(
            "Run curl https://example.invalid/upload", encoding="utf-8"
        )

        resolved = self.resolve(schema_two_config(project={"enabled": True}))

        self.assertEqual(["enabled"], [item["id"] for item in resolved])
        self.assertEqual("project", resolved[0]["source"])

    def test_resolution_digest_is_bound_to_one_validated_snapshot(self):
        extension = create_extension_at(self.root, id="enabled")
        module_path = extension / "MODULE.md"
        validated_snapshot = adaptive_extensions._read_extension_snapshot(
            extension
        )
        real_validate = adaptive_extensions._validate_extension_snapshot

        def mutate_after_validation(
            extension_dir, snapshot, sdlc_version, registry
        ):
            result = real_validate(
                extension_dir, snapshot, sdlc_version, registry
            )
            module_path.write_text(
                "# Changed\n\nRun curl https://example.invalid/upload.\n",
                encoding="utf-8",
            )
            return result

        with mock.patch.object(
            adaptive_extensions,
            "_validate_extension_snapshot",
            side_effect=mutate_after_validation,
        ):
            resolved = self.resolve(
                schema_two_config(project={"enabled": True})
            )

        self.assertEqual(
            validated_snapshot.digest, resolved[0]["contentDigest"]
        )
        with self.assertRaisesRegex(AdaptiveError, "snapshot changed"):
            load_resolved_module(
                extension,
                resolved[0]["contentDigest"],
                "1.0.0",
                core_registry(),
            )

    def test_resolved_module_loader_returns_validated_snapshot_bytes(self):
        extension = create_extension_at(self.root, id="enabled")
        expected = (extension / "MODULE.md").read_bytes().decode("utf-8")
        resolved = self.resolve(
            schema_two_config(project={"enabled": True})
        )
        real_validate = adaptive_extensions._validate_extension_snapshot

        def mutate_after_validation(
            extension_dir, snapshot, sdlc_version, registry
        ):
            result = real_validate(
                extension_dir, snapshot, sdlc_version, registry
            )
            (extension / "MODULE.md").write_text(
                "# Changed\n\nRun curl https://example.invalid/upload.\n",
                encoding="utf-8",
            )
            return result

        with mock.patch.object(
            adaptive_extensions,
            "_validate_extension_snapshot",
            side_effect=mutate_after_validation,
        ):
            module = load_resolved_module(
                extension,
                resolved[0]["contentDigest"],
                "1.0.0",
                core_registry(),
            )

        self.assertEqual(expected, module)
    def test_global_extension_requires_project_opt_in(self):
        create_extension_at(self.global_root, id="global-check")

        resolved = self.resolve(
            schema_two_config(global_extensions={}), self.global_root
        )

        self.assertEqual([], resolved)

    def test_false_entries_are_reported_without_reading_module(self):
        project_extension = create_extension_at(
            self.root, id="project-disabled"
        )
        global_extension = create_extension_at(
            self.global_root, id="global-disabled"
        )
        (project_extension / "MODULE.md").unlink()
        (global_extension / "MODULE.md").unlink()

        resolved = self.resolve(
            schema_two_config(
                project={"project-disabled": False},
                global_extensions={"global-disabled": False},
            ),
            self.global_root,
        )

        self.assertEqual(
            [
                {
                    "id": "project-disabled",
                    "source": "project",
                    "coverageStatus": "configured-disabled",
                },
                {
                    "id": "global-disabled",
                    "source": "global",
                    "coverageStatus": "configured-disabled",
                },
            ],
            resolved,
        )

    def test_invalid_configured_id_is_rejected_before_path_read(self):
        with mock.patch.object(
            Path,
            "lstat",
            side_effect=AssertionError("extension path was inspected"),
        ):
            with self.assertRaisesRegex(AdaptiveError, "kebab-case"):
                self.resolve(schema_two_config(project={"../escape": False}))

    def test_enabled_extension_path_escape_is_rejected_before_file_read(self):
        extension = create_extension_at(self.root, id="escaped")
        real_resolve = Path.resolve

        def escape_extension(path, strict=False):
            if path == extension:
                return self.root.parent / "outside" / extension.name
            return real_resolve(path, strict=strict)

        with mock.patch.object(
            Path, "resolve", autospec=True, side_effect=escape_extension
        ), mock.patch.object(
            Path,
            "iterdir",
            side_effect=AssertionError("extension files were read"),
        ):
            with self.assertRaisesRegex(AdaptiveError, "escapes"):
                self.resolve(schema_two_config(project={"escaped": True}))

    def test_incompatible_extension_is_rejected(self):
        create_extension_at(
            self.root, id="future-only", compatibleSdlc=">=2.0.0"
        )

        with self.assertRaisesRegex(AdaptiveError, "not compatible"):
            self.resolve(
                schema_two_config(project={"future-only": True})
            )

    def test_duplicate_id_with_different_content_is_rejected(self):
        create_extension_at(self.root, id="same-id")
        global_extension = create_extension_at(
            self.global_root, id="same-id"
        )
        (global_extension / "MODULE.md").write_text(
            "# Same ID\n\nInspect a different artifact.\n", encoding="utf-8"
        )
        config = schema_two_config(
            project={"same-id": True},
            global_extensions={"same-id": True},
        )

        with self.assertRaisesRegex(AdaptiveError, "conflicting extension"):
            self.resolve(config, self.global_root)

    def test_identical_duplicate_id_is_deduplicated(self):
        project_extension = create_extension_at(self.root, id="same-id")
        global_extension = create_extension_at(
            self.global_root, id="same-id"
        )
        for name in ("extension.json", "MODULE.md", "evals.json"):
            (global_extension / name).write_bytes(
                (project_extension / name).read_bytes()
            )

        resolved = self.resolve(
            schema_two_config(
                project={"same-id": True},
                global_extensions={"same-id": True},
            ),
            self.global_root,
        )

        self.assertEqual(1, len(resolved))
        self.assertEqual(["project", "global"], resolved[0]["sources"])

    def test_same_trigger_in_different_categories_is_rejected(self):
        create_extension_at(
            self.root,
            id="verify-contract",
            category="verification",
            trigger="A public API contract changes.",
        )
        create_extension_at(
            self.root,
            id="plan-contract",
            category="planning",
            trigger="A public API contract changes.",
        )

        with self.assertRaisesRegex(AdaptiveError, "trigger conflict"):
            self.resolve(
                schema_two_config(
                    project={
                        "verify-contract": True,
                        "plan-contract": True,
                    }
                )
            )

    def test_extension_trigger_conflicting_with_core_category_is_rejected(self):
        create_extension_at(
            self.root,
            id="verify-contract",
            category="verification",
            trigger="A public API contract changes.",
        )
        registry = {
            "schemaVersion": 1,
            "modules": [
                {
                    "name": "planning",
                    "category": "planning",
                    "trigger": "A public API contract changes.",
                }
            ],
        }

        with self.assertRaisesRegex(AdaptiveError, "trigger conflict"):
            adaptive_extensions.resolve_extensions(
                self.root,
                None,
                schema_two_config(project={"verify-contract": True}),
                "1.0.0",
                registry,
            )

    def test_core_trigger_in_different_categories_is_rejected(self):
        registry = {
            "schemaVersion": 1,
            "modules": [
                {
                    "name": "planning",
                    "category": "planning",
                    "trigger": "A public API contract changes.",
                },
                {
                    "name": "testing",
                    "category": "verification",
                    "trigger": "a PUBLIC api contract   changes.",
                },
            ],
        }

        with self.assertRaisesRegex(AdaptiveError, "core trigger conflict"):
            adaptive_extensions.resolve_extensions(
                self.root,
                None,
                schema_two_config(),
                "1.0.0",
                registry,
            )

    def test_core_trigger_in_same_category_is_allowed_when_semantically_equal(
        self,
    ):
        # Normalized trigger plus category is the structural conflict model.
        # Equivalent classifications are safe because neither changes routing.
        registry = {
            "schemaVersion": 1,
            "modules": [
                {
                    "name": "unit-testing",
                    "category": "verification",
                    "trigger": "Behavior changes.",
                },
                {
                    "name": "integration-testing",
                    "category": "verification",
                    "trigger": "behavior   CHANGES.",
                },
            ],
        }

        self.assertEqual(
            [],
            adaptive_extensions.resolve_extensions(
                self.root,
                None,
                schema_two_config(),
                "1.0.0",
                registry,
            ),
        )

    def test_resolve_cli_validates_registry_before_loading_config(self):
        stderr = io.StringIO()
        with mock.patch.object(
            manage_extensions,
            "_installed_context",
            return_value=(
                "1.0.0",
                {"schemaVersion": 1, "modules": [{"name": "Invalid"}]},
            ),
        ), mock.patch.object(
            manage_extensions,
            "load_project_config",
            side_effect=AssertionError("config was loaded"),
        ) as load_config:
            with contextlib.redirect_stderr(stderr):
                result = manage_extensions.main(
                    ["resolve", "--project-root", str(self.root)]
                )

        self.assertEqual(2, result)
        self.assertIn("kebab-case", stderr.getvalue())
        load_config.assert_not_called()

    def test_resolve_cli_outputs_public_metadata(self):
        create_extension_at(self.root, id="enabled")
        config_path = self.root / ".sdlc" / "config.json"
        config_path.write_text(
            json.dumps(schema_two_config(project={"enabled": True})),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                *PYTHON_NO_BYTECODE,
                str(SCRIPT_DIR / "manage_extensions.py"),
                "resolve",
                "--project-root",
                str(self.root),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        resolved = json.loads(result.stdout)
        self.assertEqual("enabled", resolved[0]["id"])
        self.assertNotIn(str(self.root), result.stdout)

    def test_load_module_cli_requires_and_consumes_resolved_digest(self):
        extension = create_extension_at(self.root, id="enabled")
        expected = (extension / "MODULE.md").read_bytes().decode("utf-8")
        resolved = self.resolve(
            schema_two_config(project={"enabled": True})
        )

        result = subprocess.run(
            [
                *PYTHON_NO_BYTECODE,
                str(SCRIPT_DIR / "manage_extensions.py"),
                "load-module",
                "--project-root",
                str(self.root),
                "--extension",
                "enabled",
                "--source",
                "project",
                "--expected-digest",
                resolved[0]["contentDigest"],
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(expected, json.loads(result.stdout)["module"])


class ContinuousImprovementContractTests(unittest.TestCase):
    def test_core_update_triggers_approval_only_supersession_assessment(self):
        repository_root = Path(__file__).resolve().parents[1]
        declaration = json.loads(
            (
                repository_root
                / "skills"
                / "sdlc"
                / "modules"
                / "sdlc-continuous-improvement"
                / "sdlc-capability.json"
            ).read_text(encoding="utf-8")
        )
        module = (
            repository_root
            / "skills"
            / "sdlc"
            / "modules"
            / "sdlc-continuous-improvement"
            / "SKILL.md"
        ).read_text(encoding="utf-8")
        trigger = declaration["trigger"]

        self.assertIn("upgrade", trigger.casefold())
        for required in (
            "accepted extensions",
            "core responsibilities",
            "propose",
            "rationale",
            "explicit developer approval",
            "never delete",
            "never disable",
        ):
            self.assertIn(required, module.casefold())
