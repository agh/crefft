import rehypeRaw from 'rehype-raw';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkGfm from 'remark-gfm';
import remarkStringify from 'remark-stringify';
import { rehypeHeadingIds } from '@astrojs/markdown-remark';
import { resolveSourceLink } from './paths.mjs';
import ruleBlocks from './rule-blocks.mjs';

export function sourceLinks({ markdown = false } = {}) {
  return (tree, file) => {
    if (!file.path) throw new Error('Markdown source path is required');
    const visit = (node) => {
      if (node.type === 'html' && /<(?:script|style|iframe|object|embed|form)\b|\son\w+\s*=|\sstyle\s*=|\b(?:href|src)\s*=\s*["']?\s*(?:javascript|data|vbscript):/i.test(node.value)) {
        throw new Error(`Active HTML is not publishable: ${file.path}`);
      }
      if (['link', 'definition', 'image'].includes(node.type) && node.url) {
        node.url = resolveSourceLink(node.url, file.path, markdown);
        if (node.type === 'image') {
          node.type = 'link';
          node.children = [{ type: 'text', value: node.alt || 'Image source' }];
          delete node.alt;
        }
      }
      for (const child of node.children ?? []) visit(child);
    };
    visit(tree);
  };
}

export function readableBlocks() {
  return (tree) => {
    const visit = (node) => {
      if (node.type === 'element' && node.tagName === 'img') {
        throw new Error('Raw images are not publishable; use a Markdown image-source link');
      }
      if (node.type === 'element' && ['pre', 'table'].includes(node.tagName)) {
        node.properties ??= {};
        node.properties.tabIndex = 0;
        if (node.tagName === 'pre') {
          node.properties.role = 'region';
          node.properties.ariaLabel = 'Code example';
        }
      }
      for (const child of node.children ?? []) visit(child);
    };
    visit(tree);
  };
}

export const remarkPlugins = [sourceLinks];
/** @type {import('@astrojs/markdown-remark').RehypePlugins} */
export const rehypePlugins = [
  rehypeRaw,
  [rehypeSanitize, {
    ...defaultSchema,
    clobberPrefix: '',
    attributes: {
      ...defaultSchema.attributes,
      '*': [...defaultSchema.attributes['*'], 'id'],
    },
  }],
  readableBlocks,
  rehypeHeadingIds,
  ruleBlocks,
];

export const parser = unified().use(remarkParse).use(remarkGfm);

export async function readingTwin(body, source) {
  const frontmatter = body.match(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/)?.[0] ?? '';
  const processor = unified().use(remarkParse).use(remarkGfm)
    .use(sourceLinks, { markdown: true }).use(remarkStringify);
  return frontmatter + String(await processor.process({ value: body.slice(frontmatter.length), path: source }));
}
