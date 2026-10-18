#!/usr/bin/env python3
"""Check canonical versions and reject floating executable installs.

The canonical source is ``configs/pre-commit/.pre-commit-config.yaml``. Every
``repo:``/``rev:`` pair written into a guide, agent brief or shipped config
MUST agree with it, so a reader who copies a snippet gets the version crefft
has actually reviewed.

Two kinds of pin are compared:

    repo/rev pairs      third-party hooks, matched by ``owner/name``
    local hook entries  ``repo: local`` hooks, matched by hook ``id``

Local hooks carry no ``rev``, so a guide that quotes ``cargo clippy
--all-targets`` while the canonical config says ``cargo clippy --all-targets
--all-features`` used to pass unnoticed. Matching on ``id`` closes that gap.

Scanned surfaces:
    guides/**    the style guides themselves
    agents/**    agent briefs, which also carry copy-and-paste config
    commands/**  slash-command definitions
    configs/**   shipped configuration, excluding the canonical file itself

Executable package and action pins are registered in ``configs/tool-versions.json``.
Shell-like fences, Dockerfiles, YAML run steps/images/actions, and inline
package-manager commands are checked, not surrounding prose. Workflows under
``.github/workflows`` are checked too. Actions require full commit SHAs;
images require complete SHA-256 digests or exact release tags. A comment
``# crefft: allow-floating -- reason`` exempts only the next logical command
and is reported separately. Actions only accept the narrower
``# crefft: illustrative -- reason`` marker in Markdown examples, never in
native workflows. See the contributing checks in ``README.md``.

Exit codes:
    0   every comparable reference agrees with the canonical config
    1   a mismatch, a floating install, or --strict with an undocumented tool
    2   the canonical config is missing or unparsable

Usage:
    python3 scripts/validate_versions.py
    python3 scripts/validate_versions.py --strict
    python3 scripts/validate_versions.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = PROJECT_ROOT / "configs/pre-commit/.pre-commit-config.yaml"
TOOL_VERSIONS_FILE = PROJECT_ROOT / "configs/tool-versions.json"

# Every tree that may quote a pinned tool version.
SCAN_DIRS = ("guides", "agents", "commands", "configs", ".github/workflows")

# Directories never scanned: vendored upstream text and generated output.
EXCLUDED_DIRS = {".git", "node_modules", "reference", ".venv", "venv", "dist", "build"}

# Tools whose canonical identity differs from the repository slug.
#   key   -> owner/repo as written in a guide
#   value -> owner/repo as written in the canonical config
ALIASES: dict[str, str] = {}

# Repositories that appear on a scanned surface on purpose but are not pinned
# in the canonical config. Listing them documents the omission instead of
# hiding it, and keeps --strict usable. Remove an entry once the tool is
# adopted canonically.
KNOWN_UNPINNED: dict[str, str] = {
    "ansible/ansible-lint": "Ansible guide only; no canonical Ansible pin yet",
    "adrienverge/yamllint": "Ansible guide only; no canonical YAML pin yet",
    "compilerla/conventional-pre-commit": "commit-message guide illustration",
    "dnephin/pre-commit-golang": "superseded by golangci-lint in the canonical config",
    "jendrikseipp/vulture": "optional Python dead-code hook",
    "returntocorp/semgrep": "security guide illustration (former organization name)",
    "semgrep/semgrep": "security guide illustration",
    "thibaudcolas/pre-commit-stylelint": "optional CSS hook",
}

# Local hooks whose ``entry`` deliberately differs from the canonical config,
# pending a decision by the area that owns the guide. Listing one reports the
# divergence on every run without failing the gate, which is how KNOWN_UNPINNED
# already treats third-party pins. Remove an entry once the owning area has
# chosen a single command.
#   key   -> hook id
#   value -> why the divergence is tolerated, and who owns the decision
KNOWN_HOOK_DIVERGENCE: dict[str, str] = {
    "standardrb": (
        "guides/languages/ruby.md deliberately shows the reporting form; the "
        "canonical config auto-corrects with --fix. Owned by the Ruby area."
    ),
}

# ``  - repo: https://github.com/owner/name``, optionally commented out.
REPO_RE = re.compile(r"^\s*(?:#\s*)?-?\s*repo:\s*(?P<url>\S+)\s*$")
REV_RE = re.compile(r"^\s*(?:#\s*)?rev:\s*(?P<rev>\S+)\s*$")

# A ``repo:``/``rev:`` pair inside prose or a fenced block. pre-commit always
# writes them close together; at most two intervening comment or key lines are
# tolerated.
PAIR_RE = re.compile(
    r"^[ \t]*(?:#[ \t]*)?-?[ \t]*repo:[ \t]*(?P<url>\S+)[ \t]*\n"
    r"(?:^[ \t]*(?:#.*|(?:#[ \t]*)?[a-z_]+:[ \t]*\S*[ \t]*)\n){0,2}?"
    r"^[ \t]*(?:#[ \t]*)?rev:[ \t]*(?P<rev>\S+)[ \t]*$",
    re.MULTILINE,
)

# ``  - repo: local``, optionally commented out, and the ``id``/``entry`` keys
# of the hooks inside such a block.
LOCAL_REPO_RE = re.compile(r"^\s*(?:#\s*)?-?\s*repo:\s*local\s*$")
HOOK_ID_RE = re.compile(r"^\s*(?:#\s*)?-\s*id:\s*(?P<id>\S+)\s*$")
HOOK_ENTRY_RE = re.compile(r"^\s*(?:#\s*)?entry:\s*(?P<entry>\S.*?)\s*$")

# A bare hostname followed by a path, used to decide whether the leading
# segment of a normalized URL is a host or already the owner.
HOST_RE = re.compile(r"^[\w.-]+\.[\w.-]+/")

SHELL_LANGUAGES = {"bash", "sh", "shell", "console", "zsh"}
FENCE_RE = re.compile(r"^\s*(?:>\s*)?(?P<fence>`{3,}|~{3,})(?P<info>[^`]*)$")
INLINE_RE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.DOTALL)
COMMAND_RE = re.compile(
    r"^(?:go (?:install|get)|npx|npm install|pnpm dlx|pip3? install|"
    r"pipx install|uv (?:tool|pip) install|uvx|cargo install|"
    r"(?:docker|podman) (?:run|pull))(?:\s|$)"
)
EXCEPTION_RE = re.compile(r"^\s*# crefft: allow-floating -- (?P<reason>\S.*)$")
ILLUSTRATIVE_RE = re.compile(r"^\s*# crefft: illustrative -- (?P<reason>\S.*)$")
EXACT_VERSION_RE = re.compile(
    r"v?\d+\.\d+\.\d+(?:[a-z]\d+)?(?:[-+][0-9A-Za-z.-]+)?"
)
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
IMAGE_VERSION_RE = re.compile(r"v?\d+\.\d+(?:\.\d+)?(?:[-+][0-9A-Za-z.-]+)?")


@dataclass(frozen=True)
class Executable:
    line: int
    command: str
    language: str
    exception: str = ""
    illustrative: bool = False


def shell_executables(
    line: int, command: str, language: str = "shell", reason: str = ""
) -> Iterator[Executable]:
    """Do not let a one-command exception cover a chained second install."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        # Retain malformed syntax so the collector can report it as an error.
        yield Executable(line, command, language, reason)
        return
    part: list[str] = []
    for token in tokens + [";"]:
        if token and set(token) <= set(";&|"):
            if part:
                yield Executable(line, shlex.join(part), language, reason)
                reason, part = "", []
        else:
            part.append(token)


