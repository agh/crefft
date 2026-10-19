# crefft.dev

Custom Astro static output, local Pagefind search, and Cloudflare Workers
static assets. There is no Worker script, SSR adapter, runtime font service,
analytics, cookie, or client-side router.

## Local setup

The checked toolchain uses Node.js `26.11.1`, npm's committed lockfile,
Astro `7.4.0`, TypeScript `6.0.3`, and Wrangler `4.151.1`.
All site dependencies and browser downloads stay inside `site/`.

From the repository root:

```sh
npm ci --prefix site
PLAYWRIGHT_BROWSERS_PATH="$PWD/site/.cache/browsers" \
  site/node_modules/.bin/playwright install chromium
ASTRO_TELEMETRY_DISABLED=1 make site-check
make check -o node_modules
```

`make site-check` runs Astro check, contract tests, a clean static build,
Pagefind, internal paths and fragments, Markdown-twin coverage, raw-file
integrity, token contrast, and a third-party resource audit. It then starts
an isolated local Wrangler server, checks HTTP status, MIME types, security
headers, search, no-JavaScript reading, and axe on home, Python, the rule
specimen, the language index, and a missing page in light/dark at `1440x900`
and `390x844`. The browser also checks exact title and identity sizes and
the citation spine's desktop position and phone divider.
Serious or critical axe findings fail the gate. The server stops afterward.

Evidence goes to `site/test-results/`; twelve viewport screenshots go to
`SITE-OUT/` with the `round2-` prefix. Both directories are ignored. Axe incomplete results are
retained, not treated as a full accessibility certification.
The resource-origin check distinguishes automatically fetched assets from
ordinary outbound citation links. Those citations are retained.

The repository Markdown gate checks tracked first-party files and the new
site documentation, not private design inputs or generated twins. The
site Gitleaks configuration extends the repository's unchanged rules and
excludes only private inputs, generated copies, tool installations, and
local evidence. Authored site code remains scanned.

For an interactive local preview after building:

```sh
ASTRO_TELEMETRY_DISABLED=1 npm --prefix site run build
cd site
WRANGLER_SEND_METRICS=false WRANGLER_WRITE_LOGS=false npm run preview
```

Open `http://127.0.0.1:4371/`. `astro dev` is available through
`npm --prefix site run dev`, but does not exercise Cloudflare headers.

## Content and URLs

`src/content.config.ts` uses Astro's `glob()` loader over the authoritative
`guides/`, `agents/`, `commands/`, and `configs/` Markdown in place.
No content files are copied into this source tree.
Guide navigation comes from the Markdown AST of `SUMMARY.md`.
Contract tests compare that navigation with the actual guide inventory.
Raw download inventories also include non-Markdown files and dotfiles.

| Source or page | Reading route | Markdown |
| --- | --- | --- |
| Home | `/` | `/index.md` |
| Guide index | `/guides/` | `/guides.md` |
| Python | `/guides/languages/python/` | `/guides/languages/python.md` |
| Rule specimen | `/rules/python-pre-commit/` | `/rules/python-pre-commit.md` |
| Rust core | `/guides/languages/rust/` | `/guides/languages/rust.md` |
| Rust topic index | `/guides/languages/rust/topics/` | `/guides/languages/rust/topics.md` |
| Agent information | `/for-agents/` | `/for-agents.md` |
| Missing page | Custom 404 response | `/404.md` |

Twins preserve source wording and code, rebase links, retain harness
frontmatter, and identify the source commit. Raw downloads under `/raw/`
are byte-exact; `/files.json` records path, URL, byte size, and SHA-256.
They are served as plain-text attachments with `nosniff`, not active content.
The brief is available at `/raw/AGENTS.md`.

The home proof extracts the Python guide's complete hook requirement,
rationale, and configuration. The shortened bad example is explicitly
illustrative. No CR identifiers, review dates, or compatibility results
are invented. Plain code avoids inline syntax colors and preserves the
strict CSP.

