import { toHtml } from 'hast-util-to-html';

const text = (value) => ({ type: 'text', value });
export const element = (tagName, properties, children) => ({
  type: 'element', tagName, properties, children,
});

export function citationNode({ guide, section, url, pins = [] }) {
  const field = (label, value) => [
    element('dt', {}, [text(label)]),
    element('dd', {}, [text(value)]),
  ];
  return element('aside', {
    className: ['citation'],
    ariaLabel: 'Rule identity and context',
    dataPagefindIgnore: true,
  }, [
    element('div', { className: ['citation-identity'] }, [
      element('p', { className: ['serial'] }, [
        element('a', { href: url }, [text(guide)]),
      ]),
      element('p', { className: ['citation-section'] }, [text(section)]),
      element('p', { className: ['id-note'] }, [text('Identifier not yet assigned')]),
    ]),
    element('dl', { className: ['context'] }, [
      ...field('Scope', `${guide} / ${section}`),
      element('dt', {}, [text('Recorded pin')]),
      element('dd', {}, pins.length
        ? [element('code', { className: ['pin'] }, [text(pins.join('; '))])]
        : [text('See this section for applicable tool versions.')]),
      ...field('Review date', 'Not recorded for this rule.'),
      ...field('Evidence', 'Read the source and its reasons. Tool behavior is not rechecked by this site build.'),
    ]),
  ]);
}

export const citationHTML = (context) => toHtml(citationNode(context));

export function recordedHookPins(code) {
  return [...code.matchAll(/-\s+repo:\s+https:\/\/github\.com\/([\w./-]+)\s*\n\s+rev:\s+([^\s#]+)/g)]
    .map((match) => `${match[1]} ${match[2]}`);
}
