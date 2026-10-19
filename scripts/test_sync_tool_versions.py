"""Exercise registry synchronization without network access or repository writes."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sync_tool_versions as sync  # noqa: E402
import validate_versions as vv  # noqa: E402
from test_sync_claude_config import load_workflow  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class SynchronizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        paths = set(vv.iter_files(ROOT))
        paths.update(ROOT.glob("*.md"))
        paths.update(ROOT / name for name in (
            sync.REGISTRY, "Makefile", "package.json", "site/package.json",
        ))
        self.original = {}
        for path in paths:
            relative = path.relative_to(ROOT)
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            self.original[relative.as_posix()] = path.read_text(encoding="utf-8")
        self.before = json.loads(self.original[sync.REGISTRY])

    def write_pins(self, pins):
        (self.root / sync.REGISTRY).write_text(json.dumps(pins, indent=2) + "\n")

    def run_sync(self, fetch=None):
        if fetch is None:
            def fetch(url):
                self.fail(f"unexpected download: {url}")
        return sync.synchronize(self.root, self.before, self.original.__getitem__, fetch)

    def assert_gate(self):
        canonical = vv.parse_canonical(self.root / "configs/pre-commit/.pre-commit-config.yaml")
        pins = vv.parse_tool_versions(self.root / sync.REGISTRY, canonical)
        self.assertEqual(vv.collect_install_mismatches(pins, self.root), [])
        self.assertEqual(vv.collect_toolchain_mismatches(pins, self.root), [])
        self.assertEqual(vv.evaluate(vv.collect_references(self.root), canonical)[0], [])
        self.assertEqual(vv.collect_floating(self.root)[0], [])

    def test_unchanged_registry_is_an_offline_no_op(self):
        self.assertEqual(self.run_sync(), [])
        self.assert_gate()

    def test_each_package_section_updates_every_checked_mirror_and_hooks(self):
        for section, name, version in (
            ("action", "actions/checkout", "v7.0.2@" + "a" * 40),
            ("docker", "hadolint/hadolint", "v2.14.1"),
            ("go", "github.com/golangci/golangci-lint/cmd/golangci-lint", "v1.62.1"),
            ("npm", "@biomejs/biome", "2.5.13"),
            ("python", "sqlfluff", "3.5.1"),
        ):
            pins = json.loads((self.root / sync.REGISTRY).read_text())
            pins[section][name] = version
            self.write_pins(pins)
            with self.subTest(section=section):
                self.assertTrue(self.run_sync())
                self.assert_gate()
        checkout = (self.root / ".forgejo/workflows/doc-lint.yml").read_text()
        self.assertIn("actions/checkout@" + "a" * 40 + " # v7.0.2", checkout)

    def test_every_automated_entry_synchronizes_and_a_second_run_is_a_no_op(self):
        pins = copy.deepcopy(self.before)
        for section, tools in pins.items():
            for name, old in tools.items():
                if section == "checksum" or name == "mvdan.cc/sh/v3/cmd/shfmt":
                    continue
                if section == "action":
                    tools[name] = "v9.0.0@" + "b" * 40
                elif section == "docker" and old.startswith("sha256:"):
                    tools[name] = "sha256:" + "b" * 64
                else:
                    tools[name] = ("v" if old.startswith("v") else "") + "9.0.0"
        self.write_pins(pins)

        def fetch(url):
            tool = "actionlint" if "/rhysd/actionlint/" in url else "vale"
            return self.binary_fetch(tool, "9.0.0")(url)

        with patch.object(sync.subprocess, "run"):
            self.assertTrue(self.run_sync(fetch))
            self.assert_gate()
            self.assertEqual(self.run_sync(), [])

    def test_tag_only_action_updates_preserve_the_sha_and_refresh_comments(self):
        pins = copy.deepcopy(self.before)
        sha = pins["action"]["actions/checkout"].split("@")[1]
        pins["action"]["actions/checkout"] = f"v7.0.2@{sha}"
        self.write_pins(pins)
        self.run_sync()
        self.assertIn(
            f"actions/checkout@{sha} # v7.0.2",
            (self.root / ".forgejo/workflows/doc-lint.yml").read_text(),
        )
        self.assert_gate()

    def test_separately_versioned_hook_wrapper_requires_manual_selection(self):
        pins = copy.deepcopy(self.before)
        pins["go"]["mvdan.cc/sh/v3/cmd/shfmt"] = "v3.13.0"
        self.write_pins(pins)
        with self.assertRaisesRegex(ValueError, "wrapper revision manually"):
            self.run_sync()

    def test_digest_only_and_multiline_docker_mirrors_are_supported(self):
        pins = copy.deepcopy(self.before)
        name = "geerlingguy/docker-debian13-ansible"
        pins["docker"][name] = "sha256:" + "a" * 64
        self.write_pins(pins)
        self.run_sync()
        self.assert_gate()
        guide = (self.root / "guides/infrastructure/ansible.md").read_text()
        self.assertRegex(guide, re.escape(name) + r"@\\\n\s+sha256:" + "a" * 64)

    def binary_fetch(self, tool, version, corrupt=False, missing=False):
        def fetch(url):
            if url.endswith("_checksums.txt"):
                platforms = vv.BINARY_PLATFORMS[tool][1:] if missing else vv.BINARY_PLATFORMS[tool]
                return "".join(
                    f"{hashlib.sha256(platform.encode()).hexdigest()}  "
                    f"{tool}_{version}_{platform}.tar.gz\n"
                    for platform in platforms
                ).encode()
            for platform in vv.BINARY_PLATFORMS[tool]:
                if url.endswith(f"_{platform}.tar.gz"):
                    return b"corrupt" if corrupt else platform.encode()
            self.fail(f"unexpected URL: {url}")
        return fetch

    def test_binary_and_hook_updates_refresh_and_verify_all_archive_checksums(self):
        for section, name, tool in (
            ("binary", "actionlint", "actionlint"),
            ("binary", "vale", "vale"),
            ("hook", "vale-cli/vale", "vale"),
        ):
            with self.subTest(section=section, name=name):
                pins = copy.deepcopy(self.before)
                pins[section][name] = "v9.0.0" if section == "hook" else "9.0.0"
                self.write_pins(pins)
                self.run_sync(self.binary_fetch(tool, "9.0.0"))
                self.assert_gate()
                current = json.loads((self.root / sync.REGISTRY).read_text())
                for platform in vv.BINARY_PLATFORMS[tool]:
                    archive = f"{tool}_9.0.0_{platform}.tar.gz"
                    self.assertEqual(
                        current["checksum"][archive],
                        "sha256:" + hashlib.sha256(platform.encode()).hexdigest(),
                    )

    def test_checksum_failures_do_not_rewrite_mirrors(self):
        for corrupt, missing in ((True, False), (False, True)):
            pins = copy.deepcopy(self.before)
            pins["binary"]["actionlint"] = "9.0.0"
            self.write_pins(pins)
            with self.subTest(corrupt=corrupt, missing=missing):
                with self.assertRaises(ValueError):
                    self.run_sync(self.binary_fetch("actionlint", "9.0.0", corrupt, missing))
                self.assertEqual((self.root / "Makefile").read_text(), self.original["Makefile"])

    def test_native_action_update_is_adopted_into_registry_and_guides(self):
        path = self.root / ".forgejo/workflows/site.yml"
        tag, old = self.before["action"]["actions/checkout"].split("@")
        path.write_text(path.read_text().replace(old + f" # {tag}", "a" * 40 + " # v7.0.2"))
        self.run_sync()
        pins = json.loads((self.root / sync.REGISTRY).read_text())
        self.assertEqual(pins["action"]["actions/checkout"], "v7.0.2@" + "a" * 40)
        self.assert_gate()

    def test_native_npm_update_and_registry_update_refresh_the_other_manifest(self):
        site = self.root / "site/package.json"
        manifest = json.loads(site.read_text())
        manifest["devDependencies"]["typescript"] = self.before["npm"]["typescript"]
        site.write_text(json.dumps(manifest, indent=2) + "\n")
        self.original["site/package.json"] = site.read_text()
        path = self.root / "package.json"
        manifest = json.loads(path.read_text())
        manifest["devDependencies"]["typescript"] = "999.0.1"
        path.write_text(json.dumps(manifest, indent=2) + "\n")
        with patch.object(sync.subprocess, "run") as run:
            self.run_sync()
        self.assertEqual(run.call_count, 1)
        self.assertIn("--ignore-scripts", run.call_args.args[0])
        self.assertEqual(
            json.loads((self.root / "site/package.json").read_text())["devDependencies"]["typescript"],
            "999.0.1",
        )
        self.assert_gate()

    def test_registry_updates_do_not_downgrade_independently_pinned_npm_packages(self):
        path = self.root / "package.json"
        manifest = json.loads(path.read_text())
        manifest["devDependencies"]["typescript"] = "999.0.0"
        path.write_text(json.dumps(manifest, indent=2) + "\n")
        self.original["package.json"] = path.read_text()
        pins = copy.deepcopy(self.before)
        pins["npm"]["typescript"] = "6.0.4"
        self.write_pins(pins)
        with patch.object(sync.subprocess, "run"):
            self.run_sync()
        self.assertEqual(
            json.loads((self.root / "package.json").read_text())["devDependencies"]["typescript"],
            json.loads(self.original["package.json"])["devDependencies"]["typescript"],
        )
        self.assert_gate()

    def test_conflicting_native_and_registry_versions_fail_explicitly(self):
        pins = copy.deepcopy(self.before)
        pins["npm"]["typescript"] = "6.0.4"
        self.write_pins(pins)
        path = self.root / "site/package.json"
        manifest = json.loads(path.read_text())
        manifest["devDependencies"]["typescript"] = "6.0.5"
        path.write_text(json.dumps(manifest, indent=2) + "\n")
        with self.assertRaisesRegex(ValueError, "conflicting updates"):
            self.run_sync()

    def test_reference_payloads_are_never_rewritten(self):
        path = self.root / "reference/guide.md"
        path.parent.mkdir()
        original = "npx sqlfluff@3.5.0\npip install sqlfluff==3.5.0\n"
        path.write_text(original)
        pins = copy.deepcopy(self.before)
        pins["python"]["sqlfluff"] = "3.5.1"
        self.write_pins(pins)
        self.run_sync()
        self.assertEqual(path.read_text(), original)

    def test_released_changelogs_and_legal_notices_are_not_rewritten(self):
        paths = [
            self.root / name for name in ("CHANGELOG.md", "SITE-CHANGELOG.md", "THIRD_PARTY_NOTICES.md")
        ]
        original = "`pip install sqlfluff==3.5.0`\n"
        for path in paths:
            path.write_text(original)
        pins = copy.deepcopy(self.before)
        pins["python"]["sqlfluff"] = "3.5.1"
        self.write_pins(pins)
        self.run_sync()
        for path in paths:
            self.assertEqual(path.read_text(), original)


class RenovateConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "renovate.json").read_text())

    def test_every_registry_entry_is_extracted_or_explicitly_derived(self):
        registry = json.loads((ROOT / sync.REGISTRY).read_text())
        text = (ROOT / sync.REGISTRY).read_text()
        counts = Counter()
        for manager in self.config["customManagers"]:
            sections = re.findall(
                r'"(\w+)":', manager["matchStrings"][0].replace("\\", ""),
            )
            section = sections[0]
            selected = re.search(manager["matchStrings"][0], text)[0]
            pattern = re.sub(r"\(\?<(\w+)>", r"(?P<\1>", manager["matchStrings"][1])
            counts[section] += len(re.findall(pattern, selected))
        for section, entries in registry.items():
            with self.subTest(section=section):
                self.assertEqual(counts[section], 0 if section == "checksum" else len(entries))
        self.assertEqual(set(registry["binary"]), set(sync.BINARY_REPOS))
        self.assertEqual(
            len(registry["checksum"]),
            sum(len(platforms) for platforms in vv.BINARY_PLATFORMS.values()),
        )

    def test_review_only_schedule_and_security_overrides(self):
        self.assertIn("config:best-practices", self.config["extends"])
        self.assertFalse(self.config["automerge"])
        self.assertFalse(self.config["platformAutomerge"])
        self.assertEqual(self.config["minimumReleaseAge"], "3 days")
        self.assertEqual(self.config["timezone"], "America/Los_Angeles")
        self.assertTrue(self.config["osvVulnerabilityAlerts"])
        self.assertEqual(self.config["vulnerabilityAlerts"]["minimumReleaseAge"], "0 days")
        self.assertIn("reference/**", self.config["ignorePaths"])
        self.assertEqual(self.config["packageRules"][0]["semanticCommitType"], "chore")
        self.assertEqual(self.config["packageRules"][0]["matchPackageNames"], ["*"])

    def test_forge_runs_strict_validation_using_the_pinned_make_target(self):
        steps = load_workflow(ROOT / ".forgejo/workflows/config-validation.yml")[
            "jobs"
        ]["renovate"]["steps"]
        self.assertIn("make renovate-check", [step.get("run") for step in steps])
        makefile = (ROOT / "Makefile").read_text()
        self.assertRegex(makefile, r"check:.* renovate-check")
        self.assertIn("renovate@$(RENOVATE_VERSION) renovate-config-validator --strict", makefile)


if __name__ == "__main__":
    unittest.main()
