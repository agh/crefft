#!/usr/bin/env python3
"""Verify a signed release on the private forge before publishing to GitHub."""

from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def release_push(tag: str) -> list[str]:
    if not re.fullmatch(r"v[0-9]{4}\.(?:[1-9]|1[0-2])\.(?:0|[1-9][0-9]*)", tag):
        raise ValueError("tag must be a release name such as v2026.10.0")

    # Do not fetch tags into the local tag namespace: a moved remote tag must
    # be compared with the signed local object, not replace it.
    for remote in ("forge", "github"):
        git(
            "fetch", "--no-tags", remote,
            f"+refs/heads/main:refs/remotes/{remote}/main",
        )

    tag_ref = f"refs/tags/{tag}"
    local_object = git("rev-parse", "--verify", tag_ref)
    remote_tag = git("ls-remote", "--refs", "forge", tag_ref).splitlines()
    if remote_tag != [f"{local_object}\t{tag_ref}"]:
        raise ValueError("local tag and forge tag must exist at the same object")
    if git("cat-file", "-t", local_object) != "tag":
        raise ValueError("release tag must be annotated")
    git("tag", "-v", tag)
    headers = git("cat-file", "tag", local_object).split("\n\n", 1)[0].splitlines()
    if f"tag {tag}" not in headers:
        raise ValueError("signed tag name must match the release ref")

    commit = git("rev-parse", "--verify", f"{local_object}^{{commit}}")
    version = git("show", f"{commit}:VERSION")
    if tag != f"v{version}":
        raise ValueError("tag must equal v plus VERSION at the tagged commit")
    if commit != git("rev-parse", "--verify", "refs/remotes/forge/main"):
        raise ValueError("tagged commit must be forge/main")
    git("merge-base", "--is-ancestor", "refs/remotes/github/main", commit)
    return ["git", "push", "github", f"{commit}:refs/heads/main", tag_ref]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--push", action="store_true", help="execute the verified push")
    args = parser.parse_args()
    try:
        command = release_push(args.tag)
        print(shlex.join(command), flush=True)
        if args.push:
            subprocess.run(command, check=True)
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip()
        print(
            f"Refusing release: {shlex.join(error.cmd)} failed"
            f"{': ' + detail if detail else ''}",
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError) as error:
        print(f"Refusing release: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
