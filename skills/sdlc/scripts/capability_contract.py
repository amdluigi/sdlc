"""Project every capability provider onto one declaration shape.

A capability can reach the control plane three ways: bundled with the skill,
installed as an extension, or supplied by a third-party skill. Those three
mechanisms declare the same vocabulary in three different places, which is
what makes the contribution model hard to explain.

This module states the vocabulary once. Bundled modules and extensions
satisfy the contract by projection, so nothing about their storage changes.
A third-party provider authors the declaration directly, in a sidecar
``sdlc-capability.json`` beside its ``SKILL.md``.

The declaration is a sidecar rather than Markdown frontmatter because the
project ships no runtime dependency and no YAML parser, and a parser reading
untrusted third-party input before any trust decision has been made is a
poor trade for idiom.
"""

from __future__ import annotations

import hashlib
import json
import re
import stat
from pathlib import Path


SCHEMA_VERSION = 1
DECLARATION_FILENAME = "sdlc-capability.json"
CONTROL_PLANE_ID = "sdlc"
BUNDLED_ID_PREFIX = "sdlc-"


def bundled_provider_id(capability):
    """Return the identity of the implementation the bundle ships.

    A module is an interface and the skill serving it is an implementation.
    Bundled implementations are named rather than anonymous, so a reader can
    see which one is bound.
    """

    return BUNDLED_ID_PREFIX + capability

MODES = ("default", "augment", "replace")

REQUIRED_FIELDS = (
    "schemaVersion",
    "id",
    "capability",
    "mode",
    "instructions",
    "trigger",
    "exitSignal",
    "evidence",
    "compatibleSdlc",
)
OPTIONAL_FIELDS = ("evaluations",)

_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MAX_ID = 64
_MAX_TEXT = 2048
_MAX_PATH = 256
_MAX_CONSTRAINT = 128


class ContractError(ValueError):
    """A declaration does not satisfy the capability provider contract."""


def _text(value, field, limit=_MAX_TEXT):
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    if len(value) > limit:
        raise ContractError(f"{field} exceeds {limit} characters")
    if any(character in value for character in "\x00\r"):
        raise ContractError(f"{field} contains control characters")
    return value


def _identifier(value, field):
    _text(value, field, _MAX_ID)
    if not _ID_PATTERN.fullmatch(value):
        raise ContractError(f"{field} must be lowercase kebab-case")
    return value


def _relative_path(value, field, suffix):
    _text(value, field, _MAX_PATH)
    if value.startswith("/") or value.startswith("\\"):
        raise ContractError(f"{field} must be a relative path")
    if re.match(r"^[A-Za-z]:", value):
        raise ContractError(f"{field} must be a relative path")
    normalized = value.replace("\\", "/")
    if any(part in ("", ".", "..") for part in normalized.split("/")):
        raise ContractError(f"{field} must not traverse directories")
    if not normalized.endswith(suffix):
        raise ContractError(f"{field} must name a {suffix} file")
    return normalized


def _evidence(value, field):
    if not isinstance(value, list) or not value:
        raise ContractError(f"{field} must be a non-empty array")
    for index, clause in enumerate(value):
        _text(clause, f"{field}[{index}]")
    return list(value)


