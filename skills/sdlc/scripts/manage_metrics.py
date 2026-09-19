#!/usr/bin/env python3

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from adaptive_extensions import AdaptiveError, load_json_strict
import config_contract
from config_contract import ConfigError, normalize_config


class MetricsError(ValueError):
    pass


SCHEMA_VERSION = 1
MAX_COUNTER = (1 << 63) - 1
MAX_STORE_BYTES = 65_536
LOCK_TIMEOUT_SECONDS = 1.0
LOCK_RETRY_SECONDS = 0.025
COUNTER_EVENTS = (
    "module.enabled",
    "module.triggered",
    "module.loaded",
    "module.reused",
    "module.disabled",
    "evidence.reused",
    "evidence.refreshed",
    "clarification.asked",
    "clarification.avoidedByEvidence",
    "extension.observed",
    "extension.accepted",
    "extension.rejected",
    "extension.promoted",
    "extension.superseded",
    "report.concise",
    "report.normal",
    "report.detailed",
)
PHASES = (
    "configuration",
    "evidence-assessment",
    "module-execution",
    "verification",
    "handoff",
)
DURATION_UPPER_BOUNDS_MS = (
    1_000,
    10_000,
    60_000,
    600_000,
    3_600_000,
    86_400_000,
)
_REPARSE_POINT_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def zero_store(generation=1):
    if type(generation) is not int or generation < 1 or generation > MAX_COUNTER:
        raise MetricsError("generation must be a positive bounded integer")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generation": generation,
        "counters": {event: 0 for event in COUNTER_EVENTS},
        "phaseDurations": {
            phase: {"count": 0, "bucketsMs": [0, 0, 0, 0, 0, 0]}
            for phase in PHASES
        },
    }


def _is_link_or_reparse(path):
    metadata = path.lstat()
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0)
        & _REPARSE_POINT_ATTRIBUTE
    )


def _verify_existing_components(root, candidate):
    resolved_root = root.resolve(strict=True)
    lexical = Path(os.path.abspath(candidate))
    lexical_root = Path(os.path.abspath(root))
    try:
        lexical.relative_to(lexical_root)
    except ValueError as error:
        raise MetricsError("metrics path escapes the project boundary") from error
    current = lexical_root
    for part in lexical.relative_to(lexical_root).parts:
        current = current / part
        if not current.exists() and not current.is_symlink():
            break
        if _is_link_or_reparse(current):
            raise MetricsError("metrics path contains a link or reparse point")
    try:
        resolved = lexical.resolve(strict=False)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as error:
        raise MetricsError("metrics path escapes the project boundary") from error
    return lexical