def logical_lines(lines: Sequence[tuple[int, str]]) -> Iterator[tuple[int, str, str]]:
    """Join shell continuations, retaining the first line and one-line exception."""
    pending = ""
    start = 0
    reason = ""
    for number, raw in lines:
        marker = EXCEPTION_RE.fullmatch(raw)
        if marker and not pending:
            reason = marker.group("reason")
            continue
        if not pending:
            start = number
        pending += raw.rstrip().removesuffix("\\")
        if raw.rstrip().endswith("\\"):
            continue
        yield start, pending.strip(), reason
        pending, reason = "", ""
    if pending:
        yield start, pending.strip(), reason


def block_executables(
    lines: Sequence[tuple[int, str]], language: str
) -> Iterator[Executable]:
    """Select runnable instructions without treating every YAML value as shell."""
    if language in SHELL_LANGUAGES or language == "dockerfile":
        stages: set[str] = set()
        for line, command, reason in logical_lines(lines):
            if language == "dockerfile":
                match = re.match(
                    r"(?i)^FROM\s+(?:--\S+\s+)*(\S+)(?:\s+AS\s+(\S+))?", command
                )
                if match:
                    image, stage = match.groups()
                    if stage:
                        stages.add(stage)
                    if image in stages:
                        continue
                exec_form = re.match(r"(?i)^(?:RUN|CMD|ENTRYPOINT)\s+(\[.*\])$", command)
                if exec_form:
                    args = json.loads(exec_form.group(1))
                    if isinstance(args, list) and all(isinstance(arg, str) for arg in args):
                        command = shlex.join(args)
            yield from shell_executables(line, command, language, reason)
        return
    if language not in {"yaml", "yml"}:
        return
    reason = ""
    illustrative = False
    position = 0
    while position < len(lines):
        number, raw = lines[position]
        position += 1
        marker = EXCEPTION_RE.fullmatch(raw) or ILLUSTRATIVE_RE.fullmatch(raw)
        if marker:
            reason = marker.group("reason")
            illustrative = bool(ILLUSTRATIVE_RE.fullmatch(raw))
            continue
        indent = len(raw) - len(raw.lstrip())
        match = re.match(r"""^\s*(?:-\s*)?["']?(run|image|uses)["']?:\s*(.*)$""", raw)
        if not match and not raw.lstrip().startswith("#"):
            for flow in re.finditer(
                r"""(?:\{|,)\s*["']?(?P<kind>uses|image)["']?:\s*"""
                r"""(?P<value>"[^"]*"|'[^']*'|[^,}]*)(?=,|})"""
                r"""|"(?:\\.|[^"\\])*"|'(?:''|[^'])*'|(?:^|\s)#.*$""", raw
            ):
                kind, value = flow.group("kind", "value")
                if kind is None:
                    continue
                value = value.strip()
                yield Executable(
                    number, f"{kind}: {value}",
                    "yaml", reason, illustrative,
                )
                reason, illustrative = "", False
        if match:
            kind, value = match.groups()
            if kind == "run" and illustrative:
                reason = ""
            if value.startswith(("'", '"')) and not value.endswith(value[0]):
                quote = value[0]
                while position < len(lines):
                    _, child = lines[position]
                    if child.strip() and len(child) - len(child.lstrip()) <= indent:
                        break
                    separator = "" if quote == '"' and value.endswith("\\") else " "
                    value = value.removesuffix("\\") + separator + child.strip()
                    position += 1
                    if value.endswith(quote):
                        break
            if re.match(r"^[|>][+-]?(?:\s|$)", value):
                key_indent = indent + (2 if raw.lstrip().startswith("-") else 0)
                selected: list[tuple[int, str]] = []
                while position < len(lines):
                    child_number, child = lines[position]
                    if child.strip() and len(child) - len(child.lstrip()) <= key_indent:
                        break
                    selected.append((child_number, child))
                    position += 1
                if kind == "run" and value.startswith("|"):
                    yield from block_executables(selected, "shell")
                else:
                    folded = " ".join(child.strip() for _, child in selected)
                    command = folded if kind == "run" else f"{kind}: {folded}"
                    if kind == "run":
                        yield from shell_executables(number, command, reason=reason)
                    else:
                        yield Executable(number, command, "yaml", reason, illustrative)
            else:
                if kind == "run" and value.startswith(("'", '"')) and value.endswith(value[0]):
                    value = value[1:-1]
                command = value if kind == "run" else f"{kind}: {value}"
                if kind == "run":
                    yield from shell_executables(number, command, reason=reason)
                else:
                    yield Executable(number, command, "yaml", reason, illustrative)
        reason, illustrative = "", False


