import { toHtml } from 'hast-util-to-html';

const text = (value) => ({ type: 'text', value });
export const element = (tagName, properties, children) => ({
  type: 'element', tagName, properties, children,
});

// The margin carries recorded facts only. A guide's own rules omit the identity, since the
// page title and the heading beside them already state it; null means nothing to show.
export function citationNode({ guide, section, url, pins = [] }) {
  const children = [];
  if (guide) {
    children.push(element('div', { className: ['citation-identity'] }, [
      element('p', { className: ['serial'] }, [
        element('a', { href: url }, [text(guide)]),
      ]),
      element('p', { className: ['citation-section'] }, [text(section)]),
    ]));
  }
  if (pins.length) {
    children.push(element('dl', { className: ['context'] }, [
      element('dt', {}, [text(pins.length === 1 ? 'Recorded pin' : 'Recorded pins')]),
      ...pins.map((pin) => element('dd', {}, [element('code', { className: ['pin'] }, [text(pin)])])),
    ]));
  }
  if (!children.length) return null;
  return element('aside', {
    className: ['citation'],
    ariaLabel: 'Rule source and pins',
    dataPagefindIgnore: true,
  }, children);
}

export const citationHTML = (context) => toHtml(citationNode(context));

export function recordedHookPins(code) {
  return [...code.matchAll(/-\s+repo:\s+https:\/\/github\.com\/([\w./-]+)\s*\n\s+rev:\s+([^\s#]+)/g)]
    .map((match) => `${match[1]} ${match[2]}`);
}
