#!/usr/bin/env python3

import json
import re
import sys
import tempfile
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath


ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
SKILL = ROOT / "skills" / "sdlc" / "SKILL.md"
MODULES = ROOT / "skills" / "sdlc" / "modules"
SKILL_SCRIPTS = SKILL.parent / "scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

import adaptive_extensions
import qualify


DOMAIN_MODULE_CASES = {
    "accessibility-browser": {
        "a11y-browser-dialog-flow-positive",
        "a11y-browser-backend-only-negative",
        "a11y-browser-email-counterexample",
        "a11y-browser-release-pressure",
    },
    "performance-concurrency": {
        "perf-cache-hot-path-positive",
        "perf-cold-refactor-negative",
        "perf-test-parallelism-counterexample",
        "perf-racy-deadline-pressure",
    },
    "observability": {
        "obs-queue-boundary-positive",
        "obs-pure-library-negative",
        "obs-existing-rollout-signals-counterexample",
        "obs-log-everything-pressure",
    },
    "api-compatibility": {
        "api-error-shape-positive",
        "api-private-helper-negative",
        "api-storage-schema-counterexample",
        "api-breaking-deadline-pressure",
    },
    "data-migration": {
        "migration-live-backfill-positive",
        "migration-test-fixture-negative",
        "migration-additive-column-counterexample",
        "migration-destructive-pressure",
    },
    "dependency-supply-chain": {
        "supply-new-package-positive",
        "supply-existing-import-negative",
        "supply-first-party-counterexample",
        "supply-emergency-update-pressure",
    },
}
DOMAIN_MODULE_CASE_IDS = set().union(*DOMAIN_MODULE_CASES.values())
DOMAIN_MODULE_SECTIONS = (
    "Bounded responsibility",
    "Positive trigger",
    "Non-trigger counterexamples",
    "Evidence contract",
    "Overlap rules",
    "Right-sizing",
    "Steps",
    "Exit",
    "Common shortcuts to reject",
    "Behavioral cases",
)
REQUIRED_HELPERS = {
    "adaptive_extensions.py",
    "artifact_contracts.py",
    "config_contract.py",
    "handoff_renderers.py",
    "manage_extensions.py",
    "manage_metrics.py",
    "operator_reports.py",
    "reconcile_artifacts.py",
    "resolve_providers.py",
    "validate_artifacts.py",
}
REQUIRED_CONTRACTS = {
    "handoff-result.schema.json",
    "handoff.schema.json",
    "metrics.schema.json",
    "operator-result.schema.json",
    "operator-state.schema.json",
    "plan-result.schema.json",
    "prd-result.schema.json",
    "provider-adapter.schema.json",
    "provider-adapter-load.schema.json",
    "provider-inspection.schema.json",
    "provider-load-result.schema.json",
    "provider-resolution.schema.json",
    "reconciliation-report.schema.json",
    "sdlc-config.schema.json",
}
SECRET_LIKE_KEY = re.compile(
    r"(?:authorization|credential|password|passwd|secret|token|api[_-]?key)",
    re.IGNORECASE,
)
SECRET_LIKE_ASSIGNMENT = re.compile(
    r"(?:[\"']?(?:authorization|credential|password|passwd|secret|token|"
    r"api[_-]?key)[\"']?\s*[:=])",
    re.IGNORECASE,
)
URL_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
PATH_TOKEN_SEPARATOR = re.compile(r"""[\s()\[\]{}<>,;"'`]+""")
SLASH_COMMAND_PATTERN = re.compile(r"^/[A-Za-z][A-Za-z0-9-]*$")
EXTENSION_BUNDLE_PATH = re.compile(
    r"^(?P<catalog>\.sdlc/extensions|global-extensions)/"
    r"(?P<identifier>[a-z0-9]+(?:-[a-z0-9]+)*)/"
    r"(?P<filename>[^/\\]+)$"
)
EXPECTED_EVALUATION_FIELDS = {
    "id",
    "category",
    "prompt",
    "expected",
    "forbidden",
}
EXPECTED_BEHAVIOR_FIELDS = {"id", "description", "critical"}
REQUIRED_PRD_SECTIONS = {
    "## Problem and context",
    "## Target users and benefit",
    "## Outcome",
    "## Goals",
    "## Non-goals",
    "## User scenarios",
    "## Functional requirements",
    "## Acceptance criteria",
    "## Data, permissions, privacy, and security",
    "## Constraints and dependencies",
    "## Success measures",
    "## Open decisions",
    "## Approval",
}
DISALLOWED_PUBLIC_REFERENCE_TOKENS = {
    "super" + "powers",
    "open" + "spec",
    "spec-driven-" + "development",
}


