import { sourceURL } from './paths.mjs';

export const pages = [
  {
    route: '/for-agents/',
    title: 'For agents',
    body: `# For agents

The brief is [AGENTS.md](/raw/AGENTS.md): the repository's instructions for
working with crefft, including scope, writing conventions, and checks.
It is not a claim that every harness automatically loads this file.

## Development and reporting

crefft is developed in a private repository.
[GitHub carries tagged releases](https://github.com/agh/crefft/releases),
not ongoing development. GitHub issues and pull requests are disabled;
source links are for reading, not submitting changes.
[GitHub private vulnerability reporting](https://github.com/agh/crefft/security/advisories/new)
is the only public reporting channel.

## Fetch only what the task needs

Start with [llms.txt](/llms.txt), a short routing map, or the
[guide index](/guides/). Every HTML page advertises its Markdown twin with
\`rel="alternate" type="text/markdown"\`.

For a reading route \`/guides/languages/python/\`, fetch
[/guides/languages/python.md](/guides/languages/python.md).
The home twin is [/index.md](/index.md). Twins retain the source wording,
with links rebased for reading outside GitHub.

Root URLs change when a new release is published. For immutable wording,
use the source commit linked from a guide; save the file and its digest
when adopting it in a project. Release archives are not provided by this site.

## Raw downloads

[files.json](/files.json) lists every file from \`agents/\`, \`commands/\`,
and \`configs/\`, plus the brief. Each entry records its repository path,
download URL, byte size, and SHA-256 digest. Raw files preserve source bytes,
including frontmatter and final newlines; they are not formatted Markdown twins.

Browse [agent definitions](/agents/), [commands](/commands/), and
[configurations](/configs/). Review a file before adopting it.
Do not execute a downloaded configuration as a shell installer.

## Scope and precedence

Select the applicable guides and record the adopted version and any project
decisions. A remote link does not prove that a harness fetched or followed it.
This site does not install files, choose project policy, or certify harness compatibility.

The separately licensed \`reference/\` tree is excluded from downloads and search.
See [reference notices](/reference/).
`,
  },
  {
    route: '/privacy/',
    title: 'Privacy',
    body: `# Privacy

This site sets no cookies and includes no analytics, tracking pixels, remote
fonts, embeds, or third-party resource requests. Reading pages need no JavaScript.
Fonts, styles, and search resources are served from the same origin as the page.

## Local search

Search runs in your browser using a downloaded Pagefind index. Search terms
are not sent to a search service or added to the URL. The browser requests
index and result files from this site as needed. The host can receive those
file requests; local search does not mean there is no network traffic.
The site does not store queries or preferences in cookies or browser storage.

## Hosting

Cloudflare serves the static files. Serving and protecting an HTTP request
requires the host to process connection and request information, such as the
IP address, requested URL, browser headers, and timing. Its normal security,
operational, and logging systems may process this information.

This notice does not assert a retention period, a processing location, or
the absence of host-level logs. Those depend on the provider and the account
configuration. Consult [Cloudflare's privacy policy](https://www.cloudflare.com/privacypolicy/)
for the provider's account of its processing.

## Outbound links

Guides link to source repositories and other references. Following one of
those links leaves this site and makes a request to that destination.
The site uses a no-referrer policy.
`,
  },
  {
    route: '/reference/',
    title: 'Reference notices',
    body: `# Reference notices

The repository's \`reference/\` tree contains third-party material with
separate licenses. It is not published, indexed, or bundled by this site.

Read [THIRD_PARTY_NOTICES.md](${sourceURL('THIRD_PARTY_NOTICES.md')})
for attribution, licenses, and recorded restrictions. Guide citations link
to those files in the source repository rather than republishing them here.

## Site typefaces

The self-hosted reading and code fonts are subsets derived from Source Serif 4
and Source Code Pro. The modified font names are crefft Reading and crefft Mono.
Both are distributed under the SIL Open Font License 1.1:
[Serif license](/fonts/SourceSerif4-OFL.txt) and
[Code license](/fonts/SourceCodePro-OFL.txt).
`,
  },
  {
    route: '/search/',
    title: 'Search guides',
    body: `# Search guides

Search the guides locally. Use double quotes for an exact phrase.
The index loads only when you submit a search.

Without JavaScript, [browse the guide index](/guides/) or use your
browser's Find command within a guide.
`,
  },
  {
    route: '/404/',
    title: 'Page not found',
    body: `# Page not found

This address does not point to a published page.

[Browse guides](/guides/), [search](/search/), or [return home](/).
`,
  },
];
