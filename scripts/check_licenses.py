#!/usr/bin/env python3
"""Compare reference license metadata with reviewed THIRD_PARTY_NOTICES.md anchors.

Run directly, or through check_vendored.py (the blocking Make and CI entry point).
No network access or third-party Python packages are required. YAML fails closed
until a safe parser is available in the check toolchain.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REVIEW = re.compile(r"<!-- license-review\s*\n(.*?)\n-->", re.DOTALL)
LABEL_FIELDS = {
    "license", "licence", "licenses", "licences", "licenseid",
    "licenseexpression", "licenseidentifier", "spdxlicense", "spdxlicenseid",
    "spdxlicenseidentifier", "spdxlicenseexpression",
    "licensedeclared", "licenseconcluded", "licenseinfoinfile", "datalicense",
}
URL_FIELDS = {"licenseurl", "licenceurl"}
RESTRICTIONS = {"noncommercial", "share-alike", "no-derivatives"}
SPDX_IDS = {
    "Apache-2.0", "BSD-3-Clause", "CC-BY-3.0", "CC-BY-SA-4.0",
    "CC-BY-NC-ND-4.0", "Community-Spec-1.0", "DRL-1.1", "MIT",
}
SUPPORT_FILES = {
    "reference/UPSTREAM.json", "reference/CHECKSUMS.sha256", "reference/ERRATA.md",
    "reference/security/manifest.json", "reference/security/NOTICE",
    "reference/security/AGENT_GUIDE.md", "reference/security/REFERENCE_PROTOCOL.md",
}


def matches(name: str, scope: str) -> bool:
    return name.startswith(scope) if scope.endswith("/") else name == scope


def local_path(root: Path, name: str) -> Path:
    path = root / name
    if not name or Path(name).is_absolute() or ".." in Path(name).parts:
        raise ValueError(f"not a repository-relative path: {name!r}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"path escapes the repository: {name!r}")
    return path


def unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)


def strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def validate_terms(root: Path, terms: dict[str, Any]) -> None:
    expression = terms.get("license")
    if not isinstance(expression, str) or not expression:
        raise ValueError("missing reviewed license")
    for identifier in re.split(r" AND | OR ", expression):
        if (identifier not in SPDX_IDS
                and not re.fullmatch(r"LicenseRef-[A-Za-z0-9.-]+", identifier)):
            raise ValueError(f"unrecognized reviewed license identifier: {identifier!r}")
    url = terms.get("license_url")
    if not isinstance(url, str):
        raise ValueError("missing reviewed license_url")
    name, _, fragment = url.partition("#")
    path = local_path(root, name)
    if not path.is_file():
        raise ValueError(f"reviewed license text is missing: {url}")
    if fragment:
        headings = re.findall(r"^#+ (.+)$", path.read_text(encoding="utf-8"), re.MULTILINE)
        anchors = {re.sub(r"[^\w -]", "", heading.lower()).replace(" ", "-")
                   for heading in headings}
        if fragment not in anchors:
            raise ValueError(f"reviewed license heading is missing: {url}")
    flags = terms.get("restrictions")
    if (not strings(flags) or any(flag not in RESTRICTIONS for flag in flags)
            or len(flags) != len(set(flags))):
        raise ValueError("missing or invalid reviewed restrictions")
    parts = terms.get("license_parts", {})
    if not isinstance(parts, dict):
        raise ValueError("reviewed license_parts must be an object")
    for part in parts.values():
        if not isinstance(part, dict):
            raise ValueError("reviewed license part must be an object")
        validate_terms(root, part)


def load_reviews(root: Path) -> list[dict[str, Any]]:
    text = (root / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    blocks = REVIEW.findall(text)
    if not blocks or len(blocks) != text.count("<!-- license-review"):
        raise ValueError("missing or malformed license-review anchors in THIRD_PARTY_NOTICES.md")
    reviews = []
    seen = set()
    for block in blocks:
        review = json.loads(block, object_pairs_hook=unique_keys)
        if not isinstance(review, dict):
            raise ValueError("license-review must be a JSON object")
        for field in ("sources", "paths"):
            if not strings(review.get(field)) or not review[field]:
                raise ValueError(f"license-review needs nonempty {field}")
        for source in review["sources"]:
            if source in seen:
                raise ValueError(f"duplicate notice source: {source}")
            seen.add(source)
        if not strings(review.get("immutable", [])):
            raise ValueError("immutable notice paths must be a list of strings")
        for name in review["paths"] + review.get("immutable", []):
            if not name.startswith("reference/"):
                raise ValueError(f"notice scope must be under reference/: {name}")
            local_path(root, name)
        validate_terms(root, review)
        reviews.append(review)
    return reviews


def check(root: Path = PROJECT_ROOT) -> list[str]:
    """Return actionable errors; an empty list means metadata matches the reviews."""
    errors: list[str] = []
    try:
        reviews = load_reviews(root)
        upstream = read_json(root / "reference/UPSTREAM.json")
        security = read_json(root / "reference/security/manifest.json")
        if not isinstance(upstream, dict) or not isinstance(security, dict):
            raise ValueError("license registries must be JSON objects")
    except (OSError, ValueError) as exc:
        return [str(exc)]

    by_source = {source: review for review in reviews for source in review["sources"]}
    registered: set[str] = set()
    covered: list[str] = []
    pinned: set[str] = set()
    originals: dict[tuple[str, str], Any] = {}
    consumed: set[tuple[str, str]] = set()
    immutable = {name for review in reviews for name in review.get("immutable", [])}

    def review_for(name: str) -> dict[str, Any] | None:
        candidates = [review for review in reviews
                      if any(matches(name, scope) for scope in review["paths"])]
        if len(candidates) != 1:
            errors.append(f"{name}: needs exactly one notice entry; found {len(candidates)}")
            return None
        return candidates[0]

    def labels(node: Any, terms: dict[str, Any], context: str, pointer: str = "",
               file: str = "") -> None:
        if isinstance(node, list):
            for index, item in enumerate(node):
                labels(item, terms, context, f"{pointer}/{index}", file)
        elif isinstance(node, dict):
            for key, value in node.items():
                child = pointer + "/" + key.replace("~", "~0").replace("/", "~1")
                normalized = re.sub(r"[^a-z]", "", key.lower())
                location = f"{context}#{child}"
                override = (file, child)
                if override in originals:
                    consumed.add(override)
                    if value != originals[override]:
                        errors.append(f"{location}: immutable label changed; review its override")
                    continue
                if normalized in LABEL_FIELDS:
                    actual = " AND ".join(value) if strings(value) else value
                    if actual != terms["license"]:
                        errors.append(
                            f"{location}: license {actual!r} disagrees with notice "
                            f"{terms['license']!r}"
                        )
                elif normalized in URL_FIELDS:
                    if value != terms["license_url"]:
                        errors.append(f"{location}: license_url disagrees with notice")
                elif key == "restrictions":
                    if not strings(value) or sorted(value) != sorted(terms["restrictions"]):
                        errors.append(f"{location}: restrictions disagree with notice")
                elif key in ("license_parts", "formats") and isinstance(value, dict):
                    for part, content in value.items():
                        expected = terms.get("license_parts", {}).get(part, terms)
                        if key == "formats" and part in terms.get("license_parts", {}):
                            required(content, expected, f"{context}#{child}/{part}")
                        labels(content, expected, context, f"{child}/{part}", file)
                elif key != "original_labels" or not context.startswith("license_overrides:"):
                    labels(value, terms, context, child, file)

    def required(node: Any, terms: dict[str, Any], context: str,
                 parts: bool = True) -> None:
        if not isinstance(node, dict):
            errors.append(f"{context}: source metadata must be an object")
            return
        for field in ("license", "license_url", "restrictions"):
            if field not in node:
                errors.append(f"{context}: missing {field} label")
        expected = terms.get("license_parts", {}) if parts else {}
        actual = node.get("license_parts", {})
        if not isinstance(actual, dict) or set(actual) != set(expected):
            errors.append(f"{context}: license_parts disagree with notice")
        else:
            for part, part_terms in expected.items():
                required(actual[part], part_terms, f"{context}/license_parts/{part}")

    def register(source: str, entry: Any, context: str, scopes: Any) -> None:
        terms = by_source.get(source)
        if terms is None:
            errors.append(f"{context}: source {source!r} has no notice entry")
            return
        if source in registered:
            errors.append(f"{context}: duplicate source registration: {source}")
        registered.add(source)
        required(entry, terms, context)
        labels(entry, terms, context)
        if not strings(scopes) or not scopes:
            errors.append(f"{context}: missing source paths")
            return
        for scope in scopes:
            local_path(root, scope)
            if review_for(scope) is not terms:
                errors.append(f"{context}: path {scope} belongs to a different notice")
            if not local_path(root, scope).exists():
                errors.append(f"{context}: source path is missing: {scope}")
            covered.append(scope)

    try:
        for registry, prefix, style in (
            (upstream, "reference/UPSTREAM.json", True),
            (security, "reference/security/manifest.json", False),
        ):
            for field, value in registry.items():
                if field not in ("sources", "files", "license_overrides"):
                    keys = [field] + json_keys(value)
                    if any(re.sub(r"[^a-z]", "", key.lower()) in LABEL_FIELDS | URL_FIELDS
                           for key in keys):
                        errors.append(f"{prefix}#/{field}: license label outside a source entry")
            sources = registry.get("sources")
            if not isinstance(sources, dict) or not sources:
                raise ValueError(f"{prefix}: missing source registry")
            for source, entry in sources.items():
                if not isinstance(entry, dict):
                    raise ValueError(f"{prefix}: source {source} must be an object")
                paths = entry.get("paths") if style else entry.get("files")
                if not style and strings(paths):
                    paths = ["reference/security/" + name for name in paths]
                register(source, entry, f"{prefix}#/sources/{source}", paths)
        entries = upstream.get("files")
        if not isinstance(entries, list):
            raise ValueError("reference/UPSTREAM.json: missing pinned file list")
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise ValueError(f"reference/UPSTREAM.json: invalid pinned entry {index}")
            name = entry["path"]
            local_path(root, name)
            pinned.add(name)
            terms = review_for(name)
            if terms:
                required(entry, terms, f"reference/UPSTREAM.json:{name}", parts=False)
                labels(entry, terms, f"reference/UPSTREAM.json:{name}")

        overrides = upstream.get("license_overrides", {})
        if not isinstance(overrides, dict):
            raise ValueError("license_overrides must be an object")
        for name, entry in overrides.items():
            terms = review_for(name)
            if name not in pinned | immutable:
                errors.append(f"{name}: license overrides require a pinned or immutable payload")
            if terms:
                required(entry, terms, f"license_overrides:{name}")
                labels(entry, terms, f"license_overrides:{name}")
            old = entry.get("original_labels") if isinstance(entry, dict) else None
            if not isinstance(old, dict) or not old:
                errors.append(f"{name}: override needs exact original_labels by JSON pointer")
            else:
                for pointer, value in old.items():
                    field = re.sub(r"[^a-z]", "", pointer.rsplit("/", 1)[-1].lower())
                    if field not in LABEL_FIELDS | URL_FIELDS:
                        errors.append(f"{name}#{pointer}: override is not a license label")
                    originals[name, pointer] = value
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
        return errors

    for source in sorted(set(by_source) - registered):
        errors.append(f"{source}: notice source has no machine license registry entry")

    for path in sorted((root / "reference").rglob("*")):
        if not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        try:
            local_path(root, name)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        support = (name in SUPPORT_FILES or path.name == "NOTICE" or "/LICENSES/" in name
                   or any(part.startswith(".") for part in path.relative_to(root).parts))
        terms = None if support else review_for(name)
        if not support and not any(matches(name, scope) for scope in covered):
            errors.append(f"{name}: vendored source has no machine license registry entry")
        if path.suffix.lower() in (".yaml", ".yml"):
            errors.append(f"{name}: YAML metadata requires a safe parser; use JSON for now")
        elif path.suffix.lower() == ".json" and name not in (
            "reference/UPSTREAM.json", "reference/security/manifest.json"
        ):
            try:
                node = read_json(path)
            except (OSError, ValueError) as exc:
                errors.append(f"{name}: {exc}")
                continue
            if terms is None:
                # Configuration files need no source label, but cannot hide declarations.
                if any(re.sub(r"[^a-z]", "", key.lower()) in LABEL_FIELDS | URL_FIELDS
                       for key in json_keys(node)):
                    terms = review_for(name)
            if terms:
                if not support and name not in pinned | immutable:
                    required(node, terms, name)
                labels(node, terms, name, file=name)
    for name, pointer in sorted(set(originals) - consumed):
        errors.append(f"{name}#{pointer}: immutable override target is missing")
    return errors


def json_keys(node: Any) -> list[str]:
    if isinstance(node, dict):
        return list(node) + [key for value in node.values() for key in json_keys(value)]
    if isinstance(node, list):
        return [key for value in node for key in json_keys(value)]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT, help="repository tree to check")
    args = parser.parse_args(argv)
    problems = check(args.root.resolve())
    if problems:
        print("License consistency check failed:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("License consistency check passed: all reference sources match reviewed notices.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