The proof sheet and its rule specimen share one component and source
extraction. The dedicated route is a named excerpt, not a permanent CR
identifier. Its citation reads "Identifier not yet assigned."

Within guides, the renderer groups each heading and its following content
up to the next heading. Sections containing bold normative keywords outside
code receive a citation rail; no source nodes, text, or anchors are removed.
The rail names the guide and section, extracts explicit hook repository/revision
pairs from that section's code, and links back to its source context.
Other version declarations remain in the section rather than being guessed
as a rule-level pin. This is presentation grouping, not rule allocation or
an authored rule registry. Citation metadata is excluded from search.

The website corrects the Docker agent's misdirected
`docker.md#secrets-vs-environment-variables` link during rendering and twin
generation. Source directory links go to the commit-pinned repository tree.
Links to sections of the brief go to its commit-pinned GitHub page because
plain-text attachments do not expose HTML anchors. No guide or agent source
is rewritten.

The root navigation generator currently reports two existing omissions in
`SUMMARY.md`: `configs/claude/infrastructure/audit-hook.sh` and
`configs/claude/infrastructure/sops_command.py`. The site lists both in the
configuration downloads and manifest. Its blocking navigation contract
covers all guide routes; it does not rewrite `SUMMARY.md`.

The `reference/` payloads are excluded. `/reference/` links to the
commit-pinned `THIRD_PARTY_NOTICES.md`.
Root URLs are release-updated, not immutable archives. Per-release records,
rule registries, conformance certification, and harness installation are
outside this first publication.

## Brand and fonts

`src/brand/visual.json` is the only authored color source. `npm run brand`
compiles the pushed cobalt light/dark palette into CSS custom properties
and generates the Witness favicons and outlined artwork. Components use token references.
Light is the default; dark follows `prefers-color-scheme`.
The supplied 64-unit Witness is the header mark; the separately drawn
16-unit master supplies `favicon.svg`, the 16- and 32-pixel PNG files, and
the two-image `favicon.ico`. These favicon defaults use light cobalt.
All shipped Witness and wordmark paths use absolute `M`, `L`, and `Z`
commands with unchanged geometry.

The desktop home title is `88px/1.01`; the rule title is `70px/1.05`.
The citation identity is `43px/1.15`, with a 224-pixel context column.
The cobalt spine sits at x=318 and text begins at x=352 at a 1440-pixel
viewport. On phones, the title is 44 pixels, the identity 24 pixels, and
the spine becomes a horizontal divider above the identity. Context follows
the obligation, pin, reason, and examples rather than displacing them.
Long reading stays at `19px/1.6`, capped at `68ch`; phone reading is
`18px/1.55`. The complete source rationale is longer than the design study's
summary, so the home proof continues below the phone's first viewport.

`npm run brand` also regenerates the repository's `banner.svg` at
1200x300 and `public/social-preview.svg` plus its 1280x640 PNG.
The artwork uses the final Witness and outlined lettering, with no
embedded fonts or external resources. The existing README banner link
is unchanged. The HTML head advertises the social PNG.
`scripts/artwork.mjs` outlines the local masters with pinned
`opentype.js` and flattens lettering curves to line segments with at most
0.025-pixel control-point deviation. Mark geometry is not approximated.
Generated lettering bounds and deterministic output are checked.

The contrast gate recomputes all 36 text, edge, focus, selection, and
skip-link pairs from `visual.json`: at least 4.5:1 for text and 3:1 for
edges and focus. Mutation tests prove every role and mode can fail.
Results are retained in `site/test-results/contrast.json`.

Source Serif 4 and Source Code Pro masters are retained in `assets/fonts/`.
WOFF2 files in `public/fonts/` include Latin Extended, IPA where supported,
punctuation, and supported characters used by the corpus. IPA uses the
`ipa` class, which selects the code face. The SIL OFL texts and a
source/output digest manifest are distributed beside the fonts.
Subsetting changes the embedded font names to **crefft Reading** and
**crefft Mono**, respecting the reserved name in the original licenses.

