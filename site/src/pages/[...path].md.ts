import { readFile } from 'node:fs/promises';
import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';
import { pages } from '../lib/pages.mjs';
import { homeMarkdown, specimenMarkdown, specimenURL } from '../lib/home.mjs';
import { readingTwin } from '../lib/markdown.mjs';
import { markdownFor, routeFor, sourceURL, version } from '../lib/paths.mjs';
import { fileManifest } from '../lib/downloads.mjs';

export async function getStaticPaths() {
  const entries = await getCollection('documents');
  const files = (await fileManifest()).files;
  return [
    ...entries.map((entry) => ({
      params: { path: markdownFor(routeFor(entry.id)).slice(1, -3) },
      props: { source: entry.filePath, id: entry.id, body: undefined },
    })),
    ...[...pages, { route: '/', body: homeMarkdown }, { route: specimenURL, body: specimenMarkdown }].map((page) => ({
      params: { path: markdownFor(page.route).slice(1, -3) },
      props: { body: page.body, source: undefined, id: undefined },
    })),
    ...['agents', 'commands', 'configs'].map((root) => ({
      params: { path: root },
      props: {
        body: `# ${root}\n\nByte-exact downloads; size and SHA-256 in [files.json](/files.json).\n\n${
          files.filter((file) => file.path.startsWith(`${root}/`))
            .map((file) => `- [${file.path}](${file.url}) (${file.size} bytes)`).join('\n')}\n`,
        source: undefined, id: undefined,
      },
    })),
  ];
}

export const GET: APIRoute = async ({ props }) => {
  let body = props.body;
  if (props.source) {
    const raw = await readFile(props.source, 'utf8');
    body = await readingTwin(raw, props.source);
    body += `\n---\n\nSource version: ${version}. [Source file](${sourceURL(props.id)}).\n`;
  }
  if (typeof body !== 'string') throw new Error('Markdown twin body is missing');
  return new Response(body, { headers: { 'Content-Type': 'text/markdown; charset=utf-8' } });
};
