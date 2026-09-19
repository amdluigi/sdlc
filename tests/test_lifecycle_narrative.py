from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "skills" / "sdlc" / "modules" / "registry.json"
README = ROOT / "README.md"
FLOW = ROOT / "docs" / "SDLC-DEVELOPMENT-FLOW.md"
DIAGRAM = ROOT / "docs" / "images" / "sdlc-development-flow" / (
    "01-development-lifecycle.svg"
)

SUPERSEDED = (
    "understand, plan, build, verify, and hand off",
    "five understandable phases",
    "Five steps: understand, plan, build, verify, and handoff",
)


def delivery_phases() -> list:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))["deliveryPhases"]


class LifecycleNarrativeTest(unittest.TestCase):
    """Public lifecycle prose must match the registry it describes."""

    def test_readme_names_every_delivery_phase(self) -> None:
        readme = README.read_text(encoding="utf-8").lower()

        for phase in delivery_phases():
            self.assertIn(
                phase,
                readme,
                f"README does not name the {phase} delivery phase",
            )

    def test_flow_document_names_every_delivery_phase(self) -> None:
        flow = FLOW.read_text(encoding="utf-8").lower()

        for phase in delivery_phases():
            self.assertIn(
                phase,
                flow,
                f"flow document does not name the {phase} delivery phase",
            )

    def test_lifecycle_diagram_names_every_delivery_phase(self) -> None:
        diagram = DIAGRAM.read_text(encoding="utf-8").lower()

        for phase in delivery_phases():
            self.assertIn(
                phase,
                diagram,
                f"lifecycle diagram does not name the {phase} phase",
            )

    def test_superseded_five_phase_narrative_is_absent(self) -> None:
        for path in (README, FLOW, DIAGRAM):
            text = path.read_text(encoding="utf-8")
            for phrase in SUPERSEDED:
                self.assertNotIn(
                    phrase,
                    text,
                    f"{path.name} still carries the superseded narrative",
                )

    def test_phase_count_claim_matches_the_registry(self) -> None:
        count = len(delivery_phases())
        flow = FLOW.read_text(encoding="utf-8").lower()

        self.assertIn(
            f"{count} delivery phases",
            flow,
            "flow document must state the current phase count",
        )

    def test_diagram_alt_text_describes_the_lifecycle(self) -> None:
        flow = FLOW.read_text(encoding="utf-8")

        self.assertIn("![", flow, "diagram must carry Markdown alt text")


if __name__ == "__main__":
    unittest.main()
