#!/usr/bin/env python3
"""Resolve and load exact, digest-bound SDLC module instruction providers."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from config_contract import (
    ConfigError,
    load_json_strict,
    load_project_config,
)
from adaptive_extensions import version_satisfies


class ProviderError(ValueError):
    pass


_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_PROFILE_IDS = {"copilot-vscode", "claude-code", "generic-agent-skills"}
_PROVIDER_METADATA = {
    "sdlc-provider-schema",
    "sdlc-compatible",
    "sdlc-modules",
}
_LOAD_STATUSES = {"partial", "missing", "stale/unverified"}
_EVIDENCE_STATUSES = _LOAD_STATUSES | {
    "satisfied",
    "configured-disabled",
    "not-applicable",
}
_MAX_SKILL_BYTES = 2 * 1024 * 1024
_LOAD_FAILURES = {
    "revoked": "provider-load-revoked",
    "token-unknown": "provider-load-token-unknown",
    "token-replayed": "provider-load-token-replayed",
    "unloadable": "provider-unloadable",
}


def _error(failure_class, module, provider, profile, remediation):
    raise ProviderError(
        f"{failure_class}: module={module}; provider={provider}; "
        f"hostProfile={profile}; remediation={remediation}"
    )


def _registry_names(registry):
    if not isinstance(registry, dict) or not isinstance(
        registry.get("modules"), list
    ):
        raise ProviderError("provider-registry-invalid")
    names = []
    for module in registry["modules"]:
        if not isinstance(module, dict) or not isinstance(
            module.get("name"), str
        ):
            raise ProviderError("provider-registry-invalid")
        names.append(module["name"])
    if len(names) != len(set(names)):
        raise ProviderError("provider-registry-invalid")
    return set(names)


def module_provider(config, module):
    state = config["modules"][module]
    if state is False:
        return {"type": "disabled", "id": None}
    if state is True:
        return {"type": "bundled", "id": None}
    return {"type": "replacement", "id": state["replaceWith"]}


def _validate_adapter(adapter):
    if not isinstance(adapter, dict):
        raise ProviderError("provider-resolution-unsupported")
    if set(adapter) != {"schemaVersion", "hostProfile", "candidates"}:
        raise ProviderError("provider-adapter-invalid")
    if adapter["schemaVersion"] != 1:
        raise ProviderError("provider-adapter-invalid")
    profile = adapter["hostProfile"]
    if profile not in _PROFILE_IDS:
        raise ProviderError("provider-adapter-invalid")
    candidates = adapter["candidates"]
    if not isinstance(candidates, list):
        raise ProviderError("provider-adapter-invalid")
    for candidate in candidates:
        if not isinstance(candidate, dict) or set(candidate) != {
            "declaredName",
            "providerMetadata",
            "contentDigest",
            "loadToken",
        }:
            raise ProviderError("provider-adapter-invalid")
        if (
            not isinstance(candidate["declaredName"], str)
            or not _ID_PATTERN.fullmatch(candidate["declaredName"])
            or not isinstance(candidate["providerMetadata"], dict)
            or not isinstance(candidate["contentDigest"], str)
            or not isinstance(candidate["loadToken"], str)
            or not candidate["loadToken"]
        ):
            raise ProviderError("provider-adapter-invalid")
        if not _DIGEST_PATTERN.fullmatch(candidate["contentDigest"]):
            raise ProviderError("provider-adapter-invalid")
        if any(
            character in candidate["loadToken"] for character in "\r\n\x00"
        ):
            raise ProviderError("provider-adapter-invalid")
    return profile, candidates


def _frontmatter(content, module, provider, profile):
    try:
        text = content.decode("utf-8")
    except UnicodeError:
        _error(
            "provider-manifest-invalid", module, provider, profile,
            "repair UTF-8 Agent Skill frontmatter",
        )
    if not text.startswith("---\n"):
        _error(
            "provider-manifest-invalid", module, provider, profile,
            "add valid Agent Skill frontmatter",
        )
    end = text.find("\n---\n", 4)
    if end < 0:
        _error(
            "provider-manifest-invalid", module, provider, profile,
            "close Agent Skill frontmatter",
        )
    top = {}
    metadata = {}
    in_metadata = False
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line == "metadata:":
            if "metadata" in top:
                _error(
                    "provider-manifest-invalid", module, provider, profile,
                    "remove duplicate frontmatter keys",
                )
            top["metadata"] = metadata
            in_metadata = True
            continue
        target = metadata if in_metadata and line.startswith("  ") else top
        if in_metadata and not line.startswith("  "):
            in_metadata = False
            target = top
        source = line[2:] if target is metadata else line
        if ":" not in source:
            _error(
                "provider-manifest-invalid", module, provider, profile,
                "use scalar Agent Skill frontmatter values",
            )
        key, value = source.split(":", 1)
        key, value = key.strip(), value.strip()
        if not key or key in target or not value:
            _error(
                "provider-manifest-invalid", module, provider, profile,
                "repair duplicate or empty frontmatter fields",
            )
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in "\"'"
        ):
            value = value[1:-1]
        target[key] = value
    name = top.get("name")
    description = top.get("description")
    if (
        not isinstance(name, str)
        or not name
        or not isinstance(description, str)
        or not description
    ):
        _error(
            "provider-manifest-invalid", module, provider, profile,
            "repair Agent Skill name and description",
        )
    return name, metadata, text[end + 5:]


def _validate_provider_metadata(
    declared_name, metadata, module, provider, profile, sdlc_version
):
    if declared_name != provider:
        _error(
            "provider-identity-mismatch", module, provider, profile,
            "make declared skill name exactly match configured provider ID",
        )
    if not isinstance(metadata, dict):
        _error(
            "provider-metadata-invalid", module, provider, profile,
            "expose provider metadata independently of instructions",
        )
    if any(
        not isinstance(key, str)
        or not isinstance(value, str)
        or not value
        for key, value in metadata.items()
    ):
        _error(
            "provider-metadata-invalid", module, provider, profile,
            "expose non-empty string provider metadata values",
        )
    unknown = {
        key for key in metadata
        if key.startswith("sdlc-") and key not in _PROVIDER_METADATA
    }
    if unknown or set(metadata) & _PROVIDER_METADATA != _PROVIDER_METADATA:
        _error(
            "provider-metadata-invalid", module, provider, profile,
            "declare only the required supported sdlc provider metadata",
        )
    if metadata["sdlc-provider-schema"] != "1":
        _error(
            "provider-metadata-invalid", module, provider, profile,
            "use sdlc-provider-schema 1",
        )
    try:
        compatible = version_satisfies(
            sdlc_version, metadata["sdlc-compatible"]
        )
    except ValueError:
        compatible = False
    if not compatible:
        _error(
            "provider-incompatible", module, provider, profile,
            f"install a provider compatible with SDLC {sdlc_version}",
        )
    supported = [item.strip() for item in metadata["sdlc-modules"].split(",")]
    if (
        not supported
        or len(supported) != len(set(supported))
        or any(not _ID_PATTERN.fullmatch(item) for item in supported)
    ):
        _error(
            "provider-metadata-invalid", module, provider, profile,
            "declare a comma-separated unique core module list",
        )
    if module not in supported:
        _error(
            "provider-module-unsupported", module, provider, profile,
            "install a provider that declares this core module",
        )


def resolve(
    config,
    registry_modules,
    adapter,
    sdlc_version,
    host_profile=None,
):
    registry = {"modules": registry_modules}
    core_names = _registry_names(registry)
    replacements = {
        module: value["replaceWith"]
        for module, value in config["modules"].items()
        if isinstance(value, dict)
    }
    if not replacements:
        return {
            "schemaVersion": 1,
            "hostProfile": host_profile,
            "providers": {},
        }
    if adapter is None:
        profile = host_profile or "unknown"
        module, provider = next(iter(replacements.items()))
        _error(
            "provider-resolution-unsupported", module, provider, profile,
            "use a host adapter that enumerates exact IDs and binds loading",
        )
    profile, candidates = _validate_adapter(adapter)
    if host_profile is not None and profile != host_profile:
        raise ProviderError("provider-adapter-invalid")

    providers = {}
    for module in sorted(replacements, key=lambda item: (
        next(
            index for index, row in enumerate(registry_modules)
            if row["name"] == item
        )
    )):
        provider = replacements[module]
        if module not in core_names:
            _error(
                "provider-module-unknown", module, provider, profile,
                "remove the unknown core module replacement",
            )
        matches = [
            candidate for candidate in candidates
            if candidate["declaredName"] == provider
        ]
        if not matches:
            _error(
                "provider-unavailable", module, provider, profile,
                "install exactly one skill with the configured ID",
            )
        if len(matches) > 1:
            _error(
                "provider-ambiguous", module, provider, profile,
                "remove duplicate installed candidates",
            )
        candidate = matches[0]
        _validate_provider_metadata(
            candidate["declaredName"],
            candidate["providerMetadata"],
            module,
            provider,
            profile,
            sdlc_version,
        )
        providers[module] = {
            "id": provider,
            "hostProfile": profile,
            "providerMetadata": candidate["providerMetadata"],
            "contentDigest": candidate["contentDigest"],
            "loadToken": candidate["loadToken"],
        }
    return {
        "schemaVersion": 1,
        "hostProfile": profile,
        "providers": providers,
    }


def inspect_module(
    module, binding, trigger, evidence_status, recognized_evidence, gaps
):
    if trigger not in {"matched", "not-matched", "undetermined"}:
        raise ProviderError("provider-inspection-invalid")
    if evidence_status not in _EVIDENCE_STATUSES:
        raise ProviderError("provider-inspection-invalid")
    if not isinstance(recognized_evidence, list) or not all(
        isinstance(item, str) and item for item in recognized_evidence
    ):
        raise ProviderError("provider-inspection-invalid")
    if not isinstance(gaps, list) or not all(
        isinstance(item, str) and item for item in gaps
    ):
        raise ProviderError("provider-inspection-invalid")
    if (
        evidence_status == "configured-disabled"
        or evidence_status in {"satisfied", "not-applicable"} and gaps
        or evidence_status in _LOAD_STATUSES and not gaps
        or trigger == "not-matched" and evidence_status != "not-applicable"
        or trigger == "matched" and evidence_status == "not-applicable"
    ):
        raise ProviderError("provider-inspection-invalid")
    load_required = trigger == "matched" and evidence_status in _LOAD_STATUSES
    if evidence_status == "satisfied":
        action = "reused"
    elif trigger == "not-matched" or evidence_status == "not-applicable":
        action = "skipped"
    elif load_required:
        action = "would-load"
    else:
        action = "blocked"
    return {
        "module": module,
        "provider": {"type": "replacement", "id": binding["id"]},
        "status": evidence_status,
        "recognizedEvidence": recognized_evidence,
        "gaps": gaps,
        "action": action,
        "loadRequired": load_required,
        "bindingDigest": binding["contentDigest"],
    }


def load_module(
    binding,
    inspection,
    registry_module,
    adapter_load,
    orchestration_context,
):
    required = {"name", "trigger", "exitSignal", "evidence"}
    if (
        not isinstance(registry_module, dict)
        or set(registry_module) < required
        or not isinstance(registry_module["evidence"], list)
    ):
        raise ProviderError("provider-registry-invalid")
    module = registry_module.get("name")
    provider = binding.get("id")
    profile = binding.get("hostProfile")
    if (
        inspection.get("module") != module
        or inspection.get("provider") != {
            "type": "replacement", "id": provider
        }
        or inspection.get("bindingDigest") != binding.get("contentDigest")
        or not inspection.get("loadRequired")
    ):
        _error(
            "provider-load-not-authorized", module, provider, profile,
            "evaluate the core trigger and evidence gap before loading",
        )
    if not callable(adapter_load):
        _error(
            "provider-resolution-unsupported", module, provider, profile,
            "load through a host adapter that consumes opaque tokens",
        )
    try:
        adapter_result = adapter_load(binding.get("loadToken"))
    except OSError:
        _error(
            "provider-unloadable", module, provider, profile,
            "repair the installed provider and retry through the host adapter",
        )
    if not isinstance(adapter_result, dict):
        raise ProviderError("provider-adapter-load-invalid")
    status = adapter_result.get("status")
    expected_fields = {"schemaVersion", "hostProfile", "status"}
    if status == "loaded":
        expected_fields.add("snapshot")
    if (
        set(adapter_result) != expected_fields
        or adapter_result.get("schemaVersion") != 1
        or adapter_result.get("hostProfile") != profile
    ):
        raise ProviderError("provider-adapter-load-invalid")
    if status in _LOAD_FAILURES:
        _error(
            _LOAD_FAILURES[status], module, provider, profile,
            "resolve again or repair the provider installation",
        )
    if (
        status != "loaded"
        or not isinstance(adapter_result.get("snapshot"), dict)
    ):
        raise ProviderError("provider-adapter-load-invalid")
    snapshot = adapter_result["snapshot"]
    if set(snapshot) != {
        "declaredName", "providerMetadata", "contentDigest", "content"
    }:
        raise ProviderError("provider-adapter-load-invalid")
    if (
        not isinstance(snapshot["declaredName"], str)
        or not isinstance(snapshot["providerMetadata"], dict)
        or not isinstance(snapshot["contentDigest"], str)
        or not isinstance(snapshot["content"], str)
    ):
        raise ProviderError("provider-adapter-load-invalid")
    content = snapshot["content"].encode("utf-8")
    if len(content) > _MAX_SKILL_BYTES:
        _error(
            "provider-unloadable", module, provider, profile,
            "reduce the provider instruction snapshot size",
        )
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    if (
        not _DIGEST_PATTERN.fullmatch(snapshot["contentDigest"])
        or digest != snapshot["contentDigest"]
        or digest != binding.get("contentDigest")
    ):
        _error(
            "provider-digest-mismatch", module, provider, profile,
            "resolve the provider again; bundled fallback is forbidden",
        )
    if snapshot["declaredName"] != provider:
        _error(
            "provider-identity-mismatch", module, provider, profile,
            "resolve the exact declared provider identity again",
        )
    if snapshot["providerMetadata"] != binding.get("providerMetadata"):
        _error(
            "provider-metadata-invalid", module, provider, profile,
            "resolve changed provider metadata again",
        )
    if not isinstance(orchestration_context, dict) or set(
        orchestration_context
    ) != {"changeContract", "projectStandards", "projectMemory"}:
        _error(
            "provider-context-invalid", module, provider, profile,
            "supply current change contract, standards, and memory context",
        )
    declared_name, provider_metadata, instructions = _frontmatter(
        content, module, provider, profile
    )
    if declared_name != snapshot["declaredName"]:
        _error(
            "provider-identity-mismatch", module, provider, profile,
            "return a snapshot matching the adapter-declared identity",
        )
    if provider_metadata != snapshot["providerMetadata"]:
        _error(
            "provider-metadata-invalid", module, provider, profile,
            "return a snapshot matching the adapter-declared metadata",
        )
    if not instructions.strip():
        _error(
            "provider-instructions-empty", module, provider, profile,
            "install a provider with a non-empty instruction body",
        )
    return {
        "schemaVersion": 1,
        "module": module,
        "provider": {"type": "replacement", "id": provider},
        "contentDigest": digest,
        "action": "loaded replacement; core evidence requires reclassification",
        "instructions": instructions,
        "context": {
            "coreTrigger": registry_module["trigger"],
            "coreExitSignal": registry_module["exitSignal"],
            "coreEvidence": registry_module["evidence"],
            "recognizedEvidence": inspection["recognizedEvidence"],
            "gaps": inspection["gaps"],
            "readinessAuthority": "orchestrator",
            "changeContract": orchestration_context["changeContract"],
            "projectStandards": orchestration_context["projectStandards"],
            "projectMemory": orchestration_context["projectMemory"],
        },
    }


def _emit(value):
    print(json.dumps(value, indent=2, sort_keys=True))


def _host_adapter_method(host_adapter, method_name):
    method = getattr(host_adapter, method_name, None)
    if not callable(method):
        raise ProviderError("provider-resolution-unsupported")
    return method


def main(argv=None, *, host_adapter=None):
    """Run the CLI contract with an optional host-injected trusted adapter."""
    parser = argparse.ArgumentParser(
        description=(
            "Resolve and load SDLC providers. Standalone CLI execution has "
            "no trusted host adapter and fails closed when provider access "
            "is required."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    resolve_parser = subparsers.add_parser("resolve")
    resolve_parser.add_argument("--project-root", type=Path, required=True)
    resolve_parser.add_argument("--registry", type=Path, required=True)
    resolve_parser.add_argument("--host-profile", required=True)
    resolve_parser.add_argument("--sdlc-version", required=True)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--resolution", type=Path, required=True)
    inspect_parser.add_argument("--module", required=True)
    inspect_parser.add_argument("--trigger", required=True)
    inspect_parser.add_argument("--evidence-status", required=True)
    inspect_parser.add_argument("--recognized-evidence", action="append", default=[])
    inspect_parser.add_argument("--gap", action="append", default=[])

    load_parser = subparsers.add_parser("load-module")
    load_parser.add_argument("--resolution", type=Path, required=True)
    load_parser.add_argument("--inspection", type=Path, required=True)
    load_parser.add_argument("--registry", type=Path, required=True)
    load_parser.add_argument("--module", required=True)
    load_parser.add_argument("--provider-context", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "resolve":
            registry = load_json_strict(args.registry)
            names = _registry_names(registry)
            config = load_project_config(args.project_root, names)
            adapter = None
            if host_adapter is not None:
                adapter = _host_adapter_method(
                    host_adapter, "enumerate_providers"
                )(args.host_profile)
            output = resolve(
                config, registry["modules"], adapter,
                args.sdlc_version, args.host_profile,
            )
        elif args.command == "inspect":
            resolution = load_json_strict(args.resolution)
            binding = resolution["providers"].get(args.module)
            if binding is None:
                raise ProviderError("provider-not-configured")
            output = inspect_module(
                args.module, binding, args.trigger, args.evidence_status,
                args.recognized_evidence, args.gap,
            )
        else:
            resolution = load_json_strict(args.resolution)
            inspection = load_json_strict(args.inspection)
            registry = load_json_strict(args.registry)
            registry_module = next(
                (
                    row for row in registry["modules"]
                    if row.get("name") == args.module
                ),
                None,
            )
            if registry_module is None:
                raise ProviderError("provider-registry-invalid")
            output = load_module(
                resolution["providers"][args.module], inspection,
                registry_module,
                (
                    _host_adapter_method(host_adapter, "load_provider")
                    if host_adapter is not None else None
                ),
                load_json_strict(args.provider_context),
            )
        _emit(output)
        return 0
    except (ConfigError, ProviderError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
