# Contributing to crefft

> [crefft](README.md) > Contributing

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
"SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and
"OPTIONAL" in this document are to be interpreted as described in
BCP 14 [RFC 2119](https://datatracker.ietf.org/doc/html/rfc2119)
[RFC 8174](https://datatracker.ietf.org/doc/html/rfc8174) when, and only
when, they appear in all capitals, as shown here.

crefft is developed in a private repository. GitHub carries tagged
releases and the corresponding `main`, not ongoing development. GitHub issues,
pull requests, projects, the wiki, and discussions are disabled. There is no
public contribution or support channel.

Security reports use
[GitHub private vulnerability reporting](https://github.com/agh/crefft/security/advisories/new),
the only public reporting channel. See [SECURITY.md](SECURITY.md).

**Why**: development and review stay private, while releases and security
reporting remain accessible to readers.

This document records the maintainer's development and release requirements;
it is not an invitation to submit changes on GitHub.

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).

## Quick Reference

| Task | Command |
| ---- | ------- |
| Run every check | `make check` |
| Lint Markdown | `npx markdownlint-cli2@0.23.2 "**/*.md"` |
| Check writing rules and package | `make vale` |
| Validate tool versions | `python3 scripts/validate_versions.py` |
| Validate a JSON file | `jq . reference/security/manifest.json` |
| Check the site | `make site-check` |
| Preview release publication | `make publish-release TAG=vYYYY.M.N` |

## Scope

crefft covers language guides, framework guides, process guides, AI-assisted
development practices, ready-to-copy configuration files, and vendored
upstream reference material.

Changes **SHOULD** fall into one of four shapes:

1. **Fix a guide** — a rule that is wrong, an example that does not run, a
   command that no longer exists, a broken link.
2. **Update a version** — a pinned tool version that has moved on, or a tool
   that is now deprecated.
3. **Add a guide** — a language, framework, or topic crefft does not cover.
4. **Correct provenance** — attribution, license, or notice problems in
   `reference/` or [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

The private review record **MUST** identify the affected file and heading or
line, expected and actual behavior, reproduction steps or the exact incorrect
text, and primary-source evidence. Version claims **MUST** include a source
URL and the date checked.

**Why**: reproducible evidence defines the scope without a public issue tracker.

## House Rules

These rules still bind the maintainer's own changes.

**Why**: private development does not lower the standards for changes that ship.

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
  `make typos` checks general spelling, and `make vale` checks the bounded
  house spelling rules; **Why**: spelling drift fails locally and in CI.
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
**SHOULD** be cited in the private review record.
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

1. Verify the evidence and scope on the private forge.
2. Create a branch on the private forge; development branches **MUST NOT**
   be pushed to `github`.
3. Make the change, following the house rules.
4. Run `make check` and fix everything it reports before committing.
5. Sign the commit, include the DCO sign-off, and use
   [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).
6. Open a pull request against the private forge's `main` and fill in
   [the template](.forgejo/PULL_REQUEST_TEMPLATE.md).
7. Merge only after review and the forge checks pass.

**Why**: the private forge holds development, review, and day-to-day CI.
GitHub receives only release updates.

Development workflows live in `.forgejo/workflows/`. The documentation,
configuration, and site checks run on every branch push and pull request.
The external-link check runs weekly and on demand, and the
security-reference check runs monthly, on demand, and when
`reference/security/` changes, since both depend on third-party services.
Actions use the full commit SHAs in
`configs/tool-versions.json`. Forge workflows use local build output and
logs, not artifact upload or download actions.

### Checks

`make check` **MUST** pass before every commit. It runs Markdown linting,
US spelling, Crefft writing rules and package fixtures, internal links,
secret scanning, script unit tests, tool-version
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

## Maintainer Release Workflow

The maintainer's clone **MUST** have remotes named `forge` and `github`.
The private forge **MUST NOT** mirror to GitHub. Only the maintainer's machine
publishes releases to GitHub.

1. On the private forge, prepare the release on `main`: update `VERSION`,
   keep the site package version consistent, and move the unreleased
   changelog entry into a dated section for that version.
2. Run `make check`, `python3 -m unittest discover scripts`, and
   `make site-check`. Review and merge the signed release commit on the
   private forge.
3. In the maintainer's clone, sign an annotated tag named `v` plus that
   commit's `VERSION` and push that tag only to `forge`. For example,
   `git tag -s "v$(cat VERSION)" -m "crefft $(cat VERSION)"` signs the tag
   at the checked-out release commit. The tag's commit **MUST** be
   `forge/main`.
4. Run `make publish-release TAG=vYYYY.M.N`, substituting the release tag.
   It fetches both remotes without replacing local tags, compares the
   local and forge tag objects, requires an annotated tag and a successful
   `git tag -v`, reads `VERSION` from the tagged commit, and checks
   `forge/main` and fast-forward ancestry from `github/main`.
5. Review the exact push printed by the dry run. To execute it with the same
   checks, run `python3 scripts/publish_release.py --tag vYYYY.M.N --push`.
   It pushes only the verified commit to `github/main` and the named tag:
   `git push github <commit>:refs/heads/main refs/tags/<tag>`.
6. Inspect the tag-triggered GitHub Actions runs. `site.yml` builds and
   checks the site before its dependent deploy job publishes the checked
   files to Cloudflare. `release.yml` builds the Vale package and creates
   the GitHub Release with `Crefft.zip` and its checksum.

The dry run fetches and verifies; it does not push or trigger GitHub jobs.
Only the explicit push triggers deployment and release publication.
If a guard fails, resolve the mismatch on the private forge or in the local
clone. The maintainer **MUST NOT** force-push GitHub's `main` to bypass it.

**Why**: publishing one verified release keeps GitHub's source, site, and
package tied to the same signed tag without exposing development branches.

## Support

There is no public general-support channel. Security reports for the latest
release are best effort, with no service levels, promised response times, or
guaranteed fixes. Use [SECURITY.md](SECURITY.md) for private security reporting.

**Why**: crefft has one maintainer and does not provide a support service.
