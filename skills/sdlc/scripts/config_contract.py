"""Strict SDLC project configuration parsing and schema migration."""

import json
import os
import re
import stat
import tempfile
from pathlib import Path


class ConfigError(ValueError):
    pass


_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_REPARSE_POINT_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _duplicate_rejecting_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json_strict(path):
    try:
        content = Path(path).read_text(encoding="utf-8")
        return json.loads(
            content,
            object_pairs_hook=_duplicate_rejecting_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ConfigError(f"invalid JSON constant: {value}")
            ),
        )
    except ConfigError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ConfigError(f"cannot read project config: {error}") from error


def _boolean_map(value, field):
    if not isinstance(value, dict):
        raise ConfigError(f"{field} must be an object")
    result = {}
    for name, enabled in value.items():
        if not isinstance(name, str):
            raise ConfigError(f"{field} names must be strings")
        if type(enabled) is not bool:
            raise ConfigError(f"{field}.{name} must be boolean")
        result[name] = enabled
    return result


def _replacement(value, field):
    if not isinstance(value, dict) or set(value) != {"replaceWith"}:
        raise ConfigError(
            f"{field} must be boolean or an object containing only replaceWith"
        )
    provider = value["replaceWith"]
    if (
        not isinstance(provider, str)
        or len(provider) > 64
        or not _ID_PATTERN.fullmatch(provider)
    ):
        raise ConfigError(
            f"{field}.replaceWith must be a lowercase kebab-case skill ID"
        )
    return {"replaceWith": provider}


def normalize_config(config, registry_names):
    if not isinstance(config, dict):
        raise ConfigError("config must be an object")
    version = config.get("schemaVersion")
    if type(version) is not int or version not in (1, 2, 3):
        raise ConfigError(f"unsupported schema version: {version}")

    allowed = {"schemaVersion", "modules"}
    if version >= 2:
        allowed.update({"extensions", "measurement"})
    unknown = set(config) - allowed
    if unknown:
        raise ConfigError(f"unknown config field: {sorted(unknown)[0]}")

    modules = config.get("modules")
    if not isinstance(modules, dict):
        raise ConfigError("modules must be an object")
    known = set(registry_names)
    unknown_modules = set(modules) - known
    if unknown_modules:
        raise ConfigError(
            f"unknown core module: {sorted(unknown_modules)[0]}"
        )

    normalized_modules = {}
    assignments = {}
    for name in sorted(known):
        value = modules.get(name, True)
        if type(value) is bool:
            normalized_modules[name] = value
        elif version == 3:
            replacement = _replacement(value, f"modules.{name}")
            provider = replacement["replaceWith"]
            if provider == "sdlc" or provider in known:
                raise ConfigError(
                    f"modules.{name}.replaceWith creates a provider cycle"
                )
            if provider in assignments:
                raise ConfigError(
                    f"provider {provider} is assigned to both "
                    f"{assignments[provider]} and {name}"
                )
            assignments[provider] = name
            normalized_modules[name] = replacement
        else:
            raise ConfigError(f"modules.{name} must be boolean")

    extensions = {"project": {}, "global": {}}
    if version >= 2:
        supplied = config.get("extensions")
        if not isinstance(supplied, dict):
            raise ConfigError("extensions must be an object")
        unknown_scopes = set(supplied) - {"project", "global"}
        if unknown_scopes:
            raise ConfigError(
                f"unknown extensions field: {sorted(unknown_scopes)[0]}"
            )
        for scope in ("project", "global"):
            extensions[scope] = _boolean_map(
                supplied.get(scope), f"extensions.{scope}"
            )

    measurement = config.get("measurement", {"enabled": False})
    if not isinstance(measurement, dict):
        raise ConfigError("measurement must be an object")
    if set(measurement) != {"enabled"}:
        unknown_measurement = set(measurement) - {"enabled"}
        if unknown_measurement:
            raise ConfigError(
                "unknown measurement field: "
                f"{sorted(unknown_measurement)[0]}"
            )
        raise ConfigError("measurement.enabled is required")
    if type(measurement["enabled"]) is not bool:
        raise ConfigError("measurement.enabled must be boolean")

    return {
        "schemaVersion": 3,
        "modules": normalized_modules,
        "extensions": extensions,
        "measurement": {"enabled": measurement["enabled"]},
    }


def _is_link_or_reparse(path):
    metadata = path.lstat()
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0)
        & _REPARSE_POINT_ATTRIBUTE
    )


def _validate_config_path(project_root, path):
    root = Path(project_root).resolve(strict=True)
    lexical_root = Path(os.path.abspath(project_root))
    lexical = Path(os.path.abspath(path))
    try:
        parts = lexical.relative_to(lexical_root).parts
    except ValueError as error:
        raise ConfigError("project config escapes project root") from error
    current = lexical_root
    for part in parts:
        current /= part
        if not current.exists() and not current.is_symlink():
            break
        if _is_link_or_reparse(current):
            raise ConfigError("project config contains a link or reparse point")
    try:
        lexical.resolve(strict=False).relative_to(root)
    except (OSError, ValueError) as error:
        raise ConfigError("project config escapes project root") from error


def write_json_atomic(path, value):
    path = Path(path)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(value, temporary, indent=2)
            temporary.write("\n")
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def load_project_config(project_root, registry_names):
    root = Path(project_root)
    if not root.is_dir():
        raise ConfigError("project root must be an existing directory")
    path = root / ".sdlc" / "config.json"
    if not path.exists() and not path.is_symlink():
        return normalize_config(
            {"schemaVersion": 1, "modules": {}}, registry_names
        )
    _validate_config_path(root, path)
    original = load_json_strict(path)
    normalized = normalize_config(original, registry_names)
    if normalized != original:
        write_json_atomic(path, normalized)
    return normalized
