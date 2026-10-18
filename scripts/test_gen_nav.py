"""Check literal file names in generated navigation link text."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gen_nav import title_for  # noqa: E402


class NavigationTitleTests(unittest.TestCase):
    def test_file_names_are_code_spans_but_titles_and_directories_are_not(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / ".editorconfig"
            config.write_text("root = true\n")
            self.assertEqual(title_for(config), "`.editorconfig`")
            guide = root / "README.md"
            guide.write_text("# Editor Settings Guide\n")
            self.assertEqual(title_for(guide), "Editor Settings")
            self.assertEqual(title_for(root), root.name)


if __name__ == "__main__":
    unittest.main()
