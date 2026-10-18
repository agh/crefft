import { readFileSync } from 'node:fs';
import path from 'node:path';
import { parser } from './markdown.mjs';
import { repository, routeFor } from './paths.mjs';

const tree = parser.parse(readFileSync(path.join(repository, 'SUMMARY.md'), 'utf8'));
const text = (node) => node.value ?? (node.children ?? []).map(text).join('');
/** @typedef {{title: string, source?: string, url?: string, children: NavigationItem[]}} NavigationItem */
/** @returns {NavigationItem[]} */
function items(list) {
  return list.children.map((item) => {
    const paragraph = item.children.find((node) => node.type === 'paragraph');
    const link = paragraph?.children.find((node) => node.type === 'link');
    const nested = item.children.find((node) => node.type === 'list');
    return {
      title: link ? text(link) : text(paragraph),
      source: link?.url,
      url: link ? routeFor(link.url) : undefined,
      children: nested ? items(nested) : [],
    };
  });
}
/** @type {Record<string, NavigationItem[]>} */
export const navigation = {};
let section;
for (const node of tree.children) {
  if (node.type === 'heading') section = text(node);
  if (node.type === 'list') navigation[section] = items(node);
}
export function flatten(nodes) {
  return nodes.flatMap((node) => [node, ...flatten(node.children)]);
}
export const guideNavigation = navigation.Guides;
export const guideNodes = flatten(guideNavigation);
export function childrenFor(source) {
  if (source === 'guides/README.md') return guideNavigation;
  return guideNodes.find((node) => node.source === source)?.children ?? [];
}