def validate_declaration(declaration, *, capabilities=None, reserved=None):
    """Return the declaration normalized, or raise ContractError.

    ``capabilities`` constrains the served capability to known names.
    ``reserved`` names identities a third-party provider may not claim.
    """

    if not isinstance(declaration, dict):
        raise ContractError("declaration must be an object")
    present = set(declaration)
    missing = set(REQUIRED_FIELDS) - present
    if missing:
        raise ContractError(f"declaration is missing {sorted(missing)[0]}")
    unknown = present - set(REQUIRED_FIELDS) - set(OPTIONAL_FIELDS)
    if unknown:
        raise ContractError(f"unknown declaration field: {sorted(unknown)[0]}")

    if type(declaration["schemaVersion"]) is not int or (
        declaration["schemaVersion"] != SCHEMA_VERSION
    ):
        raise ContractError(
            f"declaration must use schema version {SCHEMA_VERSION}"
        )

    identifier = _identifier(declaration["id"], "id")
    capability = _identifier(declaration["capability"], "capability")
    if capabilities is not None and capability not in capabilities:
        raise ContractError(f"unknown capability: {capability}")

    mode = declaration["mode"]
    if mode not in MODES:
        raise ContractError(f"unknown mode: {mode!r}")

    if reserved is not None:
        if identifier == CONTROL_PLANE_ID or identifier.startswith(
            BUNDLED_ID_PREFIX
        ):
            raise ContractError(
                f"provider id is reserved to the bundle: {identifier}"
            )
        if identifier in reserved:
            raise ContractError(f"provider id is reserved: {identifier}")

    normalized = {
        "schemaVersion": SCHEMA_VERSION,
        "id": identifier,
        "capability": capability,
        "mode": mode,
        "instructions": _relative_path(
            declaration["instructions"], "instructions", ".md"
        ),
        "trigger": _text(declaration["trigger"], "trigger"),
        "exitSignal": _text(declaration["exitSignal"], "exitSignal"),
        "evidence": _evidence(declaration["evidence"], "evidence"),
        "compatibleSdlc": _text(
            declaration["compatibleSdlc"], "compatibleSdlc", _MAX_CONSTRAINT
        ),
    }

    evaluations = declaration.get("evaluations")
    if mode == "replace" and evaluations is None:
        raise ContractError(
            "a replacing provider must declare evaluations demonstrating "
            "parity with the capability it displaces"
        )
    if evaluations is not None:
        normalized["evaluations"] = _relative_path(
            evaluations, "evaluations", ".json"
        )
    return normalized


PLACEMENT_FIELDS = ("name", "category", "order", "replaceable")


def bundled_directory_name(capability):
    """Return the directory holding a capability's implementation.

    The directory is named after the implementation it holds, not the
    interface it serves, so copying it out yields a skill directory whose
    name already matches its declared skill name.
    """

    return bundled_provider_id(capability)


def bundled_declaration_path(modules_root, name):
    """Return the declaration path for a bundled capability."""

    return (
        Path(modules_root) / bundled_directory_name(name)
        / DECLARATION_FILENAME
    )


def load_bundled_declaration(modules_root, entry, capabilities=None):
    """Load one bundled capability's own declaration from disk.

    The bundle is not exempt from the contract it publishes. Each capability
    declares itself in the same file, with the same fields, that a
    third-party provider authors. The registry row supplies placement only,
    so the two sources may never disagree: a field has exactly one home.
    """

    if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
        raise ContractError("registry entry must name a capability")
    name = entry["name"]

    declared = set(entry) - set(PLACEMENT_FIELDS)
    if declared:
        field = sorted(declared)[0]
        raise ContractError(
            f"registry entry {name} declares {field}, which belongs to its "
            f"{DECLARATION_FILENAME}; the registry owns placement only"
        )

    path = bundled_declaration_path(modules_root, name)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ContractError(
            f"capability {name} ships no readable {DECLARATION_FILENAME}: "
            f"{error}"
        )

    declaration = parse_declaration(text)
    if isinstance(declaration, dict):
        for field in PLACEMENT_FIELDS:
            if field == "name":
                continue
            if field in declaration:
                raise ContractError(
                    f"{name} declares {field}; module placement is owned by "
                    "the registry and may not be claimed by a declaration"
                )

    normalized = validate_declaration(
        declaration, capabilities=capabilities
    )
    if normalized["capability"] != name:
        raise ContractError(
            f"capability directory {name} declares capability "
            f"{normalized['capability']}"
        )
    if normalized["id"] != bundled_provider_id(name):
        raise ContractError(
            f"{name} claims provider id {normalized['id']}; the bundled "
            f"implementation of {name} is {bundled_provider_id(name)}"
        )
    if normalized["mode"] != "default":
        raise ContractError(
            f"{name} declares mode {normalized['mode']}; a bundled "
            "declaration is always the default provider"
        )

    instructions = _confined(path.parent, normalized["instructions"])
    if not instructions.is_file():
        raise ContractError(
            f"{name} declares instructions {normalized['instructions']} "
            "which is not a readable file"
        )
    return normalized


def assemble_module(entry, declaration, name):
    """Rejoin registry placement with a capability's own declaration.

    Consumers read one module record. Holding that record constant is what
    lets the storage change without moving a single consumer.
    """

    assembled = dict(entry)
    assembled["path"] = (
        f"{bundled_directory_name(name)}/{declaration['instructions']}"
    )
    assembled["trigger"] = declaration["trigger"]
    assembled["exitSignal"] = declaration["exitSignal"]
    assembled["evidence"] = list(declaration["evidence"])
    return assembled


