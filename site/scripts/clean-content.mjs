import { rm } from 'node:fs/promises';

// Astro's content cache does not track changes in transitive Markdown plugins.
await rm('.astro', { recursive: true, force: true });
await rm('.cache/astro', { recursive: true, force: true });
