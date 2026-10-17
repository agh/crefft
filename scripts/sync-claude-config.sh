#!/usr/bin/env bash
# Install crefft's Claude Code configuration into a project's .claude directory.
#
# Requires Bash, Python 3, and Git. Run from a clean release checkout.
# Only files recorded in .claude/crefft-receipt.json belong to crefft.
#
# Usage: scripts/sync-claude-config.sh --ref v2026.10.0 [--commit SHA]
#          [--adopt] [--overwrite-settings] [project-dir]
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec python3 - "$script_dir/.." "$@" <<'PY'
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

CALVER = r"[0-9]{4}\.(1[0-2]|[1-9])\.(0|[1-9][0-9]*)"
COMMIT = r"(?:[0-9a-f]{40}|[0-9a-f]{64})"
COMPONENTS = {
    "agents": "agents",
    "commands": "commands",
    "skills": "configs/claude/skills",
    "infrastructure": "configs/claude/infrastructure",
}


def fail(message: str) -> None:
    raise ValueError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def valid_path(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        name == path.as_posix()
        and not path.is_absolute()
        and ".." not in path.parts
        and (
            name == "settings.json"
            or (len(path.parts) > 1 and path.parts[0] in COMPONENTS)
        )
    )


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True
    )
    if result.returncode:
        fail(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".crefft-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            os.fchmod(handle.fileno(), mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> None:
    root = Path(sys.argv.pop(1)).resolve()
    parser = argparse.ArgumentParser(prog="sync-claude-config")
    parser.add_argument("--ref", required=True, help="release tag, such as v2026.10.0")
    parser.add_argument("--commit", help="expected full commit SHA")
    parser.add_argument("--adopt", action="store_true", help="own identical existing files")
    parser.add_argument("--overwrite-settings", action="store_true")
    parser.add_argument("project_dir", nargs="?", default=".")
    args = parser.parse_args()
    if not re.fullmatch(f"v{CALVER}", args.ref):
        fail("--ref must be a calendar release tag such as v2026.10.0")
    if args.commit is not None and not re.fullmatch(COMMIT, args.commit.lower()):
        fail("--commit must be a full commit SHA")

    sources = {}
    for component, relative in COMPONENTS.items():
        source = root / relative
        if source.is_symlink():
            fail(f"source symlink is not allowed: {source}")
        if not source.is_dir():
            fail(f"missing source component: {source}")
        for path in sorted(source.rglob("*")):
            if path.is_symlink():
                fail(f"source symlink is not allowed: {path}")
            if path.is_dir():
                continue
            if not path.is_file():
                fail(f"source is not a regular file: {path}")
            name = f"{component}/{path.relative_to(source).as_posix()}"
            sources[name] = path
    settings = root / "configs/claude/settings.json"
    if settings.is_symlink() or not settings.is_file():
        fail(f"missing source settings or not a regular file: {settings}")
    sources["settings.json"] = settings

    commit = git(root, "rev-parse", "--verify", "HEAD")
    tagged = git(root, "rev-parse", "--verify", f"refs/tags/{args.ref}^{{commit}}")
    if commit != tagged:
        fail(f"checkout {commit} does not match release tag {args.ref} ({tagged})")
    if args.commit is not None and commit != args.commit.lower():
        fail(f"commit mismatch: expected {args.commit}, checkout is {commit}")
    version = (root / "VERSION").read_text(encoding="utf-8")
    if version not in (args.ref[1:], args.ref[1:] + "\n"):
        fail("VERSION must contain one calendar version matching --ref")
    inputs = [*COMPONENTS.values(), "configs/claude/settings.json",
              "VERSION", "scripts/sync-claude-config.sh"]
    dirty = git(
        root, "status", "--porcelain", "--ignored", "--untracked-files=all", "--", *inputs
    )
    if dirty:
        fail(f"modified source in release checkout:\n{dirty}")

    # Read every payload before creating any destination or modifying any file.
    payloads = {name: path.read_bytes() for name, path in sources.items()}
    hashes = {name: digest(data) for name, data in payloads.items()}
    modes = {name: stat.S_IMODE(path.stat().st_mode) for name, path in sources.items()}
    project = Path(args.project_dir).resolve(strict=True)
    if not project.is_dir():
        fail(f"project directory not found: {project}")
    dest = project / ".claude"
    if dest.is_symlink() or (dest.exists() and not dest.is_dir()):
        fail(f"destination conflict: {dest} is not a real directory")
    receipt_path = dest / "crefft-receipt.json"
    previous = {}
    if receipt_path.is_symlink() or (receipt_path.exists() and not receipt_path.is_file()):
        fail(f"invalid receipt: {receipt_path} is not a regular file")
    if receipt_path.exists():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(f"invalid receipt: {receipt_path}: {exc}")
        if (
            not isinstance(receipt, dict)
            or receipt.get("schema_version") != 1
            or not isinstance(receipt.get("release"), str)
            or not re.fullmatch(f"v{CALVER}", receipt["release"])
            or not isinstance(receipt.get("commit"), str)
            or not re.fullmatch(COMMIT, receipt["commit"])
            or not isinstance(receipt.get("files"), dict)
        ):
            fail(f"invalid receipt: {receipt_path}")
        previous = receipt["files"]
        for name, checksum in previous.items():
            if (
                not valid_path(name)
                or not isinstance(checksum, str)
                or not re.fullmatch(r"[0-9a-f]{64}", checksum)
            ):
                fail(f"invalid receipt entry: {name!r}")

    conflicts = set()
    writes = {}
    removals = []
    owned = {}
    for name in sorted(payloads.keys() | previous.keys()):
        path = dest / name
        parents = [dest]
        for part in PurePosixPath(name).parts[:-1]:
            parents.append(parents[-1] / part)
        blocked = False
        for parent in parents:
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                conflicts.add(f"{parent}: not a real directory")
                blocked = True
        if blocked:
            continue
        if path.is_symlink() or (path.exists() and not path.is_file()):
            conflicts.add(f"{path}: not a regular file")
            continue
        current = digest(path.read_bytes()) if path.exists() else None
        if name == "settings.json" and current is not None and not args.overwrite_settings:
            if name in previous:
                owned[name] = previous[name]
            elif args.adopt and current == hashes[name]:
                owned[name] = current
            continue
        if name not in payloads:
            if current is not None:
                if current != previous[name]:
                    conflicts.add(f"{path}: modified owned file")
                else:
                    removals.append(path)
            continue
        if current is not None:
            if name not in previous and not (name == "settings.json" and args.overwrite_settings):
                if not (args.adopt and current == hashes[name]):
                    conflicts.add(f"{path}: unowned file (use --adopt only for identical content)")
                    continue
            elif name != "settings.json" and current not in (previous[name], hashes[name]):
                conflicts.add(f"{path}: modified owned file")
                continue
        owned[name] = hashes[name]
        if current != hashes[name]:
            writes[name] = payloads[name]
    if conflicts:
        fail("destination conflicts; nothing changed:\n" + "\n".join(sorted(conflicts)))

    receipt_data = (json.dumps(
        {"schema_version": 1, "release": args.ref, "commit": commit, "files": owned},
        indent=2, sort_keys=True,
    ) + "\n").encode()
    receipt_changed = not receipt_path.exists() or receipt_path.read_bytes() != receipt_data
    for name, data in writes.items():
        atomic_write(dest / name, data, modes[name])
    for path in removals:
        path.unlink()
    if receipt_changed:
        atomic_write(receipt_path, receipt_data, 0o644)
    status = "installed" if writes or removals or receipt_changed else "unchanged"
    print(f"sync-claude-config: {status} {dest} from {args.ref} ({commit})")


try:
    main()
except (OSError, ValueError) as exc:
    print(f"sync-claude-config: {exc}", file=sys.stderr)
    sys.exit(1)
PY
