#!/usr/bin/env python3
"""Unit tests for scripts/validate_versions.py.

Run with:
    python3 -m unittest discover scripts
    python3 -m unittest scripts.test_validate_versions
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_versions as vv  # noqa: E402


class NormalizeRepoTests(unittest.TestCase):
    def test_https_url(self):
        self.assertEqual(
            vv.normalize_repo("https://github.com/astral-sh/ruff-pre-commit"),
            "astral-sh/ruff-pre-commit",
        )

    def test_https_url_with_git_suffix(self):
        self.assertEqual(vv.normalize_repo("https://github.com/psf/black.git"), "psf/black")

    def test_trailing_slash(self):
        self.assertEqual(vv.normalize_repo("https://github.com/psf/black/"), "psf/black")

    def test_scp_style_ssh_keeps_owner(self):
        # The previous implementation returned "tool", losing the owner.
        self.assertEqual(vv.normalize_repo("git@github.com:owner/tool.git"), "owner/tool")

    def test_ssh_protocol_url(self):
        self.assertEqual(vv.normalize_repo("ssh://git@github.com/owner/tool.git"), "owner/tool")

    def test_non_github_host(self):
        self.assertEqual(vv.normalize_repo("https://gitlab.com/group/project"), "group/project")

    def test_quoted_url(self):
        self.assertEqual(vv.normalize_repo('"https://github.com/psf/black"'), "psf/black")

    def test_bare_owner_repo(self):
        self.assertEqual(vv.normalize_repo("psf/black"), "psf/black")

    def test_two_owners_are_distinct(self):
        # Suffix matching used to conflate these; owner-preserving keys do not.
        self.assertNotEqual(
            vv.normalize_repo("https://github.com/dnephin/pre-commit-golang"),
            vv.normalize_repo("https://github.com/TekWizely/pre-commit-golang"),
        )


class ParseCanonicalTests(unittest.TestCase):
    def _write(self, text: str) -> Path:
        tmp = Path(self.tmpdir.name) / ".pre-commit-config.yaml"
        tmp.write_text(text, encoding="utf-8")
        return tmp

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def test_reads_active_entries(self):
        path = self._write(
            "repos:\n"
            "  - repo: https://github.com/psf/black\n"
            "    rev: 24.1.0\n"
            "    hooks:\n"
            "      - id: black\n"
        )
        self.assertEqual(vv.parse_canonical(path), {"psf/black": "24.1.0"})

    def test_reads_commented_entries(self):
        path = self._write(
            "repos:\n"
            "  # - repo: https://github.com/psf/black\n"
            "  #   rev: 24.1.0\n"
            "  #   hooks:\n"
            "  #     - id: black\n"
        )
        self.assertEqual(vv.parse_canonical(path), {"psf/black": "24.1.0"})

    def test_quoted_rev_is_unquoted(self):
        path = self._write("  - repo: https://github.com/psf/black\n    rev: \"24.1.0\"\n")
        self.assertEqual(vv.parse_canonical(path), {"psf/black": "24.1.0"})

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            vv.parse_canonical(Path(self.tmpdir.name) / "absent.yaml")

    def test_repo_without_rev_is_ignored(self):
        path = self._write("  - repo: local\n    hooks:\n      - id: something\n")
        self.assertEqual(vv.parse_canonical(path), {})


class CollectReferencesTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)

    def _guide(self, relative: str, body: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def test_finds_pair_in_fenced_block(self):
        self._guide(
            "guides/languages/python.md",
            "# Python\n\n```yaml\nrepos:\n"
            "  - repo: https://github.com/psf/black\n    rev: 24.1.0\n```\n",
        )
        refs = vv.collect_references(self.root)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].repo, "psf/black")
        self.assertEqual(refs[0].rev, "24.1.0")

    def test_scans_agents_and_configs(self):
        self._guide(
            "agents/code/reviewer.md",
            "- repo: https://github.com/psf/black\n  rev: 24.1.0\n",
        )
        self._guide(
            "configs/editorconfig/README.md",
            "- repo: https://github.com/psf/isort\n  rev: 5.13.2\n",
        )
        repos = {r.repo for r in vv.collect_references(self.root)}
        self.assertEqual(repos, {"psf/black", "psf/isort"})

    def test_skips_reference_tree(self):
        self._guide(
            "guides/reference/vendored.md",
            "- repo: https://github.com/psf/black\n  rev: 0.0.0\n",
        )
        self.assertEqual(vv.collect_references(self.root), [])

    def test_tolerates_intervening_key(self):
        self._guide(
            "guides/x.md",
            "- repo: https://github.com/psf/black\n  # comment key\n  rev: 24.1.0\n",
        )
        refs = vv.collect_references(self.root)
        self.assertEqual([r.rev for r in refs], ["24.1.0"])

    def test_records_line_number(self):
        self._guide("guides/x.md", "intro\n\n- repo: https://github.com/psf/black\n  rev: 24.1.0\n")
        self.assertEqual(vv.collect_references(self.root)[0].line, 3)

    def test_non_markdown_yaml_is_scanned(self):
        self._guide(
            "configs/ansible/extra.yaml",
            "- repo: https://github.com/psf/black\n  rev: 24.1.0\n",
        )
        self.assertEqual(len(vv.collect_references(self.root)), 1)

    def test_unrelated_extension_is_ignored(self):
        self._guide("configs/thing.json", "- repo: https://github.com/psf/black\n  rev: 24.1.0\n")
        self.assertEqual(vv.collect_references(self.root), [])


class EvaluateTests(unittest.TestCase):
    def _ref(self, repo: str, rev: str) -> vv.Reference:
        return vv.Reference(path=Path("guides/x.md"), line=1, repo=repo, rev=rev)

    def test_matching_version_is_clean(self):
        refs = [self._ref("psf/black", "24.1.0")]
        mismatches, unknown = vv.evaluate(refs, {"psf/black": "24.1.0"})
        self.assertEqual(mismatches, [])
        self.assertEqual(unknown, [])

    def test_mismatch_is_reported(self):
        refs = [self._ref("psf/black", "23.0.0")]
        mismatches, unknown = vv.evaluate(refs, {"psf/black": "24.1.0"})
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0]["found"], "23.0.0")
        self.assertEqual(mismatches[0]["expected"], "24.1.0")
        self.assertEqual(unknown, [])

    def test_undocumented_unknown_tool(self):
        _, unknown = vv.evaluate([self._ref("who/what", "1.0")], {"psf/black": "24.1.0"})
        self.assertEqual(len(unknown), 1)
        self.assertFalse(unknown[0]["documented"])

    def test_documented_unknown_tool(self):
        repo = next(iter(vv.KNOWN_UNPINNED))
        _, unknown = vv.evaluate([self._ref(repo, "1.0")], {"psf/black": "24.1.0"})
        self.assertTrue(unknown[0]["documented"])


class ExecutablePinTests(unittest.TestCase):
    def _find(self, text: str, suffix: str = ".md") -> list[tuple[str, str, str]]:
        return [
            reference
            for executable in vv.iter_executables(text, suffix)
            for reference in vv.floating_references(executable)
            if not executable.exception
        ]

    def test_package_managers_reject_floating_and_accept_exact_pins(self):
        cases = [
            ("go install example.com/tool@latest", "go install example.com/tool@v1.2.3"),
            ("go install example.com/tool", "go install example.com/tool@v1.2.3"),
            ("go get example.com/lib@main", "go get example.com/lib@v1.2.3"),
            ("go get example.com/lib", "go get example.com/lib@v1.2.3"),
            ("npx tool", "npx tool@1.2.3"),
            ("npx -y @scope/tool@latest", "npx -y @scope/tool@1.2.3"),
            ("npm install tool", "npm install tool@1.2.3"),
            ("npm install -D @scope/tool@^1.2.3", "npm install -D @scope/tool@1.2.3"),
            ("pnpm dlx tool", "pnpm dlx tool@1.2.3"),
            ("pip install tool", "pip install tool==1.2.3"),
            ("pip3 install 'tool>=1.2.3'", "pip3 install 'tool==1.2.3'"),
            ("uv tool install tool", "uv tool install tool==1.2.3"),
            ("uv pip install tool", "uv pip install tool==1.2.3"),
            ("pipx install tool", "pipx install tool==1.2.3"),
            ("uvx tool", "uvx tool==1.2.3"),
            ("cargo install tool", "cargo install tool --version 1.2.3 --locked"),
            ("cargo install tool --version '^1.2'", "cargo install tool --version=1.2.3"),
            ("docker run --rm tool:latest", "docker run --rm tool:1.2.3"),
            ("docker run tool", "docker run tool@sha256:" + "a" * 64),
        ]
        for floating, pinned in cases:
            for language in ("bash", "sh", "shell", "console", "zsh"):
                with self.subTest(command=floating, language=language):
                    self.assertTrue(self._find(f"```{language}\n{floating}\n```\n"))
                    self.assertEqual(self._find(f"```{language}\n{pinned}\n```\n"), [])
            with self.subTest(inline=floating):
                self.assertTrue(self._find(f"Run `{floating}`."))
                self.assertEqual(self._find(f"Run `{pinned}`."), [])

    def test_branch_and_tag_aliases_are_not_pins(self):
        for selector in ("latest", "main", "master", "HEAD", "next", "*", "^1.2.3", "~1.2.3"):
            with self.subTest(selector=selector):
                self.assertTrue(self._find(f"```sh\nnpx tool@{selector}\n```"))

    def test_pseudoversions_prereleases_and_cargo_shorthand_are_pinned(self):
        for command in (
            "go install example.com/tool@v0.0.0-20261009192801-be2c69fb417e",
            "npx tool@4.0.0-alpha.8",
            "cargo install --locked tool@1.2.3",
            "pip install 'tool[docker]==1.2.3'",
        ):
            with self.subTest(command=command):
                self.assertEqual(self._find(f"```sh\n{command}\n```"), [])

    def test_explicit_runner_package_is_checked_not_the_binary_name(self):
        self.assertEqual(
            self._find("`npx --package=typescript@6.0.3 tsc --noEmit`"), []
        )
        self.assertTrue(self._find("`npx --package typescript@latest tsc --noEmit`"))
        self.assertEqual(self._find("`uvx --from tool==1.2.3 tool-cli`"), [])
        self.assertTrue(self._find("`uvx --from tool tool-cli`"))

    def test_all_packages_are_checked(self):
        refs = self._find(
            "```sh\nnpm install good@1.2.3 bad\npip install good==1.2.3 bad\n```"
        )
        self.assertEqual([(kind, name) for kind, name, _ in refs],
                         [("npm", "bad"), ("python", "bad")])

    def test_shell_continuations_and_chained_commands_are_checked(self):
        text = (
            "```bash\nnpm install --save-dev \\\n"
            "  good@1.2.3 bad && go install example.com/tool@HEAD\n```"
        )
        self.assertEqual([name for _, name, _ in self._find(text)], ["bad", "example.com/tool"])

    def test_semicolons_without_spaces_and_multiple_docker_commands(self):
        self.assertTrue(self._find("```sh\nnpx good@1.2.3;npx bad\n```"))
        self.assertEqual(self._find("```sh\nnpx good@1.2.3;npx other@2.3.4\n```"), [])
        self.assertTrue(self._find("```sh\ndocker run good:1.2.3;docker run bad:latest\n```"))

    def test_multiline_inline_spans_and_double_backticks(self):
        self.assertTrue(self._find("Run `go install\nexample.com/tool@latest`."))
        self.assertEqual(self._find("Run ``go install example.com/tool@v1.2.3``."), [])

    def test_console_prompts_and_environment_prefixes_are_checked(self):
        self.assertTrue(self._find("```console\n$ CI=1 npx tool\n```"))
        self.assertEqual(self._find("```zsh\nCI=1 npx tool@1.2.3\n```"), [])

    def test_yaml_run_steps_scalar_literal_and_folded(self):
        for language in ("yaml", "yml"):
            for value in (
                "go install example.com/tool@latest",
                "'go install example.com/tool@latest'",
                "|\n    go install example.com/tool@latest\n    tool --help",
                ">-\n    go install\n    example.com/tool@latest",
            ):
                text = f"```{language}\n- run: {value}\n  name: install\n```"
                with self.subTest(language=language, value=value):
                    self.assertTrue(self._find(text))
                    self.assertEqual(self._find(text.replace("@latest", "@v1.2.3")), [])

    def test_quoted_yaml_run_keeps_inner_quotes(self):
        text = '```yaml\n- run: npx tool "**/*.md"\n```'
        self.assertEqual(self._find(text), [("npm", "tool", "")])
        self.assertEqual(self._find(text.replace("npx tool", "npx tool@1.2.3")), [])

    def test_yaml_nonexecutable_values_are_not_shell_commands(self):
        text = (
            "```yaml\nname: npx tool@latest\n"
            "env:\n  WARNING: go install example.com/tool@latest\n```"
        )
        self.assertEqual(self._find(text), [])

    def test_yaml_images_and_floating_actions(self):
        for value in ("image: tool:latest", "image: >-\n  tool:latest",
                      "uses: owner/action@master", "uses: owner/action@HEAD"):
            with self.subTest(value=value):
                self.assertTrue(self._find(f"```yaml\n{value}\n```"))
                pinned = value.replace(":latest", ":1.2.3").replace("@master", "@" + "a" * 40)
                pinned = pinned.replace("@HEAD", "@" + "a" * 40)
                self.assertEqual(self._find(f"```yaml\n{pinned}\n```"), [])

    def test_yaml_escaped_image_line_is_one_exact_digest(self):
        digest = "a" * 64
        text = '```yaml\nimage: "example.com/image@\\\n  sha256:' + digest + '"\n```'
        refs = [
            reference
            for executable in vv.iter_executables(text)
            for reference in vv.executable_references(executable)
        ]
        self.assertEqual(refs, [("docker", "example.com/image", "sha256:" + digest)])
        self.assertEqual(self._find(text), [])

    def test_dockerfile_commands_and_stage_aliases(self):
        text = "```dockerfile\nFROM python:latest AS base\nRUN pip install tool\nFROM base\n```"
        self.assertEqual(self._find(text),
                         [("docker", "python", "latest"), ("python", "tool", "")])
        pinned = text.replace("python:latest", "python:3.14.0").replace(
            "pip install tool", "pip install tool==1.2.3"
        )
        self.assertEqual(self._find(pinned), [])
        self.assertEqual(self._find("```dockerfile\nFROM scratch\n```"), [])

    def test_dockerfile_exec_form_and_platform_stage_alias(self):
        text = (
            '```dockerfile\nFROM --platform=$BUILDPLATFORM python:3.14.0 AS base\n'
            'RUN ["pip", "install", "tool"]\n'
            'FROM --platform=$TARGETPLATFORM base\n```'
        )
        self.assertEqual(self._find(text), [("python", "tool", "")])
        self.assertEqual(self._find(text.replace('"tool"', '"tool==1.2.3"')), [])

    def test_docker_run_options_and_registry_ports(self):
        text = (
            "```bash\ndocker run --rm --name test -e KEY=value -p 8000:80 \\\n"
            "  -v models:/data registry.example.com:5000/tool:latest --model example\n```"
        )
        self.assertEqual(self._find(text),
                         [("docker", "registry.example.com:5000/tool", "latest")])
        self.assertEqual(self._find(text.replace(":latest", ":1.2.3")), [])
        self.assertEqual(self._find(
            "```sh\ndocker run --pull always --platform linux/arm64 tool:1.2.3\n```"
        ), [])

    def test_docker_pull_and_podman_commands_are_checked(self):
        for command in ("docker pull", "podman pull", "podman run --rm"):
            with self.subTest(command=command):
                self.assertTrue(self._find(f"```sh\n{command} tool:latest\n```"))
                self.assertEqual(self._find(f"```sh\n{command} tool:1.2.3\n```"), [])

    def test_prose_comments_and_other_fences_are_exempt(self):
        text = (
            "Avoid @latest, @main, @master, @HEAD, and :latest in runnable installs.\n"
            "Pin `@playwright/mcp@latest` instead of copying it unchanged.\n"
            "```text\nnpx tool@latest\n```\n"
            "```json\n{\"command\": \"npx\", \"args\": [\"tool@latest\"]}\n```\n"
            "```bash\n# npx tool@latest\nprintf '%s' 'npx tool@latest'\n```\n"
        )
        self.assertEqual(self._find(text), [])

    def test_nested_nonexecutable_fences_and_tilde_fences(self):
        text = "````markdown\n```bash\nnpx tool@latest\n```\n````\n"
        self.assertEqual(self._find(text), [])
        self.assertTrue(self._find("  ~~~sh\nnpx tool@latest\n  ~~~\n"))

    def test_manifest_and_local_installs_do_not_resolve_new_tool_versions(self):
        for command in (
            "npm install", "pip install -r requirements.txt", "pip install .",
            "pip install --no-cache-dir --target=/deps -r requirements.txt",
            "go install ./cmd/tool", "go get ./...",
        ):
            with self.subTest(command=command):
                self.assertEqual(self._find(f"```bash\n{command}\n```"), [])
        self.assertTrue(self._find("```bash\ngo get -u ./...\n```"))

    def test_exception_applies_only_to_next_logical_command(self):
        text = (
            "```bash\n# crefft: allow-floating -- Demonstrate the unsafe install.\n"
            "go install \\\n  example.com/tool@latest\n"
            "npx tool\n```"
        )
        self.assertEqual(self._find(text), [("npm", "tool", "")])

    def test_exception_cannot_hide_a_second_chained_install(self):
        for operator in ("&&", ";", "||", "|"):
            with self.subTest(operator=operator):
                text = (
                    "```sh\n# crefft: allow-floating -- Negative example.\n"
                    f"npx tool {operator} npx other\n```"
                )
                self.assertEqual(self._find(text), [("npm", "other", "")])

    def test_exception_requires_reason_and_immediate_adjacency(self):
        for comment in (
            "# crefft: allow-floating", "# crefft: allow-floating -- ",
            "# crefft: allow-floating -- Negative example.\n",
            "# crefft: allow-floating -- Negative example.\n# Another comment",
        ):
            with self.subTest(comment=comment):
                self.assertTrue(self._find(f"```sh\n{comment}\nnpx tool\n```"))

    def test_yaml_and_dockerfile_exceptions(self):
        for language, command in (
            ("yaml", "image: tool:latest"), ("yaml", "- run: npx tool"),
            ("dockerfile", "FROM tool:latest"),
        ):
            text = (
                f"```{language}\n"
                "# crefft: allow-floating -- Negative example.\n"
                f"{command}\n```"
            )
            with self.subTest(language=language, command=command):
                self.assertEqual(self._find(text), [])

    def test_collector_reports_locations_exceptions_and_commands_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "commands" / "example.md"
            path.parent.mkdir()
            path.write_text(
                "```sh\n# crefft: allow-floating -- Negative example.\n"
                "npx tool\nnpx other\n```", encoding="utf-8",
            )
            findings, exceptions = vv.collect_floating(root)
            self.assertEqual(findings[0]["location"], "commands/example.md:4")
            self.assertEqual(exceptions[0]["location"], "commands/example.md:3")
            self.assertEqual(exceptions[0]["reason"], "Negative example.")

    def test_native_config_files_are_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configs = root / "configs"
            configs.mkdir()
            for filename, text in (
                ("Dockerfile", "FROM tool:latest"),
                ("install.sh", "go install example.com/tool"),
                ("workflow.yml", "steps:\n  - run: uv tool install tool"),
            ):
                (configs / filename).write_text(text, encoding="utf-8")
            findings, _ = vv.collect_floating(root)
            self.assertEqual(len(findings), 3)


class ActionPinTests(unittest.TestCase):
    SHA = "a" * 40
    MARKER = "# crefft: illustrative -- This nonexecuting example demonstrates a moving tag."

    def _scan(self, body: str, relative: str = "guides/example.md"):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / relative
            path.parent.mkdir(parents=True)
            path.write_text(body, encoding="utf-8")
            return vv.collect_floating(root)

    def test_moving_tags_branches_short_shas_and_expressions_fail(self):
        for ref in ("v7", "v7.0.1", "main", "a" * 39, "a" * 41, "${{ inputs.ref }}"):
            with self.subTest(ref=ref):
                findings, _ = self._scan(f"```yaml\n- uses: actions/checkout@{ref}\n```\n")
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0]["ecosystem"], "action")

    def test_full_sha_with_version_comment_passes(self):
        findings, exceptions = self._scan(
            f"```yaml\n- uses: actions/checkout@{self.SHA} # v7.0.1\n```\n"
        )
        self.assertEqual((findings, exceptions), ([], []))

    def test_scalar_suffixes_and_malformed_quotes_cannot_hide_invalid_refs(self):
        for value in (
            f"actions/checkout@{self.SHA}#suffix",
            f"'actions/checkout@{self.SHA} # part of the reference'",
            "'actions/checkout@v7",
        ):
            with self.subTest(value=value):
                findings, _ = self._scan(f"```yaml\n- uses: {value}\n```\n")
                self.assertEqual(len(findings), 1)

    def test_marked_illustration_passes_and_reports_reason(self):
        findings, exceptions = self._scan(
            f"```yaml\n{self.MARKER}\n- uses: actions/checkout@v7\n```\n"
        )
        self.assertEqual(findings, [])
        self.assertEqual(len(exceptions), 1)
        self.assertIn("nonexecuting", exceptions[0]["reason"])

    def test_marker_only_exempts_one_adjacent_reference(self):
        findings, exceptions = self._scan(
            f"```yaml\n{self.MARKER}\n- uses: actions/checkout@v7\n"
            "- uses: actions/setup-node@v7\n```\n"
        )
        self.assertEqual([f["package"] for f in findings], ["actions/setup-node"])
        self.assertEqual(len(exceptions), 1)

    def test_marker_requires_reason_and_immediate_adjacency(self):
        for marker in (
            "# crefft: illustrative -- ",
            self.MARKER + "\n",
            self.MARKER + "\n# Another comment",
            self.MARKER + "\n- name: Checkout",
        ):
            with self.subTest(marker=marker):
                findings, _ = self._scan(
                    f"```yaml\n{marker}\n- uses: actions/checkout@v7\n```\n"
                )
                self.assertEqual(len(findings), 1)

    def test_native_workflows_and_configs_cannot_use_illustrative_marker(self):
        for relative in (
            ".github/workflows/ci.yml", ".forgejo/workflows/ci.yml", "configs/workflow.yaml",
        ):
            with self.subTest(relative=relative):
                findings, exceptions = self._scan(
                    f"{self.MARKER}\n- uses: actions/checkout@v7\n", relative
                )
                self.assertEqual(len(findings), 1)
                self.assertEqual(exceptions, [])

    def test_allow_floating_cannot_exempt_an_action(self):
        findings, exceptions = self._scan(
            "```yaml\n# crefft: allow-floating -- Negative example.\n"
            "- uses: actions/checkout@v7\n```\n"
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(exceptions, [])

    def test_reusable_workflow_reference_is_checked(self):
        reference = "example/build/.github/workflows/release.yml"
        for ref in ("v1.2.3", self.SHA):
            with self.subTest(ref=ref):
                findings, _ = self._scan(
                    f"```yaml\njobs:\n  release:\n    uses: {reference}@{ref}\n```\n"
                )
                self.assertEqual(len(findings), int(ref != self.SHA))

    def test_quoted_folded_and_flow_references_are_checked(self):
        for value in (
            '- "uses": "actions/checkout@v7"',
            "- uses: >- # reviewed release\n    actions/checkout@v7",
            "- {name: Checkout, uses: 'actions/checkout@v7'}",
            "steps: [{uses: actions/checkout@v7}]",
            "jobs: {build: {uses: 'actions/checkout@v7'}}",
        ):
            with self.subTest(value=value):
                findings, _ = self._scan(f"```yml\n{value}\n```\n")
                self.assertEqual(len(findings), 1)
                findings, _ = self._scan(f"```yml\n{value.replace('@v7', '@' + self.SHA)}\n```")
                self.assertEqual(findings, [])

    def test_generic_fence_skip_marker_cannot_bypass_pin_check(self):
        findings, _ = self._scan("~~~yaml no-check\n- uses: actions/checkout@v7\n~~~\n")
        self.assertEqual(len(findings), 1)

    def test_empty_reference_is_rejected(self):
        findings, _ = self._scan("```yaml\n- uses:\n```\n")
        self.assertEqual(len(findings), 1)

    def test_action_text_inside_run_body_is_not_an_action(self):
        findings, _ = self._scan(
            "```yaml\n- run: |\n    echo 'uses: owner/action@v1'\n"
            '- {run: "echo \'{uses: owner/action@v1}\'"}\n'
            "# {uses: owner/action@v1}\n```\n"
        )
        self.assertEqual(findings, [])

    def test_flow_marker_exempts_only_one_reference(self):
        findings, exceptions = self._scan(
            f"```yaml\n{self.MARKER}\n"
            "steps: [{uses: actions/checkout@v7}, {uses: actions/setup-node@v7}]\n```\n"
        )
        self.assertEqual([f["package"] for f in findings], ["actions/setup-node"])
        self.assertEqual(len(exceptions), 1)

    def test_all_first_party_surfaces_are_scanned(self):
        for relative in (
            ".github/workflows/ci.yml", ".forgejo/workflows/ci.yml",
            "guides/example.md", "configs/example.md",
            "agents/example.md", "commands/example.md",
        ):
            with self.subTest(relative=relative):
                body = "- uses: actions/checkout@v7\n"
                if relative.endswith(".md"):
                    body = f"```yaml\n{body}```\n"
                findings, _ = self._scan(body, relative)
                self.assertEqual(len(findings), 1)

    def test_forge_workflow_action_sha_must_match_registered_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / ".forgejo/workflows/ci.yml"
            path.parent.mkdir(parents=True)
            path.write_text(f"- uses: actions/checkout@{self.SHA}\n", encoding="utf-8")
            mismatches = vv.collect_install_mismatches(
                {"action": {"actions/checkout": "b" * 40}}, root,
            )
            self.assertEqual(len(mismatches), 1)
            self.assertEqual(mismatches[0]["location"], ".forgejo/workflows/ci.yml:1")

    def test_image_digest_is_complete_and_tag_is_a_release(self):
        for version in ("latest", "18", "alpine", "sha256:abc123...", "sha256:" + "a" * 63):
            with self.subTest(version=version):
                self.assertFalse(vv.pinned_reference("docker", version))
        for version in ("16.13", "1.2.3-alpine", "sha256:" + "a" * 64):
            with self.subTest(version=version):
                self.assertTrue(vv.pinned_reference("docker", version))

    def test_split_dockerfile_digest_is_one_reference(self):
        text = "```dockerfile\nFROM gcr.io/distroless/python3-debian12@\\\nsha256:"
        text += "a" * 64 + "\n```\n"
        findings, _ = self._scan(text)
        self.assertEqual(findings, [])

    def test_illustrative_marker_cannot_exempt_a_package_install(self):
        findings, _ = self._scan(f"```yaml\n{self.MARKER}\n- run: npx tool\n```\n")
        self.assertEqual(len(findings), 1)


class ToolVersionsTests(unittest.TestCase):
    def test_workflow_lint_pins_and_all_platforms_match_makefile(self):
        pins = vv.parse_tool_versions(vv.TOOL_VERSIONS_FILE, vv.parse_canonical(vv.CONFIG_FILE))
        self.assertIn("actionlint", pins["binary"])
        self.assertIn("zizmor", pins["python"])
        self.assertEqual(vv.collect_toolchain_mismatches(pins), [])

    def test_toolchain_version_checksum_and_missing_platform_drift_fail(self):
        import copy

        pins = vv.parse_tool_versions(vv.TOOL_VERSIONS_FILE, vv.parse_canonical(vv.CONFIG_FILE))
        for section, name, value in (
            ("binary", "actionlint", "0.0.1"),
            ("python", "zizmor", "0.0.1"),
            ("checksum", f"actionlint_{pins['binary']['actionlint']}_linux_arm64.tar.gz",
             "sha256:" + "a" * 64),
        ):
            with self.subTest(section=section, name=name):
                changed = copy.deepcopy(pins)
                changed[section][name] = value
                self.assertTrue(vv.collect_toolchain_mismatches(changed))
        del pins["checksum"][f"actionlint_{pins['binary']['actionlint']}_darwin_amd64.tar.gz"]
        self.assertTrue(vv.collect_toolchain_mismatches(pins))

    def test_canonical_file_has_exact_versions_and_agrees_with_hooks(self):
        pins = vv.parse_tool_versions(vv.TOOL_VERSIONS_FILE, vv.parse_canonical(vv.CONFIG_FILE))
        for name in ("github.com/pkg/errors", "mvdan.cc/sh/v3/cmd/shfmt"):
            self.assertTrue(vv.pinned_reference("go", pins["go"][name]))

    def test_invalid_or_floating_canonical_config_fails(self):
        for text in ('[]', '{"npm": []}', '{"npm": {"tool": "latest"}}'):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "pins.json"
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    vv.parse_tool_versions(path, {})

    def test_canonical_pre_commit_disagreement_fails(self):
        with self.assertRaises(ValueError):
            vv.parse_tool_versions(vv.TOOL_VERSIONS_FILE, {"golangci/golangci-lint": "v0.0.1"})

    def test_install_drift_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guides = root / "guides"
            guides.mkdir()
            (guides / "x.md").write_text("`npx tool@1.2.3`", encoding="utf-8")
            findings = vv.collect_install_mismatches({"npm": {"tool": "2.0.0"}}, root)
            self.assertEqual(findings[0]["found"], "1.2.3")
            self.assertEqual(findings[0]["expected"], "2.0.0")

    def test_floating_exception_cannot_hide_canonical_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guides = root / "guides"
            guides.mkdir()
            (guides / "x.md").write_text(
                "```sh\n# crefft: allow-floating -- Negative example.\n"
                "npx tool@1.2.3\n```", encoding="utf-8",
            )
            findings = vv.collect_install_mismatches({"npm": {"tool": "2.0.0"}}, root)
            self.assertEqual(len(findings), 1)


class MainExitCodeTests(unittest.TestCase):
    @staticmethod
    def _run(argv: list[str]) -> tuple[int, str]:
        import io
        from contextlib import redirect_stdout

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = vv.main(argv)
        return code, buffer.getvalue()

    def test_repository_passes_without_strict(self):
        code, _ = self._run([])
        self.assertEqual(code, 0)

    def test_repository_passes_with_strict(self):
        code, _ = self._run(["--strict"])
        self.assertEqual(code, 0)

    def test_json_output_is_parseable(self):
        import json

        _, output = self._run(["--json"])
        payload = json.loads(output)
        self.assertIn("mismatches", payload)
        self.assertIn("unknown", payload)
        self.assertIn("floating", payload)
        self.assertIn("floating_exceptions", payload)
        self.assertGreater(payload["canonical_count"], 0)

    def test_strict_fails_on_undocumented_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guide = root / "guides" / "x.md"
            guide.parent.mkdir(parents=True)
            guide.write_text(
                "- repo: https://github.com/nobody/nothing\n  rev: 9.9.9\n",
                encoding="utf-8",
            )
            self.assertEqual(self._run(["--strict", "--root", str(root)])[0], 1)
            self.assertEqual(self._run(["--root", str(root)])[0], 0)

    def test_mismatch_fails_without_strict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guide = root / "guides" / "x.md"
            guide.parent.mkdir(parents=True)
            canonical = vv.parse_canonical(vv.CONFIG_FILE)
            repo, rev = next(iter(canonical.items()))
            self.assertNotEqual(rev, "0.0.0-not-a-real-version")
            guide.write_text(
                f"- repo: https://github.com/{repo}\n  rev: 0.0.0-not-a-real-version\n",
                encoding="utf-8",
            )
            code, output = self._run(["--root", str(root)])
            self.assertEqual(code, 1)
            self.assertIn("MISMATCH", output)

    def test_floating_command_fails_without_strict_in_text_and_json(self):
        import json

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guide = root / "guides" / "x.md"
            guide.parent.mkdir()
            guide.write_text("```bash\nnpx tool@latest\n```", encoding="utf-8")
            code, output = self._run(["--root", str(root)])
            self.assertEqual(code, 1)
            self.assertIn("FLOATING guides/x.md:2", output)
            code, output = self._run(["--json", "--root", str(root)])
            self.assertEqual(code, 1)
            self.assertEqual(len(json.loads(output)["floating"]), 1)

    def test_malformed_install_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guide = root / "guides" / "x.md"
            guide.parent.mkdir()
            guide.write_text("```sh\npip install 'tool\n```", encoding="utf-8")
            code, output = self._run(["--root", str(root)])
            self.assertEqual(code, 1)
            self.assertIn("syntax", output)


if __name__ == "__main__":
    unittest.main()
