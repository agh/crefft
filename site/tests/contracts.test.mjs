import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import test from 'node:test';
import { createMarkdownProcessor } from '@astrojs/markdown-remark';
import { routeFor, markdownFor, repository, resolveSourceLink } from '../src/lib/paths.mjs';
import { guideNodes } from '../src/lib/navigation.mjs';
import { sourceLinks, readingTwin, rehypePlugins } from '../src/lib/markdown.mjs';
import { rule, requirement, reason, configuration, good, pin } from '../src/lib/home.mjs';
import { fileManifest } from '../src/lib/downloads.mjs';

test('Rust core and topic index never share HTML or Markdown routes', () => {
  const core = routeFor('guides/languages/rust.md');
  const topics = routeFor('guides/languages/rust/README.md');
  assert.equal(core, '/guides/languages/rust/');
  assert.equal(topics, '/guides/languages/rust/topics/');
  assert.notEqual(markdownFor(core), markdownFor(topics));
});

test('source links retain query strings, fragments, and reference definitions', async () => {
  const source = path.join(repository, 'guides/languages/README.md');
  const tree = { children: [
    { type: 'link', url: './rust/README.md#topic' },
    { type: 'definition', url: './python.md?mode=plain#pre-commit-configuration' },
  ] };
  sourceLinks()(tree, { path: source });
  assert.equal(tree.children[0].url, '/guides/languages/rust/topics/#topic');
  assert.equal(tree.children[1].url, '/guides/languages/python/?mode=plain#pre-commit-configuration');
  const twin = await readingTwin('[Python][p]\n\n[p]: python.md#pre-commit-configuration\n', source);
  assert.match(twin, /\/guides\/languages\/python.md#pre-commit-configuration/);
});

test('unsafe schemes, active HTML, and repository traversal fail closed', () => {
  const source = path.join(repository, 'guides/languages/python.md');
  for (const url of ['javascript:alert(1)', 'data:text/html,hello', '//example.com/x', '../../../../secret.md']) {
    assert.throws(() => resolveSourceLink(url, source));
  }
  for (const value of ['<script>alert(1)</script>', '<div onclick="alert(1)">', '<style>body{}</style>']) {
    assert.throws(() => sourceLinks()({ type: 'html', value }, { path: source }));
  }
});

test('remote Markdown images become outbound links, never runtime resources', () => {
  const image = { type: 'image', url: 'https://example.com/badge.svg', alt: 'Build status' };
  sourceLinks()(image, { path: path.join(repository, 'guides/README.md') });
  assert.equal(image.type, 'link');
  assert.deepEqual(image.children, [{ type: 'text', value: 'Build status' }]);
});

test('known source-link repairs affect HTML and twins, and directory links stay navigable', () => {
  const docker = path.join(repository, 'agents/system/docker.md');
  const original = 'docker.md#secrets-vs-environment-variables';
  assert.equal(resolveSourceLink(original, docker), '/guides/infrastructure/docker/#secrets-vs-environment-variables');
  assert.equal(resolveSourceLink(original, docker, true), '/guides/infrastructure/docker.md#secrets-vs-environment-variables');
  assert.match(resolveSourceLink('../security', docker), /\/tree\/[a-f0-9]{40}\/agents\/security$/);
  assert.match(
    resolveSourceLink('../../AGENTS.md#agency-and-sessions', docker),
    /\/blob\/[a-f0-9]{40}\/AGENTS\.md#agency-and-sessions$/,
  );
});

test('reading twins preserve harness frontmatter and code bytes', async () => {
  const source = path.join(repository, 'agents/code/reviewer.md');
  const body = await readFile(source, 'utf8');
  const twin = await readingTwin(body, source);
  assert.equal(twin.match(/^---\n[\s\S]+?\n---\n/)[0], body.match(/^---\n[\s\S]+?\n---\n/)[0]);
  const blocks = (text) => [...text.matchAll(/```[^\n]*\n([\s\S]*?)\n```/g)].map((match) => match[1]);
  assert.deepEqual(blocks(twin), blocks(body));
});

test('font subsets and masters match the recorded digest manifest', async () => {
  const records = JSON.parse(await readFile('public/fonts/manifest.json', 'utf8'));
  assert.equal(records.length, 4);
  for (const record of records) {
    const master = await readFile(`assets/fonts/${record.source}`);
    const subset = await readFile(`public/fonts/${record.file}`);
    assert.equal(record.sourceSha256, createHash('sha256').update(master).digest('hex'));
    assert.equal(record.sha256, createHash('sha256').update(subset).digest('hex'));
    assert.equal(record.bytes, subset.length);
  }
});

test('the complete proof requirement, rationale, and configuration come from Python', async () => {
  const python = await readFile('../guides/languages/python.md', 'utf8');
  assert.ok(python.includes(rule));
  assert.ok(rule.includes(requirement) && rule.includes(reason) && rule.includes(configuration));
  assert.match(good, /ruff-check/);
  assert.ok(configuration.includes(pin));
  assert.equal((requirement.match(/\*\*MUST\*\*/g) ?? []).length, 2);
});

test('SUMMARY navigation covers every guide except the root index', async () => {
  async function walk(directory) {
    const results = [];
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const filename = path.join(directory, entry.name);
      if (entry.isDirectory()) results.push(...await walk(filename));
      else if (filename.endsWith('.md')) results.push(path.relative(repository, filename));
    }
    return results;
  }
  assert.deepEqual(
    (await walk(path.join(repository, 'guides'))).filter((file) => file !== 'guides/README.md').sort(),
    guideNodes.map((node) => node.source).sort(),
  );
});

test('raw manifest covers dotfiles and records real bytes', async () => {
  const manifest = await fileManifest();
  assert.ok(manifest.files.some((file) => file.path === 'configs/pre-commit/.pre-commit-config.yaml'));
  for (const file of manifest.files) {
    const bytes = await readFile(path.join(repository, file.path));
    assert.equal(file.size, bytes.length);
    assert.equal(file.sha256, createHash('sha256').update(bytes).digest('hex'));
  }
});

test('source-rendered blocks remain keyboard accessible and plain code stays literal', async () => {
  const processor = await createMarkdownProcessor({ syntaxHighlight: false, remarkPlugins: [], rehypePlugins });
  const result = await processor.render('```html\n<script>example()</script>\n```\n\n| A | B |\n| - | - |\n| c | d |\n');
  assert.match(result.code, /tabindex="0"/);
  assert.match(result.code, /(?:&lt;|&#x3C;)script/);
  assert.doesNotMatch(result.code, /<script>/);
});

test('dependencies are exact and agree with the repository version register', async () => {
  const pkg = JSON.parse(await readFile('package.json', 'utf8'));
  const canonical = JSON.parse(await readFile('../configs/tool-versions.json', 'utf8'));
  for (const [name, version] of Object.entries({ ...pkg.dependencies, ...pkg.devDependencies })) {
    assert.match(version, /^\d+\.\d+\.\d+(?:-[\w.-]+)?$/);
    if (canonical.npm[name]) assert.equal(version, canonical.npm[name], name);
  }
});