def iter_executables(text: str, suffix: str = ".md") -> Iterator[Executable]:
    """Find executable fences and command spans, including indented/tilde fences."""
    lines = text.splitlines()
    if suffix in {".yaml", ".yml"}:
        yield from block_executables(list(enumerate(lines, 1)), "yaml")
        return
    if suffix in {".sh", ".bash", ".zsh"}:
        yield from block_executables(list(enumerate(lines, 1)), "shell")
        return
    if suffix == "dockerfile":
        yield from block_executables(list(enumerate(lines, 1)), suffix)
        return
    fence = ""
    language = ""
    block: list[tuple[int, str]] = []
    prose = [""] * len(lines)
    for number, raw in enumerate(lines, 1):
        match = FENCE_RE.match(raw)
        if fence:
            if match and match.group("fence")[0] == fence[0]:
                if len(match.group("fence")) >= len(fence) and not match.group("info").strip():
                    yield from block_executables(block, language)
                    fence, block = "", []
                    continue
            block.append((number, raw))
            continue
        if match:
            fence = match.group("fence")
            info = match.group("info").strip().lower().split()
            language = info[0] if info else ""
            continue
        prose[number - 1] = raw
    if fence:
        yield from block_executables(block, language)
    prose_text = "\n".join(prose)
    for span in INLINE_RE.finditer(prose_text):
        command = span.group(2).strip().replace("\n", " ")
        if COMMAND_RE.match(command):
            number = prose_text.count("\n", 0, span.start()) + 1
            yield from shell_executables(number, command)


