"""Check actual curl arguments, not just the spelling of credential examples."""

from __future__ import annotations

import base64
import json
import re
import sys
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from security_test_helpers import CurlExampleTestCase, fenced_blocks  # noqa: E402

DISCORD = "configs/claude/skills/communication/discord.md"
PROMETHEUS = "configs/claude/skills/monitoring/prometheus.md"
VICTORIALOGS = "configs/claude/skills/monitoring/victorialogs.md"


class CredentialTests(CurlExampleTestCase):
    def assert_transport(self, secret: str):
        requests = self.requests()
        self.assertTrue(requests, "example did not invoke curl")
        for request in requests:
            self.assertFalse(
                any(secret in arg for arg in request["argv"]),
                "credential is visible in curl argv",
            )
            private_input = request["stdin"] + "".join(request["files"].values())
            if request["stdin"].lstrip().startswith("{"):
                body = json.loads(request["stdin"])
                private_input += "".join(value for value in body.values() if isinstance(value, str))
            for line in private_input.splitlines():
                if line.startswith("url = "):
                    private_input += json.loads(line.removeprefix("url = "))
            for basic in re.findall(r"Authorization: Basic ([A-Za-z0-9+/=]+)", private_input):
                private_input += base64.b64decode(basic).decode()
            self.assertIn(secret, private_input, "credential was not delivered to curl")

    def test_discord_webhook(self):
        script = next(block for block in fenced_blocks(DISCORD) if "curl " in block)
        secret = "canary-webhook-729"
        result = self.run_shell(
            script, DISCORD_WEBHOOK_URL=f"https://discord.example.com/webhooks/{secret}"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_transport(secret)

    def test_discord_config_quotes_the_url(self):
        script = next(block for block in fenced_blocks(DISCORD) if "curl " in block)
        secret = 'canary-webhook-729"\\'
        url = f"https://discord.example.com/webhooks/{secret}"
        result = self.run_shell(script, DISCORD_WEBHOOK_URL=url)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_transport(secret)
        self.assertEqual(json.loads(self.requests()[0]["stdin"].removeprefix("url = ")), url)

    def test_discord_multiple_channels(self):
        script = next(block for block in fenced_blocks(DISCORD) if "post_discord()" in block)
        secret = "canary-webhook-543"
        result = self.run_shell(
            script,
            DISCORD_RELEASES_WEBHOOK=f"https://discord.example.com/releases/{secret}",
            DISCORD_ALERTS_WEBHOOK=f"https://discord.example.com/alerts/{secret}",
            release_payload='{"content":"release","allowed_mentions":{"parse":[]}}',
            alert_payload='{"content":"alert","allowed_mentions":{"parse":[]}}',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_transport(secret)

    def test_discord_workflow(self):
        block = next(block for block in fenced_blocks(DISCORD, "yaml") if "payload=$(jq" in block)
        script = textwrap.dedent(block.split("        run: |\n", 1)[1])
        (self.work / "RELEASE_NOTES.md").write_text("Release notes")
        secret = "canary-webhook-365"
        result = self.run_shell(
            script,
            DISCORD_WEBHOOK_URL=f"https://discord.example.com/webhooks/{secret}",
            GITHUB_REF_NAME="v1.2.0",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_transport(secret)

    def prometheus(self, **auth: str):
        script = next(block for block in fenced_blocks(PROMETHEUS) if "_api()" in block)
        result = self.run_shell(
            script,
            CURL_RESPONSE='{"status":"success","data":{"result":[]}}',
            **{"PROMETHEUS_TOKEN": "", "PROMETHEUS_USER": "", **auth},
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_prometheus_bearer(self):
        secret = 'canary-token-261"\\'
        self.prometheus(PROMETHEUS_TOKEN=secret)
        self.assert_transport(secret)

    def test_prometheus_basic(self):
        secret = 'canary-password-194"\\'
        self.prometheus(PROMETHEUS_USER="reader", PROMETHEUS_PASSWORD=secret)
        self.assert_transport(secret)

    def test_victorialogs_authentication(self):
        script = next(block for block in fenced_blocks(VICTORIALOGS) if "query_logs()" in block)
        secret = 'canary-monitoring-875"\\'
        for auth in (
            {"VICTORIALOGS_TOKEN": secret, "VICTORIALOGS_USER": ""},
            {
                "VICTORIALOGS_TOKEN": "",
                "VICTORIALOGS_USER": "reader",
                "VICTORIALOGS_PASSWORD": secret,
            },
        ):
            with self.subTest(kind="bearer" if auth["VICTORIALOGS_TOKEN"] else "basic"):
                result = self.run_shell(script, **auth)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assert_transport(secret)

    def test_github_header(self):
        path = "configs/claude/skills/communication/github.md"
        script = next(block for block in fenced_blocks(path) if 'curl -sS -H "X-GitHub' in block)
        secret = 'canary-github-432"\\'
        result = self.run_shell(script, GITHUB_PAT=secret)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_transport(secret)

    def test_release_lifecycle_header(self):
        script = next(
            block for block in fenced_blocks("guides/ai/release-manager-agent.md")
            if "# check-models.sh" in block
        )
        secret = 'canary-example-api-key-173"\\'
        result = self.run_shell(script, ANTHROPIC_API_KEY=secret, CURL_RESPONSE='{"data":[]}')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_transport(secret)

    def test_homeassistant_examples(self):
        path = "configs/claude/skills/iot/homeassistant.md"
        secret = 'canary-example-homeassistant-651"\\'
        for index, script in enumerate(fenced_blocks(path)):
            if "curl " not in script:
                continue
            with self.subTest(block=index):
                response = "{}"
                if "select(.entity_id" in script:
                    response = "[]"
                elif "jq '.[0]" in script:
                    response = "[[]]"
                result = self.run_shell(
                    script,
                    HASS_URL="https://ha.example.com",
                    HASS_TOKEN=secret,
                    HASS_AGENT_TOKEN=secret,
                    SUPERVISOR_TOKEN=secret,
                    CURL_RESPONSE=response,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assert_transport(secret)

    def test_mqtt_examples(self):
        path = "configs/claude/skills/iot/mqtt.md"
        secret = 'canary-mqtt-983"\\'
        (self.work / "acl.conf").write_text("{deny, all}.\n")
        for index, script in enumerate(fenced_blocks(path)):
            if "curl " not in script:
                continue
            with self.subTest(block=index):
                self.capture.unlink(missing_ok=True)
                result = self.run_shell(
                    script,
                    EMQX_USER="operator",
                    EMQX_PASS=secret,
                    EMQX_API_KEY="reader",
                    EMQX_API_SECRET=secret,
                    EMQX_ADMIN_KEY="admin",
                    EMQX_ADMIN_SECRET=secret,
                    CURL_RESPONSE=json.dumps({"token": secret, "payload": ""}),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = (
                    "dashboard_user:password" if "dashboard_user:password" in script else secret
                )
                self.assert_transport(expected)

    def test_monitoring_failure_status_is_preserved(self):
        for path, marker in ((PROMETHEUS, "_api()"), (VICTORIALOGS, "query_logs()")):
            with self.subTest(path=path):
                script = next(block for block in fenced_blocks(path) if marker in block)
                result = self.run_shell(
                    script,
                    PROMETHEUS_TOKEN="",
                    PROMETHEUS_USER="",
                    VICTORIALOGS_TOKEN="",
                    VICTORIALOGS_USER="",
                    CURL_EXIT="22",
                    CURL_RESPONSE='{"status":"error","error":"invalid query"}',
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("request failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
