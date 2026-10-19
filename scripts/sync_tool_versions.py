#!/usr/bin/env python3
"""Synchronize Renovate's registry changes before it creates a commit.

HEAD is the base tree; Renovate's uncommitted registry and native-manager
updates are the inputs. No vendored file or test fixture is rewritten.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Callable

import validate_versions as vv

REGISTRY = "configs/tool-versions.json"
BINARY_REPOS = {"actionlint": "rhysd/actionlint", "vale": "vale-cli/vale"}
ACTION_RE = re.compile(
    r"(?P<name>[\w.-]+/[\w./-]+)@(?P<sha>[a-f0-9]{40})"
    r"(?:[ \t]+#[ \t]*(?P<tag>v?\d+(?:\.\d+){0,2}(?:[-+][\w.-]+)?))?"
)


def download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def base_file(root: Path, name: str) -> str:
    return subprocess.run(
        ["git", "show", f"HEAD:{name}"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout


def value(section: str, pin: str) -> str:
    return pin.rsplit("@", 1)[-1] if section == "action" else pin


def adopt_native_updates(
    root: Path, pins: dict[str, dict[str, str]], before: dict[str, dict[str, str]],
    baseline: Callable[[str], str],
) -> None:
    def adopt(section: str, name: str, new: str) -> None:
        current = pins[section][name]
        old = before[section][name]
        if value(section, current) not in {value(section, old), value(section, new)}:
            raise ValueError(f"conflicting updates for {section} {name}")
        pins[section][name] = new

    for name in ("package.json", "site/package.json"):
        path = root / name
        if not path.exists():
            continue
        old_manifest = json.loads(baseline(name))
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for kind in ("dependencies", "devDependencies", "optionalDependencies"):
            for package, version in manifest.get(kind, {}).items():
                if package not in before.get("npm", {}):
                    continue
                old = old_manifest.get(kind, {}).get(package)
                if old is not None and old != version:
                    if not vv.exact_version(version):
                        raise ValueError(f"native npm update for {package} is not exact: {version}")
                    adopt("npm", package, version)

    for directory in (".github/workflows", ".forgejo/workflows"):
        for path in sorted((root / directory).glob("*")):
            if path.suffix not in {".yml", ".yaml"}:
                continue
            old_refs = {(m["name"], m["sha"], m["tag"]) for m in ACTION_RE.finditer(
                baseline(path.relative_to(root).as_posix())
            )}
            for match in ACTION_RE.finditer(path.read_text(encoding="utf-8")):
                name, sha, tag = match.group("name", "sha", "tag")
                if name not in before.get("action", {}) or (name, sha, tag) in old_refs:
                    continue
                if not tag:
                    raise ValueError(f"updated action {name} needs a release comment")
                adopt("action", name, f"{tag}@{sha}")


def refresh_checksums(
    pins: dict[str, dict[str, str]], fetch: Callable[[str], bytes] = download,
) -> None:
    for tool, platforms in vv.BINARY_PLATFORMS.items():
        if tool not in pins.get("binary", {}):
            continue
        version = pins["binary"][tool]
        archives = [f"{tool}_{version}_{platform}.tar.gz" for platform in platforms]
        if all(name in pins.get("checksum", {}) for name in archives):
            continue
        url = f"https://github.com/{BINARY_REPOS[tool]}/releases/download/v{version}"
        listing = fetch(f"{url}/{tool}_{version}_checksums.txt").decode("utf-8")
        checksums = dict(
            (name, digest) for digest, name in re.findall(
                r"^([a-f0-9]{64})[ \t]+\*?(\S+)$", listing, re.MULTILINE,
            )
        )
        verified = {}
        for archive in archives:
            if archive not in checksums:
                raise ValueError(f"upstream checksum is missing for {archive}")
            actual = hashlib.sha256(fetch(f"{url}/{archive}")).hexdigest()
            if actual != checksums[archive]:
                raise ValueError(f"SHA-256 mismatch for {archive}")
            verified[archive] = f"sha256:{actual}"
        pins["checksum"] = {
            name: digest for name, digest in pins.get("checksum", {}).items()
            if not name.startswith(f"{tool}_")
        } | verified


def replace_spec(text: str, section: str, name: str, old: str, new: str) -> str:
    start = rf"(?<![\w./@-]){re.escape(name)}"
    if section == "python":
        prefix = start + r"(?:\[[^\]\n]+\])?=="
    elif section == "docker":
        prefix = start + r"(?:@(?:\\\n[ \t]*)?|:)"
    else:
        prefix = start + "@"
    return re.sub(
        rf"({prefix}){re.escape(old)}(?![\w.+-])",
        lambda match: match[1] + new, text,
    )


def synchronize(
    root: Path, before: dict[str, dict[str, str]],
    baseline: Callable[[str], str], fetch: Callable[[str], bytes] = download,
) -> list[str]:
    pins = json.loads((root / REGISTRY).read_text(encoding="utf-8"))
    adopt_native_updates(root, pins, before, baseline)
    old_vale = before.get("binary", {}).get("vale")
    old_hook = before.get("hook", {}).get("vale-cli/vale")
    if old_vale and old_hook:
        binary = pins["binary"]["vale"]
        hook = pins["hook"]["vale-cli/vale"].removeprefix("v")
        if binary != old_vale and hook != old_hook.removeprefix("v") and binary != hook:
            raise ValueError("conflicting Vale binary and hook updates")
        version = hook if hook != old_hook.removeprefix("v") else binary
        pins["binary"]["vale"] = version
        pins["hook"]["vale-cli/vale"] = f"v{version}"
    refresh_checksums(pins, fetch)

    changes = [
        (section, name, value(section, old), value(section, pins[section][name]))
        for section, tools in before.items() if section != "checksum"
        for name, old in tools.items()
        if name in pins.get(section, {})
        and (
            value(section, old) != value(section, pins[section][name])
            or section == "action" and "@" in old and old != pins[section][name]
        )
    ]
    canonical_path = root / "configs/pre-commit/.pre-commit-config.yaml"
    hooks = vv.parse_canonical(canonical_path) if canonical_path.exists() else {}
    hook_updates = {}
    for section, name, old, new in changes:
        if (section, name) not in vv.TOOL_OVERLAPS:
            continue
        repo, suffix = vv.TOOL_OVERLAPS[section, name]
        if suffix:
            raise ValueError(f"{name}: select the pre-commit wrapper revision manually")
        if repo in hooks:
            prefix = "v" if hooks[repo].startswith("v") else ""
            hook_updates[repo] = prefix + new.removeprefix("v")

    paths = set(vv.iter_files(root))
    paths.update(root / name for name in ("AGENTS.md", "CONTRIBUTING.md", "README.md"))
    paths.add(root / "Makefile")
    updates = {}
    for path in sorted(paths):
        if not path.is_file():
            continue
        text = original = path.read_text(encoding="utf-8")
        for section, name, old, new in changes:
            if section == "binary":
                text = re.sub(
                    rf"({name}[-_]){re.escape(old)}(?![0-9A-Za-z.+-])",
                    lambda match: match[1] + new, text,
                )
            elif section == "hook":
                continue
            else:
                text = replace_spec(text, section, name, old, new)
            if section == "action":
                tag = pins["action"][name].split("@", 1)[0]
                text = re.sub(
                    rf"({re.escape(name)}@{new})[ \t]+#[ \t]*v?\d+(?:\.\d+)*"
                    r"(?:[-+][\w.-]+)?",
                    lambda match: match[1] + f" # {tag}", text,
                )
        for match in reversed(list(vv.PAIR_RE.finditer(text))):
            repo = vv.normalize_repo(match["url"])
            if repo in hook_updates:
                start, end = match.span("rev")
                text = text[:start] + hook_updates[repo] + text[end:]
        if path.name == "Makefile":
            assignments = {}
            for tool, version in pins.get("binary", {}).items():
                assignments[f"{tool.upper()}_VERSION"] = version
                for platform in vv.BINARY_PLATFORMS[tool]:
                    archive = f"{tool}_{version}_{platform}.tar.gz"
                    assignments[f"{tool.upper()}_SHA256_{platform}"] = (
                        pins["checksum"][archive].removeprefix("sha256:")
                    )
            for section, tool in (("python", "zizmor"), ("npm", "renovate")):
                if tool in pins.get(section, {}):
                    assignments[f"{tool.upper()}_VERSION"] = pins[section][tool]
            for key, version in assignments.items():
                text = re.sub(
                    rf"(?m)^({re.escape(key)} :=[ \t]*(?:\\\n[ \t]*)?)\S+",
                    lambda match: match[1] + version, text,
                )
        if text != original:
            updates[path] = text

    lock_directories = []
    for name in ("package.json", "site/package.json"):
        path = root / name
        if not path.exists():
            continue
        manifest = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for section, package, old, new in changes:
            if section != "npm":
                continue
            for kind in ("dependencies", "devDependencies", "optionalDependencies"):
                if manifest.get(kind, {}).get(package) == old and old != new:
                    manifest[kind][package] = new
                    changed = True
        if changed:
            updates[path] = json.dumps(manifest, indent=2) + "\n"
            lock_directories.append(path.parent)
    registry_text = json.dumps(pins, indent=2) + "\n"
    if json.loads((root / REGISTRY).read_text(encoding="utf-8")) != pins:
        updates[root / REGISTRY] = registry_text
    for path, text in updates.items():
        path.write_text(text, encoding="utf-8")
    for directory in lock_directories:
        subprocess.run(
            ["npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"],
            cwd=directory, check=True,
        )
    return [path.relative_to(root).as_posix() for path in sorted(updates)]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    try:
        before = json.loads(base_file(root, REGISTRY))
        vv.parse_tool_versions(root / REGISTRY, {})
        paths = synchronize(root, before, lambda name: base_file(root, name))
        subprocess.run([sys.executable, "scripts/validate_versions.py"], cwd=root, check=True)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"ERROR: tool-version synchronization failed: {error}", file=sys.stderr)
        return 1
    print(f"Synchronized {len(paths)} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