def exact_version(version: str) -> bool:
    return bool(EXACT_VERSION_RE.fullmatch(version) or COMMIT_RE.fullmatch(version))


def package_spec(spec: str, ecosystem: str) -> tuple[str, str]:
    if ecosystem == "python":
        name, _, version = spec.partition("==")
        return re.sub(r"\[.*\]$", "", name), version
    name, sep, version = spec.rpartition("@")
    if sep and name:
        return name, version
    return spec, ""


def install_references(command: str) -> Iterator[tuple[str, str, str]]:
    """Yield ecosystem/name/version triples; an empty version means floating."""
    # shlex handles quoted requirements and ignores comments, but never executes text.
    tokens = shlex.split(command, comments=True)
    index = 0
    while index < len(tokens):
        token = tokens[index]
        ecosystem = ""
        start = index + 2
        pair = tokens[index : index + 2]
        if pair in (["go", "install"], ["go", "get"]):
            ecosystem = "go"
        elif pair in (["npm", "install"], ["pnpm", "dlx"]):
            ecosystem = "npm"
        elif token in {"npx", "uvx"}:
            ecosystem = "npm" if token == "npx" else "python"
            start = index + 1
        elif pair in (["pip", "install"], ["pip3", "install"], ["pipx", "install"]):
            ecosystem = "python"
        elif token == "uv" and tokens[index + 1 : index + 3] in (
            ["tool", "install"], ["pip", "install"]
        ):
            ecosystem, start = "python", index + 3
        elif pair == ["cargo", "install"]:
            ecosystem = "cargo"
        if not ecosystem:
            index += 1
            continue
        end = start
        while end < len(tokens) and tokens[end] not in {"&&", "||", ";", "|"}:
            end += 1
        args = tokens[start:end]
        explicit_version = ""
        packages: list[str] = []
        position = 0
        while position < len(args):
            arg = args[position]
            if arg in {"--version", "--package", "-p", "--from", "--with"}:
                value = args[position + 1] if position + 1 < len(args) else ""
                if arg == "--version":
                    explicit_version = value
                elif value:
                    packages.append(value)
                position += 2
                continue
            if arg.startswith(("--version=", "--package=", "--from=", "--with=")):
                flag, value = arg.split("=", 1)
                if flag == "--version":
                    explicit_version = value
                else:
                    packages.append(value)
                position += 1
                continue
            if arg in {
                "-r", "--requirement", "-c", "--constraint", "--index-url",
                "--extra-index-url", "--target", "--prefix", "--cache-dir",
                "--torch-backend", "--features", "--registry", "--root",
            }:
                position += 2
                continue
            if arg.startswith("-") or arg.startswith((">", "<")):
                position += 1
                continue
            if token in {"npx", "uvx"} or pair == ["pnpm", "dlx"]:
                if not packages:
                    packages.append(arg)
                break
            packages.append(arg)
            position += 1
        for spec in packages:
            if spec in {".", "./...", "./...;"} or spec.startswith(("./", "../")):
                if pair == ["go", "get"] and "-u" in args:
                    yield ecosystem, spec, ""
                continue
            if spec.endswith((".whl", ".tar.gz")):
                continue
            name, version = package_spec(spec, ecosystem)
            yield ecosystem, name, explicit_version or version
        index = end


