import type { APIRoute } from 'astro';
import { guideNavigation } from '../lib/navigation.mjs';
import { markdownFor, version } from '../lib/paths.mjs';

export const GET: APIRoute = () => new Response(`# crefft

> Engineering practice, pinned. Source version ${version}.

Root URLs follow published releases; use each guide's source commit for immutable wording.
Select the applicable guides rather than loading the entire corpus.

## Start

- [For agents](https://crefft.dev/for-agents.md)
- [Repository brief](https://crefft.dev/raw/AGENTS.md)
- [Guide index](https://crefft.dev/guides.md)
- [Raw file manifest](https://crefft.dev/files.json)

## Guide categories

${guideNavigation.map((item) => `- [${item.title}](https://crefft.dev${markdownFor(item.url)})`).join('\n')}

## Scope

Every reading page has a Markdown twin: /x/ becomes /x.md; / becomes /index.md.
Raw downloads preserve source bytes and include SHA-256 and size in files.json.
The separately licensed reference tree is not published or bundled here.
`, { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
