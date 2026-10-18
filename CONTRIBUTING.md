# Contributing to crefft

> [crefft](README.md) > Contributing

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
"SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and
"OPTIONAL" in this document are to be interpreted as described in
BCP 14 [RFC 2119](https://datatracker.ietf.org/doc/html/rfc2119)
[RFC 8174](https://datatracker.ietf.org/doc/html/rfc8174) when, and only
when, they appear in all capitals, as shown here.

crefft accepts contributions through [issues](https://github.com/agh/crefft/issues/new/choose),
not pull requests. The maintainer makes the changes. Pull requests from
anyone other than the maintainer are closed with a pointer to the issue
forms; Dependabot pull requests continue.

**Why**: issues let the maintainer assess the evidence and scope before
implementing a consistent change across the guides.

This document explains how to propose a change and what the maintainer's
changes **MUST** satisfy before they are merged.

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).

## Quick Reference

| Task | Command |
| ---- | ------- |
| Run every check | `make check` |
| Lint Markdown | `npx markdownlint-cli2@0.23.2 "**/*.md"` |
| Validate tool versions | `python3 scripts/validate_versions.py` |
| Validate a JSON file | `jq . reference/security/manifest.json` |

## What Belongs Here

crefft covers language guides, framework guides, process guides, AI-assisted
development practices, ready-to-copy configuration files, and vendored
upstream reference material.

A proposal **SHOULD** fall into one of four shapes:

1. **Fix a guide** — a rule that is wrong, an example that does not run, a
   command that no longer exists, a broken link.
2. **Update a version** — a pinned tool version that has moved on, or a tool
   that is now deprecated.
3. **Add a guide** — a language, framework, or topic crefft does not cover.
4. **Correct provenance** — attribution, license, or notice problems in
   `reference/` or [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Every proposal, including a small fix, **MUST** start with an
[issue form](https://github.com/agh/crefft/issues/new/choose).
Use **Bug in a guide** for incorrect prose, examples, configuration, links,
or provenance; **Outdated version** for stale pins; and **New guide proposal**
for missing coverage.

Search existing issues first. A useful report identifies the latest crefft
release, the affected file and heading or line, the expected and actual
behavior, reproduction steps or the exact incorrect text, and primary-source
evidence. Version claims **MUST** include a source URL and the date checked.
Suggested wording belongs in the issue; a pull request is not needed.

**Why**: a reproducible, sourced issue gives the maintainer enough information
to verify the problem without guessing.

## House Rules

These rules still bind the maintainer's own changes.

**Why**: an issues-only contribution policy does not lower the standards for
the changes that ship.

- **MUST** use [RFC 2119](https://datatracker.ietf.org/doc/html/rfc2119)
  keywords (MUST, MUST NOT, SHOULD, SHOULD NOT, MAY) in **bold uppercase**,
  and **MUST** include the RFC 2119 boilerplate after the title of every
  guide.
- **MUST** include a rationale ("Why") for every major recommendation. A rule
  without a reason is an opinion.
- **MUST** provide Do/Don't code examples for style rules.
- **MUST** pin every tool version. No guide may reference a tool without
  stating the version it was verified against.
- **MUST** include a Quick Reference table at the top of every language guide,
  and a navigation breadcrumb immediately after the title.
- **MUST NOT** use vague language: "consider," "you might want to," "it is
  generally recommended."
- **MUST NOT** recommend a deprecated tool without a migration path.
- **SHOULD** keep lines at or below 100 characters, including code blocks.
- **SHOULD** link to an existing guide rather than duplicating its content.
- **SHOULD** use US English spelling in all human-facing prose, including
  Welsh-named projects. Welsh names, proper nouns, quotations, and upstream
  tool and code spellings stay unchanged.
  `make typos` enforces this rule; **Why**: spelling drift fails locally and in CI.
- **MUST** use a serial comma in lists of three or more items joined by
  "and" or "or"; two-item phrases take no serial comma.
- **MUST** put commas and periods inside closing quotation marks. Colons
  and semicolons stay outside; question and exclamation marks go inside only
  when they belong to the quoted text.
- **MUST** put literals in code spans, not quotation marks, including
  commands, flags, file names, paths, configuration values, and text to type
  or search for. Surrounding punctuation stays outside the code span.

### Verifying Time-Sensitive Claims

Version numbers, release dates, and deprecation timelines **MUST** be checked
against a current source before they are written down, and the source
**SHOULD** be cited in the issue and the maintainer's pull request.
Memory is not evidence.

**Why**: release information changes independently of crefft's text.

### Vendored Material

`reference/` holds third-party work under third-party licenses.

- **MUST NOT** add material to `reference/` without also recording its
  upstream URL, license, license URL, and required attribution in
  [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and copying the license
  text into the vendor directory where the license requires it.
- **MUST NOT** edit `reference/security/cis/` — that material is
  CC BY-NC-ND 4.0 and carries a NoDerivatives condition. See
  [`reference/security/cis/NOTICE`](reference/security/cis/NOTICE).
- **MUST** record modifications to CC BY, CC BY-SA, and Apache-2.0 material in
  the vendor directory's `NOTICE` file.

## Maintainer Development Workflow

1. Verify the issue's evidence and scope.
2. Create a branch in the repository.
3. Make the change, following the house rules.
4. Run `make check` and fix everything it reports before committing.
5. Commit using [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).
6. Open the maintainer's pull request against `main` and fill in the template.

**Why**: the maintainer's pull requests retain the same review record and
checks even though external pull requests are not accepted.

### Checks

`make check` **MUST** pass before every commit. It runs Markdown linting,
US spelling, internal links, secret scanning, script unit tests, tool-version
validation, vendored integrity and license checks, and advisory snippet checks.
See the [Makefile](Makefile) for the exact commands and pinned versions.

**Why**: the full check catches cross-guide and tooling regressions that a
single-file lint cannot detect.

Markdown lint configuration lives in `.markdownlint.json` and
`reference/security/.markdownlint.json`. Do not relax a rule to make a lint
error go away; fix the content.

### Commit Messages

```text
type(scope): description

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `ci`.
Scope is the guide or area touched.

Examples:

- `feat(python): add Hypothesis fuzzing section`
- `fix(go): correct golangci-lint config syntax`
- `docs(readme): update navigation table`
- `chore(reference): record Uber Go guide modifications in NOTICE`

The subject line **MUST** be imperative mood and at most 72 characters.

### Changelog and Version

Every user-visible change **MUST** add an entry to [CHANGELOG.md](CHANGELOG.md)
under `## [Unreleased]`, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Do not edit `VERSION`
in a pull request; releases are cut separately following
[calendar versioning (`YYYY.M.N`)](guides/process/versioning.md) for crefft
itself. The guides require Semantic Versioning 2.0.0 for libraries in every
ecosystem and CalVer for everything else. A project that publishes both a
command and importable packages is a library.
Breaking changes **MUST** go under `### Breaking`, first in the release
section, and commits **MUST** retain `!` or a `BREAKING CHANGE:` footer.

**Why**: dependency resolvers assume SemVer compatibility ranges for libraries.
A calendar version records release order instead; migration notes make
incompatible changes explicit under either policy.

## Adding a New Guide

1. Copy the structure of an existing guide of the same kind — for example
   [`guides/languages/python.md`](guides/languages/python.md).
2. Add the navigation breadcrumb and the RFC 2119 boilerplate.
3. Add the Quick Reference table.
4. Write a "Why" for every tool choice, with the version pinned and the source
   for that version cited in the pull request.
5. Add a "See Also" section linking related guides.
6. Add the guide to the navigation tables in [README.md](README.md).
7. Add a `CHANGELOG.md` entry.

## Reporting Problems

Use the [issue forms](https://github.com/agh/crefft/issues/new/choose):

- **Bug in a guide** — a rule, example, or command that is wrong.
- **Outdated version** — a pinned version that has moved on. Include the
  current version and the URL you checked.
- **New guide proposal** — a language, framework, or topic crefft should
  cover.

Security vulnerabilities **MUST NOT** be reported in public issues. See
[SECURITY.md](SECURITY.md).

**Why**: public reports can expose readers before a fix is available.

## Support

Support and issue replies are best effort, for the latest release only.
There are no service levels, promised response times, or guaranteed fixes.
See [SECURITY.md](SECURITY.md) for private security reporting.

**Why**: crefft has one maintainer and does not provide a support service.