def executable_references(executable: Executable) -> Iterator[tuple[str, str, str]]:
    """Read install specs plus image and action selectors in runnable contexts."""
    command = executable.command
    if executable.language != "yaml" or not re.match(r"^(?:image|uses):", command):
        yield from install_references(command)
    if executable.language == "yaml":
        match = re.match(r"(?:-\s*)?(image|uses):\s*(.*)$", command)
        if not match:
            return
        kind, spec = match.groups()
        if spec.startswith(("'", '"')):
            quoted = re.fullmatch(r"""(["'])(.*?)\1(?:\s+#.*)?""", spec)
            if not quoted:
                yield "action" if kind == "uses" else "docker", spec, ""
                return
            spec = quoted[2]
        else:
            spec = re.split(r"\s+#", spec, maxsplit=1)[0].strip()
        if kind == "uses":
            name, _, version = spec.partition("@")
            yield "action", name, version
            return
        images = [spec]
    elif executable.language == "dockerfile" and re.match(r"(?i)^FROM\s", command):
        images = [arg for arg in shlex.split(command)[1:] if not arg.startswith("--")][:1]
    else:
        images = []
        match = re.search(r"\b(?:docker|podman)\s+(?:run|pull)\s+(.+)", command)
        if match:
            args = shlex.split(match.group(1), comments=True)
            position = 0
            value_flags = {
                "-v", "--volume", "-p", "--publish", "-e", "--env", "--name",
                "-w", "--workdir", "--gpus", "--network", "--entrypoint",
                "--mount", "--user", "-u", "--hostname", "--env-file",
                "--pull", "--platform", "--restart", "--memory", "--cpus",
                "--label", "-l", "--device", "--add-host", "--cap-add", "--cap-drop",
                "--security-opt", "--log-driver", "--log-opt", "--runtime",
            }
            while position < len(args):
                arg = args[position]
                if arg in value_flags:
                    position += 2
                elif arg.startswith("-"):
                    position += 1
                else:
                    images.append(arg)
                    break
    for spec in images:
        if spec == "scratch":
            continue
        if "@sha256:" in spec:
            name, _, version = spec.partition("@")
        else:
            name, _, version = spec.rpartition(":")
            if not name or "/" in version:
                name, version = spec, ""
        yield "docker", name, version


def pinned_reference(ecosystem: str, version: str) -> bool:
    if ecosystem == "action":
        return bool(COMMIT_RE.fullmatch(version))
    if ecosystem == "checksum":
        return bool(DIGEST_RE.fullmatch(version))
    if ecosystem == "docker":
        return bool(DIGEST_RE.fullmatch(version) or IMAGE_VERSION_RE.fullmatch(version))
    return exact_version(version)


def floating_references(executable: Executable) -> Iterator[tuple[str, str, str]]:
    for ecosystem, name, version in executable_references(executable):
        if not pinned_reference(ecosystem, version):
            yield ecosystem, name, version


