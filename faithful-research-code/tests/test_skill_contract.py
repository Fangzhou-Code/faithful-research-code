from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class SkillContractTests(unittest.TestCase):
    def test_core_artifact_contract_is_routed_from_skill(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        required = {
            "claim-to-artifact manifest",
            "hyperparameter search space",
            "baseline",
            "reviewer-executable artifact",
            "INDEPENDENT_REPRODUCTION",
        }
        self.assertTrue(all(term in skill for term in required))

    def test_readme_template_contains_top_conference_evidence_chain(self) -> None:
        template = (ROOT / "assets" / "research-readme-template.md").read_text(
            encoding="utf-8"
        )
        for heading in (
            "## Background",
            "## Gap / Challenges",
            "## Method contributions",
            "### Result reproduction map",
            "### Main experiments",
            "### Ablation experiments",
            "### Code workflow",
            "### Artifact release and validation",
        ):
            self.assertIn(heading, template)

    def test_behavior_suite_keeps_trigger_boundaries(self) -> None:
        cases = json.loads((ROOT / "tests" / "behavior-cases.json").read_text())
        self.assertEqual(len(cases), 12)
        self.assertEqual(sum(case["should_trigger"] for case in cases), 8)
        self.assertEqual(sum(not case["should_trigger"] for case in cases), 4)


if __name__ == "__main__":
    unittest.main()
