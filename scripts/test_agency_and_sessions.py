"""Keep standalone agency/session policy copies synchronized with the template."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CANONICAL = ROOT / "configs/agents/AGENTS.md.template"
SECTION = re.compile(r"^## Agency and sessions\n.*?(?=^## |\Z)", re.MULTILINE | re.DOTALL)


class AgencyAndSessionsTests(unittest.TestCase):
    def section(self, path: Path) -> str:
        sections = SECTION.findall(path.read_text(encoding="utf-8"))
        self.assertEqual(
            len(sections),
            1,
            f"{path.relative_to(ROOT)} must contain exactly one Agency and sessions section",
        )
        return sections[0]

    def test_policy_copies_match_canonical_section(self):
        canonical = self.section(CANONICAL)
        agents = sorted((ROOT / "agents").rglob("*.md"))
        self.assertTrue(agents, "No agent definitions found")
        for path in [ROOT / "AGENTS.md", *agents]:
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertEqual(
                    self.section(path),
                    canonical,
                    "Policy differs from configs/agents/AGENTS.md.template",
                )


if __name__ == "__main__":
    unittest.main()
