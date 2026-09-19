"""Render the resolved SDLC delivery profile.

The profile states which plugin serves each capability, grouped by phase of
software development, so a developer can read one map to understand the
configured process and review one diff when it changes.

Phase is a grouping and presentation layer. Plugin resolution happens per
capability; a phase never binds a plugin.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCHEMA_VERSION = 1
BUNDLED_PLUGIN_PREFIX = "sdlc-"

HEADER = (
    "# SDLC delivery profile\n"
    "\n"
    "Generated file. Do not edit by hand.\n"
    "\n"
    "Each row states which plugin serves a capability and where that plugin\n"
    "came from. A capability is an interface and its plugin is the\n"
    "implementation bound to it. Implementations the bundle ships are named\n"
    "after the capability they serve, so `sdlc-testing` is the bundled\n"
    "implementation of `testing`.\n"
    "\n"
    "A phase heading shows its entry gate: the earliest lifecycle gate at\n"
    "which any of its capabilities participates. It is not a per-phase\n"
    "identifier, so one gate can open two phases and a gate that opens no\n"
    "phase does not appear. A phase without an entry gate lies outside the\n"
    "per-change state machine and carries no blocking authority.\n"
    "\n"
    "To change a plugin, edit the project configuration, then regenerate:\n"
    "\n"
    "```\n"
    "python skills/sdlc/scripts/delivery_profile.py render \\\n"
    "  --registry skills/sdlc/modules/registry.json \\\n"
    "  --output docs/DELIVERY-PROFILE.md\n"
    "```"
)

COLUMNS = ("Capability", "Plugin", "Source", "Role", "Enabled")


def _module_state(config, name):
    if not config:
        return True
    return config.get("modules", {}).get(name, True)


def _resolve(state, capability):
    if isinstance(state, dict) and "replaceWith" in state:
        return {
            "plugin": state["replaceWith"],
            "source": "external",
            "role": "replace",
            "enabled": True,
        }
    explicit = isinstance(state, dict)
    return {
        "plugin": BUNDLED_PLUGIN_PREFIX + capability,
        "source": "bundled",
        "role": "chosen" if explicit else "default",
        "enabled": state is not False,
    }


def build_profile(registry, config):
    """Resolve registry and configuration into delivery profile data."""
    categories = registry["categories"]
    phases = registry["deliveryPhases"]

    grouped = {name: [] for name in phases}
    for entry in registry["modules"]:
        category = categories[entry["category"]]
        resolved = _resolve(
            _module_state(config, entry["name"]), entry["name"]
        )
        resolved["name"] = entry["name"]
        resolved["category"] = entry["category"]
        grouped[category["deliveryPhase"]].append(resolved)

    gates = {}
    for value in categories.values():
        if value["gate"] is None:
            continue
        phase = value["deliveryPhase"]
        current = gates.get(phase)
        if current is None or value["gate"] < current:
            gates[phase] = value["gate"]

    return {
        "schemaVersion": SCHEMA_VERSION,
        "phases": [
            {
                "name": name,
                "gate": gates.get(name),
                "capabilities": grouped[name],
            }
            for name in phases
        ],
    }


def render_markdown(profile):
    """Render delivery profile data as deterministic Markdown."""
    lines = [HEADER]
    for phase in profile["phases"]:
        gate = phase["gate"]
        suffix = (
            "entry gate {0}".format(gate)
            if gate is not None
            else "no entry gate"
        )
        lines.append("")
        lines.append("## {0} ({1})".format(phase["name"], suffix))
        lines.append("")
        lines.append("| " + " | ".join(COLUMNS) + " |")
        lines.append("|" + "---|" * len(COLUMNS))
        for capability in phase["capabilities"]:
            lines.append(
                "| {name} | {plugin} | {source} | {role} | {enabled} |".format(
                    name=capability["name"],
                    plugin=capability["plugin"],
                    source=capability["source"],
                    role=capability["role"],
                    enabled="yes" if capability["enabled"] else "no",
                )
            )
    return "\n".join(lines) + "\n"


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Render the SDLC delivery profile"
    )
    parser.add_argument("command", choices=("render", "show"))
    parser.add_argument("--registry", required=True)
    parser.add_argument("--config", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)

    config = _load(args.config) if args.config else None
    text = render_markdown(build_profile(_load(args.registry), config))

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
