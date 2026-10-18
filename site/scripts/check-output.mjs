import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readdir, readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { load } from 'cheerio';
import { fileManifest } from '../src/lib/downloads.mjs';

const base = 'https://crefft.dev';
const dist = path.resolve('dist');
const errors = [];
const externalOrigins = new Set();
const outboundOrigins = new Set();
export async function walk(directory) {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    assert.ok(!entry.isSymbolicLink(), `Output symlink: ${entry.name}`);
    const file = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await walk(file));
    else files.push(file);
  }
  return files.sort();
}
const files = await walk(dist);
const relative = (file) => path.relative(dist, file).split(path.sep).join('/');
const names = new Set(files.map(relative));
const html = new Map();
const canonicalPath = (name) => name === 'index.html' ? '/'
  : name === '404.html' ? '/404/' : `/${name.replace(/index\.html$/, '')}`;
for (const file of files.filter((file) => file.endsWith('.html'))) {
  html.set(canonicalPath(relative(file)), load(await readFile(file, 'utf8')));
}
function targetFor(url) {
  const name = decodeURIComponent(url.pathname).slice(1);
  if (names.has(name)) return name;
  if (names.has(`${name}${name.endsWith('/') || !name ? '' : '/'}index.html`)) {
    return `${name}${name.endsWith('/') || !name ? '' : '/'}index.html`;
  }
  if (name === '404/' || name === '404') return '404.html';
}
function checkLink(value, source, resource = false) {
  if (!value) return;
  let url;
  try { url = new URL(value, `${base}${source}`); }
  catch { errors.push(`${source}: invalid URL ${value}`); return; }
  if (url.protocol === 'mailto:' && !resource) return;
  if (url.origin !== base) {
    (resource ? externalOrigins : outboundOrigins).add(url.origin);
    if (!['https:', 'http:'].includes(url.protocol)) errors.push(`${source}: unsafe URL ${value}`);
    return;
  }
  const target = targetFor(url);
  if (!target) { errors.push(`${source}: missing ${value}`); return; }
  if (url.hash && !resource) {
    const route = canonicalPath(target);
    const page = html.get(route) ?? (target.endsWith('.md') && !target.startsWith('raw/')
      ? html.get(target === 'index.md' ? '/' : `/${target.slice(0, -3)}/`) : undefined);
    if (page) {
      const id = decodeURIComponent(url.hash.slice(1));
      const found = page('[id], a[name]').toArray().some((element) =>
        page(element).attr('id') === id || page(element).attr('name') === id);
      if (!found && !id.startsWith(':~:text=')) errors.push(`${source}: missing anchor ${value}`);
    } else if (target.startsWith('raw/')) {
      errors.push(`${source}: raw downloads do not expose HTML anchors: ${value}`);
    }
  }
}
for (const [route, $] of html) {
  const ids = new Set();
  $('[id]').each((_, element) => {
    const id = $(element).attr('id');
    if (ids.has(id)) errors.push(`${route}: duplicate id ${id}`);
    ids.add(id);
  });
  if ($('h1').length !== 1) errors.push(`${route}: expected one H1, found ${$('h1').length}`);
  const twin = route === '/' ? '/index.md' : `${route.slice(0, -1)}.md`;
  if ($(`link[rel="alternate"][type="text/markdown"]`).attr('href') !== twin) {
    errors.push(`${route}: missing advertised Markdown twin`);
  }
  checkLink(twin, route);
  $('a[href], link[href]').each((_, element) => {
    const rel = $(element).attr('rel') ?? '';
    checkLink($(element).attr('href'), route,
      element.name === 'link' && !['canonical', 'alternate'].includes(rel));
    if ($(element).attr('ping')) errors.push(`${route}: link ping`);
  });
  $('[src], [srcset], [poster], [data], form[action]').each((_, element) => {
    for (const attribute of ['src', 'poster', 'data', 'action']) {
      checkLink($(element).attr(attribute), route, true);
    }
    for (const candidate of ($(element).attr('srcset') ?? '').split(',')) {
      if (candidate.trim()) checkLink(candidate.trim().split(/\s+/)[0], route, true);
    }
  });
  if ($('[style]').length) errors.push(`${route}: inline styles`);
  $('*').each((_, element) => {
    if (Object.keys(element.attribs ?? {}).some((name) => /^on/i.test(name))) {
      errors.push(`${route}: inline event handler`);
    }
  });
  if (route !== '/search/' && $('script').length) errors.push(`${route}: reading-page JavaScript`);
  $('svg path').each((_, element) => {
    if (!/^[MLZ\d .,-]+$/.test($(element).attr('d') ?? '')) errors.push(`${route}: noncanonical mark path`);
  });
  checkLink($('meta[property="og:image"]').attr('content'), route, true);
  if ($('iframe, object, embed, base, meta[http-equiv="refresh"]').length) errors.push(`${route}: active embedded content`);
  if (!$('meta[http-equiv="content-security-policy" i]').length) errors.push(`${route}: missing Astro CSP`);
}
for (const file of files.filter((file) => /\.(css|svg)$/.test(file))) {
  const source = await readFile(file, 'utf8');
  for (const match of source.matchAll(/url\(\s*["']?([^"')]+)["']?\s*\)|@import\s+["']([^"']+)/g)) {
    const url = match[1] ?? match[2];
    if (!url.startsWith('#')) checkLink(url, `/${relative(file)}`, true);
  }
}
for (const file of await walk('src')) {
  if (!/\.(astro|css)$/.test(file) || file.includes('/generated/')) continue;
  const source = await readFile(file, 'utf8');
  if (/#[\da-f]{3,8}\b|\b(?:rgb|hsl|oklch)\(/i.test(source)) errors.push(`${file}: hard-coded color`);
}
for (const file of (await fileManifest()).files) {
  const bytes = await readFile(path.join(dist, file.url));
  assert.equal(bytes.length, file.size, file.path);
  assert.equal(createHash('sha256').update(bytes).digest('hex'), file.sha256, file.path);
}
for (const name of names) {
  if (name.startsWith('reference/') && name !== 'reference/index.html') errors.push(`Vendored output: ${name}`);
}
const sizes = await Promise.all(files.map(async (file) => ({ path: relative(file), bytes: (await readFile(file)).length })));
const largestPage = sizes.filter((file) => file.path.endsWith('.html')).sort((a, b) => b.bytes - a.bytes)[0];
const report = {
  htmlPages: html.size,
  totalFiles: files.length,
  totalBytes: sizes.reduce((sum, file) => sum + file.bytes, 0),
  largestPage,
  externalResourceOrigins: [...externalOrigins].sort(),
  outboundLinkOrigins: [...outboundOrigins].sort(),
  errors,
};
await mkdir('test-results', { recursive: true });
await writeFile('test-results/output.json', `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify({ ...report, outboundLinkOrigins: `${outboundOrigins.size} outbound citation origins (not runtime requests)` }, null, 2));
assert.deepEqual([...externalOrigins], [], 'External runtime origins');
assert.deepEqual(errors, [], 'Built output errors');
