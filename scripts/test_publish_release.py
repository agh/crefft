"""Exercise release refusal and dry runs with signed, local-only Git fixtures."""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import publish_release  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/publish_release.py"
TAG = "v2026.10.4"


class PublishReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.clone = self.root / "maintainer"
        self.clone.mkdir()
        self.env = {
            **os.environ,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_AUTHOR_NAME": "Release Tests",
            "GIT_AUTHOR_EMAIL": "release@example.com",
            "GIT_COMMITTER_NAME": "Release Tests",
            "GIT_COMMITTER_EMAIL": "release@example.com",
        }
        for name in tuple(self.env):
            if name.startswith("GIT_CONFIG_") and name not in {
                "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL",
            }:
                del self.env[name]
            elif name in {
                "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            }:
                del self.env[name]
        self.key = self.root / "signing-key"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(self.key)],
            env=self.env, check=True, capture_output=True,
        )
        self.signers = self.root / "allowed-signers"
        self.signers.write_text(
            f"release@example.com {self.key.with_suffix('.pub').read_text()}",
            encoding="utf-8",
        )
        self.git("init", "--quiet", "--initial-branch=main")
        for key, value in (
            ("user.name", "Release Tests"),
            ("user.email", "release@example.com"),
            ("gpg.format", "ssh"),
            ("user.signingkey", str(self.key)),
            ("gpg.ssh.allowedSignersFile", str(self.signers)),
        ):
            self.git("config", key, value)
        self.base = self.commit("2026.10.3")
        self.commit_id = self.commit(TAG[1:])
        self.git("tag", "-s", "-m", f"Release {TAG}", TAG)
        self.tag_object = self.git("rev-parse", f"refs/tags/{TAG}")
        for remote in ("forge", "github"):
            path = self.root / f"{remote}.git"
            self.git("init", "--quiet", "--bare", str(path))
            self.git("remote", "add", remote, str(path))
            # Seed bare remotes by fetching from the fixture, never by pushing.
            self.git(
                "--git-dir", str(path), "fetch", "--quiet", "--no-tags", str(self.clone),
                f"{self.commit_id if remote == 'forge' else self.base}:refs/heads/main",
                *([f"refs/tags/{TAG}:refs/tags/{TAG}"] if remote == "forge" else []),
            )

    def git(self, *args: str, input: str | None = None) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.clone, env=self.env, input=input,
            check=True, capture_output=True, text=True,
        ).stdout.strip()

    def commit(self, version: str) -> str:
        (self.clone / "VERSION").write_text(f"{version}\n", encoding="utf-8")
        self.git("add", "VERSION")
        self.git(
            "commit", "-S", "--quiet", "-m", f"Release fixture {version}",
            "-m", "Signed-off-by: Release Tests <release@example.com>",
        )
        return self.git("rev-parse", "HEAD")

    def remote_ref(self, remote: str, ref: str, value: str | None = None) -> None:
        args = ("--git-dir", str(self.root / f"{remote}.git"), "update-ref")
        if value:
            self.git(*args, ref, value)
        else:
            self.git(*args, "-d", ref)

    def remote_refs(self) -> list[str]:
        return [
            self.git("--git-dir", str(self.root / f"{remote}.git"), "show-ref")
            for remote in ("forge", "github")
        ]

    def run_publisher(self, tag: str = TAG) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), f"--tag={tag}"],
            cwd=self.clone, env=self.env, capture_output=True, text=True,
        )

    def assert_refused(self, message: str, tag: str = TAG) -> None:
        before = self.remote_refs()
        result = self.run_publisher(tag)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(message, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.remote_refs(), before)

    def test_dry_run_prints_exact_push_without_changing_either_remote(self):
        before = self.remote_refs()
        result = self.run_publisher()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, (
            f"git push github {self.commit_id}:refs/heads/main refs/tags/{TAG}\n"
        ))
        self.assertEqual(self.remote_refs(), before)
        self.assertEqual(self.git("rev-parse", "refs/remotes/forge/main"), self.commit_id)
        self.assertEqual(self.git("rev-parse", "refs/remotes/github/main"), self.base)

    def test_make_target_runs_the_guard_and_prints_the_exact_dry_run(self):
        script = self.clone / "scripts/publish_release.py"
        script.parent.mkdir()
        shutil.copy2(SCRIPT, script)
        result = subprocess.run(
            ["make", "--no-print-directory", "-f", str(ROOT / "Makefile"),
             "publish-release", f"TAG={TAG}"],
            cwd=self.clone, env=self.env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, (
            f"git push github {self.commit_id}:refs/heads/main refs/tags/{TAG}\n"
        ))

    def test_missing_local_tag_is_refused_and_not_fetched_over_it(self):
        self.git("update-ref", "-d", f"refs/tags/{TAG}")
        self.assert_refused("rev-parse")
        self.assertEqual(self.git("tag", "--list"), "")

    def test_missing_forge_tag_is_refused(self):
        self.remote_ref("forge", f"refs/tags/{TAG}")
        self.assert_refused("same object")

    def test_different_tag_objects_at_the_same_commit_are_refused(self):
        self.git("tag", "-s", "-m", "Different annotation", "other")
        other = self.git("rev-parse", "refs/tags/other")
        self.git(
            "--git-dir", str(self.root / "forge.git"), "fetch", "--quiet",
            "--no-tags", str(self.clone), "refs/tags/other:refs/tags/other",
        )
        self.remote_ref("forge", f"refs/tags/{TAG}", other)
        self.assert_refused("same object")
        self.assertEqual(self.git("rev-parse", f"refs/tags/{TAG}"), self.tag_object)

    def test_lightweight_tag_is_refused(self):
        self.git("update-ref", f"refs/tags/{TAG}", self.commit_id)
        self.remote_ref("forge", f"refs/tags/{TAG}", self.commit_id)
        self.assert_refused("must be annotated")

    def test_unsigned_annotated_tag_is_refused(self):
        self.git("tag", "--no-sign", "-a", "-m", "Unsigned", "unsigned")
        self.replace_tag(self.git("rev-parse", "refs/tags/unsigned"))
        self.assert_refused("tag -v")

    def replace_tag(self, object_id: str) -> None:
        self.git("update-ref", f"refs/tags/{TAG}", object_id)
        self.git(
            "--git-dir", str(self.root / "forge.git"), "fetch", "--quiet", "--no-tags",
            str(self.clone), f"+refs/tags/{TAG}:refs/tags/{TAG}",
        )

    def test_invalid_signature_is_refused(self):
        data = self.git("cat-file", "tag", self.tag_object)
        changed = data.replace(f"Release {TAG}", "Tampered annotation") + "\n"
        self.replace_tag(self.git("hash-object", "-w", "-t", "tag", "--stdin", input=changed))
        self.assert_refused("tag -v")

    def test_untrusted_signer_is_refused(self):
        self.signers.write_text("", encoding="utf-8")
        self.assert_refused("tag -v")

    def test_a_signed_tag_with_a_different_name_cannot_be_aliased_as_a_release(self):
        self.git("tag", "-s", "-m", "Not a release tag", "other")
        self.replace_tag(self.git("rev-parse", "refs/tags/other"))
        self.assert_refused("signed tag name must match the release ref")

    def test_tag_must_match_version_at_its_commit(self):
        wrong = "v2026.10.5"
        self.git("tag", "-s", "-m", "Wrong version", wrong)
        self.git(
            "--git-dir", str(self.root / "forge.git"), "fetch", "--quiet", "--no-tags",
            str(self.clone), f"refs/tags/{wrong}:refs/tags/{wrong}",
        )
        self.assert_refused("VERSION at the tagged commit", wrong)

    def test_missing_version_at_tag_is_refused(self):
        self.git("rm", "VERSION")
        self.git(
            "commit", "-S", "--quiet", "-m", "Remove fixture version",
            "-m", "Signed-off-by: Release Tests <release@example.com>",
        )
        self.git("tag", "-f", "-s", "-m", "Missing version", TAG)
        self.replace_tag(self.git("rev-parse", f"refs/tags/{TAG}"))
        self.assert_refused(":VERSION")

    def test_worktree_version_and_head_do_not_select_the_publication(self):
        self.git("checkout", "--quiet", "--detach", self.base)
        (self.clone / "VERSION").write_text("2099.1.0\n", encoding="utf-8")
        result = self.run_publisher()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"{self.commit_id}:refs/heads/main", result.stdout)

    def test_tagged_commit_must_be_forge_main(self):
        self.remote_ref("forge", "refs/heads/main", self.base)
        self.assert_refused("tagged commit must be forge/main")

    def test_diverged_github_main_is_refused(self):
        tree = self.git("rev-parse", f"{self.base}^{{tree}}")
        other = self.git("commit-tree", "-S", tree, "-p", self.base, input="Divergent fixture\n")
        self.git(
            "--git-dir", str(self.root / "github.git"), "fetch", "--quiet", "--no-tags",
            str(self.clone), f"{other}:refs/heads/other",
        )
        self.remote_ref("github", "refs/heads/main", other)
        self.assert_refused("merge-base --is-ancestor")

    def test_github_main_at_the_release_commit_is_allowed(self):
        self.git(
            "--git-dir", str(self.root / "github.git"), "fetch", "--quiet", "--no-tags",
            str(self.clone), f"{self.commit_id}:refs/heads/main",
        )
        self.assertEqual(self.run_publisher().returncode, 0)

    def test_missing_remote_or_main_fails_even_with_stale_tracking_refs(self):
        self.assertEqual(self.run_publisher().returncode, 0)
        for remote in ("forge", "github"):
            with self.subTest(remote=remote):
                value = self.git("rev-parse", f"refs/remotes/{remote}/main")
                self.remote_ref(remote, "refs/heads/main")
                # show-ref exits nonzero for an empty remote, so inspect the guard directly.
                result = self.run_publisher()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"fetch --no-tags {remote}", result.stderr)
                self.remote_ref(remote, "refs/heads/main", value)
        self.git("remote", "remove", "forge")
        self.assert_refused("fetch --no-tags forge")

    def test_invalid_tag_names_are_rejected_before_fetching(self):
        for tag in ("main", "--all", "", "v2026.0.0", "v2026.13.0", "v2026.10.01"):
            with self.subTest(tag=tag):
                self.assert_refused("tag must be a release name", tag)

    def test_explicit_push_executes_only_the_verified_command(self):
        command = ["git", "push", "github", f"{self.commit_id}:refs/heads/main", f"refs/tags/{TAG}"]
        with (
            patch.object(publish_release, "release_push", return_value=command) as guard,
            patch.object(publish_release.subprocess, "run") as run,
            patch.object(sys, "argv", ["publish_release.py", "--tag", TAG, "--push"]),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(publish_release.main(), 0)
        guard.assert_called_once_with(TAG)
        run.assert_called_once_with(command, check=True)
        self.assertEqual(output.getvalue(), " ".join(command) + "\n")

    def test_explicit_push_does_not_run_after_a_refusal(self):
        with (
            patch.object(publish_release, "release_push", side_effect=ValueError("blocked")),
            patch.object(publish_release.subprocess, "run") as run,
            patch.object(sys, "argv", ["publish_release.py", "--tag", TAG, "--push"]),
            contextlib.redirect_stderr(io.StringIO()) as error,
        ):
            self.assertEqual(publish_release.main(), 1)
        run.assert_not_called()
        self.assertIn("blocked", error.getvalue())


if __name__ == "__main__":
    unittest.main()