def load_registry(registry_path):
    """Read the registry and each capability's declaration as one record."""

    registry_path = Path(registry_path)
    try:
        text = registry_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ContractError(f"registry is unreadable: {error}")
    registry = parse_declaration(text)
    if not isinstance(registry, dict) or not isinstance(
        registry.get("modules"), list
    ):
        raise ContractError("registry must declare a list of modules")

    modules_root = registry_path.parent
    names = {
        row.get("name") for row in registry["modules"]
        if isinstance(row, dict)
    }
    assembled = []
    for entry in registry["modules"]:
        declaration = load_bundled_declaration(modules_root, entry, names)
        assembled.append(
            assemble_module(entry, declaration, entry["name"])
        )
    resolved = dict(registry)
    resolved["modules"] = assembled
    return resolved


def declaration_from_extension(metadata, capabilities=None, reserved=None):
    """Project installed extension metadata onto the contract.

    Extensions keep their current ``extension.json`` field set. ``mode`` and
    ``status`` are extension lifecycle fields the projection maps, so no
    installed extension needs migrating to become conformant.
    """

    if not isinstance(metadata, dict):
        raise ContractError("extension metadata must be an object")
    required = {
        "id",
        "mode",
        "path",
        "trigger",
        "exitSignal",
        "evidence",
        "compatibleSdlc",
    }
    missing = required - set(metadata)
    if missing:
        raise ContractError(
            f"extension metadata is missing {sorted(missing)[0]}"
        )
    if metadata["mode"] != "augment":
        raise ContractError("extension mode must be augment")
    return validate_declaration(
        {
            "schemaVersion": SCHEMA_VERSION,
            "id": metadata["id"],
            "capability": metadata["id"],
            "mode": "augment",
            "instructions": metadata["path"],
            "trigger": metadata["trigger"],
            "exitSignal": metadata["exitSignal"],
            "evidence": metadata["evidence"],
            "compatibleSdlc": metadata["compatibleSdlc"],
        },
        capabilities=capabilities,
        reserved=reserved,
    )


def parse_declaration(text):
    """Parse declaration bytes or text, rejecting duplicate keys."""

    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8")
        except UnicodeError as error:
            raise ContractError(f"invalid declaration encoding: {error}")

    def reject_duplicates(pairs):
        seen = {}
        for key, value in pairs:
            if key in seen:
                raise ContractError(f"duplicate declaration key: {key}")
            seen[key] = value
        return seen

    try:
        return json.loads(text, object_pairs_hook=reject_duplicates)
    except ValueError as error:
        if isinstance(error, ContractError):
            raise
        raise ContractError(f"invalid declaration JSON: {error}")


HOST_PROFILE = "filesystem"
MAX_INSTRUCTION_BYTES = 2 * 1024 * 1024
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _rejects_link(path, label):
    try:
        metadata = path.lstat()
    except OSError as error:
        raise ContractError(f"{label} is unreadable: {error}")
    if stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT
    ):
        raise ContractError(f"{label} must not be a link or reparse point")
    return metadata


