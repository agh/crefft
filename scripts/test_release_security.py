"""Run the release readiness guard extracted from its shipped workflow."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from security_test_helpers import ROOT  # noqa: E402


class ReleaseGuardTests(unittest.TestCase):
    def guard(self) -> str:
        text = (ROOT / "agents/ops/release-manager.md").read_text()
        marked = re.search(
            r"    # release-guard:start\n(.*?)    # release-guard:end", text, re.DOTALL
        )
        if marked:
            return textwrap.dedent(marked.group(1))
        # The original workflow had no markers; replay that guard for the red test.
        start = text.index("    decision=$(jq")
        end = text.index("\n- name: Update changelog", start)
        return textwrap.dedent(text[start:end])

    def run_guard(self, decision="release", blockers=None, gates=None, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            output = work / "outputs"
            assessment = {
                "decision": decision,
                "confidence": 100,
                "version": "2026.10.0",
                "blockers": [] if blockers is None else blockers,
                "mandatory_gates": {
                    "ci": True,
                    "tests": True,
                    "security": True,
                    "reviews": True,
                    "evidence": True,
                } if gates is None else gates,
                **overrides,
            }
            (work / "readiness.json").write_text(
                json.dumps({"is_error": False, "structured_output": assessment})
            )
            result = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", self.guard()],
                cwd=work,
                env={"PATH": os.environ["PATH"], "GITHUB_OUTPUT": str(output)},
                text=True,
                capture_output=True,
                timeout=15,
            )
            return result, output.read_text() if output.exists() else ""

    def test_release_with_blockers_fails_at_any_confidence(self):
        for confidence in (0, 90, 100):
            with self.subTest(confidence=confidence):
                result, _ = self.run_guard(blockers=["required test failed"], confidence=confidence)
                self.assertNotEqual(result.returncode, 0)

    def test_release_without_blockers_passes(self):
        result, output = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("decision=release\n", output)

    def test_block_and_hold_fail_without_blockers(self):
        for decision in ("block", "hold"):
            with self.subTest(decision=decision):
                result, _ = self.run_guard(decision)
                self.assertNotEqual(result.returncode, 0)

    def test_every_mandatory_gate_is_enforced(self):
        for gate in ("ci", "tests", "security", "reviews", "evidence"):
            with self.subTest(gate=gate):
                gates = dict.fromkeys(("ci", "tests", "security", "reviews", "evidence"), True)
                gates[gate] = False
                result, _ = self.run_guard(gates=gates)
                self.assertNotEqual(result.returncode, 0)

    def test_missing_gate_results_fail_closed(self):
        for gates in ({}, [], "passed"):
            with self.subTest(gates=gates):
                result, _ = self.run_guard(gates=gates)
                self.assertNotEqual(result.returncode, 0)

    def test_invalid_decision_or_blockers_fail_closed(self):
        for overrides in (
            {"decision": "unknown"},
            {"blockers": ""},
            {"blockers": {}},
            {"blockers": False},
        ):
            with self.subTest(overrides=overrides):
                result, _ = self.run_guard(**overrides)
                self.assertNotEqual(result.returncode, 0)

    def test_failed_readiness_does_not_publish_changelog_outputs(self):
        result, output = self.run_guard(blockers=["security gate failed"])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output, "")

    def test_changelog_requires_a_successful_readiness_step(self):
        text = (ROOT / "agents/ops/release-manager.md").read_text()
        condition = text.split("- name: Update changelog\n  if: |\n", 1)[1].split("  env:", 1)[0]
        self.assertIn("steps.readiness.outcome == 'success'", condition)
        self.assertIn("steps.readiness.outputs.passed == 'true'", condition)
        self.assertIn("steps.readiness.outputs.decision == 'release'", condition)

    def test_every_documented_workflow_requires_clear_gates(self):
        text = (ROOT / "guides/ai/release-manager-agent.md").read_text()
        for workflow in ("continuous", "scheduled", "manual", "release_train"):
            with self.subTest(workflow=workflow):
                block = re.search(rf"workflow: {workflow}\n(.*?)```", text, re.DOTALL).group(1)
                self.assertIn("conditions:\n", block)
                conditions = block.split("conditions:\n", 1)[1].split("\nactions:", 1)[0]
                for rule in (
                    "require_all_checks_pass",
                    "require_no_blockers",
                    "require_mandatory_gates_pass",
                    "fail_on_missing_gate_results",
                ):
                    self.assertIn(f"  {rule}: true", conditions)


if __name__ == "__main__":
    unittest.main()
