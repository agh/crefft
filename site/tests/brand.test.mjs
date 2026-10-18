import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import test from 'node:test';
import { load } from 'cheerio';
import { Resvg } from '@resvg/resvg-js';
import { contrastPairs } from '../src/brand/contrast.mjs';
import { artwork } from '../scripts/artwork.mjs';
import { citationHTML, citationNode, element } from '../src/lib/citation.mjs';
import ruleBlocks from '../src/lib/rule-blocks.mjs';
import { repository } from '../src/lib/paths.mjs';

const palettes = JSON.parse(await readFile('src/brand/visual.json', 'utf8'));
test('all 36 text, edge, focus, selection, and skip-link pairs meet contrast thresholds', async () => {
  const pairs = contrastPairs(palettes);
  assert.equal(pairs.length, 36);
  for (const pair of pairs) {
    assert.ok(pair.ratio >= pair.minimum,
      `${pair.mode} ${pair.foreground}/${pair.background}: ${pair.ratio} < ${pair.minimum}`);
  }
  await mkdir('test-results', { recursive: true });
  await writeFile('test-results/contrast.json', `${JSON.stringify(pairs, null, 2)}\n`);
});

test('contrast checks reject failures in every authored role and mode', () => {
  for (const mode of ['light', 'dark']) {
    for (const role of ['ink', 'secondary', 'accent', 'accentHover', 'good', 'bad', 'edge', 'focus']) {
      const changed = structuredClone(palettes);
      changed[mode][role] = changed[mode].canvas;
      assert.ok(contrastPairs(changed).some((pair) => pair.ratio < pair.minimum), `${mode} ${role}`);
    }
  }
});

test('final Witness geometry uses only absolute M, L, and Z commands', async () => {
  const original = {
    'mark.svg': ['M6 50V31L15 22H26V14H18V10L22 6H34L38 10V14H34V22H49L58 31V42H50V34L46 30H34V50L26 58V30H18L14 34V50Z'],
    '16.svg': ['M1 13V8L3 6H6V3H4V2L5 1H8L9 2V3H8V6H13L15 8V11H13V9L12 8H8V13L6 15V8H4L3 9V13Z'],
  };
  for (const [name, paths] of Object.entries(original)) {
    const svg = await readFile(`src/brand/${name}`, 'utf8');
    const $ = load(svg, { xmlMode: true });
    $('path').each((index, node) => {
      const actual = $(node).attr('d');
      assert.match(actual, /^[MLZ\d .,-]+$/);
      $(node).attr('d', paths[index]);
    });
    for (const width of [16, 32, 64]) {
      const render = (source) => new Resvg(source, { fitTo: { mode: 'width', value: width } }).render().asPng();
      assert.deepEqual(render(svg), render($.xml()), `${name}: geometry at ${width}px`);
    }
  }
  const wordmark = load(await readFile('src/brand/wordmark.svg', 'utf8'), { xmlMode: true });
  wordmark('path').each((_, node) => assert.match(wordmark(node).attr('d'), /^[MLZ\d .,-]+$/));
});

test('favicon ICO contains the exact independent 16px and 32px PNG files', async () => {
  const ico = await readFile('public/favicon.ico');
  assert.equal(ico.readUInt16LE(0), 0);
  assert.equal(ico.readUInt16LE(2), 1);
  assert.equal(ico.readUInt16LE(4), 2);
  for (const [index, size] of [16, 32].entries()) {
    const png = await readFile(`public/favicon-${size}.png`);
    const entry = 6 + index * 16;
    const offset = ico.readUInt32LE(entry + 12);
    assert.equal(ico[entry], size);
    assert.equal(ico[entry + 1], size);
    assert.equal(png.readUInt32BE(16), size);
    assert.equal(png.readUInt32BE(20), size);
    assert.deepEqual(ico.subarray(offset, offset + ico.readUInt32LE(entry + 8)), png);
  }
});

