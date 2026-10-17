"""Reject tool and agent credit in shipped publication templates."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from security_test_helpers import ROOT  # noqa: E402

CREDIT = re.compile(
    r"released by|"
    r"(?:generated|written|created|authored|powered)\s+(?:by|with|using)\s+"
    r"(?:\{(?:agent|model|tool)\}|claude|copilot|gemini|chatgpt|gpt[- ]|ops/)|"
    r"co-authored-by:.*(?:copilot|claude|gemini|chatgpt|gpt[- ]|agent)|"
    r"\*\{agent\}\s*[-|]|"
    r'"(?:text|author)"\s*:\s*"(?:ops|code|docs|security|system)/',
    re.IGNORECASE,
)


class PublishedCreditTests(unittest.TestCase):
    def test_shipped_templates_do_not_credit_tools(self):
        hits = []
        for directory in ("configs", "agents", "commands", "guides"):
            for path in sorted((ROOT / directory).rglob("*")):
                if path.is_file():
                    for number, line in enumerate(path.read_text().splitlines(), 1):
                        if CREDIT.search(line):
                            hits.append(f"{path.relative_to(ROOT)}:{number}")
        self.assertEqual(hits, [], "tool credit in shipped text: " + ", ".join(hits))


if __name__ == "__main__":
    unittest.main()
