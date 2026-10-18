# GitHub Workflow Templates

> [crefft](../../README.md) > Configs > GitHub

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
"SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this
document are to be interpreted as described in [RFC 2119](https://datatracker.ietf.org/doc/html/rfc2119).

Reusable GitHub Actions workflows for projects that adopt crefft. These are
**templates**: they live here rather than in `.github/workflows/` so GitHub
cannot schedule them inside crefft itself.

## Quick Reference

| Template | Purpose | Trigger | Needs |
| -------- | ------- | ------- | ----- |
| [`workflows/sync-crefft.yml`][sync] | Agents, commands, and config | Weekly, manual | [^scopes] |
| [`workflows/doc-sync.yml`](workflows/doc-sync.yml) | Remind pull-request authors which documents a source change touches | Pull requests touching `src/`, `lib/`, `app/` | `pull-requests: write` |

[sync]: workflows/sync-crefft.yml

[^scopes]: Requires `contents: write` and `pull-requests: write` to propose
    updates to crefft-owned Claude configuration files in your project.

## Why these are templates, not live workflows

A workflow placed in `.github/workflows/` runs in the repository that holds
it. `sync-crefft.yml` previously sat in crefft's own workflow directory
and therefore ran against crefft every Monday, copying `configs/claude/*`
into a second `.claude/` tree and attempting a self-referential pull request.
`doc-sync.yml` triggers on `src/**`, `lib/**`, and `app/**`, none of which
exist in a documentation repository.

Templates **MUST NOT** be placed in `.github/workflows/` of the repository
that publishes them. Copy them into the consuming project instead.

## Adopting `sync-crefft.yml`

Keeps a downstream project's `.claude/` tree in step with crefft.

### Install

```bash
mkdir -p .github/workflows
curl -fsSL -o .github/workflows/sync-crefft.yml \
  https://raw.githubusercontent.com/agh/crefft/v2026.10.1/configs/github/workflows/sync-crefft.yml
```

### Configure

Set `CREFFT_REF` to the release tag you have reviewed. It **MUST NOT** be a
branch such as `main`. The default is `v2026.10.1`. Optionally set
`CREFFT_COMMIT` to the independently reviewed full commit SHA:

```yaml
env:
  CREFFT_REPO: agh/crefft
  CREFFT_REF: v2026.10.1
  CREFFT_COMMIT: ''
```

The template checks out that release into `.crefft-upstream/` and invokes
`.crefft-upstream/scripts/sync-claude-config.sh --ref "${CREFFT_REF}"`, adding
`--commit` when `CREFFT_COMMIT` is set. There is no separate copying logic
or configurable `SYNC_PATHS` mapping. The runner needs Bash, Git, and Python 3.

The applier verifies the checkout against the release tag and optional
commit SHA before writing. It installs these fixed mappings:

| Source in crefft | Destination in the project |
| ---------------- | -------------------------- |
| `agents/` | `.claude/agents/` |
| `commands/` | `.claude/commands/` |
| `configs/claude/skills/` | `.claude/skills/` |
| `configs/claude/infrastructure/` | `.claude/infrastructure/` |
| `configs/claude/settings.json` | `.claude/settings.json` |

Every source component is required; a missing source fails before any write.
Existing settings are preserved. Replacing them requires an explicit
`--overwrite-settings` argument to the script; the template does not pass it.

#### Why

One applier keeps automated and manual installs consistent. A release pin
prevents weekly jobs from following an unreviewed branch, and an independent
commit pin detects a moved tag.

### Ownership and adoption

Consumers **MUST** retain and commit `.claude/crefft-receipt.json` with the
installed files. It records the release, resolved commit, and SHA-256 of each
installed file. Only previously recorded files can be replaced or removed.
Project-specific files beside them survive.

An unowned conflicting path stops the entire sync with a list of conflicts
and no writes. For an earlier installation without a receipt, consumers
**MAY** run the pinned script manually with `--adopt` to claim identical
files. Adoption compares contents only; differing files still conflict.
Locally modified owned files and symlinks also block the sync. Review
conflicts rather than deleting project additions to make a run pass.

**Do:** use the pinned script for adoption and keep its receipt.
**Don't:** mirror a whole directory or move project-specific agents into a
user's home directory merely to protect them from sync.

See [manual sync](../../guides/ai/claude-code.md#manual-sync) for the same
applier outside GitHub Actions.

#### Why

File-level ownership makes upstream deletion safe without granting crefft
ownership of the project's entire `.claude/` tree. Preserving settings
protects project-specific permissions and hooks.

### Repository settings

The workflow opens a pull request, so the project **MUST** enable
**Settings → Actions → General → Allow GitHub Actions to create and approve
pull requests**. Without it `peter-evans/create-pull-request` fails with a
permissions error — this is what caused all fourteen historical failures of
this workflow in crefft.

Pull requests authored with the default `GITHUB_TOKEN` deliberately do not
trigger further workflow runs. If the sync pull request must run your CI, set
a `CREFFT_SYNC_TOKEN` secret holding a fine-grained personal access token
with `contents: write` and `pull-requests: write` on the project; the
template prefers it when present.

### Dry runs

Run the workflow manually with **Preview changes without creating a pull
request** ticked. The dry run reports `git status --porcelain` to the job
summary after running the applier in a temporary project clone. It neither
changes the project's `.claude/` tree nor opens a pull request; there is no
workspace-wide restore or clean step. `dry_run` is a Boolean input, so the
conditions compare `inputs.dry_run == true`.

The workflow validates `VERSION` as one calendar version before exporting it.
Preview outputs enter the shell through `env:` and are printed with
`printf '%s\n'`, never interpolated into shell source.

#### Why

A preview needs the same ownership checks as an install, without applying
changes to the working project. Treating version and report values as data
prevents filenames or upstream text from becoming shell commands.

## Adopting `doc-sync.yml`

Posts one comment per pull request listing the documents that correspond to
the changed source files.

### Install

```bash
mkdir -p .github/workflows
curl -fsSL -o .github/workflows/doc-sync.yml \
  https://raw.githubusercontent.com/agh/crefft/main/configs/github/workflows/doc-sync.yml
```

### Configure

Set `DOC_ROOT` to the directory holding your prose documentation, and adjust
the `paths` filter to match your source layout. The mapping strips any
extension, so `lib/parser.py` maps to `docs/lib/parser.md`; the original
template assumed TypeScript and produced `docs/lib/parser.py.md`.

### Scope

This check is advisory. It **MUST NOT** be treated as proof that
documentation is current — it only reports which documents exist for the
files that changed. It never fails the build.

## Pinning policy

Every `uses:` reference in these templates is pinned to a full commit SHA
with the release tag in a trailing comment, per
[GitHub's secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use-reference).
A tag is a mutable pointer; `tj-actions/changed-files` had its tags
retargeted during the March 2025 supply-chain incident, which a SHA pin would
have contained.

crefft's Dependabot configuration only scans `.github/workflows/`. These
templates are **not** updated automatically: when the pins in
`.github/workflows/` change, update them here in the same commit.

Current pins:

| Action | Version | SHA |
| ------ | ------- | --- |
| `actions/checkout` | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `actions/github-script` | v9.0.0 | `3a2844b7e9c422d3c10d287c895573f7108da1b3` |
| `peter-evans/create-pull-request` | v8.1.1 | `5f6978faf089d4d20b00c7766989d076bb2fc7f1` |
| `tj-actions/changed-files` | v47.0.6 | `9426d40962ed5378910ee2e21d5f8c6fcbf2dd96` |

## See Also

- [CI/CD Style Guide](../../guides/process/ci.md)
- [GitHub Templates](../../guides/process/github-templates.md)
- [Claude Code Guide](../../guides/ai/claude-code.md)
