"""Check the release archive's bytes, contents, and metadata."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_vale_package import SOURCE, build_package  # noqa: E402


class ValePackageTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.work = Path(self.tmpdir.name)

    def test_consecutive_builds_are_byte_identical(self):
        first, second = self.work / "first", self.work / "second"
        digest = build_package(first)
        self.assertEqual(digest, build_package(second))
        self.assertEqual((first / "Crefft.zip").read_bytes(), (second / "Crefft.zip").read_bytes())
        self.assertEqual(digest, hashlib.sha256((first / "Crefft.zip").read_bytes()).hexdigest())
        self.assertEqual(
            (first / "Crefft.zip.sha256").read_text(), f"{digest}  Crefft.zip\n"
        )

    def test_archive_contains_exactly_the_package_files(self):
        build_package(self.work)
        expected = sorted(
            f"Crefft/{path.relative_to(SOURCE).as_posix()}"
            for path in SOURCE.rglob("*") if path.is_file()
        )
        with zipfile.ZipFile(self.work / "Crefft.zip") as package:
            self.assertEqual(package.namelist(), expected)
            self.assertEqual(len(expected), 4)
            for entry in package.infolist():
                self.assertEqual(entry.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(entry.external_attr >> 16, stat.S_IFREG | 0o644)
                self.assertEqual(entry.create_system, 3)
                self.assertEqual(entry.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(
                    package.read(entry), (SOURCE.parent / entry.filename).read_bytes()
                )

    def test_source_permissions_and_timestamps_do_not_affect_bytes(self):
        source = self.work / "source"
        shutil.copytree(SOURCE, source)
        first = self.work / "first"
        digest = build_package(first, source)
        for path in source.rglob("*"):
            if path.is_file():
                path.chmod(0o600)
                os.utime(path, (946684800, 946684800))
        self.assertEqual(digest, build_package(self.work / "second", source))

    def test_extra_files_and_symlinks_are_rejected(self):
        source = self.work / "source"
        shutil.copytree(SOURCE, source)
        extra = source / "accept.txt"
        extra.write_text("Example\n")
        with self.assertRaisesRegex(ValueError, "only its config"):
            build_package(self.work / "output", source)
        extra.unlink()
        extra.symlink_to(source / ".vale.ini")
        with self.assertRaisesRegex(ValueError, "symlinks"):
            build_package(self.work / "output", source)


if __name__ == "__main__":
    unittest.main()
