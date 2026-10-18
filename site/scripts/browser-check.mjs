import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:net';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

process.env.PLAYWRIGHT_BROWSERS_PATH ??= path.resolve('.cache/browsers');
await mkdir('test-results', { recursive: true });
await mkdir('../SITE-OUT', { recursive: true });
const listener = createServer();
listener.listen(0, '127.0.0.1');
await once(listener, 'listening');
const port = listener.address().port;
await new Promise((resolve) => listener.close(resolve));
const base = `http://127.0.0.1:${port}`;
const server = spawn(process.execPath, [
  'node_modules/wrangler/bin/wrangler.js', 'dev', '--local',
  '--ip', '127.0.0.1', '--port', String(port), '--inspector-port', '0',
  '--show-interactive-dev-session=false',
], {
  env: {
    ...process.env, CI: 'true', WRANGLER_SEND_METRICS: 'false', WRANGLER_WRITE_LOGS: 'false',
    X_LOCAL_EXPLORER: 'false', X_LOCAL_OBSERVABILITY: 'false',
    CLOUDFLARE_API_TOKEN: '', CLOUDFLARE_ACCOUNT_ID: '',
    XDG_CONFIG_HOME: path.resolve('.cache/config'),
    XDG_CACHE_HOME: path.resolve('.cache'),
  },
  stdio: ['ignore', 'pipe', 'pipe'],
});
let serverLog = '';
server.stdout.on('data', (bytes) => { serverLog += bytes; });
server.stderr.on('data', (bytes) => { serverLog += bytes; });
const report = { command: 'wrangler dev --local', smoke: [], axe: [], layout: [], screenshots: [], noJS: [], search: [], externalOrigins: [], errors: [] };
let browser;
try {
  let ready = false;
  for (let attempt = 0; attempt < 120; attempt++) {
    if (server.exitCode !== null) throw new Error(`Wrangler exited:\n${serverLog}`);
    try {
      const response = await fetch(base);
      if (response.ok) { ready = true; break; }
    } catch (error) {
      if (error.cause?.code !== 'ECONNREFUSED') throw error;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  assert.ok(ready, `Wrangler did not become responsive:\n${serverLog}`);
  const raw = '/raw/configs/pre-commit/.pre-commit-config.yaml';
  for (const [route, status, mime] of [
    ['/', 200, 'text/html'],
    ['/guides/languages/python/', 200, 'text/html'],
    ['/rules/python-pre-commit/', 200, 'text/html'],
    ['/llms.txt', 200, 'text/plain'],
    ['/guides/languages/python.md', 200, 'text/markdown'],
    ['/files.json', 200, 'application/json'],
    [raw, 200, 'text/plain'],
    ['/missing-page-for-smoke/', 404, 'text/html'],
  ]) {
    const response = await fetch(`${base}${route}`);
    const body = Buffer.from(await response.arrayBuffer());
    const headers = Object.fromEntries(response.headers);
    report.smoke.push({ route, status: response.status, contentType: headers['content-type'], bytes: body.length, headers });
    assert.equal(response.status, status, route);
    assert.ok(headers['content-type']?.startsWith(mime), `${route}: ${headers['content-type']}`);
    assert.equal(headers['x-content-type-options'], 'nosniff');
    assert.equal(headers['referrer-policy'], 'no-referrer');
    assert.ok(headers['strict-transport-security']?.includes('max-age='));
    assert.ok(headers['permissions-policy']?.includes('camera=()'));
    assert.ok(!headers['set-cookie'], `${route}: cookie`);
    if (status === 404) {
      assert.ok(body.toString().includes('Page not found'));
      assert.deepEqual(body, await readFile('dist/404.html'));
    }
    if (route === raw) assert.deepEqual(body, await readFile(`..${route.slice(4)}`));
    if (mime === 'text/html') {
      assert.ok(headers['content-security-policy']?.includes("frame-ancestors 'none'"));
      assert.ok(!headers['content-security-policy'].includes('wasm-unsafe-eval'));
    }
  }
  browser = await chromium.launch();
  report.browser = browser.version();
  const external = new Set();
  const routes = [
    ['home', '/'],
    ['guide', '/guides/languages/python/'],
    ['rule', '/rules/python-pre-commit/'],
    ['index', '/guides/languages/'],
    ['404', '/missing-page-for-smoke/'],
  ];
  for (const colorScheme of ['light', 'dark']) {
    for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
      for (const [name, route] of routes) {
        const context = await browser.newContext({ colorScheme, viewport });
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', (error) => errors.push(error.message));
        context.on('request', (request) => {
          if (new URL(request.url()).origin !== base) external.add(new URL(request.url()).origin);
        });
        await page.addInitScript(() => {
          window.cspViolations = [];
          document.addEventListener('securitypolicyviolation', (event) => window.cspViolations.push(`${event.violatedDirective}: ${event.blockedURI}`));
        });
        await page.goto(`${base}${route}`, { waitUntil: 'networkidle' });
        await page.evaluate(() => document.fonts.ready);
        assert.equal(await page.locator('h1').count(), 1);
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${name} overflow at ${viewport.width}`);
        assert.ok(await page.evaluate(() => document.fonts.check('19px Reading')), 'Reading font did not load');
        assert.deepEqual(await page.evaluate(() => window.cspViolations), [], `${name}: CSP`);
        assert.deepEqual(errors, [], `${name}: JavaScript errors`);
        const axe = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
        const violations = axe.violations.map(({ id, impact, nodes }) => ({
          id, impact, nodes: nodes.map(({ target, failureSummary }) => ({ target, failureSummary })),
        }));
        report.axe.push({
          page: name, colorScheme, viewport, violations,
          incomplete: axe.incomplete.map(({ id, impact, nodes }) => ({
            id, impact, nodes: nodes.map(({ target, any, all, none }) => ({
              target, checks: [...any, ...all, ...none].map(({ message }) => message),
            })),
          })),
        });
        const blocking = violations.filter(({ impact }) => ['serious', 'critical'].includes(impact));
        if (blocking.length) {
          report.errors.push(`${name}/${colorScheme}/${viewport.width}: serious or critical axe findings`);
          // Name the rule and the elements, so a failure in CI explains itself.
          for (const { id, impact, nodes } of blocking) {
            console.error(`axe ${impact} ${id} on ${name}/${colorScheme}/${viewport.width}:`);
            for (const { target, failureSummary } of nodes.slice(0, 5)) {
              console.error(`  ${target.join(' ')}: ${(failureSummary ?? '').split('\n').join(' ')}`);
            }
          }
        }
        if (['home', 'rule'].includes(name)) {
          const layout = await page.evaluate(() => {
            const record = document.querySelector('.proof-sheet');
            const main = record.querySelector('.record-main');
            return {
              titleSize: parseFloat(getComputedStyle(document.querySelector('h1')).fontSize),
              identitySize: parseFloat(getComputedStyle(record.querySelector('.serial')).fontSize),
              spineWidth: parseFloat(getComputedStyle(main).borderLeftWidth),
              phoneDivider: parseFloat(getComputedStyle(record).borderTopWidth),
              readingX: main.getBoundingClientRect().left + parseFloat(getComputedStyle(main).paddingLeft) + parseFloat(getComputedStyle(main).borderLeftWidth),
              unassigned: record.querySelector('.id-note').textContent,
            };
          });
          const phone = viewport.width === 390;
          assert.equal(layout.titleSize, phone ? 44 : name === 'home' ? 88 : 70);
          assert.equal(layout.identitySize, phone ? 24 : 43);
          assert.equal(phone ? layout.phoneDivider : layout.spineWidth, 2);
          assert.equal(layout.unassigned, 'Identifier not yet assigned');
          if (!phone) assert.equal(layout.readingX, 352);
          report.layout.push({ page: name, colorScheme, viewport, ...layout });
        }
        if (name === 'guide') {
          assert.ok(await page.locator('.guide-rule').count() > 0);
          const hookRule = page.locator('[data-rule-section="pre-commit-configuration"]');
          assert.ok(await hookRule.count() === 1);
          assert.ok((await hookRule.locator('.context').textContent()).includes('v0.16.6'));
        }
        if (['home', 'guide', 'rule'].includes(name)) {
          const screenshot = `../SITE-OUT/round2-${name}-${colorScheme}-${viewport.width}x${viewport.height}.png`;
          await page.screenshot({ path: screenshot });
          report.screenshots.push(screenshot);
        }
        await page.keyboard.press('Tab');
        assert.equal(await page.locator(':focus').textContent(), 'Skip to content');
        assert.deepEqual(await context.cookies(), []);
        assert.deepEqual(await page.evaluate(() => [localStorage.length, sessionStorage.length]), [0, 0]);
        await context.close();
      }
    }
  }
  for (const [name, route] of routes) {
    const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    await page.goto(`${base}${route}`);
    assert.ok((await page.locator('h1').textContent()).length > 0);
    assert.equal(await page.locator('script').count(), 0);
    if (name === 'guide') {
      await page.getByText('On this page', { exact: true }).click();
      assert.ok(await page.getByRole('navigation', { name: 'Contents', exact: true }).isVisible());
    }
    if (name === 'rule') {
      await page.getByText('Trace this rule', { exact: true }).click();
      assert.ok(await page.locator('#trace[open]').count() === 1);
    }
    report.noJS.push(name);
    await context.close();
  }
  const context = await browser.newContext();
  const page = await context.newPage();
  const requests = [];
  const errors = [];
  context.on('request', (request) => {
    requests.push(request.url());
    if (new URL(request.url()).origin !== base) external.add(new URL(request.url()).origin);
  });
  page.on('pageerror', (error) => errors.push(error.message));
  await page.addInitScript(() => {
    window.cspViolations = [];
    document.addEventListener('securitypolicyviolation', (event) => window.cspViolations.push(`${event.violatedDirective}: ${event.blockedURI}`));
  });
  const searchResponse = await page.goto(`${base}/search/`, { waitUntil: 'networkidle' });
  assert.ok(searchResponse.headers()['content-security-policy']?.includes('wasm-unsafe-eval'));
  assert.ok(!requests.some((url) => url.includes('/pagefind/')), 'Search index loaded before a query');
  for (const term of ['ruff', '"zzzznosuchrulezzzz"']) {
    await page.getByLabel('Search terms').fill(term);
    await page.getByRole('button', { name: 'Search', exact: true }).click();
    await page.waitForFunction(() => /\d+ results/.test(document.querySelector('#status').textContent));
    const status = await page.locator('#status').textContent();
    report.search.push({ term, status });
    assert.equal(await page.locator('#results > li').count(), term === 'ruff' ? 5 : 0);
    if (term === 'ruff') {
      await page.getByRole('button', { name: 'More results' }).click();
      await page.waitForFunction(() => document.querySelectorAll('#results > li').length > 5);
    }
  }
  assert.deepEqual(errors, []);
  assert.deepEqual(await page.evaluate(() => window.cspViolations), []);
  await context.close();
  const failureContext = await browser.newContext();
  const failurePage = await failureContext.newPage();
  await failurePage.route('**/pagefind/**', (route) => route.abort());
  await failurePage.goto(`${base}/search/`);
  await failurePage.getByLabel('Search terms').fill('ruff');
  await failurePage.getByRole('button', { name: 'Search', exact: true }).click();
  await failurePage.getByText('Search could not load. Browse the guide index or try again.').waitFor();
  report.search.push({ failure: 'Blocked index reports an explicit retry/browse message.' });
  await failureContext.close();
  report.externalOrigins = [...external];
  assert.deepEqual(report.externalOrigins, []);
  assert.deepEqual(report.errors, []);
} finally {
  await browser?.close();
  server.kill('SIGTERM');
  if (server.exitCode === null) await once(server, 'exit');
  await writeFile('test-results/wrangler.log', serverLog);
  await writeFile('test-results/browser.json', `${JSON.stringify(report, null, 2)}\n`);
}
console.log(`Wrangler: ${report.smoke.length} routes passed. Axe: ${report.axe.length} scans, no serious or critical findings.`);
console.log(`No-JS: ${report.noJS.join(', ')}. External request origins: ${JSON.stringify(report.externalOrigins)}.`);
console.log(`Screenshots: ${report.screenshots.length} saved under SITE-OUT/.`);