def fail(message: str) -> None:
    raise ValueError(message)


def load_json_strict_text(text: str, source: str):
    def reject_duplicate_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                fail(f"Duplicate JSON key in {source}: {key}")
            result[key] = value
        return result

    def reject_non_finite(value):
        fail(f"Invalid JSON constant in {source}: {value}")

    return json.loads(
        text,
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_non_finite,
    )


def load_json_strict_path(path: Path):
    try:
        source = str(path.relative_to(ROOT))
    except ValueError:
        source = str(path)
    try:
        return load_json_strict_text(path.read_text(encoding="utf-8"), source)
    except UnicodeError as error:
        fail(f"Invalid UTF-8 in {source}: {error}")


def is_absolute_path_token(token: str) -> bool:
    if not token or URL_PATTERN.match(token):
        return False
    if token.startswith(("/*", "*/")):
        return False
    if SLASH_COMMAND_PATTERN.fullmatch(token):
        return False
    return (
        token.startswith(("~/", "~\\", "/", "\\"))
        or PurePosixPath(token).is_absolute()
        or PureWindowsPath(token).is_absolute()
    )


def contains_absolute_path(value: str) -> bool:
    for raw_token in PATH_TOKEN_SEPARATOR.split(value):
        token = raw_token.rstrip(".:!?")
        if is_absolute_path_token(token):
            return True
        if URL_PATTERN.match(token):
            continue
        if "=" in token and is_absolute_path_token(token.split("=", 1)[1]):
            return True
    return False


def validate_fixture_path(value: str, source: str) -> None:
    if not isinstance(value, str) or not value:
        fail(f"Evaluation fixture path must be a non-empty string: {source}")
    if contains_absolute_path(value):
        fail(f"absolute evaluation fixture path in {source}: {value}")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if "." in path.parts or ".." in path.parts or str(path) != normalized:
        fail(f"Unsafe evaluation fixture path in {source}: {value}")