def _run_git(root, arguments, capture=False):
    executable = shutil.which("git")
    if executable is None:
        raise MetricsError("ignore-verification-unavailable")
    try:
        return subprocess.run(
            [executable, "--no-optional-locks", "-C", str(root), *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=3,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise MetricsError("ignore-verification-unavailable") from error


def _local_metrics_are_ignored(root):
    result = _run_git(
        root,
        [
            "check-ignore",
            "--no-index",
            "--quiet",
            "--",
            ".sdlc/local/metrics.json",
        ],
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise MetricsError("ignore-verification-unavailable")


def _valid_gitfile_project(root, git):
    if not git.is_file() or _is_link_or_reparse(git):
        return False
    try:
        if git.stat().st_size > 4096:
            return False
        marker = git.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    if not marker.startswith("gitdir: ") or "\x00" in marker:
        return False
    result = _run_git(root, ["rev-parse", "--show-toplevel"], capture=True)
    if result.returncode != 0:
        return False
    try:
        return Path(result.stdout.strip()).resolve(strict=True) == root
    except (OSError, ValueError):
        return False


def locate_store(project_root, require_safe=True):
    root = Path(project_root)
    if not root.is_dir():
        raise MetricsError("project root must be an existing directory")
    root = root.resolve(strict=True)
    git = root / ".git"
    if git.is_dir() and not _is_link_or_reparse(git):
        path = git / "sdlc" / "metrics.json"
        category = "git-local"
    elif git.exists() or git.is_symlink():
        if not _valid_gitfile_project(root, git):
            raise MetricsError("git-metadata-unsupported")
        path = root / ".sdlc" / "local" / "metrics.json"
        category = "gitfile-local"
        if require_safe and not _local_metrics_are_ignored(root):
            raise MetricsError("local-store-not-ignored")
    else:
        path = root / ".sdlc" / "local" / "metrics.json"
        category = "non-git-local"
        if require_safe and not _local_metrics_are_ignored(root):
            raise MetricsError("local-store-not-ignored")
    return root, _verify_existing_components(root, path), category


def _registry_value():
    path = Path(__file__).resolve().parent.parent / "modules" / "registry.json"
    return load_json_strict(path)


def _registry_names():
    value = _registry_value()
    return {
        item["name"]
        for item in value.get("modules", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def _phase_index():
    try:
        return config_contract.phase_index(_registry_value())
    except ConfigError:
        return None


def measurement_enabled(project_root):
    root = Path(project_root).resolve(strict=True)
    path = root / ".sdlc" / "config.json"
    if not path.is_file():
        return False
    if _is_link_or_reparse(path):
        raise MetricsError("project config must not be a link or reparse point")
    try:
        config = normalize_config(
            load_json_strict(path), _registry_names(), _phase_index()
        )
    except (AdaptiveError, ConfigError) as error:
        raise MetricsError(str(error)) from error
    return config["measurement"]["enabled"]


def _write_config_atomic(path, value):
    temporary_path = None
    original_mode = stat.S_IMODE(path.stat().st_mode)
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        )
        temporary_path = Path(temporary_name)
        os.chmod(temporary_path, original_mode)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def configure_measurement(project_root, enabled):
    if type(enabled) is not bool:
        raise MetricsError("measurement-enabled-must-be-boolean")
    root = Path(project_root).resolve(strict=True)
    config_path = _verify_existing_components(
        root, root / ".sdlc" / "config.json"
    )
    if not config_path.is_file() or _is_link_or_reparse(config_path):
        raise MetricsError("config-unavailable")
    _, store_path, _ = locate_store(root, require_safe=enabled)
    with _store_lock(store_path):
        try:
            original = load_json_strict(config_path)
            phase_of = _phase_index()
            normalized = normalize_config(
                original, _registry_names(), phase_of
            )
        except (AdaptiveError, ConfigError) as error:
            raise MetricsError("config-invalid") from error
        current = normalized["measurement"]["enabled"]
        if current == enabled:
            return {"enabled": enabled, "changed": False}
        if original["schemaVersion"] == 1:
            normalized["measurement"] = {"enabled": enabled}
            updated = config_contract.config_to_document(normalized, phase_of)
        else:
            updated = dict(original)
            updated["measurement"] = {"enabled": enabled}
        _write_config_atomic(config_path, updated)
    return {"enabled": enabled, "changed": True}


def _bounded_integer(value, field, minimum=0):
    if type(value) is not int or value < minimum or value > MAX_COUNTER:
        raise MetricsError(f"{field} must be an integer from {minimum} to {MAX_COUNTER}")
    return value


def _validate_store_integer(value, minimum=0):
    if type(value) is not int or value < minimum or value > MAX_COUNTER:
        raise MetricsError("store-corrupt:invalid-value")


def validate_store(value):
    if not isinstance(value, dict) or set(value) != {
        "schemaVersion",
        "generation",
        "counters",
        "phaseDurations",
    }:
        raise MetricsError("store-corrupt:invalid-shape")
    if (
        type(value["schemaVersion"]) is not int
        or value["schemaVersion"] != SCHEMA_VERSION
    ):
        raise MetricsError("store-corrupt:unsupported-schema")
    _validate_store_integer(value["generation"], 1)
    counters = value["counters"]
    if not isinstance(counters, dict) or set(counters) != set(COUNTER_EVENTS):
        raise MetricsError("store-corrupt:invalid-counter-keys")
    for count in counters.values():
        _validate_store_integer(count)
    phases = value["phaseDurations"]
    if not isinstance(phases, dict) or set(phases) != set(PHASES):
        raise MetricsError("store-corrupt:invalid-phase-keys")
    for phase, observation in phases.items():
        if not isinstance(observation, dict) or set(observation) != {
            "count",
            "bucketsMs",
        }:
            raise MetricsError("store-corrupt:invalid-phase-shape")
        _validate_store_integer(observation["count"])
        buckets = observation["bucketsMs"]
        if not isinstance(buckets, list) or len(buckets) != 6:
            raise MetricsError("store-corrupt:invalid-buckets")
        for count in buckets:
            _validate_store_integer(count)
        if sum(buckets) != observation["count"]:
            raise MetricsError("store-corrupt:inconsistent-histogram")
    return value


def read_store(path):
    if not path.is_file():
        raise MetricsError("store-unavailable:absent")
    if _is_link_or_reparse(path):
        raise MetricsError("store-invalid-path:link")
    if path.stat().st_size > MAX_STORE_BYTES:
        raise MetricsError("store-corrupt:too-large")
    try:
        value = load_json_strict(path)
    except AdaptiveError as error:
        raise MetricsError("store-corrupt:invalid-json") from error
    except UnicodeError as error:
        raise MetricsError("store-corrupt:invalid-encoding") from error
    except OSError as error:
        raise MetricsError("store-unavailable:read-failed") from error
    return validate_store(value)


def _increment(value):
    return min(MAX_COUNTER, value + 1)


def _write_atomic(path, value):
    validate_store(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        )
        temporary_path = Path(temporary_name)
        os.chmod(temporary_path, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


@contextmanager
def _store_lock(path):
    lock = path.with_suffix(".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    descriptor = None
    while descriptor is None:
        try:
            descriptor = os.open(
                lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
        except FileExistsError as error:
            if time.monotonic() >= deadline:
                raise MetricsError("metrics store lock is busy") from error
            time.sleep(LOCK_RETRY_SECONDS)
    try:
        yield
    finally:
        os.close(descriptor)
        lock.unlink(missing_ok=True)
        try:
            lock.parent.rmdir()
        except OSError:
            pass


def record_event(project_root, event, duration_ms=None):
    if event not in COUNTER_EVENTS and not (
        event.startswith("phase.") and event[6:] in PHASES
    ):
        raise MetricsError("event is not in the closed measurement enum")
    is_phase = event.startswith("phase.")
    if is_phase:
        _bounded_integer(duration_ms, "duration-ms")
    elif duration_ms is not None:
        raise MetricsError("duration-ms is valid only for phase events")
    if not measurement_enabled(project_root):
        return {"status": "disabled", "written": False}
    _, path, _ = locate_store(project_root)
    with _store_lock(path):
        if not measurement_enabled(project_root):
            return {"status": "disabled", "written": False}
        value = read_store(path) if path.exists() else zero_store()
        if is_phase:
            phase = event[6:]
            observation = value["phaseDurations"][phase]
            if observation["count"] < MAX_COUNTER:
                observation["count"] += 1
                bucket = next(
                    (
                        index
                        for index, upper in enumerate(DURATION_UPPER_BOUNDS_MS)
                        if duration_ms <= upper
                    ),
                    len(DURATION_UPPER_BOUNDS_MS) - 1,
                )
                observation["bucketsMs"][bucket] += 1
        else:
            value["counters"][event] = _increment(value["counters"][event])
        _write_atomic(path, value)
    return value


def record_optional_phase(project_root, phase, operation):
    if phase not in PHASES:
        raise MetricsError("phase is not in the closed measurement enum")
    try:
        started = time.monotonic()
    except Exception:
        return operation()
    result = operation()
    try:
        elapsed = time.monotonic() - started
        if elapsed < 0:
            return result
        record_event(project_root, f"phase.{phase}", int(elapsed * 1000))
    except Exception:
        pass
    return result


def status(project_root):
    enabled = measurement_enabled(project_root)
    _, path, category = locate_store(project_root, require_safe=False)
    exists = path.is_file()
    generation = read_store(path)["generation"] if exists else None
    return {
        "enabled": enabled,
        "storeCategory": category,
        "schemaVersion": SCHEMA_VERSION if exists else None,
        "generation": generation,
        "dataExists": exists,
    }


def inspect_store(project_root):
    _, path, _ = locate_store(project_root, require_safe=False)
    return read_store(path)


def reset_store(project_root):
    _, path, _ = locate_store(project_root, require_safe=False)
    with _store_lock(path):
        current = read_store(path)
        generation = _increment(current["generation"])
        if generation == current["generation"]:
            raise MetricsError("generation cannot increment beyond the bounded maximum")
        value = zero_store(generation)
        _write_atomic(path, value)
    return value


def delete_store(project_root):
    _, path, _ = locate_store(project_root, require_safe=False)
    if not path.exists():
        return {"status": "absent", "deleted": False}
    if _is_link_or_reparse(path):
        raise MetricsError("store-invalid-path:link")
    with _store_lock(path):
        path.unlink(missing_ok=True)
    try:
        path.parent.rmdir()
    except OSError:
        pass
    return {"status": "deleted", "deleted": True}


def _parser():
    parser = argparse.ArgumentParser(
        description="Manage private project-local SDLC aggregate measurement."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "inspect", "reset", "delete"):
        command = commands.add_parser(name)
        command.add_argument("--project-root", required=True)
        if name == "inspect":
            command.add_argument("--json", action="store_true")
    configure = commands.add_parser("configure")
    configure.add_argument("--project-root", required=True)
    configure.add_argument("--enabled", choices=("true", "false"), required=True)
    record = commands.add_parser("record")
    record.add_argument("--project-root", required=True)
    record.add_argument("--event", required=True)
    record.add_argument("--duration-ms", type=int)
    return parser


def main(argv=None):
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "status":
            value = status(arguments.project_root)
        elif arguments.command == "inspect":
            value = inspect_store(arguments.project_root)
        elif arguments.command == "record":
            value = record_event(
                arguments.project_root, arguments.event, arguments.duration_ms
            )
        elif arguments.command == "reset":
            value = reset_store(arguments.project_root)
        elif arguments.command == "configure":
            value = configure_measurement(
                arguments.project_root, arguments.enabled == "true"
            )
        else:
            value = delete_store(arguments.project_root)
        print(json.dumps(value, sort_keys=True, indent=2))
        return 0
    except (MetricsError, AdaptiveError, ConfigError, UnicodeError) as error:
        if arguments.command == "inspect":
            print(json.dumps({"status": "unavailable", "reason": str(error)}))
        print(f"error: {error}", file=sys.stderr)
        return 2
    except OSError:
        reason = "operation-failed"
        if arguments.command == "inspect":
            print(json.dumps({"status": "unavailable", "reason": reason}))
        print(f"error: {reason}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
