#!/usr/bin/env python3
"""License consistency regressions using isolated, temporary reference trees."""

from __future__ import annotations

import copy
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_licenses as cl  # noqa: E402
import check_vendored as cv  # noqa: E402


class LicenseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.terms = {
            "license": "MIT",
            "license_url": "reference/example/LICENSE",
            "restrictions": [],
        }
        self.name = "reference/security/example/data.json"
        self.style_review = {
            "sources": ["example"], "paths": ["reference/example/"], **self.terms,
        }
        self.security_review = {
            "sources": ["security_example"], "paths": ["reference/security/example/"],
            **self.terms,
        }
        self.upstream = {
            "sources": {"example": {"paths": ["reference/example/"], **self.terms}},
            "files": [],
        }
        self.security = {
            "sources": {"security_example": {"files": ["example/data.json"], **self.terms}},
        }
        self.write("reference/example/LICENSE", "Synthetic license text for a test fixture.\n")
        self.write("reference/example/guide.md", "# Synthetic guide\n")
        self.write(self.name, self.terms)
        self.save()

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(content, indent=2) if not isinstance(content, str) else content
        path.write_text(text, encoding="utf-8")

    def save(self):
        self.write("reference/UPSTREAM.json", self.upstream)
        self.write("reference/security/manifest.json", self.security)
        self.write(
            "THIRD_PARTY_NOTICES.md",
            "# Synthetic notices\n\n" + "\n".join(
                "<!-- license-review\n" + json.dumps(review, indent=2) + "\n-->\n"
                for review in (self.style_review, self.security_review)
            ),
        )

    def assert_failure(self, text):
        errors = cl.check(self.root)
        self.assertTrue(errors, "checker unexpectedly accepted invalid metadata")
        self.assertIn(text, "\n".join(errors))

    def test_matching_labels_pass(self):
        self.assertEqual(cl.check(self.root), [])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cl.main(["--root", str(self.root)]), 0)

    def test_contradicting_payload_label_fails(self):
        self.write(self.name, {**self.terms, "license": "Apache-2.0"})
        self.assert_failure("license 'Apache-2.0' disagrees with notice 'MIT'")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cl.main(["--root", str(self.root)]), 1)

    def test_contradicting_manifest_label_fails(self):
        self.security["sources"]["security_example"]["license"] = "Apache-2.0"
        self.save()
        self.assert_failure("reference/security/manifest.json#/sources/security_example")

    def test_missing_labels_fail_in_payload_and_registries(self):
        upstream = copy.deepcopy(self.upstream)
        security = copy.deepcopy(self.security)
        for location in ("payload", "security", "upstream"):
            for field in ("license", "license_url", "restrictions"):
                with self.subTest(location=location, field=field):
                    self.upstream = copy.deepcopy(upstream)
                    self.security = copy.deepcopy(security)
                    self.write(self.name, self.terms)
                    target = copy.deepcopy(self.terms)
                    del target[field]
                    if location == "payload":
                        self.write(self.name, target)
                    elif location == "security":
                        self.security["sources"]["security_example"] = {
                            "files": ["example/data.json"], **target,
                        }
                    else:
                        self.upstream["sources"]["example"] = {
                            "paths": ["reference/example/"], **target,
                        }
                    self.save()
                    self.assert_failure(f"missing {field} label")

    def test_source_with_no_notice_fails(self):
        self.security["sources"]["unreviewed"] = {
            "files": ["unreviewed/data.json"], **self.terms,
        }
        self.write("reference/security/unreviewed/data.json", self.terms)
        self.save()
        self.assert_failure("source 'unreviewed' has no notice entry")

    def test_unregistered_source_file_fails(self):
        self.write("reference/security/example/unregistered.json", self.terms)
        self.assert_failure("vendored source has no machine license registry entry")

    def test_unregistered_vendor_directory_fails(self):
        self.write("reference/unreviewed/guide.md", "# Unreviewed\n")
        self.assert_failure("reference/unreviewed/guide.md: needs exactly one notice entry")

    def test_missing_source_registry_fails(self):
        del self.security["sources"]["security_example"]
        self.save()
        self.assert_failure("missing source registry")

    def test_contradicting_license_url_fails(self):
        self.write(self.name, {**self.terms, "license_url": "https://example.com/MIT"})
        self.assert_failure("license_url disagrees with notice")

    def test_restriction_flags_are_checked(self):
        for value in (["noncommercial"], ["noncommercial", None], None):
            with self.subTest(value=value):
                self.write(self.name, {**self.terms, "restrictions": value})
                self.assert_failure("restrictions disagree with notice")

    def test_alternate_license_fields_are_checked(self):
        for field in ("licenses", "spdx_license_id", "SPDX-License-Identifier",
                      "licenseDeclared", "licenseConcluded", "dataLicense"):
            with self.subTest(field=field):
                self.write(self.name, {**self.terms, field: "Apache-2.0"})
                self.assert_failure("disagrees with notice")

    def test_license_list_passes_only_when_it_matches(self):
        self.write(self.name, {**self.terms, "licenses": ["MIT"]})
        self.assertEqual(cl.check(self.root), [])
        self.write(self.name, {**self.terms, "licenses": ["MIT", "Apache-2.0"]})
        self.assert_failure("disagrees with notice")

    def test_spdx_document_ids_and_capability_booleans_are_not_licenses(self):
        self.write(self.name, {
            **self.terms, "spdxId": "SPDXRef-DOCUMENT", "license_tracking": True,
        })
        self.assertEqual(cl.check(self.root), [])

    def test_nested_labels_cannot_hide_in_arrays_or_original_labels(self):
        for nested in ({"items": [{"license": "Apache-2.0"}]},
                       {"original_labels": {"license": "Apache-2.0"}}):
            with self.subTest(nested=nested):
                self.write(self.name, {**self.terms, **nested})
                self.assert_failure("disagrees with notice")

    def test_registry_root_cannot_hide_an_extra_license(self):
        self.upstream["metadata"] = {"license": "Apache-2.0"}
        self.save()
        self.assert_failure("license label outside a source entry")

    def test_duplicate_json_labels_fail(self):
        self.write(self.name, '{"license": "Apache-2.0", "license": "MIT"}')
        self.assert_failure("duplicate JSON key: license")

    def test_bad_json_fails(self):
        self.write(self.name, "{")
        self.assert_failure(self.name)

    def test_yaml_fails_closed(self):
        self.write("reference/example/source.yaml", "license: Apache-2.0\n")
        self.assert_failure("YAML metadata requires a safe parser")

    def test_missing_or_malformed_reviews_fail(self):
        for content in ("# No anchors\n", "<!-- license-review\n{}\n"):
            with self.subTest(content=content):
                self.write("THIRD_PARTY_NOTICES.md", content)
                self.assert_failure("missing or malformed license-review anchors")

    def test_missing_local_license_text_fails(self):
        (self.root / self.terms["license_url"]).unlink()
        self.assert_failure("reviewed license text is missing")

    def test_missing_local_license_heading_fails(self):
        self.security_review["license_url"] = "THIRD_PARTY_NOTICES.md#missing"
        self.save()
        self.assert_failure("reviewed license heading is missing")

    def test_path_escape_fails(self):
        self.upstream["sources"]["example"]["paths"] = ["reference/../outside/"]
        self.save()
        self.assert_failure("not a repository-relative path")

    def test_symlink_cannot_read_a_license_outside_the_tree(self):
        (self.root / "reference/example/external.json").symlink_to(
            self.root.parent / "outside.json"
        )
        self.upstream["sources"]["example"]["paths"] = [
            "reference/example/external.json",
        ]
        self.save()
        self.assert_failure("path escapes the repository")

    def test_pinned_payload_label_is_corrected_only_in_registry(self):
        self.write(self.name, {"license": "Old custom terms"})
        before = (self.root / self.name).read_bytes()
        self.upstream["files"] = [{"path": self.name, "sha256": "unused", **self.terms}]
        self.upstream["license_overrides"] = {
            self.name: {**self.terms, "original_labels": {"/license": "Old custom terms"}},
        }
        self.save()
        self.assertEqual(cl.check(self.root), [])
        self.assertEqual((self.root / self.name).read_bytes(), before)
        self.upstream["license_overrides"][self.name]["license"] = "Apache-2.0"
        self.save()
        self.assert_failure("license 'Apache-2.0' disagrees with notice 'MIT'")

    def test_pinned_registry_missing_label_fails(self):
        self.upstream["files"] = [{"path": self.name, "sha256": "unused"}]
        self.save()
        self.assert_failure("missing license label")

    def test_unpinned_mutable_payload_cannot_override_a_contradiction(self):
        self.upstream["license_overrides"] = {
            self.name: {**self.terms, "original_labels": {"/license": "MIT"}},
        }
        self.save()
        self.assert_failure("license overrides require a pinned or immutable payload")

    def test_immutable_override_is_exact_and_must_exist(self):
        self.security_review["immutable"] = [self.name]
        self.upstream["license_overrides"] = {
            self.name: {**self.terms, "original_labels": {"/license": "Old terms"}},
        }
        self.save()
        self.assert_failure("immutable label changed")
        self.write(self.name, {})
        self.assert_failure("immutable override target is missing")

    def test_combined_dataset_parts_are_required_and_checked(self):
        part = {**self.terms, "license": "BSD-3-Clause"}
        combined = {
            **self.terms, "license": "MIT AND BSD-3-Clause",
            "license_parts": {"client": self.terms, "server": part},
        }
        self.security_review.update(combined)
        self.security["sources"]["security_example"].update(combined)
        self.write(self.name, combined)
        self.save()
        self.assertEqual(cl.check(self.root), [])
        self.write(self.name, {**combined, "license_parts": {"client": self.terms}})
        self.assert_failure("license_parts disagree with notice")
        self.write(self.name, {**combined, "license_parts": {
            "client": self.terms, "server": self.terms,
        }})
        self.assert_failure("disagrees with notice 'BSD-3-Clause'")

    def test_nested_format_label_cannot_be_deleted(self):
        combined = {**self.terms, "license_parts": {"client": self.terms}}
        self.security_review.update(combined)
        self.security["sources"]["security_example"].update(combined)
        self.write(self.name, {**combined, "formats": {"client": {}}})
        self.save()
        self.assert_failure("missing license label")

    def test_original_attack_label_is_rejected(self):
        self.security_review.update({
            "license": "LicenseRef-MITRE-ATTACK",
            "license_url": self.terms["license_url"],
        })
        self.security["sources"]["security_example"]["license"] = "CC-BY-4.0"
        self.save()
        self.assert_failure("license 'CC-BY-4.0' disagrees with notice 'LicenseRef-MITRE-ATTACK'")

    def test_original_ja4_blanket_label_is_rejected(self):
        self.security_review["license"] = "BSD-3-Clause AND LicenseRef-FoxIO-1.1"
        self.security["sources"]["security_example"]["license"] = self.security_review["license"]
        self.write(self.name, {**self.terms, "license": "BSD-3-Clause"})
        self.save()
        self.assert_failure(
            "license 'BSD-3-Clause' disagrees with notice 'BSD-3-Clause AND LicenseRef-FoxIO-1.1'"
        )

    def test_vendored_entry_point_propagates_license_failure(self):
        with patch.object(cv, "load_manifest", return_value={"files": [{"path": self.name}]}), \
                patch.object(cv, "verify", return_value=0), \
                patch.object(cv, "check_licenses", return_value=1) as checker, \
                patch.object(sys, "argv", ["check_vendored.py"]), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(cv.main(), 1)
            checker.assert_called_once_with([])


class ShippedLicenseTests(unittest.TestCase):
    def test_original_known_labels_fail_in_the_shipped_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(cl.PROJECT_ROOT / "reference", root / "reference")
            for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
                shutil.copyfile(cl.PROJECT_ROOT / name, root / name)
            self.assertEqual(cl.check(root), [])
            for name, pointer, old in (
                ("reference/security/manifest.json",
                 ["sources", "mitre_attack", "license"], "CC-BY-4.0"),
                ("reference/security/fingerprints/ja4/malware-signatures.json",
                 ["license"], "BSD-3-Clause"),
            ):
                with self.subTest(path=name):
                    path = root / name
                    original = path.read_bytes()
                    node = json.loads(original)
                    target = node
                    for key in pointer[:-1]:
                        target = target[key]
                    target[pointer[-1]] = old
                    path.write_text(json.dumps(node), encoding="utf-8")
                    errors = cl.check(root)
                    self.assertEqual(len(errors), 1, errors)
                    self.assertIn("disagrees with notice", errors[0])
                    path.write_bytes(original)
            self.assertEqual(cl.check(root), [])


if __name__ == "__main__":
    unittest.main()
