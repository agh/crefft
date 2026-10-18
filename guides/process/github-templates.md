# GitHub Templates Guide

> [crefft](../../README.md) > [Process](../README.md) > GitHub Templates

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
"SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and
"OPTIONAL" in this document are to be interpreted as described in
BCP 14 [RFC 2119](https://datatracker.ietf.org/doc/html/rfc2119)
[RFC 8174](https://datatracker.ietf.org/doc/html/rfc8174) when, and only
when, they appear in all capitals, as shown here.

Standardized templates for all @agh projects.

## Directory Structure

```text
.github/
├── ISSUE_TEMPLATE/
│   ├── bug_report.yml
│   ├── feature_request.yml
│   └── config.yml
├── PULL_REQUEST_TEMPLATE.md
├── CODEOWNERS
├── FUNDING.yml (optional)
└── workflows/
    └── ci.yml
CONTRIBUTING.md
SECURITY.md
LICENSE
```

## CONTRIBUTING.md

Projects **SHOULD** include a `CONTRIBUTING.md` file. It **MUST** state which
contribution channels the maintainer accepts and what happens to submissions
outside that policy. The example below uses crefft's issues-only policy;
projects accepting external pull requests **MUST** adapt the channel and
workflow text to their own policy.

Contribution and security templates **MUST NOT** promise response or
resolution schedules or offer bounties.

### Why

An explicit channel prevents contributors from preparing changes the
maintainer will not accept. Unfunded response, fix, and payment promises
create obligations a template cannot fulfill.

````markdown
# Contributing to [Project Name]

Contribute by opening an issue using the repository's issue forms.
The maintainer makes changes; external pull requests are closed with a
pointer to those forms. Dependabot pull requests continue.

**Why**: issues let the maintainer verify the evidence and scope before
implementing a consistent change.

## Code of Conduct

This project follows the [Contributor Covenant](https://www.contributor-covenant.org/).
Be respectful and constructive.

## Proposing a Change

1. Search existing issues to avoid duplicates.
2. Choose the issue form for a bug, version update, or new proposal.
3. Identify the latest release and affected files or sections.
4. Include reproduction steps, expected and actual behavior, and evidence.
5. Cite primary sources and the date checked for time-sensitive claims.

Support is best effort, for the latest release only, with no service levels,
promised response times, or guaranteed fixes.

**Why**: a single-maintainer project does not provide a support service.

For security problems, use GitHub's private vulnerability reporting as
described in `SECURITY.md`, not a public issue. Vulnerabilities in other
projects go through those projects' own security policies.

**Why**: public reports can expose users before a fix is available.

## Maintainer Development Workflow

The house style, tests, and checks still apply to the maintainer's changes.

**Why**: restricting contribution channels does not lower release standards.

### Making Changes

1. Create a feature branch:

   ```bash
   git checkout -b feature/your-feature-name
   ```

1. Make your changes following our style guide

1. Write or update tests

1. Run the test suite:

   ```bash
   # Language-specific command
   ```

1. Run linting:

   ```bash
   # Language-specific command
   ```

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```text
type(scope): description

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Examples:

- `feat(auth): add OAuth2 support`
- `fix(api): handle null response from server`
- `docs: update installation instructions`

### Maintainer Pull Requests

1. Open the maintainer's pull request against `main`.
2. Fill out the pull request template completely.
3. Confirm the required checks pass and address review findings.

## Reporting Issues

### Bug Reports

Use the bug report template. Include:

- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, version, etc.)
- Logs or error messages

### Feature Requests

Use the feature request template. Include:

- Problem you're trying to solve
- Proposed solution
- Alternatives you've considered

## Questions?

- Check existing documentation
- Search closed issues
- Open a discussion (if enabled) or issue

````

## SECURITY.md

Projects **MUST** include a `SECURITY.md` file with vulnerability reporting
procedures. GitHub's private vulnerability reporting **SHOULD** be the
default channel and **MUST** be enabled before the policy points reporters
to it. Replace `OWNER/REPO` below with the repository's actual path.

The policy **MUST** state the supported release scope, best-effort handling,
the absence of service levels and bounties, and publication of an advisory
after a fix. It **MUST** route vulnerabilities in other projects through
those projects' own policies, not public issues in this repository.

### Why

Private reporting keeps exploit details out of public issues while a fix
is prepared. A clear release scope and best-effort policy avoid response,
resolution, and payment promises the maintainer cannot guarantee.

```markdown
# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| Latest release | Best effort |
| Older releases and unreleased revisions | No |

Only the latest release is supported; older releases are not patched.

**Why**: maintenance effort stays on the release users are directed to use.

## Reporting a Vulnerability

Security vulnerabilities **MUST NOT** be reported through public issues.

Report privately at:
<https://github.com/OWNER/REPO/security/advisories/new>.
Do not open a public placeholder issue.

**Why**: the private advisory thread protects users before a fix.

Vulnerabilities in someone else's project **MUST** go through that project's
own security policy, never a public issue here.

**Why**: that project's maintainers control the fix and disclosure.

Include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### What to Expect

Replies and fixes are best effort. There is no promised response time, fix
date, or service level, and no bounty or other payment.

Progress is discussed in the private advisory thread. After a fix is
released, a security advisory is published with impact and remediation.

**Why**: an advisory informs users without promising an unsupported schedule.

### Disclosure Policy

Reporters **SHOULD** coordinate disclosure in the private thread until the
fix and advisory are published. Reporters are credited unless they request
anonymity. No legal action will be taken against good-faith reporters.

**Why**: coordinated disclosure protects users while a fix is prepared.

## Security Best Practices

When contributing:
- Never commit secrets, tokens, or credentials
- Use environment variables for configuration
- Follow OWASP guidelines
- Report suspicious behavior
```

## CODEOWNERS

Projects **SHOULD** define code ownership using a CODEOWNERS[^1] file for automated review assignment.

```text
# Default owners for everything
*       @org/maintainers

# Specific paths
/docs/                    @org/docs-team
/.github/                 @org/devops
/src/api/                 @org/api-team
/src/frontend/            @org/frontend-team

# Specific files
/SECURITY.md              @org/security
```

## Issue Templates

All @agh projects **SHOULD** use structured issue templates[^2] to ensure
consistent bug reports and feature requests.

### .github/ISSUE_TEMPLATE/config.yml[^10]

```yaml
blank_issues_enabled: false
contact_links:
  - name: Documentation
    url: https://docs.example.com
    about: Check our documentation first
  - name: Discussions
    url: https://github.com/org/repo/discussions
    about: Ask questions here
```

### .github/ISSUE_TEMPLATE/bug_report.yml

```yaml
name: Bug Report
description: Report a bug
labels: ["bug", "triage"]
body:
  - type: markdown
    attributes:
      value: |
        Thanks for reporting! Please fill out the form below.

  - type: textarea
    id: description
    attributes:
      label: Description
      description: Clear description of the bug
    validations:
      required: true

  - type: textarea
    id: reproduction
    attributes:
      label: Steps to Reproduce
      description: Steps to reproduce the behavior
      placeholder: |
        1. Go to '...'
        2. Click on '...'
        3. See error
    validations:
      required: true

  - type: textarea
    id: expected
    attributes:
      label: Expected Behavior
      description: What did you expect to happen?
    validations:
      required: true

  - type: textarea
    id: actual
    attributes:
      label: Actual Behavior
      description: What actually happened?
    validations:
      required: true

  - type: input
    id: version
    attributes:
      label: Version
      description: What version are you using?
    validations:
      required: true

  - type: dropdown
    id: os
    attributes:
      label: Operating System
      options:
        - Linux
        - macOS
        - Windows
        - Other
    validations:
      required: true

  - type: textarea
    id: logs
    attributes:
      label: Relevant Logs
      description: Paste any relevant logs
      render: shell
```

### .github/ISSUE_TEMPLATE/feature_request.yml

```yaml
name: Feature Request
description: Suggest a new feature
labels: ["enhancement"]
body:
  - type: textarea
    id: problem
    attributes:
      label: Problem Statement
      description: What problem does this solve?
    validations:
      required: true

  - type: textarea
    id: solution
    attributes:
      label: Proposed Solution
      description: How should it work?
    validations:
      required: true

  - type: textarea
    id: alternatives
    attributes:
      label: Alternatives Considered
      description: What other solutions have you considered?

  - type: textarea
    id: context
    attributes:
      label: Additional Context
      description: Any other context or screenshots
```

## Pull Request Template

All @agh projects **MUST** include a pull request template[^3] to ensure comprehensive change documentation.

For an issues-only project such as crefft, the template **MUST** open with
the external-pull-request closure policy and a link to its issue forms.
Keep the checklist for the maintainer's own pull requests.

### Why

The note explains closure before a contributor submits a pull request;
the checklist still records the maintainer's required review and checks.

### .github/PULL_REQUEST_TEMPLATE.md

```markdown
External pull requests are closed in favor of
[issue forms](https://github.com/OWNER/REPO/issues/new/choose).
The maintainer makes changes so the evidence and scope are settled first.
Dependabot pull requests continue. This checklist is for maintainer pull requests.

## Summary

Brief description of changes.

## Related Issues

Fixes #(issue number)

## Type of Change

- [ ] Bug fix (non-breaking change fixing an issue)
- [ ] New feature (non-breaking change adding functionality)
- [ ] Breaking change (fix or feature causing existing functionality to change)
- [ ] Documentation update
- [ ] Refactoring (no functional changes)

## Changes Made

- Change 1
- Change 2

## Testing

- [ ] Tests pass locally
- [ ] New tests added for new functionality
- [ ] Existing tests updated as needed

## Checklist

- [ ] Code follows the project's style guide
- [ ] Self-review completed
- [ ] Documentation updated (if applicable)
- [ ] No new warnings introduced
- [ ] Breaking changes documented

## Screenshots (if applicable)

## Additional Notes

Any additional context for reviewers.
```

## Git Configuration Files

### .gitignore

All projects **MUST** include a .gitignore file. You **SHOULD** create
language-specific ignores. Use [gitignore.io](https://gitignore.io)[^4]
as a starting point.

### .gitattributes

All projects **SHOULD** include a .gitattributes file[^5] to ensure consistent
line endings and file handling across platforms.

```gitattributes
# Auto detect text files and normalize line endings
* text=auto eol=lf

# Force specific file types
*.sh text eol=lf
*.py text eol=lf
*.rb text eol=lf
*.go text eol=lf
*.rs text eol=lf

# Binary files
*.png binary
*.jpg binary
*.gif binary
*.ico binary
*.pdf binary
*.zip binary

# Lock files - exact format matters
*.lock linguist-generated
package-lock.json linguist-generated
yarn.lock linguist-generated
Gemfile.lock linguist-generated
poetry.lock linguist-generated
uv.lock linguist-generated
Cargo.lock linguist-generated

# Vendored files
vendor/* linguist-vendored
node_modules/* linguist-vendored
```

### .dockerignore

Projects using Docker **SHOULD** include a .dockerignore file[^6] to reduce
build context size and improve build performance.

```dockerignore
# Git
.git
.gitignore

# CI/CD
.github
.gitlab-ci.yml

# IDE
.idea
.vscode
*.swp
*.swo

# Documentation
*.md
docs/
LICENSE

# Tests
tests/
test/
*_test.go
*.test.js

# Development
.env
.env.*
*.local

# Build artifacts (language-specific)
__pycache__/
*.pyc
node_modules/
target/
dist/
build/
```

## References

[^1]: [CODEOWNERS - GitHub Documentation](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
[^2]: [Issue Templates - GitHub Documentation](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/configuring-issue-templates-for-your-repository)
[^3]: [Pull Request Templates - GitHub Documentation](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/creating-a-pull-request-template-for-your-repository)
[^4]: [gitignore.io](https://gitignore.io) - Generate .gitignore files for your project
[^5]: [.gitattributes - Git Documentation](https://git-scm.com/docs/gitattributes)
[^6]: [.dockerignore - Docker Documentation](https://docs.docker.com/build/building/context/#dockerignore-files)
[^10]: [Issue Template Configuration - GitHub Documentation](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms)

## See Also

- [CI/CD Guide](ci.md) - CI workflow configuration and automation
- [Versioning Guide](versioning.md) - Library SemVer, CalVer, and changelog management
- [Testing Guide](testing.md) - Testing strategy and best practices
