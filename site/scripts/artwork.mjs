import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import opentype from 'opentype.js';

const number = (value) => Number(value.toFixed(3));
const point = (command) => ({ x: command.x, y: command.y });
const midpoint = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
const distanceToLine = (p, a, b) => {
  const length = Math.hypot(b.x - a.x, b.y - a.y);
  return length === 0 ? Math.hypot(p.x - a.x, p.y - a.y)
    : Math.abs((b.y - a.y) * p.x - (b.x - a.x) * p.y + b.x * a.y - b.y * a.x) / length;
};

// Lettering curves are flattened to at most 0.025 px control-point deviation.
function flattenCurve(points, append) {
  const first = points[0];
  const last = points.at(-1);
  if (points.slice(1, -1).every((p) => distanceToLine(p, first, last) <= 0.025)) {
    append(last);
    return;
  }
  const levels = [points];
  while (levels.at(-1).length > 1) {
    const previous = levels.at(-1);
    levels.push(previous.slice(1).map((p, index) => midpoint(previous[index], p)));
  }
  flattenCurve(levels.map((level) => level[0]), append);
  flattenCurve(levels.map((level) => level.at(-1)).reverse(), append);
}

export function linePath(commands) {
  const output = [];
  let current = { x: 0, y: 0 };
  let start = current;
  const line = (p) => {
    output.push(`L${number(p.x)} ${number(p.y)}`);
    current = p;
  };
  for (const command of commands) {
    if (command.type === 'M') {
      current = point(command);
      start = current;
      output.push(`M${number(current.x)} ${number(current.y)}`);
    } else if (command.type === 'L') {
      line(point(command));
    } else if (command.type === 'Q') {
      flattenCurve([current, { x: command.x1, y: command.y1 }, point(command)], line);
    } else if (command.type === 'C') {
      flattenCurve([current, { x: command.x1, y: command.y1 }, { x: command.x2, y: command.y2 }, point(command)], line);
    } else if (command.type === 'Z') {
      output.push('Z');
      current = start;
    } else {
      throw new Error(`Unsupported outline command: ${command.type}`);
    }
  }
  return output.join('');
}

export async function artwork(tokens) {
  const readFont = async (file) => {
    const bytes = await readFile(`assets/fonts/${file}`);
    return opentype.parse(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));
  };
  const reading = await readFont('SourceSerif4-Regular.ttf');
  const mono = await readFont('SourceCodePro-Regular.ttf');
  const wordmark = (await readFile('src/brand/wordmark.svg', 'utf8')).match(/<path\b[^>]+\/>/g).join('');
  const shapes = [];
  function make({ name, width, height, spine, markX, markY, markWidth, lines }) {
    const bounds = [];
    const paths = lines.map(({ text, x, y, size, role = 'accent', face = reading }) => {
      const outline = face.getPath(text, x, y, size);
      const box = outline.getBoundingBox();
      assert.ok(box.x1 >= 0 && box.y1 >= 0 && box.x2 <= width && box.y2 <= height,
        `${name}: lettering outside canvas: ${text}`);
      bounds.push({ text, size, ...box });
      return `<path fill="${tokens[role]}" d="${linePath(outline.commands)}"/>`;
    }).join('\n');
    shapes.push({ name, width, height, lettering: bounds });
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="title desc">
<title id="title">crefft / Engineering practice, pinned.</title>
<desc id="desc">Explicit rules, their reasons, and recorded tool versions. Final Witness mark with outlined lettering.</desc>
<rect width="${width}" height="${height}" fill="${tokens.canvas}"/>
<path fill="${tokens.accent}" d="M${spine} 40L${spine + 2} 40L${spine + 2} ${height - 40}L${spine} ${height - 40}Z"/>
<g fill="${tokens.accent}" transform="translate(${markX} ${markY}) scale(${markWidth / 352})">${wordmark}</g>
${paths}
</svg>\n`;
  }
  const banner = make({
    name: 'banner', width: 1200, height: 300, spine: 352, markX: 48, markY: 82, markWidth: 264,
    lines: [
      { text: 'Engineering', x: 402, y: 112, size: 62 },
      { text: 'practice, pinned.', x: 402, y: 182, size: 62 },
      { text: 'Explicit rules. Recorded versions.', x: 402, y: 240, size: 24, role: 'ink' },
      { text: 'crefft.dev', x: 48, y: 228, size: 18, face: mono, role: 'secondary' },
    ],
  });
  const social = make({
    name: 'social-preview', width: 1280, height: 640, spine: 400, markX: 48, markY: 72, markWidth: 308,
    lines: [
      { text: 'Engineering', x: 448, y: 236, size: 84 },
      { text: 'practice, pinned.', x: 448, y: 330, size: 84 },
      { text: 'Explicit rules, their reasons,', x: 448, y: 428, size: 29, role: 'ink' },
      { text: 'and recorded tool versions.', x: 448, y: 468, size: 29, role: 'ink' },
      { text: 'crefft.dev', x: 48, y: 554, size: 24, face: mono, role: 'secondary' },
    ],
  });
  return { banner, social, shapes };
}
