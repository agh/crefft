#!/usr/bin/env python3
"""Exercise the real sync applier with isolated release checkouts and projects.

Run with:
    python3 -m unittest scripts.test_sync_claude_config -v

Workflow tests use js-yaml from the existing npm documentation toolchain.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/sync-claude-config.sh"
TEMPLATE = ROOT / "configs/github/workflows/sync-crefft.yml"
RELEASE = "v2026.10.0"
# The sync template defaults to the first release that ships this applier.
TEMPLATE_DEFAULT_REF = "v2026.10.1"
PAYLOADS = {
    "agents/code/reviewer.md": b"Review code.\n",
    "commands/code.md": b"Check code.\n",
    "configs/claude/skills/README.md": b"Use skills.\n",
    "configs/claude/skills/example/check.sh": b"#!/bin/sh\nexit 0\n",
    "configs/claude/infrastructure/README.md": b"Infrastructure context.\n",
    "configs/claude/settings.json": b'{"permissions": {}}\n',
}


def tree_hash(root: Path) -> str:
    """Include paths, contents, modes, links, and mtimes to detect any writes."""
    entries = []
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        content = None
        if path.is_symlink():
            content = os.readlink(path)
        elif path.is_file():
            content = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append(
            (str(path.relative_to(root)), info.st_mode, info.st_mtime_ns, content)
        )
    return hashlib.sha256(json.dumps(entries).encode()).hexdigest()


def load_workflow(path: Path = TEMPLATE) -> dict:
    if not (ROOT / "node_modules").exists():
        raise unittest.SkipTest("YAML checks require npm documentation tools (make check)")
    parsed = subprocess.run(
        [
            "node",
            "-e",
            "const fs = require('node:fs');"
            "console.log(JSON.stringify(require('js-yaml').load("
            "fs.readFileSync(process.argv[1], 'utf8'))));",
            str(path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(parsed.stdout)


class SyncFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.upstream = self.root / ".crefft-upstream"
        self.upstream.mkdir()
        self.project = self.root / "project"
        self.project.mkdir()
        self.dest = self.project / ".claude"
        self.receipt = self.dest / "crefft-receipt.json"
        self.script = self.upstream / "scripts/sync-claude-config.sh"
        self.script.parent.mkdir()
        shutil.copy2(SCRIPT, self.script)
        for name, data in PAYLOADS.items():
            path = self.upstream / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (self.upstream / "configs/claude/skills/example/check.sh").chmod(0o755)
        (self.upstream / "VERSION").write_text("2026.10.0\n", encoding="utf-8")
        self.git("init", "--quiet")
        self.git("config", "user.name", "Sync Tests")
        self.git("config", "user.email", "sync@example.com")
        self.commit = self.release(RELEASE)

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
            cwd=self.upstream,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def release(self, tag: str) -> str:
        (self.upstream / "VERSION").write_text(f"{tag[1:]}\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", f"Release {tag}")
        self.git("tag", tag)
        return self.git("rev-parse", "HEAD")

    def sync(self, *args: str, ref: str = RELEASE) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(self.script), str(self.project), "--ref", ref, *args],
            cwd=self.project,
            capture_output=True,
            text=True,
        )

    def install(self, *args: str, ref: str = RELEASE) -> dict:
        result = self.sync(*args, ref=ref)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.receipt.is_file(), "sync did not write an ownership receipt")
        return json.loads(self.receipt.read_text(encoding="utf-8"))

    def project_file(self, relative: str, content: bytes = b"Project-owned.\n") -> Path:
        path = self.dest / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def assert_unchanged_failure(self, *args: str, ref: str = RELEASE) -> str:
        before = tree_hash(self.project)
        result = self.sync(*args, ref=ref)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(tree_hash(self.project), before, result.stderr)
        return result.stderr


class SyncTests(SyncFixture):
    def test_clean_install_records_every_file_and_release_commit(self):
        receipt = self.install("--commit", self.commit)
        self.assertEqual(receipt["release"], RELEASE)
        self.assertEqual(receipt["commit"], self.commit)
        installed = {
            str(path.relative_to(self.dest)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.dest.rglob("*")
            if path.is_file() and path != self.receipt
        }
        self.assertEqual(receipt["files"], installed)
        self.assertEqual(len(installed), len(PAYLOADS))
        self.assertTrue(os.access(self.dest / "skills/example/check.sh", os.X_OK))

    def test_second_run_changes_nothing_including_receipt_and_mtimes(self):
        self.install()
        before = tree_hash(self.project)
        self.install()
        self.assertEqual(tree_hash(self.project), before)

    def test_project_agents_commands_and_skills_survive_every_run(self):
        local = [
            self.project_file("agents/local.md"),
            self.project_file("commands/local.md"),
            self.project_file("skills/local/check.md"),
        ]
        self.install()
        self.install()
        for path in local:
            self.assertEqual(path.read_bytes(), b"Project-owned.\n")

    def test_all_unowned_conflicts_are_reported_before_any_write(self):
        self.project_file("agents/code/reviewer.md")
        self.project_file("commands/code.md")
        error = self.assert_unchanged_failure()
        self.assertIn(".claude/agents/code/reviewer.md", error)
        self.assertIn(".claude/commands/code.md", error)

    def test_existing_settings_are_preserved_and_not_claimed(self):
        path = self.project_file("settings.json", b'{"project": true}\n')
        receipt = self.install()
        self.assertEqual(path.read_bytes(), b'{"project": true}\n')
        self.assertNotIn("settings.json", receipt["files"])
        self.install()
        self.assertEqual(path.read_bytes(), b'{"project": true}\n')

    def test_missing_source_components_fail_before_any_write(self):
        for component in ("agents", "commands", "skills", "infrastructure", "settings.json"):
            relative = component
            if component not in ("agents", "commands"):
                relative = f"configs/claude/{component}"
            source = self.upstream / relative
            saved = self.root / f"saved-{component}"
            with self.subTest(component=component):
                source.rename(saved)
                try:
                    error = self.assert_unchanged_failure()
                    self.assertIn("missing source", error)
                    self.assertIn(str(source), error)
                finally:
                    saved.rename(source)

    def test_removed_upstream_file_is_deleted_only_when_receipt_owned(self):
        self.install()
        local = self.project_file("agents/local.md")
        (self.upstream / "commands/code.md").unlink()
        (self.upstream / "commands/replacement.md").write_bytes(b"Replacement.\n")
        commit = self.release("v2026.10.1")
        receipt = self.install(ref="v2026.10.1")
        self.assertFalse((self.dest / "commands/code.md").exists())
        self.assertNotIn("commands/code.md", receipt["files"])
        self.assertEqual(local.read_bytes(), b"Project-owned.\n")
        self.assertEqual(receipt["commit"], commit)
        self.assertEqual(receipt["release"], "v2026.10.1")
        other_project = self.root / "other-project"
        other_project.mkdir()
        self.project = other_project
        self.dest = other_project / ".claude"
        self.receipt = self.dest / "crefft-receipt.json"
        unowned = self.project_file("commands/code.md", b"Not installed by crefft.\n")
        receipt = self.install(ref="v2026.10.1")
        self.assertEqual(unowned.read_bytes(), b"Not installed by crefft.\n")
        self.assertNotIn("commands/code.md", receipt["files"])

    def test_identical_unowned_files_require_explicit_content_only_adoption(self):
        path = self.project_file("agents/code/reviewer.md", PAYLOADS["agents/code/reviewer.md"])
        path.chmod(0o600)
        self.assertIn(".claude/agents/code/reviewer.md", self.assert_unchanged_failure())
        receipt = self.install("--adopt")
        self.assertIn("agents/code/reviewer.md", receipt["files"])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.read_bytes(), PAYLOADS["agents/code/reviewer.md"])

    def test_adopt_refuses_different_content(self):
        self.project_file("agents/code/reviewer.md")
        self.assertIn(".claude/agents/code/reviewer.md", self.assert_unchanged_failure("--adopt"))

    def test_overwrite_settings_is_explicit(self):
        path = self.project_file("settings.json", b'{"project": true}\n')
        receipt = self.install("--overwrite-settings")
        self.assertEqual(path.read_bytes(), PAYLOADS["configs/claude/settings.json"])
        self.assertIn("settings.json", receipt["files"])

    def test_owned_settings_are_kept_on_upgrade_unless_overwrite_is_requested(self):
        receipt = self.install()
        path = self.dest / "settings.json"
        path.write_bytes(b'{"local": true}\n')
        (self.upstream / "configs/claude/settings.json").write_bytes(b'{"new": true}\n')
        self.release("v2026.10.1")
        updated = self.install(ref="v2026.10.1")
        self.assertEqual(path.read_bytes(), b'{"local": true}\n')
        self.assertEqual(updated["files"]["settings.json"], receipt["files"]["settings.json"])
        self.install("--overwrite-settings", ref="v2026.10.1")
        self.assertEqual(path.read_bytes(), b'{"new": true}\n')

    def test_wrong_commit_or_nonrelease_ref_fails_before_any_write(self):
        self.assertIn("commit", self.assert_unchanged_failure("--commit", "0" * 40))
        self.assertIn("release tag", self.assert_unchanged_failure(ref="main"))
        self.assertIn("full commit SHA", self.assert_unchanged_failure("--commit", "abcd"))

    def test_checkout_must_match_tag_and_have_clean_sources(self):
        (self.upstream / "agents/code/reviewer.md").write_bytes(b"Unreleased.\n")
        self.assertIn("modified source", self.assert_unchanged_failure())
        self.release("v2026.10.1")
        self.assertIn("checkout", self.assert_unchanged_failure())

    def test_ignored_source_files_cannot_bypass_release_verification(self):
        (self.upstream / ".gitignore").write_text("agents/ignored.md\n", encoding="utf-8")
        self.release("v2026.10.1")
        (self.upstream / "agents/ignored.md").write_bytes(b"Not part of the release.\n")
        self.assertIn("modified source", self.assert_unchanged_failure(ref="v2026.10.1"))

    def test_modified_owned_files_block_replacement_and_removal(self):
        self.install()
        self.project_file("commands/code.md", b"Local edit.\n")
        self.assertIn("modified owned file", self.assert_unchanged_failure())
        (self.upstream / "commands/code.md").unlink()
        (self.upstream / "commands/replacement.md").write_bytes(b"Replacement.\n")
        self.release("v2026.10.1")
        self.assertIn(
            "modified owned file", self.assert_unchanged_failure(ref="v2026.10.1")
        )

    def test_symlink_destinations_and_parent_collisions_are_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.dest.symlink_to(outside, target_is_directory=True)
        self.assertIn(".claude", self.assert_unchanged_failure())
        self.assertEqual(list(outside.iterdir()), [])
        self.dest.unlink()
        self.dest.mkdir()
        (self.dest / "agents").symlink_to(outside, target_is_directory=True)
        self.assertIn(".claude/agents", self.assert_unchanged_failure())
        self.assertEqual(list(outside.iterdir()), [])
        (self.dest / "agents").unlink()
        self.project_file("agents", b"Not a directory.\n")
        self.assertIn(".claude/agents", self.assert_unchanged_failure())

    def test_invalid_receipt_cannot_authorize_writes_outside_components(self):
        receipt = self.install()
        for name in ("../outside", "/tmp/outside", "crefft-receipt.json", "hooks/local.sh"):
            with self.subTest(name=name):
                receipt["files"] = {name: "0" * 64}
                self.receipt.write_text(json.dumps(receipt), encoding="utf-8")
                self.assertIn("invalid receipt", self.assert_unchanged_failure())

    def test_malformed_receipt_fails_without_changes(self):
        self.project_file("crefft-receipt.json", b"not json")
        self.assertIn("invalid receipt", self.assert_unchanged_failure())

    def test_upgrade_conflicts_do_not_partially_apply_additions_or_removals(self):
        self.install()
        self.project_file("agents/new.md")
        (self.upstream / "agents/new.md").write_bytes(b"New upstream file.\n")
        (self.upstream / "commands/code.md").unlink()
        (self.upstream / "commands/new.md").write_bytes(b"New command.\n")
        self.release("v2026.10.1")
        self.assertIn(
            ".claude/agents/new.md", self.assert_unchanged_failure(ref="v2026.10.1")
        )
        self.assertTrue((self.dest / "commands/code.md").is_file())
        self.assertFalse((self.dest / "commands/new.md").exists())

    def test_source_symlinks_are_rejected_before_writes(self):
        source = self.upstream / "commands/link.md"
        source.symlink_to(self.root / "outside")
        self.release("v2026.10.1")
        self.assertIn("source symlink", self.assert_unchanged_failure(ref="v2026.10.1"))


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = load_workflow()
        cls.steps = cls.workflow["jobs"]["sync"]["steps"]

    def test_preview_does_not_interpolate_step_outputs_into_shell_source(self):
        preview = next(step for step in self.steps if step["name"] == "Dry run summary")
        for step in self.steps:
            self.assertNotIn("${{ steps.", step.get("run", ""))
        self.assertIn("${{ steps.sync.outputs.report }}", preview["env"].values())
        self.assertIn("printf '%s\\n'", preview["run"])

    def test_template_uses_only_the_pinned_applier_and_full_action_shas(self):
        self.assertEqual(self.workflow["env"]["CREFFT_REF"], TEMPLATE_DEFAULT_REF)
        self.assertIn("CREFFT_COMMIT", self.workflow["env"])
        sync = next(step for step in self.steps if step.get("id") == "sync")
        self.assertIn(".crefft-upstream/scripts/sync-claude-config.sh", sync["run"])
        self.assertNotIn("rsync", sync["run"])
        self.assertNotIn("SYNC_PATHS", self.workflow["env"])
        for step in self.steps:
            if "uses" in step:
                self.assertRegex(step["uses"], r"@[0-9a-f]{40}$")

    def test_preview_prints_shell_metacharacters_as_data(self):
        preview = next(step for step in self.steps if step["name"] == "Dry run summary")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = root / "summary"
            payload = "$(touch EXECUTED)"
            env = dict(os.environ, GITHUB_STEP_SUMMARY=str(summary))
            outputs = {
                "version": "2026.10.0",
                "changes": "true",
                "report": payload,
            }
            code = preview["run"]
            for name, value in outputs.items():
                code = code.replace("${{ steps.sync.outputs." + name + " }}", value)
            for key, expression in preview.get("env", {}).items():
                if "outputs.changes" in expression:
                    env[key] = "true"
                elif "outputs.report" in expression:
                    env[key] = payload
                else:
                    env[key] = "2026.10.0"
            result = subprocess.run(
                ["bash", "-eu", "-o", "pipefail", "-c", code],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertFalse(
                (root / "EXECUTED").exists(), "preview executed report content"
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(payload, summary.read_text(encoding="utf-8"))


class WorkflowExecutionTests(SyncFixture):
    @classmethod
    def setUpClass(cls):
        cls.workflow = load_workflow()
        cls.steps = cls.workflow["jobs"]["sync"]["steps"]

    def setUp(self):
        super().setUp()
        target = self.project / ".crefft-upstream"
        self.upstream.rename(target)
        self.upstream = target
        self.script = target / "scripts/sync-claude-config.sh"
        self.project_file("agents/local.md")
        self.project_file("settings.json", b'{"project": true}\n')
        self.project_git("init", "--quiet")
        self.project_git("config", "user.name", "Sync Tests")
        self.project_git("config", "user.email", "sync@example.com")
        self.project_git("add", ".claude")
        self.project_git("commit", "--quiet", "-m", "Project configuration")
        self.outputs = self.root / "outputs"
        self.outputs.touch()
        self.runner_temp = self.root / "runner-temp"
        self.runner_temp.mkdir()

    def project_git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-c", "commit.gpgsign=false", *args],
            cwd=self.project,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def run_step(self, *, dry_run: bool = False, commit: str | None = None):
        step = next(step for step in self.steps if step.get("id") == "sync")
        env = {
            **os.environ,
            **self.workflow["env"],
            "CREFFT_REF": RELEASE,
            "CREFFT_COMMIT": self.commit if commit is None else commit,
            "GITHUB_OUTPUT": str(self.outputs),
            "GITHUB_WORKSPACE": str(self.project),
            "RUNNER_TEMP": str(self.runner_temp),
            "DRY_RUN": "true" if dry_run else "false",
        }
        return subprocess.run(
            ["bash", "-eu", "-o", "pipefail", "-c", step["run"]],
            cwd=self.project,
            env=env,
            capture_output=True,
            text=True,
        )

    def test_real_template_installs_via_script_and_preserves_project_files(self):
        result = self.run_step()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.dest / "settings.json").read_bytes(), b'{"project": true}\n')
        self.assertEqual((self.dest / "agents/local.md").read_bytes(), b"Project-owned.\n")
        receipt = json.loads(self.receipt.read_text(encoding="utf-8"))
        self.assertEqual(receipt["commit"], self.commit)
        self.assertIn("changes=true", self.outputs.read_text(encoding="utf-8"))

    def test_optional_commit_and_unchanged_release_report_no_changes(self):
        result = self.run_step(commit="")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.receipt.is_file())
        self.project_git("add", ".claude")
        self.project_git("commit", "--quiet", "-m", "Install pinned configuration")
        before = tree_hash(self.dest)
        self.outputs.write_bytes(b"")
        result = self.run_step(commit="")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(tree_hash(self.dest), before)
        self.assertIn("changes=false", self.outputs.read_text(encoding="utf-8"))

    def test_dry_run_keeps_workspace_and_reports_changes_then_cleans_preview(self):
        before = tree_hash(self.dest)
        unrelated = self.project / "local-notes.txt"
        unrelated.write_bytes(b"Untracked project notes.\n")
        result = self.run_step(dry_run=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(tree_hash(self.dest), before)
        self.assertEqual(unrelated.read_bytes(), b"Untracked project notes.\n")
        self.assertIn("changes=true", self.outputs.read_text(encoding="utf-8"))
        self.assertEqual(list(self.runner_temp.iterdir()), [])

    def test_invalid_versions_are_rejected_before_writes_or_exports(self):
        for version in (
            "2026.00.0\n", "2026.13.0\n", "2026.01.0\n", "2026.10.01\n",
            "2026.10.0\n2026.10.1\n", "$(touch EXECUTED)\n", "2026.10.0\n\n",
        ):
            with self.subTest(version=version):
                (self.upstream / "VERSION").write_text(version, encoding="utf-8")
                before = tree_hash(self.dest)
                result = self.run_step()
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("VERSION", result.stderr)
                self.assertEqual(tree_hash(self.dest), before)
                self.assertEqual(self.outputs.read_bytes(), b"")
                self.assertFalse((self.project / "EXECUTED").exists())

    def test_commit_mismatch_is_rejected_before_executing_upstream_script(self):
        self.script.write_text("#!/bin/sh\ntouch EXECUTED\n", encoding="utf-8")
        before = tree_hash(self.dest)
        result = self.run_step(commit="0" * 40)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("commit", result.stderr)
        self.assertFalse((self.project / "EXECUTED").exists())
        self.assertEqual(tree_hash(self.dest), before)
        self.assertEqual(self.outputs.read_bytes(), b"")


class GuideTests(unittest.TestCase):
    def test_legacy_anchor_is_immediately_before_sync_heading(self):
        text = (ROOT / "guides/ai/claude-code.md").read_text(encoding="utf-8")
        self.assertIn(
            '<a id="syncing-from-doctrine"></a>\n\n## Syncing from crefft\n', text
        )
        section = text.split("## Syncing from crefft\n", 1)[1].split("## See Also", 1)[0]
        for forbidden in ("archive/main", "rsync ", "cp -r", "checkout@v"):
            self.assertNotIn(forbidden, section)
        self.assertIn("--ref", section)
        self.assertIn("v2026.10.1", section)


if __name__ == "__main__":
    unittest.main()
