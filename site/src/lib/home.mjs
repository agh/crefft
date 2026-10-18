import { readFileSync } from 'node:fs';
import path from 'node:path';
import { repository, version } from './paths.mjs';

export const definition = 'crefft is an engineering standard for people and coding agents, with explicit rules, their reasons, and the tool versions they apply to.';
export const strapline = 'Engineering practice, pinned.';
export const proofSource = 'guides/languages/python.md';
export const proofURL = '/guides/languages/python/#pre-commit-configuration';
export const specimenURL = '/rules/python-pre-commit/';
export const proofTitle = 'Pin a compatible hook revision';
const source = readFileSync(path.join(repository, proofSource), 'utf8');
export const rule = source.match(/^## Pre-commit Configuration\n\n([\s\S]+?)(?=\n### )/m)?.[1].trim();
if (!rule) throw new Error('Python pre-commit rule boundary is missing');
export const requirement = rule.split('\n\n')[0];
export const reason = rule.split('\n\n')[1];
export const configuration = rule.match(/```yaml\n([\s\S]+?)\n```/)?.[1];
export const good = configuration?.match(/  - repo: https:\/\/github.com\/astral-sh\/ruff-pre-commit\n([\s\S]+?)(?=\n\n)/)?.[1]
  .split('\n').map((line) => line.slice(4)).join('\n');
export const pin = good?.match(/^rev: (.+)/)?.[1];
if (!configuration || !good || !pin) throw new Error('Python hook configuration is missing');
export const bad = 'rev: v0.8.0\nhooks:\n  - id: ruff';
export const proofContext = {
  guide: 'Python',
  section: 'Pre-commit Configuration',
  url: proofURL,
  pins: [`ruff-pre-commit ${pin}`],
};
export const traceMarkdown = `## Trace this rule

1. **Obligation.** The tag must exist and the hook must parse the target. Both conditions apply.
2. **Examples.** The full configuration is quoted from the guide. The bad example illustrates
   the incompatible Ruff revision described in its rationale; it is not an executed fixture.
3. **Checker.** Review required. This site build does not run a compatibility or tag-existence check.
4. **Context.** Read the [complete Python guide](${proofURL}) for configuration and migration notes.
   No rule identifier or per-rule review date is assigned.
`;
export const specimenMarkdown = `# ${proofTitle}

Identity: Python / Pre-commit Configuration. Identifier not yet assigned.
Recorded Ruff pin: ${pin}. Source version: ${version}.

Quoted from [Python: Pre-commit Configuration](${proofURL}).

${rule}

## Don't: illustrative counterexample

\`\`\`yaml
${bad}
\`\`\`

Both Ruff examples use \`https://github.com/astral-sh/ruff-pre-commit\`.

${traceMarkdown}`;
export const homeMarkdown = `# ${strapline}

${definition}

[Browse guides](/guides.md) | [For agents](/for-agents.md)

## Pin a compatible hook revision

Quoted from [Python: Pre-commit Configuration](/guides/languages/python.md#pre-commit-configuration).
Source version: ${version}. A recorded pin is not a new compatibility check.

${rule}

### Don't: illustrative counterexample

This shortened example uses the incompatible Ruff revision described in the guide.
Both Ruff examples use \`https://github.com/astral-sh/ruff-pre-commit\`.

\`\`\`yaml
${bad}
\`\`\`

Identifier not yet assigned. No per-rule review date is recorded.

[Read the rule specimen](${specimenURL.slice(0, -1)}.md).
`;
