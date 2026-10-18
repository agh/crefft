#!/usr/bin/env python3
"""Build Crefft.zip and Crefft.zip.sha256 without host-dependent metadata."""

from __future__ import annotations

import argparse
import hashlib
import stat
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "configs/vale/Crefft"
PACKAGE_FILES = {
    ".vale.ini",
    "styles/Crefft/Direct.yml",
    "styles/Crefft/Literals.yml",
    "styles/Crefft/US.yml",
}


def build_package(output_dir: Path, source: Path = SOURCE) -> str:
    paths = sorted(source.rglob("*"))
    if any(path.is_symlink() for path in paths):
        raise ValueError("The Vale package must not contain symlinks")
    files = [path for path in paths if path.is_file()]
    if {path.relative_to(source).as_posix() for path in files} != PACKAGE_FILES:
        raise ValueError("The Vale package must contain only its config and three rules")

    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / "Crefft.zip"
    # Stored entries avoid differences between compression library versions.
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as package:
        for path in files:
            name = f"Crefft/{path.relative_to(source).as_posix()}"
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            package.writestr(entry, path.read_bytes())

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output_dir / "Crefft.zip.sha256").write_text(
        f"{digest}  Crefft.zip\n", encoding="ascii"
    )
    return digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        digest = build_package(args.output_dir)
    except ValueError as error:
        parser.error(str(error))
    print(f"{digest}  Crefft.zip")


if __name__ == "__main__":
    main()
