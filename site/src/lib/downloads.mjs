import { createHash } from 'node:crypto';
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { repository, commit, version } from './paths.mjs';

async function walk(directory) {
  const files = [];
  for (const entry of await readdir(path.join(repository, directory), { withFileTypes: true })) {
    const name = `${directory}/${entry.name}`;
    if (entry.isSymbolicLink()) throw new Error(`Download symlink is not allowed: ${name}`);
    if (entry.isDirectory()) files.push(...await walk(name));
    else if (entry.isFile()) files.push(name);
  }
  return files;
}

export async function fileManifest() {
  const sources = ['AGENTS.md', ...await walk('agents'), ...await walk('commands'), ...await walk('configs')];
  const files = await Promise.all(sources.sort().map(async (source) => {
    const bytes = await readFile(path.join(repository, source));
    return {
      path: source,
      url: `/raw/${source}`,
      size: bytes.length,
      sha256: createHash('sha256').update(bytes).digest('hex'),
    };
  }));
  return { schemaVersion: 1, version, commit, files };
}
