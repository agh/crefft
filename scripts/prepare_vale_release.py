#!/usr/bin/env python3
"""Validate a release tag and extract its changelog section as release notes."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def release_notes(root: Path, tag: str) -> str:
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d{4}\.[1-9]\d?\.\d+", version) or tag != f"v{version}":
        raise ValueError("Release tag must equal v$(cat VERSION)")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    section = re.search(
        rf"^## \[{re.escape(version)}\](?: - \d{{4}}-\d{{2}}-\d{{2}})?\n"
        r"(?P<notes>.*?)(?=^## |\Z)",
        changelog, re.MULTILINE | re.DOTALL,
    )
    if not section or not section["notes"].strip():
        raise ValueError(f"CHANGELOG.md has no nonempty release section for {version}")
    return section["notes"].strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        notes = release_notes(ROOT, args.tag)
    except ValueError as error:
        parser.error(str(error))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "notes.md").write_text(notes, encoding="utf-8")


if __name__ == "__main__":
    main()