Normal builds use the checked-in subsets and do not need Python font tooling.
To regenerate them with the exact preparation dependencies:

```sh
python3 -m venv site/.venv
site/.venv/bin/pip install -r site/scripts/font-requirements.txt
site/.venv/bin/python site/scripts/subset-fonts.py
```

## Security and privacy

`public/_headers` supplies the HTTP CSP, HSTS, `nosniff`, no-referrer policy,
permissions restrictions, and framing prohibition. Astro supplies a second,
per-document CSP. Only `/search/` and the Pagefind worker allow WASM
compilation; neither permits general JavaScript evaluation or inline handlers.
Reading pages contain no scripts.

HSTS deliberately omits `includeSubDomains` until every subdomain's HTTPS
coverage is known. Stable font and search URLs are not cached as immutable.
Only fingerprinted Astro assets receive an immutable cache policy.

`wrangler.jsonc` contains no `main` or runtime binding. In addition to
`assets.directory`, it explicitly sets automatic trailing slashes and
`not_found_handling: "404-page"`. The apex custom domain is configured,
Workers development and preview URLs are disabled, and observability is off.
Validate it locally without publishing:

```sh
cd site
WRANGLER_SEND_METRICS=false WRANGLER_WRITE_LOGS=false \
  npx --no-install wrangler deploy --dry-run
```

## One-time publication setup

No deployment is performed by a local build.

1. Add `crefft.dev` to the Cloudflare account and finish domain verification.
   Create a Worker named `crefft-site` in Workers & Pages without an
   application script. Keep Workers Builds disconnected; Actions is the
   deployment authority.
2. Confirm the account owns the `crefft.dev` zone. The deployment configuration
   attaches `crefft.dev` as a custom domain. Configure `www.crefft.dev` to
   redirect to the apex, and confirm valid HTTPS for both. Canonical HTML links
   use `https://crefft.dev`; `www` is not a second Worker route in this configuration.
3. The `production` GitHub environment already has both required secrets:
   `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`. Confirm the token has
   Workers Scripts Edit and the permissions needed to manage the configured
   custom domain in this account. Add environment approval and restrict
   deployment to release tags. Wrangler receives both secrets only through
   the deployment step's environment, never files or command arguments.
4. Disable Cloudflare Web Analytics, automatic RUM, Rocket Loader,
   script injection, email obfuscation, and browser challenges for public
   HTML, Markdown, and download paths. Confirm the final account settings
   agree with the published privacy notice.
5. Follow the [maintainer release process](../CONTRIBUTING.md#maintainer-release-workflow):
   sign and tag on the private forge, preview with
   `make publish-release TAG=vYYYY.M.N`, and explicitly publish the verified
   commit and tag from the maintainer's clone to `github`.
   GitHub's `v*` tag-triggered site workflow checks that
   identity, builds and verifies without deployment credentials, and uploads
   `site/dist`. Its protected deployment job downloads that exact artifact
   and runs the lockfile-pinned Wrangler; it does not rebuild.

All workflow actions use the repository's full-SHA pins and only
`contents: read`. Release builds and deployments use noncanceling
concurrency groups. Branch pushes and pull requests run the separate
`.forgejo/workflows/site.yml` checks on the private forge, without artifact
actions or deployment credentials. GitHub carries tagged releases, with
issues and pull requests disabled. The only public reporting channel is
[GitHub private vulnerability reporting](https://github.com/agh/crefft/security/advisories/new).

After publication, check HTTPS, custom-domain routing, search, CSP, Markdown
MIME types, raw downloads, and the real 404 again on both domains.
Local Wrangler cannot establish remote DNS, certificates, account settings,
retention policies, or deployment permissions.
