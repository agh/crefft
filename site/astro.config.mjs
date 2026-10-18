import { unified } from '@astrojs/markdown-remark';
import { defineConfig } from 'astro/config';
import { remarkPlugins, rehypePlugins } from './src/lib/markdown.mjs';

export default defineConfig({
  site: 'https://crefft.dev',
  cacheDir: './.cache/astro',
  output: 'static',
  trailingSlash: 'always',
  compressHTML: true,
  prerenderConflictBehavior: 'error',
  prefetch: false,
  build: { format: 'directory', inlineStylesheets: 'never' },
  markdown: {
    syntaxHighlight: false,
    processor: unified({ remarkPlugins, rehypePlugins }),
  },
  security: {
    csp: {
      directives: [
        "default-src 'self'",
        "base-uri 'none'",
        "object-src 'none'",
        "img-src 'self'",
        "font-src 'self'",
        "connect-src 'self'",
        "frame-src 'none'",
        "form-action 'self'",
        "worker-src 'self'",
      ],
    },
  },
});