class FilesystemProviders:
    """Discover third-party providers that declare themselves on disk.

    Replacement has been unreachable because resolution required a host
    adapter enumerating installed skills, and no host has recorded evidence
    of implementing that interface. A declaration on disk needs no adapter:
    the control plane reads a file, digests it, and resolves it.

    This produces exactly the adapter and adapter-load documents the
    existing resolver already validates, so identity matching, compatibility
    checks, digest binding, and the no-fallback rule are unchanged.

    A malformed provider is skipped and reported rather than raised, so one
    bad directory cannot take the lifecycle down; read ``skipped`` to see
    what was refused and why.

    The declared instruction document is the provider's own Agent Skill
    document, so it must carry frontmatter whose name and sdlc metadata
    match this declaration. Discovery does not check that; loading does,
    and refuses a mismatch as an identity or metadata error.
    """

    def __init__(self, roots, capabilities=None, reserved=None):
        self.roots = [Path(root) for root in roots]
        self.capabilities = capabilities
        self.reserved = reserved
        self.skipped = []
        self._candidates = None
        self._tokens = {}

    def adapter(self):
        """Return the provider enumeration document."""

        if self._candidates is None:
            self._scan()
        return {
            "schemaVersion": 1,
            "hostProfile": HOST_PROFILE,
            "candidates": list(self._candidates),
        }

    def declared_modes(self):
        """Return each discovered provider ID mapped to its declared mode.

        The adapter document carries only the fields resolution validates,
        so mode travels beside it for reporting rather than inside it.
        """

        if self._candidates is None:
            self._scan()
        return {
            declaration["id"]: declaration["mode"]
            for _, declaration in self._tokens.values()
        }

    def load(self, token):
        """Return the adapter-load document for an enumerated token."""

        if self._candidates is None:
            self._scan()
        record = self._tokens.get(token)
        if record is None:
            return {
                "schemaVersion": 1,
                "hostProfile": HOST_PROFILE,
                "status": "token-unknown",
            }
        path, declaration = record
        try:
            _rejects_link(path, "instructions")
            content = path.read_bytes()
        except (ContractError, OSError):
            return {
                "schemaVersion": 1,
                "hostProfile": HOST_PROFILE,
                "status": "unloadable",
            }
        if len(content) > MAX_INSTRUCTION_BYTES:
            return {
                "schemaVersion": 1,
                "hostProfile": HOST_PROFILE,
                "status": "unloadable",
            }
        try:
            text = content.decode("utf-8")
        except UnicodeError:
            return {
                "schemaVersion": 1,
                "hostProfile": HOST_PROFILE,
                "status": "unloadable",
            }
        return {
            "schemaVersion": 1,
            "hostProfile": HOST_PROFILE,
            "status": "loaded",
            "snapshot": {
                "declaredName": declaration["id"],
                "providerMetadata": _provider_metadata(declaration),
                "contentDigest": _digest(content),
                "content": text,
            },
        }

    def _scan(self):
        candidates = []
        self._tokens = {}
        for index, root in enumerate(self.roots):
            if not root.is_dir():
                self.skipped.append(
                    {
                        "path": str(root),
                        "reason": "provider root is not a directory",
                    }
                )
                continue
            for entry in sorted(root.iterdir(), key=lambda item: item.name):
                declaration_path = entry / DECLARATION_FILENAME
                if not entry.is_dir() or not declaration_path.is_file():
                    continue
                try:
                    candidate, record = self._candidate(
                        entry, declaration_path, index
                    )
                except ContractError as error:
                    self.skipped.append(
                        {"path": str(entry), "reason": str(error)}
                    )
                    continue
                candidates.append(candidate)
                self._tokens[candidate["loadToken"]] = record
        self._candidates = candidates

    def _candidate(self, entry, declaration_path, root_index):
        _rejects_link(entry, "provider directory")
        _rejects_link(declaration_path, DECLARATION_FILENAME)
        declaration = validate_declaration(
            parse_declaration(declaration_path.read_bytes()),
            capabilities=self.capabilities,
            reserved=self.reserved,
        )
        if declaration["mode"] == "default":
            raise ContractError(
                "only the bundle may declare mode default"
            )
        instructions = _confined(entry, declaration["instructions"])
        _rejects_link(instructions, "instructions")
        if not instructions.is_file():
            raise ContractError("declared instructions do not exist")
        content = instructions.read_bytes()
        if len(content) > MAX_INSTRUCTION_BYTES:
            raise ContractError("declared instructions are too large")
        if declaration["mode"] == "replace":
            evaluations = _confined(entry, declaration["evaluations"])
            _rejects_link(evaluations, "evaluations")
            if not evaluations.is_file():
                raise ContractError(
                    "a replacing provider must ship the evaluations it "
                    "declares"
                )
        digest = _digest(content)
        candidate = {
            "declaredName": declaration["id"],
            "providerMetadata": _provider_metadata(declaration),
            "contentDigest": digest,
            "loadToken": f"{declaration['id']}@{root_index}",
        }
        return candidate, (instructions, declaration)


def _confined(base, relative):
    resolved = (base / relative).resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise ContractError(f"path escapes the provider directory: {relative}")
    return resolved


def _digest(content):
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _provider_metadata(declaration):
    return {
        "sdlc-provider-schema": "1",
        "sdlc-compatible": declaration["compatibleSdlc"],
        "sdlc-modules": declaration["capability"],
    }