def collect_floating(
    root: Path = PROJECT_ROOT, dirs: Sequence[str] = SCAN_DIRS
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    findings: list[dict[str, object]] = []
    exceptions: list[dict[str, object]] = []
    for path in iter_files(root, dirs):
        content = path.read_text(encoding="utf-8")
        suffix = "dockerfile" if path.name.lower().startswith("dockerfile") else path.suffix
        for executable in iter_executables(content, suffix):
            if path.relative_to(root).parts[0] == ".github" and not re.match(
                r"^uses:", executable.command
            ):
                continue
            try:
                refs = list(floating_references(executable))
            except ValueError as error:
                # Non-shell example text need not parse, but an install must fail closed.
                if re.search(r"\b(?:install|npx|uvx|dlx|docker run)\b", executable.command):
                    refs = [("syntax", executable.command, str(error))]
                else:
                    continue
            for ecosystem, name, version in refs:
                item: dict[str, object] = {
                    "location": f"{path.relative_to(root)}:{executable.line}",
                    "ecosystem": ecosystem,
                    "package": name,
                    "version": version,
                }
                allowed = bool(executable.exception)
                if ecosystem == "action":
                    allowed = executable.illustrative and suffix in {".md", ".template"}
                elif executable.illustrative:
                    allowed = suffix in {".md", ".template"} and ecosystem == "docker"
                if allowed:
                    item["reason"] = executable.exception
                    exceptions.append(item)
                else:
                    findings.append(item)
    return findings, exceptions


def parse_tool_versions(path: Path, hooks: dict[str, str]) -> dict[str, dict[str, str]]:
    """Load install pins and ensure overlapping pre-commit pins still agree."""
    pins = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(pins, dict) or any(
        not isinstance(tools, dict)
        or any(not isinstance(name, str) or not isinstance(rev, str)
               for name, rev in tools.items())
        for tools in pins.values()
    ):
        raise ValueError("expected ecosystem objects mapping package names to exact versions")
    for ecosystem, tools in pins.items():
        for name, version in tools.items():
            if not pinned_reference(ecosystem, version):
                raise ValueError(f"{ecosystem} {name}: {version!r} is not an exact version")
    overlaps = {
        ("binary", "vale"): ("vale-cli/vale", ""),
        ("hook", "vale-cli/vale"): ("vale-cli/vale", ""),
        ("go", "github.com/golangci/golangci-lint/cmd/golangci-lint"):
            ("golangci/golangci-lint", ""),
        ("go", "mvdan.cc/sh/v3/cmd/shfmt"): ("scop/pre-commit-shfmt", r"-\d+$"),
        ("npm", "@biomejs/biome"): ("biomejs/pre-commit", ""),
        ("npm", "prettier"): ("pre-commit/mirrors-prettier", ""),
        ("npm", "markdownlint-cli"): ("igorshubovych/markdownlint-cli", ""),
        ("python", "sqlfluff"): ("sqlfluff/sqlfluff", ""),
        ("docker", "hadolint/hadolint"): ("hadolint/hadolint", ""),
    }
    for (ecosystem, name), (repo, suffix) in overlaps.items():
        if repo not in hooks:
            continue
        expected = re.sub(suffix, "", hooks[repo]) if suffix else hooks[repo]
        if ecosystem in {"npm", "python", "binary"}:
            expected = expected.removeprefix("v")
        if pins.get(ecosystem, {}).get(name) != expected:
            raise ValueError(f"{ecosystem} {name} must match {repo}@{expected}")
    return pins


def collect_install_mismatches(
    pins: dict[str, dict[str, str]], root: Path = PROJECT_ROOT,
    dirs: Sequence[str] = SCAN_DIRS,
) -> list[dict[str, object]]:
    mismatches: list[dict[str, object]] = []
    for path in iter_files(root, dirs):
        suffix = "dockerfile" if path.name.lower().startswith("dockerfile") else path.suffix
        for executable in iter_executables(path.read_text(encoding="utf-8"), suffix):
            try:
                refs = list(executable_references(executable))
            except ValueError:
                # collect_floating reports malformed executable install syntax.
                continue
            for ecosystem, name, version in refs:
                if path.relative_to(root).parts[0] == ".github" and ecosystem != "action":
                    continue
                expected = pins.get(ecosystem, {}).get(name)
                if (
                    expected is not None
                    and pinned_reference(ecosystem, version)
                    and version != expected
                ):
                    mismatches.append({
                        "location": f"{path.relative_to(root)}:{executable.line}",
                        "repo": f"{ecosystem} {name}", "found": version, "expected": expected,
                    })
    return mismatches


def normalize_repo(url: str) -> str:
    """Reduce a repository URL to ``owner/name``.

    Handles HTTPS, SCP-style SSH (``git@github.com:owner/name.git``) and
    ``ssh://`` forms, and keeps the owner. The previous implementation dropped
    it, so ``owner/tool`` collapsed to ``tool`` and could match the wrong
    project by suffix.
    """
    url = url.strip().strip("\"'")
    if url.endswith(".git"):
        url = url[: -len(".git")]
    url = url.rstrip("/")

    scp = re.match(r"^(?:[\w.-]+@)?[\w.-]+:(?P<path>[^/].*)$", url)
    if "://" not in url and scp:
        url = scp.group("path")
    else:
        url = re.sub(r"^[a-z+]+://", "", url)
        url = re.sub(r"^[^/@]+@", "", url)
        if HOST_RE.match(url):
            url = url.split("/", 1)[1]

    parts = [p for p in url.split("/") if p]
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return "/".join(parts)


def canonical_key(repo: str) -> str:
    return ALIASES.get(repo, repo)


@dataclass(frozen=True)
class Reference:
    path: Path
    line: int
    repo: str
    rev: str

    def where(self) -> str:
        try:
            return f"{self.path.resolve().relative_to(PROJECT_ROOT)}:{self.line}"
        except ValueError:
            return f"{self.path}:{self.line}"


def parse_canonical(config_path: Path) -> dict[str, str]:
    """Read ``repo``/``rev`` pairs from the canonical pre-commit config.

    Commented-out entries count: crefft keeps optional hooks commented but
    still treats their pins as canonical.
    """
    if not config_path.is_file():
        raise FileNotFoundError(config_path)

    pins: dict[str, str] = {}
    current: str | None = None
    for raw in config_path.read_text(encoding="utf-8").splitlines():
        repo_match = REPO_RE.match(raw)
        if repo_match:
            current = canonical_key(normalize_repo(repo_match.group("url")))
            continue
        if current is None:
            continue
        rev_match = REV_RE.match(raw)
        if rev_match:
            pins[current] = rev_match.group("rev").strip("\"'")
            current = None
    return pins


def parse_local_hooks(text: str) -> Iterator[tuple[int, str, str]]:
    """Yield ``(line, hook_id, entry)`` for every hook in a ``repo: local`` block.

    Commented-out blocks count, for the same reason ``parse_canonical`` counts
    them: crefft keeps optional hooks commented but treats them as canonical.
    """
    in_local = False
    current: str | None = None
    for number, raw in enumerate(text.splitlines(), start=1):
        if LOCAL_REPO_RE.match(raw):
            in_local, current = True, None
            continue
        if REPO_RE.match(raw):
            in_local, current = False, None
            continue
        if not in_local:
            continue
        id_match = HOOK_ID_RE.match(raw)
        if id_match:
            current = id_match.group("id").strip("\"'")
            continue
        entry_match = HOOK_ENTRY_RE.match(raw)
        if entry_match and current is not None:
            yield number, current, entry_match.group("entry").strip("\"'")
            current = None


def parse_canonical_hooks(config_path: Path) -> dict[str, str]:
    """Read local hook ``id``/``entry`` pairs from the canonical config."""
    if not config_path.is_file():
        raise FileNotFoundError(config_path)
    return {
        hook_id: entry
        for _, hook_id, entry in parse_local_hooks(config_path.read_text(encoding="utf-8"))
    }


def collect_hook_mismatches(
    canonical_hooks: dict[str, str],
    root: Path = PROJECT_ROOT,
    dirs: Sequence[str] = SCAN_DIRS,
) -> list[dict[str, object]]:
    """Find local hooks that reuse a canonical ``id`` with a different ``entry``.

    Hook ids absent from the canonical config are ignored: a guide may
    legitimately illustrate a project-specific hook.
    """
    canonical = CONFIG_FILE.resolve()
    mismatches: list[dict[str, object]] = []

    for path in iter_files(root, dirs):
        if path.resolve() == canonical:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line, hook_id, entry in parse_local_hooks(content):
            expected = canonical_hooks.get(hook_id)
            if expected is None or entry == expected:
                continue
            try:
                location = f"{path.resolve().relative_to(PROJECT_ROOT)}:{line}"
            except ValueError:
                location = f"{path}:{line}"
            mismatches.append(
                {
                    "location": location,
                    "repo": f"local hook {hook_id}",
                    "found": entry,
                    "expected": expected,
                    "documented": hook_id in KNOWN_HOOK_DIVERGENCE,
                    "reason": KNOWN_HOOK_DIVERGENCE.get(hook_id, ""),
                }
            )
    return mismatches


def iter_files(root: Path, dirs: Sequence[str] = SCAN_DIRS) -> Iterator[Path]:
    """Yield every version-bearing file on the scanned surfaces."""
    for name in dirs:
        base = root / name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if EXCLUDED_DIRS.intersection(relative.parts):
                continue
            if (
                path.suffix.lower() in {".md", ".yaml", ".yml", ".template", ".sh", ".bash", ".zsh"}
                or path.name.lower().startswith("dockerfile")
            ):
                yield path


def collect_references(
    root: Path = PROJECT_ROOT, dirs: Sequence[str] = SCAN_DIRS
) -> list[Reference]:
    """Find every ``repo``/``rev`` pair on the scanned surfaces."""
    canonical = CONFIG_FILE.resolve()
    references: list[Reference] = []

    for path in iter_files(root, dirs):
        if path.resolve() == canonical:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in PAIR_RE.finditer(content):
            references.append(
                Reference(
                    path=path,
                    line=content.count("\n", 0, match.start()) + 1,
                    repo=canonical_key(normalize_repo(match.group("url"))),
                    rev=match.group("rev").strip("\"'"),
                )
            )
    return references


def evaluate(
    references: Iterable[Reference], canonical: dict[str, str]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Split references into mismatches and references outside the canonical set."""
    mismatches: list[dict[str, object]] = []
    unknown: list[dict[str, object]] = []

    for ref in references:
        expected = canonical.get(ref.repo)
        if expected is None:
            unknown.append(
                {
                    "location": ref.where(),
                    "repo": ref.repo,
                    "rev": ref.rev,
                    "reason": KNOWN_UNPINNED.get(ref.repo, "not present in the canonical config"),
                    "documented": ref.repo in KNOWN_UNPINNED,
                }
            )
        elif ref.rev != expected:
            mismatches.append(
                {
                    "location": ref.where(),
                    "repo": ref.repo,
                    "found": ref.rev,
                    "expected": expected,
                }
            )

    return mismatches, unknown


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also fail when a scanned surface references a tool absent from the canonical config",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT, help="repository root to scan")
    args = parser.parse_args(argv)

    try:
        canonical = parse_canonical(CONFIG_FILE)
    except FileNotFoundError:
        print(f"ERROR: canonical config not found at {CONFIG_FILE}", file=sys.stderr)
        return 2

    if not canonical:
        print(f"ERROR: no repo/rev pairs parsed from {CONFIG_FILE}", file=sys.stderr)
        return 2

    canonical_hooks = parse_canonical_hooks(CONFIG_FILE)
    try:
        tool_versions = parse_tool_versions(TOOL_VERSIONS_FILE, canonical)
    except (OSError, ValueError) as error:
        print(f"ERROR: {TOOL_VERSIONS_FILE}: {error}", file=sys.stderr)
        return 2

    references = collect_references(args.root)
    mismatches, unknown = evaluate(references, canonical)

    hook_findings = collect_hook_mismatches(canonical_hooks, args.root)
    hook_divergences = [h for h in hook_findings if h["documented"]]
    mismatches.extend(h for h in hook_findings if not h["documented"])
    undocumented = [u for u in unknown if not u["documented"]]
    floating, floating_exceptions = collect_floating(args.root)
    mismatches.extend(collect_install_mismatches(tool_versions, args.root))

    if args.json:
        json.dump(
            {
                "canonical_count": len(canonical),
                "canonical_hook_count": len(canonical_hooks),
                "canonical_install_count": sum(map(len, tool_versions.values())),
                "reference_count": len(references),
                "hook_divergences": hook_divergences,
                "mismatches": mismatches,
                "unknown": unknown,
                "strict": args.strict,
                "floating": floating,
                "floating_exceptions": floating_exceptions,
            },
            sys.stdout,
            indent=2,
            sort_keys=True,
        )
        sys.stdout.write("\n")
    else:
        rel = CONFIG_FILE.relative_to(PROJECT_ROOT)
        print(
            f"Canonical config: {rel} ({len(canonical)} pinned tools, "
            f"{len(canonical_hooks)} local hooks)"
        )
        print(
            f"Executable pins: {TOOL_VERSIONS_FILE.relative_to(PROJECT_ROOT)} "
            f"({sum(map(len, tool_versions.values()))} pins)"
        )
        print(f"Scanned {', '.join(SCAN_DIRS)}: {len(references)} repo/rev references")
        print()

        for item in mismatches:
            print(f"MISMATCH {item['location']}")
            print(f"  tool:     {item['repo']}")
            print(f"  found:    {item['found']}")
            print(f"  expected: {item['expected']}")

        for item in floating:
            print(
                f"FLOATING {item['location']}  {item['ecosystem']} "
                f"{item['package']}@{item['version'] or '(unversioned)'}"
            )
        for item in floating_exceptions:
            print(f"EXCEPTION {item['location']}  {item['package']} — {item['reason']}")

        for item in hook_divergences:
            print(f"DIVERGENT {item['location']}  {item['repo']}")
            print(f"  found:    {item['found']}")
            print(f"  expected: {item['expected']}")
            print(f"  tolerated: {item['reason']}")

        for item in unknown:
            level = "UNPINNED" if item["documented"] else "UNKNOWN "
            print(f"{level} {item['location']}  {item['repo']}@{item['rev']} — {item['reason']}")

        print()
        if mismatches:
            print(f"FAILURE: {len(mismatches)} version mismatches.")
        if floating:
            print(f"FAILURE: {len(floating)} floating executable references.")
        if not mismatches and not floating:
            print("OK: every comparable reference matches the canonical configuration.")
            print("OK: no floating executable references.")
        if hook_divergences:
            print(
                f"{len(hook_divergences)} local hook(s) diverge from the canonical "
                "config by documented exception."
            )
        if unknown:
            print(
                f"{len(unknown)} references are outside the canonical set "
                f"({len(undocumented)} undocumented)."
            )
        if args.strict and undocumented:
            print(
                "FAILURE: --strict rejects undocumented tools. "
                "Pin them, or record them in KNOWN_UNPINNED."
            )

    if mismatches or floating:
        return 1
    if args.strict and undocumented:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
