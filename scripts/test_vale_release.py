"""Guard the release workflow's read/build and write/publish separation."""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from prepare_vale_release import release_notes  # noqa: E402
from validate_versions import parse_canonical, parse_tool_versions  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class GitHubWorkflowPolicyTests(unittest.TestCase):
    def test_only_release_workflows_exist_and_only_version_tags_trigger_them(self):
        workflows = ROOT / ".github/workflows"
        self.assertEqual({path.name for path in workflows.iterdir()}, {"release.yml", "site.yml"})
        for path in workflows.iterdir():
            with self.subTest(workflow=path.name):
                header = path.read_text().split("\njobs:\n", 1)[0]
                trigger = header.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
                self.assertEqual(trigger.strip(), "push:\n    tags: ['v*']")


class ValeReleaseWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / ".github/workflows/release.yml").read_text()
        self.header, jobs = self.workflow.split("\njobs:\n", 1)
        self.jobs = dict(re.findall(
            r"^  ([a-z-]+):\n(.*?)(?=^  [a-z-]+:\n|\Z)",
            jobs, re.MULTILINE | re.DOTALL,
        ))

    def test_only_pushed_version_tags_trigger_release(self):
        trigger = self.header.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertEqual(trigger.strip(), "push:\n    tags: ['v*']")
        self.assertIn("cancel-in-progress: false", self.header)
        self.assertIn("group: release-${{ github.ref }}", self.header)
        self.assertNotIn("cancel-in-progress: true", self.workflow)

    def test_only_publisher_has_write_permission(self):
        self.assertEqual(set(self.jobs), {"package", "release"})
        self.assertIn("permissions:\n  contents: read", self.header)
        self.assertIn("permissions:\n      contents: read", self.jobs["package"])
        self.assertIn("permissions:\n      contents: write", self.jobs["release"])
        self.assertEqual(self.workflow.count("contents: write"), 1)
        self.assertEqual(self.workflow.count("permissions:"), 3)

    def test_publisher_only_downloads_and_publishes_existing_bytes(self):
        release = self.jobs["release"]
        self.assertIn("needs: package", release)
        actions = re.findall(r"uses: (\S+)", release)
        pins = parse_tool_versions(ROOT / "configs/tool-versions.json", {})
        self.assertEqual(actions, [
            f"actions/download-artifact@{pins['action']['actions/download-artifact']}"
        ])
        self.assertNotIn("checkout", release)
        self.assertNotRegex(release, r"\b(?:make|python3?|npm|build)\b")
        commands = release.split("        run: |\n", 1)[1]
        self.assertEqual(
            " ".join(commands.replace("\\\n", "").split()),
            'version="${GITHUB_REF_NAME#v}" '
            'gh release create "$GITHUB_REF_NAME" Crefft.zip Crefft.zip.sha256 '
            '--verify-tag --title "crefft $version" --notes-file notes.md',
        )
        self.assertEqual(release.count("- name:"), 2)
        self.assertIn("name: crefft-release", release)
        self.assertIn("GH_TOKEN: ${{ github.token }}", release)
        self.assertIn("GH_REPO: ${{ github.repository }}", release)
        self.assertEqual(self.workflow.count("${{ github.token }}"), 1)
        self.assertNotIn("${{", commands)

    def test_package_job_tests_and_uploads_the_exact_release_files(self):
        package = self.jobs["package"]
        self.assertIn('test "$RELEASE_TAG" = "v$(cat VERSION)"', package)
        self.assertIn('scripts/prepare_vale_release.py --tag "$RELEASE_TAG"', package)
        self.assertIn("python3 -m unittest discover scripts", package)
        self.assertIn("make vale-package-check", package)
        self.assertIn("--no-global test --coverage configs/vale/Crefft/styles/Crefft", package)
        paths = package.split("          path: |\n", 1)[1].split()
        self.assertEqual(paths, [
            ".tmp-check/vale-package/Crefft.zip",
            ".tmp-check/vale-package/Crefft.zip.sha256",
            ".tmp-check/vale-package/notes.md",
        ])
        self.assertIn("name: crefft-release", package)
        self.assertIn("if-no-files-found: error", package)
        self.assertIn("include-hidden-files: true", package)


class ValeReleaseNotesTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)
        (self.root / "VERSION").write_text("2026.10.3\n")
        self.changelog = self.root / "CHANGELOG.md"
        self.changelog.write_text(
            "# Changelog\n\n## [Unreleased]\n\n- Not released.\n\n"
            "## [2026.10.3] - 2026-10-18\n\n### Added\n\n- Crefft package.\n\n"
            "## [2026.10.2] - 2026-10-17\n\n- Older release.\n"
        )

    def test_extracts_only_the_matching_version(self):
        self.assertEqual(
            release_notes(self.root, "v2026.10.3"), "### Added\n\n- Crefft package.\n"
        )

    def test_mismatched_tags_fail(self):
        for tag in ("v2026.10.2", "2026.10.3", "v2026.10.3-other", "main"):
            with self.subTest(tag=tag), self.assertRaisesRegex(ValueError, "tag must equal"):
                release_notes(self.root, tag)

    def test_missing_or_empty_version_section_fails(self):
        for text in (
            "## [Unreleased]\n\n- Package.\n",
            "## [2026.10.3]\n\n## [2026.10.2]\n\n- Old.\n",
        ):
            self.changelog.write_text(text)
            with self.assertRaisesRegex(ValueError, "nonempty release section"):
                release_notes(self.root, "v2026.10.3")

    def test_last_release_section_is_supported(self):
        self.changelog.write_text("## [2026.10.3]\n\n### Added\n\n- Package.\n")
        self.assertEqual(
            release_notes(self.root, "v2026.10.3"), "### Added\n\n- Package.\n"
        )


class ValeVersionPinTests(unittest.TestCase):
    def test_makefile_binary_and_checksums_match_registered_pins(self):
        canonical = ROOT / "configs/pre-commit/.pre-commit-config.yaml"
        pins = parse_tool_versions(ROOT / "configs/tool-versions.json", parse_canonical(canonical))
        makefile = (ROOT / "Makefile").read_text().replace("\\\n", "")
        version = re.search(r"^VALE_VERSION := (\S+)$", makefile, re.MULTILINE).group(1)
        self.assertEqual(version, pins["binary"]["vale"])
        self.assertEqual(pins["hook"]["vale-cli/vale"], f"v{version}")
        checksums = dict(re.findall(
            r"^VALE_SHA256_(\S+) :=\s+([0-9a-f]{64})$", makefile, re.MULTILINE
        ))
        self.assertEqual(set(checksums), {
            "Linux_64-bit", "Linux_arm64", "macOS_64-bit", "macOS_arm64"
        })
        for platform, digest in checksums.items():
            self.assertEqual(
                pins["checksum"][f"vale_{version}_{platform}.tar.gz"], f"sha256:{digest}"
            )
        self.assertIn('shasum -a 256 -c -', makefile)
        self.assertIn('$(VALE) --no-global sync', makefile)
        self.assertIn("$(MARKDOWN_FILES) | xargs -0 $(VALE) --no-global", makefile)


if __name__ == "__main__":
    unittest.main()
