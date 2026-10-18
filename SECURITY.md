# Security Policy

> [crefft](README.md) > Security Policy

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
"SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and
"OPTIONAL" in this document are to be interpreted as described in
BCP 14 [RFC 2119](https://datatracker.ietf.org/doc/html/rfc2119)
[RFC 8174](https://datatracker.ietf.org/doc/html/rfc8174) when, and only
when, they appear in all capitals, as shown here.

## What This Policy Covers

crefft is documentation. It ships no service, no library, and no binary, so
there is nothing here to compromise at runtime. The security surface is the
material crefft tells people to copy into their own projects:

- configuration files under `configs/`
- GitHub Actions workflows under `.github/workflows/`
- agent definitions under `agents/` and `commands/`
- shell commands, install instructions, and pinned versions inside the guides
- the vendored security reference data under `reference/security/`

A dangerous default, an insecure command, a workflow that leaks a token, a
compromised or typo-squatted package name, or a pinned action pointing at a
malicious revision are all in scope. So is security advice in a guide that is
wrong in a way that would make a reader's system less safe.

Vulnerabilities in someone else's project, including upstream tools crefft
recommends, **MUST** go through that project's own security policy, never a
public issue here.

**Why**: that project's maintainers control the fix and its disclosure.

## Supported Versions

| Version | Supported |
| ------- | --------- |
| Latest release | Best effort |
| Older releases and unreleased revisions | No |

Only the [latest release](https://github.com/agh/crefft/releases/latest) is
supported. Check the problem against that release before reporting.
Fixes are developed on `main` and published in a release; older releases
are not patched.

**Why**: a single supported release keeps limited maintenance effort on the
material readers are directed to use.

## Reporting a Vulnerability

Security vulnerabilities **MUST NOT** be reported in public issues.

Report privately through GitHub:

1. Go to <https://github.com/agh/crefft/security/advisories/new>.
2. Describe the problem, where it is (file and line), and what an attacker
   could do with it.
3. Include the steps you took to confirm it.

GitHub's private vulnerability reporting is enabled for crefft. Use that
channel rather than opening a public issue, including a placeholder issue.

**Why**: the private advisory thread lets the reporter and maintainer discuss
the vulnerability without exposing readers before a fix.

## What to Expect

Replies and fixes are best effort. There is no promised response time, fix
date, or service level, and no bounty or other payment.

Progress is discussed in the private advisory thread. After a fix is
released, crefft publishes a security advisory describing the impact and
remediation. Reporters are credited in the advisory and changelog unless
they ask not to be.

Reporters **SHOULD** coordinate disclosure in that thread until the fix and
advisory are published.

**Why**: coordinated disclosure protects readers while the fix is prepared;
a single-maintainer project cannot promise a response or resolution schedule.

No legal action will be taken against anyone reporting in good faith.

## Using crefft Safely

- **MUST** review any configuration, workflow, or command before copying it
  into a project. crefft's material is a starting point, not an audited
  artifact.
- **MUST** re-pin GitHub Actions to a commit SHA you have verified yourself
  rather than trusting a tag.
- **MUST NOT** treat `reference/security/` as live threat intelligence. It is
  a periodically refreshed snapshot; check `reference/security/manifest.json`
  for `last_updated` and `next_review` before relying on it.
- **MUST NOT** commit secrets, tokens, or credentials to this repository. Some
  guides contain deliberate "never do this" examples that look like
  credentials; they are illustrative and contain no real values.

## See Also

- [CONTRIBUTING.md](CONTRIBUTING.md) — how to propose changes
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — community expectations
- [guides/ai/security.md](guides/ai/security.md) — LLM security considerations