test('banner and social sources are deterministic outlined artwork without font dependencies', async () => {
  const generated = await artwork(palettes.light);
  for (const [file, expected, width, height] of [
    ['../banner.svg', generated.banner, 1200, 300],
    ['public/social-preview.svg', generated.social, 1280, 640],
  ]) {
    const svg = await readFile(file, 'utf8');
    assert.equal(svg, expected);
    const $ = load(svg, { xmlMode: true });
    assert.equal($('svg').attr('width'), String(width));
    assert.equal($('svg').attr('height'), String(height));
    assert.equal($('text, image, use, style, script, foreignObject').length, 0);
    $('path').each((_, node) => assert.match($(node).attr('d'), /^[MLZ\d .,-]+$/));
  }
  const png = await readFile('public/social-preview.png');
  assert.equal(png.readUInt32BE(16), 1280);
  assert.equal(png.readUInt32BE(20), 640);
  assert.deepEqual(png, new Resvg(generated.social).render().asPng());
  assert.match(await readFile('../README.md', 'utf8'), /!\[crefft\]\(banner\.svg\)/);
});

test('citations escape text, show only recorded facts, and render nothing without them', () => {
  const html = citationHTML({ guide: '<script>', section: 'A & B', url: '/guides/' });
  assert.ok(!html.includes('<script>'));
  assert.doesNotMatch(html, /Identifier|Scope|Review date|Evidence|<dl/);
  assert.match(citationHTML({ pins: ['astral-sh/ruff-pre-commit v0.16.6'] }),
    /^<aside[^>]*><dl class="context"><dt>Recorded pin<\/dt><dd><code class="pin">astral-sh\/ruff-pre-commit v0\.16\.6<\/code><\/dd><\/dl><\/aside>$/);
  assert.equal(citationNode({}), null);
});

test('guide rule blocks preserve source nodes and anchors, without treating code as an obligation', () => {
  const text = (value) => ({ type: 'text', value });
  const title = element('h1', { id: 'python' }, [text('Python Style Guide')]);
  const heading = element('h2', { id: 'hooks' }, [text('Hooks')]);
  const statement = element('p', {}, [text('Hooks '), element('strong', {}, [text('MUST')]), text(' be pinned.')]);
  const why = element('p', {}, [text('Why: reproducible checks.')]);
  const exampleHeading = element('h2', { id: 'example' }, [text('Example')]);
  const code = element('pre', {}, [text('MUST')]);
  const tree = { type: 'root', children: [title, heading, statement, why, exampleHeading, code] };
  ruleBlocks()(tree, { path: `${repository}/guides/languages/python.md` });
  assert.equal(tree.children.length, 4);
  // No recorded pin, so the rule has no margin: its only child is the source content.
  assert.equal(tree.children[1].children.length, 1);
  assert.deepEqual(tree.children[1].children[0].children, [heading, statement, why]);
  assert.equal(tree.children[1].properties.dataRuleSection, 'hooks');
  assert.deepEqual(tree.children.slice(2), [exampleHeading, code]);
});

test('Wrangler shape and deployment credential isolation match the release contract', async () => {
  const config = JSON.parse(await readFile('wrangler.jsonc', 'utf8'));
  assert.deepEqual(config, {
    $schema: './node_modules/wrangler/config-schema.json',
    name: 'crefft-site', compatibility_date: '2026-10-17', workers_dev: false, preview_urls: false,
    assets: { directory: './dist', html_handling: 'auto-trailing-slash', not_found_handling: '404-page' },
    routes: [{ pattern: 'crefft.dev', custom_domain: true }], observability: { enabled: false },
  });
  const workflow = await readFile('../.github/workflows/site.yml', 'utf8');
  const deploy = workflow.slice(workflow.indexOf('  deploy:'));
  assert.match(deploy, /environment: production/);
  assert.match(deploy, /secrets\.CLOUDFLARE_ACCOUNT_ID/);
  assert.match(deploy, /secrets\.CLOUDFLARE_API_TOKEN/);
  assert.match(deploy, /startsWith\(github\.ref, 'refs\/tags\/v'\)/);
  assert.match(deploy, /cancel-in-progress: false/);
  assert.doesNotMatch(deploy, /vars\.|npm run build|make site-check/);
});
