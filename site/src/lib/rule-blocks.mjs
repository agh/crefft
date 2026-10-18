import path from 'node:path';
import { citationNode, element, recordedHookPins } from './citation.mjs';
import { repository } from './paths.mjs';

const text = (node) => node.value ?? (node.children ?? []).map(text).join('');
const heading = (node) => node.type === 'element' && /^h[1-6]$/.test(node.tagName);
function normative(node) {
  if (node.tagName === 'pre' || node.tagName === 'code') return false;
  if (node.tagName === 'strong' && /^(MUST(?: NOT)?|SHOULD(?: NOT)?|MAY|REQUIRED|RECOMMENDED)$/.test(text(node))) return true;
  return (node.children ?? []).some(normative);
}

export default function ruleBlocks() {
  return (tree, file) => {
    if (!file.path) return;
    const source = path.relative(repository, path.resolve(file.path)).split(path.sep).join('/');
    if (!source.startsWith('guides/') || source.endsWith('/README.md')) return;
    const title = tree.children.find((node) => node.tagName === 'h1');
    if (!title) throw new Error(`Guide title missing: ${source}`);
    const result = [];
    for (let index = 0; index < tree.children.length;) {
      const first = tree.children[index];
      if (!heading(first) || first.tagName === 'h1') {
        result.push(first);
        index++;
        continue;
      }
      let end = index + 1;
      while (end < tree.children.length && !heading(tree.children[end])) end++;
      const nodes = tree.children.slice(index, end);
      if (nodes.slice(1).some(normative)) {
        const id = first.properties?.id;
        if (!id) throw new Error(`Rule section lacks a heading anchor: ${source}: ${text(first)}`);
        const pins = nodes.filter((node) => node.tagName === 'pre').flatMap((node) => recordedHookPins(text(node)));
        const citation = citationNode({ pins });
        result.push(element('section', { className: ['rule-record', 'guide-rule'], dataRuleSection: id }, [
          ...(citation ? [citation] : []),
          element('div', { className: ['record-main'] }, nodes),
        ]));
      } else {
        result.push(...nodes);
      }
      index = end;
    }
    tree.children = result;
  };
}
