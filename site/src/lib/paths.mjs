import { readFileSync, existsSync, statSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import path from 'node:path';

export const repository = path.resolve('..');
export const version = readFileSync(path.join(repository, 'VERSION'), 'utf8').trim();
export const commit = execFileSync('git', ['rev-parse', 'HEAD'], {
  cwd: repository, encoding: 'utf8',
}).trim();
export const sourceURL = (source) =>
  `https://github.com/agh/crefft/blob/${commit}/${source}`;

export function routeFor(source) {
  if (source === 'README.md') return '/';
  if (source === 'AGENTS.md') return '/for-agents/';
  if (source === 'reference/README.md') return '/reference/';
  if (source === 'guides/languages/rust/README.md') return '/guides/languages/rust/topics/';
  return `/${source.replace(/(?:\/README)?\.md$/, '')}/`;
}

export function markdownFor(route) {
  return route === '/' ? '/index.md' : `${route.replace(/\/$/, '')}.md`;
}

export function resolveSourceLink(url, source, markdown = false) {
  if (/^(?:https?:|mailto:)/i.test(url)) return url;
  if (/^[a-z][a-z0-9+.-]*:|^\/\//i.test(url)) throw new Error(`Unsafe link: ${url}`);
  if (url.startsWith('#')) return url;
  if (path.resolve(source) === path.join(repository, 'agents/system/docker.md')
    && url === 'docker.md#secrets-vs-environment-variables') {
    url = '../../guides/infrastructure/docker.md#secrets-vs-environment-variables';
  }
  const [, pathname, suffix] = url.match(/^([^?#]*)(.*)$/);
  const target = pathname.startsWith('/')
    ? path.resolve(repository, `.${decodeURIComponent(pathname)}`)
    : path.resolve(path.dirname(source), decodeURIComponent(pathname));
  const relative = path.relative(repository, target).split(path.sep).join('/');
  if (relative.startsWith('../') || path.isAbsolute(relative)) {
    throw new Error(`Link leaves approved repository: ${source}: ${url}`);
  }
  if (existsSync(target) && statSync(target).isDirectory()) {
    return `${sourceURL(relative).replace('/blob/', '/tree/')}${suffix}`;
  }
  if (relative === 'README.md') return `${markdown ? '/index.md' : '/'}${suffix}`;
  if (/^guides\/.*\.md$/.test(relative)) {
    const route = routeFor(relative);
    return `${markdown ? markdownFor(route) : route}${suffix}`;
  }
  if (/^(agents|commands|configs)\/.*\.md$/.test(relative)) {
    const route = routeFor(relative);
    return `${markdown ? markdownFor(route) : route}${suffix}`;
  }
  if (relative === 'AGENTS.md') {
    return suffix.includes('#') ? `${sourceURL(relative)}${suffix}` : `/raw/AGENTS.md${suffix}`;
  }
  if (/^(agents|commands|configs)\//.test(relative)) return `/raw/${relative}${suffix}`;
  return `${sourceURL(relative)}${suffix}`;
}
