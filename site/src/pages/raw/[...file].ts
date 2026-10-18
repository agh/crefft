import { readFile } from 'node:fs/promises';
import path from 'node:path';
import type { APIRoute } from 'astro';
import { repository } from '../../lib/paths.mjs';
import { fileManifest } from '../../lib/downloads.mjs';

export async function getStaticPaths() {
  return (await fileManifest()).files.map((file) => ({
    params: { file: file.path }, props: { source: file.path },
  }));
}
export const GET: APIRoute = async ({ props }) => {
  if (typeof props.source !== 'string') throw new Error('Raw source path is missing');
  return new Response(new Uint8Array(await readFile(path.join(repository, props.source))), {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
