# Crefft Vale Package

> [crefft](../../README.md) > [Configuration](../) > Vale

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
"SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and
"OPTIONAL" in this document are to be interpreted as described in
BCP 14 [RFC 2119](https://datatracker.ietf.org/doc/html/rfc2119)
[RFC 8174](https://datatracker.ietf.org/doc/html/rfc8174) when, and only
when, they appear in all capitals, as shown here.

`Crefft` is a config-plus-styles package for **Vale 3.24.0**. The archive
contains `Crefft/.vale.ini` beside `Crefft/styles/Crefft/`, with no vocabulary
or external style dependencies.

## Rules

House prose **MUST** use US English, state the point directly, and put
literals in code spans. All three package rules have `error` severity:

| Rule | Enforcement | Why |
| ---- | ----------- | --- |
| `Crefft.US` | The color, behavior, organization, and summarize spelling families, including the forms in [`US.yml`](Crefft/styles/Crefft/US.yml) | Keep house prose consistent without changing upstream code or names. |
| `Crefft.Direct` | Rejects a bounded set of filler phrases, including straight and curly apostrophes | State what changed instead of announcing a response or using padded descriptions. |
| `Crefft.Literals` | Requires code spans around known config file names, long flags, and selected commands, including in headings and link text | Distinguish exact input from surrounding prose. |

The package enables Vale's built-in rules with `Vale.Spelling = NO`; typos
owns general spelling. Inline code, fenced blocks, and blockquotes are
excluded from prose checks to preserve upstream literals, examples, and
quoted material. The literal rule is deliberately bounded, not a detector
for every possible file name or command.

```markdown
<!-- Don't -->
The colour changes.
I'd be happy to explain. Here's what this aims to do.
Edit .editorconfig and run vale sync --all-files.

<!-- Do -->
The color changes.
The change fixes the behavior.
Edit `.editorconfig` and run `vale sync --all-files`.
```

## Human Review

Reviewers **MUST** still check the serial comma, commas and periods inside
closing quotation marks, varied sentence rhythm, and honest claims.
Vale does not establish those properties reliably. Two-item phrases do not
take a serial comma, and punctuation around code spans stays outside them.

**Why**: the measured `Microsoft.OxfordComma` trial over 179 Markdown files
raised 21 errors, only about two of them real. That false-positive rate makes
it unsuitable as a gate. No Microsoft package is installed or required.
A regular expression also cannot establish whether a claim is true or
whether a paragraph's rhythm is repetitive.

```text
Don't: We ship apples, pears and plums. The output is "ready".
Do:    We ship apples, pears, and plums. The output is "ready."

Don't: All checks pass. [No execution evidence.]
Do:    Security check not run.
```

## Consumer Setup

Consumers **MUST** pin Vale to `3.24.0` and the package to a crefft release
URL, not an unversioned package name. Install the matching Vale archive from
the [v3.24.0 release][vale-release] and verify its SHA-256 against
[`configs/tool-versions.json`](../tool-versions.json).
The first package release URL is:

```text
https://github.com/agh/crefft/releases/download/v2026.10.3/Crefft.zip
```

Create this minimal `.vale.ini`:

```ini
StylesPath = styles
MinAlertLevel = warning
Packages = https://github.com/agh/crefft/releases/download/v2026.10.3/Crefft.zip
```

Bootstrap the repository, and repeat sync in CI before linting:

```bash
vale --no-global sync
vale --no-global README.md
```

Every Vale invocation **MUST** use `--no-global`. Keep only the downloaded
`styles/Crefft/` and `styles/.vale-config/` directories in `.gitignore`;
repository-owned vocabulary files **MUST** remain tracked.

**Why**: the package's configuration enables the rules without duplicating
them locally. Sync installs that configuration as well as its styles.
Disabling global configuration prevents workstation settings from changing
the gate. Downloaded styles are disposable, but local terminology is source.

### Pre-commit and prek

The following `.pre-commit-config.yaml` works with pre-commit and prek.
It uses Vale's own `language: golang` hook at `v3.24.0`, not a separate hook
wrapper. Consumers **MUST** run `vale --no-global sync` during bootstrap and
before hooks run in CI; the hook does not sync packages.

```yaml
repos:
  - repo: https://github.com/vale-cli/vale
    rev: v3.24.0
    hooks:
      - id: vale
        args: [--no-global]
        types: [markdown]
```

**Why**: the pinned hook builds the selected Vale release, while explicit
sync makes package installation visible rather than a side effect of linting.
Vale also ships `vale-commit-msg`, but this package configures Markdown only;
commit-message policy needs a consumer-owned configuration section.

### CI

This Linux x86-64 example installs the checksum-pinned binary and checks all
tracked Markdown. Consumers **MUST** document a reason beside each exclusion
they add; this example excludes none.

```yaml
name: Prose
on: [push, pull_request]
permissions:
  contents: read
jobs:
  prose:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - name: Install Vale 3.24.0
        shell: bash
        run: |
          set -euo pipefail
          archive=vale_3.24.0_Linux_64-bit.tar.gz
          curl --fail-with-body --location --silent --show-error --retry 3 \
            --output "$RUNNER_TEMP/$archive" \
            "https://github.com/vale-cli/vale/releases/download/v3.24.0/$archive"
          echo "867534ddb678abca7f214bc4706ead0922bd5252ffe8035fc227013f66c8b214  $RUNNER_TEMP/$archive" \
            | sha256sum --check --strict
          mkdir -p "$RUNNER_TEMP/vale"
          tar -xzf "$RUNNER_TEMP/$archive" -C "$RUNNER_TEMP/vale"
          echo "$RUNNER_TEMP/vale" >> "$GITHUB_PATH"
      - name: Sync and lint
        run: |
          vale --no-global sync
          git ls-files -z '*.md' | xargs -0 vale --no-global
```

**Why**: CI uses the same executable and package as local checks, and verifies
the downloaded executable before running it. Sync downloads rules; linting
is local and does not upload prose.

## Repository Vocabulary

The package **MUST NOT** ship a vocabulary. A consuming repository **MAY**
add `Vocab = Repository` above any syntax sections in its own `.vale.ini`
and track `styles/config/vocabularies/Repository/accept.txt` and
`reject.txt`. Use repository-specific terms, not a shared list of project names.

With `Vale.Spelling = NO`, an accept list only feeds `Vale.Terms`, which
enforces **exact case**. It does not whitelist words for a disabled spell
checker. A reject list feeds `Vale.Avoid`.

**Why**: names and capitalization belong to the consuming repository. Sharing
an accept list would impose another repository's terminology and hide what
the spelling switch actually does.

```text
# Don't: treat accept.txt as a general spelling bypass.
# Do: record the exact capitalization the repository requires.
PostgreSQL
```

## Package Development and Releases

The package version **MUST** be the crefft release version; there is no
independent package version. Release `v2026.10.3` is the first planned asset.
The release workflow requires a tag matching `VERSION` and a nonempty
versioned section in `CHANGELOG.md`.

**Why**: a single release identifies the rules, configuration, and guides
reviewed together. A pinned URL changes only when a consumer chooses an
upgrade.

From the crefft root:

```bash
make vale
make vale-package
```

`make vale` installs Vale `3.24.0` with per-platform checksum verification,
syncs the local package directory, runs rule fixtures with coverage, lints
every tracked Markdown file outside the verbatim `reference/` tree, and
tests the built archive in a temporary consumer. Probe and clean fixtures use
`.txt` source files so intentional violations are not ordinary Markdown lint
inputs; the consumer copies them to Markdown before checking them.

`scripts/build_vale_package.py` writes `.tmp-check/vale-package/Crefft.zip`
and `Crefft.zip.sha256` through `make vale-package`. Entries are sorted, with
fixed timestamps and permissions, and only `Crefft/` as the root.
The release workflow uploads the tested bytes and extracted notes from a
read-only job; a separate job can publish them but cannot check out or build
source.

## See Also

- [Contributing house rules](../../CONTRIBUTING.md#house-rules)
- [Pinned tool versions](../tool-versions.json)
- [Vale packages](https://docs.vale.sh/keys/packages)
- [Vale rule testing](https://docs.vale.sh/topics/testing)

[vale-release]: https://github.com/vale-cli/vale/releases/tag/v3.24.0
