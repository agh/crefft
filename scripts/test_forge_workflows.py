"""Check forge workflow routing and execute the read-only reference checker."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_sync_claude_config import load_workflow  # noqa: E402
from validate_versions import parse_tool_versions  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".forgejo/workflows"


class ForgeWorkflowTests(unittest.TestCase):
    def test_forge_workflow_triggers_and_pins(self):
        every_push = {"doc-lint.yml", "config-validation.yml", "site.yml"}
        expected = every_push | {
            "check-security-refs.yml", "external-links.yml", "renovate-sync.yml",
        }
        self.assertEqual({path.name for path in WORKFLOWS.iterdir()}, expected)
        security_paths = [
            "reference/security/**", ".forgejo/workflows/check-security-refs.yml",
        ]
        pins = parse_tool_versions(ROOT / "configs/tool-versions.json", {})["action"]
        for name in sorted(expected):
            with self.subTest(workflow=name):
                workflow = load_workflow(WORKFLOWS / name)
                triggers = workflow["on"]
                if name in every_push:
                    self.assertIsNone(triggers["pull_request"])
                    self.assertEqual(triggers["push"], {"branches": ["**"]})
                elif name == "check-security-refs.yml":
                    # Unauthenticated GitHub API calls are rate-limited, so
                    # development events run only for reference changes.
                    self.assertEqual(triggers["pull_request"], {"paths": security_paths})
                    self.assertEqual(
                        triggers["push"], {"branches": ["**"], "paths": security_paths},
                    )
                elif name == "renovate-sync.yml":
                    self.assertEqual(triggers["push"], {"branches": ["renovate/**"]})
                    self.assertIsNone(triggers["pull_request"])
                else:
                    # External availability is not a property of a change.
                    self.assertEqual(set(triggers), {"schedule", "workflow_dispatch"})
                self.assertEqual(workflow["permissions"], {"contents": "read"})
                for job in workflow["jobs"].values():
                    self.assertEqual(job["runs-on"], "ubuntu-latest")
                    for step in job["steps"]:
                        if "uses" in step:
                            action, sha = step["uses"].split("@")
                            self.assertNotIn(action, {
                                "actions/upload-artifact", "actions/download-artifact",
                                "actions/github-script", "actions/setup-python",
                            })
                            self.assertEqual(sha, pins[action])
                            if action == "actions/checkout":
                                self.assertIs(step["with"]["persist-credentials"], False)

    def test_renovate_sync_checks_a_synchronized_update_without_writing_back(self):
        workflow = load_workflow(WORKFLOWS / "renovate-sync.yml")
        job = workflow["jobs"]["sync"]
        self.assertIn("github.event_name != 'pull_request'", job["if"])
        self.assertIn("startsWith(github.head_ref, 'renovate/')", job["if"])
        steps = job["steps"]
        commands = [step.get("run", "") for step in steps]
        sync_index = commands.index("python3 scripts/sync_tool_versions.py")
        diff_index = next(
            index for index, command in enumerate(commands)
            if "git status --short" in command and "git diff --stat" in command
        )
        check_index = commands.index("make check")
        self.assertLess(sync_index, diff_index)
        self.assertLess(diff_index, check_index)

        actions = {
            step["uses"].split("@", 1)[0]: step
            for step in steps if "uses" in step
        }
        self.assertIn("actions/setup-node", actions)
        self.assertIn("astral-sh/setup-uv", actions)
        self.assertIs(actions["actions/checkout"]["with"]["persist-credentials"], False)
        self.assertFalse(any(
            action.startswith("actions/upload-artifact")
            or action.startswith("actions/download-artifact")
            or action == "actions/setup-python"
            for action in actions
        ))

    def test_workflow_lint_runs_in_forge_with_the_local_install_path(self):
        workflow = load_workflow(WORKFLOWS / "config-validation.yml")
        steps = workflow["jobs"]["workflows"]["steps"]
        self.assertIn("make workflows", [step.get("run") for step in steps])
        self.assertTrue(any(
            step.get("uses", "").startswith("astral-sh/setup-uv@")
            and step["with"]["activate-environment"] is True
            for step in steps
        ))
        makefile = (ROOT / "Makefile").read_text()
        self.assertRegex(makefile, r"check:.* workflows")
        self.assertIn("-shellcheck= -pyflakes= $(WORKFLOW_FILES)", makefile)
        self.assertIn("--offline --persona=pedantic $(WORKFLOW_FILES)", makefile)
        for directory in (".github", ".forgejo"):
            for extension in ("yml", "yaml"):
                self.assertIn(f"{directory}/workflows/*.{extension}", makefile)

    def test_schedules_are_preserved(self):
        for name, cron in (
            ("external-links.yml", "23 6 * * 1"),
            ("check-security-refs.yml", "17 3 1 * *"),
        ):
            with self.subTest(workflow=name):
                self.assertEqual(
                    load_workflow(WORKFLOWS / name)["on"]["schedule"], [{"cron": cron}],
                )

    def test_public_submission_automation_is_removed(self):
        self.assertFalse((ROOT / ".github/dependabot.yml").exists())
        self.assertEqual(list((ROOT / ".github/ISSUE_TEMPLATE").glob("*")), [])
        self.assertFalse((ROOT / ".github/PULL_REQUEST_TEMPLATE.md").exists())
        template = (ROOT / ".forgejo/PULL_REQUEST_TEMPLATE.md").read_text()
        self.assertNotIn("External pull requests", template)
        self.assertNotIn("issue forms", template)


class SecurityReferenceWorkflowTests(unittest.TestCase):
    def run_checker(self, mode: str) -> subprocess.CompletedProcess[str]:
        workflow = (WORKFLOWS / "check-security-refs.yml").read_text()
        match = re.search(r"          node <<'JS'\n(.*?)          JS\n", workflow, re.DOTALL)
        self.assertIsNotNone(match)
        script = textwrap.dedent(match[1])
        prelude = f"""
          const mode = {json.dumps(mode)};
          global.fetch = async (url, options = {{}}) => {{
            if (options.method && options.method !== 'GET') throw new Error('write attempted');
            if (Object.keys(options.headers ?? {{}}).some((name) => /authorization/i.test(name))) {{
              throw new Error('credentials must not be sent');
            }}
            if (mode === 'transport') throw new Error('transport fixture failure');
            let body;
            if (url === 'https://cwe-api.mitre.org/api/v1/cwe/version') {{
              body = {{ ContentVersion: '1.0.0' }};
            }} else if (url.startsWith('https://api.github.com/repos/')) {{
              if (url.includes('/tags?')) {{
                body = [{{ name: 'v1.0.0' }}, {{ name: 'v2.0.0-rc1' }}];
              }} else if (url.endsWith('/releases/latest')) {{
                body = {{ tag_name: mode === 'drift' ? 'v2.0.0' : 'v1.0.0' }};
              }} else throw new Error('unexpected endpoint: ' + url);
            }} else throw new Error('unexpected host: ' + url);
            if (mode === 'empty') body = {{}};
            if (mode === 'null') body = null;
            return {{
              ok: mode !== 'http', status: mode === 'http' ? 503 : 200,
              json: async () => {{
                if (mode === 'parse') throw new Error('parse fixture failure');
                return body;
              }},
            }};
          }};
        """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "reference/security/manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({
                "sources": {
                    key: {"version": "v1.0.0" if key == "sigma_rules" else "1.0.0"} for key in (
                        "mitre_attack", "mitre_atlas", "mitre_d3fend", "cwe",
                        "slsa", "openssf_scorecard", "sigma_rules",
                    )
                },
            }), encoding="utf-8")
            return subprocess.run(
                ["node"], input=textwrap.dedent(prelude) + script, cwd=root,
                capture_output=True, text=True,
            )

    def test_current_versions_are_reported_without_network_writes(self):
        result = self.run_checker("current")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("current", result.stdout)
        self.assertNotIn("outdated", result.stdout)

    def test_drift_is_explicitly_reported(self):
        result = self.run_checker("drift")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("outdated", result.stdout)
        self.assertIn("security reference(s) are outdated", result.stderr)

    def test_transport_http_parse_and_missing_versions_fail_closed(self):
        for mode in ("transport", "http", "parse", "empty", "null"):
            with self.subTest(mode=mode):
                result = self.run_checker(mode)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("could not complete", result.stderr)


if __name__ == "__main__":
    unittest.main()
