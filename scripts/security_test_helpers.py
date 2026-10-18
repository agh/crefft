"""Helpers for running shipped security examples without making network requests."""

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

ROOT = Path(os.environ.get("CREFFT_TEST_ROOT", Path(__file__).resolve().parents[1]))


def fenced_blocks(path: str, language: str = "bash") -> list[str]:
    text = (ROOT / path).read_text(encoding="utf-8")
    return re.findall(rf"```{language}\n(.*?)\n```", text, re.DOTALL)


class CurlExampleTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.work = Path(self.tmpdir.name)
        self.capture = self.work / "curl.jsonl"
        curl = self.work / "curl"
        curl.write_text(
            f"#!{sys.executable}\n"
            + textwrap.dedent(
                """\
                import json
                import os
                import sys
                from pathlib import Path

                args = sys.argv[1:]
                files = {}
                for index, arg in enumerate(args):
                    if arg in ("--config", "-K", "--header", "-H", "--data-binary", "-d"):
                        value = args[index + 1]
                        if value.startswith("@") and value != "@-":
                            files[value] = Path(value[1:]).read_text()
                        elif arg in ("--config", "-K") and value != "-":
                            files[value] = Path(value).read_text()
                record = {"argv": args, "stdin": sys.stdin.read(), "files": files}
                with open(os.environ["CURL_CAPTURE"], "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record) + "\\n")
                print(os.environ.get("CURL_RESPONSE", ""))
                sys.exit(int(os.environ.get("CURL_EXIT", "0")))
                """
            ),
            encoding="utf-8",
        )
        curl.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": f"{self.work}{os.pathsep}{os.environ['PATH']}",
            "CURL_CAPTURE": str(self.capture),
        }

    def run_shell(self, script: str, *, stdin: str = "", **env: str):
        return subprocess.run(
            ["bash", "-euo", "pipefail", "-c", script],
            input=stdin,
            text=True,
            capture_output=True,
            cwd=self.work,
            env={**self.env, **env},
            timeout=15,
        )

    def requests(self) -> list[dict]:
        if not self.capture.exists():
            return []
        return [json.loads(line) for line in self.capture.read_text().splitlines()]