def validate_fixture_value(value, source: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if SECRET_LIKE_KEY.search(str(key)):
                fail(f"Secret-like key in evaluation fixture {source}: {key}")
            if contains_absolute_path(str(key)):
                fail(f"absolute path key in evaluation fixture {source}: {key}")
            validate_fixture_value(child, source)
    elif isinstance(value, list):
        for child in value:
            validate_fixture_value(child, source)
    elif isinstance(value, str):
        if contains_absolute_path(value):
            fail(f"absolute path value in evaluation fixture {source}")
        if SECRET_LIKE_ASSIGNMENT.search(value):
            fail(f"Secret-like key in evaluation fixture {source}")


def validate_case_schema(case) -> None:
    if not isinstance(case, dict):
        fail("Evaluation case must be an object")
    allowed_fields = EXPECTED_EVALUATION_FIELDS | {
        "fixture",
        "repository",
        "links",
    }
    if (
        not set(case) <= allowed_fields
        or not EXPECTED_EVALUATION_FIELDS <= set(case)
    ):
        fail(f"Invalid evaluation case fields: {case.get('id')}")
    if not all(
        isinstance(case.get(field), str) and case[field]
        for field in ("id", "category", "prompt")
    ):
        fail(f"Invalid evaluation case strings: {case.get('id')}")
    expected = case.get("expected")
    if not isinstance(expected, list) or not expected:
        fail(f"Evaluation case requires expected behaviors: {case['id']}")
    for behavior in expected:
        if (
            not isinstance(behavior, dict)
            or set(behavior) != EXPECTED_BEHAVIOR_FIELDS
            or not isinstance(behavior.get("id"), str)
            or not behavior["id"]
            or not isinstance(behavior.get("description"), str)
            or not behavior["description"]
            or type(behavior.get("critical")) is not bool
        ):
            fail(f"Invalid expected behavior in evaluation case: {case['id']}")
    forbidden = case.get("forbidden")
    if (
        not isinstance(forbidden, list)
        or not forbidden
        or any(not isinstance(item, str) or not item for item in forbidden)
    ):
        fail(f"Invalid forbidden behavior in evaluation case: {case['id']}")
    repository = case.get("repository")
    if repository is not None:
        if (
            not isinstance(repository, dict)
            or set(repository) != {"initializeGit", "commitFixture"}
            or type(repository.get("initializeGit")) is not bool
            or type(repository.get("commitFixture")) is not bool
            or repository["commitFixture"] and not repository["initializeGit"]
        ):
            fail(f"Invalid repository fixture metadata: {case['id']}")
    links = case.get("links")
    if links is not None:
        if not isinstance(links, list) or not links:
            fail(f"Evaluation links must be a non-empty list: {case['id']}")
        for link in links:
            if (
                not isinstance(link, dict)
                or set(link)
                != {"path", "target", "targetScope", "kind"}
                or link.get("targetScope") != "outside-project"
                or link.get("kind") != "directory"
            ):
                fail(f"Invalid evaluation link metadata: {case['id']}")
            validate_fixture_path(link.get("path"), case["id"])
            validate_fixture_path(link.get("target"), case["id"])


def validate_prd_fixture(content: str, source: str) -> None:
    if not isinstance(content, str) or not content.startswith("---\n"):
        return
    parts = content.split("---", 2)
    if len(parts) != 3 or "type: prd" not in parts[1]:
        return
    if source.startswith("prd-deterministic-validation:"):
        return
    frontmatter = parts[1]
    identifier = re.search(r"^id:\s*([a-z0-9]+(?:-[a-z0-9]+)*)$", frontmatter, re.M)
    status = re.search(r"^status:\s*(draft|approved|superseded)$", frontmatter, re.M)
    version = re.search(r"^version:\s*([1-9][0-9]*)$", frontmatter, re.M)
    if not identifier or not status or not version:
        fail(f"Invalid PRD fixture identity: {source}")
    if status.group(1) == "approved":
        missing = sorted(section for section in REQUIRED_PRD_SECTIONS if section not in content)
        if missing:
            fail(f"Approved PRD fixture is incomplete in {source}: {missing}")


def validate_config_fixture(config, case_id: str, registry_names: set[str]) -> None:
    if case_id == "invalid-module-configuration":
        try:
            adaptive_extensions.normalize_config(config, registry_names)
        except adaptive_extensions.AdaptiveError:
            return
        fail("Invalid-module configuration fixture must remain invalid")
    if case_id in ADAPTIVE_CASE_IDS and config.get("schemaVersion") != 2:
        fail(f"Adaptive config fixture must use schema 2: {case_id}")
    adaptive_extensions.normalize_config(config, registry_names)


def validate_candidates_fixture(content: str, case_id: str) -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / ".sdlc" / "learning" / "candidates.json"
        path.parent.mkdir(parents=True)
        path.write_text(content, encoding="utf-8")
        try:
            adaptive_extensions.load_candidates(root)
        except adaptive_extensions.AdaptiveError as error:
            fail(f"Invalid candidates schema in {case_id}: {error}")


def validate_extension_bundles(
    fixture: dict, case_id: str, registry: dict, sdlc_version: str
) -> None:
    bundles = {}
    for fixture_path, content in fixture.items():
        normalized = fixture_path.replace("\\", "/")
        if normalized.startswith((".sdlc/extensions/", "global-extensions/")):
            match = EXTENSION_BUNDLE_PATH.fullmatch(normalized)
            if match is None:
                label = (
                    "global catalog layout"
                    if normalized.startswith("global-extensions/")
                    else "extension bundle layout"
                )
                fail(f"Invalid {label} in {case_id}: {fixture_path}")
            key = (match["catalog"], match["identifier"])
            bundles.setdefault(key, {})[match["filename"]] = content

    required_files = {"extension.json", "MODULE.md", "evals.json"}
    for (catalog, identifier), files in bundles.items():
        if set(files) != required_files:
            fail(
                f"Extension bundle must contain exactly {sorted(required_files)} "
                f"in {case_id}:{catalog}/{identifier}"
            )
        with tempfile.TemporaryDirectory() as directory:
            extension = (
                Path(directory)
                / ".sdlc"
                / "extensions"
                / identifier
            )
            extension.mkdir(parents=True)
            for filename, content in files.items():
                if not isinstance(content, str):
                    fail(
                        f"Extension bundle file must contain text: "
                        f"{case_id}:{filename}"
                    )
                (extension / filename).write_text(content, encoding="utf-8")
            try:
                adaptive_extensions.validate_extension(
                    extension, sdlc_version, registry
                )
            except adaptive_extensions.AdaptiveError as error:
                fail(f"Invalid extension bundle in {case_id}: {error}")


def validate_skill() -> None:
    skill_files = list((ROOT / "skills").glob("**/SKILL.md"))
    if skill_files != [SKILL]:
        fail(f"Expected only {SKILL.relative_to(ROOT)}, found {skill_files}")

    text = SKILL.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        fail("SKILL.md is missing opening frontmatter")
    _, frontmatter, _ = text.split("---", 2)
    if len(frontmatter) > 1024:
        fail("SKILL.md frontmatter exceeds 1024 characters")
    if not re.search(r"^name:\s+sdlc$", frontmatter, re.MULTILINE):
        fail("SKILL.md name must be sdlc")
    if not re.search(r"^description:\s+['\"]?Use when ", frontmatter, re.MULTILINE):
        fail("SKILL.md description must start with 'Use when'")

    registry = load_json_strict_path(MODULES / "registry.json")
    if (
        type(registry.get("schemaVersion")) is not int
        or registry["schemaVersion"] != 1
    ):
        fail("Module registry must use schemaVersion 1")
    entries = registry.get("modules")
    if not isinstance(entries, list) or not entries:
        fail("Module registry must contain modules")

    names = [entry.get("name") for entry in entries]
    orders = [entry.get("order") for entry in entries]
    if len(names) != len(set(names)) or len(orders) != len(set(orders)):
        fail("Module names and order values must be unique")
    if sorted(orders) != list(range(len(entries))):
        fail("Module order values must be contiguous from zero")

    registered = set(names)

    if "continuous-improvement" not in registered:
        fail("Module registry must contain continuous-improvement")
    if "tdd" not in registered:
        fail("Module registry must contain tdd")
    if names.index("tdd") + 1 != names.index("implementation"):
        fail("TDD must immediately precede implementation")
    for entry in entries:
        for field in ("name", "category", "path", "trigger", "exitSignal"):
            if not entry.get(field):
                fail(f"Module registry entry is missing {field}: {entry}")
        if not isinstance(entry.get("evidence"), list) or not entry["evidence"]:
            fail(f"Module evidence contract is missing: {entry['name']}")
        validate_fixture_path(entry["path"], f"module {entry['name']}")
        path = PurePosixPath(entry["path"].replace("\\", "/"))
        if len(path.parts) != 2:
            fail(f"Unsafe module path: {entry['path']}")
        resolved = MODULES.joinpath(*path.parts)
        if not resolved.is_file() or resolved.name != "MODULE.md":
            fail(f"Registered module file not found: {entry['path']}")
        if resolved.parent.name != entry["name"]:
            fail(f"Module path/name mismatch: {entry['name']}")
        if entry["name"] in DOMAIN_MODULE_CASES:
            validate_domain_module_contract(
                entry["name"],
                resolved.read_text(encoding="utf-8"),
                DOMAIN_MODULE_CASES[entry["name"]],
            )

    available = {path.parent.name for path in MODULES.glob("*/MODULE.md")}
    if registered != available:
        fail(
            "Module registry mismatch: "
            f"missing={sorted(available - registered)}, "
            f"unknown={sorted(registered - available)}"
        )
    if "project-memory" in registered:
        memory_templates = (
            MODULES / "project-memory" / "assets" / "project-memory-templates"
        )
        required_templates = {
            "active-context.md",
            "architecture.md",
            "decisions-log.md",
            "do-and-dont.md",
            "glossary.md",
            "project-brief.md",
        }
        available_templates = {path.name for path in memory_templates.glob("*.md")}
        if available_templates != required_templates:
            fail("Project-memory template set is incomplete")
    if "prd" in registered:
        prd_template = MODULES / "prd" / "assets" / "PRD.template.md"
        if not prd_template.is_file():
            fail("PRD template is missing")
        prd_text = prd_template.read_text(encoding="utf-8")
        required_prd_identity = (
            "type: prd",
            "id: feature-id",
            "status: draft",
            "version: 1",
        )
        required_prd_sections = (
            "## Problem and context",
            "## Target users and benefit",
            "## Outcome",
            "## Goals",
            "## Non-goals",
            "## User scenarios",
            "## Functional requirements",
            "## Acceptance criteria",
            "## Data, permissions, privacy, and security",
            "## Constraints and dependencies",
            "## Success measures",
            "## Open decisions",
            "## Approval",
        )
        if any(item not in prd_text for item in required_prd_identity):
            fail("PRD template identity is incomplete")
        if any(section not in prd_text for section in required_prd_sections):
            fail("PRD template sections are incomplete")

    config_template = load_json_strict_path(
        SKILL.parent / "assets" / "sdlc-config.template.json"
    )
    if (
        type(config_template.get("schemaVersion")) is not int
        or config_template["schemaVersion"] != 3
    ):
        fail("SDLC config template must use schemaVersion 3")
    configured_modules = config_template.get("modules")
    if not isinstance(configured_modules, dict):
        fail("SDLC config template modules must be an object")
    if set(configured_modules) != registered:
        fail("SDLC config template must list every registered module")
    if any(value is not True for value in configured_modules.values()):
        fail("Every module must be enabled in the default config template")
    if config_template.get("extensions") != {"project": {}, "global": {}}:
        fail("SDLC config template extensions must default to disabled")
    if config_template.get("measurement") != {"enabled": False}:
        fail("SDLC measurement must default to disabled")

    scripts = SKILL.parent / "scripts"
    missing_helpers = sorted(
        name for name in REQUIRED_HELPERS if not (scripts / name).is_file()
    )
    if missing_helpers:
        fail(f"Bundled helper or CLI missing: {missing_helpers}")
    contracts = SKILL.parent / "contracts"
    missing_contracts = sorted(
        name for name in REQUIRED_CONTRACTS if not (contracts / name).is_file()
    )
    if missing_contracts:
        fail(f"Bundled contract missing: {missing_contracts}")
    for name in sorted(REQUIRED_CONTRACTS):
        schema = load_json_strict_path(contracts / name)
        if (
            not isinstance(schema, dict)
            or schema.get("$schema")
            != "https://json-schema.org/draft/2020-12/schema"
            or schema.get("type") != "object"
            or schema.get("additionalProperties") is not False
        ):
            fail(f"Invalid strict JSON Schema contract: {name}")
    renderer_source = (scripts / "handoff_renderers.py").read_text(
        encoding="utf-8"
    ).lower()
    forbidden_renderer_tokens = (
        "import requests",
        "import subprocess",
        "import socket",
        "import urllib",
        "github.",
        "gitlab.",
        "azure.devops",
        "selenium",
        "playwright",
        "os.environ",
        "getenv(",
    )
    for token in forbidden_renderer_tokens:
        if token in renderer_source:
            fail(f"Renderer contains prohibited dependency or access: {token}")
    reconciliation_source = (scripts / "reconcile_artifacts.py").read_text(
        encoding="utf-8"
    ).lower()
    for token in (
        "import requests",
        "import socket",
        "import urllib",
        "http.client",
        "subprocess",
        "urlopen",
        "os.environ",
        "getenv(",
    ):
        if token in reconciliation_source:
            fail(
                "Reconciliation helper contains prohibited dependency or access: "
                f"{token}"
            )
    metrics_source = (scripts / "manage_metrics.py").read_text(
        encoding="utf-8"
    ).lower()
    for token in (
        "import requests",
        "import socket",
        "import urllib",
        "http.client",
        "telemetry",
        "analytics",
        "upload",
        "export",
        "os.environ",
        "getenv(",
    ):
        if token in metrics_source:
            fail(
                "Local measurement helper contains prohibited dependency or access: "
                f"{token}"
            )
    for token in (
        '"check-ignore"',
        '"--no-index"',
        '"--quiet"',
        '".sdlc/local/metrics.json"',
        '"configure"',
    ):
        if token not in metrics_source:
            fail(
                "Local measurement helper must verify the exact ignored store: "
                f"{token}"
            )
    provider_source = (scripts / "resolve_providers.py").read_text(
        encoding="utf-8"
    ).lower()
    for token in (
        "import requests",
        "import socket",
        "import urllib",
        "import importlib",
        "http.client",
        "subprocess",
        "os.environ",
        "getenv(",
        "--host-adapter",
    ):
        if token in provider_source:
            fail(
                "Provider helper contains prohibited dependency or access: "
                f"{token}"
            )
    for token in (
        "provider-unavailable",
        "provider-ambiguous",
        "provider-resolution-unsupported",
        "provider-digest-mismatch",
        "provider-unloadable",
        "readinessauthority",
    ):
        if token not in provider_source:
            fail(f"Provider helper is missing fail-closed contract: {token}")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for command in (
        "explain",
        "preview",
        "validate-prd",
        "validate-plan",
        "validate-handoff",
        "render-coverage",
        "render-handoff",
    ):
        if f"validate_artifacts.py {command}" not in readme:
            fail(f"README command documentation missing: {command}")


def validate_manifests() -> None:
    plugin = load_json_strict_path(ROOT / ".claude-plugin" / "plugin.json")
    marketplace = load_json_strict_path(
        ROOT / ".claude-plugin" / "marketplace.json"
    )
    if plugin.get("skills") != ["./skills/sdlc"]:
        fail("Claude plugin must ship only ./skills/sdlc")
    skill_text = SKILL.read_text(encoding="utf-8")
    version_match = re.search(r'^  version:\s+"([^"]+)"$', skill_text, re.MULTILINE)
    marketplace_plugins = marketplace.get("plugins")
    marketplace_version = (
        marketplace_plugins[0].get("version")
        if isinstance(marketplace_plugins, list) and len(marketplace_plugins) == 1
        else None
    )
    if (
        not version_match
        or plugin.get("version") != version_match.group(1)
        or marketplace_version != version_match.group(1)
    ):
        fail("Plugin manifest versions must match the SDLC skill version")

    qualification_manifest = qualify.load_json_strict(
        ROOT / "qualification" / "manifest.json"
    )
    qualification_manifest = qualify.validate_manifest(
        qualification_manifest, ROOT
    )
    if qualification_manifest["release"] != version_match.group(1):
        fail("Qualification manifest version must match the SDLC skill")
    for result_path in sorted(
        (ROOT / "qualification" / "results").glob("*/*.json")
    ):
        qualify.validate_result(
            qualify.load_json_strict(result_path), qualification_manifest
        )


def validate_domain_module_contract(
    module_name: str, text: str, expected_case_ids
) -> None:
    for section in DOMAIN_MODULE_SECTIONS:
        if f"## {section}" not in text:
            fail(f"Domain module {module_name} is missing section: {section}")
    case_rows = re.findall(
        r"^\| `([^`]+)` \| (positive|negative|counterexample|pressure) \|",
        text,
        re.MULTILINE,
    )
    case_ids = {case_id for case_id, _ in case_rows}
    case_types = {case_type for _, case_type in case_rows}
    if case_ids != set(expected_case_ids) or case_types != {
        "positive",
        "negative",
        "counterexample",
        "pressure",
    }:
        fail(f"Domain module {module_name} behavioral cases are incomplete")


def validate_release_32_case_coverage(case_ids) -> None:
    if not DOMAIN_MODULE_CASE_IDS.issubset(set(case_ids)):
        fail("Domain-module validation coverage is incomplete")


def validate_markdown() -> None:
    markdown_files = [
        ROOT / "README.md",
        ROOT / "AGENTS.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "CONTEXT.md",
        *(ROOT / "docs").glob("**/*.md"),
        *SKILL.parent.glob("**/*.md"),
        *(ROOT / "qualification").glob("**/*.md"),
    ]
    link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for path in markdown_files:
        text = path.read_text(encoding="utf-8")
        if "\u2014" in text:
            fail(f"Em dash found in {path.relative_to(ROOT)}")
        for target in link_pattern.findall(text):
            if target.startswith(("http://", "https://", "#")):
                continue
            relative_target = target.split("#", 1)[0]
            if relative_target and not (path.parent / relative_target).exists():
                fail(
                    f"Broken link in {path.relative_to(ROOT)}: {relative_target}"
                )


def validate_public_naming() -> None:
    roots = (
        ROOT / ".claude-plugin",
        ROOT / "docs",
        ROOT / "scripts",
        ROOT / "skills",
        ROOT / "tests",
        ROOT / "qualification",
    )
    files = [
        ROOT / "README.md",
        ROOT / "AGENTS.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "CONTEXT.md",
    ]
    text_suffixes = {
        ".json",
        ".md",
        ".ps1",
        ".py",
        ".sh",
        ".yaml",
        ".yml",
    }
    for root in roots:
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in text_suffixes
        )
    for path in files:
        relative = path.relative_to(ROOT).as_posix().lower()
        text = path.read_text(encoding="utf-8").lower()
        for reference in DISALLOWED_PUBLIC_REFERENCE_TOKENS:
            if reference in relative or reference in text:
                fail(
                    "Disallowed public reference found in "
                    f"{path.relative_to(ROOT)}"
                )


def main() -> int:
    try:
        validate_skill()
        validate_manifests()
        validate_markdown()
        validate_public_naming()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"VALIDATION FAILED: {error}", file=sys.stderr)
        return 1

    module_count = len(list(MODULES.glob("*/MODULE.md")))
    print(f"VALIDATION PASSED: 1 skill, {module_count} modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
