import type { APIRoute } from 'astro';
import { fileManifest } from '../lib/downloads.mjs';

export const GET: APIRoute = async () => new Response(`${JSON.stringify(await fileManifest(), null, 2)}\n`, {
  headers: { 'Content-Type': 'application/json; charset=utf-8' },
});
