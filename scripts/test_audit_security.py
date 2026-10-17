"""Exercise the installed audit hook, including secret-bearing failure events."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from security_test_helpers import ROOT, CurlExampleTestCase  # noqa: E402

HOOK = ROOT / "configs/claude/infrastructure/audit-hook.sh"


class AuditHookTests(CurlExampleTestCase):
    def event(self, name: str) -> dict:
        return {
            "hook_event_name": name,
            "session_id": "session-123",
            "tool_name": "Bash",
            "tool_use_id": "tool-456",
            "duration_ms": 123,
            "cwd": "/private/canary-directory",
            "tool_input": {"command": "echo canary-input-619"},
            "tool_response": {"rows": ["canary-output-852"]},
            "error": "canary-error-374",
            "unexpected": "canary-extra-941",
        }

    def run_hook(self, event: dict | str, **env: str):
        return subprocess.run(
            [str(HOOK)],
            input=json.dumps(event) if isinstance(event, dict) else event,
            text=True,
            capture_output=True,
            env={**self.env, "AUDIT_LOG_URL": "https://audit.example.com", **env},
            timeout=15,
        )

    def assert_metadata_only(self, name: str, status: str):
        result = self.run_hook(self.event(name))
        self.assertEqual(result.returncode, 0, result.stderr)
        request = self.requests()[-1]
        payload = request["stdin"]
        self.assertNotIn("canary-", payload, "audit payload contains sensitive content")
        data = json.loads(payload)
        self.assertEqual(set(data), {"timestamp", "hook_event_name", "agent", "action", "outcome"})
        self.assertEqual(data["hook_event_name"], name)
        self.assertEqual(data["agent"], {"session_id": "session-123"})
        self.assertEqual(
            data["action"], {"type": "tool", "name": "Bash", "tool_use_id": "tool-456"}
        )
        self.assertEqual(data["outcome"], {"status": status, "duration_ms": 123})
        self.assertRegex(data["timestamp"], r"^\d{4}-\d\d-\d\dT.*Z$")

    def test_success_contains_only_metadata(self):
        self.assert_metadata_only("PostToolUse", "success")

    def test_failure_contains_only_metadata(self):
        self.assert_metadata_only("PostToolUseFailure", "failure")

    def test_hook_is_executable(self):
        self.assertTrue(os.access(HOOK, os.X_OK))

    def test_invalid_input_never_posts_or_echoes_content(self):
        invalid_metadata = self.event("PostToolUse")
        invalid_metadata["session_id"] = {"content": "canary-nested"}
        invalid_duration = self.event("PostToolUse")
        invalid_duration["duration_ms"] = "canary-duration"
        for event in (
            "not-json canary-invalid",
            "[]",
            "{}",
            invalid_metadata,
            invalid_duration,
            self.event("UnexpectedEvent"),
            json.dumps(self.event("PostToolUse")) + "\n{}",
        ):
            with self.subTest(event=event):
                result = self.run_hook(event)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotEqual(result.returncode, 2)
                self.assertNotIn("canary-", result.stdout + result.stderr)
        self.assertEqual(self.requests(), [])

    def test_logging_errors_are_nonblocking_hook_errors(self):
        for code in ("2", "22", "28"):
            with self.subTest(code=code):
                result = self.run_hook(self.event("PostToolUse"), CURL_EXIT=code)
                self.assertEqual(result.returncode, 1)
                self.assertTrue(result.stderr)

    def test_missing_duration_is_null(self):
        event = self.event("PostToolUse")
        del event["duration_ms"]
        result = self.run_hook(event)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(json.loads(self.requests()[0]["stdin"])["outcome"]["duration_ms"])

    def test_missing_endpoint_does_not_post(self):
        result = self.run_hook(self.event("PostToolUse"), AUDIT_LOG_URL="")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.requests(), [])


if __name__ == "__main__":
    unittest.main()
