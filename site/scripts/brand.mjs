import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { Resvg } from '@resvg/resvg-js';
import { artwork } from './artwork.mjs';

const tokens = JSON.parse(await readFile('src/brand/visual.json', 'utf8'));
const roles = ['canvas', 'surface', 'ink', 'secondary', 'accent', 'accentHover',
  'good', 'bad', 'edge', 'focus'];
assert.deepEqual(Object.keys(tokens).sort(), ['dark', 'light']);
for (const mode of Object.values(tokens)) {
  assert.deepEqual(Object.keys(mode).sort(), [...roles].sort());
  for (const value of Object.values(mode)) assert.match(value, /^#[0-9A-F]{6}$/);
}
const variables = (mode) => roles.map((role) => `  --${role}: ${tokens[mode][role]};`).join('\n');
const css = `:root {\n  color-scheme: light dark;\n${variables('light')}\n}
@media (prefers-color-scheme: dark) {\n  :root {\n${variables('dark')}\n  }\n}
@media print {\n  :root {\n${variables('light')}\n  }\n}\n`;
await mkdir('src/generated', { recursive: true });
await writeFile('src/generated/tokens.css', css);
const icon = (await readFile('src/brand/16.svg', 'utf8'))
  .replace('fill="currentColor"', `fill="${tokens.light.accent}"`);
await writeFile('public/favicon.svg', icon);
const icons = [16, 32].map((size) => new Resvg(icon, {
  fitTo: { mode: 'width', value: size },
}).render().asPng());
await Promise.all(icons.map((bytes, index) => writeFile(`public/favicon-${[16, 32][index]}.png`, bytes)));
const directory = Buffer.alloc(6 + 16 * icons.length);
directory.writeUInt16LE(1, 2);
directory.writeUInt16LE(icons.length, 4);
let offset = directory.length;
icons.forEach((bytes, index) => {
  const entry = 6 + 16 * index;
  directory[entry] = directory[entry + 1] = [16, 32][index];
  directory.writeUInt16LE(1, entry + 4);
  directory.writeUInt16LE(32, entry + 6);
  directory.writeUInt32LE(bytes.length, entry + 8);
  directory.writeUInt32LE(offset, entry + 12);
  offset += bytes.length;
});
await writeFile('public/favicon.ico', Buffer.concat([directory, ...icons]));
const { banner, social, shapes } = await artwork(tokens.light);
await writeFile('../banner.svg', banner);
await writeFile('public/social-preview.svg', social);
await writeFile('public/social-preview.png', new Resvg(social).render().asPng());
await writeFile('src/generated/artwork.json', `${JSON.stringify(shapes, null, 2)}\n`);
console.log('Brand: pushed tokens, final Witness favicons, outlined banner, and social preview generated.');
